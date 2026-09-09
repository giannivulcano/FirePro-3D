# U3 — GripHandle framework + CircleItem migration (design of record)

**Date:** 2026-09-08
**Governing spec (update in place at wrap-up):** `docs/specs/selection-manipulator.md` (Unification Roadmap §U3)
**Prior art:** U2 Handle model — `docs/superpowers/specs/2026-09-08-u2-handle-model-design.md`
**Scope:** the *first* U3 increment (one item per PR): build the live-apply `GripHandle`
framework, fix the U2 `_begin_handle` limitation, migrate **CircleItem** onto
`manip_handles()`, and parity-test it. One shippable increment to `main`.

---

## Goal

Give scene items a way to expose their parametric grips as `Handle`s that the
`SelectionManipulator` renders, hit-tests, and commits — so a grip drag becomes
one more thing the manipulator owns, not a parallel system. This PR lands the
framework plus the simplest real item (CircleItem) as the pattern-establisher.
Later PRs migrate the remaining ~20 items one at a time; U4 then deletes the
legacy grip paths entirely.

## Motivation

v1/U1/U2 left **two** systems that both mean "edit the selected thing": the
legacy per-item grip protocol (`grip_points()`/`apply_grip()` rendered by
`Model_View.drawForeground`, hit-tested by `scene_tools._find_grip_hit`, with the
drag lifecycle living in `Model_Space`) and the `SelectionManipulator`. Every v1
smoke bug (double handles, deselect-on-handle-press, stolen press) is the same
failure mode: two systems fighting one item. U3 migrates items onto the
manipulator's `Handle` model so each item has **one** render path, **one**
hit-test, **one** undo funnel. `apply_grip(index, pos)` survives as the mutation
primitive the new handles call (DRY — the edit math is not rewritten).

## Architecture & Constraints

### The `GripHandle` (live-apply Handle)

New class in `firepro3d/manip_handle.py`, alongside `ResizeHandle`/`RotateHandle`.
Unlike those (held-preview → bake on release), `GripHandle` mutates **real
geometry every move** via `apply_grip` — the live-apply drag the U2 contract was
designed to admit.

| Member | Behavior |
|---|---|
| `gesture_mode` | `"grip"` — deliberately **not** in `_SCHEMA_FOR_MODE`, so no HUD opens (legacy grips have no typed input) |
| `hud_schema` | `None` |
| `__init__(self, item, index)` | binds the target item + grip index |
| `role` | a synthetic non-rigid role (see `_begin` fix) — grip handles are not one of the 8 rigid `HandleRole`s |
| `scene_position(frame_rect)` | returns `item.grip_points()[index]` (ignores `frame_rect`; the handle rides the actual grip) |
| `shape(size, grab_pad)` | square (reuse the resize-square path) |
| `paint(...)` | square, selection-token styled (same look as a legacy grip) |
| `cursor(m)` | arrow / open-hand (no resize glyph) |
| `visible(m)` | `item.grip_hittable(index)` if defined, else `True` |
| `on_press(m)` | set `scene._grip_item = item`, `scene._grip_dragging = True`; snapshot `list(item.grip_points())` for Esc restore |
| `on_drag(m, scene_pos, mods)` | `pt = scene.get_effective_position(scene_pos)` → *(Ctrl point-transform hook — no-op for circle)* → `item.apply_grip(index, pt)` → *(sibling/propagation hook — no-op for circle)* → `scene._tools._solve_constraints(item)` → re-layout the manipulator hosts so the frame + handles track |
| `on_release(m, scene_pos, mods)` | clear `_grip_item`/`_grip_dragging`; `_solve_constraints(item)`; `commit_hook("grip")` once (→ `push_undo_state`); `m.rebake()` |
| `on_cancel(m)` | re-apply the snapshot (restore each grip to its pre-drag point); clear grip-state; **no** commit → no undo entry |
| `commit_typed(m, values)` | not used in PR#1 (no HUD); may raise `NotImplementedError` |

### Snap parity — drive the existing authority (decision A)

`GripHandle.on_drag` obtains its point from `scene.get_effective_position(scene_pos)`
— the *same* method the legacy grip path uses. That method's OSNAP branch only
fires when `_grip_dragging` is True and reads `_grip_item` as the snap-source
exclusion; `on_press` sets exactly those flags, so parity is **guaranteed** (it is
literally the same code). ALIGN (`_align_active_item`) and the grid fallback
(`get_snapped_position`) come along for free — the gridline PR later sets
`_align_active_item` in its handle's `on_press`.

The manipulator's own `_snap()` (rigid-move gesture; OSNAP-only, whole-selection
exclusion, no ALIGN/grid) is **not** reused for grip drags — it is not
grip-parity behavior.

Qt's implicit mouse grab (the `_HandleItem` host accepts the press) keeps the
scene's own `mouseMoveEvent` grip branch from firing while these flags are set,
so there is no re-entrancy with the legacy path.

### Manipulator changes (the `_begin_handle` fix)

The U2 known limitation: `_begin` installs `_active_handle = self._rigid[role]`,
so a pressed *item* handle re-resolves to the rigid handle of the same role.
Fix:

- `_begin`: `self._active_handle = (None if mode == "move" else self._rigid.get(role))`
  — `.get()` so a non-rigid `"grip"` role does not `KeyError`.
- `_begin_handle`: after `self._begin(handle.gesture_mode, …, handle.role)`,
  **overwrite** `self._active_handle = handle`. Parity-safe for rigid handles
  (`handle is self._rigid[role]`); for grip handles it installs the item's own
  handle so `on_drag`/`on_release`/`on_cancel` dispatch to it.

The existing `_active_handles()` union (`item.manip_handles()` else rigid set) and
`_sync_host_pool()` (pooled widget-less hosts) already source and render item
handles — no change needed there beyond the per-move re-layout in `on_drag`.

Live-apply mutates geometry per move, so `on_drag` re-runs the host layout (a
`rebake()`-lite) so the frame bounds and the sibling handle positions follow the
changing geometry. Held-preview handles do not (their geometry is unchanged until
release).

### Coexistence gate (no double handles / no stolen press)

Once CircleItem implements `manip_handles()`, its grips must render + hit-test
**only** through the manipulator. One shared predicate:

```python
def _item_uses_manip_handles(item) -> bool:
    fn = getattr(item, "manip_handles", None)
    return fn is not None and bool(fn())
```

- `Model_View.drawForeground` grip loop: `continue` when `_item_uses_manip_handles(item)`
  (added next to the existing `provides_handles_for` skip).
- `scene_tools._find_grip_hit`: `continue` when `_item_uses_manip_handles(item)`
  (same spot as the existing `provides_handles_for` skip).

This mirrors the existing `provides_handles_for` seam rather than extending it
(that predicate is scale-specific). U4 deletes both skips with the legacy paths.

### CircleItem migration

`CircleItem.manip_handles()` returns `[GripHandle(self, i) for i in range(len(self.grip_points()))]`
(center + 4 radius), respecting `grip_hittable` if present. Center grip →
`apply_grip(0, pt)` (translate); radius grips → `apply_grip(1..4, pt)` (resize).
Zero special drag semantics — the clean pattern-establisher.

## Design Decisions

- **Reuse `get_effective_position` by borrowing grip-state flags (A)** over
  extracting a new `resolve_grip_snap` method (B): guaranteed byte-parity, the
  working legacy snap path stays untouched during a coexistence phase, matches
  the "reuse the working architecture, don't build a parallel path" house rule.
  The borrowed-flags coupling is temporary — U4 collapses it into the single owner.
- **`gesture_mode="grip"` with no HUD schema** — legacy grips have no typed input;
  do not invent one in PR#1.
- **Framework admits all four per-item semantics as extension points**
  (point-transform-before-apply, sibling/propagation-after-apply, solver pass),
  proven by a test-only fake handle — not built for wall/gridline in this PR.
- **Coexistence gate on `manip_handles()` presence**, not extending
  `provides_handles_for`.
- **Live-apply re-lays-out hosts per move**; held-preview handles do not.

## Acceptance Criteria

- [ ] **No double handles / no stolen press:** with CircleItem migrated, its grips
      render + hit-test only via the manipulator; `drawForeground`/`_find_grip_hit`
      skip it (posted-event regression test).
- [ ] **Grip-drag parity:** posted-event drag of center + a radius grip →
      serialization byte-identical to the legacy `_drag_grip_to` path to the same
      snapped point.
- [ ] **Snap parity:** the dragged point resolves OSNAP(excl-circle) > ALIGN >
      grid, identical to legacy (OSNAP target + grid-fallback cases tested).
- [ ] **Constraint-solve + undo:** solver runs during the drag; one undo entry per
      gesture restores the pre-drag circle exactly; Esc mid-drag → no undo entry,
      geometry restored.
- [ ] **Un-migrated items unaffected:** every other item's grips still render +
      hit-test via the legacy path (LineItem regression).
- [ ] **Framework admits all four semantics** (fake-handle admissibility test:
      Ctrl point-transform, sibling apply_grip, post-apply propagation all reach
      real geometry).
- [ ] **`_begin_handle` installs the passed handle** (RED without the fix).

## Verification Checklist

- [ ] Contract units (`test_manip_griphandle.py`): `scene_position` tracks
      `grip_points`; `visible` mirrors `grip_hittable`; no HUD for `"grip"`;
      `_begin_handle` fix RED-verified.
- [ ] Posted-`QMouseEvent` parity (`test_manip_griphandle_parity.py`) on a **shown**
      view with a **real CircleItem** — never `QTest.mouseMove`/slot-level:
      byte-parity, one-undo, Esc restore, snap parity.
- [ ] Coexistence (`test_manip_griphandle_coexist.py`): migrated circle skipped by
      both legacy paths; un-migrated LineItem still legacy.
- [ ] Admissibility (`test_manip_griphandle_admissibility.py`): fake-handle four
      semantics reach real geometry.
- [ ] Each guard shown RED with the migration reverted.
- [ ] Full suite chunked, baselined vs `main` — 0 new failures (catalogued
      pre-existing failures excepted).
- [ ] Live smoke both themes: select a circle, drag center + a radius grip; verify
      snap, undo, no double handles, no stolen press.

## Out of Scope

- Migrating any item other than CircleItem (later one-per-PR increments).
- Building the wall/gridline/line special semantics (only *admitted*, not built).
- Retiring the legacy grip paths (`drawForeground` loop, `_find_grip_hit`,
  `provides_handles_for`) — that is U4, blocked until all items are migrated.
- A typed-input HUD for grip drags.
