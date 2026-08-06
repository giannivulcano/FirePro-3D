---
status: current
last-verified: 2026-08-05
verified-commit: 8f6cd90
applies-to:
  - firepro3d/project_browser.py
  - main.py (ProjectBrowser wiring in MainWindow.__init__)
source-tasks: ["/todo 2026-08-05 orphan gate — forged before multi-sheet management touched the sheet tree"]
---

# Project Browser — Design Spec

**Adjacent specs:** `paper-space.md` (sheet tree consumer contract, drag-to-sheet placement), `view-relationships.md` (view taxonomy; §"tree widgets, not graphical views"), `titleblock-template-system.md` (none directly — sheets only).

## Goal

A Revit-style dockable **Project Browser** tree that is the navigation hub for every named view in the project — plan views (levels), elevations, detail views, and paper-space sheets — and the drag source for placing model views onto sheets.

## Motivation

The user's mental model is Revit's: views are discovered and opened from a browser tree, and drawings are composed by dragging views onto sheets. The browser decouples navigation UI from `MainWindow` via signals so view-activation logic stays in one place.

## Architecture & Constraints

- **One widget, signal-driven.** `ProjectBrowser(QWidget)` embeds a private `_ProjectTree(QTreeWidget)`. It never touches scenes, managers, or `MainWindow` directly — every user gesture becomes a `pyqtSignal` that `MainWindow` wires in `__init__` (main.py). Data flows *in* through explicit refresh methods, *out* through signals only.
- **Tree item identity via data roles**, not text: `_ROLE_TYPE` (`"model_root" | "ms_stub" | "paper_root" | "sheet" | "plan" | "elevation" | "detail"`) and `_ROLE_NAME` (the view/sheet name). `_ROLE_VIEW` is declared but unused.
- **Drag-only drag/drop.** The tree is a drag *source* (`DragOnly`); drops land on `PaperScene` (paper-space spec §6.1). `_ProjectTree.mimeData` serializes the first draggable item as JSON under the custom MIME type `application/x-firepro3d-view` with keys `view_type` (`"plan" | "elevation" | "detail"`) and `view_name`. Plan names are prefixed at the drag boundary (`"Plan: {level}"`) because that is the `ViewResolver` key format; elevation/detail names pass through raw.
- **Refresh, don't mutate.** Sub-trees rebuild wholesale (`takeChildren()` + repopulate): `refresh_levels()` (from the injected `level_manager`), `refresh_details(names)`, `set_sheets(names)`. There is no incremental item editing API.
- **Theming** via `theme.detect()` tokens (`architecture/theming.md` — Rule A: token values live there).

## Design Decisions

- **Revit-style single browser** over per-view-type toolbars/menus — matches the user's linked-views workflow and gives sheets and model views one home.
- **Stub categories rendered inert** (`Schematics`, `Schedules` under 2D Model, disabled-text color, "Coming soon" tooltip) — the taxonomy is declared up front so future features slot in without re-teaching the tree's shape.
- **Elevations are a fixed cardinal set** (`North/South/East/West`, `_ELEVATIONS`) — mirrors the cardinal-only elevation model (`view-relationships.md`); no dynamic elevation list.
- **Signals carry names (strings), not objects** — the browser holds no references to levels/sheets/details, so stale-object bugs are impossible; `MainWindow` resolves names against the live managers.
- **Pure-push tree state (grill 2026-08-05, binding):** the browser never self-mutates tree structure in response to its own gestures. Gestures emit signals; `MainWindow` mutates data and pushes the authoritative state back via the refresh API. (The as-built `_create_new_sheet` local append violates this — divergence D2, to be removed by the multi-sheet task.)

## Current Behavior

### Tree structure

```
▼ 2D Model                (model_root)
    ▼ Plans               (ms_stub)   ← one child per Level (plan)
    ▼ Elevations          (ms_stub)   ← N/S/E/W (elevation)
    ▶ Details             (ms_stub)   ← populated via refresh_details (detail)
    Schematics, Schedules (ms_stub)   ← inert "Coming soon" stubs
▼ Paper Space             (paper_root)
    Layout 1 …            (sheet)
```

### Signals (all wired in main.py `MainWindow.__init__`)

| Signal | Args | Emitted on | MainWindow handler |
|---|---|---|---|
| `activateModelSpace` | — | activating `model_root` / any `ms_stub` | activate plan view of active level |
| `activatePlanView` | level name | activating a plan item | `_activate_plan_view` |
| `activateElevation` | direction | activating an elevation item | `_activate_elevation` |
| `activateDetailView` | detail name | activating / context-"Open" on a detail | `_activate_detail_view` |
| `deleteDetailView` | detail name | context-"Delete" on a detail | `_delete_detail_view` |
| `activatePaperSheet` | sheet name | activating a sheet item | `_activate_paper_sheet` |
| `createPaperSheet` | new name | context-"New Drawing" (see divergence D2) | `_activate_paper_sheet` (D2) |

Activation = `itemActivated` **and** `itemDoubleClicked`, both connected to the same dispatcher (`_on_item_activated`); on Windows these can double-fire for one double-click — harmless today because every handler is idempotent, but new handlers must stay idempotent or the wiring must be deduplicated.

### Refresh API (callers in parentheses)

- `refresh_levels()` — rebuild Plans from `level_manager.levels`; tooltip shows elevation via the injected `ScaleManager` (`levelsChanged` from level widget + level dialog).
- `refresh_details(names)` — rebuild Details (`MainWindow` after detail-view changes).
- `set_sheets(names)` — rebuild Paper Space children (see divergence D1).
- `set_level_manager(lm)` / `set_scale_manager(sm)` — swap injected managers (project load).
- `set_placed_views(set)` — record which views are placed on sheets for italic styling (see divergence D3).

### Context menus

- `paper_root` / `sheet` → **New Drawing** (prompts `QInputDialog` with auto-generated `Layout {n}` default, appends a tree item locally, emits `createPaperSheet`).
- `detail` → **Open** / **Delete**.
- All other roles → no menu.

## Divergences (as-built gaps, verified 8f6cd90; classifications grilled 2026-08-05)

- **D1 — `set_sheets` has no external caller.** The Paper Space branch shows only the `_build_tree` default `["Layout 1"]`; a loaded project's real sheet name(s) never reach the tree. Single-sheet-era gap; the multi-sheet task must make `MainWindow` push the authoritative sheet list on every load/create/rename/delete/reorder.
- **D2 — `createPaperSheet` creates nothing.** The browser optimistically appends a tree item, but `main.py` connects the signal to `_activate_paper_sheet` — no `Sheet` is created, so the tree shows a phantom entry naming a sheet that doesn't exist (activating it opens the one real sheet). **Bug** (grilled): the optimistic local append violates the pure-push contract and is removed by the multi-sheet task — the tree reflects data pushed back via `set_sheets`, never self-mutates.
- **D3 — `set_placed_views` is dead code.** No caller, so the italic placed-on-sheet styling in `refresh_levels` / `refresh_details` / elevations can never activate. **Intended feature, unwired** (grilled): keep the API; `MainWindow` wires it with multi-sheet (recompute from every `Sheet.sheet_views` on load/`sheetModified`).
- **D4 — `_ROLE_VIEW` declared, never used.**
- **D5 — `activatePaperSheet`'s name argument is ignored** by `_activate_paper_sheet` (single-sheet world; the multi-sheet task makes it meaningful).
- **D6 — drag supports only the first selected item** (`break` in `mimeData`). **Intended** (grilled): multi-view drop has no designed drop-layout semantics; each placement needs individual position/scale.
- **D7 — sheets are not drag-reorderable** (`DragOnly` mode). **Deliberate deferral with confirmed target** (grilled): drag-to-reorder in the tree is the intended order-editing mechanism (`paper-space.md` §14; order = document-set order = batch page order); lands with multi-sheet. Sheet items accept internal moves between sheet siblings only, coexisting with drag-out for view items.

## Multi-sheet design deltas [designed 2026-08-06 — proposal until the multi-sheet build stamps them]

Bound by `paper-space.md §19` (sheet semantics live there — Rule A). Browser-side changes:

- **Sheet rows keyed by number:** `_ROLE_NAME` stores `Sheet.number`; display text `"{number} - {name}"`. `set_sheets` takes `[(number, display), …]`.
- **Signals:** `activatePaperSheet(number)` (double-click); `createPaperSheet()` becomes **parameterless** (instant create — the `QInputDialog` and optimistic local append are deleted, resolving D2); new `deletePaperSheet(number)` (context-menu Delete; `MainWindow` owns the confirm); new `sheetSelected(number)` (single-click selection → sheet properties panel); new `sheetOrderChanged(list[str])` (post-drop, numbers in new tree order).
- **Drag-to-reorder (resolves D7):** guarded `dropEvent` on `_ProjectTree` — internal moves accepted only for sheet rows dropped between sheet siblings; view items stay drag-out-only. After the move the tree emits `sheetOrderChanged`; `MainWindow` reorders the data and pushes `set_sheets` back (pure push — the tree never trusts its own state).
- **Placed-views italics (resolves D3):** `set_placed_views` restyles view rows **in place** (plans, elevations, details — covers elevations, which have no rebuild path); recompute triggers owned by `paper-space.md §19.5`.

## Acceptance Criteria

- [x] Spec documents the as-built tree structure, roles, signals, refresh API, drag payload, and context menus (verified against `project_browser.py` @ 8f6cd90).
- [x] All known gaps recorded as divergences D1–D7 rather than silently specced as intended behavior.
- [ ] Multi-sheet task resolves D1/D2/D5 (and decides D7) — update this spec in place when it lands.

## Verification Checklist

- [ ] On next touch: re-verify signal wiring table against `main.py` and stamp `last-verified` / `verified-commit`.
- [ ] Rule A: theming tokens, ViewResolver name formats, and sheet-tree feature targets stay owned by `architecture/theming.md`, `paper-space.md` — this spec links, never restates values.
