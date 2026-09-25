"""D9: offset_item per primitive — type preserved, style inherited, true distances.

scene-tools.md D9: Line/RefLine → parallel of the SAME type; open polyline →
mitered parallel; closed polyline → closed, mitered at every vertex incl. the
seam; Rect (incl. rotated) → rect ±d per side, same angle; Circle → concentric
r±d (geometric r, not pen-inflated); Arc → concentric, same angles; Regular
polygon → same sides + rotation, apothem ±d; Ellipse → rx±d, ry±d; Spline →
spline approximating the offset curve; Text → not offsettable.
"""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import tool_geometry as tg
from firepro3d.geometry_2d import ReferenceLineItem
from tests._modify_tools_helpers import PRIMITIVES


def _make(name):
    return PRIMITIVES[name][0]()


def test_line_parallel_same_type(qapp):
    for name in ("line", "refline"):
        src = _make(name)
        new = tg.offset_item(src, 10.0)
        assert type(new) is type(src)                                  # [RED] refline
        a, b = new.grip_points()[0], new.grip_points()[-1]
        assert abs(abs(a.y()) - 10.0) < 1e-6 and abs(abs(b.y()) - 10.0) < 1e-6


def test_refline_keeps_printed_flag(qapp):
    src = _make("refline")
    src.printed = True
    new = tg.offset_item(src, 10.0)
    assert isinstance(new, ReferenceLineItem) and new.printed is True


def test_circle_radius_is_geometric_not_pen_inflated(qapp):
    src = _make("circle")                                 # r = 50
    new = tg.offset_item(src, 10.0)
    assert new._radius == pytest.approx(60.0)             # [RED] (was 63)
    assert (new._center.x(), new._center.y()) == pytest.approx((0.0, 0.0))


def test_closed_polyline_seam_is_offset(qapp):
    src = _make("polyline_closed")                        # square 0..100 x 0..-100
    out = tg.offset_item(src, 10.0)                       # outward
    xs = sorted(round(p.x(), 3) for p in out._points)
    ys = sorted(round(p.y(), 3) for p in out._points)
    assert xs[0] == -10.0 and xs[-1] == 110.0            # [RED] seam
    assert ys[0] == -110.0 and ys[-1] == 10.0
    assert out.is_closed()
    # every vertex is a mitered corner: exactly the 4 offset-square corners
    assert sorted((round(p.x(), 3), round(p.y(), 3)) for p in out._points) == \
        sorted([(-10.0, 10.0), (110.0, 10.0), (110.0, -110.0), (-10.0, -110.0)])


def test_closed_polyline_inward(qapp):
    out = tg.offset_item(_make("polyline_closed"), -10.0)
    assert sorted((round(p.x(), 3), round(p.y(), 3)) for p in out._points) == \
        sorted([(10.0, -10.0), (90.0, -10.0), (90.0, -90.0), (10.0, -90.0)])


def test_open_polyline_mitered(qapp):
    src = _make("polyline_open")                          # (0,0)-(100,0)-(100,-100)
    out = tg.offset_item(src, 10.0)                       # left normal: +y then +x
    pts = [(round(p.x(), 3), round(p.y(), 3)) for p in out._points]
    assert pts == [(0.0, 10.0), (110.0, 10.0), (110.0, -100.0)]
    assert not out.is_closed()


def test_rect_offset_per_side(qapp):
    new = tg.offset_item(_make("rect"), 5.0)              # 100 x 50
    r = new.rect()
    assert (r.width(), r.height()) == pytest.approx((110.0, 60.0))
    assert (r.center().x(), r.center().y()) == pytest.approx((50.0, -25.0))


def test_rotated_rect_keeps_angle(qapp):
    src = _make("rect_rotated")
    new = tg.offset_item(src, 5.0)
    assert new._angle == pytest.approx(30.0)
    r = new.rect()
    assert (r.width(), r.height()) == pytest.approx((110.0, 60.0))
    # every source corner is sqrt(2)*5 from the matching offset corner, and
    # each offset edge is exactly 5 from the source outline
    for g in (new.grip_points()[1], new.grip_points()[3]):   # edge midpoints
        assert tg.distance_to_item(src, g) == pytest.approx(5.0, abs=1e-6)


def test_arc_concentric_same_angles(qapp):
    src = _make("arc")
    new = tg.offset_item(src, 5.0)
    assert new._radius == pytest.approx(55.0)
    assert (new._start_deg, new._span_deg) == pytest.approx(
        (src._start_deg, src._span_deg))


def test_polygon_stays_regular_apothem_plus_d(qapp):
    src = _make("polygon")                                # inscribed, R=50, 6 sides
    new = tg.offset_item(src, 5.0)
    apothem = src._radius_mm * math.cos(math.pi / 6)
    new_apothem = new._radius_mm * math.cos(math.pi / 6)
    assert type(new).__name__ == "RegularPolygonItem" and new._sides == 6
    assert new_apothem == pytest.approx(apothem + 5.0)   # [RED]
    assert new._rotation_deg == pytest.approx(src._rotation_deg)


def test_ellipse_rx_ry_plus_d(qapp):
    new = tg.offset_item(_make("ellipse"), 5.0)          # 80 x 40
    assert (new._rx, new._ry) == pytest.approx((85.0, 45.0))           # [RED]


def test_inward_too_large_returns_none(qapp):
    assert tg.offset_item(_make("circle"), -60.0) is None
    assert tg.offset_item(_make("ellipse"), -45.0) is None
    assert tg.offset_item(_make("rect"), -30.0) is None  # rect half-height 25
    assert tg.offset_item(_make("arc"), -60.0) is None
    assert tg.offset_item(_make("polygon"), -50.0) is None
    assert tg.offset_item(_make("polyline_closed"), -50.0) is None   # collapses
    assert tg.offset_item(_make("polyline_closed"), -60.0) is None   # inverts


def test_text_is_not_offsettable(qapp):
    for name in ("text", "text_rotated"):
        assert tg.offset_item(_make(name), 5.0) is None


def test_style_inherited(qapp):
    from PyQt6.QtGui import QColor
    for name in ("line", "polyline_closed", "rect", "circle", "arc",
                 "polygon", "ellipse", "spline"):
        src = _make(name)
        pen = src.pen(); pen.setColor(QColor("#ff0000")); pen.setWidthF(3.0)
        src.setPen(pen)
        if src.is_fillable():
            src.fill_type = "solid"
            src._display_fill_color = "#00ff00"
        new = tg.offset_item(src, 5.0)
        assert new.pen().color().name() == "#ff0000", name
        assert new.pen().widthF() == pytest.approx(3.0), name
        if src.is_fillable():
            assert new.fill_type == "solid", name
            assert new._display_fill_color == "#00ff00", name


def test_source_is_not_mutated(qapp):
    for name in ("line", "polyline_closed", "rect", "circle", "arc",
                 "polygon", "ellipse", "spline", "rect_rotated"):
        src = _make(name)
        before = src.to_dict()
        tg.offset_item(src, 5.0)
        assert src.to_dict() == before, name


def test_spline_offset_is_approximately_d(qapp):
    src = _make("spline")
    new = tg.offset_item(src, 5.0)
    assert type(new).__name__ == "SplineItem"
    # Measured at the offset CURVE's midpoint (a control point is off-curve,
    # so its distance to the source says nothing about the offset).
    poly = new.path().toSubpathPolygons()[0]
    d = tg.distance_to_item(src, poly.at(poly.count() // 2))
    assert d == pytest.approx(5.0, rel=0.35)


def test_spline_offset_curve_stays_near_d(qapp):
    """The offset CURVE (not just a control point) stays ~d from the source."""
    src = _make("spline")
    new = tg.offset_item(src, 5.0)
    poly = new.path().toSubpathPolygons()[0]
    n = poly.count()
    ds = [tg.distance_to_item(src, poly.at(i)) for i in range(n // 10, n - n // 10)]
    assert min(ds) == pytest.approx(5.0, rel=0.35)
    assert max(ds) == pytest.approx(5.0, rel=0.35)


def test_distance_to_item_open_polyline_uses_segments(qapp):
    src = _make("polyline_open")                          # (0,0)-(100,0)-(100,-100)
    # point beyond the first segment's end on its infinite line: true distance > 0
    assert tg.distance_to_item(src, QPointF(-50, 0)) == pytest.approx(50.0)   # [RED]


def test_distance_to_item_circle_is_geometric(qapp):
    src = _make("circle")
    assert tg.distance_to_item(src, QPointF(100, 0)) == pytest.approx(50.0, abs=0.05)
    assert tg.distance_to_item(src, QPointF(20, 0)) == pytest.approx(30.0, abs=0.05)


def test_offset_side_sign(qapp):
    # closed: inside -> -1 (inward), outside -> +1
    assert tg.offset_side_sign(_make("circle"), QPointF(1, 0)) == -1.0
    assert tg.offset_side_sign(_make("circle"), QPointF(400, -400)) == 1.0
    assert tg.offset_side_sign(_make("rect_rotated"), QPointF(50, -25)) == -1.0
    assert tg.offset_side_sign(_make("polyline_closed"), QPointF(50, -50)) == -1.0
    # open line: left normal of (0,0)->(100,0) is +y (scene)
    assert tg.offset_side_sign(_make("line"), QPointF(50, 20)) == 1.0
    assert tg.offset_side_sign(_make("line"), QPointF(50, -20)) == -1.0
    # open polyline: the NEAREST segment decides (second leg, x=100 going -y:
    # left normal is +x)
    assert tg.offset_side_sign(_make("polyline_open"), QPointF(120, -80)) == 1.0
    assert tg.offset_side_sign(_make("polyline_open"), QPointF(80, -80)) == -1.0
