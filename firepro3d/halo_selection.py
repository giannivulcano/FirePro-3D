"""Scene-agnostic HALO preselection + scene-drawn rubber-band engine.

Mixed into Model_Space (plan scene) and ElevationScene. The generic ranking /
aperture-pick / band-query bodies live here; the 5 scene-specific hooks below
have plan-neutral defaults that Model_Space overrides (Room/underlay/mode) and
ElevationScene mostly inherits (see selection-mode.md elevation section)."""
from __future__ import annotations
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsItem

from .constants import (HALO_APERTURE_PX as _APERTURE_DEFAULT,
                        HALO_PRIORITY_BAND_PX as _BAND_DEFAULT)
from .halo import halo_pick_distance_px

# App-wide, user-tunable (Preferences -> HALO; loaded from QSettings by main).
# Read at call time — never copy into an instance (the SNAP_TOLERANCE_PX pattern).
HALO_APERTURE_PX: float = _APERTURE_DEFAULT
HALO_PRIORITY_BAND_PX: float = _BAND_DEFAULT


def _in_scene(item, scene) -> bool:
    """True when *item* is still alive and parented to *scene*."""
    try:
        return item.scene() is scene
    except RuntimeError:        # C++ object already deleted
        return False


class HaloSelectionMixin:
    # ---- state -------------------------------------------------------------
    def _init_halo_state(self):
        self._halo_candidates: list = []
        self._halo_index: int = 0
        self._halo_pick_pos = None
        self.halo_enabled: bool = True
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
    def _halo_rank_with_dist(self, items, scene_pos, dt=None):
        """[(item, px_distance)] in HALO order (selection-mode §3 / §4.1).

        Each raw hit resolves to its selectable parent; the parent's distance
        is the MIN over every raw hit that resolved to it (a sprinkler or
        bubble child counts for its parent). Candidates within
        ``HALO_PRIORITY_BAND_PX`` of the closest rank by runtime-Z desc, then
        distance; the rest follow by distance; stable id breaks ties. Pure +
        deterministic. ``dt`` None = identity (1 scene unit = 1 px).
        """
        dt = dt if dt is not None else QTransform()
        cursor = dt.map(scene_pos)
        dist, order = {}, []
        for it in items:
            r = self._halo_resolve(it)
            if r is None:
                continue
            if not (r.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            d = halo_pick_distance_px(it, cursor, dt)
            if r is not it:
                d = min(d, halo_pick_distance_px(r, cursor, dt))
            k = id(r)
            if k not in dist:
                order.append(r)
                dist[k] = d
            elif d < dist[k]:
                dist[k] = d
        if not order:
            return []
        edge = min(dist.values()) + HALO_PRIORITY_BAND_PX

        def _key(r):
            d = dist[id(r)]
            return (0, -r.zValue(), d, id(r)) if d <= edge else (1, 0.0, d, id(r))

        order.sort(key=_key)
        return [(r, dist[id(r)]) for r in order]

    def halo_rank(self, items, scene_pos, dt=None):
        """HALO order only (see :meth:`_halo_rank_with_dist`)."""
        return [r for r, _d in self._halo_rank_with_dist(items, scene_pos, dt)]

    def halo_candidates_at(self, scene_pos, aperture_scene, dt):
        """Aperture pick -> filtered, ranked HALO candidate list.

        aperture_scene: half-size of the pick box in scene units (also the
        source of the px aperture: judged in SCREEN PIXELS against each
        candidate's drawn trace, SNAP-style — see :meth:`_halo_rank_with_dist`).
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
        scale = max(abs(dt.m11()), 1e-9) if dt is not None else 1.0
        aperture_px = aperture_scene * scale
        ranked = [r for r, d in self._halo_rank_with_dist(others, scene_pos, dt)
                  if d <= aperture_px]
        for u in underlays:
            if u.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                ranked.append(u)
        # Per-candidate accept filter (Model_Space: labelled Room label-rect).
        ranked = [r for r in ranked if self._halo_candidate_ok(r, scene_pos)]
        return ranked

    def select_items(self, items, *, clear: bool = True):
        """Select *items* as one batch with a single ``selectionChanged``.

        Per-item ``setSelected`` fires ``selectionChanged`` each time and every
        listener (manipulator rebake, property panel) walks the whole growing
        selection — O(n^2) on large batches. Items not in this scene or not
        selectable are skipped.

        Args:
            items: Iterable of scene items to select.
            clear: Clear the existing selection first (default True).
        """
        selectable = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        self.blockSignals(True)
        try:
            if clear:
                self.clearSelection()
            for it in items:
                if it is not None and it.scene() is self and it.flags() & selectable:
                    it.setSelected(True)
        finally:
            self.blockSignals(False)
        self.selectionChanged.emit()

    def commit_rubber_band(self, scene_rect, crossing: bool, additive: bool,
                           dt=None):
        """Select items in scene_rect as ONE batch. window(crossing=False)
        ->fully contained, crossing=True->intersecting. additive (Ctrl) adds
        to current selection.

        Delegates to :meth:`select_items` (single ``selectionChanged``
        emission) rather than per-item ``setSelected`` — the latter is O(n^2)
        on large bands (every listener walks the growing selection on every
        emission; >10 min on 85k items).

        ``dt`` is the view's device transform (``viewportTransform()``). It must
        be supplied so ``ItemIgnoresTransformations`` markers (Nodes) are hit
        against their ON-SCREEN shape rather than their transform-free scene
        shape (which inflates to ~356 scene units and would over-select). When
        ``dt`` is None (headless/unit tests) the 2-arg query is used.
        """
        hits = self.rubber_band_hits(scene_rect, crossing, dt)
        self.select_items(hits, clear=not additive)

    def rubber_band_hits(self, scene_rect, crossing: bool, dt=None):
        """Resolved, filtered items a window(crossing=False)/crossing band selects.

        Pure query (no selection side-effects): the set :meth:`commit_rubber_band`
        selects. Mirrors the historical commit filter semantics exactly, with
        dedupe on resolved identity so a parent hit via multiple children is
        counted once.

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

    def _halo_cycle(self) -> bool:
        """Spacebar in select mode: advance the HALO preselection highlight."""
        if len(self._halo_candidates) < 2:
            return False
        self._halo_index = (self._halo_index + 1) % len(self._halo_candidates)
        self._emit_halo_readout()
        for v in self.views():
            v.viewport().update()
        return True

    def halo_item(self):
        """The currently highlighted HALO candidate, or None.

        Candidates removed from the scene since the last mouse move (delete,
        cut, undo restore) are pruned first, so a stale highlight is never
        painted over a vanished item while the cursor sits still.
        """
        live = [c for c in self._halo_candidates if _in_scene(c, self)]
        if len(live) != len(self._halo_candidates):
            self._halo_candidates = live
            self._halo_index = 0
        if 0 <= self._halo_index < len(self._halo_candidates):
            return self._halo_candidates[self._halo_index]
        return None

    def _halo_suppressed(self):
        """True when hover-highlight must not run (tool mode, drag, rubber-band)."""
        if not self.halo_enabled:
            return True
        if not self._halo_mode_ok():
            return True
        # An open selection-readout edit makes the canvas inert
        # (selection-mode §15). getattr: elevation_scene has no readouts.
        readouts = getattr(self, "readouts", None)
        if readouts is not None and readouts.is_editing():
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
