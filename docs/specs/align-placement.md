---
status: partial
last-verified: 2026-08-26
verified-commit: d235ab6
applies-to:
  - firepro3d/align_engine.py
  - firepro3d/align_controller.py
  - firepro3d/snap_engine.py
  - firepro3d/dynamic_input.py
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/preferences_dialog.py
  - firepro3d/main.py
  - firepro3d/constants.py
  - firepro3d/gridline.py
  - firepro3d/wall.py
source-tasks:
  - "TODO.md — Inference at range: acquire-based tracking (AutoCAD OTRACK) + band queries — SHIPPED as ALIGN"
  - "TODO.md — Compose inference guides as transient SNAP sources (OTRACK follow-up) — SHIPPED (find(align_paths=…))"
  - "docs/superpowers/specs/2026-08-26-align-tracking-design.md — governing design contract (decisions D1–D7, rationale)"
  - "docs/superpowers/plans/2026-08-16-dynamic-input-hud.md — §4 Dynamic Input HUD (Navigate component)"
---

# ALIGN — Acquire-and-Track Alignment & Dimension-Driven Placement

**Governing design doc:** [`docs/superpowers/specs/2026-08-26-align-tracking-design.md`](../superpowers/specs/2026-08-26-align-tracking-design.md)
(decisions D1–D7, rejected-alternatives history, motivation). This spec is the
governing summary of **what the code does today**; the design doc holds the *why*.
**Depends on:** [Snapping Engine Spec](snapping-engine.md) (§2.3 flagged OTRACK +
inferred placement as next-priority subsystems; both now **delivered here**).

> **Rename note (2026-08-26):** this file was `inferred-dimension-driven-placement.md`.
> The auto-proximity inference/GUIDES subsystem it originally described was
> **replaced** by ALIGN (AutoCAD-OTRACK-style acquire-and-track). The old
> Dynamic Input HUD (former §4) is retained **as the Navigate component** of ALIGN
> (§5). Equal-Spacing (§7) and Selection-Dimensions (§8) remain **proposal**.

---

## 0. Status at a glance

**BUILT (ALIGN acquire → lock → infer → guide → navigate, commit `567602e`):**

- Pure ray/intersection engine (`align_engine.py`) — `Ray`, `AcquiredRef`,
  `rays_for_acquired`, `path_x_path`, `path_x_segment`, `project_to_ray`,
  `point_along_ray`. No Qt, no firepro3d imports.
- Acquire state machine (`align_controller.py`) — dwell-to-acquire (elapsed told
  in), two acquire flavors, cap-evict, re-hover-release, active-anchor
  auto-acquire, per-direction ray gating, `build_rays`, `acquired_points`.
- One-picker integration (`snap_engine.py`) — `find(align_paths=…,
  align_aperture_px=…)` feeds ALIGN candidates (`align_intersection` prio 20,
  `align_path` prio 30) into the **existing** priority-band picker below real
  snaps, judged at their own ALIGN aperture.
- Model_Space seam — dwell feed on move, ALIGN tier in `get_effective_position`,
  universal placement-mode scope (`_ALIGN_PLACEMENT_MODES`), on-path `track`
  schema swap, lifecycle clears.
- Rendering (`model_view.drawForeground`) — `+` acquired markers + dashed
  viewport-spanning tracking vectors, gated on the master ALIGN toggle.
- Navigate = the Dynamic Input HUD (`dynamic_input.py`) + the new `track`
  distance-along-path schema (§5).
- Preferences SNAP-pane ALIGN knobs + F11 master toggle + `align/*` persistence
  (§6).

**STILL PROPOSAL:** Equal-Spacing inference (§7); Selection-Dimensions (§8);
polar-increment angles; paper-space ALIGN; apparent-intersection / multi-level.
See §9 for the divergences and accepted v1 narrowings.

---

## Table of Contents

1. [Overview — the acquire-and-track model](#1-overview-the-acquire-and-track-model)
2. [Acquire](#2-acquire)
3. [Lock & Guide — one-picker composition](#3-lock-guide-one-picker-composition)
4. [Rendering](#4-rendering)
5. [Navigate — the Dynamic Input HUD](#5-navigate-the-dynamic-input-hud)
6. [Settings](#6-settings)
7. [Equal Spacing Inference](#7-equal-spacing-inference-proposal)
8. [Selection Dimensions](#8-selection-dimensions-proposal)
9. [Divergences & accepted v1 narrowings](#9-divergences-accepted-v1-narrowings)
10. [Testing Strategy](#10-testing-strategy)

---

## 1. Overview — the acquire-and-track model

ALIGN is **pure-acquire**: nothing tracks until the user deliberately acquires a
reference. The user hover-**dwells** on a live SNAP marker to *acquire* it (a green
`+`); each acquired reference spawns transient tracking **rays** that the SnapEngine
treats as snappable sources. The user then places relative to those rays — clicking
on a path, clicking a path×path / path×geometry crossing, or typing a signed
distance along a single path. The active placement anchor **auto-acquires** (its own
H/V, plus its extension when it sits on a directional object), so the common
"line up with where I started" case needs no explicit dwell.

This replaces the retired auto-proximity inference/GUIDES subsystem, which fired
H/V guides automatically whenever the cursor lined up with any nearby reference —
no intent — the "grabby during Move" behavior that motivated the rewrite. See §9.

**Model:** **A**cquire → **L**ock → **I**nfer → **G**uide → **N**avigate.

**Scope:** model-space only. No ALIGN in paper-space (§9).

### 1.1 Three units, clean boundaries

| Unit | Role | Qt? |
|---|---|---|
| `align_engine.py` | **Pure geometry.** `Ray`, `AcquiredRef`, ray builders, path×path / path×segment, projection, distance-along-ray. Imports no Qt, no firepro3d. | No |
| `align_controller.py` | **Stateful acquire machine.** Acquired set, dwell decision (told, not polled), cap-evict, re-hover-release, active-anchor auto-acquire, per-direction gating, per-frame ray build. | Minimal |
| `model_space.py` (seam) | Holds one `AlignController`; feeds the dwell on move, builds `[Ray]` and calls `find(align_paths=…)` in the ALIGN tier of `get_effective_position`, arms the `track` schema, renders via `drawForeground`, clears on lifecycle. | Yes |

**Constraint — dwell is told, not polled.** The controller decides "acquired" from
elapsed-since-cursor-stopped **passed in** on each move (`AlignController.on_move(...,
elapsed_ms)`), never from a live `QTimer`. The live app feeds real time; tests feed
synthetic elapsed → deterministic state-machine tests.

**Constraint — one picker.** ALIGN candidates enter the **existing**
`SnapEngine.find()` priority-band picker; there is no second resolution path (§3).

### 1.2 Data model (`align_engine.py`)

`Ray(origin, direction, kind, source_id)` — a transient tracking vector; `kind` is
`"hv" | "extension" | "parallel"`; `source_id` carries provenance for self-exclusion
and render grouping. `AcquiredRef(point, direction, flavor, snap_type, source_id)` —
one acquisition snapshot; `point` is `None` for a pure direction-acquire; `flavor`
is `"point" | "direction"`. `AcquiredRef` is a **coordinate/direction snapshot** —
independent of whether the source item later moves or is deleted (acquisitions are
transient, cleared at command end regardless). Field details are owned by
`align_engine.py` (Rule A — not restated here).

---

## 2. Acquire

### 2.1 Dwell mechanics

`AlignController.on_move(cursor, snap, elapsed_ms)` advances the dwell machine for
one mouse-move. `snap` is the current SNAP result (`{"point", "snap_type",
"source_id", "direction"}`) or `None` when the cursor is over nothing. The controller
tracks *which source* it has been resting on and *for how long*:

- Resting on a **new** source restarts the dwell clock.
- Resting on the **same** source accumulates `elapsed_ms`.
- When the running dwell crosses `dwell_ms` (default `ALIGN_DWELL_MS`), that source
  is acquired — or, if already acquired, **released** (re-hover-release, §2.4).
- The crossing **latches** (dwell reset to 0) so acquire/release fires once, not
  every subsequent resting frame.

The seam (`Model_Space`) feeds `on_move` only when ALIGN is enabled and a placement
mode is armed (`_align_active_item is not None`), so dwell never runs outside a
point-asking command.

**Trackable = any SNAP candidate.** Whatever the SnapEngine grabs under the cursor is
acquirable — endpoint/midpoint/center/quadrant/intersection/node (→ point-acquire),
or nearest/perpendicular on a line-like body (→ direction-acquire). The two
snap-type sets are `_POINT_SNAPS` / `_DIRECTION_SNAPS` in `align_controller.py`.

### 2.2 Two acquire flavors (decided by the dwell's snap type — no modifier, no mode)

- **Point-acquire** — dwell on a discrete point. Emits an **H ray + a V ray** from
  the point; if the source carried a direction (an endpoint/vertex of a directional
  object), also emits an **Extension** ray along that captured direction. Built by
  `rays_for_acquired` for `flavor == "point"`.
- **Direction-acquire (Parallel)** — dwell on a nearest/perpendicular hit of a
  line-like body (cursor over the edge, not a vertex). Captures the edge direction;
  a **Parallel** ray is rebuilt each frame anchored at the **current active
  placement point** (origin moves with the drawing point, direction fixed). Built by
  `rays_for_acquired` for `flavor == "direction"`.

### 2.3 Active-anchor auto-acquire

`AlignController.set_active_anchor(point, direction)` seeds a synthetic
point-acquire (`source_id = -1`, `snap_type = "anchor"`) for the current placement
anchor, so its H/V (and its own extension when the anchor sits on a directional
object) track without an explicit dwell. Cleared with `point=None`. The seam calls
it each frame from the ALIGN tier before building rays.

### 2.4 Cap, release, clear

- **Cap** = `max_points` (default `ALIGN_MAX_POINTS`). Acquiring past the cap evicts
  the **oldest** acquisition.
- **Re-hover-release.** Dwelling again on an already-acquired source **removes** that
  one acquisition (`_toggle_acquire`).
- **Clear.** `AlignController.clear()` drops all acquisitions + the auto-anchor +
  the dwell state. The seam calls it on mode start/end (`set_mode`), Esc, and commit
  (lifecycle clears).

---

## 3. Lock & Guide — one-picker composition

ALIGN does **not** resolve positions in a parallel tier. Each frame the seam asks the
controller for the current `[Ray]` set (`build_rays(active_point)` — acquired refs +
auto-anchor + any parallel direction re-anchored at the active point) and passes them
**into** the existing picker:

```
SnapEngine.find(cursor, scene, view_transform, ...,
                align_paths=rays, align_aperture_px=..., held=self._align_result)
```

### 3.1 Candidate families & priority

When `align_paths` is provided, `find()` adds three ALIGN candidate families to the
same `_SnapCtx` picker that ranks real snaps:

| ALIGN candidate | Built from | Priority |
|---|---|---|
| path × path crossing | pairwise `Ray`×`Ray` (`path_x_path`) | `align_intersection` = 20 |
| path × geometry crossing | `Ray` × nearby scene/underlay segments (`path_x_segment`) | `align_intersection` = 20 |
| single-path projection | cursor foot on a `Ray` (`project_to_ray`) | `align_path` = 30 |

Real SNAP candidates keep priorities **0–7** (lower is stronger; owned by
`snap_engine.py` `_SNAP_PRIORITY`). Final ranking: **real SNAP > align_intersection
> align_path > free**. The winning `OsnapResult` carries the participating ray(s) as
`source_lines`, so `drawForeground` lights the tracking vector(s) (§4). This extends
the SNAP picker's priority-band model (`snapping-engine.md §6.1`) — same hysteresis,
same `_active_view_scale()` px judgment, no second merge pass.

### 3.2 The separate ALIGN aperture

ALIGN candidates are judged at their **own** px grab-radius, not the 15px real-snap
aperture. `find()` takes `align_aperture_px` (default `ALIGN_PATH_TOL_PX`, wider);
each ALIGN `ctx.check(...)` passes `aperture_px=align_aperture` to override the
per-candidate cutoff, so a path soft-snaps from farther out **without** widening the
real-snap grab. A **held** ALIGN result is released at the ALIGN aperture (not the
tighter real-snap one), so an on-path hold isn't dropped prematurely. Path-tol is
judged in true pixels via the shared `px_to_scene`/`scene_to_px` helpers +
`_active_view_scale()` — zoom-invariant (see `snapping-engine.md §14.1`, §14.4).

### 3.3 Path × geometry — nearby-segment extraction

`SnapEngine._align_geometry_segments` yields near-cursor scene/underlay segments for
the ray×geometry crossings, reusing the phase-4 segment generator
(`_iter_geometry_segments`) and the same per-move `underlay_geoms` cache the real-snap
phases populate (no redundant underlay query). It respects `_PHASE4_MAX_SEGMENTS`.
See §9 for the accepted 15-vs-20px underlay-band narrowing this cache reuse implies.

---

## 4. Rendering

`Model_View.drawForeground` paints the ALIGN overlay, **gated on the master ALIGN
toggle AND the controller's existence** — `set_align_enabled(False)` clears
`_align_result` (vectors stop) but not `_align_controller.acquired`, so the gate
prevents orphaned `+` markers:

- **`+` acquired markers** — a cosmetic cross at each `AlignController.acquired_points()`,
  in `ALIGN_ACQUIRE_COLOR` (green, distinct from snap glyphs), sized `ALIGN_GLYPH_PX`.
- **Tracking vectors** — the held result's `source_lines` drawn as dashed
  viewport-spanning cosmetic lines (`ALIGN_GUIDE_COLOR`, `ALIGN_GUIDE_DASH`).
- The path-snap point itself renders via the normal snap marker (it is an
  `OsnapResult` in the picker).

Constants (`ALIGN_*`) live in `constants.py` (Rule A — values not restated).

---

## 5. Navigate — the Dynamic Input HUD

The on-canvas Dynamic Input HUD (`dynamic_input.py`) **is the Navigate component of
ALIGN**. It reads out the live geometry of an in-progress placement and accepts typed
values to drive it precisely — including, while soft-snapped to a single ALIGN path,
a signed **distance along that path** (the `track` schema, §5.7). The rest of this
section documents the HUD as-built; it was shipped 2026-08-19 and is unchanged by the
ALIGN rewrite except for the added `track` schema.

> **Design source:** `docs/superpowers/specs/2026-08-16-dynamic-input-hud-design.md`
> + plan `docs/superpowers/plans/2026-08-16-dynamic-input-hud.md` (decisions S1–S3,
> D1–D3). This section is the governing summary of **what the code does**; the design
> docs hold rejected-alternatives history.

### 5.1 One HUD, two exclusive states (decision S1)

The HUD is created when a placement **anchor is armed** (first click / mode arm) and
lives for the whole placement — no second painted readout. `Model_Space._sync_dynamic_input`
is the single owner of its existence (called after the mode handler on move and after
the press dispatch). It is always in one of:

- **Disengaged** — a passive readout. Follows the cursor, reseeded from live geometry
  every frame, and **transparent to the mouse** (self + every child), so a click meant
  for the canvas is never swallowed.
- **Engaged** — an editor. A field holds the keyboard; the cursor is inert.

`Model_Space.is_input_mode()` is exactly `hud.is_engaged()` — *not* "a HUD exists".
Engagement is an explicit flag, not a live `hasFocus()` poll (which is False whenever
the app window is inactive).

**Engage set** — `ENGAGE_CHARS = "0123456789.-"` (typing one opens the HUD seeded with
that character), or **Tab** (opens without a character). `Escape` rung 0 **disengages**
to the passive readout without closing; a second Escape cancels the placement. Tab
inside the HUD cycles fields.

### 5.2 Schemas (organised by primitive)

`Schema` = a field set + pure `resolve(anchor, values)` / `seed(anchor, point)`
functions that know nothing about `QGraphicsScene`. A **placement** schema resolves to
the single `QPointF` a mouse click would have produced, which the existing
click-commit path (`_commit_*_at`) then consumes — so commit parity is structural, not
asserted. A **transform** schema resolves to a plain dict handled by its own applier.

| Schema | Fields | `resolve` → | Built clients (`_APPLIER_FOR_MODE`) |
|---|---|---|---|
| `line` | Length, Angle | `QPointF` | `draw_line`, `draw_gridline`, `polyline`, **`draw_arc` step 2**, **`wall` (line/polyline)** |
| `rectangle` | X, Y (signed) | `QPointF` | `draw_rectangle` (sizing step), **`wall` (rect sizing)** |
| `circle` | Radius | `QPointF` | `draw_circle` |
| `arc_span` | Span (SPAN), Arc-length | `{"span_deg": float}` | `draw_arc` step 3 |
| `rotation` | Angle | `{"angle_deg": float}` | `draw_rectangle` / `wall` (rotate step) |
| `displacement` | dX, dY | `{"offset": QPointF}` | `move` |
| `distance` | Distance | `{"distance": float}` | `gridline_offset` |
| `spacing_count` | Spacing, Count | `{"spacing", "count"}` | `gridline_array` |
| **`track`** | **Distance** (signed) | **`QPointF`** | **ALIGN on-path (§5.7)** |

Angles are **Y-up** (0° = right, 90° = up; scene Y is down). Rectangle X/Y are
**signed**. `arc`/`rectangle`/`wall` are **step-aware**: `active_schema()` returns a
different schema per placement step and the existing `_sync_dynamic_input` rebuild
swaps the HUD's field set. `arc_span` uses `FieldKind.SPAN` (unsigned 0–360°,
non-normalising) so a reflex sweep reads 270°; its Arc-length field is a derived view
coupled through the seeded radius (`set_coupling_radius`, in mm). The `rotation` angle
is Y-up (CCW+) and negated at Qt's `setRotation` (CW+ on the Y-down scene).

**Anchor gating.** `Schema.requires_anchor` (= `returns_point or needs_anchor`) decides
whether the HUD may open without a placement anchor. Every placement requires one;
`move` also requires one (its base point). The gridline transforms (`distance`,
`spacing_count`) are genuinely anchorless.

### 5.3 Seeding invariant (WYSIWYG)

The HUD seeds from the **resolved** point — the fully constrained position drawn on
screen after real SNAP → ALIGN → Ctrl → 45° snap — never from the raw cursor, so the
numbers shown are the ones the user is looking at. `Model_Space.publish_placement_state`
is the single source for both the passive readout and the engage-time seed. (Never
truthiness-test the `QPointF`: `QPointF(0,0)` is a legitimate SNAP result.)

### 5.4 Unit handling

Each field is a `DimensionEdit` (three `FieldKind` configurations of the one widget).
Schemas work in **scene units**; `DimensionEdit` stores **millimetres**:

- **DIMENSION** fields convert at the HUD boundary (`set_values`/`values`), **guarded
  on calibration** — uncalibrated treats 1 scene unit as 1 mm; a calibrated drawing
  routes through `ScaleManager.scene_to_mm`/`mm_to_scene`.
- **ANGLE** fields are dimensionless — angle convention owned by
  [units-and-formatting.md](units-and-formatting.md) (`ScaleManager.normalize_angle`/
  `format_angle`/`parse_angle`), not restated here.
- **COUNT** fields are bare integers (rounded, floored at 1).

### 5.5 Interaction with SNAP / ALIGN

The seed is the resolved point (§5.3), so an active SNAP or ALIGN result is already
baked into the readout. A typed value **overrides** it — while a field holds focus the
cursor is inert and `publish_placement_state` is a no-op, so a late snap cannot move
the seed out from under a half-typed value.

### 5.6 Error handling — two layers

- **Field level:** an unparseable entry reverts to the last valid value with no signal;
  a rejected value gets a red border. `has_invalid_field()` is sticky so a second Enter
  cannot slip reverted geometry through.
- **Applier verdict (decision D2):** too-short / too-small / count floors live in the
  commit path, not mirrored into the schema. An applier returns `bool`; on `False`,
  `_on_dynamic_input_committed` **keeps the HUD open** with every DIMENSION field
  flagged and the placement fully live, so the user simply retypes.

### 5.7 The `track` schema — distance along an ALIGN path (decision D4)

While the cursor is soft-snapped to a **single** ALIGN path (`align_path`, not a fixed
crossing), the seam swaps the primitive's schema for `track` via the same step-aware
`active_schema()` rebuild, and swaps back on leaving the path. The `track` schema has
one **signed Distance** field; the path's **origin + direction** are injected at
engage/seed time via `DynamicInputHud.set_track_direction` (stored under the reserved
`"__dir__"` key so `resolve_track` stays a pure `(anchor, values) → QPointF`).
`resolve_track` → `origin + Distance·direction`, flowing through the existing
click-commit path (structural commit parity, §5.2). Distance is signed from the
tracking **origin** and **replaces** the primitive Length/Angle readout while on-path.

Seam plumbing: the ALIGN tier recovers the winning single-path `Ray` from the built
ray set (the picker returns the foot point but not the ray) by lowest perpendicular
error — `Model_Space._arm_align_track` — and stores it as `_align_track_ray`;
`_align_track_active` / `_align_track_schema` gate the swap; `_arm_track_direction`
injects the direction into the HUD. A path×path / path×geometry **intersection** is a
fixed point with no single direction → no distance field (the arm is cleared, the
primitive schema stays live).

### 5.8 Other HUD behaviors (as-built, unchanged by ALIGN)

- **Placement-variant ←/→ cycle** — `_PLACEMENT_VARIANTS` registry, session-sticky
  `_variant_index`, flipped only at step 0; `<label> (←/→ to change): …` readout.
  Registered for `draw_arc`, `draw_rectangle`, `wall`.
- **Ghost updates on field commit** — `DynamicInputHud.fieldCommitted` redraws the
  live preview from current HUD values on each Tab field-commit, for all clients.
- **Ctrl angle-snap + reference guides** — 45° constrain during arc / rect-rotate
  steps, with protractor datum/sweep guides.
- **Single-key tool shortcuts** — L/R/C/A/G (+ K placeholder for polyline),
  scene-focus-gated in `Model_View.keyPressEvent`; `set_mode` returns focus to the
  visible view so step-0 keys reach the scene.
- **Wall / arc / rectangle** are full step-aware HUD clients; **pipe** is
  schema-mapped to `line` but has **no applier** (still places through its own
  handlers) — a parked proposal. `construction_line` is deliberately out of scope
  (its Length field was a visual no-op).

---

## 6. Settings

Five ALIGN knobs live in the Preferences **SNAP** pane (`preferences_dialog.py`, the
"ALIGN" tab) plus the F11 master toggle. All live-apply (into the live `Model_Space` +
its `AlignController`), persist to `QSettings` under `align/*`, and are covered by
Reset-to-Defaults:

| Knob | QSettings key | Live target |
|---|---|---|
| Master ALIGN on/off (also F11 + status pill) | `align/enabled` | `Model_Space.set_align_enabled` |
| Path snap aperture (px) | `align/path_tol_px` | `Model_Space._align_path_tol_px` |
| Acquire dwell (ms) | `align/dwell_ms` | `AlignController.dwell_ms` |
| Max acquired points | `align/max_points` | `AlignController.max_points` |
| Per-direction toggles (H/V · Extension · Parallel) | `align/dir_hv` · `align/dir_extension` · `align/dir_parallel` | `AlignController.set_direction_flags` |

Factory defaults are `ALIGN_*` constants in `constants.py` (Rule A — values not
restated). Per-direction toggles drop whole ray **kinds** in `build_rays` so a disabled
kind never reaches the picker. The F11 shortcut and the "ALIGN" status-bar pill are
wired window-level in `main.py` (mirrors the F3/SNAP pattern). A one-time startup
migration copies any legacy `inference/*` key to `align/*` (`_migrate_inference_to_align`).

---

## 7. Equal Spacing Inference **[PROPOSAL]**

*(Unbuilt. Retained as the design target for a future ALIGN capability.)*

### 7.1 Pattern Detection

Minimum pattern: 2 existing items define a spacing. Detect patterns among nodes on the
same pipe run, sprinklers on the same branch line, or parallel pipe runs at consistent
separation.

### 7.2 Inference Algorithm

1. Find items of the same type near the cursor (spatial + type filter).
2. Compute spacings between adjacent pairs.
3. If 2+ items exist with consistent spacing (within tolerance), infer the pattern.
4. Project the next repetition point from the last item in the pattern.
5. If cursor is near the projected point, activate the equal-spacing guide.

### 7.3 Visual

Green dashed line at the inferred position, with a dimension label showing the spacing
value. Small tick marks indicate the pattern positions.

### 7.4 Multiple Patterns

If multiple spacing patterns are detectable, show up to 2 spacing guides simultaneously;
nearest pattern takes visual priority.

---

## 8. Selection Dimensions **[PROPOSAL]**

*(Unbuilt. Retained as the design target.)*

### 8.1 Scope

Nodes and sprinklers. When selected, temporary dimension lines appear showing distances
to adjacent nodes connected via pipes. Same UX pattern as gridline on-selection spacing
dimensions.

### 8.2 Visual

Thin dimension lines with witness lines to adjacent nodes; distance label at midpoint,
formatted via `ScaleManager.format_length()`; same style as gridline spacing dimensions.

### 8.3 Editing

Double-click a dimension label → inline field opens. User types a new spacing (parsed
via `parse_dimension()`). **On confirm:** the selected node slides along the pipe
direction to satisfy the new spacing; adjacent segments stretch/shrink; downstream
nodes stay fixed; fittings auto-update. **On cancel:** revert.

### 8.4 Multi-Selection

Dimensions shown between consecutive selected nodes and between the selection boundary
and the nearest unselected neighbor; editing moves selected nodes as a rigid group
(preserving relative spacing); the unselected anchor stays fixed.

### 8.5 Constraints

Node slides only along pipe direction; minimum pipe length enforced; multi-direction
nodes apply the edit to the segment that owns the edited dimension.

---

## 9. Divergences & accepted v1 narrowings

**Auto-proximity guides REMOVED by design.** The old inference/GUIDES subsystem fired
H/V alignment guides automatically whenever the cursor lined up (within
`INFERENCE_TOL_PX`) with any gridline/wall reference point — no acquisition, no intent.
`InferenceEngine.resolve()`, `_collect_alignment_refs`, the gridline/wall
`alignment_reference_points()` providers, and `Guide(orientation∈{h,v})` are gone.

*Parity note (what the old auto H/V did → its ALIGN replacement):*

| Old auto behavior | ALIGN replacement |
|---|---|
| Auto H/V guide when cursor X or Y matched a nearby gridline/wall reference | Dwell-**acquire** that point → H + V rays (§2.2); active anchor auto-acquires its own H/V (§2.3) |
| Guide×guide intersection snap (priority 2) | path×path `align_intersection` (priority 20, §3.1) |
| Single-guide projection snap (priority 3) | single-path `align_path` (priority 30, §3.1) |
| Auto extension along a wall/pipe endpoint direction (proposal, mostly unbuilt) | Extension ray from a point-acquire on a directional object (§2.2) |
| Cyan dashed guide + crosshair glyph | Dashed tracking vector + green `+` acquired marker (§4) |
| Scene-wide, no intent (the "grabby during Move" complaint) | Pure-acquire: nothing tracks without a deliberate dwell (§1) |

**ALIGN path×underlay 15-vs-20px band narrowing (accepted).** The per-group
`underlay_geoms` cache in `snap_engine.py` is keyed on group id alone and is populated
by the real-snap phases at the 15px `SNAP_TOLERANCE_PX` search rect. When
`_align_geometry_segments` reuses that cache (passing the wider ~20px ALIGN aperture),
an underlay group already cached at 15px is **not** re-queried at 20px — so ALIGN
path×**underlay** crossings only see underlay segments within the 15px rect, a ≤5px
sliver short of the full ALIGN band. Native scene items are re-queried fresh each frame
and are unaffected. Keying on `(gid, aperture)` was deliberately rejected: it would
re-introduce the double underlay query per mousemove that this cache removed.

### 9.1 As-built refinements (2026-08-26 smoke test)

The smoke round produced these behavior changes; the spec is stamped to match shipped
behavior (`verified-commit: d235ab6`). Values live in `constants.py` — linked, not
restated (Rule A).

- **(a) First-point distance-typing routes through the mode's arm path.** Typing a
  signed distance along a path for the *first* click commits via the mode's own
  arm path (`_commit_track_first_point`), not a separate placement branch.
- **(b) Extension / perpendicular snap at ANY angle.** Tracking rays snap correctly
  at any orientation, not only axis-aligned — enabled by the picker's same-priority
  closest-wins clause (snapping-engine §6.1, Task 1); without it the H/V ray (checked
  first, equal `align_path` priority) pinned the pick and a closer angled extension
  foot never won.
- **(c) Auto-acquired anchor inherits its object's direction.** The active-anchor
  auto-acquire on a directional object extends **end-to-end at that object's angle**
  (not H/V only) and reads the **RAW mode anchor**, not the track-ray origin — which
  kills a stray cursor-pinned H/V ray that otherwise appeared.
- **(d) Per-placement reset on `push_undo_state`.** Acquired references and tracking
  state reset per placement, hung off the undo-state push, so alignment context does
  not leak across placements.
- **(e) Navigate field labelled "L".** The distance-along-path `track` HUD field is
  labelled **"L"** (§5).
- **(f) A 4th per-direction toggle "Perpendicular".** The SNAP-pane per-direction
  gating grew a fourth toggle, **Perpendicular** (§6), alongside the existing set.
- **(g) Direction-Parallel defaulted OFF.** The direction-acquire "Parallel" guide
  ships **defaulted OFF** (`ALIGN_DIR_PARALLEL_DEFAULT`, `constants.py`); it is
  superseded by the planned perpendicular-**OFFSET** follow-up (a typed perpendicular
  offset from a reference line — filed in `TODO.md`), which is the behavior actually
  wanted. Parallel remains available but off by default.

**Deferred.** Polar-increment angles; paper-space ALIGN; apparent-intersection /
multi-level snap. Equal-Spacing (§7) and Selection-Dimensions (§8) remain proposal.

See the governing design doc for the decision rationale behind each of these.

---

## 10. Testing Strategy

**ALIGN acquire/track (built):**

- **Pure engine math** (`align_engine`, no Qt) — ray build, path×path, path×segment,
  projection, distance-along-ray; ground truth (`H-ray(M) × V-ray(N) == (Nx, My)`).
- **State machine** (`align_controller`, driven directly) — dwell acquires,
  re-hover releases, cap evicts oldest, clear drops all, per-direction gating drops
  ray kinds.
- **Real-entry-point seam** — posted `QMouseEvent` dwell (elapsed-fed) on a shown +
  activated view acquires/releases/evicts/clears; ALIGN candidates enter `find()` and
  real SNAP always outranks them; the `track` schema swaps in on-path and back off.
- **Zoom-invariance** — aperture + path-tol judged in true px at multiple `m11`
  (identical accept/miss).
- **Per-knob settings round-trip** — each ALIGN knob live-applies + `align/*`
  round-trips + Reset restores factory.

**Navigate / Dynamic Input HUD (built)** — three layers mirroring the module boundary:
schema layer (no Qt, `tests/test_dynamic_input_schema.py`), widget layer
(`tests/test_dynamic_input_widget.py`), commit parity (`tests/test_dynamic_input_parity.py`);
seam behavior in `tests/test_dynamic_input_seam.py` / `_lifecycle` / `_multiview` /
`test_placement_cycle_shift.py`.

**Equal Spacing (§7) / Selection Dimensions (§8)** — proposal; tests TBD when built.
