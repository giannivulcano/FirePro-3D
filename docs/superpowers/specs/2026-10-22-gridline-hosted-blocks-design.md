---
status: proposal
last-verified: 2026-10-22
verified-commit: 6c122632
applies-to:
  - firepro3d/block_instance.py
  - firepro3d/gridline.py
  - firepro3d/section_scene.py
  - firepro3d/elevation_view.py
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/model_browser.py
  - firepro3d/scene_io.py
source-tasks: ["todo_open.md: Blocks placed in section and elevation views, hosted on a parallel reference gridline + offset [P2]"]
---

# Gridline-Hosted Blocks in Section / Elevation Views -- Design Spec

Consolidating contract (Rule A): the seven specs listed under "Spec reconciliation" get a
one-line pointer here at Account; their full rewrites are a filed follow-up.

## Goal

A user working in a section or elevation tab can drop (or activate-and-click) a block into
that view. The block is drawn there at true size and survives rebuild, save/reload and
undo, and it plots on sheets. It is used both for annotation symbols and as a stand-in for
equipment that isn't modelled (G1).

## Motivation

Sections are rebuilt from the model on every change (`SectionScene.rebuild()` clears and
re-projects), so nothing placed only in a section survives. Mid-grill (2026-10-22) the user
reframed the task. A block placed in a section is **model data hosted on a reference
gridline parallel to the cut plus a normal offset**, the way a plan block is hosted on a
level. So every parallel view shows the same block, and it moves with its gridline. The
original "view-owned" framing is superseded.

## Architecture & Constraints

- `view-relationships.md` s5.3 hosting pattern 2 holds: sections *materialise* model data.
  No third hosting pattern is introduced.
- Model plan blocks are still not projected into sections (G19, "fork B" stays out of scope).
- One undo stack (`Model_Space._undo_stack`). Every user edit here is one `push_undo_state`.
- Geometry in mm. Section scene frame: x = h, y = -z (the gridline/datum convention).
- Additive save keys only. No `SAVE_VERSION` bump (D4 precedent).

## Design Decisions

Ratified by the 2026-10-22 Phase 2 grill (G1-G20) and Phase 3 section approvals (D1-D11).

### Approach (D1)

Approaches considered:
- **A (chosen):** an ordinary `BlockInstance` with a `host` record that stays in the plan
  scene, hidden there. Sections draw copies of it.
- **B:** the gridline owns its blocks as child records.
- **C:** each section owns its blocks (view-owned; rejected by the reframe).

*Because* A reuses undo, scene_io, the browser Blocks group, paper categorisation and
`place_refusal` as-is. B would duplicate all of those for a second block kind, which is
the redundancy the reuse rule exists to prevent.

### D2 -- Host record on `BlockInstance`

`host = {"gridline": <uid>, "offset_mm": float, "along_mm": float, "elevation_mm": float,
"facing": +1 | -1}`. It is optional: `to_dict` writes it only when set. `from_dict` and
`place_kwargs` carry it, so the undo "blocks" path and scene_io "blocks" path round-trip
it unchanged.

- `offset_mm` is the signed perpendicular distance from the gridline plane. + is the left
  side walking bubble1 -> bubble2, fixed to the gridline, so it reads the same value in
  every view (G3, G4).
- `along_mm` is measured from the gridline origin along its unit direction u.
- `elevation_mm` is an absolute z. A level elevation change does not move it (G13).
- `facing` is the n-side the placing section looked from (D4).
- Plan `pos` is *derived*: `origin + along*u + offset*n`. It is recomputed by D5 and
  never edited directly, so the host record is the single source of truth.
- `level` stays on the instance (for code that reads it) but carries no meaning for a
  hosted block. **C3 amendment:** a gridline-hosted instance is gridline-scoped, not
  level-scoped. Its z range comes from `elevation_mm`.

### D3 -- Gridline uid

`GridlineItem._uid = uuid.uuid4().hex` (the `BlockInstance` convention), saved as
`"uid"` in the gridline dict.
- Files without one get a fresh uid on load.
- Copy/paste and Array give the copy a new uid.
- Undo restore preserves uids.
- `Model_Space.gridline_by_uid(uid)` resolves hosts.

*Because* labels are not unique (`check_duplicate_labels` only recolours bubbles), so a
label reference could attach blocks to the wrong gridline.

Damaged hosting: a hosted block whose uid does not resolve on load is dropped, and the
status bar reports the count. Normal editing cannot produce one (D7).

### D4 -- Facing

A section whose look side matches `facing` draws the block as placed. One looking from the
other side draws it mirrored left-to-right: `mirrored` is flipped and the rotation negated
(G5; text reads backwards, accepted). *Because* without a stored facing, a block could
render mirrored in the very view it was placed in.

### D5 -- Single follow point

`GridlineItem._rebuild_geometry()` (the single writer of the drawn line) ends by calling
`scene._sync_hosted_blocks(self)` when the scene has the method. That method recomputes
derived `pos` for every block hosted on that uid.
- It covers translate, `manip_rotate`, Origin X/Y/Angle property edits,
  `move_perpendicular` / `set_perpendicular_position` and grips (G10).
- Rename changes nothing, because hosting is by uid.
- Locked gridlines already refuse every mutator.
- Gridlines have no mirror or scale op.
- Sections refresh through the existing `sceneModified -> _schedule_rebuild`.

### D6 -- Grip 0 compensation

`apply_grip` index 0 slides `_origin` along u with the far end fixed. Before rebuilding, it
subtracts the origin's axial shift from each hosted block's `along_mm`, so the blocks stay
in place. Grip 1 (length) and grips 2/3 (bubbles) do not touch `_origin`, so hosted blocks
are unaffected (G10: end/bubble drags don't move blocks). *Because* the probe showed grip 0
moves the origin, which falsifies "anchor at origin" as a complete mechanism.

### D7 -- Delete cascade

`_bulk_delete` gains a gridline -> hosted-blocks step, modelled on the wall -> openings
cascade, in the same undo step. Status: "Deleted gridline B and N hosted blocks". Undo
restores the gridline (same uid) and the blocks (G11).

### D8 -- Section projection

`SectionScene.rebuild()` gains `_project_hosted_blocks()` after the walls step. For each
hosted model block:
- **Parallel test:** draw it only when its host gridline is parallel to the cut, using
  the same test as `_gridline_crossing_h`. That covers cardinals and placed sections alike
  (G5).
- **Position:** h is the lateral projection of the derived world point; depth is its
  distance behind the cut; the scene position is (h, -elevation_mm).
- **Depth crop:** draw only when 0 <= depth <= the section depth, and register with
  `_register_depth_item` for painter order (G6).
- **Lateral clip:** the copy is a child of a clipping parent rect spanning [h_A, h_B],
  using `ItemClipsChildrenToShape` (G7). Vertical clip comes with todo 978.
- **The copy:** a `BlockInstance` built from the model record, posed in section coords,
  `_ROLE_SOURCE` = the model block, made selectable for halo / manipulator like the other
  section copies. Paper categorisation is free (`isinstance BlockInstance -> "Blocks"`).
- **Display:** on screen, Model "Blocks" weight, always visible. On a sheet, the paper
  "Blocks" row, visibility included (G17 corrected: no on-screen Blocks visibility toggle
  exists).
- **First plan step (P4):** probe that a `BlockInstance` paints in a `SectionScene`
  (`z_range_mm` reads `scene()._level_manager`) and that `apply_paper_overrides` still
  matches it under the clipping parent. Fallback: a thin copy class built on
  `_ElevReadOnlyProxyMixin` that reuses the block painter and sets `_paper_cat = "Blocks"`.

### D9 -- Placement in a section

- **Drag-drop:** `SectionView` accepts `MIME_BLOCK`. `_block_payload`,
  `_resolve_block_drag` and `_block_drop_target_ok` move from `Model_View` into a shared
  mixin. `_BLOCK_DROP_ROLES` gains `"section"`, and `place_refusal` still gates.
- **Activate + click:** activating placement with a section tab active enters a section
  placement mode: ghost, Space rotates, click places, Esc cancels (G16). The ghost
  lifecycle (`_place_block_make_ghost` / `_refresh_ghost` / `_drop_ghost`) moves out of
  `Model_Space` into a helper both scenes use. The plan traces every library entry point
  to its hand-off.
- **Host choice:** the parallel gridline nearest the cut with 0 <= depth <= section
  depth, inside [h_A, h_B]. Offset 0; along from cursor h; elevation from cursor v;
  facing from this section's look side (G8).
- **Refusal:** with no such gridline the drop is refused (no-drop cursor) and a click does
  nothing. Status: "Can't place here -- a block in a section needs a gridline parallel to
  the cut inside the view's depth." (G9)
- **Snap:** level datums, gridline verticals and their crossings, using the plan snap
  tolerance in screen px (G15). P4 probe: whether the snap engine accepts
  `ElevGridlineItem` / `ElevDatumItem`. Otherwise a section snapper limited to those
  three targets.
- **Commit:** `Model_Space.place_block_instance(..., host=...)` + `push_undo_state()`.

### D10 -- Editing in a section

(G14; full modify tools and copy/paste are a filed follow-up.)
- **Select:** a copy picks via `_ROLE_SOURCE`. `entitySelected` emits the model block,
  and the Properties panel shows it.
- **In-plane drag:** the manipulator move maps (dh, dv) to `along_mm` (via the sign of
  the section's h relative to u) and `elevation_mm`. Host and offset are fixed. One undo
  step on release.
- **Delete:** `_delete_elev_selected` routes hosted copies to
  `Model_Space.delete_items([model])`.
- **Property rows (G13):** X/Y and Level are hidden. Shown instead:
  - Reference (dropdown of gridlines parallel to the current host)
  - Offset (signed, mm)
  - Elevation (absolute)
  - Rotation, Mirrored, Scale, Linetype, Weight and attributes, as in plan

  One undo step per edit.
- **Re-host (Reference change), option A:** the offset keeps its value, now measured
  against the new gridline's n (G4 sign). `along_mm` is recomputed so the block's h is
  unchanged. Elevation is unchanged. `facing` is recomputed so the viewing side is
  preserved. *Because* the block stays put on screen in head-on views and only its depth
  changes, which is the useful result when re-hosting.

### D11 -- Hidden in plan and 3D

The LevelManager block passes (`_set_level_vis`) hide any instance with a `host`,
whatever the level or view range (G12). A P3 consumer sweep in the plan covers every plan
path that walks `_block_instances` directly (select-all, select-similar, filters), so a
hidden hosted block can't be picked up and moved in plan. 3D already defers blocks
(`view_3d.py`), so nothing changes there.

### Browser (G18)

The Model browser's flat "Blocks" group shows hosted blocks as `<name> (on <label>)`.
Clicking a row selects the model block and focuses a view that shows it: an open tab, else
the cardinal, else the first placed section by name. In that view the copy is selected.
None -> status: "No section shows this block (its gridline <label> isn't parallel to any
view)."

## Acceptance Criteria

Guards drive the real path and assert ground truth; each is shown RED with its rule
reverted (VC3).

- [ ] AC1 Drop/click in a section with a parallel gridline in depth: the model gains one
      hosted block (host uid = the nearest parallel gridline, offset 0, elevation = cursor
      v, facing = the view side). It is drawn in that section, hidden in plan.
- [ ] AC2 No parallel gridline in depth: refused, status text shown, model unchanged.
- [ ] AC3 Drawn head-on in every parallel section (cardinal + placed); absent in a
      perpendicular one.
- [ ] AC4 A view from the other side draws it mirrored.
- [ ] AC5 Depth crop: not drawn in front of the cut or beyond the depth; painter-ordered
      by depth.
- [ ] AC6 Lateral clip at h_A / h_B.
- [ ] AC7 Host edits:
      - move/rotate/typed origin -> the block follows
      - grip 0 / grip 1 / bubble drags -> the block stays
      - rename -> still hosted
      - delete -> cascade with status count; one undo restores both
- [ ] AC8 Property edits: Offset, Elevation, Reference (option A semantics), Rotation /
      Mirrored / Scale, each one undo step.
- [ ] AC9 In-plane drag changes along + elevation only.
- [ ] AC10 Save/reload round-trips `host` and gridline `uid`. A legacy file gets uids. An
      unresolved host is dropped with a status count.
- [ ] AC11 Undo/redo of placement, drag and delete.
- [ ] AC12 Sheet export: the hosted block plots (digest guard). Hiding the paper "Blocks"
      row removes it.
- [ ] AC13 Browser: `(on B)` label. Click focuses the right view and selects the copy; the
      no-view status otherwise.
- [ ] Live smoke in the running app (VC8).

## Verification Checklist

- [ ] All AC guards green, each shown RED with its rule reverted
- [ ] Keep-green set (VC5): block, gridline, section, scene_io, undo, model_browser,
      paper_display tests
- [ ] Full chunked suite on the final tree (VC6)
- [ ] D8/D9 P4 probes recorded in the plan's first step
- [ ] Account: pointers in the seven specs below; C3 amendment; stamps

## Edge Cases & Error Handling

- **Anti-parallel gridline** (angle differs by 180 degrees): parallel for the D8 test.
  Facing is evaluated against that gridline's own n.
- **Locked host:** the gridline can't move, so its blocks don't either. The block itself
  can still be dragged in-plane.
- **Gridline copy/Array:** the copy gets a new uid and no blocks (blocks stay on the
  original).
- **Host deleted then undone:** the uid is restored, so hosting resolves.
- **Two parallel gridlines equidistant from the cut:** the first in model order wins
  (deterministic).
- **A section rotated to non-parallel after placement:** the block simply isn't drawn
  there (AC3).

## Spec reconciliation (Account pointers)

`view-relationships.md` s5.3 (pattern 2 holds) - `model-space-containment-contract.md` C3
(gridline-scoped instances) - `block-system.md` (host record) - `grid-system.md` (uid +
cascade) - `section-view-subsystem.md` (projection + placement) - `scene-io.md` (additive
`host`, gridline `uid`) - `selection-mode.md` s14 (hosted copies in sections).

## Out of scope / follow-ups

- Full modify tools + copy/paste for hosted blocks (filed).
- Vertical clip (todo 978, +1 filed).
- An on-screen Blocks visibility toggle (not filed unless asked).
- Projecting plan blocks into sections (fork B).
