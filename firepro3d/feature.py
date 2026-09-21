"""
feature.py — the minimal Feature layer (Phase A of the Feature system,
docs/specs/feature-system.md; behavior today under wall-room-floor-system.md §7).

A Feature is a saved, placeable *definition* organised as **Feature > Family > Type**
(docs/specs/feature-system.md F4):

    * **Feature** — class of building element ("Door" | "Window" | "Opening").
      The internal ``kind`` discriminator ("door"|"window"|"blank") drives paint +
      legacy migration; ``feature_label()`` maps it to the canonical Feature name.
    * **Family** — a family within a Feature ("Single-Flush" | "Fixed" | ...).
    * **Type**  — a concrete sized preset (the leaf; a ``.fpdf`` when libraries land).

Phase A defines Features in this code registry; Phase B (Manager) and Phase C
(Editor) add project-loaded sets and user authoring.  The parametric *engine*
(arbitrary parameter→geometry binding) is deferred: today a Family ships a fixed
set of Types whose sizes are read-only presets.
"""
from __future__ import annotations

from dataclasses import dataclass


# tier-1 "Feature" label, derived from the ``kind`` discriminator.  The blank
# opening is the canonical "Opening" Feature (its ``kind`` stays "blank" for
# paint + legacy-file migration).  See docs/specs/feature-system.md F4.
FEATURE_LABEL: dict[str, str] = {
    "door": "Door",
    "window": "Window",
    "blank": "Opening",
}


@dataclass(frozen=True)
class FeatureDef:
    id: str                       # stable identity — serialized as ``feature_id`` (never re-key)
    kind: str                     # paint/legacy discriminator: "door" | "window" | "blank"
    family: str                   # tier-2: "Single-Flush" | "Double-Flush" | "Fixed" | "Blank"
    type_name: str                # tier-3 leaf (Type): sized preset, e.g. "813 × 2032"
    host_type: str                # "Wall" (Phase A); future Floor/Ceiling/Face/Level
    display_name: str
    default_width_mm: float
    default_height_mm: float
    default_sill_mm: float = 0.0
    leaves: int = 1               # 2 = double-leaf door


def feature_label(fdef: "FeatureDef") -> str:
    """Return the canonical tier-1 Feature name ("Door"|"Window"|"Opening")."""
    return FEATURE_LABEL.get(fdef.kind, fdef.kind.title())


FEATURE_REGISTRY: dict[str, FeatureDef] = {
    "door_813": FeatureDef("door_813", "door", "Single-Flush", "813 × 2032", "Wall",
                           "Single-Flush 813 × 2032", 813.0, 2032.0, 0.0, 1),
    "door_914": FeatureDef("door_914", "door", "Single-Flush", "914 × 2032", "Wall",
                           "Single-Flush 914 × 2032", 914.0, 2032.0, 0.0, 1),
    "door_1829": FeatureDef("door_1829", "door", "Double-Flush", "1829 × 2032", "Wall",
                            "Double-Flush 1829 × 2032", 1829.0, 2032.0, 0.0, 2),
    "window_900": FeatureDef("window_900", "window", "Fixed", "900 × 1200", "Wall",
                             "Fixed 900 × 1200", 900.0, 1200.0, 900.0, 1),
    "blank_900": FeatureDef("blank_900", "blank", "Blank", "900 × 2100", "Wall",
                            "Blank 900 × 2100", 900.0, 2100.0, 0.0, 1),
}

# Default Type per ``kind`` (the ribbon Door/Window/Blank buttons resolve through this).
DEFAULT_FEATURE_FOR_TYPE: dict[str, str] = {
    "door": "door_914",
    "window": "window_900",
    "blank": "blank_900",
}


def get_feature(feature_id: str) -> FeatureDef:
    """Return the FeatureDef for *feature_id*, raising KeyError if absent."""
    return FEATURE_REGISTRY[feature_id]


def features_by_hierarchy() -> dict[str, dict[str, list[FeatureDef]]]:
    """Feature → Family → Type grouping for the Feature Browser (§7.13).

    Keys: the canonical Feature label ("Door"|"Window"|"Opening") → Family name
    → the Type-leaf FeatureDefs.
    """
    tree: dict[str, dict[str, list[FeatureDef]]] = {}
    for f in FEATURE_REGISTRY.values():
        tree.setdefault(feature_label(f), {}).setdefault(f.family, []).append(f)
    return tree


def nearest_feature_for(kind: str, width_mm: float) -> str:
    """Legacy-migration helper: pick the registry id of *kind* closest to width."""
    candidates = [f for f in FEATURE_REGISTRY.values() if f.kind == kind]
    if not candidates:
        candidates = list(FEATURE_REGISTRY.values())
    best = min(candidates, key=lambda f: abs(f.default_width_mm - width_mm))
    return best.id
