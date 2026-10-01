"""Mirror-axis picker for Flip / Mirror (scene-tools P1 batch DD2).

``pick_axis`` returns the nearest *straight* scene segment under the cursor —
2D-geometry edges (line / reference line / polyline incl. a closed polyline's
closing edge / rectangle / regular polygon), gridlines, wall faces and
straight underlay records — or None. Curves (arc, circle, ellipse, spline)
never qualify. Pure: reads the scene, holds no state. Scene-item segments come
from ``SnapEngine._iter_geometry_segments`` — the one home for per-type
segment extraction (phase 4 + ALIGN) — but the picker is NOT a snap
(``snapping-engine.md`` §3: no contextual snap-by-tool).

Underlays: import flattens DXF ARC / partial ELLIPSE / SPLINE and PDF Béziers
into ``path_points`` chords that look straight, so the generator's underlay
segments are not trusted. Instead the picker queries each underlay group's
``UnderlaySnapIndex`` (``data(4)``) itself and accepts only ``line`` records
and ``path_points`` records the importer tagged ``"straight": True``
(LWPOLYLINE / POLYLINE / SOLID; PDF records built purely from ``l`` / ``re``
/ ``qu``). A legacy cached record without the key is never an axis. Un-indexed
underlay children (no real import path produces them) are rejected outright.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QGraphicsItem

from .arc_math import yup_angle
from .geometry_2d import (LineItem, PolylineItem, RectangleItem,
                          RegularPolygonItem, _degenerate_axis)
from .gridline import GridlineItem
from .snap_engine import _is_underlay_group
from .underlay_snap_index import UnderlaySnapIndex
from .wall import WallSegment

# Straight-edged 2D primitives (LineItem covers ReferenceLineItem).
_STRAIGHT_2D = (LineItem, PolylineItem, RectangleItem, RegularPolygonItem)


@dataclass
class AxisPick:
    """A picked mirror axis.

    Attributes:
        p1: Scene start of the source segment.
        p2: Scene end of the source segment.
        source: The item the segment belongs to (an underlay group for
            index-backed underlay segments).
        angle_deg: Y-up heading of p1 -> p2 (``arc_math.yup_angle``); the
            infinite axis is the line through p1 and p2.
    """
    p1: QPointF
    p2: QPointF
    source: QGraphicsItem
    angle_deg: float


def _is_axis_source(item) -> bool:
    """Whether a scene item may supply an axis segment (the DD2 whitelist).

    Underlay groups and their children are excluded here: underlay segments
    come only from :func:`_underlay_segments` (straight-tagged records).
    """
    return isinstance(item, (_STRAIGHT_2D, GridlineItem, WallSegment))


def _record_segments(g: dict):
    """Local ``(a, b)`` point pairs of a straight underlay record, or none.

    ``line`` records are straight by kind; ``path_points`` records only when
    tagged ``"straight": True`` (closed ones include their closing edge).
    """
    kind = g.get("kind")
    if kind == "line":
        yield (g["x1"], g["y1"]), (g["x2"], g["y2"])
    elif kind == "path_points" and g.get("straight") is True:
        pts = g.get("points", [])
        for k in range(len(pts) - 1):
            yield pts[k], pts[k + 1]
        if g.get("closed") and len(pts) >= 3:
            yield pts[-1], pts[0]


def _underlay_groups(scene, rect: QRectF):
    """Visible, index-backed underlay groups whose bounds meet *rect*."""
    seen: set[int] = set()
    mode = Qt.ItemSelectionMode.IntersectsItemBoundingRect
    for item in scene.items(rect, mode):
        grp = item if _is_underlay_group(item) else item.parentItem()
        if grp is None or not _is_underlay_group(grp) or id(grp) in seen:
            continue
        seen.add(id(grp))
        if grp.isVisible() and isinstance(grp.data(4), UnderlaySnapIndex):
            yield grp


def _underlay_segments(scene, rect: QRectF):
    """``(a, b, group)`` scene segments of straight underlay records near *rect*."""
    for grp in _underlay_groups(scene, rect):
        xf = grp.sceneTransform()
        inv, ok = xf.inverted()
        if not ok:
            continue
        lr = inv.mapRect(rect)
        for g in grp.data(4).query(lr.x(), lr.y(), lr.width(), lr.height()):
            for a, b in _record_segments(g):
                yield (xf.map(QPointF(a[0], a[1])), xf.map(QPointF(b[0], b[1])),
                       grp)


def _seg_distance(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Distance from *p* to the finite segment a-b (inf when degenerate).

    "Degenerate" is the commit path's own test
    (``geometry_2d._degenerate_axis``), so the picker never offers an axis
    that ``manip_reflect`` would then ignore.
    """
    if _degenerate_axis(a, b):
        return float("inf")
    dx, dy = b.x() - a.x(), b.y() - a.y()
    l2 = dx * dx + dy * dy
    t = ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / l2
    t = max(0.0, min(1.0, t))
    fx, fy = a.x() + t * dx - p.x(), a.y() + t * dy - p.y()
    return (fx * fx + fy * fy) ** 0.5


def pick_axis(scene, cursor: QPointF, tol: float, exclude=None) -> "AxisPick | None":
    """Nearest visible straight segment within *tol* of *cursor*, or None.

    Args:
        scene: The model scene (``Model_Space``) to search.
        cursor: The raw cursor in scene coordinates.
        tol: Pick radius in scene units (callers convert the snap aperture
            from the ACTIVE view's scale — never ``views()[0]``).
        exclude: Optional iterable of items whose segments are skipped. The
            Flip / Mirror tools pass None: the selection's own edges are valid
            axes (DD2).

    Returns:
        The nearest pick (ties keep the first found), or None.
    """
    from .snap_engine import SnapEngine, _SnapCtx
    engine = getattr(scene, "_snap_engine", None) or SnapEngine()
    skip = {id(it) for it in (exclude or ())}
    rect = QRectF(cursor.x() - tol, cursor.y() - tol, 2.0 * tol, 2.0 * tol)
    gl_items = [gl for gl in getattr(scene, "_gridlines", []) if gl.isVisible()]
    ctx = _SnapCtx(cursor=cursor, scale=1.0, aperture_px=0.0,
                   priority_band_px=0.0)
    best: "AxisPick | None" = None
    best_d = tol
    closed_done: set[int] = set()

    def consider(a: QPointF, b: QPointF, src) -> None:
        nonlocal best, best_d
        d = _seg_distance(cursor, a, b)
        if d <= best_d and (best is None or d < best_d):
            best_d = d
            best = AxisPick(QPointF(a), QPointF(b), src, yup_angle(a, b))

    for kind, rec in engine._iter_geometry_segments(scene, rect, None,
                                                    gl_items, None, ctx):
        if kind != "seg":
            continue                      # circles are never an axis
        a, b, src, _pk = rec
        if id(src) in skip or not src.isVisible() or not _is_axis_source(src):
            continue
        consider(a, b, src)
        # The generator walks a polyline's vertex chain only; a closed
        # polyline's closing edge is an edge too (DD2: the selection's own
        # edges count).
        if (isinstance(src, PolylineItem) and src.is_closed()
                and id(src) not in closed_done):
            closed_done.add(id(src))
            pts = src._points
            consider(src.mapToScene(pts[-1]), src.mapToScene(pts[0]), src)
    for a, b, grp in _underlay_segments(scene, rect):
        if id(grp) not in skip:
            consider(a, b, grp)
    return best
