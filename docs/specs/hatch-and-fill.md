---
status: partial          # HF2 BUILT (branch hf2-pattern-renderer): tiled pattern renderer, pattern-tile blocks + Block Editor tile authoring, Hatch patterns folder, blocks-only shipped patterns (D-A28–D-A39). UNBUILT: Filled Regions, Fill Types (+ template set), colour tokens, PDF/DXF fill import (HF1, HF3–HF9). §1–§4 = as-built at 53e1773
last-verified: 2026-10-06  # LT4 Account: §2 tile frame → TileFrame on the shared capability_frame.CapabilityFrameItem base (this spec's home; TileFrameItem / TILE_FRAME_TAG aliases, tag "capability_frame"), tile rows via capability_panel; applies-to + capability_frame.py; prior Weight model design: D-A12 "By block" → By Pattern pointer (WM-8); prior LT3 Account: Folder scan bullet → capability_folder.scan (tile flag) + LT3-9 pointer; prior 2026-10-03 HF2 Account: §1–§4 rewritten to the HF2 code; ledger H1–H6/H11/H12 resolved, H9 partly; prior 2026-10-01 orphan-gate review at 3a95a3f
verified-commit: b9b1094   # LT4 Account (feat/lt4-repeat-authoring; capability frame only); prior 489dcc2 Weight model pointer; prior be7c88a LT3 Account (folder-scan relocation only); prior 53e1773
applies-to:
  - firepro3d/hatch_patterns.py     # pattern registry: frozen ids, legacy alias, folder seed + scan entry (library_patterns), picker source, project pattern load
  - firepro3d/capability_folder.py  # shared capability-folder scan — the "tile" side (the "repeat" side is owned by linetypes.md LT3)
  - firepro3d/hatch_render.py       # renderer: paint_fill / stamp_lattice / paint_swatch
  - firepro3d/render_op.py          # RenderOp type — shared with linetypes (LT3 extends it); block compile semantics owned by block-system.md
  - firepro3d/capability_frame.py   # Block Editor capability frame base (CapabilityFrameItem, tag, frame_for) — shared with linetypes.md LT4 (RepeatFrame), owned here
  - firepro3d/tile_frame.py         # Block Editor pattern-tile frame (TileFrame) + tile panel rows
  - firepro3d/system_blocks/Hatches/  # shipped pattern .fpdb files + index.json (D-A39)
  - firepro3d/displayable_item.py   # draw_fill / draw_section_hatch adapters only (the mixin's other state is owned elsewhere)
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
  startup (`main.py`) and after System Settings Apply/OK.
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
  patterns not yet in the project, with unique labels. `picker_exclude` drops
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
  scale, line_width_px, to_scene)`** — the one entry point: IntersectClip to
  the boundary (H5), optional solid background, then the tile lattice. With
  `to_scene`, the painter is re-based to **scene axes** so a rotated item or
  block pose never rotates the pattern (D-A11); `origin` is in scene coords,
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
- **Adapters** (`displayable_item.py`): `draw_fill` (per-item 2D fill —
  solid → background, hatch → tile, both at the item alpha; HF3 retires it)
  and `draw_section_hatch` (walls / floor slabs section cut: section fill +
  pattern + scale) are thin `paint_fill` wrappers passing the item's
  `sceneTransform()` as `to_scene`.
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
- Fill is still **one item's own closed path** (`get_closed_path()`); no
  multi-item boundary or island detection until Filled Regions (HF3+).

## 3. As-built: data path

| Hop | Where | Key |
|---|---|---|
| 2D item state | `geometry_2d.Geometry2DMixin` | `fill_type`, `fill_pattern` (tile block id; legacy names canonicalised on load), `fill_opacity` (0..1), colour in `_display_fill_color` |
| Serialize | `_geom2d_to_dict` / `_from_dict` | `"fill": {type, pattern, color, opacity}` (omitted when none) |
| Block compile | `block_definition._fill_ops` → `RenderOp` | primitive fill → a `fill` / `pattern` op before its stroke (origin = container origin); painted by `BlockInstance` via `paint_fill` with the pose — compile contract → [`block-system.md`](block-system.md) |
| Block tile | `BlockDefinition.tile` | `{w, h, row_shift, size: model\|drafting}` or None — owned by `block-system.md` |
| Section (DM) | `display_manager` | `section`, `section_pattern` (tile ref; factory defaults still legacy `"diagonal"`, read via alias), `section_scale`; DM `fill` colour still uses a `"hatch:#rrggbb"` prefix |
| Paper | `paper_display` | pens remapped; pattern lines use the "Hatch" category weight (weight-only row); 2D fill colour not remapped |
| Import | `pdf_import_worker`, `dxf_import_worker` | no fill emitted (unchanged by HF2; D-A22/D-A23 unbuilt) |

`fill_pattern` and `section_pattern` now share one vocabulary (tile refs);
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
| H7 | Fill undo ordering — context menus + ribbon Graphic Override call `push_undo_state()` before `set_property`; redo loses the fill | probe: redo → none | **OPEN** (`entity_context_menu` still pushes first at 53e1773) |
| H8 | Hatch drawn at the solid opacity with no UI to change it | code read | **OPEN** (Fill Opacity row is solid-only; `draw_fill` uses the item alpha for both) |
| H9 | Dead code: `refresh_patterns`, `is_builtin`, `make_hatch_tile`, `DEFAULT_PATTERNS`, `wall._draw_hatch`, `MainWindow._build_fill_group`, `annotations._rebuild_path_from_elements` | whole-repo grep | **PARTLY RESOLVED** — the four `hatch_patterns` names gone `59a05b4`, `_build_fill_group` deleted `9538ab4`; **still dead**: `wall._draw_hatch`, `annotations._rebuild_path_from_elements` |
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
  never loose in Model Space (containment C1 unchanged).
- **D-A3** v1 creation: **Pick point** (primary) + **Select objects**
  (fallback). Sketch / Edit Boundary deferred.
- **D-A4** A pick fills exactly the clicked connected face; anything inside any
  closed island stays empty (no island-style option).
- **D-A5** Boundary candidates: visible 2D primitives + block geometry in the
  same container. Ignored: text, other regions, reference/construction lines,
  viewport contents and frames, hidden items.
- **D-A6** Gaps ≤ 1 mm (container units) count as closed; otherwise hover shows
  a red "Not enclosed" hint and nothing is created (leak highlight nice-to-have).
- **D-A7** Own optional outline (line style, default Invisible). Authored
  regions draw behind other geometry; manual draw order deferred. Exception:
  imported regions keep source paint order (D-A22).
- **D-A13** Modify tools: Move/Copy/Array/Rotate/Mirror/Scale transform the
  boundary (pattern never rotates/mirrors/resizes; origin translates); Offset,
  Trim/Extend/Break/Fillet refused; Explode → boundary loops as plain primitives;
  no grips in v1; copy/paste between Block Editor ↔ Paper allowed.
- **D-A16** Per-item fill on closed primitives is **dissolved** — every fill is
  a Filled Region; "fill this shape" creates a region from it. Existing
  `prim["fill"]` in block definitions migrates on load to region + shape.
- **D-A26** Click inside selects (lowest pick priority — lines win); boundary
  is snappable even when the outline is Invisible; HALO traces the boundary.

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
  clip. Rotating a region or a containing block instance never rotates the
  pattern (Model and Drafting alike). "Pick pattern origin" nice-to-have.
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
  compute on ≥150 ms pause); curve boundary ≤ 0.2 mm; PDF underlay with fills ≤
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
  carry a `tile` flag. (Closes the gap that a library-only pattern could
  never reach a picker — patterns load on place, and can't be placed.)
- **D-A38** *(user ruling 2026-10-02, amends D-A32)* Turning Pattern tile on
  seeds **Size = Model** (the tile is what you drew, in real mm); Drafting is
  an explicit choice for patterns authored at printed size.

## Cross-spec reconciliation (to amend when the build lands — Rule A)

- `2d-geometry.md` fill section → `fill.pattern` is a tile id linked here (**done, HF2 Account**); per-item fill dissolved (D-A16) — pending HF3.
- `ui-design-system.md` D6 → picker gains token choices (D-A18).
- `docs/architecture/theming.md` → element colours may be tokens resolved by surface (D-A19).
- `block-system.md` → tile capability + pattern refs in the registry (D-A9, D-A34, D-A39: **done, HF2 Account** — "Pattern-tile capability (HF2)"); Fill Type bundling (D-A15) — pending.
- `linetypes.md` → `RenderOp` exists (`render_op.py`); LT3 extends it (**done, HF2 Account**).
- `settings-dialog.md` §4.5b → Hatch patterns folder row + seeded key (**done, HF2**).
- `docs/architecture/display-system.md` → section-cut hatching links here (**done, HF2 Account**).
- `underlay-workflow.md` §10.5 → wrongly says DXF HATCH is implemented (it imports nothing); §16.3 → fills (D-A22/23).
- `scene-io.md` §4 + `2d-geometry.md` → legacy HatchItem is discarded, not migrated (H12: **done, HF2 Account**); format bump (D-A20) — pending.
- System Blocks concept → add the Hatches series (D-A24).
