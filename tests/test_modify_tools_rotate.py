"""D8: pivot -> start ray -> end ray; typed relative CCW angle; manip_rotate commit.

Convention (observable screen truth): scene Y is down, angles are Y-up CCW+.
A +X endpoint rotated +90 about the origin lands at scene (0, -100) —
visually UP.
"""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication, QGraphicsLineItem

from firepro3d.geometry_2d import CircleItem, RectangleItem
from tests._modify_tools_helpers import PRIMITIVES, add_primitive, grips
from tests._snap_polish_helpers import click, close_view, make_view, move


def _esc(view):
    """The real Escape path: a key event to the view -> scene keyPressEvent."""
    from PyQt6.QtTest import QTest
    QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)


def _type_angle(scene, text):
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Angle").setText(text)
    scene.dynamic_input._accept()


def _flat(pts):
    return [c for p in pts for c in p]


def _visual_ccw(points, pivot, deg):
    """Rotate scene points visually CCW (Y-up) by *deg* about *pivot*."""
    a = math.radians(deg)
    out = []
    for (x, y) in points:
        dx, dy = x - pivot.x(), y - pivot.y()
        out.append((pivot.x() + dx * math.cos(a) + dy * math.sin(a),
                    pivot.y() - dx * math.sin(a) + dy * math.cos(a)))
    return out


def test_rotation_sense_plus_90_is_ccw_on_screen(qapp):
    """Typed 90 about the origin: the +X endpoint lands at scene (0, -100)."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")            # (0,0)-(100,0)
        p0 = scene._undo_pos
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))                        # pivot
        _type_angle(scene, "90")
        p2 = item.grip_points()[-1]
        assert (round(p2.x(), 3), round(p2.y(), 3)) == (0.0, -100.0)   # [RED]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
        assert item.isSelected()
    finally:
        close_view(view, scene)


def test_three_click_rotate_between_rays(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))                        # pivot
        click(view, QPointF(100, 0))                      # start ray  (0°)
        move(view, QPointF(0, 100))
        click(view, QPointF(0, 100))                      # end ray   (-90° Y-up)
        p2 = item.grip_points()[-1]
        assert (round(p2.x(), 2), round(p2.y(), 2)) == (0.0, 100.0)    # [RED]
        assert scene._undo_pos == p0 + 1
        assert item.isSelected()
        assert scene.mode in (None, "select")
        assert item.opacity() == pytest.approx(1.0)       # D11 dim restored
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("name", list(PRIMITIVES))
def test_rotate_every_primitive_keeps_type_and_undoes(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = grips(item)
        cls = type(item)
        angle0 = getattr(item, "_angle", None)
        p0 = scene._undo_pos
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))
        pivot = QPointF(scene._rotate_pivot)              # the snapped pivot
        _type_angle(scene, "45")
        lst = getattr(scene, attr)
        assert len(lst) == 1 and type(lst[0]) is cls      # [RED] rect stays a rect
        if isinstance(lst[0], CircleItem):
            # Circle grips are axis-aligned (centre + 4 quadrants) by design —
            # not a rigid function of the geometry — so compare the class
            # invariant: the centre turns, the radius is unchanged.
            assert _flat(grips(lst[0])[:1]) == pytest.approx(
                _flat(_visual_ccw(before[:1], pivot, 45)), abs=0.05)
            assert lst[0]._radius == pytest.approx(50.0)
        else:
            assert _flat(grips(lst[0])) == pytest.approx(
                _flat(_visual_ccw(before, pivot, 45)), abs=0.05)
        if isinstance(lst[0], RectangleItem):
            assert lst[0]._angle == pytest.approx((angle0 or 0.0) + 45.0)
        assert scene._undo_pos == p0 + 1
        scene.undo()
        assert _flat(grips(getattr(scene, attr)[0])) == pytest.approx(
            _flat(before), abs=0.01)
    finally:
        close_view(view, scene)


def test_ghost_sweeps_ccw_with_the_cursor(qapp):
    """After the start ray, the painted ghost follows the cursor's sweep."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")            # (0,0)-(100,0)
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))
        click(view, QPointF(100, 0))
        move(view, QPointF(0, -150))                      # visually up = +90
        pts = []
        for path in scene._move_ghost:
            for i in range(path.elementCount()):
                e = path.elementAt(i)
                pts.append((e.x, e.y))
        assert any(abs(x) < 0.5 and abs(y + 100) < 0.5 for x, y in pts), pts  # [RED]
        # The originals are untouched until the commit.
        assert grips(item)[-1] == (100.0, 0.0)
    finally:
        close_view(view, scene)


def test_hud_seeds_live_relative_angle(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))
        click(view, QPointF(100, 0))
        move(view, QPointF(0, -150))
        assert scene.begin_dynamic_input() is True
        from firepro3d.scale_manager import ScaleManager
        val = ScaleManager.parse_angle(scene.dynamic_input.editor("Angle").text())
        assert val == pytest.approx(90.0, abs=0.1)
    finally:
        close_view(view, scene)


def test_undo_mid_rotate_cancels_the_tool(qapp):
    """N2: Undo mid-Rotate ends the tool — no stale pivot, dim or ghost."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        item.translate(0.0, 200.0)                        # an undoable edit
        scene.push_undo_state()                           # -> (0,200)-(100,200)
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 200))
        click(view, QPointF(100, 200))
        move(view, QPointF(0, 50))
        scene.undo()
        assert scene.mode in (None, "select")                           # [RED]
        assert not scene._move_ghost
        live = getattr(scene, attr)[0]
        assert live.opacity() == pytest.approx(1.0)
        # The undo itself still ran: it reverted the translate.
        assert grips(live)[0] == (0.0, 0.0) and grips(live)[-1] == (100.0, 0.0)
        assert scene._rotate_pivot is None and scene._rotate_ray is None
        # A later click must not commit a rotation onto the restored items.
        click(view, QPointF(0, 50))
        assert grips(getattr(scene, attr)[0])[-1] == (100.0, 0.0)
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("step", [0, 1, 2])
def test_esc_cancels_at_every_step(qapp, step):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        before = grips(item)
        p0 = scene._undo_pos
        scene._modify_ctl.start("rotate")
        if step >= 1:
            click(view, QPointF(0, 0))
        if step >= 2:
            click(view, QPointF(100, 0))
            move(view, QPointF(0, -150))
        _esc(view)
        assert scene.mode in (None, "select")
        assert grips(item) == before
        assert scene._undo_pos == p0
        assert item.opacity() == pytest.approx(1.0)
        assert not scene._move_ghost
        assert scene._rotate_pivot is None and scene._rotate_ray is None
    finally:
        close_view(view, scene)


def test_no_legacy_dashed_preview_line(qapp):
    """D8: during Rotate only the ghost + ray — no dashed scene line item."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))
        move(view, QPointF(0, -150))
        dashed = [it for it in scene.items()
                  if isinstance(it, QGraphicsLineItem) and it.isVisible()
                  and it.pen().style() == Qt.PenStyle.DashLine]
        assert dashed == []                                              # [RED]
    finally:
        close_view(view, scene)


def _pixel(view, spt):
    img = view.viewport().grab().toImage()
    vp = view.viewportTransform().map(spt)
    return img.pixelColor(int(round(vp.x())), int(round(vp.y()))).name()


def test_pivot_to_cursor_ray_is_painted(qapp):
    """The pivot->cursor ray is drawn on the canvas (block 8)."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")                      # ghost lies along +X
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))
        # Off-axis cursors (no ALIGN H/V track through the pivot).
        probe = QPointF(-40, -70)                         # mid-ray below
        move(view, QPointF(-140, 80))                     # ray elsewhere
        QApplication.processEvents()
        off = _pixel(view, probe)
        move(view, QPointF(-80, -140))                    # ray through probe
        QApplication.processEvents()
        on = _pixel(view, probe)
        assert on != off, (on, off)                                      # [RED]
    finally:
        close_view(view, scene)
