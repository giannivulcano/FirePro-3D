---
status: ratified          # Phase 3 brainstorming gate 2026-11-03: D1-D8 approved by the user after the P-D1 / P-D5 probe fan-out (corrections folded in below)
task: "SB4d -- Convert the elevation-marker head and the detail-callout bubble to System blocks [P1] + Placed blocks (tags) draw under walls and openings in plan [P2] (widened: all annotations above model geometry in every view)"
base: 22bb5bdd
branch: sb4d-detail-callout (worktree .worktrees/sb4d-detail-callout)
consolidates: system-blocks.md (new s8d), view-relationships.md 7.3 (annotation band), section-view-subsystem.md s5 / s6, element-parameters.md (Elevation / Section / Detail categories + Marks), paper-space.md (one-sheet rule, 9.9), grid-system.md 10.1 (DM rows), display-manager rows
absorbs: todo_open.md "Spec session: detail view markers & crop geometry" and "Spec session: view markers & shared crop box" (Phase 2 Q18)
---

# SB4d -- View-marker heads as System blocks + the annotation band

Consolidating contract (three or more specs touched, Rule A): at Account each linked spec gets a
one-line pointer here and the contract moves into `system-blocks.md` s8d (heads) and
`view-relationships.md` 7.3 (band), the way SB4c's moved into s8c. Precedent:
[`2026-11-03-sb4c-elev-bubble-datum-design.md`](2026-11-03-sb4c-elev-bubble-datum-design.md).

## Goal

The three view-marker heads -- the cardinal elevation head (circle + direction letter), the placed
section head (bubble at each cut end) and the detail callout bubble -- are **user-designable,
annotative System blocks** (restyle in the Block Editor; print at authored mm on a sheet). Detail
and Section markers join the **Marks** system and their heads show `Mark` over the **sheet number**
of the one sheet the view is placed on. Every annotation in every view draws in one **annotation
band above all model geometry**, in a fixed sub-order.

## Motivation

Phase 2 Q1 (end goal): "restyle + sheet-ready". Today both heads are hand-painted (`section_marker.py`
`paint`, `detail_view.py` `_paint_callout`) at fixed model sizes (multiples of `BUBBLE_RADIUS_MM`)
driven by the Display Manager Font / Scale knobs SB4b/c already retired for gridlines and datums; the
detail callout shows the last name token over `L1`; the section label rotates along the cut. The
z-order bug: `BlockInstance` z = level plane + 0.6 while a wall's z = top / 100 + 0.3 (3048 mm gives
30.78), so placed tags, room tags (child at 200 inside a room at 0.2) and anything at a static z
below ~`elev/100` draw under walls; a wall top at 20 m already passes `Z_OVERLAY` 200.

## Architecture & Constraints

- Concept Q9 composite rule: **only the head and its text come from the block**; the cardinal wedge,
  the section triangle, the crop box and the detail leader stay bespoke (Q3). The bespoke arrow is
  sized from the head outline at the current k (Q4) and built tangent to the **enclosing circle** of
  the outline when it is not a circle (Q5).
- Heads are `OutlinedLabel` children of their marker (`system-blocks.md` s2): upright, never rotated
  (Q3 -- the section label is now upright; breaking), annotative (k = drawing scale on screen, 1 / S on
  paper through `paper_display._apply_block`), trimmed / hit through `outline_path()` /
  `trim_distance()`.
- Three new annotation categories **Elevation / Section / Detail** (Q9): `element_params.CATEGORIES`
  + `PARAMS` rows, `category_of(SectionMarker)` splits on `cardinal` (Elevation / Section),
  `category_of(DetailMarker) == "Detail"`; `system_blocks.ANNOTATION_CATEGORIES`, `LABEL_FIELD`,
  `SYSTEM_DEFAULTS`, three seed `.fpdb` under `firepro3d/system_blocks/Tags/`. Project default only --
  Annotation pane rows, no per-marker Tag row (Q10; follow-up filed).
- **Marks**: Detail and Section become full `marks.MARK_CATEGORIES` members (Q6c): pattern rows
  (`{n}` default, Q8b), mint on create, duplicate flag, Renumber category, blank panel edit
  refused (M16). Cardinals bind the Direction letter and never mint or plot (Q8). Load adopts the
  name's last token as the Mark once when the record has no `mark` key (Q20; M7 "never re-mint"
  holds for records that carry one). Markers are **not pasteable** today (`_clipboard_item_dicts`
  writes their `to_dict`, `_paste_accepts` drops the record), so there is no paste site to mint at
  and marker paste stays out of scope (probe P-D5, ratified at the D3 gate).
- **Sheet number** (Q6, Q6d): the bottom slot binds the number of the sheet whose viewport is bound
  `(source_view_type, source_view_name)` to the marker's view; blank when unplaced; legacy
  multi-placement cites the first sheet in sheet order (Q6g). No sheet-by-view lookup exists today
  (only `Model_Space.schematic_sheet_users(block_id)`): it is **generalized** into one
  `SheetManager.sheets_holding(view_type, name)` that the schematic caller, the `Sheet` getter and
  the drop refusal all use.
- **One-sheet rule** (Q6e / Q6f, phase-drift absorbed): a detail or section view may be placed on one
  sheet; a second drop is refused with a notice in `PaperGraphicsView.dropEvent` (today it refuses
  only a bad MIME, a cancelled dialog or an unresolved source) and the browser leaf is disabled
  (`project_browser.set_placed_views`, which today only italicises); plans and
  schematics stay multi-placeable; a legacy file holding two placements loads as-is and only new
  drops are blocked (Q6g). `paper-space.md`'s "the same view can appear at 1:100 on one sheet and
  1:50 on another" is narrowed to plans / schematics.
- **Annotation band** (Q13-Q17): one band above every model item in the shown slab in plan, detail,
  paper viewport and section scenes, with the sub-order text / dims < tags + labels + node badge <
  gridlines + bubbles < view markers. **Qt child z is local to the parent**, so the Room tag (child of
  `Room`) and the hydraulic node badge (child of `Node`) become **top-level** items synced by their
  host -- the SB4a pipe-label pattern (`child=False`; position on move, z in the band, removal with
  the host). Symbol items stay model: sprinklers already inherit their node's elevation z (they are
  `Node` children -- no row needed); `WaterSupply` (static 50) and the riser symbol (static 200,
  top-level) get elevation rows above Node (Q16). The section depth walk is **bounded** so 12,000
  projected items never reach the band (Q17). Values live in `constants.py`; the order is owned by
  `view-relationships.md` 7.3 (Rule A).
- **Detail tab** keeps its own callout bright above the crop mask and draggable (Q12) -- the
  `Model_View.drawForeground` repaint path is reworked to paint the block head + leader.
- Display Manager: the Section Marker (`key "Elevation Marker"`) row splits into Elevation / Section
  rows plus Detail; each acts on the **line only** (Colour tints crop box / leader / cut line / arrow;
  Fill / Font / Scale dropped, stale values ignored), as SB4b/c (Q11). Divergence found at the probe
  and fixed here: `_read_item_display_state` has no DetailMarker branch, so the Detail Marker row's
  read-back never read the item's `_tag_color` / `_fill_color`.
- Out of scope: per-marker Tag row, a `{a}` letter pattern token, a per-sheet pick if multi-placement
  returns, SB4e badge conversion (the badge only moves into the band here, keeping its SVG look),
  marker copy / paste, and migrating the literal 200-300 tool-overlay z values to `Z_PREVIEW`
  (filed as a follow-up; until then tool previews draw under annotations).

## Design Decisions (ratified at the Phase 3 brainstorming gate, 2026-11-03)

Each row was probed against the code (scouts P-D1 / P-D5: P1 / P2 / P4) before the user approved it;
the corrections the probes forced are in the row text.

| Id | Decision | Ratified by |
|----|----------|-------------|
| D1 | **Heads.** `SectionMarker` owns `head` (cardinal: one `ViewMarkerHead(OutlinedLabel)` at `_cardinal_centre()`) or `head_a` / `head_b` (placed: one per cut end, origins on the cut endpoints `_a` / `_b` -- there is no centre helper for them today); `DetailMarker` owns `bubble` at `_bubble_pos`. All `child=True`, upright, data host = the marker -- the pattern `GridlineBubble` already uses in the plan scene. Wedge / triangle built from `head.outline_path()`'s enclosing circle radius `R_k`; cardinal `_WEDGE_DIST = R_k / sin 40 deg`, gap 25 mm model (Q4). | approval Q-D1+D2 |
| D2 | **Categories + seeds.** Elevation (`Direction` letter; `LABEL_FIELD` `Direction`; `PAINT_WHEN_BLANK`), Section (`Mark`, `Sheet`), Detail (`Mark`, `Sheet`). Seeds: Elevation head = circle + `@[Direction]`; Section / Detail = circle split by a line, `@[Mark]` top, `@[Sheet]` bottom, first-cut at today's proportions (3R / 2R / 3R x `BUBBLE_RADIUS_MM`), restyled at smoke (Q19). | approval Q-D1+D2 |
| D3 | **Marks.** `MARK_CATEGORIES += ("Section", "Detail")`, `DEFAULT_PATTERNS` `{n}`; `marks.items_of_category` (an if / elif chain) gains both branches: placed sections (never cardinals) / detail markers; `category_of` learns both classes (Elevation / Section split on `cardinal`); mint at the two shipped creation sites, `SectionManager.place_section` and `DetailViewManager.create_detail` -- no paste site (markers do not paste today); `_mark` field + sparse `mark` key in both `to_dict`s; load adopts the name token once. Panel `Mark` row on both; Renumber Category combo gains both. | approval Q-D3 |
| D4 | **Sheet slot + one-sheet rule.** `SheetManager.sheets_holding(view_type, name)` generalized from `Model_Space.schematic_sheet_users` (that caller rewritten onto it); the `element_params` `Sheet` getter reads its first hit's `Sheet.number`; `PaperGraphicsView.dropEvent` refuses a second detail / section drop (status notice), `project_browser.set_placed_views` disables the placed leaf for those types (italic stays for plans). A placement / removal / sheet renumber refreshes the marker heads (pull-on-paint + `refresh_annotation_tags`). | approval Q-D4 |
| D5 | **Band.** `constants.py`: `Z_ANNOT_BASE = 10_000` with sub-bands `Z_ANNOT_TEXT` (10_000) `< Z_ANNOT_TAG` (10_100) `< Z_ANNOT_GRID` (10_200) `< Z_ANNOT_MARKER` (10_300); `Z_PREVIEW` lifted above the band (20_000), `MANIP_Z` 1e6 unchanged; the literal 200-300 tool-overlay z values stay (follow-up). `apply_to_scene`'s `_Z_OVERLAY` walk extended to every annotation holder: `TextItem` + dimension graphics -> TEXT; `BlockInstance` with an annotation `host_category` -> TAG (symbol blocks stay `Z_CAT_CONSTRUCTION`); Room tag and node badge made **top-level** (pipe-label pattern) -> TAG; `GridlineItem` -> GRID; `DetailMarker` + `SectionMarker` (walked for the first time) -> MARKER. `WaterSupply` and the riser symbol get `Z_CATEGORY_BY_CLASS` rows above Node; sprinklers unchanged (Node children). `SectionScene._assign_depth_z_values` clamps its walk below `Z_ANNOT_TEXT`; gridlines / datums -> GRID; `_HostedBlockCopy` (depth-walked today) -> TAG. Paper inherits through `scene.render` (already how pipe labels plot). | approval Q-D5 band, Q-D5 children, Q-D5 rest |
| D6 | **Detail tab.** `drawForeground` keeps calling the own marker's callout painter, which now paints the leader bespoke and the block head through the head's own `paint` under the head's scene transform (same painter, above the mask); draggable grip unchanged; other details' markers draw as items. | approval Q-D6+D7 |
| D7 | **DM rows.** Keys "Elevation Marker" (relabelled Elevation Marker), new "Section Marker", "Detail Marker": `fill: None`, `font: None`, `_NO_SCALE_CATEGORIES`; `_apply_*` tints lines only; `_read_item_display_state` gains the DetailMarker branch (the read-back divergence). Retire the bespoke circle / text paint, `_display_font_size`, `_label_font`, `_label_angle`, `_head_polygon`, `_TAG_RADIUS` (guard `tests/test_sb4d_retired_strings.py`). `BUBBLE_RADIUS_MM`, `_R_CARDINAL`, `_R_SECTION` kept only as seed-proportion sources. | approval Q-D6+D7 |
| D8 | **P4 probes (first plan tasks).** (c) the clamped depth walk at 12,000 items; (d) the `PaperGraphicsView.dropEvent` refusal path + browser leaf disable hook; (e) painting a child `OutlinedLabel` through `drawForeground` under its scene transform. Dropped as already exercised in shipped code: (a) child-above-parent painting (`GridlineBubble`, the room tag) and (b) `scene.render` plotting in scene z order (pipe labels on paper). | approval Q-D8 |

## Acceptance Criteria (Phase 2 Q1-Q21, one line each)

1. Three heads draw their category's resolved block (project default) with live bound text; annotative; upright; cardinal arrow and section triangle tangent to the head's enclosing circle and sized from it (Q3-Q5).
2. Detail head = `@[Mark]` over the sheet number; Section head = `@[Mark]` over the sheet number; cardinal = Direction letter, never mints, never plots (Q6, Q8).
3. Detail / Section are full Marks categories: pattern `{n}`, mint, duplicate flag, Renumber, blank refused; load adopts the name token once (Q6c, Q8b, Q20).
4. Sheet slot blank when unplaced, updates on place / remove; one-sheet rule for detail + section (second drop refused + notice, browser leaf disabled); legacy two-placement file loads and cites the first sheet (Q6d-Q6g).
5. Three categories, Annotation pane rows, no per-marker Tag row (Q9, Q10).
6. DM marker rows line-only; Fill / Font / Scale retired, stale values ignored (Q11).
7. Detail tab: own callout bright above the mask, draggable (Q12).
8. Annotation band in plan / detail / paper / section: every annotation above every model item in the shown slab, sub-order text / dims < tags + labels + badge < gridlines + bubbles < view markers; symbols elevation-based above nodes; section walk bounded (Q13-Q17).
9. Spec-session lines 1311 / 1315 absorbed and closed (Q18); first-cut seeds restyled at smoke (Q19).

## Verification Checklist (Q21 guards 1-10, VC3; each shown RED with the change reverted)

1. z census: a scene with a 20 m wall, a Level-2 wall in range, a placed tag block, room tag, pipe label, gridline, detail + section markers, text, a sprinkler -- every annotation's effective z > every model item's, in the Q15 sub-order, after `apply_to_scene`; sprinkler above its own-level wall, below a higher level's.
2. Section: 12,000 projected items never reach the gridline / datum / hosted-block z.
3. Paper: `scene.render` order matches the screen order.
4. Three heads: category + default registered, seed eligibility and bindings, annotative size at two drawing scales, paper mm at two scales, cardinal never plots, upright text on a 30 deg cut, arrow tangent to a circle head (today's geometry) and to a square head's circumcircle, arrow follows k.
5. Detail / Section Marks: mint on create and paste, pattern row, duplicate flag, Renumber, load adopts the name token, blank refused.
6. One-sheet rule: second drop refused with a notice, browser leaf disabled, legacy two-placement file loads and shows the first sheet.
7. Sheet slot: blank when unplaced, updates on place / remove.
8. Detail tab: own callout painted above the mask, draggable.
9. DM rows line-only, stale Fill / Font / Scale ignored, retired strings.
10. Full smoke on a real project.
- Keep-green (VC5): `test_section_marker.py` (radius asserts 294-326), `test_hf1_seam_fixes.py` 407-447, `test_paper_marker_exclusion.py`, `test_manip_griphandle_viewmarker_parity.py`, `test_detail_marker_crop.py`, `test_section_manager.py` 133-142, `test_sb4c_retired_strings.py` 37-38 (`BUBBLE_RADIUS_MM` kept), `test_sb4a_pipe_label.py:308` (the only z guard today).

## Existing Code Context

- `section_marker.py`: `SectionMarker` z `Z_OVERLAY` static; `_R_CARDINAL = 3 x BUBBLE_RADIUS_MM`, `_WEDGE_DIST = R / sin 40 deg`, `_CARDINAL_GAP = 25`, `_R_SECTION = 2 x`, `_TRI = sqrt 2`; `_label_angle` rotates the section label; `PAPER_EXCLUDED = cardinal is not None`.
- `detail_view.py`: `DetailMarker(QGraphicsPathItem)` z `Z_DETAIL_MARKER` 45 at init, forced to `Z_GRIDLINE_BUBBLE` 500 by `level_manager.apply_to_scene` `_Z_OVERLAY`; `_TAG_RADIUS = 3 x BUBBLE_RADIUS_MM`; `_paint_callout` draws leader + bubble + name token + `L1`; `_bubble_pos` serialized; `DetailViewManager.create_detail` / `from_list`.
- `level_manager.py` `apply_to_scene`: `_Z_OVERLAY = {DetailMarker, GridlineItem: Z_GRIDLINE_BUBBLE}`; `_apply_elev_z` = `max(z_range_mm) * Z_ELEV_SCALE + cat_offset`; `SectionMarker` never walked.
- `section_scene.py`: `_assign_depth_z_values` from -50 in 0.01 steps unbounded; gridlines / datums literal 50; `_HostedBlockCopy` depth-walked (the 1000 is the placement ghost only); `_manip_exclude` = `isinstance(item, BoundLabelItem)`.
- `model_view.py` `drawForeground` 278-286: finds the own marker by `_detail_name` and calls `_paint_callout(painter)` above the mask.
- `paper_space.py`: `SheetViewData(source_view_type, source_view_name, view_number)`, `Sheet.number`, `PaperGraphicsView.dropEvent` (no placement refusal), `SheetViewport` renders through `scene.render`; `project_browser.set_placed_views` italicises placed leaves. `Model_Space.schematic_sheet_users` is the only sheet-by-view lookup.
- `display_manager.py`: rows `"Elevation Marker"` (label "Section Marker") and `"Detail Marker"` with fill / font / scale; `_NO_SCALE_CATEGORIES`; `_read_item_display_state` has an `_is_elevation_marker` branch and no DetailMarker one.
- `marks.py`: `MARK_CATEGORIES`, `RENUMBER_CATEGORIES`, `DEFAULT_PATTERNS`, `items_of_category`, `mint` (returns `""` for a class `category_of` does not know).
- Child items with local z today: Room tag (`room.py`, `BoundLabelItem(self)` at `Z_OVERLAY`), `HydraulicNodeBadge` (child of `Node`), `Sprinkler` (child of `Node`), `GridlineBubble` (child of `GridlineItem`). Top-level with static z: `TextItem` 15, `WaterSupply` 50, riser symbol 200, pipe label `max(200, pipe z + 1)`.
- Reuse (1b sweep + Phase 3 probes): REUSE AS-IS `OutlinedLabel` / `BoundLabelItem`, `TagBlockHost` (not needed: no Tag row), `annotation_block` resolver, `_apply_block` paper pass + `_elev_heads`, `AnnotationPane` auto-rows, `refresh_annotation_tags`, the SB4a top-level-label sync pattern (`Pipe.sync_label_z` / `child=False`) for the room tag and badge; GENERALIZE `_manip_exclude` (plan scene needs one), display_manager detail-row read-back, `schematic_sheet_users` -> `SheetManager.sheets_holding`; GAP categories, seeds, host hooks, drawForeground rework, band constants, one-sheet rule.

## Follow-ups to file at Phase 6

- Migrate the literal 200-300 tool-overlay z values (`scene_tools`, `geometry_drawing_controller`, `model_space`, `underlay_controller`) to `Z_PREVIEW` so tool previews draw above the annotation band (D5 ratified "lift previews" without the migration).
- Per-marker Tag row for the three marker categories (Q10); `{a}` letter pattern token (Q8b); per-sheet pick if multi-placement returns (Q6d); SB4e node-badge block conversion (the badge is top-level in the band after D5).

## Breaking changes (ratified Phase 2)

Section label upright (was rotated along the cut); detail callout bottom slot level -> sheet number; DM Font / Scale / Fill retired on the marker rows; a second sheet drop of a detail / section view is refused.
