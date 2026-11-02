---
status: built  # built 2026-11-02 (feat/text-sizing-wrap, merged 6693013b, v0.80.0); as-built deviations folded into D4-D8
last-verified: 2026-11-02  # Account: D4 tri-state, D5 bound-seed scope + Block Editor hug + live re-layout, D6 _scaled_text_record, D8 keys + one Precision column + cross-family unit, AC / checklist ticks; prior 2026-11-01
verified-commit: 6693013b  # merge feat/text-sizing-wrap; prior fffb283a
applies-to:
  - firepro3d/text_item.py
  - firepro3d/paper_space.py
  - firepro3d/paper_commands.py
  - firepro3d/sketch_adapters.py
  - firepro3d/model_space.py
  - firepro3d/block_attributes.py
  - firepro3d/block_attributes_editor.py
  - firepro3d/block_explode.py
  - firepro3d/network_codec.py
  - firepro3d/element_params.py
  - firepro3d/scale_manager.py
  - firepro3d/property_manager.py
  - firepro3d/settings/panes.py
  - firepro3d/annotative.py
source-tasks:
  - "TextItem scene-mm font integer px sizing [bug P1] (+1 SB4a height/padding)"
  - "Per-attribute Unit + Precision override, default Per project settings [feature P1]"
  - "Text box Wrap toggle + Shrink to fit toggle (absorbs Fit to contents) [feature P2]"
---

# Text sizing, Wrap / Shrink to fit, attribute precision — Design Spec

Consolidating contract for three batched tasks. It spans the text, system-blocks,
element-parameters, units-and-formatting, property-panel and constraint specs;
at Account each of those gets a one-line pointer here (Rule A), and their full
rewrites are a filed follow-up.

## Goal

1. Text draws at its true cap height with even letter spacing at every size,
   and its Height can be entered in fine steps (pt for printed text, decimal mm
   for real-size text).
2. Every text box (model, Block Editor, sheet) has a **Wrap** toggle and a
   **Shrink to fit** toggle.
3. A block attribute definition can override the Unit and Precision its value
   prints with; the default is "Per project settings".

## Motivation

The SB4a PipeLabel smoke showed small annotative text is unusable: 3 mm text
draws at 2.86 mm with letters touching, so the author fell back to 2 mm with
no padding. Text boxes have no way to stop wrapping or to hug their content
(the bound-text hug is a hidden special case). Tag values print in fixed
formats with no per-tag control.

## Architecture & Constraints

- Geometry stays in mm; the stored text height stays **cap height in mm**
  (text-annotation-system). pt is a display/parse convention only.
- Display formatting is owned by `ScaleManager` (units-and-formatting); no new
  formatter lives outside it.
- Sparse serialization for new booleans (the `keep_upright` / `hide_empty`
  convention): absent key = legacy default.
- Opening an existing file moves nothing except the L96 true-cap correction.
- `TextItem.itemChange` live-syncs `data.x/y` from `pos()`; layout-time offsets
  must never be applied through `setPos`.

## Design Decisions

Ratified in Phase 2 (G1–G13) and Phase 3 (G14, approach A, sections 1–4) of
the 2026-11-01 /todo run.

### D1 — True cap height (L96)
Model and Block Editor text use the sheet-text sizing path: font pixel size
fixed at `TEXT_METRIC_REF_PX`, item `setScale(h / cap)`. The scene-mm branch
that rounded `TEXT_METRIC_REF_PX * h / cap` to a whole pixel is removed.
Margin and wrap width already divide by `scale()`; the 1b reuse sweep found
every consumer scale-aware. Stale comments describing "scale stays 1" are
rewritten.

### D2 — Height entry
- Sheet text and text in an **annotative** block (`annotative.is_annotative`)
  show and parse Height as a Word-style pt font size (decimals, e.g. `10.5 pt`).
  The existing `_text_cap_ratio` / `_font_pt_from_mm` / `_mm_from_font_pt` /
  `_format_height_pt` / `_parse_height_pt` helpers move from `paper_space.py`
  to `text_item.py` (one home; `paper_space` imports them).
- Real-size model / block text shows Height in mm with decimals (minimum > 0);
  the integer rounding is removed.
- 12 pt Arial ≈ 3.0 mm cap.

### D3 — Annotative Block Editor defaults
New text placed in an annotative block definition is seeded at 3 mm cap and
1 mm padding. Model space and real-size blocks keep
`DEFAULT_MODEL_TEXT_HEIGHT_MM` (100) / 15 mm. New constants in `constants.py`.

### D4 — Wrap / Shrink data model (approach A)
`TextAnnotationData` gains `wrap` and `shrink`, each `bool | None`: `None` = not
authored = the legacy default, resolved live by `wrap_on()` / `shrink_on()`;
`to_dict` writes a key only when the flag is authored (not `None`).
- legacy `shrink` = bound text (holds an `@[Field]`, G12/G13) **in the block
  layer** only: placed / exploded copies through `hugged_text_record`, and an
  item on a `scene_role == "block_editor"` scene. Sheet or plan text holding
  a title-block style token is never seeded.
- legacy `wrap` = `wrap_width_mm > 0` and not the seeded hug.
- `wrap_width_mm` / `box_height_mm` / `x` / `y` always hold the **authored**
  box. Turning a toggle off restores it (G2).

### D5 — Layout resolver
All sizing is resolved in `TextItem` layout (`_apply_format`), so every reader
that builds a `TextItem` (block compile, explode, sketch adapters, snap,
export) gets it without change:
- Wrap ON: `setTextWidth(wrap_width_mm / scale)`; Wrap OFF: `setTextWidth(-1)`
  then `idealWidth()`, so lines break only at typed Enter (G2).
- Shrink ON: width = widest laid-out line + padding (longest line when Wrap is
  off, widest wrapped line when on); height = content; the authored
  `box_height_mm` floor is ignored (G3).
- Shrink keeps the authored box's alignment point (`align` × `valign`) fixed by
  a **local** offset on the painted/hit geometry, never via `setPos` (see
  Architecture). The first plan step probes this offset against
  `boundingRect`, `shape`, grips and snap.
- While inline-editing, every document content change re-runs the width step
  (`TextItem._apply_wrap_width` on `contentsChanged`), so typed text widens a
  Wrap-OFF box and re-hugs a Shrink box live (smoke fix, 2026-11-02).
- The Block Editor shows the hug: bound text there hugs its displayed (sample
  or token) text about the authored alignment point, WYSIWYG with placed
  copies (Phase 4 ruling).
- `block_attributes.hugged_text_record` keeps its call sites, but its sizing
  core goes away: a bound text seeded `shrink` hugs through D5, so the
  function reduces to value substitution (SB3 U4 ruling preserved as the
  seeded default).

### D6 — Writers (G4, G14)
A grip drag, a sheet `ResizeTextBoxCommand`, or a constraint dimension
(`_TextBoxAdapter.write`, parametric-constraint D59) that sets a width or
height writes an explicit size and sets `shrink = False`; setting a width also
sets `wrap = True`. One undo step: the command's state tuple and the sketch
adapter carry both flags. Model placement seeds `wrap` from the drawn width
as today. `block_explode._scaled_text_record` and `network_codec` copy and map
the flags.

### D7 — Panel toggles
Wrap and Shrink to fit are bool rows (the `keep_upright` row shape) on model
text, Block Editor text and sheet text panels, undo-routed. Bound text shows
them too (G12).

### D8 — Attribute Unit + Precision override (L340)
- `normalise_attr` accepts two optional sparse keys: `unit` (one of the
  project's length display units; area/volume follow the length family) and
  `display_precision` (int 0–5, clamped). Absent = "Per project settings".
  The existing `precision` key keeps its A8 meaning (a `number` attribute's
  decimals); it is not reused, because every stored record carries it (0 on
  the shipped tags) and reading it as an override would move legacy files.
  A malformed `precision` reads 0 and a malformed `unit` / `display_precision`
  is dropped, so the record loads; an unknown `type` / `source` still raises.
- `format_value` formats a `HostValue` through `sm.with_overrides(unit=,
  precision=)`, a `ScaleManager` clone. Imperial length precision keeps the
  project meaning (fraction denominator `2**p`). Hydraulic kinds accept
  precision only (G7). A `number` attribute takes the unit only; it prints at
  its own `precision`. A unit override with no precision override keeps the
  project's precision integer, read in the new family (project imperial 3 =
  1/8" -> a metric override prints 3 decimals).
- The Block Editor Attributes editor (`block_attributes_editor.py`) keeps ONE
  Precision column, now a dropdown ("Per project settings", 0–5), and gains a
  Unit column ("Per project settings" default). The row type decides the key:
  a `number` row edits `precision` ("Per project settings" there saves 0 --
  accepted at smoke, 2026-11-02), a host `text` row edits `display_precision`.
  A text record's own `precision` rides on the widget and is written back
  unchanged. Every placed copy follows the definition (G5).

### D9 — Project hydraulic precision (G6)
`ScaleManager` gains `pressure_precision` / `flow_precision` /
`velocity_precision` (defaults 1 / 0 / 1, written sparsely in `to_dict`).
`format_pressure` / `format_flow` / `format_velocity` become instance methods
(three call sites). Project Settings > Units & Precision gains three rows.
Units stay psi / gpm / ft/s (units D2; metric hydraulics is out of scope).

### Approaches rejected
- **B: write the hug into the stored fields.** Every text edit would mutate
  geometry in undo, needs extra remembered-width fields, and cannot serve bound
  text (one definition record, many values) — leaving two hug mechanisms.
- **Per-instance precision override** (Edit Attributes dialog): rejected for
  the definition record (G5).

## Acceptance Criteria

- [x] AC1 3 mm text draws a 3.0 mm cap (±1%; today 2.863) at 2, 3 and 100 mm, with glyph advances within 2% of ideal.
- [x] AC2 Height shows/parses in pt (decimals) on sheet and annotative-block text; mm with decimals on real-size text; storage stays cap mm.
- [x] AC3 New text in an annotative Block Editor block stores 3 mm / 1 mm; model and real-size blocks keep 100 / 15.
- [x] AC4 RoomTag pixel lock and SB3 parity goldens re-captured; PipeLabel / RoomTag seed sizes unchanged.
- [x] AC5 Attributes editor Unit + Precision per record, default "Per project settings"; every placed copy follows.
- [x] AC6 Unit list = the project's; hydraulic kinds precision-only.
- [x] AC7 Project Pressure / Flow / Velocity precision rows, defaults 1 / 0 / 1 — today's strings unchanged.
- [x] AC8 A malformed precision value no longer raises.
- [x] AC9 Wrap + Shrink toggles on model, Block Editor and sheet text.
- [x] AC10 Wrap OFF: breaks only at Enter; width = longest line + padding; authored width restored on Wrap ON.
- [x] AC11 Shrink ON: hugs both axes; alignment point fixed.
- [x] AC12 Drag / sheet resize / constraint dim on a Shrink box: explicit size, Shrink OFF, one undo step.
- [x] AC13 Width drag on a Wrap-OFF box: Wrap ON at the dragged width, one undo step (G14).
- [x] AC14 Bound text seeded Shrink ON + Wrap OFF; looks as today; author may turn Shrink off.
- [x] AC15 Legacy load moves nothing (flags per D4) except AC1.
- [x] AC16 Flags round-trip through save/load, undo, block explode, copy/paste.

## Verification Checklist

Each guard drives the real path and is shown RED with its rule reverted (VC3).

- [x] T-L96: native-font render, drawn cap at 2/3/100 mm vs h (±1%), 'm' advance at 3 mm vs ideal (RED: restore the rounded pixel size).
- [x] T-height-row: annotative-block row shows pt and accepts 10.5; real-size row accepts 2.5 mm (RED: int rounding).
- [x] T-be-default: text placed in an annotative block stores 3 / 1 (RED: model default).
- [x] T-precision: definition precision 2 on a length attribute → instance shows 2 dp; absent follows a project change; project pressure precision 2 → `12.34 psi` (RED: drop the override in `format_value`).
- [x] T-wrap-off: long text with Wrap off lays out on one line, width = idealWidth + 2·pad; Wrap on restores the authored width.
- [x] T-shrink: box rect = content rect + pad on both axes; alignment point unchanged across a value change.
- [x] T-shrink-anchor-probe: the shrink offset never reaches `data.x/y` through `itemChange`.
- [x] T-drag-off: grip drag on a Shrink box → shrink False, dragged size, one undo restores both; width drag on Wrap-OFF → wrap True (G14).
- [x] T-legacy: fixture with `wrap_width_mm` 0 / 120 and a bound tag → flags per D4, render rects identical to base except the AC1 scale.
- [x] T-roundtrip: to_dict/from_dict, explode, undo preserve both flags (sparse keys).
- [ ] Full suite green (VC6) -- **waived by the user at Phase 6 (2026-11-02)**; coupled keep-green
  runs only (T38 + the smoke-fix round). Goldens re-captured only in the L96 commit.
- [x] Smoke: PipeLabel + RoomTag at true size; toggles on all three surfaces; precision override on a PipeLabel attribute.

## Existing Code Context

- `text_item.py` `_apply_format` (sizing paths), `_box_rect_local`, `_commit_box_size` / `apply_grip`, `to_dict` / `from_dict`.
- `paper_space.py` pt helpers and `_text_panel_properties`; `paper_commands.ResizeTextBoxCommand` (4-tuple state).
- `sketch_adapters._TextBoxAdapter` (D59 cx cy w h writes).
- `block_attributes.normalise_attr` / `format_value` / `hugged_text_record`; `element_params.HostValue` (carries `sm`).
- `scale_manager.ScaleManager` formatters and `to_dict` / `from_dict`.
- Tests that move with D1: listed in the run's 1b findings (`test_manip_griphandle_note_parity`, `test_sketch_adapters`, `test_sb3_paper`, `test_sb3_parity`, `test_sb3_pixel_lock`).

## Edge Cases & Error Handling

- Shrink on empty text: content height of one line; `hide_empty` bound text still drops its slot (system-blocks §6a) before sizing.
- Rotated / keep-upright text: the shrink offset is in the item's local frame, so rotation carries it.
- Shrink + Wrap ON with one word longer than the wrap width: Qt overflows the line; width = that line's natural width (the box grows to contain it rather than clipping).
- `with_overrides` on a unit outside the length family (hydraulic kind): unit ignored, precision applied.
