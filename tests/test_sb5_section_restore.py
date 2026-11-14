"""SB5 Task 11 -- G-section (Q14b, AC10 restated): two sections with identical
cuts; undoing a rename keeps the same marker object, uid and tab (paired by
uid); undoing a delete brings the marker back with the same uid; the counter's
recount is unchanged."""
import pytest
from PyQt6.QtCore import QPointF


@pytest.fixture
def ms(qapp):
    """The tests/test_section_undo.py fixture: a real SectionManager + tabs."""
    from firepro3d.model_space import Model_Space
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_manager import SectionManager
    s = Model_Space()
    lm = LevelManager(); s._level_manager = lm
    sm = ScaleManager(); s.scale_manager = sm
    s._sb5_tabs = QTabWidget()
    s._section_manager = SectionManager(s, lm, sm, s._sb5_tabs)
    s.push_undo_state()                      # baseline
    return s


def _twins(ms):
    mgr = ms._section_manager
    a = mgr.place_section(QPointF(0, 0), QPointF(5000, 0))
    b = mgr.place_section(QPointF(0, 0), QPointF(5000, 0))   # identical cut
    ms.push_undo_state()
    return mgr, a, b


def test_rename_undo_and_redo_keep_the_marker_by_uid(ms):
    mgr, a, b = _twins(ms)
    view = mgr.open_section("Section 2")
    uid_b = b._uid
    b._rename_with_undo("Stair")
    assert mgr.markers["Stair"] is b
    ms.undo()
    assert mgr.markers["Section 2"] is b and b._uid == uid_b
    assert mgr.markers["Section 1"] is a
    assert mgr.get_view("Section 2") is view
    ms.redo()
    assert mgr.markers["Stair"] is b and mgr.get_view("Stair") is view


def test_move_undo_keeps_the_marker(ms):
    # Coverage only (AC10 move half): GREEN at base and under RED (a) -- names unchanged.
    mgr, a, b = _twins(ms)
    b.apply_grip(1, QPointF(5000, 2000))
    ms.push_undo_state()                     # what the manipulator commit does
    ms.undo()
    assert mgr.markers["Section 2"] is b and b.cut_b == QPointF(5000, 0)
    assert mgr.markers["Section 1"] is a


def test_delete_undo_restores_the_same_uid(ms):
    mgr, a, b = _twins(ms)
    uid_b = b._uid
    b._delete_with_undo()
    assert "Section 2" not in mgr.markers
    ms.undo()
    assert mgr.markers["Section 2"]._uid == uid_b
    assert mgr.markers["Section 1"] is a
    assert mgr.place_section(QPointF(0, 900), QPointF(5000, 900)).name == "Section 3"
