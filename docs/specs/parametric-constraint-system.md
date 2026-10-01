---
status: proposal          # designed + grilled 2026-09-29, unbuilt. The prototype this file used to describe (constraints.py: Concentric/Dimensional/Alignment + iterative solver) is RETIRED by Session 1 (§12) — see §2 "As-built (to be retired)".
last-verified: 2026-09-30  # ribbon-surface wording re-pointed at the permanent Block Editor tab (feat/block-editor-ribbon-tab); §2 as-built files unchanged since 2e511cd (git diff empty for constraints.py / geometry_2d.py / the geo2d constraints group); prior 2026-09-29
verified-commit: 44325e5  # prior 2e511cd — as-built §2 claims checked against that HEAD (feat/nested-blocks)
applies-to:
  - firepro3d/constraints.py            # as-built prototype — retired in Session 1
  - firepro3d/sketch_model.py           # proposal — created in Session 1 (pure: enum, REGISTRY, records, file format)
  - firepro3d/sketch_solver.py          # proposal — created in Session 1 (pure numpy: SketchSolver + NumpySolver)
  - firepro3d/sketch_adapters.py        # proposal — created in Session 1 (pure: per-primitive variable adapters)
  - firepro3d/constraint_controller.py  # proposal — created in Session 1 (Qt shell composed into Model_Space, block_editor role)
  - firepro3d/constraint_paint.py       # proposal — created in Session 1 (glyphs, persisted dims, tint, origin + axes)
related:
  - block-system.md                     # definition schema gains "constraints" + primitive "uid"; origin fixed at (0,0)
  - 2d-geometry.md                      # primitive storage, typed setters (the D6 anchor laws)
  - selection-mode.md                   # §15 selection readouts — persisted dims reuse readout_paint + DimSpec
  - ribbon-bar.md                       # Block Editor tab (permanent base tab since 2026-09-30): Constrain + Inspect groups
  - icon-style-guide.md                 # 48-unit two-token icon contract
  - model-space-containment-contract.md # C1/C8: loose geometry + constraints never in the plan scene
  - units-and-formatting.md             # dim display through ScaleManager formatters
source-tasks:
  - todo_open.md "Spec session: parametric constraint system" [type:design] (this spec)
  - reference input: "D:/Custom Code/FPD Design/constraint-system-spec.md" (external draft; critiqued, not adopted wholesale — §4)
---

# Parametric Constraint System — Design Spec

## Goal

Let a user author **driving geometric and dimensional constraints on 2D geometry inside the Block Editor**, SolidWorks-sketch style: select geometry, apply a constraint (Horizontal, Coincident, Symmetric…) or a Smart Dimension, and have one numeric solver keep every constraint satisfied while the user drags grips, types dimension values, or runs modify tools — with DOF counting, a fully-defined state, and redundant/conflicting diagnostics. Constraints live in the block definition and are **frozen at insert**: placed instances render the solved geometry and never re-solve.

## Motivation

Fire-protection symbol libraries (heads, valves, tees, fittings) are small, symmetric, dimension-driven shapes. Today they are drawn freehand with snaps; editing one dimension means hand-moving several grips, and nothing keeps a symbol symmetric about its insertion point. A constraint system makes block authoring parametric (edit a value, the shape follows) and is the foundation for the deferred `=[AttributeName]`-driven dimensions (Block attributes task).

The existing prototype (`constraints.py`) cannot be extended into this: it is a per-constraint Gauss-Seidel mover over live item references with list-index ids, and its constraints are lost on block Save (§2).

---

## 1. Decisions (ratified — 2026-09-29 grill, 20 rounds)

Every row below was ratified by the user at a human gate (P5). "Ref-spec" = the external draft `constraint-system-spec.md`.

| # | Decision | Departs from ref-spec? |
|---|---|---|
| D1 | **Atom = the existing typed primitive item exposing named handles** to the solver. No point table, no refcounts, no "recipes", no topological fusion. Joining two shapes is a **Coincident constraint**. | Yes — ref-spec §1/§5/§9 (points as atom, rectangle/polyline recipes, Merge/Split Points) dropped. |
| D2 | **Block Editor only; frozen at insert.** `AlignmentConstraint` + Align padlock retired. Model-element "locked relationships" (walls/gridlines) is out of scope. | Same scope; adds the padlock retirement. |
| D3 | **Grounds:** the block origin (fixed; the insertion base) + non-printing **X/Y axes** through it, both pickable constraint targets; plus a **Fix** constraint. "Fully defined" counts grounding. | Corrects ref-spec §3.2's claim that axes are needed to kill rotation — H/V residuals are absolute; axes are *targets* (point-on-axis, distance-to-axis, symmetric-about-axis). |
| D4 | **Origin = the editor scene's fixed (0,0)** (the existing white cross). The movable red origin marker and the **Set Origin** tool are retired; users design around the origin or Move geometry to it. Definitions with a non-zero `origin` migrate by translating their primitives. | New (user proposal). |
| D5 | **Participating primitives + handles** per §5.1; **splines excluded** in v1; text + nested block instances expose only their insertion point. Reference lines = Revit-style reference planes. | Adds rectangle/polygon/ellipse/text/instance handles. |
| D6 | **What moves:** a drag pins the dragged handle to the cursor, everything else least-change. A typed edit keeps today's readout anchor laws (`2d-geometry.md` typed setters, e.g. line keeps `p1`, rect keeps left/bottom) as **strong preferences**, not locks. | Refines ref-spec §7.4 (pure least-norm would split a typed edit across both ends). |
| D7 | **A dimensional constraint is a persisted readout:** same painter/style as the selection readouts, always visible in the editor (never on instances/prints). Created by the Smart Dimension tool **or** by clicking a lock glyph beside a transient readout ("promote"). Driving by default; **Driving/Reference is one boolean**. A permanent dim suppresses the duplicate transient readout. | Ref-spec §8's "annotation engine" does not exist (persistent dimensions were deleted under C1/C8); replaced by the readout layer. |
| D8 | **Snaps never create constraints. No snap journal.** | Drops ref-spec §10's journal. |
| D9 | **Admit + flag:** a redundant or conflicting constraint is added and shown amber/red (not refused at the gate). | Same as ref-spec §7.5. |
| D10 | **State display:** glyphs + dims coloured by state (amber redundant, red conflicting); **DOF badge**; geometry **tint** by state (under-defined = the theme **accent** token — blue in light, green in dark; fully defined = ink; conflicting = red) behind an Inspect toggle, default on, editor only. During a conflict the geometry **holds its last good solution** (no least-squares compromise). | Adds hold-last-good. |
| D11 | **SolidWorks is the behaviour reference:** boxed relation glyphs beside geometry (toggle, default on), hover a glyph → its targets glow, click → select, Delete removes it; selecting an entity lists its constraints in the property panel. SolidWorks constraint catalogue + names are the baseline. | — |
| D12 | **Selection-first** constraint buttons (enabled only when the selection is valid for that type); with nothing selected a button enters a pick mode. **One Smart Dimension tool** (tool-first) infers the dim kind from the picks + label placement. | — |
| D13 | **"Mirror" = the Symmetric constraint only.** Mirror stays an unlinked copy tool in the scene/Modify tools; no linked "Mirror Entities". | Ref-spec had Symmetric as Tier 2; promoted. |
| D14 | **One constraint type per session**, in the §12 order; Session 1 = foundation + Horizontal and retires the old system. | Replaces ref-spec §12 phasing. |
| D15 | **Ribbon:** two new groups on the Block Editor tab **after Modify** — **Constrain** (large Smart Dimension + small buttons stacked 3/column in build order) and **Inspect**. **No greyed placeholders** — each session adds its own button. *(2026-09-30: the Block Editor page is now a permanent base tab — `ribbon-bar.md` §3.4 — not a contextual page; its Definition group's disabled **Edit Attributes** button is an explicit user-ratified exception to this rule. The rule still binds the Constrain / Inspect groups.)* | Ref-spec wanted greyed Tier-2 buttons; forbidden by `icon-style-guide.md` §7. |
| D16 | **Icons:** 48-unit on-contract (two-token); **one symbol SVG per constraint** used at ribbon (54/27 px), canvas glyph (~16 px, boxed) and panel list; whole family designed up-front as a mockup-gated contact sheet in Session 1. | — |
| D17 | **Operations on constrained geometry:** §8 table. Move/Rotate/Scale of **grounded** geometry is **refused** (SolidWorks model). | New. |
| D18 | **Bars** on a 200-primitive / 300-constraint block: drag re-solve ≤ 8 ms/mouse-move; add-constraint/commit (solve + diagnostics) ≤ 50 ms; open (load + first solve) ≤ 200 ms; residual ≤ 1e-6 mm linear, 1e-9 rad angular; a driving dim never displays a value different from what was typed. | New. |
| D19 | **UI term = "Constraints"** everywhere (group "Constrain", toggle "Show Constraints", panel "Constraints", status "Over-constrained: …"); individual type names follow SolidWorks. | — |
| D20 | **Per-session done contract** (§11). | — |

Brainstorm (Phase 3) decisions, approved by the user in the design presentation:

| # | Decision |
|---|---|
| B1 | Solver = **hand-rolled numpy** (no scipy — not in the venv), weighted minimum-change projection with damped Gauss–Newton steps, **union-find component partitioning + equality substitution from day one**, SVD diagnostics, behind a `SketchSolver` interface. Rejected: `python-solvespace` (GPLv3 — licensing), FreeCAD `planegcs` (C++ ext, uncertain Windows wheels, still need our own diagnostics). |
| B2 | Module layout §3; items remain the source of truth with **one write-back per item per solve**. |
| B3 | File format §6 (primitive `uid`, `HandleRef`, constraint record, additive key, forward-compatible inert records). |
| B4 | Residual catalogue §7.3 (corrects ref-spec angle / tangent / parallel / equal forms). |

## 2. As-built (to be retired in Session 1)

Checked at `2e511cd`. This is what exists today; none of it survives Session 1.

- `firepro3d/constraints.py` — `Constraint` base (`solve(moved_item)`, `involves`, `visual_points`, `to_dict(item_to_id)`, factory `from_dict` on `constraint_type`), `ConcentricConstraint` (writes `_center`), `DimensionalConstraint` (grip indices + `apply_grip`), `AlignmentConstraint` (moves target via `moveBy`, breaking the primitives' pos-identity convention), `solve_constraints` (≤20 Gauss-Seidel passes, stall after 3).
- Scene state on `Model_Space`: `_constraints`, `_constraint_circle_a`, `_constraint_grip_a`, `_align_padlocks`; modes `constraint_concentric` / `constraint_dimensional` → `_press_constraint`; ids = index into `SceneTools._all_geometry_items()`; captured only into undo snapshots (`_capture_constraints` / `_restore_network`).
- `SceneTools._solve_constraints` call sites: `manip_handle` grip drag/release, `selection_manipulator` move/resize bake, `modify_tools_controller.commit_rotate`, paste/move commit, `model_view.mouseDoubleClickEvent` (dim edit). **Not** called from readout commits or panel `_dim_edit`.
- `_PadlockItem` (scene_tools) creates `AlignmentConstraint` after an Align move — session-only (not saved, dropped on load, wiped by undo).
- `main.py` `_build_geo2d_constraints_group` (`_GEO2D_CONSTRAINT_TOOLS` + disabled placeholders) lives on the plan-scene 2D-geometry contextual tab, never shown in the Block Editor.
- `scene_io` discards any `constraints` payload (C8 clean-drop).
- **Divergences / latent bugs found during grounding** (filed as follow-ups; most dissolve with the retirement): (a) `Model_View.drawForeground` §3b reads `c.item_a` on every constraint — a Concentric/Alignment constraint raises `AttributeError` and skips the rest of the foreground paint; (b) geo2d Constraints buttons call `self.scene.set_mode` (plan scene) not `_active_scene()`; (c) Block Editor constraints are lost on Save (`commit_block` carries only primitives + origin); (d) `explode_selected_items` drops a **closed** polyline's closing segment (independent of constraints — survives the retirement).

## 3. Architecture

Flat `firepro3d/` package. Pure core out, Qt side-effect shell in (the `model-space-architecture.md` decomposition rule).

```
pure (no Qt; unit-testable)
  sketch_model.py     ConstraintType enum (whole catalogue from day one) + REGISTRY
                      (arity, accepted handle kinds, DOF removed, implemented flag),
                      Constraint record, HandleRef, to_dict/from_dict (§6)
  sketch_solver.py    SketchSolver interface; NumpySolver: residual/Jacobian
                      catalogue (§7.3), equality substitution, union-find components,
                      weighted min-change projection (§7.2), SVD diagnostics (§7.4)
  sketch_adapters.py  per-primitive adapter: variables(item) -> values,
                      handle(item, name) -> point/param + d/dvars,
                      write_back(item, values)   (§5)

Qt shell
  constraint_controller.py  composed into Model_Space for scene_role == "block_editor"
                            only; owns the constraint list; entry points drag /
                            typed_edit / transform_commit / add / delete; D17
                            refusals (dry-run first); undo capture; definition
                            save/load
  constraint_paint.py       origin cross + non-printing X/Y axes; boxed glyphs
                            (themed_icon); persisted dims via readout_paint; tint
  main.py                   Constrain + Inspect ribbon groups (§10)
  property panel            Constraints container (§10)
```

**Source of truth.** Primitive items remain the model (their internal scene-coordinate data, pos = identity per `2d-geometry.md`). The solver never touches Qt; the controller extracts variables through adapters, solves, then performs **exactly one write-back per affected item** followed by one repaint. This gives the anti-drift guarantee the ref-spec sought with "model owns coordinates, scene mirrors" without inventing a second model.

**Data flow (one edit):** changed handles → controller collects the affected union-find component(s) → adapters extract variables → solver (drag pins / D6 anchor weights) → write-back (skipped on failure: hold-last-good) → repaint → on commit: diagnostics + `push_undo_state`.

## 4. Reference-spec reconciliation

| Ref-spec item | Disposition |
|---|---|
| §1 points-as-atom, §5 recipes, §9 fusion/split/refcount | **Dropped** (D1). Coincident constraint replaces fusion; no refcounts. |
| §2 scope, frozen at insert, no external refs | **Kept** (D2). Refs are same-definition only; enforced at write time by `HandleRef` resolution. |
| §3.1 records | **Replaced** by §6 (uids, `HandleRef`, `helper`, `label`; no `annotation_ref`). |
| §3.2 origin + axes | **Kept, corrected** (D3/D4) — origin fixed at (0,0); axes are targets, not the rotation-killer. |
| §3.3 units ("decimal feet vs mm" open) | **Settled:** mm (project convention). File angles in **degrees** (matches primitives' `start_deg`), radians inside the solver. |
| §4 DOF table | Replaced by §5.1 variable counts; DOF = vars − rank(J); grounding counted because origin/axes are constants. |
| §6 registry + Tier 2 greyed | Enum + REGISTRY kept (file stability); **no greyed UI** (D15); unknown/unbuilt types load as inert records (§6.4). |
| §6 residuals | Corrected in §7.3 (angle sign, signed tangent, normalized parallel/perpendicular, unsquared equal, arc endpoint model). |
| §7.1 build from scratch | **Kept** (B1), now benchmarked (§9). |
| §7.2 model/scene separation | Kept in spirit via single write-back (§3). |
| §7.3 LM/dogleg, components, analytic Jacobians | Kept + equality substitution added (required by the §9 bench). |
| §7.4 least-norm drag | Kept for drag; typed edits anchor-weighted (D6). |
| §7.5 diagnostics | Kept (D9/D10) + hold-last-good. |
| §8 dims via "annotation engine" | Engine does not exist → persisted readouts (D7). |
| §10 OSNAP → no constraint + journal | No constraint kept; **journal dropped** (D8). |
| §11 context tab + contextual ribbon tab | Property-panel Constraints container + Constrain/Inspect groups on the existing Block Editor page (D11/D15). |
| §12 phasing | Replaced by §12 one-type-per-session order (D14). |
| §14 open items | Unit → mm; Chain record → moot (no fusion); argument order → §6.3 + per-type rows; rectangle recipe → moot (rectangle is intrinsic); `tool_origin` → moot. |

## 5. Primitives, variables and handles

### 5.1 Variable adapters

Only items referenced by at least one enabled constraint become solver variables. The origin and axes are **constants**.

| Primitive (`to_dict` type) | Variables | Handles (`h` names) |
|---|---|---|
| Line `draw_line` / reference line `reference_line` | x1 y1 x2 y2 | `p1` `p2` `edge` |
| Circle `draw_circle` | cx cy r | `center` `curve` |
| Arc `arc` | cx cy r θs θe | `center` `start` `end` `curve` — endpoints derived through the ArcItem's own Y-up convention (`2d-geometry.md`; Y-up CCW, Qt Y-down scene); write-back keeps `span_deg > 0` |
| Rectangle `draw_rectangle` | cx cy w h θ | corners/edges/centre named after the **existing 9-grip naming** (`tl tr br bl`, edge names, `center`); derived through the rotation; write-back **canonicalizes to a centre-following pivot** (`pivot: null`) — identical scene geometry |
| Polyline `polyline` | 2 per vertex | `v<i>` `s<i>` (closing segment of a closed polyline included) |
| Polygon `polygon` | cx cy R rot | `center` |
| Ellipse `draw_ellipse` | cx cy rx ry rot | `center` |
| Text `text` | x y | `ins` |
| Nested block instance `block_instance` | x y | `ins` (interior frozen — D2) |
| Spline `draw_spline` | — | **excluded in v1** |

Rotation of text/instances is not a variable in v1. Handle *kinds* (point / line-like edge / curve / scalar) are what REGISTRY arity rules match against.

### 5.2 Polyline vertex identity

`v<i>` indices are positional. Any operation that inserts or removes vertices renumbers the affected `HandleRef`s; constraints on a removed vertex/segment cascade-delete (one undo step with the edit).

## 6. File format

### 6.1 Primitive ids

Every primitive dict, including `block_instance` records, gains **`"uid"`** (uuid4 hex). Assigned at creation and carried as `item._uid`; survives undo snapshots, Save and reopen. Legacy dicts without one are assigned one on load. Copy / Paste / Duplicate / Array / Mirror mint **new** uids (§8). This also replaces the list-index ids the undo snapshot uses for constraints today.

### 6.2 HandleRef

`{"uid": "<primitive uid>", "h": "<handle name>"}`, or a reserved ground: `{"ref": "origin"}`, `{"ref": "x_axis"}`, `{"ref": "y_axis"}`. A ref that does not resolve within the same definition is rejected at write time (no external references).

### 6.3 Constraint record

Stored in a new `BlockDefinition` key **`"constraints": [...]`** — additive; absent ⇒ `[]`; **no `schema` bump** (the nested-blocks design reserves schema 2).

```json
{"id": "<uuid hex>", "type": "horizontal", "refs": [ {HandleRef}, ... ],
 "value": null, "driving": true, "enabled": true,
 "helper": {}, "label": {"offset": [dx, dy]}}
```

- `value`: lengths in **mm**, angles in **degrees** (Y-up, CCW-positive); `null` for geometric types.
- `refs` order = **pick order**, and is significant; each type's catalogue row (§7.3, pinned per session in §12) states what the order means. Global convention: angles are measured **from `refs[0]` to `refs[1]`, CCW-positive, Y-up**.
- `helper`: disambiguation for multi-solution types — tangent side / internal, Smart Dimension kind (`aligned` / `dx` / `dy`) and sign, point-line side. Fixed at creation from the current geometry.
- `driving`: D7 (reference dims remove no DOF). `enabled`: Suppress (kept, not solved).
- `label`: persisted-dim label offset (dims only).

### 6.4 Forward compatibility

`ConstraintType` declares the whole §12 catalogue from day one. A record whose type is unbuilt or unknown is kept **verbatim and inert**: listed in the panel as "Unsupported constraint", preserved on save, never solved, excluded from DOF. A file from a newer build never loses data in an older one.

### 6.5 Origin migration (D4)

Opening a definition whose `origin ≠ (0,0)` translates its primitives by `−origin` and writes `origin: [0,0]` on the next save. Instances render identically (compile already applies `translate(−origin)`). The `origin` field becomes a vestigial constant; its removal is a later schema cleanup.

## 7. Solver

### 7.1 Interface

```python
class SketchSolver:
    def solve(self, system, goals, weights) -> SolveResult      # values, converged, residuals
    def diagnose(self, system) -> Diagnostics                   # dof, per-entity defined, redundant ids, conflicting ids
```

`system` = variables + constraint rows for one or more components; `goals`/`weights` implement §7.2. Swapping the engine later is a module replacement.

### 7.2 Algorithm — weighted minimum-change projection

```
minimise  ‖W½ (x − x_goal)‖²   subject to  F(x) = 0
step:     dx = g + W⁻¹Jᵀ (J W⁻¹ Jᵀ + λI)⁻¹ (−F − J g),   g = x_goal − x
```

Damped Gauss–Newton iterations until `F` meets the D18 tolerances. **Constraints are hard; goals are soft** — so a drag can never violate a constraint, the geometry follows as far as it is allowed.

- **Drag:** dragged handle's goal = cursor, very high weight; every other variable's goal = its current value, weight 1.
- **Typed edit (D6):** the edit's existing typed setter (`2d-geometry.md`) is applied to a scratch copy to produce `x_goal`; the setter's anchor handle (e.g. line `p1`) gets a high weight. With no constraints present the result equals today's readout behaviour.
- **Equality substitution** (before solving): Coincident, Horizontal, Vertical, Concentric and Fix on raw variables alias variables (`y₂ := y₁`) instead of adding rows. Required, not an optimization (§9).
- **Components:** union-find over shared variables; only components containing a changed handle are solved.
- **Scaling:** angular rows are multiplied by 1000 mm so mm and radian residuals are commensurate.
- **Failure:** if tolerance is not met, nothing is written back (D10 hold-last-good) and diagnostics run.

### 7.3 Residual catalogue

`d = b − a` for a line's direction; normalized forms guard `‖d‖ < ε`.

| Type | Refs (order) | DOF | Residual |
|---|---|---|---|
| Horizontal | edge, or 2 points | 1 | `y_b − y_a` (substituted) |
| Vertical | edge, or 2 points | 1 | `x_b − x_a` (substituted) |
| Coincident | point, point \| origin | 2 | `p − q` (substituted when both raw) |
| Point-on-curve | point, edge/curve/axis | 1 | line: signed `cross(p−a, d)/‖d‖`; circle/arc: `‖p−c‖ − r` |
| Concentric | curve, curve \| point | 2 | `c₁ − c₂` (substituted) |
| Symmetric | a, b, axis (edge / X / Y axis / reference line) | 2 | midpoint of (a,b) on axis **and** `(b−a)·dir(axis) = 0`; two same-type entities expand to handle pairs |
| Fix | handle | 1–2 | `v − v₀` (v₀ stored in `helper`) |
| Parallel | edge, edge | 1 | `cross(d₁,d₂)/(‖d₁‖‖d₂‖)` |
| Perpendicular | edge, edge | 1 | `dot(d₁,d₂)/(‖d₁‖‖d₂‖)` |
| Equal | edge, edge \| curve, curve | 1 | `‖d₁‖ − ‖d₂‖` / `r₁ − r₂` |
| Tangent | edge, curve \| curve, curve | 1 | line–circle `sd(c, L) − s·r` (`s` = `helper.side`); circle–circle `‖c₁−c₂‖ − (r₁ ± r₂)` (`helper.internal`) |
| Midpoint | point, edge | 2 | `p − (a+b)/2` |
| Collinear | edge, edge | 2 | point-on-line of both ends of refs[1] on refs[0] |
| Dim: length / distance | edge \| 2 points | 1 | `‖b−a‖ − D` |
| Dim: Δx / Δy | 2 points | 1 | `s·(x_b−x_a) − D` / `s·(y_b−y_a) − D` (`s` in `helper`) |
| Dim: point–line | point, edge | 1 | signed point-on-line residual `− s·D` |
| Dim: radius / diameter | curve | 1 | `r − R` / `2r − D` |
| Dim: angle | edge, edge \| edge, axis | 1 | `atan2(cross, dot) − θ`, wrapped to (−π, π] |

Each session pins its row (argument meaning, helper fields, degenerate cases) before building; the pinned row is file-format.

### 7.4 Diagnostics (on commit, not per drag frame)

- **DOF** per component = variables − rank(J) (SVD, relative tolerance); substituted variables counted; the sketch DOF is the sum. **Fully defined** ⇔ DOF = 0 — which includes grounding, because the origin/axes are constants.
- **Per-entity defined (D10 tint):** an entity is fully defined iff its variables have ~zero components across J's **null-space basis** (same SVD).
- **Redundant (amber):** removing the constraint's rows does not reduce rank, and its residual is satisfied.
- **Conflicting (red):** the solve cannot reach tolerance; the constraints whose rows lie in the dependent set with non-zero residual are marked red. Geometry holds last good.

## 8. Operations on constrained geometry (D17)

| Operation | Behaviour |
|---|---|
| Delete an entity | Every constraint touching it cascade-deletes; one undo step. |
| Grip drag / typed readout / property-panel edit | Through the solver (§7.2). Readout + panel edits no longer bypass constraints. |
| Move / Rotate / Scale a selection | Moved handles become drag goals; the rest re-solves. **Refused** (dry-run first, nothing mutated) if the selection is grounded — status bar: "Selection is fully defined — remove Fix/grounding constraints to move". |
| Copy / Paste / Duplicate / Array | New uids; constraints **internal** to the copied set are copied and remapped; constraints to anything outside (including origin/axes) are dropped. |
| Mirror (scene tool, D13) | As Copy; internal constraints reflected (H/V preserved; Symmetric pairs preserved). |
| Offset | New geometry, no constraints. |
| Trim / Extend / Break / Fillet / Join / Explode | The consumed entities' constraints are dropped; results start free; status bar "N constraints removed". Smart remapping deferred. |
| Block Save → instances | Frozen (D2); compile unchanged. |

## 9. Performance (D18) — P4 probe, 2026-09-29

Scratch bench (pure numpy 2.3, venv; no scipy), synthetic 200 lines / 300 constraints (horizontal + coincident chain + distance):

| Configuration | Drag / mouse-move | Rank diagnostics |
|---|---|---|
| Naive dense, whole sketch | 31 ms ✗ | 107 ms ✗ |
| Constrained vars only + components — realistic (symbols of ~5) | **0.4 ms** ✓ | **2.8 ms** ✓ |
| Same — worst case (one 400-var component) | 29 ms ✗ (~6.8 ms/iteration × ~4) | 36 ms ✓ |
| + equality substitution — worst case (estimated from reduced-size step) | **~4 ms** ✓ | **5.5 ms** ✓ |

Consequence: component partitioning **and** equality substitution are Session-1 requirements. Session 1 re-runs this bench against the real solver as a perf test (both cases) — the estimate row is unverified until then (P5: the D18 bars stand; the substitution-based worst case is as-proposed until measured).

## 10. User interface

- **Ribbon (D15):** Block Editor tab = Block | Definition | 2D Geometry | Edit | Modify | **Constrain** | **Inspect** (as-built groups through Modify, and their editor-only enable state, owned by `ribbon-bar.md` §3.4). Constrain: large Smart Dimension + one small button per *built* type, stacked 3/column in §12 order; a button enables iff the current selection matches its REGISTRY arity/handle kinds, else (nothing selected) enters a pick mode (D12). Inspect: Show Constraints (toggle), Constraint Status (tint toggle), DOF badge, Delete Constraints (on selection). Every button carries a tooltip.
- **Smart Dimension (D12):** tool-first; one line → length; two points → distance with aligned / Δx / Δy chosen by label placement; circle → diameter; arc → radius; two lines → angle; point + line → point-line distance. Plus D7's lock glyph on transient readouts.
- **Canvas (D10/D11):** origin cross + non-printing X/Y axes (pickable targets); boxed ~16 px constraint glyphs beside their geometry (screen-constant, non-printing); persisted dims via `readout_paint`; state colours + tint. **Pick order:** grips > dim labels > glyphs > origin/axes > HALO geometry. Hover a glyph → its targets glow; click selects it; Delete removes it.
- **Property panel:** a **Constraints** container for the selected entity/constraint — rows: icon, type name, targets, value (editable for dims), Driving/Reference, Suppress, Delete; sketch DOF shown.
- **Status bar:** "Over-constrained: …", refusal and "N constraints removed" messages.
- **Icons (D16):** `firepro3d/graphics/Ribbon/`, 48-unit two-token per `icon-style-guide.md`, one symbol per type reused for ribbon/glyph/panel; guarded by `tests/test_icon_theming.py`.
- **Mockup gates (Session 1, before code):** (1) the full icon-family contact sheet rendered through the real loader at 54/27/16 px, light + dark; (2) the Constraints panel container + canvas glyph/tint look. Both served as interactive mockups for sign-off.

## 11. Per-session done contract (D20)

**Guard tests each constraint session ships** (VC3 — real objects, observable ground truth):

1. **Math:** residual zero on satisfying geometry, non-zero otherwise; analytic Jacobian matches finite differences on random configurations; DOF removed equals the catalogue value.
2. **End-to-end on a real Block Editor scene:** build geometry, select, click the real ribbon button, drag a grip with posted events on a shown view; assert the observable geometry (e.g. Horizontal: `p1.y == p2.y` after a drag that tried to tilt it). Shown RED with the type's residual reverted.
3. **Persistence:** save block → close editor → reopen: constraint, glyph and geometry return; a placed instance renders the solved (frozen) geometry.
4. **Undo/redo** of add, delete, and a solver-driven edit.
5. **Diagnostics:** a redundant case goes amber; a conflicting case goes red and holds last good — pixel-sampled in both themes.
6. **Ribbon:** the button enables only on a valid selection; the icon passes `test_icon_theming.py`.

**Session done:** full suite green (VC6) → user smoke from a checklist with exact commands → user approval → this spec's catalogue row flipped to built + `verified-commit` stamped → smoke-found spec deltas reconciled → next session.

## 12. Session plan (D14)

| # | Session | Also delivers |
|---|---|---|
| 1 | **Foundation + Horizontal** | `sketch_model` / `sketch_solver` / `sketch_adapters` / `constraint_controller` / `constraint_paint`; primitive `uid`s; `constraints` in `BlockDefinition`; §6.5 origin migration + Set Origin/red-marker retirement; origin + axes drawn/pickable; glyph paint; Constraints panel container; Constrain + Inspect groups; §8 seams; retire `constraints.py`, the constraint modes, `drawForeground` §3b, the geo2d Constraints group, the Align padlock / `AlignmentConstraint` (coupled tests rewritten/retired, VC5); D18 perf test; both mockup gates. |
| 2 | **Vertical + diagnostics** | DOF badge, tint, amber/red (H+V on one line = first conflict test). |
| 3 | **Coincident** | point↔point, point↔origin, point-on-curve / point-on-axis. |
| 4 | **Smart Dimension: linear** | length, aligned, Δx, Δy; lock-a-readout promotion; Driving/Reference. |
| 5 | **Smart Dimension: radius / diameter / angle** | |
| 6 | **Concentric** | |
| 7 | **Symmetric** | about an edge, X/Y axis or reference line. |
| 8 | **Fix** | |
| 9 | **Parallel** | |
| 10 | **Perpendicular** | |
| 11 | **Equal** | lengths / radii. |
| 12 | **Tangent** | signed, side helper. |
| 13 | **Midpoint** | |
| 14 | **Collinear** | |
| 15 | **Smart Dimension: point–line distance** | |
| — | Declared, deferred | Coradial, Pierce/Intersection, arc length, patterns, expression / `=[Attribute]`-driven dims (→ Block attributes task), smart constraint remapping through Trim/Extend/Join. |

## Acceptance Criteria (whole system, accumulated over §12)

- [ ] Constraints are authored only in the Block Editor; the plan scene never holds or solves them (C1/C8 preserved).
- [ ] Constraints persist in the block definition across Save / close / reopen and app restart; instances render solved geometry and never re-solve.
- [ ] Drag, typed readout, property-panel and modify-tool edits all honour constraints; with no constraints, behaviour equals today's.
- [ ] DOF badge, fully-defined state (grounding counted), per-entity tint, amber redundant and red conflicting states are correct; conflicts hold last-good geometry.
- [ ] D17 operation rules hold, including refusal of Move/Rotate/Scale on grounded selections.
- [ ] D18 performance bars met on the synthetic 200/300 block (both worst-case and realistic compositions).
- [ ] Unknown/unbuilt constraint records round-trip untouched.
- [ ] Every shipped constraint has an approved 48-unit two-token icon used on ribbon, canvas and panel.

## Verification Checklist

- [ ] Per-session §11 guards shown RED-then-GREEN.
- [ ] Full suite green on the final tree each session (VC6).
- [ ] User smoke + approval each session.
- [ ] This spec's §7.3/§12 rows stamped as each type ships; `status` moves proposal → partial (after Session 1) → current (after Session 15).
- [ ] `SPEC-INDEX.md` row updated (applies-to gains the new modules; `scene_tools.py` constraint responsibility removed).
