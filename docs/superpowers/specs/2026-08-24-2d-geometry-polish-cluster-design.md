# 2D-Geometry Polish Cluster — Design

**Date:** 2026-08-24
**Status:** approved (design)
**Tier:** Large
**Governs (target):** to be promoted into `docs/specs/2d-geometry.md` at wrap-up (closes the `construction_geometry.py` orphan; retires TODO backlog line 254).

## Goal

Three related 2D-geometry improvements, built together because they share the same subsystem (`construction_geometry.py` + the `model_space.py` placement layer):

1. **Closed-polyline placement** — click the start vertex to close a polyline into an enclosed shape whose shared start/end vertex is a single grip that moves both adjoining segments.
2. **Regular-polygon tool** — a parametric AutoCAD-style POLYGON (centre + #sides + radius, inscribed/circumscribed) as a new first-class `RegularPolygonItem`.
3. **Ribbon cleanup** — rename the Create → "Geometry" group to "2D Geometry" and remove the "Single Place" toggle (placement is always continuous; Esc exits).

## Motivation

- Polylines can currently only be finished *open* (Enter / double-click); there is no way to author a closed region interactively except via the floor/room tools. The existing closed model (coincidence of first/last vertex) yields two separate grips at the shared point that split apart on drag — the opposite of what a closed shape needs.
- There is no regular-polygon primitive; users must trace N-gons vertex-by-vertex.
- The "Single Place" toggle adds an opt-in single-shot mode nobody wants (default was already continuous). Removing it and its ~20 dead branches deletes hidden complexity.

## Architecture & Constraints

**Binding context / patterns reused:**
- `FloorSlab` (`floor_slab.py`) — the established closed-polygon-with-grips model: N points, no duplicate, `closeSubpath()` on `_rebuild_path`, one grip per vertex, "click near first vertex to close" placement (`_press_floor`, model_space.py:8666).
- `Geometry2DMixin` (`construction_geometry.py:31`) — level/offset/fill rows + `is_fillable()` keyed off `get_closed_path()`; both a closed `PolylineItem` and an always-closed `RegularPolygonItem` compose with it unchanged.
- **Opening placement (§7.6, `wall-room-floor-system.md`)** — the precedent for live cycle keys: a `mode == "opening" and not is_input_mode()` block where ←/→ and ↑/↓ mutate state and refresh a ghost **at any step**. Polygon uses this pattern (not the step-0-only `_PLACEMENT_VARIANTS` framework).
- Dynamic Input HUD (`dynamic_input.py`) — `FieldKind.COUNT`/`DIMENSION`; `_SCHEMA_FOR_MODE`/`_APPLIER_FOR_MODE` maps (model_space.py:3914/3934).
- Dual serialization: `_capture_network`/`_restore_network` (undo) **and** `scene_io` (file) are independent hand-written serializers — both change in the same commit (memory: dual serialization paths).
- Snap dispatch: `snap_engine.py` per-type named-point emitter (~641) + intersection-candidate collector (~425).

**Constraints:**
- Backward compatibility is non-negotiable: existing `.fpd` files with coincident-vertex closed polylines (including migrated `HatchItem`s) must load, render, and stay filled.
- Behavior for real users must not change when Single Place is removed (default was already continuous).
- New code lands in `construction_geometry.py` now; the `→ geometry_2d.py` rename is a separate filed follow-up (no half-migrated state).

## Design Decisions

### 1. `PolylineItem` — explicit closed flag
- Add `self._closed: bool = False`. `_rebuild_path()` calls `path.closeSubpath()` when `_closed and len(_points) >= 3`; the vertex list stays `[P0…Pn]` with **no duplicate vertex**.
- `is_closed()` returns the flag; `get_closed_path()` builds from the flag; new `close()` sets it.
- `grip_points()`/`apply_grip()` unchanged → N grips; grip 0 is the shared start/end and moving it updates both adjoining segments (auto-close).
- **Serialization:** `to_dict` adds `"closed"`. `from_dict`: if `"closed"` present → set flag; **else legacy migration** — if first≈last (existing 1e-3 test) set `_closed=True` and drop the duplicate last vertex. Fill then reads correctly.

### 2. `RegularPolygonItem` — new parametric entity
- `class RegularPolygonItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem)` (same base/MRO as `PolylineItem`).
- **Stored state:** `_center: QPointF`, `_sides: int`, `_radius_mm: float`, `_rotation_deg: float`, `_inscribed: bool`. Vertices are **derived** via `_regenerate()` → `QPolygonF` → path (`closeSubpath`); never stored.
- **Geometry convention:** *inscribed* → vertices on the radius circle (`_radius` = centre→vertex); *circumscribed* → edge-midpoints on the radius circle (`_radius` = apothem). Vertex angles = `_rotation_deg + k·360/_sides`.
- `get_closed_path()` returns the polygon → `is_fillable()` always true → fill/level rows via the mixin, identical to other 2D geometry.
- **Grips:** `grip_points()` = `[_center] + vertices`. `apply_grip(0, p)` moves centre; `apply_grip(i>0, p)` sets `_radius = dist(center, p)` and `_rotation` so vertex *i* points at `p`, then regenerates → stays regular. No separate rotation gizmo (panel has an exact Rotation field).
- **Properties:** mixin rows + `Sides`, `Radius` (dimension), `Rotation` (angle), `Shape` (inscribed/circumscribed enum); `set_property` regenerates.
- **Serialization:** `type: "polygon"` with center/sides/radius/rotation/inscribed + `_geom2d_to_dict`.

### 3. Placement integration (`model_space.py`)
- **Polyline close** (`_press_polyline`, :8098): new branch mirroring `_press_floor` — `_polyline_active` with ≥3 points and click within `8px/scale` of `pts[0]` → `close()`, finalize, select, `push_undo_state`, clear active, **stay in polyline mode**. Only `pts[0]` is tested.
- **Close cue** (`_move_polyline`, ~5404): cursor within close tolerance of `pts[0]` (≥3 pts) → snap preview tip to `pts[0]` (draws closing segment) + marker at `pts[0]` (reuse `preview_node`). Else normal follow.
- **Delete key** (keyPressEvent): branch before `delete_selected_items()` — in polyline placement, pop the last vertex; if only the start remains, discard the in-progress polyline and re-arm; stay in mode; `event.accept()`.
- **Polygon mode `"polygon"`:** register in `_press_map` (→ `_press_polygon`), `_move_map` (→ `_preview_from_polygon` live ghost), cursor map (CrossCursor), instruction map. Applier `_commit_polygon_at(tip)` builds the item, appends to new `self._draw_polygons`, selects, `push_undo_state`, stays continuous. Radius < 0.5 mm on click 2 → reject, centre stays armed.
- **Arrow keys** — Opening-style dedicated block (`mode == "polygon" and not is_input_mode()`): ↑/↓ change `_polygon_sides` (clamp 3–120), ←/→ toggle `_polygon_inscribed`, each refreshing the ghost — live at step 0 and during the radius drag.
- **HUD:** new `"polygon"` schema = `Radius` (DIMENSION, min 0) + `Sides` (COUNT, min 3); wire `_SCHEMA_FOR_MODE["polygon"]`/`_APPLIER_FOR_MODE["polygon"]`. Typed commit; rotation from last cursor angle (0° if none). Ctrl angle-snaps radius direction.

### 4. Serialization & snap
- New `self._draw_polygons` collection (init, clear path, item-type→collection map ~603, bulk-select/type lists).
- `_capture_network`/`_restore_network`: add `"polygons"` capture (~3156) + `RegularPolygonItem.from_dict` restore (~3412). Polyline `closed` flag rides the existing capture/restore.
- `scene_io`: add `"polygon"` to save enumeration + load dispatch (~10015/10032/10106) + class registry (~10099). Polyline closed-flag + legacy migration land via the existing `from_dict` path.
- `snap_engine.py`: `RegularPolygonItem` branch in the named-point emitter (~641: vertices=endpoint, edge-centres=midpoint, centre=center, gated on existing toggles) **and** the intersection-candidate collector (~425: polygon edges as segments). Import the class.

### 5. Ribbon (`main.py`)
- Rename group (`:1530`) `"Geometry"` → `"2D Geometry"`.
- Add `_mode_btn(g_geom, "Polygon", …, "polygon")` (placeholder icon acceptable; icon authoring already filed).
- **Remove Single Place — full cleanup:** delete button + wiring (:1541-1546) + `_single_place_btn`; remove `single_place_mode` (:267); collapse the ~20 `if self.single_place_mode:` branches (delete no-else branches; keep only the else body of if/else branches). Repurpose the ~2 `test_single_place_mode_exits_to_select` + `test_single_place_commit_still_closes_cleanly` tests to the continuous-commit path; remove the ~30 defensive `= False` setup lines; rewrite gridline `= True` commit tests.

## Edge Cases & Error Handling
- Polyline: closing needs ≥3 vertices (clicking start with 2 does nothing special). Delete at one vertex cancels the in-progress polyline. Open finish (Enter/double-click) retained.
- Polygon: sides clamped 3–120 (default 6); radius floored at 0.5 mm epsilon with re-pick on reject; vertex-grip drag preserves regularity.
- Legacy load: coincident-vertex polylines migrate to flagged closed with the dup dropped; fill preserved.

## Acceptance Criteria
1. During polyline placement, clicking the start vertex (≥3 pts) closes the shape; the shared vertex is one grip moving both adjoining segments; placement stays in polyline mode.
2. A close cue (marker + snap-to-start preview) appears when the cursor nears the start vertex.
3. Open polylines still finish via Enter and double-click; Delete pops the last vertex (cancels at one).
4. The Polygon tool places a parametric regular polygon (centre→radius+rotation); ↑/↓ change sides and ←/→ toggle inscribed/circumscribed live during placement; the HUD accepts typed Radius + Sides.
5. A placed polygon is panel-editable (Sides/Radius/Rotation/Shape) and stays regular; centre grip moves it; vertex grips resize+rotate while staying regular.
6. Polygons and closed polylines fill, level, snap (vertices/edge-mids/centre), and serialize (file + undo) like other 2D geometry.
7. Existing projects (incl. migrated hatches) load, render, and stay filled.
8. The Create tab group reads "2D Geometry"; the Single Place button is gone; all placement is continuous; the full suite is green.

## Verification Checklist
- [ ] `PolylineItem` closed-flag unit tests (grips, `get_closed_path`, serialization round-trip, legacy migration + fill) — red-verified.
- [ ] `RegularPolygonItem` unit tests (ground-truth vertices for inscribed/circumscribed, regen, regular-preserving grips, serialization, snap emission) — red-verified.
- [ ] Qt interaction tests (posted events on a shown view): polyline close/open/Delete; polygon centre→radius, ↑/↓, ←/→, HUD typed commit; ribbon label + no Single Place + continuous-after-commit — red-verified.
- [ ] Dual serialization (file + undo) covered for both item types.
- [ ] Full suite green (chunked).
- [ ] Governance: `docs/specs/2d-geometry.md` promoted + SPEC-INDEX row + `view-relationships §3.3/§7.3` / `ribbon-bar §3.8` links updated; backlog line 254 retired; frontmatter stamped.

## Deferred (filed follow-ups)
- Explode Polygon → closed polyline (free per-vertex deformation) + parametric re-edit polish.
- Polyline add/remove-vertex + re-open interactions.
- `construction_geometry.py → geometry_2d.py` module rename.
