"""Task 9: the Note tool places by two corners on plan and detail and opens the editor."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.constants import MIN_NOTE_BOX_MM
from firepro3d.model_space import NOTE_OFF_HINT, Model_Space
from firepro3d.system_blocks import NOTE_BLOCK_ID
from firepro3d.text_item import editing_text_item
from tests._note_helpers import click

PLAN = "plan:Plan: Level 1"
A, B = QPointF(-1200.0, -800.0), QPointF(1200.0, 400.0)       # 2400 x 1200 scene mm


_click = click


def _place(shown_model_view, key=PLAN):
    view, scene = shown_model_view
    scene.active_view_key = key
    scene.set_mode("note")
    assert scene.mode == "note"
    _click(view, A)
    assert scene._text_anchor is not None            # the first corner set the anchor
    _click(view, B)
    return view, scene


def test_two_clicks_place_a_note_owned_by_the_active_view_and_open_the_editor(
        shown_model_view, real_system_library):
    view, scene = _place(shown_model_view)
    inst = scene._block_instances[-1]
    assert inst.block_id == NOTE_BLOCK_ID
    assert inst.note["view"] == PLAN
    k = inst.note_k()
    assert (inst.note["wrap_width_mm"] * k, inst.note["box_height_mm"] * k) == pytest.approx(
        (2400.0, 1200.0), rel=0.05)
    assert scene.editing_note() is inst
    ov = scene._note_ctl.overlay
    assert editing_text_item(scene) is ov            # the real inline-edit session is live
    assert scene._texts == [] and not inst.isVisible()
    assert scene.mode != "note"                      # single placement: back to Select


def test_a_small_drag_floors_at_the_minimum_box(shown_model_view, real_system_library):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.set_mode("note")
    _click(view, QPointF(0.0, 0.0))
    _click(view, QPointF(8.0, 8.0))
    inst = scene._block_instances[-1]
    assert (inst.note["wrap_width_mm"], inst.note["box_height_mm"]) == (MIN_NOTE_BOX_MM,) * 2


def test_typed_text_commits_to_the_attribute_with_one_undo_step(
        shown_model_view, real_system_library):
    view, scene = _place(shown_model_view)
    inst = scene._block_instances[-1]
    depth = len(scene._undo_stack)
    scene._note_ctl.overlay.setPlainText("Hold at 3 m")
    scene._text_edit_ctl.commit()
    assert inst.attributes["Text"] == "Hold at 3 m" and inst.isVisible()
    assert len(scene._undo_stack) == depth + 1
    scene.undo()
    assert not [i for i in scene._block_instances if i.note]       # place + type is one step


def test_an_empty_new_note_is_discarded_with_no_step(shown_model_view, real_system_library):
    view, scene = _place(shown_model_view)
    depth = len(scene._undo_stack)
    scene._text_edit_ctl.commit()
    assert not [i for i in scene._block_instances if i.note]
    assert len(scene._undo_stack) == depth


def test_note_places_on_a_detail_view_too(shown_model_view, real_system_library):
    view, scene = _place(shown_model_view, key="detail:D1")
    assert scene._block_instances[-1].note["view"] == "detail:D1"


@pytest.mark.parametrize("key", ["", "paper:Sheet", "elevation:North"])
def test_note_mode_is_refused_off_a_plan_or_detail_view(qapp, key):
    ms = Model_Space()
    ms.active_view_key = key
    hints = []
    ms.instructionChanged.connect(hints.append)
    ms.set_mode("note")
    assert ms.mode != "note" and hints[-1] == NOTE_OFF_HINT


@pytest.mark.parametrize("role", ["block_editor"])
def test_note_mode_is_refused_on_an_editor_scene(qapp, role):
    ms = Model_Space(scene_role=role)
    ms.active_view_key = PLAN
    ms.set_mode("note")
    assert ms.mode != "note"
