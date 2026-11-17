---
status: proposal
last-verified: 2026-11-15
verified-commit: 65077f82
applies-to:
  - firepro3d/hosted_tag.py                 # new: anchor / pose / resolve / offset helpers
  - firepro3d/tag_placement_controller.py   # new: "tag" mode (hover preview, click place)
  - firepro3d/block_instance.py             # `tag` record seam (save, place_kwargs, translate -> offset, leader paint, rows)
  - firepro3d/hosted_dependents.py          # push / refresh_all_bound tag branch
  - firepro3d/system_blocks.py              # Wall / Door / Window / Opening categories + defaults
  - firepro3d/system_blocks/Tags/           # WallTag / DoorTag / WindowTag / OpeningTag .fpdb
  - firepro3d/text_leader.py                # Note leader geometry + rows, reused for tag leaders (D9 / D10)
  - firepro3d/model_space.py                # mode dispatch, place_block_instance(tag=)
  - main.py                                 # Tag button + Leader toggle
source-tasks: ["SB6 — Placed tags (todo_open.md, [P1])"]
---

# SB6 Placed Tags — Design Spec

Concept (history, ratified 2026-09-29): [`2026-09-29-system-blocks-concept-design.md`](2026-09-29-system-blocks-concept-design.md) Q2 / Q3 / Q5 / Q12 / F7 / G4.
Hosting foundation: [`element-parameters.md`](../../specs/element-parameters.md) "Hosting (SB5)". Owning spec after build: [`system-blocks.md`](../../specs/system-blocks.md) (new placed-tags section at Account).

## Goal

A user tags walls, doors, windows and openings on a plan: the Tag tool previews the host category's default tag at the cursor, a click places it, and the tag then follows its host, shows live host data, dies with it, and optionally draws a leader to it.

## Motivation

Placed tags are build phase 6 of the System Blocks concept: the first hosted annotation the user places (intrinsic labels are automatic). They are the Revit-style way to call out wall types and door / window marks on construction drawings, and the base for sheet tags (SB7).

## Architecture & Constraints

- **A tag is a `BlockInstance` with `_host_uid` set and a `tag` record** (precedents: the Note block's `note` record, the gridline-hosted `host` record). Everything that iterates `_block_instances` — selection, annotative sizing, sheet viewports, save / load, paste remap and host-gone skip, delete cascade, the dangling "?" placeholder and the load notice — applies unchanged.
- `tag` record: `{"offset": [u_mm, v_mm], "orientation": "horizontal" | "aligned", "leader": null | {"knee": [u_mm, v_mm] | null}, "block": <swapped block id> | null}`. `u` runs along the host direction, `v` along its normal, both in mm from the host anchor. Saved by `to_dict` under `"tag"`; carried by `place_kwargs`; absent on every non-tag block (sparse).
- `hosted_tag.py` (pure helpers, no Qt state):
  - `anchor(host) -> (QPointF, angle_rad)`: Wall = centreline midpoint (`centerline_pt1` / `centerline_pt2`), `centerline_angle_rad()`; WallOpening (door / window / opening) = `center_on_wall()`, host wall angle.
  - `pose(tag_rec, host, ppm) -> (x, y, rot_deg)`: anchor + R(angle)·offset; rot = 0 (horizontal) or the host angle (aligned).
  - `offset_from_scene(tag_rec, host, ppm, scene_pt)`: the inverse, used by placement and drag.
  - `resolve(tag_rec, host, scene) -> block_id`: the swapped `block` when its `host_category == category_of(host)`; otherwise drop it and return `annotation_block(category_of(host))`.
- Host categories come from `element_params.category_of` (Wall, Door, Window, Opening — all already registered).
- Units: geometry mm internally; offsets stored in mm, converted with the scene's ppm at pose time.

## Design Decisions

| # | Decision | Rationale / rejected |
|---|---|---|
| D1 | Tag = `BlockInstance` + `tag` record | Rejected: `HostedTagItem(BlockInstance)` subclass (needs a factory dispatch at every construction site: load, paste, undo restore, section copies); standalone item (re-implements selection, serialization, paste, cascade, sheet render). User approved 2026-11-15. |
| D2 | Offset in the host-anchor frame (u along, v normal), mm | Concept Q3: the tag keeps its offset in the host frame when the host moves or rotates. |
| D3 | Re-pose at every committed step: `hosted_dependents.push` and `refresh_all_bound` gain a tag branch (`pose` + `resolve`) | Matches SB5 Q10 (refresh at `push_undo_state`); undo / redo rebuild every block. **As-proposed, pending P4:** whether the tag follows *live* during a host drag — plan step 1 probes the wall / opening drag paths; if no cheap hook exists, the tag catches up on release. |
| D4 | Tag drag = offset only | Concept Q3. A tag's `translate` / manipulator bake recomputes `offset` via `offset_from_scene`; the host is untouched. Tags have no free rotation (Rotate tool leaves them; the Orientation row replaces it). |
| D5 | Orientation row: Horizontal (default) / Aligned to host | Ruling R2. Aligned = host angle; `keep_upright` text in the shipped blocks flips past 90°. |
| D6 | Category change drops a swap, re-resolves to the new default | Ruling R8 + concept Q3. The four categories always resolve (SYSTEM_DEFAULTS), so "?" only appears through a dangling host (SB5 placeholder). |
| D7 | Tool: `"tag"` mode in `tag_placement_controller.py`, opening-mode shape | Reuse sweep: `_move_opening` / `_press_opening`. Host lookup by shape hit, openings before walls (a door sits inside its wall). Ghost = `_is_ghost` BlockInstance of the resolved block at the cursor with the current orientation, traced **at the size the placed tag will have** (the off-scene prototype gets no annotative factor of its own; smoke 2026-11-16 found it drawn at authored mm, a sub-pixel dot). Click places via `place_block_instance(..., tag=...)` with `offset_from_scene(click)`; stays armed; Esc exits (R3, R5). Non-taggable hover: no ghost, status hint. |
| D8 | Ribbon: Architecture › Annotations gets **Tag** (mode button, new `tag_icon.svg`) and a checkable **Leader** toggle (default off) | Ruling R5; `_mode_btn` helper. The toggle sets whether new tags get `leader: {knee: null}`. |
| D9 | Leader = a Note leader (`text_leader` record and geometry): a shoulder leaves a tag-box edge at a right angle (`edge`, `t`, `shoulder_mm` in the tag-box frame), then a straight run knee → tip. The knee grip re-solves the edge (`solve_knee`), as on Notes. The **tip is a free grip** stored in the host frame (`tip: [u_mm, v_mm]` from the host anchor), so it follows the host; a new leader's tip defaults to the host anchor and its shoulder to `default_leader`. Drawn by the BlockInstance when `tag.leader` is set. | Concept Q12 (the leader belongs to the tag item). **Revised 2026-11-16 at smoke (FP1 re-entry):** "leaders act like Note leaders" — the shoulder/knee geometry and the free tip were chosen; 3-click placement was not (the tag click places the tag; Leader on gives the default leader). Supersedes the as-built straight anchor → block-origin leader with a host-frame knee. |
| D10 | Leader End + weight live **on each tag** (`tag.leader.end` default `system-endtypes-arrow`, `tag.leader.weight` default "" = the Notes fallback), edited by Leader End / Leader Weight Properties rows (`text_leader.panel_rows` / `set_panel_row`), as on Notes. No Display Manager row. | **Revised 2026-11-16 at smoke (FP1 re-entry), reversing ruling R4:** the DM "Tags" row (and its `paper_display` cache, project/QSettings save and apply) is removed; per-tag rows replace it. The branch never shipped, so no saved file carries the DM key that needs migrating. |
| D11 | Per-tag block swap: a property row using `annotation_choices.choices(scene, category)`; writes `tag.block` then re-resolves; undoable | Concept Q5. Needs a block-id setter on BlockInstance (GAP). |
| D12 | Shipped blocks: `Tags/WallTag`, `DoorTag`, `WindowTag`, `OpeningTag` — `@[Mark]` in a hexagon / circle / square / rounded box; Annotative, `host_category` set; ids `system-tags-<name>` | Ruling R6. **Mockup gate = plan task 1:** the four blocks are authored first and approved by the user in the running app before the rest is built; then a G7 pixel lock. |
| D13 | `ANNOTATION_CATEGORIES`, `SYSTEM_DEFAULTS`, `LABEL_FIELD` gain Wall / Door / Window / Opening | Reuse: the Project Settings Annotation pane gets four rows for free. |
| D14 | Views: plan, detail views and sheet viewports of them; not elevations / sections | Ruling R7; level-scoped model annotation (concept Q2). Section copies (`section_scene`) must skip tag blocks. |

## Acceptance Criteria

- [ ] AC1 Tag tool (Architecture › Annotations): hover over a wall / door / window / opening previews that category's default tag at the cursor; hover elsewhere shows none; click places one tag bound to the host uid; tool stays armed; Esc exits.
- [ ] AC2 Leader toggle off → no leader; on → a Note-style leader: a shoulder off a tag-box edge, then knee → tip at the host anchor. Dragging the knee re-picks the edge as on Notes; dragging the tip moves it anywhere, and it still follows the host. Leader End and Leader Weight rows in the tag's Properties restyle that tag's leader (undoable). (Revised 2026-11-16, D9 / D10.)
- [ ] AC3 Host move / rotate / grip edit through the real tools → the tag keeps its host-frame offset; Horizontal tags stay level; Aligned tags rotate with readable text.
- [ ] AC4 Host data edit (e.g. Mark) → tag text updates; host delete through every cascade path removes its tags in the same undo step; one Undo restores both re-linked.
- [ ] AC5 Dragging a tag changes only its offset; the host is unchanged.
- [ ] AC6 Tag block row swaps among same-category blocks (undoable); host category change re-resolves to the new default.
- [ ] AC7 Save / load and undo / redo round-trip `host_uid` + `tag` record; dangling host on load → "?" + the existing load notice; paste follows SB5 remap / skip rules.
- [ ] AC8 The four shipped tag blocks pass the user's in-app mockup gate (task 1) and a G7 pixel lock.
- [ ] AC9 Tags print at their authored size in sheet viewports at two scales (G3) and do not appear in elevations / sections.

## Verification Checklist

- [ ] Guards per AC, each shown RED with its rule reverted (VC3).
- [ ] Keep-green: `test_sb5_*.py`, `test_hosted_blocks_*.py`, `test_sb2a_binding.py`, `test_sb3_parity.py`, `test_sb4a_hide_empty.py`, Note-block / text-leader tests, Display Manager tests.
- [ ] Full chunked suite (VC6); seam review (VC9); user smoke of AC1–AC9.

## Edge Cases & Error Handling

- Host deleted outside a cascade path (e.g. detail-marker removal — filed P3 follow-up) → the tag dangles and shows "?" (SB5 placeholder); not fixed here.
- Opening re-hosted to another wall → anchor recomputed from the opening; offset kept.
- Wall split / merge → the uid follows SB5 transfer rules; a tag on a removed half dangles ("?").
- Tag pasted alone → stays on its original host (SB5); host gone → skipped with a footer reason.
- Several tags per host → independent records.
- Tag on a hidden level → hidden with the level's plan items.

## Testing (VC3 guards)

- G4 lifecycle: real Move / Rotate / grip / Delete / Undo on a wall and a door; assert tag scene pos = anchor + R·offset computed from the raw wall endpoints, and presence / absence after delete / undo.
- Tool: posted mouse moves / press on a shown view in `"tag"` mode → ghost over a wall, none over empty space; press → one tag with the wall's uid; mode still `"tag"`.
- Round-trip: save → load and undo → redo compare tag records.
- Drag: manipulator drag changes `tag.offset` only; wall endpoints unchanged.
- Leader: shoulder leaves the tag-box edge at a right angle (ink on the shoulder, none on the old straight path); knee drag re-picks the edge; tip drag moves the arrow and the tip follows a host move; the tag's Leader Weight / Leader End rows change its pen width / End (pixels), undoable.
- Ghost: the hover ghost's traced size equals the placed tag's size (not authored mm).
- Re-resolve: door → window changes the resolved block id; a swap is dropped.
- Views: section scene builds no copy of a tag block.
