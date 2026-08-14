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


def test_find_grip_hit_returns_bubble_grip(scene_with_gridline):
    ms, view, gl = scene_with_gridline
    gl.setSelected(True)
    hit = ms._find_grip_hit(QPointF(gl.bubble1.pos()))
    assert hit == (gl, 2)


def test_find_grip_hit_skips_hidden_bubble_grip(scene_with_gridline):
    ms, view, gl = scene_with_gridline
    gl.setSelected(True)
    bubble_pt = QPointF(gl.bubble1.pos())
    gl.bubble1.setVisible(False)
    hit = ms._find_grip_hit(bubble_pt)
    assert hit is None or hit[1] != 2


def test_bubble_grip_multiselect_same_delta(qapp):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    view = QGraphicsView(ms); view.resize(600, 600); view.resetTransform()
    a = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    b = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="2")
    for g in (a, b):
        ms.addItem(g); ms._gridlines.append(g); g.setSelected(True)
    a0, b0 = a.bubble1_offset(), b.bubble1_offset()
    ms._grip_item = a
    ms._grip_index = 2
    ms._grip_dragging = True
    # Drag a's bubble1 grip outward by 700 (origin at y=0, outward is −y)
    ms._drag_grip_to(QPointF(0, -(a0 + 700)))
    view.hide()
    assert math.isclose(a.bubble1_offset(), a0 + 700, abs_tol=1e-3)
    assert math.isclose(b.bubble1_offset(), b0 + 700, abs_tol=1e-3)


def test_bubble_grip_multiselect_skips_locked(qapp):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    view = QGraphicsView(ms); view.resize(600, 600); view.resetTransform()
    a = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    b = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="2")
    b._locked = True
    for g in (a, b):
        ms.addItem(g); ms._gridlines.append(g); g.setSelected(True)
    b0 = b.bubble1_offset()
    ms._grip_item = a; ms._grip_index = 2; ms._grip_dragging = True
    ms._drag_grip_to(QPointF(0, -3000))
    view.hide()
    assert math.isclose(b.bubble1_offset(), b0, abs_tol=1e-6)  # locked unchanged
