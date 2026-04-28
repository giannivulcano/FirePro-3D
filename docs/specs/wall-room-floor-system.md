# Wall, Room & Floor Slab System — Design Spec

**Date:** 2026-04-27
**Complexity:** Large
**Status:** Draft
**Source tasks:** TODO.md — "Spec & grill session: wall, room & floor slab system"

## 1. Goal

Define from first principles how walls, rooms, floor slabs, and wall openings behave as a unified system — geometry, placement, joinery, boundary detection, NFPA coverage, occlusion, and cross-entity interactions. This spec consolidates wall joinery (snap-engine roadmap item 3) with the audit-identified gaps across `wall.py`, `room.py`, `floor_slab.py`, and `wall_opening.py`.

## 2. Motivation

These four entity types form the core architectural model that drives NFPA 13 sprinkler design. Walls define the built environment; rooms derive from walls and track coverage metrics; floor slabs provide vertical separation and visual masking; wall openings (doors/windows) modify wall geometry and 3D mesh generation. The current implementation (~2350 LOC across four modules) evolved organically. Several behaviors are undocumented, some features exist in the enum but are never exercised (e.g., "Miter" join mode), and cross-module contracts (e.g., opening repositioning on wall edit) are incomplete. This spec establishes the canonical behavior from first principles.

## 3. Architecture & Constraints

### 3.1 Entity Summary

| Entity | Base Classes | Module | Role |
|--------|-------------|--------|------|
| `WallSegment` | `DisplayableItemMixin` + `QGraphicsPathItem` | `wall.py` | Straight-segment wall with thickness, joinery, openings |
| `Room` | `DisplayableItemMixin` + `QGraphicsPolygonItem` | `room.py` | Closed boundary from wall graph, NFPA coverage tracking |
| `FloorSlab` | `DisplayableItemMixin` + `QGraphicsPathItem` | `floor_slab.py` | Polygon slab with thickness, occlusion masking |
| `WallOpening` | `QGraphicsPathItem` | `wall_opening.py` | Wall-hosted cutout (base class for Door/Window) |
| `DoorOpening` | `WallOpening` | `wall_opening.py` | Rectangle + swing arc symbol, sill = 0 |
| `WindowOpening` | `WallOpening` | `wall_opening.py` | Rectangle + crossing diagonals, variable sill |

All entities except `WallOpening` inherit `DisplayableItemMixin` for display system integration (category defaults, per-instance overrides, section-cut flags, Z-range reporting).

### 3.2 Coordinate System

All geometry stored internally in millimeters (project convention). Scene-unit conversion uses `ScaleManager` (`paper_to_scene()` / `scene_to_paper()`). The scale manager always has valid defaults (1 px/mm, 1:100 drawing scale) even before calibration.

### 3.3 Z-Ordering

| Z-value | Entity | Constant |
|---------|--------|----------|
| -80 | FloorSlab | (hardcoded) |
| -60 | Room | (hardcoded) |
| -50 | WallSegment | (hardcoded) |
| -45 | WallOpening | (hardcoded) |

This ordering ensures floor slabs paint first (enabling occlusion masking), rooms paint behind walls, and openings paint in front of their parent wall.

### 3.4 Cross-References

- **Snap engine:** Wall snap targets (centerline endpoints/midpoint, face corners, face midpoints) are defined in `docs/specs/snapping-engine.md` §5 and §8. This spec does not redefine snap rules.
- **View relationships:** Z-range filtering, section-cut semantics, and plan-family depth sorting are defined in `docs/specs/view-relationships.md` §3, §5, §7. This spec defines entity Z-ranges; the view system owns visibility filtering.
- **Display system:** Category defaults, per-instance overrides, and section-cut appearance are defined in `docs/architecture/display-system.md`. This spec documents how each entity participates in the display cascade.

### 3.5 Relationship Map

```
WallSegment ──owns──► WallOpening (lifecycle-bound)
     │
     │ (graph walk, snapshot)
     ▼
   Room ──queries──► SprinklerSystem.nodes (on-demand)
     │
     │ (Z-range feeds ceiling height)
     ▼
 FloorSlab ──thickness──► Room.z_range_mm()
     │
     │ (flags set by)
     ▼
 LevelManager ──sets──► _is_occluding, _is_section_cut
```

## 4. Wall Geometry

### 4.1 Centerline Model

A wall is defined by two scene-coordinate endpoints (`pt1`, `pt2`) representing the wall axis. The axis meaning depends on alignment mode. Wall thickness is applied perpendicular to the axis.

**Derived properties:**
- `centerline_length()` = distance(pt1, pt2)
- `centerline_angle_rad()` = atan2(pt2.y - pt1.y, pt2.x - pt1.x)
- `normal()` = unit vector perpendicular to centerline, rotated +90°: `(-sin(angle), cos(angle))`
- `half_thickness_scene()` = `(thickness_mm / 2) / drawing_scale` converted to scene units

### 4.2 Alignment Modes

Three alignment modes control how the wall rectangle relates to the drawn axis:

| Mode | Axis meaning | Left offset | Right offset |
|------|-------------|-------------|--------------|
| **Center** | Wall centerline | +half_thickness | -half_thickness |
| **Left** | Right face of wall | +full_thickness | 0 |
| **Right** | Left face of wall | 0 | -full_thickness |

"Left" and "Right" are relative to the pt1→pt2 direction vector. The normal vector points left.

**Quad computation** (`quad_points()`):

```
nx, ny = normal()
ht = half_thickness_scene()

Center:   off_left = (nx×ht, ny×ht)        off_right = (-nx×ht, -ny×ht)
Left:     off_left = (nx×2ht, ny×2ht)      off_right = (0, 0)
Right:    off_left = (0, 0)                 off_right = (-nx×2ht, -ny×2ht)

p1_left  = pt1 + off_left
p1_right = pt1 + off_right
p2_right = pt2 + off_right
p2_left  = pt2 + off_left
```

Returns four corners in order: `(p1_left, p1_right, p2_right, p2_left)`.

### 4.3 Thickness Constraints

- **Minimum:** 1 mm (enforced on set). Zero-thickness walls are not supported.
- **Presets:** 4", 6", 8", 12" (101.6, 152.4, 203.2, 304.8 mm). Default: 6" (152.4 mm).
- **Custom:** Any value ≥ 1 mm via property editor.

Zero-thickness "room separation lines" are a distinct concept requiring a future `RoomSeparator` entity (see §14 Roadmap).

### 4.4 Wall Placement Workflow

**Chain mode** (default):
1. User clicks to set anchor (pt1). Snap engine provides the point.
2. User clicks to set tip (pt2). Ctrl constrains to angle increments.
3. Wall created from anchor to tip using active template properties (thickness, alignment, fill, levels).
4. `_auto_join_wall()` snaps endpoints to nearby walls (§5.3).
5. Tip becomes next wall's anchor (chaining). If tip is within tolerance of chain start → loop closes, chain ends.

**Rectangle mode:**
1. User clicks opposite corners of a rectangle.
2. Four walls created along rectangle edges with shared template properties.
3. All four walls auto-joined.

**Template:** A hidden `WallSegment` instance stores the active wall properties (thickness, alignment, color, fill mode, base/top level). Tab cycles alignment during placement.

### 4.5 Grip Points

| Index | Position | Behavior |
|-------|----------|----------|
| 0 | pt1 | Move endpoint, openings reposition |
| 1 | pt2 | Move endpoint, openings reposition |
| 2 | Midpoint | Translate whole wall, openings follow |

`apply_grip()` updates endpoints, calls `_rebuild_path()`, which repositions all owned openings (§7.3).

## 5. Wall Joinery

### 5.1 Join Modes

Three modes, assignable per endpoint:

| Mode | Geometry effect | End-edge drawn? | When used |
|------|----------------|-----------------|-----------|
| **Butt** | No extension — wall ends flat at endpoint | Yes | Free ends, T/cross junctions |
| **Solid** | Quad corners extended to meet partner edges | No (continuous fill) | L-joints (2 walls at corner) |
| **Auto** | Resolved at paint time (see §5.2) | Depends on resolution | Default for all endpoints |

### 5.2 Auto Resolution

`_resolve_join_mode(endpoint_idx, num_walls_at_point)`:

| Walls at point | Resolved mode | Rationale |
|----------------|--------------|-----------|
| 1 (free end) | Butt | Clean termination |
| 2 (L-joint) | Solid | Continuous corner fill |
| 3+ (T/cross) | Butt | Clean termination at complex junction |

### 5.3 Connection Discovery

Connections are **implicit** — discovered by proximity at render time. No persistent connectivity graph.

**Algorithm** (`_compute_mitered_quad()`):
1. For each endpoint, scan all walls in `scene._walls` for endpoints within `WALL_JOIN_TOLERANCE`.
2. Collect partner list: `[(wall, endpoint_index), ...]`.
3. Resolve join mode (§5.2).
4. If Solid: intersect this wall's quad edges with partner's quad edges.
5. Clamp extension to `4 × half_thickness_scene()` to prevent degenerate geometry.
6. Set `solid_ptN` flag to suppress end-edge drawing.

**Constants** (to be moved to `constants.py`):
- `WALL_JOIN_TOLERANCE`: 1.0 scene units (merge distance for endpoint matching)
- `WALL_MAX_MITER_FACTOR`: 4.0 (multiplied by half_thickness for miter clamp)

**Performance note:** The current implementation scans all walls per endpoint (O(n) per wall, O(n²) per scene rebuild). For scenes with many walls, a spatial index should be used to limit the search. This is an implementation concern, not a behavioral change.

### 5.4 Auto-Join on Placement

`_auto_join_wall(wall)` runs immediately after wall creation:

**Pass 1 — Endpoint-to-endpoint:** For each of the new wall's endpoints, search existing walls for an endpoint within `tolerance` (20 scene units). Snap the new wall's endpoint to the existing endpoint. Rebuild the partner wall's path.

**Pass 2 — Tee join:** For unsnapped endpoints, search for the nearest face point on existing walls (within `TEE_TOLERANCE` = 40 scene units). The reference point is the wall's *other* endpoint, so the new wall terminates on the nearest face. The 5% margin on the `nearest_face_point()` parameter-t check prevents false tee detection near wall endpoints.

### 5.5 Miter Geometry

For Solid joins, the quad-corner extension uses line-line intersection:

1. Determine partner's quad edges based on cross/same endpoint alignment.
2. `_intersect_lines(my_left_edge, partner_left_edge)` → intersection point for left corner.
3. Same for right corner.
4. If both intersections exist and within clamp distance → replace endpoint corners.
5. If Solid → set `solid_ptN = True` (suppresses end-edge line in `paint()`).

## 6. Wall Rendering

### 6.1 2D Path

`_rebuild_path()` constructs a `QPainterPath` from the mitered quad (four corners, closed subpath). This path is set on the `QGraphicsPathItem` for Qt's scene management.

### 6.2 Paint

`paint()` renders in layers:

1. **Fill** (if fill mode enabled): Semi-transparent polygon fill (alpha 80) using display fill color.
2. **Left edge**: Always drawn (centerline-parallel).
3. **Right edge**: Always drawn.
4. **End edges**: Drawn only if `solid_ptN` is `False` for that endpoint.
5. **Section hatch** (if applicable): Overlaid when `_fill_mode` is Section/Hatch, OR when `_is_section_cut` is True. Uses shared `draw_section_hatch()` with clip path.
6. **Selection highlight**: Red outline when selected.

### 6.3 Hit-Testing

`shape()` returns a stroked path using `QPainterPathStroker` at a scale-adaptive hit width (4–14 pixels). This provides a comfortable click target even for thin walls at high zoom.

### 6.4 Section-Cut Hatching

Walls participate in the unified section-cut protocol:

1. `LevelManager` sets `_is_section_cut = True` when the view-range cut plane intersects the wall's Z-range.
2. `paint()` calls `draw_section_hatch()` with the wall quad as clip path.
3. Section appearance (color, pattern, scale) is controlled by the display system's three-tier cascade (per-instance > category > factory default).
4. Wall fill mode `FILL_SECTION` forces hatch regardless of cut plane.

### 6.5 3D Mesh

`get_3d_mesh(level_manager)` extrudes the wall to a 3D box:

- **Without openings:** 8 vertices (4 quad corners × 2 elevations), 12 triangles (6 faces × 2).
- **With openings:** Complex mesh with rectangular cutouts. Opening positions normalized to parameter `t ∈ [0,1]` along wall. Vertical regions above/below sill height preserved. Opening width converted from mm to scene units.
- **Coordinate conversion:** Scene units → real mm via scale_manager. Y negated for 3D convention.
- **Z-range:** `base_z = base_level.elevation + base_offset_mm`, `top_z = top_level.elevation + top_offset_mm` (fallback: `base_z + height_mm`).

## 7. Wall Openings

### 7.1 Data Model

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `_wall` | `WallSegment \| None` | constructor | Parent wall reference |
| `_offset_along` | `float` | constructor | Scene units from pt1 along centerline |
| `_width_mm` | `float` | from preset | Opening width in mm |
| `_height_mm` | `float` | from preset | Opening height in mm |
| `_sill_mm` | `float` | 0 (door) / varies (window) | Distance from floor to opening bottom |

### 7.2 Positioning

`center_on_wall()` computes the opening's world position:
```
angle = wall.centerline_angle_rad()
center = wall.pt1 + offset_along × (cos(angle), sin(angle))
```

`_reposition()` sets the item's scene position and calls `_rebuild_path()` to update the local symbol geometry. The item's rotation is set to match the wall angle.

### 7.3 Wall-Edit Reposition Contract

**Invariant:** Any wall geometry change must reposition all owned openings.

`WallSegment._rebuild_path()` must call `_reposition()` on every opening in `self.openings`. This ensures openings follow wall edits in real time — grip drag, translate, or any other geometry mutation.

### 7.4 Offset Clamping

`_offset_along` is clamped to `[0, centerline_length()]` whenever:
- The opening is repositioned (§7.3)
- The user drags the opening along the wall (`translate()`)
- The wall is shortened (endpoint grip drag)

This prevents openings from floating past wall endpoints.

### 7.5 Offset Model

`_offset_along` is **absolute** (scene units from pt1), not parametric. This means:
- Wall shortened from pt2 side: opening stays at same distance from pt1 (clamped if exceeds new length).
- Wall lengthened: opening stays at same distance from pt1.
- Wall translated: opening follows (pt1 moves, offset unchanged, position recomputed).

### 7.6 Door Symbol

- Gap rectangle clearing the wall lines
- 90° swing arc from hinge-side corner (radius = half opening width)
- Fill: dark color (RGB 30, 30, 30)

### 7.7 Window Symbol

- Gap rectangle clearing the wall lines
- Crossing diagonals (X pattern)
- Horizontal centerline (glass pane indicator)
- Fill: semi-transparent blue (RGB 40, 60, 80, alpha 100)

### 7.8 Preset Libraries

**Doors:** 820, 920, 1200, 1800 mm wide × 2040 mm tall. Default: 920×2040.

**Windows:** Widths 600, 900, 1200, 1800 mm. Heights 600, 1200, 1500 mm. Default: 900×1200.

"Custom" preset allows manual dimension entry.

### 7.9 Wall Deletion

When a wall is deleted, all owned openings are removed from the scene and the wall's `openings` list is cleared. Openings cannot exist without a parent wall.

### 7.10 Opening Deletion

When an opening is deleted independently, it is removed from its parent wall's `openings` list and from the scene.

### 7.11 Translation Along Wall

`translate(dx, dy)` projects the movement vector onto the wall direction:
```
proj = dx × cos(angle) + dy × sin(angle)
offset_along += proj
offset_along = clamp(offset_along, 0, centerline_length)
```

This constrains opening movement to the wall axis.

## 8. Room Boundary Detection

### 8.1 Overview

Rooms are created by clicking inside a closed wall loop. The boundary detection algorithm walks the wall graph using the tightest-clockwise-turn heuristic to find the minimal enclosing polygon on the clicked side.

### 8.2 Graph Construction

**Step 1 — Collect nodes:**
- Wall endpoints (pt1, pt2) from all walls visible on the active level.
- Level filtering includes multi-level walls that span through the active level.
- T-junction face points: for each wall endpoint, check if it lands on another wall's face (not at its endpoints). Uses `nearest_face_point()` with `TOL × 3` search radius and a 5% parameter margin to avoid false detection near endpoints.

**Step 2 — Merge close points:**
- Points within `TOL` (2.0 scene units) are merged into unique node indices.
- O(n²) pairwise distance check (acceptable for typical wall counts).

**Step 3 — Build directed edges:**
- For each wall, collect all nodes along its centerline (endpoints + T-junction points on this wall).
- Sort by parameter `t` along the wall.
- Add bidirectional edges between consecutive nodes with precomputed angles.

### 8.3 Boundary Walk

1. Find the nearest wall to the click point (perpendicular projection).
2. Determine which side of the wall was clicked (cross product of wall direction × click offset).
3. Set start node and incoming angle accordingly.
4. **Walk:** At each node, examine all outgoing edges. Choose the edge with the smallest clockwise turn angle from the incoming direction. A turn angle < 1e-10 is treated as 2π (prevents zero-turn loops).
5. Track visited edges to prevent infinite loops.
6. Terminate when returning to the start node with ≥ 3 boundary points.
7. Iteration cap: `2 × node_count + 10` steps. Returns `None` if exceeded.

### 8.4 Alignment Inset

The boundary walk traces wall centerlines/axes. To reach the interior room face, an inset is applied:

| Dominant alignment | Inset distance | Rationale |
|-------------------|----------------|-----------|
| Center | avg_half_thickness | Axis at wall center → shrink by half thickness |
| Left | avg_half_thickness × 2 | Axis at interior face → shrink by full thickness |
| Right | 0 | Axis at exterior face → no inset needed |

"Dominant alignment" is determined by majority vote across boundary walls. Average half-thickness is used — this is a simplification that works well for uniform-thickness walls but may produce slight inaccuracies for mixed-thickness boundaries.

### 8.5 Room as Snapshot

Rooms are **snapshot entities**. Once created, the boundary polygon is independent of the source walls. Moving or deleting a wall does not update or invalidate existing rooms. The user must delete and re-detect to update a room boundary.

This is a deliberate simplification. Live wall-to-room binding would couple room lifecycle to wall edits and complicate undo. See §14 Roadmap for "refresh room" enhancement.

### 8.6 Duplicate Prevention

Before creating a new room, the algorithm checks for existing rooms with substantially overlapping boundaries. Duplicate rooms at the same location are rejected.

## 9. Room Properties & NFPA Coverage

### 9.1 Room Data Model

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `_boundary` | `list[QPointF]` | from detection | Closed polygon vertices |
| `name` | `str` | auto-assigned | Room identifier, used for sprinkler tagging |
| `_tag` | `str` | `""` | NFPA tag |
| `_hazard_class` | `str` | `"Light Hazard"` | One of 7 NFPA 13 classes |
| `_compartment_type` | `str` | `"Room"` | One of 6 types |
| `_ceiling_type` | `str` | `"Noncombustible unobstructed"` | One of 8 NFPA 13 types |
| `_ceiling_level` | `str` | — | Level reference for ceiling elevation |
| `_ceiling_offset` | `float` | `DEFAULT_CEILING_OFFSET_MM` | mm offset from ceiling level |
| `_color` | `QColor` | category default | Fill/stroke color |
| `_label_offset` | `QPointF` | (0, 0) | Drag offset for label positioning |
| `_show_label` | `bool` | `True` | Label visibility toggle |

### 9.2 Hazard Classes

Seven NFPA 13 hazard classifications with associated maximum coverage per sprinkler:

| Hazard Class | Max Coverage (sq ft) |
|-------------|---------------------|
| Light Hazard | 225 |
| Ordinary Hazard Group 1 | 130 |
| Ordinary Hazard Group 2 | 130 |
| Extra Hazard Group 1 | 100 |
| Extra Hazard Group 2 | 100 |
| Miscellaneous Storage | 100 |
| High Piled Storage | 100 |

### 9.3 Compartment Types

Six compartment types: Room, Corridor, Stairwell, Shaft, Attic, Concealed Space.

Currently stored as metadata only — not consumed by coverage calculations. Reserved for the hydraulic solver spec (design area selection rules).

### 9.4 Ceiling Types

Eight NFPA 13 ceiling construction types per Table 10.2.4.2.1(a)/(b):
- Noncombustible unobstructed
- Noncombustible obstructed
- Combustible unobstructed
- Combustible obstructed
- Bar joist (open web steel)
- Concrete T (precast)
- Metal deck
- Wood joist

Currently stored as metadata only — not consumed by coverage calculations. Reserved for the hydraulic solver spec (maximum spacing rules).

### 9.5 Coverage Check

**Area computation:** Shoelace formula on boundary polygon. Result in mm², converted to sq ft for NFPA comparison.

**Perimeter:** Sum of boundary edge lengths.

**Ceiling height:** `ceiling_level.elevation - floor_level.elevation - slab_thickness + ceiling_offset`.

**Coverage per sprinkler:** `area_sqft / sprinkler_count`.

**Pass/fail:** `coverage_per_sprinkler <= max_coverage_sqft(hazard_class)` AND `sprinkler_count > 0`.

### 9.6 Z-Range

`z_range_mm()` returns `(bot_z, top_z)`:
- `bot_z` = floor level elevation
- `top_z` = ceiling level elevation - thickest floor slab on ceiling level + ceiling offset

The slab thickness lookup scans `scene._floor_slabs` for slabs whose level matches `_ceiling_level`.

## 10. Sprinkler Detection

### 10.1 Two-Tier Strategy

Sprinkler-to-room association is evaluated on demand (not cached). Two detection tiers:

**Tier 1 — Explicit tag:**
- Iterate `sprinkler_system.nodes` for nodes with `_room_name == room.name`.
- Tags are set by the auto-populate system.
- Tagged nodes are always associated regardless of position.

**Tier 2 — Spatial fallback** (untagged nodes only):
- XY containment: `QPainterPath.contains(node.scenePos())` against room boundary polygon.
- Z-range filter: `node.z_pos` must be within room's `z_range_mm()`.
- Both checks must pass.

### 10.2 Detection Scope

Only nodes with sprinklers (`node.has_sprinkler()`) are considered. The detection returns sprinkler objects, not nodes.

## 11. Floor Slab

### 11.1 Data Model

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `_points` | `list[QPointF]` | from placement | Closed boundary polygon |
| `_thickness_mm` | `float` | 152.4 (6") | Slab structural depth |
| `_level_offset_mm` | `float` | 0 | Vertical offset from level elevation |
| `_color` | `QColor` | category default | Fill/stroke color |
| `_is_occluding` | `bool` | `False` | Set by LevelManager |
| `_is_section_cut` | `bool` | `False` | Set by LevelManager |

### 11.2 Z-Range

- Top: `level.elevation + level_offset_mm`
- Bottom: `top - thickness_mm`

### 11.3 Placement

Floor slabs are placed by clicking polygon vertices sequentially. `add_point()` adds each vertex; `close_polygon()` finalizes. Minimum 3 points required.

Vertex insertion/removal supported after placement via `insert_point()` / `remove_point()` (maintains ≥ 3 points).

### 11.4 Occlusion Masking

**Trigger:** `LevelManager` sets `_is_occluding = True` when the slab's top surface falls within the plan view Z-range (`view_depth < slab_top <= view_height`).

**Mechanism:** `paint()` draws an opaque background-colored polygon *before* the semi-transparent fill. This visually masks lower-floor content. Qt paints items in ascending Z-order, so floor slabs (Z = -80) paint their opaque mask before walls (Z = -50) on any floor. Walls on the *active* level paint over the mask; walls on *lower* levels (hidden by the level manager) never appear.

**Dependency:** Relies on Z-ordering — floor slabs (Z = -80) paint before walls (Z = -50). The opaque mask is laid down first; same-level walls paint on top of it.

### 11.5 Section-Cut Hatching

`LevelManager` sets `_is_section_cut = True` when the view-range cut plane intersects the slab's Z-range (`z_bot < view_height < z_top`).

`paint()` overlays diagonal hatch via `draw_section_hatch()` with the slab polygon as clip path. Section appearance controlled by the display system cascade.

### 11.6 Rendering

1. **Occlusion mask** (if `_is_occluding`): Opaque polygon in scene background color.
2. **Fill**: Semi-transparent polygon (alpha 50) in display fill color.
3. **Outline**: 1px cosmetic pen in display line color.
4. **Section hatch** (if `_is_section_cut`): Diagonal overlay via shared utility.
5. **Selection**: Red outline.

### 11.7 3D Mesh

`get_3d_mesh(level_manager)`:
1. Triangulate polygon using ear-clipping (`triangulate_polygon()` from `geometry_utils`).
2. Build twin vertex rings at top and bottom elevations.
3. Top face: triangulation output.
4. Bottom face: reversed winding.
5. Side faces: quad strips (2 triangles per edge) connecting top and bottom rings.
6. Convert scene coords to mm via scale_manager.

### 11.8 Grip Points

Every polygon vertex is a grip point. `apply_grip(index, new_pos)` moves the indexed vertex and rebuilds the path.

## 12. Serialization

### 12.1 WallSegment

```json
{
    "type": "wall",
    "pt1": [x, y], "pt2": [x, y],
    "thickness_mm": 152.4,
    "alignment": "Center",
    "color": "#666666",
    "fill_mode": "Solid",
    "join_mode_pt1": "Auto",
    "join_mode_pt2": "Auto",
    "base_level": "Level 1",
    "top_level": "Level 2",
    "height_mm": 3048.0,
    "base_offset_mm": 0.0,
    "top_offset_mm": 0.0,
    "level": "Level 1",
    "user_layer": "Default",
    "name": "Wall 1",
    "openings": [...]
}
```

**Backward compatibility:** `thickness_in` → `thickness_mm` (× 25.4), `height_ft` → `height_mm` (× 304.8), legacy single `join_mode` applies to both endpoints.

**Alignment migration:** `"Interior"` → `"Left"`, `"Exterior"` → `"Right"` on load.

### 12.2 WallOpening

```json
{
    "kind": "door",
    "width_mm": 920.0,
    "height_mm": 2040.0,
    "sill_mm": 0.0,
    "offset_along": 500.0,
    "level": "Level 1",
    "user_layer": "Default"
}
```

Openings are serialized within their parent wall's `openings` array. The wall reference is restored by the caller during deserialization.

### 12.3 Room

```json
{
    "type": "room",
    "boundary": [[x1, y1], [x2, y2], ...],
    "name": "Room 1",
    "color": "#4488cc",
    "hazard_class": "Light Hazard",
    "compartment_type": "Room",
    "ceiling_type": "Noncombustible unobstructed",
    "ceiling_level": "Level 2",
    "ceiling_offset": -50.8,
    "label_offset": [0, 0],
    "level": "Level 1",
    "user_layer": "Default"
}
```

### 12.4 FloorSlab

```json
{
    "type": "floor_slab",
    "points": [[x1, y1], [x2, y2], ...],
    "thickness_mm": 152.4,
    "level_offset_mm": 0.0,
    "color": "#8888cc",
    "name": "Slab 1",
    "level": "Level 1",
    "user_layer": "Default"
}
```

**Backward compatibility:** `thickness_ft` → `thickness_mm` (× 304.8).

## 13. Divergences from Current Implementation

| Area | Current behavior | Spec requirement | Migration |
|------|-----------------|------------------|-----------|
| Alignment naming | `Interior` / `Exterior` | `Left` / `Right` | Rename constants; map on deserialize |
| Join modes | Auto / Butt / Miter / Solid | Auto / Butt / Solid | Remove Miter from enum and dropdown; treat serialized "Miter" as "Butt" on load |
| Min thickness | No enforcement (0 allowed) | 1 mm minimum | Clamp on set and on deserialize |
| Opening reposition | Not called on wall edit | Called from `_rebuild_path()` | Add reposition loop |
| Offset clamping | No clamping | Clamp to [0, centerline_length] | Add clamp in `_reposition()` and `translate()` |
| Dead code | room.py lines 338-339 (unreachable returns) | Remove | Delete dead lines |
| `MITER_TOL` | Hardcoded in `wall.py` | Named constant in `constants.py` | Extract |

## 14. Roadmap (Out of Scope)

Items identified during spec development, deferred to future tasks:

1. **RoomSeparator entity** — zero-thickness partition lines for NFPA coverage boundaries without physical walls.
2. **Room refresh action** — context menu action to re-run boundary detection at the room's original click point after wall edits.
3. **Explicit wall connectivity graph** — persistent neighbor references with spatial index for O(1) lookup. Replaces O(n²) proximity scan.
4. **Alignment flip action** — grip or context menu to reverse Left/Right without redrawing.
5. **Ceiling type → max spacing** — hydraulic solver consumes ceiling type for NFPA 13 Table 10.2.4.2.1 spacing rules.
6. **Compartment type → design area** — hydraulic solver uses compartment type for design area selection.
7. **Mixed-thickness boundary inset** — per-wall inset instead of average half-thickness for rooms bounded by walls of different thicknesses.
8. **Wall connectivity spatial index** — Qt scene spatial index or custom structure to limit miter scan to nearby walls.

## 15. Verification Checklist

- [ ] Spec covers all four modules (wall, room, floor slab, wall opening)
- [ ] Wall geometry defined from first principles (alignment, quad computation, thickness)
- [ ] Joinery contract defined (Auto/Butt/Solid, proximity discovery, resolution rules)
- [ ] Room boundary detection algorithm formalized (graph construction, tightest-CW-turn, inset)
- [ ] NFPA coverage model documented (hazard class → max coverage, pass/fail)
- [ ] Floor slab occlusion and section-cut protocol documented
- [ ] Wall opening lifecycle defined (positioning, reposition-on-edit, clamping)
- [ ] Cross-entity interactions documented (room↔wall, slab↔room Z-range, opening↔wall)
- [ ] Divergences from current implementation flagged with migration path
- [ ] Roadmap captures deferred items
