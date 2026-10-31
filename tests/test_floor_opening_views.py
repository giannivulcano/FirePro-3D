"""Floor voids in level visibility/z (A1) and in section (A4 section)."""
import pytest
from PyQt6.QtCore import QPointF as P

from firepro3d.floor_slab import FloorSlab
from firepro3d.floor_opening import FloorOpening


def _rect(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


def _slab(scene, pts, void=None, top=3000.0, bottom=None):
    slab = FloorSlab(points=pts)
    slab._top_mode = "absolute"
    slab._top_abs_z_mm = top
    if bottom is not None:
        slab._bottom_mode = "absolute"
        slab._bottom_abs_z_mm = bottom
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    if void is not None:
        op = FloorOpening(void, host=slab)
        slab.add_opening(op)
        scene.addItem(op)
    return slab


def test_void_z_is_pinned_above_its_host(qapp, model_scene):
    scene = model_scene()
    slab = _slab(scene, _rect(0, 0, 4000, 3000), _rect(1000, 1000, 2000, 2000))
    (op,) = slab.openings
    scene._level_manager.apply_to_scene(scene, "Level 1",
                                        view_height=4000.0, view_depth=-1.0)
    # slab z = max(z_range) * Z_ELEV_SCALE + Z_CAT_FLOOR = 3000 * 0.01 + 0.0 = 30.0
    assert slab.zValue() == pytest.approx(30.0)
    # void z = slab z + (Z_CAT_OPENING - Z_CAT_WALL) = 30.0 + (0.35 - 0.30) = 30.05
    assert op.zValue() == pytest.approx(30.05)
    assert slab.isVisible() and op.isVisible()


def test_void_hidden_with_its_host(qapp, model_scene):
    scene = model_scene()
    slab = _slab(scene, _rect(0, 0, 4000, 3000), _rect(1000, 1000, 2000, 2000))
    (op,) = slab.openings
    lm = scene._level_manager
    # z-range (2847.6, 3000) lies wholly above a [-1, 1000] view range
    lm.apply_to_scene(scene, "Level 1", view_height=1000.0, view_depth=-1.0)
    assert not slab.isVisible() and not op.isVisible()
    # back in range, then a Model Browser Hide on the host hides its void too
    lm.apply_to_scene(scene, "Level 1", view_height=4000.0, view_depth=-1.0)
    assert slab.isVisible() and op.isVisible()
    slab._display_overrides["visible"] = False
    lm.apply_to_scene(scene, "Level 1", view_height=4000.0, view_depth=-1.0)
    assert not slab.isVisible() and not op.isVisible()
