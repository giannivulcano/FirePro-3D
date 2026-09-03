# Sprinkler / Design-Area / Hydraulic Decomposition Slice — Design

> **Status:** design (2026-09-03). Implements **Slice 6** of the Model_Space decomposition
> governed by `docs/specs/model-space-architecture.md` (§5/§8). This doc is the *how*; the
> *what* was locked in a grill (see §0). On landing, `model-space-architecture.md` §5/§6 is
> stamped in place — no parallel governing spec is created. Behavior is owned by
> `docs/specs/sprinkler-system-components.md`, `docs/specs/hydraulic-solver-and-reporting.md`,
> and the design-area/auto-populate specs (Rule A — not restated here).

## 0. Locked scope (from grill — not relitigated here)

- **Pure behavior-preserving relocation.** Zero behavior change, zero bug fixes.
- **Persisted / undoable / externally-read state stays on the scene.** `design_areas`,
  `water_supply_node`, `hydraulic_result`, `active_design_area`, and `_supply_network_node`
  (read by `hydraulic_report.py`) stay **scene attributes**; the controller reaches them via
  `self._scene.<attr>`. Rationale: they are in the dual-serialization/undo path and/or read by
  external consumers, so keeping them scene-side makes `.fpd` byte-parity + undo-parity trivial and
  requires zero serializer/test repointing (see the pipe-slice precedent: `sprinkler_system` stayed).
- **`sprinkler_system` stays** (shared with the pipe network + hydraulic solver — already left on the
  scene by slice 5). The controller only reads/mutates it via `self._scene.sprinkler_system`.
- **Serialization / undo stay on the scene.** `_capture_network`/`_restore_network` (concern #4
  god-glue) and `scene_io` + `network_codec` (`serialize/deserialize_{design_area,water_supply}`,
  already unified) are **untouched**; they reach the controller only through the public `add_sprinkler`
  shell during deserialize.
- **`get_effective_position`'s `design_area` snap branch stays** in the core resolver (irreducible
  core plumbing — reads `_snap_engine`/`_snap_result`/`_align_result`/`_snap_view`). The *handler-local*
  snap override inside `_press_design_area` travels with that body.
- **Dispatch tables untouched.** `_press_design_area`/`_move_design_area`/`_press_water_supply` stay
  as scene-side **forwarders**; `water_supply` move already routes to the shared `_move_preview_node`
  (stays). The `_skip_grip_modes` tuple membership + the instruction strings + the mode-list literals
  stay verbatim.
- **No §5.1 reach-in cleanup** — every external touchpoint is a kept method-API shell (`main.py`
  `run_hydraulics`/`clear_hydraulics`/`set_coverage_overlay`) or a direct read of a persisted attr
  that stays scene-side (`hydraulic_report`, `test_hydraulic_report`, `test_manip_badge_annotations`).
- **Deferred / explicitly out:** the §4 divergences (paste-path wall/room/floor/roof, gridline paste
  heuristic, `Room.z_range_mm`); the pre-existing sprinkler round-trip instability; concern #6
  (2D-geometry drawing); any behavior change to auto-populate, the snap override, or hydraulics.

## 1. Goal

Lift the sprinkler-placement + design-area + water-supply + run-hydraulics concern (decomposition-map
concern #2 — "Hard": scene mutation + `push_undo_state` + a shared-snap-engine mutation) out of
`model_space.py` (9,655 lines) into a scene-referencing collaborator
`SprinklerWorkflowController(scene)`, behavior-preservingly, with `.fpd` byte-parity and undo bytes
unchanged. Tractable now because the serializers are already unified (`network_codec`) and the grill
fenced the shared/persisted surfaces to stay on the scene.

## 2. Architecture

### 2.1 New collaborator

- **Module:** `firepro3d/sprinkler_workflow_controller.py`
- **Class:** `SprinklerWorkflowController` — a **plain object** (not a `QObject`), mirroring
  `PipeNetworkController(scene)` / `UnderlayController(scene)`. The signals it needs
  (`requestPropertyUpdate`, `sceneModified`) stay defined on the scene and are emitted via
  `self._scene.<sig>.emit(...)`; no thread affinity is introduced.
- **Constructed** in `Model_Space.__init__` (after `sprinkler_system` + `_pipe_ctl` exist, before
  dispatch is first used): `self._spr_ctl = SprinklerWorkflowController(self)`.

### 2.2 State owned by the controller

| Attr | Role |
|---|---|
| `self._da_editing` | working design area (None = not editing) — was `_da_editing` |
| `self._design_area_corner1` | first corner of the Shift+rect select — was `_design_area_corner1` |
| `self._design_area_rect_item` | transient rubber-band rect item — was `_design_area_rect_item` |
| `self._da_highlights` | pick-mode highlight rings list — was `_da_highlights` |
| `self._scene` | back-ref to `Model_Space` (scene-graph mutation + signal emission are universal — seam §3.1) |

**Not owned (stay on the scene, referenced via `self._scene`):** `sprinkler_system`, `design_areas`,
`water_supply_node`, `hydraulic_result`, `active_design_area`, `_supply_network_node` (external read),
`active_level`, `scale_manager`, `_snap_engine`, `_snap_view()`, `_level_manager`.

### 2.3 Delegation contract (on `Model_Space`)

- **6 public method shells** — each `return self._spr_ctl.<same>(...)`:
  `add_sprinkler`, `remove_sprinkler`, `auto_populate_room`, `run_hydraulics`, `clear_hydraulics`,
  `set_coverage_overlay`. Keeps `network_codec` deserialize (`scene.add_sprinkler`), `scene_tools`
  (`scene.add_sprinkler`), internal placement, the auto-populate dialog, and `main.py`'s three
  hydraulic buttons working unchanged.
- **`design_area_sprinklers` property shell** — stays on the scene, delegates to
  `self._spr_ctl.design_area_sprinklers` (reads `self._scene.active_design_area`). Backward-compat.
- **3 dispatch forwarders** (scene-side, so `getattr(self, name)` resolves untouched):
  `_press_design_area`, `_move_design_area`, `_press_water_supply` — each `*a` pass-through to
  `self._spr_ctl.press_design_area(*a)` / `move_design_area(*a)` / `press_water_supply(*a)`.
- **`confirm_design_area() -> bool`** (new) — the `contextMenuEvent` right-click-confirm branch body
  moves to the controller; `contextMenuEvent` keeps a thin guard:
  `if self.mode == "design_area": self._spr_ctl.confirm_design_area(); ... (stay in mode)`.

### 2.4 Methods moved whole into the controller

Sprinkler CRUD: `add_sprinkler`, `remove_sprinkler`.
Auto-populate: `auto_populate_room`.
Hydraulics: `run_hydraulics`, `clear_hydraulics`, `set_coverage_overlay`.
Design-area internals: `_ensure_editing_da`, `_da_change_committed`, `_refresh_da_highlights`,
`design_area_sprinklers` (property logic).
Placement/handler bodies: `_press_design_area` → `press_design_area(...)`; `_move_design_area` →
`move_design_area(...)`; `_press_water_supply` → `press_water_supply(...)`.
Context-menu confirm: the `design_area` branch body of `contextMenuEvent` → `confirm_design_area()`.

Body rewrites (mechanical, mirroring the pipe slice): `self.<sceneOp>`
(addItem/removeItem/createItemGroup/views/update) → `self._scene.<sceneOp>`; `self.sprinkler_system`
→ `self._scene.sprinkler_system`; the stay-on-scene attrs (`design_areas`, `water_supply_node`,
`hydraulic_result`, `active_design_area`, `_supply_network_node`, `active_level`, `scale_manager`,
`_snap_engine`, `_level_manager`) → `self._scene.<same>`; `self._snap_view()` →
`self._scene._snap_view()`; `self.<signal>.emit(...)` → `self._scene.<signal>.emit(...)`;
`self._show_status` → `self._scene._show_status`; scene methods that stay (`push_undo_state`,
`split_pipe`, `set_mode`, `project_click_onto_pipe_segment`, `apply_category_defaults` [module fn,
stays a direct import]) → `self._scene.<method>` where they are scene methods. Internal calls to
still-moving siblings stay `self.<method>`.

### 2.5 Dispatch, mode & confirm (three teardown/confirm paths, unchanged behavior)

- `_PRESS_DISPATCH` (`"design_area"→"_press_design_area"`, `"water_supply"→"_press_water_supply"`) and
  `_MOVE_DISPATCH` (`"design_area"→"_move_design_area"`, `"water_supply"→"_move_preview_node"`) resolve
  via the scene forwarders — **tables untouched**.
- `set_mode`'s two design-area branches split by ownership (both invoked next to
  `self._pipe_ctl.clear()`):
  - **Site A — mode-dependent DA z-restyle** (1031–1033, `for _da in design_areas:
    _da.sync_z_for_mode(mode=="design_area"); _da.update()`) → `self._spr_ctl.sync_design_area_z(mode
    == "design_area")` (reads `self._scene.design_areas`).
  - **Site B — leaving-`design_area` teardown** (1035–1042: null `_da_editing`,
    `_refresh_da_highlights()`, null `_design_area_corner1`, remove `_design_area_rect_item`) →
    `self._spr_ctl.clear()` — the **idempotent `clear()` hook** (§3.4). `set_mode` calls it
    unconditionally (like `_pipe_ctl.clear()`); `clear()` no-ops when there is nothing to tear down.
- `contextMenuEvent`'s `design_area` branch → `self._spr_ctl.confirm_design_area()` (sets
  `self._scene.active_design_area`, nulls `self._da_editing`, calls `_da_change_committed(confirmed=
  True)`; stays in mode). Analogous to the pipe slice's `complete_confirmation` elev delegation.

## 3. Data flow (unchanged, relocated)

- **Design-area pick (press):** `mousePressEvent` → `getattr(self,"_press_design_area")` → scene
  forwarder → `ctl.press_design_area(...)`; Shift-rect select vs single-toggle both run as today, with
  the handler-local snap override reading `self._scene._snap_engine`; `_ensure_editing_da` appends to
  `self._scene.design_areas`; `_da_change_committed` emits `requestPropertyUpdate`/`sceneModified` via
  `self._scene`.
- **Design-area confirm (right-click):** `contextMenuEvent` guard → `ctl.confirm_design_area()`.
- **Water-supply place:** forwarder → `ctl.press_water_supply(...)`; splits a pipe via
  `self._scene.split_pipe`, sets `self._scene.water_supply_node` + `sprinkler_system.supply_node`,
  emits `requestPropertyUpdate`, `push_undo_state`, `set_mode(None)`.
- **Sprinkler CRUD / auto-populate:** `scene.add_sprinkler`/`remove_sprinkler`/`auto_populate_room`
  shells → controller; mutate `self._scene.sprinkler_system` + node sprinklers. Identical order.
- **Hydraulics:** `scene.run_hydraulics(...)` shell → `ctl.run_hydraulics(...)`; runs the solver,
  writes `self._scene.hydraulic_result` + `self._scene._supply_network_node`, refreshes pipe labels +
  node badges via `self._scene.sprinkler_system`. `clear_hydraulics`/`set_coverage_overlay` likewise.
- **Undo / Save-load:** `_capture_network`/`_restore_network` + `scene_io`/`network_codec` stay on the
  scene and read `self.design_areas`/`self.water_supply_node` (scene attrs) exactly as today; restore
  calls `self.add_sprinkler(...)` (shell). Undo bytes + `.fpd` byte-identical.

## 4. Testing

**Characterization suite (written + green on the branch BEFORE C1 — the relocation safety net).**
Leverage existing coverage (`test_hydraulic_report.py`, `test_manip_badge_annotations.py`,
`test_serializer_parity.py`, any design-area/auto-populate tests), and add the gaps in a new
`tests/test_sprinkler_workflow_slice_parity.py`:

- `test_sprinkler_workflow_file_byte_parity` — load a real `.fpd` with design areas + water supply →
  save → byte-identical payload.
- `test_design_area_survives_undo_redo` — build design areas + water supply + sprinklers, snapshot,
  undo→redo, assert identical membership/active-area/water-supply/sprinkler state.
- `test_design_area_pick_live` — posted `QMouseEvent`s on a shown+activated view: click a sprinkler
  (added to working area, ring appears), Shift-rect select (adds enclosed sprinklers), right-click
  (confirm; next click starts a new area) — real entry point, not handler calls.
- `test_water_supply_place_live` — posted click on a node/pipe places the supply; a second placement
  replaces it; `scene.water_supply_node` + `sprinkler_system.supply_node` updated.
- `test_run_hydraulics_equivalence` — a fixed small network yields the same `HydraulicResult`
  (pressures/flows/badges) + `_supply_network_node` as `main` (result-equivalence, not just no-crash).
- `test_auto_populate_room` — `scene.auto_populate_room(...)` places the expected nodes/sprinklers and
  clears pre-existing ones.
- `test_sprinkler_workflow_backcompat` — the 6 public shells + `design_area_sprinklers` +
  `confirm_design_area` callable on the scene; `network_codec` deserialize (`scene.add_sprinkler`) and
  `scene_tools` (`scene.add_sprinkler`) still create sprinklers; `hydraulic_report` reads
  `scene._supply_network_node`.

**RED-demo (behavior-regression proof) — reserved for the `clear()` migration only:** stub
`SprinklerWorkflowController.clear()` to a no-op and confirm a "leave design_area mode mid-Shift-rect →
stale `_design_area_rect_item`/`_da_editing` orphaned" test goes RED; restore → green. A pure
relocation has no other red→green; the parity tests are green before and after by design.

**Subagent implementers run only the targeted test files.** Full-suite green (chunked per the
long-run-flake memory; no new failures beyond the pre-existing L72 trio + the L344 underlay-worker
locus) is a Phase-6 gate run by the orchestrator. Design-area picking + hydraulics are
interaction-heavy → **manual smoke test by the user** before wrap-up.

## 5. Slicing (revertable sub-commits, parity green at each step)

Branch: `refactor/model-space-sprinkler-slice`.

0. **C0 — Characterization tests** land on the branch, green (the safety net).
1. **C1 — Scaffold.** New `sprinkler_workflow_controller.py` (controller owning the 4 design-area
   transient attrs + `_scene` back-ref); `__init__` builds `self._spr_ctl`; move those attrs' init into
   the controller. No method bodies moved yet. Targeted tests green.
2. **C2 — Move methods** in batches, each relocating bodies + adding shells/forwarders, targeted tests
   green after each:
   - **C2a — sprinkler CRUD + auto-populate:** `add_sprinkler`, `remove_sprinkler`,
     `auto_populate_room` (+ 3 public shells).
   - **C2b — hydraulics:** `run_hydraulics`, `clear_hydraulics`, `set_coverage_overlay` (+ 3 shells;
     writes `self._scene._supply_network_node`/`hydraulic_result`).
   - **C2c — design-area internals + handlers:** `_ensure_editing_da`, `_da_change_committed`,
     `_refresh_da_highlights`, `design_area_sprinklers`; `_press_design_area`/`_move_design_area`/
     `_press_water_supply` bodies → controller (scene forwarders); `contextMenuEvent` branch →
     `confirm_design_area`.
3. **C3 — `clear()` + `sync_design_area_z()` + set_mode wiring** with the RED-demo.
4. **C4 — Verify** targeted set complete; confirm the back-compat guard; run full suite (Phase-6).
5. **C5 — Spec §5/§6 stamp** (`last-verified` / `verified-commit`); record `SprinklerWorkflowController`
   in §5's collaborator list and add the slice-6 bullet to §6.

## 6. Acceptance criteria (relocation tier, from `model-space-architecture.md` §8)

- [ ] File byte-parity: real `.fpd` (design areas + water supply) → load → save → byte-identical.
- [ ] Undo/redo leaves design-area membership / active area / water supply / sprinklers identical vs
      `main` (bytes unchanged).
- [ ] Design-area pick/select/confirm + water-supply placement + a hydraulics run drive correctly via
      posted events on a shown view; results equivalent to `main`.
- [ ] `set_mode` teardown travels as an idempotent `SprinklerWorkflowController.clear()`; the
      mode-dependent DA z-restyle travels as `sync_design_area_z(...)`.
- [ ] No §5.1 reach-in cleanup required (verified no-op); no moved method retains a hidden
      `self`/side-effect the shell doesn't cover.
- [ ] Back-compat intact: 6 shells + `design_area_sprinklers` + `confirm_design_area` for
      `main`/`hydraulic_report`/`scene_tools`/`network_codec`/tests + both deserialize paths.
- [ ] Full suite green (chunked); no new failures beyond the pre-existing trio + underlay-worker locus.
- [ ] `model-space-architecture.md` §5/§6 re-audited + stamped.

## 7. Governed-behavior cross-refs (Rule A — do not restate)

Behavior is owned by `sprinkler-system-components.md` (the `SprinklerSystem` container + sprinklers),
`hydraulic-solver-and-reporting.md` (solver, supply-node resolution, badges, reporting), and the
design-area/auto-populate specs (design-area membership, spacing warnings, NFPA curves,
auto-populate placement). Serialization lives in `architecture/io.md` + `network_codec.py`. This slice
is structural only; it moves code without changing any behavior those specs govern.
