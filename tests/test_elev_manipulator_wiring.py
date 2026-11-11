"""U5 Leg B — SelectionManipulator wraps elevation gridline/datum.

Drives ElevationScene selection through the shared SelectionManipulator (the
sole grip owner after the legacy _find_grip_hit path is retired). Uses the
``section_scene_for`` fixture (real Model_Space + LevelManager + ScaleManager)
from conftest.py — no full MainWindow.
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from firepro3d.section_scene import ElevGridlineItem


def _grid(label="A", h=100.0):
    return ElevGridlineItem(h, -50.0, 50.0, label, QColor("#888"), 1.0)


def test_manipulator_wraps_selected_gridline(qapp, section_scene_for):
    _ms, elev = section_scene_for("north")
    g = _grid()
    elev.addItem(g)

    assert elev._live_manip() is not None
    g.setSelected(True)

    manip = elev._live_manip()
    assert manip is not None
    assert manip.isVisible()
    # gridline surfaces its two extent grips (top/bottom), no rigid resize set
    assert len(manip._active_handles()) == 2


def test_gridline_grip_drag_commits_override(qapp, section_scene_for):
    from firepro3d.gridline import GridlineItem
    _ms, elev = section_scene_for("north")
    plan = GridlineItem(QPointF(0.0, -1000.0), QPointF(0.0, 1000.0), label="G7")
    g = ElevGridlineItem(100.0, -50.0, 50.0, "G7", QColor("#888"), 1.0, gridline=plan)
    elev.addItem(g)
    g.setSelected(True)

    # Simulate a grip drag: move endpoint 1 (bottom) then fire the commit hook
    # the manipulator invokes on release.
    g.apply_grip(1, QPointF(999.0, 80.0))   # x ignored (H pinned), extent moves
    elev._commit_elev_grip("move")

    assert g._label == "G7"
    assert "G7" not in elev._gridline_z_overrides             # uid-keyed (D7)
    ov = elev._gridline_z_overrides[plan._uid]
    assert ov["v_top"] == -50.0
    assert ov["v_bot"] == 80.0


def test_detached_gridline_commits_nothing(qapp, section_scene_for):
    """No plan gridline = no uid to key by: the commit writes no record."""
    _ms, elev = section_scene_for("north")
    g = _grid(label="G8")
    elev.addItem(g)
    g.setSelected(True)
    g.apply_grip(1, QPointF(999.0, 80.0))
    elev._commit_elev_grip("move")
    assert elev._gridline_z_overrides == {}


def test_manipulator_constructed_once(qapp, section_scene_for):
    _ms, elev = section_scene_for("north")
    m1 = elev._live_manip()
    m2 = elev._live_manip()
    assert m1 is m2   # same live instance; not rebuilt per call
