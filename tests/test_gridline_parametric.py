import math
from PyQt6.QtCore import QPointF
from firepro3d.gridline import GridlineItem
from firepro3d.constants import GRIDLINE_BUBBLE_OFFSET_MM


def test_params_derived_from_two_points(qapp):
    gl = GridlineItem(QPointF(100.0, 200.0), QPointF(100.0, 1200.0), label="A")
    assert gl.origin() == QPointF(100.0, 200.0)
    assert math.isclose(gl.length(), 1000.0, abs_tol=1e-6)
    assert math.isclose(gl.angle_deg() % 360, 270.0, abs_tol=1e-6)
    assert gl.bubble1_offset() == GRIDLINE_BUBBLE_OFFSET_MM


def test_rebuild_keeps_line_in_sync(qapp):
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(1000.0, 0.0), label="1")
    gl.set_length(500.0)
    ln = gl.line()
    assert math.isclose(ln.p2().x(), 500.0, abs_tol=1e-6)
    assert math.isclose(ln.p1().x(), 0.0, abs_tol=1e-6)


def test_set_origin_translates_whole_line(qapp):
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(1000.0, 0.0), label="1")
    gl.set_origin_x(300.0)
    ln = gl.line()
    assert math.isclose(ln.p1().x(), 300.0, abs_tol=1e-6)
    assert math.isclose(ln.p2().x(), 1300.0, abs_tol=1e-6)
    assert math.isclose(gl.length(), 1000.0, abs_tol=1e-6)


def test_set_angle_rotates_about_origin(qapp):
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(1000.0, 0.0), label="1")
    gl.set_angle_deg(90.0)
    ln = gl.line()
    assert math.isclose(ln.p1().x(), 0.0, abs_tol=1e-6)
    assert math.isclose(ln.p1().y(), 0.0, abs_tol=1e-6)
    assert math.isclose(ln.p2().x(), 0.0, abs_tol=1e-4)
    assert math.isclose(ln.p2().y(), -1000.0, abs_tol=1e-4)
