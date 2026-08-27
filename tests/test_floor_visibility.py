"""
test_floor_visibility.py
========================
Task 3 (floor-workflow-elevation-model): floors retire their owning
``.level`` and drive visibility purely by z-range.

These tests build a REAL ``LevelManager`` + ``Model_Space`` (mirroring
``tests/test_geo2d_level_manager.py``) and add ``FloorSlab`` items to
``scene._floor_slabs``, then call ``apply_to_scene`` and assert visibility
by z-range only (never by ``.level``).

They also cover rename remap of a floor's boundary level refs.
"""

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.floor_slab import FloorSlab


# ── Harness (mirror of test_geo2d_level_manager.py) ─────────────────────────

def _scene(qapp):
    s = Model_Space()
    s._level_manager = LevelManager()
    return s


def _add_slab(s, points=None):
    """Add a default FloorSlab (top=Level 1 +0, bottom=thickness 152.4)."""
    if points is None:
        points = [QPointF(0, 0), QPointF(1000, 0),
                  QPointF(1000, 1000), QPointF(0, 1000)]
    slab = FloorSlab(points)
    s._floor_slabs.append(slab)
    s.addItem(slab)
    return slab


# A default slab: top = Level 1 (elev 0) + 0, bottom = thickness 152.4
#   → z-range = (-152.4, 0.0)
# Level 2 sits at 3048 mm by default.


def test_floor_visible_when_zrange_in_view(qapp):
    """Default slab (z-range (-152.4, 0)) is visible in a Level 1 plan view."""
    s = _scene(qapp)
    slab = _add_slab(s)
    assert slab.z_range_mm() == pytest.approx((-152.4, 0.0))
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=2895.6, view_depth=-1000.0
    )
    assert slab.isVisible() is True


def test_floor_hidden_when_zrange_above_view(qapp):
    """A slab whose z-range is entirely above view_height is hidden."""
    s = _scene(qapp)
    slab = _add_slab(s)
    # Push the slab's top boundary up to Level 3 (elev 6096) so its whole
    # z-range (5943.6, 6096) sits well above a Level 1 plan view.
    slab._top_level = "Level 3"
    assert slab.z_range_mm() == pytest.approx((5943.6, 6096.0))
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=2895.6, view_depth=-1000.0
    )
    assert slab.isVisible() is False


def test_floor_visible_regardless_of_dot_level(qapp):
    """A slab whose z-range intersects the view is visible even when its
    ``.level`` names a non-active level — proving ``.level`` is ignored."""
    s = _scene(qapp)
    slab = _add_slab(s)
    slab.level = "Some Other Level"  # NOT the active level, NOT a real level
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=2895.6, view_depth=-1000.0
    )
    assert slab.isVisible() is True


def test_cross_level_span_visible_from_both(qapp):
    """A span floor (top=Level 2, bottom=Level 1) is visible from either
    adjacent plan whose view range intersects its z-range."""
    s = _scene(qapp)
    slab = _add_slab(s)
    slab._top_mode = "level"
    slab._top_level = "Level 2"      # elev 3048
    slab._top_offset_mm = 0.0
    slab._bottom_mode = "level"
    slab._bottom_level = "Level 1"   # elev 0
    slab._bottom_offset_mm = 0.0
    assert slab.z_range_mm() == pytest.approx((0.0, 3048.0))

    # From Level 1 plan (range [-1000, 2895.6]) — intersects (0, 3048)
    s._level_manager.apply_to_scene(
        s, active_level="Level 1", view_height=2895.6, view_depth=-1000.0
    )
    assert slab.isVisible() is True

    # From Level 2 plan (range [2048, 5943.6]) — intersects (0, 3048)
    s._level_manager.apply_to_scene(
        s, active_level="Level 2", view_height=5943.6, view_depth=2048.0
    )
    assert slab.isVisible() is True


def test_rename_remaps_boundary_levels(qapp):
    """After rename_level, a floor's _top_level / _bottom_level following the
    old name are updated to the new name."""
    s = _scene(qapp)
    slab = _add_slab(s)
    slab._top_mode = "level"
    slab._top_level = "Level 2"
    slab._bottom_mode = "level"
    slab._bottom_level = "Level 2"

    ok = s._level_manager.rename_level("Level 2", "L2", items=[], scene=s)
    assert ok is True
    assert slab._top_level == "L2"
    assert slab._bottom_level == "L2"


def test_rename_does_not_touch_floor_dot_level(qapp):
    """Rename must not rewrite a floor's owning ``.level`` (floors are
    excluded from the generic .level loop)."""
    s = _scene(qapp)
    slab = _add_slab(s)
    slab.level = "Level 2"  # stale owning level that must NOT be remapped

    s._level_manager.rename_level("Level 2", "L2", items=[slab], scene=s)
    assert slab.level == "Level 2"
