# Visibility & Display Cluster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix hidden-item reappearance on level switch, add riser pass-through indicator in plan view, and add fittings group to model browser.

**Architecture:** Three targeted fixes. Task 1 adds a 2-line guard in level_manager. Task 2 adds an SVG asset and riser symbol management to Pipe. Task 3 adds a Fittings group to model_browser and fitting hide/show support.

**Tech Stack:** PyQt6, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `firepro3d/level_manager.py` | Modify | Check `_display_overrides["visible"]` in `_set_level_vis` |
| `firepro3d/pipe.py` | Modify | Add `_riser_symbol` management, extend `setVisible` cascade |
| `firepro3d/fitting.py` | Modify | Check `_display_overrides["visible"]` in `update()` |
| `firepro3d/model_browser.py` | Modify | Add Fittings group with individual items |
| `firepro3d/model_space.py` | Modify | Handle Fitting objects in `_hide_items`/`_show_items` |
| `firepro3d/graphics/fitting_symbols/riser_passthrough.svg` | Create | Yin-yang / broken-pipe SVG symbol |
| `tests/test_visibility_display.py` | Create | Unit tests for all three fixes |

---

### Task 1: Hidden Items Respect Display Overrides

**Files:**
- Modify: `firepro3d/level_manager.py:377-411`
- Test: `tests/test_visibility_display.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_visibility_display.py`:

```python
"""tests/test_visibility_display.py — Visibility & display cluster tests."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.node import Node
from firepro3d.pipe import Pipe


@pytest.fixture
def scene(qapp):
    """Bare QGraphicsScene for items that need one."""
    return QGraphicsScene()


def _make_node(scene, x, y, z=0.0):
    n = Node(x, y)
    scene.addItem(n)
    n.z_pos = z
    return n


def _make_pipe(scene, n1, n2):
    p = Pipe(n1, n2)
    scene.addItem(p)
    return p


# ── Task 1: Hidden items respect display overrides ─────────────────────


class TestHiddenItemsRespectOverrides:

    def test_hidden_pipe_stays_hidden_after_set_level_vis(self, qapp, scene):
        """A pipe with _display_overrides['visible']=False must not be
        re-shown by _set_level_vis logic."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.level = "Level 1"
        p._display_overrides["visible"] = False
        p.setVisible(False)

        # Simulate what _set_level_vis does for active level
        from firepro3d.level_manager import LevelManager
        lm = LevelManager.__new__(LevelManager)
        lm._levels = {"Level 1": type("L", (), {"elevation": 0.0, "name": "Level 1"})()}
        lm.active_level = "Level 1"
        lm.apply_to_scene(scene)

        assert p.isVisible() is False

    def test_hidden_node_stays_hidden_after_set_level_vis(self, qapp, scene):
        """A node with _display_overrides['visible']=False stays hidden."""
        n = _make_node(scene, 0, 0)
        n.level = "Level 1"
        n._display_overrides["visible"] = False
        n.setVisible(False)

        from firepro3d.level_manager import LevelManager
        lm = LevelManager.__new__(LevelManager)
        lm._levels = {"Level 1": type("L", (), {"elevation": 0.0, "name": "Level 1"})()}
        lm.active_level = "Level 1"
        lm.apply_to_scene(scene)

        assert n.isVisible() is False

    def test_non_hidden_pipe_shown_normally(self, qapp, scene):
        """Pipe without display override is shown on active level."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.level = "Level 1"

        from firepro3d.level_manager import LevelManager
        lm = LevelManager.__new__(LevelManager)
        lm._levels = {"Level 1": type("L", (), {"elevation": 0.0, "name": "Level 1"})()}
        lm.active_level = "Level 1"
        lm.apply_to_scene(scene)

        assert p.isVisible() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py::TestHiddenItemsRespectOverrides -v`
Expected: `test_hidden_pipe_stays_hidden_after_set_level_vis` FAILS (pipe gets re-shown)

- [ ] **Step 3: Add display override guard to _set_level_vis**

In `firepro3d/level_manager.py`, inside `_set_level_vis()` (after the deleted-C++ guard at line 382, before the section-cut reset at line 385), add:

```python
            # Respect user-hidden items — do not re-show
            if getattr(item, "_display_overrides", {}).get("visible") is False:
                item.setVisible(False)
                return
```

The full function start becomes:
```python
        def _set_level_vis(item):
            # Guard against deleted C++ objects (e.g. after undo)
            try:
                item.isVisible()
            except RuntimeError:
                return

            # Respect user-hidden items — do not re-show
            if getattr(item, "_display_overrides", {}).get("visible") is False:
                item.setVisible(False)
                return

            # Reset section-cut flag
            if hasattr(item, "_is_section_cut"):
                item._is_section_cut = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py::TestHiddenItemsRespectOverrides -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add firepro3d/level_manager.py tests/test_visibility_display.py
git commit -m "fix: _set_level_vis respects _display_overrides['visible']

User-hidden items (via model browser Hide) now stay hidden across level
switches and view range changes. Early return skips Z-ordering, opacity,
and selectability entirely.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Riser Pass-Through SVG Asset

**Files:**
- Create: `firepro3d/graphics/fitting_symbols/riser_passthrough.svg`

- [ ] **Step 1: Create the yin-yang / broken-pipe SVG**

Create `firepro3d/graphics/fitting_symbols/riser_passthrough.svg`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg width="20mm" height="20mm" viewBox="0 0 20 20" version="1.1"
     xmlns="http://www.w3.org/2000/svg">
  <g>
    <!-- Outer circle -->
    <circle cx="10" cy="10" r="9" fill="none" stroke="#ffffff" stroke-width="1.5"/>
    <!-- Left half filled (semicircle) -->
    <path d="M 10,1 A 9,9 0 0 0 10,19" fill="#ffffff" stroke="none"/>
    <!-- S-curve divider -->
    <path d="M 10,1 C 10,5.5 14.5,7 14.5,10 C 14.5,13 10,14.5 10,19"
          fill="none" stroke="#ffffff" stroke-width="1"/>
    <!-- Inner left bump (small semicircle, filled opposite) -->
    <circle cx="10" cy="5.5" r="2.5" fill="#ffffff" stroke="none"/>
    <!-- Inner right bump -->
    <circle cx="10" cy="14.5" r="2.5" fill="none" stroke="none"/>
    <!-- Correct yin-yang: left half filled by the main path, right half open.
         S-curve creates the division. Small circles create the yin-yang dots. -->
    <!-- Dot in filled half (open) -->
    <circle cx="10" cy="5.5" r="1" fill="none" stroke="#ffffff" stroke-width="0.5"/>
    <!-- Dot in open half (filled) -->
    <circle cx="10" cy="14.5" r="1" fill="#ffffff" stroke="none"/>
  </g>
</svg>
```

Note: The SVG uses `#ffffff` for all strokes/fills. The `_TintedSvg` / display manager system recolours it at runtime to match the pipe colour. The 20mm × 20mm viewBox matches all other fitting SVGs.

- [ ] **Step 2: Verify the SVG file renders**

Open the SVG in a browser or Inkscape to verify the yin-yang shape looks correct. The design can be refined later — the important thing is a valid SVG at the expected path.

- [ ] **Step 3: Commit**

```bash
git add firepro3d/graphics/fitting_symbols/riser_passthrough.svg
git commit -m "feat: add riser pass-through yin-yang SVG symbol

20x20mm viewBox, white strokes/fills for display manager recolouring.
Classic broken-pipe / yin-yang symbol for plan-view riser indication.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Riser Symbol Management on Pipe

**Files:**
- Modify: `firepro3d/pipe.py:1-7, 108-137, 168-187`
- Test: `tests/test_visibility_display.py`

- [ ] **Step 1: Write failing tests for riser symbol**

Append to `tests/test_visibility_display.py`:

```python
from firepro3d.constants import Z_OVERLAY


# ── Task 2/3: Riser pass-through indicator ──────────────────────────────


class TestRiserPassthroughIndicator:

    def test_vertical_pipe_creates_riser_symbol(self, qapp, scene):
        """Vertical pipe should have a _riser_symbol."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        p.update_label()
        assert p._riser_symbol is not None

    def test_horizontal_pipe_no_riser_symbol(self, qapp, scene):
        """Horizontal pipe should not create a riser symbol."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        p = _make_pipe(scene, n1, n2)
        p.update_label()
        assert p._riser_symbol is None or not p._riser_symbol.isVisible()

    def test_riser_symbol_hidden_when_endpoint_visible(self, qapp, scene):
        """Riser symbol hidden when either endpoint node is visible."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        # Both nodes visible — symbol should be hidden
        p.update_label()
        assert p._riser_symbol.isVisible() is False

    def test_riser_symbol_shown_when_no_endpoint_visible(self, qapp, scene):
        """Riser symbol shows when neither endpoint node is visible."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        top.setVisible(False)
        bot.setVisible(False)
        p.update_label()
        assert p._riser_symbol.isVisible() is True

    def test_riser_symbol_at_z_overlay(self, qapp, scene):
        """Riser symbol should be at Z_OVERLAY."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        top.setVisible(False)
        bot.setVisible(False)
        p.update_label()
        assert p._riser_symbol.zValue() == Z_OVERLAY

    def test_riser_symbol_hidden_when_pipe_hidden(self, qapp, scene):
        """setVisible(False) on pipe cascades to riser symbol."""
        top = _make_node(scene, 0, 0, z=3000)
        bot = _make_node(scene, 0, 0, z=0)
        p = _make_pipe(scene, top, bot)
        top.setVisible(False)
        bot.setVisible(False)
        p.update_label()
        assert p._riser_symbol.isVisible() is True
        p.setVisible(False)
        assert p._riser_symbol.isVisible() is False

    def test_riser_symbol_cleanup_on_delete(self, qapp):
        """Riser symbol removed from scene when pipe is deleted."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        top = _make_node(ms, 0, 0, z=3000)
        bot = _make_node(ms, 0, 0, z=0)
        p = _make_pipe(ms, top, bot)
        top.setVisible(False)
        bot.setVisible(False)
        p.update_label()
        sym = p._riser_symbol
        ms.delete_pipe(p)
        assert sym.scene() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py::TestRiserPassthroughIndicator -v`
Expected: FAIL — `_riser_symbol` attribute doesn't exist

- [ ] **Step 3: Add _riser_symbol attribute and imports**

In `firepro3d/pipe.py`, add import for `QGraphicsSvgItem` at the top (line 2):

```python
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
```

Add import for `asset_path` (check if already imported; if not, add):

```python
from .assets import asset_path
```

In `__init__`, after the label setup (after line 114), add:

```python
        self._riser_symbol: QGraphicsSvgItem | None = None
```

- [ ] **Step 4: Add _update_riser_symbol method**

In `firepro3d/pipe.py`, after the `_is_vertical()` method (after line 166), add:

```python
    # ── Riser pass-through symbol ──────────────────────────────────────
    _RISER_SVG = asset_path("fitting_symbols", "riser_passthrough.svg")
    _RISER_SIZE_MM = 300.0  # fixed symbol size in scene units (mm)

    def _update_riser_symbol(self):
        """Show/hide the riser pass-through symbol for vertical pipes."""
        if not self.node1 or not self.node2:
            return

        if not self._is_vertical():
            # Not vertical — hide symbol if it exists
            if self._riser_symbol is not None:
                self._riser_symbol.setVisible(False)
            return

        # Vertical pipe — create symbol if needed
        if self._riser_symbol is None:
            self._riser_symbol = QGraphicsSvgItem(self._RISER_SVG)
            self._riser_symbol.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self._riser_symbol.setAcceptHoverEvents(False)

        # Add to scene if not yet added
        sc = self.scene()
        if sc is not None and self._riser_symbol.scene() is None:
            sc.addItem(self._riser_symbol)
            self._riser_symbol.setZValue(Z_OVERLAY)

        # Scale to fixed size
        bounds = self._riser_symbol.boundingRect()
        natural = max(bounds.width(), bounds.height())
        if natural > 0:
            scale = self._RISER_SIZE_MM / natural
            self._riser_symbol.setScale(scale)

        # Position at pipe XY (both endpoints share same XY for vertical pipes)
        pos = self.node1.scenePos()
        half = self._RISER_SIZE_MM / 2
        self._riser_symbol.setPos(pos.x() - half, pos.y() - half)

        # Visibility: only show when NEITHER endpoint node is visible
        if not self.isVisible():
            self._riser_symbol.setVisible(False)
        elif self.node1.isVisible() or self.node2.isVisible():
            self._riser_symbol.setVisible(False)
        else:
            self._riser_symbol.setVisible(True)
```

- [ ] **Step 5: Call _update_riser_symbol from update_label**

In `firepro3d/pipe.py`, in `update_label()`, after the existing label positioning (at the end of the method, after `self.set_label_position()`), add:

```python
        self._update_riser_symbol()
```

Also add a call in the early returns where the label is hidden. In the vertical-pipe branch (around line 189-192):

```python
        # Hide label for vertical pipes (same XY, different z) in plan view
        if self._is_vertical():
            self.label.setVisible(False)
            self._update_riser_symbol()
            return
```

And in the pipe-not-visible early return (around line 185-187):

```python
        # Sync label visibility with pipe visibility
        if not self.isVisible():
            self.label.setVisible(False)
            self._update_riser_symbol()
            return
```

- [ ] **Step 6: Extend setVisible cascade to riser symbol**

In `firepro3d/pipe.py`, update the `setVisible` override to cascade to `_riser_symbol`:

```python
    def setVisible(self, visible: bool):
        """Override to cascade visibility to the top-level label and riser symbol."""
        super().setVisible(visible)
        if hasattr(self, "label") and self.label is not None:
            if not visible:
                self.label.setVisible(False)
            else:
                show = (self._properties["Show Label"]["value"] == "True"
                        and not self._is_vertical())
                self.label.setVisible(show)
        if hasattr(self, "_riser_symbol") and self._riser_symbol is not None:
            if not visible:
                self._riser_symbol.setVisible(False)
            elif self._is_vertical():
                # Re-evaluate: only show if neither endpoint node visible
                n1_vis = self.node1.isVisible() if self.node1 else False
                n2_vis = self.node2.isVisible() if self.node2 else False
                self._riser_symbol.setVisible(not n1_vis and not n2_vis)
```

- [ ] **Step 7: Handle riser symbol cleanup in delete_pipe**

In `firepro3d/model_space.py`, in `delete_pipe()`, add riser symbol removal alongside the label removal (after the label cleanup block):

```python
        # Remove top-level riser symbol from scene
        if hasattr(pipe, "_riser_symbol") and pipe._riser_symbol is not None:
            try:
                self.removeItem(pipe._riser_symbol)
            except (RuntimeError, ValueError):
                pass
```

Also add the same pattern in the other two pipe removal sites (bulk removal Pass 3 and `_restore_network`), using the same approach used for label cleanup.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py::TestRiserPassthroughIndicator -v`
Expected: All 7 tests PASS

- [ ] **Step 9: Run full test suite**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/ -q --no-header 2>&1 | grep -E "^[0-9]+ (passed|failed)"`
Expected: All pass, no regressions

- [ ] **Step 10: Commit**

```bash
git add firepro3d/pipe.py firepro3d/model_space.py tests/test_visibility_display.py
git commit -m "feat: riser pass-through indicator in plan view

Vertical pipes render a yin-yang SVG symbol at their XY location.
Symbol shows only when neither endpoint node is visible (avoids
doubling up with fitting symbols). Fixed 300mm size. Non-interactive.
Cascades through setVisible, cleaned up on pipe deletion.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Fitting Visibility Respects Display Overrides

**Files:**
- Modify: `firepro3d/fitting.py:81-114`
- Modify: `firepro3d/model_space.py:7221-7233`
- Test: `tests/test_visibility_display.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_visibility_display.py`:

```python
from firepro3d.fitting import Fitting


# ── Task 4: Fitting visibility respects display overrides ───────────────


class TestFittingDisplayOverrides:

    def test_fitting_hidden_via_display_override(self, qapp, scene):
        """Fitting with _display_overrides['visible']=False stays hidden
        even after fitting.update()."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        _make_pipe(scene, n1, n2)
        n1.fitting._display_overrides["visible"] = False
        n1.fitting.update()
        assert n1.fitting.symbol.isVisible() is False

    def test_fitting_shown_after_override_cleared(self, qapp, scene):
        """Clearing _display_overrides restores fitting visibility."""
        n1 = _make_node(scene, 0, 0)
        n2 = _make_node(scene, 1000, 0)
        _make_pipe(scene, n1, n2)
        n1.fitting._display_overrides["visible"] = False
        n1.fitting.update()
        assert n1.fitting.symbol.isVisible() is False
        n1.fitting._display_overrides.pop("visible", None)
        n1.fitting.update()
        assert n1.fitting.symbol.isVisible() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py::TestFittingDisplayOverrides -v`
Expected: `test_fitting_hidden_via_display_override` FAILS

- [ ] **Step 3: Add display override check to fitting.update()**

In `firepro3d/fitting.py`, in `update()`, add a check just before the final `self.symbol.setVisible(visibility)` line (line 114):

```python
        # Respect per-instance display override (model browser hide/show)
        if self._display_overrides.get("visible") is False:
            visibility = False
        self.symbol.setVisible(visibility)
```

- [ ] **Step 4: Add Fitting support to _hide_items / _show_items**

In `firepro3d/model_space.py`, update `_hide_items()` to handle Fitting objects:

```python
    def _hide_items(self, items):
        """Hide the given items via display overrides (persists through refresh)."""
        for item in items:
            if hasattr(item, "_display_overrides"):
                item._display_overrides["visible"] = False
            # Fitting is not a QGraphicsItem — hide its symbol directly
            if isinstance(item, Fitting):
                if item.symbol is not None:
                    item.symbol.setVisible(False)
            else:
                item.setVisible(False)
```

Update `_show_items()` similarly:

```python
    def _show_items(self, items):
        """Show the given items via display overrides."""
        for item in items:
            if hasattr(item, "_display_overrides"):
                item._display_overrides.pop("visible", None)
            # Fitting is not a QGraphicsItem — re-evaluate via update()
            if isinstance(item, Fitting):
                item.update()
            else:
                item.setVisible(True)
```

Add the Fitting import at the top of model_space.py (check if already imported; if not, add):

```python
from .fitting import Fitting
```

- [ ] **Step 5: Update _show_all_hidden to clear fitting overrides**

In `firepro3d/model_space.py`, in `_show_all_hidden()`, add fitting override clearing after the existing QGraphicsItem loop. `_show_all_hidden` iterates `self.items()` which only returns QGraphicsItems — Fitting wrappers are missed. Add:

```python
    def _show_all_hidden(self):
        """Restore visibility for all manually hidden items."""
        for item in self.items():
            if hasattr(item, "_display_overrides"):
                if item._display_overrides.get("visible") is False:
                    item._display_overrides.pop("visible", None)
                    item.setVisible(True)
        # Also clear fitting overrides (Fitting is not a QGraphicsItem)
        ss = getattr(self, "sprinkler_system", None)
        if ss:
            for node in ss.nodes:
                if node.fitting and node.fitting._display_overrides.get("visible") is False:
                    node.fitting._display_overrides.pop("visible", None)
                    node.fitting.update()
        # Re-apply level filtering so items outside the active view range
        # don't remain visible after being un-hidden.
        if hasattr(self, "_level_manager"):
            self._level_manager.apply_to_scene(self)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py::TestFittingDisplayOverrides -v`
Expected: All 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add firepro3d/fitting.py firepro3d/model_space.py tests/test_visibility_display.py
git commit -m "feat: fitting visibility respects _display_overrides

fitting.update() checks _display_overrides['visible'] before setting
symbol visibility. _hide_items/_show_items handle Fitting objects
(not QGraphicsItems) by hiding the symbol directly.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Fittings Group in Model Browser

**Files:**
- Modify: `firepro3d/model_browser.py:262-325`
- Test: `tests/test_visibility_display.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_visibility_display.py`:

```python
# ── Task 5: Fittings group in model browser ─────────────────────────────


class TestFittingsBrowserGroup:

    def _make_browser(self, scene):
        """Create a ModelBrowser attached to the given scene."""
        from firepro3d.model_browser import ModelBrowser
        browser = ModelBrowser(scene)
        browser.refresh()
        return browser

    def _find_group(self, browser, prefix):
        """Find a top-level group item starting with prefix."""
        root = browser._tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.text(0).startswith(prefix):
                return item
        return None

    def test_fittings_group_exists(self, qapp):
        """Browser should have a Fittings group."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        n1 = _make_node(ms, 0, 0)
        n2 = _make_node(ms, 1000, 0)
        n3 = _make_node(ms, 1000, 1000)
        _make_pipe(ms, n1, n2)
        _make_pipe(ms, n2, n3)
        n2.fitting.update()
        browser = self._make_browser(ms)
        group = self._find_group(browser, "Fittings")
        assert group is not None

    def test_fittings_count_excludes_no_fitting(self, qapp):
        """'no fitting' type nodes should not appear in the Fittings group."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        n1 = _make_node(ms, 0, 0)
        n2 = _make_node(ms, 1000, 0)
        n3 = _make_node(ms, 2000, 0)
        _make_pipe(ms, n1, n2)
        _make_pipe(ms, n2, n3)
        # n2 is collinear — fitting type is "no fitting"
        n2.fitting.update()
        assert n2.fitting.type == "no fitting"
        browser = self._make_browser(ms)
        group = self._find_group(browser, "Fittings")
        # n1 and n3 have "cap" fittings; n2 has "no fitting" → excluded
        assert group.childCount() == 2

    def test_fitting_item_stores_node_id(self, qapp):
        """Fitting tree items should store the parent node id."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space()
        n1 = _make_node(ms, 0, 0)
        n2 = _make_node(ms, 1000, 0)
        _make_pipe(ms, n1, n2)
        browser = self._make_browser(ms)
        group = self._find_group(browser, "Fittings")
        assert group is not None
        # Check that at least one child stores a node id
        child = group.child(0)
        from firepro3d.model_browser import _ROLE_ENTITY
        eid = child.data(0, _ROLE_ENTITY)
        assert eid == id(n1) or eid == id(n2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py::TestFittingsBrowserGroup -v`
Expected: FAIL — no Fittings group in browser

- [ ] **Step 3: Add Fittings group to model_browser.py**

In `firepro3d/model_browser.py`, after the Sprinklers group (after line 293), add:

```python
            # -- Fittings --
            all_nodes = list(
                getattr(self._scene, "sprinkler_system", None).nodes
            ) if getattr(self._scene, "sprinkler_system", None) else []
            # Build pipe index for labeling
            pipe_list = list(
                getattr(self._scene, "sprinkler_system", None).pipes
            ) if getattr(self._scene, "sprinkler_system", None) else []
            pipe_idx = {id(p): i for i, p in enumerate(pipe_list, 1)}
            fitting_nodes = [
                n for n in all_nodes
                if n.fitting and n.fitting.type != "no fitting"
            ]
            fittings_root = QTreeWidgetItem(
                self._tree, [f"Fittings ({len(fitting_nodes)})"])
            fittings_root.setFont(0, f_bold)
            for node in fitting_nodes:
                fit = node.fitting
                # Build label: type @ connected pipe indices
                pipe_refs = ", ".join(
                    f"Pipe {pipe_idx.get(id(p), '?')}"
                    for p in node.pipes
                )
                type_name = fit.type.replace("_", " ").title()
                label = f"{type_name} @ {pipe_refs}" if pipe_refs else type_name
                item = QTreeWidgetItem(fittings_root, [label])
                item.setData(0, _ROLE_ENTITY, id(node))
                item.setToolTip(
                    0, f"Level: {node.level}  Type: {fit.type}")
                self._style_hidden(item, fit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py::TestFittingsBrowserGroup -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/ -q --no-header 2>&1 | grep -E "^[0-9]+ (passed|failed)"`
Expected: All pass, no regressions

- [ ] **Step 6: Commit**

```bash
git add firepro3d/model_browser.py tests/test_visibility_display.py
git commit -m "feat: add Fittings group to model browser

Individual fittings listed under 'Fittings (N)' group, labeled by
type and connected pipes. Excludes 'no fitting' type. Selecting a
fitting selects the parent node. Hidden fittings greyed out.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Final Integration Test and Full Suite

**Files:**
- Test: `tests/test_visibility_display.py`

- [ ] **Step 1: Run full test suite**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/ -v --tb=short`
Expected: All tests pass, no regressions

- [ ] **Step 2: Verify test count**

Run: `cd "D:/Custom Code/FirePro3D" && source venv/Scripts/activate && python -m pytest tests/test_visibility_display.py -v`
Expected: ~15 tests, all passing

- [ ] **Step 3: Final commit if any fixups needed**

Only commit if fixups were required. Otherwise, skip this step.
