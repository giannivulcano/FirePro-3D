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


def test_no_pulltab_child_items_after_migration(scene_with_gridline):
    # U3: the legacy _PullTabGrip children are removed — grips are manipulator-
    # owned. Lock/bubble-visibility gating now lives in grip_hittable (below).
    ms, view, gl = scene_with_gridline
    gl.setSelected(True)
    assert not hasattr(gl, "_bgrip1")
    assert not hasattr(gl, "_grip1")


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


# Bubble-grip multiselect parallel-delta and locked-skip are covered on the
# Handle path by test_manip_griphandle_gridline_parity.py
# (test_bubble_grip_apply_matches_legacy_and_propagates,
#  test_multiselect_endpoint_drag_moves_all_selected,
#  test_propagate_skips_non_gridlines_and_locked_and_self).
