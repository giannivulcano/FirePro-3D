"""Ground-truth tests for the ported manipulator transform math."""
import math

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform

from firepro3d.manip_math import (
    HandleRole, _ROLE_GEOM, _rect_point,
    resize_factors, resize_delta, rotate_delta, move_delta,
    transform_angle_deg,
)


RECT = QRectF(0, 0, 100, 50)


def test_role_geom_covers_8_resize_roles():
    assert len(_ROLE_GEOM) == 8
    assert HandleRole.ROTATE not in _ROLE_GEOM


def test_corner_resize_factors_simple():
    fx, fy, anchor = resize_factors(
        RECT, HandleRole.BOTTOM_RIGHT,
        QPointF(100, 50), QPointF(200, 100),
        keep_aspect=False, from_center=False)
    assert (round(fx, 6), round(fy, 6)) == (2.0, 2.0)
    assert anchor == QPointF(0, 0)


def test_negative_factor_mirrors():
    fx, fy, _ = resize_factors(
        RECT, HandleRole.BOTTOM_RIGHT,
        QPointF(100, 50), QPointF(-100, -50),
        keep_aspect=False, from_center=False)
    assert fx < 0 and fy < 0


def test_keep_aspect_corner_projects_onto_diagonal():
    fx, fy, _ = resize_factors(
        RECT, HandleRole.BOTTOM_RIGHT,
        QPointF(100, 50), QPointF(200, 50),
        keep_aspect=True, from_center=False)
    assert math.isclose(fx, fy)


def test_from_center_anchors_at_center():
    _, _, anchor = resize_factors(
        RECT, HandleRole.BOTTOM_RIGHT,
        QPointF(100, 50), QPointF(200, 100),
        keep_aspect=False, from_center=True)
    assert anchor == RECT.center()


def test_edge_midpoint_scales_one_axis():
    fx, fy, _ = resize_factors(
        RECT, HandleRole.RIGHT,
        QPointF(100, 25), QPointF(150, 25),
        keep_aspect=False, from_center=False)
    assert math.isclose(fx, 1.5) and fy == 1.0


def test_rotate_delta_snaps_absolute_angle():
    center = QPointF(0, 0)
    d, total = rotate_delta(center, QPointF(10, 0), QPointF(0, -10),
                            base_angle_deg=0.0, snap_deg=15.0)
    assert total % 15.0 == 0.0


def test_move_delta_ortho_locks_dominant_axis():
    d = move_delta(QPointF(0, 0), QPointF(10, 3), ortho=True)
    moved = d.map(QPointF(0, 0))
    assert moved == QPointF(10, 0)


def test_transform_angle_roundtrip():
    rot = QTransform()
    rot.rotate(30)
    assert math.isclose(transform_angle_deg(rot), 30.0, abs_tol=1e-9)
