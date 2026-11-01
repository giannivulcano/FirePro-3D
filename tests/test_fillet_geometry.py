"""Pure fillet maths (design 2026-11-01 DS4.3): scene coordinates (Y down),
arc angles Y-up CCW (the ArcItem convention, arc_math.yup_angle)."""
from __future__ import annotations

import math

import pytest

from firepro3d import fillet_geometry as fh
from firepro3d.constants import FILLET_DEFAULT_RADIUS_MM

PARALLEL = "Edges are parallel \u2014 no corner to fillet"
TOO_LARGE = "Radius too large for these edges"


def _u(deg):
    """Scene unit vector at the VISUAL (Y-up) angle *deg*."""
    a = math.radians(deg)
    return (math.cos(a), -math.sin(a))


def _corner(u1, u2, len1=100.0, len2=100.0, vertex=(0.0, 0.0)):
    return fh.Corner("lines", vertex, u1, u2, len1, len2, "A", "B", 0, 0)


def _on_arc(arc, deg):
    """Independent Y-up point on the arc's circle (not the module's own value)."""
    a = math.radians(deg)
    return (arc.center[0] + arc.radius * math.cos(a),
            arc.center[1] - arc.radius * math.sin(a))


# r = 10, vertex at the origin, edge 1 = +X, edge 2 = theta CCW from it (Y-up).
#   t = r / tan(theta/2)   tangent length along each edge
#   d = r / sin(theta/2)   vertex -> centre along the bisector (theta/2 from +X)
#   centre = d (cos(theta/2), -sin(theta/2)); T1 = t (1, 0); T2 = t (cos theta, -sin theta)
# Y-up angle of P seen from C = atan2(-(Py - Cy), Px - Cx). The minor arc spans 180 - theta.
#   theta 60 : t = 17.320508, d = 20      -> C (17.320508, -10); T2 (8.660254, -15)
#              T1 from C: atan2(-(0+10), 0) = -90 = 270 ; T2: atan2(5, -8.660254) = 150
#              CCW 150 -> 270 (span 120): the arc STARTS at T2's angle.
#   theta 90 : t = 10, d = 14.142136      -> C (10, -10); T2 (0, -10)
#              T1: 270 ; T2: atan2(0, -10) = 180 ; CCW 180 -> 270 (span 90).
#   theta 135: t = 4.142136, d = 10.823922 -> C (4.142136, -10); T2 (-2.928932, -2.928932)
#              T1: 270 ; T2 - C = (-7.071068, 7.071068) -> atan2(-7.071068, -7.071068) = -135 = 225 ; CCW 225 -> 270 (span 45).
CASES = [
    (60.0, (17.320508, -10.0), (17.320508, 0.0), (8.660254, -15.0), 150.0, 120.0),
    (90.0, (10.0, -10.0), (10.0, 0.0), (0.0, -10.0), 180.0, 90.0),
    (135.0, (4.142136, -10.0), (4.142136, 0.0), (-2.928932, -2.928932), 225.0, 45.0),
]


def test_default_radius_is_six_inches():
    assert FILLET_DEFAULT_RADIUS_MM == pytest.approx(6 * 25.4)


@pytest.mark.parametrize("theta, c, t1, t2, start, span", CASES)
def test_tangent_arc_numbers(theta, c, t1, t2, start, span):
    arc = fh.tangent_arc(_corner(_u(0), _u(theta)), 10.0)
    assert not isinstance(arc, fh.Refused)
    assert arc.center == pytest.approx(c, abs=1e-5)
    assert arc.radius == 10.0
    assert arc.t1 == pytest.approx(t1, abs=1e-5)
    assert arc.t2 == pytest.approx(t2, abs=1e-5)
    assert arc.start_deg == pytest.approx(start, abs=1e-4)      # [RED] Y-down revert
    assert arc.span_deg == pytest.approx(span, abs=1e-4)
    assert arc.start_is_t1 is False


@pytest.mark.parametrize("theta, c, t1, t2, start, span", CASES)
def test_arc_ends_are_the_tangent_points_in_y_up(theta, c, t1, t2, start, span):
    arc = fh.tangent_arc(_corner(_u(0), _u(theta)), 10.0)
    first = t1 if arc.start_is_t1 else t2
    last = t2 if arc.start_is_t1 else t1
    assert _on_arc(arc, arc.start_deg) == pytest.approx(first, abs=1e-4)
    assert _on_arc(arc, arc.start_deg + arc.span_deg) == pytest.approx(last, abs=1e-4)
    # bulge toward the corner: the arc midpoint is closer to the vertex than the centre is
    mid = _on_arc(arc, arc.start_deg + arc.span_deg / 2.0)
    assert math.hypot(*mid) < math.hypot(*arc.center)


def test_swapped_edges_start_at_t1():
    # edge 1 = +Y (visual up), edge 2 = +X: T1 (0,-10), T2 (10,0), C (10,-10).
    #   T1 from C: atan2(0, -10) = 180 ; T2: atan2(-(0+10), 0) = 270 ; CCW 180 -> 270.
    arc = fh.tangent_arc(_corner(_u(90), _u(0)), 10.0)
    assert arc.start_is_t1 is True
    assert arc.start_deg == pytest.approx(180.0, abs=1e-4)
    assert arc.span_deg == pytest.approx(90.0, abs=1e-4)
    assert arc.center == pytest.approx((10.0, -10.0), abs=1e-5)


@pytest.mark.parametrize("u1, u2", [(_u(0), _u(0)), (_u(0), _u(180))])
def test_parallel_and_collinear_edges_are_refused(u1, u2):
    res = fh.tangent_arc(_corner(u1, u2), 10.0)
    assert isinstance(res, fh.Refused) and res.reason == "parallel"
    assert res.message == PARALLEL


@pytest.mark.parametrize("len1, len2", [(5.0, 100.0), (100.0, 5.0)])
def test_tangent_point_past_a_far_end_is_refused(len1, len2):
    res = fh.tangent_arc(_corner(_u(0), _u(90), len1, len2), 10.0)   # t = 10
    assert isinstance(res, fh.Refused) and res.reason == "too_large"
    assert res.message == TOO_LARGE


def test_tangent_point_exactly_at_the_far_end_is_allowed():
    arc = fh.tangent_arc(_corner(_u(0), _u(90), 10.0, 10.0), 10.0)
    assert not isinstance(arc, fh.Refused)
    assert arc.t1 == pytest.approx((10.0, 0.0), abs=1e-9)


@pytest.mark.parametrize("r", [0.0, -3.0, float("nan")])
def test_non_positive_radius_is_refused(r):
    res = fh.tangent_arc(_corner(_u(0), _u(90)), r)
    assert isinstance(res, fh.Refused) and res.reason == "radius"
