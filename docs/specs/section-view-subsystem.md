---
status: current           # built 2026-10-20/21 on feature/section-views (merged to main 9666d69a); designed 2026-10-20
last-verified: 2026-10-24  # wall polish Account: s5.0 selection-never-plots pointer + known limit (mitered quad follows plan visibility) only; prior 2026-10-22  # gridline-hosted blocks Account: new s16, s3.2 / s7.1 / s14 pointers; prior 2026-10-22 paper section/plan parity Account: new s5.0 paper output only; prior 2026-10-21 Account: s6 glyphs/grips (D6r), s9 ALIGN/Ctrl + tab open, s8 push-after convention
verified-commit: 63a86f02   # wall polish (feature/wall-polish code tip); prior d44b0e11   # gridline-hosted blocks (ff merge, 0.60.0); prior dbd2e1a3 paper section/plan parity (AC1-AC5, ff merge fix/paper-section-parity); prior 9666d69a   # merge ff to main (smoke fix round a0bdc8dd + closes + 0.58.0)
applies-to:
  - firepro3d/section_scene.py      # git mv of elevation_scene.py (build)
  - firepro3d/section_manager.py    # git mv of elevation_manager.py (build)
  - firepro3d/section_marker.py     # git mv of view_marker.py (build)
  - firepro3d/elevation_view.py     # SectionView widget (file keeps the elevation_ name)
  - firepro3d/hosted_blocks.py      # gridline-hosted blocks: pure frame math (s16)
  - firepro3d/block_drop.py         # block drag payload decode + refusal, shared plan / section (s16)
source-tasks: [todo_open.md 952 section view subsystem, 872 angled gridlines, 600 sheet plot edge/void colours, 767 flat 2D geometry (closed stale), 560 _live_scenes accessor]
related: view-relationships.md (s4 taxonomy, s6 markers), paper-space.md (s6.2 paper render), display-manager spec (rows/columns)
---

# Section View Subsystem -- Design Spec

> Revision 2 (2026-10-20). Supersedes the 2026-04-29 proposal in place. Decisions ratified at the
> 2026-10-20 Phase 2 deltas grill (D1-D8, Q0) and the Phase 3 section approvals (S1-S5) are cited
> by id; everything else is design detail that may change at plan or build time.

## 1. Goal

Replace the cardinal-only elevation system with one section view subsystem: a vertical cut at any
angle in plan, defined by a marker the user places with two clicks, whose own crop box sets what the
view shows. The four cardinal elevations become permanent cardinal sections and keep their names.

## 2. Motivation (Q0)

AHJ submission sheets: place an angled marker on the plan, open it, check pipe / wall / floor
crossings and deflector clearance, host the section in a sheet viewport with its callout plotted.
Along the way the known gaps close: elevation markers never persisted (view-relationships s6.3),
only exactly-cardinal gridlines project (872), and elevation edges / voids plot in canvas colours on
sheets (600).

## 3. Architecture & Constraints

### 3.1 One view type, generalized in place (Approach A, S0)

`ElevationScene` / `ElevationView` / `ElevationManager` / `ViewMarkerArrow` / `SharedCropBox` /
`ViewMarkerManager` are not rewritten beside new modules; they are **moved and generalized**:

| Move (`git mv`) | Classes |
|---|---|
| `elevation_scene.py` -> `section_scene.py` | `ElevationScene` -> `SectionScene`, `ElevationView` -> `SectionView` (class in `elevation_view.py`, file name kept; in-scene item classes `ElevGridlineItem`, `_ElevProxyRect`, datum items keep their names) |
| `elevation_manager.py` -> `section_manager.py` | `ElevationManager` -> `SectionManager` |
| `view_marker.py` -> `section_marker.py` | `ViewMarkerArrow` + `SharedCropBox` + `ViewMarkerManager` -> `SectionMarker` |

A cardinal elevation is a `SectionScene` whose basis is cardinal. History, the HF1 colour-token
plumbing, halo, opening and slab rendering, and the gridline grips stay where they are; consumers
and the existing elevation tests re-bind by name.

### 3.2 Materialization

Unchanged from today: each section scene materializes its own `QGraphicsScene` from the data model
(view-relationships s5.3 pattern 2), rebuilt on a 100 ms debounce from `Model_Space.sceneModified`
and directly when its marker's geometry changes. Selection reads back to the source item through
`_ROLE_SOURCE`; no geometry editing in the section view, except the in-plane drag and Delete of a
gridline-hosted block copy (s16.4).

### 3.3 Constraints

- Cardinal sections render **identically** to today's elevations on today's elevation test scenes
  (acceptance d). The projection is origin-free (s4.1) so `h` values are bit-identical.
- No new Display Manager columns (D2b); the "Elevation Marker" row is relabelled "Section Marker"
  with its settings key unchanged (D8).
- No `SAVE_VERSION` bump: the project file gains a `sections` key, absence seeds cardinals (D4).
- No `_STATE_VERSION` bump: no dock or toolbar changes (S4 -- the 2026-04 "5 -> 6" item is dropped).
- No new `Model_Space` signals beyond the existing `openViewRequested(view_type, name)`.
- Cardinal view identity strings stay `"elevation"` + direction everywhere (s7.2) so saved sheets,
  the project browser and the existing tests need no migration.

## 4. Projection and classification (S1)

### 4.1 Basis

A section is `cut_a`, `cut_b`, `look_sign in {+1, -1}`, `depth_mm > 0` (world mm; the marker stores
plan-scene units -- s6 -- and `SectionScene` converts through `_scene_to_world` / ppm). Derived once per
rebuild from the marker:

```
D = unit(B - A)                      # along the cut line
N = look_sign * (-D.y, D.x)          # toward the look side ("behind" the cut)
L = |B - A|
h(p)  = p . D                        # origin-free: no (p - O) term
v(p)  = -z                           # Qt Y down
d(p)  = (p - A) . N                  # signed distance from the cut line; + = look side
sort_key = -d                        # toward the camera; ascending sort = farthest first
```

Cardinal equivalence (probed 2026-10-20 against `_world_to_elev` and the per-type depth chains):

| Cardinal | D | N | h | today's h | today's sort key |
|---|---|---|---|---|---|
| North | (-1, 0) | (0, -1) | -wx | -wx | +y = -d |
| South | (1, 0) | (0, 1) | wx | wx | -y = -d |
| East | (0, 1) | (-1, 0) | wy | wy | +x = -d |
| West | (0, -1) | (1, 0) | -wy | -wy | -x = -d |

`_register_depth_item` / `_assign_depth_z_values` are unchanged (ascending on the key, Z from -50
up by 0.01). Roofs keep their fixed Z, as today. Cut items register at `d = 0`.

### 4.2 Crop box = classification volume

The marker's crop box is the rectangle `h in [A.D, B.D]`, `d in [0, depth_mm]`; vertically a section
always spans all levels. Each item is classified by its **plan footprint** (wall mitered quad, pipe
segment, slab / roof polygon, node point):

| Zone | Rule | Rendering |
|---|---|---|
| **cut** | footprint intersects segment A->B (collinear overlap counts, at the overlap midpoint); point items are never cut | s5 cut column |
| **behind** | not cut; footprint intersects the box; projected extent clipped to `[h_A, h_B]` laterally, never vertically | s5 behind column (today's rendering) |
| **hidden** | otherwise: in front, beyond `depth_mm`, or laterally outside | not drawn |

Retired from the 2026-04 proposal: centroid zones, `CUT_TOLERANCE`, 500 mm lateral padding, numeric
far clip, 0.5 opacity for behind items.

### 4.3 Cardinal seed and auto-extent (S1 ruling)

Today the plan-side crop box seeds from the gridline bbox + `CROP_MARGIN` (2000 mm), falling back to
+/-10 000 mm, and **the elevation scene never filters on it**. To keep cardinals equal to today's
elevations the seed encloses everything: bbox of gridlines **and** all displayable plan items, plus
`CROP_MARGIN`; the cut line is the box edge on the camera side (North: `A = (x_max, y_max)`,
`B = (x_min, y_max)`); `depth_mm` = the box extent along N.

A cardinal marker carries `auto_extent = True`: while set, the box re-fits to the building on every
rebuild. The first grip edit on that marker clears it; from then on it is a plain crop box the user
owns, saved as such. Placed sections are never auto-extent.

## 5. Rendering (S2)

**Behind = today's projection rendering, unchanged** (DM *Colour* pen, DM *Fill* brush with the
wall's own colour as fallback, slab opaque mask + fill, opening void + frame), clipped laterally.
D2's recorded "outline, no fill" was reconciled at S2: applying it would change every cardinal
elevation and break acceptance (d). **Cut** adds the section columns only.

| Entity | cut | behind |
|---|---|---|
| Wall | cross-section rect: width = chord of the cut line through the mitered quad (along h), height = wall z-extent; brush = *Section colour* + *Section pattern* via `draw_section_hatch`; pen = Colour. A crossing inside an opening span draws only the wall above the head (and below the sill for windows) | today's rect + openings, clipped |
| Pipe | filled circle at the crossing, diameter = the pipe's drawn OD, Section colour | today's line |
| Sprinkler / node | never cut | today's glyph |
| Floor slab | chord x thickness rect, section hatch | today's mask + fill |
| Roof | **not cut-rendered in v1** (follow-up: mesh / plane intersection); a crossing roof shows as today's projected rect | today's rect, fixed Z |
| Gridline (872, D7a) | crossing of the infinite gridline with the cut line; drawn vertical at that h when it lies in `[h_A, h_B]`, bubble and label-keyed z-overrides as today; parallel or outside -> hidden. Replaces `_is_cardinal_for_elevation` | -- |
| Level datum | horizontal across `[h_A, h_B]` (replaces the cardinal-gated `_datum_extent`) | -- |

Shipped refinements of the table (plan reconciliations 2026-10-20, ratified at plan approval):

- **Pipe cut colour.** The cut circle uses the Pipe Display Manager *Section colour* when set; the
  Pipe row ships with no Section colour (`None`), so the circle falls back to the pipe's own line
  colour (the `PIPE_COLORS` lookup).
- **Cut wall draws the cross-section only.** The receding face of an obliquely crossed wall is not
  drawn in v1 (follow-up).
- **Concave slab chord.** The chord is `[min h, max h]` over every crossing of the cut segment with
  the slab boundary, so a concave slab's gap is filled in v1 (follow-up).

### 5.0 Paper output (AC1-AC5, 2026-10-22)

- **No scene background.** `SectionScene` paints no background brush (NoBrush, as `Model_Space`
  does); the app QSS paints the canvas behind the view, so a section viewport plots paper white.
- **Proxies plot through their paper row.** Projected items carry `_paper_cat` (Wall / Floor /
  Roof / Pipe / Sprinkler, opening items the opening's `display_category`) and take that category's
  whole paper row; elevation gridlines and level datums use the "Grid Line" / "Level Datum" rows.
  Mechanism owned by `paper-space.md` §9.9.1 (Rule A); not restated here.
- **Known gap: cut cross-sections do not occlude what lies behind them.** With the paper Wall Fill
  at "" (No Fill) a beyond-the-cut wall no longer paints an opaque body, so a farther wall shows
  through a nearer one. Tracked in `todo_open.md`, "Cut cross-sections occlude what lies behind them".
- **Known gap: hiding a paper row leaves some items on the sheet.** The opening void rect and the
  floor mask are untagged, so hiding their paper row does not hide them. Tracked in `todo_open.md`,
  "A hidden paper row leaves section opening voids and floor masks on the sheet".
- **Selection never plots.** The section scene's selection outlines (colour-source mixin, elevation
  gridlines, level datums) are guarded on paper; contract owned by `paper-space.md` §6.2 (Rule A).
- **Known limit: the section view's mitered wall quad follows plan visibility.** Sections read
  `wall.mitered_quad()` (`section_scene.py`), which joins only against walls visible in the plan
  scene (`wall-room-floor-system.md` §5.2), so a wall on a hidden level is not mitred into a
  projected section wall. Filed as a follow-up; not addressed by wall polish.

### 5.1 Sheet plot colours (600)

Three baked colours -- `_edge_color` (hex picked by canvas luminance), the opening-void brush
(`backgroundBrush()`), the slab mask (`QColor(canvas_bg)`) -- become **colour sources resolved per
paint** through the HF1 mechanism the wall and slab fills already use (`set_colour_src` /
`resolve_colour`): a surface-relative *foreground* source for edges, a *background* source for voids
and masks. On screen they resolve to the theme; in a sheet viewport to black / white. Whether
`colour_tokens` already defines such a pair is a P4 probe and the first plan task.

## 6. SectionMarker (S3)

`SectionMarker(QGraphicsItem)` in `section_marker.py`. Fields: `name`, `cut_a`, `cut_b`,
`look_sign`, `depth`, `cardinal` (`"north" | "south" | "east" | "west" | None`), `auto_extent`
(cardinals only), `gridline_z_overrides` (moved here from the scene so they persist).
`cut_a`, `cut_b`, `depth` are **plan-scene units** (mm at ppm 1; the `DetailMarker.crop_rect`
convention) -- G1 review ruling 2026-10-20, recorded as plan reconciliation 2026-10-20 (ratified at
plan approval): s4.1's "world mm" is the derived basis, converted at `SectionScene` with
`_scene_to_world` (Y sign flip); `CROP_MARGIN`, `MIN_CUT_LEN`, `FALLBACK_HALF` likewise.

- Shown on every plan level (a section cuts all levels).
- `PAPER_EXCLUDED = True` **only when `cardinal` is set** (view-relationships s6.4: cardinal markers
  never plot; placed sections plot by the default path). `_exclude_from_bulk_select = True`.
- Visual -- two glyphs (smoke ruling 2026-10-21, served-tuner mockup; supersedes the D6 "carried
  over" wording that Phase 3 approved from text alone):
  - **Cardinal**: the pre-build `ViewMarkerArrow` look unchanged -- one circle of radius
    `3 x BUBBLE_RADIUS_MM` with the cardinal letter and a filled wedge (tangents at +/-40 deg)
    whose tip sits 25 mm outside its own crop-box edge on the edge's midline
    (`_R_CARDINAL`, `_WEDGE_DIST`, `_CARDINAL_GAP`). No cut line is drawn for a cardinal.
  - **Placed section**: the cut line (solid cosmetic) with a CAD-standard head at each end -- a
    bubble of radius `2 x BUBBLE_RADIUS_MM` centred on the endpoint and a full filled triangle
    whose base lies on the cut line through the centre, sides tangent to the circle, equal
    stick-out all round (half-base = height = `R * sqrt(2)`, `_R_SECTION`, `_TRI`), apex on
    the look side; the label (last token of the name) is rotated to read along the cut and
    flipped 180 deg when the line points left so it is never upside down.
  - Both: the crop box (SharedCropBox's dashed look) and grips only while selected.
- Grips -- the crop box edits **as a rectangle in the cut frame** (DetailMarker's 8-grip layout;
  corners are never independent -- smoke ruling 2026-10-21): `0` A / `1` B (near corners: that
  end slides along the cut and the whole cut line moves along N, the far edge fixed), `2` / `3`
  far corners (the end slides along the cut, `depth` changes), `4` near-edge midpoint (the cut
  line moves along N, far edge fixed), `5` / `7` side midpoints (B / A slide along the cut only),
  `6` far-edge midpoint (`GRIP_DEPTH`: constrained along N, sets `depth`), `8` flip
  (`GRIP_FLIP`: the click-only `FlipGripHandle` toggling `look_sign`). Corners render round, edge
  midpoints square (`default_grip_handles`). Cut length and `depth` floor at `MIN_CUT_LEN`; an end
  never crosses the other (signed length along the cut before the drag must stay `>= MIN_CUT_LEN`,
  else the drag frame is refused), so a grip never flips the look side.
  Whole-marker translate through `manip_translate`. Any grip edit on a cardinal clears
  `auto_extent`.
- Double-click emits `openViewRequested("elevation", direction)` for a cardinal and
  `openViewRequested("section", name)` otherwise.
- Context menu (new; no marker has one today): **Open - Rename - Flip - Delete**. Cardinals:
  Rename and Delete disabled (D5b, D8). Rename cascades by name to the open tab title and any sheet
  viewport bound as `section:<name>`. Delete closes the tab and removes the marker.
- Property panel (`get_properties`, DetailMarker pattern): Name, Depth (mm, `ScaleManager`
  formatters), Flip toggle, read-only Cardinal.
- Undo: grip commits (the manipulator's commit hook) and menu Flip / Rename / Delete call
  `push_undo_state` **after** mutating -- the post-action snapshot convention (s8; G3 ruling
  2026-10-20). Rename pushes only when the name actually changed.

## 7. SectionManager and consumers (S4)

### 7.1 Manager

`SectionManager(QObject)` in `section_manager.py` owns `markers: dict[name, SectionMarker]` and
`_views: dict[name, (SectionScene, SectionView)]`.

```
seed_cardinals()                      # creates any missing N/S/E/W marker, auto_extent=True
place_section(a, b) -> SectionMarker  # "Section N", look_sign=+1, depth seeded (s9)
open_section(name) -> SectionView     # tab "Elevation: North" | "Section: Section 1" (D8)
close_section(name); close_all(); clear()
get_view(name); get_scene(name); get_or_build_scene(name)   # tab-less scene for sheets
open_names; open_scenes               # public (560) -- replaces main._live_scenes reading em._views
delete_section(name); rename_section(old, new); rebuild_all()
focus_hosted(inst) -> bool            # Model browser row of a hosted block (s16.6)
to_list() -> list[dict]; from_list(data)
sectionsChanged = pyqtSignal()        # place / rename / delete -> project browser refresh
```

`SectionScene(marker, model_space, level_manager, scale_manager)` reads the marker's geometry at each
rebuild; the manager calls the open scene's `_schedule_rebuild` after a marker grip edit.
`conftest.elevation_scene_for` becomes `section_scene_for(direction="north")`, building a cardinal
marker; tests re-bind by name.

### 7.2 View identity (no migration)

| View | type | name | tab | browser | viewport id |
|---|---|---|---|---|---|
| cardinal | `"elevation"` | `North`.. | `Elevation: North` | Elevations group (static four) | `elevation:North` |
| placed | `"section"` | `Section 1`.. | `Section: Section 1` | new **Sections** group, italic when hosted | `section:Section 1` |

`main._on_open_view_requested` routes both; `ViewResolver.resolve` gains the `"section"` branch and
both branches call `get_or_build_scene` (today `_resolve_elevation` returns `None` for a closed tab,
which would leave a sheet blank after reload -- acceptance a). `resolve_level_context` and
`SheetViewport` treat `"section"` exactly as `"elevation"` (own scene, no isolation).

### 7.3 Other consumers

- `display_manager._is_elevation_marker` and `paper_display._category_for_item` match
  `"SectionMarker"` instead of `"ViewMarkerArrow"`; row label "Section Marker", key kept.
- `rebuild_all` call sites bind to `scene._section_manager`.
- `main.py`: the three `_create_elevation_markers()` calls become `seed_cardinals()` after load;
  `_views.clear()` / `_views.pop` become `close_all()` / `close_section()`; `_live_scenes` reads
  `open_scenes`; the ribbon gains a "Section" `add_small_button` in the Build group beside Detail
  with a `_mode_buttons["section"]` entry. No section icon asset exists: the button reuses
  `detail_icon.svg` (plan reconciliation 2026-10-20; dedicated asset is a follow-up).
- `docs/gen_ref_pages.py`, `SPEC-INDEX.md` and view-relationships s4 / s6 are updated at Account.

## 8. Persistence and undo

**Project file (D4).** `scene_io` payload gains `"sections": [marker.to_dict() ...]` with keys
`name, cut_a, cut_b, look_sign, depth, cardinal, auto_extent, gridline_z_overrides`. Load:
`payload.get("sections")` -> `from_list` when present, then `seed_cardinals()` always (an old file
or one missing a cardinal gets it re-seeded). No `SAVE_VERSION` bump.

**Undo (acceptance e).** `Model_Space._capture_network` snapshots no markers today (detail markers
included). It gains a `"sections"` entry (`to_list()`); restore diffs by name -- update survivors'
geometry, remove deleted, re-add missing -- and leaves open tabs alone. Detail-marker undo stays out
(follow-up).

## 9. Placement tool (D5)

Mode `"section"` beside `"detail"` in `Model_Space`'s dispatch dicts. `_press_section` /
`_move_section` mirror `_press_detail` / `_move_detail`: click 1 anchors A (snapped), a dashed
preview line with a look-side hint follows the cursor; click 2 sets B -> `place_section(A, B)`:
`look_sign = +1`, `depth` = the building extent beyond the line (`max((c - A) . N)` over the
building bbox corners; 10 000 mm when nothing lies on that side), then the new section's tab is
opened (`open_section`; plan reconciliation R6 -- VC9 M2, recorded 2026-10-21: the user lands in
the view they just cut), `push_undo_state`, back to `select`. `|AB| < 100 mm` is rejected with a status message. Esc cancels. Status text follows the
detail tool's wording. The second point aligns like `draw_line` (smoke ruling 2026-10-21): the
first click is the ALIGN anchor (`PlacementInputCoordinator._mode_placement_anchor` has a
`"section"` branch, so the H/V rays and the align-placement glyphs fire), and Ctrl constrains the
cut to `_snap_angle_deg` increments through `_constrain_angle` on both the preview and the commit.

## 10. Acceptance Criteria

- [ ] (a) A placed section hosts in a sheet viewport (`section:<name>`) after save / reload; its marker plots on the host plan; cardinal markers never plot.
- [ ] (b) 600: a dark-theme sheet viewport of a cardinal section `export_pdf`s edges black and opening voids / slab masks white.
- [ ] (c) 560: `SectionManager.open_scenes` (and the schematic counterpart) are public; `_live_scenes` reads no private attribute.
- [ ] (d) Cardinal sections produce identical scenes to today's elevations on the existing elevation test scenes (17 files / 161 tests re-bound and green).
- [ ] (e) Marker place / grip move / flip / delete are each undoable.
- [ ] (f) A project without a `sections` key seeds exactly four cardinals; round-trip restores markers, crop boxes, overrides.
- [ ] 872: a gridline crossing the cut line draws vertical at the crossing; a parallel one is hidden.
- [ ] Two-click "Section" tool creates `Section 1`, `Section 2`, ...; cardinals cannot be deleted or renamed.
- [ ] Cut items carry Section colour + pattern; behind items carry today's rendering, laterally clipped.
- [ ] 767 closed as stale (2D primitives are level-less, containment C3).

## 11. Verification Checklist

- [x] Guard tests of s12 each shown RED with the rule reverted (VC3) -- per group G1-G5 + the 2026-10-21 smoke fix round (8 guards).
- [x] Whole-repo grep for every retired name (s3.1 table, `_create_elevation_markers`, `_is_cardinal_for_elevation`, `_world_to_elev`) returns only history notes (G5 Task 14; VC9 seam 5).
- [x] Launch smoke 2026-10-21: cardinals, 45 deg section, grips, placement ALIGN/Ctrl -- re-entered Phase 2 for the marker visuals (D6r) and passed on the fix round ("good enough for now").
- [x] Old project loads with four cardinals; new project saves and reloads a placed section (guards in `test_section_persistence.py`; smoke row).
- [ ] Full suite on the final tree (VC6): **not run** -- skipped on the user's instruction 2026-10-21 (keep-green 321 + 290 + 91 and VC7 proofs only). Known pre-existing: `test_empty_click_deselects` (order flake), `test_block_drag_drop::test_space_rotates...`, `test_modify_tools_shortcuts::test_flip_mirror_keys...` -- each proved at base 98f0dc09, filed.

## 12. Test Strategy (S5)

| File | Guards |
|---|---|
| `test_section_projection.py` | four cardinals vs the pre-rename `_world_to_elev` table (absolute h); 45 deg h / d on hand-computed points; painter order for three walls at increasing depth |
| `test_section_classification.py` | real Wall / Pipe / FloorSlab on a cardinal and a 45 deg cut: cut / behind / hidden by footprint; lateral clip; parallel-adjacent wall is behind; auto-extent re-fits after a wall is added and stops after a grip edit |
| `test_section_rendering.py` | cut wall brush = Section colour + pattern; behind wall brush = Fill; cut through an opening leaves the head; pipe cut-circle diameter |
| `test_gridline_section.py` | 30 deg gridline -> vertical at crossing h; parallel absent; crossing outside `[h_A, h_B]` absent |
| `test_section_sheet_plot.py` | dark theme, sheet viewport `export_pdf`: pixel probe edges black, void / mask white |
| `test_section_marker.py` | rect grips 0-8 (opposite corner fixed, ends never cross, depth/flip); head tangency + apex side; cardinal wedge tip 25 mm outside its edge; label angle; `shape()` covers the glyphs; cardinal grip clears `auto_extent`; `to_dict` round-trip; `PAPER_EXCLUDED` only on cardinals; menu Delete / Rename disabled on cardinals |
| `test_section_persistence.py` | `scene_io` round-trip; missing key seeds four; one missing cardinal re-seeded |
| `test_section_undo.py` | place / grip / flip / delete undoable; open tab untouched |
| `test_section_placement.py` | two clicks -> `Section 1`, `Section 2`; `< 100 mm` rejected; Esc cancels |
| existing `test_elev_*` and coupled suites | cardinal-equivalence net, re-bound by name |

Plan groups (FP6): G1 rename + basis + classification; G2 rendering + 872 + 600; G3 marker + grips
+ placement + undo + menu; G4 manager + consumers + persistence + browser / ribbon; G5 Account.
First plan task probes the P4 items: `colour_tokens` surface-relative pair, how grip handles push
undo elsewhere, the pipe OD source, marker level-visibility path.

## 13. Edge Cases

- Empty section: only datums and gridlines (no special handling).
- Scale not calibrated: `_ppm()` falls back to 1.0 as today.
- Wall parallel to and touching the cut line: collinear overlap counts as cut (s4.2).
- Pipe exactly along the cut line: cut, circle at the overlap midpoint.
- Coincident / sub-100 mm A, B: rejected at placement; `SectionScene` asserts `L > 0`.
- A cardinal with `auto_extent` and an empty project: the +/-10 000 mm fallback box.
- Hand-edited file missing a cardinal: `seed_cardinals()` restores it.

## 14. Out of Scope (v1) -- filed as follow-ups at Account

Roof cut-render (mesh / plane); cut vs projection line-weight DM columns (D2b); detail-marker undo;
jogged / stepped sections; break lines; in-view dimensions; geometry editing in the section view
(beyond the hosted-block drag / Delete of s16.4); vertical crop handles. SB4c / SB4d / HF5 lines are re-worded to the new module names.

## 15. Design-decision ledger

| Id | Decision | Gate |
|---|---|---|
| Q0 | AHJ sheet sections are the workflow | Phase 2 grill 2026-10-20 |
| D1 / D1b | cardinals become permanent sections with four independent markers; elevation classes retire | Phase 2 |
| D2 / D2b | cut vs behind through existing DM columns only; behind keeps today's rendering | Phase 2, reconciled S2 |
| D3 | depth = the section's own crop box in plan, seeded to the building extent | Phase 2 |
| D4 | new `sections` key, no `SAVE_VERSION` bump | Phase 2 |
| D5 / D5b | Section button beside Detail; cardinals permanent | Phase 2 |
| D6 | bespoke bubble / datum / hatch visuals carried over; marker glyphs superseded by D6r | Phase 2 |
| D6r | cardinal = old ViewMarkerArrow glyph on its own box; section = 2x bubble on each endpoint + tangent triangle (R*sqrt(2)), label along the cut; crop box edits as a rect | smoke ruling 2026-10-21, served tuner |
| D7a / D7b | gridlines crossing the cut project; 767 stale | Phase 2 |
| D8 | cardinals keep "Elevation" naming; one DM marker row relabelled | Phase 2 |
| S0 | Approach A: generalize in place + git mv | Phase 3 |
| S1 | origin-free basis; footprint classification by crop box; cardinal auto-extent until touched | Phase 3 |
| S2 | rendering table; roof cut-render deferred; 600 via per-paint colour sources | Phase 3 |
| S3 | SectionMarker, 4 grips (superseded by D6r: 8 rect grips + flip) incl. FlipGripHandle, undo via network snapshot, context menu | Phase 3 |
| S4 | cardinals keep `"elevation"` identity; `get_or_build_scene` for sheets; no `_STATE_VERSION` bump | Phase 3 |
| S5 | module moves, guard tests, FP6 groups | Phase 3 |
| R1 | marker stores plan-scene coordinates; `SectionScene` converts to world via `_scene_to_world` (s6) | plan reconciliation 2026-10-20, ratified at plan approval |
| R2 | pipe cut circle: Pipe *Section colour* when set, else the pipe's own line colour (s5) | plan reconciliation 2026-10-20, ratified at plan approval |
| R3 | cut wall draws the cross-section rect only; no receding face in v1 (s5) | plan reconciliation 2026-10-20, ratified at plan approval |
| R4 | slab chord = `[min h, max h]` over all boundary crossings; concave gap filled in v1 (s5) | plan reconciliation 2026-10-20, ratified at plan approval |
| R5 | ribbon Section button reuses `detail_icon.svg` (s7.3) | plan reconciliation 2026-10-20, ratified at plan approval |

## 16. Gridline-hosted blocks (2026-10-22)

A block placed in a section is **model data hosted on a reference gridline parallel to the cut**, not
view-owned: every parallel view shows it and it follows its gridline. This section is the one home
for how sections project, place, edit and focus hosted blocks. The record, its derived plan pose and
the property rows are owned by `block-system.md` ("Gridline-hosted instances"); the gridline uid,
follow-host hook and delete cascade by `grid-system.md` (s18); the save keys by `scene-io.md`. Design
(ratified source): `docs/superpowers/specs/2026-10-22-gridline-hosted-blocks-design.md`. This does
not add a third hosting pattern: sections still materialize model data (view-relationships s5.3
pattern 2); plan blocks without a `host` are still not projected into sections.

### 16.1 Projection (`SectionScene._project_hosted_blocks`)

Runs in `rebuild()` right after the walls step. For every model `BlockInstance` with a valid `host`
whose gridline resolves and is **parallel to the cut** (`hosted_blocks.is_parallel`, so cardinals and
placed sections alike; anti-parallel counts):

- **Pose** (`hosted_blocks.section_pose`): h = the lateral projection of the derived world point,
  v = `-elevation_mm`, depth = distance behind the cut. Outside `0 <= depth <= basis.depth` the block
  is not drawn (depth crop; also in front of the cut).
- **Facing:** a view from the host's other side (`facing_of(basis, gl) != host["facing"]`) draws the
  copy mirrored left-to-right: `mirrored` flipped and rotation negated (text reads backwards, accepted).
- **Copy:** a `_HostedBlockCopy` (a `BlockInstance` subclass) built from the model record with `host`
  popped, `_ROLE_SOURCE` = the model block, scaled by `block_scale / ppm` (section scene is mm). It is
  selectable (halo / manipulator like other section copies). `SectionScene._hosted_copies` maps
  `id(model block)` to its copy.
- **Lateral clip:** a copy whose bounds cross `[h_min, h_max]` is parented to a clipping rect
  (`ItemClipsChildrenToShape`); entirely outside is skipped. No vertical clip (filed with the crop-handle
  follow-up).
- **Painter order:** registered through `_register_depth_item` at the host point's `sort_key`.

### 16.2 Display and plot

On screen the copy always shows (no on-screen Blocks visibility toggle exists). On a sheet it
categorises as the paper **Blocks** row (`paper_display` `isinstance BlockInstance`), so the paper
Blocks row's visibility and weight govern it. In plan and 3D the model block is hidden (block-system).

### 16.3 Placement

Two entry paths, both resolving the host with `hosted_blocks.choose_host`: the parallel gridline
nearest the cut with `0 <= depth <= basis.depth`, and the point inside `[h_min, h_max]`
(`SectionScene._hosted_target`). The record is `host_at`: offset 0, along from the cursor h, elevation
from the cursor v (section `-y`), facing from this section's look side. No qualifying gridline ->
refused: no-drop cursor on a drag, nothing on a click, footer status `HOSTED_REFUSAL`.

- **Drop:** `SectionView` accepts `MIME_BLOCK` (`dragEnterEvent` / `dragMoveEvent` / `dropEvent`);
  payload decode and refusal come from `block_drop` (`place_refusal` still gates), the same code the
  plan view uses. Drop commits through `SectionScene.place_hosted_block`.
- **Activate + click:** `MainWindow` placement activation with a `SectionView` tab current calls
  `SectionScene.begin_place_block(block_id)` instead of arming the plan scene. A translucent ghost
  follows the cursor (faded when no host is in reach); Space / Shift+Space rotate 90 deg; the arrow keys
  flip across the screen axes (Left / Right left-right, Up / Down top-bottom; each press toggles; same
  pose algebra as `Model_Space.flip_place_block`); click places via `click_place_block` and stays armed;
  Esc ends it. A rebuild re-arms the ghost with its rotation, mirror and last point. Leaving the tab
  cancels the armed placement (`MainWindow._on_tab_changed`).
- **Esc routing:** `MainWindow._on_escape` ends a SectionView's armed placement
  (`cancel_place_block`) before the `_active_scene()` path, because `_active_scene()` answers the plan
  scene for section tabs. `SectionView.keyPressEvent` handles Esc / Space / arrows when it has focus.
- **Footer and panel:** `SectionScene.modeChanged = pyqtSignal(str)` emits `"place_block"` on arm and
  `"select"` on cancel. `MainWindow._on_section_scene_built` connects it to `_update_mode_label` (the
  PLACE BLOCK badge; text from `_MODE_INSTRUCTIONS["place_block"]`) and `_on_mode_changed_template`
  (the plan's property-panel clear).
- **Snap:** `snap_section_point` snaps X to gridline verticals and Y to level datums, each axis
  independently within the shared OSNAP aperture (so a point near both lands on the crossing). It does
  not use `SnapEngine.find`.
- **Commit:** `Model_Space.place_block_instance(..., host=...)` + `push_undo_state()`, then rebuild and
  select the new copy.

### 16.4 Selecting, dragging, deleting

- A copy picks through `_ROLE_SOURCE`; `entitySelected` carries the model block to the Properties panel
  (rows: block-system).
- **In-plane drag:** `_HostedBlockCopy.translate` -> `SectionScene._move_hosted_source` maps (dh, dv)
  to `along_mm` (by `h_sign`) and `elevation_mm`; host and offset are untouched, so a locked host
  gridline still lets the block move. One undo step per gesture (the manipulator release hook flushes it;
  a `QTimer` is the fallback for a bare translate).
- **Delete:** `MainWindow`'s Delete handler routes a `SectionView` tab to
  `SectionScene._delete_elev_selected` (it must not fall through to `_active_scene()`, the plan scene).
  Hosted copies go to `Model_Space.delete_items` by explicit list (a plan-hidden block cannot be
  `setSelected`), in one undo step; the plan selection is saved and restored around it.

### 16.5 Edge cases

Unresolved or malformed host (`valid_host`): not drawn, not placeable. A section rotated so the host is
no longer parallel simply stops drawing the block. Equidistant parallel gridlines: first in model order
wins. Locked host: the gridline cannot move, so neither do its blocks.

### 16.6 Browser focus (`SectionManager.focus_hosted`)

The Model browser row of a hosted block (`model-browser.md`) calls `focus_hosted(inst)`. Candidate views
in order: open tabs, then cardinals, then placed sections by name. A marker whose cut is not parallel to
the host gridline is skipped without building; the rest are rebuilt and tested via
`_hosted_copies`; a tab-less scene that does not show the block is dropped again. The first hit opens
its tab and selects the copy. None -> footer status "No section shows this block (its gridline *label*
isn't parallel to any view)." and the method returns False.
