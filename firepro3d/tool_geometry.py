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


def offset_item(src, signed_d: float, cache: "dict | None" = None):
    """Offset copy of *src* (scene-tools.md D9); the source is untouched.

    Args:
        src: A 2D geometry item.
        signed_d: Offset distance; + = outward (closed shapes, arcs) or the
            left-normal side (lines, open polylines, splines).
        cache: Optional caller-owned dict (the scene's offset state) that
            keeps a spline fit's d-independent work between calls, so the
            live ghost stays cheap (review G7 R-2); ignored by other types.

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
        fit = fit_offset_spline(src, d, cache)
        if fit is not None:
            return _spline_from_fit(src, *fit)
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


# ── Spline offset fit (review G7 I-3 / R-1 / R-2) ───────────────────────────

SPLINE_OFFSET_FIT_TOL = 0.01          # max deviation, as a fraction of |d|
SPLINE_OFFSET_MAX_CP_FACTOR = 4       # cap: control points <= 4x the source's
_SPLINE_FIT_SAMPLES = 1200            # offset targets (split across the runs)
_JOIN_LEG_SAMPLES = 20                # targets along each miter leg
_MITER_LIMIT = 4.0                    # a miter leg longer than 4|d| -> no fit
_JOIN_SEARCH_MAX = 400                # samples searched for an inner crossing
_GHOST_SAMPLES_PER_SPAN = 12          # dense evaluation of the result path


def _bspline_basis(knots, p: int, n: int, ts):
    """Cox-de Boor basis matrix ``B[j, i] = N_{i,p}(ts[j])`` (numpy, m x n).

    Fully vectorised over samples and basis functions. The right end of the
    domain belongs to the last non-empty span, so a clamped curve evaluates
    to its last control point at ``t1``; an interior knot value belongs to
    the span on its right.
    """
    import numpy as np
    k = np.asarray(knots, float)
    u = np.asarray(ts, float)[:, None]
    nk = len(k) - 1
    B = ((u >= k[None, :-1]) & (u < k[None, 1:])).astype(float)
    last = max(i for i in range(nk) if k[i] < k[i + 1])
    B[u[:, 0] >= k[last + 1], last] = 1.0
    for q in range(1, p + 1):
        kl, kr = k[:nk - q], k[q:nk]                  # k[i], k[i+q]
        k1, k2 = k[1:nk - q + 1], k[q + 1:nk + 1]     # k[i+1], k[i+q+1]
        den1, den2 = kr - kl, k2 - k1
        a = np.where(den1 > 0, (u - kl) / np.where(den1 > 0, den1, 1.0), 0.0)
        b = np.where(den2 > 0, (k2 - u) / np.where(den2 > 0, den2, 1.0), 0.0)
        B = a * B[:, :nk - q] + b * B[:, 1:nk - q + 1]
    return B[:, :n]


def _split_widest_span(inner: list) -> list:
    """Insert one knot at the middle of the widest span of [0, 1]."""
    edges = [0.0] + list(inner) + [1.0]
    i = max(range(len(edges) - 1), key=lambda j: edges[j + 1] - edges[j])
    return sorted(list(inner) + [(edges[i] + edges[i + 1]) / 2])


def _split_spans_at(inner: list, xs, budget: int) -> list:
    """Split (at its middle) every span of [0, 1] that holds one of *xs*.

    A value sitting ON a knot belongs to both neighbouring spans; the wider
    is split. At most *budget* knots are inserted (worst spans first — *xs*
    is expected sorted by residual, largest first).
    """
    edges = [0.0] + list(inner) + [1.0]
    chosen = []
    for x in xs:
        spans = [j for j in range(len(edges) - 1)
                 if edges[j] < edges[j + 1] and edges[j] <= x <= edges[j + 1]]
        if not spans:
            continue
        j = max(spans, key=lambda i: edges[i + 1] - edges[i])
        if j not in chosen:
            chosen.append(j)
            if len(chosen) >= budget:
                break
    return sorted(list(inner) + [(edges[j] + edges[j + 1]) / 2 for j in chosen])


def _clamped_uniform_knots(n: int, p: int) -> list:
    """Clamped uniform knot vector on [0, 1] for *n* control points."""
    inner = [i / (n - p) for i in range(1, n - p)]
    return [0.0] * (p + 1) + inner + [1.0] * (p + 1)


def _spline_signature(src) -> tuple:
    """Identity of a spline's geometry (the fit cache is keyed on it)."""
    return (tuple((p.x(), p.y()) for p in src._control_points), src._degree,
            tuple(src._knots or ()), tuple(src._weights or ()))


def _spline_runs(src):
    """d-independent sampling of *src*, split at its C0 corners.

    A corner is an interior knot of multiplicity >= degree (the curve may
    turn sharply there). Each run is sampled exactly (own knots / weights)
    with one-sided tangents at its ends.

    Returns:
        A dict (see keys below) or None for a degenerate source (repeated
        control points giving a zero tangent, bad knot vector, ...).
    """
    import numpy as np
    from collections import Counter
    cps = np.array([(p.x(), p.y()) for p in src._control_points], float)
    n0, p = len(cps), int(src._degree)
    if n0 < 2:
        return None
    k = list(src._knots) if src._knots else _clamped_uniform_knots(n0, p)
    if len(k) != n0 + p + 1:
        return None
    t0, t1 = float(k[p]), float(k[-p - 1])
    if not t1 > t0:
        return None
    w = np.asarray(src._weights, float) if src._weights else None

    def pts(t):
        B = _bspline_basis(k, p, n0, t)
        if w is None:
            return B @ cps
        Bw = B * w[None, :]
        return (Bw @ cps) / Bw.sum(1)[:, None]

    mult = Counter(float(x) for x in k[p + 1:-p - 1] if t0 < x < t1)
    corners = sorted(x for x, m in mult.items() if m >= p)
    edges = [t0] + corners + [t1]
    runs = []
    for a, b in zip(edges, edges[1:]):
        m = max(24, int(round(_SPLINE_FIT_SAMPLES * (b - a) / (t1 - t0))))
        ts = np.linspace(a, b, m)
        h = (b - a) * 1e-8
        P = pts(ts)
        T = pts(np.clip(ts + h, a, b)) - pts(np.clip(ts - h, a, b))
        L = np.linalg.norm(T, axis=1)
        if np.any(L < 1e-12) or not np.all(np.isfinite(P)):
            return None
        T /= L[:, None]
        runs.append({"t": (ts - t0) / (t1 - t0), "P": P, "T": T,
                     "N": np.stack([-T[:, 1], T[:, 0]], 1)})
    allP = np.vstack([r["P"] for r in runs])
    area = float(np.sum(allP[:-1, 0] * allP[1:, 1] - allP[1:, 0] * allP[:-1, 1]))
    # non-corner source knots, one order less continuous in the offset
    smooth = sorted((x - t0) / (t1 - t0) for x, m in mult.items()
                    for _ in range(min(m + 1, p)) if m < p)
    return {"p": p, "n0": n0, "runs": runs, "closed": src.is_closed(),
            "wind": 1.0 if area <= 0 else -1.0, "inner": smooth,
            "corners": [(x - t0) / (t1 - t0) for x in corners]}


def _join_runs(Qa, Ta, Qb, Tb, d):
    """Join the end of offset run *a* to the start of run *b* at a C0 corner.

    Smooth join (same tangent): the two ends meet (midpoint). Outer corner:
    the end tangents are extended to their intersection (miter, leg <=
    ``_MITER_LIMIT`` * |d|). Inner corner: both runs are trimmed where they
    cross (searched near the corner, vectorised).

    Returns:
        ``(ia, leg_a, M, leg_b, ib)`` — keep ``Qa[:ia + 1]``, then the
        ``leg_a`` samples, the corner point ``M``, the ``leg_b`` samples,
        then ``Qb[ib:]`` — or None when the join cannot be resolved.
    """
    import numpy as np
    a, ua, b, ub = Qa[-1], Ta[-1], Qb[0], Tb[0]
    empty = np.zeros((0, 2))
    den = ua[0] * ub[1] - ua[1] * ub[0]
    if abs(den) < 1e-9:
        if float(ua @ ub) > 0 and float(np.linalg.norm(a - b)) < 1e-6 + 1e-6 * abs(d):
            return len(Qa) - 2, empty, (a + b) / 2, empty, 1
        return None                                        # a 180° reversal
    # a + s*ua == b + t*ub
    s_ = ((b[0] - a[0]) * ub[1] - (b[1] - a[1]) * ub[0]) / den
    t_ = ((b[0] - a[0]) * ua[1] - (b[1] - a[1]) * ua[0]) / den
    if s_ >= 0 and t_ <= 0:                                 # outer: miter
        M = a + s_ * ua
        if max(s_, -t_) > _MITER_LIMIT * abs(d):
            return None
        L = _JOIN_LEG_SAMPLES
        leg_a = np.linspace(a, M, L + 2)[1:-1]
        leg_b = np.linspace(M, b, L + 2)[1:-1]
        return len(Qa) - 1, leg_a, M, leg_b, 0
    # inner: the runs cross near the corner — find the crossing closest to it
    na = min(len(Qa) - 1, _JOIN_SEARCH_MAX)
    nb = min(len(Qb) - 1, _JOIN_SEARCH_MAX)
    A0, A1 = Qa[-na - 1:-1], Qa[-na:]
    B0, B1 = Qb[:nb], Qb[1:nb + 1]
    r, s2 = A1 - A0, B1 - B0
    dd = r[:, None, 0] * s2[None, :, 1] - r[:, None, 1] * s2[None, :, 0]
    wv = B0[None, :, :] - A0[:, None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        tt = (wv[..., 0] * s2[None, :, 1] - wv[..., 1] * s2[None, :, 0]) / dd
        uu = (wv[..., 0] * r[:, None, 1] - wv[..., 1] * r[:, None, 0]) / dd
    ok = (np.abs(dd) > 1e-15) & (tt >= 0) & (tt <= 1) & (uu >= 0) & (uu <= 1)
    if not ok.any():
        return None
    ii, jj = np.nonzero(ok)
    best = int(np.argmin((na - 1 - ii) + jj))              # nearest the corner
    i, j = int(ii[best]), int(jj[best])
    M = A0[i] + tt[i, j] * r[i]
    ia = len(Qa) - na - 1 + i                              # last kept of a
    ib = j + 1                                             # first kept of b
    return ia, np.zeros((0, 2)), M, np.zeros((0, 2)), ib


def _refine_lsq_fit(tgt, nrm, u, p: int, inner: list, pins, tol: float,
                    n_max: int):
    """Least-squares clamped B-spline through targets *tgt* at params *u*.

    *pins* is a list of ``(u, point)``: the control point whose basis
    function is 1 at that parameter (the clamped ends, a C0 corner knot) is
    fixed there. The residual is measured along each target's normal *nrm*
    (the geometric deviation; a tangential slide along the offset is not an
    error). While it exceeds *tol*, every span holding an out-of-tolerance
    sample is split, up to *n_max* control points.

    Returns:
        ``(ok, err, C, knots, inner)`` of the last round (ok = within tol).
    """
    import numpy as np
    while True:
        kn = [0.0] * (p + 1) + list(inner) + [1.0] * (p + 1)
        n = len(kn) - p - 1
        A = _bspline_basis(kn, p, n, u)
        fixed = {}
        if pins:
            rows = _bspline_basis(kn, p, n, [pu for pu, _ in pins])
            for row, (_, pt) in zip(rows, pins):
                fixed[int(np.argmax(row))] = pt
        free = [i for i in range(n) if i not in fixed]
        rhs = tgt.copy()
        for i, pt in fixed.items():
            rhs -= np.outer(A[:, i], pt)
        X, *_ = np.linalg.lstsq(A[:, free], rhs, rcond=None)
        C = np.zeros((n, 2))
        C[free] = X
        for i, pt in fixed.items():
            C[i] = pt
        r = np.abs(((A @ C) - tgt) * nrm).sum(1)
        err = float(r.max())
        if err <= tol:
            return True, err, C, kn, inner
        if n >= n_max:
            return False, err, C, kn, inner
        bad = np.argsort(-r)[: int(np.count_nonzero(r > tol))]
        inner = _split_spans_at(inner, u[bad], n_max - n)


def _dense_path_pts(kn, p, C, ghost_basis=None):
    """Dense evaluation of the fitted curve (knot values included, so a C0
    corner is drawn exactly)."""
    import numpy as np
    if ghost_basis is None:
        n = len(C)
        m = max(200, _GHOST_SAMPLES_PER_SPAN * (n - p))
        uu = np.union1d(np.linspace(0.0, 1.0, m), np.asarray(kn, float))
        ghost_basis = _bspline_basis(kn, p, n, uu)
    return ghost_basis @ C


def _fit_open_linear(plan, n_max, d, inner=None):
    """Smooth OPEN spline: targets ``P + d*N`` are linear in d, so for one
    knot vector the fit is exactly ``C = C0 + d*C1`` (the pinned ends are
    linear in d too).

    The knots are refined against the targets at *d* (starting from *inner*
    or the source's own knots); the entry then serves every d whose
    residual ``|R0 + d*R1|`` (along the normals) stays in tolerance.

    Returns:
        A cache entry dict (``ok`` False when the cap was hit).
    """
    import numpy as np
    run = plan["runs"][0]
    P, N, u, p = run["P"], run["N"], run["t"], plan["p"]
    if inner is None:
        inner = list(plan["inner"])
        while len(inner) + p + 1 < max(plan["n0"], p + 1):
            inner = _split_widest_span(inner)
    Q = P + d * N
    ok, _, _, kn, inner = _refine_lsq_fit(
        Q, N, u, p, inner, [(0.0, Q[0]), (1.0, Q[-1])],
        SPLINE_OFFSET_FIT_TOL * abs(d), n_max)
    n = len(kn) - p - 1
    A = _bspline_basis(kn, p, n, u)
    Af = A[:, 1:-1]
    X, *_ = np.linalg.lstsq(
        Af, np.hstack([P - np.outer(A[:, 0], P[0]) - np.outer(A[:, -1], P[-1]),
                       N - np.outer(A[:, 0], N[0]) - np.outer(A[:, -1], N[-1])]),
        rcond=None)
    C0 = np.vstack([P[0], X[:, :2], P[-1]])
    C1 = np.vstack([N[0], X[:, 2:], N[-1]])
    m = max(200, _GHOST_SAMPLES_PER_SPAN * (n - p))
    uu = np.union1d(np.linspace(0.0, 1.0, m), np.asarray(kn, float))
    return {"ok": ok, "inner": inner, "kn": kn, "C0": C0, "C1": C1,
            "R0": (A @ C0 - P) * N, "R1": (A @ C1 - N) * N,
            "ghost": _bspline_basis(kn, p, n, uu),
            "fail_small": 0.0, "fail_rel": False}


def _linear_err(lin, d) -> float:
    """Normal deviation of the cached linear fit at offset *d*."""
    import numpy as np
    return float(np.abs((lin["R0"] + d * lin["R1"]).sum(1)).max())


def _r0_dominated(lin, tol) -> bool:
    """The d-free part (source not exactly representable, e.g. rational)
    uses at least half the tolerance — failures then hit SMALL |d|."""
    import numpy as np
    return float(np.abs(lin["R0"].sum(1)).max()) > 0.5 * tol


def _linear_hopeless(lin, d, tol) -> bool:
    """A refinement to the cap already failed for this kind of d."""
    if _r0_dominated(lin, tol):
        return abs(d) <= lin["fail_small"]
    return lin["fail_rel"]


def _offset_targets(plan, d):
    """Assemble the (non-linear in d) offset targets of a closed / cornered
    spline: runs offset by d, joined at every corner (and the seam)."""
    import numpy as np
    runs = plan["runs"]
    sd = d * plan["wind"] if plan["closed"] else d        # closed: + outward
    Q = [r["P"] + sd * r["N"] for r in runs]
    nr = len(runs)
    joins = []
    for i in range(nr - 1):
        joins.append(_join_runs(Q[i], runs[i]["T"], Q[i + 1], runs[i + 1]["T"], d))
    seam = (_join_runs(Q[-1], runs[-1]["T"], Q[0], runs[0]["T"], d)
            if plan["closed"] else None)
    if any(j is None for j in joins) or (plan["closed"] and seam is None):
        return None
    starts = [0] * nr
    ends = [len(q) - 1 for q in Q]
    for i, jn in enumerate(joins):
        ends[i], starts[i + 1] = jn[0], jn[4]
    if seam is not None:
        ends[-1], starts[0] = seam[0], seam[4]
    pts, nrm, ts, pins_at = [], [], [], []

    def add(block, normals, tvals):
        pts.append(block); nrm.append(normals); ts.append(tvals)

    def leg(block):
        if len(block) == 0:
            return
        dv = block[-1] - block[0] if len(block) > 1 else np.array([1.0, 0.0])
        nv = np.array([-dv[1], dv[0]]) / max(float(np.linalg.norm(dv)), 1e-12)
        add(block, np.repeat(nv[None], len(block), 0), np.full(len(block), np.nan))

    def corner(Mp):
        pins_at.append(sum(len(b) for b in pts))
        add(Mp[None], np.zeros((1, 2)), np.array([np.nan]))

    if seam is not None:
        corner(seam[2]); leg(seam[3])
    for i in range(nr):
        if ends[i] - starts[i] < 1:
            return None
        sl = slice(starts[i], ends[i] + 1)
        add(Q[i][sl], runs[i]["N"][sl], runs[i]["t"][sl])
        if i < nr - 1:
            leg(joins[i][1]); corner(joins[i][2]); leg(joins[i][3])
    if seam is not None:
        leg(seam[1]); corner(seam[2])
    tgt, nrm, tv = np.vstack(pts), np.vstack(nrm), np.concatenate(ts)
    seg = np.linalg.norm(np.diff(tgt, axis=0), axis=1)
    if seg.sum() < 1e-9:
        return None
    u = np.concatenate([[0.0], np.cumsum(seg)]) / seg.sum()
    return tgt, nrm, u, tv, pins_at


def fit_offset_spline(src, d: float, cache: "dict | None" = None):
    """Clamped B-spline approximating the TRUE offset of a spline (D9).

    Samples the source exactly (own knots / weights), offsets every sample
    along its normal by *d* and least-squares fits a non-rational clamped
    spline of the source's degree (:func:`_refine_lsq_fit`), splitting the
    spans where the normal deviation exceeds ``SPLINE_OFFSET_FIT_TOL * |d|``
    until it fits, capped at ``SPLINE_OFFSET_MAX_CP_FACTOR`` x the source's
    control points. **Never returns a fit above tolerance** — None instead,
    so :func:`offset_item` falls back (review G7 R-1).

    * Smooth open spline: targets are linear in d, so the fit is
      ``C0 + d*C1`` for one knot vector, refined once per source and cached
      (per mouse move only that sum is evaluated — R-2).
    * C0 corners (interior knot multiplicity >= degree) and closed splines
      (+ = outward): the runs between corners are offset and joined by a
      miter (outer side) or trimmed at their crossing (inner side) —
      :func:`_join_runs`, the seam of a closed spline included; the corner
      point is pinned under a knot of multiplicity = degree, params are
      chord length. The d-independent sampling and the last knot vector are
      cached; each call re-solves once and re-refines only if out of
      tolerance.

    Known limit: where |d| exceeds the source's local radius of curvature on
    the concave side the true offset self-intersects (a swallowtail); that
    is not trimmed, so such offsets usually fail the tolerance and fall back.

    Args:
        src: A ``SplineItem``.
        d: Signed offset (open: + = left normal; closed: + = outward).
        cache: Optional dict owned by the caller (the scene's offset state)
            that keeps the d-independent work between calls.

    Returns:
        ``(control_points, knots, dense_points)`` or None.
    """
    import numpy as np
    if not math.isfinite(d) or abs(d) < 1e-12:
        return None
    if cache is None:
        cache = {}
    sig = _spline_signature(src)
    if cache.get("sig") != sig:
        cache.clear()
        cache["sig"] = sig
        cache["plan"] = _spline_runs(src)
    plan = cache["plan"]
    if plan is None:
        return None
    p = plan["p"]
    n_max = max(SPLINE_OFFSET_MAX_CP_FACTOR * plan["n0"], p + 1)
    linear = not plan["closed"] and len(plan["runs"]) == 1
    if linear:
        tol = SPLINE_OFFSET_FIT_TOL * abs(d)
        lin = cache.get("linear")
        if lin is None or _linear_err(lin, d) > tol:
            if lin is not None and _linear_hopeless(lin, d, tol):
                return None                 # already refined to the cap
            fresh = _fit_open_linear(plan, n_max, d,
                                     None if lin is None else lin["inner"])
            if lin is not None:
                fresh["fail_small"] = lin["fail_small"]
                fresh["fail_rel"] = lin["fail_rel"]
            if _linear_err(fresh, d) > tol:
                if _r0_dominated(fresh, tol):
                    fresh["fail_small"] = max(fresh["fail_small"], abs(d))
                else:
                    fresh["fail_rel"] = True
            cache["linear"] = lin = fresh
        if _linear_err(lin, d) > tol:
            return None                     # never an out-of-tolerance fit
        C = lin["C0"] + d * lin["C1"]
        kn = lin["kn"]
        dense = lin["ghost"] @ C
    else:
        built = _offset_targets(plan, d)
        if built is None:
            return None
        tgt, nrm, u, tv, pins_at = built
        pins = [(0.0, tgt[0]), (1.0, tgt[-1])] + [
            (float(u[i]), tgt[i]) for i in pins_at if 0 < i < len(tgt) - 1]
        corner_u = sorted(float(u[i]) for i in pins_at if 0 < i < len(tgt) - 1)
        key = ("inner", d > 0)
        inner = cache.get(key)
        if inner is None or len(inner) < len(corner_u) * p:
            ok_t = ~np.isnan(tv)
            src_inner = [float(np.interp(x, tv[ok_t], u[ok_t])) for x in plan["inner"]
                         if tv[ok_t][0] < x < tv[ok_t][-1]]
            inner = sorted(src_inner + [c for c in corner_u for _ in range(p)])
            while len(inner) + p + 1 < max(plan["n0"], p + 1):
                inner = _split_widest_span(inner)
        else:
            # keep the refined interior knots, move the corner knots to
            # where the corners are for this d
            old_c = cache.get(("corners", d > 0), [])
            inner = sorted([x for x in inner if not any(abs(x - c) < 1e-12 for c in old_c)]
                           + [c for c in corner_u for _ in range(p)])
        tol = SPLINE_OFFSET_FIT_TOL * abs(d)
        ok, err, C, kn, inner = _refine_lsq_fit(
            tgt, nrm, u, p, inner, pins, tol, max(n_max, len(inner) + p + 1))
        cache[key] = inner
        cache[("corners", d > 0)] = corner_u
        if not ok:
            return None
        if plan["closed"]:
            C[-1] = C[0]                                   # exactly closed
        dense = _dense_path_pts(kn, p, C)
    return ([QPointF(float(x), float(y)) for x, y in C], list(kn), dense)


def _spline_from_fit(src, cps, knots, dense):
    """A new SplineItem with the fitted data and *src*'s style.

    Built without ezdxf flattening (the Offset ghost updates per mouse
    move — review G7 R-2): the path is the fit's own dense evaluation. The
    committed copy is re-created through to_dict/from_dict, which
    regenerates the exact path.
    """
    from PyQt6.QtGui import QPolygonF
    from .geometry_2d import SplineItem
    data = src.to_dict()
    new = SplineItem([], src._degree, None, None,
                     data.get("color", "#ffffff"), data.get("lineweight", 1.0))
    new._geom2d_from_dict(data)
    new._control_points = list(cps)
    new._degree = src._degree
    new._knots = list(knots)
    new._weights = None
    path = QPainterPath()
    path.addPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in dense]))
    if src.is_closed():
        path.closeSubpath()
    new.setPath(path)
    return new


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
