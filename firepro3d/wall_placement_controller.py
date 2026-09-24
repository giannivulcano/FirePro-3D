"""WallPlacementController — concern #7's wall-placement behavior extracted
from ``Model_Space`` (decomposition slice 10, sub-commit C1: line/polyline).

A plain object (not a QObject) holding a back-ref to the scene. Like the
geometry-drawing controller (slices 8/9), this collaborator is a **behavior
home**: it owns NO state. Every ``_wall*`` transient AND the persisted
``_walls`` / ``_next_wall_num`` lists stay on the scene (reached via
``self._scene``), because the already-landed ``PlacementInputCoordinator`` reads
wall state and ``_walls`` is dual-serialized. This controller owns the wall
line/polyline placement *methods* only.

Scope note (C3): the rect-primitive handlers (C2), the HUD applier
(``_apply_wall_dynamic_input``), the variant setter (``_set_wall_primitive``),
and ``clear()``/``set_mode`` teardown now all live here. Scene-side callers keep
resolving through the class-level dispatch tables + scene shells; the two
non-contiguous ``set_mode`` wall blocks fold into idempotent ``clear(new_mode)``.

Design: docs/superpowers/specs/2026-09-05-wall-placement-slice-design.md (§5, C1)
Behavior (Rule A): docs/specs/wall-room-floor-system.md +
inferred-dimension-driven-placement.md §4
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem

from .constants import AUTO_JOIN_TOLERANCE, TEE_TOLERANCE
from .display_manager import apply_category_defaults
from .wall import WallSegment, compute_wall_quad
from .geometry_2d import (rect_side_ghost, rect_signed_depth,
                          rect_from_side_and_depth, apply_rect_ghost,
                          rotated_rect_corners)


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
                # Single-placement: a completed wall returns to Select selected
                # (a mid-chain polyline segment keeps drawing — the else branch).
                self._scene._end_placement_switch(wall)
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

    def _snapshot_wall_endpoints(self, exclude):
        """Snapshot every OTHER wall's two endpoints, for an atomic Esc-restore
        of a propagating endpoint-grip drag.

        Returns a list of ``(wall, endpoint_index, QPointF)`` covering both
        endpoints of every wall except *exclude* (the directly-dragged wall,
        whose dragged grip the base ``GripHandle.on_cancel`` restores itself).
        Snapshotting all others — not just the currently-coincident ones — keeps
        the restore correct even if the drag path sweeps the endpoint across a
        wall it was not joined to at press.

        Args:
            exclude: The wall being directly grip-dragged.
        """
        snap = []
        for w in self._scene._walls:
            if w is exclude:
                continue
            gp = w.grip_points()
            snap.append((w, 0, QPointF(gp[0])))
            snap.append((w, 1, QPointF(gp[1])))
        return snap

    def _restore_wall_endpoints(self, snapshot):
        """Restore endpoints captured by :meth:`_snapshot_wall_endpoints`.

        Args:
            snapshot: The ``(wall, index, QPointF)`` list to re-apply.
        """
        for w, idx, pt in snapshot:
            w.apply_grip(idx, QPointF(pt))

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
                _step = ("Pick centre point" if self._scene._wall_rect_from_center
                         else "Pick first corner")
            elif self._scene._wall_rect_side_pt is None:
                _step = ("Pick edge midpoint (width + angle)"
                         if self._scene._wall_rect_from_center
                         else "Pick first side (direction + width)")
            else:
                _step = "Pick depth (second side)"
            self._scene.instructionChanged.emit(
                f"{_step} [{self._scene._wall_alignment}]")
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

    # ── Rect primitive (3-click: base → side (angle + W) → depth (H); mirrors
    #    the 2D rect in GeometryDrawingController.  The committer
    #    _commit_wall_rect_rotated is unchanged) ───────────────────────────────

    def _clear_wall_rect_ref_lines(self) -> None:
        """Remove the wall-rect side guide from the scene."""
        line = self._scene._wall_rect_ref_line0
        if line is not None:
            if line.scene() is self._scene:
                self._scene.removeItem(line)
            self._scene._wall_rect_ref_line0 = None

    def _update_wall_rect_thickness_preview(self, corners) -> None:
        """Wrap the wall-thickness ghost around the 4 (rotated) *corners*."""
        s = self._scene
        if s._wall_rect_thickness_preview is None:
            s._wall_rect_thickness_preview = QGraphicsPathItem()
            _ppn = QPen(QColor("#aaaaaa"), 1, Qt.PenStyle.DashLine)
            _ppn.setCosmetic(True)
            s._wall_rect_thickness_preview.setPen(_ppn)
            _fill = QColor("#cccccc")
            _fill.setAlpha(30)
            s._wall_rect_thickness_preview.setBrush(QBrush(_fill))
            s._wall_rect_thickness_preview.setZValue(199)
            s.addItem(s._wall_rect_thickness_preview)
        _wtmpl = s._get_wall_template()
        _pp = QPainterPath()
        for i in range(4):
            q1l, q1r, q2r, q2l = compute_wall_quad(
                corners[i], corners[(i + 1) % 4], _wtmpl._thickness_mm,
                _wtmpl._alignment, s.scale_manager)
            _pp.moveTo(q1l)
            _pp.lineTo(q2l)
            _pp.lineTo(q2r)
            _pp.lineTo(q1r)
            _pp.closeSubpath()
        s._wall_rect_thickness_preview.setPath(_pp)
        s._wall_rect_thickness_preview.show()

    def _move_wall_rect(self, event, snapped):
        """Mouse-move preview for the 3-click wall rectangle.

        Side step: the side guide runs ``base → cursor`` (Ctrl angle-constrains
        from the base).  Depth step: the dashed ghost is fitted to the rotated
        rect via ``apply_rect_ghost`` and the wall-thickness overlay is rebuilt
        from its rotated corners.
        """
        s = self._scene
        s.preview_pipe.hide()
        base = s._wall_rect_anchor
        if base is None:
            s.update_preview_node(snapped)
            return
        s.preview_node.hide()
        side = s._wall_rect_side_pt
        if side is None:
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                snapped = s._constrain_angle(base, snapped)
            if s._wall_rect_ref_line0 is not None:
                a, b = rect_side_ghost(base, snapped, s._wall_rect_from_center)
                s._wall_rect_ref_line0.setLine(a.x(), a.y(), b.x(), b.y())
        else:
            sol = apply_rect_ghost(s._wall_rect_preview, base, side, snapped,
                                   s._wall_rect_from_center)
            if sol is not None:
                self._update_wall_rect_thickness_preview(
                    rotated_rect_corners(*sol))
        s.publish_placement_state(base, snapped)

    def _press_wall_rect(self, event, pos, snapped, item_under, node_under, pipe_under):
        """3-click wall-rectangle placement, mirroring ``_press_draw_rectangle``.

        1st click: base (anchor) + dashed ghost + side guide.
        2nd click: fix the first side (``_advance_wall_rect_to_depth_step``).
        3rd click: fix the depth and commit 4 walls
            (``_commit_wall_rect_depth_at``).
        """
        s = self._scene
        if s._wall_rect_anchor is None:
            s._wall_rect_anchor = QPointF(snapped)
            s.update_preview_node(snapped)
            s.instructionChanged.emit(
                "Pick edge midpoint (width + angle)" if s._wall_rect_from_center
                else "Pick first side (direction + width)")
            _tmpl = s._get_wall_template()
            _wc = QColor(_tmpl._color)
            pen = QPen(_wc, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            preview.setPen(pen)
            _wc.setAlpha(30)
            preview.setBrush(QBrush(_wc))
            preview.setZValue(200)
            s.addItem(preview)
            s._wall_rect_preview = preview
            self._clear_wall_rect_ref_lines()
            s._wall_rect_ref_line0 = s._make_ref_line()      # side guide
            s._wall_rect_ref_line0.setLine(snapped.x(), snapped.y(),
                                           snapped.x(), snapped.y())
        elif s._wall_rect_side_pt is None:
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                snapped = s._constrain_angle(s._wall_rect_anchor, snapped)
            self._advance_wall_rect_to_depth_step(snapped)
        else:
            self._commit_wall_rect_depth_at(snapped)

    def _advance_wall_rect_to_depth_step(self, side_pt) -> bool:
        """Fix the first side and enter the depth step.

        Shared by the mouse second click and the ``rect_side*`` HUD applier.

        Returns:
            True when the side was fixed, False when refused (no base, or a
            FULL side under 0.5 mm — the placement stays at the side step).
        """
        s = self._scene
        base = s._wall_rect_anchor
        if base is None:
            return False
        length = math.hypot(side_pt.x() - base.x(), side_pt.y() - base.y())
        if (2 * length if s._wall_rect_from_center else length) < 0.5:
            s._show_status("Wall rectangle side too small — pick again", timeout=2000)
            return False
        s._wall_rect_side_pt = QPointF(side_pt)
        if s._wall_rect_ref_line0 is not None:
            a, b = rect_side_ghost(base, side_pt, s._wall_rect_from_center)
            s._wall_rect_ref_line0.setLine(a.x(), a.y(), b.x(), b.y())
        # Zero-depth ghost: the fixed side, until the cursor gives it depth.
        apply_rect_ghost(s._wall_rect_preview, base, side_pt, side_pt,
                         s._wall_rect_from_center)
        s.clear_placement_state()
        s.instructionChanged.emit("Pick depth (second side)")
        return True

    def _commit_wall_rect_depth_at(self, cursor) -> bool:
        """Fix the depth from *cursor* and commit the 4 walls.

        Shared by the mouse third click and the ``rect_depth*`` HUD applier.

        Returns:
            True when committed, False when refused (unarmed, or a FULL extent
            under 0.5 mm — the placement stays at the depth step).
        """
        s = self._scene
        base, side = s._wall_rect_anchor, s._wall_rect_side_pt
        if base is None or side is None:
            return False
        sol = rect_from_side_and_depth(base, side,
                                       rect_signed_depth(base, side, cursor),
                                       s._wall_rect_from_center)
        if sol is None:
            s._show_status("Wall rectangle too small — pick again", timeout=2000)
            return False
        pt1, pt2, ang, piv = sol
        s._wall_rect_sized_pt1, s._wall_rect_sized_pt2, s._wall_rect_pivot = pt1, pt2, piv
        return self._commit_wall_rect_rotated(ang)

    def _commit_wall_rect_rotated(self, angle_deg) -> bool:
        """Commit the sized wall rectangle rotated to ``angle_deg`` about its pivot.

        Uses ``rotated_rect_corners`` to compute the 4 scene-space corners, then
        creates 4 ``WallSegment``s between consecutive corners (same template and
        auto-join loop as the old 2-click commit).  Clears all rect state and
        re-arms continuous placement.

        Args:
            angle_deg: Y-up CCW degrees from +x (the same convention as the
                2D-geo rect ``set_angle``).

        Returns:
            True when 4 walls were committed; False when sizing state is missing.
        """
        pt1 = self._scene._wall_rect_sized_pt1
        pt2 = self._scene._wall_rect_sized_pt2
        pivot = self._scene._wall_rect_pivot
        if pt1 is None or pt2 is None or pivot is None:
            return False
        corners = rotated_rect_corners(pt1, pt2, angle_deg, pivot)
        _tmpl = self._scene._get_wall_template()
        _rect_align = _tmpl._alignment
        walls_created = []
        for i in range(4):
            p1 = corners[i]
            p2 = corners[(i + 1) % 4]
            wall = WallSegment(p1, p2,
                               thickness_mm=_tmpl._thickness_mm,
                               color=_tmpl._color.name())
            wall.name = f"Wall {self._scene._next_wall_num}"
            self._scene._next_wall_num += 1
            wall._alignment = _rect_align
            wall._fill_mode = _tmpl._fill_mode
            wall.level = _tmpl.level if _tmpl.level else self._scene.active_level
            wall._base_level = _tmpl._base_level if _tmpl._base_level else self._scene.active_level
            wall._top_level = getattr(_tmpl, "_top_level", "")
            wall._height_mm = getattr(_tmpl, "_height_mm", 3048.0)
            self._scene._wall_alignment = _tmpl._alignment
            self._scene.addItem(wall)
            self._scene._walls.append(wall)
            apply_category_defaults(wall)
            walls_created.append(wall)
        for wall in walls_created:
            self._auto_join_wall(wall)
            wall.setSelected(True)
        for v in self._scene.views():
            v.viewport().update()
        # Clean up preview + ref guides
        if self._scene._wall_rect_preview is not None:
            if self._scene._wall_rect_preview.scene() is self._scene:
                self._scene.removeItem(self._scene._wall_rect_preview)
            self._scene._wall_rect_preview = None
        if self._scene._wall_rect_thickness_preview is not None:
            if self._scene._wall_rect_thickness_preview.scene() is self._scene:
                self._scene.removeItem(self._scene._wall_rect_thickness_preview)
            self._scene._wall_rect_thickness_preview = None
        self._clear_wall_rect_ref_lines()
        # Reset all rect state (re-arm continuous placement)
        _from_centre = self._scene._wall_rect_from_center
        self._scene._wall_rect_anchor = None
        self._scene._wall_rect_side_pt = None
        self._scene._wall_rect_sized_pt1 = None
        self._scene._wall_rect_sized_pt2 = None
        self._scene._wall_rect_pivot = None
        self._scene.clear_placement_state()
        self._scene.push_undo_state()
        self._scene.instructionChanged.emit(
            "Pick centre point" if _from_centre else "Pick first corner")
        # Single-placement: the completed rectangle (4 segments) returns to Select.
        self._scene._end_placement_switch(walls_created)
        return True

    # ── Variant setter ──────────────────────────────────────────────────────

    def _set_wall_primitive(self, prim, from_center=False):
        """Apply the wall primitive variant (called by _PLACEMENT_VARIANTS apply_fn).

        Sets ``_wall_primitive`` and, for the rect primitives, also sets
        ``_wall_rect_from_center`` so corner and center variants are distinct.
        """
        self._scene._wall_primitive = prim
        if prim == "rect":
            self._scene._wall_rect_from_center = from_center

    # ── HUD applier (typed commit) ──────────────────────────────────────────

    def _apply_wall_dynamic_input(self, geometry) -> bool:
        """Commit a typed wall placement via the same builders the mouse uses.

        ``geometry`` is the resolved QPointF (the line/rectangle placement
        schemas resolve to the point a click would produce), routed through the
        primitive's press handler for structural commit parity.

        Args:
            geometry: The scene-space target point resolved by the active schema.

        Returns:
            True always (the press handlers do not return a refusal; a too-short
            wall emits a status message and the anchor remains armed, matching
            mouse behaviour).
        """
        if self._scene._wall_primitive == "rect":
            # Both steps' schemas resolve to a QPointF: the side end / midpoint,
            # then a point at the typed depth along the side's left normal.
            if self._scene._wall_rect_side_pt is None:
                return self._advance_wall_rect_to_depth_step(geometry)
            return self._commit_wall_rect_depth_at(geometry)
        else:
            self._press_wall(None, geometry, geometry, None, None, None)
        return True

    # ── set_mode teardown ───────────────────────────────────────────────────

    def clear(self, new_mode):
        """Tear down wall-placement transient state when leaving 'wall' mode.

        Idempotent. _wall_alignment / _wall_primitive are session-sticky and NOT
        cleared (preserved exactly as the old set_mode did). Absorbs both
        non-contiguous set_mode wall blocks verbatim.
        """
        s = self._scene
        if new_mode != "wall":
            s._wall_anchor = None
            s._wall_chain_start = None
            if s._wall_preview_line is not None:
                if s._wall_preview_line.scene() is s:
                    s.removeItem(s._wall_preview_line)
                s._wall_preview_line = None
            if s._wall_preview_rect is not None:
                if s._wall_preview_rect.scene() is s:
                    s.removeItem(s._wall_preview_rect)
                s._wall_preview_rect = None
        if new_mode != "wall":
            s._wall_rect_anchor = None
            s._wall_rect_side_pt = None
            s._wall_rect_sized_pt1 = None
            s._wall_rect_sized_pt2 = None
            s._wall_rect_pivot = None
            self._clear_wall_rect_ref_lines()
            if s._wall_rect_preview is not None:
                if s._wall_rect_preview.scene() is s:
                    s.removeItem(s._wall_rect_preview)
                s._wall_rect_preview = None
            if s._wall_rect_thickness_preview is not None:
                if s._wall_rect_thickness_preview.scene() is s:
                    s.removeItem(s._wall_rect_thickness_preview)
                s._wall_rect_thickness_preview = None
