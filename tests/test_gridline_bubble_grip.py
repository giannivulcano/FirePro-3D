import math
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsView
from firepro3d.model_space import Model_Space
from firepro3d.gridline import GridlineItem


@pytest.fixture
def scene_with_gridline(qapp):
    ms = Model_Space()
    view = QGraphicsView(ms); view.resize(600, 600); view.resetTransform()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    ms.addItem(gl); ms._gridlines.append(gl)
    yield ms, view, gl
    view.hide()


def test_bubble_grips_visible_on_select(scene_with_gridline):
    ms, view, gl = scene_with_gridline
    gl.setSelected(True)
    assert gl._bgrip1.isVisible()
    assert gl._bgrip2.isVisible()


def test_bubble_grips_hidden_when_locked(scene_with_gridline):
    ms, view, gl = scene_with_gridline
    gl._locked = True
    gl.setSelected(True)
    assert not gl._bgrip1.isVisible()


def test_grip_hittable_false_for_hidden_bubble(scene_with_gridline):
    ms, view, gl = scene_with_gridline
    gl.setSelected(True)
    gl.bubble1.setVisible(False)
    assert gl.grip_hittable(0) is True
    assert gl.grip_hittable(2) is False
    assert gl.grip_hittable(3) is True


def test_grip_hittable_false_when_locked(scene_with_gridline):
    ms, view, gl = scene_with_gridline
    gl._locked = True
    assert gl.grip_hittable(0) is False
    assert gl.grip_hittable(2) is False
