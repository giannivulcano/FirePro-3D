---
status: implemented   # built 2026-11-14 on feat/3d-solid-csg, merged to main (v0.103.0); as-built contract now in wall-room-floor-system.md s6.5 + view-3d.md s5
last-verified: 2026-11-14
verified-commit: 432e11e9
applies-to:
  - firepro3d/wall.py
  - firepro3d/wall_solid.py      # new: pure manifold3d band-solid builder
  - firepro3d/wall_outline.py    # reused helpers only (cluster_union, boundary_segments, stroke_segments, visible_corners)
  - firepro3d/view_3d.py         # 3D join pool + wall edge actors
  - requirements.txt
source-tasks: ["todo_open.md - 3D: true solid CSG + re-mitre wall corners [P1] (re-scoped 2026-11-13, Phase 2 Q1-Q10)"]
---

# 3D Wall Solids - Design Spec

## Goal

In the 3D view every wall is a watertight solid whose footprint is the wall's
plan body at every joint kind (L mitre, N-way pie, tee cope, stop, free end),
with wall openings cut through it, so 3D corners match plan and each wall's
volume is exact (plan body area x height, minus its opening cuts).

## Motivation

Phase A of openings switched `WallSegment.get_3d_mesh` to `quad_points` so
opening jambs stay square, which left 3D corners butt-joined while plan corners
are seamless mitres and pies. Downstream consumers (thermal radiation, future
quantity take-off) need closed solids with exact volume. VTK
`boolean_difference` was probed in Phase 1b and rejected (about 200 ms per
boolean, non-manifold output, wrong volumes).

## Ratified decisions (Phase 2 grill, 2026-11-13 - settled, not re-opened here)

| Id | Ruling |
|----|--------|
| Q1 | Visual parity now, with downstream-grade solids (watertight, exact volume). No general boolean engine; the 3D "operations" engine is its own design follow-up. |
| Q2 | 3D footprint = the wall's plan body (`outline().body`) exactly, at every joint kind. |
| Q3 | Joins per height band: only walls present in a band join there; above a shorter wall's top (or below a higher base) the taller wall's end takes the shape it would have without the shorter wall. Applies to L, tee and pie. |
| Q4 | Opening cut = the plan gap rect (width x full thickness, perpendicular, centred on the axis) extruded sill->head, applied to the host's own body only (its mitre wedge included); the partner keeps its material. |
| Q5 | Walls + wall openings only. Floors and roofs untouched. |
| Q6 | Thermal results may change; thermal code untouched. Guard: the mesh dict contract holds and a thermal run completes. |
| Q7 | Edge lines match plan: no seam inside a joined junction; stops draw their seam; top/bottom outline, outside verticals and reveal edges draw. |
| Q8 | Perf bar <= 5 ms per wall with 2 openings (re-set by the user 2026-11-14 in Phase 5 from the grilled 1.5 ms, which manifold3d alone - about 1-1.5 ms per wall - cannot meet; base 0.73 ms at `2509b668`, 200 L-joined walls); second bench = pie-junction grid, measured only; interleaved base/HEAD pairs on an idle host after smoke. |
| Q9 | 3D has its own join pool = walls the 3D view shows. |
| Q10 | Guards G1-G9 (Acceptance Criteria). |

## Architecture & Constraints

### D1 - Engine: manifold3d (ratified in Phase 3)

`manifold3d>=3.5` becomes a required dependency (`requirements.txt`). P4
probe (manifold3d 3.5.5, Python 3.13, win_amd64 wheel): an L-mitred
200 x 5000 x 3000 mm body minus a door and a window gave the exact volume
(2.274e9 mm3), status `NoError`, genus 1; evaluation about 1.05 ms per wall
(evaluation is lazy, about 0.5 ms per subtraction; extrude + box build
about 0.06 ms); two bands (one extra union) about 2.4 ms. No fallback
mesher: a second path would need parity guards for nothing.

### D2 - 3D join pool

`View3D._extract_walls` builds the pool once per rebuild: every wall in
`scene._walls` that passes `View3D._is_visible` (the `_display_overrides`
`visible` flag). From it, `join_neighbourhoods(pool)` (`wall.py`) computes
each wall's join ring once per rebuild - the walls whose reach box (end points
grown by 2 x half thickness + `MITER_TOL`) overlaps the wall's own or a
first-ring wall's - and each wall gets its ring as
`wall.get_3d_mesh(level_manager, pool=ring)`; the ring gives the same mesh as
the whole pool (D9). The view keeps the rings until the next rebuild and the
selection highlight passes the cached ring. With no pool (the thermal extract),
the wall builds its own ring from `pool_3d()` (`join_ring`). The plan pool
(`_join_pool`, `isVisible()` for the active plan view) is never used in 3D.

### D3 - `_join_ends(extra=None, pool=None)` (GENERALIZE)

An explicit `pool` replaces the `_join_pool(extra)` call; everything else in
`_join_ends` (stops, pies, tee cope, mitre, clamp fallbacks) runs unchanged.
The plan path passes no pool and is byte-for-byte today's behaviour.

### D4 - Height bands

Breakpoints = the wall's own base/top plus the base/top of every pool wall that
can reach one of its ends (endpoint partner within `MITER_TOL`, or a tee
host/guest within its band), clipped to the wall's own z range. For each band
the members are the pool walls whose z range covers the band; the band body is
the body polygon from `_join_ends(pool=members)` (`[p1l, p2l, *w2, p2r, p1r,
*w1]`, as `_rebuild_outline` builds it). The stop rule still compares full
tops (`z_range_mm`), so the band where both walls of an unequal L are present
gets the plan's stop body, and the band above it gets the taller wall alone.
Adjacent bands with identical polygons merge: an ordinary wall is one band.

### D5 - Opening cuts

Per opening on the wall: the plan gap rect (the geometry `WallOpening._gap_rect`
draws: opening width x full wall thickness, perpendicular to the axis, centred
on the axis at `_offset_along`), in mm, z from `base_z + sill` to
`base_z + sill + height`, clamped to the wall's z range (a cut that clamps to
nothing is dropped, as today). Cuts are subtracted from this wall's solid only.

### D6 - `firepro3d/wall_solid.py` (new, pure, no Qt)

`build_solid(bands, cuts) -> dict | None`:
`bands` = `[(polygon_mm, z0, z1)]`, `cuts` = `[(rect_mm, z0, z1)]`.
Rounds vertices to 1e-4 mm, extrudes each band (`CrossSection` +
`Manifold.extrude`), unions the bands, subtracts all cuts with one
`Manifold.batch_boolean(..., OpType.Subtract)`, returns
`{"vertices", "faces"}`. `WallSegment.get_3d_mesh` does scene->mm conversion
(Y negated, as today), colour, and edges, and keeps the dict contract. The
t-column / z-row mesher in `get_3d_mesh` is deleted.

### D7 - Edge lines (wall-emitted)

`get_3d_mesh` adds an `edges` key: a list of 3D segments in mm.
`View3D` draws a wall's edges as one line actor (a `""` wall keeps its `None`
slot, so the actor lists stay index-parallel); `extract_feature_edges` is no
longer used for walls (it would draw every mitre/pie face).

1. **Band outline:** per band, `cluster_union` of this wall's and its band
   neighbours' band bodies -> `boundary_segments` -> `stroke_segments(own band
   body, boundary)`. Stop seams are already in the plan strokes.
2. **Horizontal edges:** at each band boundary z, the band-below pieces plus
   the band-above pieces minus the parts present in both (collinear 1-D overlap
   subtraction). At base and top this is the bottom / top outline.
3. **Vertical edges:** at `visible_corners` of each band body against its band
   boundary, spanning the band; collinear verticals in consecutive bands merge.
   Each stop seam's endpoints on the faces get a vertical.
4. **Reveal edges:** per cut, its rect outline on both faces plus the four
   depth edges, computed from the cut rect intersected with the band body (a
   cut clipped by a mitre wedge draws only the edges of its own surfaces).
5. Opening frame / leaf meshes (`WallOpening.get_3d_meshes`) are unchanged.

### D8 - Errors and degenerate input

A band polygon with fewer than 3 points or near-zero area is skipped. A
manifold status other than `NoError`, or an empty solid, retries without cuts
and logs a warning; still failing, `get_3d_mesh` returns `None` (today's
degenerate contract; the view skips it).

### D9 - Performance

No mesh caching; `View3D` rebuild triggers unchanged (view-3d spec §2.3).
As built, the first G9 run showed the cost was not meshing but every wall
re-scanning the whole pool on each join query (O(n^2), 27-57 ms per wall); the
lever shipped is the per-rebuild join ring (D2), not the cached-plan-body reuse
first named here. Measured: L scene about 3 ms per wall, pie grid about 5 ms.

## Acceptance Criteria

Every guard drives the real `get_3d_mesh` / `View3D._extract_walls` with real
`WallSegment`s and is shown RED with its rule reverted (VC3).

- [x] **G1** L joint: each wall mesh is closed and manifold (PyVista: 0 open
  edges, manifold), its top-face vertices equal the plan body, volume = body
  area x height minus cuts. RED: 3D footprint from `quad_points` / pool ignored.
- [x] **G2** 3-way and 4-way pies: the sum of wall volumes = union body area x
  height. RED: pie dropped in 3D.
- [x] **G3** Tee: the stub's end vertices lie on the host's near face. RED: cope off.
- [x] **G4** Mixed height/base: band volumes exact; above the shorter wall's top
  the taller wall's end is square (or mitred against a still-present third wall).
  RED: band split off.
- [x] **G5** Door over a mitre wedge: the host loses exactly the cut volume, the
  partner's volume is unchanged. RED: cut applied to the partner.
- [x] **G6** Edge set from the real edge-building path: no segment on a mitre
  diagonal or pie spoke, the stop seam present, reveal edges present. RED:
  feature-edge path restored.
- [x] **G7** A wall hidden in 3D -> the neighbour's end goes square; shown
  again -> restored. RED: 3D pool = all walls.
- [x] **G8** Mesh dict contract (keys, types) holds and a thermal run on a
  sample model completes. RED: a dict key removed.
- [x] **G9** Perf marker, two bench shapes (200 L-joined walls x 2 openings,
  bar <= 5 ms/wall; pie-junction grid with 4-way ends, no openings, measured
  only), interleaved base/HEAD. Plus: the ring gives the whole-pool mesh
  (parity guard) and the selection highlight reuses the rebuild's ring.
- [x] User smoke in the real 3D tab: mitred L, pies, tees, stops, mixed heights,
  openings near a corner, hidden-wall toggle.

## Verification Checklist

- [x] All acceptance criteria met; G1-G8 shown RED with their rule reverted
- [x] Coupled tests (VC5 grep: `get_3d_mesh`, `view_3d`, opening watertight
  tests) green; tests asserting the old mesh layout rewritten to volume/closure
- [x] Plan joinery unchanged (plan-path tests green with no pool passed)
- [x] Full suite (VC6); G9 bench after smoke on an idle host
- [x] Account: wall-room-floor-system §6.5 rewritten as-built + §7.8.3
  pointer; view-3d §5 wall edge source; manifold3d noted as a dependency

## Existing Code Context

- `WallSegment.get_3d_mesh` (`wall.py`): today `quad_points` box +
  t-column/z-row grid with capped reveals.
- `WallSegment._join_ends` / `_join_pool` / `_rebuild_outline` (`wall.py`):
  plan joinery and body polygon assembly.
- `wall_outline.py`: `cluster_union`, `boundary_segments`, `stroke_segments`,
  `visible_corners`.
- `WallOpening._gap_rect`, `_offset_along` (`wall_opening.py`).
- `View3D._extract_walls`, `_add_edge_actor`, `_is_visible` (`view_3d.py`).

## Edge Cases & Error Handling

- Opening crossing the host's end into the partner: cut is host-only (Q4);
  warn/clamp at placement is a filed follow-up.
- Tee guest hidden in 3D: host unaffected (a host keeps its body).
- No level manager: z from `height_mm`, height rule off (as today).
- `""` wall colour: opacity-0 unpickable surface, `None` edge slot (HF1).
