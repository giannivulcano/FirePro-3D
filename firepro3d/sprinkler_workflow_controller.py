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

    def clear(self):
        """Idempotent teardown of design-area edit transient state.
        Called from Model_Space.set_mode on every mode change (safe when
        nothing is in progress)."""
        # Filled in Task 5.
        pass
