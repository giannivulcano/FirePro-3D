---
status: partial          # §1–§4 = as-built at 3a95a3f (orphan-gate review 2026-10-01); as-intended contract = "Design Decisions" (pending the 2026-10-01 concept grill — nothing below is ratified until stamped)
last-verified: 2026-10-01
verified-commit: 3a95a3f
applies-to:
  - firepro3d/hatch_patterns.py
  - firepro3d/graphics/hatch_patterns/
  - firepro3d/displayable_item.py   # draw_fill / draw_section_hatch / _apply_hatch_pattern only (the mixin's other state is owned elsewhere)
source-tasks: ["Concept: region Fill/Hatch tool + user-definable hatch patterns as blocks + theme-Automatic colours (2026-10-01)"]
---

# Hatch & Fill — Design Spec (current behaviour + divergences)

> **Orphan-gate spec (2026-10-01).** Forged because `hatch_patterns.py` had no
> governing spec. §1–§4 record what the code does *today*. Per-item fill
> *state* on 2D primitives stays owned by [`2d-geometry.md`](2d-geometry.md)
> (fill section); section-cut hatch *wiring* stays owned by the Display Manager
> + [`wall-room-floor-system.md`](wall-room-floor-system.md). This spec owns the
> **pattern registry and the fill/hatch renderer**.

## 1. As-built: pattern registry (`hatch_patterns.py`)

- Two sources merged into `PATTERN_NAMES` at import: Qt built-in brush styles
  (`diagonal`, `cross_hatch`, `horizontal`) and SVG files discovered in
  `graphics/hatch_patterns/*.svg` (`concrete`, `diagonal`). A built-in name
  shadows an SVG of the same stem.
- SVG parsing reads `<line>` elements and the viewBox only (no `<path>`,
  `<circle>`, transforms, stroke width).
- Unknown names fall back silently (`make_hatch_brush` → BDiag pattern;
  `draw_svg_hatch` → draws nothing).

## 2. As-built: renderer (`displayable_item.py`)

- `draw_fill(painter, closed_path, scene, fill_type, pattern, colour, alpha)` —
  `fill_type ∈ {none, solid, hatch}`; solid = brush under IntersectClip; hatch →
  `_apply_hatch_pattern`.
- `draw_section_hatch(...)` — solid section fill then `_apply_hatch_pattern`
  (walls, floor slabs when section-cut).
- `_apply_hatch_pattern` — SVG patterns tile vector lines clipped to the path;
  built-ins use a Qt pattern brush with a `setTransform` scale.
- Fill is always **one item's own closed path** (`get_closed_path()`); there is
  no multi-item boundary, no island detection, no angle or origin.

## 3. As-built: data path

| Hop | Where | Key |
|---|---|---|
| 2D item state | `geometry_2d.Geometry2DMixin` | `fill_type`, `fill_pattern`, `fill_opacity` (0..1), colour in `_display_fill_color` |
| Serialize | `_geom2d_to_dict` / `_from_dict` | `"fill": {type, pattern, color, opacity}` (omitted when none) |
| Block compile | `block_definition.BlockDefinition._compile` | `prim["fill"]` **ignored** — ops are `(pen, NoBrush, path)` |
| Section (DM) | `display_manager` | `section`, `section_pattern`, `section_scale`; DM `fill` colour uses a `"hatch:#rrggbb"` prefix |
| Paper | `paper_display` | pens remapped; 2D fill colour not remapped |
| Import | `pdf_import_worker`, `dxf_import_worker` | no fill emitted (see D-ledger) |

Three vocabularies name the same concept (`fill_pattern` / `section_pattern` /
DM `"hatch:"` prefix); opacity units differ (0..1 vs 0..100).

## 4. Divergences ledger (as-built defects, probed 2026-10-01)

| # | Divergence | Evidence |
|---|---|---|
| H1 | Fills vanish in placed blocks — `_compile` ignores `prim["fill"]`; with loose model geometry clean-dropped (containment C8), no saved project shows a 2D fill outside the Block Editor | probe: solid red rect → compiled op `NoBrush` |
| H2 | Built-in pattern scale is a no-op — Qt pattern brushes are cosmetic unless `QPainter.RenderHint.NonCosmeticBrushPatterns` (set nowhere); hatch is a fixed 8 device-px period on screen, paper and PDF | offscreen QImage probe |
| H3 | `concrete` renders nothing (its SVG has 0 `<line>` elements); the swatch shows a diagonal fallback (preview ≠ render) | parser probe |
| H4 | `diagonal.svg` is dead (shadowed by the built-in) | registry probe |
| H5 | `draw_svg_hatch` uses ReplaceClip (`setClipPath` default) — the paper-viewport bleed class `paper-space.md §6.2` fixed for the built-in path | code read |
| H6 | Tile size reads `scene.views()[0]` (the vestigial view) — world 24 mm in practice, not screen- or paper-aware | already filed (vestigial-view scale todo) |
| H7 | Fill undo ordering — context menus (two duplicate copies) + ribbon Graphic Override call `push_undo_state()` before `set_property`; redo loses the fill | probe: redo → none |
| H8 | Hatch drawn at the solid opacity with no UI to change it | code read |
| H9 | Dead code: `refresh_patterns`, `is_builtin`, `make_hatch_tile`, `DEFAULT_PATTERNS`, `wall._draw_hatch`, `MainWindow._build_fill_group`, `annotations._rebuild_path_from_elements` | whole-repo grep |
| H10 | Roof exposes DM section pattern/colour that `roof.py` never draws | code read |
| H11 | No angle / origin anchoring — tiles start at the clip bbox, so the pattern swims when the shape moves | code read |
| H12 | `2d-geometry.md` + `scene-io.md §4` still describe a legacy HatchItem *migration*; code discards it (containment D6) | doc vs code |

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
  scale, opacity per layer.
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
  1.5× stroke-only frame time; 200 hatched block instances ≤ 1.5× unfilled;
  theme switch ≤ 500 ms for 1,000 token items.
- **D-A27** Guard set G1–G12 (ring, mixed boundary + gap, angle invariance,
  scale incl. PDF, pattern edit propagation, type restyle, library round-trip,
  Automatic colour per surface + live switch, migration, PDF import, DXF import,
  perf) — enumerated in the concept doc.

**HF2 deltas (ratified 2026-10-02, HF2 Phase 2 FP1 grill)**
- **D-A28** Until HF8, the legacy pattern names (`diagonal`, `cross_hatch`,
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
  the model canvas.
- **D-A31** Pattern lines on paper/PDF use a new **"Hatch"** paper category
  line weight (default 0.13 mm, user-editable).
- **D-A32** Tile UI: Block Editor ribbon "Pattern tile" toggle → dashed canvas
  tile frame with W/H + row-shift grips, typed W/H/shift/Model·Drafting in the
  property panel when nothing is selected, live repeat preview (mockup-gated).
  Frame lower-left = block origin (0,0); seeded W×H = content extents from the
  origin (10×10 when empty).
- **D-A33** Each cell stamps the tile block's full content offset by the tile
  step — no per-cell clip; only the host boundary clips.
- **D-A34** Tiled blocks are listed in the Blocks browser with a pattern badge;
  place / drag-to-canvas is refused (status message) at the lowest shared
  placement entry. Turning the tile on for a block placed as a symbol is
  refused with the instance count.
- **D-A35** G12 (HF2 bar): full-viewport frame time with 200 placed instances
  each holding a hatched closed shape ≤ 1.5× the same scene unfilled; LOD tone
  (35 %) when a tile is < 2 device px or > 20k cells; the bench asserts its
  composition (pattern actually stamped).

## Cross-spec reconciliation (to amend when the build lands — Rule A)

- `2d-geometry.md` fill section → per-item fill dissolved (D-A16); link here.
- `ui-design-system.md` D6 → picker gains token choices (D-A18).
- `docs/architecture/theming.md` → element colours may be tokens resolved by surface (D-A19).
- `block-system.md` → tile capability, type/pattern bundling (D-A9, D-A15).
- `underlay-workflow.md` §10.5 → wrongly says DXF HATCH is implemented (it imports nothing); §16.3 → fills (D-A22/23).
- `scene-io.md` §4 + `2d-geometry.md` → legacy HatchItem is discarded, not migrated (H12); format bump (D-A20).
- System Blocks concept → add the Hatches series (D-A24).
