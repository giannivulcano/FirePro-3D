import sys, json
import ezdxf
from PyQt6.QtWidgets import (QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
                              QGraphicsItem, QGraphicsPixmapItem, QGraphicsTextItem, QApplication)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QSize
from PyQt6.QtGui import QPen, QBrush, QColor, QPixmap
from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from node import Node
from pipe import Pipe
from sprinkler import Sprinkler
from sprinkler_system import SprinklerSystem
from CAD_Math import CAD_Math
from Annotations import Annotation, DimensionAnnotation, NoteAnnotation
from underlay import Underlay


class Model_Space(QGraphicsScene):
    SNAP_RADIUS = 10
    SAVE_VERSION = 1
    requestPropertyUpdate = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self.underlays: list[tuple[Underlay, QGraphicsItem]] = []  # (data, scene_item)
        self.mode = None
        self.units_per_meter = 10000
        self.dimension_start = None
        self.node_start_pos = None
        self.node_end_pos = None
        self._selected_items = None
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()

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
                data.scale = item.scale() if hasattr(item, "scale") else 1.0
            underlays_data.append(data.to_dict())

        # --- Assemble and write ---
        payload = {
            "version":     self.SAVE_VERSION,
            "units_per_meter": self.units_per_meter,
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

        self.units_per_meter = payload.get("units_per_meter", 10000)

        # --- Nodes ---
        id_to_node: dict[int, Node] = {}
        for entry in payload.get("nodes", []):
            node = self.add_node(entry["x"], entry["y"])
            id_to_node[entry["id"]] = node
            if entry.get("sprinkler"):
                template = Sprinkler(None)
                for key, value in entry["sprinkler"].items():
                    # stored as {key: {"type":..,"value":..}} OR {key: value} depending on version
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

        print(f"✅ Loaded from {filename}")

    def _clear_scene(self):
        """Remove all user content, keeping preview items and origin markers."""
        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self.underlays = []
        self.clear()
        # Restore items that clear() destroyed
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()

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
        for item in self.selectedItems():
            if isinstance(item, Pipe):
                self.delete_pipe(item)
        for item in self.selectedItems():
            if isinstance(item, Node):
                if item.has_sprinkler():
                    self.remove_sprinkler(item)
                for pipe in item.pipes:
                    self.delete_pipe(pipe)
        for item in self.selectedItems():
            if isinstance(item, Node):
                self.remove_node(item)

    # -------------------------------------------------------------------------
    # MODE MANAGEMENT

    def set_mode(self, mode, template=None):
        self.mode = mode
        print(f"Mode set to: {self.mode}")
        self.preview_node.hide()
        self.preview_pipe.hide()
        if self.node_start_pos is not None:
            self.remove_node(self.node_start_pos)
        if mode in ("sprinkler", "pipe"):
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
    # UNDERLAYS

    def import_dxf(self, file_path, color=QColor("white"), line_weight=0,
                   x=0.0, y=0.0, _record: Underlay = None):
        try:
            doc = ezdxf.readfile(file_path)
            msp = doc.modelspace()
        except Exception as e:
            print("❌ Failed to load DXF:", e)
            return

        pen = QPen(color, line_weight)
        imported_items = []

        for e in msp:
            try:
                if e.dxftype() == "LINE":
                    start = QPointF(e.dxf.start[0], -e.dxf.start[1])
                    end   = QPointF(e.dxf.end[0],   -e.dxf.end[1])
                    line  = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
                    line.setPen(pen)
                    line.setZValue(-100)
                    imported_items.append(line)

                elif e.dxftype() == "CIRCLE":
                    r = e.dxf.radius
                    cx, cy = e.dxf.center.x, e.dxf.center.y
                    circle = QGraphicsEllipseItem(cx - r, -cy - r, 2 * r, 2 * r)
                    circle.setPen(pen)
                    circle.setZValue(-100)
                    imported_items.append(circle)

                elif e.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                    points = [(p[0], -p[1]) for p in e.get_points()]
                    for i in range(len(points) - 1):
                        x1, y1 = points[i]
                        x2, y2 = points[i + 1]
                        pline = QGraphicsLineItem(x1, y1, x2, y2)
                        pline.setPen(pen)
                        pline.setZValue(-100)
                        imported_items.append(pline)

                elif e.dxftype() == "TEXT":
                    pos = e.dxf.insert
                    text_item = QGraphicsTextItem(e.dxf.text)
                    text_item.setPos(pos[0], -pos[1])
                    text_item.setDefaultTextColor(color)
                    text_item.setZValue(-100)
                    imported_items.append(text_item)

            except Exception as inner:
                print(f"⚠️ Skipped entity {e.dxftype()} due to:", inner)

        if imported_items:
            for item in imported_items:
                self.addItem(item)
            group = self.createItemGroup(imported_items)
            group.setZValue(-100)
            group.setPos(x, y)
            group.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            )
            group.setData(0, "DXF Underlay")

            # Register in underlay list
            record = _record or Underlay(
                type="dxf", path=file_path, x=x, y=y,
                colour=color.name(), line_weight=line_weight
            )
            self.underlays.append((record, group))
            print(f"✅ Imported DXF: {file_path}")

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

            # Register in underlay list
            record = _record or Underlay(
                type="pdf", path=file_path,
                x=item.pos().x(), y=item.pos().y(),
                dpi=dpi, page=page
            )
            self.underlays.append((record, item))
            print(f"✅ Imported PDF '{file_path}' page {page} at {dpi} DPI")

        except Exception as e:
            print("❌ Error importing PDF:", e)

    # -------------------------------------------------------------------------
    # GEOMETRY HELPERS

    def get_snapped_position(self, x, y):
        grid = 10
        return QPointF(round(x / grid) * grid, round(y / grid) * grid)

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
        snapped = self.get_snapped_position(scene_pos.x(), scene_pos.y())

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
        snapped   = self.get_snapped_position(scene_pos.x(), scene_pos.y())

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

        elif self.mode == "dimension":
            if self.dimension_start is None:
                self.dimension_start = snapped
            else:
                dim = DimensionAnnotation(self.dimension_start, snapped)
                self.addItem(dim)
                self.annotations.add_dimension(dim)
                self.requestPropertyUpdate.emit(dim)
                self.dimension_start = None

        elif self.mode in ("paste", "move"):
            if self.node_start_pos is None:
                self.node_start_pos = snapped
            else:
                offset = CAD_Math.get_vector(self.node_start_pos, snapped)
                if self.mode == "paste":
                    self.paste_items(offset)
                elif self.mode == "move":
                    self.move_items(offset)
                self.node_start_pos = None
                self.set_mode(None)
                return

        elif self.mode is None:
            if isinstance(selection, Node):
                print(selection)
                print(f"node has: {len(selection.pipes)} pipes connected")

        super().mousePressEvent(event)

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