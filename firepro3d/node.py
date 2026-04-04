import math
from .cad_math import CAD_Math
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QPointF, QLineF, QRectF
from PyQt6.QtGui import QBrush, QPen, QColor, QPainterPath
from .fitting import Fitting
from .sprinkler import Sprinkler
from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER, DEFAULT_CEILING_OFFSET_MM
from .displayable_item import DisplayableItemMixin

class Node(DisplayableItemMixin, QGraphicsEllipseItem):
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
        self.setZValue(10)  # above walls (-50) and floors (-80)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.x_pos = x
        self.y_pos = y
        self.z_pos = z
        self.z_offset: float = z             # offset from level elevation (legacy, may be ft in old saves)
        self.icon_scale = 4
        self.sprinkler = None
        self.fitting = Fitting(self)
        self.pipes = []
        # Shared display-manager attributes
        self.init_displayable()
        # Node-specific
        self.ceiling_level: str = DEFAULT_LEVEL
        self.ceiling_offset: float = DEFAULT_CEILING_OFFSET_MM
        self._room_name: str = ""   # set by auto-populate to link to a room
        self._hydraulic_badge = None

        # Property panel support — shown for plain (non-sprinkler) nodes
        self._properties: dict = {
            "Ceiling Level":  {"type": "level_ref", "value": DEFAULT_LEVEL},
            "Ceiling Offset": {"type": "string", "value": str(DEFAULT_CEILING_OFFSET_MM)},
        }

    # -------------------------------------------------------------------------
    # Property API (used by PropertyManager and hydraulic solver)



    def get_properties(self) -> dict:
        props = self._properties.copy()
        # Format ceiling offset for display using project units
        props["Ceiling Offset"] = dict(props["Ceiling Offset"])
        props["Ceiling Offset"]["value"] = self._fmt(self.ceiling_offset)
        if self._room_name:
            props["Room"] = {"type": "string", "value": self._room_name,
                             "readonly": True}
        return props

    def set_property(self, key: str, value: str):
        # Accept legacy names from old save files
        if key in ("Elevation", "Elevation Offset", "Ceiling Offset"):
            key = "Ceiling Offset"
        if key == "Level":
            self.level = str(value)  # attribute only, not in _properties
        elif key == "Ceiling Level":
            self._properties[key]["value"] = str(value)
            self.ceiling_level = str(value)
            self._recompute_z_pos()
        elif key == "Ceiling Offset":
            sc = self.scene()
            sm = sc.scale_manager if sc and hasattr(sc, "scale_manager") else None
            if sm:
                parsed = sm.parse_dimension(str(value), sm.bare_number_unit())
                if parsed is not None:
                    self.ceiling_offset = parsed
            else:
                try:
                    self.ceiling_offset = float(value)
                except (ValueError, TypeError):
                    pass
            # Store canonical mm value back (not raw user input)
            self._properties["Ceiling Offset"]["value"] = str(self.ceiling_offset)
            self._recompute_z_pos()
        elif key in self._properties:
            self._properties[key]["value"] = str(value)

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
        self.z_pos = lvl.elevation + self.ceiling_offset  # both mm

    def z_range_mm(self) -> tuple[float, float] | None:
        """Node occupies a single elevation point at its z_pos."""
        z = getattr(self, "z_pos", None)
        return (z, z) if z is not None else None

    # -------------------------------------------------------------------------
    # Sprinkler helpers
    def add_sprinkler(self):
        if self.sprinkler is None:
            self.prepareGeometryChange()
            self.sprinkler = Sprinkler(self)

    def delete_sprinkler(self):
        self.prepareGeometryChange()
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
            # Also repaint the child sprinkler so its highlight updates
            if self.has_sprinkler():
                self.sprinkler.update()

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.pipes:
                for p in self.pipes:
                    p.update_geometry()
                    
        return super().itemChange(change, value)

    # -------------------------------------------------------------------------
    # Hydraulic badge management

    def create_hydraulic_badge(self, node_number, pressure, flow_out, total_flow,
                               position="Right", stack_index=0, stack_total=1,
                               node_label=""):
        """Create a selectable hydraulic node badge as a child item."""
        from .hydraulic_node_badge import HydraulicNodeBadge
        self.remove_hydraulic_badge()
        self._hydraulic_badge = HydraulicNodeBadge(
            self, node_number, pressure, flow_out, total_flow,
            position=position, stack_index=stack_index,
            stack_total=stack_total, node_label=node_label,
        )

    def remove_hydraulic_badge(self):
        """Remove the hydraulic badge if present."""
        if self._hydraulic_badge is not None:
            scene = self.scene()
            if scene and self._hydraulic_badge.scene() is scene:
                scene.removeItem(self._hydraulic_badge)
            self._hydraulic_badge = None

    def boundingRect(self) -> QRectF:
        """Expand bounding rect to encompass selection highlight and coverage overlay."""
        if self.has_sprinkler():
            r = self.sprinkler.TARGET_MM / 2.0 * self.sprinkler._display_scale * 1.15
        else:
            r = 14.0 * 25.4 / 2.0  # 177.8 mm (7")
        r = max(r, self.RADIUS + 4)
        # Coverage overlay can be much larger than the sprinkler graphic
        if Node._coverage_visible and self.has_sprinkler():
            try:
                cov = float(self.sprinkler._properties.get(
                    "Coverage Area", {}).get("value", 0))
            except (ValueError, TypeError):
                cov = 0.0
            if cov > 0:
                sm = getattr(self.scene(), "scale_manager", None) if self.scene() else None
                if sm and sm.is_calibrated and sm.pixels_per_mm > 0:
                    r = max(r, math.sqrt(cov * 92_903.0 / math.pi) * sm.pixels_per_mm + 10)
                else:
                    r = max(r, 50.0)
        return QRectF(-r, -r, r * 2, r * 2)

    def shape(self) -> QPainterPath:
        """Expand clickable area to encompass the sprinkler graphic so
        clicking anywhere on the sprinkler selects the node."""
        if self.has_sprinkler():
            r = self.sprinkler.TARGET_MM / 2.0 * self.sprinkler._display_scale
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
            if self.has_sprinkler():
                # Sprinkler node: draw highlight behind the sprinkler graphic.
                # Drawn here (Node Z=10) so it appears under the Sprinkler (Z=100)
                # and isn't clipped by the Sprinkler's smaller boundingRect.
                r = self.sprinkler.TARGET_MM / 2.0 * self.sprinkler._display_scale * 0.95
            else:
                # Plain node
                r = 14.0 * 25.4 / 2.0  # 177.8 mm
            pen = QPen(QColor(0, 120, 215), r * 0.45)  # ~45% of radius
            pen.setCosmetic(False)                        # scales with zoom
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r, r)

        # Pressure and node-number badges are now separate child items
        # (HydraulicNodeBadge) — no in-paint badge drawing needed.

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
                if sm and sm.is_calibrated and sm.pixels_per_mm > 0:
                    r_scene = r_real_mm * sm.pixels_per_mm
                else:
                    # Fallback when not calibrated — 50 px so it’s at least visible
                    r_scene = 50.0

                painter.setPen(QPen(QColor(0, 200, 80, 120), 1))
                painter.setBrush(QBrush(QColor(0, 200, 80, 30)))
                painter.drawEllipse(QPointF(0, 0), r_scene, r_scene)

        # suppress Qt’s default selection box
        option.state &= ~QStyle.StateFlag.State_Selected