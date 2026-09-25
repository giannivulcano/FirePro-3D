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


def test_no_start_point_perpendicular_is_cursor_foot(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(0, 0), QPointF(1000, 0)))
        # Away from the midpoint (500,0) and endpoints, so ⊥ is the only
        # in-aperture high-priority candidate: the cursor foot (300,0).
        move(view, QPointF(300, 12))
        r = scene._snap_result
        assert r is not None and r.snap_type == "perpendicular"
        assert math.hypot(r.point.x() - 300, r.point.y()) < 0.01
    finally:
        close_view(view, scene)


_ROOF_PRESS_BUG = ("pre-existing (proven at bda538a): the roof polygon first click "
                   "qFatal-aborts — placement_input_coordinator._get_roof_template "
                   "imports the non-existent firepro3d.roof_item")


@pytest.mark.parametrize("role,mode", [
    ("plan", "wall"), ("plan", "pipe"), ("plan", "floor"),
    ("block_editor", "polyline"),          # polyline is Block-Editor-only
    pytest.param("plan", "roof", marks=pytest.mark.skip(reason=_ROOF_PRESS_BUG)),
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
    finally:
        close_view(view, scene)


def test_roof_perpendicular_from_last_vertex(qapp):
    """Roof twin of the plan-mode guard. The real first press crashes
    (_ROOF_PRESS_BUG), so the in-progress roof is seeded exactly as
    ``_press_roof`` builds it (real RoofItem, first vertex at START); the
    cursor move then drives the real seam end to end."""
    from firepro3d.roof import RoofItem
    view, scene = make_view(role="plan", mode="roof")
    try:
        scene.addItem(LineItem(T1, T2))
        roof = RoofItem()
        roof.add_point(QPointF(START))
        scene.addItem(roof)
        scene._roofs.append(roof)
        scene._roof_active = roof
        move(view, CURSOR)
        _assert_per_from_start(scene)
    finally:
        close_view(view, scene)
