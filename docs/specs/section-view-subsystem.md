---
status: current           # built 2026-10-20/21 on feature/section-views (merged to main 9666d69a); designed 2026-10-20
last-verified: 2026-11-11  # paper-as-authored Account: s5 cut-symbol paper fill sentence only (per-row As Authored), rest not re-audited; prior 2026-11-11  # elevation-parity Account: s3.2, s5 gridline / datum rows, s6 fields, s8 records + label migration, s14 out-of-scope wording, s16.3 snap + Esc + footer bullets, s16.4, new s17 (routing, modify host, shared undo, selection look / readout, snap, Hide pass, Notes, context menu, ends); rest not re-audited; prior 2026-11-06  # Materials Account: s5 Wall and Floor rows link materials.md, rest not re-audited; prior 2026-11-05  # section piping Account: s4.2 pipe note, s5 Pipe row + pipe rules, s13 pipe edge case, R2 superseded, applies-to only, rest not re-audited; prior 2026-11-04  # SB4d Account: s5 depth-walk + annotation draw-order pointer, s6 glyphs / panel / persistence (heads are System blocks, upright label), s3.3 / s7.3 DM-row notes only, rest not re-audited; prior 2026-11-03  # SB4c Account: s5 projection table gridline / level datum rows, s5.0 paper-row sentence + selection-plumbing bullet, D6 dated note only, rest not re-audited; prior 2026-10-31  # floor-opening Account: s5 Floor slab row + "Slab with floor voids" refinement only, rest not re-audited; prior 2026-10-24  # wall polish Account: s5.0 selection-never-plots pointer + known limit (mitered quad follows plan visibility) only; prior 2026-10-22  # gridline-hosted blocks Account: new s16, s3.2 / s7.1 / s14 pointers; prior 2026-10-22 paper section/plan parity Account: new s5.0 paper output only; prior 2026-10-21 Account: s6 glyphs/grips (D6r), s9 ALIGN/Ctrl + tab open, s8 push-after convention
verified-commit: e2d57467   # paper-as-authored Account (0.99.0; one sentence only); prior 6dc388ed   # elevation-parity close (0.98.0; sections above only); prior b9ce2e00   # Materials merge on main (v0.94.0); prior 539eda40   # section piping on main (v0.91.0); prior 5185b8cc   # SB4d merge on main (v0.86.0) + seed restyle; prior 8d95a864   # SB4c merge on main (v0.83.0); prior 1c1e59c6   # floor-opening (v0.76.0, merged to main); prior 63a86f02   # wall polish (feature/wall-polish code tip); prior d44b0e11   # gridline-hosted blocks (ff merge, 0.60.0); prior dbd2e1a3 paper section/plan parity (AC1-AC5, ff merge fix/paper-section-parity); prior 9666d69a   # merge ff to main (smoke fix round a0bdc8dd + closes + 0.58.0)
applies-to:
  - firepro3d/section_scene.py      # git mv of elevation_scene.py (build)
  - firepro3d/section_manager.py    # git mv of elevation_manager.py (build)
  - firepro3d/section_marker.py     # git mv of view_marker.py (build)
  - firepro3d/section_pipe_symbols.py # section piping: symbol paths + line trim
  - firepro3d/elevation_view.py     # SectionView widget (file keeps the elevation_ name)
  - firepro3d/hosted_blocks.py      # gridline-hosted blocks: pure frame math (s16)
  - firepro3d/block_drop.py         # block drag payload decode + refusal, shared plan / section (s16)
  - firepro3d/modify_host.py        # ModifyHostMixin: the host contract SectionScene mounts (s17; owned by scene-tools.md I1)
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
`_ROLE_SOURCE`. **Delete is not restricted** -- it removes any selected source in one undo step
(elevation-parity R2; s16.4). **Geometry edits are**: walls, pipes, sprinklers, slabs and roofs stay
read-only projections (`view-relationships.md` s3.1). What a section edits is its **write-back copies**
-- gridline-hosted block copies and section Notes -- plus gridline / level-datum ends (s17).

### 3.3 Constraints

- Cardinal sections render **identically** to today's elevations on today's elevation test scenes
  (acceptance d). The projection is origin-free (s4.1) so `h` values are bit-identical.
- No new Display Manager columns (D2b); the "Elevation Marker" row is relabelled "Section Marker"
  with its settings key unchanged (D8). **Superseded by SB4d:** the row is split into
  "Elevation Marker" (cardinals) and "Section Marker" (placed sections) plus "Detail Marker",
  all line-only (`grid-system.md` 10.1).
- No `SAVE_VERSION` bump: the project file gains a `sections` key, absence seeds cardinals (D4).
- No `_STATE_VERSION` bump: no dock or toolbar changes (S4 -- the 2026-04 "5 -> 6" item is dropped).
- No new `Model_Space` signals beyond the existing `openViewRequested(view_type, name)` *(at the
  2026-10-20 build; elevation parity later added `Model_Space.hiddenChanged`, s17.6)*.
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

`_register_depth_item` / `_assign_depth_z_values` keep the ascending-key walk (Z from -50 up by
0.01) but the walk is now **clamped at `Z_DEPTH_CEIL`** so projected model items never reach the
annotation band (SB4d; the band and the bound: [`view-relationships.md`](view-relationships.md)
7.3). Roofs keep their fixed Z, as today. Cut items register at `d = 0`.

### 4.2 Crop box = classification volume

The marker's crop box is the rectangle `h in [A.D, B.D]`, `d in [0, depth_mm]`; vertically a section
always spans all levels. Each item is classified by its **plan footprint** (wall mitered quad, pipe
segment, slab / roof polygon, node point):

| Zone | Rule | Rendering |
|---|---|---|
| **cut** | footprint intersects segment A->B (collinear overlap counts, at the overlap midpoint); point items are never cut; a pipe lying in the cut plane is not cut (s5) | s5 cut column |
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
| Wall | cross-section rect: width = chord of the cut line through the mitered quad (along h), height = wall z-extent; brush = the wall's material look ([`materials.md`](materials.md)) via `draw_section_type`; pen = Colour. A crossing inside an opening span draws only the wall above the head (and below the sill for windows) | today's rect + openings, clipped |
| Pipe | plan riser symbol (circle + S curve) at the crossing, plan size, in the pipe colour; *Section colour* fills inside the circle; an angled pipe adds a line for the part beyond the cut | today's line, or the end-on "C" (below) |
| Sprinkler / node | never cut | today's glyph |
| Floor slab | chord x thickness rect, the slab's material look (with floor voids: one rect per material span, below) | today's mask + fill |
| Roof | **not cut-rendered in v1** (follow-up: mesh / plane intersection); a crossing roof shows as today's projected rect | today's rect, fixed Z |
| Gridline (872, D7a) | crossing of the infinite gridline with the cut line; drawn vertical at that h when it lies in `[h_A, h_B]`; z-extent from this section's `gridline_z_overrides` record (gridline-uid-keyed, s6; none = the auto extent); its two bubbles are the plan gridline's System block (`GridlineBubble` children of `ElevGridlineItem`, SB4c; per-end visibility, trim and hit shape: [`system-blocks.md`](system-blocks.md) 8c, [`grid-system.md`](grid-system.md) 8.2); parallel or outside -> hidden. Replaces `_is_cardinal_for_elevation` | -- |
| Level datum | horizontal across `[h_A, h_B]` by default (replaces the cardinal-gated `_datum_extent`), or across this section's `datum_ends` record for the level (level-name-keyed, s6); the head at the left end is the `Level` System block (`LevelDatumHead`, SB4c), and `SectionScene.drawForeground` draws the line from `ElevDatumItem.line_start_h()` (the head outline) to `ElevDatumItem.line_end_h()` (the right grip, so a dragged right end draws where it was dragged); `ElevDatumItem.shape()` is the head outline, so a press on the head selects the datum. Block contract: [`system-blocks.md`](system-blocks.md) 8c | -- |

**Draw order of the annotations (SB4d).** The gridline and level-datum items draw in the annotation
band's grid sub-band and a hosted-block copy (`_HostedBlockCopy`) in its tag sub-band, so they sit
above every projected model item at any depth; the values and the rule are owned by
[`view-relationships.md`](view-relationships.md) 7.3 (Rule A). Ratified record:
[`2026-11-03-sb4d-view-marker-heads-design.md`](../superpowers/specs/2026-11-03-sb4d-view-marker-heads-design.md).

Shipped refinements of the table (plan reconciliations 2026-10-20, ratified at plan approval):

- **Pipe symbols (section piping, 2026-11-05; supersedes R2).** The plan SVGs are hard-coded white,
  so `section_pipe_symbols.py` redraws them as paths in the pipe colour. *Section colour* unset or
  `""` is No Fill; a set colour fills inside the circle, S on top. On paper with the row's As Authored
  OFF the circle gets no fill, since a body in the row colour would hide the S
  (per-row since 2026-11-11, `2026-11-11-paper-as-authored-design.md` D6; was B&W / Custom).
- **Along the cut.** A pipe whose centreline lies in the cut plane is a normal full-length line,
  zone behind, not a symbol; a vertical pipe standing on the cut line included.
- **End-on "C".** A pipe with zero projected length that does not cross the cut draws
  `elbow_down.svg`'s C, sections and elevations alike, at the plan fitting size
  (`Fitting.plan_symbol_mm`). Its gap faces the first in-view pipe joined at its near node, else
  down. Coincident symbols draw the nearest only, cut first.
- **Trim.** A line stops at a symbol it runs behind, at the drawn circle (`radius_of`); a line
  passing in front draws over; a line ending at a symbol's centre always trims. A symbol selects
  its source pipe.
- **Pipe labels.** Lines (the part beyond an angled cut included) and vertical pipes carry the
  plan's PipeLabel block, centred on the visible part, kept readable, following the pipe's Show
  Label. Symbols carry none. Block contract: [`system-blocks.md`](system-blocks.md) 8a.
- **Cut wall draws the cross-section only.** The receding face of an obliquely crossed wall is not
  drawn in v1 (follow-up).
- **Concave slab chord.** The chord is `[min h, max h]` over every crossing of the cut segment with
  the slab boundary, so a concave slab's gap is filled in v1 (follow-up).
- **Slab with floor voids (floor-opening, 2026-10-31; voids: `wall-room-floor-system.md` §11.11).**
  A cut slab that owns voids draws **one cut rect per material span** instead of one chord:
  `SectionScene._slab_cut_spans` maps each `floor_cut.intervals_inside(slab.cut_region(), cut_a,
  cut_b)` interval of the marker's cut segment to h, so the section shows a break where the cut
  crosses a void (and, for such a slab, a concave gap is no longer filled). A void-less slab keeps
  the single chord above. A slab whose cut region is empty (a void swallows it) is classed
  `ZONE_HIDDEN` and draws nothing. A behind (elevation) slab with voids takes its h extent from the
  cut region's outer rings, so an edge-crossing void narrows it and an interior void leaves it
  unchanged. **Known gap (filed):** when the cut line crosses the slab only inside voids, no span
  results and the slab falls through to the behind draw while its zone stays CUT (`todo_open.md`
  "Section: a slab whose cut line meets only voids draws as elevation but stays zone CUT").

### 5.0 Paper output (AC1-AC5, 2026-10-22)

- **No scene background.** `SectionScene` paints no background brush (NoBrush, as `Model_Space`
  does); the app QSS paints the canvas behind the view, so a section viewport plots paper white.
- **Proxies plot through their paper row.** Projected items carry `_paper_cat` (Wall / Floor /
  Roof / Pipe / Sprinkler, opening items the opening's `display_category`) and take that category's
  whole paper row; elevation gridlines and level datums use the "Grid Line" / "Level Datum" rows
  for the **line only** (no fill; their bubbles / heads are annotation blocks printed through
  `_apply_block`, SB4c). The Level Datum Display Manager row rule is homed in `grid-system.md`
  10.1. Mechanism owned by `paper-space.md` §9.9.1 (Rule A); not restated here.
- **Selection plumbing for the heads (SB4c).** `SectionScene._manip_exclude` excludes any
  `BoundLabelItem` from the manipulator (only the top-level gridline / datum is framed) and
  `_halo_resolve` walks the full parent chain to the owning `ElevGridlineItem` / `ElevDatumItem`;
  the label-side contract is `system-blocks.md` 8c (Rule A).
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
(cardinals only), `gridline_z_overrides` (moved here from the scene so they persist) and
`datum_ends` (elevation-parity R12 / D7). The two **end records** are section-scene mm, per
section, and survive rebuilds, model edits and tab switches:

| Record | Key | Value | Absent = |
|---|---|---|---|
| `gridline_z_overrides` | the plan gridline's `uid` (a label key only in a pre-elevation-parity file; migrated on load, s8) | `{"v_top", "v_bot"}` | the auto extent (level range plus `ELEV_GRIDLINE_END_PAD_MM`) |
| `datum_ends` | the level **name** | `{"left", "right"}`: the datum line's head end (`p1`) and far end (`p2`) | the crop box `[h_min, h_max]` |

Both are deep-copied by `copy_gridline_overrides` / `copy_datum_ends` (a malformed record raises, and
the loader skips the marker, s13). `SectionMarker.to_dict` / `from_dict` carry both.
`cut_a`, `cut_b`, `depth` are **plan-scene units** (mm at ppm 1; the `DetailMarker.crop_rect`
convention) -- G1 review ruling 2026-10-20, recorded as plan reconciliation 2026-10-20 (ratified at
plan approval): s4.1's "world mm" is the derived basis, converted at `SectionScene` with
`_scene_to_world` (Y sign flip); `CROP_MARGIN`, `MIN_CUT_LEN`, `FALLBACK_HALF` likewise.

- Shown on every plan level (a section cuts all levels).
- `PAPER_EXCLUDED = True` **only when `cardinal` is set** (view-relationships s6.4: cardinal markers
  never plot; placed sections plot by the default path). `_exclude_from_bulk_select = True`.
- Visual -- two glyphs (smoke ruling 2026-10-21, served-tuner mockup; supersedes the D6 "carried
  over" wording that Phase 3 approved from text alone). Since SB4d the **heads are System
  blocks** ([`system-blocks.md`](system-blocks.md) 8d: `ViewMarkerHead` children, annotative,
  upright, the Elevation / Section annotation categories); the bespoke arrow geometry is built
  from the head outline's enclosing circle `R_k` (`_rk()`), so a restyled head carries its arrow:
  - **Cardinal**: one `head` (the Elevation block, bound to the Direction letter) at
    `_cardinal_centre()` and a filled wedge (tangents at +/-40 deg, centre-to-tip
    `R_k / sin 40 deg`) whose tip sits 25 mm outside its own crop-box edge on the edge's midline
    (`_WEDGE_DIST`, `_CARDINAL_GAP`). No cut line is drawn for a cardinal. `_R_CARDINAL`
    (3 x `BUBBLE_RADIUS_MM`) is only the seed proportion and the no-block fallback.
  - **Placed section**: the cut line (solid cosmetic) with a head at each end (`head_a` /
    `head_b`, origins on the endpoints, the Section block bound to Mark over Sheet; the line is
    trimmed at each head's outline) and a full filled triangle whose base lies on the cut line
    through the centre, sides tangent to the head's enclosing circle, equal stick-out all round
    (half-base = height = `R_k * sqrt(2)`, `_TRI`), apex on the look side. The label is now
    **upright** (breaking: it used to rotate along the cut). `_R_SECTION` is the seed
    proportion / fallback.
  - Both: the crop box (SharedCropBox's dashed look) and grips only while selected. The marker
    draws in the annotation band's marker sub-band ([`view-relationships.md`](view-relationships.md)
    7.3); the Display Manager rows tint the lines only (`grid-system.md` 10.1).
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
- Property panel (`get_properties`, DetailMarker pattern): Name, Mark (placed sections only; a
  Marks category, `element-parameters.md`; blank refused), Depth (mm, `ScaleManager`
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
  `"SectionMarker"` instead of `"ViewMarkerArrow"`; row label "Section Marker", key kept
  (SB4d: a cardinal maps to the "Elevation Marker" row, a placed section to "Section Marker").
- `rebuild_all` call sites bind to `scene._section_manager`.
- `main.py`: the three `_create_elevation_markers()` calls become `seed_cardinals()` after load;
  `_views.clear()` / `_views.pop` become `close_all()` / `close_section()`; `_live_scenes` reads
  `open_scenes`; the ribbon gains a "Section" `add_small_button` in the Build group beside Detail
  with a `_mode_buttons["section"]` entry. No section icon asset exists: the button reuses
  `detail_icon.svg` (plan reconciliation 2026-10-20; dedicated asset is a follow-up).
- `docs/gen_ref_pages.py`, `SPEC-INDEX.md` and view-relationships s4 / s6 are updated at Account.

## 8. Persistence and undo

**Project file (D4).** `scene_io` payload gains `"sections": [marker.to_dict() ...]` with keys
`name, cut_a, cut_b, look_sign, depth, cardinal, auto_extent, gridline_z_overrides, datum_ends` (+ `mark` for a
placed section, always written, SB4d; a record without it adopts the name token on load,
`element-parameters.md` Marks). Load:
`payload.get("sections")` -> `from_list` when present, then `seed_cardinals()` always (an old file
or one missing a cardinal gets it re-seeded). No `SAVE_VERSION` bump.

**Label migration (R12 / D7).** `SectionManager.from_list` runs `_migrate_gridline_overrides` per
marker after `scene_io` has loaded the gridlines: a key that is a loaded gridline's `uid` stays; a
label key maps to the `uid` of the ONE loaded gridline carrying that label (a `uid` key for the same
gridline wins); an **ambiguous** (duplicated) or **unknown** label is dropped with a `log.info` line.
The pass is idempotent (a re-saved record is all `uid` keys). Undo snapshots are taken after the
migration, so `restore_from_list` copies records verbatim and never re-migrates. `datum_ends` has
no migration (absent in an old file = auto extent).

**End records follow their level / gridline.** `LevelManager.rename_level` calls
`SectionManager.rename_level_ends` (every marker's `datum_ends` re-keyed) and
`LevelManager.remove_levels` calls `drop_level_ends` (deleted levels' entries dropped); both run for
the user's action only, inside that action's one undo step, never on load or undo restore.

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
- [ ] Cut items carry their material's look; behind items carry today's rendering, laterally clipped.
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
| `test_section_rendering.py` | cut wall brush = material look; behind wall brush = Fill; cut through an opening leaves the head; pipe cut-circle diameter |
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
- Pipe exactly along the cut line: not cut, a normal line (s5).
- Coincident / sub-100 mm A, B: rejected at placement; `SectionScene` asserts `L > 0`.
- A cardinal with `auto_extent` and an empty project: the +/-10 000 mm fallback box.
- Hand-edited file missing a cardinal: `seed_cardinals()` restores it.

## 14. Out of Scope (v1) -- filed as follow-ups at Account

Roof cut-render (mesh / plane); cut vs projection line-weight DM columns (D2b); detail-marker undo;
jogged / stepped sections; break lines; in-view dimensions; geometry editing of model items in the section view
(what a section edits is its write-back copies and ends, s3.2 / s17); vertical crop handles. SB4c / SB4d / HF5 lines are re-worded to the new module names.

## 15. Design-decision ledger

| Id | Decision | Gate |
|---|---|---|
| Q0 | AHJ sheet sections are the workflow | Phase 2 grill 2026-10-20 |
| D1 / D1b | cardinals become permanent sections with four independent markers; elevation classes retire | Phase 2 |
| D2 / D2b | cut vs behind through existing DM columns only; behind keeps today's rendering | Phase 2, reconciled S2 |
| D3 | depth = the section's own crop box in plan, seeded to the building extent | Phase 2 |
| D4 | new `sections` key, no `SAVE_VERSION` bump | Phase 2 |
| D5 / D5b | Section button beside Detail; cardinals permanent | Phase 2 |
| D6 | bespoke bubble / datum / hatch visuals carried over; marker glyphs superseded by D6r. **Note 2026-11-03: the bubble / datum visuals are superseded by SB4c** (elevation bubble + datum head are System blocks, `system-blocks.md` 8c); the hatch visuals stand | Phase 2 |
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
| R2 | **Superseded 2026-11-05 by section piping (s5).** Was: pipe cut circle in *Section colour* when set, else the pipe's own line colour | plan reconciliation 2026-10-20, ratified at plan approval |
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
- **Esc routing:** `MainWindow._active_scene()` now answers the current tab's `SectionScene` for a
  Section / Elevation tab (s17.1), so `MainWindow._on_escape` reaches `_section_escape`: it ends an armed
  placement (`cancel_place_block`), else ends a running modify tool, then clears the section's
  selection -- never the plan scene. `SectionView.keyPressEvent` handles Esc / Space / arrows when it
  has focus.
- **Footer and panel:** the `modeChanged` signal is the host mixin's (`ModifyHostMixin`, scene-tools
  I1); `SectionScene` emits `"place_block"` on arm and `"select"` on cancel, and the modify tools emit
  their own modes through it. `MainWindow._on_section_scene_built` connects it to `_update_mode_label`
  (the PLACE BLOCK badge; text from `_MODE_INSTRUCTIONS["place_block"]`), `_on_mode_changed_template`
  (the plan's property-panel clear) and `_sync_mode_buttons` (the Editor buttons lit for the running
  tool).
- **Snap:** the section's own `SnapEngine` (s17.5): `snap_point` runs `SnapEngine.find` over the
  section scene; the per-axis `snap_section_point` is retired. A drop, a placement click and the
  ghost all go through `snap_point`, so a point near a gridline vertical and a level datum lands on
  their crossing the way plan snap lands on a gridline intersection.
- **Commit:** `Model_Space.place_block_instance(..., host=...)` + `push_undo_state()`, then rebuild and
  select the new copy.

### 16.4 Selecting, dragging, deleting

- A copy picks through `_ROLE_SOURCE`; the section's selection drives the Properties panel through
  `MainWindow._on_section_selection_changed` (the panel shows the model sources of the selection, each
  once, via `SectionScene._sources_of`; rows: block-system). Panel edits on model items stay allowed (R7).
- **Write-back copies (R1, AC3).** `_HostedBlockCopy` is section-editable (`SECTION_EDITABLE`, s17.2).
  Beyond the in-plane drag below it implements `manip_rotate` (about the view normal),
  `manip_reflect` (across an in-plane axis) and `manip_scale_about` (about an in-plane base point);
  each transforms the copy, then `SectionScene._write_hosted_pose` writes the **model** block:
  the copy's h / v move `along_mm` / `elevation_mm`, and its rotation / mirror / scale become the
  model's `_pose_rot` / `_pose_mirrored` / `_pose_scale` -- rotation negated and mirror toggled when
  this section sees the host from its far side (`facing_of(basis, gl) != host["facing"]`), scale
  times pixels-per-mm (copies are built at `scale / ppm`). Host gridline, offset and facing are
  kept. Copy / Duplicate / Array / Paste create model blocks through
  `SectionScene._place_hosted_record` (s17.2: same host gridline, the shifted point sets along /
  elevation), so the new block shows in every parallel view.
- **In-plane drag:** `_HostedBlockCopy.translate` -> `SectionScene._move_hosted_source` maps (dh, dv)
  to `along_mm` (by `h_sign`) and `elevation_mm`; host and offset are untouched, so a locked host
  gridline still lets the block move. One undo step per gesture (the manipulator release hook flushes it;
  a `QTimer` is the fallback for a bare translate).
- **Delete (R2):** `MainWindow`'s Delete handler routes a Section / Elevation tab to
  `SectionScene._delete_elev_selected` (s17.1 -- never the plan's 3D-pick / constraint paths). It
  removes **any** selected source -- model proxies as well as write-back copies -- in ONE undo step.
  Hosted and Note copies go to `Model_Space.delete_items` by explicit list (a plan-hidden block cannot be
  `setSelected`); the plan selection is saved and restored around it.

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

## 17. Editing parity with plan (elevation-parity, 2026-11)

Ratified source: `docs/superpowers/specs/2026-11-09-elevation-parity-design.md` (rulings R1-R16, D1-D8).
A section or elevation tab works the way plan does, scoped to what a section may edit (s3.2): the modify
tools and clipboard, snap, Hide, the context menu, the selection look, the footer readout, Properties,
section-owned Notes and persisted datum / gridline ends. Rule A: the host contract is owned by
[`scene-tools.md`](scene-tools.md) I1, the engine seams by [`snapping-engine.md`](snapping-engine.md),
the Note rule by [`text-annotation-system.md`](text-annotation-system.md); this section owns how
`SectionScene` mounts them.

### 17.1 Routing (`main.py`)

- `MainWindow._active_scene()` answers the current tab's `SectionScene` for a Section / Elevation tab
  (`_active_section_scene()`); `_active_view()` answers the `SectionView` itself, so the one window
  Ctrl+A shortcut calls `SectionView._select_all_items` (the view-level Ctrl+A shortcut is removed:
  two live window shortcuts made the key ambiguous, AC15). F3 reaches `SectionScene.toggle_snap`
  through the same routing. Shift+letter and Ctrl+C / X / V / D therefore start on the section scene,
  never the hidden plan (AC1); the 3D-tab and Paper refusals are owned by scene-tools D2.
- `_GROUP_LIVE_KINDS`: `"section"` joins `edit` and `annotate` (Note is that group's only gated
  button); it is **not** in `inspect` or `constrain` -- a section has no constraints (U4).
- Ribbon / shortcut draw modes on a section run `_SECTION_RIBBON_MODES` (`select`, `note`) only; any other
  mode (plan draw tools, Align) is refused with `_NOT_IN_VIEW_TIP` through `MainWindow._set_active_mode`
  and its button is left un-lit. The ALIGN pill / F11 are held off on a section (`_toggle_active_align`:
  a section has the SnapEngine only, R15).
- A user selection on a section tab makes **Editor** current, as in plan (`_on_selection_jump`, U3).
- Esc, Delete and block placement on a section tab are the folded `_section_escape` /
  `_delete_elev_selected` / `begin_place_block` branches (s16.3, s16.4). Leaving the tab ends an armed
  placement and a running modify tool (`MainWindow._on_tab_changed`).
- Right-click Hide on an empty canvas never maps `None` (s17.6, s17.8).

### 17.2 Modify host: `SectionScene` mounts the plan's controller

`SectionScene(HaloSelectionMixin, ModifyHostMixin, QGraphicsScene)` sets `scene_role = "section"` (the
constraint controller exists but stays disabled for any role but plan / block editor) and calls
`_init_modify_host()`, which composes one `ModifyToolsController` (`_modify_ctl`) -- the plan's class,
not a copy. The mixin supplies the contract (modes, dispatch rows, `_HOST_TOOLS`, signals, typed
input); `SectionScene` overrides only:

| Hook | Section behaviour |
|---|---|
| `modify_selection()` | The **editable subset** of the selection: items with `SECTION_EDITABLE` (`is_section_editable`: `_HostedBlockCopy`, `_SectionNoteCopy`). Gridlines, datums and every projected model proxy are read-only here (R1). |
| `modify_empty_hint()` | `SECTION_EDIT_SKIPPED` ("N items skipped (edit in plan)") when something is selected but nothing is editable; the plain "Select items first" otherwise. A select-first tool then refuses with that text and no mode change (R3). |
| `_capture_modify_selection(mode)` | After the mixin's capture, a select-first tool entered over a mixed selection says `SECTION_EDIT_SKIPPED` for the read-only items it leaves alone (they stay selected and unchanged). |
| `push_undo_state()` | One step on the shared plan stack (s17.3). |
| `_clipboard_item_dicts` / `_paste_accepts` / `paste_items` / `_add_from_dict` / `_bulk_delete` | Section clipboard (below). |
| `paste_refusal(items)` | Why nothing on the clipboard can land here (footer text; below). |
| `set_mode` | The mixin's, plus the Note tool's rules (a tool switch commits an inline edit; leaving Note drops a half-made note). `_HOST_EXTRA_MODES = {"note"}`: the generic `set_mode` enters it with the same gates. |
| `_hud_scale_manager()` | The typed-input HUD (Tab; `PlacementInputCoordinator`, modify schemas only -- a section has no draw tools) formats and converts with the project's live `ScaleManager` wrapped by `_SectionHudScale`: never calibrated (`is_calibrated = False`), section-scene units are mm. |
| `_halo_mode_ok()` | HALO hover runs only in Select (plan parity). |

`_HOST_TOOLS` is the mixin default: copy, cut, paste, duplicate, move, rotate, array, flip, mirror,
scale. Offset and Fillet (plan 2D-geometry lists) are not hosted here; `ModifyToolsController.start`
refuses them with `TOOL_NOT_HOSTED` ("Not available in this view") and `can_start` returns False.

**Write-back copies (R1).** A section scene is rebuilt from the model (`rebuild()` clears and
re-projects), so whatever it edits is a copy of a model record, never a section-only item:
`_HostedBlockCopy` writes the model block (s16.4); `_SectionNoteCopy` (s17.7) shares its model Note's
`note` dict and forwards pose / attribute writes to the model Note.

**Rebuild held while a tool runs.** The debounced rebuild (`_rebuild_when_idle`) is held while a modify
mode is live (`_rebuild_held`), because `clear()` would delete the copies the tool holds; it runs when
`modeChanged` reports the tool ended (`_run_held_rebuild`). A direct `rebuild()` ends the running tool
first.

**Clipboard (R4, R5).** The payload carries `scene_role = "section"`.
- Copy / Cut serialise `_HostedBlockCopy.to_dict()` (pose in THIS section's frame, plus `section_host`:
  the host gridline uid and offset; no plan `host` key, so a plan paste can never place it) and a Note
  copy's model record.
- `_paste_accepts` takes only a hosted-block record (`section_host`) or a section's Note
  (`note_allowed`); plan records are refused.
- A hosted record is created by `_place_hosted_record` on its own host gridline at the pasted point
  (the point sets along / elevation; the record's offset is kept), facing this view -- refused when
  the view does not show that gridline (`shows_host_gridline`, the s16.3 placement rule applied to one
  gridline).
- `paste_refusal` returns `NOTE_INTO_SECTION_REFUSED` (only plan / detail Notes), else
  `SECTION_PASTE_PLAN_ITEMS` (nothing the section accepts), else `SECTION_PASTE_NO_HOST` (every
  accepted record's gridline is not shown). A partly fitting clipboard pastes what fits and the commit
  reports the rest skipped. The plan side refuses a clipboard of hosted blocks only with
  `HOSTED_PASTE_IN_PLAN` (`Model_Space.paste_refusal`).
- Cut deletes the model records behind the editable copies through `Model_Space._bulk_delete`, one undo
  step pushed by the caller.

### 17.3 Shared undo stack (R13, AC11)

A section owns no undo stack. Every section edit pushes onto the plan `Model_Space` stack, and Ctrl+Z /
Ctrl+Y / the header buttons on a section tab (`MainWindow._dispatch_undo` through `_active_scene()`)
step that same stack through `SectionScene.undo` / `redo` / `can_undo` / `can_redo`. A tool commit pushes
through `push_undo_state`. A write that is not a tool commit (a hosted drag, a Note copy write, a datum /
gridline end edit) marks ONE pending step with `_mark_section_edit`; the manipulator release hook
(`_commit_elev_grip`), a tool commit's own push (which folds the pending step in) or a zero-delay timer
(`_flush_hosted_push`, the fallback for a bare translate) records it once, skipping when a push since
the mark already recorded the edit. Undo is refused while the section manipulator drags, flushes a
pending step first, and ends a running modify tool (`_ready_for_shared_undo`).

### 17.4 Selection look, readout, Properties (R6, R7, R14)

- Selected projected proxies draw no Qt dashed selection box: `_ColourSrcMixin.paint` strips
  `State_Selected`, so the `SelectionManipulator` frame is the one boundary (AC12). The elevation
  gridline and level datum likewise strip it and draw their own heavier, lighter-tinted line while
  selected (`shows_selection`), never on a sheet. Contract owned by `selection-mode.md` s14.
- The HALO "<Type> - i of N" readout is `SectionScene._emit_halo_readout` on `instructionChanged`
  (the mixin's signal), connected to `footer.set_instruction` in `MainWindow._on_section_scene_built`;
  *Type* is the model source (`section_source_of`), so a pipe proxy reads "Pipe". `SectionScene.cursorMoved`
  is **not** retired: `TextEditController` emits it (the `H: ... Z: ...` readout) during a Note
  drag-select, and the section footer's live coordinate comes from `SectionView.cursorMoved`.
- Properties: `selectionChanged` -> `MainWindow._on_section_selection_changed` ->
  `update_property_manager`, which maps the selection to de-duplicated model sources
  (`SectionScene._sources_of`; a source without `get_properties`, e.g. a datum's `Level`, yields no
  panel). Panel edits on model items stay allowed (R7).
- **The selection survives a rebuild (U1):** `rebuild()` records the model uids of the selected editable
  copies (`_editable_selection_uids`) and reselects their new copies (`_reselect_editable`, one
  `selectionChanged`). Read-only proxies are not restored.

### 17.5 Snap (R15)

`SectionScene` owns one `SnapEngine` (the `_snap_engine` property copies the plan engine's per-type
toggles, `SNAP_TYPE_TOGGLES`, in on every read, so the footer osnap bar and Settings govern both). F3 /
the footer SNAP pill toggle **this scene only** (`toggle_snap`, `snapToggled`); `get_effective_position`
runs the engine while a grip drag or a tool mode is live (never in plain Select nor a
`raw_cursor_mode`); `snap_point` runs it on demand (placement, drop). There is no ALIGN and no grid
fallback in a section. `SectionView.drawForeground` paints `scene._snap_result` with the plan's
`paint_snap_indicator`. Targets: the proxies (rect proxies opt in with `SNAP_AS_RECT`), hosted-block
copies (`_HostedBlockCopy` is in `ANNOT_Z_SNAPPABLE_CLASSES`), and the elevation gridlines and level
datums, which reach the engine through the `snap_line_items()` line-target hook (`_snap_lines`, refilled
each build), not the snappable-class list. A datum snaps along its drawn segment (`snap_segment()`, head
edge to far end). The engine seams are owned by `snapping-engine.md`.

### 17.6 Hide (R8, R9)

Hide is one global flag, `_display_overrides["visible"]` on the model source (display owner:
`architecture/display-system.md`). `Model_Space._hide_items` / `_show_items` / `_show_all_hidden` /
`_hide_all_of_type` emit `Model_Space.hiddenChanged` (they still emit no `sceneModified`);
`SectionManager.reapply_hidden` is connected to it and re-runs `_apply_hidden_pass` on every live
section scene (open tabs and tab-less sheet scenes), with **no rebuild**. `rebuild()` also runs the pass
last, so hidden sources stay hidden through rebuilds and save / reopen (the flag rides the existing
`displayable_item` save).

`_apply_hidden_pass` hides each item whose source is hidden (`_source_hidden`: the source, an opening's
wall, or a sprinkler node's sprinkler) and re-shows only what the pass itself hid (`_hidden_by_pass`);
a hidden item is deselected first. The source of an item is, in order: its `_ROLE_SOURCE`; its
`_ROLE_HIDE_SOURCE` (a decoration piece -- opening frame / sill / mid line, slab mask -- that follows its
source's Hide without becoming a pick, menu or Properties target); for an `ElevGridlineItem`, its plan
`_gridline`. A pipe's label carries the pipe as `_ROLE_SOURCE`, so every piece of a pipe goes together.
A datum stands for its Level, which no Hide takes.

Section Hide calls the plan's `_hide_items` on the de-duplicated sources (`_hide_section_items`;
items without a source are skipped and `None` is never touched); Hide All (`<type>`) is global
(`_hide_all_of_source_type`); Show All Hidden is `_show_all_elev_hidden` (R9: plus the Model Browser's
per-item Show; no reveal mode).

### 17.7 Section Notes (R11)

A section Note is the plan's Note (`NoteController`, `TextEditController`, composed unchanged by
`SectionScene`) owned by the section's view key: `SectionScene.active_view_key` =
`"section:" + marker.view_name`, read live so a rename re-keys it. The model Note lives in the plan
`_block_instances` with `note["view"]` = that key, its pose in the section's 2D frame, and is hidden on
the plan canvas (`setVisible(False)`).
- `rebuild()` projects each as a `_SectionNoteCopy` (`_project_section_notes`, `notes_of`);
  `SECTION_EDITABLE`, so every modify tool, Copy / Cut / Paste and Delete act on it.
- `note_allowed(rec)` accepts a section's note record only (a `section:` view); `note_tool_allowed()` is
  always True, so the Note button is live on every section and elevation tab. Plan and detail Notes
  refuse a paste into a section (`NOTE_INTO_SECTION_REFUSED`); a section's Note refuses a paste into
  plan (`NOTE_SECTION_PASTE_REFUSED`). `NOTE_OFF_HINT` names sections among the views that hold Notes.
- `SectionManager.rename_section` re-keys and `delete_section` removes the section's Notes
  (`note_controller.rekey_notes` / `remove_notes`) inside the caller's undo step; `restore_from_list`
  passes `notes=False` (an undo restore has already restored the blocks as they were).
- Sheets render a section through `get_or_build_scene`, so its Notes plot with no new path.

### 17.8 Context menu (R10)

`SectionScene.contextMenuEvent` builds plan's shared `build_entity_context_menu`
(`_build_section_context_menu`) with plan's callbacks: Edit Block (a hosted block or Note copy;
`blockEditRequested`), Copy, Cut (the section's controller), Hide, Hide All (`<type>`) -- the type is the
proxy's model source type (`hide_type_name`), offered only for a hideable source -- Show All Hidden,
Delete, Deselect All, Properties (the target's model source), **Fit All** (`SectionView.fit_to_screen`)
and **Refresh** (`rebuild`). A right-click on an unselected target selects it alone; a right-click on
empty canvas acts on the selection (never on `None`); a right-click inside a live Note editor shows the
native text menu. Isolate exists in neither plan nor section (filed).

### 17.9 Datum and gridline ends (R12, AC10)

`_commit_elev_grip` (the manipulator commit hook) calls each selected `ElevGridlineItem` /
`ElevDatumItem`'s `_commit_grip_override`, which writes this marker's end record (s6) only when the
item moved since its build (`_built_line`) and the record changed; a changed record joins the gesture's
ONE undo step on the plan stack (s17.3). `rebuild()` / `_project_gridlines` / `_project_level_datums`
apply the records; no record = the auto extent. The right grip draws where it was dragged
(`line_end_h()`, s5). Label migration and level rename / delete cascades: s8. The 3D half (model
extents, the 2D / 3D tag) stays on the slice 2 line in `todo_open.md`.
