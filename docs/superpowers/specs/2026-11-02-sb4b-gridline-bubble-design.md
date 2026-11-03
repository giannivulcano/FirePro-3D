---
status: proposal         # designed 2026-11-02 (SB4b Phase 3), unbuilt; the built contract will land in docs/specs/system-blocks.md + grid-system.md
last-verified: 2026-11-02  # Phase 1b/3 probes against main c20d2ec3
verified-commit: c20d2ec3
applies-to:
  - firepro3d/gridline.py               # GridBubble -> GridlineBubble(BoundLabelItem); trim / shape / HALO / overlays; TagBlockHost; tag_block
  - firepro3d/bound_label.py            # PAINT_WHEN_BLANK honoured in _ops
  - firepro3d/system_blocks.py          # Gridline registered (ANNOTATION_CATEGORIES, SYSTEM_DEFAULTS, LABEL_FIELD, PAINT_WHEN_BLANK)
  - firepro3d/system_blocks/Tags/       # GridlineBubble.fpdb seed
  - firepro3d/model_space.py            # refresh_annotation_tags walks gridline bubbles; template bubble copy
  - firepro3d/paper_display.py          # plan bubbles through _apply_block; bubble save/restore retired
  - firepro3d/display_manager.py        # Grid Line row: Fill / Scale retired; _apply_gridline tints the line only
  - firepro3d/section_scene.py          # comments only (GridBubble references); elevation bubbles unchanged (SB4c)
source-tasks:
  - "SB4b -- Convert the plan gridline bubble to a System block via BoundLabelItem (todo_open.md; refined AC1-AC9 on the task line)"
---

# SB4b -- Plan gridline bubble as a System block -- Design Spec

> **Status: proposal.** Ratified: Phase 2 grill AC1-AC9 (recorded on the SB4b line in
> `todo_open.md`, 2026-11-02), the blank-label ruling and the Phase 3 approvals (approach A,
> sections 1-3, 2026-11-02). Subsystem contracts: [`system-blocks.md`](../../specs/system-blocks.md)
> (label seam, resolver, Tag row) and [`grid-system.md`](../../specs/grid-system.md) (gridline);
> this doc links to them and never restates them (Rule A). Precedent:
> [`2026-10-31-sb4a-pipe-label-design.md`](2026-10-31-sb4a-pipe-label-design.md).

## Goal

Each end of a plan gridline is drawn by a user-designable annotation block (default: a
circle with the gridline's Mark), annotative like room tags and pipe labels: it scales with
zoom and prints at its authored size. Everything a gridline does today keeps working --
per-end visibility and standoff, grips, lock, selection, HALO, the duplicate-label warning.

## Motivation

Phase 4 of the System Blocks concept (Q9 composite rule: the line stays bespoke, the head
becomes a block; F6: no longer screen-fixed). Retires the screen-fixed `GridBubble`, its
paper-mode geometry swap and the screen-scale special case in `halo_trace_path`. The
bubble block is authored so it can become the end block of a linear gridline block (SB8).

## Architecture & Constraints

- Label seam, resolver + fallback chain, pane, Tag row, `_apply_block`: `system-blocks.md`
  sections 2-8a, reused as is.
- Field keys: `element_params` already registers category `Gridline` with `Mark` (= Label,
  Q3), `Length`, `Angle` ([`element-parameters.md`](../../specs/element-parameters.md)). A
  blank text value reads raw `None` (`host_values`).
- Annotative sizing: SB1c design doc. Z: the level pass sets every `GridlineItem` to
  `Z_GRIDLINE_BUBBLE` (`level_manager`, `view-relationships.md` 7.3); child bubbles stack with it.
- Snaps skip child items (`snap_engine`: parent not None), so bubbles never snapped and
  still do not.
- Elevation / section bubbles (`section_scene._ElevBubble`) are SB4c: `bubble_paper_geometry`,
  `GRIDLINE_BUBBLE_PAPER_CAP_MM`, `GRIDLINE_BUBBLE_LABEL_EM_FRAC`, `BUBBLE_RADIUS_MM` and
  `Z_GRIDLINE_BUBBLE` stay.

## Design Decisions

| # | Decision | Rationale / alternatives |
|---|---|---|
| D1 | **Child label per end.** `GridlineBubble(BoundLabelItem)` in `gridline.py`; `bubble1` / `bubble2` keep their names and are children of the gridline (`child=True`). Visibility, opacity and z cascade from the gridline. | Approach A (approved). B (top-level, as Pipe) only adds lifecycle code -- gridlines are already overlay z. C (gridline paints ops itself) loses `_apply_block` / refresh reuse. |
| D2 | **Registration.** `ANNOTATION_CATEGORIES += ("Gridline",)` (pane row), `SYSTEM_DEFAULTS["Gridline"] = "system-tags-gridlinebubble"`, `LABEL_FIELD["Gridline"] = "Mark"`. | Reuse. The id avoids the retired `GridBubble` string. |
| D3 | **Blank label keeps the circle.** `system_blocks.PAINT_WHEN_BLANK = frozenset({"Gridline"})`; `BoundLabelItem._ops` skips the "every host field blank -> paints nothing" rule for those categories (static geometry draws, the bound text is empty). Orphan placeholder rule unchanged. | User ruling 2026-11-02 (today's empty-circle result). |
| D4 | **Pose.** `_rebuild_geometry` calls `bubbleN.set_anchor(axis point at the standoff)`; no rotation, ever (AC4). Per-end visibility stays `bubbleN.isVisible()`. | AC4 / AC8. |
| D5 | **Outline + trim.** `GridlineBubble.outline_path()` = union of the closed subpaths of the block's static ops at the current k (local coords), else the bounds rect. `trim_distance(ux, uy)` = distance from the block origin, along the unit direction toward the span, to where that ray leaves the outline. `GridlineItem.paint` trims each visible end by it (screen and paper -- k already differs on paper); cached on (definition, k, direction). | AC5. Ignoring text ops keeps a label sticking out of the shape from moving the trim. |
| D6 | **HALO + hit.** `halo_trace_path` = trimmed line + both visible outlines (scene units, no `scene_scale` dependency). `shape()` = the stroked line + both visible outlines, so a bubble press hits the gridline (the label accepts no buttons) -- click selects, Ctrl+click toggles via the existing scene path. **Unverified (P4): plan step 1 probes bubble click / Ctrl+click through a shown view;** `GridBubble.mousePressEvent` is the fallback to port if it fails. | AC7. |
| D7 | **Overlays (screen only, never paper).** `GridlineBubble.paint` after the ops: selected gridline -> outline stroked `_grid_color.lighter(150)`, cosmetic 2 px; duplicate label -> outline stroked `#ff8800`, cosmetic, drawn last. `update_duplicate_warning` sets a flag + `update()`. Skipped while `_paper_render`. | AC2 / AC7. |
| D8 | **Lock padlock** positioned beside bubble 1: its position = bubble 1 centre + perpendicular x (outline extent along that perpendicular); path offset 6 px (screen-fixed). | A scaling bubble would cover a fixed-px offset. |
| D9 | **Tag row.** `GridlineItem` mixes in `TagBlockHost`, `_TAG_CATEGORY = "Gridline"`; "Tag" row under Bubble 2 Offset (not on the placement template: off-scene it shows only the default); `_tag_changed` refreshes both bubbles + `prepareGeometryChange`. Both ends share it. | AC6. |
| D10 | **Persistence.** Sparse `tag_block` in `to_dict` / `from_dict` (the one serializer for `.fpd`, undo and paste); `_clone_parallel` (offset / array) copies it. No `SAVE_VERSION` bump. | AC6. |
| D11 | **Display Manager.** Grid Line row `fill: None`, Scale column retired (as Pipe's font); `_apply_gridline` sets `_grid_color` (line) + opacity + visibility only; its snapshot/restore drops the bubble pen / brush / label / font / scale keys; `_display_scale` gone from gridlines. Saved Fill / Scale values are ignored. | AC3 (pipe precedent). |
| D12 | **Paper.** `paper_display._apply_gridline` keeps the line weight + paper-mm dash; each visible bubble goes through `_apply_block(bubble, ...)` with opacity 1; `restore_model_display` restores the block hooks (Pipe `tag_paper` precedent). `_paper_bubble_r`, `enter_paper_mode` / `exit_paper_mode` and the bubble pen / brush / label-colour save are retired. | AC1 / AC2 (warning never plots). |
| D13 | **Refresh.** `refresh_annotation_tags` also walks gridline bubbles and calls the gridline's `prepareGeometryChange`; a Label change refreshes both bubbles. | Mapping / units / drawing-scale changes re-shape the trim. |
| D14 | **Seed** `firepro3d/system_blocks/Tags/GridlineBubble.fpdb` (id `system-tags-gridlinebubble`, Annotative, Scale with zoom, host Gridline, host attribute Mark): a circle about 9.5 mm across centred on the origin, `@[Mark]` centred, Consolas bold 3 mm cap, Automatic colours. User may redesign + Promote at smoke. | AC9 (visual gate). |
| D15 | **Retired** (guard): `GridBubble`, `RADIUS_PX`, `enter_paper_mode` / `exit_paper_mode`, plan use of `bubble_paper_geometry` and `_paper_bubble_r`, the `scene_scale` bubble radius in `halo_trace_path`, gridline `_display_scale`, DM Grid Line Fill / Scale. Comments in `section_scene.py` naming `GridBubble` are re-worded. | G10. |

## Acceptance Criteria

- [ ] AC1 bubble paints the mapped block's `@[Mark]`, annotative (screen = printed mm x drawing scale at two scales); paper mm at two viewport scales (G1, G2)
- [ ] AC2 duplicate label -> orange outline ring on screen, absent on paper (G3)
- [ ] AC3 DM Grid Line colour tints the line, not the bubble; Fill / Scale gone from the row (G4)
- [ ] AC4 bubble upright on a 30 deg gridline (G5)
- [ ] AC5 line meets the outline for the circle seed and a non-circular block; HALO trace matches (G6)
- [ ] AC6 Tag row: one undo step, `< mixed >` no-op; `tag_block` round-trips `.fpd` / undo / paste / offset copy; a missing id falls back with one notice (G7)
- [ ] AC7 bubble click / Ctrl+click select / toggle through a shown view; selection ring screen only (G8)
- [ ] AC8 per-end visibility / standoff / grips / lock carry over; a legacy file loads (G9)
- [ ] AC9 seed shipped; user redesign + approval at smoke
- [ ] D3 a blank label keeps the circle and the line still stops at it (G11)
- [ ] D15 retired strings (G10); pinned category tests updated (`test_sb3_annotation_defaults`, `test_sb3_system_default`)

## Verification Checklist

- [ ] Every guard shown RED with its change reverted (VC3)
- [ ] Keep-green: SB3 / SB3b / SB4a suites (`system-blocks.md` section 10) and every gridline / HALO / paper test that names the bubbles (grep: `bubble1`, `bubble2`, `GridBubble`, `halo_trace_path`, `_apply_gridline`)
- [ ] Live smoke via `python main.py`: zoom, angled gridline, duplicate label, Tag row, hide a bubble, lock, paper export, Block Editor redesign
- [ ] Account: `system-blocks.md` (Gridline section, s1 categories, s10), `grid-system.md` (s4.1 / s4.2 / s6.4 / s10), `paper-space.md` s9.9 / s9.9.1, display-manager Grid Line row

## Edge Cases & Error Handling

- Block resolves nowhere: Mark present -> red placeholder at the bubble position (system-blocks s2); the line trims at the placeholder box (bbox fallback).
- Hidden bubble: no trim at that end, no grip, not in shape / HALO (as today).
- Zero standoff: bubble centred on the endpoint; trim still applies.
- Very long label in the circle seed: the text may overflow the circle; the trim follows the circle (D5).

## Follow-ups

- SB4c (elevation bubbles + datum heads) retires the remaining bubble constants.
- SB8 (linear System blocks) may absorb the line + this bubble block as its end block.
