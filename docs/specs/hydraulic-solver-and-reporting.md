# Hydraulic Solver & Reporting Specification

**Status:** Draft (D2/D3/D6 resolved 2026-04-29, D8 withdrawn 2026-04-30)  
**Date:** 2026-04-30  
**Scope:** Document current behavior + flag divergences with migration paths  
**Depends on:** [Sprinkler System Components Spec](sprinkler-system-components.md)

---

## Table of Contents

1. [Goal](#1-goal)
2. [Motivation](#2-motivation)
3. [Architecture](#3-architecture)
4. [Algorithm — 4-Phase Hazen-Williams Analysis](#4-algorithm--4-phase-hazen-williams-analysis)
5. [Formulas — NFPA 13 §22.4.2](#5-formulas--nfpa-13-2242)
6. [HydraulicResult](#6-hydraulicresult)
7. [Network Validation](#7-network-validation)
8. [Node Numbering](#8-node-numbering)
9. [Report Widget](#9-report-widget)
10. [Equivalent Pipe Length Reference](#10-equivalent-pipe-length-reference)
11. [On-Scene Overlay](#11-on-scene-overlay)
12. [Divergences & Migration Paths](#12-divergences--migration-paths)
13. [Testing Strategy](#13-testing-strategy)
14. [Acceptance Criteria](#14-acceptance-criteria)
15. [Verification Checklist](#15-verification-checklist)

---

## 1. Goal

Document the hydraulic solver and reporting subsystem: the Hazen-Williams pipe-network analysis algorithm, supply curve evaluation, result visualization, and report generation. Establish the authoritative reference for calculation methodology, formula constants, network validation rules, and report format. Flag divergences from NFPA 13 compliance with prioritized migration paths.

## 2. Motivation

The hydraulic solver is the core analytical output of FirePro3D — it determines whether a sprinkler system design meets NFPA 13 water supply requirements. The report is the primary deliverable for AHJ (Authority Having Jurisdiction) submissions. Documenting the algorithm enables:

- Verification against hand calculations and competing tools
- Confidence that formula constants match NFPA 13 §22.4.2
- Clear identification of gaps (equivalent lengths, hose stream, loop support)
- Foundation for future enhancements (looped networks, multi-system)

## 3. Architecture

### 3.1 Execution Flow

```
┌─────────────────────────────────────────────────────┐
│  MainWindow.run_hydraulics()                        │
│    ↓ design_area_sprinklers (or None = all)         │
│  Model_Space.run_hydraulics()                       │
│    ↓ SprinklerSystem + ScaleManager                 │
│  HydraulicSolver.solve()                            │
│    Phase 1: Flow assignment (leaves → supply)       │
│    Phase 2: Required pressure (leaves → supply)     │
│    Phase 3: Supply curve check                      │
│    Phase 4: Actual pressure (supply → leaves)       │
│    ↓ HydraulicResult                                │
│  HydraulicReportWidget.populate()                   │
│    Tab 1: Summary                                   │
│    Tab 2: Node Summary Table                        │
│    Tab 3: Hydraulic Graph                           │
│  Model_Space: badge overlay + pipe hf heatmap       │
└─────────────────────────────────────────────────────┘
```

### 3.2 Interfaces Consumed

| Interface | Provider | Consumer |
|---|---|---|
| `Pipe.get_inner_diameter()` | Pipe schedule tables (sprinkler spec §5.3) | Friction loss formula |
| `Pipe.get_length_ft(sm)` | Pipe 3D geometry + ScaleManager | Friction loss per segment |
| `Sprinkler._properties["K-Factor"]` | SprinklerRecord (sprinkler spec §4) | Sprinkler flow: Q = K√P |
| `Sprinkler._properties["Min Pressure"]` | SprinklerRecord (sprinkler spec §4) | Leaf node pressure initialization |
| `WaterSupply` properties | WaterSupply entity (sprinkler spec §10) | Supply curve + hose stream |
| `SprinklerSystem.supply_node` | Container (sprinkler spec §9) | Network traversal root |
| `SprinklerSystem.nodes/pipes/sprinklers` | Container | Adjacency construction |
| `ScaleManager.is_calibrated`, `pixels_per_mm` | ScaleManager | Length conversion |

### 3.3 Design Area Selection

Design area sprinkler selection is a pass-through from the sprinkler components spec (§11):
- If `active_design_area` exists → use its sprinkler list
- Otherwise → use all sprinklers in the system

The solver accepts a `design_sprinklers` list parameter and does not participate in selection logic.

---

## 4. Algorithm — 4-Phase Hazen-Williams Analysis

### 4.1 Prerequisites

Before solving, the following guards are checked (in order):

| Guard | Condition | Action |
|---|---|---|
| G1 | `supply_node is None` | Fail: "No water supply node placed on the drawing." |
| G2 | `design_sprinklers` empty | Fail: "No sprinklers in the design area." |
| G3 | `system.nodes` empty | Fail: "No pipe network nodes found." |
| G4 | Supply not connected to network | Fail: "Water supply node is not connected to the pipe network." |
| G5 | No reachable design sprinklers | Fail: "None of the design sprinklers are connected to the supply node." |

Failure at any guard returns a `HydraulicResult` with `passed=False` and a diagnostic message.

### 4.2 Network Construction

`_build_adjacency()` builds an adjacency dict: `{node: [(pipe, neighbour_node), ...]}` from all pipes in the system. Pipes with `None` node references are skipped.

`_bfs_tree(supply_node, adjacency)` traverses from the supply node and produces:
- `parent_node[n]` — BFS parent of node n
- `parent_pipe[n]` — pipe connecting n to its parent
- `children[n]` — list of child nodes
- `bfs_order` — nodes in BFS traversal order (supply first)

**Constraint:** Tree topology only. If the network contains loops, some pipes are silently excluded from the BFS tree. See [Divergence D1](#12-divergences--migration-paths).

### 4.3 Phase 1 — Flow Assignment (POST-ORDER: leaves → supply)

Each design sprinkler is assigned its minimum flow:
```
Q_sprinkler = K × √P_min
```

Flows accumulate from leaves to supply by processing `bfs_order` in reverse:
```
pipe_flow[pipe_to_parent] = node_own_demand + Σ(child pipe flows)
```

Where `node_own_demand` is the sprinkler flow if the node has a design sprinkler, otherwise 0.

`total_demand` = sum of pipe flows in pipes directly connected to supply's children.

### 4.4 Phase 2 — Required Pressure (POST-ORDER: leaves → supply)

Starting from leaf sprinkler nodes (initialized to `P_min`), compute the minimum pressure required at each upstream node:

```
P_required_at_parent = P_required_at_child + hf + h_e
```

Where:
- `hf` = friction loss for the pipe between child and parent
- `h_e` = elevation correction: `0.433 × (child.z_pos - parent.z_pos) / 304.8`

At multi-branch junctions, the **most-demanding branch governs**:
```
P_required[parent] = max(P_required[parent], P_required_from_this_branch)
```

Final supply pressure requirement includes gauge elevation correction:
```
required_pressure = P_required[supply_node] + 0.433 × supply_ws.elevation
```

**This is the primary output** — the required pressure at each node tells the designer what the system needs.

### 4.5 Phase 3 — Supply Check

Evaluate supply curve at total demand plus hose stream allowance:
```
Q_check = total_demand + hose_stream_allowance
P_available = P_static - (P_static - P_residual) × (Q_check / Q_test)^1.85
```

**Pass criterion:** `P_available ≥ required_pressure`

If failed: message reports needed vs available pressure and flow.

### 4.6 Phase 4 — Actual Pressure (PRE-ORDER: supply → leaves)

Propagate actual available pressure forward from supply:
```
P_actual[supply] = P_available - supply_elevation_correction
P_actual[child] = P_actual[parent] - hf - h_e
```

Compute velocity for each pipe (informational):
```
v = Q × 0.4085 / d²
```

Post-check: verify each design sprinkler receives at least `P_min` (0.05 psi tolerance). If not, mark `passed = False` with a per-sprinkler warning.

---

## 5. Formulas — NFPA 13 §22.4.2

### 5.1 Friction Loss (Hazen-Williams)

```
hf [psi] = 4.52 × Q^1.852 / (C^1.852 × d^4.87) × L
```

| Symbol | Units | Source |
|---|---|---|
| Q | gpm | Accumulated pipe flow (Phase 1) |
| C | dimensionless | Hazen-Williams coefficient (Pipe.C-Factor, material-derived) |
| d | inches | Inside diameter (Pipe.get_inner_diameter()) |
| L | feet | Total equivalent length: physical + fitting equivalents (supply node fittings excluded) |

`L = L_physical + equiv(node1_fitting, diameter) + equiv(node2_fitting, diameter)`, where `equiv()` looks up NFPA 13 Table 22.4.3.1.1 via `equivalent_length.py`. Supply node fittings contribute 0 (the supply test data captures losses up to that point). Returns 0 if Q ≤ 0, d ≤ 0, or C ≤ 0.

### 5.2 Elevation Correction

```
h_e [psi] = 0.433 × Δz_ft
```

| Sign | Meaning |
|---|---|
| Δz positive (child higher than parent) | Water flows uphill → pressure lost |
| Δz negative (child lower than parent) | Water flows downhill → pressure gained |

Conversion: `Δz_ft = (child.z_pos - parent.z_pos) / 304.8` (mm → ft)

### 5.3 Sprinkler Flow

```
Q [gpm] = K × √P
```

| Symbol | Units | Source |
|---|---|---|
| K | gpm/√psi | Sprinkler K-factor from database |
| P | psi | Pressure at sprinkler node |

### 5.4 Velocity (informational)

```
v [fps] = Q × 0.4085 / d²
```

| Symbol | Units | Source |
|---|---|---|
| Q | gpm | Pipe flow |
| d | inches | Inside diameter |

### 5.5 Supply Curve (NFPA power law)

```
P_available = P_static - (P_static - P_residual) × (Q / Q_test)^1.85
```

Two-point curve from fire department flow test data:
- Point 1: (0 gpm, P_static psi)
- Point 2: (Q_test gpm, P_residual psi)

On a Q^1.85 X-axis, this renders as a straight line. Clamped to `max(P, 0.0)`.

Returns P_static if Q_test ≤ 0 or Q_demand ≤ 0.

---

## 6. HydraulicResult

Dataclass returned by `HydraulicSolver.solve()`:

| Field | Type | Description |
|---|---|---|
| `node_pressures` | dict[Node, float] | Actual working pressure at each node (psi) — Phase 4 output. Secondary display value. |
| `pipe_flows` | dict[Pipe, float] | Flow through each pipe (gpm) — Phase 1 output |
| `pipe_velocity` | dict[Pipe, float] | Velocity in each pipe (fps) — Phase 4 output |
| `pipe_friction_loss` | dict[Pipe, float] | Friction loss per pipe (psi) — Phase 4 output |
| `required_node_pressures` | dict[Node, float] | Minimum required pressure at each node (psi) — Phase 2 output. **Primary display value.** |
| `total_demand` | float | Sprinkler demand at supply (gpm) — Phase 1 output |
| `hose_stream_gpm` | float | Hose stream allowance (gpm) — added to demand at supply check only, not to pipe flows |
| `required_pressure` | float | Required pressure at supply node (psi) — Phase 2 output |
| `supply_pressure` | float | Available pressure from supply curve at `total_demand + hose_stream_gpm` (psi) — Phase 3 output |
| `passed` | bool | True if `supply_pressure ≥ required_pressure` |
| `messages` | list[str] | Warnings, errors, summary messages |
| `node_numbers` | dict[Node, int] | BFS-order sequential numbers (major nodes only) |
| `node_labels` | dict[Node, str] | Display labels: "1", "2", "3a", "3b", etc. |

---

## 7. Network Validation

### 7.1 Current Guards

| Guard | Condition | Message | Action |
|---|---|---|---|
| G1 | No supply node | "No water supply node placed on the drawing." | Fail |
| G2 | No design sprinklers | "No sprinklers in the design area." | Fail |
| G3 | No network nodes | "No pipe network nodes found." | Fail |
| G4 | Supply not connected | "Water supply node is not connected to the pipe network." | Fail |
| G5 | No reachable sprinklers | "None of the design sprinklers are connected to the supply node." | Fail |

### 7.2 Supply Node Discovery

Currently: `_find_supply_network_node()` finds the nearest Node to the WaterSupply item by Manhattan distance. Warns (with distance in display units) if distance > 50 scene units but still proceeds. See [Divergence D5](#12-divergences--migration-paths).

### 7.3 Additional Validations (to be added)

| Validation | Detection | Message | Action |
|---|---|---|---|
| V1 — Loop detection | `len(pipes) > len(bfs_order) - 1` (more pipes than tree edges) | "Network contains loops — N pipe(s) excluded from calculation." | Warn, proceed |

---

## 8. Node Numbering

### 8.1 Classification

| Category | Criteria | Label format |
|---|---|---|
| Major | Branch/tee point (≠2 calc-path pipes), OR sprinkler node, OR diameter change between the 2 pipes | Sequential integer: "1", "2", "3" |
| Minor | Pass-through: exactly 2 same-diameter calc-path pipes, no sprinkler | Parent major number + letter: "1a", "1b" |

### 8.2 Ordering

BFS from supply node. Supply = node 1. Most remote sprinkler = highest number.

### 8.3 Calc Path Construction

Only nodes on paths from supply to design sprinklers are numbered. For each design sprinkler, walk `parent_node` chain back to supply, adding nodes to `calc_nodes` set. BFS order is then filtered to this set.

### 8.4 Overlap Handling

Nodes at the same XY position (vertical drops — detected by rounding scene position) share a position label. Badges stack vertically using `stack_index` / `stack_total`.

---

## 9. Report Widget

### 9.1 Tab 1: Summary

| Section | Content |
|---|---|
| Status | Pass/fail banner (green ✅ PASS or red ❌ FAIL) |
| Project metadata | Project name, address, system description, date |
| Design criteria | Hazard classification, design area (ft²), density (gpm/ft²), sprinkler count, hose stream allowance |
| Water supply data | Static pressure, residual pressure, test flow, gauge elevation, test date |
| Results | Sprinkler demand (gpm), hose stream (gpm) *(shown only when > 0)*, total demand (gpm) *(shown only when hose stream > 0)*, required pressure (psi), available pressure (psi) |
| Messages | All solver warnings/errors/summaries |

**Note:** Project metadata and design criteria sections require data not currently available in the solver result. See [Divergence D7](#12-divergences--migration-paths).

### 9.2 Tab 2: Node Summary Table

NFPA 13 standard calculation sheet format. Each row represents a node and the pipe leading to it from upstream:

| Column | Source |
|---|---|
| Node # | `node_labels[node]` |
| Elevation (ft) | `node.z_pos / 304.8` |
| Flow (gpm) | `pipe_flows[pipe_to_parent]` |
| Pipe Diameter | `pipe._properties["Diameter"]` |
| Pipe Length (ft) | Physical length from `get_length_ft()` |
| Equiv. Length (ft) | Fitting equivalent lengths at both ends of pipe |
| Total Length (ft) | Physical + equivalent |
| C-Factor | `pipe._properties["C-Factor"]` |
| Friction Loss (psi/ft) | `hf / total_length` (unit friction) |
| Total hf (psi) | `pipe_friction_loss[pipe]` |
| Required Pressure (psi) | `required_node_pressures[node]` — **primary** |
| Actual Pressure (psi) | `node_pressures[node]` — secondary |
| Notes | Sprinkler K-factor, fitting types at node |

"Show minor nodes" checkbox toggles visibility of minor (pass-through) nodes.

### 9.3 Tab 3: Hydraulic Graph

Custom-painted `QWidget` (`_HydraulicGraphWidget`):

| Element | Description |
|---|---|
| X-axis | Flow (GPM), Q^1.85 scale — makes supply curve a straight line |
| Y-axis | Pressure (PSI), linear scale |
| Supply curve | Straight line from (0, P_static) through (Q_test, P_residual), extended to graph edge. Blue markers at both data points. All labels bold. |
| Origin marker | Gray dot at (0, 0) — anchors the graph |
| Sprinkler demand | Red marker at (sprinkler_demand, required_pressure). Dashed red line from origin to this point. |
| Total demand | Red marker at (sprinkler_demand + hose_stream, required_pressure) — **only shown when hose stream > 0**. Dashed red line from sprinkler demand to this point. |
| Data point labels | All bold: "0 GPM @ P_static PSI", "Q_test GPM @ P_residual PSI", "Sprinkler: Q GPM @ P PSI", "Total: Q GPM @ P PSI" |
| Grid | Dotted lines every 100 GPM (X) and 10 PSI (Y) |
| Auto-scale | Axes fit data points with padding (nearest 100 GPM, nearest 10 PSI + 10) |

### 9.4 Export

| Format | Content | Method |
|---|---|---|
| PDF | Summary + Node Summary Table (formatted HTML) | `QTextDocument` → `QPrinter` |
| CSV | Summary data + Node Summary Table rows | Python `csv` module |

**Future:** Multi-system export with per-system sections in a single document. Professional templates with company logo and engineer stamp area (P3).

---

## 10. Equivalent Pipe Length Reference

### 10.1 Data Table (NFPA 13 Table 22.4.3.1.1)

Equivalent lengths in feet, by fitting type and nominal pipe diameter:

| Fitting | ¾" | 1" | 1-¼" | 1-½" | 2" | 2-½" | 3" | 4" | 5" | 6" | 8" |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 90° elbow | 2 | 2.5 | 3 | 4 | 5 | 6 | 7 | 10 | 12 | 14 | 18 |
| 45° elbow | 1 | 1.5 | 2 | 2 | 3 | 3 | 4 | 5 | 6 | 7 | 9 |
| Tee (flow turn) | 4 | 5 | 6 | 8 | 10 | 12 | 15 | 20 | 25 | 30 | 35 |
| Cross (flow turn) | 4 | 5 | 6 | 8 | 10 | 12 | 15 | 20 | 25 | 30 | 35 |
| Cap (end) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### 10.2 Mapping: Fitting.type → Table Row

| `Fitting.type` | Table entry | Rationale |
|---|---|---|
| `90elbow` | 90° elbow | Direct match |
| `45elbow` | 45° elbow | Direct match |
| `tee` | Tee (flow turn) | Horizontal tee |
| `tee_up`, `tee_down` | Tee (flow turn) | Vertical tee |
| `wye` | 45° elbow | Branch treated as 45° turn |
| `cross` | Cross (flow turn) | Direct match |
| `elbow_up`, `elbow_down` | 90° elbow | Vertical 90° turn |
| `cap` | Cap (end) | 0 equivalent length |
| `no fitting` | — | 0 equivalent length |

### 10.3 Application

For each pipe in the network:
```
total_equivalent_length = physical_length + equiv_at_node1 + equiv_at_node2
```

Where `equiv_at_nodeX` = equivalent length for that node's fitting type at the pipe's nominal diameter. The pipe's diameter is used for the lookup (not the fitting's connected pipes, which may vary).

### 10.4 UI Access

The equivalent length table is viewable as `EquivalentLengthDialog` — accessible from the Hydraulics toolbar ("Equiv. Lengths" button) and from a button in the Hydraulic Report dock. Read-only display of the NFPA 13 table with human-readable fitting names and a source footnote. Implemented in `hydraulic_report.py`.

---

## 11. On-Scene Overlay

### 11.1 Node Badges

Major nodes (numeric labels only) display `HydraulicNodeBadge` child items showing:
- Node number (label)
- Required pressure (psi) — **primary display value**
- Flow out (gpm) — if sprinkler node: `K × √P_actual`
- Actual pressure (psi) — secondary

Badge position: auto-selected by `best_position_for_node()` to avoid overlap with pipes. Nodes at the same XY position (vertical drops) stack badges vertically.

### 11.2 Pipe Friction Loss Heatmap

Pipes colored by friction loss magnitude (relative to the maximum hf in the system):

| Normalized hf | Color | Meaning |
|---|---|---|
| Low (0.0–0.33) | Green | No bottleneck |
| Medium (0.33–0.66) | Orange | Consider upsizing |
| High (0.66–1.0) | Red | Bottleneck — upsize this pipe |

Thresholds are relative (normalized to system max hf), not absolute. This ensures the heatmap highlights the worst offenders regardless of system size.

### 11.3 Clear

`Model_Space.clear_hydraulics()` removes all badges, resets pipe display to default colors, and clears `hydraulic_result`.

---

## 12. Divergences & Migration Paths

| # | Divergence | Priority | Current Behavior | Target Behavior | Migration |
|---|---|---|---|---|---|
| D1 | Tree-only topology | P2 | BFS tree silently excludes pipes in looped networks | Detect loops, warn user with count of excluded pipes, proceed with tree approximation. Future: Hardy Cross iteration. | Add loop detection: if `len(system.pipes) > len(bfs_order) - 1`, warn. |
| ~~D2~~ | ~~Equivalent pipe lengths~~ | ~~P1~~ | **Resolved 2026-04-29.** Fitting equivalent lengths from NFPA 13 Table 22.4.3.1.1 added to friction loss via `equivalent_length.py`. Supply node fittings excluded. "Equiv (ft)" and "Total (ft)" columns in Pipe Results. Reference dialog accessible from Hydraulics toolbar and report. | | |
| ~~D3~~ | ~~Hose stream allowance~~ | ~~P1~~ | **Resolved 2026-04-29.** Hose stream consumed in Phase 3 supply check (`Q_check = total_demand + hose_stream_allowance`). Report shows separate Sprinkler Demand / Hose Stream / Total Demand line items (hose stream omitted when 0). Graph shows origin marker, red sprinkler demand marker, and red total demand marker with dashed connecting lines (total marker omitted when hose = 0). `hose_stream_gpm` field on `HydraulicResult`. | | |
| D4 | Velocity → pressure heatmap | P2 | Pipes/report color-coded by velocity thresholds (12/20 fps); solver warns at 20 fps | Replace with friction loss heatmap on pipes; de-emphasize velocity in report; keep as informational column only | Remove velocity color-coding from report cells. Add pipe hf overlay to scene (§11.2). Remove velocity warning messages from solver. |
| D5 | Supply node proximity | P2 | WaterSupply found by nearest Manhattan distance to any Node; warns (in display units) if >50 scene units | WaterSupply placed directly on a Node (same placement model as sprinklers) | Change to on-node placement. Solver reads `supply_ws.parentItem()` or stored node ref instead of proximity search. |
| ~~D6~~ | ~~Required pressure not exposed~~ | ~~P1~~ | **Resolved 2026-04-29.** `required_node_pressures` field added to `HydraulicResult`. Node badges show "Required P (psi)" as primary and "Actual P (psi)" as secondary in PropertyManager. | | |
| D7 | Report structure | P2 | 5 tabs (Summary, Pipe Results, Sprinkler Schedule, Pipe Schedule, Graph) | 3 tabs: Summary (with project/design metadata), Node Summary Table (NFPA format), Hydraulic Graph | Consolidate. Add project header + design criteria to Summary. Replace 3 middle tabs with unified NFPA-format Node Summary Table. |
| ~~D8~~ | ~~Uncalibrated scale~~ | ~~P1~~ | **Withdrawn 2026-04-30.** Scene scale is always 1 px = 1 mm; `is_calibrated` refers to underlay calibration, not scene geometry. Pipes drawn directly on the scene have correct lengths regardless. The default `pixels_per_mm = 1.0` produces correct conversions. A scale guard would block valid calculations on projects without underlays. **Pre-existing bug:** `Pipe.get_length_ft()` returns 0.0 when `is_calibrated` is False, even though `pixels_per_mm = 1.0` gives the correct result. | | |
| D9 | Multi-system export | P3 | One system per project; one calculation; one report | Per-system hydraulic calculations with combined multi-system PDF export | Depends on sprinkler spec D8. Report generates per-system sections with system identification. |
| D10 | PDF templates | P3 | Basic QPrinter HTML rendering | Company logo, engineer stamp area, page numbers, professional formatting | Template system with configurable header block. |

---

## 13. Testing Strategy

### 13.1 Friction Loss Formula

| Test | Input | Expected |
|---|---|---|
| Known values | Q=100 gpm, C=120, d=2.067", L=50 ft | `4.52 × 100^1.852 / (120^1.852 × 2.067^4.87) × 50` = hand-calculated |
| Zero flow | Q=0, any C/d/L | hf = 0 |
| Zero length | Any Q/C/d, L=0 | hf = 0 |
| Zero diameter | Q=100, d=0 | hf = 0 (guard) |

### 13.2 Supply Curve Interpolation

| Test | Input | Expected |
|---|---|---|
| Zero demand | Ps=80, Pr=60, Qt=500, Q=0 | P = 80 (static) |
| At test flow | Ps=80, Pr=60, Qt=500, Q=500 | P = 60 (residual) |
| Beyond test flow | Ps=80, Pr=60, Qt=500, Q=750 | P < 60 (extrapolated via power law) |
| Double test flow | Ps=80, Pr=60, Qt=500, Q=1000 | `80 - 20 × 2^1.85` ≈ 7.9 |
| Invalid: Ps=0 | Any | P = 0 |
| Invalid: Qt=0 | Any Q>0 | P = Ps |

### 13.3 BFS Tree Construction

| Test | Network | Expected |
|---|---|---|
| Linear (A→B→C) | 3 nodes, 2 pipes | bfs_order=[A,B,C], parent[C]=B, children[A]=[B] |
| Branch (A→B, A→C) | 3 nodes, 2 pipes from A | children[A]=[B,C], parent[B]=A, parent[C]=A |
| Disconnected node D | 4 nodes, 2 pipes (A-B, A-C) | D not in bfs_order |
| Loop (A-B-C-A) | 3 nodes, 3 pipes | bfs_order has 3 nodes, only 2 pipes in tree |

### 13.4 Flow Accumulation

| Test | Network | Expected |
|---|---|---|
| Single sprinkler | Supply→Spr(K=5.6, P_min=7) | Q = 5.6×√7 ≈ 14.8 gpm |
| Two sprinklers on branch | Supply→A→B(K=5.6,P=7), A→C(K=5.6,P=7) | pipe[Supply→A] = 14.8 + 14.8 = 29.6 gpm |
| Unequal K-factors | Supply→A→B(K=8.0,P=7), A→C(K=5.6,P=7) | pipe[Supply→A] = 21.2 + 14.8 = 36.0 gpm |

### 13.5 Pressure Propagation

| Test | Network | Expected |
|---|---|---|
| Flat, single pipe | Supply→Spr, hf=5 psi, h_e=0 | required_at_supply = P_min + 5 |
| Uphill | Supply→Spr, hf=5, Δz=+10ft | required = P_min + 5 + 4.33 = P_min + 9.33 |
| Downhill | Supply→Spr, hf=5, Δz=-10ft | required = P_min + 5 - 4.33 = P_min + 0.67 |
| Two branches | Supply→A→B(high hf), Supply→A→C(low hf) | required_at_supply = max(branch_B, branch_C) |
| Forward actual | Supply pressure = 80, hf=5, h_e=2 | actual_at_child = 80 - 5 - 2 = 73 |

### 13.6 End-to-End

Small network: supply + 3 sprinklers on a single branch line (Supply→N1→N2→N3, sprinklers on N1/N2/N3).
- Given: K=5.6, P_min=7 for all; known pipe lengths and diameters
- Verify: total_demand, required_pressure, supply check pass/fail, individual node pressures
- With hose stream: verify demand point shifts by allowance amount

### 13.7 Color Helpers (hf-based)

| Test | Input | Expected |
|---|---|---|
| Lowest hf in system | hf / max_hf ≈ 0 | Green |
| Highest hf in system | hf / max_hf = 1.0 | Red |
| Mid-range | hf / max_hf ≈ 0.5 | Orange |
| All pipes equal hf | Any | All same color (no relative difference) |

### 13.8 Report Structure

| Test | Assertion |
|---|---|
| Summary HTML | Contains: status class (pass/fail), demand value, required value, available value |
| Node Summary Table | Column count = 13, headers match NFPA format |
| CSV export | Parseable with Python csv; correct field count per row |
| Graph auto-scale | Axes encompass both supply data points and demand point |

---

## 14. Acceptance Criteria

1. Spec documents the complete 4-phase algorithm with sufficient detail to reproduce results by hand calculation.
2. All NFPA 13 §22.4.2 formulas stated with correct constants, units, and sign conventions.
3. All 10 divergences flagged with priority, current/target behavior, and migration path.
4. Network validation rules documented — 5 existing guards + 2 new validations (loops, uncalibrated).
5. Report format matches NFPA 13 calculation sheet conventions (Node Summary Table columns).
6. Equivalent pipe length table included with complete fitting-type mapping.
7. `HydraulicResult` contract fully defined — all fields with types and semantics.
8. Testing expectations define concrete inputs/outputs enabling formula verification against hand calculations.
9. Hose stream integration point clearly specified (supply curve check only, not pipe calculations).
10. Required pressure identified as primary display value (not actual pressure).

## 15. Verification Checklist

- [ ] Hazen-Williams formula stated with correct exponents (1.852, 4.87) and constant (4.52)
- [ ] Elevation correction: 0.433 psi/ft with sign convention (positive Δz = pressure lost) documented
- [ ] Supply curve power law stated with 1.85 exponent
- [ ] All 4 phases described with traversal direction and accumulation logic
- [ ] `HydraulicResult` fields include both required and actual pressures
- [ ] Hose stream addition to demand at supply check documented (not added to pipe calculations)
- [ ] Equivalent pipe length table covers all 11 pipe diameters × 5 fitting categories
- [ ] `Fitting.type` → table entry mapping is complete (no unmapped types)
- [ ] Node Summary Table columns match NFPA 13 calculation sheet format
- [ ] Network validation: all 5 guards + 2 new validations listed with conditions and actions
- [ ] Loop detection formula: `pipe_count > node_count_in_tree - 1`
- [ ] Testing section has hand-calculable expected values for friction loss formula
- [ ] Pass criterion clearly stated: `P_available ≥ required_pressure`
- [ ] Primary vs secondary display value distinguished (required vs actual pressure)
