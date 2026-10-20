# Section View Subsystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cardinal-only elevation system with one section-view subsystem: a vertical cut at any plan angle, defined by a two-click marker whose own crop box sets what the view shows; the four cardinal elevations become permanent cardinal sections that render exactly as today.

**Architecture:**
- `elevation_scene.py` / `elevation_manager.py` / `view_marker.py` are `git mv`'d to `section_scene.py` / `section_manager.py` / `section_marker.py` and generalized in place (spec S0). One oblique basis (`SectionBasis`, pure math, world mm) replaces `_world_to_elev` and the five per-type cardinal depth if-chains.
- `SectionMarker` (one `QGraphicsItem` per section, plan scene) replaces `ViewMarkerArrow` + `SharedCropBox` + `ViewMarkerManager`. It stores `cut_a`, `cut_b`, `depth_mm` in **plan-scene coordinates** (the `DetailMarker.crop_rect` convention); the scene converts to world through `_scene_to_world` when it builds the basis.
- Classification by plan footprint against the marker's crop box: cut / behind / hidden. Behind = today's rendering, laterally clipped. Cut adds the Display Manager *Section colour* + *Section pattern*.
- `SectionManager` owns markers and open views; cardinals keep the `"elevation"` identity everywhere (spec S4), placed sections are `"section"`.
- 600 (sheet plot colours) through the HF1 per-paint colour-source mechanism with a new background token `token:bg`.

**Tech Stack:** Python 3, PyQt6, pytest (no pytest-qt; `qapp` fixture + `QTest.qWaitForWindowExposed`), PyMuPDF (`fitz`) for PDF pixel probes.

**Governing spec:** `docs/specs/section-view-subsystem.md` (Revision 2, committed 682c1edd on `feature/section-views`). Related: `docs/specs/view-relationships.md` s4 / s6, `docs/specs/paper-space.md` s6.2, the display-manager spec.

**Branch / checkout:** worktree `D:\Custom Code\FirePro3D\.worktrees\feature-section-views`, branch `feature/section-views`, base `aeab43ff` (the VC7 base SHA for every pre-existing claim).

## Conventions for every task

- Run tests with the venv from the worktree root: `"D:/Custom Code/FirePro3D/venv/Scripts/python.exe" -m pytest <paths> -q`. Globs need the Bash tool (PowerShell passes `tests/test_x_*.py` literally). Do not set `QT_QPA_PLATFORM=offscreen` for MainWindow tests (PyVista aborts under offscreen).
- Every guard test is shown RED with the rule reverted before the task is called done (VC3): run the new test before the implementation step, or mutate the one line the task names under "RED proof" and restore it.
- Settings isolation: `tests/conftest.py` redirects `QSettings("GV", "FirePro3D")`; every probe runs under pytest, never bare.
- Edit safety (B7): every file in this plan holds non-ASCII (box-drawing section rules, `--`, `->` arrows, degree signs). Make changes with the Edit tool and exact `old_string`s; never retype a block through a heredoc or `sed`. Read back each edited line.
- Commit per the orchestrator's Commit rule: `git status` + `git log --oneline -5` first, stage by explicit path, never `git add -A`.
- Keep-green set per task (VC5) is listed at the end of each task; G1 and G4 also re-run the **cardinal-equivalence net**: `tests/test_elev_grip_retirement.py tests/test_elev_manip_handles_parity.py tests/test_elev_manipulator_wiring.py tests/test_elev_proxy_frame_parity.py tests/test_elev_selection_interaction.py tests/test_floor_elevation_projection.py tests/test_gridline_core.py tests/test_gridline_integration.py tests/test_halo_aperture_setting.py tests/test_halo_foldins.py tests/test_halo_pixel_ranking.py tests/test_hf1_seam_fixes.py tests/test_hf1_universal_picker_c.py tests/test_opening_render.py tests/test_paper_viewport_crop.py tests/test_rubber_band_commit.py tests/test_viewport_properties.py tests/test_paper_marker_exclusion.py tests/test_manip_griphandle_viewmarker_parity.py tests/test_detail_marker_crop.py`.
- Known pre-existing failure (VC7, proved at 1b against `aeab43ff`): `tests/test_elev_selection_interaction.py::test_empty_click_deselects` fails when run together with the other `test_elev_*.py` files and passes alone (order-dependent). Filed at Phase 6; never patched here.

## P4 probes (run at Phase 4, 2026-10-20, against 682c1edd) -- the facts the plan relies on

| Probe | Result | Plan consequence |
|---|---|---|
| `colour_tokens` surface-relative pair | Only a *foreground* token exists: `TOKEN_AUTO = "token:auto"` -> theme `ink` on canvas, `#000000` on paper (`colour_tokens.resolve_colour`, `constants.py:337`). No background token. | Task 7 adds `TOKEN_BG = "token:bg"` -> `theme.detect().canvas_bg` on canvas, `#ffffff` on paper (both paper modes); internal (not in `_LABELS`, so no picker row and no "unknown token" warning). |
| How grips push undo | `Model_Space._create_manipulator` passes `commit_hook=lambda mode: self.push_undo_state()`; `GripHandle.on_release` calls the hook only when `m._moved` (`manip_handle.py:350-352`). A click without a drag never reaches the hook. | The click-only `FlipGripHandle` (Task 8) toggles in `on_release` itself and calls `m._commit_hook("grip")` when the hook exists, so a flip is one undo step. |
| Pipe drawn OD | `Pipe.display_width_mm()` (`MAIN_WIDTH_MM` / `BRANCH_WIDTH_MM` by Line Type, `pipe.py:583`) times `_display_scale` (`pipe.py:164`). | Cut-pipe circle diameter = `pipe.display_width_mm() * getattr(pipe, "_display_scale", 1.0)`. |
| Marker level-visibility path | `LevelManager.apply_to_scene` walks named lists only (`sprinkler_system.nodes/pipes`, `_block_instances`, `_gridlines`, annotations, `_walls`, `_floor_slabs`, `design_areas`, `_roofs`, `_rooms`, underlays). An item in none of them is never hidden or re-shown. `ViewMarkerArrow` is in none today. | `SectionMarker` is added to the plan scene and to no level list, so it is shown on every plan level with no new code (spec s6 "shown on every plan level"). Guard: Task 8's `test_marker_visible_on_every_level`. |
| Display Manager row label vs key | `_CATEGORIES` rows have `key` only; the tree, swatches and settings all use `cat_def["key"]` (`display_manager.py:306, 869, 1320, ...`). No label field exists. | Task 11 adds an optional `"label"` to the row and one `category_label(key)` helper used by the tree builder; settings key stays `Elevation Marker` (D8). |
| `PAPER_EXCLUDED` read | `getattr(item, "PAPER_EXCLUDED", False)` at `paper_display.py:1196`. | An instance attribute works: `SectionMarker.__init__` sets `self.PAPER_EXCLUDED = cardinal is not None`. |
| `Model_Space._capture_network` / `_restore_network` | Snapshots named lists; no marker of any kind (`model_space.py:3062-3115`). `_section_manager` will be `None` on a headless `Model_Space`. | Task 10 adds a guarded `"sections"` entry. |
| Project browser drag | `mimeData` encodes `{"view_type": role_type, "view_name": name}` for `plan/elevation/detail/schematic` (`project_browser.py:76-96`); `SheetViewport` resolves through `ViewResolver.resolve(view_type, view_name)`. | Task 11 adds `"section"` to the role tuple; Task 13 adds the resolver branch. |

## Spec reconciliations this plan makes (stamp at Phase 6 Account)

1. **Marker coordinates.** Spec s6 says `cut_a`, `cut_b` are "world mm". The marker is a plan-scene item (grips, paint, placement clicks and `DetailMarker` all speak plan-scene coordinates), so it stores plan-scene coordinates and `SectionScene` converts with `_scene_to_world` (`sx / ppm, -sy / ppm`) when it builds the basis. Identical numbers at `ppm == 1` apart from the Y sign; the s4.1 cardinal table holds in world coordinates (verified below).
2. **Pipe cut colour.** Spec s5 says "Section colour"; the Pipe Display Manager row has `section: None`. The cut circle uses the Pipe *Section colour* when set, else the pipe's own line colour (today's `PIPE_COLORS` lookup).
3. **Cut wall draws the cross-section only.** Spec s5 table: cut -> cross-section rect; the receding face of an obliquely crossed wall is not drawn in v1 (follow-up at Account).
4. **Concave slab chord.** Spec s5 "chord x thickness": the chord is `[min h, max h]` over every crossing of the cut segment with the slab boundary (a concave slab's gap is filled in v1; follow-up).
5. **Ribbon icon.** No section icon asset exists; the Section button reuses `detail_icon.svg` (asset follow-up at Account).

## Cardinal basis check (world coordinates; scene y = -world y)

`D = unit(B - A)`, `N = look_sign * (-D.y, D.x)`, `h = p . D`, `d = (p - A) . N`, `sort_key = -d`. Marker seeds are written in plan-scene terms: `top` = smallest scene y = world `y_max`.

| Cardinal | Scene A | Scene B | World D | World N | h | today's h (`_world_to_elev`) | today's depth key |
|---|---|---|---|---|---|---|---|
| north | (right, top) | (left, top) | (-1, 0) | (0, -1) | -wx | -wx | +wy = -d + const |
| south | (left, bottom) | (right, bottom) | (1, 0) | (0, 1) | wx | wx | -wy = -d + const |
| east | (right, bottom) | (right, top) | (0, 1) | (-1, 0) | wy | wy | +wx = -d + const |
| west | (left, top) | (left, bottom) | (0, -1) | (1, 0) | -wy | -wy | -wx = -d + const |

A constant offset does not change an ascending sort, so `_assign_depth_z_values` produces today's order. In plan-scene coordinates the look normal is `N_s = look_sign * (D_s.y, -D_s.x)` (the y-flip negates the rotation sense); e.g. north: `D_s = (-1, 0)` -> `N_s = (0, 1)` = scene-down = world south.

## File structure

| File | Change | Responsibility |
|---|---|---|
| `firepro3d/section_marker.py` (git mv of `view_marker.py`) | rewrite | `SectionBasis` (pure projection / classification math), `building_bbox`, `cardinal_cut`, `SectionMarker` item (geometry, grips, paint, menu, properties, to/from dict) |
| `firepro3d/section_scene.py` (git mv of `elevation_scene.py`) | generalize | `SectionScene` (marker-driven rebuild, classification, cut rendering, 872 gridlines, 600 colour sources); item classes keep their `Elev*` names |
| `firepro3d/elevation_view.py` | rename class only | `SectionView` (`ElevationView` retired) |
| `firepro3d/section_manager.py` (git mv of `elevation_manager.py`) | rewrite | `SectionManager`: markers + open views + seed/place/open/close/delete/rename + to/from list + `sectionsChanged` |
| `firepro3d/manip_handle.py` | add | `FlipGripHandle` (click-only toggle) |
| `firepro3d/colour_tokens.py`, `firepro3d/constants.py` | add | `TOKEN_BG` |
| `firepro3d/model_space.py` | add | `"section"` mode (`_press_section` / `_move_section`), `_section_manager`, `"sections"` in undo snapshot |
| `firepro3d/scene_io.py` | add | `"sections"` payload key, load + seed |
| `firepro3d/paper_space.py` | generalize | `ViewResolver` `"section"` branch, `get_or_build_scene`, `available_views` Sections group, `SheetViewport` section == elevation |
| `firepro3d/display_manager.py`, `firepro3d/paper_display.py` | rename | `SectionMarker` class-name match, row label |
| `firepro3d/project_browser.py` | add | Sections group, `activateSectionView` / `deleteSectionView`, drag role |
| `main.py` | rewire | manager construction, routing, ribbon button, `_live_scenes`, tab close |
| `tests/conftest.py` | rename | `section_scene_for(direction="north")` |
| `docs/gen_ref_pages.py`, `docs/specs/SPEC-INDEX.md` | rename | module list / index rows |

## Coverage table (acceptance criterion / ratified ruling -> task -> guard)

| Criterion | Task | Guard |
|---|---|---|
| (a) placed section hosts in a sheet viewport after save/reload; marker plots; cardinals never plot | 12, 13, 8 | `test_section_persistence.py::test_round_trip_restores_placed_section`, `test_section_sheet_plot.py::test_section_viewport_resolves_after_reload_without_open_tab`, `test_section_marker.py::test_paper_excluded_only_on_cardinals` |
| (b) 600 dark-theme sheet export: edges black, voids / masks white | 7 | `test_section_sheet_plot.py::test_dark_theme_export_edges_black_voids_white` |
| (c) 560 public `open_scenes`; `_live_scenes` reads no private attribute | 11 | `test_section_manager.py::test_open_scenes_public_and_live_scenes_uses_it` |
| (d) cardinal sections == today's elevations (17 files / 161 tests re-bound, green) | 1, 3 | cardinal-equivalence net + `test_section_projection.py::test_cardinal_h_matches_pre_rename_table` |
| (e) place / grip / flip / delete undoable | 10 | `test_section_undo.py` (four tests) |
| (f) missing key seeds four; round-trip restores markers, boxes, overrides | 12 | `test_section_persistence.py::test_missing_key_seeds_four_cardinals`, `::test_round_trip_restores_placed_section`, `::test_one_missing_cardinal_reseeded` |
| 872 crossing gridline vertical at crossing; parallel hidden | 6 | `test_gridline_section.py` |
| two-click Section tool -> `Section 1`, `Section 2`; cardinals not deletable / renamable | 9, 8 | `test_section_placement.py`, `test_section_marker.py::test_cardinal_menu_disables_rename_delete` |
| cut items carry Section colour + pattern; behind = today's rendering, clipped | 4, 5 | `test_section_classification.py`, `test_section_rendering.py` |
| 767 closed as stale | Phase 6 step 3 | (backlog move; no code) |
| S1 cardinal auto-extent until touched | 4 | `test_section_classification.py::test_auto_extent_refits_then_stops_after_grip` |
| S3 FlipGripHandle; context menu Open/Rename/Flip/Delete | 8 | `test_section_marker.py::test_flip_grip_toggles_look_sign_one_undo_step`, `::test_cardinal_menu_disables_rename_delete` |
| S4 no `_STATE_VERSION` / `SAVE_VERSION` bump; `"elevation"` identity kept | 11, 12 | `test_section_persistence.py::test_save_version_unchanged`, `test_section_manager.py::test_cardinal_identity_is_elevation` |
| D8 "Section Marker" label, key kept | 11 | `test_section_manager.py::test_dm_row_label_section_marker_key_unchanged` |
| D5 Section button beside Detail | 11 | `test_section_manager.py::test_ribbon_section_button_enters_section_mode` |

---

# G1 -- rename, basis, marker core, classification (FP6 group: one implementer, one review)

### Task 1: Move the three modules and rename the classes (no behaviour change)

**Files:**
- Move: `firepro3d/elevation_scene.py` -> `firepro3d/section_scene.py`; `firepro3d/elevation_manager.py` -> `firepro3d/section_manager.py`; `firepro3d/view_marker.py` -> `firepro3d/section_marker.py`
- Modify: `firepro3d/elevation_view.py`, `main.py`, `firepro3d/paper_space.py`, `firepro3d/display_manager.py`, `firepro3d/paper_display.py`, `firepro3d/project_browser.py`, `docs/gen_ref_pages.py`, `tests/conftest.py`, and every test file in the cardinal-equivalence net that imports the old module paths.

This task is a pure rename: `SectionScene` still takes `direction`, `SectionManager` still keys by direction, `ViewMarkerArrow` / `SharedCropBox` / `ViewMarkerManager` keep their bodies inside `section_marker.py` until Task 3 and Task 8 replace them. Everything must stay green.

- [ ] **Step 1: git mv**

```bash
cd "/d/Custom Code/FirePro3D/.worktrees/feature-section-views"
git mv firepro3d/elevation_scene.py firepro3d/section_scene.py
git mv firepro3d/elevation_manager.py firepro3d/section_manager.py
git mv firepro3d/view_marker.py firepro3d/section_marker.py
```

- [ ] **Step 2: Rename the classes in the moved files (Edit tool, one occurrence at a time)**

In `firepro3d/section_scene.py`: `class ElevationScene(HaloSelectionMixin, QGraphicsScene):` -> `class SectionScene(HaloSelectionMixin, QGraphicsScene):`; the module docstring header `elevation_scene.py` -> `section_scene.py`. Add after the class, so Task 1 breaks no `isinstance` reader before Task 3 removes it:

```python
ElevationScene = SectionScene   # retired alias -- removed in Task 3
```

In `firepro3d/elevation_view.py`: `class ElevationView(QGraphicsView):` -> `class SectionView(QGraphicsView):` and add `ElevationView = SectionView   # retired alias -- removed in Task 11`.

In `firepro3d/section_manager.py`: `class ElevationManager:` -> `class SectionManager:`; imports become `from .section_scene import SectionScene` and `from .elevation_view import SectionView`; every `ElevationScene` / `ElevationView` inside the file becomes `SectionScene` / `SectionView`. Add `ElevationManager = SectionManager   # retired alias -- removed in Task 11`.

- [ ] **Step 3: Rewrite the imports at every consumer**

Grep first (VC4): `grep -rn "elevation_scene\|elevation_manager\|view_marker\|ElevationScene\|ElevationManager\|ElevationView" --include=*.py . docs/gen_ref_pages.py`. Expected sites (from the 1b map): `main.py:415-416` (`from firepro3d.elevation_manager import ElevationManager` -> `from firepro3d.section_manager import SectionManager` and the constructor call), `main.py:1438` (`from firepro3d.view_marker import ViewMarkerManager` -> `from firepro3d.section_marker import ViewMarkerManager`), `docs/gen_ref_pages.py:21, 39` (module names), `tests/conftest.py:429` (`from firepro3d.elevation_scene import ElevationScene` -> `from firepro3d.section_scene import SectionScene`, and the call), every `from firepro3d.elevation_scene import ...` / `from firepro3d.view_marker import ...` / `from firepro3d.elevation_view import ElevationView` in `tests/` (keep the imported *names* -- `_ElevProxyRect`, `_ROLE_SOURCE`, `ElevGridlineItem`, `ElevDatumItem`, `_is_cardinal_for_elevation`, `ViewMarkerArrow`, `SharedCropBox`, `ViewMarkerManager` all still exist after this task). `main.py` keeps the attribute name `self.elevation_manager` until Task 11.

- [ ] **Step 4: Run the cardinal-equivalence net**

Run (Bash): `"D:/Custom Code/FirePro3D/venv/Scripts/python.exe" -m pytest <the net listed under Conventions> -q`
Expected: all pass except the VC7-proved `test_empty_click_deselects` (order flake) -- confirm it passes alone: `... -m pytest tests/test_elev_selection_interaction.py::test_empty_click_deselects -q`.

- [ ] **Step 5: Retired-path grep and commit**

`grep -rn "firepro3d.elevation_scene\|firepro3d.elevation_manager\|firepro3d.view_marker\|from .elevation_scene\|from .elevation_manager\|from .view_marker" --include=*.py .` must return nothing.

```bash
git add firepro3d/section_scene.py firepro3d/section_manager.py firepro3d/section_marker.py firepro3d/elevation_view.py main.py docs/gen_ref_pages.py tests/conftest.py <each edited test file>
git commit -F <message file>   # "refactor(section): move elevation_* / view_marker to section_* and rename the classes (S0, no behaviour change)"
```

**Keep-green:** the cardinal-equivalence net.

### Task 2: `SectionBasis` -- the oblique projection and the crop-box classification math

**Files:**
- Modify: `firepro3d/section_marker.py` (add at module top, below the constants; the old classes stay below it until Tasks 3 / 8)
- Test: `tests/test_section_projection.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""Section basis guards: cardinal h parity with the retired _world_to_elev table,
45-degree h / d on hand-computed points, painter order, classification."""
import math
import pytest

from firepro3d.section_marker import SectionBasis


# Pre-rename _world_to_elev (elevation_scene.py @ aeab43ff): h for each cardinal.
_OLD_H = {"north": lambda wx, wy: -wx, "south": lambda wx, wy: wx,
          "east": lambda wx, wy: wy, "west": lambda wx, wy: -wy}
# Pre-rename depth key (closer = larger key): north +wy, south -wy, east +wx, west -wx.
_OLD_KEY = {"north": lambda wx, wy: wy, "south": lambda wx, wy: -wy,
            "east": lambda wx, wy: wx, "west": lambda wx, wy: -wx}
# World-coordinate cardinal cuts around a 20 m x 10 m box (x -10000..10000, y -5000..5000).
_CUTS = {"north": ((10000.0, 5000.0), (-10000.0, 5000.0)),
         "south": ((-10000.0, -5000.0), (10000.0, -5000.0)),
         "east": ((10000.0, -5000.0), (10000.0, 5000.0)),
         "west": ((-10000.0, 5000.0), (-10000.0, -5000.0))}
_PTS = [(0.0, 0.0), (1234.5, -678.9), (-4000.0, 2500.0), (9999.0, 4999.0), (-9999.0, -4999.0)]


@pytest.mark.parametrize("card", list(_CUTS))
def test_cardinal_h_matches_pre_rename_table(card):
    a, b = _CUTS[card]
    basis = SectionBasis.from_cut(a, b, look_sign=1, depth_mm=10000.0)
    for wx, wy in _PTS:
        h, v = basis.project(wx, wy, 3000.0)
        assert h == pytest.approx(_OLD_H[card](wx, wy), abs=1e-9)
        assert v == -3000.0


@pytest.mark.parametrize("card", list(_CUTS))
def test_cardinal_sort_order_matches_pre_rename_depth(card):
    a, b = _CUTS[card]
    basis = SectionBasis.from_cut(a, b, look_sign=1, depth_mm=10000.0)
    new = sorted(_PTS, key=lambda p: basis.sort_key(*p))
    old = sorted(_PTS, key=lambda p: _OLD_KEY[card](*p))
    assert new == old


def test_45_degree_h_and_d_hand_computed():
    # Cut from (0, 0) to (1000, 1000): D = (1, 1)/sqrt2, N = (-1, 1)/sqrt2 (look_sign +1).
    basis = SectionBasis.from_cut((0.0, 0.0), (1000.0, 1000.0), look_sign=1, depth_mm=5000.0)
    r2 = math.sqrt(2.0)
    assert basis.h(1000.0, 0.0) == pytest.approx(1000.0 / r2)
    assert basis.d(1000.0, 0.0) == pytest.approx(-1000.0 / r2)       # in front
    assert basis.d(0.0, 1000.0) == pytest.approx(1000.0 / r2)        # look side
    assert (basis.h_min, basis.h_max) == pytest.approx((0.0, 2000.0 / r2))
    flipped = SectionBasis.from_cut((0.0, 0.0), (1000.0, 1000.0), look_sign=-1, depth_mm=5000.0)
    assert flipped.d(0.0, 1000.0) == pytest.approx(-1000.0 / r2)


def test_classify_polygon_cut_behind_hidden_and_chord():
    basis = SectionBasis.from_cut((0.0, 0.0), (10000.0, 0.0), look_sign=1, depth_mm=4000.0)  # looks toward +y
    square = lambda cx, cy, half: [(cx - half, cy - half), (cx + half, cy - half),
                                   (cx + half, cy + half), (cx - half, cy + half)]
    zone, lo, hi = basis.classify_polygon(square(5000.0, 0.0, 500.0))     # straddles the cut
    assert zone == "cut" and (lo, hi) == pytest.approx((4500.0, 5500.0))
    assert basis.classify_polygon(square(5000.0, 2000.0, 500.0))[0] == "behind"
    assert basis.classify_polygon(square(5000.0, -2000.0, 500.0))[0] == "hidden"   # in front
    assert basis.classify_polygon(square(5000.0, 6000.0, 500.0))[0] == "hidden"    # beyond depth
    assert basis.classify_polygon(square(15000.0, 2000.0, 500.0))[0] == "hidden"   # laterally outside
    # Collinear overlap counts as cut (spec s13): a 200 mm thick wall lying on the line.
    zone, lo, hi = basis.classify_polygon(square(5000.0, 0.0, 100.0))
    assert zone == "cut"
    # Behind item laterally straddling h_B is still behind (clipped later by the scene).
    assert basis.classify_polygon(square(10000.0, 2000.0, 500.0))[0] == "behind"


def test_classify_segment_crossing_param_and_collinear_midpoint():
    basis = SectionBasis.from_cut((0.0, 0.0), (10000.0, 0.0), look_sign=1, depth_mm=4000.0)
    zone, h, t = basis.classify_segment((3000.0, -1000.0), (3000.0, 3000.0))
    assert zone == "cut" and h == pytest.approx(3000.0) and t == pytest.approx(0.25)
    zone, h, t = basis.classify_segment((2000.0, 0.0), (6000.0, 0.0))        # along the cut
    assert zone == "cut" and h == pytest.approx(4000.0) and t == pytest.approx(0.5)
    assert basis.classify_segment((1000.0, 1000.0), (2000.0, 3000.0))[0] == "behind"
    assert basis.classify_segment((1000.0, -1000.0), (2000.0, -3000.0))[0] == "hidden"
    assert basis.classify_segment((20000.0, 1000.0), (30000.0, 1000.0))[0] == "hidden"


def test_classify_point_never_cut():
    basis = SectionBasis.from_cut((0.0, 0.0), (10000.0, 0.0), look_sign=1, depth_mm=4000.0)
    assert basis.classify_point((5000.0, 0.0)) == "behind"      # on the line: not cut
    assert basis.classify_point((5000.0, 1000.0)) == "behind"
    assert basis.classify_point((5000.0, -1.0)) == "hidden"
    assert basis.classify_point((5000.0, 4001.0)) == "hidden"


def test_degenerate_cut_rejected():
    with pytest.raises(ValueError):
        SectionBasis.from_cut((0.0, 0.0), (0.0, 0.0), look_sign=1, depth_mm=1.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `"D:/Custom Code/FirePro3D/venv/Scripts/python.exe" -m pytest tests/test_section_projection.py -q`
Expected: FAIL -- `ImportError: cannot import name 'SectionBasis'`.

- [ ] **Step 3: Implement `SectionBasis`**

Add to `firepro3d/section_marker.py` right after the `CROP_MARGIN` constant (the module already imports `math`, `QPointF`, `QRectF`, `QPolygonF`; add `from dataclasses import dataclass` to the stdlib imports):

```python

MIN_CUT_LEN = 100.0          # mm -- shorter cuts are refused at placement (spec s9)
FALLBACK_HALF = 10000.0      # mm -- auto-extent box when the project is empty (spec s13)

ZONE_CUT = "cut"
ZONE_BEHIND = "behind"
ZONE_HIDDEN = "hidden"


@dataclass(frozen=True)
class SectionBasis:
    """Origin-free oblique basis of one section (spec s4.1), world mm.

    ``h(p) = p . D`` (along the cut, no origin term so cardinals match the
    retired ``_world_to_elev`` bit for bit), ``d(p) = (p - A) . N`` (signed
    distance from the cut line, + on the look side), ``v = -z``.
    """

    ax: float
    ay: float
    dx: float
    dy: float
    nx: float
    ny: float
    length: float
    depth: float

    @classmethod
    def from_cut(cls, a, b, look_sign: int, depth_mm: float) -> "SectionBasis":
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        length = math.hypot(bx - ax, by - ay)
        if length <= 0.0 or depth_mm <= 0.0:
            raise ValueError("degenerate section: zero cut length or depth")
        dx, dy = (bx - ax) / length, (by - ay) / length
        s = 1 if look_sign >= 0 else -1
        return cls(ax, ay, dx, dy, s * -dy, s * dx, length, float(depth_mm))

    # -- projection --------------------------------------------------------
    def h(self, x: float, y: float) -> float:
        return x * self.dx + y * self.dy

    def d(self, x: float, y: float) -> float:
        return (x - self.ax) * self.nx + (y - self.ay) * self.ny

    def project(self, x: float, y: float, z: float) -> tuple[float, float]:
        return self.h(x, y), -z

    def sort_key(self, x: float, y: float) -> float:
        """Ascending sort = farthest first (today's ``_assign_depth_z_values``)."""
        return -self.d(x, y)

    @property
    def h_a(self) -> float:
        return self.h(self.ax, self.ay)

    @property
    def h_b(self) -> float:
        return self.h(self.ax + self.dx * self.length, self.ay + self.dy * self.length)

    @property
    def h_min(self) -> float:
        return min(self.h_a, self.h_b)

    @property
    def h_max(self) -> float:
        return max(self.h_a, self.h_b)

    # -- classification (spec s4.2) ------------------------------------------
    def _in_box(self, h: float, d: float, eps: float = 1e-9) -> bool:
        return (self.h_min - eps <= h <= self.h_max + eps
                and -eps <= d <= self.depth + eps)

    def _cut_params(self, p, q) -> list[float]:
        """Params t in [0, 1] along p->q where the segment meets the cut
        segment A->B; a collinear overlap returns its two end params."""
        d1, d2 = self.d(*p), self.d(*q)
        h1, h2 = self.h(*p), self.h(*q)
        eps = 1e-9
        if abs(d1) <= eps and abs(d2) <= eps:                 # collinear
            lo, hi = sorted((h1, h2))
            ov_lo, ov_hi = max(lo, self.h_min), min(hi, self.h_max)
            if ov_lo > ov_hi + eps:
                return []
            if abs(h2 - h1) <= eps:
                return [0.0] if self._in_box(h1, 0.0) else []
            return sorted(((ov_lo - h1) / (h2 - h1), (ov_hi - h1) / (h2 - h1)))
        if (d1 > eps and d2 > eps) or (d1 < -eps and d2 < -eps):
            return []
        t = d1 / (d1 - d2)
        h = h1 + t * (h2 - h1)
        return [t] if self.h_min - eps <= h <= self.h_max + eps else []

    def classify_segment(self, p, q):
        """``(zone, h_at_cut, t_at_cut)`` for a segment footprint (pipe)."""
        ts = self._cut_params(p, q)
        if ts:
            t = sum(ts) / len(ts)                      # overlap midpoint when collinear
            x = p[0] + t * (q[0] - p[0])
            y = p[1] + t * (q[1] - p[1])
            return ZONE_CUT, self.h(x, y), t
        if self._segment_meets_box(p, q):
            return ZONE_BEHIND, None, None
        return ZONE_HIDDEN, None, None

    def _segment_meets_box(self, p, q) -> bool:
        """Liang-Barsky clip of p->q against the (h, d) box."""
        h1, d1, h2, d2 = self.h(*p), self.d(*p), self.h(*q), self.d(*q)
        t0, t1 = 0.0, 1.0
        for dp, lo, hi in ((h2 - h1, self.h_min - h1, self.h_max - h1),
                           (d2 - d1, 0.0 - d1, self.depth - d1)):
            if abs(dp) < 1e-12:
                if lo > 0.0 or hi < 0.0:
                    return False
                continue
            ta, tb = lo / dp, hi / dp
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 > t1:
                return False
        return True

    def classify_polygon(self, pts):
        """``(zone, h_lo, h_hi)`` for a closed footprint (wall quad, slab)."""
        n = len(pts)
        if n < 3:
            return ZONE_HIDDEN, None, None
        poly = QPolygonF([QPointF(x, y) for x, y in pts])
        hs = []
        for i in range(n):
            p, q = pts[i], pts[(i + 1) % n]
            for t in self._cut_params(p, q):
                hs.append(self.h(p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
        a = QPointF(self.ax, self.ay)
        b = QPointF(self.ax + self.dx * self.length, self.ay + self.dy * self.length)
        for end, h_end in ((a, self.h_a), (b, self.h_b)):
            if poly.containsPoint(end, Qt.FillRule.OddEvenFill):
                hs.append(h_end)
        if hs:
            return ZONE_CUT, min(hs), max(hs)
        # Behind: footprint meets the box. Vertex in box, box corner in
        # footprint, or an edge crossing a box edge.
        if any(self._in_box(self.h(x, y), self.d(x, y)) for x, y in pts):
            return ZONE_BEHIND, None, None
        corners = self._box_corners()
        if any(poly.containsPoint(QPointF(cx, cy), Qt.FillRule.OddEvenFill) for cx, cy in corners):
            return ZONE_BEHIND, None, None
        for i in range(n):
            if self._segment_meets_box(pts[i], pts[(i + 1) % n]):
                return ZONE_BEHIND, None, None
        return ZONE_HIDDEN, None, None

    def _box_corners(self):
        a = (self.ax, self.ay)
        b = (self.ax + self.dx * self.length, self.ay + self.dy * self.length)
        far = (self.nx * self.depth, self.ny * self.depth)
        return [a, b, (b[0] + far[0], b[1] + far[1]), (a[0] + far[0], a[1] + far[1])]

    def classify_point(self, p) -> str:
        """Points (nodes) are never cut (spec s4.2)."""
        return ZONE_BEHIND if self._in_box(self.h(*p), self.d(*p)) else ZONE_HIDDEN
```

`Qt` must be imported in the module (`from PyQt6.QtCore import Qt, QPointF, QRectF` already is).

- [ ] **Step 4: Run tests**

Run: `"D:/Custom Code/FirePro3D/venv/Scripts/python.exe" -m pytest tests/test_section_projection.py -q`
Expected: 11 passed (4 + 4 parametrized + 5).

- [ ] **Step 5: Commit**

```bash
git add firepro3d/section_marker.py tests/test_section_projection.py
git commit -F <message file>   # "feat(section): SectionBasis -- origin-free oblique projection + crop-box classification (S1)"
```

**Keep-green:** `tests/test_section_projection.py` only (nothing consumes the class yet).

### Task 3: `SectionMarker` data core; `SectionScene` reads a marker; cardinals stay bit-identical

**Files:**
- Modify: `firepro3d/section_marker.py` (add `building_bbox`, `cardinal_cut`, `SectionMarker` with geometry / dict / auto-fit only -- paint and grips arrive in Task 8), `firepro3d/section_scene.py`, `tests/conftest.py`
- Test: `tests/test_section_projection.py` (add), `tests/test_section_marker.py` (new, first two tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_section_projection.py`:

```python
def _cardinal_scene(section_scene_for, card):
    from PyQt6.QtCore import QPointF
    from firepro3d.wall import WallSegment
    ms, sec = section_scene_for(card)
    w = WallSegment(QPointF(-3000.0, 1000.0), QPointF(2000.0, -1500.0))   # oblique wall
    ms._walls.append(w)
    ms.addItem(w)
    sec.rebuild()
    return ms, sec


@pytest.mark.parametrize("card", ["north", "south", "east", "west"])
def test_cardinal_scene_wall_rect_matches_old_projection(qapp, section_scene_for, card):
    """The cardinal marker's basis reproduces _world_to_elev: the wall rect's
    h-extent equals min/max of the old table applied to the quad corners."""
    from firepro3d.section_scene import _ElevProxyRect, _ROLE_SOURCE
    ms, sec = _cardinal_scene(section_scene_for, card)
    rects = [it for it in sec.items() if isinstance(it, _ElevProxyRect)
             and it.data(_ROLE_SOURCE) is ms._walls[0]]
    assert len(rects) == 1
    r = rects[0].rect()
    corners = [sec._scene_to_world(p.x(), p.y()) for p in ms._walls[0].mitered_quad()]
    hs = [_OLD_H[card](wx, wy) for wx, wy in corners]
    assert (r.left(), r.right()) == pytest.approx((min(hs), max(hs)), abs=1e-6)
```

Create `tests/test_section_marker.py`:

```python
"""SectionMarker guards: dict round-trip, cardinal seed, auto-extent, PAPER_EXCLUDED."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.section_marker import (SectionMarker, building_bbox, cardinal_cut,
                                      CROP_MARGIN, FALLBACK_HALF)


def test_to_dict_round_trip_all_fields():
    m = SectionMarker("Section 7", QPointF(100.0, 200.0), QPointF(900.0, 650.0),
                      look_sign=-1, depth_mm=3200.0)
    m.gridline_z_overrides["A"] = {"v_top": -5000.0, "v_bot": 500.0}
    d = m.to_dict()
    assert d == {"name": "Section 7", "cut_a": [100.0, 200.0], "cut_b": [900.0, 650.0],
                 "look_sign": -1, "depth_mm": 3200.0, "cardinal": None,
                 "auto_extent": False,
                 "gridline_z_overrides": {"A": {"v_top": -5000.0, "v_bot": 500.0}}}
    m2 = SectionMarker.from_dict(d)
    assert m2.to_dict() == d


def test_cardinal_cut_scene_coordinates_match_basis_table():
    box = QRectF(-10000.0, -5000.0, 20000.0, 10000.0)   # scene: top = -5000 = world y_max
    assert cardinal_cut("north", box) == ((10000.0, -5000.0), (-10000.0, -5000.0), 10000.0)
    assert cardinal_cut("south", box) == ((-10000.0, 5000.0), (10000.0, 5000.0), 10000.0)
    assert cardinal_cut("east", box) == ((10000.0, 5000.0), (10000.0, -5000.0), 20000.0)
    assert cardinal_cut("west", box) == ((-10000.0, -5000.0), (-10000.0, 5000.0), 20000.0)


def test_building_bbox_unions_gridlines_and_items_with_fallback(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.gridline import GridlineItem
    from firepro3d.wall import WallSegment
    ms = Model_Space()
    assert building_bbox(ms) == QRectF(-FALLBACK_HALF - CROP_MARGIN, -FALLBACK_HALF - CROP_MARGIN,
                                       2 * (FALLBACK_HALF + CROP_MARGIN), 2 * (FALLBACK_HALF + CROP_MARGIN))
    gl = GridlineItem(QPointF(-1200.0, 500.0), QPointF(1200.0, 500.0), label="A")
    ms._gridlines.append(gl); ms.addItem(gl)
    w = WallSegment(QPointF(0.0, 0.0), QPointF(4000.0, 0.0))
    ms._walls.append(w); ms.addItem(w)
    bb = building_bbox(ms)
    raw = gl.sceneBoundingRect().united(w.sceneBoundingRect())
    assert bb == raw.adjusted(-CROP_MARGIN, -CROP_MARGIN, CROP_MARGIN, CROP_MARGIN)


def test_paper_excluded_only_on_cardinals():
    c = SectionMarker.cardinal("north", QRectF(-100.0, -100.0, 200.0, 200.0))
    p = SectionMarker("Section 1", QPointF(0.0, 0.0), QPointF(1000.0, 0.0))
    assert c.PAPER_EXCLUDED is True and c.cardinal == "north" and c.auto_extent is True
    assert p.PAPER_EXCLUDED is False and p.cardinal is None and p.auto_extent is False
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_section_marker.py tests/test_section_projection.py -q`
Expected: FAIL -- `ImportError` on `SectionMarker` / `building_bbox` / `cardinal_cut`, and the projection test fails on the `section_scene_for` fixture (`fixture 'section_scene_for' not found`).

- [ ] **Step 3: Add `building_bbox`, `cardinal_cut`, `SectionMarker` (data core)**

In `firepro3d/section_marker.py`, below `SectionBasis`:

```python
def building_bbox(model_space) -> QRectF:
    """Plan-scene bbox of gridlines and every displayable item, plus
    ``CROP_MARGIN`` (spec s4.3). Empty project -> the +/-FALLBACK_HALF box."""
    rect = QRectF()
    lists = (getattr(model_space, "_gridlines", []), getattr(model_space, "_walls", []),
             getattr(model_space, "_floor_slabs", []), getattr(model_space, "_roofs", []),
             getattr(model_space, "_rooms", []), getattr(model_space, "_block_instances", []))
    ss = getattr(model_space, "sprinkler_system", None)
    if ss is not None:
        lists = lists + (list(ss.nodes), list(ss.pipes))
    for items in lists:
        for it in items:
            try:
                r = it.sceneBoundingRect()
            except RuntimeError:          # deleted C++ object
                continue
            if r.isNull():
                continue
            rect = r if rect.isNull() else rect.united(r)
    if rect.isNull():
        rect = QRectF(-FALLBACK_HALF, -FALLBACK_HALF, 2 * FALLBACK_HALF, 2 * FALLBACK_HALF)
    return rect.adjusted(-CROP_MARGIN, -CROP_MARGIN, CROP_MARGIN, CROP_MARGIN)


def cardinal_cut(direction: str, box: QRectF):
    """``((ax, ay), (bx, by), depth)`` in plan-scene coords for a cardinal
    whose crop box is *box*: the cut line is the box edge on the camera side
    (scene top = world north), the look side is the box interior."""
    l, t, r, b = box.left(), box.top(), box.right(), box.bottom()
    if direction == "north":
        return (r, t), (l, t), box.height()
    if direction == "south":
        return (l, b), (r, b), box.height()
    if direction == "east":
        return (r, b), (r, t), box.width()
    if direction == "west":
        return (l, t), (l, b), box.width()
    raise ValueError(direction)


CARDINALS = ("north", "south", "east", "west")


class SectionMarker(QGraphicsItem):
    """A section's cut line + crop box on the plan (spec s6).

    Geometry is plan-scene coordinates (``DetailMarker.crop_rect`` convention);
    ``SectionScene`` converts to world through ``_scene_to_world``. Paint,
    grips, menu and properties are added in a later task; this core carries
    the fields, the dict round-trip and the cardinal auto-extent fit.
    """

    HALO_AREA = True

    def __init__(self, name: str, cut_a: QPointF, cut_b: QPointF,
                 look_sign: int = 1, depth_mm: float = 10000.0,
                 cardinal: "str | None" = None, auto_extent: bool = False,
                 parent: QGraphicsItem | None = None):
        super().__init__(parent)
        self._name = name
        self._a = QPointF(cut_a)
        self._b = QPointF(cut_b)
        self._look = 1 if look_sign >= 0 else -1
        self._depth = float(depth_mm)
        self._cardinal = cardinal
        self._auto_extent = bool(auto_extent) if cardinal else False
        self.gridline_z_overrides: dict[str, dict] = {}
        self._manager = None                     # set by SectionManager
        self.PAPER_EXCLUDED = cardinal is not None    # s6.4: cardinals never plot
        self._exclude_from_bulk_select = True
        self.level = DEFAULT_LEVEL               # display-manager categorization
        self._display_overrides: dict = {}
        self._marker_color = QColor(GRID_COLOR)
        self._fill_color = QColor("#1a1a2e")
        self._display_font_size: int | None = None
        self.setZValue(Z_OVERLAY)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    @classmethod
    def cardinal(cls, direction: str, box: QRectF) -> "SectionMarker":
        a, b, depth = cardinal_cut(direction, box)
        return cls(direction.title(), QPointF(*a), QPointF(*b), 1, depth,
                   cardinal=direction, auto_extent=True)

    # -- fields -----------------------------------------------------------
    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, v: str):
        self._name = str(v)
        self.update()

    @property
    def cut_a(self) -> QPointF:
        return QPointF(self._a)

    @property
    def cut_b(self) -> QPointF:
        return QPointF(self._b)

    @property
    def look_sign(self) -> int:
        return self._look

    @property
    def depth_mm(self) -> float:
        return self._depth

    @property
    def cardinal(self) -> "str | None":
        return self._cardinal

    @property
    def auto_extent(self) -> bool:
        return self._auto_extent

    @property
    def view_type(self) -> str:
        return "elevation" if self._cardinal else "section"

    @property
    def view_name(self) -> str:
        """The name consumers key on: the direction for a cardinal (s7.2)."""
        return self._cardinal if self._cardinal else self._name

    def normal_scene(self) -> tuple[float, float]:
        """Unit look normal in plan-scene coords (y-down): ``look * (D.y, -D.x)``."""
        dx, dy = self._b.x() - self._a.x(), self._b.y() - self._a.y()
        L = math.hypot(dx, dy) or 1.0
        return self._look * dy / L, -self._look * dx / L

    def box_polygon(self) -> QPolygonF:
        nx, ny = self.normal_scene()
        far = QPointF(nx * self._depth, ny * self._depth)
        return QPolygonF([self._a, self._b, self._b + far, self._a + far])

    # -- mutation (grips / menu / manager call these) -----------------------
    def set_geometry(self, a: QPointF, b: QPointF, depth_mm: float, *, user: bool = True):
        self.prepareGeometryChange()
        self._a, self._b, self._depth = QPointF(a), QPointF(b), float(depth_mm)
        if user and self._cardinal:
            self._auto_extent = False            # first user edit owns the box (s4.3)
        self.update()
        self._notify()

    def flip(self):
        self._look = -self._look
        self.update()
        self._notify()

    def _notify(self):
        mgr = self._manager
        if mgr is not None:
            mgr.on_marker_geometry_changed(self)

    def auto_fit(self, model_space) -> bool:
        """Re-seed a cardinal's box from the building; True when geometry moved."""
        if not self._auto_extent or not self._cardinal:
            return False
        a, b, depth = cardinal_cut(self._cardinal, building_bbox(model_space))
        a, b = QPointF(*a), QPointF(*b)
        if a == self._a and b == self._b and depth == self._depth:
            return False
        self.prepareGeometryChange()
        self._a, self._b, self._depth = a, b, depth
        self.update()
        return True

    # -- geometry stubs (Task 8 replaces) --------------------------------------
    def boundingRect(self) -> QRectF:
        return self.box_polygon().boundingRect().adjusted(-MARKER_SIZE, -MARKER_SIZE,
                                                          MARKER_SIZE, MARKER_SIZE)

    def paint(self, painter, option, widget=None):
        pass

    # -- serialization (spec s8) ------------------------------------------------
    def to_dict(self) -> dict:
        return {"name": self._name,
                "cut_a": [self._a.x(), self._a.y()],
                "cut_b": [self._b.x(), self._b.y()],
                "look_sign": self._look, "depth_mm": self._depth,
                "cardinal": self._cardinal, "auto_extent": self._auto_extent,
                "gridline_z_overrides": dict(self.gridline_z_overrides)}

    @classmethod
    def from_dict(cls, d: dict) -> "SectionMarker":
        m = cls(d["name"], QPointF(*d["cut_a"]), QPointF(*d["cut_b"]),
                int(d.get("look_sign", 1)), float(d.get("depth_mm", 10000.0)),
                cardinal=d.get("cardinal"), auto_extent=bool(d.get("auto_extent", False)))
        m.gridline_z_overrides = dict(d.get("gridline_z_overrides", {}))
        return m
```

Imports needed at the top of the module (grep before adding -- `QGraphicsItem`, `QColor`, `QPolygonF`, `DEFAULT_LEVEL`, `Z_OVERLAY`, `GRID_COLOR`, `BUBBLE_RADIUS_MM`, `math` are already imported by the old `view_marker.py` header).

- [ ] **Step 4: `SectionScene` takes a marker**

In `firepro3d/section_scene.py`:

(a) Constructor: replace `def __init__(self, direction: str, model_space: "Model_Space", ...)` and `self._direction = direction.lower()` with

```python
    def __init__(self, marker, model_space: "Model_Space",
                 level_manager: "LevelManager", scale_manager: "ScaleManager",
                 parent=None):
        super().__init__(parent)
        self._marker = marker
        self._direction = marker.cardinal or "section"   # legacy readers (tests, tab titles)
        self._basis = None                                # built per rebuild
```

Keep every other line of `__init__`. Replace the body of the `direction` property with `return self._direction` (unchanged) and add:

```python
    @property
    def marker(self):
        return self._marker

    @property
    def basis(self):
        return self._basis
```

(b) `rebuild()`: after `self._apply_theme_colours()` insert

```python
        if self._marker.auto_fit(self._ms):
            pass                                  # geometry re-seeded (s4.3); basis below reads it
        a = self._scene_to_world(self._marker.cut_a.x(), self._marker.cut_a.y())
        b = self._scene_to_world(self._marker.cut_b.x(), self._marker.cut_b.y())
        self._basis = SectionBasis.from_cut(a, b, self._marker.look_sign,
                                            self._marker.depth_mm / self._ppm())
```

and `from .section_marker import SectionBasis, ZONE_CUT, ZONE_BEHIND, ZONE_HIDDEN` at the module imports (no cycle: `section_marker` imports nothing from the scene).

(c) Retire `_world_to_elev`: rename the method to `_project(self, wx, wy, wz)` with body `return self._basis.project(wx, wy, wz)`; replace every `self._world_to_elev(` call in the file (walls, openings, pipes, sprinklers, slabs, roofs, gridlines, datum extent -- 12 sites) with `self._project(`.

(d) Retire the five depth if-chains. In `_project_walls` replace the block from `if d == "north":` through `depth = centroid_y` (the else) with `depth = self._basis.sort_key(centroid_x, centroid_y)`; the same in `_project_openings` (`depth = self._basis.sort_key(wc_x, wc_y)`), `_project_pipes` (`depth = self._basis.sort_key(cx, cy)`), `_project_sprinklers` (`depth = self._basis.sort_key(wx, wy)`), `_project_floor_slabs` (`depth = self._basis.sort_key(cx, cy)`). Delete the now-unused `d = self._direction` lines in those five methods.

(e) Gridline overrides move to the marker: replace `self._gridline_z_overrides: dict[str, dict] = {}` in `__init__` with a property

```python
    @property
    def _gridline_z_overrides(self) -> dict:
        return self._marker.gridline_z_overrides
```

(`ElevGridlineItem._commit_grip_override` writes `scene._gridline_z_overrides[label] = ...` -- a dict mutation through the property, unchanged). Delete `to_dict` / `from_dict` from the scene (the marker owns persistence now); grep `elev.to_dict\|scene.to_dict` in tests first -- none expected.

(f) `_is_cardinal_for_elevation` stays for this task (Task 6 retires it) but `_project_gridlines` and `_datum_extent` call it with `self._direction`, which is `"section"` for a placed marker -> they return nothing for placed sections until Task 6. Acceptable in G1.

(g) Delete the `ElevationScene = SectionScene` alias.

- [ ] **Step 5: conftest fixture**

Rename the fixture in `tests/conftest.py` to `section_scene_for` and build a cardinal marker:

```python
@pytest.fixture
def section_scene_for(qapp):
    """Factory ``(direction="north") -> (model_scene, section_scene)``: a fresh
    Model_Space + LevelManager (Level 1 at 0.0) + uncalibrated ScaleManager,
    wrapped in a SectionScene bound to a cardinal marker (auto-extent)."""
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_scene import SectionScene
    from firepro3d.section_marker import SectionMarker, building_bbox

    def _factory(direction: str = "north"):
        ms = Model_Space()
        lm = LevelManager()
        ms._level_manager = lm
        sm = ScaleManager()
        ms.scale_manager = sm
        marker = SectionMarker.cardinal(direction, building_bbox(ms))
        sec = SectionScene(marker, model_space=ms, level_manager=lm, scale_manager=sm)
        return ms, sec

    return _factory
```

Then grep `elevation_scene_for` across `tests/` and rename every use (18 files from the 1b map: `conftest.py`, `test_elev_*` x5, `test_floor_elevation_projection.py`, `test_halo_*` x3, `test_hf1_seam_fixes.py`, `test_hf1_universal_picker_c.py`, `test_opening_render.py`, `test_rubber_band_commit.py`). Any test that constructs `SectionScene(direction, ...)` / `ElevationScene("north", ...)` directly (grep `ElevationScene(\|SectionScene(` in tests) is rewritten to build a marker with `SectionMarker.cardinal(direction, building_bbox(ms))` first.

- [ ] **Step 6: `SectionManager` (still direction-keyed) builds a cardinal marker**

In `firepro3d/section_manager.py` `open_elevation`: replace `scene = SectionScene(direction, self._ms, self._lm, self._sm)` with

```python
        from .section_marker import SectionMarker, building_bbox
        marker = SectionMarker.cardinal(direction, building_bbox(self._ms))
        scene = SectionScene(marker, self._ms, self._lm, self._sm)
```

(Task 11 replaces this with the marker registry; this keeps the app and `test_hf1_seam_fixes` running in G1.)

- [ ] **Step 7: Run the net + new tests**

Run: `... -m pytest tests/test_section_projection.py tests/test_section_marker.py <cardinal-equivalence net> -q`
Expected: all green except the VC7 order flake. RED proof for (d): with `s * -dy, s * dx` in `SectionBasis.from_cut` swapped to `s * dy, s * -dx`, `test_cardinal_sort_order_matches_pre_rename_depth` fails on every cardinal; restore.

- [ ] **Step 8: Commit**

```bash
git add firepro3d/section_marker.py firepro3d/section_scene.py firepro3d/section_manager.py tests/conftest.py tests/test_section_projection.py tests/test_section_marker.py <renamed-fixture test files>
git commit -F <message file>   # "feat(section): SectionMarker data core; SectionScene projects through a marker basis (cardinals bit-identical)"
```

**Keep-green:** the net + the two new files.

### Task 4: Classification and lateral clip in the scene; cardinal auto-extent guard

**Files:**
- Modify: `firepro3d/section_scene.py` (`_project_walls`, `_project_openings`, `_project_pipes`, `_project_sprinklers`, `_project_floor_slabs`, `_project_roofs`)
- Test: `tests/test_section_classification.py` (new)

Behaviour: every footprint is classified through `self._basis`; `hidden` items are skipped; `behind` items get today's rendering with `h` clipped to `[h_min, h_max]`; `cut` items are **collected** into `self._cut_items` (a list of `(kind, source, data)`) and rendered by Task 5 -- in this task a cut wall / slab / pipe is drawn with today's behind rendering so nothing disappears between tasks.

- [ ] **Step 1: Write the failing tests**

```python
"""Crop-box classification on real Wall / Pipe / FloorSlab footprints, lateral
clip, and the cardinal auto-extent rule (spec s4.2 / s4.3)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.section_marker import SectionMarker, ZONE_CUT, ZONE_BEHIND, ZONE_HIDDEN


def _placed_scene(section_scene_for, a, b, depth):
    """A placed (non-cardinal) section A->B with look_sign +1 over a fresh model."""
    from firepro3d.section_scene import SectionScene
    ms, _ = section_scene_for("north")
    marker = SectionMarker("Section 1", QPointF(*a), QPointF(*b), 1, depth)
    sec = SectionScene(marker, ms, ms._level_manager, ms.scale_manager)
    return ms, sec


def _wall(ms, p, q):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(*p), QPointF(*q))
    ms._walls.append(w); ms.addItem(w)
    return w


def _source_rects(sec, src):
    from firepro3d.section_scene import _ElevProxyRect, _ROLE_SOURCE
    return [it for it in sec.items() if isinstance(it, _ElevProxyRect) and it.data(_ROLE_SOURCE) is src]


def test_wall_zones_by_footprint_on_a_horizontal_cut(qapp, section_scene_for):
    # Scene coords: cut along y = 0 from x=0 to x=10000, look_sign +1 -> N_s = (0, -1) = scene-up.
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    cut = _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))      # straddles the line
    behind = _wall(ms, (1000.0, -2000.0), (6000.0, -2000.0))  # scene-up = look side
    front = _wall(ms, (1000.0, 2000.0), (6000.0, 2000.0))     # other side
    deep = _wall(ms, (1000.0, -6000.0), (6000.0, -6000.0))    # beyond depth
    sec.rebuild()
    assert sec.zone_of(cut) == ZONE_CUT
    assert sec.zone_of(behind) == ZONE_BEHIND and _source_rects(sec, behind)
    assert sec.zone_of(front) == ZONE_HIDDEN and not _source_rects(sec, front)
    assert sec.zone_of(deep) == ZONE_HIDDEN and not _source_rects(sec, deep)


def test_behind_wall_is_clipped_laterally_not_vertically(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (-5000.0, -2000.0), (15000.0, -2000.0))      # overhangs both ends
    sec.rebuild()
    (r,) = _source_rects(sec, w)
    b = sec.basis
    assert (r.rect().left(), r.rect().right()) == pytest.approx((b.h_min, b.h_max), abs=1e-6)
    assert r.rect().height() == pytest.approx(w._height_mm, abs=1e-6)   # full wall height


def test_parallel_adjacent_wall_is_behind(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (2000.0, -300.0), (8000.0, -300.0))   # parallel, 300 mm on the look side (wall half-width < 300)
    sec.rebuild()
    assert sec.zone_of(w) == ZONE_BEHIND


def test_45_degree_cut_classifies_pipe_and_slab(qapp, section_scene_for):
    from firepro3d.floor_slab import FloorSlab
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (8000.0, -8000.0), 6000.0)
    n1 = ms.add_node(0.0, -4000.0); n2 = ms.add_node(8000.0, -4000.0)
    pipe = ms.add_pipe(n1, n2)                                   # crosses the diagonal at (4000, -4000)
    slab = FloorSlab(points=[QPointF(5000.0, -1000.0), QPointF(7000.0, -1000.0),
                             QPointF(7000.0, -3000.0), QPointF(5000.0, -3000.0)])
    slab._top_mode = "absolute"
    ms._floor_slabs.append(slab); ms.addItem(slab)
    sec.rebuild()
    assert sec.zone_of(pipe) == ZONE_CUT
    # Slab centroid (6000, -2000): in scene coords the look normal of A=(0,0)->B=(8000,-8000)
    # with look +1 is (D.y, -D.x) = (-1, -1)/sqrt2 -> the slab (x>|y|) is on the other side.
    assert sec.zone_of(slab) == ZONE_HIDDEN
    sec.marker.flip(); sec.rebuild()
    assert sec.zone_of(slab) == ZONE_BEHIND


def test_sprinkler_node_is_never_cut(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    n = ms.add_node(5000.0, 0.0); ms.add_sprinkler(n)
    sec.rebuild()
    assert sec.zone_of(n) == ZONE_BEHIND


def test_auto_extent_refits_then_stops_after_grip(qapp, section_scene_for):
    ms, sec = section_scene_for("north")
    m = sec.marker
    sec.rebuild()
    box0 = m.box_polygon().boundingRect()
    _wall(ms, (-40000.0, 0.0), (-39000.0, 0.0))                 # far outside the seed box
    sec.rebuild()
    box1 = m.box_polygon().boundingRect()
    assert box1.left() < box0.left() - 20000.0                  # re-fit followed the building
    assert sec.zone_of(ms._walls[0]) == ZONE_BEHIND              # and the wall renders
    m.set_geometry(m.cut_a, m.cut_b, m.depth_mm, user=True)      # a grip edit (same numbers)
    assert m.auto_extent is False
    _wall(ms, (60000.0, 0.0), (61000.0, 0.0))
    sec.rebuild()
    assert m.box_polygon().boundingRect() == box1                # no longer follows
    assert sec.zone_of(ms._walls[1]) == ZONE_HIDDEN
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_section_classification.py -q`
Expected: FAIL -- `AttributeError: 'SectionScene' object has no attribute 'zone_of'`.

- [ ] **Step 3: Implement**

In `firepro3d/section_scene.py`:

(a) `rebuild()`: after the basis line add `self._zones: dict[int, str] = {}` and `self._cut_items: list = []`; add

```python
    def zone_of(self, source) -> str:
        """Zone the last rebuild assigned to *source* (cut / behind / hidden)."""
        return self._zones.get(id(source), ZONE_HIDDEN)

    def _clip_h(self, h_min: float, h_max: float):
        """Lateral clip to the crop box; None when nothing remains (s4.2)."""
        lo, hi = max(h_min, self._basis.h_min), min(h_max, self._basis.h_max)
        return (lo, hi) if hi - lo >= 0.5 else None
```

(b) `_project_walls`: after `corners_world` is built insert

```python
            zone, h_lo, h_hi = self._basis.classify_polygon(corners_world)
            self._zones[id(wall)] = zone
            if zone == ZONE_HIDDEN:
                continue
            if zone == ZONE_CUT:
                self._cut_items.append(("wall", wall, (h_lo, h_hi, base_z, top_z)))
                continue
```

and after `h_min = min(h_values); h_max = max(h_values)` insert

```python
            clipped = self._clip_h(h_min, h_max)
            if clipped is None:
                continue
            h_min, h_max = clipped
```

(`width = h_max - h_min` follows, as today.) **Until Task 5 lands**, keep a cut wall drawn: replace the `continue` after the `_cut_items.append` line with nothing (fall through to today's rendering) and remove that fall-through in Task 5.

(c) `_project_openings`: skip openings whose wall is not `ZONE_BEHIND`: at the top of the per-wall loop add `if self._zones.get(id(wall)) != ZONE_BEHIND: continue` (Task 5 renders head/sill for cut walls). After `h_min = min(h_left, h_right); h_max = max(...)` add the same `_clip_h` three lines.

(d) `_project_pipes`: after `wx2, wy2 = ...` add

```python
            zone, h_cut, t_cut = self._basis.classify_segment((wx1, wy1), (wx2, wy2))
            self._zones[id(pipe)] = zone
            if zone == ZONE_HIDDEN:
                continue
            if zone == ZONE_CUT:
                self._cut_items.append(("pipe", pipe, (h_cut, z1 + t_cut * (z2 - z1))))
                # (Task 5 draws the cut circle; until then fall through)
```

then after `h1, v1 = ...; h2, v2 = ...` clip the line to `[h_min, h_max]` by parameter (works for either orientation):

```python
            lo, hi = self._basis.h_min, self._basis.h_max
            if abs(h2 - h1) > 1e-9:
                ta = (lo - h1) / (h2 - h1)
                tb = (hi - h1) / (h2 - h1)
                t0, t1 = max(0.0, min(ta, tb)), min(1.0, max(ta, tb))
                if t0 < t1:
                    h1, v1, h2, v2 = (h1 + t0 * (h2 - h1), v1 + t0 * (v2 - v1),
                                      h1 + t1 * (h2 - h1), v1 + t1 * (v2 - v1))
```

(the `ZONE_BEHIND` verdict already guarantees overlap).

(e) `_project_sprinklers`: after the world conversion `self._zones[id(node)] = self._basis.classify_point((wx, wy))`; `if self._zones[id(node)] == ZONE_HIDDEN: continue`.

(f) `_project_floor_slabs`: after `world_pts` is built: `zone, h_lo, h_hi = self._basis.classify_polygon(world_pts)`, record, skip hidden, append `("slab", slab, (h_lo, h_hi, bot_z, top_z))` for cut (fall through until Task 5), clip `h_min, h_max` with `_clip_h`.

(g) `_project_roofs`: roofs are never cut-rendered in v1 (s5): classify the projected footprint `[(vx, vy) for vx, vy, vz in verts]` with `classify_polygon`; `hidden` -> skip; otherwise today's rect with `_clip_h` on `min(h_vals), max(h_vals)`.

- [ ] **Step 4: Run tests + net**

Run: `... -m pytest tests/test_section_classification.py tests/test_section_projection.py <net> -q`
Expected: green (cardinals: the auto-extent box encloses every footprint by construction -> every item `behind`, no clip). RED proof: set `return rect.adjusted(...)` in `building_bbox` to `return rect` (no margin) -- `test_cardinal_scene_wall_rect_matches_old_projection` must stay green (items touching the box edge are still inside) but `test_auto_extent_refits_then_stops_after_grip` is unaffected; the real RED is `test_wall_zones_by_footprint_on_a_horizontal_cut` with the `if zone == ZONE_HIDDEN: continue` line removed from `_project_walls`. Restore.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/section_scene.py tests/test_section_classification.py
git commit -F <message file>   # "feat(section): classify footprints against the crop box; lateral clip; cardinal auto-extent (S1)"
```

**Keep-green:** the net + `tests/test_section_projection.py tests/test_section_marker.py tests/test_section_classification.py`.

**G1 review (one two-stage review of Tasks 1-4):** spec reviewer checks s3.1 moves, s4.1 table, s4.2 zones, s4.3 auto-extent; quality reviewer reads the OLD `_world_to_elev` / depth if-chains against `SectionBasis` (VC10 port clause).

---

# G2 -- cut rendering, 872 gridlines, 600 sheet colours (FP6 group)

### Task 5: Cut rendering -- wall cross-section with Section colour + pattern, opening head / sill, pipe circle, slab chord

**Files:**
- Modify: `firepro3d/section_scene.py` (new `_ElevCutRect`, `_ElevCutEllipse`; `_render_cut_items`; `_wall_display_props` / `_floor_display_props` / new `_pipe_display_props` read the section columns)
- Test: `tests/test_section_rendering.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""Cut vs behind rendering (spec s5): cut wall = Section colour + pattern,
behind wall = today's Fill; a crossing inside an opening leaves the head;
cut pipe = filled circle of the drawn OD."""
import pytest
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtGui import QColor

from firepro3d.section_marker import SectionMarker
from tests.test_section_classification import _placed_scene, _wall, _source_rects


def _cut_items(sec, src):
    from firepro3d.section_scene import _ElevCutRect, _ElevCutEllipse, _ROLE_SOURCE
    return [it for it in sec.items() if isinstance(it, (_ElevCutRect, _ElevCutEllipse))
            and it.data(_ROLE_SOURCE) is src]


def test_cut_wall_rect_uses_section_colour_and_pattern(qapp, section_scene_for):
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/section", "#aa0000")
    s.setValue("display/Wall/section_pattern", "crosshatch")
    s.setValue("display/Wall/color", "#004400")
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (3000.0, -1000.0), (3000.0, 1000.0))
    sec.rebuild()
    (item,) = _cut_items(sec, w)
    assert item._section_src == "#aa0000" and item._pattern == "crosshatch"
    assert item.resolved_pen_brush()[0].color().name() == "#004400"
    # Geometry: width = the chord of the cut through the mitered quad = wall thickness.
    assert item.rect().width() == pytest.approx(2.0 * w.half_thickness_scene(), abs=1e-6)
    assert item.rect().height() == pytest.approx(w._height_mm, abs=1e-6)
    # It paints the hatch: a QPainter pass on the item calls draw_section_hatch.
    from unittest.mock import patch
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    img = QImage(64, 64, QImage.Format.Format_ARGB32); img.fill(0)
    p = QPainter(img)
    with patch("firepro3d.section_scene.draw_section_hatch") as hatch:
        item.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    assert hatch.call_count == 1
    assert hatch.call_args.kwargs["pattern"] == "crosshatch"
    assert hatch.call_args.kwargs["section_fill"].name() == "#aa0000"


def test_behind_wall_keeps_todays_fill(qapp, section_scene_for):
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Wall/fill", "#123456")
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (1000.0, -2000.0), (6000.0, -2000.0))
    sec.rebuild()
    (r,) = _source_rects(sec, w)
    assert r._brush_src == "#123456" and not _cut_items(sec, w)


def test_cut_through_window_leaves_head_and_sill(qapp, section_scene_for):
    from firepro3d.wall_opening import WallOpening
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    w = _wall(ms, (3000.0, -3000.0), (3000.0, 3000.0))       # 6 m wall crossing at its midpoint
    op = WallOpening(w, offset_along=3000.0, width_mm=1200.0, height_mm=1500.0,
                     sill_mm=900.0, feature_id="window_900")
    w.openings.append(op)
    sec.rebuild()
    items = _cut_items(sec, w)
    assert len(items) == 2
    spans = sorted((-it.rect().bottom(), -it.rect().top()) for it in items)   # (z0, z1) pairs
    assert spans[0] == pytest.approx((0.0, 900.0))              # below the sill
    assert spans[1] == pytest.approx((2400.0, w._height_mm))    # above the head


def test_cut_pipe_circle_diameter_is_drawn_od(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    n1 = ms.add_node(3000.0, -1000.0); n2 = ms.add_node(3000.0, 1000.0)
    n1.z_pos = 2000.0; n2.z_pos = 3000.0
    pipe = ms.add_pipe(n1, n2)
    pipe._display_scale = 2.0
    sec.rebuild()
    (c,) = _cut_items(sec, pipe)
    od = pipe.display_width_mm() * 2.0
    assert c.rect().width() == pytest.approx(od) and c.rect().height() == pytest.approx(od)
    assert c.rect().center().x() == pytest.approx(3000.0) and c.rect().center().y() == pytest.approx(-2500.0)
```

Symbols verified at plan time (VC4): `WallSegment(pt1, pt2, thickness_mm=..., color=...)`, `WallSegment.half_thickness_scene()`, `WallOpening(wall, *, feature_id, offset_along, width_mm, height_mm, sill_mm)` with `feature_id` in `feature.FEATURE_REGISTRY` (`door_914`, `window_900`, `blank_900`; `_type` derives from it), `Model_Space.add_node(x, y)` / `add_pipe(n1, n2)` / `add_sprinkler(n)`.

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_section_rendering.py -q`
Expected: FAIL -- `ImportError: cannot import name '_ElevCutRect'`.

- [ ] **Step 3: Implement**

In `firepro3d/section_scene.py`:

(a) Imports: `from .displayable_item import draw_section_hatch` and extend the colour_tokens import to `from .colour_tokens import resolve_colour, resolve_pen_brush, section_fill_colour`.

(b) Cut item classes, after `_ElevProxyEllipse`:

```python
class _ElevCutRect(_ElevProxyRect):
    """A cut cross-section (wall / slab): Section colour body + Section
    pattern hatch inside the rect, outline in the category Colour (s5)."""

    _section_src = None
    _pattern = "diagonal"
    _hatch_scene = None      # the model scene (pattern registry / drafting factor)

    def set_section(self, section_src, pattern, hatch_scene):
        self._section_src = section_src
        self._pattern = pattern or "diagonal"
        self._hatch_scene = hatch_scene

    def _draw_shape(self, painter):
        pen, _brush = self.resolved_pen_brush()
        path = QPainterPath()
        path.addRect(self.rect())
        draw_section_hatch(painter, path, self._hatch_scene,
                           color=pen.color(), pattern=self._pattern,
                           line_width=1.0,
                           section_fill=section_fill_colour(self._section_src, self),
                           hatch_scale=1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())


class _ElevCutEllipse(_ElevProxyEllipse):
    """A cut pipe: filled circle of the drawn OD in the Section colour (s5)."""
```

(c) Display props: add `"section": s.value("display/Wall/section", "#666666")` and `"section_pattern": s.value("display/Wall/section_pattern", "diagonal")` to `_wall_display_props`; `"section": s.value("display/Floor/section", "#666666")` and `"section_pattern": s.value("display/Floor/section_pattern", "diagonal")` to `_floor_display_props`; add

```python
    def _pipe_display_props(self) -> dict:
        """Read the Pipe Section colour (None in the default row)."""
        s = QSettings("GV", "FirePro3D")
        return {"section": s.value("display/Pipe/section", None)}
```

(d) `rebuild()`: call `self._render_cut_items()` after `self._project_gridlines()` and before `self._assign_depth_z_values()`. Remove the G1 fall-throughs: in `_project_walls`, `_project_pipes` and `_project_floor_slabs` the `ZONE_CUT` branch now ends with `continue`.

(e) The renderer and the opening carve:

```python
    def _render_cut_items(self):
        """Draw every footprint the classification put AT the cut (s5)."""
        from .constants import PIPE_COLORS as _PIPE_COLORS
        wall_props = self._wall_display_props()
        floor_props = self._floor_display_props()
        pipe_sec = self._pipe_display_props()["section"]
        pen_black = QPen(QColor(0, 0, 0), 1)
        pen_black.setCosmetic(True)
        for kind, src, data in self._cut_items:
            if kind in ("wall", "slab"):
                props = wall_props if kind == "wall" else floor_props
                h_lo, h_hi, z_bot, z_top = data
                spans = (self._wall_cut_spans(src, z_bot, z_top) if kind == "wall"
                         else [(z_bot, z_top)])
                for z0, z1 in spans:
                    if z1 - z0 < 1.0 or h_hi - h_lo < 0.5:
                        continue
                    rect = _ElevCutRect(h_lo, -z1, h_hi - h_lo, z1 - z0)
                    rect.setPen(pen_black)
                    rect.set_colour_src(pen=props["color"])
                    rect.set_section(props["section"], props["section_pattern"], self._ms)
                    rect.setOpacity(props["opacity"] / 100.0)
                    rect.setData(_ROLE_SOURCE, src)
                    rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                    self.addItem(rect)
                    self._register_depth_item(0.0, rect)
            elif kind == "pipe":
                h, z = data
                od = src.display_width_mm() * getattr(src, "_display_scale", 1.0)
                col_name = src._properties.get("Colour", {}).get("value", "Red")
                own = _PIPE_COLORS.get(col_name, "#e62828")
                circ = _ElevCutEllipse(h - od / 2.0, -z - od / 2.0, od, od)
                pen = QPen(QColor(own), 1)
                pen.setCosmetic(True)
                circ.setPen(pen)
                circ.set_colour_src(pen=own, brush=pipe_sec or own)
                circ.setData(_ROLE_SOURCE, src)
                circ.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                self.addItem(circ)
                self._register_depth_item(0.0, circ)

    def _wall_cut_spans(self, wall, base_z: float, top_z: float) -> list[tuple[float, float]]:
        """Vertical spans of the cut face: the whole wall, or -- when the
        crossing falls inside an opening -- below the sill (windows) and above
        the head (s5). Scene coords for the along-wall test."""
        import math as _math
        a = wall.centerline_angle_rad()
        p1 = wall.centerline_pt1
        ux, uy = _math.cos(a), _math.sin(a)
        ma, mb = self._marker.cut_a, self._marker.cut_b
        cx, cy = mb.x() - ma.x(), mb.y() - ma.y()
        den = ux * cy - uy * cx
        if abs(den) < 1e-9:
            return [(base_z, top_z)]                       # collinear: no opening carve
        t = ((ma.x() - p1.x()) * cy - (ma.y() - p1.y()) * cx) / den   # along-wall offset
        for op in getattr(wall, "openings", None) or []:
            half = op.width_scene() / 2.0
            if not (op._offset_along - half <= t <= op._offset_along + half):
                continue
            op_lvl = getattr(op, "level", None) or getattr(wall, "_base_level", None)
            z0 = (self._level_z(op_lvl) if op_lvl else 0.0) + op._sill_mm
            z1 = z0 + op._height_mm
            spans = []
            if getattr(op, "_type", "blank") == "window" and z0 > base_z:
                spans.append((base_z, min(z0, top_z)))
            if z1 < top_z:
                spans.append((max(z1, base_z), top_z))
            return spans
        return [(base_z, top_z)]
```

- [ ] **Step 4: Run**

Run: `... -m pytest tests/test_section_rendering.py tests/test_section_classification.py <net> -q`
Expected: green. RED proof: change `section_fill=section_fill_colour(self._section_src, self)` to `section_fill=None` -> `test_cut_wall_rect_uses_section_colour_and_pattern` fails on the `section_fill` assertion; restore.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/section_scene.py tests/test_section_rendering.py
git commit -F <message file>   # "feat(section): cut rendering -- wall / slab cross-sections with Section colour + pattern, opening head/sill, pipe OD circle (S2)"
```

**Keep-green:** net + `tests/test_section_projection.py tests/test_section_marker.py tests/test_section_classification.py tests/test_section_rendering.py`.

### Task 6: 872 -- gridlines crossing the cut line; datum spans the crop box; retire `_is_cardinal_for_elevation`

**Files:**
- Modify: `firepro3d/section_scene.py` (`_project_gridlines`, `_datum_extent`, delete `_is_cardinal_for_elevation` + `_CARDINAL_EPSILON`), `tests/test_gridline_core.py`, `tests/test_gridline_integration.py`
- Test: `tests/test_gridline_section.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""872 / D7a: a gridline crossing the cut line projects vertical at the crossing;
parallel or out-of-box gridlines are absent; datums span [h_min, h_max]."""
import math
import pytest
from PyQt6.QtCore import QPointF

from tests.test_section_classification import _placed_scene


def _gridline(ms, p, q, label):
    from firepro3d.gridline import GridlineItem
    gl = GridlineItem(QPointF(*p), QPointF(*q), label=label)
    ms._gridlines.append(gl); ms.addItem(gl)
    return gl


def _grid_items(sec):
    from firepro3d.section_scene import ElevGridlineItem
    return {it._label: it for it in sec.items() if isinstance(it, ElevGridlineItem)}


def test_30_degree_gridline_draws_vertical_at_crossing(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    # Gridline through (4000, 0) at 30 degrees; its endpoints never touch y = 0 but the
    # infinite line crosses the cut at x = 4000 (spec s5: crossing of the infinite gridline).
    dx, dy = 3000.0 * math.cos(math.radians(30)), 3000.0 * math.sin(math.radians(30))
    _gridline(ms, (4000.0 + dx, dy), (4000.0 + 2 * dx, 2 * dy), "A")
    sec.rebuild()
    items = _grid_items(sec)
    assert set(items) == {"A"}
    gl = items["A"]
    assert gl.line().x1() == pytest.approx(gl.line().x2())                 # vertical
    assert gl.line().x1() == pytest.approx(sec.basis.h(4000.0, 0.0), abs=1e-6)


def test_parallel_and_outside_crossings_are_absent(qapp, section_scene_for):
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    _gridline(ms, (0.0, -2000.0), (10000.0, -2000.0), "P")      # parallel to the cut
    _gridline(ms, (15000.0, -3000.0), (15000.0, 3000.0), "O")   # crosses y=0 at x=15000 > h_max
    _gridline(ms, (5000.0, -3000.0), (5000.0, 3000.0), "I")     # crosses inside
    sec.rebuild()
    assert set(_grid_items(sec)) == {"I"}


def test_cardinal_gridlines_unchanged_from_today(qapp, section_scene_for):
    """North: a vertical-in-plan gridline shows at h = -wx; the horizontal one
    is parallel to the cut -> absent (today's cardinal rule, now derived)."""
    ms, sec = section_scene_for("north")
    _gridline(ms, (2500.0, -3000.0), (2500.0, 3000.0), "1")
    _gridline(ms, (-3000.0, 1000.0), (3000.0, 1000.0), "A")
    sec.rebuild()
    items = _grid_items(sec)
    assert set(items) == {"1"} and items["1"].line().x1() == pytest.approx(-2500.0)


def test_datum_spans_crop_box(qapp, section_scene_for):
    from firepro3d.section_scene import ElevDatumItem
    ms, sec = _placed_scene(section_scene_for, (0.0, 0.0), (10000.0, 0.0), 4000.0)
    sec.rebuild()
    datums = [it for it in sec.items() if isinstance(it, ElevDatumItem)]
    assert datums
    d = datums[0]
    assert (d._h_min, d._h_max) == pytest.approx((sec.basis.h_min, sec.basis.h_max))
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_gridline_section.py -q`
Expected: FAIL -- the 30-degree and parallel/outside tests (a placed section shows no gridline today: `_is_cardinal_for_elevation(..., "section")` is False) and `test_datum_spans_crop_box` (today's extent is the gridline bbox + margin).

- [ ] **Step 3: Implement**

In `firepro3d/section_scene.py`:

(a) Delete `_CARDINAL_EPSILON`, `_is_cardinal_for_elevation` and the "Cardinal filtering" banner above them.

(b) `_project_gridlines`: replace the block from `p1 = QPointF(line_geom.x1(), line_geom.y1())` through `h_avg = (h1 + h2) / 2.0` with

```python
            wx1, wy1 = self._scene_to_world(line_geom.x1(), line_geom.y1())
            wx2, wy2 = self._scene_to_world(line_geom.x2(), line_geom.y2())
            h_avg = self._gridline_crossing_h((wx1, wy1), (wx2, wy2))
            if h_avg is None:
                continue
```

and add the helper next to `_datum_extent`:

```python
    def _gridline_crossing_h(self, p, q):
        """h of the crossing of the INFINITE gridline p->q with the cut line,
        or None when parallel or outside [h_min, h_max] (872, D7a)."""
        b = self._basis
        d1, d2 = b.d(*p), b.d(*q)
        if abs(d2 - d1) < 1e-9:
            return None                                   # parallel to the cut
        t = d1 / (d1 - d2)                                # unbounded: any t
        h = b.h(p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
        if not (b.h_min - 1e-9 <= h <= b.h_max + 1e-9):
            return None
        return h
```

(c) `_datum_extent`: body becomes `return self._basis.h_min, self._basis.h_max`; docstring "H range of the datum lines = the crop box (s5)". Grep `DEFAULT_GRIDLINE_LENGTH_MM` in the module before dropping its local import.

(d) Coupled tests: `tests/test_gridline_core.py` (imports `_is_cardinal_for_elevation`, ~lines 44-55) and `tests/test_gridline_integration.py` (~251-268). Read each; a test asserting the cardinal-only rule is rewritten against the derived behaviour -- vertical-in-plan shows in north/south, horizontal in east/west, an oblique gridline shows in **every** cardinal at its crossing h (ratified by D7a). Drive them through `section_scene_for(card)` + `ElevGridlineItem` presence, never through a helper.

- [ ] **Step 4: Run**

Run: `... -m pytest tests/test_gridline_section.py tests/test_gridline_core.py tests/test_gridline_integration.py <net> -q`
Expected: green. The datum-extent change moves cardinal datum ends: grep `_datum_extent\|_h_min\|_h_max` in `tests/` (no hits at plan time); a failing assertion there is the ratified s5 datum row, rewritten. RED proof: drop the `if not (b.h_min ... )` range check -> `test_parallel_and_outside_crossings_are_absent` fails on "O"; restore.

- [ ] **Step 5: Retired-name grep + commit**

`grep -rn "_is_cardinal_for_elevation\|_CARDINAL_EPSILON" --include=*.py .` returns nothing.

```bash
git add firepro3d/section_scene.py tests/test_gridline_section.py tests/test_gridline_core.py tests/test_gridline_integration.py
git commit -F <message file>   # "feat(section): gridlines crossing the cut project at the crossing; datums span the crop box (872, D7a)"
```

### Task 7: 600 -- edges, voids and masks as per-paint colour sources (`token:bg`)

**Files:**
- Modify: `firepro3d/constants.py`, `firepro3d/colour_tokens.py`, `firepro3d/section_scene.py` (`_project_openings` frame items + void brush, `_project_floor_slabs` mask)
- Test: `tests/test_section_sheet_plot.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""600: a dark-theme sheet viewport of a cardinal section exports edges black
and opening voids / slab masks white; token:bg resolves per surface."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from firepro3d import theme
from firepro3d.constants import TOKEN_AUTO, TOKEN_BG
from tests.test_hf1_seam_fixes import force_theme   # noqa: F401  (fixture re-export)


def test_token_bg_resolves_canvas_bg_on_canvas_and_white_on_paper(qapp, force_theme):
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem
    from firepro3d.colour_tokens import resolve_colour
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    force_theme("dark")
    assert resolve_colour(TOKEN_BG).name() == QColor(theme.DARK.canvas_bg).name()
    paper = QGraphicsScene()
    paper.paints_on_paper = True                  # what _paper_mode reads
    item = QGraphicsRectItem(0, 0, 1, 1)
    paper.addItem(item)
    for mode in (PaperColorMode.BW, PaperColorMode.FULL_COLOR):
        save_paper_color_mode(mode)
        assert resolve_colour(TOKEN_BG, item=item).name() == "#ffffff"


def _section_with_opening_and_slab(section_scene_for):
    from firepro3d.wall import WallSegment
    from firepro3d.wall_opening import WallOpening
    from firepro3d.floor_slab import FloorSlab
    ms, sec = section_scene_for("north")
    w = WallSegment(QPointF(-3000.0, 0.0), QPointF(3000.0, 0.0))
    ms._walls.append(w); ms.addItem(w)
    op = WallOpening(w, offset_along=3000.0, width_mm=1200.0, height_mm=2100.0,
                     sill_mm=0.0, feature_id="door_914")
    w.openings.append(op)
    slab = FloorSlab(points=[QPointF(-3000.0, -500.0), QPointF(3000.0, -500.0),
                             QPointF(3000.0, 500.0), QPointF(-3000.0, 500.0)])
    slab._top_mode = "absolute"
    ms._floor_slabs.append(slab); ms.addItem(slab)
    sec.rebuild()
    return ms, sec, op, slab


def test_void_and_mask_carry_bg_source_frame_carries_auto(qapp, section_scene_for):
    from firepro3d.section_scene import _SrcRect, _ROLE_SOURCE
    ms, sec, op, slab = _section_with_opening_and_slab(section_scene_for)
    void = next(it for it in sec.items() if it.data(_ROLE_SOURCE) is op)
    assert void._brush_src == TOKEN_BG
    frames = [it for it in sec.items() if isinstance(it, _SrcRect) and it._pen_src == TOKEN_AUTO]
    assert frames                                   # the opening frame rect
    masks = [it for it in sec.items() if isinstance(it, _SrcRect)
             and it._brush_src == TOKEN_BG and it.data(_ROLE_SOURCE) is None]
    assert masks                                    # the slab mask


def test_dark_theme_export_edges_black_voids_white(qapp, tmp_path, force_theme, section_scene_for):
    """Acceptance (b): the exported PDF's drawings inside the viewport hold a
    black stroke (frame) and white fills (void + mask) and no canvas colours."""
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    from tests.test_lt1_block_paper import _export
    from tests.test_hf1_seam_fixes import _plot_colours
    force_theme("dark")
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    ms, sec, op, slab = _section_with_opening_and_slab(section_scene_for)
    pdf = _export(tmp_path, sec, 0.02, "section600.pdf")     # resolver returns (sec, crop)
    strokes, fills = _plot_colours(pdf)
    assert (0.0, 0.0, 0.0) in strokes, strokes
    assert (1.0, 1.0, 1.0) in fills, fills
    dark_bg = tuple(round(c / 255.0, 2) for c in QColor(theme.DARK.canvas_bg).getRgb()[:3])
    assert dark_bg not in fills and (0.82, 0.82, 0.82) not in strokes   # #d0d0d0 edge retired
```

`_export` crops to a window of half-size 80/2/0.02 = 2000 scene units centred on (0, 0): the wall face (h -3000..3000, v -height..0), the door void and the slab mask cross it. `_export` declares the viewport as `("plan", "Plan: Level 1", ...)` with a `MagicMock` resolver; `SheetViewport._begin_isolation` then calls `resolver.resolve_level_context`, which a MagicMock answers with a truthy mock -- if that trips on the section scene, write a local `_export_section` copy whose `SheetViewData` uses `("elevation", "North", ...)` (no isolation path, `paper_space.py:1103`). If `_plot_colours` yields no fills because the pass rasterizes, fall back to the `get_pixmap` sampling of `test_i2_latched_dm_categories_plot_paper_colour_on_full_colour` (`tests/test_hf1_seam_fixes.py:161-178`) asserting white and black hits.

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_section_sheet_plot.py -q`
Expected: FAIL -- `ImportError: cannot import name 'TOKEN_BG'`.

- [ ] **Step 3: Implement**

`firepro3d/constants.py`, after `TOKEN_ACCENT`:

```python
TOKEN_BG = "token:bg"            # theme canvas bg on canvas, white on paper (internal; 600)
```

`firepro3d/colour_tokens.py`: add `TOKEN_BG` to the constants import; in `resolve_colour` make the token branch

```python
    else:
        if value == TOKEN_BG:
            mode = _paper_mode(item)
            c = QColor(_th.detect().canvas_bg) if mode is None else QColor("#ffffff")
        else:
            if value not in _LABELS and value not in _warned:
                _warned.add(value)
                _log.warning("unknown colour token %r drawn as Automatic", value)
            mode = _paper_mode(item)
            if mode is None:
                t = _th.detect()
                c = QColor(t.accent if value == TOKEN_ACCENT else t.ink)
            elif value == TOKEN_ACCENT and mode is _pd.PaperColorMode.FULL_COLOR:
                c = QColor(_th.LIGHT.accent)
            else:
                c = QColor(_PAPER_INK)
```

(`token_label(TOKEN_BG)` stays `None`: the token is internal and never offered in a picker.)

`firepro3d/section_scene.py`:
- import `TOKEN_AUTO, TOKEN_BG` from `.constants` (next to `DEFAULT_LEVEL`).
- `_project_openings`: delete the `bg_brush` / `void_color` lines; replace `void_rect.setBrush(QBrush(void_color))` with `void_rect.set_colour_src(brush=TOKEN_BG)`; `frame_rect = QGraphicsRectItem(...)` -> `frame_rect = _SrcRect(...)` and add `frame_rect.set_colour_src(pen=TOKEN_AUTO)` after its `setBrush(NoBrush)`; `sill_line` / `mid_line` -> `_SrcLine(...)` each followed by `.set_colour_src(pen=TOKEN_AUTO)`. Keep `frame_pen = QPen(self._edge_color, 1)` + cosmetic: the source resolution keeps the pen's width and style.
- `_project_floor_slabs`: delete `_t = th.detect()` / `bg = QColor(_t.canvas_bg)`; `mask = QGraphicsRectItem(...)` -> `mask = _SrcRect(...)`; `mask.setBrush(QBrush(bg))` -> `mask.set_colour_src(brush=TOKEN_BG)`.
- `_apply_theme_colours`: keep `_edge_color` (the HF1 guard `tests/test_hf1_seam_fixes.py:95` reads it) with a comment that edges paint `TOKEN_AUTO` and the attribute is a legacy canvas readout.

- [ ] **Step 4: Run**

Run: `... -m pytest tests/test_section_sheet_plot.py tests/test_hf1_seam_fixes.py tests/test_opening_render.py tests/test_floor_elevation_projection.py <net> -q`
Expected: green. RED proof: revert `void_rect.set_colour_src(brush=TOKEN_BG)` to `void_rect.setBrush(self.backgroundBrush())` -> both section_sheet_plot void tests fail; restore.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/constants.py firepro3d/colour_tokens.py firepro3d/section_scene.py tests/test_section_sheet_plot.py
git commit -F <message file>   # "fix(section): edges, opening voids and slab masks resolve per paint -- token:bg (600, S2)"
```

**G2 review (Tasks 5-7):** spec reviewer checks the s5 table row by row and s5.1; quality reviewer reads the retired `_edge_color` / `backgroundBrush` / `QColor(canvas_bg)` sites against the new sources and walks s13's Edge Cases (collinear wall, pipe along the cut, empty section).

---

# G3 -- marker visuals, grips, flip, menu, placement tool, undo (FP6 group)

### Task 8: `SectionMarker` paint, shape, grips (`FlipGripHandle`), double-click, context menu, properties; retire `ViewMarkerArrow` / `SharedCropBox` / `ViewMarkerManager`

**Files:**
- Modify: `firepro3d/section_marker.py` (replace the paint/geometry stubs; delete the three old classes), `firepro3d/manip_handle.py` (add `FlipGripHandle`), `tests/test_manip_griphandle_viewmarker_parity.py` (rewrite against `SectionMarker`), `tests/test_paper_marker_exclusion.py` (rewrite: cardinal excluded, placed not)
- Test: `tests/test_section_marker.py` (add)

A marker needs a manager for `Open` / `Rename` / `Delete` to do anything; this task gives the marker the hooks (`_manager.open_section(name)`, `rename_section`, `delete_section`, `on_marker_geometry_changed`) and the tests use a tiny stub; Task 11 supplies the real `SectionManager`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_section_marker.py`)

```python
class _Mgr:
    """Stub of the SectionManager surface the marker calls."""
    def __init__(self):
        self.calls = []
    def open_section(self, name): self.calls.append(("open", name))
    def rename_section(self, old, new): self.calls.append(("rename", old, new))
    def delete_section(self, name): self.calls.append(("delete", name))
    def on_marker_geometry_changed(self, marker): self.calls.append(("geom", marker.name))


def _plan_with_marker(cardinal=None):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    if cardinal:
        m = SectionMarker.cardinal(cardinal, QRectF(-5000.0, -5000.0, 10000.0, 10000.0))
    else:
        m = SectionMarker("Section 1", QPointF(0.0, 0.0), QPointF(6000.0, 0.0), 1, 3000.0)
    m._manager = _Mgr()
    ms.addItem(m)
    return ms, m


def test_grip_points_and_apply_grip_endpoints_pivot_and_box_follows(qapp):
    ms, m = _plan_with_marker()
    pts = m.grip_points()
    assert len(pts) == 4
    assert pts[0] == QPointF(0.0, 0.0) and pts[1] == QPointF(6000.0, 0.0)
    assert pts[2] == QPointF(3000.0, -3000.0)          # far-edge midpoint (look side = scene-up)
    m.apply_grip(1, QPointF(6000.0, 3000.0))           # B moves; A stays; depth unchanged
    assert m.cut_a == QPointF(0.0, 0.0) and m.cut_b == QPointF(6000.0, 3000.0)
    assert m.depth_mm == 3000.0
    assert ("geom", "Section 1") in m._manager.calls


def test_depth_grip_is_constrained_along_normal(qapp):
    ms, m = _plan_with_marker()
    m.apply_grip(2, QPointF(4500.0, -5000.0))          # off-axis drag: only the normal component counts
    assert m.depth_mm == pytest.approx(5000.0)
    assert m.cut_a == QPointF(0.0, 0.0) and m.cut_b == QPointF(6000.0, 0.0)
    m.apply_grip(2, QPointF(4500.0, 2000.0))           # dragged through the cut line: clamped to the minimum
    assert m.depth_mm == pytest.approx(100.0)


def test_flip_grip_toggles_look_sign_one_undo_step(qapp):
    from firepro3d.manip_handle import FlipGripHandle
    ms, m = _plan_with_marker()
    handles = m.manip_handles()
    flip = [h for h in handles if isinstance(h, FlipGripHandle)]
    assert len(flip) == 1 and flip[0].index == 3
    pushes = []
    class _M:                                            # minimal manipulator surface
        _moved = False
        def scene(self): return ms
        def _end_drag(self): pass
        _commit_hook = staticmethod(lambda mode: pushes.append(mode))
    flip[0].on_press(_M())
    flip[0].on_release(_M(), QPointF(0.0, 0.0), 0)
    assert m.look_sign == -1 and pushes == ["grip"]
    assert m.grip_points()[2] == QPointF(3000.0, 3000.0)   # far edge now on the other side


def test_cardinal_grip_clears_auto_extent(qapp):
    ms, m = _plan_with_marker("north")
    assert m.auto_extent
    m.apply_grip(2, m.grip_points()[2] + QPointF(0.0, 500.0))
    assert m.auto_extent is False


def test_manip_translate_moves_line_and_box(qapp):
    ms, m = _plan_with_marker()
    m.manip_translate(100.0, -50.0)
    assert m.cut_a == QPointF(100.0, -50.0) and m.cut_b == QPointF(6100.0, -50.0)
    assert m.manip_bounds() == m.box_polygon().boundingRect()


def test_double_click_emits_open_view_requested(qapp):
    from PyQt6.QtWidgets import QGraphicsSceneMouseEvent
    from PyQt6.QtCore import QEvent
    got = []
    ms, m = _plan_with_marker()
    ms.openViewRequested.connect(lambda t, n: got.append((t, n)))
    ev = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseDoubleClick)
    m.mouseDoubleClickEvent(ev)
    assert got == [("section", "Section 1")]
    ms2, c = _plan_with_marker("north")
    ms2.openViewRequested.connect(lambda t, n: got.append((t, n)))
    c.mouseDoubleClickEvent(ev)
    assert got[-1] == ("elevation", "north")


def test_cardinal_menu_disables_rename_delete(qapp):
    ms, m = _plan_with_marker("north")
    menu = m.build_context_menu()
    acts = {a.text(): a for a in menu.actions()}
    assert set(acts) == {"Open", "Rename", "Flip", "Delete"}
    assert not acts["Rename"].isEnabled() and not acts["Delete"].isEnabled()
    assert acts["Open"].isEnabled() and acts["Flip"].isEnabled()
    ms2, p = _plan_with_marker()
    acts2 = {a.text(): a for a in p.build_context_menu().actions()}
    assert all(a.isEnabled() for a in acts2.values())
    acts2["Delete"].trigger()
    assert ("delete", "Section 1") in p._manager.calls
    acts2["Open"].trigger()
    assert ("open", "Section 1") in p._manager.calls


def test_marker_visible_on_every_level(qapp):
    from firepro3d.level_manager import LevelManager
    ms, m = _plan_with_marker()
    lm = LevelManager(); lm.add_level("Level 2", 3500.0)
    ms._level_manager = lm
    lm.apply_to_scene(ms, active_level="Level 2")
    assert m.isVisible()
    lm.apply_to_scene(ms, active_level="Level 1")
    assert m.isVisible()


def test_marker_shape_covers_line_bubbles_and_box_edge_only_when_selected(qapp):
    ms, m = _plan_with_marker()
    assert m.shape().contains(QPointF(3000.0, 0.0))          # on the cut line
    assert not m.shape().contains(QPointF(3000.0, -1500.0))  # inside the box, unselected: not hittable
    m.setSelected(True)
    assert m.shape().contains(QPointF(3000.0, -3000.0))      # far edge, selected


def test_get_properties_and_set_property(qapp):
    ms, m = _plan_with_marker()
    props = m.get_properties()
    assert props["Name"]["value"] == "Section 1"
    assert props["Cardinal"]["readonly"] is True and props["Cardinal"]["value"] == "-"
    assert props["Flip"]["type"] == "bool" and props["Flip"]["value"] is False
    m.set_property("Depth", "4500")
    assert m.depth_mm == pytest.approx(4500.0)
    m.set_property("Flip", True)
    assert m.look_sign == -1
    m.set_property("Name", "Stair")
    assert ("rename", "Section 1", "Stair") in m._manager.calls
```

Grep `LevelManager.add_level` and the property-panel `bool` type name (`grep -rn '"type": "bool"' firepro3d/` -- use the exact string the panel renders as a toggle; if the panel's name differs, use that one in both the code and the test).

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_section_marker.py -q`
Expected: the Task 3 tests pass; the new ones FAIL (`grip_points` missing, `FlipGripHandle` import error, ...).

- [ ] **Step 3: `FlipGripHandle` in `firepro3d/manip_handle.py`**

After `GridlineGripHandle`:

```python
class FlipGripHandle(GripHandle):
    """A click-only grip: the press/release toggles the item (``item.flip()``)
    and commits one undo step itself, because the manipulator's commit hook
    only runs for a *moved* drag (``GripHandle.on_release``). No drag
    semantics: a drag is ignored, Esc does nothing. Used by SectionMarker
    (index 3) to toggle ``look_sign`` (spec s6).
    """

    def __init__(self, item, index: int):
        super().__init__(item, index, circular=True)

    def cursor(self, m):
        return QCursor(Qt.CursorShape.PointingHandCursor)

    def on_press(self, m) -> None:
        self._snapshot = list(self.item.grip_points())

    def on_drag(self, m, scene_pos, mods) -> None:
        pass                                   # click-only

    def on_release(self, m, scene_pos, mods) -> None:
        self.item.flip()
        m._end_drag()
        hook = getattr(m, "_commit_hook", None)
        if hook is not None:
            hook("grip")

    def on_cancel(self, m) -> None:
        pass
```

- [ ] **Step 4: `SectionMarker` visuals, grips, menu, properties** (replace the Task 3 `boundingRect` / `paint` stubs; delete `SharedCropBox`, `ViewMarkerArrow`, `ViewMarkerManager` and the module docstring's shared-rectangle paragraph)

```python
    # -- geometry helpers ------------------------------------------------------
    _R = BUBBLE_RADIUS_MM * 3.0                              # bubble radius (old marker circle)
    _HEAD = BUBBLE_RADIUS_MM * 3.0 / math.sin(math.radians(40))   # arrow-head reach (old _POINT_DIST)

    def _unit(self):
        dx, dy = self._b.x() - self._a.x(), self._b.y() - self._a.y()
        L = math.hypot(dx, dy) or 1.0
        return dx / L, dy / L, L

    def _head_polygon(self, tip: QPointF, direction: tuple[float, float]) -> QPolygonF:
        """The old ViewMarkerArrow wedge: tangent points at +/-40 deg around *direction*."""
        R, D = self._R, self._HEAD
        base = math.atan2(direction[1], direction[0])
        alpha = math.acos(min(R / D, 1.0))
        t1 = QPointF(tip.x() - D * math.cos(base) + R * math.cos(base + alpha),
                     tip.y() - D * math.sin(base) + R * math.sin(base + alpha))
        t2 = QPointF(tip.x() - D * math.cos(base) + R * math.cos(base - alpha),
                     tip.y() - D * math.sin(base) + R * math.sin(base - alpha))
        return QPolygonF([t1, tip, t2])

    def _bubble_centres(self):
        ux, uy, _L = self._unit()
        off = self._R * 1.5
        return (QPointF(self._a.x() - ux * off, self._a.y() - uy * off),
                QPointF(self._b.x() + ux * off, self._b.y() + uy * off))

    def boundingRect(self) -> QRectF:
        r = self.box_polygon().boundingRect()
        for c in self._bubble_centres():
            r = r.united(QRectF(c.x() - self._R, c.y() - self._R, 2 * self._R, 2 * self._R))
        m = self._HEAD + self._R
        return r.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        """Hittable: cut line (stroked), the two bubbles, the arrow heads; the
        box edges only while selected (the interior is never hittable)."""
        path = QPainterPath()
        line = QPainterPath(self._a); line.lineTo(self._b)
        stroker = QPainterPathStroker(); stroker.setWidth(max(20.0, self._R * 0.5))
        path.addPath(stroker.createStroke(line))
        for c in self._bubble_centres():
            path.addEllipse(c, self._R, self._R)
        nx, ny = self.normal_scene()
        for end in (self._a, self._b):
            path.addPolygon(self._head_polygon(QPointF(end.x() + nx * self._HEAD, end.y() + ny * self._HEAD), (nx, ny)))
        if self.isSelected():
            box = QPainterPath(); box.addPolygon(self.box_polygon()); box.closeSubpath()
            edge = QPainterPathStroker(); edge.setWidth(max(20.0, self._R * 0.5))
            path.addPath(edge.createStroke(box))
        return path

    def paint(self, painter: QPainter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        col, fill = self._marker_color, self._fill_color
        pen_w = max(1.0, self._R * 0.04)
        # Cut line: solid, cosmetic.
        line_pen = QPen(col, 1); line_pen.setCosmetic(True)
        painter.setPen(line_pen)
        painter.drawLine(self._a, self._b)
        # Arrow heads at A and B pointing to the look side (D6: carried over).
        nx, ny = self.normal_scene()
        painter.setPen(QPen(col, pen_w)); painter.setBrush(QBrush(col))
        for end in (self._a, self._b):
            tip = QPointF(end.x() + nx * self._HEAD, end.y() + ny * self._HEAD)
            painter.drawPolygon(self._head_polygon(tip, (nx, ny)))
        # Bubbles with the name (cardinal letter for cardinals) at both ends.
        label = self._cardinal[0].upper() if self._cardinal else (self._name.split()[-1] if self._name.split() else "?")
        font = QFont("Consolas"); font.setBold(True)
        fs = self._display_font_size if self._display_font_size else 10
        font.setPixelSize(max(1, int(self._R * (fs / 10.0) * (1.0 if len(label) <= 1 else 0.7))))
        painter.setFont(font)
        for c in self._bubble_centres():
            painter.setPen(QPen(col, pen_w)); painter.setBrush(QBrush(fill))
            painter.drawEllipse(c, self._R, self._R)
            painter.setPen(QPen(col.lighter(150)))
            painter.drawText(QRectF(c.x() - self._R, c.y() - self._R, 2 * self._R, 2 * self._R),
                             Qt.AlignmentFlag.AlignCenter, label)
        if self.isSelected():
            # Crop box: SharedCropBox's dashed look, only while selected (s6).
            box_pen = QPen(col, 1, Qt.PenStyle.DashLine); box_pen.setCosmetic(True)
            painter.setPen(box_pen)
            faint = QColor(col); faint.setAlpha(15)
            painter.setBrush(QBrush(faint))
            painter.drawPolygon(self.box_polygon())
            hl = QPen(col.lighter(150), max(1.0, self._R * 0.08)); hl.setCosmetic(False)
            painter.setPen(hl); painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(self._a, self._b)

    # -- grip protocol (DetailMarker pattern) ---------------------------------------
    def grip_points(self) -> list[QPointF]:
        nx, ny = self.normal_scene()
        mid = QPointF((self._a.x() + self._b.x()) / 2.0, (self._a.y() + self._b.y()) / 2.0)
        far_mid = QPointF(mid.x() + nx * self._depth, mid.y() + ny * self._depth)
        flip = QPointF(mid.x() + nx * self._R * 1.5, mid.y() + ny * self._R * 1.5)
        return [QPointF(self._a), QPointF(self._b), far_mid, flip]

    def apply_grip(self, index: int, new_pos: QPointF):
        if index == 0:
            if math.hypot(new_pos.x() - self._b.x(), new_pos.y() - self._b.y()) < MIN_CUT_LEN:
                return
            self.set_geometry(new_pos, self._b, self._depth)
        elif index == 1:
            if math.hypot(new_pos.x() - self._a.x(), new_pos.y() - self._a.y()) < MIN_CUT_LEN:
                return
            self.set_geometry(self._a, new_pos, self._depth)
        elif index == 2:
            nx, ny = self.normal_scene()
            depth = (new_pos.x() - self._a.x()) * nx + (new_pos.y() - self._a.y()) * ny
            self.set_geometry(self._a, self._b, max(MIN_CUT_LEN, depth))
        # index 3 (flip) is click-only: FlipGripHandle.on_release calls flip().

    def manip_bounds(self) -> QRectF:
        return self.box_polygon().boundingRect()

    def manip_handles(self):
        from .manip_handle import EndpointGripHandle, GripHandle, FlipGripHandle
        return [EndpointGripHandle(self, 0, opposite_index=1),
                EndpointGripHandle(self, 1, opposite_index=0),
                GripHandle(self, 2, circular=False),
                FlipGripHandle(self, 3)]

    def manip_translate(self, dx: float, dy: float):
        self.set_geometry(QPointF(self._a.x() + dx, self._a.y() + dy),
                          QPointF(self._b.x() + dx, self._b.y() + dy), self._depth)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.prepareGeometryChange()          # shape() grows / shrinks with selection
            self.update()
        return super().itemChange(change, value)

    # -- interaction -----------------------------------------------------------------
    def mouseDoubleClickEvent(self, event):
        sc = self.scene()
        if sc is not None and hasattr(sc, "openViewRequested"):
            sc.openViewRequested.emit(self.view_type, self.view_name)
        event.accept()

    def build_context_menu(self):
        """Open - Rename - Flip - Delete (s6); Rename / Delete disabled on cardinals (D5b, D8)."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu()
        mgr = self._manager
        act_open = menu.addAction("Open")
        act_open.triggered.connect(lambda: mgr is not None and mgr.open_section(self.view_name))
        act_rename = menu.addAction("Rename")
        act_rename.triggered.connect(self._prompt_rename)
        act_flip = menu.addAction("Flip")
        act_flip.triggered.connect(self._flip_with_undo)
        act_delete = menu.addAction("Delete")
        act_delete.triggered.connect(lambda: mgr is not None and mgr.delete_section(self._name))
        if self._cardinal:
            act_rename.setEnabled(False)
            act_delete.setEnabled(False)
        return menu

    def contextMenuEvent(self, event):
        self.build_context_menu().exec(event.screenPos())
        event.accept()

    def _push_undo(self):
        sc = self.scene()
        push = getattr(sc, "push_undo_state", None)
        if push is not None:
            push()

    def _flip_with_undo(self):
        self.flip()
        self._push_undo()                         # s8: menu Flip is one undo step

    def _prompt_rename(self):
        from PyQt6.QtWidgets import QInputDialog
        new, ok = QInputDialog.getText(None, "Rename Section", "Name:", text=self._name)
        if ok and new and new != self._name and self._manager is not None:
            self._manager.rename_section(self._name, new)

    # -- property panel (DetailMarker pattern) -------------------------------------------
    def _fmt(self, mm: float) -> str:
        sc = self.scene()
        sm = getattr(sc, "scale_manager", None) if sc else None
        return sm.format_length(mm) if sm else f"{mm:.1f} mm"

    def get_properties(self) -> dict:
        return {
            "Name": {"value": self._name, "type": "string", "readonly": bool(self._cardinal)},
            "Depth": {"value": self._fmt(self._depth), "type": "string"},
            "Flip": {"value": self._look < 0, "type": "bool"},
            "Cardinal": {"value": self._cardinal.title() if self._cardinal else "-",
                         "type": "string", "readonly": True},
        }

    def set_property(self, key: str, value):
        if key == "Name" and not self._cardinal:
            new = str(value)
            if new and new != self._name and self._manager is not None:
                self._manager.rename_section(self._name, new)
        elif key == "Depth":
            sc = self.scene()
            sm = getattr(sc, "scale_manager", None) if sc else None
            parsed = float(str(value).split()[0])      # mm; the units spec owns a display-unit parser if one exists
            if parsed is not None and parsed >= MIN_CUT_LEN:
                self.set_geometry(self._a, self._b, float(parsed))
                self._push_undo()
        elif key == "Flip":
            if bool(value) != (self._look < 0):
                self._flip_with_undo()
```

Imports to add at the module top (grep the header first): `QPainterPath`, `QPainterPathStroker`, `QStyle`, `QPainter`, `QFont` (most are already imported by the old header). `ScaleManager` has no length parser at plan time (`parse_angle` / `parse_span` / `parse_factor` only, verified); Depth is parsed as mm and formatted with `format_length` -- a display-unit parser is a follow-up under the units spec.

Rename the module docstring to describe `SectionMarker` + `SectionBasis`.

- [ ] **Step 5: Rewrite the two coupled marker test files**

`tests/test_manip_griphandle_viewmarker_parity.py` (11 tests on `ViewMarkerArrow` + `SharedCropBox` grips): the contract it guarded -- legacy grip path == manipulator path on the shared box -- is retired with the box. Rewrite to **four** tests on `SectionMarker` under the real manipulator: `default` handles count == 4 with the right classes; a live `EndpointGripHandle` drag of grip 1 through `SelectionManipulator` (press / move / release on a shown `Model_View`) moves B and pushes exactly one undo state; a `FlipGripHandle` click through the view toggles `look_sign` with one undo push; Esc mid-drag restores B. Reuse the file's existing view / event helpers.

`tests/test_paper_marker_exclusion.py` (6 tests): replace every `ViewMarkerArrow` / `SharedCropBox` construction with `SectionMarker.cardinal(...)` (excluded) and a placed `SectionMarker(...)` (NOT excluded -- assert it is in the paper render set), keeping the file's `DetailMarker` cases unchanged.

- [ ] **Step 6: Run**

Run: `... -m pytest tests/test_section_marker.py tests/test_manip_griphandle_viewmarker_parity.py tests/test_paper_marker_exclusion.py tests/test_detail_marker_crop.py tests/test_manip_*.py -q` (Bash for the glob)
Expected: green. RED proofs: (1) comment out the two `setEnabled(False)` lines -> `test_cardinal_menu_disables_rename_delete` fails; (2) in `FlipGripHandle.on_release` drop the `hook("grip")` call -> `test_flip_grip_toggles_look_sign_one_undo_step` fails on `pushes`; restore both.

- [ ] **Step 7: Retired-name grep + commit**

`grep -rn "ViewMarkerArrow\|SharedCropBox\|ViewMarkerManager" --include=*.py . docs/gen_ref_pages.py` -> only `main.py:1438-1443` (`_create_elevation_markers`, replaced in Task 11) and `display_manager.py` / `paper_display.py` class-name strings (Task 11). Record the hits in the commit message body.

```bash
git add firepro3d/section_marker.py firepro3d/manip_handle.py tests/test_section_marker.py tests/test_manip_griphandle_viewmarker_parity.py tests/test_paper_marker_exclusion.py
git commit -F <message file>   # "feat(section): SectionMarker visuals, 4 grips incl. FlipGripHandle, context menu, properties; retire ViewMarkerArrow/SharedCropBox (S3)"
```

### Task 9: Two-click "Section" placement tool in `Model_Space`

**Files:**
- Modify: `firepro3d/model_space.py` (`__init__` state, `set_mode` teardown + instruction, `_SINGLE_PLACEMENT_MODES`, `_PRESS_DISPATCH`, `_MOVE_DISPATCH`, new `_press_section` / `_move_section`)
- Test: `tests/test_section_placement.py` (new)

The tool needs `scene._section_manager.place_section(a, b)` (Task 11). Until then the tests use the `_Mgr`-style stub below with a `place_section` that records and returns a marker.

- [ ] **Step 1: Write the failing tests**

```python
"""Two-click Section tool (spec s9, D5): click A, dashed preview with a look-side
hint, click B -> place_section(A, B); < 100 mm rejected; Esc cancels."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsLineItem

from firepro3d.section_marker import SectionMarker


class _PlaceMgr:
    def __init__(self):
        self.placed = []
    def place_section(self, a, b):
        m = SectionMarker(f"Section {len(self.placed) + 1}", a, b)
        self.placed.append(m)
        return m
    def open_section(self, name): pass
    def on_marker_geometry_changed(self, marker): pass


@pytest.fixture
def plan(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.model_view import Model_View
    ms = Model_Space()
    ms._section_manager = _PlaceMgr()
    view = Model_View(ms)
    view.resize(800, 600); view.show()
    QTest.qWaitForWindowExposed(view)
    view.centerOn(0, 0)
    yield ms, view
    view.close()


def _click(view, ms, x, y):
    vp = view.mapFromScene(QPointF(x, y))
    QTest.mouseMove(view.viewport(), vp)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, vp)


def test_two_clicks_place_section_1_then_2(plan):
    ms, view = plan
    ms._snap_enabled = False
    ms.set_mode("section")
    _click(view, ms, -1000.0, 0.0)
    assert ms.mode == "section" and ms._section_anchor is not None
    assert isinstance(ms._section_preview, QGraphicsLineItem)
    _click(view, ms, 1000.0, 0.0)
    mgr = ms._section_manager
    assert [m.name for m in mgr.placed] == ["Section 1"]
    a, b = mgr.placed[0].cut_a, mgr.placed[0].cut_b
    assert abs(a.x() + 1000.0) < 2.0 and abs(b.x() - 1000.0) < 2.0     # view px rounding
    assert ms.mode == "select" and ms._section_preview is None
    assert len(ms._undo_stack) >= 1
    ms.set_mode("section")
    _click(view, ms, -1000.0, 500.0); _click(view, ms, 1000.0, 500.0)
    assert [m.name for m in mgr.placed] == ["Section 1", "Section 2"]


def test_sub_100mm_cut_is_rejected_with_status(plan):
    ms, view = plan
    ms._snap_enabled = False
    msgs = []
    ms._show_status = lambda message, timeout=5000: msgs.append(message)   # status bar seam (model_space.py:939)
    ms.set_mode("section")
    _click(view, ms, 0.0, 0.0)
    _click(view, ms, 0.5, 0.0)
    assert ms._section_manager.placed == []
    assert ms.mode == "section" and ms._section_anchor is not None      # still waiting for B
    assert any("100" in m for m in msgs)


def test_escape_cancels_and_removes_preview(plan):
    ms, view = plan
    ms.set_mode("section")
    _click(view, ms, 0.0, 0.0)
    assert ms._section_preview is not None
    QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
    assert ms.mode == "select" and ms._section_anchor is None and ms._section_preview is None
    assert ms._section_manager.placed == []
```

Verified at plan time: status text goes through `Model_Space._show_status(message, timeout)` (`model_space.py:939`, writes the window's status bar -- the test replaces it on the instance). Confirm how Esc leaves a placement mode (`keyPressEvent` ~8133 -> `set_mode("select")`) before writing the Esc assertion.

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_section_placement.py -q`
Expected: FAIL -- `set_mode("section")` is refused / `_section_anchor` missing.

- [ ] **Step 3: Implement** (`firepro3d/model_space.py`)

(a) `__init__` beside the detail state (~line 603):

```python
        # Section placement (spec s9)
        self._section_anchor: "QPointF | None" = None
        self._section_preview: "QGraphicsLineItem | None" = None
        self._section_manager = None  # set by main.py
```

(b) `set_mode` teardown, after the `if mode != "detail":` block:

```python
        if mode != "section":
            self._section_anchor = None
            if self._section_preview is not None:
                if self._section_preview.scene() is self:
                    self.removeItem(self._section_preview)
                self._section_preview = None
```

(c) `_initial_steps` (~1569): `"section": "Pick the section's start point",`.

(d) Registries: `"section"` into `_SINGLE_PLACEMENT_MODES`; `"section": "_press_section"` into `_PRESS_DISPATCH` after the `"detail"` row; `"section": "_move_section"` into `_MOVE_DISPATCH` after `"detail"`.

(e) Handlers, after `_move_detail`:

```python
    # -- Section placement (spec s9) -------------------------------------------------

    def _press_section(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._section_anchor is None:
            self._section_anchor = QPointF(snapped)
            self.instructionChanged.emit("Pick the section's end point  (Esc to cancel)")
            preview = QGraphicsLineItem(QLineF(snapped, snapped))
            pen = QPen(QColor("#4488cc"), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview.setPen(pen)
            preview.setZValue(200)
            self.addItem(preview)
            self._section_preview = preview
            return
        a, b = self._section_anchor, QPointF(snapped)
        from .section_marker import MIN_CUT_LEN
        if QLineF(a, b).length() < MIN_CUT_LEN:
            self._show_status(f"Section too short: the cut line must be at least {MIN_CUT_LEN:.0f} mm")
            return
        if self._section_preview is not None:
            self.removeItem(self._section_preview)
            self._section_preview = None
        self._section_anchor = None
        mgr = self._section_manager
        if mgr is not None:
            marker = mgr.place_section(a, b)
            mgr.open_section(marker.view_name)
        self.push_undo_state()
        self.set_mode("select")

    def _move_section(self, event, snapped):
        if self._section_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._section_anchor is not None and self._section_preview is not None:
            a = self._section_anchor
            self._section_preview.setLine(QLineF(a, snapped))
            # Look-side hint: a short tick from the midpoint toward the look side (+1 = (D.y, -D.x)).
            ln = QLineF(a, snapped)
            if ln.length() > 1e-6:
                ux, uy = ln.dx() / ln.length(), ln.dy() / ln.length()
                mid = ln.center()
                hint = QLineF(mid, QPointF(mid.x() + uy * 600.0, mid.y() - ux * 600.0))
                self._draw_dim_hint = (f"L: {self.scale_manager.scene_to_display(ln.length())}  "
                                       f"look side: {'left' if hint.dy() < 0 else 'right'} of A->B")
```

Grep `QLineF` / `QGraphicsLineItem` in the module's imports (VC4) and add what is missing.

- [ ] **Step 4: Run**

Run: `... -m pytest tests/test_section_placement.py tests/test_detail_marker_crop.py -q` plus the mode-registry tests found by `grep -rln "_PRESS_DISPATCH\|_SINGLE_PLACEMENT_MODES\|_MOVE_DISPATCH" tests/` (VC5).
Expected: green. RED proof: change `< MIN_CUT_LEN` to `< 0.0` -> `test_sub_100mm_cut_is_rejected_with_status` fails; restore.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/model_space.py tests/test_section_placement.py
git commit -F <message file>   # "feat(section): two-click Section placement tool in Model_Space (s9, D5)"
```

### Task 10: Undo -- `"sections"` in the network snapshot; place / grip / flip / delete each undoable

**Files:**
- Modify: `firepro3d/model_space.py` (`_capture_network`, `_restore_network`)
- Test: `tests/test_section_undo.py` (new)

The snapshot talks to `self._section_manager` through `to_list()` / `restore_from_list(data)`; this task defines the stub contract the real `SectionManager` (Task 11) implements: `to_list() -> list[dict]`, `restore_from_list(data)` (diff by name: update survivors' geometry, remove deleted, re-add missing; open tabs untouched).

- [ ] **Step 1: Write the failing tests**

```python
"""Acceptance (e): marker place / grip move / flip / delete are undoable through
Model_Space.undo(); an open section tab is left alone (spec s8)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.section_marker import SectionMarker


class _UndoMgr:
    """Stub implementing the snapshot contract the real manager will carry."""
    def __init__(self, ms):
        self.ms = ms
        self.markers = {}
        self.closed = []
    def place_section(self, a, b):
        m = SectionMarker(f"Section {len(self.markers) + 1}", a, b)
        self.markers[m.name] = m; m._manager = self; self.ms.addItem(m)
        return m
    def open_section(self, name): pass
    def on_marker_geometry_changed(self, marker): pass
    def delete_section(self, name):
        m = self.markers.pop(name); self.ms.removeItem(m); self.closed.append(name)
    def to_list(self):
        return [m.to_dict() for m in self.markers.values()]
    def restore_from_list(self, data):
        want = {d["name"]: d for d in data}
        for name in list(self.markers):
            if name not in want:
                self.delete_section(name)
        for name, d in want.items():
            if name in self.markers:
                m = self.markers[name]
                m.set_geometry(QPointF(*d["cut_a"]), QPointF(*d["cut_b"]), d["depth_mm"], user=False)
                if m.look_sign != d["look_sign"]:
                    m.flip()
            else:
                m = SectionMarker.from_dict(d); m._manager = self
                self.markers[name] = m; self.ms.addItem(m)


@pytest.fixture
def ms(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    s._section_manager = _UndoMgr(s)
    s.push_undo_state()                      # baseline
    return s


def test_place_is_undoable(ms):
    mgr = ms._section_manager
    mgr.place_section(QPointF(0, 0), QPointF(5000, 0)); ms.push_undo_state()
    assert "Section 1" in mgr.markers
    ms.undo()
    assert mgr.markers == {}
    ms.redo()
    assert "Section 1" in mgr.markers


def test_grip_move_is_undoable(ms):
    mgr = ms._section_manager
    m = mgr.place_section(QPointF(0, 0), QPointF(5000, 0)); ms.push_undo_state()
    m.apply_grip(1, QPointF(5000, 2000)); ms.push_undo_state()     # what the manipulator commit does
    ms.undo()
    assert mgr.markers["Section 1"].cut_b == QPointF(5000, 0)


def test_flip_is_undoable(ms):
    mgr = ms._section_manager
    m = mgr.place_section(QPointF(0, 0), QPointF(5000, 0)); ms.push_undo_state()
    m._flip_with_undo()
    assert mgr.markers["Section 1"].look_sign == -1
    ms.undo()
    assert mgr.markers["Section 1"].look_sign == 1


def test_delete_is_undoable_and_survivor_identity_kept(ms):
    mgr = ms._section_manager
    keep = mgr.place_section(QPointF(0, 0), QPointF(5000, 0))
    mgr.place_section(QPointF(0, 1000), QPointF(5000, 1000)); ms.push_undo_state()
    mgr.delete_section("Section 2"); ms.push_undo_state()
    ms.undo()
    assert set(mgr.markers) == {"Section 1", "Section 2"}
    assert mgr.markers["Section 1"] is keep                      # survivor updated in place, not rebuilt


def test_snapshot_without_manager_has_no_sections_key(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    assert "sections" not in s._capture_network()
```

Grep `Model_Space.undo` / `redo` names (VC4).

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_section_undo.py -q`
Expected: `test_place_is_undoable` etc. FAIL (the snapshot has no sections, so undo leaves the marker); `test_snapshot_without_manager_has_no_sections_key` passes already.

- [ ] **Step 3: Implement**

`_capture_network`: before the `return {` add

```python
        sec_mgr = getattr(self, "_section_manager", None)
        extra = {}
        if sec_mgr is not None and hasattr(sec_mgr, "to_list"):
            extra["sections"] = sec_mgr.to_list()         # spec s8: markers join the snapshot
```

and end the literal with `**extra,` as its last entry (after `"block_capability": ...`).

`_restore_network`: inside the `try:` after the last list rebuild (after rooms / blocks / constraints are restored -- find the final `self._rooms` rebuild and the `constraint_ctl.restore` call; insert after them, still inside the `try`):

```python
            sec_mgr = getattr(self, "_section_manager", None)
            if sec_mgr is not None and "sections" in state and hasattr(sec_mgr, "restore_from_list"):
                sec_mgr.restore_from_list(state["sections"])
```

A snapshot from before this change (no `"sections"` key) leaves the markers alone.

- [ ] **Step 4: Run**

Run: `... -m pytest tests/test_section_undo.py tests/test_undo*.py -q` (Bash glob; plus any file `grep -rln "_capture_network\|_restore_network" tests/` lists).
Expected: green. RED proof: drop the `extra["sections"] = ...` line -> four tests fail; restore.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/model_space.py tests/test_section_undo.py
git commit -F <message file>   # "feat(section): section markers join the undo snapshot -- place / grip / flip / delete undoable (s8, acceptance e)"
```

**G3 review (Tasks 8-10):** spec reviewer walks s6 (every field, grip, menu row), s8 undo, s9 placement; quality reviewer reads the OLD `ViewMarkerArrow.paint` / `_tangent_points_and_tip` against `_head_polygon` (D6 carried-over visuals) and s13's coincident / sub-100 mm edge rows.

---

# G4 -- SectionManager, consumers, persistence, sheets (FP6 group)

### Task 11: `SectionManager`; `main.py` wiring; ribbon button; project-browser Sections group; Display Manager label

**Files:**
- Modify: `firepro3d/section_manager.py` (rewrite), `firepro3d/elevation_view.py` (drop the `ElevationView` alias), `main.py`, `firepro3d/project_browser.py`, `firepro3d/display_manager.py`, `firepro3d/paper_display.py`, `docs/gen_ref_pages.py`
- Test: `tests/test_section_manager.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""SectionManager + consumers: seeding, placing, opening, identity (S4), 560
public accessors, D8 label, D5 ribbon button, browser Sections group."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtWidgets import QTabWidget

from firepro3d.section_marker import SectionMarker, CARDINALS


@pytest.fixture
def mgr(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_manager import SectionManager
    ms = Model_Space()
    lm = LevelManager(); ms._level_manager = lm
    sm = ScaleManager(); ms.scale_manager = sm
    tabs = QTabWidget()
    m = SectionManager(ms, lm, sm, tabs)
    ms._section_manager = m
    yield m, ms, tabs
    m.close_all()


def test_seed_cardinals_creates_four_once_and_adds_to_scene(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    assert set(m.markers) == set(CARDINALS)
    assert all(m.markers[c].scene() is ms and m.markers[c].cardinal == c for c in CARDINALS)
    m.seed_cardinals()
    assert len(m.markers) == 4                                   # idempotent


def test_place_section_names_and_depth_seed(mgr):
    m, ms, tabs = mgr
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0.0, -6000.0), QPointF(4000.0, -6000.0))   # building 6 m scene-up of the cut
    ms._walls.append(w); ms.addItem(w)
    s1 = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    s2 = m.place_section(QPointF(0.0, 1000.0), QPointF(5000.0, 1000.0))
    assert (s1.name, s2.name) == ("Section 1", "Section 2")
    assert s1.look_sign == 1 and s1.scene() is ms and not s1.auto_extent
    # depth = max((c - A) . N) over the building bbox corners (N_s = (0, -1) here) = 6000 + wall half-width.
    assert s1.depth_mm == pytest.approx(6000.0 + w.half_thickness_scene(), abs=1.0)
    s3 = m.place_section(QPointF(0.0, -20000.0), QPointF(5000.0, -20000.0))  # look side (scene-up) is empty
    assert s3.name == "Section 3" and s3.depth_mm == 10000.0                 # -> 10 000 mm fallback (s9)


def test_open_section_tab_titles_and_identity(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    v = m.open_section("north")
    assert tabs.tabText(tabs.currentIndex()) == "Elevation: North"
    assert m.get_scene("north").marker is m.markers["north"]
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    m.open_section(s.name)
    assert tabs.tabText(tabs.currentIndex()) == "Section: Section 1"
    assert m.open_names == ["north", "Section 1"]
    assert m.open_section("north") is v and tabs.count() == 2         # re-open switches


def test_cardinal_identity_is_elevation(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    assert m.markers["north"].view_type == "elevation" and m.markers["north"].view_name == "north"
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    assert s.view_type == "section" and s.view_name == "Section 1"


def test_open_scenes_public_and_live_scenes_uses_it(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals(); m.open_section("north")
    assert [sc.marker.name for sc in m.open_scenes] == ["North"]
    import inspect, main as _main
    src = inspect.getsource(_main.MainWindow._live_scenes)
    assert "open_scenes" in src and "._views" not in src              # 560: no private read


def test_get_or_build_scene_without_tab(mgr):
    m, ms, tabs = mgr
    m.seed_cardinals()
    sc = m.get_or_build_scene("south")
    assert sc is not None and tabs.count() == 0 and m.get_scene("south") is None
    assert m.get_or_build_scene("south") is sc                          # cached
    m.open_section("south")
    assert m.get_scene("south") is sc                                   # the tab adopts the built scene


def test_delete_rename_cascade(mgr):
    m, ms, tabs = mgr
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0)); m.open_section("Section 1")
    changed = []
    m.sectionsChanged.connect(lambda: changed.append(1))
    m.rename_section("Section 1", "Stair")
    assert "Stair" in m.markers and "Section 1" not in m.markers
    assert tabs.tabText(0) == "Section: Stair" and m.open_names == ["Stair"]
    m.delete_section("Stair")
    assert tabs.count() == 0 and m.markers == {} and s.scene() is None
    assert len(changed) == 2
    m.seed_cardinals()
    with pytest.raises(ValueError):
        m.delete_section("north")                                       # cardinals permanent (D5b)


def test_marker_grip_rebuilds_open_scene(mgr):
    m, ms, tabs = mgr
    s = m.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0)); m.open_section("Section 1")
    sc = m.get_scene("Section 1")
    sc._rebuild_timer.stop()
    s.apply_grip(2, QPointF(2500.0, -4000.0))
    assert sc._rebuild_timer.isActive()                                 # scheduled by on_marker_geometry_changed


def test_dm_row_label_section_marker_key_unchanged():
    from firepro3d.display_manager import _CATEGORY_MAP, category_label
    assert "Elevation Marker" in _CATEGORY_MAP and "Section Marker" not in _CATEGORY_MAP
    assert category_label("Elevation Marker") == "Section Marker"
    assert category_label("Wall") == "Wall"


def test_dm_and_paper_display_categorise_section_marker(qapp):
    from firepro3d.display_manager import _is_elevation_marker
    from firepro3d.paper_display import _category_for_item
    m = SectionMarker("Section 1", QPointF(0, 0), QPointF(100, 0))
    assert _is_elevation_marker(m) and _category_for_item(m) == "Elevation Marker"


def test_ribbon_section_button_enters_section_mode(qapp):
    from firepro3d.view_3d import View3D  # noqa: F401 -- heavy import before MainWindow (HF1 pattern)
    import main as _main_module
    _main_module.View3D = View3D
    from main import MainWindow
    from tests._mainwindow_helpers import dispose_main_window
    win = MainWindow()
    try:
        btn = win._mode_buttons["section"]
        assert btn.text() == "Section"
        btn.click()
        assert win.scene.mode == "section"
        assert win.section_manager is win.scene._section_manager
        assert set(win.section_manager.markers) == set(CARDINALS)       # seeded at startup
        assert "Sections" in [win.project_browser._sections_root.text(0)]
    finally:
        dispose_main_window(win)
```

Fix the stray line in the first test before running (`m.markers.pop("east")...` is a placeholder -- delete it). Grep the MainWindow test helpers (`grep -rn "def .*main_window" tests/conftest.py tests/test_hf1_seam_fixes.py`) and use the real names.

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest tests/test_section_manager.py -q`
Expected: FAIL on `SectionManager.__init__` signature / `seed_cardinals` missing.

- [ ] **Step 3: Rewrite `firepro3d/section_manager.py`**

```python
"""
section_manager.py
==================
Owns the section markers on the plan and the open section views (tabs).

Cardinals (North/South/East/West) are permanent markers seeded at startup and
keep the ``"elevation"`` identity (spec s7.2); placed sections are
``"section"``. One tab per section; a tab-less scene is built for sheets
(``get_or_build_scene``) and adopted when the tab opens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QPointF
from PyQt6.QtWidgets import QTabWidget

from .section_scene import SectionScene
from .elevation_view import SectionView
from .section_marker import (SectionMarker, CARDINALS, building_bbox,
                             FALLBACK_HALF)

if TYPE_CHECKING:
    from .model_space import Model_Space
    from .level_manager import LevelManager
    from .scale_manager import ScaleManager


class SectionManager(QObject):
    """Markers + views for every section (spec s7.1)."""

    sectionsChanged = pyqtSignal()        # place / rename / delete -> browser refresh

    def __init__(self, model_space: "Model_Space", level_manager: "LevelManager",
                 scale_manager: "ScaleManager", tab_widget: QTabWidget, parent=None):
        super().__init__(parent)
        self._ms = model_space
        self._lm = level_manager
        self._sm = scale_manager
        self._tabs = tab_widget
        self.markers: dict[str, SectionMarker] = {}          # key: view_name
        self._views: dict[str, tuple[SectionScene, SectionView | None]] = {}
        self._counter = 0

    # -- keys -------------------------------------------------------------------------
    @staticmethod
    def _key(name: str) -> str:
        return name.lower() if name.lower() in CARDINALS else name

    def marker(self, name: str) -> SectionMarker | None:
        return self.markers.get(self._key(name))

    # -- markers ----------------------------------------------------------------------
    def _adopt(self, marker: SectionMarker) -> SectionMarker:
        from .display_manager import apply_category_defaults
        marker._manager = self
        self.markers[marker.view_name] = marker
        if marker.scene() is not self._ms:
            self._ms.addItem(marker)
        apply_category_defaults(marker)
        return marker

    def seed_cardinals(self) -> None:
        """Create any missing N/S/E/W marker (auto-extent). Idempotent."""
        box = None
        for c in CARDINALS:
            if c in self.markers:
                continue
            box = box or building_bbox(self._ms)
            self._adopt(SectionMarker.cardinal(c, box))

    def next_name(self) -> str:
        self._counter += 1
        return f"Section {self._counter}"

    def _seed_depth(self, a: QPointF, b: QPointF) -> float:
        """Building extent beyond the line on the look side (s9), 10 000 mm when nothing is there."""
        probe = SectionMarker("probe", a, b, 1, 1.0)
        nx, ny = probe.normal_scene()
        bb = building_bbox(self._ms)
        if bb.width() >= 2 * FALLBACK_HALF:                   # empty project fallback box
            return 10000.0
        best = max((c.x() - a.x()) * nx + (c.y() - a.y()) * ny
                   for c in (bb.topLeft(), bb.topRight(), bb.bottomLeft(), bb.bottomRight()))
        return best if best > 0.0 else 10000.0

    def place_section(self, a: QPointF, b: QPointF) -> SectionMarker:
        m = SectionMarker(self.next_name(), a, b, 1, self._seed_depth(a, b))
        self._adopt(m)
        self.sectionsChanged.emit()
        return m

    def delete_section(self, name: str) -> None:
        key = self._key(name)
        m = self.markers.get(key)
        if m is None:
            return
        if m.cardinal:
            raise ValueError("cardinal sections are permanent (D5b)")
        self.close_section(key)
        self.markers.pop(key)
        if m.scene() is self._ms:
            self._ms.removeItem(m)
        self.sectionsChanged.emit()

    def rename_section(self, old: str, new: str) -> None:
        key = self._key(old)
        m = self.markers.get(key)
        if m is None or m.cardinal or not new or new == old or self._key(new) in self.markers:
            return
        self.markers.pop(key)
        m.name = new
        self.markers[new] = m
        if key in self._views:
            scene, view = self._views.pop(key)
            self._views[new] = (scene, view)
            if view is not None:
                for i in range(self._tabs.count()):
                    if self._tabs.widget(i) is view:
                        self._tabs.setTabText(i, self._tab_title(m))
        # Sheet viewports bound as section:<old> follow the name.
        for sheet in getattr(self._ms, "_sheets", []) or []:
            for sv in getattr(sheet, "sheet_views", []):
                if sv.source_view_type == "section" and sv.source_view_name == old:
                    sv.source_view_name = new
        self.sectionsChanged.emit()

    @property
    def section_names(self) -> list[str]:
        """Placed (non-cardinal) sections, in creation order."""
        return [m.name for m in self.markers.values() if not m.cardinal]

    # -- views --------------------------------------------------------------------------
    @staticmethod
    def _tab_title(m: SectionMarker) -> str:
        return f"Elevation: {m.cardinal.title()}" if m.cardinal else f"Section: {m.name}"

    def get_or_build_scene(self, name: str) -> SectionScene | None:
        """The section's scene, built tab-less when no tab is open (sheets, s7.2)."""
        key = self._key(name)
        if key in self._views:
            return self._views[key][0]
        m = self.markers.get(key)
        if m is None:
            return None
        scene = SectionScene(m, self._ms, self._lm, self._sm)
        scene.rebuild()
        self._views[key] = (scene, None)
        return scene

    def open_section(self, name: str) -> SectionView | None:
        key = self._key(name)
        if key in self._views and self._views[key][1] is not None:
            scene, view = self._views[key]
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.setCurrentIndex(i)
                    return view
            self._views[key] = (scene, None)              # tab removed externally
        m = self.markers.get(key)
        if m is None:
            return None
        scene = self.get_or_build_scene(key)
        view = SectionView(scene, self._sm)
        idx = self._tabs.addTab(view, self._tab_title(m))
        self._tabs.setCurrentIndex(idx)
        QTimer.singleShot(50, view.fit_to_screen)
        self._views[key] = (scene, view)
        return view

    def close_section(self, name: str) -> None:
        key = self._key(name)
        entry = self._views.pop(key, None)
        if entry is None:
            return
        scene, view = entry
        if view is not None:
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.removeTab(i)
                    break

    def close_all(self) -> None:
        for k in list(self._views):
            self.close_section(k)

    def forget_view(self, widget) -> None:
        """A tab closed by the user: drop the view, keep the scene for sheets."""
        for key, (scene, view) in list(self._views.items()):
            if view is widget:
                self._views[key] = (scene, None)

    def clear(self) -> None:
        """New / load: drop every marker and view (markers are re-seeded by the caller)."""
        self.close_all()
        for m in list(self.markers.values()):
            if m.scene() is self._ms:
                self._ms.removeItem(m)
        self.markers.clear()
        self._counter = 0

    def get_view(self, name: str) -> SectionView | None:
        e = self._views.get(self._key(name))
        return e[1] if e else None

    def get_scene(self, name: str) -> SectionScene | None:
        e = self._views.get(self._key(name))
        return e[0] if e and e[1] is not None else None

    @property
    def open_names(self) -> list[str]:
        return [k for k, (sc, v) in self._views.items() if v is not None]

    @property
    def open_scenes(self) -> list[SectionScene]:
        """Every live section scene (open tabs and sheet-built) -- 560 / acceptance (c)."""
        return [sc for sc, _v in self._views.values()]

    def rebuild_all(self) -> None:
        for scene, _v in self._views.values():
            scene.rebuild()

    def on_marker_geometry_changed(self, marker: SectionMarker) -> None:
        e = self._views.get(marker.view_name)
        if e is not None:
            e[0]._schedule_rebuild()

    # -- persistence / undo (s8) -------------------------------------------------------
    def to_list(self) -> list[dict]:
        return [m.to_dict() for m in self.markers.values()]

    def from_list(self, data: list[dict]) -> None:
        """Project load: replace every marker, then the caller seeds cardinals."""
        self.clear()
        for d in data:
            m = SectionMarker.from_dict(d)
            self._adopt(m)
            parts = m.name.split()
            if not m.cardinal and len(parts) >= 2:
                try:
                    self._counter = max(self._counter, int(parts[-1]))
                except ValueError:
                    pass
        self.sectionsChanged.emit()

    def restore_from_list(self, data: list[dict]) -> None:
        """Undo restore: diff by name -- update survivors in place, remove
        deleted, re-add missing; open tabs are left alone (s8)."""
        want = {(d["cardinal"] or d["name"]): d for d in data}
        for key in list(self.markers):
            if key not in want and not self.markers[key].cardinal:
                self.delete_section(key)
        for key, d in want.items():
            m = self.markers.get(key)
            if m is None:
                self._adopt(SectionMarker.from_dict(d))
                continue
            m.set_geometry(QPointF(*d["cut_a"]), QPointF(*d["cut_b"]), d["depth_mm"], user=False)
            if m.look_sign != d["look_sign"]:
                m.flip()
            m._auto_extent = bool(d.get("auto_extent", False)) if m.cardinal else False
            m.gridline_z_overrides = dict(d.get("gridline_z_overrides", {}))
            if m.name != d["name"] and not m.cardinal:
                self.rename_section(m.name, d["name"])
        self.sectionsChanged.emit()
```

Delete the `ElevationManager` alias; delete the `ElevationView = SectionView` alias in `elevation_view.py`.

- [ ] **Step 4: Display Manager label + class-name matches**

`firepro3d/display_manager.py`: in the `"Elevation Marker"` row add `"label": "Section Marker",`; add after `_CATEGORY_MAP`:

```python
def category_label(key: str) -> str:
    """Display name of a category row; the settings key when no label is set (D8)."""
    cat = _CATEGORY_MAP.get(key)
    return cat.get("label", key) if cat else key
```

and use `category_label(key)` wherever the tree / dialog shows the row name (grep `QTreeWidgetItem(` and `setText(` call sites taking `cat_def["key"]` / `key` as display text -- lines ~1521, 2051, 2160, 2271, 3089; change only display-text arguments, never the settings path). `_is_elevation_marker`: `return type(item).__name__ == "SectionMarker"`; its docstring and `_apply_elevation_marker`'s ("Apply display settings to a SectionMarker"). `paper_display._category_for_item`: `if cls_name == "SectionMarker": return "Elevation Marker"`.

- [ ] **Step 5: `main.py`**

- Construction (415-422): `from firepro3d.section_manager import SectionManager`; `self.section_manager = SectionManager(self.scene, self.level_mgr, self.scene.scale_manager, self.central_tabs)`; `self.scene._section_manager = self.section_manager`; `self.level_widget.levelsChanged.connect(self.section_manager.rebuild_all)`; `self.section_manager.sectionsChanged.connect(self._refresh_section_browser)`. Then `grep -n "elevation_manager" main.py` and rename every remaining use to `section_manager` (the 1b map: 466, 1093, 1214, 1287, 1427-1428, 2388, 2404, 3868, 4065, 4395).
- `_create_elevation_markers` (1436-1444) -> delete; its three call sites (744, 4043, 4276) become `self.section_manager.seed_cardinals()`. `new_file` (740s) and the 4270s new-project path call `self.section_manager.clear()` **before** `_clear_scene()` is done and `seed_cardinals()` after `_place_default_gridlines()`; the load path (4043) calls `seed_cardinals()` only (scene_io's `from_list` already replaced the markers, Task 12).
- `_activate_elevation(direction)` keeps its name and body but calls `self.section_manager.open_section(direction)` and checks `direction.lower() in self.section_manager.open_names`; add

```python
    def _activate_section_view(self, name: str):
        """Open or switch to a placed section's tab (project browser / marker)."""
        already_open = name in self.section_manager.open_names
        view = self.section_manager.open_section(name)
        if view is not None and not already_open:
            scene = view.scene()
            if scene is not None:
                scene.entitySelected.connect(self.prop_manager.show_properties)
            view.cursorMoved.connect(self.footer.set_coord)

    def _delete_section_view(self, name: str):
        self.scene.push_undo_state()
        self.section_manager.delete_section(name)

    def _refresh_section_browser(self):
        self.project_browser.refresh_sections(self.section_manager.section_names)
```

- `_on_open_view_requested`: add `elif view_type == "section": self._activate_section_view(name)`. `_navigate_to_source_view`: `elif view_type == "section": self._activate_section_view(view_name)`.
- Tab close (1211-1214): replace the `_views.pop` with `self.section_manager.forget_view(widget)` for tabs whose text starts with `"Elevation: "` or `"Section: "`; `_close_stale_view_tabs` (1273, 1287): add `"Section: "` to the prefix tuple and replace `self.elevation_manager._views.clear()` with `self.section_manager.close_all()`.
- `_on_tab_changed` needs nothing (sections have no level context).
- `_live_scenes` (2388-2390): `sm = getattr(self, "section_manager", None); if sm is not None: scenes.extend(sm.open_scenes)`.
- Ribbon (after `_detail_btn`, 1707):

```python
        _section_btn = g_3d.add_small_button(
            "Section", _I("detail_icon.svg"),
            lambda: self.scene.set_mode("section"),
            checkable=True)
        _section_btn.setToolTip("Place a section: click the start and end of the cut line")
        self._mode_buttons["section"] = _section_btn
```

- Project browser wiring beside the detail signals (401-410): `self.project_browser.activateSectionView.connect(self._activate_section_view)`; `self.project_browser.deleteSectionView.connect(self._delete_section_view)`.
- Property-manager title map (3665-3680): `if isinstance(item, SectionMarker): return "Section"` (import beside `DetailMarker`).

- [ ] **Step 6: Project browser**

`firepro3d/project_browser.py`: signals `activateSectionView = pyqtSignal(str)` and `deleteSectionView = pyqtSignal(str)`; `_ROLE_TYPE` comment gains `"section"`; `mimeData` role tuple `("plan", "elevation", "detail", "section", "schematic")`; after the Details root build a `Sections` root (`self._sections_root`, type `"ms_stub"`, bold) with

```python
    def refresh_sections(self, names: list[str]):
        """Rebuild the Sections sub-tree (placed sections; cardinals stay under Elevations)."""
        if self._sections_root is None:
            return
        self._sections_root.takeChildren()
        for name in names:
            item = QTreeWidgetItem(self._sections_root, [name])
            item.setData(0, _ROLE_TYPE, "section")
            item.setData(0, _ROLE_NAME, name)
            item.setToolTip(0, f"Section view -- {name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            if ("section", name) in self._placed_views:
                f = QFont(); f.setItalic(True); item.setFont(0, f)
        self._sections_root.setExpanded(True)
```

`set_placed_views` loop gains `("section", self._sections_root)`; `_on_item_activated` gains `elif role == "section": self.activateSectionView.emit(name)`; the context menu gains a `"section"` branch mirroring `"detail"` (Open / Delete -> `activateSectionView` / `deleteSectionView`). Initialise `self._sections_root = None` where `_details_root` is.

- [ ] **Step 7: `docs/gen_ref_pages.py`**: module names `elevation_manager` -> `section_manager`, `elevation_scene` -> `section_scene`, add `section_marker` if `view_marker` was listed.

- [ ] **Step 8: Coupled tests, then run**

Tests bound to the retired manager API at plan time (`grep -rln "elevation_manager\|open_elevation\|_create_elevation_markers\|_view_marker_mgr" tests/`): `tests/test_hf1_seam_fixes.py` (`win.elevation_manager.open_elevation("north")` / `get_scene("north")` -> `win.section_manager.open_section("north")` / `get_scene("north")`), `tests/test_paper_viewport_crop.py`, `tests/test_viewport_properties.py` (they build a `ViewResolver` with an elevation manager -- pass a `SectionManager` and open through `open_section`), and `tests/test_manip_griphandle_viewmarker_parity.py` (already rewritten in Task 8). Re-run the grep after editing; it must be empty.

Run: `... -m pytest tests/test_section_manager.py tests/test_hf1_seam_fixes.py tests/test_paper_viewport_crop.py tests/test_viewport_properties.py tests/test_project_browser*.py tests/test_display_manager*.py tests/test_paper_display*.py <net> -q` (Bash globs; add every file from `grep -rln "elevation_manager\|_create_elevation_markers\|Elevation Marker" tests/`).
Expected: green. RED proofs: (1) remove the `raise ValueError` in `delete_section` -> `test_delete_rename_cascade` fails; (2) `category_label` returning `key` -> `test_dm_row_label_section_marker_key_unchanged` fails. Then launch-smoke: `"D:/Custom Code/FirePro3D/venv/Scripts/python.exe" main.py` from the worktree root -- the app opens, four markers show, a `Section` button sits beside `Detail`.

- [ ] **Step 9: Retired-name grep + commit**

`grep -rn "elevation_manager\|ElevationManager\|ElevationView\b\|_create_elevation_markers\|ViewMarkerArrow\|SharedCropBox\|ViewMarkerManager\|open_elevation\|close_elevation\|open_directions" --include=*.py . docs/gen_ref_pages.py` returns nothing.

```bash
git add firepro3d/section_manager.py firepro3d/elevation_view.py main.py firepro3d/project_browser.py firepro3d/display_manager.py firepro3d/paper_display.py docs/gen_ref_pages.py tests/test_section_manager.py <coupled test files>
git commit -F <message file>   # "feat(section): SectionManager, ribbon Section button, browser Sections group, DM label; cardinals seeded as permanent sections (S4, D5, D8, 560)"
```

### Task 12: Persistence -- `sections` key in `scene_io`, seeding on absence

**Files:**
- Modify: `firepro3d/scene_io.py`
- Test: `tests/test_section_persistence.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""Acceptance (f) / D4: project file gains "sections"; absence seeds four
cardinals; round-trip restores markers, boxes and overrides; no SAVE_VERSION bump."""
import json
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.section_marker import CARDINALS


def _scene_with_manager(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_manager import SectionManager
    ms = Model_Space()
    lm = LevelManager(); ms._level_manager = lm
    sm = ScaleManager(); ms.scale_manager = sm
    mgr = SectionManager(ms, lm, sm, QTabWidget())
    ms._section_manager = mgr
    return ms, mgr


def test_save_version_unchanged():
    from firepro3d.model_space import Model_Space
    assert Model_Space.SAVE_VERSION == 11          # D4 / S4: no bump (value at 682c1edd)


def test_round_trip_restores_placed_section(qapp, tmp_path):
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    s = mgr.place_section(QPointF(100.0, 200.0), QPointF(5100.0, 1200.0))
    s.flip(); s.set_geometry(s.cut_a, s.cut_b, 4321.0)
    s.gridline_z_overrides["A"] = {"v_top": -9000.0, "v_bot": 100.0}
    north = mgr.markers["north"]
    north.set_geometry(north.cut_a, north.cut_b, 7777.0)        # user-owned cardinal box
    path = tmp_path / "p.fp3d"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [d["name"] for d in payload["sections"]] == ["North", "South", "East", "West", "Section 1"]
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    assert set(mgr2.markers) == set(CARDINALS) | {"Section 1"}
    s2 = mgr2.markers["Section 1"]
    assert s2.to_dict() == s.to_dict()
    assert mgr2.markers["north"].auto_extent is False and mgr2.markers["north"].depth_mm == 7777.0
    assert mgr2.markers["south"].auto_extent is True


def test_missing_key_seeds_four_cardinals(qapp, tmp_path):
    ms, mgr = _scene_with_manager(qapp)
    path = tmp_path / "old.fp3d"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["sections"]                                       # a pre-section project file
    path.write_text(json.dumps(payload), encoding="utf-8")
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    assert set(mgr2.markers) == set(CARDINALS) and all(m.auto_extent for m in mgr2.markers.values())


def test_one_missing_cardinal_reseeded(qapp, tmp_path):
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    path = tmp_path / "edited.fp3d"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sections"] = [d for d in payload["sections"] if d["cardinal"] != "east"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    assert set(mgr2.markers) == set(CARDINALS)
```

Verified at plan time: the `scene_io` mixin methods are `save_to_file(filename)` / `load_from_file(filename)`.

- [ ] **Step 2: Run to verify failure**

Expected: `test_round_trip...` fails on `KeyError: 'sections'`; `test_missing_key...` fails (no seeding on load).

- [ ] **Step 3: Implement** (`firepro3d/scene_io.py`)

Payload (after `"detail_views"`):

```python
            "sections":            (self._section_manager.to_list()
                                    if getattr(self, "_section_manager", None) else []),
```

Load (after the Detail views block):

```python
        # --- Sections (spec s8, D4): key present -> replace markers; always seed cardinals ---
        sec_mgr = getattr(self, "_section_manager", None)
        if sec_mgr is not None:
            sec_data = payload.get("sections")
            if sec_data is not None:
                sec_mgr.from_list(sec_data)
            else:
                sec_mgr.clear()
            sec_mgr.seed_cardinals()
```

`main.py`'s load path (Task 11 step 5) then needs no `seed_cardinals()` of its own -- remove the call it added there if this block covers it (one home for the rule). Keep `main.py`'s new-project seeding.

- [ ] **Step 4: Run**

Run: `... -m pytest tests/test_section_persistence.py tests/test_scene_io*.py tests/test_save*.py tests/test_load*.py -q` (Bash globs; plus `grep -rln "save_to_file\|detail_views" tests/`).
Expected: green. RED proof: drop `sec_mgr.seed_cardinals()` -> `test_missing_key_seeds_four_cardinals` and `test_one_missing_cardinal_reseeded` fail; restore.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/scene_io.py tests/test_section_persistence.py main.py
git commit -F <message file>   # "feat(section): persist section markers under 'sections'; absence seeds cardinals, no SAVE_VERSION bump (D4, acceptance f)"
```

### Task 13: Sheets -- `ViewResolver` `"section"` branch via `get_or_build_scene`; `SheetViewport` treats section as elevation; Sections in `available_views`

**Files:**
- Modify: `firepro3d/paper_space.py` (`ViewResolver.__init__` param name, `resolve`, `_resolve_elevation` -> `_resolve_section`, `available_views`, `SheetViewport._begin_isolation`)
- Test: `tests/test_section_sheet_plot.py` (add)

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_section_viewport_resolves_after_reload_without_open_tab(qapp, tmp_path):
    """Acceptance (a): a sheet viewport bound as section:<name> resolves to a
    scene with no tab open (today _resolve_elevation returns None for a closed tab)."""
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.paper_space import ViewResolver
    from tests.test_section_persistence import _scene_with_manager
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    mgr.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    resolver = ViewResolver(ms, None, None, mgr, level_manager=ms._level_manager)
    got = resolver.resolve("section", "Section 1")
    assert got is not None and got[0].marker is mgr.markers["Section 1"]
    got_e = resolver.resolve("elevation", "North")
    assert got_e is not None and got_e[0].marker is mgr.markers["north"]
    assert mgr.open_names == []                                       # no tab was opened
    assert resolver.resolve("section", "Nope") is None
    assert resolver.available_views()["Sections"] == ["Section 1"]
    assert resolver.available_views()["Elevations"] == ["North", "South", "East", "West"]
    assert resolver.resolve_level_context("section", "Section 1") is None   # no isolation


def test_placed_marker_plots_and_cardinal_does_not(qapp, tmp_path):
    """Acceptance (a), second half: the host plan's paper render includes the
    placed marker and excludes the cardinal ones."""
    from firepro3d.paper_display import paper_items   # grep: the helper that filters PAPER_EXCLUDED (paper_display.py ~1196)
    from tests.test_section_persistence import _scene_with_manager
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    s = mgr.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    plotted = set(paper_items(ms))
    assert s in plotted and not (plotted & set(mgr.markers[c] for c in CARDINALS))
```

Grep the real name of the paper item filter at `paper_display.py:1196` (the function whose loop reads `PAPER_EXCLUDED`) and use it; if it is a method on a render pass, drive that pass instead and assert on the items it painted (the `test_paper_marker_exclusion.py` tests show the house pattern -- reuse theirs).

- [ ] **Step 2: Run to verify failure**

Expected: `resolve("section", ...)` returns `None`; `available_views()` has no `"Sections"`.

- [ ] **Step 3: Implement** (`firepro3d/paper_space.py`)

```python
    def __init__(self, model_scene, plan_view_manager,
                 detail_manager, section_manager, level_manager=None,
                 schematic_scenes=None):
        ...
        self._sm = section_manager          # SectionManager (cardinals + placed sections)
```

(rename every `self._em` in the class to `self._sm`; `main.py`'s construction passes `self.section_manager`.)

```python
        if view_type in ("elevation", "section"):
            return self._resolve_section(view_name)
```

```python
    def _resolve_section(self, name: str):
        """(scene, extent) for a cardinal or placed section; the scene is
        built tab-less when no tab is open so a reloaded sheet never goes
        blank (spec s7.2, acceptance a)."""
        if self._sm is None:
            return None
        scene = self._sm.get_or_build_scene(name)
        if scene is None:
            return None
        rect = scene.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            rect = QRectF(0, 0, 1000, 1000)
        return (scene, rect)
```

`available_views`: after the `Elevations` group add

```python
        if self._sm is not None:
            names = self._sm.section_names
            if names:
                result["Sections"] = names
```

`resolve_level_context`: the docstring gains "section"; the function already returns `None` for unknown types. `SheetViewport._begin_isolation`: `if resolver is None or self._data.source_view_type in ("elevation", "section"): return None`. Grep `"elevation"` across `paper_space.py` (679-719, 861, 920, 956, 1096, 1103, 3533) and extend each comparison / comment that means "own-scene view" to include `"section"`.

- [ ] **Step 4: Run**

Run: `... -m pytest tests/test_section_sheet_plot.py tests/test_paper_viewport_crop.py tests/test_viewport_properties.py tests/test_paper_*.py tests/test_hf1_seam_fixes.py -q` (Bash glob).
Expected: green. RED proof: make `_resolve_section` call `self._sm.get_scene(name)` instead of `get_or_build_scene` -> `test_section_viewport_resolves_after_reload_without_open_tab` fails (None without a tab); restore.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/paper_space.py tests/test_section_sheet_plot.py main.py
git commit -F <message file>   # "feat(section): sheets resolve cardinal and placed sections tab-less; Sections group in available views (S4, acceptance a)"
```

**G4 review (Tasks 11-13):** spec reviewer walks s7.1 (every method), s7.2 (identity table), s7.3 (each consumer), s8; quality reviewer diffs the OLD `ElevationManager` / `_resolve_elevation` / `_create_elevation_markers` paths against the new ones (VC10 port clause) and s13's "hand-edited file missing a cardinal" row.

---

# G5 -- docs, retired-name sweep, keep-green (Account prep)

### Task 14: Docs and the whole-repo retired-name sweep

**Files:**
- Modify: `docs/specs/SPEC-INDEX.md` (section-view row `applies-to` -> the three new modules; drop the "until the move lands" rows), `docs/specs/section-view-subsystem.md` frontmatter `applies-to` (drop the three `until the move lands` lines; the five reconciliations above go into s15 / the relevant sections), `docs/specs/view-relationships.md` s4 / s6 (one-line pointers to the section spec where they restate elevation-marker facts -- Rule A), `docs/gen_ref_pages.py` (verified in Task 11)
- No tests; this task's gate is the grep.

- [ ] **Step 1: Retired-name sweep**

`grep -rn "ElevationScene\|ElevationManager\|ElevationView\b\|ViewMarkerArrow\|SharedCropBox\|ViewMarkerManager\|_create_elevation_markers\|_is_cardinal_for_elevation\|_world_to_elev\|elevation_scene\.py\|elevation_manager\.py\|view_marker\.py\|elevation_scene_for" --include=*.py --include=*.md . | grep -v "docs/specs/section-view-subsystem.md\|docs/plans/2026-10-20-section-view-subsystem.md\|todo_closed.md"` -> every remaining hit is a doc line to fix (specs / architecture pages) or history text to leave; list them in the commit message.

- [ ] **Step 2: Spec edits** -- apply the five reconciliations (coordinates, pipe cut colour, cut wall face, concave chord, icon) and the `applies-to` cleanup. Do NOT stamp `last-verified` / `verified-commit` here: Account (Phase 6 step 6) stamps after the merge SHA exists.

- [ ] **Step 3: Full keep-green** (orchestrator runs VC6 at Phase 6; this task runs the union of every task's keep-green set once): the net + `tests/test_section_*.py tests/test_gridline_section.py tests/test_manip_griphandle_viewmarker_parity.py tests/test_paper_marker_exclusion.py tests/test_gridline_core.py tests/test_gridline_integration.py` (Bash glob).

- [ ] **Step 4: Commit**

```bash
git add docs/specs/SPEC-INDEX.md docs/specs/section-view-subsystem.md docs/specs/view-relationships.md
git commit -F <message file>   # "docs(section): index + spec applies-to follow the module moves; reconciliations recorded (pre-Account)"
```

## Follow-ups to file at Phase 6 (spec s14 + plan reconciliations)

Roof cut-render (mesh / plane intersection); cut-vs-projection line-weight DM columns (D2b); detail-marker undo; jogged / stepped sections; break lines; in-view dimensions; vertical crop handles; receding face of an obliquely cut wall; concave slab chord gaps; a section ribbon icon asset; SB4c / SB4d / HF5 lines re-worded to `section_scene.py` / `section_marker.py`; the VC7 `test_empty_click_deselects` order flake; 767 closed as stale (Phase 6 step 3).
