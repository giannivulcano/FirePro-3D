# Governing-Spec Index

**Purpose:** the lookup that makes the `/todo` skill's **Ground** hook work — "which spec governs the file(s) I'm about to touch?" Every substantial subsystem should map to exactly one governing spec. Code with no row here is an **orphan**: forge a spec on first touch (Phase 1b orphan gate) before editing it.

**How to use:** before editing a file, find the row whose modules include it and load that spec as binding context. After changing it (Phase 6), re-audit and stamp that spec.

> Status column is the *target* per the 2026-06-22 doc audit; each spec's own `status:` frontmatter is backfilled when it's next touched (reorg execution or first-touch). Paths are current (`docs/specs/…`); they move to `docs/design/…` when the reorg lands. `architecture/` pages are the cross-subsystem ripple map and link into these specs (Rule A).

| Subsystem | Governing spec | Primary modules (`firepro3d/`) | Status |
|---|---|---|---|
| **Model_Space composition / decomposition** (structural) | `specs/model-space-architecture.md` | `model_space.py` (composition/seams — behavior slices governed by the per-subsystem specs below), `scene_tools.py`, `scene_io.py` | partial (as-built composition current; target decomposition proposal — forged 2026-08-28) |
| Snapping / OSNAP engine | `specs/snapping-engine.md` | `snap_engine.py`, `model_view.py` | current |
| SNAP toolbar / per-type toggles | `specs/snap-toolbar.md` | `ribbon_bar.py` (Snap group surface), `snap_engine.py` | current |
| Ribbon bar (tabs/groups/buttons, mode-button sync, contextual tabs) | `specs/ribbon-bar.md` | `ribbon_bar.py`, `font_group.py`, `icons.py`, `preferences_dialog.py`, `main.py` (`init_ribbon` + `_init_*_tab` + contextual-tab mechanism) | current |
| Ribbon icons / graphics | `specs/icon-style-guide.md` | `icons.py`, `svg_utils.py`, `graphics/Ribbon/` | current |
| Underlay / import I/O (DXF·DWG·PDF) | `specs/underlay-workflow.md` (+ `architecture/io.md`) | `dxf_import_worker.py`, `pdf_import_worker.py`, `underlay.py`, `underlay_cache.py`, `dwg_converter.py` | current |
| Hydraulics & reporting | `specs/hydraulic-solver-and-reporting.md` (+ `architecture/analysis.md`) | `hydraulic_solver.py`, `hydraulic_report.py`, `hydraulic_node_badge.py` | current |
| Grid system / gridlines | `specs/grid-system.md` | `gridline.py`, `model_space.py`, `model_view.py`, `align_engine.py` | current |
| 2D geometry / drawing items | `specs/2d-geometry.md` | `construction_geometry.py`, `model_space.py` (2D-geometry placement + dispatch), `snap_engine.py` (2D snap) | current |
| Walls / rooms / floors / openings | `specs/wall-room-floor-system.md` | `wall.py`, `room.py`, `floor_slab.py`, `wall_opening.py`, `roof.py`, `model_space.py` (floor placement dispatch + template §11), `level_manager.py` (floor pure-z-range visibility + rename remap §11.3) | current |
| Pipe placement methodology | `specs/pipe-placement-methodology.md` | `pipe.py`, `node.py`, `model_space.py` (placement) | current |
| Sprinkler system components | `specs/sprinkler-system-components.md` | `sprinkler.py`, `sprinkler_db.py`, `sprinkler_system.py`, `fitting.py`, `water_supply.py`, `design_area.py`, `nfpa_curves.py`, `design_point_dialog.py` | current |
| Parametric constraints / align | `specs/parametric-constraint-system.md` | `constraints.py`, `scene_tools.py` | current |
| Views / levels / Z-model (incl. elevation) | `specs/view-relationships.md` (+ `architecture/level-system.md`) | `level_manager.py`, `elevation_scene.py` (consumes the floor two-boundary z-model via `slab._z_range_with_lm` — still governed here; §7.1 plan view-range upper bound), `elevation_view.py`, `elevation_manager.py`, `view_marker.py`, `detail_view.py`, `view_range_dialog.py` | current |
| Display / visibility | `architecture/display-system.md` (Z-order owned by `view-relationships.md §7.3` + `constants.py`) | `display_manager.py`, `displayable_item.py` | current |
| Theming / UI tokens | `architecture/theming.md` | `theme.py` | current |
| Property panel / templates | `specs/property-panel.md` | `property_manager.py`, `dimension_edit.py` | current |
| Units & formatting conventions | `specs/units-and-formatting.md` | `scale_manager.py` (conventions consumed app-wide) | current |
| **Selection mode** | `specs/selection-mode.md` | `model_space.py` (selection) | **proposal** (unbuilt) |
| **Selection manipulator** (frame/handles/rotate + rigid transforms) | `specs/selection-manipulator.md` | `selection_manipulator.py` (new), `model_view.py` (selected-item render seam), `paper_space.py` (handle retirement), `construction_geometry.py` (RectangleItem bake) | **proposal** (designed 2026-08-29, unbuilt) |
| **Section view subsystem** | `specs/section-view-subsystem.md` | `section_*.py` (do not exist yet) | **proposal** (unbuilt) |
| **ALIGN — acquire-and-track alignment & dimension-driven placement** | `specs/align-placement.md` | `align_engine.py`, `align_controller.py`, `snap_engine.py`, `dynamic_input.py`, `model_space.py`, `model_view.py`, `preferences_dialog.py`, `main.py`, `constants.py`, `gridline.py`, `wall.py` | **partial** (ALIGN acquire→lock→infer→guide→navigate built — pure ray engine, acquire state machine, one-picker `find(align_paths=…)` at prio 20/30, `track` distance-along-path schema, 5 SNAP-pane knobs + F11; Navigate = Dynamic Input HUD; Equal-Spacing §7 + Selection-Dimensions §8 = proposal) |
| **Paper space / sheets** | `specs/paper-space.md` | `paper_space.py`, `paper_export.py`, `paper_export_dialog.py`, `paper_display.py`, `paper_commands.py` | **partial** (Phase-1 + plot + text annotations + multi-sheet management built; remaining annotation types / layer overrides pending) |
| Title block templates / editor | `specs/titleblock-template-system.md` | `titleblock_template.py`, `titleblock_editor.py`, `titleblock_arrange.py`, `paper_space.py` (title block rendering) | current |
| Project Browser (navigation tree / drag source) | `specs/project-browser.md` | `project_browser.py`, `main.py` (ProjectBrowser wiring) | current |
| Model Browser (entity tree / selection sync / delete) | `specs/model-browser.md` | `model_browser.py` | current (forged 2026-08-27 on first touch — delete feature) |

## Orphans — no governing spec (forge on first touch)

| Subsystem | Modules (`firepro3d/`) | Note |
|---|---|---|
| Thermal radiation analysis | `thermal_radiation_solver.py`, `thermal_radiation_report.py`, `fire_curves.py` | Fully implemented, undocumented. Highest-value orphan. |
| **Preferences dialog** | `preferences_dialog.py` | Built 2026-08-22 (5 panes: Snapping/Units & Precision/Import & Conversion/General/Project Info); governed temporarily by `ribbon-bar.md §3.4` + `docs/superpowers/specs/2026-08-22-ribbon-overhaul-design.md §3`. **Dedicated governing spec is a filed follow-up.** |
| 3D view | `view_3d.py`, `view_cube.py` | PyVista/VTK; cross-test teardown hazards (see memory). |
| Scene I/O / `.fpd` project format | `scene_io.py` | `architecture/io.md` exists but is thin/inaccurate; promote to a real spec on first touch. |
| **Feature system** (Feature framework: definition/instance, Category > Type, host strategies, Manager, Editor) | `wall_opening.py` (first Category = *Openings*), future `feature_*.py` | Vision specced in `wall-room-floor-system.md §7.16` (2026-08-23). The Opening element (first Feature) is governed by `wall-room-floor-system.md §7`. **Promote to its own governing spec at Phase B (Manager).** |

_Backfill posture: **lazy** — these get a spec the first time a task touches them (blocking-prerequisite), not proactively._
