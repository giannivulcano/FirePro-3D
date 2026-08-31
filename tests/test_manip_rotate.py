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
