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
import os
import shutil

from PyQt6.QtCore import QPointF

from constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER, DEFAULT_CEILING_OFFSET_MM


class SceneIOMixin:
    """Save / Load / Clear operations for the plan-view scene."""

    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------

    def save_to_file(self, filename: str):
        """Serialise the full scene to JSON."""
        from display_manager import get_display_settings_for_save

        # --- Nodes (assign temp IDs) ---
        node_list = list(self.sprinkler_system.nodes)
        node_id = {n: i for i, n in enumerate(node_list)}

        nodes_data = []
        for node in node_list:
            entry = {
                "id":             node_id[node],
                "x":              node.scenePos().x(),
                "y":              node.scenePos().y(),
                "elevation":      node.z_pos,
                "z_offset":       getattr(node, "z_offset", node.z_pos),
                "user_layer":     getattr(node, "user_layer", "0"),
                "level":          getattr(node, "level", DEFAULT_LEVEL),
                "ceiling_level":  getattr(node, "ceiling_level", DEFAULT_LEVEL),
                "ceiling_offset_mm": getattr(node, "ceiling_offset", DEFAULT_CEILING_OFFSET_MM),
                "room_name":     getattr(node, "_room_name", ""),
                "sprinkler":      node.sprinkler.get_properties() if node.has_sprinkler() else None,
            }
            node_ovr = getattr(node, "_display_overrides", {})
            if node_ovr:
                entry["display_overrides"] = node_ovr
            if node.has_sprinkler():
                spr_ovr = getattr(node.sprinkler, "_display_overrides", {})
                if spr_ovr:
                    entry["sprinkler_display_overrides"] = spr_ovr
            fit_ovr = getattr(node.fitting, "_display_overrides", {}) if node.has_fitting() else {}
            if fit_ovr:
                entry["fitting_display_overrides"] = fit_ovr
            nodes_data.append(entry)

        # --- Pipes ---
        pipes_data = []
        for pipe in self.sprinkler_system.pipes:
            if pipe.node1 is None or pipe.node2 is None:
                continue
            if pipe.node1 not in node_id or pipe.node2 not in node_id:
                continue
            raw_props = {k: v["value"] for k, v in pipe._properties.items()}
            raw_props["Ceiling Offset"] = str(pipe.ceiling_offset)
            pipe_entry = {
                "node1_id":   node_id[pipe.node1],
                "node2_id":   node_id[pipe.node2],
                "user_layer": getattr(pipe, "user_layer", "0"),
                "level":      getattr(pipe, "level", DEFAULT_LEVEL),
                "ceiling_level":     getattr(pipe, "ceiling_level", DEFAULT_LEVEL),
                "ceiling_offset_mm": getattr(pipe, "ceiling_offset", DEFAULT_CEILING_OFFSET_MM),
                "properties": raw_props,
            }
            pipe_ovr = getattr(pipe, "_display_overrides", {})
            if pipe_ovr:
                pipe_entry["display_overrides"] = pipe_ovr
            pipes_data.append(pipe_entry)

        # --- Annotations ---
        annotations_data = []
        for dim in self.annotations.dimensions:
            annotations_data.append({
                "type": "dimension",
                "p1":   [dim._p1.x(), dim._p1.y()],
                "p2":   [dim._p2.x(), dim._p2.y()],
                "offset_dist": getattr(dim, "_offset_dist", 10),
                "witness_ext_override": getattr(dim, "_witness_ext_override", None),
                "properties": {k: v["value"] for k, v in dim.get_properties().items()},
                "user_layer": getattr(dim, "user_layer", DEFAULT_USER_LAYER),
                "level":      getattr(dim, "level", DEFAULT_LEVEL),
            })
        for note in self.annotations.notes:
            annotations_data.append({
                "type": "note",
                "x":    note.scenePos().x(),
                "y":    note.scenePos().y(),
                "text_width": note.textWidth(),
                "properties": {k: v["value"] for k, v in note.get_properties().items()},
                "user_layer": getattr(note, "user_layer", DEFAULT_USER_LAYER),
                "level":      getattr(note, "level", DEFAULT_LEVEL),
            })

        # --- Hatch items ---
        hatch_data = []
        for h in self._hatch_items:
            if hasattr(h, 'to_dict'):
                hatch_data.append(h.to_dict())

        # --- Constraints ---
        all_geom = self._all_geometry_items()
        geom_id = {item: i for i, item in enumerate(all_geom)}
        constraints_data = []
        for c in self._constraints:
            try:
                constraints_data.append(c.to_dict(geom_id))
            except (KeyError, AttributeError):
                pass

        # --- Underlays ---
        underlays_data = []
        for data, item in self.underlays:
            if item is not None:
                data.x        = item.scenePos().x()
                data.y        = item.scenePos().y()
                data.scale    = item.scale()
                data.rotation = item.rotation()
                data.opacity  = item.opacity()
            underlays_data.append(data.to_dict())

        # --- Water supply ---
        ws = self.water_supply_node
        ws_data = None
        if ws is not None:
            ws_data = {
                "x":          ws.pos().x(),
                "y":          ws.pos().y(),
                "properties": {k: v["value"] for k, v in ws.get_properties().items()},
            }
            ws_ovr = getattr(ws, "_display_overrides", {})
            if ws_ovr:
                ws_data["display_overrides"] = ws_ovr

        # --- Design areas ---
        design_areas_data = []
        for da in self.design_areas:
            spr_node_ids = []
            for spr in da.sprinklers:
                if spr.node and spr.node in node_id:
                    spr_node_ids.append(node_id[spr.node])
            design_areas_data.append({
                "sprinkler_node_ids": spr_node_ids,
                "properties": {k: v["value"] for k, v in da.get_properties().items()},
                "is_active": da is self.active_design_area,
            })

        # --- User layers ---
        layers_data = (
            self._user_layer_manager.to_list()
            if hasattr(self, "_user_layer_manager") and self._user_layer_manager
            else []
        )

        # --- Levels ---
        levels_data = (
            self._level_manager.to_list()
            if self._level_manager
            else []
        )

        # --- Construction geometry ---
        clines_data = [cl.to_dict() for cl in self._construction_lines]
        polylines_data = [pl.to_dict() for pl in self._polylines]
        draw_lines_data = [l.to_dict() for l in self._draw_lines]
        draw_rects_data = [r.to_dict() for r in self._draw_rects]
        draw_circles_data = [c.to_dict() for c in self._draw_circles]
        draw_arcs_data = [a.to_dict() for a in self._draw_arcs]
        gridlines_data = [gl.to_dict() for gl in self._gridlines]
        walls_data = [w.to_dict() for w in self._walls]
        floor_slabs_data = [fs.to_dict() for fs in self._floor_slabs]
        roofs_data = [r.to_dict() for r in self._roofs]
        rooms_data = [r.to_dict() for r in self._rooms]

        # --- Display settings (per-project) ---
        display_settings_data = get_display_settings_for_save()

        # --- Assemble and write ---
        payload = {
            "version":             self.SAVE_VERSION,
            "project_info":        self._project_info,
            "scale":               self.scale_manager.to_dict(),
            "display_settings":    display_settings_data,
            "user_layers":         layers_data,
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
            "construction_lines":  clines_data,
            "polylines":           polylines_data,
            "draw_lines":          draw_lines_data,
            "draw_rectangles":     draw_rects_data,
            "draw_circles":        draw_circles_data,
            "draw_arcs":           draw_arcs_data,
            "gridlines":           gridlines_data,
            "walls":               walls_data,
            "floor_slabs":         floor_slabs_data,
            "roofs":               roofs_data,
            "rooms":               rooms_data,
            "hatches":             hatch_data,
            "constraints":         constraints_data,
            "detail_views":        (self._detail_manager.to_list()
                                    if getattr(self, "_detail_manager", None) else []),
        }
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
        from node import Node
        from pipe import Pipe
        from sprinkler import Sprinkler
        from Annotations import DimensionAnnotation, NoteAnnotation, HatchItem
        from underlay import Underlay
        from scale_manager import ScaleManager
        from water_supply import WaterSupply
        from design_area import DesignArea
        from construction_geometry import (
            ConstructionLine, PolylineItem, LineItem, RectangleItem,
            CircleItem, ArcItem,
        )
        from gridline import GridlineItem
        from wall import WallSegment
        from floor_slab import FloorSlab
        from roof import RoofItem
        from room import Room
        from wall_opening import WallOpening
        from constraints import Constraint as ConstraintBase
        from PyQt6.QtGui import QColor

        try:
            with open(filename, "r") as f:
                payload = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            self._show_status(f"Failed to open: {e}")
            return

        version = payload.get("version", 1)
        self._clear_scene()

        # --- Display settings ---
        self._loaded_display_settings = payload.get("display_settings", None)

        # --- Scale ---
        if "scale" in payload:
            self._project_info = payload.get("project_info", {})
            self.scale_manager = ScaleManager.from_dict(payload["scale"])
        else:
            self.scale_manager = ScaleManager()

        # --- User layers ---
        layers_data = payload.get("user_layers", [])
        if layers_data and hasattr(self, "_user_layer_manager") and self._user_layer_manager:
            self._user_layer_manager.from_list(layers_data)

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

        # --- Nodes ---
        # Create each node unconditionally — bypass find_nearby_node so that
        # vertical pipes (same XY, different Z) keep distinct node objects.
        id_to_node: dict[int, Node] = {}
        for entry in payload.get("nodes", []):
            node = Node(entry["x"], entry["y"])
            node.user_layer = self.active_user_layer
            node.level = self.active_level
            self.addItem(node)
            self.sprinkler_system.add_node(node)
            id_to_node[entry["id"]] = node
            node.z_offset = entry.get("z_offset", entry.get("elevation", 0))
            node.user_layer = entry.get("user_layer", "0")
            node.level = entry.get("level", DEFAULT_LEVEL)
            node._room_name = entry.get("room_name", "")
            node.ceiling_level = entry.get("ceiling_level", node.level)
            if "ceiling_offset_mm" in entry:
                node.ceiling_offset = entry["ceiling_offset_mm"]
            else:
                node.ceiling_offset = entry.get("ceiling_offset", -2.0) * 25.4
            node._properties["Ceiling Level"]["value"] = node.ceiling_level
            node._properties["Ceiling Offset"]["value"] = str(node.ceiling_offset)
            if self._level_manager:
                lvl = self._level_manager.get(node.ceiling_level)
                if lvl:
                    node.z_pos = lvl.elevation + node.ceiling_offset
                else:
                    node.z_pos = entry.get("elevation", 0)
            else:
                node.z_pos = entry.get("elevation", 0)
            node._display_overrides = entry.get("display_overrides", {})
            if entry.get("sprinkler"):
                _saved_cl = node.ceiling_level
                _saved_co = node.ceiling_offset
                _saved_zp = node.z_pos
                template = Sprinkler(None)
                for key, value in entry["sprinkler"].items():
                    if isinstance(value, dict):
                        template.set_property(key, value["value"])
                    else:
                        template.set_property(key, value)
                self.add_sprinkler(node, template)
                node.ceiling_level = _saved_cl
                node.ceiling_offset = _saved_co
                node.z_pos = _saved_zp
                node._properties["Ceiling Level"]["value"] = _saved_cl
                node._properties["Ceiling Offset"]["value"] = str(_saved_co)
                node.sprinkler._display_overrides = entry.get(
                    "sprinkler_display_overrides", {})
            node._fitting_display_overrides_pending = entry.get(
                "fitting_display_overrides", {})

        # --- Pipes ---
        for entry in payload.get("pipes", []):
            n1 = id_to_node.get(entry["node1_id"])
            n2 = id_to_node.get(entry["node2_id"])
            if n1 and n2:
                pipe = self.add_pipe(n1, n2, _propagate_ceiling=False)
                pipe.user_layer = entry.get("user_layer", "0")
                pipe.level = entry.get("level", DEFAULT_LEVEL)
                pipe.ceiling_level = entry.get("ceiling_level",
                    entry.get("properties", {}).get("Ceiling Level", DEFAULT_LEVEL))
                pipe._properties["Ceiling Level"]["value"] = pipe.ceiling_level
                if "ceiling_offset_mm" in entry:
                    pipe.ceiling_offset = entry["ceiling_offset_mm"]
                    pipe._properties["Ceiling Offset"]["value"] = str(pipe.ceiling_offset)
                for key, value in entry.get("properties", {}).items():
                    if key in ("Ceiling Level", "Ceiling Offset"):
                        continue
                    pipe.set_property(key, value)
                props = entry.get("properties", {})
                if "Line Type" not in props:
                    dia = props.get("Diameter", "1\"Ø")
                    pipe._properties["Line Type"]["value"] = (
                        "Main" if dia in Pipe._MAIN_DIAMETERS else "Branch"
                    )
                    pipe.set_pipe_display()
                pipe._display_overrides = entry.get("display_overrides", {})

        # --- Fittings ---
        for node in id_to_node.values():
            node.fitting.update()
            pending = getattr(node, "_fitting_display_overrides_pending", {})
            if pending:
                node.fitting._display_overrides = pending
                del node._fitting_display_overrides_pending

        # --- Annotations ---
        for entry in payload.get("annotations", []):
            ann_type = entry.get("type")
            if ann_type == "dimension":
                p1 = QPointF(entry["p1"][0], entry["p1"][1])
                p2 = QPointF(entry["p2"][0], entry["p2"][1])
                dim = DimensionAnnotation(p1, p2)
                dim._offset_dist = entry.get("offset_dist",
                    float(entry.get("properties", {}).get("Offset", "10")))
                dim._witness_ext_override = entry.get("witness_ext_override", None)
                self.addItem(dim)
                self.annotations.add_dimension(dim)
                for key, value in entry.get("properties", {}).items():
                    dim.set_property(key, value)
                dim.update_geometry()
                dim.user_layer = entry.get("user_layer", DEFAULT_USER_LAYER)
                dim.level = entry.get("level", DEFAULT_LEVEL)
            elif ann_type == "note":
                tw = entry.get("text_width", -1)
                note = NoteAnnotation(
                    x=entry["x"], y=entry["y"],
                    text_width=tw if tw and tw > 0 else 0)
                self.addItem(note)
                self.annotations.add_note(note)
                for key, value in entry.get("properties", {}).items():
                    note.set_property(key, value)
                note.user_layer = entry.get("user_layer", DEFAULT_USER_LAYER)
                note.level = entry.get("level", DEFAULT_LEVEL)

        # --- Underlays ---
        for entry in payload.get("underlays", []):
            udata = Underlay.from_dict(entry)
            if udata.type == "pdf":
                self.import_pdf(udata.path, dpi=udata.dpi, page=udata.page,
                                x=udata.x, y=udata.y, _record=udata)
            elif udata.type == "dxf":
                self.import_dxf(udata.path, color=QColor(udata.colour),
                                line_weight=udata.line_weight,
                                x=udata.x, y=udata.y, _record=udata)

        # --- Water supply ---
        ws_data = payload.get("water_supply")
        if ws_data:
            ws = WaterSupply(ws_data["x"], ws_data["y"])
            self.addItem(ws)
            self.water_supply_node = ws
            self.sprinkler_system.supply_node = ws
            for key, value in ws_data.get("properties", {}).items():
                ws.set_property(key, value)
            ws._display_overrides = ws_data.get("display_overrides", {})

        # --- Design areas ---
        for da_entry in payload.get("design_areas", []):
            spr_node_ids = da_entry.get("sprinkler_node_ids", [])
            sprs = []
            for nid in spr_node_ids:
                node = id_to_node.get(nid)
                if node and node.has_sprinkler():
                    sprs.append(node.sprinkler)
            da = DesignArea(sprs)
            for key, value in da_entry.get("properties", {}).items():
                da.set_property(key, value)
            self.addItem(da)
            self.design_areas.append(da)
            if da_entry.get("is_active", False):
                self.active_design_area = da
            da.compute_area(self.scale_manager)

        # --- Construction geometry ---
        for entry in payload.get("construction_lines", []):
            cl = ConstructionLine.from_dict(entry)
            self.addItem(cl)
            self._construction_lines.append(cl)
        for entry in payload.get("polylines", []):
            pl = PolylineItem.from_dict(entry)
            self.addItem(pl)
            self._polylines.append(pl)
        for entry in payload.get("draw_lines", []):
            item = LineItem.from_dict(entry)
            self.addItem(item)
            self._draw_lines.append(item)
        for entry in payload.get("draw_rectangles", []):
            item = RectangleItem.from_dict(entry)
            self.addItem(item)
            self._draw_rects.append(item)
        for entry in payload.get("draw_circles", []):
            item = CircleItem.from_dict(entry)
            self.addItem(item)
            self._draw_circles.append(item)
        for entry in payload.get("draw_arcs", []):
            item = ArcItem.from_dict(entry)
            self.addItem(item)
            self._draw_arcs.append(item)

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

        # --- Recalculate auto-name counters ---
        self._recalc_name_counters()

        # --- Hatches ---
        for entry in payload.get("hatches", []):
            try:
                h = HatchItem.from_dict(entry)
                self.addItem(h)
                self._hatch_items.append(h)
            except (ValueError, KeyError, TypeError):
                pass

        # --- Constraints ---
        all_geom = self._all_geometry_items()
        id_to_geom = {i: item for i, item in enumerate(all_geom)}
        for entry in payload.get("constraints", []):
            try:
                c = ConstraintBase.from_dict(entry, id_to_geom)
                if c is not None:
                    self._constraints.append(c)
            except (ValueError, KeyError, TypeError):
                pass

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
        from sprinkler_system import SprinklerSystem
        from Annotations import Annotation
        from scale_manager import ScaleManager
        from gridline import reset_grid_counters

        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self.underlays = []
        self.scale_manager = ScaleManager()
        self.water_supply_node = None
        self.hydraulic_result = None
        for da in self.design_areas:
            if da.scene() is self:
                self.removeItem(da)
        self.design_areas = []
        self.active_design_area = None
        self._construction_lines = []
        self._polylines = []
        self._cline_anchor = None
        self._polyline_active = None
        self._draw_lines = []
        self._draw_rects = []
        self._draw_circles = []
        self._draw_arcs = []
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
        self._gridline_anchor = None
        self._walls = []
        self._floor_slabs = []
        self._roofs = []
        self._rooms = []
        self._wall_anchor = None
        self._wall_chain_start = None
        self._floor_active = None
        self._roof_active = None
        self._hatch_items = []
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
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()
        self._undo_stack = []
        self._undo_pos = -1
        self.push_undo_state()
