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
