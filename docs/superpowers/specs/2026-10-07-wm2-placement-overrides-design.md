---
status: proposal
last-verified: 2026-10-07
verified-commit: 7f97f687
applies-to:
  - firepro3d/stroke_style.py
  - firepro3d/render_op.py
  - firepro3d/block_definition.py
  - firepro3d/block_instance.py
  - firepro3d/block_explode.py
  - firepro3d/block_registry.py
  - firepro3d/block_library.py
  - firepro3d/display_manager.py
  - firepro3d/geometry_2d.py
  - firepro3d/model_space.py
  - firepro3d/scene_io.py
  - firepro3d/block_editor.py
source-tasks: [todo_open.md "WM2 — Weight model, placement half"]
---

# WM2 — Placement Weight / Linetype overrides — Design

> The *what* is owned by `docs/specs/linetypes.md` "Weight model" (WM-1–WM-12,
> ratified 2026-10-05) plus this run's Phase-2 rulings Q1–Q12 (below). This
> doc is the *how*; on build it is folded into a "WM2 — as built" subsection
> of that spec (Rule A — the spec stays the one home).

## Goal

A placed block (plan) and a nested block record (Block Editor) carry a
**Weight** (As Authored | By Category | named) and a **Linetype** (As Authored
| named) that replace every stroke beneath them, outermost wins, on canvas and
on paper/PDF — persisted, undoable, copyable, explodable, and counted by every
integrity path.

## Motivation

The end-goal consumers are programmatic: a pipe placement overriding its
plan-block line's Linetype (D-L22 / WM-4) and an "existing = Hidden" riser
dashing its nested valves (WM-6). The data path is the core deliverable; the
panel rows are its first UI (Q1).

## Phase-2 rulings (user-ratified 2026-10-07, FP3 deltas)

- **Q1** Data path (resolution + persistence) is the core; panel on top.
- **Q2** Reference-mode definitions are never placed (underlays only); every
  styled primitive class has `stroke_pieces`. Overrides never restyle the red
  missing-nested placeholder.
- **Q3** Text-box border inside a block is never compiled today → out of WM2;
  follow-up filed (WM-12 border half).
- **Q4** End blocks (WM-11 second half) deferred to LT5 as an explicit LT5
  acceptance clause.
- **Q5 (panel)** Rows "Linetype" / "Weight" after Rotation on every
  `BlockInstance` (plan + Block Editor). Weight: `As Authored` (no resolved
  value), `By Category (<Model Blocks name>)`, named weights. Linetype:
  `As Authored`, then the primitive list (folder picks load on pick).
  Tooltips explain replace-all.
- **Q5 (mixed)** Each target ignores a value outside its own option set;
  named values apply to both.
- **Q6** Explode By Category bakes the Model "Blocks" row name
  (`model_blocks_weight()`). Consequence (accepted): if paper "Blocks" ≠
  Model "Blocks", the exploded strokes now plot at the baked name on sheets.
  Named → as is; Linetype → its ref; As Authored → verbatim.
- **Q7** Non-flatten Explode: a nested child takes the outer's value per axis
  when the outer overrides that axis, else keeps its own record value;
  By Category passes down unbaked. Flatten recurses with the same rule.
- **Q8** Overrides are full references: linetype "used by" / delete refusal,
  `.fpdb` bundling, missing badge (Continuous + badge, `Missing (<id>)` row),
  weight rename + in-use; legacy files load As Authored ×2 with canvas + PDF
  parity.
- **Q9** New placements always As Authored (no sticky current); copy / paste
  / duplicate / array / mirror / move / undo / make-block-from-selection
  preserve overrides.
- **Q12** In a pattern-tile or linetype (repeat) Block Editor, a nested
  record's Linetype row is locked with a "why" tooltip. *P4 probe
  (2026-10-07): a pattern tile's strokes are unioned into one lattice path
  under one pen (`hatch_render._lattice`), so tile strokes ignore op weight —
  in a tile editor the Weight row is locked too.*

## Architecture & Constraints

- Flyweight: compiled definition ops are shared by every instance and never
  mutated — overrides build new ops (`dataclasses.replace`).
- Containment C1: Explode is Block-Editor-only (unchanged).
- Colour (WM-7/WM-8) is WM3: the `overrides` dict is designed to gain a
  `colour` key, but WM2 adds none.
- Paper: `paper_display._apply_block` hooks (`_paper_pen_width`,
  `_paper_scale`, `_paper_pen_color`) are unchanged; By Category on paper is
  the existing paper "Blocks" width.

## Design Decisions (H1–H8, user-approved 2026-10-07)

### H1 — Storage: a separate `overrides` key

`BlockInstance.overrides` and the nested record's `"overrides"`:
`{"weight": "as_authored" | "by_category" | <weight name>, "linetype":
"as_authored" | <"continuous" | linetype id>}`. Omitted from `to_dict` /
`to_nested_dict` when As Authored ×2 (legacy files round-trip unchanged).
Rejected: reusing `style` — ≥4 sites assume the primitive style schema
(`scene_tools._fresh_end`, `copy_style`, `normalize_style`, the
`model_space` "lines inside" wording).

`stroke_style` gains `AS_AUTHORED`, `BY_CATEGORY`, `normalize_overrides(d)`
(defaults, keyword validation, canonical / MW-6 legacy weight names) and
`override_refs(d) -> (weight names, linetype ids)`. `is_named_weight` and
`is_linetype_ref` exclude both new keywords.

### H2 — Resolution: a derived op list

One shared `apply_overrides(ops, overrides) -> list` (next to `RenderOp`):
stroke ops only; ops with `weight is None` (placeholder) skipped; text / fill
/ pattern untouched (WM-8). Weight override sets `op.weight`; Linetype
override sets `op.linetype`.

- **Nested record:** `BlockDefinition._nested_ops` applies the record's
  overrides after `mapped(t)` → inner records were applied inside the child's
  own compile, so the outer replaces them (WM-6 outer wins).
- **Placement:** `BlockInstance.render_ops()` returns the derived list,
  memoised on (base ops identity, overrides tuple); As Authored returns the
  base list itself. Every consumer of `render_ops()` (bounds, shape, missing
  badge, `_lt_ref_cache`, `_lt_exp_cache`, `_crisp_ops`, paint) sees one
  consistent list (H7 falls out).
- **Keyword resolution:** `canvas_weight_name(by_category)` → Model "Blocks";
  `BlockInstance._paper_op_width(by_category)` → `_paper_pen_width`;
  `resolve_stroke` borrows the dash weight for `by_linetype` only, so a
  weight override beats By Linetype (WM-5), and By Linetype resolves against
  the effective (overriding) linetype.

Rejected: per-op resolution in the paint loops (hot-path churn, every cache
key touched, record state still needed in flattened ops).

### H3 — Restore: `overrides=` on `place_block_instance`

All five hand-rolled restore sites pass `overrides=normalize_overrides(d.get(
"overrides"))`: `scene_io` (file open), `Model_Space` undo restore and paste,
`BlockEditor` load, `block_explode` (composed per Q7). `from_dict` reads the
same key. A guard test greps every `place_block_instance` caller in a restore
path.

### H4 — Integrity consumers (via `override_refs`)

| Consumer | Change |
|---|---|
| `block_registry.prim_refs` | nested-record linetype overrides are refs (bundling, cycle, dependency, host invalidation) |
| `block_registry.linetype_users_in` | includes placed instances with a linetype override (delete refusal; `registry.add` refresh loop) |
| `DisplayManager._weight_refs` / `_propagate_lw_rename` | new kinds `inst` (placed) and `nrec` (definition records) |
| `block_library` bundled weights | nested-record weight overrides |
| `Model_Space._linetype_users_message` | record overrides read "by blocks inside" |

### H5 — Panel

`geometry_2d.stroke_rows(..., placement=True)` swaps the By Linetype option
for `As Authored` + `By Category (<Model Blocks>)`; `locked` locks Linetype
in capability editors (Q12). `BlockInstance.set_property` ignores
`By Linetype (…)` labels; `Geometry2DMixin._geom2d_set` ignores `As
Authored` / `By Category (…)`. Undo: `BlockInstance` requests undo per the
primitive `_dim_edit` pattern so the panel's `deferred_undo_push` coalesces
(probe-first plan step — P4). Folder linetype picks load through
`linetype_choices.ensure_linetype_available`.

### H6 — Explode

Primitives bake the exploded instance's effective override (named as is;
`by_category` → `model_blocks_weight()`; linetype → its ref); As Authored
verbatim. Nested children get `overrides` composed per axis (outer if set,
else the record's); By Category passes down. Flatten recurses.

### H8 — Performance

A/B vs base, both shapes (many instances of a small block; few instances of
a large block). Bars: As Authored ≤ 5 % paint time; Weight override ≤ 1.1×
the same scene As Authored; Linetype override report-only (LT8 budget, same
expansion cache).

## Acceptance Criteria

- [ ] G1 As Authored: canvas + PDF widths per component = authored names.
- [ ] G2 Weight Medium: every component at Medium (canvas px + PDF mm).
- [ ] G3 By Category: canvas = Model "Blocks" px; PDF = paper "Blocks" mm.
- [ ] G4 Linetype Hidden: dashes on every component, canvas + PDF.
- [ ] G5 Hidden + By Linetype component: weight = Hidden's dash weight.
- [ ] G6 Nested Heavy record in an outer Light placement → all Light; outer
      As Authored → nested Heavy shows.
- [ ] G7 Legacy file (no fields): canvas pixel + PDF parity with base
      (parity guard: passes before and after).
- [ ] G8 Explode (non-flatten + flatten) of overridden records: identical
      pixels; baked names per Q6/Q7.
- [ ] G9 Round-trip: `.fpd` save/open, `.fpdb` export/import, undo/redo,
      copy/paste keep overrides.
- [ ] G10 Integrity: delete of an override-used linetype refused; weight
      rename follows; `.fpdb` bundles the linetype.
- [ ] G11 Mixed selection: As Authored leaves the primitive; named applies
      to both.
- [ ] G12 Real MainWindow: a panel pick on a placed block repaints and is
      one undo step.
- [ ] Perf bars (H8) met.
- [ ] Follow-ups filed: text-box border in blocks (Q3); LT5 end clause (Q4).

## Verification Checklist

- [ ] Every guard shown RED with the change reverted (G7 passes both).
- [ ] Full suite (chunked, VC6) green; pre-existing failures proved (VC7).
- [ ] Live smoke on the real MainWindow (plan + Block Editor + PDF export).
- [ ] `linetypes.md` WM2 as-built subsection; `block-system.md` /
      `property-panel.md` pointers; stamps.

## Edge Cases

- Override linetype missing → Continuous + missing badge; row shows
  `Missing (<id>)` until re-picked.
- Linetype override `continuous` on a dashed block → solid (a named choice).
- Ghost placement preview: As Authored (new placements never carry overrides).
- Repeat units cannot nest blocks (D-L1); if a nested drop is found possible,
  file a pre-existing bug (not fixed here).
