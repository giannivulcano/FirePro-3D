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
    QHeaderView, QColorDialog, QWidget, QLabel, QComboBox,
    QAbstractItemView, QTabWidget, QLineEdit, QMenu,
)
from PyQt6.QtGui import (QColor, QFont, QBrush, QPen, QPainter, QPixmap,
                         QIcon, QCursor)
from PyQt6.QtCore import Qt, QSettings, QByteArray
from PyQt6.QtSvg import QSvgRenderer

import os
import xml.etree.ElementTree as ET
from . import theme as th


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
    # Remove any leftover QGraphicsColorizeEffect from older sessions
    if item.graphicsEffect() is not None:
        item.setGraphicsEffect(None)

    src = getattr(item, "_svg_source_path", None)
    if src is None or not os.path.isfile(src):
        return  # can't recolour without the source path

    needs_recolor = ((color and color.lower() != "#ffffff") or
                     (fill_color is not None))
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
    if not val:
        return ("solid", "#000000")
    if val.startswith("hatch:"):
        return ("hatch", val[6:])
    return ("solid", val)


def _compose_fill_value(mode: str, hex_color: str) -> str:
    """Encode mode + colour into the single string stored on the button."""
    if mode == "hatch":
        return f"hatch:{hex_color}"
    return hex_color


def _make_fill_icon(mode: str, hex_color: str, w: int = 40, h: int = 20,
                    pattern: str = "diagonal") -> QPixmap:
    """Return a small pixmap showing solid or hatch swatch."""
    pix = QPixmap(w, h)
    pix.fill(QColor("transparent"))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor(hex_color)
    if mode == "hatch":
        from .hatch_patterns import make_hatch_brush
        p.fillRect(0, 0, w, h, QColor("#2b2b2b"))
        brush = make_hatch_brush(pattern, min(w, h), col)
        p.setBrush(brush)
        p.setPen(QPen(QColor(0, 0, 0, 0)))
        p.drawRect(0, 0, w, h)
    else:
        p.fillRect(0, 0, w, h, col)
    p.end()
    return pix


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
    {"key": "Wall",             "color": "#666666", "fill": "#999999", "section": "#666666", "section_pattern": "diagonal",  "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Opening",         "color": "#888888", "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Roof",             "color": "#8B4513", "fill": "#D2B48C", "section": "#8B4513", "section_pattern": "diagonal",  "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Room",             "color": "#4488cc", "fill": "#4488cc", "section": None,      "section_pattern": None,        "font": 12,   "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Floor",            "color": "#8888cc", "fill": "#8888cc", "section": "#666666", "section_pattern": "diagonal",  "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Architecture"},
    {"key": "Grid Line",        "color": "#4488cc", "fill": "#1a1a2e", "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Grids & Levels"},
    {"key": "Level Datum",      "color": "#4488cc", "fill": "#1a1a2e", "section": None,      "section_pattern": None,        "font": 10,   "scale": 1.0, "opacity": 100, "visible": True, "group": "Grids & Levels"},
    {"key": "Elevation Marker", "color": "#4488cc", "fill": "#1a1a2e", "section": None,      "section_pattern": None,        "font": 10,   "scale": 1.0, "opacity": 100, "visible": True, "group": "Grids & Levels"},
    {"key": "Detail Marker",    "color": "#4488cc", "fill": "#1a1a2e", "section": None,      "section_pattern": None,        "font": 10,   "scale": 1.0, "opacity": 100, "visible": True, "group": "Grids & Levels"},
    {"key": "2D Geometry",      "color": "#ffffff", "fill": None,      "section": None,      "section_pattern": None,        "font": None, "scale": 1.0, "opacity": 100, "visible": True, "group": "Annotation & Geometry"},
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
_COL_RESET   = 8


_CATEGORY_MAP: dict[str, dict] = {c["key"]: c for c in _CATEGORIES}


# ---------------------------------------------------------------------------
# Shared QSettings read/write helpers — eliminates repeated patterns
# ---------------------------------------------------------------------------

def _read_category_from_settings(key: str, settings: QSettings | None = None,
                                  overrides: dict | None = None) -> dict:
    """Read display settings for category *key* from QSettings.

    If *overrides* is given (e.g. from a project file), those values take
    priority over QSettings, which in turn takes priority over factory
    defaults from ``_CATEGORIES``.

    Returns dict with keys: color, fill, hatch, scale, opacity, visible, font.
    """
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    cat_def = _CATEGORY_MAP[key]
    ov = overrides or {}

    def _s(prop, default):
        """Read from overrides → QSettings → factory default."""
        if prop in ov:
            return ov[prop]
        return settings.value(f"display/{key}/{prop}", default)

    color   = _s("color", cat_def["color"])
    fill    = _s("fill", cat_def.get("fill"))
    # Read "section" key, falling back to legacy "hatch" key in QSettings
    section = _s("section", None)
    if section is None:
        section = _s("hatch", cat_def.get("section"))
    section_pattern = _s("section_pattern", cat_def.get("section_pattern"))
    section_scale = float(_s("section_scale", 1.0))
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

    return {"color": color, "fill": fill, "section": section,
            "section_pattern": section_pattern, "section_scale": section_scale,
            "scale": scale, "opacity": opacity, "visible": visible,
            "font": font}


def _write_category_to_settings(key: str, vals: dict,
                                 settings: QSettings | None = None):
    """Write display settings for category *key* to QSettings."""
    if settings is None:
        settings = QSettings("GV", "FirePro3D")
    settings.setValue(f"display/{key}/color", vals["color"])
    settings.setValue(f"display/{key}/scale", vals["scale"])
    settings.setValue(f"display/{key}/opacity", vals["opacity"])
    settings.setValue(f"display/{key}/visible", str(vals["visible"]).lower())
    if vals.get("fill"):
        settings.setValue(f"display/{key}/fill", vals["fill"])
    if vals.get("section"):
        settings.setValue(f"display/{key}/section", vals["section"])
    if vals.get("section_pattern"):
        settings.setValue(f"display/{key}/section_pattern", vals["section_pattern"])
    if vals.get("section_scale") is not None:
        settings.setValue(f"display/{key}/section_scale", vals["section_scale"])
    if vals.get("font") is not None:
        settings.setValue(f"display/{key}/font", vals["font"])


def _apply_to_scene_items(scene, key: str, vals: dict,
                           respect_overrides: bool = True):
    """Apply display settings *vals* to all items of category *key*."""
    items = _items_for_category_static(scene, key)
    for obj in items:
        if respect_overrides:
            ov = getattr(obj, "_display_overrides", {})
            c = ov.get("color", vals["color"])
            s = ov.get("scale", vals["scale"])
            o = ov.get("opacity", vals["opacity"])
            v = ov.get("visible", vals["visible"])
            f = ov.get("fill", vals.get("fill"))
            fn = ov.get("font", vals.get("font"))
            sc = ov.get("section", vals.get("section"))
            sp = ov.get("section_pattern", vals.get("section_pattern"))
            ss = ov.get("section_scale", vals.get("section_scale"))
        else:
            c, s, o, v = vals["color"], vals["scale"], vals["opacity"], vals["visible"]
            f, fn = vals.get("fill"), vals.get("font")
            sc = vals.get("section")
            sp = vals.get("section_pattern")
            ss = vals.get("section_scale")
        apply_display_to_item(obj, c, s, o, v, fill_color=f, font_size=fn,
                              section_color=sc, section_pattern=sp,
                              section_scale=ss)


def _category_has_fill(key: str) -> bool:
    """Return True if this category supports a fill colour column."""
    c = _CATEGORY_MAP.get(key)
    return c is not None and c["fill"] is not None


def _category_has_section(key: str) -> bool:
    """Return True if this category supports a section colour column."""
    c = _CATEGORY_MAP.get(key)
    return c is not None and c.get("section") is not None


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
                          section_color: str | None = None,
                          section_pattern: str | None = None,
                          section_scale: float | None = None):
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
        if fill_color:
            mode, hex_col = _parse_fill_value(fill_color)
            item._display_fill_color = hex_col
            if mode == "hatch":
                item._fill_mode = "Section"
            else:
                item._fill_mode = "Solid"
        if section_color:
            item._display_section_color = section_color
        if section_pattern:
            item._display_section_pattern = section_pattern
        if section_scale is not None:
            item._display_section_scale = section_scale
        item.setVisible(visible)
        item.setOpacity(opacity / 100.0)
        item.update()
    elif isinstance(item, Room):
        item._display_color = color
        if fill_color:
            _, hex_col = _parse_fill_value(fill_color)
            item._display_fill_color = hex_col
        if color:
            item._label_font_color = color
        if font_size is not None:
            item._label_font_size = float(font_size) * 25.4  # inches → mm scene units
        item._update_label()
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
        _apply_geo2d(item, color, opacity, visible)
    elif isinstance(item, Node):
        _apply_node(item, color, scale, opacity, visible)
    else:
        # Generic items with _display_color/_display_fill_color (e.g. RoofItem, FloorSlab)
        if hasattr(item, '_display_color'):
            item._display_color = color
        if hasattr(item, '_display_fill_color') and fill_color is not None:
            _mode, _hex = _parse_fill_value(fill_color)
            item._display_fill_color = _hex
        if section_color and hasattr(item, '_display_section_color'):
            item._display_section_color = section_color
        if section_pattern and hasattr(item, '_display_section_pattern'):
            item._display_section_pattern = section_pattern
        if section_scale is not None and hasattr(item, '_display_section_scale'):
            item._display_section_scale = section_scale
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
    """Check if item is one of the 5 draw-geometry classes (avoids circular imports)."""
    return type(item).__name__ in (
        "LineItem", "PolylineItem", "RectangleItem", "CircleItem", "ArcItem"
    )


def _is_opening_item(item) -> bool:
    """Check if item is a WallOpening (avoids circular imports)."""
    return type(item).__name__ == "WallOpening"


def _apply_geo2d(item, color, opacity, visible):
    """Apply display settings to a 2D draw-geometry item (LineItem, PolylineItem, etc.).

    Stroke colour is stored in _display_color; the paint() methods read it and
    apply it to the pen before delegating to super().paint().  Fill colour is
    already handled by draw_fill() in each paint() via _display_fill_color.
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
    """Check if item is a ViewMarkerArrow without importing at module level."""
    return type(item).__name__ == "ViewMarkerArrow"


def _is_detail_marker(item) -> bool:
    """Check if item is a DetailMarker without importing at module level."""
    return type(item).__name__ == "DetailMarker"


def _is_floor_slab(item) -> bool:
    """Check if item is a FloorSlab without importing at module level."""
    return type(item).__name__ == "FloorSlab"


def _apply_elevation_marker(marker, color, scale, opacity, visible, fill_color,
                            font_size=None):
    """Apply display settings to a ViewMarkerArrow."""
    if color:
        marker._marker_color = QColor(color)
        pen = marker.pen()
        pen.setColor(QColor(color))
        marker.setPen(pen)
    if fill_color:
        marker._fill_color = QColor(fill_color)
        marker.setBrush(QBrush(QColor(fill_color)))
    if scale and scale != 1.0:
        marker.setScale(scale)
    elif scale == 1.0:
        marker.setScale(1.0)
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
        marker._tag_color = QColor(color)
        pen = marker.pen()
        pen.setColor(QColor(color))
        marker.setPen(pen)
    if fill_color:
        marker._fill_color = QColor(fill_color)
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
        gl._grid_color = QColor(color)
        # Preserve the bubble's original pen width, just change color
        for bubble in (gl.bubble1, gl.bubble2):
            bp = bubble.pen()
            bp.setColor(QColor(color))
            bubble.setPen(bp)
            bubble._label.setDefaultTextColor(QColor(color).lighter(150))
    if fill_color:
        gl.bubble1.setBrush(QBrush(QColor(fill_color)))
        gl.bubble2.setBrush(QBrush(QColor(fill_color)))
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
        key = "Opening"
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

    color = _v("color", cat_def["color"])
    scale = float(_v("scale", cat_def["scale"]))
    opacity = int(float(_v("opacity", cat_def["opacity"])))
    visible = _v("visible", cat_def["visible"])
    if isinstance(visible, str):
        visible = visible.lower() not in ("false", "0")
    fill = _v("fill", cat_def.get("fill"))
    font = cat_def.get("font")
    if font is not None:
        font = int(float(_v("font", font)))
    section = _v("section", cat_def.get("section"))
    section_pattern = _v("section_pattern", cat_def.get("section_pattern"))
    section_scale_raw = _v("section_scale", None)
    section_scale = float(section_scale_raw) if section_scale_raw else None

    apply_display_to_item(item, color, scale, opacity, visible,
                          fill_color=fill, font_size=font,
                          section_color=section,
                          section_pattern=section_pattern,
                          section_scale=section_scale)


# ──────────────────────────────────────────────────────────────────────────────
# Section-pattern picker dialog
# ──────────────────────────────────────────────────────────────────────────────

class SectionPatternDialog(QDialog):
    """Compact dialog for picking a section hatch colour + pattern."""

    def __init__(self, current_color: str, current_pattern: str,
                 current_scale: float = 1.0, parent=None):
        super().__init__(parent)
        from .hatch_patterns import PATTERN_NAMES
        self._pattern_names = PATTERN_NAMES

        self.setWindowTitle("Section Pattern")
        self.setFixedSize(280, 170)
        _t = th.detect()
        self.setStyleSheet(f"background: {_t.bg_raised}; color: {_t.text_primary};")

        lay = QVBoxLayout(self)

        # ── Pattern combo ──
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Pattern:"))
        self._combo = QComboBox()
        self._combo.addItems(self._pattern_names)
        idx = self._combo.findText(current_pattern)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        row1.addWidget(self._combo, 1)
        lay.addLayout(row1)

        # ── Colour button + preview ──
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Colour:"))
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(40, 20)
        self._cur_color = current_color or "#666666"
        self._color_btn.setStyleSheet(
            f"background: {self._cur_color}; border: 1px solid {_t.border_subtle}; "
            f"border-radius: 2px;")
        self._color_btn.clicked.connect(self._pick_color)
        row2.addWidget(self._color_btn)
        self._preview = QLabel()
        self._preview.setFixedSize(60, 20)
        row2.addWidget(self._preview)
        row2.addStretch()
        lay.addLayout(row2)

        # ── Scale spinbox ──
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Scale:"))
        self._scale_spin = QDoubleSpinBox()
        self._scale_spin.setRange(0.25, 4.0)
        self._scale_spin.setSingleStep(0.25)
        self._scale_spin.setDecimals(2)
        self._scale_spin.setValue(current_scale)
        self._scale_spin.setSuffix("x")
        self._scale_spin.setFixedHeight(22)
        row3.addWidget(self._scale_spin)
        row3.addStretch()
        lay.addLayout(row3)

        # ── Buttons ──
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        lay.addWidget(bbox)

        self._combo.currentTextChanged.connect(lambda _: self._refresh_preview())
        self._refresh_preview()

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._cur_color), self, "Section Colour")
        if color.isValid():
            self._cur_color = color.name()
            _t = th.detect()
            self._color_btn.setStyleSheet(
                f"background: {self._cur_color}; border: 1px solid {_t.border_subtle}; "
                f"border-radius: 2px;")
            self._refresh_preview()

    def _refresh_preview(self):
        pix = _make_fill_icon("hatch", self._cur_color, 60, 20,
                              pattern=self._combo.currentText())
        self._preview.setPixmap(pix)

    def get_result(self) -> tuple[str, str, float]:
        """Return (hex_color, pattern_name, scale)."""
        return self._cur_color, self._combo.currentText(), self._scale_spin.value()


# ──────────────────────────────────────────────────────────────────────────────
# DisplayManager dialog
# ──────────────────────────────────────────────────────────────────────────────

class DisplayManager(QDialog):
    """Modal dialog providing Revit-style display settings for fire-
    suppression model items."""

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
            self._elev_settings_snapshot[key] = snap

        # Underlay records (§16.6): deep-copy the DM-editable fields.
        # State lives on the records (not QSettings); Cancel restores the
        # field values IN PLACE (snap-index aliasing — see _restore_snapshot).
        self._underlay_snapshot = []
        for data, item in getattr(self._scene, "underlays", []):
            self._underlay_snapshot.append((data, {
                "colour": data.colour,
                "opacity": data.opacity,
                "visible": data.visible,
                "line_weight_name": data.line_weight_name,
                "hidden_layers": list(data.hidden_layers),
                "hidden_in_views": list(data.hidden_in_views),
                "layer_overrides": {k: dict(v)
                                    for k, v in data.layer_overrides.items()},
            }))

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

        # Force scene repaint
        self._scene.update()

        # Restore QSettings for elevation-only categories and rebuild
        if hasattr(self, "_elev_settings_snapshot"):
            for key, snap in self._elev_settings_snapshot.items():
                for prop, val in snap.items():
                    self._settings.setValue(f"display/{key}/{prop}", val)
            self._settings.sync()
            elev_mgr = getattr(self._scene, "_elevation_manager", None)
            if elev_mgr is not None and hasattr(elev_mgr, "rebuild_all"):
                elev_mgr.rebuild_all()

        # Restore underlay records (§16.6).  hidden_layers MUST be mutated
        # in place — UnderlaySnapIndex holds a reference to the same list
        # (underlay_snap_index.py); reassignment would break the aliasing.
        for data, snap in getattr(self, "_underlay_snapshot", []):
            data.colour = snap["colour"]
            data.opacity = snap["opacity"]
            data.visible = snap["visible"]
            data.line_weight_name = snap["line_weight_name"]
            data.hidden_layers[:] = snap["hidden_layers"]          # in place!
            data.hidden_in_views[:] = snap["hidden_in_views"]      # in place
            data.layer_overrides.clear()
            data.layer_overrides.update(
                {k: dict(v) for k, v in snap["layer_overrides"].items()})
        lm = getattr(self._scene, "_level_manager", None)
        underlays = getattr(self._scene, "underlays", [])
        for data, item in underlays:
            if hasattr(self._scene, "repen_underlay"):
                self._scene.repen_underlay(data)
            if item is not None:
                try:
                    hidden = set(data.hidden_layers)
                    for child in item.childItems():
                        ln = child.data(1)
                        if ln is not None:
                            child.setVisible(ln not in hidden)
                except RuntimeError:
                    pass
            if lm is None:
                self._apply_underlay_visibility(data, item)
        if lm is not None and underlays:
            lm.apply_to_scene(self._scene)      # one pass, not one per record
        if getattr(self, "_underlay_snapshot", None) and hasattr(
                self._scene, "underlaysChanged"):
            self._scene.underlaysChanged.emit()     # browser reverts too

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

        Returns a dict with keys: color, fill, scale, opacity, visible, font.
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
            color = (getattr(item, "_display_color", None)
                     or item.pen().color().name())
            fill = None
            font_val = item._properties.get(
                "Label Size", {}).get("value", 12)
            try:
                font = int(font_val)
            except (ValueError, TypeError):
                font = 12
        elif isinstance(item, Fitting):
            color = (getattr(item, "_display_color", None)
                     or cat_def["color"])
            fill = (getattr(item, "_display_fill_color", None)
                    or cat_def.get("fill"))
            font = None
        elif isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
            color = (getattr(item, "_display_color", None)
                     or cat_def["color"])
            fill = (getattr(item, "_display_fill_color", None)
                    or cat_def.get("fill"))
            font = None
        elif isinstance(item, WallSegment):
            color = (getattr(item, "_display_color", None)
                     or item._color.name())
            fill = (getattr(item, "_display_fill_color", None)
                    or cat_def.get("fill"))
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
            color = (getattr(item, "_display_color", None)
                     or getattr(item, "_color", cat_def["color"]))
            if isinstance(color, QColor):
                color = color.name()
            fill = (getattr(item, "_display_fill_color", None)
                    or cat_def.get("fill"))
            font = cat_def.get("font")

        # Section colour + pattern — read from item or fall back to category default
        section = (getattr(item, "_display_section_color", None)
                   or cat_def.get("section"))
        section_pattern = (getattr(item, "_display_section_pattern", None)
                           or cat_def.get("section_pattern"))

        section_scale = getattr(item, "_display_section_scale", 1.0) or 1.0

        return {
            "color": color,
            "fill": fill,
            "section": section,
            "section_pattern": section_pattern,
            "section_scale": section_scale,
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
        self._tree.setColumnCount(9)
        self._tree.setHeaderLabels(
            ["Name", "Vis", "Colour", "Fill", "Section", "Scale", "Opacity", "Font", ""])
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
        hdr.setSectionResizeMode(_COL_RESET, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(_COL_VIS, 40)
        self._tree.setColumnWidth(_COL_COLOR, 60)
        self._tree.setColumnWidth(_COL_FILL, 60)
        self._tree.setColumnWidth(_COL_SECTION, 60)
        self._tree.setColumnWidth(_COL_SCALE, 90)
        self._tree.setColumnWidth(_COL_OPACITY, 90)
        self._tree.setColumnWidth(_COL_FONT, 70)
        self._tree.setColumnWidth(_COL_RESET, 40)

        # Suppress preview signals during init so scene isn't changed.
        # Snapshot was already taken in __init__ before _build_ui().
        self._suppress = True
        self._populate_tree()
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
        self._underlays_tab = self._build_underlays_tab()
        self._tabs.addTab(self._underlays_tab, "Underlays")
        self._lw_tab = self._build_line_weights_tab()
        self._tabs.addTab(self._lw_tab, "Line Weights")

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
                saved_section = _first.get("section")
                saved_section_pattern = _first.get("section_pattern")
                saved_section_scale = _first.get("section_scale", 1.0)
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
                saved_section = (self._settings.value(f"display/{key}/section")
                                 or self._settings.value(
                                     f"display/{key}/hatch",
                                     cat_def.get("section")))
                saved_section_pattern = self._settings.value(
                    f"display/{key}/section_pattern",
                    cat_def.get("section_pattern"))
                saved_section_scale = float(self._settings.value(
                    f"display/{key}/section_scale", 1.0))

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
            cat_item.setText(_COL_NAME, f"{key}  ({count})")
            cat_item.setFont(_COL_NAME, bold)
            cat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

            cat_widgets = self._make_row_widgets(
                cat_item, saved_visible, saved_color, saved_fill,
                saved_scale, saved_opacity, saved_font,
                is_category=True, category_key=key,
                section=saved_section,
                section_pattern=saved_section_pattern,
                section_scale=saved_section_scale)

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
                inst_section = _ist.get("section")
                inst_section_pattern = _ist.get("section_pattern")
                inst_section_scale = _ist.get("section_scale", 1.0)

                child = QTreeWidgetItem(cat_item)
                child.setText(_COL_NAME, self._label_for_item(obj, i, key))
                child.setFlags(Qt.ItemFlag.ItemIsEnabled)

                inst_widgets = self._make_row_widgets(
                    child, inst_visible, inst_color, inst_fill,
                    inst_scale, inst_opacity, inst_font,
                    is_category=False, category_key=key,
                    item_ref=obj, section=inst_section,
                    section_pattern=inst_section_pattern,
                    section_scale=inst_section_scale)

                self._inst_data[id(obj)] = {
                    "tree_item": child,
                    "widgets": inst_widgets,
                    "item_ref": obj,
                    "category": key,
                }

    def _make_row_widgets(self, tree_item: QTreeWidgetItem,
                          visible: bool, color: str,
                          fill: str | None,
                          scale: float, opacity: int,
                          font: int | None = None, *,
                          is_category: bool,
                          category_key: str,
                          item_ref=None,
                          section: str | None = None,
                          section_pattern: str | None = None,
                          section_scale: float = 1.0) -> dict:
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
        color_btn.setStyleSheet(
            f"background: {color}; border: 1px solid {_t.border_subtle}; "
            f"border-radius: 2px;")
        self._tree.setItemWidget(tree_item, _COL_COLOR, color_btn)

        # ── Fill colour swatch (solid only — no hatch option) ────────
        fill_btn = QPushButton()
        fill_btn.setFixedSize(40, 20)
        if has_fill and fill:
            # Strip any legacy "hatch:" prefix — fill is now solid-only
            _, hex_col = _parse_fill_value(fill)
            fill_btn.setProperty("_color", hex_col)
            fill_btn.setStyleSheet(
                f"background: {hex_col}; border: 1px solid {_t.border_subtle}; "
                f"border-radius: 2px;")
        else:
            fill_btn.setProperty("_color", "")
            fill_btn.setStyleSheet(_disabled_ss)
            fill_btn.setEnabled(False)
        self._tree.setItemWidget(tree_item, _COL_FILL, fill_btn)

        # ── Section colour+pattern swatch (for sectioned geometry) ─────
        section_btn = QPushButton()
        section_btn.setFixedSize(40, 20)
        _sec_pat = section_pattern or "diagonal"
        if has_section and section:
            section_btn.setProperty("_color", section)
            section_btn.setProperty("_pattern", _sec_pat)
            section_btn.setProperty("_section_scale", section_scale)
            pix = _make_fill_icon("hatch", section, 40, 20, pattern=_sec_pat)
            section_btn.setIcon(QIcon(pix))
            section_btn.setIconSize(pix.size())
            section_btn.setStyleSheet(
                f"border: 1px solid {_t.border_subtle}; border-radius: 2px; "
                f"background: transparent;")
        else:
            section_btn.setProperty("_color", "")
            section_btn.setProperty("_pattern", "")
            section_btn.setStyleSheet(_disabled_ss)
            section_btn.setEnabled(False)
        self._tree.setItemWidget(tree_item, _COL_SECTION, section_btn)

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
                section_btn.clicked.connect(
                    lambda _, k=category_key: self._pick_category_prop(k, "section"))
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
                section_btn.clicked.connect(
                    lambda _, ref=item_ref: self._pick_instance_prop(ref, "section"))
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
            "section_btn": section_btn,
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
        """Open a colour/pattern dialog for *prop* ('color', 'fill', or 'section')
        on the category row and propagate to instances."""
        if prop == "section":
            return self._pick_section(category_key, is_category=True)
        btn_key = {"color": "color_btn", "fill": "fill_btn"}[prop]
        default = {"color": "#ffffff", "fill": "#000000"}[prop]
        widgets = self._cat_data[category_key]["widgets"]
        cur_hex = widgets[btn_key].property("_color") or default
        color = QColorDialog.getColor(QColor(cur_hex), self,
                                      f"{category_key} {prop}")
        if color.isValid():
            self._update_swatch(widgets[btn_key], prop, color.name())
            self._on_category_changed(category_key, prop, color.name())

    def _pick_instance_prop(self, item_ref, prop: str):
        """Open a colour/pattern dialog for *prop* on an instance row."""
        if prop == "section":
            return self._pick_section(item_ref, is_category=False)
        data = self._inst_data.get(id(item_ref))
        if data is None:
            return
        btn_key = {"color": "color_btn", "fill": "fill_btn"}[prop]
        default = {"color": "#ffffff", "fill": "#000000"}[prop]
        widgets = data["widgets"]
        cur_hex = widgets[btn_key].property("_color") or default
        color = QColorDialog.getColor(QColor(cur_hex), self,
                                      f"Instance {prop}")
        if color.isValid():
            self._update_swatch(widgets[btn_key], prop, color.name())
            self._on_instance_changed(item_ref, prop, color.name())

    def _pick_section(self, key_or_ref, *, is_category: bool):
        """Open the SectionPatternDialog for a category or instance row."""
        if is_category:
            widgets = self._cat_data[key_or_ref]["widgets"]
        else:
            data = self._inst_data.get(id(key_or_ref))
            if data is None:
                return
            widgets = data["widgets"]
        btn = widgets["section_btn"]
        cur_color = btn.property("_color") or "#666666"
        cur_pattern = btn.property("_pattern") or "diagonal"
        cur_scale = btn.property("_section_scale") or 1.0
        if isinstance(cur_scale, str):
            cur_scale = float(cur_scale or "1.0")
        dlg = SectionPatternDialog(cur_color, cur_pattern, cur_scale, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_color, new_pattern, new_scale = dlg.get_result()
            btn.setProperty("_pattern", new_pattern)
            btn.setProperty("_section_scale", new_scale)
            self._update_swatch(btn, "section", new_color, pattern=new_pattern)
            if is_category:
                self._on_category_changed(key_or_ref, "section", new_color)
                self._on_category_changed(key_or_ref, "section_pattern", new_pattern)
                self._on_category_changed(key_or_ref, "section_scale", new_scale)
            else:
                self._on_instance_changed(key_or_ref, "section", new_color)
                self._on_instance_changed(key_or_ref, "section_pattern", new_pattern)
                self._on_instance_changed(key_or_ref, "section_scale", new_scale)

    # ── Swatch update (replaces 3 specific update methods) ────────────

    def _update_swatch(self, btn: QPushButton, prop: str, hex_color: str,
                        pattern: str | None = None):
        """Update a swatch button for 'color', 'fill', or 'section'."""
        _t = th.detect()
        if prop == "section":
            btn.setProperty("_color", hex_color)
            if pattern:
                btn.setProperty("_pattern", pattern)
            pat = btn.property("_pattern") or "diagonal"
            pix = _make_fill_icon("hatch", hex_color, 40, 20, pattern=pat)
            btn.setIcon(QIcon(pix))
            btn.setIconSize(pix.size())
            btn.setText("")
            btn.setStyleSheet(
                f"border: 1px solid {_t.border_subtle}; border-radius: 2px; "
                f"background: transparent;")
        else:
            # color and fill are both solid swatches
            _, hex_col = _parse_fill_value(hex_color)
            btn.setProperty("_color", hex_col)
            btn.setIcon(QIcon())
            btn.setText("")
            btn.setStyleSheet(
                f"background: {hex_col}; border: 1px solid {_t.border_subtle}; "
                f"border-radius: 2px;")

    # Legacy aliases so existing internal calls still work
    _update_color_btn = lambda self, btn, v: self._update_swatch(btn, "color", v)
    _update_fill_btn  = lambda self, btn, v: self._update_swatch(btn, "fill", v)
    _update_section_btn = lambda self, btn, v: self._update_swatch(btn, "section", v)

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
                if fill_val:
                    self._update_fill_btn(w["fill_btn"], fill_val)
            if _category_has_section(cat_key):
                section_val = cat_widgets["section_btn"].property("_color")
                section_pat = cat_widgets["section_btn"].property("_pattern") or "diagonal"
                if section_val:
                    w["section_btn"].setProperty("_pattern", section_pat)
                    self._update_swatch(w["section_btn"], "section", section_val,
                                        pattern=section_pat)
            w["scale"].setValue(cat_widgets["scale"].value())
            w["opacity"].setValue(cat_widgets["opacity"].value())
            if _category_has_font(cat_key):
                w["font"].setValue(cat_widgets["font"].value())
        finally:
            self._suppress = False
        self._apply_preview()

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
        self._suppress = True
        try:
            for cat_def in _CATEGORIES:
                key = cat_def["key"]
                cw = self._cat_data[key]["widgets"]
                cw["vis"].setChecked(cat_def["visible"])
                self._update_color_btn(cw["color_btn"], cat_def["color"])
                if _category_has_fill(key) and cat_def["fill"]:
                    self._update_fill_btn(cw["fill_btn"], cat_def["fill"])
                if _category_has_section(key) and cat_def.get("section"):
                    cw["section_btn"].setProperty("_pattern", cat_def.get("section_pattern") or "diagonal")
                    self._update_swatch(cw["section_btn"], "section", cat_def["section"],
                                        pattern=cat_def.get("section_pattern"))
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
                        if _category_has_section(key) and cat_def.get("section"):
                            iw["section_btn"].setProperty("_pattern", cat_def.get("section_pattern") or "diagonal")
                            self._update_swatch(iw["section_btn"], "section", cat_def["section"],
                                                pattern=cat_def.get("section_pattern"))
                        iw["scale"].setValue(cat_def["scale"])
                        iw["opacity"].setValue(cat_def["opacity"])
                        if _category_has_font(key) and cat_def["font"] is not None:
                            iw["font"].setValue(cat_def["font"])
        finally:
            self._suppress = False
        self._apply_preview()

    def _reset_paper_space_tab(self):
        """Reset Paper Space tab to B&W factory defaults."""
        from .paper_display import (
            FACTORY_PAPER_CATEGORIES, save_paper_categories,
            PaperColorMode, save_paper_color_mode, _HAS_FILL, _HAS_SECTION,
        )
        save_paper_color_mode(PaperColorMode.BW, self._settings)
        save_paper_categories(FACTORY_PAPER_CATEGORIES, self._settings)
        self._suppress = True
        self._color_mode_combo.setCurrentIndex(1)  # B&W
        for key, widgets in self._paper_cat_data.items():
            factory = FACTORY_PAPER_CATEGORIES[key]
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
            if key == "Grid Line":
                widgets["bubble_ht"].set_value_mm(
                    factory["bubble_label_height_mm"])
        self._suppress = False
        self._apply_color_mode_ui(PaperColorMode.BW)
        self._apply_paper_preview()

    def _reset_line_weights_tab(self):
        """Reset Line Weights tab to factory defaults."""
        from .paper_display import FACTORY_LINE_WEIGHTS, save_line_weights, LineWeightDef
        self._lw_defs = [LineWeightDef(d.name, d.width_mm)
                         for d in FACTORY_LINE_WEIGHTS]
        save_line_weights(self._lw_defs, self._settings)
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
            self._settings.sync()  # line weights already in QSettings

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
            if s.get("fill"):
                self._settings.setValue(f"display/{key}/default_fill", s["fill"])
            if s.get("section"):
                self._settings.setValue(f"display/{key}/default_section", s["section"])
            if s.get("section_pattern"):
                self._settings.setValue(f"display/{key}/default_section_pattern", s["section_pattern"])
            if s.get("section_scale") is not None:
                self._settings.setValue(f"display/{key}/default_section_scale", s["section_scale"])
            if s.get("font") is not None:
                self._settings.setValue(f"display/{key}/default_font", s["font"])
            # Also save as current settings so they persist across sessions
            self._settings.setValue(f"display/{key}/color", s["color"])
            self._settings.setValue(f"display/{key}/scale", s["scale"])
            self._settings.setValue(f"display/{key}/opacity", s["opacity"])
            self._settings.setValue(f"display/{key}/visible", s["visible"])
            if s.get("fill"):
                self._settings.setValue(f"display/{key}/fill", s["fill"])
            if s.get("section"):
                self._settings.setValue(f"display/{key}/section", s["section"])
            if s.get("section_pattern"):
                self._settings.setValue(f"display/{key}/section_pattern", s["section_pattern"])
            if s.get("section_scale") is not None:
                self._settings.setValue(f"display/{key}/section_scale", s["section_scale"])
            if s.get("font") is not None:
                self._settings.setValue(f"display/{key}/font", s["font"])
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
            if widgets["fill_btn"].isEnabled() and value:
                self._update_fill_btn(widgets["fill_btn"], value)
        elif prop == "section":
            if widgets["section_btn"].isEnabled() and value:
                self._update_swatch(widgets["section_btn"], "section", value)
        elif prop == "section_pattern":
            if widgets["section_btn"].isEnabled() and value:
                widgets["section_btn"].setProperty("_pattern", value)
                cur_col = widgets["section_btn"].property("_color") or "#666666"
                self._update_swatch(widgets["section_btn"], "section", cur_col,
                                    pattern=value)
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
            result["fill"] = w["fill_btn"].property("_color") or None
        else:
            result["fill"] = None
        if _category_has_section(key):
            result["section"] = w["section_btn"].property("_color") or None
            result["section_pattern"] = w["section_btn"].property("_pattern") or "diagonal"
            _ss = w["section_btn"].property("_section_scale")
            result["section_scale"] = float(_ss) if _ss else 1.0
        else:
            result["section"] = None
            result["section_pattern"] = None
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

            for obj in self._cat_data[key]["items"]:
                overrides = getattr(obj, "_display_overrides", {})
                eff_color = overrides.get("color", cat_settings["color"])
                eff_scale = overrides.get("scale", cat_settings["scale"])
                eff_opacity = overrides.get("opacity", cat_settings["opacity"])
                eff_visible = overrides.get("visible", cat_settings["visible"])
                eff_fill = overrides.get("fill", cat_settings.get("fill"))
                eff_font = overrides.get("font", cat_settings.get("font"))
                eff_section = overrides.get("section", cat_settings.get("section"))
                eff_sec_pat = overrides.get("section_pattern",
                                            cat_settings.get("section_pattern"))
                eff_sec_scl = overrides.get("section_scale",
                                            cat_settings.get("section_scale"))

                apply_display_to_item(obj, eff_color, eff_scale,
                                      eff_opacity, eff_visible,
                                      fill_color=eff_fill,
                                      font_size=eff_font,
                                      section_color=eff_section,
                                      section_pattern=eff_sec_pat,
                                      section_scale=eff_sec_scl)

            # Sync elevation-related categories to QSettings so elevation
            # scene rebuilds pick up changes during live preview.
            if key in self._ELEV_CATEGORIES:
                self._settings.setValue(f"display/{key}/color", cat_settings["color"])
                self._settings.setValue(f"display/{key}/scale", cat_settings["scale"])
                self._settings.setValue(f"display/{key}/opacity", cat_settings["opacity"])
                self._settings.setValue(f"display/{key}/visible", cat_settings["visible"])
                if cat_settings.get("fill"):
                    self._settings.setValue(f"display/{key}/fill", cat_settings["fill"])
                if cat_settings.get("section"):
                    self._settings.setValue(f"display/{key}/section", cat_settings["section"])
                if cat_settings.get("section_pattern"):
                    self._settings.setValue(f"display/{key}/section_pattern", cat_settings["section_pattern"])
                if cat_settings.get("section_scale") is not None:
                    self._settings.setValue(f"display/{key}/section_scale", cat_settings["section_scale"])
                if cat_settings.get("font") is not None:
                    self._settings.setValue(f"display/{key}/font", cat_settings["font"])
                elev_dirty = True

        self._scene.update()

        # Rebuild open elevation views so changes are visible immediately
        if elev_dirty:
            self._settings.sync()
            elev_mgr = getattr(self._scene, "_elevation_manager", None)
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
    _PS_COL_LABEL_HT = 7

    # Underlays tab columns (§16.6)
    _UL_COL_NAME    = 0
    _UL_COL_VIS     = 1
    _UL_COL_COLOR   = 2
    _UL_COL_OPACITY = 3
    _UL_COL_LW      = 4
    _UL_COL_VIEWS   = 5
    _UL_COL_RESET   = 6

    # Paper-space category groups
    _PS_GROUPS = {
        "Fire Suppression": [
            "Pipe", "Sprinkler", "Fitting", "Water Supply", "Node",
            "Hydraulic Badge",
        ],
        "Architecture": ["Wall", "Roof", "Room", "Floor"],
        "Grids & Levels": [
            "Grid Line", "Level Datum", "Elevation Marker", "Detail Marker",
        ],
    }

    def _build_paper_space_tab(self) -> QWidget:
        """Build the Paper Space display overrides tab."""
        from .paper_display import (
            load_line_weights, load_paper_categories, load_paper_color_mode,
            save_paper_categories, save_paper_color_mode,
            PaperColorMode, _HAS_FILL, _HAS_SECTION, _CATEGORY_KEYS,
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
        self._ps_tree.setColumnCount(8)
        self._ps_tree.setHeaderLabels(
            ["Name", "Vis", "Colour", "Fill", "Section", "Line Weight",
             "Opacity", "Label Ht"])
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
        hdr.setSectionResizeMode(self._PS_COL_LABEL_HT,
                                 QHeaderView.ResizeMode.Fixed)
        self._ps_tree.setColumnWidth(self._PS_COL_LABEL_HT, 90)

        # Load data
        cats = load_paper_categories(self._settings)
        lw_defs = load_line_weights(self._settings)
        lw_names = [d.name for d in lw_defs]

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
                tree_item.setText(self._PS_COL_NAME, key)
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
                color_btn.setStyleSheet(
                    f"background: {color_val}; "
                    f"border: 1px solid {_t.border_subtle}; "
                    f"border-radius: 2px;")
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
                    fill_btn.setStyleSheet(
                        f"background: {fill_val}; "
                        f"border: 1px solid {_t.border_subtle}; "
                        f"border-radius: 2px;")
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
                    section_btn.setStyleSheet(
                        f"background: {sec_val}; "
                        f"border: 1px solid {_t.border_subtle}; "
                        f"border-radius: 2px;")
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
                cur_lw = cat.get("line_weight", "Medium")
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

                # ── Bubble label height (Grid Line only) ─────────────
                if key == "Grid Line":
                    from .dimension_edit import DimensionEdit
                    ht_edit = DimensionEdit(
                        getattr(self._scene, "scale_manager", None),
                        initial_mm=cat.get("bubble_label_height_mm", 3.0),
                        minimum=0.5)
                    ht_edit.setFixedHeight(22)
                    ht_edit.editingFinished.connect(
                        self._on_paper_bubble_ht_changed)
                else:
                    ht_edit = QLineEdit()
                    ht_edit.setStyleSheet(_disabled_ss)
                    ht_edit.setEnabled(False)
                self._ps_tree.setItemWidget(tree_item, self._PS_COL_LABEL_HT,
                                            ht_edit)

                self._paper_cat_data[key] = {
                    "tree_item": tree_item,
                    "vis": vis_cb,
                    "color_btn": color_btn,
                    "fill_btn": fill_btn,
                    "section_btn": section_btn,
                    "lw_combo": lw_combo,
                    "opacity": opacity_spin,
                    "bubble_ht": ht_edit,
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
            _HAS_FILL, _HAS_SECTION,
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
        from .paper_display import PaperColorMode, _HAS_FILL, _HAS_SECTION
        disable = (mode == PaperColorMode.FULL_COLOR)
        for key, widgets in self._paper_cat_data.items():
            widgets["color_btn"].setEnabled(not disable)
            if key in _HAS_FILL:
                widgets["fill_btn"].setEnabled(not disable)
            if key in _HAS_SECTION:
                widgets["section_btn"].setEnabled(not disable)

    def _on_paper_color_clicked(self, key: str, prop: str):
        """Open QColorDialog for a paper-space category colour property."""
        from .paper_display import (
            PaperColorMode, save_paper_color_mode, load_paper_color_mode,
            load_paper_categories, save_paper_categories,
        )
        widgets = self._paper_cat_data[key]
        btn_key = {"color": "color_btn", "fill": "fill_btn",
                   "section_color": "section_btn"}[prop]
        btn = widgets[btn_key]
        cur_hex = btn.property("_color") or "#000000"
        color = QColorDialog.getColor(QColor(cur_hex), self,
                                      f"{key} {prop}")
        if not color.isValid():
            return

        hex_val = color.name()
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

    def _on_paper_bubble_ht_changed(self):
        """Bubble label height DimensionEdit committed for Grid Line."""
        if self._suppress:
            return
        from .paper_display import load_paper_categories, save_paper_categories
        edit = self._paper_cat_data["Grid Line"]["bubble_ht"]
        cats = load_paper_categories(self._settings)
        cats["Grid Line"]["bubble_label_height_mm"] = edit.value_mm()
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
    # Underlays tab (§16.6) — per-instance rows; state lives on the
    # Underlay records, live-apply through the scene choke points
    # (repen_underlay / set_underlay_layer_hidden). No QSettings cascade.
    # ------------------------------------------------------------------

    @staticmethod
    def _ul_lw_combo_items(sentinel: str, lw_names: list[str],
                           current: str | None) -> list[str]:
        """Combo item list: sentinel + defined weights (+ stale *current*).

        A name still referenced by the record but absent from the weight
        defs (legacy/hand-edited files — the Line Weights tab's in-use
        guard prevents new ones) is appended so it displays truthfully
        instead of silently falling back to the sentinel (setCurrentText
        no-ops on non-editable combos).
        """
        items = [sentinel] + list(lw_names)
        if current and current not in lw_names:
            items.append(current)
        return items

    def _build_underlays_tab(self) -> QWidget:
        """Build the per-underlay / per-layer appearance tab."""
        from .paper_display import load_line_weights
        _t = th.detect()

        page = QWidget()
        layout = QVBoxLayout(page)

        self._underlay_tree = QTreeWidget()
        tree = self._underlay_tree
        tree.setColumnCount(7)
        tree.setHeaderLabels(
            ["Underlay / Layer", "Vis", "Colour", "Opacity", "Line Weight",
             "Views", ""])
        tree.setRootIsDecorated(True)
        tree.setIndentation(20)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hdr = tree.header()
        hdr.setSectionResizeMode(self._UL_COL_NAME,
                                 QHeaderView.ResizeMode.Stretch)
        for col, width in ((self._UL_COL_VIS, 40),
                           (self._UL_COL_COLOR, 60),
                           (self._UL_COL_OPACITY, 90),
                           (self._UL_COL_LW, 100),
                           (self._UL_COL_VIEWS, 70),
                           (self._UL_COL_RESET, 40)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            tree.setColumnWidth(col, width)

        lw_defs = load_line_weights(self._settings)
        lw_names = [d.name for d in lw_defs]

        bold = QFont()
        bold.setBold(True)

        self._suppress = True
        for idx, (data, item) in enumerate(
                getattr(self._scene, "underlays", [])):
            self._add_underlay_row(idx, data, item, lw_names, bold, _t)
        self._suppress = False

        tree.expandAll()
        layout.addWidget(tree)
        return page

    def _add_underlay_row(self, idx, data, item, lw_names, bold, _t):
        """One top-level file row (+ per-layer children for dxf/dwg)."""
        tree = self._underlay_tree
        # Missing-file detection — same check as model_browser (§16.6:
        # missing rows stay editable, widgets enabled).
        is_missing = item is None or item.data(0) == "missing_underlay"
        level_label = "All Levels" if data.level == "*" else data.level
        label = f"{os.path.basename(data.path)}  [{level_label}]"
        if is_missing:
            label += "  (missing)"

        file_row = QTreeWidgetItem(tree)
        file_row.setText(self._UL_COL_NAME, label)
        file_row.setFont(self._UL_COL_NAME, bold)
        file_row.setFlags(Qt.ItemFlag.ItemIsEnabled)
        file_row.setData(0, Qt.ItemDataRole.UserRole, idx)

        # Vector-vs-raster: vector groups have data(1)-tagged path children;
        # raster PDFs are a bare pixmap item (no such children).
        has_layer_children = False
        if item is not None and not is_missing:
            try:
                has_layer_children = any(
                    c.data(1) is not None for c in item.childItems())
            except (RuntimeError, AttributeError):
                has_layer_children = False
        # dxf/dwg always get colour/weight (even when missing);
        # PDFs only when the loaded item proves it is a vector group.
        has_pens = data.type in ("dxf", "dwg") or has_layer_children

        # ── Visibility checkbox (all types) ──────────────────────────
        vis_cb = QCheckBox()
        vis_cb.setChecked(data.visible)
        vis_cb.toggled.connect(
            lambda v, d=data, it=item: self._on_ul_vis_toggled(d, it, v))
        tree.setItemWidget(file_row, self._UL_COL_VIS, vis_cb)

        # ── Uniform colour swatch (vector only) ──────────────────────
        if has_pens:
            color_btn = QPushButton()
            color_btn.setFixedSize(40, 20)
            color_btn.setProperty("_color", data.colour)
            color_btn.setStyleSheet(
                f"background: {data.colour}; "
                f"border: 1px solid {_t.border_subtle}; "
                f"border-radius: 2px;")
            color_btn.clicked.connect(
                lambda _, d=data, b=color_btn, r=file_row:
                self._on_ul_colour_clicked(d, b, r))
            tree.setItemWidget(file_row, self._UL_COL_COLOR, color_btn)

        # ── Opacity spinbox (all types) ──────────────────────────────
        opacity_spin = QSpinBox()
        opacity_spin.setRange(0, 100)
        opacity_spin.setSingleStep(5)
        opacity_spin.setValue(int(round(data.opacity * 100)))
        opacity_spin.setSuffix("%")
        opacity_spin.setFixedHeight(22)
        opacity_spin.valueChanged.connect(
            lambda v, d=data: self._on_ul_opacity_changed(d, v))
        tree.setItemWidget(file_row, self._UL_COL_OPACITY, opacity_spin)

        # ── Line-weight combo (vector only) ──────────────────────────
        if has_pens:
            lw_combo = QComboBox()
            lw_combo.addItems(self._ul_lw_combo_items(
                "(none)", lw_names, data.line_weight_name))
            lw_combo.setCurrentText(data.line_weight_name or "(none)")
            lw_combo.currentTextChanged.connect(
                lambda t, d=data: self._on_ul_lw_changed(d, t))
            tree.setItemWidget(file_row, self._UL_COL_LW, lw_combo)

        # ── Views… button (all types) ────────────────────────────────
        views_btn = QPushButton("Views…")
        views_btn.setFixedHeight(22)
        views_btn.clicked.connect(
            lambda _, d=data: self._build_views_menu(d).exec(QCursor.pos()))
        tree.setItemWidget(file_row, self._UL_COL_VIEWS, views_btn)

        # ── Per-layer child rows (dxf/dwg with a live group only) ────
        if (data.type in ("dxf", "dwg") and item is not None
                and not is_missing):
            # data(2) = sorted layer list (set by the import wrappers —
            # same source the browser uses); fall back to the children's
            # data(1) layer tags for groups built outside the importers.
            layers = item.data(2)
            if not layers and has_layer_children:
                layers = sorted({c.data(1) for c in item.childItems()
                                 if c.data(1) is not None})
            for layer_name in (layers or []):
                self._add_underlay_layer_row(
                    file_row, data, item, layer_name, lw_names, _t)

    def _add_underlay_layer_row(self, file_row, data, item, layer_name,
                                lw_names, _t):
        """One per-layer child row: vis / colour override / weight / reset."""
        tree = self._underlay_tree
        row = QTreeWidgetItem(file_row)
        row.setText(self._UL_COL_NAME, layer_name)
        row.setFlags(Qt.ItemFlag.ItemIsEnabled)
        row.setData(0, Qt.ItemDataRole.UserRole, layer_name)

        # Vis — MUST route through the scene choke point so
        # underlaysChanged fires and the browser tree stays in sync.
        vis_cb = QCheckBox()
        vis_cb.setChecked(layer_name not in data.hidden_layers)
        vis_cb.toggled.connect(
            lambda v, d=data, it=item, ln=layer_name:
            self._on_ul_layer_vis_toggled(d, it, ln, v))
        tree.setItemWidget(row, self._UL_COL_VIS, vis_cb)

        # Colour — shows the effective (override → uniform) colour.
        colour = data.effective_layer_colour(layer_name)
        color_btn = QPushButton()
        color_btn.setFixedSize(40, 20)
        color_btn.setProperty("_color", colour)
        color_btn.setStyleSheet(
            f"background: {colour}; "
            f"border: 1px solid {_t.border_subtle}; "
            f"border-radius: 2px;")
        color_btn.clicked.connect(
            lambda _, d=data, ln=layer_name, b=color_btn:
            self._on_ul_layer_colour_clicked(d, ln, b))
        tree.setItemWidget(row, self._UL_COL_COLOR, color_btn)

        # Weight — "(inherit)" = no per-layer override.
        lw_combo = QComboBox()
        cur = data.layer_overrides.get(layer_name, {}).get("line_weight")
        lw_combo.addItems(self._ul_lw_combo_items("(inherit)", lw_names, cur))
        lw_combo.setCurrentText(cur if cur else "(inherit)")
        lw_combo.currentTextChanged.connect(
            lambda t, d=data, ln=layer_name:
            self._on_ul_layer_lw_changed(d, ln, t))
        tree.setItemWidget(row, self._UL_COL_LW, lw_combo)

        # Reset ↺ — drop all overrides for this layer.
        reset_btn = QPushButton("↺")
        reset_btn.setFixedSize(28, 20)
        reset_btn.setToolTip("Reset layer to underlay defaults")
        reset_btn.clicked.connect(
            lambda _, d=data, ln=layer_name, b=color_btn, c=lw_combo:
            self._on_ul_layer_reset(d, ln, b, c))
        tree.setItemWidget(row, self._UL_COL_RESET, reset_btn)

    # ── Underlays tab event handlers ─────────────────────────────────

    def _build_views_menu(self, record) -> QMenu:
        """Checkable plan+detail view list; checked = visible (§16.6).

        View keys match ``scene.active_view_key`` ("plan:Plan: <level>" /
        "detail:<name>"); managers are injected on the scene by main.py.
        """
        menu = QMenu(self)
        entries: list[tuple[str, str]] = []      # (label, view_key)
        pvm = getattr(self._scene, "_plan_view_manager", None)
        if pvm is not None:
            for name in pvm._views.keys():        # "Plan: Level 1"
                entries.append((name, f"plan:{name}"))
        dm = getattr(self._scene, "_detail_manager", None)
        if dm is not None:
            for name in dm.detail_names:
                entries.append((f"Detail: {name}", f"detail:{name}"))
        for label, key in entries:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(key not in record.hidden_in_views)
            act.toggled.connect(
                lambda checked, k=key, r=record: self._set_view_visible(
                    r, k, checked))
        return menu

    def _set_view_visible(self, record, view_key: str, visible: bool):
        if visible:
            if view_key in record.hidden_in_views:
                record.hidden_in_views.remove(view_key)
        elif view_key not in record.hidden_in_views:
            record.hidden_in_views.append(view_key)
        # Re-apply for the CURRENT view (record ↔ item lookup by identity)
        for data, item in getattr(self._scene, "underlays", []):
            if data is record:
                self._apply_underlay_visibility(data, item)
                break

    def _apply_underlay_visibility(self, data, item):
        """Re-run the level pass if reachable, else toggle the item directly.

        The fallback mirrors the real pass semantics (visible flag AND
        active-view exclusion — level_manager.apply_to_scene underlay
        stage); level filtering can't be evaluated without the manager.
        """
        lm = getattr(self._scene, "_level_manager", None)
        if lm is not None:
            lm.apply_to_scene(self._scene)
        elif item is not None:
            visible = data.visible and (
                getattr(self._scene, "active_view_key", "")
                not in data.hidden_in_views)
            try:
                item.setVisible(visible)
            except RuntimeError:
                pass

    def _on_ul_vis_toggled(self, data, item, checked: bool):
        if self._suppress:
            return
        data.visible = checked
        self._apply_underlay_visibility(data, item)
        # Browser file checkbox reflects data.visible — keep it in sync
        # (layer toggles already emit via set_underlay_layer_hidden).
        if hasattr(self._scene, "underlaysChanged"):
            self._scene.underlaysChanged.emit()

    def _on_ul_colour_clicked(self, data, btn, file_row):
        if self._suppress:
            return
        cur_hex = btn.property("_color") or data.colour
        color = QColorDialog.getColor(QColor(cur_hex), self,
                                      "Underlay Colour")
        if not color.isValid():
            return
        hex_val = color.name()
        data.colour = hex_val
        self._update_color_btn(btn, hex_val)
        self._scene.repen_underlay(data)
        # Refresh swatches of layers inheriting the uniform colour.
        tree = self._underlay_tree
        for i in range(file_row.childCount()):
            child = file_row.child(i)
            ln = child.data(0, Qt.ItemDataRole.UserRole)
            if data.layer_overrides.get(ln, {}).get("colour"):
                continue
            layer_btn = tree.itemWidget(child, self._UL_COL_COLOR)
            if layer_btn is not None:
                self._update_color_btn(layer_btn, hex_val)

    def _on_ul_opacity_changed(self, data, value: int):
        if self._suppress:
            return
        data.opacity = value / 100.0
        self._scene.repen_underlay(data)

    def _on_ul_lw_changed(self, data, text: str):
        if self._suppress:
            return
        data.line_weight_name = "" if text == "(none)" else text
        self._scene.repen_underlay(data)

    def _on_ul_layer_vis_toggled(self, data, item, layer_name, checked: bool):
        if self._suppress:
            return
        self._scene.set_underlay_layer_hidden(data, item, layer_name,
                                              not checked)

    def _on_ul_layer_colour_clicked(self, data, layer_name, btn):
        if self._suppress:
            return
        cur_hex = btn.property("_color") or data.effective_layer_colour(
            layer_name)
        color = QColorDialog.getColor(QColor(cur_hex), self,
                                      f"{layer_name} Colour")
        if not color.isValid():
            return
        hex_val = color.name()
        data.layer_overrides.setdefault(layer_name, {})["colour"] = hex_val
        self._update_color_btn(btn, hex_val)
        self._scene.repen_underlay(data)

    def _on_ul_layer_lw_changed(self, data, layer_name, text: str):
        if self._suppress:
            return
        if text == "(inherit)":
            ov = data.layer_overrides.get(layer_name)
            if ov is not None:
                ov.pop("line_weight", None)
                if not ov:
                    data.layer_overrides.pop(layer_name, None)
        else:
            data.layer_overrides.setdefault(
                layer_name, {})["line_weight"] = text
        self._scene.repen_underlay(data)

    def _on_ul_layer_reset(self, data, layer_name, color_btn, lw_combo):
        if self._suppress:
            return
        data.layer_overrides.pop(layer_name, None)
        self._scene.repen_underlay(data)
        # Refresh row widgets to the inherited values (suppressed —
        # the scene state is already correct).
        self._suppress = True
        try:
            self._update_color_btn(color_btn,
                                   data.effective_layer_colour(layer_name))
            lw_combo.setCurrentText("(inherit)")
        finally:
            self._suppress = False

    # ------------------------------------------------------------------
    # Line Weights tab
    # ------------------------------------------------------------------

    def _build_line_weights_tab(self) -> QWidget:
        """Build the Line Weights definition tab."""
        from .paper_display import (
            load_line_weights, save_line_weights, LineWeightDef,
            FACTORY_LINE_WEIGHTS, validate_line_weight_name,
            validate_line_weight_width, load_paper_categories,
        )
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

        page = QWidget()
        layout = QVBoxLayout(page)

        self._lw_table = QTableWidget()
        self._lw_table.setColumnCount(2)
        self._lw_table.setHorizontalHeaderLabels(["Name", "Width (mm)"])
        self._lw_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._lw_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Fixed)
        self._lw_table.setColumnWidth(1, 120)
        self._lw_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self._lw_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)

        self._lw_defs = load_line_weights(self._settings)
        self._lw_snapshot = [LineWeightDef(d.name, d.width_mm)
                             for d in self._lw_defs]
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
        self._suppress = True
        self._lw_defs.sort(key=lambda d: d.width_mm)
        self._lw_table.setRowCount(len(self._lw_defs))
        for row, lw in enumerate(self._lw_defs):
            from PyQt6.QtWidgets import QTableWidgetItem
            name_item = QTableWidgetItem(lw.name)
            width_item = QTableWidgetItem(f"{lw.width_mm:.2f}")
            self._lw_table.setItem(row, 0, name_item)
            self._lw_table.setItem(row, 1, width_item)
        self._suppress = False

    def _line_weight_in_use(self, name: str) -> bool:
        """True if *name* is referenced by a paper category or an underlay.

        Underlay references (§16.6): the per-underlay default
        ``line_weight_name`` and per-layer
        ``layer_overrides[layer]["line_weight"]``.
        """
        from .paper_display import load_paper_categories
        cats = load_paper_categories(self._settings)
        if any(v.get("line_weight") == name for v in cats.values()):
            return True
        for data, _item in getattr(self._scene, "underlays", []):
            if data.line_weight_name == name:
                return True
            for ov in data.layer_overrides.values():
                if ov.get("line_weight") == name:
                    return True
        return False

    def _propagate_lw_rename(self, old: str, new: str):
        """Follow a weight rename through every by-name reference."""
        from .paper_display import load_paper_categories, save_paper_categories
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

    def _on_lw_cell_changed(self, row, col):
        if self._suppress or row >= len(self._lw_defs):
            return
        from .paper_display import (
            validate_line_weight_name, validate_line_weight_width,
            save_line_weights,
        )
        old_def = self._lw_defs[row]
        text = self._lw_table.item(row, col).text().strip()
        if col == 0:  # Name changed
            others = [d for i, d in enumerate(self._lw_defs) if i != row]
            if not validate_line_weight_name(text, others):
                self._suppress = True
                self._lw_table.item(row, 0).setText(old_def.name)
                self._suppress = False
                return
            old_name = old_def.name
            old_def.name = text
            self._propagate_lw_rename(old_name, text)
        else:  # Width changed
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
        save_line_weights(self._lw_defs, self._settings)
        self._populate_lw_table()
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()

    def _on_lw_add(self):
        from .paper_display import save_line_weights, LineWeightDef
        idx = len(self._lw_defs) + 1
        name = f"Custom {idx}"
        while any(d.name == name for d in self._lw_defs):
            idx += 1
            name = f"Custom {idx}"
        self._lw_defs.append(LineWeightDef(name, 0.20))
        save_line_weights(self._lw_defs, self._settings)
        self._populate_lw_table()
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()

    def _on_lw_remove(self):
        from .paper_display import save_line_weights
        row = self._lw_table.currentRow()
        if row < 0 or row >= len(self._lw_defs):
            return
        if self._line_weight_in_use(self._lw_defs[row].name):
            return
        self._lw_defs.pop(row)
        save_line_weights(self._lw_defs, self._settings)
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
        from .paper_display import load_line_weights, load_paper_categories
        lw_defs = load_line_weights(self._settings)
        lw_names = [d.name for d in lw_defs]
        cats = load_paper_categories(self._settings)
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
                cat_lw = cats[key].get("line_weight", "Medium")
                idx = combo.findText(cat_lw)
                combo.setCurrentIndex(max(0, idx))
        # Underlays-tab combos (paper-tab parity): rebuild from the records —
        # rename propagation has already updated them, so re-seating from
        # record state shows the new name live.
        tree = getattr(self, "_underlay_tree", None)
        if tree is not None:
            underlays = getattr(self._scene, "underlays", [])
            for i in range(tree.topLevelItemCount()):
                file_row = tree.topLevelItem(i)
                idx = file_row.data(0, Qt.ItemDataRole.UserRole)
                if idx is None or idx >= len(underlays):
                    continue
                data = underlays[idx][0]
                combo = tree.itemWidget(file_row, self._UL_COL_LW)
                if combo is not None:
                    cur = data.line_weight_name
                    combo.clear()
                    combo.addItems(self._ul_lw_combo_items(
                        "(none)", lw_names, cur))
                    combo.setCurrentText(cur or "(none)")
                for j in range(file_row.childCount()):
                    layer_row = file_row.child(j)
                    combo = tree.itemWidget(layer_row, self._UL_COL_LW)
                    if combo is None:
                        continue
                    layer_name = layer_row.data(0, Qt.ItemDataRole.UserRole)
                    cur = data.layer_overrides.get(
                        layer_name, {}).get("line_weight")
                    combo.clear()
                    combo.addItems(self._ul_lw_combo_items(
                        "(inherit)", lw_names, cur))
                    combo.setCurrentText(cur if cur else "(inherit)")
        self._suppress = False

    # ------------------------------------------------------------------
    # Accept / Reject
    # ------------------------------------------------------------------

    def accept(self):
        """Persist category settings to QSettings and keep scene state."""
        for cat_def in _CATEGORIES:
            key = cat_def["key"]
            s = self._read_category_settings(key)
            self._settings.setValue(f"display/{key}/color", s["color"])
            self._settings.setValue(f"display/{key}/scale", s["scale"])
            self._settings.setValue(f"display/{key}/opacity", s["opacity"])
            self._settings.setValue(f"display/{key}/visible", s["visible"])
            if s.get("fill"):
                self._settings.setValue(f"display/{key}/fill", s["fill"])
            if s.get("section"):
                self._settings.setValue(f"display/{key}/section", s["section"])
            if s.get("section_pattern"):
                self._settings.setValue(f"display/{key}/section_pattern", s["section_pattern"])
            if s.get("section_scale") is not None:
                self._settings.setValue(f"display/{key}/section_scale", s["section_scale"])
            if s.get("font") is not None:
                self._settings.setValue(f"display/{key}/font", s["font"])
        self._settings.sync()

        # Rebuild open elevation views so Level Datum / Grid Line / Elevation
        # Marker changes take effect immediately.
        elev_mgr = getattr(self._scene, "_elevation_manager", None)
        if elev_mgr is not None and hasattr(elev_mgr, "rebuild_all"):
            elev_mgr.rebuild_all()

        super().accept()

    def reject(self):
        """Cancel — revert all changes."""
        self._restore_snapshot()
        if hasattr(self, "_paper_settings_snapshot"):
            from .paper_display import (
                save_paper_categories, save_paper_color_mode, PaperColorMode,
                save_line_weights,
            )
            save_paper_categories(self._paper_settings_snapshot["categories"],
                                  self._settings)
            save_paper_color_mode(
                PaperColorMode(self._paper_settings_snapshot["color_mode"]),
                self._settings)
        if hasattr(self, "_lw_snapshot"):
            from .paper_display import save_line_weights
            save_line_weights(self._lw_snapshot, self._settings)
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
    for cat_def in _CATEGORIES:
        key = cat_def["key"]
        # Build overrides from default_* keys so they win over current keys
        default_ov: dict = {}
        for prop in ("color", "fill", "section", "section_pattern",
                      "section_scale", "scale", "opacity", "visible", "font"):
            dv = settings.value(f"display/{key}/default_{prop}")
            if dv is not None:
                default_ov[prop] = dv
        vals = _read_category_from_settings(key, settings, overrides=default_ov)
        # Write back so Display Manager shows these values
        _write_category_to_settings(key, vals, settings)
        _apply_to_scene_items(scene, key, vals, respect_overrides=True)
    settings.sync()


def apply_default_display_settings(scene):
    """Apply stored default settings (from 'Set as Default') to all items.

    Called when creating a new project to apply the user's preferred defaults.
    Reads from ``display/{key}/default_*`` keys, falling back to regular keys.
    """
    settings = QSettings("GV", "FirePro3D")

    for cat_def in _CATEGORIES:
        key = cat_def["key"]
        # Build overrides from default_* keys (fall back to regular keys)
        default_ov: dict = {}
        for prop in ("color", "fill", "section", "section_pattern", "section_scale", "scale", "opacity", "visible", "font"):
            dv = settings.value(f"display/{key}/default_{prop}")
            if dv is not None:
                default_ov[prop] = dv
        vals = _read_category_from_settings(key, settings, overrides=default_ov)

        # Also save as current settings so Display Manager shows them
        _write_category_to_settings(key, vals, settings)

        _apply_to_scene_items(scene, key, vals, respect_overrides=False)


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
    return result


def apply_project_display_settings(scene, display_dict: dict):
    """Apply display settings loaded from a project file to all items.

    *display_dict* maps category key → {color, scale, opacity, visible, fill, font}.
    User defaults (``default_*`` keys) take priority over project values,
    so the user's "Set as Default" preferences are always honoured.
    Falls back to QSettings for any category not present in *display_dict*.
    """
    settings = QSettings("GV", "FirePro3D")

    for cat_def in _CATEGORIES:
        key = cat_def["key"]
        proj = display_dict.get(key, {})

        # User defaults win over project-embedded values
        merged = dict(proj)
        for prop in ("color", "fill", "section", "section_pattern",
                      "section_scale", "scale", "opacity", "visible", "font"):
            user_default = settings.value(f"display/{key}/default_{prop}")
            if user_default is not None:
                merged[prop] = user_default

        vals = _read_category_from_settings(key, settings, overrides=merged)

        # Update QSettings so Display Manager shows these values
        _write_category_to_settings(key, vals, settings)

        _apply_to_scene_items(scene, key, vals, respect_overrides=True)
    settings.sync()


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
    elif key == "Opening":
        openings = []
        for wall in getattr(scene, "_walls", []):
            openings.extend(getattr(wall, "openings", []))
        return openings
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
        items.extend(getattr(scene, "_draw_polygons", []))
        return items
    return []
