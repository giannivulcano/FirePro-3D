"""World-unit tiled pattern renderer (hatch-and-fill concept HD4 / HD4a).

One entry point, :func:`paint_fill`: IntersectClip to the boundary, optional
solid background, then the tile block's lattice stamped in **scene axes**
anchored at the pattern origin — the boundary may be posed/rotated by the
caller's frame, the hatch never rotates (D-A11). Lattice paths are cached per
``(tile id, tile version, effective scale, nx, ny, row parity)``.

``BlockDefinition.tile`` returns a fresh copy on every access, so each entry
point reads it once and passes the dict down.
"""
from __future__ import annotations

import logging
import math
from collections import OrderedDict

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QTransform

from .constants import (DRAFTING_CANVAS_SCALE, HATCH_LOD_MAX_CELLS,
                        HATCH_LOD_MIN_CELL_PX, HATCH_LOD_TONE)
from .hatch_patterns import resolve_tile, tile_is_valid
from .render_op import STROKE

_log = logging.getLogger(__name__)
_CACHE_MAX = 256
_LATTICE: "OrderedDict[tuple, tuple[QPainterPath, QPainterPath]]" = OrderedDict()
_MISSING_LOGGED: set = set()
_PAPER_SCENE_CLS = None

#: Bench composition counter (G12 asserts the bench actually stamped cells).
STATS = {"stamped_cells": 0}


def _is_paper_scene(scene) -> bool:
    """True if *scene* is a sheet (``PaperScene``) — its items are printed mm."""
    global _PAPER_SCENE_CLS
    if scene is None:
        return False
    if _PAPER_SCENE_CLS is None:
        from .paper_space import PaperScene
        _PAPER_SCENE_CLS = PaperScene
    return isinstance(scene, _PAPER_SCENE_CLS)


def drafting_factor(scene) -> float:
    """Model mm per printed mm for a Drafting tile drawn in *scene* (D-A30).

    Inside a paper-viewport render (``scene._hatch_paper_scale`` set by
    ``paper_display.apply_paper_overrides``) → ``1 / paper_scale``; a sheet's
    own items (``PaperScene``, already printed mm) → 1; else the model canvas
    default ``DRAFTING_CANVAS_SCALE`` until SB1c lands a view scale.

    Args:
        scene: The scene being drawn, or None.

    Returns:
        The factor a Drafting tile's printed-mm size is multiplied by.
    """
    ps = getattr(scene, "_hatch_paper_scale", None) if scene is not None else None
    if ps:
        return 1.0 / ps
    if _is_paper_scene(scene):
        return 1.0
    return DRAFTING_CANVAS_SCALE


def _device_scale(painter) -> float:
    """Device px per painter unit — rotation-safe (no ``views()[0]``, H6)."""
    t = painter.deviceTransform()
    return math.hypot(t.m11(), t.m12()) or 1e-9


def _pattern_pen(scene, colour: QColor, line_width_px: float) -> QPen:
    """True-mm "Hatch" weight on paper/PDF (D-A31); cosmetic px on the canvas."""
    ps = getattr(scene, "_hatch_paper_scale", None) if scene is not None else None
    if ps or _is_paper_scene(scene):
        from .paper_display import hatch_line_mm
        pen = QPen(colour, hatch_line_mm() / (ps or 1.0))
        pen.setCosmetic(False)                 # true mm on paper/PDF (D-A31)
        return pen
    pen = QPen(colour, line_width_px)
    pen.setCosmetic(True)
    return pen


def _tone(painter, rect: QRectF, colour: QColor) -> None:
    """LOD / missing-tile tone: *rect* filled at ``HATCH_LOD_TONE`` × alpha."""
    c = QColor(colour)
    c.setAlphaF(c.alphaF() * HATCH_LOD_TONE)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(c))
    painter.drawRect(rect)


def _tile_paths(tile, k: float) -> tuple[QPainterPath, QPainterPath]:
    """(stroke path, filled path) of one tile cell scaled by *k* (tile-local)."""
    strokes, fills = QPainterPath(), QPainterPath()
    for op in tile.render_ops():
        (strokes if op.kind == STROKE else fills).addPath(op.path)
    if k != 1.0:
        t = QTransform.fromScale(k, k)
        strokes, fills = t.map(strokes), t.map(fills)
    return strokes, fills


def _lattice(tile, t: dict, k, nx, ny, parity) -> tuple[QPainterPath, QPainterPath]:
    """Cached union of nx×ny cells; cell (a, b) at (a·w + s, −b·h), s = row
    shift on odd lattice rows (``parity`` = the first row's lattice index % 2)."""
    key = (tile.id, tile.version, round(k, 9), nx, ny, parity)
    hit = _LATTICE.get(key)
    if hit is not None:
        _LATTICE.move_to_end(key)
        return hit
    w, h = t["w"] * k, t["h"] * k
    shift = t["row_shift"] * k
    cell_s, cell_f = _tile_paths(tile, k)
    out_s, out_f = QPainterPath(), QPainterPath()
    for b in range(ny):
        dx0 = shift if (parity + b) % 2 else 0.0
        for a in range(nx):
            dx, dy = a * w + dx0, -b * h
            if not cell_s.isEmpty():
                out_s.addPath(cell_s.translated(dx, dy))
            if not cell_f.isEmpty():
                out_f.addPath(cell_f.translated(dx, dy))
    _LATTICE[key] = (out_s, out_f)
    if len(_LATTICE) > _CACHE_MAX:
        _LATTICE.popitem(last=False)
    return out_s, out_f


def stamp_lattice(painter, bounds: QRectF, tile, k: float, origin: QPointF,
                  pen: QPen, colour: QColor, t: dict | None = None) -> bool:
    """Stamp *tile* (scaled by *k*) over *bounds*, anchored at *origin*.

    Painter coords must be the pattern frame (scene axes).

    Args:
        painter: Active painter in the pattern frame.
        bounds: Area to cover, painter coords.
        tile: Tile ``BlockDefinition``.
        k: Effective scale (pattern scale × drafting factor).
        origin: Lattice anchor (cell (0, 0) lower-left), painter coords.
        pen: Pattern stroke pen.
        colour: Pattern fill colour (filled ops, LOD tone).
        t: The tile dict already read from ``tile.tile`` (read once if None).

    Returns:
        False when the LOD rule drew the tone instead (D-A35).
    """
    if t is None:
        t = tile.tile
    w, h = t["w"] * k, t["h"] * k
    shift = t["row_shift"] * k
    dev = _device_scale(painter)
    if min(w, h) * dev < HATCH_LOD_MIN_CELL_PX:
        _tone(painter, bounds, colour)
        return False
    cb = QRectF()                                     # content overhang (D-A33)
    for op in tile.render_ops():
        cb = cb.united(op.path.boundingRect())
    cb = QRectF(cb.left() * k, cb.top() * k, cb.width() * k, cb.height() * k)
    ox, oy = origin.x(), origin.y()
    j0 = math.floor((oy + cb.top() - bounds.bottom()) / h)
    j1 = math.ceil((oy + cb.bottom() - bounds.top()) / h)
    i0 = math.floor((bounds.left() - cb.right() - ox - max(0.0, shift)) / w)
    i1 = math.ceil((bounds.right() - cb.left() - ox - min(0.0, shift)) / w)
    nx, ny = i1 - i0 + 1, j1 - j0 + 1
    if nx * ny > HATCH_LOD_MAX_CELLS:
        _tone(painter, bounds, colour)
        return False
    strokes, fills = _lattice(tile, t, k, nx, ny, j0 % 2)
    STATS["stamped_cells"] += nx * ny
    painter.save()
    painter.translate(ox + i0 * w, oy - j0 * h)
    if not fills.isEmpty():
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(colour))
        painter.drawPath(fills)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(strokes)
    painter.restore()
    return True


def paint_fill(painter, clip: QPainterPath, *, scene,
               background: QColor | None = None, tile_ref: str | None = None,
               colour: QColor | None = None, origin: QPointF | None = None,
               scale: float = 1.0, line_width_px: float = 1.0,
               to_scene=None) -> None:
    """Fill *clip* with an optional background and a tiled pattern.

    Args:
        painter: Active painter; its current coords are the caller's item frame.
        clip: Boundary in painter coords (closed; OddEven honoured).
        scene: The scene being drawn (drafting factor, paper weight, registry).
        background: Solid layer colour, or None.
        tile_ref: Pattern tile id / legacy name, or None for no pattern.
        colour: Pattern colour (alpha honoured); None → mid grey.
        origin: Pattern origin in **scene** coords (default the container
            origin (0, 0)).
        scale: Pattern Scale multiplier.
        line_width_px: Canvas (cosmetic) pattern line width.
        to_scene: Item→scene transform of the painter frame; the pattern is
            stamped in scene axes so a rotated frame never rotates it.
    """
    if clip is None or clip.isEmpty():
        return
    origin = QPointF(0.0, 0.0) if origin is None else origin
    painter.save()
    try:
        if to_scene is not None and not to_scene.isIdentity():
            inv, ok = to_scene.inverted()
            if ok:
                painter.setTransform(inv * painter.transform())   # now scene coords
                clip = to_scene.map(clip)
        painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)   # H5
        bounds = clip.boundingRect()
        if background is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(background))
            painter.drawRect(bounds)
        if tile_ref is None:
            return
        col = QColor(colour) if colour is not None else QColor("#808080")
        tile = resolve_tile(tile_ref, getattr(scene, "block_registry", None))
        if tile is None or not tile_is_valid(tile):
            if tile_ref not in _MISSING_LOGGED:
                _MISSING_LOGGED.add(tile_ref)
                _log.warning("Hatch pattern %r not found — drawing a tone", tile_ref)
            _tone(painter, bounds, col)
            return
        t = tile.tile
        k = scale * (drafting_factor(scene) if t["size"] == "drafting" else 1.0)
        stamp_lattice(painter, bounds, tile, k, origin,
                      _pattern_pen(scene, col, line_width_px), col, t)
    finally:
        painter.restore()


def paint_swatch(painter, rect: QRectF, tile_ref: str | None, colour: QColor,
                 registry=None, background: QColor | None = None) -> None:
    """Picker / Display Manager swatch: ~2.5 cells across *rect*'s height,
    stamped by the same lattice builder as the renderer (preview ≡ render, H3).

    Args:
        painter: Active painter (widget / pixmap coords).
        rect: Swatch rect.
        tile_ref: Pattern tile id / legacy name.
        colour: Pattern colour.
        registry: Project block registry for project tiles, or None.
        background: Optional swatch background.
    """
    painter.save()
    try:
        painter.setClipRect(rect)
        if background is not None:
            painter.fillRect(rect, background)
        tile = resolve_tile(tile_ref, registry)
        if tile is None or not tile_is_valid(tile):
            _tone(painter, rect, colour)
            return
        t = tile.tile
        k = (rect.height() / 2.5) / max(t["w"], t["h"])
        pen = QPen(colour, 1.0)
        pen.setCosmetic(True)
        stamp_lattice(painter, rect, tile, k, QPointF(rect.left(), rect.bottom()),
                      pen, colour, t)
    finally:
        painter.restore()
