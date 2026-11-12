"""
WaterSupply
===========
Represents the water main connection point on the drawing.

Rendered from the "Water Supply" symbol block (SB4g; System default
system-symbols-watersupply) placed on a network node.
The hydraulic solver reads the static pressure, residual pressure,
and test flow from this item to build the supply curve.

Usage
-----
    ws = WaterSupply(x, y)
    scene.addItem(ws)
    scene.water_supply_node = ws
"""

from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainterPath, QPen
from .constants import DEFAULT_LEVEL, Z_WATER_SUPPLY
from . import phase_registry
from .paper_display import shows_selection
from .symbol_block import SymbolBlockItem


class WaterSupply(SymbolBlockItem):
    """Water supply / connection node -- placed once per drawing on a pipe node."""

    def __init__(self, x: float = 0, y: float = 0):
        super().__init__("Water Supply")
        self.setPos(x, y)
        self._display_overrides: dict = {}  # per-instance display overrides
        self._display_scale: float = 1.0    # DM scale column retired; not read for size
        self.phase: str = phase_registry.PHASE_NEW

        self._properties: dict = {
            "Static Pressure":   {"type": "string", "value": "80"},   # psi
            "Residual Pressure": {"type": "string", "value": "60"},   # psi at test flow
            "Test Flow":         {"type": "string", "value": "500"},  # gpm at residual pressure
            "Elevation":         {"type": "string", "value": "0"},    # ft at supply gauge
            "Test Date":         {"type": "string", "value": ""},   # flow-test date (free text)
            "Hose Stream Allowance": {"type": "enum", "value": "250 GPM",
                                      "options": ["100 GPM", "250 GPM", "500 GPM"]},
            # Informational this task; adding it to solver demand is a
            # planned follow-up (grill 2026-07-14).
            "Domestic Water Allowance": {"type": "string", "value": "0",
                                         "suffix": "gpm"},
        }

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(Z_WATER_SUPPLY)
        self.level: str = DEFAULT_LEVEL

    def rescale(self, sm=None):
        """Scale calibration: the block is real size, so only repaint."""
        self.update()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # The selection outline QGraphicsSvgItem drew (Qt's dashed box on the
        # bounds), canvas only: selection never plots (wall polish D11, L42).
        if shows_selection(self):
            r = self.boundingRect()
            if not r.isEmpty():
                pen = QPen(option.palette.windowText().color(), 0, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(r)

    def shape(self) -> QPainterPath:
        """Full bounding rect, as before SB4g (clicks anywhere on the symbol)."""
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    # -------------------------------------------------------------------------
    # Property API (compatible with PropertyManager)

    def get_properties(self) -> dict:
        props = self._properties.copy()
        props[phase_registry.ROW_KEY] = phase_registry.property_row(self)   # PD1
        return props

    def set_property(self, key: str, value: str):
        if key == phase_registry.ROW_KEY:
            phase_registry.set_from_row(self, value)
        elif key in self._properties:
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
    def domestic_allowance_gpm(self) -> float:
        try:
            return float(self._properties["Domestic Water Allowance"]["value"])
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
