"""HALO preselection-highlight overlay painter (mirrors paint_snap_indicator)."""
import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QPainterPath
from PyQt6.QtWidgets import (QGraphicsPathItem, QGraphicsLineItem,
                             QGraphicsRectItem, QGraphicsEllipseItem,
                             QGraphicsPolygonItem)

from .constants import (HALO_TRACE_COLOR, HALO_TRACE_ALPHA,
                        HALO_TRACE_WIDTH_PX, HALO_GLOW_PX)

_TRACED_TYPES = (QGraphicsPathItem, QGraphicsLineItem, QGraphicsRectItem,
                 QGraphicsEllipseItem, QGraphicsPolygonItem)


def _halo_trace_path_local(item):
    """The item's *drawn* primitive geometry as a QPainterPath in local coords.

    Unlike ``shape()`` (a fattened stroke of the geometry sized for hit-testing),
    this traces the actual outline the user sees — a single line for thin/open
    geometry, the outline (no interior) for filled shapes. Baked rotation already
    lives inside the local geometry, exactly as ``shape()`` relies on, so the
    caller maps this through ``sceneTransform()`` unchanged. Falls back to
    ``shape()`` for types with no cleaner drawn path (e.g. TextItem's box)."""
    # Path items: path() IS the drawn geometry (rotation baked into the path).
    if isinstance(item, QGraphicsPathItem):
        p = item.path()
        return p if not p.isEmpty() else item.shape()
    # Line items (LineItem, ReferenceLine, Pipe): the bare segment.
    if isinstance(item, QGraphicsLineItem):
        ln = item.line()
        p = QPainterPath(ln.p1())
        p.lineTo(ln.p2())
        return p
    # Rect items (RectangleItem): axis-aligned rect + separately-baked rotation.
    if isinstance(item, QGraphicsRectItem):
        gcp = getattr(item, "get_closed_path", None)
        p = QPainterPath(gcp()) if (gcp and gcp() is not None) else None
        if p is None:
            p = QPainterPath()
            p.addRect(item.rect())
        rot = getattr(item, "_rotation_transform", None)
        if rot is not None and getattr(item, "_angle", 0.0):
            p = rot().map(p)
        return p
    # Ellipse items (CircleItem, Node marker ring).
    if isinstance(item, QGraphicsEllipseItem):
        gcp = getattr(item, "get_closed_path", None)
        if gcp and gcp() is not None:
            return QPainterPath(gcp())
        p = QPainterPath()
        p.addEllipse(item.rect())
        return p
    # Polygon items (Room).
    if isinstance(item, QGraphicsPolygonItem):
        p = QPainterPath()
        p.addPolygon(item.polygon())
        p.closeSubpath()
        return p
    return item.shape()


def _halo_local(item, scene_scale=None):
    """Local-space trace: the composite ``halo_trace_path`` hook when present,
    else the type-based :func:`_halo_trace_path_local` dispatch."""
    hook = getattr(item, "halo_trace_path", None)
    if callable(hook):
        try:
            local = hook(scene_scale)
        except Exception:
            local = None
        if local is not None and not local.isEmpty():
            return local
    return _halo_trace_path_local(item)


def halo_scene_path(item, scene_scale=None):
    """The item's traced primitive geometry mapped to scene coords via Qt's
    canonical sceneTransform (respects pos()/transform(); does NOT re-apply
    baked-rotation that the local trace already contains — unlike the items'
    overridden mapToScene).

    Composite items (gridlines, dimensions, …) may expose a ``halo_trace_path``
    hook returning a QPainterPath (in the item's local space) that unions all
    their constituent primitives — the same way a ``BlockInstance``'s ``shape()``
    is the union of its render-op paths. ``scene_scale`` is the view's
    scene→device scale, passed through for screen-fixed sub-parts (e.g. a
    gridline's ``ItemIgnoresTransformations`` bubbles). Falls back to the
    type-based :func:`_halo_trace_path_local` dispatch."""
    return item.sceneTransform().map(_halo_local(item, scene_scale))


def halo_is_area(item) -> bool:
    """True when a cursor INSIDE the item's trace is a direct hit (distance 0).

    Areas: filled 2D geometry (``fill_type != "none"``), classes flagged
    ``HALO_AREA = True`` (walls, slabs, roofs, openings, rooms, nodes), and any
    item whose trace falls back to ``shape()`` (text boxes, SVG, blocks).
    Open geometry (lines, arcs, unfilled outlines) is measured to its stroke —
    ``QPainterPath.contains`` implicitly closes open paths, so it must not be
    used for them.
    """
    fill = getattr(item, "fill_type", None)
    if fill is not None and fill != "none":
        return True
    if getattr(item, "HALO_AREA", False):
        return True
    if callable(getattr(item, "halo_trace_path", None)):
        return False
    if isinstance(item, QGraphicsPathItem):
        return item.path().isEmpty()        # empty path -> shape() fallback
    return not isinstance(item, _TRACED_TYPES)


def _seg_dist(p, a, b):
    """Minimum distance from point *p* to segment *a*-*b* (clamped projection).

    Private mirror of ``tool_geometry.point_to_segment_dist`` — kept local
    rather than imported so ``halo.py`` (imported by the scene/view modules on
    every hover) doesn't pull in ``tool_geometry``'s ``geometry_2d`` item-class
    dependency.
    """
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    proj_x = a.x() + t * dx
    proj_y = a.y() + t * dy
    return math.hypot(p.x() - proj_x, p.y() - proj_y)


def halo_pick_distance_px(item, cursor_vp, dt) -> float:
    """Screen-px distance from *cursor_vp* (viewport coords) to *item*'s drawn
    trace — the SNAP acceptance model (snapping-engine.md §6.1), judged in
    pixels via ``item.deviceTransform(dt)`` so it is zoom-invariant and correct
    for ``ItemIgnoresTransformations`` markers. 0.0 inside an area item;
    ``math.inf`` when the item has no traceable geometry.
    """
    scale = max(abs(dt.m11()), abs(dt.m22()), 1e-9)
    try:
        dev = item.deviceTransform(dt).map(_halo_local(item, scale))
    except RuntimeError:  # C++ object deleted mid-hover
        return math.inf
    if dev.isEmpty():
        return math.inf
    if halo_is_area(item) and dev.contains(cursor_vp):
        return 0.0
    cx, cy = cursor_vp.x(), cursor_vp.y()
    best = math.inf
    for poly in dev.toSubpathPolygons():
        n = len(poly)
        if n == 1:
            p = poly[0]
            best = min(best, math.hypot(cx - p.x(), cy - p.y()))
        for i in range(n - 1):
            best = min(best, _seg_dist(cursor_vp, poly[i], poly[i + 1]))
    return best


def paint_halo_highlight(painter, view, item, theme, *,
                         token=HALO_TRACE_COLOR, width=HALO_TRACE_WIDTH_PX,
                         alpha=HALO_TRACE_ALPHA, glow_px=HALO_GLOW_PX):
    """Trace *item*'s primitive geometry with a semi-transparent accent line
    plus a soft outer glow, in scene coords.

    The glow is a QPainter-level approximation of a gaussian blur: a few
    progressively wider, fainter cosmetic strokes under the crisp core line
    (``drawForeground`` has no filter/effect pipeline)."""
    if item is None:
        return
    # Scene→device scale for screen-fixed composite sub-parts (e.g. gridline
    # bubbles); matches the source GridlineItem.paint() uses for its geometry.
    dt = painter.deviceTransform()
    scene_scale = max(abs(dt.m11()), abs(dt.m22()), 1e-9)
    try:
        path = halo_scene_path(item, scene_scale)
    except Exception:
        return
    if path.isEmpty():
        return
    base = theme.color(token)
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)

    def _pen(w, a):
        c = QColor(base)
        c.setAlpha(max(0, min(255, int(round(a)))))
        pen = QPen(c, w)
        pen.setCosmetic(True)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        return pen

    if glow_px > 0:
        layers = 4
        for i in range(layers, 0, -1):
            frac = i / layers                       # 1.0 (outer) .. 0.25 (inner)
            w = width + glow_px * 2.0 * frac
            a = alpha * (0.05 + 0.20 * (1.0 - frac))
            painter.setPen(_pen(w, a))
            painter.drawPath(path)

    painter.setPen(_pen(width, alpha))
    painter.drawPath(path)
    painter.restore()


def paint_rubber_band(painter, view, rb_start, rb_end, theme):
    """Draw the direction-dependent scene-drawn band in viewport coords.

    L->R = window (theme 'band_window', blue, solid); R->L = crossing
    (theme 'band_crossing', green, dashed). Caller guards rb_active/rb_end
    and passes viewport-px points.
    """
    painter.save()
    painter.resetTransform()
    crossing = rb_end.x() < rb_start.x()
    base = theme.color("band_crossing" if crossing else "band_window")
    pen = QPen(base, 1)
    pen.setStyle(Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine)
    painter.setPen(pen)
    fill = QColor(base); fill.setAlpha(40)
    painter.setBrush(fill)
    painter.drawRect(QRectF(QPointF(rb_start), QPointF(rb_end)).normalized())
    painter.restore()
