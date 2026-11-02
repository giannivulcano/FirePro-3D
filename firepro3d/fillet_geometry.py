"""Fillet geometry (scene-tools.md D14 Fillet; design 2026-11-01 DS4.3).

Pure: tuples and dataclasses only, no Qt, no scene items. Coordinates are
scene units (Y down); arc angles are Y-up CCW degrees, the ``ArcItem``
convention (``arc_math.yup_angle``): angle of P seen from C is
``atan2(-(Py - Cy), Px - Cx)``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any, NamedTuple

Pt = tuple

LEN_TOL = 1e-6          # mm: a tangent point within this of a far end is "at" it
PARALLEL_SIN = 1e-9     # |sin(theta)| at or below this: parallel / collinear edges
SAME_SIDE_DOT = 1.0 - 1e-9   # unit-direction dot above this: two ends on one side of a point
ZERO_LEN_SQ = 1e-18     # squared length at or below this: a degenerate (point) segment
BISECTOR_MIN = 1e-12    # |u1 + u2| below this: opposite directions, no bisector
TRIMMED_END_TOL = 1e-3  # mm: a trimmed line end this far off its tangent point means a constraint resisted
LINE_PAIR_REACH = 2.0   # a hover corner lies within tol of the cursor AND of both segments

REFUSE_PARALLEL = "Edges are parallel \u2014 no corner to fillet"
REFUSE_TOO_LARGE = "Radius too large for these edges"
REFUSE_RADIUS = "Fillet radius must be greater than zero"


@dataclass(frozen=True)
class Shape:
    """A fillet candidate: ``kind`` ``"line"`` (2 points) or ``"poly"``
    (closed ring / open chain of vertices); ``ref`` is the caller's item."""
    kind: str
    pts: tuple
    closed: bool
    ref: Any


@dataclass(frozen=True)
class Corner:
    """A corner: *vertex*, the two unit directions away from it, the length
    available along each (the far end of the segment), and the source refs.

    ``kind`` ``"vertex"``: both refs are the one polyline-like item and
    ``idx1 == idx2`` is the vertex index (edge 1 runs to the previous vertex,
    edge 2 to the next). ``kind`` ``"lines"``: ``idx1`` / ``idx2`` is the index
    (0 / 1) of the line end kept (the far end); the other end is the one the
    fillet sets to the tangent point.
    """
    kind: str
    vertex: tuple
    u1: tuple
    u2: tuple
    len1: float
    len2: float
    ref1: Any
    ref2: Any
    idx1: int
    idx2: int


@dataclass(frozen=True)
class TangentArc:
    """The fillet arc: centre, radius, Y-up CCW ``start_deg`` / ``span_deg`` (> 0),
    the tangent points on edge 1 / edge 2, and whether the arc starts at ``t1``."""
    center: tuple
    radius: float
    start_deg: float
    span_deg: float
    t1: tuple
    t2: tuple
    start_is_t1: bool


class Refused(NamedTuple):
    """A refusal: ``reason`` in ``parallel`` / ``too_large`` / ``radius``."""
    reason: str
    message: str


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _norm(a):
    return math.hypot(a[0], a[1])


def tangent_arc(corner: Corner, radius: float):
    """The fillet arc of *radius* in *corner*, or a :class:`Refused`.

    With theta the angle between the edge directions: tangent length
    ``t = r / tan(theta/2)``, centre distance ``d = r / sin(theta/2)`` along the
    bisector ``u1 + u2``.

    Args:
        corner: The corner.
        radius: Fillet radius (> 0).

    Returns:
        :class:`TangentArc`, or :class:`Refused` for a non-positive radius,
        parallel / collinear edges, or a tangent point past either far end.
    """
    if not (radius > 0.0 and math.isfinite(radius)):
        return Refused("radius", REFUSE_RADIUS)
    (u1x, u1y), (u2x, u2y) = corner.u1, corner.u2
    sin_t = u1x * u2y - u1y * u2x
    cos_t = u1x * u2x + u1y * u2y
    if abs(sin_t) <= PARALLEL_SIN:
        return Refused("parallel", REFUSE_PARALLEL)
    half = math.atan2(abs(sin_t), cos_t) / 2.0
    t = radius / math.tan(half)
    if t > corner.len1 + LEN_TOL or t > corner.len2 + LEN_TOL:
        return Refused("too_large", REFUSE_TOO_LARGE)
    d = radius / math.sin(half)
    bx, by = u1x + u2x, u1y + u2y
    bn = math.hypot(bx, by)
    vx, vy = corner.vertex
    cx, cy = vx + d * bx / bn, vy + d * by / bn
    t1 = (vx + t * u1x, vy + t * u1y)
    t2 = (vx + t * u2x, vy + t * u2y)
    sa = math.degrees(math.atan2(-(t1[1] - cy), t1[0] - cx))
    ea = math.degrees(math.atan2(-(t2[1] - cy), t2[0] - cx))
    signed = (ea - sa + 540.0) % 360.0 - 180.0       # CCW sweep t1 -> t2 in (-180, 180)
    if signed >= 0.0:
        return TangentArc((cx, cy), radius, sa % 360.0, signed, t1, t2, True)
    return TangentArc((cx, cy), radius, ea % 360.0, -signed, t1, t2, False)


@dataclass(frozen=True)
class PolyPiece:
    """One open polyline of a fillet result: its points, and which tangent
    point ends it (``"prev"`` = on the previous-vertex edge = ``t1``;
    ``"next"`` = ``t2``; None = an original end)."""
    pts: tuple
    start_tp: Any
    end_tp: Any


def seg_distance(p, a, b) -> float:
    """Distance from point *p* to segment *a*-*b*."""
    ab = _sub(b, a)
    ab2 = _dot(ab, ab)
    if ab2 < ZERO_LEN_SQ:
        return _norm(_sub(p, a))
    t = max(0.0, min(1.0, _dot(_sub(p, a), ab) / ab2))
    return _norm(_sub(p, (a[0] + t * ab[0], a[1] + t * ab[1])))


def _vertex_corner(shape: Shape, i: int):
    pts = shape.pts
    n = len(pts)
    v, prev, nxt = pts[i], pts[(i - 1) % n], pts[(i + 1) % n]
    d1, d2 = _sub(prev, v), _sub(nxt, v)
    l1, l2 = _norm(d1), _norm(d2)
    if l1 < LEN_TOL or l2 < LEN_TOL:
        return None
    return Corner("vertex", v, (d1[0] / l1, d1[1] / l1), (d2[0] / l2, d2[1] / l2),
                  l1, l2, shape.ref, shape.ref, i, i)


def _line_x(a: Shape, b: Shape):
    p, p2 = a.pts
    q, q2 = b.pts
    d1, d2 = _sub(p2, p), _sub(q2, q)
    den = _cross(d1, d2)
    if abs(den) <= PARALLEL_SIN * _norm(d1) * _norm(d2):
        return None
    t = _cross(_sub(q, p), d2) / den
    return (p[0] + t * d1[0], p[1] + t * d1[1])


def _halves(x, e0, e1):
    """Candidate half-lines from *x*: ``(end index, unit dir, length)`` per end
    not at *x*; two ends on the same side collapse to the farther one."""
    out = []
    for k, e in enumerate((e0, e1)):
        d = _sub(e, x)
        n = _norm(d)
        if n > LEN_TOL:
            out.append((k, (d[0] / n, d[1] / n), n))
    if len(out) == 2 and _dot(out[0][1], out[1][1]) > SAME_SIDE_DOT:
        out = [max(out, key=lambda h: h[2])]
    return out


def _pair_corner(a: Shape, b: Shape, p, tol):
    """Corner of two lines at their intersection nearest the cursor's quadrant.

    *tol* None accepts an intersection anywhere on the infinite lines (the
    fallback click-Line-1-then-Line-2 path); a number requires it on both
    segments within *tol* (the hover path: ends meet or cross).
    """
    x = _line_x(a, b)
    if x is None:
        return None
    if tol is not None and (seg_distance(x, *a.pts) > tol
                            or seg_distance(x, *b.pts) > tol):
        return None
    r = _sub(p, x)
    rn = _norm(r)
    best = None
    for ka, ua, la in _halves(x, *a.pts):
        for kb, ub, lb in _halves(x, *b.pts):
            bis = (ua[0] + ub[0], ua[1] + ub[1])
            bn = _norm(bis)
            if bn < BISECTOR_MIN:
                continue
            score = _dot(bis, r) / (bn * rn) if rn > LEN_TOL else la + lb
            if best is None or score > best[0]:
                best = (score, Corner("lines", x, ua, ub, la, lb,
                                      a.ref, b.ref, ka, kb))
    return None if best is None else best[1]


def find_corner(shapes, p, tol):
    """The corner nearest the cursor *p* within *tol* (the snap aperture), or None.

    Candidates: a polyline vertex (interior vertices of an open one, any vertex
    of a closed one -- a Rect / RegularPolygon is a closed ``"poly"``), and the
    meeting / crossing of two ``"line"`` shapes.

    Args:
        shapes: Iterable of :class:`Shape`.
        p: Cursor, scene units.
        tol: Aperture radius, scene units.
    """
    best = None

    def offer(c):
        nonlocal best
        d = _norm(_sub(c.vertex, p))
        if d <= tol and (best is None or d < best[0]):
            best = (d, c)

    lines = []
    for sh in shapes:
        if sh.kind == "line":
            lines.append(sh)
            continue
        n = len(sh.pts)
        if n < 3:
            continue
        for i in (range(n) if sh.closed else range(1, n - 1)):
            if _norm(_sub(sh.pts[i], p)) <= tol:
                c = _vertex_corner(sh, i)
                if c is not None:
                    offer(c)
    # A hover corner is within tol of p and of both segments, so a segment
    # farther than LINE_PAIR_REACH * tol from p can't contribute: skip it
    # before the O(n^2) pairing (runs on every mouse move).
    near = [sh for sh in lines if seg_distance(p, *sh.pts) <= LINE_PAIR_REACH * tol]
    for a, b in combinations(near, 2):
        c = _pair_corner(a, b, p, tol)
        if c is not None:
            offer(c)
    return None if best is None else best[1]


def corner_between_lines(a: Shape, b: Shape, p):
    """The fallback corner of two picked lines at their (extended) intersection,
    the quadrant chosen by the cursor *p*; :class:`Refused` (``parallel``) when
    the lines are parallel / collinear."""
    c = _pair_corner(a, b, p, None)
    return c if c is not None else Refused("parallel", REFUSE_PARALLEL)


def _dedupe(seq):
    out = []
    for q in seq:
        if not out or _norm(_sub(q, out[-1])) > LEN_TOL:
            out.append(q)
    return out


def poly_pieces(pts, closed: bool, i: int, t_prev, t_next) -> list:
    """The open polyline(s) a fillet at vertex *i* leaves behind.

    An open polyline splits in two (a piece with fewer than two points -- a
    tangent point exactly on the far vertex -- is not created); a closed ring
    (Rect / polygon too) becomes one open polyline from ``t_next`` around to
    ``t_prev``.

    Args:
        pts: The vertices (scene units).
        closed: Whether the ring is closed.
        i: The filleted vertex.
        t_prev: Tangent point on the edge toward vertex ``i - 1``.
        t_next: Tangent point on the edge toward vertex ``i + 1``.
    """
    n = len(pts)
    if closed:
        seq = [t_next] + [pts[(i + k) % n] for k in range(1, n)] + [t_prev]
        d = _dedupe(seq)
        return [PolyPiece(tuple(d), "next", "prev")] if len(d) >= 2 else []
    a = _dedupe([pts[k] for k in range(0, i)] + [t_prev])
    b = _dedupe([t_next] + [pts[k] for k in range(i + 1, n)])
    out = []
    if len(a) >= 2:
        out.append(PolyPiece(tuple(a), None, "prev"))
    if len(b) >= 2:
        out.append(PolyPiece(tuple(b), "next", None))
    return out
