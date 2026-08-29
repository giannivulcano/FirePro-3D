"""Colour tokens and stylesheet for the Underlay Manager.

DARK is the active theme (green accent, matching the app's dark theme). Apply
``build_qss(theme)`` to the dialog — or to the whole application
(``app.setStyleSheet(...)``) if you want your existing import dialog and the
popup menus restyled to match. The delegates take the same ``Theme`` object, so
painted cells always agree with the stylesheet.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from PyQt6.QtGui import QColor


@dataclass(frozen=True)
class Theme:
    ground: str = "#141619"
    surface: str = "#1E2125"        # dialog chrome
    surface2: str = "#24282D"       # footer / raised strips
    table: str = "#212529"          # table + inputs
    ink: str = "#E6E9EC"
    muted: str = "#98A1AA"
    faint: str = "#6F7982"
    line: str = "#363B41"
    line_strong: str = "#454B52"
    accent: str = "#63BE8B"         # green accent
    accent_ink: str = "#0E1712"     # text on accent
    accent_soft: str = "rgba(99, 190, 139, 34)"    # QSS rgba(): alpha is 0-255
    accent_soft2: str = "rgba(99, 190, 139, 56)"
    warn: str = "#D9A24A"
    warn_soft: str = "rgba(217, 162, 74, 40)"
    danger: str = "#E07A6F"
    danger_soft: str = "rgba(224, 122, 111, 38)"
    ok: str = "#6FBE93"
    chip: str = "#2C3137"
    chip_ink: str = "#B7BFC7"

    def color(self, name: str, alpha: int = 255) -> QColor:
        """Token as a QColor (for delegate painting)."""
        c = QColor(getattr(self, name))
        c.setAlpha(alpha)
        return c


DARK = Theme()


_QSS = """
QDialog#UnderlayManagerDialog {
    background: $surface;
    color: $ink;
    font-size: 13px;
}
#UnderlayManagerDialog QLabel { background: transparent; color: $ink; }
#UnderlayManagerDialog QLabel[role="muted"]  { color: $muted; }
#UnderlayManagerDialog QLabel[role="faint"]  { color: $faint; font-size: 12px; }
#UnderlayManagerDialog QLabel[role="header"] {
    color: $muted; font-size: 10px; font-weight: 600;
}
#UnderlayManagerDialog QLabel[state="warn"] {
    color: $warn; background: $warn_soft;
    border-radius: 6px; padding: 6px 8px;
}

#UnderlayManagerDialog QPushButton {
    background: $table; color: $ink;
    border: 1px solid $line_strong; border-radius: 6px;
    padding: 5px 12px; font-weight: 500;
}
#UnderlayManagerDialog QPushButton:hover:enabled { background: $surface2; border-color: $faint; }
#UnderlayManagerDialog QPushButton:disabled { color: $faint; border-color: $line; }
#UnderlayManagerDialog QPushButton[variant="primary"] {
    background: $accent; color: $accent_ink; border-color: $accent; font-weight: 600;
}
#UnderlayManagerDialog QPushButton[variant="primary"]:hover:enabled { background: $ok; }
#UnderlayManagerDialog QPushButton[variant="danger"]:hover:enabled {
    background: $danger_soft; color: $danger; border-color: $danger;
}

#UnderlayManagerDialog QLineEdit {
    background: $table; color: $ink;
    border: 1px solid $line_strong; border-radius: 6px;
    padding: 5px 9px;
    selection-background-color: $accent_soft2;
}
#UnderlayManagerDialog QLineEdit:focus { border-color: $accent; }

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
QFrame#footerBar    { background: $surface2; border-top: 1px solid $line; }
QFrame#toolbarBar   { background: $surface; border-bottom: 1px solid $line; }
QLabel#previewBox {
    background: $table; border: 1px solid $line; border-radius: 6px;
}

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


def build_qss(theme: Theme = DARK) -> str:
    qss = _QSS
    # longest keys first, so $line never clobbers $line_strong etc.
    for key, value in sorted(asdict(theme).items(), key=lambda kv: -len(kv[0])):
        qss = qss.replace("$" + key, value)
    return qss
