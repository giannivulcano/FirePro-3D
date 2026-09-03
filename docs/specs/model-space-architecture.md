---
status: partial            # current: as-built composition §2/§3 ; proposal: target decomposition §5/§6
last-verified: 2026-09-02
verified-commit: 43311bb   # slices 1 (A+C), 2 (B), 4a+4b (codec), + Underlay domain slice landed; census in §2 mapped @ 3a99b63
applies-to:
  - firepro3d/model_space.py
  - firepro3d/scene_tools.py
  - firepro3d/scene_io.py
source-tasks:
  - "TODO.md — Model_Space decomposition"
---

# Model_Space Architecture & Decomposition — Design Spec

> **Scope of this spec.** This is the *structural* governing spec for the `Model_Space` scene object — its composition, the seams between the concerns living on it, and the contract any decomposition must honor. It does **not** restate the behavior each concern already owns; those are governed by their own specs (see §7) and linked per Rule A. The detailed per-concern method/state census is the dated analysis artifact `docs/superpowers/specs/2026-08-28-model-space-decomposition-map.md`.

## 1. Goal

Give `Model_Space` a composition contract so its ~dozen distinct concerns can be lifted into collaborators **incrementally and behavior-preservingly**, without silent regressions in the live app or in either serialization path. Today `class Model_Space(SceneToolsMixin, SceneIOMixin, QGraphicsScene)` is a single object carrying every concern's state and methods; there is no governing description of *what belongs where*, so every change risks cross-concern ripple.

## 2. Current State (as-built — `status: current`)

- `Model_Space` subclasses `QGraphicsScene` and mixes in `SceneToolsMixin` (`scene_tools.py`) and `SceneIOMixin` (`scene_io.py`). **Neither mixin has its own `__init__`** — they read/write `Model_Space` state through the shared `self`, so the three files are one object, not three collaborators.
- The object carries **~200 instance attributes** (indicative, at `verified-commit`) spanning pipe/node, sprinkler/design-area, underlay/import, serialization/undo/clipboard, ALIGN+dynamic-input+templates, 2D-geometry drawing, architectural placement, event-dispatch/selection/levels, and edit-tools. The per-concern breakdown is in the map artifact.
- **Mode-driven dispatch.** Class-level `_PRESS_DISPATCH` / `_MOVE_DISPATCH` / `_PREVIEW_DISPATCH` dicts map `self.mode` → handler-method name; `mousePressEvent`/`mouseMoveEvent` resolve a snapped position via `get_effective_position`, then `getattr(self, handler)(...)`. `_PLACEMENT_VARIANTS` (instance) + `_ALIGN_PLACEMENT_MODES` (class) drive variant cycling and ALIGN arming.
- **`set_mode` is the teardown chokepoint** — a long per-concern cascade that clears every tool's transient state on each mode transition.

## 3. The four coupling seams (the decomposition contract)

Any extraction MUST honor these — they are why concerns are entangled and what a collaborator boundary has to preserve:

1. **Scene-graph mutation is universal.** Every concern calls `self.addItem/removeItem/createItemGroup`. → An extracted collaborator is a *scene-referencing* object (`SomeManager(scene)`), never a pure non-Qt module. Pure-logic sub-layers (geometry math) are the exception and extract cleanly.
2. **Undo is whole-scene snapshot glue.** Commits call `push_undo_state()`; `_capture_network`/`_restore_network` snapshot/rebuild *all* entity lists. An extracted concern's persisted lists must remain reachable from the undo path.
3. **Dual serialization parity (INVARIANT).** `scene_io.save_to_file` (file) and `_capture_network` (undo) are independent hand-written serializers. Any persisted field must be written **identically by both**, and any new entity needs: `to_dict`/`from_dict`, an entry in *both* serializers, a rebuild in `_restore_network`, a tracking-list reset in `_clear_scene`, and — if copyable — a `paste_items` branch. (See the divergence ledger, §4.) This is the same hazard as the `project_dual_serialization_paths` memory.
4. **`set_mode` becomes registered `clear()`.** When a concern's transient state moves to a collaborator, its `set_mode` cleanup branch must move with it as a `clear()` the core calls — the flat cascade becomes an observer list. The dispatch tables are the plug-in seam: a placement concern registers schema + applier + variant + press/move handler together (miss one → HUD freezes; see `project_transform_seed_hud_per_mode`).

## 4. Divergence ledger (as-built defects found during mapping)

These are real gaps between the two serializers / dispatch paths, banked as follow-up tasks (not blockers for decomposition, but the decomposition must not entrench them):

- ~~Pipe properties read from `pipe._properties` (file) vs `pipe.get_properties()` (undo)~~ — **RESOLVED 4a**: both serialize via `network_codec.serialize_pipe` (reads `_properties`).
- ~~`_restore_network` skips `update_geometry()` and `_recalc_name_counters()`~~ — **RESOLVED**: `_recalc_name_counters()` is now called on restore; `update_geometry()` is now run via `add_pipe` (both deserialize paths route pipes through it — slice 4b). Verified by `test_pipe_geometry_correct_after_undo` (green) and `test_name_counters_recomputed_after_undo`.
- ~~`NoteAnnotation.text_width` lost on undo~~ — **RESOLVED**: both paths pass `text_width` to the ctor via `network_codec.deserialize_note` (slice 4b). Verified by `test_note_text_width_survives_undo`.
- `wall`/`room`/`floor_slab`/`roof` are captured by copy but have **no `paste_items` branch** → silently dropped on paste; `block_item` pastes but isn't tracked in any list → orphaned from undo. *(Still open — the paste path is Tier-3, deferred out of 4b.)*
- Gridline paste is detected by structural heuristic (`"origin"+"angle"`, no `"type"`) — fragile. *(Still open — Tier-3 paste path.)*
- `Room.z_range_mm()` still reads the retired floor `.level`, which new two-boundary slabs don't reliably write. *(Still open — separate bug, not a deserialize-path issue.)*

## 5. Target composition (proposal — `status: proposal`)

The end state is a thin `Model_Space` core plus scene-referencing collaborators. Candidate collaborators (names provisional, to be settled in grill): `UnderlayManager`, `PipeNetworkManager`, `SprinklerWorkflow`/`DesignAreaController`, `GeometryDrawingController`, per-element `*PlacementController`s (wall/floor/roof/opening/room/gridline), `PlacementInputCoordinator` (ALIGN+HUD+variants+templates), and a `NetworkCodec` helper unifying the dual serializers.

**What stays as the irreducible core:** the `QGraphicsScene` event overrides, the dispatch tables, `set_mode`, the grip mechanism, and `get_effective_position` result plumbing. Level-ops and gridline-selection are the most peelable subsets of the core.

**End-state framing (grilled 2026-08-28):** the target is (A) *real collaborator objects* that own their concern's state and back-reference the scene — **not** one-class-with-enforced-boundaries. Composition here **relocates** (each collaborator keeps a `self._scene` ref, because scene-graph mutation + `push_undo_state` are universal — seam §3.1); the win is navigability / isolation-testability / a named home per concern, not dependency inversion. That trade-off is accepted deliberately.

**"Pure core out, side-effect shell stays" rule.** When a method's logic is pure but it has side-effect tails (repaint via `self.views()`, status-bar via `_show_status`, `push_undo_state`), extract the *pure core* and leave a thin scene-side shell that calls it then runs the side effects. Verified necessary for the constraint solver (`_solve_constraints` repaints all viewports + reports conflicts). Any A-layer helper found to have a hidden side-effect on inspection is split the same way.

### 5.1 Cross-boundary dependency ledger (`main.py` / `model_view.py` ↔ scene)

`main.py` (MainWindow) is a **sibling** decomposition task with its own spec, but it shares a dependency surface with the scene that both tasks must honor. Classification:

- **Bare attribute access — MUST be cleaned when the owning concern extracts:** `main._on_escape` writes `scene.node_start_pos` / `scene._pipe_node_was_new`; `scene.active_view_key` / `active_level` writes. **Rule:** the slice that extracts a concern converts that concern's bare-attribute reach-ins into a public scene method *in the same commit* (e.g. `scene.cancel_pipe_placement()`), so the sibling `main.py` task never inherits a broken reach-in. This generalizes the dual-serialization "add to BOTH in the same commit" discipline to the module boundary.
- **Injected collaborators (load-order-sensitive contract):** `main` sets `scene._level_manager`, `_plan_view_manager`, `_detail_manager`, `_sheets`.
- **Method API (keep):** `run_hydraulics`, `clear_hydraulics`, `set_coverage_overlay`, `set_sprinkler_db`, `begin_place_import`/`import_dxf`/`import_pdf`, `refresh_all_underlays`.
- **Signals (already decoupled — safe):** `requestPropertyUpdate`, `sceneModified`, `modeChanged`, `instructionChanged`, `confirmRequested`, `pipeNodeHighlight`, `underlaysChanged`, `snapToggled`, `alignToggled`, `cursorMoved`.
- **View→scene:** `model_view.begin_stretch_crossing`.

## 6. Design Decisions

- **Incremental, layered, behavior-preserving — not big-bang.** Each slice is independently reviewed, tested for parity, and revertable. Rationale: the concern verdicts are mostly *Hard* (universal scene mutation + undo), and memory shows this file's bugs are live-only (grips/focus/dispatch) — a big-bang rewrite would hide regressions headless tests can't catch.
- **Slice 1 = A + C (pure relocations, zero behavior change) — ✅ landed cf1c6c1:**
  - **A —** move the *item-aware* pure helpers (`_compute_fillet`, `_compute_chamfer`, `_offset_polyline_pts`, `_get_item_segments`, `_compute_intersections`, `_compute_extend_intersections`, `extract_edges`) → new `tool_geometry.py`. A new module *is* warranted: these dispatch on `construction_geometry` item types, so they cannot live in `cad_math.py`/`geometry_intersect.py` (item-agnostic; would create an import cycle). **Reuse, don't relocate:** the raw-math duplicates `_offset_line_intersection` (≈ `gi.line_line_intersection_unbounded`) and `_point_to_segment_dist` (≈ `CAD_Math.point_on_line_nearest`) fold into the existing modules instead of moving.
  - **C —** **split** the constraint solver: the pure algorithm (`solve(constraints, moved_item=None) -> list[unsatisfied]`, loop + stall/convergence detection) → `constraints.py` (already governed by `parametric-constraint-system.md`); the repaint + `_report_constraint_conflict` side-effect tail stays as a thin scene-side `_solve_constraints` shell. Update the 3 model_space call-sites + scene_tools.
- **Slice 2 = B — `SceneToolsMixin` mixin → composition — ✅ landed 4ae820a** (`self._tools = SceneTools(self)`). Redirect its borrowed state attrs + geometry registries to `self._scene.*`; audit `self.mode` direct writes against `set_mode` side-effects; keep dispatch `getattr` resolution working (forwarding stubs or dispatch-on-collaborator). This is the first slice that changes an app-wide access/dispatch pattern → isolated for its own review + **manual smoke test**.
- **`NetworkCodec` unify** — split: **4a (serialize) ✅ landed c675721** (the 6 hand-serialized types route through `network_codec.py`; `.fpd` byte-identical) and **4b (deserialize) ✅ landed 951c72a** — the same 6 types deserialize through `network_codec.deserialize_{node,pipe,dimension,note,water_supply,design_area}`; each caller (`load_from_file`, `_restore_network`) keeps its own orchestration (id maps, ordering, load-only migrations) and its own **display tail** (restore applies category/DM display inline; file-load defers to `main`'s `apply_saved_display_settings` — an intentional context difference, *not* converged). Two non-display drifts converged deliberately: node ceiling ordering (apply after the sprinkler block — `add_sprinkler` does not read node ceiling, dropping load's save/restore dance) and pipe creation (both paths via `add_pipe(_propagate_ceiling=False)`). Field-application parity + byte-identical file round-trip + undo-capture stability asserted in `tests/test_serializer_parity.py`. Net −252 LOC from `model_space.py`+`scene_io.py`. *Then* domain concerns. **Underlay** is the recommended first domain slice (excluded from undo, own serialization block, isolated async worker, single shared `self.underlays` list).
- **Underlay domain slice — ✅ landed 43311bb** (design: `docs/superpowers/specs/2026-09-02-underlay-slice-design.md`). The underlay/import concern extracted to `firepro3d/underlay_controller.py` (**`class UnderlayController(scene)`**, a *plain object* — the async worker uses lambda slots and `underlaysChanged` stays on the scene, so no QObject affinity). It owns `self.items` (the underlay list), the async DXF worker bridge, the `place_import` transient state, and back-references the scene (`self._scene`) for scene-graph mutation + signal emission. **Pure behavior-preserving relocation** (`.fpd` byte-identical; undo untouched — the concern was already excluded from `_capture_network`/`_restore_network`). Back-compat kept by delegation, *repoint nothing*: `Model_Space.underlays` is a read-property → `self._underlay_ctl.items`; the 8 public methods + several internals are thin scene-side shells; `underlaysChanged` stays defined on the scene (controller re-emits via `self._scene`); the `_place_import_*` accessors stay as bridge properties (read/written externally by `main.py` + tests). The `place_import` press/move dispatch handlers stay as scene-side forwarders (dispatch tables **untouched**). `set_mode`'s place_import teardown → `UnderlayController.clear()`. The **freeze controller (`UnderlayFreezeController`) deliberately STAYS on the scene** (`scene._underlay_freeze`) — a view-gesture/render concern reached externally by `model_view.py` (incl. `hasattr` guards) + ~40 tests; moving it would trip the mixin→composition hasattr trap. **`UnderlayController` supersedes the provisional `UnderlayManager` name** in §5's collaborator list. Scene-side underlay references dropped 150→78 in `model_space.py`. Characterization safety net + a `clear()` RED-demo in `tests/test_underlay_slice_parity.py`.

## 7. Governed-behavior cross-references (Rule A — do not restate)

`grid-system.md` · `2d-geometry.md` · `wall-room-floor-system.md` · `pipe-placement-methodology.md` · `sprinkler-system-components.md` · `hydraulic-solver-and-reporting.md` · `align-placement.md` · `parametric-constraint-system.md` · `underlay-workflow.md` · `selection-mode.md` (proposal) · `view-relationships.md` (levels/Z). Serialization currently lives in `architecture/io.md` (thin; `scene_io.py` is a listed orphan — promote on the serialization slice).

## 8. Acceptance Criteria (tiered — grilled 2026-08-28)

**Every slice:**
- [ ] Full test suite green (chunked per the long-run-flake memory); no new failures beyond the pre-existing L72 trio.
- [ ] **File parity:** load an unchanged real `.fpd` → save → **byte-identical** output (round-trip stability).
- [ ] **Live parity:** affected tools drive correctly via posted `QMouseEvent`/`QKeyEvent` on a shown+activated view (not handler calls) — per `feedback_test_real_entry_point`.
- [ ] Any moved `set_mode` cleanup travels with its state as an idempotent `clear()` (§3.4).

**Relocation slices (A, C) — additionally, *zero* behavior change:**
- [ ] Undo/redo round-trip yields identical item state (positions, properties, connectivity) vs. `main`.
- [ ] No moved pure-logic function retains a hidden `self`/side-effect dependency (else split per the "pure core out, shell stays" rule).

**Behavior-changing slices (`NetworkCodec` unify; B if it alters dispatch) — additionally:**
- [ ] The deliberately-fixed §4 divergences are asserted as **red→green tests** (the change is intended, not incidental).
- [ ] File output still byte-identical for an unchanged `.fpd`; undo bytes *may* change by design (they now match file).
- [ ] **Manual smoke test** by the user before wrap-up (per `feedback_phase6_after_smoketest`).

## 9. Verification Checklist

- [ ] All acceptance criteria met for the slice.
- [ ] No regressions in the dispatch tables (every mode still resolves a handler).
- [ ] This spec re-audited and `last-verified`/`verified-commit` stamped after the slice.
- [ ] `SPEC-INDEX.md` updated if a subsystem boundary moved or `scene_io.py` promoted out of Orphans.
