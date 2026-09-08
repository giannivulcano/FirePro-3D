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

    # -- drag lifecycle ------------------------------------------------------
    def on_drag(self, m, scene_pos, mods) -> None:
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        snapped = m._snap(scene_pos)
        d, fx, fy = resize_delta(m._B0, m._R0, self.role, m._start_scene, snapped,
                                 keep_aspect=shift, from_center=ctrl)
        m._last_factors = (fx, fy)
        m._apply(d)
        m._feed_hud(self.hud_values(m))

    def on_release(self, m, scene_pos, mods) -> None:
        moved = m._moved
        factors = m._last_factors
        m._restore_preview()
        m._end_drag()
        if moved:
            m._bake_scale([r[0] for r in m._items0_at_press], self.role,
                          factors, m._R0_at_press, m._B0_at_press)

    def commit_typed(self, m, values) -> None:
        from .dynamic_input import resolve_manip_resize
        res = resolve_manip_resize(None, values)
        w0, h0 = m._R0.width(), m._R0.height()
        fx = (res["width"] / w0) if w0 > 1e-12 else 1.0
        fy = (res["height"] / h0) if h0 > 1e-12 else 1.0
        if abs(fx - 1.0) > 1e-12 or abs(fy - 1.0) > 1e-12:
            m._bake_scale(m._typed_items, self.role, (fx, fy), m._typed_r0, m._typed_b0)


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

    # -- drag lifecycle ------------------------------------------------------
    def on_drag(self, m, scene_pos, mods) -> None:
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        center = m._B0.map(m._R0.center())
        snap = m._ROTATE_SNAP_DEG if shift else None
        d, total = rotate_delta(center, m._start_scene, scene_pos, m._base_angle, snap)
        m._apply(d)
        m._feed_hud({"Angle": -total})

    def on_release(self, m, scene_pos, mods) -> None:
        from .selection_manipulator import _yup_angle_from_delta
        from PyQt6.QtGui import QTransform
        d = QTransform(m._D)
        moved = m._moved
        m._restore_preview()
        m._end_drag()
        if moved:
            angle = _yup_angle_from_delta(d)
            if abs(angle) > 1e-9:
                pivot = m._B0_at_press.map(m._R0_at_press.center())
                m._bake_rotate([r[0] for r in m._items0_at_press], angle, pivot)

    def commit_typed(self, m, values) -> None:
        from .dynamic_input import resolve_manip_rotate
        angle = resolve_manip_rotate(None, values)["angle_deg"]
        if abs(angle) > 1e-9:
            pivot = m._typed_b0.map(m._typed_r0.center())
            m._bake_rotate(m._typed_items, angle, pivot)
