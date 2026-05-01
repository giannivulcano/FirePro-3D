# Underlay Workflow — Specification

> **Status:** North-star design + decomposed follow-ups (spec-only — no code changes delivered by this document)
> **Source files:** `firepro3d/underlay.py`, `firepro3d/dxf_preview_dialog.py`, `firepro3d/dxf_import_worker.py`, `firepro3d/pdf_import_worker.py`, `firepro3d/model_space.py`, `firepro3d/model_browser.py`, `firepro3d/scene_io.py`, `firepro3d/underlay_context_menu.py`, `firepro3d/calibrate_dialog.py`, `main.py`
> **Date:** 2026-04-13
> **Revision:** 3 (post-implementation review — spec updated to match delivered code)

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

- The `Underlay` data model and new fields (`level`, `visible`, `hidden_layers`, `import_mode`).
- Import dialog: PDF DPI selection, PDF import mode toggle (vector/raster/auto).
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
| Preserve source DXF colours | Adds complexity (colour mapping, dark-on-dark issues); uniform colour from user layer is cleaner for MVP |
| Undoable underlay operations | Performance concern (serializing large geometry groups on every undo capture); underlays change infrequently |
| ScaleManager cleanup | Stable, out of scope; not broken |
| Separate underlay manager panel | Browser tree integration covers management needs; revisit if it proves insufficient |
| OSNAP in import dialogs | Tracked separately in snap engine roadmap |

---

## 3. Underlay Data Model

### 3.1 Current fields (unchanged)

```python
@dataclass
class Underlay:
    type: Literal["pdf", "dxf"]   # File type
    path: str                      # File path (see §4 for resolution rules)
    x: float = 0.0                # Scene position X
    y: float = 0.0                # Scene position Y
    scale: float = 1.0            # Display scale multiplier
    rotation: float = 0.0         # Rotation angle in degrees
    opacity: float = 1.0          # Opacity (0–1)
    locked: bool = False          # Lock state
    page: int = 0                 # PDF page index (0-based)
    dpi: int = 150                # PDF rasterization DPI
    colour: str = "#ffffff"       # DXF colour as hex string
    line_weight: float = 0.0      # DXF lineweight in mm
    user_layer: str = DEFAULT_USER_LAYER  # Destination layer
```

### 3.2 New fields

```python
    level: str = DEFAULT_LEVEL        # Level assignment ("*" = all levels)
    visible: bool = True              # User's explicit visibility toggle
    hidden_layers: list[str] = field(default_factory=list)  # Hidden source DXF layer names
    import_mode: str = "auto"         # PDF only: "auto" | "vector" | "raster"
```

**Behavior:**

- `level` — defaults to the active level at import time. Special value `"*"` means visible on all levels.
- `visible` — user's explicit hide/show toggle, independent of level filtering. An underlay is visible in the scene only when both `visible == True` AND (level matches active level OR level is `"*"`).
- `hidden_layers` — source DXF layer names toggled off post-import. Empty for PDFs. Persisted and reapplied on refresh/reload.
- `import_mode` — only meaningful for PDFs. `"auto"` tries vectors first, falls back to raster. `"vector"` forces vector extraction. `"raster"` skips vectors and renders as pixmap. DXF always uses vector.

### 3.3 Serialization

`to_dict()` and `from_dict()` updated to include all new fields. `from_dict()` applies backward-compatible defaults for missing fields so old project files load without error:

| Field | Default if missing |
|---|---|
| `level` | `DEFAULT_LEVEL` |
| `visible` | `True` |
| `hidden_layers` | `[]` |
| `import_mode` | `"auto"` |

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

New underlays default to the currently active level. The import dialog does not need a level picker — the user imports while viewing the relevant level, then reassigns via the browser tree if needed.

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

### 10.1 Existing behavior (unchanged, documented for reference)

`UnderlayImportDialog` (in `firepro3d/dxf_preview_dialog.py`, 1249 LOC) provides:

- File browse / drag-drop for DXF and PDF.
- Preview scene with pan/zoom.
- Source layer filtering via checkboxes (DXF).
- Scale selection: preset dropdown (1:1 through 1:1000, Custom), pick-2-pts calibration, DXF unit auto-detection from `$INSUNITS`.
- Base point pick.
- Destination layer selection.
- PDF page selection via thumbnail strip.
- Rubber-band spatial subset selection.
- Insert-at-origin checkbox vs interactive placement.

### 10.2 New: PDF DPI dropdown (P2 — not yet implemented)

`QComboBox` with options: 72, 150, 300. Visible only when file type is PDF. Default: 150. Value written to `ImportParams.pdf_dpi` (field already exists).

### 10.3 New: PDF import mode toggle (P2 — not yet implemented)

`QComboBox` with options: "Auto", "Vectors", "Raster". Visible only when file type is PDF. Default: "Auto". Value written to a new `ImportParams.import_mode` field.

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

**INSERT (block references)** is the highest-impact addition — architectural floor plans are primarily composed of blocks (doors, fixtures, symbols). Without INSERT support, large portions of the plan are missing from the underlay. `ezdxf`'s `virtual_entities()` explodes block references into constituent geometry with transforms applied, which can be fed recursively through `_extract_geometry()`.

**HATCH** and **DIMENSION** use the same `virtual_entities()` pattern. All other entity types (SOLID, POINT, LEADER, 3DFACE) are deferred — uncommon in plan views and low impact.

### 10.6 Import flow

```
File selected
  → Worker thread parses geometry (DxfImportWorker / PdfImportWorker)
  → Preview rendered in dialog
  → User configures: layers, scale, base point, destination layer, DPI, import mode
  → "Import →" pressed
  → ImportParams constructed
  → Scene placement: origin or interactive click-to-place
  → Underlay record created (level = active level, import_mode from params)
  → _apply_underlay_display() sets transform origin, scale, rotation, opacity, lock
  → Record + scene item appended to self.underlays
  → underlaysChanged emitted → browser tree refreshes
```

---

## 11. Refresh From Disk

### 11.1 Trigger

Context menu → "Refresh from Disk", or browser tree right-click → "Refresh".

### 11.2 Process

1. Sync current transform state from scene item back to `Underlay` record (position, scale, rotation, opacity).
2. Remove old scene item.
3. Re-import the file using `data.import_mode` (PDF) or standard vector import (DXF).
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
   - **DXF:** `import_dxf()` with stored colour, lineweight, user_layer.
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

1. Import dialog handles DXF and PDF with existing layer filtering, scale selection (preset, pick-2-pts, auto-detect), base point pick, and destination layer.
2. PDF: page selection via thumbnails, DPI dropdown (72/150/300), vector/raster/auto toggle.
3. Placement: origin or interactive click-to-place.
4. `Underlay` record stores all transform state plus `level`, `visible`, `hidden_layers`, `import_mode` fields.
5. Path storage: relative to project file when possible, absolute fallback (§4.1 rules).
6. Transform origin: center of bounding rect for rotation/scale.
7. Persistence: save/load with project file, re-read linked file from disk on load.
8. File-not-found: warning on load, preserve record, placeholder in scene, relink action.
9. Refresh from disk: re-import preserving position/scale/rotation/opacity/lock/hidden_layers/import_mode.
10. Per-level visibility: underlay assigned to a level, auto-hides on level switch, "all levels" option.
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
| P2 | Add PDF DPI dropdown to import dialog | §10.2 |
| P2 | Add PDF import mode toggle to import dialog | §10.3 |
| P2 | Update refresh-from-disk to preserve new state | §11 |
| P2 | Write unit tests for underlay path resolution and serialization | §14.1 |
| P2 | Write integration tests for file-not-found and refresh | §14.2 |
| P3 | Batch multi-page PDF import | §2.2 |
| P3 | Preserve source DXF colours option | §2.2 |
| P3 | Undoable underlay operations | §2.2 |
