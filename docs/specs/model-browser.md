---
status: current          # code-verified as-built behavior; divergences ledger at end
last-verified: 2026-08-27
verified-commit: 987f560
applies-to:
  - firepro3d/model_browser.py
source-tasks: "TODO.md: model browser right-click / Delete-key entity deletion (orphan-gate spec forged on first touch, 2026-08-27)"
---

# Model Browser — Governing Spec

**Date forged:** 2026-08-27 (Phase 1b orphan gate — reverse-engineered from as-built code, then extended for the delete feature)
**Adjacent docs:** `specs/property-panel.md` (the panel selection populates), `specs/project-browser.md` (the *other* tree — sheets/navigation; distinct widget), `specs/underlay-workflow.md` (underlay file/layer nodes + visibility), `architecture/display-system.md` (hide/show overrides)

## 1. Goal

One left-side dock (`ModelBrowser`, a `QTreeWidget`) that lists every **model** entity grouped by category with auto-generated names, kept in two-way sync with the 2D scene selection, and offering per-entity visibility and **deletion**. It is a *view of the scene* — it owns no entity state.

## 2. Motivation

A CAD scene at architectural density is hard to navigate by clicking geometry alone (thin items, overlaps, off-screen entities). The browser gives a structured, always-visible index: find an entity by category, click to select+highlight it in the scene, double-click to zoom to it, and manage its visibility/lifecycle without hunting on canvas.

## 3. Architecture & Constraints

### 3.1 Thin view over the scene
- The browser holds **no entity data**. Every row's identity is `id(entity)` stored in `_ROLE_ENTITY` (`Qt.ItemDataRole.UserRole`); underlay rows store the underlay list index in `_ROLE_UNDERLAY` (`UserRole+1`).
- `_find_entity_by_id` resolves a stored `id()` back to the live object by scanning the scene's entity lists. **Invariant:** rows are only valid within one `refresh()` generation — `id()` is reused after GC, so a stale row must never outlive its rebuild. `refresh()` is the reconciliation point.
- **Perf:** `_find_entity_by_id` is a linear scan across all entity lists; it runs per selected row on selection/context/delete, not per frame. Acceptable at entity counts; do not call it inside paint or per-item loops.

### 3.2 Refresh lifecycle
- `set_scene()` connects `sceneModified` and `underlaysChanged` to a **200 ms debounced** `schedule_refresh` → `_do_refresh` → `refresh()`.
- `refresh()` rebuilds the whole tree from scratch (`clear()` then repopulate), preserving expansion state via text-path keys (`_save_expansion`/`_restore_expansion`).
- The `_syncing` guard brackets every programmatic selection/rebuild so `itemSelectionChanged` / `itemChanged` handlers don't recurse into the scene and back.

### 3.3 Categories listed
Walls, Floors, Roofs, Rooms, Doors, Windows, Pipes, Nodes, Gridlines, Design Areas, Water Supply, and Underlays (file nodes + DXF layer children / PDF page child). Category roots show live counts and are bold.

### 3.4 Selection sync (two-way)
- **Tree → scene:** `_on_selection_changed` clears the scene selection and `setSelected(True)` on each resolved entity, then emits `entitySelected` (single entity or list) so the property panel updates. Underlay **file** nodes route to `_on_underlay_selected` (pan + select-if-unlocked) instead.
- **Scene → tree:** `sync_from_scene()` walks the tree and selects rows whose `_ROLE_ENTITY` matches the scene's current `selectedItems()`. Wrapped in `_syncing`; swallows `RuntimeError` (scene C++ object torn down during shutdown).

### 3.5 Double-click
`_on_item_double_clicked` selects the entity and `fitInView`s the first view on its bounding rect (+50 mm margin).

## 4. Design Decisions

### 4.1 Right-click menu (entity rows)
`_on_context_menu` gathers the resolved entities from the current tree selection (underlay rows short-circuit to `_underlay_context_menu`). For entity rows the menu offers, conditionally on override state:
- **Hide** (when any selected entity is visible) → `scene._hide_items(entities)` + `refresh()`
- **Show** (when any selected entity is hidden) → `scene._show_items(entities)` + `refresh()`
- **Show All Hidden** → `scene._show_all_hidden()` + `refresh()`
- **Delete** → see §4.3.

Hide/Show operate through the display-override system (`_display_overrides["visible"]`), not deletion.

### 4.2 Underlay nodes
File nodes carry a tri-state checkbox (Checked / PartiallyChecked when some DXF layers hidden / Unchecked when the whole underlay is hidden); DXF layer children carry two-state checkboxes toggling `Underlay.hidden_layers`. `_on_tree_item_changed` reconciles these to the underlay model and emits `underlaysChanged` + `push_undo_state()`. Underlay lifecycle (import/remove) lives in `underlay_context_menu.py`, not here.

### 4.3 Deletion (2026-08-27)
- **Trigger surfaces:** a **Delete** action appended to the entity context menu, and the **Delete key** while the tree has focus.
- **Scope:** only **entity** rows (rows whose `_ROLE_ENTITY` resolves to a live entity). Underlay file/layer rows are **excluded** — underlay removal is a separate, non-undoable path owned by the underlay context menu; deleting an underlay from here is out of scope.
- **Mechanism (single home):** the browser does **not** re-implement deletion. It selects the resolved entities in the scene (clear + `setSelected(True)`), then delegates to the scene's canonical `delete_selected_items()` (`model_space.py`) — the exact path the model-view Delete key uses. That method owns the entity-graph bookkeeping (pipes/nodes/sprinklers, water supply, design areas) **and** the single undo push (`push_undo_state()`).
- **Undo:** inherited from `delete_selected_items()` — one undo step restores the whole deletion. The browser adds no undo command of its own (no double-push).
- **Refresh:** `delete_selected_items()` emits `sceneModified` → debounced `refresh()`; the browser does not need an explicit refresh call, but may call one for immediacy.
- **Confirmation:** none — deletion is undoable, matching the model-view Delete-key behavior (no modal on the canvas either).

## 5. Acceptance Criteria

- Selecting entity rows and pressing **Delete** removes exactly those entities from the scene and the tree, via `delete_selected_items()`, and a single **Ctrl+Z** restores them.
- The context-menu **Delete** action does the same as the key.
- Pressing **Delete** on an **underlay** file/layer row does **not** delete via `delete_selected_items()` (underlays are untouched).
- Deletion pushes exactly **one** undo state (no double-push from the browser).
- No stale-`id()` deletion: a row from a superseded `refresh()` generation cannot resolve to and delete a different entity (rows are rebuilt on every scene change).

## 6. Verification Checklist

- [ ] Delete-key on entity rows → entities gone from scene; `delete_selected_items` invoked once.
- [ ] Ctrl+Z restores the deleted entities.
- [ ] Delete-key on an underlay row is a no-op for entity deletion.
- [ ] Mixed selection (entities + underlay rows) deletes only the entities.
- [ ] Empty selection → Delete does nothing (no crash).

## 7. Divergences / Ledger

- None at forge time (2026-08-27). Delete added the same session the spec was forged.
