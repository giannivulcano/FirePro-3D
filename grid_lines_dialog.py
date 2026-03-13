"""
grid_lines_dialog.py
====================
Revit-style dialog for placing / editing finite gridlines (GridlineItem).

Features
--------
* Separate **Horizontal** and **Vertical** tabs.
* Each tab has: labelling controls, quick-fill, and an editable table.
* When re-opened, current scene gridlines populate the tables.
* All dimensions honour the current ScaleManager display unit.
"""

from __future__ import annotations

import math
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QDoubleSpinBox, QSpinBox, QDialogButtonBox, QLabel,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QAbstractItemView, QTabWidget, QWidget,
)
from PyQt6.QtCore import Qt, QPointF


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


# ── Helper: classify an existing gridline as H or V ──────────────────────────

def _classify_gridline(p1: QPointF, p2: QPointF) -> str:
    """Return 'H' if the gridline is mostly horizontal, else 'V'."""
    dx = abs(p2.x() - p1.x())
    dy = abs(p2.y() - p1.y())
    return "H" if dx >= dy else "V"


def _normalize_angle(angle: float) -> float:
    """Clamp angle to the range 0–90 (always positive)."""
    a = abs(angle) % 180.0
    if a > 90.0:
        a = 180.0 - a
    return round(a, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Per-direction tab widget
# ─────────────────────────────────────────────────────────────────────────────

class _DirectionTab(QWidget):
    """One tab containing labelling, quick-fill, and an editable gridline table."""

    def __init__(self, direction: str, suffix: str, parent=None):
        """*direction* is ``'H'`` or ``'V'``."""
        super().__init__(parent)
        self._direction = direction
        self._suffix = suffix
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(6)

        # ── Labelling ─────────────────────────────────────────────────────
        lbl_group = QGroupBox("Labelling")
        lbl_form = QFormLayout(lbl_group)
        lbl_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._scheme_combo = QComboBox()
        if self._direction == "V":
            self._scheme_combo.addItems(["Numbers (1, 2, 3…)", "Letters (A, B, C…)", "Custom"])
        else:
            self._scheme_combo.addItems(["Letters (A, B, C…)", "Numbers (1, 2, 3…)", "Custom"])
        lbl_form.addRow("Scheme:", self._scheme_combo)

        self._start_label = QLineEdit()
        self._start_label.setMaximumWidth(80)
        self._update_start_label()
        self._scheme_combo.currentTextChanged.connect(self._update_start_label)
        lbl_form.addRow("Start Label:", self._start_label)

        self._length_spin = QDoubleSpinBox()
        self._length_spin.setRange(1, 1_000_000)
        self._length_spin.setValue(1000)
        self._length_spin.setDecimals(2)
        self._length_spin.setSuffix(self._suffix)
        lbl_form.addRow("Default Length:", self._length_spin)

        outer.addWidget(lbl_group)

        # ── Quick-fill ────────────────────────────────────────────────────
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
        self._qf_spacing.setSuffix(self._suffix)
        qf_lay.addWidget(self._qf_spacing)

        gen_btn = QPushButton("Generate")
        gen_btn.clicked.connect(self._generate_array)
        qf_lay.addWidget(gen_btn)

        outer.addWidget(qf_group)

        # ── Table ─────────────────────────────────────────────────────────
        self._default_angle = 90.0 if self._direction == "V" else 0.0
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels([
            "Label",
            "Offset" + self._suffix,
            "Spacing" + self._suffix,
            "Length" + self._suffix,
            "Angle°",
        ])
        self._syncing = False  # guard against recursive cellChanged loops
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(180)
        outer.addWidget(self._table)

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
        outer.addLayout(btn_row)

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

    def _next_table_label(self) -> str:
        if self._table.rowCount() == 0:
            return self._start_label.text() or "A"
        last_item = self._table.item(self._table.rowCount() - 1, 0)
        last_label = last_item.text() if last_item else "A"
        return _increment_label(last_label, self._current_scheme())

    def _last_offset(self) -> float:
        if self._table.rowCount() == 0:
            return 0.0
        item = self._table.item(self._table.rowCount() - 1, 1)
        try:
            return float(item.text()) if item else 0.0
        except ValueError:
            return 0.0

    def _row_offset(self, row: int) -> float:
        if row < 0 or row >= self._table.rowCount():
            return 0.0
        item = self._table.item(row, 1)
        try:
            return float(item.text()) if item else 0.0
        except ValueError:
            return 0.0

    def _on_cell_changed(self, row: int, col: int):
        """Keep Offset (col 1) and Spacing (col 2) in sync."""
        if self._syncing:
            return
        self._syncing = True
        if col == 1:
            # Offset changed → recalculate Spacing
            offset = self._row_offset(row)
            prev = self._row_offset(row - 1) if row > 0 else 0.0
            spacing = offset - prev
            sp_item = self._table.item(row, 2)
            if sp_item:
                sp_item.setText(f"{spacing:.2f}")
            # Also update next row's spacing if it exists
            if row + 1 < self._table.rowCount():
                next_off = self._row_offset(row + 1)
                next_sp = next_off - offset
                nsp_item = self._table.item(row + 1, 2)
                if nsp_item:
                    nsp_item.setText(f"{next_sp:.2f}")
        elif col == 2:
            # Spacing changed → recalculate Offset
            sp_item = self._table.item(row, 2)
            try:
                spacing = float(sp_item.text()) if sp_item else 0.0
            except ValueError:
                spacing = 0.0
            prev = self._row_offset(row - 1) if row > 0 else 0.0
            new_offset = prev + spacing
            off_item = self._table.item(row, 1)
            if off_item:
                off_item.setText(f"{new_offset:.2f}")
        self._syncing = False

    # ── Row management ────────────────────────────────────────────────────

    def _add_row(self):
        self._syncing = True
        row = self._table.rowCount()
        self._table.insertRow(row)
        label = self._next_table_label() if row > 0 else (self._start_label.text() or "A")
        offset = self._last_offset()
        prev = self._row_offset(row - 1) if row > 0 else 0.0
        spacing = offset - prev
        length = self._length_spin.value()
        self._table.setItem(row, 0, QTableWidgetItem(label))
        self._table.setItem(row, 1, QTableWidgetItem(f"{offset:.2f}"))
        self._table.setItem(row, 2, QTableWidgetItem(f"{spacing:.2f}"))
        self._table.setItem(row, 3, QTableWidgetItem(f"{length:.2f}"))
        self._table.setItem(row, 4, QTableWidgetItem(f"{self._default_angle:.1f}"))
        self._syncing = False

    def _remove_row(self):
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()),
                      reverse=True)
        if rows:
            for r in rows:
                self._table.removeRow(r)
        elif self._table.rowCount() > 0:
            self._table.removeRow(self._table.rowCount() - 1)

    # ── Quick-fill ────────────────────────────────────────────────────────

    def _generate_array(self):
        self._syncing = True
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
            self._table.setItem(row, 2, QTableWidgetItem(f"{spacing:.2f}"))
            self._table.setItem(row, 3, QTableWidgetItem(f"{length:.2f}"))
            self._table.setItem(row, 4, QTableWidgetItem(f"{self._default_angle:.1f}"))
            label = _increment_label(label, scheme)
        self._syncing = False

    # ── Populate from existing gridlines ──────────────────────────────────

    def populate(self, rows: list[tuple[str, float, float, float]]):
        """Fill table with existing gridlines: list of (label, offset, length, angle)
        where offset and length are in **display units**, angle in degrees."""
        self._syncing = True
        self._table.setRowCount(0)
        prev_offset = 0.0
        for label, offset, length, angle in rows:
            row = self._table.rowCount()
            self._table.insertRow(row)
            spacing = offset - prev_offset
            angle = _normalize_angle(angle)
            self._table.setItem(row, 0, QTableWidgetItem(label))
            self._table.setItem(row, 1, QTableWidgetItem(f"{offset:.2f}"))
            self._table.setItem(row, 2, QTableWidgetItem(f"{spacing:.2f}"))
            self._table.setItem(row, 3, QTableWidgetItem(f"{length:.2f}"))
            self._table.setItem(row, 4, QTableWidgetItem(f"{angle:.1f}"))
            prev_offset = offset
        self._syncing = False

    # ── Read table ────────────────────────────────────────────────────────

    def read_rows(self) -> list[tuple[str, float, float, float]]:
        """Return (label, offset_display, length_display, angle_deg) for each row."""
        result = []
        for row in range(self._table.rowCount()):
            lbl_item = self._table.item(row, 0)
            off_item = self._table.item(row, 1)
            # column 2 = spacing (derived), skip
            len_item = self._table.item(row, 3)
            ang_item = self._table.item(row, 4)
            label = lbl_item.text() if lbl_item else "?"
            try:
                offset = float(off_item.text()) if off_item else 0.0
            except ValueError:
                offset = 0.0
            try:
                length = float(len_item.text()) if len_item else 100.0
            except ValueError:
                length = 100.0
            try:
                angle = float(ang_item.text()) if ang_item else self._default_angle
            except ValueError:
                angle = self._default_angle
            angle = _normalize_angle(angle)
            result.append((label, offset, length, angle))
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Main dialog
# ─────────────────────────────────────────────────────────────────────────────

class GridLinesDialog(QDialog):
    """Modal dialog with Horizontal / Vertical tabs for gridline editing."""

    def __init__(self, parent=None, *, scale_manager=None,
                 existing_gridlines: list | None = None):
        super().__init__(parent)
        self.setWindowTitle("Gridlines")
        self.setMinimumWidth(480)
        self.setMinimumHeight(520)
        self._sm = scale_manager
        self._build_ui()

        # Populate tabs with existing gridlines (if any)
        if existing_gridlines:
            self._populate_from_scene(existing_gridlines)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        _suffix = self._sm.display_unit_suffix() if self._sm else "  units"

        self._tabs = QTabWidget()
        self._v_tab = _DirectionTab("V", _suffix)
        self._h_tab = _DirectionTab("H", _suffix)
        self._tabs.addTab(self._v_tab, "Vertical")
        self._tabs.addTab(self._h_tab, "Horizontal")
        outer.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ── Populate from existing scene gridlines ────────────────────────────

    def _scene_to_display(self, val: float) -> float:
        """Convert scene units to display units (numeric)."""
        if self._sm and hasattr(self._sm, 'scene_to_display_value'):
            return self._sm.scene_to_display_value(val)
        return val

    def _populate_from_scene(self, gridlines):
        """Read existing GridlineItem list and fill H/V tables."""
        h_rows: list[tuple[str, float, float, float]] = []
        v_rows: list[tuple[str, float, float, float]] = []

        for gl in gridlines:
            line = gl.line()
            p1, p2 = line.p1(), line.p2()
            label = gl.grid_label
            length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            # Compute angle from endpoints
            angle_rad = math.atan2(-(p2.y() - p1.y()), p2.x() - p1.x())
            angle_deg = _normalize_angle(math.degrees(angle_rad))
            kind = _classify_gridline(p1, p2)

            if kind == "V":
                offset = (p1.x() + p2.x()) / 2.0
                v_rows.append((label,
                               self._scene_to_display(offset),
                               self._scene_to_display(length),
                               angle_deg))
            else:
                # Horizontal: offset = -y position (architectural convention)
                offset = -((p1.y() + p2.y()) / 2.0)
                h_rows.append((label,
                               self._scene_to_display(offset),
                               self._scene_to_display(length),
                               angle_deg))

        if v_rows:
            self._v_tab.populate(v_rows)
        if h_rows:
            self._h_tab.populate(h_rows)

    # ── Result ────────────────────────────────────────────────────────────

    def _to_scene(self, val: float) -> float:
        if self._sm:
            return self._sm.display_to_scene(val)
        return val

    def get_gridlines(self) -> list[dict]:
        """Return combined H+V gridline specs for ``Model_Space.place_grid_lines()``.

        Each dict has keys: label, offset (scene), length (scene), angle_deg.
        """
        result = []

        # Vertical gridlines
        for label, offset, length, angle in self._v_tab.read_rows():
            result.append({
                "label": label,
                "offset": self._to_scene(offset),
                "length": self._to_scene(length),
                "angle_deg": angle,
            })

        # Horizontal gridlines
        for label, offset, length, angle in self._h_tab.read_rows():
            result.append({
                "label": label,
                "offset": self._to_scene(offset),
                "length": self._to_scene(length),
                "angle_deg": angle,
            })

        return result

    def get_params(self) -> dict:
        """Backward-compat wrapper for ``main.py``."""
        return {"gridlines": self.get_gridlines()}
