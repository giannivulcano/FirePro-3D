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
