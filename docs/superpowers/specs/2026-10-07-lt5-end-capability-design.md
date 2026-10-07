---
status: proposal   # designed 2026-10-07 (Phase 2 Q1–Q15 + design groups A–D user-approved); unbuilt
last-verified: 2026-10-07
verified-commit: cbe41a15
applies-to:
  - firepro3d/stroke_style.py
  - firepro3d/render_op.py
  - firepro3d/path_walk.py
  - firepro3d/linetype_render.py
  - firepro3d/end_render.py          # new
  - firepro3d/end_authoring.py       # new
  - firepro3d/capabilities.py        # new
  - firepro3d/capability_frame.py
  - firepro3d/capability_panel.py
  - firepro3d/capability_folder.py
  - firepro3d/linetype_choices.py
  - firepro3d/hatch_patterns.py
  - firepro3d/block_definition.py
  - firepro3d/block_instance.py
  - firepro3d/block_registry.py
  - firepro3d/block_library.py
  - firepro3d/block_editor.py
  - firepro3d/block_explode.py
  - firepro3d/blocks_browser.py
  - firepro3d/geometry_2d.py
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/app_data.py
  - firepro3d/settings/panes.py
  - main.py
source-tasks: [todo_open.md "LT5 — `end` capability"]
---

# LT5 — End capability — Design

> The *what* is owned by `docs/specs/linetypes.md` "Ends" (D-L7, D-L8, D-L8b,
> D-L10, D-L11, D-L23c/d/e), WM-11 and LTS-9f, plus this run's Phase-2
> rulings Q1–Q15 (below, which amend some of those rows). This doc is the
> *how*; on build it is folded into an "LT5 — as built" section of that spec
> (Rule A — the spec stays the one home).

## Goal

Users author **end types** as blocks (End type capability in the Block
Editor) and put them on the free ends of open 2D strokes — per line, or as a
linetype's default — drawn at a printed or weight-relative size, trimming the
stroke, on every surface (Block Editor, placed blocks on the plan, paper/PDF),
persisted, undoable and counted by every integrity path.

## Motivation

End-goal consumer (Q1): the **gridline** (primary line + two leaders with
toggleable Grid Bubble ends) as System geometry built from primitives; the
near-term user-visible case is drafting leaders / arrows / ticks / dots.
Pipes are out (pipe ends are fittings).

## Phase-2 rulings (user-ratified 2026-10-07)

- **Q2 Which strokes.** Ends draw on open Line, Polyline (closed flag off),
  Arc (span < 360°) and Spline only — the item's own closed predicate
  decides; a coincident-but-open polyline draws both ends; interior vertices
  never.
- **Q3 Default.** Any open line (Continuous included) may carry explicit ends.
  New keyword **None**; By Linetype on Continuous / on a linetype without a
  default resolves to None = **today's stroke unchanged** (square-cap
  parity). Legacy drawings stay canvas- and PDF-identical.
- **Q4 Fixed size** = printed mm under the **Drafting length rule** (LT3-5):
  true mm on paper, × project drawing scale on the plan canvas, real size in
  the Block Editor; **never** screen-constant, even on an On screen = Fixed
  linetype (answers LTS-9f).
- **Q5 Units + Trim.** Origin = attach point (the line endpoint), +X =
  outward. Fixed: 1 authored mm = 1 printed mm. Weight-relative: 1 authored
  mm = 1 × the line's weight. Trim (≥ 0, same units, along the path) stops the
  stroke that far back; trims ≥ the line length → no stroke, both ends still
  draw.
- **Q6 Orientation.** −X points from the endpoint to the trim point (chord);
  trim 0 → the endpoint tangent.
- **Q7 Look.** All end content (strokes, fills) draws in the **using line's
  colour** (authored component colours wait for HF1's By Line token —
  follow-up); end strokes draw at the line's **resolved weight** (placement
  Weight override included, WM-11).
- **Q8 Content.** Continuous strokes (locked), fills / hatch fills, static
  text (rotates with the end until LT6); no nested blocks, no linetypes.
- **Q9 Mirror.** Each end stays on its physical end (fixes `ArcItem.manip_reflect`
  swapping start/finish geometry without the style); a persisted mirrored flag
  flips asymmetric ends. Placements can't mirror today — out of scope.
- **Q10 Panel.** Start End / Finish End (By Linetype (<resolved>) | None |
  project ends | End Types folder) + Start / Finish Visible on open
  primitives; Visible off = None but keeps the pick; one undo step each;
  closed shapes hide the rows; no placement end rows; no template current.
- **Q11 Linetype defaults.** Start End / Finish End rows on the Linetype
  capability panel (default None); swatch shows ends; By Linetype lines
  follow on commit.
- **Q12 Authoring.** Ribbon **End type** toggle (exclusive with Pattern tile
  / Linetype); attach glyph + +X arrow + faint sample line from −X; rows Size
  (Fixed | Weight-relative, default Fixed), Trim (default 0) + X-only trim
  grip, Preview (thin + heavy sample); off refused while used; Continuous
  lock; not placeable as a symbol; browser badge. Look is mockup-gated.
- **Q13 Missing / integrity.** Missing end → None + red badge at that end
  (canvas only; "Missing: <name>" in the panel) — *amends D-L23e "Flat"*;
  delete refused while used ("used by N lines / linetypes"); `.fpdb` bundles
  ends incl. via linetype defaults; **End Types** library folder + Settings
  row; rename / cycle via the reference graph.
- **Q14 Interactions.** Trim never re-phases dashes (D-L9, LTS-4) incl.
  splines; an LTS short line drawn Continuous still draws its ends;
  placements use the effective weight, ends never swapped; Explode keeps ends
  + mirrored flag verbatim; copy / paste / undo / `.fpd` / `.fpdb` round-trip;
  snap / HALO / hit-test stay on the base line (LT3-6); bounds cover ends;
  selection highlight includes ends; ends never LOD-dropped; LT2-3 free-end
  table unchanged.
- **Q15 Scope + perf.** One run. Report-only bench: 2,000 lines, 400 with
  Arrow + Dot ends, pan/zoom; ends ≤ 1.3× the no-ends scene, end-less lines
  ≤ 1.1× base. Filed out: HF1 end-content colours, LT6 upright / `@[key]`,
  LT7 shipped End Types, placement mirror, per-placement end overrides.

## Architecture & Constraints

- **Flyweight compile** (`block-system.md`): end blocks are resolved and
  drawn at **paint**, never compiled into the host's op list (size depends on
  paint-time weight and device scale; `path_walk.map_piece` refuses
  reflection).
- **One renderer** for raw primitives, `BlockInstance` and paper/PDF (concept
  constraint) — the new `end_render.py`.
- **Capabilities, not kinds** — `end` beside `tile` / `repeat`, one slot,
  mutually exclusive.
- **Fast paths untouched for end-less strokes** (parity guard E1, perf bar
  1.1×).
- Snap / HALO / `shape()` stay on the untrimmed base geometry (LT3-6).

## Design Decisions (groups A–D, user-approved 2026-10-07)

### A — Data and cascade

- `BlockDefinition.end = {size: "fixed" | "weight_relative", trim: mm}` via
  `_norm_end` (bad size → fixed; trim non-numeric / negative → 0). One shared
  capability setter body replaces the twin `set_tile` / `set_repeat` bodies.
- `repeat.ends = {start, finish}` holding end ids; omitted when None (existing
  linetypes byte-identical). `_norm_repeat` keeps it; `LinetypeDef` gains
  `start_end` / `finish_end`.
- Line record per end `{end: "by_linetype" | "none" | <id>, visible,
  mirrored?}` — `NONE = "none"` keyword; `mirrored` per end (Join takes each
  outer end from its own source), written **only when true** (default dicts
  and LT2 goldens unchanged).
- `stroke_style.resolve_ends(style, lt, registry) → (ResolvedEnd, ResolvedEnd)`,
  each `(defn | None, missing_id | None, mirrored)`: By Linetype → the
  linetype default; Visible off → None; unknown / non-end id → None +
  `missing_id`.
- `RenderOp.ends` — the two end records for open strokes (None when closed),
  captured at `_compile`; `apply_overrides` carries it.
- *Rejected:* one per-line mirrored flag; always writing `mirrored: false`.

### B — Geometry

- `path_walk.end_frame(pieces, which, trim) → (attach, outward unit)` — chord
  to the trim point, tangent when trim = 0; `trim_pieces(pieces, s0, s1)`
  cross-piece on `split`.
- `linetype_render.expand(..., trims=(s0, s1))` walks the **untrimmed**
  pieces and drops dash runs outside `[s0, L − s1]` — phase identical by
  construction for every piece kind (E12).
- Mirror: every `manip_reflect` toggles both ends' `mirrored`;
  `ArcItem.manip_reflect` also swaps `style.start` / `style.finish` (E5).
  Paint adds `scale(1, −1)` in the end frame for a mirrored end.
- Bounds: `boundingRect` grows by the ends' extent — Fixed exact in model
  units; weight-relative padded like today's pen-width convention.
- *Rejected:* trimmed-piece expansion with a curve phase offset; QPainterPath
  clipping.

### C — Rendering integration

- New `end_render.py`: `EndDef.from_block(defn)` (compiled ops + size + trim,
  cached on `(id, version)` like `LinetypeDef`); `paint_ends(painter, pieces,
  ends, pen, *, fixed_factor) → (s0, s1)` draws each end's ops under
  `translate(attach) · rotate(outward) · scale(k) [· scale(1, −1)]`: strokes
  with the line's pen (colour + resolved width — cosmetic widths survive the
  scale, **P4 probe = plan step 1**), fills brushed in the line colour, text
  glyph fill.
- k: weight-relative = the pen width in painter units (canvas cosmetic px ÷
  device scale; paper mm ÷ scale); Fixed = `printed_factor(paper_scale, role,
  drawing_scale)` extracted from `length_factor`'s Drafting branch (one rule,
  two callers).
- Callers: `Geometry2DMixin._paint_routed_stroke` (raw primitives, Block
  Editor, paper) and both `BlockInstance` op paths (plain + linetyped).
- Fast paths: end-less strokes take today's path unchanged; Continuous with
  ends strokes a cached trimmed path (MW crisp split keyed on it); the
  expansion cache key gains the trims. Missing badge at the end point;
  `sync_missing_tooltip` takes a list of ids.
- *Rejected:* compiling ends into the op list; a child `BlockInstance` per end.

### D — Authoring, panel, integrity

- `capabilities.py` table (kind → noun, place-refusal reason, library flag,
  badge) drives the three-way toggle exclusivity, `commit_block_definition`
  wording, `symbol_use_refusal`, one `capability_place_reason(defn)`
  (replacing the copies in `set_mode`, `_press_place_block`, paste and
  `model_view` drop), browser kind derivation, library index flags and
  `capability_folder.FLAGS`.
- One picker source `capability_choices(flag, folder, fixed)` +
  `ensure_capability_available`; linetype / pattern / end pickers are thin
  callers.
- Block Editor: `EndFrame(CapabilityFrameItem)` (attach glyph, sample line,
  trim grip; `frame_for` branch); `end_authoring.py` (seed, fields, preview
  painter) mirroring `linetype_authoring`; `capability_panel` end branch +
  linetype Start/Finish rows; ribbon `_be_end_btn` in `_sync_capability_buttons`.
- Panel: `stroke_rows` adds 4 rows on open items; `end_label` /
  `end_from_label`; `_geom2d_set` keys; folder pick loads first, failure
  restores (WM2 H5 pattern).
- Integrity: `prim_refs` + explicit end ids; `referenced_ids` + `repeat.ends`;
  `end_users_in` + `invalidate(was_end=)`; end-off and delete refusals;
  `app_data.end_types_dir` + Settings row.
- Mockup gate **passed 2026-10-07** (served HTML, user-ratified): attach
  glyph = accent crosshair (±8 px) + a +X arrow (arm 28 px, cosmetic) at the
  origin; **no** frame box around the content; sample line = 35 % ink
  (`PREVIEW_OPACITY`) from −X, 18 mm long, ending at the trim point; trim
  grip = the circular LT4-style grip on the axis at x = −trim (X-only, ≥ 0);
  panel rows header "End type" · Size · Trim · Preview (`PaintSwatch`: the
  end on a Thin and a Heavy sample line).

## Acceptance Criteria

- [ ] Q2–Q14 behave as ruled on canvas, Block Editor and paper/PDF.
- [ ] Legacy drawings are canvas- and PDF-identical (E1).
- [ ] One renderer serves raw primitives, placements and PDF; flyweight
      compile preserved.
- [ ] Every new end reference participates in bundling, delete refusal,
      cycles and invalidation.

## Verification Checklist (guards — VC3: real path, observable ground truth)

- **E1 Parity** — legacy golden (canvas + parsed PDF) recorded at base
  `cbe41a15`, passes at base and HEAD.
- **E2 G5 sizes** — Arrow (Fixed 3 mm) on Light and Heavy → parsed PDF arrow
  length 3.0 mm (±0.05) both; Round (Weight-relative) radius = ½ weight; a
  closed shape with ends set draws none.
- **E3 Trim** — PDF stroke endpoint at the trim distance; over-trim → no
  stroke, both end blocks.
- **E4 Arc orientation** — end aligned on the endpoint→trim-point chord.
- **E5 Mirror** — mirrored Arc keeps the arrow on the same physical end (RED
  with the swap reverted); a one-sided half-arrow flips.
- **E6 Cascade** — linetype default end; explicit overrides it; editing the
  default redraws By Linetype lines.
- **E7 Placement** — a placement Weight override scales weight-relative ends;
  ends never swapped.
- **E8 Missing** — None + badge on canvas, no badge in the PDF.
- **E9 Round-trip / integrity** — `.fpd`, undo/redo, paste, Explode, `.fpdb`
  bundle; delete refused while used.
- **E10 Panel (real MainWindow)** — folder end pick loads + one undo step;
  Visible toggle; closed shapes show no end rows.
- **E11 Authoring** — toggle exclusivity, trim grip, off refusal, symbol
  refusal.
- **E12 Dash phase** — dashes outside the trims pixel-identical with / without
  ends, spline included.
- **Bench** (report-only) — Q15 shape and ratios, asserting its composition.

## Edge Cases & Error Handling

- Zero-length line: no stroke, no ends. Trims ≥ length: no stroke, both ends.
- Malformed `end` dict → normalised (fixed, trim 0); a non-end block id in an
  end slot → missing.
- An end id that is a *linetype* or *pattern* block → missing (never drawn).
- Cycle: an end block can't contain linetyped strokes or nested blocks, so
  end → linetype → end cycles can't form; `would_cycle` still covers it.

## Performance

Q15 bench, report-only (host varies 2–4×), paired / alternated runs; LT8 owns
the hard D-L21 bar.
