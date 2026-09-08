# U2 — The `Handle` Model (design of record)

**Date:** 2026-09-08
**Governing spec:** `docs/specs/selection-manipulator.md` (§209–264 Unification Roadmap)
**Task:** U2 of the Selection-Manipulator Unification roadmap
**Spec-change tier:** extend the governing spec in place (add a "U2 — Handle model (as-built)" subsection); NOT a new spec file.

> This design covers only the **"how"**. The **"what"** was locked in the 2026-09-08 /todo
> grill and is reproduced under *Fixed Requirements* — do not relitigate it here.

---

## Goal

Introduce a `Handle` behavior abstraction (role + scene-position + drag→edit + commit) and a
`manip_handles()` capability, and re-express the `SelectionManipulator`'s own **resize + rotate**
handles in terms of it — a pure internal refactor with **identical observable behavior**. This is
the foundation U3 (migrate items onto `manip_handles`), U4 (retire the parallel grip system), and
U5 (fold in selection-mode + other scenes) all build on.

## Fixed Requirements (locked in grill — binding)

1. U2 re-expresses **only** the 8 resize handles + rotate knob as `Handle`s. Interior-drag **move
   stays a manipulator-level gesture** (not a Handle).
2. `manip_handles()` consumption path is built **live but with fallback** (option B): the
   manipulator sources its handle set through one path that returns the rigid set today and is
   structurally ready to union item `manip_handles()` results in U3. No item implements it in U2 →
   behavior identical.
3. **Two concepts, reconciled by wrapping:** `Handle` (behavior) vs the existing `_Handle`
   (screen-constant `QGraphicsItem` widget). They do **not** merge.
4. **Critical U3-admissibility constraint:** the `Handle` contract must admit a **live-apply** drag
   model (parametric grips: each move calls `apply_grip(idx,pt)` + constraint solve, no held
   preview) in addition to the **held-preview** model (rigid resize/rotate: accumulate a transform
   delta, bake once on release). The manipulator must not hard-assume held-preview.
5. **Parity (hard gate):** preserve `manip._handles[role]` dict + `_begin/_update/_finish(mode,
   role)` signatures as thin adapters over the new Handles so all 6 existing manip test files pass
   **unmodified**. Zero-diff on `provides_handles_for` / `scene_tools._find_grip_hit` /
   `Model_View.drawForeground` grip loop + all 11 `grip_points()` item modules.
6. Ships **standalone to `main`**.

## Architecture & Constraints

### Module layout

- **New `firepro3d/manip_handle.py`** — behavior classes only (no Qt widget code):
  `Handle` (abstract base), `ResizeHandle(Handle)`, `RotateHandle(Handle)`.
  *(U3 later adds `GripHandle(Handle)` here — live-apply. Not in U2.)*
- **`selection_manipulator.py` keeps** the held-preview toolkit (`_begin`/`_update`/`_finish`/
  `_apply`/`_bake_move`/`_bake_scale`/`_bake_rotate`/`_snap`/`_feed_hud`/`cancel_drag`), the
  module-level capability funcs (`item_capabilities`/`manip_bounds`/`bake_translate` — imported by
  tests + `paper_space.py`), and the constants (`_ROTATE_OFFSET_PX` etc. — imported by a test).
- **`manip_math.py`** stays pure math; `manip_handle.py` imports `HandleRole`, `_ROLE_GEOM`,
  `_rect_point`, `resize_delta`, `rotate_delta` from it.

### Two-object model — **wrap, don't merge**

- `Handle` (in `manip_handle.py`) = the **behavior**: plain Python object, no Qt inheritance. Owns
  position, paint-definition, shape-definition, cursor, visibility gating, drag lifecycle, HUD.
- `_HandleItem(QGraphicsItem)` (**renamed** from `_Handle`, stays in `selection_manipulator.py`) =
  the thin **screen-constant host**: `ItemIgnoresTransformations` (or paper-mm sizing), forwards
  `paint`→`handle.paint(...)`, `shape`→`handle.shape(...)`, hover→`handle.cursor(...)`, and
  `mousePress`→`manip._begin_handle(handle, …)`. References its `Handle`.

Rationale: the widget host is the *rendering/event mechanism*; the `Handle` is the *behavior*.
Rigid handles keep rendering via role-keyed `_HandleItem`s, so `manip._handles[role].isVisible()`
and `.scenePos()` stay valid (parity). When U3/stub items return widget-less `Handle`s, the
manipulator spins up host `_HandleItem`s for them from the same pool → they render + hit-test
through the **one** path. Merging `Handle` into `QGraphicsItem` would force every future parametric
grip to be a persistent Qt child — the opposite of the spec's "manipulator is the single
renderer/hit-tester" end-state.

*(No test references `_Handle` directly — verified — so the rename is parity-safe.)*

### The `Handle` contract

```python
class Handle:
    """Behavior for one manipulator affordance. Plain object; the manipulator
    is passed in as the drag context `m`."""

    role: HandleRole            # or a parametric role tag in U3

    # geometry / appearance (host delegates to these)
    def scene_position(self, frame_rect: QRectF) -> QPointF: ...
    def shape(self, *, size, grab_pad) -> QPainterPath: ...      # local hit region
    def paint(self, painter, *, size, border, fill, hover) -> None: ...
    def cursor(self, m) -> QCursor: ...
    def visible(self, m) -> bool: ...        # capability gating (was _layout logic)

    # drag lifecycle (manipulator delegates; NO drag-model branch upstream)
    def on_press(self, m) -> None: ...
    def on_drag(self, m, scene_pos: QPointF, mods) -> None: ...
    def on_release(self, m, scene_pos: QPointF, mods) -> None: ...
    def on_cancel(self, m) -> None: ...
    def commit_typed(self, m, values: dict) -> None: ...   # HUD typed path

    # HUD
    hud_schema: str | None                   # "manip_resize" / "manip_rotate" / None
    gesture_mode: str                        # "resize" / "rotate" — sets manip._mode
    def hud_values(self, m) -> dict: ...      # live readout during on_drag
```

### How the two drag models live under one contract

- **`ResizeHandle` / `RotateHandle` (held-preview)** implement the lifecycle by *orchestrating the
  manipulator's unchanged toolkit*:
  - `on_press(m)`: `m._snapshot_items()` (the existing `_begin` snapshot body).
  - `on_drag(m, pos, mods)`: `snapped = m._snap(pos)` *(rotate skips snap)*; compute
    `resize_delta`/`rotate_delta`; `m._apply(d)`; `m._feed_hud(self.hud_values(m))`. Stores
    `_last_factors`/base angle on `m` exactly as today.
  - `on_release(m, pos, mods)`: `m._restore_preview()`; `m._bake_scale(...)` / `m._bake_rotate(...)`
    (these already fire `_refresh_fittings` → `_solve_constraints` → `commit_hook`).
  - `commit_typed(m, values)`: the current `_on_hud_committed` resize/rotate arithmetic, calling the
    same `_bake_*`.
- **`GripHandle` (U3, not U2)** implements the *same* methods but `on_drag` does
  `snapped = m._snap(pos); self.item.apply_grip(self.idx, snapped); m._solve_constraints()` —
  **no `_apply`, no held transform** — and `on_release` fires `m._commit("grip")`. The manipulator
  calls `handle.on_drag` either way and is oblivious to which model ran.

The manipulator owns drag *state* (`_items0`, `_B0`, `_R0`, `_start_scene`, `_moved`, `_held_snap`,
`_active_handle`) and exposes the toolkit methods as the documented **Handle-facing context API**
(the existing helpers, relabeled as "methods a Handle may call"). No separate `DragContext` class
(YAGNI for U2).

### Manipulator wiring

Construction:
```python
self._rigid = {role: ResizeHandle(role) for role in _RESIZE_ROLES}
self._rigid[HandleRole.ROTATE] = RotateHandle()
self._handles = {role: _HandleItem(self, self._rigid[role]) for role in self._rigid}
```

Unified sourcing (option B):
```python
def _active_handles(self) -> list[Handle]:
    item_handles = [h for it in self._items
                    for h in (getattr(it, "manip_handles", None) or (lambda: []))()]
    return item_handles or list(self._rigid.values())   # fallback = rigid
```

- `_layout()` iterates `_active_handles()`: positions each handle's host
  (`host.setPos(handle.scene_position(rect))`) and gates visibility via `handle.visible(self)`. The
  current resize/rotate/`MANIP_NO_SOLO_ROTATE` gating moves *into* `ResizeHandle.visible` /
  `RotateHandle.visible` verbatim. Widget-less sourced handles get lazily-pooled host `_HandleItem`s
  (empty in production U2).
- Lifecycle delegation, signatures unchanged:
  ```python
  def _begin(self, mode, scene_pos, screen_pos, role=None):   # SIGNATURE UNCHANGED
      self._active_handle = None if mode == "move" else self._rigid[role]
      self._mode, self._role = mode, role                     # tests read these
      ... existing snapshot bootstrap ...
      if self._active_handle: self._active_handle.on_press(self)
      self._open_hud(mode)

  def _begin_handle(self, handle, scene_pos, screen_pos):     # NEW — host calls this
      self._begin(handle.gesture_mode, scene_pos, screen_pos, handle.role)
  ```
  `_update`/`_finish` keep their move-threshold check + move-click-through, then delegate:
  `if self._active_handle: handle.on_drag/on_release(self, …)` else the existing move path.
  `_on_hud_committed`: resize/rotate → `self._active_handle.commit_typed(self, values)`; move →
  existing move branch. `cancel_drag` → `handle.on_cancel(self)` when active.

**Parity story:** `_handles[role]` dict ✓, `_begin/_update/_finish(mode, role)` signatures ✓,
`_mode`/`_role` state ✓, toolkit math/bake code byte-unchanged ✓. Only orchestration relocates.

## Design Decisions

- **Delegation (base + subclasses)** over a `drag_model` discriminant (relocates the branch, doesn't
  move behavior onto the Handle — the spec's stated target) and over template-method (bakes
  held-preview into the manipulator lifecycle → fails the live-apply admissibility constraint).
- **Wrap** (`Handle` behavior + `_HandleItem` host) over merge (`Handle : QGraphicsItem`) — keeps
  rigid rendering where the tests expect it and lets widget-less U3/stub handles render through the
  same host pool.
- **Toolkit stays on the manipulator, unchanged; only orchestration moves.** The code that could
  drift (delta math, bake, snap, constraint solve, undo) does not move — the single biggest
  risk-minimizer for the "identical behavior" gate.
- **New module `manip_handle.py`** over growing `selection_manipulator.py`; capability funcs +
  constants stay in `selection_manipulator.py` for import parity.

## Acceptance Criteria

- [ ] `Handle` base + `ResizeHandle`/`RotateHandle` exist in `manip_handle.py`; the manipulator's
      resize + rotate handles are expressed through them (behavior off the mode/role branches).
- [ ] `_active_handles()` live with rigid-set fallback; a stub item's `manip_handles()` handle
      renders + hit-tests inside the frame; `provides_handles_for`/`_find_grip_hit`/`drawForeground`
      byte-untouched.
- [ ] `Handle` contract provably admits a live-apply drag model (the `_FakeGripHandle` test).
- [ ] All 3 parity gates pass; 6 existing manip test files unmodified; 3 new test files added, each
      red-verified.
- [ ] Blast radius confined to `selection_manipulator.py` + `manip_handle.py` + 3 new tests +
      the spec subsection.

## Verification / Testing

New test files (existing 6 unmodified):
- `test_manip_handle.py` — Handle-level units: `scene_position` per role mirrors `_ROLE_GEOM`;
  `ResizeHandle`/`RotateHandle` deltas match `resize_delta`/`rotate_delta`; `visible()` gating
  matches old `_layout`. Red-verified.
- `test_manip_handle_admissibility.py` — `_FakeGripHandle` live-apply proof (live edit every move,
  **no** `_apply` held transform, one commit on release) + `manip_handles()` fallback/stub
  consumption + legacy-seam-untouched assertions.
- `test_manip_u2_parity.py` — posted-`QMouseEvent` full-gesture parity (resize corner + edge,
  rotate) → byte-identical serialization; no-op + Esc byte-parity.

Plus: full suite green (chunked per project convention); live smoke in both scenes, both themes.

## Spec update at wrap-up (Phase 6 / Account)

Add a "U2 — Handle model (as-built)" subsection under the Unification Roadmap in
`docs/specs/selection-manipulator.md`: the `Handle` contract table, the two-object split, the
`_active_handles()` fallback rule, the Handle-facing context API list, the held-preview-vs-live-apply
delegation. Add `manip_handle.py` to `applies-to`. Mark U2 status; stamp `last-verified` /
`verified-commit`.

## Out of Scope (U3+)

- Any item implementing `manip_handles()` (U3, one PR per item — carries Ctrl angle-constrain,
  gridline parallel-delta, wall-endpoint propagation, constraint solver semantics).
- Deleting `provides_handles_for` / `_find_grip_hit` / `drawForeground` grip loop (U4).
- Selection-mode (hover/Tab-cycle/rubber-band) + elevation/3D handle providers (U5).
- Making interior-move a `Handle`.
