---
status: built            # BUILT 2026-11-04 (v0.87.0, merged to main dab5a2f2); the contract now lives in docs/specs/system-blocks.md (s8e, s8d reversal) + paper-space.md (s5.2, s9.9). Build deltas: the grip registers on both manipulator hooks (manip_box_extra_handles and manip_extra_handles); the auto number is assigned in PaperScene.add_viewport, not _do_add_viewport; the view title plots as paths, not a PDF text layer
last-verified: 2026-11-04
verified-commit: dab5a2f2
applies-to:
  - firepro3d/paper_space.py
  - firepro3d/paper_commands.py
  - firepro3d/bound_label.py
  - firepro3d/view_title_label.py
  - firepro3d/element_params.py
  - firepro3d/system_blocks.py
  - firepro3d/model_space.py
  - firepro3d/scene_io.py
  - firepro3d/system_blocks/Tags/ViewTitle.fpdb
  - firepro3d/system_blocks/Tags/SectionHead.fpdb
  - firepro3d/system_blocks/Tags/DetailCallout.fpdb
source-tasks: ["SB4f -- Convert the sheet viewport view title to a System block, with a per-viewport show/hide toggle for the title"]
---

# SB4f -- Sheet viewport view title as a System block -- Design Spec

Forward-looking until built. The contract moves to the governing specs at Account
(Rule A): `system-blocks.md` (new section 8e, section 8d reversal), `paper-space.md`
(section 5.2 data, section 9.9), `element-parameters.md` (category + key table),
`schematics.md` (D-S2, D-S10), `model-space-containment-contract.md` (C9 pointer).

## Goal

The view title under a sheet viewport is drawn by a block authored once in the Block
Editor. It reads its number, title and scale from the viewport, can be hidden per
viewport, and can be moved off its default spot. Its number is the one section and
detail heads cite.

## Motivation

Revit-style sheet documentation (G1): the title is the drawing's identity on the sheet.
Today it is hand-painted in `SheetViewport.paint`, so its look cannot be changed, it
cannot be hidden, and the section / detail heads cite a Mark that means nothing on
the sheet.

## Ratified inputs

G1-G12 and AC1-AC8 (Phase 2, 2026-11-04) and D1-D5 below. G5's wording is amended by D4;
G7's reset gesture is replaced by D1 + D5.

| Id | Ruling |
|----|--------|
| D1 | Move the title with a **grip when the viewport is selected** (round grip, Room tag pattern). Clicking the title selects the viewport. |
| D2 | Old heads on load: **auto-update untouched project copies** from the new seed. An edited copy keeps Mark in the top slot and gets one notice. |
| D3 | The drop dialog's dead Show Border checkbox is **fixed here** (absorbed, logged as phase-drift). |
| D4 | The **title item paints the line**, not `SheetViewport`. Same geometry as G5 / G7; only the owner changes. Otherwise the viewport's hit area would stretch to reach a dragged title. |
| D5 | Reset lives in **both** the viewport property panel (button) and the viewport right-click menu, running the same edit. |
| D6 | A long title **runs past the box edge** rather than being clipped (accepted breaking change). |

Esc keeps its existing meaning: it cancels a grip drag in progress (`GripHandle.on_cancel`).

## Architecture & Constraints

- `BoundLabelItem` contract: `system-blocks.md` section 2. Not a `BlockInstance`, never
  under `PaperScene` as a block (containment C9, `schematics.md` D-S2).
- The title is a **sheet-native** label: `PaperScene` has no `scene_role`, so
  `annotative_factor` gives k = 1 with no `_paper_scale` and `_apply_block` is not
  involved. Blocks print at their authored paper mm.
- Paper has no Y-flip (P4 probe, 2026-11-04: an `OutlinedLabel` rendered under a
  scale-only transform has k = 1, 12 x 12 mm bounds and its head slots in the right
  order). Glyph shapes need the smoke: the offscreen font drew boxes.
- PDF export renders a transient `PaperScene`, so a child item plots with no export
  code. That scene is built fresh per export and needs no refresh wiring.
- All viewport edits go through `commit_viewport_edit` ->
  `ChangeViewportPropertiesCommand` -> `_resync_viewport`.

## Design

### 1. Title item

New `ViewTitleLabel(OutlinedLabel)` in `view_title_label.py`: `child=True`, host =
the `SheetViewport`.

- **Category** `View Title`: added to `element_params.CATEGORIES`,
  `system_blocks.ANNOTATION_CATEGORIES`, `SYSTEM_DEFAULTS`
  (`system-tags-viewtitle`), `LABEL_FIELD` (`Scale`, the one field that is never
  blank, so a missing block always shows the orphan box). One Settings > Annotation row
  through the existing loops; project default only, no per-viewport Tag row (G8).
- **`category_of`** gains a `SheetViewport` branch.
- **Keys** on the host: `Number` (`view_number`), `Title` (`display_title()`, as typed),
  `Scale` (`float_to_scale_str`, `NTS` at 0).
- **Seed** `firepro3d/system_blocks/Tags/ViewTitle.fpdb`, annotative, origin at the
  bubble centre: 3 mm radius bubble with `@[Number]` 2.0 bold, `@[Title]` 2.2 bold above
  the line, `@[Scale]` 1.6 grey below it (G11). Sample text upper-case by convention only.
- **Forwarder** `PaperScene.annotation_block(category, mapped=None)`, the
  `section_scene.py` pattern, guarded against a deleted model scene.
- **Refresh**: new `Model_Space.annotationLabelsChanged` signal emitted at the end of
  `refresh_annotation_tags`; `PaperSpaceWidget` connects it to
  `PaperScene.refresh_annotation_tags` (one live widget, `main.py`). That covers registry,
  mapping, units and scale changes in one place.
- **Orphan box size**: `bound_label.PLACEHOLDER_MM` becomes the class attribute
  `placeholder_mm` read at its three sites; `ViewTitleLabel` sets 8 mm.
- **Colour**: paints as authored, independent of the viewport B&W override (G9).

### 2. Geometry and hit

- `SheetViewport.boundingRect` = the box (plus the selection margin). `_VIEW_TITLE_H` and
  the hand-painted bubble, title and scale in `paint` are removed.
- Default spot (local): `(4.0, h + 4.5)`, which is today's bubble centre. Position =
  default + `title_offset`, so the title stays with the box's lower-left on resize.
- A new `_sync_title()` re-applies position and visibility; it runs wherever `h` or the
  placeholder state changes (`_recompute_size_from_scale`, `refresh_source`,
  `_resync_viewport`, `manip_scale`, `manip_live_restore`).
- **Visible** only when `show_title` and not a placeholder (placeholders hide it today).
- **Hit**: `ViewTitleLabel` accepts the left and right buttons and forwards press, move,
  release, double-click and context-menu events to its viewport, so the title acts as the
  viewport body did (select, native drag, navigate, menu). This forwarding is an
  unverified framework shape: **first plan step probes it** (P4).

### 3. Line (D4, G5, G7)

Painted by `ViewTitleLabel`; its `_compute_rect` unions the line's extent. The line sits at
the block origin's y and starts at the outline's right edge
(`origin + trim_distance(1, 0)`).

- **Below the box**: outline top >= box bottom and outline right < box right: the line ends
  at the box's right edge.
- **Elsewhere**: fixed length = box width.

Pen as today (black, 0.3 mm). Text ops do not count toward the outline, so on the seed the
line leaves the bubble's edge, as it does now.

### 4. Grip, undo, reset

- `SheetViewport.manip_extra_handles` (**not** `manip_handles`, which is authoritative
  and would remove the resize set): one round `GripHandle`; empty when the title is
  hidden or the view is a placeholder.
- `grip_points()` returns `[title origin in scene coords]`; `apply_grip(0, pt)` sets
  `title_offset` live and calls `_sync_title()`.
- `PaperScene._viewport_geom` gains `title_offset`; `ViewportGeometryCommand` restores it
  (the native-move 5-tuple keeps working). One undo step per drag.
- Toggling `show_title` rebakes the manipulator so the grip appears or goes at once.
- **Reset** (D5): a `Reset Title Position` button row in `ViewportProperties` and a
  `Reset Title Position` entry in `contextMenuEvent`; both call
  `commit_viewport_edit(vp, title_offset=(0.0, 0.0))`.

### 5. Data, numbers, dialog

- `SheetViewData`: `show_title: bool = True`, `title_offset: tuple[float, float] = (0.0, 0.0)`;
  sparse-safe `to_dict` / `from_dict` defaults (a legacy record reads as shown, undragged).
- `commit_viewport_edit` gains `show_title`, `title_offset`, `view_number`; old / new
  dicts carry them.
- **Panel**: `Number` (string) and `Show Title` (bool) rows beside `Show Border`.
- **Number rules** (G3): strip, refuse blank or a duplicate on this sheet with a
  `_show_status` notice (the `Sheet.validate_number` pattern), and the row re-shows the old
  value. Any text is allowed. The panel only shows a single selected viewport
  (`main.py`), so there is no multi-target commit.
- **Auto number**: `Sheet.next_view_number()` = lowest unused positive integer, used by
  `_do_add_viewport` (blank only) and to pre-fill the dialog. Deleting never renumbers.
- **Legacy**: numbers kept, duplicates tolerated at load and validated on edit or drop; a
  blank number stays blank (the `or "1"` fallback goes).
- **Drop dialog** gains Number and Show Title. Show Border is now passed through (D3). A
  duplicate number at OK shows the notice and keeps the dialog open.
- **Drop clamp**: when `show_title`, the available height and the lower y limit subtract
  the resolved block's extent below the box instead of `_VIEW_TITLE_H`.
- Stale "double-click dialog" docstrings on `ViewportProperties` and
  `commit_viewport_edit` are corrected (`mouseDoubleClickEvent` navigates; the dialog is
  drop-time only).

### 6. Section and Detail heads (AC5)

- **`Number`** param on Section and Detail: new `_view_number(marker, view_type)` beside
  `_view_sheet`, the same first-sheet-in-order rule, reading that sheet's matching
  `SheetViewData.view_number`; `None` when unplaced or blank.
- **Seeds**: `SectionHead.fpdb` and `DetailCallout.fpdb` top slot binds `@[Number]`; their
  `version` and `base_version` go up. Mark stays the browser identity and a panel row.
- **`PAINT_WHEN_BLANK`** adds Section and Detail: an unplaced head has every bound field
  blank and must still draw. This reverses the section 8d wording and
  `tests/test_sb4d_categories.py`, `tests/test_sb4b_gridline_bubble.py` pins.
- **Refresh**: `_resync_viewport` also calls `_refresh_source_heads`, so a Number edit (and
  its undo) updates the heads. Placement, removal and sheet renumber already reach them.
- **Load (D2)**, in `scene_io` once `block_definitions` are read, before items build, for
  those two ids only: a copy is **untouched** when `base_version is None or version ==
  base_version`. Untouched and older than the library file -> replaced by the library copy,
  outside undo. Edited and still bound to `Mark` -> kept, one notice for the load.
  `source_status` is not used: it reads an edited copy as `library` when the version
  numbers happen to match. A `None` base_version means pre-SB1b, already ruled untouched.

## Acceptance Criteria

- [ ] AC1 Block title: View Title category, Settings row, `ViewTitle.fpdb`; `@[Number]`,
      `@[Title]` as typed (schematic live name kept), `@[Scale]` (`NTS` at 0); k = 1; plots
      as authored.
- [ ] AC2 Line: outline right edge to box right edge while below the box; fixed box width
      elsewhere.
- [ ] AC3 Toggle: `show_title` default on, persisted, undoable, in panel and drop dialog;
      hidden paints nothing on screen or PDF and the footprint is the box.
- [ ] AC4 Number: editable in panel and dialog; unique per sheet with a notice; auto =
      lowest unused; deleting never renumbers; legacy kept, blank stays blank.
- [ ] AC5 Heads: top slot = number of the viewport showing the view (first sheet in order),
      blank while unplaced with the head still drawn; Mark stays the browser identity; heads
      refresh on number edit, undo, placement, removal, sheet renumber.
- [ ] AC6 Position: round grip moves only the title; persisted `title_offset`; one undo step;
      Esc cancels a drag; reset from panel and context menu.
- [ ] AC7 Retired: hand-painted bubble / title / scale and `_VIEW_TITLE_H` gone (retired-strings
      guard); the drop clamp uses the real title footprint.
- [ ] AC8 Sheet furniture ruled, not built: follow-up filed; C9 and D-S2 pointers added.
- [ ] D2 Load: untouched copy gets the new seed; edited copy keeps Mark + one notice.
- [ ] D3 Drop dialog's Show Border is honoured.

## Verification Checklist

- [ ] Round-trip `show_title`, `title_offset`, `view_number`; legacy record defaults.
- [ ] Number rules: duplicate and blank refused with a notice; auto number fills a gap;
      deletion leaves the others alone.
- [ ] Undo of toggle, number edit, grip drag, reset, each one step.
- [ ] Headless paint: block ops present; hidden paints nothing; `boundingRect` = box; line ends
      at the box edge, and is box-width when the title is dragged away.
- [ ] Real events on a shown view: click, drag, double-click and right-click on the title reach
      the viewport; the grip shows with the resize handles still there.
- [ ] Head slot = viewport number, blank unplaced, head still paints.
- [ ] Load: seed-copy swap and edited-copy notice on real pre-SB4f project data.
- [ ] Rendered sheet and PDF export show / hide the title.
- [ ] `test_titleblock_render.py` mirror rewritten; retired strings guard added;
      `tests/test_sb4d_categories.py`, `tests/test_sb3_annotation_defaults.py`,
      `tests/test_sb3_system_default.py`, `tests/test_sb4c_level_datum.py`,
      `tests/test_sb4b_gridline_bubble.py`, `tests/test_sb2a_element_params.py`,
      `tests/test_system_blocks_conformance.py` updated for the new category.
- [ ] Smoke (G11): the seed is rendered and restyled at Phase 6; glyphs upright.

## Edge Cases

- A placeholder viewport shows no title and no grip; it returns when the source resolves.
- A title dragged off the sheet stays there; reset brings it back.
- A viewport resized smaller keeps `title_offset` from the box's lower-left.
- Legacy multi-placement heads cite the first sheet in order, as `Sheet` does.
- A cardinal elevation binds neither `Number` nor `Sheet`.
- Undoing a viewport removal restores its stored number unchanged.

## Not Built (filed)

- North arrow + scale bar as viewport-bound System blocks (G10, `todo_open.md`).
- A per-viewport title block pick (G8).
