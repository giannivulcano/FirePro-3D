"""WallPlacementController — concern #7's wall-placement behavior extracted
from ``Model_Space`` (decomposition slice 10, sub-commit C1: line/polyline).

A plain object (not a QObject) holding a back-ref to the scene. Like the
geometry-drawing controller (slices 8/9), this collaborator is a **behavior
home**: it owns NO state. Every ``_wall*`` transient AND the persisted
``_walls`` / ``_next_wall_num`` lists stay on the scene (reached via
``self._scene``), because the already-landed ``PlacementInputCoordinator`` reads
wall state and ``_walls`` is dual-serialized. This controller owns the wall
line/polyline placement *methods* only.

Scope note (C1): the rect-primitive handlers, the HUD applier
(``_apply_wall_dynamic_input``), the variant setter (``_set_wall_primitive``),
and ``clear()``/``set_mode`` wiring are deferred to later sub-commits (C2/C3);
their scene-side callers keep resolving through the class-level dispatch tables
+ scene shells unchanged.

Design: docs/superpowers/specs/2026-09-05-wall-placement-slice-design.md (§5, C1)
Behavior (Rule A): docs/specs/wall-room-floor-system.md +
inferred-dimension-driven-placement.md §4
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem

from .constants import AUTO_JOIN_TOLERANCE, TEE_TOLERANCE
from .display_manager import apply_category_defaults
from .wall import WallSegment, compute_wall_quad


class WallPlacementController:
    def __init__(self, scene):
        self._scene = scene

    # ── Dispatch routers (branch on _wall_primitive) ────────────────────────

    def _press_wall_router(self, *args):
        """Dispatch a wall click to the active primitive's builder."""
        if self._scene._wall_primitive == "rect":
            return self._scene._press_wall_rect(*args)
        return self._press_wall(*args)

    def _move_wall_router(self, *args):
        """Dispatch a wall mouse-move to the active primitive's preview builder."""
        if self._scene._wall_primitive == "rect":
            return self._scene._move_wall_rect(*args)
        return self._move_wall(*args)

    # ── Line / polyline primitive ───────────────────────────────────────────

    def _move_wall(self, event, snapped):
        sm = self._scene.scale_manager
        if self._scene._wall_anchor is None:
            self._scene.update_preview_node(snapped)
            if self._scene._wall_preview_rect is not None:
                self._scene._wall_preview_rect.hide()
        else:
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._scene._constrain_angle(self._scene._wall_anchor, snapped)
            self._scene.preview_pipe.setLine(
                self._scene._wall_anchor.x(), self._scene._wall_anchor.y(),
                tip.x(), tip.y()
            )
            self._scene.preview_pipe.show()
            self._scene.preview_node.hide()
            _dx = tip.x() - self._scene._wall_anchor.x()
            _dy = tip.y() - self._scene._wall_anchor.y()
            _len = math.hypot(_dx, _dy)
            self._scene._draw_dim_hint = (
                f"L: {sm.scene_to_display(_len)}"
                if sm.is_calibrated else
                f"L: {_len:.0f}mm"
            )
            self._scene.publish_placement_state(self._scene._wall_anchor, tip)
            # -- Wall thickness preview rectangle --
            if _len > 1.0:  # avoid degenerate preview
                if self._scene._wall_preview_rect is None:
                    self._scene._wall_preview_rect = QGraphicsPathItem()
                    _ppn = QPen(QColor("#aaaaaa"), 1, Qt.PenStyle.DashLine)
                    _ppn.setCosmetic(True)
                    self._scene._wall_preview_rect.setPen(_ppn)
                    _fill = QColor("#cccccc")
                    _fill.setAlpha(30)
                    self._scene._wall_preview_rect.setBrush(QBrush(_fill))
                    self._scene._wall_preview_rect.setZValue(199)
                    self._scene.addItem(self._scene._wall_preview_rect)
                _wtmpl = self._scene._get_wall_template()
                p1l, p1r, p2r, p2l = compute_wall_quad(
                    self._scene._wall_anchor, tip, _wtmpl._thickness_mm,
                    _wtmpl._alignment, self._scene.scale_manager)
                _pp = QPainterPath()
                _pp.moveTo(p1l)
                _pp.lineTo(p2l)
                _pp.lineTo(p2r)
                _pp.lineTo(p1r)
                _pp.closeSubpath()
                self._scene._wall_preview_rect.setPath(_pp)
                self._scene._wall_preview_rect.show()

    def _press_wall(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._scene._wall_anchor is None:
            self._scene._wall_anchor = snapped
            self._scene._wall_chain_start = QPointF(snapped)
            self._scene.update_preview_node(snapped)
            self._scene.instructionChanged.emit(f"Pick wall end point [{self._scene._wall_alignment}]  Space=align")
        else:
            tip = snapped
            if event is not None and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                tip = self._scene._constrain_angle(self._scene._wall_anchor, snapped)
            # Close wall loop: if clicking near chain start → snap tip to start
            _close_loop = False
            if self._scene._wall_chain_start is not None:
                scale = self._scene._active_view_scale()
                tol = 15.0 / max(scale, 1e-6)
                d_start = math.hypot(tip.x() - self._scene._wall_chain_start.x(),
                                     tip.y() - self._scene._wall_chain_start.y())
                if d_start <= tol:
                    tip = QPointF(self._scene._wall_chain_start)
                    _close_loop = True
            _tmpl = self._scene._get_wall_template()
            wall = WallSegment(self._scene._wall_anchor, tip,
                               thickness_mm=_tmpl._thickness_mm,
                               color=_tmpl._color.name())
            wall.name = f"Wall {self._scene._next_wall_num}"
            self._scene._next_wall_num += 1
            wall._alignment = _tmpl._alignment
            wall._fill_mode = _tmpl._fill_mode
            wall.level = _tmpl.level if _tmpl.level else self._scene.active_level
            wall._base_level = _tmpl._base_level if _tmpl._base_level else self._scene.active_level
            wall._top_level = getattr(_tmpl, "_top_level", "")
            wall._height_mm = getattr(_tmpl, "_height_mm", 3048.0)
            # Keep scene alignment in sync with template
            self._scene._wall_alignment = _tmpl._alignment
            self._scene.addItem(wall)
            self._scene._walls.append(wall)
            apply_category_defaults(wall)
            # Auto-join: snap endpoints to nearby walls
            self._auto_join_wall(wall)
            wall.setSelected(True)
            for v in self._scene.views(): v.viewport().update()
            self._scene.preview_pipe.hide()
            if self._scene._wall_preview_rect is not None:
                self._scene._wall_preview_rect.hide()
            self._scene.push_undo_state()
            if _close_loop or self._scene._wall_primitive == "line":
                # Line variant: one segment then re-arm fresh.
                # Polyline: an explicit loop-close also stops the chain.
                self._scene._wall_anchor = None
                self._scene._wall_chain_start = None
                self._scene.instructionChanged.emit(
                    f"Pick wall start point [{self._scene._wall_alignment}]")
            else:
                # Polyline: end of this wall becomes start of next.
                self._scene._wall_anchor = QPointF(tip)
                self._scene.instructionChanged.emit(
                    f"Pick next wall end [{self._scene._wall_alignment}]  Space=align  Esc=stop")

    # ── Post-commit endpoint snap (miter / tee auto-join) ───────────────────

    def _auto_join_wall(self, wall: WallSegment,
                        tolerance: float = AUTO_JOIN_TOLERANCE):
        """Snap wall endpoints to nearby existing wall endpoints (miter join)
        and to mid-wall faces (tee join)."""

        # Track which endpoints have already been snapped (0=pt1, 1=pt2)
        snapped = set()

        # Pass 1: endpoint-to-endpoint (miter / corner join)
        for other in self._scene._walls:
            if other is wall:
                continue
            for my_idx in (0, 1):
                if my_idx in snapped:
                    continue
                my_pt = wall.pt1 if my_idx == 0 else wall.pt2
                hit = other.endpoint_near(my_pt, tolerance)
                if hit is not None:
                    target = other.pt1 if hit == 0 else other.pt2
                    wall.snap_endpoint_to(my_idx, target)
                    snapped.add(my_idx)
                    # Rebuild connected wall so its miter updates too
                    other._rebuild_path()
                    other.update()

        # Pass 2: tee join — snap unsnapped endpoints onto the host
        # wall's CENTERLINE (the point the user picked stays put; the
        # drawn body is coped back to the host face at render time by
        # WallSegment._tee_cope_corners).  The old face snap made the
        # picked point visibly "jump" off the centerline.
        for other in self._scene._walls:
            if other is wall:
                continue
            for my_idx in (0, 1):
                if my_idx in snapped:
                    continue
                my_pt = wall.pt1 if my_idx == 0 else wall.pt2
                cl_pt = other.nearest_centerline_point(my_pt, TEE_TOLERANCE)
                if cl_pt is not None:
                    wall.snap_endpoint_to(my_idx, cl_pt)
                    snapped.add(my_idx)

    # ── Grip-drag: propagate coincident endpoints ───────────────────────────

    def _propagate_wall_endpoint(self, moved, old_pt, new_pt) -> None:
        """Move every OTHER wall endpoint coincident with *old_pt* to *new_pt*.

        Polyline-drawn (or snapped-together) walls behave as joined: dragging a
        shared corner drags all its walls.  Proximity-based (no stored
        connectivity, no serialization change).  WallSegment endpoints only.

        Args:
            moved: The wall whose grip was directly dragged (excluded from scan).
            old_pt: The grip position before the drag move.
            new_pt: The grip position after the drag move.
        """
        eps = 0.5   # scene-unit anti-degeneracy tolerance (same family as snap)
        for w in self._scene._walls:
            if w is moved:
                continue
            for idx in (0, 1):
                gp = w.grip_points()[idx]
                if (abs(gp.x() - old_pt.x()) <= eps
                        and abs(gp.y() - old_pt.y()) <= eps):
                    w.apply_grip(idx, QPointF(new_pt))

    # ── Alignment cycle (Space) ─────────────────────────────────────────────

    def _cycle_wall_alignment(self) -> None:
        """Advance wall alignment Center → Left → Right and refresh the preview.

        Triggered by Spacebar via ``cycle_placement_ambiguity`` during wall
        placement.
        """
        _cycle = {"Center": "Left", "Left": "Right", "Right": "Center"}
        self._scene._wall_alignment = _cycle.get(self._scene._wall_alignment, "Center")
        if self._scene._wall_primitive == "rect":
            if self._scene._wall_rect_anchor is None:
                self._scene.instructionChanged.emit(
                    f"Pick first corner [{self._scene._wall_alignment}]")
            else:
                self._scene.instructionChanged.emit(
                    f"Pick opposite corner [{self._scene._wall_alignment}]")
        elif self._scene._wall_anchor is None:
            self._scene.instructionChanged.emit(
                f"Pick wall start point [{self._scene._wall_alignment}]  Space=align")
        else:
            self._scene.instructionChanged.emit(
                f"Pick wall end point [{self._scene._wall_alignment}]  Space=align")
        if self._scene._wall_template is not None:
            self._scene._wall_template._alignment = self._scene._wall_alignment
            self._scene.requestPropertyUpdate.emit(self._scene._wall_template)
        # Force preview rect to update without requiring mouse movement
        if (self._scene._wall_anchor is not None
                and self._scene._last_scene_pos is not None
                and self._scene._wall_preview_rect is not None):
            _wtmpl = self._scene._get_wall_template()
            p1l, p1r, p2r, p2l = compute_wall_quad(
                self._scene._wall_anchor, self._scene._last_scene_pos,
                _wtmpl._thickness_mm, _wtmpl._alignment,
                self._scene.scale_manager)
            _pp = QPainterPath()
            _pp.moveTo(p1l)
            _pp.lineTo(p2l)
            _pp.lineTo(p2r)
            _pp.lineTo(p1r)
            _pp.closeSubpath()
            self._scene._wall_preview_rect.setPath(_pp)
            for v in self._scene.views():
                v.viewport().update()
