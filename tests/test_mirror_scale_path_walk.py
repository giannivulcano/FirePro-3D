"""path_walk signed sweep + similarity map_piece (block mirror/scale DD5).

Expected values are hand-derived on Qt's Y-down circle: the point at Qt angle
a is (cx + r cos a, cy - r sin a); a positive sweep runs CCW on screen.
"""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform

from firepro3d import path_walk as pw


def _xy(q):
    return (round(q.x(), 6), round(q.y(), 6))


def _pt(a_deg, r=10.0, cx=0.0, cy=0.0):
    a = math.radians(a_deg)
    return (round(cx + r * math.cos(a), 6), round(cy - r * math.sin(a), 6))


NEG = pw.Arc(0.0, 0.0, 10.0, 90.0, -90.0)      # 90 deg, clockwise to 0 deg


def test_negative_arc_point_at_walks_clockwise():
    L = pw.length(NEG)
    assert L == pytest.approx(10.0 * math.pi / 2)
    assert _xy(pw.point_at(NEG, 0.0)) == _pt(90)
    assert _xy(pw.point_at(NEG, L / 2)) == _pt(45)          # [RED] gave 135
    assert _xy(pw.point_at(NEG, L)) == _pt(0)               # [RED] gave 180


def test_negative_arc_split_and_trim_keep_direction():
    L = pw.length(NEG)
    sp = pw.split(NEG, 0.0, L / 2)
    assert (sp.a0, sp.sweep) == pytest.approx((90.0, -45.0))  # [RED] (90, +45)
    tp = pw.trim_pieces((NEG,), 0.0, L / 2)
    assert (tp[0].a0, tp[0].sweep) == pytest.approx((90.0, -45.0))
    assert _xy(pw.point_at_total((NEG,), L / 2)) == _pt(45)


def test_negative_arc_tangent_is_direction_of_travel():
    # At 90 deg (top of circle) walking clockwise on screen = moving +x.
    dx, dy = pw.tangent_at(NEG, 0.0)
    assert (round(dx, 6), round(dy, 6)) == (1.0, 0.0)        # [RED] (-1, 0)


def test_negative_ellipse_arc_point_at_and_split():
    e = pw.EllipseArc(0.0, 0.0, 20.0, 10.0, 0.0, 90.0, -90.0)
    L = pw.length(e)
    assert _xy(pw.point_at(e, 0.0)) == (0.0, -10.0)
    end = pw.point_at(e, L)
    assert (round(end.x(), 3), round(end.y(), 3)) == (20.0, 0.0)   # [RED]
    sp = pw.split(e, 0.0, L)
    assert sp.sweep < 0
    assert pw.tangent_at(e, 0.0)[0] > 0.99                           # [RED]


def test_positive_sweep_unchanged():
    p = pw.Arc(0.0, 0.0, 10.0, 0.0, 90.0)
    L = pw.length(p)
    assert _xy(pw.point_at(p, L)) == _pt(90)
    sp = pw.split(p, 0.0, L / 2)
    assert (sp.a0, sp.sweep) == pytest.approx((0.0, 45.0))


def _mirror_x():
    """Scene reflection x -> -x (QTransform row-vector form)."""
    return QTransform(-1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def test_map_piece_reflects_arc_with_signed_sweep():
    a = pw.Arc(10.0, 0.0, 5.0, 0.0, 90.0)         # (15,0) CCW to (10,-5)
    m = pw.map_piece(a, _mirror_x())
    assert (m.cx, m.cy, m.r) == pytest.approx((-10.0, 0.0, 5.0))
    assert _xy(pw.point_at(m, 0.0)) == (-15.0, 0.0)   # image of the start
    assert _xy(pw.point_at(m, pw.length(m))) == (-10.0, -5.0)
    assert m.sweep == pytest.approx(-90.0)


def test_map_piece_scales_radius_and_ellipse_axes():
    t = QTransform.fromScale(2.0, 2.0)
    a = pw.map_piece(pw.Arc(1.0, 1.0, 5.0, 30.0, 60.0), t)
    assert (a.cx, a.cy, a.r, a.a0, a.sweep) == pytest.approx((2.0, 2.0, 10.0, 30.0, 60.0))
    e = pw.map_piece(pw.EllipseArc(0.0, 0.0, 4.0, 2.0, 15.0, 10.0, 80.0), t)
    assert (e.rx, e.ry, e.rot, e.t0, e.sweep) == pytest.approx((8.0, 4.0, 15.0, 10.0, 80.0))


@pytest.mark.parametrize("k", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_map_piece_reflected_ellipse_matches_mapped_points(k):
    e = pw.EllipseArc(5.0, 3.0, 6.0, 2.0, 25.0, 40.0, 120.0)
    t = QTransform()
    t.translate(7.0, -2.0)
    t.rotate(-30.0)
    t.scale(-1.5, 1.5)                    # reflecting similarity, s = 1.5
    m = pw.map_piece(e, t)
    s_src = pw.length(e) * k
    want = t.map(pw.point_at(e, s_src))
    got = pw.point_at(m, pw.length(m) * k)
    assert (got.x(), got.y()) == pytest.approx((want.x(), want.y()), abs=0.02)


def test_map_piece_seg_and_curve_map_points():
    t = _mirror_x()
    s = pw.map_piece(pw.Seg(1.0, 2.0, 3.0, 4.0), t)
    assert (s.x0, s.y0, s.x1, s.y1) == (-1.0, 2.0, -3.0, 4.0)
    c = pw.map_piece(pw.Curve(((0.0, 0.0), (2.0, 1.0))), t)
    assert c.pts == ((-0.0, 0.0), (-2.0, 1.0)) or c.pts == ((0.0, 0.0), (-2.0, 1.0))
