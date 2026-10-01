"""Mirror-axis picker for Flip / Mirror (scene-tools P1 batch DD2).

``pick_axis`` returns the nearest *straight* scene segment under the cursor —
2D-geometry edges (line / reference line / polyline incl. a closed polyline's
closing edge / rectangle / regular polygon), gridlines, wall faces and
underlay geometry — or None. Curves (arc, circle, ellipse, spline and curve
elements of generic path items) never qualify. Pure: reads the scene, holds no
state. Segments come from ``SnapEngine._iter_geometry_segments`` — the one
home for per-type segment extraction (phase 4 + ALIGN) — so the picker sees
exactly the geometry the snap engine sees, but it is NOT a snap
(``snapping-engine.md`` §3: no contextual snap-by-tool).
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from .arc_math import yup_angle
from .geometry_2d import (LineItem, PolylineItem, RectangleItem,
                          RegularPolygonItem, _degenerate_axis)
from .gridline import GridlineItem
from .snap_engine import _is_underlay_group
from .wall import WallSegment

# Straight-edged 2D primitives (LineItem covers ReferenceLineItem).
_STRAIGHT_2D = (LineItem, PolylineItem, RectangleItem, RegularPolygonItem)
# Generic path items keep only their LineTo elements; keys are rounded so the
# generator's mapped points and the re-walked ones compare equal.
_KEY_DIGITS = 6


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
    """Whether *item* may supply an axis segment (the DD2 whitelist)."""
    if isinstance(item, (_STRAIGHT_2D, GridlineItem, WallSegment)):
        return True
    if _is_underlay_group(item):
        return True
    parent = item.parentItem()
    return parent is not None and _is_underlay_group(parent)


def _needs_straight_check(item) -> bool:
    """A generic path item (e.g. an un-indexed underlay child) may mix curves."""
    return (isinstance(item, QGraphicsPathItem)
            and not isinstance(item, (_STRAIGHT_2D, WallSegment)))


def _key(p: QPointF) -> tuple:
    return (round(p.x(), _KEY_DIGITS), round(p.y(), _KEY_DIGITS))


def _straight_keys(item) -> set:
    """``{(key(a), key(b))}`` for every LineTo segment of a generic path item.

    Mirrors the generator's element walk (same 511-element cap): a segment is
    straight iff its END element is a ``LineToElement``.
    """
    path = item.path()
    out = set()
    n = path.elementCount()
    for j in range(min(n - 1, 511)):
        e2 = path.elementAt(j + 1)
        if e2.type != QPainterPath.ElementType.LineToElement:
            continue
        e1 = path.elementAt(j)
        out.add((_key(item.mapToScene(QPointF(e1.x, e1.y))),
                 _key(item.mapToScene(QPointF(e2.x, e2.y)))))
    return out


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
    straight: dict[int, set] = {}
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
        if _needs_straight_check(src):
            keys = straight.get(id(src))
            if keys is None:
                keys = straight[id(src)] = _straight_keys(src)
            if (_key(a), _key(b)) not in keys:
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
    return best
