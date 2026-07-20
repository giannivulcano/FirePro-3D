# Governing-Spec Index

**Purpose:** the lookup that makes the `/todo` skill's **Ground** hook work — "which spec governs the file(s) I'm about to touch?" Every substantial subsystem should map to exactly one governing spec. Code with no row here is an **orphan**: forge a spec on first touch (Phase 1b orphan gate) before editing it.

**How to use:** before editing a file, find the row whose modules include it and load that spec as binding context. After changing it (Phase 6), re-audit and stamp that spec.

> Status column is the *target* per the 2026-06-22 doc audit; each spec's own `status:` frontmatter is backfilled when it's next touched (reorg execution or first-touch). Paths are current (`docs/specs/…`); they move to `docs/design/…` when the reorg lands. `architecture/` pages are the cross-subsystem ripple map and link into these specs (Rule A).

| Subsystem | Governing spec | Primary modules (`firepro3d/`) | Status |
|---|---|---|---|
| Snapping / OSNAP engine | `specs/snapping-engine.md` | `snap_engine.py`, `model_view.py` | current |
| OSNAP toolbar / per-type toggles | `specs/osnap-toolbar.md` | `ribbon_bar.py` (Snap group surface), `snap_engine.py` | current |
| Ribbon bar (tabs/groups/buttons, mode-button sync) | `specs/ribbon-bar.md` | `ribbon_bar.py`, `font_group.py`, `main.py` (`init_ribbon` + `_init_*_tab`) | current |
| Underlay / import I/O (DXF·DWG·PDF) | `specs/underlay-workflow.md` (+ `architecture/io.md`) | `dxf_import_worker.py`, `pdf_import_worker.py`, `underlay.py`, `underlay_cache.py`, `dwg_converter.py` | current |
| Hydraulics & reporting | `specs/hydraulic-solver-and-reporting.md` (+ `architecture/analysis.md`) | `hydraulic_solver.py`, `hydraulic_report.py`, `hydraulic_node_badge.py` | current |
| Grid system / gridlines | `specs/grid-system.md` | `gridline.py`, `grid_lines_dialog.py` | current |
| Walls / rooms / floors / openings | `specs/wall-room-floor-system.md` | `wall.py`, `room.py`, `floor_slab.py`, `wall_opening.py`, `roof.py` | current |
| Pipe placement methodology | `specs/pipe-placement-methodology.md` | `pipe.py`, `node.py`, `model_space.py` (placement) | current |
| Sprinkler system components | `specs/sprinkler-system-components.md` | `sprinkler.py`, `sprinkler_db.py`, `sprinkler_system.py`, `fitting.py`, `water_supply.py`, `design_area.py`, `nfpa_curves.py`, `design_point_dialog.py` | current |
| Parametric constraints / align | `specs/parametric-constraint-system.md` | `constraints.py`, `scene_tools.py` | current |
| Views / levels / Z-model (incl. elevation) | `specs/view-relationships.md` (+ `architecture/level-system.md`) | `level_manager.py`, `elevation_scene.py`, `elevation_view.py`, `elevation_manager.py`, `view_marker.py`, `detail_view.py` | current |
| Display / visibility | `architecture/display-system.md` (Z-order owned by `view-relationships.md §7.3` + `constants.py`) | `display_manager.py`, `displayable_item.py` | current |
| Theming / UI tokens | `architecture/theming.md` | `theme.py` | current |
| Property panel / templates | `specs/property-panel.md` | `property_manager.py`, `dimension_edit.py` | current |
| Units & formatting conventions | `specs/units-and-formatting.md` | `scale_manager.py` (conventions consumed app-wide) | current |
| **Selection mode** | `specs/selection-mode.md` | `model_space.py` (selection) | **proposal** (unbuilt) |
| **Section view subsystem** | `specs/section-view-subsystem.md` | `section_*.py` (do not exist yet) | **proposal** (unbuilt) |
| **Inferred / dimension-driven placement** | `specs/inferred-dimension-driven-placement.md` | (greenfield) | **proposal** (unbuilt) |
| **Paper space / sheets** | `specs/paper-space.md` | `paper_space.py` | **partial** (Phase-1 only; export/print/annotations unbuilt) |

## Orphans — no governing spec (forge on first touch)

| Subsystem | Modules (`firepro3d/`) | Note |
|---|---|---|
| Thermal radiation analysis | `thermal_radiation_solver.py`, `thermal_radiation_report.py`, `fire_curves.py` | Fully implemented, undocumented. Highest-value orphan. |
| 3D view | `view_3d.py`, `view_cube.py` | PyVista/VTK; cross-test teardown hazards (see memory). |
| Scene I/O / `.fpd` project format | `scene_io.py` | `architecture/io.md` exists but is thin/inaccurate; promote to a real spec on first touch. |

_Backfill posture: **lazy** — these get a spec the first time a task touches them (blocking-prerequisite), not proactively._
