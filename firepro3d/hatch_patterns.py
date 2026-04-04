"""Hatch-pattern registry.

**Built-in patterns** (diagonal, cross_hatch, horizontal) use Qt's
``Qt.BrushStyle`` enums — resolution-independent vectors.

**Custom SVG patterns** are loaded from ``graphics/hatch_patterns/*.svg``.
Line geometry is extracted from the SVG and drawn as real vector lines
at paint time, clipped to the element shape.  This gives the same
crispness as the built-in patterns at any zoom level.

SVGs should use a 24×24 viewBox with ``<line>`` or ``<path>`` elements
using black strokes.  Lines that exit one edge should re-enter the
opposite edge for seamless tiling.

Call ``make_hatch_brush()`` for built-in patterns or
``get_pattern_lines()`` + ``draw_svg_hatch()`` for SVG patterns.
"""
from __future__ import annotations

import os
import re
import math
from functools import lru_cache
from xml.etree import ElementTree

from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap


# ── Locate SVG folder ─────────────────────────────────────────────────────────

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SVG_DIR = os.path.join(_THIS_DIR, "graphics", "hatch_patterns")


# ── Qt built-in (vector) patterns ─────────────────────────────────────────────

_BUILTIN_STYLES: dict[str, Qt.BrushStyle] = {
    "diagonal":    Qt.BrushStyle.BDiagPattern,
    "cross_hatch": Qt.BrushStyle.DiagCrossPattern,
    "horizontal":  Qt.BrushStyle.HorPattern,
}


# ── SVG line extraction ───────────────────────────────────────────────────────

_NS = {"svg": "http://www.w3.org/2000/svg"}


def _parse_viewbox(root) -> tuple[float, float]:
    """Return (width, height) from the viewBox attribute."""
    vb = root.get("viewBox", "0 0 24 24")
    parts = vb.replace(",", " ").split()
    if len(parts) >= 4:
        return float(parts[2]), float(parts[3])
    return 24.0, 24.0


def _extract_lines(svg_path: str) -> tuple[float, float, list[tuple[float, float, float, float]]]:
    """Parse an SVG file and return (tile_w, tile_h, [(x1,y1,x2,y2), ...]).

    Coordinates are in SVG viewBox units.  Only ``<line>`` elements are
    supported (the most common for hatch patterns).
    """
    tree = ElementTree.parse(svg_path)
    root = tree.getroot()
    tw, th = _parse_viewbox(root)

    lines: list[tuple[float, float, float, float]] = []

    # Find all <line> elements (with or without namespace)
    for tag in ("line", "{http://www.w3.org/2000/svg}line"):
        for elem in root.iter(tag):
            x1 = float(elem.get("x1", "0"))
            y1 = float(elem.get("y1", "0"))
            x2 = float(elem.get("x2", "0"))
            y2 = float(elem.get("y2", "0"))
            lines.append((x1, y1, x2, y2))

    return tw, th, lines


@lru_cache(maxsize=64)
def _cached_pattern_data(svg_path: str):
    """Cached SVG parse result."""
    return _extract_lines(svg_path)


# ── Discover available patterns ───────────────────────────────────────────────

def _discover_svg_patterns() -> dict[str, str]:
    """Scan the SVG folder and return {name: filepath} for each .svg."""
    patterns: dict[str, str] = {}
    if not os.path.isdir(_SVG_DIR):
        return patterns
    for fname in sorted(os.listdir(_SVG_DIR)):
        if fname.lower().endswith(".svg"):
            name = os.path.splitext(fname)[0]
            patterns[name] = os.path.join(_SVG_DIR, fname)
    return patterns


_SVG_PATTERNS: dict[str, str] = _discover_svg_patterns()


def refresh_patterns():
    """Re-scan the SVG folder (call after the user adds new files)."""
    global _SVG_PATTERNS, PATTERN_NAMES
    _SVG_PATTERNS.clear()
    _SVG_PATTERNS.update(_discover_svg_patterns())
    _cached_pattern_data.cache_clear()
    PATTERN_NAMES.clear()
    PATTERN_NAMES.extend(list(_BUILTIN_STYLES.keys()))
    for name in _SVG_PATTERNS:
        if name not in _BUILTIN_STYLES:
            PATTERN_NAMES.append(name)


# ── Public constants ──────────────────────────────────────────────────────────

PATTERN_NAMES: list[str] = list(_BUILTIN_STYLES.keys())
for _n in _SVG_PATTERNS:
    if _n not in _BUILTIN_STYLES:
        PATTERN_NAMES.append(_n)

DEFAULT_PATTERNS: dict[str, str] = {
    "Wall":  "diagonal",
    "Roof":  "diagonal",
    "Floor": "diagonal",
}


# ── Public API ────────────────────────────────────────────────────────────────

def is_builtin(name: str) -> bool:
    """Return True if *name* maps to a Qt built-in BrushStyle."""
    return name in _BUILTIN_STYLES


def is_svg(name: str) -> bool:
    """Return True if *name* is a custom SVG pattern."""
    return name in _SVG_PATTERNS and name not in _BUILTIN_STYLES


def make_hatch_brush(name: str, tile_size: int = 24,
                     color: QColor | None = None,
                     line_width: float = 1.0) -> QBrush:
    """Return a QBrush for built-in patterns.

    For SVG patterns, use ``draw_svg_hatch()`` instead.
    """
    col = color or QColor(100, 100, 100)
    style = _BUILTIN_STYLES.get(name, Qt.BrushStyle.BDiagPattern)
    return QBrush(col, style)


def draw_svg_hatch(painter: QPainter, clip_path, scene,
                   name: str, color: QColor,
                   line_width: float = 1.0,
                   hatch_scale: float = 1.0):
    """Draw an SVG hatch pattern as true vector lines, clipped to *clip_path*.

    Lines are cosmetic (constant screen size regardless of zoom).
    """
    svg_path = _SVG_PATTERNS.get(name)
    if svg_path is None:
        return

    tw, th, lines = _cached_pattern_data(svg_path)
    if not lines:
        return

    # Compute zoom-aware tile size in scene units
    views = scene.views() if scene else []
    scale = abs(views[0].transform().m11()) if views else 1.0
    inv = 1.0 / max(scale, 1e-6)
    tile_w = tw * inv * hatch_scale
    tile_h = th * inv * hatch_scale

    pen = QPen(color, line_width)
    pen.setCosmetic(True)

    painter.save()
    painter.setClipPath(clip_path)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Tile lines across the bounding rect
    rect = clip_path.boundingRect()
    x0 = rect.left() - tile_w
    y0 = rect.top() - tile_h
    x_end = rect.right() + tile_w
    y_end = rect.bottom() + tile_h

    # Scale factor from SVG viewBox coords to scene tile coords
    sx = tile_w / tw
    sy = tile_h / th

    ty = y0
    while ty < y_end:
        tx = x0
        while tx < x_end:
            for lx1, ly1, lx2, ly2 in lines:
                painter.drawLine(
                    QPointF(tx + lx1 * sx, ty + ly1 * sy),
                    QPointF(tx + lx2 * sx, ty + ly2 * sy))
            tx += tile_w
        ty += tile_h

    painter.restore()


def make_hatch_tile(name: str, tile_size: int = 24,
                    color: QColor | None = None,
                    line_width: float = 1.0) -> QPixmap | None:
    """Return a QPixmap preview tile for the display manager swatch."""
    col = color or QColor(100, 100, 100)

    svg_path = _SVG_PATTERNS.get(name)
    if svg_path is None:
        return None

    tw, th, lines = _cached_pattern_data(svg_path)
    if not lines:
        return None

    pix = QPixmap(tile_size, tile_size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(col, max(line_width, 1.0))
    p.setPen(pen)
    sx = tile_size / tw
    sy = tile_size / th
    for lx1, ly1, lx2, ly2 in lines:
        p.drawLine(QPointF(lx1 * sx, ly1 * sy),
                   QPointF(lx2 * sx, ly2 * sy))
    p.end()
    return pix
