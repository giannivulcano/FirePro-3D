---
status: built             # designed + approved 2026-10-01; BUILT 2026-10-01 on feat/scene-tools-p1-batch (7766316..c8ff4f4); folded into the governing specs at Account — this file is archival (see "As-built / execution amendments")
last-verified: 2026-10-01
verified-commit: c8ff4f4   # account; prior 7766316 (design)
applies-to:
  - firepro3d/modify_tools_controller.py
  - firepro3d/geometry_2d.py
  - firepro3d/axis_picker.py            # new
  - firepro3d/transform_ghost.py
  - firepro3d/dynamic_input.py
  - firepro3d/placement_input_coordinator.py
  - firepro3d/snap_engine.py
  - firepro3d/handle_snap.py
  - firepro3d/geometry_drawing_controller.py
  - firepro3d/geometry_import.py
  - firepro3d/dwg_converter.py          # as-built: DXF periodic-spline mapping (import preview)
  - firepro3d/dxf_import_worker.py      # as-built: underlay "straight" tag + periodic flattening
  - firepro3d/pdf_import_worker.py      # as-built: underlay "straight" tag
  - firepro3d/scale_manager.py          # as-built: format_factor / parse_factor
  - firepro3d/constants.py              # as-built: ARRAY_DEFAULT_MEMORY, ARRAY_GHOST_FULL_MAX, CLOSE_HIT_PX, CLOSE_RING_PX
  - firepro3d/scene_tools.py
  - firepro3d/tool_geometry.py
  - firepro3d/geometry_intersect.py
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/entity_context_menu.py
  - main.py
source-tasks:
  - "Array: reference angle + 2D (rows×cols) mode with ←/→ variant cycle; polar [P1]"
  - "Mirror + Scale scene tools [P1]"
  - "Block Editor origin isn't a reliable snap target [P1]"
  - "Create closed splines [P1]"
  - "Arc angle convention bug [P2]"
  - "One snap-target eligibility filter for find() and HandleSnapSession [P3]"
  - "Modify-tool polish [P3]"
---

# Scene-tools P1 batch — Design Spec

> Batch design doc for one /todo run (feature/Large). It is a **build
> contract**, not a new subsystem spec: on landing, each part is folded into its
> governing spec in place (Rule A) — `scene-tools.md` (M1, M2, M3, M6, M8),
> `snapping-engine.md` + `selection-manipulator.md` (M4, M7), `2d-geometry.md`
> (M5) — and this file is archived. Where this file and a governing spec
> disagree after landing, the governing spec wins.

## Goal

Make the Block Editor's modify toolset complete and correct for the next
drafting milestone: a richer Array (angle lock, 2D, polar), two mirror tools
(Flip in place, Mirror as copy), a Scale tool, a dependable origin snap,
smooth closed splines, correct arc handling in every geometry tool, one snap
eligibility rule, and three small modify-tool polish fixes.

## Motivation

The 2026-09-26 scene-tools milestone surfaced Copy/Cut/Paste/Duplicate/Move/
Rotate/Offset/linear Array but left Mirror and Scale unreachable and dead
(`scene-tools.md` DV10, DV11), the arc angle convention wrong in every
arc-aware tool (DV7), and the D10 Array without the angle / 2D / polar
variants the user asked for at the 2026-09-29 smoke. The user also found the
origin snap unreliable (handle drags never snap to it; cursor snap hits it
only by accident through the cross-arms intersection) and needs closed
splines, which the draw tool cannot make.

## Ratified "what" (Phase 2 grill, 2026-10-01 — locked)

The full ratified definition (23 decisions) is recorded in the /todo session
and summarised per member below; the design that follows implements it.

- **M1 Array** — ←/→ variants at step 0: Linear → 2D → Polar. Linear HUD
  Angle · Spacing · Count; a typed Angle **locks the direction**, cursor then
  sets spacing only. 2D: cursor = diagonal corner of the first cell; columns
  along Angle, rows along Angle+90° (CCW, Y-up); HUD Angle · Col spacing ·
  Cols · Row spacing · Rows (totals incl. original). Polar: centre pick →
  cursor sweep sets Total angle → HUD Count · Total (Count incl. original;
  360° = even fill); copies rotate with the pattern. Variant + typed values
  sticky (per canvas tab, this session).
- **M2 Flip (Shift+F) + Mirror (Shift+I)** — Flip transforms the selection in
  place; Mirror adds mirrored copies. Select-first → "Pick mirror axis" →
  hover detects the nearest **existing straight segment** (any visible: 2D
  edges, reference lines, gridlines, walls, underlays, incl. the selection's
  own edges); no two-point fallback; no snap glyph; an infinite accent
  dash-dot axis + a HALO glow on the **single** source segment + the ghost →
  click / Enter commits. No HUD. Text and block instances skipped (status
  count). One commit → Select (Flip: originals; Mirror: copies).
- **M3 Scale (Shift+S)** — base → reference point (= 1×) → cursor sets the new
  distance (ghost) → click; or type Factor after the base. Uniform, in place;
  Text and blocks skipped; factor ≤ 0 or ref = base refused.
- **M4 Origin snap** — origin is a target for cursor **and** handle snap, in
  every scene: the (0,0) cross always + the Block Editor red insertion marker
  when shown. Own kind `origin`, ⊕ glyph, F3-gated only, outranks endpoint.
  The accidental cross-arms intersection hit is removed.
- **M5 Closed splines** — **smooth periodic**. Close by clicking within 8 px of
  point 1 (≥3 points, ring shown) via one shared close helper (spline,
  polyline, floor, roof — lands the ratified either-point rule). Enter /
  double-click finish open. Saved coincident-end splines stay kinked; DXF
  closed SPLINEs import periodic. One grip per control point; stays closed on
  drag; no reopen (follow-up); no endpoint snaps; offset as a closed shape.
- **M6 Arc angle bug** — fix all 14 in-scope sites (trim, extend, break,
  break-at-point, fillet, mirror, `line_arc_intersections`). *(As built: 13
  live sites fixed; the 14th — the mirror arc branch — was retired with
  `_apply_mirror`, see DD9.)*
- **M7 Shared snap filter** — one eligibility rule for `find()` phase 1, phase
  4 and `HandleSnapSession`; children of non-underlay parents (gridline
  bubbles/labels, sprinkler & fitting symbols) are skipped everywhere.
- **M8 Polish** — badge shows the friendly tool name for every mode; Cut
  lights its own button; right-click Copy starts the base pick and Cut is
  added beside it in both context menus.

## Architecture & Constraints

- **Behaviour home** for modify tools is `ModifyToolsController` (owns no
  state; transient state scene-side; dispatch shells on `Model_Space`) —
  `scene-tools.md` I1 / `model-space-architecture.md` §5.3.
- **Per-item transform protocol** (`selection-manipulator.md`): every 2D
  primitive already has `manip_rotate(angle, pivot)`; this batch adds
  `manip_reflect` and `manip_scale_about` beside it. The name `manip_scale` is
  forbidden for them — it enables manipulator resize handles
  (`test_rect_grips_unified.py` guards this).
- **Angles**: scene Y-down mm; user-facing and stored arc/ellipse/polygon
  angles are Y-up CCW+ (`project_rotation_conventions_yup_vs_qt`); the single
  home for Y-up angle math is `arc_math` (`yup_angle`, `point_at`) per
  `2d-geometry.md`.
- **Snapping contract**: `snapping-engine.md` §3 rejects contextual
  snap-by-tool — so the Flip/Mirror axis pick is a dedicated picker with
  cursor snap off, not a snap filter.
- **Containment C1**: all new tools live on the Block Editor tab (D1); plan
  scene = milestone 2.
- **Serialization**: both paths (`project_dual_serialization_paths`) + the
  block primitive factory.
- Mockup gates: new icons (D12 family) and the ⊕ glyph colour are verified
  live under the app QSS before being accepted (`feedback_mockup_name_qt_constraints`).

## Design Decisions

Each approach decision was presented with alternatives and approved in the
2026-10-01 brainstorm. **Status: DD1–DD11 BUILT 2026-10-01 (`c8ff4f4`)** —
deviations in "As-built / execution amendments" below.

### DD1 Per-item transforms (approved: per-item methods)
`manip_reflect(p1, p2)` and `manip_scale_about(base, f)` on the eight
primitive classes in `geometry_2d.py` (Line — inherited by ReferenceLine —
Polyline, Rect, Circle, Arc, RegularPolygon, Ellipse, Spline). Text and
BlockInstance do **not** define them, so the tools skip them by capability.
θ = `arc_math.yup_angle(p1, p2)`:

| Primitive | `manip_reflect` | `manip_scale_about` |
|---|---|---|
| Line / RefLine | reflect endpoints (type kept) | scale endpoints |
| Polyline | reflect vertices; closed + fill kept | scale vertices |
| Rect | centre reflected; angle → 2θ − angle | centre scaled; w, h × f |
| Circle | centre reflected | centre scaled; r × f |
| Arc | centre reflected; start → 2θ − (start + span), span kept | centre scaled; r × f |
| Ellipse | centre reflected; rotation → 2θ − rotation | centre scaled; rx, ry × f |
| RegularPolygon | centre reflected; rotation → 2θ − rotation | centre scaled; radius × f |
| Spline | reflect control points; degree/knots/weights/closed kept | scale control points |

Style (colour, lineweight, fill) untouched; lineweights never scale.
Rejected: one `tool_geometry` isinstance chain (subclass-ordering hazard,
DV14); dict round-trip transform (breaks item identity).

### DD2 Axis picker (approved: bespoke component)
New `firepro3d/axis_picker.py`: `pick_axis(scene, cursor, tol, exclude=None)
-> AxisPick | None` — nearest **straight** segment within tolerance (tolerance
from the **active** view, not `views()[0]`), returning the segment, its source
item and the infinite line. Reads `SnapEngine._iter_geometry_segments` (covers
2D geometry, gridlines, walls, underlays via the snap index) and drops curve
segments. Pure; no scene state. Reusable later for Trim cutting-edge / Extend
boundary picks. Rejected: a per-tool cursor-snap filter (violates §3).

### DD3 Axis hover look (approved: B, single-segment glow)
`transform_ghost.py` paints: infinite axis (accent, centre-line dash-dot,
cosmetic 1 px) + HALO glow traced on the **single source segment** (not the
whole parent shape) + the standard D11 ghost (cached paths under a reflection
`QTransform`). Originals dimmed to 35 % for both Flip and Mirror.

### DD4 Flip / Mirror / Scale flows
- **Flip / Mirror**: `start()` gate (selection; ≥1 item with `manip_reflect`,
  else the shared `nothing_to_hint` status — as built "Nothing to flip — only
  2D drafting geometry can be flipped"; the designed "text and blocks are
  skipped" wording named the wrong reason for plan-scene pipes / nodes /
  walls). Axis step: cursor
  snap + ALIGN off; each move → `pick_axis` → scene-side axis state → paint.
  Click/Enter with an axis → Flip: `manip_reflect` on originals; Mirror:
  `to_dict` → `_add_from_dict` → `manip_reflect` on the copies → one
  `push_undo_state` → Select with D3 selection; status "n skipped" when
  applicable. Click with no axis → "Pick a straight edge or reference line".
- **Scale**: mode `scale`, steps base (snap/ALIGN) → reference (snap; = base
  refused) → cursor (factor = |cursor − base| / |ref − base|, ghost under a
  scale `QTransform`) → click. HUD after base: new schema `scale_factor`, one
  Factor field; typed + Enter commits; ≤ 0 → `reject_commit()`.
- Registries (VC5): `_TOOL_MODE`, `DIM_ORIGINAL_TOOLS`,
  `CANCEL_ON_UNDO_MODES`, the `Model_Space` dispatch shells /
  `_SCHEMA_FOR_MODE` / `_APPLIER_FOR_MODE`, `_initial_steps`, the window
  shortcut table, `_be_modify_buttons` / `mode_registry`.
- **Retired**: `SceneTools._apply_mirror`, `_apply_scale`, the legacy
  `mirror`/`scale` mode handling and `confirmRequested("mirror_delete")`, with
  coupled tests.

### DD5 Array variants
- `_PLACEMENT_VARIANTS["array"]` = Linear / 2D / Polar (sets
  `scene._array_variant`); `_at_placement_step_zero` gains an `array` branch
  (true only before the base/centre pick).
- Schemas (anchored): `array_linear` gains **Angle** (`FieldKind.ANGLE`)
  before Spacing · Count; new `array_grid` (Angle · Col spacing · Cols · Row
  spacing · Rows); new `array_polar` (Count · Total as `FieldKind.SPAN`).
- Angle lock mirrors Offset's sticky distance: typed Angle →
  `s._array_angle_locked`; cursor offset projected onto the locked direction
  (Linear) or locked axis pair (2D); empty / 0 releases.
- Geometry: Linear offsets k·sp·û (k = 1..N−1); 2D offsets c·colSp·û +
  r·rowSp·v̂, v̂ = û rotated +90° CCW (Y-up), (r, c) ≠ (0, 0); Polar poses
  k·step about the centre, step = Total/N at 360°, Total/(N−1) otherwise,
  applied with `manip_rotate` (Rotate's loop) — items lacking it skipped with
  a count. Commit, ghost (one cached path set, one `QTransform` per copy),
  undo and Select behaviour unchanged.
- Memory scene-side beside `_offset_sticky`: `_array_variant`,
  `_array_memory` (last typed fields per variant), `_array_angle_locked`;
  `_array_count_default` folds into `_array_memory`. Scope = per canvas tab,
  this session (same as Offset).

### DD6 Shared snap eligibility + origin source (approved: A)
- `snap_engine.is_snap_target(item, *, skip_pipes) -> bool`: False for hidden,
  z > 150, tags `origin` / `block_origin_marker`, **children of non-underlay
  parents**, pipes when `skip_pipes`. Used by phase 1, phase 4 and
  `HandleSnapSession`; each caller keeps only its genuinely caller-specific
  rules (`exclude` / `item_filter` / underlay-index branch; moving set,
  moving-node pipes, self-rest).
- `SnapEngine._origin_points(scene)`: the (0,0) cross position if visible + the
  red marker position if visible. Phase 1 tests them with the same metric as
  kind **`origin`** at **priority −1** (above intersection 0; band unchanged).
  `HandleSnapSession` adds them to its target grid; `HANDLE_TYPES` gains
  `origin`. Gated by F3 only (bypasses per-type toggles).
- Renderer: ⊕ glyph for `origin`, rotation-invariant (exempt from the tangent
  orientation rule), red-family colour token chosen with a live render.
- ALIGN: no specific change; whether ALIGN acquires by kind is a slice-0 probe.

### DD7 Smooth closed spline (approved: flag on `SplineItem`)
- `SplineItem(..., closed=False)` → `self._closed`; valid only with ≥ 3
  control points; a closed spline is always a uniform non-rational cubic
  (knots/weights `None`, degree 3).
- `_bspline_path` periodic branch: exact uniform-cubic → Bézier conversion
  (span i from control points i..i+3 wrapped: b0 = (p0+4p1+p2)/6,
  b1 = (2p1+p2)/3, b2 = (p1+2p2)/3, b3 = (p1+4p2+p3)/6), drawn with `cubicTo`
  + `closeSubpath`. **P4 verified 2026-10-01**: matches
  `ezdxf.math.closed_uniform_bspline` on its valid domain to 4e-14 mm; seam
  closed with a continuous tangent; 3 control points suffice; evaluating the
  full knot range is what produced the garbage tails.
- `is_closed()` = `self._closed` or the existing coincident-end rule.
- `to_dict` writes `"closed": true` only when set; `from_dict` defaults False;
  both serialization paths + block primitive factory.
- Grips: one per control point (no seam pair) → stays closed on drag.
  Transforms act on control points and keep the flag.
- Snap: the `_collect` spline branch emits **no endpoints** for a periodic
  spline; nearest/perpendicular/intersection come from the path.
- Offset: periodic → control loop ±d, mitered, no seam duplicate (existing
  wrapped-loop helper); result periodic.
- DXF: a closed SPLINE with degree 3, uniform knots, uniform/absent weights and
  wrapped control points (last 3 = first 3) → `SplineItem(unique_cps,
  closed=True)`; anything else keeps today's path. **Slice-0 probe** proves the
  mapping on a real closed-spline DXF before it is locked.

### DD8 Shared close helper + spline gesture
- `geometry_drawing_controller.py`: `close_hit(first, tip, cursor,
  view_scale) -> bool` (either point within 8 px — `2d-geometry.md` §4) +
  `show_close_ring` / `hide_close_ring` promoted from the polyline ring.
  Callers: spline, polyline, floor, roof (floor/roof gain the ring). Wall loop
  close (tip-snapping, 15 px) is unchanged and noted in the spec.
- `draw_spline`: with ≥ 3 points and `close_hit`, show the ring and switch the
  preview to the smooth closed curve; click commits periodic → Select.
  Enter / double-click finish open.

### DD9 Arc fix
The 14 sites (`scene_tools.py` × 9 — mirror arc branch, break circle ×2,
break-at-point circle + arc, trim circle ×2, trim arc ×2; `tool_geometry.py` ×
4 — fillet ×2, extend line + polyline arc branches; `geometry_intersect.
line_arc_intersections` × 1, Trim's only path) move to `arc_math.yup_angle` /
`point_at`. No new helper. *(As built — **13 live sites**: `scene_tools.py`
× 8 (the list above minus the mirror arc branch), `tool_geometry.py` × 4,
`geometry_intersect` × 1, all on `arc_math.yup_angle`; the mirror arc branch
was retired with `_apply_mirror` in slice 5, not patched — plan-review
amendment below.)* `test_scene_tools.py::TestBreakAtPoint::
test_arc_break_produces_two_arcs` is rewritten (its break point is off the
arc; it passes only because of the bug — `scene-tools.md` already documents
it). DXF full-ellipse rotation is out of scope (filed separately).

### DD10 Polish
- `_MODE_LABELS` in `main._update_mode_label`: friendly name for every mode in
  the dispatch tables (COPY, CUT, OFFSET, ARRAY, FLIP, MIRROR, SCALE, LINE,
  RECTANGLE …); a guard fails if a dispatched mode lacks a label.
- Cut registers as a modal button; `_sync_mode_buttons` consults
  `s._copy_is_cut` to light Copy vs Cut during `copy_base`; un-toggle cancels.
  `scene-tools.md` I1 ("Cut … plain buttons") amended.
- Both context menus: Copy → `_modify_ctl.start("copy")`; Cut added →
  `start("cut")`. `copy_selected_items` kept (copy-to-level, internals).

### DD11 Ribbon + icons
Modify group: Move · Rotate · Scale · Flip · Mirror · Offset · Array ·
Explode; tooltips show the Shift binding. Three new icons (Flip, Mirror,
Scale) in the 40-unit 2D-geo family (`icon-style-guide.md` §5.1, D12 grammar)
— contact-sheet mockup gate, live at 27 px light + dark, before wiring;
buttons use temporary icons until approved. *(As built: gate rendered the
live 18 px small-button size + 27 px; Flip / Mirror simplified by the user at
the gate — see the as-built amendments.)*

## Acceptance Criteria

*Status at Account (`c8ff4f4`; VC9 seam-review sweep at `3a95a3f` + `c8ff4f4`
fix): M1–M8 + icons MET (four with recorded deviations — see the as-built
amendments).*

- [x] **M1** Array ←/→ cycles Linear/2D/Polar only before the first pick;
      Linear with typed Angle 30° places copies at k·spacing along 30°
      (Y-up); 2D 3 × 4 places 12 items (incl. original) on the grid; Polar 8 @
      360° places 8 items at 45° steps, each rotated; variant + typed values
      pre-fill the next Array on the same canvas; one undo each.
- [x] **M2** Flip / Mirror detect any visible straight segment (incl. the
      selection's own edges), never curves; empty-space click refused; Flip
      transforms in place, Mirror adds copies; per-primitive results per DD1
      (type, closed flag, fill preserved; arc across x = 0 lands in Q2);
      text/blocks skipped with status; Shift+F / Shift+I; one undo; Esc no-op.
- [x] **M3** Scale by base/ref/cursor and by typed Factor; per-primitive
      results per DD1; refusals; text/blocks skipped; Shift+S; one undo.
- [x] **M4** Handle drag of an endpoint near (0,0) snaps to (0,0) as `origin`
      (⊕); Paste / Duplicate base near (0,0) snaps `origin` with the
      intersection toggle **off**; the Block Editor red marker pinned away
      from (0,0) is a target; plan scene too; no intersection X at the origin.
- [x] **M5** Click-near-first with ≥ 3 points makes a periodic spline with a
      continuous seam tangent; `closed` round-trips both serialization paths +
      block factory; Enter finishes open; a closed DXF SPLINE imports
      periodic; legacy coincident-end splines load unchanged; grip drag keeps
      it closed; no endpoint snaps; offset stays periodic. Polyline / floor /
      roof close on either the constrained tip or the snapped cursor.
- [x] **M6** All 14 sites (as built: the 13 live sites; the 14th retired) produce correct painted geometry (break-at-point at
      visual 45° splits there; circle break 0°–90° keeps the correct quadrant;
      fillet arc ends at the tangent points; trim removes the clicked piece;
      line × arc intersection = (50, −86.6) for the probe case).
- [x] **M7** Gridline bubble centres / symbol points are no longer
      handle-snap targets; the snap baseline (325 passed at `7766316`) passes,
      any rewritten test named in the done evidence.
- [x] **M8** Badge reads COPY / CUT / OFFSET … for real `modeChanged`
      emissions; Cut button lit during Cut and Copy not; context-menu Copy
      enters `copy_base`, Cut present in both menus.
- [x] Icons approved at the mockup gate; tooltips on every new/changed button.
- [x] Governing specs amended in place at Account (Rule A). *(Account,
      2026-10-01, stamped `c8ff4f4`.)*

## Verification Checklist

- [ ] Every guard drives the real path (real `Model_Space(scene_role=
      "block_editor")` + `Model_View`, press/move/HUD/Enter, `QShortcut`
      activation for shortcuts) and asserts observable geometry, undo count
      and undo restore; each shown RED with its change reverted (VC3).
- [ ] Keep-green: `test_dynamic_input_schema.py`, `test_dynamic_input_parity.py`,
      `test_modify_tools_*.py` (incl. `test_modify_tools_shortcuts.py`
      `EXPECTED`, `test_modify_tools_ribbon.py`), `test_icon_theming.py`
      `_MODIFY_ICONS`, `test_placement_variants.py`,
      `test_placement_input_slice_parity.py`, `test_ribbon_contextual.py`,
      `tests/test_*snap*.py` (baseline), `test_move_handle_snap.py`,
      `test_rect_grips_unified.py`, `test_scene_tools.py`, `test_tool_geometry.py`,
      `test_spline_item.py`, `test_ellipse_spline_draw.py`,
      `test_offset_item.py`, `test_polyline_closed.py`,
      `test_floor_placement_workflow.py`, roof placement tests,
      `test_geo2d_serialization.py`, `test_block_curve_import.py`,
      `test_geometry_import.py`, `test_geo2d_context_menu.py`,
      `test_block_explode.py`.
- [x] Whole-repo grep for every retired symbol (re-run at Account,
      `c8ff4f4`: no live code refs; only retirement comments
      (`scene_tools.py`), test docstrings in `test_rect_rotation_consumers.py`
      (retirement guards) and `test_manip_reflect_scale.py`, and docs;
      `_apply_scale_factor` in `model_space.py` is the new applier, not the
      retired symbol) (`_apply_mirror`,
      `_apply_scale`, `mirror_delete`, `_array_count_default`) — VC5.
- [ ] VC9 seam review before smoke; smoke → fixes → one full suite
      (`-m "not perf"`, then `-m perf` alone), honest exit codes.

## Plan-review amendments (user-ratified 2026-10-01)

Recorded when the plan (`docs/superpowers/plans/2026-10-01-scene-tools-p1-batch.md`,
local — plans are gitignored) was approved:

- **Slice-0 verdicts** (run at `012c181`): DXF closed-SPLINE → periodic mapping
  holds (and today's import draws a stray tail — fixed by DD7); `FieldKind.COUNT`
  rounds decimals → Scale adds **`FieldKind.FACTOR`**; ALIGN acquires snapped
  points generically → no ALIGN change for `origin`.
- **DD9 count is 13 live sites**: the 14th (`_apply_mirror` arc branch) is
  retired with `_apply_mirror` in slice 5, not patched.
- **DD5 accepted departures**: Angle `0` is the release value, so Linear cannot
  be *locked* to 0° (cursor / ALIGN reach horizontal); a blank Angle keeps the
  current value (the HUD never reports an empty field); only non-cursor fields
  are remembered (counts, Total, Angle lock — spacings come from the live aim).
  Defaults Linear 3, 2D 3 × 3, Polar 4 @ 360°; Polar start ray = centre →
  selection centre, CCW sweep, zero sweep = 360°; Nodes excluded from Polar
  (zero-offset paste merges them); 2D spacings signed; badge reads ARRAY for
  every variant.
- **DD1**: a reflected Rect angle is folded into [0°, 180°).
- **DD2**: the picker adds a closed polyline's closing edge (the engine's
  segment iterator omits it — snap follow-up filed).
- **DD6**: `origin` is not a `SNAP_MARKERS` key (that would add a ninth footer
  toggle); its glyph lives in a separate non-toggle map.
- **DD7**: the DXF mapping also runs in `dwg_converter.py` (import preview).
- **DD8**: the shared ring keeps the scene attribute `_polyline_close_indicator`
  and stays on vertex 0.
- **DD11**: the live small-button icon size is 18 px — the gate renders 18 and 27 px.

## As-built / execution amendments (2026-10-01)

Recorded at Account (Phase 6) from the slice reviews, the VC9 seam review and
the user decisions taken during execution; every item verified against the
code at `c8ff4f4`. **All DD1–DD11 are BUILT** on `feat/scene-tools-p1-batch`
(`7766316..c8ff4f4`, 57 commits). The governing specs now carry the contract
(Rule A) — `scene-tools.md` D10 (amended), D11–D12 / D14 (amended), D16
Flip / Mirror, D17 Scale, D18 badge, DV7 resolved; origin / eligibility →
`snapping-engine.md`; closed splines + close helper → `2d-geometry.md`.

**User decisions (2026-10-01, during execution):**

- *Origin + coincident geometry (DD6, Slice 2 review I-1):* when geometry
  coincides with the origin, the origin snap still wins (kind `origin`, ⊕)
  but adopts the coincident candidate's source / lines so ALIGN keeps
  working; a cursor `nearest` foot never decides the adopted source.
  Glyph colour `#e8325a` approved at a live gate.
- *Underlay curves are never mirror axes (DD2, Slice 4 review I1):* flattened
  DXF ARC / partial ELLIPSE / SPLINE and PDF Bézier chords are rejected via an
  additive optional underlay record key `"straight": True` (no cache-version
  bump); legacy cached `path_points` records are never axes until re-import
  (DXF LINE records still are).
- *Axis-pick perf bar:* `pick_axis` hover ≤ 8 ms median on a 20k-vertex
  contour in a 50k-record underlay (perf guard; measured 2.7–4.9 ms).
- *Polar Total (DD5, Slice 7 review I1):* the cursor sweep wins — Total is not
  remembered; Polar remembers Count only; a typed Total commits as typed.
- *Big arrays (DD5 / D11, Slice 7 review I2):* above
  `ARRAY_GHOST_FULL_MAX` (200) ghost paths the preview is one merged
  trace-only path (≤ ~16 ms repaint at 50 × 50); the commit stays uncapped.
- *Icons (DD11, gate `aaea504`):* Flip / Mirror simplified — source triangle
  + accent copy across a thin solid reference-line axis, no rings, no motion
  arrow (Flip source dashed, Mirror source solid). Scale keeps one base-corner
  ring at a larger radius than `icon-style-guide.md` §5.1's (18 px dark
  visibility — style-guide carve-out owned there).
- *Badge (DD10):* both thermal-radiation modes read **Radiation**.
- *Phase-drift absorbed (C2):* the dead close-ring wrapper after
  `_clear_scene` (New / Open) is fixed for polyline / floor / roof / spline.

**Deviations from the design text (as built):**

- *DD1:* a degenerate axis (`geometry_2d._degenerate_axis`, length² < 1e-12 —
  one threshold for picker, paint and `manip_reflect`) makes every
  `manip_reflect` a no-op (the orientation term would otherwise half-apply).
  Radius floors (Circle 1 mm, Arc via `set_radius`, Ellipse `_AXIS_MIN`) make
  very small Scale factors non-uniform — accepted, follow-up filed.
- *DD2:* axis sources are a whitelist — Line / RefLine, Polyline (incl. the
  closing edge the snap iterator omits), Rect, RegularPolygon, gridlines, wall
  faces, straight-tagged underlay records. Block-instance edges,
  floor / roof / room edges and pipes are not axes; a PDF record mixing
  straight and curved segments loses all its axes (v1); DWG underlays give no
  axis (pre-existing `_UNDERLAY_TAGS` gap, filed). Tolerance = the snap
  aperture at the active view's zoom.
- *DD4 Flip / Mirror:* refusal text is the shared `nothing_to_hint` ("Nothing
  to flip — only 2D drafting geometry can be flipped"; mirror / mirrored,
  scale / scaled), used by Scale too. Nodes (which legacy Mirror reflected) are skipped. Re-entry
  (Shift+F twice, Flip ↔ Mirror) keeps the hovered axis and rebuilds its
  ghost; an axis whose source vanished is dropped at commit; failed Mirror
  copies count as skipped. `MainWindow._on_confirm_requested`'s generic
  `else` arm lost its last emitter — left in place.
- *DD4 Scale:* the reference is refused within the pick tolerance of the base
  (`ModifyToolsController._pick_tolerance()`, snap aperture in px — renamed
  from `_axis_tolerance`), not an exact 1e-9; factor 1 ends the tool with no
  undo step ("Scale factor is 1 — nothing changed"); no Enter-at-cursor commit
  (click or typed Factor). FACTOR formatter / parser live on `ScaleManager`
  (`format_factor` / `parse_factor`, shared number grammar), not in
  `dynamic_input` (units spec rule).
- *DD5:* Array memory is per canvas tab for the session and never cleared by
  leaving the tool — **not** "same as Offset" (Offset's sticky distance is
  per tool run). Targets are only what `paste_items` can create
  (`Model_Space._paste_accepts`): walls / rooms / floors / roofs / design
  areas are refused up front so ghost == commit. Linear / 2D array a Sprinkler
  through its Node. Polar refuses a centre pick with nothing rotatable; the
  dimmed set is variant-independent (Polar-skipped items stay dimmed —
  follow-up filed). A locked-Linear projection ≤ 0 keeps the previous spacing;
  an Angle equal to the live aim does not lock; multiples of 360 release;
  the readout shows an active lock.
- *DD7:* the DXF periodic mapping also runs in `dwg_converter.py` (import
  preview) and in the underlay flattening path (`dxf_import_worker.py`);
  "both serialization paths" for splines means undo snapshot + block
  definition (loose 2D geometry is not saved in `.fpd`, C8). Non-uniform /
  weighted closed DXF splines still take the legacy path (tail, filed).
- *DD8:* the ring stays on vertex 0 (scene attribute
  `_polyline_close_indicator` kept); roof vertex-pop also uses the
  either-point rule; room placement still owns its own 8 px literal (filed).
- *DD10:* the badge also labels `dimension` (a ribbon-only literal mode).
  Cut's ribbon registry key is the pseudo-mode
  `ModifyToolsController.CUT_BUTTON_KEY` (`"copy_base:cut"`).
  `copy_selected_items` is now test-only (follow-up filed).
- *Ghost hand-off (VC9 seam review I-1, `c8ff4f4`):* `clear()` drops the
  shared transform ghost on every mode change — no mode inherits another's
  (was pre-existing for Rotate → Move, widened by Flip / Mirror / Scale /
  Array).
- *D14 (scene-tools):* Scale and Mirror (+ Flip) are now surfaced; Trim /
  Extend / Break / Fillet / Chamfer / Stretch / Merge / Join stay unreachable,
  so their DV7 fixes are guarded by tests only, not smoke-testable.

## Build order (slices; each green before the next)

0. Probes: DXF closed-spline fixture → mapping; `FieldKind.COUNT` accepts
   decimals? (else add `FieldKind.FACTOR`); ALIGN acquires by snap kind?
   Icon mockup gate (parallel).
1. Arc fix (DD9) — Flip/Mirror's arc rule depends on it.
2. Shared eligibility + origin source (DD6); re-run the snap baseline.
3. `manip_reflect` / `manip_scale_about` (DD1) with per-primitive guards.
4. Axis picker + hover paint (DD2, DD3).
5. Flip + Mirror (DD4) + ribbon/shortcuts.
6. Scale (DD4).
7. Array variants (DD5).
8. Closed spline data model + serialization + DXF (DD7).
9. Shared close helper + spline gesture (DD8).
10. Polish (DD10).
11. Wire approved icons (DD11).

## Follow-ups (filed 2026-10-01)

- Flip / Mirror / Scale for block instances (persisted mirror flag + scale pose).
- "Closed" property toggle for splines and polylines.
- Block Editor DXF import of a full ellipse mirrors its rotation.

## Existing Code Context

See the Phase 1b findings (as-built maps, REUSE / GENERALIZE / GAP, registry
lists) recorded in the session; the key homes are named in each DD above.
