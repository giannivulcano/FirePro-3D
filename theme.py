"""
theme.py
========
Centralized dark / light theme token system for FireFlow Pro.

Every UI component — ribbon, docks, dialogs, property panels, canvas,
status bar — should derive its colors from this module.  This keeps the
visual language consistent and makes future theme changes a one-line switch.

Usage
-----
    import theme as th

    # In main():
    _t = th.detect()
    app.setStyleSheet(th.build_app_qss(_t))

    # In RibbonBar.__init__():
    self.setStyleSheet(th.build_ribbon_qss(th.detect()))

    # In Model_View.drawBackground():
    dot_color = QColor(th.detect().grid_dot)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication


# ─────────────────────────────────────────────────────────────────────────────
# Token dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Theme:
    """Immutable set of color / style tokens for one theme variant."""

    # ── Identity ──────────────────────────────────────────────────────────────
    name: str                  # "light" | "dark"

    # ── Background layers ─────────────────────────────────────────────────────
    bg_base: str               # main window, dock widget interiors
    bg_raised: str             # ribbon panel, dialog bodies, toolbar
    bg_sunken: str             # input fields, table cells

    bg_tab_inactive: str       # unselected ribbon / dialog tab
    bg_tab_selected: str       # selected tab (should merge with bg_raised)

    # ── Interactive button states ─────────────────────────────────────────────
    btn_hover: str
    btn_pressed: str
    btn_checked: str
    btn_checked_border: str

    # ── Borders & separators ──────────────────────────────────────────────────
    border_strong: str         # outer frame lines, focused input rings
    border_subtle: str         # group separators, table grid, cell dividers

    # ── Text ──────────────────────────────────────────────────────────────────
    text_primary: str          # body text, labels
    text_secondary: str        # group caption labels, placeholder text
    text_disabled: str         # disabled control text
    text_accent: str           # selected tab, links, active-mode indicator

    # ── Canvas (Model_View / Paper_View) ──────────────────────────────────────
    canvas_bg: str             # scene background fill
    grid_dot: str              # dot-grid point color

    # ── Semantic colors ───────────────────────────────────────────────────────
    accent_primary: str        # focus rings, run-hydraulics button highlight
    status_ok: str             # passed / green
    status_warn: str           # warning / orange
    status_error: str          # error / red


# ─────────────────────────────────────────────────────────────────────────────
# Preset themes
# ─────────────────────────────────────────────────────────────────────────────

LIGHT = Theme(
    name             = "light",

    bg_base          = "#f5f5f5",
    bg_raised        = "#f0f0f0",
    bg_sunken        = "#ffffff",
    bg_tab_inactive  = "#dcdcdc",
    bg_tab_selected  = "#f0f0f0",

    btn_hover        = "#cce4f7",
    btn_pressed      = "#99c9f0",
    btn_checked      = "#bdd7ee",
    btn_checked_border = "#6aafe6",

    border_strong    = "#b0b0b0",
    border_subtle    = "#c8c8c8",

    text_primary     = "#222222",
    text_secondary   = "#555555",
    text_disabled    = "#aaaaaa",
    text_accent      = "#1a1a8c",

    canvas_bg        = "#ffffff",
    grid_dot         = "#cccccc",

    accent_primary   = "#0078d4",
    status_ok        = "#217346",
    status_warn      = "#b46500",
    status_error     = "#c42b1c",
)

DARK = Theme(
    name             = "dark",

    bg_base          = "#1e1e1e",
    bg_raised        = "#2b2b2b",
    bg_sunken        = "#1a1a1a",
    bg_tab_inactive  = "#333333",
    bg_tab_selected  = "#2b2b2b",

    btn_hover        = "#3a5a78",
    btn_pressed      = "#2d4a66",
    btn_checked      = "#1f4060",
    btn_checked_border = "#4fa3e0",

    border_strong    = "#555555",
    border_subtle    = "#444444",

    text_primary     = "#e0e0e0",
    text_secondary   = "#999999",
    text_disabled    = "#555555",
    text_accent      = "#4fa3e0",

    canvas_bg        = "#1e1e1e",
    grid_dot         = "#3a3a3a",

    accent_primary   = "#4fa3e0",
    status_ok        = "#4caf50",
    status_warn      = "#ffb74d",
    status_error     = "#ef5350",
)


# ─────────────────────────────────────────────────────────────────────────────
# Auto-detect
# ─────────────────────────────────────────────────────────────────────────────

def detect() -> Theme:
    """Return DARK or LIGHT by inspecting the application window palette."""
    pal = QApplication.palette()
    lum = pal.color(QPalette.ColorRole.Window).lightness()
    return DARK if lum < 128 else LIGHT


# ─────────────────────────────────────────────────────────────────────────────
# QSS builders
# ─────────────────────────────────────────────────────────────────────────────

def build_app_qss(t: Theme) -> str:
    """Return a global application QSS stylesheet from the given theme tokens.

    Applied once in main() via ``app.setStyleSheet(build_app_qss(t))``.
    All QSS here uses standard Qt widget selectors so it applies uniformly
    to every widget without needing per-widget stylesheets.
    """
    return f"""
/* ── Window & generic widgets ──────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background: {t.bg_base};
    color: {t.text_primary};
}}

/* ── Dock widgets ───────────────────────────────────────────────────────── */
QDockWidget {{
    background: {t.bg_raised};
    color: {t.text_primary};
    titlebar-close-icon: none;
}}
QDockWidget::title {{
    background: {t.bg_tab_inactive};
    color: {t.text_primary};
    padding: 5px 8px;
    border-bottom: 1px solid {t.border_strong};
    font-weight: bold;
    font-size: 8pt;
}}
QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: none;
}}

/* ── Menu bar ───────────────────────────────────────────────────────────── */
QMenuBar {{
    background: {t.bg_raised};
    color: {t.text_primary};
    border-bottom: 1px solid {t.border_strong};
    padding: 1px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background: {t.btn_hover};
    border-radius: 2px;
}}

/* ── Menus ──────────────────────────────────────────────────────────────── */
QMenu {{
    background: {t.bg_raised};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    padding: 2px;
}}
QMenu::item {{
    padding: 4px 20px 4px 8px;
    border-radius: 2px;
}}
QMenu::item:selected {{
    background: {t.btn_hover};
}}
QMenu::separator {{
    height: 1px;
    background: {t.border_subtle};
    margin: 3px 4px;
}}

/* ── Status bar ─────────────────────────────────────────────────────────── */
QStatusBar {{
    background: {t.bg_raised};
    color: {t.text_secondary};
    border-top: 1px solid {t.border_strong};
}}

/* ── Tables ─────────────────────────────────────────────────────────────── */
QTableWidget, QTableView {{
    background: {t.bg_sunken};
    color: {t.text_primary};
    gridline-color: {t.border_subtle};
    alternate-background-color: {t.bg_raised};
    border: 1px solid {t.border_strong};
    selection-background-color: {t.btn_checked};
    selection-color: {t.text_primary};
}}
QHeaderView::section {{
    background: {t.bg_raised};
    color: {t.text_primary};
    border: 1px solid {t.border_subtle};
    padding: 3px 6px;
    font-weight: bold;
    font-size: 8pt;
}}
QHeaderView::section:checked {{
    background: {t.btn_checked};
}}

/* ── Input controls ─────────────────────────────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background: {t.bg_sunken};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    border-radius: 2px;
    padding: 2px 4px;
    selection-background-color: {t.btn_checked};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {t.accent_primary};
}}
QLineEdit:disabled, QSpinBox:disabled {{
    color: {t.text_disabled};
    background: {t.bg_raised};
}}

/* ── ComboBox ───────────────────────────────────────────────────────────── */
QComboBox {{
    background: {t.bg_sunken};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    border-radius: 2px;
    padding: 2px 4px;
}}
QComboBox:focus {{
    border-color: {t.accent_primary};
}}
QComboBox QAbstractItemView {{
    background: {t.bg_raised};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    selection-background-color: {t.btn_checked};
}}
QComboBox::drop-down {{
    border-left: 1px solid {t.border_strong};
    background: {t.bg_raised};
    width: 18px;
}}

/* ── Buttons ────────────────────────────────────────────────────────────── */
QPushButton {{
    background: {t.bg_raised};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    border-radius: 3px;
    padding: 4px 12px;
    min-height: 22px;
}}
QPushButton:hover {{
    background: {t.btn_hover};
}}
QPushButton:pressed {{
    background: {t.btn_pressed};
}}
QPushButton:checked {{
    background: {t.btn_checked};
    border-color: {t.btn_checked_border};
}}
QPushButton:disabled {{
    color: {t.text_disabled};
    background: {t.bg_raised};
    border-color: {t.border_subtle};
}}
QPushButton:default {{
    border-color: {t.accent_primary};
}}

/* ── Checkboxes & radio buttons ─────────────────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {t.text_primary};
    spacing: 5px;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {t.text_disabled};
}}

/* ── Tab widgets (dialogs, docks — NOT the ribbon) ──────────────────────── */
QTabWidget::pane {{
    border: 1px solid {t.border_strong};
    background: {t.bg_raised};
}}
QTabBar::tab {{
    background: {t.bg_tab_inactive};
    color: {t.text_primary};
    padding: 4px 12px;
    border: 1px solid {t.border_strong};
    border-bottom: none;
    border-top-left-radius: 2px;
    border-top-right-radius: 2px;
}}
QTabBar::tab:selected {{
    background: {t.bg_raised};
    color: {t.text_accent};
}}
QTabBar::tab:hover:!selected {{
    background: {t.btn_hover};
}}

/* ── Scroll bars ────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t.bg_base};
    width: 10px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {t.border_strong};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.text_secondary};
}}
QScrollBar:horizontal {{
    background: {t.bg_base};
    height: 10px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {t.border_strong};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}

/* ── Splitters ──────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {t.border_subtle};
}}

/* ── Labels ─────────────────────────────────────────────────────────────── */
QLabel {{
    color: {t.text_primary};
    background: transparent;
}}

/* ── Group boxes ────────────────────────────────────────────────────────── */
QGroupBox {{
    color: {t.text_primary};
    border: 1px solid {t.border_subtle};
    border-radius: 3px;
    margin-top: 10px;
    padding-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    color: {t.text_secondary};
    font-size: 8pt;
}}

/* ── Tool tips ──────────────────────────────────────────────────────────── */
QToolTip {{
    background: {t.bg_raised};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    padding: 3px 6px;
}}

/* ── Dialog button boxes ────────────────────────────────────────────────── */
QDialogButtonBox QPushButton {{
    min-width: 70px;
}}
"""


def build_ribbon_qss(t: Theme) -> str:
    """Return ribbon-specific QSS that overrides the app-level tab styling
    so the ribbon tabs sit flush against the ribbon panel without a pane border.
    """
    return f"""
RibbonBar {{
    background: {t.bg_raised};
    border-bottom: 1px solid {t.border_strong};
}}
/* Ribbon uses its own QTabBar — override the generic tab style */
RibbonBar QTabBar {{
    background: transparent;
}}
RibbonBar QTabBar::tab {{
    background: {t.bg_tab_inactive};
    color: {t.text_primary};
    padding: 5px 20px;
    border: 1px solid {t.border_strong};
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    font-size: 9pt;
    font-weight: bold;
    min-width: 80px;
}}
RibbonBar QTabBar::tab:selected {{
    background: {t.bg_tab_selected};
    color: {t.text_accent};
    border-bottom: 2px solid {t.bg_tab_selected};
}}
RibbonBar QTabBar::tab:hover:!selected {{
    background: {t.btn_hover};
}}
RibbonButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 8pt;
    color: {t.text_primary};
    text-align: center;
}}
RibbonButton:hover {{
    background: {t.btn_hover};
    border-color: {t.btn_checked_border};
}}
RibbonButton:pressed {{
    background: {t.btn_pressed};
}}
RibbonButton:checked {{
    background: {t.btn_checked};
    border-color: {t.btn_checked_border};
}}
RibbonButton:disabled {{
    color: {t.text_disabled};
}}
RibbonButton::menu-button {{
    /* Make the right-side strip invisible but keep it functional */
    border: none;
    background: transparent;
}}
RibbonButton::menu-indicator {{
    /* Small down-arrow in the bottom-right corner */
    subcontrol-position: bottom right;
    subcontrol-origin: padding;
    width: 10px;
    height: 8px;
    bottom: 12px;
    right: 4px;
}}
RibbonSmallButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 1px 4px;
    font-size: 8pt;
    color: {t.text_primary};
    text-align: left;
}}
RibbonSmallButton:hover {{
    background: {t.btn_hover};
    border-color: {t.btn_checked_border};
}}
RibbonSmallButton:pressed {{
    background: {t.btn_pressed};
}}
RibbonSmallButton:checked {{
    background: {t.btn_checked};
    border-color: {t.btn_checked_border};
}}
RibbonSmallButton:disabled {{
    color: {t.text_disabled};
}}
"""
