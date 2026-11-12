from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QPainterPath

from .constants import DEFAULT_LEVEL, Z_SPRINKLER
from . import phase_registry

from .displayable_item import DisplayableItemMixin
from .symbol_block import SymbolBlockItem


class Sprinkler(DisplayableItemMixin, SymbolBlockItem):
    """A sprinkler head: a child of its Node, drawn from a "Sprinkler" symbol
    block at real size (SB4g D3; ``symbol_block`` None = the System default)."""

    def __init__(self, node):
        SymbolBlockItem.__init__(self, "Sprinkler", owner=node)
        self.node = node
        self.init_displayable()
        self._display_scale: float = 1.0       # DM scale column retired; not read for size
        self.phase: str = phase_registry.PHASE_NEW
        self._properties = {
            "Mark":            {"type": "string", "value": ""},
            "Manufacturer":    {"type": "enum",   "value": "Tyco",       "options": ["Victaulic", "Tyco", "Viking", "Central"]},
            "Model":           {"type": "enum",   "value": "",           "options": []},
            "Orientation":     {"type": "enum",   "value": "Upright",    "options": ["Upright", "Pendent", "Sidewall", "Concealed"]},
            "K-Factor":        {"type": "label",  "value": "5.6"},
            "Coverage Area":   {"type": "label",  "value": "130"},
            "S Spacing":       {"type": "label",  "value": "---"},
            "L Spacing":       {"type": "label",  "value": "---"},
            "Min Pressure":    {"type": "label",  "value": "7"},
            "Temperature":     {"type": "label",  "value": "155°F"},
            "Design Density":  {"type": "string", "value": "0.10"},
            "Ceiling Level":   {"type": "level_ref", "value": DEFAULT_LEVEL},
            "Ceiling Offset":  {"type": "string", "value": "-50.8"},
        }

        # Selection is handled by the parent Node — the Node's shape() covers
        # the sprinkler area so clicks land on the Node directly.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

        if node is not None:
            self.setParentItem(node)
            self.setZValue(Z_SPRINKLER)
            # No ItemIgnoresTransformations — the block is real size (scales with zoom)

    # -------------------------------------------------------------------------
    # Internal helpers

    def rescale(self, sm=None) -> None:
        """Scale calibration: the block is real size, so only repaint."""
        self.update()

    def shape(self) -> QPainterPath:
        """Full bounding rect, as before SB4g (clicks anywhere on the symbol)."""
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    # -------------------------------------------------------------------------
    # Public property API

    def get_properties(self) -> dict:
        props = self._properties.copy()
        # Sync ceiling properties from the parent node
        if self.node is not None:
            props["Ceiling Level"] = dict(props["Ceiling Level"])
            props["Ceiling Level"]["value"] = self.node.ceiling_level
            props["Ceiling Offset"] = dict(props["Ceiling Offset"])
            props["Ceiling Offset"]["value"] = self._fmt(self.node.ceiling_offset)
            props["Ceiling Offset"]["label"] = "Offset"      # D9: key stays for files
        else:
            # Template sprinkler (no node) — format the raw mm value for display
            props["Ceiling Offset"] = dict(props["Ceiling Offset"])
            try:
                raw_mm = float(props["Ceiling Offset"]["value"])
            except (ValueError, TypeError):
                raw_mm = -50.8
            props["Ceiling Offset"]["value"] = self._fmt(raw_mm)
            props["Ceiling Offset"]["label"] = "Offset"
        props[phase_registry.ROW_KEY] = phase_registry.property_row(self)   # PD1
        # X / Y / Z move the node (D10); Y is up-positive
        if self.node is not None:
            props.update(self.node.position_rows())
            props.update(self.node.hydraulic_rows())
        # Show room assignment from parent node
        room_name = getattr(self.node, "_room_name", "") if self.node else ""
        if room_name:
            props["Room"] = {"type": "string", "value": room_name,
                             "readonly": True}
        return props

    def set_property(self, key: str, value):
        if key == "Badge Position":
            if self.node is not None:
                self.node.set_property(key, value)
            return
        if key in ("X", "Y", "Z"):
            # Saved rows replay on a node-less template and move nothing.
            if self.node is not None:
                self.node.set_property(key, value)
            return
        # Accept legacy names from old save files ("Offset" is the panel label)
        if key in ("Elevation", "Elevation Offset", "Ceiling Offset (in)", "Offset"):
            key = "Ceiling Offset"
        if key == phase_registry.ROW_KEY:
            phase_registry.set_from_row(self, value)
            return
        if key not in self._properties:
            return
        self._properties[key]["value"] = value

        if key == "Level" and self.node is not None:
            self.node.level = str(value)
        elif key == "Ceiling Level" and self.node is not None:
            self.node.ceiling_level = str(value)
            self.node._properties["Ceiling Level"]["value"] = str(value)
            self.node._recompute_z_pos()
        elif key == "Ceiling Offset":
            parsed_mm = None
            if isinstance(value, (int, float)):
                parsed_mm = float(value)
            else:
                sm = self._get_scale_manager()
                if sm:
                    parsed_mm = sm.parse_dimension(str(value), sm.bare_number_unit())
                if parsed_mm is None:
                    try:
                        parsed_mm = float(value)
                    except (ValueError, TypeError):
                        parsed_mm = None
            if parsed_mm is not None:
                if self.node is not None:
                    self.node.ceiling_offset = parsed_mm
                    self.node._properties["Ceiling Offset"]["value"] = str(parsed_mm)
                    self.node._recompute_z_pos()
                else:
                    # Template sprinkler — store raw mm
                    self._properties["Ceiling Offset"]["value"] = str(parsed_mm)

    def set_properties(self, template: "Sprinkler"):
        """Copy all property values (and the phase, D-PH5) from a template Sprinkler."""
        for key, meta in template.get_properties().items():
            if meta.get("single_only") or key == phase_registry.ROW_KEY:
                continue       # position rows never move this node; phase copied below
            self.set_property(key, meta["value"])
        self.phase = getattr(template, "phase", phase_registry.PHASE_NEW)