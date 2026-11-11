"""Elevation parity D4 / AC9: section Notes follow a section rename / delete."""
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QInputDialog

from tests.test_section_persistence import _scene_with_manager


def _trigger(marker, text):
    """Trigger the marker context-menu action *text*; the menu is held for
    the call (an unreferenced QMenu deletes its actions)."""
    menu = marker.build_context_menu()
    next(a for a in menu.actions() if a.text() == text).trigger()


def _section(qapp):
    """A real Model_Space + SectionManager with one placed section and a
    baseline undo step holding it."""
    ms, mgr = _scene_with_manager(qapp)
    m = mgr.place_section(QPointF(0.0, 0.0), QPointF(10000.0, 0.0))
    ms.push_undo_state()
    return ms, mgr, m


def test_probe_marker_rename_and_delete_are_one_undo_step_each(qapp, monkeypatch):
    """Step-1 probe P-E1: the marker menu's Rename and Delete each push ONE
    post-action step, and undo restores the marker. So the note cascade runs
    inside that step (rekey_notes / remove_notes), never rekey_history /
    drop_history (the detail-view precedent is for paths with no step)."""
    ms, mgr, m = _section(qapp)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Riser", True))
    pos = ms._undo_pos
    _trigger(m, "Rename")
    assert m.name == "Riser" and ms._undo_pos == pos + 1
    ms.undo()
    assert "Section 1" in mgr.markers and "Riser" not in mgr.markers
    m = mgr.markers["Section 1"]
    pos = ms._undo_pos
    _trigger(m, "Delete")
    assert "Section 1" not in mgr.markers and ms._undo_pos == pos + 1
    ms.undo()
    assert "Section 1" in mgr.markers


import os

from firepro3d.assets import system_blocks_path
from firepro3d.block_library import load_block_file
from firepro3d.note_controller import notes_of
from tests.test_note_view_scope import place_note


def _section_with_note(qapp):
    ms, mgr, m = _section(qapp)
    ms.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    note = place_note(ms, "section:Section 1", (3000.0, -2000.0), text="KEEP")
    ms.push_undo_state()
    return ms, mgr, m, note


def test_rename_rekeys_the_sections_notes_and_undo_restores(qapp, monkeypatch):
    """AC9: marker menu Rename -> the note follows (shown in the renamed
    section's scene); undo puts name and key back together."""
    from firepro3d.section_scene import _SectionNoteCopy
    ms, mgr, m, note = _section_with_note(qapp)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Riser", True))
    _trigger(m, "Rename")
    assert note.note["view"] == "section:Riser"
    sc = mgr.get_or_build_scene("Riser")
    sc.rebuild()
    assert [i for i in sc.items() if isinstance(i, _SectionNoteCopy)]
    ms.undo()
    (back,) = notes_of(ms, "section:Section 1")
    assert back.attributes["Text"] == "KEEP" and "Section 1" in mgr.markers


def test_delete_removes_the_sections_notes_and_undo_restores(qapp):
    """AC9: marker menu Delete -> the section's notes go in the same step;
    undo restores marker and notes."""
    ms, mgr, m, note = _section_with_note(qapp)
    other = place_note(ms, "section:Elsewhere", (0.0, 0.0), text="STAY")
    pos = ms._undo_pos
    _trigger(m, "Delete")
    assert notes_of(ms, "section:Section 1") == []
    assert other in ms._block_instances                    # another view's note untouched
    assert ms._undo_pos == pos + 1
    ms.undo()
    (back,) = notes_of(ms, "section:Section 1")
    assert back.attributes["Text"] == "KEEP" and "Section 1" in mgr.markers


def test_project_browser_delete_removes_the_notes_too(qapp):
    """AC9, the other delete entry: Project Browser Delete (main
    _delete_section_view) removes the section's notes in its one step."""
    from tests._mainwindow_helpers import dispose_main_window
    from tests.test_section_manager import _main_window
    win = _main_window()
    ms = win.scene
    try:
        ms.register_block_definition(load_block_file(
            os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
        m = win.section_manager.place_section(QPointF(0.0, 0.0), QPointF(10000.0, 0.0))
        place_note(ms, "section:" + m.name, (3000.0, -2000.0), text="KEEP")
        ms.push_undo_state()
        pos = ms._undo_pos
        win.project_browser.deleteSectionView.emit(m.name)
        assert notes_of(ms, "section:" + m.name) == []
        assert ms._undo_pos == pos + 1
        ms.undo()
        assert len(notes_of(ms, "section:" + m.name)) == 1
    finally:
        dispose_main_window(win)
