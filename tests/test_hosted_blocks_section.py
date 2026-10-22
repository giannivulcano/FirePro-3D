"""D8: hosted blocks drawn in parallel sections (AC3-AC6)."""
import pytest
from firepro3d.block_instance import BlockInstance
from tests._hosted_blocks_helpers import gridline, defn
from tests.test_section_classification import _placed_scene


def _copies(sec):
    return [it for it in sec.items() if isinstance(it, BlockInstance)]


def _host(ms, gl, **kw):
    d = defn(ms)
    h = {"gridline": gl._uid, "offset_mm": 0.0, "along_mm": 1000.0,
         "elevation_mm": 500.0, "facing": 1}
    h.update(kw)
    return ms.place_block_instance(d.id, (0, 0), host=h)


def test_drawn_head_on_absent_perpendicular(qapp, section_scene_for):
    # cut (0,0)->(10000,0) world, look +y (N=(0,1)), depth 8000
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")       # world y=3000
    src = _host(ms, gl)
    assert not src.isVisible()                               # T6: hidden in plan
    sec.rebuild()
    (cp,) = _copies(sec)
    assert cp.data(0x0100) is src                            # _ROLE_SOURCE = UserRole
    assert cp.scene() is sec
    assert cp.isVisible()                                    # not derived from the model block
    assert cp.block_pos() == pytest.approx((1000.0, -500.0))
    assert cp.block_mirrored() is False
    perp = gridline(ms, (500, 0), (500, -6000), "1")
    src.host["gridline"] = perp._uid
    sec.rebuild()
    assert _copies(sec) == []


def test_back_view_mirrored(qapp, section_scene_for):
    # marker points are plan-SCENE coords (Y-down): (10000,-6000)->(0,-6000) is
    # world y=6000, D=(-1,0), N=(0,-1); gl at world y=3000 is d=3000
    ms, sec = _placed_scene(section_scene_for, (10000, -6000), (0, -6000), 8000.0)
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    _host(ms, gl)
    sec.rebuild()
    (cp,) = _copies(sec)
    assert cp.block_mirrored() is True
    assert cp.block_pos()[0] == pytest.approx(-1000.0)


@pytest.mark.parametrize("offset,shown", [(-3500.0, False), (0.0, True),
                                          (5500.0, False)])
def test_depth_crop(qapp, section_scene_for, offset, shown):
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    _host(ms, gl, offset_mm=offset)          # d = 3000 + offset
    sec.rebuild()
    assert bool(_copies(sec)) is shown


def test_depth_order_between_walls(qapp, section_scene_for):
    """The nearer hosted copy paints above the farther one (sort_key order),
    inside the depth band below the gridlines (Z 50)."""
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")        # d = 3000
    near = _host(ms, gl, offset_mm=0.0, along_mm=1000.0)     # d = 3000
    far = _host(ms, gl, offset_mm=2000.0, along_mm=2000.0)   # d = 5000
    sec.rebuild()
    z = {c.data(0x0100): (c.parentItem() or c).zValue() for c in _copies(sec)}
    assert -50.0 <= z[far] < z[near] < 50.0


def test_lateral_clip(qapp, section_scene_for):
    """Blocks straddling h_max and h_min are clipped at BOTH edges: Qt reports
    each copy clipped, and its clip path is the [h_min, h_max] box."""
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gl = gridline(ms, (0, -3000), (12000, -3000), "B")
    _host(ms, gl, along_mm=9950.0)                            # 100 mm line crosses h_max=10000
    _host(ms, gl, along_mm=-50.0)                             # crosses h_min=0
    sec.rebuild()
    cps = _copies(sec)
    assert len(cps) == 2
    b = sec.basis
    for cp in cps:
        assert cp.isClipped()                                 # Qt: an ancestor clips it
        clip = cp.parentItem()
        assert clip.rect().left() == pytest.approx(b.h_min)
        assert clip.rect().right() == pytest.approx(b.h_max)
        vis = cp.mapRectToScene(cp.clipPath().boundingRect())
        assert vis.left() >= b.h_min - 1e-6 and vis.right() <= b.h_max + 1e-6
    _host(ms, gl, along_mm=11000.0)                           # wholly outside
    sec.rebuild()
    assert len(_copies(sec)) == 2


def test_hide_then_show_all_hosted_copy(qapp, section_scene_for):
    """Hide a hosted copy in a section, then Show All: the copy returns and
    the model block stays hidden in plan (D11)."""
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    src = _host(ms, gl)
    sec.rebuild()
    (cp,) = _copies(sec)
    sec._hide_elev_items([cp])
    assert not cp.isVisible()
    sec._show_all_elev_hidden()
    (cp2,) = _copies(sec)
    assert cp2.isVisible() and cp2.scene() is sec
    assert not src.isVisible()
    assert src._display_overrides.get("visible") is not False
