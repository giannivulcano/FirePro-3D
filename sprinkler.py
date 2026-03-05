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

    SCALE = 20 / 30          # fallback scale when uncalibrated (doubled)
    SVG_NATURAL_PX = 30.0    # natural SVG bounding-box width (px)
    TARGET_PAPER_MM = 12.0   # desired symbol diameter in paper mm

    def __init__(self, node):
        super().__init__()
        self.node = node
        self._properties = {
            "K-Factor":        {"type": "enum",   "value": "5.6",        "options": ["5.6", "8.0", "11.2", "14.0", "16.8"]},
            "Type":            {"type": "enum",   "value": "Wet",        "options": ["Wet", "Dry", "Preaction", "Deluge"]},
            "Orientation":     {"type": "enum",   "value": "Upright",    "options": ["Upright", "Pendent", "Sidewall"]},
            "Temperature":     {"type": "string", "value": "68°C"},
            "Manufacturer":    {"type": "enum",   "value": "Tyco",       "options": ["Victaulic", "Tyco", "Viking", "Central"]},
            "Graphic":         {"type": "enum",   "value": "Sprinkler0", "options": ["Sprinkler0", "Sprinkler1", "Sprinkler2"]},
            "Elevation Offset": {"type": "string", "value": "0"},
            "Coverage Area":   {"type": "string", "value": "130"},
            "Min Pressure":    {"type": "string", "value": "7"},
            "Design Density":  {"type": "string", "value": "0.10"},
        }

        if node is not None:
            self.setParentItem(node)
            self.setZValue(100)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
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
        """Re-centre (zoom-independent, so no ScaleManager needed)."""
        self._centre_on_node()

    def _centre_on_node(self):
        """Centre the item on the parent node's origin (0, 0).

        Uses a QTransform that scales then translates so the SVG centre
        maps to local (0, 0).  With ItemIgnoresTransformations this keeps
        the symbol at a fixed screen-pixel size, centred on the node.
        """
        bounds = self.boundingRect()
        center = bounds.center()
        s = self.SCALE
        # Build affine: scale about origin, then translate so centre → (0,0)
        t = QTransform(s, 0, 0, s, -s * center.x(), -s * center.y())
        self.setTransform(t)
        self.setPos(0, 0)

    # -------------------------------------------------------------------------
    # Public property API

    def get_properties(self) -> dict:
        return self._properties.copy()

    def set_property(self, key: str, value):
        # Accept legacy name from old save files
        if key == "Elevation":
            key = "Elevation Offset"
        if key not in self._properties:
            return
        self._properties[key]["value"] = value

        if key == "Graphic" and self.node is not None:
            svg_path = self.GRAPHICS.get(value)
            if svg_path:
                self._load_graphic(svg_path)
        elif key == "Elevation Offset" and self.node is not None:
            # Keep node.z_offset in sync (z_pos is recomputed from level)
            try:
                self.node.z_offset = float(value)
            except (ValueError, TypeError):
                pass

    def set_properties(self, template: "Sprinkler"):
        """Copy all property values from a template Sprinkler."""
        for key, meta in template.get_properties().items():
            self.set_property(key, meta["value"])