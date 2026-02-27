import sys, json, math
from PyQt6.QtWidgets import (QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
                              QGraphicsItem, QGraphicsItemGroup, QGraphicsPixmapItem,
                              QGraphicsTextItem, QGraphicsPathItem, QApplication,
                              QProgressDialog)
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
import os


class Model_Space(QGraphicsScene):
    SNAP_RADIUS = 10
    SAVE_VERSION = 3
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
        self.preview_pipe.setZValue(5)
        self.addItem(self.preview_pipe)
        self.preview_pipe.hide()

    def init_preview_node(self):
        self.preview_node = QGraphicsEllipseItem(0, 0, 10, 10)
        self.preview_node.setBrush(QBrush(QColor(0, 0, 255, 100)))
        self.preview_node.setPen(QPen(Qt.GlobalColor.blue))
        self.preview_node.setZValue(10)
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
                "id": node_id[node],
                "x":  node.scenePos().x(),
                "y":  node.scenePos().y(),
                "sprinkler": node.sprinkler.get_properties() if node.has_sprinkler() else None,
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

        # --- Assemble and write ---
        payload = {
            "version":     self.SAVE_VERSION,
            "scale":       self.scale_manager.to_dict(),
            "nodes":       nodes_data,
            "pipes":       pipes_data,
            "annotations": annotations_data,
            "underlays":   underlays_data,
        }
        with open(filename, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"✅ Saved to {filename}")

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

        # --- Nodes ---
        id_to_node: dict[int, Node] = {}
        for entry in payload.get("nodes", []):
            node = self.add_node(entry["x"], entry["y"])
            id_to_node[entry["id"]] = node
            if entry.get("sprinkler"):
                template = Sprinkler(None)
                for key, value in entry["sprinkler"].items():
                    if isinstance(value, dict):
                        template.set_property(key, value["value"])
                    else:
                        template.set_property(key, value)
                self.add_sprinkler(node, template)

        # --- Pipes ---
        for entry in payload.get("pipes", []):
            n1 = id_to_node.get(entry["node1_id"])
            n2 = id_to_node.get(entry["node2_id"])
            if n1 and n2:
                pipe = self.add_pipe(n1, n2)
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
        if self.node_start_pos is not None:
            self.remove_node(self.node_start_pos)
        if mode in ("sprinkler", "pipe", "set_scale"):
            self.current_template = template
            if template:
                self.requestPropertyUpdate.emit(template)
        else:
            self.current_template = None

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
                "id": node_id[node],
                "x":  node.scenePos().x(),
                "y":  node.scenePos().y(),
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
        return {"nodes": nodes_data, "pipes": pipes_data, "annotations": annotations_data}

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
            self.sprinkler_system = SprinklerSystem()
            self.annotations = Annotation()

            id_to_node: dict[int, Node] = {}
            for entry in state.get("nodes", []):
                node = Node(entry["x"], entry["y"])
                self.addItem(node)
                self.sprinkler_system.add_node(node)
                id_to_node[entry["id"]] = node
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
    # GEOMETRY HELPERS

    def get_snapped_position(self, x, y):
        grid = 10
        return QPointF(round(x / grid) * grid, round(y / grid) * grid)

    def get_effective_position(self, scene_pos: QPointF) -> QPointF:
        """Return the best-fit cursor position: underlay snap > grid snap."""
        if self._snap_to_underlay:
            snap_pt = self.find_snap_point(scene_pos)
            if snap_pt is not None:
                return snap_pt
        return self.get_snapped_position(scene_pos.x(), scene_pos.y())

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

        elif self.mode in ("sprinkler", "dimension", "paste", "move"):
            self.update_preview_node(snapped)
            self.preview_pipe.hide()
        else:
            self.preview_node.hide()
            self.preview_pipe.hide()

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

        elif self.mode is None:
            if isinstance(selection, Node):
                print(selection)
                print(f"node has: {len(selection.pipes)} pipes connected")

        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu for underlays on right-click."""
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else __import__('PyQt6.QtGui', fromlist=['QTransform']).QTransform())

        # Walk up parent chain to find if this item belongs to an underlay group
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
        elif event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.clipboard_data():
                self.set_mode("paste")
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
        QApplication.clipboard().setText(json.dumps(data))

    def paste_items(self, offset):
        data = self.clipboard_data()
        for obj in data:
            if obj["type"] == "node":
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

    def move_items(self, offset):
        for item in self._selected_items:
            if isinstance(item, Node):
                item.moveBy(offset.x(), offset.y())
                item.setSelected(True)
                item.fitting.update()

    def clipboard_data(self):
        text = QApplication.clipboard().text()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None