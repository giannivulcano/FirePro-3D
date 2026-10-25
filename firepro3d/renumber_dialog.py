"""Renumber dialog (SB2b; element-parameters.md Marks M12/M13/M19; mockup surface 2).

A house dialog: pick a category and scope, preview Old -> New per level, OK
applies the result as one undo step (``marks.apply_marks``).
"""
from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QRadioButton, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import marks
from .house_dialog import HouseDialog
from .theme import FONT_VALUE, detect

_CHANGED_ROLE = Qt.ItemDataRole.UserRole + 1     # row's Mark changes
_BLANK = "(blank)"
_GRID_PATTERN_TEXT = "(1,2,3 vertical / A,B,C horizontal)"
_ROW_H = 30                                       # mockup slider default
_TABLE_MAX_H = 260                                # mockup .scr max-height
_THUMB_W, _THUMB_H = 170, 86


def _soft(hex_colour: str, alpha: int) -> QColor:
    c = QColor(hex_colour)
    c.setAlpha(alpha)
    return c


class _RowDelegate(QStyledItemDelegate):
    """Tints changed rows (QSS ``::item`` overrides ``setBackground``)."""

    def paint(self, painter, option, index):
        if index.data(_CHANGED_ROLE):
            painter.fillRect(option.rect, _soft(detect().accent, 34))
        super().paint(painter, option, index)


class _OrderThumb(QWidget):
    """Per-level order thumbnail: numbered dots at the elements' plan positions."""

    def __init__(self, points: list, parent=None):
        super().__init__(parent)
        self._points = points                 # [(x, y)] in new-Mark order
        self.setFixedSize(QSize(_THUMB_W, _THUMB_H))

    def paintEvent(self, _event) -> None:
        t = detect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(t.sunken))
        pen = QPen(QColor(t.line_strong))
        p.setPen(pen)
        p.drawRoundedRect(QRectF(0.5, 0.5, _THUMB_W - 1, _THUMB_H - 1), 4, 4)
        if self._points:
            xs = [q[0] for q in self._points]
            ys = [q[1] for q in self._points]
            x0, y0 = min(xs), min(ys)
            sx = max(max(xs) - x0, 1e-9)
            sy = max(max(ys) - y0, 1e-9)
            font = QFont()
            font.setPixelSize(9)
            p.setFont(font)
            for i, (x, y) in enumerate(self._points, 1):
                cx = 12 + ((x - x0) / sx if max(xs) > x0 else 0.5) * (_THUMB_W - 24)
                cy = 12 + ((y - y0) / sy if max(ys) > y0 else 0.5) * (_THUMB_H - 24)
                p.setBrush(_soft(t.accent, 56))
                p.setPen(QPen(QColor(t.accent)))
                p.drawEllipse(QRectF(cx - 8, cy - 8, 16, 16))
                p.setPen(QPen(QColor(t.ink)))
                p.drawText(QRectF(cx - 8, cy - 8, 16, 16), Qt.AlignmentFlag.AlignCenter, str(i))
        p.end()


class RenumberDialog(HouseDialog):
    """Pick a category and scope, preview Old -> New, OK applies as one undo step."""

    def __init__(self, scene, parent=None):
        super().__init__(parent, title="Renumber", resizable=False,
                         icon="renumber_icon.svg")
        self.setFixedWidth(560)
        self._scene = scene
        self._mapping: dict = {}
        self._rows: list = []
        mono = QFont(FONT_VALUE)

        body = QWidget(objectName="renumberBody")
        body.setStyleSheet("#renumberBody, #thumbs, #thumbCell, QRadioButton { background: transparent; }")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(16)
        grid.setColumnMinimumWidth(0, 90)
        grid.setColumnStretch(1, 1)

        self._cat = QComboBox()
        self._cat.addItems(list(marks.RENUMBER_CATEGORIES))
        self._cat.setFixedWidth(200)
        grid.addWidget(QLabel("Category"), 0, 0)
        grid.addWidget(self._cat, 0, 1, Qt.AlignmentFlag.AlignLeft)

        scope_col = QVBoxLayout()
        scope_col.setSpacing(6)
        self._scope_group = QButtonGroup(self)
        self._r_project = QRadioButton("Whole project")
        self._r_project.setChecked(True)
        self._r_selected = QRadioButton("Selected elements")
        self._r_level = QRadioButton("Level")
        self._level = QComboBox()
        lm = getattr(scene, "_level_manager", None)
        for lvl in (lm.levels if lm is not None else []):
            label = f"{lvl.name} (No. {lvl.number})" if lvl.number else lvl.name
            self._level.addItem(label, lvl.name)
        for i, rb in enumerate((self._r_project, self._r_selected, self._r_level)):
            self._scope_group.addButton(rb, i)
        scope_col.addWidget(self._r_project)
        scope_col.addWidget(self._r_selected)
        level_row = QHBoxLayout()
        level_row.setSpacing(6)
        level_row.addWidget(self._r_level)
        level_row.addWidget(self._level)
        level_row.addStretch(1)
        scope_col.addLayout(level_row)
        scope_lbl = QLabel("Scope")
        grid.addWidget(scope_lbl, 1, 0, Qt.AlignmentFlag.AlignTop)
        grid.addLayout(scope_col, 1, 1)

        self._pattern = QLineEdit()
        self._pattern.setEnabled(False)
        self._pattern.setFont(mono)
        note = QLabel("from Project Settings \u203a Marks")
        note.setProperty("role", "muted")
        prow = QHBoxLayout()
        prow.setSpacing(8)
        prow.addWidget(self._pattern)
        prow.addWidget(note)
        prow.addStretch(1)
        grid.addWidget(QLabel("Pattern"), 2, 0)
        grid.addLayout(prow, 2, 1)
        v.addLayout(grid)

        v.addSpacing(6)
        checks = QVBoxLayout()
        checks.setSpacing(6)
        self._restart = QCheckBox("Restart on each level")
        self._keep = QCheckBox("Keep current order, just close gaps")
        checks.addWidget(self._restart)
        checks.addWidget(self._keep)
        v.addLayout(checks)
        v.addSpacing(10)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Level", "Old", "New"])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        hh.setFixedHeight(26)
        self._table.setColumnWidth(0, 90)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(_ROW_H)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setItemDelegate(_RowDelegate(self._table))
        v.addWidget(self._table)

        self._summary = QLabel("")
        self._summary.setProperty("role", "muted")
        v.addSpacing(8)
        v.addWidget(self._summary)

        self._thumbs = QWidget(objectName="thumbs")
        self._thumb_lay = QGridLayout(self._thumbs)
        self._thumb_lay.setContentsMargins(0, 8, 0, 0)
        self._thumb_lay.setSpacing(8)
        self._thumb_lay.setColumnStretch(3, 1)
        v.addWidget(self._thumbs)

        self.set_body(body)
        self._ok = self.set_footer_buttons(primary=("OK", self.accept), cancel=True)["primary"]

        self._cat.currentTextChanged.connect(self.set_category)
        self._scope_group.idToggled.connect(lambda *_: self._refresh())
        self._level.activated.connect(self._on_level_picked)
        self._restart.toggled.connect(lambda *_: self._refresh())
        self._keep.toggled.connect(lambda *_: self._refresh())
        self.set_category(self._cat.currentText())

    # -- public / test seams ---------------------------------------------------
    def set_category(self, category: str) -> None:
        if self._cat.currentText() != category:
            self._cat.setCurrentText(category)       # re-enters via currentTextChanged
            return
        grid = category == "Gridline"
        pat = "" if grid else marks.patterns(self._scene).get(category, "")
        self._pattern.setText(_GRID_PATTERN_TEXT if grid else pat)
        self._pattern.setFixedWidth(300 if grid else 200)
        has_level = "{level}" in pat
        self._restart.blockSignals(True)
        self._restart.setEnabled(has_level and not grid)
        self._restart.setChecked(has_level and not grid)
        self._restart.setToolTip(
            "Gridlines are numbered by orientation" if grid else
            "" if has_level else "Enabled only when the pattern contains {level}")
        self._restart.blockSignals(False)
        self._keep.setEnabled(not grid)
        if grid:
            self._keep.blockSignals(True)
            self._keep.setChecked(False)
            self._keep.blockSignals(False)
        # Gridlines are numbered as one project-wide set: only Whole project applies
        self._scope_group.blockSignals(True)
        if grid:
            self._r_project.setChecked(True)
        self._scope_group.blockSignals(False)
        self._r_selected.setEnabled(not grid)
        self._r_level.setEnabled(not grid and self._level.count() > 0)
        self._level.setEnabled(not grid and self._level.count() > 0)
        self._refresh()

    def set_scope(self, scope: str, level_name: str | None = None) -> None:
        """Select ``"project"`` / ``"selected"`` / ``"level"`` (and the level)."""
        if level_name is not None:
            i = self._level.findData(level_name)
            if i >= 0:
                self._level.setCurrentIndex(i)
        {"project": self._r_project, "selected": self._r_selected,
         "level": self._r_level}[scope].setChecked(True)

    def current_mapping(self) -> dict:
        scope, level = self._scope()
        return marks.renumber_plan(self._scene, self._cat.currentText(), scope, level,
                                   restart_per_level=self._restart.isChecked(),
                                   keep_order=self._keep.isChecked())

    def footer_text(self) -> str:
        return self._summary.text()

    def ok_enabled(self) -> bool:
        return self._ok.isEnabled()

    def table_rows(self) -> list:
        """``[(level, old, new)]`` as displayed."""
        return list(self._rows)

    # -- internals ----------------------------------------------------------------
    def _scope(self):
        if self._cat.currentText() == "Gridline":
            return "project", None
        if self._r_selected.isChecked():
            return "selected", None
        if self._r_level.isChecked() and self._level.currentData() is not None:
            return "level", self._level.currentData()
        return "project", None

    def _on_level_picked(self, _index: int) -> None:
        self._scope_group.blockSignals(True)         # one refresh below, not one per toggle
        self._r_level.setChecked(True)               # mockup: picking a level selects the scope
        self._scope_group.blockSignals(False)
        self._refresh()

    def _blank_pattern(self) -> bool:
        return (self._cat.currentText() != "Gridline"
                and not marks.patterns(self._scene).get(self._cat.currentText(), "").strip())

    def _refresh(self) -> None:
        t = detect()
        grid = self._cat.currentText() == "Gridline"
        blank = self._blank_pattern()
        mapping = self.current_mapping()
        self._mapping = mapping
        counts = Counter(mapping.values())
        dup = {m for m, c in counts.items() if m and c > 1} if not grid else set()
        self._table.setRowCount(len(mapping))
        self._table.setFixedHeight(min(_TABLE_MAX_H, 26 + max(1, len(mapping)) * _ROW_H + 2))
        self._rows = []
        changed = 0
        mono = QFont(FONT_VALUE)
        for r, (item, new) in enumerate(mapping.items()):
            old = marks.get_mark(item)
            lvl = "-" if grid else (marks.item_level_name(item) or "")
            shown_old = old or _BLANK
            shown_new = (new or _BLANK) + ("  (duplicate)" if new in dup else "")
            is_changed = old != new
            changed += is_changed
            self._rows.append((lvl, shown_old, shown_new))
            for c, text in enumerate((lvl, shown_old, shown_new)):
                cell = QTableWidgetItem(text)
                cell.setData(_CHANGED_ROLE, is_changed)
                if c > 0:
                    cell.setFont(mono)
                if c < 2:
                    cell.setForeground(QColor(t.muted))
                else:
                    f = QFont(mono)
                    f.setBold(is_changed)
                    cell.setFont(f)
                    if new in dup:
                        cell.setForeground(QColor(t.warn))
                    elif is_changed:
                        cell.setForeground(QColor(t.accent))
                self._table.setItem(r, c, cell)
        text = f"{len(mapping)} elements, {changed} change"
        if blank:
            text += "   |   Pattern is blank: set one in Project Settings to renumber"
        self._summary.setText(text)
        self._rebuild_thumbs(mapping, grid)
        self._ok.setEnabled(not blank and changed > 0)
        if self.isVisible():
            self.adjustSize()

    def _rebuild_thumbs(self, mapping: dict, grid: bool) -> None:
        while self._thumb_lay.count():
            w = self._thumb_lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if grid:
            return
        by_level: dict = {}
        for item in mapping:                          # mapping order = renumber order
            by_level.setdefault(marks.item_level_name(item) or "", []).append(
                marks.sort_point(item))
        for i, (lvl, pts) in enumerate(by_level.items()):
            col = QVBoxLayout()
            col.setSpacing(2)
            cap = QLabel(f"{lvl}: order, top to bottom then left to right")
            cap.setProperty("role", "muted")
            cap.setWordWrap(True)
            cap.setFixedWidth(_THUMB_W)
            cell = QWidget(objectName="thumbCell")
            cell.setLayout(col)
            col.setContentsMargins(0, 0, 0, 0)
            col.addWidget(cap)
            col.addWidget(_OrderThumb(pts))
            self._thumb_lay.addWidget(cell, i // 3, i % 3, Qt.AlignmentFlag.AlignTop)

    def accept(self) -> None:
        if self._blank_pattern():
            return                                    # nothing sensible to write
        marks.apply_marks(self._scene, self.current_mapping())
        super().accept()
