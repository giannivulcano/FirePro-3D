"""
ribbon_bar.py
=============
Microsoft-style ribbon bar for FirePro 3D.

Classes
-------
RibbonButton      — large button (icon above, text below)
RibbonSmallButton — compact button (icon left, text right)
RibbonGroup       — labelled cluster of buttons with right-edge separator
RibbonPage        — one ribbon tab's content (horizontal row of groups)
RibbonBar         — full ribbon widget (tab strip + stacked pages)
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QToolButton, QLabel,
    QSizePolicy, QStackedWidget, QTabBar,
)
from PyQt6.QtGui import QIcon, QFont, QPainter, QColor
from PyQt6.QtCore import Qt, QSize
from . import theme as th


# ─────────────────────────────────────────────────────────────────────────────
# Stylesheet (kept for reference; actual QSS now comes from theme.py)
# ─────────────────────────────────────────────────────────────────────────────

RIBBON_QSS = """
RibbonBar {
    background: #f0f0f0;
    border-bottom: 1px solid #b0b0b0;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background: #dcdcdc;
    color: #333333;
    padding: 6px 24px;
    border: 1px solid #b8b8b8;
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    font-size: 10pt;
    font-weight: bold;
    min-width: 90px;
}
QTabBar::tab:selected {
    background: #f0f0f0;
    color: #1a1a8c;
    border-bottom: 2px solid #f0f0f0;
}
QTabBar::tab:hover:!selected {
    background: #e4e4e4;
}
RibbonButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 3px 6px;
    font-size: 9pt;
    color: #222222;
    text-align: center;
}
RibbonButton:hover {
    background: #cce4f7;
    border-color: #99c9f0;
}
RibbonButton:pressed {
    background: #99c9f0;
}
RibbonButton:checked {
    background: #bdd7ee;
    border-color: #6aafe6;
}
RibbonButton:disabled {
    color: #aaaaaa;
}
RibbonButton::menu-button {
    border: none;
    background: transparent;
}
RibbonButton::menu-indicator {
    subcontrol-position: bottom right;
    subcontrol-origin: padding;
    width: 10px;
    height: 8px;
    bottom: 12px;
    right: 4px;
}
RibbonSmallButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 2px 6px;
    font-size: 9pt;
    color: #222222;
    text-align: left;
}
RibbonSmallButton:hover {
    background: #cce4f7;
    border-color: #99c9f0;
}
RibbonSmallButton:pressed {
    background: #99c9f0;
}
RibbonSmallButton:checked {
    background: #bdd7ee;
    border-color: #6aafe6;
}
RibbonSmallButton:disabled {
    color: #aaaaaa;
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Buttons
# ─────────────────────────────────────────────────────────────────────────────

class RibbonButton(QToolButton):
    """Large ribbon button: 54×54 px icon with text label beneath."""

    def __init__(self, text: str, icon: QIcon | None = None, parent=None):
        super().__init__(parent)
        self.setText(text)
        if icon:
            self.setIcon(icon)
        self.setIconSize(QSize(54, 54))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFixedHeight(111)
        self.setMinimumWidth(81)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)


class RibbonSmallButton(QToolButton):
    """Compact ribbon button: 27×27 px icon with text beside it."""

    def __init__(self, text: str, icon: QIcon | None = None, parent=None):
        super().__init__(parent)
        self.setText(text)
        if icon:
            self.setIcon(icon)
        self.setIconSize(QSize(27, 27))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setFixedHeight(33)
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)


# ─────────────────────────────────────────────────────────────────────────────
# Group
# ─────────────────────────────────────────────────────────────────────────────

class RibbonGroup(QWidget):
    """
    A labelled cluster of ribbon buttons.

    Large buttons sit side-by-side.  Small buttons are stacked in vertical
    columns of up to 3 inside the same horizontal row.

    Usage
    -----
    btn  = group.add_large_button("Open",  icon, callback)
    sbtn = group.add_small_button("Undo",  icon, callback)
    mbtn = group.add_large_menu_button("Units", icon, menu)
    smbtn= group.add_small_menu_button("Precision", icon, menu)
    """

    _MAX_SMALL_PER_COL = 3

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._small_col_widget: QWidget | None = None
        self._small_col_layout: QVBoxLayout | None = None
        self._small_count = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 0)
        outer.setSpacing(0)

        # Row that holds large buttons and small-button column stacks
        self._btn_row = QHBoxLayout()
        self._btn_row.setContentsMargins(0, 0, 0, 0)
        self._btn_row.setSpacing(2)
        outer.addLayout(self._btn_row)
        outer.addStretch(1)

        # Group label — pushed to bottom by stretch (aligns across groups of different heights)
        _t = th.detect()
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = QFont()
        f.setPointSizeF(9.0)
        lbl.setFont(f)
        lbl.setStyleSheet(f"color: {_t.text_primary}; padding: 0px 0 1px 0;")
        outer.addWidget(lbl)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _flush_small_col(self):
        """Force the next small button into a new column."""
        self._small_col_widget = None
        self._small_col_layout = None
        self._small_count = 0

    def _ensure_small_col(self) -> QVBoxLayout:
        """Return the current small-button column layout, creating one if full."""
        if (self._small_col_widget is None
                or self._small_count >= self._MAX_SMALL_PER_COL):
            col = QWidget()
            col_lay = QVBoxLayout(col)
            col_lay.setContentsMargins(0, 0, 0, 0)
            col_lay.setSpacing(1)
            col_lay.addStretch()
            self._btn_row.addWidget(col)
            self._small_col_widget = col
            self._small_col_layout = col_lay
            self._small_count = 0
        return self._small_col_layout

    @staticmethod
    def _wire(btn: QToolButton, callback, checkable: bool):
        if checkable:
            btn.setCheckable(True)
        if callback is not None:
            if checkable:
                btn.toggled.connect(callback)
            else:
                btn.clicked.connect(callback)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_large_button(
        self,
        text: str,
        icon: QIcon | None,
        callback,
        *,
        checkable: bool = False,
        shortcut: str | None = None,
    ) -> RibbonButton:
        """Add a large (icon-above-text) button to the group."""
        # Large buttons must not merge into an open small-button column
        self._flush_small_col()
        btn = RibbonButton(text, icon, self)
        self._wire(btn, callback, checkable)
        if shortcut:
            btn.setShortcut(shortcut)
        self._btn_row.addWidget(btn)
        return btn

    def add_large_menu_button(
        self,
        text: str,
        icon: QIcon | None,
        menu,
    ) -> RibbonButton:
        """Add a large button that opens a QMenu instantly on click."""
        self._flush_small_col()
        btn = RibbonButton(text, icon, self)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_row.addWidget(btn)
        return btn

    def add_small_button(
        self,
        text: str,
        icon: QIcon | None,
        callback,
        *,
        checkable: bool = False,
    ) -> RibbonSmallButton:
        """Add a compact (icon-beside-text) button, stacked vertically in a column."""
        col_lay = self._ensure_small_col()
        btn = RibbonSmallButton(text, icon, self)
        self._wire(btn, callback, checkable)
        # Insert before the trailing stretch
        col_lay.insertWidget(col_lay.count() - 1, btn)
        self._small_count += 1
        return btn

    def add_small_menu_button(
        self,
        text: str,
        icon: QIcon | None,
        menu,
    ) -> RibbonSmallButton:
        """Add a compact button that opens a QMenu instantly on click."""
        col_lay = self._ensure_small_col()
        btn = RibbonSmallButton(text, icon, self)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        col_lay.insertWidget(col_lay.count() - 1, btn)
        self._small_count += 1
        return btn

    # ── Right-edge group separator ────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setPen(QColor(th.detect().border_subtle))
        p.drawLine(self.width() - 1, 4, self.width() - 1, self.height() - 20)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────

class RibbonPage(QWidget):
    """One tab's content — a horizontal row of RibbonGroups."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 0, 4, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch()

    def add_group(self, title: str) -> RibbonGroup:
        """Create and return a new RibbonGroup appended to this page."""
        grp = RibbonGroup(title, self)
        # Insert before the trailing stretch
        self._layout.insertWidget(self._layout.count() - 1, grp)
        return grp


# ─────────────────────────────────────────────────────────────────────────────
# RibbonBar
# ─────────────────────────────────────────────────────────────────────────────

class RibbonBar(QWidget):
    """
    Full ribbon widget: a QTabBar on top and a QStackedWidget of RibbonPages
    below.  Fixed total height keeps the ribbon compact.

    Usage
    -----
    ribbon = RibbonBar(parent)
    page   = ribbon.add_page("Model")
    group  = page.add_group("Draw")
    group.add_large_button("Pipe", pipe_icon, callback)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Apply theme-aware stylesheet (auto-detects dark/light from system palette)
        _t = th.detect()
        self.setStyleSheet(th.build_ribbon_qss(_t))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Tab strip
        self._tab_bar = QTabBar(self)
        self._tab_bar.setExpanding(False)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        outer.addWidget(self._tab_bar)

        # Stacked pages (one per tab)
        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet(f"background: {_t.bg_raised};")
        self._stack.setFixedHeight(150)
        outer.addWidget(self._stack)

    def _on_tab_changed(self, index: int):
        self._stack.setCurrentIndex(index)

    def add_page(self, title: str) -> RibbonPage:
        """Add a new tab with the given title and return its RibbonPage."""
        page = RibbonPage(self._stack)
        self._stack.addWidget(page)
        self._tab_bar.addTab(title)
        return page
