---
status: partial          # v1 (2026-08-30) + U1 (2026-08-31) + U2 Handle model (2026-09-08) + U3 GripHandle/CircleItem (2026-09-08) + U3 PolylineItem/default_grip_handles + SplineItem + LineItem/EndpointGripHandle (2026-09-09) + ArcItem + RegularPolygonItem + EllipseItem + RectangleItem/box-native/single-gate + WallSegment/propagation+sibling-Esc + GridlineItem/parallel-delta+sibling-Esc (2026-09-10) + Room/label-grip/state-dependent-empty + DesignArea/badge-grip + FloorSlab + RoofItem/polygon-vertex-grips + DimensionAnnotation/offset-grip (2026-09-10) + DetailMarker/parametric-crop + render_overlay + _painting_into_clip_view (2026-09-11) + NoteAnnotation/box-native+bake-at-rest-rotation (2026-09-11) + ViewMarkerArrow/shared-crop parametric (translate-only caps, own outline dropped) (2026-09-11) + U4 retire-parallel-grip-systems (2026-09-12): all 3 legacy legs deleted (drawForeground grip loop, scene_tools._find_grip_hit, drag/commit leg), provides_handles_for→_is_box_native_single, manipulator is the SOLE model-scene grip path + U5 Leg A (2026-09-13): HALO preselection engine + selection-mode folded into the PLAN scene against the unified manipulator (see selection-mode.md §4-as-HALO) + U5 Leg B (2026-09-14): the manipulator becomes the sole grip owner in the ELEVATION scene (HaloSelectionMixin extraction, elevation manipulator construction, legacy _find_grip_hit/paintEvent retired; see selection-mode.md §14); U5 Leg C (3D handle providers) remains + arc/rect grip polish (2026-09-23): rotate knob removed app-wide; RectangleItem no longer box-native (9 RectGripHandles, Ctrl/Shift); ArcItem bisector centre + ArcEndpointGripHandle; GripHandle._apply hook + arc endpoint slide-along-circle (2026-09-24) + snap polish (2026-09-24): move handle snap (HandleSnapSession — interior drag, Move tool, LineItem TranslateGripHandle midpoint); vertex-chain Ctrl (Polyline/FloorSlab/RoofItem vs previous vertex); seam round (2026-09-25): TranslateGripHandle on every whole-item move grip (Circle/Ellipse/RegularPolygon/Text centre, Wall mid, Rect centre via RectTranslateGripHandle), lazy session build
last-verified: 2026-09-25
verified-commit: 17b4371   # smoke round B: move snapping is handles only (no grab/cursor snap; Move base point = a handle); prior d36af0a   # snap-polish seam round: handle snap on every whole-item move grip (lazy build); prior 892cf76   # snap polish: move handle snap + vertex_chain_grip_handles + TranslateGripHandle; prior f2b1d99   # HALO pixel ranking / grip limit / editor undo baseline; prior 62683b9   # arc endpoint grips slide along the circle; prior d31bfda arc/rect grip polish (knob removal, RectGripHandle, ArcEndpointGripHandle); prior 434066c block polish: _handle_scene_pos grip-points cache for pooled hosts; prior c0e1c28 bugfix batch: Ctrl-resize from-centre bake anchor (_bake_scale from_center) + Shift+handle press routing (hit_handle / _manip_press_should_route); U5 Leg B (98466ef) unchanged
applies-to:
  - firepro3d/selection_manipulator.py
  - firepro3d/manip_handle.py            # U2: Handle behavior classes (base + ResizeHandle; RotateHandle deleted 2026-09-23); U3: GripHandle + EndpointGripHandle + RectGripHandle + ArcEndpointGripHandle + default_grip_handles; snap polish: TranslateGripHandle (+ RectTranslateGripHandle) + vertex_chain_grip_handles
  - firepro3d/handle_snap.py             # S2 move handle snap: HandleSnapSession + HandleSnapResult ("Move — handle snap")
  - firepro3d/manip_math.py
  - firepro3d/arc_math.py                # ArcItem centre-grip bisector math + angle helpers (shared with End Points placement — 2d-geometry.md §4)
  - firepro3d/model_view.py              # drawForeground snap/constraint overlay + manipulator render_overlay (grip-render loop retired U4)
  - firepro3d/scene_tools.py             # legacy _find_grip_hit retired U4 (no grip code remains)
  - firepro3d/model_space.py             # press routing + manipulator lifecycle
  - firepro3d/paper_space.py             # SheetViewport / TextAnnotationItem handle retirement
  - firepro3d/geometry_2d.py   # RectangleItem bake-at-rest + manip capabilities + rect_grip_resize; U1 manip_rotate on Line/Polyline/Circle/Arc/RegularPolygon; U3 manip_handles on CircleItem + PolylineItem + SplineItem + LineItem + ArcItem
  - firepro3d/view_marker.py             # U3: ViewMarkerArrow manip adapter -> shared SharedCropBox (parametric crop, translate-only caps, own outline dropped)
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
> input, RectangleItem bake-at-rest, and paper handle retirement (parity). v1
> **coexisted** with the legacy per-item grip system via the `provides_handles_for`
> arbitration seam, which leaked a class of interaction bugs ("two systems fighting
> one item"). The **Unification Roadmap** (below) structurally eliminated that class:
> U1–U3 migrated every item onto `manip_handles`, and **U4 (2026-09-12) DELETED the
> legacy grip system entirely** — the manipulator is now the sole model-scene render
> path, hit-test, and undo funnel. Only U5 (selection-mode integration + elevation/3D
> handle providers) remains.

> **Rotate knob removed (2026-09-23, user decision).** The manipulator shows **no
> rotate affordance for any item or selection** — `RotateHandle`,
> `HandleRole.ROTATE`, the knob's stem/cursor/constants, `_bake_rotate`, the
> held rotate preview and the `manip_rotate` HUD schema are deleted (guard:
> `tests/test_no_rotate_knob.py`). Per-item **`manip_rotate(angle, pivot)`** and
> `item_capabilities`' `"rotate"` mapping are **retained** for a future Rotate
> transform (filed in `todo_open.md`). Every rotate-knob / rotate-gesture
> statement below not marked historical is superseded by this note.

# Unified Selection Manipulator — Governing Spec

## Goal

One scene-level, capability-driven **selection manipulator** — adopted from the
`selection_box.py` prototype (attach-once `QGraphicsObject`, 8 resize handles +
[prototype] rotate knob, interior-drag move, click-through, modifier keys, Esc-cancel, live
readout, pure transform math) — as the single home for selection feedback and
**rigid transforms** (move / scale; the rotate gesture was removed 2026-09-23)
across the model and paper scenes.
Parametric grip editing (`grip_points()`/`apply_grip()`) is preserved and
rendered inside the manipulator frame; the manipulator adds what items cannot
do today: group move and a unified interaction model (interactive rotation
shipped in v1/U1 and was removed 2026-09-23).

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
  (`ItemIgnoresTransformations`): 8 resize handles plus pooled hosts for the
  items' own grips (no rotate knob — removed 2026-09-23). **Grip-object limit
  (2026-09-24, AutoCAD `GRIPOBJLIMIT`):** when more than
  `selection_manipulator.GRIP_OBJECT_LIMIT` items are selected (default
  `constants.GRIP_OBJECT_LIMIT`; app-wide, Preferences → UX → SNAP, persisted
  `select/grip_object_limit`) `_active_handles()` returns no per-item grips —
  frame + interior move only (the box-native single-item branch precedes the
  check). Grip hosts per item made a 20k selection paint 63k hosts. `wraps()`
  is O(1) via a membership set kept in sync with `_items`. Handle sizing:
  px in the model scene, paper-mm in the paper scene (theming.md split).
- The prototype's **pure transform math** is ported verbatim and unit-tested:
  `resize_factors` (keep-aspect, from-center, negative-factor mirroring),
  `resize_delta`, `move_delta` (ortho), `_about` (`rotate_delta` /
  `transform_angle_deg` deleted with the knob, 2026-09-23).

### Capability protocol (duck-typed, house idiom)

| Method | Who implements | Meaning |
|---|---|---|
| `manip_bounds() -> QRectF` | all (fallback `sceneBoundingRect()`; cosmetic-pen items provide it explicitly) | box the frame wraps |
| `manip_translate(dx, dy)` | all selectable items (adapter over `translate()`/`moveBy()`) | baked move |
| `manip_rotate(angle_deg, pivot)` | **U1: all parametric items** (wall, node→pipes ride, gridline, room, floor, roof, line/polyline/circle/arc/regular-polygon/ellipse/rect) + badge + text | **no manipulator consumer since 2026-09-23** (knob removed; kept for the future Rotate transform). Baked rotate, app Y-up (CCW+) sign — `CAD_Math.rotate_point(p, pivot, -angle_deg)`; angle-carriers (gridline `_angle_deg`, arc `_start_deg`, regpoly `_rotation_deg`, badge `_angle`) accumulate `% 360` |
| `manip_scale(fx, fy, anchor)` | box-native only (text, `SheetViewport`; **not** `RectangleItem` since 2026-09-23) | baked resize in the item's own semantics |

**Box-native (scale set):** `SheetViewport`, `TextAnnotationItem` / text
blocks, `DesignAreaBadge`, note/dimension annotations (`RectangleItem` left this
set 2026-09-23 — it is parametric, see its U3 as-built). An item
adopts only the capabilities that are semantically valid for it (e.g. the
fixed-layout badge may implement translate+rotate but not scale) — the handle
gating reads what each item actually implements.
`manip_scale` maps onto each item's own model — TextAnnotation `wrap_width_mm`/`box_height_mm` + reposition; SheetViewport
**crop-rect change at fixed scale** (on-paper size = crop×scale invariant —
paper-space.md owns that rule).

**Handle gating (as-built 2026-09-23):** frame + interior-move whenever the
selection is non-empty; **no rotate knob, ever**. 8 rigid resize handles iff a
**single** item with the `scale` capability (`_is_box_native_single`; it may add
`manip_box_extra_handles()`). Otherwise the union of the selected items'
declared `manip_handles()` (an empty declared set is honoured — U5 Leg B); the
rigid set is the fallback only when no selected item declares handles. The
dashed frame is suppressed for a box-native single item and for any single item
whose `manip_frame_redundant()` returns True (an unrotated `RectangleItem`).

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
  (theming.md owns the tokens). Final handle look is **mockup-gated**
  (rendered candidates → user picks) before implementation binds.
- **Shift+press routing (2026-09-16):** the model-scene press guard
  (`Model_Space._manip_press_should_route`) routes a press to the manipulator
  when it lands on the frame; a **Shift-press on a HANDLE** still routes (Shift =
  aspect/ortho constraint), while a Shift-press on the bare frame **interior**
  is excluded so additive-select / floor-vertex editing keep working.
  `SelectionManipulator.hit_handle(scene_pos)` is the handle-only hit test the
  guard uses (vs `hit_test` = interior **or** handle).
- **Ctrl/from-centre resize bake (2026-09-16):** `_bake_scale` takes a
  `from_center` flag and anchors about `r0.center()` when set (else the opposite
  corner), matching `manip_math.resize_factors`' preview anchor — the factors
  alone do not encode the anchor. `ResizeHandle` records the Ctrl state of the
  last drag frame (`_last_from_center`) and forwards it, so a Ctrl-resize keeps
  the item centred on release instead of jumping ~the handle displacement.

### Transform lifecycle (held preview, bake on release)

1. **Press** (handle/interior): snapshot per-item pre-drag state; record
   the grab point.
2. **Move**: delta from pure math. A move is **handles only** (2026-09-25): the
   grab point is **not** snapped (no cursor, ALIGN or grid snap) — only the
   **handle snap** below corrects the delta; otherwise it is the raw cursor
   delta. **Snap-then-transform** still holds for resize, which snaps the dragged
   handle point via `snap_engine.find(…, held=…)`.
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

### Move — handle snap (S2, 2026-09-24)

While a selection moves, its **own snap points** snap to other geometry —
**handles only** (user decision 2026-09-25): the cursor / grab point itself gets no
cursor, ALIGN or grid snap on any move path, since an arbitrary grab point landing
on geometry is meaningless for a whole-item move. Without a handle hit the move is
the raw cursor delta. `handle_snap.HandleSnapSession` (`handle_snap.py`) serves three
move paths: the manipulator **interior drag**, **every whole-item move grip**
(`TranslateGripHandle`: the LineItem midpoint, the Circle / Ellipse /
RegularPolygon centre, the TextItem centre `MOVE_GRIP_INDEX`, the WallSegment mid
grip, and the RectangleItem centre via `RectTranslateGripHandle`), and the **Move
tool** (`mode == "move"`, including `begin_move_from`). Grips that move only part of
an item (ArcItem bisector centre, Room label, DesignArea badge, DetailMarker
bubble, Gridline bubble standoffs) are not move grips. Paste is excluded: it has no
scene items to take handles from.

- **Handles** are the moving items' `endpoint` / `midpoint` / `center` / `quadrant`
  points from `SnapEngine._collect` (so text frame boxes and block points count,
  `snapping-engine.md §5`). In the **Move tool the picked base point is also a
  handle** (rest = the base), so "base point onto a point" still lands exactly.
  They are stored as offsets from the gesture anchor (the grab point, the Move base
  point, or the grip's rest point) and captured **once, at rest**. They are deduped
  and capped at `HANDLE_SNAP_MAX_HANDLES` (`constants.py`): the Move base point
  first, then centre points, so a large block's insertion point is never crowded
  out, then the rest by snap priority.
- **Targets** are collected **once per gesture**: the same four point types from
  every other visible item, culled to the view's visible rect plus a margin, in a
  pixel-cell grid. The margin and the exact re-collect trigger are implementation
  detail in `handle_snap.py`. Excluded: the moving items and their children,
  pipes attached to a moving node, items above z 150, and the origin marker. Pipes
  are also excluded when the engine skips pipes. Underlay geometry is queried per
  handle through each group's `UnderlaySnapIndex`. The session is built at the
  manipulator's first moved update (before the first preview transform, so the
  items are at rest), at a move grip's first drag frame (`TranslateGripHandle`,
  before its first apply; a click without a drag builds none), or when the Move
  base point is set. The **Move tool re-collects its targets** when a zoom or pan
  between its clicks leaves the collected extent stale (`sync_view`). Its preview is
  a ghost, so the items are still at rest. Handles are never rebuilt.
- **Per move**, each handle is tested against its neighbouring grid cells within
  the snap aperture. Hits are ranked by the picker's band rules
  (`snapping-engine.md §6.1`), and the best handle hit corrects the move: the
  anchor is set so that handle lands exactly on its target. A target at
  a handle's **own rest position** is skipped for that handle. It is where the
  handle already is (a connected line's end), and snapping to it would pin the
  selection at rest for any move shorter than the aperture.
- **Gating** is per frame: the SNAP toggle and the engine's enabled flag. The
  manipulator's interior drag also skips it under **Shift** (ortho would project a
  hit off its target; Shift ortho itself is unchanged). Typed dX/dY displacements
  ignore it.
- **Move tool:** the **base click** snaps normally (user-chosen geometry). Once the
  base is set, `get_effective_position` returns the raw cursor for the destination
  (no cursor snap, **no ALIGN**, no grid); only the handle session (base point
  included) snaps it. Paste keeps its cursor snap (it has no handles).
- **Move grips** (`TranslateGripHandle`) skip the scene's grip-snap authority
  (`_cursor_point` returns the raw cursor), so no cursor / ALIGN / grid snap.
- **Marker:** a hit is published to `Model_Space._snap_result` as a
  `HandleSnapResult`. The manipulator and a move grip clear only a marker they
  published themselves (on a no-hit frame, release or Esc). In the Move tool the
  destination step clears `_snap_result` each frame before a hit republishes it.
  Never used as the hysteresis `held`: see
  [`align-placement.md §3`](align-placement.md#3-lock-guide-one-picker-composition).

### HUD (readout + typed input)

Two `DynamicInputHud` transform schemas: `manip_move` (dX/dY) and
`manip_resize` (W/H) (`manip_rotate` deleted with the knob, 2026-09-23).
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
- **Rotation as data, not transform, at rest** (RectangleItem `_angle` field).
  (Interactive rotation shipped in v1/U1 and was **removed 2026-09-23**; a
  Rotate transform is to follow.)
- Prototype interaction set (click-through, Esc, Shift ortho/aspect, Ctrl
  scale-about-center); the v1 Shift-15° rotate snap left with the knob;
  **movable pivot deferred**.

## Acceptance Criteria

- [ ] One `SelectionManipulator` per scene (model + paper); frame + interior
      move on every selectable item; accent-tokened styling (mockup-approved).
- [ ] Handles capability-gated exactly as specified (8-handles/parametric
      grips-in-frame/multi-select-move-only); **no rotate knob on any item or
      selection** (`tests/test_no_rotate_knob.py`).
- [ ] Universal baked move incl. multi-select group move; grab-point OSNAP.
- [ ] Scale on box-native items; RectangleItem baked-at-rest migration, old
      saves load. (~~Rotate; Shift-15°; typed-angle via HUD~~ — removed
      2026-09-23 with the knob.)
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
  mixed selections. (The rotate knob that consumed it was **removed
  2026-09-23**; `manip_rotate` stays for a future Rotate transform.)
- Paper viewport/text rotation semantics; movable rotation pivot; group scale.
- HALO preselection / disambiguation-cycle / rubber-band — owned by
  `selection-mode.md` (Leg A built 2026-09-13 in the plan scene), which owns
  what-gets-selected; this spec owns what-happens-to-the-selection.

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
  (`MANIP_NO_SOLO_ROTATE` — deleted 2026-09-23 with the knob); the fitting-refresh step is shared across
  move/rotate/scale bakes. **Bug fixed en route:** `hit_test` mapped
  `ItemIgnoresTransformations` handles with plain `mapFromScene` (correct only at
  m11==1), so the rotate knob was unhittable at the fit-to-view zoom and the
  press cleared the selection — now mapped via the view's `deviceTransform`.
- **U2 — the `Handle` model** ✅ **DONE (2026-09-08):** defined one `Handle`
  behavior abstraction (role, position, drag→edit, commit) + a `manip_handles()`
  capability with a live-fallback sourcing path; re-expressed the manipulator's
  own resize/rotate handles as `Handle`s (`RotateHandle` since deleted,
  2026-09-23). Pure internal refactor — the 6 manip
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
  move-centre grip — move is interior drag). *(Superseded 2026-09-24: Polyline,
  FloorSlab and RoofItem vertices now Ctrl-angle-constrain via
  `vertex_chain_grip_handles` — see the PolylineItem row below.)* ✅ **SplineItem DONE (2026-09-09)**
  — control points are the spline's vertices → all round (`circular=` all
  control-point indices); same shape as Polyline, no special semantics.
  ✅ **LineItem DONE (2026-09-09)** — first item with per-item semantics:
  endpoints (grips 0, 2) round + Ctrl-angle-constrained against the opposite
  endpoint via a reusable `EndpointGripHandle(GripHandle)` (`_transform_point`
  → scene `_constrain_angle`; also serves Wall/Gridline endpoints later);
  midpoint (grip 1) round (a move grip — translates the whole line) + plain
  `GripHandle` (no constrain — matches legacy). *(Superseded 2026-09-24: the
  midpoint is a `TranslateGripHandle` — handle snap, see "Move — handle snap".)* ✅ **ArcItem DONE (2026-09-10)** — zero special
  semantics (the legacy grip path explicitly excludes arc from Ctrl-constrain):
  `default_grip_handles(self, circular={0,1,2})` (centre + start + end, all round
  — centre = move grip, start/end = the arc's geometric endpoints). Same shape as
  Spline/Polyline. *(Superseded 2026-09-23: the arc now has real grip semantics
  — see the ArcItem as-built below.)* ✅ **RegularPolygonItem DONE (2026-09-10)** — zero special
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
  `_frame_is_redundant`). *(Superseded 2026-09-23: the rect is no longer
  box-native — 9 `RectGripHandle`s at every angle; see the RectangleItem as-built
  below.)* Each
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
  both plain `GripHandle`s that never propagate. *(Superseded 2026-09-25: the mid
  grip is a `TranslateGripHandle` — handle snap; still no propagation.)* Wall keeps `manip_rotate` (no
  knob since 2026-09-23); not box-native (no `manip_scale`).
  Remaining, simplest-first:
  Gridline
  (+parallel-delta), Room, DesignArea,
  **Text blocks — both BOUNDING-BOX-governed (box-native, like Rectangle then was: frame +
  resize + move + rotate, NOT a single MText position grip)**: (a) ✅ **NoteAnnotation
  DONE (2026-09-11)** — the 2D-geometry MTEXT text block UPGRADED to box-native
  (resize = wrap-width + `box_height`, font untouched; bake-at-rest rotation, text
  tilts; additive `angle`/`box_height` serialization; see the NoteAnnotation
  as-built below). Surfaced a **pre-existing** live text-render/`QPainter engine==0`
  bug (present on `main`, filed separately — not this migration); (b) the paper
  `Sheet Text block` `TextAnnotationItem` (**already box-native** — no migration
  needed; the paper scene has no legacy grip path). `DimensionAnnotation`, Floor,
  Roof DONE; DetailMarker + ViewMarker DONE; the plan-scene U3 items are complete
  (elevation/3D-scene handle providers remain under U5).
- **U4 — retire the parallel systems** ✅ **DONE (2026-09-12):** deleted all THREE
  legacy legs — the `Model_View.drawForeground` grip-render loop, `scene_tools.
  _find_grip_hit` (+ its two dead call sites: the `model_view` rubber-band-suppress
  press branch and the `model_space` select/move grip-drag branch), AND the legacy
  grip **drag/commit** leg (`_drag_grip_to`, the `mouseMoveEvent` grip block with
  its Ctrl-constrain, the `mouseReleaseEvent` commit, and the `_grip_index` field).
  Removed the `_item_uses_manip_handles` coexistence gate. The manipulator is now
  the sole render path, hit-test, and undo funnel. **Precondition proven:** every
  model-scene `grip_points()` item also provides `manip_handles()` (state-dependent
  items — Room/DesignArea/ViewMarkerArrow — symmetric: grips empty ⟺ handles empty),
  so all three legs were already dead code. **KEPT:** `grip_points()`/`apply_grip()`
  (the mutation primitives `GripHandle` calls), the borrowed `_grip_item`/
  `_grip_dragging` scene state (read by the snap self-exclusion in
  `get_effective_position`), and the propagation/snapshot helpers
  (`_propagate_gridline_grip`, `_snapshot_gridline_grips`, `_propagate_wall_endpoint`,
  …). **RENAMED:** `provides_handles_for` → `_is_box_native_single` — its arbitration
  role is gone, but the "single scale-capable (box-native) item → rigid resize
  handles" detection survives for `_active_handles`/`_frame_is_redundant`. Elevation
  (`ElevationView.paintEvent` + `elevation_scene._find_grip_hit`), paper, and 3D have
  their OWN independent grip paths — untouched, and folded in under U5.
- **U5 — fold in selection + other scenes**:
  - ✅ **Leg A — plan-scene selection-mode + HALO DONE (2026-09-13):** integrated
    `selection-mode.md` (preselection highlight / disambiguation-cycle / rubber-band)
    against the unified manipulator, which stays the sole model-scene grip owner.
    Disambiguation moved to **Spacebar** (Tab freed for the HUD); the hover engine
    shipped as **HALO** (aperture pick + shared `halo_rank`). As-built pointer:
    `selection-mode.md` §4 (HALO). DoR:
    `docs/superpowers/specs/2026-09-13-halo-selection-mode-leg-a-design.md`. The
    manipulator contract itself was unchanged — Leg A consumed it, did not modify it.
  - ✅ **Leg B — elevation handle providers DONE (2026-09-14):** the manipulator is
    now the sole grip owner in the elevation scene. Built via the extracted
    scene-agnostic **`HaloSelectionMixin`** (`halo_selection.py`, shared with
    `Model_Space`); an `ElevationScene`-owned `SelectionManipulator`
    (`commit_hook` persists the gridline extent override, **no undo**;
    `handle_units="px"`; `exclude` = `_ElevBubble`); gridline/datum expose
    `manip_handles()` (extent grips) + an **axis-constrained `manip_translate`**
    (drops the pinned axis — §3.1); read-only proxies get a **no-op
    `manip_translate`** + `manip_handles() → []` (frame + zero handles). Legacy
    `ElevationScene._find_grip_hit` + `ElevationView.paintEvent` grip loop retired
    (borrowed `_grip_item`/`_grip_dragging` kept for `GripHandle`). **Contract
    refinement:** `_active_handles` now honours an item's *declared* (possibly
    **empty**) `manip_handles()` — the rigid resize fallback fires only when NO
    selected item provides handles (Node/sprinkler); this supersedes the U2
    as-built "`union(...) or rigid_set`". As-built pointer: `selection-mode.md`
    §14. DoR: `docs/superpowers/specs/2026-09-14-u5-leg-b-elevation-selection-design.md`.
  - ⏳ **Leg C — 3D handle providers:** pending (3D scene; orphan).

**Risks to honor at each step** (why it's staged, not a big-bang): the constraint
solver, the model full-network-snapshot vs paper macro undo
split, gridline parallel-delta, wall-endpoint propagation, and the rotation
Y-up/pivot convention all currently live in the `model_space` grip lifecycle and
must move onto the `Handle`/manipulator path without behavior drift. The v1
`provides_handles_for` seam was retired by U4 (2026-09-12): the box-native
detection it encoded survives as the internal `_is_box_native_single`, but its
arbitration-against-the-legacy-path role is gone (there is no legacy path).
The earlier "OSNAP-per-handle" risk is retired (2026-09-24). Grips snap through the
scene's snap authority (`GripHandle.on_drag` → `get_effective_position`), and a
moving selection's own points snap through the handle snap (see "Move — handle
snap").

## U2 — Handle model (as-built, 2026-09-08)

Design of record: `docs/superpowers/specs/2026-09-08-u2-handle-model-design.md`.

**Two objects, wrap-not-merge.** `Handle` (in new `firepro3d/manip_handle.py`) is a
plain behavior object; `_HandleItem` (renamed from `_Handle`, in
`selection_manipulator.py`) is the screen-constant `QGraphicsItem` host that
forwards `paint`/`shape`/`cursor`/`mousePress` to its `Handle`. Rigid handles keep
rendering via role-keyed hosts (`manip._handles[role]` preserved); widget-less
item handles (U3) get pooled hosts (`_sync_host_pool`).

**`Handle` contract:** `role`, `gesture_mode` (`"resize"`, or `"grip"` for U3
live-apply handles → sets `_mode`), `hud_schema`; `scene_position(rect)`, `shape(*,size,grab_pad)`,
`paint(painter,*,size,border,fill,hover,border_width)`, `cursor(m)`, `visible(m)`;
lifecycle `on_press/on_drag/on_release/on_cancel(m,…)`, `commit_typed(m,values)`,
`hud_values(m)`. Subclasses: `ResizeHandle` (`RotateHandle` deleted
2026-09-23). (U3 adds `GripHandle` — live-apply.)

**Delegation, no drag-model branch.** The manipulator owns drag *state* +
the held-preview toolkit (`_apply`/`_bake_*`/`_snap`/`_feed_hud`/`_snapshot_items`/
`_restore_preview` — bodies unchanged); `_begin`/`_update`/`_finish`/
`_on_hud_committed`/`cancel_drag` delegate the per-kind work to
`_active_handle.on_*`. Held-preview handles (resize/rotate) *orchestrate* the
toolkit (rigid resize only since the knob's removal); a live-apply handle (U3 parametric) calls `apply_grip`+solve in `on_drag`
and never touches `_apply` — the manipulator is oblivious. Interior-drag **move
stays a manipulator-level gesture** (not a Handle).

**`manip_handles()` sourcing (option B, live-with-fallback):**
`_active_handles()` returns the union of the selected items' `manip_handles()`.
**Refined U5 Leg B (2026-09-14):** an item that *declares* `manip_handles()` is
authoritative — its possibly-**empty** set is honoured (a read-only elevation
proxy returns `[]` for frame + zero handles); the rigid resize fallback fires
only when **no** selected item provides `manip_handles` (Node/sprinkler,
translate-only via `pos()`). Box-native items take the earlier box-native
return, so they are unaffected. `_layout` positions/gates the rigid role-hosts and syncs the pool for
any item handles.

**Handle-facing context API** (manipulator privates a Handle may read):
`_snap`, `_apply`, `_bake_move/_bake_scale`, `_feed_hud`,
`_restore_preview`, `_end_drag`, `_last_factors`, `_R0`/`_B0`/`_start_scene`/`_D`,
the `_*_at_press` release-bake snapshot trio, the `_typed_*` typed-commit trio,
`_moved`, `_resize_cursor`, `_show_scale_handles`. (`_bake_rotate`,
`_base_angle`, `_ROTATE_SNAP_DEG`, `_show_rotate_knob` deleted 2026-09-23.)

**Known limitation → U3 must fix:** `_begin_handle(handle, …)` calls
`_begin(handle.gesture_mode, …, handle.role)`, and `_begin` installs
`_active_handle = self._rigid[role]` — so a *pressed item handle* currently
re-resolves to the **rigid** handle of the same role, not the item's own handle.
Harmless in U2 (rigid-only; the admissibility test proves the *dispatch* admits
live-apply by installing the fake directly). **U3 must make `_begin_handle`
install the passed handle** (e.g. `_active_handle = handle` after `_begin`) so a
pooled/item host press drives the item's handle. Parity-safe (for rigid handles
`handle is self._rigid[role]`).

**Tests:** `tests/test_manip_handle.py` (contract units), `tests/test_manip_handle_admissibility.py` (live-apply lifecycle +
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
  plain scenes) → `_transform_point` hook → **`_apply(pt, mods)` hook** (default
  `item.apply_grip(index, pt)`; subclasses override it to use press-time state /
  modifiers — `RectGripHandle`) → `_after_apply` hook →
  `scene._tools._solve_constraints(item)` → `m._reflow_live()`. Records
  `self._last_pt`.
- `on_release`: capture `moved`; re-apply the release point **only if it differs
  from `_last_pt`** (Qt normally delivers a final move at the release position →
  re-apply skipped, so a future `_after_apply` propagation override cannot
  double-fire; the re-apply goes through the same `_apply` hook); `_clear_grip_state`; `m._end_drag()`; then if `moved`, solve +
  `commit_hook("grip")` (one undo per gesture).
- `on_cancel`: re-apply the snapshot for **only the dragged grip**
  (`apply_grip(self.index, snapshot[index])`) + `_restore_extra` for sibling/
  propagated state; `_clear_grip_state`; **no** commit. (Restoring *every* grip
  corrupts index-dependent grips — LineItem's midpoint `apply_grip` translates
  the whole line, so replaying it mid-restore shifts the endpoints; a derived
  grip like the midpoint recomputes from the endpoints anyway. Fixed 2026-09-09
  during the LineItem migration.)

**Per-item semantics are ADMITTED (not built here) as extension points:**
`_transform_point` (Ctrl angle-constrain), `_apply` (press-time / modifier-aware
apply, added 2026-09-23; `on_cancel` bypasses it and restores via `apply_grip`
directly), `_after_apply` (gridline
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

**Host positioning cost (2026-09-23, block polish).** `_sync_host_pool` and
`_reflow_live` position pooled hosts via module-level `_handle_scene_pos(handle,
rect, pts_cache)`: for a **plain** `GripHandle` (its `scene_position` not
overridden) each item's `grip_points()` is computed **once per pass** and indexed,
instead of one O(n) call per host (O(n²) for an n-point spline/polyline — dominant
on large imported selections). Subclasses overriding `scene_position` keep their
own logic. Guard: `tests/test_block_curve_import.py::test_selecting_a_long_spline_computes_grips_once_per_item`.

**Coexistence gate** (one render path, one hit-test): module-level
`_item_uses_manip_handles(item)` (in `selection_manipulator.py`) — true when the
item's `manip_handles()` returns a non-empty list. `Model_View.drawForeground`'s
grip loop and `scene_tools._find_grip_hit` both `continue` past such items. This
is now the **single** legacy-path skip: since RectangleItem (the only model-scene
box-native item) provides `manip_handles`, the separate `provides_handles_for`
skip was removed from both paths (2026-09-10; historical — RectangleItem left the
box-native set 2026-09-23). `provides_handles_for` remains an
internal helper (`_active_handles` picks the rigid resize set for a box-native
single item; `_frame_is_redundant`). U4 deletes the legacy paths + the helper.

**`default_grip_handles(item, circular=frozenset())`** (`manip_handle.py`) — the
shared body of every migrated item's `manip_handles()`: one `GripHandle` per
`grip_points()` index, `grip_hittable`-filtered, square except indices in
`circular` (rendered as discs — centre/move grips). Extracted on the 2nd
migration to keep the ~15 per-item `manip_handles()` from drifting; per-item
drag semantics live on `GripHandle` subclass hooks, not here.

**CircleItem.manip_handles()** → `default_grip_handles(self, circular={0},
translate={0})`: 5 handles (center + 4 radius). Center → `apply_grip(0)`
(translate; a `TranslateGripHandle` — handle snap); radius →
`apply_grip(1..4)` (resize). Zero special semantics — the pattern-establisher.

**PolylineItem.manip_handles()** → `vertex_chain_grip_handles(self,
closed=self.is_closed())`: one round handle per vertex, each → `apply_grip(index)`
(move vertex + rebuild). No move-centre grip (move is the manipulator's interior
drag). **Ctrl angle-constrains a vertex against its PREVIOUS vertex** (2026-09-24):
an open chain's first vertex constrains against the next one (it has no previous);
a closed chain wraps (vertex 0 constrains against vertex n−1).
**`vertex_chain_grip_handles(item, closed, circular=None)`** (`manip_handle.py`) is
the shared vertex-chain body — one `EndpointGripHandle` per `grip_hittable`
vertex with `opposite_index` chosen as above (a lone vertex gets a plain
`GripHandle`), all round by default. The anchor is re-read live from
`grip_points()` each frame. Used by PolylineItem, FloorSlab and RoofItem.

**SplineItem.manip_handles()** → `default_grip_handles(self, circular=all
control-point indices)`: one round handle per control point, each →
`apply_grip(index)` (move control point + `_regenerate`). Control points are the
spline's vertices (no midpoints); no move-centre grip; no special drag semantics.

**LineItem.manip_handles()** → `[EndpointGripHandle(0, opp=2),
TranslateGripHandle(1), EndpointGripHandle(2, opp=0)]`. Endpoints round + Ctrl-angle-
constrained against the opposite endpoint; midpoint round, no constrain — it
translates the whole line, so it is a **move grip** (round per the house rule), not a
geometric midpoint. **`TranslateGripHandle(GripHandle)`** (`manip_handle.py`,
2026-09-24) adds the handle snap to that move — and to every other whole-item move
grip (see "Move — handle snap"): on its first drag frame it builds a
`HandleSnapSession` anchored on the grip's press-time point, and in
`_transform_point` (cooperative: the next class's hook runs first) the best handle
hit (from the raw cursor) corrects the drag point. Handles only: its `_cursor_point`
returns the raw cursor (no cursor / ALIGN / grid snap). It clears its own marker on
a no-hit frame, release or cancel. **`EndpointGripHandle(GripHandle)`** (`manip_handle.py`) is the
reusable per-item Ctrl-constrain handle: `_transform_point` projects the dragged
point onto the nearest angle increment ray from `grip_points()[opposite_index]`
via the scene's `_constrain_angle` (the legacy grip authority; getattr-guarded
for headless). Reused by Wall/Gridline endpoints (opp 1↔0) in their PRs, and by
the PolylineItem / FloorSlab / RoofItem vertex chains through
`vertex_chain_grip_handles` (anchored on the previous vertex, 2026-09-24).

**WallSegment.manip_handles()** → `[WallEndpointGripHandle(0, opp=1),
WallEndpointGripHandle(1, opp=0), TranslateGripHandle(2), GripHandle(3, square)]`.
Endpoints (0, 1) round + Ctrl-angle-constrained against the opposite endpoint
(inherited from `EndpointGripHandle`); mid (2) round move grip (translates the
whole wall; handle snap, "Move — handle snap"); width (3) square thickness grip, aligned to the wall via
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
carries the edit math (endpoints, translate, thickness) unchanged; wall keeps
`manip_rotate` (no knob since 2026-09-23); not box-native.

**GridlineItem.manip_handles()** → `[GridlineGripHandle(0, opp=1, round),
GridlineGripHandle(1, opp=0, round), GridlineGripHandle(2, round),
GridlineGripHandle(3, round)]`. Grips 0/1 are the endpoints (origin/far), 2/3
the bubble-standoff grips; all round — the bubble grips are draggable move-like
affordances (reposition the bubble standoff), round per the house rule (function,
not position). `apply_grip` slides endpoints along the axis (opposite
end fixed) and bubble grips along the standoff (floored at 0) — unchanged. The
SECOND sibling-mutating migration, but the sibling relation is **multi-select
parallel-delta**, not coincidence-propagation: **`GridlineGripHandle(
EndpointGripHandle)`** (`manip_handle.py`) applies the same scene delta to the
same grip index on every OTHER *selected* gridline (`_after_apply` →
`scene._propagate_gridline_grip`) — for ALL four grips, not just endpoints (bubble
standoffs propagate too; exact for parallel selections, under-applies for
non-parallel, the historical behaviour). Endpoints Ctrl-angle-constrain against
the opposite endpoint (inherited `EndpointGripHandle`, `opposite_index` set);
bubble grips pass `opposite_index=None` to skip it (parity: legacy constrained
endpoints only). Atomic Esc-restore of siblings via `_extra_snapshots`/
`_restore_extra` → `scene._snapshot_gridline_grips(item, index)` /
`_restore_gridline_grips` (indexed by the dragged grip; `apply_grip` on a
gridline's original on-axis point is idempotent, so restore is exact). The scene
helpers live directly in `Model_Space` (gridline has no domain controller yet).
The legacy `_PullTabGrip` child items (the pre-U3 endpoint/bubble grip visuals)
are **removed** — grips are manipulator-owned; `_LockIndicator` stays and nudges
`manipulator.rebake()` on lock-toggle so grip visibility re-evaluates. Keeps
`manip_rotate` (no knob since 2026-09-23); not box-native. Hover grip-preview dropped (U5).

**Room.manip_handles()** → `default_grip_handles(self, circular={0})`. The simplest
migrated item: a SINGLE label-centre grip (round — a move affordance that
repositions the label), **conditionally present**. `grip_points()` returns `[]`
when the label is hidden (no name/tag or `_show_label` off), so `default_grip_handles`
returns `[]` too — Room is the first item to exercise the **state-dependent empty
`manip_handles()`** path: a label-less room reports "not migrated" via the gate,
which is harmless because `grip_points()` is empty then (nothing renders on either
path). Zero special drag semantics (`apply_grip(0)` moves the label; no
Ctrl-constrain, no sibling propagation — the boundary vertices are wall-derived
and NOT exposed as grips). (`MANIP_NO_SOLO_ROTATE` — the solo-room knob
suppression — was deleted 2026-09-23 with the knob.)

**DesignArea.manip_handles()** → `default_grip_handles(self, circular={0})`. A Room
twin: a SINGLE badge-centre grip (round move affordance), conditionally present —
`grip_points()` is empty unless the badge is visible (`_sync_badge` shows it only
for a confirmed area with members, not in edit mode), so `manip_handles()` is
empty and the gate is off when there's no badge. `apply_grip(0)` moves the badge;
zero special semantics. The manipulator frame wraps the badge box (`manip_bounds`
→ `badge.sceneBoundingRect()`); caps are `{translate, rotate}` (badge is a
fixed-layout table — never scalable).

**FloorSlab.manip_handles()** → `vertex_chain_grip_handles(self, closed=True)`:
one round grip per boundary vertex — a closed PolylineItem twin.
`grip_points()`/`apply_grip()` (move vertex + `_rebuild_path`) carry the edit math
unchanged. **Ctrl angle-constrains a vertex against the previous vertex**
(wrapping — see the PolylineItem row; 2026-09-24, superseding the earlier
"zero special drag semantics"). A floor's boundary is not grip-coupled to
neighbours, so there is no propagation. Keeps `manip_rotate` (no knob); not
box-native (no `manip_scale` → caps `{translate, rotate}`).

**RoofItem.manip_handles()** → identical to FloorSlab
(`vertex_chain_grip_handles(self, closed=True)`): one round grip per boundary vertex,
Ctrl-constrained against the previous vertex (wrapping). `apply_grip` →
`_rebuild_path` (regenerates overhang + ridge) unchanged. No propagation; keeps
`manip_rotate` (no knob); not box-native.

**DimensionAnnotation.manip_handles()** → `default_grip_handles(self, circular={0})`:
the SINGLE offset grip (at the offset-line midpoint) on the unified path —
round, a draggable reposition affordance per the gridline bubble-standoff
precedent (function, not position). `apply_grip(0)` changes the perpendicular
offset distance (`_offset_dist`) unchanged; zero special semantics (no
Ctrl-constrain, no sibling propagation). Caps `{translate}` — interior-drag move
via `manip_translate` (endpoints translate; `_p1/_p2` are the serialized
geometry, so a bare `moveBy` would desync); no scale/rotate in v1. The grip was
previously drawn by the legacy `drawForeground` path; it is now
manipulator-owned, so a selected dimension shows exactly one visible handle (the
grip) with no resize/rotate handles. Serialized via `network_codec` (no
`to_dict`), so parity is asserted on `_offset_dist`.

**NoteAnnotation — box-native MTEXT (`annotations.py`).** The model-scene MTEXT
note migrated from translate-only to **box-native** (as RectangleItem then was:
frame + resize + move; the rotate knob it also had was removed 2026-09-23). `manip_capabilities()` = `{translate, scale, rotate}`
unrotated, dropping `scale` when `_angle != 0` so the 9 parametric grips surface
(the pre-2026-09-23 RectangleItem convention). `manip_handles()` = `default_grip_handles(self,
circular={0,2,4,6,8}, translate={MOVE_GRIP_INDEX})`; `manip_box_extra_handles()` =
the centre move grip (index 8) alongside the rigid resize set when unrotated. Both
centre move grips are `TranslateGripHandle`s (handle snap). **Resize** clones the paper
`TextAnnotationItem` semantics: horizontal handles set the wrap width
(`setTextWidth`), vertical handles set `_box_height` (content-min clamped;
`MIN_TEXT_WRAP_WIDTH_MM` for wrap), corners do both, pinned-edge — **font is never
touched**. Because a `QGraphicsTextItem` always paints from its local origin,
`apply_grip`/`manip_scale` re-anchor `pos()` (via `_reanchor`, which maps the
local shift through the rotation) instead of moving the local rect's left/top; the
first horizontal resize from auto-width (`textWidth() <= 0`) seeds the wrap from
the content width. **Rotation is bake-at-rest, ported from RectangleItem** (data
`_angle`/`_pivot`, `_rotation_transform`, `set_angle`, `manip_rotate`; NO Qt
`setRotation` — `rotation()` stays 0) — the text tilts with the frame. The map*
overrides (`mapToScene`/`mapFromScene`/`mapRectToScene`) differ from RectangleItem
in one respect: a note's `pos()` is nonzero, so they **compose** the local
rotation with `super().map*` (pos translation), and `set_angle` converts the
manipulator's *scene* pivot to local (`QGraphicsTextItem.mapFromScene`). Qt's
`mapToScene` is non-virtual in C++, so these overrides only intercept Python
callers (grip/snap); Qt rendering uses `paint`/`boundingRect`/`shape`, all baked
(`boundingRect` unites content with `_local_box` so a tall box doesn't clip).
Serialization gains additive `angle`/`box_height` keys (`network_codec`), with old
records defaulting to `0.0`/auto-fit (byte-identical render). **Live-only
pre-existing caveat (not from this migration):** a focused note's text/cursor
don't render live and Qt spams `QPainter engine==0` (reproduces on `main`; filed
as its own bug) — static/valid-device renders show the text fine. Tests:
`tests/test_manip_griphandle_note_parity.py` (fields, serialization + back-compat,
resize/pinned/clamp/seed, box-native caps/bounds/scale/gate, rotation bake +
rotated grips + footprint, live-apply parity, posted-event drag, `_find_grip_hit`
skip both states) + the updated caps assertion in
`tests/test_manip_badge_annotations.py`.

**DetailMarker — parametric editable crop (`detail_view.py`).** DetailMarker is a
PARAMETRIC crop rectangle (NOT box-native, deliberately): `manip_handles()` =
`default_grip_handles(self, circular={8})` — 8 SQUARE crop grips (corners +
midpoints, live `apply_grip` resize; the crop-centre delta shifts the bubble so
the callout tracks the box) + a ROUND bubble move grip (index 8). Caps
`{translate}` → the manipulator FRAME is the visible bounding box; axis-aligned
(no `manip_rotate`). Box-native was tried and **rejected**: its held
scale-transform preview warped the bubble circle into an ellipse, froze the frame
(no live update), and suppressed the frame so no box showed.

Two general mechanisms were added for the shared-scene detail view (a `Model_View`
with `_clip_rect` re-rendering the SAME scene clipped to the crop):
- **`_painting_into_clip_view(widget)`** (module-level): true when painting into a
  detail/clip view. `_HandleItem.paint` short-circuits there (the crop mask, a
  view-level foreground, would otherwise dim the handles).
- **`SelectionManipulator.render_overlay(view, painter)`**: `Model_View.
  drawForeground` calls it AFTER the crop mask, so the frame (scene coords) +
  handles (viewport px) are redrawn BRIGHT on top of the mask — the crop is
  selectable/resizable from inside the detail view. In a clip view the marker
  paints nothing as an item; `drawForeground` draws its callout (leader + bubble,
  `DetailMarker._paint_callout`) bright and the passive crop rect / boundary
  outline are removed (the mask edge shows the crop — the old "blue box" is gone).

**ViewMarkerArrow — parametric shared crop (`view_marker.py`).** The N/S/E/W
elevation markers all share ONE `SharedCropBox`. The selected marker's
`manip_handles()` = `default_grip_handles(self)` — 8 SQUARE crop grips (corners +
edge midpoints) forwarding to the shared box via the existing
`grip_points`/`apply_grip`; resizing repositions all four markers to the new box
edges (`_reposition_markers_to_rect`). `manip_bounds()` = the box's scene rect;
`manip_translate()` moves the whole box + repositions the markers. Caps =
`{translate}` (mirrors DetailMarker): NOT box-native, so the manipulator's dashed
FRAME is the crop outline — `SharedCropBox`'s own dashed outline is dropped (pen
`NoPen`), its faint fill kept. **`manip_translate` is mandatory, not optional:**
the manipulator excludes items with no `"translate"` capability, so a resize-only
marker would never be wrapped and its grips would not render — the move capability
is a prerequisite of the migration. Axis-aligned (no `manip_rotate`; section-view
angle deferred). State-dependent: an unselected marker's `grip_points()` is empty,
so `manip_handles()` is empty and the coexistence gate reads "not migrated"
(benign — nothing renders on either path; same resolved case as Room/DesignArea).
**Rebake-ordering gotcha (2026-09-11 smoke fix):** `grip_points()` gates on
`isSelected()` + box existence, **NOT** `box.isVisible()`. The manipulator builds
its grip host-pool ONCE per `rebake()` (on `selectionChanged`); the crop box's
visibility is set by the marker's own `itemChange` during the SAME selection
event, which lands AFTER that rebake — so keying grips on `isVisible()` made
rebake read `[]` and render zero handles ("no handles" live). The legacy
`drawForeground` re-read `grip_points()` every repaint and never staled; the U3
migration introduced the sensitivity. **General rule for any selection-conditional
item: gate grips on selection, not on a visibility flag mutated by `itemChange`.**
Tests: `tests/test_manip_griphandle_viewmarker_parity.py` (incl.
`test_selection_renders_grip_hosts_no_manual_rebake`, which asserts the RENDERED
host pool — the earlier parity tests called `manip_handles()` directly and masked
the staleness).

**ArcItem.manip_handles()** (re-shaped 2026-09-23) → `[GripHandle(0,
circular), ArcEndpointGripHandle(1), ArcEndpointGripHandle(2)]` — centre + start +
end, all round. Semantics (`ArcItem.apply_grip`; the math lives in `arc_math.py`,
shared with the End Points placement — `2d-geometry.md §4`):
- **Centre (0)** — both endpoints stay fixed; the drag point is projected onto
  their perpendicular bisector and radius / start / span follow (CCW start→end is
  kept, so dragging across the chord grows the arc through a semicircle into a
  major arc). A full-circle arc (no chord) translates instead. A degenerate
  result holds the last valid shape.
- **Start (1) / End (2)** — `ArcEndpointGripHandle(GripHandle)` (2026-09-24,
  replaces the 3-point refit): the **centre, radius and the other endpoint stay
  fixed**; the drag point is projected radially onto the circle and only the
  dragged endpoint's angle changes. Start drag: start = angle(point), span =
  (end angle − start) mod 360; end drag: span = (angle(point) − start) mod 360.
  A span < 0.5° or > 359.5° (or a point on the centre) **holds the last valid
  shape**. No modifier semantics (Ctrl is not special). The circle is invariant
  during the drag, so `apply_grip` reads the live centre/radius (no press-time
  ref on the item). The handle snapshots the arc data on press
  (`_extra_snapshots`) and `_restore_extra` writes it back, so Esc restores
  byte-exactly.
- `ArcItem` stores every arc CCW (a negative span is normalised in `__init__`),
  which the span formulas assume.

**RegularPolygonItem.manip_handles()** → `default_grip_handles(self,
circular=all indices, translate={0})`: centre + N vertices, all round (centre =
move, a `TranslateGripHandle` — handle snap; each
vertex = a defining point — dragging it resizes + rotates). Handle count tracks
`_sides`. Zero special semantics (legacy grip path excludes polygon from
Ctrl-constrain); `apply_grip` carries the edit math.

**EllipseItem.manip_handles()** → `default_grip_handles(self, circular={0},
translate={0})`: centre + 4 axis endpoints. Mirrors CircleItem (an ellipse is a
generalized circle): centre = round move grip (`TranslateGripHandle` — handle snap); the axis-endpoint sizing grips (major rx=1,2,
which also rotate; minor ry=3,4) render **square** — same rationale as circle
radius grips (points on a closed curve for sizing, not curve termini). Zero
special semantics (not Wall/Gridline/Line → no Ctrl-constrain); not box-native
(no `manip_scale`); `apply_grip` carries the edit math. The 4 square grips are
**rotated to the ellipse's orientation** (radial alignment) via the
`grip_render_angle` hook (below), so they stay aligned to the axes at placement
angle and after a rotate.

**RectangleItem.manip_handles()** (reworked 2026-09-23 — **no longer
box-native**) → 9 `RectGripHandle`s at **every** angle (corners 0,2,4,6 +
centre 8 round; edge midpoints 1,3,5,7 square, aligned via `grip_render_angle` →
`_angle`). The rect has no `manip_scale`, so the rigid resize handles never
surface for it and `_is_box_native_single` is False. **`RectGripHandle(GripHandle)`**
overrides `_apply` to resize in the rect's LOCAL frame from the **press-time**
rect (`rect_grip_resize` in `geometry_2d.py`, the one home for the math): the
drag point is mapped through the press-time inverse rotation; **Ctrl** = resize
symmetrically about the centre; **Shift** = keep aspect (corners only; no effect
on edges); the centre grip (8) moves — it is a `RectTranslateGripHandle`
(`TranslateGripHandle` composed over `RectGripHandle`: the same press-time drag plus
handle snap). Angle is untouched. For a rotated rect whose
pivot follows its centre (`_pivot is None`), the pivot is **pinned** to the
press-time centre during the drag so the held opposite side does not drift in
scene; a click without a drag un-pins it (byte-identical), and Esc restores the
whole press-time rect + the original pivot. **Frame:** `manip_frame_redundant()`
is True at 0° (the outline coincides with the frame → dashed frame suppressed);
a rotated rect keeps the frame. (The earlier box-native split — rigid resize
set + `manip_box_extra_handles` centre grip unrotated, `apply_grip` grips only
when rotated — is gone.)

**Grip-shape house rule (2026-09-09 smoke; refined 2026-09-10).** Vertex/endpoint
grips and centre/**move** grips render **round** (disc); only inert/derived
convenience grips (a pure geometric midpoint that does *not* move the whole item)
stay **square**. The test is *function, not position*: a grip that translates the
whole item is a move grip → round, even when it sits at the geometric midpoint
(LineItem's midpoint grip). Each item passes its round indices to
`default_grip_handles` (`circular=`): CircleItem `{0}` (centre; radius grips are
non-vertex → square), PolylineItem all vertices (since 2026-09-24 via
`vertex_chain_grip_handles`, whose `circular` defaults to every vertex). Legacy `Model_View`
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

*Live during the rotate held-preview (historical):* `Handle._live_preview_rotation()`
swung square grips and the knob with the frame during a rotate drag; it, the
`Handle._m` back-ref and `_preview_rotation_deg` were deleted with the knob
(2026-09-23). `_render_angle` is now `grip_render_angle` alone.

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
`tests/test_manip_griphandle_arc_parity.py` (Arc — shape, end-grip apply,
posted start-grip drag, one-commit, Esc-restore) + `tests/test_arc_grip_reshape.py`
(bisector centre, endpoint slide-along-circle, span formulas, Ctrl not special, degenerate-span holds, byte-exact Esc) +
`tests/test_arc_math.py`, and
`tests/test_manip_griphandle_polygon_parity.py` (RegularPolygon parity — shape,
handle-count-tracks-sides, centre/vertex legacy-apply match, posted centre+vertex
drag, one-commit, Esc-restore, gate recognition), and
`tests/test_manip_griphandle_ellipse_parity.py` (Ellipse parity — shape [centre
round, axis grips square], major/minor/centre legacy-apply match, posted
major+centre drag, one-commit, Esc-restore, gate recognition), and
`tests/test_manip_griphandle_rect_parity.py` (Rectangle — shape, 9 grips and no
resize handles in both states, rotated-corner apply, posted centre-drag) +
`tests/test_rect_grips_unified.py` (local-frame resize, Ctrl/Shift, pivot pin,
frame suppression) + `tests/test_no_rotate_knob.py` (no knob anywhere).
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
`paper_commands.py`, `geometry_2d.py` (RectangleItem),
`dynamic_input.py`, `snap_engine.py`, `constants.py` `SELECTION_*`,
`theme.py` selection tokens.
