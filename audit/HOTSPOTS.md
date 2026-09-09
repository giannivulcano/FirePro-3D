# Hotspots — Census 2026-09-09

Ranked by size × complexity × churn. Line counts: `git ls-files | wc -l`. Complexity: radon CC worst-function grade. Churn: all-history commit count touching the file.

| Rank | File | Lines | MI | Worst fn (CC) | Churn | Governance |
|---|---|---|---|---|---|---|
| 1 | `firepro3d/model_space.py` | 7401 | C(0.00) | `keyPressEvent` F(114), `set_mode` F(83), `_restore_network` F(82), `_bulk_delete` F(69) | 334 | model-space-architecture.md — **active decomposition** (slices 1–11 landed) |
| 2 | `main.py` | 4829 | C(0.00) | — | 292 | ribbon-bar.md (init_ribbon) — mixed |
| 3 | `firepro3d/paper_space.py` | 4311 | C(0.00) | `apply_paper_overrides` F(50), `restore_model_display` E(34) | 109 | paper-space.md (partial) |
| 4 | `firepro3d/underlay_import_dialog.py` | 3839 | C(0.00) | — | 37 | underlay-workflow.md |
| 5 | `firepro3d/display_manager.py` | 2816 | C(0.00) | `apply_display_to_item` E(32), `_read_item_display_state` D(29) | 37 | architecture/display-system.md |
| 6 | `firepro3d/construction_geometry.py` | 2057 | C(0.00) | — | 38 | 2d-geometry.md |
| 7 | `firepro3d/view_3d.py` | 1873 | C(0.00) | — | 30 | **orphan** (3D view) |
| 8 | `firepro3d/snap_engine.py` | 1752 | C(0.00) | — | 45 | snapping-engine.md |
| 9 | `firepro3d/elevation_scene.py` | 1428 | C(0.00) | — | — | view-relationships.md |
| 10 | `firepro3d/scene_tools.py` | 1576 | C(0.00) | — | — | model-space-architecture.md |

## Worst individual functions (radon CC ≥ F, extraction candidates — sequenced last)
- `Model_Space.keyPressEvent` — **F(114)** (single worst in repo)
- `Model_Space.set_mode` F(83), `_restore_network` F(82), `_bulk_delete` F(69), `_detect_room_boundary` F(62)
- `LevelManager.apply_to_scene` F(62) · `DxfImportWorker._extract_geometry` F(59) · `HydraulicSolver.solve` F(53)
- `ModelBrowser.refresh` F(51) · `apply_paper_overrides` F(50) · `compute_voronoi_relaxation` F(47) · `Fitting.align_fitting` F(46)

**Default deep-map target:** `firepro3d/model_space.py` — but it is under active governed decomposition, so the higher-leverage first deep-map is `firepro3d/underlay_import_dialog.py` (3839 LOC, C(0.00), no decomposition in flight) or `firepro3d/display_manager.py`.
