"""
hydraulic_node_badge.py
=======================
Selectable badge child of Node that displays the hydraulic node number
using the hydraulic_node.svg graphic.  Clicking it shows read-only
hydraulic properties (P, q, Q) in the PropertyManager.
"""

from __future__ import annotations

import math
import os
from PyQt6.QtWidgets import QGraphicsItem, QStyle
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath, QTransform, QFont

_SVG_PATH = os.path.join(
    os.path.dirname(__file__),
    "graphics", "sprinkler_graphics", "hydraulic_node.svg",
)

# Badge sizing — same as existing pressure badge (30-inch diameter)
_BADGE_DIAMETER_MM = 30.0 * 25.4        # 762 mm
_OFFSET_MM = 15.0 * 25.4 * 2.2          # 838.2 mm centre-to-centre

_POSITION_OFFSETS = {
    "Right":  QPointF( _OFFSET_MM, 0),
    "Left":   QPointF(-_OFFSET_MM, 0),
    "Above":  QPointF(0, -_OFFSET_MM),
    "Below":  QPointF(0,  _OFFSET_MM),
}

# Preferred order when auto-placing
_AUTO_ORDER = ["Right", "Left", "Above", "Below"]


def best_position_for_node(node) -> str:
    """Choose a badge position that avoids connected pipe directions.

    Examines angles of all pipes connected to *node* and picks the first
    position from Right / Left / Above / Below that is furthest from any
    pipe direction.
    """
    if not node.pipes:
        return "Right"

    # Collect normalised pipe angles from this node (radians, 0 = right)
    angles: list[float] = []
    npos = node.scenePos()
    for pipe in node.pipes:
        other = pipe.node2 if pipe.node1 is node else pipe.node1
        if other is None:
            continue
        opos = other.scenePos()
        dx = opos.x() - npos.x()
        dy = opos.y() - npos.y()
        if abs(dx) < 0.1 and abs(dy) < 0.1:
            continue
        angles.append(math.atan2(dy, dx))

    if not angles:
        return "Right"

    # Direction angles for each position
    dir_angles = {
        "Right": 0.0,
        "Left":  math.pi,
        "Below": math.pi / 2,    # positive Y is down in scene coords
        "Above": -math.pi / 2,
    }

    best = "Right"
    best_min_dist = -1.0
    for pos in _AUTO_ORDER:
        da = dir_angles[pos]
        # Minimum angular distance to any pipe
        min_dist = min(
            min(abs(da - a), 2 * math.pi - abs(da - a))
            for a in angles
        )
        if min_dist > best_min_dist:
            best_min_dist = min_dist
            best = pos
    return best


class HydraulicNodeBadge(QGraphicsSvgItem):
    """Selectable SVG badge showing the hydraulic node number.

    Created as a child of Node when hydraulic results are available.
    """

    def __init__(self, parent_node, node_number: int,
                 pressure: float, flow_out: float, total_flow: float,
                 position: str = "Right", stack_index: int = 0):
        super().__init__(_SVG_PATH, parent_node)
        self._parent_node = parent_node
        self._node_number = node_number
        self._pressure = pressure
        self._flow_out = flow_out
        self._total_flow = total_flow
        self._badge_position = position
        self._stack_index = stack_index      # 0-based vertical stack offset

        self.setZValue(200)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        # Scale and centre the SVG
        self._centre_on_offset()

        # Properties for PropertyManager
        self._properties = {
            "Node Number":          {"type": "label", "value": str(node_number)},
            "Pressure P (psi)":     {"type": "label", "value": f"{pressure:.1f}"},
            "Flow Out q (gpm)":     {"type": "label", "value": f"{flow_out:.1f}"},
            "Total Flow Q (gpm)":   {"type": "label", "value": f"{total_flow:.1f}"},
            "Badge Position":       {"type": "enum",  "value": position,
                                     "options": ["Above", "Below", "Left", "Right"]},
        }

    # ------------------------------------------------------------------
    # Layout

    def _centre_on_offset(self):
        """Scale SVG to badge size and position at the current offset."""
        bounds = self.boundingRect()
        center = bounds.center()
        svg_natural = max(bounds.width(), bounds.height())
        s = _BADGE_DIAMETER_MM / svg_natural if svg_natural > 0 else 1.0
        t = QTransform(s, 0, 0, s, -s * center.x(), -s * center.y())
        self.setTransform(t)
        offset = QPointF(_POSITION_OFFSETS.get(self._badge_position, QPointF(0, 0)))
        # Vertical stacking: shift down by badge diameter per stack index
        offset += QPointF(0, self._stack_index * _BADGE_DIAMETER_MM * 1.1)
        self.setPos(offset)

    # ------------------------------------------------------------------
    # Property API  (matches Sprinkler / Pipe / Node pattern)

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value):
        if key == "Badge Position" and value in _POSITION_OFFSETS:
            self._badge_position = value
            self._properties["Badge Position"]["value"] = value
            self._centre_on_offset()

    # ------------------------------------------------------------------
    # Paint — overlay node number text on the SVG hexagon

    def paint(self, painter, option, widget=None):
        # Draw SVG background
        super().paint(painter, option, widget)

        # Draw node number centred in the badge
        rect = self.boundingRect()
        font = painter.font()
        font.setPixelSize(max(1, int(rect.height() * 0.45)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.white, 0))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self._node_number))

        # Selection highlight
        if self.isSelected():
            pen = QPen(QColor("cyan"), 2)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = max(rect.width(), rect.height()) / 2.0
            painter.drawEllipse(rect.center(), r, r)

        # Suppress default selection rectangle
        option.state &= ~QStyle.StateFlag.State_Selected

    def shape(self) -> QPainterPath:
        """Full bounding rect as clickable area."""
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path
