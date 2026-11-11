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


def _window_note(text="MMMM"):
    """Shown window, one section tab current, one model Note of that section
    (pose (3000, -2000) in its frame) projected; a baseline undo step."""
    from tests._section_window_helpers import aim, open_section_window, settle
    win, markers, views = open_section_window(1)
    ms = win.scene
    ms.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    note = place_note(ms, "section:" + markers[0].name, (3000.0, -2000.0), text=text)
    note.setVisible(False)
    ms.push_undo_state()
    view, sec = views[0], views[0].scene()
    # The window's 200 ms view-refresh debounce (started by the undo push)
    # would fire mid-test and its section rebuild commits a live Note editor
    # (by design): run it now so the test owns the timing.
    timer = getattr(win, "_view_refresh_timer", None)
    if timer is not None and timer.isActive():
        timer.stop()
        win._refresh_all_views()
    settle(sec)
    cp = sec._note_copies[id(note)]
    aim(view, cp.note_box_scene().center(), 0.5)
    return win, ms, view, sec, note


def test_double_click_edits_the_model_note_text_in_one_step(qapp, real_system_library):
    """AC9 (D13 via D4): double-click the copy -> the editor opens on it; typed
    text lands on the MODEL note's Text; one undo step; undo restores."""
    from PyQt6.QtCore import Qt
    from firepro3d.text_item import editing_text_item
    from tests._note_helpers import dbl, key
    win, ms, view, sec, note = _window_note("MMMM")
    try:
        cp = sec._note_copies[id(note)]
        pos = ms._undo_pos
        dbl(view, cp.note_box_scene().center())
        assert editing_text_item(sec) is sec._note_ctl.overlay is not None
        key(view, Qt.Key.Key_End)
        key(view, Qt.Key.Key_Z)
        key(view, Qt.Key.Key_Escape)
        assert note.attributes["Text"] == "MMMMz"
        assert ms._undo_pos == pos + 1
        ms.undo()                                     # restore re-creates the instances
        from firepro3d.note_controller import notes_of
        (back,) = notes_of(ms, sec.active_view_key)
        assert back.attributes["Text"] == "MMMM"
    finally:
        _dispose(win)


def test_delete_key_on_the_section_tab_removes_the_model_note(qapp, real_system_library):
    """AC9 / R2: the window Delete shortcut on the section tab removes the
    selected copy's model note in one step; undo brings it back to the section."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from firepro3d.note_controller import notes_of
    from tests._section_window_helpers import settle
    win, ms, view, sec, note = _window_note("GONE")
    try:
        key_ = sec.active_view_key
        sec.clearSelection()
        sec._note_copies[id(note)].setSelected(True)
        pos = ms._undo_pos
        QTest.keyClick(win.windowHandle(), Qt.Key.Key_Delete)
        QApplication.processEvents()
        assert notes_of(ms, key_) == []
        assert ms._undo_pos == pos + 1
        ms.undo()
        settle(sec)
        (back,) = notes_of(ms, key_)
        assert sec._note_copies[id(back)].attributes["Text"] == "GONE"
    finally:
        _dispose(win)


def test_plan_paste_refuses_a_section_note_record(qapp, section_scene_for):
    """D4 / R5: a section's Note never pastes onto a plan or detail canvas;
    the user is told why."""
    from firepro3d.model_space import NOTE_SECTION_PASTE_REFUSED
    ms, sec = _note_scene(section_scene_for)
    note = place_note(ms, sec.active_view_key, (3000.0, -2000.0))
    sec.rebuild()
    rec = sec._note_clipboard_record(sec._note_copies[id(note)])
    ms.active_view_key = "plan:Plan: Level 1"
    msgs = []
    ms._show_status = lambda m, *a, **k: msgs.append(m)
    n0 = len(ms._block_instances)
    assert ms.paste_items(QPointF(0.0, 0.0), data=[rec]) == []
    assert ms._add_from_dict(rec) is None
    assert len(ms._block_instances) == n0
    assert msgs[-1] == NOTE_SECTION_PASTE_REFUSED


def test_a_section_note_pastes_into_this_or_another_section_rigidly(qapp, section_scene_for):
    """D4 / R5: pasted in a section, the note joins THAT section, shifted with
    its tip (D7); a plan note record is refused there."""
    from firepro3d.model_space import NOTE_INTO_SECTION_REFUSED
    from firepro3d.section_marker import SectionMarker
    from firepro3d.section_scene import _ROLE_SOURCE, SectionScene
    ms, sec = _note_scene(section_scene_for)
    note = place_note(ms, sec.active_view_key, (3000.0, -2000.0))
    note.note["leader"] = {"edge": "L", "t": 0.5, "shoulder_mm": 5.0,
                           "tip_x": 2500.0, "tip_y": -1500.0, "end": "", "weight": ""}
    sec.rebuild()
    rec = sec._note_clipboard_record(sec._note_copies[id(note)])
    cp = sec._paste_note_record(rec, QPointF(500.0, -100.0))
    new = cp.data(_ROLE_SOURCE)
    assert new is not note and new.note["view"] == sec.active_view_key
    assert new.block_pos() == pytest.approx((3500.0, -2100.0))
    assert (new.note["leader"]["tip_x"], new.note["leader"]["tip_y"]) == pytest.approx(
        (3000.0, -1600.0))
    assert (note.note["leader"]["tip_x"], note.note["leader"]["tip_y"]) == (2500.0, -1500.0)
    m2 = SectionMarker("Section 2", QPointF(0, 0), QPointF(10000, 0), 1, 8000.0)
    sec2 = SectionScene(m2, ms, ms._level_manager, ms.scale_manager)
    cp2 = sec2._paste_note_record(rec, QPointF(0.0, 0.0))
    assert cp2.data(_ROLE_SOURCE).note["view"] == "section:Section 2"
    msgs = []
    sec2._show_status = lambda m, *a, **k: msgs.append(m)
    plan_rec = place_note(ms, "plan:Plan: Level 1", (0.0, 0.0)).to_dict()
    assert sec2._paste_note_record(plan_rec, QPointF(0.0, 0.0)) is None
    assert msgs[-1] == NOTE_INTO_SECTION_REFUSED


def test_ctrl_c_v_carries_a_section_note_into_a_parallel_section(qapp, real_system_library):
    """AC9 + R4/R5 through the real keys: Ctrl+C (base click) on a Note copy in
    section 1, Ctrl+V (click) on section 2's tab -> a new model note keyed to
    section 2; a plan paste of the same clipboard is refused."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from firepro3d.note_controller import notes_of
    from tests._note_helpers import click
    from tests._section_window_helpers import aim, open_section_window, settle, show_tab
    win, markers, views = open_section_window(2)
    ms = win.scene
    try:
        ms.register_block_definition(load_block_file(
            os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
        k1, k2 = ("section:" + m.name for m in markers)
        note = place_note(ms, k1, (3000.0, -2000.0))
        note.setVisible(False)
        ms.push_undo_state()
        # The window's 200 ms view-refresh debounce would rebuild mid-test:
        # run it now so the test owns the timing.
        timer = getattr(win, "_view_refresh_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
            win._refresh_all_views()
        sec1, sec2 = views[0].scene(), views[1].scene()
        settle(sec1)
        settle(sec2)
        sec1.clearSelection()
        sec1._note_copies[id(note)].setSelected(True)
        base = QPointF(3000.0, -2000.0)
        aim(views[0], base, 0.5)
        QTest.keyClick(win.windowHandle(), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        click(views[0], base)
        show_tab(win, views[1])
        dest = QPointF(4000.0, -2000.0)
        aim(views[1], dest, 0.5)
        QTest.keyClick(win.windowHandle(), Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        click(views[1], dest)
        (pasted,) = notes_of(ms, k2)
        assert pasted.block_pos()[0] - 3000.0 == pytest.approx(1000.0, abs=50.0)
        assert notes_of(ms, k1) == [note]
        n0 = len(ms._block_instances)
        assert ms.paste_items(QPointF(0.0, 0.0)) == []          # plan, from the real clipboard
        assert len(ms._block_instances) == n0
    finally:
        _dispose(win)


def _place_by_tool(win, view):
    """Place a Note reading "hi" through the real Note tool on *view* (E-10 flow)."""
    from PyQt6.QtCore import Qt
    from tests._note_helpers import key
    _arm_and_click(win, view)
    for k in (Qt.Key.Key_H, Qt.Key.Key_I, Qt.Key.Key_Escape):
        key(view, k)


def test_a_section_note_persists_and_shows_only_in_its_section(qapp, real_system_library, tmp_path):
    """AC9: save / reopen through the real open path keeps the note keyed to
    its section; it re-projects there, not in the parallel section, not on
    the plan canvas."""
    from firepro3d.note_controller import notes_of
    from firepro3d.section_scene import _ROLE_SOURCE
    from tests._section_window_helpers import aim, open_section_window, settle
    win, markers, views = open_section_window(2)
    ms = win.scene
    n1, n2 = markers[0].name, markers[1].name
    try:
        view, sec = views[0], views[0].scene()
        settle(sec)
        aim(view, KNEE, 0.25)
        _place_by_tool(win, view)
        assert len(notes_of(ms, "section:" + n1)) == 1
        path = str(tmp_path / "notes.fpd")
        assert ms.save_to_file(path, backup=False)
        win._load_project(path)                                  # the real open path
        (note,) = notes_of(win.scene, "section:" + n1)
        assert note.attributes["Text"] == "hi"
        assert not note.isVisible()                              # never on the plan canvas
        s1 = win.section_manager.open_section(n1).scene()
        s2 = win.section_manager.open_section(n2).scene()
        settle(s1)
        settle(s2)
        assert [c.data(_ROLE_SOURCE) for c in s1._note_copies.values()] == [note]
        assert s2._note_copies == {}                             # absent from the parallel section
    finally:
        _dispose(win)


def test_a_section_note_plots_on_a_sheet_of_that_section(qapp, real_system_library, tmp_path):
    """AC9 / D4: with the tab closed, the sheet resolver builds the section
    tab-less (get_or_build_scene) and the note's leader plots on the page."""
    from PyQt6.QtCore import QRectF
    from firepro3d.note_controller import notes_of
    from tests._section_paper_helpers import drawings, export_scene, to_paper
    from tests._section_window_helpers import aim, open_section_window, settle
    win, markers, views = open_section_window(1)
    ms = win.scene
    name = markers[0].name
    try:
        view, sec = views[0], views[0].scene()
        settle(sec)
        aim(view, KNEE, 0.25)
        _place_by_tool(win, view)
        (note,) = notes_of(ms, "section:" + name)
        win.section_manager.close_section(name)                 # sheets build tab-less (s7.2)
        scene, _rect = win._view_resolver.resolve("section", name)
        assert scene is not sec
        (cp,) = scene._note_copies.values()
        tip, knee = note.note_tip_scene(), note._note_knee_scene()
        region = QRectF(tip, knee).normalized().united(cp.note_box_scene())
        scale = 1.0 / ms.scale_manager.drawing_scale            # plot at the drawing scale
        pdf = export_scene(tmp_path, scene, scale, knee, "section_note_sheet.pdf")
        x0, y0 = to_paper(region.topLeft(), knee, scale)
        x1, y1 = to_paper(region.bottomRight(), knee, scale)
        pad = 1.0
        inside = [d for d in drawings(pdf)
                  if "s" in d["type"]
                  and d["rect"][0] >= x0 - pad and d["rect"][2] <= x1 + pad
                  and d["rect"][1] >= y0 - pad and d["rect"][3] <= y1 + pad
                  and max(d["rect"][2] - d["rect"][0], d["rect"][3] - d["rect"][1]) > 2.0]
        assert inside, "the note's leader / frame did not plot"
    finally:
        _dispose(win)
