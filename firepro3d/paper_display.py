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

from PyQt6.QtCore import QSettings

from .constants import (MODEL_WEIGHT_FACTOR, MODEL_WEIGHT_FACTOR_MIN,
                        MODEL_WEIGHT_FACTOR_MAX, MODEL_WEIGHT_PX_MAX,
                        MODEL_BLOCKS_FACTORY_MM, DEFAULT_LINE_WEIGHT_MM,
                        PAPER_LEGACY_PX_PER_MM, PAPER_LEGACY_SNAP_PX,
                        UNDERLAY_LINE_WIDTH_PX, UNDERLAY_MASK_SLOT)

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
    from .stroke_style import (AS_AUTHORED, BY_BLOCK, BY_CATEGORY, BY_LINETYPE,
                               CONTINUOUS)
    keys = (BY_BLOCK, BY_LINETYPE, CONTINUOUS, AS_AUTHORED, BY_CATEGORY)
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


def parse_model_weight_factor(value) -> float:
    """A stored / typed factor as a float; anything unparseable or outside
    MODEL_WEIGHT_FACTOR_MIN..MAX -> factory MODEL_WEIGHT_FACTOR (MW-2).
    The one rule shared by startup restore and the System Settings pane."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return MODEL_WEIGHT_FACTOR
    if not (MODEL_WEIGHT_FACTOR_MIN <= f <= MODEL_WEIGHT_FACTOR_MAX):
        return MODEL_WEIGHT_FACTOR
    return f


def set_model_weight_factor(factor) -> None:
    """Set the factor via ``parse_model_weight_factor`` (junk -> factory)."""
    global _MODEL_FACTOR
    _MODEL_FACTOR = parse_model_weight_factor(factor)

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


# Display Manager Model "Blocks" colour (linetypes.md WM3 D5): the canvas
# colour of a By Category placement Colour (token:blocks). Cached here so
# paint never reads QSettings; None = the factory (Automatic, WM3 Q3).
_MODEL_BLOCKS_COLOUR: str | None = None


def model_blocks_factory_colour() -> str:
    """Factory Model "Blocks" colour: Automatic (theme ink, WM3 Q3)."""
    from .constants import TOKEN_AUTO
    return TOKEN_AUTO


def model_blocks_colour() -> str:
    """The Model-tab "Blocks" colour (factory: Automatic)."""
    return _MODEL_BLOCKS_COLOUR or model_blocks_factory_colour()


def paper_blocks_value(cat: dict) -> str:
    """The stored colour ``token:blocks`` plots on paper (WM3 D3, task
    ruling 6): the Model "Blocks" colour when the Blocks row is As Authored,
    else the row colour; a stray ``token:blocks`` reads as Automatic."""
    from .constants import TOKEN_AUTO, TOKEN_BLOCKS
    v = model_blocks_colour() if row_as_authored(cat) else cat["color"]
    return TOKEN_AUTO if v == TOKEN_BLOCKS else v


def set_model_blocks_colour(value) -> None:
    """Set the Model "Blocks" colour; None / anything not pickable
    (``colour_tokens.picked_colour``: ``""`` No Fill, an internal token,
    garbage) -> the factory."""
    global _MODEL_BLOCKS_COLOUR
    from .colour_tokens import picked_colour       # circular at import time
    _MODEL_BLOCKS_COLOUR = picked_colour(value) if value else None


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
    ``set_project_line_weights`` to change the table. The first (lazy) seed
    reads the template via ``load_line_weights``, which may migrate an
    untouched legacy template -- one idempotent QSettings write (MW-4).
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


def shows_selection(item) -> bool:
    """True when *item* should paint its selection highlight: selected and
    not inside a paper/PDF pass -- selection never plots (wall polish D11,
    L42).  Looks ``paper_pass_active`` up at call time, so tests that patch
    the module attribute reach it."""
    return item.isSelected() and not paper_pass_active()


def auto_model_px(width_mm: float) -> int:
    """Auto canvas width (MW-3): round-half-up(mm x factor), min 1 -- the
    value the Line Weights tab shows as "Auto (n)" (Thin Lines ignored)."""
    # round(.., 9) first: float noise (1.16 x 12.5 = 14.4999..) must not turn
    # an exact half down.
    return max(1, math.floor(round(width_mm * _MODEL_FACTOR, 9) + 0.5))


def canvas_weight_px(width_mm: float) -> float:
    """Cosmetic canvas width for a raw paper mm (raw PDF widths, H-MW-c).

    Thin Lines -> 1.0 (except during a paper pass -- see thin_lines_active).
    """
    if thin_lines_active():
        return 1.0
    return float(auto_model_px(width_mm))


def paper_legacy_px(width_mm: float) -> float:
    """Cosmetic px a canvas pen plots at on paper: the pre-MW mapping, frozen.

    MW-1 / MW-4: a cosmetic pen that survives into a paper pass must plot
    exactly as before MW -- independent of the Model weight factor, Model px
    and Thin Lines. px = mm x ``PAPER_LEGACY_PX_PER_MM``; at or below
    ``PAPER_LEGACY_SNAP_PX`` it snaps to min(px, 1.0).
    """
    px = width_mm * PAPER_LEGACY_PX_PER_MM
    if px <= PAPER_LEGACY_SNAP_PX:
        px = min(px, 1.0)
    return px


def paper_legacy_pdf_px(pt_width: float) -> float:
    """``paper_legacy_px`` of a raw PDF stroke width (points), floored at
    ``UNDERLAY_LINE_WIDTH_PX`` (unweighted underlay children on paper)."""
    if pt_width <= 0.0:
        return UNDERLAY_LINE_WIDTH_PX
    return max(UNDERLAY_LINE_WIDTH_PX, paper_legacy_px(pt_width * 25.4 / 72.0))


def canvas_px_for_weight(name: str) -> float:
    """Cosmetic canvas width for a named weight (H-MW-c): Thin Lines -> 1;
    else the resolved row's Model override; else Auto of its mm."""
    if thin_lines_active():
        return 1.0
    d = _resolve_def(name)
    if d is not None and d.model_px is not None:
        return float(d.model_px)
    return float(auto_model_px(d.width_mm if d is not None
                               else DEFAULT_LINE_WEIGHT_MM))


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
# Per-category paper-space overrides
# ---------------------------------------------------------------------------

# Keys match _CATEGORIES in display_manager.py
_CATEGORY_KEYS = [
    "Pipe", "Sprinkler", "Fitting", "Water Supply", "Node",
    "Hydraulic Badge", "Wall", "Door", "Window", "Opening", "Roof", "Room",
    "Floor", "Grid Line", "Level Datum", "Elevation Marker", "Section Marker",
    "Detail Marker", "Construction", "Hatch", "Blocks", "Underlay",
]

# Which categories have a fill colour (mirrors display_manager._CATEGORIES)
_HAS_FILL = {"Sprinkler", "Water Supply", "Hydraulic Badge", "Wall", "Roof",
             "Room", "Floor"}

# Which categories have section colour
_HAS_SECTION = {"Wall", "Roof", "Floor"}

# Categories where only the line weight is meaningful (D-A31): the Display
# Manager disables every other cell and its colour-mode / reset loops skip them.
_LW_ONLY = {"Hatch"}

# Rows whose only live cells are the As Authored toggle + Colour (R2): the
# Underlay row -- layers keep their own weights and visibility.
_AUTH_ONLY = {"Underlay"}

# Retired global Color Mode (paper-as-authored D5): read once to migrate.
_LEGACY_MODE_KEY = "paper/color_mode"

# Persisted per-category properties (D1: as_authored is one of them).
_PROPS = ("color", "fill", "section_color", "line_weight", "opacity",
          "visible", "as_authored")

# Factory paper weight per category as an intended paper mm (MW-5: today's
# printed widths; resolved to the nearest live row when materialised).
_FACTORY_LW_MM = {
    "Pipe": 0.25, "Sprinkler": 0.25, "Fitting": 0.25, "Water Supply": 0.25,
    "Node": 0.18, "Hydraulic Badge": 0.13, "Wall": 0.35, "Roof": 0.25,
    "Room": 0.13, "Floor": 0.25, "Door": 0.18, "Window": 0.18,
    "Opening": 0.18, "Grid Line": 0.25, "Level Datum": 0.13,
    "Elevation Marker": 0.13, "Section Marker": 0.13, "Detail Marker": 0.18,
    "Construction": 0.18,
    "Hatch": 0.13,
    "Blocks": 0.18,         # paper-only, no fill/section (linetypes.md LT1-2)
}


def _make_factory_category(key: str) -> dict:
    """Factory paper settings for one category (D3): Automatic colour /
    section, Background fill, As Authored ON (every row but Hatch). The
    Underlay row has no weight (R2)."""
    from .constants import TOKEN_AUTO, TOKEN_BG
    cat = {
        "color": TOKEN_AUTO,
        "fill": TOKEN_BG if key in _HAS_FILL else None,
        "section_color": TOKEN_AUTO if key in _HAS_SECTION else None,
        "line_weight": (nearest_weight_name(_FACTORY_LW_MM[key])
                        if key in _FACTORY_LW_MM else None),
        "opacity": 100,
        "visible": True,
    }
    if key not in _LW_ONLY:
        cat["as_authored"] = True
    return cat


def _parse_bool(raw) -> bool:
    """A stored bool: QSettings hands strings back ("true"/"false")."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() not in ("false", "0")
    return bool(raw)


def row_as_authored(cat: dict) -> bool:
    """True when a paper row plots its items' own colours (D1)."""
    return bool(cat.get("as_authored", True))


def legacy_as_authored(mode) -> tuple[bool, bool]:
    """``(rows, underlay)`` As Authored for a retired Color Mode string
    (D4): full_color -> ON / ON; custom -> OFF / ON; bw, missing or unknown
    -> OFF / OFF."""
    m = str(mode) if mode is not None else ""
    if m == "full_color":
        return True, True
    if m == "custom":
        return False, True
    return False, False


def apply_legacy_mode(cats: dict, mode, keys=None) -> None:
    """Set ``as_authored`` per D4 on *keys* (default: every toggled row) of
    *cats*, in place. Hatch never carries it."""
    rows, und = legacy_as_authored(mode)
    for key in (cats if keys is None else keys):
        if key in _LW_ONLY or key not in cats:
            continue
        cats[key]["as_authored"] = und if key in _AUTH_ONLY else rows


def factory_paper_categories() -> dict[str, dict]:
    """Factory paper categories against the LIVE project table (Δ6 -- was the
    import-time FACTORY_PAPER_CATEGORIES dict)."""
    return {k: _make_factory_category(k) for k in _CATEGORY_KEYS}


def load_paper_categories(settings: QSettings | None = None) -> dict[str, dict]:
    """Load paper-space category overrides from QSettings. A legacy
    ``paper/color_mode`` key migrates once (D5): rows with no stored
    ``as_authored`` take the D4 value, the result is saved and the key removed."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    result: dict[str, dict] = {}
    unset: list[str] = []
    factory_all = factory_paper_categories()
    for key in _CATEGORY_KEYS:
        entry: dict = dict(factory_all[key])    # backfills new keys / rows
        for prop in _PROPS:
            raw = settings.value(f"paper/categories/{key}/{prop}")
            if raw is None:
                if prop == "as_authored" and key not in _LW_ONLY:
                    unset.append(key)
                continue
            if prop == "opacity":
                entry[prop] = int(float(raw))
            elif prop in ("visible", "as_authored"):
                entry[prop] = _parse_bool(raw)
            else:
                entry[prop] = raw
        result[key] = entry
    legacy = settings.value(_LEGACY_MODE_KEY)
    if legacy is not None:
        apply_legacy_mode(result, legacy, unset)
        save_paper_categories(result, settings)
        settings.remove(_LEGACY_MODE_KEY)
        settings.sync()
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
        for prop in _PROPS:
            val = entry.get(prop)
            if val is not None:
                settings.setValue(f"paper/categories/{key}/{prop}",
                                  str(val).lower() if prop in ("visible", "as_authored")
                                  else val)
            else:
                settings.remove(f"paper/categories/{key}/{prop}")
    settings.sync()


# ---------------------------------------------------------------------------
# Project file persistence
# ---------------------------------------------------------------------------

def get_paper_display_for_save() -> dict:
    """Return paper display settings for embedding in the project file."""
    return {
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
    """Apply paper display settings loaded from a project file. A legacy
    ``color_mode`` maps to per-row toggles where a row stores none (D4); it
    is never written back (D5)."""
    apply_project_weights(data)
    data = data if isinstance(data, dict) else {}
    proj_cats = data.get("categories") or {}
    merged: dict[str, dict] = {}
    unset: list[str] = []
    factory_all = factory_paper_categories()
    for key in _CATEGORY_KEYS:
        proj = proj_cats.get(key) or {}
        entry = dict(factory_all[key])
        entry.update({k: v for k, v in proj.items() if v is not None})
        if key not in _LW_ONLY:
            if proj.get("as_authored") is None:
                unset.append(key)
            else:
                entry["as_authored"] = _parse_bool(proj["as_authored"])
        merged[key] = entry
    apply_legacy_mode(merged, data.get("color_mode"), unset)
    save_paper_categories(merged)
    s = QSettings("GV", "FirePro3D")
    s.remove(_LEGACY_MODE_KEY)
    s.sync()


# ---------------------------------------------------------------------------
# Viewport rendering helpers
# ---------------------------------------------------------------------------

def _nearest_def(mm: float, defs) -> LineWeightDef | None:
    """Exact-mm row, else the nearest (tie -> thinner) -- MW-5 / MW-6."""
    return min(defs, key=lambda d: (abs(d.width_mm - mm), d.width_mm),
               default=None)


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
    return d.width_mm if d is not None else DEFAULT_LINE_WEIGHT_MM


_HATCH_MM: float | None = None


def hatch_line_mm() -> float:
    """Paper width (mm) of pattern lines — the "Hatch" category weight (D-A31).

    Cached: paint calls it per fill. ``save_paper_categories`` /
    ``save_line_weights`` clear the cache.
    """
    global _HATCH_MM
    if _HATCH_MM is None:
        cat = load_paper_categories().get("Hatch", {})
        _HATCH_MM = resolve_line_weight_mm(
            cat.get("line_weight") or factory_paper_categories()["Hatch"]["line_weight"])
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

    pc = getattr(item, "_paper_cat", None)
    if pc is not None:              # section / elevation proxy (AC2)
        return pc
    if isinstance(item, Pipe):
        return "Pipe"
    if isinstance(item, Sprinkler):
        return "Sprinkler"
    if isinstance(item, WallSegment):
        return "Wall"
    if isinstance(item, WallOpening):
        return item.display_category
    if type(item).__name__ == "FloorOpening":   # floor void: the Opening row (A8)
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
    if cls_name == "SectionMarker":            # SB4d D7: cardinal / placed rows
        return "Elevation Marker" if getattr(item, "cardinal", None) else "Section Marker"
    if cls_name == "DetailMarker":
        return "Detail Marker"
    if cls_name == "ElevDatumItem":         # elevation / section level datum (AC4)
        return "Level Datum"
    if cls_name == "ElevGridlineItem":      # elevation / section gridline (AC3)
        return "Grid Line"
    # Reference geometry (any flagged 2D shape, design RG12): its own
    # category, which no paper row overrides (keeps its canvas pen).
    if getattr(item, "reference", False):
        return "Reference Geometry"
    # Construction / draw geometry — pen-only paper category. These read
    # self.pen() directly in paint(), so they default to white (#ffffff) and
    # are invisible on white paper unless remapped (see _apply_construction).
    try:
        from .geometry_2d import (
            PolylineItem, LineItem,
            RectangleItem, CircleItem, ArcItem,
            EllipseItem, SplineItem, RegularPolygonItem,
        )
        from .filled_region import FilledRegionItem
        if isinstance(item, (PolylineItem, LineItem,
                             RectangleItem, CircleItem, ArcItem,
                             EllipseItem, SplineItem, RegularPolygonItem,
                             FilledRegionItem)):
            return "Construction"
    except ImportError:  # pragma: no cover - defensive fallback
        if cls_name in ("PolylineItem", "LineItem",
                        "RectangleItem", "CircleItem", "ArcItem",
                        "EllipseItem", "SplineItem", "RegularPolygonItem",
                        "FilledRegionItem"):
            return "Construction"
    return None


def _paper_qcolor(value, item=None):
    """QColor for a paper-category colour string (universal picker): a
    ``token:*`` resolves on the paper surface (black / light-theme accent);
    ``""`` (No Fill / no stroke) is fully transparent, so a pen, brush or text
    colour built from it draws nothing."""
    from PyQt6.QtGui import QColor
    from .colour_tokens import resolve_colour    # circular at import time
    if value == "":
        return QColor(0, 0, 0, 0)
    return resolve_colour(value, item=item)


def _apply_generic(item, cat, authored, lw_mm, paper_scale: float = 1.0):
    """Apply paper overrides to a generic item (Wall, Door / Window / Opening, Room, Floor, Roof).

    ``_paper_pen_width`` (true on-paper mm in model units, §9.9.1) is read by
    ``DisplayableItemMixin._outline_pen`` in the outline-painting items.
    """
    if not authored:
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


def _apply_construction(item, cat, authored, lw_mm, paper_scale):
    """Apply paper overrides to construction/draw geometry.

    These items read ``self.pen()`` directly in paint(), so the PEN COLOR (not
    just ``_display_color``) must be set for them to render in paper colours.

    The pen width is normalised to true ON-PAPER mm: the pen lives in model
    (scene) units and is rendered through the viewport at ``paper_scale`` (paper
    mm per model mm), so a raw ``lw_mm`` would plot at ``lw_mm × paper_scale`` —
    a sub-pixel hairline at architectural scales. Dividing by ``paper_scale``
    (non-cosmetic) makes it plot at ``lw_mm`` on paper regardless of scale,
    matching the gridline/underlay convention (§9.9.1). A named authored
    weight replaces the category weight (LT2-5 / WM-12); the category weight
    is the By Linetype / unstyled fallback.
    """
    from PyQt6.QtGui import QColor
    from .colour_tokens import is_token, resolve_colour   # circular at import time
    from .stroke_style import apply_stroke_joins, is_named_weight   # circular at import time
    if hasattr(item, "pen") and callable(getattr(item, "setPen", None)):
        pen = item.pen()
        if not authored:
            pen.setColor(_paper_qcolor(cat["color"], item))
        else:
            # The pen still holds the canvas-resolved ink (HF1): a token colour
            # must re-resolve on the paper surface -- this runs inside the pass
            # and _sync_stroke_pen leaves the pen alone for the whole pass.
            st = getattr(item, "style", None)
            tok = (getattr(item, "_display_color", None)
                   or (st.get("colour") if st is not None else None))
            if is_token(tok):
                pen.setColor(resolve_colour(tok, item=item))
        # LT2-5 on paper: a named weight (after the LT3-8 cascade -- By
        # Linetype takes a dashed linetype's dash weight) plots at its own
        # mm; By Linetype with no dash weight / unstyled -> the category.
        rs_fn = getattr(item, "_resolved_stroke", None)
        rs = rs_fn() if rs_fn is not None else None
        mm = (resolve_line_weight_mm(rs.weight)
              if rs is not None and is_named_weight(rs.weight) else lw_mm)
        pen.setWidthF(mm / max(paper_scale, 1e-9))
        pen.setCosmetic(False)
        apply_stroke_joins(pen)
        item.setPen(pen)
    item.setOpacity(cat["opacity"] / 100.0)
    item.update()


def _apply_pipe(pipe, cat, authored, lw_mm, paper_scale):
    """Apply paper overrides to a Pipe — uses _paper_pen_width hook.

    The pen width is normalised to true ON-PAPER mm (§9.9.1, matching
    ``_apply_construction`` / gridlines): ``Pipe.paint`` applies
    ``_paper_pen_width`` as a **non-cosmetic** pen in model (scene) units, so the
    viewport plots it at ``width × paper_scale``. A raw ``lw_mm`` would therefore
    plot at ``lw_mm × paper_scale`` — a sub-pixel hairline at architectural
    scales (the line reads as invisible on the sheet). Dividing by ``paper_scale``
    makes it plot at exactly ``lw_mm`` on paper regardless of viewport scale.
    """
    if not authored:
        pipe._display_color = cat["color"]
    pipe._paper_pen_width = lw_mm / max(paper_scale, 1e-9)
    pipe.setOpacity(cat["opacity"] / 100.0)
    pipe.update()


def _apply_block(inst, cat, authored, lw_mm, paper_scale, blocks_hook=False):
    """Paper overrides for a BlockInstance (linetypes.md LT1-2 / H5).

    Every stroke op plots non-cosmetic at the "Blocks" weight in true paper mm
    (divided by ``paper_scale``, the §9.9.1 pattern of ``_apply_pipe``); B&W /
    Custom force the category colour onto stroke + text ops, Full Color keeps
    the authored colours. Compiled op pens are never mutated (flyweight: one
    compile is shared by every instance) -- ``BlockInstance.paint`` reads these
    two hooks instead. Fill / pattern ops stay under the hatch rules.
    *blocks_hook* (WM3 D3): True only from the "Blocks" category branch --
    caches the paper "Blocks" colour for ``token:blocks``.
    """
    from PyQt6.QtGui import QColor
    from .annotative import is_annotative
    if is_annotative(inst.definition()):
        inst.prepareGeometryChange()     # SB1c D6: paper size != model bounds
    inst._paper_pen_width = lw_mm / max(paper_scale, 1e-9)
    inst._paper_scale = paper_scale          # named op weights (LT2-5)
    inst._paper_pen_color = None if authored else _paper_qcolor(cat["color"], inst)
    if blocks_hook:
        # WM3 D3 + task ruling 6: By Category on paper.
        inst._paper_blocks_colour = _paper_qcolor(paper_blocks_value(cat), inst)
    inst.setOpacity(cat["opacity"] / 100.0)
    inst.update()


def _elev_heads(item) -> list:
    """The annotation-block heads an elevation gridline / level datum owns
    (SB4c D4): its two bubbles (``ElevGridlineItem.bubble1`` / ``bubble2``)
    or its datum head (``ElevDatumItem.head``)."""
    return [h for h in (getattr(item, "bubble1", None), getattr(item, "bubble2", None),
                        getattr(item, "head", None)) if h is not None]


def _marker_heads(item) -> list:
    """The annotation-block heads a view marker owns (SB4d D1): a cardinal's
    ``head``, a placed section's ``head_a`` / ``head_b``, a detail's ``bubble``."""
    return [h for h in (getattr(item, "head", None), getattr(item, "head_a", None),
                        getattr(item, "head_b", None), getattr(item, "bubble", None))
            if h is not None]


def _model_colour_token(item, cat_key: str, cache: dict | None = None,
                        prop: str = "color"):
    """The token colour string the MODEL side stores for *item* (its *prop*:
    ``"color"`` or ``"fill"``), else None.

    Display Manager consumers (SVG tints, marker / gridline pens) latch the
    token already resolved for the canvas; a row-As-Authored paper pass keeps
    authored colours and so must re-resolve a token on the paper surface.
    Effective value = the item's own override, else its model category value
    (*cache* holds one QSettings read per (category, prop) per pass).
    """
    from .colour_tokens import is_token
    c = (getattr(item, "_display_overrides", None) or {}).get(prop)
    if c is None:
        ck = (cat_key, prop)
        if cache is not None and ck in cache:
            c = cache[ck]
        else:
            from .display_manager import _CATEGORY_MAP, _read_category_from_settings
            c = (_read_category_from_settings(cat_key)[prop]
                 if cat_key in _CATEGORY_MAP else None)
            if cache is not None:
                cache[ck] = c
    return c if is_token(c) else None


def _apply_gridline(gl, cat, authored, lw_mm, paper_scale, model_token=None):
    """Apply paper overrides to a GridlineItem's LINE (§9.9.1): weight + the
    paper-mm dash. Its bubbles are annotation blocks and take ``_apply_block``
    in the walk (SB4b D12). *model_token*: the model-side token colour (Full
    Colour only) re-resolved on the paper surface."""
    S = max(paper_scale, 1e-9)
    gl._paper_render = True          # write-together unit with the floats below
    gl._paper_line_w = lw_mm / S
    gl._paper_line_w_mm = lw_mm      # ON-PAPER mm (NOT divided by S) — dash normaliser
    if not authored:
        gl._grid_color = _paper_qcolor(cat["color"], gl)
    elif model_token is not None:
        from .colour_tokens import resolve_colour
        gl._grid_color = resolve_colour(model_token, item=gl)
    gl._lock_indicator.setVisible(False)
    gl.setOpacity(cat["opacity"] / 100.0)
    gl.update()


def _apply_marker(marker, cat, authored, lw_mm, color_attr="_marker_color",
                  model_token=None):
    """Apply paper overrides to an elevation / section / detail marker's LINE
    (SB4d D7: no fill -- the heads are annotation blocks)."""
    if authored and model_token is not None:
        # Full Colour keeps authored colours, but a token latched for the
        # canvas must re-resolve on paper (restore puts the saved colour back).
        from .colour_tokens import resolve_colour
        c = resolve_colour(model_token, item=marker)
        setattr(marker, color_attr, c)
        if hasattr(marker, "pen"):             # SectionMarker paints from fields, no pen
            pen = marker.pen()
            pen.setColor(c)
            marker.setPen(pen)
    if not authored:
        _pc = _paper_qcolor(cat["color"], marker)
        setattr(marker, color_attr, _pc)
        if hasattr(marker, "pen"):
            pen = marker.pen()
            pen.setColor(_pc)
            marker.setPen(pen)
    marker.setOpacity(cat["opacity"] / 100.0)
    marker.update()


def _save_gridline_state(gl) -> dict:
    """Capture gridline state for restore: the line colour, the lock
    indicator and each bubble's _apply_block hooks (SB4b D12)."""
    return {
        "grid_color": gl._grid_color.name(),
        "lock_vis": gl._lock_indicator.isVisible(),
        "bubble_paper": [(b._paper_pen_width, b._paper_pen_color, b._paper_scale)
                         for b in (gl.bubble1, gl.bubble2)],
    }


def _save_marker_state(marker, color_attr="_marker_color") -> dict:
    """Capture marker state for restore."""
    from PyQt6.QtGui import QColor
    c = getattr(marker, color_attr, None)
    return {
        "color_attr": color_attr,
        "marker_color": c.name() if isinstance(c, QColor) else c,
        "pen": marker.pen() if hasattr(marker, "pen") else None,
        "brush": marker.brush() if hasattr(marker, "brush") else None,
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
    from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem
    from .display_manager import _set_svg_tint
    from .colour_tokens import is_token
    from .block_definition import is_scaffold_item as _is_scaffold_item
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .pipe import Pipe
    from .gridline import GridlineItem
    from .annotative import printed_text_k
    from .text_item import TextItem

    cats = load_paper_categories()
    saved: list[dict] = []
    _tok_cache: dict = {}

    def _auth_tok(it, key, authored):
        """Model-side token colour to re-resolve on paper (row ON only)."""
        return _model_colour_token(it, key, _tok_cache) if authored else None

    def _svg_paper_retint(it, owner, key):
        """R6: a row-ON SVG symbol re-tints when its Model colour or fill is
        a token; each token resolves on the paper surface, a hex half keeps
        its canvas value. True when it re-tinted."""
        c = _model_colour_token(owner, key, _tok_cache)
        f = _model_colour_token(owner, key, _tok_cache, "fill")
        if c is None and f is None:
            return False
        _set_svg_tint(it, c if c is not None else getattr(owner, "_display_color", None),
                      f if f is not None else getattr(owner, "_display_fill_color", None))
        return True
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
    text_scale = getattr(scene, "text_print_scale", None)   # a Printed schematic (N15)
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
            # QGraphicsItem.data(item, 0), not item.data(0): TextItem shadows
            # ``data`` with its TextAnnotationData (schematic viewports hold
            # text — SV2; the snap_engine / property_manager precedent).
            if QGraphicsItem.data(item, 0) == "origin":
                # Model origin cross — authoring aid, never plots (§9.9.1).
                saved.append({"item": item, "cat_key": None,
                              "visible": item.isVisible()})
                item.setVisible(False)
                continue
            if _is_scaffold_item(item):
                # Non-printed reference geometry (task D, RG11 / RG12):
                # scaffolding, never plots. Every 2D primitive (and Text)
                # carries ``printed``, so the flag alone is not the test.
                saved.append({"item": item, "cat_key": None,
                              "visible": item.isVisible()})
                item.setVisible(False)
                continue
            if text_scale and isinstance(item, TextItem):
                # Printed text (N15): painted scaled, so it reports scaled bounds
                # for the pass. Saved first: restore never sees a half-entered item.
                saved.append({"print_text": item})
                item.set_print_pass((printed_text_k(text_scale, paper_scale), paper_scale))
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
            authored = row_as_authored(cat)
            if getattr(item, "_paper_cat", None) is not None:
                # Section / elevation proxy (AC2): the source category's
                # whole paper row, as _apply_generic gives the plan item --
                # Visible, Opacity, weight, and outside Full Colour the row's
                # Colour / Fill / Section body (a model hex would otherwise
                # plot as-is: white walls on white paper).
                lab = getattr(item, "pipe_label", None)    # a line proxy's label
                entry = {"item": item, "cat_key": cat_key, "proxy": True,
                         "visible": item.isVisible(),
                         "opacity": item.opacity(),
                         "srcs": (item._pen_src, item._brush_src,
                                  getattr(item, "_section_src", None),
                                  item._src_alpha)}
                if lab is not None:
                    entry["label"] = (lab, lab.isVisible(), lab.opacity(),
                                      lab._paper_pen_width, lab._paper_pen_color,
                                      lab._paper_scale)
                saved.append(entry)
                if not cat.get("visible", True):
                    item.setVisible(False)
                    if lab is not None:
                        lab.setVisible(False)
                    continue
                if not authored:
                    item._pen_src = cat["color"]
                    if hasattr(item, "_section_src"):          # cut wall / slab
                        if cat.get("section_color") is not None:
                            item._section_src = cat["section_color"]
                    elif getattr(item, "_no_sheet_body", False):
                        # Cut pipe symbol: a body in the row colour hides the S.
                        item._brush_src = ""
                    elif item._brush_src is not None:
                        # No Fill / Section column on the row: it takes the Colour.
                        fill = cat.get("fill")
                        item._brush_src = (fill if fill is not None
                                           else cat.get("section_color") or cat["color"])
                item._src_alpha = None   # paper fills plot opaque (_paper_fill_opaque)
                item._paper_pen_width = (resolve_line_weight_mm(cat["line_weight"])
                                         / max(paper_scale, 1e-9))
                item.setOpacity(cat["opacity"] / 100.0)
                if lab is not None and lab.isVisible():
                    _apply_block(lab, cat, authored,
                                 resolve_line_weight_mm(cat["line_weight"]), paper_scale)
                    lab.setOpacity(1.0)
                item.update()
                continue
            if cat_key in ("Grid Line", "Level Datum") and hasattr(item, "enter_paper_pass"):
                # Elevation gridline / level datum (SB4c D4): the LINE takes the
                # row's visibility, opacity, colour, weight and paper-mm dash
                # (enter_paper_pass, which also sets _paper_render); each
                # visible bubble / head is an annotation block and prints at
                # its authored mm through _apply_block (opacity 1, as the plan
                # gridline's bubbles).
                entry = {"item": item, "cat_key": cat_key, "elev_paper": None,
                         "opacity": item.opacity(), "visible": item.isVisible(),
                         "heads": []}
                if not cat.get("visible", True):
                    saved.append(entry)
                    item.setVisible(False)
                    continue
                bw = not authored
                lw_elev = resolve_line_weight_mm(cat["line_weight"])
                # Saved only once the pass is entered: restore never sees a
                # half-entered item.
                entry["elev_paper"] = item.enter_paper_pass(
                    lw_elev, paper_scale, color_src=cat["color"] if bw else None)
                saved.append(entry)
                item.setOpacity(cat["opacity"] / 100.0)
                for h in _elev_heads(item):
                    if h.isVisible():
                        entry["heads"].append((h, h._paper_pen_width, h._paper_pen_color,
                                               h._paper_scale))
                        _apply_block(h, cat, authored, lw_elev, paper_scale)
                        h.setOpacity(1.0)
                item.prepareGeometryChange()    # trim / bounds move with the paper k
                item.update()
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
                _l = item.label
                entry["tag_paper"] = (_l._paper_pen_width, _l._paper_pen_color,
                                      _l._paper_scale)
            elif isinstance(item, GridlineItem):
                entry["gridline"] = _save_gridline_state(item)
            elif cat_key in ("Elevation Marker", "Section Marker"):
                entry["marker"] = _save_marker_state(item, "_marker_color")
                entry["heads"] = [(h, h._paper_pen_width, h._paper_pen_color, h._paper_scale)
                                  for h in _marker_heads(item)]
            elif cat_key == "Detail Marker":
                entry["marker"] = _save_marker_state(item, "_tag_color")
                entry["heads"] = [(h, h._paper_pen_width, h._paper_pen_color, h._paper_scale)
                                  for h in _marker_heads(item)]
            elif cat_key == "Blocks":
                entry["block_paper"] = (item._paper_pen_width,
                                        item._paper_pen_color,
                                        item._paper_scale,
                                        getattr(item, "_paper_blocks_colour", None))
            from .room import Room as _Room
            if isinstance(item, _Room):
                _tag = item._tag
                entry["tag_paper"] = (_tag._paper_pen_width, _tag._paper_pen_color,
                                      _tag._paper_scale)
                entry["tag_opacity"] = _tag.opacity()   # top-level (SB4d D5)
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
                _apply_pipe(item, cat, authored, lw_mm, paper_scale)
                # Pipe label (SB4a D10): the one annotative path -- the label
                # is a BoundLabelItem and takes _apply_block's hooks; its
                # opacity stays 1. A hidden label is skipped.
                if item.label.isVisible():
                    _apply_block(item.label, cat, authored, lw_mm, paper_scale)
                    item.label.setOpacity(1.0)
            elif isinstance(item, GridlineItem):
                _apply_gridline(item, cat, authored, lw_mm, paper_scale,
                                _auth_tok(item, cat_key, authored))
                for b in (item.bubble1, item.bubble2):     # SB4b D12: annotative path
                    if b.isVisible():
                        _apply_block(b, cat, authored, lw_mm, paper_scale)
                        b.setOpacity(1.0)
                item.prepareGeometryChange()               # the trim moves with k
            elif isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
                if not authored:
                    _set_svg_tint(item, cat["color"], cat.get("fill"))
                else:
                    _svg_paper_retint(item, item, cat_key)
                item.setOpacity(cat["opacity"] / 100.0)
            elif cat_key in ("Elevation Marker", "Section Marker", "Detail Marker"):
                _apply_marker(item, cat, authored, lw_mm,
                              "_tag_color" if cat_key == "Detail Marker" else "_marker_color",
                              _auth_tok(item, cat_key, authored))
                for h in _marker_heads(item):          # SB4d D1: annotative heads print at authored mm
                    if h.isVisible():
                        _apply_block(h, cat, authored, lw_mm, paper_scale)   # SB4d: marker heads
                        h.setOpacity(1.0)
                item.prepareGeometryChange()           # the arrow / leader follow the paper k
            elif cat_key == "Blocks":
                _apply_block(item, cat, authored, lw_mm, paper_scale, blocks_hook=True)
            elif cat_key == "Construction":
                _apply_construction(item, cat, authored, lw_mm, paper_scale)
            else:
                _apply_generic(item, cat, authored, lw_mm, paper_scale)
                # WallOpening gap fill: set paper-white so the gap reads as a
                # clean hole on white paper instead of the dark screen background.
                from .wall_opening import WallOpening as _WallOpening
                if isinstance(item, _WallOpening):
                    from PyQt6.QtGui import QColor as _QColor
                    item._paper_gap_color = _QColor("#ffffff")
                # Room tag (SB3): the one annotative path -- the tag is a
                # BoundLabelItem and takes _apply_block's hooks (SB1c D6);
                # its opacity stays 1 (the Room row opacity is inherited
                # from the parent). A hidden tag is skipped.
                from .room import Room as _Room
                if isinstance(item, _Room) and item._tag.isVisible():
                    _apply_block(item._tag, cat, authored, lw_mm, paper_scale)
                    item._tag.setOpacity(1.0)

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
                    if not row_as_authored(fitting_cat):
                        _set_svg_tint(f.symbol, fitting_cat["color"],
                                      fitting_cat.get("fill"))
                        f._display_color = fitting_cat["color"]
                        f._display_fill_color = fitting_cat.get("fill")
                        entry["retinted"] = True
                    else:
                        entry["retinted"] = _svg_paper_retint(f.symbol, f, "Fitting")
                    f.symbol.setOpacity(fitting_cat["opacity"] / 100.0)

        # ── Underlays (§16.5) — records drive per-layer paper appearance ──
        und_cat = cats.get("Underlay") or factory_paper_categories()["Underlay"]
        und_auth = row_as_authored(und_cat)
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
                if child.data(UNDERLAY_MASK_SLOT):
                    continue          # a mask paints the sheet, not the layer
                entry["children"].append({"item": child, "pen": child.pen(),
                                          "brush": child.brush()})
                src = getattr(child, "_colour_src", None)
                if not und_auth and is_token(src):
                    # Row OFF: a token layer colour re-resolves at paint and
                    # would ignore the row colour set below; drop it for the
                    # pass (restore puts it back). "" (No Fill) stays hidden.
                    entry["children"][-1]["colour_src"] = src
                    child._colour_src = None
                # D6: row ON -> the layer's effective colour; OFF -> the
                # Underlay row colour (factory Automatic = black on paper).
                colour = (_paper_qcolor(record.effective_layer_colour(layer))
                          if und_auth else _paper_qcolor(und_cat["color"]))
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
                elif child.data(7) is not None:
                    # Unweighted raw width stays cosmetic: plot it at the
                    # frozen pre-MW mapping -- never the canvas Auto px
                    # (factor / Thin Lines dependent; MW-1 / MW-4).
                    pen.setWidthF(paper_legacy_pdf_px(float(child.data(7))))
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
    from .annotative import is_annotative as _is_annot
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
        if "print_text" in entry:
            entry["print_text"].set_print_pass(None)
            continue
        if "underlay_group" in entry:
            # Underlay-stage entry (§16.5) — pens/brushes then group visibility.
            for ch in entry["children"]:
                try:
                    ch["item"].setPen(ch["pen"])
                    ch["item"].setBrush(ch["brush"])
                    if "colour_src" in ch:
                        ch["item"]._colour_src = ch["colour_src"]
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
        if entry.get("proxy"):
            try:
                item.__dict__.pop("_paper_pen_width", None)
                (item._pen_src, item._brush_src, section_src,
                 item._src_alpha) = entry["srcs"]
                if hasattr(item, "_section_src"):
                    item._section_src = section_src
                item.setVisible(entry["visible"])
                item.setOpacity(entry["opacity"])
                if "label" in entry:
                    lab, vis, op, pen_w, pen_c, scale = entry["label"]
                    if _is_annot(lab.definition()):
                        lab.prepareGeometryChange()
                    lab._paper_pen_width, lab._paper_pen_color = pen_w, pen_c
                    lab._paper_scale = scale
                    lab.setVisible(vis)
                    lab.setOpacity(op)
                    lab.update()
                item.update()
            except RuntimeError:          # proxy deleted mid-pass (rebuild)
                pass
            continue
        if "elev_paper" in entry:
            item.setVisible(entry["visible"])
            item.setOpacity(entry["opacity"])
            for h, pen_w, pen_c, scale in entry.get("heads", ()):
                if _is_annot(h.definition()):
                    h.prepareGeometryChange()            # SB1c D6
                h._paper_pen_width, h._paper_pen_color, h._paper_scale = pen_w, pen_c, scale
                h.setOpacity(1.0)
                h.refresh()
            if entry["elev_paper"] is not None:
                item.exit_paper_pass(entry["elev_paper"])   # clears _paper_render, line weight
            item.prepareGeometryChange()
            item.update()
            continue

        # Restore visibility and opacity (common to all)
        item.setVisible(entry.get("visible", True))
        item.setOpacity(entry["opacity"])

        if isinstance(item, Pipe):
            item._display_color = entry["display_color"]
            item._paper_pen_width = entry.get("paper_pen_width")
            if "tag_paper" in entry:
                _l = item.label
                if _is_annot(_l.definition()):
                    _l.prepareGeometryChange()       # SB1c D6
                (_l._paper_pen_width, _l._paper_pen_color,
                 _l._paper_scale) = entry["tag_paper"]
                _l.update()
            item.update()

        elif isinstance(item, GridlineItem):
            gs = entry.get("gridline", {})
            item._grid_color = QColor(gs["grid_color"])
            for b, hooks in zip((item.bubble1, item.bubble2), gs["bubble_paper"]):
                if _is_annot(b.definition()):
                    b.prepareGeometryChange()            # SB1c D6
                b._paper_pen_width, b._paper_pen_color, b._paper_scale = hooks
                b.refresh()
            item._lock_indicator.setVisible(gs["lock_vis"])
            item._paper_render = False
            item._paper_line_w = 0.0
            item._paper_line_w_mm = 0.0
            item.prepareGeometryChange()
            item.update()

        elif isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
            _set_svg_tint(item, entry["display_color"],
                          entry.get("display_fill_color"))
            item.update()

        elif cat_key in ("Elevation Marker", "Section Marker", "Detail Marker"):
            ms = entry.get("marker", {})
            color_attr = ms.get("color_attr", "_marker_color")
            mc = ms.get("marker_color")
            if mc is not None:
                setattr(item, color_attr, QColor(mc))
            if ms.get("pen") is not None:
                item.setPen(ms["pen"])
            if ms.get("brush") is not None:
                item.setBrush(ms["brush"])
            for h, pen_w, pen_c, scale in entry.get("heads", ()):
                if _is_annot(h.definition()):
                    h.prepareGeometryChange()            # SB1c D6
                h._paper_pen_width, h._paper_pen_color, h._paper_scale = pen_w, pen_c, scale
                h.refresh()
            item.prepareGeometryChange()
            item.update()

        elif cat_key == "Blocks":
            # Paint hooks only (H5); opacity/visibility restored above.
            from .annotative import is_annotative
            if is_annotative(item.definition()):
                item.prepareGeometryChange()     # SB1c D6
            (item._paper_pen_width, item._paper_pen_color, item._paper_scale,
             item._paper_blocks_colour) = entry.get("block_paper", (None, None, None, None))
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
            # Restore the room tag's paper hooks (SB3).
            if "tag_paper" in entry:
                _tag = item._tag
                if _is_annot(_tag.definition()):
                    _tag.prepareGeometryChange()     # SB1c D6
                (_tag._paper_pen_width, _tag._paper_pen_color,
                 _tag._paper_scale) = entry["tag_paper"]
                _tag.update()
                if "tag_opacity" in entry:
                    _tag.setOpacity(entry["tag_opacity"])
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
            if entry.get("retinted"):
                # Re-latch the canvas tint: the apply step re-tinted the symbol.
                _set_svg_tint(item, entry["display_color"],
                              entry.get("display_fill_color"))
            fitting._display_color = entry["display_color"]
            fitting._display_fill_color = entry.get("display_fill_color")
