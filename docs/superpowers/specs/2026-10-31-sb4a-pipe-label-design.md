---
status: proposal         # designed 2026-10-31 (SB4a Phase 3), unbuilt; the built contract will land in docs/specs/system-blocks.md
last-verified: 2026-10-31  # Phase 1b/3 probes against main 4fd97ed3
verified-commit: 4fd97ed3
applies-to:
  - firepro3d/pipe.py                   # label -> top-level BoundLabelItem; Label Size retired; tag_block
  - firepro3d/bound_label.py            # explicit host (child=False); TagBlockHost mixin
  - firepro3d/room.py                   # Tag row moves to the TagBlockHost mixin (no behaviour change)
  - firepro3d/system_blocks.py          # Pipe registered (ANNOTATION_CATEGORIES, SYSTEM_DEFAULTS, LABEL_FIELD)
  - firepro3d/system_blocks/Tags/       # PipeLabel.fpdb seed
  - firepro3d/block_attributes.py       # hide_empty drop + slot close in bound_text_ops
  - firepro3d/block_explode.py          # explode honours hide_empty
  - firepro3d/text_item.py              # TextData.hide_empty + Block Editor checkbox
  - firepro3d/element_params.py         # zero flow -> None for Pipe Flow / Velocity / FrictionLoss
  - firepro3d/network_codec.py          # sparse tag_block on serialize_pipe / deserialize_pipe
  - firepro3d/model_space.py            # refresh_room_tags -> refresh_annotation_tags
  - firepro3d/paper_display.py          # pipe label through _apply_block
  - firepro3d/display_manager.py        # Pipe row font None; _apply_pipe font path retired
  - firepro3d/pipe_network_controller.py  # placement preview label size constant
  - firepro3d/constants.py              # PIPE_PREVIEW_LABEL_IN
source-tasks:
  - "SB4a — Convert the pipe label to a System block (user-designed, visual gate) (todo_open.md; grill record on the task line)"
---

# SB4a — Pipe label as a System block — Design Spec

> **Status: proposal.** Ratified decisions: Phase 2 grill AC1–AC10 + G1–G8 (recorded on the
> SB4a line in `todo_open.md`, 2026-10-31) and the Phase 3 approvals below (sections 1–3,
> label-item approach, G5 scope). The subsystem contract is
> [`docs/specs/system-blocks.md`](../../specs/system-blocks.md); this doc links to it and
> never restates it (Rule A).

## Goal

The pipe label is drawn by a user-designable annotation block, like the Room tag (SB3). It
shows the same information as today (nominal Ø, length, and after a solve flow + friction
loss) at the block's authored printed size, always readable and always on top. Each pipe
can pick its own label block.

## Motivation

Phase 4 of the System Blocks concept: every intrinsic label is drawn by a block authored in
the one Block Editor (concept Q9/Q13). The pipe label is the first of SB4a–g and sets the
pattern the others reuse. It also fixes the known 2D-length bug
(`pipe-placement-methodology.md`, Labels) by binding the 3D `Length` parameter.

## Architecture & Constraints

- The host-bound seam, resolver, fallback chain, `annotation_defaults`, pane and shared
  picker are owned by `system-blocks.md` §2–§7 and reused as is.
- Field keys and raw units are owned by [`element-parameters.md`](../../specs/element-parameters.md).
- Annotative sizing (k, paper 1/S) is owned by the SB1c design doc; paper pass by
  `paper-space.md` §9.9. Z-order constants: `view-relationships.md` §7.3 + `constants.py`.
- **Qt stacking (P4, probed 2026-10-31):** a child item cannot draw above an item stacked
  above its parent, whatever its own z (child z=200 under a pipe at 0.4 is drawn below a
  node at 0.5). This drives D1.

## Design Decisions

| # | Decision | Rationale / alternatives |
|---|---|---|
| D1 | **Top-level label linked to its pipe.** `BoundLabelItem(host, *, child=True)`; `child=False` makes it a top-level item whose data source is `self._host` (Room passes nothing — unchanged). The pipe adds it to the scene at `Z_OVERLAY` and keeps today's lifecycle: `setVisible` cascade, hidden when vertical or Show Label off, the three `removeItem(pipe.label)` sites. | AC6 (always above nodes / sprinklers / fittings). A child at pipe z breaks AC6; raising the pipe to `Z_OVERLAY` breaks elevation z-order. Approved 2026-10-31. |
| D2 | **Pose.** `Pipe.update_label()` = show/hide, `setPos(midpoint)`, `setRotation(a)` with `a` kept in [−90°, 90°) (today's direction flip and its 90 → −90 mapping), `label._pose_rot = a`, then `label.refresh()`. The HTML label, `set_label_position`, `Label Size` and the fixed `#00aaff` / `#ffaa00` colours are deleted. Existing callers (solve, clear, Diameter, geometry, DM) keep calling `update_label()`. | AC4: the whole label turns; per-text `keep_upright` flips each box about its own centre so stacked lines would swap sides (P4, `render_op.text_path`). An authored `keep_upright` text still works via `_pose_rot`. |
| D3 | **Registration.** `ANNOTATION_CATEGORIES = ("Room", "Pipe")`, `SYSTEM_DEFAULTS["Pipe"] = "system-tags-pipelabel"`, `LABEL_FIELD["Pipe"] = "Diameter"`. The Annotation pane gains its Pipe row from the tuple. `refresh_room_tags()` → `refresh_annotation_tags()` (rooms + pipes), every caller renamed. | Reuse (1b sweep). Diameter is never `None`, so a pipe whose block resolves nowhere draws the red placeholder (system-blocks §2). |
| D4 | **`TagBlockHost` mixin** (in `bound_label.py`): `tag_block` property, `_tag_row()`, `_set_tag()` lifted from Room; a `_tag_changed()` hook (Room: `self._tag.refresh()`; Pipe: `update_label()`). Pipe gets a "Tag" enum row under Show Label. One undo step, "(Library)" embed first, `< mixed >` no-op — as Room (system-blocks §8). | AC5; one implementation, two callers (GENERALIZE). |
| D5 | **Persistence.** Sparse `tag_block` key in `serialize_pipe` / `deserialize_pipe` (`network_codec`), the one codec for `.fpd` and the undo snapshot. No `SAVE_VERSION` bump. | AC5 / G5. Copy/paste does **not** carry it: pipe clipboard records carry no pipe properties at all today (pre-existing; filed as a bug). G5 = file + undo. Approved 2026-10-31. |
| D6 | **"Hide when empty".** `TextData.hide_empty: bool = False` (sparse, the `keep_upright` convention); a Block-Editor-only "Hide when empty" checkbox beside *Keep upright* in `TextItem.get_properties`. A plan-view text ignores it. | AC2, generic for every host-bound block. |
| D7 | **Drop + slot close** in `block_attributes.bound_text_ops`: a bound text with `hide_empty` whose every host field resolves to raw `None` is dropped (glyphs, border, fill). Each remaining **bound** text on the same side of the block origin (block y axis) lying beyond a dropped box moves toward the origin by the dropped box's slot (its near edge to the near edge of the next box beyond it). A box's side is that of its centre; a dropped box whose centre is on the origin closes nothing. Static primitives (cached static list) never move. `block_explode` applies the same rule. Bounds shrink through `_compute_rect`. | AC2 / G2. Keeps the authored spacing pattern; static geometry stays cached (system-blocks §9 F1). |
| D8 | **Zero flow = blank.** The `element_params` Pipe getters Flow, Velocity and FrictionLoss return `None` when the solve's flow for the pipe is 0 — E7's "the solve did not reach it" widened to "reached it with no flow". No other consumer reads these keys (probed: the hydraulic report reads `hydraulic_result` directly). | AC3; one rule in the registry, not in the label. |
| D9 | **Retirements.** `Label Size` property; DM Pipe row `"font": None` (the column hides, `_apply_pipe`'s `font_size` path goes); old files' `Label Size` is dropped by `Pipe.set_property`'s existing unknown-key skip (probed). The placement preview label (`pipe_network_controller`) uses `PIPE_PREVIEW_LABEL_IN = 12` in `constants.py` — preview unchanged. | AC8 / G6. |
| D10 | **Paper.** The paper walk's Pipe branch routes a visible label through `paper_display._apply_block(pipe.label, …)` (opacity 1), as Room; the saved state swaps `pipe_label_color` for the block hooks' state. | AC7 (authored colours; the DM Pipe colour tints the pipe only) / G7. |
| D11 | **Seed block** `firepro3d/system_blocks/Tags/PipeLabel.fpdb` (id `system-tags-pipelabel`, Annotative, Scale with zoom, host Pipe), 3 mm Arial, Automatic colour: `@[Diameter]` above the origin, `@[Length]` below, then `@[Flow]` (blue) and `@[FrictionLoss]` (orange), both *Hide when empty*. Host attributes Diameter / Length / Flow / FrictionLoss. The user redesigns it at smoke and dev-Promotes (AC10, visual gate). | Ships the code path with today's content. |

## Acceptance Criteria

- [ ] AC1 shipped PipeLabel: Ø, 3D Length, and after a solve Flow + FrictionLoss (G1)
- [ ] AC2 "Hide when empty" drops a blank bound text and closes its slot (G2, D7 guard incl. explode parity)
- [ ] AC3 Flow 0 counts as blank (G2)
- [ ] AC4 left- and right-pointing pipes get the same label angle (G3)
- [ ] AC5 per-pipe Tag row; `tag_block` round-trips `.fpd` + undo (G5)
- [ ] AC6 the label paints above a node / sprinkler at the midpoint (G4)
- [ ] AC7 authored colours; the DM Pipe colour does not tint the label
- [ ] AC8 Label Size + DM Pipe font retired; a legacy file with Label Size loads clean (G6)
- [ ] AC9 short pipes still labelled; vertical pipes unlabelled
- [ ] AC10 seed block shipped; user redesign + side-by-side approval at smoke
- [ ] G7 paper mm at two scales
- [ ] G8 perf bar (metric + ≥ 2 bench shapes confirmed with the user against a measured base first)

## Verification Checklist

- [ ] Every guard shown RED with its change reverted (VC3)
- [ ] Keep-green: the SB3 / SB3b suites (`system-blocks.md` §10) — `BoundLabelItem` and the Tag row are shared
- [ ] Retired-strings guard for the pipe (HTML label, `Label Size`, `set_label_position`)
- [ ] Live smoke via `python main.py`: solve / clear, left/right pipes, vertical pipe, Tag row, paper export, Block Editor checkbox
- [ ] Account: `system-blocks.md` (Pipe section, §1 categories, §10 guards), `element-parameters.md` E7, `pipe-placement-methodology.md` Labels, `paper-space.md` §9.9, display-manager Pipe row

## Edge Cases & Error Handling

- Missing / ineligible per-pipe or default block → fallback with one notice; nothing resolves → red placeholder at the midpoint (system-blocks §3, §2).
- Pipe without nodes or scene → no label (as today).
- Hidden pipe (level filter, DM visibility) → label hidden by the cascade.
- Solve then edit → stale values until re-solve or clear (E7, unchanged).

## Follow-ups (filed)

- [bug] Pasted pipes lose all their properties (Diameter, Tag, …).
- [bug] Room tag may draw under walls (child stacking; probe first).
- [feature] Pipe label move grip; [feature] hide the label when it does not fit (grill, already filed).
