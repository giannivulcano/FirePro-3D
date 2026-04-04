# Display System

**Key files:**

- `firepro3d/displayable_item.py` -- Mixin with per-item display attributes
- `firepro3d/display_manager.py` -- Revit-style per-category and per-instance appearance control (2,071 lines)
- `firepro3d/constants.py` -- Z-ordering constants and colour maps

## Overview

The display system provides Revit-style control over entity appearance. It operates at two levels:

1. **Per-category defaults** -- stored in QSettings and optionally overridden by project files
2. **Per-instance overrides** -- stored on each entity in `_display_overrides`

When the Display Manager applies settings, per-instance overrides take priority over category defaults.

## DisplayableItemMixin

Every entity that participates in the display system inherits `DisplayableItemMixin` and calls `init_displayable()` in its constructor. This sets up:

| Attribute | Type | Purpose |
|-----------|------|---------|
| `level` | `str` | Floor level assignment |
| `user_layer` | `str` | User-defined layer |
| `_display_color` | `str \| None` | Stroke/pen colour override |
| `_display_fill_color` | `str \| None` | Fill/brush colour override |
| `_display_overrides` | `dict` | Per-instance overrides from Display Manager |
| `_is_section_cut` | `bool` | Set by LevelManager when item straddles cut plane |
| `_display_section_color` | `str \| None` | Section-cut hatch colour |
| `_display_section_pattern` | `str \| None` | Section-cut hatch pattern name |
| `_display_section_scale` | `float` | Section-cut pattern density multiplier |

## Category definitions

Categories are defined in `_CATEGORIES` in `display_manager.py`, organized into groups:

**Fire Suppression:**

| Category | Default Colour | Default Fill | Notes |
|----------|---------------|-------------|-------|
| Pipe | `#4488ff` | -- | Label font size 12 |
| Sprinkler | `#ff4444` | `#000000` | |
| Fitting | `#44cc44` | -- | |
| Water Supply | `#00cccc` | `#2b2b2e` | |
| Node | `#888888` | -- | |
| Hydraulic Badge | `#ffffff` | `#2b2b2b` | |

**Architecture:**

| Category | Default Colour | Default Fill | Section Colour | Section Pattern |
|----------|---------------|-------------|---------------|----------------|
| Wall | `#666666` | `#999999` | `#666666` | diagonal |
| Roof | `#8B4513` | `#D2B48C` | `#8B4513` | diagonal |
| Room | `#4488cc` | `#4488cc` | -- | -- |
| Floor | `#8888cc` | `#8888cc` | `#666666` | diagonal |

**Grids & Levels:**

| Category | Default Colour |
|----------|---------------|
| Grid Line | `#4488cc` |
| Level Datum | `#4488cc` |
| Elevation Marker | `#4488cc` |
| Detail Marker | `#4488cc` |

Each category has: colour, fill, section colour/pattern/scale, font size, scale factor, opacity (0-100), and visibility (bool).

## Override cascade

When applying display settings to a scene item, the system resolves each property through a three-tier cascade:

```
Per-instance override  (_display_overrides dict on the entity)
        |  (if not set, fall through)
        v
Project-level category override  (saved in project JSON)
        |  (if not set, fall through)
        v
QSettings / factory default  (from _CATEGORIES list)
```

The `_apply_to_scene_items()` function implements this:

```python
for obj in items:
    ov = getattr(obj, "_display_overrides", {})
    c = ov.get("color", vals["color"])      # instance override or category default
    s = ov.get("scale", vals["scale"])
    o = ov.get("opacity", vals["opacity"])
    v = ov.get("visible", vals["visible"])
    ...
```

## Z-ordering convention

Z-values control draw order on the 2D canvas. Items with higher Z-values render on top.

| Z-value | Constant | Entity |
|---------|----------|--------|
| -100 | `Z_BELOW_GEOMETRY` | Underlays, DXF/PDF imports |
| -75 | `Z_ROOF` | Roof items |
| -50 | -- | Walls (behind pipes) |
| 0 | -- | Default / Floor slabs |
| 10 | -- | Nodes |
| 50 | -- | Construction geometry |
| 100 | -- | Sprinklers (on top of nodes) |
| 200 | -- | Preview / ghost items |

These constants are defined in `constants.py` and used by entity constructors via `setZValue()`.

## SVG recolouring

Sprinklers, fittings, and water supply items use SVG graphics. The display system recolours them at the SVG XML level rather than using QPainter composition effects.

The `_recolor_svg_bytes()` function:

1. Parses the SVG XML with `xml.etree.ElementTree`
2. Finds the Inkscape layer group (`<g inkscape:groupmode="layer">`)
3. Sets `stroke` and `fill` CSS properties on the layer group
4. Replaces descendant elements' explicit stroke/fill with `inherit` (preserving `fill:none` / `stroke:none` for transparent parts)
5. Creates a new `QSvgRenderer` from the modified XML
6. Caches results by `(svg_path, color, fill_color)` tuple

The `_set_svg_tint()` convenience function applies this to any item that has a `_svg_source_path` attribute, then re-centres the item on its parent node.

## Section-cut hatching

When a wall or floor slab straddles the view's cut plane (i.e., `_is_section_cut` is True), the `draw_section_hatch()` function in `displayable_item.py` fills the item's clip path with a hatch pattern. This supports:

- Built-in Qt brush patterns (diagonal, crosshatch)
- SVG-based vector patterns (drawn as crisp lines at any zoom level)
- Configurable hatch colour, line weight, and scale

## Display Manager dialog

The `DisplayManager` class in `display_manager.py` is a `QDialog` with a tree widget showing all categories grouped by type. Users can modify:

- Visibility (checkbox)
- Colour (colour picker button)
- Fill colour (solid or hatch mode)
- Section colour and pattern
- Scale factor (spin box)
- Opacity (0-100 slider)
- Font size (for label-bearing categories)
- Per-category reset button

Changes apply live to the canvas. Cancelling the dialog reverts all changes to their prior state.

## Connection to other subsystems

- **Entities** -- each entity stores `_display_overrides` and category is inferred from class type
- **Level Manager** -- sets `_is_section_cut` flag during visibility passes
- **Scene I/O** -- saves/loads per-instance overrides and project-level category settings
- **3D View** -- reads display colours for mesh materials
