"""
scene_io.py
===========
Mixin providing file I/O (save / load / clear) for Model_Space.

Extracted from Model_Space.py to keep the main scene class focused on
interactive behaviour.  Mixed into Model_Space's MRO — all ``self``
references resolve against the Model_Space instance at runtime.

Usage::

    class Model_Space(SceneIOMixin, QGraphicsScene):
        ...
"""

from __future__ import annotations

import json
import logging
import os
import shutil

from .constants import DEFAULT_LEVEL
from .underlay import Underlay
from .network_codec import (
    serialize_node, serialize_pipe,
    serialize_water_supply, serialize_design_area,
)

log = logging.getLogger("FirePro3D")


class SceneIOMixin:
    """Save / Load / Clear operations for the plan-view scene."""

    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------

    def save_to_file(self, filename: str):
        """Serialise the full scene to JSON."""
        self._project_path = os.path.abspath(filename)
        from .display_manager import get_display_settings_for_save

        # --- Nodes (assign temp IDs) ---
        node_list = list(self.sprinkler_system.nodes)
        node_id = {n: i for i, n in enumerate(node_list)}

        nodes_data = [serialize_node(node, node_id) for node in node_list]

        # --- Pipes ---
        pipes_data = []
        for pipe in self.sprinkler_system.pipes:
            if pipe.node1 is None or pipe.node2 is None:
                continue
            if pipe.node1 not in node_id or pipe.node2 not in node_id:
                continue
            pipes_data.append(serialize_pipe(pipe, node_id))

        # --- Annotations: notes + dimensions are forbidden model content
        # (containment C8) — no longer written.  Annotation only ever held
        # notes/dimensions, so annotations serialise to [].
        annotations_data = []

        # (HatchItem retired 2026-08-22; legacy loose geometry / constraints /
        #  standalone text no longer written under containment C8.)

        # --- Underlays ---
        underlays_data = []
        project_dir = os.path.dirname(os.path.abspath(filename))
        for data, item in self.underlays:
            if item is not None:
                data.x        = item.scenePos().x()
                data.y        = item.scenePos().y()
                data.scale    = item.scale()
                data.rotation = item.rotation()
                data.opacity  = item.opacity()
            d = data.to_dict()
            d["path"] = Underlay.relativize_path(
                os.path.abspath(data.path), project_dir)
            underlays_data.append(d)

        # --- Water supply ---
        ws = self.water_supply_node
        ws_data = serialize_water_supply(ws) if ws is not None else None

        # --- Design areas ---
        design_areas_data = [
            serialize_design_area(da, node_id, self.active_design_area)
            for da in self.design_areas
        ]

        # --- Levels ---
        levels_data = (
            self._level_manager.to_list()
            if self._level_manager
            else []
        )

        # --- Construction geometry + standalone text: forbidden loose content
        # (containment C8) — no longer written to the payload.
        gridlines_data = [gl.to_dict() for gl in self._gridlines]
        walls_data = [w.to_dict() for w in self._walls]
        floor_slabs_data = [fs.to_dict() for fs in self._floor_slabs]  # two-boundary schema via to_dict
        roofs_data = [r.to_dict() for r in self._roofs]
        rooms_data = [r.to_dict() for r in self._rooms]

        # --- Blocks (definitions embedded; instances reference by id) ---
        block_definitions_data = {bid: d.to_dict()
                                  for bid, d in self._block_definitions.items()}
        blocks_data = [inst.to_dict() for inst in self._block_instances]

        # --- Display settings (per-project) ---
        display_settings_data = get_display_settings_for_save()
        from .paper_display import get_paper_display_for_save
        paper_display_data = get_paper_display_for_save()

        # --- Assemble and write ---
        payload = {
            "version":             self.SAVE_VERSION,
            "project_info":        self._project_info,
            "scale":               self.scale_manager.to_dict(),
            "display_settings":    display_settings_data,
            "paper_display":       paper_display_data,
            "levels":              levels_data,
            "plan_views":          (self._plan_view_manager.to_list()
                                    if self._plan_view_manager else []),
            "active_level":        self.active_level,
            "nodes":               nodes_data,
            "pipes":               pipes_data,
            "annotations":         annotations_data,
            "underlays":           underlays_data,
            "water_supply":        ws_data,
            "design_areas":        design_areas_data,
            "gridlines":           gridlines_data,
            "walls":               walls_data,
            "floor_slabs":         floor_slabs_data,
            "roofs":               roofs_data,
            "rooms":               rooms_data,
            "block_definitions":   block_definitions_data,
            "blocks":              blocks_data,
            "detail_views":        (self._detail_manager.to_list()
                                    if getattr(self, "_detail_manager", None) else []),
            "sheets":              [s.to_dict() for s in self._sheets] if hasattr(self, '_sheets') else [],
            "titleblock_template": getattr(self, "_titleblock_template", None),
        }
        # Ensure all underlays have cache entries
        self._underlay_ctl._ensure_underlay_caches(os.path.abspath(filename))

        bak_path = filename + ".bak"
        if os.path.exists(filename):
            shutil.copy2(filename, bak_path)

        try:
            with open(filename, "w") as f:
                json.dump(payload, f, indent=2)
            self._show_status(f"Saved to {filename}")
            if os.path.exists(bak_path):
                os.remove(bak_path)
            return True
        except Exception as e:
            self._show_status(f"Save failed: {e}")
            if os.path.exists(bak_path):
                shutil.copy2(bak_path, filename)
            return False

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------

    def load_from_file(self, filename: str):
        """Clear the scene and restore from JSON."""
        from .node import Node
        from .underlay import Underlay
        from .scale_manager import ScaleManager
        from .gridline import GridlineItem
        from .wall import WallSegment
        from .block_definition import BlockDefinition
        from .floor_slab import FloorSlab
        from .roof import RoofItem
        from .room import Room
        from .wall_opening import WallOpening
        from PyQt6.QtGui import QColor

        try:
            with open(filename, "r") as f:
                payload = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            self._show_status(f"Failed to open: {e}")
            return

        version = payload.get("version", 1)
        self._clear_scene()
        self._project_path = os.path.abspath(filename)

        # --- Display settings ---
        self._loaded_display_settings = payload.get("display_settings", None)
        self._loaded_paper_display = payload.get("paper_display", None)

        # --- Scale ---
        if "scale" in payload:
            self._project_info = payload.get("project_info", {})
            self.scale_manager = ScaleManager.from_dict(payload["scale"])
        else:
            self.scale_manager = ScaleManager()

        # --- Levels ---
        levels_data = payload.get("levels", [])
        if levels_data and self._level_manager:
            self._level_manager.from_list(levels_data)
        saved_active = payload.get("active_level", "")
        if saved_active and self._level_manager and self._level_manager.get(saved_active):
            self.active_level = saved_active

        # --- Plan views (per-view cut-plane settings) ---
        pv_data = payload.get("plan_views", [])
        if pv_data and self._plan_view_manager:
            self._plan_view_manager.from_list(pv_data)

        # --- Detail views ---
        detail_data = payload.get("detail_views", [])
        if detail_data and getattr(self, "_detail_manager", None):
            self._detail_manager.from_list(detail_data)

        # --- Sheets (paper space) ---
        from .paper_space import Sheet
        sheet_data = payload.get("sheets", [])
        self._sheets = [Sheet.from_dict(d) for d in sheet_data]

        # --- Title block template (embedded copy is authoritative) ---
        self._titleblock_template = payload.get("titleblock_template", None)
        from .titleblock_template import migrate_legacy_fields, migrate_project_info
        from .paper_space import DEFAULT_TITLE_BLOCK_FIELDS
        # One-way address-key migration (2026-08-04): address/city/state →
        # address1/address2 before anything reads the dict.
        self._project_info = migrate_project_info(
            getattr(self, "_project_info", {}))
        try:
            migrate_legacy_fields(
                [s.title_block_fields for s in self._sheets],
                self._project_info,
                skip_values=DEFAULT_TITLE_BLOCK_FIELDS,
            )
        except Exception as exc:
            # Migration is best-effort: a malformed project_info container must
            # never abort project open (load continues with unmigrated fields).
            log.warning("Legacy title-block migration skipped: %s", exc)

        # --- Nodes ---
        # Create each node unconditionally — bypass find_nearby_node so that
        # vertical pipes (same XY, different Z) keep distinct node objects.
        from .network_codec import deserialize_node
        id_to_node: dict[int, Node] = {}
        for entry in payload.get("nodes", []):
            id_to_node[entry["id"]] = deserialize_node(self, entry)

        # --- Pipes ---
        from .network_codec import deserialize_pipe
        for entry in payload.get("pipes", []):
            deserialize_pipe(self, entry, id_to_node)

        # --- Fittings ---
        for node in id_to_node.values():
            node.fitting.update()
            pending = getattr(node, "_fitting_display_overrides_pending", {})
            if pending:
                node.fitting._display_overrides = pending
                del node._fitting_display_overrides_pending

        # --- Annotations: notes + dimensions are forbidden model content
        # (containment C8) — read-but-discard silently.  Annotation only ever
        # held notes/dimensions, so the restore loop is dropped entirely.

        # --- Underlays ---
        project_dir = os.path.dirname(os.path.abspath(filename))
        missing_underlays = []
        for entry in payload.get("underlays", []):
            udata = Underlay.from_dict(entry)
            resolved = Underlay.resolve_path(udata.path, project_dir)

            if resolved is not None:
                udata.path = resolved
                source_mtime = os.path.getmtime(resolved)
            else:
                # Resolve path for cache key even though file is gone
                if not os.path.isabs(udata.path):
                    udata.path = os.path.normpath(
                        os.path.join(project_dir, udata.path))
                source_mtime = None

            # Try cache first (fast path)
            if self._underlay_ctl._load_underlay_from_cache(udata, source_mtime):
                continue
            # Cache miss — fall back to source file parsing
            if resolved is None:
                missing_underlays.append(udata)
                continue

            if udata.type == "pdf":
                self.import_pdf(udata.path, dpi=udata.dpi, page=udata.page,
                                x=udata.x, y=udata.y, _record=udata,
                                import_mode=udata.import_mode)
            elif udata.type == "dxf":
                self.import_dxf(udata.path, color=QColor(udata.colour),
                                line_weight=udata.line_weight,
                                x=udata.x, y=udata.y,
                                layers=udata.selected_layers,
                                _record=udata,
                                layout=udata.layout)
            elif udata.type == "dwg":
                from .dwg_converter import (
                    find_oda_converter, convert_dwg_to_dxf,
                )
                oda = find_oda_converter()
                if oda is None:
                    missing_underlays.append(udata)
                    continue
                converted = convert_dwg_to_dxf(
                    oda, udata.path,
                    project_dir=os.path.dirname(os.path.abspath(filename)))
                if converted is None:
                    missing_underlays.append(udata)
                    continue
                self.import_dxf(converted, color=QColor(udata.colour),
                                line_weight=udata.line_weight,
                                x=udata.x, y=udata.y,
                                layers=udata.selected_layers,
                                _record=udata,
                                layout=udata.layout,
                                skip_sanitize=True)  # ODA output is clean
                # Store DWG metadata for async cleanup in _on_dxf_finished.
                # _dxf_import_params moved to the controller (underlay slice);
                # import_dxf sets it synchronously above, so it is populated here.
                if self._underlay_ctl._dxf_import_params:
                    self._underlay_ctl._dxf_import_params["_dwg_cleanup_path"] = converted
                    self._underlay_ctl._dxf_import_params["_dwg_source_path"] = udata.path

        # Handle missing underlay files
        for udata in missing_underlays:
            self._create_underlay_placeholder(udata)

        if self.underlays:
            self.underlaysChanged.emit()

        if missing_underlays:
            from .themed_message import themed_warn
            paths = "\n".join(f"  \u2022 {u.path}" for u in missing_underlays)
            themed_warn(
                None, "Missing Underlay Files",
                f"{len(missing_underlays)} underlay file(s) could not be found:\n\n"
                f"{paths}\n\n"
                "Use right-click \u2192 Relink in the browser tree to reconnect.",
            )

        # --- Water supply ---
        ws_data = payload.get("water_supply")
        if ws_data:
            from .network_codec import deserialize_water_supply
            deserialize_water_supply(self, ws_data)

        # --- Design areas ---
        from .network_codec import deserialize_design_area
        for da_entry in payload.get("design_areas", []):
            deserialize_design_area(self, da_entry, id_to_node)
            # Tile geometry is recomputed after walls & rooms load —
            # computing here would produce wall-less (over-wide) tiles

        # --- Construction geometry + standalone model text: forbidden loose
        # content (containment C8) — read-but-discard silently.  The restore
        # loops for polylines / draw_* / reference_lines / polygons / texts are
        # dropped; the single info line below reports the total dropped count.

        # --- Gridlines ---
        for entry in payload.get("gridlines", []):
            gl = GridlineItem.from_dict(entry)
            self.addItem(gl)
            self._gridlines.append(gl)

        # --- Walls ---
        for entry in payload.get("walls", []):
            wall = WallSegment.from_dict(entry)
            self.addItem(wall)
            self._walls.append(wall)
            for op_data in entry.get("openings", []):
                op = WallOpening.from_dict(op_data, wall=wall)
                wall.openings.append(op)
                self.addItem(op)

        # --- Floor slabs ---
        for entry in payload.get("floor_slabs", []):
            slab = FloorSlab.from_dict(entry)
            self.addItem(slab)
            self._floor_slabs.append(slab)

        # --- Roofs ---
        for entry in payload.get("roofs", []):
            roof = RoofItem.from_dict(entry)
            roof._scale_manager_ref = self.scale_manager
            self.addItem(roof)
            self._roofs.append(roof)

        # --- Rooms ---
        for entry in payload.get("rooms", []):
            room = Room.from_dict(entry)
            room._scale_manager_ref = self.scale_manager
            self.addItem(room)
            self._rooms.append(room)

        # --- Blocks: definitions first (registry), then instances ---
        for bid, ddict in payload.get("block_definitions", {}).items():
            self._block_definitions[bid] = BlockDefinition.from_dict(ddict)
        for bdict in payload.get("blocks", []):
            _pos = bdict.get("pos", [0.0, 0.0])
            inst = self.place_block_instance(
                bdict["block_id"], (_pos[0], _pos[1]),
                rotation=bdict.get("rotation", 0.0),
                level=bdict.get("level", "Level 1"),
            )
            inst.attributes = dict(bdict.get("attributes", {}))
        self.blockDefinitionsChanged.emit()

        # --- Design-area tiles (now that walls & rooms exist) ---
        for da in self.design_areas:
            da.compute_area(self.scale_manager)

        # --- Recalculate auto-name counters ---
        self._recalc_name_counters()
        from .gridline import sync_grid_counters, apply_duplicate_warnings
        sync_grid_counters(self._gridlines)
        apply_duplicate_warnings(self._gridlines)

        # --- Legacy hatch migration: retired under containment C8.  Legacy
        # "hatches" recreated loose PolylineItems (forbidden loose geometry),
        # so the migration block is dropped — those entries clean-drop too.

        # --- Constraints: model-scene constraints are forbidden (containment
        # C8) — read-but-discard silently.  The restore block is dropped.

        # --- Clean-drop log (containment C1/C8) ---
        # Report a single info line if any forbidden loose content was present.
        _dropped = (len(payload.get("polylines", [])) + len(payload.get("draw_lines", []))
                    + len(payload.get("reference_lines", [])) + len(payload.get("draw_rectangles", []))
                    + len(payload.get("draw_circles", [])) + len(payload.get("draw_arcs", []))
                    + len(payload.get("draw_ellipses", [])) + len(payload.get("draw_splines", []))
                    + len(payload.get("polygons", [])) + len(payload.get("texts", []))
                    + len(payload.get("hatches", []))
                    + sum(1 for a in payload.get("annotations", []) if a.get("type") in ("note", "dimension"))
                    + len(payload.get("constraints", [])))
        if _dropped:
            log.info("Clean-drop: discarded %d unsupported loose item(s) on load (containment C1/C8)", _dropped)

        # Apply level visibility
        if self._level_manager:
            self._level_manager.apply_to_scene(self)

        # Start fresh undo history
        self._undo_stack = []
        self._undo_pos = -1
        self.push_undo_state()
        self._show_status(f"Loaded from {filename}")

    # ------------------------------------------------------------------
    # CLEAR
    # ------------------------------------------------------------------

    def _clear_scene(self):
        """Remove all user content, keeping preview items and origin markers."""
        # stop settle timer + drop pixmap before clear() deletes it (spec §18)
        self.abort_underlay_freeze()
        from .sprinkler_system import SprinklerSystem
        from .annotations import Annotation
        from .scale_manager import ScaleManager
        from .gridline import reset_grid_counters

        self._project_path = None
        self._project_info = {}
        self._titleblock_template = None
        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self._underlay_ctl.reset()
        self.scale_manager = ScaleManager()
        self.water_supply_node = None
        self.hydraulic_result = None
        for da in self.design_areas:
            if da.scene() is self:
                self.removeItem(da)
        self.design_areas = []
        self.active_design_area = None
        self._polylines = []
        self._polyline_active = None
        self._draw_lines = []
        self._reference_lines = []
        self._draw_rects = []
        self._draw_circles = []
        self._draw_arcs = []
        self._draw_ellipses = []
        self._draw_splines = []
        self._draw_polygons = []
        self._texts = []
        for inst in list(getattr(self, "_block_instances", [])):
            if inst.scene() is self:
                self.removeItem(inst)
        self._block_instances = []
        self._block_definitions = {}
        self._draw_line_anchor = None
        self._draw_rect_anchor = None
        self._draw_circle_center = None
        self._draw_rect_preview = None
        self._draw_circle_preview = None
        self._draw_arc_center = None
        self._draw_arc_radius = 0.0
        self._draw_arc_start_deg = 0.0
        self._draw_arc_step = 0
        self._draw_arc_radius_line = None
        self._draw_arc_preview = None
        self._text_anchor = None
        self._text_preview = None
        self._gridlines = []
        self._walls = []
        self._floor_slabs = []
        self._roofs = []
        self._rooms = []
        self._wall_anchor = None
        self._wall_chain_start = None
        self._floor_active = None
        self._roof_active = None
        self._constraints = []
        reset_grid_counters()
        self.dimension_start = None
        self._dim_line1 = None
        self._dim_preview_line = None
        self._dim_preview_label = None
        self._dim_pending = None
        self.active_level = DEFAULT_LEVEL
        if self._level_manager:
            self._level_manager.reset()
        self.clear()
        # self.clear() deleted the selection manipulator (a scene item);
        # recreate it so the frame + press routing survive a load/new reset.
        if hasattr(self, "_create_manipulator"):
            self._create_manipulator()
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()
        self._undo_stack = []
        self._undo_pos = -1
        self.push_undo_state()
