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


# ── Review round (C1, M1–M4) ────────────────────────────────────────────────

def _text_corners(t):
    r = t._box_rect_local()
    return [(round(p.x(), 3), round(p.y(), 3)) for p in
            (t.mapToScene(q) for q in (r.topLeft(), r.topRight(),
                                       r.bottomRight(), r.bottomLeft()))]


@pytest.mark.parametrize("name", ["text", "text_rotated"])
def test_rotated_text_about_far_pivot_is_rigid_and_persists(qapp, name):
    """C1: text (unrotated, or already at 30°) turned 45° about a far pivot
    lands at the rigid rotation, and a save round-trip and undo->redo keep it
    there (the text's rotation pivot is transient, so it must not be needed to
    reproduce it)."""
    import json
    from firepro3d.text_item import TextItem
    view, scene = make_view(scale=0.25)
    try:
        item, attr = add_primitive(scene, name)
        before = _text_corners(item)
        scene._modify_ctl.start("rotate")
        click(view, QPointF(1000, 0))                     # far pivot
        pivot = QPointF(scene._rotate_pivot)
        _type_angle(scene, "45")
        exp = _flat(_visual_ccw(before, pivot, 45))
        live = scene._texts[0]
        assert _flat(_text_corners(live)) == pytest.approx(exp, abs=0.05)   # [RED]
        clone = TextItem.from_dict(json.loads(json.dumps(live.to_dict())))
        scene.addItem(clone)
        assert _flat(_text_corners(clone)) == pytest.approx(exp, abs=0.05)  # [RED]
        scene.removeItem(clone)
        scene.undo()
        scene.redo()
        assert _flat(_text_corners(scene._texts[0])) == pytest.approx(exp, abs=0.05)
    finally:
        close_view(view, scene)


def _block_instance(scene):
    from firepro3d.block_instance import BlockInstance
    inst = BlockInstance(block_id="deadbeef", resolver={}.get)
    scene.addItem(inst)
    scene._block_instances.append(inst)
    return inst


def test_rotate_dims_only_what_it_rotates(qapp):
    """M1: a selected item Rotate cannot turn (no manip_rotate) is not dimmed."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        inst = _block_instance(scene)
        inst.setSelected(True)
        scene._modify_ctl.start("rotate")
        assert item.opacity() == pytest.approx(0.35)      # the rotatable one is
        assert inst.opacity() == pytest.approx(1.0)                      # [RED]
    finally:
        close_view(view, scene)


def test_nothing_to_rotate_pushes_no_undo(qapp):
    """M3: only non-rotatable items selected -> no undo step, status says so."""
    view, scene = make_view(scale=1.0)
    try:
        inst = _block_instance(scene)
        scene.push_undo_state()
        scene.clearSelection()
        inst.setSelected(True)
        p0 = scene._undo_pos
        msgs = []
        real = scene._show_status
        scene._show_status = lambda m, *a, **k: (msgs.append(m), real(m, *a, **k))
        scene._modify_ctl.start("rotate")
        click(view, QPointF(0, 0))
        _type_angle(scene, "45")
        assert scene._undo_pos == p0
        assert scene.mode in (None, "select")
        assert "Nothing to rotate" in msgs                               # [RED]
    finally:
        close_view(view, scene)


def test_pivot_and_end_ray_snap(qapp):
    """M4 / D8: the pivot click and the end-ray click both SNAP.

    Targets are off-grid endpoints of unselected lines, so a raw or a
    grid-snapped click cannot land on them by accident.
    """
    from firepro3d.geometry_2d import LineItem
    view, scene = make_view(scale=1.0)
    try:
        for a, b in (((37.3, 58.1), (37.3, 158.1)),       # pivot P / end C
                     ((137.3, 58.1), (237.3, 58.1))):     # start S
            ln = LineItem(QPointF(*a), QPointF(*b))
            scene.addItem(ln)
            scene._draw_lines.append(ln)
        item, _ = add_primitive(scene, "line")            # (0,0)-(100,0)
        scene._modify_ctl.start("rotate")
        move(view, QPointF(39, 60))
        click(view, QPointF(39, 60))                      # near P
        pivot = QPointF(scene._rotate_pivot)
        assert (round(pivot.x(), 3), round(pivot.y(), 3)) == (37.3, 58.1)   # [RED]
        move(view, QPointF(139, 60))
        click(view, QPointF(139, 60))                     # near S: 0°
        move(view, QPointF(39, 156))
        click(view, QPointF(39, 156))                     # near C: -90°
        exp = _visual_ccw([(100.0, 0.0)], pivot, -90.0)[0]
        p2 = item.grip_points()[-1]
        assert (p2.x(), p2.y()) == pytest.approx(exp, abs=0.01)             # [RED]
    finally:
        close_view(view, scene)


def test_rotate_honours_capability_narrowing(qapp):
    """M2: an item whose ``manip_capabilities()`` drops "rotate" is left alone
    even though it carries ``manip_rotate`` (one source of truth:
    ``selection_manipulator.item_capabilities``).

    No shipped class narrows "rotate" away today, so this uses a real LineItem
    subclass that does.
    """
    from firepro3d.geometry_2d import LineItem

    class _NoRotateLine(LineItem):
        def manip_capabilities(self):
            return {"translate"}

    view, scene = make_view(scale=1.0)
    try:
        ln = _NoRotateLine(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(ln)
        scene._draw_lines.append(ln)
        scene.push_undo_state()
        scene.clearSelection()
        ln.setSelected(True)
        p0 = scene._undo_pos
        scene._modify_ctl.start("rotate")
        assert ln.opacity() == pytest.approx(1.0)                        # [RED]
        click(view, QPointF(0, 0))
        _type_angle(scene, "90")
        assert grips(ln)[-1] == (100.0, 0.0)
        assert scene._undo_pos == p0
    finally:
        close_view(view, scene)
