"""S2 guard — moving items: their own snap points snap to other geometry.

Real path: a shown Model_View over a real Model_Space, posted mouse events.
A = LineItem (0,0)-(100,0) is moved; B = LineItem (200,10)-(300,10) is the
target. Every gesture's raw drop puts A.p2 at (198,8) — 2.83 scene units
(= 2.83 px at m11 1.0, inside the 15 px aperture) from B.p1 — while the cursor
itself stays far (> 70 px) from every snap point of B. With S2 the moved
line's own endpoint lands exactly on B.p1.
"""
import math
import time

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import click, close_view, drag, make_view, move


def _ab(scene):
    a = LineItem(QPointF(0, 0), QPointF(100, 0))
    b = LineItem(QPointF(200, 10), QPointF(300, 10))
    scene.addItem(a)
    scene.addItem(b)
    scene.clearSelection()
    a.setSelected(True)
    return a, b


def _p2_off_target(a) -> float:
    p2 = a.grip_points()[2]
    return math.hypot(p2.x() - 200, p2.y() - 10)


def test_interior_drag_endpoint_snaps_while_cursor_far(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem

    view, scene = make_view(scale=1.0)
    try:
        a, _b = _ab(scene)
        # A TextItem in the visible rect: TextItem.data shadows
        # QGraphicsItem.data, so the target collection must use the unbound
        # form (else TypeError on the first move).
        scene.addItem(TextItem(TextAnnotationData(
            text="T", x=-300.0, y=-200.0, height_mm=20.0)))
        # grab at (25,0) (interior, not a grip); raw drop puts a.p2 at (198,8)
        drag(view, QPointF(25, 0), QPointF(123, 8))
        assert _p2_off_target(a) < 0.01
        assert scene._snap_result is None          # no stale marker after release
    finally:
        close_view(view, scene)


def test_move_tool_endpoint_snaps_while_cursor_far(qapp):
    view, scene = make_view(scale=1.0)
    try:
        a, _b = _ab(scene)
        scene.set_mode("move")                     # ribbon entry: captures selection
        click(view, QPointF(25, 0))                # base point
        move(view, QPointF(123, 8))
        click(view, QPointF(123, 8))               # destination
        assert _p2_off_target(a) < 0.01
        assert scene._move_handle_session is None  # gesture over
        assert scene._snap_result is None
    finally:
        close_view(view, scene)


def test_midpoint_grip_endpoint_snaps_while_cursor_far(qapp):
    view, scene = make_view(scale=1.0)
    try:
        a, _b = _ab(scene)
        QApplication.processEvents()               # manipulator grips build
        drag(view, a.grip_points()[1], QPointF(148, 8))
        assert _p2_off_target(a) < 0.01
        assert scene._snap_result is None          # no stale marker after release
    finally:
        close_view(view, scene)


def _bench_scene(n):
    view, scene = make_view(scale=1.0)
    # Spread n lines over the visible 800x600 rect so every one is a target
    # (the worst case: all collected by the session, all near the probes).
    cols = 50
    rows = max(1, n // cols)
    for i in range(n):
        x = -380 + (i % cols) * 15.0
        y = -280 + (i // cols) * (560.0 / rows)
        scene.addItem(LineItem(QPointF(x, y), QPointF(x + 5, y + 4)))
    a = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(a)
    scene.clearSelection()
    a.setSelected(True)
    return view, scene, a


def test_handle_snap_move_cost_is_interactive(qapp):
    from firepro3d.handle_snap import HandleSnapSession

    view, scene, a = _bench_scene(2000)
    try:
        s = HandleSnapSession(scene._snap_engine, scene, view, [a], QPointF(25, 0))
        t0 = time.perf_counter()
        for k in range(50):
            s.best(QPointF(25 + k, 3))
        per_move_ms = (time.perf_counter() - t0) / 50 * 1000
        assert per_move_ms < 16.0, per_move_ms
    finally:
        close_view(view, scene)


# ── G4 review round guards ─────────────────────────────────────────────────

def test_shift_first_drag_does_not_bake_preview_into_handles(qapp):
    """I1: Shift held on the first moved updates, then released. The session
    must be built at rest — a late build (after the held preview moved A by
    (50,0)) puts a phantom A.p2 handle at (248,3), which snaps to C.p1."""
    from PyQt6.QtCore import QEvent, Qt
    from tests._snap_polish_helpers import post

    view, scene = make_view(scale=1.0)
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0))
        c = LineItem(QPointF(250, 5), QPointF(250, 200))
        scene.addItem(a)
        scene.addItem(c)
        scene.clearSelection()
        a.setSelected(True)
        post(view, QEvent.Type.MouseButtonPress, QPointF(25, 0))
        view._snap_polish_pressed = True
        try:
            for x in (35, 55, 75):
                move(view, QPointF(x, 0), Qt.KeyboardModifier.ShiftModifier)
            move(view, QPointF(123, 3))
            move(view, QPointF(123, 3))
        finally:
            view._snap_polish_pressed = False
        post(view, QEvent.Type.MouseButtonRelease, QPointF(123, 3))
        p2 = a.grip_points()[2]
        assert math.hypot(p2.x() - 198, p2.y() - 3) < 0.01, (p2.x(), p2.y())
    finally:
        close_view(view, scene)


def test_connected_line_nudges_by_the_raw_delta(qapp):
    """I2: A shares its end with C. C.p1 is A.p2's OWN rest point, so it must
    not pull A back: a (12,5) px interior drag (13 px: past the 10 px
    startDragDistance, inside the 15 px aperture) moves A by exactly (12,5)."""
    view, scene = make_view(scale=1.0)
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0))
        c = LineItem(QPointF(100, 0), QPointF(100, 100))
        scene.addItem(a)
        scene.addItem(c)
        scene.clearSelection()
        a.setSelected(True)
        drag(view, QPointF(25, 0), QPointF(37, 5))
        p1 = a.grip_points()[0]
        assert math.hypot(p1.x() - 12, p1.y() - 5) < 0.01, (p1.x(), p1.y())
    finally:
        close_view(view, scene)


def test_move_tool_nudges_node_with_attached_pipe(qapp):
    """I2: a Node with an attached Pipe (which stretches with it) moves by a
    sub-aperture Move-tool displacement. The base is picked in empty space and
    ALIGN is off, so neither the cursor snap nor an ALIGN ray is in play —
    only the handle snap (the pipe's end is the node handle's own rest)."""
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe

    view, scene = make_view(scale=1.0)
    try:
        n1 = Node(0, 0, z=0.0)
        n2 = Node(100, 0, z=0.0)
        scene.addItem(n1)
        scene.addItem(n2)
        scene.addItem(Pipe(n1, n2))
        scene.clearSelection()
        n2.setSelected(True)
        scene.set_align_enabled(False)              # real ALIGN toggle (F11)
        scene.set_mode("move")
        click(view, QPointF(130, 40))
        move(view, QPointF(138, 46))
        click(view, QPointF(138, 46))
        pos = n2.scenePos()
        assert math.hypot(pos.x() - 108, pos.y() - 6) < 0.01, (pos.x(), pos.y())
    finally:
        close_view(view, scene)


def test_move_tool_retargets_after_zoom_between_clicks(qapp):
    """I3: B.p1 (700,10) is off-screen at the base click; after zooming out
    between the clicks it is visible and A.p2 snaps onto it."""
    view, scene = make_view(scale=1.0)
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0))
        b = LineItem(QPointF(700, 10), QPointF(800, 10))
        scene.addItem(a)
        scene.addItem(b)
        scene.clearSelection()
        a.setSelected(True)
        scene.set_mode("move")
        click(view, QPointF(25, 0))
        view.resetTransform()
        view.scale(0.5, 0.5)
        view.centerOn(300, 0)
        QApplication.processEvents()
        move(view, QPointF(623, 8))
        click(view, QPointF(623, 8))
        p2 = a.grip_points()[2]
        assert math.hypot(p2.x() - 700, p2.y() - 10) < 0.01, (p2.x(), p2.y())
    finally:
        close_view(view, scene)


# ── G4 re-review RR-I1: pan/zoom re-collect frequency (Move tool) ───────────
# Asserted through the session's public ``target_builds`` counter: the defect
# is "an O(scene) target collection on every pan step", and the counter counts
# exactly those collections. A timing bound would be noisy (a collection is
# ~20–140 ms depending on load) and could pass by luck on a small scene.

def _middle_pan(view, steps: int, step_px: float) -> None:
    """Real middle-button pan: press, *steps* moves of *step_px*, release."""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QMouseEvent

    def send(etype, vp, btn, btns):
        ev = QMouseEvent(etype, vp, view.viewport().mapToGlobal(vp), btn, btns,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)
        QApplication.processEvents()

    mid, none = Qt.MouseButton.MiddleButton, Qt.MouseButton.NoButton
    start = QPointF(400, 300)
    send(QEvent.Type.MouseButtonPress, start, mid, mid)
    for k in range(1, steps + 1):
        send(QEvent.Type.MouseMove, QPointF(400 + step_px * k, 300), none, mid)
    send(QEvent.Type.MouseButtonRelease,
         QPointF(400 + step_px * steps, 300), mid, none)


def _move_armed(view, scene):
    """A + B, 200 bystander lines, Move tool armed with its base at (25,0)."""
    a, _b = _ab(scene)
    for i in range(200):
        x = -380 + (i % 50) * 15.0
        y = -280 + (i // 50) * 14.0
        scene.addItem(LineItem(QPointF(x, y), QPointF(x + 5, y + 4)))
    scene.set_mode("move")
    click(view, QPointF(25, 0))
    hs = scene._move_handle_session
    assert hs is not None and hs.target_builds == 1
    return a, hs


def _visible_center(view):
    return view.mapToScene(view.viewport().rect()).boundingRect().center()


def test_move_tool_pan_inside_pad_does_not_recollect(qapp):
    view, scene = make_view(scale=1.0)
    try:
        _a, hs = _move_armed(view, scene)
        c0 = _visible_center(view)
        _middle_pan(view, steps=20, step_px=5.0)        # 100 px, pad is 400 px
        c1 = _visible_center(view)
        assert abs(c1.x() - c0.x()) > 90                 # the view really panned
        assert scene._move_handle_session is hs
        assert hs.target_builds == 1
    finally:
        close_view(view, scene)


def test_move_tool_recollects_on_pan_out_or_zoom(qapp):
    view, scene = make_view(scale=1.0)
    try:
        a, hs = _move_armed(view, scene)
        _middle_pan(view, steps=25, step_px=20.0)       # 500 px > 400 px pad
        after_pan = hs.target_builds
        assert after_pan >= 2
        assert after_pan <= 3                            # not once per step
        view.scale(0.5, 0.5)                             # zoom: aperture changes
        QApplication.processEvents()
        move(view, _visible_center(view))
        assert hs.target_builds == after_pan + 1
    finally:
        close_view(view, scene)


# ── Seam I1: every whole-item move grip handle-snaps ────────────────────────
# Each drags the item's own move grip so one of the item's snap points lands
# ~3.6 units (px at m11 1.0) from B.p1 = (200,10) while the cursor stays > 50 px
# from every point of B; the snap point must land exactly on B.p1.

def _grip_drag_case(make_item, grip_index, point_of, delta, role="block_editor",
                    extra_selected=None):
    view, scene = make_view(role=role, scale=1.0)
    try:
        b = LineItem(QPointF(200, 10), QPointF(300, 10))
        scene.addItem(b)
        it = make_item()
        scene.addItem(it)
        scene.clearSelection()
        it.setSelected(True)
        if extra_selected is not None:
            other = extra_selected()
            scene.addItem(other)
            other.setSelected(True)
        QApplication.processEvents()
        g = it.grip_points()[grip_index]
        if callable(delta):
            delta = delta(it)                          # measured in-scene
        drag(view, g, QPointF(g.x() + delta.x(), g.y() + delta.y()))
        p = point_of(it)
        return math.hypot(p.x() - 200, p.y() - 10), (p.x(), p.y())
    finally:
        close_view(view, scene)


def test_circle_centre_grip_snaps_quadrant(qapp):
    from firepro3d.geometry_2d import CircleItem
    off, p = _grip_drag_case(
        lambda: CircleItem(QPointF(0, 0), 50.0), 0,
        lambda c: QPointF(c._center.x() + c._radius, c._center.y()),
        QPointF(147, 8))
    assert off < 0.01, p


def test_regular_polygon_centre_grip_snaps_vertex(qapp):
    from firepro3d.geometry_2d import RegularPolygonItem
    off, p = _grip_drag_case(
        lambda: RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=50.0), 0,
        lambda g: min(g.vertices(), key=lambda v: math.hypot(v.x() - 200, v.y() - 10)),
        QPointF(147, 8))
    assert off < 0.01, p


def test_ellipse_centre_grip_snaps_axis_end(qapp):
    from firepro3d.geometry_2d import EllipseItem
    off, p = _grip_drag_case(
        lambda: EllipseItem(QPointF(0, 0), 50.0, 30.0), 0,
        lambda e: QPointF(e._center.x() + e._rx, e._center.y()),
        QPointF(147, 8))
    assert off < 0.01, p


def test_rectangle_centre_grip_snaps_edge_midpoint(qapp):
    from firepro3d.geometry_2d import RectangleItem
    off, p = _grip_drag_case(
        lambda: RectangleItem(QPointF(-50, -30), QPointF(50, 30)), 8,
        lambda r: r.grip_points()[3],                 # RM: right edge midpoint
        QPointF(147, 8))
    assert off < 0.01, p


def test_wall_move_grip_snaps_endpoint(qapp):
    from firepro3d.wall import WallSegment
    off, p = _grip_drag_case(
        lambda: WallSegment(QPointF(0, 0), QPointF(100, 0)), 2,
        lambda w: QPointF(w._pt2),
        QPointF(98, 8))
    assert off < 0.01, p


def _text():
    from firepro3d.text_item import TextAnnotationData, TextItem
    return TextItem(TextAnnotationData(text="MOVE", x=0.0, y=0.0, height_mm=20.0))


def _text_delta(t):
    """Raw drop puts the text's TR corner at (197,8), 3.6 from (200,10); the
    grip (box centre) then sits left of B.p1, > 15 px from every point of B."""
    tr = t.grip_points()[2]
    return QPointF(197 - tr.x(), 8 - tr.y())


def test_text_move_grip_snaps_corner_single_select(qapp):
    """Single model text (not box-native there — no "scale" cap): the centre
    move grip from ``manip_handles`` (index ``MOVE_GRIP_INDEX``)."""
    off, p = _grip_drag_case(_text, 8, lambda t: t.grip_points()[2], _text_delta)
    assert off < 0.01, p


def test_text_move_grip_snaps_corner_multi_select(qapp):
    """Multi-select: the text's centre move grip among the union of handles."""
    off, p = _grip_drag_case(
        _text, 8, lambda t: t.grip_points()[2], _text_delta,
        extra_selected=lambda: LineItem(QPointF(-300, -200), QPointF(-250, -200)))
    assert off < 0.01, p


def test_grip_click_without_drag_builds_no_session(qapp, monkeypatch):
    """M4: the O(scene) target collection is lazy — a plain click on a move
    grip builds no HandleSnapSession; a drag builds exactly one. Counted at
    the constructor (the cost under test), since timing a small scene would
    not separate the two."""
    import firepro3d.handle_snap as hsm
    from tests._snap_polish_helpers import click

    built = []
    orig = hsm.HandleSnapSession.__init__

    def counting(self, *a, **k):
        built.append(1)
        orig(self, *a, **k)

    monkeypatch.setattr(hsm.HandleSnapSession, "__init__", counting)
    view, scene = make_view(scale=1.0)
    try:
        a, _b = _ab(scene)
        QApplication.processEvents()
        click(view, a.grip_points()[1])
        assert len(built) == 0
        drag(view, a.grip_points()[1], QPointF(148, 8))
        assert len(built) == 1
        assert _p2_off_target(a) < 0.01
    finally:
        close_view(view, scene)
