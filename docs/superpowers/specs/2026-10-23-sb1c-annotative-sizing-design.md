---
status: proposal
last-verified: 2026-10-23
verified-commit: 1f158ae8
applies-to:
  - firepro3d/annotative.py            # new
  - firepro3d/block_instance.py
  - firepro3d/block_definition.py
  - firepro3d/block_properties_info.py
  - firepro3d/paper_display.py
  - firepro3d/display_manager.py
  - firepro3d/gridline.py
  - firepro3d/room.py
  - firepro3d/constants.py
  - main.py
source-tasks: [todo_open.md "SB1c -- Annotative sizing"]
---

# SB1c -- Annotative sizing -- Design Spec

Consolidating contract spec for SB1c. The owning specs (block-system DD9, paper-space s9.9,
view-relationships, linetypes ET1, System Blocks concept F6/F8) get one-line pointers here at
Account; their full rewrites are follow-ups (Rule A).

## Goal

A block whose Scale mode is **Annotative** is authored in printed millimetres and plots at that
printed size in every sheet viewport and in PDF / print, whatever the viewport scale. On model
canvases it either scales with the project drawing scale (default) or stays a fixed screen size.
Gridline bubbles and room labels plot at fixed printed sizes through the same conversion.

## Motivation

Tags, notes, detail markers and gridline heads must read the same on every sheet (Revit-like
annotation behaviour). Today `scale_mode: "annotative"` is stored (SB1a) but paints real size, and
the paper heights of bubbles and room labels are per-category Display Manager settings.

## Architecture & Constraints

- **No per-view scale.** `PlanView.scale` and a detail-view scale are **dropped** (Phase 2
  ruling 2026-10-23): annotations stay consistent across views; model-geometry blocks (doors,
  schematics) stay real size and scale with their view. This amends concept F6 / F8.
- **One factor, three contexts** -- `annotative.annotative_factor(item, painter=None) -> float`,
  decided in this order:

  | Context | Factor k (scene units per authored mm) |
  |---|---|
  | paper pass (`paper_display.paper_pass_active()` and the item's `_paper_scale` S) | `1 / S` |
  | model canvas, On screen = Fixed size (`linetype_render.screen_fixed_here`; plan / block_editor roles) | `FIXED_END_PX_PER_MM / device_scale` (painter) |
  | otherwise (Scale with zoom, default) | `ScaleManager.drawing_scale` |

  It reuses the ET1 end-type gates (`linetype_render.printed_factor`, `screen_fixed_here`,
  `end_render.screen_factor`, `mark_screen_ends`); it adds no new rule.
- No third view pattern (view-relationships s5.3): sizing is per paint on the shared scene.
- Constants live in `constants.py` (no magic numbers).

## Design Decisions

| # | Decision | Rationale / ratified by |
|---|---|---|
| D1 | Approach A: paint-time helper reusing the ET1 gates (not a Qt item transform) | an item transform is shared by every view, so Fixed size cannot be right in two differently-zoomed views; AskUserQuestion 2026-10-23 |
| D2 | Definition key `annotative_screen: "scale" \| "fixed"` (values `end_render.SCREEN_SCALE` / `SCREEN_FIXED`); default and missing-key = `"scale"`; meaningful only when `scale_mode == "annotative"`; carried by definition `to_dict`/`from_dict` and the `.fpdb` library | Phase 2 grill: default Scale with zoom |
| D3 | Scale with zoom and paper fold k into the memoised variant: `render_ops_variant(mirrored, pose_scale * k)` (scales about the base point = insertion point) | bounds, `shape()`, HALO pick and box select stay exact with no extra code |
| D4 | Fixed size: unscaled variant, painter scaled by k about the insertion point; `boundingRect` / `shape` / `_frame_rect` apply the same k from the last device scale and the item registers via `mark_screen_ends` so the view zoom hook re-prepares it | ET1 spec C precedent |
| D5 | Nested blocks are flattened at compile, so a nested child follows its top-level parent's mode (annotative child in a real-size parent paints real size); in the Block Editor nested instances paint at k = 1 | WYSIWYG with the compiled result; section 2 approval |
| D6 | Paper pass: `_apply_block` calls `prepareGeometryChange` on an annotative instance before setting `_paper_scale` and again at restore; `paper_export` / print unchanged (same `SheetViewport.paint`) | the scene echo guard absorbs it |
| D7 | Drawing-scale change: `_on_project_settings_changed` re-prepares the plan's annotative instances (today only editors are re-prepared) | trigger today is project load; the UI stays L715 (Phase 2 ruling) |
| D8 | Block properties: row "On screen: Fixed size \| Scale with zoom" (`linetype_render.SCREEN_LABELS`) directly under "Scale mode", shown only when Annotative and never for schematic editors (`block_properties_info.py` `if not schematic:` gate); switching Scale mode refreshes the panel | LTS-1 precedent; section 2 approval |
| D9 | Block Editor: 1 drawn mm = 1 printed mm for an annotative definition; ends / linetypes keep the ET1-1 drawing-scale preview | Phase 2 grill "Printed mm, like ends" |
| D10 | Shared paper conversion `annotative.paper_scene_size(mm, S) = mm / S` used by `_apply_room_label_paper_height` with `ROOM_LABEL_PAPER_CAP_MM = 2.5` and by `_apply_gridline` plus the elevation-gridline caller with `GRIDLINE_BUBBLE_PAPER_CAP_MM = 3.0` (to `bubble_paper_geometry`); per-type mutate/restore helpers stay until SB3 / SB4b | Phase 2 AC5 / AC6 |
| D11 | Model canvas unchanged for bubbles (`GridBubble.RADIUS_PX` 14 px screen-fixed) and room labels (150 mm model) | Phase 2 grill "Keep today" x2 |
| D12 | Retire factory keys `bubble_label_height_mm` / `label_height_mm` and their settings backfill (`paper_display.py`), and the Grid Line "Label Ht" Display Manager column (header, editor, write-back, reset in `display_manager.py`); stored QSettings values are never read again | Phase 2 grill "Retire now" + "Ignore; plot at 2.5 / 3.0" |
| D13 | P4, plan step 1: probe whether `RenderOp.mapped` scales pen widths and text with the path, and how the property panel refreshes after an enum edit; record the result before code relies on it | P4 |

## Acceptance Criteria

- [ ] AC1 Annotative blocks plot at authored mm in every sheet viewport (plan, detail,
      section / elevation, NTS via fit) and PDF / print; two viewports at different scales give
      the same printed size.
- [ ] AC2 "On screen" row (default Scale with zoom): Scale with zoom = authored mm x
      `drawing_scale` model units; Fixed = authored mm x 6 px at any zoom.
- [ ] AC3 Block Editor stores authored geometry 1:1 in printed mm.
- [ ] AC4 Real-size blocks unchanged.
- [ ] AC5 Gridline bubbles: canvas 14 px unchanged; paper 3.0 mm cap via the shared conversion.
- [ ] AC6 Room labels: canvas 150 mm unchanged; paper 2.5 mm via the shared conversion.
- [ ] AC7 Grid Line "Label Ht" DM column and both stored keys retired; a stale stored value is
      ignored. (Probe correction: Room `label_height_mm` never had a DM row.)
- [ ] AC8 No drawing-scale UI (stays task L715).

## Verification Checklist

Guards drive the real entry point under QSettings isolation and are shown RED with the change
reverted. The acceptance gate is the exported PDF at real scale.

- [ ] G3 PDF: one annotative block (3 mm text + 3 mm circle) in viewports at 1:50, 1:200 and NTS
      -> measured cap height and radius = authored mm in all three.
- [ ] G-zoom: shown plan view, Scale with zoom -> scene extent = authored x `drawing_scale` at
      two zooms.
- [ ] G-fixed: shown view, Fixed -> device-pixel extent = authored x 6 at two zooms;
      `boundingRect` follows the zoom.
- [ ] G-pick: HALO click and box select hit the scaled extent, miss outside it.
- [ ] G-real: real-size instance unchanged (plan / paper parity at 1:4 ratio).
- [ ] G-bubble / G-room: paper 3.0 / 2.5 mm, canvas unchanged, exact restore after the pass.
- [ ] G-DM: Label Ht column gone; a stale stored 4.0 plots 3.0.
- [ ] G-editor: a 3 mm circle stores 3; the On screen row shows only for Annotative and
      round-trips save / reload.
- [ ] Keep-green: `tests/test_gridline_paper_scale.py` and `tests/test_paper_display.py`
      rewritten for the retired keys; every test referencing a touched module (VC5 grep).

## Existing Code Context

- `block_instance.py`: pose baked into ops (`render_ops` -> `BlockDefinition.render_ops_variant`);
  `boundingRect` / `shape` from ops; paint ignores `widget`; ends already use
  `end_render.mark_screen_ends`; paper hooks are attributes set by `paper_display._apply_block`.
- `paper_display.py`: `apply_paper_overrides` (iterates `scene.items(source_rect)`),
  `restore_model_display`, `_apply_room_label_paper_height`, `_apply_gridline`,
  `_save_gridline_state`.
- `gridline.py`: `GridBubble.enter_paper_mode` / `exit_paper_mode`, `bubble_paper_geometry`.
- `paper_space.py`: `SheetViewport.paint` computes S as the fit scale.
- `main.py`: `_seed_editor_units`, `_on_project_settings_changed`.

## Edge Cases & Error Handling

- **Crop edge (known limit):** the paper pass selects items by model bounds within the viewport
  crop; an annotative block whose insertion point is just outside the crop and whose paper size
  exceeds its model bounds (for example at 1:200) does not plot.
- Nested modes follow the top-level parent (D5).
- A failed paper pass unwinds through the existing `apply_paper_overrides` exception path; the
  restore re-prepares geometry.

## Spec amendments at Account (pointers, Rule A)

- System Blocks concept F6 / F8: no per-view scale; links here.
- `block-system.md` DD9: annotative is live; `annotative_screen` key.
- `paper-space.md` s9.9: stored DM heights retired for constants; fix the `_save_gridline_state`
  drift (the rect / font / position capture is in `enter_paper_mode`).
- `view-relationships.md`: no new view pattern (one line).
- `linetypes.md` ET1: annotative blocks reuse its gates.
- `SPEC-INDEX.md`: stale System Blocks row.
