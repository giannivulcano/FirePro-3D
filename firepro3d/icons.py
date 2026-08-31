"""Themed ribbon icon loader — two-token (primary/accent) colour model.

Author icons with the sentinel colours below; the loader substitutes them
per theme. See docs/specs/icon-style-guide.md.
"""
from __future__ import annotations

import logging as _logging
import os
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QByteArray, QSize, Qt

from .assets import asset_path
from .svg_utils import svg_recolor

_log = _logging.getLogger(__name__)

LIGHT = "light"
DARK = "dark"

PRIMARY_SENTINEL = "#1A1A1A"
ACCENT_SENTINEL = "#004CFF"

# Per-theme PRIMARY (ink) display values. Accent is NOT hard-coded here — it is
# derived from the active theme variant (theme.LIGHT.accent / theme.DARK.accent)
# so theme.accent is the single source of truth for the accent colour. The SVG
# authoring sentinels above never change; only the per-theme display value does.
# See docs/specs/icon-style-guide.md §4.2.
_PRIMARY = {LIGHT: "#1A1A1A", DARK: "#F0F0F0"}
_FALLBACK = "_missing_icon.svg"
_cache: dict[tuple[str, str], QIcon] = {}


def token_map(theme: str) -> dict[str, str]:
    """Return the sentinel→theme colour substitution map for *theme* (copy).

    Primary derives from the fixed ink table; accent derives from the theme
    variant's ``accent`` token (theme.accent is the single source of truth).
    """
    from . import theme as _theme
    variant = _theme.DARK if theme == DARK else _theme.LIGHT
    return {
        PRIMARY_SENTINEL: _PRIMARY.get(theme, _PRIMARY[LIGHT]),
        ACCENT_SENTINEL: variant.accent,
    }


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
        _log.warning("themed_icon: %r not found in graphics/Ribbon, using fallback", name)
        path = asset_path("Ribbon", _FALLBACK)
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    icon = _render_icon(svg_recolor(raw, token_map(theme)))
    _cache[key] = icon
    return icon
