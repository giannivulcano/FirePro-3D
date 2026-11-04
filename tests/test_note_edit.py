"""Task 10: the Note edit overlay, grips, leader rows and the rigid carry (D5, D7, D13)."""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt

from firepro3d.constants import MIN_NOTE_BOX_MM, TEXT_LEADER_END_ID
from firepro3d.manip_handle import GripHandle
from firepro3d.model_space import NOTE_PASTE_REFUSED, Model_Space
from firepro3d.system_blocks import NOTE_BLOCK_ID
from firepro3d.text_item import TextItem, editing_text_item
from tests._note_helpers import dbl

PLAN = "plan:Plan: Level 1"
K = 100.0                      # the default 1:100 drawing scale: scene mm per printed mm
LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 6.0, "tip_x": 1400.0, "tip_y": 300.0,
          "end": "none", "weight": ""}
BOX = (20.0, 8.0)              # printed mm -> a 2000 x 800 scene box


def _note(scene, pos=(-1000.0, -400.0), leader=None, text="old"):
    scene.active_view_key = PLAN
    scene.ensure_system_block(NOTE_BLOCK_ID)
    note = {"view": PLAN, "wrap_width_mm": BOX[0], "box_height_mm": BOX[1]}
    if leader:
        note["leader"] = dict(leader)
    inst = scene.place_block_instance(NOTE_BLOCK_ID, pos, note=note)
    inst.set_attributes({"Text": text})
    scene.push_undo_state()                   # the baseline an undo returns to
    return inst


@pytest.fixture
def placed_note(shown_model_view, real_system_library):
    view, scene = shown_model_view
    return scene, _note(scene)


@pytest.fixture
def placed_note_with_leader(shown_model_view, real_system_library):
    view, scene = shown_model_view
    return scene, _note(scene, leader=LEADER)


def _tip(inst):
    r = inst.note["leader"]
    return r["tip_x"], r["tip_y"]


def _drawn_tip(inst):
    """The leader's last point as the ops draw it, through the real pose."""
    from tests.test_note_instance import drawn_tip_scene
    p = drawn_tip_scene(inst)
    return p.x(), p.y()


# -- the overlay --------------------------------------------------------------

def test_edit_commit_writes_the_attribute_and_leaves_no_loose_text(placed_note):
    ms, inst = placed_note
    ms._note_ctl.begin(inst)
    ov = ms._note_ctl.overlay
    assert editing_text_item(ms) is ov and not inst.isVisible()
    assert ms._texts == []                           # never a loose text
    ov.setPlainText("Hold at 3 m")
    ms._text_edit_ctl.commit()
    assert inst.attributes["Text"] == "Hold at 3 m"
    assert not ms._texts and inst.isVisible()
    assert ms._note_ctl.overlay is None and ov.scene() is None


def test_commit_is_one_undo_step_and_undo_restores_the_text(placed_note):
    ms, inst = placed_note
    depth = len(ms._undo_stack)
    ms._note_ctl.begin(inst)
    ms._note_ctl.overlay.setPlainText("new words")
    ms._text_edit_ctl.commit()
    assert len(ms._undo_stack) == depth + 1
    ms.undo()
    again = [i for i in ms._block_instances if i.note]
    assert [i.attributes["Text"] for i in again] == ["old"]


def test_an_edit_that_changes_nothing_pushes_no_step(placed_note):
    ms, inst = placed_note
    depth = len(ms._undo_stack)
    ms._note_ctl.begin(inst)
    ms._text_edit_ctl.commit()
    assert len(ms._undo_stack) == depth and inst.attributes["Text"] == "old"


def test_undo_snapshot_never_holds_the_overlay(placed_note):
    """A push while the edit is live (any other action) must not see the overlay:
    not in ``texts``, and the host keeps the old text."""
    ms, inst = placed_note
    ms._note_ctl.begin(inst)
    ms._note_ctl.overlay.setPlainText("typed, not yet committed")
    ms.push_undo_state()
    snap = ms._undo_stack[-1]
    assert snap["texts"] == []
    assert [b["attributes"]["Text"] for b in snap["blocks"]] == ["old"]
    ms._text_edit_ctl.commit()


def test_a_file_save_while_an_edit_is_live_writes_no_overlay(placed_note, tmp_path):
    ms, inst = placed_note
    ms._note_ctl.begin(inst)
    ms._note_ctl.overlay.setPlainText("typed, not yet committed")
    path = str(tmp_path / "live.FPD")
    assert ms.save_to_file(path)
    import json
    with open(path, encoding="utf-8") as fh:
        saved = json.load(fh)
    assert saved.get("texts", []) == []              # the file itself holds no overlay
    back = Model_Space()
    back.load_from_file(path)
    assert back._texts == []
    notes = [i for i in back._block_instances if i.note]
    assert len(notes) == 1 and notes[0].attributes["Text"] == "old"
    ms._text_edit_ctl.commit()


def test_empty_new_note_is_discarded_without_a_step(placed_note):
    ms, inst = placed_note
    inst.set_attributes({"Text": ""})
    depth = len(ms._undo_stack)
    ms._note_ctl.begin(inst, is_new=True)
    ms._text_edit_ctl.commit()
    assert inst not in ms._block_instances and inst.scene() is None
    assert len(ms._undo_stack) == depth


def test_emptied_existing_note_is_deleted_in_one_step(placed_note):
    ms, inst = placed_note
    depth = len(ms._undo_stack)
    ms._note_ctl.begin(inst)
    ms._note_ctl.overlay.setPlainText("   ")
    ms._text_edit_ctl.commit()
    assert inst not in ms._block_instances
    assert len(ms._undo_stack) == depth + 1
    ms.undo()
    assert [i.attributes["Text"] for i in ms._block_instances if i.note] == ["old"]


def test_double_click_opens_the_editor_through_the_real_event_path(
        shown_model_view, real_system_library):
    view, ms = shown_model_view
    inst = _note(ms)
    ms.set_mode("select")
    dbl(view, inst.manip_bounds().center())
    assert ms._note_ctl.overlay is not None and ms.editing_note() is inst
    assert editing_text_item(ms) is ms._note_ctl.overlay
    ms._text_edit_ctl.commit()


@pytest.mark.parametrize("mirrored", [False, True], ids=["plain", "mirrored"])
@pytest.mark.parametrize("rotation", [0.0, 90.0, 30.0])
def test_the_overlay_box_lands_on_the_note_box(shown_model_view, real_system_library,
                                               rotation, mirrored):
    view, ms = shown_model_view
    inst = _note(ms)
    inst.set_block_rotation(rotation)
    inst.set_block_mirrored(mirrored)
    want = inst.note_box_scene()
    ms._note_ctl.begin(inst)
    ov = ms._note_ctl.overlay
    got = ov.mapRectToScene(ov._box_rect_local())
    assert (got.x(), got.y(), got.width(), got.height()) == pytest.approx(
        (want.x(), want.y(), want.width(), want.height()), abs=1.0)
    ms._text_edit_ctl.commit()


@pytest.mark.parametrize("mirrored", [False, True], ids=["plain", "mirrored"])
@pytest.mark.parametrize("rotation", [0.0, 90.0, 30.0])
@pytest.mark.parametrize("edge,t", [("R", 0.5), ("L", 0.3), ("T", 0.25), ("B", 0.8)])
def test_the_overlay_leader_leaves_the_same_side_as_the_notes(
        shown_model_view, real_system_library, rotation, mirrored, edge, t):
    """The note's shoulder, knee and attach as the ops draw them (variant mirror,
    pose) against the overlay's own leader: same points in the scene."""
    view, ms = shown_model_view
    inst = _note(ms, leader=dict(LEADER, edge=edge, t=t))
    inst.set_block_rotation(rotation)
    inst.set_block_mirrored(mirrored)
    from tests.test_note_instance import leader_op
    op = leader_op(inst)
    pose = inst.pose_transform()
    knee = pose.map(QPointF(op.pieces[0].x1, op.pieces[0].y1))
    attach = pose.map(QPointF(op.pieces[0].x0, op.pieces[0].y0))
    ms._note_ctl.begin(inst)
    ov = ms._note_ctl.overlay
    ok = ov.grip_points()[ov.LEADER_KNEE_GRIP]
    from firepro3d import text_leader as _tl
    oa, _k, _t = _tl.box_frame_points(ov)
    oa = _tl._to_parent(ov, oa)                    # the overlay is top level: parent = scene
    assert (ok.x(), ok.y()) == pytest.approx((knee.x(), knee.y()), abs=1.0)
    assert (oa.x(), oa.y()) == pytest.approx((attach.x(), attach.y()), abs=1.0)
    ms._text_edit_ctl.commit()


def test_deleting_the_host_during_an_edit_drops_the_overlay_without_a_crash(placed_note):
    ms, inst = placed_note
    ms._note_ctl.begin(inst)
    ov = ms._note_ctl.overlay
    ms.remove_block_instance(inst)
    assert ms._note_ctl.overlay is None and editing_text_item(ms) is None
    assert ov.scene() is None
    assert ms._text_edit_ctl.commit() is None            # nothing live; nothing to crash


def test_undo_during_an_edit_drops_the_overlay_without_a_crash(placed_note):
    ms, inst = placed_note
    ms._note_ctl.begin(inst)
    ms._note_ctl.overlay.setPlainText("x")
    ms.undo()
    assert ms._note_ctl.overlay is None and editing_text_item(ms) is None
    assert not [i for i in ms.items() if isinstance(i, TextItem)]


def test_a_restore_with_a_live_overlay_discards_it(placed_note):
    ms, inst = placed_note
    ms._note_ctl.begin(inst)
    ms._restore_network(ms._undo_stack[-1])               # the path an undo / redo takes
    assert ms._note_ctl.overlay is None and editing_text_item(ms) is None


def test_set_mode_commits_the_overlay(placed_note):
    ms, inst = placed_note
    ms._note_ctl.begin(inst)
    ms._note_ctl.overlay.setPlainText("by mode switch")
    ms.set_mode("select")
    assert inst.attributes["Text"] == "by mode switch" and ms._note_ctl.overlay is None


# -- grips ------------------------------------------------------------------

def _grip_handle(ms, inst, which):
    inst.setSelected(True)
    m = ms._live_manip()
    m.rebake()
    i = inst.note_grip_index(which)
    return m, next(h for h in m._active_handles()
                   if isinstance(h, GripHandle) and h.item is inst and h.index == i)


def _drag(m, handle, target):
    start = handle.scene_position(m._rect)
    m._begin_handle(handle, start, QPointF(0, 0))
    m._moved = True
    handle.on_drag(m, target, Qt.KeyboardModifier.NoModifier)
    handle.on_release(m, target, Qt.KeyboardModifier.NoModifier)


def test_grip_points_are_box_corner_then_knee_then_tip(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    box = inst.note_box_scene()
    g = inst.grip_points()
    assert len(g) == 3
    assert (g[0].x(), g[0].y()) == pytest.approx((box.right(), box.bottom()), abs=1e-6)
    assert (g[1].x(), g[1].y()) == pytest.approx((box.right() + 6.0 * K, box.center().y()), abs=1e-6)
    assert (g[2].x(), g[2].y()) == (1400.0, 300.0)
    inst.note.pop("leader")
    assert len(inst.grip_points()) == 1


def test_tip_grip_drag_through_the_manipulator_is_one_undo_step(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    before = _tip(inst)
    depth = len(ms._undo_stack)
    m, h = _grip_handle(ms, inst, "tip")
    _drag(m, h, QPointF(1500.0, 200.0))
    assert _tip(inst) == pytest.approx((1500.0, 200.0))
    assert len(ms._undo_stack) == depth + 1
    ms.undo()
    again = next(i for i in ms._block_instances if i.note)
    assert (again.note["leader"]["tip_x"], again.note["leader"]["tip_y"]) == before


def test_knee_grip_moves_only_the_shoulder(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    tip = _tip(inst)
    m, h = _grip_handle(ms, inst, "knee")
    _drag(m, h, QPointF(0.0, -700.0))                 # above the box: the top edge takes it
    assert inst.note["leader"]["edge"] == "T"
    assert _tip(inst) == tip
    assert _drawn_tip(inst) == pytest.approx(tip)


def test_box_grip_resizes_the_box_and_never_moves_the_tip(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    tip = _tip(inst)
    m, h = _grip_handle(ms, inst, "box")
    _drag(m, h, QPointF(1200.0, 600.0))
    assert inst.note["wrap_width_mm"] == pytest.approx(22.0)       # (1200 - -1000) / K
    assert inst.note["box_height_mm"] == pytest.approx(10.0)       # (600 - -400) / K
    assert _tip(inst) == tip and _drawn_tip(inst) == pytest.approx(tip)


def test_box_grip_floors_at_the_minimum(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    inst.apply_grip(inst.note_grip_index("box"), QPointF(-990.0, -390.0))
    assert (inst.note["wrap_width_mm"], inst.note["box_height_mm"]) == (MIN_NOTE_BOX_MM,) * 2


def test_box_grip_on_a_rotated_note_follows_the_pose(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    inst.note["box_height_mm"] = 12.0                  # above the floor, so a no-op drag keeps it
    inst.note_changed()
    inst.set_block_rotation(90.0)
    g = inst.grip_points()[0]
    inst.apply_grip(0, g)                              # a no-op drag lands where it started
    assert (inst.note["wrap_width_mm"], inst.note["box_height_mm"]) == pytest.approx((20.0, 12.0))
    inst.apply_grip(0, QPointF(g.x(), g.y() - 500.0))  # 90 deg CCW: scene -y is the box's +x
    assert inst.note["wrap_width_mm"] == pytest.approx(25.0)


# -- the tip is pinned and carried ------------------------------------------

def test_moving_a_note_pins_the_tip(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    tip = _tip(inst)
    inst.setSelected(True)
    ms._selected_items = [inst]
    ms.move_items(QPointF(500.0, 0.0))                 # the Move tool's commit
    assert inst.block_pos()[0] == pytest.approx(-500.0)
    assert _tip(inst) == tip and _drawn_tip(inst) == pytest.approx(tip)


def test_copy_carries_the_tip_and_joins_the_active_view(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    tip = _tip(inst)
    ms.active_view_key = "detail:D1"
    new = ms.paste_items(QPointF(300.0, 100.0), data=ms._clipboard_item_dicts([inst]))
    (cp,) = new
    assert _tip(cp) == pytest.approx((tip[0] + 300.0, tip[1] + 100.0))
    assert _drawn_tip(cp) == pytest.approx(_tip(cp))
    assert cp.note["view"] == "detail:D1" and inst.note["view"] == PLAN
    assert _tip(inst) == tip                           # the source did not move


def test_paste_is_refused_where_the_canvas_cannot_hold_notes(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    recs = ms._clipboard_item_dicts([inst])
    ed = Model_Space(scene_role="block_editor")
    ed.active_view_key = PLAN
    msgs = []
    ed._show_status = lambda m, *a, **k: msgs.append(m)
    assert ed.paste_items(QPointF(0, 0), data=recs) == []
    assert not [i for i in ed._block_instances if i.note]
    assert msgs[-1] == NOTE_PASTE_REFUSED                # the user is told
    ms.active_view_key = "elevation:North"
    msgs.clear()
    ms._show_status = lambda m, *a, **k: msgs.append(m)
    assert ms.paste_items(QPointF(0, 0), data=recs) == []
    assert len([i for i in ms._block_instances if i.note]) == 1
    assert msgs[-1] == NOTE_PASTE_REFUSED


def test_a_mirror_copy_joins_the_active_view_and_reflects_the_tip(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    ms.active_view_key = "detail:D1"
    cp = ms._add_from_dict(inst.to_dict())
    assert cp.note["view"] == "detail:D1"
    cp.manip_reflect(QPointF(0.0, 0.0), QPointF(0.0, 100.0))      # across the y axis
    assert _tip(cp) == pytest.approx((-1400.0, 300.0))
    assert _drawn_tip(cp) == pytest.approx(_tip(cp))


@pytest.mark.parametrize("angle,pivot", [(90.0, (0.0, 0.0)), (37.0, (200.0, -300.0))])
def test_rotate_carries_the_tip_like_the_box(placed_note_with_leader, angle, pivot):
    ms, inst = placed_note_with_leader
    pv = QPointF(*pivot)
    tip0 = QPointF(*_tip(inst))
    pos0 = QPointF(*inst.block_pos())
    inst.manip_rotate(angle, pv)
    d_tip = math.hypot(_tip(inst)[0] - pv.x(), _tip(inst)[1] - pv.y())
    assert d_tip == pytest.approx(math.hypot(tip0.x() - pv.x(), tip0.y() - pv.y()))
    pos1 = QPointF(*inst.block_pos())
    ang_pos = math.atan2(pos1.y() - pv.y(), pos1.x() - pv.x()) - math.atan2(pos0.y() - pv.y(), pos0.x() - pv.x())
    ang_tip = (math.atan2(_tip(inst)[1] - pv.y(), _tip(inst)[0] - pv.x())
               - math.atan2(tip0.y() - pv.y(), tip0.x() - pv.x()))
    assert math.cos(ang_pos) == pytest.approx(math.cos(ang_tip), abs=1e-9)
    assert math.sin(ang_pos) == pytest.approx(math.sin(ang_tip), abs=1e-9)
    assert _drawn_tip(inst) == pytest.approx(_tip(inst))


def test_scale_never_moves_the_tip(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    tip = _tip(inst)
    inst.manip_scale_about(QPointF(0.0, 0.0), 2.0)
    assert _tip(inst) == tip and _drawn_tip(inst) == pytest.approx(tip)


# -- panel rows ---------------------------------------------------------------

def test_leader_rows_toggle_and_style_a_note(placed_note):
    ms, inst = placed_note
    rows = inst.get_properties()
    assert rows["Type"]["value"] == "Note" and rows["Leader"]["value"] is False
    assert "Leader End" not in rows
    depth = len(ms._undo_stack)
    with ms.deferred_undo_push():                       # what PropertyManager wraps a commit in
        inst.set_property("Leader", True)               # (also loads the Arrow into the project)
    assert len(ms._undo_stack) == depth + 1             # one step per panel commit
    rec = inst.note["leader"]
    box = inst.note_box_scene()
    assert rec["edge"] == "R" and rec["end"] == TEXT_LEADER_END_ID
    assert rec["tip_x"] > box.right() and box.top() < rec["tip_y"] < box.bottom() + 20.0 * K
    assert _drawn_tip(inst) == pytest.approx((rec["tip_x"], rec["tip_y"]))
    rows = inst.get_properties()
    assert rows["Leader"]["value"] is True and {"Leader End", "Leader Weight"} <= set(rows)
    inst.set_property("Leader Weight", rows["Leader Weight"]["options"][0])
    assert inst.note["leader"]["weight"] == rows["Leader Weight"]["options"][0]
    inst.set_property("Leader", False)
    assert "leader" not in inst.note                    # off drops the record
    inst.set_property("Leader", True)
    assert inst.note["leader"]["weight"] == ""          # on again starts from the default


def test_the_real_arrow_end_draws_on_a_note_leader(placed_note):
    """Toggling Leader on loads the shipped Arrow into the project; its ops draw."""
    ms, inst = placed_note
    inst.set_property("Leader", True)
    assert ms.get_block_definition(TEXT_LEADER_END_ID) is not None
    from tests.test_note_instance import leader_op
    assert leader_op(inst).ends[1]["end"] == TEXT_LEADER_END_ID
    # the head is inside the bounds the manipulator and the hit test use
    tip = QPointF(*_tip(inst))
    assert inst.boundingRect().contains(tip)
    assert inst.shape().contains(tip + QPointF(-1.0 * K, 0.0)) or inst.shape().intersects(
        QRectF(tip.x() - 6 * K, tip.y() - 3 * K, 6 * K, 6 * K))


# -- a plain block is unchanged -----------------------------------------------

def test_a_plain_block_is_unchanged_by_the_grip_methods(shown_model_view, real_system_library):
    view, ms = shown_model_view
    ms.ensure_system_block(NOTE_BLOCK_ID)
    plain = ms.place_block_instance(NOTE_BLOCK_ID, (100.0, 100.0))
    before = plain.to_dict()
    assert plain.grip_points() == [] and plain.manip_extra_handles() == []
    plain.apply_grip(0, QPointF(5000.0, 5000.0))
    plain.apply_grip(2, QPointF(5000.0, 5000.0))
    assert plain.to_dict() == before
    # the selection manipulator keeps its rigid set alone: no grip handle at all
    plain.setSelected(True)
    m = ms._live_manip()
    m.rebake()
    assert m._active_handles() == list(m._rigid.values())
    assert not [h for h in m._active_handles() if isinstance(h, GripHandle)]
    # Move
    ms._selected_items = [plain]
    ms.move_items(QPointF(40.0, 0.0))
    assert plain.block_pos() == (140.0, 100.0)
    # stretch: the crossing window captures nothing from a block
    ms._tools.begin_stretch_crossing(QRectF(0, 0, 1000, 1000))
    assert not ms._stretch_vertices and not ms._stretch_full_items
    # rubber band: a plain block and a note are both selected as before
    note = _note(ms, pos=(2000.0, 2000.0))
    plain.set_block_pos(100.0, 100.0)
    hits = ms.rubber_band_hits(QRectF(-100, -100, 6000, 6000), crossing=True)
    assert plain in hits and note in hits


def test_a_note_in_a_multi_selection_keeps_its_tip_through_a_scale(placed_note_with_leader):
    """D7 ruling, multi-select included: the Scale tool's baked scale about a base."""
    ms, inst = placed_note_with_leader
    plain = ms.place_block_instance(NOTE_BLOCK_ID, (-3000.0, 0.0))
    tip = _tip(inst)
    for it in (plain, inst):
        it.manip_scale_about(QPointF(-3000.0, 0.0), 0.5)
    assert _tip(inst) == tip


# -- panel rows carry the tip (D7) ----------------------------------------------

def _clone(ms, inst):
    return ms._add_from_dict(inst.to_dict())


def test_the_rotation_row_carries_the_tip_like_manip_rotate_in_one_step(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    ref = _clone(ms, inst)
    ref.manip_rotate(90.0, QPointF(*inst.block_pos()))
    depth = len(ms._undo_stack)
    inst.set_property("Rotation", "90")
    assert _tip(inst) == pytest.approx(_tip(ref))
    assert _tip(inst) != (1400.0, 300.0) and inst.block_rotation() == 90.0
    assert _drawn_tip(inst) == pytest.approx(_tip(inst))
    assert len(ms._undo_stack) == depth + 1


def test_the_mirrored_row_carries_the_tip_like_manip_reflect_in_one_step(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    inst.set_block_rotation(30.0)
    ref = _clone(ms, inst)
    pos = QPointF(*inst.block_pos())
    from PyQt6.QtGui import QTransform
    rigid = QTransform()
    rigid.translate(pos.x(), pos.y())
    rigid.rotate(-30.0)
    ref.manip_reflect(pos, rigid.map(QPointF(0.0, 1.0)))     # the axis the flag flip implies
    depth = len(ms._undo_stack)
    inst.set_property("Mirrored", True)
    assert inst.block_mirrored() and ref.block_mirrored()
    assert _tip(inst) == pytest.approx(_tip(ref))
    assert _drawn_tip(inst) == pytest.approx(_tip(inst))
    assert len(ms._undo_stack) == depth + 1
    inst.set_property("Mirrored", False)                      # and back: the tip returns
    assert _tip(inst) == pytest.approx((1400.0, 300.0))


def test_the_raw_pose_setters_stay_raw(placed_note_with_leader):
    ms, inst = placed_note_with_leader
    inst.set_block_rotation(90.0)                             # section_scene's path: no carry
    assert _tip(inst) == (1400.0, 300.0)
