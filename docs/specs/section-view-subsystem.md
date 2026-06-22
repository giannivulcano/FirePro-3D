# Section View Subsystem — Design Spec

**Date:** 2026-04-29
**Complexity:** Large
**Status:** Approved
**Source tasks:** TODO.md — "Spec session: Section view subsystem — first-class arbitrary-cut-line section views [ref:view-relationships§4.1]"

---

## 1. Goal

Replace the existing cardinal-only elevation view system with a unified section view subsystem that supports arbitrary-angle cut planes, enabling fire protection engineers to create section views at any angle for pipe routing verification, sprinkler clearance checks, and AHJ submission documentation.

## 2. Motivation

The current elevation system is limited to N/S/E/W cardinal directions, doesn't persist markers across sessions (known gap in view-relationships §6.3), and can't show angled cuts through the building. Fire protection work requires section views at arbitrary angles to verify pipe penetrations through walls/floors, deflector-to-ceiling clearance, and routing compliance. This spec unifies the elevation and section view concepts into a single system, fixing the persistence gap as a side effect.

## 3. Architecture & Constraints

### 3.1 Single unified view type

Section views generalize elevation views. A cardinal elevation is a section at a fixed angle (0°/90°/180°/270°). One codebase handles both, eliminating the parallel `ElevationScene`/`ElevationView`/`ElevationManager` system.

### 3.2 Per-instance materialization

Section views materialize their own `QGraphicsScene` from the data model (same pattern as the existing elevation system). They do not share `ModelSpace`'s scene. Each section scene is rebuilt independently when the model changes.

### 3.3 Data flow

```
Plan view (ModelSpace)
  ↓ entities with 2D position + Z
SectionScene
  ↓ _world_to_section() projection
  ↓ depth classification (cut / behind / hidden)
  ↓ entity-specific rendering (hatch / lighter)
SectionView (QGraphicsView)
  ↓ pan/zoom/fit, selection
  ↓ _ROLE_SOURCE sync-back
Property panel ← selected source entity
```

### 3.4 Constraints

- No new signals on `ModelSpace` beyond the existing `openViewRequested`
- Projection math must produce identical results to `ElevationScene._world_to_elev()` for cardinal angles (regression safety)
- All entities exposing `z_range_mm()` must be projectable
- `_STATE_VERSION` must be bumped to 6 (the OSNAP toolbar bumped it 4→5 on 2026-06-22, so current is 5)

## 4. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Primary use case | Full capability (routing + clearance + structure) | Fire protection needs all three for AHJ submissions |
| Cut definition | Two-click line A→B with flip arrow | Matches Revit, intuitive for CAD users |
| View depth | Adjustable near/far clip, default 5000mm | Drag handles in plan + property field |
| Lateral extent | Bounded by A→B + padding | Keeps views focused, user controls width via grips |
| Elevation relationship | Section subsumes elevation | One system, fixes persistence gap, less code |
| Vertical extent | All levels by default | Full building sections for submissions, optional crop |
| Cut vs projected | Hatched bold cut + lighter thinner behind | Industry standard for construction docs |
| Marker visual | Line + arrows + bubbles + dashed extents | Standard AEC section marker |
| Jogged sections | Not in v1 | Follow-up — complex projection stitching |
| Break lines | Not in v1 | Follow-up — coordinate discontinuity complexity |
| Migration | Section tool + N/S/E/W shortcuts | New capability without losing quick cardinal access |
| Naming | Auto-increment numbers, cardinals get direction name | Consistent with detail view pattern |
| Editability | Select + property edit, no in-scene geometry | Cross-view sync via `_ROLE_SOURCE` |

## 5. Projection Math

### 5.1 Cut plane coordinate system

The cut plane is defined by:
- **Origin `O`**: midpoint of A→B segment (world mm)
- **Direction `D`**: unit vector along A→B, `D = normalize(B - A)`
- **Look normal `N`**: perpendicular to `D`, pointing toward the look side. Default `N = (-D.y, D.x)` (left-hand perpendicular). Flip reverses sign: `N *= -1`

### 5.2 Projection function

```python
def _world_to_section(self, wx: float, wy: float, wz: float) -> tuple[float, float]:
    """Project world (mm) coords onto section 2D plane.
    Returns (h, v) where h is along the cut line direction.
    """
    dx = wx - self._origin_x
    dy = wy - self._origin_y
    h = dx * self._dir_x + dy * self._dir_y    # dot with cut direction
    v = -wz                                      # Qt Y convention
    return h, v
```

### 5.3 Depth function

```python
def _compute_depth(self, wx: float, wy: float) -> float:
    """Signed distance from cut plane along look direction.
    depth ≈ 0  → at cut plane
    depth > 0  → behind (in view)
    depth < 0  → in front (not in view)
    """
    dx = wx - self._origin_x
    dy = wy - self._origin_y
    return dx * self._normal_x + dy * self._normal_y
```

### 5.4 Cardinal equivalence

The existing `_world_to_elev()` uses hardcoded sign flips per direction. The generalized projection must produce identical H values. D and N are derived from the default perpendicular rule `N = (-D.y, D.x)`:

| Direction | D | N | h = dot(pos-O, D) | Existing h | Match |
|---|---|---|---|---|---|
| North (look toward -Y) | (-1, 0) | (0, -1) | `-(wx - Ox)` | `-wx` | yes (Ox=0) |
| South (look toward +Y) | (1, 0) | (0, 1) | `wx - Ox` | `wx` | yes |
| East (look toward -X) | (0, 1) | (-1, 0) | `wy - Oy` | `wy` | yes |
| West (look toward +X) | (0, -1) | (1, 0) | `-(wy - Oy)` | `-wy` | yes |

For painter Z sorting, existing code uses "distance toward camera" (ascending sort, larger = closer = on top). The generalized equivalent is `sort_depth = dot(pos - O, -N)`, which inverts the look-direction depth. The `_assign_depth_z_values()` ascending sort then places farther items behind and closer items on top — matching existing behavior.

Unit tests verify cardinal equivalence by comparing projection output against the hardcoded `_world_to_elev()` values.

## 6. Cut Plane Filtering

### 6.1 Zone classification

Each entity is classified by its centroid depth:

| Zone | Depth range | Rendering | Flags |
|---|---|---|---|
| **Front** | `depth < -CUT_TOLERANCE` | Hidden | — |
| **Cut** | `abs(depth) ≤ CUT_TOLERANCE` | Bold outline + section hatch fill | `_is_section_cut = True` |
| **Behind** | `CUT_TOLERANCE < depth ≤ far_clip` | Lighter pen (0.5 opacity), thinner stroke | `_is_behind_cut = True` |
| **Beyond** | `depth > far_clip` | Hidden | — |

`CUT_TOLERANCE`: 150mm default (approximately half a standard wall thickness). Sufficient to capture walls whose centerline is near the cut plane.

### 6.2 Wall intersection override

For walls, centroid depth alone can misclassify walls that are parallel to but near the cut line. If the cut line segment (A→B, extended by padding) geometrically intersects the wall's 2D quad polygon, that wall is classified as "cut" regardless of centroid depth.

### 6.3 Lateral filtering

An entity is hidden if its projected H-coordinate bounding box falls entirely outside `[h_min - padding, h_max + padding]`, where `h_min`/`h_max` are the projections of A and B onto the H-axis (always 0 and `length(AB)`). Default padding: 500mm.

## 7. Entity Projection Rules

### 7.1 Walls

- **At cut**: Cross-section rectangle. Width = wall thickness measured perpendicular to cut line (project quad corners onto normal axis, `max - min`). Height = wall Z extent (`z_top - z_bottom`). Filled with section hatch via `draw_section_hatch()`.
- **Behind cut**: Projected rectangle (same as existing elevation rendering). Lighter pen, reduced opacity, no fill.

### 7.2 Pipes

- **At cut**: Filled circle at the intersection point. Radius derived from pipe nominal diameter. Bold pen.
- **Behind cut**: Projected line connecting node endpoints. Lighter pen, reduced opacity.

### 7.3 Floor slabs

- **At cut**: Horizontal rectangle spanning the slab's lateral extent, with thickness shown vertically. Section hatch fill.
- **Behind cut**: Lighter horizontal band, reduced opacity.

### 7.4 Sprinklers

- **At cut**: Circle glyph (same as elevation), bold pen, color by orientation (Pendent=red, Upright=blue, Sidewall=green).
- **Behind cut**: Same glyph, lighter pen, reduced opacity.

### 7.5 Roofs

- **At cut**: Cross-section from mesh intersection with cut plane. Hatched fill.
- **Behind cut**: Projected bounding rect (same as existing elevation), lighter pen.

### 7.6 Gridlines

Projected as vertical lines regardless of depth — reference geometry always visible. Use existing `ElevGridlineItem` pattern with grip-drag Z-extent overrides.

### 7.7 Level datums

Horizontal dash-dot reference lines at each level's elevation. Always visible regardless of depth. Rendered in `drawForeground()` (same as existing elevation pattern).

### 7.8 Nodes (without sprinklers)

Point entities. At cut: small circle, bold pen. Behind cut: lighter circle. Classified by single-point depth.

## 8. SectionScene Class

### 8.1 File: `firepro3d/section_scene.py`

New file, replaces `firepro3d/elevation_scene.py`.

### 8.2 Constructor

```python
class SectionScene(QGraphicsScene):
    entitySelected = pyqtSignal(object)

    def __init__(self, name, cut_a, cut_b, look_sign, far_clip,
                 model_space, level_manager, scale_manager):
```

**Computed on construction:**
- `_origin`: midpoint of A→B (world mm)
- `_dir_x, _dir_y`: unit vector along A→B
- `_normal_x, _normal_y`: perpendicular unit vector × `look_sign`
- `_h_extent`: `length(AB)` (lateral range is `[0, _h_extent]`)

### 8.3 Rebuild pipeline

```
rebuild()
  → _project_level_datums()
  → _project_walls()
  → _project_pipes()
  → _project_sprinklers()
  → _project_floor_slabs()
  → _project_roofs()
  → _project_gridlines()
  → _assign_depth_z_values()
```

Each `_project_*` method:
1. Iterates source entities from `model_space`
2. Projects world coords via `_world_to_section()`
3. Computes depth via `_compute_depth()`
4. Applies lateral filter (H within extent + padding)
5. Classifies zone (front/cut/behind/beyond)
6. Creates `QGraphicsItem` with appropriate pen/brush for zone
7. Sets `_ROLE_SOURCE` data role to source entity
8. Registers depth for sorting via `_register_depth_item()`

### 8.4 Depth sorting

Uses `sort_depth = dot(pos - O, -N)` (distance toward camera) for painter Z ordering. `_register_depth_item(sort_depth, *items)` collects all items, `_assign_depth_z_values()` sorts ascending and assigns incrementing painter Z-values. Items closer to camera get higher Z (drawn on top). Same algorithm as existing elevation.

### 8.5 Serialization

```python
def to_dict(self) -> dict:
    return {
        "name": self._name,
        "cut_a": {"x": self._cut_a[0], "y": self._cut_a[1]},
        "cut_b": {"x": self._cut_b[0], "y": self._cut_b[1]},
        "look_sign": self._look_sign,
        "far_clip": self._far_clip,
        "gridline_z_overrides": dict(self._gridline_z_overrides),
    }
```

### 8.6 Debounced rebuild

Timer-based rebuild (same as existing `ElevationScene._schedule_rebuild()`), triggered on model changes.

## 9. SectionView Class

### 9.1 File: `firepro3d/section_view.py`

New file, replaces `firepro3d/elevation_view.py`.

### 9.2 Functionality

- `QGraphicsView` displaying a `SectionScene`
- Pan (middle-mouse), zoom (scroll wheel), fit-to-view (F key)
- Rubberband-drag selection
- Grip handle rendering for gridline Z-extent overrides
- Cursor coordinate display: "H: ___ Z: ___" format
- Selection → `entitySelected` signal → property panel sync

## 10. SectionMarker Class

### 10.1 File: `firepro3d/section_marker.py`

### 10.2 Visual elements

- **Cut line**: solid cosmetic pen from A→B
- **Direction arrows**: small filled triangles perpendicular to cut line at each endpoint, pointing toward look side
- **Callout bubbles**: circles at A and B containing section number/letter. Radius matches `DetailMarker` bubble sizing
- **Far clip extent lines**: dashed lines parallel to cut line, offset by `far_clip` on look side, connected by short perpendicular dashes at A and B

### 10.3 Grip handles

| Grip | Action |
|---|---|
| A endpoint | Drag to move/rotate left side |
| B endpoint | Drag to move/rotate right side |
| Far clip midpoint | Drag perpendicular to adjust depth |
| Direction arrow click | Flip `look_sign` (`*= -1`) |
| Anywhere else | Drag to translate entire marker |

### 10.4 Interaction

- Double-click → `scene.openViewRequested.emit("section", self._name)`
- Right-click context menu: Open, Rename, Flip Direction, Delete
- `_exclude_from_bulk_select = True`

### 10.5 Serialization

```python
def to_dict(self) -> dict:
    return {
        "name": self._name,
        "cut_a": {"x": ..., "y": ...},   # world mm
        "cut_b": {"x": ..., "y": ...},
        "look_sign": self._look_sign,
        "far_clip": self._far_clip,
        "level_name": self._level_name,
    }

@classmethod
def from_dict(cls, data, scale_manager) -> "SectionMarker": ...
```

## 11. SectionManager Class

### 11.1 File: `firepro3d/section_manager.py`

Replaces `firepro3d/elevation_manager.py`.

### 11.2 Responsibilities

- Owns all `SectionMarker` instances and open `SectionScene`/`SectionView` pairs
- Auto-increment counter for section naming
- Tab lifecycle: create, switch-to, close
- Serialization: `to_list()` / `from_list()` for project file persistence

### 11.3 Key methods

```
place_section(cut_a, cut_b, look_sign, far_clip) → SectionMarker
open_section(name) → SectionView
close_section(name)
delete_section(name)
rename_section(old, new)
create_cardinal(direction)
rebuild_all()
to_list() → list[dict]
from_list(data)
```

### 11.4 Cardinal shortcut logic

`create_cardinal(direction)`:
- Computes A→B from current scene bounding rect (or default 10000mm span if empty)
- Angle: North=0°, East=90°, South=180°, West=270°
- `look_sign` set to match existing elevation direction conventions
- Name set to direction string ("North", "South", etc.) instead of auto-increment

## 12. Section Placement Tool

### 12.1 Mode: `"section"`

New mode in `ModelSpace` mode system.

### 12.2 Workflow

1. User clicks "Section" ribbon button → enters `"section"` mode
2. **Click 1**: A endpoint placed. Rubber-band line follows cursor
3. **Click 2**: B endpoint placed. `SectionMarker` created with default depth (5000mm) and default look direction (left-hand perpendicular)
4. Mode returns to `"select"`

### 12.3 Integration

- Both clicks snap via existing `_apply_snapping()` path
- Status bar instruction: `"Click first point of section cut, then second point"`
- Placing a marker pushes an undo state
- Handler methods in `model_space.py`: `_on_press_section`, `_on_move_section`, `_on_press_section_pt2`

## 13. MainWindow Integration

### 13.1 Manager initialization

Replace `ElevationManager` with `SectionManager` in `main.py`:

```python
self.section_manager = SectionManager(
    self.scene, self.level_manager, self.scale_manager, self.central_tabs)
self.scene._section_manager = self.section_manager
self.level_widget.levelsChanged.connect(self.section_manager.rebuild_all)
```

### 13.2 View request handler

Update `_on_open_view_requested()`:

```python
def _on_open_view_requested(self, view_type, name):
    if view_type == "section":
        self.section_manager.open_section(name)
    elif view_type == "detail":
        self._activate_detail_view(name)
```

### 13.3 Cardinal shortcuts

Replace `_create_elevation_markers()` with:

```python
for direction in ("north", "south", "east", "west"):
    self.section_manager.create_cardinal(direction)
```

### 13.4 Ribbon changes

- Add "Section" button to Draw tab → enters `"section"` mode
- Keep N/S/E/W buttons, rewired to `section_manager.create_cardinal()`

### 13.5 Project file serialization

Add `"sections"` key to project save/load alongside existing `"details"` key:

```python
# Save
data["sections"] = self.section_manager.to_list()

# Load
if "sections" in data:
    self.section_manager.from_list(data["sections"])
```

### 13.6 State version

`_STATE_VERSION`: bump to 6 (the OSNAP toolbar bumped it 4→5 on 2026-06-22, so current is 5 → next is 6).

## 14. Migration & Retirement

### 14.1 Files retired

| File | Replacement |
|---|---|
| `elevation_scene.py` | `section_scene.py` |
| `elevation_view.py` | `section_view.py` |
| `elevation_manager.py` | `section_manager.py` |

### 14.2 Files modified

| File | Changes |
|---|---|
| `main.py` | Replace elevation manager with section manager, update ribbon, update view request handler, add section serialization |
| `model_space.py` | Add `"section"` mode handlers, replace `_elevation_manager` ref with `_section_manager` |
| `view_marker.py` | `ViewMarkerArrow` and `SharedCropBox` retired (replaced by `SectionMarker`) |

### 14.3 Backward compatibility

Old project files without a `"sections"` key: load normally, no section markers. Cardinal sections created on first startup as before. No data migration needed — elevation views were never persisted.

## 15. Edge Cases

### 15.1 Empty section

No entities within view box → only level datums and gridlines shown. No special handling.

### 15.2 Scale not calibrated

Projection uses `ppm = 1.0` fallback. Section views work but at wrong scale. Same behavior as existing elevation.

### 15.3 Wall parallel to cut line

Wall intersection override (§6.2) classifies as cut if the cut line crosses the wall quad, preventing misclassification by centroid depth alone.

### 15.4 Pipe at exact cut plane

Pipe crossing the cut plane at a single point: shown as filled circle (cross-section) at the intersection point.

### 15.5 Very short cut line

A→B distance less than 100mm: reject placement with a status bar warning. Prevents degenerate views.

### 15.6 Coincident A and B

Zero-length cut line: rejected at placement time. `SectionScene` constructor asserts `length(AB) > 0`.

### 15.7 Old project files

No `"sections"` key → no migration. Cardinal markers created fresh on startup. Existing elevation data was never persisted, so nothing is lost.

## 16. Out of Scope (v1)

- Jogged/stepped section lines (follow-up: multi-segment cut with stitched projection)
- Break lines for vertical compression (follow-up: coordinate discontinuity management)
- In-scene dimensions and annotations (depends on annotations spec)
- Direct geometry editing in section view (future: bidirectional sync)
- Vertical crop handles on section marker (future: restrict visible level range)

## 17. Acceptance Criteria

- [ ] `SectionMarker` placed via two-click tool with direction arrows, callout bubbles, and dashed extent lines
- [ ] Section markers persist in project file via `to_dict()` / `from_dict()`
- [ ] Double-click marker opens section view tab with projected geometry
- [ ] Items at cut plane rendered with section hatch; items behind rendered lighter (0.5 opacity)
- [ ] All entity types project correctly (walls, floors, pipes, nodes, sprinklers, gridlines, roofs)
- [ ] Level datum lines rendered as horizontal dash-dot references
- [ ] A/B endpoint grips, far clip drag, direction flip all functional
- [ ] Cardinal shortcuts (N/S/E/W) create section markers at 0°/90°/180°/270° with default depth
- [ ] `ElevationScene` / `ElevationView` / `ElevationManager` retired
- [ ] Select entity in section → property panel shows properties, edits propagate back
- [ ] Right-click context menu on marker (Open, Rename, Flip Direction, Delete)
- [ ] Cardinal section views produce visually equivalent output to old elevation views
- [ ] Projection math verified for arbitrary angles via unit tests

## 18. Test Strategy

### 18.1 Unit tests — Projection math (`tests/test_section_scene.py`)

| Test | Verifies |
|---|---|
| `test_projection_cardinal_north` | Matches old `_world_to_elev()` for north |
| `test_projection_cardinal_all` | All 4 cardinal directions equivalent to ElevationScene |
| `test_projection_45_degrees` | Arbitrary angle produces correct H/V |
| `test_projection_inverse` | Round-trip project → unproject recovers world coords |
| `test_depth_at_cut_plane` | Entity on cut line → `depth ≈ 0`, classified as cut |
| `test_depth_behind` | Behind cut → `0 < depth ≤ far_clip`, classified as behind |
| `test_depth_front_hidden` | In front → hidden |
| `test_depth_beyond_hidden` | Beyond far clip → hidden |
| `test_lateral_clipping` | Outside A→B extent → hidden |
| `test_wall_cut_intersection` | Cut line crossing wall quad → classified as cut |

### 18.2 Unit tests — Marker (`tests/test_section_marker.py`)

| Test | Verifies |
|---|---|
| `test_serialization_roundtrip` | `to_dict()` → `from_dict()` preserves all fields |
| `test_flip_direction` | `look_sign` inverts, normal reverses |
| `test_auto_increment_naming` | Sequential markers get "Section 1", "Section 2" |
| `test_cardinal_naming` | Cardinal shortcuts get direction names |

### 18.3 Integration tests (`tests/test_section_integration.py`)

| Test | Verifies |
|---|---|
| `test_marker_to_view` | Place marker → double-click → tab opens with projected items |
| `test_select_syncs_properties` | Select in section → property panel shows properties |
| `test_rebuild_on_model_change` | Modify wall in plan → section scene rebuilds |
| `test_cardinal_matches_old_elevation` | N/S/E/W section ≡ old ElevationScene output |

## 19. Verification Checklist

- [ ] All acceptance criteria met
- [ ] All unit and integration tests pass
- [ ] Cardinal sections produce visually equivalent results to old elevation views
- [ ] No regressions in plan view, detail view, or 3D view
- [ ] Section markers render correctly in both dark and light themes
- [ ] Project file round-trip: save with sections → load → sections restored correctly
- [ ] Old project files (no sections key) load without errors
- [ ] `_STATE_VERSION` bump doesn't break existing saved layouts

## 20. Existing Code Context

| Component | File | Lines | Role |
|---|---|---|---|
| ElevationScene (retiring) | `elevation_scene.py` | 1-1302 | Cardinal projection, rebuild pipeline |
| Projection math | `elevation_scene.py` | 660-682 | `_world_to_elev()` |
| Wall projection | `elevation_scene.py` | 758-850 | Quad → rect, depth sorting |
| Pipe projection | `elevation_scene.py` | 854-899 | Node → line, depth sorting |
| Sprinkler projection | `elevation_scene.py` | 903-946 | Node → ellipse |
| Floor slab projection | `elevation_scene.py` | 950-1024 | Mask + visible rect |
| Roof projection | `elevation_scene.py` | 1028-1074 | 3D mesh → bounding rect |
| Depth sorting | `elevation_scene.py` | 708-724 | Farthest-first Z assignment |
| ElevationView (retiring) | `elevation_view.py` | 1-150 | Pan/zoom/fit, grips |
| ElevationManager (retiring) | `elevation_manager.py` | 1-118 | Tab lifecycle |
| ViewMarkerArrow (retiring) | `view_marker.py` | 121-314 | Cardinal marker visual |
| SharedCropBox (retiring) | `view_marker.py` | 48-114 | Shared elevation crop |
| DetailMarker (reference) | `detail_view.py` | 44-412 | Serialization pattern |
| Section hatch | `displayable_item.py` | 30-81 | `draw_section_hatch()` |
| Z-range filter | `level_manager.py` | 33-62 | `_apply_z_filter()` |
| View request signal | `model_space.py` | 66 | `openViewRequested` |
| Marker creation | `main.py` | 811-816 | `_create_elevation_markers()` |
| State version | `main.py` | 2816 | `_STATE_VERSION = 4` (→ 6) |
