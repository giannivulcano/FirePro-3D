"""Fillet tool (scene-tools.md D14 Fillet; design 2026-11-01 DS4): a shown
Block Editor view, posted mouse events, scene ground truth (items, arc
centre / radius / angles, undo depth)."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtTest import QTest

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.modify_tools_controller import ModifyToolsController as MTC
from tests._snap_polish_helpers import click, close_view, make_view, move
from tests.test_arc_convention_tools import _add, _baseline, _ends_match
from tests.test_fillet_geometry import CASES

PARALLEL = "Edges are parallel \u2014 no corner to fillet"
TOO_LARGE = "Radius too large for these edges"


def _xy(p):
    return (p.x(), p.y())


def _corner_lines(scene, theta, length=100.0):
    """Two lines meeting at the origin: edge 1 along +X, edge 2 theta CCW (Y-up)."""
    a = math.radians(theta)
    l1 = _add(scene, LineItem(QPointF(length, 0.0), QPointF(0.0, 0.0)), "_draw_lines")
    l2 = _add(scene, LineItem(QPointF(length * math.cos(a), -length * math.sin(a)),
                              QPointF(0.0, 0.0)), "_draw_lines")
    return l1, l2


def _statuses(scene):
    log = []
    real = scene._show_status
    scene._show_status = lambda m, *a, **k: (log.append(m), real(m, *a, **k))
    return log


def _path_ends_match(path, a, b, tol=1e-2):     # Qt's arcMoveTo / Bezier start is ~2e-3 off the exact point (dry run)
    s, e = path.pointAtPercent(0.0), path.pointAtPercent(1.0)

    def near(p, q):
        return math.hypot(p.x() - q[0], p.y() - q[1]) <= tol
    return (near(s, a) and near(e, b)) or (near(s, b) and near(e, a))


def test_entry_needs_no_selection_and_hints(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        seen = []
        scene.instructionChanged.connect(seen.append)
        scene.clearSelection()
        assert scene._modify_ctl.can_start("fillet", []) is True
        assert scene._modify_ctl.start("fillet") is True
        assert scene.mode == "fillet"
        assert seen[-1] == MTC.FILLET_HINT                            # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("theta, center, t1, t2, start, span", CASES)
def test_hover_ghosts_then_click_fillets_two_lines(qapp, theta, center, t1, t2, start, span):
    """AC-F1: arc of radius r whose ends equal the tangent points (Y-up); the
    lines end at t1 / t2; one undo step."""
    view, scene = make_view(scale=1.0, mode=None)
    try:
        l1, l2 = _corner_lines(scene, theta)
        far2 = _xy(l2._pt1)
        p0 = _baseline(scene)
        scene._fillet_radius = 10.0
        scene._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))                                    # hover the corner
        ghost = scene._move_ghost
        assert len(ghost) == 3                                       # arc + two trimmed edges
        assert _path_ends_match(ghost[0], t1, t2)
        click(view, QPointF(0, 0))
        assert len(scene._draw_arcs) == 1
        arc = scene._draw_arcs[0]
        assert _xy(arc._center) == pytest.approx(center, abs=1e-4)
        assert arc._radius == pytest.approx(10.0)
        assert arc._start_deg == pytest.approx(start, abs=1e-4)      # [RED] Y-down revert
        assert arc._span_deg == pytest.approx(span, abs=1e-4)
        assert _ends_match(arc, t1, t2)                              # painted ends
        assert _xy(l1._pt1) == pytest.approx((100.0, 0.0)) and _xy(l1._pt2) == pytest.approx(t1, abs=1e-4)
        assert _xy(l2._pt1) == pytest.approx(far2) and _xy(l2._pt2) == pytest.approx(t2, abs=1e-4)
        assert scene._undo_pos == p0 + 1
        assert scene.mode == "fillet" and scene._move_ghost == []   # F2: stays live, nothing left armed
        assert scene._fillet_item1 is None and scene._fillet_corner is None
        scene.undo()
        assert scene._draw_arcs == []
        assert sorted(_xy(ln._pt2) for ln in scene._draw_lines) == pytest.approx(
            sorted([(0.0, 0.0), (0.0, 0.0)]))
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("scale", [1.0, 0.25])
def test_hover_aperture_is_screen_pixels_at_the_view_zoom(qapp, scale):
    view, scene = make_view(scale=scale, mode=None)
    try:
        _corner_lines(scene, 90.0)
        scene._modify_ctl.start("fillet")
        move(view, QPointF(12.0 / scale, 0.0))                       # 12 px from the vertex
        assert scene._fillet_corner is not None                      # [RED] fixed-mm aperture
        move(view, QPointF(18.0 / scale, 0.0))                       # 18 px: outside the 15 px aperture
        assert scene._fillet_corner is None
    finally:
        close_view(view, scene)


def test_fallback_click_line1_then_hover_line2_extends_to_the_intersection(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        a = _add(scene, LineItem(QPointF(50, 0), QPointF(0, 0)), "_draw_lines")      # near end first (see D2)
        b = _add(scene, LineItem(QPointF(100, -30), QPointF(100, -100)), "_draw_lines")
        p0 = _baseline(scene)
        scene._fillet_radius = 10.0
        scene._modify_ctl.start("fillet")
        seen = []
        scene.instructionChanged.connect(seen.append)
        click(view, QPointF(25, 0))                                  # Line 1 (no corner near)
        assert scene._fillet_item1 is a and seen[-1] == MTC.FILLET_LINE2_HINT
        assert len(scene._move_ghost) == 1                           # Line 1 lit
        move(view, QPointF(100, -60))                                # hover Line 2
        assert len(scene._move_ghost) == 3
        click(view, QPointF(100, -60))
        arc = scene._draw_arcs[0]
        assert _xy(arc._center) == pytest.approx((90.0, -10.0), abs=1e-4)
        assert _xy(a._pt1) == pytest.approx((90.0, 0.0), abs=1e-4)   # extended 50 -> 90
        assert _xy(b._pt1) == pytest.approx((100.0, -10.0), abs=1e-4)
        assert scene._undo_pos == p0 + 1
    finally:
        close_view(view, scene)


def test_parallel_edges_are_refused_and_nothing_changes(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _add(scene, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
        _add(scene, LineItem(QPointF(0, -50), QPointF(100, -50)), "_draw_lines")
        p0 = _baseline(scene)
        log = _statuses(scene)
        scene._modify_ctl.start("fillet")
        click(view, QPointF(50, 0))
        move(view, QPointF(50, -50))
        assert PARALLEL in log                                       # [RED]
        log.clear()
        click(view, QPointF(50, -50))
        assert PARALLEL in log
        assert scene._draw_arcs == [] and scene._undo_pos == p0 and scene.mode == "fillet"
    finally:
        close_view(view, scene)


def test_oversize_radius_is_refused_and_nothing_changes(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        l1, l2 = _corner_lines(scene, 90.0)
        p0 = _baseline(scene)
        scene._fillet_radius = 150.0                                 # t = 150 > 100
        log = _statuses(scene)
        scene._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        assert TOO_LARGE in log and scene._move_ghost == []
        log.clear()
        click(view, QPointF(0, 0))
        assert TOO_LARGE in log
        assert scene._draw_arcs == [] and scene._undo_pos == p0 and scene.mode == "fillet"
        assert _xy(l1._pt2) == (0.0, 0.0) and _xy(l2._pt2) == (0.0, 0.0)
    finally:
        close_view(view, scene)


def test_a_tangent_point_exactly_at_the_far_end_removes_the_zero_length_lines(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _corner_lines(scene, 90.0)
        p0 = _baseline(scene)
        scene._fillet_radius = 100.0                                 # t = 100 == both lengths
        scene._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        click(view, QPointF(0, 0))
        assert scene._draw_lines == [] and len(scene._draw_arcs) == 1
        assert _ends_match(scene._draw_arcs[0], (100.0, 0.0), (0.0, -100.0))
        assert scene._undo_pos == p0 + 1
    finally:
        close_view(view, scene)


def test_circle_is_not_a_corner_candidate(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _add(scene, LineItem(QPointF(100, 0), QPointF(0, 0)), "_draw_lines")
        _add(scene, CircleItem(QPointF(0, 0), 50.0), "_draw_circles")
        scene._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        assert scene._fillet_corner is None
    finally:
        close_view(view, scene)


def test_undo_mid_fillet_drops_the_picked_line_and_ghost(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _add(scene, LineItem(QPointF(0, 0), QPointF(50, 0)), "_draw_lines")
        _baseline(scene)
        scene._modify_ctl.start("fillet")
        click(view, QPointF(25, 0))
        assert scene._fillet_item1 is not None
        scene.undo()
        assert scene.mode in (None, "select")
        assert scene._fillet_item1 is None and scene._move_ghost == []      # [RED]
    finally:
        close_view(view, scene)


from firepro3d.fill_layers import BackgroundLayer, FillLayers
from firepro3d.geometry_2d import PolylineItem, RectangleItem, RegularPolygonItem


def _pts(pl):
    """Flat coordinate list: pytest.approx does NOT recurse into nested tuples (dry run: it compared exactly)."""
    return [c for p in pl._points for c in _xy(p)]


def _flat(pts):
    return [c for p in pts for c in p]


def test_open_polyline_vertex_splits_into_two_polylines_and_an_arc(qapp):
    """AC-F2: open polyline -> two open polylines + arc; the original is gone."""
    view, scene = make_view(scale=1.0, mode=None)
    try:
        pl = PolylineItem(QPointF(0, 0)); pl.append_point(QPointF(100, 0)); pl.append_point(QPointF(100, -100))
        _add(scene, pl, "_polylines")
        p0 = _baseline(scene)
        scene._fillet_radius = 10.0
        scene._modify_ctl.start("fillet")
        move(view, QPointF(100, 0))
        assert len(scene._move_ghost) == 3                          # arc + two pieces
        click(view, QPointF(100, 0))
        assert pl not in scene._polylines and len(scene._polylines) == 2
        a, b = sorted(scene._polylines, key=lambda q: q._points[0].x())
        assert _pts(a) == pytest.approx(_flat([(0.0, 0.0), (90.0, 0.0)]), abs=1e-4)
        assert _pts(b) == pytest.approx(_flat([(100.0, -10.0), (100.0, -100.0)]), abs=1e-4)
        arc = scene._draw_arcs[0]
        assert _xy(arc._center) == pytest.approx((90.0, -10.0), abs=1e-4) and arc._radius == 10.0
        assert _ends_match(arc, (90.0, 0.0), (100.0, -10.0))
        assert scene._undo_pos == p0 + 1
        scene.undo()
        assert len(scene._polylines) == 1 and scene._draw_arcs == []
    finally:
        close_view(view, scene)


def test_rect_corner_becomes_one_open_polyline_and_drops_the_fill(qapp):
    """AC-F2: closed shape becomes open, fill dropped."""
    view, scene = make_view(scale=1.0, mode=None)
    try:
        r = RectangleItem(QPointF(0, 0), QPointF(100, -50))
        r.fill_layers = FillLayers(background=BackgroundLayer("#ff0000", 1.0))
        assert r._draws_fill()                                      # precondition
        _add(scene, r, "_draw_rects")
        p0 = _baseline(scene)
        scene._fillet_radius = 10.0
        scene._modify_ctl.start("fillet")
        move(view, QPointF(100, 0))                                 # the bottom-right corner
        click(view, QPointF(100, 0))
        assert scene._draw_rects == [] and len(scene._polylines) == 1
        pl = scene._polylines[0]
        assert not pl.is_closed()
        assert _pts(pl) == pytest.approx(_flat([(90.0, 0.0), (0.0, 0.0), (0.0, -50.0),
                                          (100.0, -50.0), (100.0, -10.0)]), abs=1e-4)
        assert pl.fill_layers.is_empty and not pl._draws_fill()      # [RED] fill carried over
        arc = scene._draw_arcs[0]
        assert _xy(arc._center) == pytest.approx((90.0, -10.0), abs=1e-4)
        assert _ends_match(arc, (100.0, -10.0), (90.0, 0.0))
        assert scene._undo_pos == p0 + 1
    finally:
        close_view(view, scene)


def test_regular_polygon_corner_is_filleted_to_an_open_polyline(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        pg = RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=100.0)
        _add(scene, pg, "_draw_polygons")
        v0 = pg.vertices()[0]                                       # (100, 0)
        scene._fillet_radius = 10.0
        scene._modify_ctl.start("fillet")
        move(view, v0)
        click(view, v0)
        assert scene._draw_polygons == [] and len(scene._polylines) == 1
        assert len(scene._polylines[0]._points) == 7                # 6 vertices + 2 tangent points - 1
        assert len(scene._draw_arcs) == 1
    finally:
        close_view(view, scene)


def test_polyline_end_vertex_tangent_point_on_the_far_vertex_makes_one_piece(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        pl = PolylineItem(QPointF(0, 0)); pl.append_point(QPointF(100, 0)); pl.append_point(QPointF(100, -100))
        _add(scene, pl, "_polylines")
        _baseline(scene)
        scene._fillet_radius = 100.0                                # t == both segment lengths
        scene._modify_ctl.start("fillet")
        move(view, QPointF(100, 0))
        click(view, QPointF(100, 0))
        assert scene._polylines == [] and len(scene._draw_arcs) == 1   # both pieces degenerate
    finally:
        close_view(view, scene)


def _type_radius(scene, text):
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Radius").setText(text)
    scene.dynamic_input._accept()


def test_hud_shows_the_sticky_radius_default_then_a_typed_commit_sticks(qapp):
    """AC-F5: typed radius commits at the hovered corner; the next fillet is pre-filled with it."""
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _corner_lines(scene, 90.0)
        l3 = _add(scene, LineItem(QPointF(400, -300), QPointF(300, -300)), "_draw_lines")
        l4 = _add(scene, LineItem(QPointF(300, -400), QPointF(300, -300)), "_draw_lines")
        p0 = _baseline(scene)
        scene._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        assert scene.dynamic_input.editor("Radius").value_mm() == pytest.approx(152.4)   # default, 6 in
        _type_radius(scene, "20")
        assert len(scene._draw_arcs) == 1
        arc = scene._draw_arcs[0]
        assert _xy(arc._center) == pytest.approx((20.0, -20.0), abs=1e-4)
        assert arc._radius == pytest.approx(20.0)
        assert scene._fillet_radius == pytest.approx(20.0)           # [RED] not sticky
        assert scene._undo_pos == p0 + 1
        assert scene.mode == "fillet"                                # F2: still live, radius sticky
        move(view, QPointF(300, -300))
        assert scene.dynamic_input.editor("Radius").value_mm() == pytest.approx(20.0)
        click(view, QPointF(300, -300))
        arc2 = scene._draw_arcs[-1]
        assert arc2._radius == pytest.approx(20.0)
        assert _xy(arc2._center) == pytest.approx((320.0, -320.0), abs=1e-4)
    finally:
        close_view(view, scene)


def test_typed_radius_without_a_corner_only_sets_the_sticky(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        p0 = _baseline(scene)
        scene._modify_ctl.start("fillet")
        move(view, QPointF(500, 500))
        _type_radius(scene, "30")
        assert scene._fillet_radius == pytest.approx(30.0)
        assert scene.mode == "fillet" and scene._draw_arcs == [] and scene._undo_pos == p0
    finally:
        close_view(view, scene)


def test_typed_oversize_radius_keeps_the_hud_open_and_changes_nothing(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _corner_lines(scene, 90.0)
        p0 = _baseline(scene)
        log = _statuses(scene)
        scene._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        _type_radius(scene, "150")
        assert scene.dynamic_input is not None and scene.dynamic_input.has_invalid_field()
        assert TOO_LARGE in log and scene._draw_arcs == [] and scene._undo_pos == p0
    finally:
        close_view(view, scene)


def test_real_keystrokes_type_the_radius(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _corner_lines(scene, 90.0)
        scene._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        QTest.keyClick(view.viewport(), Qt.Key.Key_2)               # engages, seeds "2"
        ed = scene.dynamic_input.editor("Radius")
        QTest.keyClicks(ed, "0")
        QTest.keyClick(ed, Qt.Key.Key_Return)
        assert scene._draw_arcs[0]._radius == pytest.approx(20.0)
    finally:
        close_view(view, scene)


def test_enter_commits_the_hovered_corner_like_a_click(qapp):
    view, scene = make_view(scale=1.0, mode=None)
    try:
        _corner_lines(scene, 90.0)
        scene._fillet_radius = 10.0
        scene._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        assert len(scene._draw_arcs) == 1                            # [RED] Enter branch removed
    finally:
        close_view(view, scene)


FILLET_CONSTRAINED = "Fillet conflicts with the constraints on these edges"


def test_a_corner_coincident_is_dropped_so_the_lines_reach_the_tangent_points(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)     # F3: relations follow the toggle
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        l1, l2 = _corner_lines(sc, 90.0)
        ctl = sc.constraint_ctl
        ctl.add("coincident", [{"uid": l1._uid, "h": "p2"}, {"uid": l2._uid, "h": "p2"}])
        p0 = _baseline(sc)
        sc._fillet_radius = 10.0
        sc._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        click(view, QPointF(0, 0))
        assert _xy(l1._pt2) == pytest.approx((10.0, 0.0), abs=1e-4)             # [RED] solver compromise (5,-5)
        assert _xy(l2._pt2) == pytest.approx((0.0, -10.0), abs=1e-4)
        assert sorted(c.type for c in ctl.constraints) == ["coincident", "coincident", "tangent", "tangent"]
        assert not any({r.get("h") for r in c.refs} == {"p2"} and len(c.refs) == 2
                       and all(r["uid"] in (l1._uid, l2._uid) for r in c.refs)
                       for c in ctl.constraints)                                # corner coincident gone
        assert sc._undo_pos == p0 + 1
        sc.undo()
        assert [c.type for c in sc.constraint_ctl.constraints] == ["coincident"]   # restored
    finally:
        close_view(view, sc)
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)


def test_a_dimensioned_edge_refuses_and_restores_everything(qapp):
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        l1, l2 = _corner_lines(sc, 90.0)
        sc.constraint_ctl.add("dim_distance", [{"uid": l1._uid, "h": "edge"}])
        p0 = _baseline(sc)
        log = _statuses(sc)
        sc._fillet_radius = 10.0
        sc._modify_ctl.start("fillet")
        move(view, QPointF(0, 0))
        click(view, QPointF(0, 0))
        assert FILLET_CONSTRAINED in log                                          # [RED] no verify
        assert sc._draw_arcs == [] and sc._undo_pos == p0 and sc.mode == "fillet"
        got = [c for ln in sorted(sc._draw_lines, key=lambda q: q._pt1.x())
               for pt in (ln._pt1, ln._pt2) for c in _xy(pt)]
        assert got == pytest.approx([0.0, -100.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0], abs=1e-6)
        assert [c.type for c in sc.constraint_ctl.constraints] == ["dim_distance"]
    finally:
        close_view(view, sc)
