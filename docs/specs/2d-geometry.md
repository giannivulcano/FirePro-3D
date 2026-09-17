---
title: 2D Geometry System
status: current
applies-to:
  - firepro3d/geometry_2d.py
  - firepro3d/model_space.py   # 2D-geometry placement + dispatch tables only
last-verified: 2026-09-16
verified-commit: 428752f
related-contract: model-space-containment-contract.md   # SUPERSEDES the framing: primitives become Block-definition-local/level-less (C3); Text = a primitive (C5); no model-space placement (C1/C7). Body below is as-built pending implementation.
---

# 2D Geometry System

> **Superseded pending implementation (2026-09-16 — `model-space-containment-contract.md`).** The
> containment contract reframes this whole subsystem: 2D primitives become **Block-definition-local
> and level-less** (authored inside a Block definition, not placed loose in Model Space — C1/C3);
> **level scope moves to the Block instance**, so `level`/`_level_offset_mm`/`Z_CAT_CONSTRUCTION` /
> elevation-z-ordering leave the primitive (C3); **Text becomes a first-class 2D primitive** with a
> data model unified with paper annotation (C5); and **placement no longer occurs in Model Space** —
> the 2D-geometry tools live only in the **Block Editor** and **Paper Space** contexts (C7). This is
> the *target*; the contract is `status: proposal` (**unbuilt** — see its Divergences ledger D1/D3/D4).
> **The body below still describes as-built, running code** (primitives are live level-scoped model
> items today) and stays accurate for grounding until the containment-contract implementation lands.
> Per-section pointers flag the specific deltas; the invariants live once in the contract (Rule A).

> **Reference-graphic unification (2026-09-17, `3c3b00c`):** `Geometry2DMixin`
> gained an optional `layer` tag (source-layer for imported reference geometry;
> empty for authored primitives, omitted from `to_dict` when empty). It is
> threaded by `geom_dicts_to_primitives` and consumed by the reference
> `BlockDefinition`'s batched-per-layer compile. Owned by
> `reference-graphic-model.md` (R1); noted here per Rule A.

Governing spec for the reference / drawing-geometry subsystem: the item models in
`geometry_2d.py` and their placement layer in `model_space.py`. Closes
the long-standing 2D-geometry orphan (formerly `construction_geometry.py`; former
backlog "Spec session: construction geometry system"). Seeded from the 2026-08-22 (level-plane + fill) and
2026-08-24 (polish cluster) design-of-records under `docs/superpowers/specs/`.

> **Naming:** the module was renamed `construction_geometry.py` → `geometry_2d.py`
> (2026-09-16) — it began with the now-retired `ConstructionLine`. Everything
> user-facing already said "2D Geometry" (the ribbon group, the Display-Manager
> category, `Geometry2DMixin`).

## 1. Scope & item models

Eight item classes, all built on `Geometry2DMixin` + `DisplayableItemMixin` + a Qt base:

| Class | Base | Shape |
|---|---|---|
| `LineItem` | `QGraphicsLineItem` | finite 2-point line |
| `ReferenceLineItem` | `LineItem` | **non-printing** finite reference/construction line (per-item `printed` flag) |
| `PolylineItem` | `QGraphicsPathItem` | multi-segment polyline, **open or closed** |
| `RectangleItem` | `QGraphicsRectItem` | axis-aligned rect + optional rotation |
| `CircleItem` | `QGraphicsEllipseItem` | centre + radius |
| `ArcItem` | `QGraphicsPathItem` | 3-point / centre arc |
| `RegularPolygonItem` | `QGraphicsPathItem` | **parametric** regular N-gon |
| `EllipseItem` | `QGraphicsPathItem` | centre + rx/ry + **Y-up rotation** |
| `SplineItem` | `QGraphicsPathItem` | **NURBS / B-spline** (control pts + degree + knots + weights) |

`GridlineItem` is **not** a 2D-geometry item (it is a datum; see `grid-system.md`).

> → **`model-space-containment-contract.md` C5** (pending implementation) adds **Text** as a
> first-class 2D primitive (a typeable box, Word-style font), with a data model unified with
> paper-space annotation. It is authored inside Block definitions like any other primitive; standalone
> model-space text is retired. *(Count note: the intro says "Eight item classes" but the table already
> lists nine — a stale count predating `ReferenceLineItem`; corrected in the full body rewrite that
> binds to the contract implementation, not this pointer stage.)*

**`ReferenceLineItem` (task D, 2026-09-16)** — a non-printing finite reference /
construction line. Subclasses `LineItem`, so it inherits grips, manipulator
transforms, translate/rotate, **and SNAP participation** for free (the snap
engine matches `isinstance(item, LineItem)`); edits/selects/deletes identically
to a line. Differences:
- Always rendered in the width-1 dashed reference style; tracked in its own
  `scene._reference_lines` list (serialized under `"reference_lines"` in `.fpd`,
  undo capture/restore, and paste — type `"reference_line"`; `_remove_item_from_lists`
  routes it via `type_to_list` **before** `LineItem`, subclass-ordered).
- Per-item **`printed` flag, default False.** `printed=False` → excluded from
  paper-space plots (`paper_display.apply_paper_overrides` hides `printed is False`
  during the render pass) AND from a saved block definition
  (`BlockEditor.gather_primitives` includes reference lines only when printed);
  `printed=True` → plots dashed at the "Reference Lines" paper weight + embeds in
  the block. Edited via a **`ToggleSwitch`** ("toggle" property-field type).
- Own **"Reference Lines"** Display-Manager category (colour + show/hide-all;
  `display_manager._CATEGORIES` + `_items_for_category_static`;
  `paper_display._category_for_item` maps it before `LineItem`). Level-scoped;
  plan-only (no elevation/3D). Placement: a `draw_line` ←/→ variant
  (Line ↔ Reference Line, `_draw_line_variant`) building via `_make_line_like`.
  Supersedes the removed AutoCAD-style `ConstructionLine` xline.

### 1.1 `Geometry2DMixin` (the shared contract)
Provides level-plane placement + fill for all six classes:
- `level` + `_level_offset_mm` (default 0, +up); `z_range_mm()` → `(elev, elev)` at
  `level.elevation + offset`; items participate in view-range + elevation-based
  z-ordering at **`Z_CAT_CONSTRUCTION`** (2D geometry wins over building geometry at
  equal elevation; below annotation/symbol/design bands).

> → **`model-space-containment-contract.md` C3** (pending implementation): `level`,
> `_level_offset_mm`, `Z_CAT_CONSTRUCTION`, and elevation-based z-ordering **move off the primitive**
> — 2D primitives become definition-local and **level-less**; level scope becomes a property of the
> placed **Block instance** (also `view-relationships.md §3.3/§7.3`, superseded there in parallel).
> As-built today the primitive carries these; enforcement moves them at the contract implementation.
- Fill state: `fill_type` (`none`/`solid`/`hatch`), `fill_pattern`, `fill_opacity`
  (default 0.45, solid only), fill colour on `_display_color`'s sibling
  `_display_fill_color`. `is_fillable()` is true iff `get_closed_path()` returns
  non-None. Fill is rendered in each item's own `paint()` via `draw_fill()`.
- Property rows (`_geom2d_properties`) + setter (`_geom2d_set`) + dual-path
  serialization stamps (`_geom2d_to_dict`/`_geom2d_from_dict`).

## 2. Closed polylines (invariant)

`PolylineItem` closure is an **explicit `_closed: bool` flag**, NOT a duplicated
vertex (the FloorSlab model):
- vertex list stays `[P0…Pn]` with no duplicate; `_rebuild_path()` calls
  `closeSubpath()` when `_closed and len>=3`; `is_closed()` returns the flag;
  `close()` sets it.
- The shared start/end is therefore a **single grip** (grip 0) whose drag moves
  both adjoining segments.
- **Back-compat (required):** `from_dict` migrates legacy coincident-first/last
  polylines (no `closed` key, first≈last within 1e-3) → flagged closed with the
  duplicate dropped. The `scene_io` legacy-`HatchItem` migration builds a filled
  closed polyline via `close()`. Both preserve fill.
- Consumers that copy a polyline (offset `_make_offset_item`, `update_preview`)
  forward the flag.

## 3. RegularPolygonItem (parametric)

Stores `_center`, `_sides` (3–120), `_radius_mm`, `_rotation_deg`, `_inscribed`;
**vertices are always derived** (`vertices()`), never stored.

- **Geometry convention:** *inscribed* → `_radius_mm` is the circumradius
  (centre→vertex); *circumscribed* → `_radius_mm` is the apothem (centre→edge
  midpoint). `vertices()` applies a half-step (`180/sides`) orientation offset for
  circumscribed internally, so `_rotation_deg` = the desired orientation directly
  (0° = a vertex/edge pointing +x).
- **Y-up rotation (invariant):** `vertices()` uses `cy - rv*sin(a)` and `apply_grip`
  uses `atan2(-dy, dx)` — the app-wide **Y-up / CCW-positive** convention, matching
  the placement rotate angle, the dashed reference line, and the shared "rotation"
  HUD schema. The two are exact mutual inverses (a dragged vertex lands under the
  cursor). Ground-truth tests assert the *observable* vertex direction, not
  `rotation()==angle`.
- **Grips:** `grip_points()` = `[centre] + vertices`; grip 0 moves the centre; a
  vertex grip drag sets radius+rotation keeping it regular (no free deform).
- **Properties:** Sides / Radius / Rotation / Shape(enum) + the mixin rows;
  `set_property` regenerates.
- **Serialization:** `type: "polygon"` with centre/sides/radius/rotation/inscribed.

## 3.5 EllipseItem + SplineItem (curve primitives, 2026-09-07)

Two curve primitives added so DXF/PDF ellipses and splines can import as real
curves (the *import extraction* itself is a separate task — these are the
editable target primitives). Both are `QGraphicsPathItem`-based (not native Qt
shapes) so their geometry is data-parametric and paint-applied.

### 3.5.1 EllipseItem
- Stores `_center`, `_rx` (semi-major), `_ry` (semi-minor), `_rotation_deg`.
  **Rotation is data-parametric + Y-up (CCW-positive)**, applied in
  `get_closed_path()` via `QTransform().rotate(-_rotation_deg)` — never Qt
  `setRotation`, matching the `RegularPolygonItem` convention. Anti-degeneracy
  floor: `rx`/`ry` clamp to ≥ 0.5 mm (the `_AXIS_MIN` = same epsilon as
  circle/polygon radii).
- **Grips (5):** `[centre, major+, major-, minor+, minor-]`. Grip 0 translates;
  the major-axis grips set `rx` **and** `_rotation_deg` (via `atan2(-dy,dx)`,
  the exact inverse of the axis-endpoint formula — the dragged grip lands under
  the cursor); the minor-axis grips set `ry` only. No rotation grip — the major
  axis carries rotation.
- **Placement:** 3-click axes — centre → major-axis endpoint (`rx` + rotation)
  → minor-axis extent (`ry`). Mode `"draw_ellipse"`, list `_draw_ellipses`,
  `type: "draw_ellipse"`. Always closed → fillable.

### 3.5.2 SplineItem
- **Full NURBS data model:** `_control_points`, `_degree`, `_knots`, `_weights`
  (`None` ⇒ non-rational). Stored general so an *imported* arbitrary-degree
  rational spline round-trips verbatim; **authored** splines are the constrained
  subset (cubic, auto clamped-uniform knots, non-rational — degree auto-lowers
  when < 4 control points: 2 pts → line, 3 → quadratic). A degenerate < 2-point
  spline stores `_knots = None` (ezdxf rejects order 1).
- **Rendering/eval via `ezdxf.math.BSpline`** (`_bspline_path()`), used purely
  as a NURBS evaluator (no DXF I/O — respects the read-only-DXF rule).
  `order = min(degree+1, n_points)`; `.flattening()` tessellates to a
  `QPainterPath` polyline.
- **Grips:** one per control point (drag → rebuild). No centre grip.
  Add/remove control point is deferred.
- **Placement:** N-click control polygon (mirrors polyline) — Enter/double-click
  finishes, Delete pops the last point, 1 point cancels. Mode `"draw_spline"`,
  list `_draw_splines`, `type: "draw_spline"`. Open (not fillable) unless first
  == last control point.

Both register in `block_definition._PRIMITIVE_FACTORY` and thread through the
full dual-path persistence + enumeration set (§6).

### 3.5.3 Curve import-extraction contract (block-editor only)

DXF/DWG import into the **Block Editor** preserves arcs, full ellipses and
splines as these editable primitives (partial ellipses + PDF Béziers still
tessellate — no primitive exists / disproportionate effort). It is gated by a
`preserve_curves` flag on `DxfImportWorker` (default **False**, so the underlay
import path is byte-identical); `BlockImportDialog` sets it True. The shared
geom-dict schemas (scene-space; DXF `y` already negated) are:

```jsonc
// ARC — Qt-arcTo bounding-rect schema. append_geom_to_path + apply_import_transform
// already consume it; ArcItem._rebuild_path feeds start/span into the IDENTICAL
// QPainterPath.arcTo, so the factory mapping needs NO Y-flip.
{ "kind": "arc", "rx": cx-r, "ry": -cy-r, "rw": 2r, "rh": 2r,
  "start": start_angle_dxf, "span": sweep_dxf }
// ELLIPSE (full) — already emitted today (underlay renders it); only the factory changed.
{ "kind": "ellipse_full", "x": -maj, "y": -min, "w": 2maj, "h": 2min,
  "pos_cx": cx, "pos_cy": -cy, "rotation": -rot_deg }
// SPLINE — native NURBS payload; control points scene-space, knots/weights parametric.
{ "kind": "spline", "control_points": [[x,-y],…], "degree": d,
  "knots": [...]|null, "weights": [...]|null, "closed": bool }
```

`ArcItem`/`EllipseItem`/`SplineItem` are the editable targets; the extraction
maps these dicts via `geometry_import.geom_dicts_to_primitives`. Import rotation
(`ImportParams.rotation`) is applied to **all** kinds in `apply_import_transform`.

## 3.6 Reference lines (placement + selection guides) — invariant

A **reference line** is the canonical dashed guide the 2D-geometry tools use to
show *defining geometry* — axes, radii, control polygons, the 0° datum / sweep
radials. **One visual style, used everywhere:** a **cosmetic width-1 dashed pen
in the geometry colour** (`QPen(geom_colour, 1, Qt.PenStyle.DashLine)` +
`setCosmetic(True)`). The scene-side factory `Model_Space._make_ref_line()` /
`_make_ref_circle()` (z = 200) builds the placement-time guides; each item's
`paint()` draws the same style for the selection-time guides.

**Invariants:**
- The **placement-time** guide and the **selection-time** guide for the same
  primitive MUST use this identical style. **All 2D-geo ghosts are width-1
  dashed (2026-09-16):** the shape-preview rubber-bands (rect/circle/arc/polygon)
  were standardized from width-2 to width-1, and the line/polyline ghosts were
  brought onto it too — the line ghost stops reusing the shared `preview_pipe`
  darkGray/width-3 pipe pen (`_preview_from_line` re-pens it per move; `set_mode`
  resets `preview_pipe` to the darkGray default so pipe/set_scale keep their
  look), and the polyline is ghosted width-1 dashed during placement with
  `PolylineItem.finalize()` restoring the committed solid pen at its lineweight.
- Selection-time reference guides are drawn **whenever the item `isSelected()`**,
  independent of `_manip_wraps()` — they are a content aid, not the selection
  highlight (only the lighter highlight outline is gated on `not _manip_wraps`,
  to avoid double-drawing with the manipulator frame).
- Items that expose defining geometry render it as reference lines on selection:
  `EllipseItem` (major + minor axes), `SplineItem` (control polygon),
  `RegularPolygonItem` (circumradius circle), **`RectangleItem` (corner
  diagonals), `CircleItem` (radius guide + bounding box)** — the latter two via
  `_selection_ref_segments()`.

## 4. Placement workflows (`model_space.py`)

> → **`model-space-containment-contract.md` C1/C7** (pending implementation): 2D-geometry placement
> **no longer occurs in Model Space**. The tools move to the **Block Editor** (authoring) and **Paper
> Space** contexts; the Create tab is dissolved (`ribbon-bar.md` D10). This whole section describes the
> as-built model-space placement layer, which is removed at the contract implementation (C8 clean-drop
> of loose geometry). The 2D-geometry *placement-polish* batch still applies **inside the Block Editor**.

Placement is **single-placement** for 2D geometry + Architecture (user,
2026-09-16, reverting the 2026-08-24 always-continuous default): a completed
placement returns to **Select** with the just-placed item selected (so its
manipulator frame shows), via `Model_Space._end_placement_switch(item)` called as
the last step of each commit, gated on `_SINGLE_PLACEMENT_MODES`. Chain tools
(polyline, wall-polyline, floor-polygon) switch only when the chain **completes**
(Enter / double-click / close-near-first / loop-close); mid-chain keeps drawing.
Continuous modes (pipe/sprinkler/gridline) still re-arm every commit. **Esc**
exits to Select in all modes. A mode is
registered by adding rows to the dispatch tables: `_PRESS_DISPATCH`,
`_MOVE_DISPATCH` (mouse-move preview — distinct from `_PREVIEW_DISPATCH`, the HUD
field-commit path), the instruction map, cursor map (`model_view.py`),
`_SCHEMA_FOR_MODE`/`_APPLIER_FOR_MODE`, and `get_placement_anchor`.

- **Line/rect/circle/arc:** see the existing 2-click (+ rect/arc rotate/variant)
  handlers. Rectangle & Arc expose ←/→ placement variants; rectangle & polygon
  have a rotate step whose HUD uses the shared **"rotation"** schema (step-aware
  `active_schema`; the rotation seed dispatches by mode to the correct pivot).
  **Centre-mode rectangles** (2D-geo, wall, floor) use a dedicated
  **`rectangle_center`** HUD schema whose `W`/`H` fields are the **full** width
  and height (not the corner-mode signed half-extents) — `active_schema` picks it
  when the primitive's `_*_rect_from_center` flag is set. See
  `dynamic_input.py` (`seed_rectangle_center`/`resolve_rectangle_center`).
- **Placement selection (no accumulation):** every primitive is
  `setSelected(True)` on commit, and the commit **clears the prior selection
  first** so placing several in a row leaves only the last-placed item selected
  (commit sites in `geometry_drawing_controller.py` + the `model_space.py` line
  factory / polyline-finalize paths).
- **Polyline:** multi-click; **click the START vertex (≥3 verts) to close** (a
  distinct blue close-ring cues it near the first vertex); double-click / Enter
  finish *open*; **Delete** pops the last vertex (routed via a `Model_View`
  `ShortcutOverride` accept so it beats the window Delete shortcut; cancels at one
  vertex). All stay in polyline mode.
- **Polygon (3-step, mirrors centre-rectangle):** centre → radius (axis-aligned) →
  rotate. `↑/↓` change #sides and `←/→` toggle inscribed/circumscribed **live at
  every step**; a dashed **reference circle** shows during placement and while the
  polygon is **selected**; the readout carries the sides/shape hints; the HUD
  Angle field live-seeds during the rotate step. Radius < 0.5 mm is rejected
  (centre stays armed).
- **Wall (2026-08-25):** wall placement registers into this same dispatch surface
  as a first-class client. One `"wall"` scene-mode carries `_wall_primitive ∈
  {"line","polyline","rect"}` + `_wall_rect_from_center`; ←/→ cycles all four
  variants (Line / Polyline / Corner Rect / Center Rect) via `_PLACEMENT_VARIANTS`;
  the rect variants share the same **3-step** pattern (anchor → size → rotate)
  and use the shared **"rotation"** HUD schema for the rotate step (step-aware
  `active_schema`). `rect_sizing_points()` in `geometry_2d.py` is now
  **shared** between the 2D-geo rectangle and the wall rectangle. See
  `wall-room-floor-system.md §4.4` for the full wall-placement contract.
- **Floor (2026-08-28):** floor placement registers into the same dispatch as a
  first-class client, mirroring the wall. One `"floor"` scene-mode carries
  `_floor_primitive ∈ {"rect","polygon"}` + `_floor_rect_from_center`; ←/→ cycles
  Corner Rect / Center Rect / Polygon via `_PLACEMENT_VARIANTS`; the rect variants
  share the **3-step** (anchor → size → rotate) pattern with the shared
  **"rotation"** HUD schema (step-aware `active_schema` → `_floor_schema_for_primitive`),
  and reuse `rect_sizing_points()` / `rotated_rect_corners()`. The polygon variant
  shares the polyline close-ring / Enter / double-click / **Delete-pop** UX. `F`
  shortcut; `set_mode("floor_rect")` is a back-compat alias. The floor commits **one**
  closed-polygon `FloorSlab` (not N segments). See `wall-room-floor-system.md §11.4`
  for the full floor-placement + elevation-model contract.

## 5. Snap contribution (`snap_engine.py`)

Each closed shape emits its named snap points and intersection segments. The
polygon (like the rectangle) emits **vertices (endpoint), edge midpoints
(midpoint), centre (center)**, plus its edges as intersection/nearest/perpendicular
segments — its branch must precede the generic `QGraphicsPathItem` branch in every
dispatch site (emitter, `_phase4_items`, `_geometric_snaps`).

**EllipseItem** emits **centre + 4 rotated axis-endpoint quadrants** via its own
`_collect` branch placed **before** the generic `QGraphicsEllipseItem`/path branch
(mandatory: `CircleItem` rides the generic `QGraphicsEllipseItem` branch, which
reads an axis-aligned `boundingRect` and would emit *wrong* quadrants for a
rotated ellipse). **SplineItem** emits its **endpoints + control points** (as
endpoint-class snaps) via its own branch before the generic path branch.
**Deferred** (logged here, not silently capped): ellipse/spline
perpendicular / nearest / tangent / phase-4 intersection snapping — disproportionate
numerical effort (ellipse-segment = quartic; NURBS projection) for rare use.

## 6. Persistence (dual path — invariant)

Every item type persists through **both** hand-written serializers (memory: dual
serialization): `_capture_network`/`_restore_network` (undo) **and** `scene_io.py`
(file), plus copy/paste dispatch and the clipboard-ghost ctors. A new item list
(e.g. `_draw_polygons`) must also be added to the read/collect helpers that
enumerate the sibling lists: `_items_on_level`, `_all_geometry_items`
(`scene_tools.py`), the level-visibility + elevation-z passes (`level_manager.py`),
`_all_scene_items` (`level_widget.py`), the "2D Geometry" category collector
(`display_manager.py`), and the 3D renderer (`view_3d.py`). Grep `_draw_arcs`
across `firepro3d/` to find them all.

## 7. Display

The **"2D Geometry"** Display-Manager category owns colour / visibility / opacity
for all six item types (mirrors Design Area; no per-category line-weight yet).
Fill is a per-item property, independent of the category.

## Cross-references (Rule A — these own the linked facts)
- Z-order / elevation model → `view-relationships.md §7.3` + `constants.py`.
- Level-plane placement + fill design → `view-relationships.md §3.3/§7.3`.
- Ribbon "2D Geometry" group + contextual tab → `ribbon-bar.md §3.8`.
- Snapping engine → `snapping-engine.md`.
- Units / dimension parsing → `units-and-formatting.md`.

## Deferred / follow-ups
- Vertical / elevation-plane anchoring; elevation-view projection; 3D extrude of
  filled 2D profiles; hatch scale control; per-category 2D-geometry line-weight.
- Parametric-polygon polish (explode → editable polyline; "Sides" as a HUD COUNT
  field); Line+Polyline single ←/→ cycle tool (retire the `K` placeholder).
