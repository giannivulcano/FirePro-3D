# Underlay Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the P1 underlay cluster — data model, path resolution, file-not-found handling, transform origin fix, per-level visibility, per-source-layer visibility, DXF entity coverage, and browser tree integration.

**Architecture:** The `Underlay` dataclass gains four new fields (level, visible, hidden_layers, import_mode). Path resolution converts to relative paths at save time via helpers on the dataclass. Level visibility is Z-value-based, added to `LevelManager.apply_to_scene()`. Browser tree gets an "Underlays" category with source-layer children and full context menu. DXF import gains INSERT/HATCH/DIMENSION support via ezdxf's `virtual_entities()`.

**Tech Stack:** Python 3.x, PyQt6, ezdxf, pytest

**Spec:** `docs/specs/underlay-workflow.md` (Revision 2)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `firepro3d/underlay.py` | Modify | Add new fields, update serialization, add path helpers, add `get_properties()` |
| `firepro3d/dxf_import_worker.py` | Modify | Add INSERT/HATCH/DIMENSION entity support |
| `firepro3d/model_space.py` | Modify | Transform origin fix, placeholder creation, hidden_layers application, level default on import |
| `firepro3d/scene_io.py` | Modify | Path resolution on save/load, missing file handling, aggregate warning |
| `firepro3d/level_manager.py` | Modify | Add underlay visibility block in `apply_to_scene()` |
| `firepro3d/model_browser.py` | Modify | Add Underlays category, underlay click/context menu handling |
| `firepro3d/underlay_context_menu.py` | Modify | Inherit `hidden_layers` on duplicate, add new fields to duplicate |
| `tests/test_underlay.py` | Create | Unit tests for serialization, backward compat, path resolution |

## Task Dependency Graph

```
Task 1 (data model) ──┬── Task 4 (path resolution) ── Task 7 (file-not-found)
                       ├── Task 5 (level visibility)                            ├── Task 8 (browser tree)
                       ├── Task 6 (source-layer vis + duplicate)                │
Task 2 (DXF entities)  (independent)                                            │
Task 3 (transform origin) (independent)                                         │
                                                                                └── Task 9 (verify)
```

**Parallel groups:**
- **Group A** (independent): Tasks 1, 2, 3
- **Group B** (needs Task 1): Tasks 4, 5, 6
- **Group C** (needs Task 4): Task 7
- **Group D** (needs Tasks 1, 5, 6, 7): Task 8
- **Final**: Task 9

---

### Task 1: Underlay Data Model + Serialization

**Files:**
- Modify: `firepro3d/underlay.py`
- Create: `tests/test_underlay.py`

- [ ] **Step 1: Write failing tests for new fields and serialization**

```python
# tests/test_underlay.py
"""Unit tests for the Underlay data model."""
import pytest
from firepro3d.underlay import Underlay
from firepro3d.constants import DEFAULT_LEVEL, DEFAULT_USER_LAYER


class TestUnderlayFields:
    """New fields exist with correct defaults."""

    def test_default_level(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.level == DEFAULT_LEVEL

    def test_default_visible(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.visible is True

    def test_default_hidden_layers(self):
        u = Underlay(type="dxf", path="test.dxf")
        assert u.hidden_layers == []

    def test_default_import_mode(self):
        u = Underlay(type="pdf", path="test.pdf")
        assert u.import_mode == "auto"

    def test_hidden_layers_not_shared(self):
        """Each instance gets its own list (field default_factory)."""
        a = Underlay(type="dxf", path="a.dxf")
        b = Underlay(type="dxf", path="b.dxf")
        a.hidden_layers.append("Layer0")
        assert b.hidden_layers == []


class TestUnderlaySerialization:
    """to_dict / from_dict round-trip and backward compat."""

    def test_round_trip_dxf(self):
        u = Underlay(
            type="dxf", path="plans/floor1.dxf",
            x=10.0, y=20.0, scale=2.5, rotation=45.0, opacity=0.8,
            locked=True, colour="#ff0000", line_weight=0.5,
            user_layer="Underlay",
            level="Level 2", visible=False,
            hidden_layers=["A-FURN", "A-ELEC"], import_mode="auto",
        )
        d = u.to_dict()
        u2 = Underlay.from_dict(d)
        assert u2.type == "dxf"
        assert u2.path == "plans/floor1.dxf"
        assert u2.level == "Level 2"
        assert u2.visible is False
        assert u2.hidden_layers == ["A-FURN", "A-ELEC"]
        assert u2.import_mode == "auto"
        assert u2.colour == "#ff0000"
        assert u2.line_weight == 0.5

    def test_round_trip_pdf(self):
        u = Underlay(
            type="pdf", path="plans/sheet.pdf",
            page=2, dpi=300, import_mode="raster",
            level="*", visible=True,
        )
        d = u.to_dict()
        u2 = Underlay.from_dict(d)
        assert u2.page == 2
        assert u2.dpi == 300
        assert u2.import_mode == "raster"
        assert u2.level == "*"

    def test_backward_compat_missing_new_fields(self):
        """Old project files lack level/visible/hidden_layers/import_mode."""
        old_dict = {
            "type": "dxf", "path": "old.dxf",
            "x": 0.0, "y": 0.0, "scale": 1.0,
            "rotation": 0.0, "opacity": 1.0, "locked": False,
            "colour": "#ffffff", "line_weight": 0.0,
            "user_layer": "Default",
        }
        u = Underlay.from_dict(old_dict)
        assert u.level == DEFAULT_LEVEL
        assert u.visible is True
        assert u.hidden_layers == []
        assert u.import_mode == "auto"

    def test_to_dict_includes_new_fields(self):
        u = Underlay(type="dxf", path="test.dxf", level="Level 3",
                     visible=False, hidden_layers=["X"], import_mode="auto")
        d = u.to_dict()
        assert d["level"] == "Level 3"
        assert d["visible"] is False
        assert d["hidden_layers"] == ["X"]
        assert d["import_mode"] == "auto"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\Custom Code\FirePro3D && python -m pytest tests/test_underlay.py -v`
Expected: FAIL — `Underlay.__init__() got an unexpected keyword argument 'level'`

- [ ] **Step 3: Add new fields to Underlay dataclass**

In `firepro3d/underlay.py`, add after the `user_layer` field (line 29):

```python
from dataclasses import dataclass, field
```

And add new fields:

```python
    # New fields (Revision 2)
    level: str = DEFAULT_LEVEL            # Level assignment ("*" = all levels)
    visible: bool = True                  # User's explicit visibility toggle
    hidden_layers: list[str] = field(default_factory=list)  # Hidden DXF layer names
    import_mode: str = "auto"             # PDF: "auto" | "vector" | "raster"
```

Also need to import `DEFAULT_LEVEL` — it's not currently imported. Add to the imports:

```python
from .constants import DEFAULT_USER_LAYER, DEFAULT_LEVEL
```

- [ ] **Step 4: Update `to_dict()` to include new fields**

In `firepro3d/underlay.py`, in `to_dict()`, add before `return d` (after the `d["user_layer"]` line):

```python
        d["level"] = self.level
        d["visible"] = self.visible
        d["hidden_layers"] = list(self.hidden_layers)  # defensive copy
        d["import_mode"] = self.import_mode
```

- [ ] **Step 5: Update `from_dict()` to read new fields with backward-compat defaults**

In `firepro3d/underlay.py`, in `from_dict()`, add the new keyword arguments:

```python
    @staticmethod
    def from_dict(d: dict) -> "Underlay":
        return Underlay(
            type        = d["type"],
            path        = d["path"],
            x           = d.get("x", 0.0),
            y           = d.get("y", 0.0),
            scale       = d.get("scale", 1.0),
            rotation    = d.get("rotation", 0.0),
            opacity     = d.get("opacity", 1.0),
            locked      = d.get("locked", False),
            page        = d.get("page", 0),
            dpi         = d.get("dpi", 150),
            colour      = d.get("colour", "#ffffff"),
            line_weight = d.get("line_weight", 0),
            user_layer  = d.get("user_layer", DEFAULT_USER_LAYER),
            level       = d.get("level", DEFAULT_LEVEL),
            visible     = d.get("visible", True),
            hidden_layers = d.get("hidden_layers", []),
            import_mode = d.get("import_mode", "auto"),
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd D:\Custom Code\FirePro3D && python -m pytest tests/test_underlay.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add firepro3d/underlay.py tests/test_underlay.py
git commit -m "feat(underlay): add level, visible, hidden_layers, import_mode fields with serialization"
```

---

### Task 2: DXF Entity Coverage (INSERT / HATCH / DIMENSION)

**Files:**
- Modify: `firepro3d/dxf_import_worker.py`

- [ ] **Step 1: Update `run()` to handle list returns from `_extract_geometry`**

In `firepro3d/dxf_import_worker.py`, replace the geometry extraction block in `run()` (lines 123-128):

```python
            try:
                result = self._extract_geometry(entity)
                if result is not None:
                    if isinstance(result, list):
                        geometries.extend(result)
                    else:
                        geometries.append(result)
            except Exception:
                skipped += 1
```

- [ ] **Step 2: Add INSERT/HATCH/DIMENSION handling in `_extract_geometry`**

In `firepro3d/dxf_import_worker.py`, add before the final `return None` (line 241):

```python
        elif etype in ("INSERT", "DIMENSION", "HATCH"):
            # Explode block references, dimensions, and hatches into
            # constituent geometry via ezdxf's virtual_entities().
            results = []
            try:
                for sub_entity in entity.virtual_entities():
                    sub_geom = self._extract_geometry(sub_entity)
                    if sub_geom is not None:
                        if isinstance(sub_geom, list):
                            results.extend(sub_geom)
                        else:
                            results.append(sub_geom)
            except Exception:
                pass
            return results if results else None
```

This is recursive — nested INSERTs (blocks within blocks) are handled automatically. The layer name propagates from each virtual entity's own DXF layer attribute.

- [ ] **Step 3: Verify with a test DXF file**

Run: `cd D:\Custom Code\FirePro3D && python -c "from firepro3d.dxf_import_worker import DxfImportWorker; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 4: Commit**

```bash
git add firepro3d/dxf_import_worker.py
git commit -m "feat(dxf): add INSERT, HATCH, DIMENSION entity support via virtual_entities"
```

---

### Task 3: Transform Origin Fix

**Files:**
- Modify: `firepro3d/model_space.py:2224-2231` (`_apply_underlay_display`)

- [ ] **Step 1: Update `_apply_underlay_display` to set transform origin**

In `firepro3d/model_space.py`, replace the `_apply_underlay_display` method (lines 2224-2231):

```python
    def _apply_underlay_display(self, item: QGraphicsItem, record: Underlay):
        """Apply transform origin, scale, rotation, opacity, and lock state."""
        # Set origin to center BEFORE applying scale/rotation (spec §6.2)
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setScale(record.scale)
        item.setRotation(record.rotation)
        item.setOpacity(record.opacity)
        if record.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
```

- [ ] **Step 2: Commit**

```bash
git add firepro3d/model_space.py
git commit -m "fix(underlay): set transform origin to bounding rect center"
```

---

### Task 4: Path Resolution

**Depends on:** Task 1

**Files:**
- Modify: `firepro3d/underlay.py` (add static path helpers)
- Modify: `firepro3d/scene_io.py:132-141` (save), `firepro3d/scene_io.py:435-444` (load)
- Modify: `tests/test_underlay.py` (add path tests)

- [ ] **Step 1: Write failing tests for path resolution**

Append to `tests/test_underlay.py`:

```python
import os
import tempfile


class TestPathResolution:
    """Path relativize / resolve helpers."""

    def test_relativize_same_dir(self):
        project_dir = "/projects/building"
        abs_path = "/projects/building/plans/floor1.dxf"
        result = Underlay.relativize_path(abs_path, project_dir)
        assert result == os.path.join("plans", "floor1.dxf")

    def test_relativize_one_level_up(self):
        project_dir = "/projects/building"
        abs_path = "/projects/shared/floor1.dxf"
        result = Underlay.relativize_path(abs_path, project_dir)
        # One ".." — acceptable
        assert ".." in result
        assert result.endswith("floor1.dxf")

    def test_relativize_deep_traversal_returns_absolute(self):
        project_dir = "/projects/a/b/c"
        abs_path = "/other/deep/file.dxf"
        result = Underlay.relativize_path(abs_path, project_dir)
        # 3+ parent traversals → absolute path returned
        assert os.path.isabs(result)

    def test_resolve_relative_path(self, tmp_path):
        # Create a file in a subdirectory
        plans = tmp_path / "plans"
        plans.mkdir()
        dxf = plans / "floor1.dxf"
        dxf.write_text("dummy")
        result = Underlay.resolve_path("plans/floor1.dxf", str(tmp_path))
        assert result is not None
        assert os.path.exists(result)

    def test_resolve_absolute_path(self, tmp_path):
        dxf = tmp_path / "floor1.dxf"
        dxf.write_text("dummy")
        result = Underlay.resolve_path(str(dxf), str(tmp_path))
        assert result == str(dxf)

    def test_resolve_missing_returns_none(self, tmp_path):
        result = Underlay.resolve_path("nonexistent.dxf", str(tmp_path))
        assert result is None

    def test_resolve_relative_fallback_to_absolute(self, tmp_path):
        """Relative resolution fails but stored path exists as absolute."""
        dxf = tmp_path / "floor1.dxf"
        dxf.write_text("dummy")
        # Pass a different project_dir so relative resolution fails,
        # but the stored path happens to be absolute and exists
        result = Underlay.resolve_path(str(dxf), "/some/other/dir")
        assert result == str(dxf)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\Custom Code\FirePro3D && python -m pytest tests/test_underlay.py::TestPathResolution -v`
Expected: FAIL — `Underlay has no attribute 'relativize_path'`

- [ ] **Step 3: Implement path helpers on Underlay**

In `firepro3d/underlay.py`, add `import os` at the top, then add these static methods to the `Underlay` class after `from_dict`:

```python
    @staticmethod
    def relativize_path(abs_path: str, project_dir: str) -> str:
        """Convert absolute path to relative if the result is sensible.

        Returns absolute path if the relative form requires 3+ parent
        traversals (``../../../`` or deeper) or if the paths are on
        different drives (Windows).
        """
        try:
            rel = os.path.relpath(abs_path, project_dir)
        except ValueError:
            # Different drive on Windows
            return abs_path
        parts = rel.replace("\\", "/").split("/")
        parent_count = sum(1 for p in parts if p == "..")
        if parent_count >= 3:
            return abs_path
        return rel

    @staticmethod
    def resolve_path(stored_path: str, project_dir: str) -> str | None:
        """Resolve a stored underlay path to an existing absolute path.

        Returns ``None`` if the file cannot be found.

        Resolution order:
        1. If relative, resolve against *project_dir*.
        2. If that doesn't exist, try stored path as absolute.
        3. If absolute and exists, return as-is.
        """
        if os.path.isabs(stored_path):
            if os.path.exists(stored_path):
                return stored_path
            return None
        # Relative — resolve against project dir
        resolved = os.path.normpath(os.path.join(project_dir, stored_path))
        if os.path.exists(resolved):
            return resolved
        # Fallback: try stored path as absolute (project moved, underlay didn't)
        if os.path.exists(stored_path):
            return stored_path
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\Custom Code\FirePro3D && python -m pytest tests/test_underlay.py::TestPathResolution -v`
Expected: All PASS

- [ ] **Step 5: Update `save_to_file` to relativize paths**

In `firepro3d/scene_io.py`, the underlay save block (lines 132-141). Replace:

```python
        # --- Underlays ---
        underlays_data = []
        project_dir = os.path.dirname(os.path.abspath(filename))
        for data, item in self.underlays:
            if item is not None:
                data.x        = item.scenePos().x()
                data.y        = item.scenePos().y()
                data.scale    = item.scale()
                data.rotation = item.rotation()
                data.opacity  = item.opacity()
            d = data.to_dict()
            d["path"] = Underlay.relativize_path(
                os.path.abspath(data.path), project_dir)
            underlays_data.append(d)
```

Also add `import os` and `from .underlay import Underlay` at the top of `scene_io.py` if not already present.

- [ ] **Step 6: Update `load_from_file` to resolve paths**

In `firepro3d/scene_io.py`, replace the underlay load block (lines 435-444):

```python
        # --- Underlays ---
        project_dir = os.path.dirname(os.path.abspath(filename))
        missing_underlays = []
        for entry in payload.get("underlays", []):
            udata = Underlay.from_dict(entry)
            resolved = Underlay.resolve_path(udata.path, project_dir)
            if resolved is None:
                missing_underlays.append(udata)
                continue
            udata.path = resolved
            if udata.type == "pdf":
                self.import_pdf(udata.path, dpi=udata.dpi, page=udata.page,
                                x=udata.x, y=udata.y, _record=udata)
            elif udata.type == "dxf":
                self.import_dxf(udata.path, color=QColor(udata.colour),
                                line_weight=udata.line_weight,
                                x=udata.x, y=udata.y, _record=udata)
```

Note: `missing_underlays` will be used by Task 7 (file-not-found). For now, just collect them — they'll be silently skipped until Task 7 adds placeholder creation. Also note the `filename` parameter is available in `load_from_file(self, filename)`.

- [ ] **Step 7: Commit**

```bash
git add firepro3d/underlay.py firepro3d/scene_io.py tests/test_underlay.py
git commit -m "feat(underlay): add path resolution with relative/absolute save/load"
```

---

### Task 5: Per-Level Visibility

**Depends on:** Task 1

**Files:**
- Modify: `firepro3d/level_manager.py:347-599` (`apply_to_scene`)
- Modify: `firepro3d/model_space.py` (set default level on import)

- [ ] **Step 1: Add underlay visibility block to `apply_to_scene`**

In `firepro3d/level_manager.py`, add after the Water supply block (after line 510, before the Z-ordering section at line 512) a new underlay block:

```python
        # ── Underlays ────────────────────────────────────────────────────
        for data, item in getattr(scene, "underlays", []):
            if item is None:
                continue
            try:
                item.isVisible()
            except RuntimeError:
                continue
            if not data.visible:
                item.setVisible(False)
                continue
            if data.level == "*":
                item.setVisible(True)
                continue
            lvl = lvl_map.get(data.level)
            if lvl is None:
                item.setVisible(False)
                continue
            if has_view_range:
                z = lvl.elevation
                item.setVisible(view_depth <= z <= view_height)
            else:
                item.setVisible(data.level == active)
```

- [ ] **Step 2: Set default level on import**

In `firepro3d/model_space.py`, in `_on_dxf_finished` (around line 2020 where the Underlay record is created), ensure the `level` field is set to the active level when creating a new record (not when `_record` is passed):

The existing code is:
```python
record = params["_record"] or Underlay(
    type="dxf", path=params["file_path"],
    ...
)
```

Add `level=self.active_level` to the `Underlay()` constructor call:

```python
record = params["_record"] or Underlay(
    type="dxf", path=params["file_path"],
    x=params["x"], y=params["y"],
    colour=color.name(),
    line_weight=params.get("line_weight", lw),
    user_layer=ul,
    level=self.active_level,
)
```

Do the same in `import_pdf` (around line 2208) where the PDF Underlay record is created:

```python
record = _record or Underlay(
    type="pdf", path=file_path,
    x=x, y=y, page=page, dpi=dpi,
    level=self.active_level,
)
```

- [ ] **Step 3: Commit**

```bash
git add firepro3d/level_manager.py firepro3d/model_space.py
git commit -m "feat(underlay): add per-level visibility via Z-range in LevelManager"
```

---

### Task 6: Per-Source-Layer Visibility + Duplicate Inheritance

**Depends on:** Task 1

**Files:**
- Modify: `firepro3d/model_space.py` (add `_apply_underlay_hidden_layers` helper, call in load/refresh)
- Modify: `firepro3d/underlay_context_menu.py` (duplicate inherits `hidden_layers` + new fields)

- [ ] **Step 1: Add hidden layers application helper to model_space.py**

Add a new method to `Model_Space` (near `_apply_underlay_display`, around line 2231):

```python
    def _apply_underlay_hidden_layers(self, item: QGraphicsItem,
                                       data: Underlay):
        """Hide child items whose source layer is in data.hidden_layers.

        Stale layer names (no longer in the file) are silently dropped.
        """
        if not data.hidden_layers or not hasattr(item, "childItems"):
            return
        # Collect actual layer names present in this group
        actual_layers = set()
        for child in item.childItems():
            layer_name = child.data(1)
            if layer_name is not None:
                actual_layers.add(layer_name)
        # Drop stale entries
        data.hidden_layers = [
            ln for ln in data.hidden_layers if ln in actual_layers
        ]
        # Apply visibility
        hidden_set = set(data.hidden_layers)
        for child in item.childItems():
            layer_name = child.data(1)
            if layer_name in hidden_set:
                child.setVisible(False)
```

- [ ] **Step 2: Call hidden layers helper after DXF import completes**

In `firepro3d/model_space.py`, in `_on_dxf_finished` — after the line `self._apply_underlay_display(group, record)` (around line 2029), add:

```python
        self._apply_underlay_hidden_layers(group, record)
```

- [ ] **Step 3: Call hidden layers helper in `refresh_underlay`**

In `firepro3d/model_space.py`, in `refresh_underlay` — the method currently re-imports via `import_dxf`/`import_pdf` which calls `_on_dxf_finished`/`import_pdf` completion. The `_apply_underlay_hidden_layers` call added in Step 2 will run automatically for DXF. Verify this by reading the refresh flow — no additional change needed if the `_on_dxf_finished` path is used.

- [ ] **Step 4: Update duplicate to inherit new fields**

In `firepro3d/underlay_context_menu.py`, in `_duplicate` (lines 206-229), add the new fields to the `Underlay()` constructor:

```python
    @staticmethod
    def _duplicate(scene, data: Underlay, item: QGraphicsItem):
        """Duplicate the underlay with a small position offset."""
        new_data = Underlay(
            type=data.type, path=data.path,
            x=data.x + 50, y=data.y + 50,
            scale=data.scale, rotation=data.rotation,
            opacity=data.opacity, locked=False,
            page=data.page, dpi=data.dpi,
            colour=data.colour, line_weight=data.line_weight,
            user_layer=data.user_layer,
            level=data.level, visible=data.visible,
            hidden_layers=list(data.hidden_layers),  # defensive copy
            import_mode=data.import_mode,
        )
        if data.type == "pdf":
            scene.import_pdf(
                data.path, dpi=data.dpi, page=data.page,
                x=new_data.x, y=new_data.y, _record=new_data,
            )
        elif data.type == "dxf":
            scene.import_dxf(
                data.path, color=QColor(data.colour),
                line_weight=data.line_weight,
                x=new_data.x, y=new_data.y,
                _record=new_data, user_layer=data.user_layer,
            )
        scene.push_undo_state()
```

- [ ] **Step 5: Commit**

```bash
git add firepro3d/model_space.py firepro3d/underlay_context_menu.py
git commit -m "feat(underlay): per-source-layer visibility + duplicate inherits hidden_layers"
```

---

### Task 7: File-Not-Found Handling

**Depends on:** Task 4

**Files:**
- Modify: `firepro3d/model_space.py` (add `_create_underlay_placeholder`)
- Modify: `firepro3d/scene_io.py` (create placeholders for missing files, aggregate warning)

- [ ] **Step 1: Add placeholder creation method to model_space.py**

Add to `Model_Space` class (near `_apply_underlay_display`):

```python
    def _create_underlay_placeholder(self, data: Underlay) -> QGraphicsItem:
        """Create a placeholder rect for a missing underlay file."""
        rect = QGraphicsRectItem(0, 0, 200, 150)
        pen = QPen(QColor("#ff0000"), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        rect.setPen(pen)
        rect.setBrush(QBrush(QColor(255, 0, 0, 30)))
        rect.setPos(data.x, data.y)
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        rect.setData(0, "missing_underlay")

        filename = os.path.basename(data.path)
        label = QGraphicsSimpleTextItem(
            f"{filename}\nMissing \u2014 right-click to relink", rect)
        font = QFont()
        font.setPointSize(8)
        label.setFont(font)
        label.setBrush(QBrush(QColor("#ff0000")))

        self.addItem(rect)
        self.underlays.append((data, rect))
        self.underlaysChanged.emit()
        return rect
```

Ensure these imports are at the top of `model_space.py` (most are already there):
- `QGraphicsRectItem`, `QGraphicsSimpleTextItem` from `PyQt6.QtWidgets`
- `QPen`, `QBrush`, `QColor`, `QFont` from `PyQt6.QtGui`

- [ ] **Step 2: Update load flow to create placeholders and show aggregate warning**

In `firepro3d/scene_io.py`, after the underlay load loop (from Task 4 Step 6), add placeholder creation and warning:

```python
        # --- Underlays (continued: handle missing files) ---
        for udata in missing_underlays:
            self._create_underlay_placeholder(udata)

        if missing_underlays:
            from PyQt6.QtWidgets import QMessageBox
            paths = "\n".join(f"  \u2022 {u.path}" for u in missing_underlays)
            QMessageBox.warning(
                None, "Missing Underlay Files",
                f"{len(missing_underlays)} underlay file(s) could not be found:\n\n"
                f"{paths}\n\n"
                "Use right-click \u2192 Relink in the browser tree to reconnect.",
            )
```

- [ ] **Step 3: Update `refresh_underlay` to handle missing files**

In `firepro3d/model_space.py`, in `refresh_underlay` — after syncing transform state and before re-import, add a file existence check:

```python
        # Check file exists before re-import
        if not os.path.exists(data.path):
            # Replace with placeholder
            if idx is not None:
                self.underlays.pop(idx)
            self._create_underlay_placeholder(data)
            self._show_status(f"Missing underlay: {data.path}")
            return
```

- [ ] **Step 4: Commit**

```bash
git add firepro3d/model_space.py firepro3d/scene_io.py
git commit -m "feat(underlay): file-not-found placeholder, aggregate warning, refresh handling"
```

---

### Task 8: Browser Tree Integration

**Depends on:** Tasks 1, 5, 6, 7

**Files:**
- Modify: `firepro3d/model_browser.py`
- Modify: `firepro3d/underlay.py` (add `get_properties` for property panel)

This is the largest task. It adds the Underlays category to the browser tree with full context menu support.

- [ ] **Step 1: Add imports to model_browser.py**

At the top of `firepro3d/model_browser.py`, add:

```python
import os
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QInputDialog
from PyQt6.QtGui import QIcon
from .underlay import Underlay
from .underlay_context_menu import UnderlayContextMenu
```

Add a new role constant after `_ROLE_ENTITY` (line 28):

```python
_ROLE_UNDERLAY = Qt.ItemDataRole.UserRole + 1  # stores index into scene.underlays
```

- [ ] **Step 2: Add Underlays category section to `refresh()`**

In `firepro3d/model_browser.py`, in the `refresh()` method, add after the last category section (Water Supply, around line 288) and before the closing of refresh:

```python
        # -- Underlays ─────────────────────────────────────────────────
        underlays = getattr(self._scene, "underlays", [])
        if underlays:
            ul_root = QTreeWidgetItem(
                self._tree, [f"Underlays ({len(underlays)})"])
            ul_root.setFont(0, f_bold)
            ul_root.setExpanded(True)

            for idx, (data, item) in enumerate(underlays):
                filename = os.path.basename(data.path)
                is_missing = (item is not None
                              and item.data(0) == "missing_underlay")
                level_label = ("All Levels" if data.level == "*"
                               else data.level)

                # File node
                label = f"{filename}    [{level_label}]"
                if is_missing:
                    label += "  (missing)"
                file_node = QTreeWidgetItem(ul_root, [label])
                file_node.setData(0, _ROLE_UNDERLAY, idx)
                if not data.visible:
                    file_node.setForeground(0, self._GREY)

                # Source-layer children (DXF only)
                if data.type == "dxf" and item is not None and not is_missing:
                    all_layers = item.data(2) or []
                    hidden_set = set(data.hidden_layers)
                    for layer_name in all_layers:
                        count = sum(
                            1 for c in item.childItems()
                            if c.data(1) == layer_name)
                        suffix = "  (hidden)" if layer_name in hidden_set else ""
                        layer_node = QTreeWidgetItem(
                            file_node,
                            [f"{layer_name}  ({count} items){suffix}"])
                        layer_node.setData(0, _ROLE_UNDERLAY, idx)
                        layer_node.setData(0, _ROLE_ENTITY, layer_name)
                        if layer_name in hidden_set:
                            layer_node.setForeground(0, self._GREY)

                # PDF page child
                elif data.type == "pdf" and not is_missing:
                    QTreeWidgetItem(file_node, [f"Page {data.page + 1}"])
```

- [ ] **Step 3: Update `_on_selection_changed` to handle underlay clicks**

In `firepro3d/model_browser.py`, modify `_on_selection_changed` (lines 342-368). Add underlay handling before the `if not entities: return` guard:

```python
    def _on_selection_changed(self):
        """Handle tree selection changes."""
        if self._syncing:
            return
        selected_items = self._tree.selectedItems()

        # Check for underlay selection first
        for tree_item in selected_items:
            ul_idx = tree_item.data(0, _ROLE_UNDERLAY)
            if ul_idx is not None:
                self._on_underlay_selected(ul_idx)
                return

        # Existing entity selection logic (unchanged)
        entities = []
        for tree_item in selected_items:
            entity_id = tree_item.data(0, _ROLE_ENTITY)
            if entity_id is not None:
                entity = self._find_entity_by_id(entity_id)
                if entity is not None:
                    entities.append(entity)
        if not entities:
            return
        self._syncing = True
        try:
            self._scene.clearSelection()
            for entity in entities:
                entity.setSelected(True)
        finally:
            self._syncing = False
        if len(entities) == 1:
            self.entitySelected.emit(entities[0])
        else:
            self.entitySelected.emit(entities)
```

- [ ] **Step 4: Add underlay selection handler**

Add a new method to `ModelBrowser`:

```python
    def _on_underlay_selected(self, idx: int):
        """Handle click on an underlay file node — pan to it and populate
        property panel (even for locked underlays)."""
        underlays = getattr(self._scene, "underlays", [])
        if idx < 0 or idx >= len(underlays):
            return
        data, item = underlays[idx]
        if item is None:
            return

        # Pan view to the underlay
        views = self._scene.views()
        if views:
            br = item.boundingRect()
            scene_rect = item.mapToScene(br).boundingRect()
            views[0].centerOn(scene_rect.center())

        # Select in scene if not locked
        self._syncing = True
        try:
            self._scene.clearSelection()
            if not data.locked:
                item.setSelected(True)
        finally:
            self._syncing = False

        # Populate property panel
        self.entitySelected.emit(data)
```

- [ ] **Step 5: Update `_on_context_menu` to handle underlay right-click**

In `firepro3d/model_browser.py`, modify `_on_context_menu` (lines 388-430). Add an underlay check at the beginning, before the entity lookup:

```python
    def _on_context_menu(self, pos):
        """Right-click context menu on tree items."""
        if self._scene is None:
            return
        tree_item = self._tree.itemAt(pos)
        if tree_item is None:
            return

        # Check if this is an underlay node
        ul_idx = tree_item.data(0, _ROLE_UNDERLAY)
        if ul_idx is not None:
            self._underlay_context_menu(tree_item, ul_idx, pos)
            return

        # Existing entity context menu logic (unchanged from here)
        entities = []
        for ti in self._tree.selectedItems():
            eid = ti.data(0, _ROLE_ENTITY)
            if eid is not None:
                entity = self._find_entity_by_id(eid)
                if entity is not None:
                    entities.append(entity)
        if not entities:
            return

        menu = QMenu(self)
        any_hidden = any(
            getattr(e, "_display_overrides", {}).get("visible") is False
            for e in entities)
        any_visible = any(
            getattr(e, "_display_overrides", {}).get("visible") is not False
            for e in entities)
        if any_visible:
            act_hide = menu.addAction("Hide")
            act_hide.triggered.connect(
                lambda: (self._scene._hide_items(entities), self.refresh()))
        if any_hidden:
            act_show = menu.addAction("Show")
            act_show.triggered.connect(
                lambda: (self._scene._show_items(entities), self.refresh()))
        menu.addSeparator()
        act_show_all = menu.addAction("Show All Hidden")
        act_show_all.triggered.connect(
            lambda: (self._scene._show_all_hidden(), self.refresh()))
        menu.exec(self._tree.viewport().mapToGlobal(pos))
```

- [ ] **Step 6: Implement `_underlay_context_menu`**

Add a new method to `ModelBrowser`:

```python
    def _underlay_context_menu(self, tree_item, ul_idx: int, pos):
        """Build and show context menu for an underlay tree node."""
        underlays = getattr(self._scene, "underlays", [])
        if ul_idx < 0 or ul_idx >= len(underlays):
            return
        data, item = underlays[ul_idx]
        is_missing = (item is not None
                      and getattr(item, "data", lambda k: None)(0)
                      == "missing_underlay")

        # Check if this is a source-layer node (has layer name in ROLE_ENTITY)
        layer_name = tree_item.data(0, _ROLE_ENTITY)
        if isinstance(layer_name, str):
            self._underlay_layer_context_menu(data, item, layer_name, pos)
            return

        menu = QMenu(self)
        scene = self._scene

        if is_missing:
            # Missing underlays: only Relink and Remove
            act_relink = menu.addAction("Relink\u2026")
            act_relink.triggered.connect(
                lambda: self._relink_underlay(data, item))
            menu.addSeparator()
            act_remove = menu.addAction("Remove")
            act_remove.triggered.connect(
                lambda: self._remove_underlay(data, item))
        else:
            # Lock / Unlock
            lock_label = "Unlock" if data.locked else "Lock"
            act_lock = menu.addAction(lock_label)
            act_lock.triggered.connect(
                lambda: self._toggle_underlay_lock(data, item))

            # Hide / Show
            vis_label = "Show" if not data.visible else "Hide"
            act_vis = menu.addAction(vis_label)
            act_vis.triggered.connect(
                lambda: self._toggle_underlay_visible(data, item))

            # Change Level submenu
            level_menu = menu.addMenu("Change Level")
            lm = getattr(scene, "_level_manager", None)
            levels = lm.levels if lm else []
            for lvl in levels:
                act = level_menu.addAction(lvl.name)
                act.triggered.connect(
                    lambda checked=False, ln=lvl.name:
                        self._set_underlay_level(data, ln))
            level_menu.addSeparator()
            act_all = level_menu.addAction("All Levels")
            act_all.triggered.connect(
                lambda: self._set_underlay_level(data, "*"))

            menu.addSeparator()
            act_relink = menu.addAction("Relink\u2026")
            act_relink.triggered.connect(
                lambda: self._relink_underlay(data, item))

            act_refresh = menu.addAction("Refresh from Disk")
            act_refresh.triggered.connect(
                lambda: (scene.refresh_underlay(data, item),
                         self.refresh()))

            act_dup = menu.addAction("Duplicate")
            act_dup.triggered.connect(
                lambda: (UnderlayContextMenu._duplicate(scene, data, item),
                         self.refresh()))

            menu.addSeparator()
            act_remove = menu.addAction("Remove")
            act_remove.triggered.connect(
                lambda: self._remove_underlay(data, item))

        menu.exec(self._tree.viewport().mapToGlobal(pos))
```

- [ ] **Step 7: Implement source-layer context menu**

```python
    def _underlay_layer_context_menu(self, data, item, layer_name, pos):
        """Context menu for a DXF source-layer node."""
        menu = QMenu(self)
        is_hidden = layer_name in data.hidden_layers
        label = "Show Layer" if is_hidden else "Hide Layer"
        act = menu.addAction(label)
        act.triggered.connect(
            lambda: self._toggle_underlay_layer(data, item, layer_name))
        menu.exec(self._tree.viewport().mapToGlobal(pos))
```

- [ ] **Step 8: Implement underlay action helpers**

Add these methods to `ModelBrowser`:

```python
    def _toggle_underlay_lock(self, data: Underlay, item):
        data.locked = not data.locked
        if data.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        else:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._scene.push_undo_state()
        self.refresh()

    def _toggle_underlay_visible(self, data: Underlay, item):
        data.visible = not data.visible
        # Visibility is resolved by LevelManager, trigger re-apply
        lm = getattr(self._scene, "_level_manager", None)
        if lm:
            lm.apply_to_scene(self._scene)
        self._scene.push_undo_state()
        self.refresh()

    def _set_underlay_level(self, data: Underlay, level_name: str):
        data.level = level_name
        lm = getattr(self._scene, "_level_manager", None)
        if lm:
            lm.apply_to_scene(self._scene)
        self._scene.push_undo_state()
        self.refresh()

    def _toggle_underlay_layer(self, data, item, layer_name):
        """Toggle a DXF source layer on/off."""
        if layer_name in data.hidden_layers:
            data.hidden_layers.remove(layer_name)
            show = True
        else:
            data.hidden_layers.append(layer_name)
            show = False
        for child in item.childItems():
            if child.data(1) == layer_name:
                child.setVisible(show)
        self._scene.underlaysChanged.emit()
        self._scene.push_undo_state()
        self.refresh()

    def _relink_underlay(self, data: Underlay, item):
        """File dialog to relink a missing or changed underlay."""
        if data.type == "dxf":
            filter_str = "DXF Files (*.dxf)"
        else:
            filter_str = "PDF Files (*.pdf)"
        path, _ = QFileDialog.getOpenFileName(
            self, "Relink Underlay", "", filter_str)
        if not path:
            return
        data.path = path
        self._scene.refresh_underlay(data, item)
        self._scene.push_undo_state()
        self.refresh()

    def _remove_underlay(self, data: Underlay, item):
        """Remove with confirmation dialog."""
        filename = os.path.basename(data.path)
        reply = QMessageBox.question(
            self, "Remove Underlay",
            f"Remove underlay '{filename}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._scene.remove_underlay(data, item)
            self.refresh()
```

- [ ] **Step 9: Add `get_properties()` to Underlay for property panel**

In `firepro3d/underlay.py`, add a method to the `Underlay` class:

```python
    def get_properties(self) -> dict:
        """Return property template for the property manager panel.

        All fields are read-only labels for MVP. Edits are done via
        the browser tree context menu actions.
        """
        props = {
            "File": {"type": "label", "value": os.path.basename(self.path)},
            "Path": {"type": "label", "value": self.path},
            "Type": {"type": "label", "value": self.type.upper()},
            "Level": {"type": "label",
                       "value": "All Levels" if self.level == "*"
                       else self.level},
            "X": {"type": "label", "value": f"{self.x:.1f}"},
            "Y": {"type": "label", "value": f"{self.y:.1f}"},
            "Scale": {"type": "label", "value": str(self.scale)},
            "Rotation": {"type": "label", "value": f"{self.rotation:.1f}\u00b0"},
            "Opacity": {"type": "label", "value": f"{self.opacity:.0%}"},
            "Locked": {"type": "label",
                        "value": "Yes" if self.locked else "No"},
            "Visible": {"type": "label",
                         "value": "Yes" if self.visible else "No"},
        }
        if self.type == "pdf":
            props["DPI"] = {"type": "label", "value": str(self.dpi)}
            props["Page"] = {"type": "label", "value": str(self.page + 1)}
            props["Import Mode"] = {"type": "label", "value": self.import_mode}
        if self.hidden_layers:
            props["Hidden Layers"] = {
                "type": "label",
                "value": ", ".join(self.hidden_layers)}
        return props
```

- [ ] **Step 10: Add QGraphicsItem import to model_browser.py**

Ensure `QGraphicsItem` is imported at the top:

```python
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel, QSizePolicy,
    QAbstractItemView, QMenu, QMessageBox, QFileDialog,
)
from PyQt6.QtGui import QFont, QColor, QBrush
```

- [ ] **Step 11: Commit**

```bash
git add firepro3d/model_browser.py firepro3d/underlay.py
git commit -m "feat(underlay): browser tree integration with context menus and property panel"
```

---

### Task 9: Integration Verification

**Depends on:** All previous tasks

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

Run: `cd D:\Custom Code\FirePro3D && python -m pytest tests/ -v`
Expected: All PASS (existing tests + new underlay tests)

- [ ] **Step 2: Import check**

Run: `cd D:\Custom Code\FirePro3D && python -c "from firepro3d.underlay import Underlay; from firepro3d.model_browser import ModelBrowser; from firepro3d.dxf_import_worker import DxfImportWorker; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Verify backward compat with old project files**

Run: `cd D:\Custom Code\FirePro3D && python -c "
from firepro3d.underlay import Underlay
old = {'type': 'dxf', 'path': 'test.dxf', 'x': 0, 'y': 0, 'scale': 1.0, 'rotation': 0, 'opacity': 1.0, 'locked': False, 'colour': '#ffffff', 'line_weight': 0.0, 'user_layer': 'Default'}
u = Underlay.from_dict(old)
assert u.level == 'Level 1'
assert u.visible is True
assert u.hidden_layers == []
assert u.import_mode == 'auto'
d = u.to_dict()
assert 'level' in d
assert 'visible' in d
assert 'hidden_layers' in d
print('Backward compat OK')
"`
Expected: `Backward compat OK`

- [ ] **Step 4: Smoke test the application**

Run: `cd D:\Custom Code\FirePro3D && python main.py`

Manual checks:
1. Import a DXF file — verify INSERT entities (blocks) now appear
2. Check browser tree shows "Underlays" category with file node and source layers
3. Right-click underlay in browser tree — verify Lock/Unlock, Hide/Show, Change Level, Refresh, Duplicate, Remove actions
4. Lock an underlay — click its tree node — verify property panel populates
5. Hide a source layer via tree right-click — verify it disappears in the scene
6. Switch levels — verify underlay hides/shows based on level assignment
7. Save, close, reopen — verify underlay reloads with correct position, scale, hidden layers

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(underlay): complete P1 underlay workflow cluster implementation"
```
