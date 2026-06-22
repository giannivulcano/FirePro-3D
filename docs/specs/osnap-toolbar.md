# OSNAP Toolbar — Design Spec

**Date:** 2026-04-28
**Complexity:** Large
**Status:** Implemented (2026-06-22) — see §6.4 / §10 for as-built deviations
**Source tasks:** TODO.md — "Spec session: OSNAP toolbar — per-type toggle UI, dockable placement, indicator layout, interaction with status bar pill [ref:snap-spec§9.5]"

---

## 1. Goal

Provide a dockable toolbar with one-click toggle buttons for the 8 OSNAP snap types, giving CAD users immediate visual control over which snap types are active without opening the Snap Settings dialog.

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

`toggle_osnap()` (`model_space.py:3188-3200`) sets `SnapEngine.enabled` and emits `osnapToggled(bool)`. It does **not** touch the per-type flags. The toolbar connects to `osnapToggled` and dims/restores its buttons accordingly.

### 3.4 Constraints

- No new signals on `SnapEngine` or `ModelSpace` — the existing `osnapToggled` signal is sufficient.
- The toolbar is the first `QToolBar` in the app (existing UI uses a ribbon bar and dock widgets).
- `_STATE_VERSION` must be bumped from 4 → 5 (`main.py:2816`) so `restoreState()` picks up the new toolbar's dock position.

## 4. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Widget type | Dockable `QToolBar` | Standard Qt pattern, users can float/dock/hide. Matches AutoCAD. |
| Content | 8 snap-type toggles only | Clean separation: toolbar for toggles, dialog for tolerances. F3/pill handle global state. |
| Default dock | Bottom edge | Near the OSNAP status bar pill — keeps snap controls in the same visual zone. |
| Button style | SVG icon + 3-letter abbreviation | Most discoverable — icons give visual identity, text eliminates guessing. |
| F3 interaction | Dim but preserve checked state | AutoCAD pattern. F3 is a master override, not a reset. |
| Existing dialog | Keep synced | Two access points to the same state. Dialog still needed for tolerance controls. |
| Bulk toggle | Right-click context menu | Enable All / Disable All / Snap Settings... — keeps toolbar compact. |
| Default visibility | **Hidden on first launch** *(as-built deviation, 2026-06-22)* | User preference — toolbar is opt-in via the Snap ribbon group's "OSNAP Bar" toggle button. The spec originally specced visible-on-first-launch, but the app has no menu bar (ribbon UI), so Qt's automatic View-menu toggle isn't available; an explicit ribbon toggle button is provided instead. |
| Persistence | Existing `saveState()` + existing QSettings keys | No new persistence mechanism needed. |

## 5. Widget Structure

### 5.1 Class: `_OsnapToolbar(QToolBar)`

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

### 5.5 `_on_osnap_toggled(enabled: bool)`

Connected to `ModelSpace.osnapToggled`. Calls `setEnabled(enabled)` on each of the 8 `QAction`s. Qt handles the visual dimming automatically.

## 6. MainWindow Integration

### 6.1 Construction

After the status bar setup (~`main.py:433`):

```python
self.osnap_toolbar = _OsnapToolbar(self.scene._snap_engine, self)
self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self.osnap_toolbar)
self.scene.osnapToggled.connect(self.osnap_toolbar._on_osnap_toggled)
```

### 6.2 Dialog sync

At the end of `_open_snap_tolerance_dialog()` (~`main.py:1779`), after the accept/cancel logic:

```python
self.osnap_toolbar.refresh_from_engine()
```

### 6.3 State version bump

`_STATE_VERSION` at `main.py:2816`: change from `4` to `5`.

### 6.4 Show/hide

**As-built (2026-06-22):** The toolbar is hidden on first launch. Because the
app uses a ribbon (no `QMenuBar`), Qt's automatic View-menu toggle action is
not surfaced, so a dedicated checkable **"OSNAP Bar"** button is added to the
Manage → Snap ribbon group. Its `toggled` handler (`_toggle_osnap_bar`) calls
`osnap_toolbar.setVisible()`, and `osnap_toolbar.visibilityChanged` is connected
back to the button's `setChecked` so the two stay in sync (including after
`restoreState()` re-applies the user's saved visibility).

## 7. SVG Icons

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

Valid state. `SnapEngine.find()` returns no candidates when all per-type flags are off. The OSNAP pill stays green (global is still "on" — nothing matches). No special handling needed.

### 8.5 Toolbar hidden by user

`saveState()` captures visibility. On next launch, toolbar stays hidden. User restores via View menu toggle action (Qt provides this automatically).

## 9. Out of Scope

- **Underlay snap toggle**: Separate control path (`ModelSpace._snap_to_underlay`), tracked by existing TODO.
- **One-shot snap overrides** (END, MID typed at command prompt): Deferred in snap spec §9.4.
- **Per-type keyboard shortcuts**: No per-type hotkeys in this spec.
- **Snap tolerance controls on toolbar**: Stay in the dialog.

## 10. Acceptance Criteria

- [x] `_OsnapToolbar(QToolBar)` with 8 checkable toggle buttons docks at the bottom (hidden on first launch — see §6.4 as-built; shown via the Snap-group "OSNAP Bar" button)
- [x] Each button shows an SVG icon and 3-letter abbreviation with tooltip for full name
- [x] Toggling a button immediately updates `SnapEngine.snap_*` attribute and persists to QSettings
- [x] Snap Settings dialog checkboxes reflect toolbar state and vice versa (bidirectional sync)
- [x] F3 / status bar pill dims toolbar buttons via `setEnabled(False)` without changing checked state
- [x] Right-click context menu provides Enable All, Disable All, Snap Settings...
- [x] Toolbar position and visibility persists across sessions via `saveState()` / `restoreState()`
- [x] 8 SVG icons created following §7 conventions
- [x] `_STATE_VERSION` bumped from 4 → 5
- [x] **(as-built)** "OSNAP Bar" ribbon toggle button shows/hides the toolbar and stays in sync with its visibility

## 11. Test Strategy

All tests headless (no GUI event loop required).

| Test | Verifies |
|---|---|
| `test_toggle_updates_engine` | Action toggle → `SnapEngine.snap_*` attribute changes |
| `test_toggle_persists_to_qsettings` | Action toggle → QSettings key written |
| `test_f3_off_disables_actions` | `osnapToggled(False)` → all actions `isEnabled() == False` |
| `test_f3_on_restores_actions` | `osnapToggled(True)` → actions re-enabled, checked state preserved |
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
| OSNAP ribbon button | `main.py` | init_ribbon (Snap group) | Checkable OSNAP button driving `_toggle_osnap`. **As-built 2026-06-22:** F3 moved off this button to a window-level `QShortcut` (a ribbon-button shortcut was tab-scoped); the button now syncs from `osnapToggled`. |
| Toggle handler | `main.py` | 1951-1953 | Routes to `scene.toggle_osnap()` |
| Core toggle logic | `model_space.py` | 3188-3200 | Sets `enabled`, emits `osnapToggled` |
| `osnapToggled` signal | `model_space.py` | 71 | `pyqtSignal(bool)` |
| Status bar pill | `main.py` | 159-197 | `_OsnapIndicatorLabel` — green/grey |
| Pill integration | `main.py` | 429-433 | Signal wiring, click handler |
| Snap Settings dialog | `main.py` | 1675-1779 | Modal dialog with checkboxes + tolerances |
| QSettings restore | `main.py` | 542-550 | Reads `snap/{attr}` on startup |
| QSettings save | `main.py` | 1772-1773 | Writes on dialog accept |
| State save/restore | `main.py` | 520, 2820 | `saveState()` / `restoreState()` |
| State version | `main.py` | 2816 | `_STATE_VERSION = 4` (bump to 5) |
| Theme tokens | `theme.py` | 39-78 | `btn_checked`, `text_disabled`, etc. |
| Icon path helper | `assets.py` | — | `asset_path()` for graphics resolution |
