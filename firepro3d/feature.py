"""
feature.py — the minimal Feature layer (Phase A of the Feature system,
docs/specs/wall-room-floor-system.md §7.2/§7.16).

A Feature is a saved, parametric, placeable *definition* — Feature > Category > Type,
with a host_type. Phase A defines Features in this code registry; Phase B (Manager)
and Phase C (Editor) add project-loaded sets and user authoring.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureDef:
    id: str
    category: str                 # "Openings" | (future) "Furniture" | "Fixtures"
    type: str                     # "door" | "window" | "blank"
    host_type: str                # "Wall" (Phase A); future Floor/Ceiling/Face/Level
    display_name: str
    default_width_mm: float
    default_height_mm: float
    default_sill_mm: float = 0.0
    leaves: int = 1               # 2 = double-leaf door


FEATURE_REGISTRY: dict[str, FeatureDef] = {
    "door_813": FeatureDef("door_813", "Openings", "door", "Wall",
                           "Single Door 813", 813.0, 2032.0, 0.0, 1),
    "door_914": FeatureDef("door_914", "Openings", "door", "Wall",
                           "Single Door 914", 914.0, 2032.0, 0.0, 1),
    "door_1829": FeatureDef("door_1829", "Openings", "door", "Wall",
                            "Double Door 1829", 1829.0, 2032.0, 0.0, 2),
    "window_900": FeatureDef("window_900", "Openings", "window", "Wall",
                             "Window 900×1200", 900.0, 1200.0, 900.0, 1),
    "blank_900": FeatureDef("blank_900", "Openings", "blank", "Wall",
                            "Blank Opening 900×2100", 900.0, 2100.0, 0.0, 1),
}

DEFAULT_FEATURE_FOR_TYPE: dict[str, str] = {
    "door": "door_914",
    "window": "window_900",
    "blank": "blank_900",
}


def get_feature(feature_id: str) -> FeatureDef:
    """Return the FeatureDef for *feature_id*, raising KeyError if absent."""
    return FEATURE_REGISTRY[feature_id]


def features_by_category() -> dict[str, dict[str, list[FeatureDef]]]:
    """Feature > Category > Type grouping for the Feature Browser (§7.13)."""
    tree: dict[str, dict[str, list[FeatureDef]]] = {}
    for f in FEATURE_REGISTRY.values():
        tree.setdefault(f.category, {}).setdefault(f.type, []).append(f)
    return tree


def nearest_feature_for(type_: str, width_mm: float) -> str:
    """Legacy-migration helper: pick the registry id of *type_* closest to width."""
    candidates = [f for f in FEATURE_REGISTRY.values() if f.type == type_]
    if not candidates:
        candidates = list(FEATURE_REGISTRY.values())
    best = min(candidates, key=lambda f: abs(f.default_width_mm - width_mm))
    return best.id
