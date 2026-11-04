---
status: proposal         # ratified 2026-11-04 (grill Q1-Q11 + design approval); unbuilt
last-verified: 2026-11-04
verified-commit: 660f7e75
applies-to:
  - firepro3d/text_leader.py      # new: pure leader geometry + ops
  - firepro3d/text_item.py        # leader fields, paint, bounds, grips, panel rows
  - firepro3d/block_definition.py # text_box_ops emits the leader stroke
  - firepro3d/block_attributes.py # bound_text_ops per-placement patch
  - firepro3d/block_instance.py   # note record, serialization, panel rows
  - firepro3d/level_manager.py    # apply_to_scene view_key filter; rename / remove hooks
  - firepro3d/paper_space.py      # viewport isolation key; paper panel rows
  - firepro3d/section_scene.py    # skip view-owned instances
  - firepro3d/detail_view.py      # delete_detail removes owned notes
  - firepro3d/model_space.py      # note mode, placement, edit session
  - firepro3d/text_edit_controller.py # Note edit overlay
  - firepro3d/system_blocks.py    # Note system id
  - firepro3d/system_blocks/Annotations/Note.fpdb # new shipped block
  - main.py                       # Annotations group, canvas gating, rename hooks
source-tasks:
  - "todo_open.md: Architecture Annotations group + Note"
  - "todo_open.md: Text leaders for model / Block Editor text"
  - "todo_open.md: Sheet-text leaders"
---

# Text Leaders, Annotations Group and View-Owned Notes -- Design Spec

Consolidating contract for a change spanning `text-annotation-system.md`,
`ribbon-bar.md`, `model-space-containment-contract.md`, `system-blocks.md`,
`view-relationships.md` and `paper-space.md`. Each gets a one-line pointer here at
Account; the full rewrites are follow-ups (Rule A).

## Goal

- Every Text primitive can carry one leader: a shoulder perpendicular to the box edge,
  then a leader line ending in an End type.
- The Architecture tab gains an **Annotations** group whose Note button places a text
  note that belongs to one plan or detail view.

## Motivation

Text on sheets and in blocks has no leader, and the paper panel shows a "Leader: None"
placeholder. Plans have no way to carry a note. The group gives Dimension, Note and
Keyed Notes one home, with Note built first.

## Architecture & Constraints

- **C5 stands:** one Text item, one renderer. The leader is data on
  `TextAnnotationData`, drawn by one module on every surface.
- **C1 stands:** the plan holds no free text. A Note is a placed Block instance.
- **C9 is amended:** free notes may live in the model when owned by a view instance
  (D9). Keynotes and legends stay paper-only until designed.
- **No third view pattern.** `view-relationships.md` s5 keeps the shared-scene and
  rebuilt-scene patterns. A view-owned item is a visibility rule inside the shared
  scene's existing sweep, recorded there as an update.
- **Dual serialization parity:** file and undo paths both carry the new fields.
- **Merge order:** SB4d merges first, so Notes land in its annotation band. If this
  branch finishes first, it rebases when SB4d lands.

## Design Decisions

All ratified by the user at the grill (Q1-Q11) or at design approval, 2026-11-04.

| # | Decision |
|---|---|
| D1 | **Ribbon.** Group `Annotations` in the Architecture tab, after Datums, before Underlay. Note is live; Dimension and Keyed Notes are disabled with a coming-soon tooltip. Draft > Annotate is unchanged. |
| D2 | **One leader per text.** Multi-leader is a follow-up. |
| D3 | **Geometry.** One open stroke attach -> knee -> tip. The attach-to-knee part (the shoulder) is always perpendicular to the box edge. No End on the attach; the tip takes the End type, default the shipped `Arrow`. |
| D4 | **Knee drag.** Free, like a detail bubble. The edge is the one the knee is furthest outside of (ties keep the current edge). The knee's along-edge coordinate clamps to the edge's extent, so the attach slides and stops at the edge end and the shoulder stays perpendicular. A knee inside the box lands on the nearest edge at `TEXT_LEADER_MIN_SHOULDER_MM`. |
| D5 | **Independent grips.** Knee and tip each have a grip; dragging the tip leaves the shoulder alone. Grips exist only while Leader is on and follow the existing grips, so `MOVE_GRIP_INDEX` keeps its value. |
| D6 | **Style.** Named weight (`leader_weight`, same picker as the frame) and the text colour (Decision 4 of the text spec). Solid line. |
| D7 | **Pinned tip.** Moving the text keeps the tip on its target and stretches the leader, on every surface. Copy, rotate, mirror and paper scale move the leader with the box. |
| D8 | **Note model.** One shipped System block, `Note.fpdb` (Annotative, one `@[Text]` primitive). Text is the `Text` attribute. Box size, leader and owning view are per placement. Font, height and frame come from the definition, so editing the block restyles every note. Per-note formatting is out of scope. |
| D9 | **View ownership.** A Note belongs to exactly one plan or detail view, keyed in the `scene.active_view_key` format (`plan:Plan: Level 1`, `detail:D1`). It shows only in that view and in that view's sheet viewports. A detail cropping the same spot does not show it. |
| D10 | **Lifecycle.** A view rename re-keys its notes. A view delete deletes its notes in the same undo step. Notes are not attached to model elements; hosting is a follow-up. |
| D11 | **Views now.** Plan and detail. Section / elevation is a follow-up; the Note button is disabled there with a tooltip, and on paper, 3D, block and schematic canvases. |
| D12 | **Editors and sheets.** No new button. Build > Text with Leader on is the note in block and schematic editors, and it saves into the definition. Draft > Add Text with Leader on is the note on sheets. A leader in a definition has a default tip, the same for every placement. |
| D13 | **Editing.** Text is typed on the canvas. Double-click opens a transient `TextItem` over the note, so `TextEditController` runs unchanged; commit writes the `Text` attribute. New notes open the editor at once. Committing empty text deletes the note, as Text does. |
| D14 | **Annotative leader.** The note box and shoulder scale with annotative sizing. The tip is stored in scene mm, so it stays on target when the drawing scale changes. |

## Data model

**`TextAnnotationData`** gains one sparse field, `leader: dict | None`, written only when
set (the `keep_upright` convention):

| Key | Type | Meaning |
|---|---|---|
| `edge` | `"L" \| "R" \| "T" \| "B"` | Box edge the shoulder leaves |
| `t` | `float` 0-1 | Attach position along that edge |
| `shoulder_mm` | `float` | Shoulder length |
| `tip_dx`, `tip_dy` | `float` | Tip, relative to the knee, in the text's unrotated frame |
| `end` | end ref | End type; default `Arrow` |
| `weight` | `str` | Named weight, canonicalised like `border_weight` |

`_TEMPLATE_FIELDS` does not include `leader`, so a new text never inherits one.

**`BlockInstance`** gains one sparse field, `note: dict | None`:

| Key | Type | Meaning |
|---|---|---|
| `view` | `str` | Owning view key (D9) |
| `wrap_width_mm`, `box_height_mm` | `float` | Box, in printed mm |
| `leader` | dict or absent | As above, with `tip_x`, `tip_y` in scene mm relative to the instance origin (D14) |

An instance with `note` set is a Note. `BlockInstance.to_dict` / `from_dict` and
`place_kwargs` carry it, so save, undo and every rebuild site agree.

## Rendering

- `text_leader.py` is pure geometry plus op building: `leader_points(box_rect, leader)`,
  `solve_knee(box_rect, drag_point, leader)` (D4), `leader_ops(...)`.
- `text_box_ops` appends a STROKE `RenderOp` with `pieces` and an `ends` record to its
  `over` list, so blocks and placements draw the leader through the existing op path,
  placement overrides included.
- `TextItem.paint` draws the same stroke on paper and in editors, through the same
  `end_render` route as open primitives.
- `boundingRect` and `shape` grow to the leader and its end. `manip_bounds` stays the
  box, so box handles do not jump.
- `bound_text_ops` gains an optional per-placement patch merged into the text record.
  With a patch, hugging is skipped because the box is authored per placement. The patch
  joins the memo key.

## View visibility

- `LevelManager.apply_to_scene` gains `view_key`; `_set_level_vis` hides any instance
  whose `note["view"]` differs. Callers: `main.py` plan and detail apply paths and
  `SheetViewport._begin_isolation`, which sets it before the sweep.
- The viewport no-op skip compares `(level, height, depth)` only, so a detail sharing
  its plan's context would skip isolation and show the plan's notes. The comparison
  gains the view key.
- `section_scene` skips instances with `note` set when it copies block instances.

## Lifecycle

- **Rename:** plan renames (`main.py`, `PlanViewManager.rename_level`) and detail renames
  re-key owned notes.
- **Delete:** `delete_detail` and plan-view removal delete owned notes in one undo step.
  Whether level delete, which re-points refs, removes a plan view is probed in plan step
  1; the rule stands either way: if the view goes, its notes go.

## Acceptance Criteria

- [ ] Leader toggle on sheet text and Block Editor text draws shoulder, leader and End.
- [ ] The shoulder stays perpendicular across all four edges, past corners, and with
      the knee inside the box.
- [ ] Knee and tip grips move independently and undo in one step on each surface.
- [ ] Moving text keeps the tip pinned; rotate and copy carry the whole leader.
- [ ] A leader saved in a block definition draws on placements of it.
- [ ] Save/load and undo round-trip the leader and the note record.
- [ ] Architecture shows the Annotations group; Dimension and Keyed Notes are disabled.
- [ ] Note places by two corners on plan and detail and opens the editor.
- [ ] Note is disabled with a tooltip on section, paper, 3D, block and schematic canvases.
- [ ] A note on Plan L1 shows on Plan L1 and its viewport, not in an overlapping detail
      or its viewport, and the reverse.
- [ ] Renaming a view keeps its notes; deleting one removes them, and undo restores them.
- [ ] Notes never appear in sections or 3D.
- [ ] The tip stays on target when the drawing scale changes.
- [ ] Editing the Note block restyles existing notes without moving their boxes or tips.

## Verification Checklist

- [ ] Guards drive the real path: placement mode, grip drag, `SheetViewport` paint,
      save/load. Each shown RED with the change reverted (VC3).
- [ ] Keep-green covers tests coupled to `text_box_ops`, `bound_text_ops`,
      `apply_to_scene`, `_begin_isolation` and the ribbon roster (VC5).
- [ ] Smoke on plan, detail, sheet, Block Editor and schematic.
- [ ] Exported PDF shows the leader at true weight (print is the acceptance gate).
- [ ] Perf: `apply_to_scene` adds one key check per instance; no new per-paint work on
      instances without a `note`.

## Edge Cases & Error Handling

- **Missing Note definition:** the existing unresolved-block path applies.
- **Dangling view key** (a corrupt file): the note stays hidden and stays in the file; no
  repair on load.
- **Copy / paste:** the copy joins the active view. Pasting on a canvas that cannot hold
  notes refuses with a status message.
- **Leader off:** the record is dropped, so toggling on again starts from the default
  placement (right edge, mid-height).
- **Block Editor constraints:** the solver keeps driving the box; the leader follows and
  adds no constraint refs.

## Follow-ups to file

Multi-leader; tips hosted on elements; Notes in section / elevation; Dimension in the
Annotations group; Keyed Notes; per-note formatting; Note types (more than one Note block).
