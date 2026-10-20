---
status: partial          # HF4 BUILT 2026-10-20 (merge bb7074b8, feat/hf4-pick-region): Pick-point region finder (region_finder.py) + pick_region mode + hover overlay -- see "HF4 build design". Prior: HF3 BUILT 2026-10-20 (merge 66880197, feat/hf3-filled-region): FilledRegionItem (filled_region.py) + curve_chain.py Select-objects Fill, D-A13 refusals, Explode, H9 closed -- see "HF3 build design". Prior: HF1 BUILT 2026-10-18 (merge 084b43e0, feat/hf1-colour-tokens): colour tokens (token:auto / token:accent), per-paint resolver, theme bus, SAVE_VERSION 11 + .fpdb marker migration, universal picker -- see "HF1 build design". Prior: HF2 BUILT (branch hf2-pattern-renderer): tiled pattern renderer, pattern-tile blocks + Block Editor tile authoring, Hatch patterns folder, blocks-only shipped patterns (D-A28–D-A39). UNBUILT: Filled Regions, Fill Types (+ template set), colour tokens, PDF/DXF fill import (HF1, HF3–HF9). §1–§4 = as-built at 53e1773
last-verified: 2026-10-20  # UP2 Account: H7 closed (both context menus open the picker, one deferred_undo_push; verified at ab930f58; nothing else re-audited); prior HF4 Account: D-A3..D-A6 + D-A25 re-stated against the build, §2 Pick-point pointer, "HF4 build design" pointer, applies-to + region_finder.py (verified at bb7074b8; sections 1-4 otherwise not re-audited); prior HF3 Account: Filled Region rules (D-A2/D-A3/D-A5/D-A7/D-A13/D-A26) re-stated against the build, H9 resolved, "HF3 build design" pointer, applies-to + filled_region.py / curve_chain.py (verified at 66880197; sections 1-4 otherwise not re-audited); prior 2026-10-19 UP1 Account: shape-fill pointers (adapters, data path, H7/H8, D-A16, applies-to) re-verified at 902c5c0e; prior 2026-10-18 HF1 Account: "HF1 build design" re-stated as SHIPPED (resolve-time unknown-token warning, helper API, picker/amendment list, theme-bus listeners, new invariants, S1-S3 resolved, known gaps); prior HF2 polish Account: D-A11 block-pose exception (RenderOp.pattern_frame, paint_fill orient — rotation + mirror, never scale; block instances only), pickers hide invalid folder patterns (capability_choices valid_entry); prior disk-scan Account: shipped Hatches index.json removed; seeding writes no index (pointer to block-system "Library on disk"); D-A37 flag pointer; prior LT4 Account: §2 tile frame → TileFrame on the shared capability_frame.CapabilityFrameItem base (this spec's home; TileFrameItem / TILE_FRAME_TAG aliases, tag "capability_frame"), tile rows via capability_panel; applies-to + capability_frame.py; prior Weight model design: D-A12 "By block" → By Pattern pointer (WM-8); prior LT3 Account: Folder scan bullet → capability_folder.scan (tile flag) + LT3-9 pointer; prior 2026-10-03 HF2 Account: §1–§4 rewritten to the HF2 code; ledger H1–H6/H11/H12 resolved, H9 partly; prior 2026-10-01 orphan-gate review at 3a95a3f
verified-commit: ab930f58   # UP2 Account (feat/up2-fill-picker-routing; H7 row only); prior bb7074b8 HF4 Account (merge feat/hf4-pick-region; D-A3..D-A6/D-A25 + applies-to); prior 66880197 HF3 Account (merge feat/hf3-filled-region; Filled Region rules + H9 + applies-to); prior 902c5c0e UP1 Account (shape-fill pointers only); prior 084b43e0 HF1 Account (merge feat/hf1-colour-tokens; HF1 section only -- sections 1-4 still as of 6bacede7); prior 6bacede7 HF2 polish Account (merge feat/hf2-polish); prior 73d16e2b disk-scan Account (feat/block-library-disk-scan: index.json retired; pointers only); prior b9b1094 LT4 Account (feat/lt4-repeat-authoring; capability frame only); prior 489dcc2 Weight model pointer; prior be7c88a LT3 Account (folder-scan relocation only); prior 53e1773
applies-to:
  - firepro3d/hatch_patterns.py     # pattern registry: frozen ids, legacy alias, folder seed + scan entry (library_patterns), picker source, project pattern load
  - firepro3d/capability_folder.py  # shared capability-folder scan — the "tile" side (the "repeat" side is owned by linetypes.md LT3)
  - firepro3d/hatch_render.py       # renderer: paint_fill / stamp_lattice / paint_swatch
  - firepro3d/render_op.py          # RenderOp type — shared with linetypes (LT3 extends it); block compile semantics owned by block-system.md
  - firepro3d/colour_tokens.py      # HF1: token resolver (is_token / normalize_colour / resolve_colour / preview_colour / resolve_pen_brush / section_fill_colour / paint_resolver)
  - firepro3d/colour_migration.py   # HF1: SAVE_VERSION 11 / .fpdb marker load migration (legacy default colours -> token:auto)
  - firepro3d/colour_picker.py      # HF1: universal picker Theme row (owner of D6 signature = ui-design-system.md)
  - firepro3d/capability_frame.py   # Block Editor capability frame base (CapabilityFrameItem, tag, frame_for) — shared with linetypes.md LT4 (RepeatFrame), owned here
  - firepro3d/tile_frame.py         # Block Editor pattern-tile frame (TileFrame) + tile panel rows
  - firepro3d/system_blocks/Hatches/  # shipped pattern .fpdb files (D-A39; the shipped index.json was removed 2026-10-10)
  - firepro3d/displayable_item.py   # draw_section_hatch adapter only (draw_fill retired by UP1; the mixin's other state is owned elsewhere)
  - firepro3d/fill_layers.py        # UP1: FillLayers / BackgroundLayer / PatternLayer + fill record read/write (contract = superpowers/specs/2026-10-18-up1-two-layer-fill-design.md)
  - firepro3d/filled_region.py      # HF3: FilledRegionItem -- loops of primitive records, two-layer fill, delegated transforms, Explode pieces (build contract = superpowers/specs/2026-10-20-hf3-filled-region-design.md)
  - firepro3d/curve_chain.py        # HF3: close_loops chain closure for Select-objects Fill (CHAIN_WELD_MM, D-A6); pure geometry
  - firepro3d/region_finder.py      # HF4: Pick-point arrangement (flatten, split, weld, prune, face walk, islands, nudge) + exact rebuild; pure geometry (build contract = superpowers/specs/2026-10-20-hf4-pick-region-design.md, which also owns the pick_region mode in model_space.py and the overlay in model_view.py)
source-tasks: ["Concept: region Fill/Hatch tool + user-definable hatch patterns as blocks + theme-Automatic colours (2026-10-01)"]
---

# Hatch & Fill — Design Spec (current behaviour + divergences)

> **Orphan-gate spec (2026-10-01), HF2 built (2026-10-03).** §1–§4 record what
> the code does *today* (HF2: renderer + pattern-tile blocks). Per-item fill
> *state* on 2D primitives stays owned by [`2d-geometry.md`](2d-geometry.md)
> (fill section); section-cut hatch *wiring* stays owned by the Display Manager
> + [`wall-room-floor-system.md`](wall-room-floor-system.md); the block
> `tile` key, `RenderOp` compile and dependency registry are owned by
> [`block-system.md`](block-system.md) ("Pattern-tile capability (HF2)").
> This spec owns the **pattern registry, the Hatch patterns folder and the
> fill/hatch renderer**.

## 1. As-built: pattern registry (`hatch_patterns.py`)

- **A pattern is a block with a tile** (D-A8/D-A9). There is no code-level
  pattern table (D-A39). The five shipped patterns (Diagonal, Cross Hatch,
  Horizontal, Concrete, Brick) are `.fpdb` files in
  `firepro3d/system_blocks/Hatches/` (+ `index.json`), carrying the frozen
  ids `BUILTIN_*` (`builtin-hatch-…`); located via
  `assets.system_blocks_path("Hatches")` and read once per process
  (`shipped_pattern_files`).
- **Hatch patterns folder** (D-A37) = `app_data.hatch_patterns_dir()` (key
  and precedence owned by [`settings-dialog.md`](settings-dialog.md) §4.5b).
  `seed_hatch_folder` copies the shipped files in **once per folder**
  (recorded under `HATCH_SEEDED_KEY`), skipping any id already held by an
  `.fpdb` in the folder and any clashing file name; it never rewrites an
  unreadable `index.json`, and marks the folder seeded only when every shipped
  id is present and the index is sound (a failed copy retries). Called at app
  startup (`main.py`) and after System Settings Apply/OK. *(2026-10-10: the per-folder `index.json` is retired — listings read the `.fpdb` files; see [block-system.md "Library on disk"](block-system.md#library-on-disk-no-index-2026-10-10).)* Seeding
  writes no index and removes a stale one; the folder is marked seeded once
  every shipped id is present.
- **Folder scan** — `library_patterns()` delegates to the shared
  `capability_folder.scan(folder, "tile")` (moved there in LT3 so the
  Linetypes folder reuses it with `"repeat"` — scan rules: `linetypes.md`
  "LT3" H3-i). The `tile` flag decides; never called from paint. Strokes inside
  a stamped pattern tile stay Continuous (`linetypes.md` LT3-9).
- **Resolution** — `canonical_ref` maps a legacy name through `LEGACY_ALIAS`
  (`diagonal`, `cross_hatch`, `horizontal`, `concrete` → frozen ids; D-A29).
  `resolve_tile(ref, registry)` = alias → the **project** block registry, and
  only a definition with a tile; else None (the renderer then draws the tone,
  D-A36). `preview_tile` (swatches only) additionally falls back to the folder
  copy, then the shipped file.
- **Picker source** — `tile_choices(registry, exclude)` is the single source
  for every pattern picker: the project's valid tiled blocks, then folder
  patterns not yet in the project whose file tile is valid (`tile_is_valid`
  via `_file_tile`, passed as `capability_choices(valid_entry=)`; an empty or
  zero-size library pattern is hidden — HF2 polish 2026-10-17), with unique
  labels. `picker_exclude` drops
  the edited block and every tile that would nest it (Block Editor).
  `ensure_pattern_available` loads a picked folder pattern into the project
  (one undo step via `blocks_browser.ensure_block_loaded`) before its id is
  stored; `MISSING_PATTERN_LABEL` / `ref_from_value` implement D-A36.
- **Project load** — `ensure_project_patterns(scene)` collects every ref the
  project uses (`project_pattern_refs`: 2D hatch fills, block-definition
  primitive fills, item + per-instance DM section patterns, DM category
  section patterns, and `DEFAULT_TILE_REF`) and loads the missing ones from
  the folder **outside the undo history**
  (`Model_Space.load_blocks_outside_history`), repeating for nested patterns.
  Called on project new and open (`main.py`) and on Display Manager OK.

## 2. As-built: renderer (`hatch_render.py`)

- **`paint_fill(painter, clip, *, scene, background, tile_ref, colour, origin,
  scale, line_width_px, to_scene, orient)`** — the one entry point:
  IntersectClip to the boundary (H5), optional solid background, then the tile
  lattice. With `to_scene`, the painter is re-based to **scene axes** so a
  rotated item never rotates the pattern (D-A11); with `orient` (a placed
  block only — `BlockInstance._paint_fill_op` passes
  `render_op.pattern_orient(op.pattern_frame, pose, sceneTransform)`) the
  pattern frame is that rotation / reflection instead, scale stripped (D-A11
  block-pose exception); `origin` is in scene coords,
  default (0, 0) = the container origin (H11). A ref that does not resolve to a
  valid tile (`tile_is_valid`: positive W×H and at least one op) draws the
  tone, logged once (D-A36). Non-finite bounds draw nothing (never raises).
- **Effective scale** `k = scale × drafting_factor(scene)` for a Drafting tile
  (Model → `scale` only). `drafting_factor` (D-A30): inside a paper-viewport
  render `1 / scene._hatch_paper_scale` (set/cleared by
  `paper_display.apply_paper_overrides` / `restore_model_display`); a
  `PaperScene`'s own items 1; else `DRAFTING_CANVAS_SCALE` (model canvas and
  Block Editor).
- **`stamp_lattice`** — LOD tone (`HATCH_LOD_*`, D-A35) when a cell is under
  the minimum device size (device scale = `hypot(m11, m12)` of
  `deviceTransform()`, no `views()[0]` — H6) or the cell count exceeds the
  cap. Only cells over `bounds ∩ visible area` are stamped (visible area via
  the inverse `combinedTransform()` ∩ `clipBoundingRect()`); the range is
  grown by the tile content's overhang (D-A33) and, only when the visible area
  cuts the fill, snapped outward to `HATCH_VISIBLE_SNAP_CELLS` steps. Row
  shift applies on odd lattice rows, anchored at `origin`.
- **Lattice cache** — keyed by the identity of the tile's compiled op list
  (a content key: every content change yields a new list; the entry holds the
  list so its id is not recycled), effective scale, cell counts and row
  parity; LRU bounded by a total-cell budget (`HATCH_LATTICE_CACHE_MAX_CELLS`).
- **Pens** (`_pattern_pen`) — canvas: cosmetic `line_width_px`, drawn
  **aliased** (no dim AA-split lines); paper / viewport render: true-mm width
  = `paper_display.hatch_line_mm()` (the "Hatch" paper category, D-A31) ÷ the
  paper scale. Filled tile ops are drawn in the pattern colour.
- **`paint_swatch`** — picker / Display Manager swatch through the same
  `stamp_lattice` (preview ≡ render, H3); resolves via `preview_tile`.
- **Adapters** (`displayable_item.py`): `draw_section_hatch` (walls / floor slabs section cut: section fill +
  pattern + scale) is a thin `paint_fill` wrapper passing the item's
  `sceneTransform()` as `to_scene`. The 2D-shape fill no longer has an adapter here: the shape mixin
  calls `paint_fill` directly for its two layers (UP1; `draw_fill` retired) —
  [`2026-10-18-up1-two-layer-fill-design.md`](../superpowers/specs/2026-10-18-up1-two-layer-fill-design.md).
- **`pattern_preview`** — the one preview pixmap helper (picker Pattern row, fill swatch chip, Display
  Manager; UP1, promoted from the Display Manager's former fill-icon helper); same `stamp_lattice` path.
- **Block Editor capability frame** (`capability_frame.py`, this file's home
  since LT4 generalised the HF2 tile frame). `CapabilityFrameItem` is the
  shared non-primitive overlay of the Block Editor's capability
  (the one `Model_Space.block_capability` slot — [`linetypes.md`](linetypes.md)
  LT4 H4-a):
  tag `CAPABILITY_FRAME_TAG = "capability_frame"` (`data(0)`), dashed accent
  rect, a repeat-preview ring clipped outside the frame at
  `PREVIEW_OPACITY` (35 %), a scratch definition compiled from the live
  editor content with the frame's capability (preview ≡ render), HALO / pick
  shape, grips through the manipulator, and anchoring at the origin
  (`MANIP_ANCHORED`, inert translate). It is excluded from primitives
  (`gather_primitives`), snap targets (`snap_engine._NON_TARGET_TAGS`), delete
  and copy (`Model_Space.delete_items` / `copy_selected_items`), and never
  joins a multi-selection panel ([`property-panel.md`](property-panel.md)
  §3.5). `frame_for(scene, kind)` builds the subclass for `"tile"` /
  `"repeat"` and raises `ValueError` otherwise. Subclasses: `TileFrame`
  below; the linetype `RepeatFrame` → [`linetypes.md`](linetypes.md) LT4 H4-b.
- **Block Editor tile frame** (`tile_frame.py`, D-A32/D-A38): `TileFrame`
  (`KIND = "tile"`; HF2 names `TileFrameItem` and `TILE_FRAME_TAG` kept as
  aliases — the tag value is now `"capability_frame"`) with W/H and row-shift
  grips and an 8-cell repeat preview through `stamp_lattice` (at authored
  size); `seed_tile` (content extents from the origin, 10×10 empty, Size =
  Model). `tile_properties` / `set_tile_property` are the tile rows; the
  nothing-selected panel and a selected frame reach them through the shared
  capability panel (`capability_panel.py`, owned by
  [`linetypes.md`](linetypes.md) LT4 H4-f), under a **Repeat** header with
  the Pattern tile / Linetype toggles (a block is a pattern or a linetype,
  not both).
- Shape fill is **one item's own closed path** (`get_closed_path()`). Areas
  that are not one shape are a **Filled Region** (HF3, `filled_region.py`):
  its `get_closed_path()` is the OddEven path over its boundary loops, so
  `_fill_ops` / `paint_fill` / HALO work on it unchanged; the boundary comes
  from Select objects via `curve_chain.close_loops`, or from Pick point via
  `region_finder.Arrangement` + `rebuild` (HF4: crossings split faces, islands
  become inner loops). Build contracts: "HF3 build design" / "HF4 build
  design" below.

## 3. As-built: data path

| Hop | Where | Key |
|---|---|---|
| 2D item state | `geometry_2d.Geometry2DMixin` | `fill_layers` (UP1: background + pattern layers, each with colour / opacity; pattern ref canonicalised on load) — shape and record in [`2026-10-18-up1-two-layer-fill-design.md`](../superpowers/specs/2026-10-18-up1-two-layer-fill-design.md) |
| Serialize | `_geom2d_to_dict` / `_from_dict` | the `"fill"` record via `fill_layers.to_record` / `from_record` (omitted when empty; legacy `{type, pattern, color, opacity}` read at load, no version bump) — same doc |
| Block compile | `block_definition._fill_ops` → `RenderOp` | primitive fill → a `fill` / `pattern` op before its stroke (origin = container origin); painted by `BlockInstance` via `paint_fill` with the pose — compile contract → [`block-system.md`](block-system.md) |
| Block tile | `BlockDefinition.tile` | `{w, h, row_shift, size: model\|drafting}` or None — owned by `block-system.md` |
| Section (DM) | `display_manager` | `section`, `section_pattern` (tile ref; factory defaults still legacy `"diagonal"`, read via alias), `section_scale`; DM `fill` colour still uses a `"hatch:#rrggbb"` prefix |
| Paper | `paper_display` | pens remapped; pattern lines use the "Hatch" category weight (weight-only row); 2D fill colour not remapped |
| Import | `pdf_import_worker`, `dxf_import_worker` | no fill emitted (unchanged by HF2; D-A22/D-A23 unbuilt) |

A shape's pattern layer ref and `section_pattern` now share one vocabulary (tile refs);
the DM `"hatch:"` colour-mode prefix and the differing opacity units (0..1 vs
0..100) remain until D-A17 / Fill Types.

## 4. Divergences ledger (as-built defects, probed 2026-10-01; re-audited at 53e1773)

| # | Divergence | Evidence | Status |
|---|---|---|---|
| H1 | Fills vanish in placed blocks — `_compile` ignored `prim["fill"]`; with loose model geometry clean-dropped (containment C8), no saved project showed a 2D fill outside the Block Editor | probe: solid red rect → compiled op `NoBrush` | **RESOLVED** — compile `c4b416c` (typed `RenderOp`, fill/pattern ops), render `976d4c7` (`BlockInstance` → `paint_fill`) |
| H2 | Built-in pattern scale was a no-op — Qt pattern brushes are cosmetic unless `NonCosmeticBrushPatterns`; hatch was a fixed 8 device-px period on screen, paper and PDF | offscreen QImage probe | **RESOLVED** `976d4c7` (world-unit tiled renderer `af1bdd5`; no Qt pattern brushes remain) |
| H3 | `concrete` rendered nothing (its SVG had 0 `<line>` elements); the swatch showed a diagonal fallback (preview ≠ render) | parser probe | **RESOLVED** — SVGs deleted + `concrete` given real geometry `59a05b4`; swatches via `paint_swatch` `9538ab4` |
| H4 | `diagonal.svg` was dead (shadowed by the built-in) | registry probe | **RESOLVED** `59a05b4` (`graphics/hatch_patterns/` deleted) |
| H5 | `draw_svg_hatch` used ReplaceClip (`setClipPath` default) — the paper-viewport bleed class `paper-space.md §6.2` | code read | **RESOLVED** `976d4c7` (`paint_fill` IntersectClip) |
| H6 | Tile size read `scene.views()[0]` (the vestigial view) | already filed (vestigial-view scale todo) | **RESOLVED** `976d4c7` for hatch (device scale from the painter); the general vestigial-view todo is separate |
| H7 | Fill undo ordering — context menus + ribbon Graphic Override call `push_undo_state()` before `set_property`; redo loses the fill | probe: redo → none | **PARTLY CLOSED** by UP1: the ribbon Graphic Override fill swatches now write inside one `deferred_undo_push` (the setters request the push). **CLOSED** by UP2 (`879a262b`): both context menus' "Fill…" / "Fill Pattern…" entries open the picker and write every fillable selected shape inside one `deferred_undo_push` (`entity_context_menu._pick_and_apply`); redo restores the fill |
| H8 | Hatch drawn at the solid opacity with no UI to change it | code read | **CLOSED** by UP1: each fill layer carries its own opacity, edited in the picker's fill modes; the solid-only Fill Opacity row and `draw_fill` are retired — [`2026-10-18-up1-two-layer-fill-design.md`](../superpowers/specs/2026-10-18-up1-two-layer-fill-design.md) |
| H9 | Dead code: `refresh_patterns`, `is_builtin`, `make_hatch_tile`, `DEFAULT_PATTERNS`, `wall._draw_hatch`, `MainWindow._build_fill_group`, `annotations._rebuild_path_from_elements` | whole-repo grep | **RESOLVED** — the four `hatch_patterns` names gone `59a05b4`, `_build_fill_group` deleted `9538ab4`; `wall._draw_hatch` + `annotations._rebuild_path_from_elements` deleted `fe4efde5` (HF3 R14; guard `tests/test_filled_region.py::TestDeadCode`) |
| H10 | Roof exposes DM section pattern/colour that `roof.py` never draws | code read | **OPEN** (D-A17 removes the column) |
| H11 | No angle / origin anchoring — tiles started at the clip bbox, so the pattern swam when the shape moved | code read | **RESOLVED** `976d4c7` (lattice anchored at the container origin, stamped in scene axes) |
| H12 | `2d-geometry.md` + `scene-io.md §4` described a legacy HatchItem *migration*; code discards it (containment C8) | doc vs code | **RESOLVED** (docs) in the HF2 Account — both specs now say clean-dropped |

## Design Decisions (as-intended — ratified in the 2026-10-01 concept grill, Q1–Q27)

Problem-definition locks only; the *how* (data model, algorithms, schema) is
owned by the concept design doc produced in Phase 3 and is **as-proposed**
until that doc is approved.

**Filled Region (object)**
- **D-A1** A Filled Region is its own selectable object with a *static* copy of
  its boundary loops (curves kept as curves). Associative boundaries deferred
  until stable primitive ids exist (System Blocks SB5).
- **D-A2** Regions live in Block definitions (Block Editor) and on Paper only —
  never loose in Model Space (containment C1 unchanged). *(**HF3 R1**, ratified
  2026-10-20: Paper has no 2D-geometry layer — sheets hold text + viewports —
  so the Paper half is **not applicable**; regions are **Block Editor only**
  and reach sheets through placed instances in viewports. `fill_selected_items`
  is a no-op outside `scene_role == "block_editor"`.)*
- **D-A3** v1 creation: **Pick point** (primary) + **Select objects**
  (fallback). Sketch / Edit Boundary deferred. *(**Select objects BUILT by HF3**
  as chain closure — select first, click the Block Editor **Fill** button,
  immediate (R3/R8); several closed loops → one region, OddEven (R4); a failed
  Fill reports why in the status bar and creates nothing (R5). **Pick point
  BUILT by HF4** (`region_finder.py`, `pick_region` mode): the Fill button is
  always live in the Block Editor; with no boundary candidates selected
  (empty, or only text / regions / reference / hidden) it enters Pick point
  and stays there — one click = the clicked face, one region + one undo step
  per click, last region selected, Esc / right-click ends the mode (AC1, AC6);
  a click inside a face an existing region covers is refused with "This area
  already has a Filled Region" (AC7). HF3 smoke ruling 2026-10-20: both modes
  stay; a pick fills the clicked face only, one region per click.)*
- **D-A4** A pick fills exactly the clicked connected face; anything inside any
  closed island stays empty (no island-style option). *(HF4: the face is the
  tightest-left half-edge cycle around the click; one level of islands becomes
  inner loops, OddEven handles deeper nesting; faces under
  `CHAIN_MIN_LOOP_AREA_MM2` are refused; the boundary is rebuilt as exact
  Line / Arc / Circle / Bezier-chain pieces, polyline fallback ≤ 0.2 mm.)*
- **D-A5** Boundary candidates: visible 2D primitives + block geometry in the
  same container. Ignored: text, other regions, reference-flagged shapes,
  viewport contents and frames, hidden items. *(HF3 R15: the Select-objects
  candidate filter drops regions, text, block instances, hidden and
  `reference`-flagged shapes silently. HF4 Pick point: the same filter, plus
  each visible placed block instance contributes its posed geometry through
  `block_snap_geometry.posed_primitives` stand-ins — AC3.)*
- **D-A6** Gaps ≤ 1 mm (container units) count as closed; otherwise hover shows
  a red "Not enclosed" hint and nothing is created (leak highlight nice-to-have).
  *(HF4 BUILT: `CHAIN_WELD_MM` vertex weld + T-gap weld; hover shows the red
  cursor label and a red ring at the nearest pruned open end — the leak
  highlight — and a click there reports "Not enclosed" in the status bar; an
  enclosed face shows the accent tint + boundary trace, AC4/AC5.)*
- **D-A7** Own optional outline (line style, default Invisible). Authored
  regions draw behind other geometry; manual draw order deferred. Exception:
  imported regions keep source paint order (D-A22). *(HF3: `outline` flag,
  default off; on = the normal stroke fields (R11); draw order = the constant
  `Z_FILLED_REGION` in `constants.py`, below every shape.)*
- **D-A13** Modify tools: Move/Copy/Array/Rotate/Mirror/Scale transform the
  boundary (pattern never rotates/mirrors/resizes — regions; a placed block
  instance: D-A11 exception; origin translates); Offset,
  Trim/Extend/Break/Fillet refused; Explode → boundary loops as plain primitives;
  no grips in v1; copy/paste between Block Editor ↔ Paper allowed. *(**BUILT by
  HF3**: transforms delegate to each boundary piece's own hook; Offset / Trim /
  Extend / Break / Fillet / **Chamfer** refuse with a status line (*"Filled
  Regions can't be …"*, `scene_tools._find_tool_target`); Explode through the
  existing Explode button + context menus (R6), one undo step; the Block
  Editor ↔ Paper clause is N/A under R1. Guard: `TestToolMatrix`.)*
- **D-A16** Per-item fill on closed primitives is **dissolved** — every fill is
  a Filled Region; "fill this shape" creates a region from it. Existing
  `prim["fill"]` in block definitions migrates on load to region + shape.
  *(**Reversed 2026-10-18** by the unified-picker design run, rulings R2/R3/R12
  ratified: closed shapes **keep** their own fill, now two layers — background
  (solid | none) + pattern (tile | none), each with colour + opacity, the D-A12
  model — edited through the house picker's fill mode (UP1, UP2 in
  `todo_open.md`). No dissolve, no `prim["fill"]` migration, no "Region from
  this shape"; Filled Regions (HF3/HF4) cover areas that are not one shape.
  **Built by UP1** (2026-10-19): as-built contract in
  [`2026-10-18-up1-two-layer-fill-design.md`](../superpowers/specs/2026-10-18-up1-two-layer-fill-design.md).)*
- **D-A26** Click inside selects (lowest pick priority — lines win); boundary
  is snappable even when the outline is Invisible; HALO traces the boundary.
  *(BUILT by HF3: `shape()` = the filled path; `snap_engine._collect` walks
  the region's pieces; `HALO_AREA = True`. Guard: `TestSnapHaloPick`.)*

**Appearance & Fill Types**
- **D-A12** Two layers: background (Solid | None, default **None**) + foreground
  (pattern block | None) with colour (region colour by default, or "By block"),
  scale, opacity per layer. *(Amended 2026-10-05 by `linetypes.md` "Weight
  model" WM-8: "By block" is labelled **By Pattern (<colour>)**; a placement
  Colour override reaches fills/hatches, Weight/Linetype overrides do not
  reach tile strokes.)*
- **D-A14** Named **Fill Types** (project-scoped, shipped in the template); a
  region references a type, per-instance fields are overrides. Needs a types
  manager UI (mockup-gated).
- **D-A15** Blocks carry copies of the types + pattern blocks they use; on load
  missing ones are added, same-name → project wins. Deleting an in-use type or
  pattern block is refused ("used by N").
- **D-A17** Display Manager section-cut settings pick a Fill Type (one
  vocabulary). Dead Roof section column removed; roof section cut filed separately.

**Patterns**
- **D-A8** A hatch pattern **is a block** with a repeat tile (W×H, optional row
  shift) holding any 2D content. Today's built-ins become System > Hatches
  blocks. `.PAT` import = follow-up.
- **D-A9** Pattern-ness is a capability (has a tile), not a kind (System Blocks
  F3 holds). Block Editor "Pattern tile" toggle + editable tile frame + live
  repeat preview. Pickers list only tiled blocks; tiled blocks are not placeable
  as symbols.
- **D-A10** Each pattern block declares **Model** (real-size tile) or
  **Drafting** (printed-size tile). Regions add **Scale** only — no per-region
  angle. Angle comes solely from the pattern block definition; editing it
  updates every use. Drafting-in-model depends on SB1c view scale (falls back to
  real size until then).
- **D-A11** Pattern origin defaults to the container origin, stored per region;
  translates with the region, never rotates; boundary edits change only the
  clip. Rotating a region never rotates the pattern (Model and Drafting
  alike). **Exception (HF2 polish, ratified 2026-10-17):** a placed block
  instance's hatch turns and mirrors with the instance pose — nested poses
  compose (`RenderOp.pattern_frame`, carried by `RenderOp.mapped`) — but never
  scales (spacing stays Scale × Model/Drafting). Block Editor shapes, plain 2D
  shapes, wall / slab section cuts and future Filled Regions stay
  scene-aligned; no legacy flag or migration (old files re-display). "Pick
  pattern origin" nice-to-have.
- **D-A24** Shipped System > Hatches set + template Fill Types (see concept
  doc). The shipped set waits on SB1b; region/renderer/type work does not.

**Colour tokens ("Automatic")**
- **D-A18** The house picker gains **Automatic** (ink) and **Accent** for every
  drawn-item colour; Automatic is the new default for 2D geometry and text.
- **D-A19** Tokens resolve by **drawing surface**: canvas → current UI theme;
  paper/print/PDF/white previews → light-theme values (Automatic = black); B&W
  → black. Live theme switch repaints every token item without relaunch.
- **D-A20** Load migration: only known defaults (2D stroke `#ffffff`, default
  text ink) → Automatic; explicit colours kept. Forward-only format bump.
- **D-A21** Import: DXF ACI 7 and PDF pure black → Automatic; other colours literal.
  *(HF1 scope, user ruling 2026-10-17: underlays ignore per-entity colour and
  the PDF importer reads no colour, so HF1 covers Block Editor import only —
  DXF ACI 7 (direct or via BYLAYER) and geometry carrying no colour (every PDF
  line today) → Automatic. PDF pure-black detection lands with HF6's colour
  extraction.)*

**Import**
- **D-A22** PDF fills: underlay renders filled shapes (holes + paint order);
  Block Editor import → Filled Regions on an "Imported Solid" type + colour
  override; `fs` → region + outline; glyph text → one region per text run.
- **D-A23** PDF pattern hatches → plain lines. DXF SOLID → filled (fixes
  bowtie). DXF HATCH (Block Editor) → region + project-only pattern block
  converted from the HATCH definition (deduped) + "(imported)" Fill Type;
  unconvertible → lines + import-report note. Underlay → fill + pattern lines.

**Bars & guards**
- **D-A25** Perf bars: hover preview ≤ 50 ms/move on ~500 primitives (else
  compute on ≥150 ms pause) *(HF4: `tests/test_pick_region_perf.py`, grid /
  circles scenes ratified 2026-10-20; the 150 ms debounce engages when a window
  build exceeds `REGION_FINDER_DEBOUNCE_MS`)*; curve boundary ≤ 0.2 mm *(HF4:
  `REGION_FINDER_POLYLINE_MM`)*; PDF underlay with fills ≤
  1.5× stroke-only frame time; 200 hatched block instances ≤ 0.15 ms extra each (D-A35, amended);
  theme switch ≤ 500 ms for 1,000 token items.
- **D-A27** Guard set G1–G12 (ring, mixed boundary + gap, angle invariance,
  scale incl. PDF, pattern edit propagation, type restyle, library round-trip,
  Automatic colour per surface + live switch, migration, PDF import, DXF import,
  perf) — enumerated in the concept doc.

**HF2 deltas (ratified 2026-10-02, HF2 Phase 2 FP1 grill)**
- **D-A28** *(superseded 2026-10-02 by D-A39 — the code-level table is gone; frozen ids + aliases kept)* Until HF8, the legacy pattern names (`diagonal`, `cross_hatch`,
  `horizontal`, `concrete`) resolve to a code-level table of **built-in tile
  definitions** (read-only, frozen ids; the System Blocks `SYSTEM_DEFAULTS`
  idea). All Drafting at 3 mm printed spacing (`concrete` gets real
  geometry) + one Model test pattern (brick 215×65 stretcher bond — with
  10 mm joints the tile is 225×75, row shift 112.5). Shown in
  pattern pickers only — not in the Blocks browser, not openable. HF8 swaps
  their content for shipped System blocks; the table stays the fallback.
- **D-A29** A stored pattern reference is a **tile block id**; reads also
  accept a legacy name string and map it via an alias table to the built-in
  id (QSettings, DM overrides, 2D `fill.pattern` keep working; no migration
  pass, no format bump).
- **D-A30** *(amends D-A10's interim)* Until SB1c, Drafting tiles use the
  **paper viewport's real scale** on paper/PDF and an assumed **1:100** on
  the model canvas — **including the Block Editor** (user ruling
  2026-10-02, HF2 Task 4: the editor preview equals the placed block on a
  1:100 plan; a small symbol that needs a visible hatch uses a Model
  pattern; Drafting-in-model is the interim HF9 replaces).
- **D-A31** Pattern lines on paper/PDF use a new **"Hatch"** paper category
  line weight (default 0.13 mm, user-editable).
- **D-A32** Tile UI: Block Editor ribbon "Pattern tile" toggle → dashed canvas
  tile frame with W/H + row-shift grips, typed W/H/shift/Model·Drafting in the
  property panel when nothing is selected, live repeat preview (mockup-gated).
  Frame lower-left = block origin (0,0); seeded W×H = content extents from the
  origin (10×10 when empty). *(LT4, 2026-10-06: Pattern tile and the linetype
  toggle are mutually exclusive — [`linetypes.md`](linetypes.md) LT4-11b.)*
- **D-A33** Each cell stamps the tile block's full content offset by the tile
  step — no per-cell clip; only the host boundary clips.
- **D-A34** Tiled blocks are listed in the Blocks browser with a pattern badge;
  place / drag-to-canvas is refused (status message) at the lowest shared
  placement entry. Turning the tile on for a block placed as a symbol is
  refused with the instance count.
- **D-A35** G12 (HF2 bar): full-viewport frame time with 200 placed instances
  each holding a hatched closed shape costs ≤ 30 ms more than the same scene
  unfilled (≤ 0.15 ms per hatched instance — *amended 2026-10-02 by user
  ruling*: the original "≤ 1.5× unfilled" ratio got harder whenever plain
  blocks got faster; measured ~18–20 ms at ship; batching hatched instances is
  the filed follow-up if real projects lag); LOD tone
  (35 %) when a tile is < 2 device px or > 20k cells; the bench asserts its
  composition (pattern actually stamped).

- **D-A39** *(user ruling 2026-10-02, HF2 smoke — supersedes D-A28's
  code-level table)* **Blocks only.** The five patterns (Diagonal, Cross
  Hatch, Horizontal, Concrete, Brick) ship as real `.fpdb` blocks with the
  app (same frozen ids) and are copied into the Hatch patterns folder
  (D-A37) on first run when missing — never overwriting a user's edited
  copy; the folder is seeded once (a deleted shipped pattern is not
  re-seeded). Legacy names still alias to the frozen ids (D-A29). On project
  new / open, every pattern the project references (2D fills, block
  definitions, Display Manager category + instance section patterns) that
  isn't already a project definition is loaded from the folder — outside the
  undo history. Pickers list blocks only (project + folder). A reference that
  still can't resolve draws the tone (never vanish, D-A36). *As built:* the folder is re-seeded after System Settings Apply/OK when the Hatch patterns folder changes to a not-yet-seeded folder, and a Display Manager category pattern is loaded into the project when the dialog is accepted (OK), not on pick.
- **D-A36** *(ratified by the user 2026-10-02)* A pattern picker
  never rewrites a stored reference it can't resolve (deleted project tile,
  another project's id in QSettings): it shows no selection and keeps the
  stored ref unless the user explicitly picks another pattern; the renderer
  draws the tone for it ("never vanish", D-A39).

- **D-A37** *(user ruling 2026-10-02, HF2 smoke — absorbed in-session)* A
  **Hatch patterns folder** (System Settings › General › Data folder;
  default `<block library>/System/Hatches`) is the library source for
  patterns: pickers list the project's pattern blocks + every
  pattern block in that folder; picking a library pattern loads it into the
  project first, then stores its id (D-A29). Library `index.json` entries
  carry a `tile` flag. *(2026-10-10: the per-folder `index.json` is retired — listings read the `.fpdb` files; see [block-system.md "Library on disk"](block-system.md#library-on-disk-no-index-2026-10-10).)* (Closes the gap that a library-only pattern could
  never reach a picker — patterns load on place, and can't be placed.)
- **D-A38** *(user ruling 2026-10-02, amends D-A32)* Turning Pattern tile on
  seeds **Size = Model** (the tile is what you drew, in real mm); Drafting is
  an explicit choice for patterns authored at printed size.

## HF1 build design — colour tokens (approved 2026-10-17; **SHIPPED** 2026-10-18, merge `084b43e0`)

*Account 2026-10-18:* the text below states shipped behaviour. Where the
2026-10-17 proposal differed, the code won and the text was corrected (S1–S3
of the VC9 review are resolved in code and below).

The *what* is D-A18–D-A21 + D-A25's theme bar; Phase 2 rulings (2026-10-17):
Automatic = theme `ink` on canvas, `#000000` on paper; Accent = theme
`accent` on canvas, light-theme accent on paper; B&W → black for both.
Supersedes the mechanics sketch in the concept doc's HD6.

**Goal.** 2D geometry, text and Display Manager colours can say "Automatic" or
"Accent" and draw correctly on whatever surface they land on — light ink on a
dark canvas, dark ink on a light canvas, black on paper/PDF/print — and follow
a live theme switch without relaunch.

**Architecture & constraints.**
- *Value model.* A colour value stays a plain string: `#rrggbb` |
  `token:auto` | `token:accent` (constants in `constants.py`). A typed object
  was rejected — it ripples through every `to_dict` / `RenderOp` string field
  for no gain. Unknown `token:*` draws as Automatic; the warning is logged
  once per distinct value at resolve / paint time (`colour_tokens`), not at load.
- *One resolver.* Module `firepro3d/colour_tokens.py` (all of it; signatures
  live there, this list is the contract):
  - `is_token(v)`, `token_label(v)` (UI label, `None` for hex).
  - `normalize_colour(v, default)` — lower-cases hex, passes tokens **and the
    literal `""` unchanged**, anything else → `default` (replaces
    `stroke_style._hex`'s coerce-to-`#ffffff`).
  - `resolve_colour(v, alpha=None, item=None) -> QColor` — hex passes through;
    `""` → fully transparent `QColor(0,0,0,0)` whatever `alpha`; `None` →
    an invalid `QColor`.
  - `preview_colour(v)` — canvas colour for a placement rubber band; a `""`
    template previews as the theme accent (else it would be invisible).
  - `resolve_pen_brush(item, pen, brush, pen_src, brush_src, alpha)` — the
    per-paint pen / brush from stored colour strings (styles / widths kept).
  - `section_fill_colour(v, item)` — solid section-cut body colour, or `None`
    (unset, `""`, or a `hatch:` form → no solid body).
  - `paint_resolver(item)` — per-paint memo of `resolve_colour` (G12 perf);
    never outlive one paint.
- *Resolve per paint, never at set time.* A model item paints on the dark
  canvas and inside a paper viewport in the same frame, so a latched colour is
  wrong on one of them. Every consumer converts its stored string through
  `resolve_colour` at paint. **Latched consumers** (S1 resolved: gridline /
  marker pens, DM SVG tints, fitting symbols) cannot resolve at paint, so on
  **Full Colour** paper the paper pass re-resolves them on the paper surface
  and `restore_model_display` puts the canvas value back (fittings carry a
  `retinted` flag on their saved entry so only re-tinted symbols are
  re-latched).
- *Surface.* Paper when `paper_display.paper_pass_active()` is true (the
  `SheetViewport` window — screen, PDF export and print share it) or the
  item's scene carries `paints_on_paper = True` (`PaperScene`, the title-block
  editor / arrange white preview scenes); otherwise canvas. Paper colour mode
  B&W → black for both tokens. **Full Colour paper keeps authored colours**
  (S2 resolved): the paper pass leaves hex colours alone and tokens resolve on
  the paper surface (Automatic black, Accent the light-theme accent
  `#2F9E63`). The **Paper-tab category colours apply only in B&W / Custom**
  (the existing substitution for viewport content); **CUSTOM treats tokens as
  Full Colour** (Accent stays green). Items with no paper category
  (`TextItem`) get no upstream substitution, so under a B&W pass they honour
  it through `paper_display.paper_pass_color_mode()` (read by the resolver);
  paper-scene items (annotations) read the saved mode.
- *Theme bus.* `theme.py` has `theme_bus()`, a singleton QObject whose
  `changed` signal is emitted at the end of `MainWindow._apply_theme`.
  Listeners:
  - `MainWindow._on_theme_bus_changed`: first calls
    `elevation_manager.rebuild_all()` (elevation views project DM colours at
    rebuild and have no sprinkler system, so `refresh_token_latched` skips
    them), then walks every live scene (model, paper, Block Editors,
    elevation, schematic — `_live_scenes`), runs
    `display_manager.refresh_token_latched(scene)`, calls
    `on_theme_changed()` on items that define it (latched consumers: text
    default colour via `_apply_format`, DM SVG tints and gridline / marker
    pens when the stored value is a token) and `update()`s the scene.
  - `View3D._on_theme_changed`: requests a 3D rebuild when any roof or wall
    holds a token colour (the mesh colour is resolved at build).
  - `ui_kit.Swatch` (label colour + chip repaint) and `FontGroup`.
  Compiled block stroke pens keep the token string; the instance sets the pen
  colour per paint.

**Design decisions.**
- *Defaults → Automatic:* new 2D geometry (`default_style`, ctor /
  `from_dict` fallbacks), new model + Block Editor text (seed `#ffffff` today),
  new paper text (`TextAnnotationData.color` `#000000` today), Display Manager
  "2D Geometry" factory colour, `geometry_import` no-colour fallback.
- *Import (D-A21 HF1 scope):* `_aci_to_hex` path returns `token:auto` for ACI 7
  (direct or BYLAYER); underlay cache version bumped so cached geometry
  re-extracts.
- *Load migration (D-A20).* Project `SAVE_VERSION` 10 → 11; files < 11
  convert block-definition prims (stroke `#ffffff`, text `#ffffff`), paper
  annotation text `#000000` and the project Display Manager "2D Geometry"
  colour `#ffffff` → `token:auto`. `.fpdb` files carry no format version, so
  they gain a `colour_tokens: 1` marker; the same rule runs when it is absent
  (bundled nested definitions too) and saving writes it. QSettings Display
  Manager colour keys at `#ffffff` migrate once behind a settings marker. An
  explicit hex in a v11+ file is never touched. A text `color` of `""`
  (annotation or model text) in a < v11 file also becomes Automatic; v11+
  keeps `""` as "no colour". Shipped: `firepro3d/colour_migration.py`
  (payload-level, run before any `from_dict`; `SAVE_VERSION` = 11 in
  `model_space.py`; the Display Manager QSettings keys migrate once behind
  the `display/_migrated_hf1_auto` marker). The `.fpdb` marker is
  `colour_tokens: 1` (`COLOUR_TOKENS_MARK`), written on save. The shipped
  `system_blocks/Hatches/*.fpdb` stay **unmarked on disk** and re-migrate on
  every load (harmless: the rule is idempotent and an explicit hex is never
  touched).
- *Picker (D-A18, ui-design-system D6):* the signature is
  `pick_colour(initial, parent, context)` — no opt-in flags (owner:
  [ui-design-system.md D6](ui-design-system.md)). It shows an overline
  **Theme** row above Standard with two labelled chips (Automatic, Accent),
  each drawn in its current-canvas colour, plus No Fill, and returns `None`
  (cancel), `""`, a `token:*` string or a lower-case hex. Recents store hex
  only — a token pick (or `""`) is never pushed.
  *(Amended 2026-10-18, smoke ruling — ui-design-system D6 amendment: every
  picker call site shows the Theme row and No Fill; every property it edits
  accepts a token and `""` (draws nothing). Edited properties: 2D fill,
  text fill, **model / paper text colour (`""` allowed)**, Display Manager
  colour / fill / Section / paper tab, **room / floor / design-area DM
  `""`**, roof (resolved at the 3D build), **wall Colour (`_colour` store;
  the 3D mesh resolves it at build, and View3D rebuilds on the theme bus when
  a roof or wall holds a token)**, underlay colour, title-block border and
  field text, **title-block field fill**, and **elevation projection**
  (elevation proxies resolve per paint and are paper-aware, so a sheet plots
  the paper surface; S3 resolved — elevation does resolve). The former
  "FS visibility" entry is dropped: that dialog is dead and its deletion is
  filed.)*
  `ui_kit.Swatch` shows a token as its resolved colour with a small "A" corner
  badge and the label "Automatic" / "Accent".
- *Invariants (shipped).*
  - In 3D a roof or wall whose colour is `""` is an opacity-0, unpickable
    actor with a `None` edge slot, so the actor and edge lists stay
    index-parallel (section cut, pick map).
  - Display Manager fill `""` (no fill) is distinct from `None` (inherit /
    unset, which paints the default grey).
  - A Graphic Override fill on 2D geometry is display-only:
    `Geometry2DMixin._fill_value()` reads override-else-own, and `to_dict`
    never saves the override (Clear restores the own fill).
  - Paper surface rules (Full Colour keeps authored colours; Custom treats
    tokens as Full Colour; B&W pass reaches uncategorised items) are in the
    *Surface* bullet above — one home.
- *Known gaps (open, filed in `todo_open.md`).* (1) Elevation edge lines and
  opening voids / floor-slab masks are canvas-latched on sheets (plot canvas
  colours on paper). (2) Block-definition text prims with a flat
  `color == ""` are not migrated by `colour_migration`. (3) The Paper-tab
  Colour column has no UI cue that it is inactive in Full Colour (and the
  property panel shows the own fill while a Graphic Override is active).
- *Overlays (R5):* block-instance selection tints use the theme accent per
  paint; `selection_manipulator`'s `#63BE8B` lines are detect-failure
  fallbacks and stay with `# theme-exempt:`.
- *Hexguard (R8):* `tests/test_item_paint_hexguard.py` scans a listed set of
  item paint modules for `QColor("#…")` literals; one passes only with
  `# theme-exempt: <reason>` on the same line.

**Acceptance criteria.** AC1–AC10 of the HF1 Phase 2 definition, with AC7 per
the D-A21 HF1 scope above.

**Verification checklist (VC3).**
- G8a shown view, token line + text, dark and light canvas → sampled pixel =
  theme ink; G8b `export_pdf` / paper pass → black (Full Colour), accent item
  `#2F9E63`, B&W black; G8c live `_apply_theme` dark → light flips the pixel,
  text default colour and Swatch label with no reload.
- G9 (colour half): v10 project + un-marked `.fpdb` with `#ffffff` stroke,
  `#ffffff` block text, `#000000` paper text, explicit `#ff0000` → first three
  Automatic, red kept; re-save writes v11 / marker; second load converts
  nothing.
- Round-trip: token survives save/load, `normalize_style`, copy/paste, undo.
- Import: DXF ACI 7 + BYLAYER-7 entity → Automatic; other ACI literal; PDF
  line → Automatic.
- Picker: Automatic returns `token:auto`; recents unchanged.
- Hexguard: a raw `QColor("#hex")` added to a guarded module fails.
- G12 theme bar: 1,000 token items, switch → flushed repaint ≤ 500 ms
  (`perf`, own process; bench shapes confirmed with the user before the bench).

## HF3 build design — Filled Region primitive (approved 2026-10-20; **SHIPPED** 2026-10-20, merge `66880197`)

The *how* is owned by
[`2026-10-20-hf3-filled-region-design.md`](../superpowers/specs/2026-10-20-hf3-filled-region-design.md)
(status `current`): rulings R1–R15 / D1–D2, the `FilledRegionItem` record
(`{"type": "draw_filled_region", "loops": [[<shape record>, …], …], "fill": …,
"outline": …}` — loops of primitive records, superseding HD2's `seg` schema),
`curve_chain.close_loops`, the 10th-primitive registry table, the modify-tool
delegation and the guard table (`tests/test_filled_region.py`,
`tests/test_curve_chain.py`). Known gaps filed in `todo_open.md`: linetype-tile
Fill unverified, `main` family / element rows, second-phase refusal clicks,
Join adopting `curve_chain`.

## HF4 build design — Pick-point region finder (approved 2026-10-20; **SHIPPED** 2026-10-20, merge `bb7074b8`)

The *how* is owned by
[`2026-10-20-hf4-pick-region-design.md`](../superpowers/specs/2026-10-20-hf4-pick-region-design.md)
(status `current`): rulings AC1–AC9, `region_finder.Arrangement` (flatten at
`REGION_FINDER_SAGITTA_MM` with the `REGION_FINDER_MIN_CHORD_MM` floor, bucketed
split, weld, prune with open ends, half-edge face walk, one-level islands,
boundary nudge) and `rebuild` (exact pieces for `FilledRegionItem.from_pieces`
via `geometry_2d.bezier_sub`), the `pick_region` mode in `model_space.py`
(cached windowed arrangement, doubling window, shared `_commit_region` tail,
debounce fallback) and the hover overlay in `model_view.drawForeground`; the
guard table (`tests/test_region_finder.py`, `tests/test_pick_region_mode.py`,
`tests/test_pick_region_perf.py`). Known gaps filed in `todo_open.md`: AC3 /
D-A25 debounce / AC8 ellipse-arc guards, per-move bounds hoist, dim-HUD label
rect.

## Cross-spec reconciliation (to amend when the build lands — Rule A)

- `2d-geometry.md` fill section → `fill.pattern` is a tile id linked here (**done, HF2 Account**); per-item fill dissolved (D-A16) — **D-A16 reversed 2026-10-18**: the section instead gained the two-layer shape fill with UP1 (**done, UP1 Account** — pointer + `fill_layers` replace the single-fill description).
- `ui-design-system.md` D6 → picker gains token choices (D-A18) (**done, HF1 Account** — D6 colour block + amendment).
- `docs/architecture/theming.md` → element colours may be tokens resolved by surface (D-A19) (**done, HF1 Account** — theme bus pointer).
- `block-system.md` → tile capability + pattern refs in the registry (D-A9, D-A34, D-A39: **done, HF2 Account** — "Pattern-tile capability (HF2)"); Fill Type bundling (D-A15) — pending.
- `linetypes.md` → `RenderOp` exists (`render_op.py`); LT3 extends it (**done, HF2 Account**).
- `settings-dialog.md` §4.5b → Hatch patterns folder row + seeded key (**done, HF2**).
- `docs/architecture/display-system.md` → section-cut hatching links here (**done, HF2 Account**).
- `underlay-workflow.md` §10.5 → wrongly says DXF HATCH is implemented (it imports nothing); §16.3 → fills (D-A22/23).
- `scene-io.md` §4 + `2d-geometry.md` → legacy HatchItem is discarded, not migrated (H12: **done, HF2 Account**); format bump (D-A20) (**done, HF1 Account** — `scene-io.md` SAVE_VERSION 11 pointer).
- System Blocks concept → add the Hatches series (D-A24).
