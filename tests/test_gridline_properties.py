import math
from PyQt6.QtCore import QPointF
from firepro3d.gridline import GridlineItem


def test_get_properties_exposes_geometry(qapp):
    gl = GridlineItem(QPointF(100, 200), QPointF(100, 1200), label="A")
    props = gl.get_properties()
    assert props["Origin X"]["type"] == "dimension"
    assert props["Length"]["type"] == "dimension"
    assert props["Angle"]["type"] == "string"
    assert props["Bubble 1 Offset"]["type"] == "dimension"
    assert "value_mm" in props["Origin X"]


def test_set_origin_x_translates(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    gl.set_property("Origin X", 300.0)
    assert math.isclose(gl.line().p1().x(), 300.0, abs_tol=1e-6)
    assert math.isclose(gl.line().p2().x(), 1300.0, abs_tol=1e-6)


def test_set_angle_via_property(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    gl.set_property("Angle", "90")
    assert math.isclose(gl.angle_deg() % 360, 90.0, abs_tol=1e-6)


def test_set_angle_invalid_reverts(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    gl.set_property("Angle", "not-a-number")
    assert math.isclose(gl.angle_deg() % 360, 0.0, abs_tol=1e-6)


def test_panel_edit_reaches_geometry(qapp):
    from firepro3d.property_manager import PropertyManager
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    pm = PropertyManager()
    pm.show_properties(gl)
    pm._apply_property("Length", 500.0)
    assert math.isclose(gl.length(), 500.0, abs_tol=1e-6)
