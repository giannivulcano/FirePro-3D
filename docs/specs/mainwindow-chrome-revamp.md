---
status: current           # built + live-smoked (feat/mainwindow-chrome, 2026-09-19)
last-verified: 2026-09-19
verified-commit: 76757eb
applies-to:
  - main.py
  - firepro3d/frameless_shell.py
  - firepro3d/ribbon_bar.py
  - firepro3d/ui_kit.py
  - firepro3d/theme.py
  - firepro3d/settings/panes.py
  - firepro3d/snap_engine.py
  - firepro3d/icons.py
source-tasks:
  - "todo_open.md: chrome revamp of MainWindow (stage one) — header rail, footer rail, ribbon styling, snap-group teardown"
  - "folds in: Frameless MainWindow → immersive fullscreen (todo_open UI follow-ups)"
  - "folds in: Full chrome unification — pill/toolbar greys + main.py hexguard (Accent-colour section)"
  - "folds in (slice): File-group icons from 'Author the ~46 ribbon icons'"
  - "folds in (slice): ribbon-label typography from 'App-wide typography role sweep'"
related-contract: extends ui-design-system.md (deferred wave #2 — MainWindow re-shell); reconciles ribbon-bar.md, snap-toolbar.md, settings-dialog.md, icon-style-guide.md
---

# MainWindow Chrome Revamp (Stage One) — Design Spec

> **Consolidating contract.** This is one design doc for a milestone-scale chrome change spanning five governing specs. Per-spec bodies are reconciled **in place** at wrap-up (Account); the reconciliation map is in *Design Decisions → §Spec reconciliation map*. Mockups (approved, light+dark) persist under `.superpowers/brainstorm/` (git-ignored) — header v3, footer (Position-right), osnap glyphs (live-aligned), ribbon v4.

> **As-built deviations (2026-09-19).** (1) **F11 stays ALIGN** (a tested contract) — fullscreen toggles via the header restore-dot / double-click-header, not F11. (2) **`main.py` is NOT in the chrome hexguard** — it lives at the repo root (outside the `firepro3d/` scan) and carries pre-existing legacy hex; the revamp moved all chrome styling into the token-clean `header_rail.py`/`footer_rail.py` (both guarded). (3) **Breathing room around the selected ribbon button is height-via-centering** (button 68 < stack 88), not a QSS margin. (4) Ribbon large-button metrics as-built: icon 48, height 68, stack 88. (5) **Window-drag-by-header** shipped; **edge-resize over child widgets** is a filed follow-up. The per-spec reconciliation of the other five governing specs (ui-design-system, ribbon-bar, snap-toolbar, settings-dialog, icon-style-guide) is tracked as a follow-up in `todo_open.md`.

## Goal

Re-shell the FirePro3D MainWindow chrome into a tokenized, house-consistent surface: a custom **header rail** (app identity + Save/Undo/Redo + window controls), a tokenized **footer rail** (3 sub-rails with an inline osnap bar), a restyled **ribbon** (house TopTabs selection + vertical group labels + a compacted File group), a **snap-group teardown**, and **frameless fullscreen** — all driven by `theme.py` tokens with zero raw chrome hex.

## Motivation

The MainWindow is the last major surface still on ad-hoc chrome: raw-hex status pills (`#888`/`#555`/`#ffcc44`), a plain `QTabBar` ribbon, an always-visible OS title bar, and snap controls scattered across a ribbon group + a dockable toolbar + a settings pane. The house design-system (`ui-design-system.md`) already tokenizes the five frameless dialogs and defers the "MainWindow re-shell" as wave #2. This closes that wave: one visual language app-wide, `main.py` brought under the chrome hexguard, and the snap UX consolidated to the footer.

## Architecture & Constraints

- **Tokens only.** All chrome colours/spacing/fonts resolve through `theme.py` (`detect()`, the `M` metrics namespace, semantic aliases). No raw hex in chrome; `main.py` is added to `tests/test_theme_chrome_hexguard.py` and the metrics-drift guard is extended to the new widgets. Canvas/geometry colours (Display-Manager-owned) are out of scope.
- **Custom `QWidget` rails, not restyled `QMenuBar`/`QStatusBar`.** Header via `QMainWindow.setMenuWidget(header_rail)`; footer via a single custom `QWidget` replacing the status-bar contents. Rationale: frameless drag, window-control dots, sub-rail dividers, and the inline osnap chevron are beyond clean `QMenuBar`/`QStatusBar` styling, and custom widgets tokenize cleanly.
- **Reuse over rebuild.** Header dots reuse `frameless_shell._WinDot`; the frameless shell is adopted via `FramelessShellMixin` (parameterized — see below); the ribbon reuses the `ui_kit.TopTabs` *styling language* (recovered on `main`); the osnap toggle icons match `snap_engine.SNAP_MARKERS` 1:1.
- **Runnable at every commit** on a feature branch (`feat/mainwindow-chrome`); the risky frameless/VTK piece is spiked first and can split to stage 1b without blocking the chrome.
- **Rule A.** This doc links to owned facts (theme tokens in `theme.py`; snap markers in `snap_engine.SNAP_MARKERS`; ribbon roster in `ribbon-bar.md §3.4`); it does not restate them or cite line counts.

## Design Decisions

### Header rail (custom, via `setMenuWidget`)
Order L→R (approved v3): app **icon** → **"FirePro 3D"** (Title role) → **"(v…)"** (`APP_VERSION`, muted) → `│` → **Save / Undo / Redo** → `│` → **project name** + dirty **●** → *(stretch)* → **min / restore / close** dots (`_WinDot`).
- **Project name:** filename-only (no extension), **middle-elided** with full-path tooltip; dirty **●** in the accent token; `setWindowTitle` mirrored so taskbar/alt-tab stay meaningful under frameless.
- **Enabled-state:** Undo/Redo gated on the **active tab's** stack (greyed at bounds) — paper tabs use `QUndoStack.canUndo/canRedo`; other tabs need `can_undo()`/`can_redo()` helpers derived from the model scene's `_undo_stack`/`_undo_pos`. Save is **always-enabled**; dirtiness shows via the **●** (a new model-scene dirty flag set on `push_undo_state`/cleared on save).
- **Tooltips with shortcuts:** "Save [Ctrl+S]", "Undo [Ctrl+Z]", "Redo [Ctrl+Y]".
- **Shortcuts fire window-wide** (window-level `QShortcut`/`QAction`), not tab-scoped as the current ribbon Edit buttons are.

### Footer rail (custom widget, 3 sub-rails)
Layout (approved): **Mode/instruction** (accent mode badge + instruction) — *(stretch)* — `│` **Position** (`X … Y …` in the Consolas value font + pipe-mode node-snap chip) `│` **Toggles** (right-grouped). Sub-rails divided by single tokenized muted (`line`) verticals; **no `QSizeGrip`**.
- **Toggles sub-rail:** `SNAP` pill (`▾` = right-click → Snap Settings) + **inline osnap bar** (8 icon toggles, no labels, tooltips = name + how-it-works) + **`−`/`+` chevron** (collapse/expand the bar; persists `snap/bar_expanded`, default expanded) + `ALIGN` pill + `HALO` pill.
- **Osnap icons** match `snap_engine.SNAP_MARKERS` 1:1 so the toggle == the on-canvas marker: Endpoint □, Midpoint △, Center ○, Quadrant ◇, Intersection ⊠ (x_cross), Nearest ✕ (cross), Perpendicular ⌐+□ (right_angle), Tangent ○+bottom-line (tangent_circle). Authored two-token; ON = accent, OFF = muted.
- **Pills:** ON = accent border + accent text + faint accent-soft fill; OFF = `line` border + muted text. Replaces `_pill_style`/`_mode_badge_style`/`node_snap_label` raw hex.

### Ribbon (Option A — reuse TopTabs styling)
- **Top tabs:** apply the `ui_kit.TopTabs` selection language to the existing `RibbonBar` `QTabBar` (selected = ink + semibold + 2px accent underline; others muted; hover accent-soft; full-width `line_strong` divider under the strip). **Keep** all existing ribbon wiring — `insert_page(contextual=)`, `remove_page`, contextual accent treatment, tab shortcuts, `currentChanged→QStackedWidget`. (Option B — embedding a `TopTabs` instance — rejected for stage one: needs `TopTabs` to grow insert/remove/contextual APIs; more parity risk for no visible gain.)
- **Group labels:** vertical, **left-edge**, **ALL-CAPS Overline** role, reading bottom-to-top, centered on group height.
- **Density (approved v4):** ~30px tab strip + **~106px page** (was 150), large icon 30 / small icon 16.
- **File group:** New / Open / Save As as a **3-stack small-icon column** (max 3 per column) + **Recent** as a large button (own icon + `▾` recent-files dropdown). Save moves to the header.
- **Roster change:** Manage tab end state = **File / Settings / Display**. The **Edit group** (undo/redo → header) and the entire **Snap group** are deleted.

### Snap teardown
- **Remove** the ribbon master SNAP button (redundant with the footer pill + F3), the Angle-Snap menu button (angle-snap already lives in the System Settings → Snap pane, `settings/panes.py`), and the "SNAP Bar" toggle.
- **Retire** the dockable `_SnapToolbar` (`main.py`); the inline footer osnap bar replaces it, reading/writing the same `snap/{attr}` keys. Its visibility is the footer `−`/`+` chevron (no separate settings checkbox).
- **Snap Settings** entry point = right-click the footer SNAP pill (mirrors the retired toolbar's context menu) → System Settings on the Snap pane.
- **Dropped:** the "snap-to-underlay → Preferences" item — no global toggle exists; underlay snap is already per-record in the Underlay Manager.

### Frameless + fullscreen (spike-first; VTK is the make-or-break)
- **Parameterize** `FramelessShellMixin.init_frameless_shell` with a `window_type` arg (default `Qt.WindowType.Dialog`; MainWindow passes `Qt.WindowType.Window`); MainWindow builds its own header (`build_titlebar=False`) and reuses `_WinDot`.
- **Default fullscreen** (`showFullScreen`, taskbar hidden); **F11** and the **restore dot** toggle fullscreen ↔ maximized-windowed; minimize→taskbar; persist last state; migrate `ui/immersive` → `ui/fullscreen` (read-migration, no orphaned key).
- **VTK crash approach:** set `Qt.AA_DontCreateNativeWidgetSiblings` early + audit `View3D`'s `QtInteractor` native-window creation; verify against the existing "viewport delete → qFatal" repro.
- **Riskiest-first spike (build step 1):** frameless + `showFullScreen` on a MainWindow with a live 3D view + viewport-delete. **Fallback:** if the spike can't get a clean 3D + viewport-delete under frameless-fullscreen in a bounded attempt, ship header/footer/ribbon chrome on the current `showMaximized` and split frameless-fullscreen to **stage 1b** (header rail still built).

### Build sequencing (feature branch `feat/mainwindow-chrome`, runnable each commit)
1. **Spike** frameless-fullscreen + VTK (throwaway — decides E now vs 1b).
2. **Footer rail** (tokenize pills/dividers + inline osnap bar + chevron) + **snap teardown**.
3. **Header rail** (+ migrate Save/Undo/Redo, dirty flag, window-wide shortcuts).
4. **Ribbon** (TopTabs styling + vertical group labels + File-group restyle + group deletions).
5. **File-group icons** (mockup-gated) + hexguard/metrics-guard extension.
6. **Frameless-fullscreen** adoption (or 1b split per the spike).

### Spec reconciliation map (applied in Phase 6 Account, not now)
- `ui-design-system.md` — MainWindow re-shell contract (header/footer-rail invariants, new `M` tokens); flip wave #2 from deferred → current.
- `ribbon-bar.md §3.4` — roster (Manage = File/Settings/Display; Edit/Snap gone), TopTabs adoption, vertical group labels, File-group shape.
- `snap-toolbar.md` — `_SnapToolbar` retired; osnap toggles re-homed to the footer; Snap-Settings via SNAP-pill.
- `settings-dialog.md` — angle-snap/snap-pane unchanged; note the removed ribbon entry points.
- `icon-style-guide.md` — new File-group + header + osnap-toggle icon set (two-token).

## Acceptance Criteria

**Header**
- [ ] Header rail renders via `setMenuWidget`, tokenized, with the approved v3 order and window dots.
- [ ] Project name: filename-only, middle-elided, full-path tooltip, dirty ● (accent) on unsaved changes; `setWindowTitle` mirrored.
- [ ] Undo/Redo greyed when the active tab's stack is at its bound; Save always-enabled.
- [ ] Save/Undo/Redo tooltips include shortcuts; Ctrl+S/Z/Y fire window-wide from any tab.

**Footer**
- [ ] Three sub-rails with tokenized muted dividers; Mode/instruction left, Position + Toggles right-grouped (Position immediately left of SNAP); no size grip.
- [ ] Inline osnap bar: 8 toggles matching `SNAP_MARKERS`, no labels, tooltips present; `−`/`+` chevron collapses/expands and persists `snap/bar_expanded`.
- [ ] SNAP/ALIGN/HALO pills tokenized (on=accent, off=muted); right-click SNAP opens Snap Settings.
- [ ] All former raw hex in `_pill_style`/`_mode_badge_style`/`node_snap_label` removed.

**Ribbon**
- [ ] Tabs use the TopTabs selection language; contextual insert/remove, contextual accent, tab shortcuts, and page sync all still work (driven through the widget in tests).
- [ ] Vertical ALL-CAPS left-edge group labels; page density ~106px.
- [ ] File group = New/Open/Save As (3-stack) + Recent (large, dropdown); Save removed.
- [ ] Manage tab = File/Settings/Display; Edit + Snap groups gone.

**Snap teardown**
- [ ] Dockable `_SnapToolbar` retired; osnap state still persists under `snap/{attr}`; angle-snap reachable in the Snap pane.

**Frameless/fullscreen**
- [ ] `FramelessShellMixin` accepts `window_type`; MainWindow opens frameless-fullscreen, taskbar hidden; F11/restore-dot toggle; state persists; `ui/immersive`→`ui/fullscreen` migrates.
- [ ] **Hard live gate:** frameless-fullscreen with the 3D view opened + rebuilt + a viewport deleted — no native-window `qFatal`/0xC0000409. (Or documented 1b split if the spike fails.)

**Tokenization guards**
- [ ] `main.py` added to `test_theme_chrome_hexguard.py`; metrics-drift guard extended to the new rail widgets; both green.

## Verification Checklist
- [ ] All acceptance criteria met.
- [ ] Full suite green (headless), incl. the new widget tests driven through the real widgets.
- [ ] Live smoke: rendering in light+dark, frameless drag/edge-resize, fullscreen+taskbar-hidden, window-wide shortcuts, the VTK gate.
- [ ] No regressions: undo/redo across tabs, snap behavior (F3 + per-osnap), contextual ribbon tabs.
- [ ] Spec reconciliation map applied; `verified-commit`/`last-verified` stamped on each touched spec.

## Spike verdict (Task 0) — 2026-09-18

**PASS.** Frameless top-level (`FramelessWindowHint | Window`) + `showFullScreen` + `Qt.AA_DontCreateNativeWidgetSiblings` (set before `QApplication`) ran the real `MainWindow` with a live `View3D` opened/rebuilt and a paper viewport created + deleted — **no native-window `qFatal`/0xC0000409**. Task 6 proceeds as frameless-fullscreen (no stage-1b split).

Two non-fatal exceptions surfaced during Alt+F4 teardown (surfaced only because the spike installs the excepthook and skips `closeEvent` cleanup): `view_3d._clear_actors` when `self._plotter is None`, and `_on_selection_changed_contextual` reading `selectedItems()` on an already-deleted `Model_Space`. Both are selection-signal-during-teardown races, not the native-window class. **Follow-up:** confirm they reproduce on `main` (pre-existing) during the smoke pass; if so, file separately (disconnect selection signals in `MainWindow.closeEvent` / guard `_clear_actors` on `_plotter`).

## Edge Cases & Error Handling
- **Long/no project name:** middle-elide + tooltip; unsaved → "Untitled" (no ●).
- **Undo model divergence:** model scene uses a custom list stack (not `QUndoStack`); the header must read the right stack per active tab (paper vs model vs block-editor).
- **Fullscreen trap:** header dots + F11 always provide an exit; minimize restores the taskbar.
- **Multi-monitor:** fullscreen covers the current screen; drag-between-monitors only applies in windowed mode.
- **QSettings migration:** read-migrate `ui/immersive`→`ui/fullscreen`; leave `snap/{attr}` untouched; add `snap/bar_expanded`.
- **Live-only bug classes:** frameless/focus/paint + the VTK native-window crash are not headless-catchable — covered by the live-smoke gate.

## Code Style & Testing
- PyQt6, Google docstrings, relative imports within `firepro3d/`, tokens via `theme.py`. Tests: pytest with the session `qapp` fixture (no pytest-qt); **drive real widgets** (Qt tests-drive-widgets, not slots); each guard shown RED with the fix reverted; the metrics-drift + hexguard static guards run in-suite.
