from math import floor
import math
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsItem, QGraphicsTextItem, QStyle
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath, QPainterPathStroker
from PyQt6.QtCore import Qt, QPointF
from CAD_Math import CAD_Math


class Pipe(QGraphicsLineItem):
    SNAP_TOLERANCE_DEG = 7.5  # snap if within this angle

    # Paper line-weight in mm for each "Line Weight" property value.
    # Used when the scene has a calibrated scale; otherwise PX_FALLBACK is used.
    LINE_WEIGHT_MM       = {"1": 0.35, "2": 0.50, "3": 0.70, "4": 1.00}
    LINE_WEIGHT_PX_FALLBACK = {"1": 10.0,  "2": 12.0,  "3": 14.0,  "4": 16.0}

    # Nominal pipe OD in inches — used to set the 2D line width to the real
    # pipe size (1 scene unit = 1 mm, so OD_in × 25.4 = pen width in scene units).
    NOMINAL_OD_IN: dict[str, float] = {
        '1"Ø': 1.315, '1-½"Ø': 1.900, '2"Ø': 2.375, '3"Ø': 3.500,
        '4"Ø': 4.500, '5"Ø': 5.563, '6"Ø': 6.625, '8"Ø': 8.625,
    }

    # Inside diameter (inches) by schedule and nominal pipe size.
    # Used by the hydraulic solver (Hazen-Williams requires actual ID, not nominal).
    # Keys match the "Diameter" property option strings.
    INNER_DIAMETER_IN: dict[str, dict[str, float]] = {
        "Sch 10":  {"1\"Ø": 1.097, "1-½\"Ø": 1.682, "2\"Ø": 2.157, "3\"Ø": 3.260,
                    "4\"Ø": 4.260, "5\"Ø": 5.295, "6\"Ø": 6.357, "8\"Ø": 8.329},
        "Sch 40":  {"1\"Ø": 1.049, "1-½\"Ø": 1.610, "2\"Ø": 2.067, "3\"Ø": 3.068,
                    "4\"Ø": 4.026, "5\"Ø": 5.047, "6\"Ø": 6.065, "8\"Ø": 7.981},
        "Sch 80":  {"1\"Ø": 0.957, "1-½\"Ø": 1.500, "2\"Ø": 1.939, "3\"Ø": 2.900,
                    "4\"Ø": 3.826, "5\"Ø": 4.813, "6\"Ø": 5.761, "8\"Ø": 7.625},
        "Sch 40S": {"1\"Ø": 1.049, "1-½\"Ø": 1.610, "2\"Ø": 2.067, "3\"Ø": 3.068,
                    "4\"Ø": 4.026, "5\"Ø": 5.047, "6\"Ø": 6.065, "8\"Ø": 7.981},
        "Sch 10S": {"1\"Ø": 1.097, "1-½\"Ø": 1.682, "2\"Ø": 2.157, "3\"Ø": 3.260,
                    "4\"Ø": 4.260, "5\"Ø": 5.295, "6\"Ø": 6.357, "8\"Ø": 8.329},
    }

    def __init__(self, node1, node2):

        super().__init__()
        # Properties
        self._properties = {
            "Diameter":    {"type": "enum",   "value": "1\"Ø",            "options": ["1\"Ø", "1-½\"Ø", "2\"Ø","3\"Ø","4\"Ø","5\"Ø","6\"Ø","8\"Ø"]},
            "Schedule":    {"type": "enum",   "value": "Sch 40",         "options": ["Sch 10", "Sch 40", "Sch 80", "Sch 40S", "Sch 10S"]},
            "C-Factor":    {"type": "string", "value": "120"},
            "Material":    {"type": "enum",   "value": "Galvanized Steel","options": ["Galvanized Steel", "Stainless Steel", "Black Steel", "PVC"]},
            "Elevation 1": {"type": "string", "value": "0"},
            "Elevation 2": {"type": "string", "value": "0"},
            "Colour":      {"type": "enum",   "value": "Red",            "options": ["Black", "White", "Red", "Blue", "Grey"]},
            "Line Weight": {"type": "enum",   "value": "1",              "options": ["1", "2", "3", "4"]},
            "Phase":       {"type": "enum",   "value": "New",            "options": ["New", "Existing", "Demo"]},
            "Show Label":  {"type": "enum",   "value": "True",           "options": ["True", "False"]},
        }

        self.node1 = node1
        self.node2 = node2
        self.colour = None
        self.length = 0.0
        self.user_layer: str = "Default"   # user-defined layer name
        self.level: str = "Level 1"          # floor level name


        self.label = QGraphicsTextItem("", self)  # Child of pipe

        self.set_pipe_display()
        
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-100)
        
        # track node movement
        if node1 and node2:
            self.node1.pipes.append(self)
            self.node2.pipes.append(self)
            self.update_geometry()

    def set_pipe_display(self):
        colour = QColor(self._properties["Colour"]["value"])
        line_weight = self.get_od_mm()
        pen = QPen(colour, line_weight)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        self.setPen(pen)

    # --------------------------------------------
    # PIPE LABEL HELPERS
    def update_label(self, visible=None):
        if not self.node1 or not self.node2:
            return  # cannot position label yet

        if not hasattr(self, "label") or self.label is None:
            self.label = QGraphicsTextItem(parent=self)
            self.label.setDefaultTextColor(Qt.GlobalColor.black)
            # No ItemIgnoresTransformations — label is in model-space units

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

        # Text height = 12 inches in model space (1 scene unit = 1 mm)
        text_h = 12.0 * 25.4   # 304.8 mm
        # Gap between rows = pipe visual width + 2 inches (clearance each side)
        gap = self.get_od_mm() + 2.0 * 25.4   # mm

        # Include hydraulic results if available
        hr_lines = ""
        if scene and hasattr(scene, "hydraulic_result") and scene.hydraulic_result is not None:
            result = scene.hydraulic_result
            q = result.pipe_flows.get(self)
            hf = result.pipe_friction_loss.get(self)
            if q is not None:
                hr_lines += (f"<div style='font-size:{text_h:.0f}px; "
                             f"margin-top:{gap:.0f}px; color:#00aaff;'>"
                             f"{q:.1f} gpm</div>")
            if hf is not None:
                hr_lines += (f"<div style='font-size:{text_h:.0f}px; "
                             f"margin-top:{gap:.0f}px; color:#ffaa00;'>"
                             f"{hf:.2f} psi</div>")

        html = (f"<div style='text-align:center;'>"
                f"<div style='font-size:{text_h:.0f}px;'>{diameter}</div>"
                f"<div style='font-size:{text_h:.0f}px; "
                f"margin-top:{gap:.0f}px;'>{length}</div>"
                f"{hr_lines}</div>")
        self.label.setHtml(html)
        # Measure natural width then lock it so text-align:center works
        self.label.setTextWidth(-1)
        ideal = self.label.document().idealWidth()
        self.label.setTextWidth(ideal)

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

    def shape(self):
        """Viewport-scale-aware hit path — always at least ~10 screen pixels wide.

        Pipes use a non-cosmetic scene-unit pen whose width shrinks when the scale
        manager converts mm → scene units.  Without this override, a thin calibrated
        pipe can become nearly impossible to click.
        """
        ln = self.line()
        path = QPainterPath()
        path.moveTo(ln.p1())
        path.lineTo(ln.p2())
        stroker = QPainterPathStroker()
        sc = self.scene()
        views = sc.views() if sc else []
        scale = views[0].transform().m11() if views else 1.0
        # Take max of actual pen width and 10 screen-pixel equivalent
        hit_w = max(self.pen().widthF(), 10.0 / max(scale, 1e-6))
        stroker.setWidth(hit_w)
        return stroker.createStroke(path)


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

            if key in ("Diameter", "Show Label"):
                self.update_label()
            if key in ("Colour", "Line Weight", "Diameter"):
                self.set_pipe_display()
    
    def set_properties(self, template: "Pipe"):
        """Copy property values from a template sprinkler."""
        for key, meta in template.get_properties().items():
            self.set_property(key, meta["value"])

    def get_od_mm(self) -> float:
        """Return the visual outside diameter in mm for the current pipe size.

        Returns 2× the nominal OD so pipes are easier to see on screen.
        Used by the 2D paint method to draw pipes at their real physical width.
        """
        nominal = self._properties["Diameter"]["value"]
        od_in = self.NOMINAL_OD_IN.get(nominal, 1.315)   # fallback to 1"
        return od_in * 25.4 * 2  # inches → mm (= scene units), doubled for visibility

    def get_inner_diameter(self) -> float:
        """Return the actual inside diameter in inches for the current nominal size and schedule.
        Used by the hydraulic solver (Hazen-Williams requires ID, not nominal diameter).
        Falls back to 2\"-Sch-40 (2.067 in) if the combination is not found.
        """
        schedule = self._properties["Schedule"]["value"]
        nominal  = self._properties["Diameter"]["value"]
        schedule_map = self.INNER_DIAMETER_IN.get(schedule, self.INNER_DIAMETER_IN["Sch 40"])
        return schedule_map.get(nominal, 2.067)

    def paint(self, painter, option, widget=None):
        colour = QColor(self._properties["Colour"]["value"])

        # Pen width = real pipe OD in scene units (mm).
        # Non-cosmetic: the line scales with zoom just like real geometry.
        line_weight = self.get_od_mm()
        base_pen = QPen(colour, line_weight)
        base_pen.setCapStyle(Qt.PenCapStyle.FlatCap)

        # Velocity color-coding when hydraulic results are available
        scene = self.scene()
        if scene and hasattr(scene, "hydraulic_result") and scene.hydraulic_result is not None:
            v = scene.hydraulic_result.pipe_velocity.get(self, -1)
            if v >= 0:
                if v > 20:
                    colour = QColor(220, 0, 0)      # red: high velocity
                elif v > 12:
                    colour = QColor(220, 140, 0)    # orange: elevated velocity
                else:
                    colour = QColor(0, 200, 80)     # green: OK
                base_pen = QPen(colour, line_weight)
                base_pen.setCapStyle(Qt.PenCapStyle.FlatCap)

        # normal draw
        painter.setPen(base_pen)
        painter.drawLine(self.line())

        # highlight if selected
        if self.isSelected():
            highlight_pen = QPen(colour, line_weight * 1.3)
            highlight_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(highlight_pen)
            painter.drawLine(self.line())

            # also show node endpoints — zoom-independent fixed screen size
            sc = self.scene()
            views = sc.views() if sc else []
            view_scale = abs(views[0].transform().m11()) if views else 1.0
            radius = 6.0 / max(view_scale, 1e-6)  # 6 screen pixels
            brush = QBrush(QColor("white"))
            painter.setBrush(brush)
            painter.setPen(Qt.PenStyle.NoPen)

            for node in (self.node1, self.node2):
                if node is not None:
                    pos = node.scenePos()
                    painter.drawEllipse(QPointF(pos.x(), pos.y()), radius, radius)


        # prevent the default dotted selection rect
        option.state &= ~QStyle.StateFlag.State_Selected