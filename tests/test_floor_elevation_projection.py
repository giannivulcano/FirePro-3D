"""C1 regression: elevation/section view projects floors via the two-boundary
z_range model, NOT the retired single-datum (level.elevation + _level_offset_mm,
fixed _thickness_mm) model.

The projected rect for a slab must place its top edge at ``v_top = -top_z`` and
its bottom edge at ``v_bottom = -bot_z`` (elevation view is Y-down), where
``(bot_z, top_z) == slab._z_range_with_lm(lm)``.

Before the fix, ``_project_floor_slabs`` computed
``z = level.elevation + _level_offset_mm`` and ``thickness = _thickness_mm``,
so any floor with an absolute-Z top, a non-zero offset, an explicit bottom, or
a cross-level span projected at the WRONG elevation/thickness. These tests use
non-trivial two-boundary configs so they FAIL against the retired model and pass
after the fix.
"""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.floor_slab import FloorSlab
from firepro3d.elevation_scene import _ROLE_SOURCE


def _square(size=2000.0):
    return [QPointF(0, 0), QPointF(size, 0), QPointF(size, size), QPointF(0, size)]


def _projected_rect_for(elev, slab):
    """Return the visible (non-mask) projected QGraphicsRectItem for *slab*.

    The visible rect is the one tagged with the slab as _ROLE_SOURCE; the
    opaque mask rect shares its geometry but carries no source ref.
    """
    for it in elev.items():
        if it.data(_ROLE_SOURCE) is slab:
            return it
    return None


def test_absolute_top_and_bottom_project_at_true_z(qapp, elevation_scene_for):
    """Absolute top=3000, absolute bottom=2800 → v_top=-3000, v_bottom=-2800.

    Retired model would have used level.elevation(0) + offset(0) = 0 and
    thickness 150 → v_top=0, v_bottom=150. This asserts the true z_range.
    """
    scene, elev = elevation_scene_for(direction="north")
    slab = FloorSlab(points=_square())
    slab._top_mode = "absolute"
    slab._top_abs_z_mm = 3000.0
    slab._bottom_mode = "absolute"
    slab._bottom_abs_z_mm = 2800.0
    scene.addItem(slab)
    scene._floor_slabs.append(slab)

    # Sanity: the two-boundary resolver agrees with the config.
    assert slab._z_range_with_lm(scene._level_manager) == (2800.0, 3000.0)

    elev.rebuild()
    rect = _projected_rect_for(elev, slab)
    assert rect is not None, "floor slab was not projected into the elevation scene"

    r = rect.rect()
    v_top = r.y()
    v_bottom = r.y() + r.height()
    assert v_top == pytest.approx(-3000.0)     # -top_z
    assert v_bottom == pytest.approx(-2800.0)  # -bot_z
    # Guard against the retired model's answer.
    assert v_top != pytest.approx(0.0)
    assert v_bottom != pytest.approx(150.0)


def test_level_top_with_offset_projects_at_true_z(qapp, elevation_scene_for):
    """Top = Level 2 (3048mm) + 500 offset, thickness bottom 200.

    top_z = 3548, bot_z = 3348. Retired model (level=Level 1 default, offset 0,
    thickness 150) would give v_top=0 / v_bottom=150.
    """
    scene, elev = elevation_scene_for(direction="north")
    slab = FloorSlab(points=_square())
    slab._top_mode = "level"
    slab._top_level = "Level 2"        # default LevelManager: Level 2 @ 3048mm
    slab._top_offset_mm = 500.0
    slab._bottom_mode = "thickness"
    slab._thickness_mm = 200.0
    scene.addItem(slab)
    scene._floor_slabs.append(slab)

    assert slab._z_range_with_lm(scene._level_manager) == (3348.0, 3548.0)

    elev.rebuild()
    rect = _projected_rect_for(elev, slab)
    assert rect is not None

    r = rect.rect()
    v_top = r.y()
    v_bottom = r.y() + r.height()
    assert v_top == pytest.approx(-3548.0)
    assert v_bottom == pytest.approx(-3348.0)


def test_cross_level_span_projects_full_height(qapp, elevation_scene_for):
    """Top = Level 3 (6096), bottom = Level 1 (0): a 6096mm spanning slab.

    Retired model would collapse this to a fixed 150mm rect at z=0.
    """
    scene, elev = elevation_scene_for(direction="north")
    slab = FloorSlab(points=_square())
    slab._top_mode = "level"
    slab._top_level = "Level 3"        # 6096mm
    slab._top_offset_mm = 0.0
    slab._bottom_mode = "level"
    slab._bottom_level = "Level 1"     # 0mm
    slab._bottom_offset_mm = 0.0
    scene.addItem(slab)
    scene._floor_slabs.append(slab)

    assert slab._z_range_with_lm(scene._level_manager) == (0.0, 6096.0)

    elev.rebuild()
    rect = _projected_rect_for(elev, slab)
    assert rect is not None

    r = rect.rect()
    v_top = r.y()
    v_bottom = r.y() + r.height()
    assert v_top == pytest.approx(-6096.0)     # -top_z
    assert v_bottom == pytest.approx(0.0)       # -bot_z
    # Full span, not the retired fixed 150mm thickness.
    assert abs(v_bottom - v_top) == pytest.approx(6096.0)


def test_unresolvable_slab_is_skipped(qapp, elevation_scene_for):
    """A slab whose level-relative top references a missing level resolves to
    None and must be skipped (degenerate-safe), not projected at z=0."""
    scene, elev = elevation_scene_for(direction="north")
    slab = FloorSlab(points=_square())
    slab._top_mode = "level"
    slab._top_level = "NoSuchLevel"
    slab._bottom_mode = "thickness"
    slab._thickness_mm = 150.0
    scene.addItem(slab)
    scene._floor_slabs.append(slab)

    assert slab._z_range_with_lm(scene._level_manager) is None

    elev.rebuild()
    assert _projected_rect_for(elev, slab) is None
