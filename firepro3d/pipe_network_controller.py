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

import math

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QFont

from .cad_math import CAD_Math
from .node import Node
from .pipe import Pipe
from .display_manager import apply_category_defaults
from .constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM, Z_COPLANAR_TOL


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

    def _validate_4th_branch(self, node, new_pt: QPointF) -> str | None:
        """Check whether adding a 4th coplanar branch at *node* toward *new_pt* is valid.

        A 4th coplanar pipe is only allowed if:
        - The existing coplanar fitting is a tee (3 pipes with a through-run pair)
        - The new pipe is perpendicular (~90°) to the through-run

        Only considers coplanar pipes (other endpoint within
        ``Z_COPLANAR_TOL`` of *node*).

        Returns an error message string, or None if the connection is valid.
        """
        from .fitting import Fitting
        nz = node.z_pos
        coplanar_pipes = [p for p in node.pipes
                          if abs((p.node2 if p.node1 is node else p.node1).z_pos
                                 - nz) <= Z_COPLANAR_TOL]
        if len(coplanar_pipes) != 3:
            return "A 4th branch can only be added to a tee fitting."
        # Check that the current coplanar fitting is actually a tee
        ft_type = node.fitting.determine_type(coplanar_pipes)
        if ft_type != "tee":
            return (f"A 4th branch can only be added to a tee fitting "
                    f"(current fitting: {ft_type}).")
        # Find the through-run direction (the collinear pair in the tee)
        np_ = node.scenePos()
        vectors = []
        for p in coplanar_pipes:
            other = p.node2 if p.node1 is node else p.node1
            op = other.scenePos()
            dx, dy = op.x() - np_.x(), op.y() - np_.y()
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            vectors.append((dx / length, dy / length))
        if len(vectors) != 3:
            return "Cannot determine pipe directions at this node."
        # Find the collinear pair (angle ≈ 180°)
        through_dir = None
        for i in range(3):
            for j in range(i + 1, 3):
                dot = vectors[i][0] * vectors[j][0] + vectors[i][1] * vectors[j][1]
                if dot < -0.95:  # ~180° ± ~18°
                    through_dir = vectors[i]
                    break
            if through_dir:
                break
        if through_dir is None:
            return "Cannot find through-run direction on this tee."
        # Check new pipe direction is perpendicular to through-run
        dx_new = new_pt.x() - np_.x()
        dy_new = new_pt.y() - np_.y()
        len_new = math.hypot(dx_new, dy_new)
        if len_new < 1e-6:
            return "New pipe has zero length."
        ux_new, uy_new = dx_new / len_new, dy_new / len_new
        dot_new = through_dir[0] * ux_new + through_dir[1] * uy_new
        if abs(dot_new) > 0.17:  # cos(80°) ≈ 0.17 — must be within ~10° of 90°
            return ("A 4th branch must be perpendicular to the through-run "
                    "to form a cross fitting.")
        return None

    def _would_backtrack(self, start_node, end_node) -> bool:
        """Return True if placing a pipe from *start_node* to *end_node*
        would overlap an existing pipe (backtracking).

        Checks:
        1. Direct duplicate — a pipe already connects the same two nodes.
        2. End lands on an existing pipe connected to start — the new end
           point lies between the endpoints of a pipe already attached to
           start_node.

        Only considers coplanar pipes (other endpoint within
        ``Z_COPLANAR_TOL`` of *start_node*).
        """
        ep = end_node.scenePos()
        sz = start_node.z_pos
        for pipe in start_node.pipes:
            other = pipe.node2 if pipe.node1 is start_node else pipe.node1
            # Direct duplicate — always block regardless of Z
            if other is end_node:
                return True
            # Skip non-coplanar pipes (risers / cross-level)
            if abs(other.z_pos - sz) > Z_COPLANAR_TOL:
                continue
            # End point lies on an existing pipe segment
            op = other.scenePos()
            sp = start_node.scenePos()
            dx, dy = op.x() - sp.x(), op.y() - sp.y()
            length_sq = dx * dx + dy * dy
            if length_sq < 1e-6:
                continue
            t = ((ep.x() - sp.x()) * dx + (ep.y() - sp.y()) * dy) / length_sq
            if 0.01 < t < 0.99:
                proj_x = sp.x() + t * dx
                proj_y = sp.y() + t * dy
                dist = math.hypot(ep.x() - proj_x, ep.y() - proj_y)
                if dist < 10.0:
                    return True
        return False

    def _would_backtrack_at(self, start_node, target_pt: QPointF) -> bool:
        """Like _would_backtrack but takes a point instead of a node.

        Used to check for backtracking *before* creating a node.
        Only considers coplanar pipes (other endpoint within
        ``Z_COPLANAR_TOL`` of *start_node*).
        """
        sp = start_node.scenePos()
        sz = start_node.z_pos
        for pipe in start_node.pipes:
            other = pipe.node2 if pipe.node1 is start_node else pipe.node1
            # Skip non-coplanar pipes (risers / cross-level)
            if abs(other.z_pos - sz) > Z_COPLANAR_TOL:
                continue
            op = other.scenePos()
            # Check if target_pt is the same as other node
            if math.hypot(target_pt.x() - op.x(), target_pt.y() - op.y()) < 5.0:
                return True
            # Check if target_pt lies on existing pipe segment
            dx, dy = op.x() - sp.x(), op.y() - sp.y()
            length_sq = dx * dx + dy * dy
            if length_sq < 1e-6:
                continue
            t = ((target_pt.x() - sp.x()) * dx + (target_pt.y() - sp.y()) * dy) / length_sq
            if 0.01 < t < 0.99:
                proj_x = sp.x() + t * dx
                proj_y = sp.y() + t * dy
                dist = math.hypot(target_pt.x() - proj_x, target_pt.y() - proj_y)
                if dist < 10.0:
                    return True
        return False

    def _try_extend_collinear(self, start_node, end_node, template) -> bool:
        """If start_node has exactly one other pipe and the new direction is
        collinear, extend that pipe to *end_node* and remove start_node.

        Returns True if extension happened, False otherwise.
        """
        # Don't merge if the node has a sprinkler
        if start_node.has_sprinkler():
            return False

        other_pipes = [p for p in start_node.pipes]
        if len(other_pipes) != 1:
            return False  # junction or isolated — don't merge

        existing = other_pipes[0]
        far_node = existing.node2 if existing.node1 is start_node else existing.node1

        # Direction of existing pipe (far_node → start_node)
        sp = start_node.scenePos()
        fp = far_node.scenePos()
        ep = end_node.scenePos()

        dx_old = sp.x() - fp.x()
        dy_old = sp.y() - fp.y()
        dx_new = ep.x() - sp.x()
        dy_new = ep.y() - sp.y()

        len_old = math.hypot(dx_old, dy_old)
        len_new = math.hypot(dx_new, dy_new)
        if len_old < 1e-6 or len_new < 1e-6:
            return False

        # Normalise
        ux_old, uy_old = dx_old / len_old, dy_old / len_old
        ux_new, uy_new = dx_new / len_new, dy_new / len_new

        # Dot product: collinear if ≈ 1.0 (same direction continuation)
        dot = ux_old * ux_new + uy_old * uy_new
        if abs(dot - 1.0) > 0.05:  # ~5° tolerance
            return False

        # Extend: reconnect existing pipe — replace start_node with end_node
        # Only remove from the node being replaced (start_node), keep far_node
        if existing in start_node.pipes:
            start_node.pipes.remove(existing)

        # Reconnect the pipe endpoint
        if existing.node1 is start_node:
            existing.node1 = end_node
        else:
            existing.node2 = end_node
        end_node.pipes.append(existing)
        existing.update_geometry()
        existing.set_pipe_display()
        existing.update_label()
        existing.update()

        # Remove orphaned start_node
        if len(start_node.pipes) == 0:
            self._scene.sprinkler_system.remove_node(start_node)
            self._scene.removeItem(start_node)

        # Update fittings at both endpoints + apply DM colours
        far_node.fitting.update()
        self._apply_fitting_dm_colors(far_node.fitting)
        end_node.fitting.update()
        self._apply_fitting_dm_colors(end_node.fitting)
        self._scene.update()
        return True

    def _convert_45_elbow_to_wye(self, junction_node, template):
        """If the junction has a sharp 45° angle between pipe vectors,
        add a 1-ft capped stub on the through branch to create a wye.

        A 135° angle between vectors is a normal 45° elbow (keep it).
        A 45° angle between vectors is too sharp for a real fitting —
        add a stub continuing the *first* (through) pipe direction so
        the node becomes a 3-pipe wye.
        """
        if junction_node.fitting.type != "45elbow":
            return

        pipes = list(junction_node.pipes)
        if len(pipes) != 2:
            return

        jp = junction_node.scenePos()

        v = []
        for p in pipes:
            far = p.node2 if p.node1 is junction_node else p.node1
            fp = far.scenePos()
            dx, dy = fp.x() - jp.x(), fp.y() - jp.y()
            length = math.hypot(dx, dy)
            if length < 1e-6:
                return
            v.append((dx / length, dy / length, p))

        angle = abs(CAD_Math.get_angle_between_vectors(
            QPointF(v[0][0], v[0][1]), QPointF(v[1][0], v[1][1]),
            signed=False))

        # 135° between vectors → normal 45° elbow (body angle), leave it
        if math.isclose(angle, 135, abs_tol=10):
            return

        # ~45° angle: too sharp — add a stub on the through branch.
        # The through pipe is the one placed FIRST (earlier in the list).
        # The new pipe (branch) was just appended, so it's last.
        through_dir = (v[0][0], v[0][1])

        # Stub continues opposite the through direction (away from the first pipe)
        STUB_LENGTH = 304.8  # 1 ft in mm
        stub_x = jp.x() - through_dir[0] * STUB_LENGTH
        stub_y = jp.y() - through_dir[1] * STUB_LENGTH
        stub_node = self.add_node(stub_x, stub_y)

        # Add stub pipe
        self.add_pipe(junction_node, stub_node, template)

        # Let the existing fitting logic determine type (3 pipes → wye)
        junction_node.fitting.update()
        stub_node.fitting.update()

    # ── Vertical pipe helpers ─────────────────────────────────────────────

    def _compute_template_z_pos(self, template, node_idx: int = 1) -> float | None:
        """Compute the z_pos (mm) that a template pipe would impose.

        *node_idx* selects which endpoint: 1 for start node, 2 for end node.
        Uses per-node ceiling attributes when available, falling back to the
        pipe-level Ceiling Level / Ceiling Offset properties.
        """
        if node_idx == 1:
            ceiling_lvl_name = getattr(template, "node1_ceiling_level", None)
            offset = getattr(template, "node1_ceiling_offset", None)
        else:
            ceiling_lvl_name = getattr(template, "node2_ceiling_level", None)
            offset = getattr(template, "node2_ceiling_offset", None)
        # Fallback to defaults (pipe-level ceiling attrs were removed)
        if not ceiling_lvl_name:
            ceiling_lvl_name = DEFAULT_LEVEL
        if offset is None:
            offset = DEFAULT_CEILING_OFFSET_MM
        if not ceiling_lvl_name or not self._scene._level_manager:
            return None
        lvl = self._scene._level_manager.get(ceiling_lvl_name)
        if lvl is None:
            return None
        return lvl.elevation + offset

    def _make_intermediate_node(self, existing_node, template):
        """Create a node at *existing_node*'s XY but at the template's ceiling level.

        Bypasses ``add_node()`` because ``find_nearby_node()`` would return
        *existing_node* (same XY within SNAP_RADIUS).  Returns the new node.
        """
        ex = existing_node.scenePos().x()
        ey = existing_node.scenePos().y()

        intermediate = Node(ex, ey)
        intermediate.level = self._scene.active_level

        ceiling_lvl = getattr(template, "node1_ceiling_level", None) or DEFAULT_LEVEL
        ceiling_off = getattr(template, "node1_ceiling_offset", None)
        if ceiling_off is None:
            ceiling_off = DEFAULT_CEILING_OFFSET_MM
        intermediate.ceiling_level = ceiling_lvl
        intermediate._properties["Ceiling Level"]["value"] = ceiling_lvl
        intermediate.ceiling_offset = ceiling_off
        intermediate._properties["Ceiling Offset"]["value"] = str(ceiling_off)
        if self._scene._level_manager:
            lvl = self._scene._level_manager.get(ceiling_lvl)
            if lvl:
                intermediate.z_pos = lvl.elevation + ceiling_off

        self._scene.addItem(intermediate)
        self._scene.sprinkler_system.add_node(intermediate)
        return intermediate

    def _make_intermediate_node_for_n2(self, existing_node, template):
        """Create a node at *existing_node*'s XY using template's Node 2 ceiling.

        Same as ``_make_intermediate_node`` but reads from the per-node
        ``node2_ceiling_level`` / ``node2_ceiling_offset`` attributes.
        """
        ex = existing_node.scenePos().x()
        ey = existing_node.scenePos().y()

        node = Node(ex, ey)
        node.level = self._scene.active_level

        ceiling_lvl = getattr(template, "node2_ceiling_level", None) or DEFAULT_LEVEL
        ceiling_off = getattr(template, "node2_ceiling_offset", None)
        if ceiling_off is None:
            ceiling_off = DEFAULT_CEILING_OFFSET_MM
        node.ceiling_level = ceiling_lvl
        node._properties["Ceiling Level"]["value"] = ceiling_lvl
        node.ceiling_offset = ceiling_off
        node._properties["Ceiling Offset"]["value"] = str(ceiling_off)
        if self._scene._level_manager:
            lvl = self._scene._level_manager.get(ceiling_lvl)
            if lvl:
                node.z_pos = lvl.elevation + ceiling_off

        self._scene.addItem(node)
        self._scene.sprinkler_system.add_node(node)
        return node

    def _create_vertical_connection(self, start_node, existing_end_node, template):
        """Insert an intermediate node + vertical pipe + horizontal pipe.

        * intermediate_node — same XY as *existing_end_node* but at the
          template's Ceiling Level / Offset.
        * vertical pipe — between *existing_end_node* and *intermediate_node*.
        * horizontal pipe — between *start_node* and *intermediate_node*
          (carries the full template).
        """
        intermediate = self._make_intermediate_node(existing_end_node, template)

        # Vertical pipe (existing_end_node <-> intermediate) — same XY, different z
        self.add_pipe(existing_end_node, intermediate, template,
                      _propagate_ceiling=False)

        # Horizontal pipe (start_node <-> intermediate) with full template
        self.add_pipe(start_node, intermediate, template)

    def _find_or_split_vertical_at_z(self, xy_pos: QPointF,
                                      target_z: float,
                                      template) -> "Node | None":
        """Find an existing node or split a vertical pipe at *target_z* near *xy_pos*.

        Search order:
        1. Existing node at this XY whose z_pos matches *target_z*.
        2. Vertical pipe at this XY whose Z range spans *target_z* — split it.

        Returns the node at *target_z*, or ``None`` if nothing suitable exists.
        """
        if target_z is None:
            return None
        snap_r = self._scene.SNAP_RADIUS
        # 1. Existing node at matching XY and Z
        for node in self._scene.sprinkler_system.nodes:
            if node.distance_to(xy_pos.x(), xy_pos.y()) <= snap_r:
                if abs(node.z_pos - target_z) < 0.5:
                    return node
        # 2. Vertical pipe spanning target_z
        for pipe in self._scene.sprinkler_system.pipes:
            if not pipe.node1 or not pipe.node2:
                continue
            if not pipe._is_vertical():
                continue
            pipe_xy = pipe.node1.scenePos()
            dx = pipe_xy.x() - xy_pos.x()
            dy = pipe_xy.y() - xy_pos.y()
            if (dx * dx + dy * dy) > snap_r * snap_r:
                continue
            z_lo = min(pipe.node1.z_pos, pipe.node2.z_pos)
            z_hi = max(pipe.node1.z_pos, pipe.node2.z_pos)
            if z_lo + 0.5 < target_z < z_hi - 0.5:
                return self._split_vertical_pipe(pipe, target_z, template)
        return None

    # ── End vertical pipe helpers ─────────────────────────────────────────

    # ── Pipe Tab-cycle ────────────────────────────────────────────────────

    def _update_pipe_tab_candidates(self, scene_pos, z_hint=None):
        """Rebuild pipe-mode Tab candidate list at the given cursor position.

        Resets Tab index to 0.  Called on every cursor move in pipe mode.
        """
        self._tab_candidates = self.find_nearby_candidates(
            scene_pos.x(), scene_pos.y(), z_hint=z_hint)
        self._tab_index = 0
        self._tab_pos = QPointF(scene_pos.x(), scene_pos.y())
        self._emit_pipe_tab_readout()

    def _emit_pipe_tab_readout(self):
        """Emit signal with current Tab-cycle candidate info for status bar."""
        candidates = self._tab_candidates
        if not candidates:
            self._scene.pipeNodeHighlight.emit("")
            return
        idx = self._tab_index
        node = candidates[idx]
        sm = self._scene.scale_manager
        elev_str = sm.format_length(node.z_pos) if sm else f"{node.z_pos:.1f} mm"
        level_str = getattr(node, "ceiling_level", "?")
        total = len(candidates)
        if total > 1:
            text = (f"Node @ {elev_str} ({level_str}) "
                    f"[{idx + 1}/{total}]  ·  Space = cycle")
        else:
            text = f"Node @ {elev_str} ({level_str})"
        self._scene.pipeNodeHighlight.emit(text)

    def cycle_tab(self):
        if self._scene.mode == "pipe" and len(self._tab_candidates) > 1:
            self._tab_index = (self._tab_index + 1) % len(self._tab_candidates)
            self._emit_pipe_tab_readout()

    # ── Pipe placement handlers ───────────────────────────────────────────

    def move_pipe(self, event, snapped):
        if self._scene.node_start_pos:
            start = self._scene.node_start_pos.scenePos()
            snapped_end = self._scene.node_start_pos.snap_point_45(start, snapped)

            # Seed the Dynamic Input HUD readout with the constrained endpoint
            # (no-op while a HUD field is engaged — see publish_placement_state).
            self._scene.publish_placement_state(start, snapped_end)

            # Update Tab cycling candidates at cursor position
            template = getattr(self._scene, "current_template", None)
            template_z2 = (self._compute_template_z_pos(template, node_idx=2)
                           if template is not None else None)
            self._update_pipe_tab_candidates(snapped_end, z_hint=template_z2)

            self._scene.update_preview_node(snapped_end)
            self._scene.preview_pipe.setLine(start.x(), start.y(), snapped_end.x(), snapped_end.y())

            # Style preview from current template
            if template:
                from .pipe import Pipe
                from .constants import PIPE_COLORS
                col_name = template._properties.get("Colour", {}).get("value", "Red")
                color = QColor(PIPE_COLORS.get(col_name, "#e62828"))
                width = Pipe.display_width_mm(template)
                pen = QPen(color, width)
                self._scene.preview_pipe.setPen(pen)

                # Preview label — diameter on top, length below
                dx = snapped_end.x() - start.x()
                dy = snapped_end.y() - start.y()
                length_mm = math.hypot(dx, dy)
                sm = self._scene.scale_manager
                dia_str = template._properties.get("Diameter", {}).get("value", "")
                if sm and dia_str:
                    try:
                        dia_str = sm.format_length(float(dia_str))
                    except (ValueError, TypeError):
                        pass
                len_str = sm.format_length(length_mm) if sm else f"{length_mm:.0f} mm"
                lbl = f"{dia_str}\n{len_str}" if dia_str else len_str
                self._scene._preview_label.setText(lbl)
                # Font size from template label size (inches → mm scene units)
                label_size = 12
                try:
                    label_size = int(template._properties.get(
                        "Label Size", {}).get("value", 12))
                except (ValueError, TypeError):
                    pass
                font = QFont("Consolas")
                font.setPixelSize(max(1, int(label_size * 25.4)))
                self._scene._preview_label.setFont(font)
                mid_x = (start.x() + snapped_end.x()) / 2
                mid_y = (start.y() + snapped_end.y()) / 2
                br = self._scene._preview_label.boundingRect()
                self._scene._preview_label.setPos(mid_x - br.width() / 2, mid_y - br.height() - 50)
                self._scene._preview_label.show()
            else:
                pen = QPen(Qt.GlobalColor.darkGray, 3, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self._scene.preview_pipe.setPen(pen)
                self._scene._preview_label.hide()

            self._scene.preview_pipe.show()
        else:
            # Before first click — track candidates at cursor for Tab cycling
            self._scene.update_preview_node(snapped)
            template = getattr(self._scene, "current_template", None)
            template_z1 = (self._compute_template_z_pos(template, node_idx=1)
                           if template is not None else None)
            self._update_pipe_tab_candidates(snapped, z_hint=template_z1)
            self._scene.preview_pipe.hide()
            self._scene._preview_label.hide()

    def press_pipe(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._scene.node_start_pos is None:
            template = getattr(self._scene, "current_template", None)

            # Use Tab-selected candidate if available
            tab_node = None
            if (self._tab_candidates
                    and self._tab_index < len(self._tab_candidates)):
                tab_node = self._tab_candidates[self._tab_index]

            # Check for existing node BEFORE find_or_create_node
            template_z1 = (self._compute_template_z_pos(template, node_idx=1)
                           if template is not None else None)
            existing_start = (tab_node if tab_node is not None
                              else self.find_nearby_node(
                                  snapped.x(), snapped.y(), z_hint=template_z1))

            # Block starting a pipe from a node that's already full (4 = cross)
            if existing_start is not None and len(existing_start.pipes) >= 4:
                self._scene.warningIssued.emit(
                    "Connection Limit",
                    f"This node already has {len(existing_start.pipes)} connections (max 4).")
                return
            # Starting from a tee node is allowed — the second-click check
            # will validate the angle for the cross.

            if isinstance(item_under, Pipe):
                start_node = self.split_pipe(item_under, self._scene.project_click_onto_pipe_segment(snapped, item_under))
                self._scene._pipe_node_was_new = True  # split created new node
                _check_elevation = True  # split node inherits pipe's Z — may differ from template
            else:
                start_node = (tab_node if tab_node is not None
                              else self.find_or_create_node(
                                  snapped.x(), snapped.y(), z_hint=template_z1))
                self._scene._pipe_node_was_new = (existing_start is None)
                _check_elevation = (existing_start is not None and existing_start is start_node)

            # Check elevation mismatch on pre-existing or pipe-split nodes
            if _check_elevation and template is not None:
                template_z = self._compute_template_z_pos(template, node_idx=1)
                if template_z is not None and abs(start_node.z_pos - template_z) > 0.01:
                    if not hasattr(self._scene, "_pending_confirm_data"):
                        self._scene._pending_confirm_data = {}
                    self._scene._pending_confirm_data["elev_start"] = {
                        "start_node": start_node, "template": template}
                    sm = self._scene.scale_manager
                    _fz = sm.format_length if sm else (lambda v: f"{v:.1f} mm")
                    self._scene.confirmRequested.emit(
                        "elev_mismatch_start",
                        "Elevation Mismatch",
                        f"Start node is at elevation {_fz(start_node.z_pos)} "
                        f"but the template targets {_fz(template_z)}.")
                    # Result handled by complete_confirmation(); flow resumes
                    # with start_node potentially replaced by intermediate
                    return

            self._scene.node_start_pos = start_node
            # Reset Tab cycling after committing start node
            self._tab_candidates = []
            self._tab_index = 0
            # Transition to phase 1: lock Node 1, allow Node 2 editing
            if template is not None:
                if self._scene._pipe_node_was_new:
                    # New node — apply template elevation TO the node
                    start_node.ceiling_level = template.node1_ceiling_level
                    start_node.ceiling_offset = template.node1_ceiling_offset
                else:
                    # Existing node — adopt its elevation for Node 1
                    template.node1_ceiling_level = start_node.ceiling_level
                    template.node1_ceiling_offset = start_node.ceiling_offset
                # Default Node 2 to match Node 1 (horizontal pipe default)
                template.node2_ceiling_level = template.node1_ceiling_level
                template.node2_ceiling_offset = template.node1_ceiling_offset
                template._placement_phase = 1
                self._scene.requestPropertyUpdate.emit(template)
            self._scene.instructionChanged.emit("Pick end node")
        else:
            start_pos   = self._scene.node_start_pos.scenePos()
            snapped_end = self._scene.node_start_pos.snap_point_45(start_pos, snapped)
            return self._commit_pipe_at(snapped_end, item_under)

    def _commit_pipe_at(self, snapped_end, item_under) -> bool:
        """Commit the second-click pipe body at an already-final *snapped_end*.

        Shared post-snap commit path for both mouse (which snaps via
        ``snap_point_45`` first) and typed input (which computes the exact
        endpoint and MUST NOT be re-snapped). ``item_under`` is the item under
        a mouse click for split-on-pipe; None for typed input.

        Returns:
            True on success (pipe placed) or when an elevation-mismatch
            confirmation is pending (the async dialog completes the commit).
            False on a hard rejection (backtrack / connection limit / invalid
            4th branch / zero-length), leaving the placement armed.
        """
        template = getattr(self._scene, "current_template", None)

        # ── Backtrack check (before creating/splitting nodes) ─────
        if self._would_backtrack_at(self._scene.node_start_pos, snapped_end):
            self._scene.warningIssued.emit(
                "Pipe Overlap",
                "Cannot place a pipe back over an existing pipe segment.")
            return False

        # ── Node connection-limit & angle validation ─────────────
        # Only count coplanar pipes — risers don't consume branch slots
        _sz = self._scene.node_start_pos.z_pos
        start_pipes = sum(1 for p in self._scene.node_start_pos.pipes
                          if abs((p.node2 if p.node1 is self._scene.node_start_pos
                                  else p.node1).z_pos - _sz) <= Z_COPLANAR_TOL)
        if start_pipes >= 4:
            self._scene.warningIssued.emit(
                "Connection Limit",
                f"Start node already has {start_pipes} coplanar connections (max 4).")
            return False
        # Adding a 4th branch is only valid to turn a tee into a cross
        if start_pipes == 3:
            err = self._validate_4th_branch(self._scene.node_start_pos, snapped_end)
            if err:
                self._scene.warningIssued.emit("Invalid Connection", err)
                return False
        # Use Tab-selected candidate if available
        tab_node = None
        if (self._tab_candidates
                and self._tab_index < len(self._tab_candidates)):
            tab_node = self._tab_candidates[self._tab_index]

        template_z2 = (self._compute_template_z_pos(template, node_idx=2)
                       if template is not None else None)
        existing_end_check = (tab_node if tab_node is not None
                              else self.find_nearby_node(
                                  snapped_end.x(), snapped_end.y(), z_hint=template_z2))
        if existing_end_check is not None:
            _ez = existing_end_check.z_pos
            end_pipes = sum(1 for p in existing_end_check.pipes
                            if abs((p.node2 if p.node1 is existing_end_check
                                    else p.node1).z_pos - _ez) <= Z_COPLANAR_TOL)
            if end_pipes >= 4:
                self._scene.warningIssued.emit(
                    "Connection Limit",
                    f"Target node already has {end_pipes} coplanar connections (max 4).")
                return False
            if end_pipes == 3:
                err = self._validate_4th_branch(
                    existing_end_check,
                    self._scene.node_start_pos.scenePos())
                if err:
                    self._scene.warningIssued.emit("Invalid Connection", err)
                    return False

        # Check for existing node BEFORE find_or_create_node
        existing_end = (tab_node if tab_node is not None
                        else self.find_nearby_node(
                            snapped_end.x(), snapped_end.y(), z_hint=template_z2))

        if isinstance(item_under, Pipe):
            end_node = self.split_pipe(item_under, self._scene.project_click_onto_pipe_segment(snapped_end, item_under))
            _check_end_elev = True  # split node inherits pipe's Z
        else:
            end_node = (tab_node if tab_node is not None
                        else self.find_or_create_node(
                            snapped_end.x(), snapped_end.y(), z_hint=template_z2))
            _check_end_elev = (existing_end is not None)

        # Block zero-length same-node pipe — unless template specifies
        # a different elevation for Node 2 (vertical pipe placement)
        if end_node is self._scene.node_start_pos:
            if template is not None:
                z1 = self._compute_template_z_pos(template, node_idx=1)
                z2 = self._compute_template_z_pos(template, node_idx=2)
                if z1 is not None and z2 is not None and abs(z1 - z2) > 0.5:
                    # Create a new node at same XY with Node 2's elevation
                    end_node = self._make_intermediate_node_for_n2(
                        self._scene.node_start_pos, template)
                else:
                    return False  # truly same position — wait for valid click
            else:
                return False

        # Detect elevation mismatch on an existing or pipe-split end node
        if _check_end_elev and template is not None:
            template_z = self._compute_template_z_pos(template, node_idx=2)
            if template_z is not None and abs(end_node.z_pos - template_z) > 0.01:
                if not hasattr(self._scene, "_pending_confirm_data"):
                    self._scene._pending_confirm_data = {}
                self._scene._pending_confirm_data["elev_end"] = {
                    "start_node": self._scene.node_start_pos,
                    "end_node": end_node, "template": template}
                sm = self._scene.scale_manager
                _fz = sm.format_length if sm else (lambda v: f"{v:.1f} mm")
                self._scene.confirmRequested.emit(
                    "elev_mismatch_end",
                    "Elevation Mismatch",
                    f"The target node is at elevation {_fz(end_node.z_pos)} "
                    f"but the template targets {_fz(template_z)}.")
                return True  # pending: the async dialog completes the commit

        # ── Collinear extension check ─────────────────────────────
        extended = self._try_extend_collinear(
            self._scene.node_start_pos, end_node, template)

        if not extended:
            new_pipe = self.add_pipe(
                self._scene.node_start_pos, end_node, template)
            self._scene.node_start_pos.fitting.update()
            end_node.fitting.update()
            # ── 45° elbow → wye + stub ────────────────────────────
            self._convert_45_elbow_to_wye(
                self._scene.node_start_pos, template)

        # Continuous polyline: end node becomes the next start node
        self._scene.node_start_pos = end_node
        self._scene._pipe_node_was_new = False
        # Reset Tab cycling after committing end node
        self._tab_candidates = []
        self._tab_index = 0
        self._scene.push_undo_state()
        # Update template: Node 1 adopts end node's elevation for next segment
        if template is not None:
            template.node1_ceiling_level = end_node.ceiling_level
            template.node1_ceiling_offset = end_node.ceiling_offset
            # Default Node 2 to match for horizontal continuation
            template.node2_ceiling_level = end_node.ceiling_level
            template.node2_ceiling_offset = end_node.ceiling_offset
            template._placement_phase = 1
            self._scene.requestPropertyUpdate.emit(template)
        self._scene.instructionChanged.emit("Pick next node (Esc/double-click to finish)")
        return True

    # ── Elevation-mismatch confirmation resume ────────────────────────────

    def resume_elev_mismatch(self, which, result):
        if which == "start":
            self._scene._pending_confirm_data = getattr(self._scene, "_pending_confirm_data", {})
            data = self._scene._pending_confirm_data.pop("elev_start", None)
            if not data:
                return
            start_node = data["start_node"]
            template = data["template"]

            if result == "riser":
                # Create vertical riser, checking for overlap first
                xy = start_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=1)
                split_node = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if split_node is not None:
                    # Reuse existing / split node — no new vertical pipe needed
                    self._scene.node_start_pos = split_node
                else:
                    intermediate = self._make_intermediate_node(start_node, template)
                    self.add_pipe(start_node, intermediate, template,
                                  _propagate_ceiling=False)
                    self._scene.node_start_pos = intermediate
                self._scene.instructionChanged.emit("Pick end node")

            elif result == "match":
                # Place pipe at existing node's elevation — adopt node's
                # ceiling into template (mirrors normal existing-node flow)
                template.node1_ceiling_level = start_node.ceiling_level
                template.node1_ceiling_offset = start_node.ceiling_offset
                template.node2_ceiling_level = start_node.ceiling_level
                template.node2_ceiling_offset = start_node.ceiling_offset
                self._scene.node_start_pos = start_node
                self._scene.instructionChanged.emit("Pick end node")

            elif result == "template":
                # Keep template elevation; find/split existing geometry at that Z
                xy = start_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=1)
                target = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if target is not None:
                    self._scene.node_start_pos = target
                else:
                    # No existing geometry — create standalone node at template Z
                    self._scene.node_start_pos = self._make_intermediate_node(
                        start_node, template)
                self._scene.instructionChanged.emit("Pick end node")

            # Transition to phase 1: N1 locked, N2 editable
            template._placement_phase = 1
            self._scene.requestPropertyUpdate.emit(template)

        elif which == "end":
            self._scene._pending_confirm_data = getattr(self._scene, "_pending_confirm_data", {})
            data = self._scene._pending_confirm_data.pop("elev_end", None)
            if not data:
                return
            start_node = data["start_node"]
            end_node = data["end_node"]
            template = data["template"]

            if result == "riser":
                # Create vertical riser, checking for overlap first
                xy = end_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=2)
                split_node = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if split_node is not None:
                    # Reuse existing / split node — connect horizontal pipe to it
                    intermediate = split_node
                else:
                    intermediate = self._make_intermediate_node(end_node, template)
                    self.add_pipe(intermediate, end_node, template,
                                  _propagate_ceiling=False)
                # Place the horizontal pipe to the intermediate node
                extended = self._try_extend_collinear(
                    start_node, intermediate, template)
                if not extended:
                    self.add_pipe(start_node, intermediate, template)
                    start_node.fitting.update()
                    intermediate.fitting.update()
                    self._convert_45_elbow_to_wye(start_node, template)
                self._scene.node_start_pos = intermediate
                self._scene._pipe_node_was_new = False
                self._scene.push_undo_state()
                self._scene.instructionChanged.emit(
                    "Pick next node (Esc/double-click to finish)")

            elif result == "match":
                # Place pipe at existing node's elevation — adopt node's
                # ceiling into template (mirrors normal existing-node flow)
                template.node2_ceiling_level = end_node.ceiling_level
                template.node2_ceiling_offset = end_node.ceiling_offset
                self._scene.requestPropertyUpdate.emit(template)
                extended = self._try_extend_collinear(
                    start_node, end_node, template)
                if not extended:
                    self.add_pipe(start_node, end_node, template)
                    start_node.fitting.update()
                    end_node.fitting.update()
                    self._convert_45_elbow_to_wye(start_node, template)
                self._scene.node_start_pos = end_node
                self._scene._pipe_node_was_new = False
                self._scene.push_undo_state()
                self._scene.instructionChanged.emit(
                    "Pick next node (Esc/double-click to finish)")

            elif result == "template":
                # Keep template elevation; find/split existing geometry at that Z
                xy = end_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=2)
                target = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if target is None:
                    target = self._make_intermediate_node(end_node, template)
                # Place horizontal pipe to the target node
                extended = self._try_extend_collinear(
                    start_node, target, template)
                if not extended:
                    self.add_pipe(start_node, target, template)
                    start_node.fitting.update()
                    target.fitting.update()
                    self._convert_45_elbow_to_wye(start_node, template)
                self._scene.node_start_pos = target
                self._scene._pipe_node_was_new = False
                self._scene.push_undo_state()
                self._scene.instructionChanged.emit(
                    "Pick next node (Esc/double-click to finish)")

    def clear(self):
        """Idempotent teardown of pipe placement transient state.

        Absorbs set_mode's orphan-delete (only a freshly-created start node is
        removed; a pre-existing node, or a QPointF from paste/move, survives)
        plus the Tab-cycle reset.
        """
        sc = self._scene
        if sc.node_start_pos is not None:
            if isinstance(sc.node_start_pos, Node) and sc._pipe_node_was_new:
                self.remove_node(sc.node_start_pos)
            sc.node_start_pos = None
        sc._pipe_node_was_new = False
        self._tab_candidates = []
        self._tab_index = 0
        self._tab_pos = None

    def cancel_placement(self) -> bool:
        """Cancel a pipe chain mid-placement, staying in pipe mode.

        Returns True if a cancel was handled (a start node existed). Mirrors the
        legacy main._on_escape pipe branch."""
        sc = self._scene
        if sc.node_start_pos is None:
            return False
        if (sc._pipe_node_was_new
                and isinstance(sc.node_start_pos, Node)
                and not sc.node_start_pos.pipes):
            self.remove_node(sc.node_start_pos)
        sc.node_start_pos = None
        sc._pipe_node_was_new = False
        sc.preview_pipe.hide()
        sc.preview_node.hide()
        sc.instructionChanged.emit("Pick start node")
        return True
