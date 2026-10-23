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

from .constants import (FILL_TYPE_FALLBACK_COLOR, FILL_TYPE_FALLBACK_NAME,
                        FILL_TYPE_FALLBACK_OPACITY, FILL_TYPE_SOLID_BLACK,
                        TOKEN_ELEMENT)
from .fill_layers import BackgroundLayer, FillLayers, from_record, to_record

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
        for t in types:
            self.add(t)

    def all(self) -> list[FillType]:
        """Every type, sorted by casefolded name."""
        return sorted(self._types.values(), key=lambda t: t.name.casefold())

    def get(self, type_id) -> FillType | None:
        """The type with *type_id*, or None."""
        return self._types.get(type_id) if isinstance(type_id, str) else None

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
        return FillTypeTable(self._types.values())

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
        """Parse rows, dropping invalid ones and duplicate ids / names (first wins)."""
        table = cls()
        for d in rows if isinstance(rows, list) else ():
            t = FillType.from_payload(d)
            if t is not None and t.id not in table._types and not table._name_taken(t.name):
                table._types[t.id] = t
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
    t = (table or project_table()).get(type_id)
    if t is None:
        return FALLBACK_LAYERS, True
    return merge_overrides(t.layers, overrides), False


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
