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

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from . import marks
from .colour_tokens import resolve_colour
from .constants import FLOOR_OPENING_HOST_HL_COLOR, OPENING_ALIGNMENTS, Z_OVERLAY
from .display_manager import apply_category_defaults
from .wall_opening import WallOpening
from .feature import DEFAULT_FEATURE_FOR_TYPE

if TYPE_CHECKING:
    from .wall import WallSegment


class FloorOpeningDraft(QGraphicsPathItem):
    """In-progress floor-void boundary for the polygon primitive (floor-opening A6).

    A placement preview only: never in a host's ``openings``, never serialized,
    never on the undo stack.  Duck-types the members the floor polygon machinery
    reads off ``Model_Space._floor_active`` (``_points``, ``_color``,
    ``add_point``, ``last_point``, ``_rebuild_path``, ``close_polygon``) so that
    machinery is shared with the slab, not forked.
    """

    def __init__(self, first: QPointF, color: QColor):
        super().__init__()
        self._points: list[QPointF] = [QPointF(first)]
        self._color = QColor(color)
        pen = QPen(self._color, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setZValue(Z_OVERLAY)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._exclude_from_bulk_select = True
        self._rebuild_path()

    def add_point(self, pt: QPointF) -> None:
        """Append a vertex and redraw."""
        self._points.append(QPointF(pt))
        self._rebuild_path()

    def last_point(self) -> QPointF:
        """A copy of the most recent vertex (rubber-band anchor)."""
        return QPointF(self._points[-1])

    def close_polygon(self) -> None:
        """Redraw (the draft is committed by the controller, never kept)."""
        self._rebuild_path()

    def _rebuild_path(self) -> None:
        path = QPainterPath()
        if self._points:
            path.moveTo(self._points[0])
            for p in self._points[1:]:
                path.lineTo(p)
        self.setPath(path)


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
        marks.mint(self._scene, op)
        self._scene.push_undo_state()
        self._scene.instructionChanged.emit("Click on a wall to place an opening")
        # Single-placement: return to Select with the new opening selected.
        self._scene._end_placement_switch(op)

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

    # ── set_mode entering-arm / leaving-teardown (§2.5) ──────────────────────

    def enter(self, template) -> None:
        """Arm opening placement when entering 'opening' mode (§7.6).

        Absorbs the set_mode entering-arm verbatim: adopt the placement template
        (a WallOpening, or build one from a bare feature-id string), mirror its
        placement state onto the scene's cycle fields, and surface it in the
        property panel.
        """
        # Accept either a WallOpening TEMPLATE object (the pre-placement
        # property template — the new pattern) or a bare feature-id string
        # (legacy call sites / tests).  A string is adopted onto the
        # persistent template so there is always one source of truth.
        if isinstance(template, WallOpening):
            self._scene.current_template = template
        else:
            feature_id = template or DEFAULT_FEATURE_FOR_TYPE["door"]
            self._scene.current_template = WallOpening(feature_id=feature_id)
        tmpl = self._scene.current_template
        tmpl._scene_ref = self._scene
        # Mirror the template's placement state onto the scene fields the
        # cycle keys / ghost read (kept in sync both ways below).
        self._scene._opening_feature_id = tmpl.feature_id
        self._scene._opening_alignment = tmpl.alignment
        self._scene._opening_mirror_hinge = tmpl.mirror_hinge
        self._scene._opening_mirror_facing = tmpl.mirror_facing
        # Surface the template in the right-side property panel so the user
        # can edit Sill / size / orientation BEFORE placing.
        self._scene.requestPropertyUpdate.emit(tmpl)

    def clear(self, new_mode) -> None:
        """Tear down the live opening ghost when leaving 'opening' mode.

        Idempotent; no-ops when staying in 'opening'. Absorbs the set_mode
        leaving-teardown verbatim.
        """
        if new_mode != "opening":
            self._clear_opening_ghost()

    # ── Floor host strategy (floor-opening design A6) ────────────────────────
    # Floor voids reuse the floor rect / polygon machinery in Model_Space; the
    # host pick, Spacebar cycle, draft and commit live here.  State stays on
    # the scene (_floor_opening_* fields), like the _opening_* fields.

    def floor_slabs_at(self, pt: QPointF) -> list:
        """Visible slabs whose fill path contains *pt*, highest resolved top first.

        The fill ``path()`` (not the stroked ``shape()``) decides containment; a
        slab whose z-range does not resolve is skipped, exactly as it is hidden.
        Equal tops keep ``_floor_slabs`` order (stable sort).
        """
        found = []
        for slab in self._scene._floor_slabs:
            if not slab.isVisible() or not slab.path().contains(pt):
                continue
            zr = slab.z_range_mm()
            if zr is None:
                continue
            found.append((zr[1], slab))
        found.sort(key=lambda t: -t[0])
        return [slab for _, slab in found]

    def floor_opening_host(self):
        """The current host candidate, or None when nothing is armed."""
        sc = self._scene
        cands = sc._floor_opening_candidates
        if not cands:
            return None
        return cands[sc._floor_opening_host_idx % len(cands)]

    def arm_floor_host(self, pt: QPointF) -> bool:
        """First click of a floor-void placement: pick the host under *pt*.

        Returns:
            True when a host was armed; False (status + instruction posted,
            nothing armed) when no floor is under the point.
        """
        sc = self._scene
        cands = self.floor_slabs_at(pt)
        if not cands:
            msg = "Click on a floor to place an opening"
            sc._show_status(msg, timeout=2000)
            sc.instructionChanged.emit(msg)
            return False
        sc._floor_opening_candidates = cands
        sc._floor_opening_host_idx = 0
        self._show_floor_host_highlight()
        return True

    def cycle_floor_host(self) -> bool:
        """Spacebar while drawing: advance to the next stacked slab.

        Returns:
            True when the host changed; False with fewer than two candidates
            (nothing ambiguous, so the key falls through).
        """
        sc = self._scene
        cands = sc._floor_opening_candidates
        if len(cands) < 2:
            return False
        sc._floor_opening_host_idx = (sc._floor_opening_host_idx + 1) % len(cands)
        self._show_floor_host_highlight()
        host = self.floor_opening_host()
        sc.instructionChanged.emit(
            f"Opening host: {host.name or 'Floor'} "
            f"({sc._floor_opening_host_idx + 1}/{len(cands)})  -  Space = next floor")
        return True

    def _show_floor_host_highlight(self) -> None:
        """Outline the current host (created lazily, one item per placement)."""
        sc = self._scene
        host = self.floor_opening_host()
        if host is None:
            return
        hl = sc._floor_opening_host_hl
        if hl is None:
            hl = QGraphicsPathItem()
            pen = QPen(QColor(FLOOR_OPENING_HOST_HL_COLOR), 3, Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            hl.setPen(pen)
            hl.setZValue(Z_OVERLAY)
            hl.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            hl._exclude_from_bulk_select = True
            sc.addItem(hl)
            sc._floor_opening_host_hl = hl
        hl.setPath(host.path())
        for v in sc.views():
            v.viewport().update()

    def clear_floor_host_pick(self) -> None:
        """Drop the candidates and the highlight (idempotent)."""
        sc = self._scene
        sc._floor_opening_candidates = []
        sc._floor_opening_host_idx = 0
        hl = sc._floor_opening_host_hl
        if hl is not None:
            if hl.scene() is sc:
                sc.removeItem(hl)
            sc._floor_opening_host_hl = None

    def floor_opening_colour(self) -> QColor:
        """Draft / ghost colour: the Display Manager "Opening" row colour."""
        from .display_manager import _read_category_from_settings
        from .floor_opening import FLOOR_VOID_DEFAULT_COLOR
        c = _read_category_from_settings("Opening").get("color") or FLOOR_VOID_DEFAULT_COLOR
        return resolve_colour(c)

    def begin_floor_opening_draft(self, pt: QPointF) -> "FloorOpeningDraft":
        """Start the polygon draft at *pt* (a preview; the host is untouched)."""
        sc = self._scene
        draft = FloorOpeningDraft(pt, self.floor_opening_colour())
        sc.addItem(draft)
        sc._floor_active = draft
        return draft

    def commit_floor_opening_draft(self):
        """Close the polygon draft: remove the preview, commit its points.

        Returns:
            The placed FloorOpening, or None when discarded (< 3 points).
        """
        sc = self._scene
        draft = sc._floor_active
        sc._floor_active = None
        pts = list(draft._points) if draft is not None else []
        if draft is not None and draft.scene() is sc:
            sc.removeItem(draft)
        sc.preview_pipe.hide()
        sc._hide_close_ring()
        return self.commit_floor_opening(pts)

    def commit_floor_opening(self, points):
        """The void commit target (A6): host.add_opening, addItem, mint, undo, Select.

        Fewer than 3 points discard (no void, no undo entry) and re-arm.

        Returns:
            The placed FloorOpening, or None when discarded.
        """
        from .floor_opening import FloorOpening
        sc = self._scene
        host = self.floor_opening_host()
        self.clear_floor_host_pick()
        for v in sc.views():
            v.viewport().update()
        if host is None or len(points) < 3:
            sc._show_status("A floor opening needs at least 3 points", timeout=2000)
            sc.instructionChanged.emit("Click on a floor to place an opening")
            return None
        op = FloorOpening([QPointF(p) for p in points], host,
                          feature_id=sc._floor_opening_feature_id)
        host.add_opening(op)
        if op.scene() is not sc:
            sc.addItem(op)
        apply_category_defaults(op)
        marks.mint(sc, op)
        sc.push_undo_state()
        sc.instructionChanged.emit("Click on a floor to place an opening")
        # Single-placement: return to Select with the new void selected.
        sc._end_placement_switch(op)
        return op
