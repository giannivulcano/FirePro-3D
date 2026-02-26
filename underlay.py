from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Underlay:
    """
    Tracks a linked underlay file (PDF or DXF) in the project.
    The scene item is stored separately; this is the serialisable record.
    """
    type: Literal["pdf", "dxf"]
    path: str
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0
    # PDF-specific
    page: int = 0
    dpi: int = 150
    # DXF-specific — store colour as hex string e.g. "#ffffff"
    colour: str = "#ffffff"
    line_weight: int = 0

    def to_dict(self) -> dict:
        d = {
            "type":       self.type,
            "path":       self.path,
            "x":          self.x,
            "y":          self.y,
            "scale":      self.scale,
        }
        if self.type == "pdf":
            d["page"] = self.page
            d["dpi"]  = self.dpi
        elif self.type == "dxf":
            d["colour"]      = self.colour
            d["line_weight"] = self.line_weight
        return d

    @staticmethod
    def from_dict(d: dict) -> "Underlay":
        return Underlay(
            type        = d["type"],
            path        = d["path"],
            x           = d.get("x", 0.0),
            y           = d.get("y", 0.0),
            scale       = d.get("scale", 1.0),
            page        = d.get("page", 0),
            dpi         = d.get("dpi", 150),
            colour      = d.get("colour", "#ffffff"),
            line_weight = d.get("line_weight", 0),
        )