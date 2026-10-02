---
status: proposal          # designed + grilled 2026-09-29, unbuilt. The prototype this file used to describe (constraints.py: Concentric/Dimensional/Alignment + iterative solver) is RETIRED by Session 1 (§12) — see §2 "As-built (to be retired)".
last-verified: 2026-10-01  # CS1 Phase 2/3 deltas: D21–D27 added (FP1 questions + both §10 mockup gates passed), §2 re-derived at 406747b (12 solve sites, Set Origin/marker/bbox-TL default, reference-line drop), §5.3 handle↔grip map, §6 uid/schema/migration clarifications, Horizontal row pinned; prior 2026-09-30 ribbon-surface wording re-pointed at the permanent Block Editor tab (feat/block-editor-ribbon-tab); §2 as-built files unchanged since 2e511cd (git diff empty for constraints.py / geometry_2d.py / the geo2d constraints group); prior 2026-09-29
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
| D10 | **State display:** glyphs + dims coloured by state (amber redundant, red conflicting); **DOF badge**; geometry **tint** by state (under-defined = ~~the theme **accent** token~~ the `constraint_free` token — **amended by D26**; fully defined = ink; conflicting = red) behind an Inspect toggle, default on, editor only. During a conflict the geometry **holds its last good solution** (no least-squares compromise). | Adds hold-last-good. |
| D11 | **SolidWorks is the behaviour reference:** boxed relation glyphs beside geometry (toggle, default on), hover a glyph → its targets glow, click → select, Delete removes it; selecting an entity lists its constraints in the property panel. SolidWorks constraint catalogue + names are the baseline. | — |
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

Session-1 delta decisions (2026-10-01 `/todo` CS1 run — Phase 2 FP1 questions + the two §10 mockup gates, each ratified by the user at that gate):

| # | Decision |
|---|---|
| D21 | **Pick mode = hover markers.** With nothing selected a constraint button enters pick mode: every participating primitive's handles (§5.1) show as hollow square markers; hovering highlights the nearest handle (filled accent) or, before the first point pick, the nearest edge within the pick tolerance (accent glow); clicks accumulate picks until the type's arity is met, then the constraint is added. Status bar: "Horizontal: pick 2 points or 1 edge (n/2) · Esc to cancel". **Selection-first** applies only to a single selected whole-item edge (a line or reference line). Selection stays item-level — no handle selection in the selection model. |
| D22 | **Applying a constraint = pure least-change solve:** every variable's goal is its current value, weight 1 (no anchor rule). A tilted line made Horizontal moves both ends to their mean Y. |
| D23 | **Reference lines persist in definitions:** every reference line (printed or not) is saved in the definition and re-seeded on reopen (`reference_line` joins the definition primitive factory); compile renders only printed ones. Constraints on reference lines therefore survive Save. (Fixes the pre-existing drop — §2.) |
| D24 | **Create Block from selection:** the selection's **bounding-box centre** is the base point — translated to (0,0) on seed; the replaced plan instance is placed at that centre so nothing moves visually. The plan placement point is decoupled from the definition origin (always (0,0), D4). |
| D25 | **Icon grammar (amends D16):** the constraint family joins the **40-unit Modify/2D-geo family** (`icon-style-guide.md` §5.1 — 40-unit `viewBox`, ink stroke 2.4, accent = the relation, white-centred rings where markers appear), not the 48-unit canvas: it sits beside Modify on the same tab. Approved shapes (contact sheet, real loader, both themes): Smart Dimension = accent dim line + arrowheads between two ink witness lines; Horizontal / Vertical = a bare accent line; Coincident = two ink lines meeting at an accent ring; Concentric = ink outer + accent inner circle; Symmetric = dashed ink axis + mirrored accent points; Fix = accent ground line + ink hatch; Parallel = two accent slants; Perpendicular = ink legs + accent right-angle mark; Equal = two accent parallel lines; Tangent = ink circle + accent tangent line; Midpoint = ink line + accent mid ring; Collinear = two ink segments + dashed accent bridge; Inspect: Show Constraints (eye + glyph box), Constraint Status (half-accent triangle), Delete Constraints (glyph box + accent ✕). Files `constraint_<type>_icon.svg`. |
| D26 | **Tint token (amends D10):** under-defined geometry tints with a **new `constraint_free` theme token** (blue — dark `#5B8CFF`, light `#2357D9`), not `accent`: `selection == accent` in both themes, so an accent tint would read as "selected". Fully defined = `ink`; conflicting = `danger`. The tint never overrides the selection colour on a selected item. |
| D27 | **Canvas + panel metrics (gate 2):** glyph icon 16 px, box padding 2 px, radius 3 px, `surface` fill, `line_strong` 1 px border (hover → `selection_hover`, selected → `selection`, CS2 states → `warn` / `danger`), centred 12 px off its geometry on the side away from the entity centroid, several glyphs on one anchor laid out side by side; pick markers hollow squares half-size 4 px, edge pick tolerance 6 px; X/Y axes `muted` at alpha 0.22, dash-dot `[12,4,2,4]`, non-printing; Constraints panel rows 28 px (icon · type + targets · Suppress · Delete). Constants live in `theme.M` (`CONSTRAINT_*`, `PROP_CONSTRAINT_ROW_H`). |

## 2. As-built (to be retired in Session 1)

Checked at `2e511cd`; **re-derived at `406747b` (2026-10-01 CS1 grounding)** — the additions below that check are marked *(406747b)*. This is what exists today; none of it survives Session 1.

- `firepro3d/constraints.py` — `Constraint` base (`solve(moved_item)`, `involves`, `visual_points`, `to_dict(item_to_id)`, factory `from_dict` on `constraint_type`), `ConcentricConstraint` (writes `_center`), `DimensionalConstraint` (grip indices + `apply_grip`), `AlignmentConstraint` (moves target via `moveBy`, breaking the primitives' pos-identity convention), `solve_constraints` (≤20 Gauss-Seidel passes, stall after 3).
- Scene state on `Model_Space`: `_constraints`, `_constraint_circle_a`, `_constraint_grip_a`, `_align_padlocks`; modes `constraint_concentric` / `constraint_dimensional` → `_press_constraint`; ids = index into `SceneTools._all_geometry_items()`; captured only into undo snapshots (`_capture_constraints` / `_restore_network`).
- `SceneTools._solve_constraints` call sites *(406747b: 12, not the 7 first listed)*: `manip_handle` `GripHandle.on_drag` / `on_release`; `selection_manipulator` `_bake_move` / `_bake_scale`; `modify_tools_controller` `commit_rotate`, `commit_reflect` (Flip, in-place branch), `commit_scale`, `commit_array` (Polar branch); `Model_Space.move_items` (Move only — Paste does **not** solve); `model_view.mouseDoubleClickEvent` (dim edit); and the two legacy constraint click handlers in `scene_tools`. **Not** called from readout commits, panel `_dim_edit`, `paste_items` or `commit_duplicate`.
- *(406747b)* Also retired with the module: the lazy `"Constraint"` export in `firepro3d/__init__.py`, the `"constraints"` entry in `docs/gen_ref_pages.py`, the mode labels / cursors / `_initial_steps` text for the two constraint modes (remove `_PRESS_DISPATCH` rows and `_MODE_LABELS` together — `test_badge_has_a_friendly_label_for_every_dispatched_mode` pairs them), and the `mouseDoubleClickEvent` dimensional-edit block.
- *(406747b)* **Block-editor origin (D4 retirement surface):** the **Set Origin** tool (`set_origin` mode, `originPicked` signal, `_press_set_origin`, ribbon button — its `insert_block_icon.svg` is shared, keep the file), the movable **red origin marker** (`BlockEditorWidget._ensure_origin_marker`, `_block_origin_marker_item`, its snap-target registration), and the **bounding-box top-left default** of `BlockEditorWidget.origin_point()` (new definitions get a non-zero origin today). The white (0,0) cross (`Model_Space.draw_origin`) stays — it is the D3/D4 origin.
- *(406747b)* **Reference lines are not persisted** (fixed by D23): the definition primitive factory has no `reference_line` key, so a printed reference line is saved but skipped by compile and dropped on reopen, and a non-printed one is not saved at all.
- `_PadlockItem` (scene_tools) creates `AlignmentConstraint` after an Align move — session-only (not saved, dropped on load, wiped by undo).
- `main.py` `_build_geo2d_constraints_group` (`_GEO2D_CONSTRAINT_TOOLS` + disabled placeholders) lives on the plan-scene 2D-geometry contextual tab, never shown in the Block Editor.
- `scene_io` discards any `constraints` payload (C8 clean-drop).
- **Divergences / latent bugs found during grounding** (filed as follow-ups; most dissolve with the retirement): (a) `Model_View.drawForeground` §3b reads `c.item_a` on every constraint — a Concentric/Alignment constraint raises `AttributeError` and skips the rest of the foreground paint; (b) geo2d Constraints buttons call `self.scene.set_mode` (plan scene) not `_active_scene()`; (c) Block Editor constraints are lost on Save (`commit_block` carries only primitives + origin); (d) `explode_selected_items` drops a **closed** polyline's closing segment (independent of constraints — survives the retirement); *(406747b)* (e) `scene_io._clear_scene` resets `_constraints` but not `_align_padlocks`, so the next undo restore after New/Open touches deleted padlock items (code-read; dissolves with the retirement).

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
| Rectangle `draw_rectangle` | cx cy w h θ | points `tl tm tr rm br bm bl lm center` + edges `top right bottom left` (named in §5.3 — the grips are index-only in code); derived through the rotation; write-back **canonicalizes to a centre-following pivot** (`pivot: null`) — identical scene geometry |
| Polyline `polyline` | 2 per vertex | `v<i>` `s<i>` (closing segment of a closed polyline included) |
| Polygon `polygon` | cx cy R rot | `center` |
| Ellipse `draw_ellipse` | cx cy rx ry rot | `center` |
| Text `text` | x y | `ins` |
| Nested block instance `block_instance` | x y | `ins` (interior frozen — D2) |
| Spline `draw_spline` | — | **excluded in v1** |

Rotation of text/instances is not a variable in v1. Handle *kinds* (point / line-like edge / curve / scalar) are what REGISTRY arity rules match against.

### 5.2 Polyline vertex identity

`v<i>` indices are positional. Any operation that inserts or removes vertices renumbers the affected `HandleRef`s; constraints on a removed vertex/segment cascade-delete (one undo step with the edit).

### 5.3 Handle names ↔ grip indices (pinned 2026-10-01, file-format)

Grips are identified in code by an integer index into `item.grip_points()`; `sketch_adapters` owns the one map from handle name to grip index (the drag seam reports the index, the solver speaks names).

| Primitive | Grip index → handle |
|---|---|
| Line / reference line | 0 → `p1`, 2 → `p2` (1 = the translate grip, not a handle); edge `edge` |
| Rectangle | 0 `tl`, 1 `tm`, 2 `tr`, 3 `rm`, 4 `br`, 5 `bm`, 6 `bl`, 7 `lm`, 8 `center` — in the rect's **local** frame (`top` = local min-y, Qt Y-down), mapped through θ; edges `top` (tl→tr), `right` (tr→br), `bottom` (br→bl), `left` (bl→tl) |
| Circle | 0 `center` (1–4 are radius grips → the `curve`) |
| Arc | 0 `center`, 1 `start`, 2 `end` |
| Polyline | i → `v<i>`; segment `s<i>` = `v<i>`→`v<i+1>` (closing `s<n-1>` = `v<n-1>`→`v0` when closed) |
| Polygon / ellipse | 0 → `center` |
| Text / nested instance | the move grip → `ins` (text: its `pos()`, the only primitive whose geometry is not pos-identity) |

**Pivot canonicalization** (§5.1 rectangle row) happens only on a solver write-back; an unconstrained grip drag keeps today's `RectGripHandle` pivot behaviour.

## 6. File format

### 6.1 Primitive ids

Every primitive dict, including `block_instance` records, gains **`"uid"`** (uuid4 hex). Assigned at creation and carried as `item._uid`; survives undo snapshots, Save and reopen. Legacy dicts without one are assigned one **when the item is built from the dict** (`from_dict` reads `uid` if present, else mints) — `BlockDefinition.from_dict` keeps primitive dicts verbatim, so a definition round-trip never rewrites them; a legacy definition gains uids on its next save. Copy / Paste / Duplicate / Array / Mirror / Offset / block Explode mint **new** uids (§8) at the one choke point they share (`Model_Space._add_from_dict`, plus `place_block_instance` for instances); undo restore, project load and editor seeding **carry** the uid (instances included — their restore path must not drop it). The clipboard payload keeps the source uid (minting happens on paste). This also replaces the list-index ids the undo snapshot uses for constraints today.

### 6.2 HandleRef

`{"uid": "<primitive uid>", "h": "<handle name>"}`, or a reserved ground: `{"ref": "origin"}`, `{"ref": "x_axis"}`, `{"ref": "y_axis"}`. A ref that does not resolve within the same definition is rejected at write time (no external references).

### 6.3 Constraint record

Stored in a new `BlockDefinition` key **`"constraints": [...]`** — additive; absent ⇒ `[]`; **no `schema` bump**. *(2026-10-01: schema 2 is not merely reserved — library files that bundle nested blocks are already written with `schema: 2`; the additive key is still safe because `BlockDefinition.from_dict` ignores `schema`. `from_dict` currently drops unknown top-level keys, so `constraints` must be a real field, not a pass-through.)*

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

Opening a definition whose `origin ≠ (0,0)` translates its primitives by `−origin` (nested `block_instance` records' `pos` included) and writes `origin: [0,0]` on the next save. Instances render identically (compile already applies `translate(−origin)` — verified at `406747b`). The `origin` field becomes a vestigial constant; its removal is a later schema cleanup. The editor's bounding-box top-left origin default is retired with Set Origin; **Create Block from selection** uses the bbox **centre** as its base (D24); DXF/PDF import into the editor maps its base point to (0,0) unconditionally.

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

**Pinned — Horizontal (Session 1, 2026-10-01):** `refs` = `[edge]` (`edge` / `s<i>` / a rectangle edge) **or** `[point, point]` (any two §5.3 point handles, or one point + `{"ref":"origin"}` ⇒ the point lies on the X axis); order is not significant (the residual is symmetric). `helper` = `{}`, `value` = `null`. Raw-variable cases (line / reference line / polyline points, text / instance `ins`, circle / arc / polygon / ellipse `center`, origin) are **substituted** (`y_b := y_a`, origin ⇒ `y := 0`); handles derived through other variables (rectangle points/edges via θ, arc `start`/`end` via θ) add a **row**. Applying it is a D22 least-change solve. Degenerate: a zero-length edge is accepted (trivially satisfied); two refs naming the same handle are refused at the pick (status "Pick a different point").

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
| Move / Rotate / Scale a selection | Moved handles become drag goals; the rest re-solves. **Refused** (dry-run first, nothing mutated) if the selection is grounded — status bar: "Selection is fully defined — remove Fix/grounding constraints to move". *(2026-10-01: with Horizontal as the only built type a selection can never be fully defined — X stays free — so the refusal is unreachable in Session 1. Session 1 ships the dry-run seam; the refusal and its E2E guard land with the first session that can ground a selection, CS3 Coincident-to-origin.)* |
| Copy / Paste / Duplicate / Array | New uids; constraints **internal** to the copied set are copied and remapped; constraints to anything outside (including origin/axes) are dropped. |
| Mirror (scene tool, D13) | As Copy; internal constraints reflected (H/V preserved; Symmetric pairs preserved). |
| Offset | New geometry, no constraints. |
| Trim / Extend / Break / Fillet / Join / Explode | The consumed entities' constraints are dropped; results start free; status bar "N constraints removed". Smart remapping deferred. *(406747b: Trim/Extend/Break/Fillet/Chamfer/Join and geometry Explode have no ribbon button or shortcut — guarded by tests only until reachable; the Block Editor's Explode is block-only, and exploding a nested instance drops the constraints on its `ins`.)* |
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
- **Icons (D16/D25):** `firepro3d/graphics/Ribbon/constraint_<type>_icon.svg`, the 40-unit §5.1 two-token family, one symbol per type reused for ribbon/glyph/panel; guarded by a `_CONSTRAINT_ICONS` list in `tests/test_icon_theming.py`. The whole approved family is committed in Session 1 (D16 designs it up front); each type's button still ships only with its session (D15).
- **Pick mode (D21)** and the canvas/panel metrics (D27); tint colours (D26).
- **Mockup gates (Session 1, before code): both PASSED 2026-10-01.** (1) Icon-family contact sheet rendered through the real loader at the live ribbon large/small sizes + the 16 px glyph, light + dark, plus a live `RibbonBar.grab()` beside the shipped Modify icons → grammar B + eight redraws (D25). (2) Interactive canvas + panel mock (pick mode, glyph hover/select/Delete, tint candidates, panel rows) → D26/D27.

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
