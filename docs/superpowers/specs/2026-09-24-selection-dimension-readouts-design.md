---
status: proposal
last-verified: 2026-09-24
verified-commit: ca61b8c
applies-to:
  - firepro3d/selection_readouts.py   # new — DimSpec + SelectionReadoutController
  - firepro3d/readout_paint.py        # new — layout + paint free functions
  - firepro3d/geometry_2d.py          # dimension_specs() + typed setters + panel rows
  - firepro3d/model_space.py          # controller composition, is_input_mode, active_hud, _refresh_all_labels
  - firepro3d/model_view.py           # hover/press routing, drawForeground paint, HUD reposition
  - firepro3d/halo.py                 # paint_halo_path
  - firepro3d/scale_manager.py        # format_span
  - firepro3d/dynamic_input.py        # _format_span delegates
  - firepro3d/theme.py                # value_font()
  - firepro3d/constants.py            # SELDIM_*
source-tasks: ["On-selection dimension readouts for 2D primitives (todo_open.md § 2D-geometry selection dimension readouts)"]
---

# Selection Dimension Readouts — Design Spec

> **Design record.** The durable contracts live in the governing specs, which this record links to
> (Rule A): primitive side → `docs/specs/2d-geometry.md §8`; pick precedence + input-mode →
> `docs/specs/selection-mode.md §15`; span formatting → `docs/specs/units-and-formatting.md`.
> The problem definition (grill Q1–Q19, 2026-09-24) is recorded in the todo entry; the visual
> values come from the signed-off mockup (`D:\Custom Code\FPD Design\dim-readouts`).

## Goal
When a 2D primitive is selected in the Block Editor, show its key dimensions as text-only labels
on the geometry (lengths, radii, angles with a dashed reference arc). The labels update live while
editing. Hovering one highlights it with HALO. Clicking one opens a one-field HUD, and typing a
value drives the geometry.

## Motivation
The primitives' dimensions are only visible as read-only raw-mm property rows today. Direct,
unit-aware readouts on the canvas give CAD-standard "temporary dimension" feedback (Revit/AutoCAD
style) without the weight of dimensional constraints, which come later. The component is built
once so that the gridline-spacing / constraint dims and ALIGN §8 node dims can adopt it.

## Architecture & Constraints
- **Primitives describe; they don't own.** Each primitive exposes a pure
  `dimension_specs() -> list[DimSpec]`. A readout is never a `QGraphicsItem` and never a child of
  the primitive. So by construction it is outside `shape()`, bounding rects, snap, HALO
  resolution, the manipulator frame, serialization and copy/paste (grill Q14).
- **Stateless, per-frame.** The readout list is rebuilt from the live selection per paint and per
  pick (per-frame memo). No geometry-change plumbing is needed, and undo item-replacement cannot
  leave dangling references.
- **Repaint is the only trigger.** The view runs `MinimalViewportUpdate`, and labels sit outside
  item dirty regions. The controller forces a full `viewport().update()` on every view on:
  - scene `changed` (while active);
  - `selectionChanged`;
  - an explicit `refresh()` from `Model_Space._refresh_all_labels` (units/precision).
- **Pixel-space layout.** Labels are screen-constant (`SELDIM_SIZING = "screen"`). Layout is
  computed from the view transform by one shared function, used by both paint and pick, so
  "hidden ⇒ unpickable" holds.
- **Glyph-outline text.** Label text is painted via `QPainterPath.addText` + `fillPath`, never
  `drawText` through a document. This avoids the live-canvas engine==0 hazard.
- **Units boundary.** Values are mm / degrees internally. Display goes through
  `ScaleManager.format_length` / `format_span`. The HUD parses via its existing `DIMENSION` /
  `SPAN` field kinds.

### Units
| Unit | Home | Responsibility |
|---|---|---|
| `DimSpec` | `selection_readouts.py` | frozen dataclass. Fields: `kind` (linear/angular), `key` (stable id, e.g. `length`, `seg:2`, `ang:1`), `field` (HUD label), `prefix` (`""`/`R`/`R1`/`R2`), linear `a`,`b`,`away`, angular `center`,`ref_radius`,`start_deg`,`span_deg` (Y-up, `arc_math` convention), `value` (mm or deg), `field_kind` (`DIMENSION`/`SPAN`), `minimum`, `maximum`, `apply(float)` (pure mutation, no undo) |
| `dimension_specs()` | each primitive, default `[]` on `Geometry2DMixin` | per-primitive table → `2d-geometry.md §8` |
| typed setters | each primitive | anchors + floors → `2d-geometry.md §8`; the single mutation path shared by readouts and panel rows |
| `SelectionReadoutController` | `selection_readouts.py`, composed on `Model_Space` as `self.readouts` | gate `readouts_active()`, `specs_for_frame()`, `hover_at(view, vp_pos)`, `press_at(view, vp_pos)`, edit session, `refresh()`, repaint wiring |
| layout + paint | `readout_paint.py` | `layout_linear`, `layout_angular` (→ label rect, rotation, `fits`), `paint_readout`, `paint_reference_arc`. Knows nothing about primitives (reusable by follow-ups) |
| glow | `halo.py` | `paint_halo_path(painter, path, …)`; `paint_halo_highlight` delegates to it |
| formatter | `scale_manager.py` | `format_span(deg)` (unsigned 0–360); `dynamic_input._format_span` delegates |
| font | `theme.py` | `value_font(px) -> QFont` (`FONT_VALUE`) |
| constants | `constants.py` | `SELDIM_*` (below) |

### Constants (signed-off mockup, grill Q12 applied)
`SELDIM_FONT_PX = 10`, `SELDIM_LABEL_OFFSET_PX = 14` (applied to **every** linear label, away side),
`SELDIM_ARC_REF_FRAC = 0.19`, `SELDIM_ARC_REF_MIN_PX = 25`, `SELDIM_ARROW_PX = 7`,
`SELDIM_DASH = (4, 3)`, `SELDIM_FIT_MARGIN_PX = 4`. Text-only (no box), aligned + readable
rotation, symbol prefixes on, arrows on angular ends. Colours: text `ink`, arc + arrows `muted`,
hover glow = HALO accent (`HALO_TRACE_*`).

## Design Decisions
1. **Painted overlay + controller, not scene items or manipulator handles.**
   - Rejected, scene items (`ItemIgnoresTransformations` children): they leak into
     `itemsBoundingRect`/fitInView and snap iteration, need HALO special-casing, need
     hand-rolled rotated text, and every Q14 exclusion becomes a guard to write.
   - Rejected, manipulator `Handle`s: gestures ≠ value editors, no HALO glow, couples to the
     rebake cycle, overloads the manipulator.
   - Chosen, the overlay: it matches the gridline-spacing precedent.
2. **Readout is a separate transient record, not a child of the primitive** (user-confirmed).
3. **No cache between frames** (see Architecture). ≤ `GRIP_OBJECT_LIMIT` items × a few specs is
   trivial.
4. **Visibility gate `readouts_active()`** is true only when all of these hold:
   - `scene_role == "block_editor"`;
   - `mode in (None, "select")`;
   - the placement HUD is not engaged;
   - no inline text edit is active;
   - 1 ≤ selected primitives ≤ `GRIP_OBJECT_LIMIT`.

   Grip and manipulator drags remain active. Transform commands switch mode, so they are
   excluded.
5. **Fit rule.**
   - Linear: drop the label when the on-screen segment length < label width + `SELDIM_FIT_MARGIN_PX`.
   - Angular: drop the label when the reference radius (px) > the shorter leg (px). For an arc
     the legs are the radius.
6. **Hover** (`Model_View.mouseMoveEvent`, before `sc.halo_update`):
   - `readouts.hover_at` yields to `manip.hit_handle` (grips win).
   - On a label hit it stores the hover key, calls `halo_clear()` and skips `halo_update`
     (label beats parent geometry).
   - The status readout shows `<field> · click to edit`.
   - The glow is painted only when HALO is enabled.
7. **Press** (`Model_View.mousePressEvent`, left, before rubber-band arming):
   - `readouts.press_at` hits a label (grips still win) → `begin_edit`, accept, return without
     `super()`.
   - So there is no deselect, no band and no manipulator move. It works with HALO disabled.
8. **Edit session:**
   - `DynamicInputHud` on a one-field schema generated from the spec. Seeded with the current
     value, parented to the viewport, latched at the label anchor via `place_dynamic_input`,
     then `engage()`.
   - `committed`: out-of-range → `reject_commit()` (red border, stays open). Valid →
     `spec.apply(v)` → `push_undo_state()` (mutate-then-push, gridline pattern, one undo step)
     → end.
   - `cancelled` (Esc) → end.
   - Selection change, mode change, or a press outside the HUD → cancel. That press is
     consumed.
9. **Input-mode generalization:**
   - `Model_Space.is_input_mode()` = placement HUD engaged **or** readout edit active. This
     inherits the inert-mouse and Ctrl+Z-to-field guards.
   - The view's HUD code (press focus-restore gate, `_reposition_dynamic_input`,
     `scrollContentsBy`) reads `sc.active_hud()` instead of `sc.dynamic_input`.
   - **Plan-time check:** confirm the global Ctrl+Z shortcut honours `is_input_mode()`.
10. **Property-panel fold-in:**
    - Line Length, Rect Width/Height, Circle Radius and Arc Radius/Span rows change from
      `"label"` to editable dimension rows (Span angle-typed).
    - The ellipse rows are relabelled `R1`/`R2`.
    - `set_property` routes to the same named setters. The panel wraps them in the same
      mutate-then-push helper.
    - The `test_dynamic_input_parity.py` Span-row assertion is updated. This is a deliberate
      contract change.

## Acceptance Criteria
- [ ] Block Editor only. Selected primitives (≤ `GRIP_OBJECT_LIMIT`) show readouts per `2d-geometry.md §8`:
      line/reference line length; rect W/H; circle R; arc angle + R; ellipse R1/R2; polyline segment lengths +
      vertex angles (≤180° side; closed = closing segment + all vertices; zero-length skipped); polygon defining
      radius. Text/Spline none. None above the limit.
- [ ] Visuals match the signed-off constants (Consolas 10 px text-only, aligned/readable, 14 px away-side offset on
      every linear label, dashed `muted` reference arc 0.19×r min 25 px with arrows, `ink` text) in dark and light themes.
- [ ] Labels refresh live on grip drag, manipulator move/resize, panel edit, undo/redo, units/precision change
      (immediately, no mouse move), zoom/pan.
- [ ] Hidden during placement tools, transform commands, inline text edit, and while the placement HUD is engaged.
- [ ] Labels that do not fit are neither painted nor pickable. No overlap solver.
- [ ] Pick order: grips > visible labels > HALO geometry. Hovering a label glows only the label (when HALO is enabled).
- [ ] A single click on a label opens the latched one-field HUD, pre-filled and selected. There is no selection change,
      no band and no move. Works with HALO disabled.
- [ ] Enter commits exactly one undo step. Esc, click-away (consumed), selection change and mode change cancel.
      Invalid or out-of-range input → red border, stays open. Ctrl+Z inside the field edits the field text.
- [ ] Typed edits honour anchors and floors (`2d-geometry.md §8`).
- [ ] Transient: absent from `.fpd`/`.fpdb`, placed instances, thumbnails, snap/ALIGN, `itemsBoundingRect`/fitInView,
      manipulator frame.
- [ ] `ScaleManager.format_span` is the one unsigned-angle formatter, and the HUD still round-trips.
- [ ] Panel rows Length/Width/Height/Radius/Span are editable, unit-formatted, and undoable through the same setters.
      Ellipse rows read R1/R2.
- [ ] Tests at every level of the Testing Strategy, with acceptance-critical guards mutation-proved.

## Verification Checklist
- [ ] All acceptance criteria met.
- [ ] Unit + integration + render tests pass. Full suite run once (no cross-test crash).
- [ ] Whole-repo grep for `_format_span` / changed panel labels, then a launch smoke of the app.
- [ ] Live smoke checklist in a fully restarted app (hover, click-away, Ctrl+Z routing, units change, zoom).
- [ ] Governing specs stamped (`2d-geometry.md`, `selection-mode.md`, `units-and-formatting.md`).

## Testing Strategy
- `tests/test_selection_readouts_specs.py` (pure):
  - every primitive's `dimension_specs()` values and anchors;
  - polygon inscribed and circumscribed;
  - polyline open/closed angles on the ≤180° side, zero-length skip;
  - every setter's anchor and floor;
  - `apply` round-trips.
- `tests/test_readout_paint.py`:
  - fit vs hidden;
  - readable-rotation flip;
  - away-side offset;
  - pixel-sampled `ink` text and `muted` dashed arc in both themes, on real primitives (offscreen
    72-DPI caveat: sample the geometry, not font metrics).
- `tests/test_selection_readouts_interaction.py`: a real Block Editor scene with a shown `Model_View`
  and posted mouse events through the viewport, covering:
  - select shows labels, deselect removes them;
  - grip drag updates the text;
  - label hover → HALO label state, not the parent;
  - click → HUD engaged, selection unchanged, no band;
  - Enter → one undo step; Esc restores; click-away consumed;
  - units change repaints without a move;
  - hidden labels are unpickable;
  - more than 100 selected → none;
  - absent from serialization and `itemsBoundingRect`.
- `tests/test_format_span.py`: the promoted formatter + HUD delegate.
- Each acceptance-critical guard is shown RED with its fix reverted.

## Edge Cases & Error Handling
- Setters clamp to the existing floors and never raise into paint paths. Non-finite values render
  as `0`/`0°`.
- The primitive is deleted, or undo replaces it, while the editor is open → selection change →
  cancel.
- A setter exception is logged and the session is cancelled. The undo push follows the mutation,
  so there is no partial undo entry.
- A zero-length segment gives no length label, and no angle at either of its vertices.

## Follow-ups (filed in todo_open.md)
- Shared painter for gridline spacing + constraint dims.
- ALIGN §8 node/sprinkler dims.
- Unreachable manipulator typed HUD.
- Readout overlap avoidance.
