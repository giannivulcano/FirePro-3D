# Snap polish batch — refined requirements (Phase 2 output)

Date: 2026-09-24 · Type: feature/Medium (batch; bug members keep repro+guard gates)
Governing specs: `snapping-engine.md`, `align-placement.md`, `selection-manipulator.md`,
`2d-geometry.md`, `text-annotation-system.md`, `wall-room-floor-system.md`, `block-system.md`.
Phase-1b findings (repros, root causes, reuse sweep, keep-green lists):
`<scratchpad>/1b/{S1S2,S3,S4,S5,S6}.md`.

All decisions below were ratified by the user via FP1 questions on 2026-09-24.

## S4 — curve snap accuracy (bug) — do FIRST (engine-level, others build on it)
- Circle radius/centre/quadrants in `snap_engine` come from `rect()` / `_center`/`_radius`,
  never `boundingRect()` (which includes the ~10 px hit stroke and is zoom-cached).
- Cursor-dependent snaps (nearest / perpendicular) on arc, ellipse, Bézier spline and generic
  paths project onto the TRUE curve (flattened path), not the Bézier control polygon; ArcItem
  does not fall through into the generic path branch.
- AC: grip-dragging a line/polyline endpoint onto a circle, arc, ellipse, spline lands on the
  curve (|dist−r| < 0.5 mm / on-curve within flatten tolerance) at m11 0.25, 1.0, and after a zoom
  change.
- Guard (VC3): real Model_Space + shown Model_View, posted mouse events, drag endpoint 3 px off
  circle at m11 0.25 then zoom to 1.0 and repeat; arc + ellipse cases. RED before fix (20/20/48.8 mm).
- Rewrite `test_snap_engine_matrix.py::TestFullCircle` (BR_TOL / tangent calibrated to the
  inflated radius).
- Follow-up (filed): phase-4 intersections on curves use the control polygon.

## S5 — ALIGN crossings reach SNAP (bug)
- One picker: `get_effective_position` makes a single `find(..., align_paths=…)` call when ALIGN
  is active (no SNAP-first early return).
- Ranking: ALIGN crossings (path×path, path×geometry) BEAT the cursor-foot perpendicular/nearest;
  real endpoint / midpoint / center / quadrant / intersection still beat ALIGN crossings.
- AC: (a2) two acquired rays crossing on a LineItem → `align_intersection`; (b) one ray crossing a
  WallSegment face and a RectangleItem edge → `align_intersection` at the true crossing; a real
  endpoint within aperture still wins.
- Guard (VC3): the 1b repro (`s5_repro.py`) turned into a test — real dwell acquires via posted
  mouse moves, real walls/rects. RED before fix.
- Update spec: align-placement §1.1/§3/§3.1 ranking, snapping-engine §14.5.
- **Amended 2026-09-25 (smoke round A):** the live ALIGN point gets the regular snap
  glyph — `align_path` → ⊥ on a perpendicular ray, else the nearest glyph;
  `align_intersection` → the intersection X (align-placement §4). A placement started ON
  any primitive (rect/polyline edge, circle/arc, ellipse/spline) inherits the tangent at
  the clicked point, so the ALIGN ⊥ ray is ⟂ to the edge / radial (align-placement §2.3).

## S1 — true perpendicular-from-start (feature)
- `find()` accepts an optional from-point (the tool's placement anchor, from
  `_mode_placement_anchor()`). When present, `perpendicular` = foot of the perpendicular dropped
  from the from-point onto the candidate segment/line (AutoCAD PER); when absent, today's
  cursor-foot behaviour is kept. **Amended 2026-09-25 (smoke round A):** when absent there
  is NO perpendicular at all — the cursor foot is `nearest` (marker now white).
- Visual: ⊥ marker + a dashed reference guide along the touched line (2d-geometry §3.6 ref style).
- Tools: draw_line, polyline segments, wall, pipe, floor/roof polygon edges. **Amended
  2026-09-25:** also the 1st→2nd-click reference line of draw_rectangle (side), draw_circle
  (radius), draw_ellipse (major axis), draw_arc (step 1) and draw_spline (from the last
  control point); later steps of those tools get no ⊥-from.
- AC: placing a line whose start is off a target line, cursor near where the ⊥ foot lies → the
  committed end point is the foot (segment ⟂ target within 0.01°).
- Guard (VC3): per-tool real-path placement tests (at least line + wall + pipe + floor), asserting
  the dot product of committed segment and target direction ≈ 0.

## S2 — move snaps the moving items' handles (feature)
- All move paths: manipulator interior-drag, all whole-item move grips (line midpoint,
  circle/ellipse/regular-polygon/text/rect centres, wall mid grip — user-approved extension
  2026-09-25, seam review I1), Move tool.
- Handles = the moving items' own snap points (endpoints/midpoints/centres/corners), capped
  (~64) for perf. Targets collected ONCE at press (moving items excluded); per-move work is a
  cheap handle×target test. The closest handle-to-target pair within aperture sets the move; the
  offset is applied to the whole move.
- Handles only (user decision 2026-09-25, smoke item 8): no cursor / grab-point snap on any move
  path (no cursor, ALIGN or grid snap) — without a handle hit the move is the raw cursor delta.
  The Move-tool base point is a handle; the base click itself snaps normally; the destination
  cursor snap (and ALIGN) is dropped. Typed dX/dY still override.
- AC: drag a line so its endpoint comes within aperture of another line's endpoint while the
  cursor is far away → endpoints coincide exactly. Per-move cost at 2k items stays interactive
  (bench: < ~16 ms/move added).
- Guard (VC3): real-path interior drag + Move tool + a move-grip drag test per item type;
  perf bench recorded.

## S3a / Fold D — Ctrl angle constraint on polyline/polygon vertices (bug + feature)
- Open-polyline endpoints constrain against their neighbour (`EndpointGripHandle`); interior
  vertices and closed polyline / floor / roof polygon vertices constrain against the PREVIOUS
  vertex.
- Floor + roof polygon PLACEMENT (press + move) get Ctrl parity with wall.
- AC: Ctrl-drag to 33.69° → 45.00° for polyline end, interior, floor placement, roof placement.
- Guard (VC3): real Model_Space scene (not bare QGraphicsScene), Ctrl on events.
- Rewrite spec text: selection-manipulator.md ~561-564, wall-room-floor-system.md ~213.

## S3b — 2-point polyline commits as a Line (bug)
- At placement finish only (Enter / double-click): one shared `_finish_polyline()` replaces the two
  duplicate finish blocks; 2 points → LineItem (NOT via `_make_line_like` — reference variant leak).
- Existing 2-point polylines in files / paste / blocks untouched.
- Rewrite `test_dynamic_input_parity.py::test_two_point_polyline_survives_the_finish`.

## S6 — text snap points + clean block text (feature + bug)
- `TextItem` removed from `_skip_types`; new branch emits 4 corners (endpoint), 4 edge midpoints
  (midpoint), centre (center) via `grip_points()` (rotation-correct).
- BlockInstance stops emitting glyph-outline vertices (skip text ops — NoPen check as in
  `block_instance.py`); text in a block contributes its 9 box points through the instance pose.
- Guard: count `_collect` results (offscreen has no fonts — don't sweep `find()`).
- Spec: snapping-engine §5 matrix rows (TextItem, BlockInstance), block-system.md:117.

## Fold A — closed stale (docstring fix only in `model_view.py` drawForeground).
## Fold E — `last_point()` on PolylineItem (+ floor/roof), replace the 7 `_points[-1]` sites.

## Side bug (unconfirmed) — grip drags don't snap while `scene.mode is None`
(`model_space.py` gate). User to check during smoke; if it reproduces, file/fix per VC7.
