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

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTransform

from .constants import (FLIP_CROSSHAIR_IDLE_ALPHA, GHOST_GLOW_CACHE_MAX_PX,
                        HALO_GLOW_PX, HALO_TRACE_COLOR,
                        HALO_TRACE_WIDTH_PX, TRANSFORM_GHOST_DIM_OPACITY,
                        TRANSFORM_GHOST_TRACE_ALPHA, TRANSFORM_GHOST_TRACE_WIDTH_PX)
from .geometry_2d import _degenerate_axis
from .halo import halo_scene_path, paint_halo_path, paint_halo_paths

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


class LiteGhostPath(QPainterPath):
    """A ghost path :func:`paint_ghost` draws as the 1 px trace only.

    The simplified ghost of a large array (review I2): the HALO glow's four
    wide antialiased strokes per path dominate the repaint (A/B bench,
    2026-10-01: 2499 line copies 240 ms with the glow, ~5 ms as one merged
    trace), so above ``ARRAY_GHOST_FULL_MAX`` paths the copies are merged
    into one of these. It covers exactly the same geometry.
    """


class GhostFrame(list):
    """One rigid-transform frame of a shared ghost base (L1068).

    Still the list of mapped paths every reader expects, plus ``base`` (the
    unmoved scene-coord paths, shared across a gesture's frames) and
    ``xform``, so :func:`paint_ghost` can draw the cached glow of ``base``
    under ``xform`` instead of re-stroking every path.

    Args:
        base: The gesture's unmoved scene-coord ``QPainterPath``s.
        xform: This frame's scene transform (base -> frame).
    """

    def __init__(self, base, xform: QTransform):
        super().__init__(xform.map(p) for p in base)
        self.base = base
        self.xform = xform


def _is_rigid(t: QTransform, tol: float = 1e-6) -> bool:
    """True for a rotation / reflection / translation (no scale or shear)."""
    if not t.isAffine():
        return False
    a, b, c, d = t.m11(), t.m12(), t.m21(), t.m22()
    return (abs(a * a + b * b - 1.0) < tol and abs(c * c + d * d - 1.0) < tol
            and abs(a * c + b * d) < tol)


def _xf_key(t: QTransform) -> tuple:
    return (t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy())


class _GlowEntry:
    """One paint device's cached glow: the image and what it was built for.

    ``img`` is ``None`` when the base was too large to cache at that key
    (the verdict is kept so the oversize check doesn't re-run every paint).
    """

    __slots__ = ("base", "key", "img", "origin", "w0_inv")

    def __init__(self, base, key, img, origin, w0_inv):
        self.base, self.key, self.img = base, key, img
        self.origin, self.w0_inv = origin, w0_inv


class _GlowCache:
    """The HALO glow of a ghost base, rendered once in device pixels.

    One entry per paint device (a view's viewport), so a second view of the
    scene, or another view with no ghost, never evicts this one's image.
    An entry is keyed on the base list's identity (held, so the id cannot
    be reused), the painter's world transform (zoom / pan), the device pixel
    ratio and the accent colour; a miss re-renders. Bench 2026-11-01: blit
    ~1 ms (move) / ~3 ms (rotate) vs. 55-470 ms of live glow per move.
    """

    # Paint devices kept at once; the oldest is dropped past this.
    _MAX_ENTRIES = 4

    def __init__(self):
        self._entries: dict[int, _GlowEntry] = {}

    def release(self, device=None) -> None:
        """Drop *device*'s cached image (every device's when ``None``)."""
        if device is None:
            self._entries.clear()
        else:
            self._entries.pop(id(device), None)

    def cached_base(self, device):
        """The base *device*'s image was built from (``None`` if none)."""
        e = self._entries.get(id(device))
        return e.base if e is not None and e.img is not None else None

    def paint(self, painter, frame: GhostFrame, theme) -> bool:
        """Draw *frame*'s glow from the cache.

        Returns:
            False when the frame can't use the cache (non-rigid transform,
            oversized image); the caller then paints the live glow.
        """
        if not _is_rigid(frame.xform):
            return False
        device = painter.device()
        w = painter.worldTransform()
        dpr = device.devicePixelRatioF()
        key = (_xf_key(w), dpr, theme.color(HALO_TRACE_COLOR).rgba())
        dev_id = id(device)
        e = self._entries.get(dev_id)
        if e is None or e.base is not frame.base or e.key != key:
            e = self._build(frame.base, key, w, dpr, theme)
            if e is None:
                return False
            self._entries.pop(dev_id, None)
            self._entries[dev_id] = e
            while len(self._entries) > self._MAX_ENTRIES:
                del self._entries[next(iter(self._entries))]
        if e.img is None:
            return False
        # Qt composes a * b as "a, then b": image px -> device (+origin) ->
        # scene (W0^-1) -> this frame (xform) -> device (current W).
        m = (QTransform.fromTranslate(e.origin.x(), e.origin.y())
             * e.w0_inv * frame.xform * w)
        painter.save()
        painter.setWorldTransform(m)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(QPointF(0.0, 0.0), e.img)
        painter.restore()
        return True

    @staticmethod
    def _build(base, key, w: QTransform, dpr: float, theme):
        """A new entry for *base* under *w*, or ``None`` if *w* is singular."""
        w0_inv, ok = w.inverted()
        if not ok:
            return None
        bounds = QRectF()
        for p in base:
            bounds = bounds.united(p.boundingRect())
        pad = HALO_GLOW_PX + HALO_TRACE_WIDTH_PX + 2.0
        r = w.mapRect(bounds).adjusted(-pad, -pad, pad, pad)
        pw, ph = math.ceil(r.width() * dpr), math.ceil(r.height() * dpr)
        if pw <= 0 or ph <= 0 or pw * ph > GHOST_GLOW_CACHE_MAX_PX:
            return _GlowEntry(base, key, None, r.topLeft(), w0_inv)
        img = QImage(pw, ph, QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(0)
        pt = QPainter(img)
        pt.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pt.setWorldTransform(w * QTransform.fromTranslate(-r.x(), -r.y()))
        paint_halo_paths(pt, base, theme)
        pt.end()
        return _GlowEntry(base, key, img, r.topLeft(), w0_inv)


_GLOW_CACHE = _GlowCache()


def release_glow_cache(device=None) -> None:
    """Drop the cached ghost glow of *device* (every device's when ``None``).

    A view calls this with its viewport when it paints no ghost, so another
    view's live gesture keeps its image.
    """
    _GLOW_CACHE.release(device)


def paint_ghost(painter, paths, theme) -> None:
    """Paint each scene-coord path: HALO (defaults) then a 1 px solid trace.

    A :class:`LiteGhostPath` gets the trace only (no HALO glow). A
    :class:`GhostFrame` under a rigid transform draws its glow from the
    device-pixel cache (L1068).

    Args:
        painter: Active QPainter in scene coordinates.
        paths: Scene-coord ``QPainterPath``s.
        theme: Theme providing ``color(token)``.
    """
    if not paths:
        return
    pen = _trace_pen(theme)
    if not (isinstance(paths, GhostFrame)
            and _GLOW_CACHE.paint(painter, paths, theme)):
        paint_halo_paths(painter, [p for p in paths
                                   if not isinstance(p, LiteGhostPath)], theme)
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
    ``CAD_Math.mirror_point``. Identity for a degenerate axis — the commit
    path's own test (``geometry_2d._degenerate_axis``), so the ghost never
    shows a reflection ``manip_reflect`` would then skip.

    Args:
        p1: A point on the axis (scene).
        p2: A second point on the axis (scene).
    """
    if _degenerate_axis(p1, p2):
        return QTransform()
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    n2 = dx * dx + dy * dy
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
    if _degenerate_axis(p1, p2):
        return
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    c = view_rect.center()
    reach = (math.hypot(view_rect.width(), view_rect.height())
             + math.hypot(c.x() - p1.x(), c.y() - p1.y()))
    # Glow first, crisp dash-dot axis on top (the paint_ghost order).
    seg = QPainterPath()
    seg.moveTo(p1)
    seg.lineTo(p2)
    paint_halo_path(painter, seg, theme)
    pen = _trace_pen(theme)
    pen.setStyle(Qt.PenStyle.DashDotLine)
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen)
    painter.drawLine(QPointF(p1.x() - ux * reach, p1.y() - uy * reach),
                     QPointF(p1.x() + ux * reach, p1.y() + uy * reach))
    painter.restore()


def paint_flip_crosshair(painter, center, lr, ud, view_rect, theme) -> None:
    """Paint the Flip crosshair (DS3.3): a vertical and a horizontal dash-dot
    line through *center*, spanning the visible *view_rect*.

    The ``lr`` axis is the vertical line, ``ud`` the horizontal one. Active
    axes use the accent trace pen; idle ones the same pen at low alpha so the
    quadrant structure stays readable.

    Args:
        painter: Active QPainter in scene coordinates.
        center: Crosshair centre (scene).
        lr: Whether the vertical (left-right) reflection is active.
        ud: Whether the horizontal (up-down) reflection is active.
        view_rect: The view's visible scene rect.
        theme: Theme providing ``color(token)``.
    """
    cx, cy = center.x(), center.y()
    c = view_rect.center()
    reach = (math.hypot(view_rect.width(), view_rect.height())
             + math.hypot(c.x() - cx, c.y() - cy))
    active = _trace_pen(theme)
    active.setStyle(Qt.PenStyle.DashDotLine)
    idle = QPen(active)
    col = QColor(idle.color())
    col.setAlpha(FLIP_CROSSHAIR_IDLE_ALPHA)
    idle.setColor(col)
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for is_active, (ux, uy) in ((lr, (0.0, 1.0)), (ud, (1.0, 0.0))):
        painter.setPen(active if is_active else idle)
        painter.drawLine(QPointF(cx - ux * reach, cy - uy * reach),
                         QPointF(cx + ux * reach, cy + uy * reach))
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
