---
status: current
last-verified: 2026-09-30
verified-commit: f1d8151
applies-to:
  - firepro3d/view_3d.py
  - firepro3d/view_cube.py
  - firepro3d/view3d_tab.py (View3DTabController — the 3D tab's presence + ui/view3d_open pref)
  - firepro3d/canvas_placeholder.py (EmptyCanvasPlaceholder — I5)
  - firepro3d/model_space.py (view_available, NO_VIEW_HINT, set_mode no-view refusal, delete_items)
  - firepro3d/modify_tools_controller.py (ModifyToolsController.start no-view refusal)
  - main.py (View3D deferred import in main(); construction + controller + canvas stack in MainWindow.__init__; _CanvasTabBar.countChanged; _on_canvas_count_changed; _on_tab_close_requested 3D identity branch; _delete_if_not_editing; _on_escape; reset_for_project call sites; radiation heatmap calls + no-view refusal; closeEvent cleanup)
  - tests/conftest.py (stub_view3d fixture)
source-tasks: ["/todo 2026-09-30 orphan gate — 3D view forged before the closable-3D-tab work touches it", "todo_open.md — 3D Model canvas tab is closable and reopenable from the Project Browser [type:feature] (2026-09-30)"]
---

# 3D View — Design Spec (as-built + ratified as-intended)

**Status note.** Forged 2026-09-30 at `35d3c17` (orphan gate), then built on
`feat/3d-tab-closable`. §1–§8 are **as-built at `f1d8151`** (re-derived from the
code after the closable-3D-tab build; the forge-time readings they replace live
in git history). §9 is the forge-time hazard ledger, kept as history with a
Status column. §10 is the **ratified contract** (2026-09-30 grill + build-time
additions); every I-item is built and guarded (see Acceptance Criteria). Where
§1–§9 and §10 ever disagree, §10 wins and §1–§9 are the drift to fix.

**Adjacent specs:** `view-relationships.md` (view taxonomy; 3D is a read-only
projection, §3; its open question 5 "3D rebuild triggers" is answered by §2.3 here),
`project-browser.md` (the `3D Model` leaf), `mainwindow-chrome-revamp-stage2.md`
(canvas tabs + tonal scheme),
`test-harness.md` (Invariant 3 View3D stub; VTK-MainWindow and MainWindow-teardown
native-crash families),
`scene-io.md` (`.fpd` format — carries no 3D state, §7), `wall-room-floor-system.md`
(`get_3d_mesh()` producers), `thermal-radiation` (orphan — heatmap producer),
`architecture/theming.md` (tokens). Z-order for 2D is `view-relationships.md §7.3`;
it does not apply to 3D (GPU depth buffer).

## Goal

A single interactive 3D projection of the whole model (all levels) in the
"3D Model" central tab: orbit/pan/zoom navigation, a ViewCube for standard
engineering presets, click-to-select synchronised with the 2D plan selection,
section-cut and floor-plane toggles, and a thermal-radiation heatmap overlay.

## Motivation

Plan authoring is strictly 2D (`view-relationships.md §3.1`); the 3D view is the
user's check that elevations, wall/slab/roof extrusions and the pipe network
come together correctly in space.

## 1. Architecture & module boundaries (as-built)

- **`View3D(QWidget)`** (`view_3d.py`) owns a toolbar row + a pyvistaqt
  `QtInteractor` (`self._plotter`, a native VTK/OpenGL render window) + a
  `ViewCube` overlay parented to the plotter. `self._vtk_widget` is
  `self._plotter.interactor` (the event-filter target).
- **`ViewCube(QWidget)`** (`view_cube.py`) is a pure-QPainter overlay with no
  VTK/numpy dependency. It knows only `(elevation, azimuth)`; it never touches
  the camera. Out: `viewRequested(float elevation, float azimuth)`. In:
  `set_camera_angles(elev, azim)` (repaints only on a >0.1° change).
- **Constructor injection:** `View3D(model_space, level_manager, scale_manager)`
  stores `self._scene`, `self._lm`, `self._sm`. MainWindow passes `self.scene`,
  `self.level_mgr`, `self.scene.scale_manager`; `reset_for_project()` re-seats
  `_sm` to the live `scene.scale_manager` at startup and on every project
  new/open/recovery (I9 — `scene_io` replaces the manager on load/new).
- **`View3DTabController`** (`view3d_tab.py`) owns whether the 3D view is a
  canvas tab (open/close/startup pref — §2.2). **`EmptyCanvasPlaceholder`**
  (`canvas_placeholder.py`) is the widget shown when no canvas tab is open (I5).
  `View3D` itself knows nothing about tabs: it only reacts to being shown/hidden.
- **Actor bookkeeping:** `_actors: dict[category → list[actor|None]]`,
  `_actor_to_entity: actor → (entity, type_str)` (types `"wall"`, `"opening"`,
  `"slab"`, `"roof"`), `_actor_z_range: actor → (zmin, zmax)` for section cuts.
  `_clear_actors(category)` removes via pyvista then a raw VTK `RemoveActor`
  fallback. `_add_edge_actor` appends `None` when a mesh has no feature edges
  so mesh/edge lists stay index-aligned (relied on by `_apply_horizontal_cut`).
- **Coordinates:** `_scene_to_3d(sx, sy, z_mm)` → `(sx/ppm, -sy/ppm, z_mm)` where
  `ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0`. World is
  Z-up, mm; scene Y is negated. Node Z is `node.z_pos`; level Z is
  `LevelManager.get(name).elevation`.
- **Module constants** (colours, `PICK_TOLERANCE_PX`, `MAX_CYLINDER_PIPES`,
  `_PIPE_COLORS`, `_FLOOR_COLORS`, `FT_TO_MM`, `CIRCLE_SEGMENTS`) live in
  `view_3d.py`, not `constants.py` (see D14). Pipe OD comes from
  `Pipe.NOMINAL_OD_IN` (single source).

### 1.1 Data read across the boundary (per hop)

| Source | Field / call | Used by |
|---|---|---|
| `Model_Space` | `sprinkler_system.nodes`, `sprinkler_system.pipes` | `_extract_nodes/_pipes/_sprinklers`, `_extract_level_floors` (extent) |
| `Model_Space` | `water_supply_node` (`getattr`, may be `None`) | `_extract_water_supply` (drawn at Z=0 always) |
| `Model_Space` | private lists `_walls`, `_floor_slabs`, `_roofs` (`getattr`) | `_extract_walls/_openings/_floor_slabs/_roofs` |
| `Model_Space` | `selectedItems()`, `clearSelection()` | selection sync, `cancel_interaction` |
| `Model_Space` | `_radiation_selecting` (private flag, read **and written**), `radiationCancel`, `radiationConfirm` signals | `_on_key_press` (Enter/Return), `cancel_interaction` |
| `Model_Space` | `_hide_items(items)`, `_show_all_hidden()` (private) | context menu |
| `Model_Space` | `delete_items(items)` (explicit-list bulk delete, one undo step) | `delete_selected` (I8) |
| `Node` | `scenePos()`, `z_pos`, `has_sprinkler()`, `sprinkler._properties["Orientation"]["value"]` | positions, sprinkler colour (Pendent red / Sidewall green / else blue) |
| `Pipe` | `node1`, `node2`, `_properties["Colour"]["value"]`, `_properties["Diameter"]["value"]` | cylinder colour/radius |
| any item | `_display_overrides.get("visible")` (via `_is_visible`) | hide filter (openings honour their own and their host wall's — I14) |
| `WallSegment` / `FloorSlab` / `RoofItem` | `get_3d_mesh(level_manager=lm)` → dict `vertices`, `faces`, optional `color` (RGBA) | meshes + selection overlay |
| `WallOpening` (via `wall.openings`) | `get_3d_meshes(level_manager=lm)` → list of same dicts | openings |
| `LevelManager` | `levels` (each `.elevation`, `.name`), `get(name)` | floor planes, H-cut height, `_level_z_mm` |
| `ScaleManager` | `is_calibrated`, `pixels_per_mm` | `_scene_to_3d` |
| radiation result | `threshold`, `per_receiver_flux[entity]`, `per_receiver_mesh[entity]` (`vertices`, `faces`) | `show_radiation_heatmap` |
| `theme.detect()` | `bg_raised`, `text_primary`, `border_strong`, `btn_hover`, `text_secondary` | toolbar QSS, read once at construction |
| `theme.detect()` | `surface` | plotter background, read once at construction (I17) |

### 1.2 Signals

| Signal | Emitter | Connected by / to |
|---|---|---|
| `View3D.entitySelected(object)` | `_on_mouse_press` on a hit | MainWindow.__init__ → `prop_manager.show_properties` |
| `ViewCube.viewRequested(float, float)` | `ViewCube.mousePressEvent` on a hit zone | `View3D._build_ui` → `_on_viewcube_request` → `_set_view_preset` |
| `Model_Space.sceneModified` | scene | `View3D._connect_signals` → `request_rebuild` — the **only** model-change path to a 3D rebuild. MainWindow's own `sceneModified` → `_on_scene_modified` → `_refresh_all_views` debounce does **not** touch the 3D view (I6). |
| `Model_Space.selectionChanged` | scene | `View3D._connect_signals` → `_on_2d_selection_changed` |
| `Model_Space.radiationCancel` / `radiationConfirm` | emitted **by View3D** on the scene's behalf (Esc / Enter while `_radiation_selecting`) | MainWindow radiation flow |
| VTK `InteractionEvent`, `EndInteractionEvent` | interactor observers | `_sync_viewcube` |
| `ProjectBrowser.activate3DView()` | browser `3D Model` leaf (activation / context-menu Open) | MainWindow → `View3DTabController.open` (I3; `project-browser.md`) |
| `EmptyCanvasPlaceholder.open3DRequested` / `openPlanRequested` | placeholder quick buttons | MainWindow → `View3DTabController.open` / `_activate_plan_view(active level)` (I5) |
| `_CanvasTabBar.countChanged(int)` | canvas tab bar `tabInserted` / `tabRemoved` | MainWindow → `_on_canvas_count_changed` (I5) |

`cleanup()` disconnects the two scene connections (`sceneModified`,
`selectionChanged`) — I11.

## 2. Lifecycle (as-built)

### 2.1 Import & construction
- `main.py` does **not** import `view_3d` at module top (comment: "deferred —
  imports pyvista/VTK which is slow"). `main()` shows the splash, then does
  `global View3D; from firepro3d.view_3d import View3D` before
  `MainWindow(splash=...)`. Anything constructing `MainWindow` outside `main()`
  must inject `main.View3D` first — most MainWindow test files inject the real
  class; `stub_view3d` (conftest) injects a windowless stub (§8).
- `MainWindow.__init__` constructs exactly one `View3D` (right after
  `LevelManager`/`PlanViewManager`), then creates `central_tabs` with the custom
  `_CanvasTabBar` and `addTab(self.view_3d, view3d_tab.TAB_TITLE)` as the
  **first** tab (it gets the standard close dot from `tabInserted` like any
  tab). The canvas column hosts a `QStackedWidget` of `[central_tabs,
  EmptyCanvasPlaceholder]` (I5), and `self.view3d_tab = View3DTabController(
  central_tabs, view_3d, settings)` is built beside it.
- `View3D.__init__` → `_build_ui` (toolbar; `QtInteractor(self)`; background =
  theme `surface` (I17); `enable_depth_peeling(10)`; event filter on the
  interactor; VTK camera observers; `ViewCube(self._plotter)`; initial camera
  position `(10000,10000,10000)` → origin, Z-up, 45° view angle; static axes +
  hidden ground grid; section-cut state; 100 ms single-shot `_rebuild_timer`) →
  `_connect_signals`. Starts `_dirty = True`, `_first_build = True`, no pending
  render / selection / heatmap.
- Later in `__init__`, after the startup template apply,
  `view_3d.reset_for_project(scene.scale_manager)` seats the live scale manager
  (I9). The **last** statement of `__init__` is
  `view3d_tab.apply_startup_pref()` (I4), so a "closed" pref removes the tab
  before the window is ever shown. `MainWindow.showEvent`'s first show then
  opens `Plan: <DEFAULT_LEVEL>`, so a launch never shows the placeholder.
- There is **one** View3D per MainWindow for the process lifetime. It is never
  re-created or deleted; closing its tab only removes the tab (I1), and
  new/open project reuses it (same scene object — `Model_Space` is constructed
  once in `MainWindow.__init__`).

### 2.2 Tab presence (`View3DTabController`)
- **Close.** The 3D tab's close dot → `_CanvasTabBar.tabCloseClicked` →
  `MainWindow._on_tab_close_requested`, whose **first** check is
  `widget is self.view_3d` (identity, not title — I2) → `view3d_tab.close()` →
  `view_3d.clear_pick()`, `removeTab`, write `ui/view3d_open = False`. The widget
  is never `deleteLater()`-ed (the paper tab is the other keep-alive exemption).
- **Reopen.** `view3d_tab.open()` (Project Browser `3D Model` leaf via
  `activate3DView`, or the placeholder's **3D Model** button): if absent,
  `insertTab(0, view_3d, TAB_TITLE)`; always `setCurrentIndex(indexOf(view_3d))`;
  write `ui/view3d_open = True`. Idempotent — a repeat call only re-selects
  (the browser's known activation double-fire is harmless).
- **Startup.** `apply_startup_pref()` reads `ui/view3d_open` (default `True`);
  when `False` it runs `close(remember=False)` — the same path as a user close,
  minus the pref write.
- `_close_stale_view_tabs` (project new/load) removes only `Plan: `/`Elevation: `/
  `Detail: ` tabs — an open 3D tab is preserved, a closed one stays closed.

### 2.3 Rebuild triggers and visibility gating (I6)
- **Model change:** `sceneModified` → `request_rebuild()` sets `_dirty = True`
  and starts the 100 ms coalescing timer **only if visible** (and not already
  running). This is the only model-change trigger; `MainWindow._refresh_all_views`
  deliberately does not touch 3D, so a visible view rebuilds once per edit.
- **Timer:** `_do_rebuild` rebuilds only if still dirty **and** visible — a view
  hidden before the timer fired stays dirty until shown.
- **Show:** `showEvent` defers `_flush_pending` one event-loop turn
  (`QTimer.singleShot(0, …)`, keeping any render out of `showEvent` itself).
  `_flush_pending` (no-op if the plotter is closed or the view is hidden again)
  applies, in order: a pending heatmap show/clear; then if dirty → start the
  rebuild timer (the rebuild re-syncs the selection and renders); else a pending
  selection sync; else a pending render.
- **Direct calls:** toolbar **Refresh** and the context-menu Refresh / Hide /
  Show All call `rebuild()` directly (only reachable while visible).
  `delete_selected` does not rebuild itself — the scene's delete fires
  `sceneModified` → `request_rebuild`.

`rebuild()`: sets `_dirty = False`; returns if `_plotter is None` (post-cleanup
guard); with `suppress_rendering` runs all `_extract_*` (full clear-and-recreate
of every category — no incremental update) plus `_on_2d_selection_changed`;
re-applies the horizontal cut when H-Cut is on (I15); moves only `_orbit_center`
to the geometry centroid — the camera stays where the user left it (I13); on
`_first_build` only, `_fit_camera`; updates the "Nodes/Pipes" info label;
`_render()`. Heatmap overlay actors are held outside `_actors`, so a rebuild
leaves them in place.

### 2.4 Rendering only while visible (I6)
`_render()` is the only call site of `self._plotter.render()`: it renders when
visible, else sets `_render_pending` (no-op once the plotter is closed). While
hidden, `_on_2d_selection_changed` sets `_sel_pending` and returns before
touching VTK; `show_radiation_heatmap(result)` / `clear_radiation_heatmap()`
store `_pending_heatmap` (the result, or the `_HEATMAP_CLEAR` sentinel — last
request wins) and return. So scene edits, 2D selection changes, Escape and
heatmap show/clear trigger no rebuild and no render while the view is hidden
(tab closed or in the background). One nuance: `clear_pick()` (via Escape's
`cancel_interaction`, a tab close, or `reset_for_project`) still removes the
pick-highlight actors from the hidden renderer — an actor-list edit with no
render (guarded as "never rebuilds or renders" in
`tests/test_view3d_lifecycle.py`).

### 2.5 Teardown (I11)
- `cleanup()` (idempotent): stops `_rebuild_timer`; disconnects
  `sceneModified`→`request_rebuild` and `selectionChanged`→
  `_on_2d_selection_changed` (errors from an already-disconnected slot or a dead
  scene swallowed); `self._plotter.close()` (exceptions swallowed);
  `self._plotter = None`.
- `View3D.closeEvent` calls `cleanup()` (only reached if the View3D itself is
  closed as a top-level; child widgets don't get closeEvent).
- `MainWindow.closeEvent` → after the save prompt, `save_settings`,
  `_cleanup_autosave` → `if hasattr(self, "view_3d"): self.view_3d.cleanup()` →
  `super().closeEvent`. This is the only production call site.
- Post-cleanup safety: `rebuild`, `_render`, `clear_pick`, `_flush_pending` and
  `_on_2d_selection_changed` return early when `_plotter is None`; with the
  scene slots disconnected nothing scene-driven reaches the others.

### 2.6 removeTab / re-add
Empirical probe at the forge (Qt 6.9.0, PyQt6, a plain `QWidget` with `winId()`
forced native, offscreen): `QTabWidget.removeTab` does **not** reparent to
`None` — the page stays parented to the tab widget's internal `QStackedWidget`,
hidden, and re-inserting the same widget works. The build relies on this: a
closed View3D keeps its native VTK window, GL context, actors, camera, toggles
and heatmap; reopening shows it and `_flush_pending` applies the deferred work.
The `_on_tab_close_requested` comment now says so (D12). Close/reopen is guarded
on a real MainWindow + real View3D (`tests/test_view3d_tab_mainwindow.py`). A
genuine reparent (`setParent(None)` / to another parent) of the native GL child
is still untested and is never done. The **fullscreen-resize native-crash
class** still applies: headless tests must not drive real window-state changes
on a MainWindow with a real View3D (`main()` applies fullscreen after `show()`,
not in `showEvent`; `test_fullscreen_immersive.py` monkeypatches
`showFullScreen`).

## 3. Interaction (as-built)

- Event filter on the interactor owns the whole left-button cycle: press
  records position (and focuses the VTK widget); move ≥ `_CLICK_THRESHOLD` (5 px)
  = custom orbit around `_orbit_center` (0.3°/px, elevation clamped ±89.9°);
  release without drag = pick (`_on_mouse_press`). Double-click and `Leave` reset
  state. Middle-drag pan and right-drag dolly are VTK's default trackball.
  Wheel = custom zoom-to-cursor (`vtkWorldPointPicker`, fallback ray/focal-plane
  intersection; factor 0.85). `ContextMenu` → `_show_context_menu`. `KeyPress` →
  `_on_key_press`; `View3D.keyPressEvent` is a backup path.
- **Picking** (`_pick_at`): nearest projected node/pipe-midpoint within
  `PICK_TOLERANCE_PX/2` wins; else `vtkCellPicker` mapped through
  `_actor_to_entity` (walls, openings, slabs, roofs); else nearest point within
  full tolerance. Sprinklers, water supply, floors are not pickable as entities.
- **Selection model:** plain click → `scene.clearSelection()`,
  `_3d_selected = [hit]`, `hit.setSelected(True)`; Ctrl-click toggles; click on
  empty clears both. `_3d_selected` exists because "setSelected doesn't stick"
  for some items (e.g. off-level walls hidden in the plan). `entitySelected.emit(hit)`
  drives the Properties panel. The pick is **tab-scoped** (I7): MainWindow's
  Delete uses it only while the 3D tab is current; closing the 3D tab, Escape
  and project new/open/recovery drop it (`clear_pick`); switching tabs keeps it.
- **2D→3D sync:** `_on_2d_selection_changed` draws yellow node spheres, blue
  pipe overlay cylinders, and delegates walls/slabs/roofs to
  `_highlight_mesh_selection` (overlay meshes; base actors never recoloured;
  radiation overlays tinted for selected receivers).
- **Keys:** Esc → `cancel_interaction()` — the one Escape implementation shared
  with MainWindow (I12): reset orbit state, `clear_pick()` (drops `_3d_selected`
  + highlight/overlay actors), `scene.clearSelection()`, and if
  `_radiation_selecting` clear it and emit `radiationCancel`. Enter/Return while
  `_radiation_selecting` → `radiationConfirm`.
- **Context menu:** `build_entity_context_menu` with Hide (`_hide_items` +
  rebuild), Show All, Delete (`delete_selected`), Deselect
  (`cancel_interaction`), Fit, Refresh.
- **Delete** (`delete_selected`, I8): `clear_pick()` then
  `scene.delete_items(picked)` — the scene's single bulk-delete path (same
  rules as a 2D delete, one undo step); the resulting `sceneModified` requests
  the rebuild.
- **Toolbar:** Fit All, Ortho/Perspective, Refresh, H-Cut (checkable), Grid
  (checkable), Floors (checkable), info label.
- **ViewCube:** faces/edges/corners → `(elev, azim)` presets
  (`_CUBE_FACES/_EDGES/_CORNERS`); `_set_view_preset` fits to bounds then snaps
  angle; elevation 90 forces parallel projection. Positioned top-right in
  `_position_viewcube` on `View3D.resizeEvent`.

## 4. Public API consumed by the rest of the app

| Member | Caller (main.py) | Notes |
|---|---|---|
| `View3D(model_space, level_manager, scale_manager, parent=None)` | `MainWindow.__init__` | once |
| `entitySelected` | `MainWindow.__init__` | → `prop_manager.show_properties` |
| `reset_for_project(scale_manager)` | `MainWindow.__init__` (after the startup template apply), `new_file` (after the template apply), `_apply_loaded_file` (File→Open and crash recovery) | live `_sm`; `_first_build = True` (next shown rebuild re-fits); `clear_pick()`; `clear_radiation_heatmap()`; `request_rebuild()` (I9) |
| `cancel_interaction()` | `MainWindow._on_escape` | every Escape on any non-paper tab (I12) |
| `get_3d_selected()` | `_delete_if_not_editing` | consulted only while `central_tabs.currentWidget() is view_3d` (I7) |
| `delete_selected()` | `_delete_if_not_editing` | → `Model_Space.delete_items` (I8) |
| `show_radiation_heatmap(result)` | radiation compute flow | deferred while hidden (I10) |
| `clear_radiation_heatmap()` | `_clear_radiation`; `reset_for_project` | deferred while hidden |
| `cleanup()` | `MainWindow.closeEvent` | I11 |
| `clear_pick()` | `View3DTabController.close`; `reset_for_project`; `cancel_interaction` | I7 |
| `request_rebuild()` | `sceneModified` (View3D's own connection); `reset_for_project` | I6 — MainWindow does not call it |
| `rebuild()` | toolbar Refresh; context-menu Refresh / Hide / Show All | View3D-internal only; MainWindow no longer calls it |

The `stub_view3d` fixture's `_StubView3D` mirrors this surface (`cleanup`,
`rebuild`, `request_rebuild`, `get_3d_selected`, `delete_selected`,
`show_radiation_heatmap`, `clear_radiation_heatmap`, `cancel_interaction`,
`clear_pick`, `reset_for_project`, `entitySelected`) plus a `_plotter = None`
attribute; any new MainWindow→View3D call must be added to the stub or stubbed
MainWindow tests break (test-harness Invariant 3). `View3DTabController` needs
only `clear_pick()` from the widget it manages.

## 5. Rendering content (as-built summary)

Nodes: positions only (no glyphs; used for picking/bounds/floor extent).
Sprinklers: 40 mm sphere glyphs coloured by Orientation. Pipes: capped
cylinders merged per colour when count ≤ `MAX_CYLINDER_PIPES` (200), else one
line mesh whose width derives from the **first** pipe's diameter. Water supply:
60 mm sphere at Z=0. Construction (`_extract_geometry_2d`): intentionally clears
and returns (loose 2D primitives no longer live in the plan scene). Level
floors: translucent quads per level sized to the node extent + padding, with
edge outline and name label, hidden unless Floors is on; absent when there are
no nodes. Walls / slabs / roofs: `get_3d_mesh` meshes + feature-edge actors
(walls & slabs backface culling off; roofs use the mesh alpha). Openings:
`get_3d_meshes` per opening with the mesh alpha. Static: XYZ axes at origin
(500 mm) + labels; 5000 mm ground grid (1000 mm step) hidden by default.

## 6. Section cut (as-built)

H-Cut on: height = `levels[1].elevation` if ≥ 2 levels, else the default
3000 mm (no UI to change it); hides walls/openings/slabs/roofs/floors (and their
paired edge actors) whose `zmin ≥ cut`. Floor labels are not cut. Off:
everything visible, floors per the Floors toggle. `rebuild()` re-applies the cut
while H-Cut is on, so freshly created actors are cut too (I15).

## 7. Persisted vs in-memory state

**Persisted: one per-user UI preference.** `ui/view3d_open` (bool, default
`True`) in the app `QSettings`, owned by `view3d_tab.View3DTabController`
(written by `open()` / a user `close()`, read by `apply_startup_pref()` — I4).
Nothing else: `scene_io.py` contains no camera / 3D / view-tab keys;
`view_3d.py` and `view_cube.py` never touch `QSettings`; `MainWindow.save_settings`
stores no 3D state. The `.fpd` does not record which central tabs were open.

**In-memory state (survives a tab close/reopen — the widget is never destroyed;
would be lost only if it were recreated):**
- VTK camera: position, focal point, up, view angle, `parallel_projection`
  (and the Ortho/Perspective button text); `_orbit_center`;
- `_first_build` (a new widget would auto-fit again on first rebuild);
- ViewCube `_elevation`/`_azimuth` (re-derived from the camera by
  `_sync_viewcube`, so not independent);
- toggles: `_3d_grid_visible`, `_level_floors_visible`, `_h_cut_enabled`,
  `_h_cut_height_mm` + the checked state of the Grid/Floors/H-Cut buttons;
- `_3d_selected`; radiation overlay (`_radiation_meshes`, entity map, original
  colours) — the radiation result itself lives in MainWindow/report dock, so a
  recreated view could not redraw the heatmap without the caller re-sending it;
- the hidden-state deferral flags `_dirty`, `_render_pending`, `_sel_pending`,
  `_pending_heatmap`;
- all actors (rebuildable from the scene — not state).

**Project new/open/recovery (`reset_for_project`, I9):** resets `_sm`,
`_first_build` (camera re-fits on the next shown rebuild), the 3D pick and the
radiation overlay. Grid / Floors / H-Cut toggles and the projection mode keep
their values.

## 8. Test harness contact

- `tests/test_view_3d.py` — real View3D over a `_FakeScene(QGraphicsScene)`
  (`pv.OFF_SCREEN = True`); covers cleanup idempotence/closeEvent,
  rebuild-after-cleanup no-op, flux colours, `_is_visible`, `_scene_to_3d`,
  `_level_z_mm`, camera angle round-trip, bounds, actor bookkeeping, dirty flag
  (`request_rebuild`), empty rebuild, info label, `get_3d_selected`.
- `tests/test_view3d_lifecycle.py` — real View3D over a **real** `Model_Space`:
  one-undo 3D delete (I8), idle-while-hidden + flush on show (I6/I10),
  `reset_for_project` (I9), `cancel_interaction`, no slot after `cleanup` (I11),
  camera kept across rebuild (I13), H-Cut survives rebuild (I15), hidden wall
  hides its openings (I14), pipe pick ref alignment (I16), `set_mode` no-view
  refusal (I5), plotter background = `surface` pixel sample (I17).
- `tests/test_view3d_tab_mainwindow.py` — real MainWindow + real View3D (pops a
  real window; exposure is needed for `isVisible()`): close/reopen + rebuild
  counts, pref across windows, D8/I7 stale-pick delete, empty-canvas refusals and
  quick buttons, placeholder rail height, project reseat (new/open/startup),
  one rebuild per visible edit, ribbon Delete / paste / offset / radiation
  refusals, closing the last view cancels a radiation pick, placeholder plan
  label. Its fixture clears the plan selection before `close()` — see
  `test-harness.md` (MainWindow-teardown selection family).
- `tests/test_view3d_tab_controller.py`, `tests/test_canvas_placeholder.py`
  (under the live app QSS + font), `tests/test_project_browser_3d.py` — unit
  guards for the controller, the placeholder and the browser leaf.
- Not covered: picking by mouse, ViewCube interaction.
- `stub_view3d` (opt-in, `tests/conftest.py`) — used only by
  `tests/test_view3d_stub.py`; most other MainWindow test files inject the
  **real** View3D into `main` before building a MainWindow.
- `QT_QPA_PLATFORM=offscreen` is not viable (VTK needs a GL surface).
  Native-crash family "VTK-MainWindow native-child-window" (test-harness.md
  "Known native-crash families"): mitigated by the stub and by `cleanup()` on
  close. Full-suite accumulation of VTK/GL contexts is environmental; see the
  test-harness spec for the chunked-run gate.

## 9. Divergences / hazards ledger (forge-time history; dispositions in §10)

Findings and evidence are as recorded at the forge (`35d3c17`) — kept verbatim
as history; they no longer describe the code unless Status says OPEN. Status
re-verified at `f1d8151`.

| # | Finding | Evidence | Severity (guess) | Status @ `f1d8151` |
|---|---|---|---|---|
| D1 | **Stale `ScaleManager`.** View3D captures `scene.scale_manager` at construction; `scene_io` replaces `scene.scale_manager` on load and on new/clear. MainWindow re-seeds other consumers (block editors) but never View3D. A loaded project with `pixels_per_mm ≠` the construction-time manager's value would map 3D coordinates with the wrong ppm. | `View3D.__init__` `self._sm`; `scene_io.py` `self.scale_manager = ScaleManager...`; no `view_3d._sm` write in main.py | medium (latent; most projects ppm = 1) | RESOLVED I9 (`reset_for_project` at startup, new, open, recovery) |
| D2 | **Double / ungated rebuild.** MainWindow `_refresh_all_views` calls `rebuild()` on every scene edit regardless of tab visibility, defeating `_schedule_rebuild`'s gate; when visible, each edit rebuilds twice. Full clear-and-recreate of every actor each time. | `_schedule_rebuild`, `showEvent`; `MainWindow._on_scene_modified`/`_refresh_all_views` | medium (perf on large models; renders into a hidden native window) | RESOLVED I6 (`_refresh_all_views` no longer touches 3D; `request_rebuild` sole path) |
| D3 | **Renders while hidden** on every 2D selection change, every Escape, heatmap show/clear (§2.4). Hazard unproven. | `_on_2d_selection_changed`, `_on_escape` | low–unknown | RESOLVED I6 / I10 (`_render` + hidden deferral) |
| D4 | **Tab protection is title-string based** (`tabText == "3D Model"`) plus a one-shot close-button strip at construction; no widget-identity check. Renaming the tab silently makes it closable (and `_on_tab_close_requested` would then `deleteLater()` it — it only exempts `paper_space_widget`). | `_on_tab_close_requested` | medium if the title ever changes | RESOLVED I2 (`widget is self.view_3d`) |
| D5 | **Post-cleanup slots unguarded.** `cleanup()` leaves scene signal connections and the rebuild timer alive; only `rebuild()` checks `_plotter is None`. A `selectionChanged` after cleanup → `_clear_actors` → `None.renderer` AttributeError from a Qt slot (qFatal in tests; logged by `install_excepthook` in production). Trigger during teardown not reproduced. | `cleanup`, `_on_2d_selection_changed`, `_clear_actors` | medium (crash class already seen once for `rebuild`) | RESOLVED I11 |
| D6 | **Private-method call:** MainWindow calls `view_3d._on_escape()`; View3D in turn reads/writes the scene's private `_radiation_selecting` and calls `_hide_items`/`_show_all_hidden`, `_walls`/`_floor_slabs`/`_roofs`. Also `_on_key_press` Esc and `_on_escape` are two diverging Esc implementations (only the latter clears `_3d_selected`). | `MainWindow._on_escape`; `View3D._on_key_press`/`_on_escape` | low (coupling) | PARTIAL — RESOLVED I12 for the MainWindow private call and the two diverging Escapes (`cancel_interaction`); View3D's reads/writes of scene privates (`_radiation_selecting`, `_hide_items`, `_walls`/`_floor_slabs`/`_roofs`) remain — not ratified |
| D7 | **Camera re-centred on every rebuild** (focal point snapped to geometry centroid), so any user pan is discarded on the next edit. First build auto-fits; later project loads do not. | `rebuild()` bounds block; `_first_build` | low–medium (UX) | RESOLVED I13 (+ re-fit on project load, I9) |
| D8 | **Stale `_3d_selected` hijacks Delete.** `_3d_selected` is cleared only by Esc-via-MainWindow, empty-click, or `delete_selected`; not by 2D selection changes or project new/open. `MainWindow._delete_if_not_editing` checks `get_3d_selected()` first, so after a 3D pick, a later 2D selection + Delete deletes the 3D-picked item(s) instead (code-read, not reproduced). Refs can also point at items of a previous project / invalidated by undo restore. | `_on_mouse_press`, `_on_2d_selection_changed`, `_delete_if_not_editing` | **high** (wrong-item delete) — verify live | RESOLVED I7 (guarded on a real MainWindow) |
| D9 | **Openings ignore hide.** `_extract_openings` does not apply `_is_visible` to the opening or its wall, so a hidden wall's openings still render. | `_extract_openings` | low | RESOLVED I14 |
| D10 | **H-Cut lost on rebuild.** New actors from `rebuild()` are visible; `_h_cut_enabled` stays True and the button stays checked, but nothing is cut until toggled. Cut height not user-settable. | `rebuild`, `_toggle_horizontal_cut` | low–medium | RESOLVED I15 (cut height still not user-settable — out of scope) |
| D11 | **Pipe pick index mismatch.** `_pipe_refs` = all visible pipes; `_pipe_midpoints_3d` skips pipes with a `None` node, so `refs[i]` can be the wrong pipe once any pipe is skipped. | `_extract_pipes`, `_nearest_point_entity` | low | RESOLVED I16 |
| D12 | **Comment/spec drift:** `_on_tab_close_requested` says removeTab "reparents it out" — on Qt 6.9 it stays parented to the internal `QStackedWidget`, hidden (probe §2.6). `view-relationships.md` says `View3D` "(vispy/PyVista)" and "no editing", but vispy is gone and View3D can delete walls/slabs/roofs/other items and hide/show items. `ViewCube._build_rotation` docstring cites "vispy TurntableCamera" and a Y-vertical convention while the camera is Z-up (the mapping is internal to the cube; handedness of FRONT/N labels vs. world not verified by observation). Memory note `project_vtk_plotter_test_accumulation` is linked from other notes but does not exist. | as cited | low (doc) | PARTIAL — `_on_tab_close_requested` comment and `view-relationships.md` (PyVista/VTK; delete/hide) reconciled; `ViewCube._build_rotation` docstring still cites vispy (code — filed); the missing memory note is outside the repo |
| D13 | **`delete_selected` mirrors a subset of `Model_Space._bulk_delete`** (walls/slabs/roofs handled inline, skipping `_remove_item_from_lists`); other types fall back to per-item `setSelected + delete_selected_items()`, which pushes its own undo state — plus the final `push_undo_state()` → multiple undo entries for one delete. A mirror waiting to drift. | `View3D.delete_selected` vs `Model_Space._bulk_delete` | medium | RESOLVED I8 (`Model_Space.delete_items`) |
| D14 | Hygiene: toolbar buttons Fit All / Ortho / Refresh have no tooltips; colours and tolerances are module constants rather than `constants.py`/theme tokens; theme read once (no live re-theme); `QShortcut`, `QKeySequence`, `QMenu` imported unused; `FT_TO_MM`, `CIRCLE_SEGMENTS`, `COL_NODE`, `COL_SPRINKLER`, `COL_CONSTR` unused in the module (tests import some). | `_build_ui`, module header | low | OPEN (§10.6) — Fit All / Ortho / Refresh still lack tooltips; unused imports remain |
| D15 | **No way back if closed.** Nothing can re-open a 3D tab (no browser entry / action) — relevant only if the tab becomes closable. | §2.2 | n/a today | RESOLVED I3 (+ I5 placeholder quick button) |
| D16 | Pipe line-fallback width uses only the first pipe's diameter; water supply always drawn at Z=0; floor planes absent with no nodes and sized to nodes only (ignore walls/slabs). | `_extract_pipes`, `_extract_water_supply`, `_extract_level_floors` | low | OPEN (§10.6) — unchanged |

## 10. As-intended (ratified — 2026-09-30 grill, FP4 orphan gate + closable-tab Phase 2)

Each item below was ratified by the user in the grill; build status is tracked
by the Acceptance Criteria. Where this section and §1–§9 disagree, **this
section is the contract** — §1–§9 describe the code as it stood at the forge.

### 10.1 Tab lifecycle
- **I1 Closable, close = hide.** The "3D Model" canvas tab carries the same
  close dot as plan tabs. Closing removes the tab but keeps the one `View3D`
  widget and its VTK render window alive (the Paper-tab singleton pattern) —
  camera, toggles and any heatmap survive; no GL context is created or
  destroyed mid-session. There is exactly one 3D view.
- **I2 Identity, not title.** Every protection / singleton check keys on the
  widget (`is self.view_3d`), never on the tab text (resolves D4). The 3D
  widget is never `deleteLater()`-ed by a tab close.
- **I3 Reopen.** A top-level **`3D Model`** leaf sits **above** `2D Model` in the
  Project Browser (governed by `project-browser.md`). Activation (double-click /
  Enter) or its context-menu **Open** re-inserts the tab at **index 0**
  (leftmost) and makes it current; if already open it just becomes current.
  Not a drag source (no 3D paper viewports).
- **I4 Remembered as a user preference.** Open/closed persists in **QSettings**
  (per user, not per project) across launches and project new/open. The `.fpd`
  stays free of UI layout. Startup and project new/open still open the active
  level's plan, as today.
- **I5 Empty canvas allowed.** All canvas tabs may be closed. The empty canvas
  shows a placeholder: a centred message ("No views open" + "Open a view from
  the Project Browser") and two quick buttons — **3D Model** and
  **Plan: \<active level\>** (visual mockup-gated before build). With no view
  open, authoring/modify tools and Delete are refused with a status-bar hint;
  document-level actions (undo/redo, save/open, settings, managers, analyses)
  still work. Tool behaviour while 3D/Paper is current is unchanged by this
  contract (checked; follow-up if it misbehaves).
  - **I5a Radiation is an interactive tool** *(ratified at build, 2026-09-30)*.
    Starting the thermal-radiation pick on an empty canvas is refused with the
    same hint; closing the last canvas tab while a radiation pick is in
    progress cancels the pick.
  - **I5b A Block Editor tab counts as a view** *(ratified at build,
    2026-09-30)*. "No view open" means the canvas tab count is zero; a canvas
    whose only tab is a Block Editor keeps the plan scene's `view_available`
    `True`. Whether plan tools should arm while a non-plan tab is current is a
    filed follow-up.
  - **Mechanism (as-built).** The refusal state is `Model_Space.view_available`
    (default `True`, set by MainWindow from the canvas tab count). The hint text
    is `model_space.NO_VIEW_HINT` — one home. Refusal homes: `Model_Space.set_mode`
    (any mode but `None`/`"select"`), `ModifyToolsController.start` (every
    Edit/Modify entry, ribbon and shortcuts), `MainWindow._delete_if_not_editing`
    (the one Delete chokepoint — the ribbon Delete routes through it), and the
    radiation start. When the count drops to zero MainWindow shows the
    placeholder, cancels a radiation pick, disarms to `select`, then clears
    `view_available`. Placeholder visual values are the mockup-approved
    `theme.M.EMPTY_CANVAS_*` tokens (`canvas_placeholder.py`); its rail height
    is taken from the canvas tab bar's `sizeHint` and its pane paints `surface`
    (the plan canvas colour — user change at the 2026-09-30 smoke, from the
    mockup's `ground`).

### 10.2 Idle while not visible
- **I6** While the 3D view is not visible (tab closed **or** open in the
  background) there is no rebuild and no render (removing stale highlight
  actors from the unrendered renderer is allowed — §2.4) — scene edits,
  2D selection changes, Escape and heatmap show/clear only update state and
  mark it dirty. On becoming visible it rebuilds **once**, showing the current
  scene and the current 2D selection highlight. A visible view rebuilds once
  per edit, not twice (resolves D2/D3).

### 10.3 Selection and delete
- **I7 3D pick is tab-scoped.** The separate 3D pick (`_3d_selected`) stays, but
  Delete acts on it only while the 3D tab is current. Closing the 3D tab and
  project new/open clear it; merely switching tabs keeps it (resolves D8).
- **I8 One delete path.** Delete from 3D routes through the scene's own delete
  path — same rules as 2D, **one undo step** (resolves D13). 3D delete/hide are
  ratified as intended (supersedes `view-relationships.md`'s "no editing").
  Unifying 3D pick with the scene selection is a filed `[type:design]` follow-up.

### 10.4 Project load
- **I9** Project new/open **re-fits the camera** to the loaded model (as on a
  fresh launch) and re-syncs View3D to the live `scene.scale_manager`
  (resolves D1). Grid/Floors/H-Cut toggles keep their values. The camera is
  not persisted (per-project camera save is a filed follow-up).
- **I10** A radiation heatmap produced while the 3D tab is closed is applied
  silently to the hidden view and is visible on reopen; no tab switch.

### 10.5 Ledger fixes ratified in scope
- **I11** `cleanup()` also stops the rebuild timer and disconnects scene signals;
  no slot runs against a closed plotter (D5).
- **I12** MainWindow uses a public Escape API, not `_on_escape` (D6).
- **I13** Rebuilds keep the user's camera — no re-centre (D7).
- **I14** Openings honour hide, with their host wall (D9).
- **I15** H-Cut stays applied across rebuilds (D10); user-set cut height is
  out of scope.
- **I16** A 3D pick on a pipe selects that pipe even when other pipes were
  skipped for missing nodes (D11).

### 10.5a Appearance
- **I17 One canvas surface** *(user, smoke 2026-09-30)*. The 3D plotter
  background is the theme `surface` token — the same colour the plan canvas
  viewport paints — so every canvas tab reads as one surface. Read once at
  construction (no live re-theme, like the toolbar — D14).

### 10.6 Not in scope (recorded, not ratified)
D12 doc drift is reconciled at Account (residual code docstring filed — §9).
D14 hygiene and D16 extraction quirks stay as-built pending their own tasks.

## Acceptance Criteria
- [x] Every as-built claim re-verified against HEAD when the grill opened.
- [x] Each D-row ratified, scheduled (§10) or recorded out of scope (§10.6).
- [x] I1–I17 (incl. I5a/I5b) built, each guarded (§8 test files); `status`
      `current` at `f1d8151`.

## Verification Checklist
- [x] Grep `view_3d`/`View3D` across `main.py`, `firepro3d/`, `tests/` still
      matches §4 (no new callers missing from the stub) — re-verified at `f1d8151`.
- [x] `tests/test_view_3d.py` and `tests/test_view3d_stub.py` green (Account
      re-run at `f1d8151`, one process each, exit 0).
- [x] Any close/re-open work adds a live smoke (VTK is not headless-testable at
      MainWindow level) — closable-tab build live-smoked 2026-09-30 (the I17
      background change came from that smoke).
