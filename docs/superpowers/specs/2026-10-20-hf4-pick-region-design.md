---
status: proposal          # approved 2026-10-20 (brainstorm sections 1-3); unbuilt
last-verified: 2026-10-20
verified-commit: 7c674a92
applies-to:
  - firepro3d/region_finder.py
source-tasks: [HF4 (todo_open.md, Hatch & Fill slices)]
---

# HF4 -- Pick-point region finder -- Design

> **Rule A.** The *what* (D-A3..D-A6, D-A25, D-A26) lives in `docs/specs/hatch-and-fill.md`;
> the concept *how* (HD3) in `2026-10-01-hatch-and-fill-concept-design.md`; the region
> primitive, its record and the Select-objects creation in
> `2026-10-20-hf3-filled-region-design.md`. This doc owns only the HF4 build design: the
> arrangement finder, the Pick point mode and its hover overlay.

## Goal

Click inside any enclosed area of a Block Editor drawing and get a Filled Region of exactly
that face -- the clicked quadrant of a circle cut by two lines, the ring between two circles,
the space between a symbol's outline and a placed block's geometry -- with islands left empty
and the boundary rebuilt as exact curves. Hovering shows what a click would fill; where the
area leaks, it shows where.

## Motivation

HF3's Select-objects Fill closes a chain of selected curves end to end and refuses crossings by
design (R3). The user's natural creation (HF3 smoke ruling, 2026-10-20) is click-inside-a-face.
Pick point is the primary creation mode of D-A3; this slice builds it on HF3's primitive.

## Ratified rulings (do not re-ask)

Phase 2 (2026-10-20, AskUserQuestion), all on the user-visible axis:

- **AC1** Fill with an empty selection enters **Pick point** mode; Fill with boundary
  candidates selected runs HF3's chain closure unchanged. Phase 3 add: a selection holding
  **only non-candidates** (text, regions, reference, hidden) also enters Pick point (selection
  cleared) -- Fill never dead-ends on a message unless real candidates fail to close.
- **AC2** One click = exactly the clicked face; islands empty (D-A4); crossings split faces
  (circle + two lines = four quadrants, one per click).
- **AC3** Boundaries = visible 2D primitives + placed block instances' geometry in pose;
  ignored: text, regions, reference-flagged, hidden (D-A5).
- **AC4** Gap <= 1 mm counts as closed (D-A6); otherwise hover shows a red "Not enclosed"
  cursor label plus a red ring at the nearest open end; a click there reports "Not enclosed"
  in the status bar and creates nothing.
- **AC5** Hover inside an enclosed face shows an accent tint + accent boundary trace.
- **AC6** Stay in mode after a pick; one region + one undo step per click; Esc or right-click
  ends the mode; the last region created stays selected.
- **AC7** Click inside a face an existing region already covers (regions are never boundaries)
  -> refused with "This area already has a Filled Region", no tint on hover.
- **AC8** Exact-curve rebuild: line / arc exact, spline sub-range, ellipse arc -> sub-Bezier,
  polyline fallback <= 0.2 mm; new region starts Solid Automatic (HF3 R9); sources untouched
  (R10).
- **AC9** Perf: hover <= 50 ms per move on ~500 primitives (D-A25); bench scenes confirmed with
  the user before Phase 5's bench (see Performance).

## Architecture & Constraints

- **Approach A -- flatten then arrange** (chosen over B exact-curve arrangement and C lazy
  boundary walk): every intersection is segment-segment, so the finder reuses
  `geometry_intersect.line_line_intersection` and needs no arc-arc / Bezier intersection code
  (none exists); the 0.2 mm bar is met by rebuilding exact curves from the source items, not by
  exact intersections; the graph caches per window so a move costs the face walk only.
- **Drawn geometry only** -- edges come from `halo.halo_scene_path(item)` (concept
  Architecture: never read `ArcItem` angles directly).
- **Containment C1 / HF3 R1** -- Block Editor only (`scene_role == "block_editor"`).
- **Pure geometry module** -- `region_finder.py` depends on `QPointF` / `QPainterPath` and the
  2D item constructors only, never on a scene or view; the mode and overlay live in
  `model_space.py` / `model_view.py`.
- Constants reused: `CHAIN_WELD_MM` (1 mm weld), `CHAIN_MIN_LOOP_AREA_MM2` (degenerate face
  guard) from `constants.py`; new ones (flatten sagitta 0.1 mm, polyline fallback 0.2 mm,
  initial window 50 mm, boundary-click nudge 0.5 mm, hover debounce 150 ms, bucket count 32)
  go in `constants.py` under a `REGION_FINDER_*` prefix.

## Design

### 1. `region_finder.py`

**`Arrangement.build(candidates, window: QRectF) -> Arrangement`**

1. *Flatten.* For each candidate item, walk `halo_scene_path(item)` element by element:
   `MoveTo`/`LineTo` -> one segment; `CurveTo` (cubic, as splines and ellipses are drawn) ->
   adaptive subdivision at sagitta <= `REGION_FINDER_SAGITTA_MM`. Every segment carries a
   **tag** `(item, element_index, t0, t1)` -- the source element and its parameter sub-range.
   Only the window-clipped part of the path is kept (segments wholly outside are dropped).
2. *Split.* Segments are bucketed by bounding box into a `bucket x bucket` grid over the
   window; each bucket's pairs run `line_line_intersection`; split parameters are collected per
   segment, sorted, and the segment is cut, each piece keeping its tag with interpolated
   `t0..t1`.
3. *Weld.* Union-find merges vertices within `CHAIN_WELD_MM`. A degree-1 vertex within the
   weld tolerance of an edge **interior** splits that edge and welds to the split point (T-gap).
   Pieces shorter than the tolerance after welding collapse to their vertex.
4. *Prune.* Degree-1 vertices and their edges are removed iteratively; each removed end is
   recorded as an **open end** (position) for the AC4 ring.
5. *Half-edges.* Each remaining edge becomes two half-edges; per vertex the outgoing
   half-edges are sorted by angle so the face walk can take the tightest left turn.

**`Arrangement.face_at(pt: QPointF) -> Face | None`**

- Ray from `pt` toward +X to the nearest edge crossing; the half-edge on `pt`'s side starts
  the walk; at each vertex take the tightest left turn until the start recurs. Signed area > 0
  and >= `CHAIN_MIN_LOOP_AREA_MM2` -> the **outer cycle**; else `None` (unbounded, or no edge
  hit).
- **Islands**: every other closed cycle whose points lie inside the outer cycle and not inside
  another such cycle (one level; the region's OddEven fill handles deeper nesting).
- `Face` = `(outer: list[piece], islands: list[list[piece]], path: QPainterPath)`; pieces keep
  their tags in walk order.

**`Arrangement.nearest_open_end(pt) -> QPointF | None`** -- the recorded open end nearest
`pt`, or `None` when pruning removed nothing (open space).

**`rebuild(face) -> list[list[shape]]`** -- loops of live shapes for
`FilledRegionItem.from_pieces` (loop 0 outer, then islands):

| Source element | Merge rule | Rebuilt as |
|---|---|---|
| `LineItem` / polyline / rect edge (`LineTo`) | consecutive same `(item, element)` | one `LineItem` from the run's first to last point |
| `CircleItem` / `ArcItem` (drawn via `addEllipse` / `arcTo` cubics) | consecutive same item | one exact `ArcItem` (centre, radius from the item; start/span from the run's end angles via `arc_math.yup_angle`), full circle when the run closes |
| `SplineItem` / `EllipseItem` (`CurveTo`) | consecutive same `(item, element)` | one `SplineItem` per cubic sub-range from `geometry_2d.bezier_sub(b, t0, t1)` (the nested `_sub` lifted to a public helper), consecutive elements joined into one spline |
| anything else | -- | `PolylineItem` at <= `REGION_FINDER_POLYLINE_MM` |

Pieces from a block instance's stand-in rebuild the same way (the stand-in *is* a 2D item); the
region holds static copies (D-A1).

### 2. Pick point mode (`model_space.py`)

- `fill_selected_items()`: `fill_candidates(selection)` empty -> `clearSelection()`,
  `set_mode("pick_region")`, status *"Click inside an enclosed area (Esc to finish)"*, return
  `None`. Candidates present -> HF3 path unchanged. The creation tail (from_pieces -> addItem ->
  `_filled_regions.append` -> select only the new region -> `push_undo_state` -> status) moves to
  `_commit_region(loops) -> FilledRegionItem`, called by both paths.
- **Candidates** (`_pick_region_candidates(window)`): `scene.items(window,
  IntersectsItemBoundingRect)` filtered by `fill_candidates`, plus for each visible
  `BlockInstance` in the window `block_snap_geometry.posed_primitives(defn, pose)` stand-ins
  (scaffolding and text already excluded there; a missing or cyclic definition contributes
  nothing).
- **Cache**: `_pick_region_arr = (window, Arrangement)`; dropped on any scene mutation (the
  existing change hooks that `push_undo_state` / item add-remove already fire) and on mode exit.
- **Window**: starts `REGION_FINDER_WINDOW_MM` square around the cursor; when `face_at` returns
  `None` the window doubles and rebuilds until a face is found or the window covers
  `itemsBoundingRect()`; a cursor inside the current window reuses the arrangement.
- **Boundary click (concept Edge Case)**: a query point within `REGION_FINDER_NUDGE_MM` of an
  edge is nudged that distance to the edge's side facing the cursor's last motion vector.
- `mouseMoveEvent` (mode branch): compute `face_at`; if a face is found and an existing
  region's `shape()` contains the point -> preview `(None, None, True, True)`; else store
  `_pick_region_preview = (path, open_end, enclosed, covered)` = `(face.path, None, True,
  False)` or `(None, nearest_open_end(pt), False, False)`; `update()` the view.
  If the last build took > 150 ms, moves are debounced through a `QTimer.singleShot(150)` (the
  D-A25 fallback).
- `mousePressEvent` left: covered -> status *"This area already has a Filled Region"*; no face
  -> status *"Not enclosed"*; face -> `_commit_region(rebuild(face))`, stay in mode. Right
  click and Esc -> `set_mode(None)` (the generic cancel), preview cleared, status cleared.
- `main.py`: the Fill button is enabled whenever a Block Editor tab is active (the
  `fill_candidates`-gated enable rule in `_refresh_modify_buttons` is removed); its tooltip
  says *"Fill: select closed curves, or click with nothing selected to pick a point"*.

### 3. Hover overlay (`model_view.drawForeground`, block-editor branch)

- Enclosed: `theme.detect().accent` at 25 % alpha fills `face.path` (mapped to viewport);
  a 1.5 px cosmetic accent stroke traces it.
- Not enclosed: the cursor label *"Not enclosed"* in the `_draw_dim_hint` idiom (cursor
  + (14, -6), Consolas 9) with a red background; a 6 px red ring at `open_end` when present.
- Covered (AC7): nothing drawn.
- The preview attribute is `None` outside the mode; the branch is skipped.

## Acceptance Criteria

- [ ] AC1-AC9 above, each by its guard in the table below.
- [ ] Testing expectations: `tests/test_region_finder.py` (pure geometry) and
  `tests/test_pick_region_mode.py` (real scene + view, posted events); G12 bench `perf`-marked
  in its own process.
- [ ] Spec amendments at Account: `hatch-and-fill.md` D-A3 "Pick point = HF4" -> BUILT pointer;
  D-A6 leak highlight -> built (ring); concept HD3 -> pointer to this doc; `SPEC-INDEX.md` gains
  `region_finder.py`.

## Verification Checklist

| Guard | Scene | Ground truth asserted | RED when |
|---|---|---|---|
| G1 ring | two concentric circles, pick between | 2 loops; placed-instance pixel filled in the ring, empty at centre | island detection skipped |
| G2 mixed | line + spline + one rect edge | every boundary sample within 0.2 mm of the drawn curves; piece types Line/Spline/Line | polyline fallback forced |
| G2 gap | same with a 1.5 mm gap | hover: enclosed False, `open_end` within 1 mm of the gap; click: status "Not enclosed", region count unchanged | weld tolerance raised to 2 mm |
| Quadrants | circle + two crossing lines | one click -> one region with 1 `ArcItem` + 2 `LineItem`; four clicks -> 4 regions, 4 undo steps | split step skipped |
| Block boundary | instance rotated 30 deg + a line closing against its edge | face found; the arc piece comes from the stand-in | stand-ins not added |
| Already filled | region covering a face, click inside | status text; count unchanged; preview `covered` | AC7 check removed |
| Mode | Fill with empty / text-only selection; Esc; right-click; Fill button with nothing selected | mode entered, exited, button enabled (real ribbon, `test_block_editor_ribbon_tab` idiom); last region selected | enable rule restored |
| Hover | posted move events over a face / a gap | preview path non-empty / label + ring state set | preview not stored |
| G12 perf | bench shapes (a) 500 grid lines, (b) 50 circles x 2 lines | `face_at` per move <= 50 ms after warm-up; build time reported | -- (bench) |

- [ ] All guards RED with their rule reverted (VC3), then green.
- [ ] HF3 suite (`test_filled_region.py`, `test_curve_chain.py`) unchanged and green (VC5).
- [ ] Launch smoke: Fill with nothing selected enters the mode in a real Block Editor; the
  quadrant click, the ring, the leak ring and Esc behave as the rulings say.

## Existing Code Context

REUSE AS-IS: `halo.halo_scene_path`, `geometry_intersect.line_line_intersection`,
`curve_chain` constants + `loop_area`, `FilledRegionItem.from_pieces`, `set_mode`,
`_show_status`, `block_snap_geometry.posed_primitives`, `arc_math.yup_angle`, the
`_draw_dim_hint` overlay idiom, `theme.detect().accent`.
GENERALIZE: `geometry_2d._sub` -> public `bezier_sub`; `fill_selected_items` tail ->
`_commit_region`. GAP: `region_finder.py` (flatten, bucket split, weld, prune, half-edge walk,
islands, rebuild), the mode branches, the overlay. `_detect_room_boundary` (walls, tightest
turn walk) is prior art, not reused -- it has no islands and no cache.

## Edge Cases & Error Handling

- Click on a boundary line -> nudged to the nearer side (section 2).
- Open space (no edge hit by the ray) -> "Not enclosed", no ring.
- Two coincident lines -> the welded edge is one edge; a zero-area face is refused by the
  min-area guard.
- Scene changes while in mode (undo, delete) -> cache dropped, next move rebuilds.
- A face larger than the window -> the window doubles until it is found or the scene bounds are
  reached, then "Not enclosed".
- Source items deleted after the pick -> region unaffected (static copies, D-A1).

## Performance & Security

Bench scenes (to confirm with the user at Phase 5 before measuring): (a) 500 short lines in a
grid, (b) 50 circles each cut by two lines. Metric: `face_at` per move after the window is
built, bar <= 50 ms (D-A25); the build time is reported, not barred, and over 150 ms switches
hover to the debounce. Interleaved base/HEAD pairs with raw lines written to a file.
