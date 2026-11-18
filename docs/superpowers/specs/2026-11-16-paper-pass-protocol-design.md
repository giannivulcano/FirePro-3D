---
title: Paper pass protocol (items enter and leave the pass themselves)
status: Implemented 2026-11-17 (merged 2ce5b3b2, v0.107.3); as-built deviations recorded in docs/specs/paper-space.md §6.2.1 (the contract home is subsection §6.2.1 of the §6.2 named below)
task: todo_open.md "Paper pass: each item reports its own paper category and enters / leaves the pass itself" [type:maint] Large
branch: todo/p1-arch-20261116 (worktree .worktrees/p1-arch-20261116)
governing-specs: docs/specs/paper-space.md (contract home, new §6.2 "Paper pass protocol"), docs/specs/linetypes.md, docs/specs/hatch-and-fill.md, docs/specs/project-phasing.md
---

# Paper pass protocol: design

## Goal

`paper_display.apply_paper_overrides` stops knowing how every item type plots
on a sheet. Each item class enters and leaves the paper pass itself and takes
its owned children with it. The driver only picks items, maps each one to its
paper owner, and balances every enter with a leave. Plotted output does not
change, except for the four absorbed fixes (R3) and the fitting edge (D9).

## Motivation

- One function writes the private state of about a dozen classes
  (`_paper_pen_width`, `_paper_scale`, `_paper_pen_color`, `_paper_fill_opaque`,
  `_paper_no_fill`, `_paper_gap_color`, `_display_*`, `_pen_src` /
  `_brush_src`, `_grid_color`, ...).
- Three `isinstance` ladders (save, apply, restore) are paired by hand, so a
  new item type or attribute is an edit in all three.
- Children are reached only through their owner's branch. A child that is hit
  while its owner lies outside the crop gets no paper hooks (the pipe-label
  line).
- Restore runs forward, with no per-entry tolerance. Sub-item opacity is
  forced to 1.0 and never saved.

## Ratified decisions (Phase 2, 2026-11-16; do not re-ask)

- **R1.** Per-item `enter_paper_pass(...) -> token` / `exit_paper_pass(token)`,
  the existing `ElevGridlineItem` / `ElevDatumItem` shape. Owners enter their
  children. `apply_paper_overrides` only picks items and unwinds in reverse.
- **R2.** One commit per family on the feature branch, with the baseline green
  at every commit and one merge to main. No half-migrated ladder lands on main.
- **R3.** Four fixes absorbed (explicit user choice):
  - a per-entry try in restore;
  - sub-item opacity saved and restored (gridline bubble, marker head,
    elevation head);
  - the pipe label that pokes into the viewport;
  - `source_view_key` dropped.
- **R4.** The owner always decides. Every hit item maps to its paper owner, and
  each owner enters once, entering all its children whether they were hit or
  not.
- **R5.** Each class declares its paper category, as a property where it varies
  per instance. `_category_for_item` reads it first and keeps today's ladder as
  the fallback. The other four category ladders are out of scope.
- **R6.** The contract lives in a new "Paper pass protocol" subsection of
  `paper-space.md` §6.2. `linetypes.md`, `hatch-and-fill.md` and
  `project-phasing.md` drop their `_apply_*` citations and link to it.

## Design decisions (Phase 3, approved 2026-11-16)

- **D1 Approach A.** Item classes own their enter / exit. A new module,
  `firepro3d/paper_pass.py`, holds `PaperPassContext` and the driver.
  `paper_display.apply_paper_overrides` and `restore_model_display` keep their
  names and call shape as thin wrappers, so the one caller (`paper_space.py`
  `SheetViewport.paint`) and the 42 calling tests are unchanged.
  - Rejected: B, an adapter registry, which moves the ladder instead of
    removing it.
  - Rejected: C, methods that call back into `paper_display` helpers.
- **D2 Signature `enter_paper_pass(ctx, cat) -> token | None`** (a delta from
  R1's `(ctx)`, approved). The driver merges the row once
  (`phase_display.merge(row, item, keys=...)`) and passes `cat`. Owners build
  a child's own `cat`, for example a label's `LABEL_KEYS` merge. A `None`
  token means nothing to undo. `exit_paper_pass(token)` must tolerate a token
  from a partly-entered item: the enter saves first, then writes.
- **D3 `PaperPassContext`** holds:
  - `paper_scale`;
  - the loaded paper rows (`row(key)`);
  - `viewport_data`;
  - the printed-text scale;
  - the per-pass model-token cache, with the helpers `auth_tok` /
    `svg_paper_retint` / `svg_phase_tint` / `phase_keys`, moved from closures
    inside today's function;
  - `lw_mm(cat)`.

  Its own enter / exit carries the pass-level state: the hatch paper scale
  and the Thin Lines suspension. It is entered first and left last.
- **D4 Driver pick rules stay in the driver** as visibility-only tokens:
  - `PAPER_EXCLUDED`;
  - the origin cross (`QGraphicsItem.data(item, 0) == "origin"`);
  - scaffold items;
  - the detail-marker self-hide and per-sheet hide;
  - the phase-hidden mask.

  A row whose `visible` is off hides the owner with a visibility token and
  does not call enter, as today.
- **D5 Owner mapping (R4).** `paper_owner` on a child returns its owner:
  - the pipe label and the room tag (top-level `BoundLabelItem`s) → their host;
  - the gridline and elevation bubbles, marker heads and the datum head (Qt
    children) → their parent;
  - `Pipe._riser_symbol` (top-level) → its pipe;
  - the fitting symbol (`_TintedSvg`, a Qt child of the Node) → its node.

  An item without `paper_owner` is its own owner, the `HydraulicNodeBadge`
  included (it keeps its own row). Owners are de-duplicated by identity, in
  first-hit order.
- **D6 Unwind.** Tokens are unwound in reverse order. Each exit runs in its
  own try.
  - **In restore:** a failure is logged with the item and restore continues.
    After every token has run, the first error is re-raised.
  - **In apply:** a mid-pass raise unwinds everything entered so far, then
    re-raises. `test_gridline_paper_scale`'s mid-pass raise test keeps passing.
- **D7 Per-family methods.**
  - `DisplayableItemMixin` carries the generic default (today's
    `_apply_generic` and its restore). This covers wall, wall opening, floor
    opening, floor slab and roof. `WallOpening` adds the paper gap colour, and
    `Room` adds `_paper_no_fill` and enters its tag.
  - The geometry_2d classes and `FilledRegionItem` declare Construction and
    override with the pen path (`_apply_construction`).
  - One shared annotation-block hook helper (the `_paper_pen_width` /
    `_paper_pen_color` / `_paper_scale` triple, plus the Blocks colour and fill
    slots and the annotative `prepareGeometryChange`) serves `BlockInstance`,
    `BoundLabelItem` and its subclasses, and `HydraulicNodeBadge`. It takes the
    line weight, the opacity to set and the Blocks hook as arguments, and it
    saves the real prior opacity (the R3 opacity fix).
  - `Pipe` enters its riser and its label. `GridlineItem` enters its bubbles
    and hides its lock indicator. `SectionMarker` / `DetailMarker` enter their
    heads. `Sprinkler` / `WaterSupply` take the symbol path (width hooks plus
    the SVG tint).
  - `ElevGridlineItem` / `ElevDatumItem` move to the `(ctx, cat)` signature and
    enter their bubbles or head.
  - `TextItem` wraps `set_print_pass` when the context carries a print scale.
  - The section proxies (`section_scene._ColourSrcMixin` users) get their own
    enter / exit (the `_paper_cat` path), entering a line proxy's `pipe_label`.
  - The underlay group's enter / exit lives in the underlay module, run from a
    separate driver loop over `scene.underlays` (groups are not category items).
- **D8 Category (R5).** Each class declares a `paper_category` property. The
  name is grep-clean in `firepro3d/`; tests use it only in test names.
  `_category_for_item` checks `_paper_cat` (proxies), then `paper_category`,
  then today's ladder as the fallback. Its six direct test callers keep
  passing.
- **D9 Fitting inclusion (a delta, approved).** A fitting enters when its node
  or its symbol is hit (owner mapping, D5). Today the rule is
  `source_rect.contains(f.symbol.scenePos())`. This is the same fix class as
  the pipe label, a small edge change at the viewport boundary, and it is named
  in the acceptance criteria.
- **D10 Migration (R2).** The commits, in order:
  1. Characterization guards at base (the task's Gate).
  2. `paper_pass.py`: the context, the driver and a legacy adapter that runs a
     not-yet-migrated owner through the old per-entry save / apply / restore
     code as one token.
  3. One commit per family: generic → construction → annotation-block hooks
     (block, label, badge) → pipe → sprinkler / water supply → gridline →
     markers → elevation gridline / datum → section proxies → fitting →
     underlay → printed text.
  4. Delete the old ladder and the adapter, and drop `source_view_key`. The
     caller, the spy in `test_paper_export.py` and the callers in
     `test_sv2_paper_primitives.py` / `test_underlay_display.py` follow.
  5. Specs (R6).

  The 1b baseline passes at every commit.

## Architecture & constraints

- Geometry stays in mm. Paper widths stay `lw_mm / paper_scale`, non-cosmetic
  (paper-space.md §9.9.1).
- Restore must stay synchronous and export-safe, because PDF export renders
  without an event loop.
- PH3 phasing: `phase_display.merge` / `writes` / `forced` / `label_opacity`
  semantics are unchanged. A slot the status forces is still written in an As
  Authored row.
- Compiled block op pens are never mutated; the paint hooks are the only
  channel (LT1-2 / H5).
- Out of scope: where paper rows are stored (QSettings), the Display Manager
  model side, unifying the other four category ladders, the look resolver, and
  section proxy building.

## Acceptance criteria

- **AC1.** `paper_display.py` holds no per-type `isinstance` ladder in apply or
  restore. The one ladder left is `_category_for_item`'s fallback.
- **AC2.** For one item of every type the old ladders named, enter then exit
  returns every touched attribute to its prior value. This holds on a bare item
  with no scene where the class allows it.
- **AC3.** Pixel parity: one sheet viewport holding every type, rendered at
  base and at HEAD, is identical across the As Authored on / off and weight
  paths. Export parity holds through `paper_export`.
- **AC4.** A pipe label inside the crop whose pipe lies outside plots at paper
  size and in the paper colour. This guard fails at base.
- **AC5.** A raising exit does not stop the remaining exits. All other items
  restore, and the error surfaces after the unwind. This guard fails at base.
- **AC6.** A bubble or head at canvas opacity 0.4 is 0.4 again after one sheet
  render. This guard fails at base.
- **AC7.** `source_view_key` is gone from the signature, the caller and the
  tests.
- **AC8.** A fitting whose node is hit enters even when its symbol origin lies
  outside the crop (D9).
- **AC9.** The 1b before-baseline passes unchanged at every commit:
  - 116 files, 2038 passed;
  - 3 filed pre-existing failures (lt2 ×2, the sb4c level datum head).

  Each rewritten baseline test is named in the done evidence (VC5).
- **AC10.** `paper-space.md` §6.2 "Paper pass protocol" states the contract.
  The three sibling specs link to it, with no `_apply_*` citations left.

## Verification checklist

- [ ] Characterization guards (AC2, AC3) green at base before any move.
- [ ] AC4 / AC5 / AC6 guards shown RED at base and GREEN at HEAD (VC3).
- [ ] Baseline green after each family commit (R2).
- [ ] The VC9 seam review over the whole diff.
- [ ] Full suite (VC6), and smoke: a sheet with every type, plus a PDF export.
- [ ] Account: the four specs stamped. The absorbed todo lines closed: the
      pipe label, per-entry tolerance, sub-item opacity, and `source_view_key`
      (its line, if any).
