# Paper Space Display Manager Tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Paper Space" and "Line Weights" tabs to the Display Manager dialog so engineers can control per-category print display (colour, fill, line weight, opacity) independently of the model-space display.

**Architecture:** Temporary mutation approach — viewport rendering saves item display state, applies paper-space overrides, calls `scene.render()`, then restores originals. New data module `paper_display.py` owns line weight definitions, paper-space category settings, color mode state, and the apply/restore logic. The existing `DisplayManager` dialog gains a `QTabWidget` wrapper and two new tab builders.

**Tech Stack:** PyQt6 (QTabWidget, QTreeWidget, QTableWidget, QComboBox), QSettings for persistence, JSON for project file serialization.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `firepro3d/paper_display.py` | **Create** | Line weight definitions, paper-space category defaults, color mode enum, QSettings read/write, factory defaults, apply/restore logic for viewport rendering |
| `firepro3d/display_manager.py` | **Modify** | Wrap existing tree in QTabWidget, add Paper Space tab, add Line Weights tab, context-aware default tab, scoped button bar |
| `firepro3d/paper_space.py` | **Modify** | `SheetViewport.paint()` calls apply/restore around `scene.render()` |
| `firepro3d/scene_io.py` | **Modify** | Save/load `paper_display` key in project JSON |
| `main.py` | **Modify** | Pass active context to `DisplayManager`, apply paper display on project load |
| `tests/test_paper_display.py` | **Create** | Unit + integration tests for all new functionality |

---

### Task 1: Paper Display Data Module

**Files:**
- Create: `firepro3d/paper_display.py`
- Test: `tests/test_paper_display.py`

This task builds the data layer: line weight definitions, paper-space category settings, color mode, QSettings persistence, and factory defaults. No UI yet.

- [ ] **Step 1: Write line weight definition tests**

```python
# tests/test_paper_display.py
"""Tests for the paper-space display data module."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from firepro3d.paper_display import (
    LineWeightDef,
    PaperColorMode,
    FACTORY_LINE_WEIGHTS,
    FACTORY_PAPER_CATEGORIES,
    load_line_weights,
    save_line_weights,
    load_paper_categories,
    save_paper_categories,
    load_paper_color_mode,
    save_paper_color_mode,
    get_paper_display_for_save,
    apply_paper_display_from_project,
)


@pytest.fixture(autouse=True)
def _clean_settings():
    """Clear paper/* QSettings before each test."""
    s = QSettings("GV", "FirePro3D")
    s.remove("paper")
    s.sync()
    yield
    s.remove("paper")
    s.sync()


class TestLineWeightDefs:
    def test_factory_defaults_count(self):
        assert len(FACTORY_LINE_WEIGHTS) == 5

    def test_factory_names(self):
        names = [lw.name for lw in FACTORY_LINE_WEIGHTS]
        assert names == ["Very Light", "Light", "Medium", "Heavy", "Very Heavy"]

    def test_factory_widths(self):
        widths = [lw.width_mm for lw in FACTORY_LINE_WEIGHTS]
        assert widths == [0.13, 0.18, 0.25, 0.35, 0.50]

    def test_sorted_ascending(self):
        widths = [lw.width_mm for lw in FACTORY_LINE_WEIGHTS]
        assert widths == sorted(widths)

    def test_round_trip_qsettings(self):
        defs = [LineWeightDef("Thin", 0.10), LineWeightDef("Thick", 0.60)]
        save_line_weights(defs)
        loaded = load_line_weights()
        assert len(loaded) == 2
        assert loaded[0].name == "Thin"
        assert loaded[0].width_mm == 0.10
        assert loaded[1].name == "Thick"
        assert loaded[1].width_mm == 0.60

    def test_load_returns_factory_when_no_settings(self):
        loaded = load_line_weights()
        assert len(loaded) == 5
        assert loaded[0].name == "Very Light"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_paper_display.py::TestLineWeightDefs -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'firepro3d.paper_display'`

- [ ] **Step 3: Implement line weight definitions**

```python
# firepro3d/paper_display.py
"""
paper_display.py
================
Paper-space display settings — line weight definitions, per-category
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_paper_display.py::TestLineWeightDefs -v`
Expected: All 6 PASS

- [ ] **Step 5: Write color mode and category settings tests**

Add to `tests/test_paper_display.py`:

```python
class TestPaperColorMode:
    def test_default_is_bw(self):
        assert load_paper_color_mode() == PaperColorMode.BW

    def test_round_trip(self):
        save_paper_color_mode(PaperColorMode.FULL_COLOR)
        assert load_paper_color_mode() == PaperColorMode.FULL_COLOR
        save_paper_color_mode(PaperColorMode.CUSTOM)
        assert load_paper_color_mode() == PaperColorMode.CUSTOM

    def test_invalid_value_returns_bw(self):
        s = QSettings("GV", "FirePro3D")
        s.setValue("paper/color_mode", "garbage")
        assert load_paper_color_mode() == PaperColorMode.BW


class TestPaperCategories:
    def test_factory_defaults_all_14_categories(self):
        cats = FACTORY_PAPER_CATEGORIES
        assert len(cats) == 14

    def test_factory_bw_colors(self):
        """Factory default is B&W — all colors black, fills white."""
        for key, vals in FACTORY_PAPER_CATEGORIES.items():
            assert vals["color"] == "#000000", f"{key} color"
            if vals["fill"] is not None:
                assert vals["fill"] == "#ffffff", f"{key} fill"

    def test_factory_wall_heavy(self):
        assert FACTORY_PAPER_CATEGORIES["Wall"]["line_weight"] == "Heavy"

    def test_factory_pipe_medium(self):
        assert FACTORY_PAPER_CATEGORIES["Pipe"]["line_weight"] == "Medium"

    def test_factory_grid_very_light(self):
        assert FACTORY_PAPER_CATEGORIES["Grid Line"]["line_weight"] == "Very Light"

    def test_round_trip_qsettings(self):
        cats = load_paper_categories()
        cats["Pipe"]["line_weight"] = "Heavy"
        save_paper_categories(cats)
        loaded = load_paper_categories()
        assert loaded["Pipe"]["line_weight"] == "Heavy"

    def test_load_returns_factory_when_no_settings(self):
        loaded = load_paper_categories()
        assert loaded["Pipe"]["line_weight"] == "Medium"


class TestProjectPersistence:
    def test_get_paper_display_for_save(self):
        result = get_paper_display_for_save()
        assert "color_mode" in result
        assert "categories" in result
        assert "Pipe" in result["categories"]

    def test_apply_from_project_overrides_settings(self):
        project_data = {
            "color_mode": "full_color",
            "categories": {
                "Pipe": {
                    "color": "#ff0000",
                    "fill": None,
                    "section_color": None,
                    "line_weight": "Heavy",
                    "opacity": 80,
                },
            },
        }
        apply_paper_display_from_project(project_data)
        cats = load_paper_categories()
        assert cats["Pipe"]["line_weight"] == "Heavy"
        assert cats["Pipe"]["opacity"] == 80
        assert load_paper_color_mode() == PaperColorMode.FULL_COLOR

    def test_apply_from_project_missing_key_uses_factory(self):
        apply_paper_display_from_project({})
        cats = load_paper_categories()
        assert cats["Pipe"]["line_weight"] == "Medium"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python -m pytest tests/test_paper_display.py::TestPaperColorMode tests/test_paper_display.py::TestPaperCategories tests/test_paper_display.py::TestProjectPersistence -v`
Expected: FAIL — missing functions

- [ ] **Step 7: Implement color mode and category settings**

Add to `firepro3d/paper_display.py`:

```python
# ---------------------------------------------------------------------------
# Color mode
# ---------------------------------------------------------------------------

class PaperColorMode(Enum):
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


def apply_paper_display_from_project(data: dict):
    """Apply paper display settings loaded from a project file."""
    if not data:
        # No paper_display in project — reset to factory
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
    # Categories — merge project values over factory defaults
    proj_cats = data.get("categories", {})
    merged: dict[str, dict] = {}
    for key in _CATEGORY_KEYS:
        factory = FACTORY_PAPER_CATEGORIES[key]
        proj = proj_cats.get(key, {})
        entry = dict(factory)
        entry.update({k: v for k, v in proj.items() if v is not None})
        merged[key] = entry
    save_paper_categories(merged)
```

- [ ] **Step 8: Run all tests to verify they pass**

Run: `python -m pytest tests/test_paper_display.py -v`
Expected: All 16 PASS

- [ ] **Step 9: Commit**

```bash
git add firepro3d/paper_display.py tests/test_paper_display.py
git commit -m "feat(paper-display): add data module for line weights, category overrides, color mode"
```

---

### Task 2: Viewport Rendering — Apply/Restore Logic

**Files:**
- Modify: `firepro3d/paper_display.py` (add `apply_paper_overrides`, `restore_model_display`)
- Modify: `firepro3d/paper_space.py:419-441` (wrap `scene.render()` with apply/restore)
- Test: `tests/test_paper_display.py`

- [ ] **Step 1: Write apply/restore tests**

Add to `tests/test_paper_display.py`:

```python
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
from PyQt6.QtGui import QPen, QColor
from PyQt6.QtCore import QRectF

from firepro3d.paper_display import (
    apply_paper_overrides, restore_model_display,
    PaperColorMode, save_paper_color_mode, save_paper_categories,
    FACTORY_PAPER_CATEGORIES, resolve_line_weight_mm,
)


class TestApplyRestore:
    """Verify temporary mutation round-trips cleanly."""

    @pytest.fixture
    def scene_with_pipe(self, qapp):
        """Scene with a minimal Pipe mock."""
        from firepro3d.pipe import Pipe
        from firepro3d.node import Node
        scene = QGraphicsScene()
        # Create two nodes so we can make a pipe
        n1 = Node(0, 0)
        n2 = Node(100, 0)
        scene.addItem(n1)
        scene.addItem(n2)
        pipe = Pipe(n1, n2)
        scene.addItem(pipe)
        pipe._display_color = "#4488ff"
        pipe._display_scale = 1.0
        return scene, pipe

    def test_apply_bw_changes_pipe_color(self, scene_with_pipe):
        scene, pipe = scene_with_pipe
        save_paper_color_mode(PaperColorMode.BW)
        source_rect = QRectF(0, 0, 200, 200)
        saved = apply_paper_overrides(scene, source_rect)
        assert pipe._display_color == "#000000"
        restore_model_display(saved)
        assert pipe._display_color == "#4488ff"

    def test_apply_full_color_keeps_model_colors(self, scene_with_pipe):
        scene, pipe = scene_with_pipe
        save_paper_color_mode(PaperColorMode.FULL_COLOR)
        source_rect = QRectF(0, 0, 200, 200)
        saved = apply_paper_overrides(scene, source_rect)
        # Color should stay unchanged in FULL_COLOR mode
        assert pipe._display_color == "#4488ff"
        restore_model_display(saved)

    def test_restore_returns_exact_original_state(self, scene_with_pipe):
        scene, pipe = scene_with_pipe
        original_color = pipe._display_color
        original_opacity = pipe.opacity()
        save_paper_color_mode(PaperColorMode.BW)
        source_rect = QRectF(0, 0, 200, 200)
        saved = apply_paper_overrides(scene, source_rect)
        restore_model_display(saved)
        assert pipe._display_color == original_color
        assert pipe.opacity() == original_opacity


class TestResolveLineWeight:
    def test_known_weight(self):
        mm = resolve_line_weight_mm("Medium")
        assert mm == 0.25

    def test_unknown_weight_returns_default(self):
        mm = resolve_line_weight_mm("Nonexistent")
        assert mm == 0.25  # falls back to Medium
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_paper_display.py::TestApplyRestore tests/test_paper_display.py::TestResolveLineWeight -v`
Expected: FAIL — `ImportError: cannot import name 'apply_paper_overrides'`

- [ ] **Step 3: Implement apply/restore and resolve_line_weight_mm**

Add to `firepro3d/paper_display.py`:

```python
def resolve_line_weight_mm(name: str,
                           settings: QSettings | None = None) -> float:
    """Resolve a line weight name to its mm width.  Falls back to 0.25mm."""
    defs = load_line_weights(settings)
    for d in defs:
        if d.name == name:
            return d.width_mm
    return 0.25  # fallback to Medium


def _category_for_item(item) -> str | None:
    """Map a QGraphicsItem to its display category key.  Returns None for
    items that don't belong to a known category (underlays, annotations,
    construction geometry, etc.)."""
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
    # Fittings are wrappers, not QGraphicsItems — handled separately
    # in apply_paper_overrides (fitting loop after main item loop).
    # RoofItem, FloorSlab, and markers — detect by class name to avoid
    # circular imports (same pattern as display_manager.py).
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

    Returns a list of saved-state dicts for ``restore_model_display()``.
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

        # Save current state
        entry: dict = {
            "item": item,
            "display_color": getattr(item, "_display_color", None),
            "display_fill_color": getattr(item, "_display_fill_color", None),
            "display_section_color": getattr(item, "_display_section_color", None),
            "opacity": item.opacity(),
            "pen": item.pen() if hasattr(item, "pen") else None,
        }
        saved.append(entry)

        # Apply paper-space overrides
        lw_mm = resolve_line_weight_mm(cat["line_weight"])

        if color_mode != PaperColorMode.FULL_COLOR:
            # BW or CUSTOM — apply colour overrides
            item._display_color = cat["color"]
            if hasattr(item, "_display_fill_color") and cat["fill"] is not None:
                item._display_fill_color = cat["fill"]
            if hasattr(item, "_display_section_color") and cat["section_color"] is not None:
                item._display_section_color = cat["section_color"]

            # SVG items need re-rendering
            if isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
                _set_svg_tint(item, cat["color"], cat.get("fill"))

        # Line weight — always applied (even in FULL_COLOR)
        if isinstance(item, Pipe):
            item.set_pipe_display()
            # Override pen width after set_pipe_display sets color
            pen = item.pen()
            pen.setWidthF(lw_mm)
            pen.setCosmetic(False)
            item.setPen(pen)
        elif hasattr(item, "pen") and callable(getattr(item, "setPen", None)):
            pen = item.pen()
            pen.setWidthF(lw_mm)
            pen.setCosmetic(False)
            item.setPen(pen)

        # Opacity — always applied
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

        # Restore SVG items
        if isinstance(item, (Sprinkler, WaterSupply, HydraulicNodeBadge)):
            _set_svg_tint(item, entry["display_color"], entry["display_fill_color"])

        # Restore pen
        if isinstance(item, Pipe):
            item.set_pipe_display()
        elif entry["pen"] is not None and hasattr(item, "setPen"):
            item.setPen(entry["pen"])

        item.update()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_paper_display.py::TestApplyRestore tests/test_paper_display.py::TestResolveLineWeight -v`
Expected: All 5 PASS

- [ ] **Step 5: Wire apply/restore into SheetViewport.paint()**

Modify `firepro3d/paper_space.py:439-441`. Find:

```python
        # Render source scene directly (vector output)
        if self._source_scene is not None and not self._source_rect.isNull() and not self._source_rect.isEmpty():
            self._source_scene.render(painter, vp_rect, self._source_rect)
```

Replace with:

```python
        # Render source scene with paper-space display overrides
        if self._source_scene is not None and not self._source_rect.isNull() and not self._source_rect.isEmpty():
            from firepro3d.paper_display import apply_paper_overrides, restore_model_display
            saved = apply_paper_overrides(self._source_scene, self._source_rect)
            try:
                self._source_scene.render(painter, vp_rect, self._source_rect)
            finally:
                restore_model_display(saved)
```

- [ ] **Step 6: Run existing paper space tests to verify no regressions**

Run: `python -m pytest tests/test_paper_space.py -v`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
git add firepro3d/paper_display.py firepro3d/paper_space.py tests/test_paper_display.py
git commit -m "feat(paper-display): viewport rendering with paper-space display overrides"
```

---

### Task 3: Project File Persistence

**Files:**
- Modify: `firepro3d/scene_io.py:198-205` (save paper_display)
- Modify: `firepro3d/scene_io.py:289` (load paper_display)
- Modify: `main.py:2339-2345` (apply paper display on load)
- Test: `tests/test_paper_display.py`

- [ ] **Step 1: Write project persistence integration test**

Add to `tests/test_paper_display.py`:

```python
import json


class TestProjectFilePersistence:
    def test_save_includes_paper_display(self):
        save_paper_color_mode(PaperColorMode.CUSTOM)
        cats = load_paper_categories()
        cats["Pipe"]["line_weight"] = "Heavy"
        save_paper_categories(cats)
        result = get_paper_display_for_save()
        assert result["color_mode"] == "custom"
        assert result["categories"]["Pipe"]["line_weight"] == "Heavy"

    def test_load_missing_paper_display_uses_factory(self):
        apply_paper_display_from_project({})
        assert load_paper_color_mode() == PaperColorMode.BW
        cats = load_paper_categories()
        assert cats["Pipe"]["line_weight"] == "Medium"

    def test_backward_compat_no_paper_display_key(self):
        """Simulates loading a project file that predates paper_display."""
        apply_paper_display_from_project(None)
        assert load_paper_color_mode() == PaperColorMode.BW
```

- [ ] **Step 2: Update apply_paper_display_from_project to handle None**

In `firepro3d/paper_display.py`, update the guard at the top of `apply_paper_display_from_project`:

```python
def apply_paper_display_from_project(data: dict | None):
    """Apply paper display settings loaded from a project file."""
    if not data:
        # No paper_display in project — reset to factory
        save_paper_color_mode(PaperColorMode.BW)
        save_paper_categories(FACTORY_PAPER_CATEGORIES)
        return
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_paper_display.py::TestProjectFilePersistence -v`
Expected: All 3 PASS

- [ ] **Step 4: Wire save into scene_io.py**

In `firepro3d/scene_io.py`, after line 198 (`display_settings_data = get_display_settings_for_save()`), add:

```python
        from .paper_display import get_paper_display_for_save
        paper_display_data = get_paper_display_for_save()
```

And in the payload dict (around line 205), add after `"display_settings"`:

```python
            "paper_display":       paper_display_data,
```

- [ ] **Step 5: Wire load into scene_io.py**

After line 289 (`self._loaded_display_settings = payload.get("display_settings", None)`), add:

```python
        self._loaded_paper_display = payload.get("paper_display", None)
```

- [ ] **Step 6: Wire apply into main.py**

In `main.py`, after line 2345 (`apply_saved_display_settings(self.scene)`), add:

```python
        # Apply paper-space display settings from project file
        from firepro3d.paper_display import apply_paper_display_from_project
        paper_ds = getattr(self.scene, '_loaded_paper_display', None)
        apply_paper_display_from_project(paper_ds)
```

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `python -m pytest tests/test_paper_display.py tests/test_paper_space.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add firepro3d/scene_io.py main.py firepro3d/paper_display.py tests/test_paper_display.py
git commit -m "feat(paper-display): save/load paper display settings in project file"
```

---

### Task 4: Display Manager — Tab Widget Refactor

**Files:**
- Modify: `firepro3d/display_manager.py:808-1221` (wrap in QTabWidget)
- Modify: `main.py:2211-2215` (pass active context)

This task restructures the dialog without adding new tabs yet — just wraps the existing tree in a "Model" tab inside a `QTabWidget`.

- [ ] **Step 1: Refactor _build_ui to use QTabWidget**

In `firepro3d/display_manager.py`, modify the `DisplayManager.__init__` to accept an `active_context` parameter:

```python
    def __init__(self, scene, parent=None, active_context: str = "model"):
        super().__init__(parent)
        self.setWindowTitle("Display Manager")
        self.setMinimumSize(850, 420)
        self._scene = scene
        self._settings = QSettings("GV", "FirePro3D")
        self._active_context = active_context
```

In `_build_ui`, wrap the tree widget in a tab widget. Find the section where `outer.addWidget(self._tree)` is called (around line 1201) and change the method:

After building `self._tree` and populating it, instead of `outer.addWidget(self._tree)`, do:

```python
        # ── Tab widget ──────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.addTab(self._tree, "Model")
        outer.addWidget(self._tabs)
```

- [ ] **Step 2: Pass active_context from main.py**

In `main.py:2211-2215`, update `_open_display_manager`:

```python
    def _open_display_manager(self):
        """Open the Display Manager dialog (replaces FSVisibilityDialog)."""
        from firepro3d.display_manager import DisplayManager
        from firepro3d.paper_space import PaperSpaceWidget
        ctx = "paper" if isinstance(self.central_tabs.currentWidget(),
                                     PaperSpaceWidget) else "model"
        dlg = DisplayManager(self.scene, parent=self, active_context=ctx)
        dlg.exec()
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add firepro3d/display_manager.py main.py
git commit -m "refactor(display-manager): wrap model tree in QTabWidget, accept active_context"
```

---

### Task 5: Line Weights Tab

**Files:**
- Modify: `firepro3d/display_manager.py` (add `_build_line_weights_tab`)
- Test: `tests/test_paper_display.py`

- [ ] **Step 1: Write line weights tab validation tests**

Add to `tests/test_paper_display.py`:

```python
from firepro3d.paper_display import validate_line_weight_name, validate_line_weight_width


class TestLineWeightValidation:
    def test_reject_empty_name(self):
        existing = [LineWeightDef("Light", 0.18)]
        assert validate_line_weight_name("", existing) is False

    def test_reject_duplicate_name(self):
        existing = [LineWeightDef("Light", 0.18)]
        assert validate_line_weight_name("Light", existing) is False

    def test_accept_unique_name(self):
        existing = [LineWeightDef("Light", 0.18)]
        assert validate_line_weight_name("Heavy", existing) is True

    def test_reject_zero_width(self):
        assert validate_line_weight_width(0.0) is False

    def test_reject_negative_width(self):
        assert validate_line_weight_width(-0.1) is False

    def test_reject_over_max(self):
        assert validate_line_weight_width(3.01) is False

    def test_accept_valid_width(self):
        assert validate_line_weight_width(0.25) is True

    def test_accept_max_width(self):
        assert validate_line_weight_width(3.00) is True
```

- [ ] **Step 2: Implement validation functions**

Add to `firepro3d/paper_display.py`:

```python
def validate_line_weight_name(name: str,
                              existing: list[LineWeightDef]) -> bool:
    """Return True if *name* is valid (non-empty, unique)."""
    if not name or not name.strip():
        return False
    return all(lw.name != name.strip() for lw in existing)


def validate_line_weight_width(width_mm: float) -> bool:
    """Return True if *width_mm* is valid (positive, ≤ 3.0)."""
    return 0.0 < width_mm <= 3.0
```

- [ ] **Step 3: Run validation tests**

Run: `python -m pytest tests/test_paper_display.py::TestLineWeightValidation -v`
Expected: All 8 PASS

- [ ] **Step 4: Build the Line Weights tab UI**

Add method to `DisplayManager` in `firepro3d/display_manager.py`:

```python
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
        # Sort by width ascending
        self._lw_defs.sort(key=lambda d: d.width_mm)
        self._lw_table.setRowCount(len(self._lw_defs))
        for row, lw in enumerate(self._lw_defs):
            name_item = QTableWidgetItem(lw.name)
            width_item = QTableWidgetItem(f"{lw.width_mm:.2f}")
            self._lw_table.setItem(row, 0, name_item)
            self._lw_table.setItem(row, 1, width_item)
        self._suppress = False

    def _on_lw_cell_changed(self, row, col):
        if self._suppress or row >= len(self._lw_defs):
            return
        from .paper_display import (
            validate_line_weight_name, validate_line_weight_width,
            save_line_weights, load_paper_categories, save_paper_categories,
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
            # Cascade rename to paper-space categories
            old_name = old_def.name
            old_def.name = text
            cats = load_paper_categories(self._settings)
            for cat_vals in cats.values():
                if cat_vals.get("line_weight") == old_name:
                    cat_vals["line_weight"] = text
            save_paper_categories(cats, self._settings)
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
        # Refresh paper-space tab dropdowns if present
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()

    def _on_lw_add(self):
        from .paper_display import save_line_weights, LineWeightDef
        # Find a unique name
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
        from .paper_display import save_line_weights, load_paper_categories
        row = self._lw_table.currentRow()
        if row < 0 or row >= len(self._lw_defs):
            return
        name = self._lw_defs[row].name
        # Check if in use
        cats = load_paper_categories(self._settings)
        if any(v.get("line_weight") == name for v in cats.values()):
            return  # silently refuse — button should be disabled
        self._lw_defs.pop(row)
        save_line_weights(self._lw_defs, self._settings)
        self._populate_lw_table()
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()
```

- [ ] **Step 5: Add Line Weights tab to _build_ui**

In `_build_ui`, after adding the Model tab (`self._tabs.addTab(self._tree, "Model")`):

```python
        self._lw_tab = self._build_line_weights_tab()
        self._tabs.addTab(self._lw_tab, "Line Weights")
```

- [ ] **Step 6: Run all tests**

Run: `python -m pytest tests/test_paper_display.py tests/test_paper_space.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add firepro3d/display_manager.py firepro3d/paper_display.py tests/test_paper_display.py
git commit -m "feat(display-manager): add Line Weights definition tab"
```

---

### Task 6: Paper Space Tab

**Files:**
- Modify: `firepro3d/display_manager.py` (add `_build_paper_space_tab`, color mode logic, live preview)

This is the largest UI task — the paper-space category tree with colour swatches, line weight dropdowns, opacity spinners, and color mode dropdown.

- [ ] **Step 1: Build the Paper Space tab**

Add method to `DisplayManager` in `firepro3d/display_manager.py`:

```python
    def _build_paper_space_tab(self) -> QWidget:
        """Build the Paper Space display overrides tab."""
        from .paper_display import (
            load_paper_categories, load_paper_color_mode, save_paper_categories,
            save_paper_color_mode, PaperColorMode, load_line_weights,
            _HAS_FILL, _HAS_SECTION, _CATEGORY_KEYS,
        )

        page = QWidget()
        layout = QVBoxLayout(page)

        # Color mode dropdown
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Color Mode:"))
        self._color_mode_combo = QComboBox()
        self._color_mode_combo.addItems(["Full Color", "B&&W", "Custom"])
        current_mode = load_paper_color_mode(self._settings)
        self._color_mode_combo.setCurrentIndex(
            {"full_color": 0, "bw": 1, "custom": 2}[current_mode.value])
        self._color_mode_combo.currentIndexChanged.connect(
            self._on_color_mode_changed)
        mode_row.addWidget(self._color_mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Paper space category tree
        _P_COL_NAME = 0
        _P_COL_COLOR = 1
        _P_COL_FILL = 2
        _P_COL_SECTION = 3
        _P_COL_LW = 4
        _P_COL_OPACITY = 5

        self._paper_tree = QTreeWidget()
        self._paper_tree.setColumnCount(6)
        self._paper_tree.setHeaderLabels(
            ["Name", "Colour", "Fill", "Section", "Line Weight", "Opacity"])
        self._paper_tree.setRootIsDecorated(True)
        self._paper_tree.setIndentation(20)
        self._paper_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self._paper_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hdr = self._paper_tree.header()
        hdr.setSectionResizeMode(_P_COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col in (_P_COL_COLOR, _P_COL_FILL, _P_COL_SECTION):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self._paper_tree.setColumnWidth(col, 60)
        hdr.setSectionResizeMode(_P_COL_LW, QHeaderView.ResizeMode.Fixed)
        self._paper_tree.setColumnWidth(_P_COL_LW, 100)
        hdr.setSectionResizeMode(_P_COL_OPACITY, QHeaderView.ResizeMode.Fixed)
        self._paper_tree.setColumnWidth(_P_COL_OPACITY, 90)

        cats = load_paper_categories(self._settings)
        lw_defs = load_line_weights(self._settings)
        lw_names = [d.name for d in lw_defs]

        self._paper_cat_data: dict[str, dict] = {}
        self._suppress = True

        _t = th.detect()
        group_font = QFont()
        group_font.setBold(True)
        group_font.setPointSize(group_font.pointSize() + 1)

        _PAPER_GROUPS = {
            "Fire Suppression": ["Pipe", "Sprinkler", "Fitting",
                                 "Water Supply", "Node", "Hydraulic Badge"],
            "Architecture": ["Wall", "Roof", "Room", "Floor"],
            "Grids & Levels": ["Grid Line", "Level Datum",
                               "Elevation Marker", "Detail Marker"],
        }

        for grp_name, keys in _PAPER_GROUPS.items():
            grp_item = QTreeWidgetItem(self._paper_tree)
            grp_item.setText(0, grp_name)
            grp_item.setFont(0, group_font)
            grp_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            grp_item.setExpanded(True)
            grp_item.setForeground(0, QColor(_t.text_primary))

            for key in keys:
                cat_vals = cats[key]
                cat_item = QTreeWidgetItem(grp_item)
                cat_item.setText(0, key)
                cat_item.setFont(0, QFont())

                # Colour swatch
                color_btn = QPushButton()
                color_btn.setFixedSize(40, 20)
                color_btn.setProperty("_color", cat_vals["color"])
                self._update_color_btn(color_btn, cat_vals["color"])
                color_btn.clicked.connect(
                    lambda _, k=key: self._on_paper_color_clicked(k, "color"))
                self._paper_tree.setItemWidget(cat_item, _P_COL_COLOR, color_btn)

                # Fill swatch
                fill_btn = QPushButton()
                fill_btn.setFixedSize(40, 20)
                if key in _HAS_FILL and cat_vals["fill"]:
                    fill_btn.setProperty("_color", cat_vals["fill"])
                    self._update_color_btn(fill_btn, cat_vals["fill"])
                else:
                    fill_btn.setEnabled(False)
                fill_btn.clicked.connect(
                    lambda _, k=key: self._on_paper_color_clicked(k, "fill"))
                self._paper_tree.setItemWidget(cat_item, _P_COL_FILL, fill_btn)

                # Section swatch
                section_btn = QPushButton()
                section_btn.setFixedSize(40, 20)
                if key in _HAS_SECTION and cat_vals["section_color"]:
                    section_btn.setProperty("_color", cat_vals["section_color"])
                    self._update_color_btn(section_btn, cat_vals["section_color"])
                else:
                    section_btn.setEnabled(False)
                section_btn.clicked.connect(
                    lambda _, k=key: self._on_paper_color_clicked(k, "section_color"))
                self._paper_tree.setItemWidget(cat_item, _P_COL_SECTION, section_btn)

                # Line weight dropdown
                lw_combo = QComboBox()
                lw_combo.addItems(lw_names)
                cur_lw = cat_vals.get("line_weight", "Medium")
                idx = lw_combo.findText(cur_lw)
                if idx >= 0:
                    lw_combo.setCurrentIndex(idx)
                lw_combo.currentTextChanged.connect(
                    lambda text, k=key: self._on_paper_lw_changed(k, text))
                self._paper_tree.setItemWidget(cat_item, _P_COL_LW, lw_combo)

                # Opacity
                opa_spin = QSpinBox()
                opa_spin.setRange(0, 100)
                opa_spin.setSuffix("%")
                opa_spin.setValue(cat_vals.get("opacity", 100))
                opa_spin.valueChanged.connect(
                    lambda val, k=key: self._on_paper_opacity_changed(k, val))
                self._paper_tree.setItemWidget(cat_item, _P_COL_OPACITY, opa_spin)

                self._paper_cat_data[key] = {
                    "tree_item": cat_item,
                    "color_btn": color_btn,
                    "fill_btn": fill_btn,
                    "section_btn": section_btn,
                    "lw_combo": lw_combo,
                    "opacity": opa_spin,
                }

        self._suppress = False
        self._apply_color_mode_ui(current_mode)
        layout.addWidget(self._paper_tree)
        return page

    def _on_color_mode_changed(self, index):
        from .paper_display import (
            PaperColorMode, save_paper_color_mode,
            save_paper_categories, load_paper_categories,
            FACTORY_PAPER_CATEGORIES, _HAS_FILL, _HAS_SECTION,
        )
        modes = [PaperColorMode.FULL_COLOR, PaperColorMode.BW,
                 PaperColorMode.CUSTOM]
        mode = modes[index]
        save_paper_color_mode(mode, self._settings)

        if mode == PaperColorMode.BW:
            # Populate all colours with black/white
            cats = load_paper_categories(self._settings)
            for key, vals in cats.items():
                vals["color"] = "#000000"
                if key in _HAS_FILL:
                    vals["fill"] = "#ffffff"
                if key in _HAS_SECTION:
                    vals["section_color"] = "#000000"
            save_paper_categories(cats, self._settings)
            self._suppress = True
            for key, widgets in self._paper_cat_data.items():
                self._update_color_btn(widgets["color_btn"], "#000000")
                widgets["color_btn"].setProperty("_color", "#000000")
                if widgets["fill_btn"].isEnabled():
                    self._update_color_btn(widgets["fill_btn"], "#ffffff")
                    widgets["fill_btn"].setProperty("_color", "#ffffff")
                if widgets["section_btn"].isEnabled():
                    self._update_color_btn(widgets["section_btn"], "#000000")
                    widgets["section_btn"].setProperty("_color", "#000000")
            self._suppress = False

        self._apply_color_mode_ui(mode)
        if not self._suppress:
            self._apply_paper_preview()

    def _apply_color_mode_ui(self, mode):
        """Enable/disable colour columns based on color mode."""
        from .paper_display import PaperColorMode
        disable_colors = (mode == PaperColorMode.FULL_COLOR)
        for key, widgets in self._paper_cat_data.items():
            widgets["color_btn"].setDisabled(disable_colors)
            if widgets["fill_btn"].isEnabled() or not disable_colors:
                # Only re-enable fill if the category supports it
                from .paper_display import _HAS_FILL
                widgets["fill_btn"].setDisabled(
                    disable_colors or key not in _HAS_FILL)
            if widgets["section_btn"].isEnabled() or not disable_colors:
                from .paper_display import _HAS_SECTION
                widgets["section_btn"].setDisabled(
                    disable_colors or key not in _HAS_SECTION)

    def _on_paper_color_clicked(self, key, prop):
        widgets = self._paper_cat_data[key]
        btn_map = {"color": "color_btn", "fill": "fill_btn",
                   "section_color": "section_btn"}
        btn = widgets[btn_map[prop]]
        cur = btn.property("_color") or "#000000"
        color = QColorDialog.getColor(QColor(cur), self,
                                      f"{key} — {prop.replace('_', ' ').title()}")
        if not color.isValid():
            return
        hex_color = color.name()
        btn.setProperty("_color", hex_color)
        self._update_color_btn(btn, hex_color)
        # Auto-switch to Custom mode
        from .paper_display import (
            PaperColorMode, save_paper_color_mode,
            save_paper_categories, load_paper_categories,
        )
        cur_mode_idx = self._color_mode_combo.currentIndex()
        if cur_mode_idx != 2:  # not already Custom
            self._suppress = True
            self._color_mode_combo.setCurrentIndex(2)
            save_paper_color_mode(PaperColorMode.CUSTOM, self._settings)
            self._suppress = False
        # Save
        cats = load_paper_categories(self._settings)
        cats[key][prop] = hex_color
        save_paper_categories(cats, self._settings)
        if not self._suppress:
            self._apply_paper_preview()

    def _on_paper_lw_changed(self, key, text):
        if self._suppress:
            return
        from .paper_display import load_paper_categories, save_paper_categories
        cats = load_paper_categories(self._settings)
        cats[key]["line_weight"] = text
        save_paper_categories(cats, self._settings)
        self._apply_paper_preview()

    def _on_paper_opacity_changed(self, key, val):
        if self._suppress:
            return
        from .paper_display import load_paper_categories, save_paper_categories
        cats = load_paper_categories(self._settings)
        cats[key]["opacity"] = val
        save_paper_categories(cats, self._settings)
        self._apply_paper_preview()

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
                # Fallback to nearest available
                cat_lw = cats[key].get("line_weight", "Medium")
                idx = combo.findText(cat_lw)
                combo.setCurrentIndex(max(0, idx))
        self._suppress = False

    def _apply_paper_preview(self):
        """Trigger paper-space viewport refresh for live preview."""
        # Mark all paper space viewports dirty
        parent = self.parent()
        if parent is not None and hasattr(parent, "paper_space_widget"):
            ps_widget = parent.paper_space_widget
            if ps_widget is not None and hasattr(ps_widget, "paper_scene"):
                ps_widget.paper_scene.update()
```

- [ ] **Step 2: Add Paper Space tab to _build_ui**

In `_build_ui`, after the Line Weights tab addition:

```python
        self._paper_tab = self._build_paper_space_tab()
        self._tabs.insertTab(1, self._paper_tab, "Paper Space")
```

And set the default tab based on context:

```python
        # Default tab based on active context
        if self._active_context == "paper":
            self._tabs.setCurrentIndex(1)  # Paper Space tab
```

- [ ] **Step 3: Update accept/reject for paper-space tab**

In `DisplayManager.accept()`, after the existing QSettings persistence, add:

```python
        # Paper-space settings are already saved to QSettings during editing
        # (via save_paper_categories / save_paper_color_mode).
        # Nothing extra needed here.
```

In `DisplayManager.reject()`, before `super().reject()`, add paper-space snapshot restore:

```python
        # Restore paper-space settings
        if hasattr(self, "_paper_settings_snapshot"):
            from .paper_display import (
                save_paper_categories, save_paper_color_mode, PaperColorMode,
            )
            save_paper_categories(self._paper_settings_snapshot["categories"],
                                  self._settings)
            save_paper_color_mode(
                PaperColorMode(self._paper_settings_snapshot["color_mode"]),
                self._settings)
```

And in `__init__`, after `self._take_snapshot()`, snapshot paper settings:

```python
        from .paper_display import load_paper_categories, load_paper_color_mode
        self._paper_settings_snapshot = {
            "categories": load_paper_categories(self._settings),
            "color_mode": load_paper_color_mode(self._settings).value,
        }
```

- [ ] **Step 4: Scope button bar actions to active tab**

Update `_reset_all` to check the active tab:

```python
    def _reset_all(self):
        """Reset the active tab to factory defaults."""
        idx = self._tabs.currentIndex()
        if idx == 0:
            # Model tab — existing reset logic
            self._reset_model_tab()
        elif idx == 1:
            # Paper Space tab
            self._reset_paper_space_tab()
        elif idx == 2:
            # Line Weights tab
            self._reset_line_weights_tab()
```

Rename the existing `_reset_all` body to `_reset_model_tab` and add:

```python
    def _reset_paper_space_tab(self):
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
        self._suppress = False
        self._apply_color_mode_ui(PaperColorMode.BW)
        self._apply_paper_preview()

    def _reset_line_weights_tab(self):
        from .paper_display import FACTORY_LINE_WEIGHTS, save_line_weights, LineWeightDef
        self._lw_defs = [LineWeightDef(d.name, d.width_mm)
                         for d in FACTORY_LINE_WEIGHTS]
        save_line_weights(self._lw_defs, self._settings)
        self._populate_lw_table()
        if hasattr(self, "_paper_cat_data"):
            self._refresh_lw_combos()
```

Similarly scope `_set_as_default`:

```python
    def _set_as_default(self):
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._set_model_as_default()
        elif idx == 1:
            # Paper-space settings are already in QSettings — just sync
            self._settings.sync()
        elif idx == 2:
            # Line weights are already in QSettings — just sync
            self._settings.sync()
```

Rename the existing `_set_as_default` body to `_set_model_as_default`.

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/test_paper_display.py tests/test_paper_space.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add firepro3d/display_manager.py
git commit -m "feat(display-manager): add Paper Space tab with color mode, line weight dropdowns, live preview"
```

---

### Task 7: Line Weights Tab Snapshot/Restore + Remove Guard

**Files:**
- Modify: `firepro3d/display_manager.py` (snapshot/restore for Line Weights tab, remove-guard UI)

- [ ] **Step 1: Add snapshot/restore for line weights**

In `DisplayManager.reject()`, before `super().reject()`, restore line weights:

```python
        if hasattr(self, "_lw_snapshot"):
            from .paper_display import save_line_weights
            save_line_weights(self._lw_snapshot, self._settings)
```

The `_lw_snapshot` was already created in `_build_line_weights_tab`.

- [ ] **Step 2: Add remove-guard (disable when in use)**

In `_build_line_weights_tab`, connect selection change to update remove button state:

```python
        self._lw_table.currentCellChanged.connect(self._update_lw_remove_state)
```

Add the method:

```python
    def _update_lw_remove_state(self, row, col, prev_row, prev_col):
        """Disable Remove button if the selected weight is in use."""
        from .paper_display import load_paper_categories
        if row < 0 or row >= len(self._lw_defs):
            self._lw_remove_btn.setEnabled(False)
            return
        name = self._lw_defs[row].name
        cats = load_paper_categories(self._settings)
        in_use = any(v.get("line_weight") == name for v in cats.values())
        self._lw_remove_btn.setEnabled(not in_use)
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add firepro3d/display_manager.py
git commit -m "fix(display-manager): line weights snapshot/restore on cancel, remove-guard"
```

---

### Task 8: Integration Tests

**Files:**
- Modify: `tests/test_paper_display.py`

- [ ] **Step 1: Write integration tests**

Add to `tests/test_paper_display.py`:

```python
class TestViewportIntegration:
    """Integration tests for viewport rendering with paper display overrides."""

    @pytest.fixture
    def scene_with_wall(self, qapp):
        from firepro3d.wall import WallSegment
        scene = QGraphicsScene()
        wall = WallSegment(0, 0, 200, 0, thickness=100)
        scene.addItem(wall)
        wall._display_color = "#666666"
        return scene, wall

    def test_bw_mode_sets_wall_black(self, scene_with_wall):
        scene, wall = scene_with_wall
        save_paper_color_mode(PaperColorMode.BW)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        assert wall._display_color == "#000000"
        restore_model_display(saved)
        assert wall._display_color == "#666666"

    def test_line_weight_applied(self, scene_with_wall):
        scene, wall = scene_with_wall
        cats = load_paper_categories()
        cats["Wall"]["line_weight"] = "Heavy"
        save_paper_categories(cats)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        pen = wall.pen()
        assert pen.widthF() == pytest.approx(0.35, abs=0.01)
        assert pen.isCosmetic() is False
        restore_model_display(saved)

    def test_full_color_preserves_model_colors(self, scene_with_wall):
        scene, wall = scene_with_wall
        save_paper_color_mode(PaperColorMode.FULL_COLOR)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        assert wall._display_color == "#666666"  # unchanged
        restore_model_display(saved)

    def test_opacity_applied(self, scene_with_wall):
        scene, wall = scene_with_wall
        cats = load_paper_categories()
        cats["Wall"]["opacity"] = 50
        save_paper_categories(cats)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        assert wall.opacity() == pytest.approx(0.5, abs=0.01)
        restore_model_display(saved)
        assert wall.opacity() == pytest.approx(1.0, abs=0.01)

    def test_per_instance_override_ignored_in_paper_space(self, scene_with_wall):
        """Paper-space category settings override model per-instance overrides."""
        scene, wall = scene_with_wall
        wall._display_overrides = {"color": "#ff0000"}
        wall._display_color = "#ff0000"  # per-instance red
        save_paper_color_mode(PaperColorMode.BW)
        source_rect = QRectF(-10, -60, 220, 120)
        saved = apply_paper_overrides(scene, source_rect)
        assert wall._display_color == "#000000"  # B&W wins
        restore_model_display(saved)
        assert wall._display_color == "#ff0000"  # restored


class TestProjectRoundTrip:
    def test_save_load_round_trip(self):
        """Verify paper display survives project save → load cycle."""
        save_paper_color_mode(PaperColorMode.CUSTOM)
        cats = load_paper_categories()
        cats["Pipe"]["line_weight"] = "Heavy"
        cats["Pipe"]["opacity"] = 75
        save_paper_categories(cats)

        # Simulate save
        saved_data = get_paper_display_for_save()

        # Simulate loading into a fresh session
        save_paper_color_mode(PaperColorMode.BW)  # reset
        save_paper_categories(FACTORY_PAPER_CATEGORIES)

        # Load
        apply_paper_display_from_project(saved_data)
        assert load_paper_color_mode() == PaperColorMode.CUSTOM
        loaded = load_paper_categories()
        assert loaded["Pipe"]["line_weight"] == "Heavy"
        assert loaded["Pipe"]["opacity"] == 75
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/test_paper_display.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_paper_display.py
git commit -m "test(paper-display): integration tests for viewport rendering and project round-trip"
```

---

### Task 9: Final Wiring & Edge Cases

**Files:**
- Modify: `firepro3d/paper_display.py` (fitting handling in apply/restore)
- Modify: `firepro3d/display_manager.py` (detail/elevation marker detection)

- [ ] **Step 1: Add Fitting handling to apply/restore**

Fittings are non-QGraphicsItem wrappers — their symbols are separate SVG items. In `apply_paper_overrides`, after the main item loop, add fitting handling:

```python
    # Handle Fittings separately (wrappers, not QGraphicsItems)
    if hasattr(scene, "sprinkler_system"):
        for node in scene.sprinkler_system.nodes:
            f = node.fitting
            if f is None or f.symbol is None or not f.symbol.isVisible():
                continue
            # Check if fitting symbol is within source_rect
            if not source_rect.contains(f.symbol.scenePos()):
                continue
            cat = cats.get("Fitting")
            if cat is None:
                continue
            entry = {
                "item": f.symbol,
                "fitting": f,
                "display_color": getattr(f, "_display_color", None),
                "display_fill_color": getattr(f, "_display_fill_color", None),
                "opacity": f.symbol.opacity(),
                "pen": None,
            }
            saved.append(entry)
            lw_mm = resolve_line_weight_mm(cat["line_weight"])
            if color_mode != PaperColorMode.FULL_COLOR:
                _set_svg_tint(f.symbol, cat["color"], cat.get("fill"))
                f._display_color = cat["color"]
                f._display_fill_color = cat.get("fill")
            f.symbol.setOpacity(cat["opacity"] / 100.0)
```

In `restore_model_display`, add:

```python
        # Restore fitting wrapper attributes
        fitting = entry.get("fitting")
        if fitting is not None:
            fitting._display_color = entry["display_color"]
            fitting._display_fill_color = entry["display_fill_color"]
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add firepro3d/paper_display.py firepro3d/display_manager.py
git commit -m "fix(paper-display): fitting handling in apply/restore"
```

---

### Task 10: Spec Verification & Cleanup

- [ ] **Step 1: Verify all 11 acceptance criteria from the spec**

Walk through each criterion in `docs/superpowers/specs/2026-05-12-paper-space-display-manager-design.md` §8 and confirm it is implemented:

1. ✓ 3 tabs: Model, Paper Space, Line Weights
2. ✓ 14 categories, 5 columns (no Visible/Scale/Font/per-instance)
3. ✓ Color Mode dropdown with state transitions
4. ✓ Line Weights editable table with factory defaults
5. ✓ Viewport temporary mutation overrides
6. ✓ Real pen widths (non-cosmetic)
7. ✓ Live preview + cancel revert
8. ✓ Persistence in QSettings + project file
9. ✓ Default tab from active context
10. ✓ Default color mode B&W
11. ✓ Button bar scoped to active tab

- [ ] **Step 2: Run final full test suite**

Run: `python -m pytest tests/ -v --timeout=120`
Expected: All PASS

- [ ] **Step 3: Commit any remaining fixes**

```bash
git add -A
git commit -m "chore(paper-display): final cleanup and spec verification"
```
