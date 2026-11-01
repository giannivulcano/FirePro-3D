"""DS3 Flip quadrants (AC-X1..X3): centre = bbox centre of the selection, the
cursor quadrant + arrow keys choose lr / ud, live crosshair + ghost, commit
reflects once per active axis. Mirror keeps the edge-pick axis.

Item: an open polyline (0,0)(100,0)(100,-100) -> bbox x 0..100, y -100..0,
centre (CX, CY) = (50, -50) (scene is Y-down: smaller y = upper).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.transform_ghost import GhostFrame
from tests._modify_tools_helpers import add_primitive, grips, ignore_os_mouse
from tests._snap_polish_helpers import click, close_view, make_view, move
from tests.test_modify_tools_flip_mirror import (_PaintSpy, _capture_status,
                                                 _grab, _px)

CX, CY = 50.0, -50.0
OFF = 60.0
QUADS = {                       # name -> (cursor, lr, ud)
    "UR": (QPointF(CX + OFF, CY - OFF), False, False),
    "UL": (QPointF(CX - OFF, CY - OFF), True, False),
    "LR": (QPointF(CX + OFF, CY + OFF), False, True),
    "LL": (QPointF(CX - OFF, CY + OFF), True, True),
}
POLY0 = [(0.0, 0.0), (100.0, 0.0), (100.0, -100.0)]
POLY_LR = [(100.0, 0.0), (0.0, 0.0), (0.0, -100.0)]      # x -> 100 - x
POLY_UD = [(0.0, -100.0), (100.0, -100.0), (100.0, 0.0)]  # y -> -100 - y
POLY_BOTH = [(100.0, -100.0), (0.0, -100.0), (0.0, 0.0)]
EXPECT = {"UR": POLY0, "UL": POLY_LR, "LR": POLY_UD, "LL": POLY_BOTH}
SAMPLES = [QPointF(0, 0), QPointF(100, 0), QPointF(100, -100), QPointF(20, -70)]
HINT = "Move into a quadrant or ←→ / ↑↓ to flip · click/Enter applies"


def _poly(scene):
    return add_primitive(scene, "polyline_open")[0]


def _reflect_expected(p, lr, ud):
    return (2 * CX - p.x() if lr else p.x(), 2 * CY - p.y() if ud else p.y())


def test_union_manip_bounds_is_the_frame_the_manipulator_draws(qapp):
    from firepro3d.selection_manipulator import union_manip_bounds
    view, scene = make_view(scale=1.0)
    try:
        a = RectangleItem(QPointF(0, 0), QPointF(100, -50))      # manip_bounds
        b = RectangleItem(QPointF(200, 40), QPointF(260, 100))
        for it in (a, b):
            scene.addItem(it)
            scene._draw_rects.append(it)
        r = union_manip_bounds([a, b])
        assert (r.left(), r.top(), r.right(), r.bottom()) == (0.0, -50.0, 260.0, 100.0)
        assert (r.center().x(), r.center().y()) == (130.0, 25.0)
        assert union_manip_bounds([]).isNull()
        # single source of truth: the live manipulator frame is the same union
        scene.clearSelection()
        a.setSelected(True)
        b.setSelected(True)
        QApplication.processEvents()
        frame = scene._live_manip()._rect
        assert (frame.left(), frame.top(), frame.right(), frame.bottom()) == (
            r.left(), r.top(), r.right(), r.bottom())
    finally:
        close_view(view, scene)


# ── AC-X1: cursor quadrant -> ghost transform ────────────────────────────────

@pytest.mark.parametrize("quad", list(QUADS))
def test_quadrant_sets_the_ghost_reflection_about_the_bbox_centre(qapp, quad):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        assert scene._modify_ctl.start("flip") is True
        at, lr, ud = QUADS[quad]
        move(view, at)
        frame = scene._move_ghost
        assert isinstance(frame, GhostFrame) and len(frame) >= 1
        for p in SAMPLES:                                            # [RED]
            got = frame.xform.map(p)
            exp = _reflect_expected(p, lr, ud)
            assert (got.x(), got.y()) == pytest.approx(exp, abs=1e-6)
        assert (scene._flip_lr, scene._flip_ud) == (lr, ud)
        assert scene._mirror_axis is None
    finally:
        close_view(view, scene)


def test_cursor_on_a_crosshair_line_keeps_the_previous_quadrant(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        scene._modify_ctl.start("flip")
        move(view, QUADS["LL"][0])
        assert (scene._flip_lr, scene._flip_ud) == (True, True)
        move(view, QPointF(CX, CY + OFF))              # exactly on the vertical line
        assert (scene._flip_lr, scene._flip_ud) == (True, True)       # [RED]
        move(view, QUADS["LR"][0])
        move(view, QPointF(CX + OFF, CY))              # exactly on the horizontal line
        assert (scene._flip_lr, scene._flip_ud) == (False, True)      # [RED]
    finally:
        close_view(view, scene)


def test_entry_posts_the_hint_and_starts_with_nothing_active(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        seen = []
        scene.instructionChanged.connect(seen.append)
        assert scene._modify_ctl.start("flip") is True
        assert HINT in seen                                           # [RED]
        assert (scene._flip_lr, scene._flip_ud, scene._flip_quad) == (False, False, None)
        c = scene._flip_center
        assert (c.x(), c.y()) == pytest.approx((CX, CY), abs=1e-6)
        assert scene._move_ghost == []
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("snap_probe", [QPointF(103.0, 2.0)])
def test_flip_step_has_no_cursor_snap_or_align(qapp, snap_probe):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        scene._modify_ctl.start("flip")
        move(view, snap_probe)                  # 3.6 px from the endpoint (100, 0)
        assert scene._snap_result is None and scene._align_result is None
    finally:
        close_view(view, scene)


def test_every_view_repaints_on_a_quadrant_change(qapp):
    from firepro3d.model_view import Model_View
    view, scene = make_view(scale=1.0)
    other = Model_View(scene)
    try:
        ignore_os_mouse(other)
        other.resize(400, 300)
        other.show()
        QTest.qWaitForWindowExposed(other)
        other.resetTransform()
        other.centerOn(CX, -200.0)
        QApplication.processEvents()
        _poly(scene)
        scene._modify_ctl.start("flip")
        QApplication.processEvents()
        spy = _PaintSpy(other.viewport())
        band = other.mapFromScene(QPointF(CX, -200.0))
        move(view, QUADS["UL"][0])
        QApplication.processEvents()
        assert spy.repainted(band)                                    # [RED]
    finally:
        other.close()
        other.deleteLater()
        close_view(view, scene)


# ── AC-X2 (click / Enter half): commit reflects the extents, one undo step ───

@pytest.mark.parametrize("quad", ["UL", "LR", "LL"])
def test_click_in_a_quadrant_flips_in_place_in_one_undo_step(qapp, quad):
    view, scene = make_view(scale=1.0)
    try:
        item = _poly(scene)
        p0 = scene._undo_pos
        scene._modify_ctl.start("flip")
        assert item.opacity() == pytest.approx(0.35)            # originals dimmed
        at = QUADS[quad][0]
        move(view, at)
        click(view, at)
        assert grips(item) == EXPECT[quad]                            # [RED]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
        assert item.isSelected() and item.opacity() == pytest.approx(1.0)
        assert scene._flip_center is None and scene._move_ghost == []
        scene.undo()
        assert grips(scene._polylines[0]) == POLY0
    finally:
        close_view(view, scene)


def test_click_without_a_prior_move_aims_at_the_click(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item = _poly(scene)
        scene._modify_ctl.start("flip")
        click(view, QUADS["UL"][0])                  # no hover first
        assert grips(item) == POLY_LR                                 # [RED]
    finally:
        close_view(view, scene)


def test_enter_commits_the_hovered_quadrant(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item = _poly(scene)
        scene._modify_ctl.start("flip")
        move(view, QUADS["LL"][0])
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        assert grips(item) == POLY_BOTH                               # [RED]
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


def test_no_active_axis_says_nothing_flipped_and_pushes_no_undo(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item = _poly(scene)
        p0 = scene._undo_pos
        msgs = _capture_status(scene)
        scene._modify_ctl.start("flip")
        move(view, QUADS["UR"][0])
        click(view, QUADS["UR"][0])
        assert "Nothing flipped" in msgs                              # [RED]
        assert grips(item) == POLY0
        assert scene._undo_pos == p0
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)     # Enter: same
        assert msgs.count("Nothing flipped") == 2 and scene._undo_pos == p0
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_flip_status_counts_flipped_and_skipped(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item = _poly(scene)
        text, _ = add_primitive(scene, "text")
        item.setSelected(True)
        text.setSelected(True)
        tgrips = grips(text)
        msgs = _capture_status(scene)
        scene._modify_ctl.start("flip")
        move(view, QUADS["UL"][0])
        click(view, QUADS["UL"][0])
        assert grips(item) == POLY_LR and grips(text) == tgrips
        assert "Flipped 1 item(s) (1 skipped)" in msgs                # [RED]
    finally:
        close_view(view, scene)


def test_esc_cancels_flip_without_an_undo_step(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item = _poly(scene)
        p0 = scene._undo_pos
        scene._modify_ctl.start("flip")
        move(view, QUADS["LL"][0])
        assert scene._move_ghost
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
        assert scene.mode in (None, "select")
        assert grips(item) == POLY0 and scene._undo_pos == p0
        assert scene._flip_center is None and not scene._move_ghost   # [RED]
        assert (scene._flip_lr, scene._flip_ud, scene._flip_quad) == (False, False, None)
        assert item.opacity() == pytest.approx(1.0)
    finally:
        close_view(view, scene)


def test_undo_mid_flip_cancels_the_tool(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        scene._modify_ctl.start("flip")
        move(view, QUADS["LL"][0])
        scene.undo()
        assert scene.mode in (None, "select")
        assert scene._flip_center is None and not scene._move_ghost   # [RED]
    finally:
        close_view(view, scene)


def test_reentry_resets_the_flip_state_and_a_mirror_axis_never_survives(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        scene._modify_ctl.start("flip")
        move(view, QUADS["LL"][0])
        assert scene._modify_ctl.start("flip") is True           # Shift+F twice
        assert (scene._flip_lr, scene._flip_ud, scene._flip_quad) == (False, False, None)
        assert scene._move_ghost == []                                # [RED]
        # Mirror -> Flip: the hovered Mirror axis is dropped (Flip has none).
        scene.set_mode(None)
        rl = LineItem(QPointF(200, -50), QPointF(200, 50))
        rl.reference = True
        scene.addItem(rl)
        scene._draw_lines.append(rl)
        scene.clearSelection()
        scene._polylines[0].setSelected(True)
        scene._modify_ctl.start("mirror")
        move(view, QPointF(202, 0))
        assert scene._mirror_axis is not None
        assert scene._modify_ctl.start("flip") is True
        assert scene._mirror_axis is None                             # [RED]
        scene.set_mode(None)
    finally:
        close_view(view, scene)


# ── AC-X3: Mirror still requires a hovered straight edge ─────────────────────

def test_mirror_still_requires_a_hovered_edge_and_never_touches_flip_state(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item = _poly(scene)
        p0 = scene._undo_pos
        msgs = _capture_status(scene)
        scene._modify_ctl.start("mirror")
        at = QPointF(-300.0, 250.0)                  # no straight edge here
        move(view, at)
        assert scene._mirror_axis is None
        assert scene._flip_center is None                             # [RED]
        click(view, at)
        assert "Pick a straight edge or reference line" in msgs
        assert scene.mode == "mirror"
        assert len(scene._polylines) == 1 and grips(item) == POLY0
        assert scene._undo_pos == p0
        scene.set_mode(None)
    finally:
        close_view(view, scene)


# ── every primitive flips in place (outline asserted where the bbox is exact) ─

from firepro3d.cad_math import CAD_Math                      # noqa: E402
from firepro3d.halo import halo_scene_path                   # noqa: E402
from tests.test_manip_reflect_scale import _assert_same_outline, _dense  # noqa: E402
from tests.test_modify_tools_flip_mirror import GEOM          # noqa: E402

EXACT_BBOX = ["line", "polyline_open", "polyline_closed", "rect", "rect_rotated",
              "circle", "polygon"]


@pytest.mark.parametrize("name", GEOM)
def test_every_primitive_flips_in_place_about_its_centre(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = _dense(halo_scene_path(item))
        before_grips = grips(item)
        d0 = item.to_dict()
        c = QRectF(min(p.x() for p in before), min(p.y() for p in before),
                   max(p.x() for p in before) - min(p.x() for p in before),
                   max(p.y() for p in before) - min(p.y() for p in before)).center()
        p0 = scene._undo_pos
        scene._modify_ctl.start("flip")
        at = QPointF(c.x() - OFF, c.y() + OFF)                     # LL: both
        move(view, at)
        click(view, at)
        lst = getattr(scene, attr)
        assert len(lst) == 1 and lst[0] is item
        assert type(item) is type(lst[0])
        d1 = item.to_dict()
        assert (d1["type"], d1.get("closed"), d1.get("fill")) == (
            d0["type"], d0.get("closed"), d0.get("fill"))
        if name in EXACT_BBOX:                                        # [RED]
            a1, a2 = QPointF(c.x(), c.y()), QPointF(c.x(), c.y() + 1.0)
            b1, b2 = QPointF(c.x(), c.y()), QPointF(c.x() + 1.0, c.y())
            _assert_same_outline(
                [CAD_Math.mirror_point(CAD_Math.mirror_point(p, a1, a2), b1, b2)
                 for p in before], item)
        assert scene._undo_pos == p0 + 1
        scene.undo()
        assert grips(getattr(scene, attr)[0]) == before_grips
    finally:
        close_view(view, scene)


# ── crosshair paint (DS3.3) ──────────────────────────────────────────────────
V_BAND = [QPointF(CX, y) for y in range(-280, -110)]       # vertical line x = CX
H_BAND = [QPointF(x, CY) for x in range(130, 300)]         # horizontal line y = CY


def _dist(a: QColor, b: QColor) -> int:
    return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())


def _band(view, img, bg, pts):
    return sum(_dist(_px(view, img, p), bg) for p in pts)



def test_crosshair_paints_both_lines_with_active_axes_stronger(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        scene._modify_ctl.start("flip")
        bg = _px(view, _grab(view), QPointF(300, -200))
        img0 = _grab(view)
        v0, h0 = _band(view, img0, bg, V_BAND), _band(view, img0, bg, H_BAND)
        assert v0 > 0 and h0 > 0                       # entry: both lines drawn, idle
        assert 0.67 < v0 / h0 < 1.5                    # ... and equally faint
        move(view, QUADS["UL"][0])                 # lr active only
        img1 = _grab(view)
        v, h = _band(view, img1, bg, V_BAND), _band(view, img1, bg, H_BAND)
        assert h > 0                                                  # idle line still drawn
        assert sum(_dist(_px(view, img1, p), bg) > 0 for p in V_BAND) >= 50   # [RED] dash-dot present
        assert v > 1.5 * h                                            # [RED] active = accent
        move(view, QUADS["LR"][0])                 # ud active only
        img2 = _grab(view)
        v2, h2 = _band(view, img2, bg, V_BAND), _band(view, img2, bg, H_BAND)
        assert h2 > 1.5 * v2                                          # [RED]
    finally:
        close_view(view, scene)


def test_crosshair_is_gone_after_the_tool_ends(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        scene._modify_ctl.start("flip")
        bg = _px(view, _grab(view), QPointF(300, -200))
        move(view, QUADS["LL"][0])
        assert _band(view, _grab(view), bg, V_BAND) > 0
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
        img = _grab(view)
        assert _band(view, img, bg, V_BAND) == 0 and _band(view, img, bg, H_BAND) == 0   # [RED]
    finally:
        close_view(view, scene)


def test_flip_ghost_is_painted_at_the_reflected_position(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _poly(scene)
        scene._modify_ctl.start("flip")
        img0 = _grab(view)
        # The polyline's vertical leg is x = 100, y -100..0; its lr image is
        # x = 0. The Block Editor's non-printing Y axis runs through x = 0, so
        # probe beside it (x = 2) and compare the SAME point before / after:
        # the axis is identical in both grabs, only the ghost differs.
        probe = QPointF(2.0, -70.0)
        move(view, QUADS["UL"][0])
        img1 = _grab(view)
        assert _dist(_px(view, img1, probe), _px(view, img0, probe)) > 0   # [RED]
    finally:
        close_view(view, scene)
