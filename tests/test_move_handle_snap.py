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
