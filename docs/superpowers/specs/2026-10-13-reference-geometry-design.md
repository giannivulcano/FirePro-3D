---
status: proposal
last-verified: 2026-10-13
verified-commit: e35816e3
applies-to:
  - firepro3d/geometry_2d.py
  - firepro3d/geometry_drawing_controller.py
  - firepro3d/model_space.py
  - firepro3d/placement_input_coordinator.py
  - firepro3d/block_definition.py
  - firepro3d/block_editor.py
  - firepro3d/block_explode.py
  - firepro3d/schematic_scene.py
  - firepro3d/paper_display.py
  - firepro3d/display_manager.py
  - firepro3d/sketch_adapters.py
  - firepro3d/constraint_controller.py
  - firepro3d/scene_tools.py
  - firepro3d/scene_io.py
source-tasks: ["Space toggles normal <-> reference placement for every 2D primitive; retire the line <-/-> normal/reference variant (todo_open.md, 2D-geometry placement polish)"]
---

# Reference Geometry for every 2D primitive — Design Spec

## Goal

While placing any of the eight 2D shape primitives (line, polyline, rectangle, circle, arc,
regular polygon, ellipse, spline), **Space** toggles the placement between normal and
**reference** geometry. Reference geometry is non-printing construction scaffolding: it draws as
a hairline dashed guide, snaps / aligns / takes constraints and Smart Dimensions like normal
geometry, is saved with the Block or schematic, and never reaches placed instances, Explode or
sheet output unless its **Printed** flag is on. Any shape can be flipped between normal and
reference afterwards from the property panel.

## Motivation

User end goal (2026-10-13): construction scaffolding for 2D blocks and schematics — non-published
geometry to constrain, align and dimension real items to. Today only lines have a reference form
(`ReferenceLineItem`, picked by the line tool's ←/→ variant), so a reference circle (bolt circle),
reference rectangle (envelope) or reference arc is impossible.

## Architecture & Constraints

- Governing specs: `docs/specs/2d-geometry.md` (§1 item models + `ReferenceLineItem`, §3.6 reference
  style, §4 placement, §6 persistence, §7 display); `docs/specs/parametric-constraint-system.md` D23
  (reference lines persist in definitions as scaffolding); `docs/specs/block-system.md` (definition
  compile / Explode); `docs/specs/linetypes.md` LT2-1 (unstyled items), LT3 / LT5 (stroke routing, ends).
- **Where the tools run:** only `Model_Space(scene_role="block_editor")` scenes — the Block Editor and
  schematic editors (`block_editor.py`, `schematic_scene.py`). `PaperScene` has no 2D draw tools today
  (the "Paper Space context" wording in `2d-geometry.md` §4 is stale — reconcile at Account). A
  reference shape inside a schematic viewport is hidden from sheets by the existing paper-pass
  `printed is False` check (`paper_display.apply_paper_overrides`).
- Dual serialization (memory): every change lands on the undo path (`_capture_network` /
  `_restore_network`) AND the file paths (block definition primitives, schematic materialize,
  `_add_from_dict` for paste / duplicate / array / offset / explode, clipboard).
- Constants centralized in `firepro3d/constants.py`; no new magic numbers.

## Design Decisions

| # | Decision | Rationale / rejected |
|---|---|---|
| RG1 | **A `reference` + `printed` flag on `Geometry2DMixin`** for all eight shape classes (Text excluded). Reference shapes stay in their own class lists (`_draw_circles`, …). `ReferenceLineItem` and `scene._reference_lines` are **retired**. | Rejected B: a Reference subclass per shape (8 classes, 8 lists, 8 record types; a panel flip would swap the object). Rejected C: keep `ReferenceLineItem` + flag on the rest (two mechanisms; line flips still swap classes). Constraint adapters match by exact class (`sketch_adapters.adapter_for`), so a flagged `CircleItem` gets the circle adapter unchanged; snap matches by class too. |
| RG2 | **Record format:** a reference shape saves under its own type with `"reference": true, "printed": <bool>`; the keys are omitted when `reference` is False (normal records unchanged). Lines save as `"type": "draw_line"` + the flag, not `reference_line`. | One schema. Assumption (ratified 2026-10-13): files don't travel back to builds older than this change (an old build would read a new reference line as a normal printing line). |
| RG3 | **Legacy read:** a `reference_line` record loads as a `LineItem` with `reference=True` and its `printed` kept — on every load path: `block_definition._PRIMITIVE_FACTORY`, `schematic_scene.materialize_primitives`, `_restore_network` (`"reference_lines"` snapshot key), `_GEOM_TYPE_REGISTRY` / `_add_from_dict`, clipboard. | Existing blocks and schematics keep their scaffolding. |
| RG4 | **Look — one paint hook:** `Geometry2DMixin._sync_stroke_pen` returns, for a reference item, a cosmetic width-1 `DashLine` pen in the item's display colour and no resolved stroke, so `_paint_routed_stroke` takes the plain path (no linetype pieces, no ends, no crisp split). Fill is suppressed by one mixin gate (e.g. `_draws_fill()` = `fill_type != "none" and not reference`) that the seven `paint` → `draw_fill` sites and block compile's `_fill_ops` read; the fill panel rows hide while `reference` is on. `is_fillable()` itself is NOT changed (it answers "has a closed path", read by other consumers). The selection highlight of a reference item stays dashed. Block compile of a **printed** reference shape emits an unstyled STROKE op (the reference pen, `weight` / `pieces` / `linetype` / `ends` None — as a printed `ReferenceLineItem` compiles today), so instances draw it dashed. | The style record is never mutated, so flipping back restores linetype / weight / fill / ends exactly. Matches today's reference-line look ("hairline, always", user 2026-10-13). |
| RG5 | **Paint never writes the display colour into saved data.** The reference pen is derived per paint; `to_dict` serializes the style record (styled) — the legacy `color` / `lineweight` keys of `reference_line` are read only. | Fixes the pre-existing leak (`_sync_stroke_pen` unstyled branch rewrote the real pen, and `ReferenceLineItem.to_dict` saved that colour). |
| RG6 | **Placement:** one placement-scoped flag `Model_Space._place_reference`. **Space** toggles it in every shape tool via `cycle_placement_ambiguity` (still gated by `is_input_mode()`, so Space types into a focused HUD field). Reset to False on commit, Esc, `set_mode`, and scene reset; a polyline chain keeps it until the chain completes (a 2-vertex finish commits a reference line). Commit stamps `reference=True` on the new item. | User 2026-10-13: "reset after each placement". |
| RG7 | **Arc flip moves to Shift+Space:** at the arc's last step Shift+Space toggles CCW↔CW (Center / Start) or minor↔major (End Points); Space there toggles reference. Shift+Space elsewhere in draw modes does nothing. | User 2026-10-13: one Space rule for every 2D tool. The router already receives Shift as `reverse`. |
| RG8 | **Placement cue:** normal 2D ghosts are already width-1 dashed, so in reference mode the ghost takes the Reference Geometry colour and the instruction line appends " (Reference)". | A visible difference without a second ghost style. |
| RG9 | **Retire the line ←/→ variant:** the `draw_line` rows in `placement_input_coordinator._PLACEMENT_VARIANTS` and `_draw_line_variant` are removed; ←/→ in the line tool does nothing (frees it for "Merge Line and Polyline into one ←/→ cycle tool"). | User 2026-10-13. |
| RG10 | **Panel:** every shape shows a **Reference** toggle; when on, a **Printed** toggle shows and the stroke (linetype / weight / ends) and fill rows hide. A flip goes through `_geom2d_set` → `_push_undo` (one undo step, coalesced across a multi-target commit) and re-applies the item's new Display-Manager category values (one helper — GAP: `apply_category_defaults` has no 2D branch). | User 2026-10-13. |
| RG11 | **One scaffold predicate**, homed in `block_definition.py`: `is_scaffold(rec)` (record) + `is_scaffold_item(item)` (live) — `reference and not printed`, also accepting a legacy `reference_line` record. `block_editor._is_scaffold_item` and `schematic_scene._is_scaffold` are deleted in favour of it. All current guards keep their meaning: compile (no RenderOp), Explode skip, text snap boxes, scaffold-only Save refusal, seed centre, tile extents, schematic extent. | Three copies → one (GENERALIZE). |
| RG12 | **Paper:** `paper_display._category_for_item` checks the `reference` flag first (category "Reference Geometry"); the `printed is False` exclusion is unchanged (duck-typed on `printed`). A printed reference shape keeps today's canvas-pen plot — paper weight / B&W stays with the filed task "Printed reference lines plot at a paper line weight + colour". | No scope creep. |
| RG13 | **Display Manager:** category "Reference Lines" → **"Reference Geometry"** (colour + show/hide all), collecting every flagged item across the 2D lists; "2D Geometry" excludes flagged items. One-shot QSettings migration copies `display/Reference Lines/*` (incl. `default_*`) to the new key, mirroring `_migrate_opening_split`; a project's `display_settings["Reference Lines"]` seeds the new entry, mirroring `_project_entry`. | User 2026-10-13. |
| RG14 | **Break / Explode / Offset / Mirror / copy carry the flag:** `stroke_style.copy_style`'s callers in `scene_tools.py` (Break, geometry Explode) copy `reference` + `printed` to the pieces; `_clone` / `to_dict` round-trips already carry it. | Fixes the pre-existing Break bug (pieces became printable plain lines and the original stayed in `_reference_lines`). |

| RG15 | **Hidden refs are not dependencies:** `block_registry.prim_refs` skips the `style.linetype`, explicit end ids and hatch `fill.pattern` of a `reference` record — nothing a reference shape does not draw is bundled, purge-protected, invalidated or cycle-checked. Flipping a shape back to normal after its linetype / pattern was purged shows the existing missing-linetype / missing-pattern badge until one is picked. | User 2026-10-13 (Unit A review follow-up). The retired `ReferenceLineItem` was unstyled and never added refs; without this a scaffold line could trip `would_cycle` inside its own linetype's editor. |
| RG16 | **Mixed Join:** the joined polyline is reference only when every joined item is reference, and printed only when every joined item is printed; any normal input yields a normal polyline (selection order no longer decides). | User 2026-10-13 (seam review). |
| RG17 | **Flip-back colour:** a panel flip to Reference remembers the item's prior display-colour state (transient, not serialized) and a flip back to normal restores exactly that state — so a shape looks as it did before the flip (AC5), not re-coloured with the 2D Geometry category colour. | User 2026-10-13 (seam review). |
| RG18 | **Every path that creates or loads a reference item gives it the Reference Geometry colour** (`refresh_category_display`): placement stamp, panel flip, derive pieces (`copy_style`), `_add_from_dict` (Paste / Duplicate / Array / Mirror / Offset / Explode), `schematic_scene.materialize_primitives` / `add_primitive` (Block Editor reopen, schematic scenes) and undo restore. | Seam review finding 1 (2026-10-13). |

## Acceptance Criteria

- [ ] AC1 Space toggles reference while placing any of the 8 shape primitives in the Block Editor and in a schematic editor; each placement starts normal; the ghost uses the reference colour and the instruction line says "(Reference)".
- [ ] AC2 At the arc's last step Shift+Space flips CCW↔CW / minor↔major; Space there toggles reference.
- [ ] AC3 The line tool's ←/→ Line / Reference Line variant is gone.
- [ ] AC4 Reference shapes draw hairline dashed in the Display-Manager reference colour, with no fill, linetype or end blocks.
- [ ] AC5 Every shape's panel has a Reference toggle (multi-select, one undo step); while on, style + fill rows hide and Printed shows; flipping back restores linetype / weight / fill / ends unchanged.
- [ ] AC6 Printed off (default) → saved in the block / schematic and re-seeded on reopen, never drawn in placed instances, Explode or sheet / PDF output; Printed on → plots and renders in instances dashed.
- [ ] AC7 Reference shapes snap, align and take constraints / Smart Dimensions like their normal class.
- [ ] AC8 Display Manager "Reference Lines" is renamed "Reference Geometry"; saved QSettings and project values carry over.
- [ ] AC9 Existing `reference_line` records (undo, `.fpdb`, schematics, clipboard) load as reference lines with `printed` unchanged.
- [ ] AC10 Text has no reference form; Space does nothing in the text tool.
- [ ] AC11 Break / geometry Explode / Offset / Mirror of a reference shape yield reference pieces.

## Verification Checklist

Guard tests (VC3 — real path, observable ground truth, each shown RED with its change reverted):

- [ ] G1 Real Space keypress through `Model_View` in each of the 8 draw tools in a shown Block Editor view → the committed item has `reference=True`; the next placement is normal. Shift+Space at the arc's last step flips direction (sampled arc midpoint side).
- [ ] G2 A saved block with a non-printed reference circle: a placed instance's rendered pixels show no circle; Explode output has no circle; reopening the editor re-seeds it. Printed on → the instance renders it.
- [ ] G3 A schematic viewport on a sheet: a non-printed reference shape is absent from the PDF export raster; a printed one is present.
- [ ] G4 Styled circle (Hidden linetype, heavy weight, solid fill) → panel Reference on → rendered pixels show a hairline dashed outline, no fill; off → pixels match the pre-flip render; each flip is one undo step.
- [ ] G5 Legacy `reference_line` records from a `.fpdb` primitive list, an undo snapshot, and a clipboard payload load as `LineItem` with `reference=True` and `printed` intact.
- [ ] G6 Coincident and a driving Smart Dimension on a reference arc solve (arc geometry moves).
- [ ] G7 A QSettings `display/Reference Lines/color` value and a project `display_settings["Reference Lines"]` colour reach a reference shape's paint colour after the rename.
- [ ] G8 Break on a reference line yields two reference lines; none remains off-scene in a list.
- [ ] No regressions: the keep-green set (VC5 grep over `ReferenceLineItem`, `_reference_lines`, `reference_line`, `is_scaffold`, `Reference Lines`, `_draw_line_variant`, `_toggle_arc_cw`, `_toggle_arc_ep_major`) passes, with each rewritten test traced to RG1 / RG2 / RG9 / RG7.

## Existing Code Context

- `geometry_2d.py`: `Geometry2DMixin` (`_init_stroke`, `_sync_stroke_pen`, `_paint_routed_stroke`, `_geom2d_properties` / `_geom2d_set`, `_geom2d_to_dict` / `_geom2d_from_dict`, `is_fillable`); `ReferenceLineItem` (retired).
- `model_space.py`: `_reference_lines`, `_draw_line_variant`, `_make_line_like`, `cycle_placement_ambiguity`, `keyPressEvent` Space branch, `_capture_network` / `_restore_network`, `_remove_item_from_lists`, `_GEOM_TYPE_REGISTRY` / `_add_from_dict`, `_items_on_level`.
- `geometry_drawing_controller.py`: per-tool ghost pens (`_preview_from_line`, `_press_draw_circle`, `_press_draw_rectangle`, `_make_arc_preview_path`, `_press_polyline`, `_build_polygon_ghost`, ellipse / spline ghosts), `_toggle_arc_cw`, `_toggle_arc_ep_major`.
- `placement_input_coordinator.py`: `_PLACEMENT_VARIANTS["draw_line"]`.
- `block_definition.py`: `_PRIMITIVE_FACTORY`, `is_scaffold` (+ call sites in `_compile`, `_reference_items`, `text_snap_points`); `block_explode.py`; `block_editor.py` `_is_scaffold_item`; `schematic_scene.py` `_CLS_TO_LIST`, `_is_scaffold`, `materialize_primitives`.
- `paper_display.py`: `_category_for_item`, `apply_paper_overrides` `printed` check.
- `display_manager.py`: `_CATEGORIES` row, `_items_for_category_static`, `_migrate_opening_split` / `_project_entry` precedent, `apply_display_to_item` / `_is_geo2d_item` (misses RegularPolygonItem + ReferenceLineItem today).
- `sketch_adapters.py`: registry + `GRIP_HANDLES["reference_line"]` (retired); `constraint_controller._PARTICIPATING` drops `_reference_lines`.
- `scene_tools.py`: `_all_geometry_items`, Break / Explode (flag carry).

## Edge Cases & Error Handling

- Space while a HUD field has focus types a space (unchanged gate).
- A reference polyline finished with 2 vertices commits a reference line.
- A shape flipped to reference while it has a fill keeps the fill data hidden (not deleted).
- Unresolvable linetype badge / end blocks are not drawn for a reference item.
- A scaffold-only block is still refused on Save ("Draw or import geometry first.").
- Spline has no constraint adapter today (normal or reference) — AC7 holds "like their normal class".

## Follow-ups (filed, not in scope)

- Printed reference geometry paper weight / colour (existing task).
- `apply_display_to_item._is_geo2d_item` misses `RegularPolygonItem` (cosmetic; same net effect today) — fold into RG10's helper if touched.
