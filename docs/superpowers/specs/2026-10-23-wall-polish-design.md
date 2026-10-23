---
status: proposal
last-verified: 2026-10-23
verified-commit: 1f158ae8
applies-to:
  - firepro3d/wall.py
  - firepro3d/wall_outline.py
  - firepro3d/wall_placement_controller.py
  - firepro3d/snap_engine.py
  - firepro3d/halo.py
  - firepro3d/paper_display.py
source-tasks:
  - "todo_open.md: Wall polish (2026-10-23 user batch) -- joints seam lines, HALO alignment offset, footprint snap"
  - "todo_open.md: Extend the 3-wall full-miter pie join to N-way junctions"
  - "todo_open.md: Selected pipes and walls plot their selection highlight on sheets / PDF (scope: every item kind)"
---

# Wall polish -- Design Spec

Consolidating contract for this batch (it touches `wall-room-floor-system.md`,
`selection-mode.md`, `snapping-engine.md` and `paper-space.md`). At Account each
of those specs gets a one-line pointer here; their full rewrite is a follow-up.

## Goal

Walls read as architectural backgrounds for sprinkler layout: every joined
junction draws as one continuous body, the HALO and hit area sit exactly on the
drawn wall, floors snap exactly to wall faces, and no selection highlight ever
plots on a sheet or PDF.

## Motivation

User batch 2026-10-23 (Phase 2 Q1, end goal A). Today a T-junction shows the
through-wall's face line across the joined wall's end; a Left/Right-aligned wall
shows its HALO and hit area on the Center position; floor placement misses wall
faces; selected items plot their highlight on paper.

## Architecture & Constraints

- Root cause shared by the HALO, hit-area and stale-geometry bugs: `paint()`
  recomputes `mitered_quad()` on every paint, while `shape()`, the HALO fallback
  (`halo.py` QGraphicsPathItem branch -> `path()`) and the snap engine
  (`snap_quad_points`, centerline `pt1`/`pt2`) read other copies. The stored
  path is built in `__init__` as Center (no scene -> unmitered) and is never
  rebuilt after `_alignment` is set by placement (`wall_placement_controller.py`
  line, polyline and rect paths) or `WallSegment.from_dict`, nor after a
  neighbour moves.
- Rule: **one geometry source per wall.** Every consumer (paint, `shape()`,
  `boundingRect()`, HALO, snap) reads `WallSegment.outline()`.
- Level visibility is already expressed as `isVisible()` by
  `LevelManager.apply_to_scene` (z-range shaft rule); per-viewport isolation on
  sheets toggles the same flag. Joins adopt it.
- Room boundary detection (`Model_Space._detect_room_boundary`) reads
  centerlines and `nearest_face_point` only; it must yield identical polygons.
- Constants live in `constants.py` (e.g. `MITER_TOL`); no new magic numbers.

## Design Decisions

D1 **Approach A -- one cached outline per wall** (ratified over B "patch each
stale site" and C "derived JunctionItem per cluster"). B keeps several geometry
copies in sync by hand, which is how the current bugs arose; C adds a scene
object with its own z-order, paper-pass, selection and deletion lifecycle for no
gain.

D2 **`firepro3d/wall_outline.py`** (new, pure geometry, no Qt items): cluster
discovery, the N-way pie, the cluster union outline, and the per-wall
`WallOutline` record:
- `body`: the wall's own mitered polygon (fill, hatch clip, HALO, hit area);
- `stroke_segments`: the outline segments this wall strokes;
- `corners`: visible outline corners (mitred junction corners included, hidden
  in-junction corners excluded);
- `faces`: both full face lines; `caps`: end caps on free ends only;
- `centerline`: the true, alignment-correct centerline (ends + midpoint).

D3 **Invalidation is per wall.** `WallSegment.invalidate_geometry()` replaces
`_rebuild_path()` at every caller (grips, translate, rotate, `set_property`,
`snap_endpoint_to`, the join-mode sibling loop, `wall_placement_controller`). It
marks dirty the wall, its old partners/tee hosts (from the cached outline) and
its new ones (fresh proximity query), and transitively their clusters, calling
`prepareGeometryChange()` and `update()` on each. `_alignment` becomes a
property whose setter invalidates (fixes placement and `from_dict` with no extra
calls). `itemChange` invalidates on scene add/remove and on visibility change
(level switch, sheet viewport isolation).

D4 **Joins per level.** Endpoint partners and tee hosts must pass
`isVisible()`. A wall not visible on the active view never joins or shapes a
junction there; an L1-L5 shaft shows a T-break on L3 only where the teeing wall
is visible.

D5 **Bodies.** One wall at an endpoint: unchanged. Two: today's pairwise join.
Three or more under Auto: a generalized pie -- walls sorted by angle around the
junction, each piece bounded by its neighbours' face intersections and running
to the junction point. Three-way results must equal today's 3-wall pie corners
(existing 3-way tests are the parity bar). Tee: today's cope; host body
unchanged.

D6 **Outline = cluster union.** The union `QPainterPath` of a cluster's bodies
is simplified; each wall strokes only the union-boundary segments lying on its
own body edges, with its own pen. A T breaks the host's near face; a failed-tee
stub vanishes into the host; no seam line remains. Walls that overlap without
joining are not a cluster and stroke their full body (unchanged).

D7 **Fill and hatch** clip to the wall's own body, so differing patterns or
colours meet at the miter with no boundary line.

D8 **First plan step is a P4 probe**: `QPainterPath.united()` +
`simplified()` drops the shared miter edges and splits the host face at T
points within tolerance. Fallback if it does not: segment-interval clipping of
each wall's edges against its partners' bodies. D6 stays as-proposed until the
probe passes.

D9 **HALO / hit / bounds.** `halo_trace_path()` (duck-typed hook,
`halo.py`) returns the wall's own body, junction edge included even though it is
not stroked. `shape()` = body plus today's hit band; `boundingRect()` = body
padded by the pen width.

D10 **Snap hook.** A duck-typed `snap_geometry()` on WallSegment returns named
points and edges from `outline()`; the snap engine's three WallSegment
isinstance arms (`_item_segments`, `_collect`, `_geometric_snaps`) collapse into
one hook branch. `snapping-engine.md` section 8.3 names are kept. Face lines
yield an on-face foot snap even with Nearest off (type `nearest`, ranked as
today); the thin-wall face cutoff (`_FACE_COLLAPSE_SCENE_EPS`) no longer applies
to walls. Floor placement already resolves through `SnapEngine.find`, so floor
vertices land on faces.

D11 **Selection never plots.** `paper_display.shows_selection(item)` =
`item.isSelected() and not paper_pass_active()` replaces the raw selection test
at every selection-paint site: wall, pipe, roof, room, floor slab, wall opening,
node, detail view, hydraulic node badge, geometry_2d selected-state guides and
highlights, filled region. Precedent: gridline `not self._paper_render`.

## Acceptance Criteria

- [ ] AC1 Every joined junction (L, T, 3-way, 4+-way, failed-tee stub, any
  angle, thin partitions) paints as one continuous body; no outline segment
  crosses a junction; hatch flows; differing hatch/colour/thickness -> each wall
  fills its own miter side with no boundary line. Unjoined overlaps unchanged.
- [ ] AC2 Join partners = walls visible on the active view; a wall not reaching
  the view range never shapes a junction there.
- [ ] AC3 HALO and hit area trace the wall's own mitered piece for
  Center/Left/Right, right after line, polyline and rect placement, after load,
  and after any edit (own or neighbour).
- [ ] AC4 Footprint snap: visible outline corners, both full faces (snappable
  with Nearest off), caps on free ends, true centerline; thin walls included;
  participation by AC2. A floor placement click near a face lands on it.
- [ ] AC5 Room boundary detection yields identical polygons.
- [ ] AC6 No selection highlight or guide in a paper/PDF pass for every item
  kind in D11; on-canvas selection unchanged.

## Verification Checklist

- [ ] G0 P4 probe (D8) recorded before D6 is built.
- [ ] G1 Junction pixels: L/T/3-way/4-way/failed-tee x Left/Center/Right with
  hatch, real `paint()` into an image: no outline-colour pixels along the seam
  span; hatch present across it.
- [ ] G2 Differing hatch at a junction: each side keeps its pattern; no boundary
  line pixels.
- [ ] G3 Per-level joins: L1-only wall under an L3 wall end -> L3 end stays free
  (end edge drawn); L1-L5 shaft + L3 tee -> T-break on L3, none on L1.
- [ ] G4 HALO: Left/Right walls placed through the real placement controller
  (line + rect) and through save -> load; `halo_scene_path` contains points
  inside both drawn faces and not the half-thickness-offset band; hit-test at a
  drawn face selects the wall; same after a neighbour moves.
- [ ] G5 Snap: `SnapEngine.find` near a Left/Right face middle with Nearest off
  lands on the face; centerline snap lands at the true centre; thin-wall face
  snaps; L1-L5 shaft snaps on L3; a real floor placement click lands on the
  face.
- [ ] G6 Room detection keep-green + one Left/Right T-junction room polygon
  equal before/after.
- [ ] G7 Paper: per item kind, a selected item rendered through a real paper
  pass has no selection-colour pixels; the canvas render still shows it.
- [ ] Each guard shown RED with its rule reverted (VC3).

## Edge Cases & Error Handling

- Pie with a near-parallel neighbour pair: fall back to the pairwise rule for
  that pair (today's MAX_MITER limit applies).
- `united()` yields micro-slivers: segments shorter than a tolerance derived
  from `MITER_TOL` are dropped (plan derives the number).
- Paper viewport isolation toggles visibility -> outlines re-derive per
  viewport; restore re-derives back.
- Explicit Butt/Solid join modes keep today's pairwise semantics; the union
  outline still removes seams inside a joined cluster.

## Performance

Partner discovery stays a scan of `scene._walls` (as today per paint), but now
runs once per invalidation instead of every paint. A level switch invalidates
every wall once (O(n^2) scan worst case, no worse than one paint today). A
spatial filter is a follow-up if a bench shows need.

## Out of scope

Rect walls (moved to the Editor/Build design line), 3D corners (L563), rooms
onto the wall footprint.
