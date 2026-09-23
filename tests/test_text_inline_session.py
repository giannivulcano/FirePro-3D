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
    return s


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
    scene._text_edit_ctl.begin(t)
    _type(t, "Half-typ")
    t.set_property("Font Color", "#ff0000")
    assert scene._undo_stack[-1]["texts"][0]["text"] == "Hello"
    assert scene._text_edit_ctl is not None and t._editing   # panel kept the edit open


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
