"""
display_manager.py
==================
Revit-style Display Manager dialog for fire-suppression component appearance.

Provides per-category and per-instance control over visibility, colour, fill
colour, scale factor, and opacity.  Changes are applied live to the canvas;
cancelling the dialog reverts all changes to their prior state.

Replaces the older FSVisibilityDialog.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox,
    QHeaderView, QWidget, QLabel, QComboBox,
    QAbstractItemView, QTabWidget,
)
from PyQt6.QtGui import (QColor, QFont, QBrush, QPen,
                         QIcon)
from PyQt6.QtCore import Qt, QSettings, QByteArray, QSize, pyqtSignal
from PyQt6.QtSvg import QSvgRenderer

import json
import os
import xml.etree.ElementTree as ET
from . import theme as th
from . import colour_picker
from . import fill_types
from .ui_kit import Selector
from .constants import MODEL_WEIGHT_PX_MAX, TOKEN_AUTO
from .colour_tokens import is_token, resolve_colour, token_label
from .fill_layers import to_record


# ---------------------------------------------------------------------------
# SVG recolouring — set fill/stroke on the top-level layer group
# ---------------------------------------------------------------------------

_svg_color_cache: dict[tuple, QByteArray] = {}

# SVG namespace constants
_SVG_NS = "http://www.w3.org/2000/svg"
_INK_NS = "http://www.inkscape.org/namespaces/inkscape"
_SODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"

# Register so ET.tostring preserves prefixes
ET.register_namespace("", _SVG_NS)
ET.register_namespace("inkscape", _INK_NS)
ET.register_namespace("sodipodi", _SODI_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
ET.register_namespace("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
ET.register_namespace("cc", "http://creativecommons.org/ns#")
ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")


def _parse_css(style_str: str) -> dict[str, str]:
    """Parse inline CSS ``'prop:val;prop2:val2'`` into an ordered dict."""
    result: dict[str, str] = {}
    for part in style_str.split(";"):
        part = part.strip()
        if ":" in part:
            k, v = part.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def _build_css(d: dict[str, str]) -> str:
    return ";".join(f"{k}:{v}" for k, v in d.items())


def _recolor_svg_bytes(svg_path: str, color: str | None = None,
                       fill_color: str | None = None) -> QByteArray:
    """Recolour an SVG by setting fill/stroke on the top-level layer group.

    *color*      → applied as ``stroke`` on the layer ``<g>`` element.
    *fill_color* → applied as ``fill``   on the layer ``<g>`` element.
    Descendant elements have their explicit stroke/fill replaced with
    ``inherit`` so they pick up the group values.  ``fill:none`` and
    ``stroke:none`` are preserved (transparent elements stay transparent).
    Results are cached by *(path, color, fill_color)*.
    """
    if is_token(color):
        color = resolve_colour(color).name()
    elif color == "":
        color = "none"              # No stroke (universal picker)
    if is_token(fill_color):
        fill_color = resolve_colour(fill_color).name()
    elif fill_color == "":
        fill_color = "none"         # No Fill
    key = (svg_path, color, fill_color)
    if key in _svg_color_cache:
        return _svg_color_cache[key]

    with open(svg_path, "r", encoding="utf-8") as f:
        raw = f.read()

    change_stroke = color is not None and color.lower() != "#ffffff"
    change_fill = fill_color is not None

    if not change_stroke and not change_fill:
        data = QByteArray(raw.encode("utf-8"))
        _svg_color_cache[key] = data
        return data

    root = ET.fromstring(raw)

    # Find the inkscape layer group (<g inkscape:groupmode="layer">)
    layer = None
    for g in root.iter(f"{{{_SVG_NS}}}g"):
        if g.get(f"{{{_INK_NS}}}groupmode") == "layer":
            layer = g
            break

    if layer is not None:
        # ── Set fill / stroke on the layer group's style ──────────────
        style = _parse_css(layer.get("style", ""))
        if change_stroke:
            style["stroke"] = color
        if change_fill:
            style["fill"] = fill_color
        layer.set("style", _build_css(style))

        # ── Make descendants inherit (skip fill:none / stroke:none) ───
        for elem in layer.iter():
            if elem is layer:
                continue
            s = elem.get("style")
            if not s:
                continue
            props = _parse_css(s)
            changed = False
            if change_stroke and "stroke" in props:
                if props["stroke"].lower() not in ("none", "inherit"):
                    props["stroke"] = "inherit"
                    changed = True
            if change_fill and "fill" in props:
                if props["fill"].lower() not in ("none", "inherit"):
                    props["fill"] = "inherit"
                    changed = True
            if changed:
                elem.set("style", _build_css(props))

    out = ET.tostring(root, encoding="unicode", xml_declaration=True)
    data = QByteArray(out.encode("utf-8"))
    _svg_color_cache[key] = data
    return data



def _set_svg_tint(item, color: str | None, fill_color: str | None = None):
    """Apply colour tint by setting fill/stroke on the SVG layer group.

    *color*      → ``stroke`` on the top-level ``<g>`` element.
    *fill_color* → ``fill``   on the top-level ``<g>`` element.
    Falls back to the original SVG when both are None/default.
    Requires ``_svg_source_path`` on the item.
    """
    item._display_color = color
    item._display_fill_color = fill_color
    if is_token(color):
        color = resolve_colour(color).name()
    # Remove any leftover QGraphicsColorizeEffect from older sessions
    if item.graphicsEffect() is not None:
        item.setGraphicsEffect(None)

    src = getattr(item, "_svg_source_path", None)
    if src is None or not os.path.isfile(src):
        return  # can't recolour without the source path

    needs_recolor = ((color and color.lower() != "#ffffff") or color == ""
                     or (fill_color is not None))
    if needs_recolor:
        data = _recolor_svg_bytes(src, color, fill_color)
        renderer = QSvgRenderer(data)
    else:
        renderer = QSvgRenderer(src)

    item.prepareGeometryChange()
    item.setSharedRenderer(renderer)
    item._renderer = renderer  # prevent garbage collection

    # Re-centre after renderer change
    if hasattr(item, "_centre_on_node"):
        item._centre_on_node()
    elif hasattr(item, "_centre_on_offset"):
        item._centre_on_offset()
    elif hasattr(item, "_centre_on_origin"):
        item._centre_on_origin()
    item.update()


# ---------------------------------------------------------------------------
# Fill-value helpers  (plain "#rrggbb" = solid, "hatch:#rrggbb" = hatch)
# ---------------------------------------------------------------------------

def _parse_fill_value(val: str | None) -> tuple[str, str]:
    """Return (mode, hex_color).  mode is 'solid' or 'hatch'."""
    if val is None:
        return ("solid", "#000000")
    if val == "":
        return ("solid", "")            # No Fill: distinct from None (inherit)
    if val.startswith("hatch:"):
        return ("hatch", val[6:])
    return ("solid", val)


def _compose_fill_value(mode: str, hex_color: str) -> str:
    """Encode mode + colour into the single string stored on the button."""
    if mode == "hatch":
        return f"hatch:{hex_color}"
    return hex_color


def _apply_swatch_look(btn, value: str | None, _t) -> None:
    """Paint a solid Colour-column swatch: a token resolves for the fill and
    shows its label ("Automatic" / "Accent"); hex shows no text (HF1, R7)."""
    label = token_label(value)
    if value == "":
        # No Fill / no stroke: a transparent chip captioned "None".
        btn.setText("None")
        btn.setStyleSheet(
            f"background: transparent; color: {_t.muted}; font-size: 9px; "
            f"border: 1px solid {_t.border_subtle}; border-radius: 2px;")
        return
    shown = resolve_colour(value).name() if label else value
    btn.setText(label or "")
    text_css = ""
    if label:
        c = resolve_colour(value)
        text_css = (f"color: {'#000000' if c.lightness() > 128 else '#ffffff'}; "
                    "font-size: 9px; ")
    btn.setStyleSheet(
        f"background: {shown}; {text_css}border: 1px solid {_t.border_subtle}; "
        f"border-radius: 2px;")


def _fill_or(value, default):
    """*value* unless unset (``None``): ``""`` (No Fill) is a real value and
    must not fall back to the category default."""
    return default if value is None else value


def _fill_qcolor(value) -> QColor:
    """QColor for a stored fill/section colour string: a ``token:*`` resolves
    (canvas surface), ``""`` (No Fill) is fully transparent so a brush, pen or
    icon built from it draws nothing."""
    if value == "":
        return QColor(0, 0, 0, 0)
    return resolve_colour(value)


# ---------------------------------------------------------------------------
# Category definitions — order matches the tree from top to bottom
# ---------------------------------------------------------------------------

_CATEGORIES: list[dict] = [
    {"key": "Pipe",             "color": "#4488ff", "fill": None,      "section": None,      "section_pattern": None,        "font": 12,   "scale": 1.0, "opacity": 100, "visible": True, "group": "Fire Suppression"},
    {"key": "Sprinkler",        "color": "#ff4444", "fill": "#000000", "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Fire Suppression"},
    {"key": "Fitting",          "color": "#44cc44", "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Fire Suppression"},
    {"key": "Water Supply",     "color": "#00cccc", "fill": "#2b2b2e", "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Fire Suppression"},
    {"key": "Node",             "color": "#888888", "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Fire Suppression"},
    {"key": "Hydraulic Badge",  "color": "#ffffff", "fill": "#2b2b2b", "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Fire Suppression"},
    {"key": "Design Area",      "color": "#dc1e1e", "fill": "#ffc800", "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Fire Suppression"},
    {"key": "Wall",             "color": "#666666", "fill": "#999999", "section": "#666666", "section_pattern": "diagonal", "section_type": "Wall Section",  "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Door",            "color": "#888888", "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Window",          "color": "#888888", "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Opening",         "color": "#888888", "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Roof",             "color": "#8B4513", "fill": "#D2B48C", "section": None,      "section_pattern": None,         "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Room",             "color": "#4488cc", "fill": "#4488cc", "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Floor",            "color": "#8888cc", "fill": "#8888cc", "section": "#666666", "section_pattern": "diagonal", "section_type": "Floor Section",  "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Grid Line",        "color": "#4488cc", "fill": "#1a1a2e", "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Grids & Levels"},
    {"key": "Level Datum",      "color": "#4488cc", "fill": "#1a1a2e", "section": None,      "section_pattern": None,        "font": 10,   "scale": 1.0, "opacity": 100, "visible": True, "group": "Grids & Levels"},
    {"key": "Elevation Marker", "label": "Section Marker", "color": "#4488cc", "fill": "#1a1a2e", "section": None,      "section_pattern": None,        "font": 10,   "scale": 1.0, "opacity": 100, "visible": True, "group": "Grids & Levels"},
    {"key": "Detail Marker",    "color": "#4488cc", "fill": "#1a1a2e", "section": None,      "section_pattern": None,        "font": 10,   "scale": 1.0, "opacity": 100, "visible": True, "group": "Grids & Levels"},
    {"key": "2D Geometry",      "color": TOKEN_AUTO, "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Annotation & Geometry"},
    {"key": "Reference Geometry", "color": "#888888", "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Annotation & Geometry"},
]

# Group display order
_GROUPS = ["Fire Suppression", "Architecture", "Grids & Levels", "Annotation & Geometry"]

# Tree-column indices
_COL_NAME    = 0
_COL_VIS     = 1
_COL_COLOR   = 2
_COL_FILL    = 3
_COL_SECTION = 4
_COL_SCALE   = 5
_COL_OPACITY = 6
_COL_FONT    = 7
_COL_LW      = 8
_COL_RESET   = 9

# Weight-only Model-tab row (linetypes.md LT2-6) -- NOT a _CATEGORIES entry.
_MODEL_BLOCKS_KEY = "Blocks"

# Line Weights tab "Model (px)" column header + cell tooltip (MW-11).
_MODEL_PX_TIP = (
    "Canvas width of this weight in screen pixels (model views and the "
    "Block Editor; paper always prints the mm width). Auto = paper mm x the "
    "Model line weight scale (System Settings > UI), rounded, at least 1 px. "
    f"Type a whole number from 1 to {MODEL_WEIGHT_PX_MAX} to override; clear "
    "the cell or type 'auto' to return to Auto.")


_CATEGORY_MAP: dict[str, dict] = {c["key"]: c for c in _CATEGORIES}


def category_label(key: str) -> str:
    """Display name of a category row; the settings key when no label is set (D8)."""
    cat = _CATEGORY_MAP.get(key)
    return cat.get("label", key) if cat else key


# ---------------------------------------------------------------------------
# Shared QSettings read/write helpers — eliminates repeated patterns
# ---------------------------------------------------------------------------

def _read_category_from_settings(key: str, settings: QSettings | None = None,
                                  overrides: dict | None = None) -> dict:
    """Read display settings for category *key* from QSettings.

    If *overrides* is given (e.g. from a project file), those values take
    priority over QSettings, which in turn takes priority over factory
    defaults from ``_CATEGORIES``.

    Returns dict with keys: color, fill, section_type (a Fill Type *name*, or
    None for a category without a section cell), section_look (its fill
    record), scale, opacity, visible, font.
    """
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    _migrate_display_keys(settings)
    cat_def = _CATEGORY_MAP[key]
    ov = overrides or {}

    def _s(prop, default):
        """Read from overrides → QSettings → factory default."""
        if prop in ov:
            return ov[prop]
        return settings.value(f"display/{key}/{prop}", default)

    color   = _s("color", cat_def["color"])
    fill    = _s("fill", cat_def.get("fill"))
    section_type = section_look = None
    if cat_def.get("section_type"):
        # HF5 R7: the category names a Fill Type and stores its look. Legacy
        # colour / pattern / scale (a pre-HF5 file or QSettings) are conversion
        # input only; an override carrying them and no type wins over a stored one.
        legacy_ov = ("section_type" not in ov
                     and any(k in ov for k in _LEGACY_SECTION_PROPS))
        section_type = (cat_def["section_type"] if legacy_ov
                        else _s("section_type", None) or cat_def["section_type"])
        section_look = None if legacy_ov else _parse_section_look(_s("section_look", None))
    if section_type and section_look is None:
        # Read "section" key, falling back to legacy "hatch" key in QSettings
        section = _s("section", None)
        if section is None:
            section = _s("hatch", cat_def.get("section"))
        section_look = to_record(fill_types.legacy_section_layers(
            section, _s("section_pattern", cat_def.get("section_pattern")),
            float(_s("section_scale", 1.0))))
    scale   = float(_s("scale", cat_def["scale"]))
    opacity = int(float(_s("opacity", cat_def["opacity"])))
    visible = _s("visible", cat_def["visible"])
    if isinstance(visible, str):
        visible = visible.lower() not in ("false", "0")
    elif not isinstance(visible, bool):
        visible = bool(visible)
    font = cat_def.get("font")
    if font is not None:
        font = int(float(_s("font", font)))

    return {"color": color, "fill": fill, "section_type": section_type,
            "section_look": section_look,
            "scale": scale, "opacity": opacity, "visible": visible,
            "font": font}


def _store_section_cell(settings: QSettings, key: str, vals: dict,
                        prefix: str = "") -> None:
    """Write category *key*'s section cell (HF5 R7) as ``section_type`` (the
    Fill Type's name) + ``section_look`` (its fill record, JSON) under
    ``display/{key}/{prefix}...``; the legacy colour / pattern / scale keys
    are retired (removed), never written again.

    Args:
        settings: The QSettings store.
        key: Category key.
        vals: Category values carrying ``section_type`` / ``section_look``.
        prefix: ``"default_"`` for the "Set as Default" keys, else ``""``.
    """
    name = vals.get("section_type")
    if not (_category_has_section(key) and name):
        return
    settings.setValue(f"display/{key}/{prefix}section_type", name)
    if vals.get("section_look"):
        settings.setValue(f"display/{key}/{prefix}section_look",
                          json.dumps(vals["section_look"]))
    for legacy in (*_LEGACY_SECTION_PROPS, "hatch"):
        settings.remove(f"display/{key}/{prefix}{legacy}")


def _write_category_to_settings(key: str, vals: dict,
                                 settings: QSettings | None = None):
    """Write display settings for category *key* to QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    settings.setValue(f"display/{key}/color", vals["color"])
    settings.setValue(f"display/{key}/scale", vals["scale"])
    settings.setValue(f"display/{key}/opacity", vals["opacity"])
    settings.setValue(f"display/{key}/visible", str(vals["visible"]).lower())
    if vals.get("fill") is not None:
        settings.setValue(f"display/{key}/fill", vals["fill"])
    _store_section_cell(settings, key, vals)
    if vals.get("font") is not None:
        settings.setValue(f"display/{key}/font", vals["font"])


def _apply_to_scene_items(scene, key: str, vals: dict,
                           respect_overrides: bool = True):
    """Apply display settings *vals* to all items of category *key*."""
    items = _items_for_category_static(scene, key)
    for obj in items:
        _apply_vals_to_item(obj, vals, respect_overrides, key=key)


def _apply_vals_to_item(obj, vals: dict, respect_overrides: bool = True,
                        key: str | None = None) -> None:
    """Apply one category's display *vals* to *obj* (its per-item
    ``_display_overrides`` win when *respect_overrides*).

    *key* names the category: with a section cell, the item's cut Fill Type is
    the category's (``vals["section_type"]`` / ``section_look``, legacy
    converted) unless a per-item override names another (legacy per-item
    section keys convert here, once -- R4)."""
    tid = None
    if key is not None and _category_has_section(key):
        tid = fill_types.category_section_type(key, vals)
        if respect_overrides:
            ov = getattr(obj, "_display_overrides", None)
            if isinstance(ov, dict):
                fill_types.convert_item_section_override(
                    key, ov, fill_types.resolve(tid, None)[0] if tid else None)
                tid = ov.get("section_type", tid)
    if respect_overrides:
        ov = getattr(obj, "_display_overrides", {})
        c = ov.get("color", vals["color"])
        s = ov.get("scale", vals["scale"])
        o = ov.get("opacity", vals["opacity"])
        v = ov.get("visible", vals["visible"])
        f = ov.get("fill", vals.get("fill"))
        fn = ov.get("font", vals.get("font"))
    else:
        c, s, o, v = vals["color"], vals["scale"], vals["opacity"], vals["visible"]
        f, fn = vals.get("fill"), vals.get("font")
    apply_display_to_item(obj, c, s, o, v, fill_color=f, font_size=fn,
                          section_type=tid)


def refresh_category_display(item) -> None:
    """Apply the live Display-Manager values of a 2D primitive's category
    (Reference Geometry when flagged, else 2D Geometry) -- design RG10.

    Args:
        item: A 2D primitive (``Geometry2DMixin``) whose ``reference`` flag
            picks the category.
    """
    key = "Reference Geometry" if getattr(item, "reference", False) else "2D Geometry"
    vals = _read_category_from_settings(key)
    _apply_vals_to_item(item, vals, respect_overrides=True, key=key)


def _category_has_fill(key: str) -> bool:
    """Return True if this category supports a fill colour column."""
    c = _CATEGORY_MAP.get(key)
    return c is not None and c["fill"] is not None


def _category_has_section(key: str) -> bool:
    """Return True if this category's section cell picks a Fill Type (HF5)."""
    c = _CATEGORY_MAP.get(key)
    return c is not None and c.get("section_type") is not None


_LEGACY_SECTION_PROPS = ("section", "section_pattern", "section_scale")
_SECTION_PROPS = ("section_type", "section_look") + _LEGACY_SECTION_PROPS


def _parse_section_look(raw) -> dict | None:
    """A stored ``section_look`` (a JSON string in QSettings, a dict in a
    project payload) as a fill record; None when absent or unreadable."""
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    return raw if isinstance(raw, dict) and raw else None


def _fill_type_icon(layers, registry=None) -> QIcon:
    """40x20 swatch of a Fill Type's look for the section selector: body behind
    the pattern; By element (R8) previews in Automatic (the element's colour is
    only known at paint)."""
    from .fill_types_tab import look_pixmap
    return QIcon(look_pixmap(layers, registry, 40, 20))


# Cut-item state the live preview writes (walls, floors): restored on Cancel.
_CUT_ATTRS = ("_display_section_type", "_display_color", "_display_fill_color",
              "_display_scale", "_fill_mode")

_NO_SCALE_CATEGORIES = {"Wall", "Roof", "Room", "Floor"}


def _category_has_scale(key: str) -> bool:
    """Return True if this category supports the scale column."""
    return key not in _NO_SCALE_CATEGORIES


def _category_has_font(key: str) -> bool:
    """Return True if this category supports a font size column."""
    c = _CATEGORY_MAP.get(key)
    return c is not None and c["font"] is not None


# ──────────────────────────────────────────────────────────────────────────────
# Public helper — apply display settings to a single item
# ──────────────────────────────────────────────────────────────────────────────

def apply_display_to_item(item, color: str | None, scale: float,
                          opacity: float, visible: bool,
                          fill_color: str | None = None,
                          font_size: int | None = None,
                          section_type: str | None = None):
    """Apply display settings to *item* (Pipe, Sprinkler, Fitting, Node,
    WaterSupply, GridlineItem, or HydraulicNodeBadge).  Called both by the
    live-preview loop and at project load."""
    from .pipe import Pipe
    from .sprinkler import Sprinkler
    from .fitting import Fitting
    from .water_supply import WaterSupply
    from .node import Node
    from .gridline import GridlineItem
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .wall import WallSegment
    from .room import Room

    if isinstance(item, Pipe):
        _apply_pipe(item, color, scale, opacity, visible, font_size)
    elif isinstance(item, WallSegment):
        item._display_color = color
        if fill_color is not None:
            mode, hex_col = _parse_fill_value(fill_color)
            item._display_fill_color = hex_col
            if mode == "hatch":
                item._fill_mode = "Section"
            else:
                item._fill_mode = "Solid"
        if section_type is not None:
            item._display_section_type = section_type
        item.setVisible(visible)
        item.setOpacity(opacity / 100.0)
        item.update()
    elif isinstance(item, Room):
        item._display_color = color
        if fill_color is not None:
            _, hex_col = _parse_fill_value(fill_color)
            item._display_fill_color = hex_col
        # SB3 Q4: the tag draws in the block's authored colours; the row's
        # colour / font never reach it (font retired).
        item.setVisible(visible)
        item.setOpacity(opacity / 100.0)
        item.update()
    elif isinstance(item, Sprinkler):
        _apply_svg_item(item, color, scale, opacity, visible, fill_color)
        item._display_scale = scale
        item._centre_on_node()
        # Invalidate parent Node geometry so shape()/boundingRect() reflect new scale
        if item.node is not None:
            item.node.prepareGeometryChange()
    elif isinstance(item, Fitting):
        _apply_fitting(item, color, scale, opacity, visible, fill_color)
    elif isinstance(item, WaterSupply):
        _apply_svg_item(item, color, scale, opacity, visible, fill_color)
        item._display_scale = scale
        item._centre_on_origin()
    elif isinstance(item, HydraulicNodeBadge):
        _apply_svg_item(item, color, scale, opacity, visible, fill_color)
        item._display_scale = scale
        item._centre_on_offset()
    elif isinstance(item, GridlineItem):
        _apply_gridline(item, color, scale, opacity, visible, fill_color, font_size)
    elif _is_elevation_marker(item):
        _apply_elevation_marker(item, color, scale, opacity, visible, fill_color, font_size)
    elif _is_detail_marker(item):
        _apply_detail_marker(item, color, scale, opacity, visible, fill_color, font_size)
    elif _is_opening_item(item):
        _apply_opening(item, color, opacity, visible)
    elif _is_geo2d_item(item):
        _apply_geo2d(item, color, opacity, visible, fill_color)
    elif isinstance(item, Node):
        _apply_node(item, color, scale, opacity, visible)
    else:
        # Generic items with _display_color/_display_fill_color (e.g. RoofItem, FloorSlab)
        if hasattr(item, '_display_color'):
            item._display_color = color
        if hasattr(item, '_display_fill_color') and fill_color is not None:
            _mode, _hex = _parse_fill_value(fill_color)
            item._display_fill_color = _hex
        if section_type is not None and hasattr(item, '_display_section_type'):
            item._display_section_type = section_type
        item.setVisible(visible)
        item.setOpacity(opacity / 100.0)
        item.update()


def _apply_pipe(pipe, color, scale, opacity, visible, font_size=None):
    pipe._display_color = color  # override pen colour (None falls back to property)
    pipe._display_scale = scale
    if font_size is not None:
        pipe._properties["Label Size"]["value"] = str(font_size)
    pipe.set_pipe_display()
    pipe.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    pipe.setVisible(visible)
    # Also hide/show the label child if present
    for child in pipe.childItems():
        child.setVisible(visible)
    if font_size is not None:
        pipe.update_label()


def _apply_svg_item(item, color, scale, opacity, visible, fill_color=None):
    """Apply colour tint + opacity to a QGraphicsSvgItem (Sprinkler, WaterSupply, Badge)."""
    _set_svg_tint(item, color, fill_color)
    item.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    item.setVisible(visible)


def _apply_fitting(fitting, color, scale, opacity, visible, fill_color=None):
    """Apply to a Fitting (non-QGraphicsItem wrapper)."""
    fitting._display_color = color
    fitting._display_fill_color = fill_color
    fitting._display_scale = scale
    fitting._display_opacity = opacity
    fitting._display_visible = visible
    sym = fitting.symbol
    if sym is None:
        return
    _set_svg_tint(sym, color, fill_color)
    sym.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    # Visibility: fittings are hidden when sprinkler is present (handled by
    # Fitting.update()), so only override when we explicitly hide.
    if not visible:
        sym.setVisible(False)
    # Re-apply scale + alignment only if the fitting has connected pipes —
    # otherwise align_fitting can misplace the symbol.
    if fitting.node and len(fitting.node.pipes) > 0:
        fitting.align_fitting()


def _is_geo2d_item(item) -> bool:
    """Check if item is one of the 8 draw-geometry classes (avoids circular imports)."""
    return type(item).__name__ in (
        "LineItem", "PolylineItem", "RectangleItem", "CircleItem", "ArcItem",
        "EllipseItem", "SplineItem", "RegularPolygonItem", "FilledRegionItem"
    )


def _is_opening_item(item) -> bool:
    """Check if item is a WallOpening (avoids circular imports)."""
    return type(item).__name__ == "WallOpening"


def _apply_geo2d(item, color, opacity, visible, fill_color=None):
    """Apply display settings to a 2D draw-geometry item (LineItem, PolylineItem, etc.).

    Stroke colour is stored in _display_color; the paint() methods read it and
    apply it to the pen before delegating to super().paint().  Fill paints
    from each shape's own ``fill_layers`` (UP1); a
    Graphic Override / instance ``fill`` (token, hex or ``""`` = No Fill) is
    read from ``_display_overrides["fill"]`` by ``Geometry2DMixin._fill_value``.
    The apply path never writes ``_display_fill_color`` on 2D geometry (it is
    display-only there; the shape's own fill lives in ``fill_layers``), so
    Clear restores the shape and a save keeps its fill.
    """
    item._display_color = color
    item.setVisible(visible)
    item.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    item.update()


def _apply_opening(item, color, opacity, visible):
    """Apply display settings to a WallOpening.

    Stroke colour is stored in _display_color; WallOpening._paint_symbol reads
    it and applies it to the pen used to draw the door/window symbol.
    """
    item._display_color = color
    item.setVisible(visible)
    item.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    item.update()


def _apply_node(node, color, scale, opacity, visible):
    node.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    node.setVisible(visible)


def _is_elevation_marker(item) -> bool:
    """Check if item is a SectionMarker without importing at module level."""
    return type(item).__name__ == "SectionMarker"


def _is_detail_marker(item) -> bool:
    """Check if item is a DetailMarker without importing at module level."""
    return type(item).__name__ == "DetailMarker"


def _is_floor_slab(item) -> bool:
    """Check if item is a FloorSlab without importing at module level."""
    return type(item).__name__ == "FloorSlab"


def _apply_elevation_marker(marker, color, scale, opacity, visible, fill_color,
                            font_size=None):
    """Apply display settings to a SectionMarker.

    The marker is a bare QGraphicsItem whose geometry is in scene units, so
    colour / fill land on its paint fields and the scale is only recorded
    (``setScale`` would move the cut line about the item origin).
    """
    if color:
        marker._marker_color = resolve_colour(color)
    if fill_color is not None:
        marker._fill_color = _fill_qcolor(fill_color)
    marker._display_scale = scale if scale else 1.0
    if font_size is not None:
        marker._display_font_size = font_size
        # Update the label text size if the marker has a label child
        label = getattr(marker, "_label", None)
        if label is not None:
            f = label.font()
            f.setPointSize(int(font_size))
            label.setFont(f)
    marker.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    marker.setVisible(visible)
    marker.update()


def _apply_detail_marker(marker, color, scale, opacity, visible, fill_color,
                         font_size=None):
    """Apply display settings to a DetailMarker."""
    if color:
        marker._tag_color = resolve_colour(color)
        pen = marker.pen()
        pen.setColor(resolve_colour(color))
        marker.setPen(pen)
    if fill_color is not None:
        marker._fill_color = _fill_qcolor(fill_color)
    if scale and scale != 1.0:
        marker.setScale(scale)
    elif scale == 1.0:
        marker.setScale(1.0)
    if font_size is not None:
        marker._display_font_size = font_size
    marker.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    marker.setVisible(visible)
    marker.update()


def _apply_gridline(gl, color, scale, opacity, visible, fill_color, font_size=None):
    """Apply display settings to a GridlineItem."""
    if color:
        gl._grid_color = resolve_colour(color)
        # Preserve the bubble's original pen width, just change color
        for bubble in (gl.bubble1, gl.bubble2):
            bp = bubble.pen()
            bp.setColor(resolve_colour(color))
            bubble.setPen(bp)
            bubble._label.setDefaultTextColor(resolve_colour(color).lighter(150))
    if fill_color is not None:
        gl.bubble1.setBrush(QBrush(_fill_qcolor(fill_color)))
        gl.bubble2.setBrush(QBrush(_fill_qcolor(fill_color)))
    # Scale the bubbles (child transforms around their position on the line)
    if scale and scale != 1.0:
        gl.bubble1.setScale(scale)
        gl.bubble2.setScale(scale)
    elif scale == 1.0:
        gl.bubble1.setScale(1.0)
        gl.bubble2.setScale(1.0)
    gl._display_scale = scale if scale else 1.0
    gl.setOpacity(opacity / 100.0 if opacity > 1 else opacity)
    gl.setVisible(visible)


# ──────────────────────────────────────────────────────────────────────────────
# Public helper — apply category defaults to a newly created item
# ──────────────────────────────────────────────────────────────────────────────

# Door / Window were split out of the single "Opening" row (2026-10-04). A
# store or project written before the split seeds them from "Opening".
_SPLIT_FROM_OPENING = ("Door", "Window")
_OPENING_SPLIT_MARK = "display/_opening_split_v1"


def _migrate_opening_split(settings: QSettings) -> None:
    """One-shot: copy ``display/Opening/*`` (current + ``default_*``) to the
    Door / Window keys that are absent. Idempotent via a store marker."""
    if settings.value(_OPENING_SPLIT_MARK):
        return
    settings.beginGroup("display/Opening")
    legacy = {p: settings.value(p) for p in settings.childKeys()}
    settings.endGroup()
    for key in _SPLIT_FROM_OPENING:
        for prop, val in legacy.items():
            k = f"display/{key}/{prop}"
            if not settings.contains(k):
                settings.setValue(k, val)
    settings.setValue(_OPENING_SPLIT_MARK, True)


# "Reference Lines" was renamed "Reference Geometry" (reference-geometry
# design RG13, 2026-10-13): a store or project written before seeds it.
_REFERENCE_RENAME_MARK = "display/_reference_geometry_v1"


def _migrate_reference_rename(settings: QSettings) -> None:
    """One-shot (RG13): copy ``display/Reference Lines/*`` (current +
    ``default_*``) to the absent ``display/Reference Geometry/*`` keys.
    Idempotent via a store marker."""
    if settings.value(_REFERENCE_RENAME_MARK):
        return
    settings.beginGroup("display/Reference Lines")
    legacy = {p: settings.value(p) for p in settings.childKeys()}
    settings.endGroup()
    for prop, val in legacy.items():
        k = f"display/Reference Geometry/{prop}"
        if not settings.contains(k):
            settings.setValue(k, val)
    settings.setValue(_REFERENCE_RENAME_MARK, True)


_HF1_AUTO_MARK = "display/_migrated_hf1_auto"


def _migrate_2d_geometry_auto(settings: QSettings) -> None:
    """One-shot (HF1, R7): a stored "2D Geometry" colour of #ffffff (current
    or user default) becomes Automatic. Idempotent via a store marker."""
    if settings.value(_HF1_AUTO_MARK):
        return
    for prop in ("color", "default_color"):
        k = f"display/2D Geometry/{prop}"
        if str(settings.value(k, "")).lower() == "#ffffff":
            settings.setValue(k, TOKEN_AUTO)
    settings.setValue(_HF1_AUTO_MARK, True)


def _migrate_display_keys(settings: QSettings) -> None:
    """Every one-shot display-key migration, in order."""
    _migrate_opening_split(settings)
    _migrate_reference_rename(settings)
    _migrate_2d_geometry_auto(settings)


def _project_entry(display_dict: dict, key: str) -> dict:
    """Project ``display_settings`` entry for *key*; a pre-split project has
    only "Opening", which seeds Door / Window; a pre-rename project's
    "Reference Lines" seeds "Reference Geometry" (RG13)."""
    if key in display_dict:
        return display_dict[key]
    if key in _SPLIT_FROM_OPENING:
        return display_dict.get("Opening", {})
    if key == "Reference Geometry":
        return display_dict.get("Reference Lines", {})
    return {}


def apply_category_defaults(item):
    """Read QSettings for the item's category and apply display settings.

    Call this whenever a new item is added to the scene so it inherits
    the user's current Display Manager preferences.
    """
    from .pipe import Pipe
    from .sprinkler import Sprinkler
    from .fitting import Fitting
    from .water_supply import WaterSupply
    from .node import Node
    from .gridline import GridlineItem
    from .hydraulic_node_badge import HydraulicNodeBadge
    from .wall import WallSegment
    from .room import Room
    from .design_area import DesignArea

    if isinstance(item, Pipe):
        key = "Pipe"
    elif isinstance(item, Sprinkler):
        key = "Sprinkler"
    elif isinstance(item, Fitting):
        key = "Fitting"
    elif isinstance(item, WaterSupply):
        key = "Water Supply"
    elif isinstance(item, HydraulicNodeBadge):
        key = "Hydraulic Badge"
    elif isinstance(item, GridlineItem):
        key = "Grid Line"
    elif isinstance(item, Node):
        key = "Node"
    elif isinstance(item, WallSegment):
        key = "Wall"
    elif _is_opening_item(item):
        key = item.display_category
    elif isinstance(item, Room):
        key = "Room"
    elif isinstance(item, DesignArea):
        key = "Design Area"
    elif _is_floor_slab(item):
        key = "Floor"
    elif _is_elevation_marker(item):
        key = "Elevation Marker"
    elif _is_detail_marker(item):
        key = "Detail Marker"
    else:
        return

    cat_def = next((c for c in _CATEGORIES if c["key"] == key), None)
    if cat_def is None:
        return

    settings = QSettings("GV", "FirePro3D")
    _migrate_display_keys(settings)

    # For SVG-based categories, only apply overrides when the user has
    # explicitly saved settings — otherwise the default colour tint would
    # mangle the SVG's natural appearance.  Non-SVG categories (walls,
    # roofs, rooms, floors) always apply so they match the display manager.
    _SVG_CATEGORIES = {"Sprinkler", "Fitting", "Water Supply",
                       "Hydraulic Badge", "Node"}
    if key in _SVG_CATEGORIES and not settings.contains(f"display/{key}/color"):
        return

    # Prefer default_* keys (from "Set as Default"), fall back to current,
    # then factory defaults.  This ensures newly created items match the
    # user's preferred display settings.
    def _v(prop, factory):
        return (settings.value(f"display/{key}/default_{prop}")
                or settings.value(f"display/{key}/{prop}")
                or factory)

    def _vc(prop, factory):
        """Like ``_v`` but a stored ``""`` (No Fill) is a value, not unset."""
        for k in (f"display/{key}/default_{prop}", f"display/{key}/{prop}"):
            raw = settings.value(k)
            if raw is not None:
                return raw
        return factory

    color = _vc("color", cat_def["color"])      # "" = No stroke is a value
    scale = float(_v("scale", cat_def["scale"]))
    opacity = int(float(_v("opacity", cat_def["opacity"])))
    visible = _v("visible", cat_def["visible"])
    if isinstance(visible, str):
        visible = visible.lower() not in ("false", "0")
    fill = _vc("fill", cat_def.get("fill"))
    font = cat_def.get("font")
    if font is not None:
        font = int(float(_v("font", font)))
    section_type = None
    if _category_has_section(key):
        section_scale_raw = _v("section_scale", None)
        section_type = fill_types.category_section_type(key, {
            "section_type": _vc("section_type", cat_def["section_type"]),
            "section_look": _parse_section_look(_vc("section_look", None)),
            "section": _vc("section", cat_def.get("section")),
            "section_pattern": _v("section_pattern", cat_def.get("section_pattern")),
            "section_scale": float(section_scale_raw) if section_scale_raw else None,
        })

    apply_display_to_item(item, color, scale, opacity, visible,
                          fill_color=fill, font_size=font,
                          section_type=section_type)


# ──────────────────────────────────────────────────────────────────────────────
# DisplayManager dialog
# ──────────────────────────────────────────────────────────────────────────────

class DisplayManager(QDialog):
    """Modal dialog providing Revit-style display settings for fire-
    suppression model items."""

    # The PROJECT line-weight table changed (linetypes.md LT1-3 / H3).
    # MainWindow dirties the project and re-pens weight-mapped canvases;
    # deliberately not ``sceneModified`` (that fans out to 3D/elevation).
    lineWeightsChanged = pyqtSignal()

    def __init__(self, scene, parent=None, active_context: str = "model"):
        super().__init__(parent)
        self.setWindowTitle("Display Manager")
        self.setMinimumSize(850, 420)
        self._scene = scene
        self._active_context = active_context
        self._settings = QSettings("GV", "FirePro3D")

        # Restore last window geometry (size + position)
        saved_size = self._settings.value("display_manager/window_size")
        if saved_size is not None:
            self.resize(saved_size)
        saved_pos = self._settings.value("display_manager/window_pos")
        if saved_pos is not None:
            self.move(saved_pos)
        self._suppress = False  # guard against recursive signal loops

        # {id(item): {visible, opacity, color, scale, effect}} — for revert
        self._snapshot: dict[int, dict] = {}
        # {category_key: {items: [item, ...], tree_item: QTreeWidgetItem,
        #                  widgets: {vis, color_btn, fill_btn, scale, opacity}}}
        self._cat_data: dict[str, dict] = {}
        # {id(item): {tree_item, widgets, item_ref}}
        self._inst_data: dict[int, dict] = {}

        self._take_snapshot()
        # Paper-space settings snapshot for cancel-revert
        from .paper_display import load_paper_categories, load_paper_color_mode
        self._paper_settings_snapshot = {
            "categories": load_paper_categories(self._settings),
            "color_mode": load_paper_color_mode(self._settings).value,
        }

        self._build_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._settings.setValue("display_manager/window_size", self.size())

    def moveEvent(self, event):
        super().moveEvent(event)
        self._settings.setValue("display_manager/window_pos", self.pos())

    # ------------------------------------------------------------------
    # Snapshot / revert
    # ------------------------------------------------------------------

    def _take_snapshot(self):
        """Capture the current visual state of every FS item for cancel-revert."""
        from .paper_display import model_blocks_weight
        self._model_blocks_snapshot = model_blocks_weight()
        for item in self._iter_all_items():
            entry: dict = {
                "visible": item.isVisible(),
                "opacity": item.opacity(),
                "display_color": getattr(item, "_display_color", None),
                "display_fill_color": getattr(item, "_display_fill_color", None),
                "display_scale": getattr(item, "_display_scale", 1.0),
                "overrides": dict(getattr(item, "_display_overrides", {})),
            }
            self._snapshot[id(item)] = entry

        # Cut items (walls, floors) are not in _iter_all_items: snapshot their
        # section-type state so a previewed pick never survives Cancel (HF5).
        self._section_snapshot = [
            (it, {a: getattr(it, a) for a in _CUT_ATTRS if hasattr(it, a)},
             dict(it._display_overrides), it.isVisible(), it.opacity())
            for it in self._scene.items()
            if hasattr(it, "_display_section_type")
            and isinstance(getattr(it, "_display_overrides", None), dict)]

        # Also snapshot Fitting wrappers (not QGraphicsItems themselves)
        for node in self._scene.sprinkler_system.nodes:
            f = node.fitting
            if f and f.symbol:
                fid = id(f)
                self._snapshot[fid] = {
                    "visible": f.symbol.isVisible(),
                    "opacity": f.symbol.opacity(),
                    "display_color": getattr(f, "_display_color", None),
                    "display_fill_color": getattr(f, "_display_fill_color", None),
                    "display_scale": getattr(f, "_display_scale", 1.0),
                    "display_opacity": getattr(f, "_display_opacity", 100),
                    "display_visible": getattr(f, "_display_visible", True),
                    "overrides": dict(getattr(f, "_display_overrides", {})),
                }

        # Snapshot gridline pen/brush colours
        from .gridline import GridlineItem
        for item in self._scene.items():
            if isinstance(item, GridlineItem):
                self._snapshot[id(item)] = {
                    "visible": item.isVisible(),
                    "opacity": item.opacity(),
                    "grid_color": item._grid_color.name(),
                    "bubble_pen": item.bubble1.pen().color().name(),
                    "bubble_brush": item.bubble1.brush().color().name(),
                    "label_color": item.bubble1._label.defaultTextColor().name(),
                    "bubble_font_px": item.bubble1._label.font().pixelSize(),
                    "bubble_scale": item.bubble1.scale(),
                    "overrides": dict(getattr(item, "_display_overrides", {})),
                }

        # Snapshot QSettings for elevation-only categories so cancel can revert
        self._elev_settings_snapshot: dict[str, dict] = {}
        for key in ("Grid Line", "Level Datum", "Elevation Marker", "Wall", "Roof", "Floor"):
            snap: dict = {}
            for prop in ("color", "fill", "section", "section_pattern", "section_scale", "scale", "opacity", "visible", "font"):
                v = self._settings.value(f"display/{key}/{prop}")
                if v is not None:
                    snap[prop] = v
            for prop in ("section_type", "section_look"):
                # None = absent: a Cancel removes what the live preview wrote.
                snap[prop] = self._settings.value(f"display/{key}/{prop}")
            self._elev_settings_snapshot[key] = snap

    def _restore_snapshot(self):
        """Revert every item to its snapshotted state."""
        from .fitting import Fitting
        from .pipe import Pipe
        from .sprinkler import Sprinkler
        from .water_supply import WaterSupply
        from .gridline import GridlineItem
        from .hydraulic_node_badge import HydraulicNodeBadge

        for item in self._iter_all_items():
            snap = self._snapshot.get(id(item))
            if snap is None:
                continue

            # Handle gridlines separately
            if isinstance(item, GridlineItem):
                item.setVisible(snap["visible"])
                item.setOpacity(snap["opacity"])
                item._grid_color = QColor(snap["grid_color"])
                for bubble in (item.bubble1, item.bubble2):
                    bp = bubble.pen()
                    bp.setColor(QColor(snap["bubble_pen"]))
                    bubble.setPen(bp)
                item.bubble1.setBrush(QBrush(QColor(snap["bubble_brush"])))
                item.bubble2.setBrush(QBrush(QColor(snap["bubble_brush"])))
                item.bubble1._label.setDefaultTextColor(QColor(snap["label_color"]))
                item.bubble2._label.setDefaultTextColor(QColor(snap["label_color"]))
                if "bubble_font_px" in snap and snap["bubble_font_px"] > 0:
                    for bubble in (item.bubble1, item.bubble2):
                        f = bubble._label.font()
                        f.setPixelSize(snap["bubble_font_px"])
                        bubble._label.setFont(f)
                        bubble._center_label()
                if "bubble_scale" in snap:
                    item.bubble1.setScale(snap["bubble_scale"])
                    item.bubble2.setScale(snap["bubble_scale"])
                item._display_overrides = snap.get("overrides", {})
                continue

            item.setVisible(snap["visible"])
            item.setOpacity(snap["opacity"])
            item._display_overrides = snap.get("overrides", {})
            # Restore per-type display attributes
            if isinstance(item, Pipe):
                item._display_color = snap.get("display_color")
                item._display_scale = snap.get("display_scale", 1.0)
                item.set_pipe_display()
            elif isinstance(item, (Sprinkler, WaterSupply)):
                _set_svg_tint(item, snap.get("display_color"),
                              snap.get("display_fill_color"))
                item._display_scale = snap.get("display_scale", 1.0)
                if isinstance(item, Sprinkler):
                    item._centre_on_node()
                else:
                    item._centre_on_origin()
            elif isinstance(item, HydraulicNodeBadge):
                _set_svg_tint(item, snap.get("display_color"),
                              snap.get("display_fill_color"))
                item._display_scale = snap.get("display_scale", 1.0)
                item._centre_on_offset()

        for it, attrs, overrides, vis, opa in getattr(self, "_section_snapshot", ()):
            for a, v in attrs.items():
                setattr(it, a, v)
            it._display_overrides = dict(overrides)
            it.setVisible(vis)
            it.setOpacity(opa)
            it.update()

        # Restore fittings
        for node in self._scene.sprinkler_system.nodes:
            f = node.fitting
            if f is None:
                continue
            snap = self._snapshot.get(id(f))
            if snap is None:
                continue
            f._display_color = snap.get("display_color")
            f._display_fill_color = snap.get("display_fill_color")
            f._display_scale = snap.get("display_scale", 1.0)
            f._display_opacity = snap.get("display_opacity", 100)
            f._display_visible = snap.get("display_visible", True)
            f._display_overrides = snap.get("overrides", {})
            if f.symbol:
                f.symbol.setVisible(snap["visible"])
                f.symbol.setOpacity(snap["opacity"])
                _set_svg_tint(f.symbol, snap.get("display_color"),
                              snap.get("display_fill_color"))
                f.align_fitting()

        # Model "Blocks" weight (LT2-6)
        if hasattr(self, "_model_blocks_snapshot"):
            from .paper_display import model_blocks_weight, set_model_blocks_weight
            if model_blocks_weight() != self._model_blocks_snapshot:
                # Raw: runs before reject() restores the table + aliases.
                set_model_blocks_weight(self._model_blocks_snapshot,
                                        canonical=False)
                self._settings.setValue(
                    f"display/{_MODEL_BLOCKS_KEY}/line_weight",
                    self._model_blocks_snapshot)
                self.lineWeightsChanged.emit()

        # Force scene repaint
        self._scene.update()

        # Restore QSettings for elevation-only categories and rebuild
        if hasattr(self, "_elev_settings_snapshot"):
            for key, snap in self._elev_settings_snapshot.items():
                for prop, val in snap.items():
                    if val is None:
                        self._settings.remove(f"display/{key}/{prop}")
                    else:
                        self._settings.setValue(f"display/{key}/{prop}", val)
            self._settings.sync()
            elev_mgr = getattr(self._scene, "_section_manager", None)
            if elev_mgr is not None and hasattr(elev_mgr, "rebuild_all"):
                elev_mgr.rebuild_all()

    # ------------------------------------------------------------------
    # Item iteration helpers
    # ------------------------------------------------------------------

    def _iter_all_items(self):
        """Yield every fire-suppression QGraphicsItem in the scene."""
        from .gridline import GridlineItem
        from .hydraulic_node_badge import HydraulicNodeBadge
        ss = self._scene.sprinkler_system
        yield from ss.pipes
        for node in ss.nodes:
            yield node
            if node.has_sprinkler():
                yield node.sprinkler
        ws = getattr(self._scene, "water_supply_node", None)
        if ws is not None:
            yield ws
        for item in self._scene.items():
            if isinstance(item, (GridlineItem, HydraulicNodeBadge)):
                yield item

    def _items_for_category(self, key: str) -> list:
        """Return the list of items (or Fitting wrappers) for a category."""
        return _items_for_category_static(self._scene, key)

    def _label_for_item(self, item, index: int, category: str) -> str:
        """Human-readable label for an instance row."""
        if category == "Pipe":
            dia = item._properties.get("Diameter", {}).get("value", "?")
            return f"Pipe {index}  ({dia})"
        elif category == "Sprinkler":
            mfr = item._properties.get("Manufacturer", {}).get("value", "")
            ori = item._properties.get("Orientation", {}).get("value", "")
            return f"Sprinkler {index}  ({mfr} {ori})"
        elif category == "Fitting":
            return f"Fitting {index}  ({item.type})"
        elif category == "Water Supply":
            return "Water Supply"
        elif category == "Node":
            n_pipes = len(item.pipes)
            return f"Node {index}  ({n_pipes} conn.)"
        elif category == "Grid Line":
            lbl = getattr(item, "_label_text", "?")
            return f"Grid Line {index}  ({lbl})"
        elif category == "Wall":
            name = getattr(item, "name", "")
            return f"Wall {index}  ({name})" if name else f"Wall {index}"
        elif category == "Room":
            name = getattr(item, "name", "")
            return f"Room {index}  ({name})" if name else f"Room {index}"
        elif category == "Design Area":
            name = item._properties.get("System Name", {}).get("value", "")
            return f"Design Area {index}  ({name})" if name else f"Design Area {index}"
        return f"{category} {index}"

    # ------------------------------------------------------------------
    # Read current display state from a live scene item
    # ------------------------------------------------------------------

    def _read_item_display_state(self, item, category_key: str) -> dict:
        """Read the *current* display properties directly from a scene item.

        Returns a dict with keys: color, fill, section_type, scale, opacity,
        visible, font.
        This ensures the dialog always reflects what is actually on screen.
        """
        from .gridline import GridlineItem
        from .pipe import Pipe
        from .fitting import Fitting
        from .sprinkler import Sprinkler
        from .water_supply import WaterSupply
        from .hydraulic_node_badge import HydraulicNodeBadge
        from .wall import WallSegment

        cat_def = next(c for c in _CATEGORIES if c["key"] == category_key)

        # --- visibility & opacity ---
        if isinstance(item, Fitting):
            sym = item.symbol
            vis = sym.isVisible() if sym else True
            raw_opa = sym.opacity() if sym else 1.0
        elif hasattr(item, "isVisible"):
            vis = item.isVisible()
            raw_opa = item.opacity()
        else:
            vis = True
            raw_opa = 1.0

        opa = int(round(raw_opa * 100))

        # --- scale ---
        scale = float(getattr(item, "_display_scale", cat_def["scale"]))

        # --- color, fill, font (type-specific) ---
        if isinstance(item, GridlineItem):
            color = item._grid_color.name()
            fill = item.bubble1.brush().color().name()
            font = None
        elif isinstance(item, Pipe):
            color = _fill_or(getattr(item, "_display_color", None),
                             item.pen().color().name())
            fill = None
            font_val = item._properties.get(
                "Label Size", {}).get("value", 12)
            try:
                font = int(font_val)
            except (ValueError, TypeError):
                font = 12
        elif isinstance(item, Fitting):
            color = _fill_or(getattr(item, "_display_color", None),
                             cat_def["color"])
            fill = _fill_or(getattr(item, "_display_fill_color", None),
                            cat_def.get("fill"))
            font = None
        elif isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
            color = _fill_or(getattr(item, "_display_color", None),
                             cat_def["color"])
            fill = _fill_or(getattr(item, "_display_fill_color", None),
                            cat_def.get("fill"))
            font = None
        elif isinstance(item, WallSegment):
            color = _fill_or(getattr(item, "_display_color", None),
                             item._colour)
            fill = _fill_or(getattr(item, "_display_fill_color", None),
                            cat_def.get("fill"))
            font = None
        elif _is_elevation_marker(item):
            color = (getattr(item, "_marker_color", cat_def["color"])
                     if not isinstance(getattr(item, "_marker_color", None), QColor)
                     else item._marker_color.name())
            fill_c = getattr(item, "_fill_color", None)
            fill = fill_c.name() if isinstance(fill_c, QColor) else cat_def.get("fill")
            font = getattr(item, "_display_font_size", cat_def.get("font"))
        else:
            # Generic items (FloorSlab, RoofItem, Room, Node, etc.)
            color = _fill_or(
                getattr(item, "_display_color", None),
                _fill_or(getattr(item, "_colour", None),    # roof: str store
                         getattr(item, "_color", cat_def["color"])))
            if isinstance(color, QColor):
                color = color.name()
            fill = _fill_or(getattr(item, "_display_fill_color", None),
                            cat_def.get("fill"))
            font = cat_def.get("font")

        return {
            "color": color,
            "fill": fill,
            # The cut's Fill Type id (None = not applied yet: the category's).
            "section_type": getattr(item, "_display_section_type", None),
            "scale": scale,
            "opacity": opa,
            "visible": vis,
            "font": font,
        }

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        _t = th.detect()
        outer = QVBoxLayout(self)

        # ── Tree widget ──────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setColumnCount(10)
        self._tree.setHeaderLabels(
            ["Name", "Vis", "Colour", "Fill", "Section", "Scale", "Opacity",
             "Font", "Line Weight", ""])
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(20)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hdr = self._tree.header()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_VIS, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_COLOR, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_FILL, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_SECTION, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_SCALE, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_OPACITY, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_FONT, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_LW, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_RESET, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(_COL_VIS, 40)
        self._tree.setColumnWidth(_COL_COLOR, 60)
        self._tree.setColumnWidth(_COL_FILL, 60)
        self._tree.setColumnWidth(_COL_SECTION, 130)
        self._tree.setColumnWidth(_COL_SCALE, 90)
        self._tree.setColumnWidth(_COL_OPACITY, 90)
        self._tree.setColumnWidth(_COL_FONT, 70)
        self._tree.setColumnWidth(_COL_LW, 100)
        self._tree.setColumnWidth(_COL_RESET, 40)

        # Suppress preview signals during init so scene isn't changed.
        # Snapshot was already taken in __init__ before _build_ui().
        self._suppress = True
        self._populate_tree()
        self._add_model_blocks_row()
        # Expand all group headers; collapse every category (child) node
        for i in range(self._tree.topLevelItemCount()):
            grp = self._tree.topLevelItem(i)
            grp.setExpanded(True)
            for j in range(grp.childCount()):
                grp.child(j).setExpanded(False)
        self._suppress = False
        # ── Tab widget ──────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(self._tree, "Model")
        self._paper_tab = self._build_paper_space_tab()
        self._tabs.insertTab(1, self._paper_tab, "Paper Space")
        self._lw_tab = self._build_line_weights_tab()
        self._tabs.addTab(self._lw_tab, "Line Weights")
        # HF5 R5: the Fill Types tab edits a working copy; OK installs it.
        from .fill_types_tab import FillTypesTab
        # Cancel puts the live table back if the tab was edited (a pending type
        # picked in a section cell is previewed into it). Taken after the tree
        # build, which converts legacy section cells into types.
        self._ft_table_snapshot = fill_types.project_table().copy()
        self._ft_tab = FillTypesTab(self._scene, parent=self)
        self._ft_tab.edited.connect(self._refresh_section_selectors)
        self._tabs.addTab(self._ft_tab, "Fill Types")
        fill_types.fill_type_bus().changed.connect(self._on_fill_type_bus)

        if self._active_context == "paper":
            self._tabs.setCurrentIndex(1)  # Paper Space tab

        outer.addWidget(self._tabs)

        # ── Button box ───────────────────────────────────────────────
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        reset_btn = bbox.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        reset_btn.setText("Reset All")
        reset_btn.clicked.connect(self._reset_all)

        # ── Set as Default button ────────────────────────────────────
        default_btn = QPushButton("Set as Default")
        default_btn.setToolTip(
            "Save current settings as defaults for new projects")
        default_btn.clicked.connect(self._set_as_default)
        bbox.addButton(default_btn, QDialogButtonBox.ButtonRole.ActionRole)
        self._reset_btn, self._default_btn = reset_btn, default_btn
        self._reset_tip, self._default_tip = reset_btn.toolTip(), default_btn.toolTip()
        self._tabs.currentChanged.connect(self._sync_tab_buttons)
        self._sync_tab_buttons()

        outer.addWidget(bbox)

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def _populate_tree(self):
        _t = th.detect()
        bold = QFont()
        bold.setBold(True)
        group_font = QFont()
        group_font.setBold(True)
        group_font.setPointSize(group_font.pointSize() + 1)

        # Create group header items
        group_items: dict[str, QTreeWidgetItem] = {}
        for grp_name in _GROUPS:
            grp_item = QTreeWidgetItem(self._tree)
            grp_item.setText(_COL_NAME, grp_name)
            grp_item.setFont(_COL_NAME, group_font)
            grp_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            grp_item.setExpanded(True)
            # Style the group header
            grp_item.setForeground(_COL_NAME, QColor(_t.text_primary))
            group_items[grp_name] = grp_item

        for cat_def in _CATEGORIES:
            key = cat_def["key"]
            items = self._items_for_category(key)

            # Read display values from the FIRST scene item so the dialog
            # always reflects the actual current scene state.  Fall back to
            # QSettings / factory defaults only when no items exist.
            if items:
                _first = self._read_item_display_state(items[0], key)
                saved_color   = _first["color"]
                saved_fill    = _first["fill"]
                saved_scale   = _first["scale"]
                saved_opacity = _first["opacity"]
                saved_visible = _first["visible"]
                saved_font    = _first["font"]
                saved_section_type = _first.get("section_type")
            else:
                saved_color = self._settings.value(
                    f"display/{key}/color", cat_def["color"])
                saved_fill = self._settings.value(
                    f"display/{key}/fill", cat_def.get("fill"))
                saved_scale = float(self._settings.value(
                    f"display/{key}/scale", cat_def["scale"]))
                saved_opacity = int(float(self._settings.value(
                    f"display/{key}/opacity", cat_def["opacity"])))
                saved_visible = self._settings.value(
                    f"display/{key}/visible", cat_def["visible"])
                if isinstance(saved_visible, str):
                    saved_visible = saved_visible.lower() not in ("false", "0")
                saved_font = cat_def.get("font")
                if saved_font is not None:
                    saved_font = int(float(self._settings.value(
                        f"display/{key}/font", saved_font)))
                saved_section_type = None
            if _category_has_section(key):
                cat_tid = fill_types.category_section_type(
                    key, _read_category_from_settings(key, self._settings))
                saved_section_type = saved_section_type or cat_tid
            else:
                cat_tid = None

            # ── Category row (child of its group) ─────────────────────
            grp_name = cat_def.get("group", "Other")
            parent_item = group_items.get(grp_name, self._tree)
            cat_item = QTreeWidgetItem(parent_item)
            # For Level Datum, show the number of levels even though
            # they aren't scene items in the plan view.
            if key == "Level Datum":
                lm = getattr(self._scene, "_level_manager", None)
                count = len(lm.levels) if lm else 0
            else:
                count = len(items)
            cat_item.setText(_COL_NAME, f"{category_label(key)}  ({count})")
            cat_item.setFont(_COL_NAME, bold)
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            cat_widgets = self._make_row_widgets(
                cat_item, saved_visible, saved_color, saved_fill,
                saved_scale, saved_opacity, saved_font,
                is_category=True, category_key=key,
                section_type=saved_section_type)

            self._cat_data[key] = {
                "items": items,
                "tree_item": cat_item,
                "widgets": cat_widgets,
            }

            # ── Instance sub-rows ────────────────────────────────────
            for i, obj in enumerate(items, 1):
                # Read each instance's actual scene state
                _ist = self._read_item_display_state(obj, key)
                inst_color   = _ist["color"]
                inst_fill    = _ist["fill"]
                inst_scale   = _ist["scale"]
                inst_opacity = _ist["opacity"]
                inst_visible = _ist["visible"]
                inst_font    = _ist["font"]
                inst_section_type = _ist.get("section_type") or cat_tid

                child = QTreeWidgetItem(cat_item)
                child.setText(_COL_NAME, self._label_for_item(obj, i, key))
                child.setFlags(Qt.ItemFlag.ItemIsEnabled)

                inst_widgets = self._make_row_widgets(
                    child, inst_visible, inst_color, inst_fill,
                    inst_scale, inst_opacity, inst_font,
                    is_category=False, category_key=key,
                    item_ref=obj,
                    section_type=inst_section_type)

                self._inst_data[id(obj)] = {
                    "tree_item": child,
                    "widgets": inst_widgets,
                    "item_ref": obj,
                    "category": key,
                }

        # A later category may have added its section type to the table: every
        # selector lists the final set.
        self._refresh_section_selectors()

    def _add_model_blocks_row(self):
        """Weight-only "Blocks" row (linetypes.md LT2-6): the canvas weight of
        block linework whose weight is By Linetype on a Continuous line
        (linetypes.md WM-5 fallback). Not a _CATEGORIES entry -- block colours,
        visibility and opacity stay authored / per instance."""
        from .paper_display import (model_blocks_weight, picker_weight_name,
                                    weight_names)
        parent = None
        for i in range(self._tree.topLevelItemCount()):
            grp = self._tree.topLevelItem(i)
            if grp.text(_COL_NAME) == "Annotation & Geometry":
                parent = grp
        row = QTreeWidgetItem(parent or self._tree)
        row.setText(_COL_NAME, _MODEL_BLOCKS_KEY)
        f = QFont()
        f.setBold(True)
        row.setFont(_COL_NAME, f)
        row.setFlags(Qt.ItemFlag.ItemIsEnabled)
        row.setToolTip(_COL_NAME, "Blocks: line weight only (block colours, "
                                  "visibility and opacity stay authored)")
        combo = QComboBox()
        combo.addItems(weight_names())
        combo.setCurrentText(picker_weight_name(model_blocks_weight()))  # MW-6: the row it draws as
        combo.setToolTip("Canvas line weight of block linework whose weight is "
                         "By Linetype on a Continuous line (Thin Lines still "
                         "applies)")
        combo.currentTextChanged.connect(self._on_model_blocks_weight)
        self._tree.setItemWidget(row, _COL_LW, combo)
        self._model_blocks_combo = combo

    def _on_model_blocks_weight(self, name: str):
        if self._suppress or not name:
            return
        from .paper_display import set_model_blocks_weight
        set_model_blocks_weight(name)
        self._settings.setValue(f"display/{_MODEL_BLOCKS_KEY}/line_weight", name)
        self.lineWeightsChanged.emit()         # dirty + repaint (LT1 H3)

    def _refresh_model_blocks_combo(self):
        """Re-fill the Blocks combo from the project table (rename / add /
        remove / reset) without firing ``_on_model_blocks_weight``."""
        combo = getattr(self, "_model_blocks_combo", None)
        if combo is None:
            return
        from .paper_display import (model_blocks_weight, picker_weight_name,
                                    weight_names)
        was = self._suppress
        self._suppress = True
        try:
            combo.clear()
            combo.addItems(weight_names())
            combo.setCurrentText(picker_weight_name(model_blocks_weight()))  # MW-6: the row it draws as
        finally:
            self._suppress = was

    def _make_row_widgets(self, tree_item: QTreeWidgetItem,
                          visible: bool, color: str,
                          fill: str | None,
                          scale: float, opacity: int,
                          font: int | None = None, *,
                          is_category: bool,
                          category_key: str,
                          item_ref=None,
                          section_type: str | None = None) -> dict:
        """Create and embed widgets for one tree row. Returns widget dict."""
        _t = th.detect()
        has_fill = _category_has_fill(category_key)
        has_section = _category_has_section(category_key)
        has_scale = _category_has_scale(category_key)
        has_font = _category_has_font(category_key)
        _disabled_ss = (f"background: {_t.bg_sunken}; color: {_t.text_disabled}; "
                        f"border: 1px solid {_t.border_subtle}; border-radius: 2px;")

        # ── Visibility checkbox ──────────────────────────────────────
        vis_container = QWidget()
        vis_layout = QHBoxLayout(vis_container)
        vis_layout.setContentsMargins(0, 0, 0, 0)
        vis_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vis_cb = QCheckBox()
        vis_cb.setChecked(visible)
        vis_layout.addWidget(vis_cb)
        self._tree.setItemWidget(tree_item, _COL_VIS, vis_container)

        # ── Colour swatch ────────────────────────────────────────────
        color_btn = QPushButton()
        color_btn.setFixedSize(40, 20)
        color_btn.setProperty("_color", color)
        _apply_swatch_look(color_btn, color, _t)
        self._tree.setItemWidget(tree_item, _COL_COLOR, color_btn)

        # ── Fill colour swatch (solid only — no hatch option) ────────
        fill_btn = QPushButton()
        fill_btn.setFixedSize(40, 20)
        if has_fill and fill is not None:
            # Strip any legacy "hatch:" prefix — fill is now solid-only
            _, hex_col = _parse_fill_value(fill)
            fill_btn.setProperty("_color", hex_col)
            _apply_swatch_look(fill_btn, hex_col, _t)
        else:
            fill_btn.setProperty("_color", "")
            fill_btn.setStyleSheet(_disabled_ss)
            fill_btn.setEnabled(False)
        self._tree.setItemWidget(tree_item, _COL_FILL, fill_btn)

        # ── Section cell: a Fill Type selector (HF5; Wall / Floor only) ──
        section_sel = None
        if has_section:
            section_sel = Selector()
            section_sel.setShowIcon(True)           # swatch + name (user ruling 2026-10-23)
            section_sel.setIconSize(QSize(40, 20))
            # Filled by the build's final _refresh_section_selectors (one icon
            # set for every row; a later category may still add a type).
            section_sel.setProperty("_section_tid", section_type)
            self._tree.setItemWidget(tree_item, _COL_SECTION, section_sel)

        # ── Scale spinbox ────────────────────────────────────────────
        scale_spin = QDoubleSpinBox()
        scale_spin.setRange(0.1, 10.0)
        scale_spin.setSingleStep(0.1)
        scale_spin.setDecimals(1)
        scale_spin.setValue(scale)
        scale_spin.setSuffix("x")
        scale_spin.setFixedHeight(22)
        if not has_scale:
            scale_spin.setEnabled(False)
            scale_spin.setStyleSheet(_disabled_ss)
        self._tree.setItemWidget(tree_item, _COL_SCALE, scale_spin)

        # ── Opacity spinbox ──────────────────────────────────────────
        opacity_spin = QSpinBox()
        opacity_spin.setRange(0, 100)
        opacity_spin.setSingleStep(5)
        opacity_spin.setValue(opacity)
        opacity_spin.setSuffix("%")
        opacity_spin.setFixedHeight(22)
        self._tree.setItemWidget(tree_item, _COL_OPACITY, opacity_spin)

        # ── Font size spinbox ────────────────────────────────────────
        font_spin = QSpinBox()
        font_spin.setRange(4, 48)
        font_spin.setSingleStep(1)
        font_spin.setFixedHeight(22)
        if has_font and font is not None:
            font_spin.setValue(int(font))
            font_spin.setSuffix("pt" if category_key in ("Grid Line", "Level Datum", "Elevation Marker") else "in")
        else:
            font_spin.setValue(10)
            font_spin.setEnabled(False)
            font_spin.setStyleSheet(_disabled_ss)
        self._tree.setItemWidget(tree_item, _COL_FONT, font_spin)

        # ── Reset button (instance rows only) ────────────────────────
        reset_btn = None
        if not is_category:
            reset_btn = QPushButton("\u21ba")  # ↺
            reset_btn.setFixedSize(28, 22)
            reset_btn.setToolTip("Reset to category defaults")
            self._tree.setItemWidget(tree_item, _COL_RESET, reset_btn)

        # ── Connect signals ──────────────────────────────────────────
        if is_category:
            vis_cb.toggled.connect(
                lambda v, k=category_key: self._on_category_changed(k, "visible", v))
            color_btn.clicked.connect(
                lambda _, k=category_key: self._pick_category_prop(k, "color"))
            if has_fill:
                fill_btn.clicked.connect(
                    lambda _, k=category_key: self._pick_category_prop(k, "fill"))
            if has_section:
                section_sel.currentTextChanged.connect(
                    lambda name, k=category_key: self._on_category_changed(
                        k, "section_type", name))
            scale_spin.valueChanged.connect(
                lambda v, k=category_key: self._on_category_changed(k, "scale", v))
            opacity_spin.valueChanged.connect(
                lambda v, k=category_key: self._on_category_changed(k, "opacity", v))
            if has_font:
                font_spin.valueChanged.connect(
                    lambda v, k=category_key: self._on_category_changed(k, "font", v))
        else:
            vis_cb.toggled.connect(
                lambda v, ref=item_ref: self._on_instance_changed(ref, "visible", v))
            color_btn.clicked.connect(
                lambda _, ref=item_ref: self._pick_instance_prop(ref, "color"))
            if has_fill:
                fill_btn.clicked.connect(
                    lambda _, ref=item_ref: self._pick_instance_prop(ref, "fill"))
            if has_section:
                section_sel.currentTextChanged.connect(
                    lambda name, ref=item_ref: self._on_instance_section_picked(ref, name))
            scale_spin.valueChanged.connect(
                lambda v, ref=item_ref: self._on_instance_changed(ref, "scale", v))
            opacity_spin.valueChanged.connect(
                lambda v, ref=item_ref: self._on_instance_changed(ref, "opacity", v))
            if has_font:
                font_spin.valueChanged.connect(
                    lambda v, ref=item_ref: self._on_instance_changed(ref, "font", v))
            if reset_btn:
                reset_btn.clicked.connect(
                    lambda _, ref=item_ref: self._reset_instance(ref))

        return {
            "vis": vis_cb,
            "color_btn": color_btn,
            "fill_btn": fill_btn,
            "section_sel": section_sel,
            "scale": scale_spin,
            "opacity": opacity_spin,
            "font": font_spin,
            "reset": reset_btn,
        }

    # ------------------------------------------------------------------
    # Colour pickers
    # ------------------------------------------------------------------

    # ── Generic colour picker (replaces 6 specific pick methods) ────────

    def _pick_category_prop(self, category_key: str, prop: str):
        """Open a colour dialog for *prop* ('color' or 'fill') on the category
        row and propagate to instances."""
        btn_key = {"color": "color_btn", "fill": "fill_btn"}[prop]
        default = {"color": "#ffffff", "fill": "#000000"}[prop]
        widgets = self._cat_data[category_key]["widgets"]
        cur_hex = widgets[btn_key].property("_color")
        if cur_hex is None:
            cur_hex = default
        v = colour_picker.pick_colour(cur_hex, self, f"{category_label(category_key)} · {prop}")
        if v is not None:
            self._update_swatch(widgets[btn_key], prop, v)
            self._on_category_changed(category_key, prop, v)

    def _pick_instance_prop(self, item_ref, prop: str):
        """Open a colour dialog for *prop* on an instance row."""
        data = self._inst_data.get(id(item_ref))
        if data is None:
            return
        btn_key = {"color": "color_btn", "fill": "fill_btn"}[prop]
        default = {"color": "#ffffff", "fill": "#000000"}[prop]
        widgets = data["widgets"]
        cur_hex = widgets[btn_key].property("_color")
        if cur_hex is None:
            cur_hex = default
        v = colour_picker.pick_colour(cur_hex, self, f"Instance · {prop}")
        if v is not None:
            self._update_swatch(widgets[btn_key], prop, v)
            self._on_instance_changed(item_ref, prop, v)

    # ── Swatch update (replaces 3 specific update methods) ────────────

    def _update_swatch(self, btn: QPushButton, prop: str, hex_color: str):
        """Update a swatch button for 'color' or 'fill'."""
        _t = th.detect()
        # color and fill are both solid swatches
        _, hex_col = _parse_fill_value(hex_color)
        btn.setProperty("_color", hex_col)
        btn.setIcon(QIcon())
        _apply_swatch_look(btn, hex_col, _t)

    # ── Section cell: Fill Type selector (HF5) ─────────────────────────

    def _type_icons(self, table) -> dict:
        """One ``{type id: QIcon}`` for *table* -- built once per refresh and
        shared by every section selector (HF5 VC9 I1: the swatch render is the
        cost, never rebuilt per row). Swatches are memoised by look, so a tab
        edit re-renders only the edited type; the table bus clears the memo
        (a retarget can change a pattern block behind an unchanged look). The
        memo assumes the pattern blocks, pattern files and theme stay put while
        the (modal) dialog is open; looks no longer in *table* are dropped."""
        reg = self._scene.block_registry
        memo = self.__dict__.setdefault("_icon_memo", {})
        out = {}
        for t in table.all():
            icon = memo.get(t.layers)
            if icon is None:
                icon = memo[t.layers] = _fill_type_icon(t.layers, reg)
            out[t.id] = icon
        live = {t.layers for t in table.all()}
        for look in [k for k in memo if k not in live]:
            del memo[look]
        return out

    def _fill_section_selector(self, sel: Selector, type_id, icons=None) -> None:
        """(Re)fill *sel* with the project's Fill Types (name + look swatch) and
        select *type_id*; an id the table lacks gets a "? <id8>" entry so the
        row shows it (never silently another type). No signals fire. *icons* is
        a ``_type_icons`` map shared across selectors (built here when None)."""
        table = self._section_table()
        if icons is None:
            icons = self._type_icons(table)
        types = table.all()
        cur = table.get(type_id) if type_id else None
        missing = type_id if cur is None and type_id else None
        listed = (tuple((t.id, t.name) for t in types), missing)
        sel.blockSignals(True)
        try:
            if getattr(sel, "_ft_listed", None) == listed:
                # Same entries (a restyle): swap only the changed swatches.
                for i, t in enumerate(types):
                    if sel.itemIcon(i).cacheKey() != icons[t.id].cacheKey():
                        sel.setItemIcon(i, icons[t.id])
            else:
                sel.clear()
                for t in types:
                    sel.addItem(icons[t.id], t.name, t.id)
                if missing:
                    sel.addItem(fill_types.missing_type_label(missing), missing)
                sel._ft_listed = listed
            if cur is not None:
                sel.setCurrentIndex(sel.findData(cur.id))
            elif missing:
                sel.setCurrentIndex(sel.count() - 1)
        finally:
            sel.blockSignals(False)

    def _section_table(self):
        """The table the section selectors list: the Fill Types tab's working
        copy once it is edited (so a type added / renamed there is pickable
        before OK), else the project's."""
        tab = getattr(self, "_ft_tab", None)
        return tab.table() if tab is not None and tab.dirty else fill_types.project_table()

    def _on_fill_type_bus(self) -> None:
        """The project table changed (OK, a restyle, a retarget): re-list the
        section selectors. Selector refills block their signals, so this never
        re-applies a preview."""
        from PyQt6 import sip
        if not sip.isdeleted(self):
            self.__dict__.pop("_icon_memo", None)
            self._refresh_section_selectors()

    def done(self, result):
        """Stop listening to the table bus once the dialog closes."""
        try:
            fill_types.fill_type_bus().changed.disconnect(self._on_fill_type_bus)
        except (TypeError, RuntimeError):
            pass
        super().done(result)

    def _refresh_section_selectors(self) -> None:
        """Re-list the Fill Types in every section selector (the table changed:
        add / rename / restyle / delete), keeping each row's selection by id."""
        icons = self._type_icons(self._section_table())
        for data in (*self._cat_data.values(), *self._inst_data.values()):
            sel = data["widgets"].get("section_sel")
            if sel is not None:
                tid = sel.currentData() if sel.count() else sel.property("_section_tid")
                self._fill_section_selector(sel, tid, icons)

    def _on_instance_section_picked(self, item_ref, name: str) -> None:
        """An instance row picked a Fill Type by name: store its id as the
        item's override (R7: per-item overrides store the id)."""
        t = self._section_table().by_name(name)
        if t is not None:
            live = fill_types.project_table()
            if live.get(t.id) is None and live.by_name(t.name) is None:
                live.add(t)             # a pending type: same id, so OK keeps the override
                fill_types.notify_changed()
            self._on_instance_changed(item_ref, "section_type", t.id)

    # Legacy aliases so existing internal calls still work
    _update_color_btn = lambda self, btn, v: self._update_swatch(btn, "color", v)
    _update_fill_btn  = lambda self, btn, v: self._update_swatch(btn, "fill", v)

    # ------------------------------------------------------------------
    # Change handlers
    # ------------------------------------------------------------------

    def _on_category_changed(self, category_key: str, prop: str, value):
        """Category-level setting changed — propagate to all instances
        that don't have a per-instance override for this property."""
        if self._suppress:
            return
        self._suppress = True
        try:
            cat = self._cat_data[category_key]
            for obj in cat["items"]:
                overrides = getattr(obj, "_display_overrides", {})
                if prop not in overrides:
                    # Update the instance row widget to match
                    inst = self._inst_data.get(id(obj))
                    if inst:
                        self._set_widget_value(inst["widgets"], prop, value)
            self._apply_preview()
        finally:
            self._suppress = False

    def _on_instance_changed(self, item_ref, prop: str, value):
        """Per-instance override changed."""
        if self._suppress:
            return
        if not hasattr(item_ref, "_display_overrides"):
            item_ref._display_overrides = {}
        item_ref._display_overrides[prop] = value
        self._apply_preview()

    def _reset_instance(self, item_ref):
        """Clear all per-instance overrides and revert widgets to category defaults."""
        if not hasattr(item_ref, "_display_overrides"):
            return
        item_ref._display_overrides.clear()

        inst = self._inst_data.get(id(item_ref))
        if inst is None:
            return
        cat_key = inst["category"]
        cat_widgets = self._cat_data[cat_key]["widgets"]

        self._suppress = True
        try:
            w = inst["widgets"]
            w["vis"].setChecked(cat_widgets["vis"].isChecked())
            self._update_color_btn(w["color_btn"],
                                   cat_widgets["color_btn"].property("_color"))
            if _category_has_fill(cat_key):
                fill_val = cat_widgets["fill_btn"].property("_color")
                if fill_val is not None:
                    self._update_fill_btn(w["fill_btn"], fill_val)
            if _category_has_section(cat_key):
                self._fill_section_selector(
                    w["section_sel"], cat_widgets["section_sel"].currentData())
            w["scale"].setValue(cat_widgets["scale"].value())
            w["opacity"].setValue(cat_widgets["opacity"].value())
            if _category_has_font(cat_key):
                w["font"].setValue(cat_widgets["font"].value())
        finally:
            self._suppress = False
        self._apply_preview()

    def _sync_tab_buttons(self, _idx=None) -> None:
        """Reset All / Set as Default do not apply to the Fill Types tab (the
        table is per project, not an app-wide default): disable them there."""
        on_ft = self._tabs.currentWidget() is self._ft_tab
        tip = "Fill Types are per-project: there is no default to reset or save."
        for btn, own in ((self._reset_btn, self._reset_tip),
                         (self._default_btn, self._default_tip)):
            btn.setEnabled(not on_ft)
            btn.setToolTip(tip if on_ft else own)

    def _reset_all(self):
        """Reset active tab to factory defaults."""
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._reset_model_tab()
        elif idx == 1:
            self._reset_paper_space_tab()
        elif idx == 2:
            self._reset_line_weights_tab()

    def _reset_model_tab(self):
        """Reset all Model tab categories and instances to factory defaults."""
        icons = self._type_icons(self._section_table())
        self._suppress = True
        try:
            for cat_def in _CATEGORIES:
                key = cat_def["key"]
                cw = self._cat_data[key]["widgets"]
                cw["vis"].setChecked(cat_def["visible"])
                self._update_color_btn(cw["color_btn"], cat_def["color"])
                if _category_has_fill(key) and cat_def["fill"]:
                    self._update_fill_btn(cw["fill_btn"], cat_def["fill"])
                factory_tid = self._factory_section_type(cat_def)
                if factory_tid is not None:
                    self._fill_section_selector(cw["section_sel"], factory_tid, icons)
                cw["scale"].setValue(cat_def["scale"])
                cw["opacity"].setValue(cat_def["opacity"])
                if _category_has_font(key) and cat_def["font"] is not None:
                    cw["font"].setValue(cat_def["font"])

                for obj in self._cat_data[key]["items"]:
                    if hasattr(obj, "_display_overrides"):
                        obj._display_overrides.clear()
                    inst = self._inst_data.get(id(obj))
                    if inst:
                        iw = inst["widgets"]
                        iw["vis"].setChecked(cat_def["visible"])
                        self._update_color_btn(iw["color_btn"], cat_def["color"])
                        if _category_has_fill(key) and cat_def["fill"]:
                            self._update_fill_btn(iw["fill_btn"], cat_def["fill"])
                        if factory_tid is not None:
                            self._fill_section_selector(iw["section_sel"], factory_tid, icons)
                        iw["scale"].setValue(cat_def["scale"])
                        iw["opacity"].setValue(cat_def["opacity"])
                        if _category_has_font(key) and cat_def["font"] is not None:
                            iw["font"].setValue(cat_def["font"])
        finally:
            self._suppress = False
        self._apply_preview()
        # Model "Blocks" weight -> factory (fires _on_model_blocks_weight)
        from .paper_display import model_blocks_factory_weight
        self._model_blocks_combo.setCurrentText(model_blocks_factory_weight())

    @staticmethod
    def _factory_section_type(cat_def: dict):
        """Id of a category's factory section type (the project's of that
        name wins, else it is added from the factory look); None when the
        category has no section cell."""
        name = cat_def.get("section_type")
        if not name:
            return None
        before = len(fill_types.project_table().all())
        t = fill_types.project_table().ensure_named(
            name, fill_types.legacy_section_layers(
                cat_def.get("section"), cat_def.get("section_pattern"), 1.0))
        if len(fill_types.project_table().all()) != before:
            fill_types.notify_changed()
        return t.id

    def _reset_paper_space_tab(self):
        """Reset Paper Space tab to B&W factory defaults."""
        from .paper_display import (
            factory_paper_categories, save_paper_categories,
            PaperColorMode, save_paper_color_mode, _HAS_FILL, _HAS_SECTION,
            _LW_ONLY,
        )
        save_paper_color_mode(PaperColorMode.BW, self._settings)
        cats = factory_paper_categories()
        save_paper_categories(cats, self._settings)
        self._suppress = True
        self._color_mode_combo.setCurrentIndex(1)  # B&W
        for key, widgets in self._paper_cat_data.items():
            factory = cats[key]
            if key not in _LW_ONLY:
                self._update_color_btn(widgets["color_btn"], factory["color"])
                widgets["color_btn"].setProperty("_color", factory["color"])
            if key in _HAS_FILL:
                self._update_color_btn(widgets["fill_btn"], factory["fill"])
                widgets["fill_btn"].setProperty("_color", factory["fill"])
            if key in _HAS_SECTION:
                self._update_color_btn(widgets["section_btn"],
                                       factory["section_color"])
                widgets["section_btn"].setProperty("_color",
                                                    factory["section_color"])
            idx = widgets["lw_combo"].findText(factory["line_weight"])
            if idx >= 0:
                widgets["lw_combo"].setCurrentIndex(idx)
            widgets["opacity"].setValue(factory["opacity"])
            widgets["vis"].setChecked(factory.get("visible", True))
        self._suppress = False
        self._apply_color_mode_ui(PaperColorMode.BW)
        self._apply_paper_preview()

    def _reset_line_weights_tab(self):
        """Reset the PROJECT weight table to factory defaults (LT1-3).

        Never writes the template; "Set as Default" does that.
        """
        from .paper_display import FACTORY_LINE_WEIGHTS
        self._lw_defs = [d.copy() for d in FACTORY_LINE_WEIGHTS]
        self._commit_lw_defs()
        self._populate_lw_table()
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()

    def _set_as_default(self):
        """Save current tab settings as defaults for new projects."""
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._set_model_as_default()
        elif idx == 1:
            self._settings.sync()  # paper space already in QSettings
        elif idx == 2:
            # The tab edits the PROJECT table; this writes the template that
            # new projects / table-less files copy (LT1-3).
            from .paper_display import save_line_weights
            save_line_weights(self._lw_defs, self._settings)

    def _set_model_as_default(self):
        """Save current Model tab category settings as defaults for new projects.

        Also saves to regular keys so the Display Manager shows them on
        next open, and calls sync() to force immediate persistence.
        """
        for cat_def in _CATEGORIES:
            key = cat_def["key"]
            s = self._read_category_settings(key)
            # Save as defaults for new projects
            self._settings.setValue(f"display/{key}/default_color", s["color"])
            self._settings.setValue(f"display/{key}/default_scale", s["scale"])
            self._settings.setValue(f"display/{key}/default_opacity", s["opacity"])
            self._settings.setValue(f"display/{key}/default_visible", s["visible"])
            if s.get("fill") is not None:
                self._settings.setValue(f"display/{key}/default_fill", s["fill"])
            _store_section_cell(self._settings, key, s, prefix="default_")
            if s.get("font") is not None:
                self._settings.setValue(f"display/{key}/default_font", s["font"])
            # Also save as current settings so they persist across sessions
            self._settings.setValue(f"display/{key}/color", s["color"])
            self._settings.setValue(f"display/{key}/scale", s["scale"])
            self._settings.setValue(f"display/{key}/opacity", s["opacity"])
            self._settings.setValue(f"display/{key}/visible", s["visible"])
            if s.get("fill") is not None:
                self._settings.setValue(f"display/{key}/fill", s["fill"])
            _store_section_cell(self._settings, key, s)
            if s.get("font") is not None:
                self._settings.setValue(f"display/{key}/font", s["font"])
        from .paper_display import model_blocks_weight
        self._settings.setValue(
            f"display/{_MODEL_BLOCKS_KEY}/default_line_weight",
            model_blocks_weight())
        self._settings.setValue(
            f"display/{_MODEL_BLOCKS_KEY}/line_weight", model_blocks_weight())
        self._settings.sync()

    # ------------------------------------------------------------------
    # Widget value helpers
    # ------------------------------------------------------------------

    def _set_widget_value(self, widgets: dict, prop: str, value):
        """Programmatically set a widget's value (suppress re-entry)."""
        if prop == "visible":
            widgets["vis"].setChecked(value)
        elif prop == "color":
            self._update_color_btn(widgets["color_btn"], value)
        elif prop == "fill":
            if widgets["fill_btn"].isEnabled() and value is not None:
                self._update_fill_btn(widgets["fill_btn"], value)
        elif prop == "section_type":
            sel = widgets.get("section_sel")
            t = self._section_table().by_name(value) if sel is not None else None
            if t is not None:
                at = sel.findData(t.id)
                if at >= 0:             # listed already: just move the selection
                    sel.blockSignals(True)
                    try:
                        sel.setCurrentIndex(at)
                    finally:
                        sel.blockSignals(False)
                else:
                    self._fill_section_selector(sel, t.id)
        elif prop == "scale":
            widgets["scale"].setValue(value)
        elif prop == "opacity":
            widgets["opacity"].setValue(value)
        elif prop == "font":
            if widgets["font"].isEnabled():
                widgets["font"].setValue(int(value))

    def _read_category_settings(self, key: str) -> dict:
        """Read current widget values for a category row."""
        w = self._cat_data[key]["widgets"]
        result = {
            "visible": w["vis"].isChecked(),
            "color": w["color_btn"].property("_color"),
            "scale": w["scale"].value(),
            "opacity": w["opacity"].value(),
        }
        if _category_has_fill(key):
            result["fill"] = w["fill_btn"].property("_color")
        else:
            result["fill"] = None
        if _category_has_section(key):
            # The picked Fill Type's name + its current look (R7: QSettings and
            # the project payload store both; the project's type wins by name).
            t = self._section_table().get(w["section_sel"].currentData())
            result["section_type"] = t.name if t is not None else _CATEGORY_MAP[key]["section_type"]
            result["section_look"] = to_record(t.layers) if t is not None else None
        else:
            result["section_type"] = None
            result["section_look"] = None
        if _category_has_font(key):
            result["font"] = w["font"].value()
        else:
            result["font"] = None
        return result

    # ------------------------------------------------------------------
    # Live preview
    # ------------------------------------------------------------------

    # Categories whose display is read from QSettings by the elevation scene
    _ELEV_CATEGORIES = {"Grid Line", "Level Datum", "Elevation Marker",
                         "Wall", "Roof", "Floor"}

    def _apply_preview(self):
        """Apply current dialog state to all scene items (live preview)."""
        from .fitting import Fitting

        elev_dirty = False
        for cat_def in _CATEGORIES:
            key = cat_def["key"]
            cat_settings = self._read_category_settings(key)
            cat_tid = (fill_types.category_section_type(key, cat_settings)
                       if _category_has_section(key) else None)

            for obj in self._cat_data[key]["items"]:
                overrides = getattr(obj, "_display_overrides", {})
                eff_color = overrides.get("color", cat_settings["color"])
                eff_scale = overrides.get("scale", cat_settings["scale"])
                eff_opacity = overrides.get("opacity", cat_settings["opacity"])
                eff_visible = overrides.get("visible", cat_settings["visible"])
                eff_fill = overrides.get("fill", cat_settings.get("fill"))
                eff_font = overrides.get("font", cat_settings.get("font"))
                eff_tid = cat_tid
                if cat_tid is not None and isinstance(overrides, dict):
                    fill_types.convert_item_section_override(
                        key, overrides, fill_types.resolve(cat_tid, None)[0])
                    eff_tid = overrides.get("section_type", cat_tid)

                apply_display_to_item(obj, eff_color, eff_scale,
                                      eff_opacity, eff_visible,
                                      fill_color=eff_fill,
                                      font_size=eff_font,
                                      section_type=eff_tid)

            # Sync elevation-related categories to QSettings so elevation
            # scene rebuilds pick up changes during live preview.
            if key in self._ELEV_CATEGORIES:
                self._settings.setValue(f"display/{key}/color", cat_settings["color"])
                self._settings.setValue(f"display/{key}/scale", cat_settings["scale"])
                self._settings.setValue(f"display/{key}/opacity", cat_settings["opacity"])
                self._settings.setValue(f"display/{key}/visible", cat_settings["visible"])
                if cat_settings.get("fill") is not None:
                    self._settings.setValue(f"display/{key}/fill", cat_settings["fill"])
                _store_section_cell(self._settings, key, cat_settings)
                if cat_settings.get("font") is not None:
                    self._settings.setValue(f"display/{key}/font", cat_settings["font"])
                elev_dirty = True

        self._scene.update()

        # Rebuild open elevation views so changes are visible immediately
        if elev_dirty:
            self._settings.sync()
            elev_mgr = getattr(self._scene, "_section_manager", None)
            if elev_mgr is not None and hasattr(elev_mgr, "rebuild_all"):
                elev_mgr.rebuild_all()

    # ------------------------------------------------------------------
    # Paper Space tab
    # ------------------------------------------------------------------

    # Paper-space tree column indices
    _PS_COL_NAME    = 0
    _PS_COL_VIS     = 1
    _PS_COL_COLOR   = 2
    _PS_COL_FILL    = 3
    _PS_COL_SECTION = 4
    _PS_COL_LW      = 5
    _PS_COL_OPACITY = 6

    # Paper-space category groups
    _PS_GROUPS = {
        "Fire Suppression": [
            "Pipe", "Sprinkler", "Fitting", "Water Supply", "Node",
            "Hydraulic Badge",
        ],
        "Architecture": ["Wall", "Door", "Window", "Opening", "Roof", "Room", "Floor"],
        "Grids & Levels": [
            "Grid Line", "Level Datum", "Elevation Marker", "Detail Marker",
        ],
        "Drafting": ["Hatch", "Blocks"],
    }

    def _build_paper_space_tab(self) -> QWidget:
        """Build the Paper Space display overrides tab."""
        from .paper_display import (
            weight_names, load_paper_categories, load_paper_color_mode,
            save_paper_categories, save_paper_color_mode,
            PaperColorMode, _HAS_FILL, _HAS_SECTION, _CATEGORY_KEYS, _LW_ONLY,
        )
        _t = th.detect()

        page = QWidget()
        layout = QVBoxLayout(page)

        # ── Color mode dropdown ─────────────────────────────────────
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Color Mode:"))
        self._color_mode_combo = QComboBox()
        self._color_mode_combo.addItems(["Full Color", "B&W", "Custom"])
        mode = load_paper_color_mode(self._settings)
        mode_index = {
            PaperColorMode.FULL_COLOR: 0,
            PaperColorMode.BW: 1,
            PaperColorMode.CUSTOM: 2,
        }.get(mode, 1)
        self._color_mode_combo.setCurrentIndex(mode_index)
        self._color_mode_combo.currentIndexChanged.connect(
            self._on_color_mode_changed)
        mode_row.addWidget(self._color_mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # ── Category tree ───────────────────────────────────────────
        self._ps_tree = QTreeWidget()
        self._ps_tree.setColumnCount(7)
        self._ps_tree.setHeaderLabels(
            ["Name", "Vis", "Colour", "Fill", "Section", "Line Weight",
             "Opacity"])
        self._ps_tree.setRootIsDecorated(True)
        self._ps_tree.setIndentation(20)
        self._ps_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._ps_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hdr = self._ps_tree.header()
        hdr.setSectionResizeMode(self._PS_COL_NAME,
                                 QHeaderView.ResizeMode.Stretch)
        for col in (self._PS_COL_VIS, self._PS_COL_COLOR, self._PS_COL_FILL,
                    self._PS_COL_SECTION):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self._ps_tree.setColumnWidth(col, 60)
        self._ps_tree.setColumnWidth(self._PS_COL_VIS, 40)
        hdr.setSectionResizeMode(self._PS_COL_LW,
                                 QHeaderView.ResizeMode.Interactive)
        self._ps_tree.setColumnWidth(self._PS_COL_LW, 100)
        hdr.setSectionResizeMode(self._PS_COL_OPACITY,
                                 QHeaderView.ResizeMode.Interactive)
        self._ps_tree.setColumnWidth(self._PS_COL_OPACITY, 90)

        # Load data
        cats = load_paper_categories(self._settings)
        lw_names = weight_names()          # the PROJECT table (LT1-3)
        from .paper_display import factory_paper_categories, picker_weight_name
        factory_all = factory_paper_categories()

        self._paper_cat_data: dict[str, dict] = {}

        bold = QFont()
        bold.setBold(True)
        group_font = QFont()
        group_font.setBold(True)
        group_font.setPointSize(group_font.pointSize() + 1)

        _disabled_ss = (
            f"background: {_t.bg_sunken}; color: {_t.text_disabled}; "
            f"border: 1px solid {_t.border_subtle}; border-radius: 2px;")

        self._suppress = True

        for grp_name, grp_keys in self._PS_GROUPS.items():
            grp_item = QTreeWidgetItem(self._ps_tree)
            grp_item.setText(self._PS_COL_NAME, grp_name)
            grp_item.setFont(self._PS_COL_NAME, group_font)
            grp_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            grp_item.setForeground(self._PS_COL_NAME,
                                   QColor(_t.text_primary))
            grp_item.setExpanded(True)

            for key in grp_keys:
                cat = cats.get(key, {})
                tree_item = QTreeWidgetItem(grp_item)
                tree_item.setText(self._PS_COL_NAME, category_label(key))
                tree_item.setFont(self._PS_COL_NAME, bold)
                tree_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

                # ── Visibility checkbox ──────────────────────────────
                vis_cb = QCheckBox()
                vis_cb.setChecked(cat.get("visible", True))
                vis_cb.stateChanged.connect(
                    lambda state, k=key: self._on_paper_vis_changed(
                        k, state == Qt.CheckState.Checked.value))
                self._ps_tree.setItemWidget(tree_item, self._PS_COL_VIS,
                                            vis_cb)

                # ── Colour swatch ────────────────────────────────────
                color_btn = QPushButton()
                color_btn.setFixedSize(40, 20)
                color_val = cat.get("color", "#000000")
                color_btn.setProperty("_color", color_val)
                _apply_swatch_look(color_btn, color_val, _t)
                color_btn.clicked.connect(
                    lambda _, k=key: self._on_paper_color_clicked(k, "color"))
                self._ps_tree.setItemWidget(tree_item, self._PS_COL_COLOR,
                                            color_btn)

                # ── Fill swatch ──────────────────────────────────────
                fill_btn = QPushButton()
                fill_btn.setFixedSize(40, 20)
                if key in _HAS_FILL:
                    fill_val = cat.get("fill", "#ffffff")
                    fill_btn.setProperty("_color", fill_val)
                    _apply_swatch_look(fill_btn, fill_val, _t)
                    fill_btn.clicked.connect(
                        lambda _, k=key: self._on_paper_color_clicked(
                            k, "fill"))
                else:
                    fill_btn.setProperty("_color", "")
                    fill_btn.setStyleSheet(_disabled_ss)
                    fill_btn.setEnabled(False)
                self._ps_tree.setItemWidget(tree_item, self._PS_COL_FILL,
                                            fill_btn)

                # ── Section swatch ───────────────────────────────────
                section_btn = QPushButton()
                section_btn.setFixedSize(40, 20)
                if key in _HAS_SECTION:
                    sec_val = cat.get("section_color", "#000000")
                    section_btn.setProperty("_color", sec_val)
                    _apply_swatch_look(section_btn, sec_val, _t)
                    section_btn.clicked.connect(
                        lambda _, k=key: self._on_paper_color_clicked(
                            k, "section_color"))
                else:
                    section_btn.setProperty("_color", "")
                    section_btn.setStyleSheet(_disabled_ss)
                    section_btn.setEnabled(False)
                self._ps_tree.setItemWidget(tree_item, self._PS_COL_SECTION,
                                            section_btn)

                # ── Line Weight combo ────────────────────────────────
                lw_combo = QComboBox()
                lw_combo.addItems(lw_names)
                cur_lw = picker_weight_name(cat.get("line_weight")
                                            or factory_all[key]["line_weight"])  # MW-6: the row it draws as
                idx = lw_combo.findText(cur_lw)
                if idx >= 0:
                    lw_combo.setCurrentIndex(idx)
                lw_combo.currentTextChanged.connect(
                    lambda t, k=key: self._on_paper_lw_changed(k, t))
                self._ps_tree.setItemWidget(tree_item, self._PS_COL_LW,
                                            lw_combo)

                # ── Opacity spinbox ──────────────────────────────────
                opacity_spin = QSpinBox()
                opacity_spin.setRange(0, 100)
                opacity_spin.setSingleStep(5)
                opacity_spin.setValue(cat.get("opacity", 100))
                opacity_spin.setSuffix("%")
                opacity_spin.setFixedHeight(22)
                opacity_spin.valueChanged.connect(
                    lambda v, k=key: self._on_paper_opacity_changed(k, v))
                self._ps_tree.setItemWidget(tree_item, self._PS_COL_OPACITY,
                                            opacity_spin)

                if key in _LW_ONLY:
                    for _w in (vis_cb, color_btn, opacity_spin):
                        _w.setEnabled(False)
                    color_btn.setStyleSheet(_disabled_ss)
                    lw_combo.setToolTip(
                        "Line weight of hatch pattern lines on sheets and PDF")
                    tree_item.setToolTip(
                        self._PS_COL_NAME,
                        "Line weight of hatch pattern lines on sheets and PDF")

                self._paper_cat_data[key] = {
                    "tree_item": tree_item,
                    "vis": vis_cb,
                    "color_btn": color_btn,
                    "fill_btn": fill_btn,
                    "section_btn": section_btn,
                    "lw_combo": lw_combo,
                    "opacity": opacity_spin,
                }

        self._suppress = False

        # Apply initial color mode UI state
        self._apply_color_mode_ui(mode)

        layout.addWidget(self._ps_tree)
        return page

    # ── Paper Space event handlers ───────────────────────────────────

    def _on_color_mode_changed(self, index: int):
        """Color mode dropdown changed."""
        if self._suppress:
            return
        from .paper_display import (
            PaperColorMode, save_paper_color_mode,
            save_paper_categories, load_paper_categories,
            _HAS_FILL, _HAS_SECTION, _LW_ONLY,
        )
        mode_map = {0: PaperColorMode.FULL_COLOR,
                    1: PaperColorMode.BW,
                    2: PaperColorMode.CUSTOM}
        mode = mode_map.get(index, PaperColorMode.BW)
        save_paper_color_mode(mode, self._settings)

        if mode == PaperColorMode.BW:
            # Populate all colours with B&W values
            cats = load_paper_categories(self._settings)
            self._suppress = True
            for key, widgets in self._paper_cat_data.items():
                if key in _LW_ONLY:
                    continue
                cats[key]["color"] = "#000000"
                self._update_color_btn(widgets["color_btn"], "#000000")
                widgets["color_btn"].setProperty("_color", "#000000")
                if key in _HAS_FILL:
                    cats[key]["fill"] = "#ffffff"
                    self._update_color_btn(widgets["fill_btn"], "#ffffff")
                    widgets["fill_btn"].setProperty("_color", "#ffffff")
                if key in _HAS_SECTION:
                    cats[key]["section_color"] = "#000000"
                    self._update_color_btn(widgets["section_btn"], "#000000")
                    widgets["section_btn"].setProperty("_color", "#000000")
            save_paper_categories(cats, self._settings)
            self._suppress = False

        self._apply_color_mode_ui(mode)
        self._apply_paper_preview()

    def _apply_color_mode_ui(self, mode):
        """Enable/disable colour columns based on color mode."""
        from .paper_display import (
            PaperColorMode, _HAS_FILL, _HAS_SECTION, _LW_ONLY)
        disable = (mode == PaperColorMode.FULL_COLOR)
        for key, widgets in self._paper_cat_data.items():
            if key in _LW_ONLY:
                continue
            widgets["color_btn"].setEnabled(not disable)
            if key in _HAS_FILL:
                widgets["fill_btn"].setEnabled(not disable)
            if key in _HAS_SECTION:
                widgets["section_btn"].setEnabled(not disable)

    def _on_paper_color_clicked(self, key: str, prop: str):
        """Open the house colour picker for a paper-space category colour property."""
        from .paper_display import (
            PaperColorMode, save_paper_color_mode, load_paper_color_mode,
            load_paper_categories, save_paper_categories,
        )
        widgets = self._paper_cat_data[key]
        btn_key = {"color": "color_btn", "fill": "fill_btn",
                   "section_color": "section_btn"}[prop]
        btn = widgets[btn_key]
        cur_hex = btn.property("_color")
        if cur_hex is None:
            cur_hex = "#000000"
        hex_val = colour_picker.pick_colour(cur_hex, self, f"{key} · {prop}")
        if hex_val is None:
            return

        self._update_color_btn(btn, hex_val)
        btn.setProperty("_color", hex_val)

        # Save to QSettings
        cats = load_paper_categories(self._settings)
        cats[key][prop] = hex_val
        save_paper_categories(cats, self._settings)

        # Auto-switch to Custom if currently in Full Color or B&W
        current_mode = load_paper_color_mode(self._settings)
        if current_mode in (PaperColorMode.FULL_COLOR, PaperColorMode.BW):
            save_paper_color_mode(PaperColorMode.CUSTOM, self._settings)
            self._suppress = True
            self._color_mode_combo.setCurrentIndex(2)  # Custom
            self._suppress = False
            self._apply_color_mode_ui(PaperColorMode.CUSTOM)

        self._apply_paper_preview()

    def _on_paper_lw_changed(self, key: str, text: str):
        """Line weight combo changed for a paper-space category."""
        if self._suppress:
            return
        from .paper_display import load_paper_categories, save_paper_categories
        cats = load_paper_categories(self._settings)
        cats[key]["line_weight"] = text
        save_paper_categories(cats, self._settings)
        self._apply_paper_preview()

    def _on_paper_vis_changed(self, key: str, checked: bool):
        """Visibility checkbox changed for a paper-space category."""
        if self._suppress:
            return
        from .paper_display import load_paper_categories, save_paper_categories
        cats = load_paper_categories(self._settings)
        cats[key]["visible"] = checked
        save_paper_categories(cats, self._settings)
        self._apply_paper_preview()

    def _on_paper_opacity_changed(self, key: str, val: int):
        """Opacity spinbox changed for a paper-space category."""
        if self._suppress:
            return
        from .paper_display import load_paper_categories, save_paper_categories
        cats = load_paper_categories(self._settings)
        cats[key]["opacity"] = val
        save_paper_categories(cats, self._settings)
        self._apply_paper_preview()

    def _apply_paper_preview(self):
        """Trigger paper-space viewport refresh for live preview."""
        parent = self.parent()
        if parent is not None and hasattr(parent, "paper_space_widget"):
            ps_widget = parent.paper_space_widget
            if ps_widget is not None and hasattr(ps_widget, "paper_scene"):
                ps_widget.paper_scene.update()

    # ------------------------------------------------------------------
    # Line Weights tab
    # ------------------------------------------------------------------

    def _build_line_weights_tab(self) -> QWidget:
        """Build the Line Weights definition tab."""
        from .paper_display import project_line_weights
        from PyQt6.QtWidgets import QTableWidget

        page = QWidget()
        layout = QVBoxLayout(page)

        self._lw_table = QTableWidget()
        self._lw_table.setColumnCount(3)
        self._lw_table.setHorizontalHeaderLabels(
            ["Name", "Width (mm)", "Model (px)"])
        self._lw_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._lw_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Fixed)
        self._lw_table.setColumnWidth(1, 120)
        self._lw_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Fixed)
        self._lw_table.setColumnWidth(2, 120)
        self._lw_table.horizontalHeaderItem(2).setToolTip(_MODEL_PX_TIP)
        self._lw_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._lw_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)

        # Edits the live PROJECT table (LT1-3); copies so the dialog never
        # mutates project_line_weights()'s result in place.
        self._lw_defs = [d.copy() for d in project_line_weights()]
        self._lw_snapshot = [d.copy() for d in self._lw_defs]
        # (old, new) renames in order -- reject() replays them backwards.
        self._lw_renames: list[tuple[str, str]] = []
        self._lw_edited = False            # set by _commit_lw_defs
        # Rename aliases are part of the Cancel snapshot (H-g).
        from .paper_display import weight_aliases
        self._lw_alias_snapshot = weight_aliases()
        self._populate_lw_table()

        self._lw_table.cellChanged.connect(self._on_lw_cell_changed)
        self._lw_table.currentCellChanged.connect(self._update_lw_remove_state)
        layout.addWidget(self._lw_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_lw_add)
        self._lw_remove_btn = QPushButton("Remove")
        self._lw_remove_btn.clicked.connect(self._on_lw_remove)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(self._lw_remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return page

    def _populate_lw_table(self):
        from PyQt6.QtWidgets import QTableWidgetItem
        from .paper_display import auto_model_px
        self._suppress = True
        self._lw_defs.sort(key=lambda d: d.width_mm)
        self._lw_table.setRowCount(len(self._lw_defs))
        muted = th.detect().color("muted")
        for row, lw in enumerate(self._lw_defs):
            name_item = QTableWidgetItem(lw.name)
            width_item = QTableWidgetItem(f"{lw.width_mm:.2f}")
            self._lw_table.setItem(row, 0, name_item)
            self._lw_table.setItem(row, 1, width_item)
            # Model (px) (MW-11): muted "Auto (n)" or the whole-px override.
            if lw.model_px is None:
                model_item = QTableWidgetItem(
                    f"Auto ({auto_model_px(lw.width_mm)})")
                model_item.setForeground(muted)
            else:
                model_item = QTableWidgetItem(str(lw.model_px))
            model_item.setToolTip(_MODEL_PX_TIP)
            self._lw_table.setItem(row, 2, model_item)
        self._suppress = False

    def _weight_refs(self):
        """Yield ``(name, (kind, ref))`` for every live by-name weight ref:
        sheet annotations; model-plan texts; project definition text
        primitives and stroke ``style.weight``; open Block Editors' texts and
        styled raw items, and the project scene's styled geometry
        (linetypes.md LT1-5 / LT2-8); placed blocks' Weight overrides and
        definitions' nested-record Weight overrides (WM2).
        """
        from .stroke_style import is_named_weight
        for sheet in getattr(self._scene, "_sheets", []) or []:
            for ann in getattr(sheet, "annotations", []):
                yield ann.border_weight, ("ann", ann)
        scenes = [self._scene]
        prov = getattr(self._scene, "_editor_scenes_provider", None)
        if callable(prov):
            scenes.extend(sc for sc in prov() if sc is not self._scene)
        for sc in scenes:
            for item in getattr(sc, "_texts", []) or []:
                yield item._data.border_weight, ("item", item)
            for item in sc.items():
                st = getattr(item, "style", None)
                if isinstance(st, dict) and is_named_weight(st.get("weight")):
                    yield st["weight"], ("raw", item)
            for inst in getattr(sc, "_block_instances", []) or []:
                w = getattr(inst, "overrides", {}).get("weight")
                if is_named_weight(w):
                    yield w, ("inst", inst)
        reg = getattr(self._scene, "block_registry", None)
        if reg is not None:
            for bid in reg.ids():
                defn = reg.get(bid)
                for prim in getattr(defn, "primitives", []) or []:
                    if prim.get("type") == "text" and "border_weight" in prim:
                        yield prim["border_weight"], ("prim", (bid, prim))
                    st = prim.get("style")
                    if isinstance(st, dict) and is_named_weight(st.get("weight")):
                        yield st["weight"], ("sprim", (bid, st))
                    ov = prim.get("overrides")
                    if isinstance(ov, dict) and is_named_weight(ov.get("weight")):
                        yield ov["weight"], ("nrec", (bid, ov))

    def _line_weight_in_use(self, name: str) -> bool:
        """True if *name* is referenced anywhere by name.

        Reference kinds: paper categories; underlays (§16.6: the per-underlay
        default ``line_weight_name`` and per-layer
        ``layer_overrides[layer]["line_weight"]``); sheet text annotations
        (all sheets); model-plan texts (``_texts``); text primitives and
        stroke ``style.weight`` of project block definitions; open Block
        Editors' items; placed blocks' and nested records' Weight overrides
        (WM2); the Model "Blocks" weight (LT2-6 / LT2-8). Holder
        names are compared canonically (an alias key counts as its target).
        """
        from .paper_display import (canonical_weight_name,
                                    load_paper_categories, model_blocks_weight)
        if model_blocks_weight() == name:
            return True
        cats = load_paper_categories(self._settings)
        if any(v.get("line_weight") == name for v in cats.values()):
            return True
        for data, _item in getattr(self._scene, "underlays", []):
            if data.line_weight_name == name:
                return True
            for ov in data.layer_overrides.values():
                if ov.get("line_weight") == name:
                    return True
        if any(canonical_weight_name(n) == name
               for n, _ref in self._weight_refs()):
            return True
        return False

    def _propagate_lw_rename(self, old: str, new: str):
        """Follow a weight rename through every by-name reference."""
        from .paper_display import (load_paper_categories, model_blocks_weight,
                                    save_paper_categories,
                                    set_model_blocks_weight)
        if model_blocks_weight() == old:
            # Raw: the Cancel replay writes a pre-rename (alias-key) name
            # before the table + aliases are restored.
            set_model_blocks_weight(new, canonical=False)
            self._settings.setValue(
                f"display/{_MODEL_BLOCKS_KEY}/line_weight", new)
        cats = load_paper_categories(self._settings)
        for cat_vals in cats.values():
            if cat_vals.get("line_weight") == old:
                cat_vals["line_weight"] = new
        save_paper_categories(cats, self._settings)
        for data, _item in getattr(self._scene, "underlays", []):
            if data.line_weight_name == old:
                data.line_weight_name = new
            for ov in data.layer_overrides.values():
                if ov.get("line_weight") == old:
                    ov["line_weight"] = new
        touched_defs = set()
        for cur, (kind, ref) in list(self._weight_refs()):
            if cur != old:
                continue
            if kind == "ann":
                ref.border_weight = new     # live paper TextItems alias this data
            elif kind == "item":
                ref._data.border_weight = new
                ref.update()
            elif kind == "raw":
                ref.style["weight"] = new
                ref.update()
            elif kind == "sprim":
                bid, st = ref
                st["weight"] = new
                touched_defs.add(bid)
            elif kind == "inst":
                # Raw, like the Blocks weight: the Cancel replay writes a
                # pre-rename (alias-key) name before the aliases are restored.
                ref.set_overrides({**ref.overrides, "weight": new},
                                  canonical=False)
            elif kind == "nrec":
                bid, ov = ref
                ov["weight"] = new
                touched_defs.add(bid)
            else:
                bid, prim = ref
                prim["border_weight"] = new
                touched_defs.add(bid)
        reg = getattr(self._scene, "block_registry", None)
        for bid in touched_defs:
            reg.invalidate(bid)

    def _on_lw_cell_changed(self, row, col):
        if self._suppress or row >= len(self._lw_defs):
            return
        from .paper_display import (
            validate_line_weight_name, validate_line_weight_width,
        )
        old_def = self._lw_defs[row]
        text = self._lw_table.item(row, col).text().strip()
        renamed = None
        if col == 0:  # Name changed
            from .paper_display import canonical_weight_name, is_alias_key
            others = [d for i, d in enumerate(self._lw_defs) if i != row]
            # Renaming back onto an old name of THIS weight is allowed (its
            # refs are this weight's own); any other alias key is refused --
            # no hijack of the renamed-away references (LT2-8 / H-g).
            rename_back = (is_alias_key(text)
                           and canonical_weight_name(text) == old_def.name)
            hijack = is_alias_key(text) and not rename_back
            # A name something already references (a ref to a name not in the
            # table, e.g. an old file) is refused: renaming onto it would let
            # a later Cancel rewrite that pre-existing ref to the old name.
            in_use = (text != old_def.name and not rename_back
                      and self._line_weight_in_use(text))
            if hijack:
                # Non-modal refusal message at the edited cell (H-g).
                self._show_lw_refusal(row, (
                    f"“{text}” was renamed to "
                    f"“{canonical_weight_name(text)}” in this "
                    f"project — choose another name"))
            if not validate_line_weight_name(text, others) or hijack or in_use:
                self._suppress = True
                self._lw_table.item(row, 0).setText(old_def.name)
                self._suppress = False
                return
            old_name = old_def.name
            old_def.name = text
            self._propagate_lw_rename(old_name, text)
            self._lw_renames.append((old_name, text))
            renamed = (old_name, text)
        elif col == 2:  # Model (px) override (MW-11)
            from .paper_display import validate_model_px
            low = text.lower()
            if low in ("", "auto") or low.startswith("auto ("):
                new_px = None
            else:
                # ASCII digits only: int() would also take "1_0", "+5" or
                # non-ASCII digits.
                new_px = (int(text) if text.isascii() and text.isdigit()
                          else None)
                if new_px is None or not validate_model_px(new_px):
                    # Non-modal refusal at the edited cell, then restore it.
                    self._show_lw_refusal(row, (
                        "Model width must be a whole number of pixels from "
                        f"1 to {MODEL_WEIGHT_PX_MAX}, or Auto"), col=2)
                    self._populate_lw_table()
                    return
            if new_px == old_def.model_px:
                self._populate_lw_table()     # normalise the cell text
                return
            old_def.model_px = new_px
        elif col == 1:  # Width changed
            try:
                new_width = float(text)
            except ValueError:
                self._suppress = True
                self._lw_table.item(row, 1).setText(f"{old_def.width_mm:.2f}")
                self._suppress = False
                return
            if not validate_line_weight_width(new_width):
                self._suppress = True
                self._lw_table.item(row, 1).setText(f"{old_def.width_mm:.2f}")
                self._suppress = False
                return
            old_def.width_mm = new_width
        self._commit_lw_defs()
        if renamed is not None:
            # After the table commit: the table must already hold the new
            # name (set_project_line_weights drops alias keys that are live).
            from .paper_display import record_weight_rename
            record_weight_rename(*renamed)
        self._populate_lw_table()
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()

    def _show_lw_refusal(self, row: int, text: str, col: int = 0) -> None:
        """Non-modal tooltip at cell (*row*, *col*) -- the Name cell by
        default (headless-safe)."""
        from PyQt6.QtWidgets import QToolTip
        tbl = self._lw_table
        item = tbl.item(row, col)
        rect = tbl.visualItemRect(item) if item is not None else tbl.rect()
        pos = tbl.viewport().mapToGlobal(rect.bottomLeft())
        QToolTip.showText(pos, text, tbl.viewport(), rect)

    def _commit_lw_defs(self):
        """Push the edited table to the PROJECT (LT1-3) and notify MainWindow.

        Never writes the QSettings template (only "Set as Default" does).
        """
        from .paper_display import set_project_line_weights
        set_project_line_weights(self._lw_defs)
        self._lw_edited = True
        self.lineWeightsChanged.emit()

    def _on_lw_add(self):
        from .paper_display import LineWeightDef, is_alias_key
        idx = len(self._lw_defs) + 1
        name = f"Custom {idx}"
        # Never generate an alias key -- it would hijack old refs (H-g).
        while any(d.name == name for d in self._lw_defs) or is_alias_key(name):
            idx += 1
            name = f"Custom {idx}"
        self._lw_defs.append(LineWeightDef(name, 0.20))
        self._commit_lw_defs()
        self._populate_lw_table()
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()

    def _on_lw_remove(self):
        row = self._lw_table.currentRow()
        if row < 0 or row >= len(self._lw_defs):
            return
        if self._line_weight_in_use(self._lw_defs[row].name):
            return
        self._lw_defs.pop(row)
        self._commit_lw_defs()
        self._populate_lw_table()
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()

    def _update_lw_remove_state(self, row, col, prev_row, prev_col):
        """Disable Remove button if the selected weight is in use."""
        if row < 0 or row >= len(self._lw_defs):
            self._lw_remove_btn.setEnabled(False)
            return
        self._lw_remove_btn.setEnabled(
            not self._line_weight_in_use(self._lw_defs[row].name))

    def _refresh_lw_combos(self):
        """Refresh line weight dropdowns after definitions change."""
        from .paper_display import (weight_names, load_paper_categories,
                                    picker_weight_name, factory_paper_categories)
        lw_names = weight_names()          # the PROJECT table (LT1-3)
        cats = load_paper_categories(self._settings)
        factory_all = factory_paper_categories()
        self._suppress = True
        for key, widgets in self._paper_cat_data.items():
            combo = widgets["lw_combo"]
            cur = combo.currentText()
            combo.clear()
            combo.addItems(lw_names)
            idx = combo.findText(cur)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                cat_lw = picker_weight_name(
                    cats[key].get("line_weight")
                    or factory_all[key]["line_weight"])  # MW-6: the row it draws as
                idx = combo.findText(cat_lw)
                combo.setCurrentIndex(max(0, idx))
        self._suppress = False
        self._refresh_model_blocks_combo()

    # ------------------------------------------------------------------
    # Accept / Reject
    # ------------------------------------------------------------------

    def accept(self):
        """Persist category settings to QSettings and keep scene state."""
        if self._ft_tab.dirty:
            # HF5 R5: install the Fill Types working copy first (outside undo,
            # dirties the project like a line-weight edit) so the category
            # write below stores a type renamed in the tab by its new name.
            fill_types.set_project_table(self._ft_tab.table().copy())
            self._scene._dirty = True
            self._scene.sceneModified.emit()
            self._apply_preview()       # re-resolve every section cell against it
        for cat_def in _CATEGORIES:
            key = cat_def["key"]
            # One writer (HF5): the shared helper stores the section type + look.
            _write_category_to_settings(
                key, self._read_category_settings(key), self._settings)
        from .paper_display import model_blocks_weight
        self._settings.setValue(f"display/{_MODEL_BLOCKS_KEY}/line_weight",
                                model_blocks_weight())
        self._settings.sync()

        # D-A39: a category section pattern the user OK'd draws in this project
        # too — load it (and any instance override's) from the Hatch patterns
        # folder as part of the undo baseline. Not on Cancel: nothing to load.
        from .hatch_patterns import ensure_project_patterns
        ensure_project_patterns(self._scene)

        # Rebuild open elevation views so Level Datum / Grid Line / Elevation
        # Marker changes take effect immediately.
        elev_mgr = getattr(self._scene, "_section_manager", None)
        if elev_mgr is not None and hasattr(elev_mgr, "rebuild_all"):
            elev_mgr.rebuild_all()

        super().accept()

    def reject(self):
        """Cancel — revert all changes."""
        self._restore_snapshot()
        if self._ft_tab.dirty:          # HF5: drop the tab's edits + any previewed pending type
            fill_types.set_project_table(self._ft_table_snapshot.copy())
        # Weights first: un-renaming rewrites paper categories, so the
        # categories snapshot below must land after it and win (LT1-3).
        # Only when the table was edited: a no-op Cancel must not dirty.
        if getattr(self, "_lw_edited", False):
            from .paper_display import (set_project_line_weights,
                                        set_weight_aliases)
            for old, new in reversed(self._lw_renames):
                self._propagate_lw_rename(new, old)     # incl. underlay refs
            set_project_line_weights(self._lw_snapshot)
            # After the table: set_project_line_weights prunes live-name keys.
            set_weight_aliases(self._lw_alias_snapshot)
            self.lineWeightsChanged.emit()
        if hasattr(self, "_paper_settings_snapshot"):
            from .paper_display import (
                save_paper_categories, save_paper_color_mode, PaperColorMode,
            )
            save_paper_categories(self._paper_settings_snapshot["categories"],
                                  self._settings)
            save_paper_color_mode(
                PaperColorMode(self._paper_settings_snapshot["color_mode"]),
                self._settings)
        super().reject()


# ──────────────────────────────────────────────────────────────────────────────
# Startup helper — called after project load to apply saved display settings
# ──────────────────────────────────────────────────────────────────────────────

def apply_saved_display_settings(scene):
    """Read QSettings + per-item overrides and apply to all scene items.

    User defaults (``default_*`` keys) take priority over stale current keys,
    so the user's "Set as Default" preferences are always honoured.
    """
    settings = QSettings("GV", "FirePro3D")
    _migrate_display_keys(settings)
    for cat_def in _CATEGORIES:
        key = cat_def["key"]
        # Build overrides from default_* keys so they win over current keys
        default_ov: dict = {}
        for prop in ("color", "fill", "section_type", "section_look", "section",
                      "section_pattern", "section_scale", "scale", "opacity",
                      "visible", "font"):
            dv = settings.value(f"display/{key}/default_{prop}")
            if dv is not None:
                default_ov[prop] = dv
        vals = _read_category_from_settings(key, settings, overrides=default_ov)
        # Write back so Display Manager shows these values
        _write_category_to_settings(key, vals, settings)
        _apply_to_scene_items(scene, key, vals, respect_overrides=True)
    # Not the user default: this also runs at every undo restore (LT2-6).
    _apply_model_blocks_weight(None, settings, prefer_default=False,
                               use_user_default=False)
    settings.sync()


def apply_default_display_settings(scene):
    """Apply stored default settings (from 'Set as Default') to all items.

    Called when creating a new project to apply the user's preferred defaults.
    Reads from ``display/{key}/default_*`` keys, falling back to regular keys.
    """
    settings = QSettings("GV", "FirePro3D")
    _migrate_display_keys(settings)

    for cat_def in _CATEGORIES:
        key = cat_def["key"]
        # Build overrides from default_* keys (fall back to regular keys)
        default_ov: dict = {}
        for prop in ("color", "fill", "section_type", "section_look", "section",
                     "section_pattern", "section_scale", "scale", "opacity",
                     "visible", "font"):
            dv = settings.value(f"display/{key}/default_{prop}")
            if dv is not None:
                default_ov[prop] = dv
        vals = _read_category_from_settings(key, settings, overrides=default_ov)

        # Also save as current settings so Display Manager shows them
        _write_category_to_settings(key, vals, settings)

        if _category_has_section(key):
            # HF5 VC9 M1: the category's section type lands in the (just reset)
            # project table even when the new project has no wall / floor yet.
            fill_types.category_section_type(key, vals)
        _apply_to_scene_items(scene, key, vals, respect_overrides=False)
    _apply_model_blocks_weight(None, settings, prefer_default=True)


def _apply_model_blocks_weight(project: dict | None, settings: QSettings,
                               prefer_default: bool,
                               use_user_default: bool = True) -> None:
    """Resolve the Model "Blocks" weight (linetypes.md LT2-6): user default
    -> project -> current QSettings -> factory.

    Args:
        project: the project ``display_settings`` dict (Open), or None.
        settings: the QSettings store.
        prefer_default: New Project -- skip the current key (default ->
            factory).
        use_user_default: consult the "Set as Default" key. False on the
            ``apply_saved_display_settings`` path, which also runs at every
            model undo restore: it keeps the current project value instead of
            flipping it to the user default (current -> factory).
    """
    from .paper_display import model_blocks_weight, set_model_blocks_weight
    key = _MODEL_BLOCKS_KEY
    name = (settings.value(f"display/{key}/default_line_weight")
            if use_user_default else None)
    if not name and project:
        name = (project.get(key) or {}).get("line_weight")
    if not name and not prefer_default:
        name = settings.value(f"display/{key}/line_weight")
    set_model_blocks_weight(name or None)      # canonical (alias key -> live)
    settings.setValue(f"display/{key}/line_weight", model_blocks_weight())


def get_display_settings_for_save() -> dict:
    """Return the current category-level display settings as a dict
    suitable for embedding in a project file.
    """
    settings = QSettings("GV", "FirePro3D")
    result: dict = {}
    for cat_def in _CATEGORIES:
        key = cat_def["key"]
        vals = _read_category_from_settings(key, settings)
        # Strip None values for clean serialisation
        entry = {k: v for k, v in vals.items() if v is not None}
        result[key] = entry
    from .paper_display import model_blocks_weight
    result[_MODEL_BLOCKS_KEY] = {"line_weight": model_blocks_weight()}
    return result


def apply_project_display_settings(scene, display_dict: dict):
    """Apply display settings loaded from a project file to all items.

    *display_dict* maps category key → {color, scale, opacity, visible, fill, font}.
    User defaults (``default_*`` keys) take priority over project values,
    so the user's "Set as Default" preferences are always honoured.
    Falls back to QSettings for any category not present in *display_dict*.
    """
    settings = QSettings("GV", "FirePro3D")
    _migrate_display_keys(settings)

    for cat_def in _CATEGORIES:
        key = cat_def["key"]
        proj = _project_entry(display_dict, key)

        # User defaults win over project-embedded values
        merged = dict(proj)
        for prop in ("color", "fill", "section_type", "section_look", "section",
                      "section_pattern", "section_scale", "scale", "opacity",
                      "visible", "font"):
            user_default = settings.value(f"display/{key}/default_{prop}")
            if user_default is not None:
                merged[prop] = user_default

        vals = _read_category_from_settings(key, settings, overrides=merged)

        # Update QSettings so Display Manager shows these values
        _write_category_to_settings(key, vals, settings)

        _apply_to_scene_items(scene, key, vals, respect_overrides=True)
    _apply_model_blocks_weight(display_dict, settings, prefer_default=False)
    settings.sync()


def refresh_token_latched(scene) -> None:
    """Re-apply categories whose stored colour is a token, so values latched
    at apply time (SVG tints, marker / gridline pens, labels) follow a theme
    switch (HF1). Per-paint readers need nothing.

    Scenes without a ``sprinkler_system`` (paper sheet, elevation, schematic,
    Block Editor scenes) have no category items and are skipped.
    """
    from .colour_tokens import is_token
    if getattr(scene, "sprinkler_system", None) is None:
        return
    for cat in _CATEGORIES:
        key = cat["key"]
        vals = _read_category_from_settings(key)
        for item in _items_for_category_static(scene, key):
            # Per item: the effective colour is its own override when present,
            # else the category's -- a token override under a hex category
            # must re-latch too.
            ov = getattr(item, "_display_overrides", None) or {}
            if (is_token(ov.get("color", vals.get("color")))
                    or is_token(ov.get("fill", vals.get("fill")))):
                _apply_vals_to_item(item, vals, respect_overrides=True, key=key)


def _items_for_category_static(scene, key: str) -> list:
    """Same as DisplayManager._items_for_category but as a free function."""
    from .gridline import GridlineItem
    from .hydraulic_node_badge import HydraulicNodeBadge
    ss = scene.sprinkler_system
    if key == "Pipe":
        return list(ss.pipes)
    elif key == "Sprinkler":
        return [n.sprinkler for n in ss.nodes if n.has_sprinkler()]
    elif key == "Fitting":
        return [n.fitting for n in ss.nodes
                if n.has_fitting() and n.fitting.symbol
                and n.fitting.type != "no fitting"]
    elif key == "Water Supply":
        ws = getattr(scene, "water_supply_node", None)
        return [ws] if ws else []
    elif key == "Node":
        return list(ss.nodes)
    elif key == "Hydraulic Badge":
        return [i for i in scene.items() if isinstance(i, HydraulicNodeBadge)]
    elif key == "Design Area":
        return list(getattr(scene, "design_areas", []))
    elif key == "Grid Line":
        return [i for i in scene.items() if isinstance(i, GridlineItem)]
    elif key == "Roof":
        return list(getattr(scene, "_roofs", []))
    elif key == "Wall":
        return list(getattr(scene, "_walls", []))
    elif key in ("Door", "Window", "Opening"):
        return [op for wall in getattr(scene, "_walls", [])
                for op in getattr(wall, "openings", [])
                if op.display_category == key]
    elif key == "Room":
        return list(getattr(scene, "_rooms", []))
    elif key == "Floor":
        return list(getattr(scene, "_floor_slabs", []))
    elif key == "Elevation Marker":
        return [i for i in scene.items() if _is_elevation_marker(i)]
    elif key == "2D Geometry":
        items = []
        items.extend(getattr(scene, "_polylines", []))
        items.extend(getattr(scene, "_draw_lines", []))
        items.extend(getattr(scene, "_draw_rects", []))
        items.extend(getattr(scene, "_draw_circles", []))
        items.extend(getattr(scene, "_draw_arcs", []))
        items.extend(getattr(scene, "_draw_ellipses", []))
        items.extend(getattr(scene, "_draw_splines", []))
        items.extend(getattr(scene, "_draw_polygons", []))
        items.extend(getattr(scene, "_filled_regions", []))
        return [i for i in items if not getattr(i, "reference", False)]
    elif key == "Reference Geometry":
        lists = ("_polylines", "_draw_lines", "_draw_rects", "_draw_circles",
                 "_draw_arcs", "_draw_ellipses", "_draw_splines", "_draw_polygons",
                 "_filled_regions")
        return [i for a in lists for i in getattr(scene, a, [])
                if getattr(i, "reference", False)]
    return []
