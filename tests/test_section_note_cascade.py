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
