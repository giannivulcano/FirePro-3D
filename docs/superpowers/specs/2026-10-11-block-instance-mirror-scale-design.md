---
status: proposal          # designed 2026-10-11, unbuilt; durable contract lands in block-system.md "Instance pose: mirror & scale" at Account
last-verified: 2026-10-11
verified-commit: a6caccfd
applies-to:
  - firepro3d/block_pose.py            # NEW — pure pose math (one home for the rules)
  - firepro3d/block_instance.py        # pose fields, hooks, posed_ops, records, panel rows
  - firepro3d/block_definition.py      # _nested_pose via pose_matrix; render_ops_variant cache; TEXT text_frame
  - firepro3d/render_op.py             # RenderOp.mapped for any similarity transform; text_frame / readable
  - firepro3d/path_walk.py             # map_piece: reflection (signed sweep) + uniform scale
  - firepro3d/block_explode.py         # full-matrix compose + decompose; primitive + text posing
  - firepro3d/model_space.py           # place_block_instance kwargs; _add_from_dict block branch; paste/undo restore; place_block arrow flips
  - firepro3d/scene_io.py              # .fpd load via place_kwargs
  - firepro3d/schematic_scene.py       # materialize_primitives via place_kwargs
  - firepro3d/model_view.py            # browser-drag save/restore of the flip state
  - firepro3d/sketch_adapters.py       # _InsAdapter snapshots the whole pose
  - firepro3d/modify_tools_controller.py # refusal wording / docstrings only
  - firepro3d/snap_engine.py           # BlockInstance collector reads posed_ops
source-tasks:
  - todo_open.md "Flip / Mirror / Scale for block instances (persisted mirror flag + scale pose)" [P1]
---

# Block instance Mirror & Scale — Design Spec

## Goal

A placed block instance can be **mirrored** and **uniformly scaled**, as a persisted part of its
pose, through Modify ▸ Flip (Shift+F) / Mirror (Shift+I) / Scale (Shift+S), the instance's
**Mirrored** / **Scale** property rows, and **arrow-key flips while placing** (←/→, ↑/↓). The pose
survives every save / load / undo / copy path, renders and plots correctly at the top level and
nested inside other blocks, snaps on the posed geometry, and explodes to the exact posed picture.

## Motivation

Handed symbols (door swings, valve / fitting orientation, flipped detail and title blocks) and
drafting-scale symbols (legends, enlarged detail callouts) are everyday drafting needs; today the
tools skip block instances "by capability" (`scene-tools.md` D16.7 / D17.6) because `BlockInstance`
has no mirror / scale pose. Arrow flips during placement put a handed symbol down right first time
(`block-system.md` Decision 8 deferred them to this pose).

## Ratified "what" (Phase 2 grill, 2026-10-10)

| # | Ruling |
|---|---|
| G1 | End goals: handed symbols (mirror), drafting scale, placement speed. A general future-consumer pose is **not** a goal. |
| G2 | **Uniform scale only** — one factor per instance, > 0. |
| G3 | **Text stays readable** under a mirror: the box lands at its mirrored spot; glyphs stay left-to-right with their authored justification. Rotation still turns text. |
| G3b | A top↔bottom flip leaves text **upright** — a mirror alone never makes text upside down or backwards. |
| G4 | Scale enlarges **geometry + text height only**; lineweights, dash lengths, hatch pattern spacing and end-glyph sizes stay as styled. |
| G5 | **Explode parity** governs every style question: a mirrored / scaled instance looks like its exploded primitives Flipped / Scaled the same way (asymmetric end glyphs mirror; hatch keeps its scene angle; dashes follow the path; lineweights unchanged). G3 readable text layers on top. |
| G6 | In scope: plan instances, nested instances in the Block Editor, Explode, placement arrow flips. |
| G7 | Arrow flips use **screen axes** about the block origin; each press toggles; state persists across repeat placements, resets on mode entry, survives a Blocks-browser drag; plan and editor alike. |
| G8 | Editable **Mirrored** checkbox (flips left↔right in the block's own frame) and **Scale** factor row (FACTOR grammar); one undo step each. |
| G9 | Absorbed (phase-drift, user choice): Paste / Duplicate / Array keep Level Offset; every instance panel row is one undo step. Each gets a VC7 base check first. |

## Architecture & Constraints

- **Flyweight invariant (`block-system.md` "The flyweight core"):** no per-instance geometry copies.
  This design keeps it **per variant**: instances sharing `(mirrored, scale)` share one op list.
- **One pose builder:** `BlockInstance.pose_transform` and `block_definition._nested_pose` must
  agree (their docstrings already say so); both now call `block_pose.pose_matrix`.
- **Per-primitive reflect / scale hooks** are owned by `2d-geometry.md` §1.2; tool behaviour by
  `scene-tools.md` D16 / D17 (Rule A — linked, not restated).
- The scale hook is named `manip_scale_about`, **never** `manip_scale` (that name enables manipulator
  resize handles — `selection-manipulator.md` `item_capabilities`).
- Coordinates: Y-up CCW degrees for `rotation` (the `pose_transform` convention); scene units mm.

## Design Decisions

### DD1 — Approach A: pose-variant op cache (chosen)

Rotation + translation stay on the painter (rigid, exactly today's hot path). Mirror + scale are
**baked into a variant op list** cached on the `BlockDefinition`, keyed by `(mirrored, scale)`,
built by the one generalized `RenderOp.mapped(t)` that the nested-block compile already uses.

Rejected: **B — painter-level reflection/scale** (five scattered ÷s compensations — linetype
factor, end sizes, paper pen, text un-mirror, `_ends_pad` — plus a second implementation of the
rules for nested compile, and a dash-phase parity break); **C — per-instance mapped copies**
(violates the flyweight invariant).

### DD2 — Pose model

Pose `(x, y, rot, mirrored: bool, scale: float > 0)`. Full local→scene map:

```
P = T(x, y) · R(rot) · S(scale) · M^mirrored        M: local x → −x (innermost)
```

- `block_pose.pose_matrix(x, y, rot, mirrored, scale) -> QTransform` — the one builder.
- `BlockInstance.pose_transform()` stays **rigid** `T·R` (painter, bounds, snap — these read the
  variant ops, DD4). New `BlockInstance.full_pose_transform()` returns `P` (point maps: Explode,
  text frames).
- `manip_rotate` is unchanged and stays correct: rotation commutes past an innermost uniform `S·M`.

### DD3 — Hooks and setters on `BlockInstance`

- `manip_reflect(p1, p2)`: degenerate axis → no-op (`geometry_2d._degenerate_axis`);
  `θ = arc_math.yup_angle(p1, p2)`; pos → `CAD_Math.mirror_point`;
  `(rot, mirrored) ← block_pose.reflect_pose(rot, mirrored, θ)` where
  `reflect_pose` returns `(norm(2θ + 180° − rot), not mirrored)`.
  Derivation: `Refl_θ · R(α) · M = R(2θ + 180° − α) · M · M` (with `Refl_θ·R(α) = R(2θ−α)·Refl_0`
  and `Refl_0 = R(180°)·M`). Examples: unrotated block, vertical axis (θ = 90°) → `rot 0, mirrored`;
  horizontal axis (θ = 0°) → `rot 180, mirrored`.
- `manip_scale_about(base, f)`: pos → `CAD_Math.scale_point`; `scale ×= f`. Non-positive or
  non-finite `f` raises `ValueError` (the tool refuses those before calling).
- `set_block_mirrored(bool)`, `set_block_scale(f)`, `block_mirrored()`, `block_scale()`;
  `prepareGeometryChange()` + `update()` like `set_block_rotation`.

### DD4 — Variant ops

- `BlockDefinition.render_ops_variant(mirrored, scale)`: identity → `render_ops()` itself (same
  object — unposed instances are byte-for-byte today's path). Otherwise
  `[op.mapped(S·M) for op in render_ops()]`, cached in a dict keyed by
  `(mirrored, round(scale, 9))`, LRU-capped at 32 entries; dropped wherever the op cache is dropped
  (`BlockRegistry.invalidate` / recompile).
- `BlockInstance.posed_ops()` → the variant. `paint`, `_posed_path` (cache key is already
  ops-identity), `_ends_pad` / `_end_pad_rows`, and the `snap_engine._collect` BlockInstance branch
  read `posed_ops()` instead of `definition.render_ops()`.

### DD5 — `RenderOp.mapped(t)` for any similarity transform

`t` has uniform scale `s = √|det t|` and may reflect (`det < 0`). Used by nested compile
(`_nested_ops`) and by variants (DD4).

| Op part | Rule |
|---|---|
| `path`, fill / pattern `origin` | `t.map` (as today). Pattern `scale` / angle untouched → hatch keeps scene axes (G5, `hatch-and-fill.md` D-A11). |
| `pieces` (`path_walk.map_piece`) | **Seg / Curve:** points mapped. **Arc:** centre mapped, `r × s`; reflecting → `a0` reflected and **sweep negated** (direction preserved, signed sweep). **EllipseArc:** centre mapped, `rx, ry × s`; reflecting → `rot` and `t0` reflected, sweep negated. The `ValueError` is retired. |
| `ends` | Reflecting → `stroke_style.toggle_mirrored`; **no** start/finish swap (direction preserved). Sizes untouched (G4). |
| stroke `weight` / `linetype` | Untouched — resolved at paint in scene units, so dashes, end glyphs and paper pens never scale (G4). |
| TEXT `path` | Mapped; reflecting → readable rule (DD6). |

**P4 (plan step 1):** probe `point_at` / `split` / `phase0` / `append` / `to_path` / `length` on
negative-sweep `Arc` and `EllipseArc` pieces (path_walk docstrings say "sweep > 0"; `canonical()`
already normalises negative sweeps and `length` uses `abs`). **Fallback** if the probe fails:
normalise each reflected arc piece with `canonical()` and reverse the op's piece chain, swapping
start/finish ends. Until the probe passes, DD5's signed-sweep row is *as-proposed*.

### DD6 — Readable text (G3 / G3b)

- TEXT ops gain optional `text_frame = (cx, cy, baseline_angle)` (definition-local, set at compile
  from the TextItem's box centre and `data.angle`) and `readable: bool = False`.
- `mapped(t)` with `det t < 0` pre-composes the glyph path with a reflection about the text's own
  box-vertical axis through `(cx, cy)` (glyphs un-mirrored, box footprint on the mirrored spot,
  justification kept) and sets `readable = True`; `text_frame` is mapped (centre via `t`, angle =
  the mapped baseline direction).
- **Upright is decided at paint** (the final rotation lives on the painter): for a `readable` op
  whose final baseline angle (frame angle + instance `rot`) falls outside the upright range
  `(−90°, 90°]`, paint applies a 180° turn about the mapped centre. `block_pose.upright_angle` is
  the one rule (also used by Explode, DD9).
- Un-mirrored text is never flagged → today's behaviour holds (a plain block rotated 180° still
  shows its text upside down).
- A double mirror (outer over inner) cancels geometrically; `readable` stays set, so paint
  re-checks upright.

### DD7 — Persistence: sparse records + one choke point

- Records: `"mirrored": true` only when true; `"scale": f` only when ≠ 1 — in the `.fpd` instance
  dict (`to_dict`), the nested record (`to_nested_dict`), and therefore `.fpdb` bundles. Missing
  keys = identity. Existing exact-dict goldens (`test_block_instance.py`, `test_nested_block_compile.py`)
  stay green. An older app reading a new file shows the instance unmirrored (accepted).
- `BlockInstance.place_kwargs(rec) -> dict` (classmethod) → `{rotation, mirrored, scale, level,
  level_offset_mm, overrides}` from a record.
- `Model_Space.place_block_instance` gains `mirrored`, `scale`, `level_offset_mm` kwargs.
- Every field-by-field rebuild site calls `place_block_instance(id, pos, **place_kwargs(rec))`:
  `scene_io` load, `_restore_network` (undo), `paste_items` block branch (fixes the G9 Level Offset
  drop for Paste / Duplicate / Array), `schematic_scene.materialize_primitives` (editor seeding),
  Explode child (DD9).
- `_add_from_dict` gains a `block_instance` branch delegating to `place_block_instance(**place_kwargs)`
  with a fresh uid → Mirror's copy path creates posed copies.

### DD8 — Tools, placement, panel

- **Flip / Mirror / Scale:** no new tool code — `_reflectable` / `_scalable` (`hasattr`) pick up
  instances; ghosts already trace `shape()`. Refusal text becomes "…only 2D drafting geometry and
  blocks can be flipped / scaled"; docstrings / DD4 comment updated.
- **Constraint rollback:** `sketch_adapters._InsAdapter` snapshots the whole pose
  `(pos, rot, mirrored, scale)` so a rolled-back Flip / Scale restores it all.
- **Placement arrow flips (G7):** `_place_block_mirrored` beside `_place_block_rot`;
  `Model_Space.flip_place_block(axis)` (sibling of `rotate_place_block`) applies `reflect_pose` with
  θ = 90° (←/→) or θ = 0° (↑/↓) — screen axes. `keyPressEvent` branch beside the opening one:
  `mode == "place_block"`, not input mode, no modifiers, **auto-repeat ignored**. The prototype
  refresh sets it, `_press_place_block` passes it, mode entry resets it, the browser-drag
  save/restore (`model_view._begin_block_drag` / `_end_block_drag`) carries it. `_drop_block` keeps
  0° unmirrored. Status hint: "Click to place block · Space / Shift+Space = rotate 90° · ←→ / ↑↓ =
  flip (Esc to finish)".
- **Panel (G8 / G9):** **Mirrored** `bool` row (toggle = `set_block_mirrored(not m)`); **Scale**
  `dimension` row with `ScaleManager.format_factor` / `parse_factor`, minimum > 0, rejected input →
  unchanged. Level / Level Offset / Rotation / Mirrored / Scale edits are each one undo step.
  **P4 (plan step):** probe how a generic panel edit pushes undo today (`deferred_undo_push`) and
  fix at that layer without double-pushing.

### DD9 — Explode

- **Nested child:** compose full matrices `P_parent · shift(−origin) · P_child` →
  `block_pose.decompose_pose` → the child's `place_kwargs` (replaces "rotations add").
- **Primitives:** translate by `pos − origin`, then if mirrored `manip_reflect(pivot, pivot + (0, 1))`
  (local vertical, before rotation), then `manip_scale_about(pivot, s)`, then `manip_rotate(rot, pivot)`
  — the order of `P`.
- **TextItem** (no reflect / scale hooks; loose-text Flip / Scale stays out of scope — follow-up):
  private `_pose_text(item, P)` — box centre via `P`; `height_mm`, `wrap_width_mm`, `box_height_mm`,
  `cell_padding_mm` × s (border weight not); angle by `upright_angle` (DD6); anchor recomputed so
  the box centre lands on the mapped point.

### DD10 — Explode-parity exemption (explicit)

Dash **phase** along reflected arcs / ellipses: `ArcItem.manip_reflect` reverses direction (CCW
storage forces it) while the variant preserves direction (DD5). Geometry, ends, hatch and text are
exact.

## Acceptance Criteria

- [ ] AC1 Flip / Mirror on a block selection reflect instances across the picked axis (Mirror makes posed copies); blocks are no longer counted as skipped; one undo step; plan and Block Editor.
- [ ] AC2 Scale scales instances about the base by the factor; factor 1 = no-op; one undo step.
- [ ] AC3 The pose survives `.fpd` save / load, undo / redo, copy / paste, Duplicate, Array, editor save / seed (nested), `.fpdb` library round-trip; old files load unchanged; existing exact-dict goldens stay green.
- [ ] AC4 Canvas and sheet / PDF output agree; paper lineweights unchanged at any scale; text readable per G3 / G3b.
- [ ] AC5 Snap points sit on posed geometry; HALO / bounds follow the pose; no resize handles.
- [ ] AC6 A nested mirrored / scaled instance renders correctly in every placed host; no `map_piece` error; arcs have the right start, sweep and radius.
- [ ] AC7 Explode of a mirrored / scaled instance (incl. nested and text) reproduces the posed picture (DD10 exemption).
- [ ] AC8 Flyweight holds: instances with equal `(mirrored, scale)` share one variant list; perf guards within budget.
- [ ] AC9 Arrow flips during placement per G7; status hint lists the arrows.
- [ ] AC10 Panel rows per G8 / G9; refusal / status text no longer says blocks can't be flipped.
- [ ] AC11 Specs reconciled (see "Spec reconciliation").

## Verification Checklist (VC3 guards)

All guards drive real `Model_Space` / `BlockDefinition` objects and assert observable ground truth;
each that should fail without the change is shown RED with it reverted.

- [ ] `block_pose` unit tests, hand-derived numbers: `reflect_pose` (θ = 0 / 90 / 30 cases), `pose_matrix` ↔ `decompose_pose` round-trip incl. mirrored + scaled.
- [ ] `map_piece` signed-sweep / scale tests (hand-derived arc start / sweep / radius); `test_lt3_path_walk.py::test_map_piece_refuses_reflection` rewritten (contract retired by DD5).
- [ ] Flip guard: asymmetric L-shaped line block, vertical axis 50 mm right → scene-space posed endpoints (snap points / `shape()`) mirrored; RED if the hook only translates.
- [ ] Scale guard: posed bounding box × 2; paper pen width (mm) equal at scale 1 and 2.
- [ ] Tool tests that assert blocks are skipped / refused (`test_modify_tools_flip_mirror.py`, `test_modify_tools_scale.py`, `test_manip_reflect_scale.py::test_text_and_blocks_have_no_reflect_or_scale_about` → split, TextItem half kept) rewritten — contract retired by this design.
- [ ] Round-trip guards: `.fpd` save → load; undo restore; paste (pose + Level Offset); editor nested save → host compiled ops mirrored; old-format file loads unchanged.
- [ ] Call-site enumeration guard: every `place_block_instance(` call site passes `place_kwargs` (or is a documented identity site — drag-drop, `commit_block_definition`).
- [ ] Nested arc guard: mirrored ×2 nested arc → hand-derived start / sweep sign / radius.
- [ ] Readable-text raster guard: mirrored block with "FDC" text vs the un-mirrored glyph raster translated to the mirrored box; top↔bottom flip stays upright.
- [ ] Explode raster-parity guard: posed instance raster == Explode raster (non-dashed content).
- [ ] Placement guard: real key events (←, ↑) on a **shown** view, **no pre-focus**, then click → placed posed geometry mirrored; flip survives a repeat placement; resets on re-entry; survives a browser drag.
- [ ] Panel guards: Mirrored / Scale / Rotation edits → one undo step each; undo restores the pose.
- [ ] Perf guard: 1000 mirrored ×2 instances share one variant list (identity) and paint within the existing block-paint budget.

## Spec reconciliation (Account)

- `block-system.md`: new section **"Instance pose: mirror & scale"** — the one home for the pose
  contract (DD2–DD9 durable rules); Decision 9 amended (mirror / uniform scale in plan views via the
  pose); Decision 8's "arrow-key flips wait…" note closed; `.fpd` / nested record shapes gain the
  sparse keys.
- `scene-tools.md` D16.7 / D17.6: block instances supported — pointer to block-system.
- `2d-geometry.md` §1.2: "block instances skipped" → pointer.
- `linetypes.md`: `map_piece` reflection + ends `mirrored` toggle under a reflecting map → pointer.
- This doc stays the archival "how" (like the nested-blocks design doc).

## Existing Code Context (reuse map, 1b sweep)

- **Reuse as-is:** Flip / Mirror / Scale gates, dimming, ghosts (`transform_ghost.reflect_transform` /
  `scale_transform` over `shape()`), undo push; snap collectors (once on `posed_ops`); HALO / bounds;
  `manip_rotate`; Space router; `paper_display._apply_block`; `CAD_Math.mirror_point` /
  `scale_point`; `arc_math.yup_angle`; `geometry_2d._degenerate_axis`; `stroke_style.toggle_mirrored`;
  `RectangleItem.manip_reflect` as the formula template; `crisp_stroke` split cache (reflection-safe).
- **Generalize:** `pose_transform` / `_nested_pose` → `pose_matrix`; `_posed_path` source;
  `to_dict` / `from_dict` / `to_nested_dict`; the field-by-field rebuild sites → `place_kwargs`;
  `place_block_instance` signature; `_InsAdapter`; panel rows; placement prototype / commit / drag
  save-restore; `block_explode._compose`.
- **Gaps (net-new):** `block_pose.py`; `BlockInstance.manip_reflect` / `manip_scale_about`;
  `render_ops_variant`; `map_piece` reflection + scale; TEXT `text_frame` / `readable`;
  `_add_from_dict` block branch; `decompose_pose`; `flip_place_block` + key branch; `_pose_text`.

## Edge Cases & Error Handling

- Scale must be > 0 and finite; no other clamp (uniform — no radius floors apply).
- Capability blocks (pattern tile, linetype unit, end block, schematic) nesting a posed instance
  compile through the same `_nested_ops` → supported.
- Reference-mode (imported) definitions and the missing-definition placeholder op go through
  `mapped` generically.
- Degenerate reflect axis → no-op (shared threshold).
- `round(scale, 9)` keys the variant cache so float noise from repeated Scale doesn't fragment it.

## Performance

- Unposed instances: identical path (identity variant = same list).
- A variant is built once per `(definition, mirrored, scale)`; LRU cap 32 per definition.
- Painter stays rigid; no per-paint mapping.

## Code Style & Testing

Google docstrings; relative imports inside `firepro3d/`; constants in `constants.py` (variant cache
cap). Tests via `./venv/Scripts/python.exe -m pytest` (never the stale venv activate script).
