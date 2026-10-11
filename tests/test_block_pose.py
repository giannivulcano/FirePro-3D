"""block_pose: pose matrix, reflect rule, decomposition (design DD2/DD3/DD6/DD9).

Ground truth is the scene map itself: a reflected pose must place every local
point exactly where the scene reflection of the old pose put it.
"""
import itertools
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.arc_math import yup_angle
from firepro3d.block_pose import (decompose_pose, is_upright, norm_deg,
                                  pose_matrix, reflect_pose)
from firepro3d.transform_ghost import reflect_transform

LOCAL = [QPointF(0, 0), QPointF(100, 0), QPointF(0, -40), QPointF(30, 25)]


def _same(a, b):
    return (round(a.x(), 6), round(a.y(), 6)) == (round(b.x(), 6), round(b.y(), 6))


def test_identity_pose_matrix_is_translate_rotate_like_pose_transform():
    t = pose_matrix(10.0, 20.0, 90.0)
    # Y-up CCW +90: local +x lands visually up (scene -y).
    assert _same(t.map(QPointF(100, 0)), QPointF(10.0, -80.0))


def test_mirror_is_innermost_local_x_flip():
    t = pose_matrix(0.0, 0.0, 0.0, mirrored=True)
    assert _same(t.map(QPointF(100, 0)), QPointF(-100.0, 0.0))
    assert _same(t.map(QPointF(0, -40)), QPointF(0.0, -40.0))


def test_scale_is_uniform():
    t = pose_matrix(0.0, 0.0, 30.0, scale=2.0)
    p = t.map(QPointF(50, 0))
    assert math.hypot(p.x(), p.y()) == pytest.approx(100.0)


@pytest.mark.parametrize("rot,mirrored,theta,scale", list(itertools.product(
    [0.0, 30.0, 90.0, -135.0], [False, True], [0.0, 90.0, 30.0, -60.0], [1.0, 2.5])))
def test_reflect_pose_matches_scene_reflection(rot, mirrored, theta, scale):
    x, y = 40.0, -15.0
    old = pose_matrix(x, y, rot, mirrored, scale)
    p1 = QPointF(5.0, 7.0)
    p2 = QPointF(5.0 + math.cos(math.radians(theta)),
                 7.0 - math.sin(math.radians(theta)))
    assert yup_angle(p1, p2) == pytest.approx(theta)      # axis heading, (-180, 180]
    refl = reflect_transform(p1, p2)
    pos = refl.map(QPointF(x, y))
    r2, m2 = reflect_pose(rot, mirrored, theta)
    new = pose_matrix(pos.x(), pos.y(), r2, m2, scale)
    for q in LOCAL:
        assert _same(new.map(q), refl.map(old.map(q)))


def test_reflect_pose_examples():
    r, m = reflect_pose(0.0, False, 90.0)                # vertical axis
    assert r == pytest.approx(0.0) and m is True
    r, m = reflect_pose(0.0, False, 0.0)                 # horizontal axis
    assert r == pytest.approx(180.0) and m is True
    r, m = reflect_pose(*reflect_pose(30.0, False, 90.0), 90.0)
    assert norm_deg(r) == pytest.approx(30.0) and m is False   # involution


@pytest.mark.parametrize("rot,mirrored,scale", list(itertools.product(
    [0.0, 45.0, 179.0, -90.0], [False, True], [0.5, 1.0, 3.0])))
def test_decompose_round_trip(rot, mirrored, scale):
    t = pose_matrix(12.0, -7.0, rot, mirrored, scale)
    x, y, r, m, s = decompose_pose(t)
    assert (x, y) == pytest.approx((12.0, -7.0))
    assert m is mirrored
    assert s == pytest.approx(scale)
    assert norm_deg(r - rot) == pytest.approx(0.0, abs=1e-6)


def test_decompose_rigid_scale_is_exactly_one():
    for a in range(0, 360, 7):
        assert decompose_pose(pose_matrix(3, 4, a))[4] == 1.0


def test_is_upright_range():
    assert is_upright(0.0) and is_upright(90.0) and is_upright(-89.9)
    assert not is_upright(180.0) and not is_upright(-90.0) and not is_upright(135.0)
