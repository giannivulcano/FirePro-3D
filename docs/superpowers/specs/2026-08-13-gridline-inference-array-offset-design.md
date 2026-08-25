---
status: proposal          # designed, unbuilt — flips to partial (inference spec) after Phase 5 lands
last-verified: 2026-08-13
verified-commit: 3b23236
applies-to:
  - firepro3d/inference_engine.py   # new
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/gridline.py
  - firepro3d/entity_context_menu.py
  - firepro3d/main.py
  - firepro3d/constants.py
source-tasks:
  - "TODO.md — Gridline follow-up: placement alignment snapping"
  - "TODO.md — Gridline follow-up: on-canvas array/offset for gridlines"
governs-specs:                       # governing specs this design updates at Phase 6 Account
  - docs/specs/inferred-dimension-driven-placement.md   # → status: partial (gridline slice built)
  - docs/specs/grid-system.md                           # → new Array/Offset section + inference cross-ref
  - docs/architecture/theming.md                        # → alignment-guide style token
---

# Gridline Alignment Snapping + Array/Offset — Design Spec

**Date:** 2026-08-13
**Complexity:** Large (/todo workflow)
**Status:** Proposal (design approved; implementation pending)

Two paired gridline follow-ups from the 2026-08-13 Revit-UX re-architecture (`grid-system.md` §16 Out-of-Scope). The WHAT was locked in a grill session; this doc is the HOW.

## Goal

1. **Alignment snapping** — while placing or grip-editing a gridline, the active point snaps into horizontal/vertical alignment with the grabbable points of other gridlines, with a dashed guide + reference glyph, so column-grid bays line up without manual measurement.
2. **Array / Offset** — replicate a gridline into parallel copies (one offset copy, or N copies at a spacing) directly on canvas from the gridline right-click menu, replacing the deleted Grid Lines dialog's Quick Fill.

Feature 1 is built as the **first implemented slice of a general inference engine** (`inferred-dimension-driven-placement.md`), so walls/pipes/sprinklers adopt the same engine later with no rework. Feature 2 is gridline-specific.

## Motivation

Gridline placement went on-canvas in the Revit-UX re-architecture, but two workflows still lack support: laying a new bay line up with an existing grid (no alignment inference exists anywhere in the app yet), and stamping out a bay run (copy/paste is the only interim). Both are core column-grid drafting moves. Building alignment inference generically — rather than as a gridline one-off — seeds the long-planned "smart placement" subsystem whose spec already exists but was never built.

## Architecture & Constraints

### A1. `InferenceEngine` (new module `firepro3d/inference_engine.py`)

A generic, entity-agnostic coordinator owned by `Model_Space` (one instance). **Never imports `GridlineItem`.** Responsibilities:

- Collect candidate reference features each mouse-move (spatial-filtered).
- Compute active alignment guides (H/V) from those features vs the raw cursor.
- Rank a snapped position per the priority hierarchy.
- Expose `active_guides` + the chosen snapped point for the overlay renderer.

**Single integration point:** `Model_Space.get_effective_position(scene_pos)` (model_space.py:3540) resolves as:

```
OSNAP hard-snap  (existing snap engine, priority 1)
   → else InferenceEngine: guide-intersection (2) → single-guide (3)
   → else free cursor (4)
```

The engine is only consulted when OSNAP yields no hard snap, so real geometry always wins (matches inferred-placement spec §6.1 and snapping-engine spec).

### A2. Reference-provider protocol (duck-typed, house convention)

Items opt in by implementing:

```python
def alignment_reference_points(self) -> list[ReferenceFeature]: ...
```

`ReferenceFeature` is a lightweight typed record: `kind` (`"point"` now; `"edge"`/`"face"` reserved for deferred extension/wall-proximity guides), the scene-coord `pos`, the `source_item`, and a `label` (e.g. `"endpoint"`, `"bubble"`) for the glyph/debug. The engine spatial-filters `scene.items(rect)`, calls the method where present, and **excludes the active item** (the gridline being placed/dragged). Mirrors the existing `get_properties`/`set_property` duck-typed protocol; walls/pipes implement the method later with zero engine change.

`GridlineItem.alignment_reference_points()` returns 4 features: both endpoints (`p1`, `p2` from `line()`) and both bubble centers (endpoint ± `_bubbleN_offset` along the axis).

### A3. Guide rendering (overlay paint, no scene-items)

Guides render in `Model_View.drawForeground` (model_view.py:142), following the existing **snap-trace** idiom verbatim:

- **Guide lines:** scene-coord dashed **cosmetic** pen in the alignment-guide color (theming token).
- **Reference glyph:** viewport-coord marker at the reference point, like the OSNAP indicator.
- **State source:** the engine's `active_guides` surfaced on the scene the way `_snap_result` is; `drawForeground` reads it with no new plumbing.
- **Clearing:** automatic — `drawForeground` redraws from current state each repaint; empty `active_guides` (no alignment / committed / mode-exited / toggle-off) draws nothing. **No `QGraphicsItem` add/remove in event frames** (honors the scene-churn rule).

### A4. Toggle surface & persistence

- **New "Inference" tab** in the existing snap settings dialog (`_open_snap_tolerance_dialog`), with the **Alignment Guides** toggle and room reserved for the future dynamic-input/spacing toggles (proposal).
- **Status-bar pill** mirroring the F3 OSNAP pill (live at-a-glance state).
- **F12** shortcut (confirmed non-conflicting at impl).
- **QSettings** new `inference/` namespace: `inference/alignment_guides` (default `True`), restored on startup like the SNAP per-type toggles (`snap-toolbar.md`).

### A5. Array / Offset (gridline-specific)

- **Two transient modes** on `Model_Space`: `gridline_offset`, `gridline_array`, each storing the source `GridlineItem`.
- **Invocation:** a new gridline branch in `entity_context_menu.py` (type-dispatch like other entities) with **"Array Gridlines…"** and **"Offset Gridline…"**. The right-clicked gridline is the source (single-source v1), regardless of selection. Locked source allowed (copies are unlocked; source untouched).
- **Interaction:** cursor drives it live — perpendicular distance from the source's own axis → spacing, sign → side; ghost preview follows. Default count 1. **Tab or any digit** opens & seeds `_DynInput` (`(Distance)` for offset, `(Spacing, Count)` for array). Click/Enter commits; Esc cancels; mode exits after commit.
- **Ghost preview:** `drawForeground` overlay (simplified cosmetic outline — line + bubble circles), no preview scene-items.
- **Commit:** build real `GridlineItem`s (rigid parallel translation: same `_angle_deg`/`_length`, `_origin` shifted perpendicular; bubble offsets/visibility + display overrides inherited; **unlocked**), append to `_gridlines`, **sync counters then auto-label** (fresh sequential, counter-continued), run duplicate re-scan, then **one** `push_undo_state()` — same discipline as `_make_line_like`. Whole array = one undo step.

### A6. Constraints & conventions

- All geometry in mm; Y-up display convention where surfaced (panel), scene Qt Y-down.
- No `.fpd` schema change: copies serialize via existing `GridlineItem.to_dict`/`from_dict` on both paths (`scene_io` + `_capture_network`); inference persists only the toggle.
- Per-move engine cost bounded by `scene.items(rect)` spatial filtering + a cursor-move cache threshold (inferred-placement spec §9); no O(n²).
- Perpendicular normal reuses the gridline's fixed-sign `_perpendicular_vector()` convention (grid-system §5.3).

## Design Decisions

| # | Decision | Rationale | Rejected |
|---|----------|-----------|----------|
| D1 | Standalone `inference_engine.py`, owned by `Model_Space`, hooked at `get_effective_position` | Real module boundary + isolated tests; keeps "infer where nothing exists" separate from OSNAP "snap to what exists" (spec §2) | Extend `snap_engine.py` (blurs concerns, already large); inline in `model_space.py` (already huge, blocks reuse) |
| D2 | Duck-typed `alignment_reference_points()` returning typed features | House convention (`get_properties`); per-entity knowledge on the entity; engine stays entity-agnostic; typed features let edges/faces slot in later | Central provider registry (second registration surface; providers re-query scene) |
| D3 | Guides render as `drawForeground` overlay paint, no scene-items | Matches snap-trace path; auto-clears; no item churn in event frames | Real ghost `QGraphicsItem`s (churn + cleanup hazard) |
| D4 | Toggle = new tab in existing snap dialog + pill + F12 | Reuses OSNAP settings surface; user-requested; consistent | New standalone dialog/surface |
| D5 | Array/Offset = two transient modes, cursor-live + Tab/digit `_DynInput`, ghost overlay, single-undo | Mirrors the just-shipped `draw_gridline` idiom; on-canvas feel; avoids modal | Modal-first `(Spacing,Count,Side)` dialog (modal-heavy, no preview) |
| D6 | Type-to-capture: any digit opens the dyn-input (not only Tab) | Matches inferred-placement §4.3; faster entry | Tab-only |
| D7 | Built slice = H/V + gridline refs + placement/grip only; no distance label | Ships the literal ask tightly; label/other guide types are additive against the same engine | Build wall-proximity/extension/equal-spacing/label now (scope explosion) |

### Built-vs-proposal split (inferred-dimension-driven-placement.md → `status: partial`)

**Built (current after Phase 5):** InferenceEngine core (hook, provider protocol, priority ranking); **H/V alignment guides only**, from **gridline** grabbable-point references, during `draw_gridline` placement + endpoint grip-drag; guide-intersection + single-guide snap + glyph; `drawForeground` rendering; the single **alignment-guides toggle**; the per-move spatial-filter perf approach for this slice.

**Proposal (specced, unbuilt):** wall-proximity, extension-line, equal-spacing guide types; node/sprinkler/wall reference sources; other placement tools + body-drag/other-entity-drag as clients; per-guide distance labels; Selection Dimensions §8; Dynamic Input §4 as a general capability (note `_DynInput` partially exists); full three-toggle + master-key system §10.

## Acceptance Criteria

**Alignment snapping (Feature 1):**
- [ ] During `draw_gridline` placement (both points) and endpoint grip-drag, the active point H/V-snaps to any other gridline's endpoints or bubble centers.
- [ ] Simultaneous H+V guides snap to their intersection.
- [ ] Priority `OSNAP > guide-intersection > single-guide > free-cursor` holds.
- [ ] Dashed guide line + reference glyph render in the alignment-guide color; clear when alignment breaks / on commit / mode-exit / toggle-off.
- [ ] Alignment Guides toggle (snap-dialog tab + status-bar pill + F12) default on, persisted to `inference/alignment_guides`; toggling off silences guides+snap.
- [ ] Edges: no other gridlines → no guides; angled & locked gridlines are valid references; the active line's own first point emits no guide; coexists with Ctrl angle-lock.
- [ ] Engine never imports `GridlineItem`; `GridlineItem.alignment_reference_points()` supplies the 4 features.
- [ ] Alignment-guide style is a named token in `theming.md`.

**Array / Offset (Feature 2):**
- [ ] Gridline right-click menu offers "Array Gridlines…" and "Offset Gridline…".
- [ ] Offset creates one parallel copy at a cursor/typed perpendicular distance + side.
- [ ] Array creates N parallel copies, spacing-then-count, perpendicular to the source's own axis, with live ghost preview; default count 1; Tab or any digit opens the dyn-input.
- [ ] Copies are rigid parallel translations inheriting angle/length/bubble-offsets/visibility/display-overrides, created unlocked, with fresh sequential auto-labels (counter-continued + duplicate re-scan).
- [ ] Angled source → perpendicular offset is relative to the source's own axis.
- [ ] Esc cancels with no copies; whole array/offset = one undo step.
- [ ] Copies persist/round-trip via both serialization paths; no `.fpd` schema change.

**Testing:**
- [ ] Unit (no Qt): engine H/V guide emission, intersection, priority ordering, no-refs case; array/offset counts, angled-source perpendicular spacing, label sequence, attribute inheritance, unlocked, single-undo pop, serialization round-trip.
- [ ] Functional (widget-driven, `qapp`): placement + grip-drag land on aligned coord; guide appears/clears; toggle silences; right-click→preview→commit; Esc creates nothing. Drive widgets/events, not slots.
- [ ] Red-verified before fix; chunked full-suite green (OneDrive 127 flake).

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] No regressions: default 3+3 seed, existing gridline placement, snap-on-gridlines, duplicate warnings, lock enforcement, spacing dimensions.
- [ ] `inferred-dimension-driven-placement.md` reconciled to `status: partial` with built/proposal sections labeled; frontmatter fixed (valid status, `last-verified`, `verified-commit`, `applies-to`, `source-tasks`).
- [ ] `grid-system.md` gains the Array/Offset section + inference cross-ref + `alignment_reference_points()` API note; §16 items removed from Out-of-Scope.
- [ ] `theming.md` gains the alignment-guide style token; `SPEC-INDEX.md` updated (new `inference_engine.py` mapping).
- [ ] Rule A honored: architecture pages link, don't restate.

## Existing Code Context

| File | Role in this work |
|------|-------------------|
| `firepro3d/inference_engine.py` | **New** — `InferenceEngine`, `ReferenceFeature`, guide computation + priority ranking |
| `firepro3d/model_space.py` | Owns the engine; `get_effective_position` hook; `gridline_offset`/`gridline_array` modes; ghost-preview state; commit + undo |
| `firepro3d/model_view.py` | `drawForeground` guide + ghost-preview overlay paint |
| `firepro3d/gridline.py` | `alignment_reference_points()`; array/offset copy factory helper |
| `firepro3d/entity_context_menu.py` | New gridline branch (Array/Offset actions) |
| `firepro3d/main.py` | Snap-dialog "Inference" tab; status-bar pill; F12 shortcut; QSettings restore |
| `firepro3d/constants.py` | Alignment-guide geometry/tolerance constants |

## Edge Cases & Error Handling

- No other gridlines / all filtered out → no guides, plain OSNAP/free placement.
- Angled source references still emit H/V guides from their points (colinear/extension inference is deferred).
- Locked gridlines: valid references; valid array/offset sources (copies unlocked).
- Zero/sub-min spacing in array → reuse placement's sub-0.5 mm rejection; `_length` floors at 1.0 mm (grid-system §15).
- Cursor exactly between two candidate references (tie) → nearest wins; H+V pair still forms an intersection.
- Toggle off mid-placement → guides + guide-snap immediately inert; OSNAP/free unaffected.

## Performance & Security

- Engine runs per mouse-move only during placement/grip-drag/array/offset modes; `scene.items(rect)` spatial filter (viewport + margin), cursor-move cache threshold, no O(n²) (inferred-placement §9; perf memory). Gridline counts are small, but the engine is written to the general budget so wall/pipe clients stay cheap.
- No security surface (local geometry only).

## Code Style & Testing

- PyQt6, Google docstrings, relative imports within `firepro3d/`, constants centralized. Tests: `qapp` fixture (no pytest-qt), functional tests drive widgets/events not slots, red-verify, chunked full suite.
