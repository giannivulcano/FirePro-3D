"""Seam fix item 1: the dependency walkers see a leader's End and weight."""
import json
import os

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import block_library
from firepro3d import paper_display as pd
from firepro3d.assets import system_blocks_path
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_library import load_block_file, used_weight_names
from firepro3d.block_registry import referenced_ids
from firepro3d.constants import TEXT_LEADER_END_ID
from firepro3d.display_manager import DisplayManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef
from firepro3d.render_op import STROKE
from firepro3d.system_blocks import NOTE_BLOCK_ID
from firepro3d.text_item import TextAnnotationData, TextItem

LEADER = {"edge": "R", "t": 0.5, "shoulder_mm": 6.0, "tip_x": 60.0, "tip_y": 30.0,
          "end": TEXT_LEADER_END_ID, "weight": ""}


def _arrow():
    return load_block_file(os.path.join(system_blocks_path(), "Endtypes", "Arrow.fpdb"))


def _note_def():
    return load_block_file(os.path.join(system_blocks_path(), "Annotations", "Note.fpdb"))


def _text_def(**leader):
    rec = TextItem(TextAnnotationData(text="n", wrap_width_mm=30.0, box_height_mm=10.0,
                                      height_mm=3.0, color="#ffffff",
                                      leader=dict(LEADER, **leader))).to_dict()
    return BlockDefinition.new(name="T", library="L", series="S", origin=(0.0, 0.0),
                               primitives=[rec])


def _project(*defs):
    ms = Model_Space()
    for d in defs:
        ms.register_block_definition(d)
    return ms


@pytest.fixture
def weights():
    pd.set_project_line_weights([*pd.project_line_weights(), LineWeightDef("Leaderonly", 0.33)])
    yield
    pd.reset_project_line_weights()


# -- End: bundle, cycle, closure ------------------------------------------------

def test_referenced_ids_and_closure_see_a_text_leader_end(qapp):
    arrow, t = _arrow(), _text_def()
    ms = _project(arrow, t)
    assert referenced_ids(t) == {arrow.id}
    assert ms.block_registry.closure(t.id) == {arrow.id}
    assert referenced_ids(_text_def(end="none")) == set()          # keywords are not blocks
    assert referenced_ids(_text_def(end="by_linetype")) == set()


def test_a_library_save_bundles_the_end_and_it_draws_in_a_project_that_never_held_it(
        qapp, tmp_path):
    arrow, t = _arrow(), _text_def()
    ms = _project(arrow, t)
    path = block_library.save_to_library(t, root=str(tmp_path),
                                         bundled=ms.block_registry.bundle_for(t.id))
    with open(path, encoding="utf-8") as fh:
        assert set(json.load(fh)["bundled"]) == {arrow.id}
    fresh = Model_Space()
    assert fresh.get_block_definition(arrow.id) is None
    fresh.load_blocks_from_files([path])
    assert fresh.get_block_definition(arrow.id) is not None
    inst = fresh.place_block_instance(t.id, (0.0, 0.0))
    op = next(o for o in inst.render_ops() if o.kind == STROKE and len(o.pieces) == 2)
    assert op.ends[1]["end"] == arrow.id
    reg = fresh.block_registry
    assert reg.get(op.ends[1]["end"]) is not None            # resolves: no missing-end badge


def test_a_text_leader_end_cannot_make_a_cycle(qapp):
    arrow, t = _arrow(), _text_def()
    ms = _project(arrow, t)
    assert ms.block_registry.would_cycle(arrow.id, t.id) is True    # the End nesting t would loop
    assert ms.block_registry.would_cycle(t.id, arrow.id) is False   # t already uses the End


# -- End: delete / off refusal -----------------------------------------------------

def _note_with_leader(ms, **kw):
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note={
        "view": "plan:Plan: Level 1", "wrap_width_mm": 40.0, "box_height_mm": 8.0,
        "leader": dict(LEADER, **kw)})
    return inst


def test_end_delete_and_off_are_refused_while_a_note_leader_uses_it(qapp):
    arrow = _arrow()
    ms = _project(arrow, _note_def())
    assert ms.end_off_refusal(arrow.id) is None and ms.block_users_message(arrow.id) is None
    note = _note_with_leader(ms)
    assert ms.end_off_refusal(arrow.id) is not None
    assert ms.block_users_message(arrow.id) is not None
    ms.remove_block_instance(note)
    assert ms.end_off_refusal(arrow.id) is None


def test_end_off_is_refused_while_a_plan_text_leader_uses_it(qapp):
    arrow = _arrow()
    ms = _project(arrow)
    t = TextItem(TextAnnotationData(text="n", wrap_width_mm=30.0, box_height_mm=10.0,
                                    height_mm=3.0, leader=dict(LEADER)))
    ms.addItem(t)
    ms._texts.append(t)
    assert ms.end_off_refusal(arrow.id) is not None


# -- weight --------------------------------------------------------------------------

def test_a_leader_only_weight_is_reported_in_use_and_bundled(qapp, tmp_path, weights):
    t = _text_def(weight="Leaderonly", end="none")
    assert "Leaderonly" in used_weight_names([t.to_dict()])
    ms = _project(t)
    path = block_library.save_to_library(t, root=str(tmp_path))
    with open(path, encoding="utf-8") as fh:
        assert "Leaderonly" in json.load(fh)["weights"]
    d = DisplayManager(ms, active_context="paper")
    try:
        assert d._line_weight_in_use("Leaderonly")
    finally:
        d.reject()


def test_a_note_leader_weight_counts_and_follows_a_rename(qapp, weights):
    ms = _project(_note_def())
    note = _note_with_leader(ms, end="none", weight="Leaderonly")
    d = DisplayManager(ms, active_context="paper")
    try:
        assert d._line_weight_in_use("Leaderonly")
        d._propagate_lw_rename("Leaderonly", "Renamed")
        assert note.note["leader"]["weight"] == "Renamed"
    finally:
        d.reject()


def test_a_sheet_text_and_a_definition_leader_weight_count_and_follow_a_rename(qapp, weights):
    from firepro3d.paper_space import Sheet
    ms = _project(_text_def(weight="Leaderonly", end="none"))
    sheet = Sheet.create_default()
    ms._sheets = [sheet]
    ann = TextAnnotationData(text="s", leader=dict(LEADER, end="none", weight="Leaderonly"))
    sheet.annotations.append(ann)
    d = DisplayManager(ms, active_context="paper")
    try:
        assert d._line_weight_in_use("Leaderonly")
        d._propagate_lw_rename("Leaderonly", "Renamed")
        assert ann.leader["weight"] == "Renamed"
        assert [p for p in ms.block_registry.get(
            next(b for b in ms.block_registry.ids())).primitives
            if p["type"] == "text"][0]["leader"]["weight"] == "Renamed"
    finally:
        d.reject()


# -- the End picker leaves out the edited End block -----------------------------

def test_the_end_picker_leaves_out_the_end_block_being_edited(qapp):
    arrow = _arrow()
    ed = Model_Space(scene_role="block_editor")
    ed.register_block_definition(arrow)
    t = TextItem(TextAnnotationData(text="n", wrap_width_mm=30.0, box_height_mm=10.0,
                                    height_mm=3.0, leader=dict(LEADER)))
    ed.addItem(t)
    ed._texts.append(t)
    assert "Arrow" in t.get_properties()["Leader End"]["options"]
    ed._editing_block_id = arrow.id
    assert "Arrow" not in t.get_properties()["Leader End"]["options"]


def test_a_sheet_text_leader_protects_its_end(qapp):
    from firepro3d.paper_space import Sheet
    arrow = _arrow()
    ms = _project(arrow)
    sheet = Sheet.create_default()
    ms._sheets = [sheet]
    assert ms.block_users_message(arrow.id) is None and ms.end_off_refusal(arrow.id) is None
    ann = TextAnnotationData(text="s", leader=dict(LEADER, tip_x=90.0, tip_y=60.0))
    sheet.annotations.append(ann)
    assert ms.block_users_message(arrow.id) is not None
    assert ms.end_off_refusal(arrow.id) is not None
    assert ms.delete_block_definition(arrow.id) is False          # delete refused
    assert ms.get_block_definition(arrow.id) is not None
    ann.leader = None                                              # remove the leader: all clear
    assert ms.block_users_message(arrow.id) is None and ms.end_off_refusal(arrow.id) is None
    assert ms.delete_block_definition(arrow.id) is True
