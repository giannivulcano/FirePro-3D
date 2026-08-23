---
status: current          # §4–§6/§8–§13 code-verified as-built; §7 = redesign PROPOSAL (not built, 2026-08-23); divergences ledger in §13
last-verified: 2026-07-14
verified-commit: 5ba9227
applies-to:
  - firepro3d/wall.py
  - firepro3d/room.py
  - firepro3d/floor_slab.py
  - firepro3d/wall_opening.py
  - firepro3d/roof.py
---

# Wall, Room & Floor Slab System — Design Spec

**Date:** 2026-04-27
**Complexity:** Large
**Status:** Current
**Source tasks:** TODO.md — "Spec & grill session: wall, room & floor slab system"
**Impl note (2026-07-13):** §5 joinery rewritten as-built after the three-wall-junction fix — 3-wall junctions now get a **full-miter pie join** (`_pie_miter_corners`), tee joins snap to the host **centerline** and cope to its near face (`nearest_centerline_point`, `_tee_cope_corners`). Verified against commit `25e1dea`; tests `tests/test_wall_room_floor.py` (`TestThreeWallJunctionMiter`, `TestTeeJoin`).
**Impl note (2026-07-14):** §9 gains Room Protection Criteria (occupancy, system type, design point — §9.7) and the 8th hazard class (Low-Piled Storage); §12.3 serialization gains the three criteria fields. Verified against commit `5ba9227`; tests `tests/test_room_criteria.py`.
**Design note (2026-08-23):** §7 rewritten as a **first-principles redesign PROPOSAL** — the Opening becomes a **first-class, Feature-based** element (Feature > Category > Type; cross-wall placement + orientation mirrors; plan/elevation/3D representations; wall cut; §7.1–7.17). **Not yet built** (see §7.1 phasing). Introduces the forward-looking **Feature system** (§7.16), which graduates to its own governing spec at Phase B. Source: TODO.md "Opening element…" (2026-08-23 grill). §4–§6, §8–§13 unchanged as-built.

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
| 3 | Far face midpoint | Drag perpendicular to wall to adjust thickness (min 25.4 mm / 1 inch). For Center alignment the grip sits on the positive-normal face; for Right alignment, the negative-normal face. |

`apply_grip()` updates endpoints (indices 0–2) or thickness (index 3), calls `_rebuild_path()`, which repositions all owned openings (§7.3). The width grip projects the drag position onto the wall normal and converts back to mm via the current scene-to-mm ratio.

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

> **Status: PROPOSAL / not-yet-built** (2026-08-23 first-principles grill; supersedes the as-built wall-owned-cutout model, retained for reference in §7.17). This section specifies the redesigned **Opening** as the first concrete instance of a new **Feature** framework. **Phase A** (this task's deliverable) builds the Opening element + the minimal Feature data model + Feature Browser; **Phase B** (Manager) and **Phase C** (Editor) are specced forward-looking in §7.16 and filed as follow-up tasks. The rest of this spec (§4–§6, §8–§13) remains as-built/current.

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
- **XZ plane (wall plane)** — vertical, along the wall through its centerline. Default position = centerline. The opening may be **offset** across the wall (`cross_offset_mm`) and **mirrored** about this plane (`mirror_facing`).
- **YZ plane** — vertical, perpendicular to the wall through the opening centre. Aligns to nothing; used only to **mirror** the opening along the wall (`mirror_hinge` — the hand/hinge side).

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
- **Undo (tension to resolve in Phase 3/4):** architectural elements are currently **file-save only — not in the undo network** (`_capture_network` / `_restore_network` skip walls/openings). Opening **place / edit / delete / orientation-cycle must be undoable**, so the plan must bring opening ops into an undo mechanism (extend the arch capture, or dedicated `QUndoCommand`s).
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

### 12.4 FloorSlab

```json
{
    "type": "floor_slab",
    "points": [[x1, y1], [x2, y2], ...],
    "thickness_mm": 152.4,
    "level_offset_mm": 0.0,
    "color": "#8888cc",
    "name": "Slab 1",
    "level": "Level 1"
}
```

**Backward compatibility:** `thickness_ft` → `thickness_mm` (× 304.8).

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
