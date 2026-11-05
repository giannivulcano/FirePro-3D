---
status: proposal
last-verified: 2026-11-04
verified-commit: 88683cdb
applies-to:
  - firepro3d/block_instance.py
  - firepro3d/block_definition.py
  - firepro3d/render_op.py
  - firepro3d/block_editor.py
  - firepro3d/schematic_scene.py
  - firepro3d/model_space.py
  - firepro3d/sketch_adapters.py
  - firepro3d/auto_constrain.py
  - firepro3d/constants.py
source-tasks:
  - "Blocks in the schematic editor are opaque, with a settable stacking height so an overlapping block hides the one below"
  - "Suppress a placed block's constraint points, per instance"
---

# Block Stacking, Opacity and Constraint Point Suppression — Design Spec

Consolidating contract for a change spanning `docs/specs/schematics.md`,
`docs/specs/block-system.md` and `docs/specs/parametric-constraint-system.md`.
Each gets a one-line pointer here at Account (Rule A). Nothing below is built yet.

## Goal

A drafter can overlap blocks in a schematic and see only the top one where they
overlap, choose which block is on top, and stop a busy placed block from offering
its child constraint points.

## Motivation

Blocks paint only their linework and fill ops, so a block below shows through the
one above it. Nothing in the app sets stacking order: there is no Bring to Front
or Send to Back, and editor stacking is whatever insertion order produces.
A dense block floods constraint pick mode, and the only way to narrow its points
today is the annotative rule.

## Architecture & Constraints

- All blocks are flyweights: compiled `RenderOp` lists are shared across placements
  and never mutated (`render_op.py`).
- A schematic is a `BlockDefinition` authored in a `block_editor` scene. Sheet
  viewports paint a scene rebuilt from the definition through
  `schematic_scene.materialize_primitives`, so record keys must survive
  `BlockInstance.place_kwargs`, the one field-carrying choke point.
- A nested block compiles into its parent's op list in `BlockDefinition._compile`.
- Lower z paints first; pick and HALO rank by z. Z constants live in
  `firepro3d/constants.py`; the Z-order contract is owned by
  `docs/specs/view-relationships.md`.
- Plan stacking stays elevation-based (`level_manager.py`); nothing here changes it.

## Design Decisions

All rows were ratified at the 2026-11-04 Phase 2 and Phase 3 gates unless marked
as-proposed.

| # | Decision |
|---|---|
| D1 | **One mechanism: clip, never paint over.** A block omits the parts covered by an opaque block above it. No background colour is involved. Rejected: a background-coloured shape, which hides plan items below a parent (against D5) and must match the canvas tone. |
| D2 | **Mask shape (amended at smoke, 2026-11-05):** the block's silhouette: its visible outline traced from its connected linework and filled. Pieces that do not touch each get their own outline; holes inside an outline stay opaque. No bounding box fallback. Replaces "closed geometry, else bounding box", which gave a full rectangle or two tiny circles on real blocks. |
| D3 | **Opaque default:** on for a block in a schematic, off for a block nested in an ordinary block. Each placement has an on/off Properties row. |
| D4 | **Band order (amended at smoke, 2026-11-05):** blocks sit in their own band below lines, text and filled regions, in editors and inside compiled parents. In a **schematic only**, an opaque block also hides the loose lines, arcs, rectangles, circles, polylines and other `Geometry2DMixin` shapes under it, dashed centerlines included, with no per-line escape. Text, dimensions and filled regions stay on top. In an ordinary block only blocks hide blocks. A click inside an opaque block never picks a loose shape it hides (D8). |
| D5 | **Plan safety:** an opaque nested block hides only lower nested blocks of the same parent. Plan items under a placed parent are never hidden, and neither are the parent's own lines or text. |
| D6 | **Layer Height:** a whole number per placement, default 0, range -1000 to 1000. Higher draws on top; equal heights keep saved order. It has no effect on model elevation. |
| D7 | **Controls:** Layer Height and Opaque Properties rows in the Block and Schematic editors only; right-click Bring to Front (one above the scene's highest) and Send to Back (one below its lowest). A multi-selection keeps its relative order. Plan-placed blocks get neither. |
| D8 | **Clicking:** an opaque block's interior counts as part of it for HALO pick, so a click there picks it rather than something hidden. |
| D9 | **Object snap unchanged:** hidden parts still snap. |
| D10 | **Constraint Points row:** on every placed block, default on, in plan and both editors. |
| D11 | **Off offers `ins` only:** no child points, edges or curves are offered for a new pick. |
| D12 | **Existing constraints keep working:** they solve and draw as before. The filter sits where pick targets are listed, not in the adapter's handle tables. `_ins_only` is not reused directly: it removes handles, which would break those constraints. |
| D13 | **Nested reach:** off on a nested block also removes its points from the parent's offered set. |
| D14 | **Format:** optional record keys `layer_height`, `opaque`, `constraint_points_off` on `to_dict` and `to_nested_dict`, written only when not the default, with no file version bump. An absent `opaque` means the D3 default for the block's context. |

## Mechanism

**Top level.** `BlockInstance.paint` clips by the union of opaque masks of blocks
above it in the same scene that overlap its bounds, found through the scene's
spatial index and cached until a block in that neighbourhood moves or changes.

**Compiled.** `_compile` emits nested records first, ordered by Layer Height (stable),
then the definition's own primitives. `RenderOp` gains an optional `clip_out` path
in definition-local coordinates; each op from a lower nested block carries the
union of masks of opaque nested blocks above it. `RenderOp.mapped` transforms it,
so nested poses and mirror/scale variants stay correct. Op-group alignment in
`_compile` must follow the new order so corner joints still pair within a container.

**Stacking.** Block z in a `block_editor` scene = a new `Z_BLOCK_STACK` constant
below `Z_FILLED_REGION`, plus Layer Height times a small step that keeps ±1000
inside the band and above `Z_ROOF`.

## Input / Output

Record keys per D14. Example nested record:

```json
{"type": "block_instance", "block_id": "abc", "pos": [0, 0], "rotation": 0,
 "uid": "...", "layer_height": 3, "opaque": false, "constraint_points_off": true}
```

## Edge Cases & Error Handling

- **Open-line block:** a silhouette has no interior to fill, so a block of one open line hides only about its own stroke.
- **Bound text in a nested block** paints after the static ops, so `clip_out` does
  not reach it. Accepted; filed as a follow-up.
- **Out-of-range or non-numeric Layer Height** in a hand-edited record: clamped, or
  read as 0.
- **Paste between contexts:** an absent `opaque` takes the new context's default.
- **Reference-mode definitions** compile through `_compile_reference`; unaffected.
- **A missing nested block** renders its placeholder and has no mask.

## Performance & Security

Worst-case probe: 2,000 strokes each individually clipped took about 199 ms against
about 90 ms unclipped. Only covered ops carry a clip. Budgets are not set: per the
Phase 5 Performance rule they need a measured base scene and the user's ratification
before any bench or fix.

## Probed (2026-11-04, `88683cdb`)

- `setClipPath` with a subtracted path hides the masked span on raster and in
  `QPdfWriter` output; the PDF keeps a vector path.
- Outline over 15 shipped `.fpdb`: 8 had closed geometry; at most 0.32 ms per block.
  These are small system blocks, not representative of user blocks.
- Nothing in `firepro3d` implements bring-forward or send-back.

## Open items (first plan steps)

- **P4:** confirm `auto_constrain`'s target generator is the only source of pick
  candidates. Its filter today covers points only, so edges and curves need adding.
- **P4:** confirm a real sheet PDF export carries the clip through `paper_export.py`.
- **As-proposed:** the exact `Z_BLOCK_STACK` value and step (D6's range is ratified).

## Acceptance Criteria

- [ ] In a schematic, where block B overlaps block A and B is higher, A's ink in the overlap is not drawn, on canvas, on a sheet and in a PDF export.
- [ ] Raising A above B reverses that, through the Properties row and through Bring to Front.
- [ ] Turning Opaque off on B shows A through it.
- [ ] A text item, dimension or filled region crossing a block stays visible in every case. A line crossing an ordinary block's nested or placed block stays visible.
- [ ] In a schematic, a loose line, arc or shape under an opaque block is not drawn inside the block's silhouette, on canvas, on a sheet and in a PDF export, and is drawn right up to the outline, including in the corners of the block's bounding box. With Opaque off it shows through.
- [ ] An opaque block's mask follows its outline when that outline is made of separate open line ops, and is not its bounding box.
- [ ] In an ordinary block placed in plan, an opaque nested block hides a lower nested block, while the parent's own lines and a pipe under the placement stay visible.
- [ ] Existing ordinary blocks render unchanged except that their own lines and text now draw above their nested blocks.
- [ ] An existing schematic renders opaque on open, with no save required.
- [ ] Layer Height, Opaque and Constraint Points survive save, reopen, copy, paste and undo; absent keys read as defaults.
- [ ] With Constraint Points off, pick mode offers only `ins`; a constraint already on a child point keeps solving and drawing; object snap still finds the child point.
- [ ] Constraint Points off on a nested block removes its points from the parent's offered set.
- [ ] Each Properties change is one undo step and applies to every selected block.

## Verification Checklist

- [ ] Every guard drives the real path and asserts rendered pixels or the real offered set (VC3), and is shown RED with the change reverted.
- [ ] Corner joints and linetypes in blocks with nested children match base.
- [ ] Mirror and scale variants clip in the right place.
- [ ] The full suite passes on the final tree (VC6).
- [ ] The user smokes a real schematic, a sheet PDF and a plan placement.
- [ ] Perf budgets ratified and met.

## Code Style & Testing

Google docstrings; z values in `constants.py`. Tests run with the real stylesheet and
settings isolation from `tests/conftest.py`, using the absolute venv python.
