---
status: proposal          # designed, not yet built
last-verified: 2026-08-22
verified-commit: 5f359ca
applies-to:
  - main.py               # init_ribbon + _init_*_tab helpers + selection→contextual logic
  - firepro3d/ribbon_bar.py
  - firepro3d/font_group.py
  - firepro3d/assets.py    # + new themed icon loader
  - firepro3d/preferences_dialog.py   # new
source-tasks: "TODO.md §Tasks: 'Ribbon overhaul — workflow-ordered restructure + contextual tabs + unified Preferences + icon style-guide' (2026-08-22 grill + brainstorm)"
---

# Ribbon Overhaul — Design Spec

Governing spec this feeds: `docs/specs/ribbon-bar.md` (updated in place at implementation; resolves **D8**). New governing spec forged: `docs/specs/icon-style-guide.md`. This doc is the design-of-record; owned facts (mode-button sync, group API, shortcut scoping) live in `ribbon-bar.md` — linked, not restated (Rule A).

## Goal

Reshape the ribbon from 6 fixed workflow tabs into **7 base tabs + on-demand contextual tabs**, fold the app's scattered settings dialogs into one tabbed **Preferences** dialog, introduce a **themed (light/dark) icon system** with a governing style guide, and audit out dead/duplicate buttons — with **zero loss of reachable functionality** and no `.fpd`/QSettings data break.

## Motivation

The current ribbon grew organically: Build mixes architecture with sprinkler systems, Analyze mixes hydraulics with thermal radiation, settings are spread across ~6 dialogs and 2 ribbon menus, ~49% of buttons show a placeholder icon, and the always-visible Modify tab force-switches on every selection. A workflow-ordered, entity-contextual ribbon (the user's Revit mental model — see `user_revit_mental_model`) makes the tool legible and gives every future setting a single home.

## Architecture & Constraints

Honors the `ribbon-bar.md §3` **library/content split**: `ribbon_bar.py` imports only `theme` and stays dumb; every tab/group/button/callback/registry decision lives in `main.py`. All new checkable mode buttons must join `_mode_buttons` (`ribbon-bar.md §3.5`); no `shortcut=` for app-global hotkeys (`§3.3`); ribbon-originated edits respect the owning subsystem's undo route (`§5`).

### 1. Base-tab roster (7 tabs, in order)

| # | Tab | Groups (contents) |
|---|-----|-------------------|
| 1 | **Manage** | File · Import · **Preferences** (button → unified dialog) · **Edit** (always-visible Undo/Redo) · Snap quick-toggles (OSNAP / Snap-to-Underlay / Angle Snap / OSNAP Bar) |
| 2 | **View** | Navigate (Fit to Screen) · Display (Display Manager) · Panels (Properties / Browser / Hydraulic Report / Radiation Report toggles) |
| 3 | **Create** | Geometry (Line/Rect/Circle/Polyline/Arc/Single-Place) · Blocks (Insert/Create) — *generic 3D solids = follow-up* |
| 4 | **Architecture** *(renamed Build)* | Building (Wall/Floor/Roof/Room/Door/Window/Detail) · Datums (Levels / Gridline) |
| 5 | **Sprinkler Systems** | Layout (Pipe/Sprinkler/Water Supply/Design Area) · Tools (Auto-Populate/Coverage/Sprinkler Manager) · Hydraulics (Run/Clear/Equiv Lengths/Export PDF/Export CSV) |
| 6 | **Analyze** | Thermal Radiation (Run/Clear) |
| 7 | **Draft** | Annotate (model Dimension/Text/Hatch + sheet Add Text) · Font (contextual, existing `FontGroupController`) · Page (Paper Size/Title Block/Refresh/Fit Sheet) · Plot (Export PDF/Print) |

Removed base tabs/groups: the always-visible **Modify** tab (→ contextual), Draft's **Workspace** group (Browser handles Model/Paper/plan/elevation/detail switching via `activateModelSpace`/`activatePaperSheet`/…).

### 2. Contextual-tab mechanism

**Library primitives (`ribbon_bar.py`, dumb):**
- `insert_page(title, index, *, contextual=False) -> RibbonPage` — inserts a `QTabBar` tab and a `QStackedWidget` page **at the same index**, preserving the `_on_tab_changed` index-parity invariant. `contextual=True` sets a tab property (e.g. `setTabData`/dynamic QSS property) so the stylesheet can accent contextual tabs.
- `remove_page(index)` — removes tab + page together.

**Content/registry (`main.py`, owns behavior):**
- **Registry:** `entity-type key → (tab_title, page_builder)`. Every `page_builder` first calls a shared `_build_contextual_edit_group(page)` (Delete/Copy/Cut/Paste/Duplicate); type-specific tools are stubbed (empty) for this task.
- **Resolver:** `_resolve_selection_context(items) -> key | None` — empty → `None`; homogeneous family → its key; mixed families → `"mixed"`. Family keys: `geo2d`, `geo3d` (stub), `annotation`, `wall`, `floor`, `roof`, `room`, `opening` (door+window), `detail`, `pipe`, `sprinkler`, `water_supply`, `design_area`, `gridline`, `level`, `viewport`, `sheet_text`, `mixed`.
- **Selection handler:** `_on_selection_changed_contextual()` replaces `_on_selection_changed_modify`. On a **new** context: remove any current contextual tab, `insert_page` the new one at the fixed index after the last base tab, auto-activate it, and remember the base tab that was active. While the selection persists the contextual tab stays present (the user may click base tabs freely — no yank-back). On **deselect**: `remove_page` it and restore the remembered base tab. A context that equals the current one is a no-op (no churn).
- Wired to **both** `scene.selectionChanged` (model space) and the paper scene's selection signal (paper space); the resolver recognizes paper item types (`viewport`, `sheet_text`).

### 3. Unified Preferences dialog (`preferences_dialog.py`, new)

`PreferencesDialog(QDialog)` = `QVBoxLayout → QTabWidget of panes → QDialogButtonBox(OK/Apply/Cancel)`, modeled on `TitleBlockEditorDialog`. Each pane implements a tiny protocol:
- `load()` — snapshot current state + populate widgets.
- `apply()` — commit staged values to the pane's persistence target.
- `revert()` — restore the snapshot.

**Panes and persistence targets (mixed by design):**
| Pane | Absorbs | Target |
|---|---|---|
| Snapping | `_open_snap_settings` + `_open_snap_tolerance_dialog` (grid/angle, tolerance/grip, 8 snap types, inference) | QSettings + live `snap_engine` |
| Units & Precision | `_build_units_menu` + `_build_precision_menu` | QSettings |
| Import / Conversion | ODA converter path + import-mode/DPI defaults | QSettings |
| General | dock-visibility defaults, restore-on-launch (thin now) | QSettings |
| Project Info | `_open_project_info` | project `_project_info` dict + title-block push |

Buttons: **OK** = apply-all + close; **Apply** = apply-all, stay; **Cancel** = revert-all + close. Panes read/write through a **settings-source** object (QSettings today) so a future **user-profile** layer is additive (follow-up; see `project_user_accounts_future`). The Project-Info pane is only meaningful with a project open. Standalone-and-not-folded (per grill): Display Manager (→ View tab), Import Underlay dialog (workflow), templates (property-panel driven).

### 4. Themed icon system

- **Loader:** `themed_icon(name, theme) -> QIcon` — loads the SVG, substitutes the two token colors per theme via a shared `svg_recolor(svg_bytes, color_map) -> bytes` util (generalized from `display_manager._recolor_svg_bytes`, which becomes a caller of it), caches by `(name, theme)`. **Missing file → a visible themed "missing" glyph** (never a blank icon) + one-time log. The `_I` closure in `init_ribbon` becomes `themed_icon(name, current_theme)`. Icons tint at ribbon-build time (runtime theme-switch is not a current feature).
- **Two-token color model:** every icon uses exactly two semantic roles — `primary` and `accent` — authored with reserved sentinel colors and remapped per theme:

  | Role | Light theme | Dark theme | Authoring sentinel |
  |---|---|---|---|
  | primary | black (`#1A1A1A`) | white (`#F0F0F0`) | `#1A1A1A` |
  | accent | green | blue | `#004CFF` |

  Retheming = edit the two token values only; SVG geometry is untouched.
- **Governing spec:** forge `docs/specs/icon-style-guide.md` (orphan gate — icons have no spec today) covering directory/naming (`{noun}_icon.svg` under `graphics/Ribbon/`), viewBox standard, the primary+accent-only rule + sentinel values + per-theme token table, stroke width/caps, filled-vs-stroke guidance, recolor-friendly layer structure, 54×54 / 27×27 size targets, the missing-icon fallback contract, and the "no `placeholder_icon.svg` in production" coverage mandate. Add its row to `SPEC-INDEX.md`. **Authoring the ~47 missing icons is a follow-up task** (mockup-gated per `feedback_visual_grill_provisional`).

### 5. Audit removals (no functional loss)

Manage **Export** stub (`ribbon-bar.md` D6), dead **`FSVisibilityDialog`**, duplicate Build **"Display"** button, legacy **Modify→Text** group (`ribbon-bar.md` D2). Every dropped command stays reachable via keyboard shortcut, right-click menu, the property panel, or the Browser — verified in acceptance.

## Design Decisions

- **Insert/remove contextual tabs rather than hide** — `QTabBar` has no per-tab hide; inserting/removing tab+page together at a shared index is the only way to keep the `_on_tab_changed` index-parity invariant, and it's simpler than a visibility overlay.
- **Registry + resolver in `main.py`, primitives in `ribbon_bar.py`** — preserves the library/content split; the library never learns about entity types.
- **Always-visible Undo/Redo restored to Manage** — the "remove it" rationale was "it's already in Modify"; with Modify gone, undo needs a persistent mouse-reachable home (keyboard routes are unaffected — `ribbon-bar.md §3.3`).
- **Empty contextual stubs still carry the shared Edit group** — a blank tab reads as broken, and it restores mouse access to Delete/Copy/Paste that the Modify removal would otherwise push to keyboard-only.
- **Pane protocol with a swappable settings-source** — clean mixed persistence now, additive user-profiles later; no rewrite when profiles land.
- **Two-token themed icons** — modern CAD/Office idiom, makes 47 consistent icons tractable and gives real light/dark theming for the price of a color-map substitution.

## Acceptance Criteria

- [ ] 7 base tabs render in order (Manage · View · Create · Architecture · Sprinkler Systems · Analyze · Draft); group labels align; separators paint; both themes.
- [ ] Every migrated mode button still enters its scene mode (mode-button sync intact — `ribbon-bar.md §3.5`); no orphaned callbacks.
- [ ] Contextual tab, driven by **real `scene.selectionChanged`**: selecting each entity family shows the correct tab, auto-activates it, and shows the Edit group; deselect removes it and restores the prior base tab; mixed selection → generic Modify tab; unchanged context → no churn. Same for paper-scene selection (viewport / sheet text).
- [ ] Unified Preferences opens from Manage; each pane persists to the **correct target** (Snapping/Units/Import/General → QSettings; Project Info → project dict + title block); Cancel reverts all; Apply commits without closing.
- [ ] Always-visible Undo/Redo on Manage; Display Manager + Fit + Panels on View.
- [ ] Audit removals done; **no functional command lost** (each verified reachable via shortcut/right-click/panel/Browser).
- [ ] Themed icon loader tints per theme and renders a visible fallback for a missing file (not blank).
- [ ] `docs/specs/ribbon-bar.md` updated in place (D8 resolved + new taxonomy, D2/D6 closed); `docs/specs/icon-style-guide.md` forged + added to SPEC-INDEX; both stamped `last-verified`/`verified-commit`.

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] Functional widget tests pass (tab roster/order, mode-button sync, contextual show/hide via real selection, Preferences persistence targets).
- [ ] No regressions: workspace switching via Browser; all removed-button functions reachable.
- [ ] Manual smoke test in light and dark themes (visual gate).

## Tech Context

- **Framework:** PyQt6 (`QTabBar` + `QStackedWidget` ribbon; `QDialog`/`QTabWidget` for Preferences).
- **Reuse:** `RibbonGroup.add_widget` (embedded widgets, `ribbon-bar.md §3.2`); `TitleBlockEditorDialog`/`DisplayManager` (tabbed-dialog + snapshot-revert patterns); `display_manager._recolor_svg_bytes` (→ generalized `svg_recolor`). Testing per `qapp` fixture (no pytest-qt — `project_no_pytest_qt_use_qapp`), driving shown+activated views (`feedback_test_real_entry_point`).

## Existing Code Context

- `main.py` `init_ribbon` (currently 6 `_init_*_tab` helpers; `_on_selection_changed_modify` auto-switch; `_mode_buttons` sync; `_sync_mode_buttons`).
- `firepro3d/ribbon_bar.py` `RibbonBar._tab_bar`/`_stack`/`_on_tab_changed`/`add_page`.
- `firepro3d/project_browser.py` (navigation signals — the workspace-switch surface).
- Scattered settings: `_open_snap_settings`, `_open_snap_tolerance_dialog`, `_build_units_menu`, `_build_precision_menu`, `_open_project_info`; `fs_visibility_dialog.py` (dead).

## Build Order

**A.** Themed icon loader + forge `icon-style-guide.md` (foundation, low risk). → **B.** Base-tab restructure (mechanical re-parenting; delete Modify tab). → **C.** Contextual-tab mechanism (depends on B). → **D.** Unified Preferences dialog (independent; may run parallel to B/C). Governing-spec updates land with C/D and are stamped at wrap-up.

## Follow-ups (filed in TODO.md)

Author the ~47 missing icons (mockup-gated); populate contextual tabs with type-specific tools; generic 3D solid modeling in Create; migrate Draft→Font into a Sheet Text contextual tab; continue folding settings into Preferences; user-profile settings layer.
