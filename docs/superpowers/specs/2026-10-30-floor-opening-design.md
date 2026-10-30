---
status: proposal          # designed 2026-10-30, unbuilt
last-verified: 2026-10-30
verified-commit: 78382e3e
applies-to:
  - firepro3d/floor_opening.py        # new
  - firepro3d/floor_cut.py            # new (pure)
  - firepro3d/floor_slab.py
  - firepro3d/feature.py
  - firepro3d/feature_placement_controller.py
  - firepro3d/model_space.py           # floor placement machinery, delete, undo, paste
  - firepro3d/placement_input_coordinator.py
  - firepro3d/section_scene.py
  - firepro3d/level_manager.py
  - firepro3d/scene_io.py
  - firepro3d/marks.py
  - firepro3d/element_params.py
  - firepro3d/display_manager.py
  - firepro3d/paper_display.py
  - firepro3d/model_browser.py
  - main.py                            # ribbon button + Feature Browser routing
source-tasks:
  - "todo_open.md → [type:feature] Floor-hosted blank Opening (floor void / penetration) [P2]"
---

# Floor-Hosted Blank Opening (Floor Void) — Design Spec

Governing specs (Rule A — this doc links, never restates): `docs/specs/feature-system.md`
(F3 host strategies, F4 naming), `docs/specs/wall-room-floor-system.md` (§7 wall
openings — the pattern mirrored; §11 floor slab; §12.4 slab schema). Requirements
ratified in the 2026-10-30 Phase 2 grill (handoff decisions); design forks ratified in
Phase 3 (data model, plan linework, Type naming) and §1–§5 approved as presented.

## Goal

Let the user cut a void (stair well, shaft, penetration) through one floor slab: draw
it as a rectangle or polygon on the slab, and see it as a real hole in plan, section and
3D. It is the first **Floor** host strategy (feature-system F3) and the groundwork for
later floor-hosted Features.

## Motivation

Stair and shaft wells are routine in sprinkler layouts (coverage and obstruction
boundaries follow them), and today `floor_slab.py` has no void support at all. Building
the floor host strategy on the plain blank Opening proves host-pick, host-follow and
host-lifecycle for floors before richer floor-hosted Features (tables, riser bases)
arrive (`[feature] Additional host strategies` reuses it).

## Architecture & Constraints

### A1 — `FloorOpening` item, owned by its slab (ratified: data model)

- New module `firepro3d/floor_opening.py`:
  `FloorOpening(DisplayableItemMixin, QGraphicsPathItem)`.
- Fields: `feature_id` (frozen id, F4), `_points: list[QPointF]` in **absolute scene
  coordinates**, `host: FloorSlab` back-ref, `_mark: str`.
- `display_category` → `"Opening"` (the tier-1 label of its Feature; same home
  pattern as `WallOpening.display_category`, wall-room-floor §7.8.1).
- Visibility: `_visibility_by_zrange = True`; `z_range_mm()` delegates to
  `host.z_range_mm()` (a void spans exactly its host's thickness).
- Z-value: host slab z plus the opening category offset, set where `level_manager`
  sets the host's z (mirrors the wall→opening offset there).
- **Lifecycle hard-bound to one host** (Phase 2): cannot exist hostless, never
  re-hosts, deleted with its host; a slab created later inside the void region is not
  cut by it.

### A2 — Slab ownership, persistence, follow-host

- `FloorSlab.openings: list[FloorOpening]` (default empty).
- `FloorSlab.to_dict()` adds `"openings": [op.to_dict() …]` **only when non-empty** —
  existing files and void-less slabs serialize byte-identically. `to_dict` stays the
  single serializer for file and undo (§12.4).
- `FloorOpening.to_dict()` = `{"feature_id", "points", "mark", "display_overrides"?}`
  (`display_overrides` via the shared mixin helper, emitted only when non-empty).
- Re-attach sites (each: `from_dict(…, host=slab)`, append, `addItem`): `scene_io`
  load, `_restore_network`, paste (paste also translates and **mints a fresh Mark**,
  like wall-opening paste). Undo detach removes void items before their slab.
- Follow-host: `FloorSlab.translate` and `manip_rotate` apply the same transform to
  every owned void. `apply_grip`, `insert_point`, `remove_point` do **not** move voids
  (a reshaped slab keeps its voids where they are; cut = intersection, A3).
- Delete: `_bulk_delete` slab branch removes owned voids first; void branch detaches
  from `host.openings`.

### A3 — Cut region (`floor_cut.py`, pure)

New pure module (Qt geometry types only, no widgets/scene):

- `cut_rings(slab_pts, voids_pts) -> list[(outer, [holes])]` — slab polygon minus the
  union of its voids via the Qt path clipper; operands snapped before the boolean and
  no-op booleans skipped (lesson: Qt clipper float noise). A void crossing the slab
  edge cuts only the overlap (Phase 2: keep as drawn, cut = intersection). Empty list
  when a void swallows the slab.
- `triangulate_with_holes(outer, holes) -> (pts, tris)` — bridges each hole into the
  outer ring and runs the existing `geometry_utils.triangulate_polygon` (single
  ring). Fallback if a bridge cannot be found: `vtkContourTriangulator` (P4-probed
  available, VTK 9.6.0) — first plan step probes the bridge on the test shapes.
- `intervals_inside(rings, a, b) -> list[(t0, t1)]` — even-odd spans of segment a→b
  inside the region (section break).

`FloorSlab.cut_region()` caches `cut_rings` output, invalidated when the slab or any
owned void changes geometry.

### A4 — Rendering

- **Plan (ratified: hole + see-through + own outline; linework "both drawn full"):**
  slab occlusion mask, translucent fill and section hatch paint the **cut region**
  (so the level below shows through the hole); the slab **outline stays its full
  boundary** (a swallowed slab stays visible and selectable). The void paints its own
  outline **as drawn**, in the Opening Display-Manager colours, no fill.
- Slab `shape()` = cut region ∪ boundary stroke (a click in the hole does not pick
  the slab); void `shape()` = its polygon ∪ stroke (`HALO_AREA`).
- **Section** (`section_scene`): `ZONE_CUT` slabs draw one `_ElevCutRect` per
  `intervals_inside` span along the cut line instead of one full span. Non-cut
  elevation uses the cut region's extent (an interior void leaves it unchanged; a
  swallowed slab draws nothing).
- **3D:** `FloorSlab.get_3d_mesh` triangulates each outer ring with its holes (top and
  reversed bottom), adds side quads for every ring (hole walls included), returns
  `None` for an empty cut region. Consumers (`view_3d` slab loop + highlight,
  `thermal_radiation_solver`) are unchanged.

### A5 — Feature Type and entry (ratified: Opening > Floor > Sketched)

- `FEATURE_REGISTRY["floor_sketched"] = FeatureDef("floor_sketched", "blank", "Floor",
  "Sketched", "Floor", "Floor Sketched", 0.0, 0.0)` — the shape is drawn, so size
  defaults are unused. Id frozen (F4).
- Routing reads `host_type` (first prod reader): Feature Browser activation and the
  new Architecture-ribbon **"Floor Opening"** button (beside Blank) enter
  `"floor_opening"` mode for a `host_type == "Floor"` Type; wall Types keep
  `"opening"`. `_last_feature` is keyed so the wall **Blank** button never launches
  the floor Type (today it is keyed by `kind`, which both share).

### A6 — Placement (`"floor_opening"` mode)

- Reuses the floor placement machinery (wall-room-floor §11.4; shared rect/polygon
  rules owned by `2d-geometry.md §4`): rect corner / centre / polygon via ←/→ at step
  0, HUD, close-near-first, Delete-pop. **GENERALIZE:** the floor rect/polygon commit
  points take a commit target (slab vs void) instead of constructing `FloorSlab`
  directly; the floor variant/schema tables gain the `floor_opening` mode.
- Host pick (first click): candidates = visible slabs whose **fill path** contains the
  point (`path().contains`, not the stroked `shape()`), ordered by resolved top Z,
  highest first. None → reject (no-op + status "Click on a floor to place an
  opening"). The current candidate is highlighted; **Spacebar** cycles candidates while
  drawing (new `cycle_placement_ambiguity` branch).
- Commit: < 3 points → discarded (no void, no undo entry). Else append to
  `host.openings`, `addItem`, `marks.mint`, `push_undo_state`, `_end_placement_switch`
  (single-placement → Select with the void selected). Behaviour lives in
  `FeaturePlacementController` (its documented home for new host types).

### A7 — Editing

- Vertex grips via `vertex_chain_grip_handles(self, closed=True)`; `translate`,
  `manip_rotate` on the void itself. Every edit invalidates the host's cut region.
- Snap: the void's path supplies vertex + midpoint snaps through the generic
  path branch of `snap_engine`; add `FloorOpening` to `ELEV_Z_SNAPPABLE_CLASSES`.
- Overlapping voids permitted (union in `cut_rings`).

### A8 — Chrome

- **Display Manager:** voids join the existing **"Opening"** row —
  `_is_opening_item`, `_items_for_category_static("Opening")`,
  `apply_category_defaults`, `paper_display._category_for_item` gain the floor-void
  branch.
- **Mark:** one shared "Opening" sequence (wall blanks + floor voids):
  `element_params.category_of` and `marks.items_of_category` include floor voids
  (walls' openings first, then slabs' voids, in list order). Level number from the
  host's `_top_level` when `_top_mode == "level"`, else none.
- **Model Browser:** each void is a child row of its host's row under "Floors (N)"
  (new — wall openings are not nested today); label = Mark or "Opening".
- **Property panel:** `Feature: Opening` (label) · `Type: Sketched` (label) ·
  `Host: <slab name>` (label, read-only) · `Points: N` (label) · `Mark` (string).
  `set_property` pushes undo.

## Design Decisions

| Decision | Chosen | Rejected (why) |
|---|---|---|
| Data model | Own item owned by slab, nested in slab record | Separate scene list + slab uid (slab has no uid; paste/delete/undo need re-linking); plain slab data (no selection, grips, Mark, DM row) |
| Plan linework | Slab outline full + void outline as drawn | Material-only outlines (swallowed slab vanishes; grips off visible line); slab full + void clipped |
| Type naming | Opening > Floor > Sketched, ribbon "Floor Opening" | Opening > Blank > "Floor (sketched)"; new "Shaft" Feature (splits DM row + Mark sequence) |
| Points frame | Absolute scene coords, host transforms carry voids | Host-relative coords (every reader converts; no gain while hosts only translate/rotate) |
| Holes in 3D | Bridge holes into existing ear-clip | pyvista booleans (none in repo, heavier); vtkContourTriangulator kept as fallback |

## Acceptance Criteria

1. Place a floor void (rect corner / centre, polygon) from the ribbon "Floor Opening"
   button and the Feature Browser `Opening > Floor > Sketched` leaf; empty-space first
   click rejected with a status message; < 3 points discards.
2. First click picks the topmost visible slab under it; Spacebar cycles between
   stacked slabs during the draw; the void cuts only its host.
3. Plan: the hole is see-through (level below visible), fill/hatch skip it, slab
   outline stays full, void outline drawn as drawn in the Opening DM colours; a void
   crossing the slab edge cuts only the overlap; a void may swallow the slab.
4. Section: a cut through the void shows a break in the slab; 3D shows a true hole
   with side walls.
5. Void follows a moved / rotated host; has its own vertex grips and move; deleted
   with its host; overlapping voids allowed; edges and vertices snap.
6. Chrome: "Opening" DM row styles it; Mark minted in the shared Opening sequence;
   Model Browser lists it under its host floor; panel shows Feature / Type / Host
   (read-only) / Points / Mark.
7. Survives save/load **and** undo/redo (place, edit, delete host + undo); paste mints
   a fresh Mark; a project with no voids saves byte-identically to today.
8. Wall openings (door / window / blank) behave exactly as before (keep-green baseline:
   54 floor/opening test files, 832 passed, 1 skipped @78382e3e).

## Verification Checklist (VC3 guards — real objects, shown RED without the change)

- [ ] `floor_cut`: interior hole, edge-crossing void, swallowed slab, overlapping voids
      — areas and spans against hand-computed values.
- [ ] Persistence: file round-trip and undo/redo restore voids (points, mark, host);
      delete host + undo restores both; paste re-mints; void-less save unchanged.
- [ ] Plan: on a shown view, a pixel inside the hole shows the lower level's wall
      colour, not the mask colour.
- [ ] Section: cut through a void yields two cut rects straddling it.
- [ ] 3D: mesh top-face area = slab area − void area; side faces include hole walls.
- [ ] Placement via the real view: reject, Spacebar host cycle, < 3 discard, select
      after commit.
- [ ] Follow-host translate + rotate; Mark sequence; DM item list; Model Browser child.
- [ ] Keep-green baseline + coupled tests (VC5; `test_opening_feature.py` host_type
      assertion is rewritten — its contract changes here) + full suite (VC6).

## Edge Cases & Error Handling

| Situation | Ruling |
|---|---|
| First click on no slab | Reject + status |
| Several slabs under first click | Topmost first; Spacebar cycles |
| < 3 points at commit | Discard |
| Void crosses slab edge / host reshaped | Kept as drawn; cut = intersection |
| Void swallows slab | Allowed; slab keeps outline, no fill/3D/section body |
| Overlapping voids | Allowed |
| Host deleted | Voids deleted with it |
| New slab drawn inside a void | Not cut |
| Host top unresolvable (missing level) | Void hidden/skipped exactly as its host |

## Out of Scope

Stairs and multi-level connectivity (stay in `Spec session: Floor openings & stairs`);
sized/parametric floor-void Types; sprinkler coverage/obstruction use of voids; voids
in roofs or ceilings.
