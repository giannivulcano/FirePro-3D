"""Per-item baked-rotation (manip_rotate) math tests — U1.

Ground truth: a Y-up CCW+ rotation of a scene point p about pivot equals
CADMath.rotate_point(p, pivot, -deg) (the helper is CCW+ screen-Y-down).
Each item test rotates, checks every geometry point against ground truth,
and verifies rotate(θ) then rotate(-θ) round-trips to the original.
"""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.cad_math import CAD_Math

EPS = 1e-6


def rot_yup(pt: QPointF, pivot: QPointF, deg: float) -> QPointF:
    """Baked Y-up CCW+ rotation of a scene point (ground truth)."""
    return CAD_Math.rotate_point(pt, pivot, -deg)


def approx_pt(a: QPointF, b: QPointF, eps: float = EPS):
    assert abs(a.x() - b.x()) < eps and abs(a.y() - b.y()) < eps, \
        f"{(a.x(), a.y())} != {(b.x(), b.y())}"


@pytest.fixture
def scene(qapp):
    """A bare scene so items with scene-dependent _rebuild paths work."""
    return QGraphicsScene()


def test_wall_manip_rotate_endpoints(scene):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(w)
    pivot = QPointF(50, 0)
    p1_0, p2_0 = QPointF(w._pt1), QPointF(w._pt2)
    w.manip_rotate(90.0, pivot)
    approx_pt(w._pt1, rot_yup(p1_0, pivot, 90.0))
    approx_pt(w._pt2, rot_yup(p2_0, pivot, 90.0))
    w.manip_rotate(-90.0, pivot)
    approx_pt(w._pt1, p1_0)
    approx_pt(w._pt2, p2_0)


def test_node_manip_rotate_keeps_z(scene):
    from firepro3d.node import Node
    n = Node(30, 40, z=2500.0)
    scene.addItem(n)
    pivot = QPointF(0, 0)
    p0 = QPointF(n.scenePos())
    z0 = n.z_pos
    n.manip_rotate(90.0, pivot)
    approx_pt(n.scenePos(), rot_yup(p0, pivot, 90.0))
    assert n.z_pos == z0                      # elevation untouched
    assert n.x_pos == pytest.approx(n.scenePos().x())
    assert n.y_pos == pytest.approx(n.scenePos().y())
    n.manip_rotate(-90.0, pivot)
    approx_pt(n.scenePos(), p0)


def test_gridline_manip_rotate_origin_and_angle(scene):
    from firepro3d.gridline import GridlineItem
    g = GridlineItem(QPointF(0, 0), QPointF(100, 0), label="A")
    scene.addItem(g)
    pivot = QPointF(0, 0)
    origin0 = QPointF(g._origin)
    ang0 = g._angle_deg
    far0 = g.grip_points()[1]                 # far endpoint (rendered)
    g.manip_rotate(90.0, pivot)
    approx_pt(g._origin, rot_yup(origin0, pivot, 90.0))
    assert g._angle_deg == pytest.approx((ang0 + 90.0) % 360.0)
    approx_pt(g.grip_points()[1], rot_yup(far0, pivot, 90.0), eps=1e-4)
    g.manip_rotate(-90.0, pivot)
    approx_pt(g._origin, origin0)


def test_gridline_manip_rotate_respects_lock(scene):
    from firepro3d.gridline import GridlineItem
    g = GridlineItem(QPointF(0, 0), QPointF(100, 0), label="A")
    scene.addItem(g)
    g._locked = True
    o0, a0 = QPointF(g._origin), g._angle_deg
    g.manip_rotate(45.0, QPointF(10, 10))
    approx_pt(g._origin, o0)
    assert g._angle_deg == a0


def test_room_manip_rotate_boundary(scene):
    from firepro3d.room import Room
    r = Room(boundary=[QPointF(0, 0), QPointF(100, 0), QPointF(100, 80)])
    scene.addItem(r)
    pivot = QPointF(50, 40)
    b0 = [QPointF(p) for p in r._boundary]
    r.manip_rotate(90.0, pivot)
    for got, orig in zip(r._boundary, b0):
        approx_pt(got, rot_yup(orig, pivot, 90.0))
    r.manip_rotate(-90.0, pivot)
    for got, orig in zip(r._boundary, b0):
        approx_pt(got, orig)


def test_room_marks_no_solo_rotate():
    from firepro3d.room import Room
    assert getattr(Room, "MANIP_NO_SOLO_ROTATE", False) is True
