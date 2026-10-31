---
status: built             # BUILT 2026-10-31 (v0.77.0, feat/plan-block-constraints); Phase 3 approved 2026-10-31
last-verified: 2026-10-31
verified-commit: 35b55a2d
applies-to:
  - firepro3d/constraint_controller.py  # plan capability (+ BlockInstance), two-tier plan solve, ANCHOR_CID, on_definitions_changed, plan_ref_uids
  - firepro3d/sketch_adapters.py        # _NestedAdapter on plan instances; _ins_only (annotative -> ins only)
  - firepro3d/scene_io.py               # load resolves plan records through plan_ref_uids
  - firepro3d/model_space.py            # commit_block_definition / replace_block_references -> on_definitions_changed
  - firepro3d/block_instance.py         # solve write-back (set_block_pos / set_block_rotation) refresh (P4 probe)
source-tasks:
  - todo_open.md "Expose placed-block primitives to constraints in model space (plan scene), like the Block Editor's nested handles" [type:feature] [P1]
related:
  - docs/specs/parametric-constraint-system.md                       # governing spec (D2, D5, s5.1, s7.2, s8)
  - docs/specs/block-system.md                                       # instances, gridline-hosted instances, annotative sizing
  - docs/specs/model-space-containment-contract.md                   # C8 exception amended
  - docs/superpowers/specs/2026-10-24-editor-build-tabs-design.md    # s2 plan capability, L1 lock fixes, H1 hosted ride
  - docs/superpowers/specs/2026-10-15-nested-block-constraint-handles-design.md  # NB1-NB9 (adapter, naming, NB4 validity)
---

# Plan Block Constraints -- Design Spec

> Consolidating contract for this change (it spans the four specs under `related`). At Account each
> linked spec gets a one-line pointer here; their full in-place rewrites are filed as follow-ups.

## Goal

Lay out equipment in plan: a placed (level-scoped) `BlockInstance` offers its printed child
handles and its insertion point to plan constraints, so blocks can be tied to walls, gridlines and
each other (offset from a face, centred between gridlines, rows) and follow when the building
geometry moves -- while building geometry never yields to a block.

## Motivation

The Block Editor already constrains nested-instance handles (NB, 2026-10-15) and the plan scene
already constrains walls and gridlines (Editor/Build slice 2, 2026-10-27), but a placed plan block
offers nothing to pick mode, Smart Dimension or selection-first adds (`_plan_ref_types()` =
walls + gridlines). Equipment layout by dimension is the missing half of dimension-driven plan layout.

## Ratified requirements (Phase 2, grill Q1-Q9, 2026-10-31 -- not re-opened here)

AC1-AC8 and the out-of-scope list are recorded on the source task line. Phase 3 rulings that amend them:

| # | Ruling | Gate |
|---|---|---|
| PB1 | **AC4 restated:** gridline-hosted blocks (`BlockInstance.host`) take **no part** in plan constraints -- no handles, never in a solve, a record naming one drops on load; they still ride their gridline (H1). Reason: hosted blocks are never visible in plan (`block-system.md` "Gridline-hosted instances") and plan picks are visible-only (AC8), so "handles offered" was unreachable. Section-view block constraints -> follow-up. | Phase 3 FP1 (2026-10-31) |
| PB2 | **Annotative blocks offer `ins` only** (Scale with zoom and Fixed size alike); real-size blocks offer every handle. No re-solve on a drawing-scale change. | Phase 3 FP1 (2026-10-31) |
| PB3 | **Two-tier plan solve** (chosen over "fix walls on block edits only"): building-tier constraints solve as if no blocks existed; block-tier constraints then solve with every wall / gridline held. A block never pushes or holds a wall in any edit. | Phase 3 approach (2026-10-31) |
| PB4 | **Definition change hooks every swap path** (as built: `Model_Space.commit_block_definition` edit, `retarget_block_refs` swap, `reload_block_definition` reload, `load_blocks_from_files` load-replace each call `on_definitions_changed()`; supersedes the s3 hook-site names). | Phase 4 gate (2026-10-31) |
| PB5 | **Plan Auto Constrain never ties a block:** plan joins filter block instances out (`auto_constrain`); Auto Constrain on block placement stays a follow-up (Q6). | Phase 4 gate (2026-10-31) |
| PB6 | **Drag stage-2 failure holds the drag-start pose:** when stage 2 cannot converge mid-drag the blocks keep their drag-start pose (`stage2_failed` describes the last good frame) and their ties go red on release. | Phase 4 gate (2026-10-31) |

## Architecture & Constraints

- Governing spec `parametric-constraint-system.md`; the plan capability (`ref_types`), wall / gridline
  adapters, L1 lock fixes, persistence and undo are owned by the editor-build-tabs design s2.
- **One adapter seam (NB9 Approach A):** plan blocks use the existing `_NestedAdapter`; pick mode,
  glyph anchoring, dim kinds, validity, `remap_for_copy` and the build all read it -- no consumer edits.
- Pure core / Qt shell split unchanged (spec s3): tiering and anchors live in `constraint_controller`;
  `sketch_solver` is untouched.
- File format unchanged: `HandleRef.h` = `"<path>:<handle>"` / `"ins"` (NB3); no SAVE_VERSION bump --
  older builds drop block records on load (Q9, accepted).
- Containment: **C8 exception amended** -- plan records may reference walls, gridlines and
  level-scoped (unhosted) block instances. C1 unchanged (a block is a placed instance, not loose geometry).

## Design Decisions

### 1. Participation and handles

- `_PLAN_PARTICIPATING` gains `"_block_instances"`; `_plan_ref_types()` gains `BlockInstance`.
  `can_ref` rejects an instance whose `host` is set (PB1).
- Handles (AC1): `ins` + every printed child handle and nested origin through the pose (NB2/NB3);
  nested curves are `r_const` -- a driving radius / diameter dim is refused, a Reference one measures (NB7).
- `_ins_only(it)` (`sketch_adapters`): true when *it* is in the plan scene and its definition is
  annotative (`annotative.is_annotative`); `_NestedAdapter.points / edges / curves` then expose only
  `ins` (PB2). Block Editor nested instances are unaffected (annotative factor 1 there).
- Pose variables (AC2): x, y, rot (NB1); mirror and scale are table constants. Write-back:
  `set_block_pos`, `set_block_rotation` only past `ANG_WRITE_TOL`.
- **P4 (first plan step, unverified):** whether a solve write refreshes 3D, the section / elevation
  projection and bound attribute text as Move's `translate` + `push_undo_state` does; the probe
  compares both paths and adds the missing refresh to the write-back if they differ.
- `plan_ref_uids(scene)` -- one accessor (walls + gridlines + unhosted blocks) replacing the inline
  `_plan_uids` set in `SceneIOMixin` load and the plan branch of `ConstraintController.primitive_uids`.
- Picks stay visible-only; a block on a hidden level still solves (AC8, existing plan rule).

### 2. Two-tier plan solve (PB3; plan scene only -- the Block Editor stays single-tier)

- **Tier of a constraint:** *block tier* when any ref is a block instance (`_refs_an_instance`),
  else *building tier*.
- **Stage 1:** the building-tier active set, solved exactly as today (blocks are not in the System).
- **Stage 2:** the block-tier active set with every wall / gridline slot held by a fix per variable
  under `ANCHOR_CID = "__anchored__"`, appended after the builders (the L1 `LOCK_CID` seam). `conflicts`
  is only tested for emptiness and `redundant` / `to_records` drop `ANCHOR_CID`, as `LOCK_CID`.
  Focus = the edited items plus every building item stage 1 moved.

| Edit | Stage 1 | Stage 2 | Stage 2 unsatisfiable |
|---|---|---|---|
| Wall / gridline drag, Move, typed, grip | as today (`W_EDIT`) | blocks follow (goal = current pose) | the wall edit **commits**; blocks keep their pose; unsatisfied block constraints go red (`mark_unsatisfied_red`) at commit, not per drag frame |
| Block drag / Move / Rotate / typed Position / Rotation | skipped | edited blocks `W_EDIT`, walls held -> the block slides where its ties allow | hold-last-good = refused (D10 status); typed beyond `TYPED_TOL` refused (D31) |
| Mixed selection (walls + blocks) | walls are the edit | blocks are the edit, walls held at the stage-1 result | as the wall row |
| Add a block-tier constraint | -- | focus = its refs | red on admission (D38) |
| Add a building-tier constraint | as today | carries attached blocks | as the wall row |

- An unconstrained block never moves when a wall moves (no proximity follow for blocks; G10 is walls only).
- **Drag:** `begin_drag` caches one `(sys, slots, weights)` context per tier, so both stages reuse
  their System across frames (D18). The D18 drag bar stays the guard; one bench on a plan with walls +
  tied blocks (Phase 5 Performance rule: metric confirmed with the user first).
- **Diagnostics** per tier: block-tier diagnostics are built with the anchors, so a block's DOF is
  3 minus its own ties and a block tie never reduces a wall's DOF or makes a wall constraint amber.
- Unchanged: L1 locked gridlines, G10 wall proximity follow, H1 hosted ride.

### 3. Definition change, persistence, undo, copies

- **Definition edit / swap (AC5):** `Model_Space.commit_block_definition` (after
  `_block_registry.invalidate`, before its one `push_undo_state`) and `replace_block_references`
  (before its push) call `constraint_ctl.on_definitions_changed()`: `active()` re-validates every
  block record (NB4 -- a lost child handle -> inert, "Unsupported constraint" row, kept in the file,
  revived on undo); then a stage-2 solve over every block-tier component, walls held; an
  unsatisfiable record goes red. No separate undo step. Closes the plan half of the NB4 known gap.
- **Save / reopen (AC6):** the existing top-level `"constraints"` key; load resolves through
  `plan_ref_uids` (`_plan_record_resolves`), so a record on a hosted / missing block drops into the
  clean-drop count; a record whose block resolves but whose child handle is gone survives load and
  goes inert at `active()`.
- **Undo / redo (AC6):** the plan snapshot's `capture()` / `restore()`; red derived by `_unsatisfied`.
- **Delete (AC6):** `on_items_removed` cascades in the same undo step. *Plan probe:* the plan block
  delete path reaches it as the wall path does.
- **Copies (AC7):** Copy / Paste / Duplicate / Array / Mirror copy keep D30 / D97 (internal kept and
  remapped via `paste_items`' `uid_map`, outside ties dropped). *Plan probe:* the block branch writes
  `uid_map` in plan. Flip / Mirror / Scale in place keep the DD8 pose restore, then stage 2 re-solves
  with the block as the edit. Plan Explode stays refused.

## Acceptance Criteria

- [ ] AC1 A plan block offers every printed child handle + `ins` to pick mode, Smart Dimension and selection-first adds (annotative: `ins` only, PB2).
- [ ] AC2 The solve moves x y rot only; mirror / scale untouched.
- [ ] AC3 Walls / gridlines never yield to a block: a block edit slides only where its ties allow, a move needing building geometry to move is refused; a wall / gridline move carries its tied blocks; a block that cannot follow keeps its pose and its ties go red (PB3).
- [ ] AC4 (PB1) Hosted blocks take no part: never in `items()`, never moved by a solve, still ride a gridline move; a record naming one drops on load.
- [ ] AC5 A definition edit / swap re-solves resolvable block records inside its own undo step; a lost handle leaves its record inert, flagged, saved.
- [ ] AC6 Save / reopen, undo / redo and the Delete cascade carry block constraints.
- [ ] AC7 Copy / Paste / Array keep the D30 rule.
- [ ] AC8 Hidden-level blocks solve; picks visible only.

## Verification Checklist (VC3: real MainWindow / plan scene, each RED with the change reverted)

- [ ] G1 plan pick candidates include a block's child handles + `ins` (RED with `_plan_ref_types` reverted).
- [ ] G2 block corner -> wall-face distance, then a wall drag moves the block.
- [ ] G3 a block drag leaves the wall put and slides parallel; a move needing the wall to move is refused.
- [ ] G4 walls A / B with a block tied to both: dragging A moves A, the block holds, its tie goes red.
- [ ] G5 a Parallel tie rotates the block; mirror / scale unchanged.
- [ ] G6 hosted block: not in `items()`, never moved by a solve, rides a gridline move, its record drops on load.
- [ ] G7 annotative block offers `ins` only.
- [ ] G8 definition edit moving a constrained child re-solves in one undo step; deleting the child leaves the record inert, flagged, saved.
- [ ] G9 save-reopen / undo-redo / Delete cascade.
- [ ] G10 Copy keeps internal ties, drops outside ones.
- [ ] G11 hidden-level block solves, not pickable.
- [ ] G12 `ANCHOR_CID` never reaches `to_records`, conflicts or redundant.
- [ ] Keep-green (VC5): the constraint, nested-handle, plan-constraint, gridline-hosted, block-snap and paste test sets; full chunked suite (VC6); drag bench.
- [ ] User smoke: tie a block to a wall face, drag the wall, drag the block, edit its definition, save / reopen.

## Edge Cases & Error Handling

- Hosted -> level-scoped (or back) by a Reference / host edit: a block that becomes hosted leaves `items()` (PB1), so its records stop resolving -- never solved, dropped by the next save (`to_records` resolves against `plan_ref_uids`); undoing the host edit restores them with the snapshot.
- A definition becomes annotative after records name child handles: those records go inert (PB2 handle set shrinks to `ins`).
- Legacy definitions without primitive uids key handles positionally (existing `[type:maint]` line) -- unchanged.
- Missing / cyclic nested definition: no child handles, records go inert (NB edge case).
- A locked gridline is held in both tiers (L1 in stage 1, anchors in stage 2).

## Follow-ups (filed at Phase 4)

Auto Constrain on block placement (Q6); copies keeping outside ties (Q8); definition-flagged constraint
points (Q7 C); plan Explode remap; constraints on blocks in section / elevation views (PB1).

### Known gaps and follow-ups found at build (Phase 5-6, filed)

- **VC9 M2 (divergence from the PB3 edit table):** non-drag `_solve_two` refuses a no-edit solve whose
  stage 2 fails, where the wall row above says the wall edit commits and the ties go red. Filed as a
  `todo_open.md` bug; the table is the intended behaviour.
- **VC9 M3:** `on_definitions_changed` does not call `_recheck_red` (filed).
- **VC9 M4:** `_propagate_wall_endpoint` leaves stale ties (filed).
- **Plan wall-chain drag** costs about 2.2 s per frame at 200 walls -- pre-existing (found by the PB3 bench), filed.
- **Perf bars (Task 10, user-ratified 2026-10-31):** block tier <= 0.5 ms per tied block per frame (one wall +
  100 blocks); tied-vs-bare chain ratio <= 1.10. Guards: the perf tests in `tests/test_plan_block_constraints.py`.
- Account carried no SAVE_VERSION bump (Q9) and no ruling change to the s2 edit table beyond PB4-PB6.

## Existing Code Context

`constraint_controller`: `_PLAN_PARTICIPATING`, `_plan_ref_types`, `can_ref`, `items`, `active`,
`_refs_an_instance`, `_build` (L1 `LOCK_CID` fixes), `_solve` / `_solve_x`, `begin_drag`,
`mark_unsatisfied_red`, `_unsatisfied`, `_admit_in_order`, `capture` / `restore`, `on_items_removed`,
`primitive_uids`, `to_records`. `sketch_adapters`: `_NestedAdapter`, `_nested_table`, `adapter_for`.
`scene_io`: `_plan_record_resolves`, load's plan uid set. `model_space`: `commit_block_definition`,
`replace_block_references`, `_block_instances`, `paste_items`, `_shift_hosted_along`.
`block_instance`: `set_block_pos`, `set_block_rotation`, `host`, `on_definition_changed`.
`annotative`: `is_annotative`. `block_snap_geometry.posed_primitives`.
