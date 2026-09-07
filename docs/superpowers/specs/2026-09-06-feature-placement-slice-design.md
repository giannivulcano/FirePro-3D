# Feature-Placement Decomposition Slice — Design

> **Status:** design (2026-09-06). Implements **Slice 11** of the Model_Space decomposition
> governed by `docs/specs/model-space-architecture.md` (§5/§5.3/§6/§8). This doc is the *how*; the
> *what* is locked by the governing spec + the Phase-2 grill + the slice-10 template
> (`2026-09-05-wall-placement-slice-design.md`) — not relitigated. On landing,
> `model-space-architecture.md` §5/§6 is stamped in place — no parallel governing spec. Behavior is
> owned by `docs/specs/wall-room-floor-system.md §7` (Opening = first Feature) — Rule A, not restated.
>
> **Second slice of concern #7 (architectural placement); the Feature-placement collaborator.**
> Slice 10 extracted wall placement and deliberately left `_find_wall_at`/`_offset_along_wall`
> scene-side "for the future Opening slice." This slice completes that earmark.

## 0. Locked scope (from the governing spec + Phase-2 grill — not relitigated)

- **Pure behavior-preserving relocation.** Zero behavior change, zero bug fixes.
- **NEW module + collaborator.** Move concern #7's **Feature placement** methods from `model_space.py`
  into a new `firepro3d/feature_placement_controller.py` — `class FeaturePlacementController(scene)`
  (plain object, behavior home). Constructed in `Model_Space.__init__` as
  `self._feature_ctl = FeaturePlacementController(self)`, alongside the other `_*_ctl` collaborators
  (near `model_space.py:174`, next to `self._wall_ctl`).
- **Naming (Phase-1b convention, cite in every implementer prompt).** The collaborator is
  **`FeaturePlacementController`**, NOT `OpeningPlacementController`: the Opening is the *first* Feature
  (Category "Openings"; Types Door/Window/Blank; `feature.py` registry), all current Features are
  `host_type="Wall"`, and floor/ceiling/face host strategies are a filed todo. Naming it for the
  Opening would design into the corner `wall-room-floor-system.md §7.16` warns against. **The methods
  keep their `_press_opening`/`_move_opening`/`_opening_*` names** (pure relocation; they implement the
  Opening Category, the only Feature Class built so far — future Feature categories/host-types add new
  methods to the same controller, mirroring how `GeometryDrawingController` holds `_press_line`/
  `_press_rectangle`/…).
- **BEHAVIOR HOME — all placement STATE stays scene-side (§5.3, Fork 1 locked).** Mirrors slices 8/9/10:
  the controller owns the *methods*, not the state. Every `_opening_*` transient **and** the shared
  `current_template` stay on the scene, read/written via `self._scene.*`. Forcing reasons: (a) consistency
  with the established §5.3 convention (slices 8/9/10) → zero test-repoint churn (the 10 white-box
  `scene._opening_*` asserts in `test_opening_placement.py`/`test_opening_ribbon.py` stay green
  unchanged); (b) `current_template` is **shared** — read by `pipe_network_controller.py` (4×) +
  `add_sprinkler` (`model_space.py:4308`), so it is irreducibly scene-side; keeping the rest scene-side
  gives one consistent rule instead of a split state home. (State-owner purity belongs to a future
  dedicated Feature-system refactor at Phase B/C, not a mechanical relocation.)
- **Legacy door/window shims relocate as-is (Fork 3 locked).** `_press_door`/`_press_window`
  (→`_press_opening`) and `_move_door_window` (→`update_preview_node`) move into the controller with
  scene shells; the `"door"`/`"window"` modes + dispatch entries are untouched. **No retirement** —
  `DOOR_PRESETS`/`WINDOW_PRESETS`/the `**_legacy` ctor shim/the `isinstance(item,(DoorOpening,
  WindowOpening))` simplification stay OUT (already filed under the "Opening panel/polish" todo).
- **Cross-concern / shared / generic helpers STAY scene-side** (used across concerns), reached via
  `self._scene.*`: `current_template` (shared), `preview_pipe`/`preview_node`/`update_preview_node`
  (shared by every placement mode), `get_effective_position`, `_active_view_scale`, `_show_status`,
  `push_undo_state`, `scale_manager`, `active_level`, `is_input_mode`, `cycle_placement_ambiguity`
  (core, shared Space router), the `requestPropertyUpdate`/`instructionChanged` signals (emit via
  `self._scene.<sig>.emit`), `views()`, `addItem`/`removeItem`.
- **`_walls` stays scene-side (behavior-home, from slice 10)** — read by `_find_wall_at`.
- **Repoint nothing (dispatch/coordinator/keyPress/core stay working via scene shells).**
  `_PRESS_DISPATCH`/`_MOVE_DISPATCH`/`_PREVIEW_DISPATCH`/`_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` stay
  **class-level on `Model_Space`, untouched**; resolution flows `getattr(self, handler)` → scene shell
  → controller. (Opening has **no** `_PREVIEW_DISPATCH`/`_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` entry —
  click-commit + Spacebar/arrow cycle, no HUD.)
- **Plain object, not `QObject`.** Signals via `self._scene.<sig>.emit`.
- **Zero serialization surface (confirmed).** Openings serialize **inside** their host wall's
  `to_dict()["openings"]` array (`wall.py`), not a top-level scene list; the controller owns no
  persisted list. → `.fpd` byte-identical + undo bytes unchanged are **trivially** met; the gate is
  **live parity + manual smoke** (pure interaction plumbing — the live-only bug class).
- **Deferred / explicitly out:** room/floor/roof/gridline placement (later concern-#7 slices), the
  `WallOpening`/`wall.openings` entity model (governed by `wall-room-floor-system.md §7`), the Feature
  registry/Browser/Manager/Editor (Feature *system*, graduates to its own spec at Phase B), any
  behavior change, any legacy-shim retirement.

## 1. Goal

Lift concern #7's **Feature placement** behavior out of `model_space.py` into a new
`FeaturePlacementController`, behavior-preservingly — the second per-element arch-placement collaborator
(after wall). Gives Feature placement a named, isolation-testable, future-proof home (host strategies
grow here) and shrinks the god-object's method surface, while all placement STATE stays scene-side as
the contract between the Feature-placement behavior (`_feature_ctl`) and the shared placement plumbing.

## 2. Architecture

### 2.1 Collaborator (NEW)

- **Module/Class:** `firepro3d/feature_placement_controller.py` — `class FeaturePlacementController`
  (plain object, behavior home). `__init__(self, scene)` stores `self._scene = scene` (mirrors
  `WallPlacementController`).
- **Construction:** `self._feature_ctl = FeaturePlacementController(self)` in `Model_Space.__init__`
  next to `self._wall_ctl` (~`model_space.py:174`).
- **Imports (finalized against the moved bodies during implementation — import only what they use):**
  `WallOpening` (+ `DEFAULT_FEATURE_FOR_TYPE`, `OPENING_ALIGNMENTS` — confirm module homes:
  `DEFAULT_FEATURE_FOR_TYPE` is in `feature.py`; `OPENING_ALIGNMENTS`/`WallOpening` in `wall_opening.py`);
  `QGraphicsItem` (QtWidgets); `QPointF` (QtCore); `math`; `WallSegment` (from `.wall`, for the
  `_find_wall_at`/`_offset_along_wall` type hints — `TYPE_CHECKING` guard if a cycle threatens).

### 2.2 State — NONE owned by the controller (behavior-home, §5.3, Fork 1)

All stays on the scene, referenced via `self._scene`:

- **Transient cycle state (scene-side, behavior-home):** `_opening_feature_id`, `_opening_alignment`,
  `_opening_mirror_hinge`, `_opening_mirror_facing`, `_opening_ghost` (defined ~`model_space.py:446-450`).
- **Shared placement template (irreducibly scene-side):** `current_template` (read by pipe/sprinkler).
- **Persisted (scene-side, from wall slice + entity model):** `_walls` (read by `_find_wall_at`);
  openings themselves live in `wall.openings` (host-owned, not scene-side).
- **Shared plumbing / signals / generic helpers:** per §0 — all reached via `self._scene.*`.

### 2.3 Methods moved into the controller (bodies operate on `self._scene.*`)

**11 methods (line numbers at design time):**

- **Cycle behavior:** `_cycle_opening_alignment` (`:2968`), `_sync_opening_state_to_template` (`:2983`).
- **Commit-click:** `_press_opening` (`:6131`), `_press_door` (`:6171`), `_press_window` (`:6178`).
- **Live preview / ghost:** `_move_opening` (`:6184`), `_move_door_window` (`:3748`),
  `_refresh_opening_ghost` (`:6218`), `_clear_opening_ghost` (`:6230`).
- **Host lookup (slice-10 earmark):** `_find_wall_at` (`:6657`), `_offset_along_wall` (`:6664`).

Plus a **new** `enter(template)` method (absorbs the `set_mode` entering-arm, §2.5) and a **new**
`clear(new_mode)` method (absorbs the `set_mode` leaving-teardown, §2.5).

**Body rewrites (mechanical, mirroring slice 10):** `self.<sceneOp>` (`addItem`/`removeItem`/`views`/
`update_preview_node`/`_show_status`/`push_undo_state`) → `self._scene.<sceneOp>`; each state attr in
§2.2 → `self._scene.<same>`; `self.<signal>.emit` → `self._scene.<signal>.emit`; `self.mode`/
`self.current_template`/`self._walls`/`self._opening_*` → `self._scene.<same>`. **Internal calls to
still-moving siblings stay `self.<method>`** — e.g. `_press_opening` → `self._find_wall_at`/
`self._offset_along_wall`; `_move_opening` → `self._find_wall_at`/`self._offset_along_wall`/
`self._clear_opening_ghost`; `_cycle_opening_alignment` → `self._sync_opening_state_to_template`/
`self._refresh_opening_ghost`; `_press_door`/`_press_window` → `self._press_opening`.

### 2.4 Delegation contract — scene-side shells vs bare move (grep-confirmed)

**Scene-side shells REQUIRED** (referenced by a dispatch table, the core keyPress path, or tests):

- **Dispatch-resolved (press):** `_press_opening` (`_PRESS_DISPATCH["opening"]` `:4037`; also called
  white-box by `test_opening_ribbon.py:125`), `_press_door` (`:4038`), `_press_window` (`:4039`).
- **Dispatch-resolved (move):** `_move_opening` (`_MOVE_DISPATCH["opening"]` `:3311`), `_move_door_window`
  (`_MOVE_DISPATCH["door"]`/`["window"]` `:3312`/`:3313`).
- **Core-keyPress-called:** `_cycle_opening_alignment` (via `cycle_placement_ambiguity` at `:2964`, the
  core Space router); `_sync_opening_state_to_template` + `_refresh_opening_ghost` (the core keyPress
  arrow block at `:6748-6760`).

**Move WITHOUT a shell** (controller-internal only — whole-repo `*.py` grep found no external/test
caller): `_find_wall_at`, `_offset_along_wall`, `_clear_opening_ghost`. **The implementer re-greps each
before landing** (established shell-vs-bare rule). **Static-call trap:** if any relocated helper is
called statically (`Model_Space._x(...)`), it needs a `@staticmethod` shell
(`feedback_static_method_relocation_shell`) — none found at design time.

**Behavior-home bonus:** because **no state moves**, existing white-box asserts that read
`scene._opening_alignment` / `_opening_mirror_hinge` / `_opening_mirror_facing` / `_opening_feature_id`
(`test_opening_placement.py`, `test_opening_ribbon.py`) keep working **unchanged** — no test-repoint
churn (unlike slice 6, which moved DA state and had to repoint `test_design_area.py`).

### 2.5 `set_mode`, mode, `enter()` & `clear()` (unchanged behavior; Fork 2)

The `set_mode` opening block (`model_space.py:1183-1209`) is two-directional; both directions travel to
the controller (Fork 2 locked — the arm is in-concern):

- **`FeaturePlacementController.enter(template)`** — absorbs the entering-arm (`:1187-1207`) **verbatim**,
  operating on scene-side state via `self._scene.*`: adopt `current_template` (a `WallOpening` template,
  or build one from a bare feature-id string / `DEFAULT_FEATURE_FOR_TYPE["door"]`), set `tmpl._scene_ref`,
  mirror `feature_id`/`alignment`/`mirror_hinge`/`mirror_facing` onto the scene's `_opening_*` fields,
  and `self._scene.requestPropertyUpdate.emit(tmpl)`.
- **`FeaturePlacementController.clear(new_mode)`** — idempotent, guarded `if new_mode != "opening":`;
  absorbs the leaving-teardown (`:1208-1209`) — `self._clear_opening_ghost()` (controller-internal, via
  `self._scene` scene ops).
- **`set_mode` change:** replace the block at `:1183-1209` with:
  ```python
  if mode == "opening":
      self._feature_ctl.enter(template)
  self._feature_ctl.clear(mode)
  ```
  (The two are mutually exclusive on `mode`, so ordering is behavior-neutral; `clear` no-ops when
  `mode == "opening"`.) The `place_block` block below (`:1211+`) and all other mode blocks stay inline.
- **keyPress arrow block STAYS inline in core (`:6748-6760`)** — key routing is core (§5.2 + wall
  precedent). It toggles scene-side `_opening_mirror_hinge`/`_opening_mirror_facing` (behavior-home) and
  calls `self._sync_opening_state_to_template()` + `self._refresh_opening_ghost()` (now scene shells →
  controller). **Unchanged verbatim** except those two calls resolve through shells. The Space→cycle
  routing (`cycle_placement_ambiguity` `:2963-2965`) likewise stays core and calls the
  `_cycle_opening_alignment` shell.
- **`hasattr`-trap watch (`project_mixin_to_composition_hasattr_trap`):** grep for any
  `hasattr(self, "_opening_*")` / `hasattr(scene, "_opening_*")` guard. State stays scene-side, so state
  `hasattr`s are safe; method `hasattr`s (if any) resolve through the shell. Note `_clear_opening_ghost`
  and `_sync_opening_state_to_template` already use `getattr(self, "current_template"/"_opening_ghost",
  None)` internally — those become `getattr(self._scene, …)` and stay safe. Verify before landing.

## 3. Data flow (unchanged, relocated)

- **Live preview:** `mouseMoveEvent` (core) → `get_effective_position` (core) →
  `getattr(self, "_move_opening")(...)` → scene shell → controller `_move_opening`, which calls
  `self._find_wall_at`/`self._offset_along_wall`, builds/updates the low-opacity `_opening_ghost` from
  `current_template` + the `_opening_*` cycle state, and `ghost._reposition()`.
- **Commit-click:** `mousePressEvent` (core) → `getattr(self, "_press_opening")(...)` → scene shell →
  controller `_press_opening`: reject empty-space (`_find_wall_at is None`); else build the `WallOpening`
  from `current_template` (+ cycle state), `op._reposition()`, `wall.openings.append(op)`,
  `self._scene.addItem(op)`, `self._scene.push_undo_state()`. Legacy `door`/`window` modes route through
  the `_press_door`/`_press_window` shells → controller → `_press_opening`.
- **Cycle keys:** Space → core `cycle_placement_ambiguity` → `_cycle_opening_alignment` shell →
  controller (advance `_opening_alignment`, `_sync_opening_state_to_template`, `_refresh_opening_ghost`,
  emit instruction). ←/→/↑/↓ → core keyPress block toggles `_opening_mirror_*` → `_sync…`/`_refresh…`
  shells → controller.
- **Enter/teardown:** `set_mode("opening", template)` → `_feature_ctl.enter(template)` (arm + property
  panel); any other `set_mode` → `_feature_ctl.clear(mode)` (ghost torn down). `.fpd`/undo untouched
  (no serialization surface).

## 4. Testing

**Existing coverage is the parity net (must stay green = behavior preserved).** Run/keep green (exact
files confirmed by the implementer via grep): `test_opening_placement.py`, `test_opening_persistence.py`,
`test_opening_feature.py`, `test_opening_ribbon.py`, `test_opening_render.py`. **Behavior-home bonus:**
their white-box `scene._opening_*` asserts stay green **without repointing**.

**New file `tests/test_feature_placement_slice_parity.py`** (mirrors the slice-10 parity file):

- `test_backcompat_shells_feature` — the moved dispatch/core-keyPress/test-reached shells
  (`_press_opening`, `_press_door`, `_press_window`, `_move_opening`, `_move_door_window`,
  `_cycle_opening_alignment`, `_sync_opening_state_to_template`, `_refresh_opening_ghost`) are callable
  on the scene and delegate to `_feature_ctl`.
- `test_opening_place_on_wall_live` — posted `QMouseEvent` on a **shown+activated** view (real entry
  point; `QTest.mouseMove` is inert — post real events): enter `opening` mode with a door template,
  hover a wall (ghost appears), click → a `WallOpening` lands in `wall.openings` with the armed
  feature/cycle state; assert offset-along matches the click.
- `test_opening_empty_space_rejected_live` — click off any wall → no opening created, status prompt
  emitted.
- `test_opening_spacebar_cycles_alignment_live` — Space advances `_opening_alignment` through
  `OPENING_ALIGNMENTS` and the ghost + `current_template` reflect it.
- `test_opening_arrow_toggles_live` — ←/→ toggles `_opening_mirror_hinge`, ↑/↓ toggles
  `_opening_mirror_facing`; the placed opening carries the toggled state.
- `test_feature_enter_arms_template_live` — `set_mode("opening", door_template)` arms
  `current_template`, mirrors `_opening_*`, and emits `requestPropertyUpdate`; a bare feature-id string
  is adopted onto a fresh `WallOpening` template.
- **`clear()` RED-demo** — leave `opening` mode with a ghost showing; with `clear()`'s ghost-teardown
  stubbed to no-op the ghost strands on the canvas → RED; restored → green.

A pure relocation has no other red→green; parity tests are green before and after by design.

**Subagent implementers run only the targeted test files.** Full-suite green — read by **FAILED-diff vs
`main`** (`-v --tb=no`), not pass-count (`project_model_space_fullsuite_gate_native_crash`) — is a
Phase-6 orchestrator gate; no new failures beyond the documented pre-existing loci (the L72 trio, the
`main` failures at L281/L48, the catalogued sprinkler-db + underlay-manager-theme standalone failures,
the QPrinter-SEH + underlay-worker native-crash loci). Opening placement is live interaction → **manual
smoke test by the user** before wrap-up, with the exact `cd` + venv command and the branch name stated
(wrong-code-smoke-test hazard).

## 5. Slicing (revertable sub-commits, parity green at each step)

Branch: `refactor/model-space-feature-placement-slice`.

0. **C0 — Design doc + characterization/RED-demo test scaffolding** land on the branch, green.
1. **C1 — Host lookup + commit-click + legacy shims.** Create `feature_placement_controller.py` +
   `__init__` wiring (`self._feature_ctl = FeaturePlacementController(self)`). Move `_find_wall_at`,
   `_offset_along_wall` (bare), `_press_opening`, `_press_door`, `_press_window` (+ shells). Targeted
   tests green.
2. **C2 — Live preview / ghost + cycle behavior.** Move `_move_opening`, `_move_door_window`,
   `_refresh_opening_ghost`, `_clear_opening_ghost` (bare), `_cycle_opening_alignment`,
   `_sync_opening_state_to_template` (+ shells). Targeted tests green.
3. **C3 — `enter()`/`clear()` + `set_mode` wiring + RED-demo.** Add `enter(template)` (absorb the
   entering-arm verbatim) + `clear(new_mode)` (absorb the leaving-teardown); replace the `set_mode`
   block at `:1183-1209` with the two delegating calls. The keyPress arrow block + `cycle_placement_
   ambiguity` routing stay core (call the shells). RED-demo proven.
4. **C4 — Verify** targeted set; back-compat guard; `hasattr`-trap grep; static-call grep; full suite
   (Phase-6 FAILED-diff gate); **manual smoke**.
5. **C5 — Spec stamp.** Update `model-space-architecture.md` §5 (mark Feature placement landed in
   `FeaturePlacementController`; concern #7 — wall + feature done, room/floor/roof/gridline remain) +
   add the slice-11 bullet to §6; `last-verified`/`verified-commit`; add
   `feature_placement_controller.py` to `applies-to`. `SPEC-INDEX.md` — add
   `feature_placement_controller.py` to the Model_Space-composition row + a boundary note on the
   wall-room-floor row (opening placement now homed in the controller). Note the next concern-#7
   sub-slice (room OR floor/roof/gridline).

## 6. Acceptance criteria (relocation tier, from `model-space-architecture.md §8`)

- [ ] `.fpd` byte-parity + undo bytes unchanged — trivially met (zero serialization surface; openings
      live in `wall.to_dict`); asserted by a round-trip smoke on a real `.fpd` with placed door+window.
- [ ] Opening placement (hover-wall ghost → click place; Space cycle; ←/→/↑/↓ toggles; empty-space
      reject; door/window/blank) drives correctly via **posted events on a shown view**; results
      equivalent to `main`.
- [ ] `set_mode` opening logic (entering-arm + leaving-teardown) travels as `_feature_ctl.enter()` +
      idempotent `_feature_ctl.clear(new_mode)`; property-panel surface + ghost teardown identical;
      other mode blocks stay inline.
- [ ] Dispatch tables (`_PRESS_DISPATCH`/`_MOVE_DISPATCH`) untouched; no `_PREVIEW_DISPATCH`/
      `_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` entry added (opening has none). Legacy `door`/`window`
      shims relocate untouched (no retirement).
- [ ] Back-compat intact: scene shells keep dispatch/core-keyPress/`test_opening_ribbon.py` working;
      `_find_wall_at`/`_offset_along_wall`/`_clear_opening_ghost` move bare (grep-verified internal-only);
      any statically-called relocated helper has a `@staticmethod` shell; `current_template` +
      `_walls` stay scene-side.
- [ ] All `_opening_*` transient state remains scene attributes (behavior-home); white-box tests
      reading them stay green without repointing.
- [ ] No `hasattr(self, "_opening_*")` guard silently flips (grep verified).
- [ ] Full suite green (chunked); no new failures beyond the documented pre-existing loci (FAILED-diff
      vs `main`).
- [ ] `model-space-architecture.md` §5/§6 re-audited + stamped; `SPEC-INDEX.md` updated.

## 7. Governed-behavior cross-refs (Rule A — do not restate)

Behavior is owned by `docs/specs/wall-room-floor-system.md §7` (Opening = first-class Feature: placement
mode §7.6, reference frame/orientation §7.5, wall cut §7.7, level binding §7.9, persistence §7.11,
reposition contract §7.12; Feature model §7.2/§7.16). This slice is structural only; it moves code
without changing any behavior that spec governs.
