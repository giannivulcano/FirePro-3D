# Multi-Layout DXF/DWG Import Design

**Date:** 2026-05-20
**Status:** Implemented
**Revision:** 2 (post-implementation findings: UI restructure, extraction bug fixes)

## Problem

DXF files converted from DWG (or authored with multiple layouts) contain a Model space
and one or more paper-space layouts. The current DXF import path always reads Model space
and ignores paper layouts entirely. Only the DWG import path has layout selection — via a
separate `QInputDialog` popup and its own extraction pipeline.

Users need to pick which layout to import from a multi-layout DXF, and the DWG import
should use the identical pipeline with only a conversion step prepended.

## Requirements

1. DXF files with multiple layouts show a layout picker in the import dialog.
2. DXF files with a single layout (Model only) behave identically to today.
3. DWG import becomes: convert DWG → DXF via ODA, then follow the DXF import path.
4. Paper layouts render as they appear in AutoCAD (model geometry visible through
   viewports + paper-space annotations).
5. Source layer information preserved for all layouts.
6. Refresh from disk uses the saved layout name silently.
7. PDF import path is completely untouched.

## Design

### Import Dialog UI Changes

All controls (file picker, layout combo, preview mode buttons, layer/scale/rotation/
base point) live in a scrollable right panel. The left side is preview-only, maximizing
the viewport area.

A `QComboBox` labeled "Layout:" is added to the right panel, below the file picker
group and above the preview mode buttons.

**Visibility rules:**
- Hidden by default (both label and combo).
- Shown only when the opened file has 2+ layouts.
- Hidden for PDF files (no layout concept).

**Deferred extraction flow:**
1. User opens a DXF or DWG file.
2. `ezdxf` reads the document (metadata only — fast).
3. `list_layouts(doc)` returns layout names (Model always first).
4. If 1 layout: combo stays hidden, extraction starts immediately (current behavior).
5. If 2+ layouts: combo shown and populated, preview displays a "Select a layout to
   preview" placeholder, no extraction occurs.
6. User picks a layout → synchronous extraction runs → layer checkboxes populate →
   preview renders.
7. User switches layout → re-extract → layers reset → preview rebuilds.

### Unified Extraction Pipeline

A single extraction path handles both Model and paper layouts. Triggered by layout
selection (combo signal or auto-select for single-layout files).

**Model layout selected:**
1. Extract all model-space geometry via `DxfImportWorker._extract_geometry()` (sync).
2. Populate layer checkboxes.
3. Render preview.

**Paper layout selected:**
1. `get_viewport_bounds(layout_name, doc)` → list of model-space bounding rects from
   VIEWPORT entities in the paper layout.
2. Extract all model-space geometry (sync).
3. `filter_geoms_by_bounds(geoms, vp_bounds)` → keep only geometry visible through
   viewports.
4. `extract_layout_entities(layout_name, doc)` → paper-space annotations (title block,
   notes, dimensions) transformed to model-space coordinates.
5. Combine filtered model geometry + paper annotations into one geometry list.
6. Populate layer checkboxes from combined list.
7. Render preview.

This is the same pipeline the DWG path uses today — it moves into a shared method
(`_extract_for_layout()`).

### Paper-Space Entity Transform Details

`extract_layout_entities()` transforms paper-space annotations to model-space
coordinates using the largest viewport's scale mapping. Key behaviors:

- **Text size scaling:** Paper-space text height is multiplied by `ps_to_ms`
  (viewport model-height / viewport paper-height) so annotations render at the
  correct scale relative to model geometry.
- **Multiline MTEXT:** Line breaks (`\n` from `plain_text()`) are preserved in
  geometry dicts and rendered as separate lines in the preview, each individually
  aligned per `halign`.
- **Text alignment:** MTEXT `attachment_point` (1-9) is mapped to `halign`/`valign`
  fields and used by the preview renderer to offset from the insertion point.
  `QPainterPath.addText()` always places at baseline-left, so center/right/middle
  alignments require computed offsets via `QFontMetricsF`.

### DWG Path Simplification

`_load_dwg()` reduces to a thin wrapper:

1. `find_oda_converter()` → ODA path (search QSettings, PATH, common dirs).
2. `convert_dwg_to_dxf(oda_path, dwg_path, project_dir)` → converted DXF path
   (persistent in `UNDERLAY_REF/` if project is saved, temp otherwise).
3. Call `_load_dxf(converted_dxf_path)`.

All layout enumeration, selection, viewport handling, and extraction now lives in the
DXF path. The QInputDialog layout popup is removed.

### Function Renames in dwg_converter.py

| Old Name | New Name | Reason |
|---|---|---|
| `list_dwg_layouts()` | `list_layouts()` | Already takes generic `doc` param |
| `get_viewport_bounds()` | unchanged | Already generic |
| `filter_geoms_by_bounds()` | unchanged | Already generic |
| `extract_layout_entities()` | unchanged | Already generic |
| `find_oda_converter()` | unchanged | DWG-specific |
| `convert_dwg_to_dxf()` | unchanged | DWG-specific |
| `read_dxf()` | unchanged | DXF-specific |

Module stays `dwg_converter.py` — it still owns DWG conversion code.

### Persistence & Refresh

**No data model changes.** The `Underlay` dataclass already has `layout: str = ""`.
DXF imports using a paper layout store the layout name. Model-space imports store `""`.

**Cache** — no changes. `compute_cache_key()` already includes the layout parameter.
Different layouts of the same file get separate cache entries.

**Refresh from disk:**
- Reads saved `layout` from Underlay record.
- Re-extracts using that layout name silently (no picker).
- If saved layout no longer exists in the file: fall back to Model, log a console
  warning.
- All other saved params preserved (scale, rotation, base point, selected layers).

**Project load:**
- `Underlay.from_dict()` reads `layout` field (defaults to `""` if missing).
- Cache checked via `compute_cache_key()` with layout.
- If cache miss, re-extracts from source using saved layout name.
- Same fall-back-to-Model if layout no longer exists.

### Edge Cases

| Scenario | Behavior |
|---|---|
| Plain DXF, only Model space | Combo hidden, extract immediately — identical to today |
| DXF with multiple layouts | Combo shown, wait for pick, extract on selection |
| DWG, only Model space | Convert → combo hidden, extract immediately |
| DWG with multiple layouts | Convert → combo shown, wait for pick |
| DWG, ODA converter not found | Existing browse/error flow unchanged |
| PDF | Entire flow unchanged |
| Refresh, saved layout exists | Silent re-extract with saved layout |
| Refresh, saved layout gone | Fall back to Model, console warning |
| Layout switch mid-preview | Re-extract, rebuild layers and preview |
| Layer filter + layout switch | Layer checkboxes reset (new layout may have different layers) |

### What Does NOT Change

- PDF import path.
- `Underlay` dataclass (no new fields).
- Cache system.
- Scene-side import (`model_space.py`) — receives the same `ImportParams`.
- Scale calibration, base point pick, rotation.

## Implementation Findings

Bugs discovered and fixed during implementation testing with real DWG files:

### INSERT explosion exception handling

The `try/except` around the `virtual_entities()` loop in `_extract_geometry()`
wrapped the **entire** `for` loop. A single exception from any sub-entity (e.g.,
a `POLYLINE` with no `get_points()` method) would silently stop processing **all
remaining** entities in the block. In one test file, a POLYLINE at index 4217 of
5068 virtual entities caused 851 entities to be dropped — including all gridlines,
grid bubbles, and grid dimensions.

**Fix:** Materialize the generator first (`list(entity.virtual_entities())`), then
wrap each individual entity's extraction in its own `try/except`. One bad entity
no longer kills the rest.

### POLYLINE vs LWPOLYLINE

ezdxf's `POLYLINE` (3D polyline, often from block explosions) does not have a
`get_points()` method — that is `LWPOLYLINE`-only. The extraction code assumed
both had `get_points()`, causing `AttributeError` on POLYLINE entities. Fixed with
a `hasattr` check that falls back to reading `entity.vertices` directly.

### Paper-space text size not scaled

`extract_layout_entities()` transformed text position (`x`, `y`) but not the
`size` field. Paper-space text at 2.5mm height stayed at 2.5 units in model space
(where the building spans thousands of units), making all paper-space annotations
invisible. Fixed by multiplying `size` by `ps_to_ms`.

### Preview text alignment ignored

The preview renderer used `QPainterPath.addText(x, y, font, text)` which always
places at baseline-left. MTEXT with center/middle alignment (71 of 94 entities in
one test file) had their insertion point treated as top-left, causing significant
position errors magnified by `ps_to_ms`. Fixed with `QFontMetricsF`-based offsets.

### Multiline MTEXT on single line

`QPainterPath.addText()` ignores `\n` characters. MTEXT with line breaks (e.g.,
"PRODUCTION PLANT\nGROUND FLOOR") rendered as a single concatenated line. Fixed by
splitting on `\n` and rendering each line at the correct vertical offset.

## Files Modified

| File | Change |
|---|---|
| `firepro3d/dxf_preview_dialog.py` | Layout combo, deferred extraction, shared `_extract_for_layout()`, simplified `_load_dwg()`, updated `get_import_params()`, UI restructured (controls in right panel), text alignment + multiline rendering |
| `firepro3d/dwg_converter.py` | Rename `list_dwg_layouts()` → `list_layouts()`, text size scaling in paper-to-model transform |
| `firepro3d/dxf_import_worker.py` | Per-entity exception handling in INSERT explosion, POLYLINE `.vertices` fallback |
| `tests/test_dwg_converter.py` | Update test references for renamed function, add DXF layout test |
