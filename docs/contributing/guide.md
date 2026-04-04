# Conventions Guide

This document covers the coding conventions and standards used throughout FirePro3D. All contributors should follow these guidelines when adding or modifying code.

## Internal Units

All geometry is stored internally in **millimeters**. The display layer converts to feet/inches or metric for the user via `ScaleManager`, but every coordinate, dimension, and offset in code is millimeters.

When formatting a value for display, use the `_fmt()` helper inherited from `DisplayableItemMixin`:

```python
label_text = self._fmt(self.ceiling_offset)  # e.g. "-2 in" or "-50.8 mm"
```

## Constants

All shared constants live in `firepro3d/constants.py`. Never use magic numbers or strings inline -- import from this module instead.

```python
from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER, DEFAULT_CEILING_OFFSET_MM
```

### Z-Ordering

Z-values control draw order on the 2D canvas. Lower values draw behind higher values:

| Constant / Range     | Value  | Used For                            |
|----------------------|--------|-------------------------------------|
| `Z_BELOW_GEOMETRY`   | -100   | Underlays, PDF imports              |
| `Z_ROOF`             | -75    | Roof items (above underlays)        |
| Walls / Floors       | 0 - 50 | Architectural geometry              |
| Nodes                | 10+    | Pipe junction points                |
| Sprinklers           | 100    | Sprinkler symbols (topmost)         |

### Default Values

| Constant                     | Value       | Meaning                              |
|------------------------------|-------------|--------------------------------------|
| `DEFAULT_LEVEL`              | `"Level 1"` | Default floor level name            |
| `DEFAULT_USER_LAYER`         | `"Default"` | Default drawing layer               |
| `DEFAULT_CEILING_OFFSET_MM`  | `-50.8`     | Sprinkler deflector 2 inches below ceiling |
| `DEFAULT_GRIDLINE_SPACING_IN`| `7315.2`    | 24 ft grid spacing (in mm)          |

### NFPA 13 Coverage Limits

Hazard-class maximum coverage areas are defined in `NFPA_MAX_COVERAGE_SQFT`:

| Hazard Class              | Max Coverage (sq ft) |
|---------------------------|----------------------|
| Light Hazard              | 225                  |
| Ordinary Hazard Group 1/2 | 130                  |
| Extra Hazard Group 1/2    | 100                  |
| High Piled Storage        | 100                  |

### Velocity Thresholds

Pipe velocity is color-coded using thresholds in ft/s:

- `VELOCITY_HIGH_FPS = 20.0` -- Red, exceeds NFPA limits
- `VELOCITY_WARN_FPS = 12.0` -- Orange, approaching limit
- Below 12 ft/s -- Green, acceptable

## Naming Conventions

Follow PEP 8 throughout:

- **Modules and functions**: `lowercase_with_underscores` (e.g. `scene_tools.py`, `set_mode()`)
- **Classes**: `PascalCase` (e.g. `WallSegment`, `DisplayableItemMixin`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g. `Z_BELOW_GEOMETRY`)
- **Private attributes**: single leading underscore (e.g. `_room_name`, `_display_color`)

## Type Hints

All new code must include type hints on function signatures:

```python
def z_range_mm(self) -> tuple[float, float] | None:
    """Node occupies a single elevation point at its z_pos."""
    z = getattr(self, "z_pos", None)
    return (z, z) if z is not None else None
```

## Docstring Style

Use Google-style docstrings with `Args:` and `Returns:` sections:

```python
def centre_svg_on_origin(item, target_mm: float, fallback_scale: float = 1.0,
                          display_scale: float = 1.0, *, reset_pos: bool = False):
    """Scale and centre an SVG item so its visual centre maps to local (0, 0).

    Args:
        item: QGraphicsSvgItem (or any item with boundingRect).
        target_mm: Desired size in scene units (mm).
        fallback_scale: Scale to use if the SVG has zero natural size.
        display_scale: Extra multiplier from Display Manager.
        reset_pos: If True, also call item.setPos(0, 0) for child items.

    Returns:
        None. The item's transform is modified in-place.
    """
```

## Import Style

Use **relative imports** within the `firepro3d/` package:

```python
# Inside firepro3d/node.py
from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER
from .displayable_item import DisplayableItemMixin
from .fitting import Fitting
```

Use **absolute imports** from the top-level entry point (`main.py`):

```python
# Inside main.py
from firepro3d.node import Node
from firepro3d.assets import asset_path
```

## Graphics Assets

SVG icons and symbols live under `firepro3d/graphics/`. Always resolve paths through the `asset_path()` helper from `firepro3d.assets`:

```python
from firepro3d.assets import asset_path

icon = QIcon(asset_path("Ribbon", "line_icon.svg"))
```

Never construct paths manually with `os.path.join` or string concatenation.

## Mixin Pattern

FirePro3D uses mixin-based composition extensively. When creating a new entity, inherit from both the Qt graphics base class and `DisplayableItemMixin`:

```python
class MyEntity(DisplayableItemMixin, QGraphicsPathItem):
    def __init__(self):
        QGraphicsPathItem.__init__(self)
        self.init_displayable()  # sets level, user_layer, display overrides
```

The mixin does not call `super().__init__()` to avoid interfering with Qt's constructor chain. Always call `init_displayable()` explicitly.

## NFPA 13 Standards

Design decisions throughout the codebase are driven by NFPA 13 (Standard for the Installation of Sprinkler Systems). This includes:

- Coverage area limits per hazard classification
- Velocity thresholds for pipe sizing
- Sprinkler spacing and placement rules
- Hydraulic calculation methods

When adding features that relate to code compliance, reference the relevant NFPA 13 section in code comments.

## Project File Format

Projects are saved as JSON via `SceneIOMixin` in `scene_io.py`. Each entity type has a serialization block in `save_to_file()` and a corresponding deserialization block in `load_from_file()`. See [Adding Entities](adding-entities.md) for details on extending the format.
