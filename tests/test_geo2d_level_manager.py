"""
test_geo2d_level_manager.py
===========================
Tests that 2D draw geometry (construction geometry) participates in
elevation-based Z-ordering and view-range visibility via
``LevelManager.apply_to_scene``.
"""

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.construction_geometry import RectangleItem
from firepro3d.wall import WallSegment


def _scene(qapp):
    s = Model_Space()
    s._level_manager = LevelManager()
    return s


def _add_rect(s, level="Level 1", offset=0.0):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.level = level
    r._level_offset_mm = offset
    s._draw_rects.append(r)
    s.addItem(r)
    return r


def test_2d_geometry_wins_over_wall_at_equal_elevation(qapp):
    """RectangleItem on Level 1 must have a higher Z than WallSegment at same elevation.

    Constrain the wall's top level to Level 1 so both items sit at elevation 0;
    Z_CAT_CONSTRUCTION > Z_CAT_WALL ensures the rect renders on top.
    """
    s = _scene(qapp)
    r = _add_rect(s)
    w = WallSegment(QPointF(0, 0), QPointF(500, 0))
    w.level = "Level 1"
    w._top_level = "Level 1"  # pin top to same level so max(z_range) = 0 mm
    s._walls.append(w)
    s.addItem(w)
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=2896.0, view_depth=-1000.0
    )
    assert r.zValue() > w.zValue()


def test_visible_on_home_level_default_offset(qapp):
    """RectangleItem at default offset on its own level is visible."""
    s = _scene(qapp)
    r = _add_rect(s)
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=2896.0, view_depth=-1000.0
    )
    assert r.isVisible() is True


def test_hidden_when_offset_pushes_out_of_range(qapp):
    """RectangleItem with a huge offset that places it above view_height is hidden."""
    s = _scene(qapp)
    r = _add_rect(s, offset=5000.0)
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=2896.0, view_depth=-1000.0
    )
    assert r.isVisible() is False


def test_appears_on_adjacent_level_when_in_range(qapp):
    """RectangleItem on Level 1 (elev 0) appears when viewing a range that includes 0."""
    s = _scene(qapp)
    r = _add_rect(s, level="Level 1", offset=0.0)
    # Level 2 is at 3048 mm; view depth=-500 means the range [-500, 3000] includes 0
    s._level_manager.apply_to_scene(
        s, active_level="Level 2", view_height=3000.0, view_depth=-500.0
    )
    assert r.isVisible() is True
