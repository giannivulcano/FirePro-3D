---
status: partial          # D1–D15 BUILT on feat/scene-tools-2d (unmerged) — full suite + user smoke pending; §1–§6 are the PRE-build as-built record at c47ab60
last-verified: 2026-09-26
verified-commit: d9d6f20   # branch feat/scene-tools-2d; prior c47ab60 (orphan-gate as-built audit)
applies-to:
  - firepro3d/scene_tools.py
  - firepro3d/tool_geometry.py
  - firepro3d/modify_tools_controller.py
  - firepro3d/transform_ghost.py
  # Tool state machines that live on the scene (shared with other specs — this
  # spec governs only the modify-tool rows/handlers listed in §1):
  - firepro3d/model_space.py
source-tasks: [orphan-gate review — surface scene tools on the 2D-Geometry contextual ribbon]
---

# Scene Tools (2D modify tools) — Design Spec (current behaviour + divergences)

> **Orphan-gate spec (2026-09-25).** Sections 1–7 describe what the code does
> *today* at `c47ab60`. The **ratified as-intended contract is "Design
> Decisions" D1–D15** (2026-09-25 grill); where a §5 "as-proposed" note
> disagrees with D1–D15, D1–D15 wins. §8 is kept as the grill's question log.

## Goal

Give the 2D-geometry authoring surface (Block Editor scratchpad + the
`Modify | <Element>` geo2d contextual tab) a reachable, correct set of modify
tools. Target set for this milestone (user brief): **Copy, Cut, Paste** (ghost
follows cursor, click commits), **Duplicate** (like Move but keeps the
original), **Move**, **Rotate** (pick base point), **Offset** (incl. closed
shapes), **Array**; possibly **Trim**.

## Motivation

`scene_tools.py` (`SceneTools`, composed as `scene._tools`) and its scene-side
state machines survive from the pre-ribbon era, but the ribbon buttons that
armed them were removed. Most tools are now unreachable, several are wired to
dead plumbing, and none has a governing behaviour spec
(`model-space-architecture.md` governs structure only;
`parametric-constraint-system.md` governs constraints).

## Architecture & Constraints

- **Home split (as-built).** Pure item-aware math lives in `tool_geometry.py`
  (no scene state). `SceneTools` holds the commit/mutation halves plus trim/
  extend/merge/constraint/align click handlers. The *mode state machines*
  (press/move/key handlers, previews, set_mode teardown) live on `Model_Space`
  and route through its `_PRESS_DISPATCH` / `_MOVE_DISPATCH` /
  `_PREVIEW_DISPATCH` tables and `_SCHEMA_FOR_MODE` / `_APPLIER_FOR_MODE` HUD
  tables. See `model-space-architecture.md` for the decomposition contract.
- **Coordinates.** Scene is Y-down mm; user-facing angles are Y-up CCW+
  (`project_rotation_conventions_yup_vs_qt`). `CAD_Math.rotate_point(p, c, a)`
  rotates **CCW in Y-down math = visually CW** for `a > 0`; every
  `manip_rotate` therefore calls it with `-angle_deg`. `ArcItem._start_deg` is
  Y-up CCW (grip_points use `cy - r·sin`).
- **Containment C1.** Loose-geometry *authoring* modes are gated by
  `Model_Space.authoring_allowed` (`_LOOSE_AUTHORING_MODES` = draw modes +
  text/dimension). **None of the modify modes are in that set**, so every modify
  tool can be entered in the plan scene too.
- **Selection manipulator** already provides rigid move/rotate/scale for
  selected items via per-item `manip_*` / `translate` protocol
  (`selection-manipulator.md`) — a parallel path to the legacy `rotate`/`scale`
  modes (§6).

(Sections below are appended as the review proceeds.)

## 1. Tool inventory and state machines (as-built, `c47ab60`)

Each row: mode string(s) → where each hop lives. "Press"/"Move" = the
`_PRESS_DISPATCH` / `_MOVE_DISPATCH` row on `Model_Space`; "HUD" = a
`_SCHEMA_FOR_MODE` + `_APPLIER_FOR_MODE` pair (Dynamic Input); "Tear-down" =
the `set_mode` clean-up branch; "Undo" = where `push_undo_state` is called.
Verified by reading every row and by a read-only runtime probe (real
`Model_Space` + `Model_View`, offscreen) — probe results are quoted as
**[probe]**.

| Tool | Mode(s) | Press → commit | Move / preview | HUD | Esc / cancel | Undo |
|---|---|---|---|---|---|---|
| Copy | — (action) | `copy_selected_items()` → JSON of `to_dict()` (+ node dicts) on the system clipboard | — | — | — | none (no scene change) |
| Cut | — (action) | ribbon lambda: `copy_selected_items(); delete_selected_items()` | — | — | — | via delete |
| Paste | `paste` | `_press_paste_move`: click 1 = base point, click 2 → `paste_items(click2 − click1)`; then `set_mode(None)` | `_move_paste_move` → `_preview_from_move`: ghost appears only **after** click 1, built by `_clipboard_ghost_paths` | none (paste deliberately excluded from `_SCHEMA_FOR_MODE`, "F2") | generic Esc → `set_mode(None)`; ghost cleared in set_mode | after `paste_items` in `_press_paste_move` |
| Duplicate | `duplicate` (**no dispatch row**) | Ctrl+D / plan context menu → `set_mode("duplicate")`: mode has no press/move handler; entry clears the selection **[probe: mode='duplicate', 0 selected]**. Separately `duplicate_selected()` = instant copy+paste at fixed (+10, +10) mm | — | — | — | `duplicate_selected` pushes once |
| Move | `move` | Ctrl+M captures `_selected_items`; click 1 = base, click 2 → `move_items(offset)` | `_move_paste_move` + S2 `HandleSnapSession` (handles-only destination snap) | `displacement` (dX/dY, needs anchor) → `_apply_move_displacement` | generic | after `move_items` |
| Rotate (legacy) | `rotate` | click 1 = pivot, click 2 → `_tools._apply_rotate(pivot, atan2(-dy,dx))` — the **absolute** heading of the cursor, no reference ray | dashed pivot→cursor line + status "Rotate: n°" (no ghost) | none (instruction says "Tab for exact angle"; `numericInputRequested` is never emitted) | set_mode clears pivot + line | after apply |
| Scale (legacy) | `scale` | click 1 = base; **no commit path** — commit only via `complete_numeric_input("scale")`, whose `numericInputRequested` signal is never emitted | none (`scale` absent from `_MOVE_DISPATCH`) | none | set_mode | (never reached) |
| Mirror | `mirror` | click 1/2 = axis → `_apply_mirror` (copies), then `confirmRequested("mirror_delete")` | dash-dot axis line | none | set_mode | pushed before the delete-originals answer; delete pushes again |
| Offset | `offset` → `offset_side` | `_press_offset`: pick entity under raw cursor (`items(pos)[0]` filtered to Line/Polyline/Circle/Rect/Arc/Ellipse/Spline) → `offset_side`; click → `make_offset_item(source, signed)` → add to per-type list; re-arm `offset` | `_move_offset_side`: distance = `perpendicular_distance(source, cursor)`; dashed live preview item re-created each move | none (status says "Tab = type distance" — no schema; `_offset_manual` only settable from dead `complete_numeric_input`) | set_mode clears preview/source/highlight; Enter commits like a click | after each commit |
| Array | — (dialog) | `ArrayDialog` → `array_items(params)`: linear = repeated `paste_items(offset)` through a temporarily swapped clipboard; polar = rewrites dict keys then `paste_items(0,0)` | none | none | dialog cancel | one push after all copies |
| Trim | `trim` → `trim_pick` | `SceneTools._handle_trim_click`: pick cutting edge, then click target piece; Line = move nearer endpoint; Circle → Arc; Arc = shorten | edge highlight only | none | set_mode clears edge + highlight ("right-click to cancel" actually opens the context menu, whose first item is Cancel) | after each trim |
| Extend | `extend` → `extend_pick` | `_handle_extend_click`: boundary, then endpoint (Line / Polyline end vertex only) | highlight | none | set_mode | after each extend |
| Break / Break-at-point | `break`, `break_at_point` | pick object, then 1 or 2 points → `_break_item` / `_break_at_point` | highlight | none | set_mode | after |
| Fillet / Chamfer | `fillet`, `chamfer` | pick 2 **LineItems** → preview → Enter commits (`_commit_fillet/_commit_chamfer`); radius/dist fixed at 5.0 (Tab path dead) | dashed circle / bevel line | none | set_mode | after |
| Stretch | `stretch` | view-side right-to-left rubber band (`Model_View` release) → `begin_stretch_crossing`; base click, dest click → `_commit_stretch` | dashed line | none | set_mode | after |
| Merge points | `merge_points` | two endpoint clicks → `apply_grip` | marker item | none | set_mode | after |
| Join / Explode | — (methods) | `join_selected_items` / `explode_selected_items` | — | — | — | after |
| Constraints | `constraint_concentric`, `constraint_dimensional` | `_handle_constraint_*_click` | — | none (dimensional opens a modal `QDialog`) | set_mode | after |
| Align | `align` | `_press_align` → `_execute_align` + `_PadlockItem` | `_move_align` highlight / ghost | none | Esc #1 clears reference, #2 exits | **before** the move (`_execute_align` pushes, then moves) |
| Gridline array / offset | `gridline_array`, `gridline_offset` | `_press_gridline_replicate` → `GridlineItem.array_copies / offset_copy` | ghost lines (`_build_replicate_ghost`) | `spacing_count` / `distance` | Esc cancels | after commit |

### 1.1 Hop-level defects found while tracing (code-verified; runtime-confirmed where marked)

1. **Missing Qt imports in `scene_tools.py`.** `QGraphicsRectItem`,
   `QGraphicsEllipseItem`, `QDialog`, `QVBoxLayout`, `QLabel` are used but never
   imported (the module imports only `QGraphicsItem, QGraphicsPathItem,
   QGraphicsLineItem, QApplication`). Consequences **[probe]**:
   `_highlight_item(CircleItem)` and `_highlight_item(unrotated RectangleItem)`
   raise `NameError` — so **picking a circle or an axis-aligned rectangle in
   Offset, Trim, Extend, Break, Break-at-point, Fillet or Chamfer raises**; the
   first Merge-points click raises (`QGraphicsEllipseItem`); the second
   Dimensional-constraint click raises (`QDialog`, code-read only).
2. **Dead numeric-input plumbing.** `numericInputRequested` is declared and
   connected in `main.py` but never emitted, so `complete_numeric_input`
   (offset typed distance, rotate typed angle, scale factor, fillet radius,
   chamfer distance) is unreachable. Scale therefore has **no commit path at
   all**; the "Tab = …" instruction strings for offset / rotate / scale /
   fillet / chamfer are false. Tab reaches `begin_dynamic_input`, which has no
   schema for those modes.
3. **Mode entry clears the selection for selection-operand tools.** `set_mode`
   calls `clearSelection()` for every mode except `select, stretch, move,
   rotate, scale, radiation_*`, and only `move/rotate/scale` snapshot
   `_selected_items`. `mirror` is neither → `_apply_mirror` sees an empty
   selection and produces nothing **[probe: 0 selected, `_selected_items=None`,
   0 copies]**. Same trap for the dead `duplicate` mode.
4. **Paste plumbing.**
   - `paste_items` iterates `clipboard_data()` without a `None` guard → with an
     empty / non-JSON clipboard it raises `TypeError` **[probe]**. The window
     Ctrl+V `QShortcut` enters `paste` unconditionally (the scene-level Ctrl+V
     handler that checks the clipboard is shadowed), and the ribbon "Paste"
     button calls `paste_items()` with **no offset argument** (TypeError on
     click, code-read).
   - Ghost key drift: `ArcItem.to_dict()` emits `"type": "arc"` (the paste
     branch matches `"arc"`), but `_clipboard_ghost_paths` looks up
     `"draw_arc"` → **arc paste has no ghost [probe: 0 paths]**.
     `GridlineItem.to_dict()` emits no `"type"` (paste detects gridlines by
     keys) but the ghost looks for `"gridline"` → **real gridline paste has no
     ghost [probe]**; `test_clipboard_ghost_paths_gridline` passes only because
     it feeds a synthetic dict carrying `"type": "gridline"` (a VC3 synthetic
     stand-in). Block instances have no ghost.
   - `paste_items` has **no `"text"` branch** → TextItem is silently dropped
     by Paste, Duplicate and Array (`TextItem.to_dict()` → `"type": "text"`).
   - Pasted items are not selected (except block instances) and the tool exits
     after one paste.
5. **Move skips Text.** `move_items` moves items with `translate`; `TextItem`
   has only `manip_translate` **[probe: `hasattr(TextItem, 'translate')` is
   False]**, so the Move tool (and Stretch full-item capture) leave text
   behind. The selection manipulator moves text correctly.
6. **Duplicate is two different things.** The window Ctrl+D and the plan
   context menu call `set_mode("duplicate")` (dead mode); the ribbon
   Edit-group button and the scene-level Ctrl+D handler (shadowed by the
   window `QShortcut`, same mechanism as `project_qt_shortcutoverride_delete`)
   call `duplicate_selected()` (instant +10/+10 mm copy, not a Move-like
   placement).
7. **Align pushes undo before it moves** (`_execute_align`), unlike every other
   tool (mutate-then-push, see `Geometry2DMixin._push_undo`).
8. **Pick tolerance from `views()[0]`.** `_find_geometry_at`,
   `_find_endpoint_hit` and `_find_nearest_edge` size their tolerance from
   `views()[0]` — see the vestigial-`views()[0]` memory note; the tolerance may
   come from the wrong view.
9. **Offset pick uses the raw cursor and `items(pos)[0]`** (topmost of the
   filtered types), not the snap/hit-test path other tools use; the pick list
   **omits `RegularPolygonItem` and `TextItem`**, and includes Ellipse/Spline
   for which `make_offset_item` returns `None` (§3).

## 2. Reachability (every user entry point that exists today)

Sources grepped: `main.py` (ribbon builders, window `QShortcut`s),
`model_view.py` (`_TOOL_SHORTCUTS`, `_build_plan_context_menu`),
`model_space.py` (`keyPressEvent`, `contextMenuEvent` /
`_show_entity_context_menu`), `entity_context_menu.py`, `block_editor.py`.
"BE" = Block Editor scratchpad scene (`scene_role="block_editor"`), where 2D
geometry is authored (containment C1). **UNREACHABLE** = nothing a user can do
sets the mode / calls the entry.

Two structural facts govern every row:

- **The geo2d `Modify | <Element>` contextual tab never shows in the Block
  Editor.** `_on_selection_changed_contextual` returns early while
  `_block_ribbon_active`, and it reads `self.scene` (the plan scene) only. So
  that tab is reachable only for loose 2D geometry *in the plan scene* (legacy
  files — C1 forbids authoring it there). Surfacing tools "on the geo2d tab"
  alone would not reach BE geometry.
- **The shared contextual `Edit` group and the geo2d `Constraints` group bind
  `self.scene` (plan), not `_active_scene()`** — unlike the window
  `QShortcut`s and the BE page's draw buttons, which use `_active_scene()`.

| Tool | Ribbon | Keyboard | Context menu | Programmatic only | Verdict |
|---|---|---|---|---|---|
| Copy | contextual `Edit ▸ Copy` (plan scene only) | window **Ctrl+C** → `_active_scene().copy_selected_items()` | plan menu `Copy`; entity menu `Copy` (geo2d except Ellipse/Spline — `_find_entity_at` omits them) | — | reachable (plan + BE) |
| Cut | contextual `Edit ▸ Cut` (plan scene only; tooltip claims Ctrl+X) | **none** (no Ctrl+X binding anywhere) | none | — | plan only; **UNREACHABLE in BE** |
| Paste | contextual `Edit ▸ Paste` → `paste_items()` **TypeError** (missing offset) | window **Ctrl+V** → `set_mode("paste")` (no clipboard guard) | plan menu `Paste` (clipboard-guarded) | `paste_items(offset)` | reachable via Ctrl+V / menu; ribbon button broken |
| Duplicate | contextual `Edit ▸ Duplicate` → `duplicate_selected()` (plan scene only) | window **Ctrl+D** → `set_mode("duplicate")` = **dead mode**; scene Ctrl+D → `duplicate_selected()` shadowed | plan menu `Duplicate` → dead mode | `duplicate_selected()` | plan ribbon only; **effectively UNREACHABLE in BE** |
| Move (tool) | none | **Ctrl+M** (scene `keyPressEvent`; no window shortcut competes) | none | `begin_move_from(base)` (BE import) | reachable (Ctrl+M, undocumented in UI) |
| Move (manipulator) | — | — | — | interior drag of the selection frame | reachable (parallel path, §4) |
| Rotate (legacy `rotate`) | none | none | none | `set_mode("rotate")` | **UNREACHABLE** |
| Rotate (manipulator) | — | — | — | rotate knob **removed 2026-09-23** (`test_no_rotate_knob.py`); `manip_rotate` kept "for the future Rotate transform" | **UNREACHABLE** (no rotate of any kind today) |
| Scale (legacy `scale`) | none | none | none | — (and no commit path, §1.1-2) | **UNREACHABLE + dead** |
| Mirror | none | none | none | — (and empty-selection trap, §1.1-3) | **UNREACHABLE + dead** |
| Offset | none | none | none | `set_mode("offset")` (self re-arm only) | **UNREACHABLE** |
| Array (general) | none — `MainWindow._open_array_dialog` has **no caller** | none | none | `array_items(params)` | **UNREACHABLE** |
| Gridline Array / Offset | none | none | plan + entity menu on one selected gridline | `_start_gridline_replicate` | reachable (gridlines only) |
| Trim | none | none | none | — | **UNREACHABLE** |
| Extend | none | none | none | — | **UNREACHABLE** |
| Break / Break-at-point | none | none | none | — | **UNREACHABLE** |
| Fillet / Chamfer | none | none | none | — | **UNREACHABLE** |
| Stretch | none | none | none | — | **UNREACHABLE** |
| Merge points | none | none | none | — | **UNREACHABLE** |
| Join / Explode | none | none | none | methods (tests call `explode_selected_items`) | **UNREACHABLE** |
| Hatch | not a tool — fill is a property: entity/plan menu `Fill ▸ Hatch`, geo2d Graphic Override group | — | — | — | reachable (as fill property) |
| Constraint Concentric / Dimensional | geo2d tab `Constraints` group (plan scene only, `self.scene`) | none | none | — | plan only; **UNREACHABLE in BE**; Dimensional raises (§1.1-1) |
| Align | none | window **Shift+A** (`_active_scene()`) | none | — | reachable |

**Counts:** 23 rows reviewed. **UNREACHABLE everywhere: 13** (Rotate legacy, Rotate manip, Scale,
Mirror, Offset, Array, Trim, Extend, Break, Fillet/Chamfer, Stretch, Merge,
Join/Explode). **UNREACHABLE in the Block Editor specifically: 16** (the 13 +
Cut, Duplicate, Constraints).

## 3. Primitive × tool coverage matrix

Primitive classes (grepped, `geometry_2d.py` + `text_item.py`; the nine 2D
primitives of `2d-geometry.md` plus the `ReferenceLineItem` subclass):
`LineItem`, `ReferenceLineItem(LineItem)`, `PolylineItem` (open / closed),
`RectangleItem`, `CircleItem`, `ArcItem`, `RegularPolygonItem`, `EllipseItem`,
`SplineItem`, `TextItem`.

Per-item protocol available on **every** 2D primitive: `to_dict`/`from_dict`,
`translate` (**not** `TextItem` — it has `manip_translate`), `manip_rotate`
(Y-up CCW+, internally `rotate_point(…, -angle)`), `grip_points`/`apply_grip`,
`manip_handles`. No primitive has an `offset`, `mirror` or `scale` method;
`manip_scale` exists on `TextItem` only.

Legend: **S** supported · **P** partial · **M** missing (silently skipped
unless noted) · **X** suspect (runs, wrong result) · **C** crashes ·
*n/a* not meaningful. Code path in brackets.

| Tool → / Primitive ↓ | Line | RefLine | Polyline open | Polyline closed | Rect | Circle | Arc | Polygon | Ellipse | Spline | Text |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Move tool** [`move_items` → `translate`] | S | S | S | S | S | S | S | S | S | S | **M** (no `translate`) |
| **Copy/Paste** [`to_dict` → `paste_items` type branch + `translate`] | S | S | S | S | S | S | **P** commits, but **no ghost** (`"draw_arc"` key) | S | S | S | **M** (no `"text"` branch) |
| **Duplicate** [`duplicate_selected` → `paste_items(+10,+10)`] | S | S | S | S | S | S | S | S | S | S | **M** |
| **Rotate legacy** [`_apply_rotate` isinstance chain] | **X** sign (visual CW for Y-up CCW angle) [probe] | **X** (via LineItem branch) | **X** sign | **X** sign | **P/X** converts to Polyline (loses rect-ness; rect has `set_angle`/`manip_rotate`) | **X** sign (centre) | **X** centre CW + `_start_deg += a` CCW → inconsistent [probe] | **M** | **M** | **M** | **M** |
| **Rotate protocol** [`manip_rotate`, no UI] | S [probe] | S | S | S | S (`set_angle`) | S | S [probe] | S | S | S | S |
| **Offset** [`_press_offset` pick + `tool_geometry.make_offset_item`] | S | **X** result is a plain `LineItem` [probe] | **P** side from 1st segment only; distance = min over *infinite* segment lines | **X** first/last vertex not mitered — seam edge not offset [probe: square +10 → (0,10)…(0,−110)] | **C** axis-aligned (pick `_highlight_item` NameError) / S rotated | **C** pick NameError; **X** radius pen-inflated (`boundingRect()/2`: 50+10 → 63) [probe] | S | **M** not pickable, no branch | **M** pickable, `make_offset_item`→None, distance 0 → silent no-op [probe] | **M** same as Ellipse | *n/a* |
| **Array linear** [`array_items` → `paste_items` offsets] | S | S | S | S | S | S | S | S | S | S | **M** |
| **Array polar** [`array_items` dict-key rewrite: `x/y`, `pt1/pt2`, `cx/cy`, `points`] | S geometry, **X** sense (visual CW) [probe] | S/X sense | S/X | S/X | **X** rotates only the `x,y` top-left corner, `angle` untouched [probe] | S/X sense | **X** centre moves, `start_deg` untouched [probe] | **M** `center` key not rotated → all copies stacked on the original [probe] | **P** centre rotated, `rotation` untouched | **M** `control_points` not rotated → stacked [probe] | **M** |
| **Trim (target)** [`_handle_trim_click` branches] | S (nearer endpoint → hit) | P (LineItem branch in place) | **M** | **M** | **M** (+**C** as cutting edge) | **X** Y-down `atan2` vs Y-up arc angles (code-read) (+**C** as cutting edge) | **X** keeps the clicked piece; intersections computed on the Y-reflected arc [probe] | **M** | **M** | **M** | *n/a* |
| **Scale legacy** (dead) [`_apply_scale`] | S | S | S | S | S | S | S | M | M | M | M |
| **Mirror** (dead) [`_apply_mirror`] | S | **X** → plain `LineItem` in `_draw_lines` | S (fill dropped) | **X** closed flag + fill dropped (rebuilt without `close()`) | S | S | **X** keeps `start_deg`, negates span → reflects across the *horizontal*, not the axis [probe: x=0 axis gives Q4 instead of Q2] | **M** | **M** | **M** | **M** |

Adjacent (not in the target set, recorded because they share the
angle-convention defect): **Break-at-point** on an Arc at a visual 45° is a
silent no-op (`atan2` Y-down → point "outside") [probe]; **Break** on a Circle
between visual 0° and 90° yields a 90° arc in the wrong quadrant (start 270)
[probe]; **Fillet** arc endpoints miss the tangent points (Y-down
`atan2` start/span fed to a Y-up `ArcItem`) [probe: ends (10,−20),(0,−10) vs
tangents (10,0),(0,−10)]; `geometry_intersect.line_arc_intersections` and the
`compute_extend_intersections` arc branch use the same Y-down `atan2`, so every
line×arc intersection is computed against the Y-reflected arc.

**Cell counts** (target rows Move, Copy/Paste, Duplicate, Rotate-legacy,
Offset, Array-linear, Array-polar, Trim × 11 columns = 88 cells; 2 *n/a*
→ 86 scored; a cell tagged P/X counts as X; re-derived row by row):
**MISSING 20**, **SUSPECT 18** (of which 5 are "sense-only" — the polar array's
visual-CW rotation on Line/RefLine/Polyline×2/Circle), **CRASH 2** (Offset pick
on axis-aligned Rect and Circle; Trim additionally crashes when a Rect/Circle is
picked as the *cutting edge*), **PARTIAL 4**, SUPPORTED 42.

### 3.1 isinstance-dispatch ordering hazards

- `ReferenceLineItem` subclasses `LineItem`. Every `isinstance(item, LineItem)`
  branch that **creates** a new item (`make_offset_item`, `_apply_mirror`,
  `_break_item`, `_break_at_point`, `join_selected_items`) emits a plain
  `LineItem` into `_draw_lines`, and the removal half only checks
  `_draw_lines` — a broken/joined reference line is **left behind in
  `_reference_lines`** after `removeItem`. `paste_items` gets it right (the
  `"reference_line"` type key, not isinstance). Per
  `project_subclass_isinstance_dispatch_ordering`, a ReferenceLine branch must
  precede LineItem wherever the result type matters.
- `_press_offset_side` / the Enter-commit twin re-dispatch the *new* item by
  isinstance to pick the per-type list (a hand-copied chain in two places);
  neither lists `RegularPolygonItem`/`TextItem`/`ReferenceLineItem`.
- `_family_key_for` (ribbon) and `_find_entity_at` (context menu) enumerate
  primitives independently; `_find_entity_at` omits Ellipse/Spline.

## 4. Duplicate / parallel implementations

Per `feedback_parallel_system_arbitration_smell`, each pair below is an
arbitration risk; which one survives is a grill question (§8), not decided here.

| # | Concern | Implementation A | Implementation B | Divergence |
|---|---|---|---|---|
| P1 | Rotate | legacy `rotate` mode → `SceneTools._apply_rotate` (isinstance chain, `rotate_point(+a)`, rect→polyline, 5 types) | per-item `manip_rotate(angle, pivot)` on all 10 primitives (Y-up CCW+, rect keeps `set_angle`); UI (knob) removed 2026-09-23 | opposite rotation sense; A drops 5 primitive types; A destroys rect identity |
| P2 | Scale | legacy `scale` mode → `_apply_scale` (dead commit) | manipulator resize via `manip_handles` / `manip_scale` (Text) | A unreachable & dead |
| P3 | Offset | general `offset`/`offset_side` modes + `tool_geometry.make_offset_item` (no HUD, no ghost-by-HUD) | `gridline_offset` mode + `GridlineItem.offset_copy` (ghost + `distance` HUD schema + Enter/Esc) | B is the modern pattern (HUD, ghost list, one commit helper); A predates it |
| P4 | Array | `ArrayDialog` + `array_items` (dialog, linear + polar via clipboard round-trip) — unreachable | `gridline_array` mode + `GridlineItem.array_copies` (on-canvas ghost + `spacing_count` HUD) | same as P3 |
| P5 | Closed-shape offset math | `tool_geometry.offset_polyline_pts` (open-chain miter; used for closed polylines too → seam bug) | `Model_Space._inset_polygon` (closed, wrap-around miter, winding-aware; used by room detection) | B already solves the closed case A gets wrong |
| P6 | Duplicate | `set_mode("duplicate")` (dead) | `duplicate_selected()` (+10/+10 instant) | two meanings behind one label / shortcut |
| P7 | Copy serialisation | `copy_selected_items` (nodes carry elevation/ceiling/level) | `duplicate_selected` and `array_items._serialise` (hand-copied node dict **without** elevation/ceiling/level keys; array's also drops pipes to unselected nodes) | three hand-copied serialisers; paste then restores node z differently per source |
| P8 | Move | `move` tool (`move_items`: `translate` only) | manipulator interior drag (`manip_translate` first, then `translate`) | Text moves only via B |
| P9 | Numeric input | `numericInputRequested` → `MainWindow._on_numeric_input_requested` → `complete_numeric_input` (never emitted) | Dynamic Input HUD (`_SCHEMA_FOR_MODE` / `_APPLIER_FOR_MODE`) | A is a dead second channel |
| P10 | Offset commit | `_press_offset_side` isinstance→list chain | identical hand copy in `keyPressEvent` Enter branch | two copies to keep in sync |
| P11 | Entity pick | `SceneTools._find_geometry_at` (shape-contains + grip distance) | `_press_offset` (`items(pos)` + isinstance filter) and `_find_entity_at` (context menu) | three pick rules, three type lists |
| P12 | Geometry collector | `SceneTools._all_geometry_items` (per-type lists, text last) | the "2D Geometry" category collectors (`2d-geometry.md` §-ref) | see `project_geo2d_parallel_list_collectors` |

## 5. Modification schema (per target tool)

For each tool: **as-built** step sequence and HUD, then the **as-proposed,
pending a human gate** shape (derived from the user brief and from the
existing gridline-replicate / Move patterns — *not* decisions), then the open
questions. Available HUD schemas today (`dynamic_input.SCHEMAS`):
`displacement` (dX, dY; needs anchor), `distance` (Distance), `spacing_count`
(Spacing, Count), `rotation` (Angle — an **absolute** heading, ±180),
`line` (Length, Angle), `track`, `manip_move`, `manip_resize`.

### 5.1 Copy
- **As-built:** one action; serialises the selection to the *system* clipboard
  as JSON; no base point is stored (paste offsets are relative to the copied
  items' own coordinates).
- **As-proposed, pending a human gate:** unchanged action; optionally record a
  base point (Revit/AutoCAD "copy with base point").
- **Open:** Q-C1 system clipboard vs an app-internal clipboard (the JSON on the
  OS clipboard clobbers the user's text clipboard, and `array_items` /
  `duplicate_selected` temporarily overwrite it); Q-C2 is Text in scope
  (needs a `"text"` paste branch).

### 5.2 Cut
- **As-built:** ribbon-only `copy + delete` on the plan scene; no shortcut.
- **As-proposed, pending a human gate:** Ctrl+X window shortcut routed through
  `_active_scene()`; one undo step.
- **Open:** Q-X1 should Cut → Paste preserve identity (ids, constraints,
  display overrides) or always create new items.

### 5.3 Paste
- **As-built:** `paste` mode, **two clicks** (base, destination); ghost only
  after click 1; offset = click2 − click1 applied to the copied coordinates;
  exits to Select after one paste; no HUD (excluded by F2); no handle snap
  (S2 session is Move-only); pasted items not selected.
- **As-proposed, pending a human gate (user brief):** ghost follows the cursor
  immediately on entry, **one click commits**. That needs an implicit base
  point — candidates: the copied selection's bbox centre, its first grip, or a
  base point captured at Copy time (§5.1).
- **Open:** Q-P1 which implicit base point; Q-P2 does paste stay armed for
  repeated pastes (continuous) or return to Select with the pasted items
  selected (the `_SINGLE_PLACEMENT_MODES` convention); Q-P3 HUD (dX/dY from
  the base?) and handle-snap of the ghost; Q-P4 behaviour with an empty /
  foreign clipboard (today a crash).

### 5.4 Duplicate
- **As-built:** two meanings (§1.1-6): dead `duplicate` mode vs instant
  `duplicate_selected()` at +10/+10 mm.
- **As-proposed, pending a human gate (user brief):** "like Move but keeps the
  original" — i.e. the Move state machine (base → destination, S2 handle snap,
  `displacement` HUD) committing a copy instead of translating.
- **Open:** Q-D1 base-point step or ride-from-grab like the manipulator;
  Q-D2 single copy vs repeat-until-Esc (AutoCAD COPY multiple); Q-D3 retire
  `duplicate_selected()` and its +10/+10 offset.

### 5.5 Move
- **As-built:** Ctrl+M → base → destination; S2 handles-only destination snap;
  `displacement` HUD (dX/dY) → `_apply_move_displacement`; skips Text.
- **As-proposed, pending a human gate:** surface as a ribbon button; fix Text
  (`manip_translate` fallback).
- **Open:** Q-M1 is the Move *tool* still wanted alongside manipulator drag,
  or does the ribbon button just start the tool (as `begin_move_from` does).

### 5.6 Rotate
- **As-built (legacy, unreachable):** pivot click → second click sets the
  **absolute** heading of pivot→cursor as the rotation amount; visual-CW sense
  bug; no ghost; 5 primitive types skipped; rect → polyline.
- **As-proposed, pending a human gate (user brief: "pick base point"):**
  pivot click → (optional reference ray click) → live ghost rotating with the
  cursor → click / typed angle commits via the per-item `manip_rotate`
  protocol (P1-B).
- **HUD:** would need a **relative** angle field. The existing `rotation`
  schema is an *absolute* orientation (polygon/block rotate step) — reusing it
  for a relative rotate would change its meaning. **Open (proposed new schema or
  reuse).**
- **Open:** Q-R1 reference-ray step (AutoCAD ROTATE "Reference") or angle from
  +X; Q-R2 copy option (rotate-copy); Q-R3 retire `_apply_rotate` in favour of
  `manip_rotate` (P1) — coupled tests `test_rect_rotation_consumers.py`
  (pins rect→polyline and the `rotate_point(+45)` sense) would need rewriting,
  a VC5 retirement.

### 5.7 Offset
- **As-built (unreachable):** click entity → cursor distance/side → click or
  Enter commits a copy; re-arms; no HUD; no Esc distinction.
- **As-proposed, pending a human gate:** gridline-replicate pattern (P3-B):
  pick → ghost → `distance` HUD (Tab/typed) → Enter/click commits; closed
  shapes offset as closed shapes (brief: polygons, rects, circles, ellipses).
- **Per-primitive math needed (as-proposed):** Line (exists), open Polyline
  (exists; side/distance defects), closed Polyline (wrap-around miter — reuse
  `_inset_polygon`, P5), Rect (exists, incl. rotated), Circle (exists; drop the
  pen-inflated radius), Arc (exists), **RegularPolygon** (missing — a mitered
  offset of a regular polygon is still regular: apothem += d, i.e. stored
  `radius_mm += d` when circumscribed (radius = apothem) or `+= d / cos(π/n)`
  when inscribed (radius = circumradius); result type still a question only if
  round joins are chosen, Q-O5), **Ellipse** (missing — the true offset of an ellipse is **not an
  ellipse**; needs a decision: approximate as Spline/Polyline, or scale rx/ry
  by ±d as an approximation), **Spline** (missing — true offset is not a
  spline of the same degree).
- **Open:** Q-O1 ellipse/spline offset result type; Q-O2 polygon offset result
  type; Q-O3 "through point" vs fixed distance; Q-O4 sticky last distance;
  Q-O5 corner join style for polylines (miter vs round/arc like AutoCAD);
  Q-O6 ReferenceLine offset stays a ReferenceLine.

### 5.8 Array
- **As-built (unreachable):** modal `ArrayDialog`; linear (rows, cols, x/y
  spacing — `DimensionEdit`, mm) or polar (centre X/Y as **raw scene Y-down**
  spin boxes via `display_to_scene`, count, total angle, "rotate items" —
  **ignored by `array_items`**, though the dialog preview honours it).
- **As-proposed, pending a human gate:** on-canvas pattern like `gridline_array`
  (P4-B): pick direction/spacing with the cursor, `spacing_count` HUD; polar
  via a picked centre.
- **Open:** Q-A1 keep the dialog, go on-canvas, or both; Q-A2 polar "rotate
  items" semantics (it currently always rotates point-defined geometry and never
  rotates parametric orientation — neither matches the checkbox); Q-A3 polar
  sense (Y-up CCW+ per the rotation convention) and centre-Y display sign;
  Q-A4 associative array (editable later) vs one-shot copies.

### 5.9 Trim (possible)
- **As-built (unreachable):** cutting-edge pick → target-piece click; Line /
  Circle / Arc targets only; line×line, line×circle, line×arc intersections
  only (no circle×circle, arc×arc, or anything with ellipse/spline/polygon);
  arc/circle branches mix Y-down `atan2` with Y-up arc angles (keeps the
  clicked piece on an arc [probe]).
- **As-proposed, pending a human gate:** fix the angle convention first (one
  helper, `arc_math` home), then decide scope.
- **Open:** Q-T1 in this milestone or not; Q-T2 multi-edge trim (select all
  cutting edges, AutoCAD TRIM) vs single edge; Q-T3 polyline/rect targets
  (split into polyline pieces?).

## 6. Divergences ledger (as-built vs the brief / conventions)

| ID | Divergence | Evidence | Severity |
|---|---|---|---|
| DV1 | 13 tools unreachable everywhere; 16 unreachable in the Block Editor | §2 | blocks the milestone |
| DV2 | geo2d contextual tab cannot appear in the Block Editor; shared Edit/Constraints groups bind the plan scene | §2 structural facts | blocks "surface via geo2d tab" |
| DV3 | Missing Qt imports → NameError on circle / axis-aligned rect picks, merge, dimensional constraint | §1.1-1 [probe] | crash |
| DV4 | Paste: empty-clipboard TypeError; ribbon Paste TypeError; two-click paste vs the brief's ghost-then-one-click; no arc/gridline/block ghost; no text | §1.1-4 [probe] | crash + brief divergence |
| DV5 | Duplicate: dead mode behind Ctrl+D + context menu; ribbon = +10/+10 instant | §1.1-6 [probe] | brief divergence |
| DV6 | Legacy rotate: visual-CW sense for a Y-up CCW angle, arc start inconsistent, 5 types skipped, rect→polyline, absolute-heading angle | §3 [probe] | wrong result |
| DV7 | Rotation-convention violations around arcs: mirror, trim, break, break-at-point, fillet, line×arc intersection, extend-to-arc all use Y-down `atan2` against Y-up `ArcItem` angles | §3 adjacent [probe] | wrong result |
| DV8 | Offset: no polygon/ellipse/spline; closed-polyline seam; circle radius pen-inflated (pinned by `test_scene_tools.py::test_circle_offset_*`, which assert the `boundingRect()/2` radius — a test enshrining the defect); ReferenceLine → Line; false "Tab" instruction | §3, §1.1-2 [probe] | wrong result |
| DV9 | Array: dialog unreachable; polar stacks polygons/splines, mis-rotates rects/arcs, ignores `rotate_items`, CW sense, centre Y in raw scene coords | §3, §5.8 [probe] | wrong result |
| DV10 | Mirror: entry clears the selection → never produces anything; arc reflect wrong; closed polylines open | §1.1-3, §3 [probe] | dead + wrong |
| DV11 | Scale: no commit path | §1.1-2 | dead |
| DV12 | Move tool skips Text; Paste/Duplicate/Array drop Text | §1.1-4/5 [probe] | missing |
| DV13 | `numericInputRequested` never emitted; `complete_numeric_input` dead | §1.1-2 | dead code |
| DV14 | ReferenceLine subclass dispatch: new items are plain Lines; originals left in `_reference_lines` after break/join | §3.1 | wrong result |
| DV15 | Align pushes undo before mutating | §1.1-7 | undo drift |
| DV16 | All modify modes are enterable in the plan scene (none is in `_LOOSE_AUTHORING_MODES`). C1 forbids loose-geometry *authoring* there; modify tools on block instances / walls / pipes are a separate question | [probe: move/rotate/offset/trim/mirror/paste accepted with `scene_role="plan"`] | open question |

## Design Decisions (ratified — 2026-09-25 grill, FP4 orphan-gate + Phase 2)

Ratified by the user at the 2026-09-25 `/grill-me` (Q1–Q16). These are the
**as-intended** contract; §1–§6 remain the as-built record they correct.
Constraints owned elsewhere (linked, not restated): rotation sense →
`project_rotation_conventions_yup_vs_qt`; length display/parse →
`units-and-formatting.md`; HUD engine → `dynamic_input.SCHEMAS` +
`model-space-architecture.md`; handles-only move snap → `snapping-engine.md`;
ribbon page / contextual model → `ribbon-bar.md` §3.8; C1 →
`model-space-containment-contract.md`; per-item transform protocol →
`selection-manipulator.md`.

- **D1 Surface.** The milestone surface is the **Block Editor contextual page**:
  two always-visible groups after "2D Geometry" — **Edit** (Copy · Cut · Paste ·
  Duplicate · Delete; the existing shared Edit group, repaired) and **Modify**
  (Move · Rotate · Offset · Array). Buttons disabled with no selection (Paste:
  disabled with an empty/foreign clipboard). One shared builder, every callback
  routed through the **active scene** (never hard-wired to the plan). The plan
  geo2d tab is moot under C1 (D13); architecture tabs + plan block instances
  reuse the builder in milestone 2.
- **D2 Shortcuts.** Window-level, active-scene-routed, not firing while a text
  field / the HUD has focus: **Shift+C** Copy · **Shift+X** Cut · **Shift+V**
  Paste · **Shift+D** Duplicate · **Shift+M** Move · **Shift+R** Rotate ·
  **Shift+O** Offset · **Shift+A** Array. Ctrl+C / Ctrl+X (new) / Ctrl+V /
  Ctrl+D (fixed → real Duplicate) stay as aliases. **Ctrl+M retired.** Align
  moves **Shift+A → Shift+L**. Tooltips show the Shift binding.
- **D3 Select-first.** Every tool except Offset requires a selection; with none
  → status "Select items first", no mode change. After commit → Select with the
  affected items selected (moved/rotated: the originals; paste/duplicate: the
  new items; array: the original).
- **D4 Copy / Cut.** Copy is modal: "Pick base point" (normal SNAP+ALIGN) →
  selection + base point to the clipboard → Select, selection intact; Esc =
  nothing copied. Cut = the same pick, then delete, **one undo step**.
- **D5 Paste.** Ghost's base point sits on the cursor immediately; cursor snaps
  normally; **one click commits one paste** → Select with the pasted items
  selected. HUD **dX · dY** relative to the copied base point. Esc cancels.
  Empty/foreign clipboard → status "Nothing to paste", no crash, no mode change.
- **D6 Duplicate.** Move's state machine (base → destination, handles-only
  destination snap, dX/dY HUD) committing a **copy**; the **original remains a
  snap target**; single copy → Select with the copy selected; one undo step. The
  +10/+10 instant `duplicate_selected` behaviour is retired (ribbon, Ctrl+D,
  context menu all start this mode).
- **D7 Move.** Current flow kept (base → destination, handles-only snap, dX/dY
  HUD). **Text now moves** (DV12).
- **D8 Rotate.** Revit-style: pivot (SNAP+ALIGN) → start ray (click; typed input
  defaults the start ray to +X) → live ghost sweeps → end-ray click commits (end
  point snaps). HUD after the pivot: **relative Angle, CCW+ (Y-up)** — typing
  `90 Enter` rotates 90° CCW. Commit through per-item `manip_rotate` (every
  primitive; rectangles stay rectangles). Legacy `_apply_rotate` retired (P1).
  During Rotate: no selection frame, no legacy dashed line — only the ghost, a
  thin pivot→cursor ray and an angle readout. The selection frame elsewhere is
  **unchanged** (the brief's "remove the green bounding box and rotate bar" =
  during Rotate only; the knob is already gone).
- **D9 Offset.** (1) source = the single selected offsettable item, else "Pick
  object to offset"; (2) cursor sets side (inside/outside for closed shapes) +
  distance, ghost follows; (3) HUD **Distance** locks the distance, cursor still
  picks the side; (4) click/Enter commits a new item (source kept), one undo;
  (5) stays armed with the **last distance sticky**; Esc → Select. Too-large
  inward offset → no ghost + status "Offset too large", nothing created. Result
  inherits the source's style (colour, lineweight, fill — 2D primitives carry no linetype and are level-less, C3; corrected 2026-09-26). Per primitive
  (**mitered corners** throughout): Line/RefLine → parallel of the **same type**;
  open polyline → mitered parallel polyline; closed polyline → closed, mitered at
  **every** vertex incl. the seam; Rect (incl. rotated) → rect ±d per side, same
  angle; Circle → concentric r±d (**geometric r, not pen-inflated**); Arc →
  concentric, same angles, r±d; RegularPolygon → regular polygon, same sides +
  rotation, apothem ±d; **Ellipse → ellipse rx±d, ry±d**, same centre +
  rotation; Spline → spline approximating the offset curve; Text → not
  offsettable.
- **D10 Array.** On-canvas **linear** only: selection → Shift+A → base point →
  cursor sets direction + spacing, live ghost of all copies → HUD **Spacing ·
  Count** (Count = **total incl. the original**) → click/Enter commits
  **independent copies**, one undo → Select with the original selected. Not
  associative. `ArrayDialog` retired. Polar and rows×cols are follow-ups.
- **D11 Ghost.** One style for Move, Duplicate, Paste, Rotate, Offset, Array
  (and the gridline offset/array ghosts): HALO preselection glow + a **1 px
  solid accent line tracing the true drawn geometry** (not `shape()`). Original
  is **dimmed to 35 %** during every transform mode (mockup gate B, 2026-09-25;
  HALO defaults 4 px / α128 / glow 8 px). No copy cap.
- **D12 Icons.** 9 icons (Copy, Cut, Paste, Duplicate, Delete, Move, Rotate,
  Offset, Array) in the 40-unit 2D-geo family (`icon-style-guide.md` §5.1),
  27 px small buttons; grammar **ink = source, accent = result/motion**; reuse
  existing filenames + new `offset_icon.svg`; two-token + both-theme guards.
  Mockup approved 2026-09-25 as drawn (see Implementation design).
- **D13 Containment.** Paste refuses loose 2D geometry / text into a plan scene
  ("2D geometry can only be pasted in the Block Editor") and plan entities
  (walls, pipes, block instances…) into the Block Editor. No cross-scene 2D paste.
- **D14 Out of this milestone.** Trim (refine the Trim design follow-up with
  §3/§5.9); the arc Y-down/Y-up convention fix (DV7 — own bug task); Scale,
  Mirror, Extend, Break, Fillet, Chamfer, Stretch, Merge, Join, Explode stay
  unreachable (one surfacing follow-up) — but the DV3 missing-import crash is
  fixed now; polar / rows×cols array; plan block instances + architecture tabs
  (milestone 2).
- **D15 Dead plumbing.** `numericInputRequested` / `complete_numeric_input`
  deleted (the HUD replaces it).

## Acceptance Criteria (ratified 2026-09-25)

- [ ] The Block Editor page shows Edit + Modify groups (D1); every button and
      Shift/Ctrl shortcut (D2) acts on the Block Editor scene when it is active.
- [ ] Shift+letter does not fire tools while typing in a field or the HUD.
- [ ] Align is on Shift+L; Shift+A starts Array; Ctrl+M no longer exists.
- [ ] Each tool behaves per D3–D10, including Esc cancel (no scene change, no
      undo entry) and exactly one undo step per commit.
- [ ] Per-primitive end-to-end guard for every tool × in-scope primitive (Line,
      RefLine, open + closed Polyline, Rect plain + rotated, Circle, Arc,
      Polygon, Ellipse, Spline, Text where applicable): drives the real mode
      (press/move/HUD), asserts resulting geometry (coords, radii, angles, type
      preserved, style inherited) and undo restore.
- [ ] Dedicated guards: rotation sense (+90 CCW moves a +X point to scene −Y);
      closed-polyline offset seam; circle offset radius not pen-inflated;
      paste containment refusal; empty-clipboard message; Shift-key routing to
      the active scene; Block Editor buttons target the editor scene.
- [ ] No tool raises on any in-scope primitive (DV3/DV4).
- [ ] Ghost (D11) and icons (D12) match the approved mockups.
- [ ] Tooltips on every new/changed button (`feedback_always_include_tooltips`).

## Implementation design (approved 2026-09-25 brainstorm — Phase 3)

Status: design approved section-by-section; **built 2026-09-26** on `feat/scene-tools-2d` (see "Build deltas" below). Mockup
gates passed 2026-09-25: ghost = **B** (original dimmed to 35 %, HALO defaults
4 px / α128 / glow 8 px + 1 px solid accent trace, α255); icons = the 9 in
`.superpowers/brainstorm/*/content/modify-icons.html` approved as drawn.

### I1 Units (approach A — behaviour home)

- **`firepro3d/modify_tools_controller.py` — `ModifyToolsController(scene)`**:
  plain object, **behaviour home, owns NO state** (`model-space-architecture.md`
  §5.3). Holds the press / move / preview / applier / commit bodies for
  `copy_base`, `paste`, `duplicate`, `move`, `rotate`, `offset`, `offset_side`,
  `array`, plus `start(tool)` (select-first gate, D3) and idempotent
  `clear(new_mode)`. Transient state (base point, pivot, start ray, ghost base
  paths, sticky offset distance, dimmed-item list) stays **scene-side** where
  `PlacementInputCoordinator` reads it. Scene dispatch rows
  (`_PRESS_DISPATCH` / `_MOVE_DISPATCH` / `_PREVIEW_DISPATCH` /
  `_SCHEMA_FOR_MODE` / `_APPLIER_FOR_MODE`) point at thin scene shells that
  forward to the controller (the slice-10/11 idiom). The as-built
  move/paste/offset/rotate handlers **relocate** out of `model_space.py`.
- **Ribbon builders** — `build_edit_group(page, scene_getter)` and
  `build_modify_group(page, scene_getter)` (one shared implementation; the
  existing `_build_contextual_edit_group` becomes a caller). Every callback
  resolves the scene through `scene_getter()` (= `MainWindow._active_scene`).
  Modal buttons (Copy, Paste, Duplicate, Move, Rotate, Offset, Array) register in
  `_block_mode_buttons` on the Block Editor page so `_sync_mode_buttons`
  checks/clears them; Cut and Delete are plain buttons. Enable-state refreshes on
  the editor scene's `selectionChanged` and on clipboard change.
- **Window shortcuts** — one table `{key: tool}` in `main.py` registered as
  window `QShortcut`s (D2). The handler **refuses** when the focus widget is a
  `QLineEdit` / `QTextEdit` / `QPlainTextEdit` / the HUD, or when the current
  central tab is a Paper tab (so a hidden plan scene is never driven). Align
  re-bound to Shift+L; Ctrl+M branch deleted; Ctrl+X added; Ctrl+D fixed.
- **Offset math** — `tool_geometry.offset_item(item, signed_d) -> item | None`,
  one branch per primitive per D9 (subclass-before-base: `ReferenceLineItem`
  before `LineItem`). The closed-polyline case uses `Model_Space._inset_polygon`
  **promoted into `tool_geometry`** (one implementation, two callers). `None` =
  degenerate (too-large inward offset). Style copy (colour, linetype, fill,
  level) is part of `offset_item`.
- **Ghost** — `firepro3d/transform_ghost.py`: build base paths with
  `halo.halo_scene_path(item)`; per frame apply a `QTransform` (translate, or
  rotate about the pivot with the `manip_rotate` sign); paint
  `halo.paint_halo_path(...)` + a 1 px cosmetic solid accent trace. Originals
  are dimmed by setting item opacity to `TRANSFORM_GHOST_DIM_OPACITY = 0.35`
  (`constants.py`) on entry to a transform mode and restored in
  `clear()` / Esc. `Model_View.drawForeground` block 8 calls the helper; the
  gridline replicate ghost moves onto it. Nodes keep the cross marker.
- **Clipboard payload** — system clipboard JSON
  `{"fp3d_clipboard": 1, "base": [x, y], "scene_role": "<role>", "items": [...]}`.
  Missing/other version key ⇒ foreign ⇒ "Nothing to paste". Containment (D13)
  checked from `scene_role` + item `type`s before the mode is entered.
- **`_add_from_dict(d)`** on the scene: one per-type deserialise-and-register
  helper used by Paste, Duplicate, Array and `_restore_network` (GENERALIZE —
  replaces the `paste_items` if/elif chain).

### I2 Per-tool data flow

Shared: entry via `ModifyToolsController.start(tool)`; commit = one
`push_undo_state()` → `set_mode(None)` → D3 post-commit selection; Esc = the
generic `set_mode(None)` → `clear()` (drop ghost, restore opacity).

| Tool | Modes / steps | HUD | Commit |
|---|---|---|---|
| Copy / Cut | `copy_base`: 1 snapped base click | — | write payload with base; Cut = `_bulk_delete` in the **same** undo step |
| Paste | `paste`: validate payload (else refuse, no mode) → ghost from temporary `from_dict` items anchored base→cursor → 1 click | `displacement` (dX/dY from base) | `_add_from_dict` each + `translate(cursor − base)` |
| Duplicate | `duplicate`: Move machine, `keep_original=True`; handle-snap session does **not** exclude the originals | `displacement` | `to_dict` → `_add_from_dict` → `translate` |
| Move | `move` (unchanged) | `displacement` | `move_items` (+ `manip_translate` fallback for Text) |
| Rotate | `rotate`: step 0 pivot → 1 start ray → 2 sweep | new `rotate_by` schema: one ANGLE field, **relative CCW+**, anchored on the pivot, seed 0 | `manip_rotate(Δ, pivot)` per item |
| Offset | `offset` (pick; skipped with one offsettable selected) → `offset_side` (cursor side + distance; ghost = the candidate item) | `distance` (magnitude; side from the cursor) | `offset_item`; `None` ⇒ "Offset too large"; re-arm `offset` with the sticky distance |
| Array | `array`: step 0 base → 1 cursor sets direction + spacing; ghost = N−1 copies | new `array_linear` schema: Spacing + Count (**total**, min 2) | N−1 copies at k·spacing |

The gridline `spacing_count` schema is untouched (its Count = copies, not total).

**Retired (VC5 — coupled tests rewritten/retired in the same slice):**
`duplicate_selected` +10/+10; the dead `"duplicate"` wiring (now real);
`ArrayDialog` + `array_items`; legacy `_press_rotate` / `_move_rotate` /
`_apply_rotate`; `numericInputRequested` + `complete_numeric_input`; the Ctrl+M
key branch. **Fixed en route:** DV3 missing imports in `scene_tools.py`; paste
ghost type keys (moot — ghost built from real temporary items); rotated-rect
double-rotated ghost (moot — `halo_scene_path`).

### I3 Error handling

- Every refusal (no selection, empty/foreign clipboard, containment, offset too
  large, zero spacing / Count < 2) = status-bar message, no mode change, no undo
  entry; HUD refusals use `reject_commit()`.
- A clipboard item that fails `from_dict` is skipped + logged; the remainder
  pastes; the status reports the skipped count.
- Controller steps re-read the selection from the scene; no item reference is
  held across a commit (`project_undo_restore_invalidates_item_refs`).

### I4 Testing

- Per tool × primitive: parametrized end-to-end guards
  `tests/test_modify_tools_<tool>.py` driving the real mode (scene
  press/move + HUD commit), asserting real geometry, undo count = 1 and undo
  restore (VC3), shown RED on revert.
- Dedicated guards: rotation sense; closed-polyline seam; circle offset radius;
  containment refusal; empty clipboard; Shift-key routing (activate the
  `QShortcut` objects directly — `project_qtest_cannot_drive_shortcuts`) incl.
  refusal with a focused line edit; Block Editor buttons drive the editor scene;
  ghost built via `halo_scene_path` + original opacity restored after Esc.
- Icons: `_MODIFY_ICONS` added to the two-token + both-theme guards in
  `tests/test_icon_theming.py`.

### I5 Build order (plan slices; each green before the next)

1. Controller skeleton + dispatch shells; relocate Move (parity slice).
2. Ribbon builders + window shortcuts + Align→Shift+L + icons.
3. Clipboard payload + Copy/Cut base pick + one-click Paste + `_add_from_dict`.
4. Duplicate.
5. Ghost painter + dimmed original.
6. Rotate.
7. Offset (all primitives).
8. Linear Array.
9. Dead-code retirement + import fix.

### Build deltas (as-built 2026-09-26, ratified where noted)

Where the build refined the design above (each reviewed; guards in `tests/test_modify_tools_*.py`, `tests/test_offset_item.py`, `tests/test_transform_ghost.py`):

- **D9 sticky distance (user-ratified 2026-09-25):** a *typed* Distance stays locked for every next pick — the cursor only picks the side; typing `0` releases the lock (schema `offset_distance`, which admits 0); a click-derived distance only pre-fills the HUD. A typed value commits on the side the cursor held when the HUD engaged (the HUD freezes the cursor).
- **D9 spline offset:** `tool_geometry.fit_offset_spline` — adaptive clamped least-squares fit to the true offset curve (≤ 1 % of |d|, extra control points allowed, C0 corner knots split and mitered/trimmed, closed seams mitered); never returns an out-of-tolerance fit (falls back). Live ghost: per-source cached linear fit (C0 + d·C1), zoom-adaptive sampling (≈ 1 px chord). **Known limits:** swallowtail self-intersections are not trimmed; the far-cursor 40-pt case repaints ≈ 30–35 ms (user-accepted; xfail) — both tracked by the "Trim self-intersecting spline offsets" follow-up. Inward closed offsets are refused unless the result lies inside the source.
- **D9 snap:** in `offset_side` the source is excluded from snap targets (through-point snaps to other geometry stay live).
- **D10 Enter:** bare Enter commits at the current aim (no aim → refusal status); no ghost is shown before an aim exists.
- **D5/D13 paste gate:** the Block Editor accepts only the 2D registry types (allow-list); nothing is ever read from a bare-list clipboard; internal round-trips (array, copy-to-level) never touch the OS clipboard; Copy/Cut verify the clipboard write and refuse (Cut deletes nothing) if it did not land.
- **Selection / undo:** Move re-selects its originals; Undo/Redo cancel an active modify tool first (`CANCEL_ON_UNDO_MODES`); New/Open end the active tool before clearing the scene (`scene_io._clear_scene`).
- **Rotate commit** fixed `RectangleItem.manip_rotate` and `TextItem.manip_rotate` (compose about the item's own pivot, then translate — no new persisted state); governed by `selection-manipulator.md` (baked-at-rest rule).
- **Ribbon:** the modal Edit/Modify buttons register in `_block_mode_buttons` (lit while their mode runs; un-toggle cancels). Window shortcut table + Align on Shift+L: see D2.

## Verification Checklist

- [ ] All ratified acceptance criteria met
- [ ] Keep-green includes `tests/test_scene_tools.py`, `test_tool_geometry.py`,
      `test_rect_rotation_consumers.py`, `test_move_paste_ghost.py`,
      `test_move_handle_snap.py`, `test_gridline_array_offset.py`,
      `test_dynamic_input_parity.py` (enumerates schema/applier rows),
      `test_ribbon_contextual.py` (enumerates contextual builders; asserts the
      Edit group has 5 buttons), `test_polyline_closed.py`,
      `test_geo2d_serialization.py`, `test_block_editor_levelless_authoring.py`,
      `test_block_seams.py`, `test_no_rotate_knob.py`
- [ ] Tests that currently pin defects (circle-offset radius, legacy rotate
      sense / rect→polyline, synthetic gridline-ghost dict) are rewritten only
      under a ratified contract change (VC5)

## Existing Code Context

- `firepro3d/modify_tools_controller.py` — `ModifyToolsController`
  (`scene._modify_ctl`, owns no state): Copy/Cut/Paste/Duplicate/Move/Rotate/
  Offset/linear Array press/move/preview/commit + `start` / `clear` (D1–D11).
- `firepro3d/transform_ghost.py` — ghost base paths (`ghost_base_paths`),
  `paint_ghost`, dim/restore of the originals (D11).
- `firepro3d/scene_tools.py` — `SceneTools` (composed `scene._tools`):
  `_apply_scale/_mirror`, join/explode, break, fillet/chamfer commits,
  stretch, trim/extend/merge/constraint click handlers, align, pick helpers,
  `_PadlockItem`. (Array and Rotate moved to `ModifyToolsController`.)
- `firepro3d/tool_geometry.py` — pure math: `extract_edges`, offset
  (`offset_polyline_pts`, `offset_signed_dist`, `inset_polygon`,
  `distance_to_item`, `offset_side_sign`, `offset_item` — D9),
  `compute_fillet/chamfer`, segments / intersections.
- `firepro3d/model_space.py` — mode state machines: `set_mode` teardown,
  `_PRESS_DISPATCH` / `_MOVE_DISPATCH` / `_PREVIEW_DISPATCH`,
  `_SCHEMA_FOR_MODE` / `_APPLIER_FOR_MODE`, the tools' `_press_*` / `_move_*`,
  the modify-tool dispatch shells, `copy_selected_items` / `paste_items` /
  `move_items`, `keyPressEvent` (Enter commits; Ctrl+C/X/V/D are window
  `QShortcut`s, Ctrl+M retired), gridline replicate, `_inset_polygon`.
- `firepro3d/model_view.py` — `_TOOL_SHORTCUTS` (draw tools only), Tab →
  `begin_dynamic_input`, stretch crossing band, plan context menu.
- `main.py` — `_build_contextual_edit_group`, `_build_geo2d_context`,
  `_build_block_editor_context`, window `QShortcut`s (Ctrl+C/V/D, Shift+A).
- `firepro3d/dynamic_input.py` — HUD schemas.
- `firepro3d/geometry_2d.py`, `firepro3d/text_item.py` — per-item protocol.

## Edge Cases & Error Handling (observed)

- Empty / non-JSON clipboard → Paste crashes (DV4).
- Offset distance 0 (Ellipse / Spline / unknown types) → silent no-op.
- Trim with no intersection → status "No intersection found"; circle with <2
  intersections → status; arc trim point outside the span → status.
- Extend from an interior polyline vertex → status.
- Mirror asks "Delete original objects?" via `confirmRequested` *after*
  already pushing the copy's undo step.

## 7. Spec contradictions / ambiguities noticed (VC10 — not fixed here)

- `model-space-architecture.md` (existing-structure bullet) says `Model_Space`
  "mixes in `SceneToolsMixin`" with "no own `__init__`"; the code composes
  `SceneTools(self)` as `scene._tools`, which has an `__init__` (decomposition
  slice B). Stale.
- `SPEC-INDEX.md` routes `scene_tools.py` to both `model-space-architecture.md`
  (structure) and `parametric-constraint-system.md` (constraints / align);
  this draft would be a third owner (behaviour). The index is not updated by
  this review (single-file write) — follow-up: add the row and state the
  ownership split.
- `selection-manipulator.md` / `test_no_rotate_knob.py` reserve `manip_rotate`
  "for the future Rotate transform" — consistent with P1-B, but no spec names
  that transform.
- `ribbon-bar.md` §3.8 describes the geo2d builder as "Placement + Fill +
  Edit" (2026-08-22) in one bullet and "Edit → Constraints → Graphic Override"
  (2026-09-16) a paragraph later; the code matches the latter.
- `main.py` `_MODE_INSTRUCTIONS` and `Model_Space.set_mode` `_initial_steps`
  carry duplicate, diverging instruction strings for the same modes (e.g.
  offset "Tab for exact distance", which is false today).

## 8. Open questions for grill

1. **Surface / host.** The geo2d `Modify | <Element>` tab never appears in the
   Block Editor. Do the milestone tools go on the Block Editor contextual page
   (always visible there), on a selection-driven sub-tab inside the editor, or
   should the geo2d tab coexist with the Block Editor page? Must the shared
   Edit group switch from `self.scene` to `_active_scene()`?
2. **Plan-scene scope.** Should modify tools (Move/Rotate/Offset/Array/Trim) be
   allowed in the plan scene at all (block instances, walls, pipes, legacy
   loose geometry), or be gated like `_LOOSE_AUTHORING_MODES`?
3. **Paste model.** One-click paste with the ghost on the cursor needs an
   implicit base point — bbox centre, first grip, or a base point captured at
   Copy? Stay armed for repeat pastes, or return to Select with the paste
   selected? Internal clipboard vs the OS clipboard?
4. **Duplicate model.** The Move state machine committing a copy (base →
   destination, handle snap, dX/dY HUD)? Single or repeat-until-Esc? Retire
   `duplicate_selected()` and its +10/+10 behaviour?
5. **Rotate model.** Reference-ray step or heading-from-+X? Copy option? HUD:
   a new relative-angle schema vs reusing the absolute `rotation` schema?
   Retire legacy `_apply_rotate` for `manip_rotate` (and rewrite the tests that
   pin the legacy sense and rect→polyline)?
6. **Offset result types.** Ellipse and spline offsets are not ellipses /
   splines — approximate (as which primitive?), scale radii, or exclude?
   Polygon stays a RegularPolygon under a mitered offset — confirm. Corner
   joins miter or round? Through-point option? Sticky distance?
7. **Array UX.** Keep `ArrayDialog`, replace it with an on-canvas
   gridline-replicate-style pattern, or both? What does "rotate items" mean for
   polar (orientation of parametric primitives too)? Associative or one-shot?
8. **Angle-convention fix scope.** DV7 affects arc handling in trim, break,
   fillet, mirror, extend and `geometry_intersect`. Fix all in this milestone
   (one helper), or only for the tools being surfaced?
9. **Trim** in or out of this milestone; if in, multi-edge and polyline/rect
   targets?
10. **Text** in scope for the Move tool / Copy-Paste / Duplicate / Array /
    Rotate?
11. **Unreachable remainder** (Scale, Mirror, Extend, Break, Fillet, Chamfer,
    Stretch, Merge, Join, Explode): surface later, fix-and-hide, or delete
    (with the coupled tests, VC5)?
12. **Dead plumbing:** delete `numericInputRequested` /
    `complete_numeric_input` in favour of the HUD?
13. **Cut shortcut:** add Ctrl+X (the tooltip already advertises it)?
14. **Ownership:** accept this file as the behaviour owner for scene tools and
    add it to `SPEC-INDEX.md`?
