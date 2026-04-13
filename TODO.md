# TODO

## Tasks
- [x] Voronoi relaxation algorithm for auto-populate sprinkler placement [type:Recently Completed] [subject:Sprinkler Design]
- [x] Level manager elevation enhancements (guard against deleted C++ objects) [type:Recently Completed] [subject:CAD]
- [x] Sprinkler property display improvements (absolute X/Y/Z read-only properties) [type:Recently Completed] [subject:Sprinkler Design]
- [x] Algorithm selection dropdown in auto-populate dialog [type:Recently Completed]
- [x] Room name as read-only property on sprinklers and nodes [type:Recently Completed]
- [x] Room name tagging on sprinkler nodes for reliable detection [type:Recently Completed]
- [x] Auto-populate removes existing room sprinklers before placing new ones [type:Recently Completed]
- [x] Fix stacked room sprinkler detection (Z-range filtering) [type:Recently Completed]
- [x] Elevation-based Z-ordering for plan view depth sorting [type:Recently Completed]
- [x] Detail markers filtered by view range [type:Recently Completed]
- [x] Model browser refresh on undo/redo [type:Recently Completed]
- [ ] README.md for the repository [type:Backlog] [subject:Documentation] [P3]
- [ ] Unit tests for hydraulic solver [type:Backlog] [subject:Hydraulic Calculator]
- [ ] Unit tests for auto-populate algorithms [type:Backlog] [subject:Sprinkler Design]
- [ ] Unit tests for geometry utilities (CAD_Math, geometry_intersect) [type:Backlog] [subject:CAD]
- [x] Full code review, develop specs for various existing features that don't have specs and do full documentation for the project — **completed 2026-04-09**: audit identified 16 spec gaps, 5 test gaps, and 1 existing spec update; all decomposed into tasks below [type:Backlog] [P1] [subject:Documentation] [done:2026-04-09]
- [x] Spec & grill session: define and refine the relationship between views — see `docs/specs/view-relationships.md` [type:Backlog] [P1] [subject:Architecture] [done:2026-04-08]
- [ ] Spec & grill session: wall, room & floor slab system — wall placement & joinery (L/T/cross joints, cap geometry, face-corner semantics, wall-to-wall snap targets, zero-thickness behavior), room boundary detection algorithm (graph traversal for closed loops, edge orientation), NFPA coverage metrics, floor slab occlusion logic, section-cut hatching, wall alignment modes (Center/Interior/Exterior offset computation). Consolidates wall joinery (snap-engine item 3) + audit-identified gaps in `wall.py` (1028 LOC), `room.py` (540 LOC), `floor_slab.py` (381 LOC), `wall_opening.py` (404 LOC) [type:Backlog] [P1] [subject:Architecture]
- [x] Spec & grill session: snapping engine — see `docs/specs/snapping-engine.md` (14 roadmap items added below) [type:Recently Completed] [subject:CAD]
- [ ] Add absolute elevation for node 1 and 2 in pipe properties template [type:Task] [subject:Sprinkler Design]
- [x] Investigate `Room.z_range_mm()` vs user expectations [ref:view-relationships§7.2] [subject:CAD] [done:2026-04-08]
- [x] Bug: Room fill/highlight disappears when room label is scrolled off-screen in plan view — root cause was `Room.shape()` override returning only the label area; Qt used it in the viewport paint path. Fixed by removing the override. [type:Task] [P2] [subject:CAD] [done:2026-04-08]
- [ ] Restore label-only click-selection for rooms — removing `Room.shape()` means clicking anywhere inside the polygon now selects the Room. Preferred fix: in `model_space.py` selection pick (~line 4403), prefer Wall/Floor/Roof/etc. over Room, and only accept a Room hit when the click falls inside the label-bg rect. [type:Task] [P2] [subject:CAD]
- [ ] Audit other `shape()` overrides in the codebase — the Room bug proved that a restricted `shape()` affects Qt's paint culling, not just hit-testing. Grep `def shape` across `firepro3d/` and verify no other item silently loses its fill when the narrow shape region scrolls off-screen. [type:Task] [P3] [subject:CAD]
- [x] Spec session: grid system architecture — consolidated into single `GridlineItem` with lock, pull-tab grips, perpendicular reposition, on-selection spacing dimensions, edit-existing dialog, cardinal-only elevation filtering, per-view Z-extent overrides. Legacy `GridLine` removed. See `docs/specs/grid-system.md` [type:Backlog] [P1] [subject:Architecture] [done:2026-04-10]
- [x] Spec session: scale calibration & underlay workflow — see `docs/specs/underlay-workflow.md`. Covers underlay lifecycle (import → place → persist → reload → refresh), per-level visibility, per-source-layer visibility, browser tree management, file-not-found handling, path resolution, transform origin fix. ScaleManager documented as fixed global constant (1 unit = 1 mm). [type:Backlog] [P1] [subject:Architecture] [done:2026-04-13]
- [ ] Spec session: sprinkler system components — sprinkler database (JSON schema, built-in products, custom records, manager dialog), diameter/schedule cross-reference system (internal key format, nominal OD table, inner diameter lookup for hydraulics, auto-Main ≥3" logic), fitting assignment algorithm (2/3/4-branch junction rules, elbow vs tee vs wye, through-direction hints), node Z-position computation (ceiling_level + ceiling_offset formula), sprinkler symbol scaling (real-world 24" diameter, SVG variants). Modules: `sprinkler.py` (165 LOC), `sprinkler_db.py` (586 LOC), `fitting.py` (429 LOC), `node.py` (330 LOC), `sprinkler_system.py` (49 LOC) [type:Backlog] [P1] [subject:Architecture]
- [ ] Spec session: hydraulic solver & reporting — NFPA 13 Hazen-Williams 4-phase algorithm (design sprinkler selection, backward pressure propagation, supply curve check, forward pressure propagation), friction loss & elevation correction formulas, velocity limits (12/20 fps thresholds), water supply curve interpolation, design area sprinkler selection rules, network validation (tree-only, supply node required), failure modes & warnings, report generation (4-tab layout, color-coded cells, CSV/PDF export, BFS node numbering). Modules: `hydraulic_solver.py` (701 LOC), `hydraulic_report.py` (521 LOC), `water_supply.py` (80 LOC) [type:Backlog] [P1] [subject:Architecture]

## Snapping Engine Roadmap (from `docs/specs/snapping-engine.md` §12)
- [x] Snap picker: same-parent intersection suppression + endpoint protection band — fixes wall-corner and hatch case studies [ref:snap-spec§6.3] [type:Backlog] [P1] [subject:CAD] [done:2026-04-07]
- [x] Snap phase-4 segment-source filter audit — restrict `_check_geometry_intersections` to matrix-supported types; add generic `QGraphicsPathItem` (DXF) + DXF underlay group descent [ref:snap-spec§5,§6] [type:Backlog] [P1] [subject:CAD] [done:2026-04-10]
- [x] WallSegment named-target marker variants — hollow square / hollow triangle for face corners and face midpoints [ref:snap-spec§8] [type:Backlog] [P1] [subject:CAD] [done:2026-04-07]
- [ ] Fix ConstructionLine perpendicular / nearest / phase-4 participation — **deferred**: ConstructionLine tool is not in active use; revisit if the feature sees real usage. Spec §5 note 2 corrected 2026-04-08. [ref:snap-spec§5-row-ConstructionLine] [type:Backlog] [P3] [subject:CAD]
- [x] Decouple `nearest` from the perpendicular toggle in `_geometric_snaps` [ref:snap-spec§5-note-1] [type:Backlog] [P2] [subject:CAD] [done:2026-04-08]
- [x] ArcItem tangent support in `_geometric_snaps` [ref:snap-spec§5-row-ArcItem] [type:Backlog] [P2] [subject:CAD] [done:2026-04-10]
- [x] Generic `QGraphicsPathItem` (DXF) phase-4 segment extraction [ref:snap-spec§5-note-7] [type:Backlog] [P2] [subject:CAD] [done:2026-04-10]
- [x] Snap engine geometric primitive unit tests (`_line_line_intersect`, `_line_circle_intersect`, `_project_to_segment`) [ref:snap-spec§10.1] [type:Backlog] [P2] [subject:CAD] [done:2026-04-08]
- [x] Snap engine matrix fixture test harness — one headless fixture per ✓-cell in §5 (59 tests, 11 classes) [ref:snap-spec§10.2] [type:Backlog] [P2] [subject:CAD] [done:2026-04-10]
- [x] Snap engine case-study regression tests pinned to §7.1 and §7.2 [ref:snap-spec§10.3] [type:Backlog] [P2] [subject:CAD] [done:2026-04-07]
- [x] Bind F3 to global OSNAP toggle and reflect state in status bar [ref:snap-spec§9.4-§9.5] [type:Backlog] [P3] [subject:CAD] [done:2026-04-08]
- [x] Confirm or build per-type OSNAP toggle UI surface (`snap_endpoint`, `snap_midpoint`, etc.) [ref:snap-spec§9.5] [type:Backlog] [P3] [subject:CAD] [done:2026-04-08]
- [ ] Spec session: OSNAP toolbar — per-type toggle UI, dockable placement, indicator layout, interaction with status bar pill [ref:snap-spec§9.5] [type:Backlog] [P1] [subject:CAD]
- [ ] F3 integration test on real keypress — QTest.keyClick did not dispatch through QAction shortcut on headless Windows; investigate pytest-qt / qtbot or alternate dispatch [type:Backlog] [P3] [subject:Testing]
- [ ] Decide whether F3 / global OSNAP toggle should also disable `_snap_to_underlay` (DXF underlay snap), or document the separation in the snap spec [type:Backlog] [P3] [subject:CAD]
- [ ] Spec session: pipe-with-fitting named targets [ref:snap-spec§8.3] [type:Backlog] [P2] [subject:CAD]
- [ ] Spec session: inferred / dimension-driven placement (next-priority subsystem) [ref:snap-spec§2.3] [type:Backlog] [P1] [subject:Architecture]
- [ ] Extract snap primitive epsilons (`1e-10` line-line denom, `1e-12` degenerate segment/radius) to named constants on `SnapEngine` — surfaced by primitive unit tests mirroring literals [type:Backlog] [P3] [subject:CAD]
- [ ] QPainterPath MoveTo element handling — `_collect`, `_geometric_snaps`, and `_check_geometry_intersections` all pair consecutive path elements as segments without checking element type; MoveToElements in multi-contour DXF paths create phantom connecting segments. Fix consistently across all three sites. [type:Backlog] [P3] [subject:CAD]
- [ ] Full OSNAP visual treatment in import dialog — basic snap-to-point with color-coded crosshair works today; add foreground source-item trace, snap type label, and named target glyph markers to match main scene snap UX. `dxf_preview_dialog.py` [type:Backlog] [P2] [subject:CAD]
- [ ] Phase-4 intersection highlight should show both source items — `ctx.check("intersection", ix, src1)` only passes one source; `source_item2` is always `None` for phase-4 intersections. Phase-2 gridline intersections manually set both. Fix `_check_geometry_intersections` to pass both `src1` and `src2` so the foreground trace highlights both crossing items [type:Backlog] [P2] [subject:CAD]
- [ ] Snap search rect performance at low zoom — `SNAP_TOLERANCE_PX / scale` creates very large search rects when zoomed out (e.g., 800×800 scene units at scale=0.1), pulling in far too many items for the O(n²) phase-4 pairing. Consider capping the scene-unit tolerance or skipping phase 4 when the search rect exceeds a threshold [type:Backlog] [P1] [subject:CAD]

## View Relationships Follow-Ups (from `docs/specs/view-relationships.md` §11)
- [ ] Extract plan-family Z-band magic numbers to named constants in `constants.py` — spec is source of truth for order, `constants.py` should own values [ref:view-relationships§7.3] [type:Backlog] [P3] [subject:CAD]
- [ ] Investigate elevation marker persistence — gap vs `DetailMarker.to_dict()` pattern; decide mirror or alternate approach [ref:view-relationships§6.3] [type:Backlog] [P2] [subject:CAD]
- [ ] Spec session: Section view subsystem — first-class arbitrary-cut-line section views [ref:view-relationships§4.1] [type:Backlog] [P1] [subject:Architecture]
- [ ] Spec session: Drafting overrides / view templates — defines resolution rules on top of catalog [ref:view-relationships§7.4] [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: Cross-view selection / interaction sync [ref:view-relationships§1.3] [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: Paper-viewport-specific overrides (depends on view-templates spec landing first) [ref:view-relationships§7.4] [type:Backlog] [P3] [subject:Architecture]
- [ ] Document or deprecate `Node.z_offset` legacy field — spec records it as legacy, migration/cleanup needed [ref:view-relationships§3.3] [type:Backlog] [P3] [subject:CAD]
- [ ] Remove vestigial `display_mode` from `Level` and `LevelManager.apply_to_scene()` — Hidden/Faded/Visible modes are unused; all visibility is driven by Z-range filtering in practice. Clean up `_set_level_vis()`, remove `DISPLAY_MODES` list, remove combo from `level_widget.py`, update serialization with backward compat [type:Backlog] [P3] [subject:CAD]

## Additional Spec Sessions
- [ ] Spec session: Roof elements — 4 roof types (flat/gable/hip/shed), ridge/hip line computation, pitch-to-peak-height formula, overhang offset algorithm (perpendicular-edge intersection with degenerate fallback), "auto" ridge direction heuristic (longest-edge midpoints), 3D mesh generation (pitched roofs incomplete today). `roof.py` (848 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: Door & window elements — wall-relative positioning (`offset_along` centerline), width-to-scene conversion chain (3-level fallback), swing arc geometry (doors), crossing-diagonal symbol (windows), hit-test scaling by zoom, preset libraries (doors 820-1800×2040mm, windows 600×1800mm), sill height. `wall_opening.py` (404 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: Floor elements — polygon-defined slabs with thickness, `_is_occluding` flag for plan-view masking of lower floors, section-cut hatch overlay, ear-clipping triangulation for 3D mesh, level offset (raised plinth support), Z-range computation (top/bottom from level + offset/thickness). No opening cutouts in 3D mesh today. `floor_slab.py` (381 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: Floor openings & stairs — openings, stair geometry, multi-level connectivity, sprinkler coverage implications. No implementation exists today; this is a greenfield design spec [type:Backlog] [P2] [subject:Architecture]
- [x] Spec session: Paper space — see `docs/specs/paper-space.md`. Covers sheet management, sheet views (linked view references), scale control, PDF export/print, title block template system, annotations, labels/thin-lines, layer overrides, DXF export target. Three-phase implementation plan (MVP → annotations/overrides → future). [type:Backlog] [P1] [subject:Architecture] [done:2026-04-09]

## Code Review Audit — Spec Gaps (from 2026-04-09 audit)

### P1 MVP (identified above in Tasks section)
_Grid system, scale calibration & underlay, wall/room/floor system, sprinkler components, hydraulic solver — see Tasks section above_

### P2 — Views & Managers
- [ ] Spec session: elevation scene projection & rendering — cardinal-axis coordinate mapping (N/S/E/W → H,V plane), world Z → vertical axis, entity projection rules, Z-range filtering & view-depth semantics, gridline/datum placement, rebuild triggers, `_ROLE_SOURCE` sync-back to 2D. `elevation_scene.py` (1233 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: detail view markers & crop geometry — rounded-rect crop box (fillet radius = 1.5× gridline bubble), bubble placement algorithm (leader line, "below center" default), dragging vs resizing interaction model, per-detail view-range override (None = inherit from parent plan), bubble radius = 3× gridline bubble (visual hierarchy). `detail_view.py` (566 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: 3D view rendering pipeline — PyVista/VTK mesh generation from entity geometry, 200-pipe cylinder threshold (fallback to lines), pick ray casting (15px tolerance), actor-to-entity bidirectional mapping lifecycle, dirty-flag lazy rebuild, radiation heatmap overlay, roof 3D mesh gap (flat only, no pitch). `view_3d.py` (1762 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: view markers & shared crop box — tangent-line circle geometry (R/sin(40°) point distance), four-marker cardinal positioning at crop-box edges, single shared crop box (not per-marker), 8-handle grip system, double-click → elevation view activation. `view_marker.py` (507 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: layer management system — DXF layer extraction (group data(2) field), QGraphicsItem data(1) layer-name matching, UserLayer lineweight mapping (5 named values, mm → cosmetic px best-fit), active-layer tracking, default layers (Default/Underlay/Annotations/Gridlines), per-item layer assignment protocol. `layer_manager.py` (128 LOC), `user_layer_manager.py` (647 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: property manager & type system — property type dispatch (label/string/enum/combo/color/level_ref/layer_ref/button/dimension), multi-select conflict resolution (blank when values differ), debounced refresh (50ms QTimer), lazy SprinklerDatabase loading, numeric field auto-validation. `property_manager.py` (553 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: display system override resolution — formalize the three-tier cascade contract (per-instance > project > QSettings > factory default), scope of per-instance vs per-category applicability, SVG recolouring cache invalidation, interaction with future view templates (view-relationships §7.4). Deepens existing `docs/architecture/display-system.md`. `display_manager.py` (2071 LOC) [type:Backlog] [P2] [subject:Architecture]
- [ ] Spec session: scene tools (geometry editing) — 16 tools in `SceneToolsMixin`: offset (line intersection, polyline offset), array (linear/polar, 200-copy preview cap), rotate/scale/mirror (anchor point transforms), join/explode (merge segments, decompose groups), break/break-at-point (segment splitting), fillet/chamfer (corner rounding/bevelling), stretch (crossing-window selection), trim/extend (to intersections), merge/hatch (polygon merging, fill patterns), constraints (creation and solving). Per-tool workflow, algorithm, edge cases, and mode state machine integration. `scene_tools.py` (1612 LOC) [type:Backlog] [P2] [subject:Architecture]

### P2 — Existing Spec Updates
- [ ] Update pipe-placement-methodology.md — add "Known Implementation Bugs" section: snap_point_45 insertion-order dependency (§4.1), three code paths bypassing `add_pipe()` (§5.3/§5.4/§4.4), 3D length calculation bugs in preview pipe (§9.2), clarify intent of 2D-only `_would_backtrack_at()`, document elevation mismatch dialog failure modes [type:Backlog] [P2] [subject:Documentation]

### P3 — Nice-to-Have
- [ ] Spec session: auto-populate sprinkler placement algorithm — NFPA 13 density/area curve interpolation, polygon decomposition into rectangles (scanline), branch-line direction detection (1/2/3+ pipe logic), `_walk_branch()` algorithm, wall-proximity 2× rule, edge cases (L-shaped rooms, concave rooms, dead-end branches, multiple design areas). `auto_populate_dialog.py` (1640 LOC), `design_area.py` (558 LOC) [type:Backlog] [P3] [subject:Architecture]
- [ ] Spec session: construction geometry system — 6 types (ConstructionLine, PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem), placement workflows (2-click, multi-click, drag-to-edit), snap contribution per type, grip points, constraint attachment, serialization. `construction_geometry.py` (954 LOC) [type:Backlog] [P3] [subject:Architecture]
- [ ] Spec session: parametric constraint system — abstract `Constraint` base with `solve()`, ConcentricConstraint (centre translation), DimensionalConstraint (grip-point distance enforcement), resolution order, dependency handling, over-constrained detection, serialization with item ID mapping. `constraints.py` (325 LOC) [type:Backlog] [P3] [subject:Architecture]
- [ ] Spec session: annotations & hatch patterns — NoteAnnotation (MText-like word-wrap, bold/italic, alignment), DimensionAnnotation (two-point + offset witness lines), HatchItem (region fill with constraint interaction), SVG hatch pattern loader (24×24 viewBox tiling, seamless rules), built-in Qt brush patterns. `annotations.py` (739 LOC), `hatch_patterns.py` (239 LOC) [type:Backlog] [P3] [subject:Architecture]

## Code Review Audit — Test Gaps (from 2026-04-09 audit)
_Existing test gap tasks (hydraulic solver, auto-populate, geometry utilities) already in Tasks section above_
- [ ] Unit tests for wall, room & floor slab entities — wall alignment computation, room boundary detection, floor slab occlusion, section-cut hatching [type:Backlog] [P2] [subject:Testing]
- [ ] Unit tests for sprinkler system components — sprinkler database CRUD, diameter/schedule lookup chain, fitting assignment rules, node Z-position computation [type:Backlog] [P2] [subject:Testing]
- [ ] Unit tests for paper space — viewport coordinate transformation, title block rendering pipeline, layout algorithm [type:Backlog] [P2] [subject:Testing]
- [ ] Unit tests for scene tools — offset, fillet/chamfer, trim/extend, break algorithms [type:Backlog] [P3] [subject:Testing]
- [ ] Unit tests for 3D view — mesh generation from entity geometry, pick ray casting accuracy [type:Backlog] [P3] [subject:Testing]

## Underlay Workflow Follow-Ups (from `docs/specs/underlay-workflow.md` §15)
- [ ] Implement `Underlay` data model changes — new fields (`level`, `visible`, `hidden_layers`, `import_mode`), serialization, backward compat [ref:underlay-spec§3] [type:Backlog] [P1] [subject:CAD]
- [ ] Implement underlay path resolution — relative/absolute save/load rules, `..` depth guard [ref:underlay-spec§4] [type:Backlog] [P1] [subject:CAD]
- [ ] Implement file-not-found handling — placeholder item, aggregate warning, relink action [ref:underlay-spec§5] [type:Backlog] [P1] [subject:CAD]
- [ ] Fix underlay transform origin to bounding rect center [ref:underlay-spec§6] [type:Backlog] [P1] [subject:CAD]
- [ ] Implement per-level underlay visibility [ref:underlay-spec§7] [type:Backlog] [P1] [subject:CAD]
- [ ] Implement per-source-layer visibility for DXF underlays [ref:underlay-spec§8] [type:Backlog] [P1] [subject:CAD]
- [ ] Add underlay section to browser tree with context menus [ref:underlay-spec§9] [type:Backlog] [P1] [subject:CAD]
- [ ] Add PDF DPI dropdown to import dialog [ref:underlay-spec§10.2] [type:Backlog] [P2] [subject:CAD]
- [ ] Add PDF import mode toggle (vector/raster/auto) to import dialog [ref:underlay-spec§10.3] [type:Backlog] [P2] [subject:CAD]
- [ ] Update refresh-from-disk to preserve new underlay state [ref:underlay-spec§11] [type:Backlog] [P2] [subject:CAD]
- [ ] Unit tests for underlay path resolution and serialization [ref:underlay-spec§14.1] [type:Backlog] [P2] [subject:Testing]
- [ ] Integration tests for underlay file-not-found and refresh [ref:underlay-spec§14.2] [type:Backlog] [P2] [subject:Testing]
- [ ] Batch multi-page PDF import [ref:underlay-spec§2.2] [type:Backlog] [P3] [subject:CAD]
- [ ] Preserve source DXF colours option [ref:underlay-spec§2.2] [type:Backlog] [P3] [subject:CAD]
- [ ] Undoable underlay operations [ref:underlay-spec§2.2] [type:Backlog] [P3] [subject:CAD]
- [ ] Bug: Refresh-from-disk loses import scale and base-point offset — `_commit_place_import` bakes scale/base-point into geometry coordinates but doesn't store them in the Underlay record. On refresh, raw DXF is re-parsed without those transforms. Fix: store `import_scale` and `base_x`/`base_y` on Underlay, re-apply transform on refresh/load instead of baking into geometry. Also affects save/load. `model_space.py:_commit_place_import`, `underlay.py` [type:Bug] [P1] [subject:CAD]
- [ ] Fix snap not working in import dialog preview — snap engine is wired up (`_snap_engine.find()` called in pick_point mode) but no snap markers appear. Pre-existing issue, not a regression. Investigate whether `_collect()` handles bare QGraphicsItems in the preview scene correctly. `dxf_preview_dialog.py` [type:Bug] [P2] [subject:CAD]
- [ ] Two-point calibration distance input should reflect display units — currently QInputDialog shows dimensionless value, should use `format_length`/`parse_dimension` pattern and respect current display unit setting. `dxf_preview_dialog.py:_on_pick2_pt()` [type:Task] [P2] [subject:CAD]
- [ ] Add checkbox toggles for underlay and layer visibility in browser tree — checkmarks beside underlay file nodes (show/hide) and source-layer nodes (show/hide layer) for quick toggling without right-click context menu [type:Task] [P2] [subject:CAD]
- [ ] Ability to select/access individual items within an underlay group — future feature to interact with sub-items of an imported underlay [type:Backlog] [P3] [subject:CAD]
