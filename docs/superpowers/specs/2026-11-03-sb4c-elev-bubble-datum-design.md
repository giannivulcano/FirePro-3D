---
status: as-built 2026-11-03 (merged 8d95a864, v0.83.0)
task: "SB4c -- Convert the elevation gridline bubble + level datum head to System blocks (todo_open.md)"
base: 1adb7e84
branch: feat/sb4c-elev-bubble-datum
consolidates: system-blocks.md (new s8c), element-parameters.md (Level category), section-view-subsystem.md, grid-system.md s8.5 / s10, paper-space.md s9.9.1, display-manager rows
---

# SB4c -- Elevation gridline bubble + level datum head as System blocks

Consolidating contract for SB4c (three or more specs touched, Rule A): at Account each
linked spec gets a one-line pointer here, and the contract moves into `system-blocks.md`
s8c the way SB4b's moved into s8b. Template / precedent:
[`2026-11-02-sb4b-gridline-bubble-design.md`](2026-11-02-sb4b-gridline-bubble-design.md).

## Goal

Elevation / section gridline bubbles draw the **same System block as their plan gridline**
(one design drives both views), and the level datum head (symbol + name + elevation) is a
**user-designable System block**. Both are annotative: they scale with zoom and print at
their authored size.

## Motivation

User end goal (Phase 2 grill, 2026-11-03): "Match plan + restyle". SB4b converted the plan
bubble but left elevation bubbles bespoke, still reading the Display Manager Grid Line Fill /
Scale that SB4b retired from the UI (last saved value sticks with no UI). The datum head
is a fixed 4-quadrant circle sized by the DM Level Datum Scale / Font.

## Architecture & Constraints

- Concept Q9 composite rule: heads only; lines and extents stay bespoke in
  `section_scene.py`. Datum line + head as one linear block is deferred to **SB8**
  (todo_open.md SB8 +1 occurrence, 2026-11-03); the head block is authored to become its end block.
- `BoundLabelItem` resolves its block through `self.scene().annotation_block` and pulls data
  from `_host` (`element_params.host_values`, keyed by `category_of(host)`).
  `SectionScene` has no resolver today, so an unforwarded label there draws nothing.
- Annotative k on a section canvas = `_ms.scale_manager.drawing_scale`; on paper `1/S`
  through `_paper_scale` (SB1c design doc; `annotative.py`).
- Out of scope: per-view datum extents (`view-relationships.md` s7.5), SB8.

## Design Decisions

| Id | Decision | Gate |
|----|----------|------|
| D1 | **Separate data host (approach A).** `BoundLabelItem(host, *, child=True, parent=None)`: a given `parent` is the graphics parent, `host` stays the data source. `SectionScene.annotation_block(category, mapped=None)` forwards to `self._ms.annotation_block`. New `SectionScene.refresh_annotation_tags()` re-shapes its elevation bubbles and datum heads; `Model_Space.refresh_annotation_tags` also walks `self._section_manager.open_scenes` (if set). `GridlineBubble`'s outline / trim / overlay machinery is lifted into `OutlinedLabel(BoundLabelItem)` (bound_label.py or gridline.py, plan decides); `GridlineBubble(OutlinedLabel)` adds the duplicate flag. | Phase 3 approach + D1 approval |
| D2 | **Elevation gridline.** `ElevGridlineItem(..., gridline=gl)` keeps the plan `GridlineItem` and owns `bubble1` / `bubble2 = GridlineBubble(gl, parent=self)` at the top / bottom end. Top visible iff `gl.bubble1.isVisible()`, bottom iff `gl.bubble2.isVisible()` (AC2). Duplicate flag copied from the plan bubbles. `ElevGridlineItem` exposes the overlay contract `_paper_render`, `_grid_color`, `isSelected()`. The line trims at each visible bubble by `trim_distance(0, -1)` / `(0, 1)` on screen and paper; `_bubble_r`, `BUBBLE_R`, `_paper_bubble_r` retire. Z-extent overrides stay label-keyed. | D2 approval |
| D3 | **Datum head.** New `element_params` category `"Level"` (CATEGORIES + PARAMS row: `Level.Name` text, `Level.Elevation` length via the project ScaleManager); `category_of(ElevDatumItem) -> "Level"`, getters read `item._level`. `ElevDatumItem` keeps its `Level` and owns one `LevelDatumHead(OutlinedLabel)` (`child=True`) at the left end, origin on the line at today's circle centre. `drawForeground` starts the line at the head's `trim_distance(1, 0)`. Selected datum -> head outline ring (screen only). `system_blocks`: `ANNOTATION_CATEGORIES += ("Level",)`, `LABEL_FIELD["Level"] = "Level.Name"`, `SYSTEM_DEFAULTS["Level"] = "system-tags-leveldatum"`; seed `firepro3d/system_blocks/Tags/LevelDatum.fpdb`. Project default only (Annotation pane Level row; no per-level Tag). Name shown as typed. Bespoke fonts, upper-casing, quadrant items retire. | D3 approval |
| D4 | **DM + paper.** DM Level Datum row `fill: None`, `font: None`, in `_NO_SCALE_CATEGORIES`; `_gridline_display_props` / `_datum_display_props` read colour / opacity / visible only (colour tints the line; Visible / Opacity act on the whole item). Paper elevation branch keeps `enter_paper_pass` for line weight + dash only, then `_apply_block` on each visible bubble / head with opacity 1; `restore_model_display` restores the block hooks. `_HAS_FILL` drops "Grid Line" and "Level Datum". | D4 approval |
| D5 | **Retire** (guard `tests/test_sb4c_retired_strings.py`): `_ElevBubble`, `bubble_paper_geometry`, `GRIDLINE_BUBBLE_PAPER_CAP_MM`, `GRIDLINE_BUBBLE_LABEL_EM_FRAC`, `_paper_bubble_r`, the fill / scale / font display reads. **Keep `BUBBLE_RADIUS_MM`** (section_marker / detail_view use it; the task line was wrong). | Phase 2 AC9 |
| D6 | **Freshness probe (P4, first plan step).** Does a plan Mark rename, Tag change or bubble-visibility toggle rebuild or repaint open section scenes today? If not, the plan wires it (pull-on-paint covers Mark; visibility / duplicate are copied at build). | as-proposed, pending the probe |

## Acceptance Criteria

AC1-AC9 as ratified at the Phase 2 grill (2026-11-03), restated in one line each:

1. Elevation bubble draws the plan gridline's resolved block (`tag_block` -> project default) with its `@[Mark]`; annotative; upright.
2. Plan Bubble 1 -> elevation top, Bubble 2 -> bottom, every elevation / section.
3. Datum head is one `Level` block (project default only), seed reproduces today, left end only, name as typed.
4. Elevation line and datum line trim at the block outline, screen and paper.
5. Selection ring + orange duplicate ring on elevation bubbles; datum head ring; screen only.
6. DM Level Datum row line-only; Fill / Font / Scale retired; elevation stops reading Grid Line Fill / Scale.
7. Paper via `_apply_block` at authored size; line keeps paper weight / dash.
8. Selection, HALO hover, grips, z-overrides, snaps, paper rows unchanged.
9. Retirements per D5, guarded.

## Verification Checklist (guards, VC3; each shown RED with the change reverted)

- Changing the plan gridline's `tag_block` changes the elevation bubble's painted ops (real SectionScene built from a real Model_Space).
- Hiding plan Bubble 1 hides the elevation top bubble only.
- Datum head paints `Level.Name` / `Level.Elevation`; renaming the level re-paints the text.
- `trim_distance` follows a non-circular test block on the elevation line and the datum line (painted line endpoints).
- Overlay pens present on screen, absent during the paper pass.
- DM Level Datum row has no Fill / Font / Scale; a saved `display/Level Datum/scale` does not change the head.
- Paper pass routes heads through `_apply_block`; head prints at authored mm at two viewport scales.
- `tests/test_sb4c_retired_strings.py`.
- Keep-green: findings note set + the rewritten `test_sb3_annotation_defaults.py` / `test_sb3_system_default.py` tuple pins (VC5).

## Existing Code Context

Probe record: `docs/superpowers/plans/2026-11-03-sb4c-1b-findings.md` (local). Key seams:
`bound_label.BoundLabelItem._resolve`, `gridline.GridlineBubble`, `section_scene._project_gridlines`
/ `_project_level_datums` / `drawForeground` / `ElevGridlineItem.paint`, `paper_display` elevation
branch + `_apply_block` + `restore_model_display`, `section_manager.SectionManager.open_scenes`,
`element_params.category_of` / `PARAMS`, `system_blocks`, `display_manager` Level Datum row.

## As-built (2026-11-03)

Merged at `8d95a864` (v0.83.0). The contract now lives in `system-blocks.md` s8c; this record
keeps the decisions above as ratified and lists what the build corrected. Commits: D1 / D2
`bd9ee87a` `0afa894b` `e167026d` `0075f6bd`; D3 `75727c2d` `05a10c98` `7f158ded`; D4 `e7a3b152`
`b6c5325a`; D5 `9ee80b79`; VC9 `48da1062`; smoke `6f54b2fc`.

1. **D2 trim direction.** The ray from each bubble toward its line is derived from `p1 -> p2`
   (top bubble (0, +1) in Qt y-down, bottom (0, -1)); the `trim_distance(0, -1)` / `(0, 1)` order
   written in D2 is reversed. The datum head's ray toward `_h_max` is (+1, 0).
2. **D2 visibility.** The top bubble is visible iff `gl.bubble1.isVisibleTo(gl)` (the per-end toggle,
   independent of the plan item's own visibility), the bottom iff `gl.bubble2.isVisibleTo(gl)`;
   D2's `isVisible()` would have hidden both ends with a plan-hidden gridline.
3. **D6 probe result.** Every UI path (a Properties Mark / Bubble 1 / Bubble 2 commit, a Tag pick)
   already emits `sceneModified`, which reschedules `SectionScene._schedule_rebuild`; no wiring
   was added, and Mark is pulled at paint.
4. **element-parameters E3.** The `Level` category's own keys keep the `Level.` prefix (`Level.Name`,
   `Level.Elevation`, tier 1 Stored); folded into `element-parameters.md` E3 at Account.
5. **Smoke fixes (`6f54b2fc`).** `OutlinedLabel.outline_path` unions snapped operands
   (`WALL_OUTLINE_SNAP`): Qt clipper noise on a coincident-corner seed produced an empty union.
   `ElevDatumItem.halo_trace_path` starts at the head outline. The shipped `LevelDatum.fpdb` is the
   user's Block Editor restyle (a 3 mm-radius circle, crossed centre lines, two filled quadrants,
   `@[Level.Name]` / `@[Level.Elevation]`), so it no longer reproduces today's head as D3 / AC3 say.
6. **VC9 fix (`48da1062`).** `ElevDatumItem.enter_paper_pass` / `exit_paper_pass` call
   `prepareGeometryChange()`, like the gridline's.
