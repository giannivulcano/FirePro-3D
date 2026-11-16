"""SB6 AC5 / D4 -- dragging a tag changes only its offset; the host is unchanged;
a tag moved with its host keeps its offset; the Rotate tool leaves a lone tag.
Ground truth: the raw wall (a horizontal wall through the origin: u = x, v = y)."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from tests._sb6_helpers import U, V, add_wall, expected_pose, place_tag, pose_of
from tests._snap_polish_helpers import click, close_view, make_view, move


def test_ac5_manipulator_drag_changes_only_the_offset(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = add_wall(scene)
        scene.push_undo_state()
        tag = place_tag(scene, w)
        p1, p2 = QPointF(w.pt1), QPointF(w.pt2)
        x0, y0 = tag.block_pos()
        scene.clearSelection()
        tag.setSelected(True)
        QApplication.processEvents()
        m = scene._live_manip()
        start, end = QPointF(x0, y0), QPointF(x0 + 400.0, y0 - 300.0)
        m._begin("move", start, start)
        m._update(end, Qt.KeyboardModifier.NoModifier, end)
        m._finish(end, Qt.KeyboardModifier.NoModifier)
        scene.push_undo_state()                              # a further committed step re-poses
        assert (w.pt1, w.pt2) == (p1, p2)                     # host untouched
        x1, y1 = tag.block_pos()
        assert (x1, y1) != pytest.approx((x0, y0))            # it moved and stayed   [RED]
        assert tag.tag["offset"] == pytest.approx([x1, y1], abs=1e-6)   # raw: a = 0, anchor (0, 0)
    finally:
        close_view(view, scene)


def test_ac5_tag_moved_with_its_host_keeps_the_offset(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = add_wall(scene)
        scene.push_undo_state()
        tag = place_tag(scene, w)
        scene.clearSelection()
        tag.setSelected(True)
        w.setSelected(True)
        scene._modify_ctl.start("move")
        scene._selected_items = [tag, w]                      # the tag bakes before its host
        click(view, QPointF(0.0, 0.0))
        move(view, QPointF(300.0, 700.0))
        click(view, QPointF(300.0, 700.0))
        assert tag.tag["offset"] == pytest.approx([U, V])     # [RED: moves_with_host]
        assert pose_of(tag) == pytest.approx(expected_pose(w), abs=1e-6)
    finally:
        close_view(view, scene)


def test_d4_rotate_tool_leaves_a_lone_tag(qapp, real_system_library):
    from firepro3d.selection_manipulator import item_capabilities
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = add_wall(scene)
        scene.push_undo_state()
        tag = place_tag(scene, w)
        assert item_capabilities(tag) == {"translate"}
        scene.clearSelection()
        tag.setSelected(True)
        p0 = scene._undo_pos
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0.0, 0.0))
        if scene.begin_dynamic_input():
            scene.dynamic_input.editor("Angle").setText("30")
            scene.dynamic_input._accept()
        assert scene._undo_pos == p0                          # "Nothing to rotate": no step   [RED]
        assert tag.block_rotation() == 0.0
    finally:
        close_view(view, scene)
