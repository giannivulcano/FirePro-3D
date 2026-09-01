"""
theme.py
========
Centralized dark / light theme token system for FirePro 3D.

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

from .assets import asset_path


# ─────────────────────────────────────────────────────────────────────────────
# House typography (see docs/architecture/theming.md § Typography & labels)
#   FONT_UI    — Title / Body / Overline / Control (all prose + labels)
#   FONT_VALUE — numeric readouts (dims, scale, pressure, coords): monospace so
#                digit columns align and 1/l/0/O stay distinct.
# ─────────────────────────────────────────────────────────────────────────────
FONT_UI = "Arial"
FONT_VALUE = "Consolas"


def apply_app_font(app: QApplication) -> None:
    """Set the app-wide UI font family to FONT_UI, preserving the point size."""
    f = app.font()
    f.setFamily(FONT_UI)
    app.setFont(f)


# ─────────────────────────────────────────────────────────────────────────────
# Colour helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rgba(hexc: str, alpha: int) -> str:
    """'#rrggbb' + 0-255 alpha -> a QSS 'rgba(r,g,b,a)' string."""
    c = QColor(hexc)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def _mix(a: str, b: str, t: float) -> str:
    """Linear blend of two '#rrggbb' colours, t in [0,1]."""
    ca, cb = QColor(a), QColor(b)
    r = round(ca.red() + (cb.red() - ca.red()) * t)
    g = round(ca.green() + (cb.green() - ca.green()) * t)
    bl = round(ca.blue() + (cb.blue() - ca.blue()) * t)
    return QColor(r, g, bl).name()


# ─────────────────────────────────────────────────────────────────────────────
# Token dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Theme:
    """One theme variant. A variant authors ONLY the 16 primitive colours;
    every semantic token below derives from them (Layer 2)."""

    name: str

    # Layer 1: primitives (the only authored values)
    ground: str
    surface: str
    sunken: str
    raised: str
    line: str
    line_strong: str
    ink: str
    muted: str
    faint: str
    accent: str
    accent_ink: str
    on_accent: str
    selection: str
    selection_active: str
    ok: str
    warn: str
    danger: str

    # Layer 2: semantic aliases (derived; shared by all variants)
    @property
    def bg_base(self) -> str: return self.ground
    @property
    def canvas_bg(self) -> str: return self.ground
    @property
    def bg_raised(self) -> str: return self.raised
    @property
    def bg_sunken(self) -> str: return self.sunken
    @property
    def bg_tab_inactive(self) -> str: return self.surface
    @property
    def bg_tab_selected(self) -> str: return self.raised
    @property
    def surface2(self) -> str: return self.raised
    @property
    def table(self) -> str: return self.sunken
    @property
    def chip(self) -> str: return self.raised
    @property
    def chip_ink(self) -> str: return self.muted
    @property
    def btn_hover(self) -> str: return self.accent_soft
    @property
    def btn_pressed(self) -> str: return self.raised
    @property
    def btn_checked(self) -> str: return self.accent_soft2
    @property
    def btn_checked_border(self) -> str: return self.accent
    @property
    def border_strong(self) -> str: return self.line_strong
    @property
    def border_subtle(self) -> str: return self.line
    @property
    def text_primary(self) -> str: return self.ink
    @property
    def text_secondary(self) -> str: return self.muted
    @property
    def text_disabled(self) -> str: return self.faint
    @property
    def text_accent(self) -> str: return self.accent
    @property
    def grid_dot(self) -> str: return _mix(self.ground, self.faint, 0.5)
    @property
    def accent_primary(self) -> str: return self.accent
    @property
    def status_ok(self) -> str: return self.ok
    @property
    def status_warn(self) -> str: return self.warn
    @property
    def status_error(self) -> str: return self.danger
    @property
    def accent_soft(self) -> str: return _rgba(self.accent, 34)
    @property
    def accent_soft2(self) -> str: return _rgba(self.accent, 56)
    @property
    def warn_soft(self) -> str: return _rgba(self.warn, 40)
    @property
    def danger_soft(self) -> str: return _rgba(self.danger, 38)

    def color(self, name: str, alpha: int = 255) -> QColor:
        """Resolve a primitive OR semantic token name to a QColor.

        Only hex-valued tokens are resolvable (the rgba ``*_soft`` strings are
        QSS-only). Delegates pass an explicit alpha for soft fills, e.g.
        ``theme.color("accent", 40)``.

        Args:
            name: A primitive or hex-valued semantic token name.
            alpha: Alpha channel value 0-255 (default opaque).

        Returns:
            The resolved colour with the requested alpha.
        """
        val = getattr(self, name)
        c = QColor(val)
        c.setAlpha(alpha)
        return c


# ─────────────────────────────────────────────────────────────────────────────
# Preset themes
# ─────────────────────────────────────────────────────────────────────────────

DARK = Theme(
    name="dark",
    ground="#141619", surface="#1E2125", sunken="#212529", raised="#24282D",
    line="#363B41", line_strong="#454B52",
    ink="#E6E9EC", muted="#98A1AA", faint="#6F7982",
    accent="#63BE8B", accent_ink="#0E1712", on_accent="#ffffff",
    selection="#63BE8B", selection_active="#8FE3B4",
    ok="#6FBE93", warn="#D9A24A", danger="#E07A6F",
)

LIGHT = Theme(
    name="light",
    ground="#f4f5f6", surface="#ffffff", sunken="#ffffff", raised="#eceef0",
    line="#d4d8dc", line_strong="#b4bac0",
    ink="#1c2024", muted="#5a636c", faint="#98a1aa",
    accent="#2f9e63", accent_ink="#ffffff", on_accent="#ffffff",
    selection="#2f9e63", selection_active="#1f7a49",
    ok="#2f9e63", warn="#b46500", danger="#c42b1c",
)


# ─────────────────────────────────────────────────────────────────────────────
# Auto-detect
# ─────────────────────────────────────────────────────────────────────────────

# Persisted UI-theme preference (Preferences → UI). "system" | "light" | "dark".
_THEME_PREF_ORG = "GV"
_THEME_PREF_APP = "FirePro3D"
THEME_SETTINGS_KEY = "ui/theme"

_pref_cache: str | None = None


def theme_preference() -> str:
    """Return the persisted UI-theme preference: 'system' | 'light' | 'dark'.

    Cached after first read so ``detect()`` (called from paint paths) does not
    hit QSettings on every repaint. Call :func:`refresh_theme_preference` after
    changing the preference to invalidate the cache.
    """
    global _pref_cache
    if _pref_cache is None:
        from PyQt6.QtCore import QSettings
        val = QSettings(_THEME_PREF_ORG, _THEME_PREF_APP).value(
            THEME_SETTINGS_KEY, "system")
        _pref_cache = str(val).lower()
    return _pref_cache


def refresh_theme_preference() -> None:
    """Invalidate the cached UI-theme preference (call after changing it)."""
    global _pref_cache
    _pref_cache = None


def detect() -> Theme:
    """Return the active theme.

    Honors the persisted ``ui/theme`` preference (Preferences → UI): ``light``
    or ``dark`` force the variant; ``system`` (the default) picks DARK or LIGHT
    by inspecting the application window-palette lightness.
    """
    pref = theme_preference()
    if pref == "light":
        return LIGHT
    if pref == "dark":
        return DARK
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
    check_url = asset_path("checkmark.svg").replace("\\", "/")
    return f"""
/* ── Window & generic widgets ──────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background: {t.bg_base};
    color: {t.text_primary};
    font-size: 13px;
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
    border-radius: 6px;
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
    border-radius: 6px;
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
    border-radius: 6px;
    padding: 4px 8px;
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
    border-radius: 6px;
    padding: 4px 8px;
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
    border-radius: 6px;
    padding: 5px 14px;
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
/* Checkbox indicators — standalone checkboxes AND item-view check columns.
   The default dark-palette indicator is near-invisible, so make checked
   (accent fill + white tick) read clearly against unchecked (empty box). */
QCheckBox::indicator, QAbstractItemView::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t.border_strong};
    border-radius: 3px;
    background: {t.bg_base};
}}
QCheckBox::indicator:hover, QAbstractItemView::indicator:hover {{
    border-color: {t.accent_primary};
}}
QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{
    background: {t.accent_primary};
    border-color: {t.accent_primary};
    image: url("{check_url}");
}}
/* Mixed multi-select values (property panel): Word-style filled square —
   the QSS replaces native painting, so without this rule indeterminate
   renders identically to unchecked. */
QCheckBox::indicator:indeterminate, QAbstractItemView::indicator:indeterminate {{
    background: {t.accent_primary};
    border-color: {t.accent_primary};
}}
QCheckBox::indicator:disabled, QAbstractItemView::indicator:disabled {{
    border-color: {t.border_subtle};
}}
/* Radio-button indicators — styled explicitly because QSS replaces native
   painting entirely; any state without a rule silently renders as the base
   state (indistinguishable from unchecked on the dark theme). */
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {t.border_strong};
    border-radius: 7px;
    background: {t.bg_base};
}}
QRadioButton::indicator:hover {{
    border-color: {t.accent_primary};
}}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0.55 {t.accent_primary}, stop:0.65 {t.bg_base});
    border-color: {t.accent_primary};
}}
QRadioButton::indicator:disabled {{
    border-color: {t.border_subtle};
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
QTabBar::close-button {{
    subcontrol-position: right;
    background: transparent;
    border: none;
    padding: 2px;
    margin: 2px;
}}
QTabBar::close-button:hover {{
    background: {t.btn_hover};
    border-radius: 2px;
}}

/* ── Scroll bars ────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t.bg_base};
    width: 10px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {t.border_strong};
    border-radius: 5px;
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
    border-radius: 5px;
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
    border-radius: 6px;
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
    border-radius: 6px;
    padding: 3px 6px;
}}

/* ── Dialog button boxes ────────────────────────────────────────────────── */
QDialogButtonBox QPushButton {{
    min-width: 70px;
}}

/* ── Semantic button variants ─────────────────────────────────────── */
QPushButton[variant="primary"] {{
    background: {t.accent}; color: {t.accent_ink};
    border-color: {t.accent}; font-weight: 700;
}}
QPushButton[variant="primary"]:hover {{ background: {t.ok}; }}
QPushButton[variant="danger"] {{ color: {t.danger}; }}
QPushButton[variant="danger"]:hover {{
    background: {t.danger_soft}; border-color: {t.danger};
}}
/* ── Role / state labels ──────────────────────────────────────────── */
QLabel[role="header"] {{ color: {t.muted}; font-weight: 600; }}
QLabel[role="muted"] {{ color: {t.muted}; }}
QLabel[state="warn"] {{
    color: {t.warn}; background: {t.warn_soft};
    border-radius: 6px; padding: 6px 8px;
}}
/* table rows read as separated cards */
QTableWidget::item, QTableView::item {{
    border-bottom: 1px solid {t.border_subtle};
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


# ---------------------------------------------------------------------------
# Underlay Manager dialog stylesheet
#
# Object-scoped QSS for the retired underlay_manager_theme.py, using `$name`
# placeholders substituted from the house Theme by build_underlay_manager_qss().
# Kept identical to the original so the manager renders the same after retirement.
# ---------------------------------------------------------------------------
_UNDERLAY_MANAGER_QSS = """
QDialog#UnderlayManagerDialog, QDialog#UnderlayImportDialog {
    background: $surface;
    color: $ink;
    font-size: 13px;
}
#UnderlayManagerDialog QLabel, #UnderlayImportDialog QLabel { background: transparent; color: $ink; }
#UnderlayManagerDialog QLabel[role="muted"], #UnderlayImportDialog QLabel[role="muted"]  { color: $muted; }
#UnderlayManagerDialog QLabel[role="faint"], #UnderlayImportDialog QLabel[role="faint"]  { color: $faint; font-size: 12px; }
#UnderlayManagerDialog QLabel[role="header"], #UnderlayImportDialog QLabel[role="header"] {
    color: $muted; font-size: 10px; font-weight: 600;
}
#UnderlayManagerDialog QLabel[role="title"], #UnderlayImportDialog QLabel[role="title"] {
    color: $ink; font-size: 14px; font-weight: 700;
}
#UnderlayManagerDialog QLabel[role="name"], #UnderlayImportDialog QLabel[role="name"] {
    color: $ink; font-size: 14px; font-weight: 600;
}
#UnderlayManagerDialog QLabel[state="warn"], #UnderlayImportDialog QLabel[state="warn"] {
    color: $warn; background: $warn_soft;
    border-radius: 6px; padding: 6px 8px;
}

#UnderlayManagerDialog QPushButton, #UnderlayImportDialog QPushButton {
    background: $table; color: $ink;
    border: 1px solid $line_strong; border-radius: 6px;
    padding: 5px 12px; font-weight: 500;
}
#UnderlayManagerDialog QPushButton:hover:enabled, #UnderlayImportDialog QPushButton:hover:enabled { background: $accent_soft; border-color: $accent; }
#UnderlayManagerDialog QPushButton:disabled, #UnderlayImportDialog QPushButton:disabled { color: $faint; border-color: $line; }
#UnderlayManagerDialog QPushButton[variant="primary"], #UnderlayImportDialog QPushButton[variant="primary"] {
    background: $accent; color: $on_accent; border-color: $accent; font-weight: 600;
}
#UnderlayManagerDialog QPushButton[variant="primary"]:hover:enabled, #UnderlayImportDialog QPushButton[variant="primary"]:hover:enabled { background: $ok; }
#UnderlayManagerDialog QPushButton[variant="danger"]:hover:enabled, #UnderlayImportDialog QPushButton[variant="danger"]:hover:enabled {
    background: $danger_soft; color: $danger; border-color: $danger;
}

#UnderlayManagerDialog QLineEdit, #UnderlayImportDialog QLineEdit {
    background: $table; color: $ink;
    border: 1px solid $line_strong; border-radius: 6px;
    padding: 5px 9px;
    selection-background-color: $accent_soft2;
}
#UnderlayManagerDialog QLineEdit:focus, #UnderlayImportDialog QLineEdit:focus { border-color: $accent; }

QTableView#underlayTable {
    background: $table;
    alternate-background-color: $table;
    color: $ink;
    border: none;
    gridline-color: transparent;
    selection-background-color: $accent_soft2;
    selection-color: $ink;
    outline: none;
}
QTableView#underlayTable::item {
    border-bottom: 1px solid $line;
    padding: 0 4px;
}
QTableView#underlayTable::item:hover    { background: $accent_soft; }
QTableView#underlayTable::item:selected { background: $accent_soft2; color: $ink; }
QHeaderView::section {
    background: $table; color: $muted;
    border: none; border-bottom: 1px solid $line_strong;
    padding: 7px 8px;
    font-size: 10px; font-weight: 600;
}
QTableView QTableCornerButton::section { background: $table; border: none; }

QFrame#detailsPanel { background: $surface; border-left: 1px solid $line; }
QFrame#shellHeader { background: $surface2; border-bottom: 1px solid $line; }
QFrame#footerBar    { background: $surface2; border-top: 1px solid $line; }
QFrame#toolbarBar   { background: $surface; border-bottom: 1px solid $line; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: $line_strong; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $faint; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal { background: $line_strong; border-radius: 5px; min-width: 30px; }

QMenu#uwMenu {
    background: $surface; color: $ink;
    border: 1px solid $line_strong; border-radius: 8px;
    padding: 5px;
}
QMenu#uwMenu::item {
    padding: 6px 22px 6px 10px; border-radius: 5px;
}
QMenu#uwMenu::item:selected { background: $accent_soft; }
QMenu#uwMenu::item:disabled { color: $faint; }
QMenu#uwMenu::separator { height: 1px; background: $line; margin: 5px 4px; }
QMenu#uwMenu::indicator { width: 14px; height: 14px; margin-left: 4px; }

QToolTip {
    background: $surface2; color: $ink;
    border: 1px solid $line_strong; padding: 4px 7px;
}
"""


# Token names the Underlay Manager QSS references via `$name`.
_UM_QSS_TOKENS = (
    "ground", "surface", "surface2", "table", "ink", "muted", "faint",
    "line_strong", "line", "accent_ink", "on_accent", "accent_soft2", "accent_soft",
    "accent", "warn_soft", "warn", "danger_soft", "danger", "ok",
    "chip_ink", "chip",
)


def build_underlay_manager_qss(t: Theme) -> str:
    """Object-scoped QSS for the Underlay Manager dialog, from house tokens.

    Args:
        t: The active house theme.

    Returns:
        The manager stylesheet with every ``$token`` substituted.
    """
    qss = _UNDERLAY_MANAGER_QSS
    # longest keys first so `$line` never clobbers `$line_strong`
    for key in sorted(_UM_QSS_TOKENS, key=len, reverse=True):
        qss = qss.replace("$" + key, getattr(t, key))
    return qss
