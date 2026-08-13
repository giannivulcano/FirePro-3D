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


def test_origin_y_displayed_up_positive(qapp):
    # Scene Y is Qt down-positive; the panel shows up-positive.
    gl = GridlineItem(QPointF(0, 500), QPointF(0, 1500), label="1")
    props = gl.get_properties()
    assert props["Origin Y"]["value_mm"] == -500.0
    assert props["End Y"]["value"] == f"{-1500.0:.1f}"


def test_set_origin_y_up_positive_input(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000), label="1")
    gl.set_property("Origin Y", 300.0)          # user types up-positive
    assert gl.origin().y() == -300.0            # stored scene Y-down


def test_no_negative_zero_on_origin_y(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")  # origin (0,0)
    v = gl.get_properties()["Origin Y"]["value_mm"]
    assert v == 0.0 and math.copysign(1.0, v) == 1.0   # +0.0, never "-0"


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
