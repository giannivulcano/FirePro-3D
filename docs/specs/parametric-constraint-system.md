---
status: partial           # Session 1 (foundation + Horizontal) BUILT 2026-10-02 on feat/cs1-constraint-foundation; Sessions 2–15 (§12) unbuilt. The legacy prototype (constraints.py) is RETIRED (§2).
last-verified: 2026-10-02  # CS1 Account: D28–D35 ratified build rulings added (D32 amends D11/§10, D33 amends §5.1/§5.3, D34 amends D22); §2 → retired-prototype history; §3/§5/§6.3/§7/§8/§9/§10/§12 reconciled to the shipped code (tolerances, translate-first pass, live body drag, measured perf); applies-to = shipped modules; prior 2026-10-01 (CS1 Phase 2/3 deltas D21–D27, §2 re-derived at 406747b); prior 2026-09-30; prior 2026-09-29
verified-commit: 2a22ba9  # CS1 close (feat/cs1-constraint-foundation); prior 44325e5; prior 2e511cd (feat/nested-blocks)
applies-to:
  - firepro3d/sketch_model.py           # pure: ConstraintType enum (whole catalogue), REGISTRY, Constraint record, icon_for, remap_for_copy
  - firepro3d/sketch_solver.py          # pure numpy: NumpySolver (the v1 SketchSolver), System/Row/PointExpr, structure cache, BUILDERS
  - firepro3d/sketch_adapters.py        # per-primitive variable adapters, §5.3 grip map, D28/D34 weights, D29 collapse rules, write-back tolerances
  - firepro3d/constraint_controller.py  # Qt shell: composed into every Model_Space, active only in the block_editor role; every edit seam, pick mode, panel rows
  - firepro3d/constraint_paint.py       # canvas: X/Y axes, boxed glyphs (D32 visibility), target glow, pick markers, glyph pick
related:
  - block-system.md                     # definition schema "constraints" + primitive "uid"; origin fixed at (0,0); D23 scaffolding; D24 Create Block base
  - 2d-geometry.md                      # primitive storage, typed setters (the D6 anchor laws), size floors
  - selection-manipulator.md            # grip drag seam + D35 live body / resize drag
  - scene-tools.md                      # modify-tool commits through ConstraintController.edit; D30 copy rule
  - selection-mode.md                   # §15 selection readouts — persisted dims (CS4) reuse readout_paint + DimSpec
  - ribbon-bar.md                       # Block Editor tab: Constrain + Inspect groups after Modify
  - property-panel.md                   # ConstraintAdapter + the ActionRowList Constraints section
  - icon-style-guide.md                 # §5.1 40-unit family (D25)
  - model-space-containment-contract.md # C1/C8: loose geometry + constraints never in the plan scene
  - units-and-formatting.md             # dim display through ScaleManager formatters
source-tasks:
  - todo_open.md "Spec session: parametric constraint system" [type:design] (this spec)
  - todo_closed.md "CS1 — Constraint foundation + Horizontal" (2026-10-02)
  - reference input: "D:/Custom Code/FPD Design/constraint-system-spec.md" (external draft; critiqued, not adopted wholesale — §4)
---

# Parametric Constraint System — Design Spec

## Goal

Let a user author **driving geometric and dimensional constraints on 2D geometry inside the Block Editor**, SolidWorks-sketch style: select geometry, apply a constraint (Horizontal, Coincident, Symmetric…) or a Smart Dimension, and have one numeric solver keep every constraint satisfied while the user drags grips, types dimension values, or runs modify tools — with DOF counting, a fully-defined state, and redundant/conflicting diagnostics. Constraints live in the block definition and are **frozen at insert**: placed instances render the solved geometry and never re-solve.

## Motivation

Fire-protection symbol libraries (heads, valves, tees, fittings) are small, symmetric, dimension-driven shapes. Drawn freehand with snaps, editing one dimension means hand-moving several grips, and nothing keeps a symbol symmetric about its insertion point. A constraint system makes block authoring parametric (edit a value, the shape follows) and is the foundation for the deferred `=[AttributeName]`-driven dimensions (Block attributes task).

The earlier prototype (`constraints.py`) could not be extended into this: it was a per-constraint Gauss-Seidel mover over live item references with list-index ids, and its constraints were lost on block Save (§2). It was retired in Session 1.

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
| D6 | **What moves:** a drag pins the dragged handle to the cursor, everything else least-change. A typed edit keeps today's readout anchor laws (`2d-geometry.md` typed setters, e.g. line keeps `p1`, rect keeps left/bottom) as **strong preferences**, not locks. *(Typed values themselves are exact — D31.)* | Refines ref-spec §7.4 (pure least-norm would split a typed edit across both ends). |
| D7 | **A dimensional constraint is a persisted readout:** same painter/style as the selection readouts, always visible in the editor (never on instances/prints). Created by the Smart Dimension tool **or** by clicking a lock glyph beside a transient readout ("promote"). Driving by default; **Driving/Reference is one boolean**. A permanent dim suppresses the duplicate transient readout. | Ref-spec §8's "annotation engine" does not exist (persistent dimensions were deleted under C1/C8); replaced by the readout layer. |
| D8 | **Snaps never create constraints. No snap journal.** | Drops ref-spec §10's journal. |
| D9 | **Admit + flag:** a redundant or conflicting constraint is added and shown amber/red (not refused at the gate). | Same as ref-spec §7.5. |
| D10 | **State display:** glyphs + dims coloured by state (amber redundant, red conflicting); **DOF badge**; geometry **tint** by state (under-defined = ~~the theme **accent** token~~ the `constraint_free` token — **amended by D26**; fully defined = ink; conflicting = red) behind an Inspect toggle, default on, editor only. During a conflict the geometry **holds its last good solution** (no least-squares compromise). | Adds hold-last-good. |
| D11 | **SolidWorks is the behaviour reference:** boxed relation glyphs beside geometry (~~toggle, default on~~ — **amended by D32**: shown for the selection; Show Constraints is a show-all override, default off), hover a glyph → its targets glow, click → select, Delete removes it; selecting an entity lists its constraints in the property panel. SolidWorks constraint catalogue + names are the baseline. | — |
| D12 | **Selection-first** constraint buttons (enabled only when the selection is valid for that type); with nothing selected a button enters a pick mode. **One Smart Dimension tool** (tool-first) infers the dim kind from the picks + label placement. | — |
| D13 | **"Mirror" = the Symmetric constraint only.** Mirror stays an unlinked copy tool in the scene/Modify tools; no linked "Mirror Entities". | Ref-spec had Symmetric as Tier 2; promoted. |
| D14 | **One constraint type per session**, in the §12 order; Session 1 = foundation + Horizontal and retires the old system. | Replaces ref-spec §12 phasing. |
| D15 | **Ribbon:** two new groups on the Block Editor tab **after Modify** — **Constrain** (large Smart Dimension + small buttons stacked 3/column in build order) and **Inspect**. **No greyed placeholders** — each session adds its own button. *(2026-09-30: the Block Editor page is now a permanent base tab — `ribbon-bar.md` §3.4 — not a contextual page; its Definition group's disabled **Edit Attributes** button is an explicit user-ratified exception to this rule. The rule still binds the Constrain / Inspect groups.)* | Ref-spec wanted greyed Tier-2 buttons; forbidden by `icon-style-guide.md` §7. |
| D16 | **Icons:** ~~48-unit~~ on-contract (two-token; canvas **amended by D25** → the 40-unit §5.1 family); **one symbol SVG per constraint** used at ribbon (the live large/small sizes owned by `ribbon-bar.md` §3.1), canvas glyph (16 px, boxed) and panel list; whole family designed up-front as a mockup-gated contact sheet in Session 1. | — |
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

Session-1 delta decisions (2026-10-01/02 `/todo` CS1 run — Phase 2 FP1 questions, the two §10 mockup gates, and the build's user gates; each ratified by the user at that gate):

| # | Decision |
|---|---|
| D21 | **Pick mode = hover markers.** With nothing selected a constraint button enters pick mode: every participating primitive's point handles (§5.1) show as hollow square markers; hovering highlights the nearest handle (filled accent) or, before the first point pick, the nearest edge within the pick tolerance (accent glow); clicks accumulate picks until the type's arity is met, then the constraint is added. Status bar: "Horizontal: pick 2 points or 1 edge (n/2) · Esc to cancel". **Selection-first** applies only to a single selected whole-item edge (a line or reference line). Selection stays item-level — no handle selection in the selection model. |
| D22 | **Applying a constraint = least-change solve:** every variable's goal is its current value (no anchor rule). A tilted line made Horizontal moves both ends to their mean Y. ~~weight 1~~ — **amended by D34**: base weights follow D34 (positions 1, sizes `W_SIZE`, angles D28) and the translate-first pass applies. |
| D23 | **Reference lines persist in definitions:** every reference line (printed or not) is saved in the definition and re-seeded on reopen (`reference_line` joins the definition primitive factory); compile renders only printed ones. Constraints on reference lines therefore survive Save. (Fixes the pre-existing drop — §2.) |
| D24 | **Create Block from selection:** the selection's **bounding-box centre** is the base point — translated to (0,0) on seed; the replaced plan instance is placed at that centre so nothing moves visually. The plan placement point is decoupled from the definition origin (always (0,0), D4). |
| D25 | **Icon grammar (amends D16):** the constraint family joins the **40-unit Modify/2D-geo family** (`icon-style-guide.md` §5.1 — 40-unit `viewBox`, ink stroke 2.4, accent = the relation, white-centred rings where markers appear), not the 48-unit canvas: it sits beside Modify on the same tab. Approved shapes (contact sheet, real loader, both themes): Smart Dimension = accent dim line + arrowheads between two ink witness lines; Horizontal / Vertical = a bare accent line; Coincident = two ink lines meeting at an accent ring; Concentric = ink outer + accent inner circle; Symmetric = dashed ink axis + mirrored accent points; Fix = accent ground line + ink hatch; Parallel = two accent slants; Perpendicular = ink legs + accent right-angle mark; Equal = two accent parallel lines; Tangent = ink circle + accent tangent line; Midpoint = ink line + accent mid ring; Collinear = two ink segments + dashed accent bridge; Inspect: Show Constraints (eye + glyph box), Constraint Status (half-accent triangle), Delete Constraints (glyph box + accent ✕). Files `constraint_<type>_icon.svg`. |
| D26 | **Tint token (amends D10):** under-defined geometry tints with a **new `constraint_free` theme token** (blue — dark `#5B8CFF`, light `#2357D9`), not `accent`: `selection == accent` in both themes, so an accent tint would read as "selected". Fully defined = `ink`; conflicting = `danger`. The tint never overrides the selection colour on a selected item. |
| D27 | **Canvas + panel metrics (gate 2):** glyph icon 16 px, box padding 2 px, radius 3 px, `surface` fill, `line_strong` 1 px border (hover → `selection_hover`, selected → `selection`, CS2 states → `warn` / `danger`), centred 12 px off its geometry on the side away from the entity centroid, several glyphs on one anchor laid out side by side; pick markers hollow squares half-size 4 px, edge pick tolerance 6 px; X/Y axes `muted` at alpha 0.22, dash-dot `[12,4,2,4]`, non-printing; Constraints panel rows 28 px (icon · type + targets · Suppress · Delete). Constants live in `theme.M` (`CONSTRAINT_*`, `PROP_CONSTRAINT_ROW_H`). |
| D28 | **Angle variables are stiff:** an angle variable's goal weight is `ANG_SCALE²` — 1 rad of rotation costs as much as ~1000 mm of travel — so the solver prefers moving geometry to rotating it. |
| D29 | **Collapse = conflict.** A solve that can only be satisfied by collapsing a shape — a size variable the solve **moved** to or below its floor (rect w/h, circle/arc r, ellipse rx/ry, polygon R; the floors are `geometry_2d` constants: `RECT_MIN_SIZE`, `CIRCLE_MIN_RADIUS`, `ARC_MIN_RADIUS`, and `_AXIS_MIN` for ellipse rx/ry — polygon R borrows `_AXIS_MIN`, although `RegularPolygonItem` itself never clamps R) or an arc whose **raw** span `θe − θs` reaches 0 / 2π or leaves (0, 2π) — is a **conflict**: hold last good, status "Over-constrained…", the constraint is still admitted (D9). A size the solve did **not** move never counts (a sub-floor circle stays legal). Before declaring the conflict a **stiff-size retry** (every size variable `W_PIN`-stiff) runs, so a non-collapsing answer (e.g. a rotate) wins if one exists. |
| D30 | **Transformed copies keep a constraint only if the transform preserves it.** Horizontal survives a copy rotation ≡ 0 mod 180° (±1e-6°) and a reflection across a horizontal or vertical axis; any other rotation / mirror axis drops it, and the copy keeps its transformed geometry (not re-solved). Translation-only copies (Copy / Paste / Duplicate / Linear & 2D Array) keep every internal constraint. Vertical / Symmetric rules land with their sessions. |
| D31 | **Typed values are honoured exactly** (selection readout + property panel): the edited item's **changed** variables are pinned (`W_PIN`) and must land within `1e-6` of the typed value, else the edit is a conflict — rolled back, last good held. The item's unchanged variables keep the D6 `W_EDIT` anchor preference; other geometry yields. |
| D32 | **Glyph visibility (amends D11, §10):** glyphs show only for constraints touching **selected** geometry, plus the selected constraint. **Show Constraints** is a temporary show-all override, **default OFF**. No glyphs during pick mode (its markers carry the picking). Only visible glyphs pick. |
| D33 | **Polygon handles (amends §5.1/§5.3):** a regular polygon exposes `center`, vertex handles `v0..v(n-1)` and edge handles `s0..s(n-1)` (`s<i>` = `v<i>`→`v<i+1>`, closing edge included), all **derived** from its centre / R / rotation. Grip 0 → `center`, grip i (1..n) → `v<i-1>`. |
| D34 | **Solver preference: translate, then resize, then rotate (amends D22's pure least-change).** Base goal weights: positions 1, size variables `W_SIZE` (1e3), angles `ANG_SCALE²` (D28). Mechanism: a **translate-first pass** (every size + angle variable made `W_PIN`-stiffer) runs first and is taken when it honours the edit within `HONOUR_TOL` (1e-6), or moves the edit at most `HONOUR_RATIO` (1.1×) as far as the plain weighted solve does; otherwise the plain weighted solve (with its D29 retry) wins. If the plain solve fails, a pass that only "solved" by undoing the edit is a conflict too. |
| D35 | **Live drag of constrained selections.** A selection-manipulator **body drag** or **box resize** of a selection that touches an active constraint applies **live**: the real geometry is transformed and solved every frame (hold last good on a conflicting frame), Esc restores the pre-gesture state, release commits **one** undo step. Unconstrained selections keep the held-transform preview (bake on release). The **Move tool** stays commit-only (ghost; the solve runs on the destination click). **Undo/redo is refused** while any manipulator drag is in progress. |

## 2. Retired prototype (history)

Until Session 1 the codebase carried a session-only prototype: `firepro3d/constraints.py` (Concentric / Dimensional / Alignment constraints over live item references with list-index ids, solved by ≤20 Gauss-Seidel passes), two `constraint_concentric` / `constraint_dimensional` scene modes, the Align tool's `_PadlockItem` + `AlignmentConstraint`, a plan-scene geo2d "Constraints" ribbon group, a `Model_View.drawForeground` constraint-indicator block, and twelve `SceneTools._solve_constraints` call sites. Its constraints were never saved with a block definition. The Block Editor also carried a movable origin (Set Origin tool, red marker, bounding-box top-left default) and dropped reference lines on Save.

**Session 1 (2026-10-02) retired all of it** — the module, its lazy package export and API-reference entry, the modes, the padlock, the geo2d group, the foreground block, the solve call sites (each re-routed to a `ConstraintController` seam, §8), Set Origin + the red marker (D4) — and fixed the reference-line drop (D23). Grounding-time latent bugs that died with it: the `drawForeground` `c.item_a` `AttributeError`, geo2d buttons arming the plan scene, constraints lost on Save, and `_align_padlocks` surviving New/Open. One survivor is tracked separately: geometry Explode drops a closed polyline's closing segment (`todo_open.md`, independent of constraints).

## 3. Architecture

Flat `firepro3d/` package. Pure core out, Qt side-effect shell in (the `model-space-architecture.md` decomposition rule).

```
pure (no Qt logic; unit-testable)
  sketch_model.py     ConstraintType enum (whole catalogue from day one) + REGISTRY
                      (label, accepted ref-kind patterns, DOF removed, implemented flag),
                      Constraint record (inert/invalid kept verbatim), icon_for,
                      remap_for_copy (§6, §8)
  sketch_solver.py    NumpySolver (the v1 SketchSolver): System of variables +
                      aliases/fixes + residual Rows; equality substitution,
                      union-find components, weighted min-change projection
                      (§7.2), DOF by SVD (§7.4); BUILDERS = one residual builder
                      per implemented type (§7.3)
  sketch_adapters.py  per-primitive adapter: read(item) -> values, points/edges ->
                      PointExprs over the variable vector, grip index -> handle,
                      D28/D34 goal weights, D29 collapse rules, write(item, values)
                      with per-variable write tolerance (§5, §7.2)

Qt shell
  constraint_controller.py  ConstraintController — composed into EVERY Model_Space
                            (scene.constraint_ctl), enabled only for
                            scene_role == "block_editor" (inert no-ops elsewhere);
                            owns the constraint list; seams: edit() context,
                            begin_drag / drag / drag_frame / end_drag / cancel_drag,
                            add / delete / set_enabled / on_items_removed,
                            capture / restore (undo), load / to_records (definition),
                            internal_records / paste_records (copies, D30), D21 pick
                            mode, property-panel rows + ConstraintAdapter
  constraint_paint.py       non-printing X/Y axes, boxed glyphs (D32 visibility),
                            target glow, pick markers, glyph pick; painted by
                            Model_View in viewport px (the origin cross itself is
                            Model_Space.draw_origin)
  main.py                   Constrain + Inspect ribbon groups (§10)
  property_manager.py       Constraints section (§10; property-panel.md)
```

**Source of truth.** Primitive items remain the model (their internal scene-coordinate data, pos = identity per `2d-geometry.md`; text uses `pos()`). The solver never touches Qt; the controller extracts variables through adapters, solves, then performs **at most one write-back per item the solve changed** (§7.2 write tolerance) followed by one repaint. This gives the anti-drift guarantee the ref-spec sought with "model owns coordinates, scene mirrors" without inventing a second model.

**Data flow (one edit):** the seam snapshots the constrained items → the caller mutates its items → the controller builds (or, during a drag, reuses) the System, weights the edited items (`W_EDIT`) / the pinned handle or typed variables (`W_PIN`) → solves only the touched components (D34 translate-first, D29 collapse check) → write-back, or on failure restore the snapshot (D10 hold-last-good) + status "Over-constrained: the change was not applied" → the caller pushes undo after the seam exits.

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
| §7.1 build from scratch | **Kept** (B1), benchmarked (§9). |
| §7.2 model/scene separation | Kept in spirit via single write-back (§3). |
| §7.3 LM/dogleg, components, analytic Jacobians | Kept + equality substitution added (required by the §9 bench). |
| §7.4 least-norm drag | Kept for drag; typed edits anchor-weighted (D6) and exact (D31). |
| §7.5 diagnostics | Kept (D9/D10) + hold-last-good. |
| §8 dims via "annotation engine" | Engine does not exist → persisted readouts (D7). |
| §10 OSNAP → no constraint + journal | No constraint kept; **journal dropped** (D8). |
| §11 context tab + contextual ribbon tab | Property-panel Constraints section + Constrain/Inspect groups on the existing Block Editor page (D11/D15). |
| §12 phasing | Replaced by §12 one-type-per-session order (D14). |
| §14 open items | Unit → mm; Chain record → moot (no fusion); argument order → §6.3 + per-type rows; rectangle recipe → moot (rectangle is intrinsic); `tool_origin` → moot. |

## 5. Primitives, variables and handles

### 5.1 Variable adapters

Only items referenced by at least one active constraint become solver variables. The origin and axes are **constants**. Handle *kinds* are what REGISTRY patterns match against: a point handle is kind `point`, an edge handle `edge`, the origin `point`, an X/Y axis `axis`. The `curve` kind is declared in REGISTRY for later types (radius/diameter, Concentric, Equal, Tangent) but no CS1 adapter exposes a curve handle yet — it arrives with the first session that uses it.

| Primitive (`to_dict` type) | Variables | Handles (`h` names) |
|---|---|---|
| Line `draw_line` / reference line `reference_line` | x1 y1 x2 y2 | points `p1` `p2`; edge `edge` |
| Circle `draw_circle` | cx cy r | `center` |
| Arc `arc` | cx cy r θs θe | `center` `start` `end` — endpoints derived through the ArcItem's own Y-up convention (`2d-geometry.md`; Y-up CCW, Qt Y-down scene); write-back keeps `span_deg > 0` |
| Rectangle `draw_rectangle` | cx cy w h θ | points `tl tm tr rm br bm bl lm center` + edges `top right bottom left` (§5.3), derived through the rotation; write-back **canonicalizes to a centre-following pivot** (`pivot: null`) — identical scene geometry |
| Polyline `polyline` | 2 per vertex | `v<i>` `s<i>` (closing segment of a closed polyline included) |
| Polygon `polygon` | cx cy R rot | `center` + derived vertices `v0..v(n-1)` + edges `s0..s(n-1)` (D33) |
| Ellipse `draw_ellipse` | cx cy rx ry rot | `center` |
| Text `text` | x y | `ins` |
| Nested block instance `block_instance` | x y | `ins` (interior frozen — D2) |
| Spline `draw_spline` | — | **excluded in v1** (no adapter; a record naming a spline still saves, §6.4) |

Rotation of text/instances is not a variable in v1. Variable classes for D28/D34 weighting: sizes = rect w/h, circle/arc r, polygon R, ellipse rx/ry; angles = rect θ, arc θs/θe, polygon/ellipse rot; everything else is a position.

### 5.2 Polyline vertex identity

`v<i>` indices are positional. Any operation that inserts or removes vertices renumbers the affected `HandleRef`s; constraints on a removed vertex/segment cascade-delete (one undo step with the edit). *(No vertex insert/remove operation is reachable in the Block Editor at CS1.)*

### 5.3 Handle names ↔ grip indices (pinned 2026-10-01, file-format)

Grips are identified in code by an integer index into `item.grip_points()`; `sketch_adapters` owns the one map from handle name to grip index (the drag seam reports the index, the solver speaks names). During a drag a **raw** point handle pins its own two variables; a **derived** handle (rectangle point, arc `start`/`end`, polygon vertex) or a grip with no handle (a translate grip, a circle radius grip) pins every variable of its item (`_Adapter.pin_vars`).

| Primitive | Grip index → handle |
|---|---|
| Line / reference line | 0 → `p1`, 2 → `p2` (1 = the translate grip, not a handle); edge `edge` |
| Rectangle | 0 `tl`, 1 `tm`, 2 `tr`, 3 `rm`, 4 `br`, 5 `bm`, 6 `bl`, 7 `lm`, 8 `center` — in the rect's **local** frame (`top` = local min-y, Qt Y-down), mapped through θ; edges `top` (tl→tr), `right` (tr→br), `bottom` (br→bl), `left` (bl→tl) |
| Circle | 0 `center` (1–4 are radius grips — no handle in v1) |
| Arc | 0 `center`, 1 `start`, 2 `end` |
| Polyline | i → `v<i>`; segment `s<i>` = `v<i>`→`v<i+1>` (closing `s<n-1>` = `v<n-1>`→`v0` when closed) |
| Polygon | 0 → `center`, i (1..n) → `v<i-1>`; edges `s<i>` = `v<i>`→`v<i+1>` incl. the closing `s<n-1>` (D33) |
| Ellipse | 0 → `center` |
| Text / nested instance | the move grip → `ins` (text: its `pos()`, the only primitive whose geometry is not pos-identity) |

**Pivot canonicalization** (§5.1 rectangle row) happens only on a solver write-back that changes the rectangle; an unconstrained grip drag keeps today's `RectGripHandle` pivot behaviour.

## 6. File format

### 6.1 Primitive ids

Every primitive dict, including `block_instance` records, carries **`"uid"`** (uuid4 hex). Assigned at creation and carried as `item._uid`; survives undo snapshots, Save and reopen. Legacy dicts without one are assigned one **when the item is built from the dict** (`from_dict` reads `uid` if present, else keeps the one minted at construction) — `BlockDefinition.from_dict` keeps primitive dicts verbatim, so a definition round-trip never rewrites them; a legacy definition gains uids on its next save. Copy / Paste / Duplicate / Array / Mirror / Offset / block Explode mint **new** uids (§8) at the one choke point they share (`Model_Space._add_from_dict`, plus `place_block_instance` for instances); undo restore, project load and editor seeding **carry** the uid (instances included). The clipboard payload keeps the source uid (minting happens on paste, which builds the old→new `uid_map` for constraint remapping). This replaces the list-index ids the prototype used.

### 6.2 HandleRef

`{"uid": "<primitive uid>", "h": "<handle name>"}`, or a reserved ground: `{"ref": "origin"}`, `{"ref": "x_axis"}`, `{"ref": "y_axis"}`. A ref that does not resolve within the same definition is rejected at write time (no external references).

### 6.3 Constraint record

Stored in the `BlockDefinition` key **`"constraints": [...]`** (a real field, `BlockDefinition.constraints`) — additive; absent ⇒ `[]`; **no `schema` bump**. *(Library files that bundle nested blocks are already written with `schema: 2`; the additive key is safe because `BlockDefinition.from_dict` ignores `schema`.)*

```json
{"id": "<uuid hex>", "type": "horizontal", "refs": [ {HandleRef}, ... ],
 "value": null, "driving": true, "enabled": true,
 "helper": {}, "label": {"offset": [dx, dy]}}
```

- `value`: lengths in **mm**, angles in **degrees** (Y-up, CCW-positive); `null` for geometric types.
- `refs` order = **pick order**, and is significant; each type's catalogue row (§7.3, pinned per session in §12) states what the order means. Global convention: angles are measured **from `refs[0]` to `refs[1]`, CCW-positive, Y-up**.
- `helper`: disambiguation for multi-solution types — tangent side / internal, Smart Dimension kind (`aligned` / `dx` / `dy`) and sign, point-line side. Fixed at creation from the current geometry.
- `driving`: D7 (reference dims remove no DOF). `enabled`: Suppress (kept, not solved).
- `label`: persisted-dim label offset (dims only; omitted when absent).
- Unknown top-level keys on a built record are kept and re-emitted (§6.4).

**Validity.** A built-type record is solvable only if it is **valid** against the sketch: every `uid` resolves to an editor primitive, every handle exists on that primitive's adapter, the tuple of ref kinds matches one of the type's `REGISTRY` patterns, and no handle is repeated. A record that fails this on load, undo restore or paste is kept **verbatim and inert** exactly like an unknown type (§6.4); `add` refuses an invalid new record (status "Invalid constraint").

### 6.4 Forward compatibility

`ConstraintType` declares the whole §12 catalogue from day one. A record whose type is unbuilt or unknown — or a built type that is invalid (§6.3), or is not even readable — is kept **verbatim and inert**: listed in the panel as "Unsupported constraint" (read-only: Delete only, no Suppress), preserved on save, never solved, excluded from DOF. A file from a newer build never loses data in an older one.

### 6.5 Origin migration (D4)

Opening a definition whose `origin ≠ (0,0)` translates its seeded primitives by `−origin` (nested instances included — the same items are moved, uids stable) before its constraints load, and the next save writes `origin: [0,0]`. Instances render identically (compile already applies `translate(−origin)`). The `origin` field becomes a vestigial constant; its removal is a later schema cleanup. **Create Block from selection** uses the bbox **centre** as its base (D24); DXF/PDF import into the editor maps its base point to (0,0) unconditionally. *(CS3 precondition, filed: once origin-tied constraints exist the migration must translate through the controller — today it translates before the constraints load.)*

## 7. Solver

### 7.1 Interface

```python
class NumpySolver:                                   # the v1 SketchSolver (duck-typed)
    def solve(self, system, goals, weights, active=None) -> SolveResult   # x, converged, max_residual
    def diagnose(self, system) -> Diagnostics                              # nvars, rank, dof, conflicts
```

`system` = a `System` (variable vector `x`, equality `aliases` / `fixes`, residual `rows`) for one sketch; `goals`/`weights` are full-space per-variable arrays (§7.2); `active` restricts the solve to the components holding those variables. `Diagnostics.conflicts` lists contradictory fixes only; per-entity defined, redundant and conflicting constraint ids arrive with CS2 (§7.4). Swapping the engine later is a module replacement.

### 7.2 Algorithm — weighted minimum-change projection

```
minimise  ‖W½ (x − x_goal)‖²   subject to  F(x) = 0
step:     dx = g + W⁻¹Jᵀ (J W⁻¹ Jᵀ + λI)⁻¹ (−F − J g),   g = x_goal − x
```

Damped Gauss–Newton iterations starting from the goals until `F` meets the D18 linear tolerance (`1e-6` mm). **Constraints are hard; goals are soft** — so a drag can never violate a constraint, the geometry follows as far as it is allowed.

- **Base weights (D28/D34):** positions 1, sizes `W_SIZE`, angles `ANG_SCALE²`.
- **Drag:** the dragged item's variables are `W_EDIT` goals at their applied values; additionally pinned (`W_PIN`) are the grabbed handle's two variables when it is a raw point, else (a derived handle — rectangle point, arc `start`/`end`, polygon vertex — or a handle-less grip) every variable of the item (§5.3); every other variable's goal is its current value. A D35 body / resize frame weights the whole dragged selection `W_EDIT`.
- **Typed edit (D6/D31):** the edit's own typed setter mutates the real item inside the controller's `edit()` context; on exit the item's **changed** variables are pinned `W_PIN` and must land within `1e-6` of the typed value, its unchanged variables keep `W_EDIT` (the D6 anchors), and the rest re-solves. With no constraints present the result equals today's readout behaviour.
- **Transform / modify commits:** the transformed items are `W_EDIT` goals (not typed — no exactness requirement).
- **Translate-first pass (D34):** run first with sizes + angles made `W_PIN`-stiffer; taken when it honours the edit within `HONOUR_TOL` or within `HONOUR_RATIO` of the plain solve, else the plain weighted solve.
- **Equality substitution** (before solving): raw-variable equalities become **aliases** (`y₂ := y₁`) and constants become **fixes** (`y := 0`) instead of rows; contradictory fixes are reported as conflicts without iterating. Required, not an optimization (§9). In CS1 only Horizontal emits them (§7.3); Coincident, Vertical, Concentric and Fix will.
- **Components:** union-find over shared free variables; only components containing a changed variable (plus any component reading a changed fix) are solved — everything else keeps its values bit-for-bit.
- **Numerics:** relative Tikhonov damping (`λ` = a tiny fraction of the largest diagonal of `J W⁻¹ Jᵀ`, so a `W_PIN` solve is not biased off-manifold); the iteration stops early once every row is within `1e-3 × LIN_TOL`, and is capped. The substitution/component analysis is cached on the `System`, keyed on its content (aliases, fixes, row identities, size) — a drag reuses one System across frames and only refreshes `x`.
- **Scaling:** angles are radians inside the solver. Angular residual rows (CS5+) are to be multiplied by `ANG_SCALE` (1000 mm) so mm and radian residuals are commensurate; CS1 has none.
- **Collapse (D29):** a converged solve that collapses a shape is retried with sizes stiff, then reported as a conflict.
- **Write-back tolerance:** settled **per variable** — a value within `POS_WRITE_TOL` (1e-7 mm; positions and sizes) or `ANG_WRITE_TOL` (1e-8 rad) of the item's old value keeps the old value, and an item with no variable beyond tolerance is not written at all. Solver noise never re-writes an unmoved item (a rect write would canonicalize its pivot) and an axis-aligned rect stays exactly axis-aligned.
- **Failure:** if tolerance is not met (or D29/D31 rejects the result), nothing is written back, any edit already applied is restored (D10 hold-last-good), and the status bar reports the conflict.

### 7.3 Residual catalogue

`d = b − a` for a line's direction; normalized forms guard `‖d‖ < ε`.

| Type | Refs (order) | DOF | Residual |
|---|---|---|---|
| Horizontal **— BUILT CS1 (2026-10-02, `2a22ba9`)** | edge, or 2 points | 1 | `y_b − y_a` (substituted) |
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

**Pinned — Horizontal (Session 1, 2026-10-01; BUILT 2026-10-02):** `refs` = `[edge]` (`edge` / `s<i>` / a rectangle or polygon edge) **or** `[point, point]` (any two §5.3 point handles, or one point + `{"ref":"origin"}` ⇒ the point lies on the X axis); order is not significant (the residual is symmetric). `helper` = `{}`, `value` = `null`. Raw-variable cases (line / reference line / polyline points, text / instance `ins`, circle / arc / polygon / ellipse `center`, origin) are **substituted** (`y_b := y_a`, origin ⇒ `y := 0`); handles derived through other variables (rectangle points/edges via θ, arc `start`/`end` via θ, polygon vertices/edges, D33) add a **row**. Applying it is a D22/D34 least-change solve. Degenerate: a zero-length edge is accepted (trivially satisfied); two refs naming the same handle are refused at the pick (status "Pick a different point") and are invalid in a stored record (§6.3).

### 7.4 Diagnostics (on commit, not per drag frame)

- **DOF** per component = variables − rank(J) (SVD, relative tolerance); substituted variables counted; the sketch DOF is the sum. **Fully defined** ⇔ DOF = 0 — which includes grounding, because the origin/axes are constants. **Built CS1:** the sketch DOF (all participating items' variables minus what the active constraints remove) is shown in the Constraints panel footer.
- **Per-entity defined (D10 tint):** an entity is fully defined iff its variables have ~zero components across J's **null-space basis** (same SVD). *(CS2.)*
- **Redundant (amber):** removing the constraint's rows does not reduce rank, and its residual is satisfied. *(CS2.)*
- **Conflicting (red):** the solve cannot reach tolerance; the constraints whose rows lie in the dependent set with non-zero residual are marked red. Geometry holds last good. *(Hold-last-good + the conflict status are built in CS1; the red marking is CS2.)*

## 8. Operations on constrained geometry (D17)

Every Block Editor edit routes through one `ConstraintController` seam; with no active constraint on the touched items each seam is a no-op (pre-constraint behaviour).

| Operation | Behaviour |
|---|---|
| Delete an entity | Every constraint touching it cascade-deletes inside the same undo step (scene delete; an inline text edit committed empty). |
| Grip drag | `GripHandle` press/drag/release/Esc → `begin_drag` / `drag` (solve every frame, hold last good on a conflicting frame) / `end_drag` (then the commit pushes one undo step) / `cancel_drag` (restores every item the gesture's solves wrote). |
| Typed readout / property-panel edit | Through `edit(typed=True)` — D31 exact; a value that cannot be honoured is rolled back with the conflict status. Readout + panel edits no longer bypass constraints. |
| Selection-manipulator body drag / box resize | Constrained selection → **live** per D35 (real geometry + solve per frame, hold last good, Esc restores, one undo step on release); unconstrained → held-transform preview, baked on release through `edit()`. |
| Move tool / Rotate / Scale / Flip / Align | Commit-only: the Move tool shows a ghost and solves on the destination click (`move_items` inside `edit()`); Rotate, Scale, in-place Flip and Align apply inside `edit()` — the moved items are `W_EDIT` goals, the rest re-solves, a conflict rolls the whole commit back. **Refusal of grounded selections is not built:** with Horizontal as the only type a selection can never be fully defined (X stays free), so the refusal, its dry-run seam and its E2E guard land with the first session that can ground a selection (CS3 Coincident-to-origin). |
| Copy / Paste / Duplicate / Array | New uids; constraints **internal** to the copied set are copied and remapped onto the copies; constraints to anything outside (including origin/axes) are dropped. Polar Array copies follow D30 (each copy's rotation). |
| Mirror (scene tool, D13) | As Copy, filtered by D30 (Horizontal kept only for a horizontal / vertical axis). In-place Flip is an `edit()` transform (above). |
| Offset | New geometry, no constraints. |
| Block Explode (Block Editor) | The exploded nested instances' constraints (on their `ins`) cascade-delete in the explode's undo step; status "N constraint(s) removed". |
| Trim / Extend / Break / Fillet / Join / geometry Explode | Intended: the consumed entities' constraints are dropped, results start free, status "N constraints removed"; smart remapping deferred. *(Not reachable in the Block Editor — no ribbon button or shortcut; Join / geometry Explode / Break currently remove items without the cascade — filed, to be wired when exposed.)* |
| Block Save → instances | Frozen (D2); compile unchanged. Save writes every solvable record whose refs resolve plus every inert record verbatim. |
| Undo / redo | The constraint list is captured in every undo snapshot (`"constraints"`) and restored after the items are rebuilt (records re-validated, §6.3). Undo / redo are **refused while any manipulator gesture is in progress** — grip drags included, not only D35 (`selection-manipulator.md` "Undo & domains"). |

Known divergence (filed): when an `edit()` rolls back a conflicting modify-tool commit, the tool still pushes an (unchanged) undo step.

## 9. Performance (D18)

**P4 probe (2026-09-29, design-time):** a naive dense whole-sketch solve measured 31 ms per drag frame / 107 ms rank diagnostics on a synthetic 200-line / 300-constraint block — so component partitioning **and** equality substitution were made Session-1 requirements.

**Measured at CS1 close (2026-10-02, real solver + controller; perf tests `tests/test_sketch_solver_perf.py`, `tests/test_constraint_live_drag.py`):**

| Case | Measured | D18 bar |
|---|---|---|
| Realistic composition (symbols of ~5), solver drag frame | ~0.6–1 ms | ≤ 8 ms ✓ |
| Honest one-component 150-row chain, solver drag frame | ~3–8 ms (≈3–4 normally; 7.8 ms on a memory-starved host) | ≤ 8 ms ✓ (tight) |
| Controller grip-drag frame (real scene) | ~3–4 ms | ≤ 8 ms ✓ |
| Constrained D35 body-drag frame (modest sketch) | ~2.8 ms | ≤ 8 ms ✓ |
| Commit (solve + diagnose) / open (load + first solve), synthetic block | ~4–7 ms / ~7–10 ms | ≤ 50 / ≤ 200 ms ✓ |
| **Rect-heavy worst case** (one component: 100 rects + 100 lines, 299 Horizontal) | grip-drag frame **~19 ms**, D35 body-drag frame **~57 ms** | ≤ 8 ms ✗ — **OPEN** |

The rect-heavy case is a strict-xfail bench tracked by the P1 follow-up "D18 rect-heavy drag perf" in `todo_open.md` (vectorised derived rows, skip the D34 second solve when no size/angle variable moves, no full-snapshot rewrite per D35 frame), to land before CS3. **The D18 acceptance criterion stays PARTIAL until it does.**

## 10. User interface

- **Ribbon (D15):** Block Editor tab = Block | Definition | 2D Geometry | Edit | Modify | **Constrain** | **Inspect** (as-built groups through Modify, and their editor-only enable state, owned by `ribbon-bar.md` §3.4). **Built CS1:** Constrain = **Horizontal** (small, checkable); Inspect = **Show Constraints** (checkable toggle — the D32 show-all override, default off) + **Delete Constraints** (the selected constraint, or every constraint on the selected geometry). A Constrain button with a valid selection adds at once (selection-first, D21); with nothing selected it enters pick mode (D12/D21); any other selection disables the button. **Later:** the large Smart Dimension button (CS4), the Constraint Status tint toggle and the DOF badge (CS2), one small button per type in §12 order stacked 3/column — never a greyed placeholder. Every button carries a tooltip.
- **Smart Dimension (D12, CS4+):** tool-first; one line → length; two points → distance with aligned / Δx / Δy chosen by label placement; circle → diameter; arc → radius; two lines → angle; point + line → point-line distance. Plus D7's lock glyph on transient readouts.
- **Canvas (D10/D11/D32):** origin cross (`Model_Space.draw_origin`) + non-printing X/Y axes; boxed 16 px constraint glyphs beside their geometry (screen-constant, non-printing), shown per **D32** (selected geometry's constraints + the selected constraint; Show Constraints = show all; none in pick mode). Hover a glyph → its targets glow; click selects it (item selection clears); Delete removes it; Esc deselects it. **Pick order:** grips > dim labels > glyphs > origin/axes > HALO geometry. Persisted dims (CS4) and state colours + tint (CS2) later.
- **Property panel:** a **Constraints** section for a single selected entity (its constraints) or a selected constraint (`ConstraintAdapter`) — rows of icon, type name, targets, Suppress, Delete (inert rows: Delete only), hover = target glow, click = select; footer "Sketch DOF N". Built on `ui_kit.ActionRowList` with rows from `ConstraintController.panel_rows()`; the panel mechanics are owned by `property-panel.md`. Dim values + Driving/Reference arrive with CS4.
- **Status bar:** "Over-constrained: the change was not applied", "Invalid constraint", "Pick a different point", pick progress, and "N constraint(s) removed".
- **Icons (D16/D25):** `firepro3d/graphics/Ribbon/constraint_<type>_icon.svg`, the **40-unit** §5.1 two-token family, one symbol per type reused for ribbon/glyph/panel via `sketch_model.icon_for` (unknown types → the neutral Show Constraints glyph); guarded by `_CONSTRAINT_ICONS` in `tests/test_icon_theming.py`. The whole approved family (16 icons) is committed in Session 1; each type's button still ships only with its session (D15).
- **Pick mode (D21)** and the canvas/panel metrics (D27); tint colours (D26).
- **Mockup gates (Session 1, before code): both PASSED 2026-10-01.** (1) Icon-family contact sheet rendered through the real loader at the live ribbon large/small sizes + the 16 px glyph, light + dark, plus a live `RibbonBar.grab()` beside the shipped Modify icons → grammar B + eight redraws (D25). (2) Interactive canvas + panel mock (pick mode, glyph hover/select/Delete, tint candidates, panel rows) → D26/D27.

## 11. Per-session done contract (D20)

**Guard tests each constraint session ships** (VC3 — real objects, observable ground truth):

1. **Math:** residual zero on satisfying geometry, non-zero otherwise; analytic Jacobian matches finite differences on random configurations; DOF removed equals the catalogue value.
2. **End-to-end on a real Block Editor scene:** build geometry, select, click the real ribbon button, drag a grip with posted events on a shown view; assert the observable geometry (e.g. Horizontal: `p1.y == p2.y` after a drag that tried to tilt it). Shown RED with the type's residual reverted.
3. **Persistence:** save block → close editor → reopen: constraint, glyph and geometry return; a placed instance renders the solved (frozen) geometry.
4. **Undo/redo** of add, delete, and a solver-driven edit.
5. **Diagnostics:** a redundant case goes amber; a conflicting case goes red and holds last good — pixel-sampled in both themes. *(From CS2; CS1 guards hold-last-good + the conflict status.)*
6. **Ribbon:** the button enables only on a valid selection; the icon passes `test_icon_theming.py`.

**Session done:** full suite green (VC6) → user smoke from a checklist with exact commands → user approval → this spec's catalogue row flipped to built + `verified-commit` stamped → smoke-found spec deltas reconciled → next session.

## 12. Session plan (D14)

| # | Session | Also delivers |
|---|---|---|
| 1 | **Foundation + Horizontal — BUILT 2026-10-02** (`feat/cs1-constraint-foundation`, closed at `2a22ba9`; user smoke passed) | `sketch_model` / `sketch_solver` / `sketch_adapters` / `constraint_controller` / `constraint_paint`; primitive `uid`s; `constraints` in `BlockDefinition`; §6.5 origin migration + Set Origin/red-marker retirement; D23 reference lines persist; D24 bbox-centre base; X/Y axes drawn; D32 glyph paint; Constraints panel section; Constrain (Horizontal) + Inspect (Show / Delete Constraints) groups; every §8 seam incl. D35 live drag; retired `constraints.py`, the constraint modes, `drawForeground` §3b, the geo2d Constraints group, the Align padlock / `AlignmentConstraint` (coupled tests rewritten/retired, VC5); D18 perf tests; both mockup gates; build rulings D28–D35. **Open from CS1:** rect-heavy D18 worst case (§9), D17 grounded refusal (→ CS3). |
| 2 | **Vertical + diagnostics** | DOF badge, tint, amber/red (H+V on one line = first conflict test). |
| 3 | **Coincident** | point↔point, point↔origin, point-on-curve / point-on-axis; the D17 grounded-selection refusal. |
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

- [x] Constraints are authored only in the Block Editor; the plan scene never holds or solves them (C1/C8 preserved). *(CS1: the controller is inert outside the `block_editor` role; `constrain_*` modes are refused there.)*
- [x] Constraints persist in the block definition across Save / close / reopen and app restart; instances render solved geometry and never re-solve.
- [x] Drag, typed readout, property-panel and modify-tool edits all honour constraints; with no constraints, behaviour equals today's. *(CS1: every reachable seam, incl. D35 live drag; Trim/Extend/Break/Join remain unreachable.)*
- [ ] DOF badge, fully-defined state (grounding counted), per-entity tint, amber redundant and red conflicting states are correct; conflicts hold last-good geometry. *(Partial: hold-last-good + conflict status + panel sketch DOF built; badge, tint, amber/red → CS2.)*
- [ ] D17 operation rules hold, including refusal of Move/Rotate/Scale on grounded selections. *(Partial: delete cascade, copy/mirror/array (D30), explode cascade built; grounded refusal → CS3.)*
- [ ] D18 performance bars met on the synthetic 200/300 block (both worst-case and realistic compositions). *(Partial: realistic + one-component chain met; rect-heavy worst case open — §9.)*
- [x] Unknown/unbuilt constraint records round-trip untouched. *(Also invalid and unreadable records — §6.3/§6.4.)*
- [x] Every shipped constraint has an approved 40-unit two-token icon used on ribbon, canvas and panel. *(D25; was "48-unit" before the gate.)*

## Verification Checklist

- [x] Per-session §11 guards shown RED-then-GREEN. *(Session 1.)*
- [x] Full suite green on the final tree each session (VC6). *(Session 1; one intermittent flake filed.)*
- [x] User smoke + approval each session. *(Session 1, 2026-10-02.)*
- [ ] This spec's §7.3/§12 rows stamped as each type ships; `status` moves proposal → partial (after Session 1 — **done**) → current (after Session 15).
- [x] `SPEC-INDEX.md` row updated (applies-to gains the new modules; `scene_tools.py` constraint responsibility removed). *(2026-10-02.)*
