---
status: current          # documents as-built behaviour plus the bugs still open (§16.1)
last-verified: 2026-11-05  # pipe polish Account: §2.2 / §2.3 / §3.2 / §3.3 / §4.4 / §6.3 / §6.4 / §9.1 / §13 / §16 only, rest not re-audited
verified-commit: ff2b8636  # pipe polish merge on main (v0.90.0)
applies-to:
  - firepro3d/pipe.py
  - firepro3d/node.py
  - firepro3d/fitting.py
  - firepro3d/equivalent_length.py
  - firepro3d/pipe_network_controller.py
  - firepro3d/pipe_target_marker.py
  - firepro3d/model_space.py            # shells, press dispatch, SNAP_RADIUS
  - firepro3d/sprinkler_system.py
  - firepro3d/constants.py
---

# Pipe Placement Methodology — Specification

> **Status:** Revised specification (documents current implementation + required fixes)
> **Source files:** `model_space.py`, `pipe.py`, `node.py`, `fitting.py`, `sprinkler_system.py`, `constants.py`
> **Date:** 2026-04-04
> **Pipe polish verified 2026-11-05** (`ff2b8636`, v0.90.0): §2.2 node X / Y / Z, §2.3 fitting matrix and the plain-fitting rule, §3.2 / §3.3 pickup, split and target marker, §4.4, §6.3, §6.4 (panel edit moves the stack), §9.1 riser and fitting symbol sizes, masking, §13 and the §16 bug table were re-checked against code; B1, B2, B4, B10 are fixed there, B3 and the drag / Move half of B6 stay open. Other sections not re-audited.
> **Labels (§ Labels, §9.2 preview) verified 2026-11-01** (`0924bcd6`, SB4a): the placed label is now an annotation block; B11 fixed. Other sections unchanged by SB4a.
> **Revision:** 2 (post grill session)
> **§4.1 verified 2026-08-20** (`25c7edb`): B5 fixed — contextual coplanar-pipe 45° reference. Other sections still describe required fixes, not shipped code.
> **§4.1 typed-entry verified 2026-09-03** (`b5ddacf`): T19 — pipe is a Dynamic Input HUD client (relative/absolute Angle; `pipe_network_controller.py:_commit_pipe_at`). See `align-placement.md §4a`.

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
| Line Type | enum | `"Branch"` | Branch (75 mm width), Main (150 mm width) |
| Colour | enum | `"Red"` | Black, White, Red, Blue, Grey |
| Phase | enum | `"New"` | New, Existing, Demo |
| Show Label | enum | `"True"` | True, False |

**Auto-assignment rule:** Diameters ≥ 3" automatically set Line Type to `"Main"`.

**Per-node template elevations** (used only during placement):

- `node1_ceiling_level`, `node1_ceiling_offset`
- `node2_ceiling_level`, `node2_ceiling_offset`

On the template panel the offset rows read **N1 Offset** / **N2 Offset** (meta `label`; the keys `"N1 Ceiling Offset"` / `"N2 Ceiling Offset"` are unchanged).

### 2.2 Node (`firepro3d/node.py`)

| Attribute | Type | Default | Description |
|---|---|---|---|
| `x_pos`, `y_pos` | `float` | — | Position at creation, rewritten by the panel X / Y edit only. **No reader**: `scenePos()` is the live position (a drag does not update them) |
| `z_pos` | `float` | — | 3D elevation = `level.elevation + ceiling_offset` |
| `ceiling_level` | `str` | `"Level 1"` | Ceiling reference level |
| `ceiling_offset` | `float` | `-50.8` mm | Offset from the ceiling level's elevation (not necessarily below a ceiling). Panel label **Offset**, property key `"Ceiling Offset"` |
| `pipes` | `list[Pipe]` | `[]` | Connected pipes (**max 4**) |
| `sprinkler` | `Sprinkler \| None` | `None` | Attached sprinkler head |
| `fitting` | `Fitting` | — | Auto-created, always present |
| `RADIUS` | `int` | `13` | Visual radius (scene units) |

**Node panel rows** (`Node.get_properties()`; a sprinkler node shows the sprinkler's own rows, which delegate to the same node — [`sprinkler-system-components.md`](sprinkler-system-components.md) §4.4):

| Row | Edit | Effect |
|---|---|---|
| Ceiling Level | level combo | Recomputes `z_pos`; this node only |
| **Offset** (key `"Ceiling Offset"`) | length | Recomputes `z_pos`; this node only. The old key, `"Elevation"`, `"Elevation Offset"` and the label `"Offset"` are all accepted by `set_property` (file load, aliases) |
| **X**, **Y** | length, mm | Moves the node's whole riser stack (§6.4). **Y is up-positive** on the panel: scene Y is down-positive and `CAD_Math.flip_y` is the one conversion ([`units-and-formatting.md`](units-and-formatting.md) §4.2) |
| **Z** | length, mm | Absolute elevation. Typing solves the **Offset** against the node's **kept** Ceiling Level and moves **this node only** (attached pipes slope; no level change). A no-change commit does nothing |

X / Y / Z carry `single_only`: they show on a single selection and are skipped on a multi-selection and in a Pipe's inline "Node 1 / Node 2" sections ([`property-panel.md`](property-panel.md) §3.1). A committed edit requests one undo step (`request_undo_push`). The read-only **Absolute Elev.** row survives only in the Pipe's Node 1 / Node 2 sections.

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
| 1 or more, all one direction (up **or** down) | 0 or 1 | — | `"elbow_up"` / `"elbow_down"` (no `cap_up` / `cap_down` type exists) |
| 1 or more, all one direction | 2 or more | — | `"tee_up"` / `"tee_down"` (no angle test) |
| both (a pipe up **and** a pipe down: a *through* node) | 0 | Through-riser, no branch | `"riser_through"` |
| both | 1 | Through-riser with branch | `"tee_vertical"` |
| both | 2 or more | Through-riser with two or more branches | `"cross_vertical"` |

A pipe is *vertical* when its ends share XY within 10 scene units and differ in `z_pos` (`Fitting._is_vertical`); *through* is `Fitting.is_through(node)`. Vertical rows are tested before the horizontal rows, so a node with any vertical pipe never gets a plain type. Direction `up` / `down` is read from the first vertical pipe's far end (`vertical[0]`) only when the node is not a through node.

> ~~**BUG:** `determine_type()` only inspects `vertical[0]`, ignoring the second vertical pipe.~~ **Fixed (B10, pipe polish, 2026-11-05):** a through node returns `riser_through` / `tee_vertical` / `cross_vertical`. **No new SVG was drawn**: all three types share `fitting_symbols/riser_passthrough.svg` (`Fitting.SYMBOLS`), the same file the vertical pipe's own riser symbol uses (§9.1).

**Hydraulics read `fitting.type`** (`hydraulic_solver.py` -> `equivalent_length.FITTING_TYPE_MAP`): `riser_through` -> the `cap` row (0 ft), `tee_vertical` -> `tee_flow_turn`, `cross_vertical` -> `cross_flow_turn`. The hydraulic report names them in `_FITTING_NOTE_LABELS`. Table owner: [`hydraulic-solver-and-reporting.md`](hydraulic-solver-and-reporting.md) §10.2.

**Plain fittings never draw (D1).** The six *plain* types, `Fitting.PLAIN_TYPES` = `cap`, `45elbow`, `90elbow`, `tee`, `wye`, `cross`, have no plan symbol, on screen or on a sheet, while `Fitting.SHOW_PLAIN_SYMBOLS` is `False` (its default). `Fitting.draws_symbol()` is the one rule; setting the flag `True` brings every plain symbol back. The types, the SVG assets, `align_fitting`, hydraulics and `Pipe` cap-end handling are untouched by the rule: only `symbol.setVisible` follows it. Sheets (`paper_display`) restyle only a fitting whose symbol is visible, so a hidden plain symbol leaves no pixels there either. The Display Manager Fitting row (visible, colour, scale) cannot bring a hidden symbol back, because it is the second gate (`Fitting._display_visible`) after `draws_symbol()`; it governs only the symbols that still draw: `elbow_up` / `elbow_down`, `tee_up` / `tee_down` and the three through types. A user wants the plain symbols back later: change the flag, do not delete code.

Which of those drawn symbols shows is a second rule (bare riser ends, one symbol per stack per view, sprinkler nodes), owned by [`sprinkler-system-components.md`](sprinkler-system-components.md) §6.3; the pipe-side riser symbol is §9.1 below.

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

**Entry point:** `Model_Space._press_pipe()` forwards to `PipeNetworkController.press_pipe`

```
User clicks on canvas
    │
    ├─ resolve_pipe_target(snapped, snapped, z_hint=template_z)   (§3.2.1)
    │   → ("node", Node) | ("pipe", Pipe) | ("none", None)
    │   A Tab-selected candidate (§3.2.1) replaces the node result.
    │
    ├─ If an existing node was found and len(node.pipes) >= 4:
    │   └─ BLOCK: "Connection Limit" warning → return
    │
    ├─ If no node was found and the click hit a Pipe:
    │   └─ split_pipe() → creates new junction node at the click's projection
    │      onto the pipe (splits original pipe into two segments)
    │
    ├─ Else:
    │   └─ the found node, or find_or_create_node() (fixed SNAP_RADIUS) → a new node
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

#### 3.2.1 Target resolution, pickup and the target marker (pipe polish D3 / D4 / D5)

One resolver, `PipeNetworkController.resolve_pipe_target(node_pos, pipe_pos, z_hint, cached)`, answers "what will a click here do" for **both** the mouse move (marker) and the press, so the two cannot disagree. `node_pos` is the point tested for node pickup (the 45-snapped end on the second click), `pipe_pos` the point tested for a pipe hit (the snapped cursor); on the first click both are the snapped cursor. It returns, in this order:

1. **`("node", Node)`** — the nearest node inside the **pickup radius**, `pick_radius()`: the SNAP aperture (`SNAP_TOLERANCE_PX`, 15 px by default, user-tunable) converted to scene units at the *visible* view's zoom, **but never under `SNAP_RADIUS` (10 scene units = 10 mm)**. So pickup is 15 screen pixels at any zoom and never less than 10 mm. The chain's own start node is never a target. Candidates are ranked **nearest first**; nodes within `SNAP_RADIUS` of the nearest count as one spot (a riser stack can stand slightly off plumb) and are ordered by closeness of `z_pos` to the template's target Z, the rest follow by distance. A sprinkler whose symbol box contains the cursor is a candidate at its true centre distance: it no longer outranks a nearer plain node. On the move path the node is the **Tab-selected** candidate (what the press connects to); Tab cycles the same list. The aperture constant and the ranking are recorded from the snap side in [`snapping-engine.md`](snapping-engine.md) §14.6.
2. **`("pipe", Pipe)`** — else a visible pipe under `pipe_pos`, tested by `PipeNetworkController._pipe_at` with the same rule as `Pipe.shape()` (`Pipe.hit_width()`: a flat-capped stroke at least 16 screen px wide; a run shorter than 1 scene unit, i.e. a vertical pipe, is a disk of `_RISER_SIZE_MM / 2` radius). A fully transparent or hidden pipe is not hit; on equal Z the later-added pipe wins. A hit on a **vertical** pipe resolves to its end node nearest the template Z (a riser cannot be split in plan), so it returns `("node", ...)`.
3. **`("none", None)`**.

`_pipe_at` is a plain loop over `sprinkler_system.pipes` with a bounding-box reject; the `scene.items` query it replaced cost about 20 ms a move on 1500 pipes. The target marker is held to a **5 ms per move** budget (design ruling 2026-11-05; no test asserts it).

**Press.** A resolved node connects to it (the 4-pipe limit and elevation-mismatch checks of §3.2 / §3.3 still apply). A resolved pipe **splits** it at the projection of the click onto the pipe (`split_pipe`) and connects to the new node: no loose node is left beside a pipe (D3). `none` creates a new node (`find_or_create_node`, fixed `SNAP_RADIUS`). Callers that keep the fixed `SNAP_RADIUS` lookup and ignore the Tab list: paste merge, **typed** length / angle entry (`_commit_pipe_at(..., typed=True)`), `add_node`, `find_or_create_node`, and `split_pipe`'s own near-end shortcut (§4.4). The `SNAP_RADIUS` floor in `pick_radius()` keeps each of those a subset of what the marker already resolved.

**Target marker (D5).** `PipeTargetMarker` (`scene.pipe_target_marker`, `pipe_target_marker.py`) is a screen-sized glyph (half-size 8 px, ignores view transforms, Z 200, never pickable, not a snap target):

| Kind | Glyph | Colour (`SNAP_COLORS`) | Meaning | Placed at |
|---|---|---|---|---|
| `node` | ring | `midpoint` green | the click **connects to** this node | the node |
| `pipe` | diamond | `quadrant` orange | the click **splits** this pipe | the projection of `node_pos` onto the pipe |
| `none` | hidden | — | the click creates a new node | — |

It follows the cursor on every pipe-mode mouse move, before and after the first click, and re-resolves when Tab cycles candidates. It hides on Esc (`cancel_placement`), on the double-click that ends a chain, and on any mode change (`set_mode`), and returns on the next move.

**Plain-node selection (D6) is the same width.** Outside the pipe tool a plain node's hit shape is a disk of `NODE_PICK_PX` (12) screen px at the visible zoom, capped at a third of its shortest attached run so a short pipe stays reachable; the click ring shows when selected and nothing extra is drawn at rest. HALO ranking of that disk: [`selection-mode.md`](selection-mode.md) §4.1. The Sprinkler and Water Supply tools do not use the resolver: they take the item under the click (Sprinkler, then Node, then Pipe), so a click within 12 px of a node lands on that node at any zoom and a click further out on a pipe splits it where clicked ([`sprinkler-system-components.md`](sprinkler-system-components.md) §12.4).

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
    ├─ resolve_pipe_target(snapped_end, snapped, z_hint=template Z2)   (§3.2.1)
    │   ├─ node  → connect to it (a Tab-selected candidate wins; typed input skips this)
    │   ├─ pipe  → split_pipe() → junction at the projection of snapped_end
    │   └─ none  → find_or_create_node() (fixed SNAP_RADIUS)
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

Pipe endpoints snap to 45° increments **relative to a reference pipe**:

```
Increments: 0°, 45°, 90°, 135°, 180°, 225°, 270°, 315° (off the reference axis)
Soft-snap tolerance (no reference): SNAP_TOLERANCE_DEG = 7.5°
```

**Method:** `Node.snap_point_45(start, end, reference_pipe=None)` — snaps the drag
direction to the nearest 45° multiple **of the reference pipe's axis**, then
re-projects `end` at the original length. **Snap operates in 2D only** (canvas
input constraint).

The reference is the coplanar pipe whose *axis* is angularly closest to the
`start → end` drag direction (`Node._nearest_coplanar_pipe`) — **axis, not ray**,
so a pipe pointing away is an equally valid reference (0° and 180° are
equivalent). Coplanarity is `|Δz_pos| ≤ Z_COPLANAR_TOL`. Callers may override
the choice with an explicit `reference_pipe`.

A node whose only connections are risers has **no coplanar reference**, so
placement falls through to free movement with a soft snap within 7.5° of a 45°
multiple — rather than anchoring the grid to a riser's meaningless plan angle.
With exactly one coplanar pipe this is identical to the old behaviour; the
change only affects branching nodes and riser-only nodes.

**Typed relative-angle entry (Dynamic Input HUD, T19).** The same 45° grid is
reachable by typing Length + Angle in the HUD (governed by `align-placement.md
§4a`). From a **connected** node the Angle is **relative** to the reference pipe
(field labelled **"Rel A"**) and accepted **only at 45° multiples** — an off-grid
value is **rejected, never rounded** (rounding would silently choose a fitting
the user did not). From a **free** node the Angle is **absolute** and taken
**exactly** (no ±7.5° soft-snap — a typed value is intentional). The reference is
chosen at HUD-engage from the live preview direction and held for the session;
the typed endpoint is computed in `snap_point_45`'s own frame so typed and mouse
placement are byte-identical, and commit reuses the mouse's post-snap body
(`PipeNetworkController._commit_pipe_at`).

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

**Trigger:** A pipe-tool click that resolves to `("pipe", Pipe)` (§3.2.1): no node is within the pickup radius and a non-vertical pipe lies under the cursor. The same applies to a Sprinkler or Water Supply click on a pipe (§3.2.1, last paragraph).

**Action (`split_pipe()`):**
1. If click is near an existing endpoint (within the fixed `SNAP_RADIUS`, 10 scene units), return that node; the wider pickup of §3.2.1 has normally resolved such a click to a node before this runs
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

Pipes do not store ceiling data. Ceiling level and offset are **node-only** attributes. During pipe placement, the template's per-node attrs (`node1_ceiling_level`, `node1_ceiling_offset`, `node2_ceiling_level`, `node2_ceiling_offset`) drive elevation propagation, falling back to `DEFAULT_LEVEL` / `DEFAULT_CEILING_OFFSET_MM` when absent.

| Scenario | Direction | Behavior |
|---|---|---|
| New node created | Template per-node attrs → Node | Node gets template's per-node ceiling level/offset (or defaults) |
| Existing node selected | Node → Template per-node attrs | Template adopts node's existing elevation |
| Chain continuation | End node → Template Node 1 attrs | Next segment starts at previous end elevation |
| Default Node 2 | Copies Node 1 attrs | Horizontal pipe by default |

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

> ~~**BUG:** The "Riser" path manually constructs pipes.~~ **Fixed** for the Riser path (B1) and `_create_vertical_connection()` (B2): both use `add_pipe(n1, n2, template, _propagate_ceiling=False)` since they manage Z themselves. **Still open (B3):** `_split_vertical_pipe()` constructs its halves by hand (§16.1).

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

`find_nearby_node()` / `find_nearby_candidates()` snap uses XY distance only (correct — snap is a 2D canvas operation), within `SNAP_RADIUS` or an explicit `radius=` (the pipe tool passes `pick_radius()`, §3.2.1), filtered to the active view's Z range.

**Disambiguation when multiple nodes exist at the same XY (risers):** candidates are ranked **nearest first**; nodes within `SNAP_RADIUS` of the nearest are one spot and are ordered by the closeness of `z_pos` to `z_hint` (`_rank_candidates`). With no `z_hint` the nearest wins.

| Context | Tiebreaker |
|---|---|
| Pipe placement | Prefer node closest to template's target Z (`z_hint`) |
| Sprinkler placement | none: the Sprinkler tool calls `add_node` without a `z_hint`, so the nearest node wins |
| Paste merge | `paste_z` as `z_hint` |
| General selection | Prefer node on active level *(not re-audited 2026-11-05)* |

> ~~**BUG:** `find_nearby_node()` is Z-blind (B4).~~ **Fixed:** `z_hint` ordering as above (verified 2026-11-05). The pipe tool passes the template's target Z at both clicks; the Sprinkler tool does not (open: it can still pick the wrong node of a Z-stack).

### 6.4 Node Move Behavior with Risers

**Panel X / Y edit moves the stack (B6, partly fixed, pipe polish D7).** `Node._edit_position("X" | "Y", ...)` calls `Node.move_stack_to(x, y)`: every node joined to this one through vertical pipes (`Node.riser_stack()`, a walk over `Pipe._is_vertical()`) is shifted by the same delta, the stack's pipes and labels are re-derived and every fitting at the stack and its neighbours is updated. The pipe stays vertical and one undo step restores it. The Z edit and the Ceiling Level / Offset rows move **one node only** (§2.2).

> **BUG (still open, B6):** Dragging a riser node, or moving it with the Move tool (`Model_Space.move_items`, manipulator `bake_translate`), still moves only that one node. The other Z-stacked nodes stay in place, creating impossible diagonal pipe geometry. Filed in `todo_open.md` (P3); reuse `Node.riser_stack()`.

---

## 7. Pipe Creation (`add_pipe()`)

**Method:** `PipeNetworkController.add_pipe` (the `Model_Space.add_pipe` shell forwards to it)

```python
add_pipe(n1, n2, template=None, _propagate_ceiling=True, mint=True)
```

`mint` (SB2b): after the display defaults, a pipe created with `mint=True` receives the next Pipe Mark (so a template copy never keeps the source Mark); file load and undo restore pass `mint=False`, and a pipe split keeps the original Mark on its first half. Rules owned by `element-parameters.md` "Marks (SB2b)".

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
    - **With template:** Use per-node ceiling values (`node1_ceiling_level/offset`, `node2_ceiling_level/offset`), falling back to `DEFAULT_LEVEL` / `DEFAULT_CEILING_OFFSET_MM`
    - **Without template:** Apply `DEFAULT_LEVEL` / `DEFAULT_CEILING_OFFSET_MM` to both nodes
    - Recompute `z_pos` on both nodes

---

## 8. Pipe Deletion (`delete_pipe()`)

**Method:** `PipeNetworkController.delete_pipe` (shell on `Model_Space`)

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

**Labels** (when `Show Label == "True"`) -- drawn by the **PipeLabel System block** (SB4a;
contract, content, Tag row, Hide when empty, paper and persistence owned by
[`system-blocks.md`](system-blocks.md) section 8a; field keys / units / 3D `Length` by
[`element-parameters.md`](element-parameters.md)):
- The label is a `BoundLabelItem` (`Pipe.label`), an **independent top-level scene item**,
  not a child of Pipe, so it draws above nodes and fittings. Its Z is
  `max(Z_OVERLAY, pipe z + Z_LABEL_ABOVE_PIPE)` (`Pipe.sync_label_z`; `constants.py`)
- Positioned at the pipe midpoint, the whole label rotated to the pipe angle kept readable
- Hidden for vertical pipes (zero 2D projection) and when Show Label is off
- `Pipe.setVisible()` cascades visibility to the label
- Labels are **non-interactive** (not selectable, no hover)
- The text size is the block's authored printed size (annotative); the per-pipe
  `Label Size` property and the Display Manager Pipe font are **retired**

**Riser pass-through symbol** (vertical pipes):
- Vertical pipes (zero 2D extent) render a yin-yang / broken-pipe SVG symbol at their XY location
- SVG asset: `firepro3d/graphics/fitting_symbols/riser_passthrough.svg`
- Top-level scene item (`Pipe._riser_symbol`) at `Z_OVERLAY` (200) on creation, pinned just above its pipe by `Pipe.sync_riser_z` ([`view-relationships.md`](view-relationships.md) §7.3), non-interactive, tagged never-a-snap-target
- Fixed size: `Pipe._RISER_SIZE_MM` = **150 mm** scene units (halved from 300 mm by the 2026-11-05 smoke)
- Visibility rule: shown unless a *visible* endpoint node has another, non-vertical pipe **or** is a *through* node (`Fitting.is_through`). In both cases the node's fitting symbol already marks the riser. A riser end with no branches therefore shows only this pass-through symbol; in a stack with a branch at one end only, the branch node's elbow / tee symbol shows (`elbow_up` / `elbow_down` / `tee_up` / `tee_down`) and the pass-through hides.
- `Pipe.setVisible()` cascades to the riser symbol
- Vertical pipe `shape()` returns a circular hit area (**150 mm** diameter, the symbol size) so the riser is clickable for `split_pipe` operations and by `_pipe_at` (§3.2.1)

**Fitting symbol (drawn types only, §2.3):** its size (150 mm on a branch, about 212 mm on a main), which node of a riser stack draws it, and the bare-riser-end rule are owned by [`sprinkler-system-components.md`](sprinkler-system-components.md) §6.3 / §6.5. The pass-through rule above and those rules are complementary: a bare riser end shows only this section's pass-through symbol.

**Masking (a symbol is hollow).** A pipe stops at the edge of any fitting symbol drawn over it, so no ink shows through the symbol to the node. The rule is `Pipe._collect_clip_regions`: the clip circles (`Fitting.clip_region_scene`) of every node whose symbol is visible and either sits **higher** than the pipe's top end, or is **the pipe's own end node** (any elevation). The circle's radius is half the symbol's side (`symbol size x scale / 2`), whatever its rotation: a symbol turned to a diagonal branch has a wider scene bounding box, but the same circle. A hidden symbol (§2.3 plain types, bare riser ends, sprinkler nodes) clips nothing. The round end the paint adds on a mixed cap / non-cap pipe is skipped when it falls inside a clip.

> ~~**BUG:** `update_label()` shows 2D projected length~~ -- **fixed 2026-11-01 (SB4a)**: the label binds the 3D `Length` key.

> **BUG (current):** `update_elevations()` in LevelManager recomputes node Z positions but does not refresh pipe labels. Now that labels show 3D length, changing a level's elevation leaves labels stale.
>
> **FIX:** `update_elevations()` must call `pipe.update_label()` on all pipes after recomputing node Z positions.

**Fitting clipping:** see *Masking* above: pipes stop at the edge of fitting symbols drawn over them or at their own ends.

**Hit detection:** `shape()` method ensures pipes remain clickable — minimum 16 screen pixels wide regardless of zoom (`Pipe.hit_width()`, the one width `shape()` and the placement resolver share).

### 9.2 Preview Pipe (During Placement)

The preview pipe is rendered in `_move_pipe()` during mouse movement between clicks.

**Shows:**
- Colored dashed line from start node to cursor (styled from template)
- Preview label with diameter and length, in a fixed text height (`constants.PIPE_PREVIEW_LABEL_IN`; the placed label is the annotation block)

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
  "properties": {
    "Diameter": "2\"Ø", "Schedule": "Sch 40",
    "C-Factor": "120", "Material": "Galvanized Steel",
    "Line Type": "Branch", "Colour": "Red",
    "Phase": "New", "Show Label": "True"
  },
  "display_overrides": {}
}
```

A sparse `tag_block` key (the per-pipe label block id) is written only when set; a legacy `Label Size` property key is dropped on load ([`system-blocks.md`](system-blocks.md) section 8a).

> **Backward compatibility:** Old save files containing pipe-level `ceiling_level` / `ceiling_offset_mm` fields (or `"Ceiling Level"` / `"Ceiling Offset"` in the properties dict) are silently ignored on load.

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
| `SNAP_RADIUS` | 10 scene units (mm); fixed-radius node lookup, and the floor of the mouse pickup | `Model_Space.SNAP_RADIUS` |
| `SNAP_TOLERANCE_PX` | 15 px default, user-tunable; the mouse pickup aperture (§3.2.1) | `snap_engine.py` |
| `NODE_PICK_PX` | 12 px; plain node hit disk | `constants.py` |
| `Pipe._RISER_SIZE_MM` | 150 mm; riser pass-through symbol and vertical pipe pick disk | `pipe.py` |
| `Fitting.SHOW_PLAIN_SYMBOLS` | `False`; flip to bring back the plain fitting symbols | `fitting.py` |
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

| File | Role |
|---|---|
| `firepro3d/pipe.py` | Pipe class, properties, display, labels, diameter tables, riser symbol, masking |
| `firepro3d/node.py` | Node class, connections, elevation, snap, panel X / Y / Z rows, riser stack, pick disk |
| `firepro3d/fitting.py` | Fitting type determination, SVG symbols, alignment, plain-symbol rule, per-view symbol choice |
| `firepro3d/equivalent_length.py` | `Fitting.type` -> NFPA equivalent-length row |
| `firepro3d/pipe_network_controller.py` | Placement tool bodies, target resolver, pickup, splitting, extension, validation, add/delete |
| `firepro3d/pipe_target_marker.py` | Ring / diamond target marker (§3.2.1) |
| `firepro3d/model_space.py` | Dispatch forwarders and shells, `pipe_start_node`, press routing |
| `firepro3d/sprinkler_system.py` | Network container (flat lists) |
| `firepro3d/hydraulic_solver.py` | Flow/pressure calculations, BFS tree |
| `firepro3d/scene_io.py` | JSON serialization/deserialization |
| `firepro3d/view_3d.py` | 3D cylinder/line rendering |
| `firepro3d/constants.py` | Colors, velocity thresholds, NFPA limits |
| `firepro3d/water_supply.py` | Supply curve, static/residual pressure |
| `main.py` | Ribbon button, template persistence, mode setup |

---

## 15. Architectural Observations

1. **No automatic pipe routing** — all pipes are manually placed segment by segment. The only "automatic" behaviors are geometry corrections (collinear merge, 45°→wye, splitting).

2. **Tree topology assumed** — the hydraulic solver builds a BFS spanning tree from the supply node. Loops are not detected or handled.

3. **Flat storage model** — `SprinklerSystem` stores nodes and pipes as flat lists. There is no hierarchical grouping (e.g., by branch line, cross main, feed main).

4. **Implicit graph** — network connectivity is derived at runtime from `pipe.node1`/`node2` references. There is no explicit adjacency structure maintained.

5. **Template as property clipboard** — the template pipe is a full `Pipe` instance used purely for property transfer. It is never rendered or added to the scene.

6. **Elevation is node-owned** — pipes don't store ceiling data at all; they derive Z entirely from their endpoint nodes. The template carries per-node ceiling attrs (`node1_ceiling_level/offset`, `node2_ceiling_level/offset`) for propagation during placement.

7. **Fitting determination is angle-based** — uses dot products between normalized pipe direction vectors, with hardcoded angular tolerances. No consideration of pipe diameter or physical fitting geometry.

---

## 16. Bug & Enhancement Summary

### 16.1 Bugs to Fix

| # | Issue | Severity | Location |
|---|---|---|---|
| B1 | ~~Riser auto-build bypasses `add_pipe()`~~ — **fixed**: the elevation-mismatch Riser path (`resume_elev_mismatch`) builds its vertical pipe through `add_pipe(..., _propagate_ceiling=False)`; the only direct `Pipe(n1, n2)` construction of a placed pipe left outside `add_pipe` is B3 | High | `PipeNetworkController` |
| B2 | ~~`_create_vertical_connection()` bypasses `add_pipe()` partially~~ — **fixed**: both its pipes go through `add_pipe` | High | `PipeNetworkController._create_vertical_connection` |
| B3 | `_split_vertical_pipe()` bypasses `add_pipe()` — **still open**: it builds each half with `Pipe(na, nb)` + `sprinkler_system.add_pipe` + `addItem`, then `set_pipe_display()` and a Mark mint on the n2 half. It skips `apply_category_defaults`, `update_label` / `update_geometry`, the forced visibility and the neighbour-wide fitting update (only the mid node and the two ends update) | High | `PipeNetworkController._split_vertical_pipe` |
| B4 | ~~`find_nearby_node()` Z-blind~~ — **fixed**: `z_hint` orders a stack (§6.3); the Sprinkler tool still passes none | High | `PipeNetworkController.find_nearby_node` |
| B5 | ~~`snap_point_45` uses `pipes[0]` not contextual pipe — grid misaligned when branching~~ — **fixed 2026-08-17** (`25c7edb`): reference is now the coplanar pipe whose axis is angularly nearest the drag direction, with an explicit `reference_pipe` override; riser-only nodes fall through to free soft-snap (§4.1) | Medium | `Node.snap_point_45` |
| B6 | Riser node move doesn't move Z-stacked siblings — **partly fixed**: the panel X / Y edit moves the whole stack (§6.4); a drag and the Move tool still move one node (open, P3) | Medium | `Node.move_stack_to`; drag / Move: `Model_Space.move_items` |
| B7 | All geometry checks use 2D vectors — false positives on multi-level overlap | High | Multiple locations |
| B8 | Preview label formats diameter as raw key, not display format | Low | `model_space.py:3557–3561` |
| B9 | Preview length ignores Z difference | Low | `model_space.py:3554` |
| B10 | ~~Fitting `determine_type` broken for through-risers (2 vertical pipes)~~ — **fixed** (pipe polish, 2026-11-05): `riser_through` / `tee_vertical` / `cross_vertical` (§2.3), with corrected equivalent lengths | Medium | `Fitting.determine_type` |
| B11 | ~~Pipe labels show 2D length, not 3D~~ -- **fixed 2026-11-01** (SB4a) | Medium | -- |
| B12 | `update_elevations()` doesn't refresh pipe labels (latent until B11 fixed) | Low | `level_manager.py:327` |

### 16.2 Enhancements

| # | Enhancement | Priority |
|---|---|---|
| E1 | ~~New fitting types: `tee_vertical`, `cross_vertical` + SVGs~~ — types built (plus `riser_through`); **no new SVGs** (all three reuse `riser_passthrough.svg`) | Medium |
| E2 | Collinear extension for vertical pipes (3D vectors) | Medium |
| E3 | Preview pipe shows elevation info when N1 Z ≠ N2 Z | Low |

### 16.3 Implementation Order (Recommended)

1. **B7** — 3D vectors everywhere (unblocks B4, B10, E2, and makes B5 fix cleaner)
2. **B1 + B2 + B3** — Route all pipe creation through `add_pipe()` (single pattern fix) — B1, B2 done; **B3 open**
3. ~~**B4** — `z_hint` on `find_nearby_node()` (unblocks B6)~~ — done
4. ~~**B5** — Contextual snap reference~~ — **done 2026-08-17** (`25c7edb`)
5. **B6** — Riser column move (panel edit done; drag / Move open)
6. ~~**B10 + E1** — Fitting matrix + new SVGs~~ — done 2026-11-05 (types only, no new SVGs)
7. ~~**B11**~~ done (SB4a); **B12** — elevation refresh
8. **B8 + B9** — Preview fixes
9. **E2** — Vertical collinear extension
10. **E3** — Preview elevation info
