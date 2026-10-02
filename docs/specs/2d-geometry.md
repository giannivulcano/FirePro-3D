---
title: 2D Geometry System
status: current
applies-to:
  - firepro3d/geometry_2d.py
  - firepro3d/arc_math.py      # pure arc construction (End Points placement + arc grips)
  - firepro3d/geometry_intersect.py   # item-agnostic intersection math (scene tools, snap, roof consume it)
  - firepro3d/cad_math.py      # item-agnostic point/vector math (rotate/mirror/scale/project); app-wide consumers
  - firepro3d/geometry_drawing_controller.py   # 2D-geometry placement handlers
  - firepro3d/model_space.py   # 2D-geometry placement + dispatch tables only
  - firepro3d/selection_readouts.py   # DimSpec (primitive side, §8); controller governed by selection-mode.md §15
last-verified: 2026-10-02  # arc CW-toggle Account: §4 Center/Start Space CCW<->CW (_draw_arc_cw, _arc_span_to; HUD Span unsigned); prior CS1 Account: primitive uid (mixin field + to_dict stamp); size-floor constants CIRCLE_MIN_RADIUS / ARC_MIN_RADIUS / RECT_MIN_SIZE (one home, read by the constraint solver); D23 reference-line scaffolding verified; prior 2026-10-01
verified-commit: 467b62e   # arc CW-toggle (Center/Start Space flip); prior 2a22ba9 CS1 constraint foundation (feat/cs1-constraint-foundation); prior c8ff4f4 scene-tools P1 batch Account: §1.2 per-item reflect/scale (DD1), §3.5.2 periodic closed spline (DD7), §4 close_hit + shared close ring built (DD8); prior 4c48685 (Arc Span panel cap), dbeb8b6 (sec.4 either-point rule ratified), 892cf76, 762d083
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
| `RectangleItem` | `QGraphicsRectItem` | axis-aligned local rect + rotation as data (`_angle`/`_pivot`); every consumer must honour it — `mapToScene`/`mapFromScene`/`mapToParent`/`mapRectToScene` are overridden, and block compile / explode / offset go through the rotated corners; Flip / Mirror / Scale go through the per-item `manip_reflect` / `manip_scale_about` (§1.2) |
| `CircleItem` | `QGraphicsEllipseItem` | centre + radius |
| `ArcItem` | `QGraphicsPathItem` | centre + radius + start/span (stored CCW, span > 0) |
| `RegularPolygonItem` | `QGraphicsPathItem` | **parametric** regular N-gon |
| `EllipseItem` | `QGraphicsPathItem` | centre + rx/ry + **Y-up rotation** |
| `SplineItem` | `QGraphicsPathItem` | **NURBS / B-spline** (control pts + degree + knots + weights), or a smooth **periodic closed** uniform cubic (`closed=True`, §3.5.2) |

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
  during the render pass) AND from a block's rendered/exploded output — it is
  still **saved** in the block definition as scaffolding and re-seeded on reopen
  (parametric-constraint-system.md D23; `block_definition.is_scaffold` gates the
  compile and `block_explode`); `printed=True` → plots dashed at the "Reference
  Lines" paper weight + renders in the block. Edited via a **`ToggleSwitch`** ("toggle" property-field type).
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
- `_uid` — stable primitive id (uuid4 hex, CS1 2026-10-02): minted at construction,
  stamped as `"uid"` by `_geom2d_to_dict`, carried by `_geom2d_from_dict` when present (a
  legacy dict keeps the constructor's fresh one). Copy / mint / carry rules + why (constraint
  references) are owned by `parametric-constraint-system.md` §6.1 — Rule A. (`TextItem`
  inherits the field but stamps it in its own `to_dict` / `from_dict`; `BlockInstance`
  carries it outside the mixin.)
- **New-geometry pen (2026-09-23, block polish):** `Model_Space._geom_color_lw()` returns
  `constants.DEFAULT_GEOMETRY_LINEWEIGHT` (was a hard-coded 2.0) — the weight for every committed
  tool-drawn primitive **and** Block-Editor-imported ones (`geom_dicts_to_primitives(...,
  lineweight=)`). Placement ghosts keep their own preview pens (§3.6).

### 1.2 Per-item reflect / scale (scene-tools P1 batch DD1, as-built 2026-10-01)

Each of the **eight** `geometry_2d.py` primitive classes (`LineItem` — inherited by
`ReferenceLineItem` — `PolylineItem`, `RectangleItem`, `CircleItem`, `ArcItem`,
`RegularPolygonItem`, `EllipseItem`, `SplineItem`) defines two baked, in-place transforms:

- **`manip_reflect(p1, p2)`** — mirror across the **infinite** line through `p1`–`p2`;
- **`manip_scale_about(base, factor)`** — uniform scale about `base`.

They are the only primitive-side hooks of the Flip / Mirror / Scale tools; the tools select
targets by `hasattr` capability, so `TextItem`, block instances and non-2D items are skipped
(tool behaviour, refusals and undo are owned by `scene-tools.md` — Rule A). The methods only
mutate geometry (`setPath`/`setLine`/`setRect` + `set_angle`); manipulator rebake, reselect and
the undo push are the caller's duty. Both hooks change geometry only: style (colour,
lineweight, fill, RefLine `printed` / dash) is never touched, so **lineweights never scale**.
The scale hook is deliberately **not** named `manip_scale`:
that name makes the selection manipulator treat an item as box-resizable
(`item_capabilities`, `selection-manipulator.md`).

| Primitive | `manip_reflect` (θ = the axis' Y-up heading, `arc_math.yup_angle`) | `manip_scale_about` |
|---|---|---|
| Line / RefLine, Polyline | every point mirrored; RefLine keeps type / `printed` / dashed pen; the polyline `_closed` flag + fill are kept | every point scaled |
| Rectangle | origin mirrored; angle → `2θ − angle`, **folded into [0°, 180°)**; the local rect is flipped top-for-bottom, or left-for-right when the heading is folded by 180° (same footprint) — an axis-aligned rect mirrored across an axis-aligned line stays at angle 0, so the redundant manipulator frame stays suppressed; pivot semantics kept | origin + local rect scaled; angle + pivot semantics kept |
| Circle | centre mirrored; radius kept | centre scaled; radius × factor via `set_radius` (**1 mm floor**) |
| Arc | centre mirrored; reflection reverses orientation, so the old end becomes the new start: start → `2θ − (start + span)`, **span kept** (stored CCW, span > 0) | centre scaled; radius × factor (**0.01 mm floor**); angles kept |
| Regular polygon | centre mirrored; rotation → `2θ − rotation` (the circumscribed half-step contributes one full vertex step, so the vertex set is identical for both shapes) | centre scaled; defining radius × factor; sides / rotation / inscribed kept |
| Ellipse | centre mirrored; rotation → `2θ − rotation`; rx / ry kept | centre scaled; rx / ry × factor (**0.5 mm `_AXIS_MIN` floor**); rotation kept |
| Spline | control points only — degree, knots, weights and the periodic `closed` flag untouched | control points only (same) |

- **Degenerate axis = no-op.** `geometry_2d._degenerate_axis(p1, p2)` (axis length² < 1e-12,
  the same threshold `CAD_Math.mirror_point` uses for identity) makes **every**
  `manip_reflect` return unchanged — otherwise the orientation terms (rect / arc / polygon /
  ellipse) would flip while the points stayed put, half-applying the reflection. It is the one
  threshold shared by the axis picker (`axis_picker.py`) and the ghost (`transform_ghost.py`).
- **Floors make tiny factors non-uniform.** The radius floors above (Circle 1 mm, Arc 0.01 mm,
  Ellipse 0.5 mm — module constants `CIRCLE_MIN_RADIUS` / `ARC_MIN_RADIUS` / `_AXIS_MIN`) clamp
  while the centre scales exactly, so a factor small enough to hit a floor no longer yields a
  uniform image (lines / polylines / rects / polygons / splines have no such floor). Known and
  filed (`todo_open.md` "Tiny Scale factors scale non-uniformly"). The constraint solver's D29
  collapse check reads those three plus `RECT_MIN_SIZE`, which floors only its rectangle w/h
  write-back; `_AXIS_MIN` is also borrowed for polygon R, which the item itself never clamps.
- Like `manip_rotate`/`translate`, both hooks transform local data with scene-space
  arguments — they assume the primitive's `pos()` is the origin (shared pre-existing
  assumption).

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
- Consumers that copy a polyline (offset `tool_geometry.offset_item`,
  `update_preview`) forward the flag.

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
- **Periodic closed spline (DD7, as-built 2026-10-01).** `SplineItem(..., *, closed=False)`
  takes a **keyword-only** `closed` flag (`_closed`). It holds only with **≥ 3** control points
  (fewer → stored open) and then forces a **uniform non-rational cubic** (degree 3, `_knots`
  / `_weights` = `None`; the stored degree/knots/weights are ignored). `_bspline_path(...,
  closed=True)` draws it through an **exact periodic Bézier evaluator**
  (`_periodic_bezier_path` / `_periodic_bezier_spans`): span *i* uses control points
  *i..i+3* (wrapped), drawn natively with `cubicTo` and closed — evaluating only the valid
  knot domain is what keeps the seam closed with a continuous (C2) tangent.
  - **Two closed tests.** `is_periodic()` is true only for the smooth periodic flag;
    `is_closed()` is true for a periodic spline **or** the legacy coincident-end (kinked)
    form (≥ 3 control points, first == last), which is otherwise unchanged. Fill /
    `get_closed_path()` / offset follow `is_closed()`; snap uses `is_periodic()` (a
    periodic spline has no end points — `snapping-engine.md §5` owns the per-type snap
    matrix).
  - **Persistence:** `to_dict` writes `"closed": true` **only when set** (open and legacy
    splines serialize byte-identically to before); `from_dict` reads
    `bool(data.get("closed", False))`. Every copy path (undo, paste, block factory,
    `tool_geometry._spline_copy` for offset) carries the flag; grips, translate, rotate,
    reflect and scale never touch it.
  - **Selection guide:** the dashed control-polygon guide (§3.6) also draws the
    last → first leg on a periodic spline, so the guide is a closed loop.
  - **No Closed row** in `get_properties()` yet (the panel shows Degree 3 and no
    open/closed state); a periodic spline cannot be reopened, nor an open one closed, after
    drawing — filed (`todo_open.md` "\"Closed\" property toggle for splines and polylines").
  - `_PERIODIC_WRAP_EPS` (1e-6, wrapped-DXF control-point coincidence) and the underlay
    flatten tolerance (`periodic_spline_polyline(..., distance=0.5)`, matching the ezdxf
    `flattening(0.5)` it replaces) live in `geometry_2d.py` as **algorithmic epsilons** of
    the evaluator, not user-facing constants — recorded here as the one sanctioned exception
    to the `constants.py` rule.
- **Grips:** one per control point (drag → rebuild). No centre grip, no seam pair on a
  periodic spline. Add/remove control point is deferred.
- **Placement:** N-click control polygon (mirrors polyline) — Enter/double-click
  finishes **open**, Delete pops the last point, 1 point cancels; with ≥ 3 points a click
  near the first point commits a **periodic** spline (close gesture and ring: §4). Mode
  `"draw_spline"`, list `_draw_splines`, `type: "draw_spline"`. Closed (fillable) iff
  `is_closed()`: the periodic flag, or the legacy first == last control point rule.

Both register in `block_definition._PRIMITIVE_FACTORY` and thread through the
full dual-path persistence + enumeration set (§6).

### 3.5.3 Curve import-extraction contract (block-editor only)

DXF/DWG/PDF import into the **Block Editor** preserves curves **exactly** as
these editable primitives — no tessellation (2026-09-23, block polish: partial
ellipses and PDF Béziers joined arcs / full ellipses / splines). It is gated by
a `preserve_curves` flag on `DxfImportWorker` **and** `PdfImportWorker` (default
**False**, so the underlay import path keeps its own flattening — byte-identical
except for DD7 closed periodic SPLINEs, below); `BlockImportDialog`
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

**DXF closed SPLINE → periodic (DD7, 2026-10-01).** A closed SPLINE in the wrapped
periodic form — degree 3, the last 3 control points repeating the first 3 (within
`_PERIODIC_WRAP_EPS`), a uniform knot vector of `n + 4` knots, absent or uniform weights —
is recognised by `geometry_2d.periodic_control_points` and maps to its `n − 3` unique
control points:
- Block import (`geometry_import.geom_dicts_to_primitives`) → `SplineItem(unique,
  closed=True)`; the import preview (`dwg_converter.append_geom_to_path`) draws the same
  periodic path.
- Underlay import (flag off) → `dxf_import_worker` flattens via
  `geometry_2d.periodic_spline_polyline` (the same curve, flattened like ezdxf
  `flattening(0.5)`) into one closed `path_points` record. This replaces ezdxf's
  full-knot-range flattening, which drew a stray tail; it is therefore **no longer
  byte-identical** for these splines. The record is curve-derived, never `"straight"`
  (not a Flip/Mirror axis — `underlay-workflow.md` owns the record schema).
- Any other closed SPLINE (non-uniform knots or weights, degree ≠ 3, fit-point) keeps the
  verbatim path and still draws the stray tail — filed (`todo_open.md` "Closed DXF SPLINEs
  with non-uniform knots or weights still draw a stray tail").

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

**Close / pop test point — the shared close helper (ratified 2026-09-26, FP1; built
2026-10-01, DD8).** One module-level test, `geometry_drawing_controller.close_hit(first,
tip, cursor, view_scale)`, decides close-near-first for **polyline, spline, floor-polygon
and roof-polygon** placement (≥ 3 vertices): it fires when **either** the committed point
(the Ctrl-constrained tip; equal to the cursor when unconstrained, and always for the
spline, which has no Ctrl constraint) **or** the snapped cursor is within
`constants.CLOSE_HIT_PX` screen pixels of vertex 0 (converted by the active view zoom). So a
constrained tip that lands on vertex 0 closes instead of adding a near-duplicate vertex,
and snapping onto vertex 0 with Ctrl held still closes. Roof vertex-pop (click near an
existing vertex to remove it) uses the same either-point test against each vertex.
Rejected: committed-tip-only; cursor-only with duplicate suppression. The wall loop close
(tip only, its own tolerance) is a separate rule (`wall-room-floor-system.md §4.4`).
- **The close ring.** While `close_hit` holds, every caller shows **one shared ring**
  (`GeometryDrawingController.show_close_ring` / `hide_close_ring`; a fixed screen-size
  `CLOSE_RING_PX` ring in `SELECTION_OUTLINE_COLOR`, z above the overlay so it is never a
  snap target, stored on the scene as `_polyline_close_indicator` — historic name). The
  ring **stays on vertex 0** whichever point triggered, and the preview closes onto
  vertex 0 (polyline / floor / roof rubber band; the spline preview turns into the smooth
  periodic curve). It is hidden on commit, on a mode switch, on floor/roof Enter-close,
  on a Delete-pop and when a HUD-typed spline point is added.
- **Spline.** With ≥ 3 control points a click within `close_hit` of the first point
  commits a **periodic** spline (§3.5.2); Enter / double-click finish **open**. A
  Delete-pop below 3 points drops the closed cue (`_closed` cleared on the preview,
  ring hidden).
- **Ring lifecycle across New / Open.** `scene_io._clear_scene` forgets the ring
  (`scene.clear()` deletes the item under the stored wrapper); `_live_close_ring()`
  also drops a deleted or foreign-scene ring, so the next `show_close_ring` recreates it
  instead of raising `RuntimeError` (`eb54232`).
- **Not on the helper:** room manual close / click-pop and shift-click floor vertex delete
  still own their own 8 px literals — filed (`todo_open.md` "Room manual close/pop and
  shift-click floor vertex delete keep their own 8 px literals"). Known interactions,
  filed: origin snap can pre-empt the ring when vertex 0 sits 8–12 px from (0, 0); a
  HUD-typed point on vertex 0 closes a floor but adds a near-duplicate vertex on
  polylines and splines.

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
  kept. *Center / Start* sweep **CCW** from the start by default; **Space** at the
  span step toggles **CCW ↔ CW** (2026-10-02; `Model_Space._draw_arc_cw`, reset per
  placement — step-0 click, commit, mode teardown, scene reset). The preview, the
  click commit and the `arc_span` seed all read one signed span,
  `GeometryDrawingController._arc_span_to` (CCW `(0, 360]`, CW `(−360, 0]`); the
  commit hands the signed span to `ArcItem`, which stores it CCW (below). The HUD
  **Span / Arc stay unsigned magnitudes** (the SPAN convention,
  `units-and-formatting.md`): the seed reads `|span|`, and a typed Span sweeps that
  magnitude in the live direction (`_arc_end_point_for_span`). Space before the
  span step cycles nothing. **90° snap (2026-09-24):** for the mouse preview and click commit, when
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
- **`ArcItem` storage is CCW:** a negative (CW) span passed to `__init__` (legacy
  saves; the retired `SceneTools._apply_mirror` produced them — `manip_reflect` keeps the
  span positive, §1.2) is normalised to the same geometric arc with a positive span
  (start += span, span = −span). Grips: centre / start / end — their drag
  semantics (centre: bisector slide; ends: slide along the circle) are owned by
  `selection-manipulator.md` (U3 ArcItem).
- **Placement selection (no accumulation):** every primitive is
  `setSelected(True)` on commit, and the commit **clears the prior selection
  first** so placing several in a row leaves only the last-placed item selected
  (commit sites in `geometry_drawing_controller.py` + the `model_space.py` line
  factory / polyline-finalize paths).
- **Polyline:** multi-click; **click the START vertex (≥3 verts) to close** (the
  shared close ring above cues it on the first vertex); double-click / Enter
  finish *open*; **Delete** pops the last vertex (routed via a `Model_View`
  `ShortcutOverride` accept so it beats the window Delete shortcut; cancels at one
  vertex). Mid-chain clicks and Delete stay in polyline mode; a completed chain
  (close, Enter or double-click) returns to **Select** with the placed item
  selected (single-placement, above). **2-vertex finish → `LineItem`
  (2026-09-24):** an Enter / double-click finish with exactly 2 vertices commits a
  `LineItem` instead of a 2-point polyline, because a single segment is a line.
  Colour, lineweight and per-instance display overrides (`_display_overrides`)
  carry over; a fill is dropped. It is one undo step (`Model_Space._finish_polyline`,
  shared by Enter and double-click). This applies only to **placement**: loaded
  files, paste and blocks keep their 2-point polylines.
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
reads an axis-aligned rect and would emit *wrong* quadrants for a
rotated ellipse). **SplineItem** emits its **endpoints + control points** (as
endpoint-class snaps) via its own branch before the generic path branch — none for a
periodic spline (`is_periodic()`, §3.5.2), whose snaps come from its path only.

The per-item snap contribution of every primitive — including ellipse/spline
perpendicular/nearest (projected onto the flattened curve, 2026-09-24), the
approximate curve intersections, and **Text** (frame-box points) — is owned by
[`snapping-engine.md §5`](snapping-engine.md#5-item-type-snap-type-matrix) (Rule A:
not restated here).

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
for all the 2D-geometry item types (mirrors Design Area; no per-category line-weight yet).
Fill is a per-item property, independent of the category.

## 8. Selection dimension readouts (as-built 2026-09-24, `feat/selection-dim-readouts`)

> Design record: `docs/superpowers/specs/2026-09-24-selection-dimension-readouts-design.md`.
> Pick precedence, hover/press routing and input mode are owned by `selection-mode.md §15`.
> This section owns the **primitive side**: what each primitive reports and how its typed setters
> anchor.

**Contract.** Every primitive exposes a pure `dimension_specs() -> list[DimSpec]`
(`selection_readouts.py`). `Geometry2DMixin` defaults it to `[]`. A spec is data only. The
primitive never owns, parents or paints a readout. So readouts are outside `shape()`, bounding
rects, snap, serialization and copy/paste by construction. `DimSpec.apply(v)` calls one of the
named setters below. The setters are pure mutation, with no undo; undo is owned by the caller.
They are the **single** mutation path shared by the readout HUD and the property-panel rows.

| Primitive | Readouts (`field` / prefix) | Typed setter + anchor | Floor / range |
|---|---|---|---|
| `LineItem` (incl. `ReferenceLineItem`) | Length | `set_length` — keeps `pt1`, moves `pt2` along the direction | > 0 |
| `RectangleItem` | Width (local x), Height (local y); labels outside the local bottom / right edges | `set_width` / `set_height` — keep the left / bottom edge (local frame) | > 0 |
| `CircleItem` | R (single radial, centre → local +x) | `set_radius` — keeps the centre | ≥ 1 mm |
| `ArcItem` | Angle (included span, on a dashed reference arc between the radials) + R (start radial) | `set_span` — keeps centre / radius / start, end moves CCW; `set_radius` — keeps centre + angles | 0 < span < 360; r ≥ 0.01 mm |
| `EllipseItem` | R1 (= rx axis), R2 (= ry axis); no major/minor naming | existing rx / ry setters — keep centre + rotation | ≥ 0.5 mm |
| `PolylineItem` | Seg *i* length; Angle *i* at interior vertices on the ≤180° side. Closed: the closing segment + every vertex, with wraparound. Zero-length segments give no length and no angle at their vertices | `set_segment_length(i)` / `set_vertex_angle(i)` — move only the segment's end vertex (angle: rotate vertex *i+1* about *i*) | length > 0; 0 < angle ≤ 180 |
| `RegularPolygonItem` | R = the stored **defining** radius, along the matching radial (vertex if inscribed, edge-mid if circumscribed) | existing radius setter — keeps centre / sides / rotation | existing |
| `TextItem`, `SplineItem` | none | — | — |

**As-built invariants (2026-09-24):**
- Every typed setter ignores non-finite input (`math.isfinite` guard) and polyline setters ignore out-of-range indices — they run under paint-driven code and must never raise or corrupt geometry. `dimension_specs()` drops non-finite and degenerate specs (zero-length segments, zero rect sides, doubled-back polyline vertices).
- `DimSpec.minimum` sits just below each setter's floor, so the readout editor and the panel **reject** below-floor input rather than silently clamping (floors stay as a backstop).
- Y-up helpers reuse `arc_math.point_at` / `arc_math.yup_angle` (no per-class copies).

No rotation-angle readouts (rect / ellipse / polygon). **Panel fold-in:**
- Line Length, Rect Width/Height, Circle Radius and Arc Radius/Span become editable
  unit-formatted dimension rows (Span is angle-typed), routed to the same setters.
  The Span row carries `maximum = 360 − 1e-6` (property-panel §3.8), so an entry
  ≥ 360 reverts in the field (2026-09-29).
- The ellipse rows are relabelled `R1` / `R2`.
- Panel dimension edits go through `Geometry2DMixin._dim_edit`: no undo step when nothing changed; otherwise `_push_undo` → `Model_Space.request_undo_push`, so a multi-target panel commit (inside `deferred_undo_push()`) is **one** undo step. Circle/Arc radius rows carry the setter floor as `minimum`.

## Cross-references (Rule A — these own the linked facts)
- **Level / elevation / Z-order model** (now on the placed Block instance, not the primitive) →
  `block-system.md` (BlockInstance level scope) + `view-relationships.md §7.3` + `constants.py`.
- **Containment invariants** (placement-only, level-on-instance, Text primitive) →
  `model-space-containment-contract.md` C1/C3/C5/C7.
- Ribbon topology (Create dissolved; Block-Editor/Paper authoring contexts) → `ribbon-bar.md`.
- Flip / Mirror / Scale tool behaviour (targets, axis picking, ghosts, refusals, undo) →
  `scene-tools.md` (this spec owns only the per-item hooks, §1.2).
- Snapping engine → `snapping-engine.md`.
- Units / dimension parsing → `units-and-formatting.md`.

## Deferred / follow-ups
- Vertical / elevation-plane anchoring; elevation-view projection; 3D extrude of
  filled 2D profiles; hatch scale control; per-category 2D-geometry line-weight.
- Parametric-polygon polish (explode → editable polyline; "Sides" as a HUD COUNT
  field); Line+Polyline single ←/→ cycle tool (retire the `K` placeholder).
