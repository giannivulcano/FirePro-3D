---
status: approved
date: 2026-11-01
governing-specs: [docs/specs/scene-tools.md, docs/specs/parametric-constraint-system.md, docs/specs/units-and-formatting.md]
source-tasks: ["Scale: type the new value (not a factor) or cycle the input with ←/→", "Array HUD: a typed Angle of 0 doesn't update the copies' position", "Fillet (new)", "Flip: axis at the selection's centroid; quadrant picks the flip; live ghost"]
---

# Scene tool polish — Scale Length, Array 0° lock, Fillet, Flip quadrants

## Goal

Four scene-tool changes from the 2026-11-01 user batch: Scale takes the new length (or a
factor, cycled with ←/→); a typed Array Angle of 0 locks to 0°; a new Fillet tool joins any
corner with a tangent arc; Flip reflects about the selection's centre, the cursor quadrant
and the arrow keys choosing the flip, with a live ghost.

## Motivation

- Scale's factor-only HUD forces mental arithmetic when the target size is known.
- Array: D10 made a typed 0 *release* the lock, so the field reads 0 while copies follow the
  cursor — the user reads that as a bug.
- Fillet has been unreachable since the ribbon removal (D14) and its legacy maths is Y-down
  (arc ends miss the tangent points).
- Flip needs an existing straight edge as its axis; flipping in place about the selection's
  own centre is the common case.

## Architecture & Constraints

- All four live in `ModifyToolsController` slices behind the `Model_Space` shells; no new
  logic in `model_space.py` beyond dispatch-table rows (`model-space-architecture.md`).
- Geometry in mm; angles Y-up CCW+ (`arc_math.yup_angle`); length fields are `FieldKind.DIMENSION`,
  whose resolved HUD values arrive in scene units (`units-and-formatting.md`).
- Every commit runs inside `ConstraintController.edit` and pushes one undo step (scene-tools D30/D65).
- Line / Arc relations exist only in the Block Editor (`constraint_controller._plan_ref_types`
  = walls, gridlines, blocks); model-space fillets add geometry only.
- Arrow-key handling follows block placement's rules (`block-system.md` "Placement flips"):
  no modifier, keypad masked, not in input mode, auto-repeat ignored.

## Design Decisions (ratified 2026-11-01 — Phase 2 FP1 + Phase 3 section approvals)

### DS1 Scale (amends scene-tools D17)
1. Base → reference point unchanged. Between base and reference the HUD is the existing
   `scale_factor` Factor field (typed factor after the base still commits).
2. After the reference point the HUD opens on **Length** — new schema `scale_length`, one
   `FieldSpec("Length", "L", FieldKind.DIMENSION, minimum=0.0)` (> 0 enforced at commit),
   seeded live with `scene_to_mm(|cursor − base|)`.
3. **←/→** swaps Length ⇄ Factor: a `"scale"` entry in `_PLACEMENT_VARIANTS`; the cycle gate
   admits Scale at the cursor step (after the reference point), input-mode gate kept;
   `active_schema("scale")` picks by `_scale_variant`. The variant resets to Length on entry.
4. Typed Length L → factor = L ÷ |ref − base| → `commit_scale` (`DynamicInputHud.values()` returns
   DIMENSION values in scene units — verified in the 2026-11-01 plan dry run — so no mm conversion); factor-1 no-op
   and ≤ 0 / non-finite refusal unchanged.

### DS2 Array angle (amends scene-tools D10 / DD5)
1. `note_typed_angle`: a typed 0 (or any multiple of 360, which parses to 0) **locks to 0°**
   like any other angle. The "equals the unlocked seed = untouched readout" skip stays.
2. The lock **ends with the tool**: `_array_angle_locked = None` on Array entry; it no longer
   carries to the next Array.
3. `_array_grid_axes`: explicit `is not None` instead of `or 0.0`.

### DS3 Flip (amends scene-tools D16 for Flip only — Mirror keeps the edge-pick axis)
1. Centre = bounding-box centre of the reflectable selection (union of `manip_bounds`, the frame
   the selection manipulator draws) — one shared helper promoted from `selection_manipulator`.
2. State: two toggles `lr` (reflect across the vertical line through the centre) and `ud`
   (across the horizontal one). Crossing into a new **quadrant** sets both: upper-right = none,
   upper-left = lr, lower-right = ud, lower-left = lr + ud. **←/→** toggles lr, **↑/↓** toggles ud;
   a toggle holds until the cursor crosses into a different quadrant. Last input wins.
3. Paint: dash-dot crosshair through the centre, active axes in accent; ghost = `GhostFrame`
   with the composed `reflect_transform`(s); every view repaints on a state change.
4. Commit (click / Enter): `manip_reflect` once per active axis on each item, one undo step →
   Select with the originals. No active axis → status "Nothing flipped", no undo step.
   Fully-defined-block refusal (D45) and grounded refusal kept. Status hint
   "Move into a quadrant or ←→ / ↑↓ to flip · click/Enter applies".
5. Snap / ALIGN stay off in the step (as today). Esc / Undo cancel.

### DS4 Fillet (new; replaces the legacy unreachable fillet — D14's Fillet entry)
1. Entry: **Shift+E** + a Modify-group **Fillet** button. Not select-first.
2. Corner detection on hover within the snap aperture at the active view's zoom:
   (a) a polyline vertex (interior vertices of an open polyline; any vertex of a closed one),
   (b) a Rect / RegularPolygon corner, (c) two Lines whose ends meet or cross. Fallback for
   lines that only meet when extended: click Line 1, then hover Line 2.
3. `fillet_geometry.py` (pure, no scene items): `find_corner(...)` → corner (vertex, the two
   edge unit directions away from it, available segment lengths, source refs);
   `tangent_arc(corner, r)` → centre, `start_deg` / `span_deg` (Y-up, CCW), tangent points
   t1 / t2 — or a refusal: parallel / collinear edges, or a tangent point past the far end of
   either segment.
4. HUD: `fillet_radius` — one Radius `DIMENSION` field (> 0), **sticky** for the session,
   default `FILLET_DEFAULT_RADIUS_MM` (`constants.py`). Live ghost = the arc + the trimmed edges.
5. Commit (one undo step, inside `constraint_ctl.edit`):
   - Line ∠ Line → both lines trimmed to t1 / t2 + one `ArcItem` (style copied from line 1).
   - Polyline / Rect / RegularPolygon → the item is replaced by open polyline(s) + one
     `ArcItem` (style copied; **fill dropped**; an open polyline splits in two).
   - Block Editor only: `auto_join` adds coincident (arc start/end ↔ the trimmed edge ends) and
     tangent (each edge ↔ arc) relations; relations on a replaced item drop via the normal
     delete path.
6. Refusals (status, tool stays live): "Edges are parallel — no corner to fillet";
   "Radius too large for these edges".
7. Retired: `model_space._press_fillet` + its Enter branch / mode rows, `scene_tools._compute_fillet`
   / `_commit_fillet`, `tool_geometry.compute_fillet`; coupled tests rewritten (VC5).

## Acceptance Criteria

- AC-S1 Typed Length 1371.6 mm on a 914.4 mm reference scales the selection 1.5× about the base.
- AC-S2 ←/→ after the reference point swaps Length ⇄ Factor; typed Factor still commits.
- AC-A1 Typed Angle 0 → Linear copies lie on +X from the base whatever the cursor heading.
- AC-A2 A new Array after a locked one starts unlocked (cursor-aimed).
- AC-X1 Cursor in each quadrant → ghost transform = the quadrant's reflection about the bbox centre.
- AC-X2 ←/→ / ↑↓ toggle lr / ud; commit reflects the items' extents accordingly; one undo step.
- AC-X3 Mirror still requires a hovered straight edge.
- AC-F1 Lines at 60°, 90°, 135° → arc of radius r whose ends equal the tangent points (Y-up);
  the lines end at t1 / t2.
- AC-F2 Polyline vertex and rect corner → polyline(s) + arc, closed shape becomes open, fill dropped.
- AC-F3 Block Editor fillet → 2 coincident + 2 tangent relations, solve satisfied; model space → none.
- AC-F4 Parallel edges and an oversize radius are refused with the status text; nothing changes.
- AC-F5 Shift+E enters Fillet; the last typed radius pre-fills the next fillet.

## Verification Checklist

- Guards drive the real path (shown view + posted keys / mouse) and assert scene ground truth
  (item geometry, relation records, undo stack depth); each shown RED with the change reverted.
- Keep-green: `test_modify_tools_scale.py`, `test_dynamic_input_schema.py`, `test_format_factor.py`,
  `test_placement_variants.py`, `test_modify_tools_array_variants.py`,
  `test_modify_tools_flip_mirror.py`, `test_mirror_axis_paint.py`, `test_axis_picker.py`,
  `test_block_mirror_scale_tools.py`, fillet tests (`test_scene_tools.py`, `test_tool_geometry.py`,
  `test_lt2_edit_tools.py`, `test_arc_convention_tools.py`, `test_scene_tools_imports.py`,
  `test_et1_cut_ends.py`, `test_filled_region.py`), plus a grep of every test file for the
  retired symbols.
- Spec Account: scene-tools D10 / D14 / D16 / D17 + a fillet row; parametric-constraint-system
  modify-tool relations pointer.

## Edge Cases

- Scale: |ref − base| below pick tolerance is already refused at the reference step.
- Flip: cursor exactly on a crosshair line keeps the previous quadrant; a single point-like
  selection (zero-size bounds) still flips (reflection about its own centre is identity for a point).
- Fillet: a tangent point exactly at a segment's far end is allowed; the trimmed segment then
  has zero length and is removed (a polyline piece with fewer than two points is not created).
  A tangent point beyond the far end is the DS4.6 "Radius too large" refusal.
