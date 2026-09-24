"""Per-primitive dimension_specs() + typed setters (2d-geometry.md §8). Pure."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem, ReferenceLineItem
from firepro3d.selection_readouts import DimSpec, readout_text
from firepro3d.scale_manager import ScaleManager


def _by_key(item):
    return {s.key: s for s in item.dimension_specs()}


def test_line_length_spec(qapp):
    ln = LineItem(QPointF(0, 0), QPointF(300, 400))
    s = _by_key(ln)["length"]
    assert s.kind == "linear" and s.field == "Length" and s.prefix == ""
    assert s.value == pytest.approx(500.0)
    assert (s.a, s.b) == (QPointF(0, 0), QPointF(300, 400))


def test_line_set_length_keeps_pt1(qapp):
    ln = LineItem(QPointF(10, 10), QPointF(110, 10))
    _by_key(ln)["length"].apply(250.0)
    assert ln.line().p1() == QPointF(10, 10)
    assert ln.line().p2().x() == pytest.approx(260.0)
    assert ln.line().p2().y() == pytest.approx(10.0)


def test_reference_line_inherits_length(qapp):
    rl = ReferenceLineItem(QPointF(0, 0), QPointF(0, 100))
    assert _by_key(rl)["length"].value == pytest.approx(100.0)


def test_default_specs_empty(qapp):
    from firepro3d.geometry_2d import SplineItem
    sp = SplineItem([QPointF(0, 0), QPointF(10, 0), QPointF(20, 10), QPointF(30, 0)])
    assert sp.dimension_specs() == []


def test_readout_text_prefix_and_units(qapp):
    sm = ScaleManager()
    s = DimSpec(kind="linear", key="r", field="Radius", prefix="R",
                value=304.8, field_kind="dimension", apply=lambda v: None,
                a=QPointF(), b=QPointF(1, 0))
    assert readout_text(s, sm) == "R " + sm.format_length(304.8)
    ang = DimSpec(kind="angular", key="a", field="Angle", prefix="",
                  value=270.0, field_kind="span", apply=lambda v: None,
                  center=QPointF(), ref_radius=10.0, start_deg=0.0, span_deg=270.0)
    assert readout_text(ang, sm) == "270°"


from firepro3d.geometry_2d import RectangleItem


def test_rect_specs_width_height(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    d = _by_key(r)
    assert d["width"].value == pytest.approx(200.0)
    assert d["height"].value == pytest.approx(100.0)
    # width measured along the visual bottom edge (BL -> BR), height BR -> TR
    assert d["width"].a == QPointF(0, 100) and d["width"].b == QPointF(200, 100)
    assert d["height"].a == QPointF(200, 100) and d["height"].b == QPointF(200, 0)


@pytest.mark.parametrize("angle", [0.0, 30.0])
def test_rect_set_width_keeps_left_edge(qapp, angle):
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    r.set_angle(angle)
    bl0 = r.mapToScene(QPointF(r.rect().left(), r.rect().bottom()))
    tl0 = r.mapToScene(r.rect().topLeft())
    _by_key(r)["width"].apply(350.0)
    assert r.rect().width() == pytest.approx(350.0)
    bl1 = r.mapToScene(QPointF(r.rect().left(), r.rect().bottom()))
    tl1 = r.mapToScene(r.rect().topLeft())
    assert (bl1.x(), bl1.y()) == pytest.approx((bl0.x(), bl0.y()))
    assert (tl1.x(), tl1.y()) == pytest.approx((tl0.x(), tl0.y()))


@pytest.mark.parametrize("angle", [0.0, 30.0])
def test_rect_set_height_keeps_bottom_edge(qapp, angle):
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    r.set_angle(angle)
    bl0 = r.mapToScene(QPointF(r.rect().left(), r.rect().bottom()))
    br0 = r.mapToScene(QPointF(r.rect().right(), r.rect().bottom()))
    _by_key(r)["height"].apply(40.0)
    assert r.rect().height() == pytest.approx(40.0)
    bl1 = r.mapToScene(QPointF(r.rect().left(), r.rect().bottom()))
    br1 = r.mapToScene(QPointF(r.rect().right(), r.rect().bottom()))
    assert (bl1.x(), bl1.y()) == pytest.approx((bl0.x(), bl0.y()))
    assert (br1.x(), br1.y()) == pytest.approx((br0.x(), br0.y()))


from firepro3d.geometry_2d import CircleItem, ArcItem


def test_circle_radius_spec_and_setter(qapp):
    c = CircleItem(QPointF(50, 60), 100.0)
    s = _by_key(c)["radius"]
    assert s.prefix == "R" and s.value == pytest.approx(100.0)
    assert s.a == QPointF(50, 60) and s.b == QPointF(150, 60)   # single radial, +x
    s.apply(40.0)
    assert c._radius == pytest.approx(40.0) and c._center == QPointF(50, 60)
    assert c.rect().width() == pytest.approx(80.0)


def test_circle_radius_floor(qapp):
    c = CircleItem(QPointF(0, 0), 100.0)
    c.set_radius(0.2)
    assert c._radius == pytest.approx(1.0)       # existing floor (apply_grip)


def test_arc_specs(qapp):
    a = ArcItem(QPointF(0, 0), 100.0, 30.0, 120.0)
    d = _by_key(a)
    ang, rad = d["angle"], d["radius"]
    assert ang.kind == "angular" and ang.field_kind == "span"
    assert ang.value == pytest.approx(120.0)
    assert (ang.start_deg, ang.span_deg, ang.ref_radius) == pytest.approx((30.0, 120.0, 100.0))
    assert ang.maximum < 360.0
    assert rad.prefix == "R" and rad.value == pytest.approx(100.0)
    # radius along the START radial: (r cos30, -r sin30)
    assert (rad.b.x(), rad.b.y()) == pytest.approx((100 * math.cos(math.radians(30)),
                                                    -100 * math.sin(math.radians(30))))


def test_arc_set_span_keeps_start(qapp):
    a = ArcItem(QPointF(0, 0), 100.0, 30.0, 120.0)
    _by_key(a)["angle"].apply(45.0)
    assert a._start_deg == pytest.approx(30.0) and a._span_deg == pytest.approx(45.0)


def test_arc_set_radius_keeps_centre_and_angles(qapp):
    a = ArcItem(QPointF(5, 5), 100.0, 30.0, 120.0)
    _by_key(a)["radius"].apply(250.0)
    assert a._radius == pytest.approx(250.0) and a._center == QPointF(5, 5)
    assert (a._start_deg, a._span_deg) == pytest.approx((30.0, 120.0))


from firepro3d.geometry_2d import EllipseItem, RegularPolygonItem


def test_ellipse_r1_r2(qapp):
    e = EllipseItem(QPointF(0, 0), 300.0, 100.0, 0.0)
    d = _by_key(e)
    assert (d["r1"].field, d["r1"].prefix, d["r1"].value) == ("R1", "R1", pytest.approx(300.0))
    assert (d["r2"].field, d["r2"].prefix, d["r2"].value) == ("R2", "R2", pytest.approx(100.0))
    assert d["r1"].b == QPointF(300, 0)
    assert (d["r2"].b.x(), d["r2"].b.y()) == pytest.approx((0.0, -100.0))
    d["r2"].apply(500.0)            # no swap / renaming — R2 stays the ry axis
    assert e._ry == pytest.approx(500.0) and _by_key(e)["r2"].value == pytest.approx(500.0)


@pytest.mark.parametrize("inscribed", [True, False])
def test_polygon_defining_radius_radial(qapp, inscribed):
    p = RegularPolygonItem(QPointF(0, 0), 6, 100.0, 0.0, inscribed)
    s = _by_key(p)["radius"]
    assert s.prefix == "R" and s.value == pytest.approx(100.0)
    assert (s.b.x(), s.b.y()) == pytest.approx((100.0, 0.0))
    if inscribed:   # radial ends on a vertex
        assert any(math.hypot(v.x() - 100, v.y()) < 1e-6 for v in p.vertices())
    s.apply(50.0)
    assert p._radius_mm == pytest.approx(50.0) and p._sides == 6
