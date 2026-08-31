"""Pure transform math for the selection manipulator.

Ported verbatim from the SelectionBox prototype (FPD Design, 2026-08).
All functions are pure (QTransform/QRectF/QPointF in -> out) and are the
unit-tested core of resize/rotate/move gestures. Angles here follow Qt's
y-down screen convention; the Y-up (CCW+) app convention is applied at the
manipulator boundary, not in this module.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform


# --------------------------------------------------------------------------- #
#  Handle roles
# --------------------------------------------------------------------------- #

class HandleRole(Enum):
    TOP_LEFT = 0
    TOP = 1
    TOP_RIGHT = 2
    RIGHT = 3
    BOTTOM_RIGHT = 4
    BOTTOM = 5
    BOTTOM_LEFT = 6
    LEFT = 7
    ROTATE = 8


# role -> (u, v, out_x, out_y): unit position on the rect and outward direction
_ROLE_GEOM = {
    HandleRole.TOP_LEFT: (0.0, 0.0, -1, -1),
    HandleRole.TOP: (0.5, 0.0, 0, -1),
    HandleRole.TOP_RIGHT: (1.0, 0.0, 1, -1),
    HandleRole.RIGHT: (1.0, 0.5, 1, 0),
    HandleRole.BOTTOM_RIGHT: (1.0, 1.0, 1, 1),
    HandleRole.BOTTOM: (0.5, 1.0, 0, 1),
    HandleRole.BOTTOM_LEFT: (0.0, 1.0, -1, 1),
    HandleRole.LEFT: (0.0, 0.5, -1, 0),
}

_RESIZE_ROLES = tuple(_ROLE_GEOM.keys())


def _rect_point(rect: QRectF, u: float, v: float) -> QPointF:
    return QPointF(rect.left() + rect.width() * u, rect.top() + rect.height() * v)


# --------------------------------------------------------------------------- #
#  Pure transform math (unit-testable)
# --------------------------------------------------------------------------- #

def _scale_m(sx: float, sy: float) -> QTransform:
    return QTransform(sx, 0.0, 0.0, sy, 0.0, 0.0)


def _about(anchor: QPointF, m: QTransform) -> QTransform:
    """Apply matrix ``m`` about ``anchor`` (row-vector convention: A first)."""
    return (
        QTransform.fromTranslate(-anchor.x(), -anchor.y())
        * m
        * QTransform.fromTranslate(anchor.x(), anchor.y())
    )


def resize_factors(
    rect: QRectF,
    role: HandleRole,
    start_local: QPointF,
    cur_local: QPointF,
    keep_aspect: bool,
    from_center: bool,
    min_abs: float = 1e-6,
) -> Tuple[float, float, QPointF]:
    """Scale factors (fx, fy) and the local anchor for a resize drag.

    ``start_local``/``cur_local`` are the press and current positions in the
    box's local (unrotated) frame. Factors may go negative — dragging a handle
    through the opposite side mirrors the selection.
    """
    u, v, dx, dy = _ROLE_GEOM[role]
    anchor = rect.center() if from_center else _rect_point(rect, 1.0 - u, 1.0 - v)

    def axis_factor(cur: float, start: float, a: float) -> float:
        denom = start - a
        if abs(denom) < 1e-12:
            return 1.0
        f = (cur - a) / denom
        if abs(f) < min_abs:
            f = math.copysign(min_abs, f if f != 0 else 1.0)
        return f

    fx = axis_factor(cur_local.x(), start_local.x(), anchor.x()) if dx else 1.0
    fy = axis_factor(cur_local.y(), start_local.y(), anchor.y()) if dy else 1.0

    if keep_aspect:
        if dx and dy:  # corner: project the drag onto the press diagonal
            d0 = start_local - anchor
            den = d0.x() ** 2 + d0.y() ** 2
            if den > 1e-12:
                dc = cur_local - anchor
                s = (dc.x() * d0.x() + dc.y() * d0.y()) / den
                if abs(s) < min_abs:
                    s = math.copysign(min_abs, s if s != 0 else 1.0)
                fx = fy = s
        elif dx:
            fy = fx
        else:
            fx = fy
    return fx, fy, anchor


def resize_delta(
    box_tf: QTransform,
    rect: QRectF,
    role: HandleRole,
    start_scene: QPointF,
    cur_scene: QPointF,
    keep_aspect: bool,
    from_center: bool,
) -> Tuple[QTransform, float, float]:
    """Scene-space delta D for a resize drag, plus the factors used."""
    inv, ok = box_tf.inverted()
    if not ok:
        return QTransform(), 1.0, 1.0
    fx, fy, anchor = resize_factors(
        rect, role, inv.map(start_scene), inv.map(cur_scene), keep_aspect, from_center
    )
    t_local = _about(anchor, _scale_m(fx, fy))
    return inv * t_local * box_tf, fx, fy


def rotate_delta(
    center_scene: QPointF,
    start_scene: QPointF,
    cur_scene: QPointF,
    base_angle_deg: float,
    snap_deg: Optional[float],
) -> Tuple[QTransform, float]:
    """Scene-space delta D for a rotate drag and the new absolute angle.

    Snapping (when ``snap_deg``) snaps the *absolute* box angle, CAD-style.
    """
    a0 = math.degrees(math.atan2(start_scene.y() - center_scene.y(),
                                 start_scene.x() - center_scene.x()))
    a1 = math.degrees(math.atan2(cur_scene.y() - center_scene.y(),
                                 cur_scene.x() - center_scene.x()))
    d = a1 - a0
    total = base_angle_deg + d
    if snap_deg:
        total = round(total / snap_deg) * snap_deg
        d = total - base_angle_deg
    rot = QTransform()
    rot.rotate(d)
    total = (total + 180.0) % 360.0 - 180.0
    return _about(center_scene, rot), total


def move_delta(start_scene: QPointF, cur_scene: QPointF, ortho: bool) -> QTransform:
    """Scene-space delta D for a move drag (``ortho`` = axis lock)."""
    d = cur_scene - start_scene
    if ortho:
        if abs(d.x()) >= abs(d.y()):
            d.setY(0.0)
        else:
            d.setX(0.0)
    return QTransform.fromTranslate(d.x(), d.y())


def transform_angle_deg(m: QTransform) -> float:
    """Rotation of a transform's x axis, degrees, y-down positive clockwise."""
    v = m.map(QPointF(1.0, 0.0)) - m.map(QPointF(0.0, 0.0))
    return math.degrees(math.atan2(v.y(), v.x()))
