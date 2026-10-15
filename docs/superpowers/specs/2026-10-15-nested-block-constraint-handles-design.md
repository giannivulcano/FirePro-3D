---
status: proposal          # designed 2026-10-15, unbuilt; promoted into parametric-constraint-system.md at Account
last-verified: 2026-10-15
verified-commit: 1f4cbbcb
applies-to:
  - firepro3d/sketch_adapters.py        # _NestedAdapter (replaces _InsAdapter), "pose" point family
  - firepro3d/sketch_solver.py          # CurveExpr.r_const, const-radius consumers
  - firepro3d/constraint_controller.py  # active() re-validation, on_items_exploded, Fix v0 migration in _adopt
  - firepro3d/sketch_model.py           # remap_exploded, nested handle path helpers
  - firepro3d/block_snap_geometry.py    # walker yields nested-record paths + composed origins
  - firepro3d/block_explode.py          # uid_map out-param
  - firepro3d/model_space.py            # explode: remap before cascade-delete
source-tasks:
  - todo_open.md "Nested block primitives participate in constraints like loose primitives" [type:feature] [P1]
related:
  - docs/specs/parametric-constraint-system.md   # governing spec (D2, D5, §5.1, §5.3, §6.2, §8 Explode row)
  - docs/specs/block-system.md                   # instance pose (P = T·R·S·M), posed snap stand-ins
  - todo_closed.md "Snap/ALIGN completeness for blocks" (2026-10-15, feat/block-primitive-snap)
---

# Nested Block Constraint Handles — Design Spec

## Goal

In the Block Editor, a nested block instance exposes its primitives' geometry — vertices, edge midpoints, edges, arcs/circles, and the origins of its own nested blocks — as constraint handles, exactly as the shipped block-primitive-snap work exposes them to SNAP / ALIGN. Loose geometry constrains to a sub-block's handles and sub-blocks to each other; the sub-block stays rigid (interior frozen, D2) and the solver positions it by translating **and rotating** it.

## Motivation

Compound fire-protection symbols (valve = body block + handle block + loose lines) are assembled from sub-blocks. Today a sub-block participates only through its insertion point, so nothing can hold a loose line on a sub-block's arc centre or keep two sub-blocks' edges parallel. Snap already builds posed stand-ins of a placed block's primitives (`block_snap_geometry.posed_primitives`); the constraint system reuses that one geometry set so snap, align and constraints agree.

## Architecture & Constraints

- Governing spec: `docs/specs/parametric-constraint-system.md`. This design **amends D5** ("nested block instances expose only their insertion point") and §5.1's "rotation of instances is not a variable in v1". D2 (interior frozen, Block Editor only) and D1 (atom = the typed item exposing named handles) hold.
- The adapter protocol (`_Adapter.read / points / edges / curves / mid_names / hidden_names / grip_handle / pin_vars / struct_key / write`) is the **single seam**: pick mode (`PickState._candidates`), glyph anchoring (`constraint_paint._ref_geom`), dim kinds (`constraint_dims`), validity (§6.3), `remap_for_copy` and the build (`_build_fresh` / `_resolve`) all read it. Richer instance handles reach every consumer through it with no consumer edits.
- Pure core out, Qt shell in (spec §3): the handle table and expressions live in `sketch_adapters` / `sketch_solver`; the Explode remap rule in `sketch_model`; only the controller and `Model_Space` call them.
- One geometry set: handles come from `block_snap_geometry.posed_primitives` (printed, non-text primitives; nested blocks recursively; text and scaffolding skipped; missing / cyclic nested blocks skipped). Nothing is reimplemented per handle kind.
- File format: `HandleRef.h` stays a string (§6.2); no schema bump; legacy `ins` records unchanged.

## Design Decisions

Ratified at the 2026-10-15 grill (what) and the brainstorm's section approvals (how). Numbered to continue the governing spec's table at Account (D104–).

| # | Decision |
|---|---|
| NB1 (→ D104) | **Pose variables x, y, rotation.** `_NestedAdapter` vars `[x, y, rot]` (rot radians, Y-up CCW; an angle var — D28 weight, D34 stiff, `ANG_WRITE_TOL`). Mirror and scale stay fixed (panel-only); the `edit()` DD8 restore loop keeps restoring those two. Write-back: `set_block_pos` + `set_block_rotation(degrees)` only when the variable moved past tolerance, so an unmoved block keeps its exact degrees. |
| NB2 (→ D105) | **Handle set = snap parity + `ins`.** Every printed, non-text primitive of the definition (any depth) contributes its own adapter's point / edge / curve handles mapped through the instance pose; each nested record contributes its composed origin as a point; the instance's `ins` (= raw x, y) is unchanged. Child text boxes and child reference lines are excluded (as snap). |
| NB3 (→ D105) | **Naming (file format):** `h = "<path>:<handle>"` where `path` = the child primitive's `uid`, prefixed by each enclosing nested record's `uid` joined with `/`: `"<prim uid>:p1"`, `"<rec uid>/<prim uid>:m2"`, a grandchild origin `"<rec uid>:ins"`. Stable across child edits (primitive uids persist, §6.1). Parsing: split on the first `:`; the handle part is the child adapter's own name. |
| NB4 (→ D106) | **Validity is re-checked on every `active()` call for constraints that reference a `block_instance`:** handle membership on the adapter + REGISTRY pattern; a failing record gets `invalid = True` (raw kept, "Unsupported constraint" row, excluded from DOF); a passing one is revived. Loose-only constraints keep the load-time rule. A moved child handle changes geometry only — the parent re-solves at its next solve (known gap: a child edited in another tab leaves the parent visibly unsatisfied until then; follow-up). |
| NB5 (→ D107) | **Explode remaps interior refs.** `explode_instances(..., uid_map=)` records `<rec/prim uid> → new uid` (nested records → the new child instance; under flatten the recursion extends the paths). `sketch_model.remap_exploded(cons, inst_uid, uid_map)` rewrites `{"uid": inst, "h": "A/B:p1"}` to `{"uid": uid_map["A"], "h": "B:p1"}` (strip the first path segment; a fully loose target gets a bare handle). Refs on `ins` or `"item"` (Fix) and unmapped prefixes drop the constraint. `Model_Space` calls `constraint_ctl.on_items_exploded(inst, uid_map)` before `on_items_removed`; the status counts only drops; one undo step. |
| NB6 (→ D108) | **Legacy whole-item Fix migrates:** in `_adopt` (load / undo restore / paste), a `fix` on `{"uid": <block_instance>, "h": "item"}` with a 2-value `helper.v0` gets the instance's current rotation variable appended (radians). Idempotent; saved as 3 values. Other length mismatches keep the CS8 stale guard. |
| NB7 (→ D109) | **Constant-radius curves.** `CurveExpr` gains `r_const: float | None` (with `r: int | None`); `_on_circle`, `build_point_on_curve`, `build_concentric` (and later Tangent / Equal) read whichever is set. A **driving** `dim_radius` / `dim_diameter` on a const curve is refused at add ("Invalid constraint") and invalid on load; a Reference one measures it. |
| NB8 | **Pick mode unchanged (D21):** every nested handle shows its resting marker (midpoints as triangles, hidden child handles — polygon `radius`, ellipse `rx` / `ry` — never). |
| NB9 | **Approach A — composite adapter over stand-ins** (chosen over B "stand-ins as solver items with rigid-link rows" — phantom variables pollute DOF and the D18 drag bar — and C "handle table at definition compile" — couples constraint naming into `block_definition.py`; a later perf migration if measured). |

### Mechanism (Approach A)

```
_NestedAdapter(item)                           sketch_adapters.py
  _table(item) -> LocalHandles                 memo on (render_ops identity, mirrored, scale)
      stand_ins = block_snap_geometry.posed_primitives(defn, (0, 0, 0, mirrored, scale),
                                                       paths=True)   # -> [(path, item)] + nested origins
      for each (path, child): ad = adapter_for(child); x = ad.read(child)
          points[f"{path}:{n}"] = e.eval(x)[0]   for n, e in ad.points(child, 0)   (constants: local u, v)
          edges[f"{path}:{n}"]  = (name_a, name_b)                                  (by posed point)
          curves[f"{path}:{n}"] = (centre u, v; r)                                   (r already × scale)
          mids / hidden re-prefixed
      nested origins: points[f"{path}:ins"] = composed local position
  points(item, off): {"ins": raw_point(off, off+1)} +
      {name: PointExpr(idx=(off, off+1, off+2), fn=_pose_point_fn(u, v), fam=("pose", (u, v)))}
  edges / curves: pairs of those points / CurveExpr(center=posed, r=None, r_const=r)
  struct_key: ("block_instance", 3, id(ops), mirrored, scale)
```

`_pose_point_fn(u, v)` over `(x, y, th)`: `p = (x + u·cosθ + v·sinθ, y − u·sinθ + v·cosθ)` — the rectangle formula (`_rect_point_fn`) with the local offset baked; `dp/dθ = (−u·sinθ + v·cosθ, −u·cosθ − v·sinθ)`. Registered as the batched family `"pose"` (parity-tested against `fn`, like `"rect"`). The identity-rotation stand-ins already carry the origin shift, mirror and scale (`pose_primitive` order T·R·S·M with R = 0), so rotation is the only transform applied in the expression.

`block_snap_geometry.posed_primitives(defn, pose, paths=False)`: with `paths=True` yields `(path, item)` pairs and, for each nested record, `(path, origin_point)` — the one walker serves snap (today's call shape unchanged) and constraints. Snap's "nested insertion point still no snap" gap can later consume the same origins (follow-up).

### Data flow (one edit)

Unchanged from spec §3: the seam snapshots → the caller mutates → `_build` (cache keyed on `struct_key`, which now carries the child definition's compiled-ops identity) → solve → write-back → `_committed`. A child-definition edit recompiles `render_ops` → the handle-table memo and the build cache both miss on the parent's next solve.

## Acceptance Criteria

- [ ] AC1 Coincident between a loose point and a nested arc centre / line end / edge midpoint / grandchild `ins` solves by moving the sub-block (loose geometry least-change).
- [ ] AC2 Parallel between a loose edge and a nested edge solves by rotating the sub-block; a typed panel **Rotation** on a constrained instance is exact or rolled back (D31) with the conflict status.
- [ ] AC3 Handle positions are correct under rotation + mirror + scale (match the snap stand-ins' scene points).
- [ ] AC4 A deleted child primitive makes its parent constraint inert ("Unsupported constraint"), excluded from DOF; undoing the child edit revives it; a moved child primitive re-solves at the parent's next edit.
- [ ] AC5 Explode (this level and flatten) remaps interior refs to the exploded items, drops `ins` / Fix refs, reports only the drops, and undo restores the instance with its original constraints.
- [ ] AC6 Legacy records load and solve: `ins` refs unchanged; a 2-value instance Fix migrates to 3 values and pins position + rotation.
- [ ] AC7 Pick mode offers interior handles (midpoints as triangles; hidden child handles never); the Block Editor DOF count for an instance is 3.
- [ ] AC8 A driving radius / diameter dim on a nested curve is refused; a Reference one measures it; point-on-curve and Concentric to a nested curve solve.
- [ ] Testing expectations: guards 1–7 (Phase 2) + the `"pose"` family parity test, each RED with the change reverted.

## Verification Checklist

- [ ] All acceptance criteria met
- [ ] `tests/test_constraint_nested_handles.py` + `tests/test_sketch_adapters.py` additions pass; the constraint, block-snap and explode test sets stay green (VC5)
- [ ] Full chunked suite green on the final tree (VC6)
- [ ] Block Editor smoke: assemble a two-sub-block symbol, constrain, rotate by Parallel, explode, undo
- [ ] Governing spec amended in place (D5, D104–D109, §5.1, §5.3, §6.2, §7.3, §8, §12) and stamped; block-system.md pointer

---

## Existing Code Context

- `sketch_adapters._InsAdapter` — the replaced adapter (`ins` only, 2 vars).
- `sketch_adapters._rect_point_fn` / `register_point_family("rect", ...)` — the derived-point + batched-family pattern reused.
- `sketch_solver.PointExpr / CurveExpr / ItemExpr`, `_on_circle`, `build_point_on_curve`, `build_concentric`, `build_dim_radius/diameter`, `build_fix`.
- `constraint_controller.active()`, `_valid`, `_adopt`, `_build` (cache key uses `struct_key`), `_resolve`, `on_items_removed`, `edit()` DD8 pose restore, `_typed_pins`.
- `block_snap_geometry.posed_primitives / _walk`; `block_explode.explode_instances / compose_pose / pose_primitive`; `BlockInstance.snap_primitives` (memo idiom), `set_property("Rotation")` (runs inside `PropertyManager`'s `edit(typed=True)`).
- `sketch_model.remap_for_copy` — the sibling of the new `remap_exploded`.
- `Model_Space` explode command (the `on_items_removed` call site after `explode_instances`).

## Edge Cases & Error Handling

- Missing or cyclic nested definition: no stand-ins → no handles (as snap); existing refs go inert (NB4).
- Two child primitives with the same uid (a hand-edited file): the later one wins in the table; not guarded.
- A nested instance whose definition has zero printed primitives exposes only `ins`.
- Explode of a nested-in-nested *this level only*: grandchild refs re-key onto the new child instance with the first segment stripped (`"B:p1"`); flatten resolves to loose items.
- Explode failure restores the network before any remap runs (existing try/except); the remap happens only after a successful explode.
- Fix migration never runs on a point Fix (`h != "item"`) or a non-instance item.

## Performance & Security

- Handle table built once per (ops, mirrored, scale); pick-mode candidate count grows with the sub-block's primitive count (NB8, accepted). No new perf bar; the D18 drag bar tests stay the guard.

## Code Style & Testing

- Google docstrings, relative imports, constants in `constants.py`; new tests follow `tests/test_constraint_e2e.py` (real editor scene, `constraint_ctl` seams) and `tests/_block_snap_helpers.py` fixtures.
