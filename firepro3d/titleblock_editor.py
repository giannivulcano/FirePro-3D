"""Title block template editor — form panel + live preview.

Governing spec: docs/specs/titleblock-template-system.md §Editor. The preview
hosts the SAME renderer used on sheets (one render path).
"""
from __future__ import annotations

import base64
import copy
import datetime
import logging
import uuid as _uuid

from PyQt6.QtCore import Qt, QBuffer, QIODevice
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGraphicsScene, QGraphicsView,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPushButton, QSizePolicy, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QBrush, QColor, QImage, QKeySequence, QStandardItemModel

from .titleblock_template import (
    TitleBlockTemplate, TemplateLayout, TemplateVariant, CellSpec, BorderStyle,
    CELL_KINDS,
    make_default_template, load_library, save_to_library, delete_from_library,
    solve_layout, validate,
)
from .paper_space import PAPER_SIZES, TitleBlockTemplateItem, PROJECT_STD_KEYS
from .dimension_edit import DimensionEdit
from .scale_manager import ScaleManager

# Module-level ScaleManager used as dimension parser throughout the editor.
# ScaleManager() is standalone (pixels_per_mm=1 → 1 px = 1 mm, display_unit=mm),
# so bare numbers are interpreted as mm, but "1 in" / "1\"" / "1 ft" etc. also work.
_sm = ScaleManager()

_log = logging.getLogger("FirePro3D")

# Standard project info keys — imported from paper_space.PROJECT_STD_KEYS so that
# picker display names always match what build_field_values resolves.
# Do NOT add a local copy; edit paper_space.PROJECT_STD_KEYS to add new keys.

# Sample values used in the preview (no build_field_values needed)
_SAMPLE_VALUES = {
    "Company": "Vulcano Fire Design Inc.", "Project": "Sample Project",
    "Address": "123 Example St", "Title": "Level 1 — Sprinkler Plan",
    "Scale": "1:100", "Date": "2026-07-21", "Drawn By": "GV",
    "Checked By": "—", "Drawing No": "FP-101", "Rev": "0",
    "__revisions__": [{"no": "1", "description": "Issued for permit",
                       "date": "07-21"}],
}

# Field key groups for the cell form picker
_AUTO_FIELD_KEYS = ["Scale", "Date (auto)", "Sheet No"]
_SHEET_FIELD_KEYS = ["Title", "Drawing No", "Rev", "Date"]


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
            f"background-color: {c.name()}; border: 1px solid #888;")
    else:
        btn.setStyleSheet("background-color: transparent; border: 1px solid #888;")
    btn.setProperty("_color", color)


# ─────────────────────────────────────────────────────────────────────────────
# Border sub-group widget
# ─────────────────────────────────────────────────────────────────────────────

class _BorderGroup(QGroupBox):
    """Reusable widget for editing a BorderStyle (visible, width, color, corner, fillet)."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._visible = QCheckBox()
        form.addRow("Visible:", self._visible)

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
        self._fillet.setEnabled(self._corner.currentText() == "Fillet")

    def load(self, style) -> None:
        """Populate widgets from a BorderStyle (without triggering signals)."""
        self._visible.setChecked(style.visible)
        self._width.set_value_mm(style.width_mm)
        _update_swatch(self._color_btn, style.color)
        self._corner.setCurrentText(
            "Fillet" if style.corner == "fillet" else "Sharp")
        self._fillet.set_value_mm(style.fillet_radius_mm)
        self._fillet.setEnabled(style.corner == "fillet")

    def read(self) -> dict:
        """Return a dict suitable for BorderStyle.from_dict()."""
        return {
            "visible": self._visible.isChecked(),
            "width_mm": self._width.value_mm(),
            "color": self._color_btn.property("_color") or "#000000",
            "corner": "fillet" if self._corner.currentText() == "Fillet" else "sharp",
            "fillet_radius_mm": self._fillet.value_mm(),
        }




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
    """

    def __init__(self, project_template: TitleBlockTemplate | None = None,
                 parent: QWidget | None = None,
                 project_info: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Title Block Template Editor")
        self.setMinimumSize(1000, 700)

        # ── Public state ──────────────────────────────────────────────────
        self.working: TitleBlockTemplate | None = None
        self.project_template_result: TitleBlockTemplate | None = None
        self._project_info = project_info or {}
        self._use_requested = False   # set by use_for_project(); read by _on_save_clicked

        # ── Snapshot undo/redo stacks ─────────────────────────────────────
        # Each entry is a dict snapshot from TitleBlockTemplate.to_dict()
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []

        # ── Loading guard (suppress snapshot pushes during UI population) ─
        self._loading = False

        # ── Active paper size for the current session ──────────────────────
        self._active_size = "ANSI D"

        # ── Preview scene (reused across refresh_preview calls) ────────────
        self._preview_scene = QGraphicsScene(self)

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

        # ── Centre: form ──────────────────────────────────────────────────
        centre = QVBoxLayout()
        centre.setSpacing(6)

        # Template name row
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Template name")
        self._name_edit.editingFinished.connect(
            lambda: self.set_name(self._name_edit.text()))
        name_row.addWidget(self._name_edit, stretch=1)
        centre.addLayout(name_row)

        # Variant tab widget (one tab per paper size + "+" tab)
        self._variant_tabs = QTabWidget()
        self._variant_tabs.currentChanged.connect(self._on_variant_tab_changed)
        centre.addWidget(self._variant_tabs, stretch=0)

        # ── Margins group ─────────────────────────────────────────────────
        margins_group = QGroupBox("Margins")
        margins_form = QFormLayout(margins_group)
        margins_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._edge_edit = DimensionEdit(None, initial_mm=10.0,
                                        parser=_sm.parse_dimension, minimum=0.0)
        self._edge_edit.valueChanged.connect(self.set_margin_edge)
        margins_form.addRow("Edge margin (mm):", self._edge_edit)

        self._strip_margin_edit = DimensionEdit(None, initial_mm=5.0,
                                                parser=_sm.parse_dimension, minimum=0.0)
        self._strip_margin_edit.valueChanged.connect(self.set_margin_strip)
        margins_form.addRow("Strip gap (mm):", self._strip_margin_edit)

        self._strip_width_edit = DimensionEdit(None, initial_mm=90.0,
                                               parser=_sm.parse_dimension, minimum=0.0)
        self._strip_width_edit.valueChanged.connect(self.set_strip_width)
        margins_form.addRow("Strip width (mm):", self._strip_width_edit)

        centre.addWidget(margins_group)

        # ── Border groups ─────────────────────────────────────────────────
        borders_row = QHBoxLayout()
        self._area_border = _BorderGroup("Drawing Area Border")
        self._strip_border = _BorderGroup("Info Strip Border")
        borders_row.addWidget(self._area_border)
        borders_row.addWidget(self._strip_border)
        centre.addLayout(borders_row)

        # Wire border change signals
        for widget in (self._area_border, self._strip_border):
            widget._visible.toggled.connect(self._on_border_changed)
            widget._width.valueChanged.connect(lambda _: self._on_border_changed())
            widget._color_btn.clicked.connect(self._on_border_changed)
            widget._corner.currentIndexChanged.connect(
                lambda _: self._on_border_changed())
            widget._fillet.valueChanged.connect(lambda _: self._on_border_changed())

        # ── Cell list + per-cell form ─────────────────────────────────────
        cells_split = QHBoxLayout()

        # Left side: cell list
        cell_left = QVBoxLayout()
        cell_left.addWidget(QLabel("Cells (top → bottom):"))
        self._cell_list = QListWidget()
        self._cell_list.setMinimumHeight(180)
        self._cell_list.currentRowChanged.connect(self._on_cell_selected)
        cell_left.addWidget(self._cell_list, stretch=1)

        cell_btns = QHBoxLayout()
        self._cell_up_btn = QPushButton("▲")
        self._cell_up_btn.setFixedWidth(30)
        self._cell_up_btn.clicked.connect(self._move_cell_up)
        self._cell_dn_btn = QPushButton("▼")
        self._cell_dn_btn.setFixedWidth(30)
        self._cell_dn_btn.clicked.connect(self._move_cell_down)
        add_cell_btn = QPushButton("Add")
        add_cell_btn.clicked.connect(self._show_add_cell_menu)
        rm_cell_btn = QPushButton("Remove")
        rm_cell_btn.clicked.connect(self._remove_selected_cell)
        cell_btns.addWidget(self._cell_up_btn)
        cell_btns.addWidget(self._cell_dn_btn)
        cell_btns.addWidget(add_cell_btn)
        cell_btns.addWidget(rm_cell_btn)
        cell_left.addLayout(cell_btns)
        cells_split.addLayout(cell_left)

        # Right side: per-cell form
        self._cell_form_widget = QWidget()
        self._cell_form_widget.setMinimumWidth(260)
        cell_form = QFormLayout(self._cell_form_widget)
        cell_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._cell_kind_combo = QComboBox()
        self._cell_kind_combo.addItems(list(CELL_KINDS))
        self._cell_kind_combo.currentTextChanged.connect(
            lambda t: self._cell_form_prop_changed("kind", t))
        cell_form.addRow("Kind:", self._cell_kind_combo)

        self._cell_field_key = QComboBox()
        self._cell_field_key.setEditable(True)
        self._populate_field_key_combo()
        self._cell_field_key.currentTextChanged.connect(
            lambda t: self._cell_form_prop_changed("field_key", t))
        cell_form.addRow("Field key:", self._cell_field_key)

        self._cell_label_edit = QLineEdit()
        self._cell_label_edit.editingFinished.connect(
            lambda: self._cell_form_prop_changed(
                "label", self._cell_label_edit.text()))
        cell_form.addRow("Label:", self._cell_label_edit)

        self._cell_static_text = QLineEdit()
        self._cell_static_text.editingFinished.connect(
            lambda: self._cell_form_prop_changed(
                "static_text", self._cell_static_text.text()))
        cell_form.addRow("Static text:", self._cell_static_text)

        self._cell_min_height = DimensionEdit(None, initial_mm=10.0,
                                              parser=_sm.parse_dimension, minimum=0.0)
        self._cell_min_height.valueChanged.connect(
            lambda v: self._cell_form_prop_changed("min_height_mm", v))
        cell_form.addRow("Min height (mm):", self._cell_min_height)

        self._cell_cap_height = DimensionEdit(None, initial_mm=3.0,
                                              parser=_sm.parse_dimension, minimum=0.0)
        self._cell_cap_height.valueChanged.connect(
            lambda v: self._cell_form_prop_changed("cap_height_mm", v))
        cell_form.addRow("Cap height (mm):", self._cell_cap_height)

        self._cell_pair = QCheckBox()
        self._cell_pair.toggled.connect(
            lambda b: self._cell_form_prop_changed("pair_with_next", b))
        cell_form.addRow("Pair with next:", self._cell_pair)

        self._cell_bold = QCheckBox()
        self._cell_bold.toggled.connect(
            lambda b: self._cell_form_prop_changed("bold", b))
        cell_form.addRow("Bold:", self._cell_bold)

        self._cell_italic = QCheckBox()
        self._cell_italic.toggled.connect(
            lambda b: self._cell_form_prop_changed("italic", b))
        cell_form.addRow("Italic:", self._cell_italic)

        self._cell_align = QComboBox()
        self._cell_align.addItems(["left", "center", "right"])
        self._cell_align.currentTextChanged.connect(
            lambda t: self._cell_form_prop_changed("alignment", t))
        cell_form.addRow("Alignment:", self._cell_align)

        fill_row = QHBoxLayout()
        self._cell_fill_swatch = _make_swatch("", self)
        fill_row.addWidget(self._cell_fill_swatch)
        self._cell_fill_swatch.clicked.connect(self._pick_cell_fill)
        fill_clear_btn = QPushButton("None")
        fill_clear_btn.setFixedWidth(40)
        fill_clear_btn.clicked.connect(lambda: self._cell_form_prop_changed(
            "fill_color", ""))
        fill_row.addWidget(fill_clear_btn)
        fill_row.addStretch()
        cell_form.addRow("Fill:", fill_row)

        self._cell_rev_rows = QSpinBox()
        self._cell_rev_rows.setRange(1, 10)
        self._cell_rev_rows.valueChanged.connect(
            lambda v: self._cell_form_prop_changed("revision_rows", v))
        cell_form.addRow("Revision rows:", self._cell_rev_rows)

        self._cell_border_group = _BorderGroup("Cell Border")
        cell_form.addRow(self._cell_border_group)

        # Wire cell border group signals (mirror area/strip border wiring)
        self._cell_border_group._visible.toggled.connect(
            self._on_cell_border_changed)
        self._cell_border_group._width.valueChanged.connect(
            lambda _: self._on_cell_border_changed())
        self._cell_border_group._color_btn.clicked.connect(
            self._on_cell_border_changed)
        self._cell_border_group._corner.currentIndexChanged.connect(
            lambda _: self._on_cell_border_changed())
        self._cell_border_group._fillet.valueChanged.connect(
            lambda _: self._on_cell_border_changed())

        self._cell_logo_btn = QPushButton("Choose logo image…")
        self._cell_logo_btn.clicked.connect(self._pick_logo)
        cell_form.addRow("Logo:", self._cell_logo_btn)

        cells_split.addWidget(self._cell_form_widget)
        centre.addLayout(cells_split, stretch=1)

        root.addLayout(centre, stretch=1)

        # ── Right panel: preview + warnings + buttons ─────────────────────
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(QLabel("Preview:"))

        self._preview_view = QGraphicsView(self._preview_scene)
        self._preview_view.setMinimumWidth(300)
        self._preview_view.setRenderHint(
            self._preview_view.renderHints().__class__.Antialiasing)
        self._preview_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right.addWidget(self._preview_view, stretch=1)

        self._warning_label = QLabel()
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #b8620a; font-size: 11px;")
        self._warning_label.setVisible(False)
        right.addWidget(self._warning_label)

        self._btn_box = QDialogButtonBox()
        self.save_button = self._btn_box.addButton(
            "Save", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save_button.setEnabled(False)   # disabled until a valid template is loaded
        self.save_button.clicked.connect(self._on_save_clicked)
        cancel_btn = self._btn_box.addButton(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.clicked.connect(self.reject)
        right.addWidget(self._btn_box)

        root.addLayout(right)

    # ═════════════════════════════════════════════════════════════════════════
    # Library management
    # ═════════════════════════════════════════════════════════════════════════

    def _reload_library(self) -> None:
        """Reload the library list widget from disk."""
        self._loading = True
        self._template_list.clear()
        for tmpl in load_library():
            item = QListWidgetItem(tmpl.name)
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
        # Sync active size to template's paper_size
        self._active_size = self.working.paper_size
        self._populate_form()

    def new_template(self) -> None:
        """Create a fresh template in the working copy (not yet saved)."""
        tmpl = make_default_template()
        tmpl.name = "New Template"
        self.working = tmpl
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._active_size = self.working.paper_size
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
        """Push the current working state onto the undo stack; clears redo."""
        if self.working is None:
            return
        self._undo_stack.append(copy.deepcopy(self.working.to_dict()))
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
        """Rebuild the preview scene using the current working variant."""
        self._preview_scene.clear()
        enabled = False
        warnings: list[str] = []

        if self.working is None:
            self._warning_label.setVisible(False)
            self.save_button.setEnabled(False)
            return

        # Single-size model: use the template's layout and paper_size
        variant = self.working.layout
        size = self.working.paper_size
        paper_w, paper_h = PAPER_SIZES.get(size, (297.0, 420.0))

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
        self._preview_view.fitInView(
            self._preview_scene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio)

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
            self._rebuild_variant_tabs()
            self._cell_list.clear()
            return

        self._name_edit.setText(self.working.name)
        self._rebuild_variant_tabs()
        self._populate_variant_fields()
        self._rebuild_cell_list()
        # Deselect cell form when repopulating
        self._cell_form_widget.setEnabled(False)

    def _rebuild_variant_tabs(self) -> None:
        """Rebuild variant tabs from self.working.variants."""
        self._variant_tabs.blockSignals(True)
        while self._variant_tabs.count():
            self._variant_tabs.removeTab(0)
        if self.working is None:
            self._variant_tabs.blockSignals(False)
            return
        # Add one tab per existing variant
        for size in self.working.variants:
            tab = QWidget()
            self._variant_tabs.addTab(tab, size)
        # "+" tab for adding new sizes
        self._variant_tabs.addTab(QWidget(), "+")
        # Restore active tab
        for i in range(self._variant_tabs.count() - 1):
            if self._variant_tabs.tabText(i) == self._active_size:
                self._variant_tabs.setCurrentIndex(i)
                break
        self._variant_tabs.blockSignals(False)

    def _on_variant_tab_changed(self, index: int) -> None:
        if self._loading or self.working is None:
            return
        tab_text = self._variant_tabs.tabText(index)
        if tab_text == "+":
            # Show menu of available sizes to add
            self._show_add_size_menu()
            # Revert to previous tab
            for i in range(self._variant_tabs.count() - 1):
                if self._variant_tabs.tabText(i) == self._active_size:
                    self._variant_tabs.blockSignals(True)
                    self._variant_tabs.setCurrentIndex(i)
                    self._variant_tabs.blockSignals(False)
                    break
        else:
            self._active_size = tab_text
            self._populate_variant_fields()
            self._rebuild_cell_list()
            self.refresh_preview()

    def _show_add_size_menu(self) -> None:
        existing = set(self.working.variants.keys()) if self.working else set()
        available = [s for s in PAPER_SIZES if s not in existing]
        if not available:
            return
        menu = QMenu(self)
        for size in available:
            menu.addAction(size, lambda s=size: self.add_variant(s))
        menu.exec(self._variant_tabs.mapToGlobal(
            self._variant_tabs.rect().bottomLeft()))

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

    def _rebuild_cell_list(self) -> None:
        """Rebuild cell list QListWidget from active layout's cells."""
        self._cell_list.blockSignals(True)
        self._cell_list.clear()
        if self.working is None:
            self._cell_list.blockSignals(False)
            return
        variant = self.working.layout
        for cell in variant.cells:
            key = cell.field_key or cell.label or cell.static_text or cell.kind
            label = f"{cell.kind}: {key}"
            self._cell_list.addItem(label)
        self._cell_list.blockSignals(False)

    # ═════════════════════════════════════════════════════════════════════════
    # Cell form (per-cell editing)
    # ═════════════════════════════════════════════════════════════════════════

    def _on_cell_selected(self, row: int) -> None:
        """Populate per-cell form without pushing a snapshot (_loading guard)."""
        if self.working is None or row < 0:
            self._cell_form_widget.setEnabled(False)
            return
        variant = self.working.layout
        if row >= len(variant.cells):
            self._cell_form_widget.setEnabled(False)
            return
        self._loading = True
        try:
            cell = variant.cells[row]
            self._cell_form_widget.setEnabled(True)
            self._cell_kind_combo.setCurrentText(cell.kind)
            self._cell_field_key.setCurrentText(cell.field_key)
            self._cell_label_edit.setText(cell.label)
            self._cell_static_text.setText(cell.static_text)
            self._cell_min_height.set_value_mm(cell.min_height_mm)
            self._cell_cap_height.set_value_mm(cell.cap_height_mm)
            self._cell_pair.setChecked(cell.pair_with_next)
            self._cell_bold.setChecked(cell.bold)
            self._cell_italic.setChecked(cell.italic)
            self._cell_align.setCurrentText(cell.alignment)
            _update_swatch(self._cell_fill_swatch, cell.fill_color)
            self._cell_rev_rows.setValue(cell.revision_rows)
            self._cell_border_group.load(cell.border)
            # Show/hide revision rows only for revision_table kind
            rev_visible = cell.kind == "revision_table"
            self._cell_rev_rows.setVisible(rev_visible)
        finally:
            self._loading = False

    def _cell_form_prop_changed(self, prop: str, value) -> None:
        """Called by cell form widgets; pushes snapshot then mutates."""
        if self._loading:
            return
        row = self._cell_list.currentRow()
        if row < 0:
            return
        self.set_cell_prop(row, prop, value)
        # Update the list label to reflect kind/key change
        self._loading = True
        self._rebuild_cell_list()
        self._cell_list.setCurrentRow(row)
        self._loading = False

    def _populate_field_key_combo(self) -> None:
        """Fill the field_key combo with auto / sheet / project keys.

        "Sheet No" is visible but disabled (auto-computed; cannot be set by user).
        """
        self._cell_field_key.clear()
        self._cell_field_key.addItems(_AUTO_FIELD_KEYS)
        # Disable "Sheet No" (index = _AUTO_FIELD_KEYS.index("Sheet No"))
        sheet_no_idx = _AUTO_FIELD_KEYS.index("Sheet No")
        model = self._cell_field_key.model()
        if isinstance(model, QStandardItemModel):
            item = model.item(sheet_no_idx)
            if item is not None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled
                              & ~Qt.ItemFlag.ItemIsSelectable)
        self._cell_field_key.insertSeparator(len(_AUTO_FIELD_KEYS))
        self._cell_field_key.addItems(_SHEET_FIELD_KEYS)
        self._cell_field_key.insertSeparator(
            len(_AUTO_FIELD_KEYS) + 1 + len(_SHEET_FIELD_KEYS))
        # Standard project info display names (PROJECT_STD_KEYS keys = display names).
        proj_display = list(PROJECT_STD_KEYS.keys())
        self._cell_field_key.addItems(proj_display)
        # Custom keys from project_info
        custom = self._project_info.get("custom", [])
        if custom:
            self._cell_field_key.insertSeparator(
                len(_AUTO_FIELD_KEYS) + 1 + len(_SHEET_FIELD_KEYS) + 1
                + len(proj_display))
            for entry in custom:
                k = entry.get("key", "")
                if k:
                    self._cell_field_key.addItem(k)

    def _pick_cell_fill(self) -> None:
        row = self._cell_list.currentRow()
        if row < 0:
            return
        cur = QColor(self._cell_fill_swatch.property("_color") or "#ffffff")
        c = QColorDialog.getColor(cur, self)
        if c.isValid():
            self._cell_form_prop_changed("fill_color", c.name())

    def _pick_logo(self) -> None:
        row = self._cell_list.currentRow()
        if row < 0:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Logo Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff)")
        if path:
            self.set_cell_logo_from_file(row, path)

    def _show_add_cell_menu(self) -> None:
        menu = QMenu(self)
        for kind in CELL_KINDS:
            menu.addAction(kind, lambda k=kind: self.add_cell(k))
        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def _move_cell_up(self) -> None:
        row = self._cell_list.currentRow()
        if row > 0:
            self.move_cell(row, row - 1)
            self._cell_list.setCurrentRow(row - 1)

    def _move_cell_down(self) -> None:
        row = self._cell_list.currentRow()
        if self.working is None:
            return
        variant = self.working.layout
        if variant and row < len(variant.cells) - 1:
            self.move_cell(row, row + 1)
            self._cell_list.setCurrentRow(row + 1)

    def _on_border_changed(self) -> None:
        """Called when any area/strip border group widget changes."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        variant = self.working.layout
        variant.area_border = BorderStyle.from_dict(self._area_border.read())
        variant.strip_border = BorderStyle.from_dict(self._strip_border.read())
        self.refresh_preview()

    def _on_cell_border_changed(self) -> None:
        """Called when any cell border group widget changes; applies to selected cell."""
        if self._loading or self.working is None:
            return
        row = self._cell_list.currentRow()
        if row < 0:
            return
        variant = self.working.layout
        if row >= len(variant.cells):
            return
        self.push_snapshot()
        variant.cells[row].border = BorderStyle.from_dict(
            self._cell_border_group.read())
        self.refresh_preview()

    # ═════════════════════════════════════════════════════════════════════════
    # Public form slots (Pass-b API; tested directly)
    # ═════════════════════════════════════════════════════════════════════════

    def set_name(self, text: str) -> None:
        """Snapshot + set the template name (every user edit is undoable)."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        self.working.name = text
        # Update list widget label
        uid = self.working.uuid
        for i in range(self._template_list.count()):
            if self._template_list.item(i).data(Qt.ItemDataRole.UserRole) == uid:
                self._template_list.item(i).setText(text)
                break

    def set_margin_edge(self, mm: float) -> None:
        """Snapshot + mutate margin_edge_mm on the active layout."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        self.working.layout.margin_edge_mm = mm
        self.refresh_preview()

    def set_margin_strip(self, mm: float) -> None:
        """Snapshot + mutate margin_strip_mm on the active layout."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        self.working.layout.margin_strip_mm = mm
        self.refresh_preview()

    def set_strip_width(self, mm: float) -> None:
        """Snapshot + mutate strip_width_mm on the active layout."""
        if self._loading or self.working is None:
            return
        self.push_snapshot()
        self.working.layout.strip_width_mm = mm
        self.refresh_preview()

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

    # ── Cell operations ───────────────────────────────────────────────────

    def _active_variant(self) -> TemplateLayout | None:
        if self.working is None:
            return None
        # Single-size model: always return the one layout
        return self.working.layout

    def add_cell(self, kind: str) -> None:
        """Append a new cell of *kind* to the active variant."""
        if self.working is None:
            return
        variant = self._active_variant()
        if variant is None:
            return
        self.push_snapshot()
        cell = CellSpec(kind=kind)
        variant.cells.append(cell)
        self._rebuild_cell_list()
        self.refresh_preview()

    def remove_cell(self, i: int) -> None:
        """Remove cell at index *i* from the active variant."""
        if self.working is None:
            return
        variant = self._active_variant()
        if variant is None or i < 0 or i >= len(variant.cells):
            return
        self.push_snapshot()
        variant.cells.pop(i)
        self._rebuild_cell_list()
        self.refresh_preview()

    def move_cell(self, i: int, j: int) -> None:
        """Move cell at index *i* to index *j* in the active variant."""
        if self.working is None:
            return
        variant = self._active_variant()
        if variant is None:
            return
        cells = variant.cells
        if i < 0 or i >= len(cells) or j < 0 or j >= len(cells):
            return
        self.push_snapshot()
        cell = cells.pop(i)
        cells.insert(j, cell)
        self._rebuild_cell_list()
        self.refresh_preview()

    def set_cell_prop(self, i: int, prop: str, value) -> None:
        """Snapshot + set a CellSpec attribute at index *i* in the active variant."""
        if self.working is None:
            return
        variant = self._active_variant()
        if variant is None or i < 0 or i >= len(variant.cells):
            return
        self.push_snapshot()
        setattr(variant.cells[i], prop, value)
        self.refresh_preview()

    def set_cell_border_prop(self, i: int, prop: str, value) -> None:
        """Snapshot + set a BorderStyle attribute on cell *i*'s border."""
        if self.working is None:
            return
        variant = self._active_variant()
        if variant is None or i < 0 or i >= len(variant.cells):
            return
        self.push_snapshot()
        setattr(variant.cells[i].border, prop, value)
        self.refresh_preview()

    def set_cell_logo_from_file(self, i: int, path: str) -> None:
        """Read *path*, encode as base64 PNG, store in cell[i].logo_data."""
        if self.working is None:
            return
        variant = self._active_variant()
        if variant is None or i < 0 or i >= len(variant.cells):
            return
        self.push_snapshot()
        try:
            img = QImage(path)
            if img.isNull():
                # Try raw bytes
                with open(path, "rb") as fh:
                    raw = fh.read()
                variant.cells[i].logo_data = base64.b64encode(raw).decode("ascii")
            else:
                # Convert to PNG via QBuffer
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buf, "PNG")
                variant.cells[i].logo_data = base64.b64encode(
                    bytes(buf.data())).decode("ascii")
        except Exception as exc:
            _log.warning("Failed to load logo: %s", exc)
        self.refresh_preview()

    # ── Variant management ────────────────────────────────────────────────

    def add_variant(self, size: str) -> None:
        """Add a variant for *size*, copying cells from the active variant."""
        if self.working is None:
            return
        if size in self.working.variants:
            return
        self.push_snapshot()
        # Deep-copy cells via dict round-trip so they're independent
        src = self._active_variant()
        if src is not None:
            d = src.to_dict()
            d["paper_size"] = size
            new_variant = TemplateVariant.from_dict(d)
        else:
            new_variant = TemplateVariant(paper_size=size)
        self.working.variants[size] = new_variant
        self._loading = True
        self._rebuild_variant_tabs()
        self._loading = False
        self.refresh_preview()

    def remove_variant(self, size: str) -> None:
        """Remove the variant for *size* (no-op if it's the last variant)."""
        if self.working is None:
            return
        if size not in self.working.variants:
            return
        if len(self.working.variants) <= 1:
            return
        self.push_snapshot()
        del self.working.variants[size]
        if self._active_size == size:
            self._active_size = next(iter(self.working.variants))
        self._loading = True
        self._rebuild_variant_tabs()
        self._loading = False
        self.refresh_preview()

    def set_active_size(self, size: str) -> None:
        """Switch the active paper size for editing."""
        if self.working and size in self.working.variants:
            self._active_size = size
            self._loading = True
            self._populate_variant_fields()
            self._rebuild_cell_list()
            self._loading = False
            self.refresh_preview()

    # ═════════════════════════════════════════════════════════════════════════
    # Save button / dialog close
    # ═════════════════════════════════════════════════════════════════════════

    def _on_save_clicked(self) -> None:
        """Save and accept only when working is set and save succeeds.

        If use_for_project() was called before Save, refresh project_template_result
        from the (now stamped + saved) working copy so that any post-Use edits
        and the fresh modified date are captured.
        """
        if self.working is None or not self.save_button.isEnabled():
            return
        if self.save():
            if self._use_requested or self.project_template_result is not None:
                self.project_template_result = self.working.copy()
            self.accept()

    def _remove_selected_cell(self) -> None:
        row = self._cell_list.currentRow()
        if row >= 0:
            self.remove_cell(row)
