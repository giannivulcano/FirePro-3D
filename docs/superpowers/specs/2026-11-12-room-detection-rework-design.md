---
status: approved (design), pending build
date: 2026-11-12
run: bug/Large — L1559 (+L1561), folded L1831, L567, L1656
governing-spec: docs/specs/wall-room-floor-system.md (§8 rewritten in place at Account; §9.1, §12)
related: docs/superpowers/specs/2026-10-20-hf4-pick-region-design.md (region finder, pick-point hover)
---

# Room Detection Rework — Design Spec

## Goal

Clicking inside an area enclosed by walls in Room mode creates a room whose boundary is the
actual interior wall faces, for every wall layout users draw: tees (mid-span and near-end),
polyline-drawn chains, Center/Left/Right alignment in either draw direction, mixed thickness,
X-crossings, and rooms inside rooms (the outer room gets a hole). Room mode shows a live hover
of what a click would create.

## Motivation

Phase 1b reproduced wrong rooms in 21 of 26 probe cases (bow-ties, the outer rectangle,
`None`), with nine root causes R1–R9 (`.todo/room-detect-1b.md` §2). Three of them (R6
side-blind alignment inset, R7 no crossing split, R8 disconnected inner loops) cannot be fixed
inside today's centreline-graph model. The HF4 region finder, fed wall bodies, returned the
exact interior-face area in every probe case and builds a 304-wall grid in 96 ms vs 595 ms.

## Ratified rulings (do not re-ask)

Phase 2 (`.todo/room-detect-phase2.md`): Q1 inner room → outer room gets a hole; Q2 refuse
only the same face; Q3 click in a wall's thickness → status, nothing created; Q4 legacy rooms
left as-is; Q4 note: green/yellow hover highlight; Q5 not enclosed → no fill, nearest open end
marked; Q6 gaps close only within the weld tolerance; Q7 crossings split rooms; Q8 visible
walls on the active plan (incl. spanning) bound rooms, hidden walls do not, openings never
break a room.

Phase 3 (2026-11-12):
- **D-R1 Late hole:** placing a room whose walls form an island wholly inside an existing room
  on the same level punches that island as a hole in the existing room, in the same undo step.
  Drawing walls alone changes no room (snapshot rule, spec §8.5).
- **D-R2 Perimeter:** outer ring + every hole ring.
- **D-R3 Tag anchor:** keep the vertex-mean anchor unless it lies outside the room's net area;
  then move it inside (rule in §2.5). Rooms without holes are unchanged.
- **D-R4 Hole hits:** the hole is not the room — pick shape, HALO trace and selection outline
  exclude it.
- **D-R5 Engine:** approach A (below), approved over B (wall-body union) and C (patch the walk).

## Architecture & Constraints

- Geometry in mm (scene units; `pixels_per_mm` calibration applies to displayed area /
  perimeter only — L567).
- The region finder is the one closed-region engine (HF4). Rooms reuse it; no second face
  walker. `_detect_room_boundary`, its tee rule and the alignment inset table (§8.2–§8.4) are
  retired.
- Rooms stay snapshots (§8.5): only placement (and D-R1) writes a boundary or hole.
- `Room` stays a `QGraphicsPolygonItem` (outer ring = `polygon()`); holes live beside it.
- Constants in `constants.py`; theme colours via `theme.detect()` tokens, never literals
  (the existing red not-enclosed literal in `model_view` stays as HF4 shipped it).

## Design

### 1. Detection engine — `firepro3d/room_detection.py` (new)

**1.1 `region_finder.Arrangement.from_pieces(pieces, window) -> Arrangement`** (GENERALIZE):
`_split_all(pieces, window)` → `_weld(pieces, CHAIN_WELD_MM)` → `_prune` → `cls(...)`; `build()`
becomes `from_pieces(_flatten(candidates, window), window)`. No other region-finder change.

**1.2 Candidates:** today's filter, extracted unchanged from `_detect_room_boundary` as
`Model_Space._room_walls(level)`: `w.isVisible()` and (`w.level == level` or
`w._base_level == level` or `_wall_spans_level(w, level)`).

**1.3 Pieces:** for each candidate wall, each edge of `outline_geometry().body` (the joined
`QPolygonF`: mitres, wedges, tee copes) → `Piece(x0, y0, x1, y1, Tag(wall, i, "line", None, 0, 1))`.
Window = the candidates' united body bounds padded by 1 m. Openings do not cut `body`, so a
door never opens a room (Q8).

**1.4 `detect(walls, click) -> RoomFace | Refusal`:**
1. Any candidate body `containsPoint(click, OddEvenFill)` → `Refusal("in_wall")`.
2. `face = arr.face_at(click)`; `None` → `Refusal("open", arr.nearest_open_end(click))`.
3. A face whose interior sample point lies inside a wall body (a wall-body fragment) →
   `Refusal("in_wall")`.
4. `outer` = the face's outer piece cycle as `list[QPointF]` (CCW, duplicate closing point
   dropped).
5. `holes`: `face.islands` grouped into clusters by shared walls (union-find on
   `tag.item` across island cycles); each cluster's walls' bodies → `wall_outline.cluster_union`
   → the outer subpath(s) of that union (largest-area ring per connected component) = one hole
   ring each. Fragmented island cycles (1b: 5 cycles for one 4-wall inner room) thus become one
   clean ring.
6. `RoomFace(outer, holes, area_mm2 = |outer| − Σ|hole|)`.

**1.5 Cache:** `Model_Space._room_arr = (key, walls, Arrangement)`, key
`(active_level, _undo_pos, len(_walls))` (the HF4 key pattern); cleared on Room-mode exit in
`set_mode`. Room mode makes no edits, so the key holds while hovering.

### 2. Room holes — `firepro3d/room.py`

**2.1 Field:** `Room._holes: list[list[QPointF]] = []`; `holes` property returns copies.
Constructor `Room(boundary, holes=None)`.

**2.2 `room_path() -> QPainterPath`:** OddEvenFill; `addPolygon(outer)` + each hole, closed.
The single geometry source for: `paint` (fill and selection outline — replaces
`drawPolygon(self.polygon())`), `shape()` (overridden only when holes exist; else the inherited
shape, so hole-less rooms hit-test exactly as today), `halo._halo_trace_path_local` Room
branch, `_detect_sprinklers`, and new `contains_point(pt) -> bool`.

**2.3 Measures:** `_compute_area_mm2` = |shoelace(outer)| − Σ|shoelace(hole)|;
`_compute_perimeter_mm` = outer + Σ hole perimeters (D-R2); Volume and Coverage follow area.

**2.4 Transforms:** `translate` and `manip_rotate` move/rotate every hole with the outer ring
(paste goes through `translate`).

**2.5 Tag anchor (D-R3):** `_centroid()` keeps the vertex mean when `contains_point` holds;
otherwise the anchor is the midpoint of the widest inside interval of the horizontal line
through the vertex mean (intersections with outer + hole rings, sorted, paired); if that line
has no inside interval, the outer ring's first-edge midpoint nudged inward. `marks.py`'s Room
anchor reads the same helper.

**2.6 Serialization:** `to_dict` writes `"holes": [[[x, y], ...], ...]` only when non-empty;
`from_dict` reads it (absent → `[]`). Old files load and re-save byte-identical for rooms.
Keys documented in spec §12 and `scene-io.md` §2.

**2.7 Consumers (outer-ring readers → `contains_point` / holes):**

| Site | Change |
|---|---|
| `design_area.py` `member_rooms` (~736) | `room.contains_point(pt)` |
| `design_area.py` tile clip (~921–980) | clip tiles against `room_path()` (holes excluded) |
| `element_params.py` `_opening_room` (~240) | `room.contains_point(pt)` |
| `element_params.py` Area / Perimeter / Volume | follow `_compute_*` (net, D-R2) |
| `auto_populate_dialog.py` (~1408–1414) | candidate sprinkler points inside a hole are dropped (filter by `contains_point`); area label (~1202) via the calibrated net area (L567) |
| `model_space._press_room` duplicate gate | same-face rule (§3) |
| `halo.py` Room trace | `room_path()` |

### 3. Placement — `Model_Space._press_room`

1. `detect(...)`: `in_wall` → status "Click inside a room, not on a wall"; `open` → "Not
   enclosed — no closed wall boundary at the click point"; no room.
2. **Same-face duplicate:** an existing room on the active level whose `|area − face.area| ≤
   1 % of face.area` and where each contains the other's interior sample point → "Room already
   exists here"; no room. A room wholly inside another is never a duplicate (Q2).
3. Create `Room(outer, holes)` with today's tail (level, ceiling level, name, `addItem`,
   `_rooms`, `marks.mint`, `apply_category_defaults`, select, panel update).
4. **Late hole (D-R1):** for each existing room R on the active level with
   `R.contains_point(new interior point)`: re-run `detect` at R's interior sample point; every
   resulting hole ring that contains the new face's interior point and is not already one of
   R's holes (same-ring test as §3.2) is appended to `R._holes`, `R._rebuild()`. If the new
   room's walls touch R's walls there is no such island and R is unchanged (overlap, as today).
5. One `push_undo_state()` covers the new room and any punched hole; status "Created
   {name}".

### 4. Hover — Room mode

- `"room"` joins `_MOVE_DISPATCH` → `_move_room(pos)`: `detect` on the cached arrangement;
  writes `_pick_region_preview = (path, open_end, enclosed, covered, tone)`:
  placeable → `(room_path_of(face), None, True, False, "ok")`; same-face room exists →
  `(path, None, True, False, "warn")`; open → `(None, open_end, False, False, None)`;
  in wall → `None`. `update()` the view. Debounce through `QTimer.singleShot(150)` when the
  last build took > 150 ms (HF4 D-A25).
- `model_view.drawForeground` pick-point branch: an optional 5th element `tone` selects the
  colour token (`ok` green, `warn` amber); absent → `accent` (HF4 hatch pick unchanged). Same
  25 % fill + 1.5 px cosmetic stroke; the not-enclosed label + ring unchanged.
- Preview cleared on mode exit (existing `set_mode` clear) and after a press.

### 5. Folded fixes

- **L567:** `Room.get_properties` Area / Perimeter / Volume / coverage `area_sqft` divide by
  `ppm²` / `ppm` (the `element_params._ppm` source); `auto_populate_dialog` area label too.
- **L1656:** `Room.z_range_mm` and `_ceiling_height_mm` match a slab by
  `slab._top_mode == "level" and slab._top_level == ceiling_level` and use the slab's resolved
  thickness (`effective_thickness_mm()` / resolved `z_range_mm()`), not `.level` /
  `_thickness_mm`.
- **L1831:** `_press_room_manual` close and vertex pop and `_press_select_shift_floor` vertex
  delete call `geometry_drawing_controller.close_hit(...)` instead of `8.0 / scale` literals
  (same 8 px; behaviour-neutral).

## Acceptance Criteria

AC1–AC14 as ratified in `.todo/room-detect-phase2.md`, plus:
- AC15 (D-R1) placing an island room inside an existing room punches its hole in that room;
  one undo restores both.
- AC16 (D-R2/D-R3/D-R4) perimeter includes hole edges; a room's tag never anchors in its own
  hole; a click inside a hole does not pick the outer room.

## Verification Checklist

| Guard | Scene / drive | Asserts (ground truth) | RED when |
|---|---|---|---|
| G1 AC1 | walls via the wall tool; `_press_room` through mode dispatch; mid/near-end tee × C/L/R × both orders | simple polygon; area == hand-computed interior faces | old walk (bow-tie / outer rect) |
| G2 AC2 | polyline U-room via `_press_wall`, ends on centreline and on host face | both faces exact | old walk |
| G3 AC3/AC4/AC15 | inner island room; click big room near/far; place inner after outer | hole ring present, area = outer − inner; inner allowed; same face refused; punch + single undo | holes dropped / gate reverted / punch removed |
| G4 AC5–AC8 | in-wall click, gap 0.5 / 5 mm, X-crossing, hidden wall, door | status texts + room counts | each rule reverted |
| G5 AC9 | shown view, posted mouse moves in Room mode | preview tone ok / warn / open-end; viewport repaint | move branch removed / tone fixed |
| G6 AC10/AC16 | save/load with holes; sprinkler in hole; design area; opening probe; auto-populate; old file golden | hole round-trips; consumers exclude the hole; old file unchanged; tag outside hole; hole click picks inner | each consumer switch reverted |
| G7 AC12/AC13 | ppm 2 scene; Level 2 ceiling slab | Area == element_params; ceiling 2748 | ppm / slab match reverted |
| G8 AC14 | manual room close / pop, shift-click floor vertex | same tolerance behaviour via `close_hit` | n/a (neutral; existing test green) |

- `tests/test_wall_polish_rooms.py` bow-tie golden (encodes R1) is re-baselined to the exact
  faces.
- Perf (AC11): bench after smoke, metric confirmed with the user first (Phase 5 Performance).

## Existing Code Context

- `region_finder.py` (`_split_all`, `_weld`, `_prune`, `Arrangement`, `face_at`,
  `nearest_open_end`); `wall.py` `outline_geometry()` → `WallOutline.body`;
  `wall_outline.cluster_union`; `model_space._press_room` / `_detect_room_boundary` /
  `_wall_spans_level` / `_move_pick_region` (pattern); `model_view.drawForeground` pick-point
  branch; `theme` tokens `ok` / `warn`.
- Probes: Phase 1b scratchpad `test_probe_rooms*.py` (the arrangement face equals truth).

## Edge Cases & Error Handling

- No candidate walls on the level → `open` with no open end ("Not enclosed").
- Face area < `CHAIN_MIN_LOOP_AREA_MM2` → `None` → open.
- A wall-body fragment face (click in an overlap sliver) → in-wall refusal.
- Deeper nesting (a room inside the inner room): only the inner room's island is the outer
  room's hole; the inner room gets its own hole when the nested one is an island in it.
- Legacy rooms (no `holes`) and manual rooms: `_holes = []`, every path as today.

## Performance & Security

- Arrangement build over all candidate walls on the level: 96 ms / 304 walls in the 1b probe;
  hover reuses the cached build; debounce above 150 ms. No security surface.

## Code Style & Testing

- Google docstrings; relative imports; new constants in `constants.py`.
- Tests through the real entry points (mode dispatch, posted events on a shown view); each
  guard shown RED with its rule reverted.
