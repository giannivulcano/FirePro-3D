---
status: current          # code-verified as-built behavior; divergences ledger at end
last-verified: 2026-08-22
verified-commit: ce37220
applies-to:
  - firepro3d/ribbon_bar.py
  - firepro3d/font_group.py
  - firepro3d/icons.py
  - firepro3d/preferences_dialog.py
  - main.py (init_ribbon + _init_*_tab helpers + contextual-tab mechanism + mode-button sync)
source-tasks: "TODO.md §B follow-up: Draft-tab migration + Font ribbon group (orphan-gate spec forged on first touch); ribbon-overhaul 2026-08-22 (7 tabs + contextual + Preferences + icons)"
---

# Ribbon Bar — Governing Spec

**Date forged:** 2026-07-16 (Phase 1b orphan gate — reverse-engineered from as-built code)
**Adjacent docs:** `specs/osnap-toolbar.md` (Snap group + OSNAP toolbar toggle — owns that surface), `architecture/theming.md` (QSS ownership), `specs/paper-space.md` §17.4 (paper undo dispatch contract), `specs/property-panel.md` (the panel the ribbon must not bypass — see D2), `specs/icon-style-guide.md` (icon authoring contract — owns all icon token/color/naming facts)

## 1. Goal

A Microsoft-Office-style ribbon is the app's sole primary command surface (there is **no `QMenuBar`**): a tab strip over a fixed-height stack of pages, each page a horizontal row of labelled button groups. `ribbon_bar.py` is the generic widget library; `main.py` owns all content (which tabs/groups/buttons exist and what they do).

## 2. Motivation

CAD users get a workflow-ordered command surface instead of nested menus. The library/content split keeps `ribbon_bar.py` reusable and dumb; every behavioral decision (mode wiring, contextual-tab logic, dispatch) lives with the window that owns the scene.

**Contract vs as-built (grilled 2026-07-16):** the *principle* — a workflow-ordered ribbon as sole command surface — is the contract. The specific tab split is as-built, open to reshaping with a coherent workflow story.

**Target taxonomy (decided 2026-07-16, executed 2026-08-22):** the old six-tab split (Manage / Draw / Build / Modify / Analyze / Draft) is superseded. The as-built structure is **7 base tabs** (Manage → View → Create → Architecture → Sprinkler Systems → Analyze → Draft) plus on-demand contextual tabs (§3.8). The always-visible Modify tab was **removed** (D2, D8 resolved); contextual tabs now carry selection-specific commands. Draft = annotations (model + sheet) + page setup + plot (Draw/annotation merge executed). The previously deferred "Draw → Draft annotation migration" has landed.

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
- Menu buttons use `InstantPopup`. **Split buttons** (default action + dropdown) are not a group API — callers build them by hand: `add_large_button(...)` then `setMenu` + `setPopupMode(MenuButtonPopup)` (Wall/Floor/Roof/Room all do this).
- **Embedded widgets go through `add_widget(widget)`** (built 2026-07-16, resolving D3): parents the widget into the button row, flushing any open small-button column. This is the ONLY sanctioned route — never inject into a group's layouts directly. First consumer: the Draft-tab Font group (`font_group.py` `FontGroupController.container`).

### 3.3 Shortcut scoping (the trap)

`shortcut=` calls `QToolButton.setShortcut`, and a button on a hidden `QStackedWidget` page **does not fire** — ribbon-button shortcuts are effectively tab-scoped. Global hotkeys must be window-level `QShortcut`s or view `keyPressEvent`/`ShortcutOverride` handling instead (F3 precedent: `osnap-toolbar.md`; Ctrl+Z/Y in paper space: `paper-space.md` §17.4). As-built consequences: the Manage-tab Undo/Redo `shortcut="Ctrl+Z"/"Ctrl+Y"` and Sprinkler Systems-tab `F5`/`F6` only fire while their tab is current — the real global routes live elsewhere (scene/view key handling).

### 3.4 Content ownership (`main.py`)

`init_ribbon()` builds **7 base tabs** in order via private `_init_<tab>_tab` helpers, then calls `_init_contextual_tabs()` to build the contextual-tab registry. It must run **after** the dock widgets exist (Panels toggles bind to them). Ribbon widgets wired to signals connected in `__init__` (pre-`init_ribbon`) must be reached through `getattr(self, ..., None)` guards — those signals can fire before the ribbon exists.

**Base-tab content overview:**

| # | Tab | Groups |
|---|-----|--------|
| 1 | **Manage** | File (New/Open/Save/Save As/Recent) · Settings (Preferences button → `PreferencesDialog`) · Edit (Undo/Redo, always accessible) · Snap (OSNAP/Snap-to-Underlay/Angle Snap/Snap Settings/OSNAP Bar) |
| 2 | **View** | Navigate (Fit to Screen) · Underlay (Underlay Manager → import dialog/Refresh All) · Display (Display Manager) · Panels (Properties/Browser/Hydraulic Report/Radiation Report dock toggles) |
| 3 | **Create** | Geometry (Line/Rectangle/Circle/Polyline/Arc/Single-Place) · Blocks (Insert Block/Create Block) |
| 4 | **Architecture** | Building (Wall/Floor/Roof/Room/Door/Window/Detail) · Datums (Levels/Gridline) |
| 5 | **Sprinkler Systems** | Layout (Pipe/Sprinkler/Water Supply/Design Area) · Tools (Auto-Populate/Coverage Overlay/Sprinkler Manager) · Hydraulics (Run Hydraulics/Clear Results/Equiv Lengths/Export PDF/Export CSV) |
| 6 | **Analyze** | Thermal Radiation (Run Radiation/Clear Radiation) |
| 7 | **Draft** | Page (Paper Size/Title Block/Refresh Viewports/Fit Sheet) · Annotate (Dimension/Text/Hatch + sheet Add Text) · Font (`FontGroupController` embedded via `add_widget`) · Plot (Export PDF/Print) |

The **Modify tab was removed** (D2, D8 resolved). The old Manage Export stub was removed (D6 resolved).

**Preferences button (Manage → Settings):** opens `firepro3d.preferences_dialog.PreferencesDialog` — a `QTabWidget`-based dialog with 5 panes: Snapping / Units & Precision / Import & Conversion / General / Project Info. Each pane implements a `load()`/`apply()`/`revert()` protocol; OK = apply-all + close, Apply = apply-all + stay, Cancel = revert-all + close. A dedicated governing spec for `PreferencesDialog` is a filed follow-up; for design-of-record see `docs/superpowers/specs/2026-08-22-ribbon-overhaul-design.md §3`.

### 3.5 Mode-button protocol

Checkable tool buttons that enter a scene mode register in `self._mode_buttons[mode_name] = btn`; clicking calls `scene.set_mode(mode_name)`. The reverse edge is `scene.modeChanged → _sync_mode_buttons(mode)`: every registered button gets `blockSignals(True); setChecked(btn is active_btn)` — deduped by `id(btn)` because split buttons register under **multiple** mode names (e.g. `wall` and `wall_rect` → one button). New mode buttons must join this dict or they'll stay stuck checked.

### 3.6 Tab behaviors

- **Contextual tab show/hide:** `scene.selectionChanged → _on_selection_changed_contextual` (§3.8). Supersedes the old Modify auto-switch (`_on_selection_changed_modify` — removed).
- **Contextual Text group (legacy — NoteAnnotation only):** the old Modify → Text group was removed. Model-space text formatting is now routed through the contextual Annotation tab's Edit group (and the property panel for full formatting).
- **Undo/Redo dispatch:** ribbon Undo/Redo buttons (Manage → Edit) call `_dispatch_undo/_dispatch_redo`, which route on `central_tabs.currentWidget()` — `PaperSpaceWidget` → its `paper_scene.undo_stack`, else model-space `scene.undo()/redo()` (contract owned by `paper-space.md` §17.4).
- **OSNAP surface:** the Manage → Snap group and the OSNAP toolbar toggle are owned by `osnap-toolbar.md` — link, don't restate.

### 3.7 Theming

All ribbon QSS comes from `theme.build_ribbon_qss` at `RibbonBar` construction; `RibbonGroup` label color and separator color read `theme.detect()` live. The module-level `RIBBON_QSS` string in `ribbon_bar.py` is **dead** (kept "for reference" — D1).

Ribbon icons are loaded via **`firepro3d.icons.themed_icon(name, theme)`** — a two-token themed model (primary + accent roles, remapped per theme at load time). See `specs/icon-style-guide.md` for the full authoring contract, sentinel colors, per-theme token table, and fallback behavior. Do not restate token values here (Rule A: owned by `icon-style-guide.md`). The `_I` closure in `init_ribbon` calls `themed_icon(name, current_theme)` and is evaluated once at ribbon-build time (runtime theme-switch is not a current feature).

### 3.8 Contextual tabs

**Mechanism overview:** a contextual tab appears on-demand when an entity family is selected; it disappears when the selection is cleared. The always-visible Modify tab is gone — contextual tabs replace it. (The `geo2d` family + its "2D Geometry" placement group is governed by `2d-geometry.md`; `RegularPolygonItem` is a `geo2d` member.)

**Library primitives (`ribbon_bar.py` — dumb, no entity knowledge):**

- `insert_page(title, index, *, contextual=False) -> RibbonPage` — inserts a `QTabBar` entry and a `QStackedWidget` page **at the same index**, preserving `_on_tab_changed` index-parity. `contextual=True` sets `setTabData(index, "contextual")` so the stylesheet can accent contextual tabs differently.
- `remove_page(index)` — removes the tab entry and its stacked page together; calls `deleteLater()` on the widget.

**Content & registry (`main.py` — owns all behavioral decisions):**

- **`_CONTEXTUAL_TABS`** (class-level `dict[str, str]`): maps family key → human-readable tab title. Current catalog: `geo2d`, `geo3d`, `annotation`, `wall`, `floor`, `roof`, `room`, `opening`, `detail`, `pipe`, `sprinkler`, `water_supply`, `design_area`, `gridline`, `level`, `viewport`, `sheet_text`, `mixed` (→ "Modify").
- **`_contextual_registry`** (instance, built in `_init_contextual_tabs()`): maps family key → `(title, page_builder)` callable. The **`geo2d`** key uses a dedicated `_build_geo2d_context` builder (2026-08-22 — Placement + Fill groups, then the shared Edit group); all other keys still use `_build_contextual_edit_group`. Remaining type-specific tools are a filed follow-up.
- **`_contextual_index`**: fixed slot = 7 (one past the 7th base tab) where the contextual tab is always inserted.
- **`_active_contextual_key`**: the currently visible family key, or `None` when no contextual tab is shown.
- **`_pre_contextual_tab`**: the base-tab index to restore on deselect; captured only on the `None → contextual` transition so contextual-to-contextual swaps (wall → pipe) never overwrite the saved base.
- **`_family_key_for(item) -> str | None`**: maps a scene item to its family key, or `None` for items with no contextual family (underlays, badges, helper child items). Subclass-before-base ordering is observed (DoorOpening/WindowOpening before WallOpening).
- **`_resolve_selection_context(items) -> str | None`**: empty list or no mappable items → `None`; all items in the same family → that family key; items in multiple families → `"mixed"`.
- **`_on_selection_changed_contextual()`**: wired to `scene.selectionChanged`. Transition table:
  - **No change** (key == `_active_contextual_key`): no-op.
  - **`None → contextual`**: capture `_pre_contextual_tab`; `insert_page` + activate.
  - **`contextual → contextual`** (key change): `remove_page` old; `insert_page` + activate new (pre-tab stays from the original `None → contextual` capture).
  - **`contextual → None`**: `remove_page`; restore `_pre_contextual_tab`.

**Shared Edit group:** `_build_contextual_edit_group(page)` adds a single "Edit" group to any contextual page containing 5 small buttons: Delete / Copy / Cut / Paste / Duplicate. It is on **every** contextual tab. The **`geo2d`** tab additionally carries a **Placement group** (Level combo + Level Offset `DimensionEdit`, via the reusable `_build_placement_group`) and a **Fill group** (Fill type / Pattern / Fill Colour / Fill Opacity, enabled only when a fillable shape is selected) — the first type-specific contextual tools (2026-08-22); writes route through the scene undo path (`push_undo_state` + `set_property`). Remaining families' type-specific tools are a filed follow-up. A blank contextual tab was rejected (reads as broken; Edit group restores mouse-accessible clipboard/delete that removing Modify would otherwise push to keyboard-only).

**Scope note:** the contextual tab mechanism is currently **model-scene-driven only** (`scene.selectionChanged`). Paper-scene parity (paper items triggering `viewport`/`sheet_text` contextual tabs) is a filed follow-up.

## 4. Design Decisions (as-built rationale)

- **Library/content split:** `ribbon_bar.py` imports nothing from the app (only `theme`); every callback, mode string, registry entry, and dock reference stays in `main.py`. Keeps the widget library trivially reusable and testable.
- **No QMenuBar:** the ribbon replaces it entirely; anything that would be a View-menu toggle becomes a ribbon button (OSNAP Bar precedent).
- **Small-button columns of 3:** matches the 111 px large-button height (3 × 33 px + spacing) so rows align without vertical size negotiation.
- **Fixed 150 px stack:** the ribbon never grows; content that doesn't fit clips. Simplicity over responsive collapse (acceptable at the app's minimum window sizes).
- **Insert/remove contextual tabs (not hide):** `QTabBar` has no per-tab hide API; inserting/removing tab+page together at a shared index is the only way to maintain `_on_tab_changed` index-parity, and it's simpler than a visibility overlay.
- **Always-visible Undo/Redo on Manage:** with Modify removed, undo needs a persistent mouse-reachable home (keyboard routes are unaffected — §3.3).
- **Shared Edit group on every contextual stub:** restores mouse access to Delete/Copy/Paste that removing Modify would otherwise push to keyboard-only.

## 5. Acceptance Criteria (for changes to this subsystem)

- [ ] New tabs/groups/buttons are built in an `_init_*_tab` helper via the §3.2 group API (or the sanctioned `add_widget` route for embedded widgets).
- [ ] New wide groups verified to fit at a realistic minimum window width (§3.1 clipping constraint).
- [ ] Any new checkable mode button registers in `_mode_buttons` (all aliases for split buttons).
- [ ] No new `shortcut=` on ribbon buttons for hotkeys that must work app-wide (§3.3) — use window-level `QShortcut` or view key handling.
- [ ] Ribbon-originated edits respect the owning subsystem's undo route (paper `QUndoStack` commands / model `push_undo_state`) — never silent direct mutation.
- [ ] Renders correctly in both light and dark themes (QSS from `theme.build_ribbon_qss`; icons via `themed_icon`).
- [ ] New entity types that need selection-contextual commands get a `_CONTEXTUAL_TABS` entry, a `_family_key_for` branch, and a builder registered in `_contextual_registry`.

## 6. Verification Checklist

- [ ] Manual: all 7 base tabs render; group labels align; separators paint; both themes.
- [ ] Manual: enter each placement mode from its button — button checks; switching modes unchecks it (incl. split-button aliases).
- [ ] Manual: select an entity — correct contextual tab appears and auto-activates; deselect — it disappears and the prior base tab is restored.
- [ ] Manual: mixed-family selection shows the "Modify" tab; unchanged context is a no-op (no churn).
- [ ] Manual: Undo/Redo buttons act on the correct stack from a model tab and a paper tab.
- [ ] Manual: Preferences opens; each pane persists to its target; Cancel reverts.

## 7. Divergences Ledger (as-built vs intended)

| # | Divergence | Status |
|---|---|---|
| D1 | `RIBBON_QSS` module constant is dead code (real QSS in `theme.py`). | Cosmetic; delete on next touch of the file header. |
| D2 | **Modify → Text group bypassed the panel write path.** The legacy always-visible Modify tab and its Text group have been removed. | **Resolved 2026-08-22** — Modify tab removed; NoteAnnotation text formatting now routes through the property panel and the contextual Annotation tab (Edit group). |
| D3 | ~~No group API for embedded widgets~~ | **Resolved 2026-07-16** — `RibbonGroup.add_widget` built (§3.2); the Font group uses it. |
| D4 | `main.py` reaches into `self.ribbon._tab_bar` (private) in `_on_selection_changed_contextual` and `_init_contextual_tabs` for index read/write. | Latent inconsistency; add a public accessor with cause when it creates friction. |
| D5 | `_init_manage_tab` **shadows its `_btn` helper parameter** by rebinding `_btn = g_file.add_small_menu_button(...)` mid-function — the factory is unusable afterwards (later code happens not to call it). | Fragile; rename the locals on next touch. |
| D6 | ~~Manage → Export group was a permanently-disabled placeholder button.~~ | **Resolved 2026-08-22** — stub removed during Manage-tab restructure. |
| D7 | **Near-zero test coverage** — only `test_osnap_ui.py` touches the ribbon (Snap group). Contextual-tab behavior covered by `test_ribbon_restructure.py` (Preferences, 7-tab roster); mode-button sync and contextual show/hide via real selection need more coverage. | Gap; add coverage opportunistically when touching the ribbon. |
| D8 | ~~Modify tab always visible + force-switching on selection~~ vs intended Revit-style contextual tab. | **Resolved 2026-08-22** — contextual-tab mechanism built (§3.8); Modify tab removed; `_on_selection_changed_modify` replaced by `_on_selection_changed_contextual`. |
| D9 | **Paper-scene contextual parity deferred.** The `viewport` and `sheet_text` family keys exist in `_CONTEXTUAL_TABS` but `_on_selection_changed_contextual` only wires to `scene.selectionChanged` (model scene). Paper-space selection does not yet trigger contextual tabs. | Filed follow-up. |
