---
status: proposal          # designed 2026-11-06, unbuilt
last-verified: 2026-11-06
verified-commit: 22db85b3
applies-to:
  - firepro3d/dxf_fills.py          # new: HATCH / SOLID readers
  - firepro3d/underlay_runs.py      # new: overlap-aware paint-order runs
  - firepro3d/import_fills.py       # new: fill record -> Block Editor items + report
  - firepro3d/hatch_tile.py         # new: line families -> rectangular tile
  - firepro3d/dxf_import_worker.py
  - firepro3d/underlay_import_dialog.py
  - firepro3d/dwg_converter.py
  - firepro3d/underlay_controller.py
  - firepro3d/underlay_freeze.py
  - firepro3d/underlay_snap_index.py
  - firepro3d/underlay_cache.py
  - firepro3d/geometry_2d.py        # draw_z record key only
  - firepro3d/block_definition.py   # compile order only
  - firepro3d/block_editor.py       # import path only
source-tasks: [HF7, "DXF HATCH imports nothing"]
---

# HF7 DXF fills and the shared import-fill foundation: Design Spec

The consolidating contract for this change. `hatch-and-fill.md`, `underlay-workflow.md`,
`block-system.md` and `reference-graphic-model.md` link here (Rule A). The *what* stays
D-A7, D-A21, D-A22 and D-A23 in `hatch-and-fill.md`; HD7 in the concept doc is superseded
by this file where they differ (see "Changes to the concept").

## Goal

A DXF or DWG imported as an underlay shows its filled areas and pattern hatches, in the
source's paint order. The same file imported into the Block Editor gives editable Filled
Regions on named Fill Types, with pattern hatches converted to reusable pattern blocks
where a tile exists. HF6 then only has to read PDFs into the same record.

## Motivation

- DXF HATCH imports nothing and SOLID imports as a bowtie outline, so walls, furniture and
  sprinkler symbols lose their poche.
- Build order was re-ruled on 2026-11-06: HF7 first, carrying the foundation HF6 would
  have built (underlay fill, paint-order runs and cache bump, Filled Region import).
- A shipped bug blocks import: a Filled Region draws under lines in the Block Editor but
  paints over them in a placed block, because commit groups primitives by type
  (`schematic_scene._PRIMITIVE_LISTS`). Probe: compiled order `stroke, fill`.

## Architecture & Constraints

- Workers stay Qt-free in spirit: the extraction output is plain JSON-safe dicts, because
  the underlay cache round-trips them.
- Underlays stay batched. One `QGraphicsItem` per geometry is the failure mode the batch
  builder exists to prevent (`underlay-workflow.md`).
- Filled Regions exist only in the Block Editor (HF3 R1). Underlays never create one.
- Underlay colour is per layer, never per entity (D-A21 HF1 scope note).
- The Fill Type table is outside undo (HF5 R9).

## Design Decisions

### D1 Fill record

One record per source area:

```python
{"kind": "fill", "layer": str, "color": str,   # color: source colour (D-A21 mapping)
 "solid": bool,                                # paints a filled area
 "mask": bool,                                 # source is pure white
 "tone": bool,                                 # pattern over the line cap
 "loops": [[child_geom, ...], ...],            # existing geom kinds
 "lines": [[x1, y1, x2, y2], ...],             # generated pattern lines
 "pattern": {"name": str, "families": [...]}}  # None for solid fills
```

- A new `kind` over flags on `path_points`: flags cannot express holes or carry family
  data, and HF6 needs the same shape.
- `dwg_converter.geom_children(g)` returns a record's boundary child geoms, and `[]` for
  every other kind. Consumers that need bounds or points recurse through it.
- **List position is paint order.** There is no `order` key. HF6 sorts its output by
  `seqno` before returning it.
- A family is `{"angle", "base", "offset", "dashes"}` in the record's own coordinates.
  `apply_import_transform` and the paper-layout transform move loops, lines and families
  together (scale, rotate, Y already negated). Scene-space angles are what `hatch_tile`
  reads.

### D2 Extraction

- `dxf_fills.py` holds `read_solid(entity, layer, color)` and
  `read_hatch(entity, layer, color, *, exact)`.
- SOLID reads `entity.wcs_vertices()`, which already gives the 0-1-3-2 order. A SOLID is
  one closed `path_points` child tagged `"straight": True`, so the axis picker keeps its
  edges.
- HATCH runs `upright()` first when `extrusion.z < 0`. The composite-branch comment says
  `upright()` corrupts composites; probed on ezdxf 1.4.2, it flips a mirrored INSERT's
  virtual HATCH correctly, and only HATCH joins this path.
- Boundaries: `exact=True` (Block Editor, `_preserve_curves`) gives line, arc and spline
  children. `exact=False` flattens each loop to one `path_points` child.
- Flatten tolerance is relative: loop bounding-box diagonal / 2000. A fixed 0.5 unit is
  wrong for drawings in inches.
- Loops flagged text box are dropped. Style 2 (ignore) keeps only external loops; styles 0
  and 1 keep every other loop, painted by nesting depth. As-proposed until the plan's first
  probe confirms the path flags on real hatches.
- Pattern lines come from `hatching.hatch_entity(h, jiggle_origin=False)`, read through
  `itertools.islice` at `HATCH_IMPORT_MAX_LINES` (20,000, `constants.py`). Reaching the
  limit, or `DenseHatchingLinesError`, sets `tone` and clears `lines`.
- Draw order: `dxf_fills.in_draw_order(layout)` wraps `reorder.ascending` with the layout's
  `get_redraw_order()`. It replaces the plain `msp` walk in `DxfImportWorker.run`,
  `extract_file_sync`, the dialog's extract loop and `extract_layout_entities`. INSERT
  explosion passes `redraw_order=True`. The redraw order is consumed once: it is a
  generator.
- `_CACHE_VERSION` goes to 6.

### D3 Underlay render

- `underlay_runs.assign_runs(geoms) -> list[int]`. For each fill in stream order: its run
  is one above the highest earlier overlapping stroke, and level with an earlier
  overlapping fill on the same layer, one above on another layer. Every later overlapping
  stroke is raised to at least that run. Overlap is by bounding box, with numpy.
- Rejected: one run per fill-to-stroke alternation (A/B on SIMBA: 4-5 ms to 11-16 ms, over
  the bar), and per-layer runs (a mask stops masking across layers).
- Measured on real streams: SIMBA 6 runs and 80 path items (788 without overlap test),
  Ground Floor 7 runs and 155 items (590 without), assignment 87 ms and 2.1 s.
- Revisit for HF6: assignment is O(fills x geoms). If a PDF page has tens of thousands of
  fills, it needs a spatial index.
- `_build_batched_underlay_group` emits, per run: fill items, then the existing stroke and
  text items. Items keep `setData(1, layer)`, so hide and repen keep working. Same-z
  siblings in a group paint in insertion order (probed).
- Each fill batch is one path per (run, layer, class), with class one of `solid`, `tone`,
  `mask`. Loops are oriented by nesting depth (odd depth reversed) and the path uses
  `WindingFill`: an even-odd batch would cancel where two fills overlap (probed).
- Pattern lines batch with the layer's strokes in the same run.
- `tone` batches use `HATCH_LOD_TONE` as item opacity, so repen's solid brush does not
  lose it. `mask` batches use `TOKEN_BG` and repen skips them; a data slot marks them.
  The slot map is owned by `underlay-workflow.md`.
- `reference_from_geoms` keeps the records. `_reference_items` skips `fill` as an
  unsupported kind.
- `UnderlaySnapIndex` expands each fill into `geom_children` on construction, so
  `snap_engine` and `axis_picker` see plain boundaries, and `lines` never reach snap.
- Import preview: fills in the row's pen colour at `HATCH_LOD_TONE` opacity, with pattern
  lines in the stroke path. The preview does not honour run order.
- `_show_geom_type_dialog` labels the kind "Filled areas".

### D4 Block Editor import

- `import_fills.build_items(geoms, *, lineweight, project_scene) -> (items, skipped, report)`
  walks geoms in order. `BlockEditorWidget._add_imported_geoms` calls it only when a fill
  is present; otherwise today's path runs unchanged.
- Solid fill: `FilledRegionItem` on `Imported Solid` (`ensure_named`, background
  `token:auto`), outline off, a background colour override when the source colour is not
  Automatic.
- Convertible pattern: region on `<NAME> (imported)` (`ensure_look`, pattern colour
  `token:auto`, scale 1), with colour and Scale as overrides. Background off.
- A hatch with `solid` false and no pattern record is skipped and counted.
- `mask` fills in the Block Editor are ordinary regions in `#ffffff`.
- Unconvertible pattern: pattern lines as `LineItem`s plus each boundary loop as a closed
  shape, boundary only above `HATCH_IMPORT_MAX_EDIT_LINES` (2,000, `constants.py`).
- `tone` patterns take the boundary-only branch and are reported.
- The report is a list of (pattern name, count, outcome). Empty: the status line only.
  Otherwise one `themed_info` after import lists each row.
- `fill_types.notify_changed()` fires once at the end if the table changed.

### D5 Source order in blocks

- `Geometry2DMixin` gains a sparse record key `draw_z` (float). Absent means today's
  default. `from_dict` applies it with `setZValue`.
- When an import holds a fill, every imported primitive gets
  `draw_z = -0.9 + 0.8 * (i + 1) / (n + 1)`, inside the free band between
  `Z_FILLED_REGION` (-1) and the shape default (0). `n` is the number of imported items.
- `_compile` walks non-nested primitives in a stable sort on `draw_z`, defaulting to -1
  for a region and 0 otherwise. This fixes the placed-block bug for authored regions.
- A definition with no region and no `draw_z` keeps its exact list order. Records stay
  byte-identical, because the key is sparse.

### D6 Tile conversion

`hatch_tile.convert(families) -> Tile | None`, pure and Qt-free.

- Each family's translations are `m * offset + n * L * u`, where `u` is the line direction
  and `L` the dash period (an undashed family slides freely along `u`).
- For each family, find the smallest positive x and y translation in that group. A family
  running along an axis puts no constraint on it.
- `W` and `H` are the least common multiples, within a drift of 0.1 % of the finest
  spacing per tile, capped at 64 x the finest spacing. No common multiple under the cap
  means `None`.
- Tile content: each family's dashes clipped to the `W x H` cell, as `draw_line` records.
  A zero-length dash becomes a short line of 1 % of the finest spacing. More than
  `HATCH_TILE_MAX_SEGMENTS` (500, `constants.py`) means `None`.
- `row_shift` stays 0. Tile `size` is `"model"`.
- Probed on ezdxf's own definitions: ANSI31, ANSI31 at 28.28 degrees, ANSI32, ANSI37,
  ANGLE, AR-B816, NET3, GRATE, BRICK, HEX and AR-HBONE convert; GRATE at 151.72 degrees and
  AR-CONC do not.

### D7 Dedupe and grouping

- `Tile.key` hashes content normalised to the finest spacing, rounded to 1e-4. Angle is
  part of the content, so rotated copies stay separate (D-A10).
- Lookup hashes every project definition with a tile in library `Imported`. A later import
  therefore finds an earlier block, and a block the user edited stops matching.
- A new shape commits a block named `<NAME> (imported)` with library `Imported`, series
  `Patterns`, through `commit_block_definition(capability=("tile", tile),
  place_instance=False)`.
- `commit_block_definition` pushes one undo state on the project scene. Whether undoing
  that step can strand a region's pattern reference is the plan's first probe; if it can,
  the block is added without the undo push.
- The first hatch of a shape sets scale 1. Later hatches store `finest spacing / block
  spacing` as a Scale override on the region.
- Anonymous patterns (`_USER`, empty name) use the name `Hatch`.
- Name collisions go through `free_name` / `ensure_look`.

### Changes to the concept (user approved 2026-11-06)

- HD7's rational-slope test (|p|, |q| <= 8) is replaced by D6: the test is stricter than a
  tile needs. Ground Floor: 14 of 98 patterned hatches stay lines, instead of 16.
- D-A11's stored per-region pattern origin stays unbuilt, and sharing a block across
  scales needs phase dropped. **Pattern phase is not preserved in the Block Editor**: angle,
  spacing and scale are exact, position relative to the boundary is not.
- HD7's `order` key on geom dicts is replaced by list position.

### Deferred (filed at wrap-up)

- WIPEOUT import: 7 in Ground Floor's blocks, ignored today.
- The D-A25 PDF bar stays with HF6.

## Acceptance Criteria

- [ ] AC1 SOLID imports filled, no bowtie, for triangles and quads.
- [ ] AC2 Underlay solid HATCH fills with holes on line, arc, ellipse, spline and bulge
      boundaries, and through mirrored and rotated INSERTs.
- [ ] AC3 Underlay pattern HATCH draws clipped lines, dashes included; over 20,000 lines
      draws a 35 % tone.
- [ ] AC4 Underlay fills take the layer colour; pure white paints the canvas background;
      Display Manager colour, opacity and layer hide apply.
- [ ] AC5 Underlay keeps source paint order including the draw-order table; cached
      underlays re-extract.
- [ ] AC6 Hatch boundaries and SOLID corners snap, pattern lines do not, the Mirror axis
      picker still accepts SOLID edges.
- [ ] AC7 The import preview shows fills and pattern lines; crop, paper-layout and rotated
      imports carry fills correctly.
- [ ] AC8 Block Editor: SOLID and solid HATCH become regions on Imported Solid with a
      colour override, outline off.
- [ ] AC9 Block Editor: convertible patterns become a region, a project-only pattern block
      and an "(imported)" type, one per shape, Scale on the region, rotated copies
      separate.
- [ ] AC10 Unconvertible patterns become lines plus a boundary shape, boundary only over
      2,000 lines; a dialog appears only when something did not convert.
- [ ] AC11 Authored regions sit behind lines, imported items keep source order, the editor
      and placed blocks match.
- [ ] AC12 Settle redraw stays within 1.5x of base on both real drawings. Build time is
      reported.
- [ ] AC13 A block with imported fills survives a library round trip into a fresh project;
      an import is one undo step in the editor.

## Verification Checklist

Each guard drives the real path on a DXF fixture written with ezdxf and is shown RED with
its change reverted.

- **Ring and bowtie:** extract, build the underlay group, render to an image: filled in the
  ring, empty in the hole; the SOLID's centre is filled.
- **Overlapping fills:** two overlapping rings in one layer: the overlap pixel is filled.
- **Paint order:** fill over a line, line over a fill, a fill on layer B over a line on
  layer A, and a draw-order table that reverses entity order: sampled pixels follow source
  order.
- **Mirrored INSERT:** a mirrored block's hatch: pixel inside the expected world position.
- **Boundary kinds:** arc, ellipse, spline and bulge loops: area within 1 % of analytic.
- **Run count:** a scene with N separate fill-then-line pairs compiles to one run.
- **Tone and mask:** a dense hatch gives a tone item and no lines; repen keeps opacity and
  does not recolour a mask.
- **Snap:** a query returns boundary points and no pattern-line endpoint; the axis picker
  takes a SOLID edge.
- **Transforms:** crop, rotated import and paper-layout paths move loops, lines and
  families.
- **Tile (G11):** for ANSI31, ANSI37, BRICK, HEX and NET3, stamped tile segments match
  `hatch_entity` lines over the same area modulo a single translation; AR-CONC returns
  None.
- **Regions (G11):** a fixture with SOLID, solid HATCH and two scales of ANSI31 gives the
  expected region records, one pattern block and one type, Scale ratio on the second.
- **Order in blocks:** an authored region and a line, and an imported SOLID over a line:
  placed-instance pixels match the editor's.
- **Parity:** a block with no regions compiles to the same op list as base.
- **Round trip (G7):** save to library, load in a fresh project: type and pattern arrive.
- **Report:** a GRATE-at-28-degrees hatch gives lines, a closed boundary and a report row;
  a clean import shows no dialog.
- **Perf:** interleaved base/HEAD pairs on SIMBA and Ground Floor, fit and zoom views, raw
  lines in a file, each bench asserting its fill count > 0. Bars: 9.3 ms; 215 ms fit,
  126 ms zoomed. The base was measured with the QImage render bench at 1920 x 1080 on
  22db85b3.

## Edge Cases & Error Handling

- A loop with fewer than 3 usable points is dropped; a hatch with no loops is skipped and
  counted, never raised.
- A malformed HATCH follows the extractor's existing per-entity `except`, which counts it
  skipped.
- A hidden layer's fills still take part in run assignment. Harmless.
- A cropped underlay keeps a whole fill if any boundary point is inside, the same rule as
  polylines.
- Undoing an import leaves the pattern block and Fill Type in the project. A later import
  reuses them.
