---
title: 2D Geometry System
status: current
applies-to:
  - firepro3d/geometry_2d.py
  - firepro3d/arc_math.py      # pure arc construction (End Points placement + arc grips)
  - firepro3d/geometry_drawing_controller.py   # 2D-geometry placement handlers
  - firepro3d/model_space.py   # 2D-geometry placement + dispatch tables only
last-verified: 2026-09-24
verified-commit: 4e48885
related-contract: model-space-containment-contract.md   # LANDED: primitives are Block-definition-local/level-less (C1/C3); Text is a primitive (C5); no model-space placement (C1/C7).
---

# 2D Geometry System

> **Containment contract landed (C1/C3/C5/C7).** As-built: the 2D primitives are
> **Block-definition-local and level-less** — authored inside a Block definition (or Paper
> Space), never placed loose in Model Space (C1). **Level scope lives on the placed Block
> instance**, not the primitive: `level`/`_level_offset_mm`/`z_range_mm`/`Z_CAT_CONSTRUCTION`/
> elevation-z-ordering have left `Geometry2DMixin` (C3 — see `block-system.md` +
> `view-relationships.md §7.3` for the instance-level model). **Text is a first-class 2D
> primitive** (the 9th) with a data model unified with paper annotation — `TextItem` in
> `text_item.py` (C5). The 2D-geometry tools live only in the **Block Editor** and **Paper
> Space** contexts; the Create tab is dissolved (C7 — `ribbon-bar.md`). The containment
> invariants live once in `model-space-containment-contract.md` (Rule A); this spec links to
> the C-numbers and owns the primitive mechanics.

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

**Eight primitive types** live in `geometry_2d.py`, all built on `Geometry2DMixin` +
`DisplayableItemMixin` + a Qt base (`ReferenceLineItem` is a non-printing variant of `LineItem`,
listed separately below). **Text is the 9th primitive** (C5) — `TextItem` in `text_item.py`,
sharing `Geometry2DMixin` but with its own renderer + data model unified with paper annotation
(governed here for its primitive-family membership; the text data model + paper affordances are in
`paper-space.md`).

| Class | Base | Shape |
|---|---|---|
| `LineItem` | `QGraphicsLineItem` | finite 2-point line |
| `ReferenceLineItem` | `LineItem` | **non-printing** finite reference/construction line (per-item `printed` flag) |
| `PolylineItem` | `QGraphicsPathItem` | multi-segment polyline, **open or closed** |
| `RectangleItem` | `QGraphicsRectItem` | axis-aligned rect + optional rotation |
| `CircleItem` | `QGraphicsEllipseItem` | centre + radius |
| `ArcItem` | `QGraphicsPathItem` | centre + radius + start/span (stored CCW, span > 0) |
| `RegularPolygonItem` | `QGraphicsPathItem` | **parametric** regular N-gon |
| `EllipseItem` | `QGraphicsPathItem` | centre + rx/ry + **Y-up rotation** |
| `SplineItem` | `QGraphicsPathItem` | **NURBS / B-spline** (control pts + degree + knots + weights) |

`GridlineItem` is **not** a 2D-geometry item (it is a datum; see `grid-system.md`).

> **Text (the 9th primitive — C5, landed).** `TextItem` (`text_item.py`) is a typeable box
> (position, box W/H, wrap, Word-style font) authored inside Block definitions and Paper Space like
> any other primitive; standalone model-space text is retired. One `TextItem` on `TextAnnotationData`
> replaces the former `NoteAnnotation` (model) + `TextAnnotationItem` (paper); it compiles to outlined
> glyphs inside block definitions. Sizing follows the scene (`device_independent_text()`): paper text
> is zoom-invariant, block-editor text scales with the scene. See `model-space-containment-contract.md`
> C5 + `paper-space.md`.

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
Provides **fill + a reference-graphic `layer` tag** for all primitive classes. It is
**level-less** (containment C3): the mixin carries **no** `level`, `_level_offset_mm`,
`z_range_mm()` override, or `Z_CAT_CONSTRUCTION` — those left the primitive when level scope
moved to the placed **Block instance**. `init_geometry2d()` takes no level; primitives call
`init_displayable(level=None)` so **no `.level` attribute is created** (a level-less primitive's
`z_range_mm()` falls back to the `DisplayableItemMixin` base → `None`). A pre-C3 primitive dict
carrying `level`/`level_offset_mm` is read-and-ignored on `from_dict`.

> → **Level / elevation / Z-order model is owned by the placed Block instance**, not the primitive
> (`model-space-containment-contract.md` C3): `BlockInstance` carries `level` + `_level_offset_mm` +
> `z_range_mm()` and is filtered by active level / view-range via `LevelManager`. See
> `block-system.md` (instance level-scope) + `view-relationships.md §7.3` (Z model) — Rule A.
- `layer` — source-layer tag for imported reference geometry (empty for authored primitives;
  omitted from `to_dict` when empty). Owned by `reference-graphic-model.md` (R1); noted here per Rule A.
- Fill state: `fill_type` (`none`/`solid`/`hatch`), `fill_pattern`, `fill_opacity`
  (default 0.45, solid only), fill colour on `_display_color`'s sibling
  `_display_fill_color`. `is_fillable()` is true iff `get_closed_path()` returns
  non-None. Fill is rendered in each item's own `paint()` via `draw_fill()`.
- Property rows (`_geom2d_properties`) + setter (`_geom2d_set`) + dual-path
  serialization stamps (`_geom2d_to_dict`/`_geom2d_from_dict`).
- **New-geometry pen (2026-09-23, block polish):** `Model_Space._geom_color_lw()` returns
  `constants.DEFAULT_GEOMETRY_LINEWEIGHT` (was a hard-coded 2.0) — the weight for every committed
  tool-drawn primitive **and** Block-Editor-imported ones (`geom_dicts_to_primitives(...,
  lineweight=)`). Placement ghosts keep their own preview pens (§3.6).

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
  **Bézier-chain fast path (2026-09-23, block polish):** a non-rational, clamped, degree-3
  spline whose every interior knot has multiplicity 3 (`n = 3k+1` control points —
  `_is_bezier_chain`) is a chain of cubic Bézier spans and is drawn **natively and exactly**
  via `QPainterPath.cubicTo` (the PDF-import form); every other NURBS keeps the ezdxf
  flattening above.
- **Grips:** one per control point (drag → rebuild). No centre grip.
  Add/remove control point is deferred.
- **Placement:** N-click control polygon (mirrors polyline) — Enter/double-click
  finishes, Delete pops the last point, 1 point cancels. Mode `"draw_spline"`,
  list `_draw_splines`, `type: "draw_spline"`. Open (not fillable) unless first
  == last control point.

Both register in `block_definition._PRIMITIVE_FACTORY` and thread through the
full dual-path persistence + enumeration set (§6).

### 3.5.3 Curve import-extraction contract (block-editor only)

DXF/DWG/PDF import into the **Block Editor** preserves curves **exactly** as
these editable primitives — no tessellation (2026-09-23, block polish: partial
ellipses and PDF Béziers joined arcs / full ellipses / splines). It is gated by
a `preserve_curves` flag on `DxfImportWorker` **and** `PdfImportWorker` (default
**False**, so the underlay import path is byte-identical); `BlockImportDialog`
sets it True. The shared
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

**DXF partial ELLIPSE** (`preserve_curves`) → one exact **rational** `spline`
dict via ezdxf `BSpline.from_ellipse(entity.construction_tool())` (control
points Y-negated, knots/weights verbatim). Full ellipses stay `ellipse_full`.

**PDF curves** (`pdf_import_worker`, `preserve_curves`; 2026-09-23, block polish):
- Each drawing splits into **contiguous subpaths** — a gap >
  `constants.PDF_CURVE_JOIN_EPS` between segment ends starts a new subpath;
  `re`/`qu` items stay closed `path_points`.
- Each **maximal all-Bézier run** is tested against **one** least-squares circle
  fitted to samples of every segment, accepted when every sample is within
  `max(PDF_CIRCLE_FIT_ABS_TOL, PDF_CIRCLE_FIT_REL_TOL·r)` (values + rationale in
  `constants.py`). Ends meeting in a full turn → `circle`; otherwise an `arc`
  (schema above) whose centre is **projected onto the chord's perpendicular
  bisector** so it passes exactly through the source endpoints. A near-straight
  run (no bulge beyond tolerance) or a direction reversal is rejected.
- Stretches between carved circles/arcs merge into **one** piece each:
  `path_points` if all lines, else **one exact cubic `spline`** — lines
  degree-elevated to collinear cubics, interior knots multiplicity 3, so each
  span is the source Bézier verbatim (drawn by the §3.5.2 Bézier-chain path).
- Flag off (underlay path): Bézier flattening unchanged (`underlay-workflow.md §18.5`).

Guards: `tests/test_block_curve_import.py`.

## 3.6 Reference lines (placement + selection guides) — invariant

A **reference line** is the canonical dashed guide the 2D-geometry tools use to
show *defining geometry* — axes, radii, control polygons, the centre→endpoint / sweep
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
  diagonals), `CircleItem` (radius guide + bounding box), `ArcItem` (radials
  centre → start and centre → end, 2026-09-24)** — the latter three via
  `_selection_ref_segments()`.
- Because an arc's centre can lie outside its path bounds, a **selected**
  `ArcItem`'s `boundingRect()` also covers the centre (`itemChange` calls
  `prepareGeometryChange()` on `ItemSelectedChange`) so the radials repaint; its
  `shape()` stays the stroked arc, so clicking empty space near the centre does
  not select it.

## 4. Placement workflows (`model_space.py`)

> → **Placement is authoring-context only (C1/C7, landed).** 2D-geometry placement **does not occur
> in the plan Model Space** — the plan scene's `set_mode` refuses the loose primitives via the
> `scene_role`/`authoring_allowed()` gate (`model-space-containment-contract.md` C1). The tools run in
> the **Block Editor** scene (`Model_Space(scene_role="block_editor")`) and the **Paper Space** context;
> the Create tab is dissolved (`ribbon-bar.md`). The dispatch-table + placement mechanics described
> below are shared machinery, now exercised in those authoring contexts (not the plan scene). Legacy
> loose plan-scene geometry is clean-dropped on load (C8).

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

- **Line/rect/circle/arc:** see the per-mode handlers in
  `geometry_drawing_controller.py`. Rectangle & Arc expose ←/→ placement variants
  (a Ctrl/Shift/Alt/Meta-modified arrow does **not** cycle the variant). The
  polygon keeps a rotate step on the shared **"rotation"** schema; the rectangle
  has **no** rotate step (its angle comes from the first side — below).
- **Rectangle — 3-click base → side → depth (2026-09-23; shared by 2D rect, wall
  rect, floor rect).** Click 1 = **base**; click 2 fixes the **first side** (its
  angle + W); click 3 fixes the **depth** (H) perpendicular to that side, and the
  rect commits already rotated (`RectangleItem.set_angle(angle, pivot=base)`; 0°
  stays axis-aligned). Corner variant: base = a corner, `base → click 2` is the
  full side W, depth is **signed** (+ = left of the side, Y-up; − = the other
  side). Centre variant: base = the centre, click 2 = the **edge midpoint** (half
  a W from the centre; the side guide is drawn mirrored through the base), depth
  magnitude = half of H. Ctrl angle-constrains the side step. HUD schemas: side →
  `rect_side` (W + Angle, corner) / `rect_side_center` (W is the **full** width);
  depth → `rect_depth` (signed H) / `rect_depth_center` (full H) — the depth
  resolvers read the side's left normal via the `__dir__` injection
  (`align-placement.md §5.2` owns the schema table). The depth-step ghost is drawn
  **floorless** (a near-zero depth shows as a line along the side) while the
  commit rejects any full extent < 0.5 mm (the step stays armed); a side < 0.5 mm
  is likewise refused. **One home:** the pure helpers in `geometry_2d.py` —
  `rect_side_frame`, `rect_signed_depth`, `rect_side_ghost`,
  `rect_from_side_and_depth` (commit, 0.5 mm floor) / `_rect_solve` (floor as a
  parameter), `apply_rect_ghost` (the ghost fit, same transform as `set_angle`),
  `rotated_rect_corners` — wall and floor call these, never re-derive the math.
  (`rect_sizing_points` and the `rectangle` / `rectangle_center` schemas are
  deleted.)
- **Arc — three ←/→ variants.** *Center* (centre → start point [radius + start
  angle, `line` HUD] → end [`arc_span` HUD]); *Start* (start point → centre →
  end, same schemas); *End Points* (2026-09-23): end **A** → end **B** (the chord;
  `line` HUD from A, Ctrl angle-constrains, chord < 0.5 mm rejected) → the
  **centre**, which is constrained to the chord's perpendicular bisector (the
  cursor is projected onto it). The default is the **minor** arc, bulging away
  from the centre's side of the chord; **Space** toggles minor ↔ major (reset per
  placement); with the centre on the chord (semicircle) the last non-zero side is
  kept. **90° snap (2026-09-24):** for the mouse preview and click commit, when
  the centre's signed bisector distance |t| is within the OSNAP aperture of the
  half-chord h (the radials C→A and C→B perpendicular), |t| is pinned to h (sign
  kept) so the arc is exactly 90° minor / 270° major. The window is
  `SNAP_TOLERANCE_PX` converted by the active view zoom (`px_to_scene` +
  `_active_view_scale()`; with no view attached the scale falls back to 1.0,
  i.e. `SNAP_TOLERANCE_PX` scene mm). Guides: centre → apex, centre → A,
  centre → B. Step 3 HUD = `arc_radius` (typed radius places the centre on the
  bisector on the live side — exact, **never** 90°-snapped; a radius below ½
  chord is refused). One home for the math: `arc_math.py`
  (`project_to_bisector`, `arc_through_chord`, `center_for_radius`); the snap
  lives in `GeometryDrawingController._arc_ep_solve(snap90=…)`.
- **`ArcItem` storage is CCW:** a negative (CW) span passed to `__init__` (mirror
  tool, legacy saves) is normalised to the same geometric arc with a positive span
  (start += span, span = −span). Grips: centre / start / end — their drag
  semantics (centre: bisector slide; ends: slide along the circle) are owned by
  `selection-manipulator.md` (U3 ArcItem).
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
- **Polygon (3-step):** centre → radius (axis-aligned) →
  rotate. `↑/↓` change #sides and `←/→` toggle inscribed/circumscribed **live at
  every step**; a dashed **reference circle** shows during placement and while the
  polygon is **selected**; the readout carries the sides/shape hints; the HUD
  Angle field live-seeds during the rotate step. Radius < 0.5 mm is rejected
  (centre stays armed).
- **Wall (2026-08-25):** wall placement registers into this same dispatch surface
  as a first-class client. One `"wall"` scene-mode carries `_wall_primitive ∈
  {"line","polyline","rect"}` + `_wall_rect_from_center`; ←/→ cycles all four
  variants (Line / Polyline / Corner Rect / Center Rect) via `_PLACEMENT_VARIANTS`;
  the rect variants use the same **3-click base → side → depth** flow and
  `rect_side*`/`rect_depth*` schemas as the 2D rectangle (above; the
  `geometry_2d.py` rect helpers are the one home). See
  `wall-room-floor-system.md §4.4` for the full wall-placement contract.
- **Floor (2026-08-28):** floor placement registers into the same dispatch as a
  first-class client, mirroring the wall. One `"floor"` scene-mode carries
  `_floor_primitive ∈ {"rect","polygon"}` + `_floor_rect_from_center`; ←/→ cycles
  Corner Rect / Center Rect / Polygon via `_PLACEMENT_VARIANTS`; the rect variants
  use the same **3-click base → side → depth** flow + `rect_side*`/`rect_depth*`
  schemas as the 2D rectangle (`_floor_schema_for_primitive`; the `geometry_2d.py`
  rect helpers are the one home). The polygon variant
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
(file), plus copy/paste dispatch and the clipboard-ghost ctors. Serialized dicts are
**level-less** (C3) — no `level`/`level_offset_mm` keys (the `layer` tag + `fill` block
persist). These lists live/serialize in the **Block Editor** authoring scene; in the
**plan** scene they are permanently empty (loose geometry is gated out by C1 and
clean-dropped on load by C8), so the primitives no longer participate in the plan-scene
level-visibility / elevation-z / 3D-projection passes (those readers were deleted in the
C3 slice from `level_manager.py`, `view_3d.py`, `elevation_scene.py`). A new item list
still threads the collect helpers that enumerate the sibling lists: `_items_on_level`,
`_all_geometry_items` (`scene_tools.py`), the "2D Geometry" category collector
(`display_manager.py`). Grep `_draw_arcs` across `firepro3d/` to find them all.

## 7. Display

The **"2D Geometry"** Display-Manager category owns colour / visibility / opacity
for all six item types (mirrors Design Area; no per-category line-weight yet).
Fill is a per-item property, independent of the category.

## Cross-references (Rule A — these own the linked facts)
- **Level / elevation / Z-order model** (now on the placed Block instance, not the primitive) →
  `block-system.md` (BlockInstance level scope) + `view-relationships.md §7.3` + `constants.py`.
- **Containment invariants** (placement-only, level-on-instance, Text primitive) →
  `model-space-containment-contract.md` C1/C3/C5/C7.
- Ribbon topology (Create dissolved; Block-Editor/Paper authoring contexts) → `ribbon-bar.md`.
- Snapping engine → `snapping-engine.md`.
- Units / dimension parsing → `units-and-formatting.md`.

## Deferred / follow-ups
- Vertical / elevation-plane anchoring; elevation-view projection; 3D extrude of
  filled 2D profiles; hatch scale control; per-category 2D-geometry line-weight.
- Parametric-polygon polish (explode → editable polyline; "Sides" as a HUD COUNT
  field); Line+Polyline single ←/→ cycle tool (retire the `K` placeholder).
