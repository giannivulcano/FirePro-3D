"""Pure floor cut-region geometry: slab minus voids, holed triangulation, cut spans.

Qt geometry types only (QPointF / QPolygonF / QPainterPath) -- no widgets, no
scene. Design: docs/superpowers/specs/2026-10-30-floor-opening-design.md (A3).
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPolygonF

from .geometry_utils import triangulate_polygon
from .wall_outline import _poly_path   # snaps operands to WALL_OUTLINE_SNAP

Ring = list[QPointF]
CutRing = tuple[Ring, list[Ring]]


def signed_area(ring) -> float:
    """Shoelace signed area of a ring of QPointF or (x, y) tuples.

    Args:
        ring: Vertices in order (open ring; no closing duplicate).

    Returns:
        Positive when the ring is counter-clockwise in its own axes.
    """
    xy = [(p.x(), p.y()) if isinstance(p, QPointF) else p for p in ring]
    n = len(xy)
    return 0.5 * sum(xy[i][0] * xy[(i + 1) % n][1] - xy[(i + 1) % n][0] * xy[i][1]
                     for i in range(n))


def _point_in_ring(x: float, y: float, ring: Ring) -> bool:
    """Even-odd ray cast of (x, y) against one ring of QPointF."""
    inside = False
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        ay, by = a.y(), b.y()
        if (ay > y) != (by > y):
            xc = a.x() + (y - ay) * (b.x() - a.x()) / (by - ay)
            if x < xc:
                inside = not inside
    return inside


def _ring_of(poly: QPolygonF) -> Ring:
    """A clipper subpath polygon as an open ring (closing duplicate dropped)."""
    pts = [QPointF(poly.at(i)) for i in range(poly.count())]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def _inside(inner: Ring, outer: Ring) -> bool:
    """True when most of *inner*'s vertices lie inside *outer*.

    Clipper output rings never cross, so a majority vote absorbs a vertex
    shared with (touching) the other ring.
    """
    hits = sum(_point_in_ring(p.x(), p.y(), outer) for p in inner)
    return hits * 2 > len(inner)


def cut_rings(slab_pts: list[QPointF],
              voids_pts: list[list[QPointF]]) -> list[CutRing]:
    """Slab polygon minus the union of its voids.

    Args:
        slab_pts: Slab boundary vertices (scene coords).
        voids_pts: One vertex list per void (scene coords); lists with fewer
            than 3 points are ignored.

    Returns:
        ``[(outer, [holes...]), ...]``, one entry per material piece. With no
        effective void the slab ring is returned as given (no boolean run).
        Empty when the voids swallow the slab.
    """
    if len(slab_pts) < 3:
        return []
    slab_ring = [QPointF(p) for p in slab_pts]
    slab_rect = QPolygonF(slab_ring).boundingRect()
    voids = [v for v in voids_pts if len(v) >= 3
             and QPolygonF(v).boundingRect().intersects(slab_rect)]
    if not voids:                                    # no-op boolean skipped
        return [(slab_ring, [])]
    union = QPainterPath()
    for v in voids:
        union = union.united(_poly_path(QPolygonF(v)))
    result = _poly_path(QPolygonF(slab_ring)).subtracted(union).simplified()
    rings = [r for r in (_ring_of(p) for p in result.toSubpathPolygons())
             if len(r) >= 3 and abs(signed_area(r)) > 1e-9]
    areas = [abs(signed_area(r)) for r in rings]
    depth = [sum(1 for j, o in enumerate(rings)
                 if j != i and areas[j] > areas[i] and _inside(r, o))
             for i, r in enumerate(rings)]
    out: list[CutRing] = []
    slot: dict[int, int] = {}
    for i in sorted(range(len(rings)), key=lambda k: depth[k]):
        if depth[i] % 2 == 0:                        # even nesting = material
            slot[i] = len(out)
            out.append((rings[i], []))
            continue
        parents = [j for j in range(len(rings))
                   if depth[j] == depth[i] - 1 and _inside(rings[i], rings[j])]
        if parents:
            owner = min(parents, key=lambda j: areas[j])
            out[slot[owner]][1].append(rings[i])
    return out


def _seg_cross(p, q, a, b) -> bool:
    """Proper crossing of segments p-q and a-b (touching endpoints excluded)."""
    def orient(o, s, t):
        return (s[0] - o[0]) * (t[1] - o[1]) - (s[1] - o[1]) * (t[0] - o[0])
    d1, d2 = orient(p, q, a), orient(p, q, b)
    d3, d4 = orient(a, b, p), orient(a, b, q)
    return d1 * d2 < 0 and d3 * d4 < 0


def triangulate_with_holes(outer, holes):
    """Triangulate *outer* minus *holes* by bridging each hole into the ring.

    Each hole (rightmost first) is joined to the current ring by the shortest
    vertex-to-vertex segment that crosses no ring or hole edge; the bridged
    single ring goes to ``geometry_utils.triangulate_polygon``.

    Args:
        outer: Outer ring, QPointF or (x, y) tuples, any winding.
        holes: Hole rings, same element types, any winding.

    Returns:
        ``(pts, tris)``: ``pts`` the bridged ring as ``(x, y)`` float tuples
        (bridge endpoints appear twice); ``tris`` index triples into ``pts``.
        ``([], [])`` when *outer* has fewer than 3 points.
    """
    def xy(ring):
        return [(p.x(), p.y()) if isinstance(p, QPointF) else (float(p[0]), float(p[1]))
                for p in ring]
    ring = xy(outer)
    if len(ring) < 3:
        return [], []
    if signed_area(ring) < 0:
        ring.reverse()                               # outer CCW
    hs = []
    for h in holes:
        h = xy(h)
        if len(h) >= 3:
            hs.append(h[::-1] if signed_area(h) > 0 else h)   # holes CW
    hole_edges = [(h[i], h[(i + 1) % len(h)]) for h in hs for i in range(len(h))]
    for h in sorted(hs, key=lambda r: -max(p[0] for p in r)):
        edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]
        edges += hole_edges
        best = None
        for j, hp in enumerate(h):
            for i, op in enumerate(ring):
                if any(_seg_cross(hp, op, a, b) for a, b in edges):
                    continue
                d = (hp[0] - op[0]) ** 2 + (hp[1] - op[1]) ** 2
                if best is None or d < best[0]:
                    best = (d, i, j)
        if best is None:
            continue
        _, i, j = best
        ring = ring[:i + 1] + h[j:] + h[:j + 1] + ring[i:]
    return ring, triangulate_polygon(ring)


def intervals_inside(rings: list[CutRing], a: QPointF,
                     b: QPointF) -> list[tuple[float, float]]:
    """Param spans ``(t0, t1)`` of segment a->b inside the cut region (even-odd).

    Args:
        rings: ``cut_rings`` output.
        a: Segment start (scene coords); t = 0.
        b: Segment end; t = 1.

    Returns:
        Disjoint ascending spans within [0, 1]; empty when the segment misses
        all material.
    """
    all_rings = [r for outer, holes in rings for r in (outer, *holes)]
    dx, dy = b.x() - a.x(), b.y() - a.y()
    ts = {0.0, 1.0}
    for r in all_rings:
        n = len(r)
        for i in range(n):
            p, q = r[i], r[(i + 1) % n]
            ex, ey = q.x() - p.x(), q.y() - p.y()
            den = dx * ey - dy * ex
            if abs(den) < 1e-12:
                continue                             # parallel edge: no crossing
            t = ((p.x() - a.x()) * ey - (p.y() - a.y()) * ex) / den
            u = ((p.x() - a.x()) * dy - (p.y() - a.y()) * dx) / den
            if 0.0 < t < 1.0 and -1e-12 <= u <= 1.0 + 1e-12:
                ts.add(t)
    cuts = sorted(ts)
    spans: list[tuple[float, float]] = []
    for t0, t1 in zip(cuts, cuts[1:]):
        if t1 - t0 < 1e-12:
            continue
        tm = 0.5 * (t0 + t1)
        x, y = a.x() + tm * dx, a.y() + tm * dy
        if sum(_point_in_ring(x, y, r) for r in all_rings) % 2 == 1:
            if spans and abs(spans[-1][1] - t0) < 1e-12:
                spans[-1] = (spans[-1][0], t1)       # merge touching spans
            else:
                spans.append((t0, t1))
    return spans
