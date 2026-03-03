import sys, json, math
from PyQt6.QtWidgets import (QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
                              QGraphicsItem, QGraphicsItemGroup, QGraphicsPixmapItem,
                              QGraphicsTextItem, QGraphicsPathItem, QGraphicsRectItem,
                              QApplication, QProgressDialog)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPen, QBrush, QColor, QPixmap, QPainterPath
from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from node import Node
from pipe import Pipe
from sprinkler import Sprinkler
from sprinkler_system import SprinklerSystem
from CAD_Math import CAD_Math
from Annotations import Annotation, DimensionAnnotation, NoteAnnotation
from underlay import Underlay
from scale_manager import ScaleManager
from calibrate_dialog import CalibrateDialog
from underlay_context_menu import UnderlayContextMenu
from dxf_import_worker import DxfImportWorker
from water_supply import WaterSupply
from construction_geometry import (
    ConstructionLine, PolylineItem, LineItem, RectangleItem, CircleItem,
)
from snap_engine import SnapEngine, OsnapResult
import os


class Model_Space(QGraphicsScene):
    SNAP_RADIUS = 10
    SAVE_VERSION = 5
    UNDO_MAX = 50
    requestPropertyUpdate = pyqtSignal(object)
    cursorMoved = pyqtSignal(str)      # emits formatted "X: …  Y: …" string
    underlaysChanged = pyqtSignal()    # emitted when underlays list changes (for LayerManager)

    def __init__(self):
        super().__init__()
        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self.underlays: list[tuple[Underlay, QGraphicsItem]] = []  # (data, scene_item)
        self.scale_manager = ScaleManager()
        self.mode = None
        self.dimension_start = None
        self._cal_point1 = None          # first point for "set_scale" mode
        self.node_start_pos = None
        self.node_end_pos = None
        self._selected_items = None
        self._snap_to_underlay: bool = False
        self.water_supply_node: "WaterSupply | None" = None  # placed water supply
        self.hydraulic_result = None                          # last solver run (Sprint 2)
        self.design_area_sprinklers: list = []                # Sprint 2C design area
        self.active_user_layer: str = "0"                     # Sprint 4A active layer
        self._design_area_corner1: "QPointF | None" = None
        self._design_area_rect_item = None                    # QGraphicsRectItem preview
        # Construction geometry (Sprint C)
        self._construction_lines: list[ConstructionLine] = []
        self._polylines: list[PolylineItem] = []
        self._cline_anchor: "QPointF | None" = None           # first click for construction line
        self._polyline_active: "PolylineItem | None" = None   # in-progress polyline
        # Draw geometry (Sprint G)
        self._draw_lines: list[LineItem] = []
        self._draw_rects: list[RectangleItem] = []
        self._draw_circles: list[CircleItem] = []
        self._draw_dim_hint: "str | None" = None              # live dim overlay for Model_View
        self._draw_line_anchor: "QPointF | None" = None       # first click for line
        self._draw_rect_anchor: "QPointF | None" = None       # first click for rectangle
        self._draw_circle_center: "QPointF | None" = None     # first click for circle
        self._draw_rect_preview: "QGraphicsRectItem | None" = None
        self._draw_circle_preview: "QGraphicsEllipseItem | None" = None
        self._draw_color: str = "#ffffff"       # default white (dark theme)
        self._draw_lineweight: float = 1.0      # cosmetic px
        # OSNAP (Sprint H)
        self._snap_engine: SnapEngine = SnapEngine()
        self._snap_result: "OsnapResult | None" = None
        self._osnap_enabled: bool = True
        # Grip editing (Sprint I)
        self._grip_item = None                  # item currently being grip-dragged
        self._grip_index: int = -1              # grip handle index
        self._grip_dragging: bool = False
        # Offset command (Sprint L)
        self._offset_source = None              # entity selected for offset
        self._offset_dist: float = 0.0          # distance entered by user
        self._offset_preview = None             # preview item shown during side-pick
        # Place-import mode (Sprint L)
        self._place_import_params = None
        self._place_import_ghost = None
        self._place_import_bounds = QRectF(-50, -50, 100, 100)
        # Undo/redo
        self._undo_stack: list[dict] = []
        self._undo_pos: int = -1
        self._in_undo_restore: bool = False
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()
        self.push_undo_state()   # initial empty state

    # -------------------------------------------------------------------------
    # Preview items

    def init_preview_pipe(self):
        self.preview_pipe = QGraphicsLineItem()
        pen = QPen(Qt.GlobalColor.darkGray, 2, Qt.PenStyle.DashLine)
        self.preview_pipe.setPen(pen)
        self.preview_pipe.setZValue(200)
        self.addItem(self.preview_pipe)
        self.preview_pipe.hide()

    def init_preview_node(self):
        self.preview_node = QGraphicsEllipseItem(0, 0, 10, 10)
        self.preview_node.setBrush(QBrush(QColor(0, 0, 255, 100)))
        self.preview_node.setPen(QPen(Qt.GlobalColor.blue))
        self.preview_node.setZValue(200)
        self.addItem(self.preview_node)
        bounds = self.preview_node.boundingRect()
        self.preview_node.setTransformOriginPoint(bounds.center())
        self.preview_node.hide()

    # -------------------------------------------------------------------------
    # SAVE / LOAD

    def save_to_file(self, filename: str):
        """Serialise the full scene to JSON."""

        # --- Nodes (assign temp IDs) ---
        node_list = list(self.sprinkler_system.nodes)
        node_id = {n: i for i, n in enumerate(node_list)}

        nodes_data = []
        for node in node_list:
            entry = {
                "id":         node_id[node],
                "x":          node.scenePos().x(),
                "y":          node.scenePos().y(),
                "elevation":  node.z_pos,
                "user_layer": getattr(node, "user_layer", "0"),
                "sprinkler":  node.sprinkler.get_properties() if node.has_sprinkler() else None,
            }
            nodes_data.append(entry)

        # --- Pipes ---
        pipes_data = []
        for pipe in self.sprinkler_system.pipes:
            if pipe.node1 is None or pipe.node2 is None:
                continue
            pipes_data.append({
                "node1_id":   node_id[pipe.node1],
                "node2_id":   node_id[pipe.node2],
                "user_layer": getattr(pipe, "user_layer", "0"),
                "properties": {k: v["value"] for k, v in pipe.get_properties().items()},
            })

        # --- Annotations ---
        annotations_data = []
        for dim in self.annotations.dimensions:
            annotations_data.append({
                "type": "dimension",
                "p1":   [dim.handle1.scenePos().x(), dim.handle1.scenePos().y()],
                "p2":   [dim.handle2.scenePos().x(), dim.handle2.scenePos().y()],
                "properties": {k: v["value"] for k, v in dim.get_properties().items()},
            })
        for note in self.annotations.notes:
            annotations_data.append({
                "type": "note",
                "x":    note.scenePos().x(),
                "y":    note.scenePos().y(),
                "properties": {k: v["value"] for k, v in note.get_properties().items()},
            })

        # --- Underlays (sync positions from scene before saving) ---
        underlays_data = []
        for data, item in self.underlays:
            if item is not None:
                data.x = item.scenePos().x()
                data.y = item.scenePos().y()
                # rotation and opacity are already kept in sync via context menu
            underlays_data.append(data.to_dict())

        # --- Water supply ---
        ws = self.water_supply_node
        ws_data = None
        if ws is not None:
            ws_data = {
                "x":          ws.scenePos().x(),
                "y":          ws.scenePos().y(),
                "properties": {k: v["value"] for k, v in ws.get_properties().items()},
            }

        # --- User layers ---
        layers_data = (
            self._user_layer_manager.to_list()
            if hasattr(self, "_user_layer_manager") and self._user_layer_manager
            else []
        )

        # --- Construction geometry ---
        clines_data = [cl.to_dict() for cl in self._construction_lines]
        polylines_data = [pl.to_dict() for pl in self._polylines]
        draw_lines_data = [l.to_dict() for l in self._draw_lines]
        draw_rects_data = [r.to_dict() for r in self._draw_rects]
        draw_circles_data = [c.to_dict() for c in self._draw_circles]

        # --- Assemble and write ---
        payload = {
            "version":             self.SAVE_VERSION,
            "scale":               self.scale_manager.to_dict(),
            "user_layers":         layers_data,
            "nodes":               nodes_data,
            "pipes":               pipes_data,
            "annotations":         annotations_data,
            "underlays":           underlays_data,
            "water_supply":        ws_data,
            "construction_lines":  clines_data,
            "polylines":           polylines_data,
            "draw_lines":          draw_lines_data,
            "draw_rectangles":     draw_rects_data,
            "draw_circles":        draw_circles_data,
        }
        try:
            with open(filename, "w") as f:
                json.dump(payload, f, indent=2)
            print(f"✅ Saved to {filename}")
        except Exception as e:
            print(f"❌ Error saving: {e}")

    def load_from_file(self, filename: str):
        """Clear the scene and restore from JSON."""
        with open(filename, "r") as f:
            payload = json.load(f)

        version = payload.get("version", 1)
        self._clear_scene()

        # --- Scale ---
        if "scale" in payload:
            self.scale_manager = ScaleManager.from_dict(payload["scale"])
        else:
            self.scale_manager = ScaleManager()

        # --- User layers ---
        layers_data = payload.get("user_layers", [])
        if layers_data and hasattr(self, "_user_layer_manager") and self._user_layer_manager:
            self._user_layer_manager.from_list(layers_data)

        # --- Nodes ---
        id_to_node: dict[int, Node] = {}
        for entry in payload.get("nodes", []):
            node = self.add_node(entry["x"], entry["y"])
            id_to_node[entry["id"]] = node
            # Restore node elevation (plain nodes)
            node.set_property("Elevation", str(entry.get("elevation", 0)))
            node.user_layer = entry.get("user_layer", "0")
            if entry.get("sprinkler"):
                template = Sprinkler(None)
                for key, value in entry["sprinkler"].items():
                    if isinstance(value, dict):
                        template.set_property(key, value["value"])
                    else:
                        template.set_property(key, value)
                self.add_sprinkler(node, template)
                # Sprinkler's set_property("Elevation", ...) also syncs node.z_pos

        # --- Pipes ---
        for entry in payload.get("pipes", []):
            n1 = id_to_node.get(entry["node1_id"])
            n2 = id_to_node.get(entry["node2_id"])
            if n1 and n2:
                pipe = self.add_pipe(n1, n2)
                pipe.user_layer = entry.get("user_layer", "0")
                for key, value in entry.get("properties", {}).items():
                    pipe.set_property(key, value)

        # --- Fittings (update after all pipes are connected) ---
        for node in id_to_node.values():
            node.fitting.update()

        # --- Annotations ---
        for entry in payload.get("annotations", []):
            ann_type = entry.get("type")
            if ann_type == "dimension":
                p1 = QPointF(entry["p1"][0], entry["p1"][1])
                p2 = QPointF(entry["p2"][0], entry["p2"][1])
                dim = DimensionAnnotation(p1, p2)
                self.addItem(dim)
                self.annotations.add_dimension(dim)
                for key, value in entry.get("properties", {}).items():
                    dim.set_property(key, value)
            elif ann_type == "note":
                note = NoteAnnotation(x=entry["x"], y=entry["y"])
                self.addItem(note)
                self.annotations.add_note(note)
                for key, value in entry.get("properties", {}).items():
                    note.set_property(key, value)

        # --- Underlays (re-link from path) ---
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

        # --- Construction lines ---
        for entry in payload.get("construction_lines", []):
            cl = ConstructionLine.from_dict(entry)
            self.addItem(cl)
            self._construction_lines.append(cl)

        # --- Polylines ---
        for entry in payload.get("polylines", []):
            pl = PolylineItem.from_dict(entry)
            self.addItem(pl)
            self._polylines.append(pl)

        # --- Draw lines ---
        for entry in payload.get("draw_lines", []):
            item = LineItem.from_dict(entry)
            self.addItem(item)
            self._draw_lines.append(item)

        # --- Draw rectangles ---
        for entry in payload.get("draw_rectangles", []):
            item = RectangleItem.from_dict(entry)
            self.addItem(item)
            self._draw_rects.append(item)

        # --- Draw circles ---
        for entry in payload.get("draw_circles", []):
            item = CircleItem.from_dict(entry)
            self.addItem(item)
            self._draw_circles.append(item)

        # Start fresh undo history with the loaded state
        self._undo_stack = []
        self._undo_pos = -1
        self.push_undo_state()
        print(f"✅ Loaded from {filename}")

    def _clear_scene(self):
        """Remove all user content, keeping preview items and origin markers."""
        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self.underlays = []
        self.scale_manager = ScaleManager()
        self.water_supply_node = None
        self.hydraulic_result = None
        self._construction_lines = []
        self._polylines = []
        self._cline_anchor = None
        self._polyline_active = None
        self._draw_lines = []
        self._draw_rects = []
        self._draw_circles = []
        self._draw_line_anchor = None
        self._draw_rect_anchor = None
        self._draw_circle_center = None
        self._draw_rect_preview = None
        self._draw_circle_preview = None
        self.clear()
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()
        # Reset undo history
        self._undo_stack = []
        self._undo_pos = -1
        self.push_undo_state()

    # -------------------------------------------------------------------------
    # SCENE MANAGEMENT

    def draw_origin(self):
        pen = QPen(Qt.GlobalColor.black)
        pen.setWidth(1)
        size = 10
        h_line = QGraphicsLineItem(-size, 0, size, 0)
        v_line = QGraphicsLineItem(0, -size, 0, size)
        h_line.setPen(pen)
        v_line.setPen(pen)
        self.addItem(h_line)
        self.addItem(v_line)

        axis_pen = QPen(Qt.GlobalColor.gray)
        axis_pen.setWidth(0)
        axis_pen.setStyle(Qt.PenStyle.DashLine)
        x_axis = QGraphicsLineItem(-1000, 0, 1000, 0)
        y_axis = QGraphicsLineItem(0, -1000, 0, 1000)
        x_axis.setPen(axis_pen)
        y_axis.setPen(axis_pen)
        self.addItem(x_axis)
        self.addItem(y_axis)

    # -------------------------------------------------------------------------
    # DELETE

    def delete_selected_items(self):
        if not self.selectedItems():
            return
        selected = list(self.selectedItems())
        for item in selected:
            if isinstance(item, DimensionAnnotation):
                if item in self.annotations.dimensions:
                    self.annotations.dimensions.remove(item)
                self.removeItem(item)
            elif isinstance(item, NoteAnnotation):
                if item in self.annotations.notes:
                    self.annotations.notes.remove(item)
                self.removeItem(item)
            elif isinstance(item, WaterSupply):
                self.removeItem(item)
                if self.water_supply_node is item:
                    self.water_supply_node = None
                    self.sprinkler_system.supply_node = None
            elif isinstance(item, ConstructionLine):
                if item in self._construction_lines:
                    self._construction_lines.remove(item)
                self.removeItem(item)
            elif isinstance(item, PolylineItem):
                if item in self._polylines:
                    self._polylines.remove(item)
                self.removeItem(item)
            elif isinstance(item, LineItem):
                if item in self._draw_lines:
                    self._draw_lines.remove(item)
                self.removeItem(item)
            elif isinstance(item, RectangleItem):
                if item in self._draw_rects:
                    self._draw_rects.remove(item)
                self.removeItem(item)
            elif isinstance(item, CircleItem):
                if item in self._draw_circles:
                    self._draw_circles.remove(item)
                self.removeItem(item)
        for item in self.selectedItems():
            if isinstance(item, Pipe):
                self.delete_pipe(item)
        for item in self.selectedItems():
            if isinstance(item, Node):
                if item.has_sprinkler():
                    self.remove_sprinkler(item)
                for pipe in list(item.pipes):
                    self.delete_pipe(pipe)
        for item in self.selectedItems():
            if isinstance(item, Node):
                self.remove_node(item)
        self.push_undo_state()

    # -------------------------------------------------------------------------
    # MODE MANAGEMENT

    def set_mode(self, mode, template=None):
        self.mode = mode
        print(f"Mode set to: {self.mode}")
        self.preview_node.hide()
        self.preview_pipe.hide()
        self._cal_point1 = None
        # Clean up design_area preview if leaving that mode mid-draw
        if mode != "design_area":
            self._design_area_corner1 = None
            if self._design_area_rect_item is not None:
                if self._design_area_rect_item.scene() is self:
                    self.removeItem(self._design_area_rect_item)
                self._design_area_rect_item = None
        # Only remove node if we are truly holding an orphan Node (pipe mode).
        # In paste/move mode node_start_pos is a QPointF — never call remove_node on it.
        if self.node_start_pos is not None:
            if isinstance(self.node_start_pos, Node):
                self.remove_node(self.node_start_pos)
            else:
                self.node_start_pos = None
        # Cancel in-progress construction geometry
        self._cline_anchor = None
        if mode != "polyline" and self._polyline_active is not None:
            # Discard the partial polyline (fewer than 2 committed points)
            if len(self._polyline_active._points) < 2:
                if self._polyline_active.scene() is self:
                    self.removeItem(self._polyline_active)
                if self._polyline_active in self._polylines:
                    self._polylines.remove(self._polyline_active)
            self._polyline_active = None
        # Cancel in-progress draw geometry
        if mode != "draw_line":
            self._draw_line_anchor = None
        if mode != "draw_rectangle":
            self._draw_rect_anchor = None
            if self._draw_rect_preview is not None:
                if self._draw_rect_preview.scene() is self:
                    self.removeItem(self._draw_rect_preview)
                self._draw_rect_preview = None
        if mode != "draw_circle":
            self._draw_circle_center = None
            if self._draw_circle_preview is not None:
                if self._draw_circle_preview.scene() is self:
                    self.removeItem(self._draw_circle_preview)
                self._draw_circle_preview = None
        if mode in ("sprinkler", "pipe", "set_scale"):
            self.current_template = template
            if template:
                self.requestPropertyUpdate.emit(template)
        else:
            self.current_template = None

        # Clean up offset preview whenever leaving offset modes
        if mode not in ("offset", "offset_side"):
            self._clear_offset_preview()
            self._offset_source = None

        # Clean up place_import ghost
        if mode != "place_import":
            if self._place_import_ghost is not None:
                if self._place_import_ghost.scene() is self:
                    self.removeItem(self._place_import_ghost)
                self._place_import_ghost = None

        # Capture current selection when entering move mode from ribbon/keyboard
        if mode == "move" and not self._selected_items:
            self._selected_items = list(self.selectedItems())

        # Clear OSNAP snap trace whenever mode changes
        self._snap_result = None
        for v in self.views():
            v.viewport().update()

    # -------------------------------------------------------------------------
    # NODE / PIPE / SPRINKLER MANAGEMENT

    def find_nearby_node(self, x, y):
        for node in self.sprinkler_system.nodes:
            if node.distance_to(x, y) <= self.SNAP_RADIUS:
                return node
        return None

    def find_or_create_node(self, x, y):
        existing = self.find_nearby_node(x, y)
        if existing:
            return existing
        return self.add_node(x, y)

    def add_node(self, x, y):
        node = self.find_nearby_node(x, y)
        if not node:
            node = Node(x, y)
            node.user_layer = self.active_user_layer
            self.addItem(node)
            self.sprinkler_system.add_node(node)
        return node

    def remove_node(self, n):
        try:
            self.sprinkler_system.remove_node(n)
        except ValueError:
            pass
        if n.scene() is self:
            self.removeItem(n)
        n = None
        self.node_start_pos = None

    def add_pipe(self, n1, n2, template=None):
        pipe = Pipe(n1, n2)
        pipe.user_layer = self.active_user_layer
        if template:
            pipe.set_properties(template)
        self.sprinkler_system.add_pipe(pipe)
        self.addItem(pipe)
        pipe.update_label()   # re-run now that pipe.scene() is valid
        return pipe

    def split_pipe(self, pipe, split_point: QPointF):
        new_node = self.add_node(split_point.x(), split_point.y())
        template = pipe
        node_a = pipe.node1
        node_b = pipe.node2
        self.add_pipe(node_a, new_node, template)
        self.add_pipe(new_node, node_b, template)
        self.delete_pipe(pipe)
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
        try:
            self.removeItem(pipe)
        except Exception:
            pass
        if pipe in self.sprinkler_system.pipes:
            self.sprinkler_system.remove_pipe(pipe)

    def add_sprinkler(self, n, template=None):
        if n.has_sprinkler():
            return
        n.add_sprinkler()
        sprinkler = n.sprinkler
        self.sprinkler_system.add_sprinkler(sprinkler)
        if template:
            sprinkler.set_properties(template)
        if n.has_fitting():
            n.fitting.update()
        return sprinkler

    def remove_sprinkler(self, n):
        sprinkler = n.sprinkler
        self.removeItem(sprinkler)
        self.sprinkler_system.remove_sprinkler(sprinkler)
        n.delete_sprinkler()

    # -------------------------------------------------------------------------
    # UNDERLAYS — IMPORT

    # ─────────────────────────────────────────────────────────────────────────
    # PREVIEW-FIRST IMPORT (place_import mode)
    # ─────────────────────────────────────────────────────────────────────────

    def begin_place_import(self, params):
        """
        Start the interactive placement of a DXF block after the preview dialog.

        The scene enters 'place_import' mode.  A ghost bounding-box preview
        follows the cursor.  Clicking commits the placement.

        Parameters
        ----------
        params : ImportParams
            Result from DxfPreviewDialog.get_import_params()
        """
        self._place_import_params = params
        self._place_import_ghost = None

        # Build a bounding rect for the (scaled, base-point-adjusted) geometry
        if params.geom_list:
            xs, ys = [], []
            s = params.scale
            bx, by = params.base_x, params.base_y
            for g in params.geom_list:
                kind = g.get("kind")
                if kind == "line":
                    xs += [(g["x1"] - bx) * s, (g["x2"] - bx) * s]
                    ys += [(g["y1"] - by) * s, (g["y2"] - by) * s]
                elif kind in ("circle", "arc"):
                    x0 = (g.get("x", g.get("rx", 0)) - bx) * s
                    y0 = (g.get("y", g.get("ry", 0)) - by) * s
                    xs += [x0, x0 + g.get("w", g.get("rw", 0)) * s]
                    ys += [y0, y0 + g.get("h", g.get("rh", 0)) * s]
                elif kind == "path_points":
                    for pt in g.get("points", []):
                        xs.append((pt[0] - bx) * s)
                        ys.append((pt[1] - by) * s)
            if xs and ys:
                self._place_import_bounds = QRectF(
                    min(xs), min(ys),
                    max(xs) - min(xs), max(ys) - min(ys)
                )
            else:
                self._place_import_bounds = QRectF(-50, -50, 100, 100)
        else:
            self._place_import_bounds = QRectF(-50, -50, 100, 100)

        self.set_mode("place_import")

    def _update_place_import_ghost(self, pos: QPointF):
        """Reposition the ghost bounding rect at cursor position."""
        if self._place_import_ghost is not None:
            if self._place_import_ghost.scene() is self:
                self.removeItem(self._place_import_ghost)
            self._place_import_ghost = None

        r = self._place_import_bounds
        ghost = QGraphicsRectItem(
            pos.x() + r.x(), pos.y() + r.y(), r.width(), r.height()
        )
        pen = QPen(QColor("#4fa3e0"), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        ghost.setPen(pen)
        ghost.setBrush(QBrush(QColor(79, 163, 224, 20)))
        ghost.setZValue(200)
        self.addItem(ghost)
        self._place_import_ghost = ghost

    def _commit_place_import(self, insert_pt: QPointF):
        """Finalize placement: create the underlay group at insert_pt."""
        if self._place_import_ghost is not None:
            if self._place_import_ghost.scene() is self:
                self.removeItem(self._place_import_ghost)
            self._place_import_ghost = None

        params = self._place_import_params
        if not params or not params.geom_list:
            self.set_mode(None)
            return

        s = params.scale
        bx, by = params.base_x, params.base_y

        # Transform geometry: shift by base point and apply scale
        transformed = []
        for g in params.geom_list:
            kind = g.get("kind")
            t = dict(g)
            if kind == "line":
                t["x1"] = (g["x1"] - bx) * s
                t["y1"] = (g["y1"] - by) * s
                t["x2"] = (g["x2"] - bx) * s
                t["y2"] = (g["y2"] - by) * s
            elif kind in ("circle", "arc"):
                xk = "x" if kind == "circle" else "rx"
                yk = "y" if kind == "circle" else "ry"
                wk = "w" if kind == "circle" else "rw"
                hk = "h" if kind == "circle" else "rh"
                t[xk] = (g[xk] - bx) * s
                t[yk] = (g[yk] - by) * s
                t[wk] = g[wk] * s
                t[hk] = g[hk] * s
            elif kind == "ellipse_full":
                t["pos_cx"] = (g["pos_cx"] - bx) * s
                t["pos_cy"] = (g["pos_cy"] - by) * s
                t["x"] = g["x"] * s; t["y"] = g["y"] * s
                t["w"] = g["w"] * s; t["h"] = g["h"] * s
            elif kind == "path_points":
                t["points"] = [((p[0] - bx) * s, (p[1] - by) * s)
                               for p in g["points"]]
            elif kind == "text":
                t["x"] = (g["x"] - bx) * s
                t["y"] = (g["y"] - by) * s
            transformed.append(t)

        # Build scene items and group them
        color = params.color
        pen = QPen(color, params.line_weight)

        items = []
        for geom in transformed:
            item = self._geom_to_item(geom, pen, color)
            if item is not None:
                items.append(item)

        if not items:
            self.set_mode(None)
            return

        old_method = self.itemIndexMethod()
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        for item in items:
            self.addItem(item)
        group = self.createItemGroup(items)
        group.setZValue(-100)
        group.setPos(insert_pt)
        group.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        group.setData(0, "DXF Underlay")
        all_layers = sorted({g.get("layer", "0") for g in transformed})
        group.setData(2, all_layers)
        self.setItemIndexMethod(old_method)

        record = Underlay(
            type="dxf", path=params.file_path,
            x=insert_pt.x(), y=insert_pt.y(),
            colour=color.name(),
            line_weight=params.line_weight,
        )
        self._apply_underlay_display(group, record)
        self.underlays.append((record, group))
        self.underlaysChanged.emit()
        self.push_undo_state()
        self.set_mode(None)

    def import_dxf(self, file_path, color=QColor("white"), line_weight=0,
                   x=0.0, y=0.0, layers=None, _record: Underlay = None):
        """
        Import a DXF file as an underlay using a background thread.

        Supported entities: LINE, CIRCLE, ARC, ELLIPSE, LWPOLYLINE, POLYLINE,
        SPLINE, TEXT, MTEXT.

        Parameters
        ----------
        layers : list[str] | None
            If given, only import entities on these layers. None = all layers.
        """
        parent_widget = self.views()[0] if self.views() else None

        # Create progress dialog
        progress = QProgressDialog("Importing DXF…", "Cancel", 0, 100, parent_widget)
        progress.setWindowTitle("DXF Import")
        progress.setMinimumDuration(0)   # show immediately
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)

        # Create and configure worker (no Qt objects passed — created on main thread later)
        worker = DxfImportWorker(file_path, layers)

        # Store references so they don't get garbage-collected
        self._dxf_worker = worker
        self._dxf_progress = progress
        self._dxf_import_params = {
            "file_path": file_path, "color": color, "line_weight": line_weight,
            "x": x, "y": y, "layers": layers, "_record": _record,
        }

        # Wire signals
        worker.progress.connect(lambda cur, tot: self._on_dxf_progress(progress, cur, tot))
        worker.status.connect(lambda msg: progress.setLabelText(msg))
        worker.finished_data.connect(lambda geom_list: self._on_dxf_finished(geom_list, progress))
        worker.error.connect(lambda msg: self._on_dxf_error(msg, progress))
        progress.canceled.connect(worker.cancel)

        worker.start()

    def _on_dxf_progress(self, progress: QProgressDialog, current: int, total: int):
        if total > 0:
            progress.setMaximum(total)
            progress.setValue(current)

    def _on_dxf_finished(self, geom_list: list, progress: QProgressDialog):
        """Receives raw geometry dicts from the worker and creates QGraphicsItems
        on the main thread (required by Qt)."""
        params = self._dxf_import_params
        progress.setLabelText(f"Building {len(geom_list)} items…")
        QApplication.processEvents()

        if not geom_list:
            progress.close()
            self._cleanup_dxf_worker()
            return

        color = params["color"]
        pen = QPen(color, params["line_weight"])

        items = []
        for geom in geom_list:
            item = self._geom_to_item(geom, pen, color)
            if item is not None:
                items.append(item)

        if not items:
            progress.close()
            self._cleanup_dxf_worker()
            return

        progress.setLabelText(f"Adding {len(items)} items to scene…")
        QApplication.processEvents()

        # Temporarily disable BSP indexing for bulk insertion
        old_method = self.itemIndexMethod()
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

        for item in items:
            self.addItem(item)
        group = self.createItemGroup(items)
        group.setZValue(-100)
        group.setPos(params["x"], params["y"])
        group.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        group.setData(0, "DXF Underlay")

        record = params["_record"] or Underlay(
            type="dxf", path=params["file_path"],
            x=params["x"], y=params["y"],
            colour=color.name(),
            line_weight=params["line_weight"],
        )

        # Apply saved display settings
        self._apply_underlay_display(group, record)
        # Store sorted layer list on the group for the LayerManager
        all_layers = sorted({geom.get("layer", "0") for geom in geom_list})
        group.setData(2, all_layers)

        self.underlays.append((record, group))

        # Restore indexing
        self.setItemIndexMethod(old_method)

        progress.close()
        self._cleanup_dxf_worker()
        self.underlaysChanged.emit()
        print(f"✅ Imported DXF: {params['file_path']} ({len(items)} items)")

    def _geom_to_item(self, geom: dict, pen: QPen, color: QColor):
        """Convert a geometry dict (from DxfImportWorker) into a QGraphicsItem.
        Must be called on the main thread."""
        kind = geom["kind"]
        layer = geom.get("layer", "0")

        if kind == "line":
            item = QGraphicsLineItem(geom["x1"], geom["y1"], geom["x2"], geom["y2"])
            item.setPen(pen)
            item.setZValue(-100)

        elif kind == "circle":
            item = QGraphicsEllipseItem(geom["x"], geom["y"], geom["w"], geom["h"])
            item.setPen(pen)
            item.setZValue(-100)

        elif kind == "arc":
            path = QPainterPath()
            rect = QRectF(geom["rx"], geom["ry"], geom["rw"], geom["rh"])
            path.arcMoveTo(rect, geom["start"])
            path.arcTo(rect, geom["start"], geom["span"])
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            item.setZValue(-100)

        elif kind == "ellipse_full":
            item = QGraphicsEllipseItem(geom["x"], geom["y"], geom["w"], geom["h"])
            item.setPen(pen)
            item.setZValue(-100)
            item.setPos(geom["pos_cx"], geom["pos_cy"])
            item.setRotation(geom["rotation"])

        elif kind == "path_points":
            points = geom["points"]
            if len(points) < 2:
                return None
            path = QPainterPath()
            path.moveTo(points[0][0], points[0][1])
            for pt in points[1:]:
                path.lineTo(pt[0], pt[1])
            if geom.get("closed"):
                path.closeSubpath()
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            item.setZValue(-100)

        elif kind == "text":
            item = QGraphicsTextItem(geom["text"])
            item.setPos(geom["x"], geom["y"])
            item.setDefaultTextColor(color)
            item.setZValue(-100)

        else:
            return None

        # Tag each item with its DXF layer so LayerManager can toggle visibility
        item.setData(1, layer)
        return item

    def _on_dxf_error(self, msg: str, progress: QProgressDialog):
        progress.close()
        print(f"❌ {msg}")
        self._cleanup_dxf_worker()

    def _cleanup_dxf_worker(self):
        if hasattr(self, "_dxf_worker") and self._dxf_worker is not None:
            self._dxf_worker.quit()
            self._dxf_worker.wait()
        self._dxf_worker = None
        self._dxf_progress = None
        self._dxf_import_params = None

    def import_pdf(self, file_path, dpi=150, page=0, x=0.0, y=0.0,
                   _record: Underlay = None):
        try:
            doc = QPdfDocument(self)
            doc.load(file_path)
            page_count = doc.pageCount()

            if page < 0 or page >= page_count:
                raise IndexError(f"Page {page} out of range (0–{page_count-1})")

            page_size = doc.pagePointSize(page)
            if not page_size.isValid():
                raise RuntimeError("Invalid page size returned from PDF")

            width_px  = int(page_size.width()  * dpi / 72.0)
            height_px = int(page_size.height() * dpi / 72.0)

            options = QPdfDocumentRenderOptions()
            image   = doc.render(page, QSize(width_px, height_px), options)
            if image.isNull():
                raise RuntimeError("Failed to render PDF page to image")

            pixmap = QPixmap.fromImage(image)
            item   = QGraphicsPixmapItem(pixmap)
            item.setZValue(-100)
            item.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            )
            item.setPos(x if x != 0.0 else -pixmap.width()  / 2,
                        y if y != 0.0 else -pixmap.height() / 2)
            item.setData(0, "PDF Underlay")
            self.addItem(item)

            record = _record or Underlay(
                type="pdf", path=file_path,
                x=item.pos().x(), y=item.pos().y(),
                dpi=dpi, page=page
            )

            # Apply saved display settings
            self._apply_underlay_display(item, record)

            self.underlays.append((record, item))
            print(f"✅ Imported PDF '{file_path}' page {page} at {dpi} DPI")

        except Exception as e:
            print("❌ Error importing PDF:", e)

    # -------------------------------------------------------------------------
    # UNDERLAYS — MANAGEMENT

    def _apply_underlay_display(self, item: QGraphicsItem, record: Underlay):
        """Apply scale, rotation, opacity, and lock state from the record."""
        if record.scale != 1.0:
            item.setScale(record.scale)
        if record.rotation != 0.0:
            item.setRotation(record.rotation)
        if record.opacity < 1.0:
            item.setOpacity(record.opacity)
        if record.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def find_underlay_for_item(self, item: QGraphicsItem):
        """Return the (Underlay, QGraphicsItem) tuple for a scene item, or None."""
        for data, scene_item in self.underlays:
            if scene_item is item:
                return data, scene_item
        return None

    def remove_underlay(self, data: Underlay, item: QGraphicsItem):
        """Remove an underlay from the scene and the tracking list."""
        pair = (data, item)
        if pair in self.underlays:
            self.underlays.remove(pair)
        if item.scene() is self:
            if isinstance(item, QGraphicsItemGroup):
                # destroyItemGroup re-parents children back to the scene rather
                # than deleting them, so we must remove each child first.
                for child in item.childItems():
                    self.removeItem(child)
                self.destroyItemGroup(item)
            else:
                self.removeItem(item)
        self.underlaysChanged.emit()
        print(f"🗑️ Removed underlay: {data.path}")

    def refresh_underlay(self, data: Underlay, item: QGraphicsItem):
        """Re-import an underlay from disk, preserving position/scale/rotation/opacity."""
        # Sync current position back to record
        data.x = item.scenePos().x()
        data.y = item.scenePos().y()

        # Remove old item from scene
        idx = None
        for i, (d, it) in enumerate(self.underlays):
            if d is data:
                idx = i
                break
        if item.scene() is self:
            self.removeItem(item)

        # Re-import
        if data.type == "pdf":
            self.import_pdf(
                data.path, dpi=data.dpi, page=data.page,
                x=data.x, y=data.y, _record=data
            )
        elif data.type == "dxf":
            self.import_dxf(
                data.path, color=QColor(data.colour),
                line_weight=data.line_weight,
                x=data.x, y=data.y, _record=data
            )

        # The import functions append a new entry — remove the duplicate old slot if needed
        if idx is not None and idx < len(self.underlays):
            # Find and remove the entry pointing to the old (now removed) item
            # The fresh entry is at the end
            old_entries = [(i, d) for i, (d, it) in enumerate(self.underlays) if d is data]
            if len(old_entries) > 1:
                # Remove the first (stale) one
                self.underlays.pop(old_entries[0][0])

        print(f"🔄 Refreshed underlay: {data.path}")

    def refresh_all_underlays(self):
        """Re-import every underlay from disk."""
        # Take a snapshot since refresh modifies the list
        snapshot = list(self.underlays)
        for data, item in snapshot:
            self.refresh_underlay(data, item)

    # -------------------------------------------------------------------------
    # UNDO / REDO

    def _capture_network(self) -> dict:
        """Serialize nodes/pipes/annotations to a dict (no underlays/scale)."""
        node_list = list(self.sprinkler_system.nodes)
        node_id = {n: i for i, n in enumerate(node_list)}
        nodes_data = []
        for node in node_list:
            nodes_data.append({
                "id":        node_id[node],
                "x":         node.scenePos().x(),
                "y":         node.scenePos().y(),
                "elevation": node.z_pos,
                "sprinkler": node.sprinkler.get_properties() if node.has_sprinkler() else None,
            })
        pipes_data = []
        for pipe in self.sprinkler_system.pipes:
            if pipe.node1 is None or pipe.node2 is None:
                continue
            pipes_data.append({
                "node1_id":   node_id[pipe.node1],
                "node2_id":   node_id[pipe.node2],
                "properties": {k: v["value"] for k, v in pipe.get_properties().items()},
            })
        annotations_data = []
        for dim in self.annotations.dimensions:
            annotations_data.append({
                "type": "dimension",
                "p1":   [dim.handle1.scenePos().x(), dim.handle1.scenePos().y()],
                "p2":   [dim.handle2.scenePos().x(), dim.handle2.scenePos().y()],
                "properties": {k: v["value"] for k, v in dim.get_properties().items()},
            })
        for note in self.annotations.notes:
            annotations_data.append({
                "type": "note",
                "x":    note.scenePos().x(),
                "y":    note.scenePos().y(),
                "properties": {k: v["value"] for k, v in note.get_properties().items()},
            })
        ws = self.water_supply_node
        ws_data = None
        if ws is not None:
            ws_data = {
                "x":          ws.scenePos().x(),
                "y":          ws.scenePos().y(),
                "properties": {k: v["value"] for k, v in ws.get_properties().items()},
            }
        return {
            "nodes":              nodes_data,
            "pipes":              pipes_data,
            "annotations":        annotations_data,
            "water_supply":       ws_data,
            # ── Draw geometry ──────────────────────────────────────────────
            "construction_lines": [cl.to_dict() for cl in self._construction_lines],
            "polylines":          [pl.to_dict() for pl in self._polylines],
            "draw_lines":         [l.to_dict()  for l in self._draw_lines],
            "draw_rectangles":    [r.to_dict()  for r in self._draw_rects],
            "draw_circles":       [c.to_dict()  for c in self._draw_circles],
        }

    def _restore_network(self, state: dict):
        """Restore nodes/pipes/annotations from a dict (keeps underlays and scale)."""
        self._in_undo_restore = True
        try:
            for pipe in list(self.sprinkler_system.pipes):
                if pipe.scene() is self:
                    self.removeItem(pipe)
            for node in list(self.sprinkler_system.nodes):
                if node.scene() is self:
                    self.removeItem(node)
            for dim in list(self.annotations.dimensions):
                if dim.scene() is self:
                    self.removeItem(dim)
            for note in list(self.annotations.notes):
                if note.scene() is self:
                    self.removeItem(note)
            # Remove old water supply if present
            if self.water_supply_node and self.water_supply_node.scene() is self:
                self.removeItem(self.water_supply_node)
            self.water_supply_node = None
            self.sprinkler_system = SprinklerSystem()
            self.annotations = Annotation()

            id_to_node: dict[int, Node] = {}
            for entry in state.get("nodes", []):
                node = Node(entry["x"], entry["y"])
                self.addItem(node)
                self.sprinkler_system.add_node(node)
                id_to_node[entry["id"]] = node
                node.set_property("Elevation", str(entry.get("elevation", 0)))
                if entry.get("sprinkler"):
                    template = Sprinkler(None)
                    for key, value in entry["sprinkler"].items():
                        if isinstance(value, dict):
                            template.set_property(key, value["value"])
                        else:
                            template.set_property(key, value)
                    self.add_sprinkler(node, template)

            for entry in state.get("pipes", []):
                n1 = id_to_node.get(entry["node1_id"])
                n2 = id_to_node.get(entry["node2_id"])
                if n1 and n2:
                    pipe = Pipe(n1, n2)
                    self.sprinkler_system.add_pipe(pipe)
                    self.addItem(pipe)
                    pipe.update_label()
                    for key, value in entry.get("properties", {}).items():
                        pipe.set_property(key, value)

            for node in id_to_node.values():
                node.fitting.update()

            for entry in state.get("annotations", []):
                ann_type = entry.get("type")
                if ann_type == "dimension":
                    p1 = QPointF(entry["p1"][0], entry["p1"][1])
                    p2 = QPointF(entry["p2"][0], entry["p2"][1])
                    dim = DimensionAnnotation(p1, p2)
                    self.addItem(dim)
                    self.annotations.add_dimension(dim)
                    for key, value in entry.get("properties", {}).items():
                        dim.set_property(key, value)
                elif ann_type == "note":
                    note = NoteAnnotation(x=entry["x"], y=entry["y"])
                    self.addItem(note)
                    self.annotations.add_note(note)
                    for key, value in entry.get("properties", {}).items():
                        note.set_property(key, value)

            # Restore water supply
            ws_data = state.get("water_supply")
            if ws_data:
                ws = WaterSupply(ws_data["x"], ws_data["y"])
                self.addItem(ws)
                self.water_supply_node = ws
                self.sprinkler_system.supply_node = ws
                for key, value in ws_data.get("properties", {}).items():
                    ws.set_property(key, value)

            # ── Draw geometry ──────────────────────────────────────────────
            # Remove existing items from scene and lists
            for cl in list(self._construction_lines):
                if cl.scene() is self:
                    self.removeItem(cl)
            self._construction_lines.clear()

            for pl in list(self._polylines):
                if pl.scene() is self:
                    self.removeItem(pl)
            self._polylines.clear()

            for item in list(self._draw_lines):
                if item.scene() is self:
                    self.removeItem(item)
            self._draw_lines.clear()

            for item in list(self._draw_rects):
                if item.scene() is self:
                    self.removeItem(item)
            self._draw_rects.clear()

            for item in list(self._draw_circles):
                if item.scene() is self:
                    self.removeItem(item)
            self._draw_circles.clear()

            # Restore from snapshot
            for d in state.get("construction_lines", []):
                cl = ConstructionLine.from_dict(d)
                self.addItem(cl)
                self._construction_lines.append(cl)

            for d in state.get("polylines", []):
                pl = PolylineItem.from_dict(d)
                self.addItem(pl)
                self._polylines.append(pl)

            for d in state.get("draw_lines", []):
                li = LineItem.from_dict(d)
                self.addItem(li)
                self._draw_lines.append(li)

            for d in state.get("draw_rectangles", []):
                ri = RectangleItem.from_dict(d)
                self.addItem(ri)
                self._draw_rects.append(ri)

            for d in state.get("draw_circles", []):
                ci = CircleItem.from_dict(d)
                self.addItem(ci)
                self._draw_circles.append(ci)

        finally:
            self._in_undo_restore = False

    def push_undo_state(self):
        """Snapshot current network state onto the undo stack."""
        if self._in_undo_restore:
            return
        state = self._capture_network()
        # Discard redo history beyond current position
        self._undo_stack = self._undo_stack[:self._undo_pos + 1]
        self._undo_stack.append(state)
        if len(self._undo_stack) > self.UNDO_MAX:
            self._undo_stack.pop(0)
        else:
            self._undo_pos = len(self._undo_stack) - 1

    def undo(self):
        """Restore the previous network state."""
        if self._undo_pos > 0:
            self._undo_pos -= 1
            self._restore_network(self._undo_stack[self._undo_pos])

    def redo(self):
        """Restore the next network state."""
        if self._undo_pos < len(self._undo_stack) - 1:
            self._undo_pos += 1
            self._restore_network(self._undo_stack[self._undo_pos])

    # -------------------------------------------------------------------------
    # SCALE REFRESH

    def _refresh_all_scales(self):
        """Refresh visual sizes of all pipes, nodes, sprinklers, and fittings
        after a scale calibration change, then refresh all labels."""
        sm = self.scale_manager
        for pipe in self.sprinkler_system.pipes:
            pipe.update()       # triggers repaint with new scale-aware line weight
            pipe.update_label()
        for node in self.sprinkler_system.nodes:
            node.update()
            if node.has_sprinkler():
                node.sprinkler.rescale(sm)
            if node.has_fitting() and node.fitting.symbol is not None:
                node.fitting.rescale(sm)
                node.fitting.update()
        for dim in self.annotations.dimensions:
            dim.rescale(sm)
        if self.water_supply_node is not None:
            self.water_supply_node.rescale(sm)

    def _refresh_all_labels(self):
        """Refresh display text on all pipes and dimension annotations."""
        for pipe in self.sprinkler_system.pipes:
            pipe.update_label()
        for dim in self.annotations.dimensions:
            dim.update_label()

    def set_display_unit(self, unit):
        """Change the display unit and refresh all labels."""
        self.scale_manager.display_unit = unit
        self._refresh_all_labels()

    # -------------------------------------------------------------------------
    # HYDRAULICS

    def run_hydraulics(self, design_sprinklers=None):
        """Run the Hazen-Williams solver and store results for overlay display."""
        from hydraulic_solver import HydraulicSolver
        solver = HydraulicSolver(self.sprinkler_system, self.scale_manager)
        result = solver.solve(design_sprinklers=design_sprinklers)
        self.hydraulic_result = result
        # Refresh all pipe labels and node badges
        for pipe in self.sprinkler_system.pipes:
            pipe.update_label()
            pipe.update()
        for node in self.sprinkler_system.nodes:
            node.update()
        return result

    def clear_hydraulics(self):
        """Remove the hydraulic results overlay."""
        self.hydraulic_result = None
        for pipe in self.sprinkler_system.pipes:
            pipe.update_label()
            pipe.update()
        for node in self.sprinkler_system.nodes:
            node.update()

    def set_coverage_overlay(self, visible: bool):
        """Show or hide translucent coverage circles on all sprinkler nodes."""
        Node._coverage_visible = visible
        for node in self.sprinkler_system.nodes:
            node.update()

    def _get_draw_color(self) -> str:
        """Return the effective draw colour: explicit override, else active layer colour."""
        if self._draw_color and self._draw_color != "#ffffff":
            return self._draw_color
        if hasattr(self, "_user_layer_manager") and self._user_layer_manager:
            ldef = self._user_layer_manager.get(self.active_user_layer)
            if ldef:
                return ldef.color
        return self._draw_color

    # -------------------------------------------------------------------------
    # GEOMETRY HELPERS

    def get_snapped_position(self, x, y):
        grid = 10
        return QPointF(round(x / grid) * grid, round(y / grid) * grid)

    def get_effective_position(self, scene_pos: QPointF) -> QPointF:
        """Return best-fit cursor position: OSNAP > underlay snap > grid snap."""
        # OSNAP takes highest priority
        if self._osnap_enabled:
            views = self.views()
            if views:
                result = self._snap_engine.find(scene_pos, self, views[0].transform())
                self._snap_result = result
                if result is not None:
                    return result.point
            else:
                self._snap_result = None
        else:
            self._snap_result = None

        # Underlay snap
        if self._snap_to_underlay:
            snap_pt = self.find_snap_point(scene_pos)
            if snap_pt is not None:
                return snap_pt
        return self.get_snapped_position(scene_pos.x(), scene_pos.y())

    def toggle_osnap(self, enabled: bool | None = None):
        """Toggle or explicitly set OSNAP.  Called from ribbon button / F3."""
        if enabled is None:
            self._osnap_enabled = not self._osnap_enabled
        else:
            self._osnap_enabled = bool(enabled)
        self._snap_engine.enabled = self._osnap_enabled
        self._snap_result = None
        # Refresh foreground overlay
        for v in self.views():
            v.viewport().update()

    def find_snap_point(self, pos: QPointF) -> QPointF | None:
        """Find the nearest DXF underlay snap point within tolerance."""
        sm = self.scale_manager
        tolerance = sm.paper_to_scene(2.0) if sm.is_calibrated else 15.0
        search_rect = QRectF(pos.x() - tolerance, pos.y() - tolerance,
                             tolerance * 2, tolerance * 2)
        best_dist = tolerance
        best_pt = None
        for item in self.items(search_rect):
            parent = item.parentItem()
            if parent is None or not isinstance(parent, QGraphicsItemGroup):
                continue
            for pt in self._item_snap_points(item):
                d = math.hypot(pos.x() - pt.x(), pos.y() - pt.y())
                if d < best_dist:
                    best_dist = d
                    best_pt = pt
        return best_pt

    def _item_snap_points(self, item) -> list:
        """Return scene-coordinate snap points for a QGraphicsItem."""
        pts = []
        if isinstance(item, QGraphicsLineItem):
            line = item.line()
            pts.append(item.mapToScene(line.p1()))
            pts.append(item.mapToScene(line.p2()))
            pts.append(item.mapToScene(
                QPointF((line.x1() + line.x2()) / 2, (line.y1() + line.y2()) / 2)
            ))
        elif isinstance(item, QGraphicsEllipseItem):
            pts.append(item.mapToScene(item.boundingRect().center()))
        elif isinstance(item, QGraphicsPathItem):
            path = item.path()
            for i in range(min(path.elementCount(), 256)):   # cap to avoid spam on splines
                elem = path.elementAt(i)
                pts.append(item.mapToScene(QPointF(elem.x, elem.y)))
        return pts

    @staticmethod
    def _constrain_angle(anchor: QPointF, raw: QPointF) -> QPointF:
        """
        Return *raw* projected onto the nearest 0/45/90/135/180/225/270/315 °
        ray from *anchor*.  Used when the user holds Ctrl while drawing a line.
        """
        dx = raw.x() - anchor.x()
        dy = raw.y() - anchor.y()
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return anchor
        angle = math.atan2(dy, dx)
        # Snap angle to nearest multiple of π/4 (45°)
        snapped = round(angle / (math.pi / 4)) * (math.pi / 4)
        return QPointF(anchor.x() + dist * math.cos(snapped),
                       anchor.y() + dist * math.sin(snapped))

    # ─────────────────────────────────────────────────────────────────────────
    # Tab exact-input handler
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_tab_input(self):
        """
        Open a small dialog to let the user type exact dimensions for the
        current drawing operation (line length+angle, rect W+H, circle radius).
        Called by Model_View.keyPressEvent when Tab is pressed.
        """
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QFormLayout,
            QDoubleSpinBox, QDialogButtonBox,
        )

        sm = self.scale_manager

        # ── Line ──────────────────────────────────────────────────────────
        if self.mode == "draw_line" and self._draw_line_anchor is not None:
            anchor = self._draw_line_anchor

            dlg = QDialog()
            dlg.setWindowTitle("Exact Length & Angle")
            form = QFormLayout()
            l_spin = QDoubleSpinBox()
            l_spin.setRange(0.01, 1_000_000)
            l_spin.setDecimals(3)
            l_spin.setValue(100)
            l_spin.setSuffix("  px" if not sm.is_calibrated else "")
            a_spin = QDoubleSpinBox()
            a_spin.setRange(-360, 360)
            a_spin.setDecimals(2)
            a_spin.setValue(0)
            a_spin.setSuffix("  °")
            form.addRow("Length:", l_spin)
            form.addRow("Angle:", a_spin)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
            )
            outer = QVBoxLayout(dlg)
            outer.addLayout(form)
            outer.addWidget(buttons)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            length = l_spin.value()
            angle_rad = math.radians(a_spin.value())
            tip = QPointF(
                anchor.x() + length * math.cos(angle_rad),
                anchor.y() + length * math.sin(angle_rad),
            )
            color = self._get_draw_color()
            item = LineItem(anchor, tip, color, self._draw_lineweight)
            item.user_layer = self.active_user_layer
            self.addItem(item)
            self._draw_lines.append(item)
            self._draw_line_anchor = None
            self.preview_pipe.hide()
            self.push_undo_state()

        # ── Rectangle ────────────────────────────────────────────────────
        elif self.mode == "draw_rectangle" and self._draw_rect_anchor is not None:
            dlg = QDialog()
            dlg.setWindowTitle("Exact Width & Height")
            form = QFormLayout()
            suf = "" if not sm.is_calibrated else ""
            w_spin = QDoubleSpinBox()
            w_spin.setRange(0.01, 1_000_000)
            w_spin.setDecimals(3)
            w_spin.setValue(100)
            w_spin.setSuffix(suf)
            h_spin = QDoubleSpinBox()
            h_spin.setRange(0.01, 1_000_000)
            h_spin.setDecimals(3)
            h_spin.setValue(100)
            h_spin.setSuffix(suf)
            form.addRow("Width:", w_spin)
            form.addRow("Height:", h_spin)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
            )
            outer = QVBoxLayout(dlg)
            outer.addLayout(form)
            outer.addWidget(buttons)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            pt2 = QPointF(
                self._draw_rect_anchor.x() + w_spin.value(),
                self._draw_rect_anchor.y() + h_spin.value(),
            )
            color = self._get_draw_color()
            item = RectangleItem(self._draw_rect_anchor, pt2, color, self._draw_lineweight)
            item.user_layer = self.active_user_layer
            self.addItem(item)
            self._draw_rects.append(item)
            if self._draw_rect_preview is not None:
                self.removeItem(self._draw_rect_preview)
                self._draw_rect_preview = None
            self._draw_rect_anchor = None
            self.push_undo_state()

        # ── Polyline ─────────────────────────────────────────────────────
        elif self.mode == "polyline" and self._polyline_active is not None:
            anchor = self._polyline_active._points[-1]

            dlg = QDialog()
            dlg.setWindowTitle("Exact Segment Length & Angle")
            form = QFormLayout()
            l_spin = QDoubleSpinBox()
            l_spin.setRange(0.01, 1_000_000)
            l_spin.setDecimals(3)
            l_spin.setValue(100)
            l_spin.setSuffix("  px" if not sm.is_calibrated else "")
            a_spin = QDoubleSpinBox()
            a_spin.setRange(-360, 360)
            a_spin.setDecimals(2)
            a_spin.setValue(0)
            a_spin.setSuffix("  °")
            form.addRow("Length:", l_spin)
            form.addRow("Angle:", a_spin)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
            )
            outer = QVBoxLayout(dlg)
            outer.addLayout(form)
            outer.addWidget(buttons)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            length = l_spin.value()
            angle_rad = math.radians(a_spin.value())
            tip = QPointF(
                anchor.x() + length * math.cos(angle_rad),
                anchor.y() + length * math.sin(angle_rad),
            )
            self._polyline_active.append_point(tip)
            self.push_undo_state()

        # ── Circle ───────────────────────────────────────────────────────
        elif self.mode == "draw_circle" and self._draw_circle_center is not None:
            dlg = QDialog()
            dlg.setWindowTitle("Exact Radius")
            form = QFormLayout()
            r_spin = QDoubleSpinBox()
            r_spin.setRange(0.01, 1_000_000)
            r_spin.setDecimals(3)
            r_spin.setValue(50)
            form.addRow("Radius:", r_spin)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
            )
            outer = QVBoxLayout(dlg)
            outer.addLayout(form)
            outer.addWidget(buttons)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            r = r_spin.value()
            color = self._get_draw_color()
            item = CircleItem(self._draw_circle_center, r, color, self._draw_lineweight)
            item.user_layer = self.active_user_layer
            self.addItem(item)
            self._draw_circles.append(item)
            if self._draw_circle_preview is not None:
                self.removeItem(self._draw_circle_preview)
                self._draw_circle_preview = None
            self._draw_circle_center = None
            self.push_undo_state()

    # ─────────────────────────────────────────────────────────────────────────
    # Grid Lines
    # ─────────────────────────────────────────────────────────────────────────

    def place_grid_lines(self, params: dict):
        """
        Place a rectangular grid of construction lines from *params*.

        Parameters (keys in *params*)
        ------------------------------
        h_count   : int   — number of horizontal lines (0 = none)
        h_first   : float — Y-coordinate of the first horizontal line
        h_spacing : float — Y-increment between successive horizontal lines
        v_count   : int   — number of vertical lines (0 = none)
        v_first   : float — X-coordinate of the first vertical line
        v_spacing : float — X-increment between successive vertical lines
        """
        h_count   = int(params.get("h_count",   0))
        h_first   = float(params.get("h_first",   0))
        h_spacing = float(params.get("h_spacing", 100))
        v_count   = int(params.get("v_count",   0))
        v_first   = float(params.get("v_first",   0))
        v_spacing = float(params.get("v_spacing", 100))

        # Horizontal lines: run parallel to the X-axis (constant Y)
        # Two anchor points differ only in X so the line extends left↔right.
        for i in range(h_count):
            y = h_first + i * h_spacing
            cl = ConstructionLine(QPointF(-1, y), QPointF(1, y))
            self.addItem(cl)
            self._construction_lines.append(cl)

        # Vertical lines: run parallel to the Y-axis (constant X)
        for i in range(v_count):
            x = v_first + i * v_spacing
            cl = ConstructionLine(QPointF(x, -1), QPointF(x, 1))
            self.addItem(cl)
            self._construction_lines.append(cl)

        if h_count > 0 or v_count > 0:
            self.push_undo_state()

    # ─────────────────────────────────────────────────────────────────────────
    # OFFSET COMMAND helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _offset_line_intersection(
        self, p1: QPointF, d1: QPointF, p2: QPointF, d2: QPointF
    ) -> "QPointF | None":
        """Return intersection of two infinite lines (p1+t*d1) and (p2+s*d2), or None."""
        denom = d1.x() * d2.y() - d1.y() * d2.x()
        if abs(denom) < 1e-10:
            return None  # parallel
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        t = (dx * d2.y() - dy * d2.x()) / denom
        return QPointF(p1.x() + t * d1.x(), p1.y() + t * d1.y())

    def _offset_polyline_pts(
        self, pts: list, signed_dist: float
    ) -> list:
        """Return offset polyline points (miter join at corners)."""
        n = len(pts)
        if n < 2:
            return list(pts)
        # Per-segment left-side unit normals
        normals = []
        for i in range(n - 1):
            dx = pts[i + 1].x() - pts[i].x()
            dy = pts[i + 1].y() - pts[i].y()
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-10:
                normals.append(None)
            else:
                normals.append((-dy / seg_len, dx / seg_len))

        result = []
        for i in range(n):
            if i == 0:
                nx, ny = normals[0] if normals[0] else (0.0, 0.0)
                result.append(QPointF(pts[0].x() + signed_dist * nx,
                                      pts[0].y() + signed_dist * ny))
            elif i == n - 1:
                nx, ny = normals[-1] if normals[-1] else (0.0, 0.0)
                result.append(QPointF(pts[-1].x() + signed_dist * nx,
                                      pts[-1].y() + signed_dist * ny))
            else:
                n1 = normals[i - 1]
                n2 = normals[i]
                if n1 is None:
                    n1 = n2
                if n2 is None:
                    n2 = n1
                # Offset lines: p_prev + t*(pts[i]-pts[i-1]) + d*n1
                #               pts[i] + s*(pts[i+1]-pts[i]) + d*n2
                op1 = QPointF(pts[i - 1].x() + signed_dist * n1[0],
                              pts[i - 1].y() + signed_dist * n1[1])
                op2 = QPointF(pts[i].x() + signed_dist * n1[0],
                              pts[i].y() + signed_dist * n1[1])
                op3 = QPointF(pts[i].x() + signed_dist * n2[0],
                              pts[i].y() + signed_dist * n2[1])
                op4 = QPointF(pts[i + 1].x() + signed_dist * n2[0],
                              pts[i + 1].y() + signed_dist * n2[1])
                d1 = QPointF(op2.x() - op1.x(), op2.y() - op1.y())
                d2 = QPointF(op4.x() - op3.x(), op4.y() - op3.y())
                inter = self._offset_line_intersection(op1, d1, op3, d2)
                if inter is not None:
                    result.append(inter)
                else:
                    result.append(op2)  # fallback: parallel segments
        return result

    def _offset_signed_dist(self, source, dist: float, side_pt: QPointF) -> float:
        """Return +dist or -dist depending on which side of source the cursor is on."""
        if isinstance(source, LineItem):
            line = source.line()
            p1 = source.mapToScene(line.p1())
            p2 = source.mapToScene(line.p2())
            dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
            # Cross product with cursor vector: positive → left of line
            cross = dx * (side_pt.y() - p1.y()) - dy * (side_pt.x() - p1.x())
            return dist if cross >= 0 else -dist
        if isinstance(source, PolylineItem):
            pts = source._points
            if len(pts) < 2:
                return dist
            p1, p2 = pts[0], pts[1]
            dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
            cross = dx * (side_pt.y() - p1.y()) - dy * (side_pt.x() - p1.x())
            return dist if cross >= 0 else -dist
        if isinstance(source, CircleItem):
            cx = source.x() + source.boundingRect().center().x()
            cy = source.y() + source.boundingRect().center().y()
            d = math.hypot(side_pt.x() - cx, side_pt.y() - cy)
            r = source.boundingRect().width() / 2
            return dist if d >= r else -dist
        if isinstance(source, RectangleItem):
            # cursor outside → grow, cursor inside → shrink
            r = source.mapRectToScene(source.rect())
            if r.contains(side_pt):
                return -dist
            return dist
        return dist

    def _make_offset_item(self, source, signed_dist: float):
        """Create and return a new item that is the offset of source, or None."""
        color = source.pen().color()
        lw = source.pen().widthF()

        if isinstance(source, LineItem):
            line = source.line()
            p1 = source.mapToScene(line.p1())
            p2 = source.mapToScene(line.p2())
            dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-10:
                return None
            nx, ny = -dy / seg_len, dx / seg_len
            new_p1 = QPointF(p1.x() + signed_dist * nx, p1.y() + signed_dist * ny)
            new_p2 = QPointF(p2.x() + signed_dist * nx, p2.y() + signed_dist * ny)
            item = LineItem(new_p1, new_p2, color, lw)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            return item

        if isinstance(source, PolylineItem):
            pts = source._points
            new_pts = self._offset_polyline_pts(pts, signed_dist)
            if len(new_pts) < 2:
                return None
            item = PolylineItem(new_pts[0], color, lw)
            for p in new_pts[1:]:
                item.append_point(p)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            return item

        if isinstance(source, CircleItem):
            r = source.boundingRect().width() / 2
            new_r = r + signed_dist
            if new_r <= 0:
                return None
            # CircleItem stores center as scene position of its bounding rect centre
            scene_rect = source.mapRectToScene(source.rect())
            cx = scene_rect.center().x()
            cy = scene_rect.center().y()
            item = CircleItem(QPointF(cx, cy), new_r, color, lw)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            return item

        if isinstance(source, RectangleItem):
            r = source.mapRectToScene(source.rect())
            new_r = r.adjusted(-signed_dist, -signed_dist, signed_dist, signed_dist)
            if new_r.width() <= 0 or new_r.height() <= 0:
                return None
            item = RectangleItem(new_r.topLeft(), new_r.bottomRight(), color, lw)
            item.user_layer = getattr(source, "user_layer", self.active_user_layer)
            return item
        return None

    def _clear_offset_preview(self):
        if self._offset_preview is not None:
            if self._offset_preview.scene() is self:
                self.removeItem(self._offset_preview)
            self._offset_preview = None

    def project_point_onto_line(self, p1: QPointF, p2: QPointF, p: QPointF) -> QPointF:
        line_dx = p2.x() - p1.x()
        line_dy = p2.y() - p1.y()
        line_len2 = line_dx**2 + line_dy**2
        if line_len2 == 0:
            return p1
        t = ((p.x() - p1.x()) * line_dx + (p.y() - p1.y()) * line_dy) / line_len2
        t = max(0, min(1, t))
        return QPointF(p1.x() + t * line_dx, p1.y() + t * line_dy)

    def project_click_onto_pipe_segment(self, snapped, selection):
        line = selection.line()
        return self.project_point_onto_line(
            QPointF(line.x1(), line.y1()), QPointF(line.x2(), line.y2()), snapped
        )

    def update_preview_node(self, pos: QPointF):
        offset = self.preview_node.boundingRect().center()
        self.preview_node.setPos(pos - offset)
        self.preview_node.show()

    # -------------------------------------------------------------------------
    # MOUSE EVENTS

    def mouseMoveEvent(self, event):
        scene_pos = event.scenePos()
        sm = self.scale_manager
        if sm.is_calibrated:
            coord_str = (f"X: {sm.scene_to_display(scene_pos.x())}  "
                         f"Y: {sm.scene_to_display(scene_pos.y())}")
        else:
            coord_str = f"X: {scene_pos.x():.0f} px  Y: {scene_pos.y():.0f} px"
        self.cursorMoved.emit(coord_str)

        snapped = self.get_effective_position(scene_pos)
        self._draw_dim_hint = None   # cleared each frame; draw modes set it below

        if self.mode == "pipe":
            if self.node_start_pos:
                start = self.node_start_pos.scenePos()
                snapped_end = self.node_start_pos.snap_point_45(start, snapped)
                self.update_preview_node(snapped_end)
                self.preview_pipe.setLine(start.x(), start.y(), snapped_end.x(), snapped_end.y())
                self.preview_pipe.show()
            else:
                self.update_preview_node(snapped)
                self.preview_pipe.hide()

        elif self.mode == "set_scale":
            self.update_preview_node(snapped)
            if self._cal_point1 is not None:
                self.preview_pipe.setLine(
                    self._cal_point1.x(), self._cal_point1.y(),
                    snapped.x(), snapped.y()
                )
                self.preview_pipe.show()
            else:
                self.preview_pipe.hide()

        elif self.mode == "design_area":
            self.preview_node.hide()
            self.preview_pipe.hide()
            if self._design_area_corner1 is not None and self._design_area_rect_item is not None:
                c1 = self._design_area_corner1
                rect = QRectF(c1, snapped).normalized()
                self._design_area_rect_item.setRect(rect)

        elif self.mode == "polyline":
            self.preview_node.hide()
            self.preview_pipe.hide()
            if self._polyline_active is not None:
                tip = snapped
                if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                        and len(self._polyline_active._points) >= 1):
                    tip = self._constrain_angle(
                        self._polyline_active._points[-1], snapped
                    )
                self._polyline_active.update_preview(tip)
                _last = self._polyline_active._points[-1]
                _dx = tip.x() - _last.x()
                _dy = tip.y() - _last.y()
                _len = math.hypot(_dx, _dy)
                _ang = math.degrees(math.atan2(_dy, _dx))
                self._draw_dim_hint = (
                    f"L: {sm.scene_to_display(_len)}  A: {_ang:.1f}°"
                    if sm.is_calibrated else
                    f"L: {_len:.0f}px  A: {_ang:.1f}°"
                )

        elif self.mode == "draw_line":
            self.preview_node.hide()
            if self._draw_line_anchor is not None:
                tip = snapped
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    tip = self._constrain_angle(self._draw_line_anchor, snapped)
                self.preview_pipe.setLine(
                    self._draw_line_anchor.x(), self._draw_line_anchor.y(),
                    tip.x(), tip.y()
                )
                self.preview_pipe.show()
                _dx = tip.x() - self._draw_line_anchor.x()
                _dy = tip.y() - self._draw_line_anchor.y()
                _len = math.hypot(_dx, _dy)
                _ang = math.degrees(math.atan2(_dy, _dx))
                self._draw_dim_hint = (
                    f"L: {sm.scene_to_display(_len)}  A: {_ang:.1f}°"
                    if sm.is_calibrated else
                    f"L: {_len:.0f}px  A: {_ang:.1f}°"
                )
            else:
                self.preview_pipe.hide()

        elif self.mode == "draw_rectangle":
            self.preview_node.hide()
            self.preview_pipe.hide()
            if self._draw_rect_anchor is not None and self._draw_rect_preview is not None:
                rect = QRectF(self._draw_rect_anchor, snapped).normalized()
                self._draw_rect_preview.setRect(rect)
                self._draw_dim_hint = (
                    f"W: {sm.scene_to_display(rect.width())}  H: {sm.scene_to_display(rect.height())}"
                    if sm.is_calibrated else
                    f"W: {rect.width():.0f}px  H: {rect.height():.0f}px"
                )

        elif self.mode == "draw_circle":
            self.preview_node.hide()
            self.preview_pipe.hide()
            if self._draw_circle_center is not None and self._draw_circle_preview is not None:
                r = math.hypot(snapped.x() - self._draw_circle_center.x(),
                               snapped.y() - self._draw_circle_center.y())
                cx, cy = self._draw_circle_center.x(), self._draw_circle_center.y()
                self._draw_circle_preview.setRect(cx - r, cy - r, 2 * r, 2 * r)
                self._draw_dim_hint = (
                    f"R: {sm.scene_to_display(r)}"
                    if sm.is_calibrated else
                    f"R: {r:.0f}px"
                )

        elif self.mode == "place_import":
            self.preview_node.hide()
            self.preview_pipe.hide()
            self._update_place_import_ghost(snapped)

        elif self.mode == "offset":
            self.preview_node.hide()
            self.preview_pipe.hide()

        elif self.mode == "offset_side":
            self.preview_node.hide()
            self.preview_pipe.hide()
            if self._offset_source is not None and self._offset_dist > 0:
                sd = self._offset_signed_dist(self._offset_source, self._offset_dist, snapped)
                self._clear_offset_preview()
                preview = self._make_offset_item(self._offset_source, sd)
                if preview is not None:
                    pen = preview.pen()
                    pen.setStyle(Qt.PenStyle.DashLine)
                    preview.setPen(pen)
                    preview.setZValue(200)
                    self.addItem(preview)
                    self._offset_preview = preview

        elif self.mode in ("sprinkler", "dimension", "paste", "move", "water_supply"):
            self.update_preview_node(snapped)
            self.preview_pipe.hide()
        else:
            # ── Grip drag ──────────────────────────────────────────────────
            if self._grip_dragging and self._grip_item is not None:
                self._grip_item.apply_grip(self._grip_index, snapped)
                # Refresh foreground (grip handle positions changed)
                for v in self.views():
                    v.viewport().update()
                return
            self.preview_node.hide()
            self.preview_pipe.hide()

        # Repaint foreground for snap indicator / grip overlay
        for v in self.views():
            v.viewport().update()

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        scene_pos = event.scenePos()
        snapped   = self.get_effective_position(scene_pos)

        items     = self.items(snapped)
        selection = next((i for i in items if isinstance(i, Node)), None)
        if selection is None:
            selection = next((i for i in items if isinstance(i, Pipe)), None)

        if self.mode == "sprinkler":
            if selection is None:
                node = self.add_node(snapped.x(), snapped.y())
            elif isinstance(selection, Pipe):
                node = self.split_pipe(selection, self.project_click_onto_pipe_segment(snapped, selection))
            elif isinstance(selection, Node):
                node = selection
                if node.has_sprinkler():
                    return
            self.add_sprinkler(node, getattr(self, "current_template", None))
            node.fitting.update()
            self.push_undo_state()

        elif self.mode == "pipe":
            if self.node_start_pos is None:
                if isinstance(selection, Pipe):
                    self.node_start_pos = self.split_pipe(selection, self.project_click_onto_pipe_segment(snapped, selection))
                else:
                    self.node_start_pos = self.find_or_create_node(snapped.x(), snapped.y())
            else:
                start_pos   = self.node_start_pos.scenePos()
                snapped_end = self.node_start_pos.snap_point_45(start_pos, snapped)
                if isinstance(selection, Pipe):
                    end_node = self.split_pipe(selection, self.project_click_onto_pipe_segment(snapped_end, selection))
                else:
                    end_node = self.find_or_create_node(snapped_end.x(), snapped_end.y())
                self.add_pipe(self.node_start_pos, end_node, getattr(self, "current_template", None))
                self.node_start_pos.fitting.update()
                end_node.fitting.update()
                self.node_start_pos = None
                self.preview_pipe.hide()
                self.preview_node.hide()
                self.push_undo_state()

        elif self.mode == "set_scale":
            if self._cal_point1 is None:
                self._cal_point1 = snapped
                print(f"Scale point 1: ({snapped.x():.1f}, {snapped.y():.1f}) — click second point")
            else:
                dialog = CalibrateDialog(self.views()[0] if self.views() else None)
                if dialog.exec():
                    distance = dialog.get_distance()
                    unit = dialog.get_unit_code()
                    try:
                        self.scale_manager.calibrate(
                            self._cal_point1, snapped, distance, unit
                        )
                        self.scale_manager.drawing_scale = dialog.get_drawing_scale()
                        print(f"✅ Scale set: {self.scale_manager.pixels_per_mm:.4f} px/mm, "
                              f"drawing scale 1:{self.scale_manager.drawing_scale:.0f}")
                        self._refresh_all_scales()
                    except ValueError as e:
                        print(f"❌ Calibration failed: {e}")
                self._cal_point1 = None
                self.set_mode(None)
                return

        elif self.mode == "dimension":
            if self.dimension_start is None:
                self.dimension_start = snapped
            else:
                dim = DimensionAnnotation(self.dimension_start, snapped)
                self.addItem(dim)
                self.annotations.add_dimension(dim)
                self.requestPropertyUpdate.emit(dim)
                self.dimension_start = None
                self.push_undo_state()

        elif self.mode == "water_supply":
            # Place (or replace) the water supply node at the clicked position
            if self.water_supply_node is not None:
                self.removeItem(self.water_supply_node)
            ws = WaterSupply(snapped.x(), snapped.y())
            self.addItem(ws)
            self.water_supply_node = ws
            self.sprinkler_system.supply_node = ws
            self.requestPropertyUpdate.emit(ws)
            self.push_undo_state()
            self.set_mode(None)
            return

        elif self.mode == "design_area":
            if self._design_area_corner1 is None:
                # First click: set corner1 and create preview rect
                self._design_area_corner1 = snapped
                rect_item = QGraphicsRectItem(QRectF(snapped, snapped))
                rect_item.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
                rect_item.setBrush(QBrush(QColor(255, 200, 0, 40)))
                rect_item.setZValue(200)
                self.addItem(rect_item)
                self._design_area_rect_item = rect_item
            else:
                # Second click: commit the rectangle
                c1 = self._design_area_corner1
                selection_rect = QRectF(c1, snapped).normalized()
                # Find sprinklers inside the rectangle
                self.design_area_sprinklers = [
                    s for s in self.sprinkler_system.sprinklers
                    if s.node and selection_rect.contains(s.node.scenePos())
                ]
                # Reset corner for next use
                self._design_area_corner1 = None
                # Keep the rect visible as a reminder (user can clear it)
                self.set_mode(None)
                print(f"Design area: {len(self.design_area_sprinklers)} sprinkler(s) selected.")
            return

        elif self.mode in ("paste", "move"):
            if self.node_start_pos is None:
                self.node_start_pos = snapped
            else:
                offset = CAD_Math.get_vector(self.node_start_pos, snapped)
                if self.mode == "paste":
                    self.paste_items(offset)
                elif self.mode == "move":
                    self.move_items(offset)
                self.push_undo_state()
                self.node_start_pos = None
                self.set_mode(None)
                return

        elif self.mode == "place_import":
            self._commit_place_import(snapped)
            return

        elif self.mode == "offset":
            # Select entity to offset
            hit = [i for i in self.items(scene_pos)
                   if isinstance(i, (LineItem, PolylineItem, CircleItem, RectangleItem))]
            if not hit:
                return
            self._offset_source = hit[0]
            # Ask for offset distance
            from PyQt6.QtWidgets import (
                QDialog, QVBoxLayout, QFormLayout,
                QDoubleSpinBox, QDialogButtonBox,
            )
            dlg = QDialog()
            dlg.setWindowTitle("Offset Distance")
            form = QFormLayout()
            d_spin = QDoubleSpinBox()
            d_spin.setRange(0.01, 1_000_000)
            d_spin.setDecimals(3)
            d_spin.setValue(self._offset_dist if self._offset_dist > 0 else 10.0)
            sm = self.scale_manager
            d_spin.setSuffix("  px" if not sm.is_calibrated else "")
            form.addRow("Distance:", d_spin)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok |
                QDialogButtonBox.StandardButton.Cancel
            )
            outer = QVBoxLayout(dlg)
            outer.addLayout(form)
            outer.addWidget(buttons)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._offset_source = None
                return
            self._offset_dist = d_spin.value()
            self.set_mode("offset_side")
            return

        elif self.mode == "offset_side":
            # Click determines which side — commit the offset
            if self._offset_source is not None and self._offset_dist > 0:
                sd = self._offset_signed_dist(self._offset_source, self._offset_dist, snapped)
                self._clear_offset_preview()
                new_item = self._make_offset_item(self._offset_source, sd)
                if new_item is not None:
                    if isinstance(new_item, LineItem):
                        self.addItem(new_item)
                        self._draw_lines.append(new_item)
                    elif isinstance(new_item, PolylineItem):
                        self.addItem(new_item)
                        self._polylines.append(new_item)
                    elif isinstance(new_item, CircleItem):
                        self.addItem(new_item)
                        self._draw_circles.append(new_item)
                    elif isinstance(new_item, RectangleItem):
                        self.addItem(new_item)
                        self._draw_rects.append(new_item)
                    self.push_undo_state()
            # Stay in offset mode ready for next entity
            self._offset_source = None
            self.set_mode("offset")
            return

        elif self.mode == "polyline":
            if self._polyline_active is None:
                # First click — create the polyline item
                color = self._get_draw_color()
                pl = PolylineItem(snapped, color, self._draw_lineweight)
                pl.user_layer = self.active_user_layer
                self.addItem(pl)
                self._polylines.append(pl)
                self._polyline_active = pl
            else:
                # Subsequent clicks — append vertex (apply Ctrl constraint if held)
                tip = snapped
                if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                        and len(self._polyline_active._points) >= 1):
                    tip = self._constrain_angle(
                        self._polyline_active._points[-1], snapped
                    )
                self._polyline_active.append_point(tip)
            return  # don't let super() deselect items mid-draw

        elif self.mode == "draw_line":
            if self._draw_line_anchor is None:
                self._draw_line_anchor = snapped
            else:
                # Place the line (apply Ctrl constraint if held)
                tip = snapped
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    tip = self._constrain_angle(self._draw_line_anchor, snapped)
                color = self._get_draw_color()
                lw = self._draw_lineweight
                item = LineItem(self._draw_line_anchor, tip, color, lw)
                item.user_layer = self.active_user_layer
                self.addItem(item)
                self._draw_lines.append(item)
                self._draw_line_anchor = None
                self.preview_pipe.hide()
                self.push_undo_state()
            return

        elif self.mode == "draw_rectangle":
            if self._draw_rect_anchor is None:
                self._draw_rect_anchor = snapped
                # Create preview rect
                preview = QGraphicsRectItem(QRectF(snapped, snapped))
                preview.setPen(QPen(QColor(self._draw_color), 1, Qt.PenStyle.DashLine))
                preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                preview.setZValue(200)
                self.addItem(preview)
                self._draw_rect_preview = preview
            else:
                # Commit rectangle
                rect = QRectF(self._draw_rect_anchor, snapped).normalized()
                color = self._get_draw_color()
                lw = self._draw_lineweight
                item = RectangleItem(
                    QPointF(rect.x(), rect.y()),
                    QPointF(rect.x() + rect.width(), rect.y() + rect.height()),
                    color, lw
                )
                item.user_layer = self.active_user_layer
                self.addItem(item)
                self._draw_rects.append(item)
                # Remove preview
                if self._draw_rect_preview is not None:
                    self.removeItem(self._draw_rect_preview)
                    self._draw_rect_preview = None
                self._draw_rect_anchor = None
                self.push_undo_state()
            return

        elif self.mode == "draw_circle":
            if self._draw_circle_center is None:
                self._draw_circle_center = snapped
                # Create preview circle
                preview = QGraphicsEllipseItem(snapped.x(), snapped.y(), 0, 0)
                preview.setPen(QPen(QColor(self._draw_color), 1, Qt.PenStyle.DashLine))
                preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                preview.setZValue(200)
                self.addItem(preview)
                self._draw_circle_preview = preview
            else:
                # Commit circle
                r = math.hypot(snapped.x() - self._draw_circle_center.x(),
                               snapped.y() - self._draw_circle_center.y())
                if r > 0:
                    color = self._get_draw_color()
                    lw = self._draw_lineweight
                    item = CircleItem(self._draw_circle_center, r, color, lw)
                    item.user_layer = self.active_user_layer
                    self.addItem(item)
                    self._draw_circles.append(item)
                # Remove preview
                if self._draw_circle_preview is not None:
                    self.removeItem(self._draw_circle_preview)
                    self._draw_circle_preview = None
                self._draw_circle_center = None
                self.push_undo_state()
            return

        elif self.mode is None:
            if isinstance(selection, Node):
                print(selection)
                print(f"node has: {len(selection.pipes)} pipes connected")
            # ── Check for grip handle hit ───────────────────────────────────
            grip_hit = self._find_grip_hit(snapped)
            if grip_hit is not None:
                self._grip_item, self._grip_index = grip_hit
                self._grip_dragging = True
                return  # consumed — don't deselect / pass to super()

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._grip_dragging:
            self._grip_dragging = False
            self._grip_item     = None
            self._grip_index    = -1
            self.push_undo_state()
            for v in self.views():
                v.viewport().update()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu for underlays on right-click.
        Uses self.items() instead of itemAt() so locked underlays (ItemIsSelectable=False) are found."""
        hit_items = self.items(event.scenePos())

        for item in hit_items:
            candidate = item
            while candidate is not None:
                result = self.find_underlay_for_item(candidate)
                if result is not None:
                    data, scene_item = result
                    UnderlayContextMenu.show(
                        self, data, scene_item,
                        event.screenPos()
                    )
                    return
                candidate = candidate.parentItem()

        super().contextMenuEvent(event)

    # -------------------------------------------------------------------------
    # KEY EVENTS

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.set_mode(None)
            for item in self.selectedItems():
                item.setSelected(False)
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selected_items()
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            for item in self.items():
                if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                    item.setSelected(True)
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
        elif event.key() == Qt.Key.Key_Y and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.redo()
        elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selected_items()
        elif event.key() == Qt.Key.Key_M and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.selectedItems():
                self._selected_items = self.selectedItems()
                self.set_mode("move")
        elif event.key() == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.duplicate_selected()
        elif event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.clipboard_data():
                self.set_mode("paste")
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Finish an in-progress polyline
            if self.mode == "polyline" and self._polyline_active is not None:
                if len(self._polyline_active._points) >= 2:
                    self._polyline_active.finalize()
                    self._polyline_active = None
                    self.push_undo_state()
                    # Stay in polyline mode so user can draw another
        else:
            super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # COPY / PASTE / MOVE

    def copy_selected_items(self):
        data = []
        for item in self.selectedItems():
            if isinstance(item, Node):
                sprinkler = item.sprinkler.get_properties() if item.has_sprinkler() else None
                pipes = []
                for p in item.pipes:
                    other = p.node1 if p.node2 == item else p.node2
                    pipes.append({"x": other.pos().x(), "y": other.pos().y()})
                data.append({
                    "type": "node",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "sprinkler": sprinkler,
                    "pipes": pipes,
                })
            elif hasattr(item, "to_dict"):
                data.append(item.to_dict())
        QApplication.clipboard().setText(json.dumps(data))

    def paste_items(self, offset):
        data = self.clipboard_data()
        for obj in data:
            obj_type = obj.get("type", "")
            if obj_type == "node":
                new_x = obj["x"] + offset.x()
                new_y = obj["y"] + offset.y()
                existing = self.find_nearby_node(new_x, new_y)
                node1 = existing if existing else self.add_node(new_x, new_y)

                if obj.get("sprinkler"):
                    template = Sprinkler(None)
                    for key, meta in obj["sprinkler"].items():
                        template.set_property(key, meta["value"])
                    self.add_sprinkler(node1, template)

                for p in obj.get("pipes", []):
                    px = p["x"] + offset.x()
                    py = p["y"] + offset.y()
                    existing_p = self.find_nearby_node(px, py)
                    node2 = existing_p if existing_p else self.add_node(px, py)
                    if not any(
                        (pipe.node1 == node1 and pipe.node2 == node2) or
                        (pipe.node1 == node2 and pipe.node2 == node1)
                        for pipe in self.sprinkler_system.pipes
                    ):
                        self.add_pipe(node1, node2)
                node1.fitting.update()

            elif obj_type == "draw_line":
                item = LineItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.user_layer = self.active_user_layer
                self.addItem(item)
                self._draw_lines.append(item)

            elif obj_type == "draw_rectangle":
                item = RectangleItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.user_layer = self.active_user_layer
                self.addItem(item)
                self._draw_rects.append(item)

            elif obj_type == "draw_circle":
                item = CircleItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.user_layer = self.active_user_layer
                self.addItem(item)
                self._draw_circles.append(item)

            elif obj_type == "polyline":
                item = PolylineItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.user_layer = self.active_user_layer
                self.addItem(item)
                self._polylines.append(item)

            elif obj_type == "construction_line":
                item = ConstructionLine.from_dict(obj)
                item.translate(offset.x(), offset.y())
                self.addItem(item)
                self._construction_lines.append(item)

            elif obj_type == "block_item":
                from block_item import BlockItem
                def _item_factory(d):
                    t = d.get("type", "")
                    if t == "draw_line":
                        return LineItem.from_dict(d)
                    elif t == "draw_rectangle":
                        return RectangleItem.from_dict(d)
                    elif t == "draw_circle":
                        return CircleItem.from_dict(d)
                    elif t == "polyline":
                        return PolylineItem.from_dict(d)
                    elif t == "construction_line":
                        return ConstructionLine.from_dict(d)
                    elif t == "block_item":
                        return BlockItem.from_dict(d, _item_factory)
                    return None
                item = BlockItem.from_dict(obj, _item_factory)
                item.translate(offset.x(), offset.y())
                self.addItem(item)
                # BlockItems live in the scene but aren't tracked in a dedicated list

    def move_items(self, offset):
        if not self._selected_items:
            return
        for item in self._selected_items:
            if isinstance(item, Node):
                item.moveBy(offset.x(), offset.y())
                item.setSelected(True)
                item.fitting.update()
            elif hasattr(item, "translate"):
                item.translate(offset.x(), offset.y())
                item.setSelected(True)
        self._selected_items = None   # clear after use

    def clipboard_data(self):
        text = QApplication.clipboard().text()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    # -------------------------------------------------------------------------
    # DUPLICATE (Sprint I)

    def duplicate_selected(self):
        """Copy selected items and immediately paste them at +10,+10 offset."""
        items = self.selectedItems()
        if not items:
            return

        data = []
        for item in items:
            if isinstance(item, Node):
                sprinkler = item.sprinkler.get_properties() if item.has_sprinkler() else None
                pipes_d = []
                for p in item.pipes:
                    other = p.node1 if p.node2 == item else p.node2
                    pipes_d.append({"x": other.pos().x(), "y": other.pos().y()})
                data.append({
                    "type": "node",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "sprinkler": sprinkler, "pipes": pipes_d,
                })
            elif hasattr(item, "to_dict"):
                data.append(item.to_dict())

        if not data:
            return

        # Temporarily swap clipboard → paste → restore
        old = QApplication.clipboard().text()
        QApplication.clipboard().setText(json.dumps(data))
        self.paste_items(QPointF(10, 10))
        QApplication.clipboard().setText(old)
        self.push_undo_state()

    # -------------------------------------------------------------------------
    # ARRAY (Sprint J)

    def array_items(self, params: dict):
        """
        Duplicate selected items in a linear or polar array.

        params keys
        -----------
        mode : "linear" | "polar"

        Linear:
          rows, cols        : int
          x_spacing         : float  (scene units per column)
          y_spacing         : float  (scene units per row)

        Polar:
          cx, cy            : float  (centre of rotation in scene coords)
          count             : int    (total number of copies incl. original)
          total_angle       : float  (degrees, e.g. 360 for full circle)
          rotate_items      : bool   (rotate geometry orientation; Nodes only)
        """
        items = self.selectedItems()
        if not items:
            return

        # Serialise selected items
        def _serialise(item):
            if isinstance(item, Node):
                sprinkler = item.sprinkler.get_properties() if item.has_sprinkler() else None
                pipes_d = []
                for p in item.pipes:
                    other = p.node1 if p.node2 == item else p.node2
                    pipes_d.append({"x": other.pos().x(), "y": other.pos().y()})
                return {"type": "node", "x": item.pos().x(), "y": item.pos().y(),
                        "sprinkler": sprinkler, "pipes": pipes_d}
            elif hasattr(item, "to_dict"):
                return item.to_dict()
            return None

        data = [d for item in items if (d := _serialise(item)) is not None]
        if not data:
            return

        old_clip = QApplication.clipboard().text()

        mode = params.get("mode", "linear")

        if mode == "linear":
            rows = max(1, int(params.get("rows", 1)))
            cols = max(1, int(params.get("cols", 1)))
            xs   = float(params.get("x_spacing", 100))
            ys   = float(params.get("y_spacing", 100))

            QApplication.clipboard().setText(json.dumps(data))
            for r in range(rows):
                for c in range(cols):
                    if r == 0 and c == 0:
                        continue  # skip the original position
                    self.paste_items(QPointF(c * xs, r * ys))

        elif mode == "polar":
            cx    = float(params.get("cx", 0))
            cy    = float(params.get("cy", 0))
            count = max(2, int(params.get("count", 4)))
            ta    = float(params.get("total_angle", 360))
            # angle step
            if abs(ta - 360) < 0.01:
                step = math.radians(ta / count)
            else:
                step = math.radians(ta / (count - 1))

            for i in range(1, count):
                angle = step * i
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                rotated = []
                for obj in data:
                    rot = dict(obj)
                    if "x" in rot and "y" in rot:
                        ox, oy = rot["x"] - cx, rot["y"] - cy
                        rot["x"] = cx + ox * cos_a - oy * sin_a
                        rot["y"] = cy + ox * sin_a + oy * cos_a
                    # Rotate geometry point pairs
                    for key in ("pt1", "pt2"):
                        if key in rot:
                            ox = rot[key][0] - cx
                            oy = rot[key][1] - cy
                            rot[key] = [
                                cx + ox * cos_a - oy * sin_a,
                                cy + ox * sin_a + oy * cos_a,
                            ]
                    # Rotate circle centre
                    for cx_k, cy_k in (("cx", "cy"),):
                        if cx_k in rot and cy_k in rot:
                            ox = rot[cx_k] - cx
                            oy = rot[cy_k] - cy
                            rot[cx_k] = cx + ox * cos_a - oy * sin_a
                            rot[cy_k] = cy + ox * sin_a + oy * cos_a
                    # Rotate polyline vertices
                    if "points" in rot:
                        new_pts = []
                        for px, py in rot["points"]:
                            ox, oy = px - cx, py - cy
                            new_pts.append([cx + ox * cos_a - oy * sin_a,
                                            cy + ox * sin_a + oy * cos_a])
                        rot["points"] = new_pts
                    rotated.append(rot)
                QApplication.clipboard().setText(json.dumps(rotated))
                self.paste_items(QPointF(0, 0))

        QApplication.clipboard().setText(old_clip)
        self.push_undo_state()

    # -------------------------------------------------------------------------
    # ROTATE SELECTED (Sprint M recovery)

    def rotate_selected_items(self):
        """Rotate selected items by a user-specified angle around their centroid."""
        items = self.selectedItems()
        if not items:
            return
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QFormLayout,
            QDoubleSpinBox, QDialogButtonBox,
        )
        dlg = QDialog()
        dlg.setWindowTitle("Rotate")
        form = QFormLayout()
        a_spin = QDoubleSpinBox()
        a_spin.setRange(-360, 360)
        a_spin.setDecimals(2)
        a_spin.setValue(90)
        a_spin.setSuffix("  °")
        form.addRow("Angle:", a_spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        outer = QVBoxLayout(dlg)
        outer.addLayout(form)
        outer.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        angle = a_spin.value()
        angle_rad = math.radians(angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Compute centroid of all selected items
        xs, ys = [], []
        for item in items:
            pos = item.scenePos()
            xs.append(pos.x())
            ys.append(pos.y())
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)

        for item in items:
            if isinstance(item, Node):
                ox = item.scenePos().x() - cx
                oy = item.scenePos().y() - cy
                nx = cx + ox * cos_a - oy * sin_a
                ny = cy + ox * sin_a + oy * cos_a
                item.setPos(nx, ny)
                item.fitting.update()
            elif isinstance(item, (LineItem, PolylineItem, RectangleItem,
                                   CircleItem, ConstructionLine)):
                if hasattr(item, '_pt1') and hasattr(item, '_pt2'):
                    # LineItem or ConstructionLine
                    for attr in ('_pt1', '_pt2'):
                        pt = getattr(item, attr)
                        ox, oy = pt.x() - cx, pt.y() - cy
                        setattr(item, attr, QPointF(
                            cx + ox * cos_a - oy * sin_a,
                            cy + ox * sin_a + oy * cos_a))
                    if isinstance(item, LineItem):
                        item.setLine(item._pt1.x(), item._pt1.y(),
                                     item._pt2.x(), item._pt2.y())
                    elif isinstance(item, ConstructionLine):
                        item._recompute_line()
                elif isinstance(item, PolylineItem):
                    item._points = [
                        QPointF(cx + (p.x() - cx) * cos_a - (p.y() - cy) * sin_a,
                                cy + (p.x() - cx) * sin_a + (p.y() - cy) * cos_a)
                        for p in item._points
                    ]
                    item._rebuild_path()
                elif isinstance(item, CircleItem):
                    ox = item._center.x() - cx
                    oy = item._center.y() - cy
                    item._center = QPointF(
                        cx + ox * cos_a - oy * sin_a,
                        cy + ox * sin_a + oy * cos_a)
                    r = item._radius
                    item.setRect(item._center.x() - r, item._center.y() - r,
                                 2 * r, 2 * r)
                elif isinstance(item, RectangleItem):
                    # Rotate all four corners and rebuild
                    rect = item.rect()
                    corners = [
                        QPointF(rect.left(), rect.top()),
                        QPointF(rect.right(), rect.top()),
                        QPointF(rect.right(), rect.bottom()),
                        QPointF(rect.left(), rect.bottom()),
                    ]
                    rotated = []
                    for c in corners:
                        ox, oy = c.x() - cx, c.y() - cy
                        rotated.append(QPointF(
                            cx + ox * cos_a - oy * sin_a,
                            cy + ox * sin_a + oy * cos_a))
                    xs_r = [p.x() for p in rotated]
                    ys_r = [p.y() for p in rotated]
                    item.setRect(QRectF(
                        QPointF(min(xs_r), min(ys_r)),
                        QPointF(max(xs_r), max(ys_r))))
        self.push_undo_state()

    # -------------------------------------------------------------------------
    # GRIP HELPERS (Sprint I)

    def _find_grip_hit(self, pos: QPointF):
        """
        Return *(item, grip_index)* if *pos* is within 8 screen pixels of any
        grip handle on a selected item, else *None*.
        """
        views = self.views()
        if not views:
            return None
        scale = views[0].transform().m11()
        tol   = 8.0 / max(scale, 1e-6)   # 8 viewport px → scene units

        for item in self.selectedItems():
            if not hasattr(item, "grip_points"):
                continue
            for idx, gpt in enumerate(item.grip_points()):
                if math.hypot(pos.x() - gpt.x(), pos.y() - gpt.y()) <= tol:
                    return (item, idx)
        return None