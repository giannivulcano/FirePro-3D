---
status: current
last-verified: 2026-09-30
verified-commit: f1d8151
applies-to:
  - firepro3d/view_3d.py
  - firepro3d/view3d_tab.py (new)
  - firepro3d/canvas_placeholder.py (new)
  - firepro3d/project_browser.py
  - firepro3d/model_space.py (set_mode no-view refusal)
  - main.py (3D tab wiring, _CanvasTabBar count seam, canvas stack, chokepoints)
source-tasks: ["todo_open.md — 3D Model canvas tab is closable and reopenable from the Project Browser [type:feature] (2026-09-30)"]
---

# Closable 3D Model Tab — Design Spec

**What is ratified where.** The *what* (I1–I16) is the as-intended contract in
`docs/specs/view-3d.md §10`, ratified in the 2026-09-30 grill — this doc does
not restate it; it cites I-numbers. This doc owns the *how*: approach A
(View3D owns its lifecycle), approved 2026-09-30, and the empty-canvas visual,
approved at the served mockup gate 2026-09-30.

## Goal

The user can close the 3D Model tab like any plan tab and bring it back from a
`3D Model` leaf at the top of the Project Browser (or the empty-canvas quick
button), with the 3D view doing no work while it is out of sight and no native
VTK crash on any close/reopen/fullscreen path.

## Motivation

The 3D view is the heaviest widget in the window and today it can neither be
closed nor kept idle: every scene edit rebuilds it even when hidden (D2). A
closable, idle-when-hidden 3D tab gives users a lighter plan-only workspace and
fixes the stale-pick wrong-item delete (D8) that closing would otherwise worsen.

## Architecture & Constraints

- **Approach A — View3D owns its lifecycle.** Every rule about when VTK may be
  touched lives inside `View3D` behind a public API; `MainWindow` only routes
  intent. Rejected: B (guard each `MainWindow` call site with `isVisible()` — a
  mirror of the rule at every caller; D2 is exactly that failure) and C (a full
  canvas-tab manager for plan/detail/paper/editor tabs — out of scope; candidate
  follow-up).
- **Keep-alive singleton.** One `View3D` for the session; closing is
  `removeTab` only (I1). Probed on Qt 6.9 (`view-3d.md §2.6`): a removed page
  stays parented, hidden, under the tab widget's internal `QStackedWidget`, and
  re-adding works. Never `deleteLater()` it; identity checks use
  `w is self.view_3d` (I2).
- **Startup "closed" = the close path.** When the pref says closed, View3D is
  still constructed and added, then removed before the window's first show — so
  the VTK widget is never a parentless top-level window and "closed at startup"
  runs through exactly the user-close code.
- **main.py stays thin.** New behaviour lands in two small modules
  (`view3d_tab.py`, `canvas_placeholder.py`); `main.py` gains wiring only
  (1000-line tripwire: `main.py` and `view_3d.py` are both over it — noted, not
  refactored here).
- **Tokens only** (`theme.detect()` + `theme.M`); label sizes in the widgets' own
  QSS, never `setFont` (the app QSS `QWidget { font-size }` wins on re-apply).
- **Conventions:** Google docstrings, relative imports in `firepro3d/`, QSettings
  keys `ui/<name>`, tooltips on every button.

## Design Decisions

### DD1 — View3D public API (I6, I9, I11–I16)
| Member | Behaviour |
|---|---|
| `request_rebuild()` | Public name for today's `_schedule_rebuild` (mark dirty; start the 100 ms coalescing timer only if visible). **As built, its only model-change caller is View3D's own `sceneModified` connection** — `MainWindow._refresh_all_views` does **not** call it (its 200 ms debounce would fire after the first rebuild and rebuild a visible view twice per edit), so a visible edit rebuilds **once** (D2). `rebuild()` stays for the explicit Refresh button. |
| `_render()` | The only way View3D renders: renders if `isVisible()`, else sets `_render_pending`. Every direct `self._plotter.render()` routes through it (D3). |
| hidden-state deferral | While hidden, `_on_2d_selection_changed` sets `_sel_pending` and returns; heatmap show/clear store `_pending_heatmap` (a result or a clear sentinel) and return. `showEvent` flushes in one order: dirty → rebuild (which re-syncs selection and re-applies heatmap/H-Cut); else pending selection → sync; else pending heatmap → apply; else `_render_pending` → render. *(As built: differs — see As-built deviations.)* |
| `reset_for_project(scale_manager)` | `_sm = scale_manager`; `_first_build = True` (next rebuild re-fits); `clear_pick()`; mark dirty via `request_rebuild()` (I9, D1). *(As built: differs — see As-built deviations.)* |
| `clear_pick()` | Clears `_3d_selected` + highlight/overlay actors (render via `_render()`). |
| `cancel_interaction()` | Public Escape (today's `_on_escape` body, render via `_render()`); `_on_key_press` Esc calls it so the two Escapes stop diverging (I12, D6). |
| `cleanup()` | Stops `_rebuild_timer`, disconnects its two scene connections (`sceneModified`, `selectionChanged`), then closes the plotter; idempotent (I11, D5). |
| `rebuild()` | No focal re-centre after the first build (I13, D7); re-applies H-Cut when `_h_cut_enabled` (I15, D10); re-applies a live heatmap if one is set. *(As built: differs — see As-built deviations.)* |
| extraction fixes | `_extract_openings` skips hidden openings and openings whose host wall is hidden (I14, D9); `_extract_pipes` builds `_pipe_refs` and `_pipe_midpoints_3d` in the same filtered loop so indices align (I16, D11). |
| `delete_selected()` | Routes through the scene: select exactly the picked items in the scene, then one `delete_selected_items()` call — one undo step, 2D rules (I8, D13). *(P4: the plan's first probes confirm `delete_selected_items` handles walls/slabs/roofs and pushes exactly one undo state.)* *(As built: differs — see As-built deviations.)* |

### DD2 — `view3d_tab.View3DTabController` (I1–I4, I7)
Owns the 3D tab's presence in `central_tabs`; built by `MainWindow` with
`(central_tabs, view_3d, settings)`.
- `is_open()` → `central_tabs.indexOf(view_3d) != -1`.
- `open()` → if closed, `insertTab(0, view_3d, "3D Model")`; `setCurrentIndex`;
  write `ui/view3d_open = True`.
- `close()` → `view_3d.clear_pick()`; `removeTab(indexOf(view_3d))`; write
  `ui/view3d_open = False`. Never deletes.
- `apply_startup_pref()` → reads `ui/view3d_open` (default `True`); closed →
  `close()` without re-writing the pref. Called before first show; the canvas
  is momentarily empty (unseen) until `MainWindow.showEvent`'s first-show
  `_activate_plan_view(DEFAULT_LEVEL)` adds the plan, so a launch never shows
  the placeholder.
- The close dot: the construction-time loop that strips close buttons from
  every startup tab is removed, so `_CanvasTabBar.tabInserted` gives 3D the same
  dot as any tab. `_on_tab_close_requested` checks `widget is self.view_3d`
  first and delegates to `close()`; the title check goes.

### DD3 — Empty canvas (I5)
- **Count seam:** `_CanvasTabBar` already overrides `tabInserted`; it gains a
  `tabRemoved` override and emits one `countChanged(int)` from both.
- **Host:** the canvas column's single `central_tabs` becomes a `QStackedWidget`
  of `[central_tabs, EmptyCanvasPlaceholder]`; `MainWindow` switches on
  `countChanged` (0 → placeholder) and sets `scene.view_available = count > 0`.
- **`canvas_placeholder.EmptyCanvasPlaceholder(QWidget)`** — signals
  `open3DRequested`, `openPlanRequested`; `set_active_level(name)` updates the
  plan button text (`Plan: <level>`), called on activeLevelChanged and on load. *(As built: differs — see As-built deviations.)*
  Visual (mockup-approved):
  - an empty **26 px rail row** (surface) + **1 px `line_strong` divider**, so the
    dock-header dividers keep landing on the canvas divider row (the live
    probe showed `#centralTabs`' bar collapses 26 → 0 px with no tabs); the rail
    height is taken from the canvas tab bar's measured height, and a guard
    pins them equal;
  - below it the `ground` pane *(As built: differs — see As-built deviations.)* with a centred block at **45 %** of pane height:
    title **"No views open"** 13 pt bold `ink`; hint **"Open a view from the
    Project Browser"** 9 pt `muted`; gaps title→hint **6 px**, hint→buttons
    **18 px**;
  - two house `QPushButton`s side by side — **3D Model** and **Plan: \<level\>**
    — spacing **8 px**, `setMinimumWidth(120)`, tooltips "Open the 3D Model
    view" / "Open the plan view of the active level".
- **Refusal:** `Model_Space.view_available` (default `True`, so Block-Editor
  scenes are untouched). `set_mode` refuses any mode other than `None`/`"select"`
  when it is `False`, emitting `instructionChanged("Open a view from the Project
  Browser")` (footer status). *(As built: differs — see As-built deviations.)* `MainWindow._start_modify_tool` and
  `_delete_if_not_editing` return early with the same hint when the stack shows
  the placeholder. Undo/redo, save/open, settings, managers stay live.

### DD4 — Project Browser leaf (I3)
`project_browser.py`: a top-level item **inserted at index 0** (above
`2D Model`), `_ROLE_TYPE = "view3d"`, not drag-enabled (it is already outside
`mimeData`'s `plan/elevation/detail` set); new signal `activate3DView()` emitted
from `_on_item_activated` and a context-menu **Open**. `MainWindow` connects it
to `View3DTabController.open`. Idempotent under the known double-fire of
`itemActivated` + `itemDoubleClicked` (open on an open tab only re-selects).

### DD5 — MainWindow routing (I7, I9, I10)
- `_delete_if_not_editing`: use the 3D pick only when
  `central_tabs.currentWidget() is self.view_3d` (I7).
- `open_file` / `new_file` *(As built: differs — see As-built deviations.)*: after `_close_stale_view_tabs()`, call
  `view_3d.reset_for_project(self.scene.scale_manager)` (I9).
- `_on_escape` → `view_3d.cancel_interaction()`; `_refresh_all_views` no
  longer touches the 3D view (as built — see As-built deviations).
- Radiation: unchanged call to `show_radiation_heatmap` — DD1's deferral makes
  it land silently while closed (I10).

## Acceptance Criteria
- [ ] I1–I16 (`view-3d.md §10`) each met — criteria text lives there.
- [ ] Empty-canvas visual matches DD3's approved values under the live app QSS + font.
- [ ] Guard tests (VC3 — real `MainWindow` / real `View3D`, not the stub; each shown RED with its fix reverted):
  1. **Close/reopen:** close the 3D tab → `view_3d` not deleted (sip), `indexOf == -1`; a scene edit leaves the rebuild count flat; `activate3DView` → index 0, current, exactly one rebuild after show.
  2. **Pref:** close → `ui/view3d_open` false; a second `MainWindow` on the same (isolated) QSettings starts without the 3D tab; reopen writes true.
  3. **D8:** pick an item in 3D, close the tab, select a pipe in the plan, Delete → only the pipe is gone, one undo restores it; the 3D-picked item survives.
  4. **Empty canvas:** close every tab → placeholder current; `set_mode("pipe")` leaves mode unchanged and the footer shows the hint; each quick button opens its view.
  5. **Rail alignment:** placeholder rail height == canvas tab bar height with one tab (under `build_app_qss` + `apply_app_font`).
  6. **Project load:** after open/new, `view_3d._sm is scene.scale_manager` and the next shown rebuild re-fits the camera.
  7. **Cleanup:** `cleanup()` then `scene.selectionChanged.emit()` / `sceneModified.emit()` raises nothing.
  8. **Unit guards on View3D:** camera focal point unchanged across a rebuild (D7); H-Cut still applied after rebuild (D10); hidden wall's opening absent (D9); pick on a pipe after a skipped pipe returns that pipe (D11); 3D delete = one undo step (D13).
  9. **Browser:** the `3D Model` leaf is the first top-level item; activation emits `activate3DView` once per gesture handler; not in drag MIME.
- [ ] Live smoke: close/reopen ×10, fullscreen toggle with 3D closed and open, startup with pref closed then reopen, radiation run while closed then reopen — no native crash, heatmap present.

## Verification Checklist
- [ ] P4 probes run first (plan step 1): a View3D added-then-removed before first show renders correctly on first reopen; `delete_selected_items` on mixed walls/slabs/roofs/pipes pushes one undo state.
- [ ] Smoke before the full suite; full suite `-m "not perf"`, then `-m perf` standalone (VC6); MainWindow/VTK guards run early in the build (native-state accumulation degrades later runs).
- [ ] VC9 seam review before smoke (Large).
- [ ] `grep -n "view_3d\._\|_on_escape()" main.py` → no private View3D calls remain.
- [ ] Account: `view-3d.md` (§10 built → status), `project-browser.md` (tree + signals table), `mainwindow-chrome-revamp-stage2.md` (3D no longer close-protected; empty-canvas rail), `test-harness.md` if the View3D stub gains members.

## Existing Code Context
- Paper-tab keep-alive precedent: `MainWindow._activate_paper_sheet` + the
  `paper_space_widget` exemption in `_on_tab_close_requested`.
- `View3D._schedule_rebuild` / `showEvent` already implement dirty-while-hidden;
  DD1 makes them the only path.
- `Model_Space.authoring_allowed` (containment C1) is the existing mode gate
  next to which the no-view refusal sits in `set_mode`.

## As-built deviations (verified at `f1d8151`; `view-3d.md` §1–§8 is the as-built record)
- **Rebuild trigger.** `_refresh_all_views` dropped its 3D call entirely instead
  of calling `request_rebuild()` (a second request after the first rebuild
  would rebuild twice); `sceneModified` → `request_rebuild` is the sole path.
- **Show flush.** `showEvent` defers `_flush_pending` with
  `QTimer.singleShot(0, …)`. Order: pending heatmap show/clear first, then dirty
  → rebuild (re-syncs selection), else pending selection, else pending render.
  The rebuild does not re-apply the heatmap: the overlay actors live outside
  `_actors` and survive it.
- **`reset_for_project`** also calls `clear_radiation_heatmap()` (the old
  project's overlay is keyed by its entities). It runs at three sites, not
  after `_close_stale_view_tabs()`: at startup after the template apply, in
  `new_file` after the template apply (which replaces `scene.scale_manager`),
  and in `_apply_loaded_file` (File→Open and crash recovery).
- **`delete_selected`** calls a new `Model_Space.delete_items(items)`
  (explicit-list bulk delete, one undo step; `delete_selected_items()`
  delegates to it). It does not select-then-delete, because `setSelected` does
  not stick for some picked items.
- **Empty-canvas pane is `surface`**, not the mockup's `ground`. The user
  changed it at the 2026-09-30 smoke to match the live plan canvas. The 3D
  plotter background moved to `surface` too (`view-3d.md` I17).
- **Plan-button label** refreshes when the canvas becomes empty and on
  `levelsChanged` (level widget + Levels dialog), not on "activeLevelChanged
  / load". An active-level change opens that plan, so it leaves the empty
  canvas.
- **Refusal homes.** Modify-tool refusal lives in `ModifyToolsController.start`
  (the one home for ribbon and shortcuts), not `_start_modify_tool`.
  `_delete_if_not_editing` keys on `scene.view_available`, not on the stack.
  The ribbon Delete now routes through `_delete_if_not_editing`.
- **Added at build (user-ratified, `view-3d.md` I5a/I5b).** Thermal-radiation
  start is refused on an empty canvas, and closing the last tab cancels a
  pick in progress. On the empty-canvas swap MainWindow disarms to `select`
  before clearing `view_available`. A canvas whose only tab is a Block Editor
  counts as a view.
- **Rebuild camera.** Only `_orbit_center` follows the geometry; the first build
  (and the first after `reset_for_project`) fits.

## Follow-ups (filed at Phase 6)
- Per-project 3D camera save in the `.fpd` [feature].
- Unified 2D/3D selection [design].
- Tool behaviour while the 3D or Paper tab is current (verify; bug if broken).
- Canvas-tab manager extraction from `main.py` (approach C) [maint].
