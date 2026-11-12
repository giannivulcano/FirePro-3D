---
status: proposal
last-verified: 2026-11-12
verified-commit: 119fbbf0
applies-to:
  - firepro3d/symbol_block.py          # new: SymbolBlockItem
  - firepro3d/sprinkler.py
  - firepro3d/water_supply.py
  - firepro3d/pipe.py                  # _riser_symbol only
  - firepro3d/node.py                  # ring / shape / bounds radius
  - firepro3d/model_space.py           # symbol_block resolver, refresh hook
  - firepro3d/render_op.py             # fill_override, real-size stroke weight
  - firepro3d/stroke_style.py          # numeric (model mm) weight
  - firepro3d/block_definition.py      # symbol_for, numeric weight compile
  - firepro3d/block_properties_info.py # Block Editor "Symbol for" row
  - firepro3d/annotation_choices.py    # eligibility predicate
  - firepro3d/display_manager.py       # _set_svg_tint SymbolBlockItem branch
  - firepro3d/paper_display.py         # symbol paper hooks, riser Pipe row
  - firepro3d/network_codec.py         # sparse symbol_block
  - firepro3d/system_blocks/Symbols/   # five shipped seeds
source-tasks:
  - "SB4g -- Convert sprinkler (3 variants), water-supply and riser symbols to System symbol blocks (real size) [P1] (todo_open.md, System Blocks build)"
---

# SB4g -- Symbol blocks (sprinkler, water supply, riser) -- Design

Design record for the SB4g slice. Once built, the contract moves into
[`system-blocks.md`](../../specs/system-blocks.md) (a new symbol-blocks section),
[`sprinkler-system-components.md`](../../specs/sprinkler-system-components.md) 8 / 10.3,
[`pipe-placement-methodology.md`](../../specs/pipe-placement-methodology.md) 9.1 (riser) and
[`block-system.md`](../../specs/block-system.md) (the `.fpdb` schema: `symbol_for`, numeric
stroke weight). This file is then history. Concept: Q9 composite rule in
[`2026-09-29-system-blocks-concept-design.md`](2026-09-29-system-blocks-concept-design.md).

## Goal

The sprinkler head (three variants), the water supply and the riser pass-through draw
from **System symbol blocks** at real size instead of SVG files. The user edits them in
the Block Editor (Workbench check-out, then Promote, and every element picks the change
up), picks a symbol per head and per water supply, and gets one colour path through
blocks.

## Motivation

End goal (Phase 2, all four ratified): symbols editable in the Block Editor; own symbol
per head; phasing dashes later (D-PH13 via PH4, which needs block paint, not SVG); one
colour path (the riser gains a colour). This is the last fixed graphic of the concept's
Q9 conversion list.

## Architecture & Constraints

- **Composite rule (Q9).** Sprinkler, WaterSupply and the vertical Pipe stay bespoke
  items; only their fixed graphic comes from a block.
- **Not a `BlockInstance`.** A `BlockInstance` is level-scoped, selectable, serialized,
  painted by the Blocks paper row and has a stub DM colour, so it is the wrong item (SB3
  D-A reasoning). The symbol item follows the `BoundLabelItem` precedent: a light
  `QGraphicsItem` that paints a definition's ops.
- **Flyweight.** Every element paints the shared compiled ops of its definition
  (`BlockDefinition.render_ops_variant(False, 1.0)`); nothing is compiled per element.
- **Fittings unchanged (R5).** `riser_through`, `tee_vertical` and `cross_vertical`
  keep drawing `graphics/fitting_symbols/riser_passthrough.svg`; the asset stays.
- **Section / 3D unchanged.** They never read the plan SVG.
- **Selection, snap, z unchanged (AC10).** Sprinkler is not selectable (the Node is
  picked), WaterSupply is, the riser is never a snap target and is pinned above its pipe
  (`Pipe.sync_riser_z`; z-order owned by `view-relationships.md` 7.3).

## Design Decisions

Ratified in Phase 2 / 3 (`AskUserQuestion`, 2026-11-12). R-numbers are the Phase 2
rulings; D-numbers are the design.

| Id | Decision |
|---|---|
| R1 | Faithful conversion: a one-off (unshipped) script turns the five SVGs into block primitives, committed as seeded System `.fpdb` files; each keeps its current look. |
| R2 | Size = the block's real authored size. Seeds are authored at today's sizes (sprinkler 609.6 mm, water supply 609.6 mm, riser 150 mm), so nothing moves. A user symbol draws at its own size; the node's pick area, halo and selection ring follow the symbol's extent. |
| R3 | Choice lives in a per-element **Symbol** row (replaces the sprinkler's "Graphic"); a new head takes the placement template's choice. |
| R4 | The riser draws in its pipe's colour (velocity colour, else pipe Colour, else the DM Pipe row); on paper it takes the Pipe paper row. |
| R5 | Vertical fittings keep the SVG (above). |
| R6 | Saved `Graphic` values (`Sprinkler0/1/2`) are dropped on load: every head loads with the default symbol. |
| R7 | The water supply gets the same Symbol row; the riser is one System block for every vertical pipe, no per-pipe row. |
| R8 | A missing chosen block draws that category's System default, keeps the stored id and logs a warning. |
| R9 | Tint as today: DM row Colour recolours strokes, Fill recolours fills; unset = authored; paper As Authored keeps authored colours with today's token re-tint; paper not-As-Authored = paper Colour / Fill. User symbols are tinted the same way. |
| R10 | The Block Editor gains a **Symbol for** field (Sprinkler / Water Supply / Riser) on real-size blocks; only flagged blocks are listed per category. |
| R11 | Demolition dashing is not in SB4g; the D-PH13 / PH4 lines get a note that SB4g landed. |
| R12 | *Superseded by R13* (named lineweights). |
| R13 | Line widths scale with zoom like today: a new **real-size stroke width** (model mm) beside named lineweights. |
| D1 | Approach A: `SymbolBlockItem` (below). Rejected: B, a child `BlockInstance` (level-scoped, selectable, serialized, wrong paper row, stub DM colour); C, block rendered back to SVG bytes (no path to PH4 dashing). |
| D2 | New definition key `symbol_for`, not `host_category`: annotation pickers read `host_category`, and Riser is not an element category. |

### D3 `SymbolBlockItem` (`firepro3d/symbol_block.py`)

- `SymbolBlockItem(category, owner=None, parent=None)`: a `QGraphicsItem`. It holds the
  resolved definition (re-resolved by `refresh()`), and the tint pair.
- **Paint:** `paint_ops(painter, ops, pose, self, override=<stroke tint>,
  fill_override=<fill tint>)` with `ops = defn.render_ops_variant(False, 1.0)` and an
  identity pose. It carries the item protocol `paint_ops` reads (`_paper_pen_width`,
  `_paper_pen_color`, `_paper_scale`, `_is_ghost`, `_crisp_ops`, `_pose_rot`), as
  `BoundLabelItem` does.
- **Bounds / shape:** the union of the ops' paths (plus half the widest real-size
  stroke), through one helper promoted out of `BlockInstance`'s bounds / shape code
  (GENERALIZE; `BlockInstance` calls the same helper). Cached; `refresh()` drops it.
- `extent_radius()`: half the larger side of the bounds, the one size the Node ring /
  shape and the riser's hit disk read.
- `set_tint(stroke, fill)`: stores `_display_color` / `_display_fill_color` (the
  attributes `_set_svg_tint` and paper snapshot code already read), resolves tokens, and
  repaints. A stroke of `#ffffff` or None means authored (today's rule).
- No definition at all (System default also missing): paints nothing, empty bounds.
- `Sprinkler` and `WaterSupply` subclass it (class names kept, so paper
  `_category_for_item`, DM lists, selection flags and z stay). Their SVG loading,
  `GRAPHICS`, `SVG_NATURAL_PX`, `SCALE` and centring code are removed; the block origin
  is the element's origin (seeds are authored centred on (0, 0)).
- `Pipe._riser_symbol` is a plain `SymbolBlockItem("Riser")`: same `RISER_SYMBOL_TAG`
  data, no mouse / hover, `setPos` at the node XY (origin-centred, no half-size offset),
  same show / hide rule and `sync_riser_z`. The vertical pipe's hit disk radius is the
  symbol's `extent_radius()`.

### D4 Resolver `Model_Space.symbol_block(category, chosen_id=None)`

1. `chosen_id`, when given and resolvable through `ensure_system_block(chosen_id,
   accept=eligible)`, wins.
2. Otherwise `SYMBOL_DEFAULTS[category]` (new, in `system_blocks.py`: Sprinkler ->
   `system-symbols-sprinkler0`, Water Supply -> `system-symbols-watersupply`, Riser ->
   `system-symbols-riser`).
3. A chosen id that missed logs one warning and one status notice per
   `(category, id)` (the `_annot_notified` pattern); the id stays on the element.
4. `eligible_symbol(defn, category)`: `scale_mode == "real_size"` and
   `symbol_for == category`. System seeds carry their `symbol_for`.
5. Memoised with the annotation memo; cleared on `blockDefinitionsChanged`.

### D5 Real-size stroke width (R13)

- A stroke style's `weight` may be a **number** (model mm, > 0) besides a named weight
  or keyword. `stroke_style.is_real_weight(w)`; `is_named_weight` stays False for it.
- **Canvas:** `paint_ops` draws it with a non-cosmetic pen, width = w x the pose's
  scale, so it scales with zoom (the crisp cosmetic path is skipped for it).
- **Paper:** non-cosmetic width w in scene mm; the viewport transform plots it at
  w / scale, as today's SVG strokes do. B&W / Custom colour forcing applies as for any
  stroke.
- **Block Editor:** the weight row gains a "Real size..." entry that takes an mm value
  (units per `units-and-formatting.md`); the panel shows it as its length.
- **Persistence / Explode:** `.fpdb` stores the number; Explode keeps it on the
  exploded item; a reader that predates it never sees one (only new seeds use it).
- Converted seeds use it at today's real widths (for example sprinkler0's ring about
  29.8 mm, the riser about 11 mm).

### D6 Data and persistence

- `Sprinkler.symbol_block` / `WaterSupply.symbol_block`: a block id or None (= System
  default). Written sparse: `"symbol_block"` inside the node's `sprinkler` record and on
  the water-supply record, only when not None. The legacy `"Graphic"` property is not in
  `_properties` any more; a file's `Graphic` value is ignored (R6), no error.
- Copy / paste, undo (rebuild from serialization) and the placement template carry it
  (template copy goes through the same property / record path as today's `Graphic`).

### D7 Symbol row and Block Editor field

- **Symbol row** on sprinkler and water supply, in the slot of today's "Graphic": the
  `TagBlockHost._tag_row` pattern. Options = the System symbols of that category, then
  user-library blocks passing `eligible_symbol`, through `annotation_choices.choices`
  generalized to take an eligibility predicate (one disk walk / parse cache). A kept
  missing id is listed "(missing)", an ineligible one "(not eligible)". Picking sets
  `symbol_block` (one undo step) and refreshes the item.
- **Block Editor:** `block_properties_info` gains **Symbol for** (none / Sprinkler /
  Water Supply / Riser), shown when Scale mode is Real size. `BlockDefinition.symbol_for`
  (`""` = none) is written only when set; it round-trips through `.fpdb` and `.fpd`.

### D8 Refresh, tint and paper

- `Model_Space.refresh_annotation_tags` also refreshes every sprinkler, water supply and
  riser symbol item, so a System edit, Reload or Promote repaints every element (AC5).
- `display_manager._set_svg_tint` gets a first branch: a `SymbolBlockItem` calls
  `set_tint(color, fill_color)` and returns. All 11 call sites (DM apply, snapshot
  restore, paper, fitting, pipe network controller) carry over unchanged.
- `render_op.paint_ops` gains `fill_override` (fill ops take it instead of
  `op.colour`; `paint_fill_op` takes the colour as a parameter).
- **Paper:** the `(Sprinkler, WaterSupply)` branch keeps its tint rules and also sets
  `_paper_scale` and `_paper_pen_width` (the two lines `_apply_block` sets, without its
  colour forcing); `restore_model_display` resets them. The riser symbol is tinted with
  the Pipe paper row colour in the pipe branch and restored with the pipe.
- **Canvas riser colour (R4):** `Pipe` re-tints its riser symbol wherever its display
  colour is applied (velocity colour, pipe Colour, DM Pipe row).
- `node.py` ring / shape / bounds read `sprinkler.extent_radius()` (x 1.15 ring,
  max with `Node.RADIUS` for the shape, x 0.95 halo as today) instead of `TARGET_MM`.

### D9 Seeds and conversion

- Folder `firepro3d/system_blocks/Symbols/`: `Sprinkler0.fpdb`, `Sprinkler1.fpdb`,
  `Sprinkler2.fpdb`, `Water Supply.fpdb`, `Riser.fpdb`; ids `system-symbols-sprinkler0`,
  `-sprinkler1`, `-sprinkler2`, `-watersupply`, `-riser`; Library System, Series
  Symbols, Scale mode Real size, `symbol_for` set, version 1.
- A one-off script (kept out of the shipped tree) reproduces today's scene geometry
  exactly: the same map the SVG item applies now (its scale -- `Sprinkler.SCALE` /
  `WaterSupply` scale / the riser's `_RISER_SIZE_MM / natural` -- and its centring
  offset), so every point lands where it draws today, centred on (0, 0), Y flipped:
  `circle` -> `draw_circle`; straight `path` segments -> `draw_line`; cubic Bezier runs
  -> `draw_spline` with explicit clamped knots (exact); filled Bezier shapes ->
  `draw_filled_region` with spline pieces; empty paths dropped (three in sprinkler2).
  Stroke widths -> D5 real-size weights; colours -> the SVG's literal colours (white
  strokes, `#2e2e2e` / black / white fills).

## Acceptance Criteria

- [ ] AC1 Five System symbol blocks ship in `system_blocks/Symbols/`, real size, converted faithfully; on-screen look matches today at every zoom (sizes 609.6 / 609.6 / 150 mm, line widths scale with zoom).
- [ ] AC2 Sprinkler, WaterSupply and the riser draw from blocks (no `QGraphicsSvgItem` for them); riser show / hide rules unchanged; fittings unchanged.
- [ ] AC3 Symbol row on sprinkler and water supply lists System + flagged user symbols for that category; the choice is saved per element; the placement template carries it; copy / paste and undo keep it.
- [ ] AC4 Block Editor "Symbol for" field is authored, saved in `.fpdb`, and filters the lists.
- [ ] AC5 Editing a System symbol (Workbench check-out -> Promote) changes every element using it.
- [ ] AC6 A user symbol draws at its authored size; Node bounds / shape / halo / ring follow the symbol extent; the riser hit disk follows the riser block extent.
- [ ] AC7 DM and paper tint per R9 for sprinkler / water supply; riser per R4; As Authored behaves as today.
- [ ] AC8 Old `Graphic` values are dropped on load -> default symbol; no load error.
- [ ] AC9 Missing chosen block -> System default drawn, id kept, warning logged.
- [ ] AC10 Snap / selection / z behaviour unchanged.
- [ ] AC11 A real-size stroke width scales with zoom on canvas and plots at width / scale on paper; named weights are unchanged.

## Verification Checklist

Guards (VC3: real scene, shown view, real DM / paper paths; each RED with its change reverted):

- [ ] G1 per symbol: paint a shown view -> symbol pixels at the element, extent equals the authored real size within tolerance, item is not an SVG item.
- [ ] G2 Symbol row: the shown Properties panel lists System + a flagged user symbol, excludes unflagged and annotative blocks; picking changes the drawn ops; save / load and undo round-trip.
- [ ] G3 a 300 mm user symbol draws 300 mm; node `shape()` / `boundingRect()` follow it.
- [ ] G4 DM tint: Sprinkler row Colour / Fill change sampled stroke / fill pixels; unset -> authored; paper As Authored unchanged; the riser takes the pipe's velocity colour.
- [ ] G5 legacy load: a file whose head has `Graphic: "Sprinkler2"` loads with the default symbol, no exception.
- [ ] G6 a missing block id -> default drawn + warning logged, id kept.
- [ ] G7 System edit propagation: changing the System definition's ops repaints the element with the new ops.
- [ ] G8 riser visibility / z / snap-exclusion suite stays green (rewritten to the block item).
- [ ] G9 real-size stroke: the stroke's pixel width doubles when the zoom doubles; a named-weight stroke's does not; on paper it plots at width / scale.
- [ ] `tests/test_system_blocks_conformance.py` covers the five new files (ids, Library, version, loads).
- [ ] Coupled tests rewritten (list: `.todo/sb4g-1b-report.md` "Tests to rewrite"; re-grep at plan time per VC5).
- [ ] Full suite green (VC6); launch smoke of the app.

## Existing Code Context

Verified at `119fbbf0` (Phase 1b report + Phase 3 probes):

- `BlockDefinition.render_ops_variant(mirrored, scale)`; `_compile` builds stroke ops with
  `weight=st["weight"]` (a string today).
- `render_op.paint_ops(painter, ops, pose, item, *, override, selected, tint, end_ops,
  ends)`: canvas strokes cosmetic at `canvas_px(weight)`; paper non-cosmetic
  `paper_op_width`; `paint_fill_op` colours from `op.colour` only.
- `Model_Space.ensure_system_block(block_id, accept=None)` (embeds outside undo);
  `_on_block_definitions_changed` -> `refresh_annotation_tags`.
- `display_manager._set_svg_tint(item, color, fill_color)` and its call sites listed in D8.
- `paper_display._apply_block` (pen width / paper scale lines), the
  `(Sprinkler, WaterSupply)` paper branch, `_svg_paper_retint`, `_category_for_item`.
- `Pipe` riser block: `QGraphicsSvgItem(_RISER_SVG)`, `RISER_SYMBOL_TAG`, `_RISER_SIZE_MM`,
  `sync_riser_z`, the vertical hit disk.
- `node.py` ring / shape / halo from `Sprinkler.TARGET_MM * _display_scale`.
- `network_codec.sprinkler_props` (writes `get_properties()` values; carries `Graphic`
  today); sparse-id precedent: pipe `tag_block`.
- `TagBlockHost._tag_row` + `annotation_choices.choices(sc, category, current=)`.
- `block_properties_info` "Host category" row (the place for "Symbol for").
- Primitives: `CircleItem`, `LineItem`, `SplineItem` (explicit knots, degree, closed),
  `FilledRegion` pieces accept `draw_spline`.

## Edge Cases & Error Handling

- System default missing too (a broken install): the item paints nothing, bounds empty,
  one log line; the Node falls back to `Node.RADIUS` for its shape.
- A chosen block later edited to a different `symbol_for` or to Annotative: treated as
  missing (R8) at the next resolve.
- `_display_scale` (DM scale column retired, always 1.0): no longer read for symbol size.
- A riser symbol of a pipe that is not in a scene: no resolve until it is added.

## Performance

Symbol items paint shared compiled ops (no per-element compile); resolution is memoised.
A project with thousands of heads paints one cached ops list per variant, as placed
blocks do today.
