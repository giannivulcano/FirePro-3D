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

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem

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

    # ── Rect primitive (3-step: corner → size → rotate) ─────────────────────

    def _clear_wall_rect_ref_lines(self) -> None:
        """Remove wall-rect rotate-step reference guides from the scene."""
        for attr in ("_wall_rect_ref_line0", "_wall_rect_ref_lineA"):
            line = getattr(self._scene, attr, None)
            if line is not None:
                if line.scene() is self._scene:
                    self._scene.removeItem(line)
                setattr(self._scene, attr, None)

    def _update_wall_rect_ref_lines(self, angle_deg) -> None:
        """Point the two wall-rect rotate-step guides from the pivot.

        Mirrors ``_update_rect_ref_lines``: a 0° datum + the live sweep line at
        ``angle_deg``, both diagonal-length so they frame the sized rectangle.
        A no-op until both guides and the sized rect exist.
        """
        piv = self._scene._wall_rect_pivot
        if (piv is None or self._scene._wall_rect_ref_line0 is None
                or self._scene._wall_rect_ref_lineA is None
                or self._scene._wall_rect_sized_pt1 is None
                or self._scene._wall_rect_sized_pt2 is None):
            return
        p1, p2 = self._scene._wall_rect_sized_pt1, self._scene._wall_rect_sized_pt2
        length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        rad = math.radians(angle_deg)
        self._scene._wall_rect_ref_line0.setLine(piv.x(), piv.y(),
                                                 piv.x() + length, piv.y())
        self._scene._wall_rect_ref_lineA.setLine(
            piv.x(), piv.y(),
            piv.x() + length * math.cos(rad),
            piv.y() - length * math.sin(rad))   # Y-up: subtract sin

    def _move_wall_rect(self, event, snapped):
        """Mouse-move preview for the wall rectangle primitive.

        Rotate step: spins the preview rect + updates ref guides (mirrors
        ``_move_draw_rectangle`` rotate branch).  Sizing step: updates the
        axis-aligned preview rect and wall-thickness overlay (existing logic,
        now also handles centre mode via ``rect_sizing_points``).
        """
        sm = self._scene.scale_manager
        if self._scene._wall_rect_rotating:
            # Rotate step: spin the sized preview rect about the pivot.
            self._scene.preview_node.hide()
            self._scene.preview_pipe.hide()
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._scene._wall_rect_pivot is not None):
                snapped = self._scene._constrain_angle(self._scene._wall_rect_pivot, snapped)
            angle = self._wall_rect_rotation_angle_to(snapped)
            if self._scene._wall_rect_preview is not None and self._scene._wall_rect_pivot is not None:
                self._scene._wall_rect_preview.setTransformOriginPoint(self._scene._wall_rect_pivot)
                self._scene._wall_rect_preview.setRotation(-angle)   # Y-up CCW → Qt CW negate
            self._update_wall_rect_ref_lines(angle)
            self._scene.publish_placement_state(self._scene._wall_rect_pivot, snapped)
            return
        if self._scene._wall_rect_anchor is None:
            self._scene.update_preview_node(snapped)
        else:
            self._scene.preview_node.hide()
        self._scene.preview_pipe.hide()
        if self._scene._wall_rect_anchor is not None and self._scene._wall_rect_preview is not None:
            from .construction_geometry import rect_sizing_points
            anc = self._scene._wall_rect_anchor
            pt1, pt2 = rect_sizing_points(anc, snapped, self._scene._wall_rect_from_center)
            rect = QRectF(pt1, pt2).normalized()
            self._scene._wall_rect_preview.setRect(rect)
            self._scene._draw_dim_hint = (
                f"W: {sm.scene_to_display(rect.width())}  "
                f"H: {sm.scene_to_display(rect.height())}"
            )
            self._scene.publish_placement_state(anc, snapped)
            # -- Wall thickness preview (4 quads around rectangle) --
            if rect.width() > 1.0 and rect.height() > 1.0:
                if self._scene._wall_rect_thickness_preview is None:
                    self._scene._wall_rect_thickness_preview = QGraphicsPathItem()
                    _ppn = QPen(QColor("#aaaaaa"), 1, Qt.PenStyle.DashLine)
                    _ppn.setCosmetic(True)
                    self._scene._wall_rect_thickness_preview.setPen(_ppn)
                    _fill = QColor("#cccccc")
                    _fill.setAlpha(30)
                    self._scene._wall_rect_thickness_preview.setBrush(QBrush(_fill))
                    self._scene._wall_rect_thickness_preview.setZValue(199)
                    self._scene.addItem(self._scene._wall_rect_thickness_preview)
                _wtmpl = self._scene._get_wall_template()
                _ra = _wtmpl._alignment
                corners = [
                    QPointF(rect.x(), rect.y()),
                    QPointF(rect.x() + rect.width(), rect.y()),
                    QPointF(rect.x() + rect.width(), rect.y() + rect.height()),
                    QPointF(rect.x(), rect.y() + rect.height()),
                ]
                _pp = QPainterPath()
                for i in range(4):
                    p1 = corners[i]
                    p2 = corners[(i + 1) % 4]
                    q1l, q1r, q2r, q2l = compute_wall_quad(
                        p1, p2, _wtmpl._thickness_mm, _ra, sm)
                    _pp.moveTo(q1l)
                    _pp.lineTo(q2l)
                    _pp.lineTo(q2r)
                    _pp.lineTo(q1r)
                    _pp.closeSubpath()
                self._scene._wall_rect_thickness_preview.setPath(_pp)
                self._scene._wall_rect_thickness_preview.show()

    def _press_wall_rect(self, event, pos, snapped, item_under, node_under, pipe_under):
        """3-step wall-rectangle placement, mirroring ``_press_draw_rectangle``.

        Step 1 (no anchor): set anchor, create dashed preview.
        Step 2 (anchor set, not rotating): advance to rotate step via
            ``_advance_wall_rect_to_rotate_step``.
        Step 3 (rotating): commit 4 WallSegments at the rotation angle.
        """
        if self._scene._wall_rect_rotating:
            # Third click: commit at the pivot→cursor heading.
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._scene._wall_rect_pivot is not None):
                snapped = self._scene._constrain_angle(self._scene._wall_rect_pivot, snapped)
            self._commit_wall_rect_rotated(
                self._wall_rect_rotation_angle_to(snapped))
        elif self._scene._wall_rect_anchor is None:
            # First click: store anchor, show dashed preview rect.
            self._scene._wall_rect_anchor = snapped
            self._scene.update_preview_node(snapped)
            _instr = ("Pick corner (from centre)" if self._scene._wall_rect_from_center
                      else "Pick opposite corner for rectangular wall")
            self._scene.instructionChanged.emit(_instr)
            _tmpl = self._scene._get_wall_template()
            _wc = QColor(_tmpl._color)
            pen = QPen(_wc, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            preview.setPen(pen)
            _wc.setAlpha(30)
            preview.setBrush(QBrush(_wc))
            preview.setZValue(200)
            self._scene.addItem(preview)
            self._scene._wall_rect_preview = preview
        else:
            # Second click: size the axis-aligned rect and enter rotate step.
            self._advance_wall_rect_to_rotate_step(snapped)

    def _wall_rect_rotation_angle_to(self, cursor) -> float:
        """Return Y-up degrees from +x (pivot → cursor).  Falls back to 0°."""
        piv = self._scene._wall_rect_pivot
        if piv is None:
            return 0.0
        return math.degrees(math.atan2(-(cursor.y() - piv.y()),
                                       cursor.x() - piv.x()))

    def _advance_wall_rect_to_rotate_step(self, corner) -> bool:
        """Advance armed wall rect from sizing to rotate step.

        Mirrors ``_advance_rectangle_to_rotate_step``.  Computes the
        axis-aligned pt1/pt2 via ``rect_sizing_points``, rejects extents <0.5,
        stores state, snaps the preview rect, creates ref guides, emits
        instruction.

        Args:
            corner: The second placement point (fully snapped QPointF).

        Returns:
            True when the step advanced, False when refused (no anchor / too-small).
        """
        from .construction_geometry import rect_sizing_points
        anc = self._scene._wall_rect_anchor
        if anc is None:
            return False
        pt1, pt2 = rect_sizing_points(anc, corner, self._scene._wall_rect_from_center)
        if abs(pt2.x() - pt1.x()) < 0.5 or abs(pt2.y() - pt1.y()) < 0.5:
            self._scene._show_status("Wall rectangle too small — skipped", timeout=2000)
            return False
        self._scene._wall_rect_sized_pt1 = pt1
        self._scene._wall_rect_sized_pt2 = pt2
        self._scene._wall_rect_pivot = QPointF(anc)
        self._scene._wall_rect_rotating = True
        # Snap the preview to the sized rect.
        if self._scene._wall_rect_preview is not None:
            self._scene._wall_rect_preview.setRect(QRectF(pt1, pt2).normalized())
        # Clear thickness preview — it no longer applies during rotate step.
        if self._scene._wall_rect_thickness_preview is not None:
            if self._scene._wall_rect_thickness_preview.scene() is self._scene:
                self._scene.removeItem(self._scene._wall_rect_thickness_preview)
            self._scene._wall_rect_thickness_preview = None
        # Create rotation reference guides.
        self._clear_wall_rect_ref_lines()
        self._scene._wall_rect_ref_line0 = self._scene._make_ref_line()
        self._scene._wall_rect_ref_lineA = self._scene._make_ref_line()
        self._update_wall_rect_ref_lines(0.0)
        self._scene.clear_placement_state()
        self._scene.instructionChanged.emit("Pick rotation / type angle")
        return True

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
        from .construction_geometry import rotated_rect_corners
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
        self._scene._wall_rect_rotating = False
        self._scene._wall_rect_sized_pt1 = None
        self._scene._wall_rect_sized_pt2 = None
        self._scene._wall_rect_pivot = None
        self._scene.clear_placement_state()
        self._scene.push_undo_state()
        self._scene.instructionChanged.emit(
            "Pick centre point" if _from_centre else "Pick first corner")
        return True
