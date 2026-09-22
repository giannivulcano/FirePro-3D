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
# Layout metrics (variant-INDEPENDENT; semantic-first — see docs/specs/ui-design-system.md).
#   Base ramp (reference only, NOT a master multiplier): xs=4 sm=8 md=12 lg=16 xl=20.
#   Margins are (left, top, right, bottom); consume via `layout.setContentsMargins(*M.X)`
#   in Python and `{M.X}` interpolation in build_dialog_qss.
# ─────────────────────────────────────────────────────────────────────────────
class _Metrics:
    # base ramp (reference)
    XS, SM, MD, LG, XL = 4, 8, 12, 16, 20
    # header / titlebar
    HEADER_H = 40
    HEADER_MARGIN = (14, 7, 10, 7)
    HEADER_ICON = 22
    HEADER_ICON_GAP = 8
    HEADER_TITLE_GAP = 10
    WINCTL_DOT = 20
    WINCTL_ICON = 18
    # body / panels
    DIALOG_BODY_MARGIN = (20, 18, 20, 18)   # simple form dialogs (content-driven)
    PANEL_PAGE_MARGIN = (14, 14, 14, 14)    # dense panel pages
    PANEL_W = 268
    PANEL_W_WIDE = 324
    SEAM = 1
    SECTION_GAP = 8
    TOPTABS_BAR_INSET = 12   # horizontal inset of the tab strip (TopTabs)
    TOPTABS_PAGE_TOP = 14    # breathing room below the divider (TopTabs)
    LEFT_TAB_W = 24          # browser LeftTabs vertical strip width (mockup-tuned)
    LEFT_TAB_INSET = 2       # gap between the window/dock left edge and the strip
    LEFT_TAB_GAP = 2         # inter-tab gap (QSS margin-bottom + accent-bar trim)
    DOCK_HEADER_H = 33       # dock header rail height (aligns with canvas tab rail)
    # footer
    FOOTER_MARGIN = (14, 9, 14, 9)
    FOOTER_BTN_GAP = 8
    FOOTER_H = 30                       # footer rail fixed height
    FOOTER_SUBRAIL_MARGIN = (12, 0, 12, 0)  # per sub-rail h-padding
    FOOTER_TOGGLE_GAP = 6              # spacing in the toggles sub-rail
    FOOTER_OSNAP_GAP = 2              # spacing between inline osnap toggles
    # toolbar
    TOOLBAR_MARGIN = (12, 9, 12, 9)
    TOOLBAR_GAP = 8
    # side-rail (SideTabs)
    SIDE_RAIL_W = 188
    SIDE_RAIL_MARGIN = (6, 12, 6, 12)
    SIDE_RAIL_ROW_GAP = 4
    STEP_ROW_MARGIN = (10, 6, 8, 6)
    STEP_ROW_GAP = 8
    STEP_CHIP = 16
    # radii / pill
    RADIUS_INPUT = 6
    RADIUS_CARD = 7
    RADIUS_PILL = 11
    RADIUS_CHIP = 8
    PILL_PADDING = (3, 10)                  # (vertical, horizontal)


M = _Metrics()


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
    selection_hover: str
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
    @property
    def toggle_knob(self) -> str: return self.on_accent

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
    selection_hover="#00BFFF",
    ok="#6FBE93", warn="#D9A24A", danger="#E07A6F",
)

LIGHT = Theme(
    name="light",
    ground="#f4f5f6", surface="#ffffff", sunken="#ffffff", raised="#eceef0",
    line="#d4d8dc", line_strong="#b4bac0",
    ink="#1c2024", muted="#5a636c", faint="#98a1aa",
    accent="#2f9e63", accent_ink="#ffffff", on_accent="#ffffff",
    selection="#2f9e63", selection_active="#1f7a49",
    selection_hover="#0091D6",
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

def _tab_language_qss(t: Theme, sel: str, *, edge: str = "bottom") -> str:
    """Shared house tab-state QSS for any ``QTabBar::tab`` selector.

    Emits ONLY the state/colour language (muted default; accent-soft hover with a
    1px accent outline + rounded corners away from the content edge; ink + 600 +
    a 2px accent bar on ``edge`` when selected; faint disabled). Callers append
    their own metric literals (padding/font/min-width). ``edge`` is the border the
    accent bar rides: ``"bottom"`` for top-mounted strips (ribbon/dialog/canvas),
    ``"right"`` for a left-mounted (West) strip (browser LeftTabs).
    """
    round_away = {
        "bottom": "border-top-left-radius: 5px; border-top-right-radius: 5px;",
        "right": "border-top-left-radius: 5px; border-bottom-left-radius: 5px;",
    }[edge]
    return f"""
{sel} {{ background: transparent; color: {t.muted};
    border: 1px solid transparent; border-{edge}: 2px solid transparent; }}
{sel}:hover:!selected {{ color: {t.ink}; background: {t.accent_soft};
    border-color: {t.accent}; border-{edge}-color: transparent; {round_away} }}
{sel}:selected {{ color: {t.ink}; font-weight: 600; border-{edge}: 2px solid {t.accent}; }}
{sel}:disabled {{ color: {t.faint}; }}
"""


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
    font-size: 9.75pt;   /* 13px @ 96dpi — pt (not px) so QComboBox popups don't
                            hit QFont::setPointSize(-1). See ui-design-system.md. */
}}

/* ── Dock widgets ───────────────────────────────────────────────────────── */
/* Body tone (surface): the middle panels are surface; rails are surface2/raised. */
QDockWidget {{
    background: {t.surface};
    color: {t.text_primary};
    titlebar-close-icon: none;
}}
/* Dock resize separator collapsed to 0 so docked panels butt flush against the
   canvas rail vlines (a wider separator left a gap where the panel's header
   divider meets the vertical rail line). The vlines are the visible dividers. */
QMainWindow::separator {{ background: {t.surface}; width: 0px; height: 0px; }}
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
    border-top: 2px solid {t.border_strong};   /* 2px, matching the header divider */
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

/* ── Canvas view tabs (mainwindow-chrome-revamp-stage2.md — TopTabs language) */
/* Frame every edge of the canvas with the rail divider token; body tone. */
/* The whole tab-row strip (incl. the empty space beside the QTabBar) = surface2. */
/* Side rail dividers are explicit QFrame vlines flanking the canvas (main.py);
   a QTabWidget border-left is covered by the first tab. Pane carries the top
   (under-strip) + bottom lines. */
QTabWidget#centralTabs {{ background: {t.surface}; }}
QTabWidget#centralTabs::pane {{ border: none; border-top: 1px solid {t.line_strong}; background: {t.surface}; }}
/* Clear the QGraphicsView default frame (StyledPanel 1px) on canvas views — the
   faint line bordering the canvas. Dialog previews (#previewView) keep theirs. */
QTabWidget#centralTabs QGraphicsView {{ border: none; }}
QTabWidget#centralTabs QTabBar {{ background: {t.surface}; }}
/* Match the ribbon TopTabs metrics (7px 16px 8px, 9pt); right padding insets
   the close dot from the tab's right edge. */
QTabWidget#centralTabs QTabBar::tab {{ padding: 4px 10px 5px 16px; margin-right: 2px; font-size: 9pt; }}
{_tab_language_qss(t, "QTabWidget#centralTabs QTabBar::tab", edge="bottom")}
/* Selected canvas tab matches the browser rail: accent-soft fill + 1px accent
   outline + the 2px accent bar (border-bottom renders fine on North tabs). */
QTabWidget#centralTabs QTabBar::tab:selected {{
    background: {t.accent_soft}; border: 1px solid {t.accent};
    border-top-left-radius: 5px; border-top-right-radius: 5px;
    border-bottom: 2px solid {t.accent}; }}
QTabWidget#centralTabs QTabBar::scroller {{ width: 16px; }}
/* Scroller (overflow) arrows only. The close button is a custom QToolButton
   (_CanvasTabBar/_TabCloseButton) with its own transparent style — a header-
   style dot, not the built-in ::close-button indicator. */
QTabWidget#centralTabs QTabBar::scroller QToolButton {{
    background: {t.bg_raised}; border: 1px solid {t.line_strong}; }}

/* ── Browser LeftTabs (west strip; mainwindow-chrome-revamp-stage2.md) ───── */
QTabBar#leftTabsBar {{ background: transparent; }}
QTabBar#leftTabsBar::tab {{ padding: 12px 6px; margin-bottom: {M.LEFT_TAB_GAP}px; font-size: 9pt; }}
{_tab_language_qss(t, "QTabBar#leftTabsBar::tab", edge="right")}
/* Browser rail: selected tab keeps the hover-highlight look — accent-soft fill
   + 1px accent outline. The 2px accent side-bar on the content-facing edge is
   drawn by ui_kit._WestTabBar.paintEvent (QSS border-right is unreliable on
   rotated tabs). Per-surface override (top tabs stay underline-only). */
QTabBar#leftTabsBar::tab:selected {{
    background: {t.accent_soft}; border: 1px solid {t.accent};
    border-top-left-radius: 5px; border-bottom-left-radius: 5px; }}

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
QLabel[role="header"] {{ color: {t.accent};
    border-bottom: 1px solid {t.border_subtle}; padding-bottom: 1px; }}
QLabel[role="muted"] {{ color: {t.muted}; }}
QLabel[state="warn"] {{
    color: {t.warn}; background: {t.warn_soft};
    border-radius: 6px; padding: 6px 8px;
}}
/* table rows read as separated cards */
QTableWidget::item, QTableView::item {{
    border-bottom: 1px solid {t.border_subtle};
}}
/* ── Segmented controls (property-panel icon_enum / bool_group) ─────── */
QWidget#segmented QToolButton {{
    background: {t.bg_raised}; border: 1px solid {t.border_subtle};
    border-radius: 5px; color: {t.muted}; margin: 0; padding: 0;
}}
/* selected renders identically to hover (same fill, light icon/text) */
QWidget#segmented QToolButton:hover,
QWidget#segmented QToolButton:checked {{
    background: {_rgba(t.accent, 128)}; border-color: {t.accent}; color: {t.ink};
}}
/* ── Properties dock: seamless combos + spinboxes (field-colour, single arrow) ── */
#PropertiesDock QComboBox, #PropertiesDock QSpinBox,
#PropertiesDock QLineEdit, #PropertiesDock QPlainTextEdit {{
    background: {t.bg_raised}; font-size: 11px; min-height: 25px;
}}
#PropertiesDock QComboBox::drop-down {{
    border: none; background: transparent; width: 18px;
}}
#PropertiesDock QSpinBox::up-button, #PropertiesDock QSpinBox::down-button {{
    border: none; background: transparent; width: 16px;
}}
/* ── Percent slider (property-panel opacity) ───────────────────────── */
QSlider#pctSlider::groove:horizontal {{
    height: 4px; background: {t.border_subtle}; border-radius: 2px;
}}
QSlider#pctSlider::sub-page:horizontal {{
    background: {t.accent}; border-radius: 2px;
}}
QSlider#pctSlider::handle:horizontal {{
    background: {t.accent}; width: 12px; height: 12px;
    margin: -5px 0; border-radius: 6px;
}}
"""


def build_ribbon_qss(t: Theme) -> str:
    """Return ribbon-specific QSS that overrides the app-level tab styling
    so the ribbon tabs sit flush against the ribbon panel without a pane border.
    """
    return f"""
RibbonBar {{
    background: {t.surface};
    border-bottom: 1px solid {t.border_strong};
}}
/* Ribbon tabs adopt the house TopTabs look: flat, muted, accent-underline on
   select. Tab strip pinned to the body tone (surface) so it reads as one ribbon
   surface; the header↔ribbon divider lives above the strip (in the chrome stack),
   not under it. */
RibbonBar QTabBar {{
    background: {t.surface};
}}
RibbonBar QTabBar::tab {{
    padding: 7px 16px 8px;
    margin-right: 2px;
    font-size: 9pt;
    min-width: 80px;
}}
{_tab_language_qss(t, "RibbonBar QTabBar::tab", edge="bottom")}
/* Selected ribbon tab: accent-soft fill + 1px accent outline + accent underline
   (matches the canvas tabs / browser rail — not underline-only). */
RibbonBar QTabBar::tab:selected {{
    background: {t.accent_soft}; border: 1px solid {t.accent};
    border-top-left-radius: 5px; border-top-right-radius: 5px;
    border-bottom: 2px solid {t.accent}; }}
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


def build_dialog_qss(t: "Theme") -> str:
    """Unified house-dialog stylesheet (replaces build_underlay_manager_qss /
    build_block_manager_qss / _import_extra_qss). Scoped to the
    QDialog[houseDialog="true"] marker + shared child objectNames — never a
    per-dialog objectName. See docs/specs/ui-design-system.md."""
    chev_r = asset_path("chevron_right.svg").replace("\\", "/")
    chev_d = asset_path("chevron_down.svg").replace("\\", "/")
    return f"""
/* ── House dialog root ──────────────────────────────────────────────────── */
QDialog[houseDialog="true"] {{ background: {t.surface}; color: {t.ink}; font-size: 9.75pt; }}
QDialog[houseDialog="true"] QLabel {{ background: transparent; color: {t.ink}; }}
QDialog[houseDialog="true"] QLabel[role="muted"] {{ color: {t.muted}; }}
QDialog[houseDialog="true"] QLabel[role="faint"] {{ color: {t.faint}; font-size: 12px; }}
QDialog[houseDialog="true"] QLabel[role="header"] {{ color: {t.muted}; font-size: 10px; font-weight: 600; }}
QDialog[houseDialog="true"] QLabel[role="title"] {{ color: {t.ink}; font-size: 14px; font-weight: 700; }}
QDialog[houseDialog="true"] QLabel[role="name"]  {{ color: {t.ink}; font-size: 14px; font-weight: 600; }}
QDialog[houseDialog="true"] QLabel[state="warn"] {{
    color: {t.warn}; background: {t.warn_soft}; border-radius: {M.RADIUS_INPUT}px; padding: 6px 8px; }}

/* ── Buttons ────────────────────────────────────────────────────────────── */
QDialog[houseDialog="true"] QPushButton {{
    background: {t.table}; color: {t.ink}; border: 1px solid {t.line_strong};
    border-radius: {M.RADIUS_INPUT}px; padding: 5px 12px; font-weight: 500; }}
QDialog[houseDialog="true"] QPushButton:hover:enabled {{ background: {t.accent_soft}; border-color: {t.accent}; }}
QDialog[houseDialog="true"] QPushButton:disabled {{ color: {t.faint}; border-color: {t.line}; }}
QDialog[houseDialog="true"] QPushButton[variant="primary"] {{
    background: {t.accent}; color: {t.on_accent}; border-color: {t.accent}; font-weight: 600; }}
QDialog[houseDialog="true"] QPushButton[variant="primary"]:hover:enabled {{ background: {t.ok}; }}
QDialog[houseDialog="true"] QPushButton[variant="danger"]:hover:enabled {{
    background: {t.danger_soft}; color: {t.danger}; border-color: {t.danger}; }}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QDialog[houseDialog="true"] QLineEdit {{
    background: {t.table}; color: {t.ink}; border: 1px solid {t.line_strong};
    border-radius: {M.RADIUS_INPUT}px; padding: 5px 9px; selection-background-color: {t.accent_soft2}; }}
QDialog[houseDialog="true"] QLineEdit:focus {{ border-color: {t.accent}; }}
QDialog[houseDialog="true"] QComboBox {{ font-size: 9.75pt; }}
QDialog[houseDialog="true"] QCheckBox {{ background: transparent; }}
QDialog[houseDialog="true"] QWidget#pdfOpts {{ background: transparent; }}
QDialog[houseDialog="true"] QListWidget {{
    background: {t.raised}; color: {t.ink}; border: 1px solid {t.line_strong}; border-radius: {M.RADIUS_INPUT}px; }}
QDialog[houseDialog="true"] QListWidget::item {{ padding: 3px 6px; }}
QDialog[houseDialog="true"] QListWidget::item:hover {{ background: {t.accent_soft}; }}
QDialog[houseDialog="true"] QListWidget::item:selected {{ background: {t.accent_soft}; color: {t.ink}; }}
QGraphicsView#previewView {{ background: {t.ground}; border: 1px solid {t.line}; }}

/* ── Structural regions (child objectNames) ─────────────────────────────── */
QFrame#shellHeader {{ background: {t.surface2}; border-bottom: 1px solid {t.line}; }}
QFrame#footerBar   {{ background: {t.surface2}; border-top: 1px solid {t.line}; }}
QFrame#toolbarBar  {{ background: {t.surface}; border-bottom: 1px solid {t.line}; }}
QFrame#dialogBody  {{ background: {t.surface}; border-top: 1px solid {t.line}; }}
QFrame#detailsPanel {{ background: {t.surface}; border-left: 1px solid {t.line}; }}
QStackedWidget#detailsPanel {{ background: {t.surface}; border-left: 1px solid {t.line_strong}; }}
/* Rail-adjacent content: no own border — the SideTabs rail's border-right (line_strong)
   is the single canonical rail/content separator (see ui-design-system.md multi-section recipe). */
QStackedWidget#railContent {{ background: {t.surface}; }}

/* ── Underlay/Block table (tree AND flat view share rules) ──────────────── */
QTreeView#underlayTable, QTableView#underlayTable {{
    background: {t.table}; alternate-background-color: {t.table}; color: {t.ink};
    border: none; gridline-color: transparent; selection-background-color: {t.accent_soft2};
    selection-color: {t.ink}; outline: none; }}
QTreeView#underlayTable::item, QTableView#underlayTable::item {{ border-bottom: 1px solid {t.line}; padding: 0 4px; }}
QTreeView#underlayTable::item:hover, QTableView#underlayTable::item:hover {{ background: {t.accent_soft}; }}
QTreeView#underlayTable::item:selected, QTableView#underlayTable::item:selected {{ background: {t.accent_soft2}; color: {t.ink}; }}
QTreeView#underlayTable::branch {{ background: {t.table}; }}
QTreeView#underlayTable::branch:has-children:!has-siblings:closed,
QTreeView#underlayTable::branch:closed:has-children:has-siblings {{ background: {t.table}; image: url("{chev_r}"); }}
QTreeView#underlayTable::branch:open:has-children:!has-siblings,
QTreeView#underlayTable::branch:open:has-children:has-siblings {{ background: {t.table}; image: url("{chev_d}"); }}

/* ── Kit: SideTabs / step rows ──────────────────────────────────────────── */
QDialog[houseDialog="true"] QFrame#stepRail {{ background: {t.surface}; border-right: 1px solid {t.line_strong}; }}
QDialog[houseDialog="true"] QFrame#stepRailInner {{ background: transparent; }}
QDialog[houseDialog="true"] QFrame[stepRow="true"] {{
    border-radius: {M.RADIUS_INPUT}px; border-left: 2px solid transparent; background: transparent; }}
QDialog[houseDialog="true"] QFrame[stepRow="true"]:hover {{ background: {t.accent_soft}; }}
QDialog[houseDialog="true"] QFrame[stepRow="true"][current="true"] {{ background: {t.accent_soft}; border-left: 2px solid {t.accent}; }}
QDialog[houseDialog="true"] QLabel[stepNo="true"] {{
    background: {t.raised}; color: {t.muted}; border-radius: {M.RADIUS_CHIP}px; font-size: 9px; font-weight: 700; }}
QDialog[houseDialog="true"] QLabel[stepNo="true"][current="true"], QDialog[houseDialog="true"] QLabel[stepNo="true"][done="true"] {{
    background: {t.accent}; color: {t.accent_ink}; }}
QDialog[houseDialog="true"] QLabel[stepNo="true"][warn="true"] {{ background: {t.warn_soft}; color: {t.warn}; }}
QDialog[houseDialog="true"] QLabel[stepName="true"] {{ font-size: 12px; font-weight: 700; background: transparent; color: {t.ink}; }}
QDialog[houseDialog="true"] QLabel[stepStatus="true"] {{ font-size: 10px; color: {t.faint}; background: transparent; }}
QDialog[houseDialog="true"] QLabel[stepStatus="true"][state="warn"], QDialog[houseDialog="true"] QLabel[stepStatus="true"][warn="true"] {{ color: {t.warn}; }}
QDialog[houseDialog="true"] QLabel[stepStatus="true"][state="done"], QDialog[houseDialog="true"] QLabel[stepStatus="true"][done="true"] {{ color: {t.muted}; }}

/* ── Kit: TopTabs (peer pages within a section; DIALOG_TABS_SPEC) ────────── */
QDialog[houseDialog="true"] QTabBar#topTabsBar {{ background: transparent; }}
QDialog[houseDialog="true"] QTabBar#topTabsBar::tab {{
    padding: 7px 11px 8px; margin-right: 2px; font-size: 12px; }}
{_tab_language_qss(t, 'QDialog[houseDialog="true"] QTabBar#topTabsBar::tab', edge="bottom")}

/* ── Kit: SwitchBar (segmented) ─────────────────────────────────────────── */
QDialog[houseDialog="true"] QPushButton[switch="true"] {{ padding: 5px 14px; border-radius: 0; }}
QDialog[houseDialog="true"] QPushButton[switch="true"][segpos="left"] {{ border-top-left-radius: 7px; border-bottom-left-radius: 7px; }}
QDialog[houseDialog="true"] QPushButton[switch="true"][segpos="right"] {{ border-top-right-radius: 7px; border-bottom-right-radius: 7px; border-left: none; }}
QDialog[houseDialog="true"] QPushButton[switch="true"][segpos="mid"] {{ border-left: none; }}
QDialog[houseDialog="true"] QPushButton[switch="true"]:checked {{ background: {t.accent}; color: {t.on_accent}; }}

/* ── Kit: Pill ──────────────────────────────────────────────────────────── */
QDialog[houseDialog="true"] QPushButton[pill="true"] {{ padding: {M.PILL_PADDING[0]}px {M.PILL_PADDING[1]}px; border-radius: {M.RADIUS_PILL}px; }}
QDialog[houseDialog="true"] QPushButton[pill="true"]:hover:enabled {{ background: {t.accent_soft}; border-color: {t.accent}; }}

/* ── Kit: cards / pills / drop hint (folded out of _import_extra_qss) ───── */
QDialog[houseDialog="true"] QFrame#scaleCard, QDialog[houseDialog="true"] QFrame#srcCard {{
    background: {t.raised}; border: 1px solid {t.line_strong}; border-radius: {M.RADIUS_CARD}px; }}
QDialog[houseDialog="true"] QWidget#panelPage {{ background: {t.surface}; }}
QDialog[houseDialog="true"] QLabel#scaleVal {{ font-size: 17px; font-weight: 700; background: transparent; }}
QDialog[houseDialog="true"] QLabel#scalePill {{ font-size: 10px; font-weight: 600; padding: 2px 9px; border-radius: 9px; border: 1px solid transparent; }}
QDialog[houseDialog="true"] QLabel#scalePill[state="warn"] {{ color: {t.warn}; border-color: {t.warn}; }}
QDialog[houseDialog="true"] QLabel#scalePill[state="ok"] {{ color: {t.ok}; border-color: {t.ok}; }}
QDialog[houseDialog="true"] QLabel#dropHint {{ color: {t.muted}; font-size: 13px; background: transparent; }}

/* ── Scrollbars / menu / tooltip ────────────────────────────────────────── */
QDialog[houseDialog="true"] QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QDialog[houseDialog="true"] QScrollBar::handle:vertical {{ background: {t.line_strong}; border-radius: 5px; min-height: 30px; }}
QDialog[houseDialog="true"] QScrollBar::handle:vertical:hover {{ background: {t.faint}; }}
QDialog[houseDialog="true"] QScrollBar::add-line, QDialog[houseDialog="true"] QScrollBar::sub-line {{ height: 0; width: 0; }}
QDialog[houseDialog="true"] QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QDialog[houseDialog="true"] QScrollBar::handle:horizontal {{ background: {t.line_strong}; border-radius: 5px; min-width: 30px; }}
QMenu#uwMenu {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line_strong}; border-radius: 8px; padding: 5px; }}
QMenu#uwMenu::item {{ padding: 6px 22px 6px 10px; border-radius: 5px; }}
QMenu#uwMenu::item:selected {{ background: {t.accent_soft}; }}
QMenu#uwMenu::item:disabled {{ color: {t.faint}; }}
QMenu#uwMenu::separator {{ height: 1px; background: {t.line}; margin: 5px 4px; }}
QMenu#uwMenu::indicator {{ width: 14px; height: 14px; margin-left: 4px; }}
QHeaderView::section {{
    background: {t.table}; color: {t.muted}; border: none; border-bottom: 1px solid {t.line_strong};
    padding: 7px 8px; font-size: 10px; font-weight: 600; }}
QToolTip {{
    background: {t.surface2}; color: {t.ink}; border: 1px solid {t.line_strong}; padding: 4px 7px; }}
"""

