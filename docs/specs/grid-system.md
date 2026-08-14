---
status: current          # Revit-aligned on-canvas re-architecture as-built 2026-08-13 (parametric model; dialog removed); §17 array/offset + inference added 2026-08-14
last-verified: 2026-08-14
verified-commit: de2b12a
applies-to:
  - firepro3d/gridline.py
  - firepro3d/model_space.py
  - firepro3d/property_manager.py
  - firepro3d/model_view.py
  - firepro3d/paper_display.py
  - firepro3d/scene_io.py
  - firepro3d/constants.py
  - firepro3d/inference_engine.py
  - main.py
---

# Grid System Architecture — Design Spec

**Date:** 2026-04-10 (re-architected 2026-08-13)
**Complexity:** Large
**Status:** Implemented
**Source tasks:** TODO.md — "Spec session: grid system architecture"; "polish gridlines" (Revit-aligned UX re-architecture, 2026-08-12/13). See design doc `docs/superpowers/specs/2026-08-12-gridline-revit-ux-design.md`.

## 1. Goal

Define the canonical grid system for FirePro3D: a single **parametric** `GridlineItem` class (origin + length + angle + per-bubble offsets) with auto-numbered bubble labels, pull-tab grips, lock support, perpendicular repositioning, and on-selection spacing dimensions. Gridlines are placed **on-canvas** (Revit-style, mirroring the Line tool) and edited through the right-side **Properties panel** — there is no modal dialog. Gridlines are level-independent building datums that project into elevation views. The legacy `GridLine` class is removed.

## 2. Motivation

The grid system diverged from both its spec and the app's Revit-aligned mental model. Editing lived in a modal table (`grid_lines_dialog.py`) rather than on-canvas + Properties panel like every other entity; grip drag *translated the whole line* instead of extending/shortening it; the bubble standoff was a length-proportional "overshoot" baked into geometry rather than an editable property; angled gridlines were second-class (a binary `dy>=dx` bucket mis-paired non-parallel lines for spacing); and the dash-dot linetype read as solid when zoomed out or exported to PDF. The 2026-08-13 re-architecture replaces the dialog with **on-canvas placement + Properties-panel editing**, adopts a **native parametric data model**, and fixes those correctness bugs. The legacy `GridLine` class was already removed in the original consolidation.

## 3. Architecture & Constraints

### 3.1 Canonical Class: `GridlineItem`

`GridlineItem` (`firepro3d/gridline.py`) is the single gridline implementation. `GridLine` (`firepro3d/grid_line.py`) is deprecated and removed.

### 3.2 Level Independence

Gridlines are building-wide vertical datums. They have no `level` field and appear in all plan views regardless of active level. The existing `level` field is removed from `GridlineItem`.

### 3.3 Coordinate System (Parametric)

All geometry stored in millimeters (project convention). The **authoritative state is parametric**: `_origin` (the "main point" / start), `_length` (mm), and `_angle_deg` (0–360°, **Y-up**: 0°=East, CCW-positive — same convention as the Line tool's Tab input). The underlying `QGraphicsLineItem` `line()` (p1=origin, p2=origin+length·(cosθ, −sinθ)) is **derived** and kept eagerly in sync by a single writer (`_rebuild_geometry()`), so snap / spacing / elevation readers that call `line()` need no per-consumer shim. See §4.

### 3.4 Angled Gridlines

Gridlines support arbitrary angles (not just cardinal); the angle is a first-class stored field (§4.1). Classification as "vertical" (dy >= dx) or "horizontal" (dy < dx) determines the auto-labeling scheme (§6). Spacing-dimension pairing is **not** keyed off that binary classification — it uses true-parallelism angle clustering (§5.4).

### 3.5 Cross-References

- **Snap engine:** Gridline snap participation is defined in `docs/specs/snapping-engine.md` §5. This spec does not redefine snap rules. Snap reads `line()`, which the parametric model keeps in sync.
- **Paper space:** True-scale bubble rendering through sheet viewports is defined in `docs/specs/paper-space.md` §9.9.1 (label height is a Grid Line paper-category setting; there is no per-item property). See §10.2.
- **Theming:** Selection-grip style (white fill + `SELECTION_OUTLINE_COLOR`) is owned by `docs/architecture/theming.md`. See §5 / §14.
- **Constants:** Grid constant *values* live in `firepro3d/constants.py` (`GRIDLINE_BUBBLE_OFFSET_MM`, dash geometry, colors). This spec names them, not their values (Rule A).

## 4. Data Model (Parametric)

### 4.1 `GridlineItem` State

`GridlineItem` is a `QGraphicsLineItem` whose **source-of-truth is parametric**. A single `_rebuild_geometry()` is the **sole writer** of all derived state — the `line()`, bubble positions, grip positions, and lock-indicator position. Every mutator (placement, grip drag, panel edit, load) routes through it, so `line()` always reflects the parametric truth.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `_origin` | `QPointF` | (from constructor) | The "main point" / start endpoint (scene mm) |
| `_length` | `float` | (derived at ctor) | Gridline length in mm (mutators floor at 1.0) |
| `_angle_deg` | `float` | (derived at ctor) | 0–360°, Y-up (0°=East, CCW+) |
| `_bubble1_offset` | `float` | `GRIDLINE_BUBBLE_OFFSET_MM` | Absolute along-axis outward standoff at the origin end (mm) |
| `_bubble2_offset` | `float` | `GRIDLINE_BUBBLE_OFFSET_MM` | Absolute along-axis outward standoff at the far end (mm) |
| `_label_text` | `str` | auto-assigned | Shared by both bubbles |
| `_locked` | `bool` | `False` | Prevents grip drag, body drag, spacing edit, panel geometry edit |
| `_display_overrides` | `dict` | `{}` | Per-instance display overrides |
| `_display_scale` | `float` | `1.0` | Bubble scale factor (from Display Manager) |
| `_grid_color` | `QColor` | `GRID_COLOR` (#4488cc) | Line + bubble border color |
| `_paper_*` (4) | — | — | Write-together paper-pass state (owned by `paper_display`, §10.2) |

Per-end bubble **visibility** is stored on the `GridBubble` child items (`isVisible()`), not as separate `GridlineItem` flags.

**Derived (never stored):** `line()` p1/p2, bubble/grip/lock positions — all written only by `_rebuild_geometry()`:

```
p1 = _origin
p2 = _origin + _length · (cos θ, −sin θ)   # θ = radians(_angle_deg); Y-up → scene Y-down
setLine(p1, p2)
bubble1 at  p1 − _bubble1_offset · û        # û = unit direction; outward = away from the span
bubble2 at  p2 + _bubble2_offset · û
reposition grips + lock indicator
```

**Removed fields:** `_p1`/`_p2` explicit endpoints (now derived); `level` (gridlines are level-independent); `_user_layer` (layer system removed); `paper_height_mm` (retired 2026-08-08 — bubble label height is category-owned, paper-space §9.9.1).

**Retired concept:** the length-proportional bubble overshoot (`GRIDLINE_BUBBLE_OVERSHOOT_FRAC`) is gone. `line()` is the *clicked span* (origin→far); bubbles stand off by explicit absolute per-end offsets (default `GRIDLINE_BUBBLE_OFFSET_MM`, `constants.py`). `paint()` draws from the offset bubble edge, shortened so the line meets each visible bubble.

### 4.2 `GridBubble` (Child)

`QGraphicsEllipseItem` with `ItemIgnoresTransformations` — constant screen size during model-space editing. Two instances per gridline, positioned by `_rebuild_geometry()` at each endpoint standoff.

- Centered label text (Consolas, bold, pixel-size scaled to bubble radius)
- Click on bubble selects parent gridline; Ctrl+Click toggles selection
- Duplicate-label warning: bubble border color changes to orange (`#ff8800`) when the label matches another gridline in the scene. **Border width is unchanged** by the warning. Clears automatically when resolved.
- `enter_paper_mode()` / `exit_paper_mode()` swap to scene-unit geometry for the paper render pass (§10.2, paper-space §9.9.1).

### 4.3 Pull-Tab Grips (Child)

`_PullTabGrip` — `QGraphicsRectItem` with `ItemIgnoresTransformations` (constant screen size). Two instances per gridline, positioned slightly outward beyond each endpoint along the line direction.

- Visible only when the gridline is selected (and unlocked) or hovered
- Rendered in the **house selection-grip style**: white fill + `SELECTION_OUTLINE_COLOR` (#0055ff) outline (per `docs/architecture/theming.md`); model grips are screen-px sized
- Dragging a grip extends/shortens the gridline along its axis (§5.2)

A `_LockIndicator` padlock child renders beside the origin bubble when the gridline is selected; clicking it toggles `_locked`.

### 4.4 Serialization Format

`to_dict` emits the parametric format (`display_overrides` written only when non-empty):

```json
{
    "origin": [x, y],
    "length": 12000.0,
    "angle": 90.0,
    "bubble1_offset": 1000.0,
    "bubble2_offset": 1000.0,
    "bubble1_vis": true,
    "bubble2_vis": true,
    "label": "1",
    "locked": false,
    "display_overrides": {}
}
```

`from_dict` reads this parametric format and **migrates legacy formats** — see §9.2. Both serialization paths (`scene_io.py` file I/O and `model_space._capture_network` / `_restore_network` undo) delegate to these class methods; there is one serializer, not two hand-written copies.

## 5. Movement & Interaction

### 5.1 Body Drag (Reposition)

Triggered by clicking the gridline body (not bubble, not grip) and dragging.

- Movement constrained to the perpendicular direction only. Mouse delta is projected onto the perpendicular vector; the parallel component is discarded.
- Lock-aware: no-op if `_locked`.
- Undo: single state push on mouse release.

### 5.2 Grip Drag (Extend/Shorten)

Triggered by clicking a pull-tab grip and dragging. `apply_grip(index, new_pos)` **extends/shortens the gridline along its own axis with the opposite endpoint fixed** — it does *not* translate the whole line (the pre-re-architecture bug).

- Index 0 (origin end) and index 1 (far end): the cursor is projected onto the line direction; the perpendicular component is discarded. The grabbed endpoint moves along the axis, the other stays put, and `_length` (and `_origin`, for the origin grip) update accordingly.
- Length floors at 1.0 mm.
- Re-angling is **not** a grip gesture — angle lives in the Properties panel / placement.
- Lock-aware: no-op if `_locked`.
- Undo: single state push on mouse release. Multi-select applies the same grip delta to all selected gridlines.

### 5.3 Movement API

| Method | Constraint | Lock-aware |
|--------|-----------|------------|
| `apply_grip(index, new_pos)` | Along line direction only (opposite end fixed) | Yes |
| `move_perpendicular(offset)` | Perpendicular to line direction only | Yes |
| `set_perpendicular_position(value)` | Absolute perpendicular coordinate | Yes |

`_perpendicular_vector()` is a **fixed** normal `(−d.y, d.x)` with **no** sign-flip. The fixed sign guarantees every gridline in a parallel cluster shares a consistent normal, which the parallelism-based spacing (§5.4) requires.

### 5.4 On-Selection Spacing Dimensions

When one or more gridlines are selected, spacing dimensions appear between **truly parallel** gridlines using the existing dimensional constraint visual style. Pairing is by **angle clustering**: each gridline's direction angle mod π; two gridlines are parallel (eligible for a spacing dimension) iff their angles agree within a small fixed tolerance (`EPS_ANGLE`). Within a parallel cluster, members are projected onto the cluster's shared normal, sorted, and a dimension is emitted between every adjacent pair where ≥1 member is selected. **Non-parallel neighbors get no dimension.** This replaces the old binary `dy>=dx` bucket, which mis-paired lines of different angles and flipped discontinuously near 45°.

- **Single selection:** dimensions to the nearest parallel unselected neighbor on each side (adjacent pairs in the sorted cluster).
- **Multi-selection:** dimensions between adjacent selected parallel gridlines plus dimensions to the nearest unselected parallel neighbor on each outer edge.

### 5.5 Double-Click Spacing Edit

Double-clicking a spacing dimension opens an inline text field on the dimension (routed through `model_view.mouseDoubleClickEvent`; the dims are read from a cached copy so the second click of the double-click cannot clear them). The user enters a new spacing value in display units (via the existing numerical input handler with unit conversion).

- **Single selection:** the selected gridline moves perpendicular to satisfy the new spacing. The neighbor stays fixed.
- **Multi-selection:** all selected gridlines move as a rigid group, maintaining their relative spacing. The unselected anchor neighbor stays fixed.
- Lock-aware: locked gridlines in the moving set are skipped.
- Undo: single state push.

### 5.6 Bubble Offset (Implemented)

Each bubble stands off from its endpoint by an **absolute, editable per-end offset** (`_bubble1_offset` / `_bubble2_offset`, mm; default `GRIDLINE_BUBBLE_OFFSET_MM`). Offsets are edited via the Properties panel (§7). The offset is along the gridline axis, outward from the span; the line is shortened in `paint()` to meet the visible bubble edge. Independent bubble **leader/jog** offset (moving a bubble off-axis with a leader line) remains a future follow-up.

### 5.7 Double-Click to Select

Double-clicking a gridline body or bubble reliably selects the gridline (`model_view.mouseDoubleClickEvent`) and emits `requestPropertyUpdate`, guarding against the second press of the double-click landing on empty space and clearing the selection.

## 6. Auto-Numbering

### 6.1 Labeling Scheme

**Flipped 2026-08-13** to match the default-seed convention (user preference):

- **Vertical gridlines** (dy >= dx): Numbers — 1, 2, 3, …
- **Horizontal gridlines** (dy < dx): Letters — A, B, C, …, Z, AA, AB, …, AZ, BA, …

Classification uses the `dy >= dx` test on the p1→p2 delta. (This binary test still drives *labeling*; spacing pairing uses true-parallelism clustering — §5.4.)

### 6.2 Global Counters

Module-level `_next_number: int` and `_next_letter_idx: int`. The `auto_label(p1, p2)` function classifies orientation and returns the next label from the appropriate counter. Auto-labeling happens in `GridlineItem.__init__`.

### 6.3 Counter Sync

On any event that could create a mismatch between counter state and scene state, `sync_grid_counters(gridlines)` scans all existing `GridlineItem` instances and resets each counter to max+1:

- **File load** — after `from_dict()` restores all gridlines (`scene_io`)
- **Undo/redo** — after scene state is restored (`_restore_network`)
- **Before each on-canvas placement** — `_make_line_like` syncs the counters to the existing gridlines *before* constructing the new `GridlineItem` (which auto-labels at construction), so a placed gridline continues the sequence (e.g. "4" after a 1/2/3 seed) instead of restarting, then re-syncs after append

Sync logic:
1. Collect all existing labels, classify each as number or letter.
2. For numbers: parse to int, set counter to max+1.
3. For letters: convert to index (A=0, Z=25, AA=26, AB=27…), set counter to max+1.
4. Non-parseable labels (user-entered custom text like "X-1") are ignored by sync.

### 6.4 Duplicate Detection

After any label change (Properties-panel relabel, auto-assign at placement, load, undo/redo) `apply_duplicate_warnings` scans for duplicates. Gridlines with duplicate labels display a visual warning:

- Bubble border color changes to orange (`#ff8800`); the border **width is unchanged**
- Warning is informational only — does not block any operation
- Clears automatically when the duplicate is resolved (rename or delete)

## 7. On-Canvas Placement & Properties-Panel Editing

> The former modal Grid Lines dialog (`grid_lines_dialog.py`, `apply_grid_dialog`, and its MainWindow opener) was **removed** in the 2026-08-13 re-architecture in favor of on-canvas placement + Properties-panel editing (Revit-aligned). Its table / in-dialog undo / round-trip / reconciliation machinery no longer exists. Batch replication is via **copy/paste**; an on-canvas array/offset tool is a filed follow-up (§16).

### 7.1 On-Canvas Placement

Gridlines are placed with a new `draw_gridline` scene mode that **rides the Line-tool handlers** — `_press_draw_line`, the `_handle_tab_input` dynamic-input branch, the move-time dimension hint, and `_constrain_angle` — with the only divergence being a `_make_line_like` item factory (`draw_line` → `LineItem`; `draw_gridline` → `GridlineItem`). This structurally guarantees placement mirrors the Line tool one-for-one:

- **1st click** = origin; **2nd click** = length + angle
- **Ctrl** = angle-constrain; **Tab** = exact length + angle dynamic input
- `single_place_mode` returns to select mode after one placement; otherwise it loops
- On placement the factory syncs auto-number counters *before* construction (§6.3), calls `apply_category_defaults` (adopts the live Display Manager "Grid Line" color/scale), appends to `_gridlines`, selects the item, emits `requestPropertyUpdate`, then re-syncs counters and re-runs duplicate warnings

The **Draw-tab ribbon "Gridline" button** (a checkable mode button in the Geometry group, `main.py`) sets `draw_gridline`. The default 3+3 seed is unchanged (`place_grid_lines`, called by `_place_default_gridlines`).

### 7.2 Properties-Panel Editing

`GridlineItem.get_properties()` / `set_property()` expose the gridline's editable geometry to the right-side Properties panel (`property_manager.py` dispatches to these, like every other entity). Rows:

| Row | Type | `set_property` effect |
|-----|------|-----------------------|
| Label | string | relabel + duplicate re-scan |
| Origin X | dimension (mm) | set `_origin.x()` → **whole line translates** |
| Origin Y | dimension (mm) | set `_origin.y()` → **whole line translates** |
| Length | dimension (mm, min 1.0) | set `_length`, origin fixed |
| Angle | string (numeric, `°` suffix) | parse + set `_angle_deg` mod 360 → rotate about origin; invalid input reverts |
| End X / End Y | label (read-only) | derived far endpoint, informational |
| Bubble 1 / Bubble 2 | enum (Visible/Hidden) | toggle that bubble's visibility |
| Bubble 1 Offset / Bubble 2 Offset | dimension (mm, min 0.0) | set `_bubbleN_offset` |
| Locked | enum (True/False) | set `_locked` |

**Y is displayed up-positive.** The scene stays Qt down-positive; Origin Y and End Y are **negated** for display and re-negated on parse, so a value typed as "up" reads/writes correctly. Negative-zero is normalized to 0 for both Origin and End coordinates.

Angle is a plain numeric string (not a `dimension`) because degrees are not an mm quantity — mirroring the old plain-numeric angle cell; the `°` suffix is stripped on parse.

Geometry/offset commits (Origin X/Y, Length, Angle, Bubble 1/2 Offset) push **one** model-space undo state after mutating (`push_undo_state()`), because model-space property edits don't self-capture undo otherwise. Each panel commit is one undo step.

## 8. Elevation View Integration

### 8.1 Gridline Filtering Rule

Only exactly-cardinal gridlines appear in elevation views:

- **North/South elevations:** Show gridlines where `dx == 0` (within epsilon `1e-6`)
- **East/West elevations:** Show gridlines where `dy == 0` (within epsilon `1e-6`)
- Angled gridlines (dx ≠ 0 and dy ≠ 0) never appear in any elevation view.

### 8.2 Projection

For a qualifying gridline, the `ElevGridlineItem` is drawn as a vertical line in the elevation:

- **H-position:** The gridline's perpendicular coordinate (X for vertical gridlines in N/S, Y for horizontal gridlines in E/W), sign-adjusted per the existing direction mapping table in `elevation_scene.py`.
- **V-extent (default):** Top of highest level to bottom of lowest level (full building height from `LevelManager`).

### 8.3 Per-View Z-Extent Overrides

Each `ElevationScene` stores a dict mapping gridline labels to Z-extent overrides:

```python
_gridline_z_overrides: dict[str, dict]  # label → {"v_top": float, "v_bot": float}
```

- Override set via grip drag on `ElevGridlineItem` top/bottom grips in the elevation view.
- If no override exists, defaults to full building height (recalculated on each rebuild).
- Overrides are **per-view** — adjusting a gridline's extent in the North elevation does not affect the South or East elevations.

### 8.4 Elevation Override Serialization

Stored in the elevation view's `to_dict()`:

```json
{
    "direction": "north",
    "gridline_z_overrides": {
        "A": {"v_top": -500.0, "v_bot": 12000.0},
        "C": {"v_top": 0.0, "v_bot": 6000.0}
    }
}
```

### 8.5 Level Datums

`ElevDatumItem` behavior is unchanged. Horizontal reference lines span all visible gridlines. Extent recalculated from projected gridline H-positions.

## 9. Legacy Cleanup & Migration

### 9.1 `grid_line.py` Removal

- Delete `firepro3d/grid_line.py` entirely.
- Remove all imports of `GridLine` from other modules.
- Any serialized project files using the old format are handled by migration (§9.2).

### 9.2 Serialization Migration

The `from_dict()` loader reads the current **parametric** format (`"origin"` key present) and migrates legacy formats:

| Legacy input | Migration |
|--------------|-----------|
| No `"origin"` key, but `"p1"`/`"p2"` present | Two-point geometry → derive `_origin`/`_length`/`_angle_deg`/offsets via the ctor |
| No `"origin"` key, but `"start"`/`"end"` present | Older two-point key names → same derivation |
| `"bubble_start"`/`"bubble_end"` | Old bubble-visibility keys → read as `bubble1_vis`/`bubble2_vis` |
| `bubble1_offset`/`bubble2_offset` absent | Default to `GRIDLINE_BUBBLE_OFFSET_MM` |
| Legacy keys (`level`, `axis`, `user_layer`, `paper_height_mm`) | Silently ignored (layer system removed; per-item paper height retired; orientation is stored) |

When the parametric format is present, `_length`/`_angle_deg` are set exactly from the stored values (not re-derived from a computed `p2`) to avoid float drift.

### 9.3 `level` Field Removal

Existing project files with `"level"` on gridlines: field is read and silently discarded on load. No migration action needed — gridlines simply become visible on all levels.

## 10. Display & Paper Space

### 10.1 Display Manager Category

Single category: **"Grid Line"**

| Property | Default | Applies to |
|----------|---------|-----------|
| `color` | `#4488cc` | Line pen, bubble border |
| `fill` | `#1a1a2e` | Bubble fill |
| `opacity` | `100` | Entire item (0–100%) |
| `scale` | `1.0` | Bubble radius multiplier |
| `visible` | `True` | Show/hide all gridlines |

Per-instance overrides via `_display_overrides` take precedence over category defaults.

### 10.1.1 Dash-Dot Linetype

The gridline renders as a **dash-dot** line. The line pen is non-cosmetic (width in scene units) with an explicit `setDashPattern`; the dash geometry is resolved differently on screen vs paper so it never collapses to apparent-solid:

- **On screen (model-absolute):** the dash pattern is a **fixed model-mm** pattern that scales with zoom like a CAD/Revit model linetype — bold at working zoom, thinning toward solid only at extreme zoom-out. Constants `_DASH_MODEL_MM`/`_GAP_MODEL_MM`/`_DOT_MODEL_MM` (`gridline.py`). The line **weight** stays a screen constant (~`GRID_WIDTH` px).
- **On paper (paper-mm):** the dash pattern is a **fixed on-paper mm** pattern (`_DASH_MM`/`_GAP_MM`/`_DOT_MM`), normalized by the on-paper line width (`_paper_line_w_mm`) so — because pen width and pattern both ride the viewport scale — the on-paper dash resolves to the fixed mm regardless of viewport scale, and a PDF reads as dash-dot at any DPI.

The **selection highlight** and the **duplicate-warning** recolor never change line/border width (dup warning recolors the bubble border only; §6.4).

### 10.2 Paper Space Bridge [as-built 2026-08-08]

Mechanism owned by `docs/specs/paper-space.md` §9.9.1 (Rule A — see there for the render-pass contract). Grid-system-side summary:

- **Model-space editing:** unchanged — bubbles stay `ItemIgnoresTransformations`, fixed screen size, always readable. (The thin-lines WYSIWYG-preview toggle is deferred.)
- **Sheet view rendering:** bubbles render at a true paper size derived from the Grid Line paper category's `bubble_label_height_mm` (label cap height, factory 3.0 mm); the category line weight drives both the gridline line and the bubble border on paper.
- **Retired:** the per-item `GridlineItem.paper_height_mm` field. `to_dict` stops writing it; `from_dict` ignores the legacy key. Sizing is uniform per category (grill decision 2026-08-07).
- Selection ring, pull-tab grips, lock indicator, and the duplicate-label warning color never plot.

## 11. Design Decisions

### 11.1 Single canonical class

**Chosen:** Consolidate into `GridlineItem`, remove `GridLine`.
**Rationale:** Two parallel implementations with overlapping features adds maintenance burden without value. `GridlineItem` is the active implementation; missing features (lock, grips, perpendicular move) are absorbed from `GridLine`.

### 11.2 On-canvas placement + Properties panel (dialog removed)

**Chosen:** Delete the modal Grid Lines dialog. Place gridlines on-canvas (mirroring the Line tool) and edit them through the right-side Properties panel — like every other entity. Batch creation = copy/paste; an on-canvas array/offset tool is a filed follow-up.
**Rationale:** The modal table diverged from the app's Revit-aligned mental model (on-canvas + property panel) and from the property-panel-over-dialog preference. On-canvas placement by *code-sharing* the Line-tool handlers (item-factory divergence only) structurally guarantees behavioral parity and prevents drift, at zero extra placement code.

### 11.11 Native parametric storage

**Chosen:** Store `_origin` + `_length` + `_angle_deg` + per-bubble offsets as source-of-truth; derive `line()` via a single `_rebuild_geometry()` writer.
**Rationale:** The panel-edit math (translate-whole-line / length / rotate-about-origin) falls straight out of parametric fields, and the model matches the on-canvas UX. `line()` is kept eagerly in sync so read-only consumers (snap / spacing / elevation) need no changes. Cost: both serialization paths and legacy migration are rewritten — accepted.

### 11.12 Grip = extend/shorten along the line (opposite end fixed)

**Chosen:** A pull-tab grip drag extends/shortens the gridline along its axis with the far end fixed; re-angling is a panel edit, not a grip gesture.
**Rationale:** Supersedes the pre-re-architecture whole-line-translate bug. Predictable, matches the parametric length field. Body drag remains perpendicular reposition.

### 11.13 Absolute mm bubble offset (retire fractional overshoot)

**Chosen:** Bubble standoff is an absolute, editable per-end mm offset (default `GRIDLINE_BUBBLE_OFFSET_MM`); the length-proportional `GRIDLINE_BUBBLE_OVERSHOOT_FRAC` is retired.
**Rationale:** Standoff no longer scales with gridline length (long lines got huge overshoots); it becomes a first-class editable property; and geometry no longer bakes the bubble end into `line()` (which had forced a lossy round-trip inverse in the old dialog).

### 11.14 Parallelism-based spacing pairing

**Chosen:** Pair gridlines for spacing dimensions by true parallelism (angle mod π within `EPS_ANGLE`), not the binary `dy>=dx` bucket.
**Rationale:** The binary bucket mis-paired non-parallel lines and flipped discontinuously near 45°. Naming keeps `dy>=dx` (standard structural convention); only spacing pairing changed.

### 11.15 Model-absolute dash on screen, paper-mm on paper

**Chosen:** Explicit `setDashPattern` — fixed model-mm on screen (scales with zoom like a CAD linetype), fixed on-paper-mm normalized by paper line width on paper.
**Rationale:** `Qt.PenStyle.DashDotLine`'s pattern is expressed in pen-width multiples, so a non-cosmetic pen collapsed the dashes to apparent-solid when zoomed out or rendered at print DPI. Explicit patterns keep the linetype legible everywhere.

### 11.16 Y displayed up-positive

**Chosen:** Origin Y / End Y are shown and parsed up-positive in the Properties panel (scene stays Qt down-positive); negative-zero normalized to 0.
**Rationale:** Matches user/architectural convention that "up" is positive; avoids a confusing sign inversion in the panel.

### 11.3 Level independence

**Chosen:** Remove `level` field. Gridlines visible on all plan levels.
**Rationale:** Gridlines are building-wide structural datums (column grid), not floor-specific elements. Matches Revit semantics.

### 11.4 Angled gridlines as first-class

**Chosen:** Support arbitrary angles.
**Rationale:** Real fire protection layouts include buildings with angled wings. The geometry already supports arbitrary p1/p2; the spec formalizes this and defines elevation behavior (cardinal-only filtering).

### 11.5 Elevation filtering — perpendicular cardinal only

**Chosen:** Only exactly-cardinal gridlines (dx=0 or dy=0 within epsilon) appear in elevations.
**Rationale:** Projecting angled gridlines onto an elevation plane creates ambiguity about H-position. Cardinal-only is simple, predictable, and matches the convention that elevation views show perpendicular structural bays. Angled gridlines in sections are a future section-view feature.

### 11.6 Body drag constrained perpendicular

**Chosen:** Perpendicular-only movement.
**Rationale:** Matches Revit. Prevents accidental rotation. A gridline's "position" is its perpendicular coordinate — that's what spacing depends on.

### 11.7 Spacing dimensions with double-click edit

**Chosen:** Show on selection, double-click to edit, isolate movement (no cascade).
**Rationale:** Provides immediate feedback on grid spacing without a separate tool. Isolation (only selected gridlines move) is predictable. Multi-selection enables rigid-group movement for cascade-like behavior when desired.

### 11.8 Bubble standoff as an editable absolute offset

**Chosen:** Each bubble stands off its endpoint by an editable absolute mm offset (§5.6, §11.13). Off-axis bubble **leader/jog** offset remains a follow-up.
**Rationale:** An absolute per-end offset is the natural parametric replacement for the retired length-proportional overshoot and gives users direct control without leader-rendering complexity.

### 11.9 Counter sync (no gap-filling)

**Chosen:** Sync to max+1, do not fill gaps.
**Rationale:** Gap-filling risks confusing label sequences. Users can manually relabel to fill gaps if desired.

### 11.10 Duplicate labels — warn but allow

**Chosen:** Visual warning (orange bubble border), no enforcement.
**Rationale:** Strict enforcement creates frustrating UX during batch relabeling (rename A→temp before renaming B→A). Duplicates are almost always mistakes, so the visual cue is sufficient.

## 12. Acceptance Criteria

- [x] `GridlineItem` is the single canonical gridline class
- [x] `grid_line.py` removed; all imports cleaned up
- [x] Parametric data model: `_origin` + `_length` + `_angle_deg` + per-bubble offsets; single `_rebuild_geometry()` writer keeps `line()` in sync
- [x] Lock/unlock prevents grip drag, body drag, spacing edit, and panel geometry edit
- [x] Visible pull-tab grips at endpoints (on selection/hover), house selection-grip style (white + `SELECTION_OUTLINE_COLOR`)
- [x] Perpendicular body drag with directional constraint (fixed-sign normal)
- [x] On-canvas placement via `draw_gridline` mode, mirroring the Line tool (1st click origin, 2nd click length+angle, Ctrl-constrain, Tab exact input, single-place)
- [x] Draw-tab ribbon "Gridline" button sets `draw_gridline`; modal Grid Lines dialog removed
- [x] Properties-panel editing: Origin X/Y translate whole line, Length (origin fixed), Angle (rotate about origin), Bubble visible/offset, Label, Locked; End X/Y read-only; each geometry/offset commit = one undo step
- [x] Origin Y / End Y displayed and parsed up-positive; negative-zero normalized to 0
- [x] Paper-space bridge: bubbles true-scale through sheet viewports per §10.2 / paper-space §9.9.1 (category-owned label height; per-item `paper_height_mm` retired) — built 2026-08-08
- [x] Angled gridlines supported as first-class (stored angle)
- [ ] Elevation views show only exactly-cardinal gridlines (perpendicular to viewing plane)
- [x] Auto-numbering counters sync to max existing label on load/undo/before each on-canvas placement
- [x] Auto-labeling: vertical (dy>=dx) → numbers, horizontal → letters (matches default seed)
- [x] Duplicate labels produce visual warning (orange bubble border, width unchanged), not enforcement
- [x] Grip drag extends/shortens along line (opposite end fixed); body drag constrained perpendicular
- [x] Bubble standoff is an editable absolute per-end offset (default `GRIDLINE_BUBBLE_OFFSET_MM`); fractional overshoot retired
- [x] Gridlines render as legible dash-dot (model-absolute on screen, paper-mm on paper — no apparent-solid)
- [x] Gridlines are level-independent (visible on all plan levels, `level` field removed)
- [ ] Elevation Z-extent defaults to full building height; per-view grip-editable overrides stored on elevation scene
- [x] Single "Grid Line" display manager category
- [x] Undo: panel geometry commit = one step; drag operations = one step on mouse release
- [x] On-selection spacing dimensions between truly parallel gridlines (angle clustering); non-parallel neighbors show none
- [x] Double-click spacing edit: selected gridline(s) move, neighbor stays fixed; multi-select moves as rigid group preserving relative spacing
- [x] Serialization: new parametric format on both paths (`scene_io` + `_capture_network`); legacy `p1/p2` (and `start/end`) files load
- [x] Snap interaction deferred to snap spec (cross-reference only)

## Alignment Constraint Participation

Gridlines can be both **reference** and **target** for the Align tool:

- **As reference:** The gridline's single line segment (p1→p2) serves as the reference edge. Other items align to it.
- **As target:** The Align tool calls `set_perpendicular_position()` to move the gridline. This respects the existing `_locked` flag — locked gridlines cannot be aligned (status bar warning: "Gridline 'X' is locked").
- **Edge extraction:** A gridline exposes exactly one linear segment (p1→p2).
- **Lock constraint:** When locked via Align, an `AlignmentConstraint` is stored referencing the gridline. The padlock icon appears at the alignment point. Moving the reference triggers `set_perpendicular_position()` via the constraint solver.

No structural changes to `GridlineItem` are needed. The existing `move_perpendicular()` and `set_perpendicular_position()` APIs are sufficient.

## 13. Verification Checklist

- [x] Core acceptance criteria met (except elevation Z-override items, still open)
- [x] Unit tests pass: auto-numbering (flipped), serialization round-trip (both paths), legacy migration, parametric edits, grip extend/shorten, parallelism spacing, duplicate detection
- [x] Functional/widget tests: on-canvas placement mirrors the Line tool (incl. Tab + Ctrl); property-panel edits reach geometry; copy/paste of a lone gridline
- [x] No regressions: default 3+3 seed, snap on gridlines, duplicate warnings, lock enforcement
- [x] `grid_line.py` and `grid_lines_dialog.py` fully removed, no dead imports
- [x] Existing project files with legacy `p1/p2` gridlines load correctly
- [x] Startup seed cannot be undone away (undo stack reset after seed, `main.py`)
- [ ] Align tool can use gridline as reference (other items align to it)
- [ ] Align tool can use gridline as target (gridline moves to match reference)
- [ ] Locked gridlines rejected by Align tool with status bar warning
- [ ] AlignmentConstraint lock works with gridline as target

## 14. Existing Code Context

| File | Role |
|------|------|
| `firepro3d/gridline.py` | Canonical parametric `GridlineItem` + `GridBubble` + grips/lock; serialization; paint/dash; `get_properties`/`set_property`; `alignment_reference_points()`; `offset_copy()`/`array_copies()` copy factories; `_is_template` placement-template flag |
| `firepro3d/model_space.py` | Scene management, gridline storage, `draw_gridline` placement (`_make_line_like`), grip path, parallelism spacing, body drag, `place_grid_lines` seed, both undo serialization paths; `gridline_offset`/`gridline_array` transient modes; `_collect_alignment_refs`; `get_effective_position` inference hook; `_get_gridline_template()` |
| `firepro3d/property_manager.py` | Right-side Properties panel dispatch to `get_properties`/`set_property` |
| `firepro3d/model_view.py` | Double-click-to-select gridline + double-click spacing-dimension edit; `drawForeground` inference guide + array/offset ghost-preview overlay |
| `firepro3d/inference_engine.py` | `InferenceEngine`, `ReferenceFeature`, `Guide`, `InferenceResult` — entity-agnostic; owned by `Model_Space` |
| `firepro3d/paper_display.py` | Paper render pass: `_apply_gridline` true-scale bubbles + dash-dot paper geometry (§10.2) |
| `firepro3d/scene_io.py` | File serialization (delegates to `GridlineItem.to_dict`/`from_dict`); counter sync on load |
| `firepro3d/elevation_scene.py` | Elevation projection + `ElevGridlineItem` (filtering, Z-overrides) |
| `firepro3d/constants.py` | Centralized grid constants (`GRIDLINE_BUBBLE_OFFSET_MM`, dash geometry, colors, `INFERENCE_TOL_PX`, `INFERENCE_GUIDE_COLOR`, `INFERENCE_GUIDE_DASH`, `INFERENCE_GLYPH_PX`) |
| `main.py` | Draw-tab ribbon "Gridline" button; default seed + post-seed undo-stack reset; "GUIDES" status-bar pill; F12 shortcut; `inference/alignment_guides` QSettings restore |

**Removed:** `firepro3d/grid_line.py` (legacy `GridLine`); `firepro3d/grid_lines_dialog.py` (modal dialog).

### Key API additions (§17)

| API | Location | Purpose |
|-----|----------|---------|
| `alignment_reference_points() -> list[ReferenceFeature]` | `GridlineItem` | Returns 4 inference features (2 endpoints + 2 bubble centres) for the alignment engine |
| `offset_copy(distance: float) -> GridlineItem` | `GridlineItem` | One parallel copy at signed perpendicular distance (mm) |
| `array_copies(spacing: float, count: int) -> list[GridlineItem]` | `GridlineItem` | N parallel copies at successive spacing multiples |
| `_is_template: bool` | `GridlineItem` | Flag for placement-template instance; restricts `get_properties()` to non-geometric rows |

## 15. Edge Cases & Error Handling

- **45° gridline classification:** `dy >= dx` classifies as vertical → number label. Consistent, documented.
- **Counter sync with mixed custom labels:** Labels like "X-1" that don't parse as numbers or letters are ignored by sync. Counter resumes from the highest parseable label.
- **Zero-length placement:** the placement press rejects a sub-0.5-mm span ("Gridline too short — skipped"); mutators floor `_length` at 1.0 mm.
- **Floating-point epsilon for cardinal test:** `1e-6` absolute tolerance on dx or dy for elevation filtering. A gridline at 89.9999° would fail the cardinal test and not appear in elevations.
- **Spacing pairing tolerance:** angle clustering uses a small fixed `EPS_ANGLE`. Non-parallel gridlines share no cluster → no spacing dimension between them.

## 16. Out of Scope

- Snap interaction rules (see `docs/specs/snapping-engine.md` §5)
- Paper space thin-lines rendering mode switching (see `docs/specs/paper-space.md` §9.2)
- Off-axis bubble **elbow/jog leader** + per-view leader independence (bubble *along-axis* offset is implemented — §5.6)
- Angled gridlines projecting into **elevation** views (section-view territory)
- On-canvas interactive **rotate** handle (angle lives in the Properties panel)
- Display-Manager **linetype** property (solid/dashed/center/…)
- Section view gridline projection (deferred to section view spec)
- Grid snap (regular spacing constraint independent of gridline objects)
- Display Manager category CRUD

## 17. On-Canvas Array & Offset

### 17.1 Overview

Two transient modes — `gridline_offset` and `gridline_array` — replicate a source gridline into parallel copies directly on canvas. Invoked from the gridline right-click entity menu ("Offset Gridline…" / "Array Gridlines…") via `_show_entity_context_menu`; falls back to `_build_plan_context_menu` when no item is under the cursor but a gridline is selected. The right-clicked (or selected) gridline is the source. Locked sources are allowed; copies are always unlocked.

### 17.2 Offset Mode (`gridline_offset`)

Creates **one** parallel copy at a cursor-driven or typed perpendicular distance + side. The cursor drives spacing and side live (perpendicular projection onto the source axis). Tab or any digit opens `_DynInput` with a single "Distance" field. Click/Enter commits; Esc cancels with no copy created.

### 17.3 Array Mode (`gridline_array`)

Creates **N** parallel copies at successive multiples of a signed spacing. Default count = 1. Live ghost preview in `drawForeground` (cosmetic outline — line + bubble circles; no preview scene-items). "Spacing ×Count" Dim HUD displayed live. Tab or any digit opens `_DynInput` with "Spacing" and "Count" fields. Click/Enter commits; Esc cancels.

### 17.4 Copy Geometry

Copies are **rigid parallel translations**: same `_angle_deg` and `_length`, `_origin` shifted perpendicular by `n × spacing` using the gridline's fixed-sign `_perpendicular_vector()` (§5.3). Inherited: bubble offsets, bubble visibility, display overrides. **Not inherited:** lock (copies always unlocked).

### 17.5 Labeling & Commit

Before building copies, `sync_grid_counters` runs on the existing gridlines so auto-labels continue the current sequence. Each copy receives a fresh sequential auto-label via `auto_label()`. After all copies are appended to `_gridlines`, `apply_duplicate_warnings` re-scans. The entire array/offset commit is **one** `push_undo_state()` — whole set = one undo step.

### 17.6 Serialization

Copies are ordinary `GridlineItem` instances. They serialize/round-trip via `GridlineItem.to_dict`/`from_dict` on both paths (`scene_io` + `_capture_network`). No `.fpd` schema change.

### 17.7 Placement Template

Entering `draw_gridline` mode emits `requestPropertyUpdate(_get_gridline_template())`. The template is an off-scene `GridlineItem` with `_is_template = True`; its `get_properties()` exposes only non-geometric rows (Bubble 1/2 Offset, Bubble 1/2 Visible, Locked). Placed gridlines adopt the template's bubble/lock settings. The template persists for the session; paste-mode ghost + inference participation is a filed follow-up.

### 17.8 Alignment Snapping (Inference)

During gridline placement (`draw_gridline`, both points) and endpoint grip-drag, the active point participates in the inference engine's H/V alignment guides. Reference features are supplied by `GridlineItem.alignment_reference_points()` (4 features: both endpoints + both bubble centres). Guide rendering, snap priority, and toggle details are governed by `docs/specs/inferred-dimension-driven-placement.md` (Rule A — see there for the full contract; this section only notes gridline participation).
