"""
paper_display.py
================
Paper-space display settings -- line weight definitions, per-category
overrides (colour, fill, line weight, opacity), and color mode state.

Provides the data layer and QSettings persistence for the paper-space
tab in the Display Manager dialog.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QSettings

from .constants import (MODEL_WEIGHT_FACTOR, MODEL_WEIGHT_FACTOR_MIN,
                        MODEL_WEIGHT_FACTOR_MAX, MODEL_WEIGHT_PX_MAX,
                        MODEL_BLOCKS_FACTORY_MM)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Line weight definitions
# ---------------------------------------------------------------------------

@dataclass
class LineWeightDef:
    """A named pen weight: paper mm + optional canvas Model override (MW-2)."""
    name: str
    width_mm: float
    model_px: int | None = None      # whole canvas px 1..20; None = Auto

    def copy(self) -> "LineWeightDef":
        """An independent copy carrying every field (H-MW-a)."""
        return LineWeightDef(self.name, float(self.width_mm), self.model_px)

    def to_dict(self) -> dict:
        """Persisted form; ``model_px`` omitted when Auto (Δ6)."""
        d = {"name": self.name, "width_mm": self.width_mm}
        if self.model_px is not None:
            d["model_px"] = int(self.model_px)
        return d


# MW-4: the user standard (2026-10-04).
FACTORY_LINE_WEIGHTS: list[LineWeightDef] = [
    LineWeightDef("Thinnest", 0.18),
    LineWeightDef("Thinner",  0.25),
    LineWeightDef("Thin",     0.35),
    LineWeightDef("Thick",    0.50),
    LineWeightDef("Thickest", 0.70),
]
# The pre-MW factory: an untouched template equal to it migrates (MW-4), and
# its names resolve by their mm wherever a table lacks them (MW-6).
LEGACY_FACTORY_LINE_WEIGHTS: list[LineWeightDef] = [
    LineWeightDef("Very Light", 0.13),
    LineWeightDef("Light",      0.18),
    LineWeightDef("Medium",     0.25),
    LineWeightDef("Heavy",      0.35),
    LineWeightDef("Very Heavy", 0.50),
]
_FACTORY_NAME_MM: dict[str, float] = {
    d.name: d.width_mm for d in (*LEGACY_FACTORY_LINE_WEIGHTS, *FACTORY_LINE_WEIGHTS)}


def validate_model_px(px) -> bool:
    """True for a whole-px Model override in 1..MODEL_WEIGHT_PX_MAX (MW-11)."""
    return (isinstance(px, int) and not isinstance(px, bool)
            and 1 <= px <= MODEL_WEIGHT_PX_MAX)


def _is_legacy_factory(defs: list[LineWeightDef]) -> bool:
    """An untouched pre-MW factory template (names + mm, no overrides)."""
    want = {(d.name, round(d.width_mm, 6)) for d in LEGACY_FACTORY_LINE_WEIGHTS}
    return (len(defs) == len(want) and all(d.model_px is None for d in defs)
            and {(d.name, round(d.width_mm, 6)) for d in defs} == want)


def load_line_weights(settings: QSettings | None = None) -> list[LineWeightDef]:
    """The new-project template (QSettings), else factory defaults.

    A stored template equal to the pre-MW factory is replaced by (and
    rewritten as) the new factory; anything else is returned as stored (MW-4).
    """
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    raw = settings.value("paper/line_weights")
    defs = None
    if raw is not None:
        try:
            defs = _parse_weight_list(json.loads(raw) if isinstance(raw, str) else raw)
        except (json.JSONDecodeError, TypeError):
            defs = None
    if defs is None:
        return [d.copy() for d in FACTORY_LINE_WEIGHTS]
    if _is_legacy_factory(defs):
        new = [d.copy() for d in FACTORY_LINE_WEIGHTS]
        save_line_weights(new, settings)
        return new
    return defs


def save_line_weights(defs: list[LineWeightDef],
                      settings: QSettings | None = None):
    """Persist line weight definitions to QSettings (the template)."""
    _clear_hatch_mm()
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    settings.setValue("paper/line_weights", json.dumps([d.to_dict() for d in defs]))
    settings.sync()


def validate_line_weight_name(name: str,
                              existing: list[LineWeightDef]) -> bool:
    """Return True if *name* is valid (non-empty, unique, not reserved).

    The style keywords (By Block / By Linetype / Continuous, in keyword or
    display spelling, any case) are reserved: a row so named would collide
    with the keyword everywhere a weight is read (LT2-8).
    """
    if not name or not name.strip():
        return False
    if name.strip().lower() in _reserved_weight_names():
        return False
    return all(lw.name != name.strip() for lw in existing)


def _reserved_weight_names() -> frozenset[str]:
    """Lower-cased names a weight row may never take."""
    from .stroke_style import BY_BLOCK, BY_LINETYPE, CONTINUOUS
    keys = (BY_BLOCK, BY_LINETYPE, CONTINUOUS)
    return frozenset({*keys, *(k.replace("_", " ") for k in keys)})


def validate_line_weight_width(width_mm: float) -> bool:
    """Return True if *width_mm* is valid (positive, <= 3.0)."""
    return 0.0 < width_mm <= 3.0


# ---------------------------------------------------------------------------
# Project weight table (linetypes.md LT1-3 / H1)
# ---------------------------------------------------------------------------
# The LIVE named-weight table is project-scoped: saved in the .fpd and bundled
# into .fpdb files. QSettings (load_line_weights / save_line_weights) is only
# the TEMPLATE new projects and table-less files copy. Lazily seeded from the
# template so headless callers (and tests that patch load_line_weights) work.

_PROJECT_LW: list[LineWeightDef] | None = None
_THIN_LINES = False
# >0 while a paper pass (apply_paper_overrides .. restore_model_display) is
# live: Thin Lines is a view toggle and never reaches paper/PDF (LT1-8).
_THIN_SUSPEND = 0
# MW-2: System factor (QSettings view/model_weight_factor), cached so paint
# never reads QSettings; MainWindow restores it at startup.
_MODEL_FACTOR: float = MODEL_WEIGHT_FACTOR


def model_weight_factor() -> float:
    """Canvas px per paper mm for Auto weights (MW-2)."""
    return _MODEL_FACTOR


def set_model_weight_factor(factor) -> None:
    """Set the factor; anything unparseable / out of 1..20 -> factory 8."""
    global _MODEL_FACTOR
    try:
        f = float(factor)
    except (TypeError, ValueError):
        f = MODEL_WEIGHT_FACTOR
    if not (MODEL_WEIGHT_FACTOR_MIN <= f <= MODEL_WEIGHT_FACTOR_MAX):
        f = MODEL_WEIGHT_FACTOR
    _MODEL_FACTOR = f

# Rename aliases (linetypes.md LT2-8 / H-g): old name -> current name, so a
# reference written before a rename (undo snapshot, clipboard, paper command,
# library file, open editor) still resolves. Project-scoped (.fpd), reset with
# the table on New / table-less Open.
_WEIGHT_ALIASES: dict[str, str] = {}
# Display Manager Model "Blocks" weight (LT2-4/LT2-6) -- the canvas weight of
# By Linetype strokes with no dash weight (WM-5). Cached here so paint never
# reads QSettings.
_MODEL_BLOCKS_WEIGHT: str | None = None


def model_blocks_factory_weight() -> str:
    """Factory Model "Blocks" weight: the row nearest 0.18 mm (MW-5)."""
    return nearest_weight_name(MODEL_BLOCKS_FACTORY_MM)


def model_blocks_weight() -> str:
    """The Model-tab "Blocks" weight name (factory: nearest 0.18 mm)."""
    return _MODEL_BLOCKS_WEIGHT or model_blocks_factory_weight()


def set_model_blocks_weight(name: str | None, *, canonical: bool = True) -> None:
    """Set the Model "Blocks" weight (None -> factory).

    A renamed-away name is stored canonical (H-g), so the in-use check and
    the combo see the live row name. ``canonical=False`` is only for the
    Display Manager Cancel replay, which restores a pre-rename name BEFORE
    the table and aliases are restored.
    """
    global _MODEL_BLOCKS_WEIGHT
    if not name:
        _MODEL_BLOCKS_WEIGHT = None
    else:
        _MODEL_BLOCKS_WEIGHT = (canonical_weight_name(str(name)) if canonical
                                else str(name))


def weight_aliases() -> dict[str, str]:
    """A copy of the project rename-alias map."""
    return dict(_WEIGHT_ALIASES)


def set_weight_aliases(aliases: dict | None) -> None:
    """Replace the alias map (Cancel snapshot restore / project load).

    Keeps the invariant "an alias key is never a live table name" (as
    ``set_project_line_weights`` does): keys that are live rows of the
    CURRENT table are dropped. Every caller installs the table first
    (``apply_project_weights``, Cancel restore, reset), so the current table
    is the one the aliases belong to.
    """
    global _WEIGHT_ALIASES
    live = {d.name for d in (_PROJECT_LW or ())}
    _WEIGHT_ALIASES = {str(k): str(v) for k, v in (aliases or {}).items()
                       if k and v and k != v and str(k) not in live}
    _clear_hatch_mm()


def record_weight_rename(old: str, new: str) -> None:
    """Record a table rename *old* -> *new* (call after the table changed).

    Collapses chains (X->old becomes X->new) and drops an entry keyed by
    *new* (renaming back makes *new* a live name again).
    """
    if not old or not new or old == new:
        return
    aliases = {k: (new if v == old else v) for k, v in _WEIGHT_ALIASES.items()}
    aliases.pop(new, None)
    aliases[old] = new
    set_weight_aliases(aliases)


def canonical_weight_name(name: str) -> str:
    """Follow the alias chain from *name* (cycle-guarded); identity if none."""
    seen = set()
    cur = name
    while cur in _WEIGHT_ALIASES and cur not in seen:
        seen.add(cur)
        cur = _WEIGHT_ALIASES[cur]
    return cur


def is_alias_key(name: str) -> bool:
    """True if *name* is an old (renamed-away) weight name."""
    return name in _WEIGHT_ALIASES


def project_line_weights() -> list[LineWeightDef]:
    """The live project weight table (seeded from the template on first use).

    Callers must not mutate the result (or its defs); use
    ``set_project_line_weights`` to change the table.
    """
    if _PROJECT_LW is None:
        set_project_line_weights(load_line_weights())   # copies the defs
    return _PROJECT_LW


def set_project_line_weights(defs: list[LineWeightDef]) -> None:
    """Replace the live project table (copies *defs*).

    Keeps the invariant "an alias key is never a live table name": any rename
    alias whose old name is now a table row is dropped (the name is live again).
    """
    global _PROJECT_LW, _WEIGHT_ALIASES
    _PROJECT_LW = [d.copy() for d in defs]
    live = {d.name for d in _PROJECT_LW}
    _WEIGHT_ALIASES = {k: v for k, v in _WEIGHT_ALIASES.items()
                       if k not in live}
    _clear_hatch_mm()


def reset_project_line_weights() -> None:
    """Re-seed the project table from the template (New Project / old files).

    Also clears the rename aliases (they are project-scoped, LT2-8).
    """
    set_project_line_weights(load_line_weights())
    set_weight_aliases({})


def weight_names() -> list[str]:
    """Project weight names sorted by width — the source for every picker."""
    return [d.name for d in sorted(project_line_weights(),
                                   key=lambda d: d.width_mm)]


def merge_project_line_weights(weights: dict, model_px: dict | None = None) -> list[str]:
    """Add bundled ``{name: mm}`` weights the project lacks (project wins).

    *model_px* is the bundle's ``weight_model_px`` ``{name: px}`` (H-MW-a);
    an added row takes its valid override. Returns the names added. Invalid
    widths are skipped.
    """
    have = {d.name for d in project_line_weights()} | set(_WEIGHT_ALIASES)
    added = []
    for name, mm in (weights or {}).items():
        try:
            mm = float(mm)
        except (TypeError, ValueError):
            continue
        if name in have or not name or not validate_line_weight_width(mm):
            continue
        px = (model_px or {}).get(name)
        added.append(LineWeightDef(str(name), mm,
                                   px if validate_model_px(px) else None))
        have.add(name)
    if added:
        set_project_line_weights([*project_line_weights(), *added])
    return [d.name for d in added]


# ---------------------------------------------------------------------------
# Canvas mapping + Thin Lines (linetypes.md LT1-7 / LT1-8, D-L14)
# ---------------------------------------------------------------------------

def set_thin_lines(on: bool) -> None:
    """Global Thin Lines view toggle (model + Block Editor views, never paper)."""
    global _THIN_LINES
    _THIN_LINES = bool(on)


def thin_lines() -> bool:
    """True while Thin Lines is on (the user toggle, pass-independent)."""
    return _THIN_LINES


def thin_lines_active() -> bool:
    """True when Thin Lines applies to strokes painted/baked right now.

    False during a paper pass even with the toggle on, so canvas-mapped pens
    a viewport plots (text borders, unweighted PDF-underlay widths) keep
    their non-thin width on sheets and PDF (LT1-8).
    """
    return _THIN_LINES and _THIN_SUSPEND == 0


def paper_pass_active() -> bool:
    """True while a paper pass is live (apply_paper_overrides ..
    restore_model_display).

    Paint-time canvas pen derivation (``Geometry2DMixin._sync_stroke_pen``)
    must leave the pen alone during the pass: re-deriving there would resolve
    the non-thin width and flip it back on the next model paint, a setPen /
    scene.changed ping-pong against the paper echo guard (LT2 H-c).
    """
    return _THIN_SUSPEND > 0


def auto_model_px(width_mm: float) -> int:
    """Auto canvas width (MW-3): round-half-up(mm x factor), min 1 -- the
    value the Line Weights tab shows as "Auto (n)" (Thin Lines ignored)."""
    return max(1, math.floor(width_mm * _MODEL_FACTOR + 0.5))


def canvas_weight_px(width_mm: float) -> float:
    """Cosmetic canvas width for a raw paper mm (raw PDF widths, H-MW-c).

    Thin Lines -> 1.0 (except during a paper pass -- see thin_lines_active).
    """
    if thin_lines_active():
        return 1.0
    return float(auto_model_px(width_mm))


def canvas_px_for_weight(name: str) -> float:
    """Cosmetic canvas width for a named weight (H-MW-c): Thin Lines -> 1;
    else the resolved row's Model override; else Auto of its mm."""
    if thin_lines_active():
        return 1.0
    d = _resolve_def(name)
    if d is not None and d.model_px is not None:
        return float(d.model_px)
    return float(auto_model_px(d.width_mm if d is not None else 0.25))


def _parse_weight_list(raw) -> list[LineWeightDef] | None:
    """``[{"name", "width_mm"}, ...]`` -> defs, or None when absent/malformed."""
    if not raw:
        return None
    out: list[LineWeightDef] = []
    seen: set[str] = set()
    try:
        for e in raw:
            try:
                name, mm = str(e["name"]), float(e["width_mm"])
            except (KeyError, TypeError, ValueError):
                continue
            if not name or name in seen or not validate_line_weight_width(mm):
                continue
            px = e.get("model_px") if isinstance(e, dict) else None
            seen.add(name)
            out.append(LineWeightDef(name, mm, px if validate_model_px(px) else None))
    except TypeError:                      # raw not iterable
        return None
    return out or None


# ---------------------------------------------------------------------------
# Color mode
# ---------------------------------------------------------------------------

class PaperColorMode(Enum):
    """Paper-space color rendering mode."""
    FULL_COLOR = "full_color"
    BW = "bw"
    CUSTOM = "custom"


def load_paper_color_mode(settings: QSettings | None = None) -> PaperColorMode:
    """Load paper color mode from QSettings, defaulting to B&W."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    raw = settings.value("paper/color_mode")
    try:
        return PaperColorMode(raw)
    except (ValueError, KeyError):
        return PaperColorMode.BW


def save_paper_color_mode(mode: PaperColorMode,
                          settings: QSettings | None = None):
    """Persist paper color mode to QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    settings.setValue("paper/color_mode", mode.value)
    settings.sync()


# ---------------------------------------------------------------------------
# Per-category paper-space overrides
# ---------------------------------------------------------------------------

# Keys match _CATEGORIES in display_manager.py
_CATEGORY_KEYS = [
    "Pipe", "Sprinkler", "Fitting", "Water Supply", "Node",
    "Hydraulic Badge", "Wall", "Door", "Window", "Opening", "Roof", "Room",
    "Floor", "Grid Line", "Level Datum", "Elevation Marker", "Detail Marker",
    "Construction", "Hatch", "Blocks",
]

# Which categories have a fill colour (mirrors display_manager._CATEGORIES)
_HAS_FILL = {"Sprinkler", "Water Supply", "Hydraulic Badge", "Wall", "Roof",
             "Room", "Floor", "Grid Line", "Level Datum", "Elevation Marker",
             "Detail Marker"}

# Which categories have section colour
_HAS_SECTION = {"Wall", "Roof", "Floor"}

# Categories where only the line weight is meaningful (D-A31): the Display
# Manager disables every other cell and its colour-mode / reset loops skip them.
_LW_ONLY = {"Hatch"}

# Factory paper weight per category as an intended paper mm (MW-5: today's
# printed widths; resolved to the nearest live row when materialised).
_FACTORY_LW_MM = {
    "Pipe": 0.25, "Sprinkler": 0.25, "Fitting": 0.25, "Water Supply": 0.25,
    "Node": 0.18, "Hydraulic Badge": 0.13, "Wall": 0.35, "Roof": 0.25,
    "Room": 0.13, "Floor": 0.25, "Door": 0.18, "Window": 0.18,
    "Opening": 0.18, "Grid Line": 0.25, "Level Datum": 0.13,
    "Elevation Marker": 0.13, "Detail Marker": 0.18, "Construction": 0.18,
    "Hatch": 0.13,
    "Blocks": 0.18,         # paper-only, no fill/section (linetypes.md LT1-2)
}


def _make_factory_category(key: str) -> dict:
    """Build the factory default paper-space settings for one category."""
    cat = {
        "color": "#000000",
        "fill": "#ffffff" if key in _HAS_FILL else None,
        "section_color": "#000000" if key in _HAS_SECTION else None,
        "line_weight": nearest_weight_name(_FACTORY_LW_MM[key]),
        "opacity": 100,
        "visible": True,
    }
    if key == "Grid Line":
        cat["bubble_label_height_mm"] = 3.0
    if key == "Room":
        # Fixed ON-PAPER cap height for the room tag label (§9.9). Without this
        # the label is model-unit sized and shrinks to sub-pixel at plot scale.
        cat["label_height_mm"] = 2.5
    return cat


def factory_paper_categories() -> dict[str, dict]:
    """Factory paper categories against the LIVE project table (Δ6 -- was the
    import-time FACTORY_PAPER_CATEGORIES dict)."""
    return {k: _make_factory_category(k) for k in _CATEGORY_KEYS}


def load_paper_categories(settings: QSettings | None = None) -> dict[str, dict]:
    """Load paper-space category overrides from QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    result: dict[str, dict] = {}
    factory_all = factory_paper_categories()
    for key in _CATEGORY_KEYS:
        factory = factory_all[key]
        # Start with factory defaults so any new keys are backfilled automatically.
        entry: dict = dict(factory)
        for prop in ("color", "fill", "section_color", "line_weight",
                     "opacity", "visible"):
            raw = settings.value(f"paper/categories/{key}/{prop}")
            if raw is not None:
                if prop == "opacity":
                    entry[prop] = int(float(raw))
                elif prop == "visible":
                    if isinstance(raw, bool):
                        entry[prop] = raw
                    elif isinstance(raw, str):
                        entry[prop] = raw.lower() not in ("false", "0")
                    else:
                        entry[prop] = bool(raw)
                else:
                    entry[prop] = raw
            # else: factory default already set above
        # Load any category-specific numeric extras (e.g. bubble_label_height_mm).
        for prop in factory:
            if prop not in entry or prop not in ("color", "fill", "section_color",
                                                  "line_weight", "opacity", "visible"):
                raw = settings.value(f"paper/categories/{key}/{prop}")
                if raw is not None:
                    try:
                        entry[prop] = float(raw)
                    except (ValueError, TypeError):
                        pass  # unparseable stored value — keep factory default
                # else: factory default already in entry from dict(factory) above
        result[key] = entry
    return result


def save_paper_categories(cats: dict[str, dict],
                          settings: QSettings | None = None):
    """Persist paper-space category overrides to QSettings."""
    _clear_hatch_mm()
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    factory_all = factory_paper_categories()
    for key in _CATEGORY_KEYS:
        entry = cats.get(key, factory_all[key])
        for prop in ("color", "fill", "section_color", "line_weight",
                     "opacity", "visible"):
            val = entry.get(prop)
            if val is not None:
                settings.setValue(f"paper/categories/{key}/{prop}",
                                 str(val).lower() if prop == "visible" else val)
            else:
                settings.remove(f"paper/categories/{key}/{prop}")
        # Persist any category-specific numeric extras present in the factory.
        factory = factory_all[key]
        for prop in factory:
            if prop not in ("color", "fill", "section_color",
                            "line_weight", "opacity", "visible"):
                val = entry.get(prop)
                if val is not None:
                    settings.setValue(f"paper/categories/{key}/{prop}", val)
                else:
                    settings.remove(f"paper/categories/{key}/{prop}")
    settings.sync()


# ---------------------------------------------------------------------------
# Project file persistence
# ---------------------------------------------------------------------------

def get_paper_display_for_save() -> dict:
    """Return paper display settings for embedding in the project file."""
    return {
        "color_mode": load_paper_color_mode().value,
        "categories": load_paper_categories(),
        "line_weights": [d.to_dict() for d in project_line_weights()],
        "line_weight_aliases": weight_aliases(),
    }


def apply_project_weights(data: dict | None) -> None:
    """Install a project file's weight table, then its rename aliases.

    Called at the top of ``load_from_file`` (before any definition / text
    parse canonicalises weight names -- else the PREVIOUS project's aliases
    would rewrite this file's names) and again by
    ``apply_paper_display_from_project`` (same values; idempotent).
    """
    data = data if isinstance(data, dict) else {}
    parsed = _parse_weight_list(data.get("line_weights"))
    if parsed is None:
        reset_project_line_weights()       # old file / no paper_display -> template
    else:
        set_project_line_weights(parsed)   # never touches QSettings (LT1-3)
        set_weight_aliases(data.get("line_weight_aliases"))


def apply_paper_display_from_project(data: dict | None):
    """Apply paper display settings loaded from a project file."""
    apply_project_weights(data)
    if not data:
        # No paper_display in project -- reset to factory
        save_paper_color_mode(PaperColorMode.BW)
        save_paper_categories(factory_paper_categories())
        return
    # Color mode
    mode_str = data.get("color_mode", "bw")
    try:
        mode = PaperColorMode(mode_str)
    except ValueError:
        mode = PaperColorMode.BW
    save_paper_color_mode(mode)
    # Categories -- merge project values over factory defaults
    proj_cats = data.get("categories", {})
    merged: dict[str, dict] = {}
    factory_all = factory_paper_categories()
    for key in _CATEGORY_KEYS:
        factory = factory_all[key]
        proj = proj_cats.get(key, {})
        entry = dict(factory)
        entry.update({k: v for k, v in proj.items() if v is not None})
        merged[key] = entry
    save_paper_categories(merged)


# ---------------------------------------------------------------------------
# Viewport rendering helpers
# ---------------------------------------------------------------------------

def _nearest_def(mm: float, defs) -> LineWeightDef | None:
    """Exact-mm row, else the nearest (tie -> thinner) -- MW-5 / MW-6."""
    defs = list(defs)
    if not defs:
        return None
    for d in defs:
        if abs(d.width_mm - mm) < 1e-9:
            return d
    return min(defs, key=lambda d: (abs(d.width_mm - mm), d.width_mm))


def nearest_weight_name(mm: float) -> str:
    """Live project row for an intended paper mm ("" for an empty table)."""
    d = _nearest_def(mm, project_line_weights())
    return d.name if d is not None else ""


def _resolve_def(name: str, defs=None, canonical: bool = True) -> LineWeightDef | None:
    """The row a weight reference draws with: exact (after aliases), else a
    factory name -- old or new set -- via its factory mm to the nearest row
    (MW-6), else None."""
    if defs is None:
        defs = project_line_weights()
    if canonical:
        name = canonical_weight_name(name)
    for d in defs:
        if d.name == name:
            return d
    mm = _FACTORY_NAME_MM.get(name)
    return _nearest_def(mm, defs) if mm is not None else None


def live_weight_name(name: str) -> str | None:
    """The live row a weight name draws as (MW-6), or None if it resolves to
    no row (an unknown, non-factory name)."""
    d = _resolve_def(name)
    return d.name if d is not None else None


def picker_weight_name(name):
    """The name a weight picker shows as selected for a stored *name*: the
    live row it draws as (MW-6), else *name* unchanged (unknown names and
    keywords keep today's display). Display only -- never stored back."""
    if not name:
        return name
    live = live_weight_name(name)
    return live if live is not None else name


def resolve_line_weight_mm(name: str,
                           settings: QSettings | None = None) -> float:
    """Resolve a line weight name to its mm width.  Falls back to 0.25mm.

    Reads the live PROJECT table; an explicit *settings* reads that template
    store instead (Display Manager / tests).
    """
    if settings is not None:
        d = _resolve_def(name, load_line_weights(settings), canonical=False)
    else:
        d = _resolve_def(name)
    return d.width_mm if d is not None else 0.25


_HATCH_MM: float | None = None


def hatch_line_mm() -> float:
    """Paper width (mm) of pattern lines — the "Hatch" category weight (D-A31).

    Cached: paint calls it per fill. ``save_paper_categories`` /
    ``save_line_weights`` clear the cache.
    """
    global _HATCH_MM
    if _HATCH_MM is None:
        cat = load_paper_categories().get("Hatch", {})
        _HATCH_MM = resolve_line_weight_mm(cat.get("line_weight", "Very Light"))
    return _HATCH_MM


def _clear_hatch_mm() -> None:
    global _HATCH_MM
    _HATCH_MM = None


def _is_detail_marker(item) -> bool:
    """Return True if *item* is a DetailMarker instance."""
    from .detail_view import DetailMarker
    return isinstance(item, DetailMarker)


def _category_for_item(item) -> str | None:
    """Map a QGraphicsItem to its display category key."""
    from .pipe import Pipe
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .node import Node
    from .gridline import GridlineItem
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .wall import WallSegment
    from .wall_opening import WallOpening
    from .room import Room

    if isinstance(item, Pipe):
        return "Pipe"
    if isinstance(item, Sprinkler):
        return "Sprinkler"
    if isinstance(item, WallSegment):
        return "Wall"
    if isinstance(item, WallOpening):
        return item.display_category
    if isinstance(item, Room):
        return "Room"
    if isinstance(item, Node):
        return "Node"
    if isinstance(item, WaterSupply):
        return "Water Supply"
    if isinstance(item, GridlineItem):
        return "Grid Line"
    if isinstance(item, HydraulicNodeBadge):
        return "Hydraulic Badge"
    from .block_instance import BlockInstance
    if isinstance(item, BlockInstance):
        return "Blocks"
    # Detect by class name to avoid circular imports
    cls_name = type(item).__name__
    if cls_name == "RoofItem":
        return "Roof"
    if cls_name == "FloorSlab":
        return "Floor"
    if cls_name == "ViewMarkerArrow":
        return "Elevation Marker"
    if cls_name == "DetailMarker":
        return "Detail Marker"
    if cls_name == "LevelDatumItem":
        return "Level Datum"
    # Construction / draw geometry — pen-only paper category. These read
    # self.pen() directly in paint(), so they default to white (#ffffff) and
    # are invisible on white paper unless remapped (see _apply_construction).
    try:
        from .geometry_2d import (
            PolylineItem, LineItem, ReferenceLineItem,
            RectangleItem, CircleItem, ArcItem,
        )
        if isinstance(item, ReferenceLineItem):   # subclass — check before LineItem
            return "Reference Lines"
        if isinstance(item, (PolylineItem, LineItem,
                             RectangleItem, CircleItem, ArcItem)):
            return "Construction"
    except ImportError:  # pragma: no cover - defensive fallback
        if cls_name == "ReferenceLineItem":
            return "Reference Lines"
        if cls_name in ("PolylineItem", "LineItem",
                        "RectangleItem", "CircleItem", "ArcItem"):
            return "Construction"
    return None


def _apply_generic(item, cat, color_mode, lw_mm, paper_scale: float = 1.0):
    """Apply paper overrides to a generic item (Wall, Door / Window / Opening, Room, Floor, Roof).

    ``_paper_pen_width`` (true on-paper mm in model units, §9.9.1) is read by
    ``DisplayableItemMixin._outline_pen`` in the outline-painting items.
    """
    if color_mode != PaperColorMode.FULL_COLOR:
        item._display_color = cat["color"]
        if hasattr(item, "_display_fill_color") and cat["fill"] is not None:
            item._display_fill_color = cat["fill"]
        if hasattr(item, "_display_section_color") and cat["section_color"] is not None:
            item._display_section_color = cat["section_color"]
    # Paper-space fill should render opaque (not semi-transparent like model).
    # Items like FloorSlab/Room use alpha 50 in model-space paint(); setting
    # _paper_fill_opaque tells them to skip the alpha reduction.
    item._paper_fill_opaque = True
    # Rooms plot as boundary + tag only — suppress the fill entirely in
    # viewports (a filled room reads as a solid blob on the sheet).
    from .room import Room
    if isinstance(item, Room):
        item._paper_no_fill = True
    item._paper_pen_width = lw_mm / max(paper_scale, 1e-9)
    item.setOpacity(cat["opacity"] / 100.0)
    item.update()


def _apply_room_label_paper_height(room, cat, color_mode, paper_scale, entry):
    """Size + colour the room tag label for paper (§9.9).

    Size: the label font is stored in model (scene) units and rendered through
    the viewport at ``paper_scale`` (paper mm per model mm), so a raw model size
    plots at ``size × paper_scale`` — shrinking to sub-pixel at architectural
    scales. Dividing the target paper height by ``paper_scale`` makes the label
    render at a constant on-paper size regardless of viewport scale (the same
    true-scale trick as gridline bubbles).

    Colour: the model label colour comes from the *model* Display Manager "Room"
    colour, which is light for readability on the dark canvas — invisible on
    white paper (white-on-white). In B&W / custom modes force the paper "Room"
    category colour (black by default) so the tag reads; full-colour keeps the
    authored colour. Original size + colour are saved on *entry* and restored by
    ``restore_model_display``.
    """
    S = max(paper_scale, 1e-9)
    cap_mm = cat.get("label_height_mm", 2.5)
    entry["room_label_font_size"] = room._label_font_size
    entry["room_label_font_color"] = room._label_font_color
    room._label_font_size = cap_mm / S
    if color_mode != PaperColorMode.FULL_COLOR:
        room._label_font_color = cat["color"]
    room._update_label()


def _apply_construction(item, cat, color_mode, lw_mm, paper_scale):
    """Apply paper overrides to construction/draw geometry.

    These items read ``self.pen()`` directly in paint(), so the PEN COLOR (not
    just ``_display_color``) must be set for them to render in paper colours.

    The pen width is normalised to true ON-PAPER mm: the pen lives in model
    (scene) units and is rendered through the viewport at ``paper_scale`` (paper
    mm per model mm), so a raw ``lw_mm`` would plot at ``lw_mm × paper_scale`` —
    a sub-pixel hairline at architectural scales. Dividing by ``paper_scale``
    (non-cosmetic) makes it plot at ``lw_mm`` on paper regardless of scale,
    matching the gridline/underlay convention (§9.9.1).
    """
    from PyQt6.QtGui import QColor
    if hasattr(item, "pen") and callable(getattr(item, "setPen", None)):
        pen = item.pen()
        if color_mode != PaperColorMode.FULL_COLOR:
            pen.setColor(QColor(cat["color"]))
        pen.setWidthF(lw_mm / max(paper_scale, 1e-9))
        pen.setCosmetic(False)
        item.setPen(pen)
    item.setOpacity(cat["opacity"] / 100.0)
    item.update()


def _apply_pipe(pipe, cat, color_mode, lw_mm, paper_scale):
    """Apply paper overrides to a Pipe — uses _paper_pen_width hook.

    The pen width is normalised to true ON-PAPER mm (§9.9.1, matching
    ``_apply_construction`` / gridlines): ``Pipe.paint`` applies
    ``_paper_pen_width`` as a **non-cosmetic** pen in model (scene) units, so the
    viewport plots it at ``width × paper_scale``. A raw ``lw_mm`` would therefore
    plot at ``lw_mm × paper_scale`` — a sub-pixel hairline at architectural
    scales (the line reads as invisible on the sheet). Dividing by ``paper_scale``
    makes it plot at exactly ``lw_mm`` on paper regardless of viewport scale.
    """
    if color_mode != PaperColorMode.FULL_COLOR:
        from PyQt6.QtGui import QColor
        pipe._display_color = cat["color"]
        # The label text has no authored colour, so it follows the (dark-theme)
        # palette default — white, readable on the model canvas but invisible on
        # white paper. Force the paper category colour so the label reads on the
        # sheet; restore_model_display puts the original back (mirrors rooms /
        # gridline bubble labels). FULL_COLOR keeps the authored/model colour.
        _lbl = getattr(pipe, "label", None)
        if _lbl is not None:
            _lbl.setDefaultTextColor(QColor(cat["color"]))
    pipe._paper_pen_width = lw_mm / max(paper_scale, 1e-9)
    pipe.setOpacity(cat["opacity"] / 100.0)
    pipe.update()


def _apply_block(inst, cat, color_mode, lw_mm, paper_scale):
    """Paper overrides for a BlockInstance (linetypes.md LT1-2 / H5).

    Every stroke op plots non-cosmetic at the "Blocks" weight in true paper mm
    (divided by ``paper_scale``, the §9.9.1 pattern of ``_apply_pipe``); B&W /
    Custom force the category colour onto stroke + text ops, Full Color keeps
    the authored colours. Compiled op pens are never mutated (flyweight: one
    compile is shared by every instance) -- ``BlockInstance.paint`` reads these
    two hooks instead. Fill / pattern ops stay under the hatch rules.
    """
    from PyQt6.QtGui import QColor
    inst._paper_pen_width = lw_mm / max(paper_scale, 1e-9)
    inst._paper_scale = paper_scale          # named op weights (LT2-5)
    inst._paper_pen_color = (QColor(cat["color"])
                             if color_mode != PaperColorMode.FULL_COLOR else None)
    inst.setOpacity(cat["opacity"] / 100.0)
    inst.update()


def _apply_gridline(gl, cat, color_mode, lw_mm, paper_scale):
    """Apply paper overrides to a GridlineItem — colors + true-scale geometry (§9.9.1)."""
    from PyQt6.QtGui import QColor, QBrush
    from .gridline import bubble_paper_geometry

    S = max(paper_scale, 1e-9)
    cap_mm = cat.get("bubble_label_height_mm", 3.0)
    r_mm, em_mm = bubble_paper_geometry(cap_mm)

    gl._paper_render = True          # write-together unit with the floats below
    gl._paper_line_w = lw_mm / S
    gl._paper_line_w_mm = lw_mm      # ON-PAPER mm (NOT divided by S) — dash normaliser
    gl._paper_bubble_r = r_mm / S

    if color_mode != PaperColorMode.FULL_COLOR:
        gl._grid_color = QColor(cat["color"])
    # Authored color in full-color mode — suppresses the duplicate-warning
    # orange in ALL modes (a warning is not authored content, §9.9.1).
    pen_color = (QColor(cat["color"]) if color_mode != PaperColorMode.FULL_COLOR
                 else QColor(gl._grid_color))

    for bubble in (gl.bubble1, gl.bubble2):
        bubble._paper_saved = bubble.enter_paper_mode(r_mm / S, em_mm / S)
        # Model-side Display Manager bubble scale multiplier never affects
        # paper output (§9.9.1 isolation) — the multiplier is applied as an
        # item scale on each bubble, which would compound the paper radius.
        bubble.setScale(1.0)
        bp = bubble.pen()
        bp.setColor(pen_color)
        bp.setWidthF(lw_mm / S)
        bp.setCosmetic(False)
        bubble.setPen(bp)
        bubble._label.setDefaultTextColor(pen_color)
        if color_mode != PaperColorMode.FULL_COLOR and cat["fill"] is not None:
            bubble.setBrush(QBrush(QColor(cat["fill"])))

    gl._lock_indicator.setVisible(False)
    gl.setOpacity(cat["opacity"] / 100.0)
    gl.update()


def _apply_marker(marker, cat, color_mode, lw_mm, color_attr="_marker_color"):
    """Apply paper overrides to an elevation/detail marker."""
    from PyQt6.QtGui import QColor, QBrush, QPen
    if color_mode != PaperColorMode.FULL_COLOR:
        setattr(marker, color_attr, QColor(cat["color"]))
        pen = marker.pen()
        pen.setColor(QColor(cat["color"]))
        marker.setPen(pen)
        if cat["fill"] is not None and hasattr(marker, "_fill_color"):
            marker._fill_color = QColor(cat["fill"])
            marker.setBrush(QBrush(QColor(cat["fill"])))
    marker.setOpacity(cat["opacity"] / 100.0)
    marker.update()


def _save_gridline_state(gl) -> dict:
    """Capture gridline state for restore.

    Full pen/brush objects (not color names) and per-bubble entries — the two
    bubbles can legitimately differ (e.g. duplicate-warning pen).
    """
    from PyQt6.QtGui import QPen, QBrush
    return {
        "grid_color": gl._grid_color.name(),
        "bubble_pen": [QPen(b.pen()) for b in (gl.bubble1, gl.bubble2)],
        "bubble_brush": [QBrush(b.brush()) for b in (gl.bubble1, gl.bubble2)],
        "label_color": [b._label.defaultTextColor()
                        for b in (gl.bubble1, gl.bubble2)],
        "bubble_scale": [gl.bubble1.scale(), gl.bubble2.scale()],
        "lock_vis": gl._lock_indicator.isVisible(),
    }


def _save_marker_state(marker, color_attr="_marker_color") -> dict:
    """Capture marker state for restore."""
    from PyQt6.QtGui import QColor
    c = getattr(marker, color_attr, None)
    fill = getattr(marker, "_fill_color", None)
    return {
        "color_attr": color_attr,
        "marker_color": c.name() if isinstance(c, QColor) else c,
        "fill_color": fill.name() if isinstance(fill, QColor) else fill,
        "pen": marker.pen(),
        "brush": marker.brush(),
    }


def apply_paper_overrides(scene, source_rect, paper_scale: float = 1.0,
                          source_view_key: str = "", viewport_data=None) -> list[dict]:
    """Temporarily mutate visible items to paper-space display settings.

    Type-aware: each item type is handled according to how its paint()
    method reads display properties. Returns a list of saved-state dicts
    for ``restore_model_display()``.

    Args:
        scene: Source QGraphicsScene being rendered through a viewport.
        source_rect: Model-space crop rect of the viewport.
        paper_scale: True geometric scale (paper mm per model mm) of the
            viewport render — drives true-scale gridline bubbles (§9.9.1).
        source_view_key: The rendering viewport's
            ``f"{source_view_type}:{source_view_name}"`` — drives per-view
            underlay exclusion (§16.5). ``""`` means no per-view filtering.
        viewport_data: The SheetViewData of the viewport being painted; drives
            detail self-hide (a detail viewport hides its own marker) and
            per-sheet ``hidden_detail_ids`` suppression.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QBrush, QColor, QPen
    from PyQt6.QtWidgets import QGraphicsPathItem
    from .display_manager import _set_svg_tint
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .pipe import Pipe
    from .gridline import GridlineItem

    color_mode = load_paper_color_mode()
    cats = load_paper_categories()
    saved: list[dict] = []
    # Drafting-tile scale for the hatch renderer during THIS viewport render
    # (D-A30); cleared by restore_model_display. First entry → cleared even if
    # the pass fails part-way.
    scene._hatch_paper_scale = paper_scale
    saved.append({"hatch_scene": scene})
    # Thin Lines never plots (LT1-8): suspend it for the pass so paint-time
    # canvas pens (text borders) resolve their real width; lifted by restore.
    global _THIN_SUSPEND
    _THIN_SUSPEND += 1
    saved.append({"thin_suspend": True})
    try:
        items = scene.items(source_rect)

        for item in items:
            if not item.isVisible():
                continue
            # Instance-aware: class flags (manipulator, markers) and per-item
            # flags (the block placement ghost) both exclude.
            if getattr(item, "PAPER_EXCLUDED", False):
                saved.append({"item": item, "cat_key": None,
                              "visible": item.isVisible()})
                item.setVisible(False)
                continue
            if item.data(0) == "origin":
                # Model origin cross — authoring aid, never plots (§9.9.1).
                saved.append({"item": item, "cat_key": None,
                              "visible": item.isVisible()})
                item.setVisible(False)
                continue
            if getattr(item, "printed", True) is False:
                # Non-printing reference line (task D): scaffolding, never plots.
                # (`printed` exists only on ReferenceLineItem; other items → True.)
                saved.append({"item": item, "cat_key": None,
                              "visible": item.isVisible()})
                item.setVisible(False)
                continue
            if viewport_data is not None and _is_detail_marker(item):
                marker_name = getattr(item, "name", None)
                hide = False
                if viewport_data.source_view_type == "detail":
                    hide = (marker_name == viewport_data.source_view_name)  # self-hide
                if marker_name in viewport_data.hidden_detail_ids:
                    hide = True                                              # per-sheet hide
                if hide:
                    saved.append({"item": item, "cat_key": None,
                                  "visible": item.isVisible()})
                    item.setVisible(False)
                    continue
            cat_key = _category_for_item(item)
            if cat_key is None:
                continue
            cat = cats.get(cat_key)
            if cat is None:
                continue

            # --- Save current state ---
            entry: dict = {
                "item": item,
                "cat_key": cat_key,
                "display_color": getattr(item, "_display_color", None),
                "display_fill_color": getattr(item, "_display_fill_color", None),
                "display_section_color": getattr(item, "_display_section_color", None),
                "opacity": item.opacity(),
                "visible": item.isVisible(),
                "pen": item.pen() if hasattr(item, "pen") else None,
            }

            # Type-specific extra state
            if isinstance(item, Pipe):
                entry["paper_pen_width"] = getattr(item, "_paper_pen_width", None)
                _lbl = getattr(item, "label", None)
                entry["pipe_label_color"] = (
                    _lbl.defaultTextColor() if _lbl is not None else None)
            elif isinstance(item, GridlineItem):
                entry["gridline"] = _save_gridline_state(item)
            elif cat_key == "Elevation Marker":
                entry["marker"] = _save_marker_state(item, "_marker_color")
            elif cat_key == "Detail Marker":
                entry["marker"] = _save_marker_state(item, "_tag_color")
            elif cat_key == "Blocks":
                entry["block_paper"] = (item._paper_pen_width,
                                        item._paper_pen_color,
                                        item._paper_scale)
            from .wall_opening import WallOpening
            if isinstance(item, WallOpening):
                entry["paper_gap_color"] = getattr(item, "_paper_gap_color", None)

            saved.append(entry)

            # --- Visibility override ---
            if not cat.get("visible", True):
                item.setVisible(False)
                continue

            # --- Apply type-specific overrides ---
            lw_mm = resolve_line_weight_mm(cat["line_weight"])

            if isinstance(item, Pipe):
                _apply_pipe(item, cat, color_mode, lw_mm, paper_scale)
            elif isinstance(item, GridlineItem):
                _apply_gridline(item, cat, color_mode, lw_mm, paper_scale)
            elif isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
                if color_mode != PaperColorMode.FULL_COLOR:
                    _set_svg_tint(item, cat["color"], cat.get("fill"))
                item.setOpacity(cat["opacity"] / 100.0)
            elif cat_key == "Elevation Marker":
                _apply_marker(item, cat, color_mode, lw_mm, "_marker_color")
            elif cat_key == "Detail Marker":
                _apply_marker(item, cat, color_mode, lw_mm, "_tag_color")
            elif cat_key == "Blocks":
                _apply_block(item, cat, color_mode, lw_mm, paper_scale)
            elif cat_key == "Construction":
                _apply_construction(item, cat, color_mode, lw_mm, paper_scale)
            else:
                _apply_generic(item, cat, color_mode, lw_mm, paper_scale)
                # WallOpening gap fill: set paper-white so the gap reads as a
                # clean hole on white paper instead of the dark screen background.
                from .wall_opening import WallOpening as _WallOpening
                if isinstance(item, _WallOpening):
                    from PyQt6.QtGui import QColor as _QColor
                    item._paper_gap_color = _QColor("#ffffff")
                # Room tag label: size to a fixed ON-PAPER height (§9.9) so it
                # plots readably at any viewport scale instead of shrinking.
                from .room import Room as _Room
                if isinstance(item, _Room):
                    _apply_room_label_paper_height(
                        item, cat, color_mode, paper_scale, entry)

        # --- Fittings (wrappers, not QGraphicsItems) ---
        if hasattr(scene, "sprinkler_system"):
            fitting_cat = cats.get("Fitting")
            if fitting_cat is not None:
                for node in scene.sprinkler_system.nodes:
                    f = node.fitting
                    if f is None or f.symbol is None or not f.symbol.isVisible():
                        continue
                    if not source_rect.contains(f.symbol.scenePos()):
                        continue
                    entry = {
                        "item": f.symbol,
                        "cat_key": "Fitting",
                        "fitting": f,
                        "display_color": getattr(f, "_display_color", None),
                        "display_fill_color": getattr(f, "_display_fill_color", None),
                        "opacity": f.symbol.opacity(),
                        "visible": f.symbol.isVisible(),
                        "pen": None,
                    }
                    saved.append(entry)
                    if not fitting_cat.get("visible", True):
                        f.symbol.setVisible(False)
                        continue
                    if color_mode != PaperColorMode.FULL_COLOR:
                        _set_svg_tint(f.symbol, fitting_cat["color"],
                                      fitting_cat.get("fill"))
                        f._display_color = fitting_cat["color"]
                        f._display_fill_color = fitting_cat.get("fill")
                    f.symbol.setOpacity(fitting_cat["opacity"] / 100.0)

        # ── Underlays (§16.5) — records drive per-layer paper appearance ──
        for record, group in getattr(scene, "underlays", []):
            if group is None:
                continue
            try:
                was_visible = group.isVisible()
            except RuntimeError:
                continue
            if not group.sceneBoundingRect().intersects(source_rect):
                continue
            entry = {"underlay_group": group, "visible": was_visible,
                     "children": []}
            saved.append(entry)
            if not was_visible:
                continue          # model-side hidden: leave untouched
            for child in group.childItems():
                layer = child.data(1)
                if layer is None or not isinstance(child, QGraphicsPathItem):
                    continue
                entry["children"].append({"item": child, "pen": child.pen(),
                                          "brush": child.brush()})
                # Black ONLY in BW (spec D6): Full Color AND Custom keep
                # the authored effective layer colours.
                colour = (QColor("#000000")
                          if color_mode == PaperColorMode.BW
                          else QColor(record.effective_layer_colour(layer)))
                if child.pen().style() == Qt.PenStyle.NoPen:
                    child.setBrush(QBrush(colour))      # text batch
                    continue
                pen = QPen(child.pen())
                pen.setColor(colour)
                weight_name = record.effective_layer_weight(layer)
                if weight_name:
                    pen.setWidthF(resolve_line_weight_mm(weight_name)
                                  / max(paper_scale, 1e-9))
                    pen.setCosmetic(False)  # true mm on paper (§9.9.1 pattern)
                elif _THIN_LINES and child.data(7) is not None:
                    # Unweighted PDF width was baked at 1 px by Thin Lines;
                    # plot the non-thin source width (suspended above).
                    from .model_space import _pdf_width_to_px
                    pen.setWidthF(_pdf_width_to_px(float(child.data(7))))
                child.setPen(pen)

    except Exception:
        # A mid-pass failure must not escape before the caller receives
        # `saved` -- already-applied items would be stuck in paper geometry
        # (and the next pass would snapshot that as model state). Unwind
        # whatever was applied, then re-raise.
        restore_model_display(saved)
        raise
    return saved


def restore_model_display(saved: list[dict]):
    """Restore items to their pre-override state.

    Type-aware restore matching the type-aware apply.
    """
    from .display_manager import _set_svg_tint
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .pipe import Pipe
    from .gridline import GridlineItem
    from PyQt6.QtGui import QColor, QBrush, QPen

    global _THIN_SUSPEND
    for entry in saved:
        if "hatch_scene" in entry:
            entry["hatch_scene"]._hatch_paper_scale = None
            continue
        if "thin_suspend" in entry:
            if entry["thin_suspend"]:            # lift once per pass
                entry["thin_suspend"] = False
                if _THIN_SUSPEND <= 0:
                    _log.warning("restore_model_display: Thin Lines "
                                 "suspension counter unbalanced (%d)",
                                 _THIN_SUSPEND)
                _THIN_SUSPEND = max(0, _THIN_SUSPEND - 1)
            continue
        if "underlay_group" in entry:
            # Underlay-stage entry (§16.5) — pens/brushes then group visibility.
            for ch in entry["children"]:
                try:
                    ch["item"].setPen(ch["pen"])
                    ch["item"].setBrush(ch["brush"])
                except RuntimeError:
                    pass
            try:
                entry["underlay_group"].setVisible(entry["visible"])
            except RuntimeError:
                pass
            continue

        item = entry["item"]
        cat_key = entry.get("cat_key")

        if cat_key is None:
            # Origin-cross entry — visibility only (§9.9.1).
            item.setVisible(entry.get("visible", True))
            continue

        # Restore visibility and opacity (common to all)
        item.setVisible(entry.get("visible", True))
        item.setOpacity(entry["opacity"])

        if isinstance(item, Pipe):
            item._display_color = entry["display_color"]
            item._paper_pen_width = entry.get("paper_pen_width")
            _lbl = getattr(item, "label", None)
            _lc = entry.get("pipe_label_color")
            if _lbl is not None and _lc is not None:
                _lbl.setDefaultTextColor(_lc)
            item.update()

        elif isinstance(item, GridlineItem):
            gs = entry.get("gridline", {})
            item._grid_color = QColor(gs["grid_color"])
            for i, bubble in enumerate((item.bubble1, item.bubble2)):
                # Matched pair with _apply_gridline's enter_paper_mode — but
                # the geometry stage is skipped when the category is hidden
                # (visibility continue), so guard on the saved marker.
                pm = getattr(bubble, "_paper_saved", None)
                if pm is not None:
                    bubble.exit_paper_mode(pm)
                    del bubble._paper_saved
                bubble.setScale(gs["bubble_scale"][i])
                bubble.setPen(gs["bubble_pen"][i])
                bubble.setBrush(gs["bubble_brush"][i])
                bubble._label.setDefaultTextColor(gs["label_color"][i])
            item._lock_indicator.setVisible(gs["lock_vis"])
            item._paper_render = False
            item._paper_line_w = 0.0
            item._paper_line_w_mm = 0.0
            item._paper_bubble_r = 0.0
            item.update()

        elif isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
            _set_svg_tint(item, entry["display_color"],
                          entry.get("display_fill_color"))
            item.update()

        elif cat_key in ("Elevation Marker", "Detail Marker"):
            ms = entry.get("marker", {})
            color_attr = ms.get("color_attr", "_marker_color")
            mc = ms.get("marker_color")
            if mc is not None:
                setattr(item, color_attr, QColor(mc))
            fc = ms.get("fill_color")
            if fc is not None and hasattr(item, "_fill_color"):
                item._fill_color = QColor(fc)
            if ms.get("pen") is not None:
                item.setPen(ms["pen"])
            if ms.get("brush") is not None:
                item.setBrush(ms["brush"])
            item.update()

        elif cat_key == "Blocks":
            # Paint hooks only (H5); opacity/visibility restored above.
            (item._paper_pen_width, item._paper_pen_color,
             item._paper_scale) = entry.get("block_paper", (None, None, None))
            item.update()

        elif cat_key == "Construction":
            # Construction/draw geometry reads self.pen() directly — restore the
            # saved pen (color + width + cosmetic flag). No _display_* / fill
            # attrs are touched on apply, so restore is pen + opacity + vis only.
            if entry.get("pen") is not None and hasattr(item, "setPen"):
                item.setPen(entry["pen"])
            item.update()

        else:
            # Generic (Wall, Room, Floor, Roof, WallOpening)
            item._display_color = entry["display_color"]
            if hasattr(item, "_display_fill_color"):
                item._display_fill_color = entry.get("display_fill_color")
            if hasattr(item, "_display_section_color"):
                item._display_section_color = entry.get("display_section_color")
            if hasattr(item, "_paper_fill_opaque"):
                del item._paper_fill_opaque
            if hasattr(item, "_paper_no_fill"):
                del item._paper_no_fill
            item.__dict__.pop("_paper_pen_width", None)
            # Restore the room label's model-unit font size + colour (§9.9).
            if "room_label_font_size" in entry:
                item._label_font_size = entry["room_label_font_size"]
                if "room_label_font_color" in entry:
                    item._label_font_color = entry["room_label_font_color"]
                item._update_label()
            if entry.get("pen") is not None and hasattr(item, "setPen"):
                item.setPen(entry["pen"])
            # Restore WallOpening gap colour: prior value (None means unset →
            # delete the attr entirely so the screen path reverts to backgroundBrush).
            if "paper_gap_color" in entry:
                prior = entry["paper_gap_color"]
                if prior is None:
                    item.__dict__.pop("_paper_gap_color", None)
                else:
                    item._paper_gap_color = prior
            item.update()

        # Restore fitting wrapper attributes
        fitting = entry.get("fitting")
        if fitting is not None:
            fitting._display_color = entry["display_color"]
            fitting._display_fill_color = entry.get("display_fill_color")
