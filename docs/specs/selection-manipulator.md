---
status: partial          # v1 (2026-08-30) + U1 (2026-08-31) + U2 Handle model (2026-09-08) + U3 GripHandle/CircleItem (2026-09-08) + U3 PolylineItem/default_grip_handles + SplineItem + LineItem/EndpointGripHandle (2026-09-09) + ArcItem + RegularPolygonItem + EllipseItem + RectangleItem/box-native/single-gate + WallSegment/propagation+sibling-Esc (2026-09-10); remaining U3 items + U4/U5 remain
last-verified: 2026-09-10
verified-commit: 189b5f9   # U3 WallSegment migration (propagation + sibling-Esc + width-grip alignment)
applies-to:
  - firepro3d/selection_manipulator.py
  - firepro3d/manip_handle.py            # U2: Handle behavior classes (base + ResizeHandle/RotateHandle); U3: GripHandle + EndpointGripHandle + default_grip_handles
  - firepro3d/manip_math.py
  - firepro3d/model_view.py              # drawForeground grip-render seam + boundary/grip dedup
  - firepro3d/scene_tools.py             # _find_grip_hit suppression for box-native items
  - firepro3d/model_space.py             # press routing + manipulator lifecycle
  - firepro3d/paper_space.py             # SheetViewport / TextAnnotationItem handle retirement
  - firepro3d/construction_geometry.py   # RectangleItem bake-at-rest + manip capabilities; U1 manip_rotate on Line/Polyline/Circle/Arc/RegularPolygon; U3 manip_handles on CircleItem + PolylineItem + SplineItem + LineItem + ArcItem
  # U1 (universal rigid rotate) added manip_rotate to the parametric items —
  # governed here for the manipulator contract; each item's geometry is owned
  # by its own spec (see SPEC-INDEX): wall.py, node.py, gridline.py, room.py,
  # floor_slab.py, roof.py, design_area.py (badge _angle, dual-serialized).
source-tasks:
  - "TODO.md: Adopt the SelectionBox manipulator app-wide [P2]"
  - "TODO.md: U1 — universal rigid rotate [P1]"
---

> **v1 status (2026-08-30):** built and merged — the manipulator drives model +
> paper selection, baked move/rotate/scale, group move, HUD readout + typed
> input, RectangleItem bake-at-rest, and paper handle retirement (parity). It
> **coexists** with the legacy per-item grip system via the `provides_handles_for`
> arbitration seam. That seam still leaks known interaction bugs (surfaced in
> live smoke — the "two systems fighting one item" class). Rather than chase
> them per-symptom, they are deferred to and structurally eliminated by the
> **Unification Roadmap** (below): U1–U4 collapse the two systems into one, at
> which point the whole bug class is impossible. Treat v1 as the transitional
> state, not the destination.

# Unified Selection Manipulator — Governing Spec

## Goal

One scene-level, capability-driven **selection manipulator** — adopted from the
`selection_box.py` prototype (attach-once `QGraphicsObject`, 8 resize handles +
rotate knob, interior-drag move, click-through, modifier keys, Esc-cancel, live
readout, pure transform math) — as the single home for selection feedback and
**rigid transforms** (move / rotate / scale) across the model and paper scenes.
Parametric grip editing (`grip_points()`/`apply_grip()`) is preserved and
rendered inside the manipulator frame; the manipulator adds what items cannot
do today: interactive rotation, group move, and a unified interaction model.

## Motivation

Selection feedback is split three ways: a view-level grip renderer in
`Model_View.drawForeground` (model scene), duplicated per-item 8-handle code in
`SheetViewport` and `TextAnnotationItem` (paper), and no interactive rotation
anywhere. ~90% of model items are parametric-grip (grips edit endpoints, width,
vertices, radii) — a uniform bounding-box scale would break them, so the
manipulator is **capability-gated**, not one-size.

## Architecture & Constraints

### The manipulator object

- New module `firepro3d/selection_manipulator.py`: `SelectionManipulator
  (QGraphicsObject)`, instantiated **once per scene** (`Model_Space`,
  `PaperScene`), added to the scene, tracks `scene.selectionChanged`, wraps the
  selection's union `manip_bounds()`, `z = 1e6`. Screen-constant children
  (`ItemIgnoresTransformations`): 8 resize `_Handle`s, one rotate `_Handle`
  (knob on a stem above the top-edge midpoint), rotate cursor. Handle sizing:
  px in the model scene, paper-mm in the paper scene (theming.md split).
- The prototype's **pure transform math** is ported verbatim and unit-tested:
  `resize_factors` (keep-aspect, from-center, negative-factor mirroring),
  `rotate_delta` (absolute-angle snap), `move_delta` (ortho), `_about`,
  `transform_angle_deg`.

### Capability protocol (duck-typed, house idiom)

| Method | Who implements | Meaning |
|---|---|---|
| `manip_bounds() -> QRectF` | all (fallback `sceneBoundingRect()`; cosmetic-pen items provide it explicitly) | box the frame wraps |
| `manip_translate(dx, dy)` | all selectable items (adapter over `translate()`/`moveBy()`) | baked move |
| `manip_rotate(angle_deg, pivot)` | **U1: all parametric items** (wall, node→pipes ride, gridline, room [group-follow only], floor, roof, line/polyline/circle/arc/regular-polygon) + box-native (rect, badge) | baked rotate, app Y-up (CCW+) sign — `CAD_Math.rotate_point(p, pivot, -angle_deg)`; angle-carriers (gridline `_angle_deg`, arc `_start_deg`, regpoly `_rotation_deg`, badge `_angle`) accumulate `% 360` |
| `manip_scale(fx, fy, anchor)` | v1: box-native only | baked resize in the item's own semantics |

**Box-native (v1 rotate/scale set):** `RectangleItem`, `SheetViewport`,
`TextAnnotationItem`, `DesignAreaBadge`, note/dimension annotations. An item
adopts only the capabilities that are semantically valid for it (e.g. the
fixed-layout badge may implement translate+rotate but not scale) — the handle
gating reads what each item actually implements.
`manip_scale` maps onto each item's own model — RectangleItem corner geometry;
TextAnnotation `wrap_width_mm`/`box_height_mm` + reposition; SheetViewport
**crop-rect change at fixed scale** (on-paper size = crop×scale invariant —
paper-space.md owns that rule).

**Handle gating:** frame + interior-move whenever selection non-empty; rotate
knob iff every selected item implements `manip_rotate` (v1: single box-native
item; paper viewport/text do NOT implement it in v1 — no knob there); 8 resize
handles iff a single item with `manip_scale`. Parametric single-select: frame +
the item's own `grip_points()` (unchanged pipeline). Multi-select: frame +
group move only.

### Event routing & coexistence

- View-level `scene_tools._find_grip_hit` continues to run **before** scene
  dispatch — parametric grip clicks are consumed before the manipulator sees
  them (selection-mode.md §8 grip-priority satisfied by existing event order).
- Plain click inside the frame falls through to normal picking (prototype
  click-through), so overlapping items stay selectable.
- `Model_View.drawForeground` keeps drawing **parametric grips**; its dashed
  selection boundary is superseded for manipulator-wrapped items (one boundary,
  drawn by the manipulator frame).
- Styling: accent-styled from theme `selection` / `selection_active` tokens
  (theming.md owns the tokens). Final handle/knob look is **mockup-gated**
  (rendered candidates → user picks) before implementation binds.

### Transform lifecycle (held preview, bake on release)

1. **Press** (handle/knob/interior): snapshot per-item pre-drag state; record
   the grab point.
2. **Move**: delta from pure math. **Snap-then-transform** — move snaps the
   dragged grab point via `snap_engine.find(…, held=…)`; resize snaps the
   dragged handle point; rotate takes no OSNAP (Shift = 15° absolute snap).
   Preview = prototype held transform prepended to each item's `transform()`.
   No geometry edits, no constraint solve during the drag.
3. **Release**: clear preview transforms → **bake once** through each item's
   `manip_*` (real mm coords) → constraint solver once (existing release path)
   → undo commit (below) → frame rebake.
4. **Esc** mid-drag: drop preview transforms, restore snapshots — no geometry
   churn, no undo entry.

**Baked-at-rest rule:** committed state carries **no Qt item transform**.
RectangleItem reconciles by keeping `_angle` as a serialized **data field**
(a rotated rect cannot be axis-aligned coords) while dropping the held
`setRotation`/`setTransformOriginPoint` — paint/shape/grips/snap read
angle-aware local geometry. Old saves load unchanged (same fields; only the
rendering path changes).

### HUD (readout + typed input)

Three `DynamicInputHud` transform schemas: `manip_move` (dX/dY),
`manip_resize` (W/H), `manip_rotate` (Angle, Y-up, `FieldKind.ANGLE`).
Passive: `set_values()` reseeded every move — **the HUD is the readout** (the
prototype's `_Readout` child is not ported). Typed: engage → `committed` →
apply the exact value → bake + undo as if released.

### Undo & domains

- One undo entry per gesture: **model** = single `push_undo_state()` after the
  bake; **paper** = `beginMacro` + existing per-item commands
  (`ViewportGeometryCommand`, `ResizeTextBoxCommand`, move equivalents) +
  `endMacro`.
- **Mixed model+paper selections are disallowed** (separate scenes/stacks).
- Group move resolves Sprinkler → parent Node (as `move_items` does). Items
  lacking a translate path are **excluded from the wrap and logged** — never
  silently skipped.

## Design Decisions

- **Hybrid architecture** (scene-child manipulator + untouched parametric grip
  pipeline) over full-prototype-adoption (rewires a working system for churn)
  and over view-level reimplementation (loses the prototype's proven
  interaction model; re-duplicates for paper).
- **Held-preview / bake-on-release** over incremental per-move baking: one
  bake per gesture matches one-undo-per-gesture, avoids repeated float drift
  and per-move constraint solves; Esc is trivial.
- **Capability gating** over uniform box transforms: bounding-box scale is
  semantically wrong for parametric items; they keep their grips.
- **Rotation as data, not transform, at rest** (RectangleItem `_angle` field);
  interactive rotation generalizes from RectangleItem's proven pattern.
- Full prototype interaction set in v1 (click-through, Esc, Shift
  ortho/aspect/15°, Ctrl scale-about-center); **movable pivot deferred**.

## Acceptance Criteria

- [ ] One `SelectionManipulator` per scene (model + paper); frame + interior
      move on every selectable item; accent-tokened styling (mockup-approved).
- [ ] Handles capability-gated exactly as specified (knob/8-handles/parametric
      grips-in-frame/multi-select-move-only).
- [ ] Universal baked move incl. multi-select group move; grab-point OSNAP.
- [ ] Rotate + scale on box-native items; Shift-15°; typed-angle via HUD;
      Y-up readout; RectangleItem baked-at-rest migration, old saves load.
- [ ] Paper per-item handle code retired with behavior parity (crop×scale rule,
      text box model, identical command outcomes).
- [ ] Esc restores pre-drag state exactly; one undo per gesture per domain;
      no mixed-domain selection.
- [ ] Grip click still beats interior-move (posted-event regression test).

## Verification Checklist

- [ ] Pure-math unit tests (mirroring, snap, Y-up signs) — red-verified.
- [ ] Posted-`QMouseEvent` interaction tests via `app.sendEvent`
      (press→move→release, Esc, click-through, modifiers) — never
      `QTest.mouseMove` / slot-level calls.
- [ ] No-op byte-parity: press+release without move → serialization
      byte-identical; Esc-cancel likewise.
- [ ] Undo round-trip: N-item group move → one undo restores all coords.
- [ ] Paper replacement parity diffed line-by-line against the retired
      `SheetViewport`/`TextAnnotationItem` handle code.
- [ ] Full suite green (chunked per project convention); live smoke in both
      scenes, both themes.

## Out of Scope (staged)

- **[P1] SHIPPED (U1, 2026-08-31):** parametric items implement `manip_rotate`
  (baked vertex rotation) → rotation is universal; group rotate lights up for
  mixed selections. (Annotations remain translate-only — a mixed selection that
  includes a note/dimension hides the rotate knob; adding rotate there is the
  next label-rotate follow-up.)
- Paper viewport/text rotation semantics; movable rotation pivot; group scale.
- Hover pre-highlight / Tab-cycle / rubber-band — owned by
  `selection-mode.md` (proposal), which continues to own what-gets-selected;
  this spec owns what-happens-to-the-selection.

## Unification Roadmap (proposal — the intended end-state)

**Problem this fixes.** v1 ships **two** systems that both mean "manipulate the
selected thing": the legacy per-item grip protocol (`grip_points()`/
`apply_grip()` rendered by `Model_View.drawForeground`, hit-tested by
`scene_tools._find_grip_hit`) and the `SelectionManipulator`. `provides_handles_for`
is an **arbitration predicate** deciding which owns an item — a transitional
seam, not the destination. Every v1 smoke bug (double handles, deselect-on-
handle-press, stolen press) was the same failure mode: two systems fighting over
one item. A single owner makes that whole bug class impossible.

**Target.** One capability-driven handle system. Each item exposes ALL its
editable affordances — rigid-transform handles (resize/rotate) AND parametric
handles (vertices, endpoints, radius, sweep) — as one kind of thing: a `Handle`
(role + scene position + drag-behavior + commit). The manipulator is the single
renderer, hit-tester, and undo funnel for every handle. A polygon vertex handle
and a corner-scale handle are just two roles in one system. No `drawForeground`
grip loop, no `_find_grip_hit`, no `provides_handles_for` — because there is one
owner. `grip_points()`/`apply_grip()` survive only as the *mutation primitives*
parametric Handles call (DRY — reuse, don't rewrite the edit math).

**Phased path** (each step independently shippable + parity-tested):

- **U1 — universal rigid rotate** ✅ **DONE (2026-08-31):** every parametric item
  implements `manip_rotate` (baked). Group rotate lights up. Manipulator now
  does rigid transforms for ALL items. Room is group-follow only
  (`MANIP_NO_SOLO_ROTATE`); the fitting-refresh step is shared across
  move/rotate/scale bakes. **Bug fixed en route:** `hit_test` mapped
  `ItemIgnoresTransformations` handles with plain `mapFromScene` (correct only at
  m11==1), so the rotate knob was unhittable at the fit-to-view zoom and the
  press cleared the selection — now mapped via the view's `deviceTransform`.
- **U2 — the `Handle` model** ✅ **DONE (2026-09-08):** defined one `Handle`
  behavior abstraction (role, position, drag→edit, commit) + a `manip_handles()`
  capability with a live-fallback sourcing path; re-expressed the manipulator's
  own resize/rotate handles as `Handle`s. Pure internal refactor — the 6 manip
  test files pass unmodified. See **"U2 — Handle model (as-built)"** below.
- **U3 — migrate items onto `manip_handles`, one per PR** — **IN PROGRESS.**
  ✅ **CircleItem DONE (2026-09-08)** — landed the live-apply `GripHandle`
  framework + the `_begin_handle` fix + coexistence gate (see "U3 — GripHandle
  (as-built)" above). ✅ **PolylineItem DONE (2026-09-09)** — extracted the
  shared `default_grip_handles(item, circular=frozenset())` helper
  (`manip_handle.py`) that is the common body of every item's `manip_handles()`
  (loop `grip_points()` → `GripHandle`, `grip_hittable`-filtered, square except
  `circular` indices, which render as round discs); CircleItem refactored onto it
  (`circular={0}` centre), Polyline passes all vertex indices (round; no
  move-centre grip — move is interior drag). ✅ **SplineItem DONE (2026-09-09)**
  — control points are the spline's vertices → all round (`circular=` all
  control-point indices); same shape as Polyline, no special semantics.
  ✅ **LineItem DONE (2026-09-09)** — first item with per-item semantics:
  endpoints (grips 0, 2) round + Ctrl-angle-constrained against the opposite
  endpoint via a reusable `EndpointGripHandle(GripHandle)` (`_transform_point`
  → scene `_constrain_angle`; also serves Wall/Gridline endpoints later);
  midpoint (grip 1) round (a move grip — translates the whole line) + plain
  `GripHandle` (no constrain — matches legacy). ✅ **ArcItem DONE (2026-09-10)** — zero special
  semantics (the legacy grip path explicitly excludes arc from Ctrl-constrain):
  `default_grip_handles(self, circular={0,1,2})` (centre + start + end, all round
  — centre = move grip, start/end = the arc's geometric endpoints). Same shape as
  Spline/Polyline. ✅ **RegularPolygonItem DONE (2026-09-10)** — zero special
  semantics (legacy grip path excludes polygon from Ctrl-constrain):
  `default_grip_handles(self, circular=all indices)` (centre + N vertices, all
  round — centre = move, vertices = the polygon's defining points; dragging a
  vertex resizes + rotates, the edit math living in `apply_grip`). Handle count
  tracks `_sides`. ✅ **EllipseItem DONE (2026-09-10)** — mirrors CircleItem (an
  ellipse is a generalized circle): `default_grip_handles(self, circular={0})`
  (centre round move grip; the 4 axis-endpoint sizing grips — major rx=1,2 [also
  rotates] / minor ry=3,4 — square). Zero special semantics (not Wall/Gridline/
  Line → no Ctrl-constrain); not box-native (no `manip_scale`). ✅ **RectangleItem
  DONE (2026-09-10, box-native special)** — rect now provides `manip_handles()`
  (9 grips) so `_item_uses_manip_handles` is the **single coexistence gate** (the
  legacy paths drop their separate `provides_handles_for` skip). `_active_handles`
  returns the rigid RESIZE set for the box-native (unrotated) rect — grips don't
  double up; a ROTATED rect (scale cap dropped) surfaces its parametric grips
  (live-apply; `apply_grip` resizes in the local frame — replaces the legacy green
  grips). `provides_handles_for` kept internal (`_active_handles` +
  `_frame_is_redundant`). Each
  item exposes its parametric points as `GripHandle`s
  whose drag calls its existing `apply_grip`; the manipulator renders/hit-tests
  them inside the frame. Carry the per-item drag semantics that live in
  `model_space` today (Ctrl angle-constrain on wall/line/gridline endpoints via
  `_transform_point`; gridline multi-select **parallel-delta** + wall-endpoint
  propagation via `_after_apply`; the **constraint solver** pass — all admitted
  by the framework). Parity test each item (posted-event drag == legacy grip
  drag). ✅ **WallSegment DONE (2026-09-10)** — the FIRST migrated item with
  **sibling mutation** (its drag moves OTHER items). `manip_handles()` returns 4
  live-apply grips: two `WallEndpointGripHandle(EndpointGripHandle)`s (endpoints
  0/1, round, Ctrl-constrain against the opposite endpoint — opp 1↔0) that add
  **propagation** (`_after_apply` → `scene._propagate_wall_endpoint`: every OTHER
  wall endpoint coincident with the pre-move position follows) plus **atomic
  Esc-restore of siblings** (`_extra_snapshots`/`_restore_extra` →
  `scene._snapshot_wall_endpoints`/`_restore_wall_endpoints`, homed in
  `WallPlacementController`, reached via duck-typed scene bridges); a mid (2) round
  move grip (translates the whole wall) and a width (3) square thickness grip,
  both plain `GripHandle`s that never propagate. The rotate knob coexists (wall
  has `manip_rotate`, like EllipseItem); not box-native (no `manip_scale`).
  Remaining, simplest-first:
  Gridline
  (+parallel-delta), Room, DesignArea,
  **Text blocks — both BOUNDING-BOX-governed (box-native, like Rectangle: frame +
  resize + move + rotate, NOT a single MText position grip)**: (a) the 2D-geometry
  MTEXT text block `NoteAnnotation` (model scene; has a ribbon button; TODAY it is
  translate-only with a single position grip — must be UPGRADED to box-native:
  add `manip_scale`/`manip_rotate` + a bounding box, decide what resize does
  [wrap-width vs font scale]); (b) the paper `Sheet Text block`
  `TextAnnotationItem` (already box-native). `DimensionAnnotation` migrates
  alongside (translate-only today), Floor, Roof, and the
  elevation/detail/view-marker items.
- **U4 — retire the parallel systems**: once every item provides `manip_handles`,
  delete the `drawForeground` grip loop, `scene_tools._find_grip_hit`, and the
  `provides_handles_for` predicate. One render path, one hit-test, one undo
  funnel. *(Progress 2026-09-10: the legacy-path SKIP is already a single gate —
  `_item_uses_manip_handles` — after the RectangleItem box-native migration;
  `provides_handles_for` is now internal-only, used by `_active_handles` +
  `_frame_is_redundant`.)*
- **U5 — fold in selection + other scenes**: integrate `selection-mode.md`
  (hover pre-highlight / Tab-cycle / rubber-band) against the unified handles;
  add handle providers for elevation and 3D scenes (their own selection specs).

**Risks to honor at each step** (why it's staged, not a big-bang): the constraint
solver, OSNAP-per-handle, the model full-network-snapshot vs paper macro undo
split, gridline parallel-delta, wall-endpoint propagation, and the rotation
Y-up/pivot convention all currently live in the `model_space` grip lifecycle and
must move onto the `Handle`/manipulator path without behavior drift. The v1
`provides_handles_for` seam is no longer a legacy-path *skip* (unified to
`_item_uses_manip_handles` at the RectangleItem migration) but stays as an
internal helper until U4 removes it.

## U2 — Handle model (as-built, 2026-09-08)

Design of record: `docs/superpowers/specs/2026-09-08-u2-handle-model-design.md`.

**Two objects, wrap-not-merge.** `Handle` (in new `firepro3d/manip_handle.py`) is a
plain behavior object; `_HandleItem` (renamed from `_Handle`, in
`selection_manipulator.py`) is the screen-constant `QGraphicsItem` host that
forwards `paint`/`shape`/`cursor`/`mousePress` to its `Handle`. Rigid handles keep
rendering via role-keyed hosts (`manip._handles[role]` preserved); widget-less
item handles (U3) get pooled hosts (`_sync_host_pool`).

**`Handle` contract:** `role`, `gesture_mode` (`"resize"`/`"rotate"` → sets
`_mode`), `hud_schema`; `scene_position(rect)`, `shape(*,size,grab_pad)`,
`paint(painter,*,size,border,fill,hover,border_width)`, `cursor(m)`, `visible(m)`;
lifecycle `on_press/on_drag/on_release/on_cancel(m,…)`, `commit_typed(m,values)`,
`hud_values(m)`. Subclasses: `ResizeHandle`, `RotateHandle`. (U3 adds
`GripHandle` — live-apply.)

**Delegation, no drag-model branch.** The manipulator owns drag *state* +
the held-preview toolkit (`_apply`/`_bake_*`/`_snap`/`_feed_hud`/`_snapshot_items`/
`_restore_preview` — bodies unchanged); `_begin`/`_update`/`_finish`/
`_on_hud_committed`/`cancel_drag` delegate the per-kind work to
`_active_handle.on_*`. Held-preview handles (resize/rotate) *orchestrate* the
toolkit; a live-apply handle (U3 parametric) calls `apply_grip`+solve in `on_drag`
and never touches `_apply` — the manipulator is oblivious. Interior-drag **move
stays a manipulator-level gesture** (not a Handle).

**`manip_handles()` sourcing (option B, live-with-fallback):**
`_active_handles()` returns `union(item.manip_handles() for items) or
rigid_set` — today no item implements it, so the rigid fallback runs (behavior
identical). `_layout` positions/gates the rigid role-hosts and syncs the pool for
any item handles.

**Handle-facing context API** (manipulator privates a Handle may read):
`_snap`, `_apply`, `_bake_move/_bake_scale/_bake_rotate`, `_feed_hud`,
`_restore_preview`, `_end_drag`, `_last_factors`, `_R0`/`_B0`/`_start_scene`/`_D`/
`_base_angle`, the `_*_at_press` release-bake snapshot trio, the `_typed_*`
typed-commit trio, `_ROTATE_SNAP_DEG`, `_moved`, `_resize_cursor`,
`_show_scale_handles`/`_show_rotate_knob`.

**Known limitation → U3 must fix:** `_begin_handle(handle, …)` calls
`_begin(handle.gesture_mode, …, handle.role)`, and `_begin` installs
`_active_handle = self._rigid[role]` — so a *pressed item handle* currently
re-resolves to the **rigid** handle of the same role, not the item's own handle.
Harmless in U2 (rigid-only; the admissibility test proves the *dispatch* admits
live-apply by installing the fake directly). **U3 must make `_begin_handle`
install the passed handle** (e.g. `_active_handle = handle` after `_begin`) so a
pooled/item host press drives the item's handle. Parity-safe (for rigid handles
`handle is self._rigid[role]`).

**Tests:** `tests/test_manip_handle.py` (contract units + knob-outline-width
guard), `tests/test_manip_handle_admissibility.py` (live-apply lifecycle +
`manip_handles()` consumption + legacy seams intact),
`tests/test_manip_u2_parity.py` (posted-event vs slot byte-parity + no-op/Esc).
The 6 pre-U2 manip test files pass unmodified.

## U3 — GripHandle (as-built, first increment: CircleItem, 2026-09-08)

Design of record: `docs/superpowers/specs/2026-09-08-u3-griphandle-circleitem-design.md`.

First per-item migration onto `manip_handles()`. Ships CircleItem; the remaining
items follow one-per-PR (simplest-first, see the roadmap bullet).

**`GripHandle(Handle)`** (`manip_handle.py`) — the live-apply handle. `role =
HandleRole.GRIP` (new non-rigid enum member, absent from `_rigid`);
`gesture_mode = "grip"` (absent from `_SCHEMA_FOR_MODE` → **no HUD**, matching
legacy grips); `__init__(item, index)`. `scene_position` ignores the frame and
returns `item.grip_points()[index]` (rides the live grip); `visible` mirrors
`grip_hittable`. **Lifecycle** mutates real geometry every move via the item's
`apply_grip(index, pt)` (the DRY mutation primitive — edit math is not rewritten):
- `on_press`: borrow the scene's grip-state (`_grip_item`/`_grip_dragging`,
  saving prior values) so the snap authority runs exactly as legacy; snapshot all
  grip points for Esc.
- `on_drag`: `pt = scene.get_effective_position(scene_pos)` (getattr fallback for
  plain scenes) → `_transform_point` hook → `apply_grip` → `_after_apply` hook →
  `scene._tools._solve_constraints(item)` → `m._reflow_live()`. Records
  `self._last_pt`.
- `on_release`: capture `moved`; re-apply the release point **only if it differs
  from `_last_pt`** (Qt normally delivers a final move at the release position →
  re-apply skipped, so a future `_after_apply` propagation override cannot
  double-fire); `_clear_grip_state`; `m._end_drag()`; then if `moved`, solve +
  `commit_hook("grip")` (one undo per gesture).
- `on_cancel`: re-apply the snapshot for **only the dragged grip**
  (`apply_grip(self.index, snapshot[index])`) + `_restore_extra` for sibling/
  propagated state; `_clear_grip_state`; **no** commit. (Restoring *every* grip
  corrupts index-dependent grips — LineItem's midpoint `apply_grip` translates
  the whole line, so replaying it mid-restore shifts the endpoints; a derived
  grip like the midpoint recomputes from the endpoints anyway. Fixed 2026-09-09
  during the LineItem migration.)

**Four per-item semantics are ADMITTED (not built here) as extension points:**
`_transform_point` (Ctrl angle-constrain), `_after_apply` (gridline
parallel-delta / wall-endpoint propagation), `_extra_snapshots`/`_restore_extra`
(siblings), plus the always-run solver pass. Proven by
`test_manip_griphandle_admissibility.py` fake-handle overrides.

**Snap parity** = drive the scene's own `get_effective_position` via the borrowed
flags (OSNAP-excl-dragged > ALIGN > grid) — guaranteed byte-identical to legacy;
the rigid-move `_snap` is **not** reused for grips.

**Manipulator changes:** `_begin` uses `_rigid.get(role)` (tolerates the
non-rigid GRIP role); `_begin_handle` installs the passed handle and fires its
`on_press` once (grip only; rigid handles still get their single `on_press` from
`_begin`); `hit_test` iterates `_handles` **+ `_host_pool`** (pooled item-handle
hosts); new `_reflow_live()` recomputes the frame + repositions rigid + pooled
hosts every live-apply move **without rebuilding the handle list** (stable
`_active_handle`).

**Coexistence gate** (one render path, one hit-test): module-level
`_item_uses_manip_handles(item)` (in `selection_manipulator.py`) — true when the
item's `manip_handles()` returns a non-empty list. `Model_View.drawForeground`'s
grip loop and `scene_tools._find_grip_hit` both `continue` past such items. This
is now the **single** legacy-path skip: since RectangleItem (the only model-scene
box-native item) provides `manip_handles`, the separate `provides_handles_for`
skip was removed from both paths (2026-09-10). `provides_handles_for` remains an
internal helper (`_active_handles` picks the rigid resize set for a box-native
single item; `_frame_is_redundant`). U4 deletes the legacy paths + the helper.

**`default_grip_handles(item, circular=frozenset())`** (`manip_handle.py`) — the
shared body of every migrated item's `manip_handles()`: one `GripHandle` per
`grip_points()` index, `grip_hittable`-filtered, square except indices in
`circular` (rendered as discs — centre/move grips). Extracted on the 2nd
migration to keep the ~15 per-item `manip_handles()` from drifting; per-item
drag semantics live on `GripHandle` subclass hooks, not here.

**CircleItem.manip_handles()** → `default_grip_handles(self, circular={0})`:
5 handles (center + 4 radius). Center → `apply_grip(0)` (translate); radius →
`apply_grip(1..4)` (resize). Zero special semantics — the pattern-establisher.

**PolylineItem.manip_handles()** → `default_grip_handles(self, circular=all
vertex indices)`: one round handle per vertex, each → `apply_grip(index)` (move
vertex + rebuild). No move-centre grip (move is the manipulator's interior
drag); no special drag semantics.

**SplineItem.manip_handles()** → `default_grip_handles(self, circular=all
control-point indices)`: one round handle per control point, each →
`apply_grip(index)` (move control point + `_regenerate`). Control points are the
spline's vertices (no midpoints); no move-centre grip; no special drag semantics.

**LineItem.manip_handles()** → `[EndpointGripHandle(0, opp=2),
GripHandle(1), EndpointGripHandle(2, opp=0)]`. Endpoints round + Ctrl-angle-
constrained against the opposite endpoint; midpoint round + plain — it translates
the whole line, so it is a **move grip** (round per the house rule), not a
geometric midpoint. **`EndpointGripHandle(GripHandle)`** (`manip_handle.py`) is the
reusable per-item Ctrl-constrain handle: `_transform_point` projects the dragged
point onto the nearest angle increment ray from `grip_points()[opposite_index]`
via the scene's `_constrain_angle` (the legacy grip authority; getattr-guarded
for headless). Reused by Wall/Gridline endpoints (opp 1↔0) in their PRs.

**WallSegment.manip_handles()** → `[WallEndpointGripHandle(0, opp=1),
WallEndpointGripHandle(1, opp=0), GripHandle(2), GripHandle(3, square)]`.
Endpoints (0, 1) round + Ctrl-angle-constrained against the opposite endpoint
(inherited from `EndpointGripHandle`); mid (2) round move grip (translates the
whole wall); width (3) square thickness grip, aligned to the wall via
`grip_render_angle(3)` = the centerline's Y-up angle (so the square's edges track
the wall orientation, like RectangleItem's edge grips / EllipseItem's axis grips;
the round grips ignore it). The FIRST migrated item whose drag
mutates OTHER items, so **`WallEndpointGripHandle(EndpointGripHandle)`**
(`manip_handle.py`) adds two wall-only semantics on top of the Ctrl-constrain:
(1) **propagation** — `_transform_point` captures the endpoint's pre-apply
position per frame and `_after_apply` calls `scene._propagate_wall_endpoint`, so
every OTHER wall endpoint coincident with the old position follows to the new one
(joined polyline walls stay joined); (2) **atomic Esc-restore of siblings** —
`_extra_snapshots` (in `on_press`) snapshots every other wall's endpoints via
`scene._snapshot_wall_endpoints(self.item)` and `_restore_extra` (in `on_cancel`)
re-applies them via `scene._restore_wall_endpoints`, because the base `on_cancel`
only restores the dragged grip. Both wall-graph helpers live in
`WallPlacementController`, reached through thin `Model_Space` bridges; all scene
calls are getattr-guarded so a headless plain scene degrades to no-propagation.
The mid/width grips are plain `GripHandle`s and never propagate. `apply_grip`
carries the edit math (endpoints, translate, thickness) unchanged; the rotate
knob coexists (wall has `manip_rotate`); not box-native.

**ArcItem.manip_handles()** → `default_grip_handles(self, circular={0, 1, 2})`:
3 handles (centre + start + end), all round — centre is a move grip, start/end
are the arc's geometric endpoints (curve termini), per the house rule. **Zero
special drag semantics**: the legacy grip drag (`model_space.py`) explicitly
excludes arc from Ctrl-constrain (*"rect, arc, polygon, circle … must NOT be
affected by this block"*), so no `EndpointGripHandle`/`_transform_point`. Same
shape as Spline/Polyline; `apply_grip` already carries the edit math (centre =
translate; start = radius+start-angle; end = span-angle).

**RegularPolygonItem.manip_handles()** → `default_grip_handles(self,
circular=all indices)`: centre + N vertices, all round (centre = move; each
vertex = a defining point — dragging it resizes + rotates). Handle count tracks
`_sides`. Zero special semantics (legacy grip path excludes polygon from
Ctrl-constrain); `apply_grip` carries the edit math.

**EllipseItem.manip_handles()** → `default_grip_handles(self, circular={0})`:
centre + 4 axis endpoints. Mirrors CircleItem (an ellipse is a generalized
circle): centre = round move grip; the axis-endpoint sizing grips (major rx=1,2,
which also rotate; minor ry=3,4) render **square** — same rationale as circle
radius grips (points on a closed curve for sizing, not curve termini). Zero
special semantics (not Wall/Gridline/Line → no Ctrl-constrain); not box-native
(no `manip_scale`); `apply_grip` carries the edit math. The 4 square grips are
**rotated to the ellipse's orientation** (radial alignment) via the
`grip_render_angle` hook (below), so they stay aligned to the axes at placement
angle and after a rotate.

**RectangleItem.manip_handles()** (box-native special) → `default_grip_handles(
self, circular={0,2,4,6,8})`: the 9 rect grips (corners 0,2,4,6 + centre 8 round;
edge midpoints 1,3,5,7 square). These surface **only for a ROTATED rect** — an
unrotated rect is box-native (`provides_handles_for` → `_active_handles` returns
the rigid resize set), so it shows the 8 resize handles + rotate knob and the
grips don't double up. A rotated rect drops the `scale` cap → its parametric grips
drive edits via `apply_grip` (resize in the rect's own local frame, no shear),
replacing the legacy green grips. `grip_render_angle` returns `_angle` so the
square edge-midpoint grips align with the rotated edges. Providing `manip_handles`
makes `_item_uses_manip_handles` the single coexistence gate (see above). The
**centre MOVE grip is present for BOTH states**: the rotated rect exposes it as
grip 8 of its parametric handles; the unrotated (box-native) rect adds it via
`manip_box_extra_handles()` → `_active_handles` appends it to the rigid resize set
(the rigid set has no centre handle — move is otherwise interior-drag only).

**Grip-shape house rule (2026-09-09 smoke; refined 2026-09-10).** Vertex/endpoint
grips and centre/**move** grips render **round** (disc); only inert/derived
convenience grips (a pure geometric midpoint that does *not* move the whole item)
stay **square**. The test is *function, not position*: a grip that translates the
whole item is a move grip → round, even when it sits at the geometric midpoint
(LineItem's midpoint grip). Each item passes its round indices to
`default_grip_handles` (`circular=`): CircleItem `{0}` (centre; radius grips are
non-vertex → square), PolylineItem all vertices. Legacy `Model_View`
`drawForeground` drew every grip square (`model_view.py` `drawRect` 8×8); this
rule supersedes that look as items migrate.

**Square-grip orientation hook — `grip_render_angle(index) -> float`** (added
2026-09-10). Optional per-item hook; when present, `GripHandle` rotates a
**square** grip's render + hit-shape by the returned Y-up degrees so its edges
align with the item's orientation (radial alignment), applied as `rotate(-ang)`
in both `paint()` and `shape()` (same value → hit-test matches render; a square
is 90°/reflection-symmetric so the sign is immaterial). **Circular grips ignore
it** (a disc is rotation-invariant). Absent → 0 (axis-aligned; the default for
every other migrated item, including CircleItem's square radius grips, whose
axis-aligned radials look identical rotated). EllipseItem returns `_rotation_deg`
so its 4 square axis grips track the ellipse's placement angle and post-hoc
rotate. `_HandleItem.boundingRect` already reserves `√2·half` for a rotated
square.

*Live during the rotate held-preview:* the rotate knob is held-preview (the
item's angle isn't mutated until the release bake), so screen-constant
(`ItemIgnoresTransformations`) handles would keep their pre-drag orientation
while the frame turns. `Handle._live_preview_rotation()` returns the
manipulator's `_preview_rotation_deg()` (= `_yup_angle_from_delta(self._D)` while
`_mode == "rotate"`, else 0); it's added to a square grip's `_render_angle` **and**
used by `RotateHandle.shape/paint` to swing the knob+stem with the frame. Because
it's the same angle the release bake applies, there's no jump on commit. The
manipulator sets `handle._m` on every handle (rigid at construction; grips in
`_sync_host_pool`), and `_apply` repaints all handle hosts each rotate move
(their orientation depends on `_D`, which a transform-change repaint doesn't
otherwise track). This makes the rotate knob swing for **any** rotatable item
(box-native rects included), not just the ellipse.

**Known follow-up (filed):** `_item_uses_manip_handles` treats an empty
`manip_handles()` as "not migrated"; unreachable for CircleItem (always 5), but a
future item with fully state-dependent hittability should be handled when it
lands.

**Tests:** `tests/test_manip_griphandle.py` (contract + `_begin_handle` fix),
`tests/test_manip_griphandle_admissibility.py` (four-semantics + `on_release`
ends drag + no double `_after_apply`), `tests/test_manip_griphandle_coexist.py`
(gate), `tests/test_manip_griphandle_parity.py` (CircleItem posted-event
byte-parity vs legacy `apply_grip`, one-undo, Esc restore),
`tests/test_manip_griphandle_polyline_parity.py`,
`tests/test_manip_griphandle_spline_parity.py`,
`tests/test_manip_griphandle_line_parity.py` (Polyline/Spline/Line parity; Line
adds Ctrl-constrain-wiring + midpoint-translate), and
`tests/test_manip_griphandle_arc_parity.py` (Arc parity — shape, end-grip/span
legacy-apply match, posted start-grip drag, one-commit, Esc-restore), and
`tests/test_manip_griphandle_polygon_parity.py` (RegularPolygon parity — shape,
handle-count-tracks-sides, centre/vertex legacy-apply match, posted centre+vertex
drag, one-commit, Esc-restore, gate recognition), and
`tests/test_manip_griphandle_ellipse_parity.py` (Ellipse parity — shape [centre
round, axis grips square], major/minor/centre legacy-apply match, posted
major+centre drag, one-commit, Esc-restore, gate recognition), and
`tests/test_manip_griphandle_rect_parity.py` (Rectangle box-native — shape, gate
True both states, unrotated shows rigid resize handles [not grips], rotated shows
9 parametric grips, rotated-corner apply parity, posted centre-drag, `_find_grip_hit`
skip both states).
`test_scene_tools.py` asserts
the migrated circle/polyline/spline/line/arc/**rect** are skipped by
`_find_grip_hit` (the rect legacy-hit test became the "migrated → skipped"
contract), and its generic `_find_grip_hit` mechanic tests use a migration-
agnostic `_GripStub` (they used to ride `LineItem`, which now skips the legacy
path). All pre-U3 manip test files pass unmodified.

## Existing Code Context

Prototype: `D:\Custom Code\FPD Design\selection box\selection_box.py`.
Seams: `model_view.py` (`drawForeground`, grip press pipeline),
`scene_tools.py` (`_find_grip_hit`), `model_space.py` (drag lifecycle,
`push_undo_state`, `move_items`), `paper_space.py` (retiring handle code),
`paper_commands.py`, `construction_geometry.py` (RectangleItem),
`dynamic_input.py`, `snap_engine.py`, `constants.py` `SELECTION_*`,
`theme.py` selection tokens.
