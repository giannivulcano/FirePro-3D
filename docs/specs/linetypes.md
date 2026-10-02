---
status: proposal         # greenfield — nothing below is built; D-L1–D-L23 ratified in the 2026-10-02 concept grill (Q1–Q23); how = docs/superpowers/specs/2026-10-02-linetypes-concept-design.md (LD1–LD7, ratified in the brainstorm)
last-verified: 2026-10-02
verified-commit: 18df05d
applies-to:               # planned modules (none exist yet) + the seams they change
  - firepro3d/stroke_style.py        # planned — cascade resolution
  - firepro3d/path_walk.py           # planned — arc-length walker + axis phase
  - firepro3d/linetype_render.py     # planned — expansion renderer
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
  D-A10).
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
  Continuous (no recursion); (b) explode, copy, mirror and modify tools keep
  Linetype/Weight/ends — new free ends from break/trim get By Linetype ends;
  (c) mirror flips end blocks, text stays upright; (d) closed shapes never
  draw ends; (e) a missing linetype/end block draws Continuous/Flat plus a
  visible warning badge, never nothing.

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
