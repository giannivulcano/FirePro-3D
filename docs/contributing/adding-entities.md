# Adding New Entities

This guide walks through adding a new entity type to FirePro3D, using the existing `Node` implementation as a reference. Every entity follows the same pattern: subclass a Qt graphics item, mix in `DisplayableItemMixin`, register with the Display Manager, and wire up serialization.

## Step 1: Create the Entity File

Create `firepro3d/my_entity.py`. Your class must inherit from both `DisplayableItemMixin` and a `QGraphicsItem` subclass. Here is the pattern from `node.py`:

```python
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPen, QBrush
from .constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER
from .displayable_item import DisplayableItemMixin


class MyEntity(DisplayableItemMixin, QGraphicsEllipseItem):
    def __init__(self, x, y):
        super().__init__(-10, -10, 20, 20)  # bounding rect
        self.setPos(x, y)
        self.setZValue(10)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        # Initialize display-manager attributes
        self.init_displayable()
```

Key points:

- Call `self.init_displayable()` in `__init__` -- this sets `level`, `user_layer`, `_display_color`, and other shared attributes.
- Set an appropriate Z-value (see the [conventions guide](guide.md) for the Z-ordering table).
- Enable `ItemIsSelectable` and `ItemSendsGeometryChanges` flags for interactive items.

## Step 2: Implement Required Methods

### boundingRect() and paint()

Every QGraphicsItem must define its bounding rectangle and paint logic. From `node.py`:

```python
def boundingRect(self) -> QRectF:
    """Expand bounding rect to encompass selection highlight."""
    r = 14.0 * 25.4 / 2.0  # 177.8 mm (7 inches)
    r = max(r, self.RADIUS + 4)
    return QRectF(-r, -r, r * 2, r * 2)

def paint(self, painter, option, widget=None):
    painter.setPen(QPen(Qt.PenStyle.NoPen))
    painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    if self.isSelected():
        r = 14.0 * 25.4 / 2.0
        pen = QPen(QColor(0, 120, 215), r * 0.45)
        pen.setCosmetic(False)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), r, r)

    # Suppress Qt's default selection box
    option.state &= ~QStyle.StateFlag.State_Selected
```

### itemChange()

Handle selection and position changes:

```python
def itemChange(self, change, value):
    if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
        self.update()  # force repaint on selection change

    if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
        # Update connected items here
        pass

    return super().itemChange(change, value)
```

## Step 3: Add Properties for the Property Panel

The PropertyManager reads a `_properties` dict and calls `get_properties()` / `set_property()`. From `node.py`:

```python
# In __init__:
self._properties: dict = {
    "Ceiling Level":  {"type": "level_ref", "value": DEFAULT_LEVEL},
    "Ceiling Offset": {"type": "string", "value": str(DEFAULT_CEILING_OFFSET_MM)},
}

def get_properties(self) -> dict:
    props = self._properties.copy()
    # Format values for display
    props["Ceiling Offset"] = dict(props["Ceiling Offset"])
    props["Ceiling Offset"]["value"] = self._fmt(self.ceiling_offset)
    return props

def set_property(self, key: str, value: str):
    if key == "Ceiling Level":
        self._properties[key]["value"] = str(value)
        self.ceiling_level = str(value)
    elif key in self._properties:
        self._properties[key]["value"] = str(value)
```

Supported property types include `"string"`, `"combo"`, `"level_ref"`, and `"bool"`. Add `"readonly": True` to prevent editing.

## Step 4: Register the Category in Display Manager

Open `firepro3d/display_manager.py` and add an entry to the `_CATEGORIES` list:

```python
_CATEGORIES: list[dict] = [
    {"key": "Pipe",       "color": "#4488ff", "fill": None,      "section": None,
     "section_pattern": None, "font": 12, "scale": 1.0, "opacity": 100,
     "visible": True, "group": "Fire Suppression"},
    # ... existing categories ...

    # Add your new category:
    {"key": "My Entity",  "color": "#cc44cc", "fill": None,      "section": None,
     "section_pattern": None, "font": None, "scale": 1.0, "opacity": 100,
     "visible": True, "group": "Fire Suppression"},
]
```

Then update the `apply_category_defaults()` function to recognize your class:

```python
def apply_category_defaults(item):
    from .my_entity import MyEntity
    # ... existing isinstance checks ...
    elif isinstance(item, MyEntity):
        key = "My Entity"
```

This allows the Display Manager UI to control visibility, color, and opacity for your entity type.

## Step 5: Add Serialization in scene_io.py

### Saving

In `SceneIOMixin.save_to_file()`, collect your entities and serialize them. Follow the pattern used for nodes:

```python
# In save_to_file():
my_entities_data = []
for ent in self._get_my_entities():  # however you track them
    my_entities_data.append({
        "x": ent.scenePos().x(),
        "y": ent.scenePos().y(),
        "user_layer": getattr(ent, "user_layer", DEFAULT_USER_LAYER),
        "level": getattr(ent, "level", DEFAULT_LEVEL),
        "properties": {k: v["value"] for k, v in ent._properties.items()},
    })
# Add to the payload dict:
payload["my_entities"] = my_entities_data
```

### Loading

In `SceneIOMixin.load_from_file()`, deserialize and add items to the scene. From the node loading pattern:

```python
# In load_from_file():
from .my_entity import MyEntity

for entry in payload.get("my_entities", []):
    ent = MyEntity(entry["x"], entry["y"])
    ent.user_layer = entry.get("user_layer", DEFAULT_USER_LAYER)
    ent.level = entry.get("level", DEFAULT_LEVEL)
    for key, value in entry.get("properties", {}).items():
        ent.set_property(key, value)
    ent._display_overrides = entry.get("display_overrides", {})
    self.addItem(ent)
```

## Step 6: Add a Creation Method in Model_Space

Add a method to `firepro3d/Model_Space.py` that creates and adds your entity to the scene:

```python
def add_my_entity(self, x: float, y: float) -> "MyEntity":
    from .my_entity import MyEntity
    from .display_manager import apply_category_defaults

    ent = MyEntity(x, y)
    ent.level = self.active_level
    ent.user_layer = self.active_user_layer
    apply_category_defaults(ent)
    self.addItem(ent)
    return ent
```

Always call `apply_category_defaults()` so the new item inherits the user's current Display Manager settings.

## Step 7: Connect to the UI

### Ribbon Button

In `main.py`, add a button using the `_mode_btn` helper inside one of the `_init_*_tab` methods:

```python
_mode_btn(g_group, "My Entity", _I("my_entity_icon.svg"),
          "place_my_entity").setToolTip("Place a new entity")
```

### Mouse Handler

In `firepro3d/Model_Space.py`, handle the mode in `mousePressEvent`:

```python
if self.mode == "place_my_entity":
    pos = self._snap_or_raw(event)
    self.add_my_entity(pos.x(), pos.y())
```

See [Adding Tools](adding-tools.md) for the full tool-wiring pattern.

## Checklist

When adding a new entity, verify each step:

- [ ] Entity class inherits `DisplayableItemMixin` + QGraphicsItem subclass
- [ ] `init_displayable()` called in `__init__`
- [ ] `boundingRect()`, `paint()`, `itemChange()` implemented
- [ ] `_properties` dict defined; `get_properties()` and `set_property()` implemented
- [ ] Category added to `_CATEGORIES` in `display_manager.py`
- [ ] `apply_category_defaults()` updated with isinstance check
- [ ] Save block added to `save_to_file()` in `scene_io.py`
- [ ] Load block added to `load_from_file()` in `scene_io.py`
- [ ] Creation method added to `Model_Space.py` with `apply_category_defaults()` call
- [ ] Ribbon button or menu entry added in `main.py`
