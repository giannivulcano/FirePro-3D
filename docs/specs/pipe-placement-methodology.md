# Pipe Placement Methodology — Specification

> **Status:** Revised specification (documents current implementation + required fixes)
> **Source files:** `model_space.py`, `pipe.py`, `node.py`, `fitting.py`, `sprinkler_system.py`, `constants.py`
> **Date:** 2026-04-04
> **Revision:** 2 (post grill session)

---

## 1. Overview

Pipe placement in FirePro3D is a **manual, click-to-place drawing tool** that creates pipe segments between junction nodes. The system uses a **template-based property inheritance** model, **continuous polyline** drawing mode, and several **automatic geometry corrections** (collinear merging, 45° elbow-to-wye conversion, pipe splitting).

The piping network is a **tree topology** (no loops) stored as a flat list of `Pipe` and `Node` objects in `SprinklerSystem`. Network graph structure is implicit — derived at runtime from `pipe.node1`/`pipe.node2` references and `node.pipes` lists.

### 1.1 Foundational Rules

These rules govern the entire pipe placement system:

| Rule | Rationale |
|---|---|
| **All pipe creation MUST go through `add_pipe()`** | Prevents inconsistent state from manual `Pipe()` + `addItem()` construction. Use `_propagate_ceiling=False` when callers manage Z themselves. |
| **Snapping is 2D (canvas input)** | The user clicks on a 2D canvas; snap constrains cursor position in plan view. |
| **All geometry validation uses 3D vectors** | Backtrack detection, collinear checks, 4th-branch validation, fitting determination, and angle measurements must use `(x, y, z_pos)` vectors to correctly handle pipes at different elevations. |
| **Bare nodes without pipes or sprinklers must not exist** | Auto-cleanup on pipe deletion is correct and intentional. |

---

## 2. Data Model

### 2.1 Pipe (`firepro3d/pipe.py`)

| Attribute | Type | Default | Description |
|---|---|---|---|
| `node1`, `node2` | `Node \| None` | — | Endpoint nodes (`None` = template pipe) |
| `length` | `float` | — | 2D scene-pixel distance (auto-computed) |
| `ceiling_level` | `str` | `"Level 1"` | Level the pipe hangs from |
| `ceiling_offset` | `float` | `-50.8` mm | Distance below ceiling (negative = below) |
| `user_layer` | `str` | `"Default"` | CAD-style user layer |
| `level` | `str` | `"Level 1"` | Display/visibility level |
| `_placement_phase` | `int` | `0` | Template state: 0 = before 1st click, 1 = before 2nd |

**Editable Properties** (`_properties` dict):

| Key | Type | Default | Options |
|---|---|---|---|
| Diameter | enum | `"1\"Ø"` | `1"Ø`, `1-½"Ø`, `2"Ø`, `3"Ø`, `4"Ø`, `5"Ø`, `6"Ø`, `8"Ø` |
| Schedule | enum | `"Sch 40"` | `Sch 10`, `Sch 40`, `Sch 80`, `Sch 40S`, `Sch 10S` |
| C-Factor | string | `"120"` | Hazen-Williams roughness coefficient |
| Material | enum | `"Galvanized Steel"` | Galvanized Steel, Stainless Steel, Black Steel, PVC |
| Ceiling Level | level_ref | `"Level 1"` | Any defined level |
| Ceiling Offset | string | `"-50.8"` | mm below ceiling |
| Line Type | enum | `"Branch"` | Branch (75 mm width), Main (150 mm width) |
| Colour | enum | `"Red"` | Black, White, Red, Blue, Grey |
| Phase | enum | `"New"` | New, Existing, Demo |
| Show Label | enum | `"True"` | True, False |
| Label Size | string | `"12"` | Text height in inches |

**Auto-assignment rule:** Diameters ≥ 3" automatically set Line Type to `"Main"`.

**Per-node template elevations** (used only during placement):

- `node1_ceiling_level`, `node1_ceiling_offset`
- `node2_ceiling_level`, `node2_ceiling_offset`

### 2.2 Node (`firepro3d/node.py`)

| Attribute | Type | Default | Description |
|---|---|---|---|
| `x_pos`, `y_pos` | `float` | — | Scene position |
| `z_pos` | `float` | — | 3D elevation = `level.elevation + ceiling_offset` |
| `ceiling_level` | `str` | `"Level 1"` | Ceiling reference level |
| `ceiling_offset` | `float` | `-50.8` mm | Offset below ceiling |
| `pipes` | `list[Pipe]` | `[]` | Connected pipes (**max 4**) |
| `sprinkler` | `Sprinkler \| None` | `None` | Attached sprinkler head |
| `fitting` | `Fitting` | — | Auto-created, always present |
| `RADIUS` | `int` | `13` | Visual radius (scene units) |

### 2.3 Fitting (`firepro3d/fitting.py`)

Fittings are **auto-determined** from the count and angles of connected pipes.

**Complete fitting type matrix:**

| Vertical | Horizontal | Condition | Fitting Type |
|---|---|---|---|
| 0 | 0 | — | `"no fitting"` |
| 0 | 1 | — | `"cap"` |
| 0 | 2 | ~180° (collinear) | `"no fitting"` |
| 0 | 2 | ~90° | `"90elbow"` |
| 0 | 2 | ~45° or ~135° | `"45elbow"` |
| 0 | 3 | ~90° branch | `"tee"` |
| 0 | 3 | ~45° or ~135° branch | `"wye"` |
| 0 | 4 | Two perpendicular collinear pairs | `"cross"` |
| 1 (up) | 0 | — | `"cap_up"` |
| 1 (down) | 0 | — | `"cap_down"` |
| 1 (up) | 1 | — | `"elbow_up"` |
| 1 (down) | 1 | — | `"elbow_down"` |
| 1 | 2 | 90° horizontal branch | `"tee_up"` / `"tee_down"` |
| 2 (up+down) | 1 | Through-riser with branch | `"tee_vertical"` **(NEW)** |
| 2 (up+down) | 2 | Through-riser with cross | `"cross_vertical"` **(NEW)** |

> **BUG (current):** `determine_type()` only inspects `vertical[0]`, ignoring second vertical pipe. Through-risers (2 vertical + horizontal branches) return wrong fitting types.
>
> **FIX:** Implement full matrix above. Requires new SVG symbols for `tee_vertical` and `cross_vertical`.

Fitting SVGs are located in `firepro3d/graphics/fitting_symbols/`.

### 2.4 SprinklerSystem (`firepro3d/sprinkler_system.py`)

Flat container — no graph structure:

```python
self.nodes = []        # All junction nodes
self.pipes = []        # All pipe segments
self.sprinklers = []   # All sprinkler heads
self.fittings = []     # All fitting symbols
self.supply_node = None
```

Graph topology is built on-demand by `HydraulicSolver._build_adjacency()` via BFS from the supply node.

---

## 3. Pipe Placement Tool — User Interaction

### 3.1 Entry & Mode

1. User clicks **Pipe** button in ribbon → `scene.set_mode("pipe", current_pipe_template)`
2. `current_pipe_template` is a `Pipe(None, None)` instance storing the user's last-used properties
3. Template persists across sessions via `QSettings("GV", "FirePro3D")`
4. Status bar shows: `"Click to place first node, then second node"`

### 3.2 Phase 0 → Phase 1: First Click (Start Node)

**Entry point:** `_press_pipe()` at `model_space.py:4479`

```
User clicks on canvas
    │
    ├─ find_nearby_node(snapped.x, snapped.y, z_hint=template_z)
    │   ├─ Priority 1: cursor inside any sprinkler's bounding box → snap to that node
    │   ├─ Priority 2: distance ≤ SNAP_RADIUS → snap to that node
    │   └─ Tiebreaker: among Z-stacked candidates, prefer closest to z_hint
    │
    ├─ If existing node found and len(node.pipes) >= 4:
    │   └─ BLOCK: "Connection Limit" warning → return
    │
    ├─ If click lands on an existing Pipe:
    │   └─ split_pipe() → creates new junction node at click point
    │      (splits original pipe into two segments)
    │
    ├─ Else:
    │   └─ find_or_create_node() → returns existing or new node
    │
    ├─ Elevation mismatch check:
    │   If existing node's z_pos ≠ template's target z_pos:
    │   └─ 3-option dialog (see §5.4)
    │
    ├─ If node is NEW: apply template elevation TO the node
    │   node.ceiling_level = template.node1_ceiling_level
    │   node.ceiling_offset = template.node1_ceiling_offset
    │
    ├─ If node is EXISTING: adopt its elevation INTO the template
    │   template.node1_ceiling_level = node.ceiling_level
    │   template.node1_ceiling_offset = node.ceiling_offset
    │
    ├─ Default Node 2 ceiling = Node 1 ceiling (horizontal pipe)
    │
    ├─ template._placement_phase = 1
    │
    └─ Status: "Pick end node"
```

### 3.3 Phase 1 → Pipe Created: Second Click (End Node)

```
User clicks second point
    │
    ├─ Snap to 45° grid (2D only):
    │   snapped_end = start_node.snap_point_45(start_pos, snapped)
    │   (nearest 0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°)
    │
    ├─ Backtrack check (_would_backtrack_at) — uses 3D vectors:
    │   ├─ Direct duplicate: pipe already connects same two nodes → BLOCK
    │   └─ End point lies on existing pipe segment from start → BLOCK
    │   NOTE: pipes at different Z that overlap in plan view are NOT backtrack
    │
    ├─ Connection limit validation (start node) — uses 3D vectors:
    │   ├─ ≥ 4 pipes → BLOCK
    │   └─ = 3 pipes → _validate_4th_branch():
    │       ├─ Current fitting must be "tee"
    │       └─ New pipe must be perpendicular to through-run (within ~10°)
    │       └─ Else → BLOCK: "must be perpendicular to form a cross"
    │
    ├─ Connection limit validation (end node, if existing):
    │   └─ Same checks as start node
    │
    ├─ If click lands on existing Pipe:
    │   └─ split_pipe() → junction at click point
    ├─ Else:
    │   └─ find_or_create_node()
    │
    ├─ Zero-length check:
    │   If end_node IS start_node:
    │   ├─ If template specifies different Z for Node 2 (vertical pipe):
    │   │   └─ Create intermediate node at same XY with Node 2's elevation
    │   └─ Else: ignore click (wait for valid point)
    │
    ├─ Elevation mismatch check on existing end node:
    │   └─ 3-option dialog (see §5.4)
    │
    ├─ ── COLLINEAR EXTENSION CHECK (3D) ──
    │   _try_extend_collinear(start_node, end_node, template):
    │   ├─ Conditions (ALL must be true):
    │   │   ├─ start_node has exactly 1 existing pipe
    │   │   ├─ start_node has no sprinkler
    │   │   ├─ 3D direction matches (within 5° tolerance)
    │   │   └─ Same continuation direction (3D dot product ≈ 1.0)
    │   │   └─ Z slope must match (dZ/dXY ratio equal)
    │   ├─ If yes:
    │   │   ├─ Reconnect existing pipe: replace start_node with end_node
    │   │   ├─ Remove orphaned start_node from scene
    │   │   └─ Return True (skip creating new pipe)
    │   └─ If no: Return False → create new pipe normally
    │   NOTE: applies to vertical pipes too — risers passing through
    │   intermediate floors merge into single pipes; junction nodes are
    │   created on-demand when horizontal branches are added via split_pipe()
    │
    ├─ If NOT extended:
    │   ├─ add_pipe(start_node, end_node, template)
    │   ├─ Update fittings at both nodes + all neighbor nodes
    │   │
    │   └─ ── 45° ELBOW → WYE CONVERSION ──
    │       _convert_45_elbow_to_wye(start_node, template):
    │       ├─ If start_node.fitting.type == "45elbow":
    │       │   ├─ Measure angle between 2 pipe vectors (3D)
    │       │   ├─ If ~135° → normal 45° elbow → leave it
    │       │   ├─ If ~45° → too sharp for real fitting:
    │       │   │   ├─ Add 1-ft (304.8 mm) capped stub
    │       │   │   │   opposite the through-pipe direction
    │       │   │   └─ Node becomes 3-pipe wye
    │       └─ Else: no-op
    │
    ├─ ── CONTINUOUS POLYLINE ──
    │   end_node becomes new start_node for next segment
    │   template.node1 adopts end_node's elevation
    │   template.node2 defaults to match (horizontal continuation)
    │
    └─ Status: "Pick next node (Esc/double-click to finish)"
```

### 3.4 Chain Termination

- **Escape** or **double-click**: Ends the chain, stays in pipe mode
- **Mode change**: Exits pipe mode entirely
- **Orphan cleanup**: Nodes with 0 pipes and no sprinkler are removed on `delete_pipe()`

---

## 4. Automatic Geometry Corrections

### 4.1 45° Snap Grid

All pipe endpoints snap to the nearest 45° increment from the start node:

```
Allowed angles: 0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°
Snap tolerance: SNAP_TOLERANCE_DEG = 7.5°
```

**Method:** `Node.snap_point_45(start, end)` — projects the cursor position onto the nearest 45° ray from the start point. **Snap operates in 2D only** (canvas input constraint).

> **BUG (current):** `snap_point_45` uses `self.pipes[0]` as the angular reference — insertion-order dependent, ignores the contextually relevant pipe.
>
> **FIX:** During chain continuation, the snap reference must be the pipe the user is continuing from (the last segment). For a fresh start from an existing node, prefer the through-run direction (collinear pair) if one exists; fall back to `pipes[0]` only if no through-run.

### 4.2 Collinear Extension

**Purpose:** Prevent unnecessary intermediate nodes on straight pipe runs.

**Trigger:** Placing a new pipe from a node that has exactly 1 existing pipe, where the new **3D direction** continues the existing pipe's direction (within 5° tolerance).

**Action:**
1. Reconnect the existing pipe's endpoint from `start_node` → `end_node`
2. Remove the now-orphaned `start_node`
3. Result: one longer pipe instead of two pipes with a pass-through node

**Guards:**
- Node must not have a sprinkler (sprinklers require a dedicated node)
- Direction must be a continuation (3D dot product ≈ 1.0), not a reversal
- **Z slope must match** — `dZ/dXY` ratio must be equal for both segments; a flat pipe and a sloped pipe that are collinear in plan view must NOT merge

**Vertical pipes:** Collinear extension applies to vertical pipes (same XY, same Z direction). Risers passing through intermediate floors merge into single pipes. Junction nodes are created on-demand when horizontal branches are later added via `split_pipe()` or `_split_vertical_pipe()`.

> **BUG (current):** Uses 2D vectors only (`scenePos()`). Two pipes collinear in plan view but at different Z slopes are incorrectly merged. Vertical pipes (`len_old < 1e-6`) are never merged.
>
> **FIX:** Use 3D direction vectors `(dx, dy, dz)` for the collinear check.

### 4.3 45° Elbow to Wye Conversion

**Purpose:** A 45° angle between two pipe vectors is too sharp for real fittings. Convert to a proper wye by adding a capped stub.

**Trigger:** After pipe placement, if `junction_node.fitting.type == "45elbow"` and the angle between vectors is ~45° (not ~135°, which is a normal body-angle 45° elbow).

**Action:**
1. Determine through-pipe direction (the first/older pipe)
2. Add a 304.8 mm (1 ft) capped stub continuing opposite the through direction
3. Node becomes a 3-pipe wye fitting

### 4.4 Pipe Splitting

**Purpose:** Allow users to create junctions on existing pipe segments.

**Trigger:** User clicks on an existing `Pipe` item during placement.

**Action (`split_pipe()`):**
1. If click is near an existing endpoint (within `SNAP_RADIUS`), return that node
2. Otherwise, create new node at the projected click point
3. Create two new pipes: `node_a → new_node` and `new_node → node_b`
4. Delete original pipe
5. New pipes inherit all properties from the split pipe (used as template)
6. Update fittings at all three nodes

**Vertical pipe splitting** (`_split_vertical_pipe()`):
- Splits a vertical pipe at a target Z elevation
- Creates a mid-node at the pipe's XY with the target Z
- Replaces original with two shorter vertical pipes

### 4.5 Backtrack Prevention

**Purpose:** Prevent placing duplicate or overlapping pipes.

**Checks (`_would_backtrack_at()`) — must use 3D vectors:**
1. **Direct duplicate:** Target point is within 5 px of an existing neighbor node **at the same Z**
2. **Overlap:** Target point projects onto an existing pipe segment (within 10 px perpendicular distance, parameter `t` between 0.01 and 0.99) **at the same Z**

> **BUG (current):** Uses 2D vectors only. Pipes at different elevations that overlap in plan view are incorrectly blocked as backtrack.
>
> **FIX:** Use 3D vectors. Pipes on different levels that overlap in plan view are not duplicates.

---

## 5. Elevation & 3D Positioning

### 5.1 Z-Position Computation

```
node.z_pos = level.elevation + node.ceiling_offset
```

- `ceiling_level` names a level (e.g., "Level 1") → looked up in `LevelManager`
- `ceiling_offset` is typically `-50.8 mm` (2 inches below ceiling)
- Elevation is stored in millimeters

### 5.2 Template Elevation Propagation

During pipe placement, ceiling properties flow in two directions:

| Scenario | Direction | Behavior |
|---|---|---|
| New node created | Template → Node | Node gets template's ceiling level/offset |
| Existing node selected | Node → Template | Template adopts node's existing elevation |
| Chain continuation | End node → Template Node 1 | Next segment starts at previous end elevation |
| Default Node 2 | Copies Node 1 | Horizontal pipe by default |

### 5.3 Vertical Pipes (Risers/Drops)

Created when template specifies different ceiling levels for Node 1 and Node 2:
- Typically same XY position, different `z_pos` (vertical riser)
- Can also be diagonal (e.g., along a roof slope or stair) — same XY is not required
- Detected via `_is_vertical()`: both endpoints share XY but differ in Z
- An intermediate node is created at the same XY with Node 2's elevation

### 5.4 Elevation Mismatch Handling

When selecting an existing node whose `z_pos` differs from the template's target, a **3-option dialog** is shown:

| Choice | Action |
|---|---|
| **Riser** | Auto-create a vertical pipe between existing node and a new intermediate node at the template's Z. Checks for existing vertical geometry first via `_find_or_split_vertical_at_z()` — reuses or splits existing risers rather than creating duplicates. Continues placement from the intermediate node. |
| **Match** | Adopt the existing node's elevation into the template. Abandons the template's target Z. |
| **Template** | Keep template elevation. Find/split existing vertical geometry at that Z, or create a standalone node at the template's Z. |

> **BUG (current):** The "Riser" path manually constructs pipes (`Pipe()` + `addItem()`) instead of using `add_pipe()`. This skips `apply_category_defaults`, `update_label`, `update_geometry`, fitting updates, and ceiling propagation. Same issue in `_create_vertical_connection()` and `_split_vertical_pipe()`.
>
> **FIX:** All three code paths must use `add_pipe(n1, n2, template, _propagate_ceiling=False)` since they manage Z themselves.

---

## 6. Node Connection Rules

### 6.1 Maximum 4 Connections

Each node supports at most 4 pipe connections (cross fitting).

### 6.2 4th Branch Validation (`_validate_4th_branch()`)

Adding a 4th pipe to a 3-pipe node is only allowed if:
1. Current fitting is a `"tee"` (has a collinear through-run pair)
2. New pipe is **perpendicular** to the through-run (within ~10°, `|dot| < 0.17`)

The through-run is identified by finding the collinear pair among existing pipes (`dot < -0.95`, i.e., ~180° ± 18°). **Must use 3D vectors.**

### 6.3 Node Snapping & Z Disambiguation

`find_nearby_node()` snap uses XY distance only (correct — snap is a 2D canvas operation).

**Disambiguation when multiple nodes exist at the same XY (risers):**

| Context | Tiebreaker |
|---|---|
| Pipe placement | Prefer node closest to template's target Z (`z_hint`) |
| Sprinkler placement | Prefer node closest to active level's elevation |
| General selection | Prefer node on active level |

> **BUG (current):** `find_nearby_node()` is Z-blind — returns the first node within SNAP_RADIUS by insertion order. This causes:
> 1. Wrong-elevation pipe connections (triggering unnecessary mismatch dialogs)
> 2. Connection limit false positives (checking wrong node's pipe count)
> 3. 4th-branch validation against wrong node's geometry
> 4. Sprinklers placed on wrong Z-stacked node
> 5. Paste/duplicate merging into wrong node
>
> **FIX:** Add optional `z_hint` parameter to `find_nearby_node()`. Among XY candidates, prefer the node whose `z_pos` is closest to `z_hint`. All placement tools pass their target Z.

### 6.4 Node Move Behavior with Risers

> **BUG (current):** Moving a node that is part of a riser (Z-stacked at same XY) only moves that one node. The other Z-stacked nodes stay in place, creating impossible diagonal pipe geometry.
>
> **FIX:** When moving a node that has vertical pipes, move all Z-stacked nodes at the same XY as a unit.

---

## 7. Pipe Creation (`add_pipe()`)

**Method:** `model_space.py:930`

```python
add_pipe(n1, n2, template=None, _propagate_ceiling=True)
```

**This is the ONLY permitted way to create pipes.** No manual `Pipe()` + `addItem()` construction.

**Sequence:**
1. Create `Pipe(n1, n2)` — registers pipe in both `n1.pipes` and `n2.pipes`
2. Set `pipe.user_layer = active_user_layer`
3. If template provided: `pipe.set_properties(template)` (copies all properties)
4. Set `pipe.level = active_level` (display level, NOT ceiling level)
5. Register in `sprinkler_system.pipes`
6. Add to scene (`addItem`)
7. Apply display manager category defaults
8. Update label and geometry
9. Force visibility on
10. Update fittings at **both endpoints and all their neighbors**
11. Apply fitting display manager colors
12. Force viewport repaint
13. If `_propagate_ceiling`:
    - **With template:** Use per-node ceiling values (`node1_ceiling_level/offset`, `node2_ceiling_level/offset`), falling back to pipe-level values
    - **Without template:** Apply pipe's single ceiling level/offset to both nodes
    - Recompute `z_pos` on both nodes

---

## 8. Pipe Deletion (`delete_pipe()`)

**Method:** `model_space.py:1473`

1. Remove pipe from both endpoint nodes' `pipes` lists
2. If a node has **no pipes and no sprinkler** → remove the node entirely
3. Clear `pipe.node1` and `pipe.node2` references
4. Remove pipe from scene
5. Remove from `sprinkler_system.pipes`

---

## 9. Display & Rendering

### 9.1 2D Plan View

| Property | Branch | Main |
|---|---|---|
| Display width | 75 mm | 150 mm |
| Auto-assign | Diameters < 3" | Diameters ≥ 3" |
| Pen cap | Round (default) | Round (default) |
| Z-value | 5 | 5 |

**Color sources** (priority order):
1. Hydraulic velocity color-coding (if results available)
2. Pipe `Colour` property
3. Display manager category defaults

**Velocity color thresholds:**

| Velocity | Color | Hex |
|---|---|---|
| < 12 fps | Green | `(0, 200, 80)` |
| 12–20 fps | Orange | `(220, 140, 0)` |
| > 20 fps | Red | `(220, 0, 0)` |

**Labels** (when `Show Label == "True"`):
- Diameter in display units using `_INT_TO_IMPERIAL` / `_INT_TO_METRIC` mappings
- **3D length** (computed from `sqrt(dx² + dy² + dz²)`, matching hydraulic solver)
- Hydraulic results if available (flow gpm, friction loss psi)
- Positioned at midpoint, rotated to align with pipe
- Hidden for vertical pipes (zero 2D projection)

> **BUG (current):** `update_label()` shows 2D projected length via `scene_to_display(self.length)`, not 3D length. Inconsistent with hydraulic solver's `get_length_ft()`.
>
> **FIX:** Labels must show 3D length. Use `get_length_ft()` (or equivalent mm computation) for the label.

> **BUG (current):** `update_elevations()` in LevelManager recomputes node Z positions but does not refresh pipe labels. Once labels show 3D length, changing a level's elevation leaves labels stale.
>
> **FIX:** `update_elevations()` must call `pipe.update_label()` on all pipes after recomputing node Z positions.

**Fitting clipping:** Pipes are clipped around fitting SVGs at higher elevations to prevent visual overlap.

**Hit detection:** `shape()` method ensures pipes remain clickable — minimum 16 screen pixels wide regardless of zoom.

### 9.2 Preview Pipe (During Placement)

The preview pipe is rendered in `_move_pipe()` during mouse movement between clicks.

**Shows:**
- Colored dashed line from start node to cursor (styled from template)
- Preview label with diameter and length

> **BUG (current):** Preview label formats diameter using `float()` on the raw diameter key (e.g., `"1\"Ø"`), which always throws `ValueError`. Falls through to raw key display instead of using `_INT_TO_IMPERIAL` / `_INT_TO_METRIC` mappings. Preview shows `1"Ø` while placed pipes show `Ø 1"`.
>
> **FIX:** Preview must use `Pipe._INT_TO_IMPERIAL` / `_INT_TO_METRIC` for diameter display, matching placed pipe labels.

> **BUG (current):** Preview length is 2D pixel distance only. Does not account for Z difference between N1 and N2 template elevations.
>
> **FIX:** Preview must compute 3D length using `sqrt(dx² + dy² + dz²)` where `dz` comes from the template's N1/N2 ceiling values.

### 9.3 3D View (`view_3d.py`)

| Pipe Count | Rendering | Detail |
|---|---|---|
| ≤ 200 | Cylinder meshes | Radius from OD table, grouped by color |
| > 200 | Line segments | Line width proportional to diameter |

Colors match 2D with velocity overrides when hydraulic results are present.

---

## 10. Hydraulic Integration

### 10.1 Pipe Data Used by Solver

| Property | Accessor | Used For |
|---|---|---|
| Inner diameter | `get_inner_diameter()` → `INNER_DIAMETER_IN[schedule][diameter]` | Hazen-Williams friction loss |
| 3D length | `get_length_ft(sm)` → accounts for vertical Z difference | Friction loss calculation |
| C-Factor | `_properties["C-Factor"]["value"]` | Roughness coefficient |

### 10.2 Hazen-Williams Equation

```
Friction loss:  hf = 4.52 × Q^1.852 / (C^1.852 × d^4.87) × L  [psi]
Velocity:       v  = Q × 0.4085 / d²  [fps]
```

Where: Q = flow (gpm), C = C-factor, d = inner diameter (inches), L = length (ft)

### 10.3 Network Topology Discovery

1. `_build_adjacency()`: Creates `{node: [(pipe, neighbor), ...]}` from all pipes
2. `_bfs_tree()`: BFS from supply node → produces parent map, pipe-to-parent map, children map, traversal order
3. 4-phase hydraulic solve: assign flows → propagate pressure backward → compare supply → propagate forward

---

## 11. Persistence (JSON)

### 11.1 Project File Format (version 9)

**Node serialization:**
```json
{
  "id": 0,
  "x": 400.0, "y": 140.0,
  "elevation": 0.0, "z_offset": 0.0,
  "user_layer": "Default", "level": "Level 1",
  "ceiling_level": "Level 1", "ceiling_offset_mm": -50.8,
  "room_name": "Room A",
  "sprinkler": { ... },
  "display_overrides": { ... }
}
```

**Pipe serialization:**
```json
{
  "node1_id": 0, "node2_id": 1,
  "user_layer": "Default", "level": "Level 1",
  "ceiling_level": "Level 1", "ceiling_offset_mm": -50.8,
  "properties": {
    "Diameter": "2\"Ø", "Schedule": "Sch 40",
    "C-Factor": "120", "Material": "Galvanized Steel",
    "Ceiling Level": "Level 1", "Ceiling Offset": "-50.8",
    "Line Type": "Branch", "Colour": "Red",
    "Phase": "New", "Show Label": "True", "Label Size": "12"
  },
  "display_overrides": {}
}
```

**Load sequence:** Nodes are loaded first (with stable integer IDs), then pipes reference them by `node1_id`/`node2_id`.

---

## 12. Template System

### 12.1 Template Pipe

A `Pipe(None, None)` instance — never added to the scene — that stores the user's preferred properties for the next pipe segment.

### 12.2 Template Lifecycle

| Event | Action |
|---|---|
| Application start | Load from `QSettings("GV", "FirePro3D")` key `"template/pipe"` |
| User changes property in panel | Property written to template |
| Pipe tool activated | Template passed to `scene.set_mode("pipe", template)` |
| First click (new node) | Template elevation → node |
| First click (existing node) | Node elevation → template |
| Pipe created | `pipe.set_properties(template)` copies all properties |
| Chain continuation | End node elevation → template Node 1 |
| Application exit | Save to `QSettings` |

### 12.3 Per-Node Elevation on Templates

Templates carry separate ceiling values for each endpoint:
- `node1_ceiling_level` / `node1_ceiling_offset` (locked after 1st click)
- `node2_ceiling_level` / `node2_ceiling_offset` (editable between 1st and 2nd click)

This allows placing **vertical pipes** (risers/drops) and **diagonal pipes** (roof slopes, stairs) where Node 1 and Node 2 are at different elevations.

---

## 13. Key Constants

| Constant | Value | Location |
|---|---|---|
| `SNAP_RADIUS` | Scene-dependent | `model_space.py` |
| `SNAP_TOLERANCE_DEG` | 7.5° | `pipe.py` |
| `BRANCH_WIDTH_MM` | 75.0 mm | `pipe.py` |
| `MAIN_WIDTH_MM` | 150.0 mm | `pipe.py` |
| `DEFAULT_CEILING_OFFSET_MM` | -50.8 mm | `constants.py` |
| `VELOCITY_HIGH_FPS` | 20.0 fps | `constants.py` |
| `VELOCITY_WARN_FPS` | 12.0 fps | `constants.py` |
| Collinear merge tolerance | 5° (dot ≈ 1.0 ± 0.05) | `model_space.py:1157` |
| Backtrack snap distance | 5 px | `model_space.py:1103` |
| Backtrack overlap tolerance | 10 px perpendicular | `model_space.py:1089` |
| 4th-branch perpendicular tolerance | ~10° (\|dot\| < 0.17) | `model_space.py:1055` |
| Through-run collinear tolerance | ~18° (dot < -0.95) | `model_space.py:1040` |
| 45° elbow angle tolerance | ±10° from 135° | `model_space.py:1222` |
| Wye stub length | 304.8 mm (1 ft) | `model_space.py:1231` |

---

## 14. File Map

| File | Lines | Role |
|---|---|---|
| `firepro3d/pipe.py` | ~672 | Pipe class, properties, display, labels, diameter tables |
| `firepro3d/node.py` | ~330 | Node class, connections, elevation, snap |
| `firepro3d/fitting.py` | ~429 | Fitting type determination, SVG symbols, alignment |
| `firepro3d/model_space.py` | ~7,195 | Placement tool, splitting, extension, validation, add/delete |
| `firepro3d/sprinkler_system.py` | ~1,341 | Network container (flat lists) |
| `firepro3d/hydraulic_solver.py` | ~21,591 | Flow/pressure calculations, BFS tree |
| `firepro3d/scene_io.py` | ~639 | JSON serialization/deserialization |
| `firepro3d/view_3d.py` | ~75,151 | 3D cylinder/line rendering |
| `firepro3d/constants.py` | ~62 | Colors, velocity thresholds, NFPA limits |
| `firepro3d/water_supply.py` | ~5,022 | Supply curve, static/residual pressure |
| `main.py` | ~4,200 | Ribbon button, template persistence, mode setup |

---

## 15. Architectural Observations

1. **No automatic pipe routing** — all pipes are manually placed segment by segment. The only "automatic" behaviors are geometry corrections (collinear merge, 45°→wye, splitting).

2. **Tree topology assumed** — the hydraulic solver builds a BFS spanning tree from the supply node. Loops are not detected or handled.

3. **Flat storage model** — `SprinklerSystem` stores nodes and pipes as flat lists. There is no hierarchical grouping (e.g., by branch line, cross main, feed main).

4. **Implicit graph** — network connectivity is derived at runtime from `pipe.node1`/`node2` references. There is no explicit adjacency structure maintained.

5. **Template as property clipboard** — the template pipe is a full `Pipe` instance used purely for property transfer. It is never rendered or added to the scene.

6. **Elevation is node-owned** — pipes don't have independent elevations; they derive Z from their endpoint nodes. The pipe's `ceiling_level`/`ceiling_offset` properties exist for template propagation and serialization, not runtime positioning.

7. **Fitting determination is angle-based** — uses dot products between normalized pipe direction vectors, with hardcoded angular tolerances. No consideration of pipe diameter or physical fitting geometry.

---

## 16. Bug & Enhancement Summary

### 16.1 Bugs to Fix

| # | Issue | Severity | Location |
|---|---|---|---|
| B1 | Riser auto-build bypasses `add_pipe()` — skips display defaults, labels, geometry, fittings | High | `model_space.py:4256–4264` |
| B2 | `_create_vertical_connection()` bypasses `add_pipe()` partially | High | `model_space.py:1348–1358` |
| B3 | `_split_vertical_pipe()` bypasses `add_pipe()` | High | `model_space.py:1429–1442` |
| B4 | `find_nearby_node()` Z-blind — wrong node at risers causes 5+ downstream bugs | High | `model_space.py:856` |
| B5 | `snap_point_45` uses `pipes[0]` not contextual pipe — grid misaligned when branching | Medium | `node.py:178` |
| B6 | Riser node move doesn't move Z-stacked siblings | Medium | `model_space.py:7134` |
| B7 | All geometry checks use 2D vectors — false positives on multi-level overlap | High | Multiple locations |
| B8 | Preview label formats diameter as raw key, not display format | Low | `model_space.py:3557–3561` |
| B9 | Preview length ignores Z difference | Low | `model_space.py:3554` |
| B10 | Fitting `determine_type` broken for through-risers (2 vertical pipes) | Medium | `fitting.py:149–154` |
| B11 | Pipe labels show 2D length, not 3D | Medium | `pipe.py:169` |
| B12 | `update_elevations()` doesn't refresh pipe labels (latent until B11 fixed) | Low | `level_manager.py:327` |

### 16.2 Enhancements

| # | Enhancement | Priority |
|---|---|---|
| E1 | New fitting types: `tee_vertical`, `cross_vertical` + SVGs | Medium |
| E2 | Collinear extension for vertical pipes (3D vectors) | Medium |
| E3 | Preview pipe shows elevation info when N1 Z ≠ N2 Z | Low |

### 16.3 Implementation Order (Recommended)

1. **B7** — 3D vectors everywhere (unblocks B4, B10, E2, and makes B5 fix cleaner)
2. **B1 + B2 + B3** — Route all pipe creation through `add_pipe()` (single pattern fix)
3. **B4** — `z_hint` on `find_nearby_node()` (unblocks B6)
4. **B5** — Contextual snap reference
5. **B6** — Riser column move
6. **B10 + E1** — Fitting matrix + new SVGs
7. **B11 + B12** — 3D labels + elevation refresh
8. **B8 + B9** — Preview fixes
9. **E2** — Vertical collinear extension
10. **E3** — Preview elevation info
