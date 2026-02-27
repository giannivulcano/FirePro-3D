""" UPDATES
- On selection highlight handles
- add handle to centerline

"""

# annotations.py
import math
from CAD_Math import CAD_Math
from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsLineItem, QGraphicsPolygonItem, QGraphicsEllipseItem 
from PyQt6.QtGui import QPen, QColor, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QLineF

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


class NoteAnnotation(QGraphicsTextItem, Annotation):
    """A text note placed on the drawing."""
    def __init__(self, text="Note", x=0, y=0):
        QGraphicsTextItem.__init__(self, text)
        Annotation.__init__(self)
        self.setDefaultTextColor(Qt.GlobalColor.white)
        self.setPos(x, y)

        self._properties.update({
            "Text": {"type": "string", "value": text},
            "FontSize": {"type": "string", "value": "12"},
        })

    def set_property(self, key, value):
        super().set_property(key, value)
        if key == "Text":
            self.setPlainText(value)
        elif key == "FontSize":
            self.setFont(self.font().setPointSize(int(value)))

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

        # Styling
        self.pen = QPen(QColor(self._properties["Colour"]["value"]), 
                        float(self._properties["Line Weight"]["value"]), 
                        Qt.PenStyle.SolidLine)
        self.setPen(self.pen)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(0)

        # Label
        self.label = QGraphicsTextItem(parent=self)
        self.label.setZValue(100)

        # Arrows
        self.arrow1 = QGraphicsPolygonItem(self)
        self.arrow1.setZValue(0)
        self.arrow2 = QGraphicsPolygonItem(self)
        self.arrow2.setZValue(0)

        # Witness lines
        self.witness1 = QGraphicsLineItem(self)
        self.witness1.setPen(self.pen)
        self.witness1.setZValue(0)
        self.witness2 = QGraphicsLineItem(self)
        self.witness2.setPen(self.pen)
        self.witness2.setZValue(0)

        # Handles
        self.handle1 = Handle(self, p1.x(), p1.y())
        self.handle1.setTransformOriginPoint(self.handle1.boundingRect().center())
        self.handle1.setVisible(True)
        self.handle2 = Handle(self, p2.x(), p2.y())
        self.handle2.setTransformOriginPoint(self.handle2.boundingRect().center())
        self.handle2.setVisible(True)
        center_point = self.line().center()
        self.handle3 = Handle(self, center_point.x(), center_point.y())
        self.handle3.setVisible(True)
        self.handle3.setTransformOriginPoint(self.handle3.boundingRect().center())

        self.update_geometry()

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
        elif key == "Color":
            self.setPen(QPen(QColor(value.lower()), 1))
        elif key in ("Witness Length", "Offset"):
            self.update_geometry()

    def update_geometry(self):
        """Recalculate line, arrows, label, and witness lines based on handle positions."""
        p1 = self.handle1.scenePos()
        p2 = self.handle2.scenePos()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())

        self.update_arrows_and_witness()
        self.update_label()

    def rescale(self, sm=None) -> None:
        """Re-draw with updated scale-aware sizes (called after calibration)."""
        self.update_geometry()

    def update_label(self):
        length = self.line().length()
        scene = self.scene()
        if scene and hasattr(scene, "scale_manager"):
            self.label.setPlainText(scene.scale_manager.scene_to_display(length))
        else:
            self.label.setPlainText(f"{length:.1f} px")
        self.set_label_position()

    def set_label_position(self):
        line = self.line()  # QLineF
    
        v1 = CAD_Math.get_unit_vector(line.p1(),line.p2())
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

        # move label so its center sits on line midpoint
        self.label.setPos(mid_point - center)
        self.label.setRotation(angle)

    def update_arrows_and_witness(self):
        # Scale-aware sizes
        sm = getattr(self.scene(), "scale_manager", None) if self.scene() else None
        if sm and sm.is_calibrated:
            arrow_size = sm.paper_to_scene(1.5)   # 1.5mm arrow on paper
            witness_len = sm.paper_to_scene(8.0)  # 8mm witness line on paper
            offset_gap = sm.paper_to_scene(1.5)   # 1.5mm gap between dim line and annotation line
            offset_dist = sm.paper_to_scene(2.0)  # 2mm start offset from point
        else:
            arrow_size = 6
            witness_len = float(self._properties["Witness Length"]["value"])
            offset_gap = 5
            offset_dist = float(self._properties["Offset"]["value"])

        # Original line
        line = self.line()
        angle = math.atan2(line.dy(), line.dx())  # line angle
        perp_angle = angle + math.pi / 2          # perpendicular angle

        # Perpendicular unit vector
        dx_perp = math.cos(perp_angle)
        dy_perp = math.sin(perp_angle)

        # Start witness line
        start = QPointF(self.handle1.x(), self.handle1.y())
        p1a = start + QPointF(dx_perp * offset_dist, dy_perp * offset_dist)
        p1b = p1a + QPointF(dx_perp * witness_len, dy_perp * witness_len)
        self.witness1.setLine(p1a.x(), p1a.y(), p1b.x(), p1b.y())

        # End witness line
        end = QPointF(self.handle2.x(), self.handle2.y())
        p2a = end + QPointF(dx_perp * offset_dist, dy_perp * offset_dist)
        p2b = p2a + QPointF(dx_perp * witness_len, dy_perp * witness_len)
        self.witness2.setLine(p2a.x(), p2a.y(), p2b.x(), p2b.y())

        # Create new offset line
        ox = dx_perp * offset_gap
        oy = dy_perp * offset_gap
        p1 = p1b - QPointF(ox, oy)
        p2 = p2b - QPointF(ox, oy)
        offset_line = QLineF(p1, p2)

        # Apply to the QGraphicsLineItem
        self.setLine(offset_line)

        # Arrows
        points = [QPointF(0, 0), QPointF(-arrow_size, arrow_size/2), QPointF(-arrow_size, -arrow_size/2)]
        poly = QPolygonF(points)
        self.arrow1.setPolygon(poly)
        self.arrow1.setRotation(CAD_Math.get_vector_angle(p1,p2)+90)
        self.arrow1.setPos(p1.x(),p1.y())
        self.arrow1.setPen(self.pen)

        self.arrow2.setPolygon(poly)
        self.arrow2.setRotation(CAD_Math.get_vector_angle(p2,p1)+90)
        self.arrow2.setPos(p2.x(),p2.y())
        self.arrow2.setPen(self.pen)

        #update handle 3
        center_point = self.line().center()
        #self.handle3.setPos(center_point)  # QPointF directly

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