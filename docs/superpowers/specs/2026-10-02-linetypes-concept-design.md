---
status: proposal          # concept ratified 2026-10-02 (grill Q1–Q23 + brainstorm LD-A, LD1–LD7); unbuilt — slices LT1–LT8
last-verified: 2026-10-02
verified-commit: 18df05d
applies-to:
  - firepro3d/geometry_2d.py
  - firepro3d/block_definition.py
  - firepro3d/block_instance.py
  - firepro3d/block_registry.py
  - firepro3d/block_library.py
  - firepro3d/block_editor.py
  - firepro3d/paper_display.py
  - firepro3d/display_manager.py
  - firepro3d/scene_io.py
  - firepro3d/scene_tools.py
  - firepro3d/block_explode.py
  # new: stroke_style.py, path_walk.py, linetype_render.py
source-tasks: ["Concept: user-definable linetypes as blocks — end types, dash-dot spacing + configuration, lineweight at definition vs host level (2026-10-02)"]
---

# Linetypes — Concept Design

> **Rule A.** The *what* — decisions D-L1…D-L23 — is owned by
> [`docs/specs/linetypes.md`](../../specs/linetypes.md) "Design Decisions"
> (with the as-built baseline). This doc owns the *how* and the build slices;
> it cites D-L ids rather than restating them. Promote into `linetypes.md` (and
> the linked specs in its reconciliation list) as each slice lands.

## Goal

Linetypes and end types authored as blocks, applied to 2D primitives through a
single style record and one shared renderer, with a weight/linetype cascade
from definition → use site → nested placements → surface — the foundation for
building gridlines, pipes and leaders from primitives.

## Motivation

See `linetypes.md` Motivation. Headline defects closed on the way: block
linework has no paper weight and is forced cosmetic; three dash vocabularies;
edit tools drop every style field except pen colour/width.

## Architecture & Constraints

- **Containment C1/C9** — linetyped primitives live in block definitions and
  on paper only.
- **Flyweight compile** (`block-system.md` "The flyweight core") — one compiled
  op list per definition; per-placement variation resolves at paint (LD-A).
- **Capabilities, not kinds** — `repeat` / `end` beside hatch's `tile`
  (D-A9, System Blocks F3).
- **Scene unit = 1 mm**; placements carry no scale (`block-system.md`
  Decision 9), so definition-local phase is stable under pose.
- **Gridline dash normalisation** (`grid-system.md §10.1.1`) is the reference
  for printed-mm vs viewport-scale lengths; never Qt pen dash patterns (width
  multiples collapse).
- **One renderer** — loose paper primitives, `BlockInstance` and PDF share
  `linetype_render`; no per-class copies.

## Design Decisions (the how — ratified in the 2026-10-02 brainstorm)

### LD-A — Expansion at paint, shared renderer

Compile keeps strokes unresolved (`StrokeOp`); a shared resolver + expander
runs at paint with a cache. Rejected: expand at compile (breaks the flyweight
per host style/scale); QPen dash patterns (two paths, width-multiple units).

### LD1 — Data model

- **Style record** on every 2D primitive, (de)serialized once in
  `Geometry2DMixin._geom2d_to_dict` / `_geom2d_from_dict` (moves `"lineweight"`
  out of the per-class `to_dict`s):
  `style: {linetype: <block id>|"by_block", weight: <name>|"by_linetype"|"by_block", start: {end: <id>|"by_linetype"|"by_block", visible: bool}, finish: {…}, colour: ColourValue}`.
- **Linetype block:** `BlockDefinition.repeat = {length, size: "drafting"|"model", ends: {start, finish}}`; component weights are the authored
  primitives' named weights inside the unit.
- **End block:** `BlockDefinition.end = {size: "fixed"|"weight_relative", trim}`;
  block origin = attach point, +X = outward line direction.
- **Placement / nested record:** `style: {linetype, weight}` on `BlockInstance`
  and on nested `block_instance` records (nested-blocks D2 gains the slot).
- **`copy_style(src, dst)`** — the one style-preserving copy, used by Explode,
  join, break, trim, fillet, chamfer, offset, the polyline-variant swap and
  clipboard (D-L23b).

### LD2 — Cascade (`stroke_style.py`)

- `resolve_stroke(style, host_chain, surface) -> ResolvedStroke(linetype_def,
  dash_weight_mm, component_weights, start_end, finish_end, colour, warning)`.
- Nested-record styles are static per definition → folded into each
  `StrokeOp` at compile; a residual `by_block` means "outermost placement".
- Top-level `by_block` → surface category (D-L17). Missing references →
  Continuous/Flat + `warning` (D-L23e).

### LD3 — Renderer

- **`path_walk.py`** (GAP): iterate segments of a primitive's drawn path
  (reuse the `halo_trace_path` hook — the existing drawn-geometry source);
  arc-length point/tangent; phase per D-L9/D-L9b — straight: projection on the
  canonical axis (direction folded to [0°,180°)) from the origin's projection;
  arcs/circles from their circle's 0°; ellipse 0°; spline start.
- **`linetype_render.py`**: `expand(path, ResolvedStroke, scale) ->
  ExpandedStroke{dash_path, symbol_ops, end_ops}` — explicit geometry; dots =
  zero-length dashes with round cap; symbol fit-skip (D-L15); end blocks placed
  at each end, stroke trimmed by `end.trim`; weight-relative ends scaled by the
  resolved weight; LOD < 2 px period → continuous (screen only). Cache key =
  (op id, resolved-style hash, scale bucket).
- **Compile:** `BlockDefinition._compile` emits `StrokeOp`s — the stroke half
  of hatch HD4's `RenderOp` (one refactor, whichever slice lands first).
  `BlockInstance.paint` stops forcing cosmetic pens.

### LD4 — Weights and surfaces

- Named-weight table → `.fpd` (`scene_io`); QSettings = new-project template;
  `.fpdb` bundles used weights; project wins, missing added (D-L13). The
  Line Weights tab edits the project table.
- Canvas: width = mm × `constants.UNDERLAY_MM_TO_PX_HINT`, cosmetic; view-level
  **Thin Lines** toggle → 1 px (D-L14). Retire the duplicate
  `_BORDER_WEIGHT_PX` / `frame_group` weight copies onto this mapping.
  *(LT1 BUILT 2026-10-04 — as-built contract in `linetypes.md` "LT1".)*
- Paper/PDF: width = mm ÷ viewport scale. Lengths: Drafting = printed mm
  (× scale inside viewports, gridline normalisation); Model = real mm;
  Drafting in model view falls back to real size until SB1c (D-L3).
- Display Manager: "Blocks" category weight (model + paper);
  `_category_for_item` gains a `BlockInstance` case.

### LD5 — Registry and library

- `block_registry.nested_ids` → `referenced_ids(defn)`: nested records **plus**
  style references (primitive linetype/end ids, `repeat.ends` defaults), so
  `closure`, `bundle_for`, `would_cycle`, `users_of`, `invalidate` follow.
- Pickers filter on capability; capable blocks excluded from symbol placement.
- System series: Linetypes (General: Continuous, Hidden, Center, Phantom, Dot,
  Fire-FP, Sprinkler-S; Piping: Branch, Main, Cross Main, Existing, Drain) and
  End Types (Flat, Round, Square, Arrow, Open Arrow, Arrow 30°, Tick, Dot,
  Slash, Box, None, Grid Bubble).
- Repeat units / end blocks: Continuous strokes only — enforced at authoring
  and at compile (D-L23a).

### LD6 — Authoring

- Block Editor **repeat frame** — one frame widget shared with HF2's tile frame.
- Property panel **Pattern** list (Dash/Gap/Dot rows) rewriting the axis
  segments of the same block; symbols drawn only.
- **End-block mode** — attach-point + +X glyph; Fixed/Weight-relative + trim
  fields.
- Live preview on a sample line + L polyline.
- Ribbon **current Linetype / Weight** pickers (tooltips) feeding new
  primitives (D-L18); panel rows for Linetype, Weight, Start End, Finish End,
  Visible ×2.

### LD7 — Build slices

| Slice | Content | Depends |
|---|---|---|
| LT1 | Project-scoped weights + Blocks category + `_category_for_item` BlockInstance case + canvas px mapping + Thin Lines | — |
| LT2 | Style record + `copy_style` + migration (Continuous/By Block) + format bump + edit-tool preservation | — |
| LT3 | `path_walk` + `linetype_render` (dashes, axis phase, LOD, cache) + StrokeOp compile + non-cosmetic block paint + cascade resolver | LT1, LT2; HF2 RenderOp (or lands it) |
| LT4 | `repeat` capability + authoring (frame, Pattern list, preview) + `referenced_ids` + pickers + ribbon current style | LT3 |
| LT5 | `end` capability + end rendering/trim + per-end override/visible + By Block chain through placements/nested | LT4 |
| LT6 | Embedded symbols + fit-skip + upright text + `@[key]` in end blocks | LT5, SB1 attributes |
| LT7 | System Linetypes / End Types / Piping series | LT6, SB1b |
| LT8 | Perf bench + fixes (bench confirmed with the user first) | LT6 |

LT1 ∥ LT2 independent.

## Acceptance Criteria

- [ ] `linetypes.md` acceptance criteria.
- [ ] One renderer serves loose paper primitives, block placements and PDF.
- [ ] Flyweight compile preserved (one compile per definition).

## Verification Checklist (guards — VC3: real path, observable ground truth)

- **G1 Seam** — two collinear lines (abutting and gapped, opposite draw
  directions) with one linetype → raster along the axis identical to a single
  line (pixel compare).
- **G2 Trim stability** — trim/break a linetyped line → surviving dash raster
  unchanged.
- **G3 Print exact** — Drafting Hidden on paper and in a 1:100 viewport → PDF
  dash lengths = authored mm (±0.05 mm, parsed from the PDF); a Model linetype
  scales with the viewport.
- **G4 Cascade** — block with By Linetype / named / By Block primitives, placed
  with different weights, nested two deep → PDF stroke widths match the
  D-L4/5/6/17 table.
- **G5 Ends** — open line with Arrow (Fixed) and Round (weight-relative) at
  Light and Heavy → arrow length constant mm; round radius = ½ weight; closed
  shape draws none.
- **G6 Symbols** — Fire-FP across a corner / near an end block → no clipped
  glyph (occurrence skipped).
- **G7 End attributes** — grid-bubble end block with `@[Label]` → host label,
  upright when rotated, `?` without a source.
- **G8 Round-trip** — `.fpd` save/load + undo/redo + `.fpdb` bundle (linetype +
  end blocks + weight names) into a project with a conflicting weight →
  project value wins, missing added.
- **G9 Migration** — legacy file → Continuous/By Block; paper PDF stroke widths
  identical to before.
- **G10 Perf** — D-L21 bench (confirmed with the user first).
- **G11 Missing** — deleted linetype → Continuous + badge, never invisible.

**Keep-green (registry/style enumerators, from the 1b sweep):**
`test_block_text_compile`, `test_ellipse_spline_integration`,
`test_spline_periodic` (`_PRIMITIVE_FACTORY`); `test_paper_display`,
`test_gridline_paper_scale`, `test_underlay_display` (weights);
`test_paper_construction_plots` (`_category_for_item`); `test_frame_group`,
`test_text_frame`, `test_text_item` (border types); `test_gridline_render`,
`test_geo2d_ghost_preview`, `test_modify_tools_rotate`,
`test_underlay_integration` (dash); `test_geo2d_display_category`,
`test_reference_line`, `test_design_area` (DM categories);
`test_block_library_bundle` (`nested_ids`/`bundle_for`); the block
`render_ops` and `"lineweight"`-key tests.

## Edge Cases & Error Handling

- Line shorter than one period: the axis rhythm still applies (may read as a
  gap or partial dash); end blocks still draw.
- Zero-length line: no stroke, no ends.
- End blocks longer than the line: both draw, stroke fully trimmed.
- Weight name deleted while in use: refused (existing guard), now per project.
- Cyclic reference via a linetype referencing a block that uses it:
  `would_cycle` over `referenced_ids` refuses it.
- Legacy loose model primitives remain dropped by C8; migration applies to
  block definitions and paper.

## Performance & Security

- D-L21 bar; expansion cache bounded by visible ops; invalidation on definition
  edit via `BlockRegistry.invalidate` + weight-table edits.
- No security surface (local files only).
