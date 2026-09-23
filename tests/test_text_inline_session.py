"""Inline-edit session contract (spec: text-annotation-system § Inline edit):
one undo step per session, empty handling, commit triggers, focus policy."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QFocusEvent
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget


@pytest.fixture
def scene(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    s.push_undo_state()                     # baseline so undo() can step back
    yield s
    import gc
    from firepro3d.text_item import editing_text_item
    ed = editing_text_item(s)
    if ed is not None:
        # A test that left an inline-edit session live must not leak the
        # TextItem's caret QTimer / scene._editing_item marker into the next
        # test's process state — abandon (not commit), the test already made
        # its assertions.
        s._text_edit_ctl.abandon(ed)
    QApplication.processEvents()
    gc.collect()


def _add(scene, text="Hello"):
    from firepro3d.text_item import TextItem, TextAnnotationData
    d = TextAnnotationData(text=text, x=0.0, y=0.0, height_mm=40.0, wrap_width_mm=600.0)
    d.color = "#ffffff"
    t = TextItem(d)
    scene.addItem(t)
    scene._texts.append(t)
    t._apply_format()
    # Snapshot the box onto the undo stack so it is present in the "one step
    # back" state a later undo() restores to (parity with a real placement,
    # which always commits through push_undo_state before an edit can begin).
    scene.push_undo_state()
    return t


def _type(t, s):
    t.setPlainText(s)          # stands in for keystrokes (routing tested in Task 4)


def test_predicate_tracks_session(scene):
    from firepro3d.text_item import editing_text_item
    t = _add(scene)
    assert editing_text_item(scene) is None
    scene._text_edit_ctl.begin(t)
    assert editing_text_item(scene) is t
    scene.commit_text_edit()
    assert editing_text_item(scene) is None


def test_edit_commit_is_one_undo_step(scene):
    t = _add(scene)
    n = len(scene._undo_stack)
    scene._text_edit_ctl.begin(t)
    _type(t, "World")
    scene.commit_text_edit()
    assert len(scene._undo_stack) == n + 1
    assert scene._undo_stack[-1]["texts"][0]["text"] == "World"


def test_noop_edit_pushes_nothing(scene):
    t = _add(scene)
    n = len(scene._undo_stack)
    scene._text_edit_ctl.begin(t)
    scene.commit_text_edit()
    assert len(scene._undo_stack) == n


def test_emptied_existing_box_is_deleted_as_one_step(scene):
    t = _add(scene)
    n = len(scene._undo_stack)
    scene._text_edit_ctl.begin(t)
    _type(t, "   ")
    scene.commit_text_edit()
    assert scene._texts == []
    assert len(scene._undo_stack) == n + 1
    scene.undo()
    assert [x.data.text for x in scene._texts] == ["Hello"]


def test_new_placement_starts_empty_and_is_one_step(scene):
    n = len(scene._undo_stack)
    scene.set_mode("text")
    scene._press_text(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    scene._press_text(None, QPointF(400, 200), QPointF(400, 200), None, None, None)
    t = scene._texts[-1]
    assert t.toPlainText() == ""
    assert len(scene._undo_stack) == n          # no placement snapshot yet
    _type(t, "Note")
    scene.commit_text_edit()
    assert len(scene._undo_stack) == n + 1
    scene.undo()
    assert scene._texts == []                   # one Ctrl+Z removes place+type


def test_empty_new_placement_is_discarded_without_step(scene):
    n = len(scene._undo_stack)
    scene.set_mode("text")
    scene._press_text(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    scene._press_text(None, QPointF(400, 200), QPointF(400, 200), None, None, None)
    scene.commit_text_edit()
    assert scene._texts == []
    assert len(scene._undo_stack) == n


def test_midedit_panel_change_does_not_bake_typed_text(scene):
    t = _add(scene)
    n = len(scene._undo_stack)
    scene._text_edit_ctl.begin(t)
    _type(t, "Half-typ")
    t.set_property("Font Color", "#ff0000")
    assert len(scene._undo_stack) == n + 1                    # exactly one step
    assert scene._undo_stack[-1]["texts"][0]["text"] == "Hello"
    assert t.toPlainText() == "Half-typ"                      # typed text survives, un-baked
    assert scene._text_edit_ctl is not None and t._editing   # panel kept the edit open


def test_stale_panel_content_replay_does_not_wipe_live_typing(scene):
    """I3: the property-panel Content box re-emits its stale (pre-edit)
    ``_data.text`` on every focus-out (``_MultilineEdit``), including a click
    back onto the canvas while an inline edit is live. That stale value must
    NOT stomp the live-typed document — ``_set_property_model`` skips the
    ``setPlainText``/data write when the incoming value already equals
    ``_data.text`` (the panel is repeating what it already showed, not
    authoring a real change)."""
    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    _type(t, "XYZ")
    stale = t.data.text                    # "Hello" — unwritten until commit
    assert stale == "Hello" and t.toPlainText() == "XYZ"
    t.set_property("Content", stale)
    assert t.toPlainText() == "XYZ", "stale panel replay wiped the live document"
    assert t._editing, "the stale replay must not end the session either"


def test_set_mode_commits(scene):
    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    _type(t, "X")
    scene.set_mode("select")
    assert not t._editing and t.data.text == "X"


def test_undo_while_editing_commits_first(scene):
    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    _type(t, "X")
    scene.undo()                                # commit pushes, undo reverts it
    from firepro3d.text_item import editing_text_item
    assert editing_text_item(scene) is None
    assert [x.data.text for x in scene._texts] == ["Hello"]


def test_delete_during_edit_ends_session_cleanly(scene):
    from firepro3d.text_item import editing_text_item
    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    scene._delete_single_item(t)
    assert editing_text_item(scene) is None
    assert t._caret_timer is None or not t._caret_timer.isActive()


def test_rebegin_on_live_new_placement_keeps_is_new(scene):
    """A second `begin()` call on the item that is ALREADY the live session
    (e.g. a second click landing back on the freshly-placed, still-empty box)
    must only reposition the caret — it must not reset `_edit_before`/
    `_edit_is_new`, or the box's "new placement, discard-if-empty" rule would
    be lost and an empty commit would wrongly push an undo step."""
    n = len(scene._undo_stack)
    scene.set_mode("text")
    scene._press_text(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    scene._press_text(None, QPointF(400, 200), QPointF(400, 200), None, None, None)
    t = scene._texts[-1]
    assert t._edit_is_new is True
    scene._text_edit_ctl.begin(t)            # re-begin on the already-live item
    assert t._edit_is_new is True            # not clobbered back to False
    scene.commit_text_edit()
    assert scene._texts == []                # still discarded (empty, new)
    assert len(scene._undo_stack) == n       # ...and still with no undo step


def test_undo_after_discarded_placement_is_noop(scene):
    """Ctrl+Z / ribbon Undo right after (or during) an empty new placement is
    ALREADY handled by the commit-first discard — it must just cancel the
    placement, not ALSO step the undo stack back into unrelated prior
    history, since nothing was ever pushed for the discarded item."""
    t = _add(scene)                          # a real, tracked, pushed box
    stack_before = list(scene._undo_stack)
    pos_before = scene._undo_pos
    scene.set_mode("text")
    scene._press_text(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    scene._press_text(None, QPointF(400, 200), QPointF(400, 200), None, None, None)
    scene.undo()                             # commit discards the empty placement
    assert scene._undo_stack == stack_before
    assert scene._undo_pos == pos_before
    assert [x.data.text for x in scene._texts] == ["Hello"]


def test_redo_after_discarded_placement_is_noop(scene):
    """Redo right after (or during) an empty new placement is ALREADY handled
    by the commit-first discard — it must just cancel the placement, not ALSO
    step the undo stack forward into unrelated later history, since nothing
    was ever pushed for the discarded item (mirrors
    ``test_undo_after_discarded_placement_is_noop``)."""
    t = _add(scene)                          # a real, tracked, pushed box
    scene.undo()                             # step back so a redo target exists
    stack_before = list(scene._undo_stack)
    pos_before = scene._undo_pos
    scene.set_mode("text")
    scene._press_text(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    scene._press_text(None, QPointF(400, 200), QPointF(400, 200), None, None, None)
    scene.redo()                             # commit discards the empty placement
    assert scene._undo_stack == stack_before
    assert scene._undo_pos == pos_before


def test_redo_commits_first(scene):
    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    _type(t, "X")
    scene.redo()                                # commit pushes the edit first
    from firepro3d.text_item import editing_text_item
    assert editing_text_item(scene) is None
    assert t.data.text == "X"


# ── Focus policy (needs a shown view so focus is real) ─────────────────────

def test_window_deactivation_keeps_edit(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    scene.sendEvent(t, QFocusEvent(QEvent.Type.FocusOut,
                                   Qt.FocusReason.ActiveWindowFocusReason))
    assert t._editing


def test_focus_to_other_widget_commits(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    _type(t, "Y")
    le = QLineEdit(view)
    le.show()
    le.setFocus(Qt.FocusReason.MouseFocusReason)
    QApplication.processEvents()
    assert not t._editing and t.data.text == "Y"


def test_focus_within_own_view_keeps_edit(shown_model_view):
    """A focus change that stays on the scene's own view/viewport — e.g. a
    manipulator grip grabbing item-level focus in the same widget — must not
    end the session (only a WIDGET-level focus move elsewhere commits)."""
    view, scene = shown_model_view
    scene.scene_role = "block_editor"
    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    _type(t, "Z")
    assert QApplication.focusWidget() in (view, view.viewport())
    scene.sendEvent(t, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason))
    assert t._editing


def test_focus_to_property_panel_keeps_edit(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"

    class PropertyManager(QWidget):           # name-matched panel stand-in
        pass

    t = _add(scene)
    scene._text_edit_ctl.begin(t)
    pm = PropertyManager(view)
    le = QLineEdit(pm)
    pm.show()
    le.setFocus(Qt.FocusReason.MouseFocusReason)
    QApplication.processEvents()
    assert t._editing
