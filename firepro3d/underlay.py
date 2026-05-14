import os
from dataclasses import dataclass, field
from typing import Literal
from .constants import DEFAULT_LEVEL


@dataclass
class Underlay:
    """
    Tracks a linked underlay file (PDF or DXF) in the project.
    The scene item is stored separately; this is the serialisable record.
    Only the *path* is stored — the file is re-read from disk on every load
    so external edits are picked up automatically (linked-file workflow).
    """
    type: Literal["pdf", "dxf", "dwg"]
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
    # New fields (Revision 2)
    level: str = DEFAULT_LEVEL
    visible: bool = True
    hidden_layers: list[str] = field(default_factory=list)
    import_mode: str = "auto"
    # Import transform params (Revision 3) — baked into geometry coordinates;
    # stored so refresh-from-disk can re-apply the same transform.
    import_scale: float = 1.0
    import_base_x: float = 0.0
    import_base_y: float = 0.0
    selected_layers: list[str] | None = None
    layout: str = ""  # DWG layout name (empty = Model space)

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
        d["level"] = self.level
        d["visible"] = self.visible
        d["hidden_layers"] = list(self.hidden_layers)
        d["import_mode"] = self.import_mode
        d["import_scale"] = self.import_scale
        d["import_base_x"] = self.import_base_x
        d["import_base_y"] = self.import_base_y
        d["selected_layers"] = list(self.selected_layers) if self.selected_layers is not None else None
        d["layout"] = self.layout
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
            level         = d.get("level", DEFAULT_LEVEL),
            visible       = d.get("visible", True),
            hidden_layers = d.get("hidden_layers", []),
            import_mode   = d.get("import_mode", "auto"),
            import_scale    = d.get("import_scale", 1.0),
            import_base_x   = d.get("import_base_x", 0.0),
            import_base_y   = d.get("import_base_y", 0.0),
            selected_layers = d.get("selected_layers", None),
            layout = d.get("layout", ""),
        )

    @staticmethod
    def relativize_path(abs_path: str, project_dir: str) -> str:
        """Convert absolute path to relative if the result is sensible.

        Returns absolute path if the relative form requires 3+ parent
        traversals (``../../../`` or deeper) or if the paths are on
        different drives (Windows).
        """
        try:
            rel = os.path.relpath(abs_path, project_dir)
        except ValueError:
            return abs_path
        parts = rel.replace("\\", "/").split("/")
        parent_count = sum(1 for p in parts if p == "..")
        if parent_count >= 3:
            return abs_path
        return rel

    @staticmethod
    def resolve_path(stored_path: str, project_dir: str) -> str | None:
        """Resolve a stored underlay path to an existing absolute path.

        Returns ``None`` if the file cannot be found.

        Resolution order:
        1. If relative, resolve against *project_dir*.
        2. If that doesn't exist, try stored path as absolute.
        3. If absolute and exists, return as-is.
        """
        if os.path.isabs(stored_path):
            if os.path.exists(stored_path):
                return stored_path
            return None
        resolved = os.path.normpath(os.path.join(project_dir, stored_path))
        if os.path.exists(resolved):
            return resolved
        if os.path.exists(stored_path):
            return stored_path
        return None

    def get_properties(self) -> dict:
        """Return property template for the property manager panel.

        All fields are read-only labels for MVP. Edits are done via
        the browser tree context menu actions.
        """
        props = {
            "File": {"type": "label", "value": os.path.basename(self.path)},
            "Path": {"type": "label", "value": self.path},
            "Type": {"type": "label", "value": self.type.upper()},
            "Level": {"type": "label",
                       "value": "All Levels" if self.level == "*"
                       else self.level},
            "X": {"type": "label", "value": f"{self.x:.1f}"},
            "Y": {"type": "label", "value": f"{self.y:.1f}"},
            "Scale": {"type": "label", "value": str(self.scale)},
            "Rotation": {"type": "label", "value": f"{self.rotation:.1f}\u00b0"},
            "Opacity": {"type": "label", "value": f"{self.opacity:.0%}"},
            "Locked": {"type": "label",
                        "value": "Yes" if self.locked else "No"},
            "Visible": {"type": "label",
                         "value": "Yes" if self.visible else "No"},
            "Import Scale": {"type": "label",
                              "value": f"{self.import_scale:.6g}"},
        }
        if self.type == "pdf":
            props["DPI"] = {"type": "label", "value": str(self.dpi)}
            props["Page"] = {"type": "label", "value": str(self.page + 1)}
            props["Import Mode"] = {"type": "label", "value": self.import_mode}
        if self.type == "dwg" and self.layout:
            props["Layout"] = {"type": "label", "value": self.layout}
        if self.hidden_layers:
            props["Hidden Layers"] = {
                "type": "label",
                "value": ", ".join(self.hidden_layers)}
        return props

    def cache_key(self) -> str:
        """Return the cache filename for this underlay's geometry."""
        from .underlay_cache import compute_cache_key
        return compute_cache_key(
            self.path, page=self.page, selected_layers=self.selected_layers,
            layout=self.layout)