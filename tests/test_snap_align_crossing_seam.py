"""S5 guard — ALIGN crossings win over cursor-foot snaps through the real seam."""
import math

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.wall import WallSegment
from tests._snap_polish_helpers import close_view, dwell, make_view, move


def _setup_b(qapp):
    view, scene = make_view(mode="draw_line")
    scene.addItem(LineItem(QPointF(-2000, 0), QPointF(0, 0)))
    scene.addItem(WallSegment(QPointF(1500, -300), QPointF(1500, 1700), thickness_mm=200.0))
    scene.addItem(RectangleItem(QPointF(3000, -300), QPointF(3800, 1700)))
    dwell(view, QPointF(0, 0))
    assert len(scene._align_controller.acquired) >= 1
    return view, scene


def test_ray_x_wall_face_wins_over_perpendicular(qapp):
    view, scene = _setup_b(qapp)
    try:
        move(view, QPointF(1412, 16))
        pt = scene.get_effective_position(QPointF(1412, 16))
        assert math.hypot(pt.x() - 1400, pt.y()) < 0.01
    finally:
        close_view(view, scene)


def test_ray_x_rect_edge_wins_over_perpendicular(qapp):
    view, scene = _setup_b(qapp)
    try:
        move(view, QPointF(3012, 12))
        pt = scene.get_effective_position(QPointF(3012, 12))
        assert math.hypot(pt.x() - 3000, pt.y()) < 0.01
    finally:
        close_view(view, scene)


def test_path_x_path_on_geometry_wins(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(-2000, 0), QPointF(0, 0)))
        scene.addItem(LineItem(QPointF(1000, 2000), QPointF(1000, 1000)))
        dwell(view, QPointF(0, 0))
        dwell(view, QPointF(1000, 1000))
        scene.addItem(LineItem(QPointF(0, -1000), QPointF(3000, 2000)))   # through (1000,0)
        move(view, QPointF(1012, 4))
        pt = scene.get_effective_position(QPointF(1012, 4))
        assert math.hypot(pt.x() - 1000, pt.y()) < 0.01
    finally:
        close_view(view, scene)


def test_real_endpoint_still_beats_crossing(qapp):
    view, scene = _setup_b(qapp)
    try:
        scene.addItem(LineItem(QPointF(1395, 5), QPointF(1395, 900)))   # endpoint 5 units off crossing
        move(view, QPointF(1398, 4))
        res = scene._snap_result
        assert res is not None and res.snap_type == "endpoint"
    finally:
        close_view(view, scene)
