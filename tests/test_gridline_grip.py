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
