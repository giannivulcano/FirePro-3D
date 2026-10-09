---
status: current
last-verified: 2026-10-09  # SV2 Account: schematic leaf drag + placed italics verified against project_browser.py; prior 2026-10-08  # SV1 Account: Schematics root / roles / 4 signals / refresh_schematics verified against project_browser.py + main.py; prior 2026-09-30  # closable 3D tab: 3D Model leaf + activate3DView; full signal table re-verified; prior 2026-09-19
verified-commit: 7dd64383   # prior b851b1aa; prior f1d8151; prior 2330ae8
applies-to:
  - firepro3d/project_browser.py
  - main.py (ProjectBrowser wiring in MainWindow.__init__)
source-tasks: ["/todo 2026-08-05 orphan gate — forged before multi-sheet management touched the sheet tree", "todo_open.md — 3D Model canvas tab is closable and reopenable from the Project Browser (2026-09-30)"]
---

> **Chrome note (2026-09-19, Stage-2 revamp).** The dock host is a custom
> `ui_kit.LeftTabs` (west-edge vertical tabs), not a West `QTabWidget` — see
> `mainwindow-chrome-revamp-stage2.md`. The `ProjectBrowser` widget itself is
> unchanged (single tree); only its container + tone (body `surface`) changed.

# Project Browser — Design Spec

**Adjacent specs:** `paper-space.md` (sheet tree consumer contract, drag-to-sheet placement), `view-relationships.md` (view taxonomy; §"tree widgets, not graphical views"), `view-3d.md` (the `3D Model` leaf's behaviour — §10 I3), `titleblock-template-system.md` (none directly — sheets only).

## Goal

A Revit-style dockable **Project Browser** tree that is the navigation hub for every named view in the project — the 3D Model view, plan views (levels), elevations, detail views, and paper-space sheets — and the drag source for placing model views onto sheets.

## Motivation

The user's mental model is Revit's: views are discovered and opened from a browser tree, and drawings are composed by dragging views onto sheets. The browser decouples navigation UI from `MainWindow` via signals so view-activation logic stays in one place.

## Architecture & Constraints

- **One widget, signal-driven.** `ProjectBrowser(QWidget)` embeds a private `_ProjectTree(QTreeWidget)`. It never touches scenes, managers, or `MainWindow` directly — every user gesture becomes a `pyqtSignal` that `MainWindow` wires in `__init__` (main.py). Data flows *in* through explicit refresh methods, *out* through signals only.
- **Tree item identity via data roles**, not text: `_ROLE_TYPE` (`"view3d" | "model_root" | "ms_stub" | "paper_root" | "sheet" | "plan" | "elevation" | "detail" | "schematic_root" | "schematic_series" | "schematic"`) and `_ROLE_NAME` (the view/sheet name; unset on the `view3d` leaf). `_ROLE_VIEW` is declared but unused.
- **Drag-out + guarded internal drop.** The tree is a drag *source* for view items; drops of views land on `PaperScene` (paper-space spec §6.1). The tree's own drop mode is `DragDrop` with `IgnoreAction` default, used only for the guarded internal sheet reorder (D7). `_ProjectTree.mimeData` serializes the first draggable item as JSON under the custom MIME type `application/x-firepro3d-view` with keys `view_type` (`"plan" | "elevation" | "detail"`) and `view_name`. Plan names are prefixed at the drag boundary (`"Plan: {level}"`) because that is the `ViewResolver` key format; elevation/detail names pass through raw.
- **Refresh, don't mutate.** Sub-trees rebuild wholesale (`takeChildren()` + repopulate): `refresh_levels()` (from the injected `level_manager`), `refresh_details(names)`, `set_sheets(names)`. There is no incremental item editing API.
- **Theming** via `theme.detect()` tokens (`architecture/theming.md` — Rule A: token values live there).

## Design Decisions

- **Revit-style single browser** over per-view-type toolbars/menus — matches the user's linked-views workflow and gives sheets and model views one home.
- **Stub category rendered inert** (`Schedules` under 2D Model; `Schematics` is live since SV1 — see "Schematics root (SV1)", disabled-text color, "Coming soon" tooltip) — the taxonomy is declared up front so future features slot in without re-teaching the tree's shape.
- **Elevations are a fixed cardinal set** (`North/South/East/West`, `_ELEVATIONS`) — mirrors the cardinal-only elevation model (`view-relationships.md`); no dynamic elevation list.
- **Signals carry names (strings), not objects** — the browser holds no references to levels/sheets/details, so stale-object bugs are impossible; `MainWindow` resolves names against the live managers.
- **Pure-push tree state (grill 2026-08-05, binding):** the browser never self-mutates tree structure in response to its own gestures. Gestures emit signals; `MainWindow` mutates data and pushes the authoritative state back via the refresh API. (The as-built `_create_new_sheet` local append violates this — divergence D2, to be removed by the multi-sheet task.)

## Current Behavior

### Tree structure

```
  3D Model                (view3d)    ← top-level leaf, first row; not draggable
▼ 2D Model                (model_root)
    ▼ Plans               (ms_stub)   ← one child per Level (plan)
    ▼ Elevations          (ms_stub)   ← N/S/E/W (elevation)
    ▶ Details             (ms_stub)   ← populated via refresh_details (detail)
    Schematics            (schematic_root) ← Series ▸ leaf, populated via refresh_schematics
    Schedules             (ms_stub)   ← inert "Coming soon" stub
▼ Paper Space             (paper_root)
    Layout 1 …            (sheet)
```

### Signals (all wired in main.py `MainWindow.__init__`)

Re-verified against `main.py` at `f1d8151` (every row: connect site + handler).

| Signal | Args | Emitted on | MainWindow handler |
|---|---|---|---|
| `activate3DView` | — | activating the `view3d` leaf / its context-"Open" | `View3DTabController.open` (`self.view3d_tab.open` — reinsert leftmost + current; idempotent; `view-3d.md §10 I3`) |
| `activateModelSpace` | — | activating `model_root` / any `ms_stub` | lambda → `_activate_plan_view(scene.active_level)` |
| `activatePlanView` | level name | activating a plan item | `_activate_plan_view` |
| `activateElevation` | direction | activating an elevation item | `_activate_elevation` |
| `activateDetailView` | detail name | activating / context-"Open" on a detail | `_activate_detail_view` |
| `deleteDetailView` | detail name | context-"Delete" on a detail | `_delete_detail_view` |
| `activatePaperSheet` | sheet **number** | activating a sheet item / context-"Open" | `_activate_paper_sheet(number)` |
| `createPaperSheet` | — | context-"New Drawing" (instant create) | `_create_sheet` |
| `deletePaperSheet` | sheet number | context-"Delete" on a sheet | `_delete_sheet` (owns the confirm) |
| `sheetSelected` | sheet number | single-click selection of a sheet row | `_on_browser_sheet_selected` (sheet props → panel; skipped in Add-Text mode) |
| `createSchematic` | — | root context-"New Schematic…" | `_new_schematic` |
| `activateSchematic` | definition id | activating / context-"Open" on a schematic leaf | `_open_schematic` |
| `renameSchematic` | definition id | context-"Rename…" on a leaf | `_rename_schematic` |
| `deleteSchematic` | definition id | context-"Delete" on a leaf | `_delete_schematic` |
| `sheetOrderChanged` | numbers, new order | internal sheet drag-drop (`sheetDropped` → order computation) | `_reorder_sheets` (reorder + reconcile push) |

Activation = `itemActivated` **and** `itemDoubleClicked`, both connected to the same dispatcher (`_on_item_activated`); on Windows these can double-fire for one double-click — harmless today because every handler is idempotent, but new handlers must stay idempotent or the wiring must be deduplicated.

### Refresh API (callers in parentheses)

- `refresh_levels()` — rebuild Plans from `level_manager.levels`; tooltip shows elevation via the injected `ScaleManager` (`levelsChanged` from level widget + level dialog).
- `refresh_details(names)` — rebuild Details (`MainWindow` after detail-view changes).
- `set_sheets([(number, display), …])` — rebuild Paper Space children from the authoritative list (`MainWindow._push_sheet_list` on every load/sheet-op/`_on_paper_modified`). The whole rebuild is signal-blocked and preserves the selected sheet row by number (D1 resolved 2026-08-07).
- `set_level_manager(lm)` / `set_scale_manager(sm)` — swap injected managers. **No caller in `main.py`** at `f1d8151`: the browser keeps the construction-time managers across project new/open (see divergence D8).
- `set_placed_views(set)` — record which views are placed on sheets for italic styling (see divergence D3).

### Context menus

- `paper_root` / `sheet` → **New Drawing** (emits parameterless `createPaperSheet` — instant create, no dialog, no local append; D2). `sheet` adds **Open** (`activatePaperSheet(number)`) and **Delete** (`deletePaperSheet(number)`).
- `detail` → **Open** / **Delete**.
- `view3d` → **Open** (`activate3DView`).
- `schematic_root` → **New Schematic…**; `schematic` → **Open / Rename… / Delete** (see "Schematics root (SV1)").
- All other roles → no menu.

### Schematics root (SV1)

The Schematics root, Series rows and leaves, their verbs and the push API
`refresh_schematics(rows)` are owned by [`schematics.md`](schematics.md) D-S4/D-S16
(as built: its "SV1 as built" section). Since SV2 (2026-10-09) leaves drag a
schematic viewport (`mimeData` → `MIME_VIEW` `{"view_type": "schematic", "view_name":
<definition id>}`) and are italic while placed — `set_placed_views` walks the
Schematics root, keyed `("schematic", id)` — schematics.md D-S8 / "SV2 as built".
Root and Series rows are folders (no activation signal, not draggable).

## Divergences (classifications grilled 2026-08-05; D1/D2/D3/D5/D7 **resolved by the multi-sheet build, 2026-08-07**)

- **D1 — RESOLVED.** `MainWindow._push_sheet_list` pushes the authoritative `(number, display)` list on every load/sheet-op/paper-mutation; the `_build_tree` "Layout 1" default is gone (tree starts empty until pushed).
- **D2 — RESOLVED.** The optimistic local append and `QInputDialog` are deleted; `createPaperSheet()` is parameterless and `MainWindow._create_sheet` owns instant creation (auto number, becomes active). The tree never self-mutates (pure-push contract honored; drop-onto-self is an explicit no-op).
- **D3 — RESOLVED.** `set_placed_views` restyles view rows **in place** (plans, elevations, details) and is driven by `MainWindow._recompute_placed_views` from every `Sheet.sheet_views` on load/`_on_paper_modified`/sheet ops.
- **D4 — `_ROLE_VIEW` declared, never used.** (Still latent.)
- **D5 — RESOLVED.** `activatePaperSheet` carries the sheet **number** (identity) and `_activate_paper_sheet(number)` switches sheets by it.
- **D6 — drag supports only the first selected item** (`break` in `mimeData`). **Intended** (grilled): multi-view drop has no designed drop-layout semantics; each placement needs individual position/scale.
- **D7 — RESOLVED.** Internal sheet drag-reorder via guarded `dropEvent` (`application/x-firepro3d-sheet` mime; accepts only sheet-row/paper-root targets; `IgnoreAction` — Qt never moves the item; emits `sheetDropped` → order computed → `sheetOrderChanged`), coexisting with drag-out for view items. UX polish note: the drop cursor shows over non-sheet rows even though the drop is rejected (follow-up filed).
- **D8 — stale `ScaleManager` (recorded 2026-09-30 at Account, pre-existing; follow-up to be filed).** `MainWindow` constructs the browser with `scene.scale_manager` and never calls `set_scale_manager`, but `scene_io` replaces `scene.scale_manager` on project load/new — so the level-tooltip elevation (`format_length`) uses the construction-time manager's units afterwards. The twin of `view-3d.md` D1 (fixed there by `reset_for_project`). `set_level_manager` likewise has no caller (the scene's level manager is not replaced on load, so that one is harmless).

## Multi-sheet design deltas [designed 2026-08-06; as-built 2026-08-07]

Bound by `paper-space.md §19` (sheet semantics live there — Rule A). Browser-side changes:

- **Sheet rows keyed by number:** `_ROLE_NAME` stores `Sheet.number`; display text `"{number} - {name}"`. `set_sheets` takes `[(number, display), …]`.
- **Signals:** `activatePaperSheet(number)` (double-click); `createPaperSheet()` becomes **parameterless** (instant create — the `QInputDialog` and optimistic local append are deleted, resolving D2); new `deletePaperSheet(number)` (context-menu Delete; `MainWindow` owns the confirm); new `sheetSelected(number)` (single-click selection → sheet properties panel); new `sheetOrderChanged(list[str])` (post-drop, numbers in new tree order).
- **Drag-to-reorder (resolves D7):** guarded `dropEvent` on `_ProjectTree` — internal moves accepted only for sheet rows dropped between sheet siblings; view items stay drag-out-only. After the move the tree emits `sheetOrderChanged`; `MainWindow` reorders the data and pushes `set_sheets` back (pure push — the tree never trusts its own state).
- **Placed-views italics (resolves D3):** `set_placed_views` restyles view rows **in place** (plans, elevations, details — covers elevations, which have no rebuild path); recompute triggers owned by `paper-space.md §19.5`.

## Acceptance Criteria

- [x] Spec documents the as-built tree structure, roles, signals, refresh API, drag payload, and context menus (verified against `project_browser.py` @ 91a1d38).
- [x] All known gaps recorded as divergences D1–D7 rather than silently specced as intended behavior.
- [x] Multi-sheet task resolved D1/D2/D3/D5/D7 (2026-08-07); D4/D6 remain intended/latent; D8 recorded 2026-09-30 (open).
- [x] Closable-3D-tab build (2026-09-30, `f1d8151`): top-level `3D Model` leaf (role `view3d`) above `2D Model`, not draggable, `activate3DView` on activation + context-menu Open (guards: `tests/test_project_browser_3d.py`).

## Verification Checklist

- [x] Signal wiring table re-verified against `main.py` and stamped (2026-09-30, `f1d8151`). Re-verify on next touch.
- [ ] Rule A: theming tokens, ViewResolver name formats, and sheet-tree feature targets stay owned by `architecture/theming.md`, `paper-space.md` — this spec links, never restates values.
