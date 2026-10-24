"""Element attribute registry (element-parameters.md, SB2a).

Every element category exposes keyed values that host-bound blocks read
through ``@[key]`` text. One module, pure getters over the elements' real
fields (approach 1): a getter returns the raw value in canonical units
(lengths mm, areas mm2, volumes mm3, pressure psi, flow gpm, velocity
ft/s, pipe inner diameter in, angles deg) or None. ``HostValue`` formats it
by kind through the scene ScaleManager.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPolygonF

from .constants import ELEMENT_ROOM_PROBE_MM
from .format_utils import get_scale_manager
from .scale_manager import ScaleManager

CATEGORIES = ("Room", "Pipe", "Sprinkler", "Wall", "Door", "Window", "Opening",
              "Gridline")
TIER_NAMES = {1: "Stored", 2: "Geometry", 3: "Hydraulic", 4: "Related"}
KINDS = ("text", "number", "length", "area", "volume", "area_sqft", "pressure",
         "flow", "velocity", "pipe_id", "angle", "diameter")


@dataclass(frozen=True)
class ParamSpec:
    """One keyed value of a category (E3: PascalCase key, dotted if related)."""
    key: str
    label: str
    kind: str
    tier: int
    getter: Callable

    def __post_init__(self):
        # Definition-time check: HostValue.text runs from paint and must not raise.
        if self.kind not in KINDS:
            raise ValueError(f"unknown ParamSpec kind {self.kind!r} for {self.key!r}")


@dataclass(frozen=True)
class HostValue:
    """A raw host value plus its kind, formatted in project display units."""
    raw: object
    kind: str
    sm: Optional[ScaleManager] = None

    def _sm(self) -> ScaleManager:
        return self.sm if self.sm is not None else ScaleManager()

    @property
    def text(self) -> Optional[str]:
        """The kind formatter's string, or None when there is no value."""
        if self.raw is None:
            return None
        sm, v, k = self._sm(), self.raw, self.kind
        if k == "text":
            return str(v)
        if k == "length":
            return sm.format_length(v)
        if k == "area":
            return sm.format_area_mm2(v)
        if k == "volume":
            return sm.format_volume_mm3(v)
        if k == "area_sqft":
            return sm.format_area_sqft(v)
        if k == "pressure":
            return sm.format_pressure(v)
        if k == "flow":
            return sm.format_flow(v)
        if k == "velocity":
            return sm.format_velocity(v)
        if k == "pipe_id":
            return sm.format_pipe_id(v)
        if k == "angle":
            return ScaleManager.format_bearing(v)
        if k == "number":
            return ScaleManager.format_factor(v)
        if k == "diameter":
            return _diameter_text(v, sm)
        return str(v)

    @property
    def number(self) -> Optional[float]:
        """The same quantity as a bare float in display units (None: text)."""
        if self.raw is None or self.kind in ("text", "diameter"):
            return None
        try:
            v = float(self.raw)
        except (TypeError, ValueError):
            return None
        sm, k = self._sm(), self.kind
        if k == "length":
            return sm.length_value(v)
        if k == "area":
            return sm.area_mm2_value(v)
        if k == "volume":
            return sm.volume_mm3_value(v)
        if k == "area_sqft":
            return sm.area_sqft_value(v)
        if k == "pipe_id":
            return sm.pipe_id_value(v)
        if k == "angle":         # bearing, 0..360 (gridline ruling)
            return round(v, 2) % 360.0 if math.isfinite(v) else None
        return v                 # pressure / flow / velocity / number


def _diameter_text(key: str, sm: ScaleManager) -> str:
    """The pipe panel's nominal diameter string (pipe.py display maps)."""
    from .pipe import Pipe
    from .scale_manager import DisplayUnit
    metric = sm.display_unit in (DisplayUnit.METRIC_MM, DisplayUnit.METRIC_M)
    return (Pipe._INT_TO_METRIC if metric else Pipe._INT_TO_IMPERIAL).get(key, str(key))


# -- scene helpers ------------------------------------------------------------

def scene_of(item):
    """The item's scene; a sprinkler reaches it through its node."""
    sc = item.scene() if callable(getattr(item, "scene", None)) else None
    if sc is None and getattr(item, "node", None) is not None:
        sc = item.node.scene()
    return sc


def is_live(item) -> bool:
    """True while *item* is in a scene (a deleted host -> placeholders)."""
    return scene_of(item) is not None


def _ppm(item) -> float:
    sm = get_scale_manager(item)
    return sm.pixels_per_mm if sm is not None else 1.0


def _level_name(item, name=None):
    sc = scene_of(item)
    lm = getattr(sc, "_level_manager", None)
    name = getattr(item, "level", None) if name is None else name
    lvl = lm.get(name) if (lm is not None and name) else None
    return lvl.name if lvl is not None else None


def _hr(item):
    return getattr(scene_of(item), "hydraulic_result", None)


def _hr_get(item, field: str, key):
    hr = _hr(item)
    return getattr(hr, field).get(key) if hr is not None else None


def _none(_item):
    return None                  # Mark / Level.Number until SB2b (E4)


def _room_named(item, name, level=None):
    """The room called *name*; when *level* is given and a same-named room is on
    it, that one wins (auto-populate tags a node with room.name and room.level),
    else the first room with the name."""
    if not name:
        return None
    named = [r for r in getattr(scene_of(item), "_rooms", ()) if r.name == name]
    if level:
        for r in named:
            if getattr(r, "level", None) == level:
                return r
    return named[0] if named else None


# -- Room ---------------------------------------------------------------------

def _room_area(r):
    return r._compute_area_mm2() / _ppm(r) ** 2


def _room_ceiling(r):
    lm = getattr(scene_of(r), "_level_manager", None)
    # _ceiling_height_mm() returns 0.0 for an unknown level; the spec wants None
    if lm is None or lm.get(r.level) is None or lm.get(r._ceiling_level) is None:
        return None
    return r._ceiling_height_mm()


def _room_volume(r):
    c = _room_ceiling(r)
    return None if c is None else _room_area(r) * c


# -- Wall / openings ----------------------------------------------------------

def _feature(op):
    from .feature import FEATURE_REGISTRY
    return FEATURE_REGISTRY.get(op.feature_id)


def _opening_room(op):
    """E6: the room just past the wall face on the facing side, else the
    other side, else None."""
    w, sc = op.wall, scene_of(op)
    if w is None or sc is None:
        return None
    c = op.center_on_wall()
    nx, ny = w.normal()
    # half_thickness_scene() already equals half_mm * ppm (the drawing scale
    # cancels in paper_to_scene), so the probe reaches (half_mm + PROBE_MM) * ppm.
    reach = w.half_thickness_scene() + ELEMENT_ROOM_PROBE_MM * _ppm(op)
    first = -1.0 if op.mirror_facing else 1.0
    for sign in (first, -first):
        p = QPointF(c.x() + sign * nx * reach, c.y() + sign * ny * reach)
        for room in getattr(sc, "_rooms", ()):
            if QPolygonF(room.boundary).containsPoint(p, Qt.FillRule.OddEvenFill):
                return room
    return None


def _opening_room_attr(op, attr):
    r = _opening_room(op)
    return getattr(r, attr) if r is not None else None


# -- Pipe / sprinkler -----------------------------------------------------------

def _prop(item, key):
    return item._properties[key]["value"]


def _pipe_length(p):
    a, b = p.node1, p.node2
    if a is None or b is None:
        return None
    ppm = _ppm(p)
    d = b.scenePos() - a.scenePos()
    return math.sqrt((d.x() / ppm) ** 2 + (d.y() / ppm) ** 2 + (b.z_pos - a.z_pos) ** 2)


def _pipe_level(p):
    return _level_name(p, getattr(p, "level", None) or getattr(p.node1, "level", None))


def _spr_flow(s):
    pr = _hr_get(s, "node_pressures", s.node)
    if pr is None or pr < 0:
        return None
    return float(_prop(s, "K-Factor")) * math.sqrt(pr)


def _spr_room(s, attr):
    r = _room_named(s, getattr(s.node, "_room_name", ""), getattr(s.node, "level", None))
    return getattr(r, attr) if r is not None else None


# -- the table (design section 1) ----------------------------------------------

def _P(key, kind, tier, getter, label=None):
    return ParamSpec(key, label or key, kind, tier, getter)


def _level_keys(level_of=None):
    return [_P("Level.Name", "text", 4, level_of or (lambda i: _level_name(i))),
            _P("Level.Number", "text", 4, _none)]


_OPENING_KEYS = [
    _P("Mark", "text", 1, _none),
    _P("Family", "text", 1, lambda o: _feature(o).family),
    _P("Type", "text", 1, lambda o: _feature(o).type_name),
    _P("Width", "length", 1, lambda o: o.width_mm),
    _P("Height", "length", 1, lambda o: o.height_mm),
    _P("Sill", "length", 1, lambda o: o.sill_mm),
    _P("Wall.Mark", "text", 4, _none),
    _P("Wall.Name", "text", 4, lambda o: o.wall.name),
    _P("Room.Name", "text", 4, lambda o: _opening_room_attr(o, "name")),
    _P("Room.Mark", "text", 4, lambda o: _opening_room_attr(o, "_tag")),
    *_level_keys(),
]

_TABLE = {
    "Room": [
        _P("Name", "text", 1, lambda r: r.name),
        _P("Mark", "text", 1, lambda r: r._tag),               # E4: today's Room Tag
        _P("HazardClass", "text", 1, lambda r: r._hazard_class, "Hazard class"),
        _P("Occupancy", "text", 1, lambda r: r._occupancy),
        _P("SystemType", "text", 1, lambda r: r._system_type, "System type"),
        _P("CeilingType", "text", 1, lambda r: r._ceiling_type, "Ceiling type"),
        _P("Area", "area", 2, _room_area),
        _P("Perimeter", "length", 2, lambda r: r._compute_perimeter_mm() / _ppm(r)),
        _P("CeilingHeight", "length", 2, _room_ceiling, "Ceiling height"),
        _P("Volume", "volume", 2, _room_volume),
        *_level_keys(),
    ],
    "Pipe": [
        _P("Mark", "text", 1, _none),
        _P("Diameter", "diameter", 1, lambda p: _prop(p, "Diameter")),
        _P("Schedule", "text", 1, lambda p: _prop(p, "Schedule")),
        _P("Material", "text", 1, lambda p: _prop(p, "Material")),
        _P("CFactor", "number", 1, lambda p: float(_prop(p, "C-Factor")), "C-factor"),
        _P("Length", "length", 2, _pipe_length),
        _P("InnerDiameter", "pipe_id", 2, lambda p: p.get_inner_diameter(), "Inner diameter"),
        _P("Flow", "flow", 3, lambda p: _hr_get(p, "pipe_flows", p)),
        _P("Velocity", "velocity", 3, lambda p: _hr_get(p, "pipe_velocity", p)),
        _P("FrictionLoss", "pressure", 3, lambda p: _hr_get(p, "pipe_friction_loss", p),
           "Friction loss"),
        *_level_keys(_pipe_level),
    ],
    "Sprinkler": [
        _P("Mark", "text", 1, _none),
        _P("Manufacturer", "text", 1, lambda s: _prop(s, "Manufacturer")),
        _P("Model", "text", 1, lambda s: _prop(s, "Model")),
        _P("Orientation", "text", 1, lambda s: _prop(s, "Orientation")),
        _P("KFactor", "number", 1, lambda s: float(_prop(s, "K-Factor")), "K-factor"),
        _P("Temperature", "text", 1, lambda s: _prop(s, "Temperature")),
        _P("MinPressure", "pressure", 1, lambda s: float(_prop(s, "Min Pressure")),
           "Min pressure"),
        _P("CoverageArea", "area_sqft", 1, lambda s: float(_prop(s, "Coverage Area")),
           "Coverage area"),
        _P("Elevation", "length", 2, lambda s: s.node.z_pos),
        _P("Pressure", "pressure", 3, lambda s: _hr_get(s, "node_pressures", s.node)),
        _P("Flow", "flow", 3, _spr_flow),
        _P("NodeNumber", "text", 3, lambda s: _hr_get(s, "node_labels", s.node), "Node number"),
        _P("Room.Name", "text", 4, lambda s: getattr(s.node, "_room_name", "")),
        _P("Room.Mark", "text", 4, lambda s: _spr_room(s, "_tag")),
        *_level_keys(lambda s: _level_name(s, getattr(s.node, "level", None))),
    ],
    "Wall": [
        _P("Name", "text", 1, lambda w: w.name),
        _P("Mark", "text", 1, _none),
        _P("Thickness", "length", 1, lambda w: w.thickness_mm),
        _P("Length", "length", 2, lambda w: w.centerline_length() / _ppm(w)),
        _P("Height", "length", 2, lambda w: w._computed_height_mm()),
        *_level_keys(),
    ],
    "Door": _OPENING_KEYS,
    "Window": _OPENING_KEYS,
    "Opening": _OPENING_KEYS,
    "Gridline": [
        _P("Mark", "text", 1, lambda g: g.grid_label),          # Q3: Label is the Mark
        _P("Length", "length", 2, lambda g: g.length() / _ppm(g)),
        _P("Angle", "angle", 2, lambda g: g.angle_deg()),
    ],
}

PARAMS: dict[str, dict[str, ParamSpec]] = {
    cat: {s.key: s for s in specs} for cat, specs in _TABLE.items()}

_OPENING_CATEGORY = {"door": "Door", "window": "Window", "blank": "Opening"}


def category_of(item) -> Optional[str]:
    """The element category of *item*, or None (E1; WallOpening splits by kind).
    No candidate class subclasses another today; put a new subclass first."""
    from .gridline import GridlineItem
    from .pipe import Pipe
    from .room import Room
    from .sprinkler import Sprinkler
    from .wall import WallSegment
    from .wall_opening import WallOpening
    if isinstance(item, WallOpening):
        return _OPENING_CATEGORY.get(item.openings_type)
    for cls, cat in ((Room, "Room"), (Pipe, "Pipe"), (Sprinkler, "Sprinkler"),
                     (WallSegment, "Wall"), (GridlineItem, "Gridline")):
        if isinstance(item, cls):
            return cat
    return None


def host_values(item) -> dict[str, HostValue]:
    """``{key: HostValue}`` for *item*'s category ({} for a non-element).
    A getter that raises or meets missing data yields ``raw=None``."""
    cat = category_of(item)
    if cat is None:
        return {}
    sm = get_scale_manager(item)
    out = {}
    for key, spec in PARAMS[cat].items():
        try:
            raw = spec.getter(item)
        except Exception:        # one bad element never breaks paint (spec Edge Cases)
            raw = None
        if raw == "":
            raw = None
        out[key] = HostValue(raw, spec.kind, sm)
    return out


# -- Block Editor pickers (design section 3; E9, E10) -----------------------------

NONE_LABEL = "(none)"
WARN_MARK = "\u26a0"


def unknown_label(name: str, what: str) -> str:
    """The warn entry for a value kept from a file (E9)."""
    return f"{WARN_MARK} {name} \u2014 unknown {what}"


def category_choice(current: str) -> tuple[list, str, list]:
    """Options, current label and warn options for the Host category row."""
    opts = [NONE_LABEL, *CATEGORIES]
    if not current:
        return opts, NONE_LABEL, []
    if current in CATEGORIES:
        return opts, current, []
    bad = unknown_label(current, "category")
    return opts + [bad], bad, [bad]


def host_key_items(category: str, current: str) -> list[tuple]:
    """Combo entries ``(text, key, selectable, warn)``.

    A blank entry, then per tier a disabled header and ``Label (Key)`` items;
    a stored key the category lacks is kept as a warn entry.
    """
    out = [("", "", True, False)]
    specs = PARAMS.get(category, {})
    for tier, name in TIER_NAMES.items():
        group = [s for s in specs.values() if s.tier == tier]
        if group:
            out.append((name, None, False, False))
            out += [(f"{s.label} ({s.key})", s.key, True, False) for s in group]
    if current and current not in specs:
        out.append((unknown_label(current, "key"), current, True, True))
    return out
