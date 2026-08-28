# Model_Space Decomposition Map (Phase 1b analysis)

> Status: **analysis artifact** (2026-08-28). Read-only map produced by a 9-agent fan-out over `model_space.py` (10,715 LOC / 341 methods), `scene_tools.py` (1,887 LOC / 46 methods, `SceneToolsMixin`), `scene_io.py` (~757 LOC / 3 methods, `SceneIOMixin`). This is the backbone for the forthcoming **structural governing spec** (`model-space-architecture.md`, orphan-gated) and the input to first-slice selection. It is NOT itself the governing spec.

## 0. The shape of the problem

`class Model_Space(SceneToolsMixin, SceneIOMixin, QGraphicsScene)` is a **~198-instance-attribute god-object**. The two mixins share `self` with it (neither has its own `__init__`), so the "3 classes" are really one object with ~390 methods. The existing governing specs (grid, 2d-geometry, walls/rooms/floors, pipe-placement, selection-mode, ALIGN, constraints) each own a **behavior slice** of this file; **nothing governs its composition** — that is the orphan this decomposition must fill.

## 1. Concern census & coupling verdicts

| # | Concern | ~Methods | Extraction | Why |
|---|---|---|---|---|
| 1 | Pipe/Node network | 29 | **Hard** | direct scene-graph mutation; `node_start_pos`/`_pipe_node_was_new` written externally by `main._on_escape`; dual-serialization; `_restore_network` builds `Pipe()` directly, bypassing `add_pipe` |
| 2 | Sprinkler / Design-Area / hydraulic-run | 16 | **Hard** | scene mutation + `push_undo_state`; temporarily mutates the shared snap engine; dual-serialization of DA/water-supply |
| 3 | Underlay / import (DXF·DWG·PDF) + caches | 28 | **Hard, but cleanest domain slice** | `scene.underlays` read by 6+ external consumers; async DXF worker — BUT **excluded from undo** (no `_capture_network` entanglement), owns its own scene_io block, async boundary already isolated |
| 4 | Serialization / undo-network / clipboard | 24 | **Hard (god-glue)** | inherently reads/writes *every* entity list; this is the concern that couples all others |
| 5 | ALIGN + dynamic-input HUD + placement-variant + templates | ~50 | **Medium** | clean accessor boundary (`get_placement_anchor`/`get_resolved_point`/`publish_placement_state`); named dispatch tables — but Qt-view coupling + appliers scattered into drawing concerns |
| 6 | 2D-geometry drawing + modify tools | ~80 | **Hard** | shared `preview_pipe`, deep `mode` coupling — BUT modify-tool *logic* already lives in `scene_tools.py`; per-primitive triads are self-contained |
| 7 | Architectural placement (wall/floor/roof/opening/room/gridline/detail) | ~65 | **Hard** | dense per-element transient state; `_auto_join_wall`/`_detect_room_boundary` read `self._walls`; roof pops a modal mid-placement |
| 8 | Event-dispatch / selection / grips / levels / lifecycle | ~40 | **IRREDUCIBLE CORE (stays)** | `QGraphicsScene` overrides must receive events; `set_mode` (486 LOC) is the teardown chokepoint; dispatch tables are the extension seam |
| 9 | `SceneToolsMixin` (geometry-op logic) | 46 | **Hard semantically, but best FIRST-SLICE candidate** | already a file/class boundary; pure-math sub-layer has **zero** `self` coupling |

## 2. The recurring seams (the real coupling structure)

These four cut across every concern and define the decomposition contract:

1. **Scene-graph mutation is universal.** Every concern calls `self.addItem/removeItem/createItemGroup`. → No concern can be a pure non-Qt object; every extracted collaborator needs a scene reference. Extractions are "collaborator-with-scene-ref," not "pure module."
2. **`push_undo_state()` is central glue.** ~every commit calls it. Undo is snapshot-based (`_capture_network` reads all lists) and lives with concern #4.
3. **Dual serialization** (`scene_io.save_to_file` = file, `_capture_network` = undo) — two hand-written serializers that must stay field-identical. **Divergences found** (see §4).
4. **`set_mode` (486 LOC) clears every concern's transient state** via a flat `if mode != "X"` cascade. Extraction converts this into a registered-observer `clear()` pattern — each extracted concern exposes `clear()`.
5. **Dispatch tables** (`_PRESS_DISPATCH`, `_MOVE_DISPATCH`, `_PREVIEW_DISPATCH`, `_PLACEMENT_VARIANTS`, `_ALIGN_PLACEMENT_MODES`) are the plug-in seam. A placement concern registers a schema + applier + variant + press/move handler (memory: miss one → HUD freezes).

## 3. Instance-attribute census by concern (from `__init__`)

Approx counts (owned state that would travel with an extraction): 2D-geometry ~47, arch-placement ~47, edit-tools ~40, ALIGN/snap/HUD ~15, selection/grip ~10, sprinkler/DA ~10, misc-infra ~9, pipe/node ~6, level/mode ~6, serialization/undo ~5, placement-variants 2, underlay 1. **Total ~198.** This is the master coupling map: the size of each concern's owned state predicts extraction pain.

## 4. Latent bugs / divergences surfaced (bank as follow-ups)

- **Pipe property source divergence:** `save_to_file` reads `pipe._properties`; `_capture_network` reads `pipe.get_properties()` (adds synthesized Length/Elevation rows). Harmless today only because `set_property` discards them on restore — a trap for any new synthesized row.
- **`_restore_network` skips `update_geometry()` + `_recalc_name_counters()`** that the file-load path runs → possible undo-only rendering/name-counter glitches.
- **`NoteAnnotation.text_width`** may be lost on undo (ctor arg present in `scene_io`, absent in `_restore_network`).
- **Copy-but-no-paste:** `wall`/`room`/`floor_slab`/`roof` emit `to_dict()` with a `"type"` and are captured by copy, but `paste_items` has no branch → silently dropped. `block_item` pastes but isn't tracked in any list → orphaned from undo.
- **Gridline paste heuristic** keys on structural fields (`"origin"+"angle"`, no `"type"`) — fragile.
- **`Room.z_range_mm()` still reads the retired floor `.level`** — new two-boundary slabs don't write it reliably → ceiling-height may degrade.

## 5. First-slice candidates (lowest-risk → highest-payoff)

The map argues for a **layered** first slice, not lifting a stateful domain concern:

- **A — Pure geometry-math layer out of `SceneToolsMixin` → `tool_geometry.py`.** `_compute_fillet/_compute_chamfer/_offset_*/_get_item_segments/_compute_intersections/_compute_extend_intersections/_point_to_segment_dist` + module-level `extract_edges`. **Zero `self` coupling, zero serialization, zero Qt.** Behavior-preserving; unit-testable. Safest possible slice; proves the extract→verify→parity loop.
- **C — Constraint solver → `constraints.py`.** `_solve_constraints`/`_report_constraint_conflict`/`_all_geometry_items` become a standalone function taking `_constraints`. **Already has a governing spec** (`parametric-constraint-system.md`). Called from 3 model_space sites + scene_tools. Medium.
- **B — Convert `SceneToolsMixin` mixin→composition** (the TODO's named target). Physically separated already, but Hard: ~17 state attrs + 6 registries redirected to `self._scene.*`, `self.mode` direct writes audited vs `set_mode`, dispatch `getattr` resolution. Do A+C first, then B.
- **UnderlayManager** — best *domain-concern* first slice if a bigger, more visible payoff is wanted: excluded from undo (no dual-serialization tangle), own serialization block, isolated async worker; main shared surface is the single `self.underlays` list (redirectable via property).

**Recommended sequence:** forge the structural spec (Phase 1b, +/grill-me) → **A** (tool_geometry) → **C** (constraint solver to its spec'd home) → **B** (SceneToolsMixin composition) → reassess before touching stateful domain concerns (Underlay next).

## 6. What stays (irreducible core)

The `QGraphicsScene` event overrides (`mousePress/Move/Release/DoubleClick/contextMenu/keyPress`), the dispatch tables, `set_mode`, the grip mechanism, and `get_effective_position`'s result plumbing. Level-ops and gridline-selection clusters are the most peelable subsets of the "core."
