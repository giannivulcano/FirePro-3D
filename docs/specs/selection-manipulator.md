---
status: partial          # v1 (2026-08-30) + U1 universal rigid rotate (2026-08-31); U2–U5 of the Unification roadmap remain
last-verified: 2026-08-31
verified-commit: 4e5f893
applies-to:
  - firepro3d/selection_manipulator.py
  - firepro3d/manip_math.py
  - firepro3d/model_view.py              # drawForeground grip-render seam + boundary/grip dedup
  - firepro3d/scene_tools.py             # _find_grip_hit suppression for box-native items
  - firepro3d/model_space.py             # press routing + manipulator lifecycle
  - firepro3d/paper_space.py             # SheetViewport / TextAnnotationItem handle retirement
  - firepro3d/construction_geometry.py   # RectangleItem bake-at-rest + manip capabilities; U1 manip_rotate on Line/Polyline/Circle/Arc/RegularPolygon
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
- **U2 — the `Handle` model**: define one `Handle` abstraction (role, position,
  drag→edit, commit) and a `manip_handles(self) -> list[Handle]` capability.
  Re-express the manipulator's own resize/rotate handles as `Handle`s. No item
  migration yet; pure internal refactor with identical behavior.
- **U3 — migrate items onto `manip_handles`, one per PR**: each item exposes its
  parametric points as `Handle`s whose drag calls its existing `apply_grip`
  logic. The manipulator renders/hit-tests them inside the frame. Carry the
  per-item drag semantics that live in `model_space` today (Ctrl angle-constrain
  on wall/line/gridline endpoints, gridline multi-select **parallel-delta**,
  wall-endpoint propagation, the **constraint solver** pass). Parity test each
  item (posted-event drag == legacy grip drag).
- **U4 — retire the parallel systems**: once every item provides `manip_handles`,
  delete the `drawForeground` grip loop, `scene_tools._find_grip_hit`, and the
  `provides_handles_for` predicate. One render path, one hit-test, one undo
  funnel.
- **U5 — fold in selection + other scenes**: integrate `selection-mode.md`
  (hover pre-highlight / Tab-cycle / rubber-band) against the unified handles;
  add handle providers for elevation and 3D scenes (their own selection specs).

**Risks to honor at each step** (why it's staged, not a big-bang): the constraint
solver, OSNAP-per-handle, the model full-network-snapshot vs paper macro undo
split, gridline parallel-delta, wall-endpoint propagation, and the rotation
Y-up/pivot convention all currently live in the `model_space` grip lifecycle and
must move onto the `Handle`/manipulator path without behavior drift. The v1
`provides_handles_for` seam stays until U4 removes it.

## Existing Code Context

Prototype: `D:\Custom Code\FPD Design\selection box\selection_box.py`.
Seams: `model_view.py` (`drawForeground`, grip press pipeline),
`scene_tools.py` (`_find_grip_hit`), `model_space.py` (drag lifecycle,
`push_undo_state`, `move_items`), `paper_space.py` (retiring handle code),
`paper_commands.py`, `construction_geometry.py` (RectangleItem),
`dynamic_input.py`, `snap_engine.py`, `constants.py` `SELECTION_*`,
`theme.py` selection tokens.
