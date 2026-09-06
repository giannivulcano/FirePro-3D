# Wall-Placement Decomposition Slice — Design

> **Status:** design (2026-09-05). Implements **Slice 10** of the Model_Space decomposition
> governed by `docs/specs/model-space-architecture.md` (§5/§5.3/§8). This doc is the *how*; the
> *what* is locked by the governing spec + the Phase-2 grill + the slice-8/9 template
> (`2026-09-04-geometry-drawing-slice-design.md`, `2026-09-05-arc-polygon-slice-design.md`) — not
> relitigated. On landing, `model-space-architecture.md` §5/§6 is stamped in place — no parallel
> governing spec. Behavior is owned by `docs/specs/wall-room-floor-system.md` and the dynamic-input /
> `inferred-dimension-driven-placement.md §4` spec (Rule A — not restated here).
>
> **First slice of concern #7 (architectural placement).** Unlike slices 8/9 (which extended the
> existing `GeometryDrawingController`), this slice creates a **NEW** per-element collaborator
> (`WallPlacementController`). §5 of the governing spec sets the concern-#7 shape: per-element
> `*PlacementController`s, **wall first** (room-detection reads walls, so wall must extract before
> room/opening). This slice sets the pattern the room/opening/roof/gridline slices follow.

## 0. Locked scope (from the governing spec + grill — not relitigated)

- **Pure behavior-preserving relocation.** Zero behavior change, zero bug fixes.
- **NEW module + collaborator.** Move concern #7's **wall placement** methods from `model_space.py`
  into a new `firepro3d/wall_placement_controller.py` — `class WallPlacementController(scene)` (plain
  object, behavior home). Constructed in `Model_Space.__init__` as `self._wall_ctl =
  WallPlacementController(self)`, alongside the other `_*_ctl` collaborators (near `model_space.py:174`).
- **BEHAVIOR HOME — all wall STATE stays scene-side (§5.3).** Mirrors slices 8/9: the controller owns
  the *methods*, not the state. Every `_wall*` transient + the persisted `_walls`/`_next_wall_num`
  stay on the scene, read/written via `self._scene.*`. Forcing reasons: (a) the coordinator
  (`placement_input_coordinator.py`) reads `_wall_primitive` / `_wall_rect_rotating` / `_wall_rect_pivot`
  (slice-7 code); moving the state would churn freshly-landed slice-7 code — against the lowest-risk
  mandate. (b) `_walls` participates in BOTH serializers + undo-restore (§3.3 dual-serialization
  INVARIANT) and is read by external consumers (`_detect_room_boundary`, `_wall_spans_level`,
  serializers, tests).
- **Coordinator-owned schema/template/variant are OUT OF SCOPE, untouched (slice 7).**
  `_wall_schema_for_primitive` (`model_space.py:2637`) is already a thin scene shell → `self._plc.*`;
  `_get_wall_template` (`:2858`) is coordinator-owned; the `_PLACEMENT_VARIANTS` variant-cycling
  lambdas live in the coordinator. This slice does not touch them.
- **Cross-concern helpers STAY scene-side, untouched** (they read `self._walls` but belong to later
  concern-#7 slices), reached by their existing callers unchanged:
  - `_detect_room_boundary` (`:4716`) + `_wall_spans_level` (`:4703`) — **room concern**, called from
    `_press_room` (`:5042`). Extract with the future Room slice.
  - `_find_wall_at` (`:7162`) + `_offset_along_wall` (`:7169`) — **opening host-lookup**, called from
    door/window placement (`:6604/6617/6656/6660`). Extract with the future Opening slice.
- **Shared/generic helpers STAY scene-side** (used across concerns), reached via `self._scene.*`:
  `_make_ref_line`, `_constrain_angle`, `preview_pipe`/`preview_node`/`update_preview_node`,
  `get_effective_position`, `_geom_color_lw`, `publish_placement_state`/`clear_placement_state`,
  `_last_scene_pos`, `_active_view_scale`, `scale_manager`, `active_level`, `push_undo_state`,
  `_show_status`, `compute_wall_quad` (module import), `apply_category_defaults`.
- **Repoint nothing (dispatch/coordinator/keyPress/core-grip/external stay working via scene shells).**
  `_PRESS_DISPATCH`/`_MOVE_DISPATCH`/`_PREVIEW_DISPATCH`/`_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` stay
  **class-level on `Model_Space`, untouched**; resolution flows `getattr(self, handler)` → scene shell
  → controller.
- **Plain object, not `QObject`.** Signals via `self._scene.<sig>.emit`.
- **Zero serialization surface (confirmed).** No state moves off the scene → `.fpd` byte-identical +
  undo bytes unchanged are **trivially** met; the gate is **live parity + manual smoke** (pure
  interaction plumbing — the live-only bug class).
- **Deferred / explicitly out:** `_detect_room_boundary`/`_wall_spans_level` (room), `_find_wall_at`/
  `_offset_along_wall` (opening), the floor/roof/gridline placement branches (later slices — their
  `set_mode` blocks stay inline), any behavior change.

## 1. Goal

Lift concern #7's **wall placement** behavior out of `model_space.py` into a new
`WallPlacementController`, behavior-preservingly — the first of the per-element arch-placement
collaborators. Gives wall placement a named, isolation-testable home and shrinks the god-object's method
surface, while all wall STATE stays scene-side as the contract between the wall-placement behavior
(`_wall_ctl`) and the placement-input coordinator (`_plc`). Establishes the concern-#7 pattern for the
room/opening/roof/gridline slices that follow.

## 2. Architecture

### 2.1 Collaborator (NEW)

- **Module/Class:** `firepro3d/wall_placement_controller.py` — `class WallPlacementController` (plain
  object, behavior home). `__init__(self, scene)` stores `self._scene = scene` (mirrors
  `GeometryDrawingController`).
- **Construction:** `self._wall_ctl = WallPlacementController(self)` in `Model_Space.__init__` next to
  the other `_*_ctl` lines (~`model_space.py:174`).
- **Imports:** `WallSegment`, `compute_wall_quad` (from `.wall`); `QGraphicsLineItem`,
  `QGraphicsPathItem` (Qt widgets); `QPainterPath`, `QPen`, `QColor`, `QBrush` (QtGui, as needed by the
  moved bodies); `QPointF` (QtCore); `math`. The exact import set is finalized against the moved bodies
  during implementation (import only what the relocated methods use).

### 2.2 State — NONE owned by the controller (behavior-home, §5.3)

All stays on the scene, referenced via `self._scene`:

- **Persisted (BOTH serializers + undo + external readers):** `_walls`, `_next_wall_num`.
- **Line/polyline transient:** `_wall_anchor`, `_wall_chain_start`, `_wall_preview_line`,
  `_wall_preview_rect`.
- **Session-sticky (NOT cleared on mode exit):** `_wall_alignment`, `_wall_primitive`. (Written by
  `_set_wall_primitive` / `cycle_placement_variant`; read by the coordinator.)
- **Coordinator-owned (untouched):** `_wall_template`.
- **Rect transient:** `_wall_rect_anchor`, `_wall_rect_preview`, `_wall_rect_thickness_preview`,
  `_wall_rect_from_center`, `_wall_rect_rotating`, `_wall_rect_sized_pt1`, `_wall_rect_sized_pt2`,
  `_wall_rect_pivot`, `_wall_rect_ref_line0`, `_wall_rect_ref_lineA`.
- **Shared plumbing / generic helpers / render scratch:** `preview_pipe`, `preview_node`,
  `update_preview_node`, `_last_scene_pos`, `_active_view_scale`, `mode`, `get_effective_position`,
  `scale_manager`, `active_level`, `push_undo_state`, `_show_status`, `publish_placement_state`/
  `clear_placement_state`, `_make_ref_line`, `_constrain_angle`, `_geom_color_lw`,
  `requestPropertyUpdate` (signal) — all reached via `self._scene.*`.

### 2.3 Methods moved into the controller (bodies operate on `self._scene.*`)

**~17 methods (line counts at design time):**

- **Dispatch routers:** `_press_wall_router` (`:5672`), `_move_wall_router` (`:5678`).
- **Line/polyline primitive:** `_press_wall` (`:5756`), `_move_wall` (`:3751`).
- **Rect primitive:** `_press_wall_rect` (`:5815`), `_move_wall_rect` (`:3824`),
  `_advance_wall_rect_to_rotate_step` (`:5861`), `_commit_wall_rect_rotated` (`:6028`),
  `_wall_rect_rotation_angle_to` (`:5853`), `_update_wall_rect_ref_lines` (`:3508`),
  `_clear_wall_rect_ref_lines` (`:3499`).
- **HUD applier:** `_apply_wall_dynamic_input` (`:5730`).
- **Variant / alignment:** `_set_wall_primitive` (`:5662`), `_cycle_wall_alignment` (`:3049`).
- **Post-commit / grip reaction:** `_auto_join_wall` (`:7120`), `_propagate_wall_endpoint` (`:3220`).

**Body rewrites (mechanical, mirroring slice 8/9):** `self.<sceneOp>` (`addItem`/`removeItem`/`views`/
`update_preview_node`/`clearSelection`/`selectedItems`) → `self._scene.<sceneOp>`; each state attr in
§2.2 → `self._scene.<same>`; generic helpers (`_make_ref_line`, `_constrain_angle`, `_geom_color_lw`) →
`self._scene.<same>`; `self.<signal>.emit` → `self._scene.<signal>.emit`; `self._show_status`/
`push_undo_state`/`publish_placement_state`/`clear_placement_state`/`get_effective_position`/
`_last_scene_pos`/`_active_view_scale`/`scale_manager`/`active_level`/`mode` → `self._scene.<same>`.
**Internal calls to still-moving siblings stay `self.<method>`** (e.g. `_press_wall_router` →
`self._press_wall`/`self._press_wall_rect`; `_move_wall_rect` → `self._wall_rect_rotation_angle_to`/
`self._update_wall_rect_ref_lines`; `_commit_wall_rect_rotated` → `self._auto_join_wall`/
`self._clear_wall_rect_ref_lines`; `_press_wall` → `self._auto_join_wall`;
`_advance_wall_rect_to_rotate_step` → `self._clear_wall_rect_ref_lines`/`self._update_wall_rect_ref_lines`).

**Cross-concern calls stay `self._scene.<method>`:** none of the moved methods call
`_detect_room_boundary`/`_find_wall_at`/`_offset_along_wall` (verified — those are called by room/opening
placement, not by wall placement). If the implementer's grep finds any such call, it routes through
`self._scene.*`.

### 2.4 Delegation contract — scene-side shells vs bare move

**Scene-side shells REQUIRED** (referenced by a dispatch table, the coordinator, `keyPressEvent`, the
core grip path, or external/tests — the implementer greps each; the known callers are listed):

- **Dispatch-resolved (press/move):** `_press_wall_router`, `_move_wall_router` (registered in
  `_PRESS_DISPATCH["wall"]`/`_MOVE_DISPATCH["wall"]`); `_press_wall`, `_move_wall`, `_move_wall_rect`
  (also called white-box by `test_wall_placement_workflow.py:287/310`).
- **Applier-resolved** (`getattr(self._scene, _APPLIER_FOR_MODE["wall"])`): `_apply_wall_dynamic_input`.
- **Coordinator-called** (`placement_input_coordinator._apply_current_variant`): `_set_wall_primitive`.
- **Shared-cycle-called** (`cycle_placement_ambiguity`, shared by pipe/wall/opening):
  `_cycle_wall_alignment`.
- **Core-grip-path-called** (`model_space.py:3215`, inside the grip-move handler — the irreducible-core
  grip mechanism): `_propagate_wall_endpoint`. **Pure forward** — the `_tools._solve_constraints(gi)` +
  viewport-update at `:3216` stay in the core grip handler, so the shell needs no constraint context.

**Move WITHOUT a shell** unless a whole-repo caller grep finds an external reference (internal-only
siblings): `_press_wall_rect`, `_advance_wall_rect_to_rotate_step`, `_commit_wall_rect_rotated`,
`_auto_join_wall`, `_wall_rect_rotation_angle_to`, `_update_wall_rect_ref_lines`,
`_clear_wall_rect_ref_lines`. **The implementer greps every one** (the established shell-vs-bare rule) —
several are plausibly hit by `test_wall_*.py` white-box tests, which would require a shell (or a
repointed test assert). **Static-call trap:** if any relocated helper is called statically
(`Model_Space._x(...)`), it needs a `@staticmethod` shell (`feedback_static_method_relocation_shell`).

**Behavior-home bonus:** because **no state moves**, existing white-box asserts that read
`scene._wall_anchor` / `_wall_primitive` / `_wall_rect_rotating` (e.g.
`test_wall_placement_workflow.py`) keep working **unchanged** — no test-repoint churn (unlike slice 6,
which moved DA state and had to repoint `test_design_area.py` to `scene._spr_ctl._da_*`).

### 2.5 Dispatch, mode & `clear()` (unchanged behavior)

- **Dispatch tables + `_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` untouched** (class-level on `Model_Space`).
  Resolution flows `getattr(self, handler)` → scene shell → controller (mouse) and
  `getattr(self._scene, applier_name)` → scene shell → controller (HUD).
- **`WallPlacementController.clear(new_mode)`** — idempotent, guarded `if new_mode != "wall":`. It
  absorbs **both** non-contiguous `set_mode` wall blocks **verbatim**:
  - the line/polyline block (`model_space.py:1131-1142`): null `_wall_anchor`/`_wall_chain_start`,
    remove+null `_wall_preview_line`/`_wall_preview_rect`;
  - the rect block (`:1163-1177`): null `_wall_rect_anchor`, `_wall_rect_rotating=False`,
    null `_wall_rect_sized_pt1/_pt2`/`_wall_rect_pivot`, call `self._clear_wall_rect_ref_lines()`,
    remove+null `_wall_rect_preview`/`_wall_rect_thickness_preview`.

  All operating on scene-side state via `self._scene.*`. `_wall_alignment` and `_wall_primitive` are
  **NOT** cleared (session-sticky — preserved exactly as today).
- **`set_mode` change:** delete the two wall blocks (`:1131-1142` and `:1163-1177`); add
  `self._wall_ctl.clear(mode)` next to `self._geom_ctl.clear(mode)` at `:1052`. **The floor block
  (`:1143-1162`) between them stays inline** (floor is a later concern-#7 slice); the roof block
  (`:1178+`) and text/dimension/offset/etc. stay inline.
- **`hasattr`-trap watch (`project_mixin_to_composition_hasattr_trap`):** grep for any
  `hasattr(self, "_wall_*")` / `hasattr(scene, "_wall_*")` guard that would silently flip now that the
  methods (not state) moved. State stays scene-side, so state `hasattr`s are safe; method `hasattr`s
  (if any) resolve through the shell. Verify before landing.

## 3. Data flow (unchanged, relocated)

- **Mouse placement:** `mousePressEvent`/`mouseMoveEvent` (core) resolve the snapped point via
  `get_effective_position` (core), then `getattr(self, "_press_wall")(...)` → scene shell →
  `_press_wall_router` (controller) → per-primitive handler (`_press_wall` line / `_press_wall_rect`
  rect), which reads/writes scene-side transient state + shared `preview_*`, and on commit builds the
  `WallSegment`(s), appends to `self._scene._walls`, runs `self._auto_join_wall`, then
  `self._scene.push_undo_state()`.
- **HUD typed commit:** HUD Enter → `scene._on_dynamic_input_committed` (coordinator) →
  `getattr(self._scene, _APPLIER_FOR_MODE["wall"])(geometry)` → scene applier shell →
  `_apply_wall_dynamic_input` (controller), which routes the typed point through the press handlers
  (line) or advance/commit (rect rotate step); returns bool (D2 refusal gating unchanged).
- **Variant / alignment:** coordinator `_apply_current_variant` → scene shell `_set_wall_primitive` →
  controller (sets `self._scene._wall_primitive` + rect-from-center flag); `cycle_placement_ambiguity`
  → scene shell `_cycle_wall_alignment` → controller (cycles `_wall_alignment`, updates instruction +
  forces preview redraw).
- **Grip-drag endpoint propagation:** core grip-move handler (`:3208-3216`) calls
  `gi.apply_grip(...)` then `self._propagate_wall_endpoint(gi, old, new)` → scene shell → controller
  (scans `self._scene._walls`, moves coincident endpoints); the core handler then runs
  `self._tools._solve_constraints(gi)` + viewport update (unchanged, stays core).
- **Teardown:** `set_mode` → `self._wall_ctl.clear(mode)` covers line/polyline + rect; floor/roof/
  text/dimension inline; `.fpd`/undo untouched (no serialization surface).

## 4. Testing

**Existing coverage is the parity net (must stay green = behavior preserved).** Run/keep green (exact
files confirmed by the implementer via grep): `test_wall_placement_workflow.py`, `test_wall_align.py`,
`test_wall_centered.py`, `test_wall_joined_endpoints.py`, `test_wall_room_floor.py`,
`test_wall_centerline.py`, `test_wall_grip_ctrl.py`, `test_wall_ribbon.py`, `test_dynamic_input_seam.py`.
**Static-call trap check:** re-run any suite that calls a relocated helper statically (grep first — none
found at design time, but the implementer confirms).

**New file `tests/test_wall_placement_slice_parity.py`** (mirrors the slice-8/9 parity files):

- `test_backcompat_shells_wall` — the moved dispatch/coordinator/keyPress/core-grip/test-reached shells
  (`_press_wall`, `_press_wall_router`, `_move_wall`, `_move_wall_router`, `_move_wall_rect`,
  `_apply_wall_dynamic_input`, `_set_wall_primitive`, `_cycle_wall_alignment`,
  `_propagate_wall_endpoint`) are callable on the scene and delegate to `_wall_ctl`.
- `test_wall_line_draw_live` — posted `QMouseEvent`/`QKeyEvent` on a **shown+activated** view (real
  entry point; `QTest.mouseMove` is inert — post real events): 2-click line wall in the default
  variant; assert the committed `WallSegment` endpoints/alignment match the mouse path and it lands in
  `_walls`; a second wall snapping to the first triggers `_auto_join_wall` (shared endpoint mitred).
- `test_wall_polyline_chain_live` — polyline primitive: N-click chain with a final click within the
  close-loop tolerance of `_wall_chain_start`; assert the loop closes (last endpoint == chain start)
  and each segment lands in `_walls`.
- `test_wall_rect_draw_live` — rect primitive 3-step (anchor → size → rotate) incl. Ctrl-constrain
  during rotate; assert 4 `WallSegment`s committed with the rotated-rect corners, each auto-joined, and
  continuous placement re-arms (`_wall_rect_anchor` reset).
- `test_wall_hud_typed_commit_live` — type the endpoint at step 1 (line) + type the rotate angle at
  step 2 (rect); assert geometry equivalent to the mouse path (applier path through the coordinator →
  scene shell → controller).
- `test_wall_endpoint_propagation_live` — build two walls sharing a corner, grip-drag the shared
  endpoint; assert the coincident endpoint on the other wall follows (via `_propagate_wall_endpoint`).
- **`clear()` RED-demo** — leaving `wall` mode mid-placement (line: `_wall_anchor` set + preview
  showing; rect: rotate armed with ref-lines) with `clear()`'s wall block stubbed to no-op leaves a
  stale preview/ref-line/anchor → RED; restored → green.

A pure relocation has no other red→green; parity tests are green before and after by design.

**Subagent implementers run only the targeted test files.** Full-suite green — read by **FAILED-diff vs
`main`** (`-v --tb=no`), not pass-count (`project_model_space_fullsuite_gate_native_crash`) — is a
Phase-6 orchestrator gate; no new failures beyond the documented pre-existing loci (the L72 trio, the
`main` failures at L281/L48, the catalogued sprinkler-db + underlay-manager-theme standalone failures,
the QPrinter-SEH + underlay-worker native-crash loci). Wall placement is live interaction → **manual
smoke test by the user** before wrap-up, with the exact `cd` + venv command and the branch name stated
(wrong-code-smoke-test hazard).

## 5. Slicing (revertable sub-commits, parity green at each step)

Branch: `refactor/model-space-wall-placement-slice`.

0. **C0 — Design doc + characterization/RED-demo test scaffolding** land on the branch, green.
1. **C1 — Line/polyline primitive.** Create `wall_placement_controller.py` + `__init__` wiring
   (`self._wall_ctl = WallPlacementController(self)`). Move `_press_wall_router`, `_move_wall_router`,
   `_press_wall`, `_move_wall`, `_auto_join_wall`, `_propagate_wall_endpoint`, `_cycle_wall_alignment` +
   their scene shells. Targeted tests green.
2. **C2 — Rect primitive.** Move `_press_wall_rect`, `_move_wall_rect`,
   `_advance_wall_rect_to_rotate_step`, `_commit_wall_rect_rotated`, `_wall_rect_rotation_angle_to`,
   `_update_wall_rect_ref_lines`, `_clear_wall_rect_ref_lines` (+ shells per grep). Targeted tests green.
3. **C3 — HUD applier + variant + `clear()`/`set_mode` wiring + RED-demo.** Move
   `_apply_wall_dynamic_input`, `_set_wall_primitive` (+ shells). Add
   `WallPlacementController.clear(new_mode)` absorbing both `set_mode` wall blocks verbatim; delete them
   from `set_mode`; add `self._wall_ctl.clear(mode)` at `:1052`. Floor/roof/text/dimension stay inline.
   RED-demo proven.
4. **C4 — Verify** targeted set; back-compat guard; `hasattr`-trap grep; static-call grep; full suite
   (Phase-6 FAILED-diff gate); **manual smoke**.
5. **C5 — Spec stamp.** Update `model-space-architecture.md` §5 (mark wall landed in
   `WallPlacementController`; concern #7 arch-placement STARTED — wall done, room/opening/roof/gridline
   remain) + add the slice-10 bullet to §6; `last-verified`/`verified-commit`; add
   `wall_placement_controller.py` to `applies-to`. `SPEC-INDEX.md` — add `wall_placement_controller.py`
   to the Model_Space-composition row's primary modules + the pipe-placement/wall-room-floor rows if a
   boundary note is warranted. Note the next concern-#7 sub-slice (room OR opening — room-detection
   already reads walls, so either can follow).

## 6. Acceptance criteria (relocation tier, from `model-space-architecture.md` §8)

- [ ] `.fpd` byte-parity + undo bytes unchanged — trivially met (zero serialization surface); asserted
      by a round-trip smoke check on a real `.fpd` with line-drawn **and** rect-drawn walls.
- [ ] Wall line (2-click), polyline (close-loop chain), and rect (3-step incl. Ctrl-rotate) drive
      correctly via **posted events on a shown view**, both mouse and HUD-typed; results equivalent to
      `main`. Auto-join + endpoint-propagation behave identically.
- [ ] `set_mode` wall teardown (both non-contiguous blocks) travels as part of the single idempotent
      `WallPlacementController.clear(new_mode)`; floor/roof/text/dimension branches stay inline unchanged;
      `_wall_alignment`/`_wall_primitive` remain session-sticky (not cleared).
- [ ] Dispatch tables + `_APPLIER_FOR_MODE`/`_SCHEMA_FOR_MODE` untouched; coordinator schema/template/
      variant paths unchanged; the coordinator's reads of scene-side wall state
      (`_wall_primitive`/`_wall_rect_rotating`/`_wall_rect_pivot`) unchanged.
- [ ] Back-compat intact: scene shells keep dispatch/coordinator/keyPress/core-grip/`main.py`/tests
      working; any statically-called relocated helper has a `@staticmethod` shell; `_detect_room_boundary`/
      `_wall_spans_level`/`_find_wall_at`/`_offset_along_wall` stay scene-side untouched.
- [ ] Persisted lists (`_walls`/`_next_wall_num`) + all `_wall*` transient state remain scene
      attributes (behavior-home model); white-box tests reading them stay green without repointing.
- [ ] No `hasattr(self, "_wall_*")` guard silently flips (grep verified).
- [ ] Full suite green (chunked); no new failures beyond the documented pre-existing loci (FAILED-diff
      vs `main`).
- [ ] `model-space-architecture.md` §5/§6 re-audited + stamped; `SPEC-INDEX.md` updated.

## 7. Governed-behavior cross-refs (Rule A — do not restate)

Behavior is owned by `docs/specs/wall-room-floor-system.md` (wall placement workflow, primitives,
alignment, miter/auto-join, endpoint propagation) and the dynamic-input /
`inferred-dimension-driven-placement.md §4` spec (HUD lifecycle, step-aware schemas, seed/publish/
resolve, variant cycling). This slice is structural only; it moves code without changing any behavior
those specs govern.
