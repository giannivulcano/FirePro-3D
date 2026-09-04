# Placement-Input Coordination Decomposition Slice — Design

> **Status:** design (2026-09-03). Implements **Slice 7** of the Model_Space decomposition
> governed by `docs/specs/model-space-architecture.md` (§5/§8). This doc is the *how*; the
> *what* was locked in a grill (see §0). On landing, `model-space-architecture.md` §5/§6 is
> stamped in place — no parallel governing spec is created. Behavior is owned by
> `docs/specs/align-placement.md` and the dynamic-input / `inferred-dimension-driven-placement.md §4`
> spec (Rule A — not restated here).

## 0. Locked scope (from grill + design exploration — not relitigated here)

- **Pure behavior-preserving relocation.** Zero behavior change, zero bug fixes.
- **One collaborator, one slice.** Extract the **placement-input** concern — the HUD lifecycle,
  variant cycling, seed/publish/resolve, schema selection, template getters, and placement-anchor
  accessors — into `PlacementInputCoordinator(scene)`. (The grill originally reserved a second
  sub-slice "7b" for ALIGN; design exploration showed ALIGN-tracking is irreducible core — see the
  next bullet — so there is no 7b.)
- **ALIGN-tracking stays as core snap-plumbing (KEY DECISION).** The AutoCAD-style ALIGN *tracking*
  subsystem (`_align_controller`, `_align_enabled`, `_align_path_tol_px`, the per-frame scratch
  `_align_result`/`_align_track_ray`/`_align_track_dist`/`_align_anchor_dir`/`_align_active_item`/
  `_align_last_move_ns`, and the tracking helpers `_align_track_active`/`_align_track_schema`/
  `_align_snap_dict`/`_commit_track_first_point`) is **read or driven by `get_effective_position` and
  `mouseMoveEvent`** — the two hottest per-move core paths (evidence: `model_space.py` L2099/2114/2119
  and L3983/3984). It belongs to the same irreducible-core snap bucket as `_snap_result` and the snap
  engine (§6). It **stays on the scene, untouched**; the coordinator reaches what little it needs
  (`_align_track_schema()`, `_align_track_active()`, `_align_track_ray`/`_dist`) via `self._scene.*`.
  This is a deliberate architectural conclusion, recorded in `model-space-architecture.md` §5/§6 — not
  a deferred TODO. The coordinator owns placement **input**; the snap resolver owns ALIGN **tracking**.
- **The `"align"` MODE and `_press_align`/`_move_align` are OUT OF SCOPE.** They are the two-pick
  **align-EDGES tool** (`SceneTools._press_align`/`_move_align`, reading
  `_align_reference`/`_align_highlight`/`_align_ghost`/`_align_padlocks`) — a different subsystem that
  merely shares the "align" name prefix. It stays in `scene_tools.py`, untouched.
- **Plain object, not `QObject`.** Mirrors `PipeNetworkController(scene)` /
  `SprinklerWorkflowController(scene)`. Signals stay on the scene, emitted via `self._scene.<sig>.emit`.
- **Generalized render-scratch rule (LOCKED).** Any scratch read by `model_view.drawForeground` stays
  scene-side. `_align_result` stays (core). `_draw_dim_hint` stays, written by the coordinator via
  `self._scene._draw_dim_hint`. `_resolved_point` is coordinator-internal (not read by
  `drawForeground`) so it **moves**.
- **Appliers stay scene-side, dispatched via `getattr`.** `_apply_{rectangle,polygon,arc,wall,floor,
  pipe}_dynamic_input`, `_commit_draw_line_at` / `_commit_polyline_at` / `_commit_draw_circle_at`,
  `_apply_move_displacement`, `_apply_gridline_offset` / `_apply_gridline_array` stay on the scene and
  are reached through `getattr(self._scene, applier_name)`.
- **Dispatch tables + registries.** `_APPLIER_FOR_MODE`, `_SCHEMA_FOR_MODE`, `_ALIGN_PLACEMENT_MODES`
  stay **class-level on `Model_Space`**. `_PLACEMENT_VARIANTS` (instance registry built by
  `_init_placement_variants`) **moves to the coordinator** with the variant-cycling machinery; its
  lambdas call scene methods with the scene passed in as `s`.
- **Variant flags + template caches stay scene-side.** `_arc_variant`, `_draw_rect_from_center`,
  `_wall_primitive`, `_floor_primitive`, `_wall_rect_rotating`, `_floor_rect_rotating`,
  `_polygon_rotating`, `_draw_arc_step` (geometry stage-state consumed by #6/#7 handlers) and
  `_wall_template` / `_floor_template` / `_roof_template` / `_gridline_template` / `_geometry_template`
  (authored by `main.py` dialogs) stay scene attributes; only the *getter/decision* logic moves.
- **Zero serialization surface (confirmed).** No concern-#5 state is in `scene_io.py`,
  `network_codec.py`, or `_capture_network`/`_restore_network`. `.fpd` byte-identical and undo bytes
  unchanged are **trivially** met; the gate is **live parity + manual smoke** (pure interaction
  plumbing — HUD widget, dispatch, render — the live-only bug class).
- **§5.1 cleanup — flag stays scene-side.** Add `get_align_enabled()` as a **scene method**
  (`return self._align_enabled`) and repoint the 4 bare `_align_enabled` reads (`main.py`
  567/2355/2390, `model_view.py` 442). Because `_align_enabled` stays on the scene (ALIGN is core),
  this is pure read-hygiene with zero hot-path cost — it does not require moving the flag.
- **Deferred / explicitly out:** concern #6 (2D-geometry drawing) and #7 (arch-placement); the align-
  EDGES tool; the §4 divergence ledger; the `node_start_pos` split; any behavior change.

## 1. Goal

Lift the placement-input concern out of `model_space.py` (9,376 lines) into a scene-referencing
collaborator `PlacementInputCoordinator(scene)`, behavior-preservingly. Tractable as a *Medium* slice
because the heavy engine already lives in its own module — the `DynamicInputHud` + `SCHEMAS`
(`dynamic_input.py`, 1,391 LOC) — so this slice relocates the **scene-side coordination**, not the
HUD engine. Design exploration fenced ALIGN-tracking to stay in the core snap resolver (it is read/
driven by `get_effective_position`/`mouseMoveEvent`), so the coordinator has a clean accessor boundary
(`publish_placement_state` / `get_resolved_point` / `active_schema` / `_hud_available`) and no hot-path
entanglement.

## 2. Architecture

### 2.1 New collaborator

- **Module:** `firepro3d/placement_input_coordinator.py`
- **Class:** `PlacementInputCoordinator` — a **plain object** (mirrors `PipeNetworkController` /
  `SprinklerWorkflowController`). Delegates to the already-extracted `DynamicInputHud`; owns the
  scene-side placement-input state and back-references the scene (`self._scene`) for scene-graph
  mutation, signal emission, and reads of stay-scene-side state (incl. ALIGN scratch).
- **Constructed** in `Model_Space.__init__` at ~L169, immediately after `self._spr_ctl`:
  `self._plc = PlacementInputCoordinator(self)`. The coordinator's `__init__` runs
  `self._init_placement_variants()` (building `_PLACEMENT_VARIANTS` + `_variant_index` on the
  coordinator), **replacing** the current `self._init_placement_variants()` call at L268. The
  `dynamic_input` HUD widget **stays lazily created** (starts `None`, built in `_create_dynamic_input`).

### 2.2 State owned by the coordinator

| Attr | Role |
|---|---|
| `self._scene` | back-ref to `Model_Space` (scene mutation + signals + stay-scene reads — seam §3.1) |
| `self.dynamic_input` | the live `DynamicInputHud` widget (or `None`); lazily created — was `dynamic_input` |
| `self._pipe_hud_reference` | reference pipe for the pipe HUD relative-angle frame — was `_pipe_hud_reference` |
| `self._resolved_point` | constrained point under cursor, the HUD seed source (coordinator-internal — not read by `drawForeground`) — was `_resolved_point` |
| `self._variant_index` | per-mode sticky variant index `{mode: int}` — was `_variant_index` |
| `self._PLACEMENT_VARIANTS` | per-mode variant registry — was the instance dict built in `_init_placement_variants` |

**Not owned (stay on the scene, referenced via `self._scene`):**
- **ALIGN-tracking (all of it — core snap-plumbing):** `_align_controller`, `_align_enabled`,
  `_align_path_tol_px`, `_align_result`, `_align_track_ray`, `_align_track_dist`, `_align_anchor_dir`,
  `_align_active_item`, `_align_last_move_ns`, and the helpers `_align_track_active`,
  `_align_track_schema`, `_align_snap_dict`, `_commit_track_first_point`.
- **Render scratch read by `drawForeground`:** `_draw_dim_hint` (written by the coordinator via
  `self._scene._draw_dim_hint`).
- **Geometry stage-state (variant flags):** `_arc_variant`, `_draw_rect_from_center`, `_wall_primitive`,
  `_floor_primitive`, `_wall_rect_rotating`, `_floor_rect_rotating`, `_polygon_rotating`, `_draw_arc_step`.
- **Template caches:** `_wall_template`, `_floor_template`, `_roof_template`, `_gridline_template`,
  `_geometry_template`.
- **Shared placement plumbing:** `preview_pipe`, `preview_node`, `_last_scene_pos`, `_snap_result`,
  `_snap_engine`, `mode`, `get_effective_position`, `active_level`, `scale_manager`.
- **Dispatch tables (class-level on `Model_Space`):** `_APPLIER_FOR_MODE`, `_SCHEMA_FOR_MODE`,
  `_ALIGN_PLACEMENT_MODES`.

### 2.3 Delegation contract (on `Model_Space`)

- **Public method shells** — each `return self._plc.<same>(...)` — for method-API callers
  (`main.py` / `model_view.py` / dispatch): `get_placement_anchor`, `get_resolved_point`,
  `publish_placement_state`, `clear_placement_state`, `is_input_mode`, `active_schema`,
  `cycle_placement_variant`, `apply_dynamic_input`, `begin_dynamic_input`, `end_dynamic_input`.
- **`get_align_enabled() -> bool`** (new) — a **scene method**, `return self._align_enabled` (flag
  stays scene-side). Replaces the 4 bare `_align_enabled` reads (§5.1). `set_align_enabled` stays a
  scene method unchanged (ALIGN stays scene-side).

### 2.4 Methods moved whole into the coordinator

**HUD lifecycle:** `_create_dynamic_input`, `_sync_dynamic_input`, `begin_dynamic_input`,
`end_dynamic_input`, `_on_dynamic_input_cancelled`, `_on_dynamic_input_committed`,
`_on_dynamic_input_field_committed` (unused; scheduled removal), `is_input_mode`, `_hud_available`,
`apply_dynamic_input`, `_visible_view`.
**Seed/publish/resolve + HUD arming:** `publish_placement_state`, `get_resolved_point`,
`clear_placement_state`, `_seed_values_for`, `_transform_seed_values`, `_seed_pipe_line`,
`_arm_pipe_relative`, `_arm_arc_coupling`, `_arm_track_direction` (arms the HUD from the winning ALIGN
ray — reads `self._scene._align_track_ray`).
**Schema selection:** `active_schema`, `_base_schema`, `_rectangle_schema_for_step`,
`_polygon_schema_for_step`, `_arc_schema_for_step`, `_wall_schema_for_primitive`,
`_floor_schema_for_primitive`.
**Variant cycling:** `_init_placement_variants`, `_at_placement_step_zero`, `_apply_current_variant`,
`cycle_placement_variant`.
**Template getters:** `_get_wall_template`, `_get_floor_template`, `_get_roof_template`,
`_get_gridline_template`, `_get_geometry_template`.
**Placement-anchor accessors:** `get_placement_anchor`, `_mode_placement_anchor`.

**Body rewrites (mechanical, mirroring prior slices):** `self.<sceneOp>` (`addItem`/`removeItem`/
`views`/`update`/`clearSelection`) → `self._scene.<sceneOp>`; each stay-scene attr (the ALIGN-tracking
set, `_draw_dim_hint`, the variant flags, the template caches, `preview_pipe`, `preview_node`,
`_last_scene_pos`, `_snap_result`, `_snap_engine`, `mode`, `active_level`, `scale_manager`) →
`self._scene.<same>`; `self.get_effective_position(...)` → `self._scene.get_effective_position(...)`;
the ALIGN helpers that stay on the scene (`_align_track_schema`, `_align_track_active`) →
`self._scene._align_track_*()`; `self.<signal>.emit(...)` → `self._scene.<signal>.emit(...)`;
`self._show_status` → `self._scene._show_status`; the class dispatch tables →
`self._scene._APPLIER_FOR_MODE` / `_SCHEMA_FOR_MODE`; `getattr(self, applier_name)` →
`getattr(self._scene, applier_name)`; scene methods that stay (`_set_wall_primitive`,
`_set_floor_primitive`, appliers, `set_mode`) → `self._scene.<method>`. Internal calls to
still-moving siblings stay `self.<method>`.

### 2.5 Dispatch, mode & `clear()` (unchanged behavior)

- **`apply_dynamic_input` / `_hud_available`** — coordinator methods: gate on
  `self._scene.mode in self._scene._APPLIER_FOR_MODE`; dispatch via
  `getattr(self._scene, applier_name)(...)`. The `_APPLIER_FOR_MODE` table stays class-level on
  `Model_Space`.
- **One idempotent `clear()`** (the §3.4 hook): `PlacementInputCoordinator.clear()` =
  `self.end_dynamic_input()` + `self.clear_placement_state()`. `set_mode` calls `self._plc.clear()`
  **once** at ~L976 (before `self.mode = mode` — HUD teardown must see the outgoing mode), replacing
  the current L976 `end_dynamic_input()` + L981 `clear_placement_state()`.
- **Stays inline in `set_mode` (ALIGN core — NOT moved):** the entire ALIGN block L1000-1007
  (`_align_controller.clear()`, dwell-scratch nulling, the mode-conditional
  `_align_active_item`/`_align_result` arm) stays verbatim — ALIGN-tracking stays scene-side.
- **`_variant_index` writes in `set_mode` (hasattr-trap fix).** L954/963 currently do
  `if hasattr(self, "_variant_index"): self._variant_index["wall"|"floor"] = …` (the wall/floor
  corner-rect alias). When `_variant_index` moves to the coordinator, the `hasattr(self, …)` guard
  silently evaluates False and the alias breaks (the *mixin→composition hasattr trap*,
  `project_mixin_to_composition_hasattr_trap`). Repoint to `self._plc._variant_index["wall"|"floor"]`
  and drop the guard (`_plc` is built at L169, so `_variant_index` always exists when `set_mode` runs).

## 3. Data flow (unchanged, relocated)

- **Per-move HUD sync:** `mouseMoveEvent` (core) resolves the point via `get_effective_position`
  (core — drives ALIGN, writes ALIGN scratch), calls the per-mode `_move_*` handler (which publishes
  via `scene.publish_placement_state(...)` → `_plc`), then `scene._sync_dynamic_input()` (shell →
  `_plc`) reconciles the HUD. The HUD seeds from `_plc._resolved_point`; the painted fallback readout
  `_draw_dim_hint` is written by `_plc` onto the scene and painted by `drawForeground` (untouched).
- **Typed commit:** the HUD's Enter → `scene._on_dynamic_input_committed()` (shell → `_plc`) resolves
  typed values into geometry, dispatches through `getattr(self._scene, _APPLIER_FOR_MODE[mode])`, and
  on success closes the HUD; on refusal the applier returns False and the field is flagged.
- **Variant cycle:** ←/→ in `keyPressEvent` (core) → `scene.cycle_placement_variant(direction)`
  (shell → `_plc`); `_plc` advances `_variant_index[mode]`, runs the registry `apply_fn` with
  `self._scene` (which sets the scene-side variant flag), emits the hinted step-0 readout.
- **Schema resolution:** `scene.active_schema()` (shell → `_plc.active_schema`) returns the Track
  schema when `self._scene._align_track_schema()` is live (ALIGN stays scene-side), else `_base_schema()`
  (mode + variant-flag + step aware, reading scene-side flags).
- **ALIGN tracking (untouched, scene-side):** `get_effective_position` drives `_align_controller`,
  writes `_align_result`/`_align_track_ray`; `drawForeground` paints them + the acquired `+` markers.
  The coordinator only *reads* the winning ray via `self._scene._align_track_ray` to seed the track HUD.
- **Teardown:** `set_mode` → `self._plc.clear()` (HUD); the ALIGN block runs inline; `.fpd`/undo
  untouched (no serialization surface).

## 4. Testing

**Existing coverage is the parity net (must stay green = behavior preserved).** ~26 files already
exercise this concern through the seam and the real entry point: `test_dynamic_input_*`
(lifecycle/seam/parity/multiview/widget/schema/pipe), `test_placement_variants.py`,
`test_wall_placement_workflow.py`, `test_floor_placement_workflow.py`, and the `test_align_*` suite
(which also guards that ALIGN-tracking behavior is unchanged while the coordinator reads it via
`self._scene`).

**Add ONE new file `tests/test_placement_input_slice_parity.py`:**

- `test_backcompat_shells` — the public shells (`get_placement_anchor`, `get_resolved_point`,
  `publish_placement_state`, `clear_placement_state`, `is_input_mode`, `active_schema`,
  `cycle_placement_variant`, `apply_dynamic_input`, `begin/end_dynamic_input`) are callable on the
  scene and delegate to `_plc`; `scene.get_align_enabled()` returns the scene flag.
- `test_hud_open_seed_commit_live` — posted `QMouseEvent`/`QKeyEvent` on a shown+activated view: draw a
  line/rectangle, open the HUD, seed a value, commit; assert the geometry matches the mouse path (real
  entry point, not handler calls).
- `test_variant_cycle_live` — ←/→ cycles the wall/floor/rect/arc variant at step 0, and the wall/floor
  corner-rect alias set in `set_mode` still lands on the right slot (guards the hasattr-trap fix).
- `test_track_schema_seed_live` — with an ALIGN track engaged, `active_schema()` returns the Track
  schema and the HUD seeds the signed distance from `self._scene._align_track_dist` — proving the
  coordinator reads ALIGN scratch correctly via `self._scene`.
- `test_align_enabled_accessor` — `scene.get_align_enabled()` reflects `set_align_enabled(...)`; the 4
  repointed reads observe the same value.
- **`clear()` RED-demo** — stub `PlacementInputCoordinator.clear()` to a no-op and confirm a
  "leave a placement mode with the HUD open → stale HUD / stale `_resolved_point` readout" test goes
  RED; restore → green.

A pure relocation has no other red→green; the parity tests are green before and after by design.

**Subagent implementers run only the targeted test files.** Full-suite green — read by **FAILED-diff vs
`main`** (`-v --tb=no`), not pass-count, per `project_model_space_fullsuite_gate_native_crash` — is a
Phase-6 orchestrator gate; no new failures beyond the documented pre-existing loci (the L72 trio, the
two newly-catalogued `main` failures, the QPrinter-SEH and underlay-worker native-crash loci). The HUD
is a live widget → **manual smoke test by the user** before wrap-up, with the exact `cd` + venv command
and the branch name stated (per the wrong-code-smoke-test hazard).

## 5. Slicing (revertable sub-commits, parity green at each step)

Branch: `refactor/model-space-placement-input-slice`.

0. **C0 — Characterization + RED-demo tests** land on the branch, green (safety net).
1. **C1 — Scaffold.** New `placement_input_coordinator.py` (coordinator owning `dynamic_input`,
   `_pipe_hud_reference`, `_resolved_point`, `_variant_index`, `_PLACEMENT_VARIANTS` + `_scene`
   back-ref); `__init__` builds `self._plc` at ~L169 and runs `_init_placement_variants` (remove the
   L268 call); **hasattr-trap fix** at `set_mode` L954/963. No HUD/seed/schema bodies moved yet.
   Targeted tests green.
2. **C2a — HUD lifecycle + commit dispatch:** `_create_dynamic_input`, `_sync_dynamic_input`,
   `begin/end_dynamic_input`, `_on_dynamic_input_cancelled/_committed/_field_committed`, `is_input_mode`,
   `_hud_available`, `apply_dynamic_input`, `_visible_view` (+ shells). `_draw_dim_hint` writes routed
   through `self._scene`.
3. **C2b — seed/publish/resolve + schema + templates + anchors:** `publish_placement_state`,
   `get_resolved_point`, `clear_placement_state`, `_seed_values_for`, `_transform_seed_values`,
   `_seed_pipe_line`, `_arm_pipe_relative`, `_arm_arc_coupling`, `_arm_track_direction`; `active_schema`,
   `_base_schema`, the 5 `_*_schema_for_step/_primitive`; `_get_*_template`; `get_placement_anchor`,
   `_mode_placement_anchor` (+ shells). ALIGN reads go through `self._scene.*`.
4. **C2c — variant cycling:** `_at_placement_step_zero`, `_apply_current_variant`,
   `cycle_placement_variant` (+ shell).
5. **C3 — `clear()` + `set_mode` wiring + §5.1 + RED-demo:** `set_mode` L976/981 → single
   `self._plc.clear()`; add scene `get_align_enabled()` + repoint the 4 bare `_align_enabled` reads.
6. **C4 — Verify** targeted set; back-compat guard; full suite (Phase-6 gate); **manual smoke**.
7. **C5 — Spec stamp:** record `PlacementInputCoordinator` in `model-space-architecture.md` §5, add the
   slice-7 bullet to §6 **including the "ALIGN-tracking stays as irreducible core snap-plumbing"
   architectural conclusion**; `last-verified`/`verified-commit`. `SPEC-INDEX.md` unchanged (new
   collaborator under the existing spec; no boundary moved).

## 6. Acceptance criteria (relocation tier, from `model-space-architecture.md` §8)

- [ ] `.fpd` byte-parity + undo bytes unchanged — trivially met (zero serialization surface); asserted
      by a round-trip smoke check.
- [ ] HUD open/seed/commit, ←/→ variant cycle (incl. the wall/floor corner-rect alias), and an
      ALIGN-track typed-distance seed all drive correctly via **posted events on a shown view**; results
      equivalent to `main`.
- [ ] `set_mode` HUD teardown travels as a single idempotent `PlacementInputCoordinator.clear()`; the
      ALIGN block stays inline unchanged (ALIGN is core).
- [ ] Render reads untouched: `model_view.drawForeground` still reads `_align_result` + `_draw_dim_hint`
      from the scene; `get_effective_position` still drives ALIGN + writes its scratch on the scene.
- [ ] §5.1: scene `get_align_enabled()` added; the 4 bare `_align_enabled` reach-ins repointed. No ALIGN
      state moved off the scene.
- [ ] Back-compat intact: the public shells keep `main.py` / `model_view.py` / dispatch working
      unchanged; dispatch tables untouched.
- [ ] Full suite green (chunked); no new failures beyond the documented pre-existing loci (FAILED-diff
      vs `main`).
- [ ] `model-space-architecture.md` §5/§6 re-audited + stamped, incl. the ALIGN-tracking-is-core note.

## 7. Governed-behavior cross-refs (Rule A — do not restate)

Behavior is owned by the dynamic-input / `inferred-dimension-driven-placement.md §4` spec (HUD
lifecycle, schemas, seed/publish/resolve, variant cycling, one-HUD invariant S1) and
`docs/specs/align-placement.md` (ALIGN acquire/dwell/track — which this slice leaves in the core snap
resolver, unchanged). This slice is structural only; it moves code without changing any behavior those
specs govern.
