"""ui_kit.py — reusable house UI components (container/chrome + thin content
API; never domain content). Styled by theme.build_dialog_qss. See
docs/specs/ui-design-system.md. Widgetization-review rule: new widgetizable UI
gets a 'promote to ui_kit?' review before being built inline."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRect, QRectF, QPointF, QSize, pyqtSignal
from PyQt6.QtGui import (QColor, QBrush, QPainter, QPen, QPolygonF, QFont,
                         QFontDatabase, QIntValidator)
from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
                             QPushButton, QButtonGroup, QSizePolicy, QTabWidget,
                             QTabBar, QStackedWidget, QComboBox, QStyledItemDelegate,
                             QLineEdit)

from .theme import M, detect as _detect


def dock_header(text: str) -> QLabel:
    """A MainWindow dock header rail — centered bold label on the body tone
    (`surface`) with a bottom divider, 33px tall so it height-aligns with the
    canvas top (tab) rail. Shared by the property panel + browser dock
    (mainwindow-chrome-revamp-stage2.md)."""
    from .theme import detect
    t = detect()
    lbl = QLabel(text)
    lbl.setFixedHeight(M.DOCK_HEADER_H)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    f = QFont()
    f.setBold(True)
    f.setPointSize(9)
    lbl.setFont(f)
    lbl.setStyleSheet(
        f"background: {t.surface}; color: {t.ink};"
        f" border-bottom: 1px solid {t.line_strong};")
    return lbl


def browser_tree_qss() -> str:
    """Shared QSS for the MainWindow browser trees (project/model/feature/blocks):
    surface bg, no frame, rounded accent-soft hover, and a selected state that
    stays highlighted (accent_soft2) with accent text + a 1px accent outline
    (mainwindow-chrome-revamp-stage2.md). Item reserves a 1px transparent border
    so the selected outline adds no layout shift."""
    from .theme import detect
    from .assets import asset_path
    t = detect()
    chev_r = asset_path("chevron_right.svg").replace("\\", "/")
    chev_d = asset_path("chevron_down.svg").replace("\\", "/")
    return (
        f"QTreeWidget {{ background: {t.surface}; color: {t.ink};"
        f" border: none; outline: none;"
        f" selection-background-color: transparent; selection-color: {t.accent}; }}"
        f"QTreeWidget::item {{ border: 1px solid transparent; border-radius: 10px;"
        f" padding: 4px 6px; }}"
        f"QTreeWidget::item:hover:!selected {{ background: {t.accent_soft}; }}"
        f"QTreeWidget::item:selected {{ background: {t.accent_soft2};"
        f" color: {t.accent}; border: 1px solid {t.accent}; }}"
        # Branch cells painted OPAQUE surface so the row-selection fill never
        # shows in the indent (the "box + bar to the left"); chevron images keep
        # the native expand/collapse arrows (project_qtreeview_branch_styling_kills_arrows).
        f"QTreeWidget::branch {{ background: {t.surface}; }}"
        f"QTreeWidget::branch:has-children:!has-siblings:closed,"
        f"QTreeWidget::branch:closed:has-children:has-siblings {{"
        f" background: {t.surface}; image: url('{chev_r}'); }}"
        f"QTreeWidget::branch:open:has-children:!has-siblings,"
        f"QTreeWidget::branch:open:has-children:has-siblings {{"
        f" background: {t.surface}; image: url('{chev_d}'); }}"
    )


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

    def __init__(self, parent=None):
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
        self._divider.setFixedHeight(M.SEAM)
        self._divider.setStyleSheet(f"background: {detect().line_strong};")
        self._stack = QStackedWidget()
        # The tab BAR is inset by *page_inset*; the stack is FULL-BLEED (0
        # horizontal) so a page that leads with a rail can sit flush-left like
        # the main dialog rail — each page owns its own content padding. Only
        # *page_top* is applied (breathing room below the divider so Section
        # overline labels don't crowd the tab ribbon). The divider is full-bleed.
        _bar_row = QWidget(objectName="topTabsBarRow")
        _bl = QHBoxLayout(_bar_row)
        _bl.setContentsMargins(M.TOPTABS_BAR_INSET, 0, M.TOPTABS_BAR_INSET, 0)
        _bl.setSpacing(0)
        _bl.addWidget(self._bar)
        _bl.addStretch(1)
        _stack_row = QWidget(objectName="topTabsStackRow")
        self._stack.setObjectName("topTabsStack")
        _sl = QVBoxLayout(_stack_row)
        _sl.setContentsMargins(0, M.TOPTABS_PAGE_TOP, 0, 0)
        _sl.setSpacing(0)
        _sl.addWidget(self._stack)
        v.addWidget(_bar_row)
        v.addWidget(self._divider)      # full-bleed
        v.addWidget(_stack_row, 1)
        # Paint the container + rows/stack the OPAQUE dialog surface (targeted
        # selectors so nothing bleeds onto child controls). Opaque `surface`
        # (not transparent) is required because unstyled QStackedWidget/QWidget
        # paint BLACK when shown live (project trap: unstyled_qwidget_black_live);
        # add_tab() pins each page the same way.
        from .theme import detect as _detect
        _s = _detect().surface
        self.setStyleSheet(
            f"QWidget#topTabs, QWidget#topTabsBarRow, QWidget#topTabsStackRow,"
            f" QStackedWidget#topTabsStack {{ background: {_s}; }}")
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
        # Pin the page to the OPAQUE dialog surface (unstyled QStackedWidget
        # pages render BLACK live — project trap; transparent does NOT fix it,
        # an opaque bg is required). Targeted objectName selector so it never
        # bleeds onto child controls.
        from .theme import detect as _detect
        name = widget.objectName() or f"topTabsPage{len(self._keys)}"
        widget.setObjectName(name)
        prior = widget.styleSheet()
        rule = f"QWidget#{name} {{ background: {_detect().surface}; }}"
        widget.setStyleSheet(f"{prior}\n{rule}" if prior else rule)
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


class _WestTabBar(QTabBar):
    """West ``QTabBar`` that paints the selection accent bar itself.

    A QSS ``border-right`` on a rotated (West) tab is unreliable — it maps to a
    physical edge after rotation and often doesn't render — so the 2px accent
    side-bar (the selection marker, on the content-facing right edge) is drawn
    directly over the styled tab. Fill + 1px outline still come from QSS.
    """
    _BAR_W = 2

    def paintEvent(self, e):
        super().paintEvent(e)
        i = self.currentIndex()
        if i < 0:
            return
        from .theme import detect
        r = self.tabRect(i)
        # Draw at the WIDGET's right edge, not tabRect.right(): a West tab's
        # natural width can exceed the fixed strip width (M.LEFT_TAB_W), so the
        # tab rect overflows into the clipped region and a bar drawn there is
        # off-screen (confirmed via render diagnostic).
        x = self.width() - self._BAR_W
        # Trim the bar by the inter-tab gap so it doesn't overshoot into the
        # margin-bottom space below the tab (tabRect includes that gap).
        bar = QRect(x, r.top(), self._BAR_W, r.height() - M.LEFT_TAB_GAP)
        p = QPainter(self)
        p.fillRect(bar, QColor(detect().accent))
        p.end()


class LeftTabs(QWidget):
    """House left-edge vertical-tab strip — TopTabs rotated to the West edge.

    Composed of a ``QTabBar`` (RoundedWest → Qt rotates the labels to read
    bottom-to-top, matching the ribbon group labels) + a vertical ``line_strong``
    divider + a ``QStackedWidget``. Styled ``#leftTabsBar`` via
    ``theme._tab_language_qss(edge="right")`` (2px accent side-bar on select).
    Same key-based + QTabWidget-compatible API as :class:`TopTabs`; a drop-in for
    the browser dock's West ``QTabWidget``. Text-only (no icons).
    """
    tabSelected = pyqtSignal(str)
    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("leftTabs")
        # WA_StyledBackground so the surface bg paints live (plain-QWidget QSS
        # background trap: unstyled_qwidget_black_live).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(M.LEFT_TAB_INSET, 0, 0, 0)  # small gap: strip ← dock edge
        h.setSpacing(0)
        self._bar = _WestTabBar(objectName="leftTabsBar")
        self._bar.setShape(QTabBar.Shape.RoundedWest)
        self._bar.setDrawBase(False)
        self._bar.setExpanding(False)
        self._bar.setUsesScrollButtons(False)
        self._bar.setElideMode(Qt.TextElideMode.ElideNone)
        self._bar.setFixedWidth(M.LEFT_TAB_W)
        from .theme import detect
        self._divider = QFrame()
        self._divider.setFixedWidth(M.SEAM)
        self._divider.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._divider.setStyleSheet(f"background: {detect().line_strong};")
        self._stack = QStackedWidget()
        # Opaque surface so unstyled stacked pages don't paint black live
        # (project trap: unstyled_qwidget_black_live).
        self._stack.setObjectName("leftTabsStack")
        _s = detect().surface
        self.setStyleSheet(
            f"QWidget#leftTabs, QStackedWidget#leftTabsStack {{ background: {_s}; }}")
        # Pin the bar to the TOP: a West QTabBar sizes to its tab content height,
        # so without an alignment flag the layout vertically centres the short
        # bar. AlignTop justifies the tabs to the top; the divider + stack keep
        # the full row height (no alignment flag).
        h.addWidget(self._bar, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(self._divider)
        h.addWidget(self._stack, 1)
        self._keys: list[str] = []
        self._bar.currentChanged.connect(self._on_current)

    def _on_current(self, idx):
        self._stack.setCurrentIndex(idx)
        self.currentChanged.emit(idx)
        if 0 <= idx < len(self._keys):
            self.tabSelected.emit(self._keys[idx])

    def addTab(self, widget, label, *, key=None, icon=None):
        """Add a page. ``key`` defaults to ``label`` (QTabWidget-compat call form
        ``addTab(widget, label)`` works directly)."""
        if icon is None:
            self._bar.addTab(label)
        else:
            self._bar.addTab(icon, label)
        from .theme import detect
        name = widget.objectName() or f"leftTabsPage{len(self._keys)}"
        widget.setObjectName(name)
        prior = widget.styleSheet()
        rule = f"QWidget#{name} {{ background: {detect().surface}; }}"
        widget.setStyleSheet(f"{prior}\n{rule}" if prior else rule)
        self._stack.addWidget(widget)
        self._keys.append(key if key is not None else label)
        return len(self._keys) - 1

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


class _FontPreviewDelegate(QStyledItemDelegate):
    """Paints the family name (default) plus an 'AaBb 0123' preview in that face."""
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        fam = index.data(FontSelect.ROLE_FAMILY)
        if not fam:
            return
        painter.save()
        f = QFont(fam)
        if option.font.pointSize() > 0:
            f.setPointSize(option.font.pointSize())
        painter.setFont(f)
        painter.setPen(option.palette.text().color())
        r = option.rect.adjusted(0, 0, -8, 0)
        painter.drawText(r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         "AaBb 0123")
        painter.restore()

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), 22))


class FontSelect(QComboBox):
    """Reusable font picker: TrueType families with an SHX-ready source seam,
    in-face previews, type-ahead, recently-used (max 5), and a current checkmark.

    Emits ``fontChanged(str family)`` on an activated selection. A raw
    ``QFontComboBox`` cannot carry section headers or (later) SHX entries, so this
    is the standard replacement (ui-design-system.md). SHX support is deferred:
    the ``_sources`` list is the seam a future SHX source plugs into.
    """
    fontChanged = pyqtSignal(str)
    ROLE_FAMILY = Qt.ItemDataRole.UserRole + 1
    MAX_RECENT = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recent: list[str] = []
        self.setEditable(True)                 # enables type-ahead
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setItemDelegate(_FontPreviewDelegate(self))
        self._sources = [("TrueType", list(QFontDatabase.families()))]  # font-source seam
        self._rebuild()
        self.activated.connect(self._on_activated)

    def _add_header(self, text):
        self.addItem(text)
        item = self.model().item(self.count() - 1)   # default model is QStandardItemModel
        if item is not None:
            item.setEnabled(False)                   # section header: non-selectable

    def _add_family(self, fam):
        self.addItem(fam)
        self.setItemData(self.count() - 1, fam, self.ROLE_FAMILY)

    def _rebuild(self, current: str | None = None):
        current = current or self.current_family()
        self.blockSignals(True)
        self.clear()
        if self._recent:
            self._add_header("Recent")
            for fam in self._recent:
                self._add_family(fam)
        for label, fams in self._sources:
            self._add_header(label)
            for fam in fams:
                self._add_family(fam)
        self.blockSignals(False)
        if current:
            self.set_current_family(current)

    def current_family(self) -> str:
        return self.itemData(self.currentIndex(), self.ROLE_FAMILY) or self.currentText()

    def set_current_family(self, fam: str):
        for i in range(self.count()):
            if self.itemData(i, self.ROLE_FAMILY) == fam:
                self.setCurrentIndex(i)
                return
        self.setCurrentText(fam)                     # missing font: show the name as typed

    def recent_families(self) -> list[str]:
        return list(self._recent)

    def _pin_recent(self, fam: str):
        if fam in self._recent:
            self._recent.remove(fam)
        self._recent.insert(0, fam)
        del self._recent[self.MAX_RECENT:]

    def commit_current(self):
        """Emit fontChanged for the current family and pin it as recent."""
        fam = self.current_family()
        if not fam:
            return
        self._pin_recent(fam)
        self.fontChanged.emit(fam)

    def _on_activated(self, _index):
        fam = self.current_family()
        if not fam:
            return
        self._pin_recent(fam)
        self._rebuild(current=fam)
        self.fontChanged.emit(fam)


# ── Custom property-panel inputs ─────────────────────────────────────────────
# Fully self-painted so there is no native QComboBox/QSpinBox chrome to fight
# (arrows vanishing when styled, drop-down tone, inconsistent widths). Tuned via
# docs/mockups/selector-tuner.html: height 24, field=surface2 (window-header
# tone), 1px border, radius 4, ink triangle caret behind a 1px divider.

_SEL_H = 24
_SEL_RADIUS = 4
_CARET_W = 22
_ARROW_W = 16


class Selector(QComboBox):
    """A custom-painted dropdown. Subclasses QComboBox to keep its popup/model
    (``addItems``/``currentText``/``currentTextChanged``); only the closed-state
    paint is ours — field=surface2, 1px border, radius 4, ink triangle caret."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_SEL_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumWidth(0)
        f = self.font()
        f.setPixelSize(11)
        self.setFont(f)
        t = _detect()
        self.view().setStyleSheet(
            f"QAbstractItemView {{ background: {t.surface2}; color: {t.ink};"
            f" border: 1px solid {t.accent}; outline: none;"
            f" selection-background-color: {t.accent};"
            f" selection-color: {t.accent_ink}; }}")

    def paintEvent(self, event):
        t = _detect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(t.border_subtle), 1))
        p.setBrush(QColor(t.surface2))
        p.drawRoundedRect(r, _SEL_RADIUS, _SEL_RADIUS)
        divx = r.right() - _CARET_W
        p.drawLine(QPointF(divx, r.top() + 3), QPointF(divx, r.bottom() - 3))
        p.setPen(QColor(t.ink))
        tr = QRectF(r.left() + 6, r.top(), divx - r.left() - 10, r.height())
        txt = self.fontMetrics().elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, int(tr.width()))
        p.drawText(tr, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), txt)
        cx = divx + _CARET_W / 2
        cy = r.center().y()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.ink))
        p.drawPolygon(QPolygonF([QPointF(cx - 5, cy - 2),
                                 QPointF(cx + 5, cy - 2), QPointF(cx, cy + 3.5)]))


class _StepArrows(QWidget):
    """Two stacked triangle hit-areas (up / down) with a gap between them."""

    def __init__(self, on_step, parent=None):
        super().__init__(parent)
        self._on_step = on_step          # callable(+1 | -1)
        self.setFixedWidth(_ARROW_W)

    def paintEvent(self, event):
        t = _detect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.ink))
        cx = self.width() / 2
        h = self.height()
        up_cy, dn_cy, s = h * 0.30, h * 0.70, 5      # 40% gap between the arrows
        p.drawPolygon(QPolygonF([QPointF(cx - s, up_cy + 2.5),
                                 QPointF(cx + s, up_cy + 2.5), QPointF(cx, up_cy - 2.5)]))
        p.drawPolygon(QPolygonF([QPointF(cx - s, dn_cy - 2.5),
                                 QPointF(cx + s, dn_cy - 2.5), QPointF(cx, dn_cy + 2.5)]))

    def mousePressEvent(self, event):
        self._on_step(1 if event.position().y() < self.height() / 2 else -1)


class Stepper(QWidget):
    """A custom-painted integer stepper (drop-in for a QSpinBox in the property
    panel): field=surface2 box, editable value, spaced up/down triangles behind a
    divider. API: ``setRange``/``setMinimum``/``setMaximum``/``setValue``/
    ``value`` + ``valueChanged(int)``."""

    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_SEL_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._min, self._max, self._value = 0, 100000, 0
        t = _detect()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._edit = QLineEdit("0")
        self._edit.setFrame(False)
        self._edit.setValidator(QIntValidator(self._min, self._max, self))
        self._edit.setStyleSheet(
            f"background: transparent; border: none; color: {t.ink};"
            f" padding: 0 6px; font-size: 11px;")
        self._edit.editingFinished.connect(self._commit_edit)
        lay.addWidget(self._edit, 1)
        lay.addWidget(_StepArrows(self._step, self))

    def paintEvent(self, event):
        t = _detect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(t.border_subtle), 1))
        p.setBrush(QColor(t.surface2))
        p.drawRoundedRect(r, _SEL_RADIUS, _SEL_RADIUS)
        divx = r.right() - _ARROW_W
        p.drawLine(QPointF(divx, r.top() + 3), QPointF(divx, r.bottom() - 3))

    def setRange(self, lo, hi):
        self._min, self._max = int(lo), int(hi)
        self._edit.setValidator(QIntValidator(self._min, self._max, self))
        self.setValue(self._value)

    def setMinimum(self, lo):
        self.setRange(lo, self._max)

    def setMaximum(self, hi):
        self.setRange(self._min, hi)

    def value(self):
        return self._value

    def minimum(self):
        return self._min

    def maximum(self):
        return self._max

    def setValue(self, v):
        v = max(self._min, min(self._max, int(v)))
        changed = v != self._value
        self._value = v
        self._edit.setText(str(v))
        if changed:
            self.valueChanged.emit(v)

    def _step(self, d):
        self.setValue(self._value + d)

    def _commit_edit(self):
        try:
            self.setValue(int(self._edit.text() or 0))
        except ValueError:
            self._edit.setText(str(self._value))


class _Chip(QWidget):
    """A small painted colour chip (rounded rect + border) that emits ``clicked``."""

    clicked = pyqtSignal()

    def __init__(self, hex_color="#000000", parent=None):
        super().__init__(parent)
        self._color = hex_color
        self.setFixedSize(34, 14)          # tuner defaults
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_color(self, hex_color):
        self._color = hex_color
        self.update()

    def paintEvent(self, event):
        t = _detect()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(t.border_subtle), 1))
        p.setBrush(QColor(self._color))
        p.drawRoundedRect(r, 3, 3)

    def mousePressEvent(self, event):
        self.clicked.emit()


class Swatch(QWidget):
    """Colour picker: a painted chip + hex label. Opens QColorDialog on click and
    emits ``colorChanged(hex)``. Replaces a bare QPushButton (which picked up the
    app's global button chrome — min-height, padding, hover — and rendered wrong)."""

    colorChanged = pyqtSignal(str)

    def __init__(self, hex_color="#000000", parent=None):
        super().__init__(parent)
        self._hex = hex_color or "#000000"
        t = _detect()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)                  # tuner hex-gap
        lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._chip = _Chip(self._hex)
        self._chip.clicked.connect(self._pick)
        self._label = QLabel(self._hex.upper())
        self._label.setStyleSheet(f"color: {t.muted}; font-size: 11px;")
        lay.addWidget(self._chip)
        lay.addWidget(self._label)
        lay.addStretch(1)

    def _pick(self):
        from PyQt6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self._hex), self, "Colour")
        if c.isValid():
            self.set_hex(c.name())
            self.colorChanged.emit(c.name())

    def set_hex(self, hex_color):
        self._hex = hex_color
        self._chip.set_color(hex_color)
        self._label.setText(hex_color.upper())

    def hex(self):
        return self._hex
