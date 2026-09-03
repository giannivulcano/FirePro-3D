"""PipeNetworkController — the pipe/node network concern extracted from
``Model_Space`` (decomposition slice 5).

A plain object (not a QObject) holding a back-ref to the scene. All scene-graph
mutation, signal emission, undo, and serialization stay on the scene and are
reached via ``self._scene``; this controller owns the pipe placement/creation/
deletion/geometry-correction behavior and the pipe Tab-cycle transient state.

Design: docs/superpowers/specs/2026-09-02-pipe-network-slice-design.md
Behavior (Rule A): docs/specs/pipe-placement-methodology.md
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF

from .node import Node
from .display_manager import apply_category_defaults


class PipeNetworkController:
    def __init__(self, scene):
        self._scene = scene
        # pipe Tab-cycle transient (was Model_Space._pipe_tab_*)
        self._tab_candidates = []
        self._tab_index = 0
        self._tab_pos = None

    def find_nearby_node(self, x, y, z_hint=None):
        pt = QPointF(x, y)

        view_range = self._scene._get_active_view_range()

        def _in_view_range(node):
            if view_range is None:
                return True
            return view_range[0] <= node.z_pos <= view_range[1]

        # Collect all XY candidates (both priority tiers), filtered by view range
        bbox_candidates = []
        dist_candidates = []
        for node in self._scene.sprinkler_system.nodes:
            if not _in_view_range(node):
                continue
            if node.has_sprinkler():
                spr = node.sprinkler
                if spr.mapToScene(spr.boundingRect()).boundingRect().contains(pt):
                    bbox_candidates.append(node)
                    continue
            if node.distance_to(x, y) <= self._scene.SNAP_RADIUS:
                dist_candidates.append(node)

        # Merge: bbox hits first, then distance hits
        candidates = bbox_candidates + dist_candidates
        if not candidates:
            return None
        if z_hint is None or len(candidates) == 1:
            return candidates[0]
        return min(candidates, key=lambda n: abs(n.z_pos - z_hint))

    def find_nearby_candidates(self, x, y, z_hint=None):
        """Return all nodes within SNAP_RADIUS, filtered by view range.

        If *z_hint* is provided, results are sorted by ascending distance
        to *z_hint*.  Otherwise sorted by insertion order.
        """
        pt = QPointF(x, y)
        view_range = self._scene._get_active_view_range()

        def _in_view_range(node):
            if view_range is None:
                return True
            return view_range[0] <= node.z_pos <= view_range[1]

        candidates = []
        for node in self._scene.sprinkler_system.nodes:
            if not _in_view_range(node):
                continue
            if node.has_sprinkler():
                spr = node.sprinkler
                if spr.mapToScene(spr.boundingRect()).boundingRect().contains(pt):
                    candidates.append(node)
                    continue
            if node.distance_to(x, y) <= self._scene.SNAP_RADIUS:
                candidates.append(node)

        if z_hint is not None and len(candidates) > 1:
            candidates.sort(key=lambda n: abs(n.z_pos - z_hint))
        return candidates

    def find_or_create_node(self, x, y, z_hint=None):
        existing = self.find_nearby_node(x, y, z_hint=z_hint)
        if existing:
            return existing
        return self.add_node(x, y, z_hint=z_hint)

    def add_node(self, x, y, z_hint=None):
        node = self.find_nearby_node(x, y, z_hint=z_hint)
        if not node:
            node = Node(x, y)
            node.level = self._scene.active_level
            node.ceiling_level = self._scene.active_level

            node._properties["Ceiling Level"]["value"] = self._scene.active_level
            # Compute z_pos from ceiling level elevation + offset
            if self._scene._level_manager:
                lvl = self._scene._level_manager.get(self._scene.active_level)
                if lvl:
                    node.z_pos = lvl.elevation + node.ceiling_offset
            self._scene.addItem(node)
            apply_category_defaults(node)
            node.setVisible(True)
            self._scene.sprinkler_system.add_node(node)
        return node

    def remove_node(self, n):
        try:
            self._scene.sprinkler_system.remove_node(n)
        except ValueError:
            pass
        if n.scene() is self._scene:
            self._scene.removeItem(n)
        n = None
        self._scene.node_start_pos = None

    @staticmethod
    def _apply_fitting_dm_colors(fitting):
        """Apply Display Manager colour/opacity to a fitting without re-aligning.

        This avoids the full apply_category_defaults → _apply_fitting → align_fitting
        chain which can displace the symbol if called at the wrong time.
        """
        from .display_manager import _set_svg_tint, _CATEGORIES
        from PyQt6.QtCore import QSettings
        cat_def = next((c for c in _CATEGORIES if c["key"] == "Fitting"), None)
        if cat_def is None or fitting.symbol is None:
            return
        settings = QSettings("GV", "FirePro3D")
        if not settings.contains("display/Fitting/color"):
            return  # no user-saved settings — keep SVG natural colours
        color = settings.value("display/Fitting/color", cat_def["color"])
        fill = settings.value("display/Fitting/fill", cat_def.get("fill"))
        opacity = int(float(settings.value("display/Fitting/opacity", cat_def["opacity"])))
        fitting._display_color = color
        fitting._display_fill_color = fill
        fitting._display_opacity = opacity
        _set_svg_tint(fitting.symbol, color, fill)
        fitting.symbol.setOpacity(opacity / 100.0 if opacity > 1 else opacity)

    def clear(self):
        """Idempotent teardown of pipe placement transient state.

        Populated in a later slice (C3, set_mode + cancel wiring). Kept
        no-op-safe here so C1 wiring is inert until then.
        """
        self._tab_candidates = []
        self._tab_index = 0
        self._tab_pos = None
