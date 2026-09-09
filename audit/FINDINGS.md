# Findings Register — Census 2026-09-09

Categories: delete / dedupe / abstract / restructure / spec-gap / bug. Status: open → accepted/rejected/done. **User triages every row.** IDs stable across runs.

## Dead code — delete

| # | File(s) | Cat | Description | Risk | Effort | Status |
|---|---|---|---|---|---|---|
| F1 | `backup/2025-09-29_node.py` | delete | Backup file committed to git. No dynamic-access risk (backup/ dir). | low | S | open |
| F2 | `firepro3d/layer_manager.py` (128 LOC, `LayerManager`) | delete | Layer system was **removed** (CLAUDE.md). Only referenced by a stale comment in `model_space.py:146` + auto-gen `docs/gen_ref_pages.py`. No real importer. grep: no getattr/importlib dynamic access. | low | S | open |
| F3 | annotations/array_dialog/auto_populate_dialog/model_view/paper_space/main | delete | 6 unused imports @90% (QTextOption, QAbstractSpinBox, `_interpolate_density`, QScrollBar, QGraphicsDropShadowEffect, QStyleFactory). | low | S | open |
| F4 | auto_populate_dialog/display_manager/manip_handle/model_view/paper_display/wall_opening | delete | 6 unused local vars @100% (prev_col×2, applied_pt, next_child, source_view_key, preset) — dead assignments. | low | S | open |
| F5 | 16 funcs @60% (see vulture.txt) | delete | Candidate-dead functions — e.g. `geometry_intersect.circle_circle_intersections`, `align_engine.point_along_ray`, `block_library.list_library`, `hatch_patterns.{refresh_patterns,is_builtin,make_hatch_tile}`, `underlay_cache.delete_cache`, `manip_math.transform_angle_deg`. Each needs a caller+test+dynamic-access grep before delete. | low | M | open |
| F6 | fs_visibility_dialog/loading/loading_bar | delete | Unused classes @60%: `FSVisibilityDialog`, `LoaderWorker`, `LoadingBar`. Verify not instantiated dynamically. **Excludes `ui_kit.*` (unbuilt-by-design per ui-design-system.md proposal) and `TitleBlockFieldOverlay`.** | med | M | open |

## Latent bug (found while mapping — logged, NOT fixed per hard rule 1)

| # | File(s) | Cat | Description | Risk | Effort | Status |
|---|---|---|---|---|---|---|
| F7 | `firepro3d/scene_tools.py` (+placement_input_coordinator, paper_space, wall_opening, format_utils, design_area) | bug | **Missing imports**: `QGraphicsRectItem` (L893) & `QGraphicsEllipseItem` (L1124) used but never imported → NameError if highlight/merge-marker branches run. 15 total F821 undefined-name across 6 files — investigate each (some may be forward-refs). **live-smoke-required.** | high | M | open |

## Duplication — dedupe (same-spec, safe to propose)

| # | File(s) | Cat | Description | Risk | Effort | Status |
|---|---|---|---|---|---|---|
| F8 | `floor_slab.py` ↔ `roof.py` | dedupe | 3 duplicate blocks (253:328/357:423, 551:581/639:668, 404:421/494:511). Both under wall-room-floor-system.md — slab-like items sharing paint/serialize logic. | med | M | open |
| F9 | `roof.py`↔`wall.py` (480:514/588:622), `floor_slab.py`↔`wall.py` (230:247/359:379) | dedupe | Same spec (wall-room-floor-system.md). | med | M | open |
| F10 | `roof_dialog.py` ↔ `wall_dialog.py` (140:161/43:66) | dedupe | Same spec — dialog scaffolding. | low | S | open |
| F11 | `block_manager.py` ↔ `underlay_manager.py` (505:525/301:321) | dedupe | Both under ui-design-system.md (dialog chrome). | low | S | open |

## Duplication — ⚠ CROSS-SPEC (human decision only, never auto-propose — hard rule 3)

| # | File(s) | Cat | Description | Risk | Effort | Status |
|---|---|---|---|---|---|---|
| F12 | `hydraulic_report.py` ↔ `thermal_radiation_report.py` (47:71/59:83) | dedupe ⚠ | Specs: hydraulic-solver-and-reporting.md vs **thermal orphan**. Report-header scaffold shared. | med | M | open |
| F13 | `model_space.py` ↔ `scene_io.py` (1847:1862/45:69) | dedupe ⚠ | The **known dual-serialization path** (`_capture_network` vs `scene_io` — intentional independent serializers). Likely **REJECT**. | med | M | open |
| F14 | `elevation_scene.py` ↔ `gridline.py` (109:126/234:255) | dedupe ⚠ | Specs: view-relationships.md vs grid-system.md. | low | M | open |
| F15 | `annotations.py` ↔ `pipe.py` (372:387/325:340) | dedupe ⚠ | Cross-subsystem. | low | M | open |
| F16 | `level_widget.py` ↔ `project_browser.py` / `property_manager.py` | dedupe ⚠ | Cross-subsystem UI widget scaffolding. | low | S | open |

## Dependency hygiene

| # | File(s) | Cat | Description | Risk | Effort | Status |
|---|---|---|---|---|---|---|
| F17 | `requirements.txt` | delete | Unused deps: `fonttools`, `freetype-py`, `requests` (grep: zero imports). **Keep `pytest-timeout`** — pytest plugin used via config, deptry false positive. | low | S | open |

## Restructure — monster files (governed / sequenced LAST)

| # | File(s) | Cat | Description | Risk | Effort | Status |
|---|---|---|---|---|---|---|
| F18 | `firepro3d/model_space.py` | restructure | 7401 LOC, MI C(0.00), `keyPressEvent` F(114) + 4 more F-grade. **Already governed decomposition** (model-space-architecture.md, slices 1–11 landed). Continue extraction; not a fresh proposal. | med | L | open |
| F19 | `firepro3d/underlay_import_dialog.py` | restructure | 3839 LOC, C(0.00), no decomposition in flight. Highest-leverage NEW deep-map target. | med | L | open |
| F20 | `firepro3d/display_manager.py` | restructure | 2816 LOC, C(0.00), `apply_display_to_item` E(32). | med | L | open |

## Spec-coverage census
Project is **well-governed** — SPEC-INDEX.md maps every major subsystem; orphans (thermal radiation, preferences dialog, 3D view, scene_io, feature system) are already tracked with a lazy-backfill posture. **No new orphans, no stale-spec rows** (section-view `section_*.py` non-existence is an intentional proposal, not drift). `annotations.py` / `level_widget.py` have no explicit index row — likely fold under paper-space / view-relationships; note for confirmation, not a forge-now orphan.
