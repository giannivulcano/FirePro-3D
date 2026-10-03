---
status: partial           # HF2 built 2026-10-03 (HD4/HD4a); HF1, HF3–HF9 unbuilt. Concept ratified 2026-10-01 (grill Q1–Q27 + brainstorm sections 1–6). HD4a "Built-ins + alias" code table superseded by D-A39 (blocks only) — as-built lives in specs/hatch-and-fill.md §1–§3
last-verified: 2026-10-03  # HF2 Account (status + supersession note only; design text left as approved)
verified-commit: 53e1773
applies-to:
  - firepro3d/hatch_patterns.py
  - firepro3d/hatch_render.py       # HF2
  - firepro3d/render_op.py          # HF2
  - firepro3d/tile_frame.py         # HF2
  - firepro3d/displayable_item.py
  - firepro3d/geometry_2d.py
  - firepro3d/block_definition.py
  - firepro3d/block_instance.py
  - firepro3d/block_editor.py
  - firepro3d/colour_picker.py
  - firepro3d/theme.py
  - firepro3d/display_manager.py
  - firepro3d/paper_display.py
  - firepro3d/pdf_import_worker.py
  - firepro3d/dxf_import_worker.py
  - firepro3d/underlay_controller.py
  # new: colour_value.py, region_finder.py, fill_types.py (+ filled_region.py if split from geometry_2d)
source-tasks: ["Concept: region Fill/Hatch tool + user-definable hatch patterns as blocks + theme-Automatic colours (2026-10-01)"]
---

# Hatch & Fill — Concept Design

> **Rule A.** The *what* — decisions D-A1…D-A27 — is owned by
> [`docs/specs/hatch-and-fill.md`](../../specs/hatch-and-fill.md) "Design
> Decisions" (with the as-built record and divergences H1–H12). This doc owns
> the *how* and the build slices; it cites D-A ids rather than restating them.
> Promote into `hatch-and-fill.md` (and the linked specs listed there) as each
> slice lands.

## Goal

Let a user fill any enclosed area — bounded by any mix of lines, arcs, splines
and shape edges, with islands — in the Block Editor or on a sheet, using
hatch patterns they author as blocks, styled through named Fill Types, in
colours that can follow the theme ("Automatic"). Imported PDF/DXF fills arrive
as real fills, not line soup.

## Motivation

- Fill today is a property of one closed shape only and is **lost** on every
  placed block (H1) — so no saved project can show a fill outside the editor.
- Hatch patterns are hard-coded, can't scale (H2), and one of four draws
  nothing (H3).
- Imported drawings lose all fills: PDF fills become outlines (multi-piece
  fills a zig-zag), DXF HATCH imports nothing.
- New 2D linework is hard-coded white — wrong on a light theme and on paper.

## Architecture & Constraints

- **Containment C1** — regions live in Block definitions and on Paper only (D-A2).
- **System Blocks F3** — no kind field; pattern-ness is the `tile` capability (D-A9).
- **Scene unit = 1 mm**; geometry in mm; hatch scale is world-unit (Model) or
  printed mm (Drafting).
- **Y-up vs Qt** — the region finder consumes *drawn* geometry
  (`halo.halo_scene_path`) so it never reads `ArcItem` start/span angles (the
  open arc-angle-convention bug).
- **One fill system** — per-item fill is dissolved (D-A16); section-cut hatch
  routes through Fill Types (D-A17). No parallel vocabularies.

## Design Decisions (the how — ratified in the 2026-10-01 brainstorm, sections 1–6)

### HD1 — Units

| Unit | Job | Home |
|---|---|---|
| ColourValue + resolver | `"#rrggbb"` \| `"token:auto"` \| `"token:accent"`; `resolve_colour(value, surface)` | new `colour_value.py` |
| Pattern tile | optional `BlockDefinition.tile = {w, h, row_shift, size: "model"\|"drafting"}` | `block_definition.py` |
| Pattern renderer | world-unit tiled drawing of a tile block clipped to a path | `hatch_patterns.py` (rewritten) |
| FilledRegion | 10th 2D primitive | `geometry_2d.py` (or `filled_region.py`) |
| Region finder | edges → arrangement → face at click, with islands | new `region_finder.py` |
| Fill Types | project table + `.fpdb` bundling | new `fill_types.py` |

### HD2 — FilledRegion is the 10th 2D primitive

It joins the existing primitive registries (block compile, Explode, clipboard
`paste_items` type dispatch, paper display, HALO, snap collectors, both
serialization paths — `scene_io`/block primitives and `_capture_network`
undo), so D-A2's two containers come for free. Serialized shape:

```json
{"type": "draw_filled_region",
 "loops": [[{"seg": "line", "p": [[x,y],[x,y]]},
            {"seg": "arc", "c": [x,y], "r": r, "a0": deg, "span": deg},
            {"seg": "spline", "degree": 3, "ctrl": [...], "knots": [...]}], ...],
 "fill_type": "<uuid>", "overrides": {...},
 "outline": {"style": "invisible" | {...}},
 "origin": [x, y], "order": n}
```

Loop 0 is the outer boundary; further loops are islands; rendered with
OddEven fill. Arc angles in the file are **Y-up** (model convention) via
`arc_math.yup_angle`. Modify-tool behaviour per D-A13; the pattern origin
translates with the region but the pattern frame never rotates/mirrors/scales.

### HD3 — Region finder (Pick point; Select objects)

1. **Candidates** — D-A5 set, spatially pre-filtered to a window around the
   click (window doubles until a bounded face is found or the container bounds
   are hit).
2. **Edges** — `halo_scene_path(item)` flattened at ≤ 0.1 mm sagitta; each
   segment tagged `(source item, t0, t1)`.
3. **Arrangement** — split at all crossings (grid-bucketed), weld endpoints
   ≤ 1 mm (D-A6), half-edge graph.
4. **Face** — the bounded face containing the click; its inner cycles are the
   islands (D-A4). None → "Not enclosed".
5. **Rebuild** — merge consecutive same-source pieces into exact curves (line,
   arc exact; spline sub-split at t; ellipse arc → spline); fallback dense
   polyline ≤ 0.2 mm.

Select objects runs 2–5 on the chosen items only (largest face, or the face at
a click). Hover caches steps 2–3 per tool session, invalidated on container
change, so a mouse move costs only 4–5 (D-A25 bar). Rejected: raster
flood-fill (fails 0.2 mm, loses curves); QPainterPath boolean tricks
(imprecise joints, slow on splines).

### HD4 — Pattern renderer + block compile

- **Pattern frame** — origin = region origin; axes = container axes (never
  rotated, D-A10/11); scale = region Scale × (Drafting ? 1/view-scale : 1)
  (Drafting needs SB1c; falls back to 1).
- **Geometry** — tile block compiled once to per-pen tile-local paths; for a
  region, stamp cells covering the clip bbox (row shift applied) into one
  `QPainterPath` per pen.
- **Cache** — per region, keyed `(tile def version, scale, boundary hash,
  view-scale bucket)`. Paint: IntersectClip to the region path → background →
  cached pattern paths.
- **LOD** — tile < ~2 device px → 35 % tone solid in the pattern colour; > 20k
  cells → tone regardless.
- **Pens** — cosmetic on canvas; named paper line weight on paper/PDF.
- **Replaces** Qt pattern brushes, the SVG `<line>` parser and `views()[0]`
  scale → fixes H2–H6.
- **Block compile** — ops become a `RenderOp(kind, colour, pen, path,
  tile_ref?, origin?, scale?)` with `kind ∈ {stroke, fill, pattern, text}`
  (replaces the `pen == NoPen ⇒ text` heuristic). Colour stays an unresolved
  ColourValue, resolved at paint → theme switches need no recompile. Fixes H1.
- **Section cut** (walls/floors) calls the same renderer via its Fill Type.

#### HD4a — HF2 build design (approved 2026-10-02; the *what* = D-A28–D-A35)

**Approach — paint-time stamping in scene axes.** `BlockInstance` bakes its
pose into geometry (no Qt transform), so its `paint` is in scene coords. The
compile keeps pattern ops definition-local (flyweight shared); paint maps
clip + origin through the pose and stamps cells in **scene axes** — the
boundary rotates, the hatch never does (D-A11, G3). Rejected: baking pattern
lines into the flyweight (rotates with the instance); raster brush textures
(raster PDF, H2 class).

**`RenderOp`** — new `render_op.py` (LT3's `StrokeOp` extends the same type):

```python
@dataclass(frozen=True)
class RenderOp:
    kind: str                      # "stroke" | "fill" | "pattern" | "text"
    path: QPainterPath             # definition-local, origin-relative; fill/pattern = closed clip (OddEven)
    pen: QPen | None = None        # stroke only
    colour: str | None = None      # fill/pattern/text (unresolved; HF1 ColourValue later)
    alpha: int = 255
    tile_ref: str | None = None    # pattern: tile block id or legacy alias
    origin: QPointF | None = None  # pattern: definition-local pattern origin
    scale: float = 1.0             # pattern: region Scale
```

`_compile` emits a primitive's fill/pattern op before its stroke op; text →
`kind="text"` (retires the `NoPen ⇒ text` heuristic in `block_instance.paint`
and `snap_engine`). `_nested_ops` maps `path` and `origin` through the pose.
Tuple-indexing tests (`op[0]`/`op[2]`) move to `op.path`/`op.kind` (contract
relocated, VC5).

**Tile schema** — `BlockDefinition.tile = {"w", "h", "row_shift", "size":
"model"|"drafting"} | None`; additive key (no schema bump); its setter bumps
the version + invalidates like `set_primitives`.

**Built-ins + alias** (`hatch_patterns.py`, rewritten) — `BUILTIN_TILES:
{frozen_id: BlockDefinition}` built in code (diagonal, cross_hatch,
horizontal, concrete; Drafting, 3 mm printed spacing; + brick 215×65 Model);
`LEGACY_ALIAS = {name: frozen_id}`; `resolve_tile(ref, registry)` = alias →
built-ins → project registry, else `None`; `tile_choices(registry)` = the one
picker source. SVG parser, `refresh_patterns`, `make_hatch_tile`,
`DEFAULT_PATTERNS`, `is_builtin` and `graphics/hatch_patterns/*.svg` deleted.

**Registry** — `block_registry.nested_ids` → `referenced_ids(defn)`: nested
records **plus** primitive `fill.pattern` ids, so `closure`, `bundle_for`,
`would_cycle`, `users_of`, `invalidate` follow pattern use (G5, `.fpdb`
bundling, self-reference cycle refusal). Same generalisation as linetypes LD5.

**Renderer** — new `hatch_render.py`; one entry point:

```python
def paint_fill(painter, clip_scene_path, *, scene,
               background: QColor | None, tile_ref: str | None,
               colour: QColor | None, origin: QPointF,
               scale: float = 1.0, line_width_px: float = 1.0) -> None
```

1. save → `setClipPath(clip, IntersectClip)` (H5).
2. Background rect if set.
3. Resolve tile; effective cell = `w,h × scale × drafting_factor` (Model → 1).
4. LOD: device scale = `hypot(m11, m12)` of `painter.deviceTransform()`
   (rotation-safe; paper/PDF-correct; no `views()[0]` — H6). Cell < 2 px or
   > 20k cells → 35 % tone fill, return.
5. Cell range = (clip bbox ∩ visible paint area) grown by the content's
   overhang past the frame (D-A33), snapped to the lattice anchored at
   `origin`; when the visible area cuts the fill (the panning case) the range is widened to 4-cell steps so panning reuses cache entries, while a fully visible fill stamps its exact cells (user ruling 2026-10-02, `afb2322`).
   Visible area = the device rect mapped back through the inverse of
   `combinedTransform()` (not `deviceTransform()`, which carries a widget's
   offset in its window — review C1), ∩ `clipBoundingRect()` (user ruling 2026-10-02, HF2 Task 3
   review I2: a large fill shows real hatch when zoomed in; the 20k cap
   counts visible cells only).
6. Cached lattice path keyed `(identity of the tile's compiled op list, eff
   scale, nx, ny, row parity)` — not the tile version, which undo can
   restore to a number already cached with other content (Task 3 review
   I1); the cache is bounded by a total-cells budget
   (`HATCH_LATTICE_CACHE_MAX_CELLS`), not an entry count — union of the tile's stroke paths offset per cell, row shift
   on odd rows — then `translate(first cell)` → `drawPath` (no path copy).
   Unrotated copies of one block share an entry.
7. Pen: canvas cosmetic `line_width_px`; paper/PDF = "Hatch" paper category mm
   ÷ paper scale (the `_apply_construction` pattern).
8. Colour: override, or the tile's authored pen colours ("By block"); fill
   ops inside a tile draw as tone fills.

`drafting_factor(scene)`: inside a paper-viewport render `1 / paper_scale`
(`apply_paper_overrides` sets `scene._hatch_paper_scale`;
`restore_model_display` clears it — the apply/restore window HF1's surface
context also uses); items on a `paper_space.PaperScene` (sheet-native,
already printed mm) 1; model canvas / Block Editor /
previews `constants.DRAFTING_CANVAS_SCALE = 100` until SB1c (D-A30).
`displayable_item.draw_fill` stays as the per-item 2D adapter (seven
`geometry_2d` call sites; HF3 dissolves per-item fill and retires it) and
`draw_section_hatch` stays as the wall/floor adapter — both become thin
wrappers over `paint_fill`; `_apply_hatch_pattern` is deleted.

**Callers** — `wall.py` / `floor_slab.py` section cut: `paint_fill(...,
origin=(0,0))` (container origin). `geometry_2d` per-item fill → `paint_fill`
with the container origin (no swim — H11 for 2D) and the item alpha.
`BlockInstance.paint` → `paint_fill(pose.map(op.path),
origin=pose.map(op.origin), ...)` for fill/pattern ops.

**Paper "Hatch" category** — new `paper_display._CATEGORY_KEYS` entry,
factory 0.13 mm; the Display Manager paper tab enumerates it.

**Block Editor authoring** — tile state `editor_scene.block_tile` (seeded
from `defn.tile`; `commit_block` → `commit_block_definition(tile=...)`; in the
undo snapshot like constraints — hook probed as plan step 1).
- Ribbon **Pattern tile** toggle (tooltip). On → seed per D-A32 (corner at
  origin, content extents, 10×10 empty); refused with a status message when
  `instance_count(id) + len(users_of(id)) > 0` (D-A34). Off → tile cleared;
  references render the missing-tile tone.
- **`TileFrameItem`** (new `tile_frame.py`; LT's repeat frame reuses it):
  non-primitive overlay (`data(0) == "tile_frame"`) excluded from
  `gather_primitives`, snap targets, delete and paper; it stays HALO-pickable
  and selectable, because the manipulator only shows grips on a selected item
  (U3 `default_grip_handles` + a no-op `manip_translate` — the frame is
  anchored at the origin). Selecting it shows the same tile fields as the
  nothing-selected panel. Dashed accent rect (0,0)→(w,h); W/H grip
  top-right; row-shift grip on the top edge (X only); grips snap via the
  existing handle-snap path. Live repeat preview = the 8 surrounding cells
  (+ shift) at 35 % via `hatch_render`'s lattice builder over a scratch tile
  compiled from the current editor primitives (preview ≡ render); rebuilt on
  `sceneModified`, debounced to the next frame. **Mockup-gated.**
- `BlockPropertiesInfo` gains a **Pattern tile** section (nothing selected):
  `Pattern tile` bool, `Width` / `Height` / `Row shift`
  (`format_length`/`parse_dimension`), `Size` Model|Drafting (default
  Drafting); hidden when off; edits move the frame; tooltips on every field.

**Pickers** — `geometry_2d` property options, both context menus, the two
`main.py` combos and the Display Manager section column read
`tile_choices(registry)` and store the id (D-A29). DM swatches render via
`paint_fill` into a pixmap (preview ≡ render; H3 swatch mismatch).

**Placement refusal** — at the lowest shared *user* entries (not
`place_block_instance`, which load / explode / undo use):
`Model_Space.set_mode("place_block")` (ribbon, browser, `model_view` mode
entry) and the `model_view` drag gate's `(defn, pool, reason)` check (gains
"Pattern blocks fill regions — they can't be placed"). `blocks_browser`
draws a hatch badge on tiled entries.

**Errors / edges** — unknown or missing tile → 35 % tone in the given colour
+ one log line, never blank; zero-size or empty tile → listed nowhere, panel
hint "Tile is empty"; a tile referencing itself (fill or nesting) → refused by
the `referenced_ids` cycle guard; definitions without `tile` unchanged.

**HF2 guards** (VC3; each RED with its change reverted):

| Guard | Scenario | Ground truth |
|---|---|---|
| H1 / place | block with a hatched rect placed on the plan scene, offscreen render | hatch pixels inside the rect, none outside |
| G3 | same block at 30° | line angle fitted from sampled hatch pixels = 45° ± 1° |
| G4 | Scale ×1 vs ×2, canvas render + `paper_export` PDF | spacing ratio 2.0 ± 5 % on both (PDF via PyMuPDF path extraction) |
| G5 | tile block `set_primitives` | placed-instance + section-cut-wall pixels change, no reload |
| Alias | fixture `.fpd` `fill.pattern="diagonal"` + QSettings `section_pattern="diagonal"` | hatch pixels; stored ref round-trips to the frozen id |
| D-A30 | paper viewport 1:50 vs 1:100, Drafting diagonal | printed spacing 3 mm on both |
| Refusals | `set_mode("place_block")` + drop with a tiled block; tile-on for a placed block | mode not entered / drop rejected + status; tile stays `None` |
| G12 | 200 hatched instances vs unfilled, one viewport render (`perf`, own process) | hatched − unfilled ≤ 30 ms (≤ 0.15 ms/instance; D-A35 amended 2026-10-02); bench asserts stamped cell count > 0 |

**Build order** — (1) probes: `block_tile` undo hook, PyMuPDF spacing
extraction; (2) `RenderOp` + `_compile` + consumers + tuple-test rewrites;
(3) `hatch_render` + built-ins + alias + `referenced_ids` + paper "Hatch";
walls / floors / `draw_fill` onto it, old code deleted; (4) pickers →
`tile_choices` + ids; (5) mockup gate → `TileFrameItem` + toggle + panel +
undo; (6) refusals + browser badge; (7) guards + perf bench + spec
reconciliation (`block-system.md`, `2d-geometry.md` fill section, H2–H6
retired in `hatch-and-fill.md`).

### HD5 — Fill Types

- Project payload `fill_types: [{id (uuid), name, background: {colour,
  opacity} | null, pattern: {block_id, colour | "by_block", scale, opacity} |
  null}]`; template seeds the shipped set.
- Resolution: region → type → per-instance overrides. Missing type → "Solid
  Grey 20 %" fallback + "?" in the panel.
- `.fpdb` bundling: `fill_types` + pattern blocks in the nested-block bundle
  (schema 2 → 3); merge by **name**, project wins, ids remapped (D-A15).
- Delete guards: "used by N" via the `BlockRegistry` dependency graph extended
  with type → pattern edges.
- Fill Types manager pane — **mockup-gated** before build; Display Manager
  section column becomes a Fill Type picker (D-A17).

### HD6 — Colour tokens

- `resolve_colour(value, surface)`, `surface ∈ {canvas, paper}`: canvas → the
  current UI theme; paper → light-theme values; B&W mode → black (D-A19).
- Surface is a scoped context set by `paper_display`'s apply/restore window,
  PDF/print export and white-backdrop previews; default `canvas`.
- `theme.changed` QObject signal emitted by `MainWindow._apply_theme`;
  listeners `scene.update()` every scene; latched consumers (text default
  colour, SVG tints, labels, gridlines) subscribe and invalidate.
- `pick_colour(allow_tokens=True)` adds an Automatic / Accent row;
  `ui_kit.Swatch` shows tokens with an "A" badge.
- Migration of the scattered `QColor(str)` sites to `resolve_colour` goes by
  consumer family; a hexguard-style test blocks new raw `QColor(hex)` in item
  paint code.
- Load migration per D-A20; file-format version bump.

### HD7 — Import

- **PDF** (`_extract_path`): read `type`, `fill`, `fill_opacity`, `even_odd`,
  `seqno`; keep subpaths separate (fixes the zig-zag join); emit
  `fill: {colour, opacity, rule}` + `order`. Glyph-outline fills (small, dense,
  aligned with page text spans) group per text run. Pure black →
  `token:auto` (D-A21).
- **Underlay render** (`_build_batched_underlay_group`, `_compile_reference`,
  `repen_underlay`): batches split into runs by `order` (stroke → fill →
  stroke …) so paint order (white masks) survives batching; underlay cache
  version bump.
- **Block Editor import**: fill → FilledRegion on "Imported Solid" + colour
  override; `fs` → region + outline (D-A22).
- **DXF SOLID**: vertex order 0-1-3-2 (fixes bowtie) → filled.
- **DXF HATCH**: read `hatch.paths` (loops + islands) instead of the missing
  `virtual_entities()`; underlay = fill + pattern lines (ezdxf hatch-line
  rendering).
- **HATCH → tile** (Block Editor): if every line family's direction has a
  rational slope p/q with |p|,|q| ≤ 8, a finite tile exists — the lattice LCM
  of the family periods, capped at 64× base spacing → project-only pattern
  block + "(imported)" type, deduped by definition hash. Otherwise lines +
  import-report note (D-A23).

### HD8 — Build slices

| Slice | Content | Depends |
|---|---|---|
| HF1 Colour tokens | HD6 complete | — |
| HF2 Renderer + tile blocks | HD4 + tile schema + Block Editor tile frame / live repeat preview + test patterns | — |
| HF3 FilledRegion + Select objects | HD2, D-A13, dissolve + migrate per-item fill (D-A16), dead code (H9) | HF2 |
| HF4 Pick point | HD3 + hover preview + perf guard | HF3 |
| HF5 Fill Types | HD5 (manager mockup-gated) + DM section → type | HF3 |
| HF6 PDF fills | HD7 PDF + underlay + Block Editor import | HF3, HF5 |
| HF7 DXF SOLID / HATCH | HD7 DXF incl. tile conversion | HF6 |
| HF8 Shipped System > Hatches + template types | D-A24 | HF5, SB1b |
| HF9 Drafting patterns in model | view-scale term of HD4 | SB1c |

HF1 and HF2 are independent and may run in parallel.

## Acceptance Criteria

- [ ] Every D-A1…D-A27 in `hatch-and-fill.md` holds in the shipped build.
- [ ] Guards G1–G12 (below) pass and each is shown RED with its change reverted.
- [ ] D-A25 perf bars met on real data (benches confirmed with the user first).
- [ ] H1–H12 resolved or explicitly retired.
- [ ] Linked specs amended per `hatch-and-fill.md` "Cross-spec reconciliation".

## Verification Checklist (guards — VC3: real path, observable ground truth)

- **G1 Ring** — two concentric circles, pick between: placed-instance pixel
  sample filled in the ring, empty at the centre.
- **G2 Mixed boundary** — line + spline + one rect edge: region boundary
  within 0.2 mm of the drawn curves; a 1.5 mm gap → "Not enclosed", nothing created.
- **G3 Angle invariance** — rotate region and placed instance 30°: sampled
  hatch angle stays 45°.
- **G4 Scale** — region Scale ×2 doubles measured hatch spacing on screen and
  in exported PDF.
- **G5 Pattern edit** — editing the tile block re-renders every region using it.
- **G6 Type restyle** — type colour change updates regions and cut walls.
- **G7 Library round-trip** — block with region saved to library, loaded into
  a fresh project: type + pattern arrive; on collision the project wins.
- **G8 Automatic** — light on dark canvas, black on paper/PDF, black in B&W;
  live theme switch repaints without relaunch.
- **G9 Migration** — old block with `prim["fill"]` + white lines → region +
  shape, Automatic stroke, filled when placed.
- **G10 PDF** — fixture with ring fill, white mask, glyph text: underlay keeps
  the hole and order; Block Editor import yields regions.
- **G11 DXF** — fixture with SOLID, solid HATCH, ANSI31 HATCH → correct regions
  + one deduped pattern block.
- **G12 Perf** — D-A25 bars as `perf`-marked guards in their own process.

## Edge Cases & Error Handling

- Pick on a boundary line itself → treat as a click on the nearer side's face.
- Click outside every closed face (open space) → "Not enclosed".
- Region whose source items are later deleted → unaffected (static, D-A1).
- Tile block with no content or zero-size tile → not listed in pickers; the
  Block Editor shows a "tile is empty" hint.
- Nested pattern recursion (a tile containing a region that uses the same
  pattern) → refused by the `BlockRegistry` cycle guard.
- Unknown token string in a file (future token) → render as Automatic + one
  load warning; never silently black.

## Performance & Security

Perf bars D-A25. Region cache + LOD tone + cell cap bound pattern cost;
arrangement build is grid-bucketed and windowed around the click. Before any
optimisation, confirm the metric with the user and A/B on real data.
