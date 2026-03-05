"""
WaterSupply
===========
Represents the water main connection point on the drawing.

Drawn as a filled downward-pointing triangle with a "WS" label.
The hydraulic solver reads the static pressure, residual pressure,
and test flow from this item to build the supply curve.

Usage
-----
    ws = WaterSupply(x, y)
    scene.addItem(ws)
    scene.water_supply_node = ws
"""

import math

from PyQt6.QtWidgets import QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QPolygonF


class WaterSupply(QGraphicsItem):
    """Water supply / connection node — placed once per drawing."""

    SYMBOL_SIZE_PX  = 15      # fallback radius when uncalibrated (pixels)
    TARGET_PAPER_MM = 10.0    # desired diameter in paper-mm when calibrated

    def __init__(self, x: float = 0, y: float = 0):
        super().__init__()
        self.setPos(x, y)

        self._properties: dict = {
            "Static Pressure":   {"type": "string", "value": "80"},   # psi
            "Residual Pressure": {"type": "string", "value": "60"},   # psi at test flow
            "Test Flow":         {"type": "string", "value": "500"},  # gpm at residual pressure
            "Elevation":         {"type": "string", "value": "0"},    # ft at supply gauge
        }

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable   |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(50)
        self.level: str = "Level 1"

    # ─────────────────────────────────────────────────────────────────────────
    # Property API (compatible with PropertyManager)

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value: str):
        if key in self._properties:
            self._properties[key]["value"] = str(value)

    # ─────────────────────────────────────────────────────────────────────────
    # Convenience accessors for the hydraulic solver

    @property
    def static_pressure(self) -> float:
        try:
            return float(self._properties["Static Pressure"]["value"])
        except (ValueError, TypeError):
            return 0.0

    @property
    def residual_pressure(self) -> float:
        try:
            return float(self._properties["Residual Pressure"]["value"])
        except (ValueError, TypeError):
            return 0.0

    @property
    def test_flow(self) -> float:
        try:
            return float(self._properties["Test Flow"]["value"])
        except (ValueError, TypeError):
            return 0.0

    @property
    def elevation(self) -> float:
        try:
            return float(self._properties["Elevation"]["value"])
        except (ValueError, TypeError):
            return 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Scale helper

    def _get_half_size(self) -> float:
        """Return half the symbol size in scene pixels."""
        sm = getattr(self.scene(), "scale_manager", None) if self.scene() else None
        if sm and sm.is_calibrated:
            return sm.paper_to_scene(self.TARGET_PAPER_MM / 2)
        return self.SYMBOL_SIZE_PX

    def rescale(self, sm=None):
        """Called after scale calibration — just trigger a repaint."""
        self.update()

    # ─────────────────────────────────────────────────────────────────────────
    # Qt overrides

    def boundingRect(self) -> QRectF:
        s = self._get_half_size() * 1.4   # a little padding for the border pen
        return QRectF(-s, -s, 2 * s, 2 * s)

    def paint(self, painter, option, widget=None):
        s = self._get_half_size()
        h = s * math.sqrt(3)   # height of equilateral triangle with half-base = s

        # Downward-pointing equilateral triangle
        pts = [
            QPointF(0,   h * 0.667),    # bottom vertex
            QPointF(-s, -h * 0.333),    # top-left
            QPointF( s, -h * 0.333),    # top-right
        ]
        poly = QPolygonF(pts)

        fill_color  = QColor(0, 180, 220)          # sky-blue fill
        border_color = QColor("white") if self.isSelected() else QColor(0, 100, 160)

        painter.setPen(QPen(border_color, 2))
        painter.setBrush(QBrush(fill_color))
        painter.drawPolygon(poly)

        # "WS" label centred inside the triangle
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(6, int(s * 0.55)))
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        # Place text in the centre-of-mass region of the triangle
        label_rect = QRectF(-s * 0.75, -h * 0.10, s * 1.5, h * 0.55)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, "WS")

        # Suppress Qt's default dashed-rectangle selection indicator
        option.state &= ~QStyle.StateFlag.State_Selected
