# Pipe/Node Network Decomposition Slice — Design

> **Status:** design (2026-09-02). Implements Slice 5 of the Model_Space decomposition
> governed by `docs/specs/model-space-architecture.md` (§5/§8). This doc is the *how*; the
> *what* was locked in a grill (see §0). On landing, `model-space-architecture.md` §5 is
> stamped in place — no parallel governing spec is created. Behavior is owned by
> `docs/specs/pipe-placement-methodology.md` (Rule A — not restated here).

## 0. Locked scope (from grill — not relitigated here)

- **Pure behavior-preserving relocation.** Zero behavior change, zero bug fixes.
- **`node_start_pos` split DEFERRED** — the attr is overloaded (`Node` in pipe mode, `QPointF`
  in move/paste) and stays **on the scene**; the controller reads/writes it via
  `self._scene.node_start_pos`. Its dedicated P3 TODO ("Split `node_start_pos`") stays filed and
  is *unblocked* (not entangled) by this slice. `_pipe_node_was_new` stays on the scene too.
- **Fittings ride with pipe** (`_apply_fitting_dm_colors` + the `.fitting.update()` orchestration
  inside pipe ops move). **Sprinklers stay** (concern #2; the pipe concern only *reads*
  `node.sprinkler`). `add_sprinkler` does not move.
- **Storage / undo / serialization stay on the scene.** `self.sprinkler_system`,
  `_capture_network`/`_restore_network` (undo "god-glue", concern #4), and `scene_io` +
  `network_codec` are untouched; they reach the controller only through the public shells.
- **Shared preview items stay** — `preview_pipe` / `preview_node` are used by every placement
  mode; they stay on the scene, controller references via `self._scene.preview_*`.
- **`complete_confirmation` stays on the scene** — it is a *general* confirmation router
  (`mirror_delete`, array/paste delete-originals, pipe `elev_mismatch_*`). Only its pipe branches
  delegate to the controller. `_pending_confirm_data` is shared confirmation state → stays.
- **Full back-compat, repoint nothing:** the 6 public methods (`add_pipe`, `delete_pipe`,
  `find_nearby_node`, `find_or_create_node`, `remove_node`, `split_pipe`) + the new
  `cancel_pipe_placement()` keep working for 25+ test sites, the paste path, `scene_tools`
  mirror, and both deserialize paths.
- **Deferred / explicitly out:** all pipe-spec bugs B1–B12; the `node_start_pos` split;
  caller repointing; `main.py` decomposition (beyond the `cancel_pipe_placement` reach-in
  cleanup); the sprinkler/Design-Area concern; any undo/serialization rewrite; the
  dispatch-plugin generalization; the `_other_end` / `PolylineItem.last_point` cleanups.

## 1. Goal

Lift the pipe/node network concern (~22 methods + the pipe-only Tab-cycling transient state + the
fitting-update orchestration + the pipe press/move placement logic) out of `model_space.py`
(10,699 lines) into a scene-referencing collaborator `PipeNetworkController(scene)`,
behavior-preservingly, with `.fpd` byte-parity and undo bytes unchanged. This is decomposition-map
concern #1 ("Hard" — universal scene mutation + undo coupling), tractable now because slices 2–4
already unified the serializers (`network_codec`) and composed out `SceneTools`, and because the
grill fenced the shared surfaces to stay on the scene.

## 2. Architecture

### 2.1 New collaborator

- **Module:** `firepro3d/pipe_network_controller.py`
- **Class:** `PipeNetworkController` — a **plain object** (not a `QObject`), mirroring
  `SceneTools(scene)` and `UnderlayController(scene)`. All signals it needs
  (`instructionChanged`, `pipeNodeHighlight`, `confirmRequested`, `warningIssued`,
  `requestPropertyUpdate`) stay defined on the scene and are emitted via `self._scene.<sig>.emit(...)`,
  so no thread affinity is introduced.
- **Constructed** in `Model_Space.__init__` (after `sprinkler_system` exists, before dispatch is
  first used): `self._pipe_ctl = PipeNetworkController(self)`.

### 2.2 State owned by the controller

| Attr | Role |
|---|---|
| `self._tab_candidates` / `_tab_index` / `_tab_pos` | pipe Tab-cycle transient (was `_pipe_tab_candidates` / `_pipe_tab_index` / `_pipe_tab_pos`) |
| `self._scene` | back-ref to `Model_Space` (scene-graph mutation + signal emission are universal — seam §3.1) |

**Not owned (stay on the scene, referenced via `self._scene`):** `sprinkler_system`,
`node_start_pos`, `_pipe_node_was_new`, `preview_pipe`, `preview_node`, `_pending_confirm_data`,
`current_template` (the active placement template passed by `set_mode`), `_level_manager`.

### 2.3 Delegation contract (on `Model_Space`)

- **6 public shells** — each `return self._pipe_ctl.<same>(...)`:
  `add_pipe`, `delete_pipe`, `split_pipe`, `find_nearby_node`, `find_or_create_node`,
  `add_node`, `remove_node`, `find_nearby_candidates`. (All external callers + `network_codec`
  deserialize + `scene_io` + paste + mirror unchanged.)
- **`_apply_fitting_dm_colors`** moves to the controller as a `@staticmethod`; the scene keeps a
  `@staticmethod` shell `Model_Space._apply_fitting_dm_colors = staticmethod(...)` **only if** a
  static-style caller (`Model_Space._apply_fitting_dm_colors(f)`) exists — audit shows all 4 call
  sites are instance-style (`self._apply_fitting_dm_colors`), so an instance shell suffices, but a
  staticmethod shell is used defensively per the `static-method-relocation-shell` memory. `_restore_network`
  (stays on scene) calls it via the shell.
- **New:** `Model_Space.cancel_pipe_placement() -> bool` → `return self._pipe_ctl.cancel_placement()`.
  Encapsulates `main._on_escape`'s pipe mid-chain cancel (orphan-delete a newly-created start node,
  reset `node_start_pos`/`_pipe_node_was_new`, hide `preview_*`, emit `instructionChanged`); returns
  `True` when it handled a cancel. `main._on_escape` becomes:
  `if self.scene.mode == "pipe" and self.scene.cancel_pipe_placement(): return`.
- Tab-cycle accessors the view/keypress path reads (`_pipe_tab_candidates` etc.) get **read shells**
  if any external/keypress site touches them; audit shows they're only touched inside pipe methods →
  no external shell needed, but the scene-side keypress Tab handler (if any) calls
  `self._pipe_ctl.cycle_tab()`.

### 2.4 Methods moved whole into the controller

Node CRUD: `find_nearby_node`, `find_nearby_candidates`, `find_or_create_node`, `add_node`,
`remove_node`.
Pipe create/delete/split: `add_pipe`, `delete_pipe`, `split_pipe`, `_split_vertical_pipe`.
Geometry corrections: `_validate_4th_branch`, `_would_backtrack`, `_would_backtrack_at`,
`_try_extend_collinear`, `_convert_45_elbow_to_wye`.
Vertical stack: `_compute_template_z_pos`, `_make_intermediate_node`, `_make_intermediate_node_for_n2`,
`_create_vertical_connection`, `_find_or_split_vertical_at_z`.
Tab cycling: `_update_pipe_tab_candidates`, `_emit_pipe_tab_readout`.
Fitting: `_apply_fitting_dm_colors` (staticmethod).
Placement logic: the **bodies** of `_press_pipe` and `_move_pipe` → `press_pipe(...)` / `move_pipe(...)`
on the controller (see §2.5).

Body rewrites (mechanical): `self.<sceneOp>` (addItem/removeItem/createItemGroup/views/update) →
`self._scene.<sceneOp>`; `self.sprinkler_system` → `self._scene.sprinkler_system`;
`self.node_start_pos` / `_pipe_node_was_new` / `preview_pipe` / `preview_node` /
`_pending_confirm_data` / `current_template` / `_level_manager` → `self._scene.<same>`;
`self.<signal>.emit(...)` → `self._scene.<signal>.emit(...)`; `self._show_status` →
`self._scene._show_status`; internal calls to still-moving siblings stay `self.<method>`; calls to
methods that stay on the scene (e.g. `push_undo_state`, `apply_category_defaults`,
`_get_active_view_range`, `add_sprinkler`) become `self._scene.<method>`.

### 2.5 Dispatch & mode

- `_press_pipe` / `_move_pipe` **stay as scene-side forwarders** so `_PRESS_DISPATCH` (`"pipe" →
  "_press_pipe"`, line 6092) and `_MOVE_DISPATCH` (`"pipe" → "_move_pipe"`, line 4832) resolve via
  `getattr(self, name)` untouched. Each forwarder passes its args straight through:
  `def _press_pipe(self, *a): return self._pipe_ctl.press_pipe(*a)`. The `_PREVIEW_DISPATCH` has no
  pipe entry (pipe manages `preview_pipe` inline in `move_pipe`) — unchanged.
- `complete_confirmation` **stays on the scene** (general router). Its `elev_mismatch_start` /
  `elev_mismatch_end` branch bodies move to `self._pipe_ctl.resume_elev_mismatch(which, result)`;
  the `mirror_delete` / array branches stay put.
- `set_mode`'s pipe teardown splits by ownership:
  - **Tab-cycle reset** (model_space 987–989) → `PipeNetworkController.clear()`.
  - **Orphan-delete + `node_start_pos`/`_pipe_node_was_new` reset** (1047–1054) → also
    `PipeNetworkController.clear()` (it operates on `self._scene.node_start_pos`, preserving the
    `isinstance(..., Node)` guard so move/paste's `QPointF` is never orphan-deleted).
  - **`preview_*.hide()`** (1027–1028) stays in `set_mode` (shared teardown for all modes).
  `set_mode` calls `self._pipe_ctl.clear()` in the non-`"pipe"` branch. `clear()` is idempotent.

### 2.6 The cancel/confirm/teardown map (three paths, unchanged behavior)

| Path | Trigger | After slice |
|---|---|---|
| `main._on_escape` (main.py 4054) | Esc mid-chain, stay in pipe mode | `scene.cancel_pipe_placement()` → `ctl.cancel_placement()` |
| `set_mode` teardown (1047–1054, 987–989) | mode change | `ctl.clear()` (idempotent; keeps `isinstance` guard) |
| `keyPressEvent` Esc reset (~10136) | scene-level Esc | stays internal; nulls `self.node_start_pos` (scene attr) |
| `complete_confirmation` elev branches (6211+) | dialog result | `ctl.resume_elev_mismatch(...)` |

## 3. Data flow (unchanged, relocated)

- **Placement (press):** `mousePressEvent` → dispatch `getattr(self, "_press_pipe")` → scene
  forwarder → `ctl.press_pipe(event, pos, snapped, item_under, node_under, pipe_under)`; the body
  runs exactly as today (find/create/split start node, elevation-mismatch → `confirmRequested`
  emit + `_pending_confirm_data` stash, backtrack/limit validation, `add_pipe`, collinear-extend,
  45°→wye, chain advance) but reads/writes shared state via `self._scene`.
- **Placement (move):** `_move_pipe` forwarder → `ctl.move_pipe(event, snapped)` → Tab-candidate
  sync + `preview_pipe`/`preview_node` update via `self._scene.preview_*`.
- **Create/delete/split:** `add_pipe`/`delete_pipe`/`split_pipe` shells → controller; controller
  mutates `self._scene.sprinkler_system.{nodes,pipes}` and updates fittings. Identical order.
- **Undo:** `_capture_network`/`_restore_network` stay on the scene; restore calls
  `self.add_pipe(...)` (shell → controller) and `self._apply_fitting_dm_colors(...)` (shell) exactly
  as today. Undo bytes unchanged.
- **Save/load:** `scene_io` + `network_codec` untouched; deserialize calls `scene.add_pipe(...)`
  (shell). `.fpd` byte-identical.

## 4. Testing

**Characterization suite (written + green on the branch BEFORE C1 — the relocation safety net).**
Leverage existing coverage (`test_node_snap.py`, `test_pipe_data_integrity.py`,
`test_serializer_parity.py`, `test_move_paste_ghost.py`, `test_dynamic_input_*`), and add the gaps:

- `test_pipe_file_byte_parity` — load a real `.fpd` with a pipe/node network → save → byte-identical
  payload.
- `test_pipe_survives_undo_redo` — build a multi-segment network (incl. a tee + a riser), snapshot,
  undo→redo, assert identical nodes/pipes/fittings/connectivity/positions.
- `test_pipe_placement_live` — posted `QMouseEvent`s on a shown+activated view: click start (preview
  appears), move (preview follows + label), click end (pipe created), continue chain, double-click
  terminates (real entry point, not handler calls).
- `test_pipe_cancel_placement` — start a segment (new start node), `scene.cancel_pipe_placement()`
  (and a posted Esc via `main._on_escape`), assert the orphan start node is removed, mode stays
  `"pipe"`, `node_start_pos is None`.
- `test_pipe_geometry_corrections` — characterize collinear-extend (merge), 45°→wye (stub added),
  `split_pipe` (junction + 2 halves), backtrack block (duplicate refused), 4th-branch validation
  (perpendicular-only cross).
- `test_pipe_backcompat` — all 6 public shells + `cancel_pipe_placement` callable on the scene;
  the paste path (`paste_items`) and `scene_tools` mirror still create pipes/nodes.

**RED-demo (behavior-regression proof) — reserved for the `clear()` migration only:** stub
`PipeNetworkController.clear()` to a no-op and confirm `test_pipe_cancel_placement` (orphan-not-
cleaned) goes RED; restore → green. A pure relocation has no other red→green; the parity tests are
green before and after by design.

**Subagent implementers run only the targeted pipe test files.** Full-suite green (chunked per the
long-run-flake memory; no new failures beyond the pre-existing L72/L84 trio) is a Phase-6 gate run
by the orchestrator. Pipe placement is live-interaction-heavy → **manual smoke test by the user**
before wrap-up.

## 5. Slicing (revertable sub-commits, parity green at each step)

Branch: `refactor/model-space-pipe-slice`.

0. **C0 — Characterization tests** land on the branch, green (the safety net).
1. **C1 — Scaffold.** New `pipe_network_controller.py` (controller owning the Tab-cycle attrs +
   `_scene` back-ref); `__init__` builds `self._pipe_ctl`; move the Tab-cycle attrs' init into the
   controller. No method bodies moved yet. Targeted tests green.
2. **C2 — Move methods** in batches, each relocating bodies + adding shells/forwarders, targeted
   tests green after each:
   - **C2a — node CRUD + fitting colour:** `find_nearby_node`, `find_nearby_candidates`,
     `find_or_create_node`, `add_node`, `remove_node`, `_apply_fitting_dm_colors`.
   - **C2b — create/delete/split:** `add_pipe`, `delete_pipe`, `split_pipe`, `_split_vertical_pipe`.
   - **C2c — geometry corrections + vertical stack:** `_validate_4th_branch`, `_would_backtrack`,
     `_would_backtrack_at`, `_try_extend_collinear`, `_convert_45_elbow_to_wye`,
     `_compute_template_z_pos`, `_make_intermediate_node`, `_make_intermediate_node_for_n2`,
     `_create_vertical_connection`, `_find_or_split_vertical_at_z`.
   - **C2d — placement logic + Tab-cycle methods:** `_press_pipe`/`_move_pipe` bodies →
     `press_pipe`/`move_pipe` (scene forwarders); `_update_pipe_tab_candidates`/`_emit_pipe_tab_readout`;
     `complete_confirmation` elev branches → `ctl.resume_elev_mismatch`.
3. **C3 — `cancel_pipe_placement()` + `clear()` + set_mode** wiring, `main._on_escape` reach-in
   cleanup (same commit), with the RED-demo.
4. **C4 — Verify** targeted set complete; confirm the back-compat guard; run full suite (Phase-6).
5. **C5 — Spec §5 stamp** (`last-verified` / `verified-commit`); record `PipeNetworkController` in
   §5's collaborator list (supersedes the provisional `PipeNetworkManager` name).

## 6. Acceptance criteria (relocation tier, from `model-space-architecture.md` §8)

- [ ] File byte-parity: real `.fpd` (pipe network) → load → save → byte-identical payload.
- [ ] Undo/redo leaves nodes/pipes/fittings/connectivity identical vs `main` (bytes unchanged).
- [ ] Pipe tool drives correctly via posted events on a shown view; mid-chain cancel removes the
      orphan start node and stays in pipe mode.
- [ ] `set_mode` teardown travels as an idempotent `PipeNetworkController.clear()` (orphan-delete +
      Tab reset), preserving the `isinstance(node_start_pos, Node)` guard.
- [ ] `main._on_escape` reach-ins converted to `scene.cancel_pipe_placement()` in the same commit.
- [ ] No moved method retains a hidden `self`/side-effect the shell doesn't cover.
- [ ] Back-compat intact: 6 shells + `cancel_pipe_placement` + `_apply_fitting_dm_colors` for
      25+ tests, paste, mirror, both deserialize paths.
- [ ] Full suite green (chunked); no new failures beyond the pre-existing trio.
- [ ] `model-space-architecture.md` §5 re-audited + stamped.

## 7. Governed-behavior cross-refs (Rule A — do not restate)

Behavior is owned by `pipe-placement-methodology.md` (placement, geometry corrections, elevation,
fittings, templates) and `sprinkler-system-components.md` (the `SprinklerSystem` container +
sprinklers, out of scope here). Serialization currently lives in `architecture/io.md` +
`network_codec.py`. This slice is structural only; it moves code without changing any behavior those
specs govern.
