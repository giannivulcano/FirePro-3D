import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal
from .constants import DEFAULT_LEVEL
from . import phase_registry

if TYPE_CHECKING:
    from .block_definition import BlockDefinition


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
    # User-authored display name (import dialog Source step). Blank falls back
    # to the file basename for display (Manager NAME column, browser node).
    name: str = ""
    # Project phasing (PD1): status id, saved sparse; not on the undo stack (underlays never are).
    phase: str = phase_registry.PHASE_NEW
    # Reference-graphic unification (R3/RD2): the shared reference BlockDefinition
    # that OWNS this underlay's geometry (curve-preserving, layer-tagged geoms).
    # Runtime + cache-backed — set when the batched group is built, reconstructed
    # from the underlay cache on load; deliberately NOT serialized (to_dict) so
    # .fpd stays lean. compare/repr excluded (not a value-identity field).
    definition: "BlockDefinition | None" = field(
        default=None, compare=False, repr=False)

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
        d["name"] = self.name
        phase_registry.write_element(self, d)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Underlay":
        levels = d.get("levels")
        if levels is None:
            levels = [d.get("level", DEFAULT_LEVEL)]
        u = Underlay(
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
            name = d.get("name", ""),
        )
        phase_registry.read_element(u, d)
        return u

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

        Rows are read-only labels except Phase (project-phasing PD1); other
        edits go through the browser menu.
        """
        display_name = (self.name or "").strip() or os.path.basename(self.path)
        props = {
            "Name": {"type": "label", "value": display_name},
            "File": {"type": "label", "value": os.path.basename(self.path)},
            "Path": {"type": "label", "value": self.path},
            "Type": {"type": "label", "value": self.type.upper()},
            phase_registry.ROW_KEY: phase_registry.property_row(self),
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

    def set_property(self, key: str, value) -> None:
        """The one editable panel row: Phase. Not undoable (underlays never are);
        a change marks the project unsaved (ruling R6) through the scene the
        Model Browser attached when it showed this record (``_scene_ref``)."""
        if key == phase_registry.ROW_KEY and phase_registry.set_from_row(self, value):
            sc = getattr(self, "_scene_ref", None)
            if sc is not None:
                sc._dirty = True
                sc.sceneModified.emit()      # MainWindow._on_scene_modified -> _modified

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
# `levels` and `scale_verified` are authored by the import dialog (redesign:
# the Placement multi-select + scale-evidence card), so Modify overwrites them.
# The remaining management fields (colour, line_weight_name, layer_overrides,
# hidden_layers, visible, snap, locked, opacity, line_weight) are NOT listed
# here and are therefore preserved by apply_import_params_preserving_management.
# ---------------------------------------------------------------------------
_GEOMETRY_PLACEMENT_FIELDS = (
    "type", "path", "page", "dpi", "scale", "rotation", "x", "y",
    "import_scale", "import_base_x", "import_base_y",
    "selected_layers", "layout", "import_bounds", "import_mode",
    "levels", "scale_verified", "name",
)


def apply_import_params_preserving_management(
        record: "Underlay", incoming: "Underlay",
        new_layer_names: list[str] | None = None) -> None:
    """Overwrite only geometry+placement on *record* from *incoming*.

    Management fields (colour, line_weight_name, layer_overrides,
    hidden_layers, visible, snap, locked, opacity, line_weight) are preserved.
    ``levels`` and ``scale_verified`` are dialog-authored placement (see
    ``_GEOMETRY_PLACEMENT_FIELDS``), so Modify overwrites them like geometry.
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


# ---------------------------------------------------------------------------
# Paper pass (paper-space.md s6.2 "Paper pass protocol"; s16.5). Groups are
# not category items: ``paper_pass.run_pass`` enters them in its own loop over
# ``scene.underlays``, after the owner loop.
# ---------------------------------------------------------------------------

def enter_underlay_paper_pass(ctx, record, group):
    """Plot one underlay group under the Underlay row (s16.5; records drive
    per-layer paper appearance): a model-side hidden group is left untouched;
    a hidden status hides it (PH3 R5); a status opacity sets the group
    opacity; each layer path child plots in the row colour (row off) or the
    layer's effective colour (row on), a named layer weight in true paper mm,
    an unweighted raw width at the frozen pre-MW mapping. Saves first; a
    raise mid-write unwinds the group.

    Args:
        ctx: The pass's ``paper_pass.PaperPassContext``.
        record: The group's ``Underlay`` record.
        group: The record's scene group (None when not built).

    Returns:
        The token :func:`exit_underlay_paper_pass` takes, or None for a
        missing / deleted group or one outside the crop.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QBrush, QPen
    from PyQt6.QtWidgets import QGraphicsPathItem
    from . import paper_display as pd
    from . import paper_pass, phase_display
    from .colour_tokens import is_token
    from .constants import UNDERLAY_MASK_SLOT

    if group is None:
        return None
    try:
        was_visible = group.isVisible()
    except RuntimeError:
        return None
    if not group.sceneBoundingRect().intersects(ctx.source_rect):
        return None
    und_row = ctx.row("Underlay") or pd.factory_paper_categories()["Underlay"]
    und_cat = phase_display.merge(und_row, record, keys=phase_display.UNDERLAY_KEYS)   # PH3 R5
    und_auth = pd.row_as_authored(und_cat)
    und_col = phase_display.writes(und_cat, und_auth, "color")
    tok = {"group": group, "visible": was_visible,
           "opacity": group.opacity(), "children": []}

    def write():
        if not was_visible:
            return                # model-side hidden: leave untouched
        if not und_cat.get("visible", True):   # PH3 R5: a hidden status
            group.setVisible(False)
            return
        if phase_display.forced(und_cat, "opacity"):
            group.setOpacity(und_cat["opacity"] / 100.0)   # PH3 R5 opacity
        for child in group.childItems():
            layer = child.data(1)
            if layer is None or not isinstance(child, QGraphicsPathItem):
                continue
            if child.data(UNDERLAY_MASK_SLOT):
                continue          # a mask paints the sheet, not the layer
            tok["children"].append({"item": child, "pen": child.pen(),
                                    "brush": child.brush()})
            src = getattr(child, "_colour_src", None)
            if und_col and is_token(src):
                # Row OFF: a token layer colour re-resolves at paint and
                # would ignore the row colour set below; drop it for the
                # pass (the exit puts it back). "" (No Fill) stays hidden.
                tok["children"][-1]["colour_src"] = src
                child._colour_src = None
            # D6: row ON -> the layer's effective colour; OFF -> the
            # Underlay row colour (factory Automatic = black on paper).
            colour = (pd._paper_qcolor(und_cat["color"]) if und_col
                      else pd._paper_qcolor(record.effective_layer_colour(layer)))
            if child.pen().style() == Qt.PenStyle.NoPen:
                child.setBrush(QBrush(colour))      # text batch
                continue
            pen = QPen(child.pen())
            pen.setColor(colour)
            weight_name = record.effective_layer_weight(layer)
            if weight_name:
                pen.setWidthF(pd.resolve_line_weight_mm(weight_name)
                              / max(ctx.paper_scale, 1e-9))
                pen.setCosmetic(False)  # true mm on paper (s9.9.1 pattern)
            elif child.data(7) is not None:
                # Unweighted raw width stays cosmetic: plot it at the
                # frozen pre-MW mapping -- never the canvas Auto px
                # (factor / Thin Lines dependent; MW-1 / MW-4).
                pen.setWidthF(pd.paper_legacy_pdf_px(float(child.data(7))))
            child.setPen(pen)
    return paper_pass.enter_guarded(exit_underlay_paper_pass, tok, write)


def exit_underlay_paper_pass(tok) -> None:
    """Undo :func:`enter_underlay_paper_pass` (the base underlay restore):
    each child's pen, brush and dropped ``_colour_src``, then the group's
    visibility and opacity. A deleted child or group (RuntimeError) is
    skipped; tolerates a partly-entered token."""
    for ch in tok["children"]:
        try:
            ch["item"].setPen(ch["pen"])
            ch["item"].setBrush(ch["brush"])
            if "colour_src" in ch:
                ch["item"]._colour_src = ch["colour_src"]
        except RuntimeError:
            pass
    try:
        tok["group"].setVisible(tok["visible"])
        tok["group"].setOpacity(tok["opacity"])   # PH3 R5 restore
    except RuntimeError:
        pass