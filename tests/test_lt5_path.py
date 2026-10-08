"""LT5 B -- path_walk end frames, trims and tangents (design B, Q5 / Q6).

Ground truth is never the new helpers' own math: tangents are checked
against central differences of the pre-existing ``point_at``; arc chords
against Qt's own angle -> point (``QPainterPath.arcMoveTo``, the call
``ArcItem._rebuild_path`` builds its arc with) and the chord-tangent angle
theorem.
"""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath

from firepro3d import path_walk as pw

_H = 1e-4


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def _fd_tangent(p, s):
    """Central difference of point_at (one-sided at the ends)."""
    L = pw.length(p)
    a, b = max(s - _H, 0.0), min(s + _H, L)
    pa, pb = pw.point_at(p, a), pw.point_at(p, b)
    return _unit(pb.x() - pa.x(), pb.y() - pa.y())


def _spline_curve():
    from firepro3d.geometry_2d import SplineItem
    sp = SplineItem([QPointF(0, 0), QPointF(50, -60), QPointF(100, 0),
                     QPointF(150, -40)])
    (c,) = sp.stroke_pieces()
    return c


PIECES = {
    "seg": pw.Seg(10, 5, -20, 45),
    "arc_q1": pw.Arc(0, 0, 50, 0.0, 90.0),
    "arc_wrap": pw.Arc(3, -7, 20, 300.0, 120.0),
    "ellipse": pw.EllipseArc(5, 5, 40, 15, 30.0, 10.0, 200.0),
    "curve": None,
}


@pytest.mark.parametrize("name", list(PIECES))
@pytest.mark.parametrize("frac", [0.0, 0.31, 0.77, 1.0])
def test_tangent_matches_point_at_differences(qapp, name, frac):
    p = PIECES[name] or _spline_curve()
    s = frac * pw.length(p)
    got = pw.tangent_at(p, s)
    exp = _fd_tangent(p, s)
    assert got == pytest.approx(exp, abs=2e-3)
    assert math.hypot(*got) == pytest.approx(1.0)


def test_arc_tangent_sign_qt_y_down():
    # Qt CCW from 0 deg on a Y-down scene: the start (50, 0) heads UP (-y).
    assert pw.tangent_at(pw.Arc(0, 0, 50, 0.0, 90.0), 0.0) == pytest.approx(
        (0.0, -1.0), abs=1e-12)


def test_end_frame_line_tangent_and_chord_agree():
    pcs = (pw.Seg(0, 0, 100, 0),)
    at, out = pw.end_frame(pcs, "start", 0.0)
    assert (at.x(), at.y()) == (0.0, 0.0) and out == pytest.approx((-1.0, 0.0))
    at, out = pw.end_frame(pcs, "finish", 0.0)
    assert (at.x(), at.y()) == (100.0, 0.0) and out == pytest.approx((1.0, 0.0))
    assert pw.end_frame(pcs, "finish", 30.0)[1] == pytest.approx((1.0, 0.0))


def test_end_frame_polyline_uses_its_end_segments():
    pcs = (pw.Seg(0, 0, 0, -50), pw.Seg(0, -50, 80, -50))
    at, out = pw.end_frame(pcs, "start", 0.0)
    assert (at.x(), at.y()) == (0.0, 0.0) and out == pytest.approx((0.0, 1.0))
    at, out = pw.end_frame(pcs, "finish", 0.0)
    assert (at.x(), at.y()) == (80.0, -50.0) and out == pytest.approx((1.0, 0.0))
    # A trim reaching past the corner: chord from the end to the trim point.
    at, out = pw.end_frame(pcs, "finish", 100.0)       # trim point (0, -30)
    assert out == pytest.approx(_unit(80.0, -20.0))


def _qt_point(cx, cy, r, deg):
    """Qt's own angle -> point on the circle (``arcMoveTo``), Y-down scene."""
    path = QPainterPath()
    path.arcMoveTo(QRectF(cx - r, cy - r, 2 * r, 2 * r), deg)
    return path.currentPosition()


@pytest.mark.parametrize("which", ["start", "finish"])
def test_e4_arc_end_aligns_on_the_endpoint_to_trim_point_chord(qapp, which):
    """E4 (path level): Q6 -- -X runs from the endpoint to the trim point."""
    cx, cy, r, a0, sweep, trim = 0.0, 0.0, 50.0, 0.0, 90.0, 10.0
    arc = pw.Arc(cx, cy, r, a0, sweep)
    d = math.degrees(trim / r)                 # arc length -> central angle
    if which == "start":
        end_pt, trim_pt = _qt_point(cx, cy, r, a0), _qt_point(cx, cy, r, a0 + d)
    else:
        end_pt = _qt_point(cx, cy, r, a0 + sweep)
        trim_pt = _qt_point(cx, cy, r, a0 + sweep - d)
    at, out = pw.end_frame((arc,), which, trim)
    assert (at.x(), at.y()) == pytest.approx((end_pt.x(), end_pt.y()), abs=1e-6)
    exp = _unit(end_pt.x() - trim_pt.x(), end_pt.y() - trim_pt.y())
    # Qt places non-quadrant arc points via its Bezier fit (~0.04 mm on
    # r = 50): 2e-3 still separates the chord from the tangent (0.1 rad).
    assert out == pytest.approx(exp, abs=2e-3)
    # The chord is not the tangent: chord-tangent angle = half the subtended
    # angle (trim / r rad) -- 5.73 deg here.
    _, tan_out = pw.end_frame((arc,), which, 0.0)
    ang = math.degrees(math.acos(max(-1.0, min(1.0, out[0] * tan_out[0]
                                               + out[1] * tan_out[1]))))
    assert ang == pytest.approx(math.degrees(trim / r / 2.0), abs=1e-4)


def test_end_frame_trim_past_length_clamps_to_the_other_end():
    pcs = (pw.Seg(0, 0, 100, 0),)
    at, out = pw.end_frame(pcs, "start", 250.0)
    assert (at.x(), at.y()) == (0.0, 0.0) and out == pytest.approx((-1.0, 0.0))


def test_end_frame_degenerate():
    assert pw.end_frame((), "start", 0.0) is None
    assert pw.end_frame((pw.Seg(5, 5, 5, 5),), "finish", 0.0) is None
    # Zero-length pieces around a live one are skipped.
    pcs = (pw.Seg(0, 0, 0, 0), pw.Seg(0, 0, 10, 0), pw.Seg(10, 0, 10, 0))
    assert pw.end_frame(pcs, "start", 0.0)[1] == pytest.approx((-1.0, 0.0))
    assert pw.end_frame(pcs, "finish", 0.0)[1] == pytest.approx((1.0, 0.0))


def test_end_frame_coincident_open_polyline_falls_back_to_tangent():
    # Open square loop (end == start): the chord to a full-length trim point
    # is zero, so the end orients on its tangent instead.
    pcs = (pw.Seg(0, 0, 10, 0), pw.Seg(10, 0, 10, -10),
           pw.Seg(10, -10, 0, -10), pw.Seg(0, -10, 0, 0))
    at, out = pw.end_frame(pcs, "finish", 40.0)
    assert (at.x(), at.y()) == (0.0, 0.0) and out == pytest.approx((0.0, 1.0))


def test_trim_pieces_cross_piece_lengths_and_endpoints():
    pcs = (pw.Seg(0, 0, 30, 0), pw.Arc(30, -20, 20, 270.0, 90.0),
           pw.Seg(50, -20, 50, -60))
    total = pw.total_length(pcs)
    out = pw.trim_pieces(pcs, 40.0, 25.0)
    assert pw.total_length(out) == pytest.approx(total - 65.0)
    first = pw.point_at(out[0], 0.0)
    exp0 = pw.point_at_total(pcs, 40.0)
    assert (first.x(), first.y()) == pytest.approx((exp0.x(), exp0.y()))
    last = pw.point_at(out[-1], pw.length(out[-1]))
    exp1 = pw.point_at_total(pcs, total - 25.0)
    assert (last.x(), last.y()) == pytest.approx((exp1.x(), exp1.y()))
    assert len(out) == 2                      # the first Seg is wholly cut


def test_trim_pieces_identity_and_over_trim():
    pcs = (pw.Seg(0, 0, 30, 0), pw.Seg(30, 0, 30, 30))
    assert pw.trim_pieces(pcs, 0.0, 0.0) == pcs
    kept = pw.trim_pieces(pcs, 0.0, 5.0)
    assert kept[0] is pcs[0]                  # wholly kept: same object
    assert pw.trim_pieces(pcs, 40.0, 20.0) == ()
    assert pw.trim_pieces(pcs, 60.0, 0.0) == ()


def test_trim_pieces_on_a_spline_curve(qapp):
    c = _spline_curve()
    L = pw.length(c)
    (out,) = pw.trim_pieces((c,), 12.0, 7.0)
    assert pw.length(out) == pytest.approx(L - 19.0, abs=1e-6)
    a, e = pw.point_at(out, 0.0), pw.point_at(c, 12.0)
    assert (a.x(), a.y()) == pytest.approx((e.x(), e.y()))
