# Wall Placement Workflow Revision — Design

**Date:** 2026-08-24
**Status:** approved (design); implementation pending
**Tier:** Large (`/todo`)
**Extends (update in place at wrap-up):** `docs/specs/wall-room-floor-system.md`,
`docs/specs/inferred-dimension-driven-placement.md`, `docs/specs/2d-geometry.md §4`,
`docs/specs/ribbon-bar.md`. No new governing spec (no orphan gate).

> The **what** was locked in the 2026-08-24 grill; this doc is the **how**. Scope
> decisions are not reopened here.

---

## 1. Goal

Make wall placement a first-class client of the unified 2D-geometry placement
system (`2d-geometry.md §4`), give it a clean keyboard-driven UX (single button,
`W` shortcut, ←/→ primitive cycle, Spacebar alignment), define a **true wall
centerline** so wall-hosted features stop referencing the alignment/click line,
make walls **full H/V inference participants**, and make **polyline-drawn walls
joined** (dragging a shared endpoint moves both connected walls).

## 2. Motivation

Wall placement is a bespoke pair of modes (`wall` polyline, `wall_rect`) behind a
dropdown, disconnected from the unified 2D-drawing dispatch that every other
placement tool now uses. It has no `W` shortcut, no HUD (typed dimensions), an
inconsistent alignment key (Left-Shift vs. the opening's Spacebar), and — most
importantly — a **latent correctness bug**: wall-hosted openings position
themselves along the wall's *click line* (`wall.pt1`), so on Left/Right-aligned
walls doors/windows sit on the wall **face**, not its true center. Chained walls
also separate on edit because there is no endpoint connectivity.

## 3. Architecture & Constraints

### 3.1 Wall as a variant-bearing placement client (topology)

One `"wall"` scene-mode carries a `_wall_primitive ∈ {"line","polyline","rect"}`
flag. It is registered in the existing placement-variant machinery
(`_init_placement_variants`, model_space.py:4004):

```
_PLACEMENT_VARIANTS["wall"] = [
    ("Wall (Line)",      "Pick wall start point",       λ s: set _wall_primitive="line"),
    ("Wall (Polyline)",  "Pick wall start point",       λ s: set _wall_primitive="polyline"),
    ("Wall (Rectangle)", "Pick first corner",           λ s: set _wall_primitive="rect"),
]
```

- ←/→ cycles the primitive **at step 0 only**, session-sticky, via the existing
  `cycle_placement_variant` (model_space.py:4053) + `_apply_current_variant`
  (:4040) + the `"<label> (←/→ to change): <instr>"` readout — all reused.
- `_at_placement_step_zero()` (:4028) gains a `"wall"` branch:
  `return self._wall_anchor is None and self._wall_rect_anchor is None`.
- `_PRESS_DISPATCH["wall"]` / `_MOVE_DISPATCH["wall"]` become thin routers that
  dispatch on `_wall_primitive` to the existing `_press_wall`/`_move_wall`
  (line/polyline) and `_press_wall_rect`/`_move_wall_rect` (rect) bodies.
- **`wall_rect` scene-mode is retired** — folded into the `"rect"` primitive.

**Constraint:** the wall ←/→ semantics ("cycle the primitive") differ from the
2D-geo tools' ←/→ ("cycle an intra-tool sub-variant"), but the *mechanism* is
identical — `apply_fn` sets a flag. Wall primitives expose **no** 2D-geo
sub-variants (Wall-Rect is axis-aligned 2-corner only; no corner/centre, no rotate
step). ↑/↓ stays **reserved** (nothing claims it) for future polygon-walls.

### 3.2 The reuse boundary (shared-machinery contract)

| Reused as-is | Wall-specific (overridden) |
|---|---|
| ←/→ variant cycle + step-0 gate + sticky index | Press/move routers → wall builders |
| `_TOOL_SHORTCUTS` (`W → set_mode("wall")`) | Thickness-quad preview |
| `get_placement_anchor` (wall anchor) | Appliers building `WallSegment`(s) |
| Always-continuous re-arm + Esc→select | Spacebar alignment |
| Instruction/readout pattern | Joined-endpoint grip propagation |
| HUD schemas (`line`, `rectangle`) | Primitive-aware `active_schema`, `_apply_wall_dynamic_input` |

"Future 2D-geo primitive updates reflect in walls" holds **structurally**: a new
2D-geo primitive exposes its placement interaction through the shared dispatch
surface; wiring it into walls is a new variant row + a wall applier — not a
re-implementation of the placement flow. (Not zero-wall-code: a wall is not a
`LineItem`.)

### 3.3 Dynamic Input (HUD) — full parity

`active_schema()` (model_space.py:4060) becomes **primitive-aware** for `"wall"`
(the same step-aware pattern rect/arc already use):

- `_wall_primitive in ("line","polyline")` → `SCHEMAS["line"]` (Length + Angle).
- `_wall_primitive == "rect"` → `SCHEMAS["rectangle"]` sizing only (no rotate step).

`_APPLIER_FOR_MODE["wall"] = "_apply_wall_dynamic_input"`, which routes on
`_wall_primitive` to build the `WallSegment`(s), using the **same finish-vs-continue
branch** as the mouse path so typed and mouse placement stay in parity
(structural commit parity per `inferred-dimension-driven-placement.md §4.2`).
`"wall"` is **removed from the static `_SCHEMA_FOR_MODE` map** (where it is
currently a parked `line` PROPOSAL, §4.7) and instead special-cased inside
`active_schema()` — exactly the pattern `draw_rectangle`/`draw_arc` already use for
their step-aware schemas — via a small `_wall_schema_for_primitive()` helper. This
promotes wall from a parked schema-only mapping to a built HUD client.

### 3.4 Derived true centerline

`WallSegment` gains **derived** accessors (no stored fields, no serialization
change):

```
half = self.half_thickness_scene();  nx, ny = self.normal()
k = {Center: 0.0, Left: +1.0, Right: -1.0}[self._alignment]
centerline_pt1 = self._pt1 + (nx*half*k, ny*half*k)
centerline_pt2 = self._pt2 + (nx*half*k, ny*half*k)
centerline_midpoint = midpoint(centerline_pt1, centerline_pt2)
```

Derivation verified against `quad_points()` (wall.py:214): Left →
`off_left=normal·2half, off_right=0` → span center `= _pt + normal·half` (k=+1);
Right is the mirror (k=−1); Center is 0. The centerline is **parallel** to the
click line, so `centerline_angle_rad()` and `normal()` are unchanged.

**Readers repoint `pt1 → centerline_pt1`:**
- `wall_opening.center_on_wall` (wall_opening.py:282) — anchor at `centerline_pt1`.
  Because the shift is parallel, the stored `_offset_along` / `cross_offset_mm`
  map **1:1** (no serialization change); a `cross_offset` of 0 now lands on the
  true center. `get_3d_mesh` (:744) inherits the fix via `center_on_wall`.
- `elevation_scene.py:893` — swap its direct `wall.pt1` for `wall.centerline_pt1`.

**Behavior:** Center-aligned walls' openings are **unaffected** (k=0 →
`centerline_pt1 == pt1`). Left/Right-aligned walls' openings shift to true center
on load — the intended bug-fix, accepted with no migration.

### 3.5 Inference (provider + consumer + perf)

- **Provider:** `WallSegment.alignment_reference_points()` (duck-typed, like
  `GridlineItem`'s at gridline.py:874) returns `ReferenceFeature`s at the
  **true-centerline endpoints + centerline midpoint**. (Face/click-line refs
  omitted to avoid guide noise — a filed follow-up.)
- **Consumer:** during wall placement, `_inference_active_item` is set to the
  placement sentinel (drop the `None`-for-wall at set_mode:824-827), so
  `get_effective_position` runs the H/V engine; wall placement snaps to guides
  from all providers (gridlines + walls).
- **Perf (standing rule):** `_collect_alignment_refs` (model_space.py:3716) adds a
  **spatial-filtered** wall pass — an inflated cursor rect (INFERENCE_TOL_PX
  mapped to scene units) queried through the scene BSP index
  (`scene.items(rect)`, **not** `sceneBoundingRect`), type-filtered to
  `WallSegment`, then `alignment_reference_points()` on the survivors. Gridlines
  keep their direct path (small list). Bounds per-frame cost to walls near the
  cursor, independent of total wall count (matches
  `inferred-dimension-driven-placement.md §9.3`). OSNAP (separate `snap_engine.py`)
  already covers walls fully — unchanged.

### 3.6 Spacebar alignment re-key

- **Trigger:** `keyPressEvent` gains a `Key_Space` branch for `mode == "wall"`
  gated on `not is_input_mode()` (mirroring the opening's existing Spacebar
  branch), calling `_cycle_wall_alignment()` (model_space.py:5071) directly.
- **Handler:** unchanged Center→Left→Right cycle; its `wall_rect`-anchor sub-branch
  collapses (rect folds into the `"wall"` primitive). Template sync + live property
  refresh (:5092) unchanged.
- **Left-Shift:** the `("wall","wall_rect")` case is removed from
  `cycle_placement_ambiguity` (model_space.py:5003), so **Spacebar is the sole
  wall-alignment binding**; Left-Shift keeps select/pipe/opening. The HUD-engaged
  gate means Spacebar types into a field when one is active.

### 3.7 Line vs Polyline variants

One shared segment-commit body; a single **finish-vs-continue** branch on
`_wall_primitive`:
- `"line"` → after committing a segment, **finish**: clear `_wall_anchor`, re-arm a
  fresh Line placement (continuous, per the always-continuous contract).
- `"polyline"` → **continue** the chain as today (incl. close-near-start),
  `_press_wall` (model_space.py:8980) behavior.

Both create `WallSegment`s identically (same OSNAP/inference, miter/join, undo).
The HUD applier uses the same branch (parity). `"rect"` keeps its own
`_press_wall_rect` body (2-corner → 4 mitered walls).

### 3.8 Joined wall endpoints (proximity, no connectivity model)

Today `apply_grip(0/1)` (wall.py:423) moves only that wall's endpoint; there is
**no** connectivity (the wall.py:625 "connected walls" path is join-mode-only,
rebuilding all miters by proximity). New behavior lives in the single grip-drag
home (model_space.py:5198): when an **endpoint grip (index 0/1)** moves from
`old_pos` to `new_pos`, find every *other* `WallSegment` whose `_pt1` or `_pt2` ≈
`old_pos` (anti-degeneracy scene-unit epsilon) and apply the same move to it.

- **No stored connectivity, no serialization change.** Works for any coincident
  walls (polyline-drawn *or* manually snapped-together).
- **3+ walls at a vertex** → all coincident endpoints follow (T/X junctions).
- **Scope:** `WallSegment`↔`WallSegment` endpoint grips only (not mid/width grips,
  not walls↔floors).
- **Undo:** rides the existing single grip-drag push (all moved walls captured).
- **Openings** on moved walls re-anchor automatically (centerline derived;
  `_rebuild_path` runs). Miters recompute by proximity; the shared corner stays
  coincident, so the join stays mitered.

## 4. Design Decisions (grill ledger)

| # | Decision | Chosen |
|---|---|---|
| D1 | Mode topology | One `"wall"` mode + `_wall_primitive` variant (A) |
| D2 | HUD scope | Full parity — primitive-aware `active_schema` + wall applier (A) |
| D3 | Centerline accessor | Derived `centerline_pt1/pt2/midpoint`; readers swap `pt1` (A) |
| D4 | Inference | Provider (centerline refs) + consumer + `scene.items(rect)` filter (A) |
| D5 | Spacebar re-key | Direct handler; drop walls from Left-Shift path (A) |
| D6 | Line vs Polyline | Shared body, finish-vs-continue branch (A) |
| D6b | Joined endpoints | Proximity coincident-endpoint propagation, included now (A) |

## 5. Acceptance Criteria

1. `W` posted to a focused `Model_View` (no HUD engaged) enters `"wall"` mode.
2. ←/→ at step 0 cycles Line → Polyline → Rectangle; session-sticky; readout shows
   the label + `(←/→ to change)`.
3. Spacebar (wall mode, not HUD-engaged) cycles alignment Center→Left→Right; the
   preview + property template update; Left-Shift no longer cycles wall alignment.
4. A Left- or Right-aligned wall exposes a true centerline at its geometric center
   (`centerline_pt1 == _pt1 + normal·half_thickness·k`, asserted as observable
   direction/offset, not `== _pt1`).
5. An opening on a Left/Right-aligned wall renders at the wall's true center
   (regression for the bug).
6. A Center-aligned wall + opening round-trips **byte-identical** (no drift for the
   common case).
7. Wall placement **consumes** H/V inference guides (aligns to a gridline/wall
   reference), and a placed wall **provides** H/V references at its centerline
   endpoints/midpoint; the wall provider pass is spatial-filtered.
8. Typed HUD dimensions place walls: Line/Polyline via Length+Angle, Rectangle via
   width/height; typed and mouse placement produce identical geometry (parity).
9. Line variant places one segment then re-arms; Polyline chains and closes near
   start; both match the old `_press_wall` behavior (parity-diff).
10. Dragging a shared endpoint of two polyline-connected walls moves **both**
    walls' endpoints; 3+ walls at a vertex all follow; undo restores all.
11. The single wall ribbon button (no dropdown) enters `"wall"` at the sticky
    primitive (default Line).
12. Full suite green.

## 6. Verification Checklist

- [ ] `W` → wall mode (posted key, focused shown view); ignored while a HUD field
      is engaged.
- [ ] ←/→ cycles Line→Polyline→Rect at step 0; **no** cycle once a point is down.
- [ ] ↑/↓ do nothing in wall mode (reserved; no accidental binding).
- [ ] Spacebar cycles alignment; Left-Shift does not (wall); opening unchanged.
- [ ] `centerline_pt1/pt2/midpoint` correct for Center/Left/Right (ground-truth).
- [ ] Opening on Left/Right wall at true center; Center wall+opening byte-identical
      round-trip.
- [ ] 3D + elevation/section openings match the plan (all read the centerline).
- [ ] Wall placement consumes H/V guides; wall provides refs; provider pass uses
      `scene.items(rect)` (no unbounded scan) — assert via a large-wall-count timing
      or a spy on the query, not `sceneBoundingRect`.
- [ ] HUD parity: typed == mouse for line/polyline/rect walls.
- [ ] Line finishes+re-arms; Polyline chains+closes; parity-diff vs old handlers.
- [ ] Joined endpoints: 2-wall drag moves both; 3-wall vertex all follow; undo OK;
      openings re-anchor.
- [ ] Single wall button; dropdown gone; ribbon spec updated.
- [ ] Tests: posted `QMouseEvent`/`QKeyEvent` on shown+activated view; `qapp`
      fixture; no direct handler calls / `_selected_items` pokes; red-verified with
      fixes stashed.

## 7. Testing Strategy

Placement UX is the "posted-event, real-view" category that has hidden bugs here
before — drive a **shown + activated** `Model_View` with **posted**
`QMouseEvent`/`QKeyEvent`; never call `_press_wall(...)` directly or set
`_selected_items`. Assert **observable** geometry (centerline offset direction,
opening world position, wall count after a rect placement, both walls moved after a
joined-endpoint drag). **Parity-diff** the folded-in handlers against the old
`_press_wall`/`_press_wall_rect` (replacement-review rule). Ground-truth the
convention-critical assertions (centerline is `+normal·half` toward the interior on
a Left wall, not `== _pt1`). `qapp` fixture (no pytest-qt); full suite green
(chunked if it flakes); `--timeout` guard.

## 8. Follow-ups (filed in TODO.md)

- Arc/circle **curved walls** (needs a curved `WallSegment` entity).
- **Polygon walls** (closed N straight mitered segments; ↑/↓ side-count; resolve
  ←/→ vs ↑/↓ key contention).
- **Angled Wall-Parallel / Wall-Perpendicular** inference guides + distance labels
  (general engine upgrade).
- Review wall **sub-variant + polygon-wall key scheme** when curved/polygon land.
- **Opening Spacebar-sole** symmetry (retire opening's Left-Shift alignment path).

## 9. Out of Scope

Curved wall entities; polygon walls; angled inference guides; any change to OSNAP
(already covers walls); any serialization/format change; touching opening placement
keys beyond the filed follow-up.
