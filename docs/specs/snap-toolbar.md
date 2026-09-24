# SNAP Toolbar — Design Spec

**Date:** 2026-04-28
**Complexity:** Large
**Status:** Superseded (2026-09-19) — dockable toolbar **RETIRED**; osnap toggles re-homed to the footer `InlineOsnapBar` (verified-commit 0a7b44a). Same `snap/{attr}` QSettings + `SnapEngine.snap_*` contract. Historical: Implemented (2026-06-22) — see §6.4 / §10 for as-built deviations; class renamed `_OsnapToolbar` → `_SnapToolbar` (2026-08-25). See banner below.
**Source tasks:** TODO.md — "Spec session: SNAP toolbar — per-type toggle UI, dockable placement, indicator layout, interaction with status bar pill [ref:snap-spec§9.5]"

> **⚠ RETIRED (2026-09-19) — dockable toolbar removed; osnap toggles re-homed to the footer.** The MainWindow chrome revamp (merge `0a7b44a`) deleted the dockable `_SnapToolbar` class from `main.py`. The 8 per-type osnap toggles now live in the **footer rail's `InlineOsnapBar`** (`firepro3d/footer_rail.py`), which reads/writes the **same** `snap/{attr}` QSettings keys and the live `SnapEngine.snap_*` booleans — that single-source-of-truth contract (§3) is **unchanged**. What moved: Snap-Settings is reached by **right-clicking the footer SNAP pill → System Settings (UX pane)**; the inline bar's visibility is a **−/+ chevron** in the footer persisting `snap/bar_expanded` (no ribbon "SNAP Bar" button, no dockable show/hide); master SNAP off dims the inline bar; angle-snap lives in **System Settings → UX pane** (no longer a ribbon button). The footer contract is owned by [`docs/specs/mainwindow-chrome-revamp.md`](mainwindow-chrome-revamp.md) (status: current) — not restated here. The design text below is retained for history; treat toolbar-specific mechanics (§6/§7/§10) as superseded per the inline notes.

> **Rename note (2026-08-25):** The product feature was renamed from "OSNAP" to "SNAP" (Select Nearest Anchor Point). The class `_OsnapToolbar` was renamed to `_SnapToolbar` and the signal `osnapToggled` / method `toggle_osnap` was renamed to `snapToggled` / `toggle_snap`. The QSettings persistence keys remain unchanged under the `snap/*` namespace.

---

## 1. Goal

Provide a dockable toolbar with one-click toggle buttons for the 8 SNAP types, giving CAD users immediate visual control over which snap types are active without opening the Snap Settings dialog.

## 2. Motivation

The per-type toggles currently live only in a modal dialog (Manage > Snap Settings). Frequent snap-type changes during design work require repeated dialog opens. A toolbar provides always-visible, one-click toggles — matching the AutoCAD OSNAP toolbar pattern that fire protection designers expect. The snapping engine spec (§9.5) formally deferred this to a dedicated spec session.

## 3. Architecture & Constraints

### 3.1 Single source of truth

The 8 `SnapEngine.snap_*` boolean attributes (`snap_engine.py:194-201`) remain the canonical state. Both the toolbar and the Snap Settings dialog read/write these attributes directly via `setattr()` / `getattr()`. No new state layer or signal system is introduced.

### 3.2 Data flow

```
Toolbar toggle click
  → setattr(engine, attr, checked)    # immediate snap behavior change
  → QSettings.setValue(snap/{attr})    # persist

Dialog checkbox toggle
  → setattr(engine, attr, checked)    # live update (existing behavior)
  → QSettings on accept / revert on cancel (existing behavior)
  → toolbar.refresh_from_engine()     # sync toolbar after dialog close
```

### 3.3 F3 global override

`toggle_snap()` (`model_space.py`) sets `SnapEngine.enabled` and emits `snapToggled(bool)`. It does **not** touch the per-type flags. The toolbar connects to `snapToggled` and dims/restores its buttons accordingly.

### 3.4 Constraints

- No new signals on `SnapEngine` or `ModelSpace` — the existing `snapToggled` signal is sufficient.
- The toolbar is the first `QToolBar` in the app (existing UI uses a ribbon bar and dock widgets).
- `_STATE_VERSION` must be bumped from 4 → 5 (`main.py:2816`) so `restoreState()` picks up the new toolbar's dock position.

## 4. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Widget type | Dockable `QToolBar` | Standard Qt pattern, users can float/dock/hide. Matches AutoCAD. |
| Content | 8 snap-type toggles only | Clean separation: toolbar for toggles, dialog for tolerances. F3/pill handle global state. |
| Default dock | Bottom edge | Near the SNAP status bar pill — keeps snap controls in the same visual zone. |
| Button style | SVG icon + 3-letter abbreviation | Most discoverable — icons give visual identity, text eliminates guessing. |
| F3 interaction | Dim but preserve checked state | AutoCAD pattern. F3 is a master override, not a reset. |
| Existing dialog | Keep synced | Two access points to the same state. Dialog still needed for tolerance controls. |
| Bulk toggle | Right-click context menu | Enable All / Disable All / Snap Settings... — keeps toolbar compact. |
| Default visibility | **Hidden on first launch** *(as-built deviation, 2026-06-22)* | User preference — toolbar is opt-in via the Snap ribbon group's "SNAP Bar" toggle button. The spec originally specced visible-on-first-launch, but the app has no menu bar (ribbon UI), so Qt's automatic View-menu toggle isn't available; an explicit ribbon toggle button is provided instead. |
| Persistence | Existing `saveState()` + existing QSettings keys | No new persistence mechanism needed. QSettings keys remain under `snap/*` namespace. |

## 5. Widget Structure

### 5.1 Class: `_SnapToolbar(QToolBar)`

*(Renamed from `_OsnapToolbar` on 2026-08-25.)*

Defined in `main.py`, alongside `_OsnapIndicatorLabel`.

**Constructor parameters:**
- `engine: SnapEngine` — the snap engine instance (read/write per-type attrs)
- `main_window: MainWindow` — for accessing `QSettings` and opening Snap Settings dialog

**Button mapping** (left-to-right order):

| Abbr | Tooltip | `SnapEngine` attribute | Icon file |
|---|---|---|---|
| END | Endpoint | `snap_endpoint` | `snap_endpoint.svg` |
| MID | Midpoint | `snap_midpoint` | `snap_midpoint.svg` |
| INT | Intersection | `snap_intersection` | `snap_intersection.svg` |
| CEN | Center | `snap_center` | `snap_center.svg` |
| QUA | Quadrant | `snap_quadrant` | `snap_quadrant.svg` |
| NEA | Nearest | `snap_nearest` | `snap_nearest.svg` |
| PER | Perpendicular | `snap_perpendicular` | `snap_perpendicular.svg` |
| TAN | Tangent | `snap_tangent` | `snap_tangent.svg` |

### 5.2 Button implementation

Each button is a checkable `QAction`:
- Icon loaded via `asset_path("Ribbon/snap_endpoint.svg")`, etc.
- Text set to 3-letter abbreviation
- Toolbar `toolButtonStyle` set to `Qt.ToolButtonStyle.ToolButtonTextUnderIcon`
- `toggled` signal connected to handler that does `setattr(engine, attr, checked)` + `QSettings.setValue()`

### 5.3 Right-click context menu

Override `contextMenuEvent()` to show:
- **Enable All** — sets all 8 engine attrs to `True`, persists, refreshes buttons
- **Disable All** — sets all 8 engine attrs to `False`, persists, refreshes buttons
- *(separator)*
- **Snap Settings...** — calls `main_window._open_snap_tolerance_dialog()`

### 5.4 `refresh_from_engine()`

Public method that reads all 8 `SnapEngine` attributes and updates button checked states. Blocks signals on each `QAction` during update to prevent re-triggering the toggle handler.

### 5.5 `_on_snap_toggled(enabled: bool)`

Connected to `ModelSpace.snapToggled`. Calls `setEnabled(enabled)` on each of the 8 `QAction`s. Qt handles the visual dimming automatically.

## 6. MainWindow Integration

> **As-built (2026-09-19):** superseded — the dockable toolbar was removed; osnap toggles are now the footer `InlineOsnapBar`. The construction/dialog-sync/state-version/show-hide mechanics below describe the retired dockable path. See `mainwindow-chrome-revamp.md` for the footer contract.

### 6.1 Construction

After the status bar setup (~`main.py:433`):

```python
self.snap_toolbar = _SnapToolbar(self.scene._snap_engine, self)
self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self.snap_toolbar)
self.scene.snapToggled.connect(self.snap_toolbar._on_snap_toggled)
```

### 6.2 Dialog sync

At the end of `_open_snap_tolerance_dialog()` (~`main.py:1779`), after the accept/cancel logic:

```python
self.snap_toolbar.refresh_from_engine()
```

### 6.3 State version bump

`_STATE_VERSION` at `main.py:2816`: change from `4` to `5`.

### 6.4 Show/hide

> **As-built (2026-09-19):** superseded — no ribbon "SNAP Bar" button and no dockable show/hide. Inline-bar visibility is now a footer **−/+ chevron** persisting `snap/bar_expanded`; see `mainwindow-chrome-revamp.md`. The 2026-06-22 note below is historical.

**As-built (2026-06-22):** The toolbar is hidden on first launch. Because the
app uses a ribbon (no `QMenuBar`), Qt's automatic View-menu toggle action is
not surfaced, so a dedicated checkable **"SNAP Bar"** button is added to the
Manage → Snap ribbon group. Its `toggled` handler (`_toggle_snap_bar`) calls
`snap_toolbar.setVisible()`, and `snap_toolbar.visibilityChanged` is connected
back to the button's `setChecked` so the two stay in sync (including after
`restoreState()` re-applies the user's saved visibility).

## 7. SVG Icons

> **As-built (2026-09-19):** the 8 icons live on and are consumed by the footer `InlineOsnapBar` (re-authored two-token), not a dockable toolbar. Render-size/placement mechanics below refer to the retired toolbar; see `mainwindow-chrome-revamp.md`. The symbol set and authoring conventions still apply.

### 7.1 Conventions

- 40×40mm viewBox (matches existing ribbon icons)
- White (#ffffff) stroke, 2px stroke-width
- Context geometry (line/circle being snapped to) at reduced opacity (~0.5)
- Snap marker glyph at full white — the focal element
- No blue accents (reserved for grip points in other icons)
- Files in `firepro3d/graphics/Ribbon/`
- Must be visually distinct at 16-24px toolbar render size

### 7.2 Symbol descriptions

| Snap Type | Symbol |
|---|---|
| Endpoint | Small square at end of a line segment |
| Midpoint | Triangle pointing at midpoint of a line segment |
| Intersection | X-cross where two lines meet |
| Center | Circle with crosshair dot at center |
| Quadrant | Diamond at cardinal point of a circle arc |
| Nearest | Hourglass/bowtie shape on a line |
| Perpendicular | Right-angle (⊥) symbol against a line |
| Tangent | Circle with a line touching tangentially |

## 8. Edge Cases

### 8.1 First launch (no QSettings)

All 8 toggles default to `True` (SnapEngine constructor defaults). Toolbar reads engine state on construction — correct behavior with no special handling.

### 8.2 STATE_VERSION mismatch

Old saved state (version 4) won't restore the new toolbar position. Qt silently ignores the unknown toolbar — it appears at the default bottom dock. Next `save_settings()` writes version 5.

### 8.3 Dialog open while toolbar visible

Dialog is modal — user can't interact with toolbar while it's open. The dialog's live `setattr()` calls change SnapEngine state, but toolbar buttons don't update until `refresh_from_engine()` is called after the dialog closes.

### 8.4 All types disabled

Valid state. `SnapEngine.find()` returns no candidates when all per-type flags are off. The SNAP pill stays green (global is still "on" — nothing matches). No special handling needed.

### 8.5 Toolbar hidden by user

`saveState()` captures visibility. On next launch, toolbar stays hidden. User restores via View menu toggle action (Qt provides this automatically).

## 8.6 Status-bar pills — SNAP · ALIGN · HALO

The status bar carries a row of one-click toggle pills. Alongside the existing **SNAP** (F3, snap engine) and **ALIGN** pills sits a **HALO** pill (added 2026-09-13, `main.py`) that toggles the HALO preselection-highlight engine. Its state persists under QSettings `halo/enabled`; it matches the SNAP/ALIGN pill style (green when on, grey when off, click to toggle). HALO's behavior is owned by `selection-mode.md §4` — not restated here; this pill is only its on/off surface. (A Preferences "HALO" tab additionally exposes the aperture + priority band — keys and semantics owned by `selection-mode.md §4.5`.)

## 9. Out of Scope

- **Underlay snap toggle**: Separate control path (`ModelSpace._snap_to_underlay`), tracked by existing TODO.
- **One-shot snap overrides** (END, MID typed at command prompt): Deferred in snap spec §9.4.
- **Per-type keyboard shortcuts**: No per-type hotkeys in this spec.
- **Snap tolerance controls on toolbar**: Stay in the dialog.

## 10. Acceptance Criteria

> **As-built (2026-09-19):** these criteria were met by the retired dockable `_SnapToolbar`; the same toggle/persist/sync/dim behaviors now hold for the footer `InlineOsnapBar` under the unchanged `snap/{attr}` contract (§3). Toolbar-specific criteria (bottom-dock placement, `saveState()`/`restoreState()` position persistence, `_STATE_VERSION` bump, "SNAP Bar" ribbon button) no longer apply — see `mainwindow-chrome-revamp.md`.

- [x] `_SnapToolbar(QToolBar)` with 8 checkable toggle buttons docks at the bottom (hidden on first launch — see §6.4 as-built; shown via the Snap-group "SNAP Bar" button)
- [x] Each button shows an SVG icon and 3-letter abbreviation with tooltip for full name
- [x] Toggling a button immediately updates `SnapEngine.snap_*` attribute and persists to QSettings
- [x] Snap Settings dialog checkboxes reflect toolbar state and vice versa (bidirectional sync)
- [x] F3 / status bar pill dims toolbar buttons via `setEnabled(False)` without changing checked state
- [x] Right-click context menu provides Enable All, Disable All, Snap Settings...
- [x] Toolbar position and visibility persists across sessions via `saveState()` / `restoreState()`
- [x] 8 SVG icons created following §7 conventions
- [x] `_STATE_VERSION` bumped from 4 → 5
- [x] **(as-built)** "SNAP Bar" ribbon toggle button shows/hides the toolbar and stays in sync with its visibility

## 11. Test Strategy

All tests headless (no GUI event loop required).

| Test | Verifies |
|---|---|
| `test_toggle_updates_engine` | Action toggle → `SnapEngine.snap_*` attribute changes |
| `test_toggle_persists_to_qsettings` | Action toggle → QSettings key written |
| `test_f3_off_disables_actions` | `snapToggled(False)` → all actions `isEnabled() == False` |
| `test_f3_on_restores_actions` | `snapToggled(True)` → actions re-enabled, checked state preserved |
| `test_enable_all` | Context menu Enable All → all 8 engine attrs `True` |
| `test_disable_all` | Context menu Disable All → all 8 engine attrs `False` |
| `test_refresh_from_engine` | Mutate engine attrs directly → `refresh_from_engine()` → button states match |
| `test_dialog_cancel_syncs_toolbar` | Open dialog, toggle, cancel → toolbar reflects reverted state |

## 12. Verification Checklist

- [ ] All acceptance criteria met
- [ ] All 8 tests pass
- [ ] No regressions in existing snap behavior (F3, status bar pill, Snap Settings dialog)
- [ ] Toolbar renders correctly in both dark and light themes
- [ ] Icons are visually distinct at toolbar render size (16-24px)
- [ ] `_STATE_VERSION` bump doesn't break existing saved layouts (toolbar appears at default position)

## 13. Existing Code Context

| Component | File | Lines | Role |
|---|---|---|---|
| Per-type toggles | `snap_engine.py` | 194-201 | 8 boolean attributes (source of truth) |
| SNAP ribbon button | `main.py` | init_ribbon (Snap group) | Checkable SNAP button driving `_toggle_snap`. **As-built 2026-06-22:** F3 moved off this button to a window-level `QShortcut` (a ribbon-button shortcut was tab-scoped); the button now syncs from `snapToggled`. |
| Toggle handler | `main.py` | — | Routes to `scene.toggle_snap()` |
| Core toggle logic | `model_space.py` | — | Sets `enabled`, emits `snapToggled` |
| `snapToggled` signal | `model_space.py` | — | `pyqtSignal(bool)` |
| Status bar pill | `main.py` | 159-197 | `_OsnapIndicatorLabel` — green/grey |
| Pill integration | `main.py` | 429-433 | Signal wiring, click handler |
| Snap Settings dialog | `main.py` | 1675-1779 | Modal dialog with checkboxes + tolerances |
| QSettings restore | `main.py` | 542-550 | Reads `snap/{attr}` on startup |
| QSettings save | `main.py` | 1772-1773 | Writes on dialog accept |
| State save/restore | `main.py` | 520, 2820 | `saveState()` / `restoreState()` |
| State version | `main.py` | 2816 | `_STATE_VERSION = 4` (bump to 5) |
| Theme tokens | `theme.py` | 39-78 | `btn_checked`, `text_disabled`, etc. |
| Icon path helper | `assets.py` | — | `asset_path()` for graphics resolution |
