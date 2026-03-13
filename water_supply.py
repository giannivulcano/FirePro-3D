"""
WaterSupply
===========
Represents the water main connection point on the drawing.

Rendered as an SVG symbol (water_supply.svg) placed on a network node.
The hydraulic solver reads the static pressure, residual pressure,
and test flow from this item to build the supply curve.

Usage
-----
    ws = WaterSupply(x, y)
    scene.addItem(ws)
    scene.water_supply_node = ws
"""

import os

from PyQt6.QtWidgets import QGraphicsItem, QStyle
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QTransform, QPainterPath
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtSvg import QSvgRenderer


class WaterSupply(QGraphicsSvgItem):
    """Water supply / connection node -- placed once per drawing on a pipe node."""

    SVG_PATH = os.path.join(
        os.path.dirname(__file__),
        "graphics", "sprinkler_graphics", "water_supply.svg",
    )
    SVG_NATURAL_PX = 30.0               # natural SVG bounding-box width (px)
    TARGET_MM      = 24.0 * 25.4        # desired symbol diameter in mm (24 inches)
    SCALE          = TARGET_MM / SVG_NATURAL_PX

    def __init__(self, x: float = 0, y: float = 0):
        super().__init__()
        self.setPos(x, y)
        self._display_overrides: dict = {}  # per-instance display overrides
        self._display_scale: float = 1.0    # display scale multiplier

        self._properties: dict = {
            "Static Pressure":   {"type": "string", "value": "80"},   # psi
            "Residual Pressure": {"type": "string", "value": "60"},   # psi at test flow
            "Test Flow":         {"type": "string", "value": "500"},  # gpm at residual pressure
            "Elevation":         {"type": "string", "value": "0"},    # ft at supply gauge
            "Hose Stream Allowance": {"type": "enum", "value": "250 GPM",
                                      "options": ["100 GPM", "250 GPM", "500 GPM"]},
        }

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(50)
        self.level: str = "Level 1"

        # Load SVG
        renderer = QSvgRenderer(self.SVG_PATH)
        self.setSharedRenderer(renderer)
        self._renderer = renderer          # prevent garbage collection
        self._centre_on_origin()

    # -------------------------------------------------------------------------
    # SVG scaling / centering

    def _centre_on_origin(self):
        """Centre the SVG on (0,0) at TARGET_MM scale (same pattern as Sprinkler)."""
        bounds = self.boundingRect()
        center = bounds.center()
        svg_natural = max(bounds.width(), bounds.height())
        s = self.TARGET_MM / svg_natural if svg_natural > 0 else self.SCALE
        s *= self._display_scale  # apply display manager scale override
        t = QTransform(s, 0, 0, s, -s * center.x(), -s * center.y())
        self.setTransform(t)

    def rescale(self, sm=None):
        """Called after scale calibration -- just re-centre."""
        self._centre_on_origin()

    def shape(self) -> QPainterPath:
        """Return full bounding rect as shape so clicking anywhere on the
        symbol selects it (not just the SVG path outlines)."""
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    # -------------------------------------------------------------------------
    # Property API (compatible with PropertyManager)

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value: str):
        if key in self._properties:
            self._properties[key]["value"] = str(value)

    # -------------------------------------------------------------------------
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

    @property
    def hose_stream_allowance(self) -> float:
        """Return hose stream allowance in gpm (parsed from '250 GPM' etc.)."""
        raw = self._properties.get("Hose Stream Allowance", {}).get("value", "250 GPM")
        try:
            return float(raw.split()[0])
        except (ValueError, IndexError):
            return 250.0
