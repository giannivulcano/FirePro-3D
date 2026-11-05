"""D5: what a pipe-tool click will do, shown at the cursor target."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsItem

from .snap_engine import SNAP_COLORS


class PipeTargetMarker(QGraphicsItem):
    """Screen-sized glyph: ring = connect to node, diamond = split pipe.

    Colours come from the shared OSNAP token table (``SNAP_COLORS``): the
    node ring uses the ``midpoint`` green and the split diamond the
    ``quadrant`` orange, so the two kinds stay distinct from each other.

    Never pickable: its shape is empty and it takes no mouse buttons. Z 200
    matches ``preview_node`` and keeps it out of ``is_snap_target``.
    """

    SIZE_PX = 8.0

    def __init__(self):
        super().__init__()
        self.kind = "none"
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setZValue(200)

    def boundingRect(self) -> QRectF:
        s = self.SIZE_PX + 2.0
        return QRectF(-s, -s, 2 * s, 2 * s)

    def shape(self) -> QPainterPath:
        return QPainterPath()

    def paint(self, painter, option, widget=None):
        s = self.SIZE_PX
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == "node":
            painter.setPen(QPen(QColor(SNAP_COLORS["midpoint"]), 2.0))
            painter.drawEllipse(QPointF(0, 0), s, s)
        elif self.kind == "pipe":
            painter.setPen(QPen(QColor(SNAP_COLORS["quadrant"]), 2.0))
            painter.drawPolygon([QPointF(0, -s), QPointF(s, 0),
                                 QPointF(0, s), QPointF(-s, 0)])
