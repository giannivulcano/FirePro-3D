import math
from CAD_Math import CAD_Math
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QPointF, QLineF
from PyQt6.QtGui import QBrush, QPen, QColor
from fitting import Fitting
from sprinkler import Sprinkler

class Node(QGraphicsEllipseItem):
    RADIUS = 13


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
        self.icon_scale = 4
        self.sprinkler = None
        self.fitting = Fitting(self)
        self.pipes = []

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
                print("only 4 connections permitted")

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

    
    def paint(self, painter, option, widget=None):
        # invisible by default
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        if self.isSelected():
            sm = getattr(self.scene(), "scale_manager", None) if self.scene() else None
            if sm and sm.is_calibrated:
                # 4.5mm circle for sprinkler nodes, 1.5mm for plain nodes
                radius = sm.paper_to_scene(4.5) if self.has_sprinkler() else sm.paper_to_scene(1.5)
            else:
                radius = self.RADIUS if self.has_sprinkler() else self.RADIUS / 2

            highlight_pen = QPen(QColor("red"), 3)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), radius, radius)

        # suppress Qt’s default selection box
        option.state &= ~QStyle.StateFlag.State_Selected