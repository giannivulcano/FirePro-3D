"""S1 guard — with a placement start point, ⊥ is the foot FROM the start point."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import click, close_view, make_view, move

# 45° target line; the foot of the perpendicular from START onto it is FOOT.
T1, T2 = QPointF(0, 0), QPointF(1000, 1000)
START = QPointF(0, 800)
FOOT = QPointF(400, 400)
# On the target line, 30 mm (along-line 42.4 mm) off the foot: 10.6 px at
# m11 = 0.25 — inside the 15 px aperture and the 12 px priority band.
CURSOR = QPointF(430, 430)


def _perp_dot(a, b, t1, t2):
    ux, uy = b.x() - a.x(), b.y() - a.y()
    vx, vy = t2.x() - t1.x(), t2.y() - t1.y()
    return abs(ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))


def _assert_per_from_start(scene):
    r = scene._snap_result
    assert r is not None
    assert r.snap_type == "perpendicular"
    assert math.hypot(r.point.x() - FOOT.x(), r.point.y() - FOOT.y()) < 0.01
    assert _perp_dot(START, r.point, T1, T2) < 1e-4


def test_draw_line_end_snaps_perpendicular_from_start(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(T1, T2))
        click(view, START)
        move(view, CURSOR)
        assert scene._snap_result is not None
        assert scene._snap_result.snap_type == "perpendicular"
        click(view, CURSOR)
        ln = [i for i in scene._draw_lines if i.grip_points()[0] == START][0]
        end = ln.grip_points()[2]
        assert math.hypot(end.x() - FOOT.x(), end.y() - FOOT.y()) < 0.01
        assert _perp_dot(START, end, T1, T2) < 1e-4
    finally:
        close_view(view, scene)


def test_no_start_point_cursor_foot_is_nearest(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(0, 0), QPointF(1000, 0)))
        # Away from the midpoint (500,0) and endpoints. No start point → no
        # ⊥ at all (smoke item 1): the cursor foot (300,0) is ``nearest``.
        move(view, QPointF(300, 12))
        r = scene._snap_result
        assert r is not None and r.snap_type == "nearest"
        assert math.hypot(r.point.x() - 300, r.point.y()) < 0.01
    finally:
        close_view(view, scene)


def _near(a, b, tol=0.01):
    return math.hypot(a.x() - b.x(), a.y() - b.y()) < tol


def _committed_end(scene, mode):
    """The committed segment's END point for *mode*, read from the real model
    item the second click built (not from the snap result)."""
    if mode == "wall":
        walls = [w for w in scene._walls if _near(w.pt1, START)]
        assert len(walls) == 1, [(w.pt1, w.pt2) for w in scene._walls]
        return walls[0].pt2
    if mode == "pipe":
        pipes = [p for p in scene.sprinkler_system.pipes
                 if _near(p.node1.scenePos(), START)]
        assert len(pipes) == 1
        return pipes[0].node2.scenePos()
    if mode == "floor":
        pts = scene._floor_slabs[-1]._points
        assert len(pts) == 2 and _near(pts[0], START), pts
        return pts[1]
    if mode == "roof":
        pts = scene._roof_active._points
        assert len(pts) == 2 and _near(pts[0], START), pts
        return pts[1]
    if mode == "polyline":
        pts = scene._polyline_active._points
        assert len(pts) >= 2 and _near(pts[0], START), pts
        return pts[1]
    raise AssertionError(mode)


@pytest.mark.parametrize("role,mode", [
    ("plan", "wall"), ("plan", "pipe"), ("plan", "floor"),
    ("block_editor", "polyline"),          # polyline is Block-Editor-only
    ("plan", "roof"),                       # roof first-click crash fixed (G3)
])
def test_mode_perpendicular_from_start(qapp, role, mode):
    view, scene = make_view(role=role, mode=mode)
    try:
        assert scene.mode == mode
        if mode == "wall":
            assert scene._wall_primitive == "line"
        if mode == "floor":
            scene._set_floor_primitive("polygon")
        scene.addItem(LineItem(T1, T2))
        click(view, START)
        move(view, CURSOR)
        _assert_per_from_start(scene)
        click(view, CURSOR)                  # commit the segment
        end = _committed_end(scene, mode)
        assert _near(end, FOOT), end
        assert _perp_dot(START, end, T1, T2) < 1e-4
    finally:
        close_view(view, scene)


def test_draw_line_perpendicular_from_start_onto_circle(qapp):
    """m7(a): ⊥-from onto a circle is radial — the committed end is where the
    line centre→start meets the circle (near side), so the line points at
    the centre."""
    from firepro3d.geometry_2d import CircleItem
    view, scene = make_view(mode="draw_line")
    try:
        r = 500.0
        scene.addItem(CircleItem(QPointF(0, 0), r))
        start = QPointF(1000, 800)
        k = r / math.hypot(start.x(), start.y())
        radial = QPointF(start.x() * k, start.y() * k)          # near-side PER point
        th = math.atan2(radial.y(), radial.x()) + math.radians(4)
        cursor = QPointF(r * math.cos(th), r * math.sin(th))    # on the circle, ~35 mm off
        click(view, start)
        move(view, cursor)
        res = scene._snap_result
        assert res is not None and res.snap_type == "perpendicular", res
        click(view, cursor)
        ln = [i for i in scene._draw_lines if _near(i.grip_points()[0], start)][0]
        end = ln.grip_points()[2]
        assert _near(end, radial), end
        # Ground truth: the committed line is radial (collinear with the centre).
        cross = start.x() * end.y() - start.y() * end.x()
        assert abs(cross) / (math.hypot(start.x(), start.y()) * r) < 1e-6
    finally:
        close_view(view, scene)
