import math
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.construction_geometry import EllipseItem


def _make(rx=40.0, ry=20.0, rot=0.0):
    return EllipseItem(QPointF(100, 200), rx, ry, rot)


def test_construct_stores_params():
    e = _make(40, 20, 30)
    assert e._center == QPointF(100, 200)
    assert e._rx == 40.0 and e._ry == 20.0
    assert e._rotation_deg == 30.0


def test_grips_center_plus_four_axis_endpoints():
    e = _make(40, 20, 0.0)
    g = e.grip_points()
    assert len(g) == 5
    assert g[0] == QPointF(100, 200)
    assert g[1].x() == pytest.approx(140) and g[1].y() == pytest.approx(200)
    assert g[2].x() == pytest.approx(60)  and g[2].y() == pytest.approx(200)
    assert g[3].x() == pytest.approx(100) and g[3].y() == pytest.approx(180)
    assert g[4].x() == pytest.approx(100) and g[4].y() == pytest.approx(220)


def test_major_grip_sets_rx_and_rotation_yup():
    e = _make(40, 20, 0.0)
    ang = math.radians(30)
    target = QPointF(100 + 50 * math.cos(ang), 200 - 50 * math.sin(ang))
    e.apply_grip(1, target)
    assert e._rx == pytest.approx(50, abs=1e-6)
    assert e._rotation_deg == pytest.approx(30, abs=1e-6)
    g1 = e.grip_points()[1]
    assert g1.x() == pytest.approx(target.x(), abs=1e-6)
    assert g1.y() == pytest.approx(target.y(), abs=1e-6)


def test_minor_grip_sets_ry_only():
    e = _make(40, 20, 30.0)
    e.apply_grip(3, QPointF(100, 150))
    assert e._ry == pytest.approx(50, abs=1e-6)
    assert e._rotation_deg == pytest.approx(30, abs=1e-6)


def test_subepsilon_axis_clamped():
    e = _make(40, 20, 0.0)
    e.apply_grip(1, QPointF(100.1, 200))
    assert e._rx >= 0.5


def test_is_fillable_and_closed_path():
    e = _make()
    assert e.is_fillable() is True
    assert e.get_closed_path() is not None


def test_to_from_dict_roundtrip():
    e = _make(40, 20, 30.0)
    e.level = "Level 2"
    d = e.to_dict()
    assert d["type"] == "draw_ellipse"
    e2 = EllipseItem.from_dict(d)
    assert e2._center == e._center
    assert e2._rx == e._rx and e2._ry == e._ry
    assert e2._rotation_deg == e._rotation_deg
    assert e2.level == "Level 2"


def test_translate_moves_center():
    e = _make()
    e.translate(10, -5)
    assert e._center == QPointF(110, 195)


def test_manip_rotate_advances_rotation():
    e = _make(40, 20, 0.0)
    e.manip_rotate(90.0, QPointF(100, 200))
    assert e._rotation_deg == pytest.approx(90.0)
