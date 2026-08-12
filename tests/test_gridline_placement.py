import math
from PyQt6.QtCore import QPointF, Qt
from types import SimpleNamespace
from firepro3d.model_space import Model_Space
from firepro3d.gridline import GridlineItem


def _place(scene, p1, p2, ctrl=False):
    mods = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    ev = SimpleNamespace(modifiers=lambda: mods)
    scene.set_mode("draw_gridline")
    scene._press_draw_line(ev, p1, p1, None, None, None)
    scene._press_draw_line(ev, p2, p2, None, None, None)


def test_draw_gridline_creates_gridline_not_line(qapp):
    scene = Model_Space()
    _place(scene, QPointF(0, 0), QPointF(0, 1000))
    assert len(scene._gridlines) == 1
    assert isinstance(scene._gridlines[0], GridlineItem)
    assert len(scene._draw_lines) == 0
    assert math.isclose(scene._gridlines[0].length(), 1000.0, abs_tol=1e-6)


def test_draw_gridline_ctrl_constrains_angle(qapp):
    scene = Model_Space()
    _place(scene, QPointF(0, 0), QPointF(1000, 30), ctrl=True)
    gl = scene._gridlines[0]
    assert abs(gl.line().p2().y()) < 1.0
