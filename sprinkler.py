from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtSvg import QSvgRenderer


class Sprinkler(QGraphicsSvgItem):
    GRAPHICS = {
        "Sprinkler0": r"graphics/sprinkler_graphics/sprinkler0.svg",
        "Sprinkler1": r"graphics/sprinkler_graphics/sprinkler1.svg",
        "Sprinkler2": r"graphics/sprinkler_graphics/sprinkler2.svg"
    }

    SCALE = 10 / 30

    def __init__(self, node):
        super().__init__()
        self.node = node
        self._properties = {
            "K-Factor":     {"type": "enum",    "value": "5.6",        "options": ["5.6", "8.0", "12.0"]},
            "Type":         {"type": "enum",    "value": "Wet",        "options": ["Wet", "Dry", "Preaction", "Deluge"]},
            "Orientation":  {"type": "enum",    "value": "Upright",    "options": ["Upright", "Pendent", "Sidewall"]},
            "Temperature":  {"type": "string",  "value": "68°C"},
            "Manufacturer": {"type": "enum",    "value": "Tyco",       "options": ["Victaulic", "Tyco"]},
            "Graphic":      {"type": "enum",    "value": "Sprinkler0", "options": ["Sprinkler0", "Sprinkler1", "Sprinkler2"]},
            "Elevation":    {"type": "string",  "value": "0"},
        }

        if node is not None:
            self.setParentItem(node)
            self.setZValue(100)
            self._load_graphic(self.GRAPHICS[self._properties["Graphic"]["value"]])

    # -------------------------------------------------------------------------
    # Internal helpers

    def _load_graphic(self, svg_path: str):
        """Load an SVG file into this item and re-centre it on the node."""
        renderer = QSvgRenderer(svg_path)
        self.setSharedRenderer(renderer)
        self._renderer = renderer  # prevent garbage collection
        self.setScale(self.SCALE)
        self._centre_on_node()

    def _centre_on_node(self):
        """Centre the scaled item on the parent node's origin (0, 0)."""
        bounds = self.boundingRect()          # unscaled local rect
        # Multiply by SCALE to get the actual painted size
        scaled_w = bounds.width()  * self.SCALE
        scaled_h = bounds.height() * self.SCALE
        # Shift so the centre of the painted graphic lands on (0, 0)
        self.setPos(-scaled_w / 2, -scaled_h / 2)

    # -------------------------------------------------------------------------
    # Public property API

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value):
        if key not in self._properties:
            return
        self._properties[key]["value"] = value

        if key == "Graphic" and self.node is not None:
            svg_path = self.GRAPHICS.get(value)
            if svg_path:
                self._load_graphic(svg_path)

    def set_properties(self, template: "Sprinkler"):
        """Copy all property values from a template Sprinkler."""
        for key, meta in template.get_properties().items():
            self.set_property(key, meta["value"])