---
status: partial
last-verified: 2026-08-14
verified-commit: de2b12a
applies-to:
  - firepro3d/inference_engine.py
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/gridline.py
  - firepro3d/constants.py
source-tasks:
  - "TODO.md — gridline follow-up: placement alignment snapping"
---

# Inferred / Dimension-Driven Placement Specification

**Date:** 2026-04-28 (first slice built 2026-08-14)
**Depends on:** [Snapping Engine Spec](snapping-engine.md) (§2.3 flagged this as next-priority subsystem)

---

## 0. First Implemented Slice (2026-08-14)

Gridlines are the **first client** of the inference engine. The built slice delivers:

**BUILT (as of 2026-08-14, commit de2b12a):**
- `InferenceEngine` core in `firepro3d/inference_engine.py` — entity-agnostic (no Qt, no firepro3d imports). Dataclasses `ReferenceFeature(kind, x, y, source_id, label)`, `Guide(orientation, coord, ref)`, `InferenceResult(snapped, guides, priority)`. `InferenceEngine.resolve(cursor, refs, tol) -> InferenceResult`.
- `Model_Space.get_effective_position` integration hook — consults the engine only after OSNAP/underlay miss, only when `_inference_enabled` and `_inference_active_item` is set. Active item is a `_PlacementSentinel` during `draw_gridline` placement (both points), or the dragged `GridlineItem` during endpoint grip-drag.
- `_collect_alignment_refs` — iterates `self._gridlines` only (not the full scene), calling duck-typed `alignment_reference_points()`, self-excluding by `source_id`.
- `GridlineItem.alignment_reference_points()` — returns 4 `ReferenceFeature`s: both endpoints and both bubble centres.
- H/V alignment guides only; priority hierarchy: `OSNAP > guide-intersection > single-guide > free`.
- `model_view.drawForeground` guide rendering — cyan dashed cosmetic line (`INFERENCE_GUIDE_COLOR`, `INFERENCE_GUIDE_DASH`) + crosshair glyph (`INFERENCE_GLYPH_PX`) at the reference point; no scene-items; reads `scene._inference_result`; auto-clears on empty result.
- Single **alignment-guides toggle**: "Inference" tab in the snap settings dialog + "GUIDES" status-bar pill + F12 shortcut; `QSettings` key `inference/alignment_guides` (default `True`), restored on startup.
- Tolerance `INFERENCE_TOL_PX` = 65 px — wider than OSNAP (40 px), as specified (weak snap, visual hint).

**STILL PROPOSAL (below):** wall-proximity, extension-line, and equal-spacing guide types; node/sprinkler/wall reference sources; other placement tools (pipe, wall, …) and body-drag as clients; per-guide distance labels; Selection Dimensions (§8); Dynamic Input (§4) as a general capability (`_DynInput` partially exists for gridline offset/array and line-tool placement); the full three-toggle + master-key system (§10).

---

## Table of Contents

1. [Goal](#1-goal)
2. [Motivation](#2-motivation)
3. [Architecture](#3-architecture)
4. [Dynamic Input](#4-dynamic-input)
5. [Alignment Guides](#5-alignment-guides)
6. [Guide Snap Integration](#6-guide-snap-integration)
7. [Equal Spacing Inference](#7-equal-spacing-inference)
8. [Selection Dimensions](#8-selection-dimensions)
9. [Performance](#9-performance)
10. [Toggle System](#10-toggle-system)
11. [Testing Strategy](#11-testing-strategy)
12. [Acceptance Criteria](#12-acceptance-criteria)
13. [Verification Checklist](#13-verification-checklist)

---

## 1. Goal

Define an inferred placement and dimension-driven editing subsystem for FirePro3D: floating dimension input during placement, automatic alignment guides with weak-snap behavior, equal spacing inference, and post-placement selection dimensions with inline editing.

## 2. Motivation

Without this system, precise placement requires pre-existing geometry to snap to. Users cannot:

- Type an exact pipe length during drawing
- See alignment relationships to other items as they draw
- Maintain equal sprinkler spacing without manual measurement
- Edit node positions by typing exact distances to neighbors

These are the capabilities that make Revit feel "smart" during drafting. OSNAP handles "snap to what exists" — this system handles "place precisely where nothing exists yet."

### 2.1 Three Capabilities

1. **Dynamic Input** — floating dimension fields at cursor during placement; type to override cursor position
2. **Alignment Guides** — automatic inference lines showing alignment, wall proximity, extension, and equal spacing relationships
3. **Selection Dimensions** — post-placement editing via temporary dimensions on selected nodes

These share visual language (temporary dimensions), input mechanism (type a value to override), and unit-conversion pipeline (ScaleManager). They are designed as a unified subsystem with independent toggles.

## 3. Architecture

### 3.1 Module Map

```
┌──────────────────────────────────────────────────────┐
│  InferenceEngine (central coordinator)               │
│  ├─ DynamicInput (floating length field at cursor)   │
│  ├─ AlignmentGuides (dashed inference lines)         │
│  │   ├─ H/V alignment (blue)                        │
│  │   ├─ Wall proximity (orange)                      │
│  │   ├─ Extension lines (blue)                       │
│  │   └─ Equal spacing (green)                        │
│  ├─ SelectionDimensions (post-placement editing)     │
│  └─ GuideSnap (weak snap points from guides)         │
├──────────────────────────────────────────────────────┤
│  Integrations:                                       │
│  ├─ SnapEngine (priority below OSNAP)                │
│  ├─ ScaleManager (unit display/parsing)              │
│  ├─ 45° constraint (angle locked, non-overridable)   │
│  └─ Model_Space (placement modes, drag handling)     │
└──────────────────────────────────────────────────────┘
```

### 3.2 Toggle System Overview

| Toggle | Controls | Default |
|---|---|---|
| Dynamic Input | Floating length/angle fields at cursor | On |
| Alignment Guides | Inference lines during placement and drag | On |
| Spacing Inference | Equal spacing detection and guides | On |

Master key (e.g. F12) toggles all three simultaneously.

### 3.3 Active Modes

All placement modes (pipe, sprinkler, wall, construction geometry) and drag repositioning of existing items.

---

## 4. Dynamic Input **[PROPOSAL]**

> `_DynInput` partially exists — it is built for gridline offset/array and the line-tool placement, but as a general per-placement-mode capability (pipe, wall, sprinkler, arc, …) this section is unbuilt proposal.

### 4.1 Activation

Appears after the first click in any placement mode (pipe, wall, line, circle, arc, rectangle). Not shown before first click — no reference point exists. Toggle-able independently.

### 4.2 Visual

Floating input widget near the cursor (offset to avoid occluding the snap marker):

| Field | Content | Editable | Shown for |
|---|---|---|---|
| Length | Distance from start point in display units | Yes — type to override | Pipe, wall, line |
| Angle | Current angle from reference | Read-only (display only) | Pipe, wall, line |
| Radius | Distance from center | Yes — type to override | Circle, arc |
| Width × Height | Dimensions from corner | Yes — type to override | Rectangle |

For pipes: angle field shows current 45°-constrained value. **Non-overridable** — fitting assignment depends on 45° increment angles. The dynamic input for pipes is effectively a single-field length input with angle shown as read-only context.

### 4.3 Input Behavior

| Action | Result |
|---|---|
| Move cursor | Length/angle update live from cursor position |
| Type digits | Length field captures keystrokes immediately (no click needed to focus) |
| Enter or click | Confirm placement at the typed length (or cursor length if nothing typed) |
| Escape | Cancel current placement |
| Tab | Cycle between editable fields (radius → sweep for arc, width → height for rectangle). No-op for pipe (single editable field). |

### 4.4 Unit Handling

- Display: `ScaleManager.format_length()` for current display unit
- Input: `ScaleManager.parse_dimension()` — accepts bare numbers (interpreted as current unit) or explicit units ("10'", "3048mm")
- Same pipeline as all existing dimension input (`format_length`/`parse_dimension` pattern)

### 4.5 Interaction with OSNAP

If OSNAP finds a snap point, the dynamic input fields update to show the snapped distance/angle (not the raw cursor distance). If the user then types a value, it overrides the snap — typed input always wins over snap position.

### 4.6 Interaction with 45° Constraint

For pipes: the angle is locked to the nearest 45° increment at all times. Typing a length extends the pipe at the currently displayed constrained angle. The user cannot type an angle. This ensures every placed pipe has a valid fitting type.

---

## 5. Alignment Guides

### 5.1 Guide Types

**H/V alignment from gridline references — [BUILT]**. All other guide types — [PROPOSAL]:

| Type | Trigger | Visual | Color | Status |
|---|---|---|---|---|
| H/V Alignment | Cursor X or Y matches a gridline endpoint or bubble centre within tolerance | Dashed vertical or horizontal line through cursor and aligned item | Cyan (`INFERENCE_GUIDE_COLOR`) | **BUILT** (gridline refs only) |
| Wall Parallel | Cursor position projects onto a wall face line within tolerance | Dashed line parallel to wall face, through cursor | Orange | PROPOSAL |
| Wall Perpendicular | Cursor-to-wall perpendicular distance is within a threshold | Dashed line perpendicular from wall face to cursor, with distance label | Orange | PROPOSAL |
| Extension Line | Cursor aligns with the direction of an existing pipe endpoint or wall face edge | Dashed line extending from the endpoint through cursor | Blue | PROPOSAL |
| Equal Spacing | Distance from cursor to nearest item matches an existing spacing pattern (2+ items) | Dashed line at the inferred position, with spacing dimension label | Green | PROPOSAL |

### 5.2 Active During **[PARTIAL — gridlines only; others PROPOSAL]**

**BUILT:** `draw_gridline` placement (both points) and gridline endpoint grip-drag. **PROPOSAL:** all other placement modes (pipe, sprinkler, wall, construction geometry) and drag repositioning of other entity types.

### 5.3 Detection Algorithm **[PARTIAL]**

**As built (gridline slice):** `_collect_alignment_refs` iterates `self._gridlines` directly (the provider list is small, so no spatial-index or cursor-move cache is needed for this slice). Providers are duck-typed (`alignment_reference_points()`); future wall/pipe/node providers slot in by iterating their own collections, keeping the per-frame cost bounded without a global scene scan. The as-specced `scene.items(rect)` path and 2px cursor-move cache are not needed for this slice and are not built.

**PROPOSAL (for future multi-entity providers, if the provider list grows large):** spatial filter via `scene.items(rect)` + per-provider type filter + cursor-move cache threshold (§9.5).

### 5.4 Tolerance **[BUILT]**

`INFERENCE_TOL_PX` = 65 px — separate from and wider than OSNAP (`SNAP_TOLERANCE_PX` = 40 px); implemented in `constants.py`.

### 5.5 Dimension Labels **[PROPOSAL]**

Per-guide distance labels are unbuilt. The first slice emits no distance label on guides.

### 5.6 Wall Clearance Scope **[PROPOSAL]**

Wall distance guides show for all walls within `2 × max_coverage_spacing` of cursor. In corners, multiple wall distance guides appear simultaneously (one per nearby wall). This supports NFPA 13 wall clearance verification during sprinkler placement.

---

## 6. Guide Snap Integration **[BUILT]**

### 6.1 Priority Hierarchy

Snap candidates are evaluated in priority order:

| Priority | Source | Example |
|---|---|---|
| 1 (highest) | OSNAP | Endpoint, midpoint, intersection of existing geometry |
| 2 | Guide intersection | Two guides crossing (e.g. H-align + V-align) |
| 3 | Single guide | Cursor projected onto alignment line |
| 4 (lowest) | Free cursor | No snap, raw cursor position |

### 6.2 Guide Intersection Snap

When two or more guides intersect, the intersection point becomes a snap candidate at priority 2. This is the most powerful inferred position — "aligned with A horizontally AND B vertically."

Detection: for each pair of active guides, compute line-line intersection. If the intersection falls within the viewport, register it as a snap candidate.

### 6.3 Single Guide Snap

Each active guide contributes a snap point: the cursor projected onto the guide line (nearest point on the guide to the raw cursor position). Priority 3 — only used when no OSNAP or guide intersection is available.

### 6.4 Snap Marker **[PARTIAL]**

The crosshair glyph (`INFERENCE_GLYPH_PX`) renders at the reference point being aligned to. A distinct snap-point shape (e.g. diamond) separate from the OSNAP markers is **PROPOSAL**.

---

## 7. Equal Spacing Inference **[PROPOSAL]**

### 7.1 Pattern Detection

Minimum pattern: 2 existing items define a spacing. The system detects spacing patterns among:
- Nodes on the same pipe run (connected via pipes)
- Sprinklers on the same branch line
- Parallel pipe runs at consistent separation

### 7.2 Inference Algorithm

1. Find items of the same type near the cursor (spatial + type filter)
2. Compute spacings between adjacent pairs
3. If 2+ items exist with consistent spacing (within tolerance), infer the pattern
4. Project the next repetition point from the last item in the pattern
5. If cursor is near the projected point, activate the equal spacing guide

### 7.3 Visual

Green dashed line at the inferred position, with dimension label showing the spacing value. Small tick marks on the guide indicate the pattern positions (existing items + the proposed next position).

### 7.4 Multiple Patterns

If multiple spacing patterns are detectable (e.g. S-spacing along a branch AND L-spacing between branches), show up to 2 spacing guides simultaneously. Nearest pattern takes visual priority.

---

## 8. Selection Dimensions **[PROPOSAL]**

### 8.1 Scope

Nodes and sprinklers. When selected, temporary dimension lines appear showing distances to adjacent nodes connected via pipes. Same UX pattern as gridline on-selection spacing dimensions.

### 8.2 Visual

- Thin dimension lines with witness lines connecting to adjacent nodes
- Distance label at midpoint of the dimension line
- Formatted via `ScaleManager.format_length()`
- Same visual style as gridline spacing dimensions (existing convention)

### 8.3 Editing

Double-click a dimension label → inline text field opens on the dimension. User types a new spacing value in display units (parsed via `parse_dimension()`).

**On confirm (Enter):**
- The selected node slides along the pipe direction to satisfy the new spacing
- Adjacent pipe segments stretch/shrink accordingly
- Downstream nodes stay fixed (only the edited segment changes length)
- Fittings auto-update on affected nodes

**On cancel (Escape):** revert to original position.

### 8.4 Multi-Selection

When multiple nodes are selected:
- Dimensions shown between consecutive selected nodes AND between selection boundary and nearest unselected neighbor
- Editing a dimension moves all selected nodes as a rigid group (preserving relative spacing within the selection)
- Unselected anchor neighbor stays fixed

### 8.5 Constraints

- Node can only slide along pipe direction (no free 2D movement via dimension edit)
- Minimum pipe length enforced (node cannot be pushed past adjacent nodes)
- If node has pipes in multiple directions, the dimension edit applies to the pipe segment that owns the edited dimension

---

## 9. Performance

### 9.1 Scan Budget

The inference engine runs on every mouse move during active placement/drag. Target: complete scan + render in < 5ms to maintain 60fps responsiveness.

### 9.2 Collector strategy (as-built for gridline slice) **[BUILT]**

For the gridline slice, `_collect_alignment_refs` iterates `self._gridlines` directly — the provider list is small enough that no spatial index or cursor-move cache is needed. The engine itself is generic; future providers (walls, pipes, nodes) slot in by iterating their own collections, keeping per-frame cost bounded without a global scene traversal.

### 9.3 Spatial-index path (for future large-provider scenarios) **[PROPOSAL]**

If the aggregate provider list grows large (e.g. node/sprinkler providers over dense scenes), filter via `scene.items(rect)` spatial index before dispatching to `alignment_reference_points()`. Type-filter per guide type as below; no O(n²) iteration of the full scene.

| Guide type | Scan items |
|---|---|
| H/V alignment | Nodes with sprinklers, plain nodes on calc paths |
| Wall proximity | WallSegment items |
| Extension | Pipe endpoints (node.pipes), wall face edges |
| Equal spacing | Nodes on connected pipe runs |

### 9.4 Display Cap **[PROPOSAL]**

Maximum 6 guides visible simultaneously. When more candidates exist, rank by proximity to cursor and show the nearest. Guide intersections count as 1 toward the cap (not 2).

### 9.5 Cursor-move cache **[PROPOSAL]**

Cache the spatial query results per frame. If the cursor hasn't moved beyond a threshold (e.g. 2px), reuse the previous guide set without recomputing. Not needed for the gridline slice.

---

## 10. Toggle System

### 10.1 Alignment Guides toggle **[BUILT]**

Single "Alignment Guides" toggle — "Inference" tab in the snap settings dialog, "GUIDES" status-bar pill, F12 shortcut. `QSettings` key `inference/alignment_guides` (default `True`), restored on startup. Toggling off immediately silences guides and guide-snap; OSNAP/free cursor unaffected.

### 10.2 Three Independent Toggles + Master Key **[PROPOSAL]**

The full three-toggle + master system below is unbuilt. F12 currently maps to the single alignment-guides toggle (§10.1).

| Toggle | Key | Scope | Default |
|---|---|---|---|
| Dynamic Input | TBD | Floating length/angle fields | On |
| Alignment Guides | F12 (built, §10.1) | Inference lines during placement/drag | On |
| Spacing Inference | TBD | Equal spacing detection | On |

Master key toggles all three simultaneously. If any are on, master-off turns all off. If all are off, master-on restores previous individual states.

### 10.3 Status Bar **[PARTIAL]**

"GUIDES" pill is built (§10.1). Multiple-state pill showing Dynamic Input + Spacing Inference state is PROPOSAL.

### 10.4 Persistence **[BUILT for alignment-guides; PROPOSAL for the other two]**

`inference/alignment_guides` persisted to `QSettings` on toggle and restored in `MainWindow.restore_settings`. Same pattern as the OSNAP per-type toggles; see `docs/specs/osnap-toolbar.md`.

---

## 11. Testing Strategy

### 11.1 Dynamic Input

| Test | Assertion |
|---|---|
| Length parsing | "10'" → 3048mm, "3048mm" → 3048mm, "10" (bare, imperial mode) → correct conversion |
| Typed length overrides cursor | Type "5'" during pipe placement → pipe length exactly 5' regardless of cursor position |
| Angle display | Pipe at 45° snap shows "45°" in read-only angle field |
| Enter confirms | Typed length + Enter → placement at exact length |
| Escape cancels | Escape during typed input → no placement, field clears |
| Tab cycles fields | Arc: Tab moves focus from radius to sweep angle |

### 11.2 Alignment Guides

| Test | Assertion |
|---|---|
| H/V detection | Cursor at same Y as existing node (within tolerance) → horizontal guide fires |
| Wall perpendicular | Cursor 3' from wall → orange guide with "3'-0"" label |
| Extension line | Cursor along pipe direction from endpoint → blue extension guide |
| Tolerance boundary | Cursor 1px outside tolerance → no guide. 1px inside → guide fires |
| Display cap | 8 potential guides → only 6 nearest shown |
| Multi-wall corner | Cursor near corner of two walls → two orange guides showing distance to each wall |

### 11.3 Guide Snap

| Test | Assertion |
|---|---|
| OSNAP wins over guide | OSNAP endpoint and guide alignment both in range → OSNAP snap point used |
| Guide intersection wins over single guide | Two guides crossing near cursor → snap to intersection, not to individual guide |
| Single guide catches cursor | No OSNAP nearby, one guide active → cursor snaps to guide |
| No guides, no OSNAP | Cursor at raw position |

### 11.4 Equal Spacing

| Test | Assertion |
|---|---|
| 2-item pattern | Two sprinklers 10' apart → cursor near 10' from second → green guide at projected position |
| Pattern tolerance | Sprinklers at 10' and 10'-2" → pattern detected (within tolerance) |
| No pattern | Sprinklers at 10' and 7' → no equal spacing guide |
| Multiple patterns | S-spacing and L-spacing both detectable → up to 2 spacing guides shown |

### 11.5 Selection Dimensions

| Test | Assertion |
|---|---|
| Select node → dimensions appear | Selecting a pipe-connected node shows distance to adjacent nodes |
| Edit dimension → node slides | Double-click, type "8'", Enter → node repositions to 8' from neighbor along pipe direction |
| Multi-select rigid move | Select 2 nodes, edit outer dimension → both move together, relative spacing preserved |
| Minimum length | Cannot edit dimension to push node past adjacent node |
| Deselect → dimensions disappear | Clicking away removes temporary dimensions |

---

## 12. Acceptance Criteria

1. User can type an exact pipe length during placement via floating input field and the pipe is placed at that precise length.
2. Angle field is read-only for pipes — 45° constraint is non-overridable.
3. Dynamic input works for all placement tools: pipe, wall, line, circle, arc, rectangle.
4. Alignment guides appear during placement and drag showing H/V alignment, wall proximity, extension lines, and equal spacing with color coding (blue, orange, green).
5. Guide snap produces snap points at guide lines (priority 3) and guide intersections (priority 2), both below OSNAP (priority 1).
6. Equal spacing inference detects patterns from 2+ items and offers the next repetition.
7. Selecting a node shows temporary dimensions to adjacent connected nodes; double-clicking a dimension allows inline editing that repositions the node along the pipe.
8. Multi-select dimension editing moves selected nodes as a rigid group.
9. All dimension display and input uses ScaleManager for unit conversion.
10. Performance: guide computation completes within 5ms per frame with max 6 visible guides.
11. Three independent toggles + master key, persisted to QSettings, reflected in status bar.

## 13. Verification Checklist

- [ ] Dynamic input appears after first click in all placement modes (pipe, wall, line, circle, arc, rectangle)
- [ ] Length field accepts typed input; Enter confirms at typed length
- [ ] Angle field is read-only for pipes (45° constraint non-overridable)
- [ ] Tab cycles between editable fields (radius/sweep for arc, width/height for rectangle)
- [ ] H/V alignment guides fire when cursor aligns with existing node X or Y
- [ ] Wall perpendicular guides show distance to nearby walls (within 2× max coverage spacing)
- [ ] Wall parallel guides fire when cursor aligns with wall face direction
- [ ] Extension guides fire along pipe endpoint and wall face directions
- [ ] Equal spacing guides fire with 2+ item pattern (green dashed line + spacing label)
- [ ] Guide intersections produce snap points at priority 2 (above single guide, below OSNAP)
- [ ] OSNAP (priority 1) always wins over guide snap
- [ ] Guide snap points use distinct marker shape (diamond) from OSNAP markers
- [ ] Max 6 guides visible simultaneously
- [ ] Color coding: blue (alignment/extension), green (spacing), orange (wall proximity)
- [ ] Selection dimensions appear on node select, showing distances to adjacent pipe-connected nodes
- [ ] Double-click dimension → inline edit → node slides along pipe direction
- [ ] Multi-select dimension edit moves selection as rigid group preserving relative spacing
- [ ] Downstream nodes stay fixed during dimension edit (only edited segment changes)
- [ ] Three toggles (dynamic input, guides, spacing) + master key, persisted to QSettings
- [ ] Status bar shows toggle states alongside OSNAP indicator (F3 pill)
- [ ] Guide computation < 5ms per frame; spatial + type filtering; 2px cursor cache threshold
