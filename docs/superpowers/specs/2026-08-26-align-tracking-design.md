---
status: proposal
last-verified: 2026-08-26
verified-commit: c58ae6d
applies-to:
  - firepro3d/align_engine.py        # renamed from inference_engine.py
  - firepro3d/align_controller.py    # NEW — stateful acquire machine
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/dynamic_input.py        # Navigate stage (HUD) — kept as-built + `track` schema
  - firepro3d/snap_engine.py          # find(align_paths=...) integration
  - firepro3d/preferences_dialog.py
  - firepro3d/main.py
  - firepro3d/gridline.py
  - firepro3d/wall.py
  - firepro3d/constants.py
source-tasks:
  - "TODO.md — Inference refinement (P1, 2026-08-26) — folded in (path-snap tol)"
  - "TODO.md — Compose inference guides as transient SNAP sources (OTRACK follow-up)"
  - "TODO.md — Inference at range: acquire-based tracking (AutoCAD OTRACK) + band queries"
  - "docs/specs/snapping-engine.md §2.3 — OTRACK 'deserves its own spec'"
---

# ALIGN — Acquire-and-Track Alignment System — Design Spec

AutoCAD-OTRACK-style **acquire-and-track** alignment, replacing FirePro3D's
automatic-proximity inference/GUIDES subsystem. Model: **A**cquire → **L**ock →
**I**nfer → **G**uide → **N**avigate.

## Goal

The user hover-dwells on a snap point to *acquire* it (`+` marker); each acquired
point spawns a transient reference line the SnapEngine treats as a snappable source;
the user places relative to those lines — clicking on a path, typing a distance along
it, or clicking a path×path / path×geometry intersection. Nothing tracks without a
deliberate acquire (the active placement anchor auto-acquires).

## Motivation

Today's inference fires H/V guides automatically whenever the cursor lines up with any
nearby reference — no intent — which is the "grabby during Move" complaint that started
this, and (per `snapping-engine.md §14.4`) it was *silently scene-based* until the
vestigial-view fix, so it never felt right at any zoom. OTRACK's deliberate acquire
model gives precise control, works for arbitrary-angle geometry (extension/parallel),
and composes into the one SNAP picker instead of a parallel resolution tier.

---

## Architecture & Constraints

### Three units, clear boundaries

| Unit | Role | Qt? | Testable via |
|---|---|---|---|
| `align_engine.py` (rename of `inference_engine.py`) | **Pure geometry.** `Ray`, path×path, path×geometry, projection-onto-ray, distance-along-ray. | No | direct unit tests (gate 2) |
| `align_controller.py` (**NEW**) | **Stateful acquire machine.** Acquired set, dwell decision, cap-evict, re-hover-release, ray generation, render-data. | minimal | driven directly in tests (gate 3) |
| `model_space.py` (seam) | Holds one `AlignController`; delegates move + lifecycle; passes `[Ray]` to `find()`, render-data to `drawForeground`. | yes | shown-view posted-event tests |

**Constraint — dwell is told, not polled.** The controller decides "acquired" from
elapsed-since-cursor-stopped **passed in** on each move, never from a live `QTimer`.
The live app feeds real time (`QElapsedTimer`); tests feed synthetic elapsed →
deterministic state-machine tests without a wall-clock dependency.

**Constraint — one picker.** ALIGN candidates enter the **existing** `SnapEngine.find()`
priority-band picker; no second resolution path. `snap_engine.py` keeps its px-aperture
+ hysteresis + `_active_view_scale()` arithmetic; ALIGN rides all of it.

**Constraint — pure engine stays pure.** `align_engine.py` imports no Qt and no
firepro3d modules (as `inference_engine.py` does today).

### Data model (`align_engine.py`)

```
Ray:                       # a transient tracking vector
  origin: (x, y)           # scene units
  direction: (dx, dy)      # unit vector
  kind: "hv" | "extension" | "parallel"
  source_id: int           # provenance (self-exclusion, render grouping)

AcquiredRef:               # what the controller stores per acquisition
  point: (x, y) | None     # None for a pure direction-acquire (parallel)
  direction: (dx, dy)|None # extension/parallel direction, captured at acquire-time
  flavor: "point" | "direction"
  snap_type: str           # what SNAP grabbed (+ glyph / debug)
  source_id: int           # re-hover-release identity + self-exclude
```

`AcquiredRef` is a **coordinate/direction snapshot** — independent of whether the
source item later moves or is deleted (acquisitions are transient, cleared at
command end regardless).

### Integration hook

`Model_Space.get_effective_position` keeps its order **real SNAP → underlay → ALIGN →
grid**, but the ALIGN tier now:
1. asks the controller for the current `[Ray]` set (built from acquired refs + the
   auto-acquired active anchor + any parallel direction anchored at the active point),
2. calls `find(..., align_paths=rays, held=self._align_result)`,
3. stores the result for render + hysteresis.

The retired `InferenceEngine.resolve()` auto-proximity path and
`_collect_alignment_refs` (gridline/wall providers) are **removed** — replaced by the
acquire model everywhere (gridline, wall, move/paste, and now universally).

## Design Decisions

### D1 — Transient paths passed INTO `find()` (not a separate pass, not scene items)
`SnapEngine.find(..., align_paths: list[Ray] | None = None)`. When provided, find()
adds three candidate families to the existing picker:

| ALIGN candidate | Built from | Picker priority |
|---|---|---|
| path×path intersection | pairwise `Ray`×`Ray` | 2 (below real SNAP) |
| path×geometry intersection | `Ray` × nearby scene segments (via existing `scene.items(rect)` BSP filter) | 2 |
| single-path projection | cursor foot on a `Ray` | 3 |

Real SNAP candidates stay priority 1. Final ranking: **real SNAP > path×path /
path×geometry > single path > free** (extends `snapping-engine.md §6.1`). The
`OsnapResult` carries the participating ray(s) as `source_lines` so the existing
`drawForeground` trace lights the tracking vector(s). *Rejected:* separate merge pass
(duplicates picker/hysteresis arithmetic); transient scene items (pollution +
lifecycle hazards + infinite rays don't fit finite-segment extraction).

### D2 — `AlignController` owns acquire-state (not the Model_Space seam)
Model_Space is already the largest class and a recurring bug surface; ALIGN is a full
state machine (dwell/acquire/release/evict, two acquire flavors, per-frame ray build).
A dedicated unit keeps it testable in isolation and keeps `align_engine.py` pure.
Model_Space holds one instance and exposes a small seam. *Rejected:* `_align_*` on
Model_Space (mirrors the pattern we're retiring; bloats the big class; needs a shown
view to exercise).

### D3 — Acquire flavor decided by the dwell's snap type (no modifier, no mode)
This resolves the two-flavor grill answer without a new key:
- Dwell on a **discrete point** (endpoint/midpoint/center/quadrant/intersection/node)
  → **point-acquire**: emits H + V rays; if the point is an **endpoint/vertex of a
  directional object** (line/wall/pipe/polyline segment), also emits an **Extension**
  ray along that object (segment direction; adjacent-segment direction at a polyline
  vertex), captured from `OsnapResult.source_item` at acquire-time.
- Dwell on a **nearest/on-edge hit of a line-like object** (cursor over the body, not a
  vertex) → **direction-acquire (Parallel)**: captures the edge direction; a Parallel
  ray is rebuilt each frame anchored at the **current active placement point** (origin
  moves with the drawing point, direction fixed).

### D4 — Navigate = new `track` schema (arc's coupling-injection pattern)
New lightweight `track` **placement** schema in `dynamic_input.py`: one signed
**Distance** field; the path **origin + direction** are injected at engage-time via a
coupling setter (the same mechanism arc uses for `set_coupling_radius`). `resolve()` →
`origin + distance·direction` as a `QPointF`, flowing through the existing
click-commit path (structural commit parity, §4.2). The seam swaps the primitive's
schema for `track` **while soft-snapped to a single path** and swaps back on leaving it,
reusing the existing `active_schema()` step-aware rebuild. Distance = signed distance
from the tracking **origin**; it **replaces** the primitive Length/Angle readout while
on-path. Path×path/×geometry intersections are fixed points → no field.

### D5 — Rename first, as an isolated no-behavior-change commit
Commit 1 is the pure rename (module, identifiers, constants, pill/tab labels, F12→F11,
QSettings `inference/*`→`align/*` with one-time startup migration, spec file rename +
SPEC-INDEX/`applies-to`/`[ref:]`), full suite green, **no behavior change**. Everything
else is built on the clean renamed base. The `DynamicInputHud` (`dynamic_input.py`)
keeps its name — it is the **Navigate** component, not the alignment engine.

### D6 — Rendering reuses `drawForeground`
`+` acquired markers (cosmetic cross, `ALIGN_ACQUIRE_COLOR`, distinct from snap
glyphs); tracking vectors dashed viewport-spanning (`ALIGN_GUIDE_DASH`,
`ALIGN_GUIDE_COLOR`); path-snap renders via the normal snap marker + `source_lines`
trace. Constants `INFERENCE_*`→`ALIGN_*`.

### D7 — Settings in Preferences SNAP pane → ALIGN
Persisted `align/*`, covered by Reset-to-Defaults, live-apply + Apply (the 1-of-6
lesson): path-snap tolerance (~20px), acquire dwell (~400ms), per-direction toggles
(H/V, Extension, Parallel), master ALIGN on/off (F11 + status pill), max acquired
points (5). Existing aperture (15px) + hysteresis (3px) stay. Path-snap tol judged in
px via `_active_view_scale()` (folds in the P1 band-right-size fix; pixel-correct).

### Performance
≤5 acquired pts × {H, V, extension} + parallel = ≤~16 rays; path×path O(rays²) ≤ ~120
pairs (line-line math); path×geometry via the existing `scene.items(rect)` filter (only
near-cursor geometry). Inside the existing per-move `find()` within the 5ms budget; a
ray-count cap guards pathological cases.

### Scope boundaries
Model-space only. path×geometry IS a v1 snap. Auto-proximity guides removed everywhere.
Selection-dimensions (§8) + equal-spacing (§7) stay **proposal**. Polar-increment
angles, paper-space, apparent-intersection/multi-level all deferred.

## Acceptance Criteria

- [ ] Hover-dwell (~400ms, tunable) on a live SNAP marker acquires it (`+`); no auto-proximity guide fires without acquisition.
- [ ] The active placement anchor auto-acquires (H/V + its own extension if on a directional object).
- [ ] Point-acquire emits H/V; endpoint/vertex of a directional object also emits an Extension ray.
- [ ] Direction-acquire (edge dwell) emits a Parallel ray anchored at the active placement point.
- [ ] Re-hover-dwell releases one acquisition; Esc / commit / mode-start/end clears all.
- [ ] Cap = 5 (tunable); the 6th evicts the oldest.
- [ ] Cursor soft-snaps to a single path, path×path, and path×geometry crossings via `find()`; real SNAP always outranks ALIGN.
- [ ] On a single path the HUD shows a signed Distance-from-origin field (replaces Length/Angle); Enter commits at `origin + distance·direction`. Works in every HUD client; click-to-place-on-path works in every point-asking command.
- [ ] All five ALIGN knobs live-apply + persist to `align/*` + Reset-to-Defaults restores factory.
- [ ] Full rename shipped: `align_engine.py`, `_align_*`, `ALIGN_*`, `align/*` (migrated), ALIGN pill/tab, F11; `align-placement.md` + SPEC-INDEX updated.
- [ ] Model-space only; no ALIGN in paper-space.

### Test gates (all binding)
- [ ] **Zoom-invariance hard gate** — aperture + path-tol judged in true px at m11 = 0.02/1.0/10.0 (identical accept/miss).
- [ ] **Pure engine-layer math** — ray build, path×path, path×geometry, projection, distance-along-ray; ground-truth (`H-ray(M)×V-ray(N)==(Nx,My)`).
- [ ] **Real-entry-point state machine** — posted QMouseEvent dwell (elapsed-fed) acquires / re-hover releases / Esc-commit-cmdend clears / 6th evicts, on a shown+activated view.
- [ ] **Per-knob settings round-trip** — each knob live-applies + QSettings round-trips + Reset restores.
- [ ] **Parity-review** the retired auto-proximity `resolve()`/`_collect_alignment_refs` path + **interactive real-DXF smoke** (zoom in/out) feel sign-off.

## Verification Checklist

- [ ] All acceptance criteria met
- [ ] The 5 test gates pass
- [ ] No regressions in SNAP / HUD / gridline / wall / move behavior (Commit 1 rename is behavior-neutral; full suite green)
- [ ] Full suite green (chunked); zoom-invariance hard gate green
- [ ] `align-placement.md` reconciled (rename of `inferred-dimension-driven-placement.md`, restructured around A→L→I→G→N; HUD = Navigate as-built; selection-dims retained) + SPEC-INDEX/`applies-to`/`[ref:]` updated + stamped

---

## Existing Code Context (mapped 2026-08-26)

**Reuse as-is:** `SnapEngine.find(cursor, scene, view_transform, exclude, only_types,
item_filter, held)` → `OsnapResult(point, snap_type, source_item, source_item2,
source_lines, name)`; `px_to_scene`/`scene_to_px`/`_safe_scale`;
`Model_Space._snap_view()`/`_active_view_scale()`; `SNAP_TOLERANCE_PX=15`,
`SNAP_HYSTERESIS_PX=3`, `SNAP_PRIORITY_BAND_PX`; `DynamicInputHud` + schema/seed/resolve
(+ `set_coupling_radius` injection pattern); `drawForeground` guide block +
`SNAP_COLORS`/`SNAP_MARKERS`; snap-toolbar QSettings persist pattern.

**Generalize (rewrite):** `InferenceEngine.resolve` (H/V-only, auto) → `align_engine`
ray math; `Guide(orientation∈{h,v})` → `Ray(origin, direction)`;
`_collect_alignment_refs` → acquired-set from `find()` results; `get_effective_position`
ALIGN tier; single GUIDES toggle (F12) → ALIGN (F11).

**Gap (net-new):** `align_controller.py` acquire machine (dwell/marker/release/evict);
arbitrary-angle rays; path×path & path×geometry candidates in `find()`; `track` HUD
schema; extension (point-acquire) + parallel (direction-acquire).

## Tech Context
- **Language/Framework:** Python 3.x + PyQt6 (per CLAUDE.md).
- **Geometry:** millimeters internally; angles Y-up (see `units-and-formatting.md`).
- **Dependencies:** reuse `snap_engine` + `dynamic_input`; no new third-party deps.

## Code Style & Testing
- Google docstrings; relative imports within `firepro3d/`; PEP-8 module names.
- pytest headless against `QGraphicsScene`; widget tests via the session `qapp`
  fixture (no pytest-qt); post real `QMouseEvent`/`QKeyEvent` (QTest.mouseMove inert);
  run full suite chunked before "done".
