"""
tool_geometry.py
================
Pure, item-aware geometry helpers for the modify/draw tools.

Extracted from :class:`SceneTools` (``scene_tools.py``) as the first slice
of the Model_Space decomposition (see ``docs/specs/model-space-architecture.md``
§6, slice A). These functions take scene *items* and plain values and return
computed geometry — they hold **no** scene state, mutate **no** scene, and do
**no** I/O, so they are unit-testable in isolation.

Layering: this module sits *above* the item-agnostic primitives in
``cad_math.py`` (raw point math) and ``geometry_intersect.py`` (raw intersection
math) and *below* the interactive tool state-machines that remain on the scene.
It dispatches on ``geometry_2d`` item types, so it cannot live in
those lower modules without creating an import cycle.

``SceneTools`` retains thin wrappers that delegate here, so every existing
caller (and the ``tests/test_scene_tools.py`` parity net) is unchanged.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem

from .geometry_2d import (
    PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
    ReferenceLineItem, RegularPolygonItem, EllipseItem, SplineItem,
)
from .geometry_2d import _AXIS_MIN as _ELLIPSE_AXIS_MIN
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
    from .geometry_2d import LineItem, PolylineItem

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
    if isinstance(source, (PolylineItem, SplineItem)):
        # Open chains: the side of the segment NEAREST the cursor decides
        # (scene-tools.md D9 "cursor sets side"), not the first segment. A
        # spline measures against its drawn curve, a polyline its vertices.
        if isinstance(source, PolylineItem):
            pts = list(source._points)
            segs = list(zip(pts, pts[1:]))
        else:
            segs = _path_segments(source)
        segs = [(a, b) for a, b in segs
                if math.hypot(b.x() - a.x(), b.y() - a.y()) > 1e-10]
        if not segs:
            return dist
        p1, p2 = min(segs, key=lambda s: point_to_segment_dist(side_pt, *s))
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
        # cursor outside → grow, cursor inside → shrink (tested in the
        # rect's local frame so a rotated rect uses its real footprint).
        if source.rect().contains(source.mapFromScene(side_pt)):
            return -dist
        return dist
    if isinstance(source, ArcItem):
        cx, cy = source._center.x(), source._center.y()
        d = math.hypot(side_pt.x() - cx, side_pt.y() - cy)
        return dist if d >= source._radius else -dist
    return dist


# ─────────────────────────────────────────────────────────────────────────────
# OFFSET (scene-tools.md D9) — offset_item + its cursor measures
# ─────────────────────────────────────────────────────────────────────────────

# One degenerate floor for every inward offset (review G7 M-2): a result whose
# defining half-extent (radius, semi-axis, apothem, half-width, half an edge)
# would be at or below this is refused ("Offset too large"). Matches the
# ellipse anti-degeneracy floor; the circle keeps its own larger 1 mm floor.
OFFSET_MIN_EXTENT_MM = _ELLIPSE_AXIS_MIN

def inset_polygon(pts: list, dist: float) -> "list[QPointF] | None":
    """Offset a closed polygon inward by *dist* (negative = outward).

    Mitered at every vertex, including the seam (vertex 0 against n-1), and
    winding-aware. Promoted from ``Model_Space._inset_polygon`` so room
    detection and the Offset tool share one implementation.

    Args:
        pts: The polygon vertices (implicitly closed; no duplicate last point).
        dist: Inward distance; negative grows the polygon.

    Returns:
        The offset vertices, or None for fewer than 3 vertices.
    """
    import math as _m
    n = len(pts)
    if n < 3:
        return None

    # Compute inward normals for each edge
    normals = []
    for i in range(n):
        j = (i + 1) % n
        dx = pts[j].x() - pts[i].x()
        dy = pts[j].y() - pts[i].y()
        length = _m.hypot(dx, dy)
        if length < 1e-12:
            normals.append((0.0, 0.0))
            continue
        # Inward normal (assuming CW winding for scene Y-down)
        nx = dy / length
        ny = -dx / length
        normals.append((nx, ny))

    # Check winding: if polygon area is positive (CCW), flip normals
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i].x() * pts[j].y() - pts[j].x() * pts[i].y()
    if area > 0:  # CCW winding
        normals = [(-nx, -ny) for nx, ny in normals]

    # Offset each edge inward and intersect consecutive offset edges
    result = []
    for i in range(n):
        prev = (i - 1) % n
        # Previous edge offset line
        p1 = QPointF(pts[prev].x() + normals[prev][0] * dist,
                     pts[prev].y() + normals[prev][1] * dist)
        p2 = QPointF(pts[i].x() + normals[prev][0] * dist,
                     pts[i].y() + normals[prev][1] * dist)
        # Current edge offset line
        p3 = QPointF(pts[i].x() + normals[i][0] * dist,
                     pts[i].y() + normals[i][1] * dist)
        p4 = QPointF(pts[(i + 1) % n].x() + normals[i][0] * dist,
                     pts[(i + 1) % n].y() + normals[i][1] * dist)
        # Intersect
        dx1 = p2.x() - p1.x()
        dy1 = p2.y() - p1.y()
        dx2 = p4.x() - p3.x()
        dy2 = p4.y() - p3.y()
        denom = dx1 * dy2 - dy1 * dx2
        if abs(denom) < 1e-10:
            result.append(QPointF(pts[i].x() + normals[i][0] * dist,
                                  pts[i].y() + normals[i][1] * dist))
        else:
            t = ((p3.x() - p1.x()) * dy2 - (p3.y() - p1.y()) * dx2) / denom
            result.append(QPointF(p1.x() + t * dx1, p1.y() + t * dy1))

    return result


def _path_segments(item) -> list:
    """Scene-coord segments approximating *item*'s drawn geometry (HALO trace)."""
    from .halo import halo_scene_path
    segs = []
    for poly in halo_scene_path(item).toSubpathPolygons():
        pts = [poly.at(i) for i in range(poly.count())]
        segs += list(zip(pts, pts[1:]))
    return segs


def distance_to_item(item, pt: QPointF) -> float:
    """True distance from *pt* to *item*'s drawn geometry.

    Measured to finite segments (never infinite lines); a circle is measured
    analytically to its geometric radius.

    Args:
        item: A 2D geometry item.
        pt: Scene point.

    Returns:
        The distance in scene units (mm); 0.0 for an item with no geometry.
    """
    if isinstance(item, CircleItem):
        c = item._center
        return abs(math.hypot(pt.x() - c.x(), pt.y() - c.y()) - item._radius)
    segs = _path_segments(item)
    return min((point_to_segment_dist(pt, a, b) for a, b in segs), default=0.0)


def _is_closed_shape(item) -> bool:
    """True for shapes whose offset side is inside/outside (D9)."""
    return (isinstance(item, (RectangleItem, CircleItem, RegularPolygonItem,
                              EllipseItem))
            or (isinstance(item, (PolylineItem, SplineItem))
                and item.is_closed()))


def _offset_closed_loop(pts, d):
    """Mitered offset of a closed vertex loop (+d outward), or None if it
    collapses, inverts or leaves an edge at/below the degenerate floor."""
    new_pts = inset_polygon(pts, -d)
    if new_pts is None or not _inset_ok(pts, new_pts):
        return None
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        src_len = math.hypot(pts[j].x() - pts[i].x(), pts[j].y() - pts[i].y())
        new_len = math.hypot(new_pts[j].x() - new_pts[i].x(),
                             new_pts[j].y() - new_pts[i].y())
        if src_len > 2 * OFFSET_MIN_EXTENT_MM and new_len <= 2 * OFFSET_MIN_EXTENT_MM:
            return None
    return new_pts


def offset_side_sign(item, pt: QPointF) -> float:
    """Which side of *item* the cursor *pt* picks.

    Returns:
        +1.0 = outward (closed shapes) / the left-normal side (open lines,
        polylines, splines) / away from the centre (arcs); -1.0 otherwise.
    """
    if _is_closed_shape(item):
        return -1.0 if item.get_closed_path().contains(item.mapFromScene(pt)) else 1.0
    return 1.0 if offset_signed_dist(item, 1.0, pt) > 0 else -1.0


def _clone(item):
    """Style-preserving copy (colour, lineweight, fill, layer, flags) via the
    item's own serialisation — the same round-trip Paste / Duplicate use."""
    return type(item).from_dict(item.to_dict())


def offset_item(src, signed_d: float):
    """Offset copy of *src* (scene-tools.md D9); the source is untouched.

    Args:
        src: A 2D geometry item.
        signed_d: Offset distance; + = outward (closed shapes, arcs) or the
            left-normal side (lines, open polylines, splines).

    Returns:
        A new, scene-less item of the source's type inheriting its style, or
        None when the offset is degenerate (too large inward) or *src* is not
        offsettable (Text, non-geometry).
    """
    d = float(signed_d)
    if not math.isfinite(d):
        return None
    # ReferenceLineItem subclasses LineItem: one branch, and _clone keeps the
    # exact type (a RefLine offsets to a RefLine).
    if isinstance(src, LineItem):
        a, b = src._pt1, src._pt2
        dx, dy = b.x() - a.x(), b.y() - a.y()
        L = math.hypot(dx, dy)
        if L < 1e-10:
            return None
        new = _clone(src)
        new.translate(-dy / L * d, dx / L * d)
        return new
    if isinstance(src, PolylineItem):
        pts = list(src._points)
        if src.is_closed():
            new_pts = _offset_closed_loop(pts, d)
        else:
            new_pts = offset_polyline_pts(pts, d)
        if not new_pts or len(new_pts) < 2:
            return None
        new = _clone(src)
        new._points = [QPointF(p) for p in new_pts]
        new._rebuild_path()
        return new
    if isinstance(src, RectangleItem):
        r = src.rect().adjusted(-d, -d, d, d)
        if min(r.width(), r.height()) / 2 <= OFFSET_MIN_EXTENT_MM:
            return None
        new = _clone(src)
        new.prepareGeometryChange()
        new.setRect(r)
        # _clone restored angle + pivot; a centre-following pivot (None)
        # re-derives from the unchanged centre, an explicit one stays put —
        # the same footprint maths as the retired make_offset_item branch.
        return new
    if isinstance(src, CircleItem):
        if src._radius + d < 1.0:          # CircleItem's own 1 mm floor
            return None
        new = _clone(src)
        new.set_radius(src._radius + d)
        return new
    if isinstance(src, ArcItem):
        if src._radius + d <= OFFSET_MIN_EXTENT_MM:
            return None
        new = _clone(src)
        new.set_radius(src._radius + d)
        return new
    if isinstance(src, RegularPolygonItem):
        # Stored radius is the circumradius (inscribed) or the apothem
        # (circumscribed); the apothem moves by exactly d either way.
        n = src._sides
        c = math.cos(math.pi / n)
        apothem = src._radius_mm * c if src._inscribed else src._radius_mm
        if apothem + d <= OFFSET_MIN_EXTENT_MM:
            return None
        step = d / c if src._inscribed else d
        new = _clone(src)
        new.set_radius(src._radius_mm + step)
        return new
    if isinstance(src, EllipseItem):
        if min(src._rx, src._ry) + d <= OFFSET_MIN_EXTENT_MM:
            return None
        new = _clone(src)
        new.set_rx(src._rx + d)
        new.set_ry(src._ry + d)
        return new
    if isinstance(src, SplineItem):
        cps = list(src._control_points)
        if len(cps) < 2:
            return None
        # Fit against the TRUE offset curve (review G7 I-3).
        if src.is_closed() and _offset_closed_loop(cps[:-1], d) is None:
            return None                     # inward past the loop's extent
        fit = fit_offset_spline(src, d)
        if fit is not None:
            new = _clone(src)
            new._control_points, new._knots = fit
            new._weights = None
            new._regenerate()
            return new
        # Unresolvable seam / degenerate fit: Tiller-Hanson — offset the
        # control polygon (loop), mitered.
        if src.is_closed():
            # Closed loop (first == last): offset the control LOOP mitered
            # at every vertex incl. the seam, then re-close (I-2).
            loop = _offset_closed_loop(cps[:-1], d)
            if loop is None:
                return None
            new_cps = loop + [QPointF(loop[0])]
        else:
            new_cps = offset_polyline_pts(cps, d)
        new = _clone(src)
        new._control_points = [QPointF(p) for p in new_cps]
        new._regenerate()
        return new
    return None


# ── Spline offset fit (review G7 I-3) ───────────────────────────────────────

SPLINE_OFFSET_FIT_TOL = 0.01          # max deviation, as a fraction of |d|
SPLINE_OFFSET_MAX_CP_FACTOR = 4       # cap: control points <= 4x the source's
_SPLINE_FIT_SAMPLES = 600             # offset targets along the source


def _bspline_basis(knots, p: int, n: int, ts):
    """Cox-de Boor basis matrix ``B[j, i] = N_{i,p}(ts[j])`` (numpy, m x n).

    The right end of the domain belongs to the last non-empty span, so a
    clamped curve evaluates to its last control point at ``t1``.
    """
    import numpy as np
    k = np.asarray(knots, float)
    ts = np.asarray(ts, float)
    nk = len(k) - 1
    B = np.zeros((len(ts), nk))
    last = max(i for i in range(nk) if k[i] < k[i + 1])
    for i in range(nk):
        if k[i] < k[i + 1]:
            B[:, i] = (ts >= k[i]) & (ts < k[i + 1])
    B[ts >= k[last + 1], last] = 1.0
    for q in range(1, p + 1):
        Bn = np.zeros((len(ts), nk - q))
        for i in range(nk - q):
            den1 = k[i + q] - k[i]
            den2 = k[i + q + 1] - k[i + 1]
            a = (ts - k[i]) / den1 * B[:, i] if den1 > 0 else 0.0
            b = (k[i + q + 1] - ts) / den2 * B[:, i + 1] if den2 > 0 else 0.0
            Bn[:, i] = a + b
        B = Bn
    return B[:, :n]


def _split_widest_span(inner: list) -> list:
    """Insert one knot at the middle of the widest span of [0, 1]."""
    edges = [0.0] + list(inner) + [1.0]
    i = max(range(len(edges) - 1), key=lambda j: edges[j + 1] - edges[j])
    return sorted(list(inner) + [(edges[i] + edges[i + 1]) / 2])


def _split_span_at(inner: list, x: float) -> list:
    """Insert one knot at the middle of the span of [0, 1] containing *x*.

    A residual peak sitting ON a knot belongs to both neighbouring spans;
    the wider of them is split.
    """
    edges = [0.0] + list(inner) + [1.0]
    spans = [j for j in range(len(edges) - 1)
             if edges[j] < edges[j + 1] and edges[j] <= x <= edges[j + 1]]
    i = max(spans, key=lambda j: edges[j + 1] - edges[j])
    return sorted(list(inner) + [(edges[i] + edges[i + 1]) / 2])


def _clamped_uniform_knots(n: int, p: int) -> list:
    """Clamped uniform knot vector on [0, 1] for *n* control points."""
    inner = [i / (n - p) for i in range(1, n - p)]
    return [0.0] * (p + 1) + inner + [1.0] * (p + 1)


def _refine_lsq_fit(tgt, u, p: int, inner: list, start, end,
                    tol: float, n_max: int):
    """Least-squares clamped B-spline through targets *tgt* at params *u*.

    End control points are pinned to *start* / *end*; interior knots start
    at *inner* and one is inserted per round in the span where the pointwise
    residual peaks, until it is <= *tol* or the control count reaches
    *n_max*.

    Returns:
        ``(max_residual, control_points ndarray, knots)`` of the best round.
    """
    import numpy as np
    best = None
    while True:
        kn = [0.0] * (p + 1) + list(inner) + [1.0] * (p + 1)
        n = len(kn) - p - 1
        A = _bspline_basis(kn, p, n, u)
        rhs = tgt - np.outer(A[:, 0], start) - np.outer(A[:, -1], end)
        X, *_ = np.linalg.lstsq(A[:, 1:-1], rhs, rcond=None)
        C = np.vstack([start, X, end])
        # Pointwise residual (same parameter) bounds the true deviation.
        r = np.linalg.norm(A @ C - tgt, axis=1)
        err = float(r.max())
        if best is None or err < best[0]:
            best = (err, C, kn)
        if err <= tol or n >= n_max:
            return best
        inner = _split_span_at(inner, float(u[r.argmax()]))


_SEAM_EXT_SAMPLES = 40        # targets along each miter extension leg


def _seam_targets(Q, T, d):
    """Closed-loop offset samples *Q* (tangents *T*) joined at the seam.

    Outer seam corner: the two end tangent lines are extended to their
    intersection (miter, limited to 4|d|). Inner corner: the samples are
    trimmed where the loop's head and tail portions cross. Smooth seam:
    unchanged.

    Returns:
        ``(targets, seam_point, lo, hi, shift)`` — Q indices lo..hi are kept
        and ``Q[i]`` is ``targets[i + shift]`` — or None when the seam cannot
        be resolved (the caller then keeps the control-loop offset).
    """
    import numpy as np
    a, ua, b, vb = Q[0], T[0], Q[-1], T[-1]
    den = ua[0] * vb[1] - ua[1] * vb[0]
    if abs(den) < 1e-9 or float(np.linalg.norm(a - b)) < 1e-9:
        M = (a + b) / 2                                   # smooth seam
        return np.vstack([M, Q[1:-1], M]), M, 1, len(Q) - 2, 0
    # a + s*ua == b + t*vb
    s_ = ((b[0] - a[0]) * vb[1] - (b[1] - a[1]) * vb[0]) / den
    t_ = ((b[0] - a[0]) * ua[1] - (b[1] - a[1]) * ua[0]) / den
    if s_ <= 0 and t_ >= 0:                               # outer corner: miter
        M = a + s_ * ua
        if np.linalg.norm(M - a) > 4 * abs(d):            # miter limit
            return None
        k = _SEAM_EXT_SAMPLES
        ext1 = np.linspace(M, a, k)[:-1]
        ext2 = np.linspace(b, M, k)[1:]
        return np.vstack([ext1, Q, ext2]), M, 0, len(Q) - 1, k - 1
    # inner corner: trim at the crossing of the head and tail portions
    q = len(Q) // 4
    head, tail = Q[:q], Q[-q:]
    for i in range(len(head) - 1):
        p1, r_ = head[i], head[i + 1] - head[i]
        for j in range(len(tail) - 1):
            p3, s2 = tail[j], tail[j + 1] - tail[j]
            dd = r_[0] * s2[1] - r_[1] * s2[0]
            if abs(dd) < 1e-15:
                continue
            w = p3 - p1
            tt = (w[0] * s2[1] - w[1] * s2[0]) / dd
            uu = (w[0] * r_[1] - w[1] * r_[0]) / dd
            if 0 <= tt <= 1 and 0 <= uu <= 1:
                X = p1 + tt * r_
                lo, hi = i + 1, len(Q) - q + j
                return np.vstack([X, Q[lo:hi + 1], X]), X, lo, hi, 1 - lo
    return None


def fit_offset_spline(src, d: float):
    """Clamped B-spline approximating the TRUE offset of a spline (D9).

    Samples the source exactly (its own knots / weights), offsets every
    sample along its normal by *d*, then least-squares fits a non-rational
    clamped spline of the source's degree to those samples
    (:func:`_refine_lsq_fit`), adding control points where the residual
    peaks until it is within ``SPLINE_OFFSET_FIT_TOL * |d|``, capped at
    ``SPLINE_OFFSET_MAX_CP_FACTOR`` x the source count (the best fit found
    is returned at the cap).

    Open spline: + = the left-normal side; params follow the source's, the
    ends are pinned to the exact offset end points. Closed spline (first ==
    last control point): + = outward; the seam is mitered (outer corner) or
    trimmed (inner corner) by :func:`_seam_targets`, params are chord
    length and both ends are pinned to the one seam point, so the result is
    closed. Either way every source knot is kept with one more multiplicity
    (the offset is one order less continuous there: its speed jumps with the
    curvature).

    Known limit: where |d| exceeds the source's local radius of curvature on
    the concave side the true offset self-intersects (a swallowtail); it is
    not trimmed, so the result follows the untrimmed offset there.

    Args:
        src: A ``SplineItem`` with at least 2 control points.
        d: Signed offset.

    Returns:
        ``(control_points, knots)`` or None (degenerate source, unresolved
        seam) — the caller then keeps the control-polygon offset.
    """
    import numpy as np
    from collections import Counter
    cps = np.array([(p.x(), p.y()) for p in src._control_points], float)
    n0, p = len(cps), int(src._degree)
    if n0 < 2 or abs(d) < 1e-12:
        return None
    k = list(src._knots) if src._knots else _clamped_uniform_knots(n0, p)
    if len(k) != n0 + p + 1:
        return None
    t0, t1 = k[p], k[-p - 1]
    if not t1 > t0:
        return None
    w = np.asarray(src._weights, float) if src._weights else None

    def _src_pts(t):
        B = _bspline_basis(k, p, n0, t)
        if w is None:
            return B @ cps
        Bw = B * w[None, :]
        return (Bw @ cps) / Bw.sum(1)[:, None]

    # Dense params (every other one is a "midpoint"), so the residual check
    # covers the curve between fitted points too.
    ts = np.linspace(t0, t1, 2 * _SPLINE_FIT_SAMPLES - 1)
    h = (t1 - t0) * 1e-8       # tangent step (one-sided at the clamped ends)
    P = _src_pts(ts)
    T = _src_pts(np.clip(ts + h, t0, t1)) - _src_pts(np.clip(ts - h, t0, t1))
    L = np.linalg.norm(T, axis=1)
    if np.any(L < 1e-12):
        return None
    T /= L[:, None]
    closed = src.is_closed()
    if closed:
        area = float(np.sum(P[:-1, 0] * P[1:, 1] - P[1:, 0] * P[:-1, 1]))
        d = d if area <= 0 else -d          # + outward (inset_polygon's rule)
    Q = P + d * np.stack([-T[:, 1], T[:, 0]], 1)       # left normal * d
    mult = Counter((x - t0) / (t1 - t0) for x in k[p + 1:-p - 1] if t0 < x < t1)
    src_inner = sorted(x for x, m_ in mult.items() for _ in range(min(m_ + 1, p)))
    tol = SPLINE_OFFSET_FIT_TOL * abs(d)
    n_max = max(n0, SPLINE_OFFSET_MAX_CP_FACTOR * n0, p + 1)
    if not closed:
        tgt, u, start, end, inner = Q, (ts - t0) / (t1 - t0), Q[0], Q[-1], src_inner
    else:
        seam = _seam_targets(Q, T, d)
        if seam is None:
            return None
        tgt, M, lo, hi, shift = seam
        seg = np.linalg.norm(np.diff(tgt, axis=0), axis=1)
        if seg.sum() < 1e-9:
            return None
        u = np.concatenate([[0.0], np.cumsum(seg)]) / seg.sum()
        # source knots move to the chord parameter of their own samples
        q_t = (ts[lo:hi + 1] - t0) / (t1 - t0)
        q_u = u[lo + shift:hi + shift + 1]
        inner = sorted(float(np.interp(x, q_t, q_u)) for x in src_inner
                       if q_t[0] < x < q_t[-1])
        start = end = M
    while len(inner) + p + 1 < max(n0, p + 1):
        inner = _split_widest_span(inner)
    _, C, kn = _refine_lsq_fit(tgt, u, p, inner, start, end, tol, n_max)
    if closed:
        C[-1] = C[0]                                       # exactly closed
    return [QPointF(float(x), float(y)) for x, y in C], list(kn)


def _inset_ok(src_pts, new_pts) -> bool:
    """False when a polygon offset collapsed or turned inside out.

    A too-large miter offset reverses (or zeroes) edges — a square inset past
    its half-width comes back point-reflected, which keeps the winding, so the
    test is per edge: every offset edge must run the same way as its source
    edge.
    """
    n = len(src_pts)
    if len(new_pts) != n:
        return False
    for i in range(n):
        j = (i + 1) % n
        sx = src_pts[j].x() - src_pts[i].x()
        sy = src_pts[j].y() - src_pts[i].y()
        nx = new_pts[j].x() - new_pts[i].x()
        ny = new_pts[j].y() - new_pts[i].y()
        if sx * sx + sy * sy < 1e-18:
            continue                      # degenerate source edge: no verdict
        if sx * nx + sy * ny <= 1e-9:
            return False
    return True


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
    from .geometry_2d import (
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
    from .geometry_2d import LineItem, PolylineItem

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
