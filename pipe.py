from math import floor
import math
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsItem, QGraphicsTextItem, QStyle
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtCore import Qt, QPointF
from CAD_Math import CAD_Math


class Pipe(QGraphicsLineItem):
    SNAP_TOLERANCE_DEG = 7.5  # snap if within this angle

    # Paper line-weight in mm for each "Line Weight" property value.
    # Used when the scene has a calibrated scale; otherwise PX_FALLBACK is used.
    LINE_WEIGHT_MM       = {"1": 0.35, "2": 0.50, "3": 0.70, "4": 1.00}
    LINE_WEIGHT_PX_FALLBACK = {"1": 5.0,  "2": 6.0,  "3": 7.0,  "4": 8.0}

    def __init__(self, node1, node2):

        super().__init__()
        # Properties
        self._properties = {
            "Diameter": {"type": "enum", "value": "Ø 2\"", "options": ["1\"Ø", "1-½\"Ø", "2\"Ø","3\"Ø","4\"Ø","5\"Ø","6\"Ø","8\"Ø"]},
            "Material" : {"type": "enum", "value": "Galvanized Steel", "options": ["Galvanized Steel", "Stainless Steel", "Black Steel","PVC"]},
            "Colour" : {"type": "enum", "value": "Red", "options": ["Black", "White", "Red", "Blue","Grey"]},
            "Line Weight" : {"type": "enum", "value": "1", "options": ["1", "2","3","4"]},
            "Phase" : {"type": "enum", "value": "New", "options": ["New", "Existing","Demo"]},
            "Show Label" : {"type": "enum", "value": "True", "options": ["True", "False"]},

        }

        self.node1 = node1
        self.node2 = node2
        self.colour = None
        self.length = 0.0


        self.label = QGraphicsTextItem("", self)  # Child of pipe

        #self.set_pipe_display()
        
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-100)
        
        # track node movement
        if node1 and node2:
            self.node1.pipes.append(self)
            self.node2.pipes.append(self)
            self.update_geometry()

    def set_pipe_display(self):
        colour = QColor(self._properties["Colour"]["value"]) #If you're storing names ("red") or hex codes, QColor handles both.
        line_weight = float(self._properties["Line Weight"]["value"])+4
        pen = QPen(colour, line_weight)
        self.setPen(pen)

    # --------------------------------------------
    # PIPE LABEL HELPERS
    def update_label(self, visible=None):
        if not self.node1 or not self.node2:
            return  # cannot position label yet
        
        if not hasattr(self, "label") or self.label is None:
            self.label = QGraphicsTextItem(parent=self)
            self.label.setDefaultTextColor(Qt.GlobalColor.black)
            self.label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        
        visible = True if self._properties["Show Label"]["value"] == "True" else False
        self.label.setVisible(visible)
        if not visible:
            return  # skip extra work if hidden

        # Format text
        diameter = self._properties.get('Diameter', {}).get('value', 'N/A')
        scene = self.scene()
        if scene and hasattr(scene, "scale_manager"):
            length = scene.scale_manager.scene_to_display(getattr(self, "length", 0.0))
        else:
            length = f"{self.length:.1f} px"

        html = f"<div style='text-align:center'>{diameter}<br>{length}</div>"
        self.label.setHtml(html)

        # Adjust width to match content for proper centering
        self.label.setTextWidth(self.label.boundingRect().width())

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

    # --------------------------------------------------------------
    # PIPE HELPERS

    def update_geometry(self):
        start = self.node1.scenePos()
        end = self.node2.scenePos()

        # Snap visually for the pipe line
        snapped_end = self.snap_point_45_if_close(start, end)
        self.setLine(start.x(), start.y(), snapped_end.x(), snapped_end.y())

        # Store the length
        self.length = CAD_Math.get_vector_length(self.node1.scenePos(),self.node2.scenePos())

        self.update_label()  # <- move here


    @classmethod
    def snap_point_45_if_close(cls, start: QPointF, end: QPointF) -> QPointF:
        dx = end.x() - start.x()
        dy = end.y() - start.y()

        angle = math.degrees(math.atan2(dy, dx))
        snap_angle = round(angle / 45) * 45

        # only snap if within tolerance
        if abs(angle - snap_angle) <= cls.SNAP_TOLERANCE_DEG:
            length = math.hypot(dx, dy)
            rad = math.radians(snap_angle)
            return QPointF(start.x() + length * math.cos(rad),
                           start.y() + length * math.sin(rad))
        else:
            return end
        
    def get_properties(self):
        return self._properties.copy()

    def set_property(self, key, value):
        if key in self._properties:
            self._properties[key]["value"] = value

            if key in ("Diameter","Show Label"):
                self.update_label()
            if key in ("Colour", "Line Weight"):
                self.set_pipe_display()
    
    def set_properties(self, template: "Pipe"):
        """Copy property values from a template sprinkler."""
        for key, meta in template.get_properties().items():
            self.set_property(key, meta["value"])

    def paint(self, painter, option, widget=None):
        colour = QColor(self._properties["Colour"]["value"])
        lw_key = self._properties["Line Weight"]["value"]
        sm = getattr(self.scene(), "scale_manager", None)
        if sm and sm.is_calibrated:
            line_weight = sm.paper_to_scene(self.LINE_WEIGHT_MM.get(lw_key, 0.5))
        else:
            line_weight = self.LINE_WEIGHT_PX_FALLBACK.get(lw_key, 6.0)
        base_pen = QPen(colour, line_weight)

        # normal draw
        painter.setPen(base_pen)
        painter.drawLine(self.line())

        # highlight if selected
        if self.isSelected():
            highlight_pen = QPen(colour, line_weight * 1.6)
            painter.setPen(highlight_pen)
            painter.drawLine(self.line())

            # also show node endpoints — scale-aware radius
            radius = sm.paper_to_scene(0.75) if sm and sm.is_calibrated else 6
            brush = QBrush(QColor("white"))
            painter.setBrush(brush)
            painter.setPen(Qt.PenStyle.NoPen)

            for node in (self.node1, self.node2):
                if node is not None:
                    pos = node.scenePos()
                    painter.drawEllipse(QPointF(pos.x(), pos.y()), radius, radius)


        # prevent the default dotted selection rect
        option.state &= ~QStyle.StateFlag.State_Selected