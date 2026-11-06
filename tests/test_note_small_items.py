"""Seam fix item 6: S1 tab teardown, S2 leader row owns the leader, S3 cursor, S4 constraints."""
import os

import pytest
from PyQt6.QtCore import QPointF, Qt

from firepro3d.assets import system_blocks_path
from firepro3d.block_library import load_block_file
from firepro3d.model_space import Model_Space
from firepro3d.system_blocks import NOTE_BLOCK_ID
from tests.test_note_instance import LEADER, NOTE, leader_op, note_scene
from tests.test_note_ribbon import main_window  # noqa: F401  (module MainWindow fixture)
from tests.test_note_view_scope import PLAN, place_note, view_fixture


# -- S1: a note in progress is torn down on tab change -----------------------------

def test_a_note_in_progress_is_torn_down_on_a_tab_change(main_window, real_system_library):
    win = main_window
    win._set_canvas_context("plan")
    sc = win.scene
    sc.active_view_key = PLAN
    sc.set_mode("note")
    sc._press_note(None, QPointF(0, 0), QPointF(0, 0), None, None, None)       # the tip
    ctl = sc._note_ctl
    assert ctl.tool_anchor() is not None and ctl._tool_line is not None
    win._on_tab_changed(win.central_tabs.currentIndex())                      # the real handler
    assert sc.mode == "select"
    assert ctl.tool_anchor() is None and ctl._tool_line is None               # cannot finish elsewhere


# -- S2: the Leader row owns the leader --------------------------------------------

def _with_definition_leader(ms):
    d = ms.get_block_definition(NOTE_BLOCK_ID)
    prim = dict(d.primitives[0], leader=dict(LEADER, tip_x=900.0, tip_y=60.0, end="none"))
    d.set_primitives([prim])


def test_a_leader_added_to_the_note_definition_does_not_draw_on_notes_with_the_row_off(qapp):
    ms = note_scene()
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE))
    inst.set_attributes({"Text": "hello"})
    _with_definition_leader(ms)
    inst.note_changed()
    with pytest.raises(StopIteration):
        leader_op(inst)                                    # no two-piece leader stroke
    on = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), note=dict(NOTE, leader=dict(LEADER)))
    on.set_attributes({"Text": "hello"})
    assert leader_op(on).pieces[-1].x1 != 900.0            # its own record draws, not the prim's


def test_the_overlay_of_a_note_with_the_row_off_carries_no_definition_leader(
        shown_model_view, real_system_library):
    view, ms = shown_model_view
    ms.active_view_key = PLAN
    ms.ensure_system_block(NOTE_BLOCK_ID)
    inst = ms.place_block_instance(NOTE_BLOCK_ID, (-500.0, -300.0), note=dict(NOTE, view=PLAN))
    inst.set_attributes({"Text": "x"})
    _with_definition_leader(ms)
    ms._note_ctl.begin(inst)
    ov = ms._note_ctl.overlay
    assert ov.data.leader is None
    ms._text_edit_ctl.commit()


# -- S3: cursor ---------------------------------------------------------------------

def test_the_note_mode_has_the_text_cursor(shown_model_view, real_system_library):
    view, ms = shown_model_view
    assert view._mode_cursors["note"] == view._mode_cursors["text"] == Qt.CursorShape.CrossCursor
    view.set_crosshair_enabled(False)
    ms.active_view_key = PLAN
    ms.set_mode("note")
    assert view.cursor().shape() == Qt.CursorShape.CrossCursor


# -- S4: constraints -----------------------------------------------------------------

def _fixed_note(ms, view):
    inst = place_note(ms, view)
    ctl = ms.constraint_ctl
    assert ctl.enabled
    c = ctl.add("fix", [{"uid": inst._uid, "h": "item"}], _commit=False)
    assert c is not None and ctl.constraints
    return inst


def test_removing_a_views_notes_cascades_their_constraints(qapp):
    from firepro3d.note_controller import remove_notes
    fx = view_fixture()
    ms = fx["ms"]
    _fixed_note(ms, "detail:D1")
    keep = place_note(ms, PLAN, (900.0, 900.0))
    remove_notes(ms, "detail:D1")
    assert ms.constraint_ctl.constraints == []             # no constraint left naming a dead note
    assert keep in ms._block_instances


def test_dropping_a_views_history_drops_constraints_naming_its_notes(qapp):
    fx = view_fixture()
    ms, det = fx["ms"], fx["det"]
    _fixed_note(ms, "detail:D1")
    ms.push_undo_state()
    assert ms._undo_stack[-1]["constraints"]
    det.delete_detail("D1")
    assert all(not s["constraints"] for s in ms._undo_stack)
    ms.push_undo_state()
    ms.undo()
    assert ms.constraint_ctl.constraints == []
