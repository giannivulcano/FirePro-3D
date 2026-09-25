"""S5 guard — ALIGN crossings win over cursor-foot snaps through the real seam."""
import math

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.wall import WallSegment
from tests._snap_polish_helpers import click, close_view, dwell, make_view, move


def _commit_line_end(view, scene, start: QPointF, cursor: QPointF) -> QPointF:
    """Draw a real line: click *start*, move to *cursor*, click there; return
    the committed LineItem's end point (seam M6 — observable end effect). The
    start is chosen clear of all geometry so its own H/V rays do not cross
    near *cursor*."""
    before = {id(i) for i in scene.items()}
    click(view, start)
    move(view, cursor)
    click(view, cursor)
    new = [i for i in scene.items()
           if id(i) not in before and type(i) is LineItem]
    assert len(new) == 1, new
    return new[0].mapToScene(new[0].line().p2())


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
        end = _commit_line_end(view, scene, QPointF(700, 900), QPointF(1412, 16))
        assert math.hypot(end.x() - 1400, end.y()) < 0.01, end
    finally:
        close_view(view, scene)


def test_ray_x_rect_edge_wins_over_perpendicular(qapp):
    view, scene = _setup_b(qapp)
    try:
        move(view, QPointF(3012, 12))
        pt = scene.get_effective_position(QPointF(3012, 12))
        assert math.hypot(pt.x() - 3000, pt.y()) < 0.01
        end = _commit_line_end(view, scene, QPointF(2300, 900), QPointF(3012, 12))
        assert math.hypot(end.x() - 3000, end.y()) < 0.01, end
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
        end = _commit_line_end(view, scene, QPointF(-500, 1500), QPointF(1012, 4))
        assert math.hypot(end.x() - 1000, end.y()) < 0.01, end
    finally:
        close_view(view, scene)


def test_real_endpoint_still_beats_crossing(qapp):
    view, scene = _setup_b(qapp)
    try:
        scene.addItem(LineItem(QPointF(1395, 5), QPointF(1395, 900)))   # endpoint 5 units off crossing
        move(view, QPointF(1398, 4))
        res = scene._snap_result
        assert res is not None and res.snap_type == "endpoint"
        end = _commit_line_end(view, scene, QPointF(700, 900), QPointF(1398, 4))
        assert math.hypot(end.x() - 1395, end.y() - 5) < 0.01, end
    finally:
        close_view(view, scene)


def test_in_aperture_real_endpoint_beats_crossing_after_weak_foot(qapp):
    """I2: the cursor-foot beats the endpoint by distance (1 px vs 14 px, past
    the 12 px band), then an ALIGN crossing (5 px) displaces the foot — but a
    real endpoint that would beat the crossing pairwise must still win
    (align-placement §3.1: real SNAP > align_intersection)."""
    view, scene = make_view(mode="draw_line", scale=1.0)
    try:
        scene.addItem(LineItem(QPointF(0, 0), QPointF(100, 0)))
        # Vertical helper line whose endpoint (91,-200) is dwell-acquired:
        # its V / extension rays run along x = 91, crossing the line at (91,0).
        scene.addItem(LineItem(QPointF(91, -200), QPointF(91, -280)))
        dwell(view, QPointF(91, -200))
        assert len(scene._align_controller.acquired) >= 1
        move(view, QPointF(86, 1))
        res = scene._snap_result
        assert res is not None and res.snap_type == "endpoint", (
            res, scene._align_result)
        assert math.hypot(res.point.x() - 100, res.point.y()) < 0.01
        end = _commit_line_end(view, scene, QPointF(-200, 200), QPointF(86, 1))
        assert math.hypot(end.x() - 100, end.y()) < 0.01, end
    finally:
        close_view(view, scene)


def test_hold_on_crossing_releases_to_in_aperture_real_endpoint(qapp):
    """I2 (hold clause): a HELD align_intersection must not outlive a real
    endpoint that beats it pairwise, even when this frame's best is a weak
    cursor-foot."""
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QGraphicsScene

    from firepro3d.snap_engine import OsnapResult, SnapEngine

    sc = QGraphicsScene()
    sc.addItem(LineItem(QPointF(0, 0), QPointF(100, 0)))
    held = OsnapResult(point=QPointF(91, 0), snap_type="align_intersection")
    res = SnapEngine().find(QPointF(86, 1), sc, QTransform(), held=held)
    assert res is not None and res.snap_type == "endpoint"
    assert math.hypot(res.point.x() - 100, res.point.y()) < 0.01
