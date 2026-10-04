"""Pure constraint data model — parametric-constraint-system.md §6, §12.

No Qt. ``ConstraintType`` declares the whole catalogue from day one (§6.4);
``REGISTRY`` says which types are built. A record whose type is unknown or not
yet implemented loads **inert** and round-trips verbatim.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from enum import Enum

GROUNDS = ("origin", "x_axis", "y_axis")
# Types whose record carries a numeric ``value`` the residual reads (§6.3):
# the controller passes it to the builder and drops Reference dims (D7/D52).
VALUED = frozenset({"dim_distance", "dim_radius", "dim_diameter", "dim_angle",
                    "dim_point_line"})
_KNOWN = frozenset(("id", "type", "refs", "value", "driving", "enabled", "helper", "label"))


class ConstraintType(str, Enum):
    """File ``type`` strings (file-format; §7.3 catalogue, §12 order)."""
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    COINCIDENT = "coincident"
    POINT_ON_CURVE = "point_on_curve"
    DIM_DISTANCE = "dim_distance"        # length / aligned / Δx / Δy (helper.kind)
    DIM_RADIUS = "dim_radius"
    DIM_DIAMETER = "dim_diameter"
    DIM_ANGLE = "dim_angle"
    CONCENTRIC = "concentric"
    SYMMETRIC = "symmetric"
    FIX = "fix"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"
    EQUAL = "equal"
    TANGENT = "tangent"
    MIDPOINT = "midpoint"
    COLLINEAR = "collinear"
    DIM_POINT_LINE = "dim_point_line"


@dataclass(frozen=True)
class TypeSpec:
    """Registry row: accepted ref-kind patterns (pick order), DOF removed, built?"""
    label: str
    patterns: tuple
    dof: int
    implemented: bool = False

    @property
    def icon(self) -> str:
        """Ribbon/glyph icon filename derived from the label."""
        return f"constraint_{self.label.lower().replace(' ', '_')}_icon.svg"


REGISTRY: dict[str, TypeSpec] = {
    "horizontal": TypeSpec("Horizontal", (("edge",), ("point", "point")), 1, True),
    "vertical": TypeSpec("Vertical", (("edge",), ("point", "point")), 1, True),
    "coincident": TypeSpec("Coincident", (("point", "point"),), 2, True),
    "point_on_curve": TypeSpec("Coincident", (("point", "edge"), ("point", "curve"), ("point", "axis")), 1, True),
    "dim_distance": TypeSpec("Smart Dimension", (("edge",), ("point", "point")), 1, True),
    "dim_radius": TypeSpec("Smart Dimension", (("curve",),), 1),
    "dim_diameter": TypeSpec("Smart Dimension", (("curve",),), 1),
    "dim_angle": TypeSpec("Smart Dimension", (("edge", "edge"), ("edge", "axis")), 1),
    "concentric": TypeSpec("Concentric", (("curve", "curve"), ("curve", "point")), 2),
    "symmetric": TypeSpec("Symmetric", (("point", "point", "edge"), ("point", "point", "axis")), 2),
    "fix": TypeSpec("Fix", (("point",),), 2),
    "parallel": TypeSpec("Parallel", (("edge", "edge"),), 1),
    "perpendicular": TypeSpec("Perpendicular", (("edge", "edge"),), 1),
    "equal": TypeSpec("Equal", (("edge", "edge"), ("curve", "curve")), 1),
    "tangent": TypeSpec("Tangent", (("edge", "curve"), ("curve", "curve")), 1),
    "midpoint": TypeSpec("Midpoint", (("point", "edge"),), 2),
    "collinear": TypeSpec("Collinear", (("edge", "edge"),), 2),
    "dim_point_line": TypeSpec("Smart Dimension", (("point", "edge"),), 1),
}


# Glyph / panel icon for a record whose type this build does not know (VC9 F6):
# a neutral constraint-family glyph box, never the loader's _missing fallback.
NEUTRAL_ICON = "constraint_show_constraints_icon.svg"


def icon_for(ctype: str) -> str:
    """The one icon home for a constraint type (ribbon, canvas glyph, panel).

    Args:
        ctype: A record's ``type``.

    Returns:
        ``REGISTRY[ctype].icon``, or :data:`NEUTRAL_ICON` for an unknown type.
    """
    spec = REGISTRY.get(ctype)
    return spec.icon if spec is not None else NEUTRAL_ICON


def is_ground(ref: dict) -> bool:
    """Whether a ref points at a ground (origin/axis) rather than a primitive.

    Args:
        ref: A single ref dict from a constraint record.

    Returns:
        True if the ref is a ground ref (has a ``"ref"`` key).
    """
    return "ref" in ref


def ref_uids(c: "Constraint") -> set:
    """Primitive uids a constraint references (grounds excluded).

    Args:
        c: The constraint record.

    Returns:
        The set of referenced primitive uids.
    """
    return {r["uid"] for r in c.refs if not is_ground(r)}


@dataclass
class Constraint:
    """One constraint record (§6.3). ``raw`` keeps an inert record verbatim.

    An inert record is kept verbatim and must not be edited; its ``to_dict``
    returns the raw dict. Unknown top-level keys on a built record are kept in
    ``extras`` and re-emitted (§6.4: a newer build's file never loses data).
    """
    id: str
    type: str
    refs: list
    value: float | None = None
    driving: bool = True
    enabled: bool = True
    helper: dict = field(default_factory=dict)
    label: dict | None = None
    raw: dict | None = None
    extras: dict = field(default_factory=dict)
    # A built-type record whose refs do not validate against the sketch (an
    # unknown handle, a wrong ref kind / arity): kept verbatim and inert like
    # an unknown type (§6.4). Never serialised -- ``raw`` is.
    invalid: bool = False

    @classmethod
    def new(cls, ctype: str, refs: list, **kw) -> "Constraint":
        for k in ("helper", "label"):
            if k in kw:
                kw[k] = copy.deepcopy(kw[k])
        return cls(id=uuid.uuid4().hex, type=ctype, refs=copy.deepcopy(refs), **kw)

    @property
    def inert(self) -> bool:
        if self.invalid:
            return True
        spec = REGISTRY.get(self.type)
        return spec is None or not spec.implemented

    @property
    def label_text(self) -> str:
        spec = REGISTRY.get(self.type)
        return spec.label if spec is not None else "Unsupported constraint"

    def to_dict(self) -> dict:
        if self.raw is not None:
            return copy.deepcopy(self.raw)
        d = copy.deepcopy(self.extras)
        d |= {"id": self.id, "type": self.type, "refs": copy.deepcopy(self.refs),
             "value": self.value, "driving": self.driving, "enabled": self.enabled,
             "helper": copy.deepcopy(self.helper)}
        if self.label is not None:
            d["label"] = copy.deepcopy(self.label)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Constraint":
        c = cls(id=str(d.get("id") or uuid.uuid4().hex), type=str(d.get("type", "")),
                refs=copy.deepcopy(list(d.get("refs", []))), value=d.get("value"),
                driving=bool(d.get("driving", True)), enabled=bool(d.get("enabled", True)),
                helper=copy.deepcopy(dict(d.get("helper", {}))),
                label=copy.deepcopy(d.get("label")),
                extras={k: copy.deepcopy(v) for k, v in d.items() if k not in _KNOWN})
        if c.inert:
            c.raw = copy.deepcopy(d)
        return c


def remap_for_copy(cons, uid_map: dict) -> list:
    """§8 Copy/Paste/Duplicate/Array: keep only constraints internal to the
    copied set (every ref a mapped uid — grounds count as external), with
    fresh ids and remapped uids.

    Args:
        cons: Source constraint records (not modified).
        uid_map: Old primitive uid -> new primitive uid.

    Returns:
        New constraint records for the copied set.
    """
    out = []
    for c in cons:
        if c.inert or not c.refs:
            continue
        if any(not isinstance(r, dict) or is_ground(r) or r.get("uid") not in uid_map
               for r in c.refs):
            continue
        n = Constraint.from_dict(c.to_dict())
        n.id = uuid.uuid4().hex
        n.refs = [{**r, "uid": uid_map[r["uid"]]} for r in c.refs]
        out.append(n)
    return out
