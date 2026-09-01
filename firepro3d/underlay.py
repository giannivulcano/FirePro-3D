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
    colour: str = "#c0c0c0"
    line_weight: float = 0.0
    # New fields (Revision 2)
    levels: list[str] = field(default_factory=lambda: [DEFAULT_LEVEL])  # ["*"] = all levels
    snap: bool = True
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
    # Spatial bounds of area-selected geometry (raw DXF coordinates).
    # Stored so re-extraction can reproduce the same spatial filter.
    import_bounds: list[float] | None = None  # [min_x, min_y, max_x, max_y]
    # Display management & view assignment (Revision 8, spec §16.2)
    layer_overrides: dict = field(default_factory=dict)
    line_weight_name: str = ""
    # Scale provenance (redesign): True once calibrated or user-confirmed.
    scale_verified: bool = False

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
            # DM colour edits apply to vector-PDF pens too (§16.6);
            # line_weight stays dxf/dwg-only.
            d["colour"] = self.colour
        elif self.type in ("dxf", "dwg"):
            d["colour"]      = self.colour
            d["line_weight"] = self.line_weight
        d["levels"] = list(self.levels)
        d["snap"] = self.snap
        d["visible"] = self.visible
        d["hidden_layers"] = list(self.hidden_layers)
        d["import_mode"] = self.import_mode
        d["import_scale"] = self.import_scale
        d["import_base_x"] = self.import_base_x
        d["import_base_y"] = self.import_base_y
        d["selected_layers"] = list(self.selected_layers) if self.selected_layers is not None else None
        d["layout"] = self.layout
        if self.import_bounds is not None:
            d["import_bounds"] = list(self.import_bounds)
        d["layer_overrides"] = {k: dict(v)
                                for k, v in self.layer_overrides.items()}
        d["line_weight_name"] = self.line_weight_name
        d["scale_verified"] = self.scale_verified
        return d

    @staticmethod
    def from_dict(d: dict) -> "Underlay":
        levels = d.get("levels")
        if levels is None:
            levels = [d.get("level", DEFAULT_LEVEL)]
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
            # Old PDF dicts lack colour (pre-§16.6 to_dict omitted it) —
            # default to the dataclass gray so reloaded PDF vector pens keep
            # today's look; DXF keeps the legacy white fallback for
            # colour-less old files.
            colour      = d.get("colour",
                                "#c0c0c0" if d["type"] == "pdf" else "#ffffff"),
            line_weight = d.get("line_weight", 0),
            levels        = list(levels),
            snap          = d.get("snap", True),
            visible       = d.get("visible", True),
            hidden_layers = d.get("hidden_layers", []),
            import_mode   = d.get("import_mode", "auto"),
            import_scale    = d.get("import_scale", 1.0),
            import_base_x   = d.get("import_base_x", 0.0),
            import_base_y   = d.get("import_base_y", 0.0),
            selected_layers = d.get("selected_layers", None),
            layout = d.get("layout", ""),
            import_bounds = d.get("import_bounds", None),
            layer_overrides = {k: dict(v)
                               for k, v in d.get("layer_overrides", {}).items()},
            line_weight_name = d.get("line_weight_name", ""),
            scale_verified = d.get("scale_verified", False),
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

    def effective_layer_colour(self, layer: str) -> str:
        """Two-tier fallback (§16.2): layer override → underlay colour."""
        return self.layer_overrides.get(layer, {}).get("colour", self.colour)

    def effective_layer_weight(self, layer: str) -> str:
        """Two-tier fallback (§16.2): layer override → underlay weight name."""
        return self.layer_overrides.get(layer, {}).get(
            "line_weight", self.line_weight_name)

    def get_properties(self) -> dict:
        """Return property template for the property manager panel.

        All fields are read-only labels for MVP. Edits are done via
        the browser tree context menu actions.
        """
        props = {
            "File": {"type": "label", "value": os.path.basename(self.path)},
            "Path": {"type": "label", "value": self.path},
            "Type": {"type": "label", "value": self.type.upper()},
            "Levels": {"type": "label",
                       "value": "All Levels" if self.levels == ["*"]
                       else ", ".join(self.levels) or "—"},
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
        """Return the cache filename for this underlay's geometry.

        For PDF underlays the current bézier flatten tolerance (a Preferences
        knob) participates in the key, so changing it re-extracts on reload.
        DXF/DWG pass no tolerance, keeping their keys stable.
        """
        from .underlay_cache import compute_cache_key
        flatten_tol = None
        if self.type == "pdf":
            from .pdf_import_worker import current_pdf_flatten_tol
            flatten_tol = current_pdf_flatten_tol()
        return compute_cache_key(
            self.path, page=self.page, selected_layers=self.selected_layers,
            layout=self.layout, import_bounds=self.import_bounds,
            flatten_tol=flatten_tol)


# ---------------------------------------------------------------------------
# Geometry / placement fields — everything the import dialog controls.
# Management fields (levels, colour, line_weight_name, layer_overrides,
# hidden_layers, visible, snap, locked, opacity, line_weight) are NOT listed
# here and are therefore preserved by apply_import_params_preserving_management.
# ---------------------------------------------------------------------------
_GEOMETRY_PLACEMENT_FIELDS = (
    "type", "path", "page", "dpi", "scale", "rotation", "x", "y",
    "import_scale", "import_base_x", "import_base_y",
    "selected_layers", "layout", "import_bounds", "import_mode",
)


def apply_import_params_preserving_management(
        record: "Underlay", incoming: "Underlay",
        new_layer_names: list[str] | None = None) -> None:
    """Overwrite only geometry+placement on *record* from *incoming*.

    Management fields (levels, colour, line_weight_name, layer_overrides,
    hidden_layers, visible, snap, locked, opacity, line_weight) are preserved.
    If *new_layer_names* is given, prune layer_overrides/hidden_layers whose
    layer no longer exists (by-name reconciliation, mirroring refresh_underlay).

    Args:
        record: The existing underlay record to update in-place.
        incoming: A freshly constructed Underlay carrying the new import params.
        new_layer_names: Optional list of layer names present in the new
            file; used to drop stale overrides/hidden entries.
    """
    for f in _GEOMETRY_PLACEMENT_FIELDS:
        setattr(record, f, getattr(incoming, f))
    if new_layer_names is not None:
        known = set(new_layer_names)
        record.layer_overrides = {
            k: v for k, v in record.layer_overrides.items() if k in known}
        record.hidden_layers = [h for h in record.hidden_layers if h in known]