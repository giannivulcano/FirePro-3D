---
status: partial          # LT1 BUILT 2026-10-04 (project weights, Blocks paper category, canvas mapping, Thin Lines); LT2 BUILT 2026-10-04 (style record, copy_style, per-op weights, Model Blocks row, rename aliases); LT3 BUILT 2026-10-05 (linetype renderer, `repeat` data, integrity set, picker, Linetypes folder); WM1 BUILT 2026-10-05 (By Block retired on primitives, the current); LT4 BUILT 2026-10-06 (repeat authoring: capability slot, repeat frame, Pattern list, preview swatch, Continuous lock, badges, ribbon toggle); LT5–LT8, WM2, WM3 unbuilt. D-L1–D-L23 ratified in the 2026-10-02 concept grill (Q1–Q23); how = docs/superpowers/specs/2026-10-02-linetypes-concept-design.md (LD1–LD7)
last-verified: 2026-10-06  # LT4 Account (LT4 section reconciled to as-built: header, H4-a–H4-g, LT4-4/11e/11f/12 + A6 amendments, guards; applies-to + cross-spec pointers); prior WM1 Account (WM section: WM1 as-built subsection, WM-10 amendment, LT2-7/LT3-8/LT3-12 pointers, applies-to); prior Weight model design (WM-1–WM-12 section added; D-L4 weight half/D-L5/D-L6/D-L17/LT2-9 superseded; D-L18/D-L19/D-L22 amended; unbuilt); prior LT3 Account (LT3 section reconciled to as-built: 0° arc restart, option-A badge, perf memo, seam rulings A/B/D/E, guards; D-L9b amendment pointer; D-L4/5/17 weight rows flagged under redesign); prior 2026-10-04 paper-outline-weight audit (paper_display.py touched; no linetypes claim changed); prior LT2 Account (LT2 section reconciled to as-built: H-a/H-b/H-c/H-e/H-g refinements, guards); prior LT1 Account d031637
verified-commit: b9b1094   # LT4 Account (feat/lt4-repeat-authoring); prior 123ead7 WM1 Account (feat/wm1-weight-model-primitive); prior 489dcc2 Weight model design; prior be7c88a LT3 Account (feat/lt3-linetype-renderer); prior 4c799ee audit only; prior 0056b5c
applies-to:               # LT1 + LT2 + LT3 + WM1 + LT4 seams (built)
  - firepro3d/repeat_frame.py        # LT4 — RepeatFrame (repeat unit frame, Length grip, preview ring); shared frame base capability_frame.py is owned by hatch-and-fill.md
  - firepro3d/linetype_pattern.py    # LT4 — pure rows ⇄ reading (rows_from_reading, spans, content_end / axis_end, validate_rows, SEED_ROWS)
  - firepro3d/linetype_authoring.py  # LT4 — live rows ⇄ axis Lines (apply_pattern_rows), Weight row, Repeat field edits, begin_linetype, pre_capture hook, preview_painter
  - firepro3d/capability_panel.py    # LT4 — capability panel rows + write-back (tile rows delegate to tile_frame.py, owned by hatch-and-fill.md)
  - firepro3d/block_editor.py        # LT4: toggle_capability, capability seed on open, commit with capability only (rest owned by block-system.md)
  - firepro3d/blocks_browser.py      # LT4: _linetype_badge / _capability_badge + library-row index flags only (rest owned by block-system.md)
  - firepro3d/model_space.py         # LT4: block_capability slot + set_block_capability, push_undo_state pre-capture call, symbol_use_refusal / linetype_off_refusal, linetype users wording (_linetype_users_message), commit_block_definition capability= only (rest owned by block-system.md and others)
  - firepro3d/paper_display.py       # LT1: project weight table, canvas mapping, Thin Lines, Blocks paper category; LT2: Model Blocks weight, rename aliases, apply_project_weights, paper_pass_active
  - firepro3d/block_instance.py      # LT1/LT2: paper pen hooks + per-op weight resolution; LT3: linetype paint (memo, expansion cache, plain fast path, badge) only (rest owned by block-system.md)
  - firepro3d/display_manager.py     # LT1/LT2: Line Weights tab, weight in-use / rename / aliases, Model "Blocks" row only (rest owned by display-system)
  - firepro3d/stroke_style.py        # LT2: stroke style record, migration, copy_style, canvas weight resolution; LT3: resolve_stroke cascade + linetype_block / linetype_ref_missing / is_linetype_ref; LT4: apply_current linetype-editor branch (Continuous + pattern weight)
  - firepro3d/render_op.py           # LT2: RenderOp.weight; LT3: pieces + linetype only (type owned by hatch-and-fill.md)
  - firepro3d/path_walk.py           # LT3 — analytic pieces, arc length, axis phase, split, split_at_zero
  - firepro3d/linetype_render.py     # LT3 — unit reading, expansion, paint_stroke / draw_expansion, missing badge; LT4 — axis_role (the one per-Line LT3-3 role, shared by the reading and the Pattern list)
  - firepro3d/linetype_choices.py    # LT3 — panel Linetype picker source (project + Linetypes folder)
  - firepro3d/capability_folder.py   # LT3 parts — shared tile/repeat folder scan ("repeat" flag; the hatch side is owned by hatch-and-fill.md)
  - firepro3d/block_definition.py    # LT3: repeat key + stroke-op pieces at compile only (rest owned by block-system.md)
  - firepro3d/block_registry.py      # LT3: linetype refs in prim_refs, linetype_users_in, invalidate(was_linetype) only
  - firepro3d/geometry_2d.py         # Geometry2DMixin style record + LT3 stroke_pieces / paint routing / panel Linetype + Weight rows; WM1 stroke_rows + GeometryTemplate rows; LT4 stroke_rows locked= + the template's locked linetype-unit rows only (the rest is owned by 2d-geometry.md)
  - firepro3d/geometry_drawing_controller.py  # WM1: apply_current at the 7 draw commits only
  - firepro3d/placement_input_coordinator.py  # WM1: scene-aware GeometryTemplate only
  - main.py                          # WM1: _GEOMETRY_DRAW_MODES template routing + current save/restore; LT4: ribbon Linetype toggle (_be_toggle_linetype / _be_toggle_capability / _sync_capability_buttons) only
source-tasks: ["Concept: user-definable linetypes as blocks — end types, dash-dot spacing + configuration, lineweight at definition vs host level (2026-10-02)"]
---

# Linetypes — Design Spec (as-intended)

> **Greenfield spec (2026-10-02).** Forged by the linetype concept run (orphan
> gate, greenfield path). At forging no linetype code existed (see *As-built
> baseline*; LT1–LT4 and WM1 have since built — each built slice section is
> as-built). This
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
  line and polyline. *(Amended 2026-10-05 by LT4-1/LT4-2: the drawn axis
  Lines are canonical, the list is their view/editor and ripples — Length =
  sum of rows.)*

### Weight and linetype cascade

- **D-L4 Definition vs use.** The definition authors a weight per component
  (dash, each symbol). A line's Weight = **By Linetype** | named weight |
  **By Block**. A named weight replaces the dash weight only; symbols keep
  their authored weight. Editing the definition updates By Linetype lines only.
  *(Weight half **SUPERSEDED** 2026-10-05 by the "Weight model" section — a
  line's Weight = By Linetype | named (no By Block, WM-5); "a named weight
  replaces the dash weight only, symbols keep theirs" survives as WM-2.)*
- ~~**D-L5 Host (By Block).**~~ **SUPERSEDED** 2026-10-05 by "Weight model"
  WM-2/WM-3/WM-6 (placement override, outer wins). *Was:* only By Block
  primitives follow the host; every placement and nested record has a Weight
  (default = the Display Manager "Blocks" weight); By Block chains outward.
- ~~**D-L6 Linetype By Block.**~~ **SUPERSEDED** 2026-10-05 by "Weight model"
  WM-4 (placement Linetype = As Authored | named; primitives lose By Block).
- ~~**D-L17 Top-level By Block.**~~ **SUPERSEDED** 2026-10-05 by "Weight
  model" WM-5/WM-12 (By Linetype's category fallback = the drawing item's
  category; D-L17's paper "Construction" survives for raw primitives on a
  sheet).
- **D-L18 New primitives** use a sticky **current** Linetype + Weight
  (ribbon/panel). Picking a linetype does not change the current weight.
  *(Amended 2026-10-05 by "Weight model" WM-10: factory current = Continuous ·
  By Linetype · By Linetype colour, app-session-scoped.)*
- **D-L19 Colour.** Unit and end-block content defaults to **By Line** (the
  using line's ColourValue); authors may set explicit component colours; B&W
  forces black. *(Extended 2026-10-05 by "Weight model" WM-7: colour gets the
  same placement/By Linetype cascade.)*

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
  their start. *(Amended 2026-10-05, user ruling: the arc / ellipse rhythm
  **restarts at 0°** — a point's phase is the arc length of its own angle in
  [0°, 360°), the walk splitting at 0° — see "LT3" H3-a.)*
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
  Pipe-as-linear-Feature is its own design task. *(Amended 2026-10-05 by
  "Weight model" WM-4: the plan-block line is authored Continuous + Weight By
  Linetype and the pipe placement overrides the Linetype; the Main/Branch
  linetype distinction is expected to go away — user, 2026-10-05.)*
- **D-L23 Defaults.** (a) strokes inside repeat units/end blocks are always
  Continuous (no recursion) — and, per LT3-9, so are pattern-tile strokes when
  stamped as a hatch; (b) explode, copy, mirror and modify tools keep
  Linetype/Weight/ends — new free ends from break/trim get By Linetype ends;
  (c) mirror flips end blocks, text stays upright; (d) closed shapes never
  draw ends; (e) a missing linetype/end block draws Continuous/Flat plus a
  visible warning badge, never nothing.

## Weight model — By Block moves from the primitive to the placement (ratified 2026-10-05)

> Design run (the P1 "Weight model" task, filed at the LT3 close). *What*
> settled in a Phase-2 grill (Q1–Q12, every row user-ratified); supersedes
> D-L4 (weight half), D-L5, D-L6, D-L17 and LT2-9, amends D-L18/D-L19/D-L22.
> **WM1 BUILT 2026-10-05** (primitive half, `feat/wm1-weight-model-primitive`,
> verified `123ead7` — see "WM1 — as built" below); WM2 (placement half) and
> WM3 (colour cascade) unbuilt in `todo_open.md`. Worked examples below are
> the acceptance scenarios.

- **WM-1 Drivers** (all four ratified): what is authored is what is seen; a
  Revit-style per-instance override; system geometry driven by its placement
  or linetype; no "By Block" anywhere in the UI.
- **WM-2 Override scope.** A named override on a placement or nested record
  **replaces every stroke's** weight (authored Heavy included — the hierarchy
  flattens). Symbols embedded in a linetype's repeat unit keep their authored
  weight (D-L4's surviving rule). A hierarchy-preserving override is the
  instance-parameters design's (revisit trigger there).
- **WM-3 Placement Weight** = **As Authored** (default for new and migrated
  placements) | **By Category** (replace every stroke with the Display
  Manager "Blocks" weight — Model row on canvas, paper category on sheets) |
  a named weight. Every deferring picker option shows what it resolves to:
  "By Category (Light)", "By Linetype (Very Fine)".
- **WM-4 Placement Linetype** = As Authored | a named linetype (replaces every
  stroke's linetype). Primitives lose Linetype By Block (Continuous | a
  linetype). No By Category linetype. Strokes inside repeat units / end
  blocks / pattern tiles stay Continuous (D-L23a, LT3-9).
- **WM-5 By Linetype stays on primitives** (weight): it borrows the dash
  weight of the stroke's **effective** linetype (after any placement
  override). A placement Weight override (named / By Category) beats it. No
  dash weight (Continuous, malformed, missing) → the drawing item's category
  weight (WM-12).
- **WM-6 Nesting — outer wins.** Each level's override replaces everything
  beneath it, so the outermost non-As-Authored setting decides (an
  "existing = Hidden" riser dashes its nested valve too). Nested records carry
  the same picker as top-level placements.
- **WM-7 Colour mirrors weight.** Placement / nested-record Colour = As
  Authored | By Category (the "Blocks" colour — the Model row gains a Colour
  column; paper uses the paper "Blocks" category colour) | a named colour;
  replace-all, outer wins, resolved value shown. Unlike weight, a colour
  override **reaches** linetype-embedded symbols, fills, hatches, text and end
  blocks ("existing = grey" greys everything). Primitive Colour = explicit |
  **By Linetype (<colour>)** = the linetype's designed colour = its **first
  dash's** colour; dashes authored "By Line" (D-L19) give no designed colour →
  **Automatic** (hatch D-A18; needs HF1). The paper B&W / Custom colour modes
  stay above the whole cascade.
- **WM-8 Hatch.** D-A12's foreground colour "By block" is renamed **By
  Pattern (<colour>)** (the pattern's analogue of By Linetype). A placement
  Colour override reaches fills and hatches; Weight / Linetype overrides do
  **not** reach hatch tile strokes.
- **WM-9 Migration** (on load, every LT2-2 path — `.fpd`, `.fpdb`, stored
  definitions, clipboard, undo; no definition `version` bump; shipped `.fpdb`s
  not rewritten): weight `by_block` → `by_linetype`; linetype `by_block` →
  `continuous`; end `by_block` → `by_linetype`; placements / nested records
  without a slot → As Authored ×3. Canvas **and paper output stay identical**
  (By Linetype on Continuous resolves exactly as `by_block` does today).
- **WM-10 New primitives.** Factory current = Continuous · By Linetype weight
  · By Linetype colour; a pick becomes the sticky current for the next
  primitive (picking a linetype changes neither weight nor colour); the
  current is shared by every Block Editor and never saved in the `.fpd`.
  *(Amended 2026-10-05 by the WM1 Phase-2: the current **persists** in
  QSettings like every new template family (`property-panel.md` §3.7) instead
  of resetting on launch; its surface is the pre-placement GeometryTemplate in
  the Properties panel, not a ribbon group; only a pick on the template moves
  it — editing a selected primitive never does.)*
- **WM-11 Explode and ends.** Explode bakes the record's resolved values
  (look unchanged); As Authored explodes verbatim (By Linetype kept); By
  Category bakes the current DM value as a concrete name / colour. A placement
  never swaps end types (a per-placement end override is instance-parameters
  work), but end blocks take the placement's resolved Colour and Weight
  (weight-relative caps scale with it).
- **WM-12 Text and fallback category.** Text in a placed block takes the
  placement Colour; glyphs are never bolded; the text-box border takes Weight
  + Colour (+ Linetype once the border migrates to linetypes). The By Linetype
  fallback category is the drawing item's: inside a placement → "Blocks"
  (Model / paper); a raw primitive drawn directly on a sheet (latent, LT3-6) →
  paper "Construction".

Acceptance scenarios (test block "Sprinkler": circle Heavy/red, cross
Light/Automatic, deflector Medium/blue): As Authored → as authored; Weight
Medium → all Medium; Linetype Hidden → all dashed; Colour Grey → all grey;
nested record Heavy inside an outer Light placement → all Light; a legacy file
→ pixel-identical canvas + PDF; Explode of an overridden record → identical
look.

### WM1 — as built (2026-10-05, verified `123ead7`)

*What* (WM1 Phase-2, FP3 deltas, user-ratified): D1 a primitive with a
linetype id + `by_block` migrates like the rest (it then draws at the dash
weight — data only possible since LT3); D2 the current lives on the
GeometryTemplate (ribbon group dropped, no mockup gate); only a template pick
moves the current; the template's Linetype list is the primitive panel's
(folder linetypes load on pick); the current persists; a current linetype that
is not a linetype in the project draws / shows Continuous.

*How:* `stroke_style` — `normalize_style` / `_end` migrate `by_block`
(weight → `by_linetype`, linetype → `continuous`, end → `by_linetype`;
`BY_BLOCK` survives only as migration input and defensive guards);
`default_style` = Continuous / By Linetype; `weight_label` /
`weight_from_label` ("By Linetype (<dash weight | Model Blocks weight>)");
the current store `current_style` / `set_current` / `reset_current` /
`current_to_settings` / `current_from_settings` (QSettings
`template/geometry/linetype|weight`; an unknown weight → By Linetype) /
`apply_current` (stamped right after construction at the 8 draw commits —
`geometry_drawing_controller` circle / ellipse / polyline / rectangle / arc /
polygon / spline and `Model_Space._make_line_like`; never imports, edit tools,
paste or previews). `geometry_2d.stroke_rows` builds the Linetype / Weight
rows (tooltips) for primitives and `GeometryTemplate` (now scene-aware via
`PlacementInputCoordinator._get_geometry_template`); `linetype_choices`
offers no By Block. `MainWindow._on_mode_changed_template` shows the
template of the *signalling* scene for all 8 draw modes
(`_GEOMETRY_DRAW_MODES`); `save_settings` / `restore_settings` persist the
current. No panel-refresh exclusion was needed: every draw tool is
single-placement and nothing changes the selection while one is armed
(probed, 2026-10-05).

*Guards (VC3):* `tests/test_wm1_style.py` (migration, labels, store),
`test_wm1_parity.py` (G1 canvas pixel + parsed-PDF parity for by_block input
through `BlockDefinition.from_dict` / `LineItem.from_dict`; G2 the linetype
edge — RED with the migration reverted), `test_wm1_template.py` (pickers,
template rows, folder pick, all 8 tools stamp the current, import does not),
`test_wm1_mainwindow.py` (real MainWindow + Block Editor: every tool shows the
signalling scene's template — RED with the old routing; a template pick drives
a real two-click line; selection edits don't move the current; save_settings
round-trip; G5 no "By Block" UI string). Contract-retired + rewritten:
`test_lt2_style_record` (default, empty weight, copy_style marker),
`test_lt2_edit_tools` (`_styled` marker), `test_lt2_panel` (4),
`test_lt3_picker` (option lists, fixed choices), `test_lt2_migration` (2),
`test_block_curve_import` (1).

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
  *(Superseded by WM1: no By Block options; Weight = "By Linetype (<resolved>)"
  + named; the current is the GeometryTemplate, default Continuous / By
  Linetype.)*
- **LT2-8 Rename** (closes the LT1-5 known gaps). After renaming A → B every
  holder draws at B's width and saves as B: live items, open Block Editors,
  model / paper / Block Editor undo-redo across the rename, paste of a
  pre-rename clipboard, `.fpd` save, `.fpdb` save, library re-place, and LT2
  `style.weight`. Cancel fully restores. A weight later created (or another
  weight renamed) as A must not hijack the old references. Undo snapshots no
  longer share primitive dicts with the live definitions.
- **LT2-9 Explode (recorded for LT5).** Once placements carry style, Explode
  resolves `by_block` primitives to the instance's concrete values (look
  unchanged). In LT2 they are copied verbatim. *(Superseded 2026-10-05 by
  "Weight model" WM-11: Explode bakes the record's resolved override; As
  Authored explodes verbatim.)*
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
> approved section by section in the brainstorm, both 2026-10-04. **BUILT
> 2026-10-05** on `feat/lt3-linetype-renderer` (verified `be7c88a`); every H
> item below is locked as-built. Scope moved forward from LT4 by Q1/Q2/Q12/Q13:
> the `repeat` data key, the integrity set, the panel picker and the Linetypes
> folder. LT4 keeps the authoring surface (repeat frame, Pattern list, preview,
> browser badge, sticky current style).
>
> **Build-time refinements**, each ratified and recorded inline below:
>
> - *User rulings:* arc / ellipse dash rhythm **restarts at 0°** (2026-10-05;
>   amends D-L9b, H3-a / H3-c); missing glyph = mockup **option A**
>   (2026-10-04; LT3-10); the LT3-11 **perf fix keeps the 2× bar** — a per-paint
>   memo, with only the expansion held across paints, per instance (H3-f); and
>   **blocks with no linetype refs take the pre-LT3 paint path** (2026-10-05:
>   plain 200-instance scene back to base `b256fe6` speed, best-of-40).
> - *Orchestrator rulings from the seam review (VC9, 2026-10-05):* the glyph
>   bounds pad applies **only while a reference is unresolved** (LT3-10); a
>   linetype id naming a **non-`repeat` block is missing** (LT3-8 / LT3-10); the
>   panel Weight row gains a **By Linetype** option (LT3-8); the delete refusal
>   also covers **loose lines** in the plan / an open Block Editor (LT3-2).
> - *Spec corrections (code was right):* screen LOD is skipped on **every**
>   paper pass, on-screen sheet viewports included (H3-c); the LT3-13 row lives
>   in the General pane's Data folder group; the H3-c cache keys.
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
  (refused at `set_mode("place_block")`, the armed placement click and the
  drag / browser gate, with `block_library.LINETYPE_REASON`; paste skips it),
  cannot be deleted while a primitive uses it, and `referenced_ids` follows
  primitives' linetype ids (bundle, closure, cycle, users_of, invalidate).
  *(Seam ruling A, 2026-10-05:)* "a primitive" includes live styled primitives
  in the plan and in an open Block Editor, not only definition primitives; the
  refusal message names the nesting blocks and the lines together. The
  Blocks-browser badge stays LT4.
- **LT3-3 Unit reading** (Q3). In the unit (definition-local, origin at the
  unit start, +X along the line): a non-zero Line on the X axis, clamped to
  `[0, length]`, is a **dash** (a Line wholly outside, or a clamped sliver, is
  ignored — never a dot); a zero-length axis Line (tested unclamped) inside the
  frame is a **dot**; uncovered axis is **gap**. One dash weight per linetype =
  the heaviest named weight among the dashes (none named → By Linetype falls
  back per LT3-8). Every other primitive in the unit is ignored until LT6.
- **LT3-4 Canvas** (Q4). Widths stay cosmetic per D-L14 (Thin Lines still
  applies); dash/gap lengths are geometry and scale with zoom. Paper/PDF are
  true mm for both. LD3's "BlockInstance.paint stops forcing cosmetic pens" is
  retired as met by LT1/LT2 on paper — explicit dash geometry cannot collapse.
- **LT3-5 Drafting sizing** (Q5; **amends D-L3's fallback**). Length factor per
  surface: plan canvas — Drafting × `ScaleManager.drawing_scale` (SB1c later
  swaps in `PlanView.scale`), Model × 1; paper pass — Drafting ÷ the viewport's
  paper scale, Model × 1; Block Editor — × 1 (real size), including a nested
  placed block there (the drawing scale applies only on the `scene_role`
  `"plan"` scene).
- **LT3-6 Surfaces.** Plan canvas (detail views included), sheet viewports /
  PDF, Block Editor raw items. Placement ghosts (the block placement ghost and
  raw ghost pens), HALO, snap and `shape()` stay on the continuous base
  geometry; ghosts never draw the missing glyph. No other surface paints block
  strokes (verified 2026-10-04: only `BlockInstance`, raw primitives and the
  tile lattice consume strokes). *Raw plan primitives* (loose styled geometry
  in the plan scene) route through the same paint path and take the paper
  factor from the scene's viewport-pass scale; no UI path creates them today
  (containment C1 keeps drawing in the Block Editor), so the path is latent
  but guarded.
- **LT3-7 Selection** (Q6). The accent highlight follows the expanded dashes
  (raw primitives re-stroke the expansion with the highlight pen; a placed
  block strokes its expansion with the accent pen).
- **LT3-8 Cascade** (Q9) *(the `by_block` rows are retired by WM1 — a legacy
  `by_block` is migrated on load and never reaches the cascade)*:

  | Linetype | Draws |
  |---|---|
  | `continuous` | solid |
  | `by_block` | solid (Continuous) until LT5's placement slot |
  | a linetype id | its dashes; missing (no such block, **or a block without `repeat`** — seam ruling E) → solid + badge (LT3-10) |

  | Weight | Canvas | Paper |
  |---|---|---|
  | named | its `canvas_weight_px` | its mm ÷ viewport scale (LT2-5) |
  | `by_block` | Model "Blocks" weight | paper "Blocks" weight |
  | `by_linetype` + a resolvable linetype with a dash weight | the dash weight | its mm ÷ viewport scale |
  | `by_linetype` otherwise | Model "Blocks" weight (LT2-4) | paper "Blocks" weight |

  The panel Weight row offers **By Block**, **By Linetype** and the named
  weights, and shows By Linetype as itself (seam ruling D — LT3 draws the two
  differently, so folding By Linetype into "By Block" would let a re-pick
  silently change the width).
- **LT3-9 Pattern tiles** (Q7; **extends D-L23a**). Strokes of a pattern-tile
  block stamped as a hatch always draw Continuous; editing the tile in the
  Block Editor shows its linetypes (raw items).
- **LT3-10 Missing** (Q8). A linetype id that does not resolve to a `repeat`
  block draws Continuous everywhere, plus a canvas-only warning glyph (never
  plots; at the stroke's mid-length for a raw primitive, once at the insertion
  point for a placed block), the item's tooltip "Missing linetype: <id> — drawn
  Continuous" (the previous tooltip returns once it resolves) and "Missing
  (<id>)" in the panel Linetype row (re-picking that label never rewrites the
  stored id). A *malformed* linetype (a `repeat` block with `length ≤ 0` or
  non-finite, or no axis dash or dot) draws Continuous without a badge. Glyph
  = mockup option A (user, 2026-10-04): a filled amber (theme `warn`) triangle
  with a white "!" drawn as geometry, at the fixed device size
  `constants.LINETYPE_BADGE_PX`. *(Seam ruling B:)* the item's bounds grow to
  hold the glyph **only while a reference is unresolved** — a resolving
  linetype keeps the Continuous bounds (manipulator frame, copy base point).
- **LT3-11 Performance** (Q10). Continuous ops never reach the expander;
  existing perf guards stay green; 200 placed instances of a block with Hidden
  lines paint ≤ 2× the same scene Continuous (bar kept by the user's perf-fix
  ruling; met via H3-f). D-L21 stays LT8.
- **LT3-12 Picker** (Q12; *By Block removed by WM1*). The panel Linetype row lists Continuous, By Block,
  the project's linetypes, then Linetypes-folder linetypes not yet loaded
  (unique labels; in a Block Editor the edited block and anything that would
  cycle are left out); picking a folder linetype loads it (one undo step,
  carrying the new ref; a failed load restores the old ref) before its id is
  stored.
- **LT3-13 Linetypes folder** (Q13). System Settings > General gains
  "Linetypes (optional)" in its Data folder group (path, Browse…, Reset,
  tooltips), default `<block library>/System/Linetypes`; key and precedence
  owned by [`settings-dialog.md`](settings-dialog.md) §4.5b beside the Hatch
  patterns folder. No seeding until LT7.

### How (H3-a–H3-i) — as built

- **H3-a `path_walk.py`.** Frozen piece types `Seg(x0, y0, x1, y1)`,
  `Arc(cx, cy, r, a0, sweep)`, `EllipseArc(cx, cy, rx, ry, rot, t0, sweep)`
  (Qt parametric degrees in the frame `translate(c)·rotate(−rot)`) and
  `Curve(pts)` (a flattened polyline; `Curve.from_path` flattens scaled up by
  `constants.LINETYPE_CURVE_FLATTEN_SCALE` because Qt's default flattening
  strays visibly from a mm-scale cubic). Angles follow Qt `arcTo` (positive
  sweep = Qt CCW). `canonical(piece)` folds a Seg's direction to [0°, 180°)
  and normalises a negative sweep to its positive equivalent, so phase never
  depends on draw direction. `phase0(piece, anchor)` per D-L9 / D-L9b — Seg:
  projection of its canonical start on its axis measured from the anchor's
  projection; Arc: `r × a0`; EllipseArc: arc length from parameter 0; Curve: 0.
  **`split_at_zero(piece)`** (user ruling 2026-10-05) breaks a canonical Arc /
  EllipseArc at every 0° crossing (a full turn from 0° stays one piece), so
  the walk restarts the rhythm at 0°. `split(piece, s0, s1)` returns the exact
  sub-piece (Arc / EllipseArc stay analytic, Curve slices its vertices);
  `length`, `point_at`, `append` (arcs as true curves), `to_path`,
  `total_length`, `point_at_total`. `map_piece(piece, t)` maps through a rigid,
  orientation-preserving transform and **raises on a reflection** (block
  Flip/Mirror must add a branch). The maths is self-contained (no
  `arc_math` / `geometry_intersect` reuse); ellipse arc length uses a cached
  per-(rx, ry) table and a Curve's cumulative lengths are cached per value.
- **H3-b `stroke_pieces()`** on the 8 styled classes (item-local, the item's
  own frame incl. baked rotation): Line 1 Seg; Polyline its segments (+ the
  closing Seg when closed); Rectangle 4 Segs (corners through its rotation
  transform); RegularPolygon N Segs; Circle one 360° Arc from 0°; Arc one Arc
  (stored CCW span); Ellipse one EllipseArc from 0°; Spline one Curve of its
  drawn path, memoised until its path regenerates (a degenerate spline has no
  pieces).
- **H3-c `linetype_render.py`.** `LinetypeDef.from_block(defn)` (LT3-3
  reading → frozen `block_id`, `version`, `period`, `dashes ((start,
  length), …)`, `dots (pos, …)`, `dash_weight`, `size`; `None` when
  malformed), cached in a bounded LRU keyed `(id, version, origin)` that hits
  only when it holds the definition's own primitives list (the origin moves
  the unit without a version bump). `expand(pieces, lt, factor, anchor) ->
  (dash_path, dot_path)`: pieces are split at 0° then walked from `phase0`;
  dashes are flat-cap subpaths (arcs via `arcTo`), dots are 1 µm round-cap
  segments (P4); a piece longer than `LINETYPE_MAX_PERIODS` periods draws
  continuous; a non-positive / non-finite scaled period expands to nothing.
  Bounded LRU keyed on `(pieces, the LinetypeDef value, factor, anchor)` (the
  returned paths are shared — read-only). `paint_stroke(painter, pieces, lt,
  pen, *, factor, anchor) -> bool` is the raw-primitive paint entry: it returns
  **False** (nothing drawn — the caller draws its unchanged plain stroke and
  its own highlight) for no linetype, no pieces, a bad period, or a screen
  period < `LINETYPE_LOD_MIN_PERIOD_PX` (`hatch_render._device_scale`); else
  it draws via **`draw_expansion(painter, dash, dot, pen)`** (dashes FlatCap,
  then dots RoundCap) — the low-level half `BlockInstance.paint` calls with
  its own period / LOD decision. **Screen LOD is skipped on every paper pass**
  (`paper_pass_active()`), on-screen sheet viewports included — paper always
  expands. The missing id comes from `ResolvedStroke`, not from
  `paint_stroke`. Also here: `mid_point(pieces)` (raw badge anchor),
  `paint_missing_badge(painter, at)` (LT3-10 glyph, device space),
  `badge_pad_px()` (derived from the glyph's own reach + an AA pixel — one
  home with the drawing) and `sync_missing_tooltip(item, missing_id)`.
- **H3-d `stroke_style` cascade.** `resolve_stroke(style, registry)` →
  `ResolvedStroke(lt: LinetypeDef | None, weight: str, missing_id)` per LT3-8:
  the returned `weight` is already resolved (By Linetype → the dash weight
  when present), and callers pass it to the unchanged `canvas_px` /
  paper-width helpers. `linetype_block(ref, registry)` (the block when it has
  `repeat`, malformed or not, else None), `linetype_ref_missing(ref,
  registry)` and `is_linetype_ref(value)` (a non-empty value other than
  `continuous` / `by_block`) are the one shared "missing" test for paint,
  bounds and the registry.
- **H3-e RenderOp.** The stroke kind gains `pieces` (tuple, definition-local,
  origin-relative) and `linetype` (the style's raw value); `origin` is set to
  the definition origin `(0, 0)` and doubles as the stroke's phase anchor;
  `mapped()` maps pieces and anchor, so nested blocks keep their own
  definition's phase. `_compile` fills them for styled primitives with
  `stroke_pieces()` (mapped by the item transform + position − origin);
  reference-mode ops and placeholders leave them empty (always Continuous).
  Additive — the HD4a contract (`kind`, `pen`, order) is unchanged.
  **Explode** (D-L9 consequence): exploded primitives become the host's raw
  items, so their phase re-anchors from the nested definition's origin to the
  host definition's origin — dashes may shift.
- **H3-f Paint routing.** The 8 primitive `paint()`s replace their stroke +
  highlight with `Geometry2DMixin._paint_routed_stroke` (fill, reference
  guides unchanged): `_sync_stroke_pen()` returns this paint's
  `ResolvedStroke`; a record with nothing to expand (Continuous / By Block /
  malformed) and no missing state takes the unchanged plain path (LT3-11); otherwise `_paint_linetyped` calls
  `paint_stroke` (anchor = the scene origin mapped into the item — the Block
  Editor origin is fixed at (0, 0) since CS1; Rectangle draws its dashes in the
  unrotated item frame because its pieces carry the rotation), re-stroking the
  expansion with the highlight pen when selected, and `_paint_lt_badge` draws
  the glyph at mid-length unless `paper_pass_active()`. Raw length factor per
  LT3-5 (`_linetype_factor`; the paper factor reads the scene's viewport-pass
  `_hatch_paper_scale`). `BlockInstance.paint`: a block whose compiled ops name
  **no linetype id** (memoised on the op list's identity) paints the **pre-LT3
  loop** with zero LT3 bookkeeping; otherwise a **per-paint memo** resolves each
  distinct (linetype, weight) once (cascade, width, length factor, period
  check, screen LOD with the device scale read once under the pose) and strokes
  each op's expansion via `draw_expansion` under the pose
  (`painter.setWorldTransform(pose, True)`), so expansion is definition-local
  and shared by every instance. Nothing resolved outlives the paint (weight
  table, aliases, Model Blocks, Thin Lines, registry and drawing-scale edits
  reach the next paint); only the **expansion** crosses paints — held **per
  instance** (`_lt_exp_cache`), keyed on the compiled op list (held), the op
  index, the `LinetypeDef` reading and the exact factor (every `expand`
  input). The badge draws once at the insertion point, canvas only; the
  placement ghost (`_is_ghost`) skips routing and the badge. The tile lattice
  (`hatch_render`) is untouched.
- **H3-g `repeat` data** (mirrors HF2 `tile`). `BlockDefinition.repeat` =
  `{length, size: "drafting"|"model"}` | None via `_norm_repeat` and
  `set_repeat(repeat, *, notify=True)` (version bump → cache key); additive
  `.fpdb` / embed key (no schema bump); library `index.json` entries gain a
  `repeat` flag. `ends` defaults (LD1) stay LT5.
- **H3-h Integrity.** `block_registry.prim_refs` adds a styled primitive's
  `style.linetype` when `is_linetype_ref` → `referenced_ids`, `users_of`,
  `closure`, `bundle_for`, `would_cycle`, `invalidate` follow. Live users:
  `block_registry.linetype_users_in(scene, id)` and
  `Model_Space.linetype_user_contexts(id)` (the plan + open Block Editors via
  `_editor_scenes_provider`) feed `delete_block_definition` and
  `block_users_message`. `BlockRegistry.add` passes
  `invalidate(id, was_linetype=…)` (the replaced definition's `repeat`), and
  `invalidate` re-announces the bounds (`prepareGeometryChange`) of raw
  linetype users whenever the old or new definition is a linetype or the id
  vanished, so a flip to / from missing never leaves stale glyph bounds.
  Placement refusal (shared `set_mode` entry, armed click,
  `Model_View._resolve_block_drag`) + paste skip extended to `repeat` blocks.
  A cycle is never offered: the picker drops `hatch_patterns.picker_exclude`
  ids, and a Block Editor save that would cycle is refused (`would_cycle`).
- **H3-i Folder + picker.** `app_data.linetypes_dir()` (override
  `LINETYPE_DIR_KEY`, else `<block_library_dir>/System/Linetypes`). The folder
  scan moved out of `hatch_patterns` into **`capability_folder.scan(folder,
  flag)`** (`flag` ∈ `"tile"` / `"repeat"`; folder + two subfolder levels,
  `index.json` flag, one `.fpdb` parse cached per path + mtime serving both
  flags, scan cached per (folder, flag) + every mtime; never called from
  paint). **`linetype_choices.py`**: `linetype_choices(registry, exclude)`
  mirrors `tile_choices`; `linetype_ref_from_value`, `missing_label` /
  `is_missing_label`, and `ensure_linetype_available` (loads into the
  **project** scene via `blocks_browser.ensure_block_loaded`). The panel
  Linetype row uses it through `Geometry2DMixin._set_linetype_from_panel`
  (every linetype change goes through `_set_style_field`, which calls
  `prepareGeometryChange` for the glyph pad).

### LT3 guards (VC3) — as built

Files (all new): `tests/test_lt3_path_walk.py` (phase per piece type, split
exactness, `split_at_zero`, reflection refused), `test_lt3_expand.py`
(LT3-3 reading + malformed units, expansion, 0° restart, cache keys, bad
factor), `test_lt3_stroke_pieces.py`, `test_lt3_compile.py`,
`test_lt3_cascade.py`, `test_lt3_repeat_data.py`,
`test_lt3_primitive_paint.py` (G1 incl. an off-grid split, G2 through the real
Trim — far and near end — and Break tools, G-sel raw, G-canvas, HALO / snap /
`shape()` stay continuous), `test_lt3_block_paint.py` (plan drawing scale,
nested, Model size, ghost, G-sel placed block), `test_lt3_pdf.py` (G3, G4-LT3
incl. a raw plan primitive), `test_lt3_tile_continuous.py` (G-tile),
`test_lt3_missing.py` (G11, tooltip, bounds pad only while unresolved,
non-`repeat` ref, replaced-by-non-linetype announce), `test_lt3_integrity.py`
(G8-LT3 incl. delete refused for plan / open-editor lines and the combined
message), `test_lt3_picker.py`, `test_lt3_linetypes_folder.py`,
`test_lt3_paint_memo.py` (every memo input reaches the next paint),
`test_lt3_perf.py` (G-perf, LT3-11); shared fixtures in `tests/lt3_support.py`.

Contract-retired + rewritten: only
`tests/test_lt2_panel.py::test_rows_present_with_options` (the Weight row gains
By Linetype — seam ruling D). The three planned rewrites
(`test_lt1_block_paper._block_strokes`,
`test_lt2_style_record::test_weight_name_for_by_block_is_model_blocks`,
`test_render_op_compile`) proved unnecessary: the Continuous path is unchanged
and the RenderOp fields are additive.

## LT4 — `repeat` authoring: repeat frame, Pattern list, preview, badges (ratified 2026-10-05)

> Slice contract for LT4 (concept LD6 authoring half; D-L20, D-L23a, LT3-3).
> The *what* was settled in the LT4 Phase-2 grill (Q1–Q15, every row
> user-ratified, 2026-10-05) and the *how* (H4-a–H4-g) approved section by
> section in the brainstorm the same day. **BUILT 2026-10-06** on
> `feat/lt4-repeat-authoring`, verified `b9b1094` — the *How* and guards below
> are as built. Both P4 probes closed
> 2026-10-05 (H4-a / H4-d: `push_undo_state` is the single commit funnel —
> draw commits, `commit_paste`, editor import and Explode all push — so one
> pre-capture hook serves grow-to-fit and the lock; no undo amend). The Pattern-list
> layout was ratified on a browser mockup (layout A, 24 px rows, 64 px swatch)
> and then on the **live Qt render under the app QSS** (user-approved
> 2026-10-05, before build; rows = `M.PROP_FIELD_H`, swatch =
> `PATTERN_PREVIEW_H_PX`).
> The sticky current Linetype/Weight moved to WM1 (built); LT4 is authoring
> only.
>
> **Build-time refinements** (who ratified): the live Qt gate incl. the
> ▲ / ▼ / ✕ row glyphs (**user**, 2026-10-05); ribbon icon candidate A
> (**user**, 2026-10-05 — [`icon-style-guide.md`](icon-style-guide.md) §5
> deviation); the pre-placement template display rule (LT4-4), the A6 reword
> and the empty-stack baseline skip (H4-a) (**orchestrator rulings** at the
> reviews). Review findings folded in at Account: LT4-11e mixed wording,
> LT4-11f group name, LT4-12 pre-origin case.

### What (grill Q1–Q15)

- **LT4-1 Geometry canonical** (Q1; *amends D-L20*). The drawn axis Lines ARE
  the linetype (the LT3-3 reading); the Pattern list is a view and editor of
  them. Content the list can't express — overlapping dashes, a dot inside a
  dash — shows the note "Dashes overlap — edit on the canvas" and the rows (and
  the Weight row) are read-only. The list always shows exactly what the
  renderer reads.
- **LT4-2 Ripple** (Q2). Rows are sequential (Dash / Gap / Dot, a Dot has no
  length): editing a length, adding, removing or reordering a row shifts every
  later element; **Length = sum of the rows**. The frame grip and the typed
  Length row change only the trailing gap.
- **LT4-3 Weight** (Q3). One **Weight** row on the linetype (By Category
  (<Blocks weight>) | named) sets every axis dash Line's weight; hand-drawn
  differing weights show `< mixed >` and still read "heaviest wins" (LT3-3).
  By Category stores `by_linetype` on the dashes (→ Blocks category, WM-5).
- **LT4-4 Continuous lock** (Q4; *implements D-L23a at authoring*). While the
  edited block is a linetype, every primitive entering it is Continuous (the
  sticky current is not changed); a new draw also takes the linetype's Weight.
  A selected primitive's Linetype row is greyed ("Lines inside a linetype are
  always Continuous"). Turning Linetype on converts existing non-Continuous
  primitives in the same undo step ("N lines set to Continuous").
  *(Amended at the LT4 Account — orchestrator ruling, seam review: the
  pre-placement **Geometry template** shown while a draw tool is armed inside
  a linetype editor DISPLAYS what the next draw gets — Continuous and the
  linetype's dash Weight (the current Weight when there is no single dash
  weight) — with both rows locked; the stored current is untouched (WM-10).)*
- **LT4-5 Off while used** (Q5). Turning Linetype off is refused while any line
  uses the block (definitions, plan, an open Block Editor) — same data and
  wording family as delete; checked at the toggle and again at save.
- **LT4-6 Seed** (Q6, Q7). On: Length = the axis content's end from the origin
  (the list reads it); an empty unit seeds **Dash 6 · Gap 3**; Size seeds
  **Drafting** (D-L3; unlike hatch D-A38). One undo step.
- **LT4-7 Preview** (Q8). Canvas: the unit repeats one period each side of the
  frame at 35 % (the HF2 ring look). Panel: a swatch strip draws a sample line
  and an L polyline. Both draw through `linetype_render` (preview ≡ render) and
  update on every edit.
- **LT4-8 Other content** (Q9, Q10). A ripple moves only axis Lines; off-axis
  content stays put. List edits move / resize the existing Lines in place (same
  uid, style, constraints); a constraint the edit violates shows the existing
  red unsatisfied state; a removed row deletes its Line and its constraints.
- **LT4-9 Frame bounds** (Q12, Q13). Length never goes below the content end
  (the grip stops, a typed value reverts). Drawing or moving an axis Line past
  the end grows Length to fit in the same undo step; shrinking stays manual.
  Axis content before 0 reads clamped (LT3-3) and the list shows that.
- **LT4-10 Badges** (Q11). The Blocks browser badges linetypes (dash-dot glyph)
  **and** patterns on project **and** library rows (the library `index.json`
  `tile` / `repeat` flags); tooltip "Linetype — apply it from a line's
  Linetype row; it can't be placed".
- **LT4-11 Settled defaults** (Q14 a–i, batch-ratified): (a) Linetype on is
  refused while the block is placed as a symbol (instances or nested; counts in
  the message; re-checked at save — hatch D-A34 parity); (b) Linetype and
  Pattern tile are exclusive — turning one on while the other is on is refused
  with a status message; (c) **Save As keeps the linetype** (fixes the 1b
  finding: the new-definition path dropped `repeat`); (d) a new linetype is
  registered, never placed, and a Create-Block-from-selection source stays
  untouched; (e) the delete refusal for a linetype used by blocks' lines reads
  "“Hidden” is used by lines inside: Riser, Valve — change their linetype
  first." (nesting users keep "explode or remove it there"; *amended at
  Account:* when some blocks nest it and others' lines use it, both clauses
  appear — "“Hidden” is used inside: Host, and by lines inside: Riser —
  explode or remove it there, and change their linetype first." — and a block
  that does both is named in both); (f) a ribbon
  **Linetype** toggle beside Pattern Tile in the Block Editor tab's
  **Definition** group (*amended at Account*; the spec first said "Block"),
  checked state synced with the panel and undo / redo; (g) every toggle, list
  edit, Weight / Size change and grip drag is one undo step; (h) tooltips on
  every new control; (i) the Pattern list, frame and swatch are mockup-gated.
- **LT4-12 Edge cases.** The last remaining dash / dot can't be removed (✕
  disabled: "A linetype needs at least one dash or dot"); lengths must be > 0
  (a bad entry reverts); undo / redo restores the capability, the Lines and
  the frame together; reopening a linetype loads its capability into the undo
  baseline. *Known behaviour (added at Account, review G4 M-6):* turning
  Linetype on when the only axis content lies before the origin (e.g. a Line
  −5..−1) finds no counted axis Line, so it seeds Dash 6 at 0..6 and the
  pre-origin Line stays as dead on-axis content (the reading ignores it; the
  list does not show it).

### How (H4-a–H4-g) — as built

- **H4-a One capability slot** (approach A). `Model_Space.block_capability` =
  `None | ("tile", {w, h, row_shift, size}) | ("repeat", {length, size})`
  replaces `block_tile`; one setter `set_block_capability(cap, *,
  push_undo=True)` syncs the frame item. A `repeat` payload is normalised
  there through `block_definition._norm_repeat` (every reader may index
  `["length"]` / `["size"]`); an empty payload clears the slot. The frame for a
  new kind is built (`capability_frame.frame_for`) **before** any mutation, so
  an unknown kind raises `ValueError` with the slot and frame unchanged. One
  undo-snapshot key `"block_capability"` (restore also accepts a legacy
  `"block_tile"` key). Read-only copy views `block_tile` / `block_repeat`;
  `capability_frame_item()` (either kind) and `tile_frame_item()` (tile only);
  `set_block_tile` stays as the HF2 alias (passing None clears whatever
  capability is set). The slot holds one capability; LT4-11b's refusal
  message lives in the toggle (H4-e). **Pre-capture hook:**
  `push_undo_state` — after its undo-restore / suspended guard, before
  `_capture_network` — calls `linetype_authoring.pre_capture(scene)` when
  the slot is a `repeat` **and the undo stack is non-empty**: grow-to-fit
  (LT4-9) and the Continuous lock (H4-d) join the commit's snapshot (P4
  closed: no amend). The empty-stack (re-baseline) push is skipped, so
  reopening a linetype never mutates the saved definition (orchestrator
  ruling, review G4). The hook never pushes, so it cannot recurse.
- **H4-b Shared frame.** Both frames subclass
  `capability_frame.CapabilityFrameItem` — the shared chrome (overlay tag,
  exclusions, ring clip + opacity, scratch definition) is owned by
  [`hatch-and-fill.md`](hatch-and-fill.md) §2 "Block Editor capability
  frame". LT4's subclass `repeat_frame.RepeatFrame` (`KIND = "repeat"`): rect
  from the origin to Length, ± `REPEAT_FRAME_HALF_H_MM` about the axis; one
  circular, X-only Length grip that sets the trailing gap and stops at
  `max(grip x, linetype_pattern.content_end(...), 0.1 mm)` (LT4-9), writing
  the slot with `push_undo=False` (the manipulator's commit pushes the one
  step); the ring is one period each side, drawn by `expand` +
  `draw_expansion` of the frame's scratch definition (LT4-7). A malformed
  repeat (no / non-numeric `length`) reads as Length 0 — bounds and paint never
  raise inside a Qt virtual.
- **H4-c Rows ⇄ geometry.** One per-Line LT3-3 rule,
  `linetype_render.axis_role(p1, p2, length)`, serves both
  `LinetypeDef.from_block` and the list. `linetype_pattern.py` (pure, no Qt
  items): `rows_from_reading(dashes, dots, length)` (leading / between /
  trailing gaps, touching dashes = adjacent Dash rows, a dot at a dash's start
  sorts first, `None` when dashes overlap or a dot sits inside a dash),
  `spans(rows)` → `(spans, period)`, `content_end` / `axis_end` (unclamped
  far end of the axis Lines — the one LT4-9 rule), `validate_rows` (≥ one dash
  or dot; every dash / gap > `LINETYPE_AXIS_TOL_MM`) and `SEED_ROWS`.
  `linetype_authoring.apply_pattern_rows(scene, rows, *, push_undo=True) ->
  bool` (a module function, not a `Model_Space` method) matches axis Lines to
  spans in x order per kind (dash ↔ non-zero Line, dot ↔ zero-length Line),
  moves / resizes matches in place (same item, uid, style, constraints),
  removes extras (`ConstraintController.on_items_removed` drops their
  constraints), creates the rest through the owning editor's `_add_primitive`
  (Continuous, the current dash weight) and sets Length = period — one undo
  step. It returns False **before any mutation** when the rows fail
  `validate_rows`, equal the live `current_rows` within tolerance (a
  re-commit adds no step), the scene is not a linetype, or a new mark is
  needed but the scene has no owning Block Editor. A constraint on a moved
  Line that the ripple violates goes red live through
  `ConstraintController.mark_unsatisfied_red` (the D38 rule, shared with
  paste), so live red equals the red an undo / redo restore derives (LT4-8).
  `set_pattern_weight(scene, weight)` stamps every axis dash in one step
  (none when nothing changes); `set_repeat_field(scene, key, value)` edits
  Length (refused — the panel shows the old value — when ≤ 0, below the
  content end, or unchanged) and Size, one step each.
- **H4-d Lock.** `pre_capture` (the H4-a hook) sets every non-Continuous
  styled primitive in a `repeat` scene to Continuous — covering draw commits,
  paste, Block-Editor import and Explode (P4 closed: all four push; A3 drives
  each real entry). New draws take Continuous **and** the linetype's dash
  weight at creation through a `block_repeat` branch in
  `stroke_style.apply_current` (`pattern_weight(scene)`, else the current
  Weight; the current itself is not changed). `stroke_rows(..., locked=True)`
  disables a selected primitive's Linetype row with the tooltip "Lines inside
  a linetype are always Continuous" (`Geometry2DMixin.get_properties` passes
  `locked` when its scene has a `block_repeat`). The pre-placement
  `GeometryTemplate` in a linetype editor shows the rows the next draw gets —
  Continuous + `pattern_weight` (else the current Weight) — both disabled,
  Weight tooltip "New lines take the linetype's Weight (set it in the Repeat
  section)" (LT4-4 amendment).
- **H4-e Toggle + save.** `BlockEditorWidget.toggle_capability(kind)`
  (`toggle_pattern_tile` stays a thin alias; an unknown kind raises
  `ValueError`). Off: a linetype is refused while used
  (`Model_Space.linetype_off_refusal` → the delete refusal's
  `block_users_message`, LT4-5). On while the other capability is on: refused
  with "Turn Pattern tile off first — a block is a pattern or a linetype, not
  both" (or "Turn Linetype off first — …" the other way). On while placed:
  `symbol_use_refusal(block_id, kind)` ("Used as a symbol (N placed, M nested
  in other blocks) — remove those before making it a linetype"; the HF2 name
  `pattern_use_refusal` stays as a tile alias). Linetype on runs
  `linetype_authoring.begin_linetype(scene, content_end)` (convert to
  Continuous, set the repeat — Length = content end, Size Drafting — and seed
  `SEED_ROWS` into an empty unit) then pushes once, with the status
  "N lines set to Continuous" when any converted. Opening a definition puts
  its tile or repeat into the slot before the undo re-baseline (LT4-12).
  `commit_block_definition(..., capability=)` (the editor passes
  `block_capability`): re-runs LT4-11a on any capability, never places a new
  pattern / linetype ("Saved linetype ‘X’ — linetypes aren't placed; your
  original geometry is unchanged."), refuses dropping a used linetype's repeat
  (LT4-5), and sets `tile=` / `repeat=` on `BlockDefinition.new` or
  `set_tile` + `set_repeat` on the edit path (so Save As keeps it, LT4-11c).
- **H4-f Panel + widgets.** `capability_panel.py` is the one home of the
  capability rows: `capability_rows(scene)` feeds both the nothing-selected
  `BlockPropertiesInfo` and a selected frame (`CapabilityFrameItem.get_properties`);
  `set_capability_property(scene, editor, key, value)` writes back (the two
  toggles go through `toggle_capability`). Rows: a **Repeat** header, then
  `Pattern tile` + `Linetype` bools; a tile adds `tile_frame.tile_properties`
  (owned by `hatch-and-fill.md`); a linetype adds —
  `Length` (dimension; `minimum` = content end − 1e-6, because
  `DimensionEdit`'s minimum is strict, so a typed value below the end reverts
  at once and Length = end is accepted), `Size` (Drafting | Model),
  `Weight`, a **Pattern** header + `Pattern rows` (row type `pattern_list`;
  value None + note "Dashes overlap — edit on the canvas" when
  unrepresentable), a **Preview** header + `Preview swatch` (row type
  `stroke_preview`, `paint = linetype_authoring.preview_painter(scene)`,
  height `PATTERN_PREVIEW_H_PX`). **Weight row:** options
  "By Category (<Model Blocks weight>)" + the named weights (By Category
  stores `by_linetype`); `< mixed >` when the dashes differ (a `< mixed >`
  pick is ignored); a dash weight that is not a current weight name is
  offered as its own option, never silently replaced; disabled when the rows
  are unrepresentable, and for a **dots-only** unit it shows By Category,
  disabled, tooltip "Add a dash to set the linetype's Weight". **Swatch:** a
  straight sample plus an L polyline, `PATTERN_PREVIEW_PERIODS` periods across,
  through `expand` + `draw_expansion` of the frame's scratch definition, pen =
  `canvas_px` of the dash weight (By Linetype when none). Panel integration —
  the two row types, the frame dropped from a multi-selection,
  `BlockPropertiesInfo._scene_ref` (the nothing-selected panel follows the
  display units) — is owned by [`property-panel.md`](property-panel.md)
  §3.1 / §3.2 / §3.5; the widgets `ui_kit.PatternList` / `PaintSwatch` by
  [`ui-design-system.md`](ui-design-system.md). The form rebuilds on every
  commit (50 ms debounce), so the list never relies on focus across a commit.
- **H4-g Ribbon, badge, wording.** Ribbon **Linetype** checkable small
  button (`MainWindow._be_linetype_btn`, `linetype_icon.svg`) in the Block
  Editor tab's **Definition** group beside Pattern Tile, tooltip "Linetype —
  make this block a linetype (repeats along lines, applied from a line's
  Linetype row, can't be placed as a symbol)". `_be_toggle_linetype` /
  `_be_toggle_tile` → `_be_toggle_capability(kind, checked)` (a refused
  toggle snaps the check back); `_sync_tile_button` → `_sync_capability_buttons`
  (signals blocked), connected to each editor's `sceneModified` and re-run by
  `_set_block_editor_context` (tab switch / close). Badges: `blocks_browser._linetype_badge(dpr)` (muted dash-dash-dot
  glyph; `_BADGE_CACHE` keyed by kind, muted colour, dpr) beside
  `_pattern_badge`, picked by `_capability_badge(kind, dpr)` on **project**
  rows (the definition's tile / repeat) **and library** rows (the index
  `tile` / `repeat` flags, from the refresh's single `list_library` read);
  linetype tooltip "Linetype — apply it from a line's Linetype row; it can't
  be placed". Wording: `block_users_message` hands a linetype to
  `_linetype_users_message`, which names the blocks whose **own** lines use it
  ("“Hidden” is used by lines inside: Riser, Valve — change their linetype
  first."), adds the live contexts ("…, and by lines in the plan and in the
  open Block Editor — …"), keeps pure nesting on the D12 wording ("“B” is used
  inside: A, D — explode or remove it there first."), and for mixed users
  emits both clauses ("“Hidden” is used inside: Host, and by lines inside:
  Riser — explode or remove it there, and change their linetype first."). No
  new paint path: ring and swatch use the LRU-cached `expand` on a handful of
  pieces — no new perf bench; LT3 perf guards stay keep-green.

### LT4 guards (VC3) — as built

Acceptance guards A1–A9 (ratified with the *how*; each is met by the files
listed after them):

- **A1 List → geometry** — real Block Editor: Dash 6→8, add Dot, reorder,
  remove → axis Line coordinates match, Length = sum, off-axis items unmoved,
  one undo step each, Ctrl+Z restores the exact Lines.
- **A2 Geometry → list** — drawn axis Lines (incl. past the end, and an
  overlap) → rows = `LinetypeDef.from_block`; frame grew; overlap → read-only.
- **A3 Continuous lock** — current Hidden: a drawn line is Continuous; toggle-on
  converts 2 Hidden lines with the count message; the Linetype row disabled.
- **A4 Refusals** — on while placed as a symbol; on while Pattern tile is on;
  off while another block's lines use it → refused, state unchanged; the save
  re-check refuses too.
- **A5 Round-trip (G8 authoring half)** — author → Save → use on a line →
  `.fpd` save / load → undo / redo → Save As → `.fpdb` export / import:
  `repeat` + Weight survive; the Save As copy is a linetype; the bundle carries
  the weight names.
- **A6 Preview ≡ render** — *(reworded at Account, orchestrator ruling on seam
  review M4)* the swatch and the canvas ring draw through the same renderer
  path (`expand` + `draw_expansion`) as canvas strokes: the swatch guard
  compares its pixel coverage with a direct `expand` + `draw_expansion` of the
  same pieces / factor / pen; the ring has its own pixel guard.
- **A7 Badge** — project + library linetype / pattern rows carry badge +
  tooltip.
- **A8 Delete wording** — the exact LT4-11e message.
- **A9 Ribbon sync** — real MainWindow: panel toggle, ribbon toggle, undo /
  redo → button check state follows.

Keep-green: the HF2 tile tests (tile frame, D-A34 refusals), 
`test_block_editor_ribbon_tab` + `test_icon_theming` (ribbon roster, VC5),
`test_block_usage_counts`, `test_lt3_*`, `test_wm1_*`,
`test_property_panel_header`. Live smoke: author Hidden from an empty block,
apply it to a line in another block, check plan and PDF.

Files (all new, under `tests/`):

- `test_lt4_pattern.py` — pure rows ⇄ reading: `axis_role` = LT3-3,
  sequential rows, leading gap + touching dashes, overlap / dot-inside →
  None, dot at a dash start, `spans` round trip, `content_end` (unclamped,
  axis only), `validate_rows` (incl. a sub-tolerance dash), `SEED_ROWS`.
- `test_lt4_capability_slot.py` — H4-a: slot views + undo, copy views,
  legacy `block_tile` snapshot restore, undo / redo across a tile ⇄ repeat
  switch, re-set after `scene.clear()`, repeat payload normalised.
- `test_lt4_repeat_frame.py` — H4-b: both frames share the base + tag, Length
  grip (trailing gap, clamp), not deletable / not a snap target, ring paints
  dashes outside the frame (the ring pixel guard), malformed repeat never
  raises, `frame_for` rejects an unknown kind.
- `test_lt4_authoring.py` — A1 (ripple in place, one step, reorder / remove,
  invalid rows refused, removed row drops its Line **and** constraints,
  violated constraint red live and after undo / redo), A2 (rows = the
  renderer reading, overlap unrepresentable, draw past the end grows in the
  same step), A3 (lock on commit + draw takes the Weight; real paste,
  editor import and Explode entries), Weight row, no-editor refusal before
  mutating, one-step counts for the grip drag (live manipulator), Size and
  Weight, panel `< mixed >`.
- `test_lt4_toggle.py` — LT4-6 seed (empty → Dash 6 / Gap 3, Drafting, one
  step; content → read + convert with the count), A4 (on while placed, both
  exclusivity wordings, off while used — behaviour and exact wording — and
  both save re-checks), unknown kind raises, LT4-11c / 11d (Save As keeps
  it, never placed, Create-from-selection source untouched), LT4-12 (reopen
  into the baseline; the hook does not mutate it).
- `test_lt4_panel.py` — rows for a linetype (tooltips), overlap read-only +
  note, Length below the content end reverts (immediately in the field), real
  widgets commit through `DimensionEdit`, primitive Linetype row locked only
  in a linetype, selected frame = nothing-selected rows, swatch through the
  real renderer, imperial display units in the nothing-selected panel,
  frame dropped from multi-selections (both orders, plus tile + Rectangle),
  same rows twice = one step, dots-only Weight row (By Category, disabled,
  why-tooltip), unknown dash weight shown, the Geometry template inside /
  outside a linetype.
- `test_lt4_widgets.py` — `PatternList` / `PaintSwatch` domain-free: whole-list
  commits, move / remove / add, last dash or dot can't be removed, read-only
  note, every control has a tooltip, swatch paints its rect.
- `test_lt4_preview.py` — A6 (seed and authored swatches = a direct
  `expand` + `draw_expansion`).
- `test_lt4_roundtrip.py` — A5 through the real editor: author → undo / redo
  → Save → edit-in-place Save → use on a line → `.fpd` save / load → Save As
  → `.fpdb` bundle carrying `repeat` + the weight name → load.
- `test_lt4_browser_wording.py` — A7 (linetype + pattern badges on project
  and library rows), A8 (line-user wording, pure nesting, mixed nesting +
  line users, a block in both clauses), one `list_library` read per refresh.
- `test_lt4_ribbon.py` — A9 on a real MainWindow (own pytest process): panel,
  ribbon and undo toggles; redo, two-editor tab switch and close.
- `test_lt4_ref_pages.py` — the LT4 modules are listed in the API-reference
  `TIERS` beside `tile_frame` (`docs/gen_ref_pages.py`).

Rewritten for the contract change: `test_block_editor_ribbon_tab.py` (the
editor-only roster gains "Linetype") and `test_icon_theming.py`
(`linetype_icon.svg` joins `_BLOCK_ICONS`).

## Acceptance Criteria

- [x] Collinear lines sharing a linetype are indistinguishable from one line (D-L9) — LT3 G1 (`tests/test_lt3_primitive_paint.py`), 2026-10-05.
- [ ] Every row of the cascade (Weight model WM-2..WM-12; D-L4/5/6/17 superseded) resolves to the stated weight/linetype/colour on canvas and PDF.
- [ ] Ends obey D-L7/8/8b; symbols obey D-L15; end attributes obey D-L10.
- [ ] Weights travel with `.fpd`/`.fpdb` (D-L13); legacy files migrate (D-L17a).
- [ ] D-L21 bar met on the confirmed bench.
- [ ] Guards G1–G11 in the concept doc pass.

## Verification Checklist

- [ ] Guards G1–G11 (concept doc) RED with the change reverted, GREEN with it.
- [ ] Full suite green; registry-enumerating tests updated (concept doc keep-green list).
- [ ] Cross-spec reconciliation below applied when each slice lands.

## Cross-spec reconciliation (to amend when the build lands — Rule A)

- `block-system.md` — `repeat` / `end` capabilities; placement + nested-record `style` slot; `referenced_ids`; StrokeOp compile; Blocks category weight. *(LT3 part — `repeat`, linetype refs in `referenced_ids`, stroke-op pieces — applied 2026-10-05: "Linetype capability (LT3)" pointer.)*
- `2d-geometry.md` §1 — `style` record replaces px `lineweight`; current-style defaults; §1.2 "lineweights never scale" stays. *(LT3 pointer — `stroke_pieces()` + paint routing — applied 2026-10-05.)*
- `paper-space.md` — raw primitives on a sheet: By Linetype fallback → Construction (WM-12); BlockInstance category; project-scoped weights.
- `2026-05-12-paper-space-display-manager-design.md` §7.2 — weights move from QSettings to the project.
- `hatch-and-fill.md` HD4 — RenderOp stroke half = StrokeOp (one refactor). *(Applied 2026-10-05: LT3 extended the `stroke` kind with `pieces` / `linetype`; the folder scan moved to `capability_folder.py`.)*
- `grid-system.md` §16 — linetype property becomes the gridline-from-primitives follow-up.
- `view-relationships.md` §7.4 — catalog rows 2 and 4 point here.
- `units-and-formatting.md` — line-weight display convention (named weight + mm).
- `feature-system.md` — pipe as a Feature (D-L22).
- **LT4 (applied 2026-10-06, LT4 Account, `b9b1094`):** `hatch-and-fill.md` §2
  — the frame is now `TileFrame` on the shared `capability_frame` base (that
  file's home) and the nothing-selected rows come from `capability_panel`;
  `block-system.md` — "Block Editor capability slot (LT4)" pointer
  (`block_capability`, `symbol_use_refusal`, library-row badges) + the stale
  `pattern_use_refusal` mention fixed; `property-panel.md` — `pattern_list` /
  `stroke_preview` row types (§3.2), the frame never joins a multi-selection
  (§3.5), `BlockPropertiesInfo._scene_ref` (§3.1); `ui-design-system.md` —
  `PatternList` / `PaintSwatch` entries; `icon-style-guide.md` §5 —
  `linetype_icon.svg` deviation; `SPEC-INDEX.md` rows.
