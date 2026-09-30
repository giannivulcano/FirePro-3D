---
status: partial
last-verified: 2026-09-30
verified-commit: a835d44
applies-to:
  - firepro3d/view_3d.py
  - firepro3d/view_cube.py
  - main.py (View3D deferred import in main(); construction + "3D Model" tab in MainWindow.__init__; _on_tab_close_requested / _close_stale_view_tabs protection; _refresh_all_views; _on_escape; _delete_if_not_editing; radiation heatmap calls; closeEvent cleanup)
  - tests/conftest.py (stub_view3d fixture)
source-tasks: ["/todo 2026-09-30 orphan gate — 3D view forged before the closable-3D-tab work touches it"]
---

# 3D View — Design Spec (as-built + ratified as-intended)

**Status note.** §1–§9 are **as-built** (code-read at `35d3c17`, re-checked
unchanged at `a835d44`). §10 is the **as-intended contract**, ratified in the
2026-09-30 grill; it overrides §1–§9 wherever they differ. The §9 ledger's
"Disposition" is in §10 (I-numbers) — rows not named there stay as-built.

**Adjacent specs:** `view-relationships.md` (view taxonomy; 3D is a read-only
projection, §3; its open question 5 "3D rebuild triggers" is answered by §4 here),
`test-harness.md` (Invariant 3 View3D stub; VTK-MainWindow native-crash family),
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
  `self.level_mgr`, `self.scene.scale_manager` **captured once** (see D1).
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
| `Model_Space` | private lists `_walls`, `_floor_slabs`, `_roofs` (`getattr`) | `_extract_walls/_openings/_floor_slabs/_roofs`, `delete_selected` |
| `Model_Space` | `selectedItems()`, `clearSelection()` | selection sync |
| `Model_Space` | `_radiation_selecting` (private flag, read **and written**), `radiationCancel`, `radiationConfirm` signals | `_on_key_press`, `_on_escape` |
| `Model_Space` | `_hide_items(items)`, `_show_all_hidden()` (private) | context menu |
| `Model_Space` | `delete_selected_items()`, `push_undo_state()`, `removeItem()` | `delete_selected` |
| `Node` | `scenePos()`, `z_pos`, `has_sprinkler()`, `sprinkler._properties["Orientation"]["value"]` | positions, sprinkler colour (Pendent red / Sidewall green / else blue) |
| `Pipe` | `node1`, `node2`, `_properties["Colour"]["value"]`, `_properties["Diameter"]["value"]` | cylinder colour/radius |
| any item | `_display_overrides.get("visible")` (via `_is_visible`) | hide filter (not applied to openings — D9) |
| `WallSegment` / `FloorSlab` / `RoofItem` | `get_3d_mesh(level_manager=lm)` → dict `vertices`, `faces`, optional `color` (RGBA) | meshes + selection overlay |
| `WallOpening` (via `wall.openings`) | `get_3d_meshes(level_manager=lm)` → list of same dicts | openings |
| `LevelManager` | `levels` (each `.elevation`, `.name`), `get(name)` | floor planes, H-cut height, `_level_z_mm` |
| `ScaleManager` | `is_calibrated`, `pixels_per_mm` | `_scene_to_3d` |
| radiation result | `threshold`, `per_receiver_flux[entity]`, `per_receiver_mesh[entity]` (`vertices`, `faces`) | `show_radiation_heatmap` |
| `theme.detect()` | `bg_raised`, `text_primary`, `border_strong`, `btn_hover`, `text_secondary` | toolbar QSS, read once at construction |

### 1.2 Signals

| Signal | Emitter | Connected by / to |
|---|---|---|
| `View3D.entitySelected(object)` | `_on_mouse_press` on a hit | MainWindow.__init__ → `prop_manager.show_properties` |
| `ViewCube.viewRequested(float, float)` | `ViewCube.mousePressEvent` on a hit zone | `View3D._build_ui` → `_on_viewcube_request` → `_set_view_preset` |
| `Model_Space.sceneModified` | scene | `View3D._connect_signals` → `_schedule_rebuild`; **also** MainWindow → `_on_scene_modified` → `_refresh_all_views` → `view_3d.rebuild()` (D2) |
| `Model_Space.selectionChanged` | scene | `View3D._connect_signals` → `_on_2d_selection_changed` |
| `Model_Space.radiationCancel` / `radiationConfirm` | emitted **by View3D** on the scene's behalf (Esc / Enter while `_radiation_selecting`) | MainWindow radiation flow |
| VTK `InteractionEvent`, `EndInteractionEvent` | interactor observers | `_sync_viewcube` |

No signal is ever disconnected (not in `cleanup()` either — D5).

## 2. Lifecycle (as-built)

### 2.1 Import & construction
- `main.py` does **not** import `view_3d` at module top (comment: "deferred —
  imports pyvista/VTK which is slow"). `main()` shows the splash, then does
  `global View3D; from firepro3d.view_3d import View3D` before
  `MainWindow(splash=...)`. Anything constructing `MainWindow` outside `main()`
  must inject `main.View3D` first — 35 test files do so with the real class;
  `stub_view3d` (conftest) injects a windowless stub (§8).
- `MainWindow.__init__` constructs exactly one `View3D` (right after
  `LevelManager`/`PlanViewManager`), then creates `central_tabs` with the custom
  `_CanvasTabBar` and `addTab(self.view_3d, "3D Model")` as the **first** tab.
- `View3D.__init__` → `_build_ui` (toolbar; `QtInteractor(self)`; background
  `(0.12,0.12,0.14)`; `enable_depth_peeling(10)`; event filter on the interactor;
  VTK camera observers; `ViewCube(self._plotter)`; initial camera position
  `(10000,10000,10000)` → origin, Z-up, 45° view angle; static axes + hidden
  ground grid; section-cut state; 100 ms single-shot `_rebuild_timer`) →
  `_connect_signals`. Starts `_dirty = True`, `_first_build = True`.
- There is **one** View3D per MainWindow for the process lifetime. It is never
  re-created; new/open project reuses it (same scene object — `Model_Space` is
  constructed once in `MainWindow.__init__`).

### 2.2 Tab protection
- Immediately after `addTab`, `MainWindow.__init__` strips the close button of
  every tab then present (only "3D Model") via `setTabButton(..., None)`.
- `_on_tab_close_requested` early-returns when `tabText(index) == "3D Model"`
  (title-string check).
- `_close_stale_view_tabs` (project new/load) removes only `Plan: `/`Elevation: `/
  `Detail: ` tabs — the 3D tab is preserved.
- Neither the Project Browser nor any menu/ribbon action can open or re-add a 3D
  tab: there is no 3D entry in `project_browser.py` and no `insertTab`/`addTab`
  of `view_3d` besides the constructor. **Today `view_3d` is never removed from
  `central_tabs`.**

### 2.3 Rebuild triggers and visibility gating
Three paths reach `rebuild()`:

1. **View-internal (gated):** `sceneModified` → `_schedule_rebuild` sets
   `_dirty = True` and starts the 100 ms timer **only if `self.isVisible()`**.
   `showEvent` starts the timer if `_dirty`. `_do_rebuild` skips when not dirty.
   Intended effect: edits while the tab is hidden defer to the next show.
2. **MainWindow (ungated):** `sceneModified` → `_on_scene_modified` → 200 ms
   `_view_refresh_timer` → `_refresh_all_views` → `self.view_3d.rebuild()`
   **unconditionally** (only `hasattr` checks). So every scene edit rebuilds 3D
   ~200 ms later even while the 3D tab is hidden, and while it is visible the
   edit rebuilds **twice** (100 ms internal + 200 ms external). Path 1's gating
   is effectively dead (D2).
3. **Direct calls:** toolbar "Refresh", context-menu Refresh / Hide / Show All,
   `delete_selected` (after `push_undo_state`, which itself fires
   `sceneModified` → path 2 again).

`rebuild()`: sets `_dirty = False`; returns if `_plotter is None` (post-cleanup
guard, added for the debounced-refresh-after-close crash); with
`suppress_rendering` runs all `_extract_*` (full clear-and-recreate of every
category — no incremental update) plus `_on_2d_selection_changed`; re-centres
the camera focal point on the geometry centroid **keeping direction and
distance** (every rebuild — D7); on `_first_build` only, `_fit_camera`; updates
the "Nodes/Pipes" info label; `render()`.

### 2.4 Renders that ignore visibility
Besides path 2, these call `self._plotter.render()` regardless of whether the
tab is shown: `_on_2d_selection_changed` (every 2D selection change, via the
view's own `selectionChanged` connection), `_highlight_mesh_selection`,
`_on_escape` (called by MainWindow on **every** Escape on any tab),
`show_radiation_heatmap`, `clear_radiation_heatmap`. Whether rendering a hidden
native VTK window is itself harmful is **not established** (no repro, no guard,
no comment claims it). Known latent raiser (memory, uncaptured): an exception in
pyvistaqt `QVTKRenderWindowInteractor.timerEvent`.

### 2.5 Teardown
- `cleanup()` (idempotent): `self._plotter.close()` (exceptions swallowed), then
  `self._plotter = None`. It does **not** stop `_rebuild_timer`, disconnect the
  scene signals, clear `_actors`, or touch `_vtk_widget`/`_view_cube`.
- `View3D.closeEvent` calls `cleanup()` (only reached if the View3D itself is
  closed as a top-level; child widgets don't get closeEvent).
- `MainWindow.closeEvent` → after the save prompt, `save_settings`,
  `_cleanup_autosave` → `if hasattr(self, "view_3d"): self.view_3d.cleanup()` →
  `super().closeEvent`. This is the only production call site.
- Post-cleanup safety: only `rebuild()` is guarded. `_on_2d_selection_changed`,
  `_on_escape`, `delete_selected`, `show/clear_radiation_heatmap` and the toolbar
  slots dereference `self._plotter` unguarded (D5).

### 2.6 removeTab / re-add — what would happen today
Not reachable in the shipped app (§2.2). Empirical probe (Qt 6.9.0, PyQt6, a
plain `QWidget` with `winId()` forced native, offscreen; **not** a real
QtInteractor): `QTabWidget.removeTab` does **not** reparent to `None` — the page
stays parented to the tab widget's internal `QStackedWidget`, is hidden
(`isHidden() == True`), and `addTab` of the same widget re-inserts it fine. The
comment in `_on_tab_close_requested` ("removeTab reparents it out") is therefore
inaccurate on this Qt version (D12). Consequences for View3D if it were removed
and re-added, by code reading only (unverified live):
- the native VTK window would be hidden, not destroyed; the GL context,
  actors, camera and toggles survive; `showEvent` on re-add starts the dirty
  rebuild;
- MainWindow path 2 would keep rebuilding/rendering the hidden widget;
- no code anywhere guards a VTK render-window reparent. The only recorded VTK
  resize/state hazard is the **fullscreen-resize native-crash class**: headless
  tests must not drive real window-state changes on a MainWindow with a real
  View3D (`main.py restore_settings` comment; `main()` applies fullscreen after
  `show()`, not in `showEvent`; `test_fullscreen_immersive.py` monkeypatches
  `showFullScreen`). A genuine reparent (`setParent(None)` / to another parent)
  of a native GL child is untested territory.

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
  for some items. `entitySelected.emit(hit)` drives the Properties panel.
- **2D→3D sync:** `_on_2d_selection_changed` draws yellow node spheres, blue
  pipe overlay cylinders, and delegates walls/slabs/roofs to
  `_highlight_mesh_selection` (overlay meshes; base actors never recoloured;
  radiation overlays tinted for selected receivers).
- **Keys:** Esc → reset orbit, clear highlight actors, `scene.clearSelection()`,
  and if `_radiation_selecting` clear it and emit `radiationCancel` (note: does
  **not** clear `_3d_selected`, unlike `_on_escape`). Enter/Return while
  `_radiation_selecting` → `radiationConfirm`.
- **Context menu:** `build_entity_context_menu` with Hide (`_hide_items` +
  rebuild), Show All, Delete (`delete_selected`), Deselect (`_on_escape`), Fit,
  Refresh.
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
| `rebuild()` | `_refresh_all_views` | ungated (D2) |
| `_on_escape()` (**private**) | `MainWindow._on_escape` | every Escape on any non-paper tab (D6) |
| `get_3d_selected()` | `_delete_if_not_editing` | checked **before** the 2D selection (D8) |
| `delete_selected()` | `_delete_if_not_editing` | |
| `show_radiation_heatmap(result)` | radiation compute flow | |
| `clear_radiation_heatmap()` | `_clear_radiation` | |
| `cleanup()` | `MainWindow.closeEvent` | |

The `stub_view3d` fixture's `_StubView3D` mirrors exactly this surface plus a
`_plotter = None` attribute; any new MainWindow→View3D call must be added to the
stub or stubbed MainWindow tests break (test-harness Invariant 3).

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
everything visible, floors per the Floors toggle. The cut is **not re-applied by
`rebuild()`** (D10).

## 7. Persisted vs in-memory state

**Persisted: nothing.** `scene_io.py` contains no camera / 3D / view-tab keys;
`view_3d.py` and `view_cube.py` never touch `QSettings`; `MainWindow.save_settings`
stores no 3D state (it saves window geometry/state, dock visibilities,
templates). The `.fpd` does not record which central tabs were open.

**In-memory state lost if the widget were destroyed and recreated:**
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
- all actors (rebuildable from the scene — not state).

**State that survives project new/open today (never reset):** camera (no
re-fit — `_first_build` is already `False`), toggles, H-cut, radiation overlay
if not cleared, and `_3d_selected` refs to items of the previous project (D8).

## 8. Test harness contact

- `tests/test_view_3d.py` — the only real-View3D unit coverage; sets
  `pv.OFF_SCREEN = True`, uses a `_FakeScene(QGraphicsScene)` with the needed
  signals; covers cleanup idempotence/closeEvent, rebuild-after-cleanup no-op,
  flux colours, `_is_visible`, `_scene_to_3d`, `_level_z_mm`, camera angle
  round-trip, bounds, actor bookkeeping, dirty flag, empty rebuild, info label,
  `get_3d_selected`. No test covers `_schedule_rebuild`'s visibility gate
  against MainWindow's ungated path, picking, ViewCube, or section cut.
- `stub_view3d` (opt-in, `tests/conftest.py`) — used only by
  `tests/test_view3d_stub.py`; 35 other test files inject the **real** View3D
  into `main` before building a MainWindow.
- `QT_QPA_PLATFORM=offscreen` is not viable (VTK needs a GL surface).
  Native-crash family "VTK-MainWindow native-child-window" (test-harness.md
  "Known native-crash families"): mitigated by the stub and by `cleanup()` on
  close. Full-suite accumulation of VTK/GL contexts is environmental; see the
  test-harness spec for the chunked-run gate.

## 9. Divergences / hazards ledger (as-built; dispositions in §10)

| # | Finding | Evidence | Severity (guess) |
|---|---|---|---|
| D1 | **Stale `ScaleManager`.** View3D captures `scene.scale_manager` at construction; `scene_io` replaces `scene.scale_manager` on load and on new/clear. MainWindow re-seeds other consumers (block editors) but never View3D. A loaded project with `pixels_per_mm ≠` the construction-time manager's value would map 3D coordinates with the wrong ppm. | `View3D.__init__` `self._sm`; `scene_io.py` `self.scale_manager = ScaleManager...`; no `view_3d._sm` write in main.py | medium (latent; most projects ppm = 1) |
| D2 | **Double / ungated rebuild.** MainWindow `_refresh_all_views` calls `rebuild()` on every scene edit regardless of tab visibility, defeating `_schedule_rebuild`'s gate; when visible, each edit rebuilds twice. Full clear-and-recreate of every actor each time. | `_schedule_rebuild`, `showEvent`; `MainWindow._on_scene_modified`/`_refresh_all_views` | medium (perf on large models; renders into a hidden native window) |
| D3 | **Renders while hidden** on every 2D selection change, every Escape, heatmap show/clear (§2.4). Hazard unproven. | `_on_2d_selection_changed`, `_on_escape` | low–unknown |
| D4 | **Tab protection is title-string based** (`tabText == "3D Model"`) plus a one-shot close-button strip at construction; no widget-identity check. Renaming the tab silently makes it closable (and `_on_tab_close_requested` would then `deleteLater()` it — it only exempts `paper_space_widget`). | `_on_tab_close_requested` | medium if the title ever changes |
| D5 | **Post-cleanup slots unguarded.** `cleanup()` leaves scene signal connections and the rebuild timer alive; only `rebuild()` checks `_plotter is None`. A `selectionChanged` after cleanup → `_clear_actors` → `None.renderer` AttributeError from a Qt slot (qFatal in tests; logged by `install_excepthook` in production). Trigger during teardown not reproduced. | `cleanup`, `_on_2d_selection_changed`, `_clear_actors` | medium (crash class already seen once for `rebuild`) |
| D6 | **Private-method call:** MainWindow calls `view_3d._on_escape()`; View3D in turn reads/writes the scene's private `_radiation_selecting` and calls `_hide_items`/`_show_all_hidden`, `_walls`/`_floor_slabs`/`_roofs`. Also `_on_key_press` Esc and `_on_escape` are two diverging Esc implementations (only the latter clears `_3d_selected`). | `MainWindow._on_escape`; `View3D._on_key_press`/`_on_escape` | low (coupling) |
| D7 | **Camera re-centred on every rebuild** (focal point snapped to geometry centroid), so any user pan is discarded on the next edit. First build auto-fits; later project loads do not. | `rebuild()` bounds block; `_first_build` | low–medium (UX) |
| D8 | **Stale `_3d_selected` hijacks Delete.** `_3d_selected` is cleared only by Esc-via-MainWindow, empty-click, or `delete_selected`; not by 2D selection changes or project new/open. `MainWindow._delete_if_not_editing` checks `get_3d_selected()` first, so after a 3D pick, a later 2D selection + Delete deletes the 3D-picked item(s) instead (code-read, not reproduced). Refs can also point at items of a previous project / invalidated by undo restore. | `_on_mouse_press`, `_on_2d_selection_changed`, `_delete_if_not_editing` | **high** (wrong-item delete) — verify live |
| D9 | **Openings ignore hide.** `_extract_openings` does not apply `_is_visible` to the opening or its wall, so a hidden wall's openings still render. | `_extract_openings` | low |
| D10 | **H-Cut lost on rebuild.** New actors from `rebuild()` are visible; `_h_cut_enabled` stays True and the button stays checked, but nothing is cut until toggled. Cut height not user-settable. | `rebuild`, `_toggle_horizontal_cut` | low–medium |
| D11 | **Pipe pick index mismatch.** `_pipe_refs` = all visible pipes; `_pipe_midpoints_3d` skips pipes with a `None` node, so `refs[i]` can be the wrong pipe once any pipe is skipped. | `_extract_pipes`, `_nearest_point_entity` | low |
| D12 | **Comment/spec drift:** `_on_tab_close_requested` says removeTab "reparents it out" — on Qt 6.9 it stays parented to the internal `QStackedWidget`, hidden (probe §2.6). `view-relationships.md` says `View3D` "(vispy/PyVista)" and "no editing", but vispy is gone and View3D can delete walls/slabs/roofs/other items and hide/show items. `ViewCube._build_rotation` docstring cites "vispy TurntableCamera" and a Y-vertical convention while the camera is Z-up (the mapping is internal to the cube; handedness of FRONT/N labels vs. world not verified by observation). Memory note `project_vtk_plotter_test_accumulation` is linked from other notes but does not exist. | as cited | low (doc) |
| D13 | **`delete_selected` mirrors a subset of `Model_Space._bulk_delete`** (walls/slabs/roofs handled inline, skipping `_remove_item_from_lists`); other types fall back to per-item `setSelected + delete_selected_items()`, which pushes its own undo state — plus the final `push_undo_state()` → multiple undo entries for one delete. A mirror waiting to drift. | `View3D.delete_selected` vs `Model_Space._bulk_delete` | medium |
| D14 | Hygiene: toolbar buttons Fit All / Ortho / Refresh have no tooltips; colours and tolerances are module constants rather than `constants.py`/theme tokens; theme read once (no live re-theme); `QShortcut`, `QKeySequence`, `QMenu` imported unused; `FT_TO_MM`, `CIRCLE_SEGMENTS`, `COL_NODE`, `COL_SPRINKLER`, `COL_CONSTR` unused in the module (tests import some). | `_build_ui`, module header | low |
| D15 | **No way back if closed.** Nothing can re-open a 3D tab (no browser entry / action) — relevant only if the tab becomes closable. | §2.2 | n/a today |
| D16 | Pipe line-fallback width uses only the first pipe's diameter; water supply always drawn at Z=0; floor planes absent with no nodes and sized to nodes only (ignore walls/slabs). | `_extract_pipes`, `_extract_water_supply`, `_extract_level_floors` | low |

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

### 10.2 Idle while not visible
- **I6** While the 3D view is not visible (tab closed **or** open in the
  background) nothing reaches VTK: no rebuild, no render — scene edits,
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

### 10.6 Not in scope (recorded, not ratified)
D12 doc drift is reconciled at Account. D14 hygiene and D16 extraction quirks
stay as-built pending their own tasks.

## Acceptance Criteria
- [x] Every as-built claim re-verified against HEAD when the grill opened.
- [x] Each D-row ratified, scheduled (§10) or recorded out of scope (§10.6).
- [ ] I1–I16 built, each guarded per the closable-3D-tab plan; `status` moves to
      `current` once code matches §10.

## Verification Checklist
- [ ] Grep `view_3d`/`View3D` across `main.py`, `firepro3d/`, `tests/` still
      matches §4 (no new callers missing from the stub).
- [ ] `tests/test_view_3d.py` and `tests/test_view3d_stub.py` green.
- [ ] Any close/re-open work adds a live smoke (VTK is not headless-testable at
      MainWindow level).
