"""Fill Types -- the project table of named fills (HF5; hatch-and-fill D-A14).

One project-wide store (like ``paper_display._PROJECT_LW``, ruling R9):
Filled Regions, block compile, the registry and section cuts all read
:func:`project_table`. The table is outside undo; callers that change it
call :func:`notify_changed` (repaint + recompile) and dirty the project.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal

from .constants import (FILL_TYPE_CUSTOM_LABEL, FILL_TYPE_FALLBACK_COLOR,
                        FILL_TYPE_FALLBACK_NAME,
                        FILL_TYPE_FALLBACK_OPACITY, FILL_TYPE_SOLID_BLACK,
                        TOKEN_ELEMENT)
from .fill_layers import BackgroundLayer, FillLayers, PatternLayer, from_record, to_record

_LAYER_KEYS = ("background", "pattern")
FALLBACK_LAYERS = FillLayers(BackgroundLayer(FILL_TYPE_FALLBACK_COLOR,
                                             FILL_TYPE_FALLBACK_OPACITY))


def new_id() -> str:
    """A fresh type id."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class FillType:
    """A named fill look; ``layers`` reuses the UP1 two-layer model."""
    id: str
    name: str
    layers: FillLayers

    def to_payload(self) -> dict:
        """JSON row: id, name and the layer record."""
        return {"id": self.id, "name": self.name, **(to_record(self.layers) or {})}

    @classmethod
    def from_payload(cls, d) -> "FillType | None":
        """Parse one row; None when it has no usable id / name."""
        if not isinstance(d, dict):
            return None
        tid, name = d.get("id"), d.get("name")
        if not (isinstance(tid, str) and tid and isinstance(name, str) and name.strip()):
            return None
        rec = {k: d[k] for k in _LAYER_KEYS if k in d}
        return cls(tid, name.strip(), from_record(rec))


class FillTypeTable:
    """Id- and name-unique set of :class:`FillType` (names compare casefolded)."""

    def __init__(self, types=()):
        self._types: dict[str, FillType] = {}
        # {dropped id: kept id} for a same-name duplicate row dropped on load
        # (first wins); lookups follow it so the duplicate's regions re-point.
        self._aliases: dict[str, str] = {}
        for t in types:
            self.add(t)

    def all(self) -> list[FillType]:
        """Every type, sorted by casefolded name."""
        return sorted(self._types.values(), key=lambda t: t.name.casefold())

    def get(self, type_id) -> FillType | None:
        """The type with *type_id* (following a load-time duplicate alias), or None."""
        if not isinstance(type_id, str):
            return None
        hit = self._types.get(type_id)
        if hit is None:
            hit = self._types.get(self._aliases.get(type_id))
        return hit

    def by_name(self, name) -> FillType | None:
        """The type called *name* (casefolded), or None."""
        key = str(name).strip().casefold()
        return next((t for t in self._types.values() if t.name.casefold() == key), None)

    def _name_taken(self, name: str, except_id: str | None = None) -> bool:
        hit = self.by_name(name)
        return hit is not None and hit.id != except_id

    def add(self, t: FillType) -> FillType:
        """Add *t*; ValueError on a duplicate id or name."""
        if t.id in self._types:
            raise ValueError(f"fill type id {t.id!r} exists")
        if self._name_taken(t.name):
            raise ValueError(f"fill type name {t.name!r} exists")
        self._types[t.id] = t
        return t

    def replace(self, t: FillType) -> FillType:
        """Replace the type with the same id; KeyError if absent."""
        if t.id not in self._types:
            raise KeyError(t.id)
        if self._name_taken(t.name, except_id=t.id):
            raise ValueError(f"fill type name {t.name!r} exists")
        self._types[t.id] = t
        return t

    def remove(self, type_id: str) -> None:
        """Drop a type (no-op when absent)."""
        self._types.pop(type_id, None)

    def copy(self) -> "FillTypeTable":
        """An independent table with the same (immutable) types."""
        out = FillTypeTable(self._types.values())
        out._aliases = dict(self._aliases)
        return out

    def free_name(self, base: str) -> str:
        """*base*, or '*base* N' for the first unused N >= 2."""
        if not self._name_taken(base):
            return base
        n = 2
        while self._name_taken(f"{base} {n}"):
            n += 1
        return f"{base} {n}"

    def ensure_named(self, name: str, layers: FillLayers) -> FillType:
        """The type called *name* (project wins), else a new one with *layers* (R7)."""
        hit = self.by_name(name)
        return hit if hit is not None else self.add(FillType(new_id(), name.strip(), layers))

    def ensure_look(self, base: str, layers: FillLayers) -> FillType:
        """A type named *base* / '*base* N' with exactly *layers*, else a new one (R4)."""
        for t in self.all():
            if t.layers == layers and (t.name == base or t.name.startswith(base + " ")):
                return t
        return self.add(FillType(new_id(), self.free_name(base), layers))

    def to_payload(self) -> list[dict]:
        """JSON rows for the project file."""
        return [t.to_payload() for t in self.all()]

    @classmethod
    def from_payload(cls, rows) -> "FillTypeTable":
        """Parse rows, dropping invalid ones and duplicate ids / names (first wins).

        A row dropped for a duplicate *name* is aliased to the type that kept
        the name, so regions typed with the dropped id resolve to it.
        """
        table = cls()
        for d in rows if isinstance(rows, list) else ():
            t = FillType.from_payload(d)
            if t is None or t.id in table._types:
                continue
            kept = table.by_name(t.name)
            if kept is None:
                table._types[t.id] = t
            else:
                table._aliases[t.id] = kept.id
        return table


def seed_table() -> FillTypeTable:
    """R6 minimal built-in set (HF8 replaces it with the template set)."""
    return FillTypeTable([
        FillType(new_id(), FILL_TYPE_SOLID_BLACK, FillLayers(BackgroundLayer("#000000", 1.0))),
        FillType(new_id(), FILL_TYPE_FALLBACK_NAME, FALLBACK_LAYERS),
    ])


# -- project-wide store (R9) ------------------------------------------------
_TABLE: FillTypeTable | None = None


class _FillTypeBus(QObject):
    changed = pyqtSignal()


_BUS: _FillTypeBus | None = None


def fill_type_bus() -> _FillTypeBus:
    """The change bus (``changed`` fires on any table change)."""
    global _BUS
    if _BUS is None:
        _BUS = _FillTypeBus()
    return _BUS


def notify_changed() -> None:
    """Tell listeners the table changed (repaint scenes, recompile blocks)."""
    fill_type_bus().changed.emit()


def project_table() -> FillTypeTable:
    """The project-wide table (lazily seeded)."""
    global _TABLE
    if _TABLE is None:
        _TABLE = seed_table()
    return _TABLE


def set_project_table(table: FillTypeTable) -> None:
    """Install *table* as the project table and notify."""
    global _TABLE
    _TABLE = table
    notify_changed()


def reset_project_table() -> None:
    """New project / startup: the seed set."""
    set_project_table(seed_table())


def load_project_fill_types(rows) -> None:
    """Open: the file's table, or the seed set when absent / empty (old files)."""
    table = FillTypeTable.from_payload(rows)
    set_project_table(table if table.all() else seed_table())


# -- resolution --------------------------------------------------------------
def merge_overrides(base: FillLayers, overrides) -> FillLayers:
    """*base* with sparse *overrides* on top (absent = inherit, None = off)."""
    if not isinstance(overrides, dict) or not overrides:
        return base
    rec = dict(to_record(base) or {})
    for k in _LAYER_KEYS:
        if k not in overrides:
            continue
        ov = overrides[k]
        if ov is None:
            rec.pop(k, None)
        elif isinstance(ov, dict):
            rec[k] = {**rec.get(k, {}), **ov}
    return from_record(rec)


def diff_overrides(base: FillLayers, new: FillLayers) -> dict:
    """Minimal overrides turning *base* into *new* (inverse of :func:`merge_overrides`)."""
    b, n = to_record(base) or {}, to_record(new) or {}
    out: dict = {}
    for k in _LAYER_KEYS:
        bl, nl = b.get(k), n.get(k)
        if nl is None:
            if bl is not None:
                out[k] = None
        elif bl is None:
            out[k] = dict(nl)
        else:
            fields = {f: v for f, v in nl.items() if bl.get(f) != v}
            if fields:
                out[k] = fields
    return out


def resolve(type_id, overrides, table: FillTypeTable | None = None):
    """``(FillLayers, missing)`` for a typed fill; missing -> the fallback look."""
    t = (table if table is not None else project_table()).get(type_id)
    if t is None:
        return FALLBACK_LAYERS, True
    return merge_overrides(t.layers, overrides), False


def canonical_id(type_id, table: FillTypeTable | None = None):
    """The kept id for *type_id* (follows a load-time duplicate alias); an id the
    table does not resolve is returned unchanged so a missing type stays missing."""
    t = (table if table is not None else project_table()).get(type_id)
    return t.id if t is not None else type_id


def canonicalise_records(prims, table: FillTypeTable | None = None) -> None:
    """Re-point every typed primitive record's ``fill_type`` to its kept id, in place."""
    for p in prims if isinstance(prims, list) else ():
        if isinstance(p, dict) and isinstance(p.get("fill_type"), str) and p["fill_type"]:
            p["fill_type"] = canonical_id(p["fill_type"], table)


def record_fill_layers(rec: dict) -> FillLayers:
    """The fill a primitive record draws: typed (``fill_type`` + sparse ``fill``) or custom."""
    if not isinstance(rec, dict):
        return from_record(None)
    if rec.get("fill_type"):
        return resolve(rec["fill_type"], rec.get("fill"))[0]
    return from_record(rec.get("fill"))


def element_colour(value, element_value):
    """R8: ``token:element`` -> the drawing element's colour; anything else unchanged."""
    return element_value if value == TOKEN_ELEMENT else value


# -- section cuts (HF5 R4 / R7) ---------------------------------------------
def legacy_section_layers(section, pattern, scale) -> FillLayers:
    """R4: a pre-HF5 section cell (colour + pattern + scale) as a look.

    Body colour -> background (a '#hex' or token; '' / None / 'hatch:...' -> none,
    as ``colour_tokens.section_fill_colour`` reads it); the pattern always drew
    (default diagonal) in the element's line colour -> By element (R8).
    """
    from .colour_tokens import is_token
    from .hatch_patterns import canonical_ref
    bg = None
    if isinstance(section, str) and (section.startswith("#") or is_token(section)):
        bg = BackgroundLayer(section, 1.0)
    try:
        sc = float(scale) if scale is not None else 1.0
    except (TypeError, ValueError):
        sc = 1.0
    return FillLayers(bg, PatternLayer(canonical_ref(pattern or "diagonal"), TOKEN_ELEMENT,
                                       1.0, sc if sc > 0 else 1.0))


def category_section_type(key: str, vals: dict) -> str | None:
    """The project type id a category's section settings name (R7), converting legacy (R4).

    ``section_type`` (a name) + ``section_look`` (a fill record) win: the project
    type of that name, else a type added from the look. Without a name, legacy
    ``section`` / ``section_pattern`` / ``section_scale`` convert to one type per
    distinct look (``<key> Section`` / ``<key> Section N``).
    """
    table = project_table()
    name = vals.get("section_type")
    if name:
        rec = vals.get("section_look")
        look = from_record(rec) if rec else None
        if look is None or look.is_empty:
            look = legacy_section_layers(vals.get("section"), vals.get("section_pattern"),
                                         vals.get("section_scale"))
        before = len(table.all())
        t = table.ensure_named(name, look)
        if len(table.all()) != before:
            notify_changed()
        return t.id
    if vals.get("section") is not None or vals.get("section_pattern"):
        before = len(table.all())
        t = table.ensure_look(f"{key} Section", legacy_section_layers(
            vals.get("section"), vals.get("section_pattern"), vals.get("section_scale")))
        if len(table.all()) != before:
            notify_changed()
        return t.id
    return None


def convert_item_section_override(key: str, ov: dict,
                                  base: FillLayers | None = None) -> None:
    """Per-item legacy section override keys -> one ``section_type`` id (R4), in place.

    Args:
        key: Category key (names the converted types ``<key> Section N``).
        ov: The item's ``_display_overrides`` (mutated).
        base: The category's look; a legacy override carried only some of
            colour / pattern / scale and the rest inherited the category's.
    """
    legacy = [k for k in ("section", "section_pattern", "section_scale") if k in ov]
    if not legacy or "section_type" in ov:
        for k in legacy:
            ov.pop(k, None)
        return
    bg = base.background if base is not None else None
    pat = base.pattern if base is not None else None
    sec = ov["section"] if "section" in ov else (bg.color if bg is not None else None)
    ref = ov.get("section_pattern") or (pat.ref if pat is not None else None)
    scl = ov["section_scale"] if "section_scale" in ov else (pat.scale if pat is not None else None)
    table = project_table()
    before = len(table.all())
    t = table.ensure_look(f"{key} Section", legacy_section_layers(sec, ref, scl))
    for k in legacy:
        ov.pop(k)
    ov["section_type"] = t.id
    if len(table.all()) != before:
        notify_changed()


# -- users / delete guards (HF5 R5, AC8) ------------------------------------
def reserved_name(name) -> bool:
    """True for a name the region panel's Fill Type picker would shadow or mis-pick:
    blank, "(Custom)" or a "? "-prefixed label (Group B carry-in)."""
    s = str(name).strip()
    return (not s or s.casefold() == FILL_TYPE_CUSTOM_LABEL.casefold()
            or s.startswith("? "))


def type_users(type_id: str, scene) -> list[str]:
    """Who uses a type (D-A15 "used by N"): typed region primitives in block
    definitions, Filled Regions in the plan and open Block Editors, Display
    Manager categories (by name) and per-item section overrides.

    Ids are compared through :func:`canonical_id`, so a record that kept a
    load-time duplicate's id still counts for the type that absorbed it.

    Args:
        type_id: The type's id.
        scene: The project ``Model_Space``.

    Returns:
        Human-readable user labels; empty when the type is unused.
    """
    from .block_registry import fill_type_refs
    t = project_table().get(type_id)
    canon = t.id if t is not None else type_id
    out: list[str] = []
    for d in getattr(scene, "_block_definitions", {}).values():
        if any(canonical_id(r) == canon for r in fill_type_refs(d.primitives)):
            out.append(f"block {d.name}")
    if t is not None:
        from .display_manager import _CATEGORIES, _read_category_from_settings
        for c in _CATEGORIES:
            name = _read_category_from_settings(c["key"]).get("section_type")
            if name and str(name).casefold() == t.name.casefold():
                out.append(f"{c['key']} sections")
    scenes = [s for _label, s in scene._user_scenes()] if hasattr(scene, "_user_scenes") else [scene]
    n_regions = n_items = 0
    for sc in scenes:
        for it in sc.items():
            ft_id = getattr(it, "fill_type", None)
            if isinstance(ft_id, str) and ft_id and canonical_id(ft_id) == canon:
                n_regions += 1
            ov = getattr(it, "_display_overrides", None)
            if isinstance(ov, dict) and isinstance(ov.get("section_type"), str) \
                    and canonical_id(ov["section_type"]) == canon:
                n_items += 1
    if n_regions:
        out.append(f"{n_regions} region(s)")
    if n_items:
        out.append(f"{n_items} element section override(s)")
    return out


def pattern_users(block_id: str) -> list[str]:
    """Sorted names of the project types whose pattern layer tiles *block_id*
    (D-A15: a pattern block a Fill Type uses cannot be deleted)."""
    from .hatch_patterns import canonical_ref
    want = canonical_ref(block_id)
    return sorted((t.name for t in project_table().all()
                   if t.layers.pattern is not None
                   and canonical_ref(t.layers.pattern.ref) == want),
                  key=str.casefold)


def region_pattern_users(block_id: str, scene) -> int:
    """Filled Regions (plan + open Block Editors) that tile *block_id* through
    their own custom / override pattern layer (D-A15). A typed region that only
    inherits the type's pattern is the Fill Type clause's, not counted here.
    """
    from .filled_region import FilledRegionItem
    from .hatch_patterns import canonical_ref
    want = canonical_ref(block_id)
    scenes = [s for _label, s in scene._user_scenes()] if hasattr(scene, "_user_scenes") else [scene]
    n = 0
    for sc in scenes:
        for it in sc.items():
            if not isinstance(it, FilledRegionItem):
                continue
            pat = it.fill_layers.pattern
            if pat is None or canonical_ref(pat.ref) != want:
                continue
            t = project_table().get(it.fill_type) if it.fill_type else None
            tp = t.layers.pattern if t is not None else None
            if tp is not None and canonical_ref(tp.ref) == want:
                continue                      # inherited from the type: its clause counts it
            n += 1
    return n
