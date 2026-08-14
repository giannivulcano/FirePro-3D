import math
from PyQt6.QtCore import QPointF
from firepro3d.gridline import GridlineItem


def test_grip_far_end_extends_origin_fixed(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    gl.apply_grip(1, QPointF(1500, 80))  # perpendicular 80 is discarded
    ln = gl.line()
    assert math.isclose(ln.p1().x(), 0.0, abs_tol=1e-6)   # origin fixed
    assert math.isclose(ln.p1().y(), 0.0, abs_tol=1e-6)
    assert math.isclose(ln.p2().x(), 1500.0, abs_tol=1e-6)
    assert math.isclose(ln.p2().y(), 0.0, abs_tol=1e-6)   # stayed on the line


def test_grip_origin_end_moves_far_fixed(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    gl.apply_grip(0, QPointF(200, 50))
    ln = gl.line()
    assert math.isclose(ln.p2().x(), 1000.0, abs_tol=1e-6)  # far end fixed
    assert math.isclose(ln.p1().x(), 200.0, abs_tol=1e-6)
    assert math.isclose(gl.length(), 800.0, abs_tol=1e-6)


def test_grip_locked_noop(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    gl._locked = True
    gl.apply_grip(1, QPointF(1500, 0))
    assert math.isclose(gl.length(), 1000.0, abs_tol=1e-6)


def test_grip_points_includes_bubble_centres(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    gp = gl.grip_points()
    assert len(gp) == 4  # origin, far, bubble1, bubble2


def test_bubble1_grip_sets_offset_along_axis(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")  # vertical, dir (0,1)
    # bubble1 stands off from origin outward (−û = (0,-1)). Drag to y=-1500.
    gl.apply_grip(2, QPointF(40, -1500))  # x=40 perpendicular is discarded
    assert math.isclose(gl.bubble1_offset(), 1500.0, abs_tol=1e-6)


def test_bubble2_grip_sets_offset_along_axis(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    # bubble2 stands off from far (0,5000) outward (+û = (0,1)). Drag to y=6200.
    gl.apply_grip(3, QPointF(-30, 6200))
    assert math.isclose(gl.bubble2_offset(), 1200.0, abs_tol=1e-6)


def test_bubble_grip_floors_at_zero(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    gl.apply_grip(2, QPointF(0, 800))  # inward past origin → negative → floored
    assert math.isclose(gl.bubble1_offset(), 0.0, abs_tol=1e-6)


def test_bubble_grip_locked_noop(qapp):
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    before = gl.bubble1_offset()
    gl._locked = True
    gl.apply_grip(2, QPointF(0, -1500))
    assert math.isclose(gl.bubble1_offset(), before, abs_tol=1e-6)
