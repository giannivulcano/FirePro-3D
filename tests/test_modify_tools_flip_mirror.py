"""DD4 Flip / Mirror on a real Block Editor scene + view (P1 batch M2).

Select-first -> "Pick mirror axis" -> each move detects the nearest existing
straight segment (axis_picker; cursor SNAP + ALIGN off) -> click / Enter
commits. Flip reflects the originals in place (Select: originals); Mirror adds
reflected copies (Select: copies). One undo step; Esc is a no-op.

Ground truth: painted outlines vs CAD_Math.mirror_point, painted arc samples
for the Y-up quadrant, viewport pixels for the hover paint, the undo stack.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.cad_math import CAD_Math
from firepro3d.geometry_2d import CircleItem, ReferenceLineItem
from firepro3d.halo import halo_scene_path
from tests._modify_tools_helpers import PRIMITIVES, add_primitive, grips
from tests._snap_polish_helpers import click, close_view, make_view, move
from tests.test_manip_reflect_scale import _assert_same_outline, _dense

GEOM = [n for n in PRIMITIVES if not n.startswith("text")]
AXIS_X = 200.0
HOVER = QPointF(AXIS_X + 2.0, 250.0)     # on the axis line, far from every item
LINE0 = [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]          # factory line grips
LINE_FLIPPED = [(400.0, 0.0), (350.0, 0.0), (300.0, 0.0)]


def _axis_line(scene, x=AXIS_X):
    """A vertical reference line x = *x* (y -500..500): the edge picked as axis.
    Added BEFORE ``add_primitive`` so it is part of the undo baseline."""
    rl = ReferenceLineItem(QPointF(x, -500), QPointF(x, 500))
    scene.addItem(rl)
    scene._reference_lines.append(rl)
    return rl.to_dict()


def _own(scene, attr, axis_d):
    """The tracking list minus the axis reference line (identified by data,
    since an undo restore replaces every item)."""
    return [it for it in getattr(scene, attr) if it.to_dict() != axis_d]


def _hover_and_click(view, at=HOVER):
    move(view, at)
    click(view, at)


def _capture_status(scene):
    msgs = []
    real = scene._show_status
    scene._show_status = lambda m, *a, **k: (msgs.append(m), real(m, *a, **k))
    return msgs


def _grab(view):
    view.viewport().update()
    QApplication.processEvents()
    return view.viewport().grab().toImage()


def _px(view, img, spt):
    vp = view.mapFromScene(spt)
    return QColor(img.pixel(vp.x(), vp.y()))


def test_flip_reflects_in_place_one_undo_selects_original(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _axis_line(scene)
        item, _ = add_primitive(scene, "line")            # (0,0)-(100,0)
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("flip") is True
        assert scene.mode == "flip"
        assert item.opacity() == pytest.approx(0.35)      # DD3: originals dimmed
        _hover_and_click(view)
        assert grips(item) == LINE_FLIPPED                                # [RED]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
        assert item.isSelected() and item.opacity() == pytest.approx(1.0)
        scene.undo()
        assert grips(scene._draw_lines[0]) == LINE0
    finally:
        close_view(view, scene)


def test_mirror_adds_reflected_copy_and_selects_it(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _axis_line(scene)
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("mirror")
        assert item.opacity() == pytest.approx(0.35)
        _hover_and_click(view)
        lines = scene._draw_lines
        assert len(lines) == 2                                            # [RED]
        copy = next(ln for ln in lines if ln is not item)
        assert grips(item) == LINE0                       # original untouched
        assert grips(copy) == LINE_FLIPPED
        assert copy.isSelected() and not item.isSelected()
        assert item.opacity() == pytest.approx(1.0)
        assert scene._undo_pos == p0 + 1
        scene.undo()
        assert len(scene._draw_lines) == 1
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("tool", ["flip", "mirror"])
@pytest.mark.parametrize("name", GEOM)
def test_every_primitive_reflects_per_dd1(qapp, name, tool):
    view, scene = make_view(scale=1.0)
    try:
        axis_d = _axis_line(scene)
        item, attr = add_primitive(scene, name)
        before = _dense(halo_scene_path(item))
        before_grips = grips(item)
        d0 = item.to_dict()
        p0 = scene._undo_pos
        scene._modify_ctl.start(tool)
        _hover_and_click(view)
        lst = _own(scene, attr, axis_d)
        if tool == "flip":
            assert len(lst) == 1 and lst[0] is item
            result = item
        else:
            assert len(lst) == 2                                          # [RED]
            result = next(it for it in lst if it is not item)
            assert grips(item) == before_grips
        a1, a2 = QPointF(AXIS_X, -500), QPointF(AXIS_X, 500)
        _assert_same_outline(
            [CAD_Math.mirror_point(p, a1, a2) for p in before], result)  # [RED]
        assert type(result) is type(item)
        d1 = result.to_dict()
        assert (d1["type"], d1.get("closed"), d1.get("fill")) == (
            d0["type"], d0.get("closed"), d0.get("fill"))
        assert scene._undo_pos == p0 + 1
        scene.undo()
        lst = _own(scene, attr, axis_d)
        assert len(lst) == 1 and grips(lst[0]) == before_grips
    finally:
        close_view(view, scene)


def test_flip_arc_across_x0_lands_in_visual_q2(qapp):
    """Convention-critical (M2): the upper-right arc (centre 0,0, 0..90)
    flipped across x = 0 paints in the visual upper-left quadrant."""
    view, scene = make_view(scale=1.0)
    try:
        _axis_line(scene, x=0.0)
        arc, _ = add_primitive(scene, "arc")
        scene._modify_ctl.start("flip")
        _hover_and_click(view, QPointF(2.0, 250.0))
        path = arc.mapToScene(arc.path())
        pts = [path.pointAtPercent(i / 20) for i in range(21)]
        assert all(p.x() <= 1e-6 and p.y() <= 1e-6 for p in pts)          # [RED]
        mid = path.pointAtPercent(0.5)
        assert (round(mid.x(), 2), round(mid.y(), 2)) == (-35.36, -35.36)
    finally:
        close_view(view, scene)


def test_the_selections_own_edge_is_a_valid_axis(qapp):
    view, scene = make_view(scale=1.0)
    try:
        pl, _ = add_primitive(scene, "polyline_closed")   # (0,0)(100,0)(100,-100)(0,-100)
        scene._modify_ctl.start("flip")
        _hover_and_click(view, QPointF(50.0, 2.0))       # its own bottom edge y = 0
        assert sorted(grips(pl)) == sorted(
            [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)])     # [RED]
        assert pl.is_closed()
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("where", ["on_a_circle", "empty_space"])
def test_click_without_a_straight_edge_is_refused(qapp, where):
    view, scene = make_view(scale=1.0)
    try:
        c = CircleItem(QPointF(250, 0), 50.0)
        scene.addItem(c)
        scene._draw_circles.append(c)
        item, _ = add_primitive(scene, "line")
        msgs = _capture_status(scene)
        p0 = scene._undo_pos
        scene._modify_ctl.start("flip")
        at = QPointF(300.0, 2.0) if where == "on_a_circle" else QPointF(-300.0, 250.0)
        move(view, at)
        assert scene._mirror_axis is None
        click(view, at)
        assert "Pick a straight edge or reference line" in msgs          # [RED]
        assert scene.mode == "flip"
        assert grips(item) == LINE0
        assert scene._undo_pos == p0
        scene.set_mode(None)
    finally:
        close_view(view, scene)


def test_text_is_skipped_with_a_status_count(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _axis_line(scene)
        text, _ = add_primitive(scene, "text")
        line, _ = add_primitive(scene, "line")
        text.setSelected(True)                            # line + text selected
        tgrips = grips(text)
        msgs = _capture_status(scene)
        scene._modify_ctl.start("flip")
        _hover_and_click(view)
        assert grips(line) == LINE_FLIPPED
        assert grips(text) == tgrips
        assert "Flipped 1 item(s) (1 skipped)" in msgs                    # [RED]
        assert text.isSelected() and line.isSelected()
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("tool", ["flip", "mirror"])
def test_text_only_selection_is_refused(qapp, tool):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "text")
        msgs = _capture_status(scene)
        assert scene._modify_ctl.start(tool) is False                     # [RED]
        assert scene.mode in (None, "select")
        assert f"Nothing to {tool} — text and blocks are skipped" in msgs
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("tool", ["flip", "mirror"])
def test_esc_is_a_no_op(qapp, tool):
    view, scene = make_view(scale=1.0)
    try:
        _axis_line(scene)
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start(tool)
        move(view, HOVER)
        assert scene._mirror_axis is not None
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
        assert scene.mode in (None, "select")
        assert grips(item) == LINE0 and len(scene._draw_lines) == 1
        assert scene._undo_pos == p0
        assert scene._mirror_axis is None and not scene._move_ghost
        assert item.opacity() == pytest.approx(1.0)
    finally:
        close_view(view, scene)


def test_enter_commits_on_the_hovered_axis(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _axis_line(scene)
        item, _ = add_primitive(scene, "line")
        scene._modify_ctl.start("flip")
        move(view, HOVER)
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        assert grips(item) == LINE_FLIPPED                                # [RED]
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


def test_axis_step_has_no_cursor_snap_or_align(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _axis_line(scene)
        item, _ = add_primitive(scene, "line")
        near_end = QPointF(103.0, 2.0)                    # 3.6 px from the endpoint
        scene._modify_ctl.start("rotate")                 # control: a snapping step
        move(view, near_end)
        assert scene._snap_result is not None
        scene.set_mode(None)
        item.setSelected(True)
        scene._modify_ctl.start("flip")
        move(view, near_end)
        assert scene._snap_result is None                                 # [RED]
        assert scene._align_result is None
    finally:
        close_view(view, scene)


def test_hover_paints_the_axis_and_the_reflected_ghost(qapp):
    view, scene = make_view(scale=1.0)
    try:
        rl = ReferenceLineItem(QPointF(AXIS_X, -50), QPointF(AXIS_X, 50))
        scene.addItem(rl)
        scene._reference_lines.append(rl)
        add_primitive(scene, "line")                      # (0,0)-(100,0)
        scene._modify_ctl.start("flip")
        img0 = _grab(view)
        bg = _px(view, img0, QPointF(300, -200))
        assert _px(view, img0, QPointF(350, 0)) == bg
        move(view, QPointF(AXIS_X + 2.0, 0.0))
        img1 = _grab(view)
        assert _px(view, img1, QPointF(350, 0)) != bg     # [RED] ghost at the mirror image
        on_axis = [QPointF(AXIS_X, y) for y in range(-280, -100)]
        assert sum(_px(view, img1, p) != bg for p in on_axis) >= 60       # [RED] axis
    finally:
        close_view(view, scene)


# ── Slice-4 review hand-offs: blocks, undo restore, multi-view repaint ──────

def _block(scene, at=(-150.0, -150.0)):
    """A real placed BlockInstance (one line primitive) — no manip_reflect."""
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
        _axis_line(scene)
        inst = _block(scene)
        line, _ = add_primitive(scene, "line")
        inst.setSelected(True)                            # line + block selected
        assert inst.isSelected()
        pose = _pose(inst)
        msgs = _capture_status(scene)
        scene._modify_ctl.start("flip")
        assert inst.opacity() == pytest.approx(1.0)       # not "in flight"
        _hover_and_click(view)
        assert grips(line) == LINE_FLIPPED
        assert _pose(inst) == pose
        assert "Flipped 1 item(s) (1 skipped)" in msgs                    # [RED]
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("tool", ["flip", "mirror"])
def test_block_only_selection_is_refused(qapp, tool):
    view, scene = make_view(role="plan", scale=1.0)
    try:
        inst = _block(scene)
        scene.clearSelection()
        inst.setSelected(True)
        msgs = _capture_status(scene)
        assert scene._modify_ctl.start(tool) is False                     # [RED]
        assert scene.mode in (None, "select")
        assert f"Nothing to {tool} — text and blocks are skipped" in msgs
    finally:
        close_view(view, scene)


def _short_axis(scene):
    """A short vertical reference line x = AXIS_X (y -50..50): the infinite
    painted axis then crosses empty canvas at y in [-280, -100)."""
    rl = ReferenceLineItem(QPointF(AXIS_X, -50), QPointF(AXIS_X, 50))
    scene.addItem(rl)
    scene._reference_lines.append(rl)


_AXIS_BAND = [QPointF(AXIS_X, y) for y in range(-280, -100)]


def _axis_pixels(view, img, bg):
    return sum(_px(view, img, p) != bg for p in _AXIS_BAND)


@pytest.mark.parametrize("tool", ["flip", "mirror"])
def test_undo_mid_pick_drops_the_axis(qapp, tool):
    """The AxisPick holds its source item, which an undo restore replaces —
    after Ctrl+Z mid-pick no axis survives and none is painted."""
    view, scene = make_view(scale=1.0)
    try:
        _short_axis(scene)
        scene.push_undo_state()
        add_primitive(scene, "line")
        scene._modify_ctl.start(tool)
        move(view, QPointF(AXIS_X + 2.0, 0.0))
        bg = _px(view, _grab(view), QPointF(300, -200))
        assert _axis_pixels(view, _grab(view), bg) >= 60  # precondition: painted
        scene.undo()
        assert scene._mirror_axis is None                                 # [RED]
        assert scene.mode in (None, "select")
        assert _axis_pixels(view, _grab(view), bg) == 0
    finally:
        close_view(view, scene)


class _PaintSpy:
    """Event filter recording the viewport regions actually repainted."""

    def __init__(self, viewport):
        from PyQt6.QtCore import QObject

        spy = self

        class _F(QObject):
            def eventFilter(self, obj, ev):
                from PyQt6.QtCore import QEvent
                if ev.type() == QEvent.Type.Paint:
                    spy.regions.append(ev.region())
                return False
        self.regions = []
        self._f = _F()
        viewport.installEventFilter(self._f)

    def repainted(self, vp_point) -> bool:
        return any(r.contains(vp_point) for r in self.regions)


@pytest.mark.parametrize("tool", ["flip", "mirror"])
def test_every_view_repaints_the_axis_band(qapp, tool):
    """MinimalViewportUpdate: a second view on the same scene (a detail view)
    repaints the axis band on each axis change and on mode exit, so no stale
    axis / glow remains there. Parity guard: mouseMoveEvent and set_mode
    already sweep every view; this pins that the axis rides on them."""
    from firepro3d.model_view import Model_View
    view, scene = make_view(scale=1.0)
    other = Model_View(scene)
    try:
        other.resize(400, 300)
        other.show()
        QTest.qWaitForWindowExposed(other)
        other.resetTransform()
        other.centerOn(AXIS_X, -200.0)
        QApplication.processEvents()
        _short_axis(scene)
        add_primitive(scene, "line")
        scene._modify_ctl.start(tool)
        QApplication.processEvents()
        spy = _PaintSpy(other.viewport())
        band = other.mapFromScene(QPointF(AXIS_X, -200.0))
        move(view, QPointF(AXIS_X + 2.0, 0.0))            # axis appears
        QApplication.processEvents()
        assert scene._mirror_axis is not None
        assert spy.repainted(band)                                        # [RED]
        spy.regions.clear()
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)  # mode exit
        QApplication.processEvents()
        assert scene._mirror_axis is None
        assert spy.repainted(band)                                        # [RED]
    finally:
        other.close()
        other.deleteLater()
        close_view(view, scene)
