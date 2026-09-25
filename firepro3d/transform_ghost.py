"""Transform ghost (scene-tools.md D11): HALO glow + 1 px solid accent trace.

One style for every transform preview (Move, Duplicate, Paste, Rotate,
Offset, Array and the gridline array/offset ghosts): the ghost traces the
item's true drawn geometry (:func:`halo.halo_scene_path`, not ``shape()``),
painted as the HALO glow with a crisp 1 px accent line on top. The originals
are dimmed while the transform runs; :func:`dim_items` multiplies (never
resets) the existing opacity so a display-manager opacity survives, and
:func:`restore_items` puts back the exact prior value.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen

from .constants import (HALO_TRACE_COLOR, TRANSFORM_GHOST_DIM_OPACITY,
                        TRANSFORM_GHOST_TRACE_ALPHA, TRANSFORM_GHOST_TRACE_WIDTH_PX)
from .halo import halo_scene_path, paint_halo_path


def ghost_base_paths(items) -> list:
    """Scene-coord traced geometry for *items* (drawn geometry, not shape()).

    Args:
        items: Graphics items (in a scene or free-standing).

    Returns:
        A list of non-empty scene-coord ``QPainterPath``s; items whose trace
        fails or is empty are skipped.
    """
    out = []
    for it in items:
        try:
            p = halo_scene_path(it)
        except Exception:
            continue
        if p is not None and not p.isEmpty():
            out.append(p)
    return out


def paint_ghost(painter, paths, theme) -> None:
    """Paint each scene-coord path: HALO (defaults) then a 1 px solid trace.

    Args:
        painter: Active QPainter in scene coordinates.
        paths: Scene-coord ``QPainterPath``s.
        theme: Theme providing ``color(token)``.
    """
    if not paths:
        return
    c = QColor(theme.color(HALO_TRACE_COLOR))
    c.setAlpha(TRANSFORM_GHOST_TRACE_ALPHA)
    pen = QPen(c, TRANSFORM_GHOST_TRACE_WIDTH_PX)
    pen.setCosmetic(True)
    for path in paths:
        paint_halo_path(painter, path, theme)
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    for path in paths:
        painter.drawPath(path)
    painter.restore()


def dim_items(items) -> list:
    """Multiply each item's opacity by the dim factor.

    Args:
        items: Graphics items to dim.

    Returns:
        ``[(item, prior_opacity)]`` for :func:`restore_items`.
    """
    saved = []
    for it in items or ():
        prior = it.opacity()
        saved.append((it, prior))
        it.setOpacity(prior * TRANSFORM_GHOST_DIM_OPACITY)
    return saved


def restore_items(saved) -> None:
    """Restore the exact prior opacities recorded by :func:`dim_items`.

    Args:
        saved: The list :func:`dim_items` returned; deleted items are skipped.
    """
    from PyQt6 import sip as _sip
    for it, prior in saved or ():
        if not _sip.isdeleted(it):
            it.setOpacity(prior)
