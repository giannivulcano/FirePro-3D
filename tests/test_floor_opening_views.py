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


def _section(section_scene_for):
    # Placed cut y = 0 from x = 0 to x = 10000, look_sign +1 (scene-up = look side),
    # depth 4000. ppm 1 and D = (1, 0): h = world x = scene x.
    from tests.test_section_classification import _placed_scene
    return _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)


def _slab_rects(sec, slab, cut):
    from firepro3d.section_scene import _ElevCutRect, _ElevProxyRect, _ROLE_SOURCE
    kind = _ElevCutRect if cut else _ElevProxyRect
    out = [it.rect() for it in sec.items()
           if isinstance(it, kind) and it.data(_ROLE_SOURCE) is slab
           and (cut or not isinstance(it, _ElevCutRect))]
    return sorted(out, key=lambda r: r.x())


def test_section_through_a_void_breaks_the_slab(qapp, section_scene_for):
    from firepro3d.section_marker import ZONE_CUT
    ms, sec = _section(section_scene_for)
    slab = _slab(ms, _rect(2000, -1000, 6000, 1000), _rect(3000, -500, 4000, 500),
                 top=3000.0, bottom=2800.0)
    sec.rebuild()
    assert sec.zone_of(slab) == ZONE_CUT
    rects = _slab_rects(sec, slab, cut=True)
    # material along the cut line: x 2000..3000 and 4000..6000
    assert [(r.x(), r.width()) for r in rects] == [(2000.0, 1000.0), (4000.0, 2000.0)]
    assert all(r.y() == -3000.0 and r.height() == 200.0 for r in rects)   # v = -z


def test_section_cut_void_less_slab_is_one_span(qapp, section_scene_for):
    ms, sec = _section(section_scene_for)
    slab = _slab(ms, _rect(2000, -1000, 6000, 1000), top=3000.0, bottom=2800.0)
    sec.rebuild()
    assert [(r.x(), r.width()) for r in _slab_rects(sec, slab, cut=True)] == [(2000.0, 4000.0)]


def test_behind_slab_extent_is_its_material(qapp, section_scene_for):
    ms, sec = _section(section_scene_for)
    # behind the cut (scene-up); the void crosses the slab's east edge at x = 5000
    slab = _slab(ms, _rect(2000, -3000, 6000, -1000), _rect(5000, -3500, 7000, -500),
                 top=3000.0, bottom=2800.0)
    sec.rebuild()
    (r,) = _slab_rects(sec, slab, cut=False)
    assert (r.x(), r.width()) == pytest.approx((2000.0, 3000.0))   # material x 2000..5000


def test_swallowed_slab_draws_nothing_in_section(qapp, section_scene_for):
    from firepro3d.section_marker import ZONE_HIDDEN
    from tests.test_section_classification import _source_rects
    ms, sec = _section(section_scene_for)
    slab = _slab(ms, _rect(2000, -1000, 6000, 1000), _rect(1900, -1100, 6100, 1100),
                 top=3000.0, bottom=2800.0)
    sec.rebuild()
    assert sec.zone_of(slab) == ZONE_HIDDEN
    assert _source_rects(sec, slab) == []
