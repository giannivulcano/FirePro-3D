# View Relationships — Specification

> **Status:** Approved (Revision 1, post grill session)
> **Date:** 2026-04-08
> **Source tasks:** TODO.md "Spec & grill session: define and refine the relationship between views" (P1, Architecture)
> **Adjacent specs:** `pipe-placement-methodology.md`, `snapping-engine.md`
> **Pattern:** Documents current behavior + names required fixes (same revision style as `pipe-placement-methodology.md` Rev 2).

---

## 1. Goal & Motivation

### 1.1 Goal

Establish a single source of truth for **how views in FirePro3D relate to the data model and to each other**, so that future feature work (section views, drafting overrides, view templates) has a stable contract to build against and existing bugs (view range, depth sort) have a target to be fixed *to*.

### 1.2 Motivation

FirePro3D models a 3D world (walls, pipes, sprinklers, rooms at real elevations in millimeters) but **authors all geometry in 2D plan view** with Z assigned by property. That dual nature — 2D input, 3D semantics — is the source of every "the elevation looks wrong" / "the room is at the wrong height" / "the pipe shows in the wrong view" bug. Without a written contract, every view-related change has to re-derive the same assumptions from code, and the assumptions drift.

This spec is the contract.

### 1.3 What this spec does NOT cover

These are explicitly out of scope and have their own future spec sessions:

- **Cross-view selection / interaction sync** — clicking an item in one view highlighting it in another. Self-contained interaction-design problem.
- **Override resolution rules** — what wins when two drafting overrides conflict. Will be a "view templates" spec once the override catalog (§7) lands.
- **Paper-viewport-specific overrides** on top of view-instance overrides. Future extension.
- **Editing geometry from elevation or 3D views.** The current contract is strict 2D-plan authoring (§3.1); allowing edits in elevation is a planned future extension, not a current commitment.
- **Hydraulic / NFPA semantics**, sprinkler placement algorithms, pipe routing — already covered by `pipe-placement-methodology.md` and adjacent specs.

---

## 2. Vocabulary

The word "view" is overloaded in the codebase (`Model_View`, `View3D`, `ElevationView`, `DetailViewManager`, `ViewMarker`, `ViewRangeDialog`, `ViewCube`). The spec uses these explicit terms throughout:

| Term | Meaning |
|---|---|
| **Data model** | The domain objects: `WallSegment`, `Pipe`, `Node`, `Sprinkler`, `Room`, `FloorSlab`, `Roof`, `Level`, etc. The single source of truth. Stored in the project file. |
| **Base view type** | One of three abstract projections: **plan**, **section**, **3D**. See §4. |
| **View instance** | A concrete configured projection: e.g. *"plan view, Level 2, view range 2700–4900 mm, scale 1:50"*. A project has many. |
| **View widget** | The Qt object that renders an instance to the screen (`Model_View`, `ElevationView`, `View3D`). Implementation detail; the spec rarely talks about widgets directly. |
| **View scene** | The `QGraphicsScene` a view widget renders. Today this is either the shared `Model_Space` (plan, detail, paper viewport) or a per-view scene rebuilt from the data model (`ElevationScene`). See §5. |
| **View marker** | A marker placed in a parent view that defines a child view instance: detail markers, elevation markers (and, planned, section markers). See §6. |
| **Parameterization** | A specialization of a base view type that does not warrant being a base type of its own. Detail = parameterized plan. Elevation = parameterized section (cardinal cut line). |
| **World Z** | Real elevation in millimeters. Data. See §3.2. |
| **Render Z** | `QGraphicsItem::zValue()`, an integer painter-order index. Derived from item type and (recently) world Z. See §8. |

Note that **view widget** and **view scene** are *implementation details*. The spec describes the contract; whether two views share a scene or rebuild their own is recorded in §5 as an *observation* and a *constraint on the contract*, not as part of the contract itself.

---

## 3. Foundational Claims

### 3.1 Authoring contract: strict 2D-plan today, elevation editing planned

> **All geometry is authored in plan view. Z is set by property, never by direct manipulation in elevation or 3D. Elevation, section, detail, and 3D views are read-only projections of the data model.**

Consequences:
- The snap engine is 2D (canvas input only) — see `snapping-engine.md`.
- The pipe placement methodology is plan-view-driven — see `pipe-placement-methodology.md`.
- `ElevationView` and `View3D` provide pan / zoom / fit / coordinate display, but no geometric editing tools.
- A future "edit in elevation" capability is a **planned extension**: the spec must not introduce constraints that preclude it (e.g. must not assume Z is invisible to view widgets).

### 3.2 Two distinct Z systems

The spec asserts there are **two Z axes** in FirePro3D and they must never be confused:

| | World Z | Render Z |
|---|---|---|
| **Unit** | Millimeters | Painter-order integer |
| **Source** | Data model (level elevations + offsets) | Item type bands + (recently) world Z |
| **Mutable by** | Property edits, level table edits | Renderer (derived) |
| **Used for** | View-range filtering, elevation rendering, 3D rendering, hydraulic Z drops | Plan/detail painter order (which item draws on top in 2D) |
| **Per item** | Yes (or per node, for pipes) | Yes (`QGraphicsItem.zValue()`) |
| **Persists in project file** | Yes (as level + offset) | No — recomputed on load |

Conversion is **one-way**: world Z → render Z, computed by the plan renderer. Render Z → world Z is undefined.

### 3.3 World Z mechanisms (current data model)

This table enumerates every property in the data model that contributes to an object's world Z. **It is the authoritative reference** for "where does this object live in 3D?" — if you add a Z-bearing property and don't update this table, the spec is out of date.

| Object | Attribute | Type | Default | Meaning | Source |
|---|---|---|---|---|---|
| **Level** | `elevation` | float (mm) | Level 1 = 0; Level 2 = 3048; Level 3 = 6096 | Floor elevation of the level | `level_manager.py:68-74` |
| **Level** | `view_top` | float (mm) | 2000 | Default plan view-range top, *relative to elevation* | `level_manager.py:72` |
| **Level** | `view_bottom` | float (mm) | -1000 | Default plan view-range bottom, relative to elevation | `level_manager.py:73` |
| **Pipe** | `ceiling_level` | str (level ref) | "Level 1" | Level the pipe hangs from | `pipe.py:89` |
| **Pipe** | `ceiling_offset` | float (mm) | -50.8 | Offset below `ceiling_level.elevation` | `pipe.py:90` |
| **Pipe** | `node1/2_ceiling_level` | str | "Level 1" | Per-endpoint level (template placement) | `pipe.py:94-97` |
| **Pipe** | `node1/2_ceiling_offset` | float (mm) | -50.8 | Per-endpoint offset (template placement) | `pipe.py:94-97` |
| **Node** | `z_pos` | float (mm) | computed | World Z; `_recompute_z_pos()` derives from `ceiling_level + ceiling_offset` | `node.py:32, 95-111` |
| **Node** | `z_offset` | float | constructor `z` | **Legacy** field; pre-`z_pos` saves; do not use in new code | `node.py:33` |
| **Sprinkler** | `ceiling_level` | str | "Level 1" | Inherits from parent node via property panel | `sprinkler.py:43` |
| **Sprinkler** | `ceiling_offset` | float (mm) | -50.8 | Same mechanism as pipe | `sprinkler.py:44` |
| **WallSegment** | `_base_level` | str | "Level 1" | Wall bottom level | `wall.py:131` |
| **WallSegment** | `_top_level` | str | "Level 2" | Wall top level | `wall.py:132` |
| **WallSegment** | `_height_mm` | float | 3048 | Fallback height if `_top_level` is unset | `wall.py:133` |
| **WallSegment** | `_base_offset_mm` / `_top_offset_mm` | float | 0 | Reserved (not currently applied) | `wall.py:134-135` |
| **Room** | `level` (inherited) | str | "Level 1" | Floor level | `room.py:74-87` |
| **Room** | `_ceiling_level` | str | "Level 2" | Ceiling level | `room.py:93` |
| **Room** | `_ceiling_offset` | float (mm) | 0 | Offset below ceiling level | `room.py:94` |
| **Room** | `z_range_mm()` | method | computed | Returns `(floor_z, ceil_z)` — see §7.2 for formula and known issues | `room.py:124-144` |
| **FloorSlab** | `level` (inherited) | str | "Level 1" | Slab top sits at this level | `floor_slab.py:62` |
| **FloorSlab** | `_level_offset_mm` | float | 0 | Vertical offset from level | `floor_slab.py:60` |
| **FloorSlab** | `_thickness_mm` | float | 152.4 | Slab thickness; bottom Z = top Z − thickness | `floor_slab.py:59` |
| **Roof** | `level` (inherited) | str | "Level 1" | Roof base elevation | `roof.py:23` |
| **Roof** | (slope/pitch) | — | flat | Pitch affects 3D only; 2D treats roof as flat at level elevation | `roof.py:28-30` |
| **Underlay** (DXF/PDF) | (none) | — | Z = 0 | Always at world Z = 0; not configurable | `underlay.py` |
| **ViewMarker** (elevation/section) | `level` | str | "Level 1" | Marker sits on this level (no Z extent) | `view_marker.py:159` |
| **DetailMarker** | `level` | str | "Level 1" | Same | `detail_view.py:81` |
| **DetailMarker** | `_view_height` / `_view_depth` | float \| None | None | Optional Z-range override; inherits from parent plan if None | `detail_view.py:61-62` |

**Resolution rule.** When multiple mechanisms could supply Z for the same object (e.g. pipe carries `ceiling_level`/`ceiling_offset` AND its endpoint nodes carry `z_pos`), **the node values are authoritative** for placed pipes; the pipe's own `ceiling_level`/`ceiling_offset` are template defaults applied at placement time.

---

## 4. View Type Taxonomy

### 4.1 Three base projections

| Base type | Cut plane | Look direction | Implementation today |
|---|---|---|---|
| **Plan** | Horizontal slab `[z_bottom, z_top]` | Top-down (-Z) | `Model_View` rendering `Model_Space` |
| **Section** | Vertical line in plan + look direction + depth | Horizontal | `ElevationView` rendering `ElevationScene` (cardinal cut line only) |
| **3D** | None (full model) | Camera-controlled | `View3D` (vispy/PyVista) |

Section as a first-class subsystem with arbitrary cut lines is **planned**, not implemented. Today only the cardinal-line specialization (elevation) exists.

### 4.2 Parameterizations

A parameterization is a specialization of a base type that uses the same projection math but adds bounds, scale, or display settings.

| Parameterization | Base | Specialization |
|---|---|---|
| **Detail view** | Plan | Adds a crop rectangle (`_clip_rect`) and a fit-to-crop transform. No independent scale or visibility overrides today (see §7.4). |
| **Elevation view** | Section | Cut line is constrained to a cardinal axis (N/S/E/W); look direction implicit. |
| **Section view** *(planned)* | Section | Removes the cardinal-axis constraint. |

### 4.3 Paper viewport (frame, not a base type)

A **paper viewport** is not a view type — it is a **frame** placed on a paper sheet that hosts a parameterization of any base type. Today only plan is hosted (`PaperViewport` calls `Model_Space.render()` into a target rect — `paper_space.py:507`); section/elevation/3D viewport hosting is unimplemented.

### 4.4 Excluded from the taxonomy

These are not view types under this spec, even though their filenames suggest otherwise:
- `view_cube.py` — 3D navigation widget. Part of the 3D view, not its own type.
- `view_range_dialog.py` — UI for editing a view's range. Configures a view, is not a view.
- `dxf_preview_dialog.py` — import-time preview. Not a project view.
- `model_browser.py`, `project_browser.py` — tree widgets. Not graphical views.

---

## 5. Architecture: how view scenes relate to the data model

### 5.1 Current state — hybrid

FirePro3D's view system today is **hybrid**: some views share a scene, others rebuild their own. The spec records this honestly rather than pretending it's uniform.

| View | Scene | Materialization |
|---|---|---|
| **Plan** (`Model_View`) | `Model_Space` (shared) | Items live directly in the scene; data model items ARE the scene items |
| **Detail** (`Model_View` with `_clip_rect`) | `Model_Space` (shared) | Same scene as plan; rendered through a clip rectangle |
| **Paper viewport** (`PaperViewport`) | renders `Model_Space` into a target rect | Direct call to `Model_Space.render(painter, target, src)` |
| **Elevation** (`ElevationView`) | `ElevationScene` (per-instance) | Rebuilt from the data model on demand (`ElevationScene.rebuild()` at `elevation_scene.py:614`; `ElevationManager.rebuild_all()` at `elevation_manager.py:114`); items are `ElevGridlineItem`, `ElevDatumItem`, etc. — distinct from plan items |
| **3D** (`View3D`) | vispy/PyVista internal representation | Rebuilt from the data model |

The pattern is: **plan-family views share `Model_Space`; non-plan views materialize their own representation from the data model.**

### 5.2 Implication: data model items wear two hats in plan-family views

In `Model_Space`, `WallSegment` / `Pipe` / `Sprinkler` / etc. are *both* domain objects *and* `QGraphicsItem` instances. They live in the scene. There is no separation between "the data" and "what plan view draws."

This is fine for plan editing (edits go directly to the data) but it has consequences:

- Adding a non-plan-shaped view of the same data (elevation, 3D) requires materialization, because the items themselves only know how to draw themselves in plan.
- Detail and paper viewport "for free" inherit whatever plan does — including bugs.
- Drafting overrides (§7) cannot be applied per-view unless they are stateful flags on the items themselves OR a render-time override layer is introduced.

### 5.3 Constraint: any future view must be one of two patterns

The spec **constrains** future views to follow one of these two existing patterns:

1. **Plan-family pattern** — operates on `Model_Space` directly, possibly with clipping. Cheap but inherits plan behavior.
2. **Materialization pattern** — owns its scene/representation, rebuilds from the data model on demand, listens to model changes to know when to rebuild.

Introducing a third pattern (e.g. a "shadow scene" with cloned items, or a global scene that all views share with per-view filtering) requires updating this spec first. This is deliberate: two patterns are enough surface area to reason about; three is too many.

---

## 6. View Markers and View Instances

### 6.1 Canonical creation mechanism

> **Parameterized view instances are created by placing a view marker in a parent view.** The marker is the user-facing affordance; the instance is its consequence.

| Marker | Created in | Produces | Persisted |
|---|---|---|---|
| **DetailMarker** | Plan | Detail view instance (parameterized plan, with crop) | Yes (project JSON, via `to_dict()`/`from_dict()` at `detail_view.py:379-412`) |
| **ViewMarkerArrow** (elevation) | Plan | Elevation view instance (parameterized section, cardinal cut line) | Partial — see §6.3 |
| **SectionMarker** *(planned)* | Plan | Section view instance | Not yet implemented |

### 6.2 Marker → instance binding (current)

- **Detail markers** persist by name; the binding is `name → DetailMarker (geometry) + name → Model_View (open tab)`. Opening a detail by name calls `DetailViewManager.open_detail(name)` (`detail_view.py:469-501`) which creates a new `Model_View` with `_clip_rect` set to the marker's crop rectangle and fits the view.
- **Elevation markers** are *ephemeral* in the scene: they hold a back-reference to `ViewMarkerManager` and a direction property (N/S/E/W). Double-clicking emits `scene.openViewRequested.emit("elevation", direction)`, which the UI handles by creating an `ElevationScene` + `ElevationView` on demand.

### 6.3 Known gap

> **Elevation markers do not currently persist in the project file** the way detail markers do. Their *placement* (a shared crop box on plan) may persist via `SharedCropBox`, but the per-direction marker geometry and the open-tab state do not survive a save/reload in a documented way.

This is a follow-up. The spec asserts the contract should be: **all view markers persist; opening a project restores the marker geometry; opening a marker's instance recreates it with the same parameters.** Anything that currently violates this contract is a bug to be fixed.

---

## 7. View Range and Drafting Overrides

### 7.1 View range — the contract

A plan or section view instance is parameterized by a **Z slab** `[z_bottom, z_top]`:

- **Anchor:** the view is anchored to a **level**.
- **Default top:** `level.elevation + level.view_top` (`view_top` defaults to 2000 mm).
- **Default bottom:** `level.elevation + level.view_bottom` (`view_bottom` defaults to −1000 mm).
- **Override:** an instance may override `view_top`/`view_bottom` to non-default values. (Today this is exposed via `view_range_dialog.py`.)
- **Intersection rule:** an item is visible iff its world-Z range (a single value or a `[z_bot, z_top]` returned by `z_range_mm()`) intersects the slab.
- **Cut/clip semantics:** items that *cross* `z_top` may be drawn cut/clipped (e.g. walls show as filled outlines at the cut plane); items that fall *below* `z_bottom` may be drawn dashed or hidden depending on view configuration.

The implementation of intersection + cut today lives in `level_manager.py:33-50` (`_apply_z_filter`).

### 7.2 Room Z formula and the "ceiling vs floor" follow-up

`Room.z_range_mm()` (`room.py:124-144`) currently returns:

```
floor_z = self.level.elevation
ceil_z  = self._ceiling_level.elevation - slab_thickness + self._ceiling_offset
```

where `slab_thickness` is looked up from any `FloorSlab` on the scene whose level matches `_ceiling_level`.

> **This contradicts the TODO entry "Plan Views room Z values seem to be calculated based on ceiling height property rather floor level."** Reading the code, the floor Z is *already* level-derived. The actual likely issue is one of:
>
> 1. The `slab_thickness` lookup is fragile — if no floor slab exists for `_ceiling_level`, the default value used may be wrong, making `ceil_z` look like it ignores floor anchoring.
> 2. `_ceiling_offset` is being applied with the wrong sign for some configuration.
> 3. The display of room Z somewhere in the UI uses a different (ceiling-only) formula than `z_range_mm()`.
>
> **The original TODO entry is replaced by a clearer follow-up** (see §11): *"Investigate why `Room.z_range_mm()` results disagree with user expectations of floor-anchored Z; reconcile with the spec."*

The spec's contract is unambiguous: **room view-range membership is anchored to the floor**, with the ceiling derived as above.

### 7.3 Depth sort — the contract

| View family | Painter ordering |
|---|---|
| **Plan / detail / paper viewport (plan-family)** | Type-based coarse band, then world-Z within band |
| **Elevation (section-family)** | Type-based coarse band, then world-Z within band, projected onto the cut plane |
| **3D** | GPU depth buffer; type bands and world-Z sorting do not apply |

**Coarse type bands today (plan-family).** The codebase has only **two named constants** in `firepro3d/constants.py`:

- `Z_BELOW_GEOMETRY = -100` — underlays, PDFs
- `Z_ROOF = -75` — roof items

All other bands are **scattered magic numbers** at item construction sites. The observed values from the codebase are:

| Band | Value | Items |
|---|---|---|
| Below geometry | -200 | `SharedCropBox` (`view_marker.py:65`) |
| Underlays | -100 | `Z_BELOW_GEOMETRY` |
| Floor slabs | -80 | `floor_slab.py:65` |
| Roof | -75 | `Z_ROOF` |
| Rooms | -60 | `room.py:116` |
| Walls | -50 | (typical, not hardcoded as a constant) |
| Annotations / dimensions | 0 | `annotations.py` |
| Title block (paper space) | 0.5 | `paper_space.py:134, 169` |
| Pipes / paper viewport | 5 | `pipe.py:105`, `paper_space.py:482` |
| Nodes | 10 | `node.py:25` |
| Detail markers | 45 | `detail_view.py:74` |
| Sprinklers / view marker arrows | 200 | `sprinkler.py:53`, `view_marker.py:151` |
| Elevation bubbles (in elevation scene) | 500 | `elevation_scene.py:63` |
| Array preview overlay | 999 | ephemeral UI |

> **Follow-up:** these magic numbers should be extracted to named constants in `constants.py`. The spec is the source of truth for the *order*; `constants.py` will become the source of truth for the *values* once extracted.

### 7.4 Drafting overrides — catalog (current state: aspirational)

> **Honest disclosure: the override system described below does not exist in code today.** Detail views inherit all rendering from the plan they crop; paper viewports are passive `Model_Space` renderings with no per-viewport state. The catalog below is the *target contract* for the future override subsystem, listed here so that view markers and view instances can be designed not to preclude it.

**Override unit:** the **view instance**. (Same instance shown in two paper viewports renders identically.) Per-paper-viewport overrides on top are deferred.

**Override categories the future subsystem must support:**

| # | Category | Examples |
|---|---|---|
| 1 | **Visibility** | Show/hide by user-layer, by item type, by level, by phase (New/Existing/Demo) |
| 2 | **Line weight** | Global multiplier; per-layer / per-type overrides |
| 3 | **Colour** | By-item, by-layer, by-phase, monochrome override |
| 4 | **Line type** | Dash patterns, by-layer |
| 5 | **Scale** | View scale (1:50, 1:100, ...); interaction with text size, marker size, hatch density |
| 6 | **Annotations** | Show/hide labels, dimensions, view markers (e.g. hide section markers in plan when not needed) |
| 7 | **Crop / view range** | Already covered by §7.1; included for completeness so downstream paper viewports may further crop |

**Override resolution rules** — what wins when two overrides conflict — are **deferred to a future spec session** (working title: "view templates"). This spec deliberately defines only the *catalog*, not the *resolution*.

---

## 8. The two-Z conversion rule

For **plan-family views** (plan, detail, paper viewport):

```
render_z(item) = type_band(item) + small_world_z_term(item)
```

where:

- `type_band(item)` is a coarse integer determined by the item's class (the table in §7.3).
- `small_world_z_term(item)` is a small fractional contribution derived from the item's world Z, used to break ties *within* a band so that items at higher world elevation draw on top of items at lower elevation. (Recently completed: "Elevation-based Z-ordering for plan view depth sorting.")

The exact form of `small_world_z_term` is an implementation detail of the renderer, **not** part of the contract. The contract is:

1. Two items in different type bands always sort by type band.
2. Two items in the same type band sort by world Z (higher Z draws on top).
3. The total `render_z` is recomputed when world Z changes (level edits, ceiling-offset edits).

For **section-family views**, the same rule applies but the projection axis is the cut-plane normal, not -Z.

For **3D views**, the rule does not apply: the GPU depth buffer handles ordering from true 3D coordinates.

---

## 9. Open Questions

These are real unknowns the spec did not resolve and that should be answered in implementation tasks or follow-up specs:

1. **Elevation markers persistence** — what's the actual current state? §6.3 records the gap; an investigation task should produce a definitive answer before any "view marker contract" implementation work.
2. **Room Z formula** — is the issue lookup fragility, sign convention, or a UI display path? §7.2 gives three hypotheses; investigation needed before fix.
3. **Section view first cut** — does the first implementation reuse `ElevationScene` or introduce a new scene class? Out of scope for this spec; will be answered when the section subsystem gets its own spec session.
4. **Overrides storage shape** — when the override catalog (§7.4) ships, where do per-instance overrides live? On the view instance object? On a sidecar "view template" object? Resolved by the future view-templates spec.
5. **3D view rebuild triggers** — what data-model changes invalidate the 3D representation today? Not investigated in this spec.

---

## 10. Acceptance Checklist (for the spec itself)

A reader should be able to answer all of these *without reading code*:

- [ ] **Foundational claims.** Authoring contract (strict 2D-plan), planned extension (elevation editing), why. — §3.1
- [ ] **Z model.** What world Z means, what render Z means, the conversion rule, and the enumeration of every world-Z-bearing property. — §3.2, §3.3, §8
- [ ] **Type taxonomy.** Three base projections (plan, section, 3D), parameterizations (detail-from-plan, elevation-from-section), explicit "section is planned." Vocabulary up front. — §2, §4
- [ ] **View instances and markers.** How an instance is created via a marker placed in a parent view; what marker types exist today; what the parent→child binding looks like; the persistence gap. — §6
- [ ] **View range.** Anchor (floor), thickness, intersection rule, cut/clip semantics. Room Z bug honestly diagnosed. — §7.1, §7.2
- [ ] **Depth sort.** Per-view-type contract, type bands as coarse layer + world-Z within band, references `constants.py`, explicit "3D uses depth buffer." — §7.3, §8
- [ ] **Drafting overrides.** Per-instance override model, 7 categories cataloged, explicit "does not exist in code today; resolution rules deferred." — §7.4
- [ ] **Paper viewports.** Passive `Model_Space` rendering today; future per-viewport overrides marked as extension. — §4.3, §5.1, §7.4
- [ ] **Out of scope, named.** Cross-view selection sync, paper-viewport overrides, override resolution rules, elevation/3D editing. — §1.3
- [ ] **Open questions.** Items that need more research before they can be specced. — §9

**Meta criteria:**
- [ ] The spec is self-contained: no implementation details leak in beyond what's necessary to anchor the contract to current code.
- [ ] Where current code disagrees with the spec, the spec says so explicitly and points at a follow-up TODO entry. (Pipe spec Rev 2 pattern.)

---

## 11. Follow-ups (file in TODO.md when this spec lands)

- **[P2] Investigate Room.z_range_mm() vs user expectations.** Replaces existing "Plan Views room Z values seem to be calculated based on ceiling height" entry with the three hypotheses from §7.2. Likely fix is one of: slab-thickness lookup hardening, sign correction, or UI display path divergence.
- **[P3] Extract plan-family Z-band magic numbers to named constants in `constants.py`.** Spec §7.3 lists current values; the spec is the source of truth for *order*, `constants.py` should become the source of truth for *values*.
- **[P2] Investigate elevation marker persistence.** §6.3 records the gap. Decide whether to mirror the `DetailMarker.to_dict()` pattern or use a different approach.
- **[P1] Future spec session: Section view subsystem.** First-class arbitrary-cut-line section views. Will reference §4.1 of this spec.
- **[P2] Future spec session: Drafting overrides / view templates.** Will reference §7.4 catalog and define resolution rules.
- **[P2] Future spec session: Cross-view selection / interaction sync.** Will reference §2 vocabulary.
- **[P3] Future spec session: Paper-viewport-specific overrides** (on top of view-instance overrides). Depends on view templates spec landing first.
- **[P3] Document `Node.z_offset` legacy field migration.** §3.3 records `z_offset` as legacy; a migration / cleanup task should remove or formally deprecate it.
