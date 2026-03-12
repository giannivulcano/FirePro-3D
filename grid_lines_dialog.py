"""
grid_lines_dialog.py
====================
Revit-style dialog for placing finite gridlines (GridlineItem) on the canvas.

Features
--------
* Direction: Horizontal / Vertical / Custom angle
* Labelling: customisable start label + scheme (Letters / Numbers / Custom)
* Editable table: Label | Offset (from origin) | Length
* Quick-fill: generate N gridlines at uniform spacing
* +/− row buttons
* All dimensions honour the current ScaleManager display unit.
"""

from __future__ import annotations

import math
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QDoubleSpinBox, QSpinBox, QDialogButtonBox, QLabel,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QAbstractItemView, QSizePolicy,
)
from PyQt6.QtCore import Qt


# ── Label generation helpers ──────────────────────────────────────────────────

def _increment_label(label: str, scheme: str) -> str:
    """Return the next label after *label* according to the naming scheme."""
    if scheme == "Numbers":
        try:
            return str(int(label) + 1)
        except ValueError:
            return label + "'"
    elif scheme == "Letters":
        return _next_letter(label)
    else:
        # Custom — just append a prime mark
        return label + "'"


def _next_letter(s: str) -> str:
    """Increment a letter label: A→B, Z→AA, AZ→BA."""
    if not s:
        return "A"
    chars = list(s.upper())
    carry = True
    for i in range(len(chars) - 1, -1, -1):
        if carry:
            if chars[i] == "Z":
                chars[i] = "A"
            else:
                chars[i] = chr(ord(chars[i]) + 1)
                carry = False
    if carry:
        chars.insert(0, "A")
    return "".join(chars)


# ─────────────────────────────────────────────────────────────────────────────
# Dialog
# ─────────────────────────────────────────────────────────────────────────────

class GridLinesDialog(QDialog):
    """Modal dialog for configuring and placing finite gridlines."""

    def __init__(self, parent=None, scale_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Place Gridlines")
        self.setMinimumWidth(480)
        self._sm = scale_manager
        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        _suffix = self._sm.display_unit_suffix() if self._sm else "  units"

        # ── Direction group ───────────────────────────────────────────────
        dir_group = QGroupBox("Direction")
        dir_form = QFormLayout(dir_group)
        dir_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._dir_combo = QComboBox()
        self._dir_combo.addItems(["Vertical", "Horizontal", "Custom Angle"])
        self._dir_combo.currentTextChanged.connect(self._on_direction_changed)
        dir_form.addRow("Direction:", self._dir_combo)

        self._angle_spin = QDoubleSpinBox()
        self._angle_spin.setRange(-360, 360)
        self._angle_spin.setValue(90)
        self._angle_spin.setDecimals(2)
        self._angle_spin.setSuffix("°")
        self._angle_spin.setEnabled(False)
        dir_form.addRow("Angle:", self._angle_spin)

        self._length_spin = QDoubleSpinBox()
        self._length_spin.setRange(1, 1_000_000)
        self._length_spin.setValue(1000)
        self._length_spin.setDecimals(2)
        self._length_spin.setSuffix(_suffix)
        dir_form.addRow("Default Length:", self._length_spin)

        outer.addWidget(dir_group)

        # ── Labelling group ───────────────────────────────────────────────
        lbl_group = QGroupBox("Labelling")
        lbl_form = QFormLayout(lbl_group)
        lbl_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._scheme_combo = QComboBox()
        self._scheme_combo.addItems(["Letters (A, B, C…)", "Numbers (1, 2, 3…)", "Custom"])
        lbl_form.addRow("Scheme:", self._scheme_combo)

        self._start_label = QLineEdit()
        self._start_label.setMaximumWidth(80)
        self._update_start_label()
        self._scheme_combo.currentTextChanged.connect(self._update_start_label)
        lbl_form.addRow("Start Label:", self._start_label)

        outer.addWidget(lbl_group)

        # ── Quick-fill group ──────────────────────────────────────────────
        qf_group = QGroupBox("Quick Fill")
        qf_lay = QHBoxLayout(qf_group)

        qf_lay.addWidget(QLabel("Count:"))
        self._qf_count = QSpinBox()
        self._qf_count.setRange(1, 200)
        self._qf_count.setValue(5)
        qf_lay.addWidget(self._qf_count)

        qf_lay.addWidget(QLabel("Spacing:"))
        self._qf_spacing = QDoubleSpinBox()
        self._qf_spacing.setRange(0.01, 1_000_000)
        self._qf_spacing.setValue(100)
        self._qf_spacing.setDecimals(2)
        self._qf_spacing.setSuffix(_suffix)
        qf_lay.addWidget(self._qf_spacing)

        gen_btn = QPushButton("Generate")
        gen_btn.clicked.connect(self._generate_array)
        qf_lay.addWidget(gen_btn)

        outer.addWidget(qf_group)

        # ── Table ─────────────────────────────────────────────────────────
        tbl_group = QGroupBox("Gridlines")
        tbl_lay = QVBoxLayout(tbl_group)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Label", "Offset" + _suffix, "Length" + _suffix])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(180)
        tbl_lay.addWidget(self._table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(40)
        add_btn.clicked.connect(self._add_row)
        rem_btn = QPushButton("−")
        rem_btn.setFixedWidth(40)
        rem_btn.clicked.connect(self._remove_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rem_btn)
        btn_row.addStretch()
        tbl_lay.addLayout(btn_row)

        outer.addWidget(tbl_group)

        # ── OK / Cancel ──────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # ── Seed first row ────────────────────────────────────────────────
        self._add_row()

    # ── Direction helpers ─────────────────────────────────────────────────

    def _on_direction_changed(self, text: str):
        self._angle_spin.setEnabled(text == "Custom Angle")
        if text == "Vertical":
            self._angle_spin.setValue(90)
        elif text == "Horizontal":
            self._angle_spin.setValue(0)

    # ── Labelling helpers ─────────────────────────────────────────────────

    def _current_scheme(self) -> str:
        text = self._scheme_combo.currentText()
        if text.startswith("Letters"):
            return "Letters"
        elif text.startswith("Numbers"):
            return "Numbers"
        return "Custom"

    def _update_start_label(self):
        scheme = self._current_scheme()
        if scheme == "Letters":
            self._start_label.setText("A")
        elif scheme == "Numbers":
            self._start_label.setText("1")
        # Custom: leave whatever the user typed

    def _next_table_label(self) -> str:
        """Compute the next label based on the last row in the table."""
        if self._table.rowCount() == 0:
            return self._start_label.text() or "A"
        last_item = self._table.item(self._table.rowCount() - 1, 0)
        last_label = last_item.text() if last_item else "A"
        return _increment_label(last_label, self._current_scheme())

    def _last_offset(self) -> float:
        """Return the offset from the last row, or 0.0."""
        if self._table.rowCount() == 0:
            return 0.0
        item = self._table.item(self._table.rowCount() - 1, 1)
        try:
            return float(item.text()) if item else 0.0
        except ValueError:
            return 0.0

    # ── Table row management ──────────────────────────────────────────────

    def _add_row(self):
        """Append one row with auto-incremented label and default values."""
        row = self._table.rowCount()
        self._table.insertRow(row)

        label = self._next_table_label() if row > 0 else (self._start_label.text() or "A")
        offset = self._last_offset() if row == 0 else self._last_offset()
        length = self._length_spin.value()

        self._table.setItem(row, 0, QTableWidgetItem(label))
        self._table.setItem(row, 1, QTableWidgetItem(f"{offset:.2f}"))
        self._table.setItem(row, 2, QTableWidgetItem(f"{length:.2f}"))

    def _remove_row(self):
        """Remove selected rows (or the last row)."""
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()),
                      reverse=True)
        if rows:
            for r in rows:
                self._table.removeRow(r)
        elif self._table.rowCount() > 0:
            self._table.removeRow(self._table.rowCount() - 1)

    # ── Quick-fill ────────────────────────────────────────────────────────

    def _generate_array(self):
        """Populate the table with N rows at uniform spacing."""
        self._table.setRowCount(0)
        count = self._qf_count.value()
        spacing = self._qf_spacing.value()
        length = self._length_spin.value()
        scheme = self._current_scheme()

        label = self._start_label.text() or ("A" if scheme == "Letters" else "1")
        for i in range(count):
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(label))
            self._table.setItem(row, 1, QTableWidgetItem(f"{i * spacing:.2f}"))
            self._table.setItem(row, 2, QTableWidgetItem(f"{length:.2f}"))
            label = _increment_label(label, scheme)

    # ── Result ────────────────────────────────────────────────────────────

    def _to_scene(self, val: float) -> float:
        """Convert a display-unit value to scene units (pixels)."""
        if self._sm:
            return self._sm.display_to_scene(val)
        return val

    def get_gridlines(self) -> list[dict]:
        """Return list of gridline specs: {label, offset, length, angle_deg}.

        *offset* and *length* are in **scene units** (pixels).
        *angle_deg* is the gridline direction (0 = horizontal, 90 = vertical).
        """
        angle = self._angle_spin.value()
        result = []
        for row in range(self._table.rowCount()):
            lbl_item = self._table.item(row, 0)
            off_item = self._table.item(row, 1)
            len_item = self._table.item(row, 2)
            label = lbl_item.text() if lbl_item else "?"
            try:
                offset = self._to_scene(float(off_item.text())) if off_item else 0.0
            except ValueError:
                offset = 0.0
            try:
                length = self._to_scene(float(len_item.text())) if len_item else 100.0
            except ValueError:
                length = 100.0
            result.append({
                "label": label,
                "offset": offset,
                "length": length,
                "angle_deg": angle,
            })
        return result

    # Keep backward-compat method name used by main.py
    def get_params(self) -> dict:
        """Return parameters in the new gridline format."""
        return {"gridlines": self.get_gridlines()}
