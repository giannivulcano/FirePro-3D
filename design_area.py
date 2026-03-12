"""
design_area.py
==============
Persistent annotation representing a fire suppression design area.

Stores a set of sprinklers, a hazard classification, and displays
as a bounding rectangle on the scene.  Multiple design areas can
coexist; the active one is used for hydraulic calculations.
"""

from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath

HAZARD_OPTIONS = [
    "Light Hazard",
    "Ordinary Hazard Group 1",
    "Ordinary Hazard Group 2",
    "Extra Hazard Group 1",
    "Extra Hazard Group 2",
]


class DesignArea(QGraphicsRectItem):
    """Selectable design-area rectangle that tracks a set of sprinklers."""

    def __init__(self, sprinklers=None, parent=None):
        super().__init__(parent)
        self._sprinklers: list = list(sprinklers or [])
        self._properties: dict = {
            "Hazard Classification": {
                "type": "enum",
                "value": "Ordinary Hazard Group 1",
                "options": HAZARD_OPTIONS,
            },
            "System Name": {"type": "string", "value": "System 1"},
            "Area": {"type": "label", "value": "0"},
        }
        self.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(255, 200, 0, 40)))
        self.setZValue(200)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.level: str = "Level 1"
        self.user_layer: str = "Default"
        self._update_rect()

    # ------------------------------------------------------------------
    # Sprinkler management

    @property
    def sprinklers(self) -> list:
        return self._sprinklers

    def add_sprinkler(self, spr):
        if spr not in self._sprinklers:
            self._sprinklers.append(spr)
            self._update_rect()

    def remove_sprinkler(self, spr):
        if spr in self._sprinklers:
            self._sprinklers.remove(spr)
            self._update_rect()

    def toggle_sprinkler(self, spr):
        if spr in self._sprinklers:
            self.remove_sprinkler(spr)
            return False  # removed
        else:
            self.add_sprinkler(spr)
            return True   # added

    def set_sprinklers(self, sprinklers: list):
        """Replace the full sprinkler set (e.g. from rectangle selection)."""
        self._sprinklers = list(sprinklers)
        self._update_rect()

    # ------------------------------------------------------------------
    # Bounding rectangle

    def _update_rect(self):
        """Recompute bounding box from sprinkler positions."""
        if not self._sprinklers:
            self.setRect(QRectF())
            self._properties["Area"]["value"] = "0"
            return
        xs = [s.node.scenePos().x() for s in self._sprinklers if s.node]
        ys = [s.node.scenePos().y() for s in self._sprinklers if s.node]
        if not xs:
            self.setRect(QRectF())
            return
        # Margin around outermost sprinklers (scene units)
        margin = 300.0
        rect = QRectF(
            min(xs) - margin, min(ys) - margin,
            max(xs) - min(xs) + 2 * margin,
            max(ys) - min(ys) + 2 * margin,
        )
        self.setRect(rect)

    def compute_area(self, scale_manager):
        """Compute area using the scale_manager and update property."""
        if not scale_manager or not scale_manager.is_calibrated:
            return
        ppm = scale_manager.pixels_per_mm
        if ppm <= 0:
            return
        r = self.rect()
        w_mm = r.width() / ppm
        h_mm = r.height() / ppm
        # Display in the current unit system
        if scale_manager.display_unit == "m":
            area = (w_mm / 1000.0) * (h_mm / 1000.0)
            self._properties["Area"]["value"] = f"{area:.1f} m\u00b2"
        else:
            # Assume imperial (feet)
            area_sqft = (w_mm / 304.8) * (h_mm / 304.8)
            self._properties["Area"]["value"] = f"{area_sqft:.0f} sq ft"

    # ------------------------------------------------------------------
    # Property API

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value: str):
        if key in self._properties:
            self._properties[key]["value"] = str(value)

    # ------------------------------------------------------------------
    # Paint override for selection highlight

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # Suppress default selection rectangle
        option.state &= ~QStyle.StateFlag.State_Selected

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.rect())
        return path
