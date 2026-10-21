"""Acceptance (e): marker place / grip move / flip / delete are undoable through
Model_Space.undo(); an open section tab is left alone (spec s8)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.section_marker import SectionMarker


@pytest.fixture
def ms(qapp):
    from firepro3d.model_space import Model_Space
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_manager import SectionManager
    s = Model_Space()
    lm = LevelManager(); s._level_manager = lm
    sm = ScaleManager(); s.scale_manager = sm
    s._section_manager = SectionManager(s, lm, sm, QTabWidget())     # the real manager (G4)
    s.push_undo_state()                      # baseline
    return s


def test_place_is_undoable(ms):
    mgr = ms._section_manager
    mgr.place_section(QPointF(0, 0), QPointF(5000, 0)); ms.push_undo_state()
    assert "Section 1" in mgr.markers
    ms.undo()
    assert mgr.markers == {}
    ms.redo()
    assert "Section 1" in mgr.markers


def test_grip_move_is_undoable(ms):
    mgr = ms._section_manager
    m = mgr.place_section(QPointF(0, 0), QPointF(5000, 0)); ms.push_undo_state()
    m.apply_grip(1, QPointF(5000, 2000)); ms.push_undo_state()     # what the manipulator commit does
    ms.undo()
    assert mgr.markers["Section 1"].cut_b == QPointF(5000, 0)


def test_flip_is_undoable(ms):
    mgr = ms._section_manager
    m = mgr.place_section(QPointF(0, 0), QPointF(5000, 0)); ms.push_undo_state()
    m._flip_with_undo()
    assert mgr.markers["Section 1"].look_sign == -1
    ms.undo()
    assert mgr.markers["Section 1"].look_sign == 1


def test_delete_is_undoable_and_survivor_identity_kept(ms):
    mgr = ms._section_manager
    keep = mgr.place_section(QPointF(0, 0), QPointF(5000, 0))
    mgr.place_section(QPointF(0, 1000), QPointF(5000, 1000)); ms.push_undo_state()
    mgr.delete_section("Section 2"); ms.push_undo_state()
    ms.undo()
    assert set(mgr.markers) == {"Section 1", "Section 2"}
    assert mgr.markers["Section 1"] is keep                      # survivor updated in place, not rebuilt


def test_snapshot_without_manager_has_no_sections_key(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    assert "sections" not in s._capture_network()
