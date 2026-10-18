---
status: proposal          # designed 2026-10-18 (UP1 /todo run, Phase 3); unbuilt. Consolidating contract for the shape-fill change across ui-design-system D6, 2d-geometry 1.1, hatch-and-fill (H8, data path, adapters) and property-panel (row types) -- those specs get one-line pointers here at Account (Rule A).
last-verified: 2026-10-18
verified-commit: 16e26485
applies-to:
  - firepro3d/fill_layers.py           # NEW: FillLayers / BackgroundLayer / PatternLayer, record read (new + legacy) / write
  - firepro3d/geometry_2d.py           # Geometry2DMixin fill state, _draws_fill, paint, rows, set_property, to/from dict
  - firepro3d/displayable_item.py      # draw_fill retired (draw_section_hatch stays)
  - firepro3d/hatch_render.py          # fill preview helper (promoted from display_manager._make_fill_icon)
  - firepro3d/block_definition.py      # _fill_ops: background FILL op + PATTERN op with scale
  - firepro3d/block_registry.py        # prim_refs pattern ref via fill_layers
  - firepro3d/hatch_patterns.py        # _fill_ref / project_pattern_refs via fill_layers
  - firepro3d/colour_picker.py         # ColourPickerDialog mode= ; pick_fill
  - firepro3d/ui_kit.py                # FillSwatch
  - firepro3d/property_manager.py      # "fill" row type
  - firepro3d/display_manager.py       # _make_fill_icon callers -> shared helper
  - firepro3d/halo.py                  # area test (reads _draws_fill; unchanged code path)
source-tasks: [UP1 (todo_open.md), unified-picker design run 2026-10-18 R1-R12, UP1 Phase 2 R13-R15]
---

# UP1 -- Picker fill mode + two-layer shape fill -- Design

## Goal

Every closed 2D shape carries a two-layer fill -- a **background** (solid colour | none) and a
**pattern** (tile | none), each with its own colour and opacity, the pattern also with a scale --
edited through two property swatches, **Fill** and **Fill Pattern**, that open the house colour
picker in a fill mode. Old files look exactly as before.

## Motivation

Today a shape has one fill that is either solid or hatch, a hatch is drawn at the solid opacity
with no way to change it (hatch-and-fill H8), and fill editing is split across an enum, a pattern
combo, a colour row and a solid-only opacity string. The unified-picker design run (R1-R12)
reversed D-A16 (shapes keep their own fill) and settled the two-layer model (the D-A12 model used
by Filled Regions) edited in one picker. UP2 then routes the remaining picker sites to it.

## Ratified rulings (do not re-ask)

R1-R12 are recorded on the UP1 line in `todo_open.md` and in `hatch-and-fill.md` (D-A16 reversal
note) / `ui-design-system.md` D6 (amendment). Phase 2 (2026-10-18, AskUserQuestion):

- **R13** A Graphic Override / instance `fill` colour recolours **both** layers; each layer keeps
  its own opacity.
- **R14** The interior pick area (shape / HALO) exists when **any** fill layer is set; a shape
  with neither layer picks on its edge only.
- **R15** Shapes persist only as block primitives (`.fpd` never holds loose 2D geometry,
  containment C8), so legacy load targets primitive `fill` records -- settled by D1 below.

Phase 3 (2026-10-18, AskUserQuestion + section approvals):

- **D1** Storage: one layer module with **read-time normalisation** (approach A). No file
  marker, no `SAVE_VERSION` bump. *Because* one reader covers every place a fill record enters
  (`.fpdb`, project-bundled definitions, shipped system blocks, undo snapshots) with no migration
  wiring per load site. Accepted cost: an older FirePro3D build opening a re-saved file shows no
  fill (it reads `type` absent as none; it does not crash).
- **D2** A newly enabled pattern layer starts with colour **Automatic** (`token:auto`, HF1).
  *Because* it then matches the shape's default stroke and follows the theme.
- **D3** The fill-mode controls sit **below** the colour rows, above the footer. *Because* the
  colour picker then looks identical in every mode down to the Recent row.
- **D4** Section 1 (model, render, load) and section 2 (picker, swatches, panel, compatibility)
  approved as presented below.

## Architecture & Constraints

- One fact, one home: the fill record shape, its legacy reading and the defaults live in
  `fill_layers.py`; no other module parses a `fill` dict.
- Geometry in mm; opacity stored as a fraction 0..1 per layer (today's `fill_opacity` unit), shown
  as a percentage in the picker.
- Rendering stays on the one renderer entry point `hatch_render.paint_fill` (it already paints a
  background and a tile in one call, each honouring its own QColor alpha -- probed 2026-10-18).
- Colours are HF1 values: `#rrggbb`, `token:*`, resolved per paint (`resolve_colour`).
- Picker result contract (HF1) is unchanged for `mode="colour"`.

## Design

### 1. Model, render, load (approved)

**`fill_layers.py` (new).**

| Name | Shape |
|---|---|
| `BackgroundLayer` | frozen dataclass `color: str`, `opacity: float = 1.0` |
| `PatternLayer` | frozen dataclass `ref: str`, `color: str = "token:auto"`, `opacity: float = 1.0`, `scale: float = 1.0` |
| `FillLayers` | frozen dataclass `background: BackgroundLayer \| None = None`, `pattern: PatternLayer \| None = None`; `is_empty` |
| `NO_LAYER` | sentinel returned by the picker for "layer off" |
| `to_record(layers) -> dict \| None` | `{"background": {"color", "opacity"}, "pattern": {"ref", "color", "opacity", "scale"}}`, an absent layer's key omitted; `None` when empty (the caller then writes no `fill` key) |
| `from_record(rec) -> FillLayers` | new shape as above; **legacy** shape (has a `type` key): `solid` -> background, `hatch` -> pattern, `none` -> empty; legacy `color` missing/None -> `#888888`, legacy `color` `""` (HF1 No Fill) -> empty (the item path never drew it), legacy `opacity` missing -> 0.45, `pattern` through `canonical_ref`; legacy pattern colour = the legacy `color`, scale 1.0 (R11 same-look); a non-dict or malformed record -> empty (never raises) |
| `pattern_ref(rec) -> str \| None` | the canonical pattern ref of a record (either shape), for the reference collectors |

New layers created by the UI start at opacity 1.0 (R10); loaded layers keep their stored opacity.

**Shape state.** `Geometry2DMixin.fill_layers: FillLayers` replaces `fill_type`, `fill_pattern`
and `fill_opacity`. `_display_fill_color` is no longer the shape's own colour: on 2D geometry it is
a display-only slot written only by paper monochrome mode (`paper_display`), never serialized.
`_geom2d_to_dict` writes `d["fill"] = to_record(...)` when non-empty; `_geom2d_from_dict` reads
`from_record(data.get("fill"))`.

**Effective colour (both layers, R13).** Graphic Override `fill` if set, else
`_display_fill_color` if set, else the layer's own colour. A `""` (No Fill) effective value hides
both layers.

**`_draws_fill` (R14).** True iff not `reference`, the layers are non-empty, and the override
effective value is not `""`. It still gates paint, `shape()` (interior united into the stroke) and
`halo.halo_is_area` (which already calls `_draws_fill`).

**Paint.** One mixin helper replaces the seven `draw_fill(...)` call sites: a single
`paint_fill(painter, closed_path, scene=..., background=<bg colour with bg alpha or None>,
tile_ref=<pattern ref or None>, colour=<pattern colour with pattern alpha>, scale=<pattern scale>,
to_scene=self.sceneTransform())`. `displayable_item.draw_fill` is retired; `draw_section_hatch`
stays.

**Block compile.** `block_definition._fill_ops` reads `from_record(prim.get("fill"))` and emits a
`FILL` op for the background, then a `PATTERN` op carrying `tile_ref`, `colour`, `alpha` and
`scale` (both ops share the clip and container origin as today). `BlockInstance._paint_fill_op`
already honours `op.scale` and `op.alpha`.

**Reference collectors.** `block_registry.prim_refs`, `hatch_patterns._fill_ref` and
`hatch_patterns.project_pattern_refs` take the ref from `fill_layers.pattern_ref` /
`fill_layers.pattern.ref`.

### 2. Picker, swatches, panel, compatibility (approved)

**Picker modes.** `ColourPickerDialog(..., mode="colour" | "fill" | "pattern")`:

- `"colour"` -- today's dialog, unchanged (stroke, text, line and every existing caller, R5).
- `"fill"` -- adds the Fill block with **Opacity** (percent stepper, 0-100). The Standard row's
  No Fill chip means "background off".
- `"pattern"` -- adds the Fill block with a **Pattern** row (None chip, then preview tiles for
  `tile_choices` entries, then "More..." opening the rest), **Opacity** and **Scale** (positive
  number). The No Fill colour chip is hidden; the Pattern row's None chip means "pattern off".

The block sits below the Recent row, above the footer (D3). Entry point
`pick_fill(initial: BackgroundLayer | PatternLayer | None, parent=None, *, pattern: bool,
context="") -> layer | NO_LAYER | None` (None = cancel). Recents still record the colour only.

**One preview helper.** `display_manager._make_fill_icon` moves to `hatch_render` with a
`background` parameter (default the old `#2b2b2b`) and serves the picker Pattern row, the swatch
chip and the Display Manager.

**`ui_kit.FillSwatch`.** Reuses `_Chip`; the chip paints the background colour, or the pattern
preview for a pattern layer, or the shared No-Fill glyph; emits `layerChanged(object)` (a layer or
`NO_LAYER`) after `pick_fill`.

**Panel rows (R6/R8).** Every fillable, non-reference shape always shows **Fill**
(`type: "fill"`, `pattern: False`) and **Fill Pattern** (`type: "fill"`, `pattern: True`),
defaulting to none. `property_manager` gains row type `"fill"` building a `FillSwatch` and writing
back through the existing `_apply_property` (undo macro unchanged). The `Fill` enum, `Pattern`,
`Fill Colour` and `Fill Opacity` rows retire (closes H8). Multi-selection follows the panel's
existing rule for `"color"` rows -- the plan's first step probes that rule (P4) before relying on it.

**Compatibility shim (removed by UP2).** `set_property("Fill", "none" | "solid" | "hatch")` and
`set_property("Pattern", ref)` keep their meaning, mapped onto the layers (`none` clears both,
`solid` enables the background keeping any colour, `hatch` enables the pattern), so
`entity_context_menu` and `Model_View` fill submenus keep working until UP2 reroutes them. Graphic
Override writes `_display_overrides` and is unaffected.

## Acceptance Criteria

- [ ] AC1 Picker fill mode: `"pattern"` shows Pattern row (None + tiles + More...), Opacity,
      Scale; `"fill"` shows Opacity only; `"colour"` shows neither (R4/R5/R9).
- [ ] AC2 Every closed non-reference shape shows Fill + Fill Pattern swatches, default none; the
      old four fill rows are gone (R6/R8, H8).
- [ ] AC3 Two-layer model rendered by one `paint_fill` call, each layer at its own opacity, pattern
      at its scale; block instances render the same through the compiled ops (R3/R9).
- [ ] AC4 New layers start at 100 % opacity; loaded opacity kept (R10).
- [ ] AC5 Legacy `solid` / `hatch` records load and render identically (R11, D1).
- [ ] AC6 Override colour recolours both layers (R13); pick area per R14.
- [ ] AC7 Context-menu fill entries still work through the shim until UP2.

## Verification Checklist (guards, VC3)

- G1 Legacy hatch + solid block primitives (real `.fpdb`-shaped dicts) load and render pixels
  identical to a golden rendered at base SHA `16e26485`.
- G2 Picker in pattern mode returns colour + pattern + opacity + scale through a real `FillSwatch`
  click (dialog driven, not called).
- G3 A stroke `Swatch` (mode colour) never shows Pattern / Opacity / Scale.
- G4 A new closed shape paints nothing inside until a layer is picked (pixel sample).
- G5 Override Fill colour recolours both layers (pixel sample on a bg + pattern shape).
- G6 A pattern-only shape picks on its interior through the real HALO pick; a no-fill shape does
  not.
- G7 Undo/redo + copy round-trip preserve both layers (to_dict parity, `test_serializer_parity`).
- G8 A multi-select apply of Fill Pattern writes every target.
- G9 The context-menu "Hatch -> pattern" path turns the pattern layer on (shim).
- Each guard shown RED with its change reverted; keep-green per VC5 (fill tests listed in
  `.todo/up1-1b-findings.md` + a whole-repo grep for every retired symbol: `fill_type`,
  `fill_pattern`, `fill_opacity`, `draw_fill`, `_make_fill_icon`, the four row keys).

## Existing Code Context

- Renderer, adapters and data path: `hatch-and-fill.md` sections 2-3.
- Fill readers today: `geometry_2d._geom2d_to_dict` / `_from_dict`, `block_definition._fill_ops`,
  `block_registry.prim_refs`, `hatch_patterns._fill_ref`, `project_pattern_refs`.
- Display-only writers of `_display_fill_color` on 2D geometry: `paper_display` (monochrome mode
  + snapshot restore). `display_manager._apply_geo2d` never writes it.
- Picker: `colour_picker.ColourPickerDialog` (body, Theme / Standard / Greys / Recent rows,
  footer), `pick_colour`; `ui_kit.Swatch` / `_Chip`; `property_manager` row dispatch.

## Edge Cases & Error Handling

- Unknown / invalid pattern ref: the renderer tone rule (D-A36) applies unchanged.
- Malformed `fill` record: empty layers, never raises (paint must not raise, M5).
- Reference-flagged shapes: no fill rows, no fill paint, no interior pick (RG4), layers kept.
- Pattern scale <= 0 or non-finite: rejected by the picker field; a stored bad value loads as 1.0.

## Out of scope

- Rerouting the context menus, Graphic Override controls and `SectionPatternDialog` (UP2).
- Fill Types (D-A14), By Pattern colour (D-A12 / WM-8) for shapes, Filled Regions (HF3/HF4).
