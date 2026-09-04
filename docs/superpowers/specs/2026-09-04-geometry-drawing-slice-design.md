# 2D-Geometry Drawing Decomposition Slice — Design

> **Status:** design (2026-09-04). Implements **Slice 8** of the Model_Space decomposition
> governed by `docs/specs/model-space-architecture.md` (§5/§8). This doc is the *how*; the
> *what* was locked in a grill (see §0). On landing, `model-space-architecture.md` §5/§6 is
> stamped in place — no parallel governing spec is created. Behavior is owned by
> `docs/specs/2d-geometry.md` and the dynamic-input / `inferred-dimension-driven-placement.md §4`
> spec (Rule A — not restated here).

## 0. Locked scope (from grill 2026-09-03/04 — not relitigated here)

- **Pure behavior-preserving relocation.** Zero behavior change, zero bug fixes.
- **One collaborator, seeded scope.** Extract concern #6's **simple 2D-drawing primitives** — Line,
  Rectangle (3-step size→rotate), Circle, Polyline — into `GeometryDrawingController(scene)`.
  **Arc + Polygon are deferred to Slice 9** (into the same controller).
- **Persisted geometry lists STAY scene-side (Q1, evidence-settled).** `_draw_lines`, `_draw_rects`,
  `_draw_circles`, `_polylines` participate in BOTH serializers (`scene_io.save_to_file` +
  `_capture_network`) and undo-restore (the §3.3 dual-serialization INVARIANT), and are read bare by 4+
  external consumers via `getattr(self._scene, "_draw_lines", [])` (`view_3d.py` L797/806/821/850,
  `level_manager.py`, `level_widget.py`, `display_manager.py`). They stay on the scene; the controller
  appends/reads via `self._scene.*`.
- **`draw_gridline` is OUT OF SCOPE (Q2, concern #7).** The `draw_line`/`draw_gridline` modes share the
  press/move/preview/commit handlers today; the commit factory `_make_line_like` branches on
  `self.mode == "draw_gridline"` and builds a `GridlineItem` (pulling in `_gridlines`,
  `_register_gridline`, `sync_grid_counters`, `apply_duplicate_warnings`, the gridline template). **The
  line drawing control-flow/preview moves to the controller; the dual-concern factory `_make_line_like`
  STAYS scene-side** so the gridline concern is byte-for-byte untouched for its own future slice. The
  controller's line commit calls `self._scene._make_line_like(anchor, tip)`.
- **KEY DECISION — the controller is a BEHAVIOR HOME; transient drawing STATE stays scene-side.**
  Unlike the pipe/sprinkler/underlay controllers (which own their state), `GeometryDrawingController`
  relocates the drawing *methods* but leaves the transient drawing state on the scene, read/written via
  `self._scene`. **Why:** the already-extracted `PlacementInputCoordinator` (slice 7) reads essentially
  all of it — `_mode_placement_anchor` (`placement_input_coordinator.py` L569–594) reads
  `_draw_line_anchor`/`_draw_rect_anchor`/`_draw_rect_rotating`/`_draw_rect_pivot`/`_draw_circle_center`;
  `_at_placement_step_zero` (L92) reads `_draw_rect_anchor`/`_draw_rect_rotating`; `_transform_seed_values`
  (L705–710) reads `_draw_rect_rotating`/sized/pivot; the variant lambdas (L54/56) write
  `_draw_rect_from_center`; `_polyline_active` is read at L631. Moving that state into `_geom_ctl` would
  force ~8 controller→controller reach-ins and rewrite freshly-landed Slice-7 code — the opposite of
  "lowest-risk behavior-preserving." One clean rule: **all geometry drawing state (transient + persisted)
  stays on the scene as the shared contract between the drawing behavior (now `_geom_ctl`) and the
  placement-input coordinator (`_plc`); the coordinator's reads are UNCHANGED (`self._scene._draw_*`).**
  This mirrors Slice 2 (`SceneTools` operates on scene state via `self._scene`) and Slice 7 (geometry
  stage-state deliberately left scene-side).
- **Repoint nothing (Q3).** Moved handlers/appliers keep thin **scene-side shells** of the same name;
  `_PRESS_DISPATCH`/`_MOVE_DISPATCH`/`_PREVIEW_DISPATCH`/`_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` stay
  **class-level on `Model_Space`, untouched**; the coordinator keeps dispatching appliers via
  `getattr(self._scene, applier_name)`. Miss-one-and-the-HUD-freezes risk
  (`project_transform_seed_hud_per_mode`) is why the whole triad + applier keep shells.
- **Generic ref-guide + colour helpers STAY scene-side.** `_make_ref_line` and `_make_ref_circle` are
  shared across 5 primitives spanning 3 concerns — rect (moving) **plus** arc + polygon (stay, Slice 9)
  **plus** wall + floor rect (stay, concern #7) at L4866/6271/6682/6955. `_geom_color_lw`, `_constrain_angle`,
  `update_preview_node`, and the coordinator's `_get_geometry_template` also stay; only the rect-*specific*
  `_update_rect_ref_lines`/`_clear_rect_ref_lines` move with rectangle. The controller reaches the generic
  helpers via `self._scene.*`.
- **Plain object, not `QObject`.** Mirrors `PipeNetworkController`/`SprinklerWorkflowController`/
  `PlacementInputCoordinator`. Signals stay on the scene, emitted via `self._scene.<sig>.emit`.
- **Shared placement plumbing stays scene-side:** `preview_pipe`, `preview_node`, `_last_scene_pos`,
  `_snap_result`, `_snap_engine`, `mode`, `get_effective_position`, `active_level`, `scale_manager`,
  `push_undo_state`, `_show_status`, `clear_placement_state`/`publish_placement_state`, `_draw_dim_hint`
  (render scratch read by `drawForeground`; written by the controller via `self._scene`).
- **Zero serialization surface (confirmed).** No state moves off the scene, so `.fpd` byte-identical and
  undo bytes unchanged are **trivially** met; the gate is **live parity + manual smoke** (pure interaction
  plumbing — the live-only bug class).
- **Deferred / explicitly out:** Arc + Polygon (Slice 9); `draw_gridline` + all gridline machinery
  (concern #7); the `_make_line_like` gridline branch; the edit/modify tools (already `SceneTools`);
  any behavior change.

## 1. Goal

Lift concern #6's simple-primitive drawing behavior out of `model_space.py` into a scene-referencing
collaborator `GeometryDrawingController(scene)`, behavior-preservingly. This gives the Line/Rectangle/
Circle/Polyline drawing algorithms a named, isolation-testable home and shrinks the god-object's method
surface, while the shared drawing STATE stays scene-side as the contract between the drawing behavior and
the placement-input coordinator.

## 2. Architecture

### 2.1 New collaborator

- **Module:** `firepro3d/geometry_drawing_controller.py`
- **Class:** `GeometryDrawingController` — a **plain object**. Owns no persisted or transient drawing
  state (per §0 KEY DECISION); holds only `self._scene` (back-ref for scene-graph mutation, signal
  emission, and all state reads/writes) and, optionally, nothing else. Constructed in
  `Model_Space.__init__` immediately after `self._plc` (~L170–173):
  `self._geom_ctl = GeometryDrawingController(self)`.

### 2.2 State — NONE owned by the controller

All geometry drawing state stays on the scene (per §0 KEY DECISION), referenced via `self._scene`:

- **Persisted lists:** `_draw_lines`, `_draw_rects`, `_draw_circles`, `_polylines`.
- **Line transient:** `_draw_line_anchor`.
- **Rectangle transient:** `_draw_rect_anchor`, `_draw_rect_from_center`, `_draw_rect_preview`,
  `_draw_rect_rotating`, `_draw_rect_sized_pt1`, `_draw_rect_sized_pt2`, `_draw_rect_pivot`,
  `_draw_rect_ref_line0`, `_draw_rect_ref_lineA`.
- **Circle transient:** `_draw_circle_center`, `_draw_circle_preview`.
- **Polyline transient:** `_polyline_active`, `_polyline_close_indicator`.
- **Shared plumbing / generic helpers / render scratch:** as listed in §0.

### 2.3 Delegation contract (on `Model_Space`)

- **Scene-side shells** — each `return self._geom_ctl.<same>(...)` — kept for every moved method that is
  referenced by (a) a dispatch table (`getattr(self, handler)` in `mousePressEvent`/`mouseMoveEvent`/
  preview), (b) the coordinator's applier dispatch (`getattr(self._scene, applier_name)`), or (c)
  `main.py`/`model_view.py`/tests. The `draw_gridline` dispatch entries resolve to the **line shells**
  (`_press_draw_line`/`_move_draw_line`/`_preview_from_line`/`_commit_draw_line_at`), which forward to the
  controller; the controller branches on `self._scene.mode == "draw_gridline"` and delegates item
  creation to `self._scene._make_line_like(...)` (STAYS scene-side).
- **Internal-only methods** (called solely by other moved methods, with no dispatch/coordinator/external
  caller) move **without** a shell. The implementer greps each method's callers to decide shell-vs-bare
  (the established rule).

### 2.4 Methods moved into the controller (behavior; bodies operate on `self._scene.*`)

**Line:** `_press_draw_line`, `_move_draw_line`, `_preview_from_line`, `_commit_draw_line_at`
(commit calls `self._scene._make_line_like` — the gridline-aware factory stays scene-side).
**Rectangle:** `_press_draw_rectangle`, `_move_draw_rectangle`, `_preview_from_rectangle`,
`_preview_rectangle_rotation`, `_rect_sizing_points`, `_rect_rotation_angle_to`,
`_advance_rectangle_to_rotate_step`, `_apply_rectangle_dynamic_input`, `_apply_rectangle_rotation`,
`_commit_rectangle_rotated`, `_update_rect_ref_lines`, `_clear_rect_ref_lines` (calls
`self._scene._make_ref_line` — generic factory stays scene-side).
**Circle:** `_press_draw_circle`, `_move_draw_circle`, `_preview_from_circle`, `_commit_draw_circle_at`.
**Polyline:** `_press_polyline`, `_move_polyline`, `_preview_from_polyline`, `_commit_polyline_at`, plus
the polyline-close-indicator helpers (`_show_polyline_close_indicator`/`_update_...`/
`_hide_polyline_close_indicator`) and `_delete_or_pop_polyline_vertex` (whichever are drawing-only per
caller grep).

**Body rewrites (mechanical, mirroring prior slices):** `self.<sceneOp>` (`addItem`/`removeItem`/`views`/
`update`/`clearSelection`/`update_preview_node`) → `self._scene.<sceneOp>`; each geometry state attr
(persisted lists + all transient attrs in §2.2) → `self._scene.<same>`; `self.get_effective_position` →
`self._scene.get_effective_position`; the generic helpers (`_make_ref_line`, `_make_ref_circle`,
`_geom_color_lw`, `_constrain_angle`, `_make_line_like`, `_get_geometry_template`) →
`self._scene.<same>`; `self.<signal>.emit` → `self._scene.<signal>.emit`; `self._show_status` →
`self._scene._show_status`; `self.push_undo_state()` → `self._scene.push_undo_state()`;
`self.clear_placement_state()`/`publish_placement_state(...)` → `self._scene.<same>`;
`self._draw_dim_hint = …` → `self._scene._draw_dim_hint = …`. Internal calls to still-moving siblings
stay `self.<method>`.

### 2.5 Dispatch, mode & `clear()` (unchanged behavior)

- **Dispatch tables untouched** (class-level on `Model_Space`). `mousePressEvent`/`mouseMoveEvent`/preview
  resolve `getattr(self, handler)` → the scene shell → the controller. The coordinator's `apply_dynamic_input`
  resolves `getattr(self._scene, applier_name)` → the scene shell → the controller.
- **One idempotent `clear(new_mode)`** (the §3.4 hook): `GeometryDrawingController.clear(new_mode)`
  absorbs the line/rect/circle/polyline teardown branches from `set_mode` (currently L1035–1064),
  preserving the exact per-primitive `if new_mode != "<mode>": …` guards (so staying in a mode mid-
  placement still preserves that primitive's state). It operates on scene-side state via `self._scene.*`.
  `set_mode` replaces L1035–1064 with a single `self._geom_ctl.clear(mode)` call (positioned exactly where
  those branches are today, after the pipe/sprinkler `clear()` calls).
- **Stays inline in `set_mode` (NOT moved):** the polygon branch (L1065–1073), the arc branch
  (L1074–1087), and the text branch (L1088+) — polygon/arc are Slice 9; text is a different concern.
  The `_hide_polyline_close_indicator()` call at L1044 moves into `clear()` with the polyline branch.

## 3. Data flow (unchanged, relocated)

- **Mouse placement:** `mousePressEvent`/`mouseMoveEvent` (core) resolve the snapped point via
  `get_effective_position` (core), then `getattr(self, handler)(...)` → scene shell → controller press/
  move handler, which reads/writes scene-side transient state and shared `preview_pipe`/`preview_node`,
  and on commit calls `self._scene._make_line_like`/builds the item and appends to the scene-side list,
  then `self._scene.push_undo_state()`.
- **HUD typed commit:** the HUD's Enter → `scene._on_dynamic_input_committed` (coordinator) resolves typed
  values → `getattr(self._scene, _APPLIER_FOR_MODE[mode])(geometry)` → scene applier shell → controller
  applier/commit; returns bool (D2 refusal gating unchanged).
- **Schema / anchor / seed (coordinator, unchanged):** `active_schema`/`_mode_placement_anchor`/
  `_at_placement_step_zero`/`_transform_seed_values` continue reading the scene-side drawing state via
  `self._scene._draw_*` — **not touched by this slice**.
- **`draw_gridline` (untouched behavior):** dispatch → line shells → controller line handlers → on commit
  `self._scene._make_line_like` takes the `mode == "draw_gridline"` branch and builds the `GridlineItem`
  exactly as today (gridline machinery scene-side, unchanged).
- **Teardown:** `set_mode` → `self._geom_ctl.clear(mode)` for line/rect/circle/polyline; polygon/arc/text
  branches inline; `.fpd`/undo untouched (no serialization surface).

## 4. Testing

**Existing coverage is the parity net (must stay green = behavior preserved).** Run/keep green:
`test_geometry2d_mixin.py`, `test_geo2d_serialization.py`, `test_geo2d_placement_defaults.py`,
`test_rectangle_rotation.py`, `test_rectangle_bake.py`, `test_polyline_close_placement.py`,
`test_polyline_closed.py`, `test_draw_fill.py`, `test_geo2d_{context_menu,contextual_tab,display_category,
level_manager,panel,paper,fill_render,fill_opacity}.py`. **Static-call trap trio** —
`test_append_geom_to_path.py` / `test_pdf_text_render.py` / `test_import_dialog_preview.py` call
`Model_Space._append_geom_to_path` **statically**; if any relocated helper is called statically it needs a
`@staticmethod` shell (`feedback_static_method_relocation_shell`). **All `test_gridline_*.py`** as the
regression check that the deferred gridline concern is byte-for-byte untouched.

**Add ONE new file `tests/test_geometry_drawing_slice_parity.py`:**

- `test_backcompat_shells` — the moved public/dispatch/applier shells (`_press_draw_line`,
  `_commit_draw_line_at`, `_press_draw_rectangle`, `_apply_rectangle_dynamic_input`, `_press_draw_circle`,
  `_commit_draw_circle_at`, `_press_polyline`, `_commit_polyline_at`, …) are callable on the scene and
  delegate to `_geom_ctl`.
- `test_draw_live` — posted `QMouseEvent`/`QKeyEvent` on a **shown+activated** view (real entry point, not
  handler calls; `QTest.mouseMove` is inert here — post real events): Line 2-click; Rectangle 3-step incl.
  Ctrl-rotate; Circle 2-click; Polyline multi-click + Enter-finalize + close-on-start. Assert committed
  geometry matches the mouse path and lands in the scene-side list.
- `test_hud_typed_commit_live` — for each of the 4 primitives, open the HUD, type an exact value, commit;
  assert geometry equivalent to the mouse path (the applier path through the coordinator → scene shell →
  controller).
- `test_gridline_still_scene_side` — drawing a `draw_gridline` line still builds a `GridlineItem` via the
  scene-side `_make_line_like` (gridline untouched).
- **`clear()` RED-demo** — stub `GeometryDrawingController.clear()` to a no-op and confirm a "leave a draw
  mode mid-placement → stale anchor/preview" test goes RED; restore → green.

A pure relocation has no other red→green; parity tests are green before and after by design.

**Subagent implementers run only the targeted test files.** Full-suite green — read by **FAILED-diff vs
`main`** (`-v --tb=no`), not pass-count, per `project_model_space_fullsuite_gate_native_crash` — is a
Phase-6 orchestrator gate; no new failures beyond the documented pre-existing loci (the L72 trio, the
newly-catalogued `main` failures at L281/L48, the QPrinter-SEH and underlay-worker native-crash loci).
The drawing tools are live interaction → **manual smoke test by the user** before wrap-up, with the exact
`cd` + venv command and the branch name stated (per the wrong-code-smoke-test hazard).

## 5. Slicing (revertable sub-commits, parity green at each step)

Branch: `refactor/model-space-geometry-drawing-slice`.

0. **C0 — Characterization + RED-demo tests** land on the branch, green (safety net).
1. **C1 — Scaffold.** New `geometry_drawing_controller.py` (`GeometryDrawingController(scene)`, `_scene`
   back-ref, empty `clear(new_mode)`); `__init__` builds `self._geom_ctl` at ~L173. No bodies moved yet.
   Targeted tests green.
2. **C2a — Line + Circle** (simplest): move the 8 handlers/appliers + scene shells; commit calls
   `self._scene._make_line_like`. Targeted tests green.
3. **C2b — Polyline:** move the 4 handlers + close-indicator helpers + shells. Targeted tests green.
4. **C2c — Rectangle** (3-step): move the ~12 methods incl. `_update_rect_ref_lines`/`_clear_rect_ref_lines`
   (calling `self._scene._make_ref_line`) + shells. Targeted tests green.
5. **C3 — `clear()` + `set_mode` wiring + RED-demo:** move the line/rect/circle/polyline teardown branches
   (L1035–1064 + the L1044 polyline-indicator hide) into `GeometryDrawingController.clear(new_mode)`;
   `set_mode` calls `self._geom_ctl.clear(mode)` once; polygon/arc/text branches stay inline.
6. **C4 — Verify** targeted set; back-compat guard; full suite (Phase-6 FAILED-diff gate); **manual smoke**.
7. **C5 — Spec stamp:** record `GeometryDrawingController` in `model-space-architecture.md` §5, add the
   slice-8 bullet to §6 (incl. the "behavior-home / state-stays-scene-side" and "gridline factory stays
   scene-side" conclusions); `last-verified`/`verified-commit`; add the module to `applies-to`.
   `SPEC-INDEX.md` unchanged (new collaborator under the existing spec; no boundary moved). Note Slice 9
   (Arc + Polygon into the same controller) as the next concern-#6 sub-slice.

## 6. Acceptance criteria (relocation tier, from `model-space-architecture.md` §8)

- [ ] `.fpd` byte-parity + undo bytes unchanged — trivially met (zero serialization surface); asserted by
      a round-trip smoke check on a real `.fpd` with 2D geometry.
- [ ] Line/Rectangle(incl. rotate)/Circle/Polyline drive correctly via **posted events on a shown view**,
      both mouse and HUD-typed; results equivalent to `main`.
- [ ] `draw_gridline` still builds a `GridlineItem` via the scene-side `_make_line_like` (gridline concern
      untouched); all `test_gridline_*` green.
- [ ] `set_mode` line/rect/circle/polyline teardown travels as a single idempotent
      `GeometryDrawingController.clear(new_mode)`; polygon/arc/text branches stay inline unchanged.
- [ ] Dispatch tables + `_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` untouched; coordinator applier dispatch via
      `getattr(self._scene, …)` unchanged; the coordinator's reads of scene-side drawing state unchanged.
- [ ] Back-compat intact: scene shells keep dispatch/coordinator/`main.py`/`model_view.py`/tests working;
      any statically-called relocated helper has a `@staticmethod` shell.
- [ ] Persisted geometry lists + all transient drawing state remain scene attributes (behavior-home model).
- [ ] Full suite green (chunked); no new failures beyond the documented pre-existing loci (FAILED-diff vs
      `main`).
- [ ] `model-space-architecture.md` §5/§6 re-audited + stamped; module added to `applies-to`.

## 7. Governed-behavior cross-refs (Rule A — do not restate)

Behavior is owned by `docs/specs/2d-geometry.md` (primitive placement, fill, level/plane semantics) and
the dynamic-input / `inferred-dimension-driven-placement.md §4` spec (HUD lifecycle, schemas, seed/
publish/resolve, variant cycling). This slice is structural only; it moves code without changing any
behavior those specs govern.
