"""Scene-agnostic HALO preselection + scene-drawn rubber-band engine.

Mixed into Model_Space (plan scene) and ElevationScene. The generic ranking /
aperture-pick / band-query bodies live here; the 5 scene-specific hooks below
have plan-neutral defaults that Model_Space overrides (Room/underlay/mode) and
ElevationScene mostly inherits (see selection-mode.md elevation section)."""
from __future__ import annotations
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QGraphicsItem


class HaloSelectionMixin:
    # ---- state -------------------------------------------------------------
    def _init_halo_state(self):
        self._halo_candidates: list = []
        self._halo_index: int = 0
        self._halo_pick_pos = None
        self.halo_enabled: bool = True
        self._band_preview: list = []
        self._rb_active_flag: bool = False

    # ---- overridable hooks (plan-neutral defaults) -------------------------
    def _halo_resolve(self, item):
        """Resolve a hit child to its selectable parent. Default: identity."""
        return item

    def _halo_is_underlay(self, item):
        """True if item belongs to a placed underlay group. Default: False."""
        return False

    def _halo_candidate_ok(self, item, scene_pos):
        """Per-candidate accept filter (Model_Space uses it for Room label-rect).
        Default: accept."""
        return True

    def _halo_in_view_range(self, item):
        return True

    def _halo_mode_ok(self):
        """True when no blocking tool mode is active. Default: True."""
        return True

    # ---- generic engine (bodies moved verbatim from model_space.py) --------
    def halo_rank(self, items, scene_pos):
        """Order candidates: runtime-Z desc -> screen distance -> stable id.

        Pure + deterministic. Resolves child->parent, dedupes, drops
        non-selectable items. Single order consumed by hover/cycle/click.
        """
        resolved, seen = [], set()
        for it in items:
            r = self._halo_resolve(it)
            if r is None or id(r) in seen:
                continue
            if not (r.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            seen.add(id(r))
            resolved.append(r)

        def _dist(it):
            c = it.sceneBoundingRect().center()
            return (c.x() - scene_pos.x()) ** 2 + (c.y() - scene_pos.y()) ** 2

        resolved.sort(key=lambda it: (-it.zValue(), _dist(it), id(it)))
        return resolved

    def halo_candidates_at(self, scene_pos, aperture_scene, dt):
        """Aperture pick -> filtered, ranked HALO candidate list.

        aperture_scene: half-size of the pick box in scene units.
        dt: the view's viewportTransform for
        ItemIgnoresTransformations-correct hits.
        """
        a = aperture_scene
        box = QRectF(scene_pos.x() - a, scene_pos.y() - a, 2 * a, 2 * a)
        raw = self.items(box, Qt.ItemSelectionMode.IntersectsItemShape,
                         Qt.SortOrder.DescendingOrder, dt)
        vis = [i for i in raw if i.isVisible() and self._halo_in_view_range(i)]
        underlays = [i for i in vis if self._halo_is_underlay(i)]
        others = [i for i in vis if not self._halo_is_underlay(i)]
        ranked = self.halo_rank(others, scene_pos)
        for u in underlays:
            if u.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                ranked.append(u)
        # Per-candidate accept filter (Model_Space: labelled Room label-rect).
        ranked = [r for r in ranked if self._halo_candidate_ok(r, scene_pos)]
        return ranked

    def commit_rubber_band(self, scene_rect, crossing: bool, additive: bool,
                           dt=None):
        """Select items in scene_rect. window(crossing=False)->fully contained,
        crossing=True->intersecting. additive (Ctrl) adds to current selection.

        ``dt`` is the view's device transform (``viewportTransform()``). It must
        be supplied so ``ItemIgnoresTransformations`` markers (Nodes) are hit
        against their ON-SCREEN shape rather than their transform-free scene
        shape (which inflates to ~356 scene units and would over-select). When
        ``dt`` is None (headless/unit tests) the 2-arg query is used.
        """
        hits = self.rubber_band_hits(scene_rect, crossing, dt)
        if not additive:
            self.clearSelection()
        for r in hits:
            r.setSelected(True)

    def rubber_band_hits(self, scene_rect, crossing: bool, dt=None):
        """Resolved, filtered items a window(crossing=False)/crossing band selects.

        Pure query (no selection side-effects): shared by
        :meth:`commit_rubber_band` (which selects them) and the live band
        preview (which HALO-highlights them). Mirrors the historical
        commit filter semantics exactly, with dedupe on resolved identity so a
        parent hit via multiple children is highlighted once.

        ``dt`` is the view's device transform (``viewportTransform()``); it
        must be supplied so ``ItemIgnoresTransformations`` markers (Nodes) hit
        against their ON-SCREEN shape. When None (headless/unit tests) the
        2-arg query is used.
        """
        mode = (Qt.ItemSelectionMode.IntersectsItemShape if crossing
                else Qt.ItemSelectionMode.ContainsItemShape)
        if dt is not None:
            raw = self.items(scene_rect, mode, Qt.SortOrder.DescendingOrder, dt)
        else:
            raw = self.items(scene_rect, mode)
        out, seen = [], set()
        for it in raw:
            if getattr(it, "_exclude_from_bulk_select", False):
                continue
            if self._halo_is_underlay(it):
                continue
            r = self._halo_resolve(it)
            if r is None or id(r) in seen:
                continue
            if getattr(r, "_exclude_from_bulk_select", False):
                continue
            if not (r.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            # Per-candidate accept filter (Model_Space: labelled Room label-rect
            # touched by the band; generic default accepts everything).
            if not self._halo_candidate_ok(r, scene_rect):
                continue
            seen.add(id(r))
            out.append(r)
        return out

    def update_band_preview(self, scene_rect, crossing: bool, dt=None):
        """Recompute the live band preselection preview set (highlighted, not
        selected). Called from the view's move handler while banding."""
        self._band_preview = self.rubber_band_hits(scene_rect, crossing, dt)

    def clear_band_preview(self) -> bool:
        """Drop the band preview set. Returns True if it had been populated."""
        had = bool(self._band_preview)
        self._band_preview = []
        return had

    def halo_item(self):
        """The currently highlighted HALO candidate, or None."""
        if 0 <= self._halo_index < len(self._halo_candidates):
            return self._halo_candidates[self._halo_index]
        return None

    def _halo_suppressed(self):
        """True when hover-highlight must not run (tool mode, drag, rubber-band)."""
        if not self.halo_enabled:
            return True
        if not self._halo_mode_ok():
            return True
        live_manip = getattr(self, "_live_manip", None)
        if callable(live_manip):
            manip = live_manip()
            if manip is not None and manip.is_dragging():
                return True
        if getattr(self, "_rb_active_flag", False):
            return True
        return False

    def _escape_ladder(self) -> bool:
        """Select-mode Escape precedence: cancel band -> reset HALO -> clear selection.

        (Manipulator-drag cancel is handled earlier in keyPressEvent.) Returns True
        if it consumed the key.
        """
        for v in self.views():
            if getattr(v, "_rb_active", False):
                v._rb_active = False
                self._rb_active_flag = False
                self.clear_band_preview()
                v.viewport().update()
                return True
        if self.halo_item() is not None or self._halo_candidates:
            self.halo_clear()
            for v in self.views():
                v.viewport().update()
            return True
        if self.selectedItems():
            self.clearSelection()
            return True
        return False

    def halo_clear(self):
        """Drop the candidate list. Returns True if there was something to clear."""
        had = bool(self._halo_candidates)
        self._halo_candidates, self._halo_index, self._halo_pick_pos = [], 0, None
        return had

    def halo_update(self, scene_pos, aperture_scene, dt):
        """Rebuild the candidate list for a mouse move. Returns True if the
        highlighted item changed (caller repaints)."""
        if self._halo_suppressed():
            return self.halo_clear()
        prev = self.halo_item()
        self._halo_candidates = self.halo_candidates_at(scene_pos, aperture_scene, dt)
        self._halo_index = 0
        self._halo_pick_pos = scene_pos
        changed = self.halo_item() is not prev
        if changed:
            self._emit_halo_readout()
        return changed
