"""SprinklerWorkflowController — the sprinkler / design-area / hydraulic-run
concern extracted from ``Model_Space`` (decomposition slice 6).

A plain object (not a QObject) holding a back-ref to the scene. All scene-graph
mutation, signal emission, undo, and serialization stay on the scene and are
reached via ``self._scene``; this controller owns the sprinkler-placement,
design-area edit lifecycle, water-supply placement, and hydraulics-run behavior,
plus the design-area edit transient state.

Design: docs/superpowers/specs/2026-09-03-sprinkler-workflow-slice-design.md
Behavior (Rule A): docs/specs/sprinkler-system-components.md,
docs/specs/hydraulic-solver-and-reporting.md
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QTransform
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QGraphicsRectItem

from .node import Node
from .pipe import Pipe
from .water_supply import WaterSupply
from .design_area import DesignArea
from .display_manager import apply_category_defaults
from .constants import DEFAULT_LEVEL, DESIGN_AREA_HL_RADIUS_PX, Z_OVERLAY


class SprinklerWorkflowController:
    def __init__(self, scene):
        self._scene = scene
        # design-area edit transient (was Model_Space._da_*)
        self._da_editing = None
        self._design_area_corner1 = None
        self._design_area_rect_item = None
        self._da_highlights = []

    # ── Sprinkler CRUD ─────────────────────────────────────────────────────────

    def add_sprinkler(self, n, template=None):
        if n.has_sprinkler():
            return
        n.add_sprinkler()
        sprinkler = n.sprinkler
        self._scene.sprinkler_system.add_sprinkler(sprinkler)
        if template:
            sprinkler.set_properties(template)
        apply_category_defaults(sprinkler)
        sprinkler.setVisible(True)
        sprinkler.update()
        if n.has_fitting():
            n.fitting.update()
        for v in self._scene.views():
            v.viewport().update()
        return sprinkler

    def remove_sprinkler(self, n):
        sprinkler = n.sprinkler
        self._scene.removeItem(sprinkler)
        self._scene.sprinkler_system.remove_sprinkler(sprinkler)
        n.delete_sprinkler()

    # ── Auto-populate room with sprinklers ─────────────────────────────────

    def auto_populate_room(self, room, positions, sprinkler_record,
                           level, ceiling_level, sprinkler_offset,
                           design_density="0.10"):
        """Place sprinkler nodes at computed positions inside a room.

        Parameters
        ----------
        room : Room
            The target room.
        positions : list[QPointF]
            Scene-unit positions for each sprinkler.
        sprinkler_record : SprinklerRecord
            Database record to apply as template properties.
        level, ceiling_level : str
            Level names for the nodes.
        sprinkler_offset : float
            Offset from ceiling surface in mm (negative = below).
        design_density : str
            Design density string (gpm/ft²).
        """
        if not positions:
            return

        self._scene.push_undo_state()

        # Remove existing sprinklers in this room before placing new ones
        existing = room._detect_sprinklers()
        for spr in existing:
            node = spr.node
            if node is not None:
                # Remove the sprinkler from the node
                if node.sprinkler is spr:
                    node.delete_sprinkler()
                # If the node has no pipes, remove it entirely
                if not node.pipes:
                    self._scene.sprinkler_system.remove_node(node)
                    if node.scene() is self._scene:
                        self._scene.removeItem(node)

        # Compute the node ceiling_offset so the sprinkler ends up at
        # the correct absolute Z:
        #   ceiling_offset = sprinkler_offset - (ceil_level_elev - room_ceiling_elev)
        # This accounts for dropped ceilings where the room ceiling is
        # lower than the ceiling level.
        ceiling_offset = sprinkler_offset
        lm = self._scene._level_manager
        if lm is not None:
            ceil_lvl = lm.get(ceiling_level)
            if ceil_lvl is not None:
                ceil_level_elev = ceil_lvl.elevation
                zr = room.z_range_mm()
                if zr is not None:
                    room_ceiling_elev = max(zr)
                    ceiling_offset = sprinkler_offset - (ceil_level_elev - room_ceiling_elev)

        # Build a temporary Sprinkler as template for set_properties
        from .sprinkler import Sprinkler
        temp_spr = Sprinkler(None)
        temp_spr._properties["Manufacturer"]["value"] = sprinkler_record.manufacturer
        temp_spr._properties["Model"]["value"] = sprinkler_record.model
        temp_spr._properties["Orientation"]["value"] = sprinkler_record.type
        temp_spr._properties["K-Factor"]["value"] = str(sprinkler_record.k_factor)
        temp_spr._properties["Coverage Area"]["value"] = str(sprinkler_record.coverage_area)
        temp_spr._properties["Min Pressure"]["value"] = str(sprinkler_record.min_pressure)
        temp_spr._properties["Temperature"]["value"] = f"{sprinkler_record.temp_rating}°F"
        temp_spr._properties["Design Density"]["value"] = design_density
        # Level is a Node property, not a Sprinkler property — set on node below
        temp_spr._properties["Ceiling Level"]["value"] = ceiling_level
        temp_spr._properties["Ceiling Offset"]["value"] = str(ceiling_offset)

        count = 0
        for pt in positions:
            # Always create a NEW node — don't reuse existing nodes at
            # the same XY.  Stacked rooms need separate nodes at
            # different Z positions for the same XY location.
            node = Node(pt.x(), pt.y())
            self._scene.addItem(node)
            self._scene.sprinkler_system.add_node(node)
            # Set level, ceiling, and room assignment
            node.level = level
            node._room_name = room.name
            node.ceiling_level = ceiling_level
            node._properties["Ceiling Level"]["value"] = ceiling_level
            node.ceiling_offset = ceiling_offset
            node._properties["Ceiling Offset"]["value"] = str(ceiling_offset)
            node._recompute_z_pos()
            self.add_sprinkler(node, temp_spr)
            count += 1

        room_name = room.name or room._tag or "room"
        self._scene._show_status(f"Placed {count} sprinkler(s) in {room_name}.")

    # ── Design-area picks lifecycle ────────────────────────────────────────────

    @property
    def design_area_sprinklers(self) -> list:
        """Sprinklers from the active design area (backward compat)."""
        if self._scene.active_design_area:
            return list(self._scene.active_design_area.sprinklers)
        return []

    def _refresh_da_highlights(self):
        """Rebuild the per-sprinkler highlight rings for design_area mode.

        One fixed-screen-size ring per selected sprinkler of the active
        design area.  Self-clearing: outside design_area mode (or with no
        active area) it just removes existing rings.
        """
        sc = self._scene
        for it in self._da_highlights:
            if it.scene() is sc:
                sc.removeItem(it)
        self._da_highlights.clear()

        if sc.mode != "design_area" or not self._da_editing:
            return

        r = DESIGN_AREA_HL_RADIUS_PX
        for spr in self._da_editing.sprinklers:
            if not spr.node:
                continue
            ring = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
            ring.setPos(spr.node.scenePos())
            pen = QPen(QColor(255, 140, 0), 2)
            pen.setCosmetic(True)
            ring.setPen(pen)
            ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            ring.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            ring.setZValue(Z_OVERLAY)
            ring.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            sc.addItem(ring)
            self._da_highlights.append(ring)

    def _ensure_editing_da(self, resume_spr=None):
        """Return the design area picks modify, creating or resuming one.

        With no working area: if *resume_spr* already belongs to a design
        area, editing resumes on that one; otherwise a new area starts.
        Confirming (right-click) clears the working area so the next pick
        starts a fresh one — this is how multiple design areas are made.
        """
        sc = self._scene
        if self._da_editing is not None:
            return self._da_editing
        da = None
        if resume_spr is not None:
            da = next((d for d in sc.design_areas
                       if resume_spr in d.sprinklers), None)
        if da is None:
            da = DesignArea()
            da.level = getattr(sc, "active_level", DEFAULT_LEVEL)
            sc.addItem(da)
            apply_category_defaults(da)
            da.sync_z_for_mode(editing=True)
            sc.design_areas.append(da)
        self._da_editing = da
        sc.active_design_area = da
        return da

    def _da_change_committed(self, da, confirmed=False):
        """Shared tail for every design-area mutation: recompute, refresh
        rings, live property panel, browser/dirty signal, status tally."""
        sc = self._scene
        da.compute_area(sc.scale_manager)
        self._refresh_da_highlights()
        sc.requestPropertyUpdate.emit(da)
        sc.sceneModified.emit()
        count = len(da.sprinklers)
        area = da._properties.get("Area", {}).get("value", "0")
        if confirmed:
            sc._show_status(
                f"Design area confirmed: {count} sprinkler(s), {area}. "
                f"Click a sprinkler to start a new design area.")
        else:
            sc._show_status(
                f"Design area: {count} sprinkler(s), {area}. "
                f"Click more or right-click to confirm.")

    def confirm_design_area(self) -> bool:
        """Right-click confirm: lock the working area; next pick starts a new one.
        Returns True if an area was confirmed."""
        sc = self._scene
        da = self._da_editing or sc.active_design_area
        if da and da.sprinklers:
            sc.active_design_area = da
            self._da_editing = None
            self._da_change_committed(da, confirmed=True)
            return True
        return False

    # ── Water-supply placement ─────────────────────────────────────────────────

    def press_water_supply(self, event, pos, snapped, item_under, node_under, pipe_under):
        sc = self._scene
        # Require direct click on a node or pipe (no proximity fallback)
        if isinstance(item_under, Node):
            target_node = item_under
        elif isinstance(item_under, Pipe):
            target_node = sc.split_pipe(
                item_under,
                sc.project_click_onto_pipe_segment(snapped, item_under),
            )
        else:
            sc._show_status("Click on a node or pipe to place water supply")
            return

        if target_node is None:
            sc._show_status("Click on a node or pipe to place water supply")
            return

        if sc.water_supply_node is not None:
            sc.removeItem(sc.water_supply_node)
        ws = WaterSupply(target_node.scenePos().x(), target_node.scenePos().y())
        sc.addItem(ws)
        sc.water_supply_node = ws
        sc.sprinkler_system.supply_node = ws
        sc.requestPropertyUpdate.emit(ws)
        sc.push_undo_state()
        sc.set_mode(None)

    # ── Design-area click handlers ─────────────────────────────────────────────

    def press_design_area(self, event, pos, snapped, item_under, node_under, pipe_under):
        sc = self._scene
        modifiers = event.modifiers() if hasattr(event, 'modifiers') else Qt.KeyboardModifier.NoModifier
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if shift:
            # Shift+click: rectangle selection mode
            if self._design_area_corner1 is None:
                self._design_area_corner1 = snapped
                rect_item = QGraphicsRectItem(QRectF(snapped, snapped))
                rect_item.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
                rect_item.setBrush(QBrush(QColor(255, 200, 0, 40)))
                rect_item.setZValue(2)
                sc.addItem(rect_item)
                self._design_area_rect_item = rect_item
                sc._show_status("Shift+click second corner to complete rectangle.")
            else:
                c1 = self._design_area_corner1
                selection_rect = QRectF(c1, snapped).normalized()
                active = getattr(sc, "active_level", DEFAULT_LEVEL)
                selected_sprs = [
                    s for s in sc.sprinkler_system.sprinklers
                    if s.node and selection_rect.contains(s.node.scenePos())
                    and getattr(s.node, "level", DEFAULT_LEVEL) == active
                ]
                # Remove the temporary preview rect
                if self._design_area_rect_item and self._design_area_rect_item.scene() is sc:
                    sc.removeItem(self._design_area_rect_item)
                self._design_area_rect_item = None
                self._design_area_corner1 = None
                # Add to the working design area (create/resume as needed)
                da = self._ensure_editing_da()
                for s in selected_sprs:
                    da.add_sprinkler(s)
                self._da_change_committed(da)
        else:
            # Normal click: toggle the nearest sprinkler on the active level.
            # Routes through SnapEngine (center-only whitelist, sprinkler nodes
            # only) so the pick aperture stays zoom-invariant and consistent
            # with the rest of the snap system.  OSNAP toggle is overridden so
            # design-area picking always works regardless of the F3 setting.
            active = getattr(sc, "active_level", DEFAULT_LEVEL)
            _view = sc._snap_view()
            xform = _view.transform() if _view is not None else QTransform()
            node_to_spr = {spr.node: spr for spr in sc.sprinkler_system.sprinklers
                           if spr.node is not None
                           and getattr(spr.node, "level", DEFAULT_LEVEL) == active}
            target_spr = None
            _was_enabled = sc._snap_engine.enabled
            _was_center = sc._snap_engine.snap_center
            sc._snap_engine.enabled = True
            sc._snap_engine.snap_center = True
            try:
                result = sc._snap_engine.find(
                    pos, sc, xform,
                    only_types={"center"},
                    item_filter=lambda it: it in node_to_spr)
            finally:
                sc._snap_engine.enabled = _was_enabled
                sc._snap_engine.snap_center = _was_center
            if result is not None:
                target_spr = node_to_spr.get(result.source_item)
            if target_spr:
                da = self._ensure_editing_da(resume_spr=target_spr)
                da.toggle_sprinkler(target_spr)
                self._da_change_committed(da)
            else:
                sc._show_status("No sprinkler found. Click on a sprinkler to add/remove it.")

    def move_design_area(self, event, snapped):
        sc = self._scene
        sc.preview_node.hide()
        sc.preview_pipe.hide()
        if self._design_area_corner1 is not None and self._design_area_rect_item is not None:
            c1 = self._design_area_corner1
            rect = QRectF(c1, snapped).normalized()
            self._design_area_rect_item.setRect(rect)

    # ── Mode z/style resync + idempotent teardown ──────────────────────────────

    def sync_design_area_z(self, entering_da_mode: bool):
        """Mode-dependent DA z/style resync (was set_mode Site A)."""
        for _da in self._scene.design_areas:
            _da.sync_z_for_mode(entering_da_mode)
            _da.update()

    def clear(self):
        """Idempotent design-area edit teardown (was set_mode Site B)."""
        self._da_editing = None
        self._refresh_da_highlights()      # self-clearing outside design_area mode
        self._design_area_corner1 = None
        if self._design_area_rect_item is not None:
            if self._design_area_rect_item.scene() is self._scene:
                self._scene.removeItem(self._design_area_rect_item)
            self._design_area_rect_item = None

    # ── Hydraulics ─────────────────────────────────────────────────────────────

    def run_hydraulics(self, design_sprinklers=None):
        """Run the Hazen-Williams solver and store results for overlay display."""
        from .hydraulic_solver import HydraulicSolver
        solver = HydraulicSolver(self._scene.sprinkler_system, self._scene.scale_manager)
        result = solver.solve(design_sprinklers=design_sprinklers)
        # Prepend design-area spacing violations — the report renders
        # messages at the top, so listing violations lead the output.
        da = self._scene.active_design_area
        if da is not None and getattr(da, "spacing_warnings", None):
            result.messages[:0] = da.spacing_warnings
        if da is not None:
            crit = da.effective_criteria()
            if crit.warnings:
                result.messages[:0] = crit.warnings
            remote_psi = min(
                (result.required_node_pressures.get(s.node, 0.0)
                 for s in da.sprinklers if s.node), default=0.0)
            da.set_hydraulic_snapshot({
                "total_demand_gpm": result.total_demand,
                "demand_psi": result.required_pressure,
                "remote_head_psi": remote_psi,
                "sprinklers_calculated": len(design_sprinklers or []),
                "hose_gpm": getattr(result, "hose_stream_gpm", 0.0),
            } if (result.passed or result.node_pressures) else None)
        self._scene.hydraulic_result = result
        self._scene._supply_network_node = getattr(solver, '_supply_node', None)
        # Refresh all pipe labels and node badges
        for pipe in self._scene.sprinkler_system.pipes:
            pipe.update_label()
            pipe.update()
        from .hydraulic_node_badge import best_position_for_node

        # Group major nodes by 2D scene position to detect overlaps (vertical drops)
        pos_groups: dict[tuple, list] = {}
        for node in self._scene.sprinkler_system.nodes:
            node.remove_hydraulic_badge()
            label = result.node_labels.get(node) if hasattr(result, 'node_labels') else None
            # Only create badges for major nodes (purely numeric labels)
            if label is not None and label.isdigit():
                sp = node.scenePos()
                key = (round(sp.x(), 0), round(sp.y(), 0))
                pos_groups.setdefault(key, []).append(node)

        for nodes_at_pos in pos_groups.values():
            # All nodes at this 2D position share auto-position, stack vertically
            pos_label = best_position_for_node(nodes_at_pos[0])
            for stack_idx, node in enumerate(nodes_at_pos):
                nn = result.node_numbers[node]
                p_actual = result.node_pressures.get(node, 0.0)
                p_required = result.required_node_pressures.get(node, 0.0)
                q_out = 0.0
                if node.has_sprinkler():
                    try:
                        k = float(node.sprinkler._properties.get(
                            "K-Factor", {}).get("value", 5.6))
                    except (ValueError, TypeError):
                        k = 5.6
                    q_out = k * math.sqrt(max(p_actual, 0.0))
                q_total = 0.0
                for pipe in node.pipes:
                    pf = abs(result.pipe_flows.get(pipe, 0.0))
                    if pf > q_total:
                        q_total = pf
                label = result.node_labels.get(node, str(nn)) if hasattr(result, 'node_labels') else str(nn)
                node.create_hydraulic_badge(nn, p_actual, p_required,
                                            q_out, q_total,
                                            position=pos_label,
                                            stack_index=stack_idx,
                                            stack_total=len(nodes_at_pos),
                                            node_label=label)

        for node in self._scene.sprinkler_system.nodes:
            node.update()
        return result

    def clear_hydraulics(self):
        """Remove the hydraulic results overlay."""
        self._scene.hydraulic_result = None
        for pipe in self._scene.sprinkler_system.pipes:
            pipe.update_label()
            pipe.update()
        for node in self._scene.sprinkler_system.nodes:
            node.remove_hydraulic_badge()
            node.update()

    def set_coverage_overlay(self, visible: bool):
        """Show or hide translucent coverage circles on all sprinkler nodes."""
        Node._coverage_visible = visible
        for node in self._scene.sprinkler_system.nodes:
            node.prepareGeometryChange()
            node.update()
