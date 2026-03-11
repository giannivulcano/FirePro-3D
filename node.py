import math
from CAD_Math import CAD_Math
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QPointF, QLineF, QRectF
from PyQt6.QtGui import QBrush, QPen, QColor, QPainterPath
from fitting import Fitting
from sprinkler import Sprinkler

class Node(QGraphicsEllipseItem):
    RADIUS = 13

    # Class-level toggle — all nodes share the same visibility state.
    # Toggled by Model_Space.set_coverage_overlay(visible).
    _coverage_visible: bool = False


    def __init__(self, x, y, z=0):
        super().__init__(-self.RADIUS, -self.RADIUS,
                         self.RADIUS*2, self.RADIUS*2)
        self.setPos(x, y)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.x_pos = x
        self.y_pos = y
        self.z_pos = z
        self.z_offset: float = z             # offset from level elevation (ft)
        self.icon_scale = 4
        self.sprinkler = None
        self.fitting = Fitting(self)
        self.pipes = []
        self.user_layer: str = "Default"   # user-defined layer name
        self.level: str = "Level 1"          # floor level (visibility)
        self.ceiling_level: str = "Level 1"  # ceiling level (3D elevation)
        self.ceiling_offset: float = -2.0    # inches below ceiling (default -2")

        # Property panel support — shown for plain (non-sprinkler) nodes
        self._properties: dict = {
            "Level":          {"type": "level_ref", "value": "Level 1"},
            "Ceiling Level":  {"type": "level_ref", "value": "Level 1"},
            "Ceiling Offset (in)": {"type": "string", "value": "-2"},
        }

    # -------------------------------------------------------------------------
    # Property API (used by PropertyManager and hydraulic solver)

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value: str):
        # Accept legacy names from old save files
        if key in ("Elevation", "Elevation Offset", "Ceiling Offset"):
            key = "Ceiling Offset (in)"
        if key in self._properties:
            self._properties[key]["value"] = str(value)
        if key == "Level":
            self.level = str(value)
        elif key == "Ceiling Level":
            self.ceiling_level = str(value)
            self._recompute_z_pos()
        elif key == "Ceiling Offset (in)":
            try:
                self.ceiling_offset = float(value)
            except (ValueError, TypeError):
                pass
            self._recompute_z_pos()

    def _recompute_z_pos(self):
        """Recompute z_pos from ceiling_level elevation + ceiling_offset.

        Called when the user changes Ceiling Level or Ceiling Offset via the
        property panel so that the 3D view stays in sync without requiring a
        full level_manager.update_elevations() pass.
        """
        scene = self.scene()
        if scene is None:
            return
        lm = getattr(scene, "_level_manager", None)
        if lm is None:
            return
        lvl = lm.get(self.ceiling_level)
        if lvl is None:
            return
        self.z_pos = lvl.elevation + self.ceiling_offset / 12.0

    # -------------------------------------------------------------------------
    # Sprinkler helpers
    def add_sprinkler(self):
        if self.sprinkler is None:
            self.sprinkler = Sprinkler(self)

    def delete_sprinkler(self):
        self.sprinkler = None

    def has_sprinkler(self):
        return self.sprinkler is not None

    # -------------------------------------------------------------------------
    # Fitting helpers    
    def has_fitting(self):
        return self.fitting is not None      

    # -------------------------------------------------------------------------
    # Pipe helpers
    def add_pipe(self, pipe):
        
        if pipe not in self.pipes:
            if len(self.pipes) < 4:
                self.pipes.append(pipe)

                self.fitting.update()   # <-- auto-update here
                pipe.update_geometry()
            else:
                pass  # max 4 connections

    def remove_pipe(self, pipe):
        if pipe in self.pipes:
            self.pipes.remove(pipe)
            if self.fitting:
                self.fitting.update()

        # Only clear references if they actually point here
        if getattr(pipe, "node1", None) is self:
            pipe.node1 = None
        elif getattr(pipe, "node2", None) is self:
            pipe.node2 = None

    # -------------------------------------------------------------------------
    # Geometry helpers
    def distance_to(self, x, y):
        return QLineF(self.scenePos(), QPointF(x, y)).length()
        
    def snap_point_45(self, start: QPointF, end: QPointF) -> QPointF:
        """
        Snap 'end' to 45° increments relative to the first connected pipe
        if one exists. If not, allow free movement but snap only when the
        angle is *near* 0°, 45°, 90°, etc.
        """
        angle = CAD_Math.get_vector_angle(start, end)-90
        length = CAD_Math.get_vector_length(start, end)

        if self.pipes:
            # Snap relative to connected pipe
            reference_pipe = self.pipes[0]
            base_angle = CAD_Math.get_vector_angle(
                reference_pipe.node1.scenePos(), reference_pipe.node2.scenePos()
            )
            rel_angle = angle - base_angle
            snap_rel = round(rel_angle / 45) * 45
            snapped = base_angle + snap_rel
        else:
            # Free movement, with "soft" snapping near 45° multiples
            base_angle = 0
            nearest_snap = round(angle / 45) * 45
            diff = abs(angle - nearest_snap)

            # Snap only if within 7.5° of a multiple of 45°
            if diff < 7.5:
                snapped = nearest_snap
            else:
                snapped = angle

        rad = math.radians(snapped)
        return QPointF(
            start.x() + length * math.cos(rad),
            start.y() + length * math.sin(rad)
        )

        
    

            
    # -------------------------------------------------------------------------
    #item change handling

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()  # force a full repaint when selected/deselected

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.pipes:
                for p in self.pipes:
                    p.update_geometry()
                    
        return super().itemChange(change, value)

    
    def boundingRect(self) -> QRectF:
        """Expand bounding rect to encompass zoom-dependent selection highlight
        and coverage overlay so Qt doesn't clip the painted graphics."""
        if self.has_sprinkler():
            r = self.sprinkler.TARGET_MM / 2.0 * 1.15
        else:
            r = 14.0 * 25.4 / 2.0  # 177.8 mm (7")
        r = max(r, self.RADIUS + 4)
        return QRectF(-r, -r, r * 2, r * 2)

    def shape(self) -> QPainterPath:
        """Expand clickable area to encompass the sprinkler graphic so
        clicking anywhere on the sprinkler selects the node."""
        if self.has_sprinkler():
            r = self.sprinkler.TARGET_MM / 2.0
        else:
            r = 14.0 * 25.4 / 2.0  # 177.8 mm (7")
        r = max(r, self.RADIUS)
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), r, r)
        return path

    def paint(self, painter, option, widget=None):
        # invisible by default
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        if self.isSelected():
            # Zoom-dependent selection highlight (scales with scene geometry)
            if self.has_sprinkler():
                # Slightly larger than sprinkler SVG (15% bigger)
                radius = self.sprinkler.TARGET_MM / 2.0 * 1.15
            else:
                # Plain node: 14-inch diameter highlight
                radius = 14.0 * 25.4 / 2.0  # 177.8 mm

            highlight_pen = QPen(QColor("red"), 2)
            highlight_pen.setCosmetic(True)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), radius, radius)

        # Pressure badge when hydraulic results are available
        scene = self.scene()
        if scene and hasattr(scene, "hydraulic_result") and scene.hydraulic_result is not None:
            p = scene.hydraulic_result.node_pressures.get(self)
            if p is not None:
                # Zoom-independent badge
                views = scene.views() if scene else []
                view_scale = abs(views[0].transform().m11()) if views else 1.0
                badge_r = 14.0 / max(view_scale, 1e-6)
                font_pt = max(5, int(14.0 * 0.55))

                # Pick badge color based on pressure vs. minimum
                p_min = 7.0
                if self.has_sprinkler():
                    try:
                        p_min = float(self.sprinkler._properties["Min Pressure"]["value"])
                    except (KeyError, ValueError, TypeError):
                        pass
                if p < p_min:
                    bg = QColor(220, 0, 0, 200)      # red – below minimum
                elif p < p_min * 1.5:
                    bg = QColor(220, 140, 0, 200)    # orange – marginal
                else:
                    bg = QColor(0, 160, 60, 200)     # green – comfortable

                painter.setBrush(QBrush(bg))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(0, -badge_r * 2.2), badge_r, badge_r)

                font = painter.font()
                font.setPointSize(font_pt)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QPen(Qt.GlobalColor.white, 1))
                painter.drawText(
                    QRectF(-badge_r, -badge_r * 3.2, badge_r * 2, badge_r * 2),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{p:.0f}"
                )

        # Coverage overlay — translucent green circle sized from sprinkler’s
        # Coverage Area property (sq ft).  Drawn only when the class-level
        # flag _coverage_visible is True and this node carries a sprinkler.
        if Node._coverage_visible and self.has_sprinkler():
            try:
                coverage_sqft = float(
                    self.sprinkler._properties.get("Coverage Area", {}).get("value", 0)
                )
            except (ValueError, TypeError):
                coverage_sqft = 0.0

            if coverage_sqft > 0:
                sm = getattr(self.scene(), "scale_manager", None) if self.scene() else None
                # Real-world radius in mm: r = sqrt(A_mm² / π)
                # 1 sq ft = 92 903 mm²
                r_real_mm = math.sqrt(coverage_sqft * 92_903.0 / math.pi)
                if sm and sm.is_calibrated and sm.drawing_scale > 0:
                    r_paper_mm = r_real_mm / sm.drawing_scale
                    r_scene = sm.paper_to_scene(r_paper_mm)
                else:
                    # Fallback when not calibrated — 50 px so it’s at least visible
                    r_scene = 50.0

                painter.setPen(QPen(QColor(0, 200, 80, 120), 1))
                painter.setBrush(QBrush(QColor(0, 200, 80, 30)))
                painter.drawEllipse(QPointF(0, 0), r_scene, r_scene)

        # suppress Qt’s default selection box
        option.state &= ~QStyle.StateFlag.State_Selected