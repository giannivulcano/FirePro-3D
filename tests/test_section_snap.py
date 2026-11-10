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


def _shown_crossing_view(section_scene_for):
    """The shown, fitted SectionView of tests/test_hosted_blocks_click._view
    (gridline "2" at plan x = 2000 crosses the cut; host gridline "B")."""
    from tests.test_hosted_blocks_click import _view
    ms, sec, gl, v = _view(section_scene_for)
    lvl = ms._level_manager.get("Level 1")
    return ms, sec, v, QPointF(GRID_X, -lvl.elevation)


def _px(view, n):
    """*n* screen px in section-scene mm at *view*'s zoom."""
    from firepro3d.snap_engine import px_to_scene
    return px_to_scene(float(n), view.transform().m11())


def test_f3_toggle_is_the_sections_own(qapp, section_scene_for):
    """toggle_snap() turns the SECTION's snap off (snap_point returns the raw
    cursor, snapToggled(False) fires) and leaves the plan scene's on (AC13)."""
    ms, sec, v, cross = _shown_crossing_view(section_scene_for)
    xy = lambda p: (p.x(), p.y())                     # noqa: E731
    try:
        near = QPointF(cross.x() + _px(v, 4), cross.y() - _px(v, 4))
        assert xy(sec.snap_point(near)) == pytest.approx(xy(cross))   # on: the crossing
        seen = []
        sec.snapToggled.connect(seen.append)
        sec.toggle_snap()
        assert seen == [False]
        assert xy(sec.snap_point(near)) == pytest.approx(xy(near))    # off: the raw cursor
        assert sec._snap_result is None               # no marker to paint
        assert ms._snap_enabled is True               # plan untouched
        sec.toggle_snap(True)
        assert xy(sec.snap_point(near)) == pytest.approx(xy(cross))
    finally:
        v.close()


def test_section_follows_the_plan_type_toggles(qapp, section_scene_for):
    """The footer osnap bar writes the plan engine; a section adopts its
    per-type toggles (Intersection off -> the crossing is not offered)."""
    ms, sec, v, cross = _shown_crossing_view(section_scene_for)
    try:
        ms._snap_engine.snap_intersection = False
        sec.snap_point(QPointF(cross.x() + _px(v, 4), cross.y() - _px(v, 4)))
        assert sec._snap_result is not None
        assert sec._snap_result.snap_type != "intersection"
    finally:
        v.close()


def test_handle_snap_paths_read_the_plan_type_toggles(qapp, section_scene_for):
    """OPEN-1 (integrator): every reader of ``sec._snap_engine`` -- the
    manipulator / grip / Move handle-snap paths read the attribute and call
    the engine directly, never ``snap_point`` -- sees the plan engine's
    per-type toggles: Intersection off in plan -> the section engine no
    longer offers the datum x gridline crossing.
    RED when: the ``self._sync_snap_type_toggles()`` line is deleted from the
    ``_snap_engine`` property (the section engine keeps Intersection on)."""
    ms, sec, v, cross = _shown_crossing_view(section_scene_for)
    try:
        near = QPointF(cross.x() + _px(v, 4), cross.y() - _px(v, 4))
        on = sec._snap_engine.find(near, sec, v.transform())
        assert on is not None and on.snap_type == "intersection"   # precondition (T13)
        ms._snap_engine.snap_intersection = False                 # the footer osnap bar's write
        off = sec._snap_engine.find(near, sec, v.transform())
        assert off is None or off.snap_type != "intersection"
    finally:
        ms._snap_engine.snap_intersection = True
        v.close()


def test_gridline_grip_drag_snaps_to_a_datum(qapp, section_scene_for):
    """A grip drag in a section snaps through get_effective_position (the
    GripHandle cursor authority): the bottom end dropped 4 px off the Level 1
    datum lands ON it and survives a rebuild (persisted extent)."""
    from tests.test_elev_grip_retirement import _drive_grip
    ms, sec, v, cross = _shown_crossing_view(section_scene_for)
    try:
        def gridline_2():
            return next(it for it in sec.items()
                        if isinstance(it, ElevGridlineItem) and abs(it._h - GRID_X) < 1e-6)
        ex = gridline_2()
        p2 = ex.line().p2()                           # bottom end (index 1), below Level 1
        drop = (cross.x(), cross.y() + _px(v, 4))
        m = _drive_grip(sec, ex, index=1, start=(p2.x(), p2.y()), path=[drop])
        m._finish(QPointF(*drop), Qt.KeyboardModifier.NoModifier)
        sec.rebuild()
        ex2 = gridline_2()
        assert ex2.line().p2().y() == pytest.approx(cross.y(), abs=1e-6)
    finally:
        v.close()


def _marker_px(view, pt):
    """Pixels of the intersection glyph colour around *pt* on a fresh grab."""
    from firepro3d.snap_engine import SNAP_COLORS
    from tests.test_align_snap_glyphs import _count_colour
    return _count_colour(view, pt, SNAP_COLORS["intersection"])


def test_section_view_paints_the_snap_marker(qapp, section_scene_for):
    """Armed hosted-block placement hovering 4 px off the crossing: the
    SectionView paints the intersection glyph there (AC13 markers); Esc-free
    disarm removes it."""
    from tests._hosted_blocks_helpers import defn
    from tests._modify_tools_helpers import ignore_os_mouse
    from tests._snap_polish_helpers import move
    ms, sec, v, cross = _shown_crossing_view(section_scene_for)
    ignore_os_mouse(v)
    try:
        sec.begin_place_block(defn(ms).id)
        move(v, QPointF(cross.x() + _px(v, 4), cross.y() - _px(v, 4)))
        assert sec._snap_result is not None
        assert sec._snap_result.snap_type == "intersection"
        n_on = _marker_px(v, cross)
        sec.cancel_place_block()
        n_off = _marker_px(v, cross)
        assert n_on - n_off >= 10, (n_on, n_off)
    finally:
        v.close()


def test_select_mode_hover_clears_a_stale_marker(qapp, section_scene_for):
    """A plain select-mode hover drops a marker left by an earlier snap
    (Model_Space parity: get_effective_position runs on every move)."""
    from tests._modify_tools_helpers import ignore_os_mouse
    from tests._snap_polish_helpers import move
    ms, sec, v, cross = _shown_crossing_view(section_scene_for)
    ignore_os_mouse(v)
    try:
        near = QPointF(cross.x() + _px(v, 4), cross.y() - _px(v, 4))
        sec.snap_point(near)                          # a marker is up
        n_on = _marker_px(v, cross)
        move(v, near)                                 # select mode, no tool
        assert sec._snap_result is None
        assert n_on - _marker_px(v, cross) >= 10
    finally:
        v.close()
