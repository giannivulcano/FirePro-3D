# Sprinkler System Components Specification

**Status:** Draft  
**Date:** 2026-04-28  
**Scope:** Document current behavior + flag divergences with migration paths

---

## Table of Contents

1. [Goal](#1-goal)
2. [Motivation](#2-motivation)
3. [Architecture & Constraints](#3-architecture--constraints)
4. [Sprinkler Database](#4-sprinkler-database)
5. [Pipe Diameter, Schedule & Material System](#5-pipe-diameter-schedule--material-system)
6. [Fitting Assignment](#6-fitting-assignment)
7. [Node Z-Position Computation](#7-node-z-position-computation)
8. [Sprinkler Visual & Symbol System](#8-sprinkler-visual--symbol-system)
9. [SprinklerSystem Container](#9-sprinklersystem-container)
10. [WaterSupply Entity](#10-watersupply-entity)
11. [Design Area & NFPA 13 Curves](#11-design-area--nfpa-13-curves)
12. [Template Lifecycle & Data Flow](#12-template-lifecycle--data-flow)
13. [Serialization & Backward Compatibility](#13-serialization--backward-compatibility)
14. [Divergences & Migration Paths](#14-divergences--migration-paths)
15. [Testing Strategy](#15-testing-strategy)
16. [Acceptance Criteria](#16-acceptance-criteria)
17. [Verification Checklist](#17-verification-checklist)

---

## 1. Goal

Document the sprinkler system component subsystem: the data models, algorithms, and visual elements that define fire protection piping networks in FirePro3D. Establish the authoritative reference for sprinkler product data, pipe sizing, fitting assignment logic, node elevation computation, and design area validation. Flag divergences from correct/complete behavior with prioritized migration paths.

## 2. Motivation

These 8 modules form the physical backbone of the application — every hydraulic calculation, every auto-populate placement, and every 3D view depends on them. Yet no spec exists documenting their contracts, invariants, or known gaps. This spec enables:

- Confident refactoring (clear invariants prevent regressions)
- Hydraulic solver spec (separate, builds on these interfaces)
- New feature work (multi-system support, sidewall sprinklers, material manager) with documented starting points

## 3. Architecture & Constraints

### 3.1 Module Map

```
┌─────────────────────────────────────────────────────────┐
│  SprinklerSystem (typed index container)                │
│  ├─ nodes: [Node]        ├─ pipes: [Pipe]              │
│  ├─ sprinklers: [Sprinkler]  └─ supply_node: WaterSupply│
│  └─ fittings: [] (unused — accessed via Node.fitting)   │
├─────────────────────────────────────────────────────────┤
│  Node ──owns──> Fitting (symbol + type logic)           │
│       ──owns──> Sprinkler (SVG visual)                  │
│       ──refs──> Pipe[] (max 4)                          │
├─────────────────────────────────────────────────────────┤
│  SprinklerDatabase (JSON file, product records)         │
│  DesignArea (hazard class, NFPA curves, sprinkler set)  │
│  WaterSupply (supply curve properties)                  │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Constraints

- All geometry in millimeters internally
- Imperial units for NFPA 13 domain data (psi, gpm, ft², °F) — display adapts via ScaleManager
- 4-pipe maximum per node (design invariant — 5-way junctions modeled as two adjacent nodes)
- Scene items live in both Qt scene graph AND SprinklerSystem typed lists (parallel bookkeeping)

### 3.3 Boundary with Hydraulic Solver Spec

This spec owns all physical component data. The hydraulic solver spec (separate) consumes:

| Interface | Source | Consumer |
|---|---|---|
| `Pipe.get_inner_diameter()` | §5 schedule tables | Hazen-Williams friction loss |
| `Pipe.get_length_ft()` | Pipe 3D geometry | Friction loss per segment |
| `Sprinkler._properties["K-Factor"]` | §4 database record | Design sprinkler flow: Q = K × √P |
| `Sprinkler._properties["Min Pressure"]` | §4 database record | Leaf node pressure initialization |
| `WaterSupply` properties | §10 | Supply curve construction |
| `SprinklerSystem.supply_node` | §9 | Network root for traversal |
| Design area sprinkler list + hazard | §11 | Design sprinkler selection |

---

## 4. Sprinkler Database

### 4.1 Data Model — SprinklerRecord

`firepro3d/sprinkler_db.py` — immutable dataclass.

| Field | Type | Units | Purpose |
|-------|------|-------|---------|
| id | str | — | Unique key (e.g. `"tyco_ty315"`) |
| manufacturer | str | — | Brand name |
| model | str | — | Product model number |
| type | str | — | Installation type: Pendent, Upright, Sidewall, Concealed |
| k_factor | float | gpm/√psi | Flow coefficient (hydraulic solver input) |
| min_pressure | float | psi | Minimum operating pressure |
| coverage_area | float | ft² | Maximum protection area per sprinkler |
| temp_rating | int | °F | Activation temperature |
| orifice | str | — | Orifice size (e.g. `'1/2"'`) |
| notes | str | — | Free-text description |

Serialization: `to_dict()` / `from_dict()` with safe defaults for all fields.

### 4.2 SprinklerDatabase

JSON-backed store at `DEFAULT_PATH = "sprinklers.json"`.

**Collections:**
- `library` — all products (defaults + user additions)
- `templates` — user-starred favourites (subset of library, dedup by id)

**Lifecycle:**
- First run: seeded with 15 built-in defaults, saved to disk
- Subsequent: loaded from JSON file; corrupt/missing file falls back to defaults

**CRUD:**
- `add_to_library(record)` — append and save
- `update_in_library(index, record)` — replace at index and save
- `delete_from_library(index)` — remove at index and save

**Query helpers (cascading filters):**
- `get_unique_manufacturers()` → sorted set of manufacturer names
- `get_models_for(manufacturer)` → sorted model names for that manufacturer
- `get_types_for(manufacturer, model=None)` → sorted installation types
- `find_records(manufacturer=None, model=None, type_=None)` → filtered list

**Template management:**
- `add_to_templates(record)` — star a product (skip if id already starred)
- `delete_from_templates(index)` — remove from starred list

### 4.3 SprinklerManagerDialog

Full-featured manager dialog with two tabs:

**Library tab:**
- Search bar: filters by manufacturer, model, notes (case-insensitive substring match)
- Type combo filter: (All), Pendent, Upright, Sidewall, Concealed
- Table: Manufacturer, Model, Type, K-factor, Min P, Coverage, Temp, Orifice
- CRUD buttons: Add, Edit, Delete, ★ Star (add to templates)

**My Templates tab:**
- Same table format as Library
- Buttons: Use as Template, Remove

**Interaction:**
- "Use as Template" / double-click → emits `templateChosen(SprinklerRecord)`, accepts dialog
- Signal enables external consumers to react to selection

### 4.4 Field Mapping: SprinklerRecord ↔ Sprinkler._properties

| Record field | Direction | Properties key | Notes |
|---|---|---|---|
| manufacturer | → | Manufacturer | Auto-populate path only; Sprinkler Manager path does not set this |
| model | → | Model | Auto-populate path only; Sprinkler Manager path does not set this |
| type | → | Orientation | Auto-populate path uses correct key; **BUG:** Sprinkler Manager path uses `"Type"` which silently fails (key not in _properties) |
| k_factor | → | K-Factor | Both paths work correctly |
| min_pressure | → | Min Pressure | Both paths work correctly |
| coverage_area | → | Coverage Area | Both paths work correctly |
| temp_rating | → | Temperature | Auto-populate formats as `"155°F"`; **BUG:** Sprinkler Manager path uses `"Temp Rating"` which silently fails |
| orifice | ✗ | — | Not transferred to placed sprinklers |
| notes | ✗ | — | Not transferred to placed sprinklers |
| — | — | Design Density | Set by auto-populate, not from DB |
| — | — | S Spacing / L Spacing | Computed by design_area |
| — | — | Graphic | User-selected SVG variant |
| — | — | Ceiling Level / Ceiling Offset | From parent Node |
| — | — | X / Y / Z | Read-only, from Node scenePos + z_pos |

**Bug note:** Two template application paths exist with different behavior:
- `model_space.py:1709-1715` (auto-populate) — directly sets `_properties[key]["value"]`, uses correct keys. Transfers all fields including Manufacturer, Model, Temperature, Orientation.
- `main.py:2207-2211` (Sprinkler Manager "Use as Template") — calls `set_property(key, value)`, uses wrong keys for Temperature (`"Temp Rating"`) and Orientation (`"Type"`). Also does not transfer Manufacturer or Model. Only K-Factor, Min Pressure, and Coverage Area actually transfer.

---

## 5. Pipe Diameter, Schedule & Material System

### 5.1 Internal Key Format

Diameter keys stored in `_properties["Diameter"]` and serialization:

```
"1\"Ø", "1-½\"Ø", "2\"Ø", "3\"Ø", "4\"Ø", "5\"Ø", "6\"Ø", "8\"Ø"
```

Display mappings:
- Imperial: `"1\"Ø"` → `"Ø 1\""`, `"1-½\"Ø"` → `"Ø 1-½\""`, etc.
- Metric: `"1\"Ø"` → `"Ø 25 mm"`, `"1-½\"Ø"` → `"Ø 40 mm"`, etc.
- Round-trip: `_INT_TO_IMPERIAL` / `_INT_TO_METRIC` forward, `_DISPLAY_TO_INT` reverse

### 5.2 Nominal OD Table

`NOMINAL_OD_IN` — nominal outside diameter in inches per internal key.

| Key | OD (in) | Key | OD (in) |
|-----|---------|-----|---------|
| 1"Ø | 1.315 | 4"Ø | 4.500 |
| 1-½"Ø | 1.900 | 5"Ø | 5.563 |
| 2"Ø | 2.375 | 6"Ø | 6.625 |
| 3"Ø | 3.500 | 8"Ø | 8.625 |

Also contains legacy keys without Ø suffix for backward compatibility with older projects and 3D view.

Used for: fitting symbol sizing reference, 3D mesh cylinder radius.

### 5.3 Inner Diameter Lookup

`INNER_DIAMETER_IN[schedule][nominal]` — actual inside diameter in inches.

Schedules: Sch 10, Sch 40, Sch 80, Sch 40S, Sch 10S.

Consumed by `Pipe.get_inner_diameter()` for Hazen-Williams friction loss calculation. Fallback: 2.067" (2" Sch 40) when combination not found.

Example values (Sch 40):

| Nominal | ID (in) | Nominal | ID (in) |
|---------|---------|---------|---------|
| 1"Ø | 1.049 | 4"Ø | 4.026 |
| 1-½"Ø | 1.610 | 5"Ø | 5.047 |
| 2"Ø | 2.067 | 6"Ø | 6.065 |
| 3"Ø | 3.068 | 8"Ø | 7.981 |

### 5.4 Auto-Main Classification

```python
_MAIN_DIAMETERS = {"3\"Ø", "4\"Ø", "5\"Ø", "6\"Ø", "8\"Ø"}
```

When Diameter is set to a value in this set, Line Type auto-assigns to "Main". Display width: Main = 150mm, Branch = 75mm. Threshold: ≥ 3" is Main.

### 5.5 C-Factor

Hazen-Williams roughness coefficient. Read-only, auto-derived from Material via `MATERIAL_C_FACTOR` mapping (NFPA 13 Table 22.4.4.8):

| Material | C-Factor |
|----------|----------|
| Galvanized Steel | 120 |
| Black Steel | 120 |
| Stainless Steel | 150 |
| PVC | 150 |
| CPVC | 150 |

Material options: Galvanized Steel, Stainless Steel, Black Steel, PVC, CPVC.

~~See [Divergence D5](#14-divergences--migration-paths) for planned material-derivation.~~ **Resolved 2026-05-03.**

### 5.6 Pipe Properties Schema

| Key | Type | Default | Options |
|-----|------|---------|---------|
| Diameter | enum | 1"Ø | ¾"Ø, 1"Ø, 1-¼"Ø, 1-½"Ø, 2"Ø, 2-½"Ø, 3"Ø, 4"Ø, 5"Ø, 6"Ø, 8"Ø |
| Schedule | enum | Sch 40 | Sch 10, Sch 40, Sch 80, Sch 40S, Sch 10S |
| C-Factor | string (readonly) | 120 | Auto-derived from Material |
| Material | enum | Galvanized Steel | Galvanized Steel, Stainless Steel, Black Steel, PVC, CPVC |
| Line Type | enum | Branch | Branch, Main |
| Colour | enum | Red | Black, White, Red, Blue, Grey |
| Phase | enum | New | New, Existing, Demo |
| Show Label | enum | True | True, False |
| Label Size | string | 12 | — |

---

## 6. Fitting Assignment

### 6.1 Type Determination Algorithm

`Fitting.determine_type(pipes)` in `firepro3d/fitting.py` classifies the junction:

| Pipe count | Condition | Result |
|---|---|---|
| 0 | — | `no fitting` |
| 1 | — | `cap` |
| 2 | Angle 180°±10° | `no fitting` (collinear) |
| 2 | Angle 90°±10° | `90elbow` |
| 2 | Angle 45°±5° or 135°±5° | `45elbow` |
| 2 | Other angles | `no fitting` |
| 3 | Any pair at 90° | `tee` |
| 3 | No 90° pair | `wye` |
| 4 | Two perpendicular collinear pairs | `cross` |
| 4 | Otherwise | `no fitting` |

**Design invariant:** Angle tolerances (10° for elbows/collinear, 5° for 45° elbows) are coupled to the 45° snap constraint in `Node.snap_point_45`. They are intentionally generous for snap-placed pipes and do not require tuning.

### 6.2 Vertical Pipe Handling

**Detection criteria:**
- Same XY position: `dx² + dy² < 100` (10px tolerance)
- Different Z: `|Δz_pos| > 0.01`

**Type assignment when vertical pipes present:**

| Vertical | Horizontal | Result |
|---|---|---|
| 1 | 0–1 | `elbow_up` or `elbow_down` |
| 1 | 2+ | `tee_up` or `tee_down` |

Direction (`up`/`down`) determined by comparing `z_pos` of this node vs the other end of the vertical pipe.

### 6.3 Visibility Rules

Fitting symbol is hidden when:
1. Node has a sprinkler (sprinkler symbol takes visual precedence)
2. Two nodes overlap in XY (vertical pipe): only the highest-Z **visible** node shows its fitting. Hidden nodes (e.g. outside view range) are skipped -- the next-highest visible node shows its fitting instead.
   - Tie-break 1: higher `ceiling_offset` wins
   - Tie-break 2: higher `id()` wins

### 6.4 Symbol Alignment

Each fitting type defines `through` direction(s) — canonical unit vectors describing the SVG's orientation:

| Type | Through spec | Alignment method |
|---|---|---|
| cap | 1 vector | `rotate_unit_vector` |
| 90elbow, 45elbow | 2 vectors (pair) | `make_qtransform_from_qpoints` |
| tee, wye | 2 vectors (pair) | Identify collinear pair first, then affine match |
| cross | 1 vector | Identify one collinear pair, rotate to match |
| elbow_up/down | 1 vector | Rotate to horizontal pipe direction |
| tee_up/down | 2 vectors (pair) | Use horizontal pipe vectors for alignment |

For tee/wye: the algorithm identifies the collinear pipe pair (angle ≈ 180°) to distinguish the "through-run" from the "branch" before computing the transform.

### 6.5 Symbol Scaling

```
target_mm = max_connected_pipe_width × 4 × display_scale
scale_factor = target_mm / svg_natural_size
```

- Branch pipe (75mm width) → 300mm fitting symbol
- Main pipe (150mm width) → 600mm fitting symbol

SVG is scaled uniformly and centred on the parent node's origin (0, 0).

### 6.6 Pipe Clipping

`clip_region_scene()` returns a circular `QPainterPath` in scene coordinates (bounding circle of the fitting symbol). Pipes use this path to clip their rendering near the junction, preventing visual overlap with the fitting symbol. Returns `None` if fitting is invisible or `no fitting`.

---

## 7. Node Z-Position Computation

### 7.1 Authoritative Formula

```
z_pos = level_elevation(ceiling_level) + ceiling_offset
```

Where:
- `ceiling_level` — name of the reference level (default: "Level 1")
- `ceiling_offset` — vertical offset from that level's elevation in mm (default: -50.8mm = -2")
- Both stored on Node and synced to child Sprinkler's property display

### 7.2 Recomputation Trigger

`_recompute_z_pos()` is called when:
- User changes Ceiling Level via property panel → resolves new level elevation
- User changes Ceiling Offset via property panel → uses new offset value

Resolution: `scene._level_manager.get(ceiling_level).elevation + ceiling_offset`

Graceful fallback: no-op if scene is None, level_manager is None, or level not found.

### 7.3 Node Ownership

| Owned entity | Cardinality | Access |
|---|---|---|
| Fitting | Exactly 1 | `node.fitting` (always created in `__init__`) |
| Sprinkler | 0 or 1 | `node.sprinkler` (optional, via `add_sprinkler()`) |
| Pipes | 0–4 | `node.pipes` list (bidirectional refs) |

### 7.4 Property Sync

Ceiling Level and Ceiling Offset exist in two forms:
- Instance attributes: `node.ceiling_level`, `node.ceiling_offset` (authoritative)
- Properties dict: `node._properties["Ceiling Level"]`, `node._properties["Ceiling Offset"]` (for PropertyManager display)

Both are updated together on `set_property()`. When a Sprinkler is present, its `get_properties()` reads ceiling values directly from the parent Node (Node is single source of truth).

Pipes do not store ceiling data; all Z positioning is derived from endpoint Node `ceiling_level` and `ceiling_offset` attributes.

### 7.5 Legacy z_offset Field

~~See [Divergence D4](#14-divergences--migration-paths).~~ **Resolved 2026-05-03.** `ceiling_offset` is now the sole source of truth for Z computation:

- `z_pos = lvl.elevation + ceiling_offset` (all paths: property panel, deserialization, level changes, paste, move-to-level)

`z_offset` is deprecated: no longer written on save or clipboard copy. Old saves containing `z_offset` are still read for backward compatibility (paste path falls back to `z_offset` when `ceiling_offset_mm` is absent).

---

## 8. Sprinkler Visual & Symbol System

### 8.1 SVG Graphics

Three generic drafting symbols in `firepro3d/graphics/sprinkler_graphics/`:
- `sprinkler0.svg` — "Sprinkler0"
- `sprinkler1.svg` — "Sprinkler1"
- `sprinkler2.svg` — "Sprinkler2"

User-selectable via the `Graphic` property dropdown. Symbol selection is independent of installation type (Orientation). These are aesthetic/drafting-convention variants, not orientation-specific.

### 8.2 Scaling Constants

| Constant | Value | Purpose |
|---|---|---|
| `SVG_NATURAL_PX` | 30.0 | Native SVG bounding box width in px |
| `TARGET_MM` | 609.6 | Desired symbol diameter in scene mm (24" × 25.4) |
| `SCALE` | 20.32 | `TARGET_MM / SVG_NATURAL_PX` |

No `ItemIgnoresTransformations` flag — symbol scales with zoom to maintain real-world size (24" diameter circle in plan view).

### 8.3 Centering

`centre_svg_on_origin()` (via `displayable_item.centre_svg_on_origin` helper) positions the SVG so its centre aligns with the parent Node's local origin (0, 0). Called on:
- Graphic load / change
- Display scale change
- `rescale()` events

### 8.4 Selection Delegation

`Sprinkler.setFlag(ItemIsSelectable, False)` — the sprinkler is not directly selectable. Clicking anywhere on the sprinkler graphic selects the parent Node. Node's `shape()` expands to encompass the sprinkler's bounding area (`TARGET_MM / 2 × display_scale` radius circle).

### 8.5 Display Integration

- `_display_scale` multiplier (from DisplayManager) affects effective visual size
- SVG tinting via `_set_svg_tint()` for colour/fill overrides
- Z-value: 100 (above Node at 10, above fitting symbols)
- Paint: suppresses default Qt selection dashes; selection highlight drawn by parent Node

---

## 9. SprinklerSystem Container

### 9.1 Purpose

Performance-motivated typed index (`firepro3d/sprinkler_system.py`, 49 LOC). Avoids expensive `O(n)` type-filtered `scene.items()` calls by maintaining separate lists for each entity type.

### 9.2 Contents

| Attribute | Type | Populated by |
|---|---|---|
| `nodes` | list[Node] | `model_space.py` add/remove helpers |
| `pipes` | list[Pipe] | `model_space.py` add/remove helpers |
| `sprinklers` | list[Sprinkler] | `model_space.py` add/remove helpers |
| `fittings` | list[Fitting] | Never populated (fittings accessed via `node.fitting`) |
| `supply_node` | WaterSupply \| None | Set when water supply is placed/removed |

**Design invariant:** The `fittings` list is intentionally unused. Fittings are always accessed through their owning Node. The list exists for potential future use but carries no maintenance burden.

### 9.3 Consumers

| Module | Access pattern |
|---|---|
| `hydraulic_solver.py` | Iterates sprinklers, traverses pipes/nodes from supply |
| `level_manager.py` | Updates z_pos for all nodes/pipes on level elevation change |
| `display_manager.py` | Applies display overrides to all system items |
| `elevation_scene.py` | Projects pipes/nodes into elevation view |
| `hydraulic_report.py` | Generates tabular report data |

### 9.4 Sync Mechanism

All mutations go through `model_space.py` helpers which maintain both:
1. Qt scene graph: `scene.addItem()` / `scene.removeItem()`
2. Typed lists: `sprinkler_system.add_*()` / `remove_*()`

Undo/redo rebuilds from serialization, which re-populates both. No independent sync mechanism — consistency relies on all mutations flowing through model_space helpers.

### 9.5 Report

`report()` returns a dict with entity counts: `{"nodes": N, "pipes": N, "sprinklers": N, "fittings": N}`.

---

## 10. WaterSupply Entity

### 10.1 Role

Physical network endpoint representing the water main connection (`firepro3d/water_supply.py`, 80 LOC). Placed once per system (currently once per project due to singleton SprinklerSystem). Provides supply curve data consumed by the hydraulic solver.

### 10.2 Properties

| Key | Type | Default | Units |
|---|---|---|---|
| Static Pressure | string | 80 | psi |
| Residual Pressure | string | 60 | psi (at test flow) |
| Test Flow | string | 500 | gpm (at residual pressure) |
| Elevation | string | 0 | ft (at supply gauge) |
| Hose Stream Allowance | enum | 250 GPM | 100 GPM, 250 GPM, 500 GPM |

### 10.3 Visual

Same scaling pattern as Sprinkler:
- SVG: `graphics/sprinkler_graphics/water_supply.svg`
- 24" real-world diameter (`TARGET_MM = 609.6`, `SCALE = 20.32`)
- Centred on origin, `ItemIsSelectable`, Z-value 50
- No `ItemIgnoresTransformations` — scales with zoom

### 10.4 Solver Interface

Convenience `@property` accessors with safe float parsing (fallback to 0.0):
- `static_pressure` → float psi
- `residual_pressure` → float psi
- `test_flow` → float gpm
- `elevation` → float ft
- `hose_stream_allowance` → float gpm (parsed from "250 GPM" format)

---

## 11. Design Area & NFPA 13 Curves

### 11.1 Hazard Classification

Per-design-area property (per-room granularity). Options from NFPA 13:

| Classification | Typical use |
|---|---|
| Light Hazard | Offices, churches, hospitals |
| Ordinary Hazard Group 1 | Parking garages, laundries |
| Ordinary Hazard Group 2 | Machine shops, dry cleaners |
| Extra Hazard Group 1 | Aircraft hangars, saw mills |
| Extra Hazard Group 2 | Flammable liquid spraying, plastic processing |

Stored as `_properties["Hazard Classification"]` enum on DesignArea.

### 11.2 Density/Area Curves

`DENSITY_AREA_CURVES` — NFPA 13 Figure 11.2.3.1.1 data. Hardcoded in `auto_populate_dialog.py`.

Structure: `dict[str, list[tuple[float, float]]]` — hazard class name → list of `(area_sqft, density_gpm_per_sqft)` control points.

Each curve defines the relationship between design area size and required water density. Larger design areas require lower density; smaller areas require higher density.

### 11.3 Interpolation

Two helper functions:

- `_interpolate_density(hazard, area_sqft)` → density (gpm/ft²)
  - Linear interpolation between curve control points
  - Clamped to curve endpoints outside range

- `_interpolate_area(hazard, density)` → area (ft²)
  - Inverse interpolation: given a density, find the corresponding area
  - Sorts by density ascending for lookup

### 11.4 Design Area Selection

A DesignArea contains a geometric boundary (polygon) defining which sprinklers belong to it. The sprinkler list is determined by spatial containment within the room boundary.

Output to hydraulic solver: list of design sprinklers + hazard classification.

### 11.5 Coverage & Spacing

Auto-populate computes S (short) and L (long) spacing for placed sprinklers based on actual placement geometry:
- S spacing: distance between sprinklers along branch lines
- L spacing: distance between branch lines

Values written to `Sprinkler._properties["S Spacing"]` / `["L Spacing"]` as formatted display strings (unit-aware via ScaleManager).

---

## 12. Template Lifecycle & Data Flow

### 12.1 Initialization

At application startup (`MainWindow.__init__`):
- `current_sprinkler_template = Sprinkler(None)` — headless instance with default properties
- `current_pipe_template = Pipe(None, None)` — headless instance with default properties
- Both receive a `_scene_ref` for ScaleManager access (survives `_clear_scene` resets)

### 12.2 Persistence

Template properties saved to / restored from `QSettings("GV", "FirePro3D")`:
- Key: `template/sprinkler` — dict of property key → value
- Key: `template/pipe` — dict of property key → value

Survives application restarts.

### 12.3 Update Sources

| Source | Updates template? | Mechanism |
|---|---|---|
| Sprinkler Manager "Use as Template" | Yes | `_apply_sprinkler_template_from_record(record)` |
| Property panel edit on placed sprinkler | No | Only modifies the placed instance |
| Auto-populate dialog | No | Uses SprinklerRecord directly for batch placement |

### 12.4 Placement Flow

1. User clicks sprinkler mode button → `scene.set_mode("sprinkler", template)`
2. User clicks on a node → sprinkler added to that node
3. User clicks on a pipe → pipe split, new intermediate node created, sprinkler added
4. `sprinkler.set_properties(template)` copies all template property values to the new instance
5. Fitting auto-updates on affected nodes

### 12.5 Mode Persistence

The template object persists on `MainWindow` across mode switches. Re-entering sprinkler mode passes the same template instance. The template is never destroyed during the session — only its property values change.

---

## 13. Serialization & Backward Compatibility

### 13.1 Node Serialization

**Saved fields:** position (x, y), `elevation` (z_pos), `ceiling_level`, `ceiling_offset_mm`, level, layer, sprinkler properties (if sprinkler present). `z_offset` is no longer written (removed 2026-05-03).

**Load migration:**
1. Read `ceiling_level` and `ceiling_offset_mm` (current format)
2. If `ceiling_offset_mm` absent, derive from legacy `ceiling_offset` field (inches → mm)
3. Recompute `z_pos` from level manager; fall back to `elevation` field if level not found
4. Old `z_offset` field is ignored (read only for clipboard backward compat)

### 13.2 Pipe Serialization

**Saved fields:** node references (by index into node list), all `_properties` values, per-node ceiling fields (`node1_ceiling_level`, etc.).

**Backward compat:** Old save files containing pipe-level `ceiling_level`/`ceiling_offset_mm` fields are silently ignored on load; all ceiling data is read from endpoint Node attributes.

**Stability:** Diameter internal keys (`"1\"Ø"` format), schedule strings, and material strings are stable across versions. No migration needed.

### 13.3 Sprinkler Serialization

Embedded within parent Node's serialization as a `_properties` dict snapshot. All values stored as strings. Legacy property names (`"Elevation"`, `"Elevation Offset"`, `"Ceiling Offset (in)"`) accepted on load and mapped to current names.

### 13.4 Backward Compatibility Rules

| Scenario | Strategy |
|---|---|
| New optional field missing on load | Provide default value |
| Renamed field | Accept both names in `set_property()` |
| Removed field present in old save | Silently ignore |
| Type coercion needed | Parse with fallback (e.g. `float(value)` with except) |

No format version bump required for any currently-flagged divergence. All migrations are graceful (read old → use new internally → write new on next save).

---

## 14. Divergences & Migration Paths

| # | Divergence | Priority | Current Behavior | Target Behavior | Migration |
|---|---|---|---|---|---|
| D1 | Database path + singleton | P1 | CWD-relative `sprinklers.json`; 3 independent instances (MainWindow, model_space, property_manager) | Stable path (`%APPDATA%/FirePro3D/sprinklers.json`); single shared instance on MainWindow passed to all consumers | Move path to platform-appropriate app data dir. Remove direct `SprinklerDatabase()` calls; accept instance parameter everywhere. |
| D2 | SprinklerRecord missing fields | P2 | 10 fields (see §4.1) | Add optional: `response_type` (SR/QR/EC/ESFR), `max_s_spacing` (ft), `max_l_spacing` (ft), `thread_size`, `listing`, `deflector_min` (in), `deflector_max` (in) | Add fields with defaults to dataclass. `from_dict` provides defaults for missing fields. No breaking change. |
| D3 | "Concealed" missing from Orientation | P1 | Sprinkler Orientation options: Upright, Pendent, Sidewall | Add "Concealed" to options list | One-line change to `Sprinkler._properties["Orientation"]["options"]`. |
| ~~D4~~ | ~~z_offset dual computation path~~ | ~~P2~~ | **Resolved 2026-05-03.** `ceiling_offset` is now sole source of truth. `z_offset` no longer written on save/copy. Old files still read for backward compat. All computation sites (move-to-level, paste, property manager) unified. | | |
| ~~D5~~ | ~~C-Factor user-editable~~ | ~~P2~~ | **Resolved 2026-05-03.** C-Factor is now read-only and auto-derived from Material via `MATERIAL_C_FACTOR` mapping. CPVC added as material option. Old saves: C-Factor re-derived from Material on next edit. | | |
| ~~D6~~ | ~~Missing pipe sizes~~ | ~~P2~~ | **Resolved 2026-05-03.** 11 sizes: ¾", 1", 1-¼", 1-½", 2", 2-½", 3", 4", 5", 6", 8". All added to `_INTERNAL_DIAMETERS`, `NOMINAL_OD_IN`, `INNER_DIAMETER_IN` (all 5 schedules), imperial/metric display mappings. | | |
| D7 | SVG symbols limited & orientation-blind | P3 | 3 generic symbols; no orientation-driven selection | Asymmetric sidewall symbol (triangle); orientation-driven symbol auto-selection; wall auto-detection for sidewall orientation; tab-cycle orientation input; in-app symbol editor (create/edit/delete) | Multi-phase: (1) Add sidewall triangle SVG + orientation→symbol mapping, (2) Wall proximity detection for orientation prediction, (3) Symbol editor UI. Each phase is a separate implementation task. |
| D8 | Singleton SprinklerSystem | P3 | One SprinklerSystem per project; one supply_node; all items in one container | Per-node/pipe system assignment; multiple SprinklerSystem instances; independent supply nodes; per-system hydraulic calculations | Requires: system ID field on Node/Pipe, system selector UI, serialization extension, hydraulic solver multi-run. Major architectural change — separate spec recommended. |
| D9 | Sprinkler Manager template bug | P1 | `main.py` uses wrong keys (`"Temp Rating"`, `"Type"`) and omits Manufacturer/Model when applying a SprinklerRecord as template | Use correct keys (`"Temperature"`, `"Orientation"`) and transfer all fields matching auto-populate path | Fix key strings in `_apply_sprinkler_template_from_record()`. Add Manufacturer and Model transfer. |

---

## 15. Testing Strategy

### 15.1 Unit Tests — SprinklerDatabase

| Test | Assertion |
|---|---|
| CRUD round-trip | add → save → new instance from same file → record present |
| Duplicate template prevention | starring same id twice → templates list has one entry |
| Filter query | `find_records(manufacturer="Viking", type_="Pendent")` → correct subset |
| Empty/corrupt file recovery | missing or malformed JSON → falls back to 15 defaults |
| Delete persistence | delete → save → reload → record absent |

### 15.2 Unit Tests — Diameter/Schedule Tables

| Test | Assertion |
|---|---|
| Full matrix coverage | Every `_INTERNAL_DIAMETERS` × every schedule → valid positive float |
| OD table coverage | Every `_INTERNAL_DIAMETERS` key → entry in `NOMINAL_OD_IN` |
| Imperial round-trip | internal → `_INT_TO_IMPERIAL` → `_DISPLAY_TO_INT` → same internal key |
| Metric round-trip | internal → `_INT_TO_METRIC` → `_DISPLAY_TO_INT` → same internal key |
| Fallback | Unknown combo in `get_inner_diameter()` → 2.067 |

### 15.3 Unit Tests — Fitting Assignment

| Test | Assertion |
|---|---|
| 0 pipes | → `no fitting` |
| 1 pipe | → `cap` |
| 2 pipes at 180° | → `no fitting` |
| 2 pipes at 90° | → `90elbow` |
| 2 pipes at 45° | → `45elbow` |
| 2 pipes at 170° | → `no fitting` (within 10° of 180°) |
| 3 pipes with 90° pair | → `tee` |
| 3 pipes all at 120° | → `wye` |
| 4 pipes, perpendicular pairs | → `cross` |
| 4 pipes, irregular | → `no fitting` |
| 1 vertical + 1 horizontal | → `elbow_up` or `elbow_down` |
| 1 vertical + 2 horizontal | → `tee_up` or `tee_down` |

### 15.4 Unit Tests — Node Z-Position

| Test | Assertion |
|---|---|
| Normal computation | level elev 3000mm + offset -50.8mm → z_pos = 2949.2mm |
| Level not found | z_pos unchanged (no crash) |
| No scene | z_pos unchanged (no crash) |
| Ceiling Level change | triggers recomputation with new level elevation |
| Ceiling Offset change | triggers recomputation with new offset |

### 15.5 Unit Tests — Record → Properties Transfer

| Test | Assertion |
|---|---|
| Template application | K-Factor, Min Pressure, Coverage Area, Temp, Orientation match record |
| Orphaned record fields | orifice, notes do not appear in sprinkler properties |
| Instance-only fields preserved | Design Density, S Spacing unaffected by template apply |
| Concealed type | sets Orientation to "Concealed" (documents current behavior) |

---

## 16. Acceptance Criteria

1. Spec documents all current behavior for the 8 subsystems with sufficient detail that a developer unfamiliar with the code can predict behavior from the spec alone.
2. All 8 divergences are flagged with priority, current behavior, target behavior, and migration path.
3. Design invariants are explicitly marked as intentional (not accidental) with rationale.
4. Data flow between this spec's components and the hydraulic solver is defined as a clear interface boundary (§3.3).
5. Field mapping table (§4.4) accounts for all fields in both SprinklerRecord and Sprinkler._properties with no undocumented orphans.
6. Testing expectations define concrete test cases (not just "test X") for each of the 5 areas.

## 17. Verification Checklist

- [ ] Every `SprinklerRecord` field documented with type, units, and purpose
- [ ] Every `Sprinkler._properties` key documented with source (DB, computed, user, node)
- [ ] Every `Pipe` property documented with type, default, and options
- [ ] `determine_type` truth table covers all pipe-count × angle combinations
- [ ] Vertical pipe logic documented with detection thresholds
- [x] Z-position formula unified on `ceiling_offset` (z_offset deprecated 2026-05-03)
- [ ] Density/area curve data structure and interpolation algorithm described
- [ ] Template lifecycle: creation, update, persistence, placement all documented
- [ ] Each divergence has: current behavior, target behavior, priority, migration steps
- [ ] Serialization section covers backward-compat for all flagged changes
- [ ] All 5 test areas have specific, executable test case descriptions
