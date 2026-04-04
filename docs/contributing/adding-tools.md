# Adding New Tools

This guide covers how to add a new interactive tool (drawing mode) to FirePro3D. Tools follow a consistent pattern: define a mode string, implement mouse event handlers, and wire up a ribbon button.

## Architecture Overview

Tools are driven by a **mode string** stored on `Model_Space`. The flow is:

1. User clicks a ribbon button, which calls `scene.set_mode("my_tool")`
2. `Model_Space.set_mode()` stores the mode and emits `modeChanged`
3. Mouse event handlers in `Model_Space` or `SceneToolsMixin` check `self.mode` and dispatch accordingly
4. When the tool completes (or the user presses Escape), `set_mode(None)` resets to idle

## Step 1: Add the Mode Constant

In `firepro3d/Model_Space.py`, the `set_mode()` method manages all mode transitions. It handles cleanup of previews, snap state, and stale references:

```python
def set_mode(self, mode, template=None):
    self.mode = mode
    self._snap_result = None      # clear stale snap marker
    self._grip_item = None
    self._grip_index = -1
    self._grip_dragging = False
    self.modeChanged.emit(mode)
    # Auto-deselect all geometry when entering a drawing mode
    if mode not in ("select", "stretch", "move", "rotate", "scale",
                    "radiation_emitter", "radiation_receiver"):
        self.clearSelection()
    self.preview_node.hide()
    self.preview_pipe.hide()
    self._cal_point1 = None
```

No code changes are needed in `set_mode()` itself -- it accepts any string. Just choose a descriptive name like `"my_tool"` and use it consistently.

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
        pos = self._snap_or_raw(event)
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
            pos = self._snap_or_raw(event)
            # Update a preview item here
            pass
```

### Existing Tool Example: Offset

For reference, here is how the offset tool computes perpendicular distance to determine the offset side. This shows the typical pattern of helper methods supporting the main tool:

```python
def _perpendicular_distance(self, source, pt: QPointF) -> float:
    """Return the perpendicular distance from *pt* to *source* entity."""
    if isinstance(source, LineItem):
        line = source.line()
        p1 = source.mapToScene(line.p1())
        p2 = source.mapToScene(line.p2())
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        seg_len = math.hypot(dx, dy)
        if seg_len < 1e-10:
            return math.hypot(pt.x() - p1.x(), pt.y() - p1.y())
        return abs(dx * (p1.y() - pt.y()) - dy * (p1.x() - pt.x())) / seg_len
```

### Wire Into Model_Space Mouse Events

In `Model_Space.py`, add dispatch logic in the appropriate mouse handler. For a press-based tool:

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

In `main.py`, ribbon buttons are created inside tab-building methods (`_init_draw_tab`, `_init_build_tab`, `_init_modify_tab`). Use the `_mode_btn` helper for tools that set a drawing mode:

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

To add your tool button, call `_mode_btn` inside the appropriate tab method:

```python
# In _init_draw_tab or _init_modify_tab:
_mode_btn(g_group, "My Tool", _I("my_tool_icon.svg"), "my_tool").setToolTip(
    "Description of what the tool does")
```

The button is automatically checkable -- it stays highlighted while the tool is active, and un-highlights when the mode changes.

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

Replace the placeholder with a proper SVG before merging. Icons should be simple, single-color, and legible at both 32x32 (large button) and 16x16 (small button) sizes.

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
