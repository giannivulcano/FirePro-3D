"""GeometryDrawingController — concern #6's simple 2D-drawing primitives
extracted from ``Model_Space`` (decomposition slice 8).

A plain object (not a QObject) holding a back-ref to the scene. Unlike the
pipe/sprinkler/underlay controllers, this collaborator is a **behavior home**:
it owns NO state. All geometry drawing state — the persisted ``_draw_lines`` /
``_draw_rects`` / ``_draw_circles`` / ``_polylines`` lists AND every transient
anchor/preview/flag — stays on the scene (reached via ``self._scene``), because
the already-extracted ``PlacementInputCoordinator`` reads it. This controller
owns the Line / Rectangle / Circle / Polyline drawing *methods* and the single
idempotent ``clear()`` teardown.

Scope note: ``draw_gridline`` shares the line handlers but its item factory
(``_make_line_like``) stays scene-side (dual-concern with the gridline concern);
Arc + Polygon are deferred to Slice 9 (into this same controller).

Design: docs/superpowers/specs/2026-09-04-geometry-drawing-slice-design.md
Behavior (Rule A): docs/specs/2d-geometry.md
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem


class GeometryDrawingController:
    def __init__(self, scene):
        self._scene = scene

    def clear(self, new_mode) -> None:
        """Idempotent teardown for the simple-primitive draw modes.

        Absorbs the line/rect/circle/polyline branches of ``set_mode``'s teardown
        cascade. Each per-primitive guard is preserved verbatim (``if new_mode !=
        "<mode>": …``) so staying in a mode mid-placement still preserves that
        primitive's in-progress state. Operates on scene-side state via
        ``self._scene`` (behavior-home model). Populated in C3.
        """
        # Wired in C3 (set_mode teardown relocation).
