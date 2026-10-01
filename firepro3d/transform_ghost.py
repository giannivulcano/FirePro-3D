"""Transform ghost (scene-tools.md D11): HALO glow + 1 px solid accent trace.

One style for every transform preview (Move, Duplicate, Paste, Rotate,
Offset, Array and the gridline array/offset ghosts — Flip / Mirror additionally
paint their axis (:func:`paint_axis`) and map the ghost through
:func:`reflect_transform`; Scale through :func:`scale_transform`): the ghost
traces the item's true drawn geometry (:func:`halo.halo_scene_path`, not
``shape()``), painted as the HALO glow with a crisp 1 px accent line on top.
The originals are dimmed while the transform runs; :func:`dim_items`
multiplies (never resets) the existing opacity so a display-manager opacity
survives, and :func:`restore_items` puts back the exact prior value.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPen, QTransform

from .constants import (HALO_TRACE_COLOR, TRANSFORM_GHOST_DIM_OPACITY,
                        TRANSFORM_GHOST_TRACE_ALPHA, TRANSFORM_GHOST_TRACE_WIDTH_PX)
from .halo import halo_scene_path, paint_halo_path

# Opacity match tolerance for restore (qreal round-trip noise only).
_OPACITY_TOL = 1e-4


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
    pen = _trace_pen(theme)
    for path in paths:
        paint_halo_path(painter, path, theme)
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    for path in paths:
        painter.drawPath(path)
    painter.restore()


def _trace_pen(theme) -> QPen:
    """The 1 px cosmetic accent pen shared by the ghost trace and the ray."""
    c = QColor(theme.color(HALO_TRACE_COLOR))
    c.setAlpha(TRANSFORM_GHOST_TRACE_ALPHA)
    pen = QPen(c, TRANSFORM_GHOST_TRACE_WIDTH_PX)
    pen.setCosmetic(True)
    return pen


def paint_ray(painter, start, end, theme) -> None:
    """Paint Rotate's thin pivot->cursor ray (D8) with the ghost trace pen.

    Args:
        painter: Active QPainter in scene coordinates.
        start: The pivot (scene coordinates).
        end: The cursor (scene coordinates).
        theme: Theme providing ``color(token)``.
    """
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(_trace_pen(theme))
    painter.drawLine(start, end)
    painter.restore()


def reflect_transform(p1, p2) -> QTransform:
    """Scene ``QTransform`` mirroring across the infinite line p1-p2 (DD3).

    ``x' = p1 + R·(x − p1)`` with ``R = [[a, b], [b, −a]]``,
    ``a = (dx² − dy²)/n²``, ``b = 2·dx·dy/n²`` — the same map as
    ``CAD_Math.mirror_point``. Identity for a degenerate axis.

    Args:
        p1: A point on the axis (scene).
        p2: A second point on the axis (scene).
    """
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    n2 = dx * dx + dy * dy
    if n2 < 1e-18:
        return QTransform()
    a = (dx * dx - dy * dy) / n2
    b = 2.0 * dx * dy / n2
    px, py = p1.x(), p1.y()
    return QTransform(a, b, b, -a, px - a * px - b * py, py - b * px + a * py)


def scale_transform(base, factor: float) -> QTransform:
    """Scene ``QTransform`` for a uniform scale by *factor* about *base*
    (the Scale ghost, DD4) — the same map as ``CAD_Math.scale_point``."""
    return QTransform(factor, 0.0, 0.0, factor,
                      base.x() * (1.0 - factor), base.y() * (1.0 - factor))


def paint_axis(painter, p1, p2, view_rect, theme) -> None:
    """Paint the Flip / Mirror axis (DD3): an infinite centre-line.

    A cosmetic 1 px accent dash-dot line through p1-p2 spanning the whole
    visible *view_rect*, plus the HALO glow traced on the single source
    segment p1-p2 only (not the whole parent shape).

    Args:
        painter: Active QPainter in scene coordinates.
        p1: Source segment start (scene).
        p2: Source segment end (scene).
        view_rect: The view's visible scene rect (the axis spans past it).
        theme: Theme providing ``color(token)``.
    """
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    n = math.hypot(dx, dy)
    if n < 1e-9:
        return
    ux, uy = dx / n, dy / n
    c = view_rect.center()
    reach = (math.hypot(view_rect.width(), view_rect.height())
             + math.hypot(c.x() - p1.x(), c.y() - p1.y()))
    pen = _trace_pen(theme)
    pen.setStyle(Qt.PenStyle.DashDotLine)
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawLine(QPointF(p1.x() - ux * reach, p1.y() - uy * reach),
                     QPointF(p1.x() + ux * reach, p1.y() + uy * reach))
    painter.restore()
    seg = QPainterPath()
    seg.moveTo(p1)
    seg.lineTo(p2)
    paint_halo_path(painter, seg, theme)


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

    An item whose opacity no longer equals the dimmed value (someone else —
    e.g. the display manager or a level switch — set it mid-transform) keeps
    that newer value.

    Args:
        saved: The list :func:`dim_items` returned; deleted items are skipped.
    """
    from PyQt6 import sip as _sip
    for it, prior in saved or ():
        if _sip.isdeleted(it):
            continue
        if abs(it.opacity() - prior * TRANSFORM_GHOST_DIM_OPACITY) <= _OPACITY_TOL:
            it.setOpacity(prior)
