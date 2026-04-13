from dataclasses import dataclass, field
from typing import Literal
from .constants import DEFAULT_USER_LAYER, DEFAULT_LEVEL


@dataclass
class Underlay:
    """
    Tracks a linked underlay file (PDF or DXF) in the project.
    The scene item is stored separately; this is the serialisable record.
    Only the *path* is stored — the file is re-read from disk on every load
    so external edits are picked up automatically (linked-file workflow).
    """
    type: Literal["pdf", "dxf"]
    path: str
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0
    rotation: float = 0.0
    opacity: float = 1.0
    locked: bool = False
    # PDF-specific
    page: int = 0
    dpi: int = 150
    # DXF-specific — store colour as hex string e.g. "#ffffff"
    colour: str = "#ffffff"
    line_weight: float = 0.0
    # Layer assignment (colour/lineweight derived from this layer at runtime)
    user_layer: str = DEFAULT_USER_LAYER
    # New fields (Revision 2)
    level: str = DEFAULT_LEVEL
    visible: bool = True
    hidden_layers: list[str] = field(default_factory=list)
    import_mode: str = "auto"

    def to_dict(self) -> dict:
        d = {
            "type":       self.type,
            "path":       self.path,
            "x":          self.x,
            "y":          self.y,
            "scale":      self.scale,
            "rotation":   self.rotation,
            "opacity":    self.opacity,
            "locked":     self.locked,
        }
        if self.type == "pdf":
            d["page"] = self.page
            d["dpi"]  = self.dpi
        elif self.type == "dxf":
            d["colour"]      = self.colour
            d["line_weight"] = self.line_weight
        d["user_layer"] = self.user_layer
        d["level"] = self.level
        d["visible"] = self.visible
        d["hidden_layers"] = list(self.hidden_layers)
        d["import_mode"] = self.import_mode
        return d

    @staticmethod
    def from_dict(d: dict) -> "Underlay":
        return Underlay(
            type        = d["type"],
            path        = d["path"],
            x           = d.get("x", 0.0),
            y           = d.get("y", 0.0),
            scale       = d.get("scale", 1.0),
            rotation    = d.get("rotation", 0.0),
            opacity     = d.get("opacity", 1.0),
            locked      = d.get("locked", False),
            page        = d.get("page", 0),
            dpi         = d.get("dpi", 150),
            colour      = d.get("colour", "#ffffff"),
            line_weight = d.get("line_weight", 0),
            user_layer    = d.get("user_layer", DEFAULT_USER_LAYER),
            level         = d.get("level", DEFAULT_LEVEL),
            visible       = d.get("visible", True),
            hidden_layers = d.get("hidden_layers", []),
            import_mode   = d.get("import_mode", "auto"),
        )