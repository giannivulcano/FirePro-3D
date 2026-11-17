from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QPainterPath

from .constants import DEFAULT_CEILING_OFFSET_MM, DEFAULT_LEVEL, Z_SPRINKLER
from . import phase_registry
from . import element_uid

from .displayable_item import DisplayableItemMixin
from .symbol_block import SymbolBlockItem, _SymbolPaperMixin


class Sprinkler(_SymbolPaperMixin, DisplayableItemMixin, SymbolBlockItem):
    """A sprinkler head: a child of its Node, drawn from a "Sprinkler" symbol
    block at real size (SB4g D3; ``symbol_block`` None = the System default)."""

    paper_category = "Sprinkler"    # paper row (paper-space.md s6.2, R5)

    def __init__(self, node):
        SymbolBlockItem.__init__(self, "Sprinkler", owner=node)
        self._uid: str = element_uid.new_uid()     # SB5 D2: stable element id
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
            "Ceiling Offset":  {"type": "string", "value": str(DEFAULT_CEILING_OFFSET_MM)},
        }

        # Selection is handled by the parent Node — the Node's shape() covers
        # the sprinkler area so clicks land on the Node directly.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

        if node is not None:
            self.setParentItem(node)
            sc = node.scene()                  # SB5: a child joining by setParentItem
            if sc is not None and hasattr(sc, "_uid_gen"):    # never reaches addItem: drop
                sc._uid_gen += 1               # a memoized element_by_uid miss
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

    def get_properties(self, *, with_symbol_row: bool = True) -> dict:
        """The panel rows. ``with_symbol_row=False`` skips the Symbol row, whose
        build walks the symbol library on disk -- serialize / undo / signature
        callers that discard that row pass it (SB4g VC9 I1)."""
        from .system_blocks import SYMBOL_ROW_KEY
        props = {}
        for k, v in self._properties.items():      # the Symbol row takes Graphic's old slot
            if k == "Ceiling Level" and with_symbol_row:
                props[SYMBOL_ROW_KEY] = self.symbol_row()
            props[k] = v
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
                raw_mm = DEFAULT_CEILING_OFFSET_MM
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
        from .system_blocks import SYMBOL_ROW_KEY
        if key == SYMBOL_ROW_KEY:
            self.set_symbol_from_row(value)
            return
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
        if key in ("Ceiling Level", "Ceiling Offset") and self.node is not None:
            if key == "Ceiling Level":
                self.node.host(str(value), self.node.ceiling_offset)   # refresh: Fitting.type (Q5)
            else:
                parsed_mm = self._parse_mm(value)
                if parsed_mm is not None:
                    self.node.host(self.node.ceiling_level, parsed_mm)
            return
        self._properties[key]["value"] = value
        if key == "Level" and self.node is not None:
            self.node.level = str(value)
        elif key == "Ceiling Offset":
            parsed_mm = self._parse_mm(value)
            if parsed_mm is not None:
                self._properties["Ceiling Offset"]["value"] = str(parsed_mm)   # template: raw mm

    def _parse_mm(self, value):
        if isinstance(value, (int, float)):
            return float(value)
        sm = self._get_scale_manager()
        parsed = sm.parse_dimension(str(value), sm.bare_number_unit()) if sm else None
        if parsed is None:
            try:
                parsed = float(value)
            except (ValueError, TypeError):
                parsed = None
        return parsed

    def set_properties(self, template: "Sprinkler"):
        """Copy all property values, the phase (D-PH5) and the symbol choice
        (SB4g R3) from a template Sprinkler."""
        from .system_blocks import SYMBOL_ROW_KEY
        for key, meta in template.get_properties(with_symbol_row=False).items():
            if meta.get("single_only") or key in (phase_registry.ROW_KEY, SYMBOL_ROW_KEY):
                continue       # position rows never move this node; phase + symbol copied below
            if self.node is not None and key in ("Ceiling Level", "Ceiling Offset"):
                continue       # Q11: a head never re-hosts its node; the tool hosts nodes it creates
            self.set_property(key, meta["value"])
        self.phase = getattr(template, "phase", phase_registry.PHASE_NEW)
        self.set_symbol_block(getattr(template, "symbol_block", None))

    def ceiling_host(self) -> tuple[str, float]:
        """A node-less template's (Ceiling Level, Ceiling Offset mm): the host
        for a node the sprinkler tool creates (Q11)."""
        lvl = self._properties["Ceiling Level"]["value"] or DEFAULT_LEVEL
        try:
            off = float(self._properties["Ceiling Offset"]["value"])
        except (ValueError, TypeError):
            off = DEFAULT_CEILING_OFFSET_MM
        return lvl, off