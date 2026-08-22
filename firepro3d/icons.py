"""Themed ribbon icon loader — two-token (primary/accent) colour model.

Author icons with the sentinel colours below; the loader substitutes them
per theme. See docs/specs/icon-style-guide.md.
"""
from __future__ import annotations

import os
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QByteArray, QSize, Qt

from .assets import asset_path
from .display_manager import svg_recolor

LIGHT = "light"
DARK = "dark"

PRIMARY_SENTINEL = "#1A1A1A"
ACCENT_SENTINEL = "#004CFF"

# Per-theme token values (icon-style-guide.md token table).
_TOKENS = {
    LIGHT: {PRIMARY_SENTINEL: "#1A1A1A", ACCENT_SENTINEL: "#008000"},  # primary black, accent green
    DARK:  {PRIMARY_SENTINEL: "#F0F0F0", ACCENT_SENTINEL: "#3B82F6"},  # primary white, accent blue
}
_FALLBACK = "_missing_icon.svg"
_cache: dict[tuple[str, str], QIcon] = {}


def token_map(theme: str) -> dict[str, str]:
    return dict(_TOKENS.get(theme, _TOKENS[LIGHT]))


def _render_icon(svg_bytes: bytes) -> QIcon:
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    pm = QPixmap(QSize(64, 64))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return QIcon(pm)


def themed_icon(name: str, theme: str) -> QIcon:
    """Return a theme-tinted QIcon for a ribbon SVG. Missing file → fallback glyph."""
    key = (name, theme)
    if key in _cache:
        return _cache[key]
    path = asset_path("Ribbon", name)
    if not os.path.isfile(path):
        path = asset_path("Ribbon", _FALLBACK)
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    icon = _render_icon(svg_recolor(raw, token_map(theme)))
    _cache[key] = icon
    return icon
