---
status: partial          # LT1 BUILT 2026-10-04 (project weights, Blocks paper category, canvas mapping, Thin Lines); LT2 BUILT 2026-10-04 (style record, copy_style, per-op weights, Model Blocks row, rename aliases); LT3 RATIFIED 2026-10-04 (proposal, unbuilt); LT4–LT8 unbuilt. D-L1–D-L23 ratified in the 2026-10-02 concept grill (Q1–Q23); how = docs/superpowers/specs/2026-10-02-linetypes-concept-design.md (LD1–LD7)
last-verified: 2026-10-04  # paper-outline-weight audit (paper_display.py touched; no linetypes claim changed); prior LT2 Account (LT2 section reconciled to as-built: H-a/H-b/H-c/H-e/H-g refinements, guards); prior LT1 Account d031637
verified-commit: 4c799ee   # audit only; prior 0056b5c
applies-to:               # LT1 + LT2 seams (built) + planned modules (LT3+)
  - firepro3d/paper_display.py       # LT1: project weight table, canvas mapping, Thin Lines, Blocks paper category; LT2: Model Blocks weight, rename aliases, apply_project_weights, paper_pass_active
  - firepro3d/block_instance.py      # LT1/LT2: paper pen hooks + per-op weight resolution only (rest owned by block-system.md)
  - firepro3d/display_manager.py     # LT1/LT2: Line Weights tab, weight in-use / rename / aliases, Model "Blocks" row only (rest owned by display-system)
  - firepro3d/stroke_style.py        # LT2: stroke style record, migration, copy_style, canvas weight resolution (LT3: cascade)
  - firepro3d/render_op.py           # LT2: RenderOp.weight only (type owned by hatch-and-fill.md)
  - firepro3d/path_walk.py           # planned — arc-length walker + axis phase
  - firepro3d/linetype_render.py     # planned — expansion renderer
  - firepro3d/capability_folder.py   # planned (LT3) — shared tile/repeat folder scan
  - firepro3d/geometry_2d.py         # Geometry2DMixin style record only (the rest is owned by 2d-geometry.md)
source-tasks: ["Concept: user-definable linetypes as blocks — end types, dash-dot spacing + configuration, lineweight at definition vs host level (2026-10-02)"]
---

# Linetypes — Design Spec (as-intended)

> **Greenfield spec (2026-10-02).** Forged by the linetype concept run (orphan
> gate, greenfield path). No linetype code exists; today every stroke is a
> plain `QPen` whose width is a cosmetic px (see *As-built baseline*). This
> spec owns **linetype + end-type definitions, the stroke style record, the
> weight/linetype cascade and the stroke renderer contract**. Block storage,
> capabilities and the registry stay owned by [`block-system.md`](block-system.md);
> named weights' factory values by `paper_display.FACTORY_LINE_WEIGHTS`;
> primitives' geometry by [`2d-geometry.md`](2d-geometry.md).

## Goal

Users author **linetypes** and **end types** as blocks and apply them to 2D
primitives, with a weight model that works inside a definition, at the use
site and through nested placements — so that all system geometry (gridlines,
pipes, leaders) can eventually be built from primitives.

## Motivation

Fire-protection drawings depend on line meaning (Hidden, Center, Fire-FP,
Sprinkler-S, Existing, Drain). Today there are three unrelated dash
vocabularies (text-border enum, Qt pen styles, the gridline's explicit
pattern), blocks plot at cosmetic width with no paper weight, and the
gridline/pipe line work is bespoke. The end goal (user, 2026-10-02): build
system geometry such as a gridline (primary line + two leaders of definable
length + toggleable bubble end caps) from primitives via System Blocks.

## As-built baseline (2026-10-02, 18df05d)

- Primitive weight = `pen().widthF()` in cosmetic px, serialized as
  `"lineweight"` in each primitive class's own `to_dict` (default
  `constants.DEFAULT_GEOMETRY_LINEWEIGHT`); no dash, cap or linetype key.
- `BlockInstance.paint` forces `setCosmetic(True)` on every op pen;
  `_display_pen_color` returns None.
- `paper_display._category_for_item` has no `BlockInstance` case → block
  linework plots at its cosmetic width on paper/PDF.
- Named weights (`paper_display.LineWeightDef`) live in QSettings only.
- No arc-length walker exists (`pointAtPercent`/`percentAtLength` unused).
- `block_registry.nested_ids` scans only `block_instance` records.
- Pipe `"Line Type"` is an enum (Branch/Main) choosing a draw width.

> **Since HF2 (2026-10-03, `53e1773`):** the typed `RenderOp` now exists
> (`render_op.py`; compile contract → `block-system.md` "Pattern-tile capability (HF2)") — LT3's
> `StrokeOp` extends its `stroke` kind rather than adding a type; and
> `block_registry.referenced_ids` (nested records + pattern refs) now exists — LD5 adds
> linetype / end-type refs to it.

## Design Decisions (as-intended — ratified 2026-10-02 grill Q1–Q23)

### Definitions

- **D-L1 Content.** A linetype's repeat unit holds dashes, gaps, dots and
  embedded symbols/text, authored in the Block Editor. No fills, hatches or
  nested blocks in the unit.
- **D-L2 Consumers.** Core scope = 2D primitives (in block definitions and on
  paper). Region outlines, text border, system items' fixed dashes, pipes =
  follow-ups (pipes per D-L22).
- **D-L3 Sizing.** Per-linetype flag: **Drafting** (printed mm, default) |
  **Model** (real-world mm). Drafting in model views needs `PlanView.scale`
  (System Blocks SB1c) and falls back to real size until then (mirrors hatch
  D-A10). *(Amended by LT3-5: the plan-canvas fallback is the project
  `drawing_scale`, not real size; the Block Editor stays real size.)*
- **D-L12 Library.** Linetypes and end types are ordinary blocks with a
  capability (`repeat` / `end`; no kind field — hatch D-A9 / System Blocks F3).
  Project registry + libraries; System > Linetypes and System > End Types
  series (read-only, customise by Duplicate); `.fpdb` bundles them with
  dependents; delete refused while used ("used by N"); pickers list only
  capable blocks; capable blocks are not placeable as symbols.
- **D-L20 Authoring.** Draw inside a repeat frame (frame length = period) in
  the Block Editor, plus a property-panel numeric list (Dash / Gap / Dot)
  editing the same block; symbols by drawing only; live preview on a sample
  line and polyline.

### Weight and linetype cascade

- **D-L4 Definition vs use.** The definition authors a weight per component
  (dash, each symbol). A line's Weight = **By Linetype** | named weight |
  **By Block**. A named weight replaces the dash weight only; symbols keep
  their authored weight. Editing the definition updates By Linetype lines only.
- **D-L5 Host (By Block).** Only By Block primitives follow the host. Every
  placement and every nested record has a Weight (default = the Display
  Manager "Blocks" category weight). By Block inside By Block chains outward.
  Authored named weights never change.
- **D-L6 Linetype By Block.** Linetype = named | By Block, same rule; placement
  and nested record carry a Linetype (default Continuous).
- **D-L17 Top-level By Block** resolves to the surface's category: "Blocks"
  in model, "Construction" on paper.
- **D-L18 New primitives** use a sticky **current** Linetype + Weight
  (ribbon/panel), initially Continuous + By Block. Picking a linetype does
  not change the current weight.
- **D-L19 Colour.** Unit and end-block content defaults to **By Line** (the
  using line's ColourValue); authors may set explicit component colours; B&W
  forces black.

### Ends

- **D-L7 Ownership.** The linetype sets default start/finish end types; each
  line overrides per end (By Linetype | explicit). Closed shapes draw no ends.
- **D-L8 Catalog.** Every end type is a block — caps (Flat, Round, Square)
  included; System set + user-drawn.
- **D-L8b Sizing.** Per end block: **Fixed** (printed mm) | **Weight-relative**
  (units of line weight). System caps ship weight-relative; arrows, ticks, dots
  ship Fixed.
- **D-L10 End data.** End blocks may hold `@[key]` attribute text (System
  Blocks F3) resolved from the placement that owns the line; Fixed sizing;
  `keep_upright`; missing source → `?`. Repeat units stay static.
- **D-L11 Bindable.** Linetype, Weight, Start End, Finish End and a per-end
  **Visible** flag are addressable properties so a future instance-parameter
  system can drive them. Instance parameters themselves are a separate design.

### Layout along the path

- **D-L9 Phase (seamless).** Phase is axis-anchored: a straight piece's phase =
  position along its infinite axis, measured from the projection of the
  block-definition origin (or sheet origin), direction-independent. Collinear
  pieces — touching or gapped, drawn either way — read as one line; trim/split
  never moves surviving dashes. No stretch-to-fit.
- **D-L9b Per segment.** Each polyline segment follows the same axis rule;
  arcs/circles anchor at their circle's 0°; ellipses at their 0°; splines from
  their start.
- **D-L15 Symbols.** A symbol occurrence draws only if its whole footprint fits
  on one straight piece and clears end blocks; otherwise it becomes plain dash
  (never clipped, bent or shifted). Text stays upright; symbols follow the
  tangent on curves.

### Surfaces, portability, migration

- **D-L13 Project weights.** The named-weight table is project-scoped (`.fpd`);
  QSettings is the template for new projects; `.fpdb` bundles the names+values
  it uses; on import the project wins and missing names are added.
- **D-L14 Canvas.** Each named weight maps to a constant screen width (the
  existing mm→px underlay hint); a **Thin Lines** toggle draws all 1 px;
  paper/PDF are true mm.
- **D-L16 Import** (follow-ups): DXF LTYPE → project linetype blocks + DXF
  lineweight → nearest named weight; PDF dash arrays/caps → linetypes on Block
  Editor import, underlays draw dashes as authored.
- **D-L17a Migration.** Legacy primitives load as Continuous + By Block with
  the linetype's default ends; the px width is dropped; format bump. Paper
  linework prints exactly as before (via D-L17).
- **D-L21 Performance.** Bench: 2,000 linetyped segments (1,500 Center/Hidden +
  500 Fire-FP) + 400 end blocks → pan/zoom paint ≤ 16 ms/frame and ≤ 1.5× the
  same scene Continuous. Screen-only LOD: period < 2 px → continuous, symbols
  skipped. Paper/PDF always exact. Bench confirmed with the user before any
  perf fix.
- **D-L22 Pipes.** Pipes adopt linetypes: a pipe is a Feature whose plan block
  is one line in a piping linetype; the "Line Type" enum becomes a Linetype
  property from System > Linetypes > Piping; Main's weight comes from its
  linetype; the plan-block line is Linetype By Block + Weight By Linetype.
  Pipe-as-linear-Feature is its own design task.
- **D-L23 Defaults.** (a) strokes inside repeat units/end blocks are always
  Continuous (no recursion) — and, per LT3-9, so are pattern-tile strokes when
  stamped as a hatch; (b) explode, copy, mirror and modify tools keep
  Linetype/Weight/ends — new free ends from break/trim get By Linetype ends;
  (c) mirror flips end blocks, text stays upright; (d) closed shapes never
  draw ends; (e) a missing linetype/end block draws Continuous/Flat plus a
  visible warning badge, never nothing.

## LT1 — Project weights, Blocks paper category, canvas mapping, Thin Lines (ratified 2026-10-03)

> Slice contract for LT1 (concept LD4). The *what* was settled in the LT1
> Phase-2 grill (Q1–Q13) and the *how* (H1–H10) was approved as one batch,
> both on 2026-10-03. **BUILT 2026-10-04** on `feat/lt1-project-weights`
> (verified `d031637`); every P4 probe passed and every H item below is locked
> as-built. Build-time refinements, each user-ratified: H3's signal, LT1-5's
> model-plan texts + rename-onto-referenced refusal, and LT1-8's paper-pass
> suspension.

### What (grill Q1–Q13)

- **LT1-1 Canvas blocks unchanged.** On the model canvas, block linework keeps
  its authored cosmetic px until LT2 migrates primitives to By Block. The
  Model-tab "Blocks" row, with its weight cell, lands with LT2; LT1 adds no
  Model-tab row.
- **LT1-2 Paper "Blocks" category** (Paper tab only): weight / colour /
  visibility / opacity, **no fill column**, factory weight **Light**. Every
  block stroke op (nested included) plots non-cosmetic at that weight in true
  mm, whatever its authored px (D-L17's By Block → Blocks, applied early on
  paper). B&W / Custom force the category colour onto stroke **and** text ops;
  Full Color keeps authored colours. Fill / pattern ops stay under the hatch
  rules. Absorbs todo L33 (white-pen blocks invisible on sheets).
  *(LT2-5 refines: from LT2 only By Block ops take the category weight;
  named-weight ops plot at their own mm.)*
- **LT1-3 Project weight table** (D-L13): saved in the `.fpd`. Open adopts it
  and **never writes QSettings**. An old file without a table, and New Project,
  both copy the template (QSettings, else factory). Edits mark the project
  dirty; they are not undoable (like every Display Manager edit). "Set as
  Default" on the Line Weights tab writes the template.
- **LT1-4 `.fpdb` weights.** An optional `weights: {name: mm}` key carries the
  names used by the definition and its bundled nested definitions (LT1: text
  `border_weight`). No used names → no key; no schema bump. On load, missing
  names are added and the project silently wins conflicts; a merge that adds
  names dirties the project (not undoable) and re-pens its underlays. Only
  names present in the project table are written (an unknown name is never
  fabricated). A name in neither falls back to `resolve_line_weight_mm`'s
  default.
- **LT1-5 In-use / rename** cover paper categories (incl. Blocks), underlays,
  sheet texts (all sheets), model-plan texts (`Model_Space._texts`) and text
  primitives in project block definitions. Renaming onto a name something
  already references is refused (it would let Cancel rewrite that reference).
  Library files on disk are not rewritten. *Known gaps (filed):* texts in an
  open Block Editor, and undo snapshots taken before a rename, keep the old
  name.
- **LT1-6 Pickers.** Every Border Weight picker lists the live table, sorted
  by width (custom weights included).
- **LT1-7 One canvas mapping** (D-L14): px = mm × `UNDERLAY_MM_TO_PX_HINT`;
  ≤ 1.25 px snaps to ≤ 1.0 (the underlay fast path). It serves underlay
  layers, PDF-underlay widths and text borders; the bespoke text-border px
  table is retired.
- **LT1-8 Thin Lines** (D-L14): a **global** view-display toggle (the spec's
  "view-level" means a view display toggle, not per-tab state) on the footer
  rail. It applies to every model and Block Editor view, never paper/PDF;
  affects only strokes through the LT1-7 mapping (blocks join when LT2/LT3
  route them through it); persists as a user preference in QSettings
  (`view/thin_lines`). Paper isolation: a viewport pass suspends Thin Lines
  (paint-time consumers resolve non-thin), and unweighted PDF-underlay layers
  whose baked pen is thin are re-penned from their stored source width for the
  pass — paper output is identical with Thin Lines on or off.
- **Out of scope (filed):** wall paper weight (L11); the paper **categories'**
  QSettings-as-live-store flaw (Open overwrites the template; New doesn't
  reset); Full Color white-on-white for Construction + Blocks.

### How (H1–H10)

- **H1** The live table is module-level in `paper_display`
  (`project_line_weights` / `set_project_line_weights` /
  `reset_project_line_weights`); `resolve_line_weight_mm(name)` reads it.
  `load_line_weights` / `save_line_weights(settings)` are the template API.
- **H2** Persisted as `paper_display.line_weights`;
  `apply_paper_display_from_project` sets the project table (old file →
  template); `new_file` resets it from the template.
- **H3** The Line Weights tab edits the project table; every edit emits
  `DisplayManager.lineWeightsChanged` (not `sceneModified`, which fans out to
  3D / elevation rebuilds). MainWindow `_on_line_weights_changed` marks the
  project modified and calls `_refresh_weight_canvases` (re-pens every
  underlay, repaints model / paper / Block Editor views); `_apply_loaded_file`
  calls the same refresh after applying an opened file's table. Cancel replays
  renames in reverse and restores the snapshot (only when the table was
  edited). "Set as Default" writes the template.
- **H4** `paper_display.canvas_weight_px(width_mm)` implements LT1-7 and
  returns 1.0 while `thin_lines_active()` (Thin Lines on and not suspended by a
  paper pass); it replaces the inline mapping in `underlay_layer_pen`,
  `_pdf_width_to_px` (keeping its floor) and `TextItem._frame_pen`.
- **H5** `BlockInstance` gains `_paper_pen_width` / `_paper_pen_color` (the
  Pipe pattern), set by an `_apply_block` branch of `apply_paper_overrides`
  and cleared by `restore_model_display`; compiled op pens are never mutated
  (flyweight). Nested blocks are covered because the compile flattens their ops.
  Selection never plots (the accent is skipped while a paper width is set);
  the block placement ghost is paper-excluded (`PAPER_EXCLUDED` is read
  per instance).
- **H6** `"Blocks"` joins `_CATEGORY_KEYS` with `_FACTORY_LW` Light, outside
  `_HAS_FILL` / `_HAS_SECTION`, and the Display Manager Paper tab's
  `_PS_GROUPS["Drafting"]` (rows come from `_PS_GROUPS`, not the key list).
- **H7** `save_to_library` computes the `weights` map itself via the
  `used_weight_names` collector (definition + bundle); on load,
  `block_library.read_bundled_weights(path)` is merged by
  `Model_Space._merge_bundled_weights` at both embed sites
  (`load_blocks_from_files`, `reload_block_definition`).
- **H8** `_line_weight_in_use` / `_propagate_lw_rename` walk
  `DisplayManager._text_weight_refs` (renamed `_weight_refs` in LT2) (sheet annotations — live paper TextItems
  alias them — model-plan TextItems, definition text primitives → rename calls
  `BlockRegistry.invalidate`).
- **H9** `paper_display.weight_names()` feeds `frame_group`, both
  property-row builders and the Underlay Manager weight menu.
- **H10** `FooterRail.thin_pill` (copy of the HALO pill, tooltip, no shortcut
  in LT1); MainWindow `_toggle_thin_lines` sets the flag, stores
  `view/thin_lines` and calls `_refresh_weight_canvases`; the flag is restored
  at startup before any underlay is built. Paper isolation: the module counter
  `_THIN_SUSPEND` (incremented by `apply_paper_overrides`, released by
  `restore_model_display`, warns if unbalanced).

### LT1 guards (VC3) — as built

T1 `tests/test_lt1_block_paper.py` (real PDF parse at 1:50 + 1:100, Thin Lines
on/off; nested three deep follows Heavy) · T2 same file (BW black / Full Color
authored, Custom colour, block text, selection never plots, ghost never plots)
· T3 `tests/test_lt1_project_weights.py`, `tests/test_lt1_weights_dialog.py`,
`tests/test_lt1_open_order.py` (real `_load_project`) · T4
`tests/test_lt1_fpdb_weights.py` · T5 `tests/test_lt1_weight_refs.py` · T6
`tests/test_lt1_thin_lines.py` (paper parity for weighted + unweighted PDF
underlays; the model-text border is guarded at the paper-pass level because a
pre-existing crash blocks model text in viewports — filed) · T7
`tests/test_lt1_canvas_mapping.py` · T8 `tests/test_lt1_pickers.py`.

## LT2 — Stroke style record, copy_style, weight resolution, rename aliases (ratified 2026-10-04)

> Slice contract for LT2 (concept LD1 + D-L17a/D-L18/D-L23b), batched with the
> LT1 follow-up bug "weight rename leaves stale names". The *what* was settled
> in the LT2 Phase-2 grill (Q1–Q12, FP3 deltas only) and the *how* (H-a–H-g)
> approved as one batch, both 2026-10-04. P4 probe: an identical `setPen` on
> Path / Line / Rect items emits no `scene.changed` (paint-time pen sync is
> loop-free). **BUILT 2026-10-04** on `feat/lt2-style-record` (verified at
> the Account stamp below); every H item is locked as-built. Build-time
> refinements, each from a review / seam round and recorded inline: H-a's
> function names, H-b's dropped `_geom_style`, H-c's preview ghosts + paper-pass
> skip, H-e's weight-only row, H-g's open-time install, alias invariant,
> reserved names and refusal tooltip.

### What (grill Q1–Q12)

- **LT2-1 Record.** The 8 stroke primitives (Polyline, Line, Rectangle,
  Circle, Arc, RegularPolygon, Ellipse, Spline) carry
  `style: {linetype, weight, start, finish, colour}`. `TextItem` (own
  `border_weight`) and `ReferenceLineItem` (fixed reference style + its paper
  rule) do **not**.
  - `linetype` = `"continuous"` (reserved keyword — never a block, never
    "missing") | `"by_block"` | a linetype block id (LT4+). LT7's shipped
    "Continuous" entry is a picker label for the keyword.
  - `weight` = a named weight | `"by_linetype"` | `"by_block"`.
  - `start` / `finish` = `{end: "by_linetype" | "by_block" | <id>, visible: bool}`
    — stored and preserved from LT2, rendered from LT5.
  - `colour` = `#hex` (already a valid HF1 ColourValue; HF1 adds tokens
    without a migration). The record is the **only** source of the authored
    colour — never `pen()` (which `paint()` tints with `_display_color`).
- **LT2-2 Migration** (D-L17a). A legacy primitive (`"lineweight"` /
  `"color"` keys, no `style`) loads as Continuous / By Block / `by_linetype`
  ends / its authored colour; the px width is dropped. Applies to `.fpd`,
  `.fpdb`, stored definition primitives, clipboard payloads and undo
  snapshots. A definition's `version` / `source_status` never changes on
  migration. Paper output of legacy files is identical.
- **LT2-3 Edit tools** (D-L23b). Every derive path keeps the full record via
  `copy_style`. Free ends:

  | Tool | Ends |
  |---|---|
  | Break / break-at-point (split) | outer ends keep; both cut ends → `by_linetype` |
  | Trim (in place) | trimmed end → `by_linetype`; other end keeps |
  | Extend | moved end keeps (same end, longer) |
  | Fillet / chamfer | trimmed ends at the tangent/corner → `by_linetype`; the new arc/segment copies style with both ends `by_linetype` |
  | Join | outer ends of the sources; style from the first-picked item |
  | Copy / mirror / offset / array / explode / polyline swap / clipboard | verbatim |

- **LT2-4 Canvas** (D-L14, D-L17). Top-level By Block (and, in LT2, By
  Linetype — Continuous has no weight) → the Display Manager **Model "Blocks"**
  weight (factory **Light** → exactly 1.0 px); a named weight → its own
  `canvas_weight_px`. Same rule on the plan canvas (compiled block ops) and the
  Block Editor (raw items). Thin Lines applies to both. Strokes stay solid
  until LT3.
- **LT2-5 Paper.** By Block ops plot at the paper "Blocks" weight (LT1-2,
  unchanged); named-weight ops plot at their own mm (true mm ÷ viewport
  scale), nested blocks included. The placement / nested-record `style` slot
  (D-L5 By Block chaining) stays LT5 — in LT2 By Block always means the
  category.
- **LT2-6 Model "Blocks" row.** The Display Manager Model tab gains a Line
  Weight column, filled only on a new "Blocks" row (weight only — authored
  block colours, per-instance visibility/opacity unchanged); default Light.
- **LT2-7 Panel.** Linetype (Continuous / By Block) and Weight (By Block +
  named weights) are editable on selected primitives, undoable; Polygon gains
  Colour / Weight rows. The sticky ribbon **current** Linetype/Weight (D-L18)
  is LT4 (concept LD7); new primitives default to Continuous + By Block.
- **LT2-8 Rename** (closes the LT1-5 known gaps). After renaming A → B every
  holder draws at B's width and saves as B: live items, open Block Editors,
  model / paper / Block Editor undo-redo across the rename, paste of a
  pre-rename clipboard, `.fpd` save, `.fpdb` save, library re-place, and LT2
  `style.weight`. Cancel fully restores. A weight later created (or another
  weight renamed) as A must not hijack the old references. Undo snapshots no
  longer share primitive dicts with the live definitions.
- **LT2-9 Explode (recorded for LT5).** Once placements carry style, Explode
  resolves `by_block` primitives to the instance's concrete values (look
  unchanged). In LT2 they are copied verbatim.
- **Out of scope (filed):** hard-coded `"Medium"` text-border default and
  factory-name assumptions surviving a rename of a factory weight; the
  categories' QSettings-as-live-store flaw (now also the Model "Blocks" row).

### How (H-a–H-g)

- **H-a Record + migration.** New `stroke_style.py` owns `default_style(colour)`,
  `normalize_style(d)` (fills missing fields, validates keywords, deep copy)
  and `migrate_primitive(rec)` (a new dict; non-styled records unchanged).
  Migration runs at `Geometry2DMixin._geom2d_from_dict` (items; never shares
  the caller's style dict) and `BlockDefinition.from_dict` via
  `block_definition._load_prim` (stored primitive dicts deep-copied +
  migrated, text `border_weight` canonicalised, no `version` bump);
  `BlockDefinition.to_dict` deep-copies `primitives`.
  `_geom2d_to_dict` writes `style`; the 8 classes stop writing
  `lineweight` / `color`. `Model_Space.SAVE_VERSION` 9 → 10 (informational —
  migration is key-presence driven; load never reads the version). Shipped
  `.fpdb`s are not rewritten.
- **H-b `copy_style(src, dst, *, fresh_ends=())`** in `stroke_style.py` — deep
  copy of `src.style` (no-op for Text / ReferenceLine); `fresh_ends` names the
  ends reset to `by_linetype` per LT2-3. Replaces the explicit
  `color=`/`lineweight=` copies at the `scene_tools` derive sites and the
  polyline → line swap; dict round-trips (`_clone`, `_spline_copy`, paste,
  undo, editor seed/commit) carry the record already (`_spline_copy` drops its
  `"lineweight"` read). Constructors keep `color` / `lineweight` as plain pen
  arguments (ghosts, reference compile). New primitives get
  `default_style(<colour>)` from the mixin's `_init_stroke` (colour from
  `_geom_color_lw`); LT4 adds the sticky current-style accessor (a placeholder
  `_geom_style` with no caller was removed at the seam review). In-place
  trim / fillet / chamfer reset the moved end via `scene_tools._fresh_end`;
  Join takes each outer end from the source segment that forms it (swapped if
  that segment was reversed into the chain).
- **H-c Pen derived at paint.** Each primitive `paint()` calls the mixin's
  `_sync_stroke_pen()`: colour = `_display_color` or `style.colour`; width =
  `canvas_weight_px(resolve)` with By Block / By Linetype → the Model "Blocks"
  weight; cosmetic. Skipped while a placement ghost owns the pen (`_ghost_pen`:
  polyline placement, polygon ghost, ellipse + spline previews), while the pen
  is non-cosmetic, and for the whole of a paper pass
  (`paper_display.paper_pass_active()` — no setPen ping-pong with the sheet).
  The style record is the truth; the pen is a render cache.
- **H-c′/H-d Compiled ops.** `RenderOp` gains `weight: str | None`
  (unresolved name / `"by_block"`), filled at compile from the primitive's
  style; reference-mode compile and placeholders leave `None`.
  `BlockInstance.paint` resolves per op — `None`: today's op pen width
  (canvas) / `_paper_pen_width` (paper); `"by_block"`: Model Blocks px
  (canvas) / `_paper_pen_width` (paper); named: its `canvas_weight_px` /
  its mm ÷ `_paper_scale`. `_apply_block` also stores `_paper_scale`;
  `restore_model_display` clears it. Pen *style* (printed reference-line
  DashLine) still comes from `op.pen`. The flyweight compile is unchanged.
- **H-e Model "Blocks" row.** A weight-only special row (deliberately **not** a
  `_CATEGORIES` entry — that would add colour / visibility / opacity widgets
  and per-instance rows): `display_manager._add_model_blocks_row` under
  "Annotation & Geometry", a Line Weight column (`_COL_LW`, reset column moves
  to `_COL_RESET` 9) editable only there, tooltip'd. The live value is cached
  as `paper_display.model_blocks_weight()` (factory
  `MODEL_BLOCKS_FACTORY_WEIGHT` "Light"), stored **canonical** (a raw escape
  `canonical=False` exists only for the Cancel replay), persisted as
  `display_settings["Blocks"]` + QSettings `display/Blocks/line_weight`
  (`default_line_weight` for Set as Default). Precedence: Open = user default →
  project → current → factory; New = user default → factory; the undo-restore
  path (`apply_saved_display_settings`) **ignores the user default** so Ctrl+Z
  never flips the project's value. An edit emits `lineWeightsChanged` → the
  LT1 H3 refresh.
- **H-f Panel rows.** `_geom2d_properties` adds Linetype / Weight (and Colour
  where missing) through the existing panel undo path; the per-class
  read-only Colour / Line Weight labels go. `_weight_refs` (renamed from
  LT1's `_text_weight_refs`), `_line_weight_in_use`, `_propagate_lw_rename` and
  `used_weight_names` include `style.weight` references (one predicate,
  `stroke_style.is_named_weight`) and the Model "Blocks" weight.
- **H-g Rename aliases.** `paper_display` keeps a project alias map
  `{old: new}` persisted beside `line_weights` (`.fpd`), reset by New, part of
  the Display Manager Cancel snapshot. Rename A → B adds A → B, collapses any
  X → A to X → B and drops a B → … entry (renaming back works).
  `canonical_weight_name()` follows the chain (cycle-guarded);
  `resolve_line_weight_mm` uses it (project path only; the template path is
  literal). **Invariant:** an alias key is never a live table name — both
  `set_project_line_weights` and `set_weight_aliases` prune such keys, so
  callers install the table **then** the aliases (`apply_project_weights`).
  **Open:** `scene_io.load_from_file` installs the file's table + aliases
  (`paper_display.apply_project_weights`) **before** any definition / text
  parse, so a previous project's aliases never canonicalise the new file's
  names. **No hijack:** creating a weight, or renaming a different weight,
  onto an alias key is refused with a non-modal tooltip on the edited cell
  (renaming the target back is allowed). **Reserved names:**
  `validate_line_weight_name` refuses `by_block` / `by_linetype` /
  `continuous` (and the spaced spellings), case-insensitive. Eager rewrite of
  live holders: the H8 walk + definition-primitive `style.weight` + styled
  raw items in the project scene and in open Block Editors (via
  `project_scene._editor_scenes_provider`, registered by
  `BlockEditorManager`). Normalisation to canonical names at the
  serialization boundaries — `TextAnnotationData.to_dict/from_dict`,
  `normalize_style` (primitive to/from dict), `BlockDefinition.from_dict` —
  which covers undo restore (model and editor scenes), paste, `.fpd` save,
  `.fpdb` write / `used_weight_names`, and library merge
  (`merge_project_line_weights` skips alias keys, so an incoming old name maps
  onto this project's renamed weight — by design). Paper undo commands rely on
  the resolver + save normalisation. Snapshot cost of the deep copy (probe,
  200 definitions × 50 primitives): 164 ms vs 120 ms per undo push (1.37×).

### LT2 guards (VC3) — as built

Files: `tests/test_lt2_style_record.py`, `test_lt2_panel.py`,
`test_lt2_migration.py`, `test_lt2_edit_tools.py`, `test_lt2_canvas_paper.py`,
`test_lt2_model_blocks_row.py`, `test_lt2_rename.py` (incl. the two-project
open guard and every LT2-8 holder). Contract-retired + rewritten:
`test_lt1_block_paper::test_model_canvas_block_render_unchanged` (now 1 px),
`test_block_curve_import`, `test_polyline_two_point_finish`
(`test_two_point_line_keeps_style`), `test_offset_item::test_style_inherited`,
`test_modify_tools_offset::test_committed_item_inherits_style`,
`test_dynamic_input_parity` ("Weight" row), and three round-trip assertions in
`test_block_definition` / `test_block_library` (migrated primitives).

G9 (legacy `.fpd` + `.fpdb` → record defaults; **parsed PDF stroke widths
identical to base**; definition `version` / `source_status` unchanged) · G8a
(`.fpd` save/load, undo/redo, `.fpdb` bundle keep the full record; used
`style.weight` names bundled) · T-edit (every reachable tool through its real
entry point preserves style; unreachable `scene_tools` functions called
directly against the LT2-3 table) · T-canvas (pixel sampling, plan + Block
Editor: By Block = 1 px at Light, wider at Heavy row; named Heavy =
`canvas_weight_px`; Thin Lines → 1 px) · T-paper (real PDF parse at 1:50 /
1:100: By Block at the paper Blocks weight, named ops at their mm, nested
included) · T-panel (Weight / Linetype edit applied, undoable, persisted) ·
T-colour (Display Manager colour override active → saved `style.colour` =
authored) · T-rename (per holder in LT2-8: draws at B, saves as B; Cancel
restores; no hijack) · T-snap (in-place edit of a definition primitive after
a snapshot leaves the snapshot unchanged).

## LT3 — Linetype renderer, repeat data, Linetypes folder (ratified 2026-10-04)

> Slice contract for LT3 (concept LD-A, LD2, LD3, part of LD5). The *what* was
> settled in the LT3 Phase-2 grill (Q1–Q13, FP3 deltas) and the *how* (H3-a–H3-i)
> approved section by section in the brainstorm, both 2026-10-04. **Unbuilt.**
> Scope moved forward from LT4 by Q1/Q2/Q12/Q13: the `repeat` data key, the
> integrity set, the panel picker and the Linetypes folder. LT4 keeps the
> authoring surface (repeat frame, Pattern list, preview, browser badge, sticky
> current style).
>
> **P4 probe (2026-10-04, PyQt6 → QPdfWriter → PyMuPDF):** flat-cap dash
> subpaths plot at exact length (6.000 mm); `arcTo` dashes reach the PDF as
> curves; a **zero-length round-cap subpath is dropped** on screen and in the
> PDF, while a 1 µm round-cap segment (or `drawPoint`) renders a dot in both.

### What (grill Q1–Q13)

- **LT3-1 Source** (Q1). A linetype is a block with a `repeat` record. LT3
  ships the data key and picker, no authoring UI; the smoke uses hand-made
  `.fpdb` linetypes in the Linetypes folder.
- **LT3-2 Integrity** (Q2). A `repeat` block is not placeable as a symbol
  (paste skips it), cannot be deleted while a primitive uses it, and
  `referenced_ids` follows primitives' linetype ids (bundle, closure, cycle,
  users_of, invalidate). The Blocks-browser badge stays LT4.
- **LT3-3 Unit reading** (Q3). In the unit (definition-local, origin at the
  unit start, +X along the line): Line primitives lying on the X axis within
  `[0, length]` are **dashes**; zero-length axis Lines are **dots**; uncovered
  axis is **gap**. One dash weight per linetype = the heaviest named weight
  among the dashes (none named → By Linetype falls back per LT3-8). Every other
  primitive in the unit is ignored until LT6.
- **LT3-4 Canvas** (Q4). Widths stay cosmetic per D-L14 (Thin Lines still
  applies); dash/gap lengths are geometry and scale with zoom. Paper/PDF are
  true mm for both. LD3's "BlockInstance.paint stops forcing cosmetic pens" is
  retired as met by LT1/LT2 on paper — explicit dash geometry cannot collapse.
- **LT3-5 Drafting sizing** (Q5; **amends D-L3's fallback**). Length factor per
  surface: plan canvas — Drafting × `ScaleManager.drawing_scale` (SB1c later
  swaps in `PlanView.scale`), Model × 1; paper pass — Drafting ÷ the viewport's
  paper scale, Model × 1; Block Editor — × 1 (real size).
- **LT3-6 Surfaces.** Plan canvas (detail views included), sheet viewports /
  PDF, Block Editor raw items. Placement ghosts, HALO, snap and `shape()` stay
  on the continuous base geometry. No other surface paints block strokes
  (verified 2026-10-04: only `BlockInstance`, raw primitives and the tile
  lattice consume strokes).
- **LT3-7 Selection** (Q6). The accent highlight follows the expanded dashes.
- **LT3-8 Cascade** (Q9):

  | Linetype | Draws |
  |---|---|
  | `continuous` | solid |
  | `by_block` | solid (Continuous) until LT5's placement slot |
  | a linetype id | its dashes; missing → solid + badge (LT3-10) |

  | Weight | Canvas | Paper |
  |---|---|---|
  | named | its `canvas_weight_px` | its mm ÷ viewport scale (LT2-5) |
  | `by_block` | Model "Blocks" weight | paper "Blocks" weight |
  | `by_linetype` + a resolvable linetype with a dash weight | the dash weight | its mm ÷ viewport scale |
  | `by_linetype` otherwise | Model "Blocks" weight (LT2-4) | paper "Blocks" weight |

- **LT3-9 Pattern tiles** (Q7; **extends D-L23a**). Strokes of a pattern-tile
  block stamped as a hatch always draw Continuous; editing the tile in the
  Block Editor shows its linetypes (raw items).
- **LT3-10 Missing** (Q8). A linetype id that does not resolve draws
  Continuous everywhere, plus a canvas-only warning glyph (tooltip names the
  id; never plots; at the stroke's mid-length for a raw primitive, once at the
  insertion point for a placed block) and "Missing (<id>)" in the panel
  Linetype row. A *malformed*
  linetype (`length ≤ 0`, no axis dash or dot) draws Continuous without a
  badge. Glyph look is mockup-gated (first plan step).
- **LT3-11 Performance** (Q10). Continuous ops never reach the expander;
  existing perf guards stay green; 200 placed instances of a block with Hidden
  lines paint ≤ 2× the same scene Continuous. D-L21 stays LT8.
- **LT3-12 Picker** (Q12). The panel Linetype row lists Continuous, By Block,
  the project's linetypes, then Linetypes-folder linetypes not yet loaded
  (unique labels); picking a folder linetype loads it (one undo step) before
  its id is stored.
- **LT3-13 Linetypes folder** (Q13). System Settings > Data gains
  "Linetypes (optional)" (path, Browse…, Reset, tooltips), default
  `<block library>/System/Linetypes`; key and precedence owned by
  [`settings-dialog.md`](settings-dialog.md) §4.5b beside the Hatch patterns
  folder. No seeding until LT7.

### How (H3-a–H3-i)

- **H3-a `path_walk.py`.** Piece types `Seg(p0, p1)`, `Arc(c, r, a0, sweep)`,
  `EllipseArc(c, a, b, rot, t0, t1)`, `Curve(path)`; `length(piece)`;
  `phase0(piece, anchor)` per D-L9/D-L9b — Seg: projection of `p0` on its axis
  (direction folded to [0°, 180°)) measured from the anchor's projection; Arc:
  `r × a0` (Y-up CCW from the circle's 0°; a negative sweep is normalised to
  its CCW equivalent first, so phase never depends on draw direction); EllipseArc: arc length from its 0°;
  Curve: 0 at its start. `split(piece, s0, s1)` returns the exact sub-piece
  (Arc / EllipseArc stay analytic, Curve flattens). Existing helpers reused:
  `arc_math.point_at` / `yup_angle`, `geometry_intersect.point_on_segment_param`,
  `_periodic_bezier_spans` / `_bspline_path`.
- **H3-b `stroke_pieces()`** on the 8 styled classes (definition-local, the
  item's own frame incl. baked rotation): Line 1 Seg; Polyline its segments
  (+ the closing Seg when closed); Rectangle 4 Segs; RegularPolygon N Segs;
  Circle one 360° Arc; Arc one Arc; Ellipse one EllipseArc; Spline one Curve
  (its drawn path).
- **H3-c `linetype_render.py`.** `LinetypeDef.from_block(defn)` (LT3-3 reading
  → `period`, `dashes [(start, length)]`, `dots [pos]`, `dash_weight`, `size`;
  `None` when malformed). `expand(pieces, lt, length_factor, anchor) ->
  (dash_path, dot_path)`: dashes are flat-cap subpaths (arcs via `arcTo`), dots
  are 1 µm round-cap segments (P4). LRU cache keyed `(pieces key, linetype id,
  definition version, length_factor)` with a budget (the `hatch_render._lattice`
  pattern). `paint_stroke(painter, pieces, base_path, resolved, pen, *,
  length_factor, anchor, selected) -> missing_id | None` is the one paint entry:
  Continuous / unresolved / period × device scale < 2 px
  (`hatch_render._device_scale`) → `drawPath(base_path)` unchanged; else the
  dash path (FlatCap) then the dot path (RoundCap); when selected the accent
  highlight strokes the same paths.
- **H3-d `stroke_style.resolve_stroke(style, registry)`** →
  `ResolvedStroke(lt: LinetypeDef | None, weight: str, missing_id)` per LT3-8.
  `canvas_weight_name` / `canvas_px` take the resolved weight (By Linetype →
  dash weight when present).
- **H3-e RenderOp.** The stroke kind gains `pieces` (tuple, definition-local)
  and `linetype` (the style's raw value); the existing `origin` doubles as the
  stroke's phase anchor (the defining definition's origin, origin-relative);
  `mapped()` maps pieces and anchor, so nested blocks keep their own
  definition's phase. `_compile` fills them; reference-mode ops and
  placeholders leave them empty (always Continuous). Additive — the HD4a
  contract (`kind`, `pen`, order) is unchanged.
- **H3-f Paint routing.** The 8 primitive `paint()`s replace their
  `super().paint()` stroke + highlight with `paint_stroke` (fill, reference
  guides unchanged; anchor = the Block Editor's `origin_point()`, else the
  scene origin). `BlockInstance.paint` calls `paint_stroke` per stroke op under
  the pose (`painter.setWorldTransform(pose, True)`), so expansion is
  definition-local and shared by every instance. Length factor per LT3-5;
  `paint_stroke`'s missing id → the caller draws the badge unless
  `paper_pass_active()`. The tile lattice (`hatch_render`) is untouched.
- **H3-g `repeat` data** (mirrors HF2 `tile`). `BlockDefinition.repeat` =
  `{length, size: "drafting"|"model"}` | None via `_norm_repeat` and
  `set_repeat()` (version bump → cache key); additive `.fpdb` / embed key (no
  schema bump); library `index.json` entries gain a `repeat` flag. `ends`
  defaults (LD1) stay LT5.
- **H3-h Integrity.** `block_registry.prim_refs` adds a styled primitive's
  `style.linetype` when it is a block id → `referenced_ids`, `users_of` (the
  existing delete refusal), `closure`, `bundle_for`, `would_cycle`,
  `invalidate` follow. Pattern-placement refusal + paste skip extended to
  `repeat` blocks. Picking a linetype that would cycle is refused via
  `would_cycle`.
- **H3-i Folder + picker.** `app_data.linetypes_dir()` (override
  `LINETYPE_DIR_KEY`, else `<block_library_dir>/System/Linetypes`). The folder
  scan is generalised out of `hatch_patterns.library_patterns()` into one
  capability-folder scanner (new `capability_folder.py`) (folder + two subfolder levels, `index.json` flag,
  mtime cache) called with `"tile"` and `"repeat"`. `linetype_choices(registry,
  exclude)` mirrors `tile_choices`; a picked folder linetype loads via
  `blocks_browser.ensure_block_loaded`; the panel Linetype row uses it.

### LT3 guards (VC3)

G1 seam (collinear Hidden lines, abutting + gapped, opposite directions → axis
raster identical to one line) · G2 trim/break through the real tools →
surviving dash raster unchanged · G3 print exact (Drafting Hidden at 1:50 and
1:100 → PDF dash lengths = authored mm ± 0.05; a Model linetype scales with the
viewport) · G4-LT3 cascade (named / By Block / By Linetype primitives, placed +
nested → PDF widths and canvas px per LT3-8) · G-canvas (plan dash px = printed
mm × drawing_scale × zoom; Block Editor real size; period < 2 px → solid) ·
G-sel (accent only on dash pixels) · G-tile (stamped tile stroke solid) · G11
missing (solid + badge on canvas, no badge in the PDF, panel "Missing") ·
G8-LT3 (`.fpd` save/load, undo/redo, `.fpdb` save → fresh-project load keep the
linetype; delete-while-used refused; symbol placement refused; cycle refused) ·
G-perf (LT3-11). Unit tests: `path_walk` phase per piece type + split
exactness; `LinetypeDef.from_block` reading + malformed units.

Contract-retired + rewritten (planned): `test_lt1_block_paper._block_strokes`
(must read dashed strokes, not only full-length ones),
`test_lt2_style_record::test_weight_name_for_by_block_is_model_blocks` (By
Linetype row), `test_render_op_compile` (additive fields only).

## Acceptance Criteria

- [ ] Collinear lines sharing a linetype are indistinguishable from one line (D-L9).
- [ ] Every row of the cascade (D-L4/5/6/17) resolves to the stated weight/linetype on canvas and PDF.
- [ ] Ends obey D-L7/8/8b; symbols obey D-L15; end attributes obey D-L10.
- [ ] Weights travel with `.fpd`/`.fpdb` (D-L13); legacy files migrate (D-L17a).
- [ ] D-L21 bar met on the confirmed bench.
- [ ] Guards G1–G11 in the concept doc pass.

## Verification Checklist

- [ ] Guards G1–G11 (concept doc) RED with the change reverted, GREEN with it.
- [ ] Full suite green; registry-enumerating tests updated (concept doc keep-green list).
- [ ] Cross-spec reconciliation below applied when each slice lands.

## Cross-spec reconciliation (to amend when the build lands — Rule A)

- `block-system.md` — `repeat` / `end` capabilities; placement + nested-record `style` slot; `referenced_ids`; StrokeOp compile; Blocks category weight.
- `2d-geometry.md` §1 — `style` record replaces px `lineweight`; current-style defaults; §1.2 "lineweights never scale" stays.
- `paper-space.md` — top-level By Block → Construction; BlockInstance category; project-scoped weights.
- `2026-05-12-paper-space-display-manager-design.md` §7.2 — weights move from QSettings to the project.
- `hatch-and-fill.md` HD4 — RenderOp stroke half = StrokeOp (one refactor).
- `grid-system.md` §16 — linetype property becomes the gridline-from-primitives follow-up.
- `view-relationships.md` §7.4 — catalog rows 2 and 4 point here.
- `units-and-formatting.md` — line-weight display convention (named weight + mm).
- `feature-system.md` — pipe as a Feature (D-L22).
