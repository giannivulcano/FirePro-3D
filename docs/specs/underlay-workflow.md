---
status: current            # §1–§15 verified 2026-06-23; §16 Underlay Manager 2026-08-29; §17 PDF-import-polish 2026-08-28; §18 freeze-blit 2026-08-30; §10 Import-dialog Rev-8 first-principles redesign 2026-09-01 (feat/import-dialog-redesign); §10.7 Modify round-trip + 3-way insertion + frameless shell 2026-09-01 (feat/underlay-manager-chrome-match)
last-verified: 2026-09-01  # §10 Rev-8 shell + §10.7 Modify lossless round-trip / 3-way insertion-position / page-switch preservation / origin-pivot fix; import dialog module renamed to underlay_import_dialog.py
verified-commit: cfcb6d6
applies-to:
  - firepro3d/preferences_dialog.py    # §17.1 ImportPane PDF DPI/mode defaults
  - firepro3d/underlay.py
  - firepro3d/model_space.py          # §16.3 pens, repen_underlay
  - firepro3d/level_manager.py        # §7.2 per-level visibility clause
  - firepro3d/level_widget.py         # §16.7 rename remap
  - firepro3d/paper_display.py        # §16.5 paper override stage
  - firepro3d/paper_space.py          # §16.5 source_view_key plumbing
  - firepro3d/display_manager.py      # Underlays tab REMOVED (§16.6)
  - firepro3d/underlay_manager.py     # §16.6 Underlay Manager (new)
  - firepro3d/underlay_manager_model.py
  - firepro3d/underlay_manager_delegates.py
  - firepro3d/underlay_manager_theme.py
  - firepro3d/underlay_snap_index.py  # §16.8 per-underlay snap
  - firepro3d/snap_engine.py
  - firepro3d/underlay_import_dialog.py   # §10 import dialog (renamed 2026-09-01); §10.7 Modify flow
  - firepro3d/frameless_shell.py          # §10.1 FramelessShellMixin — shared frameless house chrome
  - firepro3d/dxf_import_worker.py
  - firepro3d/pdf_import_worker.py
  - firepro3d/dwg_converter.py
  - firepro3d/underlay_cache.py
  - firepro3d/underlay_freeze.py            # §18 freeze-blit
  - firepro3d/model_view.py                 # §18 gesture sources
  - firepro3d/underlay_context_menu.py
  - firepro3d/calibrate_dialog.py
source-tasks:
  - "Underlay display management & view assignment [P1]"
  - "Underlay Manager [P1]"
---

# Underlay Workflow — Specification

> **Status:** §1–§15 describe current behavior (verified 2026-06-23). **§16 is current** (Underlay Manager shipped on `feat/underlay-manager`, 2026-08-29 @ `56c8148`). §17 PDF Import Polish shipped 2026-08-28. Sections tagged "(as-built)" reflect shipped code.
> **Source files:** `firepro3d/underlay.py`, `firepro3d/underlay_import_dialog.py`, `firepro3d/frameless_shell.py`, `firepro3d/underlay_manager.py`, `firepro3d/dxf_import_worker.py`, `firepro3d/dwg_converter.py`, `firepro3d/pdf_import_worker.py`, `firepro3d/model_space.py`, `firepro3d/model_browser.py`, `firepro3d/scene_io.py`, `firepro3d/underlay_context_menu.py`, `firepro3d/underlay_cache.py`, `firepro3d/calibrate_dialog.py`, `main.py`
> **Date:** 2026-04-13
> **Revision:** 8 (adds §16 — display management & view assignment design: per-layer colour/weight, per-view visibility, Display Manager Underlays tab)
> **Revision 7:** import-dialog UI cleanup: pill controls, merged Placement group, level-of-insertion selector, inline custom scale + "Calibrate", "Insert at origin" greys base point, hidden preview scrollbars; checkbox indicators styled globally in `firepro3d/theme.py`
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

- The `Underlay` data model and new fields (`levels`, `snap`, `visible`, `hidden_layers`, `import_mode`, `import_scale`, `import_base_x/y`, `selected_layers`, `layout`, `import_bounds`).
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
| ~~Preserve source DXF colours~~ | Implemented — per-entity colour extracted (ACI/true_color/BYLAYER) but currently disabled in rendering; uniform gray used for MVP clarity. **Re-deferred in the 2026-08-09 §16 design (D5):** per-layer overrides land instead; source-colour rendering needs (layer, colour) re-batching and remains a follow-up. |
| Undoable underlay operations | Performance concern (serializing large geometry groups on every undo capture); underlays change infrequently |
| ScaleManager cleanup | Stable, out of scope; not broken |
| ~~Separate underlay manager panel~~ | **Shipped 2026-08-29** — the Underlay Manager (§16.6) is the single management home; the Display Manager Underlays tab was removed. |
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
    levels: list[str] = field(default_factory=lambda: [DEFAULT_LEVEL])
                                      # Level assignment. ["*"] = all levels.
                                      # Empty list → hidden regardless of active level.
    snap: bool = True                 # Per-underlay OSNAP enable. False → UnderlaySnapIndex
                                      # returns nothing for this record. General SNAP/F3
                                      # remains the master gate.
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

> **Removed field:** `hidden_in_views: list[str]` — per-view underlay exclusion is removed from the record. Per-view visibility is a property of the VIEW, to be re-homed onto PlanView/DetailView/SheetViewport as a future drafting-overrides/view-templates feature (cross-ref `view-relationships.md §7.4`). Interim: an underlay shows in every view of its assigned levels (paper viewports included). Any old `.fpd` files containing `hidden_in_views` silently ignore the key on load.

**Behavior:**

- `levels` — list of level names the underlay is assigned to. Defaults to `[active_level]` at import time. Special value `["*"]` means visible on all levels. Empty list → always hidden. Level assignment is managed exclusively from the Underlay Manager (§16.6) Levels column; the import dialog's Level combo is removed.
- `snap` — per-underlay OSNAP enable. `False` → `UnderlaySnapIndex.query()` returns nothing for this record; replaces the old global `Model_Space._snap_to_underlay` toggle (removed). The general SNAP / F3 master gate still applies when `snap` is `True`.
- `visible` — user's explicit hide/show toggle, independent of level filtering. An underlay is visible in the scene only when `visible == True` AND the per-level check (§7.2) passes.
- `hidden_layers` — source DXF layer names toggled off post-import. Empty for PDFs. Persisted and reapplied on refresh/reload. Edited from the Underlay Manager's expandable layer rows (§16.6).
- `import_mode` — only meaningful for PDFs. `"auto"` tries vectors first, falls back to raster. `"vector"` forces vector extraction. `"raster"` skips vectors and renders as pixmap. DXF always uses vector.
- `layout` — DXF and DWG. Name of the paper-space layout selected at import time. Empty string means Model space. Used for viewport-based spatial filtering and cache key differentiation. DXF files with multiple layouts now show a layout picker (Revision 5).
- `import_bounds` — bounding box of area-selected geometry in raw DXF coordinates (`[min_x, min_y, max_x, max_y]`). `None` means no area selection was applied (full import). When set, re-extraction from source (cache miss or refresh) applies `filter_geoms_by_bounds()` using this rectangle before building Qt items. Computed by `compute_geom_bounds()` in the import dialog when `_selected_indices` is set.

### 3.3 Serialization

`to_dict()` emits `levels` (list) and `snap` (bool). `from_dict()` applies backward-compatible defaults for missing fields so old project files load without error:

| Field | Default if missing | Migration note |
|---|---|---|
| `levels` | `[DEFAULT_LEVEL]` | Old `{"level": "F1"}` migrates to `["F1"]`; `{"level": "*"}` → `["*"]` |
| `snap` | `True` | — |
| `visible` | `True` | — |
| `hidden_layers` | `[]` | — |
| `import_mode` | `"auto"` | — |
| `import_scale` | `1.0` | — |
| `import_base_x` | `0.0` | — |
| `import_base_y` | `0.0` | — |
| `selected_layers` | `None` | — |
| `layout` | `""` | — |
| `import_bounds` | `None` | — |

`hidden_in_views` is **not** emitted by `to_dict()` and is silently ignored by `from_dict()` (stale key from pre-56c8148 files). The old `level: str` key is also dropped from `to_dict()` output; `from_dict()` reads `levels` first and, if absent, falls back to the legacy `level` string to produce a single-element list.

### 3.4 Rendering (pen width)

Underlay geometry is batched into one `QGraphicsPathItem` per DXF/PDF source layer (`_build_batched_underlay_group` in `model_space.py`). Stroked geometry uses a **cosmetic** pen whose width is a fixed device-pixel constant — `UNDERLAY_LINE_WIDTH_PX` (`constants.py`, currently `1.5`, matching the gridline on-screen width). Because the pen is cosmetic, underlay lines render at a constant on-screen thickness **independent of zoom level and `import_scale`**. The stored `Underlay.line_weight` (mm) is **not** consulted when rendering; all four build sites (interactive placement, DXF import, PDF vector import, reload-from-disk) pass the same fixed pixel width. Text is filled with the underlay colour and `NoPen`.

> **Forward note:** the §16 design (proposal) supersedes the uniform-pen rule with per-layer colour/weight overrides while preserving this section's cosmetic-on-screen invariant (screen pens stay cosmetic; true mm weights apply only in paper output). §3.4 remains the as-built contract until §16 ships.

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

Missing underlays appear in the browser tree with a warning icon. Right-click offers "Relink" as the first action. Browser underlay nodes are **navigation-only** (§9.3) — level readout shows the `levels` list or "All Levels"; no Change-Level, Relink, or layer-visibility editing is offered from the browser. Full management is via the Underlay Manager (§16.6).

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

Each `Underlay` has a `levels: list[str]` field (§3.2). Defaults to `[active_level]` at import time. `["*"]` means visible on all levels. Empty list → always hidden.

### 7.2 Level-switch filtering

`LevelManager.apply_to_scene()` drives underlay visibility. The rule (AND-composed, in order):

1. `data.visible == False` → hide; stop.
2. `"*" in data.levels` → show; stop.
3. `data.levels` is empty → hide; stop.
4. If a view range `[view_depth, view_height]` is active: show if **any** assigned level's elevation falls within the range.
5. Otherwise (no view range): show if the active level name is in `data.levels`.

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
    if "*" in data.levels:
        item.setVisible(True)
        continue
    if not data.levels:
        item.setVisible(False)
        continue
    if has_view_range:
        visible = any(
            view_depth <= lvl_map[l].elevation <= view_height
            for l in data.levels if l in lvl_map
        )
        item.setVisible(visible)
    else:
        item.setVisible(active in data.levels)
```

> **Removed clause:** the old `active_view_key in data.hidden_in_views` check (§16.4 design, now retired) no longer exists in this pass; `hidden_in_views` is removed from the record entirely (§3.2).

### 7.3 Import behavior

New underlays default to `[active_level]`; `Model_Space.add_underlay` sets `record.levels` to the active level at insertion time. The import dialog's **Level** combo is removed — all level assignment happens post-import in the Underlay Manager (§16.6) Levels column. `params.scale` bakes into geometry via `import_scale`; the display `scale` field is preserved.

### 7.4 Level reassignment

Exclusively via the **Underlay Manager** (§16.6) Levels column: each chip in the column represents an assigned level; clicking the column opens a picker showing all project levels plus "All Levels" (`"*"`). Multi-level assignment is supported (any number of levels, or `["*"]`). The old browser tree "Change Level" submenu is removed.

**Level rename:** `LevelWidget._remap_underlay_views` walks `scene.underlays` on rename and rewrites any occurrence of the old name in `record.levels` to the new name. Empty-after-remap lists are left as-is (underlay becomes hidden until reassigned).

---

## 8. Per-Source-Layer Visibility

> Per-layer editing surface is the **Underlay Manager** expandable child rows (§16.6), not the Display Manager tab (removed). Per-layer colour/weight overrides (`layer_overrides`) are also managed from there.

### 8.1 Data flow

Each child item in a DXF underlay group has `data(1)` set to its source layer name (existing behavior). The group has `data(2)` set to the sorted list of all source layer names (existing behavior). `Underlay.hidden_layers` stores the names of layers toggled off.

### 8.2 Toggling a layer

1. User edits the layer visibility checkbox in the Underlay Manager's layer child row.
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

Browser underlay nodes are **navigation-only**. Level readout shows the `levels` list / "All Levels". No Change-Level, Relink, or layer-visibility editing is offered from the browser — use the Underlay Manager (§16.6) for all management.

| Node | Left-click | Right-click menu |
|---|---|---|
| "Underlays" root | Expand/collapse | — |
| File node | Select underlay in scene (if unlocked), pan to it, populate property panel (always, even if locked) | Lock/Unlock, Hide/Show, Scale, Rotate, Refresh, Duplicate, Remove |
| Source layer node (DXF) | — | (navigation display only; no layer toggle) |
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

### 10.1 Dialog Layout (Revision 8 — first-principles redesign, 2026-09-01)

`UnderlayImportDialog` (`firepro3d/underlay_import_dialog.py`) is a **frameless**
`QDialog` sharing the Underlay-Manager QSS scope (single-homed in `theme.py`) and
the frameless house chrome via `FramelessShellMixin` (`frameless_shell.py`, the
same mixin the Underlay Manager inherits — see §16.6 and
`architecture/theming.md`). Laid out as **header · [step rail | preview |
contextual panel] · commit footer**. House chrome follows
`architecture/theming.md` (Arial UI / Consolas values + the type roles;
switch-vs-checkbox; frameless windows; scrollbars-off; divider-widget seams).
Opens **maximized**.

- **Header** (single `shellHeader`, styled like the footer): layers glyph
  (`underlay_import_icon.svg`, solid-accent top layer) + "Import Underlay —
  {project}" (`role="title"`) + active file / "(no file loaded)" + the standard
  frameless min/max/close controls. Drag-to-move and double-click-to-maximize,
  plus resize edges and **Win11 DWM rounded corners**, all come from
  `FramelessShellMixin` (shared with the Underlay Manager, §16.6) — the dialog
  does not hand-roll them.
- **Step rail** (`_StepRail` of `_StepRow`): Source / Content / Placement — number
  chip + name + status; active row = green rounded highlight + left accent bar.
  Clicking a row switches the contextual panel; loading a source auto-advances to
  Content.
- **Preview** (central, top/bottom split): the PDF **filmstrip** on top (side
  arrows, no scrollbar) for multi-page PDFs; the preview workspace below (pan /
  cursor-anchored zoom clamped 25–1200% / crop / calibrate). Empty state = a
  centred glyph + "Drop a PDF, DWG or DXF here". Crop draws a dashed-accent
  rectangle with an **outside-dim scrim**. Base marker + pick cursor use `warn`.
- **Contextual panel** (`QStackedWidget`, one page per step; **flat overline
  sections** — only lists + inputs bordered):
  - **Source:** file field + Browse/Reload + Recent (`underlay_mru.RecentSources`).
  - **Content:** Region (Draw crop / Clear) **above** Source layers (All/None +
    auto-expanding list), then PDF Options (DPI, import mode — hidden for DXF/DWG).
  - **Placement:** **Levels** multi-select (auto-fits all levels), Scale (preset
    combo + custom factor + verified/unverified pill + Calibrate / Looks-right),
    Rotation, Base point (X/Y + Pick — stay enabled in both position modes),
    Position (**toggle switch** "Insert at origin").
- **Footer:** commit-sentence (rich text via one `update_all()`), Cancel, and a
  solid-accent **Import →** (white text).

**Levels re-added (reverses the Rev-7 removal):** the Placement panel carries a
plain multi-select defaulting to `[active_level]`; `ImportParams.levels` flows
into the new record (`_record_levels` in `model_space.py`) and into
`replace_underlay` on Modify (§10.7). The Underlay Manager (§16.6) remains a
second home for post-import level reassignment.

**Scale verification:** `Underlay.scale_verified` (bool, persisted via
`to_dict`/`from_dict`, default False) — Calibrate (two-point pick) **or** "Looks
right" sets it True; changing the scale factor resets it False; Modify keeps a
verified scale verified. The commit sentence, rail state, and pill colour
warn/ok on this state. Calibration markers use the theme `accent`.

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
  → User configures: layers, scale, rotation, base point, DPI, import mode
    (Level is NOT configured here — removed from dialog; defaults to active level)
  → "Import →" pressed
  → ImportParams constructed
  → Scene placement: origin or interactive click-to-place
  → Underlay record created (levels = [active_level]; import_mode from params; snap = True)
  → _apply_underlay_display() sets transform origin, scale, rotation, opacity, lock
  → Record + scene item appended to self.underlays
  → underlaysChanged emitted → Underlay Manager + browser tree refresh
```

### 10.7 Modify (prefill/re-import) flow

The import dialog supports a **prefill/modify mode**: when invoked via the
Manager's Modify action, it re-opens pre-filled from the existing record as a
**lossless round-trip** — page/layers/crop/scale/base and levels are restored so
the dialog reflects the placed underlay, not a fresh import. (`_apply_modify_prefill`;
crop is re-selected by bounds via `_restore_crop_from_bounds`, the PDF page is
re-selected without re-firing the thumbnail load via `_sync_page_indicator`.)

**Insertion-position control (Modify-only, 3-way).** A single-select switch bar
replaces the plain "Insert at origin" toggle while modifying, with three modes
(default **Reuse existing position**):

- **Reuse existing position** — keep the underlay where it sits (`position=None`).
- **Pick new position** — interactive cursor-follow re-placement via
  `begin_replace_underlay_placement`, which carries the management fields
  (`_UNDERLAY_MGMT_FIELDS`) across the re-place. **Escape exits pick mode.**
- **Insert at origin** — anchor at `QPointF(0, 0)`.

The chosen mode flows as `replace_underlay(record, params, position=…)`.

On confirm, `Model_Space.replace_underlay` OVERWRITES only geometry and placement:
`path / page / dpi / scale / rotation / base / selected_layers / layout / import_bounds / import_mode`

It PRESERVES all management fields:
`levels / colour / line_weight_name / layer_overrides (by layer name) / hidden_layers / visible / snap / locked / opacity`

Note: `params.scale` bakes into geometry via `import_scale`; the display `scale`
field is preserved as-is. Layer overrides are matched by layer name — new layers
get inherit-defaults; stale names are left dormant. `position` overrides only the
on-canvas anchor; when `None` the underlay keeps its current `scenePos`.

### 10.8 Page-switch preservation (multi-page PDF)

Switching PDF pages in the dialog (`_on_page_thumb_clicked`) loads the new page's
geometry but **preserves the user's selections** the same way Modify does:
**layers by NAME, crop by BOUNDS** (captured before the load, re-applied after).
Non-geometry settings — scale, base point, levels, DPI, import mode — persist
because `_load_pdf_page(reset_base=False)` never touches those widgets and does
not re-derive the base point from the new page's bounds. Layers absent on the new
page are silently not re-checked; crop bounds re-select whatever geometry now
falls inside them.

### 10.9 Deterministic preview fit

The preview "fit" fits against `_content_rect()` — **geometry only, excluding
overlay markers** (crop scrim, base/pick cursors) — so the same content always
fits to the same frame regardless of transient overlay state (initial load, page
switch, Modify prefill).

### 10.10 Insert-at-origin + rotation pivot (as-built)

Vector underlays rotate about the **base point**, not the centroid, matching the
import-dialog preview. `apply_import_transform` bakes `coord → (coord − base) ×
scale` into the geometry, so the base point sits at group-local `(0, 0)`;
`model_space._apply_underlay_display` therefore calls
`setTransformOriginPoint(0, 0)` on vector `QGraphicsItemGroup`s. Raster pixmaps
have no base point (centred on origin at import) and keep the centroid pivot.

> **Backward-compat:** the previous centroid pivot swung the base point away from
> the insert point, flinging "Insert at origin" imports far from the preview (and
> subtly mis-placing off-centre-base non-origin imports). Existing rotated
> underlays shift once on reload to the corrected position.

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

---

## 16. Underlay Manager (as-built, 2026-08-29 @ `56c8148`)

> **Supersedes:** The Display Manager "Underlays" tab (previously §16.6) is **REMOVED** — `display_manager.py` no longer contains an Underlays tab. The Underlay Manager is now the single management home for all underlay editing. The old §16.1–§16.10 content (feat/underlay-display design) is retired; per-view exclusion via `hidden_in_views` is removed from the data model (§3.2). Per-view underlay visibility is re-homed to the view (PlanView/DetailView/SheetViewport) as a future drafting-overrides/view-templates feature — see `view-relationships.md §7.4`.

### 16.1 Overview

The Underlay Manager is a **modeless `QDialog`** opened via the Ribbon "Underlay Manager" button. It is the single surface for all post-import underlay management. The Display Manager no longer has an Underlays tab. The browser tree is navigation-only (§9.3).

**Modules:** `firepro3d/underlay_manager.py`, `underlay_manager_model.py`, `underlay_manager_delegates.py`, `underlay_manager_theme.py`.

### 16.2 Tree table layout

An expandable `QTreeView` with a custom `QAbstractItemModel`. Parent rows = underlays; child rows = source layers (DXF/DWG only).

**Parent row columns:** Name/Source, Type, Vis (`record.visible`), Snap (`record.snap`), Colour (`record.colour`, hex swatch), Weight (`record.line_weight_name`, named combo), Levels (chip list).

**Child row columns (DXF/DWG only):** Layer name, —, Vis (`hidden_layers` membership), — (snap N/A per layer), Colour (`layer_overrides[layer]["colour"]`), Weight (`layer_overrides[layer]["line_weight"]`), —.

Raster PDF underlays have no layer children and disable Snap/Colour/Weight controls (no layers). Vector PDFs show as a single pseudo-layer row — underlay-level colour/weight applies.

```
Underlay Manager
├─ structural.dxf  DXF  ☑  ☑  #a0a0a0  Medium   [Level 1] [Level 2]
│   ├─ A-WALL           ☑     #6060a0  (inherit)
│   └─ A-FURN           ☐     (inherit) (inherit)
├─ floor1.pdf      PDF  ☑  ☑  #c0c0c0  (none)   [All Levels]
└─ mechanical.dxf  DXF  ⚠  ☑  #c0c0c0  (none)   [Level 2]
```

Missing-file rows show the ⚠ marker with all controls enabled (state persists, applies on relink).

### 16.3 Rendering & screen hint (`model_space.py`, `constants.py`)

No change to rendering architecture from the prior design:

- `_build_batched_underlay_group`: each layer's stroke item gets its pen from `underlay_layer_pen(record, layer) -> QPen` (colour + hint width, always cosmetic); text items use NoPen + colour brush.
- **Screen hint:** no effective weight → `UNDERLAY_LINE_WIDTH_PX`. Named weight → `px = width_mm * UNDERLAY_MM_TO_PX_HINT` (6.0, `constants.py`). Always cosmetic — never zoom-scales (§3.4 invariant).
- **Fast-stroker constraint (2026-08-30, perf-critical):** Qt's fast cosmetic stroker only handles widths ≤ 1.0 px; wider cosmetic pens use the generic stroke pipeline, measured **~20× slower** over a dense underlay (22 ms vs 1 ms on a 94k-point reference). `UNDERLAY_LINE_WIDTH_PX` is therefore **1.0** and hint widths ≤ `UNDERLAY_FAST_PATH_SNAP_PX` (1.25) snap down to 1.0; heavier user-chosen named weights keep their true hint width (and its cost). Never raise the default above 1.0.
- **Live re-application:** `Model_Space.repen_underlay(record)` swaps pens/brushes in place (no group rebuild, no `scene.clear()`), O(2 × layer count). Called by the Manager on every edit. Guards deleted C++ objects (`RuntimeError` → skip).
- **Cache untouched:** overrides at pen level only; `cache_key()` unchanged.
- **Effective layer appearance:** `layer_overrides[layer]` → fall back to `record.colour` / `record.line_weight_name`. Two tiers only; state lives on the record in the project file.
- The legacy `line_weight: float` field remains serialized-but-ignored (superseded by `line_weight_name`; never rendered; no migration).

### 16.4 Per-view visibility (removed)

`hidden_in_views` and the `active_view_key in data.hidden_in_views` clause in `LevelManager.apply_to_scene` are **removed**. An underlay is visible in every view of its assigned levels — no per-viewport hiding. The `active_view_key` attribute on `Model_Space` is also removed. Per-view exclusion is deferred to the view-templates feature (`view-relationships.md §7.4`).

### 16.5 Paper pass (`paper_display.py`, `paper_space.py`)

The underlay stage in `apply_paper_overrides` remains, with one change: the `hidden_in_views` visibility step is removed (no per-view exclusion). The paper pass still:

- Iterates `scene.underlays` (record, group) pairs directly.
- Skips groups spatially outside `source_rect`.
- Applies colour overrides: **B&W** → black; **Full Color/Custom** → effective per-layer colours.
- Applies weight overrides: named weight → `pen.setWidthF(width_mm / paper_scale)`, `setCosmetic(False)`; no weight → keep cosmetic screen pen (hairline).
- Saves and restores `(child, pen, brush)` triples; participates in the pass's exception-safe unwind.

### 16.6 Underlay Manager — editing contract

**Instant-apply, no undo.** Every edit mutates the `Underlay` record and calls `scene.repen_underlay` / `LevelManager.apply_to_scene`. Underlays remain excluded from the undo snapshot (§2.2 posture unchanged).

- **Vis / Snap:** checkboxes toggle `record.visible` / `record.snap`; snap change calls `scene.repen_underlay`; visibility change calls `LevelManager.apply_to_scene`.
- **Colour:** single hex swatch picker (no mono/tint modes). Updates `record.colour`; calls `repen_underlay`.
- **Weight:** named Line Weight combo; updates `record.line_weight_name`; calls `repen_underlay`. Named weight removal is blocked if any underlay references it (scan `line_weight_name` + `layer_overrides`); rename propagates to both.
- **Levels column:** chip list — click opens a picker showing all project levels plus "All Levels" (`"*"`); multi-select supported. Updates `record.levels`; calls `apply_to_scene`.
- **Layer child rows:** Vis checkbox writes `hidden_layers` + applies visibility in place; Colour/Weight write `layer_overrides`; both call `repen_underlay`. `underlaysChanged` fires → browser tree stays in sync.
- **Delete:** confirm dialog ("The source file on disk is not affected.") → removes record and scene group; not undoable.
- **Add underlay…** button → opens the existing import dialog.
- **Re-import (modify flow):** invoked from the Manager; import dialog pre-fills from the existing record. On confirm, `Model_Space.replace_underlay` overwrites only geometry+placement fields; preserves management fields (§10.7).
- **Manager data binding:** binds to `Model_Space.underlays`; re-syncs model on `underlaysChanged`.
- **No QSettings writes** — all state persists via `Underlay.to_dict()` in the project file.

### 16.7 Per-underlay snap (`underlay_snap_index.py`, `snap_engine.py`)

`UnderlaySnapIndex.query()` returns nothing for a record where `record.snap is False`. The global SNAP / F3 master gate is the outer check; `record.snap` is the per-underlay inner gate. The old global `Model_Space._snap_to_underlay` flag and its ribbon button are removed.

### 16.8 Edge wiring

- **Refresh-from-disk (§11):** `refresh_underlay` re-imports with `_record=data`, so `layer_overrides` / `hidden_layers` survive on the same record and re-bind by layer name. New layers get inherit-defaults; stale names left dormant (harmless — only queried for extant layers).
- **Duplicate (§8.3):** record copy carries all fields — no extra work.
- **Level rename:** `LevelWidget._remap_underlay_views` remaps occurrences of the old name in `record.levels` to the new name. The `remap_view_key` method on `Underlay` is removed (no `hidden_in_views` to remap). Stale level names in `levels` become dormant (underlay hidden until reassigned from Manager).
- **Failure posture:** paper stage inherits the pass's try/unwind; `repen_underlay` and the visibility pass guard deleted C++ objects (`RuntimeError` → skip).

### 16.9 Acceptance criteria (as-built)

- [x] Underlay Manager opens modeless from Ribbon; "Add underlay…" opens the import dialog; delete shows confirm.
- [x] Vis/Snap/Colour/Weight/Levels edits apply instantly; Manager re-syncs on `underlaysChanged`.
- [x] Per-layer Vis/Colour/Weight in expanded child rows; layer visibility is one state shared with browser.
- [x] `record.snap = False` → `UnderlaySnapIndex.query()` returns nothing for that underlay; global SNAP/F3 still gated.
- [x] `levels` list drives the §7.2 visibility pass; `["*"]` = all levels; empty = hidden.
- [x] Modify flow: re-import overwrites geometry+placement, preserves management fields (§10.7).
- [x] Old `.fpd` files: `hidden_in_views` silently ignored; `level` string migrates to `levels` list; `snap` defaults to `True`.
- [x] Paper pass: B&W → black strokes; named weights measure true-mm; no-weight → hairline. No per-view hiding (removed).
- [x] Full suite green (2956 passed @ 56c8148).

### 16.10 Testing

- Unit (`tests/test_underlay.py`): round-trip for `levels`/`snap` fields; legacy `level`→`levels` migration; `hidden_in_views` silently dropped; default-factory isolation.
- E2E (`tests/test_underlay_manager.py`): import → assign 2 levels → save → reload → levels preserved.
- Widget-driven: Manager edits → actual pen colour/width changes on scene children; layer checkbox ↔ browser sync; weight remove-blocked + rename-follows.
- Export parity: B&W → black strokes; named weight measures true-mm; no-weight baseline unchanged.

## 17. PDF Import Polish (as-built, 2026-08-28)

Shipped on `feat/pdf-import-polish` (grill-locked WHAT; TDD). Amends earlier notes.

**17.1 PDF DPI + import-mode defaults (supersedes §10 "dialog-only").** The
`ImportPane` (Preferences → Import & Conversion) now exposes **PDF DPI**
(72/150/300) and **import mode** (Auto/Vectors/Raster) **defaults**, persisted to
QSettings `import/pdf_dpi` / `import/pdf_import_mode` (`_QSETTINGS_ORG`/`_APP`).
The import dialog **seeds** its PDF Options combos from these on load; a
per-import change is **one-off** (does not write back). The old "these are set in
the import dialog and not read from QSettings" statement is retired.

**17.2 Multi-page page selection by name (supersedes the "batch multi-page"
non-goal).** Batch import is still not wanted. Instead, `pdf_page_names()`
resolves each page's **name** (PyMuPDF page label else "Page N"); the thumbnail
strip shows it as a caption and the info label echoes the selected page. Import
stays single-page. **Amended 2026-08-30:** the interactive placement commit now
persists `params.pdf_page`/`pdf_dpi` into the record (it previously defaulted
to page 0 while the cache carried the selected page's geometry — masked by
cache hits until any re-extraction silently rebuilt the wrong sheet).

**17.3 PDF vector line-width preservation.** `pdf_import_worker._extract_path`
now carries each path's **stroke width**; `_build_batched_underlay_group`
sub-batches stroke geometry **by width** (one cosmetic pen per width bucket,
`pt→mm→px` via `UNDERLAY_MM_TO_PX_HINT`, floored at `UNDERLAY_LINE_WIDTH_PX`), so
the source line-weight hierarchy is preserved. A DM **per-file Line-Weight
override wins** (flattens to one pen); `repen_underlay` preserves each child's
source width (item `data(7)`) on live DM colour/opacity edits. Source **colour**
is still **not** preserved (same deferral as DXF §16-D5). DXF geoms carry no
width → single bucket → unchanged look.

**17.4 PDF text rendering.** Text is rendered DPI-independently at **pixel
(fractional) size** — never point size — positioned at the span **baseline
origin** and **x-scaled to the source span width** so a substitute font's
advances don't drift. `_extract_text` emits `origin`, `size`, `twidth`,
`valign=3`. (Both `_append_geom_to_path` copies — model_space + dxf_preview —
are updated identically; a full de-dup is a filed follow-up.)

**Amended 2026-08-30 (text width on the canvas).** The import transform that
bakes an underlay's `import_scale`/base-point into geometry dicts **must scale
`twidth` together with `size`** — `twidth` is in the same coordinate space as
`size` and drives the append helper's horizontal fit (`sx = twidth/nat_w`), so
leaving it raw distorted canvas text horizontally by the import-scale factor
at architectural scales (the import-dialog preview renders **raw** geometry —
no bake — so it stayed self-consistent, which is why the bug was
canvas-only). This transform was inlined byte-identically in four
`model_space` sites (`_commit_place_import`, `_on_dxf_finished`,
`_import_pdf_vectors`, `_load_underlay_from_cache`), all with the same
omission; it is now the single pure `dwg_converter.apply_import_transform()`
(alongside `filter_geoms_by_bounds`/`compute_geom_bounds`). The
`_append_geom_to_path` copies themselves were verified **byte-identical** (not
the drift) — the two-copy de-dup remains the open §17.4 follow-up.

**17.5 Architectural / engineering scale (PDF only).** The scale dropdown offers
imperial **architectural** (`1/8"…3"=1'-0"`) and **engineering** (`1"=10'…100'`)
presets whose `import_scale` is computed as `M × 25.4/72` (M = paper→real
magnification), verified against the calibration ground truth `import_scale =
real_mm / source_points`. A read-out shows the resulting real-world size, and a
Custom/calibrated factor is annotated with its ratio (`1:M` + named scale).
**DXF/DWG arch-scale is deferred** — its `$INSUNITS`→scale path (`_DXF_INSUNITS`
"to-inches" factors) is inconsistent with the calibration formula and must be
reconciled first (filed follow-up).

## 18. Interactive rendering performance — gesture freeze-blit (as-built, 2026-08-29)

Dense vector underlays (20k+ batched primitives) made zoom/pan repaints scale
with zoom (measured 47→228 ms/frame ×1→×8 on a reference project; no-underlay
baseline 8–14 ms flat). During an interactive gesture the underlay is therefore
frozen to a bitmap and not re-stroked per frame.

### 18.1 Mechanism (`underlay_freeze.py`)

- `_UnderlayPathItem(QGraphicsPathItem)`: the only child type
  `_build_batched_underlay_group` creates; its `paint()` returns without
  stroking while `scene._underlay_freeze.frozen` is set. **Paint-only
  suppression** — never `setVisible`/`setOpacity` (those states belong to the
  LevelManager pass, the Underlay Manager and the paper pass).
- `UnderlayFreezeController` (owned by `Model_Space`): `begin(view)` hand-
  renders all visible `_UnderlayPathItem`s (pens/brushes/opacity/hidden-layers
  respected, cosmetic pens at device width, **aliased** — the capture only
  lives inside the gesture's accepted degradation window and strokes ~25-40%
  faster) into a transparent pixmap over the padded viewport
  (`UNDERLAY_FREEZE_PAD_FRACTION` 0.25; per-axis clamp
  `UNDERLAY_FREEZE_MAX_PX` with squeeze-not-truncate correction — memory
  bounded at any zoom), adds a transient `QGraphicsPixmapItem` in scene
  coordinates (stretches with the view = transient degradation), and starts
  the `UNDERLAY_FREEZE_SETTLE_MS` single-shot settle timer (scene-parented).
  `end()`/`abort()` removes the pixmap (RuntimeError-guarded against
  C++-deleted objects) and restores vector painting. Raster-PDF underlay
  children are not frozen (already cheap blits).
- **Settle = 450 ms** (amended 2026-08-30 from the grill's ≤150 ms target,
  deliberately): live instrumentation measured 0.3–3 s between deliberate
  wheel ticks; a 100 ms settle unfroze between every tick, so each tick paid
  a fresh capture plus a settle vector repaint (the ">1 s per tick" thrash).
  450 ms spans a natural gesture: one capture at start, one crisp repaint
  ~half a second after the last tick.

### 18.2 Gesture sources (`model_view.py`)

Wheel zoom begins/extends the freeze (settle timer restarts per tick; timer
expiry = gesture end; pure horizontal-scroll wheel events are ignored).
Middle-drag pan begins on first pan move and ends on release.
`fit_to_screen` aborts first (the transient pixmap must not inflate
`itemsBoundingRect`).

### 18.3 Abort sites (the invariants' teeth)

`abort_underlay_freeze()` (public, on `Model_Space`) is called at entry of:
`repen_underlay`, `_apply_underlay_display`, `set_underlay_layer_hidden`,
`refresh_underlay`, `replace_underlay`, `remove_underlay` (Manager
instant-apply, §16.6); `_clear_scene` (load/new — the settle timer must not
outlive the items); `LevelManager.apply_to_scene` (level switches, guarded —
elevation scenes lack the controller); `SheetViewport.paint` (guarded —
covers the on-screen paper canvas AND `export_pdf`/`print_sheets`, so the
plotted PDF can never contain the frozen bitmap; required separately from the
level hook because §6.6's no-op-skip bypasses `apply_to_scene`). The frozen
pixmap uses a transparent background, so theme switches can never leave
stale-theme pixels.

### 18.4 Acceptance & as-built results (2026-08-29 grill; final 2026-08-30)

≤16 ms/frame during gestures at ×0.5–×8 on the reference FPD (probe:
`tools/perf_probe_underlay.py`, FPD path arg + synthetic fallback; no timing
asserts in pytest — behavioral tests live in `tests/test_underlay_freeze.py`).

**As-built on the reference file (with the §16.3 fast-stroker fix, which
turned out to be the dominant lever — live paints were 300–760 ms while
underlay pens were 1.5 px):** plain vector repaints 5.7–15.8 ms at every
zoom (≤16 ms even unfrozen); frozen gesture frames 2.2–5.2 ms; capture
~71 ms; 30-repaint zoom gesture 3.6 s → 208 ms. NOTE: headless probes can
understate live costs when the geometry cache misses (a cache miss
re-extracts only `record.page` — see the page-persistence fix) — the live
instrumented launcher pattern is the trustworthy measurement.

### 18.5 PDF bézier flatten tolerance (task 73, 2026-08-30)

The PDF vector extractor flattens cubic béziers by De Casteljau subdivision
(`pdf_import_worker._flatten_bezier`); `tol` is the max chord deviation in
**PDF points** (1 pt = 1/72"), i.e. a *scale-independent ceiling on the
plotted-sheet curve error* (2.0 pt ≈ 0.7 mm on paper), applied before the
import scale. It governs the geometry-cache size (the Sleeman reference:
4,695 source paths → ~94k points at the fine setting).

**Shipped as a live Preferences knob, not a hardcoded coarsening.** The
value is `constants.PDF_BEZIER_FLATTEN_TOL` (the default) overridden by
`import/pdf_bezier_flatten_tol` (Preferences → Import & Conversion, spinbox
0.25–4.0 pt), read via `pdf_import_worker.current_pdf_flatten_tol()`. That
one reader feeds BOTH the extraction and the **PDF cache key**
(`compute_cache_key(flatten_tol=…)`, folded in only for PDF by
`Underlay.cache_key()` / `_write_underlay_cache`), so changing the setting
re-extracts on the next load or Underlay-Manager refresh. Because the
tolerance now keys PDF caches, the earlier plan to bump `_CACHE_VERSION`
globally was reverted (`_CACHE_VERSION` stays 4) — DXF/DWG pass
`flatten_tol=None`, keeping their keys and caches valid.

**Default = 0.5 (unchanged fidelity).** A visual gate on the Sleeman FPD
showed coarser defaults (2.0, then 1.5) facet visibly when zoomed *past*
plot scale, so the default keeps the original fine 0.5 — no fidelity
regression — and coarsening (for a smaller/faster underlay) is opt-in per
user. Curve **endpoints are always exact** (`_flatten_bezier` emits p0/p3 at
any tol); only interior vertices thin, so on-curve snapping shifts subtly at
coarse settings while arc/curve *ends* stay put. DXF spline/arc/ellipse
flatten tuning is a separate filed follow-up (unit-aware — DXF tolerance is
in drawing units, not paper points). Tests: `tests/test_pdf_bezier_flatten.py`
(endpoint exactness, deviation bound, setting reader), cache-key tolerance
participation in `tests/test_underlay_cache.py`.
