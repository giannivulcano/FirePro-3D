# Arc + Polygon Drawing Decomposition Slice — Design

> **Status:** design (2026-09-05). Implements **Slice 9** of the Model_Space decomposition
> governed by `docs/specs/model-space-architecture.md` (§5/§5.3/§8). This doc is the *how*; the
> *what* is locked by the governing spec + the slice-8 template
> (`2026-09-04-geometry-drawing-slice-design.md`) — not relitigated. On landing,
> `model-space-architecture.md` §5/§6 is stamped in place — no parallel governing spec.
> Behavior is owned by `docs/specs/2d-geometry.md` and the dynamic-input /
> `inferred-dimension-driven-placement.md §4` spec (Rule A — not restated here).

## 0. Locked scope (from the governing spec + slice-8 precedent — not relitigated)

- **Pure behavior-preserving relocation.** Zero behavior change, zero bug fixes.
- **Into the EXISTING controller.** Move concern #6's **Arc** (3-step centre→radius/start→span) and
  **Polygon** (3-step centre→radius→rotate, with ↑/↓ sides + ←/→ inscribed/circumscribed) drawing
  *methods* from `model_space.py` into the already-landed `GeometryDrawingController(scene)`
  (`firepro3d/geometry_drawing_controller.py`). No new module, no new collaborator.
- **BEHAVIOR HOME — all drawing STATE stays scene-side (§5.3).** Mirrors slice 8: the controller owns
  the *methods*, not the state. Every arc/polygon transient + persisted attr stays on the scene, read/
  written via `self._scene.*`. Forcing reasons: (a) `_draw_arc_step` and the arc/polygon variant flags
  are **explicitly named in the slice-7 conclusion (§5.3)** as staying scene-side (read by
  `PlacementInputCoordinator`); (b) the persisted lists `_draw_arcs`/`_draw_polygons` participate in
  BOTH serializers + undo-restore (§3.3 dual-serialization INVARIANT) and are read by external
  consumers. Moving them would churn freshly-landed slice-7 code — against the lowest-risk mandate.
- **Schema + seed/coupling are ALREADY coordinator-owned (slice 7) — OUT OF SCOPE, untouched.**
  `_arc_schema_for_step`, `_polygon_schema_for_step`, `_arm_arc_coupling` are already thin scene-side
  shells → `self._plc.*` (verified: `model_space.py:2652/2656/2811`). Arc/polygon **variant cycling**
  (`_PLACEMENT_VARIANTS` lambdas that `setattr(s, "_arc_variant", …)`) lives in the coordinator
  (`placement_input_coordinator.py:43-50`) — untouched.
- **Generic helpers STAY scene-side** (shared across concerns), reached via `self._scene.*`:
  `_make_ref_line`, `_make_ref_circle`, `_geom_color_lw`, `_constrain_angle`, `_get_geometry_template`,
  `update_preview_node`. (Slice 8 already left these scene-side; slice 9 confirms — arc + polygon are
  exactly the "stay, Slice 9" consumers slice-8 §0 anticipated.)
- **Dual-concern helper STAYS scene-side:** `_inset_polygon` (a `@staticmethod` at
  `model_space.py:5306`, called at `:5276` from the **offset / scene-tools** path, **not** the polygon
  *drawing* tool) is NOT moved. It belongs to the edit-tools concern.
- **Repoint nothing (dispatch/coordinator/keyPress/external stay working via scene-side shells).**
  `_PRESS_DISPATCH`/`_MOVE_DISPATCH`/`_PREVIEW_DISPATCH`/`_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` stay
  **class-level on `Model_Space`, untouched**; the coordinator keeps dispatching appliers via
  `getattr(self._scene, applier_name)`.
- **Arc-variant constant — cycle-free via lazy import (precedented).** `_commit_draw_arc_rim_at` reads
  `self._scene._arc_variant == _ARC_VARIANT_START`. The controller cannot import from `model_space`
  (cycle), so it **lazy-imports inside the method** — `from firepro3d.model_space import
  _ARC_VARIANT_START` — mirroring `placement_input_coordinator.py:43` verbatim (the sibling collaborator
  landed in slice 7 does exactly this). No constant is moved; no other reference changes.
- **Plain object, not `QObject`.** (Already true — extending the existing controller.) Signals via
  `self._scene.<sig>.emit`.
- **Zero serialization surface (confirmed).** No state moves off the scene → `.fpd` byte-identical +
  undo bytes unchanged are **trivially** met; the gate is **live parity + manual smoke** (pure
  interaction plumbing — the live-only bug class).
- **Deferred / explicitly out:** the `text` and `dimension` `set_mode` branches (different concerns —
  stay inline); `_inset_polygon` (edit-tools); any behavior change; the per-element
  `*PlacementController`s (wall/floor/roof/opening/room/gridline — later slices).

## 1. Goal

Lift concern #6's Arc + Polygon drawing behavior out of `model_space.py` into the existing
`GeometryDrawingController`, behavior-preservingly — completing concern #6's simple-geometry drawing
relocation begun in slice 8. Gives arc/polygon algorithms the same named, isolation-testable home and
further shrinks the god-object's method surface, while all drawing STATE stays scene-side as the
contract between the drawing behavior (`_geom_ctl`) and the placement-input coordinator (`_plc`).

## 2. Architecture

### 2.1 Collaborator (existing)

- **Module/Class:** `firepro3d/geometry_drawing_controller.py` — `GeometryDrawingController` (plain
  object, behavior home). No constructor/`__init__` change (already built at `Model_Space.__init__`).
- Add imports: `QGraphicsLineItem`, `QGraphicsPathItem` (Qt widgets); `QPainterPath` (QtGui);
  `ArcItem`, `RegularPolygonItem` (from `.construction_geometry`). `math`/`QPointF`/`QRectF`/pens are
  already imported.

### 2.2 State — NONE owned by the controller (behavior-home, §5.3)

All stays on the scene, referenced via `self._scene`:

- **Persisted lists:** `_draw_arcs`, `_draw_polygons` (BOTH serializers + undo + external readers).
- **Arc transient:** `_draw_arc_center`, `_draw_arc_radius`, `_draw_arc_start_deg`, `_draw_arc_step`,
  `_draw_arc_radius_line`, `_draw_arc_preview`, `_draw_arc_ref_line0`, `_draw_arc_ref_start`,
  `_draw_arc_ref_sweep`, and the variant flag `_arc_variant` (written by the coordinator's variant
  lambdas — §5.3, stays scene-side).
- **Polygon transient:** `_polygon_center`, `_polygon_rotating`, `_polygon_sized_radius`,
  `_polygon_preview`, `_polygon_ref_circle`, `_polygon_ref_lineA`, `_polygon_sides`,
  `_polygon_inscribed`.
- **Shared plumbing / generic helpers / render scratch:** `preview_pipe`, `preview_node`,
  `update_preview_node`, `_last_scene_pos`, `_active_view_scale`, `mode`, `get_effective_position`,
  `scale_manager`, `push_undo_state`, `_show_status`, `publish_placement_state`/`clear_placement_state`,
  `instructionChanged`, `_make_ref_line`, `_make_ref_circle`, `_geom_color_lw`, `_constrain_angle`,
  `_get_geometry_template` — all reached via `self._scene.*`.

### 2.3 Methods moved into the controller (bodies operate on `self._scene.*`)

**Arc (11):** `_press_draw_arc`, `_move_draw_arc`, `_preview_from_arc`, `_advance_arc_to_span_step`,
`_commit_draw_arc_rim_at`, `_arc_end_point_for_span`, `_apply_arc_dynamic_input`, `_commit_draw_arc_at`,
`_set_arc_ref_lines`, `_update_arc_sweep_ref`, `_clear_arc_ref_lines`.

**Polygon (15):** `_press_polygon`, `_move_polygon`, `_preview_from_polygon`, `_preview_polygon_rotation`,
`_advance_polygon_to_rotate_step`, `_apply_polygon_dynamic_input`, `_commit_polygon_rotated`,
`_commit_polygon_at`, `_build_polygon_ghost`, `_polygon_rotation_angle_to`, `_polygon_readout`,
`_cycle_polygon_sides`, `_toggle_polygon_inscribed`, `_clear_polygon_ref_items`.
*(Plus the arc/polygon teardown into `clear()`, §2.5.)*

**Body rewrites (mechanical, mirroring slice 8):** `self.<sceneOp>` (`addItem`/`removeItem`/`views`/
`update_preview_node`/`clearSelection`) → `self._scene.<sceneOp>`; each state attr in §2.2 →
`self._scene.<same>`; `self.get_effective_position`/`_active_view_scale`/`_last_scene_pos` →
`self._scene.<same>`; generic helpers (`_make_ref_line`, `_make_ref_circle`, `_geom_color_lw`,
`_constrain_angle`, `_get_geometry_template`) → `self._scene.<same>`; `self.<signal>.emit` →
`self._scene.<signal>.emit`; `self._show_status`/`push_undo_state`/`publish_placement_state`/
`clear_placement_state` → `self._scene.<same>`. **Internal calls to still-moving siblings stay
`self.<method>`** (e.g. `_move_draw_arc` → `self._preview_from_arc`/`self._update_arc_sweep_ref`;
`_press_polygon` → `self._commit_polygon_rotated`/`self._advance_polygon_to_rotate_step`;
`_commit_draw_arc_rim_at` → `self._advance_arc_to_span_step`; `_cycle_polygon_sides` →
`self._preview_polygon_rotation`/`self._preview_from_polygon`/`self._polygon_readout`).

### 2.4 Delegation contract — scene-side shells vs bare move

**Scene-side shells REQUIRED** (referenced by a dispatch table, the coordinator's applier dispatch,
`keyPressEvent`, or external/tests — the implementer greps each; the callers below are the known ones):

- **Dispatch-resolved (press/move/preview):** `_press_draw_arc`, `_move_draw_arc`, `_preview_from_arc`,
  `_press_polygon`, `_move_polygon`, `_preview_from_polygon`.
- **Applier-resolved** (`getattr(self._scene, _APPLIER_FOR_MODE[mode])`): `_apply_arc_dynamic_input`,
  `_apply_polygon_dynamic_input`.
- **keyPress-called** (`model_space.py:7781-7785`): `_cycle_polygon_sides`, `_toggle_polygon_inscribed`.
- **External/instruction-line callers:** `_polygon_readout` (called at `:1384`, outside the polygon
  block — needs a shell); `_commit_polygon_at` (its docstring documents pre-3-step external/test callers
  — shell to be safe, confirm via grep).

**Move WITHOUT a shell** unless a caller-grep finds an external reference (internal-only siblings):
`_advance_arc_to_span_step`, `_commit_draw_arc_rim_at`, `_arc_end_point_for_span`, `_commit_draw_arc_at`,
`_set_arc_ref_lines`, `_update_arc_sweep_ref`, `_clear_arc_ref_lines`, `_polygon_rotation_angle_to`,
`_advance_polygon_to_rotate_step`, `_commit_polygon_rotated`, `_build_polygon_ghost`,
`_preview_polygon_rotation`, `_clear_polygon_ref_items`. **The implementer greps every one** (the
established shell-vs-bare rule) — several of these are plausibly hit by `test_regular_polygon*.py` /
`test_arc*.py` white-box tests, which would require a shell (or a repointed test assert, matching the
slice-6 `test_design_area.py` precedent). **Static-call trap:** if any relocated helper is called
statically (`Model_Space._x(...)`), it needs a `@staticmethod` shell
(`feedback_static_method_relocation_shell`).

### 2.5 Dispatch, mode & `clear()` (unchanged behavior)

- **Dispatch tables + `_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` untouched** (class-level on `Model_Space`).
  Resolution flows `getattr(self, handler)` → scene shell → controller (mouse) and
  `getattr(self._scene, applier_name)` → scene shell → controller (HUD).
- **`clear(new_mode)` gains the arc + polygon teardown.** The existing
  `GeometryDrawingController.clear(new_mode)` (currently line/rect/circle/polyline) absorbs the two
  `set_mode` branches at `model_space.py:1053-1075`, **verbatim** (preserving the exact
  `if new_mode != "polygon"` / `if new_mode != "draw_arc"` guards so staying in a mode mid-placement
  preserves that primitive's state), operating on scene-side state via `self._scene.*` and calling
  `self._clear_polygon_ref_items()` / `self._clear_arc_ref_lines()` (now controller methods).
- **`set_mode` change:** delete lines `1053-1075` (the polygon + arc branches). The single
  `self._geom_ctl.clear(mode)` call already at `:1052` now also tears down arc/polygon. **The `text`
  branch (`:1076-1081`) and `dimension` branch (`:1082+`) stay inline** (different concerns).

## 3. Data flow (unchanged, relocated)

- **Mouse placement:** `mousePressEvent`/`mouseMoveEvent` (core) resolve the snapped point via
  `get_effective_position` (core), then `getattr(self, handler)(...)` → scene shell → controller press/
  move handler, which reads/writes scene-side transient state + shared `preview_*`, and on commit builds
  the `ArcItem`/`RegularPolygonItem`, appends to the scene-side list, then `self._scene.push_undo_state()`.
- **HUD typed commit:** HUD Enter → `scene._on_dynamic_input_committed` (coordinator) →
  `getattr(self._scene, _APPLIER_FOR_MODE[mode])(geometry)` → scene applier shell →
  `_apply_arc_dynamic_input` / `_apply_polygon_dynamic_input` (step-aware) → controller commit; returns
  bool (D2 refusal gating unchanged). Arc step-2 span dict → `_arc_end_point_for_span`; polygon rotate
  dict → `_commit_polygon_rotated`.
- **Schema / seed / variant (coordinator, unchanged):** `active_schema` → `_arc_schema_for_step` /
  `_polygon_schema_for_step` (already coordinator shells); the variant lambdas write
  `self._scene._arc_variant` — **not touched by this slice**.
- **↑/↓/←/→ live edits:** `keyPressEvent` (core) → scene shells `_cycle_polygon_sides` /
  `_toggle_polygon_inscribed` → controller, which rereads `_last_scene_pos` and rebuilds the ghost.
- **Teardown:** `set_mode` → `self._geom_ctl.clear(mode)` covers line/rect/circle/polyline **+ arc +
  polygon**; text/dimension inline; `.fpd`/undo untouched (no serialization surface).

## 4. Testing

**Existing coverage is the parity net (must stay green = behavior preserved).** Run/keep green (exact
files confirmed by the implementer via grep): `test_regular_polygon*.py`, `test_arc*.py`,
`test_geometry2d_mixin.py`, `test_geo2d_serialization.py`, `test_geo2d_placement_defaults.py`,
`test_dynamic_input_parity.py`, `test_placement_variants.py`, and the slice-8 parity file
`test_geometry_drawing_slice_parity.py`. **Static-call trap trio** (`test_append_geom_to_path.py` /
`test_pdf_text_render.py` / `test_import_dialog_preview.py`) — re-run to catch any statically-called
relocated helper. **All `test_gridline_*.py`** stay green (gridline concern untouched — arc/polygon
don't touch it, but the shared `clear()` does).

**Extend the slice-8 parity file `tests/test_geometry_drawing_slice_parity.py`** (or add
`tests/test_arc_polygon_slice_parity.py` mirroring it):

- `test_backcompat_shells_arc_polygon` — the moved public/dispatch/applier/keyPress shells
  (`_press_draw_arc`, `_apply_arc_dynamic_input`, `_commit_draw_arc_at`, `_press_polygon`,
  `_apply_polygon_dynamic_input`, `_cycle_polygon_sides`, `_toggle_polygon_inscribed`,
  `_polygon_readout`, …) are callable on the scene and delegate to `_geom_ctl`.
- `test_arc_draw_live` — posted `QMouseEvent`/`QKeyEvent` on a **shown+activated** view (real entry
  point; `QTest.mouseMove` is inert — post real events): Arc 3-click (centre → start → end) in the
  default centre-first variant; assert the committed `ArcItem` centre/radius/start°/span match the mouse
  path and it lands in `_draw_arcs`.
- `test_polygon_draw_live` — Polygon 3-click (centre → radius → rotate) incl. ↑/↓ sides and ←/→
  inscribed toggle mid-placement + Ctrl-rotate; assert the `RegularPolygonItem`
  sides/radius/rotation/inscribed match and it lands in `_draw_polygons`.
- `test_hud_typed_commit_live` — Arc: type radius+start° at step 1, span at step 2; Polygon: type radius
  at sizing, angle at rotate; assert geometry equivalent to the mouse path (applier path through the
  coordinator → scene shell → controller).
- **`clear()` RED-demo** — extend the existing RED-demo: leaving `draw_arc` / `polygon` mid-placement
  (mid-step) with `clear()`'s new arc/polygon block stubbed to no-op leaves a stale
  preview/ref-line/anchor → RED; restored → green.

A pure relocation has no other red→green; parity tests are green before and after by design.

**Subagent implementers run only the targeted test files.** Full-suite green — read by **FAILED-diff vs
`main`** (`-v --tb=no`), not pass-count (`project_model_space_fullsuite_gate_native_crash`) — is a
Phase-6 orchestrator gate; no new failures beyond the documented pre-existing loci (the L72 trio, the
`main` failures at L281/L48, the QPrinter-SEH + underlay-worker native-crash loci). Arc/polygon are live
interaction → **manual smoke test by the user** before wrap-up, with the exact `cd` + venv command and
the branch name stated (wrong-code-smoke-test hazard).

## 5. Slicing (revertable sub-commits, parity green at each step)

Branch: `refactor/model-space-arc-polygon-slice`.

0. **C0 — Design doc + characterization/RED-demo test scaffolding** land on the branch, green.
1. **C1 — Arc.** Move the 11 arc methods + scene shells (dispatch/applier: `_press_draw_arc`,
   `_move_draw_arc`, `_preview_from_arc`, `_apply_arc_dynamic_input`; internal per grep). Lazy-import
   `_ARC_VARIANT_START` inside `_commit_draw_arc_rim_at`. Targeted tests green.
2. **C2 — Polygon.** Move the 15 polygon methods + scene shells (dispatch/applier/keyPress/instruction:
   `_press_polygon`, `_move_polygon`, `_preview_from_polygon`, `_apply_polygon_dynamic_input`,
   `_cycle_polygon_sides`, `_toggle_polygon_inscribed`, `_polygon_readout`, `_commit_polygon_at`;
   internal per grep). Targeted tests green.
3. **C3 — `clear()` + `set_mode` wiring + RED-demo.** Move the `set_mode` polygon+arc teardown branches
   (`:1053-1075`) into `GeometryDrawingController.clear(new_mode)` verbatim; delete them from `set_mode`
   (the `:1052` `clear(mode)` call now covers them); text/dimension branches stay inline.
4. **C4 — Verify** targeted set; back-compat guard; full suite (Phase-6 FAILED-diff gate); **manual smoke**.
5. **C5 — Spec stamp.** Update `model-space-architecture.md` §5 (mark Arc+Polygon landed in
   `GeometryDrawingController`; concern #6 simple-geometry drawing now complete) + add the slice-9 bullet
   to §6; `last-verified`/`verified-commit`; `applies-to` already lists the module. `SPEC-INDEX.md`
   unchanged (no boundary moved). Note the next concern-#6/#7 sub-slice (arch-placement:
   per-element `*PlacementController`s, wall first).

## 6. Acceptance criteria (relocation tier, from `model-space-architecture.md` §8)

- [ ] `.fpd` byte-parity + undo bytes unchanged — trivially met (zero serialization surface); asserted by
      a round-trip smoke check on a real `.fpd` with arc + polygon geometry.
- [ ] Arc (3-click, both variants) / Polygon (3-click incl. ↑/↓ sides, ←/→ inscribed, Ctrl-rotate) drive
      correctly via **posted events on a shown view**, both mouse and HUD-typed; results equivalent to `main`.
- [ ] `set_mode` arc+polygon teardown travels as part of the single idempotent
      `GeometryDrawingController.clear(new_mode)`; text/dimension branches stay inline unchanged.
- [ ] Dispatch tables + `_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` untouched; coordinator applier/schema/variant
      paths unchanged; the coordinator's reads of scene-side drawing state unchanged.
- [ ] Back-compat intact: scene shells keep dispatch/coordinator/keyPress/`main.py`/tests working; any
      statically-called relocated helper has a `@staticmethod` shell; `_inset_polygon` stays scene-side.
- [ ] Persisted lists (`_draw_arcs`/`_draw_polygons`) + all arc/polygon transient state remain scene
      attributes (behavior-home model).
- [ ] Full suite green (chunked); no new failures beyond the documented pre-existing loci (FAILED-diff vs `main`).
- [ ] `model-space-architecture.md` §5/§6 re-audited + stamped.

## 7. Governed-behavior cross-refs (Rule A — do not restate)

Behavior is owned by `docs/specs/2d-geometry.md` (arc/polygon placement, fill, level/plane semantics) and
the dynamic-input / `inferred-dimension-driven-placement.md §4` spec (HUD lifecycle, step-aware schemas,
seed/publish/resolve, variant cycling). This slice is structural only; it moves code without changing any
behavior those specs govern.
