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
    "Grid Line": "Medium", "Level Datum": "Very Light",
    "Elevation Marker": "Very Light", "Detail Marker": "Light",
}


def _make_factory_category(key: str) -> dict:
    """Build the factory default paper-space settings for one category."""
    cat = {
        "color": "#000000",
        "fill": "#ffffff" if key in _HAS_FILL else None,
        "section_color": "#000000" if key in _HAS_SECTION else None,
        "line_weight": _FACTORY_LW[key],
        "opacity": 100,
        "visible": True,
    }
    if key == "Grid Line":
        cat["bubble_label_height_mm"] = 3.0
    return cat


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
        # Start with factory defaults so any new keys are backfilled automatically.
        entry: dict = dict(factory)
        for prop in ("color", "fill", "section_color", "line_weight",
                     "opacity", "visible"):
            raw = settings.value(f"paper/categories/{key}/{prop}")
            if raw is not None:
                if prop == "opacity":
                    entry[prop] = int(float(raw))
                elif prop == "visible":
                    if isinstance(raw, bool):
                        entry[prop] = raw
                    elif isinstance(raw, str):
                        entry[prop] = raw.lower() not in ("false", "0")
                    else:
                        entry[prop] = bool(raw)
                else:
                    entry[prop] = raw
            # else: factory default already set above
        # Load any category-specific numeric extras (e.g. bubble_label_height_mm).
        for prop in factory:
            if prop not in entry or prop not in ("color", "fill", "section_color",
                                                  "line_weight", "opacity", "visible"):
                raw = settings.value(f"paper/categories/{key}/{prop}")
                if raw is not None:
                    try:
                        entry[prop] = float(raw)
                    except (ValueError, TypeError):
                        entry[prop] = raw
                # else: factory default already in entry from dict(factory) above
        result[key] = entry
    return result


def save_paper_categories(cats: dict[str, dict],
                          settings: QSettings | None = None):
    """Persist paper-space category overrides to QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    for key in _CATEGORY_KEYS:
        entry = cats.get(key, FACTORY_PAPER_CATEGORIES[key])
        for prop in ("color", "fill", "section_color", "line_weight",
                     "opacity", "visible"):
            val = entry.get(prop)
            if val is not None:
                settings.setValue(f"paper/categories/{key}/{prop}",
                                 str(val).lower() if prop == "visible" else val)
            else:
                settings.remove(f"paper/categories/{key}/{prop}")
        # Persist any category-specific numeric extras present in the factory.
        factory = FACTORY_PAPER_CATEGORIES[key]
        for prop in factory:
            if prop not in ("color", "fill", "section_color",
                            "line_weight", "opacity", "visible"):
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


def _apply_generic(item, cat, color_mode, lw_mm):
    """Apply paper overrides to a generic item (Wall, Room, Floor, Roof)."""
    if color_mode != PaperColorMode.FULL_COLOR:
        item._display_color = cat["color"]
        if hasattr(item, "_display_fill_color") and cat["fill"] is not None:
            item._display_fill_color = cat["fill"]
        if hasattr(item, "_display_section_color") and cat["section_color"] is not None:
            item._display_section_color = cat["section_color"]
    # Paper-space fill should render opaque (not semi-transparent like model).
    # Items like FloorSlab/Room use alpha 50 in model-space paint(); setting
    # _paper_fill_opaque tells them to skip the alpha reduction.
    item._paper_fill_opaque = True
    if hasattr(item, "pen") and callable(getattr(item, "setPen", None)):
        pen = item.pen()
        pen.setWidthF(lw_mm)
        pen.setCosmetic(False)
        item.setPen(pen)
    item.setOpacity(cat["opacity"] / 100.0)
    item.update()


def _apply_pipe(pipe, cat, color_mode, lw_mm):
    """Apply paper overrides to a Pipe — uses _paper_pen_width hook."""
    if color_mode != PaperColorMode.FULL_COLOR:
        pipe._display_color = cat["color"]
    pipe._paper_pen_width = lw_mm
    pipe.setOpacity(cat["opacity"] / 100.0)
    pipe.update()


def _apply_gridline(gl, cat, color_mode, lw_mm, paper_scale):
    """Apply paper overrides to a GridlineItem — colors + true-scale geometry (§9.9.1)."""
    from PyQt6.QtGui import QColor, QBrush
    from .gridline import bubble_paper_geometry

    S = max(paper_scale, 1e-9)
    cap_mm = cat.get("bubble_label_height_mm", 3.0)
    r_mm, em_mm = bubble_paper_geometry(cap_mm)

    gl._paper_render = True          # write-together unit with the two floats below
    gl._paper_line_w = lw_mm / S
    gl._paper_bubble_r = r_mm / S

    if color_mode != PaperColorMode.FULL_COLOR:
        gl._grid_color = QColor(cat["color"])
    # Authored color in full-color mode — suppresses the duplicate-warning
    # orange in ALL modes (a warning is not authored content, §9.9.1).
    pen_color = (QColor(cat["color"]) if color_mode != PaperColorMode.FULL_COLOR
                 else QColor(gl._grid_color))

    for bubble in (gl.bubble1, gl.bubble2):
        bubble._paper_saved = bubble.enter_paper_mode(r_mm / S, em_mm / S)
        # Model-side Display Manager bubble scale multiplier never affects
        # paper output (§9.9.1 isolation) — the multiplier is applied as an
        # item scale on each bubble, which would compound the paper radius.
        bubble.setScale(1.0)
        bp = bubble.pen()
        bp.setColor(pen_color)
        bp.setWidthF(lw_mm / S)
        bp.setCosmetic(False)
        bubble.setPen(bp)
        bubble._label.setDefaultTextColor(pen_color)
        if color_mode != PaperColorMode.FULL_COLOR and cat["fill"] is not None:
            bubble.setBrush(QBrush(QColor(cat["fill"])))

    gl._grip1.setVisible(False)
    gl._grip2.setVisible(False)
    gl._lock_indicator.setVisible(False)
    gl.setOpacity(cat["opacity"] / 100.0)
    gl.update()


def _apply_marker(marker, cat, color_mode, lw_mm, color_attr="_marker_color"):
    """Apply paper overrides to an elevation/detail marker."""
    from PyQt6.QtGui import QColor, QBrush, QPen
    if color_mode != PaperColorMode.FULL_COLOR:
        setattr(marker, color_attr, QColor(cat["color"]))
        pen = marker.pen()
        pen.setColor(QColor(cat["color"]))
        marker.setPen(pen)
        if cat["fill"] is not None and hasattr(marker, "_fill_color"):
            marker._fill_color = QColor(cat["fill"])
            marker.setBrush(QBrush(QColor(cat["fill"])))
    marker.setOpacity(cat["opacity"] / 100.0)
    marker.update()


def _save_gridline_state(gl) -> dict:
    """Capture gridline state for restore.

    Full pen/brush objects (not color names) and per-bubble entries — the two
    bubbles can legitimately differ (e.g. duplicate-warning pen).
    """
    from PyQt6.QtGui import QPen, QBrush
    return {
        "grid_color": gl._grid_color.name(),
        "bubble_pen": [QPen(b.pen()) for b in (gl.bubble1, gl.bubble2)],
        "bubble_brush": [QBrush(b.brush()) for b in (gl.bubble1, gl.bubble2)],
        "label_color": [b._label.defaultTextColor()
                        for b in (gl.bubble1, gl.bubble2)],
        "bubble_scale": [gl.bubble1.scale(), gl.bubble2.scale()],
        "grip_vis": (gl._grip1.isVisible(), gl._grip2.isVisible()),
        "lock_vis": gl._lock_indicator.isVisible(),
    }


def _save_marker_state(marker, color_attr="_marker_color") -> dict:
    """Capture marker state for restore."""
    from PyQt6.QtGui import QColor
    c = getattr(marker, color_attr, None)
    fill = getattr(marker, "_fill_color", None)
    return {
        "color_attr": color_attr,
        "marker_color": c.name() if isinstance(c, QColor) else c,
        "fill_color": fill.name() if isinstance(fill, QColor) else fill,
        "pen": marker.pen(),
        "brush": marker.brush(),
    }


def apply_paper_overrides(scene, source_rect, paper_scale: float = 1.0) -> list[dict]:
    """Temporarily mutate visible items to paper-space display settings.

    Type-aware: each item type is handled according to how its paint()
    method reads display properties. Returns a list of saved-state dicts
    for ``restore_model_display()``.

    Args:
        scene: Source QGraphicsScene being rendered through a viewport.
        source_rect: Model-space crop rect of the viewport.
        paper_scale: True geometric scale (paper mm per model mm) of the
            viewport render — drives true-scale gridline bubbles (§9.9.1).
    """
    from .display_manager import _set_svg_tint
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .pipe import Pipe
    from .gridline import GridlineItem

    color_mode = load_paper_color_mode()
    cats = load_paper_categories()
    saved: list[dict] = []
    items = scene.items(source_rect)

    for item in items:
        if not item.isVisible():
            continue
        if item.data(0) == "origin":
            # Model origin cross — authoring aid, never plots (§9.9.1).
            saved.append({"item": item, "cat_key": None,
                          "visible": item.isVisible()})
            item.setVisible(False)
            continue
        cat_key = _category_for_item(item)
        if cat_key is None:
            continue
        cat = cats.get(cat_key)
        if cat is None:
            continue

        # --- Save current state ---
        entry: dict = {
            "item": item,
            "cat_key": cat_key,
            "display_color": getattr(item, "_display_color", None),
            "display_fill_color": getattr(item, "_display_fill_color", None),
            "display_section_color": getattr(item, "_display_section_color", None),
            "opacity": item.opacity(),
            "visible": item.isVisible(),
            "pen": item.pen() if hasattr(item, "pen") else None,
        }

        # Type-specific extra state
        if isinstance(item, Pipe):
            entry["paper_pen_width"] = getattr(item, "_paper_pen_width", None)
        elif isinstance(item, GridlineItem):
            entry["gridline"] = _save_gridline_state(item)
        elif cat_key == "Elevation Marker":
            entry["marker"] = _save_marker_state(item, "_marker_color")
        elif cat_key == "Detail Marker":
            entry["marker"] = _save_marker_state(item, "_tag_color")

        saved.append(entry)

        # --- Visibility override ---
        if not cat.get("visible", True):
            item.setVisible(False)
            continue

        # --- Apply type-specific overrides ---
        lw_mm = resolve_line_weight_mm(cat["line_weight"])

        if isinstance(item, Pipe):
            _apply_pipe(item, cat, color_mode, lw_mm)
        elif isinstance(item, GridlineItem):
            _apply_gridline(item, cat, color_mode, lw_mm, paper_scale)
        elif isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
            if color_mode != PaperColorMode.FULL_COLOR:
                _set_svg_tint(item, cat["color"], cat.get("fill"))
            item.setOpacity(cat["opacity"] / 100.0)
        elif cat_key == "Elevation Marker":
            _apply_marker(item, cat, color_mode, lw_mm, "_marker_color")
        elif cat_key == "Detail Marker":
            _apply_marker(item, cat, color_mode, lw_mm, "_tag_color")
        else:
            _apply_generic(item, cat, color_mode, lw_mm)

    # --- Fittings (wrappers, not QGraphicsItems) ---
    if hasattr(scene, "sprinkler_system"):
        fitting_cat = cats.get("Fitting")
        if fitting_cat is not None:
            for node in scene.sprinkler_system.nodes:
                f = node.fitting
                if f is None or f.symbol is None or not f.symbol.isVisible():
                    continue
                if not source_rect.contains(f.symbol.scenePos()):
                    continue
                entry = {
                    "item": f.symbol,
                    "cat_key": "Fitting",
                    "fitting": f,
                    "display_color": getattr(f, "_display_color", None),
                    "display_fill_color": getattr(f, "_display_fill_color", None),
                    "opacity": f.symbol.opacity(),
                    "visible": f.symbol.isVisible(),
                    "pen": None,
                }
                saved.append(entry)
                if not fitting_cat.get("visible", True):
                    f.symbol.setVisible(False)
                    continue
                if color_mode != PaperColorMode.FULL_COLOR:
                    _set_svg_tint(f.symbol, fitting_cat["color"],
                                  fitting_cat.get("fill"))
                    f._display_color = fitting_cat["color"]
                    f._display_fill_color = fitting_cat.get("fill")
                f.symbol.setOpacity(fitting_cat["opacity"] / 100.0)

    return saved


def restore_model_display(saved: list[dict]):
    """Restore items to their pre-override state.

    Type-aware restore matching the type-aware apply.
    """
    from .display_manager import _set_svg_tint
    from .sprinkler import Sprinkler
    from .water_supply import WaterSupply
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .pipe import Pipe
    from .gridline import GridlineItem
    from PyQt6.QtGui import QColor, QBrush, QPen

    for entry in saved:
        item = entry["item"]
        cat_key = entry.get("cat_key")

        if cat_key is None:
            # Origin-cross entry — visibility only (§9.9.1).
            item.setVisible(entry.get("visible", True))
            continue

        # Restore visibility and opacity (common to all)
        item.setVisible(entry.get("visible", True))
        item.setOpacity(entry["opacity"])

        if isinstance(item, Pipe):
            item._display_color = entry["display_color"]
            item._paper_pen_width = entry.get("paper_pen_width")
            item.update()

        elif isinstance(item, GridlineItem):
            gs = entry.get("gridline", {})
            item._grid_color = QColor(gs["grid_color"])
            for i, bubble in enumerate((item.bubble1, item.bubble2)):
                # Matched pair with _apply_gridline's enter_paper_mode — but
                # the geometry stage is skipped when the category is hidden
                # (visibility continue), so guard on the saved marker.
                pm = getattr(bubble, "_paper_saved", None)
                if pm is not None:
                    bubble.exit_paper_mode(pm)
                    del bubble._paper_saved
                bubble.setScale(gs["bubble_scale"][i])
                bubble.setPen(gs["bubble_pen"][i])
                bubble.setBrush(gs["bubble_brush"][i])
                bubble._label.setDefaultTextColor(gs["label_color"][i])
            item._grip1.setVisible(gs["grip_vis"][0])
            item._grip2.setVisible(gs["grip_vis"][1])
            item._lock_indicator.setVisible(gs["lock_vis"])
            item._paper_render = False
            item.update()

        elif isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
            _set_svg_tint(item, entry["display_color"],
                          entry.get("display_fill_color"))
            item.update()

        elif cat_key in ("Elevation Marker", "Detail Marker"):
            ms = entry.get("marker", {})
            color_attr = ms.get("color_attr", "_marker_color")
            mc = ms.get("marker_color")
            if mc is not None:
                setattr(item, color_attr, QColor(mc))
            fc = ms.get("fill_color")
            if fc is not None and hasattr(item, "_fill_color"):
                item._fill_color = QColor(fc)
            if ms.get("pen") is not None:
                item.setPen(ms["pen"])
            if ms.get("brush") is not None:
                item.setBrush(ms["brush"])
            item.update()

        else:
            # Generic (Wall, Room, Floor, Roof)
            item._display_color = entry["display_color"]
            if hasattr(item, "_display_fill_color"):
                item._display_fill_color = entry.get("display_fill_color")
            if hasattr(item, "_display_section_color"):
                item._display_section_color = entry.get("display_section_color")
            if hasattr(item, "_paper_fill_opaque"):
                del item._paper_fill_opaque
            if entry.get("pen") is not None and hasattr(item, "setPen"):
                item.setPen(entry["pen"])
            item.update()

        # Restore fitting wrapper attributes
        fitting = entry.get("fitting")
        if fitting is not None:
            fitting._display_color = entry["display_color"]
            fitting._display_fill_color = entry.get("display_fill_color")
