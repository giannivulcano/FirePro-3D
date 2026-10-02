# Adding New Tools

This guide covers how to add a new interactive tool (drawing mode) to FirePro3D. Tools follow a consistent pattern: define a mode string, implement mouse event handlers, and wire up a ribbon button.

> **Stale in places (noted 2026-10-01).** The step-by-step below predates the
> `Model_Space` decomposition: `SceneToolsMixin` is now the composed
> `SceneTools` (`scene._tools`), and modes route through the
> `_PRESS_DISPATCH` / `_MOVE_DISPATCH` / `_PREVIEW_DISPATCH` and
> `_SCHEMA_FOR_MODE` / `_APPLIER_FOR_MODE` tables, with 2D modify-tool
> behaviour in `ModifyToolsController`. The governing contracts are
> [`model-space-architecture.md`](../specs/model-space-architecture.md)
> (structure) and [`scene-tools.md`](../specs/scene-tools.md) (modify-tool
> behaviour, registries to update when adding a tool); they win where this
> guide disagrees.

## Architecture Overview

Tools are driven by a **mode string** stored on `Model_Space`. The flow is:

1. User clicks a ribbon button, which calls `scene.set_mode("my_tool")`
2. `Model_Space.set_mode()` stores the mode and emits `modeChanged`
3. Mouse event handlers in `Model_Space` or `SceneToolsMixin` check `self.mode` and dispatch accordingly
4. When the tool completes (or the user presses Escape), `set_mode(None)` resets to idle

## Step 1: Add the Mode Constant

In `firepro3d/model_space.py` (the `Model_Space` class), the `set_mode()` method manages all mode transitions. It handles cleanup of previews, snap state, and stale references:

`set_mode()` stores the mode, clears stale snap / grip state, runs the modify
tools' teardown (`ModifyToolsController.clear`), emits `modeChanged`, and —
for every mode **not** in its keep-selection exemption — clears the
selection. Read the exemption tuple in `Model_Space.set_mode` itself (it is
not restated here; selection-operand modify tools such as move / rotate /
scale / flip / mirror / array keep the selection — see
[`scene-tools.md`](../specs/scene-tools.md) D3). A selection-operand tool
must be added to that tuple; a drawing tool must not.

No other change is needed in `set_mode()` -- it accepts any string. Just choose a descriptive name like `"my_tool"` and use it consistently.

## Step 2: Implement Tool Logic in SceneToolsMixin

Tool implementations live in `firepro3d/scene_tools.py` as methods on `SceneToolsMixin`. This mixin is mixed into `Model_Space`, so `self` refers to the scene at runtime.

### Mouse Event Pattern

Tools typically respond to mouse press, move, and release events. The main `Model_Space` mouse handlers delegate to tool-specific methods based on `self.mode`. Add your handler methods to `SceneToolsMixin`:

```python
class SceneToolsMixin:
    """Geometry editing tools for the plan-view scene."""

    # ... existing tools ...

    # ─────────────────────────────────────────────────────────────────
    # MY TOOL
    # ─────────────────────────────────────────────────────────────────

    def _my_tool_press(self, event):
        """Handle mouse press for the my_tool mode."""
        pos = self.get_effective_position(event.scenePos())
        # First click: store start point
        if not hasattr(self, "_my_tool_start"):
            self._my_tool_start = pos
            self._show_status("Click second point...")
            return
        # Second click: complete the operation
        end = pos
        self._do_my_tool(self._my_tool_start, end)
        self._my_tool_start = None
        self.set_mode("select")

    def _my_tool_move(self, event):
        """Handle mouse move for live preview."""
        if hasattr(self, "_my_tool_start") and self._my_tool_start:
            pos = self.get_effective_position(event.scenePos())
            # Update a preview item here
            pass
```

### Existing Tool Example: Offset

For reference, the Offset tool (`docs/specs/scene-tools.md` D9) keeps its pure
geometry in `firepro3d/tool_geometry.py` and its gesture in
`firepro3d/modify_tools_controller.py`; `Model_Space` only holds thin dispatch
shells. The cursor handler measures the true distance to the source's drawn
geometry, picks the side, and previews the candidate item as the ghost:

```python
def move_offset_side(self, event, snapped):
    from . import tool_geometry as tg
    s = self._scene
    src = s._offset_source
    if src is None or self._drop_dead_source():
        return
    if not s._offset_typed:                      # a typed distance is locked
        s._offset_dist = tg.distance_to_item(src, snapped)
    s._offset_side = tg.offset_side_sign(src, snapped)
    self._refresh_offset_ghost()                 # ghost = offset_item(...) trace
    s.publish_placement_state(snapped, snapped)  # seeds the Distance HUD
```

### Wire Into Model_Space Mouse Events

In `model_space.py`, add dispatch logic in the appropriate mouse handler. For a press-based tool:

```python
# In mousePressEvent:
if self.mode == "my_tool":
    self._my_tool_press(event)
    return

# In mouseMoveEvent (for live preview):
if self.mode == "my_tool":
    self._my_tool_move(event)
```

## Step 3: Add a Ribbon Button

In `main.py`, ribbon buttons are created inside tab-building helpers. Use the `_mode_btn` helper for tools that set a drawing mode:

```python
def _mode_btn(group, label, icon, mode_name, large=True):
    """Create a checkable draw-mode button."""
    cb = lambda: self.scene.set_mode(mode_name)
    if large:
        btn = group.add_large_button(label, icon, cb, checkable=True)
    else:
        btn = group.add_small_button(label, icon, cb, checkable=True)
    self._mode_buttons[mode_name] = btn
    return btn
```

Choose the tab that matches the tool's purpose:

| Tool category | Tab helper | Tab label |
|---|---|---|
| Geometry drawing (lines, circles, construction lines) | `_init_create_tab` | **Create** |
| Building elements (walls, floors, rooms, doors) | `_init_architecture_tab` | **Architecture** |
| Sprinkler / pipe placement | `_init_sprinkler_systems_tab` | **Sprinkler Systems** |

> **Note — Modify tab removed.** There is no longer a dedicated Modify tab.
> Model-edit operations (move, rotate, copy) are keyboard/right-click driven.
> Selection-sensitive commands appear automatically in a **contextual tab**
> that inserts when an entity family is selected and disappears on deselect.
> See `docs/specs/ribbon-bar.md §3.8` for the contextual-tab mechanism.

To add your tool button, call `_mode_btn` inside the appropriate tab helper:

```python
# Example: geometry tool → _init_create_tab
_mode_btn(g_group, "My Tool", _I("my_tool_icon.svg"), "my_tool").setToolTip(
    "Description of what the tool does")
```

The button is automatically checkable — it stays highlighted while the tool is active, and un-highlights when the mode changes.

### Simple vs. Split-Menu Buttons

For tools with a single action, `_mode_btn` is all you need:

```python
_mode_btn(g_geom, "Circle", _I("circle_icon.svg"), "draw_circle")
```

For tools with sub-modes, create a split-menu button manually:

```python
_line_btn = g_geom.add_large_button(
    "Line", _I("line_icon.svg"),
    lambda: self.scene.set_mode("draw_line"), checkable=True)
_line_menu = QMenu(_line_btn)
_line_menu.addAction("Line").triggered.connect(
    lambda: self.scene.set_mode("draw_line"))
_line_menu.addAction("Construction Line").triggered.connect(
    lambda: self.scene.set_mode("construction_line"))
_line_btn.setMenu(_line_menu)
_line_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
self._mode_buttons["draw_line"] = _line_btn
```

## Step 4: Add an Icon

Place your tool's SVG icon in `firepro3d/graphics/Ribbon/`. Use `placeholder_icon.svg` during development:

```python
_mode_btn(g_group, "My Tool", _I("placeholder_icon.svg"), "my_tool")
```

Icons are loaded through the `asset_path` helper:

```python
_I = lambda name: QIcon(asset_path("Ribbon", name))
```

Replace the placeholder with a proper SVG before merging. Icons should be simple, single-color, and legible at both large-button and small-button render sizes (button geometry owned by `docs/specs/ribbon-bar.md` §3.1).

## Step 5: Handle Escape / Cancel

`set_mode(None)` is called when the user presses Escape. It cleans up preview items and resets state automatically. If your tool allocates temporary graphics items, clean them up in `set_mode()` or in a dedicated cleanup method:

```python
# In set_mode() or a cleanup path:
if mode != "my_tool":
    self._my_tool_start = None
    if self._my_tool_preview is not None:
        if self._my_tool_preview.scene() is self:
            self.removeItem(self._my_tool_preview)
        self._my_tool_preview = None
```

## Checklist

- [ ] Mode string chosen (descriptive, `snake_case`)
- [ ] Tool handler methods added to `SceneToolsMixin` in `scene_tools.py`
- [ ] Mouse event dispatch added in `Model_Space.py`
- [ ] Ribbon button added via `_mode_btn()` in `main.py`
- [ ] SVG icon placed in `firepro3d/graphics/Ribbon/`
- [ ] Escape/cancel cleanup handles any preview items
- [ ] Status bar messages guide the user through multi-click workflows
