"""
import_dialog.py
================
Unified underlay import dialog for FireFlow Pro.

Handles both PDF and DXF underlays from a single dialog, replacing the
separate ImportDialog (PDF) and DxfImportDialog classes.  A QStackedWidget
swaps the type-specific options panel when the user changes file type.

Usage
-----
    from import_dialog import UnifiedImportDialog

    dlg = UnifiedImportDialog(parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        opts = dlg.get_options()
        if opts["type"] == "pdf":
            scene.import_pdf(opts["file"], dpi=opts["dpi"], page=opts["page"])
        elif opts["type"] == "dxf":
            scene.import_dxf(opts["file"],
                             color=opts["color"],
                             line_weight=opts["line_weight"],
                             layers=opts["layers"])
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QSpinBox, QComboBox,
    QCheckBox, QListWidget, QListWidgetItem, QRadioButton,
    QButtonGroup, QStackedWidget, QDialogButtonBox, QColorDialog,
    QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


# ── Line-weight options (shared with old DxfImportDialog) ────────────────────

_LW_OPTIONS: list[tuple[str, float]] = [
    ("Hairline (0)",            0.0),
    ("Very Light (0.18 mm)",   0.18),
    ("Light (0.25 mm)",        0.25),
    ("Medium (0.35 mm)",       0.35),
    ("Heavy (0.50 mm)",        0.50),
    ("Very Heavy (0.70 mm)",   0.70),
]


class UnifiedImportDialog(QDialog):
    """
    Single dialog for importing PDF or DXF underlays.

    File type is selected via radio buttons at the top.  Switching the
    type changes the stacked options panel and updates the browse filter.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Underlay")
        self.setMinimumWidth(440)

        self._color = QColor("#ffffff")

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── File type selection ───────────────────────────────────────────────
        type_group = QGroupBox("File Type")
        type_row = QHBoxLayout(type_group)
        self._rb_pdf = QRadioButton("PDF")
        self._rb_dxf = QRadioButton("DXF")
        self._rb_pdf.setChecked(True)
        type_row.addWidget(self._rb_pdf)
        type_row.addWidget(self._rb_dxf)
        type_row.addStretch()
        root.addWidget(type_group)

        # ── File path ─────────────────────────────────────────────────────────
        file_group = QGroupBox("File")
        file_row = QHBoxLayout(file_group)
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("Select a file…")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._browse)
        file_row.addWidget(self._file_edit)
        file_row.addWidget(self._browse_btn)
        root.addWidget(file_group)

        # ── Type-specific options ─────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_pdf_panel())   # index 0
        self._stack.addWidget(self._build_dxf_panel())   # index 1
        root.addWidget(self._stack)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # Wire type toggle
        self._rb_pdf.toggled.connect(self._on_type_changed)
        self._rb_dxf.toggled.connect(self._on_type_changed)

    # ── Panel builders ────────────────────────────────────────────────────────

    def _build_pdf_panel(self) -> QGroupBox:
        grp = QGroupBox("PDF Options")
        lay = QVBoxLayout(grp)

        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("Render DPI:"))
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(50, 600)
        self._dpi_spin.setValue(150)
        dpi_row.addWidget(self._dpi_spin)
        dpi_row.addStretch()
        lay.addLayout(dpi_row)

        page_row = QHBoxLayout()
        page_row.addWidget(QLabel("Page:"))
        self._page_spin = QSpinBox()
        self._page_spin.setRange(0, 999)
        self._page_spin.setValue(0)
        page_row.addWidget(self._page_spin)
        page_row.addStretch()
        lay.addLayout(page_row)

        return grp

    def _build_dxf_panel(self) -> QGroupBox:
        grp = QGroupBox("DXF Options")
        lay = QVBoxLayout(grp)

        # Colour row
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Line Colour:"))
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(60, 24)
        self._color_btn.clicked.connect(self._pick_color)
        self._refresh_color_btn()
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        lay.addLayout(color_row)

        # Line weight
        lw_row = QHBoxLayout()
        lw_row.addWidget(QLabel("Line Weight:"))
        self._lw_combo = QComboBox()
        for label, _ in _LW_OPTIONS:
            self._lw_combo.addItem(label)
        self._lw_combo.setCurrentIndex(1)      # default: Very Light
        lw_row.addWidget(self._lw_combo)
        lw_row.addStretch()
        lay.addLayout(lw_row)

        # Layer filter
        layer_lbl = QLabel("Layers (optional — load file to populate):")
        lay.addWidget(layer_lbl)

        btn_row = QHBoxLayout()
        load_btn = QPushButton("Load Layers from File")
        load_btn.clicked.connect(self._load_dxf_layers)
        self._sel_all_cb = QCheckBox("Select All")
        self._sel_all_cb.setChecked(True)
        self._sel_all_cb.stateChanged.connect(self._toggle_all_layers)
        btn_row.addWidget(load_btn)
        btn_row.addWidget(self._sel_all_cb)
        lay.addLayout(btn_row)

        self._layer_list = QListWidget()
        self._layer_list.setMaximumHeight(140)
        lay.addWidget(self._layer_list)

        return grp

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_type_changed(self):
        self._stack.setCurrentIndex(0 if self._rb_pdf.isChecked() else 1)
        # Clear the path when switching type
        self._file_edit.clear()

    def _browse(self):
        from PyQt6.QtWidgets import QFileDialog
        if self._rb_pdf.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select PDF File", "",
                "PDF Files (*.pdf);;All Files (*)"
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select DXF File", "",
                "DXF Files (*.dxf);;All Files (*)"
            )
        if path:
            self._file_edit.setText(path)
            if self._rb_dxf.isChecked():
                self._load_dxf_layers()

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Choose Line Colour")
        if color.isValid():
            self._color = color
            self._refresh_color_btn()

    def _refresh_color_btn(self):
        self._color_btn.setStyleSheet(
            f"background-color: {self._color.name()}; border: 1px solid #888;"
        )

    def _load_dxf_layers(self):
        """Read layer names from the selected DXF file and populate the list."""
        path = self._file_edit.text().strip()
        if not path:
            return
        try:
            import ezdxf
            doc = ezdxf.readfile(path)
            layers = sorted(layer.dxf.name for layer in doc.layers)
        except Exception:
            layers = []

        self._layer_list.clear()
        for name in layers:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._layer_list.addItem(item)

    def _toggle_all_layers(self, state):
        checked = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        for i in range(self._layer_list.count()):
            self._layer_list.item(i).setCheckState(checked)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_options(self) -> dict:
        """Return all import options as a plain dict.

        Keys
        ----
        type        : "pdf" | "dxf"
        file        : str  — absolute path
        -- PDF only --
        dpi         : int
        page        : int
        -- DXF only --
        color       : QColor
        line_weight : float  (mm)
        layers      : list[str] | None  — None means "all layers"
        """
        file_type = "pdf" if self._rb_pdf.isChecked() else "dxf"
        opts: dict = {
            "type": file_type,
            "file": self._file_edit.text().strip(),
        }
        if file_type == "pdf":
            opts["dpi"]  = self._dpi_spin.value()
            opts["page"] = self._page_spin.value()
        else:
            opts["color"]       = QColor(self._color)
            opts["line_weight"] = _LW_OPTIONS[self._lw_combo.currentIndex()][1]
            opts["layers"]      = self._get_selected_layers()
        return opts

    def _get_selected_layers(self) -> list[str] | None:
        if self._layer_list.count() == 0:
            return None
        selected = []
        all_checked = True
        for i in range(self._layer_list.count()):
            item = self._layer_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
            else:
                all_checked = False
        return None if all_checked else selected
