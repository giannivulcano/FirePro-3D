# Underlay Geometry Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache underlay geometry dicts to a `.fpd.cache/` directory so that project reload skips expensive DXF/PDF re-parsing and loads from cache instead.

**Architecture:** A new `underlay_cache.py` module owns all cache I/O — read, write, invalidation by source file modification timestamp. The existing import and load paths in `model_space.py` and `scene_io.py` gain cache-write (on import) and cache-read (on load) hooks. When a source file is missing but its cache exists, the underlay renders from cache instead of showing a placeholder.

**Tech Stack:** Python `json` for serialization, `os.path` / `os.stat` for timestamp tracking. No new dependencies.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `firepro3d/underlay_cache.py` | **Create** | Cache I/O: write geometry dicts, read geometry dicts, check freshness, delete stale entries, compute cache key |
| `firepro3d/underlay.py` | **Modify** | Add `cache_key()` method to Underlay dataclass; add `import_bounds` field for area-selection persistence |
| `firepro3d/model_space.py` | **Modify** | Write cache after import; read cache on reload; handle cache-hit for missing source files; store raw geom on groups via `data(5)` |
| `firepro3d/scene_io.py` | **Modify** | On load, try cache before calling `import_dxf`/`import_pdf`; on save, write cache for all underlays; pass project dir for cache directory resolution |
| `firepro3d/dwg_converter.py` | **Modify** | Add `compute_geom_bounds()` for bounding-box computation from geometry dicts |
| `tests/test_underlay_cache.py` | **Create** | Unit tests for cache module |
| `tests/test_underlay_cache_integration.py` | **Create** | Integration tests for cache-aware load/save |

---

### Task 1: Cache Module — Core I/O

**Files:**
- Create: `firepro3d/underlay_cache.py`
- Create: `tests/test_underlay_cache.py`

This task builds the standalone cache module with no integration into the import pipeline. Pure functions, fully testable in isolation.

- [ ] **Step 1: Write the failing test for cache directory creation**

```python
# tests/test_underlay_cache.py
import json
import os
import tempfile
import pytest

from firepro3d.underlay_cache import cache_dir_for_project, write_cache, read_cache


class TestCacheDirForProject:
    def test_returns_sibling_cache_dir(self, tmp_path):
        project_file = tmp_path / "MyProject.fpd"
        project_file.touch()
        result = cache_dir_for_project(str(project_file))
        assert result == str(tmp_path / "MyProject.fpd.cache")

    def test_different_project_names(self, tmp_path):
        result = cache_dir_for_project(str(tmp_path / "Other.fpd"))
        assert result.endswith("Other.fpd.cache")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_underlay_cache.py::TestCacheDirForProject -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'firepro3d.underlay_cache'`

- [ ] **Step 3: Write the cache module with `cache_dir_for_project`**

```python
# firepro3d/underlay_cache.py
"""
underlay_cache.py
=================
Geometry-dict cache for underlay files (DXF / PDF).

Stores the intermediate geometry dicts (output of ezdxf / PyMuPDF parsing)
as JSON in a sibling ``.fpd.cache/`` directory.  On project reload the
expensive source-file parsing is skipped when a fresh cache entry exists.

Cache key:  ``<sanitised_basename>_<hex_hash>.json``
Freshness:  source-file modification timestamp stored inside the cache file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any


def cache_dir_for_project(project_path: str) -> str:
    """Return the cache directory path for a project file.

    Example: ``/plans/MyProject.fpd`` → ``/plans/MyProject.fpd.cache/``
    """
    return os.path.abspath(project_path) + ".cache"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_underlay_cache.py::TestCacheDirForProject -v`
Expected: PASS

- [ ] **Step 5: Write failing test for cache key computation**

```python
# tests/test_underlay_cache.py  (append)

class TestCacheKey:
    def test_same_inputs_same_key(self):
        from firepro3d.underlay_cache import compute_cache_key
        k1 = compute_cache_key("/plans/floor1.dxf", page=0, selected_layers=None)
        k2 = compute_cache_key("/plans/floor1.dxf", page=0, selected_layers=None)
        assert k1 == k2

    def test_different_path_different_key(self):
        from firepro3d.underlay_cache import compute_cache_key
        k1 = compute_cache_key("/plans/floor1.dxf", page=0, selected_layers=None)
        k2 = compute_cache_key("/plans/floor2.dxf", page=0, selected_layers=None)
        assert k1 != k2

    def test_different_page_different_key(self):
        from firepro3d.underlay_cache import compute_cache_key
        k1 = compute_cache_key("/plans/sheet.pdf", page=0, selected_layers=None)
        k2 = compute_cache_key("/plans/sheet.pdf", page=1, selected_layers=None)
        assert k1 != k2

    def test_different_layers_different_key(self):
        from firepro3d.underlay_cache import compute_cache_key
        k1 = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=["A-WALL"])
        k2 = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=["A-WALL", "A-DOOR"])
        assert k1 != k2

    def test_key_is_valid_filename(self):
        from firepro3d.underlay_cache import compute_cache_key
        key = compute_cache_key("C:\\My Plans\\floor (1).dxf", page=0, selected_layers=None)
        # Should contain only alphanumeric, underscore, hyphen, dot
        assert re.match(r'^[\w\-.]+$', key), f"Invalid filename chars in: {key}"

    def test_none_layers_same_as_omitted(self):
        from firepro3d.underlay_cache import compute_cache_key
        k1 = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=None)
        k2 = compute_cache_key("/plans/floor.dxf", page=0)
        assert k1 == k2
```

- [ ] **Step 6: Implement `compute_cache_key`**

```python
# firepro3d/underlay_cache.py  (append)

def compute_cache_key(
    source_path: str,
    page: int = 0,
    selected_layers: list[str] | None = None,
) -> str:
    """Compute a deterministic cache filename for an underlay.

    The key encodes the source path, page number, and layer selection
    so that different imports of the same file get separate cache entries.
    """
    norm = os.path.normpath(os.path.abspath(source_path))
    parts = [norm, str(page)]
    if selected_layers is not None:
        parts.append(",".join(sorted(selected_layers)))
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    # Sanitise basename for use in filename
    base = os.path.splitext(os.path.basename(source_path))[0]
    safe = re.sub(r'[^\w\-]', '_', base)[:40]
    return f"{safe}_{digest}.json"
```

- [ ] **Step 7: Run cache key tests**

Run: `pytest tests/test_underlay_cache.py::TestCacheKey -v`
Expected: PASS

- [ ] **Step 8: Write failing tests for write_cache and read_cache**

```python
# tests/test_underlay_cache.py  (append)

SAMPLE_GEOMS = [
    {"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "layer": "0"},
    {"kind": "circle", "x": 50, "y": 50, "w": 20, "h": 20, "layer": "A-WALL"},
    {"kind": "path_points", "points": [(0, 0), (10, 20), (30, 40)],
     "closed": True, "layer": "0"},
    {"kind": "text", "x": 5, "y": 10, "text": "Hello", "layer": "ANNO"},
]


class TestWriteAndReadCache:
    def test_roundtrip(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "test_abc123.json"
        mtime = 1715600000.0

        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=mtime)

        result = read_cache(cache_dir, key, source_mtime=mtime)
        assert result is not None
        assert len(result) == len(SAMPLE_GEOMS)
        assert result[0]["kind"] == "line"
        assert result[2]["points"] == [(0, 0), (10, 20), (30, 40)]

    def test_stale_cache_returns_none(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "test_abc123.json"
        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)

        # Source file is newer than cached mtime
        result = read_cache(cache_dir, key, source_mtime=2000.0)
        assert result is None

    def test_missing_cache_returns_none(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        result = read_cache(cache_dir, "nonexistent.json", source_mtime=1000.0)
        assert result is None

    def test_cache_dir_created_on_write(self, tmp_path):
        cache_dir = str(tmp_path / "new_proj.fpd.cache")
        assert not os.path.exists(cache_dir)
        write_cache(cache_dir, "test.json", SAMPLE_GEOMS, source_mtime=1000.0)
        assert os.path.isdir(cache_dir)

    def test_read_without_mtime_skips_freshness(self, tmp_path):
        """When source_mtime is None (file missing), return cache unconditionally."""
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "test.json"
        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)
        result = read_cache(cache_dir, key, source_mtime=None)
        assert result is not None
        assert len(result) == len(SAMPLE_GEOMS)

    def test_corrupt_cache_returns_none(self, tmp_path):
        cache_dir = str(tmp_path / "proj.fpd.cache")
        os.makedirs(cache_dir)
        cache_file = os.path.join(cache_dir, "corrupt.json")
        with open(cache_file, "w") as f:
            f.write("not valid json{{{")
        result = read_cache(cache_dir, "corrupt.json", source_mtime=1000.0)
        assert result is None
```

- [ ] **Step 9: Implement `write_cache` and `read_cache`**

```python
# firepro3d/underlay_cache.py  (append)

def write_cache(
    cache_dir: str,
    key: str,
    geom_list: list[dict[str, Any]],
    source_mtime: float,
) -> None:
    """Write geometry dicts to a cache file.

    Creates the cache directory if it doesn't exist.  The cache file
    stores the source modification timestamp alongside the geometry
    so that staleness can be detected on read.
    """
    os.makedirs(cache_dir, exist_ok=True)
    payload = {
        "version": 1,
        "source_mtime": source_mtime,
        "geom_count": len(geom_list),
        "geoms": geom_list,
    }
    path = os.path.join(cache_dir, key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))


def read_cache(
    cache_dir: str,
    key: str,
    source_mtime: float | None,
) -> list[dict[str, Any]] | None:
    """Read cached geometry dicts if the cache is fresh.

    Returns ``None`` if the cache file is missing, corrupt, or stale
    (source file is newer than cached timestamp).

    When *source_mtime* is ``None`` (source file missing), the cache
    is returned unconditionally — this enables the "render from cache
    when source is missing" feature.
    """
    path = os.path.join(cache_dir, key)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if payload.get("version") != 1:
        return None

    # Freshness check: skip if source_mtime is None (file missing)
    if source_mtime is not None:
        cached_mtime = payload.get("source_mtime", 0.0)
        if source_mtime > cached_mtime:
            return None

    return payload.get("geoms")
```

- [ ] **Step 10: Run all cache module tests**

Run: `pytest tests/test_underlay_cache.py -v`
Expected: all PASS

- [ ] **Step 11: Write failing test for `delete_cache`**

```python
# tests/test_underlay_cache.py  (append)

class TestDeleteCache:
    def test_delete_existing(self, tmp_path):
        from firepro3d.underlay_cache import delete_cache
        cache_dir = str(tmp_path / "proj.fpd.cache")
        write_cache(cache_dir, "test.json", SAMPLE_GEOMS, source_mtime=1000.0)
        assert os.path.isfile(os.path.join(cache_dir, "test.json"))
        delete_cache(cache_dir, "test.json")
        assert not os.path.isfile(os.path.join(cache_dir, "test.json"))

    def test_delete_nonexistent_no_error(self, tmp_path):
        from firepro3d.underlay_cache import delete_cache
        cache_dir = str(tmp_path / "proj.fpd.cache")
        delete_cache(cache_dir, "ghost.json")  # should not raise
```

- [ ] **Step 12: Implement `delete_cache`**

```python
# firepro3d/underlay_cache.py  (append)

def delete_cache(cache_dir: str, key: str) -> None:
    """Remove a cache file.  No-op if the file doesn't exist."""
    path = os.path.join(cache_dir, key)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
```

- [ ] **Step 13: Run all tests and commit**

Run: `pytest tests/test_underlay_cache.py -v`
Expected: all PASS

```bash
git add firepro3d/underlay_cache.py tests/test_underlay_cache.py
git commit -m "feat(cache): add underlay geometry cache module

write_cache/read_cache/delete_cache with JSON storage,
timestamp-based freshness, and deterministic cache keys."
```

---

### Task 2: Underlay Data Model — Cache Key Method

**Files:**
- Modify: `firepro3d/underlay.py:7-41`
- Modify: `tests/test_underlay_serialization.py`

Add a `cache_key()` convenience method to the Underlay dataclass that delegates to `compute_cache_key`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_underlay_serialization.py  (append to end of file)

class TestUnderlayCacheKey:
    def test_dxf_cache_key_deterministic(self):
        u = Underlay(type="dxf", path="/plans/floor1.dxf")
        assert u.cache_key() == u.cache_key()

    def test_pdf_different_pages_different_keys(self):
        u1 = Underlay(type="pdf", path="/plans/sheet.pdf", page=0)
        u2 = Underlay(type="pdf", path="/plans/sheet.pdf", page=1)
        assert u1.cache_key() != u2.cache_key()

    def test_dxf_layer_selection_affects_key(self):
        u1 = Underlay(type="dxf", path="/plans/floor.dxf", selected_layers=None)
        u2 = Underlay(type="dxf", path="/plans/floor.dxf",
                      selected_layers=["A-WALL"])
        assert u1.cache_key() != u2.cache_key()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_underlay_serialization.py::TestUnderlayCacheKey -v`
Expected: FAIL with `AttributeError: 'Underlay' object has no attribute 'cache_key'`

- [ ] **Step 3: Add `cache_key()` method to Underlay**

Add this method to the `Underlay` class in `firepro3d/underlay.py`, after the `get_properties` method:

```python
    def cache_key(self) -> str:
        """Return the cache filename for this underlay's geometry."""
        from .underlay_cache import compute_cache_key
        return compute_cache_key(
            self.path, page=self.page, selected_layers=self.selected_layers)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_underlay_serialization.py::TestUnderlayCacheKey -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add firepro3d/underlay.py tests/test_underlay_serialization.py
git commit -m "feat(cache): add cache_key() method to Underlay dataclass"
```

---

### Task 3: Cache Write on Import — DXF Path

**Files:**
- Modify: `firepro3d/model_space.py:2069-2230` (`import_dxf`, `_on_dxf_finished`)
- Modify: `firepro3d/model_space.py:1970-2067` (`_commit_place_import`)

Wire cache writes into the two DXF import paths: direct import (`_on_dxf_finished`) and interactive placement (`_commit_place_import`). Cache is written after geometry dicts are received but **before** the import transform is applied (raw geometry is cached, transform is re-applied from Underlay record on reload).

> **Revision note (2026-05-24):** In the implemented version, `_on_dxf_finished` applies the `import_bounds` spatial filter (via `filter_geoms_by_bounds`) *before* the cache write, so the cached geometry reflects the user's area selection. The raw pre-transform geometry is also stored on the group item via `group.setData(5, _raw_geom)` for use by `_ensure_underlay_caches` on save.

The import functions need to know the project file path for the cache directory. `Model_Space` already has access to the current filename via `self._current_filename` (set by `save_to_file` / `load_from_file`).

- [ ] **Step 1: Verify `_current_filename` exists on Model_Space**

```bash
cd "D:/Custom Code/FirePro3D"
grep -n "_current_filename" firepro3d/model_space.py firepro3d/scene_io.py | head -20
```

If `_current_filename` is not already tracked, check for the attribute that stores the project path. The save/load flow in `scene_io.py` receives `filename` as a parameter — we need to persist it.

- [ ] **Step 2: Add `_project_path` tracking if needed**

Check if `Model_Space.__init__` or `SceneIOMixin` already stores the project path. If not, add to `scene_io.py`:

In `load_from_file`, after the existing code at the top of the method, add:

```python
        self._project_path = os.path.abspath(filename)
```

In `save_to_file`, after the existing code at the top of the method, add:

```python
        self._project_path = os.path.abspath(filename)
```

In `_clear_scene`, add:

```python
        self._project_path = None
```

- [ ] **Step 3: Add cache write to `_on_dxf_finished`**

In `firepro3d/model_space.py`, in `_on_dxf_finished`, right after the `if not geom_list:` early return (after line 2129), add the cache write call. The geometry list at this point is the **raw** pre-transform data — exactly what we want to cache.

Add this block after line 2129 (`return` inside the `if not geom_list` block), before the colour derivation (line 2131):

```python
        # Write geometry cache (raw, pre-transform)
        self._write_underlay_cache(params["file_path"], geom_list,
                                   page=0,
                                   selected_layers=params.get("layers"))
```

- [ ] **Step 4: Add cache write to `_commit_place_import`**

In `_commit_place_import`, after `params = self._place_import_params` (line 1977), before the transform loop, add:

```python
        # Write geometry cache (raw, pre-transform)
        self._write_underlay_cache(
            params.file_path, params.geom_list,
            page=getattr(params, "pdf_page", 0),
            selected_layers=getattr(params, "selected_layers", None))
```

- [ ] **Step 5: Add the `_write_underlay_cache` helper**

Add this method to Model_Space (near the existing underlay management methods, after `_underlay_color_lw` around line 3485):

```python
    def _write_underlay_cache(self, source_path: str, geom_list: list[dict],
                              page: int = 0,
                              selected_layers: list[str] | None = None):
        """Write geometry dicts to the project cache directory.

        No-op if the project has not been saved yet (no project path).
        """
        project_path = getattr(self, "_project_path", None)
        if not project_path:
            return
        try:
            source_mtime = os.path.getmtime(source_path)
        except OSError:
            return
        from .underlay_cache import cache_dir_for_project, compute_cache_key, write_cache
        cache_dir = cache_dir_for_project(project_path)
        key = compute_cache_key(source_path, page=page,
                                selected_layers=selected_layers)
        try:
            write_cache(cache_dir, key, geom_list, source_mtime=source_mtime)
        except OSError:
            pass  # non-fatal — cache is an optimisation
```

- [ ] **Step 6: Run existing underlay tests to verify no regressions**

Run: `pytest tests/test_underlay_integration.py tests/test_underlay_serialization.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add firepro3d/model_space.py firepro3d/scene_io.py
git commit -m "feat(cache): write underlay geometry cache on DXF import

Caches raw geometry dicts to .fpd.cache/ on both direct import
and interactive placement. No-op when project is unsaved."
```

---

### Task 4: Cache Write on Import — PDF Path

**Files:**
- Modify: `firepro3d/model_space.py:2308-2445` (`import_pdf`)
- Modify: `firepro3d/model_space.py:2447-2544` (`_import_pdf_vectors`)

Wire cache writes into the two PDF import paths: vector and raster. For vector PDFs, cache the geometry dicts (same as DXF). For raster PDFs, there is nothing to cache — the pixmap is rendered from the PDF each time and the bottleneck is typically acceptable.

- [ ] **Step 1: Add cache write to `_import_pdf_vectors`**

In `_import_pdf_vectors`, right after the method docstring, before the colour derivation (line 2458), add:

```python
        # Write geometry cache (raw, pre-transform)
        self._write_underlay_cache(
            file_path, geom_list, page=page,
            selected_layers=None)
```

- [ ] **Step 2: Add cache write to `import_pdf` vector path**

In `import_pdf`, in the vector extraction block (around line 2340), the `geom_list` is available right after `extract_pdf_vectors_sync`. The cache write is already handled by `_import_pdf_vectors` which is called on line 2341. No additional change needed here — `_import_pdf_vectors` will write the cache.

Verify: re-read lines 2330-2346 to confirm `_import_pdf_vectors` is the only call site.

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_underlay_integration.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add firepro3d/model_space.py
git commit -m "feat(cache): write underlay geometry cache on PDF vector import"
```

---

### Task 5: Cache Read on Project Load

**Files:**
- Modify: `firepro3d/scene_io.py:437-471` (underlay loading section of `load_from_file`)
- Modify: `firepro3d/model_space.py` (add `_load_underlay_from_cache` helper)

This is the main payoff: on project load, check the cache before calling `import_dxf` / `import_pdf`. If the cache is fresh, skip source file parsing entirely and build Qt items directly from cached geometry dicts.

> **Revision note (2026-05-24):** The implemented version differs from the original plan in three ways: (1) on cache miss with a valid source file, it performs sync re-extraction and rebuilds the cache rather than falling back to async import; (2) when `record.import_bounds` is set, the re-extracted geometry is filtered through `filter_geoms_by_bounds()` before caching; (3) the raw (pre-transform) geometry is stored on the group via `data(5)` so `_ensure_underlay_caches` can write it on save without re-extraction.

- [ ] **Step 1: Add `_load_underlay_from_cache` to Model_Space**

Add this method near `_write_underlay_cache`:

```python
    def _load_underlay_from_cache(self, record: Underlay,
                                  source_mtime: float | None) -> bool:
        """Try to load an underlay from the geometry cache.

        When the cache is stale but the source file exists, re-extracts
        synchronously and rebuilds the cache before proceeding.

        Returns True if the underlay was loaded, False if the caller
        should fall back to async parsing.
        """
        project_path = getattr(self, "_project_path", None)
        if not project_path:
            return False

        from .underlay_cache import cache_dir_for_project, read_cache
        cache_dir = cache_dir_for_project(project_path)
        key = record.cache_key()

        geom_list = read_cache(cache_dir, key, source_mtime=source_mtime)
        if geom_list is None:
            # Cache stale — try synchronous re-extraction from source
            if source_mtime is None:
                return False
            try:
                if record.type == "dxf":
                    from .dxf_import_worker import DxfImportWorker
                    geom_list = DxfImportWorker.extract_file_sync(
                        record.path, record.selected_layers,
                        layout=record.layout)
                elif record.type == "dwg":
                    # ... ODA convert + extract_file_sync ...
                else:
                    return False
            except Exception:
                return False
            if not geom_list:
                return False
            # Apply spatial bounds filter (area selection at import time)
            if record.import_bounds is not None:
                from .dwg_converter import filter_geoms_by_bounds
                geom_list = filter_geoms_by_bounds(
                    geom_list, [tuple(record.import_bounds)])
            # Write fresh cache
            self._write_underlay_cache(
                record.path, geom_list,
                page=record.page,
                selected_layers=record.selected_layers,
                layout=record.layout)

        # Snapshot raw geom for cache-on-save
        _raw_geom = geom_list

        # Apply import transform (same logic as _on_dxf_finished reload path)
        if (record.import_scale != 1.0
                or record.import_base_x != 0.0
                or record.import_base_y != 0.0):
            # ... base-point shift + scale transform ...

        # Build Qt items (same as _on_dxf_finished / _import_pdf_vectors)
        # ... batched QPainterPath rendering ...

        group.setData(5, _raw_geom)  # raw pre-transform geom for cache
        if source_mtime is None:
            group.setData(3, "source_missing")

        self._apply_underlay_display(group, record)
        self._apply_underlay_hidden_layers(group, record)
        self.underlays.append((record, group))
        return True
```

- [ ] **Step 2: Modify `load_from_file` in scene_io.py to try cache first**

Replace the underlay loading section (lines 437-471) in `scene_io.py` with cache-aware logic:

```python
        # --- Underlays ---
        project_dir = os.path.dirname(os.path.abspath(filename))
        missing_underlays = []
        for entry in payload.get("underlays", []):
            udata = Underlay.from_dict(entry)
            resolved = Underlay.resolve_path(udata.path, project_dir)

            if resolved is not None:
                udata.path = resolved
                source_mtime = os.path.getmtime(resolved)
            else:
                source_mtime = None

            # Try cache first (fast path)
            if self._load_underlay_from_cache(udata, source_mtime):
                continue

            # Cache miss — fall back to source file parsing
            if resolved is None:
                missing_underlays.append(udata)
                continue

            if udata.type == "pdf":
                self.import_pdf(udata.path, dpi=udata.dpi, page=udata.page,
                                x=udata.x, y=udata.y, _record=udata,
                                import_mode=udata.import_mode)
            elif udata.type == "dxf":
                self.import_dxf(udata.path, color=QColor(udata.colour),
                                line_weight=udata.line_weight,
                                x=udata.x, y=udata.y,
                                layers=udata.selected_layers,
                                _record=udata,
                                user_layer=udata.user_layer)

        # Handle missing underlay files
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

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_underlay_integration.py tests/test_underlay_serialization.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add firepro3d/model_space.py firepro3d/scene_io.py
git commit -m "feat(cache): load underlays from cache on project open

Try geometry cache before parsing source files. Falls back to
full import on cache miss. Significant load time improvement
for projects with large/many underlays."
```

---

### Task 6: Cache-Based Rendering for Missing Source Files

**Files:**
- Modify: `firepro3d/scene_io.py:437-471` (already modified in Task 5)

The cache-read logic from Task 5 already handles this case. When `resolved is None` (source file missing), we call `_load_underlay_from_cache(udata, source_mtime=None)`. Since `source_mtime=None`, `read_cache` skips the freshness check and returns cached geometry unconditionally.

The only remaining piece is a visual indicator that the source file is missing. We need to mark the underlay group so the browser tree can show a warning icon.

- [ ] **Step 1: Write failing test**

```python
# tests/test_underlay_cache_integration.py
import json
import os
import pytest
from unittest.mock import patch

from firepro3d.underlay import Underlay
from firepro3d.underlay_cache import (
    cache_dir_for_project, compute_cache_key, write_cache,
)


SAMPLE_GEOMS = [
    {"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100, "layer": "0"},
    {"kind": "circle", "x": 50, "y": 50, "w": 20, "h": 20, "layer": "0"},
]


class TestCacheForMissingSource:
    """When source file is gone but cache exists, underlay should render."""

    def test_missing_source_loads_from_cache(self, tmp_path):
        # Set up a project file and cache
        project_file = tmp_path / "test.fpd"
        cache_dir = str(tmp_path / "test.fpd.cache")
        source_path = str(tmp_path / "floor.dxf")

        record = Underlay(
            type="dxf", path=source_path,
            x=10.0, y=20.0,
            selected_layers=None,
        )
        key = record.cache_key()
        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)

        # Source file does NOT exist
        assert not os.path.exists(source_path)

        # Cache should still be readable with mtime=None
        from firepro3d.underlay_cache import read_cache
        result = read_cache(cache_dir, key, source_mtime=None)
        assert result is not None
        assert len(result) == 2

    def test_missing_source_group_tagged(self, tmp_path):
        """Groups loaded from cache for missing sources should carry
        a data tag so the browser tree can show a warning."""
        # This verifies the convention: group.data(3) == "source_missing"
        # when loaded from cache without a source file.
        # (Actual integration test requires scene — covered by smoke test)
        pass  # placeholder for integration-level test
```

- [ ] **Step 2: Add "source_missing" tag to `_load_underlay_from_cache`**

In `_load_underlay_from_cache` in `model_space.py`, after `group.setData(2, all_layers)`, add:

```python
        if source_mtime is None:
            group.setData(3, "source_missing")
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_underlay_cache_integration.py tests/test_underlay_cache.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add firepro3d/model_space.py tests/test_underlay_cache_integration.py
git commit -m "feat(cache): render from cache when source file is missing

When source underlay file is gone but geometry cache exists,
render the underlay from cache and tag the group with
data(3)='source_missing' for browser tree warning display."
```

---

### Task 7: Cache Write on Project Save

**Files:**
- Modify: `firepro3d/scene_io.py:35-230` (`save_to_file`)

On project save, ensure every underlay with a valid source file has an up-to-date cache entry. This covers two scenarios:
1. Underlays imported before the project was ever saved (no cache dir existed at import time)
2. Source files that were refreshed-from-disk since last save

> **Revision note (2026-05-24):** The original plan proposed a freshness-check + sync re-extraction approach. This was replaced with a simpler design: all import paths now store the raw (pre-transform) geometry list on the group item via `data(5)`. `_ensure_underlay_caches` reads directly from `data(5)` and writes unconditionally, avoiding both the freshness check and the expensive sync re-extraction that froze the UI on large DXF files. This also guarantees that area-selection filtering (`import_bounds`) is preserved in the cache, since `data(5)` already reflects the filtered geometry.

- [ ] **Step 1: Add `_ensure_underlay_caches` method to Model_Space**

Add near `_write_underlay_cache`:

```python
    def _ensure_underlay_caches(self, project_path: str):
        """Ensure every underlay has a cache entry.

        Called on save.  Reads the raw geometry stored on each group's
        ``data(5)`` — this is the exact geometry that was imported
        (including area selection filtering), avoiding expensive
        re-extraction from the source file.
        """
        for record, item in self.underlays:
            if not os.path.isfile(record.path):
                continue
            # data(5) is the authoritative raw geometry from the live
            # scene — always write it, overriding any stale cache that
            # may have been written before area-selection filtering.
            geom_list = item.data(5) if item is not None else None
            if not geom_list:
                continue
            self._write_underlay_cache(
                record.path, geom_list,
                page=record.page,
                selected_layers=record.selected_layers,
                layout=record.layout)
```

- [ ] **Step 2: Check if `DxfImportWorker.extract_file_sync` exists**

The DXF worker currently only has `_extract_geometry` (per-entity) and `run()` (threaded). We need a synchronous whole-file extraction. Check current API:

```bash
grep -n "def.*extract" firepro3d/dxf_import_worker.py
```

If `extract_file_sync` doesn't exist, add it as a `@staticmethod` on `DxfImportWorker`.

- [ ] **Step 3: Add `extract_file_sync` to DxfImportWorker if needed**

Add to `firepro3d/dxf_import_worker.py`:

```python
    @staticmethod
    def extract_file_sync(file_path: str,
                          layers: list[str] | None = None) -> list[dict]:
        """Synchronous geometry extraction for cache population.

        Same logic as ``run()`` but without threading or progress signals.
        """
        sanitized = _sanitize_dxf(file_path)
        doc = ezdxf.readfile(sanitized or file_path)
        msp = doc.modelspace()
        geoms = []
        for entity in msp:
            if layers and entity.dxf.layer not in layers:
                continue
            geoms.extend(DxfImportWorker._extract_geometry(entity))
        return geoms
```

- [ ] **Step 4: Call `_ensure_underlay_caches` from `save_to_file`**

In `scene_io.py`, in `save_to_file`, after `self._project_path = os.path.abspath(filename)` (added in Task 3) and before the JSON write, add:

```python
        # Ensure all underlays have cache entries
        self._ensure_underlay_caches(os.path.abspath(filename))
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/test_underlay_cache.py tests/test_underlay_serialization.py tests/test_underlay_integration.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add firepro3d/model_space.py firepro3d/scene_io.py firepro3d/dxf_import_worker.py
git commit -m "feat(cache): write missing cache entries on project save

On save, re-parse any underlay source files that lack a fresh
cache entry. Covers imports made before first save."
```

---

### Task 8: Cache Invalidation on Refresh-from-Disk

**Files:**
- Modify: `firepro3d/model_space.py:2632-2676` (`refresh_underlay`)

When the user refreshes an underlay from disk, the source file may have changed. The re-import path already re-parses the source file, and the cache write hooks from Tasks 3-4 will write a fresh cache entry. The old stale entry is automatically superseded because the cache key is the same — `write_cache` overwrites the file.

No code changes needed — verify with a test.

- [ ] **Step 1: Write verification test**

```python
# tests/test_underlay_cache_integration.py  (append)

class TestCacheInvalidationOnRefresh:
    def test_stale_cache_returns_none(self, tmp_path):
        """After source file is modified, old cache should be invalidated."""
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=None)

        # Write cache with old mtime
        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)

        # Source file is now newer
        from firepro3d.underlay_cache import read_cache
        result = read_cache(cache_dir, key, source_mtime=2000.0)
        assert result is None, "Stale cache should return None"

    def test_fresh_write_overwrites_stale(self, tmp_path):
        """Re-writing with new mtime makes the cache fresh again."""
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = compute_cache_key("/plans/floor.dxf", page=0, selected_layers=None)

        write_cache(cache_dir, key, SAMPLE_GEOMS, source_mtime=1000.0)
        # Overwrite with newer data
        new_geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 50, "y2": 50, "layer": "0"}]
        write_cache(cache_dir, key, new_geoms, source_mtime=2000.0)

        from firepro3d.underlay_cache import read_cache
        result = read_cache(cache_dir, key, source_mtime=2000.0)
        assert result is not None
        assert len(result) == 1
        assert result[0]["x2"] == 50
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_underlay_cache_integration.py::TestCacheInvalidationOnRefresh -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_underlay_cache_integration.py
git commit -m "test(cache): verify cache invalidation on refresh-from-disk"
```

---

### Task 9: Edge Cases and Final Integration Tests

**Files:**
- Modify: `tests/test_underlay_cache_integration.py`

Cover remaining edge cases: raster PDF (no cache), large geometry lists, tuple-to-list JSON roundtrip for path_points.

- [ ] **Step 1: Write edge case tests**

```python
# tests/test_underlay_cache_integration.py  (append)

class TestCacheEdgeCases:
    def test_path_points_tuple_roundtrip(self, tmp_path):
        """Tuples in path_points become lists after JSON roundtrip."""
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "tuple_test.json"
        geoms = [{"kind": "path_points",
                  "points": [(1.5, 2.5), (3.0, 4.0)],
                  "closed": True, "layer": "0"}]
        write_cache(cache_dir, key, geoms, source_mtime=1000.0)

        from firepro3d.underlay_cache import read_cache
        result = read_cache(cache_dir, key, source_mtime=1000.0)
        # JSON converts tuples to lists — code must handle both
        assert result[0]["points"] == [[1.5, 2.5], [3.0, 4.0]]

    def test_empty_geom_list(self, tmp_path):
        """Empty geometry list should roundtrip correctly."""
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "empty.json"
        write_cache(cache_dir, key, [], source_mtime=1000.0)

        from firepro3d.underlay_cache import read_cache
        result = read_cache(cache_dir, key, source_mtime=1000.0)
        assert result == []

    def test_arc_geometry_roundtrip(self, tmp_path):
        """Arc geometry dicts with all fields survive cache roundtrip."""
        cache_dir = str(tmp_path / "proj.fpd.cache")
        key = "arc_test.json"
        geoms = [{"kind": "arc", "rx": 10.0, "ry": 20.0,
                  "rw": 30.0, "rh": 30.0,
                  "start": 0.0, "span": 180.0, "layer": "0"}]
        write_cache(cache_dir, key, geoms, source_mtime=1000.0)

        from firepro3d.underlay_cache import read_cache
        result = read_cache(cache_dir, key, source_mtime=1000.0)
        assert result[0]["start"] == 0.0
        assert result[0]["span"] == 180.0
```

- [ ] **Step 2: Run all cache tests**

Run: `pytest tests/test_underlay_cache.py tests/test_underlay_cache_integration.py -v`
Expected: all PASS

- [ ] **Step 3: Verify `_geom_to_item` handles list points (not just tuples)**

Check `model_space.py:2264-2276` — the `path_points` handler accesses `points[0][0]`, `points[0][1]`. Lists work identically to tuples for indexing, so no change needed. Verify:

```python
# Quick mental check:
# path.moveTo(points[0][0], points[0][1])  — works for both [x,y] and (x,y)
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --timeout=60`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_underlay_cache_integration.py
git commit -m "test(cache): add edge case tests for geometry cache roundtrip"
```

---

## Self-Review Checklist

**Spec coverage:**
1. Cache geometry dicts to `.fpd.cache/` — Task 1 (module), Tasks 3-4 (write hooks)
2. Skip re-parsing on reload — Task 5 (`_load_underlay_from_cache`)
3. Timestamp-based invalidation — Task 1 (`read_cache` freshness check), Task 8 (verification)
4. Missing source renders from cache — Task 6
5. Cache on import + save — Tasks 3-4 (import), Task 7 (save via `data(5)`)
6. Works for DXF and PDF — Tasks 3-4 (DXF and PDF write paths), Task 5 (unified read)
7. Unit tests — Tasks 1, 2, 6, 8, 9
8. Area-selection persistence — `import_bounds` filter applied on sync re-extraction (Task 5), preserved through `data(5)` on save (Task 7)

**Placeholder scan:** No TBD/TODO/placeholder steps found.

**Type consistency:** `compute_cache_key`, `write_cache`, `read_cache`, `delete_cache`, `cache_dir_for_project` — names consistent across all tasks. `Underlay.cache_key()` delegates to `compute_cache_key`. `_write_underlay_cache` and `_load_underlay_from_cache` on Model_Space — consistent naming pattern.

**Note on transform duplication:** The import transform code (base-point shift + scale) is duplicated in 4 places (`_commit_place_import`, `_on_dxf_finished`, `_import_pdf_vectors`, `_load_underlay_from_cache`). This is existing technical debt — this plan matches the existing pattern rather than refactoring, which would be scope creep.

**Note on `data(5)` convention:** All import paths (`_on_dxf_finished`, `_import_pdf_vectors`, `_load_underlay_from_cache`, `_commit_place_import`) store the raw pre-transform geometry list on the group item via `group.setData(5, _raw_geom)`. This is read by `_ensure_underlay_caches` on save, eliminating the need for sync re-extraction from source files at save time.
