"""Block instance pose math (design 2026-10-11 block-instance-mirror-scale).

The one home for the pose rules shared by ``BlockInstance``,
``block_definition._nested_pose``, the variant op cache and Explode:

    P = T(x, y) . R(rot) . S(scale) . M^mirrored     (M: local x -> -x, innermost)

``rot`` is Y-up CCW degrees (the ``BlockInstance.pose_transform`` convention).
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform


def norm_deg(a: float) -> float:
    """Fold an angle into (-180, 180].

    Args:
        a: Angle in degrees.

    Returns:
        The equivalent angle in (-180, 180].
    """
    r = math.fmod(float(a), 360.0)
    if r <= -180.0:
        r += 360.0
    elif r > 180.0:
        r -= 360.0
    return r


def pose_matrix(x: float, y: float, rot: float, mirrored: bool = False,
                scale: float = 1.0) -> QTransform:
    """Local -> scene ``QTransform`` for a block pose (design DD2).

    Args:
        x: Insertion point x (scene mm).
        y: Insertion point y (scene mm).
        rot: Rotation, Y-up CCW degrees.
        mirrored: Local x -> -x applied first (innermost).
        scale: Uniform scale (> 0).

    Returns:
        The pose transform.
    """
    t = QTransform()
    t.translate(float(x), float(y))
    t.rotate(-float(rot))                       # Qt CW+, app Y-up CCW+
    t.scale(-float(scale) if mirrored else float(scale), float(scale))
    return t


def reflect_pose(rot: float, mirrored: bool, theta: float) -> tuple[float, bool]:
    """Pose (rotation, mirrored) after reflecting across an axis (design DD3).

    ``Refl_theta . R(a) . M = R(2 theta + 180 - a) . M . M``. The caller
    reflects the insertion point itself.

    Args:
        rot: Current Y-up CCW rotation, degrees.
        mirrored: Current mirror flag.
        theta: Y-up heading of the reflection axis, degrees.

    Returns:
        ``(rot, mirrored)`` of the reflected pose.
    """
    return norm_deg(2.0 * float(theta) + 180.0 - float(rot)), not mirrored


def decompose_pose(t: QTransform) -> tuple[float, float, float, bool, float]:
    """Inverse of ``pose_matrix`` for a similarity *t* (design DD9).

    Args:
        t: A similarity transform (rotation, uniform scale, optional flip).

    Returns:
        ``(x, y, rot, mirrored, scale)``.
    """
    det = t.m11() * t.m22() - t.m12() * t.m21()
    mirrored = det < 0
    scale = 1.0 if abs(abs(det) - 1.0) < 1e-12 else math.sqrt(abs(det))
    o = t.map(QPointF(0.0, 0.0))
    ex = t.map(QPointF(1.0, 0.0))
    vx, vy = ex.x() - o.x(), ex.y() - o.y()
    if mirrored:                                # undo the innermost x flip
        vx, vy = -vx, -vy
    rot = math.degrees(math.atan2(-vy, vx))     # scene Y-down -> Y-up
    return o.x(), o.y(), norm_deg(rot), mirrored, scale


def is_upright(angle: float) -> bool:
    """True when a text baseline at Y-up *angle* reads upright: (-90, 90].

    Args:
        angle: Baseline angle, Y-up degrees.
    """
    a = norm_deg(angle)
    return -90.0 < a <= 90.0
