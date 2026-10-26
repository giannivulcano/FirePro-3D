---
status: partial -- slice 1 built 2026-10-26 (c23c1610); slices 2-3 open   # three feature slices (see Build slices)
last-verified: 2026-10-26
verified-commit: c23c1610
applies-to:
  - main.py (init_ribbon, _init_build_tab / _init_editor_tab, canvas context, retired contextual-tab mechanism)
  - firepro3d/ribbon_bar.py
  - firepro3d/constraint_controller.py
  - firepro3d/sketch_adapters.py
  - firepro3d/auto_constrain.py
  - firepro3d/wall.py
  - firepro3d/wall_placement_controller.py
  - firepro3d/gridline.py
  - firepro3d/scene_io.py
  - firepro3d/model_view.py
source-tasks:
  - "todo_open.md -> [type:design] Context-aware \"Editor\" tab + new \"Build\" tab; plan-view Editor edits feature primitive geometry [P1]"
consolidates:   # Rule A -- each of these gets a one-line pointer at Account; full rewrites are follow-ups
  - docs/specs/ribbon-bar.md
  - docs/specs/model-space-containment-contract.md
  - docs/specs/parametric-constraint-system.md
  - docs/specs/wall-room-floor-system.md
  - docs/specs/feature-system.md
  - docs/specs/scene-tools.md   # Edit + Modify button roster merges into one "Edit" group
---

# Editor + Build Tabs and Plan-View Constraints -- Design Spec

> **Status: partial.** Slice 1 (the ribbon, section 1) is built and verified at `c23c1610`
> (2026-10-26); slices 2-3 (plan constraints, Wall Auto Constrain) are unbuilt. This is the
> consolidating contract the governing specs above link to; it records the ratified decisions
> of the 2026-10-24 grill (G1-G13), the Phase 3 deltas (B1-B6), the approved ribbon mockup
> and the slice-1 rulings (S1, R1, R2).

## Goal

Two things, delivered as one coherent workflow change:

1. **Ribbon:** the ribbon becomes seven permanent tabs --
   `Manage | Architecture | Sprinkler Systems | Analyze | Draft | Build | Editor`.
   **Build** creates things (Block entry verbs, block Definition, 2D Geometry);
   **Editor** changes things (Edit, Constrain, Inspect). Both follow the active
   canvas. The contextual-tab mechanism ("Modify | <Element>") is retired.
2. **Plan constraints:** in plan view the Editor's Constrain / Inspect / Edit tools act
   on **wall centerlines** and **gridlines**, giving dimension-driven wall layout:
   Smart Dimension lengths and offsets, H/V, Perpendicular, Parallel, Coincident,
   Equal and the rest of the line-capable catalogue, persisted in the `.fpd`.

## Motivation

The user lays out walls by dimension (G1): "this wall 12'-0" from gridline A, these two
perpendicular, this room a rectangle that stays a rectangle when I drag a corner." The
Block Editor already has a full parametric sketch solver; plan walls have only
proximity joins. Splitting the ribbon by *intent* (Build vs Editor) instead of by
*canvas* (a Block Editor tab) lets the same Editor tools serve both the block canvas and
the plan canvas, and removing contextual tabs ends the per-selection tab churn (G4, G6).

## Ratified decisions (index)

| Id | Decision | Gate |
|---|---|---|
| G1 | End goal: dimension-driven wall layout in plan; walls act as a constrained sketch | Phase 2 ask |
| G2 | Containment: narrow amend -- no loose drawing in Model Space; constraint + modify tools on feature defining geometry allowed | Phase 2 ask |
| G3 | Tab roster `...Draft | Build | Editor`; Build = Block + Definition + 2D Geometry; Editor = Edit + Constrain + Inspect | Phase 2 ask (+ B5) |
| G4 | All contextual editor tabs retire (whole mechanism) | Phase 2 ask |
| G5 | Type-specific contextual groups (Graphic Override; Opening Placement/Orientation) -> property panel only | Phase 2 ask |
| G6 | Selection never switches the ribbon tab | Phase 2 ask |
| G7 | Accept the panel gap: contextual tabs retire before panel parity; panel rows filed P2 | Phase 2 ask |
| G8 | Plan refs: walls + datums; floors/roofs/rooms/pipes are follow-ups (levels narrowed by B1) | Phase 2 ask |
| G9 | Legacy projects load unconstrained (no inference) | Phase 2 ask |
| G10 | Unconstrained ends keep proximity follow | Phase 2 ask |
| G11 | Wall auto-constrain mirrors the Block Editor (joins -> Coincident / point-on-edge, H/V by exactness, rect -> Perpendicular + Coincident), under the global toggle | Phase 2 ask |
| G12 | Plan glyphs / driving dims: on selection or while a Constrain/Inspect tool is active; never on sheets/PDF/print | Phase 2 ask |
| G13 | Paper / 3D: Build + Editor groups disabled with a tooltip, Build's Block group live | Phase 2 ask |
| B1 | Plan constraints reference walls + **gridlines only** -- levels are not drawn in plan; level refs are a follow-up for an elevation/section Editor | Phase 3 ask |
| B2 | Editor Edit group live in plan; Move/Rotate act on walls (constraint-aware); Flip/Mirror/Scale/Offset refuse walls as today -> wall-hook follow-up (Array is **not** in that set -- see R2) | Phase 3 ask; Array corrected by R2 |
| B3 | Entering a block/schematic canvas jumps the ribbon to **Build**; leaving restores the prior tab only if Build is still current | Phase 3 ask |
| B4 | Architecture A: one ConstraintController with a per-scene capability (no parallel plan system) | Phase 3 ask |
| B5 | Ribbon mockup approved, with Edit + Modify merged into one group titled **Edit** | Phase 3 mockup gate |
| B6 | Design sections 1-4 below approved | Phase 3 asks |
| S1 | Elevation / Section tabs are a seventh canvas kind `section`, behaving like paper / 3D (Build › Block live; the rest off, "Not available in this view") | slice-1 Phase 2 ask |
| R1 | Two mode-button registries kept (`_mode_buttons` for plan tools, `_block_mode_buttons` for Build / Editor tools); `_sync_mode_buttons` gates `_block_mode_buttons` by "Edit is live for the current canvas kind". Deviation from section 1's "collapse to one if no shared key" | slice-1 Phase 4 ask (2026-10-25) |
| H1 | A solve that moves a gridline treats its hosted blocks as a grip drag does: ride the frame on shift / rotate; origin slide along the axis compensates so they stay put (D6) | slice-2 Phase 2 ask (2026-10-26) |
| R2 | **Array stays live on a wall selection** -- Array copies walls through the paste path (`paste_items` has a wall branch). B2 wrongly listed Array among the tools that refuse walls; in plan a wall selection greys Scale / Flip / Mirror / Offset only | slice-1 Phase 5 ask (2026-10-26) |

## Architecture & Constraints

### 1. Ribbon (slice 1)

- **Seven permanent base tabs**, each built once with `RibbonBar.add_page`. The Block
  Editor tab (`_init_block_editor_tab`) is split into `_init_build_tab` and
  `_init_editor_tab`; the `_be_page` / `_be_page_index` pair becomes one per tab.
- **Build** = **Block** (New, Open large; Manager, Insert small -- always live) ·
  **Definition** (Save, Save As, Save as Template, Import, Edit Attributes, Pattern Tile,
  Linetype, End Type) · **2D Geometry** (today's draw-mode buttons + Fill).
- **Editor** = **Edit** (one group: today's Edit buttons Copy / Cut / Paste / Duplicate /
  Delete followed by today's Modify buttons Move / Rotate / Scale / Flip / Mirror /
  Offset / Array / Explode) · **Constrain** · **Inspect** (contents owned by
  `parametric-constraint-system.md` §10). One helper builds the merged group from the two
  existing builders' button sets; the button roster, order and shortcuts stay owned by
  `scene-tools.md` D1/D2 -- only the grouping changes.
- **Canvas context.** `_set_block_editor_context(active: bool)` generalizes to
  `_set_canvas_context(kind)`, `kind` in
  `plan | block | schematic | paper | 3d | detail | section`, derived in `_on_tab_changed`
  (today's `isinstance(w, BlockEditorWidget)` branch; schematic = a `BlockEditorWidget` of
  kind `"schematic"`; section = a `SectionView` -- every Elevation and Section tab, each on
  its own `section_manager` scene, which today falls through `_on_tab_changed` as plan).
  One table owns which groups are live per kind:

  | Group | plan | detail | block | schematic | section | paper | 3d |
  |---|---|---|---|---|---|---|---|
  | Build › Block | live | live | live | live | live | live | live |
  | Build › Definition, 2D Geometry | off (a) | off (a) | live | live (c) | off (b) | off (b) | off (b) |
  | Editor › Edit, Constrain, Inspect | live (d) | live (d) | live | live | off (b) | off (b) | off (b) |

  (a) tooltip "Open or create a block to edit" (today's `_BE_NO_EDITOR_TIP`);
  (b) tooltip "Not available in this view"; (c) the schematic capability narrowing
  (`schematics.md` D-S14: Pattern Tile / Linetype / End Type / Edit Attributes) runs as a
  second pass after the table; (d) Constrain + Inspect stay `off (a)` in plan/detail
  until slice 2 lands. A Detail tab is a `Model_View` on the shared model scene, so kind
  `detail` behaves as plan (**resolved at slice 1**: `_canvas_kind_for` keys it off the
  `Detail: ` tab text).
  The `section` column was ratified at the slice-1 Phase 2 gate (S1, 2026-10-25): it
  behaves like paper / 3D; Editor tools acting on a section scene are a follow-up
  (`todo_open.md` "Constraint refs beyond walls + gridlines", +1 occurrence).
- **Selection narrowing.** `_refresh_modify_buttons` runs against the *active* scene for
  every live kind (plan included). Each Edit button's enable state is
  `ModifyToolsController.can_start(tool, items)`, which shares `_refusal_hint` with
  `start()` so the ribbon state and the click cannot drift; a wall selection disables
  Scale / Flip / Mirror / Offset (B2) while **Array stays live** (R2), Delete needs a
  selection and a live view, and Explode stays Block-Editor-only (containment C3).
- **Mode-button registries (R1, as built).** Editor buttons light for whichever scene is
  active (plan or block). The split `_mode_buttons` / `_block_mode_buttons` (#217) is
  **kept**: `_sync_mode_buttons` treats `_block_mode_buttons` as live only where Edit is
  live for the current canvas kind (`_GROUP_LIVE_KINDS["edit"]`), so the Editor's
  Move / Rotate light from a plan mode and nothing in it lights on paper / 3D / section
  (user ruling 2026-10-25; the design had allowed collapsing to one registry).
- **Switch / restore (B3).** Today's `_show_block_editor_ribbon` / `_hide_block_editor_ribbon`
  retarget to the Build page: entering a block/schematic canvas remembers the current tab
  and makes Build current; leaving restores it only if Build is still current.
- **Contextual tabs retired (G4/G6).** Deleted: `_CONTEXTUAL_TABS`, `_contextual_registry`,
  `_init_contextual_tabs`, `_on_selection_changed_contextual` (and its
  `selectionChanged` connect), `_build_geo2d_context`, `_build_geo2d_graphic_override_group`,
  `_build_opening_context`, `_build_floor_context`, `_build_graphic_override_group`,
  `_build_contextual_edit_group`, `_contextual_title`, `_element_name_for`,
  `_family_key_for`, `_resolve_selection_context`, `_pre_contextual_tab`,
  `_active_contextual_*`, and the suppression role of `_block_ribbon_active`.
  `RibbonBar.insert_page(contextual=True)` / `remove_page` stay in the library (dumb,
  reusable). Coupled tests rewritten or retired in the same slice:
  `tests/test_ribbon_contextual.py`, `tests/test_opening_ribbon.py`,
  `tests/test_view3d_tab_mainwindow.py`, `tests/test_block_editor_ribbon_tab.py`,
  `tests/test_modify_tools_ribbon.py` (VC5 whole-repo grep at plan time).

### 2. Plan constraint capability and persistence (slice 2)

- **Capability, not a role check.** `ConstraintController` keeps `enabled` and gains
  `ref_types`: `None` (all adapters) when `scene_role == "block_editor"`,
  `{WallSegment, GridlineItem}` when the scene is the plan model scene; every other
  scene stays disabled. The adapter lookup filters by `ref_types`, so pick mode, Auto
  Constrain and selection-first adds see only walls and gridlines.
- **Gate audit.** Every read of `ctl.enabled` / `constraint_ctl.enabled` (about thirty,
  in `constraint_controller.py`, `constraint_paint.py`, `geometry_drawing_controller.py`,
  `model_view.py`, `model_space.py`, `modify_tools_controller.py`, `property_manager.py`,
  `selection_manipulator.py`) is classified *constraints are on* (keep) or
  *this is the Block Editor* (becomes a role check -- e.g. 2D-drawing H/V `_hv_on`, the
  origin cross + X/Y axes, `model_space.py`'s refusal of `constrain_*` modes in plan).
  The plan lists each site with its verdict. Not to be confused with the per-constraint
  `c.enabled` (Suppress) flag.
- **No origin / axes in plan.** The reserved grounds `origin`, `x_axis`, `y_axis` are not
  offered and not painted in plan; H/V and Fix are absolute and need neither.
- **Wall adapter** (`sketch_adapters`): variables `x1 y1 x2 y2` from `_pt1` / `_pt2`
  (centerline, scene coords); handles `p1`, `p2`, `mid` (derived midpoint, D58), edge
  `edge`; grip map 0 -> `p1`, 1 -> `p2`, 2 (translate) and 3 (width) pin the whole item
  (no handle). Write-back sets both endpoints, then `invalidate_geometry()` (rebuilds the
  cached outline / joins and re-anchors openings -- `wall-room-floor-system.md` §4.5/§6.1).
  A solve that shrinks a wall to zero length is a collapse (D29) and is refused. Width is
  not a variable.
- **Gridline adapter:** variables `x1 y1 x2 y2` (origin, far end) derived from
  `_origin` / `_length` / `_angle_deg`; handles `p1`, `p2`, `mid`, edge `edge`; grip map
  0 -> `p1`, 1 -> `p2`, bubble grips 2/3 have no handle. Write-back converts back to
  origin / length / angle; bubbles keep their standoff. **Hosted blocks (H1):** a solve
  treats hosted blocks exactly as a grip drag does -- they ride the gridline frame when it
  shifts or rotates, and when the origin slides along the axis the write-back calls
  `_shift_hosted_along` so they stay put (D6).
- **Participation.** The controller's `items()` walks `_PARTICIPATING` scene lists;
  `ref_types` adds the plan scene's `_walls` / `_gridlines` and the plan scene lists only
  those two (no 2D-geometry lists).
- **Gate audit count (1b probe, 2026-10-26):** 41 controller-`enabled` reads, not ~30.
  The constraint paint layer (`constraint_paint.paint` -> `_paint_axes`, called from
  `Model_View.drawForeground`) draws the X/Y ground axes: that draw becomes a
  Block-Editor role check, as do the reserved-ground pick candidates
  (`PickState._candidates`).
- **Wall uid.** `WallSegment` mints `_uid` (uuid4 hex) at construction; `to_dict` /
  `from_dict` carry `"uid"` (legacy dicts keep the minted one); Copy / Paste / Duplicate
  mint new uids at the same paste path that re-mints gridline and instance uids. Internal
  constraints of a copied set are remapped as today (D30). 1b probe: the gridline branch
  of `paste_items` re-mints `_uid` but never writes `uid_map` (geometry and block branches
  do), so the wall branch and the gridline branch both add their `uid_map` entry. The
  wall branch also calls `apply_category_defaults` (slice 2 scope add; normal placement
  already does).
- **Persistence.** `scene_io` save writes the plan controller's records under a top-level
  `"constraints"` key; load restores them after every item exists. A record whose refs do
  not all resolve to a wall or gridline in the loaded scene is **dropped** and counted in
  the existing clean-drop log line (this also clears stale pre-contract loose-geometry
  records); a record of an unknown type whose refs resolve is kept **inert** per
  `parametric-constraint-system.md` §6.4.
- **Undo.** The plan snapshot already calls `constraint_ctl.capture()` / `restore()`
  (`_capture_network` / `_restore_network`); with the capability on, plan undo / redo
  carry constraints. Deleting a constrained wall cascade-deletes its constraints in the
  same undo step (`on_items_removed`).
- **Levels.** A solve moves every wall in the touched component, including walls on a
  hidden level; picks land only on visible items.

### 3. Wall Auto Constrain, proximity follow, glyphs (slices 2-3)

- **Placement records (slice 3, G11).** `_auto_join_wall` produces records and sends them
  through `ConstraintController.auto_join` inside the placement's own `push_undo_state`:
  endpoint-to-endpoint join -> `coincident [new end, partner end]`; tee join ->
  `point_on_curve [new end, host edge]`; line / polyline walls add `horizontal` /
  `vertical` when the centerline is exactly H/V; a rectangle commit
  (`_commit_wall_rect_rotated`) adds 4 `coincident` corners + 3 `perpendicular` corners
  (a 4th would be redundant). Gated by the global Auto Constrain toggle XOR Shift (D139)
  on the committing press. The geometric snap / join itself is unchanged.
- **Proximity follow coexists (G10, slice 3).** On an endpoint drag the solver moves every
  end tied to it by `coincident`; `_propagate_wall_endpoint` then skips those ends so
  nothing moves twice. Touching ends with no Coincident still follow by proximity.
  Joins stay proximity-resolved at render; coincident ends stay exactly coincident, so
  miters hold.
- **Glyphs and dims (G12, slice 2).** `Model_View.drawForeground` paints plan constraints
  under D32 (selected walls' constraints + the selected constraint; Show Constraints =
  all; pick markers while a Constrain / Inspect tool is active). Sheets and PDF render
  through `QGraphicsScene.render` (paper viewport, `paper_export`), which never runs a
  view's `drawForeground` -- glyphs never plot by construction; T7 still guards it.
- **Smart Dimension in plan:** a wall edge -> centerline length; two ends -> distance; an
  end then a gridline edge -> point-line offset (D133-D137). Values stored in mm;
  display / parse per `units-and-formatting.md`.

### 4. Containment contract amendments

- **C7 reworded:** "No 2D drawing tools in Model Space. Constraint and Modify tools may
  act on the *defining geometry* of built-in Features (wall centerlines) and of datums
  (gridlines) in plan."
- **C8 exception:** plan constraints whose refs are all walls / gridlines persist in the
  `.fpd`; every other constraint record is still dropped.
- **C1 unchanged:** no loose authored geometry in the model.

## Design Decisions (approaches considered)

| Axis | Chosen | Rejected | Why |
|---|---|---|---|
| Constraint engine | A: existing controller + per-scene capability | B: separate plan system with a wall-graph solver; C: relations stored on each wall | One solver, glyph painter, Smart Dim and panel; B duplicates all of them (the reuse-sweep failure mode); C leaves the shared record format and can't express wall-to-gridline |
| Ribbon split | By intent (Build / Editor) | By canvas (Block Editor tab) + contextual tabs | Same Editor tools serve plan and block; no selection churn |
| Edit + Modify | One "Edit" group | Two groups | User call at the mockup gate (B5) |
| Canvas switch | Jump to Build + restore (today's rule retargeted) | Jump to Editor; never switch | New blocks start with drawing (B3) |
| Level refs | Gridlines only in plan | Draw level datums in plan; hidden ref | Levels have no plan graphic (B1) |
| Wall Modify gaps | Ship Move/Rotate, file the rest | Add all wall hooks now | Keeps slice scope; hooks are independent (B2) |

## Build slices

Each is its own `[type:feature]` `/todo` run, in order (filed at 4f).

1. **Ribbon** (built 2026-10-26, `c23c1610`) -- Build + Editor tabs, merged Edit group, canvas-kind context table,
   switch/restore to Build, contextual mechanism + coupled tests retired; Constrain /
   Inspect plan-disabled. Guards T1, T2.
2. **Plan constraint foundation** -- capability + gate audit, wall uid, wall + gridline
   adapters, `.fpd` persistence + undo, plan glyphs + Smart Dim; Constrain / Inspect go
   live in plan. Guards T4, T5, T7, T6 (legacy loads with 0 constraints).
3. **Wall Auto Constrain** -- placement records + proximity-follow skip. Guards T3, T6
   (proximity follow still moves touching ends), T8.

## Acceptance Criteria

- [x] AC1 Ribbon roster `Manage|Architecture|Sprinkler Systems|Analyze|Draft|Build|Editor`; the Block Editor tab is gone; Build = Block / Definition / 2D Geometry, Editor = Edit (merged) / Constrain / Inspect; enable state per the canvas-kind table (T1).
- [x] AC2 No contextual tab is ever inserted; selection never changes the current tab (T2).
- [x] AC3 Entering a block/schematic canvas makes Build current; leaving restores the prior tab only if Build is still current.
- [ ] AC4 Plan Constrain / Inspect act on wall centerlines + gridlines only; constraints persist in the `.fpd`, round-trip undo/redo, and never plot (T4, T5, T7).
- [ ] AC5 Containment C7/C8 amended as in §4; C1 unchanged.
- [ ] AC6 Wall placement auto-constrains per §3 under the toggle; a rect wall resizes as a rect; deleting a constraint frees it (T3, T8).
- [ ] AC7 Legacy projects load with 0 constraints; unconstrained ends keep proximity follow (T6).

## Verification Checklist (tests -- VC3: real MainWindow / scene, each shown RED with the change reverted)

- [x] T1 roster + per-group enable state for each canvas kind (plan, detail, block, schematic, section, paper, 3d), tooltips included.
- [x] T2 selecting walls / pipes / 2D geometry inserts no tab and leaves the current tab unchanged.
- [ ] T3 place a rect wall -> drag a corner grip -> the four walls stay a rectangle (angles measured from endpoints).
- [ ] T4 Smart Dim a wall length -> drag its other end -> length held; Smart Dim an end-to-gridline offset -> move the gridline -> offset held.
- [ ] T5 save / reopen the `.fpd` and undo / redo round-trip plan constraints (record content compared, not count).
- [ ] T6 a legacy `.fpd` loads with 0 constraints; dragging a joined end still moves touching ends.
- [ ] T7 glyphs present on a selected constrained wall in the plan view; absent from a sheet viewport render and a PDF export (pixel digests, per the pixel-guard convention).
- [ ] T8 Auto Constrain off -> wall placement adds no constraints.
- [ ] T9 (slice 2, H1) a solve that slides a gridline's origin along its axis leaves a hosted block's scene position unchanged; a solve that shifts the gridline sideways moves the block with it.
- [ ] T10 (slice 2) a pasted wall takes its Display Manager category defaults; a copied constrained gridline pair (and wall pair) keeps its internal constraint on the copies (D30).
- [ ] T11 (slice 2) no origin cross / X-Y ground axes paint in the plan view and none is offered as a pick candidate.

## Edge Cases & Error Handling

- Over-constrained edit in plan -> the Block Editor's hold-last-good + status ("Over-constrained: the change was not applied").
- A constrained wall on a hidden level still moves with its component; it cannot be picked.
- Deleting a gridline cascade-deletes its constraints (one undo step).
- Copying a constrained wall set into another project keeps only internal constraints (D30).
- An opening on a solver-moved wall re-anchors via `invalidate_geometry()`.
- Grip 3 (width) drag on a constrained wall: width is not a variable -- the drag pins the whole item and changes thickness only.

## Follow-ups (filed at 4f)

- Property-panel rows: Opening level / alignment / Flip Hinge / Flip Facing; per-instance Stroke / Fill override + Clear (P2, G7).
- Wall hooks for Flip / Mirror / Scale / Offset / Trim / Extend (B2). Array is not needed: Array already copies walls (R2).
- Level refs in an elevation / section Editor (B1); Editor tools on a section scene (S1).
- Floor / roof / room / pipe constraint refs (G8).
- ~~Re-home or close the overlapping open lines~~ -- **done at the slice 1 Account (2026-10-26):** the superseded contextual-tab lines were closed; the Colour-UI cues, paper Viewport / Sheet Text and Underlay lines were re-worded to the property panel / paper context.
- Paste path skips Display Manager category defaults (pasted / duplicated / arrayed walls) -> folded into slice 2 (user ruling 2026-10-26, slice 1 smoke).
- Per-spec full rewrites for the six consolidated specs (Rule A pointers land at Account).
