"""Seam fix item 2: a leader's End loads outside the model undo history."""
import os

from PyQt6.QtCore import QPointF

from firepro3d.constants import TEXT_LEADER_END_ID
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
from firepro3d.system_blocks import NOTE_BLOCK_ID
from firepro3d.text_item import TextAnnotationData, TextItem


def _fresh_project():
    ms = Model_Space()
    ms.push_undo_state()                       # a baseline state, so there is a step to undo to
    return ms


def test_a_sheet_text_leader_loads_arrow_without_a_model_undo_step_and_it_survives_undo(
        qapp, real_system_library):
    ms = _fresh_project()
    assert ms.get_block_definition(TEXT_LEADER_END_ID) is None
    pos, depth = ms._undo_pos, len(ms._undo_stack)
    paper = PaperScene(Sheet.create_default(), ViewResolver(ms, None, None, None))
    t = TextItem(TextAnnotationData(text="n", x=20.0, y=20.0, wrap_width_mm=40.0,
                                    box_height_mm=12.0, height_mm=3.0))
    paper.addItem(t)
    t.set_property("Leader", True)             # the real panel path, on the sheet's own stack
    assert t.data.leader and t.data.leader["end"] == TEXT_LEADER_END_ID
    assert ms.get_block_definition(TEXT_LEADER_END_ID) is not None
    assert (ms._undo_pos, len(ms._undo_stack)) == (pos, depth)      # no model step
    ms.push_undo_state()
    ms.undo()
    assert ms.get_block_definition(TEXT_LEADER_END_ID) is not None  # the sheet leader keeps its End


def test_the_first_note_leader_loads_arrow_without_a_model_undo_step_and_it_survives_undo(
        qapp, real_system_library):
    ms = _fresh_project()
    ms.active_view_key = "plan:Plan: Level 1"
    ms.ensure_system_block(NOTE_BLOCK_ID)
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note={
        "view": ms.active_view_key, "wrap_width_mm": 40.0, "box_height_mm": 8.0})
    inst.set_attributes({"Text": "x"})
    ms.push_undo_state()
    pos, depth = ms._undo_pos, len(ms._undo_stack)
    chg = inst._note_leader_change("Leader", True)          # the load, before any panel push
    assert chg[0] and ms.get_block_definition(TEXT_LEADER_END_ID) is not None
    assert (ms._undo_pos, len(ms._undo_stack)) == (pos, depth)
    inst.note["leader"] = chg[0]
    ms.push_undo_state()
    ms.undo()
    assert ms.get_block_definition(TEXT_LEADER_END_ID) is not None


def test_an_open_primitive_end_still_loads_as_an_undoable_batch(qapp, real_system_library):
    """ensure_end_available keeps its default: a plan line's End is one undo step."""
    from firepro3d.capabilities import ensure_end_available
    ms = _fresh_project()
    depth = len(ms._undo_stack)
    assert ensure_end_available(TEXT_LEADER_END_ID, ms)
    assert len(ms._undo_stack) == depth + 1
