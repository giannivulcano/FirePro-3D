"""Elevation parity D4 / AC9: Notes owned by a section."""
import os

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.assets import system_blocks_path
from firepro3d.block_library import load_block_file
from tests.test_note_view_scope import place_note
from tests.test_section_classification import _placed_scene


def _note_scene(section_scene_for):
    """A placed section "Section 1" over a model holding the shipped Note block."""
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    ms.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    return ms, sec


def _dispose(win):
    """Close a test window. A Note editor left live by a failing assertion
    would be committed by ``closeEvent`` (marking the project dirty) and raise
    the modal save prompt, hanging the run: end it first."""
    from tests._mainwindow_helpers import dispose_main_window
    win._commit_text_edits()
    dispose_main_window(win)


def _copies(sec):
    from firepro3d.section_scene import _SectionNoteCopy
    return [i for i in sec.items() if isinstance(i, _SectionNoteCopy)]


def test_a_section_note_projects_as_a_copy_in_its_section_only(qapp, section_scene_for):
    """AC9: the note keyed to this section shows here at its stored pose;
    another section's and a plan view's notes do not; plan never shows it."""
    from firepro3d.section_scene import _ROLE_SOURCE
    ms, sec = _note_scene(section_scene_for)
    assert sec.active_view_key == "section:Section 1"
    mine = place_note(ms, "section:Section 1", (3000.0, -2000.0), text="MINE")
    place_note(ms, "section:Other", (3000.0, -2000.0), text="THEIRS")
    place_note(ms, "plan:Plan: Level 1", (3000.0, -2000.0), text="PLAN")
    sec.rebuild()
    (cp,) = _copies(sec)
    assert cp.data(_ROLE_SOURCE) is mine and cp.isVisible()
    assert cp.block_pos() == pytest.approx((3000.0, -2000.0))
    assert cp.attributes["Text"] == "MINE"
    ms.active_view_key = "plan:Plan: Level 1"
    ms._level_manager.apply_to_scene(ms)
    assert not mine.isVisible()                       # plan's view filter, unchanged


def test_dragging_the_copy_moves_the_model_note_in_one_undo_step(qapp, section_scene_for):
    """AC9 / AC11: a manipulator move of the copy lands on the model note,
    one step; rebuild re-projects there; undo puts it back."""
    from tests.test_hosted_blocks_edit import _drag_real
    ms, sec = _note_scene(section_scene_for)
    mine = place_note(ms, "section:Section 1", (3000.0, -2000.0))
    ms.push_undo_state()
    sec.rebuild()
    (cp,) = _copies(sec)
    pos = ms._undo_pos
    _drag_real(sec, [cp], 250.0, -100.0)
    assert mine.block_pos() == pytest.approx((3250.0, -2100.0))
    assert ms._undo_pos == pos + 1
    qapp.processEvents()                              # the deferred flush adds nothing
    assert ms._undo_pos == pos + 1
    sec.rebuild()
    (cp2,) = _copies(sec)
    assert cp2.block_pos() == pytest.approx((3250.0, -2100.0))
    ms.undo()
    sec.rebuild()
    (back,) = _copies(sec)
    assert back.block_pos() == pytest.approx((3000.0, -2000.0))


def test_delete_removes_the_model_note_in_one_step_and_undo_restores(qapp, section_scene_for):
    """AC9 / R2: Delete in the section removes the model note (one step)."""
    ms, sec = _note_scene(section_scene_for)
    mine = place_note(ms, "section:Section 1", (3000.0, -2000.0), text="GONE")
    mine.setVisible(False)                # plan's view filter hides it (a real note is never visible there)
    ms.push_undo_state()
    sec.rebuild()
    (cp,) = _copies(sec)
    cp.setSelected(True)
    pos = ms._undo_pos
    sec._delete_elev_selected()
    assert mine not in ms._block_instances and _copies(sec) == []
    assert ms._undo_pos == pos + 1
    ms.undo()
    sec.rebuild()
    (back,) = _copies(sec)
    assert back.attributes["Text"] == "GONE"


TIP, KNEE, THIRD = QPointF(2000.0, -1500.0), QPointF(2600.0, -2200.0), QPointF(3400.0, -2200.0)


def _arm_and_click(win, view):
    """The ribbon Note button on the section tab, then tip / elbow / box-edge
    clicks posted to the section view."""
    from tests._note_helpers import click
    win._mode_buttons["note"].click()
    assert view.scene().mode == "note"        # S4: the tool entered on the SECTION
    for pt in (TIP, KNEE, THIRD):
        click(view, pt)


def test_note_tool_on_a_section_tab_places_a_section_owned_note(qapp, real_system_library):
    """AC9: the Note button on a section tab arms the tool THERE; three clicks,
    typed text and Esc place ONE model Note keyed to the section, in its 2D
    frame (tip where the click landed), one undo step, never on the plan
    canvas, re-projected after a rebuild."""
    from PyQt6.QtCore import Qt
    from firepro3d.note_controller import notes_of
    from firepro3d.section_scene import _ROLE_SOURCE, _SectionNoteCopy
    from firepro3d.text_item import editing_text_item
    from tests._note_helpers import key
    from tests._section_window_helpers import aim, open_section_window, settle
    win, markers, views = open_section_window(1)
    ms = win.scene
    try:
        view, sec = views[0], views[0].scene()
        settle(sec)
        aim(view, KNEE, 0.25)
        pos = ms._undo_pos
        _arm_and_click(win, view)
        assert ms.mode != "note"                                   # never the hidden plan
        assert editing_text_item(sec) is sec._note_ctl.overlay is not None
        key(view, Qt.Key.Key_H)
        key(view, Qt.Key.Key_I)
        key(view, Qt.Key.Key_Escape)
        assert editing_text_item(sec) is None
        (note,) = notes_of(ms, "section:" + markers[0].name)
        assert note.attributes["Text"] == "hi"
        assert ms._undo_pos == pos + 1                             # place + type = one step
        tip = note.note_tip_scene()
        want = view.mapToScene(view.mapFromScene(TIP))
        tol = 1.5 / view.transform().m11()
        assert (tip.x(), tip.y()) == pytest.approx((want.x(), want.y()), abs=tol)
        win.level_mgr.apply_to_scene(ms)
        assert not note.isVisible()
        settle(sec)
        (cp,) = [i for i in sec.items() if isinstance(i, _SectionNoteCopy)]
        assert cp.data(_ROLE_SOURCE) is note and cp.isVisible()
    finally:
        _dispose(win)


def test_esc_in_the_empty_section_note_editor_leaves_nothing(qapp, real_system_library):
    """AC9 / notes N24: Esc in a new, empty editor -> no note, no undo step."""
    from PyQt6.QtCore import Qt
    from firepro3d.note_controller import notes_of
    from tests._note_helpers import key
    from tests._section_window_helpers import aim, open_section_window, settle
    win, markers, views = open_section_window(1)
    ms = win.scene
    try:
        view, sec = views[0], views[0].scene()
        settle(sec)
        aim(view, KNEE, 0.25)
        pos = ms._undo_pos
        _arm_and_click(win, view)
        key(view, Qt.Key.Key_Escape)
        assert notes_of(ms, "section:" + markers[0].name) == []
        assert ms._undo_pos == pos
        settle(sec)
        assert sec._note_copies == {}
    finally:
        _dispose(win)


def test_arming_note_on_a_section_shows_the_sections_template(qapp, real_system_library):
    """OPEN-3 (integrator): the Note button on a section tab shows THAT
    scene's Note template in the Properties panel (the one its tool places
    with), not the plan scene's.
    RED when: ``getattr(sender, "_note_ctl", None) or`` is dropped from
    ``MainWindow._on_mode_changed_template`` (the panel shows
    ``win.scene._note_ctl.template``)."""
    from PyQt6.QtWidgets import QApplication
    from tests._section_window_helpers import open_section_window, settle
    win, markers, views = open_section_window(1)
    try:
        sec = views[0].scene()
        settle(sec)
        assert sec._note_ctl.template is not win.scene._note_ctl.template   # precondition
        win._mode_buttons["note"].click()
        QApplication.processEvents()
        assert sec.mode == "note"
        assert win.prop_manager._targets == [sec._note_ctl.template]
    finally:
        _dispose(win)


def test_switching_tools_while_editing_a_section_note_keeps_the_text(qapp, real_system_library):
    """OPEN-4 (integrator): a tool switch (the Note button again) while a
    section Note editor is live commits the typed text first, as plan's
    set_mode does: the editor closes and the model note keeps "hi".
    RED when: the ``self._text_edit_ctl.commit()`` line is deleted from
    ``SectionScene.set_mode`` (if Step 0 showed it is needed; else a pin)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from firepro3d.note_controller import notes_of
    from firepro3d.text_item import editing_text_item
    from tests._note_helpers import key
    from tests._section_window_helpers import aim, open_section_window, settle
    win, markers, views = open_section_window(1)
    ms = win.scene
    try:
        view, sec = views[0], views[0].scene()
        settle(sec)
        aim(view, KNEE, 0.25)
        _arm_and_click(win, view)
        key(view, Qt.Key.Key_H)
        key(view, Qt.Key.Key_I)
        assert editing_text_item(sec) is not None                 # precondition: editor live
        # The Editor's Move button is disabled while the editor is live (the
        # editing copy is hidden, so it is not selected): the Note button is
        # the tool switch a user has on a section tab.
        btn = win._mode_buttons["note"]
        assert btn.isEnabled()
        btn.click()
        QApplication.processEvents()
        assert editing_text_item(sec) is None
        (note,) = notes_of(ms, "section:" + markers[0].name)
        assert note.attributes["Text"] == "hi"
    finally:
        _dispose(win)
