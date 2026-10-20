---
status: proposal          # designed 2026-10-20, unbuilt; flips to current at the HF3 Account
last-verified: 2026-10-20
verified-commit: ea4172ec
applies-to:
  - firepro3d/filled_region.py
  - firepro3d/curve_chain.py
source-tasks: [HF3 (todo_open.md, Hatch & Fill slices)]
---

# HF3 -- FilledRegion primitive + Select-objects creation -- Design

> **Rule A.** The *what* (D-A1..D-A26) lives in `docs/specs/hatch-and-fill.md`; the concept
> *how* (HD1..HD8) in `2026-10-01-hatch-and-fill-concept-design.md`; the two-layer fill record
> in `2026-10-18-up1-two-layer-fill-design.md` (`fill_layers.py`). This doc owns only the HF3
> build design: where it departs from HD2/HD3 it says so and the concept doc gets a pointer.

## Goal

A **Filled Region** is the 10th 2D primitive: a selectable, static-boundary area object that
fills space which is *not one closed shape* -- the space between a symbol's outline and its
inner curves, a ring, a shape bounded by several curves. In v1 it is created from a selection
("Select objects"), lives only inside Block definitions, is styled with the same two-layer fill
as closed shapes, moves with the modify tools and explodes back to its boundary curves.

## Motivation

Block symbols need filled interiors (the first real use: symbol interiors in block symbols --
Phase 2 ruling). UP1 gave closed shapes their own fill; everything that is not one shape has no
fill today. HF3 lays the primitive that HF4 (Pick point) and HF5 (Fill Types) build on, and
retires the last H9 dead hatch code.

## Ratified rulings (do not re-ask)

Phase 1b / Phase 2 (2026-10-19/20, AskUserQuestion), all on the user-visible axis:

- **R1** Block Editor only -- Paper has no 2D-geometry layer, so the Paper half of D-A2 and the
  D-A13 "copy/paste Block Editor <-> Paper" clause are **not applicable** in HF3 (spec amendment,
  not a build).
- **R2** First use: symbol interiors in block symbols.
- **R3** Boundary pipeline for Select objects: **chain closure** (endpoint matching), not the
  HD3 arrangement (that stays HF4's region finder for Pick point).
- **R4** Several closed loops in one selection -> **one region**, OddEven nesting (loop 0 outer,
  the rest islands).
- **R5** A failed Fill reports **why** in the status bar; nothing is created.
- **R6** Explode of a region reaches the user through the **existing Explode button** (and the
  context-menu Explode).
- **R7** Guards: G9a placed-instance pixels, G9b round-trips, G9c D-A13 tool matrix (the concept
  doc's G9 Migration is obsolete -- D-A16 reversed).
- **R8** Creation: **select first -> click Fill**, immediate (no mode, no second click).
- **R9** A new region starts **Solid Automatic** (`token:auto`, opacity 1.0), pattern None.
- **R10** Source curves are **kept, unchanged** after Fill; the region holds static copies (D-A1).
- **R11** Outline default Invisible; switching it on paints the **default stroke style**.
- **R12** After Fill the **new region only** is selected.
- **R13** The property panel shows the **shape rows** (Colour defaults to None); Display Manager
  category **"2D Geometry"**.
- **R14** Delete the two H9 dead functions (`wall.WallSegment._draw_hatch`,
  `annotations._rebuild_path_from_elements`).
- **R15** A Fill selection containing a region or a Text item: those are **silently ignored**
  as boundary candidates (D-A5); the Block Editor never fills a region into another region.

Phase 3 (2026-10-20, AskUserQuestion + section approvals S1..S5):

- **D1 Boundary model = loops of primitive records** (approach B). *Because* every shape class
  already owns `to_dict`/`from_dict`, the `manip_*` transform hooks, snap points and
  `halo_scene_path`; HD2's custom `{seg: ...}` schema would duplicate all of it (the reuse-sweep
  failure mode). Rejected: A (HD2 seg schema), C (flattened polylines -- loses curves, D-A1).
- **D2 Home = `filled_region.py` + `curve_chain.py`.** *Because* `geometry_2d.py` is already the
  largest module, and the loop-closure helper is pure geometry Join can adopt later.
- **D3..D7** Sections 1..5 below approved as presented.

## Architecture & Constraints

- Containment C1/C8 unchanged: regions exist only in Block-Editor scenes (and so in block
  definitions); the plan-scene loader clean-drops them like other loose geometry.
- One fill system: the region's style is a `fill_layers.FillLayers` record, painted by
  `hatch_render.paint_fill` through the mixin helper `_paint_fill_layers` -- no new renderer.
- Dual serialization invariant (2d-geometry.md section 6): file (`scene_io`/`to_dict`) and undo
  (`_capture_network`) write the same record.
- Geometry in mm, scene coordinates; the region sits at scene pos (0,0) like the shapes.
- `curve_chain.py` is pure (Qt geometry types only, no scene access).

## Design

### 1. Model: `FilledRegionItem` (`filled_region.py`)

**Class.** `FilledRegionItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem)`, type
key `"draw_filled_region"`, registered in `block_definition._PRIMITIVE_FACTORY` and the
`stroke_style` type table. `_REFERENCE_CAPABLE = False` (like text): no Reference form.

**Boundary = pieces.** `self._loops: list[list[item]]` -- each loop an ordered list of
*parentless, scene-less* shape objects (`LineItem`, `ArcItem`, `PolylineItem`, `SplineItem`,
`EllipseItem`, `CircleItem`, ...) built by `_PRIMITIVE_FACTORY[rec["type"]].from_dict(rec)`.
They are never added to a scene or a scene list, so selection, snap and the Display Manager
never see them as items -- the region exposes them. Loop 0 is the outer loop (largest |area| at
creation), the rest islands. `_rebuild_path()` concatenates each piece's path in chain order
(a piece reversed via `QPainterPath.toReversed()` when its start does not meet the previous
end), closes each loop, `Qt.FillRule.OddEvenFill`.

**Record** (file, undo and clipboard all write this):

```json
{"type": "draw_filled_region",
 "loops": [[<shape record>, <shape record>, ...], ...],
 "fill": <fill_layers.to_record(...)>,
 "outline": false,
 "color": "...", "lineweight": 0.0, "style": {...}, "layer": "..."}
```

`fill` is omitted when empty (UP1 rule); `outline` true = the stroke is drawn with the normal
`Geometry2DMixin` stroke fields. **Supersedes HD2's** `loops[].seg` schema, `fill_type` /
`overrides` (HF5 adds `fill_type` *beside* `fill`), `origin` (the pattern origin is the path's
bounding-rect origin per paint, as for shape fill) and `order` (draw order is z, section 4).

**Style.** `fill_layers` reused as-is; a new region starts
`FillLayers(background=BackgroundLayer("token:auto", 1.0))` (R9). `self.outline = False` by
default (R11); the stroke record exists from creation with the default stroke style, so flipping
`outline` on paints it with no further choice. Paint = region path with the stroke pen (or
`Qt.PenStyle.NoPen`) + `_paint_fill_layers`. `get_closed_path()` returns the OddEven path so
`block_definition._fill_ops` and `halo.halo_is_area` work unchanged; `is_fillable()` is True;
`_draws_fill` is inherited.

**Hit area.** `shape()` = the filled path (interior counts), so click-inside selects; priority
is z (section 4).

### 2. Creation: the Fill button + `curve_chain.py`

**Entry point (R8).** A `Fill` small button in the Block Editor ribbon beside the shape tools;
not a mode -- it fires like Explode in `main.py` (`_build_modify_group`'s explode button pattern:
`scene_getter().fill_selected_items()`). Enabled only when the selection holds at least one
boundary-capable shape (`_refresh_modify_buttons` gets a `"Fill"` branch). Tooltip: *"Fill --
make a Filled Region from the selected closed outline(s)"*. Block Editor tab only (R1);
`scene_role != "block_editor"` returns with no action, like `explode_selected_blocks`.

**`ModelSpace.fill_selected_items()`** (`model_space.py`, beside `explode_selected_blocks`):

1. Candidates = selected items of the eight shape classes that are not `reference`-flagged
   (D-A5); regions, text, block instances, hidden items are dropped silently (R15).
2. `curve_chain.close_loops(pieces, tol=CHAIN_WELD_MM)` -> `ChainResult(loops, reason)`.
3. Failure -> `_show_status(reason, 4000)`; nothing created, selection unchanged (R5).
4. Success -> `FilledRegionItem.from_pieces(loops)` (pieces copied through
   `to_dict`/`from_dict` so the region's copies are static -- D-A1; sources untouched -- R10),
   added to the scene + `_filled_regions`, `push_undo_state()`, selection = the new region
   only (R12), status *"Filled Region created (N loops)"*.

**`curve_chain.py`** -- pure, no scene access:

- Input: shape objects. A piece with `is_closed()` True (circle, ellipse, rectangle, polygon,
  closed polyline/spline) is one loop by itself; an open piece (line, arc, open polyline/spline)
  contributes its two endpoints, read as `path.pointAtPercent(0)` / `(1)` of the piece's
  scene path -- one rule for every class, no per-class endpoint API.
- Chaining: Join's greedy head/tail matching (`scene_tools.join_selected_items`) generalised to
  **many loops** -- start a chain from any unused open piece, extend at either end while an
  unused endpoint lies within `CHAIN_WELD_MM = 1.0` (D-A6; new in `constants.py`; Join's own
  literal `TOL = 1.0` is left alone, follow-up filed); a chain whose two free ends meet within
  tolerance closes into a loop; repeat until no open pieces remain.
- Failure reasons (one status string each, R5): *"Not enclosed -- N curve(s) have an open end"*
  (leftover pieces); *"Not enclosed -- gap of X mm at (x, y)"* when the best unmatched pair is
  within 10x tolerance; *"Select closed shapes or curves that form a closed outline"* when no
  candidate survived step 1.
- Output loops sorted by |area| descending (outer first); piece direction is resolved at path
  build (section 1), so the helper only orders pieces.
- A selection whose pieces cross (an X of two lines) fails with the open-end reason -- crossings
  are HF4's arrangement, not HF3's (R3).

### 3. Registry membership (the "10th primitive" checklist)

Found by grepping the spline primitive's footprint (`_draw_splines`, `SplineItem`,
`"draw_spline"` across `firepro3d/` and `main.py`); the region threads the same seams.

| Seam | HF3 adds |
|---|---|
| Scene list | `ModelSpace._filled_regions`; class->list map entry; `to_dict` key `"filled_regions"`; `clear()`; the from-dict loader; `_add_from_dict` table `"draw_filled_region": (FilledRegionItem, "_filled_regions")`; `scene_io.py` reset; `scene_tools._all_geometry_items`; `display_manager` "2D Geometry" collector (2 sites, R13); `schematic_scene` list map; `constraint_controller._PRIMITIVE_LISTS` (rigid body only: no handles, no adapter -- listed so it moves with a group) |
| Factory | `_PRIMITIVE_FACTORY["draw_filled_region"]`; `stroke_style` type table; `block_snap_geometry` reaches it through the factory |
| Containment | C1/C8 unchanged: the plan-scene loader clean-drops the `filled_regions` key; `fill_selected_items` is `block_editor`-only |
| Undo | `_capture_network` / `_restore_network` carry the list (same record as file) |
| Clipboard | `paste_items` type dispatch via `_add_from_dict`; the ghost ctor reuses the region path; paste into a plan scene refused like other 2D geometry |
| Block compile | `_compile` generic branch: `_fill_ops` (via `get_closed_path`) emits FILL/PATTERN, then a STROKE op only when `outline` is on |
| HALO | `halo_scene_path` = the region path; `halo_is_area` True (D-A26 "traces the boundary") |
| Snap | `snap_engine._collect`: a `FilledRegionItem` branch returns `self._collect(piece)` for every piece of every loop -- snappable with the outline Invisible (D-A26) |
| Panel | Protocol-driven (`get_properties`/`set_property`, `is_fillable()` True): the shape rows appear (R13), one extra **Outline** toggle row, no Reference toggle |
| Paper display | `paper_display._category_for_item` -> "2D Geometry"; viewports render regions through placed instances only |
| Modify tools | section 4 |
| Cursors / modes | none -- Fill is a button |

Not touched: `tool_geometry` (refusals, section 4), `view_3d`, `geometry_import` /
`dxf_import_worker` (HF6).

### 4. Modify tools (D-A13), pick priority, Explode

**Transforms by delegation.** The manipulator discovers capability by hook presence
(`selection_manipulator.item_capabilities`; `bake_translate` prefers `manip_translate` >
`translate` > `moveBy`). `FilledRegionItem` implements `translate`, `manip_rotate`,
`manip_reflect`, `manip_scale_about` -- and whichever scale hook name the capability probe reads
(`manip_scale` vs `manip_scale_about`: the plan's first step pins it from the eight shapes, P4)
-- each forwarding to every piece's same-named hook, then `_rebuild_path()`. The fill pattern
never rotates/mirrors/scales by construction: `paint_fill` draws in the scene frame with the
origin from the path's bounding rect, as for shape fill (D-A13). `manip_handles()` returns `[]`
(no grips in v1); `manip_capabilities()` returns `{"translate", "rotate", "scale"}` so the
manipulator frame still shows.

**Refused tools.** Offset / Trim / Extend / Break / Fillet filter candidates by `isinstance`
against the shape classes (`tool_geometry._is_closed_shape`, `offset_signed_dist`, the pickers),
so a region is already not a candidate. HF3 adds one status line (*"Filled Regions can't be
offset / trimmed / ..."*) only at the refusal seams that are silent today -- the plan greps each
tool's "nothing eligible" branch. G9c asserts region unchanged + status text present.

**Pick priority + draw order (D-A7, D-A26).** `Z_FILLED_REGION = -1` in `constants.py`
(between `Z_BELOW_GEOMETRY` and the shapes' default z 0 -- probed: no `setZValue` in
`geometry_2d.py`). The region paints under every shape; `itemAt` returns the topmost, so a click
on a line crossing the region picks the line, a click in the open interior picks the region.
The runtime elevation z pass is plan-scene only. Manual draw order deferred (D-A7).

**Explode (R6).** `explode_selected_blocks` handles both: regions in the selection become their
pieces -- each piece `to_dict()` -> `_add_from_dict` (new live shapes; `copy_style` from the
region's stroke record, so an Invisible region explodes to default-stroke curves, no fill) --
the region removed, one undo step together with any block explode, results selected. Button
enable: `has_block or has_region`; context-menu Explode (`entity_context_menu.on_explode`)
gets the same gate.

### 5. Dead code, guards, spec amendments

**H9 (R14):** delete `wall.WallSegment._draw_hatch` and `annotations._rebuild_path_from_elements`
(both re-confirmed caller-less 2026-10-20); VC5 greps `tests/` for both names first.

**Guards** (VC3 -- real path, observable ground truth; each shown RED with its change reverted),
`tests/test_filled_region.py` + `tests/test_curve_chain.py`:

| Guard | Scenario -> ground truth |
|---|---|
| **G9a Placed-instance pixels** | Block Editor scene: rect outline + inner circle selected -> `fill_selected_items()` -> save block -> place in a plan scene -> render (`_render_scene` from `test_geo2d_fill_render.py`): pixel between rect and circle = fill colour, circle centre = background (island), rect edge = stroke (sources untouched); the editor scene renders the region under the lines. |
| **G9b Round-trips** | region with 2 loops, Solid + outline on: `to_dict` -> fresh scene `from_dict`; `_capture_network` -> `_restore_network`; copy -> `paste_items`: loops piece-by-piece equal (type + geometry), `fill` and `outline` equal; plan-scene loader drops `filled_regions` with no item. |
| **G9c D-A13 tool matrix** | Move/Rotate/Mirror/Scale through the manipulator path move every piece and the fill pixel; Offset/Trim/Extend/Break/Fillet leave it unchanged + status; Explode yields len(pieces) live shapes of the piece classes, region gone, one undo step restores it. |
| **Chain** | `close_loops`: 4 lines, 0.5 mm gap -> 1 loop; 1.5 mm gap -> "gap of 1.5 mm"; circle + 4 lines -> 2 loops, outer first; crossing X -> open-end reason; text only -> "Select closed shapes...". |
| **Creation UX** | region + text + lines selected -> region from the lines only; after Fill `selectedItems() == [region]`; failed Fill leaves selection and item count unchanged; non-editor scene -> no-op. |
| **Snap / HALO / pick** | `_collect(region)` yields the pieces' endpoints with outline off; `halo_is_area(region)` True; `itemAt` on a crossing line returns the line, interior returns the region. |
| **Panel** | selected region: shape rows + Outline row, no Reference toggle; toggling Outline changes a boundary pixel. |
| **Dead code** | `WallSegment` has no `_draw_hatch`; `annotations` has no `_rebuild_path_from_elements`. |

**Spec amendments (Phase 6 Account, in place -- Rule A):** `hatch-and-fill.md` (D-A13 Paper
clause N/A; HD2 superseded pointer; HF3 shipped note); concept doc HD2/HD3 amendment note (record
= loops of primitive records; Select objects = chain closure; arrangement stays HF4);
`2d-geometry.md` section 1 table 10th row, section 6 `filled_regions` key, section 7 category;
`scene-io.md` (key); `scene-tools.md` (Fill + Explode); `snapping-engine.md` (region branch);
`SPEC-INDEX.md` adds `filled_region.py`, `curve_chain.py` under hatch-and-fill.

**Follow-ups to file:** Join adopts `curve_chain` / `CHAIN_WELD_MM`; HF4 Pick point (unchanged);
HF5 `fill_type` beside `fill`; manual draw order for regions (D-A7 deferred).

## Acceptance Criteria

- [ ] R1..R15 and D1..D2 hold in the shipped build.
- [ ] Fill on a rect + inner circle in the Block Editor yields one region with an island, Solid
      Automatic, outline off, selected alone; the sources are unchanged.
- [ ] The region survives file, undo and clipboard round-trips (G9b) and renders in placed
      instances (G9a).
- [ ] D-A13 tool matrix (G9c) passes; no grips; z below shapes; lines win the pick.
- [ ] Explode button / context menu explode a region to its pieces in one undo step.
- [ ] Snap and HALO read the boundary with the outline Invisible.
- [ ] H9 functions deleted; full suite green (VC6).

## Verification Checklist

- [ ] Every guard in section 5 shown RED with its change reverted (`shared/red-proof.ps1`).
- [ ] Keep-green set (VC5): `tests/test_block_explode.py`, `tests/test_geo2d_fill_render.py`,
      `tests/test_up1_fill_layers.py`, `tests/test_hatch_*.py`, the snap / HALO / clipboard /
      undo tests found by grepping `_draw_splines` and `SplineItem` in `tests/`.
- [ ] Smoke (Phase 6): draw a symbol outline + inner curve in the Block Editor, select, Fill,
      save, place; Explode it; Move/Rotate it; toggle Outline in the panel.
- [ ] Account: amendments listed in section 5 applied and stamped.

## Existing Code Context

- `geometry_2d.py` -- the eight shape classes, `Geometry2DMixin` (`fill_layers`,
  `_paint_fill_layers`, `_draws_fill`, `get_closed_path`, `manip_*`, `translate`).
- `fill_layers.py` -- the record and defaults (UP1).
- `block_definition.py` -- `_PRIMITIVE_FACTORY`, `_fill_ops`, `_compile`.
- `scene_tools.py` -- `join_selected_items` (chaining precedent), `explode_selected_items`
  (shape explode precedent), `_all_geometry_items`.
- `model_space.py` -- `explode_selected_blocks`, `_add_from_dict`, `paste_items`,
  `_capture_network`, class->list map, `to_dict`/from-dict loader.
- `selection_manipulator.py` -- `item_capabilities`, `bake_translate`.
- `snap_engine.py` -- `_collect`; `halo.py` -- `halo_scene_path`, `halo_is_area`.
- `main.py` -- `_build_modify_group` (Explode button pattern), `_refresh_modify_buttons`,
  the fill swatch rows (`_fillable_targets`).
- `tests/test_geo2d_fill_render.py` (`_render_scene`), `tests/test_block_explode.py`.

## Edge Cases & Error Handling

- Pieces that cross (not meeting at ends) -> open-end failure (R3).
- Duplicate piece selected twice (two coincident lines) -> both chain; the loop closes with one
  and the other is an open end -> failure with the open-end reason.
- A closed piece plus open pieces that do not close -> failure (no partial region).
- Region in the selection of a later Fill -> ignored (R15); Fill with nothing eligible ->
  candidate-less reason.
- Outline on + stroke colour None -> the category colour, as for shapes.
- Loading a record whose piece record has an unknown type -> that piece skipped, one load
  warning; a loop left with no pieces is dropped.

## Performance & Security

Chaining is O(n^2) over the selected pieces (n is a hand-made selection, tens of items); no
spatial index needed. Region paint cost = one `paint_fill` per region, as for a shape fill.
