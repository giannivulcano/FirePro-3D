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
