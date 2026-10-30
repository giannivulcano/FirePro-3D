---
status: built             # WF1-WF11 built on feat/wall-face-constraints (merged to main 2026-10-30)
last-verified: 2026-10-30  # Account: all WF rows + AC1-AC8 re-audited against the branch diff
verified-commit: 43e792d4  # wall-face constraints Account; prior 75e3cb0f (main at the branch cut)
applies-to:
  - firepro3d/sketch_adapters.py        # _WallAdapter hidden face midpoints + translate hook
  - firepro3d/constraint_dims.py        # _EDGE_MID face rows
  - firepro3d/constraint_controller.py  # _pl_apply translate, _dim_refusal thickness row, DIM_WALL_THICKNESS_STATUS
  - firepro3d/wall_placement_controller.py  # per-press snap capture, passes 1b / 1c
  - firepro3d/auto_constrain.py         # resolve_wall_snap, plan_wall_face_join (plan_joins wrapper)
  - firepro3d/model_space.py            # scene._wall_start_target (init + clear)
source-tasks:
  - "todo_open.md: Constraints between wall faces: Smart Dimension face-to-face ... and a new wall's end joined to a host's face [P2]"
---

# Constraints between wall faces -- Design Spec

Consolidating contract for a change that touches three governing specs (the
"three or more specs" rule): `docs/specs/parametric-constraint-system.md`
(D58 derived midpoints, D81 parallel-edge dims, D77 refusals),
`docs/specs/wall-room-floor-system.md` (s5.4 auto-join) and
`docs/superpowers/specs/2026-10-24-editor-build-tabs-design.md` (W1 wall
handles, PD1-PD3 placement records). Each gets a one-line pointer here at
Account; this file owns the rules below (Rule A).

## Goal

Lay out a plan from the architect's **clear** (inside-to-inside) dimensions
and butt partitions into a wall's face Revit-style:

1. Smart Dimension between two parallel wall **faces** reads the clear
   distance and, typed, moves the second-picked wall.
2. A wall started or ended on a host wall's face keeps its end where it was
   clicked and is **recorded** as joined to that face (or pinned to the face
   corner), so it rides the host when the host moves.

## Motivation

Today the picker hovers a wall's faces but the second face pick is refused
("invalid"): `classify_dim` -> `_parallel_refs` needs the second edge's
midpoint handle and a wall has none for its faces, so the pair falls through
to `dim_angle` and `_dim_refusal`. At placement, OSNAP offers face lines,
face midpoints and face corners, but `_auto_join_wall` tests only host
endpoints (`AUTO_JOIN_TOLERANCE`) and the host **click line** within
`TEE_TOLERANCE` -- a face sits half a thickness away, outside the band, so
nothing joins and nothing is recorded; the partition floats when the host
moves. (Rendering already treats a face-placed end as a tee: `_tee_host`
bands on the true centerline at half-thickness + `MITER_TOL`.)

## Architecture & Constraints

- **No new record types, no solver change.** `coincident` and
  `point_on_curve` are generic over `{uid, h}` refs; `dim_point_line` (D81)
  already expresses "distance between parallel edges".
- **No new visible handles (Q4).** Face midpoints exist only as *hidden*
  derived handles (the shipped `hidden_names` mechanism: text `ins`, polygon
  `radius`) -- never a marker, never pickable, never a grip. The user picks
  face **lines**.
- **Placement records stay under the Auto Constrain gate** (toggle XOR
  Shift, PD2) and flow through `plan_joins` / `plan_commit` as every other
  wall record; hidden hosts are never targets (S3-S1).
- **Geometry first, records name it (PD2).** The face passes move no
  geometry: the OSNAP already put the click on the face / corner.
- Units: scene mm, as everywhere; tolerances from `constants.py`.

## Design Decisions

| id | Decision | Source |
|----|----------|--------|
| WF1 | **Hidden face midpoints.** `_WallAdapter.points` adds `mid_l` = mid(`p1l`,`p2l`) and `mid_r` = mid(`p1r`,`p2r`) (derived, `_mid`); `mid_names` stays `("mid",)` (not extended) and `hidden_names` returns `frozenset(("mid_l", "mid_r"))` (the base's type), so `item_handles` skips them (no marker, no pick) while `_ref_geom`, the solver and dims resolve them by name. `handle_kind` reports them as points. | Phase 3 S1 |
| WF2 | **D81 face rows.** `constraint_dims._EDGE_MID` gains `face_l -> mid_l`, `face_r -> mid_r` (`_MID_TO_EDGE` derives). A face/face or face/centerline/gridline parallel pair then classifies as `dim_point_line [second pick's mid, first pick's edge]` -- same graphics, `measure_key` (D56 duplicates), paste and persistence as any D81 dim. Non-parallel faces still take the angle path. | Phase 3 S1 |
| WF3 | **Typed value moves the second pick as a whole wall (Q1).** `_pl_apply` today returns None (least change) when the midpoint's edge has derived ends. New adapter hook `translate_raws(it, h) -> tuple[int, ...] | None`: the raw variable indices that translate the item rigidly when point handle *h* is driven along a normal; `_WallAdapter` returns `(0, 1, 2, 3)` for `mid`, `mid_l`, `mid_r`; the base adapter returns None (today's behaviour). `_pl_apply` uses it when the edge ends are not raw: all listed raws shift by the same normal delta; the line (refs[1]) is held as today. A wall held elsewhere (Fix, tied ends, another dim) still yields to the solver's conflict / least-change handling. | Phase 3 S1; grill Q1 |
| WF4 | **Same-wall thickness refused (Q5).** `_dim_refusal`: a `dim_point_line` whose point is `mid_l` / `mid_r` of uid U and whose line is the other face of U -> `DIM_WALL_THICKNESS_STATUS` = "Thickness is a wall property -- edit it in the panel" (new constant in `constraint_controller.py`, next to the other `DIM_*_STATUS` texts, which live there -- `constants.py` holds none). Status posted, pick resets, tool stays live (D77 refusal shape). The own-face vs own-centerline pair (half thickness) takes the same row. | grill Q5 |
| WF5 | **Per-press snap capture.** At each wall press (`_press_wall`) the controller resolves the scene's `_snap_result` through a new `auto_constrain.resolve_wall_snap` = `resolve_snap` plus one case it cannot express once WF1 hides the face midpoints: a MID snap on a hidden `mid_l` / `mid_r` resolves to that **face edge** target (`resolve_snap` matches point snaps against visible handles only). The controller owns no state (behaviour-home rule, `test_wall_state_stays_scene_side`): the start click's target is stored scene-side as `scene._wall_start_target` (initialised with the other `_wall*` transients, reset in `clear()`), the end click's target is a local of the end press. The shipped read `GeometryDrawingController._capture` already performs the same press-path read. A chained continuation's start inherits no target (its start is the previous end, which carries its own records). Rect mode and a typed-HUD completion capture nothing (unchanged). Targets whose `ref["uid"]` is not a visible `WallSegment` in `scene._walls` are ignored. | Phase 3 S2; P4 precedent `geometry_drawing_controller._capture` |
| WF6 | **Join priority = ordered passes.** `_auto_join_wall(wall, targets=(start, end))`: Pass 1 endpoint within `AUTO_JOIN_TOLERANCE` (snap + coincident, today) > **Pass 1b** captured target is a host point `p1l` / `p1r` / `p2l` / `p2r` -> `coincident [end drawn handle, corner]`, no snap move > **Pass 1c** captured target is a host edge `face_l` / `face_r` -> `point_on_curve [end drawn handle, face]` only -- a PER snap places the click and records no `perpendicular` (smoke ruling 2026-10-30, reversing the as-designed PER row; `plan_joins` gets no incoming edge), no snap move > Pass 2 click line within `TEE_TOLERANCE` (snap + PD3 tee, today). An end claimed by a pass is skipped by later ones (`snapped`). Records via a new `plan_wall_face_join(wall, idx, target)` = `plan_joins(wall uid, wall_drawn_handles(wall)[idx], None, target)` (no incoming edge). | Phase 3 S2; grill Q2 / Q3 |
| WF7 | **Behaviour change (thin hosts).** A host thinner than 2 x `TEE_TOLERANCE` used to pull a named face click to its centerline in Pass 2; Pass 1c now wins for a named face / corner. Unnamed clicks (no OSNAP, or an OSNAP on another item) behave as today. | Phase 3 S2 |
| WF8 | **Rendering.** A face-line end is already a render tee (`_tee_host`, true-centerline band half-thickness + `MITER_TOL`) coped to the near face: no change. A **corner-pinned** end is neither a tee (within `MITER_TOL` of the host end projection) nor a miter partner (the host's centerline end is half a thickness away): it draws as a square-capped free end meeting the host corner, bodies overlap-filled. Accepted for v1; a miter / clean-up rule is a follow-up. | Phase 3 S2 (user accepted) |
| WF9 | **Off-span (Q6).** A face-tied end lives on the face's infinite line (point_on_curve semantics); sliding the host past it leaves the end on the line past the host corner, square cap, no red state, no clamp. | grill Q6 |
| WF10 | **Legacy (Q7).** No retro records on open. Manual Coincident (point + face edge) ties a legacy end today and is the documented fallback. | grill Q7 |
| WF11 | **Status / panel text.** A face dim lists as the shipped `Smart Dimension · <value> mm` row; the placement records list as `Coincident` rows -- the shipped label of both `coincident` and `point_on_curve` (`sketch_model.TypeSpec`); no new labels. | Phase 3 |

## Acceptance Criteria

- [x] AC1 Smart Dimension, face of wall A then parallel face of wall B, places a `dim_point_line` reading the clear distance; typing a value moves B by the full delta (both ends, length and direction kept) and A holds; a B held by Fix or a tied end yields to today's conflict / least-change path.
- [x] AC2 Face then the other face of the same wall: status `DIM_WALL_THICKNESS_STATUS`, no record, tool live.
- [x] AC3 Wall line started (and, separately, ended) on a host face line or face midpoint: `_pt` exactly at the click, record `point_on_curve [new drawn end, host face_l|face_r]` and no `perpendicular` on any snap (PER included), gate honoured (toggle XOR Shift), Center / Left / Right hosts.
- [x] AC4 Same on a host face corner: record `coincident [new drawn end, host p1l|p1r|p2l|p2r]`, no snap move.
- [x] AC5 After AC3, moving the host perpendicular (grip drag through the real view) moves the tied end onto the new face line; sliding it off-span leaves the end on the line with no red constraint.
- [x] AC6 No new pick markers: `item_handles(wall)` yields no `mid_l` / `mid_r`; the pick-mode marker count on a wall is unchanged.
- [x] AC7 Opening a saved file adds no records (constraint count equals the file's).
- [x] AC8 Pass order: an end within `AUTO_JOIN_TOLERANCE` of a host endpoint AND named on a face corner takes the endpoint join (Pass 1), not 1b.
- [x] Testing: e2e on the shown MainWindow via the real Smart Dimension button and posted face clicks (`tests/test_plan_constraints_e2e.py` pattern); placement via the real press path with a staged `scene._snap_engine.find` (a press recomputes `_snap_result` inside `get_effective_position`, so the engine, not the result, is staged; line / midpoint / corner x Center / Left / Right); refusal asserts the status text; every guard RED-proved with the change reverted (`shared/red-proof.ps1`).

## Verification Checklist

- [x] All acceptance criteria met
- [x] Keep-green set (1b report) green (final coupled set 298 passed); full suite skipped by the standing Large-tier ruling (no VC6)
- [x] No regressions: Pass 1 / Pass 2 parity tests (`test_wall_placement_slice_parity.py`, `test_auto_constrain_wall.py`) unchanged
- [x] Account: pointers in the three governing specs; W1 row amended (hidden `mid_l` / `mid_r`); rows here flipped to built with the commit

## Existing Code Context

- `sketch_adapters._WallAdapter` (points / edges / `_offsets`), `_LineAdapter.mid_names`, `_Adapter.hidden_names`, `_mid`.
- `constraint_dims._EDGE_MID`, `edge_mid_name`, `mid_edge_name`, `_parallel_refs`, `mid_parallel`, `measure_key`, `classify_dim`.
- `constraint_controller.PickState._candidates` / `hover_at`, `dim_precheck`, `_dim_refusal`, `_pl_apply`.
- `auto_constrain.item_handles`, `resolve_snap`, `Target`, `plan_joins`, `wall_drawn_handles`, `plan_wall_join`, `plan_commit`.
- `wall_placement_controller._press_wall`, `_auto_join_wall`, `_propagate_wall_endpoint`, `_coincident_tied` (PD5 end sets already include `p1l` / `p1r`).
- `wall.WallSegment.snap_geometry` (face names), `_tee_host`, `nearest_centerline_point`, `endpoint_near`.
- `geometry_drawing_controller._capture` (press-path `_snap_result` read precedent).

## Edge Cases & Error Handling

- Face then a **gridline** or another wall's **centerline** (parallel): D81 row via the hidden mid -- allowed, reads face-to-line.
- Face then an **end cap** (`end1` / `end2`, perpendicular): angle path as today.
- Both passes 1b / 1c on the **same end** cannot happen (one target per press).
- Start and end on the **same host** (a wall drawn along a face): two `point_on_curve` on one face -> collinear-ish; the solver accepts (a line on a line), as two point-on-edge records on a line do today.
- A face target whose host is **hidden** or no longer in `_walls` is dropped silently (`resolve_snap` returns None for a source without an adapter; the pass re-checks `isVisible()`).

## Follow-ups (filed at Phase 6)

- `[type:design]` Midpoint constraint (SolidWorks-style) and retire the D58 derived-midpoint pick nodes (grill Q4).
- Reconcile the open "typed Smart Dimension on a wall's length resizes about the midpoint" task with the WF3 second-pick rule.
- Corner-pinned end miter / clean-up (WF8).
- Rect mode and HUD completions: face targets (WF5 scope).
