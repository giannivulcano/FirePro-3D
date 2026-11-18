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

from . import phase_display
from .constants import (MODEL_WEIGHT_FACTOR, MODEL_WEIGHT_FACTOR_MIN,
                        MODEL_WEIGHT_FACTOR_MAX, MODEL_WEIGHT_PX_MAX,
                        MODEL_BLOCKS_FACTORY_MM, DEFAULT_LINE_WEIGHT_MM,
                        PAPER_LEGACY_PX_PER_MM, PAPER_LEGACY_SNAP_PX,
                        UNDERLAY_LINE_WIDTH_PX)

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


# LW-DC-1: the factory Defaults (ratified 2026-11-12; replaces MW-4's table).
DEFAULT_LINE_WEIGHTS: list[LineWeightDef] = [
    LineWeightDef("Extra Thin",  0.13, 1),
    LineWeightDef("Thin",        0.18, 2),
    LineWeightDef("Fine",        0.25, 3),
    LineWeightDef("Medium",      0.35, 4),
    LineWeightDef("Wide",        0.50, 5),
    LineWeightDef("Thick",       0.70, 6),
    LineWeightDef("Extra Thick", 1.00, 8),
]
FACTORY_LINE_WEIGHTS = DEFAULT_LINE_WEIGHTS      # the public name stays
# MW-4's retired table (2026-10-04): a migration input only (LW-DC-8).
MW_FACTORY_LINE_WEIGHTS: list[LineWeightDef] = [
    LineWeightDef("Thinnest", 0.18),
    LineWeightDef("Thinner",  0.25),
    LineWeightDef("Thin",     0.35),
    LineWeightDef("Thick",    0.50),
    LineWeightDef("Thickest", 0.70),
]
LINE_WEIGHT_SCHEMA = 2           # payload key "line_weight_schema" (LW-DC-8)
OLD_SUFFIX = " (old)"
# The pre-MW factory: an untouched template equal to it migrates (MW-4), and
# its names resolve by their mm wherever a table lacks them (MW-6).
LEGACY_FACTORY_LINE_WEIGHTS: list[LineWeightDef] = [
    LineWeightDef("Very Light", 0.13),
    LineWeightDef("Light",      0.18),
    LineWeightDef("Medium",     0.25),
    LineWeightDef("Heavy",      0.35),
    LineWeightDef("Very Heavy", 0.50),
]
# Factory-name -> mm (MW-6): the Defaults, plus the old non-clashing names at
# their old mm. "Thin" / "Thick" / "Medium" resolve to the Default rows.
_FACTORY_NAME_MM: dict[str, float] = {
    **{d.name: d.width_mm for d in (*LEGACY_FACTORY_LINE_WEIGHTS,
                                    *MW_FACTORY_LINE_WEIGHTS)},
    **{d.name: d.width_mm for d in DEFAULT_LINE_WEIGHTS}}

# Old factory name -> Default name, only for pre-schema-2 sources (LW-DC-8).
_STATIC_LEGACY_MAP: dict[str, str] = {
    "Very Light": "Extra Thin", "Light": "Thin", "Medium": "Fine",
    "Heavy": "Medium", "Very Heavy": "Wide", "Thinnest": "Thin",
    "Thinner": "Fine", "Thin": "Medium", "Thick": "Wide", "Thickest": "Thick"}


def is_default_weight(name: str) -> bool:
    """True if *name* is one of the seven factory Default names (LW-DC-2)."""
    return any(d.name == name for d in DEFAULT_LINE_WEIGHTS)


def factory_default(name: str) -> "LineWeightDef | None":
    """A copy of the factory Default called *name*, else None."""
    for d in DEFAULT_LINE_WEIGHTS:
        if d.name == name:
            return d.copy()
    return None


def ensure_defaults(defs) -> list[LineWeightDef]:
    """Copies of *defs* plus any missing Default in factory form (prepended)."""
    have = {d.name for d in defs}
    return [*(d.copy() for d in DEFAULT_LINE_WEIGHTS if d.name not in have),
            *(d.copy() for d in defs)]


def legacy_weight_migration(defs) -> tuple[list[LineWeightDef], dict[str, str]]:
    """LW-DC-8 merge-by-width of a pre-schema-2 table.

    A row whose (name, mm) is in the MW or pre-MW factory set and whose mm
    equals a Default merges into it (``mapping[name]`` = the Default; a
    ``model_px`` override carries over); a row that is exactly a Default
    (same name and mm) merges into itself (identity mapping, no `` (old)``
    row); another row named like a Default is
    renamed with `` (old)`` (uniquified); any other row stays Custom. Missing
    Defaults are added. The mapping is single-hop (apply it simultaneously).
    """
    factory = {(d.name, round(d.width_mm, 6))
               for d in (*MW_FACTORY_LINE_WEIGHTS, *LEGACY_FACTORY_LINE_WEIGHTS)}
    by_mm = {round(d.width_mm, 6): d.name for d in DEFAULT_LINE_WEIGHTS}
    mapping: dict[str, str] = {}
    px_over: dict[str, int | None] = {}
    kept: list[LineWeightDef] = []
    clashes: list[LineWeightDef] = []
    for d in defs:
        mm = round(d.width_mm, 6)
        target = by_mm.get(mm)
        if (d.name, mm) in factory and target is not None:
            mapping[d.name] = target
            if d.model_px is not None:
                px_over.setdefault(target, d.model_px)
        elif target == d.name:
            # Exactly a Default's (name, mm): merges into itself (identity).
            mapping[d.name] = d.name
            if d.model_px is not None:
                px_over.setdefault(d.name, d.model_px)
        elif is_default_weight(d.name):
            clashes.append(d)
        else:
            kept.append(d.copy())
    taken = {d.name for d in kept} | {d.name for d in DEFAULT_LINE_WEIGHTS}
    for d in clashes:
        new = d.name + OLD_SUFFIX
        n = 2
        while new in taken:
            new = f"{d.name} (old {n})"
            n += 1
        taken.add(new)
        mapping[d.name] = new
        c = d.copy()
        c.name = new
        kept.append(c)
    present = {d.name for d in defs}
    for name, target in _STATIC_LEGACY_MAP.items():
        if name in present:
            continue
        mapping.setdefault(name, target)
    out = []
    for d in DEFAULT_LINE_WEIGHTS:
        c = d.copy()
        if d.name in px_over:
            c.model_px = px_over[d.name]
        out.append(c)
    return [*out, *kept], mapping


def validate_model_px(px) -> bool:
    """True for a whole-px Model override in 1..MODEL_WEIGHT_PX_MAX (MW-11)."""
    return (isinstance(px, int) and not isinstance(px, bool)
            and 1 <= px <= MODEL_WEIGHT_PX_MAX)


def _is_legacy_factory(defs: list[LineWeightDef]) -> bool:
    """An untouched MW or pre-MW factory template (names + mm, no overrides)."""
    got = {(d.name, round(d.width_mm, 6)) for d in defs}
    return (all(d.model_px is None for d in defs) and any(
        len(defs) == len(want) and got == want
        for want in ({(d.name, round(d.width_mm, 6)) for d in fac}
                     for fac in (LEGACY_FACTORY_LINE_WEIGHTS,
                                 MW_FACTORY_LINE_WEIGHTS))))


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
        # Rewriting the template alone would hide the old names from
        # ``migrate_settings_weights`` (stored "Thin" 0.35 would then map to
        # itself): run that one-time migration first, which also rewrites it.
        if not migrate_settings_weights(settings):
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


_SETTINGS_SCHEMA_KEY = "paper/line_weight_schema"


def _settings_schema_current(settings: QSettings) -> bool:
    """True once ``migrate_settings_weights`` has run on *settings*."""
    try:
        return int(settings.value(_SETTINGS_SCHEMA_KEY, 0) or 0) >= LINE_WEIGHT_SCHEMA
    except (TypeError, ValueError):
        return False
# Non-category QSettings keys holding a weight name (LW-DC-9): the Model
# Blocks weight (current + "Set as Default") and the ribbon's current weight.
_SETTINGS_WEIGHT_KEYS = ("display/Blocks/line_weight",
                         "display/Blocks/default_line_weight",
                         "template/geometry/weight")


def migrate_settings_weights(settings: QSettings) -> bool:
    """One-time LW-DC-9 migration of the app-wide weight names.

    Runs the LW-DC-8 merge-by-width over the new-project template
    (``paper/line_weights``: read raw, before ``load_line_weights`` could
    replace a legacy factory template) and rewrites every stored weight name
    through its mapping -- each ``paper/categories/*/line_weight``, the Model
    Blocks weight (current and default) and the ribbon current weight -- so
    paper output is unchanged. The mapping is the template's merged with
    ``_STATIC_LEGACY_MAP`` for names the template lacks. Stamps
    ``paper/line_weight_schema`` = 2; a later call is a no-op.

    Args:
        settings: The app QSettings (tests pass an isolated one).

    Returns:
        True if a migration ran, False if the store was already schema 2.
    """
    if _settings_schema_current(settings):
        return False
    raw = settings.value("paper/line_weights")
    defs = None
    if raw is not None:
        try:
            defs = _parse_weight_list(json.loads(raw) if isinstance(raw, str) else raw)
        except (json.JSONDecodeError, TypeError):
            defs = None
    new_defs, mapping = legacy_weight_migration(defs or [])
    if defs is not None:
        save_line_weights(new_defs, settings)
    keys = [f"paper/categories/{k}/line_weight" for k in _CATEGORY_KEYS]
    for key in (*keys, *_SETTINGS_WEIGHT_KEYS):
        cur = settings.value(key)
        if cur is not None and str(cur) in mapping and mapping[str(cur)] != str(cur):
            settings.setValue(key, mapping[str(cur)])
    settings.setValue(_SETTINGS_SCHEMA_KEY, LINE_WEIGHT_SCHEMA)
    settings.sync()
    _clear_hatch_mm()
    return True


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
    if is_default_weight(name.strip()):
        return False           # a Default name is never taken by another row (LW-DC-3)
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
    """Re-seed the project table (New Project / old files) as a copy of the
    app's weight table, i.e. ``load_line_weights()``, which reads QSettings
    and falls back to the factory defaults.

    Also clears the rename aliases (they are project-scoped, LT2-8).
    """
    set_project_line_weights(load_line_weights())
    set_weight_aliases({})


def weight_names() -> list[str]:
    """Project weight names for every picker: Defaults by width, then Custom
    by width (LW-DC-7)."""
    rows = sorted(project_line_weights(), key=lambda d: d.width_mm)
    return ([d.name for d in rows if is_default_weight(d.name)]
            + [d.name for d in rows if not is_default_weight(d.name)])


def weight_separator_index() -> int:
    """Index in ``weight_names()`` where Custom starts (= the Default count)."""
    return sum(1 for d in project_line_weights() if is_default_weight(d.name))


def weight_separator_at(head_len: int = 0) -> int | None:
    """Combo index for ``insertSeparator`` between Defaults and Custom.

    Args:
        head_len: Number of rows listed before ``weight_names()`` in the combo.

    Returns:
        The index where Custom starts, or ``None`` when no Custom rows exist
        or no Default precedes them (no leading separator).
    """
    sep = weight_separator_index()
    return head_len + sep if 0 < sep < len(project_line_weights()) else None


def fill_weight_combo(combo, head=()) -> None:
    """Clear ``combo`` and fill it: ``head``, Defaults, a separator, Custom
    (LW-DC-7). The separator is an empty-text item, only when Custom rows exist."""
    combo.clear()
    combo.addItems([*head, *weight_names()])
    at = weight_separator_at(len(head))
    if at is not None:
        combo.insertSeparator(at)


def _same_mm(a: float, b: float) -> bool:
    return round(float(a), 6) == round(float(b), 6)


def merge_project_line_weights(weights: dict, model_px: dict | None = None
                               ) -> tuple[list[str], dict[str, str]]:
    """Merge a bundle's ``{name: mm}`` into the project table by width (LW-DC-10).

    Per bundled ``(name, mm)``: the project row of that name with the same
    mm -> nothing; a pre-schema-2 factory pair (MW / pre-MW name at its
    factory mm) with a row of that exact mm -> mapped to that row (a Default
    preferred); a name the table lacks -> added under its name; a name whose
    row has another mm -> mapped to the row with that exact mm, else added
    as Custom ``name (old)`` and mapped to it. *model_px* is the bundle's
    ``weight_model_px`` ``{name: px}`` (H-MW-a) for an added row. Invalid
    widths and rename-alias keys are skipped.

    Returns:
        ``(added_names, mapping)``: the rows added, and the ``old -> new``
        name map the caller applies to the bundle's own references
        (``weight_refs.retarget_definition_refs``).
    """
    table = list(project_line_weights())
    aliases = set(_WEIGHT_ALIASES)
    factory = {(d.name, round(d.width_mm, 6))
               for d in (*MW_FACTORY_LINE_WEIGHTS, *LEGACY_FACTORY_LINE_WEIGHTS)}
    added: list[LineWeightDef] = []
    mapping: dict[str, str] = {}

    def add(name: str, mm: float, px) -> None:
        row = LineWeightDef(name, mm, px if validate_model_px(px) else None)
        added.append(row)
        table.append(row)

    for name, mm in (weights or {}).items():
        try:
            mm = float(mm)
        except (TypeError, ValueError):
            continue
        if not name or name in aliases or not validate_line_weight_width(mm):
            continue
        name = str(name)
        cur = next((d for d in table if d.name == name), None)
        if cur is not None and _same_mm(cur.width_mm, mm):
            continue
        exact = sorted((d for d in table if _same_mm(d.width_mm, mm)),
                       key=lambda d: not is_default_weight(d.name))
        ex = exact[0] if exact else None
        if (name, round(mm, 6)) in factory and ex is not None:
            mapping[name] = ex.name
        elif cur is None:
            add(name, mm, (model_px or {}).get(name))
        elif ex is not None:
            mapping[name] = ex.name
        else:
            new, n = name + OLD_SUFFIX, 2
            while any(d.name == new for d in table):
                new, n = f"{name} (old {n})", n + 1
            add(new, mm, (model_px or {}).get(name))
            mapping[name] = new
    if added:
        set_project_line_weights([*project_line_weights(), *added])
    return [d.name for d in added], mapping


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
# Manager disables every other cell and the row carries no As Authored toggle.
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
        "line_weight_schema": LINE_WEIGHT_SCHEMA,
    }


def _pending_migration(kind: "str | None") -> "tuple[list[LineWeightDef], dict[str, str]] | None":
    """The ``(new_defs, mapping)`` of a pending LW-DC-8 migration of *kind*
    (``"table"`` / ``"tableless"``) against the CURRENT project table (None
    when *kind* is None). Computed when used, never at stash time, so rows a
    mid-load library merge adds survive.

    A table-less file can only hold pre-schema-2 names, so its mapping is the
    static legacy map (Default names included: an old "Medium" is 0.25 mm) --
    except the template's own Custom rows, which map to themselves.
    """
    if kind is None:
        return None
    if kind == "tableless":
        table = project_line_weights()
        custom = {d.name for d in table if not is_default_weight(d.name)}
        mapping = {k: v for k, v in _STATIC_LEGACY_MAP.items() if k not in custom}
        return ensure_defaults(table), mapping
    return legacy_weight_migration(project_line_weights())


def _extend_mapping(mapping: dict[str, str]) -> dict[str, str]:
    """*mapping* plus every rename-alias key whose target it maps (alias keys
    follow their target)."""
    ext = dict(mapping)
    for key in weight_aliases():
        target = canonical_weight_name(key)
        if key not in ext and target in mapping:
            ext[key] = mapping[target]
    return ext


def pending_weight_mapping(kind: "str | None") -> dict[str, str]:
    """The LW-DC-8 old-name -> new-name map of a pending migration of *kind*
    (alias keys included), or ``{}``. The loader migrates payload records
    built asynchronously (underlays) with this before they are created."""
    pending = _pending_migration(kind)
    return _extend_mapping(pending[1]) if pending is not None else {}


def migrate_underlay_entry(entry: dict, ext: dict[str, str]) -> dict:
    """A copy of one saved underlay payload with its weight names re-pointed
    through *ext* (single hop): the default ``line_weight_name`` and every
    ``layer_overrides[layer]["line_weight"]``."""
    out = dict(entry)
    cur = out.get("line_weight_name")
    if cur in ext:
        out["line_weight_name"] = ext[cur]
    overrides = {}
    for layer, ov in (out.get("layer_overrides") or {}).items():
        ov = dict(ov)
        if ov.get("line_weight") in ext:
            ov["line_weight"] = ext[ov["line_weight"]]
        overrides[layer] = ov
    if "layer_overrides" in out:
        out["layer_overrides"] = overrides
    return out


def _schema_current(data: dict) -> bool:
    v = data.get("line_weight_schema")
    return isinstance(v, int) and not isinstance(v, bool) and v >= LINE_WEIGHT_SCHEMA


def apply_project_weights(data: dict | None, *, stash: bool = False) -> "str | None":
    """Install a project file's weight table, then its rename aliases.

    Called by ``project_tables.begin_load`` right after ``_clear_scene``
    (before any definition / text parse canonicalises weight names -- else
    the PREVIOUS project's aliases would rewrite this file's names) and again
    by ``apply_paper_display_from_project`` (same values; idempotent).

    A schema-2 table installs with any missing Default added. A table with
    no ``line_weight_schema`` installs UNCHANGED (holders parse against it);
    with ``stash=True`` (the loader only) its LW-DC-8 merge-by-width is
    returned as the migration kind (``"table"`` / ``"tableless"``, else
    None) for the load session. A table-less file takes the template (and
    returns a static-map migration: its old factory names map by width, the
    template's Custom rows stay).

    Returns:
        The pending migration kind, or None (always None without ``stash``).
    """
    data = data if isinstance(data, dict) else {}
    kind = None
    parsed = _parse_weight_list(data.get("line_weights"))
    current = _schema_current(data)
    if parsed is None:
        reset_project_line_weights()       # old file / no paper_display -> template
        if stash and not current:
            kind = "tableless"
    elif current:
        set_project_line_weights(ensure_defaults(parsed))
        set_weight_aliases(data.get("line_weight_aliases"))
    else:
        set_project_line_weights(parsed)   # never touches QSettings (LT1-3)
        set_weight_aliases(data.get("line_weight_aliases"))
        if stash:
            kind = "table"
    return kind


def apply_pending_weight_migration(scene, kind: "str | None", paper_display: dict | None,
                                   display_settings: dict | None = None) -> bool:
    """Run the pending *kind* LW-DC-8 migration against the freshly loaded *scene*.

    Re-points every by-name holder through ``weight_refs.retarget_weight_refs``
    (alias keys follow their target), then installs the migrated table and
    prunes the aliases it touched. The file's own payload dicts are migrated
    in place too -- ``paper_display`` (categories, table, schema stamp) and
    ``display_settings`` (the Model Blocks weight) -- so the later
    ``apply_paper_display_from_project`` / ``apply_project_display_settings``
    re-apply migrated names. The retarget runs against a scratch settings
    store: the app's QSettings (migrated once by ``migrate_settings_weights``)
    must not be rewritten by a project open.

    Returns:
        True if a migration ran.
    """
    pending = _pending_migration(kind)      # against the table as it is NOW
    if pending is None:
        return False
    import shutil
    import tempfile
    from . import weight_refs
    new_defs, mapping = pending
    ext = _extend_mapping(mapping)
    tmp = tempfile.mkdtemp(prefix="fp3d_lwdc_")
    try:
        scratch = QSettings(f"{tmp}/scratch.ini", QSettings.Format.IniFormat)
        # Underlay records were migrated from their payload as they were
        # built (they may not exist yet: async DXF/DWG builds).
        weight_refs.retarget_weight_refs(scene, scratch, ext, underlays=False)
        del scratch
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if isinstance(paper_display, dict):
        for cat in (paper_display.get("categories") or {}).values():
            if isinstance(cat, dict) and cat.get("line_weight") in ext:
                cat["line_weight"] = ext[cat["line_weight"]]
    if isinstance(display_settings, dict):
        blocks = display_settings.get(weight_refs.MODEL_BLOCKS_KEY)
        if isinstance(blocks, dict) and blocks.get("line_weight") in ext:
            blocks["line_weight"] = ext[blocks["line_weight"]]
    kept = {k: v for k, v in weight_aliases().items()
            if k not in ext and canonical_weight_name(v) not in mapping}
    set_project_line_weights(new_defs)
    set_weight_aliases(kept)
    if isinstance(paper_display, dict):
        paper_display["line_weights"] = [d.to_dict() for d in project_line_weights()]
        paper_display["line_weight_aliases"] = weight_aliases()
        paper_display["line_weight_schema"] = LINE_WEIGHT_SCHEMA
    return True


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
    """Map a QGraphicsItem to its display category key: the class's
    ``paper_category`` first, else the isinstance fallback ladder (the
    Display Manager rows and classes that declare no row)."""
    from .pipe import Pipe
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .node import Node
    from .gridline import GridlineItem
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .wall import WallSegment
    from .wall_opening import WallOpening
    from .room import Room

    pc = getattr(item, "paper_category", None)
    if pc is not None:              # the class declares its row (R5 / D8; a
        return pc                   # section proxy's is its _paper_cat, AC2)
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
    # are invisible on white paper unless remapped (see the construction
    # family's _paper_construction_write in geometry_2d).
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


def _is_phase_hidden_mask(item) -> bool:
    """PH3: an item with no paper category that only follows a host's Hide (a
    section slab's occlusion mask) must not occlude when the host's status is
    hidden."""
    disp = phase_display.active()
    if disp is None:                    # Phasing off: no lookups (AC4r)
        return False
    from PyQt6.QtWidgets import QGraphicsItem
    from .phase_registry import effective_phase
    from .section_scene import _ROLE_HIDE_SOURCE
    if QGraphicsItem.data(item, _ROLE_HIDE_SOURCE) is None:
        return False
    return effective_phase(item) in disp.hidden


def _hide_phase_hidden_mask_token(item, saved) -> None:
    """The phase-hidden mask hide as a visibility token (D4)."""
    if _is_phase_hidden_mask(item):
        from . import paper_pass
        paper_pass.hide_for_pass(saved, item)


def apply_paper_overrides(scene, source_rect, paper_scale: float = 1.0,
                          viewport_data=None):
    """Enter the paper pass for one sheet-viewport render (paper-space.md
    s6.2 "Paper pass protocol").

    Returns the opaque token list for ``restore_model_display``.

    Args:
        scene: Source QGraphicsScene being rendered through a viewport.
        source_rect: Model-space crop rect of the viewport.
        paper_scale: True geometric scale (paper mm per model mm) of the
            viewport render — drives true-scale gridline bubbles (§9.9.1).
        viewport_data: The SheetViewData of the viewport being painted; drives
            detail self-hide (a detail viewport hides its own marker) and
            per-sheet ``hidden_detail_ids`` suppression.
    """
    from . import paper_pass
    return paper_pass.run_pass(scene, source_rect, paper_scale, viewport_data)


def restore_model_display(saved) -> None:
    """Leave the paper pass: every token in reverse, each in its own try; the
    first error re-raises after the full unwind (D6)."""
    from . import paper_pass
    paper_pass.unwind(saved)
