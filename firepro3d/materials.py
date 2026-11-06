"""Materials -- the project table a wall or floor picks its cut look from.

Governing spec: docs/specs/materials.md. One project-wide store outside undo,
replaced on load (HF5 R9, as ``fill_types``). There is no second bus: a change
calls ``fill_types.notify_changed()``, which repaints every live scene. Cuts
resolve :func:`fill_type_of` per paint, so nothing is cached on an element.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import fill_types
from .constants import MATERIAL_NONE_ID, MATERIAL_NONE_NAME, TOKEN_ELEMENT
from .fill_layers import FillLayers, PatternLayer

CATEGORIES = ("Wall", "Floor")


@dataclass(frozen=True)
class Material:
    """A named cut look; ``fill_type`` is a Fill Type id, or None = draws nothing."""
    id: str
    name: str
    fill_type: str | None = None

    def to_payload(self) -> dict:
        """JSON row."""
        return {"id": self.id, "name": self.name, "fill_type": self.fill_type}

    @classmethod
    def from_payload(cls, d) -> "Material | None":
        """Parse one row; None when it has no usable id / name."""
        if not isinstance(d, dict):
            return None
        mid, name, ft_id = d.get("id"), d.get("name"), d.get("fill_type")
        if not (isinstance(mid, str) and mid and isinstance(name, str) and name.strip()):
            return None
        return cls(mid, name.strip(), ft_id if isinstance(ft_id, str) and ft_id else None)


class MaterialTable:
    """Id- and name-unique set of :class:`Material`; the None row is always present."""

    def __init__(self, rows=(), defaults=None):
        self._rows: dict[str, Material] = {
            MATERIAL_NONE_ID: Material(MATERIAL_NONE_ID, MATERIAL_NONE_NAME, None)}
        self._defaults: dict[str, str] = {}
        for m in rows:
            if m.id == MATERIAL_NONE_ID:
                self._rows[m.id] = Material(m.id, MATERIAL_NONE_NAME, m.fill_type)
            else:
                self.add(m)
        for key, mid in (defaults or {}).items():
            self.set_default(key, mid)

    def all(self) -> list[Material]:
        """None first, then every other row by casefolded name."""
        rest = sorted((m for m in self._rows.values() if m.id != MATERIAL_NONE_ID),
                      key=lambda m: m.name.casefold())
        return [self._rows[MATERIAL_NONE_ID], *rest]

    def get(self, material_id) -> Material | None:
        """The row with *material_id*, or None."""
        return self._rows.get(material_id) if isinstance(material_id, str) else None

    def by_name(self, name) -> Material | None:
        """The row called *name* (casefolded), or None."""
        key = str(name).strip().casefold()
        return next((m for m in self._rows.values() if m.name.casefold() == key), None)

    def _name_taken(self, name: str, except_id: str | None = None) -> bool:
        hit = self.by_name(name)
        return hit is not None and hit.id != except_id

    def add(self, m: Material) -> Material:
        """Add *m*; ValueError on a duplicate id or name."""
        if m.id in self._rows:
            raise ValueError(f"material id {m.id!r} exists")
        if self._name_taken(m.name):
            raise ValueError(f"material name {m.name!r} exists")
        self._rows[m.id] = m
        return m

    def replace(self, m: Material) -> Material:
        """Replace the row with the same id; None keeps its name (M9)."""
        if m.id not in self._rows:
            raise KeyError(m.id)
        if m.id == MATERIAL_NONE_ID and m.name != MATERIAL_NONE_NAME:
            raise ValueError("the None material cannot be renamed")
        if self._name_taken(m.name, except_id=m.id):
            raise ValueError(f"material name {m.name!r} exists")
        self._rows[m.id] = m
        return m

    def remove(self, material_id: str) -> None:
        """Drop a row; a default that named it falls back to None."""
        if material_id == MATERIAL_NONE_ID:
            raise ValueError("the None material cannot be deleted")
        self._rows.pop(material_id, None)
        self._defaults = {k: v for k, v in self._defaults.items() if v != material_id}

    def default_for(self, category: str) -> str:
        """The material id new elements of *category* take (M11)."""
        mid = self._defaults.get(category)
        return mid if mid in self._rows else MATERIAL_NONE_ID

    def set_default(self, category: str, material_id) -> None:
        """Set *category*'s default; an unknown category or id is ignored."""
        if category in CATEGORIES and material_id in self._rows:
            self._defaults[category] = material_id

    def free_name(self, base: str) -> str:
        """*base*, or '*base* N' for the first unused N >= 2."""
        if not self._name_taken(base):
            return base
        n = 2
        while self._name_taken(f"{base} {n}"):
            n += 1
        return f"{base} {n}"

    def copy(self) -> "MaterialTable":
        """An independent table with the same (immutable) rows."""
        return MaterialTable(self._rows.values(), self._defaults)

    def to_payload(self) -> dict:
        """The project file's ``materials`` value."""
        return {"rows": [m.to_payload() for m in self.all()],
                "defaults": dict(self._defaults)}

    @classmethod
    def from_payload(cls, payload) -> "MaterialTable":
        """Parse a stored table, dropping invalid rows and duplicate ids / names."""
        table = cls()
        rows = payload.get("rows") if isinstance(payload, dict) else None
        for d in rows if isinstance(rows, list) else ():
            m = Material.from_payload(d)
            if m is None:
                continue
            if m.id == MATERIAL_NONE_ID:
                table._rows[m.id] = Material(m.id, MATERIAL_NONE_NAME, m.fill_type)
            elif m.id not in table._rows and not table._name_taken(m.name):
                table._rows[m.id] = m
        defaults = payload.get("defaults") if isinstance(payload, dict) else None
        for key, mid in (defaults or {}).items() if isinstance(defaults, dict) else ():
            table.set_default(key, mid)
        return table


def _starter_rows() -> list[Material]:
    """M10: the starters, adding their Fill Types by name (the project wins)."""
    from .hatch_patterns import (BUILTIN_BRICK, BUILTIN_CONCRETE, BUILTIN_CROSS_HATCH,
                                 BUILTIN_DIAGONAL)
    types = fill_types.project_table()
    rows = []
    for name, ft_name, ref in (("Concrete", "Concrete", BUILTIN_CONCRETE),
                               ("Brick", "Brick", BUILTIN_BRICK),
                               ("Wood Framed", "Cross Hatch", BUILTIN_CROSS_HATCH),
                               ("Steel Framed", "Diagonal", BUILTIN_DIAGONAL)):
        t = types.ensure_named(ft_name, FillLayers(None, PatternLayer(ref, TOKEN_ELEMENT)))
        rows.append(Material(fill_types.new_id(), name, t.id))
    return rows


def seed_table() -> MaterialTable:
    """The starter table."""
    return MaterialTable(_starter_rows())


# -- project-wide store (R9) ------------------------------------------------
_TABLE: MaterialTable | None = None


def project_table() -> MaterialTable:
    """The project-wide table (lazily seeded)."""
    global _TABLE
    if _TABLE is None:
        _TABLE = seed_table()
    return _TABLE


def set_project_table(table: MaterialTable) -> None:
    """Install *table* and repaint (no second bus)."""
    global _TABLE
    _TABLE = table
    fill_types.notify_changed()


def reset_project_table() -> None:
    """New project / startup, after the Fill Type reset: the starters."""
    set_project_table(seed_table())


def load_project_materials(payload) -> None:
    """Open, after the Fill Types: the file's table, or the starters when it has none."""
    rows = payload.get("rows") if isinstance(payload, dict) else None
    has_rows = isinstance(rows, list) and bool(rows)
    set_project_table(MaterialTable.from_payload(payload) if has_rows else seed_table())


# -- resolution ---------------------------------------------------------------
def material_of(item) -> Material:
    """*item*'s material; a missing or unknown id reads as None (the id stays stored)."""
    table = project_table()
    hit = table.get(getattr(item, "material_id", MATERIAL_NONE_ID))
    return hit if hit is not None else table.get(MATERIAL_NONE_ID)


def fill_type_of(item) -> str | None:
    """The one cut resolver: the Fill Type id *item* draws when cut, or None."""
    return material_of(item).fill_type


# -- elements ----------------------------------------------------------------
ROW_KEY = "Building Material"       # M14: rows key on their label; "Material" is a pipe row


def write_element(item, d: dict) -> dict:
    """Stamp ``material`` onto *d*; omitted when it is the None material."""
    if item.material_id != MATERIAL_NONE_ID:
        d["material"] = item.material_id
    return d


def read_element(item, data: dict) -> None:
    """Restore ``material_id`` and retire a legacy section override (M7).

    Called from ``from_dict`` after ``display_overrides_from_dict``, so the
    Fill Type tables are loaded and aliases are already canonical. Re-running
    on a snapshot is a no-op: the override keys are gone.
    """
    saved = data.get("material")
    item.material_id = saved if isinstance(saved, str) and saved else MATERIAL_NONE_ID
    ov = item._display_overrides
    fill_types.convert_item_section_override(item.material_category, ov)
    type_id = ov.pop("section_type", None)
    if saved or not type_id:
        return
    t = fill_types.project_table().get(type_id)
    if t is not None:
        item.material_id = _material_for_fill_type(t).id


def _material_for_fill_type(t) -> Material:
    """A material already drawing Fill Type *t*, else a new one named after it."""
    table = project_table()
    for m in table.all():
        if m.id != MATERIAL_NONE_ID and m.fill_type \
                and fill_types.canonical_id(m.fill_type) == t.id:
            return m
    return table.add(Material(fill_types.new_id(), table.free_name(t.name), t.id))


def property_row(item) -> dict:
    """The Properties panel row for ``ROW_KEY``."""
    return {"type": "enum", "value": material_of(item).name,
            "options": [m.name for m in project_table().all()]}


def set_from_row(item, name) -> bool:
    """Apply a ``ROW_KEY`` panel value; True when the material changed.

    A changed value asks for one undo step: ``set_property`` pushes none of
    its own and the panel pushes only for ``Mark``. The panel's ``defer``
    coalesces a multi-selection into one step.
    """
    m = project_table().by_name(name)
    if m is None or m.id == item.material_id:
        return False
    item.material_id = m.id
    item.update()
    sc = item.scene()
    if sc is not None and hasattr(sc, "request_undo_push"):
        sc.request_undo_push()
    return True
