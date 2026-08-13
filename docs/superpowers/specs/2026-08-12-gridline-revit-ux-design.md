---
status: proposal
last-verified: 2026-08-12
verified-commit: 6d27212
applies-to:
  - firepro3d/gridline.py
  - firepro3d/grid_lines_dialog.py   # to be deleted
  - firepro3d/model_space.py
  - firepro3d/property_manager.py
  - firepro3d/ribbon_bar.py
  - main.py
  - firepro3d/scene_io.py
  - firepro3d/constants.py
governs-spec: docs/specs/grid-system.md   # updated in place at Account (Phase 6)
---

# Gridline UX Re-architecture (Revit-aligned) — Design Spec

**Date:** 2026-08-12
**Complexity:** Large
**Status:** proposal
**Source task:** TODO.md — "polish gridlines" (grill 2026-08-12; scope locked in Phase 2)

> This is the **plan-of-record** for the change. The governing contract
> (`docs/specs/grid-system.md`) is updated *in place* at wrap-up (Account /
> Phase 6) to match as-built behavior — not ahead of the code.

## 1. Goal

Replace the modal Grid Lines dialog with a **Revit-style on-canvas gridline
workflow**: draw gridlines directly on the canvas (Draw tab, mirroring the Line
tool), and edit all geometry and bubble properties through the right-side
Properties panel. Fix the correctness bugs surfaced along the way (grip drag,
angled-gridline spacing, dash-dot PDF legibility) and adopt a native parametric
data model (origin + length + angle + per-bubble offsets).

## 2. Motivation

The gridline system diverged from both its spec and the app's Revit-aligned
mental model:

- **Editing lives in a modal table** (`grid_lines_dialog.py`) rather than
  on-canvas + Properties panel, unlike every other entity.
- **Grip drag is broken** — `GridlineItem.apply_grip` *translates the whole
  line* instead of extending/shortening (contradicts its own call-site comment
  at `model_space.py:4440` and spec §5.2).
- **Angled gridlines are second-class** — spacing dimensions bucket by a binary
  `dy>=dx` test and mis-pair non-parallel lines; the near-45° boundary flips
  discontinuously.
- **Dash-dot gridlines read as solid** when zoomed out and in exported PDF
  (the pattern scales with the computed pen width).
- The bubble standoff is a length-proportional "overshoot" baked into geometry
  (§7.6), not an editable property.

## 3. Architecture & Constraints

### 3.1 Parametric data model (source of truth)

`GridlineItem` remains a `QGraphicsLineItem` — so snap, spacing, elevation
projection, and `paint()` keep reading `line().p1()/p2()` with no per-consumer
shim — but its **authoritative editable state is parametric**:

| Field | Type | Notes |
|-------|------|-------|
| `_origin` | `QPointF` | the "main point" (1st-clicked endpoint) |
| `_length` | `float` | mm |
| `_angle_deg` | `float` | 0–360°, **Y-up** (0°=East, CCW+) — same convention as the Line tool's Tab input |
| `_bubble1_offset` | `float` | mm, along-axis outward standoff at the origin end |
| `_bubble2_offset` | `float` | mm, along-axis outward standoff at the far end |
| `_bubble1_visible` / `_bubble2_visible` | `bool` | as today |
| `_label_text`, `_locked`, `_display_overrides` | — | as today |

**Derived state** (the `QGraphicsLineItem` line, bubble/grip/lock positions) is
written *only* by a single **`_rebuild_geometry()`**:

```
p1 = _origin
p2 = _origin + _length · (cos θ, −sin θ)      # θ = radians(_angle_deg), Y-up→scene Y-down
setLine(p1, p2)
bubble1 at  p1 − _bubble1_offset · û          # û = unit(p1→p2); outward = away from the span
bubble2 at  p2 + _bubble2_offset · û
reposition grips + lock indicator
```

Every mutation (placement, grip drag, panel edit, load) routes through
`_rebuild_geometry()`. `line()` therefore always reflects the parametric truth.

**Retired:** the length-proportional overshoot (`GRIDLINE_BUBBLE_OVERSHOOT_FRAC`,
§7.6). `line()` is now the *clicked span* (origin→far); bubbles stand off by the
explicit absolute offsets; `paint()` draws from `p1 − off1·û` to `p2 + off2·û`,
still shortened at each end to meet the visible bubble edge (existing `scene_r`
logic, measured from the offset bubble center).

### 3.2 On-canvas placement — share the Line tool machinery

A new `draw_gridline` scene mode **reuses the same code paths** as `draw_line`
— `_press_draw_line`, the `_handle_tab_input` dynamic-input branch, the
move-time `_draw_dim_hint` overlay, and `_constrain_angle` (Ctrl) — with the
**only** divergence being an item factory:

- `draw_line`     → `LineItem`
- `draw_gridline` → `GridlineItem` (appended to `_gridlines`, `apply_category_defaults`, `requestPropertyUpdate` emitted)

This *structurally guarantees* the "mirrors line placement one-for-one"
requirement (1st click = origin, 2nd click = length+angle, Ctrl-constrain, Tab
exact input, `single_place_mode` handling). The bespoke `_press_gridline` stub
is removed. The ribbon "Gridlines" button moves to the **Draw tab** and sets
`draw_gridline` instead of opening the dialog.

### 3.3 Properties-panel geometry editing

`GridlineItem.get_properties()` exposes the geometry rows below. X/Y/Length/offsets
use the `dimension` type (`DimensionEdit`, mm); **Angle is a plain numeric field**
(`string` type, parsed to 0–360 with a `°` suffix — degrees are not an mm
quantity, mirroring the old dialog's plain-numeric angle cell), not `dimension`:

| Row | Type | `set_property` effect |
|-----|------|-----------------------|
| Origin X / Origin Y | dimension (mm) | set `_origin.x()/.y()` → **whole line translates** |
| Length | dimension (mm) | set `_length` (guard `>0`), origin fixed |
| Angle | string (numeric, ° suffix) | parse + set `_angle_deg` mod 360 → rotate about origin; invalid reverts |
| Label | string | relabel + duplicate re-scan |
| Lock | enum | set `_locked` |
| Bubble 1 / 2 visible | enum | toggle visibility |
| Bubble 1 / 2 offset | dimension (mm) | set `_bubbleN_offset` |
| End X / End Y | label (read-only) | derived, informational |

Geometry/offset commits call `scene.push_undo_state()` after mutating (model-space
property edits don't self-capture undo today) so each panel commit is one undo
step.

### 3.4 Angled spacing — parallelism grouping

`_compute_gridline_spacing` replaces the binary `dy>=dx` bucket with **angle
clustering**: each gridline's direction angle mod π; two gridlines are parallel
(eligible for a spacing dimension) iff their angles agree within `ε` (a small
fixed tolerance). Within a parallel cluster, project onto the cluster's shared
normal, sort by that projection, and dimension adjacent pairs where ≥1 member is
selected. **Non-parallel neighbors get no dimension.** The perpendicular-vector
sign convention is made explicit/consistent so offsets and spacings round-trip.

### 3.5 Dash-dot legibility

Root cause: the gridline pen is non-cosmetic (width in *scene* units,
`GRID_WIDTH/sx`), and `Qt.PenStyle.DashDotLine`'s pattern is expressed in
pen-width multiples, so zooming out (or rendering at print DPI) collapses the
dashes to apparent-solid.

Fix: replace the enum with an explicit `pen.setDashPattern([...])`:
- **Screen path:** dash/gap lengths targeting a fixed *pixel* length, i.e.
  `target_px / sx` in scene units → constant on-screen appearance at any zoom.
- **Paper path (`_paper_render`):** dash/gap in fixed *mm*, scaled by
  `_paper_line_w` so a PDF reads as dash-dot.

Exact dash/gap lengths tuned via a throwaway mockup **and a real PDF export
check** (visual decision — mockup-gated).

### 3.6 Cross-references (unchanged owners)

- Snap participation → `docs/specs/snapping-engine.md` §5 (reads `line()`; unaffected).
- Paper-space bubble true-scale → `docs/specs/paper-space.md` §9.9.1 (category-owned label height; unaffected by the offset change).
- Display Manager "Grid Line" category → `display_manager.py._apply_gridline` (freshly-placed gridlines must adopt current category color/scale — §5 below).

## 4. Data Flow

1. **Placement:** ribbon Draw→Gridline sets `draw_gridline` → click/click (or click+Tab) → factory builds `GridlineItem(origin, length, angle)` → `apply_category_defaults` → `_gridlines.append` → `requestPropertyUpdate`.
2. **Panel edit:** `PropertyManager._apply_property` → `GridlineItem.set_property` mutates a parametric field → `_rebuild_geometry()` → `push_undo_state()` + `sceneModified`.
3. **Grip drag:** `model_space` grip path → `apply_grip(index, pos)` now extend/shortens (opposite end fixed) → `_rebuild_geometry()`; multi-select applies the same length/endpoint delta.
4. **Serialize:** `to_dict()` (parametric) → `scene_io` and `_capture_network` (both).
5. **Load:** `from_dict()` reads parametric (new) or derives from `p1/p2` (legacy).

## 5. Design Decisions

- **D1 — Native parametric storage (not p1/p2 + derived).** Chosen over
  minimal-ripple p1/p2-plus-two-scalars. Rationale: the panel edit math
  (translate-whole-line / length / angle) falls straight out of parametric
  fields, and the model matches the new UX. Cost: both serialization paths and
  `from_dict` migration are rewritten — accepted. `line()` is kept eagerly in
  sync so read-only consumers (snap/spacing/elevation) need no changes.
- **D2 — Placement by code-sharing, not duplication.** `draw_gridline` rides the
  `draw_line` handlers with an item factory, guaranteeing behavioral parity and
  preventing drift.
- **D3 — Absolute mm bubble offset, retire the fractional overshoot.** Bubble
  standoff no longer scales with gridline length; default is a fixed
  `GRIDLINE_BUBBLE_OFFSET_MM` constant.
- **D4 — Grip = extend/shorten along line (opposite end fixed).** Supersedes the
  whole-line-translate bug; re-angling is *not* a grip gesture (lives in the
  panel Angle field / placement). Spec §5.2 updated at Account.
- **D5 — Parallelism-based spacing pairing.** Supersedes binary `dy>=dx` for
  spacing only; naming keeps `dy>=dx` (standard structural convention).
- **D6 — Delete the dialog; batch creation = copy/paste.** Quick Fill is
  dropped; an on-canvas array/offset is a filed follow-up.
- **D7 — Fresh-placement adopts current DM category.** Placement applies the
  live "Grid Line" color/scale (not the hardcoded default).

## 6. Acceptance Criteria

- [ ] Draw-tab **Gridline** tool places gridlines on canvas with **behavior
      identical to the Line tool** (1st click origin, 2nd click length+angle,
      **Ctrl** angle-constrain, **Tab** exact length+angle input, single-place).
- [ ] `grid_lines_dialog.py`, `_open_grid_dialog`, the `GridLinesDialog` import
      and its wiring, and its tests are **removed**; default 3+3 seed still works.
- [ ] Properties panel edits — **Origin X/Y translate the whole line**; **Length**
      moves the far end (origin fixed); **Angle** rotates about the origin; each
      commit is one undo step.
- [ ] Per-bubble **visible** + **offset (mm)** editable; default offset is the new
      absolute constant; bubbles stand off along the axis; the line meets the
      bubble edge.
- [ ] **Grip drag extends/shortens along the line, opposite end fixed** (no more
      whole-line translation); multi-select moves the same grip on all.
- [ ] Spacing dimensions appear **only between parallel gridlines** (within ε);
      non-parallel neighbors show none; **double-click-to-edit retained**.
- [ ] Gridlines render as a **legible dash-dot at fit-zoom and in exported PDF**
      (not apparent-solid).
- [ ] Freshly-placed gridline immediately reflects the current DM "Grid Line"
      color/scale; duplicate-warning keeps a **constant border width**.
- [ ] Naming keeps the `dy>=dx` letters/numbers scheme.
- [ ] New parametric fields persist through **both** `scene_io` and undo
      (`_capture_network`); **legacy `p1/p2` files load** (origin/length/angle
      derived, offsets defaulted).
- [ ] `GRIDLINE_BUBBLE_OFFSET_MM` added; `GRIDLINE_BUBBLE_OVERSHOOT_FRAC`
      retired; `DEFAULT_GRIDLINE_SPACING_IN/_LENGTH_IN` renamed to `_MM`.

## 7. Deferred (filed as follow-ups)

- Angled gridlines projecting into **elevation** views (section-view territory).
- On-canvas **array/offset** for fast bay layout (copy/paste covers replication).
- Perpendicular **bubble elbow/jog leader** + per-view leader independence.
- Display-Manager **linetype** property (solid/dashed/center/…).
- On-canvas interactive **rotate** handle (angle lives in the panel).

## 8. Verification Checklist

- [ ] Unit: parametric edits (translate-whole-line, length, angle), bubble
      offset, `_rebuild_geometry` invariants.
- [ ] Unit: parallelism spacing pairing (parallel → dim; non-parallel → none;
      near-45° stable) + perpendicular-sign round-trip regression.
- [ ] Unit: serialization round-trip (both paths) + legacy `p1/p2` migration.
- [ ] Functional/widget (qapp fixture; drive widgets not slots): placement
      mirrors Line tool incl. **Tab** and **Ctrl**; property-panel edits reach
      geometry; copy/paste of a lone gridline works.
- [ ] Real **PDF export** dash-dot legibility check (zoomed-out sheet).
- [ ] No regressions: default seed, snap on gridlines, elevation cardinal
      filtering, duplicate warnings, lock enforcement.
- [ ] Full suite green (chunked per OneDrive-venv guidance).

## 9. Existing Code Context

| File | Role | Action |
|------|------|--------|
| `firepro3d/gridline.py` | `GridlineItem` + `GridBubble` | Rewrite to parametric + offsets + grip fix + dash pattern |
| `firepro3d/grid_lines_dialog.py` | modal dialog | **Delete** |
| `firepro3d/model_space.py` | placement, grip, spacing, body drag | Add `draw_gridline` mode share; grip path; parallelism spacing |
| `firepro3d/property_manager.py` | panel dispatch | (reads new `get_properties`; undo push in `set_property`) |
| `firepro3d/ribbon_bar.py`, `main.py` | ribbon wiring | Move button to Draw tab; drop dialog import/wiring; seed rewire |
| `firepro3d/scene_io.py` | file serialization | Parametric + legacy migration |
| `firepro3d/constants.py` | constants | `GRIDLINE_BUBBLE_OFFSET_MM`; retire overshoot frac; `_IN`→`_MM` rename |
| `docs/specs/grid-system.md` | governing spec | Updated in place at **Account (Phase 6)** |
