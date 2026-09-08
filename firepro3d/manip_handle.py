# firepro3d/manip_handle.py
"""Handle behavior abstraction for the SelectionManipulator (U2).

Governing spec: docs/specs/selection-manipulator.md (Unification §U2).
A ``Handle`` is a plain object describing one manipulator affordance: where it
sits, how it draws/hit-tests, and — via the drag lifecycle (Task 2) — what a
drag on it does. The manipulator (passed in as ``m``) owns drag STATE and the
held-preview toolkit; a Handle ORCHESTRATES that toolkit (rigid) or applies
live (U3 parametric). The manipulator never branches on drag model.

Rendering/event receipt lives in the ``_HandleItem`` QGraphicsItem host
(selection_manipulator.py), which forwards paint/shape/cursor/press here.
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QCursor, QPainter, QPainterPath, QPen

from .manip_math import (
    HandleRole, _ROLE_GEOM, _RESIZE_ROLES, _rect_point,
    resize_delta, rotate_delta,
)

# Corner roles render as circles; edge midpoints as squares (mockup style A).
_CORNER_ROLES = frozenset({
    HandleRole.TOP_LEFT, HandleRole.TOP_RIGHT,
    HandleRole.BOTTOM_LEFT, HandleRole.BOTTOM_RIGHT,
})


class Handle:
    """One manipulator affordance (behavior only; no Qt inheritance).

    Subclasses implement geometry/appearance and the drag lifecycle. ``m`` is
    the SelectionManipulator, exposing the Handle-facing context API.
    """

    role: HandleRole = HandleRole.ROTATE
    gesture_mode: str = ""            # "resize"/"rotate" — sets manip._mode
    hud_schema: Optional[str] = None  # DynamicInput schema name, or None

    # -- geometry / appearance (the host delegates to these) -----------------
    def scene_position(self, frame_rect: QRectF) -> QPointF:
        raise NotImplementedError

    def shape(self, *, size: float, grab_pad: float) -> QPainterPath:
        raise NotImplementedError

    def paint(self, painter: QPainter, *, size: float, border: QColor,
              fill: QColor, hover: bool) -> None:
        raise NotImplementedError

    def cursor(self, m) -> QCursor:
        raise NotImplementedError

    def visible(self, m) -> bool:
        raise NotImplementedError

    # -- drag lifecycle (Task 2 fills rigid subclasses) ----------------------
    def on_press(self, m) -> None:
        """Handle-specific press setup. The common held-preview snapshot is
        done by the manipulator's _begin; rigid handles need nothing extra."""

    def on_drag(self, m, scene_pos: QPointF, mods) -> None:
        raise NotImplementedError

    def on_release(self, m, scene_pos: QPointF, mods) -> None:
        raise NotImplementedError

    def on_cancel(self, m) -> None:
        """Default: nothing beyond the manipulator's transform restore."""

    def commit_typed(self, m, values: dict) -> None:
        raise NotImplementedError

    def hud_values(self, m) -> dict:
        return {}


class ResizeHandle(Handle):
    """One of the 8 box-native resize handles (held-preview → manip_scale)."""

    gesture_mode = "resize"
    hud_schema = "manip_resize"

    def __init__(self, role: HandleRole):
        self.role = role

    def scene_position(self, frame_rect: QRectF) -> QPointF:
        u, v, _, _ = _ROLE_GEOM[self.role]
        return _rect_point(frame_rect, u, v)

    def shape(self, *, size, grab_pad) -> QPainterPath:
        half = size / 2.0 + grab_pad
        path = QPainterPath()
        rect = QRectF(-half, -half, 2 * half, 2 * half)
        if self.role in _CORNER_ROLES:
            path.addEllipse(rect)     # corner = circle
        else:
            path.addRect(rect)        # midpoint = square
        return path

    def paint(self, painter, *, size, border, fill, hover):
        half = size / 2.0
        painter.setBrush(QBrush(border if hover else fill))
        rect = QRectF(-half, -half, size, size)
        if self.role in _CORNER_ROLES:
            painter.drawEllipse(rect)
        else:
            painter.drawRect(rect)

    def cursor(self, m) -> QCursor:
        return m._resize_cursor(self.role)

    def visible(self, m) -> bool:
        return m._show_scale_handles()

    def hud_values(self, m) -> dict:
        fx, fy = m._last_factors
        return {"Width": abs(m._R0.width() * fx),
                "Height": abs(m._R0.height() * fy)}


class RotateHandle(Handle):
    """The rotate knob above the top-edge midpoint (held-preview → manip_rotate)."""

    role = HandleRole.ROTATE
    gesture_mode = "rotate"
    hud_schema = "manip_rotate"

    def scene_position(self, frame_rect: QRectF) -> QPointF:
        return _rect_point(frame_rect, 0.5, 0.0)

    def shape(self, *, size, grab_pad) -> QPainterPath:
        from .selection_manipulator import _ROTATE_OFFSET_PX, _ROTATE_RADIUS_PX
        c = QPointF(0.0, -_ROTATE_OFFSET_PX)
        r = _ROTATE_RADIUS_PX + grab_pad
        path = QPainterPath()
        path.addEllipse(c, r, r)
        return path

    def paint(self, painter, *, size, border, fill, hover):
        from .selection_manipulator import _ROTATE_OFFSET_PX, _ROTATE_RADIUS_PX
        c = QPointF(0.0, -_ROTATE_OFFSET_PX)
        stem = QPen(QColor(border.red(), border.green(), border.blue(), 140), 1.0)
        painter.setPen(stem)
        painter.drawLine(QPointF(0, 0), c)
        painter.setPen(QPen(border, painter.pen().widthF() or 1.0))
        painter.setBrush(QBrush(border if hover else fill))
        painter.drawEllipse(c, _ROTATE_RADIUS_PX, _ROTATE_RADIUS_PX)

    def cursor(self, m) -> QCursor:
        return m._rotate_cursor

    def visible(self, m) -> bool:
        return m._show_rotate_knob()

    def hud_values(self, m) -> dict:
        return {}
