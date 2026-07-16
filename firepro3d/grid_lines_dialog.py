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
    QSpinBox, QDialogButtonBox, QLabel,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QAbstractItemView, QTabWidget, QWidget,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QKeySequence

from .constants import (DEFAULT_GRIDLINE_SPACING_IN, DEFAULT_GRIDLINE_LENGTH_IN,
                        GRIDLINE_BUBBLE_OVERSHOOT_FRAC)
from .dimension_edit import DimensionEdit, DimensionDelegate
from .scale_manager import ScaleManager


class _NumericItem(QTableWidgetItem):
    """Table item that sorts by a numeric value, not lexicographically.

    Stores a float via ``setData(UserRole+1, value)`` and uses it for
    ``__lt__`` comparison so that ``24'-0"`` sorts correctly next to
    ``48'-0"`` regardless of display format.
    """

    def __init__(self, text: str, sort_value: float):
        super().__init__(text)
        self.setData(Qt.ItemDataRole.UserRole + 1, sort_value)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        my_val = self.data(Qt.ItemDataRole.UserRole + 1)
        other_val = other.data(Qt.ItemDataRole.UserRole + 1) if other else None
        if my_val is not None and other_val is not None:
            return float(my_val) < float(other_val)
        return super().__lt__(other)


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
    """Return 'H' if the gridline is mostly horizontal, else 'V'.

    At exactly 45 degrees (dx == dy), classifies as 'V' to match
    ``auto_label``'s ``dy >= dx`` rule (spec §15).
    """
    dx = abs(p2.x() - p1.x())
    dy = abs(p2.y() - p1.y())
    return "H" if dx > dy else "V"


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

    def __init__(self, direction: str, scale_manager=None, parent=None):
        """*direction* is ``'H'`` or ``'V'``."""
        super().__init__(parent)
        self._direction = direction
        self._sm = scale_manager
        self._build_ui()

        # Session-only undo/redo of table state (cell edits incl. their
        # sync effects, add/remove row, Generate, sorts). Snapshots are
        # recorded on a 0 ms singleshot so one user action — which may fire
        # several cellChanged signals — coalesces into one undo step.
        self._undo_stack: list[list] = []
        self._redo_stack: list[list] = []
        self._record_timer = QTimer(self)
        self._record_timer.setSingleShot(True)
        self._record_timer.setInterval(0)
        self._record_timer.timeout.connect(self._record_state)
        self._undo_stack.append(self._snapshot())

    # ── Dimension format / parse helpers ──────────────────────────────

    def _fmt(self, mm: float) -> str:
        """Format mm as a display string (e.g. ``24'-0"`` or ``7315.2 mm``)."""
        if self._sm:
            return self._sm.format_length(mm)
        return f"{mm:.1f} mm"

    def _parse(self, text: str) -> float:
        """Parse a dimension string to mm. Returns 0.0 on failure."""
        if self._sm:
            fallback = self._sm.bare_number_unit()
            parsed = ScaleManager.parse_dimension(text.strip(), fallback)
            if parsed is not None:
                return parsed
        try:
            return float(text)
        except ValueError:
            return 0.0

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

        self._length_edit = DimensionEdit(self._sm,
                                          initial_mm=DEFAULT_GRIDLINE_LENGTH_IN)
        self._length_edit.setMaximumWidth(140)
        lbl_form.addRow("Default Length:", self._length_edit)

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
        self._qf_spacing_edit = DimensionEdit(self._sm,
                                              initial_mm=DEFAULT_GRIDLINE_SPACING_IN)
        self._qf_spacing_edit.setMaximumWidth(140)
        qf_lay.addWidget(self._qf_spacing_edit)

        gen_btn = QPushButton("Generate")
        gen_btn.clicked.connect(self._generate_array)
        qf_lay.addWidget(gen_btn)

        outer.addWidget(qf_group)

        # ── Table ─────────────────────────────────────────────────────────
        self._default_angle = 90.0 if self._direction == "V" else 0.0
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Label",
            "Offset",
            "Spacing",
            "Length",
            "Angle°",
            "Locked",
            "_backing",
        ])
        self._table.setColumnHidden(6, True)  # _backing is now column 6
        # Dimension columns edit through the canonical DimensionEdit widget
        # (units-and-formatting.md §3 / property-panel.md §3.8): commits are
        # re-formatted to display units, invalid input reverts. The mm value
        # lives in UserRole+1 (also the numeric sort key).
        self._dim_delegate = DimensionDelegate(
            lambda: self._sm, parent=self._table,
            value_role=Qt.ItemDataRole.UserRole + 1)
        for col in (1, 2, 3):   # Offset, Spacing, Length
            self._table.setItemDelegateForColumn(col, self._dim_delegate)
        self._syncing = False  # guard against recursive cellChanged loops
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        header = self._table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setStyleSheet(
            "QHeaderView::section { padding-right: 14px; }"
            "QHeaderView::down-arrow, QHeaderView::up-arrow {"
            "  width: 10px; height: 10px;"
            "  subcontrol-position: center right;"
            "  padding-right: 2px;"
            "}")
        header.sectionClicked.connect(self._sort_by_column)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._sort_col = -1
        self._sort_asc = True
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

    def _cell_mm(self, row: int, col: int) -> float:
        """Return a dimension cell's value in mm.

        Prefers the exact mm value in the UserRole+1 slot (kept current by
        the DimensionDelegate and the sync handler); falls back to parsing
        the display text for cells that predate the role value.
        """
        if row < 0 or row >= self._table.rowCount():
            return 0.0
        item = self._table.item(row, col)
        if item is None:
            return 0.0
        val = item.data(Qt.ItemDataRole.UserRole + 1)
        if val is not None:
            return float(val)
        return self._parse(item.text())

    def _last_offset_mm(self) -> float:
        """Return the last row's offset in mm."""
        return self._cell_mm(self._table.rowCount() - 1, 1)

    def _row_offset_mm(self, row: int) -> float:
        """Return a row's offset in mm."""
        return self._cell_mm(row, 1)

    def _on_cell_changed(self, row: int, col: int):
        """Keep Offset (col 1) and Spacing (col 2) in sync."""
        if self._syncing:
            return
        self._syncing = True
        if col == 1:
            # Offset changed → recalculate Spacing
            offset = self._row_offset_mm(row)
            prev = self._row_offset_mm(row - 1) if row > 0 else 0.0
            spacing = offset - prev
            sp_item = self._table.item(row, 2)
            if sp_item:
                sp_item.setText(self._fmt(spacing))
                sp_item.setData(Qt.ItemDataRole.UserRole + 1, spacing)
            # Also update next row's spacing if it exists
            if row + 1 < self._table.rowCount():
                next_off = self._row_offset_mm(row + 1)
                next_sp = next_off - offset
                nsp_item = self._table.item(row + 1, 2)
                if nsp_item:
                    nsp_item.setText(self._fmt(next_sp))
                    nsp_item.setData(Qt.ItemDataRole.UserRole + 1, next_sp)
        elif col == 2:
            # Spacing changed → recalculate Offset
            spacing = self._cell_mm(row, 2)
            prev = self._row_offset_mm(row - 1) if row > 0 else 0.0
            new_offset = prev + spacing
            off_item = self._table.item(row, 1)
            if off_item:
                off_item.setText(self._fmt(new_offset))
                off_item.setData(Qt.ItemDataRole.UserRole + 1, new_offset)
        elif col == 4:
            # Angle changed → normalize display, revert on invalid input
            item = self._table.item(row, 4)
            if item:
                try:
                    angle = _normalize_angle(float(item.text()))
                except ValueError:
                    prev_val = item.data(Qt.ItemDataRole.UserRole + 1)
                    angle = (float(prev_val) if prev_val is not None
                             else self._default_angle)
                item.setText(f"{angle:.1f}")
                item.setData(Qt.ItemDataRole.UserRole + 1, angle)
        self._syncing = False
        self._schedule_record()

    # ── Sorting ──────────────────────────────────────────────────────────

    def _sort_by_column(self, col: int):
        """Sort table by column, toggling ascending/descending."""
        if col == 6:
            return  # Don't sort by hidden backing column
        if col == self._sort_col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        order = (Qt.SortOrder.AscendingOrder if self._sort_asc
                 else Qt.SortOrder.DescendingOrder)
        self._table.horizontalHeader().setSortIndicator(col, order)
        self._syncing = True
        self._table.sortItems(col, order)
        # Recalculate all spacing values after sort (spacing is relative
        # to the previous row, so it changes when order changes).
        self._recalc_spacing()
        self._syncing = False
        self._schedule_record()

    def _recalc_spacing(self):
        """Recalculate spacing column for all rows after a sort."""
        for row in range(self._table.rowCount()):
            offset = self._row_offset_mm(row)
            prev = self._row_offset_mm(row - 1) if row > 0 else 0.0
            spacing = offset - prev
            sp_item = self._table.item(row, 2)
            if sp_item:
                sp_item.setText(self._fmt(spacing))
                sp_item.setData(Qt.ItemDataRole.UserRole + 1, spacing)

    # ── In-dialog undo / redo ─────────────────────────────────────────────

    def _snapshot(self) -> list:
        """Capture full table state (text, numeric role, backing, lock)."""
        rows = []
        for r in range(self._table.rowCount()):
            cells = []
            for c in range(7):
                item = self._table.item(r, c)
                if item is None:
                    cells.append(None)
                    continue
                cells.append({
                    "text": item.text(),
                    "num": item.data(Qt.ItemDataRole.UserRole + 1),
                    "backing": item.data(Qt.ItemDataRole.UserRole),
                    "check": item.checkState() if c == 5 else None,
                })
            rows.append(cells)
        return rows

    def _schedule_record(self):
        """Coalesce the current user action into one pending undo step."""
        self._record_timer.start()

    def _reset_history(self):
        """Make the current table state the undo baseline."""
        self._record_timer.stop()
        self._undo_stack = [self._snapshot()]
        self._redo_stack = []

    def _record_state(self):
        snap = self._snapshot()
        if self._undo_stack and snap == self._undo_stack[-1]:
            return
        self._undo_stack.append(snap)
        self._redo_stack.clear()

    def _restore(self, snap: list):
        self._syncing = True
        self._table.setRowCount(0)
        for r, cells in enumerate(snap):
            self._table.insertRow(r)
            for c, cell in enumerate(cells):
                if cell is None:
                    continue
                if c in (1, 2, 3, 4) and cell["num"] is not None:
                    # keep numeric sorting alive across restores
                    item = _NumericItem(cell["text"], float(cell["num"]))
                else:
                    item = QTableWidgetItem(cell["text"])
                    item.setData(Qt.ItemDataRole.UserRole + 1, cell["num"])
                if c == 5:
                    item.setFlags(Qt.ItemFlag.ItemIsUserCheckable
                                  | Qt.ItemFlag.ItemIsEnabled)
                    item.setCheckState(cell["check"])
                item.setData(Qt.ItemDataRole.UserRole, cell["backing"])
                self._table.setItem(r, c, item)
        self._syncing = False

    def _flush_pending_record(self):
        if self._record_timer.isActive():
            self._record_timer.stop()
            self._record_state()

    def undo(self):
        self._flush_pending_record()
        if len(self._undo_stack) < 2:
            return
        self._redo_stack.append(self._undo_stack.pop())
        self._restore(self._undo_stack[-1])

    def redo(self):
        self._flush_pending_record()
        if not self._redo_stack:
            return
        snap = self._redo_stack.pop()
        self._undo_stack.append(snap)
        self._restore(snap)

    # ── Row management ────────────────────────────────────────────────────

    def _add_row(self):
        self._syncing = True
        row = self._table.rowCount()
        # Compute label and offset BEFORE inserting the empty row
        # (otherwise helpers read the empty row's blank cells).
        label = self._next_table_label() if row > 0 else (self._start_label.text() or "A")
        if row >= 2:
            last_mm = self._row_offset_mm(row - 1)
            prev_mm = self._row_offset_mm(row - 2)
            spacing_mm = last_mm - prev_mm
        elif row == 1:
            spacing_mm = self._qf_spacing_edit.value_mm()
        else:
            spacing_mm = 0.0
        offset_mm = (self._last_offset_mm() + spacing_mm) if row > 0 else 0.0
        self._table.insertRow(row)
        length_mm = self._length_edit.value_mm()
        self._table.setItem(row, 0, QTableWidgetItem(label))
        self._table.setItem(row, 1, _NumericItem(self._fmt(offset_mm), offset_mm))
        self._table.setItem(row, 2, _NumericItem(self._fmt(spacing_mm), spacing_mm))
        self._table.setItem(row, 3, _NumericItem(self._fmt(length_mm), length_mm))
        self._table.setItem(row, 4, _NumericItem(f"{self._default_angle:.1f}", self._default_angle))
        lock_item = QTableWidgetItem()
        lock_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        lock_item.setCheckState(Qt.CheckState.Unchecked)
        self._table.setItem(row, 5, lock_item)
        backing_item = QTableWidgetItem()
        backing_item.setData(Qt.ItemDataRole.UserRole, None)
        self._table.setItem(row, 6, backing_item)
        self._syncing = False
        self._schedule_record()

    def _remove_row(self):
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()),
                      reverse=True)
        if rows:
            for r in rows:
                self._table.removeRow(r)
        elif self._table.rowCount() > 0:
            self._table.removeRow(self._table.rowCount() - 1)
        self._schedule_record()

    # ── Quick-fill ────────────────────────────────────────────────────────

    def _generate_array(self):
        self._syncing = True
        self._table.setRowCount(0)
        count = self._qf_count.value()
        spacing_mm = self._qf_spacing_edit.value_mm()
        length_mm = self._length_edit.value_mm()
        scheme = self._current_scheme()
        label = self._start_label.text() or ("A" if scheme == "Letters" else "1")
        for i in range(count):
            row = self._table.rowCount()
            self._table.insertRow(row)
            offset_mm = i * spacing_mm
            self._table.setItem(row, 0, QTableWidgetItem(label))
            self._table.setItem(row, 1, _NumericItem(self._fmt(offset_mm), offset_mm))
            self._table.setItem(row, 2, _NumericItem(self._fmt(spacing_mm), spacing_mm))
            self._table.setItem(row, 3, _NumericItem(self._fmt(length_mm), length_mm))
            self._table.setItem(row, 4, _NumericItem(f"{self._default_angle:.1f}", self._default_angle))
            lock_item = QTableWidgetItem()
            lock_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            lock_item.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(row, 5, lock_item)
            backing_item = QTableWidgetItem()
            backing_item.setData(Qt.ItemDataRole.UserRole, None)
            self._table.setItem(row, 6, backing_item)
            label = _increment_label(label, scheme)
        self._syncing = False
        self._schedule_record()

    # ── Populate from existing gridlines ──────────────────────────────────

    def populate(self, rows: list[tuple]):
        """Fill table with existing gridlines.

        Each element is ``(label, offset_mm, length_mm, angle)`` or
        ``(label, offset_mm, length_mm, angle, backing_gridline)``.
        Offset and length are in **mm**, angle in degrees.
        *backing_gridline* is the existing ``GridlineItem`` (or ``None``).
        """
        self._syncing = True
        self._table.setRowCount(0)
        prev_offset_mm = 0.0
        for entry in rows:
            if len(entry) >= 5:
                label, offset_mm, length_mm, angle, backing = entry[0], entry[1], entry[2], entry[3], entry[4]
            else:
                label, offset_mm, length_mm, angle = entry
                backing = None
            row = self._table.rowCount()
            self._table.insertRow(row)
            spacing_mm = offset_mm - prev_offset_mm
            angle = _normalize_angle(angle)
            self._table.setItem(row, 0, QTableWidgetItem(label))
            self._table.setItem(row, 1, _NumericItem(self._fmt(offset_mm), offset_mm))
            self._table.setItem(row, 2, _NumericItem(self._fmt(spacing_mm), spacing_mm))
            self._table.setItem(row, 3, _NumericItem(self._fmt(length_mm), length_mm))
            self._table.setItem(row, 4, _NumericItem(f"{angle:.1f}", angle))
            lock_item = QTableWidgetItem()
            lock_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            lock_item.setCheckState(
                Qt.CheckState.Checked if (backing is not None and backing._locked)
                else Qt.CheckState.Unchecked
            )
            self._table.setItem(row, 5, lock_item)
            backing_item = QTableWidgetItem()
            backing_item.setData(Qt.ItemDataRole.UserRole, backing)
            self._table.setItem(row, 6, backing_item)
            prev_offset_mm = offset_mm
        self._syncing = False
        # Populate defines the baseline state — not an undoable action.
        self._reset_history()

    # ── Read table ────────────────────────────────────────────────────────

    def read_rows(self) -> list[tuple]:
        """Return (label, offset_mm, length_mm, angle_deg, backing, locked) per row.

        *backing* is the original ``GridlineItem`` reference (or ``None``
        for newly-added rows).  Offset and length are in **mm**.
        *locked* is a bool indicating the lock checkbox state.
        """
        result = []
        for row in range(self._table.rowCount()):
            lbl_item = self._table.item(row, 0)
            off_item = self._table.item(row, 1)
            # column 2 = spacing (derived), skip
            len_item = self._table.item(row, 3)
            ang_item = self._table.item(row, 4)
            lock_item = self._table.item(row, 5)
            bck_item = self._table.item(row, 6)
            label = lbl_item.text() if lbl_item else "?"
            offset = self._cell_mm(row, 1) if off_item else 0.0
            length = self._cell_mm(row, 3) if len_item else 100.0
            try:
                angle = float(ang_item.text()) if ang_item else self._default_angle
            except ValueError:
                angle = self._default_angle
            angle = _normalize_angle(angle)
            backing = bck_item.data(Qt.ItemDataRole.UserRole) if bck_item else None
            locked = (lock_item.checkState() == Qt.CheckState.Checked) if lock_item else False
            result.append((label, offset, length, angle, backing, locked))
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
        self._existing = list(existing_gridlines) if existing_gridlines else []
        self._build_ui()

        # Populate tabs with existing gridlines (if any)
        if self._existing:
            self._populate_from_scene(self._existing)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        self._tabs = QTabWidget()
        self._v_tab = _DirectionTab("V", scale_manager=self._sm)
        self._h_tab = _DirectionTab("H", scale_manager=self._sm)
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

    # ── Undo / redo routing ───────────────────────────────────────────────

    def keyPressEvent(self, event):
        """Route Ctrl+Z / Ctrl+Y (and Ctrl+Shift+Z) to the active tab.

        Reaches here only when no cell editor is open — an open editor
        (QLineEdit/DimensionEdit) consumes these for its own text undo,
        which is the desired behaviour.
        """
        if event.matches(QKeySequence.StandardKey.Undo):
            self._tabs.currentWidget().undo()
            event.accept()
            return
        if (event.matches(QKeySequence.StandardKey.Redo)
                or (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and event.key() == Qt.Key.Key_Y)):
            self._tabs.currentWidget().redo()
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Populate from existing scene gridlines ────────────────────────────

    def _populate_from_scene(self, gridlines):
        """Read existing GridlineItem list and fill H/V tables.

        Each row stores a reference to its backing GridlineItem so
        that ``apply_grid_dialog()`` can diff-reconcile on accept.
        """
        h_rows: list[tuple] = []
        v_rows: list[tuple] = []

        for gl in gridlines:
            line = gl.line()
            p1, p2 = line.p1(), line.p2()
            label = gl.grid_label
            # Invert the scene construction exactly (apply_grid_dialog):
            # the drawn line runs from origin - overshoot to origin + length,
            # so |p1p2| = (1 + frac) * length. Reading the raw hypot as the
            # dialog Length grew gridlines 6% on every open → OK round-trip.
            line_len = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            length = line_len / (1.0 + GRIDLINE_BUBBLE_OVERSHOOT_FRAC)
            if line_len > 0.0:
                ux = (p2.x() - p1.x()) / line_len
                uy = (p2.y() - p1.y()) / line_len
                origin_x = p1.x() + GRIDLINE_BUBBLE_OVERSHOOT_FRAC * length * ux
                origin_y = p1.y() + GRIDLINE_BUBBLE_OVERSHOOT_FRAC * length * uy
            else:
                ux, uy = 0.0, -1.0
                origin_x, origin_y = p1.x(), p1.y()
            # Compute angle from endpoints
            angle_rad = math.atan2(-(p2.y() - p1.y()), p2.x() - p1.x())
            angle_deg = _normalize_angle(math.degrees(angle_rad))
            kind = _classify_gridline(p1, p2)

            # Offset is applied along the perpendicular during construction
            # (ox = o·px, oy = -o·py with px = -uy, py = ux); invert by
            # projection: o = ox·px - oy·py. Canonicalize the direction to
            # the normalized 0-90° quadrant so reversed lines keep the sign.
            if ux < 0 or (ux == 0 and uy > 0):
                ux, uy = -ux, -uy
            offset = origin_x * (-uy) - origin_y * ux

            if kind == "V":
                v_rows.append((label, offset, length, angle_deg, gl))
            else:
                h_rows.append((label, offset, length, angle_deg, gl))

        if v_rows:
            self._v_tab.populate(v_rows)
        if h_rows:
            self._h_tab.populate(h_rows)

    # ── Result ────────────────────────────────────────────────────────────

    def get_gridlines(self) -> list[dict]:
        """Return combined H+V gridline specs for ``Model_Space.apply_grid_dialog()``.

        Each dict has keys: label, offset (mm), length (mm),
        angle_deg, and ``_backing`` (the original ``GridlineItem`` or
        ``None`` for new rows).
        """
        result = []

        # Vertical gridlines
        for label, offset_mm, length_mm, angle, backing, locked in self._v_tab.read_rows():
            result.append({
                "label": label,
                "offset": offset_mm,
                "length": length_mm,
                "angle_deg": angle,
                "_backing": backing,
                "locked": locked,
            })

        # Horizontal gridlines
        for label, offset_mm, length_mm, angle, backing, locked in self._h_tab.read_rows():
            result.append({
                "label": label,
                "offset": offset_mm,
                "length": length_mm,
                "angle_deg": angle,
                "_backing": backing,
                "locked": locked,
            })

        return result

    # ── Deletion confirmation ───────────────────────────────────────────

    def accept(self):
        """Confirm before deleting gridlines that were removed from tables."""
        if self._existing:
            # Collect all backing refs still present in the tables
            kept = set()
            for _, _, _, _, backing, _ in self._v_tab.read_rows():
                if backing is not None:
                    kept.add(id(backing))
            for _, _, _, _, backing, _ in self._h_tab.read_rows():
                if backing is not None:
                    kept.add(id(backing))
            deleted = [gl for gl in self._existing if id(gl) not in kept]
            if deleted:
                n = len(deleted)
                answer = QMessageBox.question(
                    self,
                    "Delete Gridlines",
                    f"{n} gridline(s) will be deleted. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return  # abort accept
        super().accept()

    def get_params(self) -> dict:
        """Backward-compat wrapper for ``main.py``."""
        return {"gridlines": self.get_gridlines()}
