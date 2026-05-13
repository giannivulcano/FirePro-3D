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
from dataclasses import dataclass, asdict
from enum import Enum

from PyQt6.QtCore import QSettings


# ---------------------------------------------------------------------------
# Line weight definitions
# ---------------------------------------------------------------------------

@dataclass
class LineWeightDef:
    """A named pen weight used in paper-space rendering."""
    name: str
    width_mm: float


FACTORY_LINE_WEIGHTS: list[LineWeightDef] = [
    LineWeightDef("Very Light", 0.13),
    LineWeightDef("Light",      0.18),
    LineWeightDef("Medium",     0.25),
    LineWeightDef("Heavy",      0.35),
    LineWeightDef("Very Heavy", 0.50),
]


def load_line_weights(settings: QSettings | None = None) -> list[LineWeightDef]:
    """Load line weight definitions from QSettings, or return factory defaults."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    raw = settings.value("paper/line_weights")
    if raw is None:
        return list(FACTORY_LINE_WEIGHTS)
    try:
        entries = json.loads(raw) if isinstance(raw, str) else raw
        return [LineWeightDef(e["name"], float(e["width_mm"])) for e in entries]
    except (json.JSONDecodeError, KeyError, TypeError):
        return list(FACTORY_LINE_WEIGHTS)


def save_line_weights(defs: list[LineWeightDef],
                      settings: QSettings | None = None):
    """Persist line weight definitions to QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    data = json.dumps([asdict(d) for d in defs])
    settings.setValue("paper/line_weights", data)
    settings.sync()


def validate_line_weight_name(name: str,
                              existing: list[LineWeightDef]) -> bool:
    """Return True if *name* is valid (non-empty, unique)."""
    if not name or not name.strip():
        return False
    return all(lw.name != name.strip() for lw in existing)


def validate_line_weight_width(width_mm: float) -> bool:
    """Return True if *width_mm* is valid (positive, <= 3.0)."""
    return 0.0 < width_mm <= 3.0


# ---------------------------------------------------------------------------
# Color mode
# ---------------------------------------------------------------------------

class PaperColorMode(Enum):
    """Paper-space color rendering mode."""
    FULL_COLOR = "full_color"
    BW = "bw"
    CUSTOM = "custom"


def load_paper_color_mode(settings: QSettings | None = None) -> PaperColorMode:
    """Load paper color mode from QSettings, defaulting to B&W."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    raw = settings.value("paper/color_mode")
    try:
        return PaperColorMode(raw)
    except (ValueError, KeyError):
        return PaperColorMode.BW


def save_paper_color_mode(mode: PaperColorMode,
                          settings: QSettings | None = None):
    """Persist paper color mode to QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    settings.setValue("paper/color_mode", mode.value)
    settings.sync()


# ---------------------------------------------------------------------------
# Per-category paper-space overrides
# ---------------------------------------------------------------------------

# Keys match _CATEGORIES in display_manager.py
_CATEGORY_KEYS = [
    "Pipe", "Sprinkler", "Fitting", "Water Supply", "Node",
    "Hydraulic Badge", "Wall", "Roof", "Room", "Floor",
    "Grid Line", "Level Datum", "Elevation Marker", "Detail Marker",
]

# Which categories have a fill colour (mirrors display_manager._CATEGORIES)
_HAS_FILL = {"Sprinkler", "Water Supply", "Hydraulic Badge", "Wall", "Roof",
             "Room", "Floor", "Grid Line", "Level Datum", "Elevation Marker",
             "Detail Marker"}

# Which categories have section colour
_HAS_SECTION = {"Wall", "Roof", "Floor"}

# Factory default line weight per category
_FACTORY_LW = {
    "Pipe": "Medium", "Sprinkler": "Medium", "Fitting": "Medium",
    "Water Supply": "Medium", "Node": "Light", "Hydraulic Badge": "Very Light",
    "Wall": "Heavy", "Roof": "Medium", "Room": "Very Light", "Floor": "Medium",
    "Grid Line": "Very Light", "Level Datum": "Very Light",
    "Elevation Marker": "Very Light", "Detail Marker": "Light",
}


def _make_factory_category(key: str) -> dict:
    """Build the factory default paper-space settings for one category."""
    return {
        "color": "#000000",
        "fill": "#ffffff" if key in _HAS_FILL else None,
        "section_color": "#000000" if key in _HAS_SECTION else None,
        "line_weight": _FACTORY_LW[key],
        "opacity": 100,
    }


FACTORY_PAPER_CATEGORIES: dict[str, dict] = {
    k: _make_factory_category(k) for k in _CATEGORY_KEYS
}


def load_paper_categories(settings: QSettings | None = None) -> dict[str, dict]:
    """Load paper-space category overrides from QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    result: dict[str, dict] = {}
    for key in _CATEGORY_KEYS:
        factory = FACTORY_PAPER_CATEGORIES[key]
        entry: dict = {}
        for prop in ("color", "fill", "section_color", "line_weight", "opacity"):
            raw = settings.value(f"paper/categories/{key}/{prop}")
            if raw is not None:
                entry[prop] = int(float(raw)) if prop == "opacity" else raw
            else:
                entry[prop] = factory[prop]
        result[key] = entry
    return result


def save_paper_categories(cats: dict[str, dict],
                          settings: QSettings | None = None):
    """Persist paper-space category overrides to QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    for key in _CATEGORY_KEYS:
        entry = cats.get(key, FACTORY_PAPER_CATEGORIES[key])
        for prop in ("color", "fill", "section_color", "line_weight", "opacity"):
            val = entry.get(prop)
            if val is not None:
                settings.setValue(f"paper/categories/{key}/{prop}", val)
            else:
                settings.remove(f"paper/categories/{key}/{prop}")
    settings.sync()


# ---------------------------------------------------------------------------
# Project file persistence
# ---------------------------------------------------------------------------

def get_paper_display_for_save() -> dict:
    """Return paper display settings for embedding in the project file."""
    return {
        "color_mode": load_paper_color_mode().value,
        "categories": load_paper_categories(),
    }


def apply_paper_display_from_project(data: dict | None):
    """Apply paper display settings loaded from a project file."""
    if not data:
        # No paper_display in project -- reset to factory
        save_paper_color_mode(PaperColorMode.BW)
        save_paper_categories(FACTORY_PAPER_CATEGORIES)
        return
    # Color mode
    mode_str = data.get("color_mode", "bw")
    try:
        mode = PaperColorMode(mode_str)
    except ValueError:
        mode = PaperColorMode.BW
    save_paper_color_mode(mode)
    # Categories -- merge project values over factory defaults
    proj_cats = data.get("categories", {})
    merged: dict[str, dict] = {}
    for key in _CATEGORY_KEYS:
        factory = FACTORY_PAPER_CATEGORIES[key]
        proj = proj_cats.get(key, {})
        entry = dict(factory)
        entry.update({k: v for k, v in proj.items() if v is not None})
        merged[key] = entry
    save_paper_categories(merged)


# ---------------------------------------------------------------------------
# Viewport rendering helpers
# ---------------------------------------------------------------------------

def resolve_line_weight_mm(name: str,
                           settings: QSettings | None = None) -> float:
    """Resolve a line weight name to its mm width.  Falls back to 0.25mm."""
    defs = load_line_weights(settings)
    for d in defs:
        if d.name == name:
            return d.width_mm
    return 0.25


def _category_for_item(item) -> str | None:
    """Map a QGraphicsItem to its display category key."""
    from .pipe import Pipe
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .node import Node
    from .gridline import GridlineItem
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .wall import WallSegment
    from .room import Room

    if isinstance(item, Pipe):
        return "Pipe"
    if isinstance(item, Sprinkler):
        return "Sprinkler"
    if isinstance(item, WallSegment):
        return "Wall"
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
    # Detect by class name to avoid circular imports
    cls_name = type(item).__name__
    if cls_name == "RoofItem":
        return "Roof"
    if cls_name == "FloorSlab":
        return "Floor"
    if cls_name == "ViewMarkerArrow":
        return "Elevation Marker"
    if cls_name == "DetailMarker":
        return "Detail Marker"
    if cls_name == "LevelDatumItem":
        return "Level Datum"
    return None


def apply_paper_overrides(scene, source_rect) -> list[dict]:
    """Temporarily mutate visible items to paper-space display settings.

    Returns a list of saved-state dicts for restore_model_display().
    """
    from .display_manager import _set_svg_tint
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .pipe import Pipe

    color_mode = load_paper_color_mode()
    cats = load_paper_categories()
    saved: list[dict] = []
    items = scene.items(source_rect)

    for item in items:
        if not item.isVisible():
            continue
        cat_key = _category_for_item(item)
        if cat_key is None:
            continue
        cat = cats.get(cat_key)
        if cat is None:
            continue

        entry: dict = {
            "item": item,
            "display_color": getattr(item, "_display_color", None),
            "display_fill_color": getattr(item, "_display_fill_color", None),
            "display_section_color": getattr(item, "_display_section_color", None),
            "opacity": item.opacity(),
            "pen": item.pen() if hasattr(item, "pen") else None,
        }
        saved.append(entry)

        lw_mm = resolve_line_weight_mm(cat["line_weight"])

        if color_mode != PaperColorMode.FULL_COLOR:
            item._display_color = cat["color"]
            if hasattr(item, "_display_fill_color") and cat["fill"] is not None:
                item._display_fill_color = cat["fill"]
            if hasattr(item, "_display_section_color") and cat["section_color"] is not None:
                item._display_section_color = cat["section_color"]
            if isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
                _set_svg_tint(item, cat["color"], cat.get("fill"))

        if isinstance(item, Pipe):
            item.set_pipe_display()
            pen = item.pen()
            pen.setWidthF(lw_mm)
            pen.setCosmetic(False)
            item.setPen(pen)
        elif hasattr(item, "pen") and callable(getattr(item, "setPen", None)):
            pen = item.pen()
            pen.setWidthF(lw_mm)
            pen.setCosmetic(False)
            item.setPen(pen)

        item.setOpacity(cat["opacity"] / 100.0)
        item.update()

    return saved


def restore_model_display(saved: list[dict]):
    """Restore items to their pre-override state."""
    from .display_manager import _set_svg_tint
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .pipe import Pipe

    for entry in saved:
        item = entry["item"]
        item._display_color = entry["display_color"]
        if hasattr(item, "_display_fill_color"):
            item._display_fill_color = entry["display_fill_color"]
        if hasattr(item, "_display_section_color"):
            item._display_section_color = entry["display_section_color"]
        item.setOpacity(entry["opacity"])

        if isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
            _set_svg_tint(item, entry["display_color"], entry["display_fill_color"])
        if isinstance(item, Pipe):
            item.set_pipe_display()
        elif entry["pen"] is not None and hasattr(item, "setPen"):
            item.setPen(entry["pen"])
        item.update()
