"""Project phasing -- the status registry and the element phase helpers (PH1).

Governing spec: docs/specs/project-phasing.md (D-PH3..D-PH6, D-PH16); how:
docs/superpowers/specs/2026-10-20-project-phasing-concept-design.md PD1 / PD4.
One project-wide registry outside undo, replaced on open and reset on New
(the ``materials.py`` project-table pattern), saved as the top-level
``"phases"`` key. An element's phase is a status id; a missing or unknown id
reads as ``"new"``. PH1 stores the factory graphics; nothing renders them yet.
"""
from __future__ import annotations

import copy
import logging

from .constants import (PHASE_DEMOLITION, PHASE_DEMOLITION_LINETYPE, PHASE_EXISTING,
                        PHASE_EXISTING_COLOUR, PHASE_EXISTING_FILL, PHASE_NEW)

log = logging.getLogger(__name__)

PHASES_SAVE_VERSION = 13     # below it a pipe's "Phase" text migrates to an id (D-PH6)
BUILTIN_IDS = (PHASE_NEW, PHASE_EXISTING, PHASE_DEMOLITION)
ROW_KEY = "Phase"                    # the shared element row (PD1)
FITTING_ROW_KEY = "Fitting Phase"    # the node panel's fitting override row (D-PH4)
_AUTO = "Auto"
_GRAPHIC_KEYS = ("colour", "fill", "weight", "linetype", "opacity")
_LEGACY_PIPE_PHASE = {"New": PHASE_NEW, "Existing": PHASE_EXISTING, "Demo": PHASE_DEMOLITION}


def _graphics(**given) -> dict:
    """A graphics record; None in a slot = no override (D-PH10 "--")."""
    return {k: given.get(k) for k in _GRAPHIC_KEYS}


def factory_statuses() -> list[dict]:
    """The three built-ins with their D-PH10 factory graphics."""
    return [
        {"id": PHASE_NEW, "name": "New", "builtin": True,
         "graphics": _graphics(), "include_in_calc": True},
        {"id": PHASE_EXISTING, "name": "Existing", "builtin": True,
         "graphics": _graphics(colour=PHASE_EXISTING_COLOUR, fill=PHASE_EXISTING_FILL),
         "include_in_calc": True},
        {"id": PHASE_DEMOLITION, "name": "Demolition", "builtin": True,
         "graphics": _graphics(linetype=PHASE_DEMOLITION_LINETYPE),
         "include_in_calc": False},       # D-PH14: hydraulics exclude Demolition
    ]


_FACTORY_CALC = {r["id"]: r["include_in_calc"] for r in factory_statuses()}


def _parse_status(d) -> dict | None:
    """One stored row, or None when it has no usable id / name."""
    if not isinstance(d, dict):
        return None
    sid, name = d.get("id"), d.get("name")
    if not (isinstance(sid, str) and sid and isinstance(name, str) and name.strip()):
        return None
    g = d.get("graphics") if isinstance(d.get("graphics"), dict) else {}
    calc = d.get("include_in_calc", _FACTORY_CALC.get(sid, True))
    return {"id": sid, "name": name.strip(), "builtin": sid in BUILTIN_IDS,
            "graphics": _graphics(**{k: g.get(k) for k in _GRAPHIC_KEYS}),
            "include_in_calc": bool(calc)}


class PhaseRegistry:
    """Ordered, id- and name-unique status list; the built-ins are always present (D-PH19)."""

    def __init__(self, statuses=None):
        self._rows: list[dict] = []
        for d in (factory_statuses() if statuses is None else statuses):
            s = _parse_status(d)
            if s is None or self.get(s["id"]) is not None or self.id_for_name(s["name"]):
                continue
            self._rows.append(s)
        for i, fac in enumerate(factory_statuses()):
            if self.get(fac["id"]) is None:
                clash = self.id_for_name(fac["name"])
                if clash is not None:        # a custom row squats the built-in's name:
                    self.get(clash)["name"] = self._free_name(fac["name"])   # keep its id
                self._rows.insert(min(i, len(self._rows)), fac)

    def _free_name(self, base: str) -> str:
        """*base* with a numeric suffix until no row carries the name."""
        n = 2
        while self.id_for_name(f"{base} ({n})"):
            n += 1
        return f"{base} ({n})"

    def statuses(self) -> list[dict]:
        """Deep copies of every row, in order."""
        return copy.deepcopy(self._rows)

    def ids(self) -> list[str]:
        return [r["id"] for r in self._rows]

    def names(self) -> list[str]:
        return [r["name"] for r in self._rows]

    def get(self, sid) -> dict | None:
        """The row with id *sid* (live), or None."""
        return next((r for r in self._rows if r["id"] == sid), None)

    def name_of(self, sid) -> str:
        """*sid*'s display name; an unknown id shows as New's name."""
        row = self.get(sid) or self.get(PHASE_NEW)
        return row["name"]

    def id_for_name(self, name) -> str | None:
        """The id whose name is *name* (casefolded), or None."""
        key = str(name).strip().casefold()
        return next((r["id"] for r in self._rows if r["name"].casefold() == key), None)

    def to_list(self) -> list[dict]:
        """The project file's ``"phases"`` value."""
        return copy.deepcopy(self._rows)

    @classmethod
    def from_list(cls, rows) -> "PhaseRegistry":
        """Parse a stored list; invalid / duplicate rows drop, built-ins are re-added."""
        return cls(rows if isinstance(rows, list) else None)

    def copy(self) -> "PhaseRegistry":
        """An independent copy (the Display Manager Phases tab's working copy)."""
        return PhaseRegistry(self.to_list())

    def graphics_of(self, sid) -> dict:
        """A copy of *sid*'s graphics record ({} for an unknown id)."""
        row = self.get(sid)
        return dict(row["graphics"]) if row else {}

    def set_graphic(self, sid, key, value) -> bool:
        """Set one graphics slot; None = no override ("—"). False for an unknown id / key."""
        row = self.get(sid)
        if row is None or key not in _GRAPHIC_KEYS:
            return False
        row["graphics"][key] = value
        return True

    def reset_graphics_to_factory(self) -> None:
        """Built-ins back to their D-PH10 factory graphics; names, order and custom rows kept."""
        factory = {r["id"]: r["graphics"] for r in factory_statuses()}
        for row in self._rows:
            if row["id"] in factory:
                row["graphics"] = dict(factory[row["id"]])


# -- project-wide store (materials.py pattern) ---------------------------------
_TABLE: PhaseRegistry | None = None
_UNKNOWN_LOGGED: set[str] = set()


def project_table() -> PhaseRegistry:
    """The project registry (lazily the factory)."""
    global _TABLE
    if _TABLE is None:
        _TABLE = PhaseRegistry()
    return _TABLE


def set_project_table(reg: PhaseRegistry) -> None:
    """Install *reg*; the unknown-id log starts over."""
    global _TABLE
    _TABLE = reg
    _UNKNOWN_LOGGED.clear()          # one info line per unknown id per load


def reset_project_table() -> None:
    """New project / startup: the factory registry."""
    set_project_table(PhaseRegistry())


def load_project_phases(rows) -> None:
    """Open (and the template overlay): the file's rows, or the factory when absent (D-PH6)."""
    has_rows = isinstance(rows, list) and bool(rows)
    set_project_table(PhaseRegistry.from_list(rows) if has_rows else PhaseRegistry())


def to_list() -> list[dict]:
    """The project registry for ``"phases"``."""
    return project_table().to_list()


# -- element ids -----------------------------------------------------------------
def read_id(value) -> str:
    """A stored phase value as a registry id; missing -> new, unknown -> new + one info line."""
    if value is None or value == "":
        return PHASE_NEW
    if isinstance(value, str) and project_table().get(value) is not None:
        return value
    key = repr(value)
    if key not in _UNKNOWN_LOGGED:
        _UNKNOWN_LOGGED.add(key)
        log.info("Unknown phase status %r reads as New", value)
    return PHASE_NEW


def write_element(item, d: dict) -> dict:
    """Stamp ``"phase"`` onto *d*; omitted when it is New (old files stay byte-identical)."""
    sid = getattr(item, "phase", PHASE_NEW)
    if sid != PHASE_NEW:
        d["phase"] = sid
    return d


def read_element(item, data) -> None:
    """Restore ``item.phase`` from a record (missing / unknown -> New)."""
    item.phase = read_id(data.get("phase") if isinstance(data, dict) else None)


def legacy_pipe_phase(text) -> str | None:
    """The one home of the pre-phasing pipe text map (New / Existing / Demo -> id).

    Used by ``migrate_payload`` (files) and ``MainWindow.restore_settings``
    (an old ``template/pipe`` QSettings value). Never by the panel path.
    """
    return _LEGACY_PIPE_PHASE.get(str(text).strip())


def _resolve(value) -> str | None:
    """A panel / settings value as an id: a status name or an id (no legacy text, C2)."""
    reg = project_table()
    text = str(value).strip()
    sid = reg.id_for_name(text)
    if sid is None and reg.get(text) is not None:
        sid = text
    return sid


def _changed(item) -> None:
    """Repaint *item* and ask its scene for one undo step (coalesced by the panel)."""
    upd = getattr(item, "update", None)
    if callable(upd):
        upd()
    scene_fn = getattr(item, "scene", None)
    sc = scene_fn() if callable(scene_fn) else None
    if sc is not None and hasattr(sc, "request_undo_push"):
        sc.request_undo_push()


def property_row(item) -> dict:
    """The panel row for ``ROW_KEY`` (enum of the registry names)."""
    reg = project_table()
    return {"type": "enum", "value": reg.name_of(getattr(item, "phase", PHASE_NEW)),
            "options": reg.names()}


def set_from_row(item, value) -> bool:
    """Apply a ``ROW_KEY`` value; True when the phase changed.

    The panel path only: a change requests one undo step (``materials.set_from_row``
    precedent). Placement / load / paste copies assign ``item.phase`` directly.
    """
    sid = _resolve(value)
    if sid is None or sid == getattr(item, "phase", PHASE_NEW):
        return False
    item.phase = sid
    _changed(item)
    return True


# -- payload migration (D-PH6) -----------------------------------------------------
def migrate_payload(payload) -> None:
    """Below ``PHASES_SAVE_VERSION``: a pipe's ``properties["Phase"]`` text becomes ``"phase"``.

    Runs on the raw payload before any deserializer (``scene_io.load_from_file``),
    so neither the file nor the undo path ever sees the legacy key. Every other
    element has no key and reads New; the registry seed is
    ``load_project_phases``' missing-key default.
    """
    if not isinstance(payload, dict):
        return
    version = payload.get("version", 1)
    if isinstance(version, (int, float)) and version >= PHASES_SAVE_VERSION:
        return
    for entry in payload.get("pipes") or ():
        props = entry.get("properties") if isinstance(entry, dict) else None
        if not isinstance(props, dict) or "Phase" not in props:
            continue
        legacy = props.pop("Phase")
        sid = legacy_pipe_phase(legacy)
        if sid is None:
            log.info("Unknown legacy pipe phase %r reads as New", legacy)
            sid = PHASE_NEW
        if sid != PHASE_NEW:
            entry["phase"] = sid


# -- fittings (D-PH4) ---------------------------------------------------------------
def derive_fitting_phase(fitting) -> str:
    """D-PH4 over every connected pipe: any New -> New; else any Existing ->
    Existing; else Demolition. A fitting with no pipes reads New (D-PH5 default)."""
    node = getattr(fitting, "node", None)
    phases = [effective_phase(p) or PHASE_NEW for p in (node.pipes if node is not None else ())]
    if not phases or PHASE_NEW in phases:
        return PHASE_NEW
    if PHASE_EXISTING in phases:
        return PHASE_EXISTING
    return PHASE_DEMOLITION


def _auto_label(node) -> str:
    return f"{_AUTO} ({project_table().name_of(derive_fitting_phase(node.fitting))})"


def fitting_row(node) -> dict:
    """The node panel's ``FITTING_ROW_KEY`` row: Auto (<derived>) then each status."""
    reg = project_table()
    auto = _auto_label(node)
    ov = node.fitting.phase_override
    return {"type": "enum", "value": auto if ov is None else reg.name_of(ov),
            "options": [auto, *reg.names()]}


def set_fitting_from_row(node, value) -> bool:
    """Apply a Fitting Phase value; Auto clears the override (ruling 2026-11-11)."""
    text = str(value).strip()
    new = None if text.startswith(f"{_AUTO} (") else _resolve(text)
    if new is None and not text.startswith(f"{_AUTO} ("):
        return False
    if new == node.fitting.phase_override:
        return False
    node.fitting.phase_override = new
    _changed(node)
    return True


# -- the single reader (PD1) ----------------------------------------------------------
def effective_phase(item) -> str | None:
    """The phase *item* plots and calculates with; None = not phased (D-PH3).

    Section / elevation proxies -> their source element; a child of a block
    placement -> the outermost placement; a Note (annotation) -> None; a fitting
    -> its override, else the D-PH4 derivation; anything with ``phase`` -> it.
    """
    if item is None:
        return None
    from PyQt6.QtWidgets import QGraphicsItem
    if isinstance(item, QGraphicsItem):
        from .section_scene import section_source_of
        src = section_source_of(item)
        if src is not None and src is not item:
            return effective_phase(src)
        from .block_instance import BlockInstance
        outer, parent = None, item.parentItem()
        while parent is not None:
            if isinstance(parent, BlockInstance):
                outer = parent
            parent = parent.parentItem()
        if outer is not None:
            return effective_phase(outer)
        if isinstance(item, BlockInstance) and item.note:
            return None
    from .fitting import Fitting
    if isinstance(item, Fitting):
        return item.phase_override or derive_fitting_phase(item)
    sid = getattr(item, "phase", None)
    return sid if isinstance(sid, str) else None
