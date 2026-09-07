"""FeaturePlacementController — concern #7's Feature-placement behavior extracted
from ``Model_Space`` (decomposition slice 11, sub-commit C1: host lookup +
commit-click + legacy shims).

A plain object (not a QObject) holding a back-ref to the scene. Like the wall /
geometry-drawing controllers (slices 8/9/10), this collaborator is a **behavior
home**: it owns NO state. Every ``_opening_*`` transient AND the shared
``current_template`` / persisted ``_walls`` stay on the scene (reached via
``self._scene``), because ``current_template`` is shared (read by pipe/sprinkler)
and the white-box ``scene._opening_*`` asserts must stay green without repointing.
This controller owns the Feature-placement *methods* only.

Named ``FeaturePlacementController`` (not ``OpeningPlacementController``): the
Opening is the *first* Feature Category; future host-types / categories add new
methods to the same controller. The methods keep their ``_press_opening`` /
``_move_opening`` / ``_opening_*`` names (pure relocation).

Design: docs/superpowers/specs/2026-09-06-feature-placement-slice-design.md (§5, C1)
Behavior (Rule A): docs/specs/wall-room-floor-system.md §7 (Opening = first Feature)
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

from .constants import OPENING_ALIGNMENTS
from .wall_opening import WallOpening
from .feature import DEFAULT_FEATURE_FOR_TYPE

if TYPE_CHECKING:
    from .wall import WallSegment


class FeaturePlacementController:
    def __init__(self, scene):
        self._scene = scene

    # ── Host lookup (slice-10 earmark) ───────────────────────────────────────

    def _find_wall_at(self, pos: QPointF) -> "WallSegment | None":
        """Return the first wall whose shape contains pos."""
        for wall in self._scene._walls:
            if wall.shape().contains(pos):
                return wall
        return None

    def _offset_along_wall(self, wall: "WallSegment", pos: QPointF) -> float:
        """Project pos onto the wall centerline and return distance from pt1."""
        a = wall.centerline_angle_rad()
        dx = pos.x() - wall.pt1.x()
        dy = pos.y() - wall.pt1.y()
        return dx * math.cos(a) + dy * math.sin(a)

    # ── Commit-click (§7.6) ──────────────────────────────────────────────────

    def _press_opening(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Commit-click for the unified opening placement mode (§7.6).

        Requires a wall under the cursor: empty-space clicks are rejected with a
        status prompt (§7.10).  The placed opening inherits the pre-commit cycle
        state (alignment / hinge / facing) currently armed on the scene.
        """
        wall = self._find_wall_at(snapped)
        if wall is None:
            self._scene._show_status("Click on a wall to place an opening", timeout=2000)
            self._scene.instructionChanged.emit("Click on a wall to place an opening")
            return
        # The placement TEMPLATE (a WallOpening) is the single source of truth
        # for feature + size + sill; the scene mirrors below carry only the
        # live cycle state (alignment / hinge / facing) which is kept synced
        # onto the template by the cycle keys.
        tmpl = getattr(self._scene, "current_template", None)
        if isinstance(tmpl, WallOpening):
            op = WallOpening(
                wall=wall, feature_id=tmpl.feature_id,
                offset_along=self._offset_along_wall(wall, snapped),
                width_mm=tmpl.width_mm, height_mm=tmpl.height_mm,
                sill_mm=tmpl.sill_mm,
            )
            op.alignment = tmpl.alignment
            op.mirror_hinge = tmpl.mirror_hinge
            op.mirror_facing = tmpl.mirror_facing
        else:
            op = WallOpening(wall=wall, feature_id=self._scene._opening_feature_id,
                             offset_along=self._offset_along_wall(wall, snapped))
            op.alignment = self._scene._opening_alignment
            op.mirror_hinge = self._scene._opening_mirror_hinge
            op.mirror_facing = self._scene._opening_mirror_facing
        op.level = wall.level
        op._reposition()
        wall.openings.append(op)
        self._scene.addItem(op)
        self._scene.push_undo_state()
        self._scene.instructionChanged.emit("Click on a wall to place an opening")

    def _press_door(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Legacy door dispatch — retarget onto the unified opening path so the
        pre-Task-7 ribbon buttons keep working (§7.6)."""
        self._scene._opening_feature_id = DEFAULT_FEATURE_FOR_TYPE["door"]
        self._press_opening(event, pos, snapped, item_under, node_under, pipe_under)

    def _press_window(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Legacy window dispatch — retarget onto the unified opening path."""
        self._scene._opening_feature_id = DEFAULT_FEATURE_FOR_TYPE["window"]
        self._press_opening(event, pos, snapped, item_under, node_under, pipe_under)

    # ── Live preview / ghost (§7.6) ──────────────────────────────────────────

    def _move_opening(self, event, snapped):
        """Redraw the live opening ghost on the hovered wall.

        Hidden (and removed) when the cursor is not over a wall, so the ghost
        never floats in empty space.
        """
        wall = self._find_wall_at(snapped)
        if wall is None:
            self._clear_opening_ghost()
            return
        offset = self._offset_along_wall(wall, snapped)
        ghost = self._scene._opening_ghost
        # Rebuild the ghost from scratch if it is missing or its Feature changed
        # (feature_id is immutable on a WallOpening, so swap on mismatch).
        if ghost is None or ghost.feature_id != self._scene._opening_feature_id:
            self._clear_opening_ghost()
            ghost = WallOpening(feature_id=self._scene._opening_feature_id)
            ghost.setOpacity(0.5)
            ghost.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            ghost._exclude_from_bulk_select = True
            self._scene.addItem(ghost)
            self._scene._opening_ghost = ghost
        ghost.wall = wall
        ghost._offset_along = offset
        tmpl = getattr(self._scene, "current_template", None)
        if isinstance(tmpl, WallOpening):
            ghost.width_mm = tmpl.width_mm
            ghost.height_mm = tmpl.height_mm
            ghost.sill_mm = tmpl.sill_mm
        ghost.alignment = self._scene._opening_alignment
        ghost.mirror_hinge = self._scene._opening_mirror_hinge
        ghost.mirror_facing = self._scene._opening_mirror_facing
        ghost._reposition()

    def _move_door_window(self, event, snapped):
        self._scene.update_preview_node(snapped)

    def _refresh_opening_ghost(self):
        """Re-apply the current cycle state to the live ghost (post-cycle)."""
        ghost = self._scene._opening_ghost
        if ghost is None:
            return
        ghost.alignment = self._scene._opening_alignment
        ghost.mirror_hinge = self._scene._opening_mirror_hinge
        ghost.mirror_facing = self._scene._opening_mirror_facing
        ghost._reposition()
        for v in self._scene.views():
            v.viewport().update()

    def _clear_opening_ghost(self):
        """Remove the live opening ghost if present."""
        ghost = getattr(self._scene, "_opening_ghost", None)
        if ghost is not None:
            if ghost.scene() is self._scene:
                self._scene.removeItem(ghost)
            self._scene._opening_ghost = None

    # ── Alignment cycle (Space) + template sync ──────────────────────────────

    def _cycle_opening_alignment(self) -> None:
        """Advance opening alignment through OPENING_ALIGNMENTS and refresh the
        live ghost (§7.6)."""
        aligns = list(OPENING_ALIGNMENTS)
        try:
            idx = aligns.index(self._scene._opening_alignment)
        except ValueError:
            idx = -1
        self._scene._opening_alignment = aligns[(idx + 1) % len(aligns)]
        self._sync_opening_state_to_template()
        self._refresh_opening_ghost()
        self._scene.instructionChanged.emit(
            f"Opening [{self._scene._opening_alignment}] · Space=align "
            f"←/→=hinge ↑/↓=facing")

    def _sync_opening_state_to_template(self) -> None:
        """Push the live cycle state onto the placement template and refresh the
        property panel so Spacebar/arrow changes are reflected there (§7.6)."""
        tmpl = getattr(self._scene, "current_template", None)
        if isinstance(tmpl, WallOpening):
            tmpl.alignment = self._scene._opening_alignment
            tmpl.mirror_hinge = self._scene._opening_mirror_hinge
            tmpl.mirror_facing = self._scene._opening_mirror_facing
            self._scene.requestPropertyUpdate.emit(tmpl)
