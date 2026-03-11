from PyQt6.QtWidgets import QGraphicsItem
from PyQt6.QtGui import QTransform
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtSvg import QSvgRenderer


class Sprinkler(QGraphicsSvgItem):
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
        self._properties = {
            "Manufacturer":    {"type": "enum",   "value": "Tyco",       "options": ["Victaulic", "Tyco", "Viking", "Central"]},
            "Model":           {"type": "enum",   "value": "",           "options": []},
            "Orientation":     {"type": "enum",   "value": "Upright",    "options": ["Upright", "Pendent", "Sidewall"]},
            "K-Factor":        {"type": "label",  "value": "5.6"},
            "Coverage Area":   {"type": "label",  "value": "130"},
            "Min Pressure":    {"type": "label",  "value": "7"},
            "Temperature":     {"type": "label",  "value": "155°F"},
            "Design Density":  {"type": "string", "value": "0.10"},
            "Graphic":         {"type": "enum",   "value": "Sprinkler0", "options": ["Sprinkler0", "Sprinkler1", "Sprinkler2"]},
            "Level":           {"type": "level_ref", "value": "Level 1"},
            "Ceiling Level":   {"type": "level_ref", "value": "Level 1"},
            "Ceiling Offset":  {"type": "string", "value": "-2"},
        }

        if node is not None:
            self.setParentItem(node)
            self.setZValue(100)
            # No ItemIgnoresTransformations — symbol scales with zoom (real-world size)
            self._load_graphic(self.GRAPHICS[self._properties["Graphic"]["value"]])

    # -------------------------------------------------------------------------
    # Internal helpers

    def _load_graphic(self, svg_path: str):
        """Load an SVG file into this item and re-centre it on the node."""
        renderer = QSvgRenderer(svg_path)
        self.setSharedRenderer(renderer)
        self._renderer = renderer  # prevent garbage collection
        # Zoom-independent: always use fixed screen-pixel scale
        self._centre_on_node()

    def rescale(self, sm=None) -> None:
        """Re-centre the sprinkler at real-world scale."""
        self._centre_on_node()

    def _centre_on_node(self):
        """Centre the item on the parent node's origin (0, 0).

        Uses a QTransform that scales then translates so the SVG centre
        maps to local (0, 0).  The symbol is sized to TARGET_MM and
        scales with zoom like all other scene geometry.
        """
        bounds = self.boundingRect()
        center = bounds.center()
        svg_natural = max(bounds.width(), bounds.height())
        s = self.TARGET_MM / svg_natural if svg_natural > 0 else self.SCALE
        # Build affine: scale about origin, then translate so centre → (0,0)
        t = QTransform(s, 0, 0, s, -s * center.x(), -s * center.y())
        self.setTransform(t)
        self.setPos(0, 0)

    # -------------------------------------------------------------------------
    # Public property API

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value):
        # Accept legacy names from old save files
        if key == "Elevation":
            key = "Ceiling Offset"
        if key == "Elevation Offset":
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
            self.node._properties["Level"]["value"] = str(value)
        elif key == "Ceiling Level" and self.node is not None:
            self.node.ceiling_level = str(value)
            self.node._properties["Ceiling Level"]["value"] = str(value)
        elif key == "Ceiling Offset" and self.node is not None:
            try:
                self.node.ceiling_offset = float(value)
            except (ValueError, TypeError):
                pass
            self.node._properties["Ceiling Offset"]["value"] = str(value)

    def set_properties(self, template: "Sprinkler"):
        """Copy all property values from a template Sprinkler."""
        for key, meta in template.get_properties().items():
            self.set_property(key, meta["value"])