---
status: proposal          # designed 2026-08-29 (grill + brainstorm), unbuilt
last-verified: 2026-08-29
verified-commit: 5726bf9
applies-to:
  - firepro3d/selection_manipulator.py   # (new — does not exist yet)
  - firepro3d/model_view.py              # drawForeground selected-item rendering seam
  - firepro3d/paper_space.py             # SheetViewport / TextAnnotationItem handle retirement
  - firepro3d/construction_geometry.py   # RectangleItem bake migration
source-tasks:
  - "TODO.md design-token follow-ups: Adopt the SelectionBox manipulator app-wide [P2]"
---

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
| `manip_rotate(angle_deg, pivot)` | v1: box-native only | baked rotate, app Y-up (CCW+) sign |
| `manip_scale(fx, fy, anchor)` | v1: box-native only | baked resize in the item's own semantics |

**Box-native (v1 rotate/scale set):** `RectangleItem`, `SheetViewport`,
`TextAnnotationItem`, `DesignAreaBadge`, note/dimension annotations.
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

- **[P1] follow-up (filed):** parametric items implement `manip_rotate`
  (baked vertex rotation) → rotation becomes universal; group rotate lights up
  for mixed selections.
- Paper viewport/text rotation semantics; movable rotation pivot; group scale.
- Hover pre-highlight / Tab-cycle / rubber-band — owned by
  `selection-mode.md` (proposal), which continues to own what-gets-selected;
  this spec owns what-happens-to-the-selection.

## Existing Code Context

Prototype: `D:\Custom Code\FPD Design\selection box\selection_box.py`.
Seams: `model_view.py` (`drawForeground`, grip press pipeline),
`scene_tools.py` (`_find_grip_hit`), `model_space.py` (drag lifecycle,
`push_undo_state`, `move_items`), `paper_space.py` (retiring handle code),
`paper_commands.py`, `construction_geometry.py` (RectangleItem),
`dynamic_input.py`, `snap_engine.py`, `constants.py` `SELECTION_*`,
`theme.py` selection tokens.
