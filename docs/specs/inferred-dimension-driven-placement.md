---
status: partial
last-verified: 2026-08-25
verified-commit: eead762
applies-to:
  - firepro3d/inference_engine.py
  - firepro3d/dynamic_input.py
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/gridline.py
  - firepro3d/wall.py
  - firepro3d/construction_geometry.py
  - firepro3d/constants.py
source-tasks:
  - "TODO.md — gridline follow-up: placement alignment snapping"
  - "docs/superpowers/plans/2026-08-16-dynamic-input-hud.md — §4 rewrite (T22)"
  - "docs/superpowers/specs/2026-08-20-placement-ux-overhaul-design.md — arc/rect variants + ghost-on-commit"
  - "docs/superpowers/specs/2026-08-24-wall-placement-workflow-design.md — wall as HUD + inference client"
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

**BUILT (extended 2026-08-14, commit 41ed103):**
- **Move/paste as inference clients.** Both pick points of the AutoCAD-style move/copy flow (`_press_paste_move`) run OSNAP + alignment inference (`_inference_active_item` set for `paste`/`move` in `set_mode`). **Move self-excludes the moving gridlines** from the reference set via `_inference_exclude_ids` (honored in `_collect_alignment_refs`), so a mover never aligns to its own current position; paste excludes nothing. A cosmetic scene-coord **silhouette ghost** of the affected geometry rides the cursor (owned by `grid-system.md §5.7`-adjacent move/paste sections; rendered in `Model_View.drawForeground` block 8).
- **Dynamic Input HUD (§4) — shipped 2026-08-19.** The modal `_DynInput` was
  replaced by the on-canvas `DynamicInputHud` (`dynamic_input.py`), organised by
  geometric primitive, live for the whole placement (readout ⇄ editor). Built
  clients: `draw_line`, `draw_gridline`, `polyline`, `draw_rectangle`,
  `draw_circle`, `move`, `gridline_offset`, `gridline_array`. Type-to-seed and
  Tab both engage it.

**BUILT (Placement-UX Overhaul, 2026-08-21, commit 9b0f285):**
- **Arc as a step-aware Dynamic Input client** (§4.7). Two ←/→-cycled variants
  (centre-first / start-first); step 2 reuses the `line` schema (Radius + Start°),
  step 3 is the new `arc_span` transform schema (Span° ⇄ Arc-length coupled). HUD
  drives the readout + preview; block-4 `_draw_dim_hint` retired for arc.
- **Rectangle rotate step.** Corner/centre variants keep their 2-click sizing, then
  a third **rotate** step: `RectangleItem` gains a stored `angle` (native Qt
  transform; grips/snap/serialization all rotation-aware), driven by the new
  `rotation` transform schema.
- **Ghost updates on field commit (§4.9).** Each Tab field-commit redraws the live
  preview from the current HUD values (typed + still-seeded), for all HUD clients.
- **Generic placement-variant cycle (§4.8).** `_PLACEMENT_VARIANTS` registry +
  ←/→ at step 0, session-sticky; `<label> (←/→ to change): …` readout.
- **Ctrl angle-snap** during arc placement (centre→cursor bearing) and the rect
  rotate step, via the shared `_constrain_angle`.
- **Angle reference guides** — protractor lines from the pivot/centre during the
  rect rotate step (0° datum + live sweep) and the arc span step (0° datum + start
  radial + live sweep radial).
- **Single-key tool shortcuts** L/R/C/A/G (+ K placeholder for polyline), scene-focus
  gated in `Model_View.keyPressEvent`; `set_mode` returns focus to the visible view
  so step-0 keyboard reaches the scene.

**STILL PROPOSAL (below):** wall-proximity, extension-line, and equal-spacing guide types; node/sprinkler reference sources; **pipe** placement as Dynamic Input + inference client; general body-drag (non-wall) as inference client (move/paste pick-point inference is built, but *moved-geometry key-point* snapping is not); per-guide distance labels; Selection Dimensions (§8); angled Wall-Parallel/Wall-Perpendicular guides + at-range/acquire tracking (filed in TODO.md follow-ups); the full three-toggle + master-key system (§10).

**BUILT 2026-08-25 (commit eead762):** wall placement is a full HUD client (primitive-aware `active_schema`: `line`/`polyline` → `line` schema, rect sizing → `rectangle` schema, rect rotate step → `rotation` schema; applier `_apply_wall_dynamic_input`); wall provides H/V references (`WallSegment.alignment_reference_points()` at the true centerline endpoints + midpoint) and consumes them during placement (`_inference_active_item` set for `"wall"`); the wall provider pass in `_collect_alignment_refs` is spatial-filtered via `scene.items(rect)` (no unbounded scan — see §5.3).

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
│  ├─ DynamicInputHud  [BUILT — dynamic_input.py]      │
│  │   on-canvas editable HUD; schemas by primitive    │
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
│  ├─ ScaleManager (unit display/parsing; angle fns)   │
│  ├─ 45° constraint (pipe: relative, editable — §4.7) │
│  └─ Model_Space (placement modes, drag handling)     │
└──────────────────────────────────────────────────────┘
```

The Dynamic Input HUD lives in its own module, `firepro3d/dynamic_input.py`
(`FieldKind`, `FieldSpec`, `Schema`, the pure `resolve_*`/`seed_*` functions,
and the `DynamicInputHud` widget — no `QGraphicsScene` knowledge). `Model_Space`
owns the seam (§4).

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

## 4. Dynamic Input

Shipped 2026-08-19 as `DynamicInputHud` in `firepro3d/dynamic_input.py` — an
on-canvas, **non-modal** HUD that both reads out the live geometry of an
in-progress placement and accepts typed values to drive it precisely. It
replaced the modal `_DynInput` `QDialog` (deleted). Schemas are organised by
**geometric primitive, not entity type**, so one schema serves many clients.

> **Design source:** `docs/superpowers/specs/2026-08-16-dynamic-input-hud-design.md`
> and the plan `docs/superpowers/plans/2026-08-16-dynamic-input-hud.md` (decisions
> S1–S3, D1–D3, findings ledger). This section is the governing summary of **what
> the code does**; the design doc holds the rejected-alternatives history.

### 4.1 One HUD, two exclusive states (decision S1)

The HUD is created when a placement **anchor is armed** (first click / mode arm)
and lives for the whole placement — there is no second painted readout for the
modes it serves. `Model_Space._sync_dynamic_input` is the single owner of its
existence (called after the mode handler on move and after the press dispatch).
It is always in one of:

- **Disengaged** — a passive readout. Follows the cursor, is reseeded from the
  live geometry every frame, and is **transparent to the mouse** (self + every
  child), so a click meant for the canvas is never swallowed.
- **Engaged** — an editor. A field holds the keyboard, the cursor is inert.

`Model_Space.is_input_mode()` is exactly `hud.is_engaged()` — *not* "a HUD
exists". Everything that makes the mouse inert keys off engagement. Engagement is
an explicit flag, not a live `hasFocus()` poll (which is False whenever the app
window is inactive).

**Engage set** — `ENGAGE_CHARS = "0123456789.-"` (typing one opens the HUD seeded
with that character), or **Tab** (opens without contributing a character).
`Escape` rung 0 **disengages** to the passive readout without closing; a second
Escape cancels the placement. Tab inside the HUD cycles its fields.

### 4.2 Schemas (organised by primitive)

`Schema` = a field set + pure `resolve(anchor, values)` / `seed(anchor, point)`
functions that know nothing about `QGraphicsScene`. A **placement** schema
resolves to the single `QPointF` a mouse click would have produced, which the
existing click-commit path (`_commit_*_at`) then consumes — so commit parity is
structural, not asserted. A **transform** schema resolves to a plain dict handled
by its own small applier.

| Schema | Fields | `resolve` → | Built clients (`_APPLIER_FOR_MODE`) |
|---|---|---|---|
| `line` | Length, Angle | `QPointF` | `draw_line`, `draw_gridline`, `polyline`, **`draw_arc` step 2** |
| `rectangle` | X, Y (signed) | `QPointF` | `draw_rectangle` (sizing step) |
| `circle` | Radius | `QPointF` | `draw_circle` |
| `arc_span` | Span (SPAN), Arc-length | `{"span_deg": float}` | `draw_arc` step 3 |
| `rotation` | Angle | `{"angle_deg": float}` | `draw_rectangle` (rotate step) |
| `displacement` | dX, dY | `{"offset": QPointF}` | `move` |
| `distance` | Distance | `{"distance": float}` | `gridline_offset` |
| `spacing_count` | Spacing, Count | `{"spacing", "count"}` | `gridline_array` |

Angles are **Y-up** (0° = right, 90° = up; scene Y is down, so
`y = anchor.y() − length·sin θ`). Rectangle X/Y are **signed** (a left/down drag
is a negative extent, and in corner mode that sign *is* the geometry).

`arc`/`rectangle` are **step-aware**: `active_schema()` returns a different schema
per placement step (`_draw_arc_step`; the rect rotate flag), and the existing
`_sync_dynamic_input` schema-change rebuild swaps the HUD's field set. `arc_span`
uses a dedicated **`FieldKind.SPAN`** (unsigned 0–360° magnitude, non-normalising)
so a reflex sweep reads 270°, not −90°; its Arc-length field is a derived view
coupled through the seeded radius (`set_coupling_radius`, in mm). The `rotation`
angle is **Y-up (CCW+)** and is negated at Qt's `setRotation` (CW+ on the Y-down
scene) so the rect turns the way the readout says.

**Anchor gating.** `Schema.requires_anchor` (= `returns_point or needs_anchor`)
decides whether the HUD may open without a placement anchor. Every placement
requires one; `move` is a transform that *also* requires one (its base point),
so it carries `needs_anchor=True` and stays shut until the base point is picked.
The gridline transforms (`distance`, `spacing_count`) are genuinely anchorless
and open as soon as their source is armed.

> A mode appears in `_SCHEMA_FOR_MODE` (forward declaration) before it appears in
> `_APPLIER_FOR_MODE` (the gate that actually opens a HUD). `wall` and `pipe` are
> schema-mapped to `line` but have **no applier yet** — they are **[PROPOSAL]**
> (§4.7), parked as new clients. `arc` and `draw_rectangle` are **step-aware**
> (their `active_schema()` is keyed on the placement step, not a static
> `_SCHEMA_FOR_MODE` row). `sprinkler` and `construction_line` are not
> schema-mapped at all.

### 4.3 Seeding invariant (WYSIWYG)

The HUD seeds from the **resolved** point — the fully constrained position drawn
on screen after OSNAP → inference → Ctrl → 45° snap — never from the raw cursor,
so the numbers shown are the ones the user is looking at.
`Model_Space.publish_placement_state` is the single source for both the passive
readout and the engage-time seed, so the two cannot disagree. (Never
truthiness-test the `QPointF`: `QPointF(0,0)` is a legitimate OSNAP result.)

### 4.4 Unit handling

Each field is a `DimensionEdit` (three `FieldKind` configurations of the one
widget, so the house parser/formatter and revert-to-last-valid come along). The
schemas work in **scene units**; `DimensionEdit` stores **millimetres**:

- **DIMENSION** fields convert at the HUD boundary (`set_values`/`values`),
  **guarded on calibration** — uncalibrated (the default) treats 1 scene unit as
  1 mm, matching the on-canvas readout; a calibrated drawing routes through
  `ScaleManager.scene_to_mm`/`mm_to_scene`. The conversion lives in the HUD, not
  in the schemas (which stay pure geometry) nor in `DimensionEdit` (mm-native).
- **ANGLE** fields are dimensionless — see the angle convention in
  [units-and-formatting.md](units-and-formatting.md) (owned by
  `ScaleManager.normalize_angle`/`format_angle`/`parse_angle`), not restated here.
- **COUNT** fields are bare integers (rounded, floored at 1).

### 4.5 Interaction with OSNAP / inference

The seed is the resolved point (§4.3), so an active OSNAP or alignment guide is
already baked into the readout. A typed value **overrides** it — while a field
holds focus the cursor is inert and `publish_placement_state` is a no-op, so a
late snap cannot move the seed out from under a half-typed value.

### 4.6 Error handling — two layers

- **Field level:** an unparseable entry reverts to the last valid value with no
  signal (kills the old `_DynInput.value() → 0.0` bug); a rejected value gets a
  red border. `has_invalid_field()` is sticky so a second Enter cannot slip
  reverted geometry through.
- **Applier verdict (decision D2):** the too-short / too-small / count floors
  live in the commit path, not mirrored into the schema. An applier returns
  `bool`; on `False` `_on_dynamic_input_committed` **keeps the HUD open** with
  every DIMENSION field flagged and the placement fully live, so the user simply
  retypes — instead of the value vanishing into a status message after the HUD
  has closed.

### 4.7 HUD clients — arc **[BUILT]**, wall **[BUILT 2026-08-25]**, pipe **[PROPOSAL]**

- **Arc — [BUILT 2026-08-21].** Two ←/→-cycled variants (`_arc_variant`:
  centre-first / start-first). Step 1 is the anchor click; step 2 reuses the
  `line` schema and `_commit_draw_arc_rim_at` (variant-aware: the second point is
  the rim in centre-first, the centre in start-first) to fix radius + start°;
  step 3 is the `arc_span` transform, whose applier `_commit_draw_arc_at` sweeps
  the stored centre/radius/start to the resolved end point. `_apply_arc_dynamic_input`
  routes by step. The HUD is the readout + preview (`_preview_from_arc`), so arc
  no longer paints `_draw_dim_hint` (block 4 survives for the other non-HUD modes).
- **Wall — [BUILT 2026-08-25, commit eead762].** `active_schema()` is
  **primitive-aware** for `"wall"` (same step-aware pattern as rect/arc): `line`
  and `polyline` primitives → `line` schema (Length + Angle); `rect` primitive at
  the sizing step → `rectangle` schema (signed X, Y); `rect` primitive at the
  rotate step → `rotation` schema (Angle, Y-up CCW). The applier
  `_apply_wall_dynamic_input` routes on `_wall_primitive` and step to build the
  `WallSegment`(s) via the same finish-vs-continue branch the mouse path uses
  (structural commit parity — `inferred-dimension-driven-placement.md §4.2`).
  `"wall"` is **no longer a parked static `_SCHEMA_FOR_MODE` entry** — it is
  handled inside `active_schema()` by `_wall_schema_for_primitive()`.
- **Pipe — [PROPOSAL].** Pipe is schema-mapped to `line` in `_SCHEMA_FOR_MODE`
  but has no applier, so no HUD opens; it still places through its own handlers.
  When pipe lands, its angle field is intended to be **editable and validated**,
  *not* read-only: the 45° constraint is **relative to the reference pipe and only
  when connected** (a free pipe soft-snaps within 7.5°), so a typed angle is
  accepted when it yields a valid fitting rather than forbidden outright.
  *(This corrects the earlier proposal, which called the pipe angle "read-only
  / non-overridable" and "locked to 45° at all times".)*
- **`construction_line` is out of scope** — its Length field was a visual no-op
  (the drawn line extends past both defining points), so it is deliberately
  absent from `get_placement_anchor` and the schema tables.

### 4.8 Placement-variant cycle **[BUILT]**

`_PLACEMENT_VARIANTS: dict[mode → list[(label, first-point instruction, apply_fn)]]`
(a data table beside `_SCHEMA_FOR_MODE`/`_APPLIER_FOR_MODE`) with a session-sticky
`_variant_index`. `cycle_placement_variant(±1)` — wired to `←`/`→` in
`Model_Space.keyPressEvent` — flips the variant **only at step 0** (`_at_placement_step_zero`)
and while no HUD field is engaged; otherwise it returns False so the arrow reaches
the view's default scroll. `set_mode` applies the sticky variant on entry and emits
the `<label> (←/→ to change): <instruction>` readout; the first press handler emits
the plain next-step instruction, so the hint disappears once a point is placed.
Orthogonal to the Left-Shift-tap `cycle_placement_ambiguity` (a different axis).

Registered variants: `draw_arc` (Centre Point / Start Point → `_arc_variant`),
`draw_rectangle` (Corner / Centre → `_draw_rect_from_center`),
`wall` (Line / Polyline / Corner Rectangle / Center Rectangle → `_wall_primitive` + `_wall_rect_from_center`).

**Ribbon/keyboard.** The Line and Rectangle ribbon split-menus were retired (corner/
centre and line/construction-line are cycle variants now). Single-key tool shortcuts
live in `Model_View.keyPressEvent` (scene-focus-gated, bare-key only): L/R/C/A/G →
line/rect/circle/arc/gridline, plus a **placeholder K → polyline** (removed when
Line+Polyline merge into one cycle tool). `set_mode` returns keyboard focus to the
visible view so step-0 keys (the cycle arrows) reach the scene after a ribbon click.

### 4.9 Ghost updates on field commit **[BUILT]**

While a field is engaged the cursor is inert (§4.5), so the live preview would sit
frozen at its engage-time seed. `DynamicInputHud.fieldCommitted` fires on each Tab
field-commit; `Model_Space._on_dynamic_input_field_committed` reads the current
values **non-destructively** (`current_values()` — no force-commit, no flag
mutation), `resolve`s them, and drives the same per-mode preview the mouse uses
(`_preview_from_resolved` / `_PREVIEW_DISPATCH`, extracted from the `_move_*`
tails). Placement schemas resolve to a point; the `move` transform and arc's
`arc_span` resolve via `_transform_preview_point` (offset→target / span→endpoint);
the rect `rotation` drives its own angle-based `_preview_rectangle_rotation`.

### 4.10 Angle-snap and reference guides **[BUILT]**

**Ctrl** angle-snaps to `_snap_angle_deg` (45°) via the shared `_constrain_angle`
during arc placement (centre→cursor bearing, both steps) and the rect rotate step
(pivot→cursor), on both the move preview and the committing click. **Reference
guides** (dashed cosmetic lines) render as a protractor: the rect rotate step shows
a 0° datum + a live sweep from the pivot; the arc span step shows a 0° datum + the
fixed start radial + a live sweep radial from the centre. Created on entering the
step, cleared on commit and mode-exit.

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

### 5.2 Active During **[PARTIAL]**

**BUILT:** `draw_gridline` placement (both points), gridline endpoint grip-drag, the **move/paste pick points** (both clicks; move self-excludes the movers), and **`"wall"` placement** (all primitives and steps; provider + consumer — see §5.3 and §0 built note above).

**PROPOSAL:** `pipe`, `sprinkler`, and other construction-geometry placement modes as consumers; moved-geometry key-point snapping (non-wall); drag repositioning of non-wall entity types.

### 5.3 Detection Algorithm **[PARTIAL]**

**As built (gridline + wall slice):** `_collect_alignment_refs(cursor, tol)` now runs two passes:

1. **Gridlines** — iterates `self._gridlines` directly (small list, no spatial filter needed).
2. **Walls** — spatial-filter via `scene.items(rect)` (inflated cursor rect using `INFERENCE_TOL_PX` mapped to scene units), type-filtered to `WallSegment`, then `alignment_reference_points()` on the survivors. This uses the scene BSP index (`scene.items(rect)`, **not** `sceneBoundingRect`), bounding per-frame cost to walls near the cursor independent of total wall count.

Both providers are duck-typed (`alignment_reference_points()`); self-exclusion via `source_id` and `_inference_exclude_ids` is applied to all collected refs.

**PROPOSAL (for future multi-entity providers):** node/sprinkler/pipe providers slotting in by iterating their own collections; cursor-move cache threshold (§9.5).

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

### 11.1 Dynamic Input **[BUILT]**

Three layers, mirroring the module boundary:

- **(a) Schema layer — no Qt** (`tests/test_dynamic_input_schema.py`): `resolve_*`
  / `seed_*` round-trips, Y-up sign, signed rectangle extents, `requires_anchor`
  (placements + `move`, not the anchorless transforms), `spacing_count` integer
  flooring. Angle format/parse/normalize in `tests/test_scale_manager_angle.py`.
- **(b) Widget layer — HUD-driven** (`tests/test_dynamic_input_widget.py`):
  seeding, value reads, grow-only field width, sticky invalid styling + red
  border, session undo, engage/disengage, mouse-transparency, numpad Enter.
- **(c) Commit parity — mouse vs HUD** (`tests/test_dynamic_input_parity.py`):
  a typed value and the same value dragged produce identical geometry, for line,
  rectangle, circle, polyline, gridline offset/array and move; applier-rejection
  keeps the HUD open (D2); the `GridlineItem.translate` regression.

Seam-level (`Model_Space`) behaviour — anchor gating, engage refusal, input-mode
inertness, the Left-Shift-tap placement cycle — lives in
`tests/test_dynamic_input_seam.py`, `tests/test_dynamic_input_lifecycle.py`,
`tests/test_dynamic_input_multiview.py` and `tests/test_placement_cycle_shift.py`.

| Example assertion | Where |
|---|---|
| `resolve_line` is Y-up; `seed_line` round-trips | (a) |
| Typed length overrides cursor; commit matches the mouse click | (c) |
| Unparseable entry reverts to last valid, nothing placed at zero | (b) |
| A refused too-short commit keeps the HUD open, field flagged | (c) |
| Tab cycles HUD fields; digit/`.`/`-` opens+seeds; numpad Enter commits | (b) |

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
