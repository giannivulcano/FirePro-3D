"""DD4 Scale on a real Block Editor scene + view (P1 batch M3).

base (snap/ALIGN) -> reference point (= 1x; == base refused) -> the cursor sets
the new distance (live ghost) -> click; or type Factor after the base. Uniform,
in place; text / blocks skipped; factor <= 0 refused; one undo; Esc no-op.
Ground truth: grips / painted outlines vs CAD_Math.scale_point, viewport
pixels for the ghost, the undo stack.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.cad_math import CAD_Math
from firepro3d.halo import halo_scene_path
from firepro3d.scale_manager import ScaleManager
from tests._modify_tools_helpers import (PRIMITIVES, add_primitive, grips,
                                         ignore_os_mouse)
from tests._snap_polish_helpers import click, close_view, move
from tests._snap_polish_helpers import make_view as _make_view
from tests.test_manip_reflect_scale import _assert_same_outline, _dense

GEOM = [n for n in PRIMITIVES if not n.startswith("text")]
LINE0 = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
NOTHING_TO_SCALE = "Nothing to scale — only 2D drafting geometry can be scaled"


def make_view(**kw):
    """The shared shown view, deaf to the real mouse: the live ghost / factor
    must come only from the test's own events, never a real cursor moving
    over the window."""
    view, scene = _make_view(**kw)
    return ignore_os_mouse(view), scene


def _type_factor(scene, text):
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Factor").setText(text)
    scene.dynamic_input._accept()


def _capture_status(scene):
    msgs = []
    real = scene._show_status
    scene._show_status = lambda m, *a, **k: (msgs.append(m), real(m, *a, **k))
    return msgs


def _grab(view, scene):
    hud = getattr(scene, "dynamic_input", None)
    if hud is not None:
        hud.hide()                    # the HUD widget is not part of the ghost
    view.viewport().update()
    QApplication.processEvents()
    return view.viewport().grab().toImage()


def _px(view, img, spt):
    vp = view.mapFromScene(spt)
    return QColor(img.pixel(vp.x(), vp.y()))


def test_base_reference_cursor_scales_by_the_distance_ratio(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")            # (0,0)-(100,0)
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("scale") is True
        assert item.opacity() == pytest.approx(0.35)
        click(view, QPointF(0, 0))                        # base
        click(view, QPointF(100, 0))                      # reference = 1x
        move(view, QPointF(200, 0))
        click(view, QPointF(200, 0))                      # new distance -> x2
        assert grips(item) == [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]    # [RED]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select") and item.isSelected()
        assert item.opacity() == pytest.approx(1.0)
        scene.undo()
        assert grips(scene._draw_lines[0]) == LINE0
    finally:
        close_view(view, scene)


def test_typed_factor_after_the_base_commits(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))                        # base
        _type_factor(scene, "0.5")
        assert grips(item) == [(0.0, 0.0), (25.0, 0.0), (50.0, 0.0)]      # [RED]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("text", ["0", "-2"])
def test_non_positive_factor_is_refused(qapp, text):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        _type_factor(scene, text)
        assert grips(item) == LINE0                                       # [RED]
        assert scene._undo_pos == p0
        assert scene.mode == "scale"
        assert scene.dynamic_input.has_invalid_field()
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_reference_equal_to_base_is_refused(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        msgs = _capture_status(scene)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))                        # base
        click(view, QPointF(0, 0))                        # ref == base
        assert "Reference point must differ from the base point" in msgs  # [RED]
        assert scene.mode == "scale" and scene._scale_ref is None
        click(view, QPointF(100, 0))                      # a real reference
        move(view, QPointF(50, 0))
        click(view, QPointF(50, 0))                       # -> x0.5
        assert grips(item) == [(0.0, 0.0), (25.0, 0.0), (50.0, 0.0)]
    finally:
        close_view(view, scene)


def test_cursor_back_on_the_base_is_refused(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        msgs = _capture_status(scene)
        p0 = scene._undo_pos
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        click(view, QPointF(100, 0))
        move(view, QPointF(0, 0))
        click(view, QPointF(0, 0))                        # factor 0
        assert "Scale factor must be greater than 0" in msgs              # [RED]
        assert grips(item) == LINE0 and scene._undo_pos == p0
        assert scene.mode == "scale"
        scene.set_mode(None)
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("name", GEOM)
def test_every_primitive_scales_per_dd1(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = _dense(halo_scene_path(item))
        before_grips = grips(item)
        lw, d0 = item.pen().widthF(), item.to_dict()
        p0 = scene._undo_pos
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        base = QPointF(scene._scale_base)                 # the snapped base used
        _type_factor(scene, "1.5")
        lst = getattr(scene, attr)
        assert len(lst) == 1 and lst[0] is item
        _assert_same_outline(
            [CAD_Math.scale_point(p, base, 1.5) for p in before], item)   # [RED]
        assert item.pen().widthF() == lw
        d1 = item.to_dict()
        assert (d1["type"], d1.get("closed")) == (d0["type"], d0.get("closed"))
        assert scene._undo_pos == p0 + 1
        scene.undo()
        assert grips(getattr(scene, attr)[0]) == before_grips
    finally:
        close_view(view, scene)


def test_text_is_skipped_with_a_status_count(qapp):
    view, scene = make_view(scale=1.0)
    try:
        text, _ = add_primitive(scene, "text")
        line, _ = add_primitive(scene, "line")
        text.setSelected(True)
        tgrips = grips(text)
        msgs = _capture_status(scene)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        _type_factor(scene, "2")
        assert grips(line) == [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]
        assert grips(text) == tgrips
        assert "Scaled 1 item(s) by 2 (1 skipped)" in msgs                # [RED]
    finally:
        close_view(view, scene)


def test_text_only_selection_is_refused(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "text")
        msgs = _capture_status(scene)
        assert scene._modify_ctl.start("scale") is False                  # [RED]
        assert scene.mode in (None, "select")
        assert NOTHING_TO_SCALE in msgs
    finally:
        close_view(view, scene)


def test_esc_mid_scale_is_a_no_op(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        click(view, QPointF(100, 0))
        move(view, QPointF(200, 0))
        assert scene._move_ghost                          # ghost live
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
        assert scene.mode in (None, "select")
        assert grips(item) == LINE0 and scene._undo_pos == p0
        assert scene._scale_base is None and not scene._move_ghost
        assert item.opacity() == pytest.approx(1.0)
    finally:
        close_view(view, scene)


def test_cursor_step_paints_the_scaled_ghost(qapp):
    """The sampled pixel sits at 45° on the x2 ghost circle — off the ALIGN
    H/V pair through the base, so only the ghost can paint it."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")                    # centre (0,0), r 50
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))                        # base (centre)
        click(view, QPointF(50, 0))                       # reference (quadrant)
        img0 = _grab(view, scene)
        bg = _px(view, img0, QPointF(300, -200))
        on_ghost = QPointF(70.71, -70.71)                 # r 100 at 45°
        assert _px(view, img0, on_ghost) == bg
        move(view, QPointF(100, 0))                       # x2
        img1 = _grab(view, scene)
        assert _px(view, img1, on_ghost) != bg                            # [RED]
        scene.set_mode(None)
    finally:
        close_view(view, scene)


# ── Carried from the Slice-5 reviews: snap ON, blocks, undo restore ─────────

def test_base_point_uses_cursor_snap(qapp):
    """Unlike the Flip / Mirror axis pick, Scale's points snap (DD4): a click
    a few px off the line's endpoint lands the base ON the endpoint."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        scene._modify_ctl.start("scale")
        move(view, QPointF(3.0, 2.0))
        click(view, QPointF(3.0, 2.0))
        b = scene._scale_base
        assert (round(b.x(), 6), round(b.y(), 6)) == (0.0, 0.0)          # [RED]
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def _block(scene, at=(-150.0, -150.0)):
    """A real placed BlockInstance (one line primitive) — no manip_scale_about."""
    from firepro3d.block_definition import BlockDefinition
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[{"type": "draw_line", "pt1": [0, 0],
                                         "pt2": [40, 0], "color": "#ffffff",
                                         "lineweight": 1.0}],
                            origin=(0.0, 0.0))
    scene.register_block_definition(d)
    return scene.place_block_instance(d.id, at)


def _pose(item):
    t = item.sceneTransform()
    return tuple(round(v, 6) for v in (t.m11(), t.m12(), t.m21(), t.m22(),
                                       t.dx(), t.dy()))


def test_block_instance_is_skipped_with_a_status_count(qapp):
    view, scene = make_view(role="plan", scale=1.0)
    try:
        inst = _block(scene)
        line, _ = add_primitive(scene, "line")
        inst.setSelected(True)                            # line + block selected
        assert inst.isSelected()
        pose = _pose(inst)
        msgs = _capture_status(scene)
        scene._modify_ctl.start("scale")
        assert inst.opacity() == pytest.approx(1.0)       # not "in flight"
        click(view, QPointF(0, 0))
        _type_factor(scene, "2")
        assert grips(line) == [(0.0, 0.0), (100.0, 0.0), (200.0, 0.0)]
        assert _pose(inst) == pose
        assert "Scaled 1 item(s) by 2 (1 skipped)" in msgs                # [RED]
    finally:
        close_view(view, scene)


def test_block_only_selection_is_refused(qapp):
    view, scene = make_view(role="plan", scale=1.0)
    try:
        inst = _block(scene)
        scene.clearSelection()
        inst.setSelected(True)
        msgs = _capture_status(scene)
        assert scene._modify_ctl.start("scale") is False                  # [RED]
        assert scene.mode in (None, "select")
        assert NOTHING_TO_SCALE in msgs
    finally:
        close_view(view, scene)


def test_undo_mid_scale_drops_the_state_and_the_ghost(qapp):
    """Ctrl+Z mid-scale ends the tool (CANCEL_ON_UNDO_MODES): no base /
    reference survives, and the ghost is gone from the viewport."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")                    # centre (0,0), r 50
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        click(view, QPointF(50, 0))
        move(view, QPointF(100, 0))                       # x2 ghost live
        on_ghost = QPointF(70.71, -70.71)
        img = _grab(view, scene)
        bg = _px(view, img, QPointF(300, -200))
        assert _px(view, img, on_ghost) != bg             # precondition
        scene.undo()
        assert scene.mode in (None, "select")
        assert scene._scale_base is None and scene._scale_ref is None     # [RED]
        assert not scene._move_ghost
        assert _px(view, _grab(view, scene), on_ghost) == bg
    finally:
        close_view(view, scene)


# ── Slice-6 review round 2: one factor text, pixel ref tolerance, factor-1
#    no-op, live HUD value, real keystrokes ──────────────────────────────────

def _factor_text(scene):
    return scene.dynamic_input.editor("Factor").text()


def test_live_hud_shows_the_cursor_factor(qapp):
    """The passive HUD reads |cursor - base| / |ref - base| as the cursor
    moves (the _transform_seed_values scale branch), not a frozen 1."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        click(view, QPointF(100, 0))                      # reference = 100
        seen = []
        for x in (150.0, 137.0, 300.0):
            move(view, QPointF(x, 0))
            hud = scene.dynamic_input
            assert hud is not None and hud.isVisible() and not hud.is_engaged()
            seen.append(_factor_text(scene))
        assert seen == ["1.5", "1.37", "3"]                               # [RED]
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_real_keystrokes_type_the_factor(qapp):
    """A digit on the canvas engages the HUD; ".5" + Return in the Factor
    field scales by 0.5 — real key events, not the HUD's private accept."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))                        # base
        move(view, QPointF(40, 30))
        QTest.keyClick(view.viewport(), Qt.Key.Key_0)     # engages, seeds "0"
        ed = scene.dynamic_input.editor("Factor")
        assert QApplication.focusWidget() is ed and ed.text() == "0"
        QTest.keyClicks(ed, ".5")
        QTest.keyClick(ed, Qt.Key.Key_Return)
        assert grips(item) == [(0.0, 0.0), (25.0, 0.0), (50.0, 0.0)]      # [RED]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


def test_status_and_commit_show_the_hud_factor_text(qapp):
    """One formatter (ScaleManager.format_factor) for the HUD, the live
    status and the commit message: 61.75 / 7 reads "8.8214" in all three
    (``:.4g`` would print "8.821")."""
    view, scene = make_view(scale=4.0)
    try:
        item, _ = add_primitive(scene, "line")
        msgs = _capture_status(scene)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        click(view, QPointF(7, 0))                        # reference = 7
        move(view, QPointF(61.75, 0))
        hud_text = _factor_text(scene)
        assert hud_text == "8.8214"
        assert msgs[-1] == f"Factor: {hud_text}"                          # [RED]
        click(view, QPointF(61.75, 0))
        assert f"Scaled 1 item(s) by {hud_text}" in msgs
    finally:
        close_view(view, scene)


def test_commit_message_never_uses_scientific_notation(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        msgs = _capture_status(scene)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        _type_factor(scene, "0.00002")
        assert "Scaled 1 item(s) by 0.00002" in msgs                      # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("scale,base,near,far", [
    (1.0, (300.0, -200.0), (308.0, -200.0), (340.0, -200.0)),     # 8 px / 40 px
    (0.25, (400.0, -400.0), (440.0, -400.0), (600.0, -400.0)),    # 10 px / 50 px
])
def test_reference_within_the_pick_aperture_of_the_base_is_refused(
        qapp, scale, base, near, far):
    """|ref - base| inside the snap aperture (screen px, zoom-aware) cannot
    measure a factor; a reference beyond it is taken. SNAP and ALIGN are
    off (F3 / F11) — with them on, ALIGN's base-point glyph pulls a near
    click exactly onto the base, which hides the raw near-miss."""
    view, scene = make_view(scale=scale)
    try:
        add_primitive(scene, "line")
        scene.toggle_snap(False)
        scene.set_align_enabled(False)
        msgs = _capture_status(scene)
        scene._modify_ctl.start("scale")
        click(view, QPointF(*base))
        move(view, QPointF(*near))
        click(view, QPointF(*near))
        assert "Reference point must differ from the base point" in msgs  # [RED]
        assert scene._scale_ref is None and scene.mode == "scale"
        move(view, QPointF(*far))
        click(view, QPointF(*far))
        assert scene._scale_ref is not None
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_typed_factor_one_is_a_no_op_without_an_undo_step(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        msgs = _capture_status(scene)
        p0, n0 = scene._undo_pos, len(scene._undo_stack)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        _type_factor(scene, "1")
        assert grips(item) == LINE0
        assert (scene._undo_pos, len(scene._undo_stack)) == (p0, n0)      # [RED]
        assert "Scale factor is 1 — nothing changed" in msgs
        assert scene.mode in (None, "select") and item.isSelected()
        assert scene.dynamic_input is None or not scene.dynamic_input.isVisible()
    finally:
        close_view(view, scene)


def test_cursor_at_the_reference_distance_is_a_no_op(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        msgs = _capture_status(scene)
        p0, n0 = scene._undo_pos, len(scene._undo_stack)
        scene._modify_ctl.start("scale")
        click(view, QPointF(0, 0))
        click(view, QPointF(100, 0))
        move(view, QPointF(100, 0))
        click(view, QPointF(100, 0))                      # factor exactly 1
        assert grips(item) == LINE0
        assert (scene._undo_pos, len(scene._undo_stack)) == (p0, n0)      # [RED]
        assert "Scale factor is 1 — nothing changed" in msgs
        assert scene.mode in (None, "select") and item.isSelected()
    finally:
        close_view(view, scene)
