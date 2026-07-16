---
status: current          # code-verified as-built behavior; divergences ledger at end
last-verified: 2026-07-16
verified-commit: 002cc19
applies-to:
  - firepro3d/ribbon_bar.py
  - main.py (init_ribbon + _init_*_tab helpers + mode-button sync)
source-tasks: "TODO.md §B follow-up: Draft-tab migration + Font ribbon group (orphan-gate spec forged on first touch)"
---

# Ribbon Bar — Governing Spec

**Date forged:** 2026-07-16 (Phase 1b orphan gate — reverse-engineered from as-built code)
**Adjacent docs:** `specs/osnap-toolbar.md` (Snap group + OSNAP toolbar toggle — owns that surface), `architecture/theming.md` (QSS ownership), `specs/paper-space.md` §17.4 (paper undo dispatch contract), `specs/property-panel.md` (the panel the ribbon must not bypass — see D2)

## 1. Goal

A Microsoft-Office-style ribbon is the app's sole primary command surface (there is **no `QMenuBar`**): a tab strip over a fixed-height stack of pages, each page a horizontal row of labelled button groups. `ribbon_bar.py` is the generic widget library; `main.py` owns all content (which tabs/groups/buttons exist and what they do).

## 2. Motivation

CAD users get a workflow-ordered command surface (Manage → Draw → Build → Modify → Analyze → Draft) instead of nested menus. The library/content split keeps `ribbon_bar.py` reusable and dumb; every behavioral decision (mode wiring, tab auto-switching, dispatch) lives with the window that owns the scene.

**Contract vs as-built (grilled 2026-07-16):** the *principle* — a workflow-ordered ribbon as sole command surface — is the contract. The specific six-tab split is **as-built, open to reshaping** (e.g. a Draw+Draft merge needs no argument against this spec, only a coherent workflow story).

**Target taxonomy (decided 2026-07-16, execution deferred):** no Draw+Draft merge — **Draft becomes the documentation tab**: the model-space Annotations group (Dimension/Text/Hatch) moves Draw → Draft in a future task, so Draft = annotations (model + sheet) + page setup + plot, and Draw = pure construction geometry + blocks (TODO filed).

## 3. Architecture & Constraints

### 3.1 Widget library (`ribbon_bar.py`)

| Class | Role | Key constraints |
|---|---|---|
| `RibbonBar` | `QTabBar` + `QStackedWidget` of pages | Stack fixed at 150 px tall; tab index drives stack index; QSS applied at construction from `theme.build_ribbon_qss(theme.detect())` (Rule A: theming owned by `architecture/theming.md`) |
| `RibbonPage` | One tab's content — HBox of groups + trailing stretch | `add_group(title)` inserts before the stretch. No overflow handling: a too-narrow window clips groups (no collapse/scroll). **Accepted constraint (grilled 2026-07-16):** responsive collapse stays out of scope; any new wide group must be sanity-checked at a realistic minimum window width |
| `RibbonGroup` | Labelled button cluster with painted right-edge separator | Title label pushed to the bottom by a stretch (aligns across groups); large buttons sit side-by-side; small buttons auto-stack in vertical columns of ≤ 3 (`_MAX_SMALL_PER_COL`); a large button **flushes** the open small column |
| `RibbonButton` | Large: 54×54 icon above text, 111 px tall, min-width 81 | |
| `RibbonSmallButton` | Compact: 27×27 icon beside text, 33 px tall, min-width 120 | |

### 3.2 Group API (the only sanctioned way to add controls)

`add_large_button(text, icon, callback, *, checkable=False, shortcut=None)`, `add_small_button(text, icon, callback, *, checkable=False)`, `add_large_menu_button(text, icon, menu)`, `add_small_menu_button(text, icon, menu)` — all return the button.

- Checkable buttons wire `callback` to **`toggled`**; non-checkable to **`clicked`** (`_wire`). A `None` callback is allowed (caller wires signals itself — the Panels dock toggles do this).
- Menu buttons use `InstantPopup`. **Split buttons** (default action + dropdown) are not a group API — callers build them by hand: `add_large_button(...)` then `setMenu` + `setPopupMode(MenuButtonPopup)` (Line/Rectangle/Wall/Floor/Roof/Room all do this).
- There is **no API for arbitrary embedded widgets** (combos, spinboxes). The one existing case (Modify → Text group) reaches into `group.layout().insertLayout(0, ...)` directly — see D3. Any new widget-bearing group must either extend the group API deliberately or accept that pattern; don't invent a third way.

### 3.3 Shortcut scoping (the trap)

`shortcut=` calls `QToolButton.setShortcut`, and a button on a hidden `QStackedWidget` page **does not fire** — ribbon-button shortcuts are effectively tab-scoped. Global hotkeys must be window-level `QShortcut`s or view `keyPressEvent`/`ShortcutOverride` handling instead (F3 precedent: `osnap-toolbar.md`; Ctrl+Z/Y in paper space: `paper-space.md` §17.4). As-built consequences: the Manage-tab Undo/Redo `shortcut="Ctrl+Z"/"Ctrl+Y"` and Analyze-tab `F5`/`F6` only fire while their tab is current — the real global routes live elsewhere (scene/view key handling).

### 3.4 Content ownership (`main.py`)

`init_ribbon()` builds six tabs in order — **Manage** (file I/O, import, settings, snap, undo/redo, gridlines/levels, view, dock-panel toggles), **Draw** (construction geometry, blocks, model-space annotations: Dimension/Text/Hatch), **Build** (walls/floors/roofs/rooms/openings, pipe/sprinkler/water-supply/design-area, library), **Modify** (edit/transform/constraints + selection-contextual Text formatting), **Analyze** (hydraulics, thermal radiation, report export), **Draft** (workspace switch, page setup, plot). It must run **after** the dock widgets exist (Panels toggles bind to them). Each tab is built by a private `_init_<tab>_tab(_I, _btn[, _mode_btn])` helper taking the icon-loader and button-factory closures.

### 3.5 Mode-button protocol

Checkable tool buttons that enter a scene mode register in `self._mode_buttons[mode_name] = btn`; clicking calls `scene.set_mode(mode_name)`. The reverse edge is `scene.modeChanged → _sync_mode_buttons(mode)`: every registered button gets `blockSignals(True); setChecked(btn is active_btn)` — deduped by `id(btn)` because split buttons register under **multiple** mode names (e.g. `wall` and `wall_rect` → one button). New mode buttons must join this dict or they'll stay stuck checked.

### 3.6 Tab behaviors

- **Modify auto-switch:** `scene.selectionChanged → _on_selection_changed_modify` — selecting items while not in a `_DRAW_MODES` mode force-switches the tab strip to Modify (`self.ribbon._tab_bar.setCurrentIndex(self._modify_tab_idx)` — private-attr reach, D4) and enables the selection-dependent button list; empty selection disables them. *Intended design differs — see D8.*
- **Contextual Text group (Modify):** visible only when a model-space `NoteAnnotation` is selected; widgets sync from `get_properties()` under `blockSignals` and write back via `set_property` + `scene.push_undo_state()` per gesture (bypasses the property panel's `_apply_property` — D2).
- **Undo/Redo dispatch:** ribbon Undo/Redo buttons call `_dispatch_undo/_dispatch_redo`, which route on `central_tabs.currentWidget()` — `PaperSpaceWidget` → its `paper_scene.undo_stack`, else model-space `scene.undo()/redo()` (contract owned by `paper-space.md` §17.4).
- **OSNAP surface:** the Manage → Snap group and the OSNAP toolbar toggle are owned by `osnap-toolbar.md` — link, don't restate.

### 3.7 Theming

All ribbon QSS comes from `theme.build_ribbon_qss` at `RibbonBar` construction; `RibbonGroup` label color and separator color read `theme.detect()` live. The module-level `RIBBON_QSS` string in `ribbon_bar.py` is **dead** (kept "for reference" — D1).

## 4. Design Decisions (as-built rationale)

- **Library/content split:** `ribbon_bar.py` imports nothing from the app (only `theme`); every callback, mode string, and dock reference stays in `main.py`. Keeps the widget library trivially reusable and testable.
- **No QMenuBar:** the ribbon replaces it entirely; anything that would be a View-menu toggle becomes a ribbon button (OSNAP Bar precedent).
- **Small-button columns of 3:** matches the 111 px large-button height (3 × 33 px + spacing) so rows align without vertical size negotiation.
- **Fixed 150 px stack:** the ribbon never grows; content that doesn't fit clips. Simplicity over responsive collapse (acceptable at the app's minimum window sizes).

## 5. Acceptance Criteria (for changes to this subsystem)

- [ ] New tabs/groups/buttons are built in an `_init_*_tab` helper via the §3.2 group API (or a deliberate, spec'd API extension for embedded widgets — the sanctioned route once D3's `add_widget` primitive lands).
- [ ] New wide groups verified to fit at a realistic minimum window width (§3.1 clipping constraint).
- [ ] Any new checkable mode button registers in `_mode_buttons` (all aliases for split buttons).
- [ ] No new `shortcut=` on ribbon buttons for hotkeys that must work app-wide (§3.3) — use window-level `QShortcut` or view key handling.
- [ ] Ribbon-originated edits respect the owning subsystem's undo route (paper `QUndoStack` commands / model `push_undo_state`) — never silent direct mutation.
- [ ] Renders correctly in both light and dark themes (QSS from `theme.build_ribbon_qss`).

## 6. Verification Checklist

- [ ] Manual: all six tabs render; group labels align; separators paint.
- [ ] Manual: enter each placement mode from its button — button checks; switching modes unchecks it (incl. split-button aliases).
- [ ] Manual: select an item — Modify tab auto-switches, selection buttons enable; deselect — they disable.
- [ ] Manual: Undo/Redo buttons act on the correct stack from a model tab and a paper tab.

## 7. Divergences Ledger (as-built vs intended)

| # | Divergence | Status |
|---|---|---|
| D1 | `RIBBON_QSS` module constant is dead code (real QSS in `theme.py`). | Cosmetic; delete on next touch of the file header. |
| D2 | **Modify → Text group bypasses the panel write path**: per-gesture `set_property` + `push_undo_state` loops over selection, `QSpinBox` for pt size, no mixed-value handling — parallel to (and older than) the property-panel contract (`property-panel.md` §3.3). Model-space `NoteAnnotation` only. | **Legacy (grilled 2026-07-16):** intended design is **one entity-aware Word-style Font group** serving model-space text *and* sheet text, routed through each subsystem's proper undo path. This group is absorbed by that work (timing decided in the Font-group feature grill); it must NOT be copied for paper items. |
| D3 | **No group API for embedded widgets** — the Text group injects a layout via `group.layout().insertLayout(0, ...)`. | **Gap (grilled 2026-07-16):** extend `RibbonGroup` with a deliberate `add_widget`-style primitive as part of the Font-group feature; the Text group's injection hack migrates to it on absorption. Once built, that primitive is the only sanctioned route. |
| D4 | `main.py` reaches into `self.ribbon._tab_bar` (private) for the Modify auto-switch and modify-tab index. | Latent inconsistency; add a public accessor with cause. |
| D5 | `_init_manage_tab` **shadows its `_btn` helper parameter** by rebinding `_btn = g_file.add_small_menu_button(...)` mid-function — the factory is unusable afterwards (later code happens not to call it). | Fragile; rename the locals on next touch. |
| D6 | Manage → Export group is a permanently-disabled placeholder button. | Intentional stub ("coming soon"); remove or wire when export lands. |
| D7 | **Near-zero test coverage** — only `test_osnap_ui.py` touches the ribbon (Snap group). No tests for mode-button sync, Modify auto-switch, or group layout. | Gap; add coverage opportunistically when touching the ribbon. |
| D8 | **Modify tab is always visible + force-switches on selection** vs the intended design (grilled 2026-07-16): a Revit-style **contextual tab** — hidden when nothing is selected, appears (and activates) on selection, contents **specific to the selected entity type**, disappears on deselect. | Intended direction; as-built stands until a dedicated contextual-tab task (TODO filed 2026-07-16). The Font group and any new contextual surfaces should be designed to slot into this trajectory. |
