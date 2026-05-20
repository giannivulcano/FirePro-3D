# Multi-Layout DXF/DWG Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users pick which layout (Model or paper-space) to import from multi-layout DXF files, and unify DWG import to use the same flow with a conversion step prepended.

**Architecture:** Add a layout combo box to `UnderlayImportDialog`, extract a shared `_extract_for_layout()` method that handles both Model and paper-space layouts (viewport bounds filtering + paper annotations). `_load_dxf()` defers extraction until layout selection. `_load_dwg()` becomes a thin wrapper: convert DWG → DXF, then call `_load_dxf()`.

**Tech Stack:** Python 3.x, PyQt6, ezdxf

**Spec:** `docs/superpowers/specs/2026-05-20-multi-layout-dxf-import-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `firepro3d/dwg_converter.py` | Modify | Rename `list_dwg_layouts` → `list_layouts` |
| `firepro3d/dxf_preview_dialog.py` | Modify | Layout combo UI, `_extract_for_layout()`, refactored `_load_dxf()`, simplified `_load_dwg()`, updated `get_import_params()` |
| `tests/test_dwg_converter.py` | Modify | Update renamed function refs, add new DXF-layout test |

---

### Task 1: Rename `list_dwg_layouts` → `list_layouts`

**Files:**
- Modify: `firepro3d/dwg_converter.py:255`
- Modify: `firepro3d/dwg_converter.py:241` (docstring reference)
- Modify: `tests/test_dwg_converter.py:110-139`

- [ ] **Step 1: Update tests to use new name**

In `tests/test_dwg_converter.py`, replace all `list_dwg_layouts` references with `list_layouts`:

```python
# test_list_layouts_model_only (line 109-118)
def test_list_layouts_model_only():
    """list_layouts() returns ['Model'] for single-layout DXF."""
    from firepro3d.dwg_converter import list_layouts

    mock_doc = mock.MagicMock()
    mock_doc.layouts.names.return_value = ["Model"]

    with mock.patch("ezdxf.readfile", return_value=mock_doc):
        result = list_layouts("/tmp/test.dxf")
        assert result == ["Model"]


# test_list_layouts_multiple (line 121-131)
def test_list_layouts_multiple():
    """list_layouts() returns all layout names, Model first."""
    from firepro3d.dwg_converter import list_layouts

    mock_doc = mock.MagicMock()
    mock_doc.layouts.names.return_value = ["Model", "Sheet 1", "24x36 Plan"]

    with mock.patch("ezdxf.readfile", return_value=mock_doc):
        result = list_layouts("/tmp/test.dxf")
        assert result[0] == "Model"
        assert set(result) == {"Model", "Sheet 1", "24x36 Plan"}


# test_list_layouts_error (line 134-139)
def test_list_layouts_error():
    """list_layouts() returns ['Model'] on read failure."""
    from firepro3d.dwg_converter import list_layouts

    with mock.patch("ezdxf.readfile", side_effect=Exception("corrupt")):
        result = list_layouts("/tmp/test.dxf")
        assert result == ["Model"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dwg_converter.py::test_list_layouts_model_only tests/test_dwg_converter.py::test_list_layouts_multiple tests/test_dwg_converter.py::test_list_layouts_error -v`
Expected: FAIL with `ImportError: cannot import name 'list_layouts'`

- [ ] **Step 3: Rename function in dwg_converter.py**

In `firepro3d/dwg_converter.py`:

Line 241 docstring — change:
```python
    Call once and pass the result to :func:`list_dwg_layouts`,
```
to:
```python
    Call once and pass the result to :func:`list_layouts`,
```

Line 255 function definition — change:
```python
def list_dwg_layouts(dxf_path: str = "", doc=None) -> list[str]:
    """Read layout names from a converted DXF file.
```
to:
```python
def list_layouts(dxf_path: str = "", doc=None) -> list[str]:
    """Read layout names from a DXF file.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dwg_converter.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add firepro3d/dwg_converter.py tests/test_dwg_converter.py
git commit -m "refactor: rename list_dwg_layouts to list_layouts"
```

---

### Task 2: Add layout combo box to import dialog UI

**Files:**
- Modify: `firepro3d/dxf_preview_dialog.py:375-407` (`_build_ui`)

- [ ] **Step 1: Add layout combo box in `_build_ui()`**

In `firepro3d/dxf_preview_dialog.py`, in `_build_ui()`, insert the layout bar after the file bar (after `outer.addLayout(file_bar)` at line 391) and before the thumbnail strip (line 393):

```python
        outer.addLayout(file_bar)

        # Layout selector (hidden by default, shown for multi-layout DXF/DWG)
        layout_bar = QHBoxLayout()
        layout_bar.addWidget(QLabel("Layout:"))
        self._layout_combo = QComboBox()
        self._layout_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        layout_bar.addWidget(self._layout_combo, 1)
        self._layout_combo.setVisible(False)
        outer.addLayout(layout_bar)

        # PDF page thumbnail strip (hidden by default)
```

- [ ] **Step 2: Add `_on_layout_changed` stub**

Add a stub method after `_detect_dxf_units()` (after line 828), in the DXF loading section:

```python
    def _on_layout_changed(self, index: int):
        """Handle layout combo selection — extract geometry for the chosen layout."""
        if index < 0 or not hasattr(self, "_doc") or self._doc is None:
            return
        layout_name = self._layout_combo.currentText()
        self._extract_for_layout(layout_name)
```

- [ ] **Step 3: Verify app launches**

Run: `python main.py`
Open the import dialog (File → Import Underlay). Confirm the dialog opens without errors. The layout combo should not be visible (no file loaded yet). Close the app.

- [ ] **Step 4: Commit**

```bash
git add firepro3d/dxf_preview_dialog.py
git commit -m "feat: add layout combo box to import dialog (hidden by default)"
```

---

### Task 3: Extract `_extract_for_layout()` shared method

**Files:**
- Modify: `firepro3d/dxf_preview_dialog.py`

This method encapsulates the full extraction pipeline for a given layout. It handles both Model space (direct extraction) and paper layouts (viewport bounds → extraction → filter → paper annotations). It is called by `_on_layout_changed()` and directly by `_load_dxf()` for single-layout files.

- [ ] **Step 1: Add `_extract_for_layout()` method**

Add this method after `_on_layout_changed()`:

```python
    def _extract_for_layout(self, layout_name: str):
        """Run the full extraction pipeline for a layout and rebuild the preview.

        For Model: extracts all model-space geometry.
        For paper layouts: viewport-filtered model geometry + paper annotations.
        """
        doc = self._doc
        path = self._file_edit.text().strip()
        self._selected_layout = layout_name

        # ── Viewport bounds (paper layouts only) ─────────────────────────
        vp_bounds = None
        if layout_name != "Model":
            from .dwg_converter import get_viewport_bounds
            vp_bounds = get_viewport_bounds(
                layout_name=layout_name, doc=doc)

        # ── Extract model-space geometry ─────────────────────────────────
        from .dxf_import_worker import DxfImportWorker, _build_layer_colors
        msp = doc.modelspace()
        all_ents = list(msp)

        # Collect layer names from doc + entity attributes
        layers_set: set[str] = {"0"}
        for layer in doc.layers:
            layers_set.add(layer.dxf.name)
        for entity in msp:
            layers_set.add(
                entity.dxf.get("layer", "0")
                if hasattr(entity.dxf, "get") else "0"
            )

        self._set_extracting(len(all_ents))
        worker_ref = DxfImportWorker.__new__(DxfImportWorker)
        worker_ref._cancelled = False
        worker_ref._layer_colors = _build_layer_colors(doc)

        geoms: list[dict] = []
        for i, ent in enumerate(all_ents):
            if self._loading_bar.cancelled:
                break
            if i % 200 == 0:
                self._update_progress(i, len(all_ents))
            # Pre-filter by viewport bounds at entity level
            if vp_bounds and not self._entity_in_viewport(ent, vp_bounds):
                continue
            try:
                g = worker_ref._extract_geometry(ent)
                if g is not None:
                    if isinstance(g, list):
                        geoms.extend(g)
                    else:
                        geoms.append(g)
            except Exception:
                pass

        self._all_geoms = geoms

        # ── Post-extraction viewport filter (catches INSERT/HATCH) ───────
        if vp_bounds:
            from .dwg_converter import filter_geoms_by_bounds
            self._all_geoms = filter_geoms_by_bounds(
                self._all_geoms, vp_bounds)

        # ── Paper layout annotations ─────────────────────────────────────
        if layout_name != "Model":
            from .dwg_converter import extract_layout_entities
            layout_geoms = extract_layout_entities(
                layout_name=layout_name, doc=doc)
            if layout_geoms:
                self._all_geoms.extend(layout_geoms)

        # ── Entity type dialog (DWG files only, first extraction) ────────
        if getattr(self, "_show_entity_type_filter", False):
            self._show_entity_type_filter = False
            self._clear_loading()
            excluded = self._show_geom_type_dialog()
            if excluded is None:
                # User cancelled — clean up and bail
                from .dwg_converter import cleanup_converted_dxf
                cleanup_converted_dxf(
                    getattr(self, "_converted_dxf_path", ""))
                self._all_geoms = []
                self._rebuild_preview()
                self._info_lbl.setText(
                    "Import cancelled.")
                return
            if excluded:
                self._all_geoms = [
                    g for g in self._all_geoms
                    if g.get("kind") not in excluded
                ]

        # ── Populate layers from combined geometry ───────────────────────
        geom_layers = {g.get("layer", "0") for g in self._all_geoms}
        self._layers = sorted(layers_set | geom_layers)
        self._populate_layer_list()
        self._selected_indices = None

        # ── Rebuild preview ──────────────────────────────────────────────
        self._set_loading("Building preview\u2026")
        self._rebuild_preview()
        self._clear_loading()

        n = len(self._all_geoms)
        layout_label = (f" (layout: {layout_name})"
                        if layout_name != "Model" else "")
        self._info_lbl.setText(
            f"{n:,} entities loaded from "
            f"{os.path.basename(path)}{layout_label}")
        self._update_status()
```

- [ ] **Step 2: Verify app launches**

Run: `python main.py`
Open the import dialog. Confirm it opens without errors. Close the app.

- [ ] **Step 3: Commit**

```bash
git add firepro3d/dxf_preview_dialog.py
git commit -m "feat: add _extract_for_layout() shared extraction pipeline"
```

---

### Task 4: Refactor `_load_dxf()` for deferred extraction

**Files:**
- Modify: `firepro3d/dxf_preview_dialog.py:731-808`

Replace the entire `_load_dxf()` method. The new version reads the doc, detects layouts, and either auto-extracts (single layout) or defers extraction to the combo (multiple layouts).

- [ ] **Step 1: Replace `_load_dxf()`**

Replace lines 731-808 (the entire `_load_dxf` method) with:

```python
    def _load_dxf(self, path: str, _doc=None):
        """Load a DXF file with layout detection and deferred extraction.

        Args:
            path: Path to the DXF file.
            _doc: Pre-read ezdxf document (skips sanitization/read).
                  Used by _load_dwg() to pass ODA-converted docs that
                  must not go through _sanitize_dxf().
        """
        self._file_type = "dxf"
        self._pdf_opts_grp.setVisible(False)
        self._thumb_list.setVisible(False)
        self._has_vectors = True

        if not _HAS_EZDXF:
            QMessageBox.warning(self, "Missing dependency",
                                "ezdxf is required for DXF import.\n"
                                "Install it with: pip install ezdxf")
            return

        if _doc is not None:
            doc = _doc
        else:
            self._set_loading("Reading DXF file\u2026")
            clean = _sanitize_dxf(path)
            try:
                doc = ezdxf.readfile(clean)
            except Exception as e:
                self._clear_loading()
                self._info_lbl.setText(f"Error: {e}")
                return
            finally:
                if clean != path and os.path.exists(clean):
                    os.remove(clean)

        self._doc = doc

        # Auto-detect DXF units ($INSUNITS)
        self._detect_dxf_units(doc)

        # Detect layouts
        from .dwg_converter import list_layouts
        layouts = list_layouts(doc=doc)

        if len(layouts) <= 1:
            # Single layout — hide combo, extract immediately
            self._layout_combo.blockSignals(True)
            self._layout_combo.clear()
            self._layout_combo.blockSignals(False)
            self._layout_combo.setVisible(False)
            self._clear_loading()
            self._extract_for_layout("Model")
        else:
            # Multiple layouts — show combo, defer extraction
            self._layout_combo.blockSignals(True)
            self._layout_combo.clear()
            for name in layouts:
                self._layout_combo.addItem(name)
            self._layout_combo.setCurrentIndex(-1)  # no selection
            self._layout_combo.blockSignals(False)
            self._layout_combo.setVisible(True)
            self._clear_loading()
            self._info_lbl.setText("Select a layout to preview.")
            self._update_status()
```

- [ ] **Step 2: Smoke-test DXF import**

Run: `python main.py`

Test with a single-layout DXF:
1. File → Import Underlay → browse a simple DXF file
2. Confirm: layout combo is NOT visible, geometry previews immediately (same as before)

If you have a multi-layout DXF (converted from DWG):
1. Import it — layout combo should appear with layout names
2. Preview should be empty with "Select a layout to preview."
3. Pick a layout — extraction runs, preview populates
4. Switch layouts — preview rebuilds with new layout

- [ ] **Step 3: Commit**

```bash
git add firepro3d/dxf_preview_dialog.py
git commit -m "feat: refactor _load_dxf() for layout detection and deferred extraction"
```

---

### Task 5: Simplify `_load_dwg()` to thin wrapper

**Files:**
- Modify: `firepro3d/dxf_preview_dialog.py:832-969`

Replace the entire `_load_dwg()` method. Keep ODA detection + conversion + error handling. Remove stages 3-9 (layout selection, viewport handling, extraction, entity type dialog, preview rebuild). Just convert, then call `_load_dxf()`.

- [ ] **Step 1: Replace `_load_dwg()`**

Replace lines 832-969 (the entire `_load_dwg` method, up to but NOT including `_browse_for_oda`) with:

```python
    def _load_dwg(self, path: str):
        """Load a DWG file by converting to DXF via ODA File Converter."""
        from .dwg_converter import (
            find_oda_converter, convert_dwg_to_dxf,
            cleanup_converted_dxf, read_dxf, ODA_DOWNLOAD_URL,
        )

        oda_path = find_oda_converter()
        if oda_path is None:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("ODA File Converter Required")
            msg.setText(
                "DWG import requires ODA File Converter (free download).\n\n"
                f"Download from:\n{ODA_DOWNLOAD_URL}")
            msg.addButton(QMessageBox.StandardButton.Cancel)
            locate_btn = msg.addButton("Locate ODA\u2026",
                                       QMessageBox.ButtonRole.ActionRole)
            msg.exec()
            if msg.clickedButton() == locate_btn:
                oda_path = self._browse_for_oda()
            if oda_path is None:
                return

        # ── Stage 1: ODA conversion ──────────────────────────────────────
        self._set_loading("Converting DWG \u2192 DXF\u2026")
        dxf_path = convert_dwg_to_dxf(oda_path, path,
                                       project_dir=self._default_dir or None)
        while dxf_path is None:
            self._clear_loading()
            from .dwg_converter import get_last_error
            diag = get_last_error()
            detail = f"\n\nDiagnostics:\n{diag}" if diag else ""
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Conversion Failed")
            msg.setText(
                f"ODA File Converter could not convert this DWG file.\n"
                f"ODA path: {oda_path}{detail}")
            msg.addButton(QMessageBox.StandardButton.Cancel)
            change_btn = msg.addButton("Change ODA Path\u2026",
                                       QMessageBox.ButtonRole.ActionRole)
            msg.exec()
            if msg.clickedButton() != change_btn:
                return
            new_path = self._browse_for_oda()
            if new_path is None:
                return
            oda_path = new_path
            self._set_loading("Converting DWG \u2192 DXF\u2026")
            dxf_path = convert_dwg_to_dxf(oda_path, path,
                                           project_dir=self._default_dir or None)

        # ── Stage 2: Read converted DXF (bypasses _sanitize_dxf) ────────
        self._set_loading("Reading DXF\u2026")
        doc = read_dxf(dxf_path)
        if doc is None:
            self._clear_loading()
            QMessageBox.warning(self, "Read Error",
                                f"Could not read converted DXF:\n{dxf_path}")
            return
        self._clear_loading()

        # ── Stage 3: Hand off to unified DXF path ───────────────────────
        self._dwg_source_path = path
        self._converted_dxf_path = dxf_path
        self._show_entity_type_filter = True
        self._load_dxf(dxf_path, _doc=doc)
        self._file_type = "dwg"

        # Clean up temp DXFs (UNDERLAY_REF DXFs are preserved).
        # Safe because the ezdxf doc is in memory as self._doc.
        cleanup_converted_dxf(dxf_path)
```

- [ ] **Step 2: Smoke-test DWG import**

Run: `python main.py`

If ODA File Converter is installed and a DWG file is available:
1. File → Import Underlay → browse a DWG file
2. Confirm: conversion runs, layout combo appears (if multi-layout), entity type dialog shown after first layout pick
3. Single-layout DWG: entity type dialog shown immediately after auto-extraction

If no DWG test files are available, confirm the ODA-not-found dialog still appears correctly by testing with a `.dwg` extension file.

- [ ] **Step 3: Commit**

```bash
git add firepro3d/dxf_preview_dialog.py
git commit -m "feat: simplify _load_dwg() to conversion + _load_dxf() handoff"
```

---

### Task 6: Update `get_import_params()` to include layout for all file types

**Files:**
- Modify: `firepro3d/dxf_preview_dialog.py:1745-1781`
- Modify: `tests/test_dwg_converter.py` (add new test)

- [ ] **Step 1: Write test for DXF with layout in ImportParams**

Add to the end of `tests/test_dwg_converter.py`:

```python
def test_import_params_dxf_layout():
    """ImportParams carries layout for DXF files with paper layouts."""
    from firepro3d.dxf_preview_dialog import ImportParams
    from firepro3d.underlay import Underlay

    p = ImportParams()
    p.file_path = r"C:\drawings\floor.dxf"
    p.file_type = "dxf"
    p.layout = "Sheet 1"
    p.scale = 1.0
    p.geom_list = [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 0,
                     "layer": "0", "color": "#ffffff"}]

    record = Underlay(
        type=p.file_type, path=p.file_path,
        import_scale=p.scale, layout=p.layout,
    )
    assert record.type == "dxf"
    assert record.layout == "Sheet 1"

    # Cache key differs from same file without layout
    record_model = Underlay(
        type=p.file_type, path=p.file_path,
        import_scale=p.scale, layout="",
    )
    assert record.cache_key() != record_model.cache_key()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_dwg_converter.py::test_import_params_dxf_layout -v`
Expected: PASS (ImportParams and Underlay already support the `layout` field — this test validates the DXF + layout combination works)

- [ ] **Step 3: Update `get_import_params()` in dxf_preview_dialog.py**

Replace lines 1775-1778 (the DWG-specific layout block):

```python
        # DWG-specific: preserve original .dwg path and layout
        if self._file_type == "dwg":
            p.file_path = getattr(self, "_dwg_source_path", p.file_path)
            p.layout = getattr(self, "_dwg_layout", "")
```

with:

```python
        # Preserve original .dwg path for DWG files
        if self._file_type == "dwg":
            p.file_path = getattr(self, "_dwg_source_path", p.file_path)

        # Include selected layout for any file type (empty string = Model)
        selected = getattr(self, "_selected_layout", "")
        p.layout = "" if selected == "Model" else selected
```

- [ ] **Step 4: Update `_show_geom_type_dialog()` reference**

In `_show_geom_type_dialog()` at line 1003, change:

```python
        layout_note = getattr(self, "_dwg_layout", "Model")
```

to:

```python
        layout_note = getattr(self, "_selected_layout", "Model")
```

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/test_dwg_converter.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add firepro3d/dxf_preview_dialog.py tests/test_dwg_converter.py
git commit -m "feat: include layout in ImportParams for DXF and DWG files"
```

---

### Task 7: Final verification and cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass. Watch for import errors from the renamed function.

- [ ] **Step 2: Grep for stale `list_dwg_layouts` references**

Run: `grep -r "list_dwg_layouts" firepro3d/ tests/`
Expected: No matches. If any remain, update them to `list_layouts`.

- [ ] **Step 3: Grep for stale `_dwg_layout` references**

Run: `grep -r "_dwg_layout" firepro3d/ tests/`
Expected: No matches. If any remain, update them to `_selected_layout`.

- [ ] **Step 4: Smoke-test full workflow**

Run: `cd "D:\Custom Code\FirePro3D" && python main.py`

Verify each scenario:

1. **Single-layout DXF**: Import a plain DXF → layout combo hidden, geometry previews immediately, same behavior as before
2. **Multi-layout DXF**: Import a DXF with paper layouts → layout combo visible, "Select a layout to preview" shown, pick layout → preview populates, switch layouts → preview rebuilds
3. **DWG import** (if ODA installed): Import a DWG → conversion runs, layout combo appears, entity type dialog shown after first layout extraction
4. **PDF import**: Import a PDF → completely unchanged (layout combo stays hidden, PDF thumbnail strip works)
5. **Layer filtering**: After loading a layout, toggle layers → preview updates
6. **Scale/rotation**: Persist across layout switches

- [ ] **Step 5: Commit any remaining fixes**

```bash
git add -u
git commit -m "fix: clean up stale references from layout refactor"
```

---

## Known Limitation: Refresh with stale cache

The refresh-from-disk path re-extracts geometry via `DxfImportWorker`, which only reads model space. For paper layouts, this produces incorrect geometry if the cache is stale (source file was modified externally). This is a pre-existing limitation that also affects DWG paper layouts today.

**Mitigation:** The cache is populated correctly during initial import (with viewport filtering and paper annotations). As long as the source file hasn't changed, refresh works correctly via cache. If the source file changes, the user should re-import rather than refresh.

A follow-up task can add layout-aware extraction to the refresh path if this becomes a user pain point.
