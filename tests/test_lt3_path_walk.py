"""LT3 H3-a — path_walk: analytic pieces, arc length, D-L9 phase, split."""
import math
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath, QTransform
from firepro3d import path_walk as pw


def test_seg_length_and_point():
    s = pw.Seg(0, 0, 30, 40)
    assert pw.length(s) == pytest.approx(50)
    p = pw.point_at(s, 25)
    assert (p.x(), p.y()) == pytest.approx((15, 20))


def test_seg_canonical_direction_folds_to_half_turn():
    # Opposite draw directions canonicalise to the same piece (D-L9).
    a = pw.canonical(pw.Seg(10, 5, 0, 5))
    b = pw.canonical(pw.Seg(0, 5, 10, 5))
    assert a == b


def test_seg_phase_is_axis_projection_from_anchor():
    # Horizontal axis: phase = x of start relative to the anchor's projection.
    assert pw.phase0(pw.canonical(pw.Seg(7, 3, 20, 3)), (2.0, 99.0)) == pytest.approx(5.0)
    # Same axis, gapped, drawn reversed: phase continues the same rhythm.
    assert pw.phase0(pw.canonical(pw.Seg(40, 3, 25, 3)), (2.0, 99.0)) == pytest.approx(23.0)


def test_arc_point_matches_qt_arcto_convention():
    a = pw.Arc(0, 0, 10, 0.0, 90.0)
    end = pw.point_at(a, pw.length(a))
    path = QPainterPath()
    r = QRectF(-10, -10, 20, 20)
    path.arcMoveTo(r, 0.0)
    path.arcTo(r, 0.0, 90.0)
    assert (end.x(), end.y()) == pytest.approx((path.currentPosition().x(),
                                                path.currentPosition().y()), abs=1e-6)


def test_arc_phase_is_radius_times_start_angle():
    a = pw.Arc(0, 0, 10, 90.0, 45.0)
    assert pw.phase0(a, (0.0, 0.0)) == pytest.approx(10 * math.pi / 2)


def test_ellipse_arc_length_quarter_matches_numeric():
    e = pw.EllipseArc(0, 0, 20, 10, 0.0, 0.0, 90.0)
    # Ramanujan full perimeter / 4 for a=20 b=10.
    a, b = 20, 10
    h = ((a - b) / (a + b)) ** 2
    quarter = math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h))) / 4
    assert pw.length(e) == pytest.approx(quarter, rel=1e-3)


def test_ellipse_point_matches_qt_parametric_arcto():
    e = pw.EllipseArc(5, 5, 20, 10, 30.0, 0.0, 360.0)
    t = QTransform()
    t.translate(5, 5)
    t.rotate(-30.0)
    path = QPainterPath()
    path.arcMoveTo(QRectF(-20, -10, 40, 20), 45.0)
    want = t.map(path.currentPosition())
    got = pw.point_at_param(e, 45.0)
    assert (got.x(), got.y()) == pytest.approx((want.x(), want.y()), abs=1e-6)


def test_split_seg_exact():
    s = pw.split(pw.Seg(0, 0, 10, 0), 2.0, 5.0)
    assert s == pw.Seg(2.0, 0.0, 5.0, 0.0)


def test_split_arc_stays_analytic():
    s = pw.split(pw.Arc(0, 0, 10, 0.0, 180.0), 0.0, 10 * math.pi / 2)
    assert isinstance(s, pw.Arc)
    assert s.sweep == pytest.approx(90.0)


def test_curve_from_path_flattens_and_measures():
    path = QPainterPath(QPointF(0, 0))
    path.lineTo(10, 0)
    path.lineTo(10, 10)
    c = pw.Curve.from_path(path)
    assert pw.length(c) == pytest.approx(20)
    assert pw.phase0(c, (123.0, 4.0)) == 0.0


def _cubic_pt(b, t):
    u = 1.0 - t
    w = (u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t)
    return (sum(k * p[0] for k, p in zip(w, b)), sum(k * p[1] for k, p in zip(w, b)))


def test_curve_from_path_stays_on_the_analytic_cubic():
    # The analytic cubic is the ground truth: the flattened Curve
    # -- vertices AND chord midpoints -- must stay within ±0.02 mm of it.
    b = ((0.0, 0.0), (10.0, 20.0), (30.0, -5.0), (50.0, 10.0))
    path = QPainterPath(QPointF(*b[0]))
    path.cubicTo(QPointF(*b[1]), QPointF(*b[2]), QPointF(*b[3]))
    c = pw.Curve.from_path(path)
    dense = [_cubic_pt(b, i / 20000) for i in range(20001)]

    def dist(x, y):
        return min(math.hypot(x - px, y - py) for px, py in dense)

    probes = list(c.pts) + [((x0 + x1) / 2, (y0 + y1) / 2)
                            for (x0, y0), (x1, y1) in zip(c.pts, c.pts[1:])]
    worst = max(dist(x, y) for x, y in probes)
    assert worst <= 0.02, worst
    assert c.pts[0] == pytest.approx(b[0]) and c.pts[-1] == pytest.approx(b[3])


def test_map_piece_rotates_arc_start_angle():
    t = QTransform()
    t.rotate(-90.0)                      # Y-up CCW 90° (Qt CW-positive)
    m = pw.map_piece(pw.Arc(0, 0, 10, 0.0, 30.0), t)
    assert m.a0 == pytest.approx(90.0)
    p0 = pw.point_at(m, 0.0)
    want = t.map(pw.point_at(pw.Arc(0, 0, 10, 0.0, 30.0), 0.0))
    assert (p0.x(), p0.y()) == pytest.approx((want.x(), want.y()), abs=1e-9)


def test_append_path_arc_emits_curve_elements():
    path = QPainterPath()
    pw.append(path, pw.Arc(0, 0, 10, 0.0, 90.0))
    kinds = {path.elementAt(i).type for i in range(path.elementCount())}
    assert QPainterPath.ElementType.CurveToElement in kinds


def test_split_at_zero_breaks_arc_crossing_zero():
    parts = pw.split_at_zero(pw.Arc(0, 0, 10, 330.0, 60.0))
    assert [(p.a0, p.sweep) for p in parts] == [pytest.approx((330.0, 30.0)),
                                                pytest.approx((0.0, 30.0))]


def test_split_at_zero_full_circle_is_one_piece():
    assert pw.split_at_zero(pw.Arc(0, 0, 10, 0.0, 360.0)) == (pw.Arc(0, 0, 10, 0.0, 360.0),)
    parts = pw.split_at_zero(pw.Arc(0, 0, 10, 30.0, 360.0))
    assert [(p.a0, p.sweep) for p in parts] == [pytest.approx((30.0, 330.0)),
                                                pytest.approx((0.0, 30.0))]


def test_split_at_zero_ellipse_and_passthrough():
    parts = pw.split_at_zero(pw.EllipseArc(0, 0, 20, 10, 15.0, 300.0, 120.0))
    assert [(p.t0, p.sweep) for p in parts] == [pytest.approx((300.0, 60.0)),
                                                pytest.approx((0.0, 60.0))]
    s = pw.Seg(0, 0, 1, 0)
    assert pw.split_at_zero(s) == (s,)
    a = pw.Arc(0, 0, 10, 10.0, 90.0)
    assert pw.split_at_zero(a) == (a,)


def test_curve_split_keeps_interior_vertices():
    c = pw.Curve(((0, 0), (10, 0), (10, 10), (20, 10)))
    s = pw.split(c, 5.0, 25.0)
    assert s.pts == ((5.0, 0.0), (10.0, 0.0), (10.0, 10.0), (15.0, 10.0))
    assert pw.length(s) == pytest.approx(20.0)
    p = pw.point_at(c, 15.0)
    assert (p.x(), p.y()) == pytest.approx((10.0, 5.0))


@pytest.mark.parametrize("piece", [pw.Arc(3, 4, 0.0, 0.0, 90.0),
                                   pw.EllipseArc(3, 4, 0.0, 0.0, 0.0, 0.0, 90.0)])
def test_zero_length_pieces_do_not_crash_point_queries(piece):
    p = pw.point_at(piece, 0.0)
    assert (p.x(), p.y()) == pytest.approx((3.0, 4.0))
    # A degenerate piece before a real one is skipped by the total walk.
    q = pw.point_at_total((piece, pw.Seg(0, 0, 10, 0)), 5.0)
    assert (q.x(), q.y()) == pytest.approx((5.0, 0.0))
    only = pw.point_at_total((piece,), 0.0)
    assert (only.x(), only.y()) == pytest.approx((3.0, 4.0))


def test_map_piece_refuses_reflection():
    with pytest.raises(ValueError):
        pw.map_piece(pw.Arc(0, 0, 10, 0.0, 30.0), QTransform(-1, 0, 0, 1, 0, 0))
