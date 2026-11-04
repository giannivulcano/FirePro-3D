"""Leader grips, pinned tip, rigid carry, paper undo (design D5, D7)."""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt

from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextAnnotationData, TextItem

LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 6.0, "tip_x": 80.0, "tip_y": 60.0,
          "end": "none", "weight": ""}


def _text():
    return TextItem(TextAnnotationData(text="n", wrap_width_mm=30.0, box_height_mm=10.0,
                                       height_mm=3.0, leader=dict(LEADER)))


def _tip(item):
    return item.data.leader["tip_x"], item.data.leader["tip_y"]


def _tip_in_box(item):
    """The tip in the item's own box frame, the observable that a rigid
    transform must leave alone."""
    from firepro3d.text_leader import box_frame_points
    _a, _k, t = box_frame_points(item)
    return t.x(), t.y()


def test_leader_grips_follow_the_move_grip_only_while_on(qapp):
    item = _text()
    assert len(item.grip_points()) == 11 and TextItem.MOVE_GRIP_INDEX == 8
    item.data.leader = None
    assert len(item.grip_points()) == 9


def test_tip_grip_moves_the_tip_and_leaves_the_shoulder(qapp):
    item = _text()
    knee = item.grip_points()[9]
    item.apply_grip(10, QPointF(90.0, 70.0))
    assert _tip(item) == (90.0, 70.0)
    assert item.grip_points()[9] == knee


def test_knee_grip_keeps_the_tip(qapp):
    item = _text()
    item.apply_grip(9, QPointF(45.0, 2.0))
    assert _tip(item) == (80.0, 60.0)
    assert item.data.leader["edge"] == "R"


def test_moving_the_box_pins_the_tip(qapp):
    item = _text()
    item.manip_translate(10.0, 5.0)
    assert _tip(item) == (80.0, 60.0)


def test_centre_grip_move_pins_the_tip(qapp):
    item = _text()
    c = item.grip_points()[8]
    item.apply_grip(8, QPointF(c.x() + 7.0, c.y() + 4.0))
    assert _tip(item) == (80.0, 60.0)


def test_a_move_through_the_scene_pins_the_tip(qapp):
    sc = Model_Space()
    item = _text()
    sc.addItem(item)
    sc._selected_items = [item]
    sc.move_items(QPointF(10.0, 5.0))
    assert item.pos().x() == pytest.approx(10.0)
    assert _tip(item) == (80.0, 60.0)


def test_rigid_shift_carries_the_tip(qapp):
    item = _text()
    item.shift_leader(10.0, 5.0)
    assert _tip(item) == (90.0, 65.0)


def test_paste_offset_is_rigid_and_carries_the_tip(qapp):
    sc = Model_Space()
    rec = _text().to_dict()
    new = sc.paste_items(QPointF(10.0, 5.0), data=[rec])
    t = new[0]
    assert t.pos().x() == pytest.approx(10.0)
    assert _tip(t) == pytest.approx((90.0, 65.0))


@pytest.mark.parametrize("angle,pivot", [(90.0, (0.0, 0.0)), (-90.0, (0.0, 0.0)),
                                         (37.0, (15.0, 20.0)), (180.0, (50.0, 40.0))])
def test_rotate_carries_the_tip_rigidly(qapp, angle, pivot):
    """The tip keeps its place in the box frame, whatever way manip_rotate turns
    the box (the observable that fixes the sign)."""
    item = _text()
    before = _tip_in_box(item)
    item.manip_rotate(angle, QPointF(*pivot))
    assert _tip_in_box(item) == pytest.approx(before, abs=1e-6)


def test_rotate_turns_the_tip_through_the_same_angle_as_the_box(qapp):
    item = _text()
    c0 = item.grip_points()[8]
    item.manip_rotate(90.0, QPointF(0.0, 0.0))
    c1 = item.grip_points()[8]
    ang = math.atan2(c1.y(), c1.x()) - math.atan2(c0.y(), c0.x())
    tx, ty = _tip(item)
    tang = math.atan2(ty, tx) - math.atan2(60.0, 80.0)
    assert math.cos(ang) == pytest.approx(math.cos(tang), abs=1e-6)
    assert math.sin(ang) == pytest.approx(math.sin(tang), abs=1e-6)
    assert math.hypot(tx, ty) == pytest.approx(100.0, abs=1e-6)


def test_scale_carries_the_tip_about_the_anchor(qapp):
    item = _text()
    b = item.manip_bounds()
    w0 = b.width()
    item.manip_scale(2.0, 1.0, QPointF(b.x(), b.y() + b.height() / 2))   # ML anchor
    assert item.manip_bounds().width() == pytest.approx(w0 * 2.0, abs=1e-3)
    # x doubles about the box's left edge (x = 0); fy == 1 leaves y alone
    assert _tip(item)[0] == pytest.approx(160.0, abs=1e-3)
    assert _tip(item)[1] == pytest.approx(60.0, abs=1e-3)


# ── paper: real manipulator path and undo ───────────────────────────────────

def _paper_text(qapp):
    from firepro3d.paper_space import PaperScene, Sheet
    from tests.test_paper_annotations import _stub_resolver
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    data = TextAnnotationData(text="word " * 4, x=20.0, y=20.0, wrap_width_mm=40.0,
                              box_height_mm=12.0, height_mm=3.0,
                              leader={"edge": "R", "t": 0.5, "shoulder_mm": 6.0,
                                      "tip_x": 90.0, "tip_y": 60.0, "end": "none",
                                      "weight": ""})
    item = TextItem(data)
    scene.addItem(item)
    item.setPos(20.0, 20.0)
    item.setSelected(True)
    return scene, item, data


def test_paper_box_native_path_offers_the_knee_and_tip_grips(qapp):
    scene, item, _d = _paper_text(qapp)
    assert item.is_device_independent()
    handles = item.manip_box_extra_handles()
    assert [h.index for h in handles] == [8, 9, 10]
    item.data.leader = None
    assert [h.index for h in item.manip_box_extra_handles()] == [8]


def _drag_handle(scene, item, index, target):
    """Drag grip *index* of *item* to *target* through the real manipulator
    (paper box-native extra handle): press, move, release."""
    from PyQt6.QtWidgets import QGraphicsView
    view = QGraphicsView(scene)
    manip = scene._manipulator
    manip.rebake()
    handle = next(h for h in item.manip_box_extra_handles() if h.index == index)
    start = item.grip_points()[index]
    manip._begin_handle(handle, start, QPointF(0, 0))
    manip._moved = True
    handle.on_drag(manip, target, Qt.KeyboardModifier.NoModifier)
    handle.on_release(manip, target, Qt.KeyboardModifier.NoModifier)
    return view


def test_paper_tip_grip_drag_is_one_undo_step_and_undo_restores_it(qapp):
    scene, item, data = _paper_text(qapp)
    before = dict(data.leader)
    idx0 = scene.undo_stack.index()
    _v = _drag_handle(scene, item, TextItem.LEADER_TIP_GRIP, QPointF(100.0, 70.0))
    assert _tip(item) == pytest.approx((100.0, 70.0), abs=1.0)
    assert _tip(item) != (before["tip_x"], before["tip_y"])
    assert scene.undo_stack.index() == idx0 + 1
    scene.undo_stack.undo()
    assert data.leader == before
    scene.undo_stack.redo()
    assert data.leader["tip_x"] != before["tip_x"]


def test_paper_knee_grip_drag_undoes(qapp):
    scene, item, data = _paper_text(qapp)
    before = dict(data.leader)
    idx0 = scene.undo_stack.index()
    _v = _drag_handle(scene, item, TextItem.LEADER_KNEE_GRIP, QPointF(70.0, 28.0))
    assert (data.leader["shoulder_mm"], data.leader["t"]) != (before["shoulder_mm"], before["t"])
    assert scene.undo_stack.index() == idx0 + 1
    scene.undo_stack.undo()
    assert data.leader == before


def test_paper_text_box_geom_snapshot_carries_a_copy_of_the_leader(qapp):
    from firepro3d.paper_commands import ResizeTextBoxCommand
    from firepro3d.paper_space import PaperScene
    scene, item, data = _paper_text(qapp)
    old = PaperScene._text_box_geom(data)
    item.apply_grip(TextItem.LEADER_TIP_GRIP, QPointF(100.0, 70.0))
    new = PaperScene._text_box_geom(data)
    assert old[6]["tip_x"] == 90.0 and new[6]["tip_x"] == 100.0
    scene.undo_stack.push(ResizeTextBoxCommand(scene, data, old, new))
    scene.undo_stack.undo()
    assert data.leader["tip_x"] == 90.0
    scene.undo_stack.redo()
    assert data.leader["tip_x"] == 100.0


# ── explode ─────────────────────────────────────────────────────────────────

def test_explode_poses_the_tip_like_a_placement_draws_it(qapp):
    from firepro3d.block_definition import BlockDefinition
    from tests.test_block_explode import _proj_and_editor
    rec = TextItem(TextAnnotationData(
        text="AB", x=-20.0, y=10.0, wrap_width_mm=30.0, box_height_mm=10.0, height_mm=3.0,
        color="#ffffff", leader=dict(LEADER, tip_x=60.0, tip_y=-30.0))).to_dict()
    b = BlockDefinition.new(name="B", library="L", series="S", origin=(10.0, 5.0),
                            primitives=[rec])
    proj, w, es = _proj_and_editor(b)
    try:
        inst = es.place_block_instance(b.id, (20.0, 30.0), rotation=30.0)
        want = inst.full_pose_transform().map(QPointF(60.0 - 10.0, -30.0 - 5.0))
        inst.setSelected(True)
        new = es.explode_selected_blocks()
        t = [i for i in new if isinstance(i, TextItem)][0]
        assert _tip(t) == pytest.approx((want.x(), want.y()), abs=1e-6)
    finally:
        es.cleanup()


def test_block_editor_whole_definition_shift_carries_the_tip(qapp):
    from firepro3d.block_definition import BlockDefinition
    from tests.test_block_explode import _proj_and_editor
    rec = _text().to_dict()
    b = BlockDefinition.new(name="B", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[rec])
    proj, w, es = _proj_and_editor(b)
    try:
        w.seed_from_definition(b)
        t = next(i for i in w.gather_primitives() if isinstance(i, TextItem))
        tip0, x0 = _tip(t), t.pos().x()
        w._translate_all(10.0, 5.0)
        assert t.pos().x() == pytest.approx(x0 + 10.0)
        assert _tip(t) == pytest.approx((tip0[0] + 10.0, tip0[1] + 5.0))
    finally:
        es.cleanup()
