import os

from PyQt6.QtWidgets import QGraphicsItem, QStyle
from PyQt6.QtGui import QTransform, QPainterPath, QPen, QColor
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import Qt

from constants import DEFAULT_LEVEL

from displayable_item import DisplayableItemMixin


class Sprinkler(DisplayableItemMixin, QGraphicsSvgItem):
    GRAPHICS = {
        "Sprinkler0": r"graphics/sprinkler_graphics/sprinkler0.svg",
        "Sprinkler1": r"graphics/sprinkler_graphics/sprinkler1.svg",
        "Sprinkler2": r"graphics/sprinkler_graphics/sprinkler2.svg"
    }

    SVG_NATURAL_PX = 30.0    # natural SVG bounding-box width (px)
    TARGET_MM = 24.0 * 25.4  # desired symbol diameter in mm (24 inches)
    SCALE = TARGET_MM / SVG_NATURAL_PX  # scene-unit scale factor

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.init_displayable()
        self._display_scale: float = 1.0
        self._properties = {
            "Manufacturer":    {"type": "enum",   "value": "Tyco",       "options": ["Victaulic", "Tyco", "Viking", "Central"]},
            "Model":           {"type": "enum",   "value": "",           "options": []},
            "Orientation":     {"type": "enum",   "value": "Upright",    "options": ["Upright", "Pendent", "Sidewall"]},
            "K-Factor":        {"type": "label",  "value": "5.6"},
            "Coverage Area":   {"type": "label",  "value": "130"},
            "S Spacing":       {"type": "label",  "value": "---"},
            "L Spacing":       {"type": "label",  "value": "---"},
            "Min Pressure":    {"type": "label",  "value": "7"},
            "Temperature":     {"type": "label",  "value": "155°F"},
            "Design Density":  {"type": "string", "value": "0.10"},
            "Graphic":         {"type": "enum",   "value": "Sprinkler0", "options": ["Sprinkler0", "Sprinkler1", "Sprinkler2"]},
            "Ceiling Level":   {"type": "level_ref", "value": DEFAULT_LEVEL},
            "Ceiling Offset":  {"type": "string", "value": "-50.8"},
        }

        # Selection is handled by the parent Node — the Node's shape() covers
        # the sprinkler area so clicks land on the Node directly.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

        if node is not None:
            self.setParentItem(node)
            self.setZValue(100)
            # No ItemIgnoresTransformations — symbol scales with zoom (real-world size)
            self._load_graphic(self.GRAPHICS[self._properties["Graphic"]["value"]])

    # -------------------------------------------------------------------------
    # Internal helpers

    def _load_graphic(self, svg_path: str):
        """Load an SVG file into this item and re-centre it on the node."""
        # Resolve relative to this module's directory (not CWD)
        if not os.path.isabs(svg_path):
            svg_path = os.path.join(os.path.dirname(__file__), svg_path)
        self._svg_source_path = os.path.abspath(svg_path)
        renderer = QSvgRenderer(svg_path)
        self.setSharedRenderer(renderer)
        self._renderer = renderer  # prevent garbage collection
        # Zoom-independent: always use fixed screen-pixel scale
        self._centre_on_node()

    def rescale(self, sm=None) -> None:
        """Re-centre the sprinkler at real-world scale."""
        self._centre_on_node()

    def _centre_on_node(self):
        """Centre the item on the parent node's origin (0, 0)."""
        from displayable_item import centre_svg_on_origin
        centre_svg_on_origin(self, self.TARGET_MM, self.SCALE,
                              self._display_scale, reset_pos=True)

    def shape(self) -> QPainterPath:
        """Return full bounding rect as shape so clicking anywhere on the
        sprinkler graphic selects it (not just the SVG path outlines)."""
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        """Draw the SVG, then overlay a blue glow circle when the parent
        node is selected.  Colour tinting is done at the SVG level via
        _set_svg_tint (no QPainter composition needed)."""
        # Suppress default selection dashes
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

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
        else:
            # Template sprinkler (no node) — format the raw mm value for display
            props["Ceiling Offset"] = dict(props["Ceiling Offset"])
            try:
                raw_mm = float(props["Ceiling Offset"]["value"])
            except (ValueError, TypeError):
                raw_mm = -50.8
            props["Ceiling Offset"]["value"] = self._fmt(raw_mm)
        # Show room assignment from parent node
        room_name = getattr(self.node, "_room_name", "") if self.node else ""
        if room_name:
            props["Room"] = {"type": "string", "value": room_name,
                             "readonly": True}
        return props

    def set_property(self, key: str, value):
        # Accept legacy names from old save files
        if key in ("Elevation", "Elevation Offset", "Ceiling Offset (in)"):
            key = "Ceiling Offset"
        if key not in self._properties:
            return
        self._properties[key]["value"] = value

        if key == "Graphic" and self.node is not None:
            svg_path = self.GRAPHICS.get(value)
            if svg_path:
                self._load_graphic(svg_path)
        elif key == "Level" and self.node is not None:
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
        """Copy all property values from a template Sprinkler."""
        for key, meta in template.get_properties().items():
            self.set_property(key, meta["value"])