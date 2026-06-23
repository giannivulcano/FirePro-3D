# Underlay Workflow — Specification

> **Status:** North-star design + decomposed follow-ups (spec-only — no code changes delivered by this document)
> **Source files:** `firepro3d/underlay.py`, `firepro3d/dxf_preview_dialog.py`, `firepro3d/dxf_import_worker.py`, `firepro3d/dwg_converter.py`, `firepro3d/pdf_import_worker.py`, `firepro3d/model_space.py`, `firepro3d/model_browser.py`, `firepro3d/scene_io.py`, `firepro3d/underlay_context_menu.py`, `firepro3d/underlay_cache.py`, `firepro3d/calibrate_dialog.py`, `main.py`
> **Date:** 2026-04-13
> **Revision:** 7 (import-dialog UI cleanup: pill controls, merged Placement group, level-of-insertion selector, inline custom scale + "Calibrate", "Insert at origin" greys base point, hidden preview scrollbars; checkbox indicators styled globally in `firepro3d/theme.py`)
> **Last verified:** 2026-06-23 (commit `3e5b01a`) — §3.1 data model (`user_layer` removed), §3.4 underlay render pen width (cosmetic, fixed px)

---

## 1. Goal & Motivation

### 1.1 Goal

Define the end-to-end underlay lifecycle in FirePro3D: import, placement, persistence, reload, refresh, and management. Produce a single reference that describes both current behavior and target behavior, with a decomposed roadmap of follow-up tasks.

### 1.2 Why now

Underlays are the primary reference material for fire protection design — every project starts with an imported floor plan. The current implementation works but has gaps in usability (no way to manage locked underlays, no level-based filtering, silent failures on missing files) and maintainability (no spec, no tests). As the project grows toward paper-space and multi-level workflows, underlay management becomes a bottleneck. Speccing now prevents these gaps from compounding.

### 1.3 ScaleManager context

`ScaleManager` is a **fixed global constant**: 1 scene unit = 1 mm. It is not a calibratable value and is out of scope for this spec. The only calibration relevant to underlays is the per-import two-point pick in the import dialog, which computes a scale factor so the underlay's geometry maps correctly to mm-based scene coordinates.

---

## 2. Scope

### 2.1 In scope (this spec)

- The `Underlay` data model and new fields (`level`, `visible`, `hidden_layers`, `import_mode`, `import_scale`, `import_base_x/y`, `selected_layers`, `layout`, `import_bounds`).
- Import dialog: PDF DPI selection, PDF import mode toggle (vector/raster/auto).
- DWG import via ODA File Converter (DWG→DXF conversion, layout selection, viewport-based spatial filtering, paper layout entity transform).
- Underlay geometry caching (`underlay_cache.py`) for fast project reload.
- Placement: origin vs interactive click-to-place (existing, documented).
- Path storage: relative vs absolute strategy.
- File-not-found handling: warning, placeholder, relink.
- Per-level underlay visibility.
- Per-source-layer visibility for DXF underlays.
- Browser tree integration for underlay management.
- Transform origin fix (center of bounding rect).
- Refresh-from-disk behavior with new state preservation.
- Persistence and backward compatibility.
- Testing strategy.

### 2.2 Out of scope (future follow-ups)

| Feature | Reason for deferral |
|---|---|
| Batch multi-page PDF import | Low priority; one-page-at-a-time is adequate and each page needs independent placement |
| ~~Preserve source DXF colours~~ | Implemented — per-entity colour extracted (ACI/true_color/BYLAYER) but currently disabled in rendering; uniform gray used for MVP clarity |
| Undoable underlay operations | Performance concern (serializing large geometry groups on every undo capture); underlays change infrequently |
| ScaleManager cleanup | Stable, out of scope; not broken |
| Separate underlay manager panel | Browser tree integration covers management needs; revisit if it proves insufficient |
| ~~OSNAP in import dialogs~~ | **Implemented 2026-05-22.** Hybrid architecture: invisible individual items (transparent cosmetic pen) alongside batched QPainterPaths for rendering. Snap engine processes preview items identically to plan-view underlays. Supports endpoint, midpoint, center, quadrant, nearest, perpendicular, intersection. See `docs/superpowers/plans/2026-05-22-hybrid-snap-preview.md`. |

---

## 3. Underlay Data Model

### 3.1 Current fields (unchanged)

```python
@dataclass
class Underlay:
    type: Literal["pdf", "dxf", "dwg"]  # File type
    path: str                      # File path (see §4 for resolution rules)
    x: float = 0.0                # Scene position X
    y: float = 0.0                # Scene position Y
    scale: float = 1.0            # Display scale multiplier
    rotation: float = 0.0         # Rotation angle in degrees
    opacity: float = 1.0          # Opacity (0–1)
    locked: bool = False          # Lock state
    page: int = 0                 # PDF page index (0-based)
    dpi: int = 150                # PDF rasterization DPI
    colour: str = "#c0c0c0"       # DXF uniform colour as hex string (gray default)
    line_weight: float = 0.0      # DXF lineweight in mm (stored only; not used for rendering — see §3.4)
```

> The per-item layer system has been removed; the old `user_layer` field on `Underlay` no longer exists (stale `user_layer`/`user_layers` keys are silently ignored on load).

### 3.2 New fields

```python
    level: str = DEFAULT_LEVEL        # Level assignment ("*" = all levels)
    visible: bool = True              # User's explicit visibility toggle
    hidden_layers: list[str] = field(default_factory=list)  # Hidden source DXF layer names
    import_mode: str = "auto"         # PDF only: "auto" | "vector" | "raster"
    # Import transform params (Revision 3)
    import_scale: float = 1.0         # Scale applied during import (for reload)
    import_base_x: float = 0.0        # Base point X subtracted during import
    import_base_y: float = 0.0        # Base point Y subtracted during import
    selected_layers: list[str] | None = None  # DXF layers imported (None = all)
    # Layout support (Revision 4: DWG, Revision 5: DXF)
    layout: str = ""                   # Layout name (empty = Model space)
    # Area selection persistence (Revision 6)
    import_bounds: list[float] | None = None  # [min_x, min_y, max_x, max_y]
```

**Behavior:**

- `level` — defaults to the active level at import time. Special value `"*"` means visible on all levels.
- `visible` — user's explicit hide/show toggle, independent of level filtering. An underlay is visible in the scene only when both `visible == True` AND (level matches active level OR level is `"*"`).
- `hidden_layers` — source DXF layer names toggled off post-import. Empty for PDFs. Persisted and reapplied on refresh/reload.
- `import_mode` — only meaningful for PDFs. `"auto"` tries vectors first, falls back to raster. `"vector"` forces vector extraction. `"raster"` skips vectors and renders as pixmap. DXF always uses vector.
- `layout` — DXF and DWG. Name of the paper-space layout selected at import time. Empty string means Model space. Used for viewport-based spatial filtering and cache key differentiation. DXF files with multiple layouts now show a layout picker (Revision 5).
- `import_bounds` — bounding box of area-selected geometry in raw DXF coordinates (`[min_x, min_y, max_x, max_y]`). `None` means no area selection was applied (full import). When set, re-extraction from source (cache miss or refresh) applies `filter_geoms_by_bounds()` using this rectangle before building Qt items. Computed by `compute_geom_bounds()` in the import dialog when `_selected_indices` is set.

### 3.3 Serialization

`to_dict()` and `from_dict()` updated to include all new fields. `from_dict()` applies backward-compatible defaults for missing fields so old project files load without error:

| Field | Default if missing |
|---|---|
| `level` | `DEFAULT_LEVEL` |
| `visible` | `True` |
| `hidden_layers` | `[]` |
| `import_mode` | `"auto"` |
| `import_scale` | `1.0` |
| `import_base_x` | `0.0` |
| `import_base_y` | `0.0` |
| `selected_layers` | `None` |
| `layout` | `""` |
| `import_bounds` | `None` |

### 3.4 Rendering (pen width)

Underlay geometry is batched into one `QGraphicsPathItem` per DXF/PDF source layer (`_build_batched_underlay_group` in `model_space.py`). Stroked geometry uses a **cosmetic** pen whose width is a fixed device-pixel constant — `UNDERLAY_LINE_WIDTH_PX` (`constants.py`, currently `1.5`, matching the gridline on-screen width). Because the pen is cosmetic, underlay lines render at a constant on-screen thickness **independent of zoom level and `import_scale`**. The stored `Underlay.line_weight` (mm) is **not** consulted when rendering; all four build sites (interactive placement, DXF import, PDF vector import, reload-from-disk) pass the same fixed pixel width. Text is filled with the underlay colour and `NoPen`.

---

## 4. Path Resolution

### 4.1 Save-time logic

When serializing an `Underlay` to the project file:

1. Compute `os.path.relpath(underlay_path, project_dir)` where `project_dir` is the parent directory of the `.fpd` file.
2. If the result requires 3 or more parent traversals (i.e., starts with `../../../` or deeper), store the absolute path instead — deeply relative paths are fragile.
3. Otherwise store the relative path.

### 4.2 Load-time logic

When deserializing:

1. If the stored path is relative, resolve it against the project file's parent directory.
2. If the resolved path does not exist, try the stored path as absolute (handles: project file moved but underlay stayed).
3. If neither resolves, mark as missing (see §5).

### 4.3 Relink action

User picks a new file via file dialog → `Underlay.path` updated using the save-time rules (§4.1) → triggers refresh from disk.

The file dialog is constrained to the same file type as the original underlay (DXF→DXF, PDF→PDF). Relinking across types would break type-specific state (hidden_layers, colour, line_weight for DXF; page, dpi, import_mode for PDF). To change types, remove and re-import.

---

## 5. File-Not-Found Handling

When path resolution (§4.2) fails to find the underlay file:

### 5.1 Record preserved

The `Underlay` record stays in `self.underlays` with a placeholder scene item. All stored state (position, scale, rotation, level, hidden_layers, etc.) is retained so the user can relink without losing placement.

### 5.2 Placeholder item

A `QGraphicsRectItem` is created at the stored position (x, y):

- Dashed red border, semi-transparent red fill.
- `QGraphicsSimpleTextItem` child showing filename and "Missing — right-click to relink".
- Fixed size: 200 × 150 scene units (original bounds are unknown).
- Selectable but not movable (prevent accidental repositioning).

### 5.3 Warning on load

After all underlays are processed, a single aggregate `QMessageBox.warning` lists all missing files with their stored paths. One warning, not one per file.

### 5.4 Browser tree

Missing underlays appear in the browser tree with a warning icon. Right-click offers "Relink" as the first action.

### 5.5 Recovery paths

- **Relink:** User selects new file → path updated → refresh replaces placeholder with real content.
- **File reappears:** "Refresh from Disk" on the placeholder replaces it with real content without needing relink (e.g., network drive reconnects).

---

## 6. Transform Origin

### 6.1 Problem

Qt's default transform origin is the item's local (0,0) — the top-left corner of the group. Rotating or scaling swings the underlay around its corner, which is not the expected behavior.

### 6.2 Fix

Set transform origin to the center of the underlay's bounding rect:

```python
item.setTransformOriginPoint(item.boundingRect().center())
```

This is called in `_apply_underlay_display()` **before** `setScale()` and `setRotation()`. On refresh, the origin is recalculated after re-importing geometry (bounds may change if the source file was edited externally).

---

## 7. Per-Level Visibility

### 7.1 Level field

Each `Underlay` has a `level: str` field. Defaults to the active level at import time. `"*"` means visible on all levels.

### 7.2 Level-switch filtering

Underlays participate in the existing Z-range visibility system used by all other entities, rather than using a separate level-match check. This keeps the visibility model consistent and avoids the vestigial `display_mode` machinery.

Each underlay is assigned a Z-value derived from its level's elevation (set in `LevelManager.apply_to_scene()`). When the plan view's Z-range `[view_depth, view_height]` does not include the underlay's Z-value, it is hidden — same as walls, floors, and other entities.

**Special cases:**

- `level == "*"` (all levels): Always visible regardless of Z-range filtering.
- `data.visible == False`: Hidden regardless of level/Z-range (user's explicit override).

```python
for data, item in getattr(scene, "underlays", []):
    if item is None:
        continue
    try:
        item.isVisible()  # guard against deleted C++ objects
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

Both Z-range (or level match when no view range is set) AND the user's explicit `visible` toggle must pass for the underlay to be shown.

### 7.3 Import behavior

New underlays default to the currently active level. The import dialog provides a **Level** selector (top of the Placement group, §10.1) populated from the project levels and defaulting to the active level. The chosen level is carried on `ImportParams.level`; `open_import_dialog()` activates that level's plan view before committing so the `Underlay` record is tagged with it (`main.py`). Level can still be reassigned afterward via the browser tree (§7.4).

### 7.4 Level reassignment

Available via browser tree right-click → "Change Level" submenu, which lists all project levels plus "All Levels" (`"*"`).

---

## 8. Per-Source-Layer Visibility

### 8.1 Data flow

Each child item in a DXF underlay group has `data(1)` set to its source layer name (existing behavior). The group has `data(2)` set to the sorted list of all source layer names (existing behavior). `Underlay.hidden_layers` stores the names of layers toggled off.

### 8.2 Toggling a layer

1. User right-clicks a source layer node in the browser tree → "Hide" / "Show".
2. Walk the group's children: for each child where `child.data(1) == layer_name`, call `child.setVisible(show)`.
3. Update `data.hidden_layers` — add or remove the layer name.
4. Emit `underlaysChanged` signal so the browser tree updates (dimmed styling for hidden layers).

### 8.3 On duplicate

Duplicating an underlay (via context menu or browser tree) inherits the parent's `hidden_layers` list. The duplicate is a copy of the record, not a fresh import — if the user duplicated a structural plan with furniture hidden, the copy should also have furniture hidden.

### 8.4 On refresh from disk

After re-importing, re-apply hidden layers: walk children, hide those whose `data(1)` is in `data.hidden_layers`. If a layer name no longer exists in the refreshed file, silently drop it from `hidden_layers`. New layers in the refreshed file default to visible.

### 8.5 PDF underlays

Single raster item — no source layers. Browser tree shows the file node with a page child but no layer children. `hidden_layers` stays empty; layer toggling is not offered.

---

## 9. Browser Tree Integration

### 9.1 Location

Extend `ModelBrowser.refresh()` in `firepro3d/model_browser.py` with an "Underlays" category section, following the existing pattern (category root node → child items, `_ROLE_ENTITY` storing `id()` for selection sync).

### 9.2 Tree structure

```
📎 Underlays (3)
  ├── 📄 floor1.pdf            [Level 1]
  │     └── Page 1
  ├── 📄 structural.dxf        [Level 1]
  │     ├── 🔲 A-WALL          (12 items)
  │     ├── 🔲 A-DOOR          (8 items)
  │     └── 👁 A-FURN          (hidden, 23 items)
  ├── ⚠️ mechanical.dxf        [Level 2]  (missing)
  └── 📄 site-plan.pdf         [All Levels]
        └── Page 3
```

### 9.3 Node types and interactions

| Node | Left-click | Right-click menu |
|---|---|---|
| "Underlays" root | Expand/collapse | — |
| File node | Select underlay in scene (if unlocked), pan to it, populate property panel (always, even if locked) | Lock/Unlock, Hide/Show, Change Level, Scale, Rotate, Opacity, Relink, Refresh, Duplicate, Remove |
| Source layer node (DXF) | — | Hide/Show layer |
| Missing file node | — | Relink, Remove |

**Remove confirmation:** The "Remove" action shows a confirmation dialog ("Remove underlay '{filename}'? This cannot be undone.") since underlay removal is not undoable and re-importing requires effort.

### 9.4 Properties dialog

Accessed via file node right-click → "Properties". Shows: file path, type, level, position (x, y), scale, rotation, opacity, DPI (PDF only), import mode (PDF only), lock state. All fields editable. Changes applied immediately and synced to the `Underlay` record and scene item.

### 9.5 Scene ↔ tree sync

- Selecting an unlocked underlay in the scene highlights its file node in the tree.
- Selecting a file node in the tree selects the underlay in the scene (if unlocked) and pans the view to it.
- `underlaysChanged` signal triggers tree rebuild.

### 9.6 Selection behavior

Underlay groups are **not selectable or movable** in the scene — they are reference geometry that must not interfere with rubber-band selection or click-selection of design elements (walls, nodes, pipes, etc.). The browser tree is the primary management surface for all underlay operations — all actions are available via right-click regardless of lock state. Underlays remain snappable (the snap engine descends into underlay group children for endpoint, midpoint, and intersection detection).

---

## 10. Import Dialog

### 10.1 Dialog Layout (Revision 7)

`UnderlayImportDialog` (in `firepro3d/dxf_preview_dialog.py`) uses a two-panel layout:

- **Left panel:** Preview-only (QGraphicsView with pan/zoom, info label). Scrollbars are disabled (`ScrollBarAlwaysOff`) — panning is driven programmatically via the scrollbar values, so the bars are hidden without losing pan.
- **Right panel** (scrollable, 260-340px; horizontal scrollbar disabled): controls stacked vertically, top to bottom:
  - File group (path field, **Browse** / **Reload** pill buttons)
  - Layout combo (hidden until multi-layout file; see §10B)
  - Preview mode — three pills in one segmented row (Pan/Zoom, Select Area, Clear Selection)
  - **Placement** group (one bordered group, thin dividers between sub-rows; sits **above** Source Layers):
    - **Level** — target floor, defaults to the active level (§7.3)
    - **Scale** — compact preset combo (sized to its widest item) + an inline custom-factor field (shown only for "Custom…"; persists the last-used value via QSettings) + a **Calibrate** pill (two-point pick; DXF unit auto-detection in §10.4)
    - **Rotation** — angle field + inline −90° / +90° / 180° pills
    - **Base / Insertion Point** — X and Y fields side by side + an inline **Pick** pill
  - Source layer filtering (All/None pills + per-layer checkboxes)
  - PDF Options (DPI, import mode — hidden for DXF/DWG)
- **Bottom bar:** Status label, **Insert at origin** checkbox, Import/Cancel buttons. While "Insert at origin" is checked the base-point fields and Pick pill are greyed out (the base point is unused in that mode).
- **PDF thumbnail strip** above the splitter (visible only for multi-page PDFs).

**Visual conventions:** action buttons use a compact rounded "pill" style; the former separate Scale / Rotation / Base group boxes are merged into one **Placement** group. Checkbox indicators (the layer list and the "Insert at origin" box) are styled globally by `theme.build_app_qss()` — empty box unchecked, accent fill + white tick (`firepro3d/graphics/checkmark.svg`) checked — so they read clearly on the dark theme. Two-point scale-calibration markers render as a green diamond with a constant-size centre dot at the picked point.

### 10.2 PDF DPI dropdown

`QComboBox` with options: 72, 150, 300. Visible only when file type is PDF (the PDF Options group is hidden for DXF/DWG). Default: 150. Value written to `ImportParams.pdf_dpi`.

### 10.3 PDF import mode toggle

`QComboBox` with options: "Auto", "Vectors", "Raster". Visible only when file type is PDF. Default: "Auto". Value written to `ImportParams.import_mode`.

- **Auto:** Current behavior — try vector extraction, fall back to raster if no vectors found.
- **Vectors:** Force vector extraction. Show a warning if no vectors found.
- **Raster:** Skip vector extraction entirely. Render page as pixmap at selected DPI.

### 10.4 DXF unit auto-detection

Reads `$INSUNITS` from the DXF header. Maps known unit codes (1=inches, 2=feet, 4=mm, 5=cm, 6=meters) to scale factors. Missing or unitless (`0`) defaults to scale factor 1.0 (assumes inches). The pick-2-pts calibration serves as a fallback when auto-detection is wrong or absent.

### 10.5 DXF entity coverage

`DxfImportWorker._extract_geometry()` handles the following DXF entity types:

| DXF Entity | Output | Status |
|---|---|---|
| LINE | `line` → QGraphicsLineItem | Existing |
| CIRCLE | `circle` → QGraphicsEllipseItem | Existing |
| ARC | `arc` → QGraphicsPathItem | Existing |
| ELLIPSE | `ellipse_full` or `path_points` | Existing |
| LWPOLYLINE | `path_points` → QGraphicsPathItem | Existing |
| POLYLINE | `path_points` → QGraphicsPathItem | Existing |
| SPLINE | `path_points` (flattened) | Existing |
| TEXT | `text` → QGraphicsTextItem | Existing |
| MTEXT | `text` (plain_text extracted) | Existing |
| INSERT | Recurse via `entity.virtual_entities()` | Implemented |
| HATCH | Boundary paths via `virtual_entities()` | Implemented |
| DIMENSION | Explode to lines + text via `virtual_entities()` | Implemented |

**INSERT (block references)** is the highest-impact addition — architectural floor plans are primarily composed of blocks (doors, fixtures, symbols). Without INSERT support, large portions of the plan are missing from the underlay. `ezdxf`'s `virtual_entities()` explodes block references into constituent geometry with transforms applied, which can be fed recursively through `_extract_geometry()`. ATTRIB text on INSERT blocks is extracted separately (not included in `virtual_entities()` output). Exception handling is **per-entity**: the generator is materialized to a list first, then each sub-entity is wrapped in its own `try/except` so one bad entity cannot silently drop the rest of the block.

**POLYLINE vs LWPOLYLINE:** Both map to `path_points`. LWPOLYLINE uses `get_points()`, while POLYLINE (3D polyline, common in block explosions) uses `.vertices` to extract vertex locations. A `hasattr` check selects the correct accessor.

**HATCH** and **DIMENSION** use the same `virtual_entities()` pattern. LEADER, MULTILEADER, and MLEADER are also exploded. SOLID and POINT are extracted directly. All other entity types (3DFACE, etc.) are skipped.

### 10.6 Import flow

```
File selected
  → Worker thread parses geometry (DxfImportWorker / PdfImportWorker)
  → Preview rendered in dialog
  → User configures: level, layers, scale, rotation, base point, DPI, import mode
  → "Import →" pressed
  → ImportParams constructed (carries the chosen level)
  → open_import_dialog() activates the chosen level's plan view
  → Scene placement: origin or interactive click-to-place
  → Underlay record created (level = ImportParams.level — defaults to active; import_mode from params)
  → _apply_underlay_display() sets transform origin, scale, rotation, opacity, lock
  → Record + scene item appended to self.underlays
  → underlaysChanged emitted → browser tree refreshes
```

---

## 10B. Multi-Layout Import & DWG Support (Revision 4 + 5)

### 10B.1 Overview

Both DXF and DWG files can contain multiple paper-space layouts. When a file has 2+ layouts, a layout combo box appears in the import dialog's right panel. The user picks a layout before extraction begins (deferred extraction — no geometry loaded until a layout is selected). Single-layout files auto-extract immediately with the combo hidden.

DWG files are imported via ODA File Converter, a free external CLI tool that converts DWG to DXF. The converted DXF then follows the identical DXF layout selection flow. `_load_dwg()` is a thin wrapper: convert → `read_dxf()` → `_load_dxf()`.

### 10B.2 ODA File Converter

- **Discovery order:** QSettings (`dwg/oda_converter_path`) → system PATH → common install directories (`C:\Program Files\ODA\ODAFileConverter *\`)
- **Not installed:** Error dialog with download link + "Locate ODA…" button to browse for the executable. Path saved to QSettings for future use.
- **Conversion:** `ODAFileConverter <in_dir> <out_dir> ACAD2018 DXF 0 1`. Runs in temp input directory (source DWG copied in). GUI suppressed via `STARTF_USESHOWWINDOW`.
- **Output:** Converted DXF saved to `<project_dir>/UNDERLAY_REF/` for reuse. Skips re-conversion if existing DXF is newer than source DWG.
- **Module:** `firepro3d/dwg_converter.py`
- **Sanitization bypass:** Converted DXFs are read via `read_dxf()` and passed to `_load_dxf(_doc=doc)` to bypass `_sanitize_dxf()`, which can corrupt large ODA-produced files.

### 10B.3 Layout Selection

DXF and DWG files can contain multiple paper-space layouts (e.g., "Ground Floor", "Second Floor"). Layout names are enumerated via `list_layouts(doc=doc)` (metadata read, no extraction). When 2+ layouts exist, a combo box is shown in the right panel:

- **"Model"** — imports all model-space geometry (no spatial filter)
- **Paper layouts** — extracts viewport definitions from the layout, filters model-space geometry to entities within viewport bounds, and merges paper-layout entities (gridline bubbles, title block) transformed to model-space coordinates via the viewport's scale mapping

### 10B.4 Unified Import Flow (DXF and DWG)

1. DWG only: ODA converts DWG → DXF (or uses cached DXF from UNDERLAY_REF/)
2. DXF read once via `ezdxf.readfile()` (or `_sanitize_dxf()` + `readfile()` for plain DXF), doc stored as `self._doc`
3. `list_layouts(doc)` enumerates layouts; combo shown if 2+ layouts, deferred extraction
4. User picks layout (or auto-select for single-layout files)
5. `_extract_for_layout(layout_name)` runs the unified extraction pipeline:
   a. Viewport bounds computed from selected layout's VIEWPORT entities (paper layouts only)
   b. Geometry extraction with entity-level pre-filter (LINE/CIRCLE/ARC/etc. filtered by viewport bounds; INSERT/HATCH/DIMENSION always pass)
   c. Post-extraction viewport filter via `filter_geoms_by_bounds()` (catches INSERT sub-entities outside viewport)
   d. Paper layout entities transformed to model-space and merged (text size scaled by `ps_to_ms`, alignment preserved)
   e. DWG only, first extraction: entity type dialog shown (geometry counts by kind; user can deselect types)
6. Layers populated from combined geometry, preview rebuilt

### 10B.5 Paper-Space Entity Transform

`extract_layout_entities()` transforms paper-space annotations to model-space coordinates using the viewport's scale mapping (`ps_to_ms = view_height / paper_height`):

- **Position:** `model_x = (paper_x - vp_paper_cx) * ps_to_ms + vp_model_cx`
- **Text size:** `model_size = paper_size * ps_to_ms`
- **Circle/arc size:** Radius and bounding box dimensions scaled by `ps_to_ms`
- **Multiline MTEXT:** `plain_text()` preserves `\n` line breaks; renderer splits and renders each line at correct vertical offset
- **Text alignment:** MTEXT `attachment_point` (1-9) mapped to `halign`/`valign`; renderer uses `QFontMetricsF` to compute baseline-left offsets for center/right/middle alignments

### 10B.6 Underlay Record

DWG underlays are stored with `type="dwg"`, DXF with `type="dxf"`. Both preserve the layout name. The `layout` field is included in the cache key so multiple layouts from the same file get independent cache entries. Empty layout string means Model space.

### 10B.7 Refresh & Reload

- **Cache hit:** Geometry loaded from `.fpd.cache/` (fast)
- **Cache miss (DWG):** ODA re-converts DWG → DXF, geometry re-extracted
- **Cache miss (DXF):** Geometry re-extracted from source file
- **Layout:** Saved layout name used silently for re-extraction; falls back to Model if layout no longer exists. **Important:** re-extraction must replicate the viewport-filtering pipeline from `_extract_for_layout()` — not just read modelspace. This means: compute viewport bounds via `get_viewport_bounds()`, pre-filter entities, post-filter geometry via `filter_geoms_by_bounds()`, and merge paper layout entities via `extract_layout_entities()`. All three re-extraction paths (`DxfImportWorker.run()`, `extract_file_sync()`, and the `scene_io.py` reload call to `import_dxf()`) must accept and use the layout parameter.
- **`import_bounds` on re-extraction:** When a cache miss triggers sync re-extraction and `record.import_bounds` is set, the re-extracted geometry is filtered through `filter_geoms_by_bounds()` using the saved bounds before building Qt items and writing the cache. This reproduces the area selection the user made at import time.
- **`_ensure_underlay_caches` (save-time):** Reads raw geometry from each underlay group's `data(5)` (the pre-transform geometry list stored at import time) and writes it to the cache. This approach avoids re-extracting from the source file on save, which previously caused UI freezes with large DXF files. The `data(5)` value is authoritative — it already reflects area-selection filtering — so the cache write is unconditional (no freshness check). DWG underlays no longer trigger ODA conversion at save time.

---

## 11. Refresh From Disk

### 11.1 Trigger

Context menu → "Refresh from Disk", or browser tree right-click → "Refresh".

### 11.2 Process

1. Sync current transform state from scene item back to `Underlay` record (position, scale, rotation, opacity).
2. Remove old scene item.
3. Re-import the file using `data.import_mode` (PDF) or standard vector import (DXF/DWG). DXF and DWG re-import passes `layout=data.layout` to `import_dxf` so layout-aware extraction is preserved.
4. If file is missing → replace with placeholder (§5), warn user. Stop.
5. Recalculate transform origin: `setTransformOriginPoint(boundingRect().center())`.
6. Apply display settings via `_apply_underlay_display()`.
7. Re-apply hidden layers (§8.3): walk children, hide those in `data.hidden_layers`, drop stale names.
8. Update scene item reference in `self.underlays`.

### 11.3 Preserved state

Position, scale, rotation, opacity, lock, level, visible, user_layer, hidden_layers, import_mode — all preserved from the record.

---

## 12. Persistence

### 12.1 Save

In `scene_io.py`, before serializing:

1. For each `(data, item)` in `self.underlays`, sync current transform from item to record (existing behavior).
2. Convert `data.path` to relative path per §4.1 rules.
3. Call `data.to_dict()` — includes all fields.
4. Include in project JSON under `"underlays"` key.

### 12.2 Load

In `scene_io.py`, when deserializing:

1. For each entry in `payload["underlays"]`, call `Underlay.from_dict(entry)` with backward-compatible defaults (§3.3).
2. Resolve path per §4.2 rules.
3. Attempt re-import:
   - **DXF:** `import_dxf()` with stored colour, lineweight, user_layer, **and layout**. The worker must use layout-aware extraction (viewport filtering + paper annotations) when a non-empty layout is saved.
   - **PDF:** `import_pdf()` with stored DPI, page, using `import_mode` to select vector/raster path.
   - **Missing file:** Create placeholder (§5).
4. Apply hidden_layers to successfully loaded DXF underlays.
5. Apply level filtering based on active level.
6. After all underlays processed, show aggregate missing-file warning if any.

### 12.3 Backward compatibility

Old project files lack the new fields. `from_dict()` applies defaults (§3.3). No migration step needed — the defaults produce identical behavior to pre-spec versions.

---

## 13. Acceptance Criteria

### 13.1 Must-have (MVP)

1. Import dialog handles DXF and PDF with source-layer filtering, scale selection (preset combo, "Calibrate" two-point pick, DXF unit auto-detect), rotation, base-point pick, and a level-of-insertion selector (defaults to the active level).
2. PDF: page selection via thumbnails, DPI dropdown (72/150/300), vector/raster/auto toggle.
3. Placement: origin or interactive click-to-place.
4. `Underlay` record stores all transform state plus `level`, `visible`, `hidden_layers`, `import_mode` fields.
5. Path storage: relative to project file when possible, absolute fallback (§4.1 rules).
6. Transform origin: center of bounding rect for rotation/scale.
7. Persistence: save/load with project file, re-read linked file from disk on load.
8. File-not-found: warning on load, preserve record, placeholder in scene, relink action.
9. Refresh from disk: re-import preserving position/scale/rotation/opacity/lock/hidden_layers/import_mode.
10. Per-level visibility: underlay assigned to a level (chosen in the import dialog, default active), auto-hides on level switch, "all levels" option.
11. Per-source-layer visibility: toggle in browser tree, persisted across save/load/refresh.
12. Browser tree: File → source layers hierarchy, right-click for all management actions.
13. Underlays are never selectable/movable in the scene (reference geometry); fully manageable via browser tree. Lock additionally prevents browser-initiated transforms.
14. DXF entity coverage: INSERT (block references), HATCH, and DIMENSION entities imported via `virtual_entities()` explosion.

### 13.2 Out of scope (future follow-ups)

See §2.2.

---

## 14. Testing Strategy

### 14.1 Unit tests (`tests/test_underlay.py`)

| Test | What it verifies |
|---|---|
| Path resolution: inside project dir | `relpath` computed correctly, round-trips through save/load |
| Path resolution: outside project dir | Absolute path stored, resolves on load |
| Path resolution: deep `..` guard | Paths with >2 levels of `..` fall back to absolute |
| Serialization round-trip | `to_dict()` → `from_dict()` preserves all fields including new ones |
| Backward compat | `from_dict()` with dict missing new fields applies correct defaults |
| Field defaults | All 4 new fields have correct defaults |
| Hidden layers list isolation | `field(default_factory=list)` prevents sharing between instances |

**Note:** Hidden-layers apply/stale/new-layer tests and level-filtering tests require Qt scene infrastructure. These are better suited for integration tests (§14.2) and were deferred to that scope.

### 14.2 Integration tests (`tests/test_underlay_integration.py`)

| Test | What it verifies |
|---|---|
| File-not-found | Save with underlay, delete file, reload → record preserved, placeholder created, warning triggered |
| Refresh from disk | Modify source DXF (add layer), refresh → new layer visible, existing hidden layers stay hidden |
| Import mode persistence | Import PDF as raster, save, reload → re-imported as raster not vector |

### 14.3 Not tested (out of scope)

- Browser tree UI interactions (requires full Qt event loop, low ROI for unit tests).
- Import dialog UI changes (thin UI additions, better tested manually).
- Context menu actions (thin wrappers over tested logic).

---

## 15. Follow-Up Tasks

Tasks to add to `TODO.md` after this spec is approved:

| Priority | Task | Ref |
|---|---|---|
| P1 | Implement `Underlay` data model changes (new fields, serialization, backward compat) | §3 |
| P1 | Implement path resolution (relative/absolute save/load) | §4 |
| P1 | Implement file-not-found handling (placeholder, warning, relink) | §5 |
| P1 | Fix transform origin to bounding rect center | §6 |
| P1 | Implement per-level underlay visibility | §7 |
| P1 | Implement per-source-layer visibility | §8 |
| P1 | Add underlay section to browser tree with context menus | §9 |
| ~~done~~ | ~~Add PDF DPI dropdown to import dialog~~ — implemented | §10.2 |
| ~~done~~ | ~~Add PDF import mode toggle to import dialog~~ — implemented | §10.3 |
| P2 | Update refresh-from-disk to preserve new state | §11 |
| P2 | Write unit tests for underlay path resolution and serialization | §14.1 |
| P2 | Write integration tests for file-not-found and refresh | §14.2 |
| P3 | Batch multi-page PDF import | §2.2 |
| P3 | Preserve source DXF colours option | §2.2 |
| P3 | Undoable underlay operations | §2.2 |
