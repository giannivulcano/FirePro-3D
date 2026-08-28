"""
tool_geometry.py
================
Pure, item-aware geometry helpers for the modify/draw tools.

Extracted from :class:`SceneToolsMixin` (``scene_tools.py``) as the first slice
of the Model_Space decomposition (see ``docs/specs/model-space-architecture.md``
§6, slice A). These functions take scene *items* and plain values and return
computed geometry — they hold **no** scene state, mutate **no** scene, and do
**no** I/O, so they are unit-testable in isolation.

Layering: this module sits *above* the item-agnostic primitives in
``cad_math.py`` (raw point math) and ``geometry_intersect.py`` (raw intersection
math) and *below* the interactive tool state-machines that remain on the scene.
It dispatches on ``construction_geometry`` item types, so it cannot live in
those lower modules without creating an import cycle.

``SceneToolsMixin`` retains thin wrappers that delegate here, so every existing
caller (and the ``tests/test_scene_tools.py`` parity net) is unchanged.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem

from .construction_geometry import (
    PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
)
from .constants import DEFAULT_LEVEL
from .cad_math import CAD_Math
from . import geometry_intersect as gi


def extract_edges(item) -> list[tuple[QPointF, QPointF]]:
    """Extract linear edge segments from a scene item.

    Returns a list of (QPointF, QPointF) tuples representing line segments
    in scene coordinates.  Handles gridlines, walls, pipes, construction
    geometry, polylines, and generic QGraphicsPathItems (DXF/PDF entities).

    Args:
        item: A QGraphicsItem or ``None``.

    Returns:
        List of ``(p1, p2)`` segment tuples.  Empty for unrecognised types.
    """
    if item is None:
        return []

    # Deferred imports to avoid circular dependencies
    from .gridline import GridlineItem
    from .wall import WallSegment
    from .pipe import Pipe
    from .construction_geometry import LineItem, PolylineItem

    # GridlineItem — single line segment
    if isinstance(item, GridlineItem):
        line = item.line()
        return [(line.p1(), line.p2())]

    # WallSegment — centerline + two face edges
    if isinstance(item, WallSegment):
        edges = [(QPointF(item._pt1), QPointF(item._pt2))]
        try:
            p1l, p1r, p2r, p2l = item.mitered_quad()
            edges.append((QPointF(p1l), QPointF(p2l)))
            edges.append((QPointF(p1r), QPointF(p2r)))
        except Exception:
            pass
        return edges

    # Pipe — node1 to node2
    if isinstance(item, Pipe):
        if item.node1 and item.node2:
            return [(item.node1.scenePos(), item.node2.scenePos())]
        return []

    # LineItem — use item.line() mapped to scene coords
    if isinstance(item, LineItem):
        line = item.line()
        p1 = item.mapToScene(line.p1())
        p2 = item.mapToScene(line.p2())
        return [(p1, p2)]

    # PolylineItem — consecutive _points mapped to scene coords
    if isinstance(item, PolylineItem):
        pts = getattr(item, "_points", [])
        if len(pts) < 2:
            return []
        edges = []
        for i in range(len(pts) - 1):
            p1 = item.mapToScene(pts[i])
            p2 = item.mapToScene(pts[i + 1])
            edges.append((p1, p2))
        return edges

    # Generic QGraphicsPathItem (DXF/PDF entities) — walk path elements
    if isinstance(item, QGraphicsPathItem):
        path = item.path()
        edges = []
        current = QPointF(0, 0)
        for i in range(path.elementCount()):
            el = path.elementAt(i)
            pt = QPointF(el.x, el.y)
            if el.type == QPainterPath.ElementType.MoveToElement:
                current = pt
            elif el.type == QPainterPath.ElementType.LineToElement:
                p1 = item.mapToScene(current)
                p2 = item.mapToScene(pt)
                edges.append((p1, p2))
                current = pt
            else:
                # Skip curve elements
                current = pt
        return edges

    return []


# ─────────────────────────────────────────────────────────────────────────────
# OFFSET math
# ─────────────────────────────────────────────────────────────────────────────

def offset_line_intersection(
    p1: QPointF, d1: QPointF, p2: QPointF, d2: QPointF
) -> "QPointF | None":
    """Return intersection of two infinite lines (p1+t*d1) and (p2+s*d2), or None.

    Ray form (point + direction), used by :func:`offset_polyline_pts` for miter
    joins — distinct from ``geometry_intersect``'s two-endpoint form.
    """
    denom = d1.x() * d2.y() - d1.y() * d2.x()
    if abs(denom) < 1e-10:
        return None  # parallel
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    t = (dx * d2.y() - dy * d2.x()) / denom
    return QPointF(p1.x() + t * d1.x(), p1.y() + t * d1.y())


def offset_polyline_pts(pts: list, signed_dist: float) -> list:
    """Return offset polyline points (miter join at corners)."""
    n = len(pts)
    if n < 2:
        return list(pts)
    # Per-segment left-side unit normals
    normals = []
    for i in range(n - 1):
        dx = pts[i + 1].x() - pts[i].x()
        dy = pts[i + 1].y() - pts[i].y()
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-10:
            normals.append(None)
        else:
            normals.append((-dy / seg_len, dx / seg_len))

    result = []
    for i in range(n):
        if i == 0:
            nx, ny = normals[0] if normals[0] else (0.0, 0.0)
            result.append(QPointF(pts[0].x() + signed_dist * nx,
                                  pts[0].y() + signed_dist * ny))
        elif i == n - 1:
            nx, ny = normals[-1] if normals[-1] else (0.0, 0.0)
            result.append(QPointF(pts[-1].x() + signed_dist * nx,
                                  pts[-1].y() + signed_dist * ny))
        else:
            n1 = normals[i - 1]
            n2 = normals[i]
            if n1 is None:
                n1 = n2
            if n2 is None:
                n2 = n1
            # Offset lines: p_prev + t*(pts[i]-pts[i-1]) + d*n1
            #               pts[i] + s*(pts[i+1]-pts[i]) + d*n2
            op1 = QPointF(pts[i - 1].x() + signed_dist * n1[0],
                          pts[i - 1].y() + signed_dist * n1[1])
            op2 = QPointF(pts[i].x() + signed_dist * n1[0],
                          pts[i].y() + signed_dist * n1[1])
            op3 = QPointF(pts[i].x() + signed_dist * n2[0],
                          pts[i].y() + signed_dist * n2[1])
            op4 = QPointF(pts[i + 1].x() + signed_dist * n2[0],
                          pts[i + 1].y() + signed_dist * n2[1])
            d1 = QPointF(op2.x() - op1.x(), op2.y() - op1.y())
            d2 = QPointF(op4.x() - op3.x(), op4.y() - op3.y())
            inter = offset_line_intersection(op1, d1, op3, d2)
            if inter is not None:
                result.append(inter)
            else:
                result.append(op2)  # fallback: parallel segments
    return result


def perpendicular_distance(source, pt: QPointF) -> float:
    """Return the perpendicular distance from *pt* to *source* entity."""
    if isinstance(source, LineItem):
        line = source.line()
        p1 = source.mapToScene(line.p1())
        p2 = source.mapToScene(line.p2())
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-10:
            return math.hypot(pt.x() - p1.x(), pt.y() - p1.y())
        # Point-to-line distance (not segment — infinite line)
        return abs(dx * (p1.y() - pt.y()) - dy * (p1.x() - pt.x())) / seg_len

    if isinstance(source, PolylineItem):
        pts = source._points
        if len(pts) < 2:
            return 0.0
        # Minimum distance to any segment
        min_d = float("inf")
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            dx, dy = b.x() - a.x(), b.y() - a.y()
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-10:
                continue
            d = abs(dx * (a.y() - pt.y()) - dy * (a.x() - pt.x())) / seg_len
            min_d = min(min_d, d)
        return min_d if min_d < float("inf") else 0.0

    if isinstance(source, CircleItem):
        cx = source.x() + source.boundingRect().center().x()
        cy = source.y() + source.boundingRect().center().y()
        r = source.boundingRect().width() / 2
        return abs(math.hypot(pt.x() - cx, pt.y() - cy) - r)

    if isinstance(source, RectangleItem):
        r = source.mapRectToScene(source.rect())
        # Distance to nearest edge
        cx = max(r.left(), min(pt.x(), r.right()))
        cy = max(r.top(), min(pt.y(), r.bottom()))
        if r.contains(pt):
            # Inside: distance to nearest edge
            return min(pt.x() - r.left(), r.right() - pt.x(),
                       pt.y() - r.top(), r.bottom() - pt.y())
        return math.hypot(pt.x() - cx, pt.y() - cy)

    if isinstance(source, ArcItem):
        cx, cy = source._center.x(), source._center.y()
        return abs(math.hypot(pt.x() - cx, pt.y() - cy) - source._radius)

    return 0.0


def offset_signed_dist(source, dist: float, side_pt: QPointF) -> float:
    """Return +dist or -dist depending on which side of source the cursor is on."""
    if isinstance(source, LineItem):
        line = source.line()
        p1 = source.mapToScene(line.p1())
        p2 = source.mapToScene(line.p2())
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        # Cross product with cursor vector: positive → left of line
        cross = dx * (side_pt.y() - p1.y()) - dy * (side_pt.x() - p1.x())
        return dist if cross >= 0 else -dist
    if isinstance(source, PolylineItem):
        pts = source._points
        if len(pts) < 2:
            return dist
        p1, p2 = pts[0], pts[1]
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        cross = dx * (side_pt.y() - p1.y()) - dy * (side_pt.x() - p1.x())
        return dist if cross >= 0 else -dist
    if isinstance(source, CircleItem):
        cx = source.x() + source.boundingRect().center().x()
        cy = source.y() + source.boundingRect().center().y()
        d = math.hypot(side_pt.x() - cx, side_pt.y() - cy)
        r = source.boundingRect().width() / 2
        return dist if d >= r else -dist
    if isinstance(source, RectangleItem):
        # cursor outside → grow, cursor inside → shrink
        r = source.mapRectToScene(source.rect())
        if r.contains(side_pt):
            return -dist
        return dist
    if isinstance(source, ArcItem):
        cx, cy = source._center.x(), source._center.y()
        d = math.hypot(side_pt.x() - cx, side_pt.y() - cy)
        return dist if d >= source._radius else -dist
    return dist


def make_offset_item(source, signed_dist: float):
    """Create and return a new item that is the offset of source, or None."""
    color = source.pen().color()
    lw = source.pen().widthF()

    if isinstance(source, LineItem):
        line = source.line()
        p1 = source.mapToScene(line.p1())
        p2 = source.mapToScene(line.p2())
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-10:
            return None
        nx, ny = -dy / seg_len, dx / seg_len
        new_p1 = QPointF(p1.x() + signed_dist * nx, p1.y() + signed_dist * ny)
        new_p2 = QPointF(p2.x() + signed_dist * nx, p2.y() + signed_dist * ny)
        item = LineItem(new_p1, new_p2, color, lw)
        item.level = getattr(source, "level", DEFAULT_LEVEL)
        return item

    if isinstance(source, PolylineItem):
        pts = source._points
        new_pts = offset_polyline_pts(pts, signed_dist)
        if len(new_pts) < 2:
            return None
        item = PolylineItem(new_pts[0], color, lw)
        for p in new_pts[1:]:
            item.append_point(p)
        if source.is_closed():
            item.close()
        item.level = getattr(source, "level", DEFAULT_LEVEL)
        return item

    if isinstance(source, CircleItem):
        r = source.boundingRect().width() / 2
        new_r = r + signed_dist
        if new_r <= 0:
            return None
        # CircleItem stores center as scene position of its bounding rect centre
        scene_rect = source.mapRectToScene(source.rect())
        cx = scene_rect.center().x()
        cy = scene_rect.center().y()
        item = CircleItem(QPointF(cx, cy), new_r, color, lw)
        item.level = getattr(source, "level", DEFAULT_LEVEL)
        return item

    if isinstance(source, RectangleItem):
        r = source.mapRectToScene(source.rect())
        new_r = r.adjusted(-signed_dist, -signed_dist, signed_dist, signed_dist)
        if new_r.width() <= 0 or new_r.height() <= 0:
            return None
        item = RectangleItem(new_r.topLeft(), new_r.bottomRight(), color, lw)
        item.level = getattr(source, "level", DEFAULT_LEVEL)
        return item

    if isinstance(source, ArcItem):
        new_r = source._radius + signed_dist
        if new_r <= 0:
            return None
        item = ArcItem(source._center, new_r,
                       source._start_deg, source._span_deg, color, lw)
        item.level = getattr(source, "level", DEFAULT_LEVEL)
        return item
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FILLET / CHAMFER math
# ─────────────────────────────────────────────────────────────────────────────

def compute_fillet(item1, item2, radius):
    """Compute fillet arc data between two line items. Returns dict or None."""
    if not isinstance(item1, LineItem) or not isinstance(item2, LineItem):
        return None
    ix = gi.line_line_intersection_unbounded(item1._pt1, item1._pt2,
                                             item2._pt1, item2._pt2)
    if ix is None:
        return None  # parallel lines
    # Determine which ends are near intersection
    def _near_end(item, ix):
        d1 = CAD_Math.get_vector_length(item._pt1, ix)
        d2 = CAD_Math.get_vector_length(item._pt2, ix)
        return ("_pt1", "_pt2") if d1 < d2 else ("_pt2", "_pt1")
    near1, far1 = _near_end(item1, ix)
    near2, far2 = _near_end(item2, ix)
    # Vectors from intersection along each line
    u1 = CAD_Math.get_unit_vector(ix, getattr(item1, far1))
    u2 = CAD_Math.get_unit_vector(ix, getattr(item2, far2))
    # Half-angle between the two lines
    dot = u1.x()*u2.x() + u1.y()*u2.y()
    dot = max(-1.0, min(1.0, dot))
    half = math.acos(dot) / 2
    if half < 1e-6:
        return None  # lines too close to parallel
    # Bisector
    bx = u1.x() + u2.x()
    by = u1.y() + u2.y()
    bl = math.hypot(bx, by)
    if bl < 1e-12:
        return None
    bx /= bl; by /= bl
    # Fillet center distance from intersection
    d = radius / math.sin(half)
    center = QPointF(ix.x() + bx * d, ix.y() + by * d)
    # Tangent points (perpendicular foot from center to each line)
    tp1 = CAD_Math.point_on_line_nearest(center, item1._pt1, item1._pt2)
    tp2 = CAD_Math.point_on_line_nearest(center, item2._pt1, item2._pt2)
    # Arc angles
    sa = math.degrees(math.atan2(tp1.y()-center.y(), tp1.x()-center.x()))
    ea = math.degrees(math.atan2(tp2.y()-center.y(), tp2.x()-center.x()))
    span = (ea - sa) % 360
    if span > 180:
        span -= 360
    return {"center": center, "radius": radius, "start": sa, "span": span,
            "tp1": tp1, "tp2": tp2,
            "item1": item1, "near1": near1,
            "item2": item2, "near2": near2}


def compute_chamfer(item1, item2, dist):
    """Compute chamfer data between two line items. Returns dict or None."""
    if not isinstance(item1, LineItem) or not isinstance(item2, LineItem):
        return None
    ix = gi.line_line_intersection_unbounded(item1._pt1, item1._pt2,
                                             item2._pt1, item2._pt2)
    if ix is None:
        return None
    def _near_end(item, ix):
        d1 = CAD_Math.get_vector_length(item._pt1, ix)
        d2 = CAD_Math.get_vector_length(item._pt2, ix)
        return ("_pt1", "_pt2") if d1 < d2 else ("_pt2", "_pt1")
    near1, far1 = _near_end(item1, ix)
    near2, far2 = _near_end(item2, ix)
    u1 = CAD_Math.get_unit_vector(ix, getattr(item1, far1))
    u2 = CAD_Math.get_unit_vector(ix, getattr(item2, far2))
    cp1 = QPointF(ix.x() + u1.x()*dist, ix.y() + u1.y()*dist)
    cp2 = QPointF(ix.x() + u2.x()*dist, ix.y() + u2.y()*dist)
    return {"cp1": cp1, "cp2": cp2,
            "item1": item1, "near1": near1,
            "item2": item2, "near2": near2}


# ─────────────────────────────────────────────────────────────────────────────
# SEGMENT / INTERSECTION helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_item_segments(item):
    """Return geometric representation of an item as list of tuples.
    Returns: [("line", p1, p2), ("circle", center, radius),
              ("arc", center, radius, start_deg, span_deg)]"""
    from .construction_geometry import (
        LineItem, CircleItem, ArcItem, RectangleItem, PolylineItem,
    )
    segs = []
    if isinstance(item, LineItem):
        grips = item.grip_points()
        segs.append(("line", grips[0], grips[2]))
    elif isinstance(item, CircleItem):
        segs.append(("circle", item._center, item._radius))
    elif isinstance(item, ArcItem):
        segs.append(("arc", item._center, item._radius,
                     item._start_deg, item._span_deg))
    elif isinstance(item, RectangleItem):
        grips = item.grip_points()
        # 9 grips: TL, TM, TR, RM, BR, BM, BL, LM, Center
        tl = grips[0]
        tr = grips[2]
        br = grips[4]
        bl = grips[6]
        segs.append(("line", tl, tr))
        segs.append(("line", tr, br))
        segs.append(("line", br, bl))
        segs.append(("line", bl, tl))
    elif isinstance(item, PolylineItem):
        pts = item._points
        for i in range(len(pts) - 1):
            segs.append(("line", QPointF(pts[i]), QPointF(pts[i + 1])))
    return segs


def compute_intersections(item, edge):
    """Compute intersection points between two geometry items."""
    results = []

    # Get segments/shapes from both items
    item_segs = get_item_segments(item)
    edge_segs = get_item_segments(edge)

    for seg in item_segs:
        for eseg in edge_segs:
            if seg[0] == "line" and eseg[0] == "line":
                pt = gi.line_line_intersection(
                    seg[1], seg[2], eseg[1], eseg[2])
                if pt:
                    results.append(pt)
            elif seg[0] == "line" and eseg[0] == "circle":
                pts = gi.line_circle_intersections(
                    seg[1], seg[2], eseg[1], eseg[2])
                results.extend(pts)
            elif seg[0] == "circle" and eseg[0] == "line":
                pts = gi.line_circle_intersections(
                    eseg[1], eseg[2], seg[1], seg[2])
                results.extend(pts)
            elif seg[0] == "line" and eseg[0] == "arc":
                pts = gi.line_arc_intersections(
                    seg[1], seg[2], eseg[1], eseg[2],
                    eseg[3], eseg[4])
                results.extend(pts)
            elif seg[0] == "arc" and eseg[0] == "line":
                pts = gi.line_arc_intersections(
                    eseg[1], eseg[2], seg[1], seg[2],
                    seg[3], seg[4])
                results.extend(pts)
    return results


def compute_extend_intersections(item, grip_idx, boundary):
    """Compute where *item* would intersect *boundary* if extended.

    Only returns intersections in the forward direction from the
    extending endpoint (away from the interior of the item).
    """
    from .construction_geometry import LineItem, PolylineItem

    raw_results: list[QPointF] = []
    extend_pt: QPointF | None = None
    direction: tuple[float, float] | None = None

    if isinstance(item, LineItem):
        grips = item.grip_points()
        p1, p2 = grips[0], grips[2]
        if grip_idx == 0:
            extend_pt, fixed_pt = p1, p2
        else:
            extend_pt, fixed_pt = p2, p1
        direction = (extend_pt.x() - fixed_pt.x(),
                     extend_pt.y() - fixed_pt.y())

        boundary_segs = get_item_segments(boundary)
        for bseg in boundary_segs:
            if bseg[0] == "line":
                pt = gi.line_line_intersection_unbounded(p1, p2, bseg[1], bseg[2])
                if pt:
                    raw_results.append(pt)
            elif bseg[0] == "circle":
                raw_results.extend(
                    gi.line_circle_intersections_unbounded(p1, p2, bseg[1], bseg[2]))
            elif bseg[0] == "arc":
                pts = gi.line_circle_intersections_unbounded(p1, p2, bseg[1], bseg[2])
                for pt in pts:
                    angle = math.degrees(math.atan2(
                        pt.y() - bseg[1].y(), pt.x() - bseg[1].x())) % 360
                    if gi._angle_in_arc(angle, bseg[3], bseg[4]):
                        raw_results.append(pt)

    elif isinstance(item, PolylineItem):
        vertices = item._points
        if len(vertices) < 2:
            return []
        if grip_idx == 0:
            extend_pt = vertices[0]
            neighbor = vertices[1]
        elif grip_idx == len(vertices) - 1:
            extend_pt = vertices[-1]
            neighbor = vertices[-2]
        else:
            return []  # cannot extend from interior vertex

        direction = (extend_pt.x() - neighbor.x(),
                     extend_pt.y() - neighbor.y())

        boundary_segs = get_item_segments(boundary)
        for bseg in boundary_segs:
            if bseg[0] == "line":
                pt = gi.line_line_intersection_unbounded(
                    neighbor, extend_pt, bseg[1], bseg[2])
                if pt:
                    raw_results.append(pt)
            elif bseg[0] == "circle":
                raw_results.extend(
                    gi.line_circle_intersections_unbounded(
                        neighbor, extend_pt, bseg[1], bseg[2]))
            elif bseg[0] == "arc":
                pts = gi.line_circle_intersections_unbounded(
                    neighbor, extend_pt, bseg[1], bseg[2])
                for pt in pts:
                    angle = math.degrees(math.atan2(
                        pt.y() - bseg[1].y(), pt.x() - bseg[1].x())) % 360
                    if gi._angle_in_arc(angle, bseg[3], bseg[4]):
                        raw_results.append(pt)

    # Filter to forward direction only
    if extend_pt is not None and direction is not None:
        dx, dy = direction
        forward = []
        for pt in raw_results:
            vx = pt.x() - extend_pt.x()
            vy = pt.y() - extend_pt.y()
            dot = vx * dx + vy * dy
            if dot > -1e-6:
                forward.append(pt)
        return forward if forward else raw_results

    return raw_results


def point_to_segment_dist(p, s1, s2):
    """Return the minimum distance from point *p* to segment *s1*-*s2*."""
    dx = s2.x() - s1.x()
    dy = s2.y() - s1.y()
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.hypot(p.x() - s1.x(), p.y() - s1.y())
    t = ((p.x() - s1.x()) * dx + (p.y() - s1.y()) * dy) / len_sq
    t = max(0.0, min(1.0, t))
    proj_x = s1.x() + t * dx
    proj_y = s1.y() + t * dy
    return math.hypot(p.x() - proj_x, p.y() - proj_y)
