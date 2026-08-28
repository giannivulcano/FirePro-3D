---
status: current          # §4–§13 code-verified as-built; §7 Phase A (first-class Feature-based Opening) BUILT 2026-08-24; §11 two-boundary floor model BUILT 2026-08-28; divergences ledger in §13
last-verified: 2026-08-28
verified-commit: 579e841
applies-to:
  - firepro3d/wall.py
  - firepro3d/room.py
  - firepro3d/floor_slab.py
  - firepro3d/wall_opening.py
  - firepro3d/roof.py
  - firepro3d/model_space.py   # floor placement dispatch + template persistence (§11.9)
  - firepro3d/level_manager.py  # floor pure-z-range visibility + rename remap (§11.3)
---

# Wall, Room & Floor Slab System — Design Spec

**Date:** 2026-04-27
**Complexity:** Large
**Status:** Current
**Source tasks:** TODO.md — "Spec & grill session: wall, room & floor slab system"
**Impl note (2026-07-13):** §5 joinery rewritten as-built after the three-wall-junction fix — 3-wall junctions now get a **full-miter pie join** (`_pie_miter_corners`), tee joins snap to the host **centerline** and cope to its near face (`nearest_centerline_point`, `_tee_cope_corners`). Verified against commit `25e1dea`; tests `tests/test_wall_room_floor.py` (`TestThreeWallJunctionMiter`, `TestTeeJoin`).
**Impl note (2026-07-14):** §9 gains Room Protection Criteria (occupancy, system type, design point — §9.7) and the 8th hazard class (Low-Piled Storage); §12.3 serialization gains the three criteria fields. Verified against commit `5ba9227`; tests `tests/test_room_criteria.py`.
**Design note (2026-08-23):** §7 rewritten as a **first-principles redesign** — the Opening becomes a **first-class, Feature-based** element (Feature > Category > Type; cross-wall placement + orientation mirrors; plan/elevation/3D representations; wall cut; §7.1–7.17). Introduces the forward-looking **Feature system** (§7.16), which graduates to its own governing spec at Phase B. Source: TODO.md "Opening element…" (2026-08-23 grill).
**Impl note (2026-08-28):** §11 (Floor Slab) **rewritten as-built** on `feat/floor-workflow-elevation-model` — the floor gains a **two-boundary elevation model** (independent top + bottom, each with a reference mode), the owning `.level`-for-geometry is **retired** (visibility is pure z-range), and placement is folded onto the unified 2D-geometry dispatch (mirrors the wall §4.4 pattern: one checkable **Floor** button, `F`, ←/→ primitive cycle, rect rotate-step, polygon, continuous placement). §11.10 records the plan view-range upper-bound derivation cross-reference. Verified against commit `579e841`; tests `tests/test_floor_{elevation_model,elevation_projection,serialization,visibility,placement_workflow,panel_display,template_persistence}.py`, `tests/test_graphic_override.py`.

**Impl note (2026-08-24):** §7 **Phase A BUILT** as-built on `feat/opening-feature-element` (subagent-driven; `feature.py`, `feature_browser.py`, rewritten `wall_opening.py`, + model_space/main/elevation_scene/view_3d/display_manager/level_manager/wall wiring; ~40 commits; full suite green). Verified against commit `f5b63b2`; tests `tests/test_opening_{feature,placement,render,persistence,ribbon}.py`. **As-built refinements over the §7 draft** (from smoke tests): (a) **z-order** — an opening is pinned just above its host wall (`level_manager._apply_elev_z`) so its plan gap cuts the wall regardless of head-vs-wall height (§7.7); (b) **plan gap fill** = scene background on screen / paper-white on sheets (not white/dark block); door swing arc spans the opening; (c) **3D** — the door/window **frame is a fixed-depth object** (`_FRAME_DEPTH_MM`), only the wall **cut** matches wall depth; `wall.get_3d_mesh` builds from `quad_points` (un-mitered) so opening jambs stay perpendicular on joined walls (3D corners butt-join — follow-up to re-mitre); walls made watertight through openings (capped reveals, §7.8.3); (d) **paper space** — openings use the "Wall" paper category + a paper-aware gap fill; (e) **undo** — openings ride the existing snapshot undo (no new mechanism, §7.11 correction); (f) a **pre-placement property template** (`current_opening_template`, QSettings `template/opening`) lets sill/size/orientation be set before placing (§7.6). Deferred (filed in TODO): Phase B Manager, Phase C Editor, 3D `boolean_difference`/re-mitre, vertical-plane anchoring, elevation projection polish, panel polish.

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

> **Redesign (§7, PROPOSAL):** `WallOpening` becomes a **first-class `DisplayableItemMixin` element** and the first **Feature** (Category *Openings*; Types Door / Window / **Blank Opening**), adopting elevation-based Z-ordering via `Z_CAT_OPENING`. The as-built rows above (hardcoded Z = −45, no `DisplayableItemMixin`) describe the superseded model (§7.17). See §7.

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

A wall is defined by two scene-coordinate endpoints (`_pt1`, `_pt2`) representing the wall's **alignment reference line** (the click line). The axis meaning depends on alignment mode. Wall thickness is applied perpendicular to the axis.

**Derived geometric properties:**
- `centerline_length()` = distance(pt1, pt2)
- `centerline_angle_rad()` = atan2(pt2.y - pt1.y, pt2.x - pt1.x)
- `normal()` = unit vector perpendicular to the click line, rotated +90°: `(-sin(angle), cos(angle))`
- `half_thickness_scene()` = `(thickness_mm / 2) / drawing_scale` converted to scene units

**True geometric centerline (derived, no serialization change):**

For Center-aligned walls the click line IS the true centerline. For Left/Right-aligned walls the click line is a face; the true centerline is offset perpendicular by `normal() · half_thickness_scene() · k`, where k encodes the alignment:

| Alignment | k | True centerline offset from `_pt1`/`_pt2` |
|-----------|---|--------------------------------------------|
| Center    | 0 | None — click line = true centerline         |
| Left      | +1 | `normal() * half_thickness_scene()`        |
| Right     | −1 | `-normal() * half_thickness_scene()`       |

Three derived accessors (`_centerline_offset()` is the private helper):
- `centerline_pt1` → `QPointF` — first endpoint of the true geometric centerline
- `centerline_pt2` → `QPointF` — second endpoint
- `centerline_midpoint()` → `QPointF` — midpoint of the true centerline

**Consumers of the true centerline:** wall-hosted openings (`center_on_wall` in `wall_opening.py`), the 3D mesh (`get_3d_mesh` via `center_on_wall`), and the elevation-scene projection all reference `centerline_pt1` so that features sit at the wall's true geometric center on Left/Right-aligned walls, not on the click/face line. Center-aligned walls are unaffected (k = 0).

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

Wall placement is a first-class client of the unified 2D-geometry placement dispatch (see `align-placement.md §4` and `2d-geometry.md §4` for shared machinery — not restated here).

**Single `"wall"` scene-mode** carries `_wall_primitive ∈ {"line", "polyline", "rect"}` and `_wall_rect_from_center: bool`. The old separate `"wall_rect"` mode is **retired**; `set_mode("wall_rect")` is a backward-compat alias that folds to `wall + rect primitive`.

**W shortcut** — scene-focus-gated in `Model_View._TOOL_SHORTCUTS` (bare key, no Ctrl/Shift); enters `"wall"` mode and returns focus to the view.

**←/→ cycles the primitive** at step 0 only (session-sticky, via the shared `cycle_placement_variant` + `_PLACEMENT_VARIANTS["wall"]`):

| Slot | Variant | First-step instruction |
|------|---------|------------------------|
| 0 | Wall (Line) | Pick wall start point |
| 1 | Wall (Polyline) | Pick wall start point |
| 2 | Wall (Corner Rectangle) | Pick first corner |
| 3 | Wall (Center Rectangle) | Pick centre point |

↑/↓ are **reserved** (no binding) for future polygon walls.

**Spacebar** cycles wall alignment Center → Left → Right. This is the **sole** alignment binding; Left-Shift no longer cycles wall alignment. Gated on `not is_input_mode()` so a focused HUD field receives the key for typing.

**Line variant:** places one segment (anchor → tip) then re-arms. Ctrl constrains the tip to 45° increments. `_auto_join_wall()` snaps endpoints to nearby walls (§5.3). Placement is always-continuous (Esc → select mode).

**Polyline variant:** chains segments. Ctrl constrains angle. Close-near-start snaps the tip to the chain's first point and ends the chain. Each committed segment calls `_auto_join_wall()`. Otherwise identical to Line.

**Corner / Center Rectangle — 3-step placement:**
1. **Anchor** — first click sets the first corner (Corner variant) or the centre (Center variant).
2. **Sizing** — second click fixes the opposite corner; produces an axis-aligned bounding rectangle. `rect_sizing_points()` (shared with 2D-geo rect, see `construction_geometry.py`) computes `pt1/pt2` from anchor + corner + the `from_center` flag.
3. **Rotate step** — third click sets the rectangle's orientation. Ctrl snaps to 45° increments (pivot = rectangle centroid). HUD uses the `rotation` schema (Y-up CCW, seeded live from the wall pivot). Commit at the desired angle; four mitered `WallSegment`s are built and auto-joined.

**Dynamic Input HUD:** wall is a built HUD client. `active_schema()` dispatches by primitive and step:
- `_wall_primitive in ("line", "polyline")` → `line` schema (Length + Angle)
- `_wall_primitive == "rect"`, sizing step → `rectangle` schema (X, Y signed)
- `_wall_primitive == "rect"`, rotate step → `rotation` schema (Angle)

Typed placement is handled by `_apply_wall_dynamic_input`; typed and mouse placement produce identical geometry (structural commit parity per `align-placement.md §4.2`).

**Template:** A hidden `WallSegment` instance stores the active wall properties (thickness, alignment, colour, fill mode, base/top level). Set before placement via the property panel or by cycling with Spacebar.

### 4.5 Grip Points

| Index | Position | Behavior |
|-------|----------|----------|
| 0 | pt1 | Move endpoint, openings reposition; joined-endpoint propagation (see below) |
| 1 | pt2 | Move endpoint, openings reposition; joined-endpoint propagation (see below) |
| 2 | Midpoint | Translate whole wall, openings follow |
| 3 | Far face midpoint | Drag perpendicular to wall to adjust thickness (min 25.4 mm / 1 inch). For Center alignment the grip sits on the positive-normal face; for Right alignment, the negative-normal face. |

`apply_grip()` updates endpoints (indices 0–2) or thickness (index 3), calls `_rebuild_path()`, which repositions all owned openings (§7.3). The width grip projects the drag position onto the wall normal and converts back to mm via the current scene-to-mm ratio.

**Joined-endpoint propagation (`_propagate_wall_endpoint`, model_space.py):** when an endpoint grip (index 0 or 1) is dragged, `Model_Space` finds every **other** `WallSegment` whose `_pt1` or `_pt2` is coincident with the pre-drag position (proximity, ~0.5 scene-unit epsilon) and applies the same move to it. This keeps polyline-drawn or snapped-together walls joined on edit. No stored connectivity; no serialization change. 2+ walls at a vertex all follow (T/X junctions). Openings on all moved walls re-anchor automatically (`_rebuild_path` runs on each).

**Ctrl angle-snap during grip drag:** holding Ctrl during an endpoint-grip drag (indices 0 or 1) angle-snaps the dragged point to 45° increments **from the opposite endpoint** (`_constrain_angle`). Applies to `WallSegment` grips 0/1, `GridlineItem` grips 0/1, and `LineItem` grips 0/2. (Other grip indices and item types are unaffected.)

## 5. Wall Joinery

### 5.1 Join Modes

Three modes, assignable per endpoint:

| Mode | Geometry effect | End-edge drawn? | When used |
|------|----------------|-----------------|-----------|
| **Butt** | No extension — wall ends flat at endpoint | Yes | Free ends, T/cross junctions |
| **Solid** | Quad corners extended to meet partner edges | No (continuous fill) | L-joints (2 walls at corner) |
| **Auto** | Resolved at paint time (see §5.2) | Depends on resolution | Default for all endpoints |

### 5.2 Auto Resolution

Effective treatment per Auto endpoint (as-built 2026-07-13; the
`_resolve_join_mode(endpoint_idx, num_walls_at_point)` helper still
returns Butt for anything ≠ 2 walls — the pie and tee treatments are
separate branches in `_compute_mitered_quad` keyed on the raw `Auto`
mode, so explicit per-endpoint Butt/Solid overrides keep their meaning):

| Walls at point | Treatment | Rationale |
|----------------|-----------|-----------|
| 1 (free end, no host) | Butt | Clean termination |
| 1, endpoint mid-span on a host wall | **Tee cope** (§5.5) | End hugs the host's near face at any angle |
| 2 (L-joint) | Solid | Continuous corner fill |
| 3 (shared endpoint) | **Full-miter pie** (§5.5) | Seamless junction — a diagonal member's flat Butt end can't mate (2026-07-13 smoke test); falls back to Butt when the geometry degenerates |
| 4+ (cross) | Butt | Near-always orthogonal; flat ends land flush |

### 5.3 Connection Discovery

Connections are **implicit** — discovered by proximity at render time. No persistent connectivity graph.

**Algorithm** (`_compute_mitered_quad()`):
1. For each endpoint, scan all walls in `scene._walls` for endpoints within `WALL_JOIN_TOLERANCE`.
2. Collect partner list: `[(wall, endpoint_index), ...]`.
3. Dispatch per §5.2: raw-Auto with 2 partners → pie miter; raw-Auto with 0 partners → tee-cope host search; otherwise resolve the join mode and, if Solid, intersect this wall's quad edges with `partners[0]`'s quad edges (§5.5).
4. Clamp all extensions to `4 × half_thickness_scene()` to prevent degenerate geometry (fallback: Butt).
5. Set `solid_ptN` flag to suppress end-edge drawing; pie joins additionally emit end-wedge fill vertices.

**Constants** (to be moved to `constants.py`):
- `WALL_JOIN_TOLERANCE`: 1.0 scene units (merge distance for endpoint matching)
- `WALL_MAX_MITER_FACTOR`: 4.0 (multiplied by half_thickness for miter clamp)

**Performance note:** The current implementation scans all walls per endpoint (O(n) per wall, O(n²) per scene rebuild). For scenes with many walls, a spatial index should be used to limit the search. This is an implementation concern, not a behavioral change.

### 5.4 Auto-Join on Placement

`_auto_join_wall(wall)` runs immediately after wall creation:

**Pass 1 — Endpoint-to-endpoint:** For each of the new wall's endpoints, search existing walls for an endpoint within `tolerance` (20 scene units). Snap the new wall's endpoint to the existing endpoint. Rebuild the partner wall's path.

**Pass 2 — Tee join (as-built 2026-07-13):** For unsnapped endpoints, snap to the host wall's **centerline** via `nearest_centerline_point()` (within `TEE_TOLERANCE` = 40 scene units; 5% parameter-t margin keeps it away from the host's endpoints). The picked point stays put — the drawn body is coped back to the host face at render time (§5.5). *Superseded behavior:* the endpoint used to snap to the nearest **face** (`nearest_face_point()`, retained for room detection), which made the picked point visibly jump off the centerline and left diagonal tees with gap triangles.

### 5.5 Miter Geometry

**2-wall Solid joins** — the quad-corner extension uses line-line intersection:

1. Determine partner's quad edges based on cross/same endpoint alignment.
2. `_intersect_lines(my_left_edge, partner_left_edge)` → intersection point for left corner.
3. Same for right corner.
4. If both intersections exist and within clamp distance → replace endpoint corners.
5. If Solid → set `solid_ptN = True` (suppresses end-edge line in `paint()`).

**3-wall full-miter pie** (`_pie_miter_corners`, as-built 2026-07-13):

1. Compute each wall's outward unit vector from the junction; sort the two partners by signed angle from mine.
2. My left/right face each miters (via `_intersect_lines`) with the **angularly adjacent** partner's *wedge-facing* face — the face whose offset points into the wedge shared with me (works for any alignment, since face lines come from `quad_points()`).
3. The third junction corner — the partners' far-face intersection — is appended as an **end-wedge vertex** (`_end_wedge_pts1/2`, returned by `_compute_mitered_quad` and consumed by `_rebuild_path`/`paint`) so every wall's fill polygon covers the junction triangle; the triple overlap is invisible because hatch lines are scene-global. Omitted when the partners' far faces are parallel (diagonal into a split straight run — the end is then a straight edge on the run's near face).
4. Both corners (and the wedge vertex) must fall within the `MAX_MITER_FACTOR` clamp, else the whole endpoint falls back to Butt (e.g. near-parallel members).
5. End edges suppressed (`solid_ptN`); side-face lines terminate exactly at the pie corners. `snap_quad_points()` keeps returning the 4 corners only.

**Tee cope** (`_tee_cope_corners`, as-built 2026-07-13):

1. Host = nearest wall whose centerline passes within `half_thickness + MITER_TOL` of my endpoint, mid-span. This band covers endpoints on the centerline (current tee snap) **and** legacy endpoints parked on the face by the pre-2026-07 snap — old files heal on reload.
2. Near face = the host face on my body's side of the host centerline (sign test against my other endpoint; bail out when I run along the host).
3. Both of my face lines intersect the near-face line → end corners hug the host face at any angle; end edge suppressed; same clamp/fallback as above.

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

## 7. Wall Openings — First-Class, Feature-Based Element (redesign)

> **Status: Phase A BUILT as-built (2026-08-24)** — see the 2026-08-24 impl note at the top of this spec for the as-built refinements over this draft (z-order pin, gap fill, fixed-depth frame, `quad_points` 3D, paper category, template). Superseded the wall-owned-cutout model (retained for reference in §7.17). This section specifies the redesigned **Opening** as the first concrete instance of a new **Feature** framework. **Phase A** (built) = the Opening element + the minimal Feature data model + Feature Browser; **Phase B** (Manager) and **Phase C** (Editor) remain forward-looking (§7.16) and are filed as follow-up tasks. The rest of this spec (§4–§6, §8–§13) is as-built/current.

### 7.1 Scope & Phasing

- **Phase A (this deliverable):** the Opening element — Door / Window / Blank Opening — as a Hybrid first-class, wall-hosted element with the placement/orientation model, the wall cut, all three view representations, level binding, the property panel + "Openings" contextual ribbon tab, a read-only Feature Browser, and 3 seed door Features.
- **Phase B:** Feature **Manager** dialog (load Features into a project; template-project prepopulation).
- **Phase C:** Feature **Editor v1** (author void+symbol Features by drawing 2D geometry).

### 7.2 The Feature Model

A **Feature** is a saved, parametric, placeable *definition* — the 3D/parametric cousin of a `BlockItem` (which groups static 2D geometry). Taxonomy:

> **Feature** (definition) → **Category** (Openings, Furniture, Fixtures, …) → **Type** (Door, Window, Blank Opening, …), placed in the scene as **instances**.

A Feature definition bundles **representation artifacts** (plan schematic, elevation/section schematic, 3D geometry — each authored, see §7.8), **parameters** (size, …), and a **host declaration** (`host_type`). Openings are Category **"Openings"**, `host_type = Wall`. `host_type` is first-class from day one so a future Floor-hosted table or Ceiling-hosted diffuser is a data change, not a re-architecture. Phase A defines Features in a **code registry**; Phase B/C add project-loaded sets and user authoring.

*(Naming note: the future extrude/hole/boolean 3D modeling ops are named **"operations"**, not "features", to avoid colliding with this term.)*

### 7.3 Opening = Hybrid First-Class, Wall-Hosted

An opening is a **first-class element** (own identity, selection, "Openings" contextual tab, property record) that is **hard-bound to exactly one host wall**: it cannot exist wall-less, does **not** re-host to another wall, and is **deleted with its host wall**. (Decision: *Hybrid* — first-class identity + wall lifecycle dependency; no floating/re-hosting openings in MVP.)

### 7.4 Data Model

**Feature definition (registry):** `id`, `category` ("Openings"), `type` ("Door"|"Window"|"Blank Opening"), `host_type` ("Wall"), default parameters (width/height/sill), and the three representation artifacts (§7.8) as scale-parametric authored geometry.

**Opening instance (placed):**

| Field | Notes |
|-------|-------|
| `feature_id` | Which Feature definition. |
| host wall | Implicit = parent wall (serialized within it, §7.11). |
| `offset_along` | Scene units from wall pt1 (along-wall position; clamped §7.7). |
| `cross_offset_mm` | Signed cross-wall offset from the alignment reference (proud allowed; sign-flips on facing mirror, §7.5). |
| `alignment` | `Centered` \| `Flush-front` \| `Flush-back`. |
| `mirror_hinge` | bool — YZ mirror (hand/hinge, along wall). |
| `mirror_facing` | bool — XZ mirror (which face it faces). |
| `width_mm`, `height_mm`, `sill_mm` | Size (override the definition defaults; drive the parametric scale). |
| `level` | Default = host wall base level; user-assignable (§7.9). |

### 7.5 Reference Frame, Position & Orientation

Each opening carries a **local reference frame** anchored on its host wall (local X = along wall, Y = across wall / thickness, Z = up):

- **XY plane (level plane)** — horizontal at the opening's Level elevation; sill/head measured up in world-Z from it (§7.9).
- **XZ plane (wall plane)** — vertical, along the wall through its **true geometric centerline**. The along-wall origin is `centerline_pt1` (§4.1), so `cross_offset_mm = 0` lands at the wall's true centre regardless of alignment. The opening may be **offset** across the wall (`cross_offset_mm`) and **mirrored** about this plane (`mirror_facing`).
- **YZ plane** — vertical, perpendicular to the wall through the opening centre. Aligns to nothing; used only to **mirror** the opening along the wall (`mirror_hinge` — the hand/hinge side).

> **As-built (2026-08-25):** `wall_opening.py`'s `center_on_wall` helper anchors at `wall.centerline_pt1` (not `wall.pt1`). `get_3d_mesh` and the elevation-scene projection inherit the fix via `center_on_wall`. Center-aligned walls are unaffected (k=0 → `centerline_pt1 == pt1`).

**Cross-wall alignment** (`Centered` / `Flush-front` / `Flush-back`) is the preset that `cross_offset_mm` is measured from; **Centered + 0** is the default. The cross-wall offset is **continuous** and **not clamped** — a positive offset intentionally sits the opening *proud* of a face.

**Sign-flip invariant (hard):** `cross_offset_mm` is defined in the opening's own facing frame, so a **facing mirror negates the world-space offset**. An element sitting *proud of the front face* stays *proud of the back face* after a facing flip — never recessed.

**Offset preserved on alignment cycle:** cycling `alignment` (Spacebar) **preserves** the typed `cross_offset_mm` (set "Flush-back, +10 mm" then re-centre without losing the 10).

### 7.6 Placement Mode & Controls

Placement is an **active placement mode** (no literal drag-drop). Entered from either a **ribbon quick-button** (Door / Window / Blank Opening — launches the last-used Feature of that Type) or the **Feature Browser** (activating a Feature carries *that* Feature into the mode). Behavior:

- Live preview follows the cursor onto a wall; commit click places the opening.
- **Spacebar** → cycle cross-wall **alignment** (Centered / Flush-front / Flush-back).
- **← / →** → **hinge** flip (YZ mirror).
- **↑ / ↓** → **facing** flip (XZ mirror).
- Committing over **empty space (no host wall)** is **rejected** (no-op + status message).
- The same keys + the **property panel** edit a **selected** placed opening (undoable), matching how walls expose alignment via both the cycle key and the panel.
- **Keyboard gating:** these keys are gated **off while a Dynamic Input HUD field is focused** (typing a dimension must not cycle) — same rule as the wall-alignment Spacebar change.

**Dependencies to record:** (a) Spacebar-for-alignment is the *target* convention of the pending P1 task *"Cycle key: Left-Shift tap → Spacebar"* (walls); openings adopt the target. (b) In opening-placement mode, **←/→ rebinds** from the generic "placement-variant" cycle to the hinge mirror.

### 7.7 The Wall Cut (Host Behavior — Distinct From the Symbol)

The **cut** is a host behavior driven by the opening's width/height/sill/position, **separate from the drawn symbol**, and occurs in every view *even for a Blank Opening with no symbol*:

- **Plan:** jambs break the wall lines (a gap in the wall poché).
- **Elevation/section:** the wall's poché/fill is voided across the opening width, sill→head.
- **3D:** a rectangular hole is cut through the wall mesh (existing capability, §6.5).

**Clamping:** *along-wall* position (`offset_along`) is clamped to keep the opening fully within the wall segment. *Cross-wall* offset is **never** clamped (proud is intentional, §7.5).

### 7.8 Representations — Authored, Feature-Owned, Parametric-by-Scale

Representations are **independent authored artifacts** — **not** projections of one another or of the 3D model (a door is drawn **open** in plan but **closed** in 3D). They belong to the **Feature definition** and are drawn using the existing **2D-geometry system** (the geo2d line/arc/rect tooling) — this is precisely what the Phase-C Editor authors. For Phase A the seed Features **generate** these procedurally; the architecture treats them as Feature-owned artifacts either way. They **scale to the instance's primary dimensions** (a scale transform of the authored artifact — width/height stretch); richer parametrics are future.

**7.8.1 Plan schematic**
- **Door:** jambs + a **leaf line at the 90°-open position** + a **90° swing arc**; the **hinge side** (`mirror_hinge`) sets the pivot jamb, the **facing** (`mirror_facing`) sets which side of the wall it swings to. **Double-leaf** = two mirrored leaves + two arcs meeting at centre.
- **Window:** jambs + **3 parallel lines** (frame / glass / frame) across the opening.
- **Blank Opening:** jambs only (gap), no symbol.
- Weights/colours via the Display Manager (an "Openings"/"Features" category) — not hardcoded.

**7.8.2 Elevation / section schematic** (the currently-missing representation)
- The opening **voids the wall poché** across its width, **sill→head**, and the Feature's elevation schematic is drawn into the void:
  - **Door:** frame rectangle sill(0)→head; optional centre line for a double-leaf; no swing in elevation.
  - **Window:** frame rectangle sill→head + a **sill line** (+ optional mullion, parametric later) — where sill height reads visually.
  - **Blank:** void rectangle only.
- One schematic serves both a **cardinal elevation view** and a **section cut through the wall** (no separate section symbol for MVP).
- **Section plane passing *through* the opening:** wall poché interrupted over the opening width; head/sill show as horizontal lines (the hole reads in section). No door leaf in section. (Projection mechanism owned by `view-relationships.md`; this section defines only what an opening contributes.)

**7.8.3 3D representation**
- The wall **hole-cut** (host behavior, §6.5) **+** a **simple procedural closed** geometry: doors → frame box + closed leaf slab (on the facing side, respecting the facing mirror); windows → frame + semi-transparent glass pane; Blank → void only. All parametric-by-scale; no hardware/reveals/mullions.
- **Fallback (if Phase A runs hot):** void-only, closed-leaf 3D deferred to a follow-up.

### 7.9 Level Binding

The opening's Level defaults to the **host wall's base level** but is **user-assignable** at MVP (panel level dropdown). Sill/head are measured from the **assigned** level (`head = sill + height`; door sill = 0, window sill > 0). **Invariant / warning:** the resulting world-Z `[sill, head]` must fall within the host wall's `[base_z, top_z]`; a violation raises a **non-blocking warning** (panel), never an auto-resize.

### 7.10 Edge Cases

| Situation | Ruling |
|-----------|--------|
| Place with no valid host wall | **Reject** (no-op + status). |
| Along-wall position past a wall end | **Clamp** `offset_along` within the segment. |
| Wall shorter than opening width | **Reject placement**; an existing opening on a shrunk wall stays clamped + **validity warning** (never auto-delete). |
| Wall shortened / moved / rotated | Opening **follows** + re-clamps (§7.12). |
| Cross-wall offset past a wall face | **Allowed** (proud), not clamped. |
| Overlapping openings on one wall | **Permissive** — allowed, no hard block in MVP (soft-validation = future). |
| Sill/head outside wall vertical extent | **Warn** (§7.9), non-blocking; no auto-resize. |
| Host wall deleted | Opening **deleted** with it. |

### 7.11 Persistence & Undo

- **Instances** serialize **within their host wall's `openings` array** (keeps the wall↔opening lifecycle atomic). Instance shape = §7.4 fields. Legacy openings (`kind` / `width_mm` / `height_mm` / `sill_mm` / `offset_along` / `level`) **migrate** on load: `kind`→`type` + `feature_id` (nearest seed Feature); missing fields default (`cross_offset_mm`=0, `alignment`=Centered, mirrors=`False`).
- **Definitions** = code registry in Phase A (not persisted); Phase B adds the project loaded-set.
- **Undo (already covered — corrected 2026-08-23 after code grounding):** the snapshot-based undo (`Model_Space.push_undo_state()` → `_capture_network()` / `_restore_network()`; a list-based `_undo_stack`, **not** Qt `QUndoStack`) **already captures *and* restores walls *and* their nested openings** (via `wall.to_dict()["openings"]` / `WallOpening.from_dict`; `_restore_network` rebuilds walls+openings at the walls loop). So opening **place/delete already undoes** whenever the mutating handler calls `push_undo_state()` (as `_press_door` does today). The only real work: **every** opening mutation path — placement, orientation-cycle, and panel `set_property` — must call `push_undo_state()` (some current `set_property` impls don't snapshot). **No new undo architecture is needed** — the earlier "arch-not-in-undo" concern was a mis-read, disproven by direct inspection of `_restore_network`.
- **Dual-serialization discipline:** any new persisted field lands in **both** the file path and whatever undo path is chosen, in the same commit; "survives save/load **and** undo/redo" is an explicit acceptance test.

### 7.12 Reposition Contract (unchanged from as-built)

Any wall geometry change repositions all owned openings: `WallSegment._rebuild_path()` calls `_reposition()` on every opening (grip drag, translate, thickness/endpoint edits). Along-wall offset is re-clamped on every reposition.

### 7.13 Feature Browser, Manager & Model Browser

- **Feature Browser (Phase A):** a new tree tab showing Features **loaded in the current project**, organized **Feature > Category > Type**; activating a leaf enters the placement mode (§7.6). Read-only in Phase A (seeded set).
- **Manager (Phase B):** an Architecture-ribbon **dialog** to choose which Features (from the global library) are **loaded into this project**; template projects prepopulate a default set (Revit "Load Family").
- **Model/Project browser:** *placed instances* grouped **by Type** (Doors, Windows, …) — matches current behavior.

### 7.14 Seed Data (Phase A)

Three door Features for test/troubleshooting: **813 mm (32″)** and **914 mm (36″)** single man doors, and an **1829 mm (72″) double-leaf** door — one procedural "Door" definition instantiated at three widths (parametric-by-scale).

### 7.15 Acceptance Criteria (Phase A)

1. Place Door/Window/Blank on a wall via placement mode (ribbon quick-button **and** Feature Browser); empty-space rejected.
2. Spacebar alignment; ←→ hinge; ↑↓ facing; live preview during placement; same keys + panel edit a selected opening (undoable); keys gated while a HUD field is focused.
3. Cross-wall offset continuous, proud allowed, **sign-flips on facing mirror**; along-wall clamped.
4. All three views: **plan** (open door + arc reflecting hinge/facing, window glazing, blank gap; wall cut), **elevation/section** (void + frame/sill), **3D** (hole + closed leaf/frame/pane).
5. 3 seed doors selectable, parametric-scaled.
6. Level default-from-wall-base but assignable; sill/head from level; fit warning.
7. Feature Browser (Feature>Category>Type) + "Openings" contextual tab + property panel.
8. Survives save/load **and** undo/redo.

### 7.16 Feature System — Forward-Looking Architecture (graduates to its own spec)

The Opening proves a general **Feature framework** that will grow beyond walls. Captured here so openings don't design into a corner; **it graduates to its own governing spec** when Phase B/C build it (filed in `SPEC-INDEX.md` orphans).

- **Host strategies:** `host_type` ∈ Wall (openings) | Floor (e.g. a table, riser base) | Ceiling (pendent sprinkler, diffuser) | Face | Level/free (unhosted). The wall-hosting placement model (§7.5–7.7) is one strategy.
- **Editor v1 (Phase C) is deliberately constrained** to the **void+symbol paradigm**: define size parameters, draw the plan & elevation schematics (reusing the 2D-geometry tools), define the wall-cut and `host_type`. **Free-form 3D solid authoring is deferred** to Editor v2, gated behind the future 3D solid-modeling ("operations") system.
- **Future feasibility (own session):** folding Sprinkler Systems (Pipe/Fitting/Sprinkler/Valve/Pump) into the Feature framework — needs a brainstorm/feasibility review, and must first reconcile the terminology tension (there "Feature" reads as a *discipline/system* grouping, a looser sense than "Feature = a concrete placeable definition" here).

### 7.17 Superseded As-Built Model (reference)

The pre-redesign code (`wall_opening.py`) modeled openings as **wall-owned cutouts**: `WallOpening(QGraphicsPathItem)` with `DoorOpening` / `WindowOpening`, positioned by absolute `offset_along` only (no cross-wall offset, no alignment, no mirrors), centered on the wall centerline, serialized by `kind` within the wall, plan door-swing-arc / window-crossing-diagonals symbols, 3D hole-cut, **no elevation projection**, level inherited from the wall, and a placeholder "opening" contextual tab. This model is **superseded** by §7.1–7.16; §7.11 defines its migration.

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
| `_hazard_class` | `str` | `"Light Hazard"` | One of 8 NFPA 13 classes (§9.2) |
| `_occupancy` | `str` | `""` | Free-text occupancy description (§9.7) |
| `_system_type` | `str` | `"Wet"` | `"Wet"` \| `"Dry"` (§9.7) |
| `_design_point` | `tuple[float, float] \| None` | `None` | Selected NFPA design point `(area_sqft, density)`; `None` → curve minimum (§9.7) |
| `_compartment_type` | `str` | `"Room"` | One of 6 types |
| `_ceiling_type` | `str` | `"Noncombustible unobstructed"` | One of 8 NFPA 13 types |
| `_ceiling_level` | `str` | — | Level reference for ceiling elevation |
| `_ceiling_offset` | `float` | `DEFAULT_CEILING_OFFSET_MM` | mm offset from ceiling level |
| `_color` | `QColor` | category default | Fill/stroke color |
| `_label_offset` | `QPointF` | (0, 0) | Drag offset for label positioning |
| `_show_label` | `bool` | `True` | Label visibility toggle |

### 9.2 Hazard Classes

Eight NFPA 13 hazard classifications (`constants.HAZARD_CLASSES`) with associated maximum coverage per sprinkler (`constants.NFPA_MAX_COVERAGE_SQFT`):

| Hazard Class | Max Coverage (sq ft) |
|-------------|---------------------|
| Light Hazard | 225 |
| Ordinary Hazard Group 1 | 130 |
| Ordinary Hazard Group 2 | 130 |
| Extra Hazard Group 1 | 100 |
| Extra Hazard Group 2 | 100 |
| Low-Piled Storage | 130 (OH-type criteria per NFPA 13 low-piled provisions) |
| Miscellaneous Storage | 100 |
| High Piled Storage | 100 |

The three storage classes (`nfpa_curves.STORAGE_HAZARDS`) have **no density/area curve** — their design criteria come from the NFPA 13 storage chapters (a planned follow-up). They disengage design-area criteria inheritance ([sprinkler-system-components.md §11.8](sprinkler-system-components.md)).

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

### 9.7 Protection Criteria & Design Point (as-built 2026-07-14)

The panel's "Protection Criteria" section (rendered via `header`-type rows — `property-panel.md §3.2`) carries the room-side inputs to design-area criteria inheritance. **The inheritance/resolution rules are owned by [sprinkler-system-components.md §11.8](sprinkler-system-components.md)** — this section only defines the room-side storage:

- **Occupancy** (`_occupancy`) — free text; surfaces on the design-criteria badge.
- **System Type** (`_system_type`) — Wet | Dry.
- **Design Point** (`_design_point`) — a `(area_sqft, density)` point on the hazard's NFPA density/area curve, picked via the Design Point **button** which opens `DesignPointDialog` (a modal wrapper around the auto-populate dialog's `DensityAreaGraph`). `Room.design_point()` returns the stored point, defaulting to the hazard curve's **minimum-area point** (`nfpa_curves.min_design_point`); it returns `None` for storage hazards (no curve — the button face reads "N/A" and the picker refuses to open).
- **Hazard change resets the design point:** `set_property("Hazard Class", …)` sets `_design_point = None` when the class actually changes — the point lives on a specific curve, so switching curves invalidates it.

**Fill Color panel row removed (2026-07-14):** room appearance is owned by the Display Manager cascade; `set_property("Fill Color")` remains for backward compatibility but no row renders.

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

> **Rewritten as-built 2026-08-28** (two-boundary elevation model; owning `.level`-for-geometry retired; unified placement dispatch). See the 2026-08-28 impl note at the top of this spec.

### 11.1 Two-Boundary Elevation Model

A slab's vertical extent is defined by **two independently-specified boundaries** — a **top** and a **bottom** — each choosing a *reference mode*. This replaces the superseded *single datum + downward thickness* model (a slab can now span a story, sit on a surveyed datum, or reference different levels top vs. bottom). The owning `.level` concept is **retired for geometry** (§11.3).

**Data fields** (flat per-attribute, on `FloorSlab`):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `_points` | `list[QPointF]` | from placement | Closed boundary polygon |
| `_top_mode` | `str` | `"level"` | Top reference: `"level"` \| `"absolute"` |
| `_top_level` | `str` | `DEFAULT_LEVEL` | Level name for `"level"` top |
| `_top_offset_mm` | `float` | 0 | Signed offset added to the top level elevation |
| `_top_abs_z_mm` | `float` | 0 | World-mm Z for `"absolute"` top |
| `_bottom_mode` | `str` | `"thickness"` | Bottom reference: `"level"` \| `"absolute"` \| `"thickness"` |
| `_bottom_level` | `str` | `DEFAULT_LEVEL` | Level name for `"level"` bottom |
| `_bottom_offset_mm` | `float` | 0 | Signed offset added to the bottom level elevation |
| `_bottom_abs_z_mm` | `float` | 0 | World-mm Z for `"absolute"` bottom |
| `_thickness_mm` | `float` | 152.4 (6") | Input **only** in `"thickness"` bottom mode; else a derived readout |
| `_visibility_by_zrange` | `bool` | `True` | Marks the item for pure-z-range visibility (§11.3) |
| `_color` | `QColor` | category default | Construction default; **not** panel-edited (Display Manager owns appearance) |
| `_is_occluding` | `bool` | `False` | Set by `LevelManager` |
| `_is_section_cut` | `bool` | `False` | Set by `LevelManager` |

The mode enum tuples are also mirrored in `constants.py` (`FLOOR_TOP_MODES`, `FLOOR_BOTTOM_MODES`). Retired fields: `_level_offset_mm` and the owning `.level` (a vestigial `.level` attr may survive from the `DisplayableItemMixin` default but is **never serialized and never drives geometry**).

### 11.2 Z-Range Resolution (pure resolver)

Boundary→Z resolution is a **module-level pure function** with no Qt dependency (unit-testable at ground truth):

```
_resolve_boundary_z(mode, level, offset_mm, abs_z_mm, level_manager) -> float | None
  "absolute" → abs_z_mm
  else       → level_manager.get(level).elevation + offset_mm
               (None if level_manager is None or the level is missing)
```

`z_range_mm()` returns an **ordered** `(bot, top)` tuple, or `None` when unresolvable:

```
top = _resolve_boundary_z(top…)                          (None → None)
bot = top - _thickness_mm       if _bottom_mode == "thickness"
      else _resolve_boundary_z(bottom…)                  (None → None)
return (min(bot, top), max(bot, top))                    # always ordered
```

Implemented as `_z_range_with_lm(lm)` (takes an explicit `LevelManager`) with `z_range_mm()` a thin caller resolving the manager via the live scene (`scene._level_manager`, or a `_scene` test hook). `effective_thickness_mm()` = `top − bot` (or `None`). The **elevation/section projection** resolves floor Z through `_z_range_with_lm(self._lm)` (see §11.10) — correcting the prior model where `.level` *did* drive elevation geometry.

### 11.3 Visibility — Pure Z-Range (owning `.level` retired)

Floors carry `_visibility_by_zrange = True`. `LevelManager._set_level_vis` routes any flagged item through **pure z-range** — it ignores `.level` entirely: within a view range the item is shown and `_apply_z_filter` sets `_is_section_cut`; with no view range it is simply shown. There is no `.level == active` fast-path and no `isinstance` coupling in `level_manager`. The default `Level.view_bottom = -1000 mm` margin (owned by `view-relationships.md §7.1`) keeps default slabs and cross-level spans visible.

**Rename remap:** `LevelManager.rename_level(old, new, items, scene=…)` skips floors in the generic `.level` loop (guarded by `_visibility_by_zrange`) and instead remaps each slab's `_top_level` / `_bottom_level` (when `== old`) via a separate pass over `scene._floor_slabs`. `LevelWidget` now passes `scene=` so the remap runs. `PlanViewManager.rename_level` is unrelated (renames plan-view keys).

**Model Browser:** floors sit under a flat "Floors (N)" node; the tooltip dropped the `Level:` line (now just `Points: N`) since a floor has no owning level.

### 11.4 Placement Workflow (unified dispatch — mirrors the wall)

Floor placement is a first-class client of the unified 2D-geometry placement dispatch (shared machinery: `2d-geometry.md §4`; the wall precedent it mirrors: §4.4). The old separate `floor` (click-vertex polygon) / `floor_rect` (2-click box, dropdown-selected, **not** HUD-wired) modes are **retired**.

**Single `"floor"` scene-mode** carries `_floor_primitive ∈ {"rect", "polygon"}` and `_floor_rect_from_center: bool`. `set_mode("floor_rect")` is a backward-compat alias that folds to `floor + rect primitive` (corner).

**F shortcut** — scene-focus-gated in `Model_View._TOOL_SHORTCUTS` (bare key). It **displaced** the old bare-`F` Fit-to-Screen binding (Fit is now reached via the View-tab "Fit to Screen" button).

**←/→ cycles the primitive** at step 0 (session-sticky, via `cycle_placement_variant` + `_PLACEMENT_VARIANTS["floor"]`):

| Slot | Variant | First-step instruction |
|------|---------|------------------------|
| 0 | Floor (Corner Rectangle) | Pick first corner |
| 1 | Floor (Center Rectangle) | Pick centre point |
| 2 | Floor (Polygon) | Pick first boundary point |

**Rect (Corner/Center) — 3-step:** anchor → sizing → **rotate**, mirroring the wall rect. `rect_sizing_points()` computes the axis-aligned `pt1/pt2` from anchor + corner + `from_center`; `rotated_rect_corners()` produces the 4 rotated scene corners committed as **one** `FloorSlab` (a floor is a single closed polygon, unlike the wall rect's 4 segments). Ctrl snaps to 45° about the pivot (= the anchor). Rotate-step guides (`_floor_rect_ref_line0/A`) + a spinning dashed preview show the orientation.

**Polygon:** click-vertex boundary; **click near the first vertex (≥3 verts) / Enter / double-click** closes; **Delete** pops the last vertex (routed through `Model_View` for both the polygon and the tool-shortcut path; discards the in-progress slab at one vertex). `close_polygon()` finalizes; minimum 3 points. Vertex insert/remove after placement via `insert_point()` / `remove_point()` (keeps ≥ 3). The old click-near-a-vertex-to-delete-mid-placement gesture was removed (Delete replaces it).

**Continuous** placement (each commit re-arms; Esc exits to select). The **passive HUD** shows geometry only (rect W/H then rotate Angle; polygon per-segment Length/Angle). Polygon move republishes placement state every frame (`publish_placement_state(last_pt, snapped)`) so the `line`-schema HUD seeds a live per-segment readout (without it `get_resolved_point()` stays `None` and the readout freezes at 0 mm/0°). Spacebar/↑/↓ are inert.

**Dispatch surfaces** (all mirror the wall): `_press_floor_router` / `_move_floor_router` dispatch on `_floor_primitive`; `_apply_floor_dynamic_input` handles typed placement (rect sizing→rotate→commit; polygon routes the point through the vertex handler); `_floor_schema_for_primitive` (rect sizing → `rectangle`, rect rotate → `rotation`, polygon → `line`); `_PLACEMENT_VARIANTS["floor"]`; and a **`floor` branch in `_transform_seed_values`** (the rotate-step live angle seed — the `project_transform_seed_hud_per_mode` precedent).

**Naming:** a placed floor takes the floor template's user-authored name (the placeholder `"(Template)"` and blank both fall back to `"Floor"`), **uniquified** against existing floor names — a "Slab" collision yields `Slab 1`, `Slab 2`, … (suffix starts at 1). Named *before* the slab is appended to `_floor_slabs` so it does not collide with itself.

**Template application:** `_apply_floor_template_fields` copies the full two-boundary model (top/bottom mode/level/offset/abs-z + thickness) from the template onto a placed slab — closing the parity gap the old thickness-only copy left. The owning `.level` is deliberately **not** copied (retired; would silently revert on reload/undo).

### 11.5 Degenerate-Safety (allow + warn)

Inverted/zero-height configurations are **allowed** (never blocked at input), then warned and degraded:

- **Anti-degeneracy constant** `MIN_FLOOR_THICKNESS_MM` = 1.0 mm (in `constants.py`) — a degeneracy floor, **not** an architectural minimum.
- **Thickness-mode input** rejects values below `MIN_FLOOR_THICKNESS_MM` (the panel's `Thickness` dimension row carries `minimum`; `set_property` clamps with `max(v, MIN_FLOOR_THICKNESS_MM)`).
- **Level/Absolute inversion** (resolved `bot ≥ top`): allowed. `get_3d_mesh` returns `None` when `top − bot < MIN_FLOOR_THICKNESS_MM` (no inverted winding); `z_range_mm` still returns the ordered tuple so visibility/section stay defined; `get_properties` emits a `warning` row (§11.7).

### 11.6 Occlusion Masking

**Trigger:** `LevelManager` sets `_is_occluding = True` when the slab's top surface falls within the plan view Z-range (`view_depth < slab_top <= view_height`), using the resolved `z_range_mm()[1]`.

**Mechanism:** `paint()` draws an opaque background-colored polygon *before* the semi-transparent fill, masking lower-floor content. Qt paints in ascending Z-order, so floor slabs (Z = -80) paint their opaque mask before walls (Z = -50). Same-level walls paint over the mask; lower-level walls (hidden by the level manager) never appear.

### 11.7 Property Panel (mode-conditional)

`get_properties()` returns **mode-conditional rows**; the panel re-queries after every edit (`property-panel.md §3.3`), so returning a different key set drives dynamic show/hide with no extra machinery:

```
Type · Name
── Top ──
  Top Reference : enum {Level, Absolute}
  (level)  Top Level : level_ref ; Top Offset : dimension
  (abs)    Top Z     : dimension
  Top Elevation : label (read-only, always)
── Bottom ──
  Bottom Reference : enum {Level, Absolute, Thickness}
  (level)     Bottom Level : level_ref ; Bottom Offset : dimension
  (abs)       Bottom Z     : dimension
  (thickness) Thickness    : dimension (minimum = MIN_FLOOR_THICKNESS_MM)
  Thickness (derived) : label   [shown when bottom ≠ thickness]
  Bottom Elevation : label (read-only, always)
  Points : label
  ⚠ "Floor is inverted" warning   [when resolved bot ≥ top and bottom ≠ thickness]
```

**No `Colour` row** — appearance is owned by the Display Manager "Floor" category and the reusable Graphic Override group (`ribbon-bar.md`). Because two-boundary floors expose their own `Top/Bottom Reference` rows, they **opt out** of the panel's legacy synthesized Level combo (`property_manager.py` suppresses it when `"Top Reference"`/`"Bottom Reference"` is present — a legacy combo there would resurrect the retired `.level` coupling and lie). `set_property` maps each enum/dimension key to its field (out-of-options enum labels no-op defensively; dimensions parse via `ScaleManager`).

### 11.8 Rendering

1. **Occlusion mask** (if `_is_occluding`): Opaque polygon in scene background color.
2. **Fill**: Semi-transparent polygon (alpha 50) in display fill color (opaque when `_paper_fill_opaque`).
3. **Outline**: 1 px cosmetic pen in display line color.
4. **Section hatch** (if `_is_section_cut`): Diagonal overlay via `draw_section_hatch()` with the slab polygon as clip path; appearance from the display cascade. `LevelManager` sets `_is_section_cut = True` when the cut plane straddles the slab's Z-range (`z_bot < view_height < z_top`).
5. **Selection**: Red outline.

### 11.9 3D Mesh

`get_3d_mesh(level_manager=None)`:
1. Resolve the vertical extent via the shared pure resolver — `_z_range_with_lm(level_manager)` when a manager is passed (the 3D pipeline supplies one), else `z_range_mm()`. Returns `None` if unresolvable **or** if `top − bot < MIN_FLOOR_THICKNESS_MM` (§11.5).
2. Triangulate the polygon (ear-clipping, `triangulate_polygon()`); convert scene coords to mm via `scale_manager`.
3. Build twin vertex rings at `top_z` and `bot_z`; top face = triangulation, bottom face = reversed winding, side faces = quad strips per edge.

### 11.10 Grip Points & Cross-References

Every polygon vertex is a grip point; `apply_grip(index, new_pos)` moves the indexed vertex and rebuilds the path. `translate(dx, dy)` shifts all vertices (so `move_items` works on floors).

**Elevation / section projection** (`elevation_scene._project_floor_slabs`) resolves each slab's world-Z via `slab._z_range_with_lm(self._lm)` — using the elevation scene's **own** `LevelManager` explicitly (the slab lives in the model scene, so `slab.z_range_mm()` is not guaranteed to reach the right manager). Unresolvable slabs are skipped (degenerate-safe).

**Plan view-range upper bound** derivation (a thick floor above no longer bleeds into the current plan) is owned by `view-relationships.md §7.1` — link, don't restate.

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
    "level": "Level 1"
}
```

Openings are serialized within their parent wall's `openings` array. The wall reference is restored by the caller during deserialization.

> **Redesign (§7.11, PROPOSAL):** the instance shape gains `feature_id`, `type`, `cross_offset_mm`, `alignment`, `mirror_hinge`, `mirror_facing`; the legacy shape above (`kind` + width/height/sill/offset_along/level) becomes the **migration source** (`kind`→`type`+`feature_id`; missing fields default). New fields must land on **both** serialization paths (file + undo — see §7.11 undo tension).

### 12.3 Room

```json
{
    "type": "room",
    "boundary": [[x1, y1], [x2, y2], ...],
    "color": "#4488cc",
    "name": "Room 1",
    "tag": "",
    "show_label": true,
    "level": "Level 1",
    "ceiling_level": "Level 2",
    "ceiling_offset": -50.8,
    "hazard_class": "Light Hazard",
    "occupancy": "",
    "system_type": "Wet",
    "design_point": [1500.0, 0.1],
    "compartment_type": "Room",
    "ceiling_type": "Noncombustible unobstructed",
    "label_offset": [0, 0]
}
```

`design_point` serializes as `null` when unset (load restores `None` → curve-minimum default, §9.7). Missing `occupancy`/`system_type`/`design_point` on old saves default to `""`/`"Wet"`/`null`. (The legacy `user_layer` field is gone — the per-item layer system was removed.)

### 12.4 FloorSlab (two-boundary schema, 2026-08-28)

```json
{
    "type": "floor_slab",
    "points": [[x1, y1], [x2, y2], ...],
    "color": "#8888cc",
    "name": "Slab 1",
    "top_mode": "level",
    "top_level": "Level 1",
    "top_offset_mm": 0.0,
    "top_abs_z_mm": 0.0,
    "bottom_mode": "thickness",
    "bottom_level": "Level 1",
    "bottom_offset_mm": 0.0,
    "bottom_abs_z_mm": 0.0,
    "thickness_mm": 152.4,
    "display_overrides": { }
}
```

`to_dict()` is the **single serializer for both persistence paths** — `scene_io` (file save) and `_capture_network`/`_restore_network` (undo) both delegate to it (memory: dual serialization paths). `display_overrides` (per-instance Display-Manager stroke/fill overrides) is **emitted only when non-empty** (matches `GridlineItem`); `from_dict` defaults it to `{}`.

**Migration (lossless, both paths):** a legacy record (no `top_mode` key) `{level, level_offset_mm, thickness_mm}` loads to `top_mode="level"`, `top_level=level`, `top_offset_mm=level_offset_mm`, `bottom_mode="thickness"`, `thickness_mm` — reproducing the same `(bot_z, top_z)`/mesh as before. Legacy `thickness_ft` → `thickness_mm` (× 304.8) still handled. **The new schema is written on re-save; legacy keys (`level`, `level_offset_mm`) are dropped** (the load path keeps reading them).

## 13. Divergences from Current Implementation

All rows in this ledger are **resolved** as-built (re-verified 2026-07-14):

| Area | Resolution |
|------|-----------|
| Alignment naming | `Left` / `Right` in use; legacy `Interior` / `Exterior` migrated on deserialize |
| Join modes | Miter removed from the enum; serialized `"Miter"` maps to **`"Solid"`** on load (spec originally said Butt — Solid preserves corner geometry) |
| Min thickness | Clamped to 1 mm on set (`set_property`) and on deserialize |
| Opening reposition | `WallSegment._rebuild_path()` repositions owned openings |
| Offset clamping | `WallOpening._reposition()` clamps `_offset_along` to `[0, centerline_length]` |
| Dead code (room.py unreachable returns) | Removed |
| `MITER_TOL` | Named constant in `constants.py` (with `MAX_MITER_FACTOR`, `AUTO_JOIN_TOLERANCE`, `TEE_TOLERANCE`), imported by `wall.py` |

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
