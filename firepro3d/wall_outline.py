"""Pure wall-outline geometry (wall polish design D2, D5, D6).

No scene queries and no graphics items: callers pass face lines and
polygons; results are plain QPointF / QPolygonF / QPainterPath values.
``WallSegment`` (wall.py) owns the per-wall cache and the scene queries.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPolygonF

from .constants import WALL_OUTLINE_MIN_SEG, WALL_OUTLINE_ON_EDGE_TOL

Line = tuple[QPointF, QPointF]


@dataclass(frozen=True)
class JunctionArm:
    """One wall end at a junction.

    Attributes:
        key: Caller identity (the wall); keys the returned corners.
        ux: Unit vector x, from the junction outward along the wall.
        uy: Unit vector y.
        ccw_face: Face line on the +90 deg side of (ux, uy).
        cw_face: Face line on the -90 deg side of (ux, uy).
    """
    key: object
    ux: float
    uy: float
    ccw_face: Line
    cw_face: Line


@dataclass
class WallOutline:
    """One wall's cached outline (design D2).

    Attributes:
        body: Own mitered polygon -- fill, hatch clip, HALO, hit area.
        union_body: ``body`` with tee ends run to the host centerline;
            used only for the cluster union (G0).
        quad: Mitered corners (p1l, p1r, p2r, p2l) -- ``mitered_quad()``.
        solid: Per-end flags (pt1, pt2): the end edge is joined.
        wedge: Per-end extra polygon vertices (pt1 list, pt2 list).
        faces: (left p1l->p2l, right p1r->p2r) full face lines.
        caps: End edges on free ends only.
        centerline: True alignment-correct centerline (pt1, pt2).
        neighbours: Walls whose union bodies shape this outline.
        stroke_segments: Outline pieces this wall strokes (lazy).
        corners: Visible outline corners on this wall (lazy).
    """
    body: QPolygonF
    union_body: QPolygonF
    quad: tuple[QPointF, QPointF, QPointF, QPointF]
    solid: tuple[bool, bool]
    wedge: tuple[list[QPointF], list[QPointF]]
    faces: tuple[Line, Line]
    caps: tuple[Line, ...]
    centerline: Line
    neighbours: tuple
    stroke_segments: list[Line] | None = None
    corners: list[QPointF] | None = None


def intersect_lines(p1: QPointF, p2: QPointF,
                    p3: QPointF, p4: QPointF) -> QPointF | None:
    """Intersect infinite lines (p1->p2) and (p3->p4); None if parallel."""
    dx1, dy1 = p2.x() - p1.x(), p2.y() - p1.y()
    dx2, dy2 = p4.x() - p3.x(), p4.y() - p3.y()
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-10:
        return None
    t = ((p3.x() - p1.x()) * dy2 - (p3.y() - p1.y()) * dx2) / denom
    return QPointF(p1.x() + t * dx1, p1.y() + t * dy1)


def _foot(pt: QPointF, a: QPointF, b: QPointF) -> QPointF:
    """Projection of pt onto the infinite line a->b."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-18:
        return QPointF(a)
    t = ((pt.x() - a.x()) * dx + (pt.y() - a.y()) * dy) / len_sq
    return QPointF(a.x() + t * dx, a.y() + t * dy)


def junction_pie(arms: list[JunctionArm], junction: QPointF,
                 max_miter: float):
    """N-way full miter (design D5) for three or more arms.

    Arms are sorted by angle; arm i's ccw face meets arm i+1's cw face at
    a shared junction corner.  Parallel facing faces (a straight-through
    pair) use the foot of the junction on each face instead (pairwise
    rule).  Each wall's slice runs to the hub, the centroid of all
    junction corners, so slices tile the core without overlap (D7).

    Args:
        arms: One arm per wall end at the junction.
        junction: The shared endpoint.
        max_miter: A corner this far or farther from the junction aborts.

    Returns:
        ``({key: (ccw_corner, cw_corner)}, hub)``, or None for fewer than
        three arms or a corner beyond *max_miter* (caller falls back to
        Butt, as today's 3-wall pie does).
    """
    if len(arms) < 3:
        return None
    order = sorted(arms, key=lambda a: math.atan2(a.uy, a.ux))
    n = len(order)
    ccw_c: list[QPointF | None] = [None] * n
    cw_c: list[QPointF | None] = [None] * n
    for i, a in enumerate(order):
        j = (i + 1) % n
        b = order[j]
        c = intersect_lines(*a.ccw_face, *b.cw_face)
        if c is None:
            ccw_c[i] = _foot(junction, *a.ccw_face)
            cw_c[j] = _foot(junction, *b.cw_face)
            continue
        if math.hypot(c.x() - junction.x(),
                      c.y() - junction.y()) >= max_miter:
            return None
        ccw_c[i] = c
        cw_c[j] = QPointF(c)
    pts = ccw_c + cw_c
    hub = QPointF(sum(p.x() for p in pts) / len(pts),
                  sum(p.y() for p in pts) / len(pts))
    return {order[i].key: (ccw_c[i], cw_c[i]) for i in range(n)}, hub


def cluster_union(polys: list[QPolygonF]) -> QPainterPath:
    """Simplified union of a cluster's union bodies (design D6)."""
    u = QPainterPath()
    for poly in polys:
        p = QPainterPath()
        p.addPolygon(poly)
        p.closeSubpath()
        u = u.united(p)
    return u.simplified()


def boundary_segments(path: QPainterPath) -> list[Line]:
    """Every non-degenerate boundary segment of a polygonal path."""
    segs: list[Line] = []
    for poly in path.toSubpathPolygons():
        for i in range(poly.count() - 1):
            a, b = poly.at(i), poly.at(i + 1)
            if math.hypot(b.x() - a.x(), b.y() - a.y()) > 0.0:
                segs.append((QPointF(a), QPointF(b)))
    return segs


def _dist_to_line(pt: QPointF, a: QPointF, b: QPointF, length: float):
    return abs((pt.x() - a.x()) * (b.y() - a.y())
               - (pt.y() - a.y()) * (b.x() - a.x())) / length


def _edges(body: QPolygonF):
    n = body.count()
    if n > 1 and body.at(0) == body.at(n - 1):
        n -= 1
    for i in range(n):
        yield body.at(i), body.at((i + 1) % n)


def stroke_segments(body: QPolygonF, boundary: list[Line],
                    tol: float = WALL_OUTLINE_ON_EDGE_TOL,
                    min_seg: float = WALL_OUTLINE_MIN_SEG) -> list[Line]:
    """The union-boundary pieces lying on this wall's own body edges (D6).

    For each body edge, boundary segments collinear with it (both ends
    within *tol* of its line) are projected onto it, clipped to the edge
    span, merged, and kept when at least *min_seg* long.
    """
    out: list[Line] = []
    for p, q in _edges(body):
        dx, dy = q.x() - p.x(), q.y() - p.y()
        length = math.hypot(dx, dy)
        if length < min_seg:
            continue
        spans = []
        for a, b in boundary:
            if (_dist_to_line(a, p, q, length) > tol
                    or _dist_to_line(b, p, q, length) > tol):
                continue
            ta = ((a.x() - p.x()) * dx + (a.y() - p.y()) * dy) / length
            tb = ((b.x() - p.x()) * dx + (b.y() - p.y()) * dy) / length
            lo, hi = max(min(ta, tb), 0.0), min(max(ta, tb), length)
            if hi - lo >= min_seg:
                spans.append((lo, hi))
        spans.sort()
        merged: list[list[float]] = []
        for lo, hi in spans:
            if merged and lo <= merged[-1][1] + tol:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        ux, uy = dx / length, dy / length
        for lo, hi in merged:
            out.append((QPointF(p.x() + ux * lo, p.y() + uy * lo),
                        QPointF(p.x() + ux * hi, p.y() + uy * hi)))
    return out


def visible_corners(body: QPolygonF, boundary: list[Line],
                    tol: float = WALL_OUTLINE_ON_EDGE_TOL) -> list[QPointF]:
    """Union-outline vertices lying on this wall's body boundary (D2).

    Mitred junction corners are outline vertices and are kept; corners
    hidden inside a junction are not on the union boundary and drop out.
    """
    edges = [(p, q, math.hypot(q.x() - p.x(), q.y() - p.y()))
             for p, q in _edges(body)]
    out: list[QPointF] = []
    seen: set[tuple[float, float]] = set()
    for a, _b in boundary:
        k = (round(a.x() / tol), round(a.y() / tol))
        if k in seen:
            continue
        for p, q, length in edges:
            if length <= 0.0 or _dist_to_line(a, p, q, length) > tol:
                continue
            t = ((a.x() - p.x()) * (q.x() - p.x())
                 + (a.y() - p.y()) * (q.y() - p.y())) / length
            if -tol <= t <= length + tol:
                seen.add(k)
                out.append(QPointF(a))
                break
    return out
