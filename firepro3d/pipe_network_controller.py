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
from .pipe import Pipe
from .display_manager import apply_category_defaults
from .constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM


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

    def add_pipe(self, n1, n2, template=None, _propagate_ceiling=True):
        pipe = Pipe(n1, n2)
        # Apply template first so non-level properties are copied
        if template:
            pipe.set_properties(template)
        # Only override the visibility level (Level) with the active level.
        # Ceiling Level comes from the template — it controls 3D elevation.
        pipe.level = self._scene.active_level
        self._scene.sprinkler_system.add_pipe(pipe)
        self._scene.addItem(pipe)
        apply_category_defaults(pipe)
        pipe.update_label()   # re-run now that pipe.scene() is valid
        pipe.update_geometry()
        # Ensure visibility — level filtering may not have run yet
        pipe.setVisible(True)
        pipe.setOpacity(1.0)
        pipe.update()
        # Update fittings at both endpoints immediately so they reflect
        # the new connection angle before anything else renders.
        # Collect all affected nodes first, then update + apply colours.
        affected_nodes = {n1, n2}
        for p in n1.pipes:
            affected_nodes.add(p.node2 if p.node1 is n1 else p.node1)
        for p in n2.pipes:
            affected_nodes.add(p.node2 if p.node1 is n2 else p.node1)
        for node in affected_nodes:
            node.fitting.update()
            self._apply_fitting_dm_colors(node.fitting)
        for v in self._scene.views():
            v.viewport().update()

        # Propagate the pipe's ceiling properties to both endpoint nodes
        # so their 3D elevation matches what the user set on the template.
        # Skip during load — nodes already have authoritative ceiling data.
        if _propagate_ceiling and template is not None:
            # Use per-node ceiling values from template; fall back to defaults
            for node, lvl_attr, off_attr in (
                (n1, "node1_ceiling_level", "node1_ceiling_offset"),
                (n2, "node2_ceiling_level", "node2_ceiling_offset"),
            ):
                if node is None:
                    continue
                c_lvl = getattr(template, lvl_attr, None)
                c_off = getattr(template, off_attr, None)
                if c_lvl is None:
                    c_lvl = DEFAULT_LEVEL
                if c_off is None:
                    c_off = DEFAULT_CEILING_OFFSET_MM
                node.ceiling_level = c_lvl
                node._properties["Ceiling Level"]["value"] = c_lvl
                node.ceiling_offset = c_off
                node._properties["Ceiling Offset"]["value"] = str(c_off)
                node._recompute_z_pos()
        elif _propagate_ceiling:
            # No template — apply defaults to both endpoint nodes
            for node in (n1, n2):
                if node is not None:
                    node.ceiling_level = DEFAULT_LEVEL
                    node._properties["Ceiling Level"]["value"] = DEFAULT_LEVEL
                    node.ceiling_offset = DEFAULT_CEILING_OFFSET_MM
                    node._properties["Ceiling Offset"]["value"] = str(DEFAULT_CEILING_OFFSET_MM)
                    node._recompute_z_pos()

        return pipe

    def _split_vertical_pipe(self, pipe, target_z: float, template) -> "Node":
        """Split a vertical pipe at *target_z*, returning the new mid-node.

        Creates a new node at the pipe's XY with the template's ceiling
        properties (so z_pos == target_z), then replaces the original pipe
        with two shorter vertical pipes.
        """
        xy = pipe.node1.scenePos()
        mid = Node(xy.x(), xy.y())
        mid.level = self._scene.active_level

        ceiling_lvl = getattr(template, "node1_ceiling_level", None) or DEFAULT_LEVEL
        ceiling_off = getattr(template, "node1_ceiling_offset", None)
        if ceiling_off is None:
            ceiling_off = DEFAULT_CEILING_OFFSET_MM
        mid.ceiling_level = ceiling_lvl
        mid._properties["Ceiling Level"]["value"] = ceiling_lvl
        mid.ceiling_offset = ceiling_off
        mid._properties["Ceiling Offset"]["value"] = str(ceiling_off)
        mid.z_pos = target_z

        self._scene.addItem(mid)
        self._scene.sprinkler_system.add_node(mid)

        # Create two replacement vertical pipes preserving the original's properties
        node_a = pipe.node1
        node_b = pipe.node2
        for (na, nb) in ((node_a, mid), (mid, node_b)):
            seg = Pipe(na, nb)
            seg.level = pipe.level
            for key in ("Diameter", "Schedule", "C-Factor",
                        "Material", "Colour", "Phase", "Line Type"):
                seg._properties[key]["value"] = pipe._properties[key]["value"]
            self._scene.sprinkler_system.add_pipe(seg)
            self._scene.addItem(seg)
            seg.set_pipe_display()

        self.delete_pipe(pipe)
        mid.fitting.update()
        node_a.fitting.update()
        node_b.fitting.update()
        return mid

    # ── End vertical pipe helpers ─────────────────────────────────────────

    def split_pipe(self, pipe, split_point: QPointF):
        # If split point is near an existing endpoint, return that node
        # instead of creating a tiny degenerate split.
        for end_node in (pipe.node1, pipe.node2):
            if end_node is not None:
                dx = end_node.scenePos().x() - split_point.x()
                dy = end_node.scenePos().y() - split_point.y()
                if (dx * dx + dy * dy) < self._scene.SNAP_RADIUS * self._scene.SNAP_RADIUS:
                    return end_node
        new_node = self.add_node(split_point.x(), split_point.y())
        node_a = pipe.node1
        node_b = pipe.node2
        # Use _propagate_ceiling=False — pipe attributes can be stale.
        # Copy ceiling from the authoritative source (endpoint nodes).
        self.add_pipe(node_a, new_node, pipe, _propagate_ceiling=False)
        self.add_pipe(new_node, node_b, pipe, _propagate_ceiling=False)
        self.delete_pipe(pipe)
        # Set new_node's ceiling from node_a (authoritative endpoint)
        new_node.ceiling_level = node_a.ceiling_level
        new_node._properties["Ceiling Level"]["value"] = node_a.ceiling_level
        new_node.ceiling_offset = node_a.ceiling_offset
        new_node._properties["Ceiling Offset"]["value"] = str(node_a.ceiling_offset)
        new_node._recompute_z_pos()
        new_node.fitting.update()
        node_a.fitting.update()
        node_b.fitting.update()
        return new_node

    def delete_pipe(self, pipe):
        for node in (pipe.node1, pipe.node2):
            if node is not None:
                node.remove_pipe(pipe)
                if not node.has_sprinkler() and not node.pipes:
                    self.remove_node(node)
        pipe.node1 = None
        pipe.node2 = None
        # Remove top-level label from scene
        if hasattr(pipe, "label") and pipe.label is not None:
            try:
                self._scene.removeItem(pipe.label)
            except (RuntimeError, ValueError):
                pass
        # Remove top-level riser symbol from scene
        if hasattr(pipe, "_riser_symbol") and pipe._riser_symbol is not None:
            try:
                self._scene.removeItem(pipe._riser_symbol)
            except (RuntimeError, ValueError):
                pass
        try:
            self._scene.removeItem(pipe)
        except (RuntimeError, ValueError):
            pass  # item may already be removed from scene
        if pipe in self._scene.sprinkler_system.pipes:
            self._scene.sprinkler_system.remove_pipe(pipe)

    def clear(self):
        """Idempotent teardown of pipe placement transient state.

        Populated in a later slice (C3, set_mode + cancel wiring). Kept
        no-op-safe here so C1 wiring is inert until then.
        """
        self._tab_candidates = []
        self._tab_index = 0
        self._tab_pos = None
