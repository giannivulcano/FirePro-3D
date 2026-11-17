"""SB6 AC5 / D4 -- dragging a tag changes only its offset; the host is unchanged;
a tag moved with its host keeps its offset; the Rotate tool leaves a lone tag.
Ground truth: the raw wall (a horizontal wall through the origin: u = x, v = y)."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from tests._sb6_helpers import U, V, add_wall, expected_pose, place_tag, pose_of
from tests._modify_tools_helpers import add_primitive, grips
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


def _scale_by_two(scene, view):
    scene._modify_ctl.start("scale")
    click(view, QPointF(0.0, 0.0))                            # the base point
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Factor").setText("2")
    scene.dynamic_input._accept()


def test_d4_scale_tool_skips_a_tag_and_scales_the_rest(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = add_wall(scene)
        line, _ = add_primitive(scene, "line")                # (0,0)-(100,0), a non-tag item
        scene.push_undo_state()
        tag = place_tag(scene, w)
        size0 = tag.sceneBoundingRect().size()
        scene.clearSelection()
        tag.setSelected(True)
        line.setSelected(True)
        _scale_by_two(scene, view)
        assert grips(line) == [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]   # the non-tag DID scale
        assert tag._pose_scale == 1.0              # [RED only with BOTH _scalable and the manip_scale_about guard reverted]
        assert pose_of(tag) == pytest.approx(expected_pose(w), abs=1e-6)
        s1 = tag.sceneBoundingRect().size()
        assert (s1.width(), s1.height()) == pytest.approx((size0.width(), size0.height()), abs=1e-6)
    finally:
        close_view(view, scene)


def test_d4_scale_tool_on_a_lone_tag_pushes_no_undo_step(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = add_wall(scene)
        scene.push_undo_state()
        tag = place_tag(scene, w)
        scene.clearSelection()
        tag.setSelected(True)
        n0, p0 = len(scene._undo_stack), scene._undo_pos
        if scene._modify_ctl.start("scale"):
            click(view, QPointF(0.0, 0.0))
            if scene.begin_dynamic_input():
                scene.dynamic_input.editor("Factor").setText("2")
                scene.dynamic_input._accept()
        assert tag._pose_scale == 1.0
        assert (len(scene._undo_stack), scene._undo_pos) == (n0, p0)        # [RED]
    finally:
        close_view(view, scene)


def test_d4_direct_manip_scale_about_leaves_a_tag_unscaled(qapp, real_system_library):
    """Defence in depth for direct callers (e.g. explode) that bypass the Scale tool's filter."""
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = add_wall(scene)
        scene.push_undo_state()
        tag = place_tag(scene, w)
        pose0, size0 = pose_of(tag), tag.sceneBoundingRect().size()
        tag.manip_scale_about(QPointF(0.0, 0.0), 2.0)
        assert tag._pose_scale == 1.0                                       # [RED]
        assert pose_of(tag) == pytest.approx(pose0, abs=1e-6)
        s1 = tag.sceneBoundingRect().size()
        assert (s1.width(), s1.height()) == pytest.approx((size0.width(), size0.height()), abs=1e-6)
    finally:
        close_view(view, scene)
