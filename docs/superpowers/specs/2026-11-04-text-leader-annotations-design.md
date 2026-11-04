---
status: built            # ratified 2026-11-04 (grill Q1-Q12 + design approval); D4, D7, D8 amended at smoke
last-verified: 2026-11-04
verified-commit: a71e3443
applies-to:
  - firepro3d/text_leader.py      # new: pure leader geometry + ops
  - firepro3d/text_item.py        # leader fields, paint, bounds, grips, panel rows
  - firepro3d/block_definition.py # text_box_ops emits the leader stroke
  - firepro3d/block_attributes.py # bound_text_ops per-placement patch
  - firepro3d/block_instance.py   # note record, serialization, panel rows
  - firepro3d/note_controller.py  # note lifecycle helpers, placement, edit overlay, template
  - firepro3d/selection_manipulator.py # additive handles; pinned grips in a held preview
  - firepro3d/level_manager.py    # apply_to_scene view_key filter; rename / remove hooks; Z_NOTE
  - firepro3d/paper_space.py      # viewport isolation key; paper panel rows
  - firepro3d/section_marker.py   # plan bbox skips notes
  - firepro3d/level_widget.py     # level delete removes owned notes
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
| D4 | **Knee drag.** Free, like a detail bubble. The edge is the one the knee is furthest outside of (ties keep the current edge). The knee's along-edge coordinate clamps to the edge's extent, so the attach slides and stops at the edge end and the shoulder stays perpendicular. A knee inside the box lands on the nearest edge at `TEXT_LEADER_MIN_SHOULDER_MM`. The knee snaps to the edge midpoint within the snap aperture, capped at a quarter of the edge so a coarse zoom cannot pin it, gated by the Snap and Midpoint toggles (smoke, 2026-11-04). |
| D5 | **Independent grips.** Knee and tip each have a grip; dragging the tip leaves the shoulder alone. Grips exist only while Leader is on and follow the existing grips, so `MOVE_GRIP_INDEX` keeps its value. |
| D6 | **Style.** Named weight (`leader_weight`, same picker as the frame) and the text colour (Decision 4 of the text spec). Solid line. |
| D7 | **Pinned tip.** Moving the text keeps the tip on its target and stretches the leader, on every surface: the tip is stored absolute, so a box move never touches it. It holds during the drag too: the tip and its grip stay put while the box, knee and shoulder preview. Copy, rotate, mirror and whole-definition shifts carry it explicitly, including the Rotation and Mirrored rows. A box resize or scale never moves the tip, single item or multi-select (ruling 2026-11-04). |
| D8 | **Note model** (amended at smoke, 2026-11-04). One shipped System block, `Note.fpdb` (Annotative, one `@[Text]` primitive, border on as a new Text). Text is the `Text` attribute. Box size, leader and owning view are per placement. A Note carries the Text primitive's Format, Frame and Fill rows plus Wrap and Shrink to fit, and stores only what differs from the definition, so editing the block still restyles every field a note left alone. The same rows show while the Note tool is armed (`NoteTemplate`, Leader included) and stamp the next note. A Note is not a pickable symbol: it is placed with the Note tool only. |
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
| `tip_x`, `tip_y` | `float` | Tip, absolute in the surface frame (the same frame as `x` / `y`), which is what pins it (D7) |
| `end` | end ref | End type; default `Arrow` |
| `weight` | `str` | Named weight, canonicalised like `border_weight` |

`_TEMPLATE_FIELDS` does not include `leader`, so a new text never inherits one.

**`BlockInstance`** gains one sparse field, `note: dict | None`:

| Key | Type | Meaning |
|---|---|---|
| `view` | `str` | Owning view key (D9) |
| `wrap_width_mm`, `box_height_mm` | `float` | Box, in printed mm |
| `leader` | dict or absent | As above; `tip_x`, `tip_y` are absolute scene mm (D14) |
| `style` | dict or absent | `TextAnnotationData` fields differing from the definition's primitive, printed mm (D8) |

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

- `LevelManager.apply_to_scene` gains `view_key`; `_set_level_vis` gates a note by the
  view key alone: a match shows regardless of level and z range, a mismatch hides it, so
  a note pasted across levels stays visible in the view that owns it. Callers: `main.py`
  plan and detail apply paths and `SheetViewport._begin_isolation`, which sets it before
  the sweep.
- A Note draws at `Z_NOTE`, above every model item at any elevation (smoke, 2026-11-04),
  from `place_block_instance` and the level sweep; its edit overlay matches. It stays a
  snap target. SB4d's annotation band binds host categories and a Note has none, so the
  branch merging second folds `Z_NOTE` into `Z_ANNOT_TEXT` and keeps the note case. The
  whole box stays a hit area, so a Note wins clicks over geometry under it; filed.
- The viewport no-op skip compares `(level, height, depth)` only, so a detail sharing
  its plan's context would skip isolation and show the plan's notes. The comparison
  gains the view key.
- `section_scene` already copies hosted instances only, so a Note cannot reach it; a guard pins that. `section_marker`'s plan bbox skips notes, so a note cannot grow a crop.

## Lifecycle

- **Rename:** `_on_level_renamed` re-keys plan notes and retargets plan viewports, also
  when an undo restores a level rename. A detail's Name row today changes
  only `marker._name`, leaving the manager key, the tab and viewports on the old name,
  so a save and reload would orphan its notes. `DetailViewManager.rename_detail` re-keys
  all of them, and the Name row calls it. A detail has no undo step, so its rename
  rewrites the undo history in place and its delete drops the notes from it.
- **Delete:** level delete is the only way a plan view goes (`level_widget` ->
  `pvm.remove_level`); owned notes go before its one `_push_level_step`. `delete_detail`
  removes owned notes too. Detail delete has no undo step today, so see Divergences.

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
- [ ] Renaming a view keeps its notes through save and reload; deleting one removes them;
      undo of a level delete restores them.
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

## Divergences

- **Detail delete is not undoable** (details are saved in the file but have no undo step).
  D10's "same undo step" holds for level delete only until that follow-up lands.
- **D8 reversed after approval.** Per-note formatting was out of scope at the grill. The
  user asked for it at smoke; it was built first and this spec amended after.
- **Verification.** VC6 was waived by the user; the record is keep-green by touched
  module. "Notes never appear in 3D" is confirmed by reading, with no guard.

## Follow-ups

Filed in `todo_open.md`: multi-leader; tips hosted on elements; Notes in section /
elevation; Dimension and Keyed Notes in the group; Note types; undoable detail delete;
whether an empty Note box blocks clicks.
