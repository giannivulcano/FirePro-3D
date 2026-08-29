"""Title block template editor — form panel + live preview.

Governing spec: docs/specs/titleblock-template-system.md §Editor (rev 3 proposal).
The preview hosts the SAME renderer used on sheets (one render path).

Tab organisation (rev3):
  Overview      — paper-size + orientation + three margin/strip DimensionEdits
  Drawing Area  — area-border group
  Fields        — roster + intrinsics form + single-field preview (DD-18)
  Arrangements  — pool | strip canvas | placement props + strip border (DD-17)
"""
from __future__ import annotations

import base64
import copy
import datetime
import logging
import re as _re
import uuid as _uuid

from PyQt6.QtCore import Qt, QBuffer, QIODevice, QEvent, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGraphicsScene, QGraphicsView,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPushButton, QPlainTextEdit, QRadioButton,
    QSizePolicy, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QBrush, QColor, QImage, QKeySequence, QPen

from .titleblock_template import (
    TitleBlockTemplate, TemplateLayout, FieldDef, Slot, BorderStyle,
    KINDS, new_field_id, unplace_field,
    native_orientation,
    make_default_template, load_library, save_to_library, delete_from_library,
    solve_layout, validate,
)
from .paper_space import (
    PAPER_SIZES, TitleBlockTemplateItem, PROJECT_STD_KEYS,
    PROJECT_TOKEN_ALIASES, DEFAULT_TITLE_BLOCK_FIELDS,
)
from .dimension_edit import DimensionEdit
from .scale_manager import ScaleManager
from .titleblock_arrange import ArrangementsTab
from .constants import TB_PREVIEW_MIN_MM
from .theme import detect

# Module-level ScaleManager used as dimension parser throughout the editor.
# ScaleManager() is standalone (pixels_per_mm=1 → 1 px = 1 mm, display_unit=mm),
# so bare numbers are interpreted as mm, but "1 in" / "1\"" / "1 ft" etc. also work.
_sm = ScaleManager()

_log = logging.getLogger("FirePro3D")

_UNDO_STACK_MAX = 50

# Standard project info keys — imported from paper_space.PROJECT_STD_KEYS so that
# picker display names always match what build_field_values resolves.
# Do NOT add a local copy; edit paper_space.PROJECT_STD_KEYS to add new keys.

# Preview sample values (DD-13): the KEY SET must match build_field_values —
# derived from the same constants — so token-known/unknown behaves identically
# in editor previews and on sheets. Values are illustrative samples.
_SAMPLE_VALUES = {k: "" for k in PROJECT_STD_KEYS}
_SAMPLE_VALUES.update({k: "" for k in PROJECT_TOKEN_ALIASES})
_SAMPLE_VALUES.update({k: "" for k in DEFAULT_TITLE_BLOCK_FIELDS})
_SAMPLE_VALUES["Date (auto)"] = "22 Jul 2026"
_SAMPLE_VALUES["Sheet No"] = "FP-1.0"
_SAMPLE_VALUES.update({
    "Company": "Vulcano Fire Design Inc.", "Project": "Sample Project",
    "Address Line 1": "123 Example St",
    "Address": "123 Example St",   # legacy alias mirrors Line 1
    "Title": "Level 1 — Sprinkler Plan",
    "Scale": "1:100", "Date": "2026-07-21", "Drawn By": "GV",
    "Checked By": "—", "Drawing No": "FP-101", "Rev": "0",
    "__revisions__": [{"no": "1", "description": "Issued for permit",
                       "date": "07-21"}],
})

# Field key groups for the Insert field ▾ picker and token helper.
# Title and Drawing No are identity-derived (auto), not user-typed per-sheet.
_AUTO_FIELD_KEYS = ["Scale", "Date (auto)", "Sheet No", "Drawing No", "Title"]
_SHEET_FIELD_KEYS = ["Rev", "Date"]


def _template_page_mm(template: TitleBlockTemplate) -> tuple[float, float]:
    """Return (width_mm, height_mm) of the effective page for *template*.

    Swaps PAPER_SIZES dims when ``template.orientation`` differs from the
    paper size's native orientation.  This is the single authoritative place
    for the swap rule in the editor; matches the paper-space helper logic.

    Args:
        template: The template whose paper size and orientation to resolve.

    Returns:
        ``(width_mm, height_mm)`` in mm.
    """
    w, h = PAPER_SIZES.get(template.paper_size, (297.0, 420.0))
    if template.orientation != native_orientation(template.paper_size):
        w, h = h, w
    return w, h


# ─────────────────────────────────────────────────────────────────────────────
# Helper: colour swatch button
# ─────────────────────────────────────────────────────────────────────────────

def _make_swatch(color: str, parent: QWidget | None = None) -> QPushButton:
    """Return a small colour-swatch QPushButton displaying *color*."""
    btn = QPushButton(parent)
    btn.setFixedSize(28, 22)
    _update_swatch(btn, color)
    return btn


def _update_swatch(btn: QPushButton, color: str) -> None:
    c = QColor(color) if color else QColor(0, 0, 0, 0)
    if c.isValid() and color:
        btn.setStyleSheet(
            f"background-color: {c.name()}; border: 1px solid {detect().border_strong};")
    else:
        btn.setStyleSheet(f"background-color: transparent; border: 1px solid {detect().border_strong};")
    btn.setProperty("_color", color)


# ─────────────────────────────────────────────────────────────────────────────
# Border sub-group widget
# ─────────────────────────────────────────────────────────────────────────────

class _BorderGroup(QGroupBox):
    """Reusable widget for editing a BorderStyle (visible, width, color, corner, fillet).

    With ``show_edges=True`` (field cells only) an "Edges:" row of four
    per-edge checkboxes is added; fillet requires all four edges on
    (grill 2026-08-04 3b). Frame groups (area/strip) omit the row.
    """

    def __init__(self, title: str, parent: QWidget | None = None, *,
                 show_edges: bool = False):
        super().__init__(title, parent)
        self._show_edges = show_edges
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._visible = QCheckBox()
        form.addRow("Visible:", self._visible)

        if show_edges:
            edges_row = QHBoxLayout()
            self._edge_top = QCheckBox("Top")
            self._edge_bottom = QCheckBox("Bottom")
            self._edge_left = QCheckBox("Left")
            self._edge_right = QCheckBox("Right")
            for cb in (self._edge_top, self._edge_bottom,
                       self._edge_left, self._edge_right):
                cb.setChecked(True)
                cb.toggled.connect(self._sync_fillet_enabled)
                edges_row.addWidget(cb)
            edges_row.addStretch()
            form.addRow("Edges:", edges_row)

        self._width = DimensionEdit(None, initial_mm=0.5,
                                    parser=_sm.parse_dimension, minimum=0.0)
        form.addRow("Width (mm):", self._width)

        self._color_btn = _make_swatch("#000000", self)
        form.addRow("Color:", self._color_btn)
        self._color_btn.clicked.connect(self._pick_color)

        self._corner = QComboBox()
        self._corner.addItems(["Sharp", "Fillet"])
        form.addRow("Corner:", self._corner)

        self._fillet = DimensionEdit(None, initial_mm=0.0,
                                     parser=_sm.parse_dimension, minimum=0.0)
        form.addRow("Fillet radius (mm):", self._fillet)
        self._corner.currentIndexChanged.connect(self._on_corner_changed)

    def _pick_color(self):
        cur = QColor(self._color_btn.property("_color") or "#000000")
        c = QColorDialog.getColor(cur, self)
        if c.isValid():
            _update_swatch(self._color_btn, c.name())

    def _on_corner_changed(self, _):
        self._fillet.setEnabled(
            self._all_edges_on() and self._corner.currentText() == "Fillet")

    def _all_edges_on(self) -> bool:
        if not self._show_edges:
            return True
        return all(cb.isChecked() for cb in
                   (self._edge_top, self._edge_bottom,
                    self._edge_left, self._edge_right))

    def _sync_fillet_enabled(self) -> None:
        """Fillet requires all four edges (grill 2026-08-04 3b)."""
        full = self._all_edges_on()
        self._corner.setEnabled(full)
        self._fillet.setEnabled(
            full and self._corner.currentText() == "Fillet")
        tip = "" if full else "Fillet requires all four edges"
        self._corner.setToolTip(tip)
        self._fillet.setToolTip(tip)

    def load(self, style) -> None:
        """Populate widgets from a BorderStyle.

        Widget setters DO fire signals; callers must run under the dialog's
        ``_loading`` guard.
        """
        self._visible.setChecked(style.visible)
        self._width.set_value_mm(style.width_mm)
        _update_swatch(self._color_btn, style.color)
        self._corner.setCurrentText(
            "Fillet" if style.corner == "fillet" else "Sharp")
        self._fillet.set_value_mm(style.fillet_radius_mm)
        self._fillet.setEnabled(style.corner == "fillet")
        if self._show_edges:
            self._edge_top.setChecked(style.edge_top)
            self._edge_bottom.setChecked(style.edge_bottom)
            self._edge_left.setChecked(style.edge_left)
            self._edge_right.setChecked(style.edge_right)
            self._sync_fillet_enabled()

    def read(self) -> dict:
        """Return a dict suitable for BorderStyle.from_dict().

        Edge keys are included only when the group shows edge checkboxes;
        frame groups omit them (from_dict defaults them to True).
        """
        d = {
            "visible": self._visible.isChecked(),
            "width_mm": self._width.value_mm(),
            "color": self._color_btn.property("_color") or "#000000",
            "corner": "fillet" if self._corner.currentText() == "Fillet" else "sharp",
            "fillet_radius_mm": self._fillet.value_mm(),
        }
        if self._show_edges:
            d["edge_top"] = self._edge_top.isChecked()
            d["edge_bottom"] = self._edge_bottom.isChecked()
            d["edge_left"] = self._edge_left.isChecked()
            d["edge_right"] = self._edge_right.isChecked()
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Main dialog
# ─────────────────────────────────────────────────────────────────────────────

class TitleBlockEditorDialog(QDialog):
    """Library manager + per-template editor for TitleBlockTemplate objects.

    Usage::

        dlg = TitleBlockEditorDialog(project_template=current_template)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_tmpl = dlg.project_template_result  # None if user didn't click Use

    Public result attributes
    ------------------------
    project_template_result : TitleBlockTemplate | None
        Set by use_for_project(); None if the user never clicked "Use for project".
    result_saved : bool
        True once a successful Save has refreshed project_template_result —
        a SAVED use-intent survives Close (reject), so MainWindow applies the
        result when either the dialog was accepted or result_saved is True
        (holistic review 2026-08-04 finding 1). Unsaved use-intents still
        discard on Close.
    """

    #: Emitted after a successful mid-session Save with a COPY of the saved
    #: template. MainWindow uses it to live-refresh the project template
    #: (uuid match) without waiting for dialog close.
    templateSaved = pyqtSignal(object)

    def __init__(self, project_template: TitleBlockTemplate | None = None,
                 parent: QWidget | None = None,
                 project_info: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Title Block Template Editor")
        self.setMinimumSize(640, 760)

        # ── Public state ──────────────────────────────────────────────────
        self.working: TitleBlockTemplate | None = None
        self.project_template_result: TitleBlockTemplate | None = None
        # True once _do_save() has refreshed project_template_result from a
        # successful library write; project_template_result is never reset
        # after __init__, so this flag has the same single reset point.
        self.result_saved: bool = False
        self._project_info = project_info or {}
        self._use_requested = False   # set by use_for_project(); read by _do_save

        # ── Snapshot undo/redo stacks ─────────────────────────────────────
        # Each entry is a dict snapshot from TitleBlockTemplate.to_dict()
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []

        # ── Loading guard (suppress snapshot pushes during UI population) ─
        self._loading = False

        # ── Preview scene (reused across refresh_preview calls) ────────────
        self._preview_scene = QGraphicsScene(self)

        # ── Field preview scene (single-field preview on Fields tab) ───────
        self._field_preview_scene = QGraphicsScene(self)

        # ── Build UI ──────────────────────────────────────────────────────
        self._build_ui()

        # ── Load library and pre-select project template if provided ───────
        self._reload_library()
        if project_template is not None:
            # Edit a copy so cancel truly discards
            self._edit_copy_of(project_template)
        else:
            # No project template: ensure the initial state is reflected
            # (save_button stays disabled; preview shows empty state)
            self.refresh_preview()

    # ═════════════════════════════════════════════════════════════════════════
    # UI construction
    # ═════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setSpacing(8)

        # ── Left panel: library list + actions ────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(QLabel("Templates:"))
        self._template_list = QListWidget()
        self._template_list.setMinimumWidth(180)
        self._template_list.setMaximumWidth(220)
        self._template_list.currentItemChanged.connect(self._on_list_selection)
        left.addWidget(self._template_list, stretch=1)

        btn_row = QHBoxLayout()
        self._new_btn = QPushButton("New")
        self._new_btn.clicked.connect(self.new_template)
        self._dup_btn = QPushButton("Duplicate")
        self._dup_btn.clicked.connect(self.duplicate_template)
        btn_row.addWidget(self._new_btn)
        btn_row.addWidget(self._dup_btn)
        left.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        self._del_btn = QPushButton("Delete")
        self._del_btn.clicked.connect(self.delete_template)
        self._use_btn = QPushButton("Use for project")
        self._use_btn.clicked.connect(self.use_for_project)
        btn_row2.addWidget(self._del_btn)
        btn_row2.addWidget(self._use_btn)
        left.addLayout(btn_row2)

        root.addLayout(left)

        # ── Centre: form (single column — tabs full width) ────────────────
        centre = QVBoxLayout()
        centre.setSpacing(6)

        # ── Component tabs (Overview / Drawing Area / Fields) ─────────────
        self._component_tabs = QTabWidget()
        centre.addWidget(self._component_tabs, stretch=1)

        # ── Tab 0: Overview ────────────────────────────────────────────────
        overview_widget = QWidget()
        overview_layout = QVBoxLayout(overview_widget)
        overview_layout.setSpacing(6)

        overview_form_group = QGroupBox("Paper Setup")
        overview_form = QFormLayout(overview_form_group)
        overview_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name row — first inside Paper Setup (Fix 3)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Template name")
        self._name_edit.editingFinished.connect(
            lambda: self.set_name(self._name_edit.text()))
        overview_form.addRow("Name:", self._name_edit)

        # Paper size combo
        self._paper_size_combo = QComboBox()
        self._paper_size_combo.addItems(list(PAPER_SIZES.keys()))
        self._paper_size_combo.currentTextChanged.connect(
            lambda t: self.set_paper_size(t))
        overview_form.addRow("Paper size:", self._paper_size_combo)

        # Orientation toggle (two radio buttons)
        orient_widget = QWidget()
        orient_row = QHBoxLayout(orient_widget)
        orient_row.setContentsMargins(0, 0, 0, 0)
        self._orient_landscape = QRadioButton("Landscape")
        self._orient_portrait = QRadioButton("Portrait")
        self._orient_landscape.setChecked(True)
        orient_row.addWidget(self._orient_landscape)
        orient_row.addWidget(self._orient_portrait)
        orient_row.addStretch()
        self._orient_landscape.toggled.connect(self._on_orientation_toggled)
        self._orient_portrait.toggled.connect(self._on_orientation_toggled)
        overview_form.addRow("Orientation:", orient_widget)

        # Three margin/strip DimensionEdits
        self._edge_edit = DimensionEdit(None, initial_mm=10.0,
                                        parser=_sm.parse_dimension, minimum=0.0)
        self._edge_edit.valueChanged.connect(self.set_margin_edge)
        overview_form.addRow("Edge margin (mm):", self._edge_edit)

        self._strip_margin_edit = DimensionEdit(None, initial_mm=5.0,
                                                parser=_sm.parse_dimension, minimum=0.0)
        self._strip_margin_edit.valueChanged.connect(self.set_margin_strip)
        overview_form.addRow("Strip gap (mm):", self._strip_margin_edit)

        self._strip_width_edit = DimensionEdit(None, initial_mm=90.0,
                                               parser=_sm.parse_dimension, minimum=0.0)
        self._strip_width_edit.valueChanged.connect(self.set_strip_width)
        overview_form.addRow("Strip width (mm):", self._strip_width_edit)

        overview_layout.addWidget(overview_form_group)

        # Preview group — below Paper Setup, inside Overview tab (Fix 2)
        preview_group = QGroupBox("Preview")
        preview_group_layout = QVBoxLayout(preview_group)
        preview_group_layout.setContentsMargins(4, 4, 4, 4)

        self._preview_view = QGraphicsView(self._preview_scene)
        self._preview_view.setMinimumHeight(280)
        self._preview_view.setRenderHint(
            self._preview_view.renderHints().__class__.Antialiasing)
        self._preview_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_group_layout.addWidget(self._preview_view)

        overview_layout.addWidget(preview_group, stretch=1)

        self._component_tabs.addTab(overview_widget, "Overview")

        # Refresh fitInView when the Overview tab becomes visible so the fit
        # runs with a realized viewport (avoids the empty-rect on first show).
        self._component_tabs.currentChanged.connect(self._on_tab_changed)

        # ── Tab 1: Drawing Area ────────────────────────────────────────────
        area_widget = QWidget()
        area_layout = QVBoxLayout(area_widget)
        area_layout.setSpacing(6)

        self._area_border = _BorderGroup("Drawing Area Border")
        area_layout.addWidget(self._area_border)
        area_layout.addStretch()

        # Wire border change signals
        self._area_border._visible.toggled.connect(self._on_border_changed)
        self._area_border._width.valueChanged.connect(
            lambda _: self._on_border_changed())
        self._area_border._color_btn.clicked.connect(self._on_border_changed)
        self._area_border._corner.currentIndexChanged.connect(
            lambda _: self._on_border_changed())
        self._area_border._fillet.valueChanged.connect(
            lambda _: self._on_border_changed())

        self._component_tabs.addTab(area_widget, "Drawing Area")

        # ── Strip border group — lives on the Arrangements tab (DD-17) ─────
        # Constructed here so its change signals wire alongside the area
        # border's; re-parented into the Arrangements tab's third column.
        self._strip_border = _BorderGroup("Info Strip Border")

        # Wire strip border change signals (writes strip_border to working + snapshot)
        self._strip_border._visible.toggled.connect(self._on_border_changed)
        self._strip_border._width.valueChanged.connect(
            lambda _: self._on_border_changed())
        self._strip_border._color_btn.clicked.connect(self._on_border_changed)
        self._strip_border._corner.currentIndexChanged.connect(
            lambda _: self._on_border_changed())
        self._strip_border._fillet.valueChanged.connect(
            lambda _: self._on_border_changed())

        # ── Tab 2: Fields (DD-18) ─────────────────────────────────────────
        fields_widget = QWidget()
        fields_layout = QHBoxLayout(fields_widget)
        fields_layout.setSpacing(6)

        # ── LEFT: roster ─────────────────────────────────────────────────
        roster_col = QVBoxLayout()
        roster_col.addWidget(QLabel("Fields:"))
        self._field_list = QListWidget()
        self._field_list.setMinimumWidth(140)
        self._field_list.setMaximumWidth(180)
        self._field_list.currentRowChanged.connect(self._on_field_selected)
        roster_col.addWidget(self._field_list, stretch=1)

        roster_btns = QHBoxLayout()
        self._new_field_btn = QPushButton("New")
        self._new_field_btn.clicked.connect(self._new_field)
        self._dup_field_btn = QPushButton("Duplicate")
        self._dup_field_btn.clicked.connect(self._duplicate_field)
        self._delete_field_btn = QPushButton("Delete")
        self._delete_field_btn.clicked.connect(self._delete_field)
        roster_btns.addWidget(self._new_field_btn)
        roster_btns.addWidget(self._dup_field_btn)
        roster_btns.addWidget(self._delete_field_btn)
        roster_col.addLayout(roster_btns)
        fields_layout.addLayout(roster_col)

        # ── MIDDLE: intrinsics form (grouped — grill 2026-08-04) ──────────
        self._field_form_widget = QWidget()
        self._field_form_widget.setMinimumWidth(260)
        self._field_form_widget.setEnabled(False)
        form_col = QVBoxLayout(self._field_form_widget)
        form_col.setSpacing(6)

        def _group(title):
            box = QGroupBox(title)
            f = QFormLayout(box)
            f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            return box, f

        # ── Identity group ────────────────────────────────────────────────
        identity_box, identity_form = _group("Identity")

        # Name
        self._fname_edit = QLineEdit()
        self._fname_edit.editingFinished.connect(
            lambda: self._field_prop("name", self._fname_edit.text()))
        identity_form.addRow("Name:", self._fname_edit)

        # Label
        self._flabel_edit = QLineEdit()
        self._flabel_edit.editingFinished.connect(
            lambda: self._field_prop("label", self._flabel_edit.text()))
        identity_form.addRow("Label:", self._flabel_edit)

        # Kind combo
        self._fkind_combo = QComboBox()
        self._fkind_combo.addItems(list(KINDS))
        self._fkind_combo.currentTextChanged.connect(self._on_kind_changed)
        identity_form.addRow("Kind:", self._fkind_combo)

        form_col.addWidget(identity_box)

        # ── Content group ─────────────────────────────────────────────────
        content_box, content_form = _group("Content")

        # Text (multi-line) + Insert token button
        text_vbox = QVBoxLayout()
        text_vbox.setSpacing(2)
        self._ftext_edit = QPlainTextEdit()
        self._ftext_edit.setFixedHeight(72)
        self._ftext_edit.installEventFilter(self)
        text_vbox.addWidget(self._ftext_edit)
        self._insert_btn = QPushButton("Insert field ▾")
        self._insert_btn.clicked.connect(self._show_insert_menu)
        text_vbox.addWidget(self._insert_btn)
        content_form.addRow("Text:", text_vbox)

        # Image controls (grill 2026-08-04 item 4): real thumbnail,
        # Choose/Clear, and an explicit height input (0 = auto band).
        img_row = QVBoxLayout()
        img_row.setSpacing(4)
        self._fimg_thumb = QLabel()
        self._fimg_thumb.setFixedSize(120, 72)
        self._fimg_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fimg_thumb.setStyleSheet(
            f"border: 1px solid {detect().border_strong}; "
            "background: #fff;"  # theme-exempt: white paper preview
        )
        img_row.addWidget(self._fimg_thumb)
        img_btns = QHBoxLayout()
        self._fimg_btn = QPushButton("Choose image…")
        self._fimg_btn.clicked.connect(self._pick_field_image)
        img_btns.addWidget(self._fimg_btn)
        self._fimg_clear = QPushButton("Clear")
        self._fimg_clear.clicked.connect(
            lambda: self._field_prop("image_data", ""))
        img_btns.addWidget(self._fimg_clear)
        img_btns.addStretch()
        img_row.addLayout(img_btns)
        height_row = QHBoxLayout()
        height_row.addWidget(QLabel("Height (mm):"))
        self._fimg_height = DimensionEdit(None, initial_mm=0.0,
                                          parser=_sm.parse_dimension,
                                          minimum=0.0)
        self._fimg_height.valueChanged.connect(
            lambda v: self._field_prop("image_height_mm", v))
        height_row.addWidget(self._fimg_height)
        height_row.addWidget(QLabel("(0 = auto)"))
        height_row.addStretch()
        img_row.addLayout(height_row)
        content_form.addRow("Image:", img_row)

        # Revision rows spinbox (revision_table only)
        self._frev_rows = QSpinBox()
        self._frev_rows.setRange(1, 10)
        self._frev_rows.setKeyboardTracking(False)
        self._frev_rows.valueChanged.connect(
            lambda v: self._field_prop("revision_rows", v))
        content_form.addRow("Revision rows:", self._frev_rows)

        form_col.addWidget(content_box)

        # ── Text Style group ──────────────────────────────────────────────
        style_box, style_form = _group("Text Style")

        # Text style: font family
        self._ffont_combo = QComboBox()
        self._ffont_combo.addItems(["Arial", "Helvetica", "Times New Roman",
                                     "Courier New", "Calibri"])
        self._ffont_combo.setEditable(True)
        # Commit only on dropdown pick (activated) or typed entry (editingFinished)
        # to avoid per-keystroke snapshots from currentTextChanged.
        self._ffont_combo.activated.connect(self._commit_font_family)
        self._ffont_combo.lineEdit().editingFinished.connect(self._commit_font_family)
        style_form.addRow("Font:", self._ffont_combo)

        # Cap height
        self._fcap_height = DimensionEdit(None, initial_mm=3.0,
                                          parser=_sm.parse_dimension, minimum=0.0)
        self._fcap_height.valueChanged.connect(
            lambda v: self._field_prop("cap_height_mm", v))
        style_form.addRow("Cap height (mm):", self._fcap_height)

        # Bold / italic checkboxes (one row)
        self._fbold = QCheckBox()
        self._fbold.toggled.connect(
            lambda b: self._field_prop("bold", b))
        self._fitalic = QCheckBox()
        self._fitalic.toggled.connect(
            lambda b: self._field_prop("italic", b))
        bi_row = QHBoxLayout()
        bi_row.addWidget(self._fbold)
        bi_row.addWidget(QLabel("Italic:"))
        bi_row.addWidget(self._fitalic)
        bi_row.addStretch()
        style_form.addRow("Bold:", bi_row)

        # Alignment
        self._falign = QComboBox()
        self._falign.addItems(["left", "center", "right"])
        self._falign.currentTextChanged.connect(
            lambda t: self._field_prop("alignment", t))
        style_form.addRow("Alignment:", self._falign)

        # Text colour (label + body + revision text; grill 2026-08-04 item 6)
        self._ftext_color_swatch = _make_swatch("#000000", self)
        self._ftext_color_swatch.clicked.connect(self._pick_text_color)
        style_form.addRow("Text colour:", self._ftext_color_swatch)

        form_col.addWidget(style_box)

        # ── Fill & Border group ───────────────────────────────────────────
        fb_box = QGroupBox("Fill & Border")
        fb_col = QVBoxLayout(fb_box)
        fb_form = QFormLayout()
        fb_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Fill color swatch + None clear
        fill_row = QHBoxLayout()
        self._ffield_fill_swatch = _make_swatch("", self)
        self._ffield_fill_swatch.clicked.connect(self._pick_field_fill)
        fill_row.addWidget(self._ffield_fill_swatch)
        fill_clear_btn = QPushButton("None")
        fill_clear_btn.setFixedWidth(40)
        fill_clear_btn.clicked.connect(
            lambda: self._field_prop("fill_color", ""))
        fill_row.addWidget(fill_clear_btn)
        fill_row.addStretch()
        fb_form.addRow("Fill:", fill_row)
        fb_col.addLayout(fb_form)

        # Cell border group
        self._field_border_group = _BorderGroup("Cell Border", show_edges=True)
        self._field_border_group._visible.toggled.connect(
            self._on_field_border_changed)
        for cb in (self._field_border_group._edge_top,
                   self._field_border_group._edge_bottom,
                   self._field_border_group._edge_left,
                   self._field_border_group._edge_right):
            cb.toggled.connect(lambda _: self._on_field_border_changed())
        self._field_border_group._width.valueChanged.connect(
            lambda _: self._on_field_border_changed())
        self._field_border_group._color_btn.clicked.connect(
            self._on_field_border_changed)
        self._field_border_group._corner.currentIndexChanged.connect(
            lambda _: self._on_field_border_changed())
        self._field_border_group._fillet.valueChanged.connect(
            lambda _: self._on_field_border_changed())
        fb_col.addWidget(self._field_border_group)

        form_col.addWidget(fb_box)
        form_col.addStretch()

        fields_layout.addWidget(self._field_form_widget)

        # ── RIGHT: single-field preview ───────────────────────────────────
        preview_col = QVBoxLayout()
        preview_col.addWidget(QLabel("Preview:"))
        self._field_preview_view = QGraphicsView(self._field_preview_scene)
        self._field_preview_view.setMinimumWidth(180)
        self._field_preview_view.setRenderHint(
            self._field_preview_view.renderHints().__class__.Antialiasing)
        self._field_preview_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_col.addWidget(self._field_preview_view, stretch=1)
        fields_layout.addLayout(preview_col)

        self._component_tabs.addTab(fields_widget, "Fields")

        # ── Tab 3: Arrangements (DD-17) ───────────────────────────────────
        self._arrange_tab = ArrangementsTab(self._strip_border)
        self._component_tabs.addTab(self._arrange_tab, "Arrangements")
        canvas = self._arrange_tab.canvas
        canvas.set_provider(self._arrange_provider)
        canvas.gestureStarting.connect(self.push_snapshot)
        canvas.gestureCompleted.connect(self._after_arrange_gesture)
        canvas.selectionChanged.connect(self._on_canvas_selection)
        canvas.unplaceRequested.connect(self._unplace_from_canvas)
        self._arrange_tab.min_height.valueChanged.connect(
            self._on_placement_min_height)
        self._arrange_tab.sizing.currentTextChanged.connect(
            self._on_placement_sizing)

        root.addLayout(centre, stretch=1)

        # ── Bottom: warnings + Save / Save && Close / Close (outside tabs) ──
        self._warning_label = QLabel()
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet(f"color: {detect().warn}; font-size: 11px;")
        self._warning_label.setVisible(False)
        centre.addWidget(self._warning_label)

        self._btn_box = QDialogButtonBox()
        self.save_button = self._btn_box.addButton(
            "Save", QDialogButtonBox.ButtonRole.ApplyRole)
        self.save_button.setEnabled(False)   # disabled until a valid template is loaded
        self.save_button.clicked.connect(self._on_save_clicked)
        self.save_close_button = self._btn_box.addButton(
            "Save && Close", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save_close_button.setEnabled(False)
        self.save_close_button.clicked.connect(self._on_save_close_clicked)
        self.close_button = self._btn_box.addButton(
            "Close", QDialogButtonBox.ButtonRole.RejectRole)
        self.close_button.clicked.connect(self.reject)
        centre.addWidget(self._btn_box)

    # ═════════════════════════════════════════════════════════════════════════
    # Event filter (FocusOut on QPlainTextEdit commits the text)
    # ═════════════════════════════════════════════════════════════════════════

    def eventFilter(self, obj, event) -> bool:
        if obj is self._ftext_edit and event.type() == QEvent.Type.FocusOut:
            self._commit_field_text()
        return super().eventFilter(obj, event)

    # ═════════════════════════════════════════════════════════════════════════
    # Library management
    # ═════════════════════════════════════════════════════════════════════════

    def _reload_library(self) -> None:
        """Reload the library list widget from disk.

        Each item displays the template's ``display_name`` ("Name (SIZE)" or
        "Name (SIZE, Portrait)") with the uuid stored in UserRole.
        """
        self._loading = True
        self._template_list.clear()
        for tmpl in load_library():
            item = QListWidgetItem(tmpl.display_name)
            item.setData(Qt.ItemDataRole.UserRole, tmpl.uuid)
            self._template_list.addItem(item)
        self._loading = False

    def _on_list_selection(self, current, _previous) -> None:
        if self._loading or current is None:
            return
        uid = current.data(Qt.ItemDataRole.UserRole)
        self.select_template(uid)

    # ── Public session API ────────────────────────────────────────────────

    def select_template(self, uuid: str) -> None:
        """Load the library template with *uuid* into the working copy."""
        for tmpl in load_library():
            if tmpl.uuid == uuid:
                self._edit_copy_of(tmpl)
                # Sync list selection without retriggering
                self._loading = True
                for i in range(self._template_list.count()):
                    if self._template_list.item(i).data(
                            Qt.ItemDataRole.UserRole) == uuid:
                        self._template_list.setCurrentRow(i)
                        break
                self._loading = False
                return

    def _edit_copy_of(self, tmpl: TitleBlockTemplate) -> None:
        """Begin editing a deep copy of *tmpl*; clears undo stacks."""
        self.working = tmpl.copy()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._populate_form()

    def new_template(self) -> None:
        """Create a fresh template in the working copy (not yet saved)."""
        tmpl = make_default_template()
        tmpl.name = "New Template"
        self.working = tmpl
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._populate_form()

    def duplicate_template(self) -> None:
        """Duplicate the working template with a fresh UUID."""
        if self.working is None:
            return
        new_tmpl = self.working.copy()
        new_tmpl.uuid = str(_uuid.uuid4())
        new_tmpl.name = new_tmpl.name + " (copy)"
        self.working = new_tmpl
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._populate_form()

    def delete_template(self) -> None:
        """Delete the currently selected template from the library (after confirm)."""
        if self.working is None:
            return
        resp = QMessageBox.question(
            self, "Delete Template",
            f"Delete '{self.working.name}' from the library?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_from_library(self.working.uuid)
        except (ValueError, OSError) as exc:
            _log.warning("Failed to delete template: %s", exc)
        self.working = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._reload_library()
        self._populate_form()

    def save(self) -> bool:
        """Stamp modified date and write the working template to the library.

        Returns:
            True on success, False when working is None or save fails.
            On failure the modified stamp is restored to its pre-call value
            so the working copy is not left with a spurious date.
        """
        if self.working is None:
            return False
        old_modified = self.working.modified
        self.working.modified = datetime.date.today().isoformat()
        try:
            save_to_library(self.working)
        except (OSError, ValueError) as exc:
            self.working.modified = old_modified
            _log.warning("Failed to save template: %s", exc)
            QMessageBox.warning(self, "Save Failed",
                                f"Could not save template:\n{exc}")
            return False
        self._reload_library()
        # Re-sync list selection
        uid = self.working.uuid
        self._loading = True
        for i in range(self._template_list.count()):
            if self._template_list.item(i).data(Qt.ItemDataRole.UserRole) == uid:
                self._template_list.setCurrentRow(i)
                break
        self._loading = False
        return True

    def use_for_project(self) -> None:
        """Set project_template_result to a copy of the working template.

        Also sets ``_use_requested`` so that a subsequent Save will refresh
        project_template_result from the (possibly modified) post-save working copy.
        """
        if self.working is None:
            return
        self._use_requested = True
        self.project_template_result = self.working.copy()

    # ═════════════════════════════════════════════════════════════════════════
    # Snapshot undo / redo
    # ═════════════════════════════════════════════════════════════════════════

    def push_snapshot(self) -> None:
        """Push the current working state onto the undo stack; clears redo.

        The undo stack is capped at ``_UNDO_STACK_MAX`` entries; the oldest
        entry is dropped when the cap is exceeded.
        """
        if self.working is None:
            return
        self._undo_stack.append(copy.deepcopy(self.working.to_dict()))
        if len(self._undo_stack) > _UNDO_STACK_MAX:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> None:
        """Restore the previous snapshot (if any)."""
        if len(self._undo_stack) < 1:
            return
        # Push current state to redo before restoring
        if self.working is not None:
            self._redo_stack.append(copy.deepcopy(self.working.to_dict()))
        snap = self._undo_stack.pop()
        self.working = TitleBlockTemplate.from_dict(snap)
        self._populate_form()

    def redo(self) -> None:
        """Re-apply the next snapshot (if any)."""
        if not self._redo_stack:
            return
        if self.working is not None:
            self._undo_stack.append(copy.deepcopy(self.working.to_dict()))
        snap = self._redo_stack.pop()
        self.working = TitleBlockTemplate.from_dict(snap)
        self._populate_form()

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo()
            event.accept()
            return
        if (event.matches(QKeySequence.StandardKey.Redo)
                or (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and event.key() == Qt.Key.Key_Y)
                or (event.modifiers() == (Qt.KeyboardModifier.ControlModifier
                                          | Qt.KeyboardModifier.ShiftModifier)
                    and event.key() == Qt.Key.Key_Z)):
            self.redo()
            event.accept()
            return
        super().keyPressEvent(event)

    # ═════════════════════════════════════════════════════════════════════════
    # Preview
    # ═════════════════════════════════════════════════════════════════════════

    def refresh_preview(self) -> None:
        """Rebuild the preview scene using the current working template.

        Page dims are computed via ``_template_page_mm`` (swap rule respects
        orientation vs. native orientation for the selected paper size).
        """
        self._preview_scene.clear()
        enabled = False
        warnings: list[str] = []

        if self.working is None:
            self._warning_label.setVisible(False)
            self.save_button.setEnabled(False)
            self.save_close_button.setEnabled(False)
            return

        # Single-size model: use the template's layout and oriented paper dims
        variant = self.working.layout
        paper_w, paper_h = _template_page_mm(self.working)

        # Validate first (save-blocking errors)
        errs = validate(variant, paper_w, paper_h)
        if errs:
            warnings.extend(errs)
        else:
            enabled = True

        # Draw paper background
        paper_rect = self._preview_scene.addRect(0, 0, paper_w, paper_h)
        paper_rect.setBrush(QBrush(QColor("#ffffff")))

        # Solve layout and build renderer item regardless (clamp-hardened)
        try:
            layout = solve_layout(variant, paper_w, paper_h, _SAMPLE_VALUES)
        except Exception as exc:
            warnings.append(f"Layout error: {exc}")
            self._show_warnings(warnings)
            self.save_button.setEnabled(False)
            self.save_close_button.setEnabled(False)
            return

        warnings.extend(layout.warnings)

        try:
            item = TitleBlockTemplateItem(layout, variant, _SAMPLE_VALUES)
            self._preview_scene.addItem(item)
            warnings.extend(item.warnings)
        except Exception as exc:
            warnings.append(f"Render error: {exc}")

        self._show_warnings(warnings)
        self.save_button.setEnabled(enabled)
        self.save_close_button.setEnabled(enabled)
        # Use itemsBoundingRect (not sceneRect) so the rect shrinks when
        # switching from a large paper size (e.g. ANSI D) to a small one
        # (e.g. A4). QGraphicsScene.clear() resets sceneRect lazily; stale
        # huge rects cause the preview to zoom to near-invisible.
        items_rect = self._preview_scene.itemsBoundingRect()
        if not items_rect.isEmpty():
            self._preview_scene.setSceneRect(items_rect)
            self._preview_view.fitInView(
                items_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _show_warnings(self, warnings: list[str]) -> None:
        if warnings:
            self._warning_label.setText("\n".join(warnings))
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)

    # ═════════════════════════════════════════════════════════════════════════
    # Form population (load working → widgets; guarded by _loading)
    # ═════════════════════════════════════════════════════════════════════════

    def _populate_form(self) -> None:
        """Populate all form widgets from self.working. Does NOT push snapshots."""
        self._loading = True
        try:
            self._populate_form_inner()
        finally:
            self._loading = False
        self.refresh_preview()

    def _populate_form_inner(self) -> None:
        if self.working is None:
            self._name_edit.clear()
            self._field_list.clear()
            self._field_form_widget.setEnabled(False)
            self._field_preview_scene.clear()
            # Clear the Arrangements tab gracefully: refresh against an empty
            # layout (provider falls back to the same empty state).
            self._arrange_tab.refresh(TemplateLayout())
            return

        self._name_edit.setText(self.working.name)
        self._populate_overview_fields()
        self._populate_variant_fields()
        self._rebuild_field_list()
        # Deselect field form when repopulating
        self._field_form_widget.setEnabled(False)
        self._field_preview_scene.clear()
        self._arrange_tab.refresh(self.working.layout)
        # Re-sync placement props from the (possibly restored) canvas
        # selection so the min-height edit / sizing combo never display
        # stale pre-undo values.
        self._on_canvas_selection(self._arrange_tab.canvas.selected_field_id)

    def _populate_overview_fields(self) -> None:
        """Populate paper-size combo + orientation radios from working template."""
        if self.working is None:
            return
        # Paper size combo
        idx = self._paper_size_combo.findText(self.working.paper_size)
        if idx >= 0:
            self._paper_size_combo.setCurrentIndex(idx)
        # Orientation radios
        if self.working.orientation == "portrait":
            self._orient_portrait.setChecked(True)
        else:
            self._orient_landscape.setChecked(True)

    def _populate_variant_fields(self) -> None:
        """Update margin/border widgets from the active layout (no snapshot)."""
        if self.working is None:
            return
        variant = self.working.layout
        self._edge_edit.set_value_mm(variant.margin_edge_mm)
        self._strip_margin_edit.set_value_mm(variant.margin_strip_mm)
        self._strip_width_edit.set_value_mm(variant.strip_width_mm)
        self._area_border.load(variant.area_border)
        self._strip_border.load(variant.strip_border)

    # ═════════════════════════════════════════════════════════════════════════
    # Fields tab — roster helpers
    # ═════════════════════════════════════════════════════════════════════════

    def _rebuild_field_list(self, keep_row: bool = False) -> None:
        """Repopulate the field roster list from active layout's fields.

        Args:
            keep_row: When True, restore the current row after clearing.
        """
        prev_row = self._field_list.currentRow() if keep_row else -1
        self._field_list.blockSignals(True)
        self._field_list.clear()
        if self.working is None:
            self._field_list.blockSignals(False)
            return
        placed = self.working.layout.placed_ids()
        for f in self.working.layout.fields:
            indicator = "●" if f.id in placed else "○"
            item = QListWidgetItem(f"{indicator} {f.name}")
            item.setData(Qt.ItemDataRole.UserRole, f.id)
            self._field_list.addItem(item)
        self._field_list.blockSignals(False)
        if keep_row and 0 <= prev_row < self._field_list.count():
            self._field_list.setCurrentRow(prev_row)

    # ═════════════════════════════════════════════════════════════════════════
    # Fields tab — selection helper
    # ═════════════════════════════════════════════════════════════════════════

    def _sel_field(self) -> FieldDef | None:
        """Return the currently selected FieldDef, or None if no selection."""
        i = self._field_list.currentRow()
        flds = self.working.layout.fields if self.working else []
        return flds[i] if 0 <= i < len(flds) else None

    # ═════════════════════════════════════════════════════════════════════════
    # Fields tab — form population
    # ═════════════════════════════════════════════════════════════════════════

    def _on_field_selected(self, row: int) -> None:
        """Populate per-field form on selection (under _loading guard)."""
        if self.working is None or row < 0:
            self._field_form_widget.setEnabled(False)
            self._field_preview_scene.clear()
            return
        flds = self.working.layout.fields
        if row >= len(flds):
            self._field_form_widget.setEnabled(False)
            self._field_preview_scene.clear()
            return
        self._loading = True
        try:
            f = flds[row]
            self._field_form_widget.setEnabled(True)
            self._fname_edit.setText(f.name)
            self._flabel_edit.setText(f.label)
            self._fkind_combo.setCurrentText(f.kind)
            self._ftext_edit.setPlainText(f.text)
            self._fcap_height.set_value_mm(f.cap_height_mm)
            self._fbold.setChecked(f.bold)
            self._fitalic.setChecked(f.italic)
            self._falign.setCurrentText(f.alignment)
            _update_swatch(self._ftext_color_swatch, f.text_color)
            _update_swatch(self._ffield_fill_swatch, f.fill_color)
            self._frev_rows.setValue(f.revision_rows)
            self._field_border_group.load(f.border)
            # Font combo
            idx = self._ffont_combo.findText(f.font_family)
            if idx >= 0:
                self._ffont_combo.setCurrentIndex(idx)
            else:
                self._ffont_combo.setCurrentText(f.font_family)
            # Thumbnail + image height
            self._update_field_thumb(f.image_data)
            self._fimg_height.set_value_mm(f.image_height_mm)
            # Apply kind-dependent widget visibility
            self._apply_kind_behavior(f.kind)
        finally:
            self._loading = False
        self._refresh_field_preview()

    def _apply_kind_behavior(self, kind: str) -> None:
        """Enable/disable form sections based on field kind."""
        is_rev = (kind == "revision_table")
        self._frev_rows.setEnabled(is_rev)
        self._ftext_edit.setEnabled(not is_rev)
        self._insert_btn.setEnabled(not is_rev)
        self._fimg_btn.setEnabled(not is_rev)
        self._fimg_clear.setEnabled(not is_rev)
        self._fimg_thumb.setEnabled(not is_rev)
        self._fimg_height.setEnabled(not is_rev)

    def _update_field_thumb(self, image_data: str) -> None:
        """Update the image thumbnail label from base64 image data."""
        if not image_data:
            self._fimg_thumb.clear()
            return
        from PyQt6.QtCore import QByteArray
        from PyQt6.QtGui import QPixmap
        try:
            raw = QByteArray.fromBase64(image_data.encode("ascii"))
            pm = QPixmap()
            if pm.loadFromData(raw) and not pm.isNull():
                self._fimg_thumb.setPixmap(
                    pm.scaled(120, 72, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation))
            else:
                self._fimg_thumb.clear()
        except Exception:
            self._fimg_thumb.clear()

    # ═════════════════════════════════════════════════════════════════════════
    # Fields tab — property mutations
    # ═════════════════════════════════════════════════════════════════════════

    def _update_roster_row(self) -> None:
        """Update only the currently selected roster item's text in-place.

        Uses a blockSignals guard so no currentRowChanged re-fires (no rebuild,
        no double preview solve, no form repopulate).
        """
        row = self._field_list.currentRow()
        if self.working is None or row < 0 or row >= self._field_list.count():
            return
        flds = self.working.layout.fields
        if row >= len(flds):
            return
        f = flds[row]
        placed = self.working.layout.placed_ids()
        indicator = "●" if f.id in placed else "○"
        item = self._field_list.item(row)
        if item is not None:
            self._field_list.blockSignals(True)
            item.setText(f"{indicator} {f.name}")
            self._field_list.blockSignals(False)

    def _field_prop(self, prop: str, value) -> None:
        """Snapshot + mutate a FieldDef property on the selected field.

        No-op when loading, no field selected, or value unchanged (prevents
        empty snapshots on Qt focus-churn re-emission).
        Updates the roster in-place (no full rebuild) to avoid re-entrant
        _on_field_selected → double preview solve + form repopulate.
        """
        f = self._sel_field()
        if self._loading or f is None or getattr(f, prop) == value:
            return
        self.push_snapshot()
        setattr(f, prop, value)
        self._update_roster_row()
        # Refresh image thumbnail when image_data changes (Clear button)
        if prop == "image_data":
            self._update_field_thumb(f.image_data)
        self.refresh_preview()
        self._refresh_field_preview()

    def _commit_field_text(self) -> None:
        """Commit QPlainTextEdit content to the selected field's text property."""
        f = self._sel_field()
        if self._loading or f is None:
            return
        new_text = self._ftext_edit.toPlainText()
        if f.text == new_text:
            return
        self.push_snapshot()
        f.text = new_text
        self._update_roster_row()
        self.refresh_preview()
        self._refresh_field_preview()

    def _commit_font_family(self) -> None:
        """Commit the current font combo text to the selected field's font_family.

        Called on activated (dropdown pick) and lineEdit().editingFinished (typed
        entry).  Using these two signals instead of currentTextChanged avoids
        per-keystroke snapshots while the user is typing.
        """
        self._field_prop("font_family", self._ffont_combo.currentText())

    def _on_kind_changed(self, kind: str) -> None:
        """Handle kind combo change: mutate kind + refresh widget visibility."""
        if self._loading:
            return
        self._field_prop("kind", kind)
        f = self._sel_field()
        if f is not None:
            self._apply_kind_behavior(f.kind)

    def _on_field_border_changed(self) -> None:
        """Called when any field border group widget changes."""
        if self._loading or self.working is None:
            return
        f = self._sel_field()
        if f is None:
            return
        # No-op guard: skip snapshot when group state matches the field's border.
        new_border = BorderStyle.from_dict(self._field_border_group.read())
        if new_border.to_dict() == f.border.to_dict():
            return
        self.push_snapshot()
        f.border = new_border
        self.refresh_preview()
        self._refresh_field_preview()

    def _pick_text_color(self) -> None:
        """Open a colour dialog for the selected field's text colour."""
        f = self._sel_field()
        if f is None:
            return
        cur = QColor(f.text_color or "#000000")
        c = QColorDialog.getColor(cur, self)
        if c.isValid():
            _update_swatch(self._ftext_color_swatch, c.name())
            self._field_prop("text_color", c.name())

    def _pick_field_fill(self) -> None:
        """Open color dialog for the field fill swatch."""
        if self._sel_field() is None:
            return
        cur = QColor(self._ffield_fill_swatch.property("_color") or "#ffffff")
        c = QColorDialog.getColor(cur, self)
        if c.isValid():
            _update_swatch(self._ffield_fill_swatch, c.name())
            self._field_prop("fill_color", c.name())

    def _pick_field_image(self) -> None:
        """Choose an image file and encode it as base64 PNG for the selected field."""
        f = self._sel_field()
        if f is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Field Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff)")
        if not path:
            return
        try:
            img = QImage(path)
            if img.isNull():
                with open(path, "rb") as fh:
                    raw = fh.read()
                data = base64.b64encode(raw).decode("ascii")
            else:
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buf, "PNG")
                data = base64.b64encode(bytes(buf.data())).decode("ascii")
        except Exception as exc:
            _log.warning("Failed to load field image: %s", exc)
            return
        self._field_prop("image_data", data)
        self._update_field_thumb(data)

    # ═════════════════════════════════════════════════════════════════════════
    # Fields tab — token insert
    # ═════════════════════════════════════════════════════════════════════════

    def _insert_token(self, key: str) -> None:
        """Insert @[key] at the cursor in _ftext_edit, then commit."""
        self._ftext_edit.insertPlainText(f"@[{key}]")
        self._commit_field_text()

    def _show_insert_menu(self) -> None:
        """Show a grouped menu for inserting @[Key] tokens at cursor."""
        menu = QMenu(self)

        # Auto section
        menu.addSection("Auto")
        for key in _AUTO_FIELD_KEYS:
            act = menu.addAction(key)
            act.triggered.connect(lambda checked=False, k=key: self._insert_token(k))

        # Sheet section
        menu.addSection("Sheet")
        for key in _SHEET_FIELD_KEYS:
            act = menu.addAction(key)
            act.triggered.connect(lambda checked=False, k=key: self._insert_token(k))

        # Project section
        menu.addSection("Project")
        proj_display = list(PROJECT_STD_KEYS.keys())
        for key in proj_display:
            act = menu.addAction(key)
            act.triggered.connect(lambda checked=False, k=key: self._insert_token(k))

        # Custom project keys
        custom = self._project_info.get("custom", [])
        if custom:
            menu.addSection("Custom")
            for entry in custom:
                k = entry.get("key", "")
                if k:
                    act = menu.addAction(k)
                    act.triggered.connect(
                        lambda checked=False, kk=k: self._insert_token(kk))

        sender = self.sender()
        if sender is not None:
            menu.exec(sender.mapToGlobal(sender.rect().bottomLeft()))
        else:
            menu.exec()

    # ═════════════════════════════════════════════════════════════════════════
    # Fields tab — roster actions
    # ═════════════════════════════════════════════════════════════════════════

    def _unique_field_name(self, base: str) -> str:
        """Return a name unique among current field names.

        Tries *base* first; on collision appends " 2", " 3", etc.

        Args:
            base: The desired base name (e.g. "New Field" or "Logo (copy)").

        Returns:
            A name that does not appear in the current layout's field name set.
        """
        existing = {f.name for f in self.working.layout.fields}
        if base not in existing:
            return base
        n = 2
        while f"{base} {n}" in existing:
            n += 1
        return f"{base} {n}"

    @staticmethod
    def _copy_base(name: str) -> str:
        """Strip any trailing ' (copy)' or ' (copy) N' suffix from *name*.

        Used by _duplicate_field so that duplicating a copy re-bases to the
        canonical "X (copy)" series rather than nesting suffixes.

        Args:
            name: A field name that may end with " (copy)" or " (copy) N".

        Returns:
            The name with the copy suffix removed, or *name* unchanged if no
            suffix is present.
        """
        return _re.sub(r" \(copy\)( \d+)?$", "", name)

    def _new_field(self) -> None:
        """Add a new unplaced field to the pool."""
        if self.working is None:
            return
        self.push_snapshot()
        name = self._unique_field_name("New Field")
        new_f = FieldDef(id=new_field_id(), name=name)
        self.working.layout.fields.append(new_f)
        self._rebuild_field_list()
        # Select the new field
        new_row = len(self.working.layout.fields) - 1
        self._field_list.setCurrentRow(new_row)
        self._arrange_tab.refresh(self.working.layout)   # new field → pool
        self.refresh_preview()

    def _duplicate_field(self) -> None:
        """Duplicate the selected field with a fresh id and a unique name."""
        f = self._sel_field()
        if self.working is None or f is None:
            return
        self.push_snapshot()
        new_f = FieldDef.from_dict(f.to_dict())
        new_f.id = new_field_id()
        new_f.name = self._unique_field_name(self._copy_base(f.name) + " (copy)")
        self.working.layout.fields.append(new_f)
        self._rebuild_field_list()
        new_row = len(self.working.layout.fields) - 1
        self._field_list.setCurrentRow(new_row)
        self._arrange_tab.refresh(self.working.layout)   # copy starts in pool
        self.refresh_preview()

    def _delete_field(self) -> None:
        """Delete the selected field, warning if it is placed on the strip."""
        f = self._sel_field()
        if self.working is None or f is None:
            return
        lay = self.working.layout
        if f.id in lay.placed_ids():
            resp = QMessageBox.question(
                self, "Delete Field",
                f"'{f.name}' is placed on the strip. Delete anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if resp != QMessageBox.StandardButton.Yes:
                return
        self.push_snapshot()
        unplace_field(lay, f.id)
        lay.fields = [fd for fd in lay.fields if fd.id != f.id]
        self._rebuild_field_list()
        self._field_form_widget.setEnabled(False)
        self._field_preview_scene.clear()
        self._arrange_tab.refresh(lay)     # pool/canvas drop the deleted field
        self.refresh_preview()

    # ═════════════════════════════════════════════════════════════════════════
    # Fields tab — single-field preview (DD-18)
    # ═════════════════════════════════════════════════════════════════════════

    def _refresh_field_preview(self) -> None:
        """Rebuild the single-field preview scene for the selected field."""
        self._field_preview_scene.clear()
        if self.working is None:
            return
        f = self._sel_field()
        if f is None:
            return
        try:
            lay = self.working.layout
            # Determine min height: use placed slot's value if placed, else TB_PREVIEW_MIN_MM
            placed_ids = lay.placed_ids()
            slot_min_h = TB_PREVIEW_MIN_MM
            if f.id in placed_ids:
                for row in lay.rows:
                    for slot in row:
                        if slot.field_id == f.id:
                            slot_min_h = slot.min_height_mm
                            break

            # Build a minimal one-row layout with just this field
            mini = TemplateLayout(
                margin_edge_mm=0.0,
                margin_strip_mm=0.0,
                strip_width_mm=lay.strip_width_mm,
                strip_border=BorderStyle(visible=False),
                fields=[f],
                rows=[[Slot(f.id, slot_min_h)]],
            )
            strip_w = lay.strip_width_mm
            preview_h = slot_min_h * 3
            solved = solve_layout(mini, strip_w, preview_h, _SAMPLE_VALUES)
            # The solver's height pass can grow the cell beyond the nominal
            # 3x-min preview strip (e.g. an explicit image_height_mm band
            # taller than a small slot min), and the renderer clips to the
            # strip — re-solve with the strip sized to the natural cell
            # height so the content is never chopped in the Fields preview
            # (holistic review 2026-08-04 finding 3).
            if solved.cell_rects and solved.cell_rects[0].height() > preview_h:
                preview_h = solved.cell_rects[0].height()
                solved = solve_layout(mini, strip_w, preview_h, _SAMPLE_VALUES)

            # White paper background so the renderer's fills/text read on
            # a white ground, not the dark app theme.
            if solved.cell_rects:
                cr = solved.cell_rects[0]
                bg = self._field_preview_scene.addRect(
                    cr.x(), cr.y(), cr.width(), cr.height())
                bg.setBrush(QBrush(QColor("#ffffff")))
                bg.setPen(QPen(QColor("#ffffff"), 0))
                bg.setZValue(-1)

            item = TitleBlockTemplateItem(solved, mini, _SAMPLE_VALUES)
            self._field_preview_scene.addItem(item)
            if solved.cell_rects:
                self._field_preview_view.fitInView(
                    solved.cell_rects[0], Qt.AspectRatioMode.KeepAspectRatio)
        except Exception as exc:
            _log.warning("Field preview error: %s", exc)

    # ═════════════════════════════════════════════════════════════════════════
    # Arrangements tab (DD-17) — provider, gesture hooks, placement props
    # ═════════════════════════════════════════════════════════════════════════

    def _arrange_provider(self) -> tuple:
        """Provider for the strip canvas: (layout, paper_w, paper_h, values).

        Falls back to an empty layout at ANSI D dims when no working template
        is loaded, so the canvas renders a graceful empty state.
        """
        if self.working is None:
            w, h = PAPER_SIZES.get("ANSI D", (863.6, 558.8))
            return TemplateLayout(), w, h, _SAMPLE_VALUES
        return (self.working.layout, *_template_page_mm(self.working),
                _SAMPLE_VALUES)

    def _after_arrange_gesture(self) -> None:
        """Refresh all dependents after a completed arrangement gesture.

        Connected to ``gestureCompleted`` (the snapshot was already pushed by
        ``gestureStarting``); also called directly by the placement-prop and
        Delete-unplace handlers after their own snapshot + mutation.
        """
        if self.working is None:
            return
        self._arrange_tab.refresh(self.working.layout)
        self._rebuild_field_list(keep_row=True)      # placed indicators
        self.refresh_preview()
        # Re-sync placement props: the refresh may have cleared a stale
        # selection (emitting selectionChanged("")), or the selected slot's
        # values may have changed — re-populate from the surviving selection.
        self._on_canvas_selection(self._arrange_tab.canvas.selected_field_id)

    def _unplace_from_canvas(self, field_id: str) -> None:
        """Unplace *field_id* on Delete-key request from the canvas.

        Idempotency guard: a stale request for an already-unplaced field
        (e.g. Delete re-fired on a stale selection) is a no-op — no snapshot.

        Args:
            field_id: The field to remove from the strip (stays in the pool).
        """
        if self.working is None:
            return
        if field_id not in self.working.layout.placed_ids():
            return
        self.push_snapshot()
        unplace_field(self.working.layout, field_id)
        self._after_arrange_gesture()

    def _selected_slot(self) -> Slot | None:
        """Return the Slot of the canvas's selected field, or None."""
        fid = self._arrange_tab.canvas.selected_field_id
        if not fid or self.working is None:
            return None
        for row in self.working.layout.rows:
            for s in row:
                if s.field_id == fid:
                    return s
        return None

    def _on_canvas_selection(self, _field_id: str) -> None:
        """Enable + populate the placement props for the selected slot.

        Runs under a save/restore ``_loading`` guard so populating the
        min-height edit and sizing combo never triggers the mutation slots
        (and never clobbers an outer ``_loading`` context).
        """
        slot = self._selected_slot()
        self._arrange_tab.props_group.setEnabled(slot is not None)
        if slot is None:
            return
        prev_loading = self._loading
        self._loading = True
        try:
            self._arrange_tab.min_height.set_value_mm(slot.min_height_mm)
            self._arrange_tab.sizing.setCurrentText(
                "Dynamic" if slot.sizing == "dynamic" else "Static")
        finally:
            self._loading = prev_loading

    def _on_placement_min_height(self, mm: float) -> None:
        """Snapshot + write the selected slot's min height (no-op guarded)."""
        slot = self._selected_slot()
        if self._loading or slot is None or slot.min_height_mm == mm:
            return
        self.push_snapshot()
        slot.min_height_mm = mm
        self._after_arrange_gesture()

    def _on_placement_sizing(self, text: str) -> None:
        """Snapshot + write the selected slot's sizing mode (no-op guarded)."""
        slot = self._selected_slot()
        val = text.lower()
        if self._loading or slot is None or slot.sizing == val:
            return
        self.push_snapshot()
        slot.sizing = val
        self._after_arrange_gesture()

    # ═════════════════════════════════════════════════════════════════════════
    # Tab change handler
    # ═════════════════════════════════════════════════════════════════════════

    def _on_tab_changed(self, index: int) -> None:
        """Re-fit the preview when the Overview tab (index 0) becomes visible.

        fitInView requires the QGraphicsView to have a realized viewport; it
        fails silently when called before the widget is shown. Calling it here
        (on tab switch) ensures the viewport geometry is valid.
        """
        if index == 0:
            items_rect = self._preview_scene.itemsBoundingRect()
            if not items_rect.isEmpty():
                self._preview_view.fitInView(
                    items_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _on_border_changed(self) -> None:
        """Called when any area/strip border group widget changes."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        variant = self.working.layout
        variant.area_border = BorderStyle.from_dict(self._area_border.read())
        variant.strip_border = BorderStyle.from_dict(self._strip_border.read())
        self.refresh_preview()
        self._refresh_arrange_canvas()   # strip border renders on the canvas

    def _refresh_arrange_canvas(self) -> None:
        """Re-solve the Arrangements canvas after a non-gesture edit.

        Strip geometry (margins / strip width) and frame borders change what
        the canvas renders but arrive from the Overview / border widgets —
        outside the canvas's own gesture path — so those handlers call this
        to keep the canvas current.  The ``getattr`` guard covers
        construction order: during ``_build_ui`` the border/margin signals
        are wired before ``_arrange_tab`` exists.
        """
        tab = getattr(self, "_arrange_tab", None)
        if tab is not None and self.working is not None:
            tab.refresh(self.working.layout)

    def _on_orientation_toggled(self, checked: bool) -> None:
        """Called when either orientation radio button's toggled signal fires.

        Both Landscape and Portrait radios connect here.  Only acts on the
        ``checked=True`` transition to avoid double-fire (each toggle emits
        once for the button becoming checked and once for the other becoming
        unchecked).
        """
        if self._loading or self.working is None:
            return
        # Only act on the "becoming checked" transition to avoid double-fire
        if not checked:
            return
        orientation = "landscape" if self._orient_landscape.isChecked() else "portrait"
        self.set_orientation(orientation)

    # ═════════════════════════════════════════════════════════════════════════
    # Public form slots (API; tested directly)
    # ═════════════════════════════════════════════════════════════════════════

    def set_name(self, text: str) -> None:
        """Snapshot + set the template name (every user edit is undoable)."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        self.working.name = text
        # Update list widget label with the full display_name ("Name (SIZE)" or
        # "Name (SIZE, Portrait)") so the suffix is always current.
        uid = self.working.uuid
        for i in range(self._template_list.count()):
            if self._template_list.item(i).data(Qt.ItemDataRole.UserRole) == uid:
                self._template_list.item(i).setText(self.working.display_name)
                break

    def set_paper_size(self, size: str) -> None:
        """Snapshot + set template paper_size; re-solves preview at new dims.

        Args:
            size: A key in PAPER_SIZES (e.g. ``"ANSI D"``).  Unknown keys are
                accepted and will produce a fallback page size in the preview.
        """
        if self._loading or self.working is None:
            return
        if self.working.paper_size == size:
            return
        self.push_snapshot()
        self.working.paper_size = size
        self.refresh_preview()

    def set_orientation(self, orientation: str) -> None:
        """Snapshot + set template orientation; re-solves preview at swapped dims.

        Args:
            orientation: ``"landscape"`` or ``"portrait"``.
        """
        if self._loading or self.working is None:
            return
        if self.working.orientation == orientation:
            return
        self.push_snapshot()
        self.working.orientation = orientation
        self.refresh_preview()

    def set_margin_edge(self, mm: float) -> None:
        """Snapshot + mutate margin_edge_mm on the active layout."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        self.working.layout.margin_edge_mm = mm
        self.refresh_preview()
        self._refresh_arrange_canvas()   # strip rect depends on edge margin

    def set_margin_strip(self, mm: float) -> None:
        """Snapshot + mutate margin_strip_mm on the active layout."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        self.working.layout.margin_strip_mm = mm
        self.refresh_preview()
        self._refresh_arrange_canvas()

    def set_strip_width(self, mm: float) -> None:
        """Snapshot + mutate strip_width_mm on the active layout."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        self.working.layout.strip_width_mm = mm
        self.refresh_preview()
        self._refresh_arrange_canvas()

    def set_border_prop(self, which: str, prop: str, value) -> None:
        """Set a border property on the active layout's area or strip border.

        Args:
            which: ``"area"`` or ``"strip"``.
            prop: BorderStyle attribute name.
            value: New value.
        """
        if self.working is None:
            return
        self.push_snapshot()
        border = (self.working.layout.area_border if which == "area"
                  else self.working.layout.strip_border)
        setattr(border, prop, value)
        self.refresh_preview()

    # ═════════════════════════════════════════════════════════════════════════
    # Save button / dialog close
    # ═════════════════════════════════════════════════════════════════════════

    def _do_save(self) -> bool:
        """Shared Save core: library write + project-result/live refresh hooks.

        If use_for_project() was called before Save, refresh project_template_result
        from the (now stamped + saved) working copy so that any post-Use edits
        and the fresh modified date are captured. templateSaved is emitted AFTER
        that refresh so listeners observe the final result state.
        """
        if self.working is None or not self.save_button.isEnabled():
            return False
        if not self.save():
            return False
        if self._use_requested or self.project_template_result is not None:
            self.project_template_result = self.working.copy()
            # Mark the result as saved: a saved use-intent survives a later
            # Close/reject (holistic review 2026-08-04 finding 1).
            self.result_saved = True
        self.templateSaved.emit(self.working.copy())
        return True

    def _on_save_clicked(self) -> None:
        """Save mid-session: library write + live refresh, dialog stays open."""
        self._do_save()

    def _on_save_close_clicked(self) -> None:
        """Save then accept (the pre-2026-08-04 Save behavior)."""
        if self._do_save():
            self.accept()
