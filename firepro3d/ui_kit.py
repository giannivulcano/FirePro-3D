"""ui_kit.py — reusable house UI components (container/chrome + thin content
API; never domain content). Styled by theme.build_dialog_qss. See
docs/specs/ui-design-system.md. Widgetization-review rule: new widgetizable UI
gets a 'promote to ui_kit?' review before being built inline."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
                             QPushButton, QButtonGroup, QSizePolicy)

from .theme import M


class _StepRow(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, key, label, *, icon=None, sub=None, step_no=None, parent=None):
        super().__init__(parent)
        self._key = key
        self.setProperty("stepRow", "true")
        h = QHBoxLayout(self)
        h.setContentsMargins(*M.STEP_ROW_MARGIN)
        h.setSpacing(M.STEP_ROW_GAP)
        if step_no is not None:
            self._no = QLabel(str(step_no))
            self._no.setProperty("stepNo", "true")
            self._no.setFixedSize(M.STEP_CHIP, M.STEP_CHIP)
            self._no.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.addWidget(self._no)
        else:
            self._no = None
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self._name = QLabel(label)
        self._name.setProperty("stepName", "true")
        col.addWidget(self._name)
        self._status = QLabel(sub or "")
        self._status.setProperty("stepStatus", "true")
        col.addWidget(self._status)
        h.addLayout(col)
        h.addStretch(1)

    def mousePressEvent(self, e):
        self.clicked.emit(self._key)

    def set_current(self, on):
        for w in (self, self._no):
            if w is not None:
                w.setProperty("current", "true" if on else "false")
                w.style().unpolish(w); w.style().polish(w)

    def set_status(self, text, state):
        self._status.setText(text)
        self._status.setProperty("state", state or "")
        self._status.style().unpolish(self._status); self._status.style().polish(self._status)
        if self._no is not None:
            self._no.setProperty("done", "true" if state == "done" else "false")
            self._no.setProperty("warn", "true" if state == "warn" else "false")
            self._no.style().unpolish(self._no); self._no.style().polish(self._no)


class SideTabs(QFrame):
    """Vertical exclusive tab rail. Optional numbered-step mode via step_no."""
    tabSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stepRail")
        self.setFixedWidth(M.SIDE_RAIL_W)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*M.SIDE_RAIL_MARGIN)
        inner = QFrame(objectName="stepRailInner")
        self._v = QVBoxLayout(inner)
        self._v.setContentsMargins(0, 0, 0, 0)
        self._v.setSpacing(M.SIDE_RAIL_ROW_GAP)
        outer.addWidget(inner)
        outer.addStretch(1)
        self._rows = {}
        self._current = None

    def add_tab(self, key, label, *, icon=None, sub=None, step_no=None):
        row = _StepRow(key, label, icon=icon, sub=sub, step_no=step_no)
        row.clicked.connect(self._on_click)
        self._v.addWidget(row)
        self._rows[key] = row
        if self._current is None:
            self.set_current(key)

    def _on_click(self, key):
        self.set_current(key)
        self.tabSelected.emit(key)

    def set_current(self, key):
        for k, row in self._rows.items():
            row.set_current(k == key)
        self._current = key

    def current(self):
        return self._current

    def set_status(self, key, text, state):
        self._rows[key].set_status(text, state)
