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

    def clear(self):
        """Idempotent teardown of design-area edit transient state.
        Called from Model_Space.set_mode on every mode change (safe when
        nothing is in progress)."""
        # Filled in Task 5.
        pass
