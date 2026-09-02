# Underlay Decomposition Slice — Design

> **Status:** design (2026-09-02). Implements the next domain slice of the Model_Space
> decomposition governed by `docs/specs/model-space-architecture.md` (§5). This doc is the
> *how*; the *what* was locked in a grill (see §0). On landing, `model-space-architecture.md`
> §5 is stamped in place — no parallel governing spec is created.

## 0. Locked scope (from grill — not relitigated here)

- **Pure behavior-preserving relocation.** Zero behavior change, zero bug fixes.
- **Deferred (explicitly out):** PDF cache-key mismatch bug; duplicate-drops-import-fields bug
  (lives in `underlay_context_menu.py`, off-surface); per-element-underlay-selection (un-spec'd,
  deferred); the dispatch-plugin generalization; caller-repointing; `main.py` decomposition.
- **Full back-compat, repoint nothing:** `scene.underlays`, the 8 public methods, and
  `underlaysChanged` keep working for 10 prod files + ~200 test sites.
- **Freeze controller stays on the scene** (refined from the grill after finding external
  `hasattr(sc, "_underlay_freeze")` reach-ins in `model_view.py` + ~40 test sites — moving it
  would trip the `mixin→composition hasattr trap`, a live-only break).

## 1. Goal

Lift the underlay/import concern (~10 attrs + ~28 methods + the async DXF worker + the cache
orchestration + the `place_import` transient state) out of `model_space.py` (11,838 lines) into a
scene-referencing collaborator `UnderlayController(scene)`, behavior-preservingly, with file
byte-parity and undo untouched. This is the "cleanest domain slice" per the decomposition map
(concern #3: excluded from undo, own serialization block, isolated async worker, single shared
`self.underlays` list).

## 2. Architecture

### 2.1 New collaborator

- **Module:** `firepro3d/underlay_controller.py`
- **Class:** `UnderlayController` — a **plain object** (not a `QObject`). Rationale: the async
  worker signals are connected via **lambda slots** (no QObject receiver needed), and
  `underlaysChanged` stays defined on the scene — so introducing a QObject would only add thread
  affinity we don't want. Mirrors slice-B's `SceneTools(scene)` shape.
- **Constructed** in `Model_Space.__init__`: `self._underlay_ctl = UnderlayController(self)`.

### 2.2 State owned by the controller

| Attr | Role |
|---|---|
| `self.items` | the `list[(Underlay, QGraphicsItem)]` (was `Model_Space.underlays`) |
| `self._dxf_worker` / `self._dxf_progress` / `self._dxf_import_params` | async DXF import bridge |
| `self._place_import_params` / `_ghost` / `_bounds` / `_preserve_mgmt` / `_remove_old` | `place_import` transient state |
| `self._scene` | back-ref to `Model_Space` (scene-graph mutation + `underlaysChanged` are universal — decomposition seam §3.1) |

**Not owned:** `UnderlayFreezeController` — stays `scene._underlay_freeze` (view-gesture/render
concern; reached externally by `model_view.py` + tests). The controller references it via
`self._scene._underlay_freeze` for defensive aborts, exactly as the code does today.

### 2.3 Delegation contract (on `Model_Space`)

- `underlays` → **read `@property`** returning `self._underlay_ctl.items`. Returns the live list, so
  in-place mutations (`.append`, iteration) keep working; only *rebinds* need routing.
- Every `self.underlays = <x>` rebind → `self._underlay_ctl.reset()` (audited across
  `model_space.py` + `scene_io.py`; known site: `scene_io.py:537`).
- **8 public shells** (`import_dxf`, `import_pdf`, `begin_place_import`, `refresh_all_underlays`,
  `refresh_underlay`, `replace_underlay`, `begin_replace_underlay_placement`, `remove_underlay`) →
  each `return self._underlay_ctl.<same>(...)`. All external callers + `scene_io` unchanged.
- `underlaysChanged` stays on the scene; controller emits `self._scene.underlaysChanged.emit()`.
- `abort_underlay_freeze` shell stays on the scene (unchanged).

### 2.4 Methods moved whole into the controller

Private/internal (called only by moved methods or by `scene_io` via the public shells):
`_on_dxf_progress/_finished/_error`, `_cleanup_dxf_worker`, `_import_pdf_vectors`,
`_build_batched_underlay_group`, `_attach_snap_index`, `_build_pen_cache`, `_append_geom_to_path`,
`_apply_underlay_display`, `_apply_underlay_hidden_layers`, `_create_underlay_placeholder`,
`find_underlay_for_item`, `repen_underlay`, `set_underlay_layer_hidden`,
`_update_place_import_ghost`, `_commit_place_import`, `_ensure_underlay_caches`,
`_load_underlay_from_cache`, `_write_underlay_cache`.

Body rewrites (mechanical): `self.<sceneOp>` → `self._scene.<sceneOp>`;
`self.underlays` → `self.items`; `self.underlaysChanged.emit()` → `self._scene.underlaysChanged.emit()`;
`self._underlay_freeze` → `self._scene._underlay_freeze`; `self._show_status` → `self._scene._show_status`
(and any other scene-side helper via `self._scene.`). The async worker's **lambda-connect block
moves verbatim** (only the captured `self` rebinds to the controller), preserving Qt thread-delivery
semantics. `group.setData(0..6)` slot conventions are untouched.

### 2.5 Dispatch & mode

- `place_import` **press/move handlers stay as scene-side forwarders** so `_PRESS_DISPATCH` /
  `_MOVE_DISPATCH` (resolved via `getattr(self, name)`) are untouched. They call
  `self._underlay_ctl._update_place_import_ghost(...)` / `_commit_place_import(...)`.
- `set_mode`'s `place_import` teardown (~model_space.py 1245–1257) → **`UnderlayController.clear()`**;
  `set_mode` calls `self._underlay_ctl.clear()` when leaving `place_import`. `clear()` is idempotent
  (removes the ghost if present, nulls the transient payloads, resets `_bounds` to default) and
  preserves the deferred-remove-old cancel-safety (a cancelled "Pick new position" never destroys
  the original underlay).

## 3. Data flow (unchanged, relocated)

- **Import (async DXF):** `scene.import_dxf(...)` shell → `ctl.import_dxf(...)` builds
  `DxfImportWorker(QThread)`, wires lambda slots (`progress`/`status`/`finished_data`/`error`),
  `worker.start()`. On `finished_data` → `ctl._on_dxf_finished` mutates the scene, registers the
  underlay in `ctl.items`, `scene.underlaysChanged.emit()`, `ctl._cleanup_dxf_worker()`.
- **Import (PDF):** `scene.import_pdf(...)` → `ctl.import_pdf(...)` (sync vectors first, raster
  fallback). Same registration/emit tail.
- **Save:** `scene_io.save_to_file` reads `scene.underlays` (property), relativizes paths, writes the
  underlay block; `_ensure_underlay_caches(project_path)` writes JSON caches for dirty groups.
- **Load:** `scene_io.load_from_file` per record: resolve path → `ctl._load_underlay_from_cache`
  (via a shell or public method) → source re-parse via `scene.import_pdf/_dxf` shells → placeholder
  fallback. Order preserved exactly.
- **Undo/redo:** untouched — `_capture_network`/`_restore_network` never reference underlays;
  `undo`/`redo` call `scene.abort_underlay_freeze()` (unchanged).

## 4. Testing

**Characterization suite (written + green on `main` BEFORE C1 — the relocation safety net):**
- `test_underlay_file_byte_parity` — load a real `.fpd` (PDF + DXF underlay) → save → byte-identical
  `.fpd` payload.
- `test_underlay_survives_undo_redo` — snapshot `scene.underlays`, undo/redo cycle, assert identical
  records/items/order (proves the undo-exclusion invariant survives).
- `test_place_import_live` — posted `QMouseEvent`s on a shown+activated view: ghost follows cursor,
  commit places the group (real entry point, not handler calls).
- `test_place_import_cancel_preserves_original` — begin "Pick new position", cancel via `set_mode`,
  assert the original underlay is untouched (cancel-safety).
- `test_async_dxf_import_completes` — async import → `finished_data` → registered + `underlaysChanged`
  emitted + worker cleaned up.
- `test_scene_underlays_backcompat` — `scene.underlays` property readable, `scene.import_pdf(...)`
  shell callable, `scene.underlaysChanged` connectable (guards the delegation contract).

**RED-demo (behavior-regression proof) — reserved for the `clear()` migration only:** stub
`UnderlayController.clear()` to a no-op and confirm `test_place_import_cancel_preserves_original`
+ the ghost-removal assertion go RED; restore → green. (A pure relocation has no other red-to-green;
the parity tests are green before and after by design.)

**Subagent implementers run only the targeted underlay test files.** Full-suite green (chunked per
the long-run-flake memory; no new failures beyond the pre-existing L72/L84 trio) is a Phase-6 gate
run by the orchestrator.

## 5. Slicing (revertable sub-commits, parity green at each step)

Branch: `refactor/model-space-underlay-slice`.

0. **C0 — Characterization tests** land on the branch, green (the safety net).
1. **C1 — Scaffold + list ownership.** New `underlay_controller.py` (controller owning `items=[]`,
   `_scene` back-ref); `__init__` builds `self._underlay_ctl`; add `underlays` property; route the
   `self.underlays = []` rebind(s) → `reset()`. All method bodies unchanged (in-place mutation via
   the property still valid). Targeted tests green.
2. **C2 — Move methods** in batches, each batch relocating bodies + adding shells/forwarders, targeted
   tests green after each:
   - C2a: import/async (`import_dxf`, `import_pdf`, `_on_dxf_*`, `_cleanup_dxf_worker`,
     `_import_pdf_vectors`, `_build_batched_underlay_group`, `_attach_snap_index`, `_build_pen_cache`,
     `_append_geom_to_path`).
   - C2b: manage (`refresh_underlay`, `refresh_all_underlays`, `replace_underlay`,
     `begin_replace_underlay_placement`, `remove_underlay`, `repen_underlay`,
     `set_underlay_layer_hidden`, `find_underlay_for_item`, `_apply_underlay_display`,
     `_apply_underlay_hidden_layers`, `_create_underlay_placeholder`).
   - C2c: place_import (`begin_place_import`, `_update_place_import_ghost`, `_commit_place_import`)
     + scene-side dispatch forwarders.
   - C2d: cache (`_ensure_underlay_caches`, `_load_underlay_from_cache`, `_write_underlay_cache`).
3. **C3 — `clear()` + set_mode** wiring, with the RED-demo.
4. **C4 — Verify** targeted set complete; confirm the back-compat guard; run full suite (Phase-6).
5. **C5 — Spec §5 stamp** (`last-verified` / `verified-commit`); note the `UnderlayController`
   name (supersedes the provisional `UnderlayManager` in §5).

## 6. Acceptance criteria (relocation tier, from `model-space-architecture.md` §8)

- [ ] File byte-parity: real `.fpd` (PDF+DXF) → load → save → byte-identical payload.
- [ ] Undo/redo leaves `scene.underlays` identical (exclusion invariant intact).
- [ ] `place_import` drives correctly via posted events on a shown view; cancel preserves the original.
- [ ] Async DXF import completes, registers, emits, cleans up the worker.
- [ ] `set_mode` teardown travels as an idempotent `UnderlayController.clear()`.
- [ ] No moved method retains a hidden `self`/side-effect dependency the shell doesn't cover.
- [ ] `scene.underlays` / 8 shells / `underlaysChanged` back-compat intact (10 prod files + tests).
- [ ] Full suite green (chunked); no new failures beyond the pre-existing trio.
- [ ] `model-space-architecture.md` §5 re-audited + stamped.

## 7. Governed-behavior cross-refs (Rule A — do not restate)

Behavior is owned by `underlay-workflow.md` (import/cache/freeze §18/§16) and the freeze paint-only
contract there. This slice is structural only; it moves code without changing any behavior those
specs govern.
