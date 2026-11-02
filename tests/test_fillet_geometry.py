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

# -- find_corner -------------------------------------------------------------

def _poly(pts, closed=False, ref="P"):
    return fh.Shape("poly", tuple(pts), closed, ref)


def _line(a, b, ref):
    return fh.Shape("line", (tuple(a), tuple(b)), False, ref)


def test_open_polyline_interior_vertex_is_a_corner_ends_are_not():
    sh = _poly([(0, 0), (100, 0), (100, -100)])
    c = fh.find_corner([sh], (100.0, 0.0), 15.0)
    assert c.kind == "vertex" and c.vertex == (100, 0) and c.idx1 == c.idx2 == 1
    assert c.u1 == pytest.approx((-1.0, 0.0)) and c.u2 == pytest.approx((0.0, -1.0))
    assert (c.len1, c.len2) == pytest.approx((100.0, 100.0))
    assert fh.find_corner([sh], (0.0, 0.0), 15.0) is None            # free end
    assert fh.find_corner([sh], (100.0, -100.0), 15.0) is None


def test_closed_polyline_every_vertex_is_a_corner():
    sh = _poly([(0, 0), (100, 0), (100, -100)], closed=True)
    c = fh.find_corner([sh], (0.0, 0.0), 15.0)
    # vertex 0: previous vertex (100,-100), next (100,0)
    assert c.idx1 == 0
    assert c.u1 == pytest.approx((1 / math.sqrt(2), -1 / math.sqrt(2)))
    assert c.u2 == pytest.approx((1.0, 0.0))
    assert c.len1 == pytest.approx(math.hypot(100, 100))


def test_corner_aperture_is_inclusive():
    sh = _poly([(0, 0), (100, 0), (100, -100)])
    assert fh.find_corner([sh], (100.0, 14.9), 15.0) is not None
    assert fh.find_corner([sh], (100.0, 15.1), 15.0) is None


def test_two_corners_in_the_aperture_the_nearer_one_wins():
    a, b = _line((100, 0), (0, 0), "A"), _line((0, -100), (0, 0), "B")       # corner at (0, 0)
    c_, d_ = _line((200, 10), (10, 10), "C"), _line((10, -90), (10, 10), "D")  # corner at (10, 10)
    for cursor, want in (((2.0, 2.0), (0.0, 0.0)), ((9.0, 9.0), (10.0, 10.0))):
        got = fh.find_corner([a, b, c_, d_], cursor, 15.0)
        assert got.vertex == pytest.approx(want)


def test_cursor_exactly_at_a_crossing_picks_the_corner_with_the_longest_halves():
    # + crossing at the origin: the right half of A is 300 long, the up half of B is 200,
    # every other half is 50 -> the (right, up) quadrant has the largest la + lb.
    a, b = _line((-50, 0), (300, 0), "A"), _line((0, -200), (0, 50), "B")
    c = fh.find_corner([a, b], (0.0, 0.0), 15.0)                     # rn == 0: no quadrant hint
    assert (c.len1, c.len2) == pytest.approx((300.0, 200.0))
    assert c.u1 == pytest.approx((1.0, 0.0)) and c.u2 == pytest.approx((0.0, -1.0))


def test_far_lines_are_not_paired_and_the_corner_is_unchanged(monkeypatch):
    near = [_line((100, 0), (0, 0), "A"), _line((0, -100), (0, 0), "B")]
    far = [_line((1000 + 10 * i, 500), (1000 + 10 * i, 900 + i), f"F{i}") for i in range(40)]
    want = fh.find_corner(near, (0.0, 0.0), 15.0)
    calls = []
    real = fh._pair_corner
    monkeypatch.setattr(fh, "_pair_corner", lambda a, b, p, tol: (calls.append((a.ref, b.ref)), real(a, b, p, tol))[1])
    got = fh.find_corner(far + near + far[::-1], (0.0, 0.0), 15.0)
    assert got == want
    assert calls == [("A", "B")]                                     # no far line is ever paired


def test_lines_whose_ends_meet_form_a_corner():
    a, b = _line((100, 0), (0, 0), "A"), _line((0, -100), (0, 0), "B")
    c = fh.find_corner([a, b], (0.0, 0.0), 15.0)
    assert c.kind == "lines" and c.vertex == pytest.approx((0.0, 0.0))
    assert (c.ref1, c.ref2, c.idx1, c.idx2) == ("A", "B", 0, 0)       # far ends kept
    assert c.u1 == pytest.approx((1.0, 0.0)) and c.u2 == pytest.approx((0.0, -1.0))
    assert (c.len1, c.len2) == pytest.approx((100.0, 100.0))


def test_crossing_lines_cursor_quadrant_picks_the_corner():
    a, b = _line((-100, 0), (100, 0), "A"), _line((0, -100), (0, 100), "B")
    c = fh.find_corner([a, b], (5.0, -5.0), 15.0)          # visual upper-right
    assert (c.idx1, c.idx2) == (1, 0)
    assert c.u1 == pytest.approx((1.0, 0.0)) and c.u2 == pytest.approx((0.0, -1.0))
    c = fh.find_corner([a, b], (-5.0, 5.0), 15.0)          # visual lower-left
    assert (c.idx1, c.idx2) == (0, 1)
    assert c.u1 == pytest.approx((-1.0, 0.0)) and c.u2 == pytest.approx((0.0, 1.0))


def test_lines_that_only_meet_when_extended_are_not_hover_corners():
    # NEAR end listed first in each line: without the same-side collapse in _halves the
    # tie goes to the first-listed (near) end and idx would be (0, 0). (Dry run: with
    # the far end listed first the collapse mutation stayed GREEN.)
    a, b = _line((50, 0), (0, 0), "A"), _line((100, -30), (100, -100), "B")
    assert fh.find_corner([a, b], (100.0, 0.0), 15.0) is None
    c = fh.corner_between_lines(a, b, (100.0, -5.0))
    assert c.vertex == pytest.approx((100.0, 0.0))
    assert (c.idx1, c.idx2) == (1, 1)                      # the far ends (0,0) and (100,-100)
    assert c.u1 == pytest.approx((-1.0, 0.0)) and c.u2 == pytest.approx((0.0, -1.0))
    assert (c.len1, c.len2) == pytest.approx((100.0, 100.0))


def test_parallel_lines_have_no_corner():
    a, b = _line((0, 0), (100, 0), "A"), _line((0, -50), (100, -50), "B")
    assert fh.find_corner([a, b], (0.0, 0.0), 15.0) is None
    res = fh.corner_between_lines(a, b, (50.0, -25.0))
    assert isinstance(res, fh.Refused) and res.message == PARALLEL


# -- poly_pieces -------------------------------------------------------------

def test_open_polyline_splits_in_two():
    pts = [(0, 0), (100, 0), (100, -100)]
    pcs = fh.poly_pieces(pts, False, 1, (90.0, 0.0), (100.0, -10.0))
    assert [p.pts for p in pcs] == [((0, 0), (90.0, 0.0)), ((100.0, -10.0), (100, -100))]
    assert [(p.start_tp, p.end_tp) for p in pcs] == [(None, "prev"), ("next", None)]


def test_zero_length_remainder_is_not_created():
    pts = [(0, 0), (100, 0), (100, -100)]
    pcs = fh.poly_pieces(pts, False, 1, (0.0, 0.0), (100.0, -10.0))   # t_prev == P0
    assert [p.pts for p in pcs] == [((100.0, -10.0), (100, -100))]


def test_closed_ring_becomes_one_open_polyline():
    # rect (0,0)-(100,-50): TL (0,-50), TR (100,-50), BR (100,0), BL (0,0); corner BR (i = 2)
    ring = [(0, -50), (100, -50), (100, 0), (0, 0)]
    pcs = fh.poly_pieces(ring, True, 2, (100.0, -10.0), (90.0, 0.0))
    assert len(pcs) == 1
    assert pcs[0].pts == ((90.0, 0.0), (0, 0), (0, -50), (100, -50), (100.0, -10.0))
    assert (pcs[0].start_tp, pcs[0].end_tp) == ("next", "prev")
