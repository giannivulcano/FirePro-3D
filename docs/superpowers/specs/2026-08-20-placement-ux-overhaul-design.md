---
status: proposal
last-verified: 2026-08-20
verified-commit: 8b0181e
applies-to:
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/dynamic_input.py
  - firepro3d/construction_geometry.py
  - firepro3d/snap_engine.py
  - firepro3d/scene_io.py
source-tasks:
  - "TODO.md — Arc placement revamp + Dynamic Input (P1)"
  - "TODO.md — extend multi-mode placement to rectangles"
  - "TODO.md — Dynamic Input ghost updates on field commit"
---

# Placement-UX Overhaul — Design Spec

> Working design doc (Phase-3 brainstorm output). The settled design folds into
> `docs/specs/inferred-dimension-driven-placement.md §4` **in place** at wrap-up, and
> `construction_geometry.py` (RectangleItem/ArcItem) joins that spec's `applies-to`
> — no separate orphan spec (one-fact-one-home: "how drawn primitives place" stays in one spec).

## Goal

Three connected placement-UX improvements, one branch, sequenced **#3 → #1 → #2**:

1. **Ghost-on-commit** — the placement preview redraws on each Dynamic Input field commit.
2. **Arc revamp** — two ←/→-cycled placement variants + step-aware Dynamic Input.
3. **Rectangle revamp** — corner/center variants each gain a rotate step; `RectangleItem` stores angle.

## Motivation

Precise, Revit-like drafting. Today the arc tool is single-workflow with a hand-built readout
and no typed input; the rectangle tool is corner-only and axis-aligned; and the Dynamic Input
ghost freezes at its seed the moment a field is engaged (§4.5), so a user typing an exact length
sees nothing until the whole placement commits. This is also groundwork for a future arc-wall
placement mode.

## Architecture & Constraints (the locked "what")

**Piece #3 — ghost updates on field commit**
- On each field commit (Tab-to-next / Tab-wrap; **not** per-keystroke), preview redraws from
  `resolve(anchor, current HUD values)` — typed fields mixed with still-seeded fields.
- Reflects **valid values only** (invalid reverts to last-valid per §4.6; never zeros).
- Applies to **all HUD clients** (line, gridline, polyline, rectangle, circle, arc, move,
  gridline offset/array) via a shared preview-render path driven by a HUD field-commit signal.

**Piece #1 — arc**
- Two variants, ←/→-cycled at **step 0 only**, readout `"<Mode> (←/→ to change): <instruction>"`:
  - **Center Point Arc** (current): center → rim (radius + start°) → end (span).
  - **Start Point Arc** (new): start-on-arc → center → end. Identical tail (both sweep to an
    endpoint; span derived by projecting onto the radius circle).
- **Step-aware Dynamic Input:** step 2 = `Radius` + `Start°`; step 3 = `Span°` **and**
  `Arc length`, **live-coupled** (edit either → both update; canonical = span°,
  `arc_len = radius·span_rad`).
- `_commit_arc_at(point)` split from the inline `_press_draw_arc` step-2 body; arc becomes a HUD
  client; retires arc's `_draw_dim_hint` / block-4 readout.

**Piece #2 — rectangle**
- Two variants, ←/→-cycled at step 0: **Corner Rectangle** and **Center Rectangle**. Both keep
  their **exact current 2-click sizing**, then gain a **3rd step: rotate**, angle from **+x axis**
  (0° = axis-aligned). Step 3 = drag-preview-rotate + click-commit + DI `Angle`.
- **Pivot = the mode's anchor** (corner-1 / center).
- `RectangleItem` gains stored **`angle`** → paint, **both serialization paths**
  (`scene_io` + undo `_capture_network`), grips, snap.

**Cross-cutting**
- ←/→ cycle: step-0 only, **session-sticky per tool**, **no QSettings**, `(←/→ to change)`
  hint shown only when cycling is available. One generic cycle mechanism for arc + rect.
  Line/circle stay single-mode. Orthogonal to the Left-Shift-tap `cycle_placement_ambiguity`.

## Design Decisions (the settled "how")

### D1 — Shared preview-render path (feeds #3 and the arc/rect ghosts)
Extract the preview-update tail of each `_move_*` into a **mode-dispatched `_preview_from_resolved(resolved)`**
(a `_PREVIEW_DISPATCH` table parallel to `_MOVE_DISPATCH`). Both mouse-move and the HUD
field-commit path call it → one preview code path, no divergence. Point-schema modes drive their
scene preview items (`preview_pipe` / `_draw_rect_preview` / `_draw_arc_radius_line` /
`_draw_arc_preview`); transform modes drive their `drawForeground` ghosts (blocks 7/8).

### D2 — HUD field-commit signal (#3)
`DynamicInputHud._step_focus` emits **`fieldCommitted`** after its `editor.try_commit()`
(`dynamic_input.py:953`). `Model_Space._on_dynamic_input_field_committed()` reads the current
field values **non-destructively** (per-editor current mm; **no** `values()` force-commit, **no**
invalid-flag mutation — the sticky-invalid machinery stays exclusively on the real Tab/Enter path),
runs `schema.resolve(anchor, values)`, and calls `_preview_from_resolved`. Typed+seed mix,
valid-only. Rejected alternatives: HUD owning the preview (breaks the scene-blind module boundary,
§3.1); per-keystroke `textChanged` (rejected in grill — per-Tab only).

### D3 — Step-aware schema selection
`active_schema()` keyed on **(mode, current placement step)**. Mode handlers already track their
step (`_draw_arc_step`; rect gains a rotate-step flag). A step advance changes the active schema,
and the **existing** `_sync_dynamic_input` schema-change rebuild (`hud.schema is not schema →
end + recreate`) swaps the HUD field set. No new HUD lifecycle.

### D4 — Arc as a HUD client
- **Step 2 reuses the `line` schema.** Anchor = the first click point (center in Center-first;
  start in Start-first). `resolve_line(anchor, Length, Angle)` yields the second point. New applier
  **`_commit_arc_rim_at(point)`** branches on `_arc_variant`: Center-first → `point` is the rim
  (radius = |center→point|, start° = angle center→point); Start-first → `point` is the center
  (radius = |center→start|, start° = angle center→start). Either way it advances to step 3. This is
  what the 2nd mouse click already does — structural parity, no new geometry math.
- **Step 3 = `arc_span` transform schema** → `{"span_deg": x}` (scalar, like `move`/`gridline_offset`,
  because the end point needs radius+start from scene state). Applier **`_commit_arc_at`** reads
  stored center/radius/start°/variant + span → builds the `ArcItem`. The **Span°↔Arc-length
  coupling lives in the schema/HUD**: canonical value is span°; the `Arc length` field is a derived
  view that writes back to span when edited. Mouse-vs-HUD parity holds: a click-derived span and a
  typed span produce the identical `ArcItem`.

### D5 — `RectangleItem` rotation (native transform)
- Use **`setTransformOriginPoint(pivot)` + `setRotation(angle)`** — Qt handles rotated paint,
  `boundingRect`, and scene hit-testing for free.
- **Preserve the "grips are scene coords" contract** (consumers read `grip_points()[i]` raw as
  scene points — `model_space.py:4797,6046`): `grip_points()` returns `self.mapToScene(local_corner)`;
  `apply_grip(idx, scenePos)` does `mapFromScene` first, resizes the local rect, re-applies. Zero
  consumer edits.
- **`snap_engine`'s 3 `RectangleItem` branches** (intersections `:434`, named corners `:662`,
  edge-projection `:1121`) map the 4 corners through the item transform (`item.mapToScene(corner)`).
- **Serialize** `x/y/w/h` (unrotated local rect) + `angle` + `pivot(px,py)` in **both** `to_dict`
  (→ `scene_io`) and the undo `_capture_network` path; `from_dict` sets origin+rotation.
  **Back-compat:** missing `angle` → 0, missing `pivot` → rect center (identical to today's render).
- Rejected: baked rotated coordinates (loses Qt's free rotated paint/hit-test; custom
  `paint`/`boundingRect`/`shape`; invites the stale-boundingRect / shape-culling bug class).

### D6 — Generic placement-variant cycle
In `model_space` (data tables, like `_SCHEMA_FOR_MODE`/`_APPLIER_FOR_MODE`):
- **`_PLACEMENT_VARIANTS: dict[mode → list[Variant]]`**, `Variant = (label, first_point_instruction,
  apply_fn)`:
  - `draw_arc` → `[("Center Point Arc", "Select center point to begin", _arc_variant="center"),
    ("Start Point Arc", "Select start point to begin", _arc_variant="start")]`
  - `draw_rectangle` → `[("Corner Rectangle", "Pick first corner", _draw_rect_from_center=False),
    ("Center Rectangle", "Pick center point", _draw_rect_from_center=True)]`
- **`_variant_index: dict[mode → int]`** — session-sticky, default 0, no QSettings. New `_arc_variant`
  flag; rect reuses existing `_draw_rect_from_center`.
- **`_at_placement_step_zero()`** predicate — arc → `_draw_arc_step == 0`; rect → `_draw_rect_anchor
  is None`.
- **`cycle_placement_variant(direction) -> bool`** — returns False (key falls through to default
  view-scroll) unless mode ∈ registry **and** `_at_placement_step_zero()` **and** `not is_input_mode()`;
  else advances index mod N, runs `apply_fn`, emits the hinted readout, returns True.
- **`keyPressEvent`** — `Key_Left`/`Key_Right` → `if cycle_placement_variant(∓1): accept; return`,
  by the existing `not is_input_mode()` discipline. Left-Shift `cycle_placement_ambiguity` untouched
  (orthogonal axis).
- **Readout ownership** — `set_mode(tool)` applies the sticky variant + emits
  `"<label> (←/→ to change): <instruction>"`. The first press handler (placing point 1) emits the
  plain next-step instruction **without** the hint; Esc-to-step-0 re-emits the hinted readout.

## Acceptance Criteria

- [ ] #3: engaging a line then committing Length updates preview to typed-length/seed-angle;
      committing Angle updates again; invalid reverts don't zero the ghost; holds for all HUD clients.
- [ ] Arc: ←/→ cycles Center Point ↔ Start Point at step 0 only; readout string correct;
      session-sticky; falls through to scroll after first click.
- [ ] Arc: step-aware HUD (step 2 Radius+Start°, step 3 Span°↔Arc-length coupled, canonical span°).
- [ ] Arc: Center-first and Start-first produce identical `ArcItem` from equivalent points;
      mouse≡HUD parity; degenerate (r≈0, span≈0/360) rejected keeping HUD open (D2/§4.6).
- [ ] Rect: Corner + Center each gain a rotate step; angle from +x, 0°=axis-aligned; pivot=anchor.
- [ ] Rect: `angle` survives save/load (`scene_io`) **and** undo/redo (`_capture_network`);
      back-compat load of angle-less records renders axis-aligned.
- [ ] Rect: grips, snap, and hit-test correct on a rotated rectangle.
- [ ] Cycle abstraction generic (serves arc + rect); line/circle unaffected;
      Left-Shift `cycle_placement_ambiguity` unaffected.

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] Schema-layer tests (no Qt): `resolve_*`/`seed_*` round-trips incl. span↔arc-length coupling
      and angled-rect; Y-up sign; degenerate rejects.
- [ ] Parity tests (mouse vs HUD) incl. Center-first≡Start-first.
- [ ] Angled-rect through both serialization paths (scene_io + undo).
- [ ] Seam tests: cycle-at-step-0-only, stickiness, readout string; ghost-on-commit against real
      preview geometry driven by real Tab key events (functional, not source-inspection).
- [ ] No regressions in existing placement modes (line/circle/polyline/gridline/move).
- [ ] Full suite green (chunked — OneDrive-venv 127 flake); manual smoke gates Phase 6.

## Existing Code Context (grounded, commit 8b0181e)

- Arc: `_press_draw_arc` / `_move_draw_arc` (3-click, **inline** commit, `_draw_dim_hint`);
  `ArcItem(center, radius, start_deg, span_deg)` in `construction_geometry.py`.
- Rect: `_press_draw_rectangle` / `_move_draw_rectangle` / `_commit_draw_rectangle_at`
  (2-click; `_draw_rect_from_center` flag exists, unused); `rectangle` schema (X/Y signed);
  `RectangleItem` axis-aligned QGraphicsRectItem, `to_dict`=x/y/w/h, 9 grips, `shape()` stroked.
- HUD seam: `_sync_dynamic_input`, `publish_placement_state` → `_resolved_point`,
  `_on_dynamic_input_committed` (fires on Enter only; Tab = `_step_focus` → `try_commit` validate),
  `_SCHEMA_FOR_MODE` / `_APPLIER_FOR_MODE`.
- Preview is live scene items updated in `_move_*` from `snapped` (frozen when engaged);
  `drawForeground` blocks: 4=dim-hint (11 non-HUD modes), 7=gridline ghost, 8=move ghost.
- Grips consumed raw as scene coords (`model_space.py:4797,6046`); `shape()` mapped via
  `mapToScene` (`:9226,9269`). Snap reads `RectangleItem` at `snap_engine.py:434,662,1121`.
- Cycle: Left-Shift-tap → `cycle_placement_ambiguity`; **no arrow keys bound anywhere**.

## Deferred (filed as follow-ups, out of this branch)

- 3-point / arbitrary-rotated rectangle as a *distinct* placement mode.
- QSettings persistence of the chosen variant across restarts.
- Arc-wall placement mode (the downstream goal this unblocks).
