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
from PyQt6.QtGui import (
    QBrush, QColor, QCursor, QPainter, QPainterPath, QPen, QTransform,
)

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
    _m = None                         # back-ref to the manipulator (set on attach)

    def _live_preview_rotation(self) -> float:
        """The manipulator's in-progress rotate-preview angle (Y-up deg), 0 when
        not rotating or unattached. Lets a screen-constant (ItemIgnores-
        Transformations) handle turn with the frame during the held-preview,
        before the release bake."""
        m = self._m
        fn = getattr(m, "_preview_rotation_deg", None) if m is not None else None
        return fn() if fn is not None else 0.0

    # -- geometry / appearance (the host delegates to these) -----------------
    def scene_position(self, frame_rect: QRectF) -> QPointF:
        raise NotImplementedError

    def shape(self, *, size: float, grab_pad: float) -> QPainterPath:
        raise NotImplementedError

    def paint(self, painter: QPainter, *, size: float, border: QColor,
              fill: QColor, hover: bool, border_width: float) -> None:
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

    def paint(self, painter, *, size, border, fill, hover, border_width):
        half = size / 2.0
        painter.setPen(QPen(border, border_width))
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
        ang = self._live_preview_rotation()
        if ang:
            # Swing the knob around the anchor with the frame during a rotate
            # preview (Qt y-down rotate is CW+; negate the Y-up angle).
            path = QTransform().rotate(-ang).map(path)
        return path

    def paint(self, painter, *, size, border, fill, hover, border_width):
        from .selection_manipulator import _ROTATE_OFFSET_PX, _ROTATE_RADIUS_PX
        ang = self._live_preview_rotation()
        painter.save()
        if ang:
            painter.rotate(-ang)            # stem+knob swing with the frame
        c = QPointF(0.0, -_ROTATE_OFFSET_PX)
        stem = QPen(QColor(border.red(), border.green(), border.blue(), 140), 1.0)
        painter.setPen(stem)
        painter.drawLine(QPointF(0, 0), c)
        painter.setPen(QPen(border, border_width))
        painter.setBrush(QBrush(border if hover else fill))
        painter.drawEllipse(c, _ROTATE_RADIUS_PX, _ROTATE_RADIUS_PX)
        painter.restore()

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


class GripHandle(Handle):
    """A live-apply parametric grip (U3).

    Unlike the held-preview ResizeHandle/RotateHandle, this handle mutates real
    geometry every move via ``item.apply_grip(index, pt)`` — the live-apply drag
    the U2 Handle contract was designed to admit. ``role`` is the non-rigid
    ``HandleRole.GRIP`` so the manipulator's rigid role dict never resolves it;
    the manipulator installs THIS handle in ``_begin_handle`` (U3 fix).
    """

    role = HandleRole.GRIP
    gesture_mode = "grip"       # deliberately NOT in _SCHEMA_FOR_MODE -> no HUD
    hud_schema = None

    def __init__(self, item, index: int, circular: bool = False):
        self.item = item
        self.index = index
        # circular=True renders/hit-tests the handle as a disc (used for
        # centre/move grips) vs the default square (parametric point grips) —
        # mirrors the manipulator's corner-circle / edge-square convention.
        self.circular = circular

    # -- geometry / appearance -----------------------------------------------
    def scene_position(self, frame_rect: QRectF) -> QPointF:
        return self.item.grip_points()[self.index]

    def _render_angle(self) -> float:
        """Y-up degrees to rotate this grip's SQUARE by, so its edges align with
        the host item's orientation (e.g. an ellipse's axes) — radial alignment.
        Opt-in: the item implements ``grip_render_angle(index)`` (absent → 0,
        axis-aligned, the default for every unmigrated item). Ignored for circular
        grips (a disc is rotation-invariant). A square is symmetric under 90°/
        reflection, so the sign/exact-axis choice is visually immaterial; both
        shape() and paint() apply the SAME value so hit-test matches render.

        During a rotate held-preview the item's own angle isn't mutated until the
        release bake, so add the manipulator's LIVE preview rotation (0 unless a
        rotate is in progress) — the grips turn with the item as the knob drags,
        and because it's the same angle the bake applies there's no jump on
        commit. ``self._m`` (the manipulator) is set by the host on attach."""
        if self.circular:
            return 0.0
        fn = getattr(self.item, "grip_render_angle", None)
        base = 0.0 if fn is None else float(fn(self.index))
        return base + self._live_preview_rotation()

    def shape(self, *, size: float, grab_pad: float) -> QPainterPath:
        half = size / 2.0 + grab_pad
        path = QPainterPath()
        rect = QRectF(-half, -half, 2 * half, 2 * half)
        if self.circular:
            path.addEllipse(rect)
            return path
        path.addRect(rect)
        ang = self._render_angle()
        if ang:
            # Qt (y-down) rotate is CW+; negate the Y-up angle to match paint()
            # and the item's own get_closed_path (t.rotate(-rotation_deg)).
            path = QTransform().rotate(-ang).map(path)
        return path

    def paint(self, painter: QPainter, *, size, border, fill, hover,
              border_width) -> None:
        half = size / 2.0
        painter.setPen(QPen(border, border_width))
        painter.setBrush(QBrush(border if hover else fill))
        rect = QRectF(-half, -half, size, size)
        if self.circular:
            painter.drawEllipse(rect)
            return
        ang = self._render_angle()
        if ang:
            painter.save()
            painter.rotate(-ang)
            painter.drawRect(rect)
            painter.restore()
        else:
            painter.drawRect(rect)

    def cursor(self, m) -> QCursor:
        return QCursor(Qt.CursorShape.OpenHandCursor)

    def visible(self, m) -> bool:
        fn = getattr(self.item, "grip_hittable", None)
        return True if fn is None else bool(fn(self.index))

    # -- drag lifecycle (live-apply) -----------------------------------------
    def on_press(self, m) -> None:
        sc = m.scene()
        # Borrow the scene's grip-state so get_effective_position snaps exactly
        # as the legacy grip path does (OSNAP excl. this item > ALIGN > grid).
        self._prev_grip_item = getattr(sc, "_grip_item", None)
        self._prev_grip_dragging = getattr(sc, "_grip_dragging", False)
        sc._grip_item = self.item
        sc._grip_dragging = True
        # Snapshot every grip point for an exact Esc restore.
        self._snapshot = list(self.item.grip_points())
        self._extra_snapshots(m)   # subclasses snapshot siblings if they mutate them

    def on_drag(self, m, scene_pos: QPointF, mods) -> None:
        sc = m.scene()
        # Snap parity: drive the scene's own grip-snap authority (OSNAP excl.
        # this item > ALIGN > grid) via the flags borrowed in on_press. Real
        # Model_Space always has it; a plain scene (headless test) falls back
        # to the raw point.
        eff = getattr(sc, "get_effective_position", None)
        pt = eff(scene_pos) if eff is not None else QPointF(scene_pos)
        pt = self._transform_point(m, pt, mods)         # hook: Ctrl-constrain
        self._last_pt = QPointF(pt)                     # AC6: track for on_release dedup
        self.item.apply_grip(self.index, pt)
        applied = self.item.grip_points()[self.index]
        self._after_apply(m, applied)                   # hook: sibling / propagation
        tools = getattr(sc, "_tools", None)
        if tools is not None:
            tools._solve_constraints(self.item)
        m._reflow_live()

    def on_release(self, m, scene_pos: QPointF, mods) -> None:
        sc = m.scene()
        moved = m._moved
        # Apply the final mouse position: MouseButtonRelease bypasses _update,
        # so the last on_drag landed at the penultimate mouse position. Snap +
        # constrain the release point exactly as on_drag does so the committed
        # geometry matches where the user let go.
        if moved:
            eff = getattr(sc, "get_effective_position", None)
            pt = eff(scene_pos) if eff is not None else QPointF(scene_pos)
            pt = self._transform_point(m, pt, mods)
            # Re-apply only if the release point genuinely differs from the last
            # on_drag point. In normal use Qt delivers a final move at the
            # release position, so pt == last -> skip (avoids a double
            # _after_apply for future sibling-propagation overrides). AC6.
            if pt != getattr(self, "_last_pt", None):
                self.item.apply_grip(self.index, pt)
                self._after_apply(m, self.item.grip_points()[self.index])
        self._clear_grip_state(sc)
        m._end_drag()
        if moved:
            tools = getattr(sc, "_tools", None)
            if tools is not None:
                tools._solve_constraints(self.item)
            if m._commit_hook is not None:
                m._commit_hook("grip")

    def on_cancel(self, m) -> None:
        sc = m.scene()
        # Restore only the DRAGGED grip from its snapshot. Re-applying every grip
        # corrupts items whose apply_grip is index-dependent: LineItem's midpoint
        # grip translates the whole line, so replaying it mid-restore shifts the
        # endpoints. Only the dragged grip was mutated this gesture (a derived
        # grip like the midpoint recomputes from the endpoints); sibling /
        # propagated state on OTHER items is restored by _restore_extra.
        self.item.apply_grip(self.index, self._snapshot[self.index])
        self._restore_extra(m)
        self._clear_grip_state(sc)
        m._reflow_live()

    # -- extension points (no-ops here; wall/gridline PRs override) -----------
    def _transform_point(self, m, pt: QPointF, mods) -> QPointF:
        return pt

    def _after_apply(self, m, applied_pt: QPointF) -> None:
        pass

    def _extra_snapshots(self, m) -> None:
        pass

    def _restore_extra(self, m) -> None:
        pass

    # -- helpers -------------------------------------------------------------
    def _clear_grip_state(self, sc) -> None:
        sc._grip_item = getattr(self, "_prev_grip_item", None)
        sc._grip_dragging = getattr(self, "_prev_grip_dragging", False)


class EndpointGripHandle(GripHandle):
    """A ``GripHandle`` that Ctrl-angle-constrains its drag against a fixed
    opposite endpoint — the per-item semantics for 2-endpoint items (LineItem
    endpoints, and later WallSegment / GridlineItem endpoints).

    Under Ctrl the dragged point is projected onto the nearest angle increment
    ray from the opposite endpoint via the scene's ``_constrain_angle`` (the same
    authority the legacy grip path used, so behaviour is a faithful port). A
    plain scene (headless) with no ``_constrain_angle`` falls back to the raw
    point. ``opposite_index`` is the grip index of the anchor endpoint (for a
    LineItem: endpoint 0 ↔ 2; its midpoint grip stays a plain ``GripHandle``).
    """

    def __init__(self, item, index: int, opposite_index: int,
                 circular: bool = True):
        super().__init__(item, index, circular=circular)
        self.opposite_index = opposite_index

    def _transform_point(self, m, pt: QPointF, mods) -> QPointF:
        if not (mods & Qt.KeyboardModifier.ControlModifier):
            return pt
        constrain = getattr(m.scene(), "_constrain_angle", None)
        if constrain is None:
            return pt
        grips = self.item.grip_points()
        if self.opposite_index >= len(grips):
            return pt
        return constrain(grips[self.opposite_index], pt)


class WallEndpointGripHandle(EndpointGripHandle):
    """A ``WallSegment`` endpoint grip.

    Extends ``EndpointGripHandle`` (Ctrl-angle-constrain against the opposite
    endpoint) with the two wall-specific semantics that live in ``model_space``
    today:

    * **Propagation** — after each apply, every OTHER wall endpoint coincident
      with the endpoint's pre-move position follows to the new position
      (``scene._propagate_wall_endpoint``), keeping polyline-drawn walls joined.
    * **Atomic sibling Esc-restore** — Wall is the first migrated item whose drag
      mutates OTHER items, so it snapshots every other wall endpoint at press
      (``scene._snapshot_wall_endpoints``) and restores them on cancel
      (``scene._restore_wall_endpoints``); the base ``on_cancel`` only restores
      the dragged grip.

    All scene calls are duck-typed (``getattr``) so a plain headless scene with
    no wall graph degrades to no-propagation / no-snapshot.
    """

    def _transform_point(self, m, pt, mods):
        # Capture the endpoint position BEFORE this frame's apply_grip. Per-frame,
        # NOT the press snapshot: siblings follow every move, so the coincidence
        # test in propagation must run against where the endpoint was last frame,
        # not the gesture start. Runs before apply_grip in both on_drag and the
        # on_release re-apply, so _after_apply always has the correct old point.
        self._old_pt = QPointF(self.item.grip_points()[self.index])
        return super()._transform_point(m, pt, mods)

    def _after_apply(self, m, applied_pt):
        prop = getattr(m.scene(), "_propagate_wall_endpoint", None)
        old = getattr(self, "_old_pt", None)
        if prop is not None and old is not None:
            prop(self.item, old, applied_pt)

    def _extra_snapshots(self, m):
        snap = getattr(m.scene(), "_snapshot_wall_endpoints", None)
        self._wall_snapshot = snap(self.item) if snap is not None else None

    def _restore_extra(self, m):
        restore = getattr(m.scene(), "_restore_wall_endpoints", None)
        if restore is not None and getattr(self, "_wall_snapshot", None):
            restore(self._wall_snapshot)


def default_grip_handles(item, circular: "frozenset[int] | set[int]" = frozenset()):
    """Build the default live-apply ``GripHandle`` list for a U3-migrated item.

    One handle per ``item.grip_points()`` index, ``grip_hittable``-filtered (an
    item with no ``grip_hittable`` keeps every point). Handles render as squares
    except indices in *circular*, which render as round discs. House rule
    (2026-09-09 smoke): vertex/endpoint grips and centre/move grips render round;
    midpoint and other derived convenience grips stay square — each item passes
    the round indices (e.g. CircleItem ``{0}`` centre; PolylineItem all vertices;
    a future LineItem ``{0, 2}`` endpoints, leaving the midpoint square). This is
    the shared body of every item's ``manip_handles()``; per-item drag semantics
    live on ``GripHandle`` subclass hooks, not here.
    """
    fn = getattr(item, "grip_hittable", None)
    out = []
    for i in range(len(item.grip_points())):
        if fn is not None and not fn(i):
            continue
        out.append(GripHandle(item, i, circular=(i in circular)))
    return out
