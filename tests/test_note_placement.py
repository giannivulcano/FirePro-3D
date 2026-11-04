"""Task 9: the Note tool places by two corners on plan and detail and opens the editor."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.constants import MIN_NOTE_BOX_MM
from firepro3d.model_space import NOTE_OFF_HINT, Model_Space
from firepro3d.system_blocks import NOTE_BLOCK_ID
from firepro3d.text_item import editing_text_item
from tests._note_helpers import click
from tests.test_note_ribbon import main_window  # noqa: F401  (module MainWindow fixture)

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


# -- the Note block is not a placeable symbol (seam fix item 4) ------------------

def _plan_view(shown_model_view):
    view, scene = shown_model_view
    scene.active_view_key = PLAN
    scene.ensure_system_block(NOTE_BLOCK_ID)
    return view, scene


def test_set_mode_place_block_refuses_the_note_block(shown_model_view, real_system_library):
    from firepro3d.capabilities import NOTE_PICK_REASON
    view, scene = _plan_view(shown_model_view)
    msgs = []
    scene._show_status = lambda m, *a, **k: msgs.append(m)
    scene.set_mode("place_block", template=NOTE_BLOCK_ID)
    assert scene.mode != "place_block" and msgs[-1] == NOTE_PICK_REASON


def test_an_armed_note_symbol_is_refused_at_the_click(shown_model_view, real_system_library):
    view, scene = _plan_view(shown_model_view)
    scene._place_block_id = NOTE_BLOCK_ID                # armed some other way
    scene.mode = "place_block"
    n = len(scene._block_instances)
    scene._press_place_block(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert len(scene._block_instances) == n


def test_dragging_the_note_block_is_refused_and_nesting_it_is_too(
        shown_model_view, real_system_library):
    from firepro3d import block_drop
    from firepro3d.capabilities import NOTE_PICK_REASON
    view, scene = _plan_view(shown_model_view)
    _d, _pool, why = block_drop.resolve_block_drag(scene, {"id": NOTE_BLOCK_ID, "path": None})
    assert why == NOTE_PICK_REASON
    from firepro3d.block_editor import BlockEditorWidget
    w = BlockEditorWidget(scene)                           # nesting in a block / schematic canvas
    try:
        _d, _pool, why = block_drop.resolve_block_drag(
            w.editor_scene, {"id": NOTE_BLOCK_ID, "path": None})
        assert why == NOTE_PICK_REASON
    finally:
        w.editor_scene.cleanup()


def test_pasting_a_note_still_works(shown_model_view, real_system_library):
    view, scene = _plan_view(shown_model_view)
    n = scene.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note={
        "view": PLAN, "wrap_width_mm": 20.0, "box_height_mm": 8.0})
    new = scene.paste_items(QPointF(100.0, 0.0), data=scene._clipboard_item_dicts([n]))
    assert len(new) == 1 and new[0].note["view"] == PLAN


def test_the_note_tool_still_places(shown_model_view, real_system_library):
    from PyQt6.QtCore import QRectF
    view, scene = _plan_view(shown_model_view)
    scene.set_mode("note")
    scene._note_ctl.place(QRectF(0, 0, 2000, 1000))
    assert scene._block_instances[-1].note["view"] == PLAN
    scene._text_edit_ctl.commit()


def test_activating_the_note_block_in_the_browser_starts_the_note_tool_on_a_plan(
        main_window, real_system_library):
    main_window._set_canvas_context("plan")
    sc = main_window._active_scene()
    sc.active_view_key = PLAN
    main_window._on_block_activated(NOTE_BLOCK_ID)
    try:
        assert sc.mode == "note"
    finally:
        sc.set_mode("select")


def test_activating_the_note_block_is_refused_off_a_plan(main_window, real_system_library):
    sc = main_window.scene
    sc.set_mode("select")
    old = sc.active_view_key
    sc.active_view_key = "elevation:North"                 # a canvas that cannot hold a note
    hints = []
    sc.instructionChanged.connect(hints.append)
    try:
        main_window._on_block_activated(NOTE_BLOCK_ID)
        assert sc.mode != "note" and hints and hints[-1] == NOTE_OFF_HINT
    finally:
        sc.active_view_key = old
