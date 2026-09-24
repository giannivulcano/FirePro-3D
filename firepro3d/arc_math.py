"""Pure circular-arc construction helpers.

Conventions (the ``ArcItem`` ones): scene points are Qt coords (Y-down);
angles are Y-up degrees CCW from +x (``atan2(-dy, dx)``); a point at angle θ on
a circle of radius r about c is ``(c.x + r·cosθ, c.y − r·sinθ)``. The chord
"left normal" ``n`` of a→b is ``(uy, −ux)`` in Qt coords (Y-up left).

One home for the End-Points arc placement and the ArcItem centre/endpoint grip
drags (2d-geometry.md §4, selection-manipulator.md U3 ArcItem).
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

_EPS = 1e-9


def _norm360(deg: float) -> float:
    """``deg % 360`` folded so a float-noise result of 360.0 reads as 0.0."""
    v = deg % 360.0
    return 0.0 if 360.0 - v < 1e-9 else v


def yup_angle(center: QPointF, p: QPointF) -> float:
    """Y-up degrees of *p* as seen from *center*."""
    return math.degrees(math.atan2(-(p.y() - center.y()), p.x() - center.x()))


def point_at(center: QPointF, radius: float, deg: float) -> QPointF:
    """Point at Y-up angle *deg* on the circle (*center*, *radius*)."""
    a = math.radians(deg)
    return QPointF(center.x() + radius * math.cos(a),
                   center.y() - radius * math.sin(a))


def chord_frame(a: QPointF, b: QPointF):
    """Return ``(midpoint, (nx, ny), half_chord)`` for chord a→b, or None if a≈b.

    ``(nx, ny)`` is the unit left normal of a→b (Y-up left) in Qt coords.
    """
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length < _EPS:
        return None
    ux, uy = dx / length, dy / length
    mid = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
    return mid, (uy, -ux), length / 2.0


def project_to_bisector(a: QPointF, b: QPointF, p: QPointF):
    """Project *p* onto the perpendicular bisector of a–b.

    Returns ``(centre, t)`` — the projected point and its signed distance from
    the chord midpoint along the left normal — or None when a≈b.
    """
    frame = chord_frame(a, b)
    if frame is None:
        return None
    m, (nx, ny), _ = frame
    t = (p.x() - m.x()) * nx + (p.y() - m.y()) * ny
    return QPointF(m.x() + t * nx, m.y() + t * ny), t


def arc_through_chord(a: QPointF, b: QPointF, center: QPointF,
                      bulge_sign: int):
    """Return ``(radius, start_deg, span_deg)`` of the arc between a and b
    about *center* whose midpoint lies on the *bulge_sign* side of the chord
    (+1 = along the left normal). *center* must lie on the bisector. The span
    is CCW-positive in (0, 360).
    """
    m, (nx, ny), _ = chord_frame(a, b)
    r = math.hypot(a.x() - center.x(), a.y() - center.y())
    ta, tb = yup_angle(center, a), yup_angle(center, b)
    ccw = (tb - ta) % 360.0                         # CCW sweep a → b
    mid = point_at(center, r, ta + ccw / 2.0)
    side = (mid.x() - m.x()) * nx + (mid.y() - m.y()) * ny
    if (side > 0) == (bulge_sign > 0):
        return r, _norm360(ta), ccw
    return r, _norm360(tb), 360.0 - ccw


def center_for_radius(a: QPointF, b: QPointF, radius: float, side_sign: int):
    """Centre on the a–b bisector with ``|centre − a| == radius`` on the
    *side_sign* side (+1 = left normal); None when radius < half chord or a≈b."""
    frame = chord_frame(a, b)
    if frame is None:
        return None
    m, (nx, ny), h = frame
    if radius < h - 1e-9:
        return None
    t = math.sqrt(max(radius * radius - h * h, 0.0))
    t = t if side_sign >= 0 else -t
    return QPointF(m.x() + t * nx, m.y() + t * ny)


def arc_from_three_points(p_start: QPointF, p_mid: QPointF, p_end: QPointF):
    """CCW arc from *p_start* through *p_mid* to *p_end*.

    Returns ``(centre, radius, start_deg, span_deg)``, or None when the points
    are collinear or *p_mid* is not on the CCW sweep start→end (the arc would
    have to run clockwise — callers hold the last valid shape).
    """
    ax, ay = p_start.x(), p_start.y()
    bx, by = p_mid.x(), p_mid.y()
    cx, cy = p_end.x(), p_end.y()
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-6:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    centre = QPointF(ux, uy)
    r = math.hypot(ax - ux, ay - uy)
    ts = yup_angle(centre, p_start)
    span = (yup_angle(centre, p_end) - ts) % 360.0
    if not ((yup_angle(centre, p_mid) - ts) % 360.0 < span):
        return None
    return centre, r, _norm360(ts), span
