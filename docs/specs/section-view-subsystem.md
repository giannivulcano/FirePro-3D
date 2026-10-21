---
status: proposal          # designed 2026-10-20 (Phase 3 of the section-view build); flips to current at Account
last-verified: 2026-10-20
verified-commit: aeab43ff   # design probes ran against this HEAD (pre-build)
applies-to:
  - firepro3d/section_scene.py      # git mv of elevation_scene.py (build)
  - firepro3d/section_manager.py    # git mv of elevation_manager.py (build)
  - firepro3d/section_marker.py     # git mv of view_marker.py (build)
  - firepro3d/elevation_view.py     # SectionView widget (file keeps the elevation_ name)
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
`_ROLE_SOURCE`; no geometry editing in the section view.

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
- Visual (D6, carried over): cut line (solid cosmetic), the existing arrow-head polygon at each end
  pointing to the look side, a bubble at A and B carrying the name -- always drawn; the crop box
  (SharedCropBox's dashed look) and grips only while selected.
- Grips -- DetailMarker's protocol (`grip_points / apply_grip / manip_bounds / manip_handles /
  manip_translate`): `0` A, `1` B (endpoint style: that end moves, the line pivots on the other, the
  box follows), `2` far-edge midpoint (constrained along N, sets `depth`), `3` flip -- a new
  click-only `FlipGripHandle` in `manip_handle.py` (none exists) toggling `look_sign`. Whole-marker
  translate through `manip_translate`. Any grip edit on a cardinal clears `auto_extent`.
- Double-click emits `openViewRequested("elevation", direction)` for a cardinal and
  `openViewRequested("section", name)` otherwise.
- Context menu (new; no marker has one today): **Open - Rename - Flip - Delete**. Cardinals:
  Rename and Delete disabled (D5b, D8). Rename cascades by name to the open tab title and any sheet
  viewport bound as `section:<name>`. Delete closes the tab and removes the marker.
- Property panel (`get_properties`, DetailMarker pattern): Name, Depth (mm, `ScaleManager`
  formatters), Flip toggle, read-only Cardinal.
- Undo: grip commits and menu Flip / Delete call `push_undo_state` before mutating (s8).

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
building bbox corners; 10 000 mm when nothing lies on that side), `push_undo_state`, back to
`select`. `|AB| < 100 mm` is rejected with a status message. Esc cancels. Status text follows the
detail tool's wording.

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

- [ ] Guard tests of s12 each shown RED with the rule reverted (VC3).
- [ ] Whole-repo grep for every retired name (s3.1 table, `_create_elevation_markers`, `_is_cardinal_for_elevation`, `_world_to_elev`) returns only this spec's history notes.
- [ ] Launch smoke: open each cardinal, place a 45 deg section, open it, host it on a sheet, export dark-theme PDF.
- [ ] Old project loads with four cardinals; new project saves and reloads a placed section.
- [ ] Full suite green on the final tree (VC6), the VC7-proved `test_empty_click_deselects` order flake excepted (filed, not patched).

## 12. Test Strategy (S5)

| File | Guards |
|---|---|
| `test_section_projection.py` | four cardinals vs the pre-rename `_world_to_elev` table (absolute h); 45 deg h / d on hand-computed points; painter order for three walls at increasing depth |
| `test_section_classification.py` | real Wall / Pipe / FloorSlab on a cardinal and a 45 deg cut: cut / behind / hidden by footprint; lateral clip; parallel-adjacent wall is behind; auto-extent re-fits after a wall is added and stops after a grip edit |
| `test_section_rendering.py` | cut wall brush = Section colour + pattern; behind wall brush = Fill; cut through an opening leaves the head; pipe cut-circle diameter |
| `test_gridline_section.py` | 30 deg gridline -> vertical at crossing h; parallel absent; crossing outside `[h_A, h_B]` absent |
| `test_section_sheet_plot.py` | dark theme, sheet viewport `export_pdf`: pixel probe edges black, void / mask white |
| `test_section_marker.py` | grips 0-3; cardinal grip clears `auto_extent`; `to_dict` round-trip; `PAPER_EXCLUDED` only on cardinals; menu Delete / Rename disabled on cardinals |
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
jogged / stepped sections; break lines; in-view dimensions; geometry editing in the section view;
vertical crop handles. SB4c / SB4d / HF5 lines are re-worded to the new module names.

## 15. Design-decision ledger

| Id | Decision | Gate |
|---|---|---|
| Q0 | AHJ sheet sections are the workflow | Phase 2 grill 2026-10-20 |
| D1 / D1b | cardinals become permanent sections with four independent markers; elevation classes retire | Phase 2 |
| D2 / D2b | cut vs behind through existing DM columns only; behind keeps today's rendering | Phase 2, reconciled S2 |
| D3 | depth = the section's own crop box in plan, seeded to the building extent | Phase 2 |
| D4 | new `sections` key, no `SAVE_VERSION` bump | Phase 2 |
| D5 / D5b | Section button beside Detail; cardinals permanent | Phase 2 |
| D6 | bespoke marker / bubble / datum / hatch visuals carried over | Phase 2 |
| D7a / D7b | gridlines crossing the cut project; 767 stale | Phase 2 |
| D8 | cardinals keep "Elevation" naming; one DM marker row relabelled | Phase 2 |
| S0 | Approach A: generalize in place + git mv | Phase 3 |
| S1 | origin-free basis; footprint classification by crop box; cardinal auto-extent until touched | Phase 3 |
| S2 | rendering table; roof cut-render deferred; 600 via per-paint colour sources | Phase 3 |
| S3 | SectionMarker, 4 grips incl. FlipGripHandle, undo via network snapshot, context menu | Phase 3 |
| S4 | cardinals keep `"elevation"` identity; `get_or_build_scene` for sheets; no `_STATE_VERSION` bump | Phase 3 |
| S5 | module moves, guard tests, FP6 groups | Phase 3 |
| R1 | marker stores plan-scene coordinates; `SectionScene` converts to world via `_scene_to_world` (s6) | plan reconciliation 2026-10-20, ratified at plan approval |
| R2 | pipe cut circle: Pipe *Section colour* when set, else the pipe's own line colour (s5) | plan reconciliation 2026-10-20, ratified at plan approval |
| R3 | cut wall draws the cross-section rect only; no receding face in v1 (s5) | plan reconciliation 2026-10-20, ratified at plan approval |
| R4 | slab chord = `[min h, max h]` over all boundary crossings; concave gap filled in v1 (s5) | plan reconciliation 2026-10-20, ratified at plan approval |
| R5 | ribbon Section button reuses `detail_icon.svg` (s7.3) | plan reconciliation 2026-10-20, ratified at plan approval |
