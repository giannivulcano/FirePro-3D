# Grid System Architecture — Design Spec

**Date:** 2026-04-10
**Complexity:** Large
**Status:** Implemented
**Source tasks:** TODO.md — "Spec session: grid system architecture"

## 1. Goal

Define the canonical grid system for FirePro3D: a single `GridlineItem` class with auto-numbered bubble labels, pull-tab grips, lock support, perpendicular repositioning, on-selection spacing dimensions, and a source-of-truth editing dialog. Gridlines are level-independent building datums that project into elevation views. The legacy `GridLine` class is removed.

## 2. Motivation

The grid system has two parallel implementations (`GridlineItem` in `gridline.py`, `GridLine` in `grid_line.py`) with overlapping but incomplete feature sets. Neither supports lock/unlock, visible grip handles, perpendicular repositioning, or interactive spacing adjustment. The dialog creates gridlines but cannot edit existing ones. This spec consolidates everything into one canonical class, absorbs missing features, and defines the full lifecycle from creation through elevation projection.

## 3. Architecture & Constraints

### 3.1 Canonical Class: `GridlineItem`

`GridlineItem` (`firepro3d/gridline.py`) is the single gridline implementation. `GridLine` (`firepro3d/grid_line.py`) is deprecated and removed.

### 3.2 Level Independence

Gridlines are building-wide vertical datums. They have no `level` field and appear in all plan views regardless of active level. The existing `level` field is removed from `GridlineItem`.

### 3.3 Coordinate System

All geometry stored in millimeters (project convention). Gridlines are defined by two endpoints (p1, p2) in scene coordinates. Orientation is derived from the p1→p2 delta, not stored as a separate field.

### 3.4 Angled Gridlines

Gridlines support arbitrary angles (not just cardinal). The angle is implicit in the p1/p2 geometry. Classification as "vertical" (dy >= dx) or "horizontal" (dy < dx) determines auto-labeling scheme and parallel-neighbor matching for spacing dimensions.

### 3.5 Cross-References

- **Snap engine:** Gridline snap participation is defined in `docs/specs/snapping-engine.md` §5. This spec does not redefine snap rules.
- **Paper space:** The thin-lines toggle and `paper_height_mm` rendering are defined in `docs/specs/paper-space.md` §9.2. This spec defines the `paper_height_mm` property; paper space owns the rendering mode switching.

## 4. Data Model

### 4.1 `GridlineItem` State

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `_p1`, `_p2` | `QPointF` | (from constructor) | Scene-coordinate endpoints (mm) |
| `_label_text` | `str` | auto-assigned | Shared by both bubbles |
| `_locked` | `bool` | `False` | Prevents grip drag, body drag, spacing edit |
| `_bubble1_visible` | `bool` | `True` | Per-end bubble toggle |
| `_bubble2_visible` | `bool` | `True` | Per-end bubble toggle |
| `_user_layer` | `str` | `"Default"` | Layer assignment |
| `_display_overrides` | `dict` | `{}` | Per-instance display overrides |
| `_display_scale` | `float` | `1.0` | Bubble scale factor (from Display Manager) |
| `_grid_color` | `QColor` | `#4488cc` | Line + bubble border color |
| `paper_height_mm` | `float` | `3.0` | Label height for paper space rendering |

**Removed fields:** `level` (gridlines are level-independent).

### 4.2 `GridBubble` (Child)

`QGraphicsEllipseItem` with `ItemIgnoresTransformations` — constant screen size during model-space editing. Two instances per gridline, positioned at p1 and p2.

- Centered label text (Consolas, bold, pixel-size scaled to bubble radius)
- Click on bubble selects parent gridline; Ctrl+Click toggles selection
- Duplicate-label warning: bubble border changes to orange (`#ff8800`) when label matches another gridline in the scene. Clears automatically when resolved.

### 4.3 Pull-Tab Grips (Child)

`QGraphicsRectItem` with `ItemIgnoresTransformations`. Two instances per gridline, positioned at endpoints, offset slightly outward along the line direction.

- Visible only when gridline is selected or hovered
- Semi-transparent fill (subtle affordance)
- Dragging a grip extends/shortens the gridline (§5.2)

### 4.4 Serialization Format

```json
{
    "p1": [x, y],
    "p2": [x, y],
    "label": "A",
    "locked": false,
    "bubble1_vis": true,
    "bubble2_vis": true,
    "user_layer": "Default",
    "paper_height_mm": 3.0,
    "display_overrides": {}
}
```

## 5. Movement & Interaction

### 5.1 Body Drag (Reposition)

Triggered by clicking the gridline body (not bubble, not grip) and dragging.

- Movement constrained to the perpendicular direction only. Mouse delta is projected onto the perpendicular vector; the parallel component is discarded.
- Lock-aware: no-op if `_locked`.
- Undo: single state push on mouse release.

### 5.2 Grip Drag (Extend/Shorten)

Triggered by clicking a pull-tab grip and dragging.

- Movement constrained along the line direction only. Mouse delta is projected onto the line direction vector; the perpendicular component is discarded.
- Lock-aware: no-op if `_locked`.
- Undo: single state push on mouse release.

### 5.3 Movement API

| Method | Constraint | Lock-aware |
|--------|-----------|------------|
| `apply_grip(index, new_pos)` | Along line direction only | Yes |
| `move_perpendicular(offset)` | Perpendicular to line direction only | Yes |
| `set_perpendicular_position(value)` | Absolute perpendicular coordinate | Yes |

### 5.4 On-Selection Spacing Dimensions

When one or more gridlines are selected, spacing dimensions appear between parallel gridlines using the existing dimensional constraint visual style.

**Single selection:** Up to 2 dimensions — one to the nearest parallel unselected neighbor on each side.

**Multi-selection:** Dimensions between all selected parallel gridlines (chain dimension), plus dimensions to the nearest unselected neighbor on each outer edge.

"Parallel" means same orientation classification (both vertical or both horizontal via the `dy >= dx` rule).

### 5.5 Double-Click Spacing Edit

Double-clicking a spacing dimension opens an inline text field on the dimension. The user enters a new spacing value in display units (via the existing numerical input handler with unit conversion).

- **Single selection:** The selected gridline moves perpendicular to satisfy the new spacing. The neighbor stays fixed.
- **Multi-selection:** All selected gridlines move as a rigid group, maintaining their relative spacing. The unselected anchor neighbor stays fixed.
- Lock-aware: edit rejected if the gridline that would move is locked.
- Undo: single state push.

### 5.6 Bubble Offset

Bubbles are always positioned at the endpoints. Independent bubble offset (dragging a bubble away from the endpoint with a leader line) is out of scope. Users can extend the gridline via grip drag to give bubbles more room.

## 6. Auto-Numbering

### 6.1 Labeling Scheme

- **Horizontal gridlines** (dy < dx): Numbers — 1, 2, 3, …
- **Vertical gridlines** (dy >= dx): Letters — A, B, C, …, Z, AA, AB, …, AZ, BA, …

Classification uses the `dy >= dx` test on the p1→p2 delta.

### 6.2 Global Counters

Module-level `_next_number: int` and `_next_letter_idx: int`. The `auto_label(p1, p2)` function classifies orientation and returns the next label from the appropriate counter.

### 6.3 Counter Sync

On any event that could create a mismatch between counter state and scene state, scan all existing `GridlineItem` instances and reset each counter to max+1:

- **File load** — after `from_dict()` restores all gridlines
- **Undo/redo** — after scene state is restored
- **Dialog accept** — after batch create/edit/delete completes

Sync logic:
1. Collect all existing labels, classify each as number or letter.
2. For numbers: parse to int, set counter to max+1.
3. For letters: convert to index (A=0, Z=25, AA=26, AB=27…), set counter to max+1.
4. Non-parseable labels (user-entered custom text like "X-1") are ignored by sync.

### 6.4 Duplicate Detection

After any label change (manual edit, auto-assign, dialog apply), scan for duplicates. Gridlines with duplicate labels display a visual warning:

- Bubble border color changes to orange (`#ff8800`)
- Warning is informational only — does not block any operation
- Clears automatically when the duplicate is resolved (rename or delete)

## 7. Grid Lines Dialog

### 7.1 Overview

Modal dialog with two tabs (Vertical / Horizontal). Acts as a source-of-truth editor for the grid array — supports creating new gridlines, editing existing gridlines in-place, and deleting gridlines.

### 7.2 Table Columns

| Column | Type | Notes |
|--------|------|-------|
| Label | String | Editable, auto-incremented on new rows |
| Offset | Numeric | Perpendicular position, display units |
| Spacing | Numeric | Derived from offset delta to previous row |
| Length | Numeric | Gridline extent, display units |
| Angle° | Numeric | 0–90° off cardinal |
| *(hidden)* | `GridlineItem` ref | `None` for new rows |

### 7.3 Numerical Input

All dimension fields (Offset, Spacing, Length, Default Length, Quick Fill Spacing) are plain `QLineEdit` widgets — not spinboxes. Values display in formatted units via `ScaleManager.format_length()` (e.g., `24'-0"` for imperial, `7315.2 mm` for metric). User input is parsed via `ScaleManager.parse_dimension()`, which accepts any unit format (ft-in, mm, m, bare numbers). This matches the pipe properties and other dimension input fields in the application.

### 7.3.1 Column Sorting

Clicking a column header sorts the table by that column, toggling between ascending and descending. Dimension columns sort numerically (by parsed mm value), not lexicographically, so `48'-0"` sorts after `24'-0"` correctly. The Spacing column is recalculated after sorting since it is relative to the previous row.

### 7.4 Offset ↔ Spacing Sync

Editing offset recalculates spacing from the previous row. Editing spacing recalculates offset from the previous row's offset + new spacing. Bidirectional.

### 7.5 Quick Fill

Count + Spacing + Generate button fills the table with evenly-spaced rows. Auto-labels from the Start Label field using the selected scheme (Numbers or Letters). Replaces existing rows (clears table first).

### 7.5.1 Add Row Defaults

Clicking "+" adds a row that continues the spacing pattern:
- **2+ existing rows:** New row offset = last offset + (last offset − second-to-last offset).
- **1 existing row:** New row offset = last offset + Quick Fill spacing value.
- **Empty table:** Offset = 0.

### 7.6 Population from Scene

On dialog open:
1. Scan `Model_Space._gridlines` for all existing gridlines.
2. Classify each as H or V using the `dy >= dx` rule.
3. Populate the appropriate tab, sorted by perpendicular offset.
4. Each row stores a hidden reference to its source `GridlineItem`.
5. Angled gridlines (not exactly 0° or 90°) go to the closest tab with their angle preserved.

### 7.7 Reconciliation on Accept

Diff-based reconciliation using identity matching (hidden `GridlineItem` reference, not label). Single undo step wraps the entire operation.

1. **Modified rows** (hidden ref is not `None`, values changed) — update `GridlineItem` in-place: reposition endpoints, relabel, adjust length/angle.
2. **New rows** (hidden ref is `None`) — create new `GridlineItem`, add to scene.
3. **Deleted rows** (source `GridlineItem` exists in scene but no matching row in table) — remove from scene.
4. **Confirmation prompt** if any deletions are pending: "N gridline(s) will be deleted. Continue?"
5. After apply: sync auto-numbering counters (§6.3).

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

The `from_dict()` loader handles both old (`GridLine`) and current (`GridlineItem`) formats:

| Old format (`GridLine`) | New format (`GridlineItem`) | Migration |
|------------------------|---------------------------|-----------|
| `"type": "grid_line"` present | No `"type"` key | Detect by presence of `"type"` key |
| `"axis": "x"/"y"` | (removed) | Ignored — orientation derived from p1/p2 |
| `"locked": true` | `"locked": true` | Passes through |
| `"bubble_start"/"bubble_end"` | `"bubble1_vis"/"bubble2_vis"` | Key rename |
| No `"user_layer"` | `"user_layer": "Default"` | Default applied |
| No `"paper_height_mm"` | `"paper_height_mm": 3.0` | Default applied |

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

### 10.2 Paper Space Bridge

Per `docs/specs/paper-space.md` §9.2:

- **Thin-lines ON (default):** Bubbles use `ItemIgnoresTransformations` — fixed screen size, always readable.
- **Thin-lines OFF:** Bubbles render at `paper_height_mm` in model units — WYSIWYG print preview.
- **Sheet view rendering:** Bubbles always render at `paper_height_mm` × sheet view scale factor.

The `paper_height_mm` property on `GridlineItem` is the bridge between the two systems.

## 11. Design Decisions

### 11.1 Single canonical class

**Chosen:** Consolidate into `GridlineItem`, remove `GridLine`.
**Rationale:** Two parallel implementations with overlapping features adds maintenance burden without value. `GridlineItem` is the active implementation; missing features (lock, grips, perpendicular move) are absorbed from `GridLine`.

### 11.2 Edit-existing dialog via diff-based reconciliation

**Considered:**
- **(A) Diff-based reconciliation** — dialog tracks identity, computes changeset on accept. ✓ Chosen.
- **(B) Replace-all** — delete and recreate all gridlines. Breaks references (elevation overrides, snap caches, undo).
- **(C) Create-only dialog** — smaller scope but doesn't meet requirements.

**Rationale:** Identity tracking is straightforward (hidden column stores Python object reference) and preserves all external references to `GridlineItem` instances.

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

### 11.8 Bubbles always at endpoints (no offset)

**Chosen:** No bubble offset / leader lines.
**Rationale:** Pull-tab grips already let users extend gridlines to space bubbles. Bubble offset adds per-bubble grip points, leader rendering, and serialization complexity for a polish feature. Deferred as follow-up.

### 11.9 Counter sync (no gap-filling)

**Chosen:** Sync to max+1, do not fill gaps.
**Rationale:** Gap-filling risks confusing label sequences. Users can manually relabel to fill gaps if desired.

### 11.10 Duplicate labels — warn but allow

**Chosen:** Visual warning (orange bubble border), no enforcement.
**Rationale:** Strict enforcement creates frustrating UX during batch relabeling (rename A→temp before renaming B→A). Duplicates are almost always mistakes, so the visual cue is sufficient.

## 12. Acceptance Criteria

- [ ] `GridlineItem` is the single canonical gridline class
- [ ] `grid_line.py` removed; all imports cleaned up
- [ ] Lock/unlock prevents grip drag, body drag, and spacing edit
- [ ] Visible pull-tab grips at endpoints (on selection/hover)
- [ ] Perpendicular body drag with directional constraint
- [ ] `ItemIgnoresTransformations` on bubbles with `paper_height_mm` for paper space bridge
- [ ] Angled gridlines supported as first-class (arbitrary p1/p2)
- [ ] Elevation views show only exactly-cardinal gridlines (perpendicular to viewing plane)
- [ ] Auto-numbering counters sync to max existing label on load/undo/dialog accept
- [ ] Duplicate labels produce visual warning (orange bubble border), not enforcement
- [ ] Grip drag constrained along line direction; body drag constrained perpendicular
- [ ] Bubbles always at endpoints (no independent offset)
- [ ] Dialog supports create, edit-existing (identity-matched), and delete with confirmation
- [ ] Dialog uses existing numerical input handler with display-unit conversion (no hardcoded inches)
- [ ] Gridlines are level-independent (visible on all plan levels, `level` field removed)
- [ ] Elevation Z-extent defaults to full building height; per-view grip-editable overrides stored on elevation scene
- [ ] Single "Grid Line" display manager category
- [ ] Undo: dialog accept = one step; drag operations = one step on mouse release
- [ ] On-selection spacing dimensions to parallel neighbors (single) or between selected (multi)
- [ ] Double-click spacing edit: selected gridline(s) move, neighbor stays fixed; multi-select moves as rigid group preserving relative spacing
- [ ] Serialization migration handles old `GridLine` format
- [ ] Snap interaction deferred to snap spec (cross-reference only)

## Alignment Constraint Participation

Gridlines can be both **reference** and **target** for the Align tool:

- **As reference:** The gridline's single line segment (p1→p2) serves as the reference edge. Other items align to it.
- **As target:** The Align tool calls `set_perpendicular_position()` to move the gridline. This respects the existing `_locked` flag — locked gridlines cannot be aligned (status bar warning: "Gridline 'X' is locked").
- **Edge extraction:** A gridline exposes exactly one linear segment (p1→p2).
- **Lock constraint:** When locked via Align, an `AlignmentConstraint` is stored referencing the gridline. The padlock icon appears at the alignment point. Moving the reference triggers `set_perpendicular_position()` via the constraint solver.

No structural changes to `GridlineItem` are needed. The existing `move_perpendicular()` and `set_perpendicular_position()` APIs are sufficient.

## 13. Verification Checklist

- [ ] All acceptance criteria met
- [ ] Unit tests pass: auto-numbering, serialization round-trip, migration, movement constraints, elevation filtering, duplicate detection
- [ ] Integration tests pass: dialog CRUD lifecycle, elevation projection, spacing dimensions, lock enforcement
- [ ] No regressions: existing gridline creation (2-click), existing elevation view rendering, existing snap behavior with gridlines
- [ ] `grid_line.py` fully removed, no dead imports
- [ ] Existing project files with old-format gridlines load correctly
- [ ] Align tool can use gridline as reference (other items align to it)
- [ ] Align tool can use gridline as target (gridline moves to match reference)
- [ ] Locked gridlines rejected by Align tool with status bar warning
- [ ] AlignmentConstraint lock works with gridline as target

## 14. Existing Code Context

| File | LOC | Role | Action |
|------|-----|------|--------|
| `firepro3d/gridline.py` | ~354 | Active `GridlineItem` + `GridBubble` | Modify (canonical) |
| `firepro3d/grid_line.py` | ~302 | Legacy `GridLine` | Remove |
| `firepro3d/grid_lines_dialog.py` | ~473 | Batch creation dialog | Modify (add edit-existing) |
| `firepro3d/elevation_scene.py` | ~1233 | Elevation projection + `ElevGridlineItem` | Modify (filtering, Z-overrides) |
| `firepro3d/model_space.py` | (large) | Scene management, gridline storage, placement | Modify (body drag, spacing dimensions) |
| `firepro3d/constants.py` | — | Centralized constants | Modify (add grid constants if needed) |

## 15. Edge Cases & Error Handling

- **45° gridline classification:** `dy >= dx` classifies as vertical → letters. Consistent, documented.
- **Counter sync with mixed custom labels:** Labels like "X-1" that don't parse as numbers or letters are ignored by sync. Counter resumes from the highest parseable label.
- **Empty scene dialog:** Dialog opens with empty tables. Quick Fill works normally. No reconciliation deletions (nothing to delete).
- **All gridlines deleted via dialog:** Confirmation prompt, then all removed. Counters reset to 1 / A.
- **Floating-point epsilon for cardinal test:** `1e-6` absolute tolerance on dx or dy for elevation filtering. A gridline at 89.9999° would fail the cardinal test and not appear in elevations.
- **Perpendicular neighbor search for spacing:** If no parallel neighbor exists on one side, no dimension shown for that side. Two isolated gridlines at different angles show no spacing.

## 16. Out of Scope

- Snap interaction rules (see `docs/specs/snapping-engine.md` §5)
- Paper space thin-lines rendering mode switching (see `docs/specs/paper-space.md` §9.2)
- Bubble offset with leader lines (potential follow-up)
- Section view gridline projection (deferred to section view spec)
- Grid snap (regular spacing constraint independent of gridline objects)
- Display Manager category CRUD
