"""Task 6: the shipped Note block and the per-placement note record (D8, D14)."""
import os

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage, QPainter, QColor

from firepro3d.annotative import reprepare_annotative
from firepro3d.assets import system_blocks_path
from firepro3d.block_instance import BlockInstance
from firepro3d.block_library import load_block_file
from firepro3d.constants import TEXT_LEADER_END_ID
from firepro3d.model_space import Model_Space
from firepro3d.render_op import STROKE, TEXT
from firepro3d.system_blocks import NOTE_BLOCK_ID

NOTE = {"view": "plan:Plan: Level 1", "wrap_width_mm": 40.0, "box_height_mm": 8.0}
LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 6.0, "tip_x": 500.0, "tip_y": 400.0,
          "end": "none", "weight": ""}


def _path(*parts):
    return os.path.join(system_blocks_path(), *parts)


def note_scene(with_arrow=False):
    ms = Model_Space()
    ms.register_block_definition(load_block_file(_path("Annotations", "Note.fpdb")))
    if with_arrow:
        ms.register_block_definition(load_block_file(_path("Endtypes", "Arrow.fpdb")))
    return ms


def leader_op(inst):
    """The note's leader stroke: the STROKE op that carries two pieces."""
    return next(o for o in inst.render_ops() if o.kind == STROKE and len(o.pieces) == 2)


def drawn_tip_scene(inst):
    """Where the leader's last point lands in the scene, through the real pose."""
    last = leader_op(inst).pieces[-1]
    return inst.pose_transform().map(QPointF(last.x1, last.y1))


def test_note_block_ships_annotative_with_a_text_attribute(qapp):
    d = load_block_file(_path("Annotations", "Note.fpdb"))
    assert d.id == NOTE_BLOCK_ID and d.scale_mode == "annotative"
    assert [a["key"] for a in d.attributes] == ["Text"]
    assert [p["text"] for p in d.primitives] == ["@[Text]"]


def test_record_round_trips_through_place_kwargs(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (10.0, 20.0), note=dict(NOTE))
    rec = inst.to_dict()
    assert rec["note"] == NOTE
    assert BlockInstance.place_kwargs(rec)["note"] == NOTE
    again = ms.place_block_instance(NOTE_BLOCK_ID, (10.0, 20.0), **BlockInstance.place_kwargs(rec))
    assert again.note == NOTE and again.note is not inst.note


def test_record_survives_from_dict(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE, leader=dict(LEADER)))
    back = BlockInstance.from_dict(inst.to_dict(), ms.get_block_definition)
    assert back.note == inst.note and back.note is not inst.note


def test_plain_block_record_has_no_note_key(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0))
    assert "note" not in inst.to_dict() and inst.note is None


def test_note_never_enters_a_nested_record(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE))
    assert "note" not in inst.to_nested_dict()


def test_placement_box_size_reaches_the_ops(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE))
    inst.set_attributes({"Text": "hello"})
    wide = inst.boundingRect().width()
    inst.note["wrap_width_mm"] = 80.0
    inst.note_changed()
    assert inst.boundingRect().width() > wide


def test_the_box_is_the_manipulator_frame_not_the_leader(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE, leader=dict(LEADER)))
    inst.set_attributes({"Text": "hello"})
    box = inst.manip_bounds()
    k = ms.scale_manager.drawing_scale        # printed mm -> scene mm\n    assert box.width() == pytest.approx(40.0 * k) and box.height() == pytest.approx(8.0 * k)
    assert inst.boundingRect().contains(box)
    assert inst.boundingRect().contains(QPointF(500.0, 400.0))   # the tip is in the bounds


def test_leader_tip_stays_put_when_the_drawing_scale_changes(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE, leader=dict(LEADER)))
    inst.set_attributes({"Text": "hello"})
    before = drawn_tip_scene(inst)
    assert (before.x(), before.y()) == pytest.approx((500.0, 400.0))
    box1 = inst.manip_bounds().width()
    ms.scale_manager.drawing_scale = 50.0
    reprepare_annotative(ms)
    after = drawn_tip_scene(inst)
    assert (after.x(), after.y()) == pytest.approx((500.0, 400.0))
    assert inst.note["leader"]["tip_x"] == 500.0                 # stored in scene mm
    assert inst.manip_bounds().width() == pytest.approx(box1 * 50.0 / 100.0)   # the box DID scale (1:100 -> 1:50)


@pytest.mark.parametrize("mirrored,rotation", [(False, 0.0), (True, 0.0), (False, 90.0), (True, 30.0)])
def test_tip_lands_on_target_under_any_pose(qapp, mirrored, rotation):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (30.0, 10.0), rotation=rotation, mirrored=mirrored,
                                   note=dict(NOTE, leader=dict(LEADER)))
    inst.set_attributes({"Text": "hello"})
    tip = drawn_tip_scene(inst)
    assert (tip.x(), tip.y()) == pytest.approx((500.0, 400.0))


def test_a_real_end_type_draws_on_the_note(qapp):
    """The real Arrow end: the leader op carries it and the bounds hold its head."""
    ms = note_scene(with_arrow=True)
    inst = ms.place_block_instance(
        NOTE_BLOCK_ID, (0.0, 0.0),
        note=dict(NOTE, leader=dict(LEADER, tip_x=200.0, tip_y=10.0, end=TEXT_LEADER_END_ID)))
    inst.set_attributes({"Text": "hello"})
    op = leader_op(inst)
    assert op.ends[1]["end"] == TEXT_LEADER_END_ID
    ms.scale_manager.drawing_scale = 100.0
    reprepare_annotative(ms)
    plain = ms.place_block_instance(
        NOTE_BLOCK_ID, (0.0, 0.0),
        note=dict(NOTE, leader=dict(LEADER, tip_x=200.0, tip_y=10.0, end="none")))
    plain.set_attributes({"Text": "hello"})
    assert inst.boundingRect().height() > plain.boundingRect().height()   # the head is bounded


def test_block_edit_restyles_without_moving_box_or_tip(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE, leader=dict(LEADER)))
    inst.set_attributes({"Text": "hello"})
    box, tip = inst.manip_bounds(), drawn_tip_scene(inst)
    d = ms.get_block_definition(NOTE_BLOCK_ID)
    d.set_primitives([dict(d.primitives[0], height_mm=3.5, bold=True)])
    inst.note_changed()
    assert inst.manip_bounds() == box          # the box holds: the font fits it
    now = drawn_tip_scene(inst)
    assert (now.x(), now.y()) == pytest.approx((tip.x(), tip.y()))


def test_ops_text_follows_the_attribute(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE))
    inst.set_attributes({"Text": ""})
    assert not any(o.kind == TEXT and not o.path.isEmpty() for o in inst.render_ops())
    inst.set_attributes({"Text": "hello"})
    assert any(o.kind == TEXT and not o.path.isEmpty() for o in inst.render_ops())


def test_a_note_never_grows_a_section_crop(qapp):
    from firepro3d.section_marker import building_bbox
    ms = note_scene()
    before = building_bbox(ms)
    ms.place_block_instance(NOTE_BLOCK_ID, (90000.0, 90000.0), note=dict(NOTE))
    assert building_bbox(ms) == before
    ms.place_block_instance(NOTE_BLOCK_ID, (90000.0, 90000.0))     # a plain block does count
    assert building_bbox(ms) != before


@pytest.mark.parametrize("mirrored,rotation", [(False, 0.0), (True, 30.0)])
def test_editing_the_block_origin_never_drags_the_tip(qapp, mirrored, rotation):
    """The ops frame includes the definition-origin shift; the tip's way back from
    the scene must invert it too. (The box moves with the origin: the insertion
    point stays put and the box hangs from it, so it shifts by minus the origin.)"""
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (30.0, 10.0), rotation=rotation,
                                   mirrored=mirrored, note=dict(NOTE, leader=dict(LEADER)))
    inst.set_attributes({"Text": "hello"})
    tip = drawn_tip_scene(inst)
    d = ms.get_block_definition(NOTE_BLOCK_ID)
    d.origin = (7.0, 4.0)
    inst.note_changed()
    now = drawn_tip_scene(inst)
    assert (now.x(), now.y()) == pytest.approx((tip.x(), tip.y()))
    assert (inst.note["leader"]["tip_x"], inst.note["leader"]["tip_y"]) == (500.0, 400.0)
