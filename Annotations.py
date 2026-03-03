""" UPDATES
- On selection highlight handles
- add handle to centerline
- Sprint Q: tick marks, label above line, draggable offset, text overhaul

"""

# annotations.py
import math
from CAD_Math import CAD_Math
from PyQt6.QtWidgets import (
    QGraphicsTextItem, QGraphicsLineItem,
    QGraphicsPolygonItem, QGraphicsEllipseItem,
)
from PyQt6.QtGui import QPen, QColor, QPolygonF, QFont, QPainter, QTextOption
from PyQt6.QtCore import Qt, QPointF, QLineF, QRectF

class Annotation:
    """Base class for CAD annotations."""

    def __init__(self):
        self._properties = {
            "Layer": {"type": "enum", "options": ["Default", "Notes", "Dimensions"], "value": "Default"},
            "Color": {"type": "enum", "options": ["Black", "Red", "Blue"], "value": "Black"},
        }
        self.dimensions = [] #list of dimensions
        self.notes = [] #list of notes
        self.base_point_A = None
        self.base_point_B = None


    def get_properties(self):
        return self._properties

    def set_property(self, key, value):
        if key in self._properties:
            self._properties[key]["value"] = value

    def add_dimension(self, dim):
        self.dimensions.append(dim)

    def add_note(self, note):
        self.notes.append(note)


# ═════════════════════════════════════════════════════════════════════════════
# NoteAnnotation — MText-like text annotation
# ═════════════════════════════════════════════════════════════════════════════

class NoteAnnotation(QGraphicsTextItem, Annotation):
    """A text note placed on the drawing.  Supports multiline word-wrap,
    bold/italic, and alignment when a text_width is set."""

    def __init__(self, text="Note", x=0, y=0, text_width=0):
        QGraphicsTextItem.__init__(self, text)
        Annotation.__init__(self)
        self.setDefaultTextColor(Qt.GlobalColor.white)
        self.setPos(x, y)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, True)

        # Enable word wrap if width was specified
        if text_width > 0:
            self.setTextWidth(text_width)

        self._properties.update({
            "Text":      {"type": "string", "value": text},
            "FontSize":  {"type": "string", "value": "12"},
            "Bold":      {"type": "enum", "options": ["Off", "On"], "value": "Off"},
            "Italic":    {"type": "enum", "options": ["Off", "On"], "value": "Off"},
            "Alignment": {"type": "enum",
                          "options": ["Left", "Center", "Right"],
                          "value": "Left"},
        })

    # ── property dispatch ─────────────────────────────────────────────────

    def set_property(self, key, value):
        super().set_property(key, value)
        if key == "Text":
            self.setPlainText(value)
        elif key == "FontSize":
            try:
                f = self.font()
                f.setPointSize(int(value))
                self.setFont(f)
            except (ValueError, TypeError):
                pass
        elif key == "Bold":
            f = self.font()
            f.setBold(value == "On")
            self.setFont(f)
        elif key == "Italic":
            f = self.font()
            f.setItalic(value == "On")
            self.setFont(f)
        elif key == "Alignment":
            opt = self.document().defaultTextOption()
            _map = {
                "Left":   Qt.AlignmentFlag.AlignLeft,
                "Center": Qt.AlignmentFlag.AlignCenter,
                "Right":  Qt.AlignmentFlag.AlignRight,
            }
            opt.setAlignment(_map.get(value, Qt.AlignmentFlag.AlignLeft))
            self.document().setDefaultTextOption(opt)

    # ── visual editing frame ──────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.hasFocus():
            pen = QPen(QColor("#88aaff"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())


# ═════════════════════════════════════════════════════════════════════════════
# DimensionAnnotation — AutoCAD-style linear dimension
# ═════════════════════════════════════════════════════════════════════════════

class DimensionAnnotation(QGraphicsLineItem, Annotation):
    def __init__(self, p1: QPointF, p2: QPointF):
        super().__init__(p1.x(), p1.y(), p2.x(), p2.y())

        # Properties
        self._properties = {
            "Text Size": {"type": "string", "value": "10"},
            "Colour": {"type": "enum", "options": ["Black", "Red", "Blue", "White"], "value": "White"},
            "Line Weight": {"type": "enum", "options": ["2", "4", "6"], "value": "2"},
            "Witness Length": {"type": "string", "value": "20"},
            "Offset": {"type": "string", "value": "10"},
        }

        # Draggable perpendicular offset distance (scene units)
        self._offset_dist = float(self._properties["Offset"]["value"])
        self._perp_angle = 0.0     # stored by update_arrows_and_witness
        self._updating = False     # recursion guard

        # Styling — cosmetic pen so dimension lines stay visible at any zoom
        self._dim_pen = QPen(QColor(self._properties["Colour"]["value"]),
                        float(self._properties["Line Weight"]["value"]),
                        Qt.PenStyle.SolidLine)
        self._dim_pen.setCosmetic(True)
        self.setPen(self._dim_pen)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(self.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(0)

        # Label — 12pt, zoom-independent so it's always readable
        self.label = QGraphicsTextItem(parent=self)
        self.label.setZValue(100)
        self.label.setFlag(self.label.GraphicsItemFlag.ItemIgnoresTransformations, True)
        label_font = QFont("Consolas", 12)
        self.label.setFont(label_font)
        self.label.setDefaultTextColor(QColor(self._properties["Colour"]["value"]))

        # Tick marks (45-degree slashes at each end of dimension line)
        self.tick1 = QGraphicsLineItem(self)
        self.tick1.setPen(self._dim_pen)
        self.tick1.setZValue(0)
        self.tick2 = QGraphicsLineItem(self)
        self.tick2.setPen(self._dim_pen)
        self.tick2.setZValue(0)

        # Witness lines
        self.witness1 = QGraphicsLineItem(self)
        self.witness1.setPen(self._dim_pen)
        self.witness1.setZValue(0)
        self.witness2 = QGraphicsLineItem(self)
        self.witness2.setPen(self._dim_pen)
        self.witness2.setZValue(0)

        # Handles — hidden by default, shown when dimension is selected
        self.handle1 = Handle(self, p1.x(), p1.y())
        self.handle1.setTransformOriginPoint(self.handle1.boundingRect().center())
        self.handle1.setVisible(False)
        self.handle2 = Handle(self, p2.x(), p2.y())
        self.handle2.setTransformOriginPoint(self.handle2.boundingRect().center())
        self.handle2.setVisible(False)
        center_point = self.line().center()
        self.handle3 = Handle(self, center_point.x(), center_point.y())
        self.handle3.setVisible(False)
        self.handle3.setTransformOriginPoint(self.handle3.boundingRect().center())

        self.update_geometry()

    # ── Selection → handle visibility ─────────────────────────────────────

    def itemChange(self, change, value):
        if change == self.GraphicsItemChange.ItemSelectedHasChanged:
            vis = bool(value)
            self.handle1.setVisible(vis)
            self.handle2.setVisible(vis)
            self.handle3.setVisible(vis)
        elif change == self.GraphicsItemChange.ItemPositionHasChanged:
            self.update_geometry()
        return super().itemChange(change, value)

    # ---------------------------------|
    # Helpers -------------------------|

    def get_properties(self):
        return self._properties

    def set_property(self, key, value):
        if key in self._properties:
            self._properties[key]["value"] = value
        if key == "Text Size":
            font = self.label.font()
            font.setPointSize(int(value))
            self.label.setFont(font)
        elif key == "Colour":
            _color_map = {"Black": "#000000", "Red": "#ff0000", "Blue": "#0000ff", "White": "#ffffff"}
            c = _color_map.get(value, value.lower())
            self._dim_pen = QPen(QColor(c), float(self._properties["Line Weight"]["value"]))
            self._dim_pen.setCosmetic(True)
            self.setPen(self._dim_pen)
            self.label.setDefaultTextColor(QColor(c))
            self.tick1.setPen(self._dim_pen)
            self.tick2.setPen(self._dim_pen)
            self.witness1.setPen(self._dim_pen)
            self.witness2.setPen(self._dim_pen)
        elif key in ("Witness Length", "Offset"):
            if key == "Offset":
                self._offset_dist = float(value)
            self.update_geometry()

    def update_geometry(self):
        """Recalculate line, ticks, label, and witness lines based on handle positions."""
        if self._updating:
            return
        self._updating = True
        try:
            p1 = self.handle1.scenePos()
            p2 = self.handle2.scenePos()

            # Derive offset distance from handle3 if it has been dragged
            h3 = self.handle3.scenePos()
            mid_base = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            line_angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            perp = line_angle + math.pi / 2
            # Project handle3 offset vector onto perpendicular direction
            dx = h3.x() - mid_base.x()
            dy = h3.y() - mid_base.y()
            projected = dx * math.cos(perp) + dy * math.sin(perp)
            if abs(projected) > 1e-3:
                self._offset_dist = projected

            self.setLine(p1.x(), p1.y(), p2.x(), p2.y())
            self.update_arrows_and_witness()
            self.update_label()
        finally:
            self._updating = False

    def rescale(self, sm=None) -> None:
        """Re-draw with updated scale-aware sizes (called after calibration)."""
        self.update_geometry()

    def update_label(self):
        # Compute display length from handle1 → handle2 (the measurement, not the offset line)
        p1 = self.handle1.scenePos()
        p2 = self.handle2.scenePos()
        length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        scene = self.scene()
        if scene and hasattr(scene, "scale_manager"):
            self.label.setPlainText(scene.scale_manager.scene_to_display(length))
        else:
            self.label.setPlainText(f"{length:.1f} px")
        self.set_label_position()

    def set_label_position(self):
        line = self.line()  # QLineF — the offset dimension line

        v1 = CAD_Math.get_unit_vector(line.p1(), line.p2())
        # If pointing left, flip direction
        if v1.x() < 0:
            v1 = QPointF(-v1.x(), -v1.y())
        v2 = QPointF(1, 0)
        angle = -CAD_Math.get_angle_between_vectors(v1, v2, signed=True)
        if angle == 90:
            angle = -90

        mid_point = QPointF((line.x1() + line.x2()) / 2, (line.y1() + line.y2()) / 2)
        bounds = self.label.boundingRect()
        center = bounds.center()

        # set transform origin so future rotations work around the center
        self.label.setTransformOriginPoint(center)

        # Because ItemIgnoresTransformations is set, boundingRect() is in
        # device pixels.  Convert to scene units by dividing by view scale.
        views = self.scene().views() if self.scene() else []
        view_scale = abs(views[0].transform().m11()) if views else 1.0
        scene_center_x = center.x() / view_scale
        scene_bounds_h = bounds.height() / view_scale

        # Offset label ABOVE the line (perpendicular direction)
        label_gap = 4.0 / view_scale   # 4 screen-px gap

        # Use the same perpendicular direction as the witness lines
        perp_dx = math.cos(self._perp_angle)
        perp_dy = math.sin(self._perp_angle)
        # Offset the label so its bottom edge sits above the line
        offset = QPointF(perp_dx * label_gap, perp_dy * label_gap)
        label_pos = mid_point + offset - QPointF(scene_center_x, scene_bounds_h)
        self.label.setPos(label_pos)
        self.label.setRotation(angle)

    def update_arrows_and_witness(self):
        # Scale-aware sizes
        sm = getattr(self.scene(), "scale_manager", None) if self.scene() else None
        if sm and sm.is_calibrated:
            tick_size = sm.paper_to_scene(1.5)    # 1.5mm tick on paper
            offset_gap = sm.paper_to_scene(1.0)   # 1mm gap at measurement point
            witness_ext = sm.paper_to_scene(2.0)  # 2mm extension past dimension line
        else:
            tick_size = 6
            offset_gap = 3
            witness_ext = 6  # extend witness lines past dimension line

        # Measurement endpoints from handles
        start = QPointF(self.handle1.x(), self.handle1.y())
        end = QPointF(self.handle2.x(), self.handle2.y())

        # Line angle and perpendicular
        line = QLineF(start, end)
        angle = math.atan2(line.dy(), line.dx())
        perp_angle = angle + math.pi / 2
        self._perp_angle = perp_angle  # store for label positioning

        dx_perp = math.cos(perp_angle)
        dy_perp = math.sin(perp_angle)

        # Dimension line offset from measurement baseline
        offset = self._offset_dist

        # Witness lines: from near measurement point to past the dimension line
        w1_start = start + QPointF(dx_perp * offset_gap, dy_perp * offset_gap)
        w1_end   = start + QPointF(dx_perp * (offset + offset_gap + witness_ext),
                                    dy_perp * (offset + offset_gap + witness_ext))
        self.witness1.setLine(w1_start.x(), w1_start.y(), w1_end.x(), w1_end.y())

        w2_start = end + QPointF(dx_perp * offset_gap, dy_perp * offset_gap)
        w2_end   = end + QPointF(dx_perp * (offset + offset_gap + witness_ext),
                                  dy_perp * (offset + offset_gap + witness_ext))
        self.witness2.setLine(w2_start.x(), w2_start.y(), w2_end.x(), w2_end.y())

        # Dimension line endpoints (at offset distance from measurement points)
        p1 = start + QPointF(dx_perp * offset, dy_perp * offset)
        p2 = end   + QPointF(dx_perp * offset, dy_perp * offset)
        self.setLine(QLineF(p1, p2))

        # Tick marks — 45-degree slashes at each end of the dimension line
        tick_angle = angle + math.pi / 4
        dx_tick = math.cos(tick_angle) * tick_size
        dy_tick = math.sin(tick_angle) * tick_size
        self.tick1.setLine(p1.x() - dx_tick, p1.y() - dy_tick,
                           p1.x() + dx_tick, p1.y() + dy_tick)
        self.tick1.setPen(self._dim_pen)
        self.tick2.setLine(p2.x() - dx_tick, p2.y() - dy_tick,
                           p2.x() + dx_tick, p2.y() + dy_tick)
        self.tick2.setPen(self._dim_pen)

        # Reposition handle3 at midpoint of dimension line
        center_point = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        self.handle3.setPos(center_point)


class Handle(QGraphicsEllipseItem):
    """Draggable node for annotations."""
    def __init__(self, parent, x, y, radius=4):
        super().__init__(-radius, -radius, 2*radius, 2*radius, parent)
        self.setBrush(QColor("blue"))
        self.setPos(x, y)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def itemChange(self, change, value):
        if change == self.GraphicsItemChange.ItemPositionChange and self.parentItem():
            self.parentItem().update_geometry()
        return super().itemChange(change, value)
