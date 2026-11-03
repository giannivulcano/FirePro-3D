---
status: approved
date: 2026-11-03
governing-specs: [docs/specs/linetypes.md, docs/specs/2d-geometry.md, docs/specs/block-system.md]
source-tasks: ["Loose line overshoots its endpoints by half the line weight (square pen cap)"]
---

# Stroke corner joins — flat free ends, mitered vertices, cross-item joints

## Goal

A free stroke end stops flat at its endpoint; every vertex inside one item is a sharp
miter (bevelled past ~29°); two coincident ends of separate open strokes in the same
container meet in the same sharp corner — on the model canvas, inside placed blocks and the
Block Editor, and on sheets / PDF / print.

## Motivation

Qt's default `QPen` is SquareCap + BevelJoin and no FirePro3D stroke pen sets either, so a
6 px line paints 3 px past each endpoint and three Lines forming a triangle show overlapping
square caps at every corner (user screenshot 2026-11-03; task line filed 2026-10-23 at the
SB1c smoke). A closed `PolylineItem` triangle is not sharp either: BevelJoin clips the apex,
and the crisp H/V axis split (`linetypes.md` MW-7) breaks a mixed path into capped runs and
stamps round joint dots where a horizontal base meets a diagonal side.

## Acceptance criteria (ratified FP1, 2026-11-03)

- **AC1** A free end stops flat at its endpoint.
- **AC2** Every vertex inside one item (polyline, rect, polygon, a closed seam) is a sharp
  miter; the crisp split never caps or dots over it.
- **AC3** Two coincident ends (within `CHAIN_WELD_MM`) of separate open strokes — lines,
  polyline ends, arcs, splines, open ellipse arcs — miter along their end tangents.
- **AC4** Only a clean pair joins: exactly two ends at the point, same weight name and same
  colour string. Three or more ends, or mixed weight / colour, draw each end flat.
- **AC5** Miter limit = PDF ratio 4 (miter length / width, ≈ 29°); beyond it the tip is
  bevelled. (P4 probe: Qt's `setMiterLimit` measures the tip's reach *from the join point*
  in pen widths, so PDF 4 == **Qt 2**, Qt's default; a 20° corner with a 20 px pen is clipped
  at 40 px under Qt 2 and passes at Qt 4.)
- **AC6** A dashed / patterned stroke joins only when its end is inked at the corner (the
  first / last expanded dash covers the endpoint); a gap there draws flat. An end carrying an
  end type (arrow, tick, …) never joins.
- **AC7** Joins stay within one container: the loose model geometry, one block definition
  (Block Editor + every placed instance), one sheet. A loose line touching a placed block's
  line draws flat.
- **AC8** All of the above hold on the model canvas, inside placed blocks and on sheets /
  PDF / print.

## Architecture & constraints

Every stroke is a per-item (or per-block-op) `QPen` + `drawPath` through three routes:
`Geometry2DMixin._paint_base_stroke` (Continuous — the crisp split, or the one-segment
`LineItem` fast path), `linetype_render.paint_stroke` (dashed; dashes already FlatCap, dots
RoundCap) and `BlockInstance.paint` (`QPen(op.pen)` per op, then the same two routes).
Paper passes swap non-cosmetic mm pens in (`paper_display._apply_construction`) and draw
through the same code. Qt cannot miter across two `drawPath` calls, so the work splits in
two: **pen properties** (AC1, AC2, AC5) and **joint patches** (AC2 at split junctions; AC3,
AC4, AC6, AC7 across items). Chosen over merging coincident strokes into one painted path
(takes painting away from the items: highlight, Display Manager colour, tint, paper pens,
hit-testing) and over a per-container overlay item (re-derives every stroke's pen outside
the item and has to sit at the right z).

Out of scope (own pens, unchanged): pipes, walls, HALO, constraint paint, snap markers,
section views, DXF import pens, the Offset / Join / Fillet tool geometry (they miter their
own math already).

## Design decisions

- **D1 Stroke pen factory.** `stroke_style.stroke_pen(colour, width_px, cosmetic=True) ->
  QPen`: FlatCap, MiterJoin, `setMiterLimit(STROKE_MITER_LIMIT / 2)` with
  `constants.STROKE_MITER_LIMIT = 4.0` (the PDF ratio; the Qt value is derived, never a
  second constant). Callers: `Geometry2DMixin._init_stroke`, `_reference_pen`,
  `_sync_stroke_pen` (re-asserts cap / join with the width, so a pen a paper pass left
  behind is normalised), the block op compile in `block_definition.py` (`op.pen`, both the
  primitive-copy sites), `paper_display._apply_construction`. Selection-highlight pens copy
  the stroke pen's cap / join. `linetype_render` keeps its own dash / dot caps.
- **D2 Joint wedge helper.** New `firepro3d/stroke_joints.py`:
  `joint_wedge(corner, d_a, d_b, half_w, limit=STROKE_MITER_LIMIT) -> QPolygonF | None`.
  `d_a`, `d_b` are unit directions *away* from the corner. Returns the outer wedge (corner,
  outer edge of A at its flat end, miter tip, outer edge of B); past the limit the tip is
  replaced by the bevel chord; `None` when the strokes are collinear (nothing to fill) or
  overlap (reversed / parallel). Pure math, no Qt painter.
- **D3 Crisp-split junctions (AC2).** `crisp_stroke.split_axis` records each axis↔other
  junction as `(point, d_in, d_out)` (`CrispSplit.joints`; `joint_points` retired, its
  one reader rewritten). `crisp_stroke.stroke` fills a `joint_wedge` per junction with the
  pen colour instead of the round dots: cosmetic pens in **device space** (`half_w =
  pen.widthF() / 2`, corner and directions mapped through `worldTransform`, drawn under an
  identity transform, the painter's own AA hint). Closed single-class loops stay one closed
  subpath (mitered by D1). Paper passes and non-cosmetic pens already draw unsplit and get
  D1's MiterJoin. The `LineItem` fast path is unchanged.
- **D4 JointIndex (AC3, AC4, AC6).** `stroke_joints.JointIndex`: `register(key, ends)` /
  `unregister(key)` / `partner(point, tangent, weight, colour) -> JointPartner | None`.
  Storage: dict keyed on the point quantised to a `CHAIN_WELD_MM` grid; `partner` scans the
  3×3 neighbourhood and matches on exact distance ≤ `CHAIN_WELD_MM`. A match needs exactly
  two entries at the point, both `inked`, same weight name, same colour string, neither
  carrying an end type. An end record is `(point, tangent_away, weight, colour, inked,
  has_end_type)`; closed shapes register nothing. End data come from `stroke_pieces()`'s
  first / last piece (lines, polylines, arcs, splines, ellipse arcs); `inked` for a dashed
  stroke is a new `linetype_render.end_inked(pieces, lt, factor, anchor, fixed, trims)`
  over the existing `expand(trims=)` (Continuous = True).
- **D5 Containers (AC7).** (a) `Model_Space.stroke_joints` for loose styled items; (b) one
  index per `BlockDefinition`, compiled with its ops (static; recompiled whenever the ops
  are); (c) one per sheet on `paper_space` for paper-space geometry. A placed instance asks
  its definition's index with op-local coordinates; a loose item asks its scene's; the
  Block Editor scene is container (a) for the definition being edited.
- **D6 Index maintenance.** Geometry changes have no existing choke point (the stroke
  caches are keyed by value, `itemChange` does not see `setLine` / `setPath`). D6 adds one:
  `Geometry2DMixin._stroke_geometry_changed()`, called at every `prepareGeometryChange`
  site in `geometry_2d.py` (12 today — the plan's first step enumerates them and any
  external `setLine` / `setRect` / `setPath` caller) and from `itemChange` on
  `ItemSceneHasChanged` (register / unregister). It re-registers the item's ends and calls
  `update()` on the former and new partners, so a moved line's old partner repaints flat in
  the same frame. Undo / load / paste go through the same setters or `addItem`.
- **D7 Paint.** `_paint_routed_stroke` (and `BlockInstance`'s op loop) asks the container
  index once per end per paint and fills the wedge with the stroke's **painter-local pen**
  colour (tint, Display Manager colour, paper pen, selection accent are already on it):
  device space for cosmetic pens, scene space for paper pens. The selection highlight draws
  its own wedge when shown. A missing container (item not in a scene, ghost pens,
  reference items — RG4) skips joints.
- **D8 Performance.** Register / unregister are O(1) per end; paint adds two dict lookups
  per styled open item. Bench before any optimisation (Phase 5 Performance rule): (1) 2 000
  loose lines, pan / zoom repaint; (2) drag one line in that scene. Budget: no measurable
  regression over base — a > 5 % frame-time increase on either fails.

## Plan-time deviations (ratified at plan approval, 2026-11-03)

Grounding for the plan (`docs/superpowers/plans/2026-11-03-stroke-corner-joins.md`,
local) found four places the decisions above do not fit the code; each was put to the
user and ratified as written here. Account reconciles the D-rows at Phase 6.

- **D4 — end records store geometry only.** `JointEnd = (point, tangent_away, which,
  owner)`. Weight, colour, `inked` and end type are matched **at paint**
  (`stroke_joints.joinable`) from both owners' live state: there is no style-change choke
  point to keep stored attributes current, and `inked` for a Fixed linetype depends on the
  paint's device scale. AC4 / AC6 semantics unchanged.
- **D5(c) dropped.** `PaperScene` hosts only `TextItem`s, viewports and the title block;
  sheets show model geometry through viewports, i.e. the paper pass over `Model_Space`
  (container (a)). AC8's sheet / PDF leg is container (a) under a paper pass.
- **D6 — choke point = setter overrides.** `LineItem` never calls `prepareGeometryChange`
  (Qt's `setLine` does it internally). `Geometry2DMixin` overrides `setLine` / `setRect` /
  `setPath` (Python-level calls dispatch to the mixin, which precedes the Qt base in the
  MRO) and handles `ItemSceneChange` / `ItemSceneHasChanged` (+ position / transform /
  rotation changes when any caller moves a styled primitive that way) in `itemChange`.
- **D7 — both partners draw the shared wedge** (same colour and width → identical
  polygon; keeps either item's repaint self-sufficient), and open styled items pad
  `boundingRect` by `STROKE_MITER_LIMIT / 2` pen widths (the miter tip's reach);
  `BlockInstance.boundingRect` pads by the same reach at `MODEL_WEIGHT_PX_MAX` when its
  definition holds any joint.

## Verification checklist

Each guard renders to a `QImage` at an exaggerated weight (e.g. `canvas_px` patched to 20)
and is shown RED at base `c20d2ec3`:

1. Lone line: dark-pixel extent equals the endpoints (AC1).
2. Three `LineItem`s forming a 60° triangle, and a closed `PolylineItem` triangle: no dark
   pixel outside the mitered-outline oracle (`QPainterPathStroker`, MiterJoin, Qt limit 2)
   and none missing inside (AC2, AC3).
3. Three ends at one point (a star): every end flat (AC4). Two weights at a corner: flat.
4. A 20° sliver: the tip is bevelled — no dark pixel beyond the bevel chord (AC5).
5. A dashed corner whose end lands in a gap: flat; one whose dash reaches the corner: sharp
   (AC6). A line with an Arrow end: no wedge (AC6).
6. The 3-Line triangle inside a placed block instance, in a Block Editor scene, and on a
   sheet exported through `QPdfWriter` + PyMuPDF pixel check (AC7, AC8). A loose line
   touching a block's line: flat (AC7).
7. Move one triangle side away → both former partners flat; undo → sharp (D6).
8. `joint_wedge` unit table: 90°, 60°, 29° ± 1°, 20°, 180° (None), 0° (None).
9. Bench D8 at base and HEAD, interleaved pairs, raw lines to a file.
