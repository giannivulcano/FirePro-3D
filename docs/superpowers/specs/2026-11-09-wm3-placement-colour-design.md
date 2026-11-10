---
title: WM3 - placement / nested-record Colour override + Model "Blocks" Colour
date: 2026-11-09
status: approved (Phase 3, 2026-11-09)
governing-spec: docs/specs/linetypes.md (WM-7 / WM-8 / WM-11 / WM-12; section "WM3")
base: b6b66b51
branch: feature/block-colour-override
---

# WM3 - placement Colour override

## Goal

A placed block (plan) and a nested `block_instance` record (Block Editor) carry a
**Colour** override - As Authored | By Category | a colour - that replaces the
colour of everything the block draws (WM-7), and the Display Manager's Model
"Blocks" row gains the Colour that By Category resolves to on canvas.

## Motivation

WM-7 ("colour mirrors weight") was ratified on 2026-10-05; WM2 shipped the Weight
and Linetype halves (2026-10-07). "Existing = grey" (one placement greys a whole
fixture: linework, text, fills, hatches, end blocks, linetype symbols) is the
workflow WM3 delivers. Primitive Colour By Linetype is split to WM3b.

## Settled rulings (ratified - do not re-ask)

- Scope (Phase 1): placement + nested-record Colour and the Model "Blocks" Colour; WM3b split off.
- Spec (2026-10-05): WM-7 replace-all, outer wins, resolved value shown, reaches
  linetype symbols / fills / hatches / text / end blocks; paper B&W / Custom stay
  above the cascade; By Category on sheets = paper "Blocks" colour (also under Full
  Colour); WM-11 Explode bakes the resolved colour (By Category -> the current DM value
  as a concrete colour); WM-12 text + text-box border take the placement Colour.
- Phase 2 FP1: Q1 one enum row + picker; Q2 imported reference linework IS recoloured;
  Q3 Model "Blocks" Colour factory = Automatic; Q4 locked in pattern-tile / linetype-unit
  Block Editors.
- Phase 3 (design approval, 2026-11-09): approach A (internal `token:blocks`);
  perf report-only; fills / hatches under B&W / Custom follow the existing hatch /
  paper rules exactly as an authored fill of that colour does (no new paper rule).

## Architecture & Constraints

### Approaches considered (how By Category resolves)

- **A (chosen): internal colour token `token:blocks`** written onto op colours and
  resolved at paint by `colour_tokens.resolve_colour` (canvas -> Model "Blocks" colour;
  paper -> the paper "Blocks" colour). A DM change is only a repaint; the op memo stays
  stable. Precedent: `token:bg` / `token:element` are internal tokens the picker never offers.
- B: resolve to a concrete colour at apply time - the op memo would key on the DM value
  and be wrong on sheets (different colour).
- C: the paint-time `override` slot (`BlockInstance._display_pen_color`, a stub) - fills
  ignore it (`render_op.paint_fill_op`), and stroke joints compare the compiled op colour
  (`stroke_joints.joinable`, `_op_joint_attrs`), so joins would decide on authored colours.

### D1 Data

- `overrides` = `{"weight", "linetype", "colour"}`; colour = `as_authored` |
  `by_category` | a colour string (`#rrggbb`, `token:auto`, `token:accent`).
- `stroke_style.normalize_overrides` canonicalises colour through
  `colour_tokens.normalize_colour`; non-string / blank / `""` (No Fill) / unknown token
  / garbage -> As Authored. Weight / linetype keywords are not valid colours.
- `is_as_authored` tests all three axes (a colour-only override must save:
  `BlockInstance.to_dict`, `block_definition._load_prim`).
- `override_args` -> `(weight | None, linetype | None, colour | None)`;
  `BlockInstance._ov_args` is None when all three are None. `compose_overrides`
  unchanged (generic per key). `override_refs` unchanged (colours are values, not
  registry names - no in-use / rename / bundling rule).
- Legacy files: the key is omitted while As Authored x3 -> byte-identical round-trip.

### D2 Resolution

- `render_op.apply_overrides(ops, weight=None, linetype=None, colour=None)`: weight /
  linetype keep today's rule (styled strokes only); colour replaces `op.colour` on
  **every** kind - STROKE (styled and imported reference strokes, Q2), TEXT, FILL,
  PATTERN - with `by_category` written as `token:blocks`.
- New `RenderOp.fixed: bool = False`; `block_definition._placeholder_op` sets it; every
  axis of `apply_overrides` skips a fixed op (the red missing-nested placeholder is never
  restyled; today it is indistinguishable from a reference stroke - both `weight=None`,
  `colour=None`).
- Callers unchanged in shape: `_nested_ops` (`*override_args(...)`), `BlockInstance.render_ops`
  memo (args tuple now carries colour), `block_attributes.bound_text_ops` + `BoundPrim.override_args`
  (bound text, text-box fill / border / leader). Joints, end blocks (`end_render` uses
  `pen.color()`), linetype-embedded symbols (`linetype_render.draw_expansion` strokes with
  the op pen) follow from the op colour. Masks, crisp split cache, linetype expansion
  memos are colour-free (no change).

### D3 By Category + paper

- `constants.TOKEN_BLOCKS = "token:blocks"` (internal). `colour_tokens.resolve_colour`:
  canvas -> `resolve_colour(paper_display.model_blocks_colour())` (cached string; may be
  `token:auto`); paper (any colour mode) -> the instance's `_paper_blocks_colour`
  (resolved from the paper "Blocks" category colour by `paper_display._apply_block`,
  joined into the `block_paper` save / restore tuple). `token_label` returns None for it
  (internal, like `token:bg`); no picker offers it.
- Paint precedence unchanged: authored -> placement override (op level) -> constraint
  tint -> selection accent -> paper `_paper_pen_color` (B&W / Custom, strokes + text).
  Fills / hatches follow the existing hatch / paper rules as an authored fill of the
  same colour.

### D4 Panel

- `geometry_2d.stroke_rows(..., placement=True)` adds a **Colour** row after Weight:
  enum options `As Authored`, `By Category (<Swatch label of the Model Blocks colour>)`,
  `Pick colour…`, plus the current picked colour (Swatch label, e.g. "Automatic",
  "#808080") when one is set; per-option swatch icons.
- `property_manager` enum rows gain optional `icons` (option -> colour string) and
  `action_options` (option -> "colour"): choosing `Pick colour…` opens
  `colour_picker.pick_colour` in the panel (never from the item), applies the result as
  the colour string, and a cancel restores the previous selection without a write.
- `BlockInstance._set_override_from_panel` gains a Colour branch (labels -> keywords;
  colour strings via `normalize_colour`); one undo step per pick (`request_undo_push`);
  `_overrides_locked()` gates the row and the setter (Q4); a mixed selection writes only
  targets that own the row (WM2 Q5). `Geometry2DMixin._geom2d_set` ignores the block-only
  labels.

### D5 Display Manager

- Model "Blocks" control on the Line Weights tab gains a colour `Swatch` beside the weight
  combo. Factory `token:auto` (Q3). `paper_display`: `_MODEL_BLOCKS_COLOUR` cache,
  `model_blocks_colour()` / `set_model_blocks_colour()` / `model_blocks_factory_colour()`.
- Storage mirrors the weight: QSettings `display/Blocks/color` + `display/Blocks/default_color`;
  project record `Blocks.color` (`get_display_settings_for_save`), read on open by the
  same path as `_apply_model_blocks_weight` (user default -> project -> QSettings ->
  factory). Cancel restores the snapshot; Reset -> factory; Set as default writes both.
  The tooltip "block colours ... stay authored" is reworded. A change repaints the scene
  (By Category placements redraw).

### D6 Explode (WM-11)

`block_explode._bake` writes the resolved colour (By Category -> the current
`model_blocks_colour()` string) onto: styled primitives' `style["colour"]` (+ pen sync);
text `data.color` (its box border uses the text colour); each fill layer's `color` on
filled primitives (a pattern layer at `token:element` already follows the baked style
colour). As Authored explodes verbatim. Nested children compose per axis (unchanged).

### D7 Not changed

Selection accent, constraint tint and paper colour stay above the override; new
placements As Authored; copy / paste / undo / make-from-selection / Block Editor seed /
`.fpdb` carry the colour through the existing dict and `BlockInstance.place_kwargs`
choke point; primitive By Linetype is WM3b.

## Acceptance Criteria

- AC1 Colour row on BlockInstance + nested record; options per D4; one undo step per pick.
- AC2 A colour -> every stroke, text, fill, hatch, linetype symbol, end block, bound text,
  text-box border / leader, imported linework draws in it (canvas + PDF).
- AC3 By Category -> Model "Blocks" colour on canvas; paper "Blocks" colour on sheets
  (Full Colour included); B&W / Custom above it.
- AC4 Nested: outer non-As-Authored wins; a nested record alone recolours its child.
- AC5 Persistence: `.fpd`, `.fpdb`, undo, paste, Block Editor seed round-trip; legacy
  files pixel-identical.
- AC6 DM Model "Blocks" Colour: factory Automatic; persists (QSettings + project);
  Cancel restores; tooltip reworded; a change repaints By Category placements.
- AC7 Explode bakes the resolved colour (strokes, text, fills) - look unchanged.
- AC8 Row locked in tile / linetype-unit editors.
- AC9 The missing-nested placeholder is never recoloured.

## Verification Checklist (guards, VC3 - real objects, observable output, RED with the change reverted)

- G1 canvas pixels: Sprinkler test block (circle red, cross Automatic, deflector blue,
  a text with box border, a fill, a hatch, an end block, a linetype with a dot symbol)
  with Colour Grey -> sampled pixels grey; As Authored -> authored.
- G2 parsed PDF: same scene on a sheet - Full Colour -> grey ops; B&W -> black.
- G3 By Category: change the DM Model Blocks colour -> placement repaints; on a sheet ->
  paper Blocks colour.
- G4 nested outer-wins pixels.
- G5 persistence round-trips (extend `test_wm2_persistence`).
- G6 explode pixel parity.
- G7 panel: real MainWindow pick -> repaint + one undo step; locked in a tile editor.
- G8 imported reference linework recoloured.
- G9 placeholder never recoloured.
- Perf: report-only colour case in `tests/test_wm2_perf.py` (no bar - same op replace
  WM2 measured at <= 1.1x).
- Contract-retired + rewritten: `tests/test_lt2_model_blocks_row.py` (weight-only row).
