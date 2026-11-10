"""Elevation parity D3 / AC13: the plan SnapEngine on a SectionScene.

Engine-level guards build a real SectionScene over a real Model_Space
(``section_scene_for`` via ``_placed_scene``) and call the real
``SnapEngine.find``; view-level guards post real mouse events to a shown
SectionView. Expected points come from the fixture geometry: the cut runs
+x from plan x = 0 (h = plan x), section v = -elevation (section_scene.py
module docstring), the level elevation from the LevelManager.
"""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTransform

from firepro3d.section_scene import ElevDatumItem, ElevGridlineItem
from firepro3d.snap_engine import SnapEngine
from tests._hosted_blocks_helpers import gridline
from tests.test_section_classification import _placed_scene

GRID_X = 2000.0     # gridline "2" crosses the cut at plan x = 2000 -> h = 2000


def _crossing_scene(section_scene_for):
    """A placed cut (0,0)->(10000,0) crossed by gridline "2" at x = GRID_X:
    one elevation gridline at h = GRID_X, one datum per level."""
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gridline(ms, (GRID_X, 0), (GRID_X, -6000), "2")
    sec.rebuild()
    lvl = ms._level_manager.get("Level 1")
    return ms, sec, lvl


def test_engine_returns_the_datum_gridline_crossing(qapp, section_scene_for):
    """D3 step-1 probe: 4 mm off the Level 1 datum x gridline "2" crossing,
    find() returns that crossing as an ``intersection`` of the two items."""
    _ms, sec, lvl = _crossing_scene(section_scene_for)
    cross = QPointF(GRID_X, -lvl.elevation)
    res = SnapEngine().find(QPointF(cross.x() + 4.0, cross.y() - 4.0),
                            sec, QTransform())
    assert res is not None, "find() sees neither the gridline nor the datum"
    assert res.snap_type == "intersection", res.snap_type
    assert (res.point.x(), res.point.y()) == pytest.approx((cross.x(), cross.y()))
    assert {type(res.source_item), type(res.source_item2)} == {
        ElevGridlineItem, ElevDatumItem}


def test_datum_snaps_to_its_drawn_line(qapp, section_scene_for):
    """OPEN-2 ruling ("snap to the drawn line"): the datum's endpoint snap
    near its head is the head's EDGE (where the drawn line starts) and its
    midpoint is the middle of the DRAWN segment, head edge to the right end
    -- far from the head (cause 2: its bounding rect is the head, so only
    the line-target route reaches it).

    Expected numbers from raw sources, not the snap code: v = -(Level 1
    elevation) (the fixture's level); the right end = the crop box's h_max
    (``sec.basis``, the datum's auto extent, ``_datum_extent``); the head
    edge = where the horizontal at v leaves the head's drawn outline
    (``head.outline_path()``, the block outline the head paints)."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainterPath
    _ms, sec, lvl = _crossing_scene(section_scene_for)
    b = sec.basis
    v = -lvl.elevation
    d = next(i for i in sec.items()
             if isinstance(i, ElevDatumItem) and i._level is lvl)
    outline = d.head.mapToParent(d.head.outline_path())
    assert not outline.isEmpty()                                 # precondition: the head draws
    strip = QPainterPath()
    strip.addRect(QRectF(b.h_min - 1.0e5, v - 0.01, 2.0e5, 0.02))
    edge_x = outline.intersected(strip).boundingRect().right()   # the head's edge on the line
    # precondition: the head sits at the left crop edge (its centre is just
    # outside h_min, so its right edge lands a hair left of h_min: -1.6 mm)
    assert b.h_min - 50.0 < edge_x < GRID_X
    res = SnapEngine().find(QPointF(edge_x + 3.0, v + 3.0), sec, QTransform())
    assert res is not None and res.snap_type == "endpoint", res
    assert res.source_item is d
    assert (res.point.x(), res.point.y()) == pytest.approx((edge_x, v), abs=0.5)
    mid_x = (edge_x + b.h_max) / 2.0
    res = SnapEngine().find(QPointF(mid_x + 3.0, v + 3.0), sec, QTransform())
    assert res is not None and res.snap_type == "midpoint", res
    assert res.source_item is d
    assert (res.point.x(), res.point.y()) == pytest.approx((mid_x, v), abs=0.5)


def test_hosted_copy_is_a_snap_target(qapp, section_scene_for):
    """A hosted block's section copy snaps at its insertion point (R15)."""
    from tests._hosted_blocks_helpers import defn
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gridline(ms, (0, -3000), (6000, -3000), "B")     # parallel host (test_hosted_blocks_edit._setup)
    sec.rebuild()
    at = QPointF(2500.0, -1200.0)                     # placement point = the copy's insertion point
    inst = sec.place_hosted_block(defn(ms).id, at)
    cp = sec._hosted_copies[id(inst)]
    res = SnapEngine().find(QPointF(at.x() + 3.0, at.y() - 3.0), sec, QTransform())
    assert res is not None and res.source_item is cp, res
    assert (res.point.x(), res.point.y()) == pytest.approx((at.x(), at.y()))


def test_wall_proxy_snaps_corner_edge_midpoint_and_centre(qapp, section_scene_for):
    """A projected wall (read-only rect proxy) offers the rectangle snap set (R15)."""
    from tests.test_section_classification import _source_rects, _wall
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (1000.0, -2000.0), (6000.0, -2000.0))   # behind the cut (look side)
    sec.rebuild()
    (proxy,) = _source_rects(sec, w)
    r = proxy.mapRectToScene(proxy.rect())    # the projection's rect: the input, not the engine's output
    eng = SnapEngine()
    for want, pt in (("endpoint", r.topLeft()),
                     ("midpoint", QPointF(r.center().x(), r.top())),
                     ("center", r.center())):
        res = eng.find(QPointF(pt.x() + 3.0, pt.y() + 3.0), sec, QTransform())
        assert res is not None and res.snap_type == want, (want, res)
        assert res.source_item is proxy, (want, res.source_item)
        assert (res.point.x(), res.point.y()) == pytest.approx((pt.x(), pt.y()))


@pytest.mark.parametrize("mode,base,raw", [
    ("move", None, False), ("move", QPointF(0, 0), True),
    ("duplicate", QPointF(0, 0), True), ("rotate", QPointF(0, 0), False),
    ("flip", None, True), ("mirror", None, True), ("fillet", None, True),
    ("constrain_distance", None, True), ("select", None, False), (None, None, False),
])
def test_raw_cursor_mode_table(mode, base, raw):
    """The one raw-cursor rule (snapping-engine s3), shared by Model_Space and
    SectionScene. Rows copied from model_space.py:4402-4419 at 41a76d1b."""
    from firepro3d.snap_engine import raw_cursor_mode
    assert raw_cursor_mode(mode, base) is raw
