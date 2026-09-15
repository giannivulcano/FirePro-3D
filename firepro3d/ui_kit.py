"""ui_kit.py — reusable house UI components (container/chrome + thin content
API; never domain content). Styled by theme.build_dialog_qss. See
docs/specs/ui-design-system.md. Widgetization-review rule: new widgetizable UI
gets a 'promote to ui_kit?' review before being built inline."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QPainter
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
                             QPushButton, QButtonGroup, QSizePolicy, QTabWidget,
                             QTabBar, QStackedWidget)

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

    def set_label(self, text):
        self._name.setText(text)

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

    def clear(self):
        """Remove every tab — for dynamic rails rebuilt when their data changes."""
        for row in list(self._rows.values()):
            self._v.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        self._current = None

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

    def set_label(self, key, text):
        row = self._rows.get(key)
        if row is not None:
            row.set_label(text)

    def set_header(self, widget):
        """Insert a header widget (e.g. action buttons) above the tab rows,
        INSIDE the rail frame (shares its background + border)."""
        self.layout().insertWidget(0, widget)


class TopTabs(QWidget):
    """House top-tab strip (peer pages inside one section; DIALOG_TABS_SPEC).

    Composed of a ``QTabBar`` + a **full-width divider** + a ``QStackedWidget``
    (the reference's design — a QTabWidget's ``::pane`` border is unreliable and
    the bar sizes to its tabs, so its own line stops short of the content width).
    Styled ``#topTabsBar`` (muted default, accent-underline + semibold selected,
    accent-soft hover) with a ``#topTabsDivider`` line under the strip. The
    key-based API mirrors SideTabs; a QTabWidget-compatible subset
    (``count``/``tabText``/``widget``/``currentWidget``/``setCurrentWidget``/
    ``currentChanged``) keeps callers + tests working. Rail → tabs is the max
    depth: never nest TopTabs.
    """
    tabSelected = pyqtSignal(str)          # key of the newly-current tab
    currentChanged = pyqtSignal(int)       # mirrors QTabWidget (index)

    def __init__(self, parent=None, *, page_inset=12):
        super().__init__(parent)
        self.setObjectName("topTabs")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self._bar = QTabBar(objectName="topTabsBar")
        self._bar.setDrawBase(False)
        self._bar.setExpanding(False)
        self._bar.setUsesScrollButtons(True)
        self._bar.setElideMode(Qt.TextElideMode.ElideNone)
        # Full-width divider under the strip. A bare stylesheet set DIRECTLY on
        # the divider paints it and beats any parent-background bleed (palette is
        # overridden by the house dialog stylesheet, so use a stylesheet here).
        from .theme import detect
        self._divider = QFrame()
        self._divider.setFixedHeight(1)
        self._divider.setStyleSheet(f"background: {detect().line_strong};")
        self._stack = QStackedWidget()
        # Tabs + pages are inset by *page_inset* so they align with padded
        # content; the divider stays FULL-BLEED to the widget's edges (so the
        # adopter zeroes its horizontal margins around TopTabs).
        _bar_row = QWidget()
        _bl = QHBoxLayout(_bar_row)
        _bl.setContentsMargins(page_inset, 0, page_inset, 0)
        _bl.setSpacing(0)
        _bl.addWidget(self._bar)
        _bl.addStretch(1)
        _stack_row = QWidget()
        _sl = QVBoxLayout(_stack_row)
        _sl.setContentsMargins(page_inset, 0, page_inset, 0)
        _sl.setSpacing(0)
        _sl.addWidget(self._stack)
        v.addWidget(_bar_row)
        v.addWidget(self._divider)      # full-bleed
        v.addWidget(_stack_row, 1)
        self._keys: list[str] = []
        self._bar.currentChanged.connect(self._on_current)

    def _on_current(self, idx):
        self._stack.setCurrentIndex(idx)
        self.currentChanged.emit(idx)
        if 0 <= idx < len(self._keys):
            self.tabSelected.emit(self._keys[idx])

    def add_tab(self, key, label, widget, *, icon=None):
        """Add a page keyed by *key*; returns the tab index."""
        if icon is None:
            self._bar.addTab(label)
        else:
            self._bar.addTab(icon, label)
        self._stack.addWidget(widget)
        self._keys.append(key)
        return len(self._keys) - 1

    # ── SideTabs-style key API ─────────────────────────────────────────────
    def set_current(self, key):
        if key in self._keys:
            self.setCurrentIndex(self._keys.index(key))

    def current(self):
        i = self.currentIndex()
        return self._keys[i] if 0 <= i < len(self._keys) else None

    # ── QTabWidget-compatible subset (callers + tests) ─────────────────────
    def tabBar(self): return self._bar
    def count(self): return self._bar.count()
    def tabText(self, i): return self._bar.tabText(i)
    def widget(self, i): return self._stack.widget(i)
    def currentIndex(self): return self._bar.currentIndex()
    def setCurrentIndex(self, i): self._bar.setCurrentIndex(i)
    def currentWidget(self): return self._stack.currentWidget()

    def setCurrentWidget(self, w):
        i = self._stack.indexOf(w)
        if i >= 0:
            self._bar.setCurrentIndex(i)


class DetailsPanel(QFrame):
    def __init__(self, *, width=M.PANEL_W, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("detailsPanel")
        self.setFixedWidth(width)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(*M.PANEL_PAGE_MARGIN)
        self._v.setSpacing(M.SECTION_GAP)
        if title is not None:
            hdr = QLabel(title.upper())
            hdr.setProperty("role", "header")
            self._v.addWidget(hdr)

    def content_layout(self):
        return self._v


class Section(QWidget):
    def __init__(self, title, content=None, parent=None):
        super().__init__(parent)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(0, 0, 0, 0)
        self._v.setSpacing(M.SECTION_GAP)
        self._hdr = QLabel(title.upper())
        self._hdr.setProperty("role", "header")
        self._v.addWidget(self._hdr)
        if content is not None:
            self._v.addWidget(content)

    def set_content(self, widget):
        self._v.addWidget(widget)


class SwitchBar(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, options, parent=None, *, expanding=True):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        self._btns = {}
        self._current = None
        n = len(options)
        pol = (QSizePolicy.Policy.Expanding if expanding
               else QSizePolicy.Policy.Preferred)
        for i, (key, label) in enumerate(options):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("switch", "true")
            b.setProperty("segpos", "left" if i == 0 else "right" if i == n - 1 else "mid")
            b.setSizePolicy(pol, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _=False, k=key: self._select(k))
            self._grp.addButton(b, i)
            h.addWidget(b)
            self._btns[key] = b
        if not expanding and self._btns:
            # Content-fit: every segment equal width = the widest label.
            w = max(b.sizeHint().width() for b in self._btns.values())
            for b in self._btns.values():
                b.setFixedWidth(w)
            h.addStretch(1)              # keep the compact switch left-aligned
        if options:
            self.set_current(options[0][0])

    def _select(self, key):
        self.set_current(key)
        self.changed.emit(key)

    def set_current(self, key):
        for k, b in self._btns.items():
            b.setChecked(k == key)
        self._current = key

    def current(self):
        return self._current


class _PaintedSwitch(QWidget):
    """iOS-style painted track + sliding knob. Theme read at paint time."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = bool(checked)
        self.setFixedSize(42, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, v: bool) -> None:
        v = bool(v)
        if v != self._checked:
            self._checked = v
            self.update()
            self.toggled.emit(v)

    def toggle(self) -> None:
        self.setChecked(not self._checked)

    def mousePressEvent(self, event):
        self.setChecked(not self._checked)
        event.accept()

    def paintEvent(self, _event):
        from .theme import detect
        t = detect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        track = QColor(t.accent if self._checked else t.line_strong)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(track))
        rad = r.height() / 2
        p.drawRoundedRect(r, rad, rad)
        d = r.height() - 4
        x = (r.right() - d - 2) if self._checked else (r.left() + 2)
        p.setBrush(QBrush(QColor(t.toggle_knob)))
        p.drawEllipse(int(x), r.top() + 2, int(d), int(d))
        p.end()


class ToggleSwitch(QWidget):
    """iOS-style painted toggle (sliding knob) + label to the right.

    Public API mirrors QCheckBox: ``isChecked()``, ``setChecked(on)``,
    ``toggled`` signal, ``text()``.
    """
    toggled = pyqtSignal(bool)

    def __init__(self, label, checked=False, parent=None):
        super().__init__(parent)
        self._label_text = label
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(M.SM)
        self._sw = _PaintedSwitch(checked=checked)
        self._sw.toggled.connect(self.toggled)
        h.addWidget(self._sw)
        h.addWidget(QLabel(label))
        h.addStretch(1)

    def isChecked(self) -> bool:
        return self._sw.isChecked()

    def setChecked(self, on: bool) -> None:
        self._sw.setChecked(on)

    def toggle(self) -> None:
        self._sw.toggle()

    def text(self) -> str:
        """Return the label text (mirrors QCheckBox.text() for compatibility)."""
        return self._label_text


class Pill(QPushButton):
    def __init__(self, text="", *, icon=None, checkable=False, expanding=False, parent=None):
        super().__init__(text, parent)
        self.setProperty("pill", "true")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon is not None:
            self.setIcon(icon)
        self.setCheckable(checkable)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding if expanding else QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed)
