---
status: current          # §10–§11 code-verified as-built; divergence ledger in §14
last-verified: 2026-07-14
verified-commit: 5ba9227
applies-to:
  - firepro3d/sprinkler.py
  - firepro3d/sprinkler_db.py
  - firepro3d/sprinkler_system.py
  - firepro3d/fitting.py
  - firepro3d/water_supply.py
  - firepro3d/design_area.py
  - firepro3d/nfpa_curves.py
  - firepro3d/design_point_dialog.py
---

# Sprinkler System Components Specification

**Status:** Current  
**Date:** 2026-04-28  
**Scope:** Document current behavior + flag divergences with migration paths  
**Impl note (2026-07-13):** §11 rewritten as-built after the design-area polish task (`feat/design-area-polish`) — two-value geometry (calc As vs drawn tiles), creation/pick UX, multi-area flow, derived level, two-state rendering, Display Manager category, dual-path serialization. Verified against commit `5a1a367`; tests `tests/test_design_area.py`.
**Impl note (2026-07-13, later):** §11.5 tile clipping upgraded — wall-segment **line-of-sight shadow clip** (`_clip_tile_at_walls`) replaces the room-polygon clip as the primary slant defense; the former "no detected room → overshoot" known limitation is retired. Verified against commit `600b6ef`.
**Impl note (2026-07-14):** Design-Area Criteria System — curve data moved to `nfpa_curves.py` (§11.2), room-criteria inheritance + `EffectiveCriteria` (§11.8), dry-system required area (§11.9), DESIGN CRITERIA badge (§11.10), WaterSupply Test Date + Domestic Water Allowance (§10.2). Room-side criteria storage owned by `wall-room-floor-system.md §9`. Tests: `tests/test_design_criteria.py`, `tests/test_nfpa_curves.py`, `tests/test_room_criteria.py`.

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
│  DesignArea (criteria + badge, sprinkler set — §11)     │
│  nfpa_curves (density/area curve data — §11.2)          │
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
| manufacturer | → | Manufacturer | Both paths transfer |
| model | → | Model | Both paths transfer |
| type | → | Orientation | Both paths use the correct key |
| k_factor | → | K-Factor | Both paths work correctly |
| min_pressure | → | Min Pressure | Both paths work correctly |
| coverage_area | → | Coverage Area | Both paths work correctly |
| temp_rating | → | Temperature | Both paths format as `"155°F"` |
| orifice | ✗ | — | Not transferred to placed sprinklers |
| notes | ✗ | — | Not transferred to placed sprinklers |
| — | — | Design Density | Set by auto-populate, not from DB |
| — | — | S Spacing / L Spacing | Computed by design_area |
| — | — | Graphic | User-selected SVG variant |
| — | — | Ceiling Level / Ceiling Offset | From parent Node |
| — | — | X / Y / Z | Read-only, from Node scenePos + z_pos |

**Path note (verified 2026-07-14):** Two template application paths exist — auto-populate (`model_space.py`, sets `_properties[key]["value"]` directly) and the Sprinkler Manager "Use as Template" (`main.py::_apply_sprinkler_template_from_record`, via `set_property`). Both now transfer all seven mapped fields with correct keys (the former `"Temp Rating"`/`"Type"` wrong-key bug is fixed — §14 D9 resolved).

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
- **Display override:** `fitting._display_overrides["visible"] == False` forces the fitting symbol hidden regardless of other visibility rules. Set via model browser Hide/Show context menu.

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

Fittings are listed in the model browser under a "Fittings (N)" group with individual hide/show support.

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
| Test Date | string | "" | flow-test date (free text; shown in the hydraulic report header) |
| Hose Stream Allowance | enum | 250 GPM | 100 GPM, 250 GPM, 500 GPM |
| Domestic Water Allowance | string | 0 | gpm — **informational this task** (shown on the design-criteria badge, §11.10); adding it to solver demand is a planned follow-up (grill 2026-07-14) |

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
- `hose_stream_allowance` → float gpm (parsed from "250 GPM" format; fallback 250.0)
- `domestic_allowance_gpm` → float gpm (badge consumer only — not in the solver demand)

---

## 11. Design Area & NFPA 13 Curves

### 11.1 Hazard Classification (inherited/effective — as-built 2026-07-14)

The DesignArea's hazard is normally **inherited from the rooms containing its member sprinklers** (§11.8), not set directly. The stored `_properties["Hazard Classification"]` enum (options = `HAZARD_OPTIONS`, the five curve-bearing NFPA 13 occupancy classes: Light, OH1, OH2, EH1, EH2) is the *fallback* used when no room criteria govern, and is **overwritten by write-back** while inheritance is engaged (so a later disengage keeps the last effective value).

Room-side hazard classes (8, including the three storage classes) and their per-sprinkler coverage limits are owned by `wall-room-floor-system.md §9.2` + `constants.py` (`HAZARD_CLASSES`, `NFPA_MAX_COVERAGE_SQFT`). Storage classes have no density/area curve and **disengage** inheritance (§11.8).

### 11.2 Density/Area Curves — `nfpa_curves.py`

`DENSITY_AREA_CURVES` — NFPA 13 Figure 11.2.3.1.1 data. **Single home: `firepro3d/nfpa_curves.py`** (moved out of `auto_populate_dialog.py` 2026-07-14; the dialog re-imports the data and re-aliases the helpers as `_interpolate_density`/`_interpolate_area` for its internal call sites). No Qt imports — safe for any module. Also home to `HAZARD_ABBREV` (LH/OH1/…, used by badges and warnings) and `STORAGE_HAZARDS` (the three curve-less storage classes).

Structure: `dict[str, list[tuple[float, float]]]` — hazard class name → list of `(area_sqft, density_gpm_per_sqft)` control points.

Each curve defines the relationship between design area size and required water density. Larger design areas require lower density; smaller areas require higher density.

### 11.3 Interpolation (`nfpa_curves.py`)

Three helper functions:

- `interpolate_density(hazard, area_sqft)` → density (gpm/ft²)
  - Linear interpolation between curve control points
  - Clamped to curve endpoints outside range
  - No-curve hazard (storage/unknown) → 0.10 (Light Hazard minimum) as a safe fallback

- `interpolate_area(hazard, density)` → area (ft²)
  - Inverse interpolation: given a density, find the corresponding area
  - Sorts by density ascending for lookup
  - No-curve hazard → 1500.0 fallback

- `min_design_point(hazard)` → `(area_sqft, density) | None`
  - The smallest-area point on the hazard's curve — the default room design point (`wall-room-floor-system.md §9`); `None` for curve-less hazards

### 11.4 Creation & Pick Mode (as-built 2026-07-13)

Design areas are created in `design_area` mode (`Model_Space._press_design_area`):

- **Click** toggles the nearest sprinkler on the active level within a zoom-aware radius (`DESIGN_AREA_PICK_PX` screen px / view scale), using the **raw** cursor position. **Shift+click twice** = rectangle selection (level-filtered). **Right-click confirms** and stays in the mode.
- **Snapping:** general OSNAP/underlay/grid snapping is suppressed in this mode; sprinkler node centres are the only snap target (rendered with the `center` marker). See `Model_Space.get_effective_position`.
- **Non-sprinkler items are inert:** the mode is in `_skip_grip_modes` and the press handler never falls through to item selection.
- **Multiple areas:** the working area (`Model_Space._da_editing`) receives picks. Confirm clears it — the next pick on an unclaimed sprinkler starts a **new** design area; picking a member of an existing area **resumes editing** that area. `active_design_area` (the calc input) is the last edited/confirmed area.
- **Feedback:** orange highlight rings (`DESIGN_AREA_HL_RADIUS_PX`) mark the working area's sprinklers; every toggle recomputes and shows `count + area` in the status bar, pushes the area to the property panel (`requestPropertyUpdate`), and emits `sceneModified` (model browser + dirty flag).

Output to hydraulic solver: list of design sprinklers + effective criteria (§11.8). `Model_Space.run_hydraulics` prepends `spacing_warnings` and then `EffectiveCriteria.warnings` to `HydraulicResult.messages` (criteria warnings lead), and pushes the badge snapshot (§11.10).

### 11.5 Two-Value Geometry: Calc As vs Drawn Tiles (as-built 2026-07-13)

Each member sprinkler carries **two deliberately different values**:

**Calc (`As`)** — NFPA 13 measurement convention, capped at the listing:
- `S`/`L` from `_compute_s_l`: max(distance to next sprinkler via branch walk, 2× nearest aligned wall distance) per axis; `_fallback_side` (√listed-coverage square) when undetermined.
- `As = min(S×L, listed Coverage Area)`. When `S×L` exceeds the listing, the cap applies **and** a warning is recorded in `DesignArea.spacing_warnings` (spacing violates the listing — surfaces at the top of the hydraulic report).
- `Area` property = Σ capped As (numeric, in `_as_entries`; no display-string parsing).
- `S Spacing`/`L Spacing` sprinkler properties keep showing the NFPA values.

**Drawing (tiles)** — tessellating, wall-clipped (`_tile_extents` + `_tile_polygon`):
- Per-side extents: half the gap to the nearest neighbour on that side (branch walk along S; perpendicular projection for L), the full distance to the first wall hit by a **ray-cast** in that direction (`_wall_distance_on_side` — any wall angle), or √(listed coverage)/2 on open sides; nearer bound wins.
- Tiles are additionally **clipped to the containing room polygon** (when one contains the sprinkler).
- **Wall-segment shadow clip** (`_clip_tile_at_walls`, 2026-07-13): flat per-side extents can't express a slanted boundary, and the room clip no-ops when the stored room boundary lacks the diagonal edge (stale snapshot §8.5, unconnected/dead-end diagonal, no room). Each nearby wall segment (bbox-prefiltered, level-filtered, ends extended 10 mm to seal junction gaps) casts a **line-of-sight shadow quad** from the sprinkler's viewpoint, subtracted from the tile; the connected piece containing the sprinkler is kept. Tiles stop at physical walls regardless of room state; coverage survives past an open wall end only where the sprinkler has sight lines. Sprinklers within 1 mm of a wall line cast no shadow from it.
- Tiles are inflated ~10 mm before `QPainterPath.united` so exactly-touching rows merge seamlessly; the union is `simplified()`.

### 11.6 Rendering, Level & Persistence (as-built 2026-07-13)

- **Two visual states**, keyed on scene mode: *editing* (`design_area` mode) = fill + faint interior tile edges, below geometry; *confirmed* = dashed outline tracing the union boundary (L-shapes keep their notch), above all geometry and gridline bubbles. Z values live in `constants.py` (`Z_DESIGN_AREA`, `Z_DESIGN_AREA_CONFIRMED`; ordering owned by `view-relationships.md §7.3`); `DesignArea.sync_z_for_mode` switches them.
- **Display Manager:** "Design Area" category (Fire Suppression group) — `color` = confirmed outline, `fill` = editing hue, plus opacity/visibility; applied via `_display_color`/`_display_fill_color` and `apply_category_defaults` at creation/load.
- **Level is derived, read-only:** `DesignArea.level` reports the member sprinklers' node level (creation-time value is only the empty-area fallback); shown as a read-only `Level` label property. Level visibility is applied by `level_manager.apply_to_scene`.
- **Persistence:** design areas serialize through **both** independent paths — `scene_io.py` (project files) and `_capture_network`/`_restore_network` (undo) — with `sprinkler_node_ids`, `properties`, `is_active`, `level`, `badge_offset` (`None` unless the badge was user-moved — §11.10). `properties` is the **raw stored** dict (`{key: value}`), which as of 2026-07-14 includes `System Name`, `System Type`, `Design Area (Base)` (ft², NFPA basis) and `Show Badge` alongside `Hazard Classification` — the synthesized display rows from `get_properties()` (§11.8) are *not* persisted. Missing `level` (pre-2026-07 saves) backfills from member sprinklers. Missing `badge_offset` keeps auto-centre. **Both load paths recompute tiles only after walls & rooms are restored** (earlier compute produces wall-less, over-wide tiles).

### 11.7 Coverage & Spacing (auto-populate)

Auto-populate computes S (short) and L (long) spacing for placed sprinklers based on actual placement geometry:
- S spacing: distance between sprinklers along branch lines
- L spacing: distance between branch lines

Values written to `Sprinkler._properties["S Spacing"]` / `["L Spacing"]` as formatted display strings (unit-aware via ScaleManager).

The auto-populate dialog also **seeds its density/area graph from the room's Protection Criteria design point** (`room.design_point()`) on open, so the room's chosen point pre-selects on the curve.

### 11.8 Criteria Inheritance (as-built 2026-07-14)

`DesignArea.effective_criteria()` resolves hazard / design point / system type from the rooms containing the member sprinklers and returns an **`EffectiveCriteria`** dataclass: `hazard`, `base_area_sqft`, `density`, `system_type` ("Wet" | "Dry"), `inherited`, `governing_room`, `required_area_sqft`, `drawn_area_sqft`, `warnings`.

**Room membership:** `member_rooms()` → (rooms on the design area's level whose polygon contains a member sprinkler's node, plus a count of roomless member sprinklers). Point-in-polygon on `Room.boundary`; a shared internal `_effective_criteria_impl(rooms, roomless)` lets `get_properties()` and `badge_rows()` reuse one room scan per call.

**Resolution rules (grill 2026-07-14):**

1. **All rooms have curve-bearing hazards → inheritance engages.** Hazard = most demanding across rooms (rank = index in `HAZARD_OPTIONS`); among rooms tied at the top hazard, the room with the **largest design-point base area** governs. Design point = the governing room's `design_point()` (room-side semantics owned by `wall-room-floor-system.md §9`). System type = **Dry if any member room is Dry**, else Wet. Inherited values are shown **read-only** in the panel and `set_property()` refuses writes to the three criteria keys while inherited.
2. **Write-back:** the resolved hazard / system type / base area are written back into the DesignArea's stored `_properties`, so a later **disengage keeps the last effective values** instead of reverting to stale defaults.
3. **Disengage:** any member room with a curve-less hazard (`STORAGE_HAZARDS` or unknown) disengages inheritance — the area's own stored values govern, with a warning ("requires storage protection criteria (not yet supported)" for storage classes, "has no density/area curve" otherwise). No rooms at all → own stored values, density from `interpolate_density(hazard, base)`.
4. **Warnings** (accumulated on `EffectiveCriteria.warnings`): multi-room span (lists each room's `HAZARD_ABBREV` and names the governing hazard), roomless design sprinklers ("room criteria govern"), the disengage cases above, and the required-area shortfall (§11.9).

**Panel view:** `get_properties()` overlays the resolved criteria onto the stored dict and appends synthesized display rows — `Design Density` and `Required Area` (labels), `Criteria From` (governing room, only when inherited), `Rooms` (member-room list), and `Warnings` (**`warning` type, always last**). `Design Area (Base)` displays/edits in project units but stores ft² (`units-and-formatting.md §4`); row rendering/widget types are owned by `property-panel.md §3.2`.

### 11.9 Dry-System Required Area

`required_area_sqft = base_area_sqft × 1.3` when the effective system type is **Dry** (NFPA 13 +30% for dry systems), else `× 1.0`. When the drawn area (Σ capped As, §11.5) falls **below** the required area, a shortfall warning is appended ("enlarge the sprinkler selection", noting "+30% dry system" when applicable). The panel's Required Area row and the hydraulic report's Required Area line carry the same "+30% dry" annotation.

### 11.10 Design Criteria Badge (as-built 2026-07-14)

`DesignAreaBadge` — a child `QGraphicsItem` of its DesignArea rendering the AHJ "DESIGN CRITERIA" table on the drawing. Sized in model-space mm via the `DA_BADGE_*` constants (`constants.py`); its unit spellings (`usgpm`, `ft²`) are the deliberate AHJ exception to project units (`units-and-formatting.md §5`). Locked at the 2026-07-14 mockup gate.

- **Rows — fixed 10-row layout** (`badge_rows()`; title + 8 content rows + blank footer band mirroring the title row height): DESIGN CRITERIA title; SYSTEM ID / ZONE (system name / WET|DRY); OCCUPANCY (hazard abbrev — governing room's `_occupancy`, falling back to the first non-empty member room's) / SYSTEM CAPACITY (Dry → `system_capacity_gal(pipes)`, the network water volume from pipe IDs × lengths; Wet → "N/A"); DENSITY / AREA OF APPLICATION (drawn area); COVERAGE PER SPRINKLER / STORAGE HEIGHT ("N/A"); ORIFICE / "K" FACTOR (orifice via the `K_TO_ORIFICE` nominal-size map); HOSE ALLOWANCE INSIDE/OUTSIDE (TBD); DOMESTIC WATER ALLOWANCE (from WaterSupply, §10.2) / SPRINKLERS CALCULATED; the TOTAL DEMAND banner line. K-factors and coverage lists **dedupe on numeric value** (`"130"` vs `"130.0"` collapse). Missing calc data renders `TBD`. The fixed row count lets `boundingRect()` derive from constants alone (no scene traversal in Qt's hottest geometry callback); rows recompute on every paint (live with room edits).
- **Hydraulic snapshot:** `Model_Space.run_hydraulics` pushes `_hyd_snapshot` (`total_demand_gpm`, `demand_psi`, `remote_head_psi` = min required pressure across design sprinklers, `sprinklers_calculated`, `hose_gpm`) onto the active area — `None` when the solve produced no data. **Membership changes (`add_sprinkler`/`remove_sprinkler`) clear the snapshot** (stale results must not survive a changed selection); the badge shows TBD cells until the next run.
- **Drag — grip protocol, not item drag:** the badge has **no `ItemIsMovable`** — Model_Space never forwards select-mode presses to Qt items, so native item drag is dead scene-wide. Instead the parent DesignArea exposes one grip at the badge centre (`grip_points()`/`apply_grip()`, Room-label precedent). `itemChange` sets `_badge_user_moved` and emits `sceneModified` (suppressed via a `_syncing` flag during auto-centre and load).
- **Auto-centre:** until `_badge_user_moved`, `_sync_badge()` re-centres the badge on the tile-union bounding-rect centre after every shape recompute.
- **Visibility:** shown only when the area is **confirmed** (scene not in `design_area` mode), the `Show Badge` bool property is on, and the area has members.
- **Persistence:** `badge_offset` in both serialization paths (§11.6); `set_badge_offset()` on load sets `_badge_user_moved` so auto-centre doesn't override the restored position.
- **Selection:** bare `DesignArea` is deliberately **not** click-selectable — it sits above everything with a filled tile-union path, so interior clicks would steal room/wall selection. Rubber-band selection selects the area. The badge is the only click target: `mousePressEvent`'s fallback filter accepts a `DesignAreaBadge` hit and resolves it to the parent `DesignArea` (mirrors Sprinkler→Node; the `ItemIsSelectable` check applies to the resolved parent), so a badge click selects the area — the grip-drag entry point. Functional coverage: `tests/test_design_criteria.py::TestBadgeClickSelection` (badge click selects; interior click does not).

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

**Saved fields:** position (x, y), `elevation` (z_pos), `ceiling_level`, `ceiling_offset_mm`, level, `room_name`, sprinkler properties (if sprinkler present). `z_offset` is no longer written (removed 2026-05-03); the per-item layer field is gone (layer system removed).

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
| ~~D9~~ | ~~Sprinkler Manager template bug~~ | ~~P1~~ | **Resolved (verified 2026-07-14).** `_apply_sprinkler_template_from_record()` uses the correct keys (`"Temperature"`, `"Orientation"`) and transfers Manufacturer and Model — both template paths now match (§4). | | |
| ~~D10~~ | ~~Badge-click select resolve inert~~ | ~~P1~~ | **Resolved 2026-07-14.** `mousePressEvent`'s fallback filter now accepts a `DesignAreaBadge` hit directly and resolves it to the parent `DesignArea` (selectability checked on the parent); bare `DesignArea` stays out of the filter, so the interior click-steal fix stands (§11.10). Functional tests `TestBadgeClickSelection` + guard test `TestSelectModeFilter` in `tests/test_design_criteria.py`. | | |

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
