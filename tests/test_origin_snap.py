"""DD6 guards — shared snap eligibility + the ``origin`` snap kind (Slice 2).

Real path: shown Model_View over a real Model_Space (or a real
BlockEditorWidget for the red insertion marker), posted mouse events through
the scene dispatch (cursor snap via get_effective_position -> find(); handle
snap via the manipulator / Move-Duplicate destination -> HandleSnapSession).
Ground truth: where the geometry actually lands (grip points) and the
published snap marker / painted glyph pixels.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem

from firepro3d.geometry_2d import LineItem
from firepro3d.snap_engine import SNAP_COLORS
from tests._snap_polish_helpers import (
    click, close_view, drag, dwell, make_view, move, post,
)


def _at(p: QPointF, x: float, y: float, tol: float = 0.01) -> bool:
    return math.hypot(p.x() - x, p.y() - y) <= tol


def _selected_line(scene, p1, p2):
    a = LineItem(QPointF(*p1), QPointF(*p2))
    scene.addItem(a)
    scene._draw_lines.append(a)
    scene.clearSelection()
    a.setSelected(True)
    QApplication.processEvents()
    return a


def _drag_peek(view, start: QPointF, end: QPointF, steps: int = 6):
    """Real press / moves / release; returns the scene's published snap
    marker as it stood on the last move, before the release."""
    post(view, QEvent.Type.MouseButtonPress, start)
    view._snap_polish_pressed = True
    try:
        for i in range(1, steps + 1):
            t = i / steps
            move(view, QPointF(start.x() + (end.x() - start.x()) * t,
                               start.y() + (end.y() - start.y()) * t))
        marker = view.scene()._snap_result
    finally:
        view._snap_polish_pressed = False
    post(view, QEvent.Type.MouseButtonRelease, end)
    return marker


def _count_colour(view, scene_pt, hexcol, half=9, rows=None):
    """Pixels of exactly *hexcol* in a box around *scene_pt* (device px).

    Same sampling as tests/test_align_snap_glyphs.py::_count_colour; *rows*
    optionally limits the box to the given row offsets (device px)."""
    img = view.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    vp = view.viewportTransform().map(scene_pt)
    want = QColor(hexcol).rgb()
    cx, cy = int(round(vp.x() * dpr)), int(round(vp.y() * dpr))
    h = int(math.ceil(half * dpr))
    ys = (range(cy - h, cy + h + 1) if rows is None
          else [cy + int(round(r * dpr)) for r in rows])
    n = 0
    for x in range(cx - h, cx + h + 1):
        for y in ys:
            if 0 <= x < img.width() and 0 <= y < img.height() and img.pixel(x, y) == want:
                n += 1
    return n


# ── M7: shared eligibility ──────────────────────────────────────────────────

def test_child_of_a_plain_parent_is_not_a_handle_snap_target(qapp):
    """find() never snapped to children of non-underlay parents; the handle
    snap now follows the same rule (D-a)."""
    view, scene = make_view(scale=1.0)
    try:
        parent = QGraphicsRectItem(0, 0, 1, 1)
        parent.setPos(500, 500)                    # its own corners are far away
        scene.addItem(parent)
        child = LineItem(QPointF(-300, -490), QPointF(-200, -490))   # scene (200,10)-(300,10)
        child.setParentItem(parent)
        a = _selected_line(scene, (0, 0), (100, 0))
        drag(view, QPointF(25, 0), QPointF(123, 8))   # raw: a.p2 at (198,8), 2.8 px from (200,10)
        assert _at(a.grip_points()[2], 198.0, 8.0)                       # [RED]
    finally:
        close_view(view, scene)


def test_gridline_bubble_is_not_a_handle_snap_target(qapp):
    """Parity guard (passes before and after): a bubble (child of the
    gridline, z 500) never offered a handle-snap point."""
    from firepro3d.gridline import GridlineItem

    view, scene = make_view(scale=0.25)
    try:
        gl = GridlineItem(QPointF(-100, -150), QPointF(-100, 150))
        scene.addItem(gl)
        scene._gridlines.append(gl)
        b = gl.bubble1.scenePos()                  # (-100, -1150)
        a = _selected_line(scene, (300, -1000), (400, -1000))
        dx, dy = (b.x() + 8) - 300, (b.y() + 8) - (-1000)
        drag(view, QPointF(350, -1000), QPointF(350 + dx, -1000 + dy))
        p1 = a.grip_points()[0]
        # raw landing (device-px quantised at m11 0.25 -> within 4 mm), never the bubble centre
        assert _at(p1, b.x() + 8, b.y() + 8, tol=4.0)
        assert math.hypot(p1.x() - b.x(), p1.y() - b.y()) > 5.0
    finally:
        close_view(view, scene)


def test_no_intersection_on_the_origin_cross_arms(qapp):
    """The cross is decoration: a line crossing its +-10 mm arm is not an
    intersection target (the old accidental phase-4 hit)."""
    view, scene = make_view(scale=4.0, mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(5, -50), QPointF(5, 50)))
        move(view, QPointF(5.5, 0.5))              # (0,0) is 22 px away: outside the aperture
        res = scene._snap_result
        assert res is None or res.snap_type != "intersection"            # [RED]
    finally:
        close_view(view, scene)


# ── M4: handle snap to the origin ──────────────────────────────────────────

def test_handle_drag_endpoint_snaps_to_origin(qapp):
    view, scene = make_view(scale=1.0)
    try:
        a = _selected_line(scene, (100, 100), (200, 100))
        # grab the interior (150,100); raw drop puts a.p1 at (4,3) = 5 px from (0,0)
        marker = _drag_peek(view, QPointF(150, 100), QPointF(54, 3))
        assert _at(a.grip_points()[0], 0.0, 0.0)                         # [RED]
        assert marker is not None and marker.snap_type == "origin"
    finally:
        close_view(view, scene)


def test_duplicate_destination_handle_snaps_to_origin(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _selected_line(scene, (100, 100), (200, 100))
        scene._modify_ctl.start("duplicate")
        click(view, QPointF(150, 100))             # base = midpoint
        move(view, QPointF(54, 3))                 # copy's p1 raw at (4,3)
        click(view, QPointF(54, 3))
        firsts = sorted((round(l.grip_points()[0].x(), 3), round(l.grip_points()[0].y(), 3))
                        for l in scene._draw_lines)
        assert firsts == [(0.0, 0.0), (100.0, 100.0)]                    # [RED]
    finally:
        close_view(view, scene)


# ── M4: cursor snap to the origin with the intersection toggle OFF ─────────

def test_paste_base_snaps_to_origin_with_intersection_off(qapp):
    view, scene = make_view(scale=1.0)
    try:
        a = _selected_line(scene, (100, 100), (200, 100))
        scene._snap_engine.snap_intersection = False
        scene._modify_ctl.start("copy")
        click(view, QPointF(100, 100))             # copied base = a.p1
        scene.clearSelection()
        assert scene._modify_ctl.start("paste")
        move(view, QPointF(4, 3))
        marker = scene._snap_result
        click(view, QPointF(4, 3))
        pasted = [l for l in scene._draw_lines if l is not a]
        assert len(pasted) == 1
        assert _at(pasted[0].grip_points()[0], 0.0, 0.0)                 # [RED]
        assert marker is not None and marker.snap_type == "origin"
    finally:
        close_view(view, scene)


def test_duplicate_base_click_snaps_to_origin_with_intersection_off(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _selected_line(scene, (100, 100), (200, 100))
        scene._snap_engine.snap_intersection = False
        scene._modify_ctl.start("duplicate")
        move(view, QPointF(4, 3))
        click(view, QPointF(4, 3))                 # the base pick
        assert scene.node_start_pos is not None
        assert _at(scene.node_start_pos, 0.0, 0.0)                       # [RED]
    finally:
        close_view(view, scene)


def test_origin_is_gated_by_f3_only(qapp):
    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        eng = scene._snap_engine
        for attr in ("snap_endpoint", "snap_midpoint", "snap_intersection",
                     "snap_center", "snap_quadrant", "snap_nearest",
                     "snap_perpendicular", "snap_tangent"):
            setattr(eng, attr, False)              # every per-type toggle off
        move(view, QPointF(4, 3))
        res = scene._snap_result
        assert res is not None and res.snap_type == "origin"             # [RED]
        assert _at(res.point, 0.0, 0.0)
        scene.toggle_snap(False)                   # F3 off
        move(view, QPointF(5, 3))
        assert scene._snap_result is None
    finally:
        close_view(view, scene)


def test_origin_outranks_a_closer_endpoint(qapp):
    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(4, -4), QPointF(104, -104)))
        move(view, QPointF(3, -2))                 # endpoint 2.2 px, origin 3.6 px
        res = scene._snap_result
        assert res is not None and res.snap_type == "origin"             # [RED]
    finally:
        close_view(view, scene)


def test_plan_scene_origin_is_its_own_kind(qapp):
    # The plan scene refuses 2D-geometry modes (containment C1); Pipe placement
    # cursor-snaps through the same get_effective_position -> find().
    view, scene = make_view(role="plan", scale=1.0, mode="pipe")
    try:
        move(view, QPointF(4, 3))
        res = scene._snap_result
        assert res is not None and res.snap_type == "origin"             # [RED] (was "intersection")
        assert _at(res.point, 0.0, 0.0)
    finally:
        close_view(view, scene)


# ── M4: the Block Editor red insertion marker ──────────────────────────────

def _block_editor(origin: QPointF):
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager

    project = Model_Space()
    project._level_manager = LevelManager()
    project.scale_manager = ScaleManager()
    w = BlockEditorWidget(project)
    sc = w.editor_scene
    sc._level_manager = LevelManager()
    sc.scale_manager = ScaleManager()
    w.set_origin_point(origin)
    w.resize(800, 600)
    w.show()
    QTest.qWaitForWindowExposed(w)
    v = w.view
    v.resetTransform()
    v.centerOn(0, 0)
    v.setFocus()
    QApplication.processEvents()
    sc.set_mode("select")
    return w, v, sc, project


def _close_editor(w, project):
    w.editor_scene.cleanup()
    project.cleanup()
    w.close()
    w.deleteLater()
    QApplication.processEvents()


def test_pinned_red_marker_is_a_cursor_snap_target(qapp):
    w, v, sc, project = _block_editor(QPointF(300, 200))
    try:
        a = _selected_line(sc, (100, 100), (200, 100))
        sc._modify_ctl.start("copy")
        click(v, QPointF(100, 100))                # copied base = a.p1
        sc.clearSelection()
        assert sc._modify_ctl.start("paste")
        move(v, QPointF(304, 203))
        click(v, QPointF(304, 203))
        pasted = [l for l in sc._draw_lines if l is not a]
        assert len(pasted) == 1
        assert _at(pasted[0].grip_points()[0], 300.0, 200.0)             # [RED]
    finally:
        _close_editor(w, project)


def test_pinned_red_marker_is_a_handle_snap_target(qapp):
    w, v, sc, project = _block_editor(QPointF(300, 200))
    try:
        a = _selected_line(sc, (100, 100), (200, 100))
        # raw drop puts a.p1 at (304,203)
        marker = _drag_peek(v, QPointF(150, 100), QPointF(354, 203))
        assert _at(a.grip_points()[0], 300.0, 200.0)                     # [RED]
        assert marker is not None and marker.snap_type == "origin"
    finally:
        _close_editor(w, project)


# ── M4: the glyph ───────────────────────────────────────────────────────────

def test_origin_glyph_is_an_upright_circle_plus_in_its_colour(qapp):
    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        move(view, QPointF(4, 3))
        assert scene._snap_result is not None
        col = SNAP_COLORS["origin"]                                      # [RED] KeyError
        assert _count_colour(view, QPointF(0, 0), col) >= 10
        # upright plus: the horizontal arm fills the centre rows (a rotated
        # glyph would leave only the centre pixel there)
        assert _count_colour(view, QPointF(0, 0), col, half=4, rows=(-1, 0)) >= 8
    finally:
        close_view(view, scene)


# ── M4: ALIGN acquires the origin like any snapped point (slice-0 probe c) ─

def test_align_dwell_on_origin_tracks_its_axes(qapp):
    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        scene._snap_engine.snap_intersection = False   # no accidental cross hit
        dwell(view, QPointF(1, 1))                 # rest on the origin snap
        move(view, QPointF(300, 4))                # near the origin's H ray
        res = scene._align_result
        assert res is not None and res.snap_type == "align_path"         # [RED]
        assert _at(res.point, 300.0, 0.0, 0.5)
    finally:
        close_view(view, scene)


# ── I-1: real geometry coinciding with the origin keeps its source ─────────
# (user decision 2026-10-01: the origin kind/glyph still wins, but the result
# carries the coincident real candidate's source item / name, so ALIGN keeps
# the Extension / Perpendicular rays it had before the origin kind existed.)

_R2 = math.sqrt(0.5)


def test_line_end_on_origin_keeps_its_extension_ray(qapp):
    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(0, 0), QPointF(100, -100)))
        dwell(view, QPointF(1, 1))                 # rest on the origin (= the line's end)
        res = scene._snap_result
        assert res is not None and res.snap_type == "origin"
        move(view, QPointF(-200, 203))             # beside the line's extension
        res = scene._align_result
        assert res is not None and res.snap_type == "align_path"         # [RED]
        assert _at(res.point, -201.5, 201.5, 0.5)
    finally:
        close_view(view, scene)


def test_placement_armed_on_origin_line_end_gets_its_perpendicular_ray(qapp):
    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(0, 0), QPointF(100, -100)))
        click(view, QPointF(1, 1))                 # arm the first point on the origin
        s = scene._mode_placement_anchor()
        assert s is not None and _at(s, 0.0, 0.0)
        # 300 mm out along the line's normal (_R2, _R2), 3 mm off it along the line
        target = QPointF(300 * _R2, 300 * _R2)
        move(view, QPointF(target.x() + 3 * _R2, target.y() - 3 * _R2))
        res = scene._align_result
        assert res is not None and res.snap_type in ("align_path", "align_intersection")  # [RED]
        assert _at(res.point, target.x(), target.y(), 0.5)
    finally:
        close_view(view, scene)


def test_wall_face_corner_on_origin_keeps_the_wall_extension_ray(qapp):
    from firepro3d.wall import WallSegment

    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        # 200 mm wall along (0.6, -0.8): its face-left-corner-A lands on (0,0)
        w = WallSegment(QPointF(-80, -60), QPointF(520, -860), thickness_mm=200.0)
        scene.addItem(w)
        assert _at(w.snap_quad_points()[0], 0.0, 0.0)
        move(view, QPointF(4, 3))
        res = scene._snap_result
        assert res is not None and res.snap_type == "origin"
        assert res.name is not None and res.name.startswith("face-")    # [RED]
        # ...yet the glyph stays an outlined ⊕: the arms are painted, the
        # quadrant interior (3 px diagonal) is not (a filled face disc would be)
        col = SNAP_COLORS["origin"]
        assert _count_colour(view, QPointF(0, 0), col, half=4, rows=(-1, 0)) >= 8
        assert _count_colour(view, QPointF(-3, -3), col, half=0) == 0
        dwell(view, QPointF(1, 1))                 # acquire the origin (= the face corner)
        move(view, QPointF(-180 + 3 * 0.8, 240 + 3 * 0.6))   # beside the face's extension
        res = scene._align_result
        assert res is not None and res.snap_type == "align_path"
        assert _at(res.point, -180.0, 240.0, 0.5)
    finally:
        close_view(view, scene)


# ── I-2: each source-less origin point has its own ALIGN identity ──────────

def test_block_editor_dwell_acquires_both_origin_points(qapp):
    w, v, sc, project = _block_editor(QPointF(300, 200))
    try:
        sc._snap_engine.snap_intersection = False
        sc.set_mode("draw_line")
        dwell(v, QPointF(1, 1))                    # acquire the (0,0) cross
        move(v, QPointF(150, 100))                 # away from both
        dwell(v, QPointF(301, 201))                # acquire the red marker
        acq = sorted(tuple(round(c, 3) for c in a.point)
                     for a in sc._align_controller.acquired if a.point is not None)
        assert acq == [(0.0, 0.0), (300.0, 200.0)]                       # [RED]
    finally:
        _close_editor(w, project)


# ── M-4: origin edge cases + the phase-4 skip_pipes rule ───────────────────

def test_hidden_origin_cross_is_not_offered(qapp):
    """Paper rendering hides the cross while it plots: no origin then."""
    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        scene._snap_engine.snap_intersection = False
        for it in scene._origin_cross_items:
            it.setVisible(False)
        move(view, QPointF(4, 3))
        res = scene._snap_result
        assert res is None or res.snap_type != "origin"                  # [RED]
    finally:
        close_view(view, scene)


def test_origin_is_offered_after_a_new_load_reset(qapp):
    """scene_io._clear_scene deletes the old cross (scene.clear) and redraws
    it: the deleted items are dropped and the new ones registered."""
    view, scene = make_view(scale=1.0, mode=None)
    try:
        scene._clear_scene()
        scene.set_mode("draw_line")
        move(view, QPointF(4, 3))
        res = scene._snap_result
        assert res is not None and res.snap_type == "origin"
        assert _at(res.point, 0.0, 0.0)
    finally:
        close_view(view, scene)


def test_design_area_center_pick_never_returns_the_origin(qapp):
    """Parity guard: the design-area sprinkler pick calls find() with
    only_types={"center"} (sprinkler_workflow_controller); the origin kind
    obeys that whitelist like every other kind."""
    view, scene = make_view(role="plan", scale=1.0, mode=None)
    try:
        res = scene._snap_engine.find(QPointF(4, 3), scene, view.transform(),
                                      only_types={"center"})
        assert res is None
    finally:
        close_view(view, scene)


def test_phase4_skips_pipes_when_skip_pipes(qapp):
    """DD6: phase 4 (intersections) now applies the shared rule, so with
    skip_pipes a pipe no longer intersects a line (it did before)."""
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe

    view, scene = make_view(role="plan", scale=1.0, mode=None)
    try:
        n1, n2 = Node(1000, 1000, z=0.0), Node(1100, 1000, z=0.0)
        scene.addItem(n1)
        scene.addItem(n2)
        scene.addItem(Pipe(n1, n2))
        scene.addItem(LineItem(QPointF(1050, 950), QPointF(1050, 1050)))
        eng = scene._snap_engine
        cur = QPointF(1052, 1002)
        res = eng.find(cur, scene, view.transform())
        assert res is not None and res.snap_type == "intersection"       # control
        eng.skip_pipes = True
        res = eng.find(cur, scene, view.transform())
        assert res is None or res.snap_type != "intersection"            # [RED]
    finally:
        close_view(view, scene)


# ── RR-1: a cursor foot never decides the origin's adopted source ──────────

def test_line_through_origin_gives_a_stable_origin_source(qapp):
    """A line passing THROUGH (0,0) (no endpoint / midpoint there): its
    cursor-dependent ``nearest`` foot lands exactly on the origin only for
    some sub-pixel cursor x. The origin result must not flip between carrying
    the line (dashed trace painted in the origin colour) and not."""
    view, scene = make_view(scale=1.0, mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(-50, 0), QPointF(150, 0)))
        col = SNAP_COLORS["origin"]
        seen = []
        for x in (0.5, 0.0):
            move(view, QPointF(300, 300))          # release any snap hold: a fresh approach
            move(view, QPointF(x, 3))
            res = scene._snap_result
            assert res is not None and res.snap_type == "origin"
            trace = _count_colour(view, QPointF(90, 0), col, half=40, rows=(0,))
            seen.append((res.source_item is None, trace > 0))
        assert seen[0] == seen[1], seen                                  # [RED]
    finally:
        close_view(view, scene)
