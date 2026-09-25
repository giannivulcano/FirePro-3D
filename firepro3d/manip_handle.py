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
from PyQt6.QtGui import (
    QBrush, QColor, QCursor, QPainter, QPainterPath, QPen, QTransform,
)

from .manip_math import (
    HandleRole, _ROLE_GEOM, _RESIZE_ROLES, _rect_point,
    resize_delta,
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

    role: HandleRole                  # set by every concrete subclass
    gesture_mode: str = ""            # "resize"/"grip" — sets manip._mode
    hud_schema: Optional[str] = None  # DynamicInput schema name, or None

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
        m._last_from_center = ctrl   # bake must anchor about the same point the preview did
        m._apply(d)
        m._feed_hud(self.hud_values(m))

    def on_release(self, m, scene_pos, mods) -> None:
        moved = m._moved
        factors = m._last_factors
        from_center = m._last_from_center
        m._restore_preview()
        m._end_drag()
        if moved:
            m._bake_scale([r[0] for r in m._items0_at_press], self.role,
                          factors, m._R0_at_press, m._B0_at_press,
                          from_center=from_center)

    def commit_typed(self, m, values) -> None:
        from .dynamic_input import resolve_manip_resize
        res = resolve_manip_resize(None, values)
        w0, h0 = m._R0.width(), m._R0.height()
        fx = (res["width"] / w0) if w0 > 1e-12 else 1.0
        fy = (res["height"] / h0) if h0 > 1e-12 else 1.0
        if abs(fx - 1.0) > 1e-12 or abs(fy - 1.0) > 1e-12:
            m._bake_scale(m._typed_items, self.role, (fx, fy), m._typed_r0, m._typed_b0)


class GripHandle(Handle):
    """A live-apply parametric grip (U3).

    Unlike the held-preview ResizeHandle, this handle mutates real
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
        shape() and paint() apply the SAME value so hit-test matches render."""
        if self.circular:
            return 0.0
        fn = getattr(self.item, "grip_render_angle", None)
        return 0.0 if fn is None else float(fn(self.index))

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
        # as the legacy grip path did (one picker: SNAP + ALIGN ranked together,
        # excluding this item; else grid).
        self._prev_grip_item = getattr(sc, "_grip_item", None)
        self._prev_grip_dragging = getattr(sc, "_grip_dragging", False)
        sc._grip_item = self.item
        sc._grip_dragging = True
        # Snapshot every grip point for an exact Esc restore.
        self._snapshot = list(self.item.grip_points())
        self._extra_snapshots(m)   # subclasses snapshot siblings if they mutate them

    def on_drag(self, m, scene_pos: QPointF, mods) -> None:
        sc = m.scene()
        self._raw_pt = QPointF(scene_pos)   # raw cursor, for _transform_point hooks (S2)
        # Snap parity: drive the scene's own grip-snap authority (one picker:
        # SNAP + ALIGN ranked together, excluding this item; else grid) via
        # the flags borrowed in on_press (``_cursor_point`` hook; a whole-item
        # move grip returns the raw cursor instead). Real Model_Space always
        # has it; a plain scene (headless test) falls back to the raw point.
        pt = self._cursor_point(sc, scene_pos)          # hook: cursor snap
        pt = self._transform_point(m, pt, mods)         # hook: Ctrl-constrain
        self._last_pt = QPointF(pt)                     # AC6: track for on_release dedup
        self._apply(pt, mods)                           # hook: press-time/modifier apply
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
            self._raw_pt = QPointF(scene_pos)
            pt = self._cursor_point(sc, scene_pos)
            pt = self._transform_point(m, pt, mods)
            # Re-apply only if the release point genuinely differs from the last
            # on_drag point. In normal use Qt delivers a final move at the
            # release position, so pt == last -> skip (avoids a double
            # _after_apply for future sibling-propagation overrides). AC6.
            if pt != getattr(self, "_last_pt", None):
                self._apply(pt, mods)
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
    def _cursor_point(self, sc, scene_pos: QPointF) -> QPointF:
        """The drag point before ``_transform_point``: the scene's grip-snap
        authority (``get_effective_position``) when present, else raw."""
        eff = getattr(sc, "get_effective_position", None)
        return eff(scene_pos) if eff is not None else QPointF(scene_pos)

    def _transform_point(self, m, pt: QPointF, mods) -> QPointF:
        return pt

    def _apply(self, pt: QPointF, mods) -> None:
        """Apply the (snapped, transformed) drag point. Subclasses override to
        use press-time state / modifiers (e.g. RectGripHandle). NOT used by
        on_cancel, which restores the snapshot via ``apply_grip`` directly."""
        self.item.apply_grip(self.index, pt)

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


class TranslateGripHandle(GripHandle):
    """A grip whose drag translates the whole item (a move grip).

    Every whole-item move grip is one: the LineItem midpoint, the
    Circle/Ellipse/RegularPolygon centre, the TextItem centre
    (``MOVE_GRIP_INDEX``), the WallSegment mid grip, and — composed with
    ``RectGripHandle`` — the RectangleItem centre (``RectTranslateGripHandle``).

    S2: the item's own snap points snap to geometry via a
    ``HandleSnapSession`` (anchor = this grip's press-time point); the closest
    handle hit is the ONLY snap: the grip gets no cursor / ALIGN / grid snap
    (``_cursor_point`` returns the raw cursor — handles only, user decision
    2026-09-25). The session is built lazily on the first ``_transform_point``
    — ``on_drag`` calls it before ``_apply``, so the item is still at rest — so
    a click without a drag pays no target collection. The marker it publishes
    on the scene is cleared on a no-hit frame, release or cancel. Cooperative: ``_transform_point`` runs the next class's hook first, so
    it composes with a subclass's own drag semantics.
    """

    def on_press(self, m) -> None:
        super().on_press(m)
        self._hs = None
        self._hs_built = False
        self._marker = None

    def _cursor_point(self, sc, scene_pos: QPointF) -> QPointF:
        """Handles only (user decision 2026-09-25): a whole-item move grip
        gets NO cursor / ALIGN / grid snap — the raw cursor — so only a
        handle hit (``_transform_point``) moves the item onto geometry."""
        return QPointF(scene_pos)

    def _handle_snap(self, m):
        """The gesture's HandleSnapSession, built on first use (item at rest).

        Built regardless of the snap toggles (they gate each frame's use, so a
        toggle flipped mid-drag just works); None when no snap engine / view is
        reachable (paper).
        """
        if not getattr(self, "_hs_built", False):
            self._hs_built = True
            sc = m.scene()
            engine = getattr(sc, "_snap_engine", None)
            view = m._view() if hasattr(m, "_view") else None
            if engine is not None and view is not None:
                from .handle_snap import HandleSnapSession
                self._hs = HandleSnapSession(engine, sc, view, [self.item],
                                             self._snapshot[self.index])
        return getattr(self, "_hs", None)

    def _transform_point(self, m, pt: QPointF, mods) -> QPointF:
        pt = super()._transform_point(m, pt, mods)
        raw = getattr(self, "_raw_pt", None)
        if raw is None:
            return pt
        sc = m.scene()
        if not (getattr(sc, "_snap_enabled", True)
                and getattr(getattr(sc, "_snap_engine", None), "enabled", True)):
            return pt
        hs = self._handle_snap(m)
        if hs is None:
            return pt
        hit = hs.best(raw)
        if hit is None:
            self._clear_own_marker(sc)   # no cursor pick replaces it any more
            return pt
        corrected, res = hit
        if hasattr(sc, "_snap_result"):
            sc._snap_result = res
            self._marker = res
        return corrected

    def on_release(self, m, scene_pos: QPointF, mods) -> None:
        sc = m.scene()
        super().on_release(m, scene_pos, mods)
        self._end_handle_snap(sc)

    def on_cancel(self, m) -> None:
        super().on_cancel(m)
        self._end_handle_snap(m.scene())

    def _end_handle_snap(self, sc) -> None:
        """Drop the session and clear the marker if it is still ours."""
        self._hs = None
        self._hs_built = False
        self._raw_pt = None
        self._clear_own_marker(sc)

    def _clear_own_marker(self, sc) -> None:
        """Clear the scene marker if it is still the one this grip published."""
        mine = getattr(self, "_marker", None)
        self._marker = None
        if (sc is not None and mine is not None
                and getattr(sc, "_snap_result", None) is mine):
            sc._snap_result = None
            for v in sc.views():
                v.viewport().update()


class RectGripHandle(GripHandle):
    """A ``RectangleItem`` grip: local-frame resize from the PRESS-time rect,
    Ctrl = symmetric about the centre, Shift = keep aspect (corners). Angle and
    pivot are untouched. Esc restores the whole rect (both sides may move).

    A rotated rect with a centre-following pivot (``_pivot is None``) has its
    pivot PINNED to the press-time centre (footprint unchanged at press) so the
    rotation origin cannot drift as the rect resizes — otherwise the held
    opposite corner/edge would move in scene. The scene→local mapping uses the
    press-time inverse rotation (taken after pinning). Esc restores the
    original ``_pivot`` (None) exactly."""

    def _extra_snapshots(self, m) -> None:
        it = self.item
        self._r0 = QRectF(it.rect())
        self._pivot_pinned = it._pivot is None and it._angle != 0.0
        if self._pivot_pinned:
            self._pivot0 = None
            it._pivot = QPointF(it.rect().center())
        inv, ok = it._rotation_transform().inverted()
        self._inv0 = inv if ok else QTransform()

    def _apply(self, pt: QPointF, mods) -> None:
        from .geometry_2d import rect_grip_resize
        it = self.item
        it.prepareGeometryChange()
        it.setRect(rect_grip_resize(
            self._r0, self.index, self._inv0.map(QPointF(pt)),
            bool(mods & Qt.KeyboardModifier.ControlModifier),
            bool(mods & Qt.KeyboardModifier.ShiftModifier)))

    def _restore_extra(self, m) -> None:
        self.item.prepareGeometryChange()
        self.item.setRect(QRectF(self._r0))
        if getattr(self, "_pivot_pinned", False):
            self.item._pivot = self._pivot0

    def on_release(self, m, scene_pos: QPointF, mods) -> None:
        # A click without a drag must leave the rect byte-identical: un-pin the
        # press-time pivot (a real drag keeps it pinned so the committed
        # footprint matches the preview).
        if not m._moved and getattr(self, "_pivot_pinned", False):
            self.item._pivot = self._pivot0
        super().on_release(m, scene_pos, mods)


class RectTranslateGripHandle(TranslateGripHandle, RectGripHandle):
    """The RectangleItem centre grip (index 8): ``RectGripHandle``'s press-time
    local-frame drag (``rect_grip_resize`` index 8 translates; rotated-rect
    pivot pinning + exact Esc restore) plus S2 handle snap."""


class EndpointGripHandle(GripHandle):
    """A ``GripHandle`` that Ctrl-angle-constrains its drag against a fixed
    opposite endpoint — the per-item semantics for 2-endpoint items (LineItem
    endpoints, and later WallSegment / GridlineItem endpoints), and for vertex
    chains (PolylineItem / FloorSlab / RoofItem vertices, anchored on the
    previous vertex — see ``vertex_chain_grip_handles``).

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


class ArcEndpointGripHandle(GripHandle):
    """An ``ArcItem`` start/end grip: the endpoint slides along the circle
    (centre, radius and the other endpoint fixed — ``ArcItem.apply_grip``).
    No modifier semantics. Snapshots the full arc data on press so Esc
    restores it byte-exactly (re-deriving the angle from the snapshot grip
    point would leave float noise)."""

    def __init__(self, item, index: int):
        super().__init__(item, index, circular=True)

    def _extra_snapshots(self, m) -> None:
        it = self.item
        self._arc0 = (QPointF(it._center), it._radius, it._start_deg,
                      it._span_deg)

    def _restore_extra(self, m) -> None:
        it = self.item
        c, r, st, sp = self._arc0
        it._center, it._radius = QPointF(c), r
        it._start_deg, it._span_deg = st, sp
        it._rebuild_path()


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


class GridlineGripHandle(EndpointGripHandle):
    """A ``GridlineItem`` grip.

    Every gridline grip carries multi-select **parallel-delta**: after each
    apply, the same scene-space delta is re-applied to the same grip index on
    every OTHER selected gridline (``scene._propagate_gridline_grip``). Because
    the drag mutates OTHER items, ``on_press`` snapshots them
    (``scene._snapshot_gridline_grips``) and ``on_cancel`` restores them
    (``scene._restore_gridline_grips``) — the base ``on_cancel`` restores only
    the dragged grip.

    Endpoints (0, 1) additionally Ctrl-angle-constrain against the opposite
    endpoint (inherited ``EndpointGripHandle`` behaviour, ``opposite_index`` set).
    Bubble-standoff grips (2, 3) pass ``opposite_index=None`` to skip the
    constrain — parity with the legacy path, which Ctrl-constrained endpoints
    only. All scene calls are duck-typed so a plain headless scene degrades to
    no-propagation / no-snapshot.
    """

    def __init__(self, item, index: int, opposite_index=None,
                 circular: bool = False):
        super().__init__(item, index, opposite_index, circular=circular)

    def _transform_point(self, m, pt, mods):
        # Capture the pre-apply position of THIS grip every frame (before
        # apply_grip in both on_drag and the on_release re-apply) so _after_apply
        # can compute the incremental scene delta to hand to the siblings.
        self._old_pt = QPointF(self.item.grip_points()[self.index])
        if self.opposite_index is None:
            return pt                       # bubble grips: no Ctrl-constrain
        return super()._transform_point(m, pt, mods)

    def _after_apply(self, m, applied_pt):
        prop = getattr(m.scene(), "_propagate_gridline_grip", None)
        old = getattr(self, "_old_pt", None)
        if prop is not None and old is not None:
            delta = QPointF(applied_pt.x() - old.x(), applied_pt.y() - old.y())
            prop(self.item, self.index, delta)

    def _extra_snapshots(self, m):
        snap = getattr(m.scene(), "_snapshot_gridline_grips", None)
        self._gl_snapshot = (snap(self.item, self.index)
                             if snap is not None else None)

    def _restore_extra(self, m):
        restore = getattr(m.scene(), "_restore_gridline_grips", None)
        if restore is not None and getattr(self, "_gl_snapshot", None):
            restore(self._gl_snapshot)


def default_grip_handles(item, circular: "frozenset[int] | set[int]" = frozenset(),
                         translate: "frozenset[int] | set[int]" = frozenset()):
    """Build the default live-apply ``GripHandle`` list for a U3-migrated item.

    One handle per ``item.grip_points()`` index, ``grip_hittable``-filtered (an
    item with no ``grip_hittable`` keeps every point). Handles render as squares
    except indices in *circular*, which render as round discs. House rule
    (2026-09-09 smoke): vertex/endpoint grips and centre/move grips render round;
    midpoint and other derived convenience grips stay square — each item passes
    the round indices (e.g. CircleItem ``{0}`` centre; PolylineItem all vertices;
    a future LineItem ``{0, 2}`` endpoints, leaving the midpoint square). This is
    the shared body of every item's ``manip_handles()``; per-item drag semantics
    live on ``GripHandle`` subclass hooks, not here. Indices in *translate* are
    whole-item move grips and get a ``TranslateGripHandle`` (S2 handle snap).
    """
    fn = getattr(item, "grip_hittable", None)
    out = []
    for i in range(len(item.grip_points())):
        if fn is not None and not fn(i):
            continue
        cls = TranslateGripHandle if i in translate else GripHandle
        out.append(cls(item, i, circular=(i in circular)))
    return out


def vertex_chain_grip_handles(item, closed: bool,
                              circular: "frozenset[int] | set[int] | None" = None):
    """Vertex grips that Ctrl-angle-constrain against the PREVIOUS vertex (S3a).

    For polyline / polygon vertex chains (PolylineItem, FloorSlab, RoofItem).
    An open chain's first vertex constrains against the next one (it has no
    previous); a closed chain wraps (vertex 0 constrains against n−1). Reuses
    ``EndpointGripHandle`` — the anchor is re-read live from ``grip_points()``
    each frame. ``grip_hittable``-filtered like ``default_grip_handles``;
    *circular* defaults to every vertex (house rule: vertex grips are round).

    Args:
        item: The vertex-chain item (``grip_points()`` = its vertices in order).
        closed: True if the chain wraps (closed polyline / polygon boundary).
        circular: Indices rendered round; ``None`` means all vertices.

    Returns:
        One handle per hittable vertex (``EndpointGripHandle`` when n >= 2).
    """
    n = len(item.grip_points())
    fn = getattr(item, "grip_hittable", None)
    circ = set(range(n)) if circular is None else set(circular)
    out = []
    for i in range(n):
        if fn is not None and not fn(i):
            continue
        if n < 2:
            out.append(GripHandle(item, i, circular=(i in circ)))
            continue
        if i > 0:
            opp = i - 1
        else:
            opp = n - 1 if closed else 1
        out.append(EndpointGripHandle(item, i, opposite_index=opp,
                                      circular=(i in circ)))
    return out
