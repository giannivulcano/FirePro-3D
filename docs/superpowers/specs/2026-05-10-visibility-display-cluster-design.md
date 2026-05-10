# Visibility & Display Cluster Design

**Date:** 2026-05-10
**Status:** Approved
**Scope:** Three targeted fixes to pipe/fitting visibility and riser plan-view representation.

---

## 1. Goal

Fix three visibility issues: (1) user-hidden items reappear after level switch, (2) vertical risers are invisible in plan view, (3) fittings cannot be hidden/managed from the model browser.

## 2. Motivation

- Hidden items reappearing breaks user trust in the hide/show workflow.
- Risers passing through a floor are completely invisible in plan view, making multi-level designs unreadable. Fire protection drawings conventionally show a yin-yang / broken-pipe symbol at riser XY locations.
- Fittings are the only visible entity type without a model browser group, so users cannot hide/show them selectively.

---

## 3. Architecture & Constraints

**Approach:** Targeted fixes following existing patterns. No new subsystems or architectural changes.

- Task 1 modifies `level_manager.py` only (2-line guard).
- Task 2 adds an SVG asset and extends `Pipe` to manage a riser symbol (same pattern as pipe labels).
- Task 3 adds a Fittings group to `model_browser.py` following the existing Pipes/Sprinklers pattern, plus fitting hide/show support in `model_space.py`.

**Constraints:**
- All geometry in millimeters.
- Z_OVERLAY = 200 for overlay items (labels, badges, riser symbols).
- `_display_overrides["visible"]` is the canonical "user hidden" flag.
- Fitting is not a QGraphicsItem — it wraps a `_TintedSvg` symbol parented to the Node.

---

## 4. Design

### 4.1 Hidden Items Respect Display Overrides

**File:** `firepro3d/level_manager.py`

In `_set_level_vis()`, add an early return at the top (after the deleted-C++ guard):

```python
if getattr(item, "_display_overrides", {}).get("visible") is False:
    item.setVisible(False)
    return
```

This skips Z-ordering, opacity, and selectability entirely. The item is "dead" until un-hidden.

**Scope:** Universal — applies to all entity types processed by `_set_level_vis` (pipes, nodes, walls, rooms, floors, roofs, construction geometry).

**Interactions:**
- `_show_all_hidden()` clears the override then calls `apply_to_scene()` — works correctly.
- `_show_items()` clears the override and calls `setVisible(True)` — next `apply_to_scene()` re-evaluates normally.
- Display manager runs after level_manager — no conflict.

### 4.2 Riser Pass-Through Indicator

**Files:** `firepro3d/pipe.py`, new SVG `firepro3d/graphics/fitting_symbols/riser_passthrough.svg`

**Symbol:** Circle divided by an S-curve (yin-yang / broken-pipe). Fixed size: 300mm scene units (matches branch fitting size of 75mm × 4). SVG asset loaded via the same `_TintedSvg` / `QGraphicsSvgItem` pattern used by fittings.

**Lifecycle on Pipe:**

- New attribute: `self._riser_symbol: QGraphicsSvgItem | None = None`
- New method `_update_riser_symbol()` called from `update_label()` and `setVisible()`:
  - If `_is_vertical()` is True:
    - Create symbol if needed, add to scene as top-level item at `Z_OVERLAY`
    - Position at the pipe's XY (both endpoints share the same XY for vertical pipes)
    - Non-interactive: `setAcceptedMouseButtons(NoButton)`, `setAcceptHoverEvents(False)`
    - **Visibility rule:** Show only when NEITHER `self.node1.isVisible()` NOR `self.node2.isVisible()`. If either node is visible, the node's fitting symbol already indicates the riser.
  - If not vertical: hide/remove the symbol.
- `Pipe.setVisible()` cascades to `_riser_symbol` (same as label cascade).
- `delete_pipe()` and other pipe removal sites clean up `_riser_symbol` (same pattern as label cleanup).

**Edge cases:**
- Horizontal pipe: `_is_vertical()` False, no symbol created.
- Riser with one node on active level: that node's fitting (elbow_up/tee_up) shows, riser symbol hidden.
- Riser with both nodes outside view range but pipe passes through: pipe's `z_range_mm()` spans both levels, level_manager shows the pipe, riser symbol appears.
- User hides pipe via display overrides: `setVisible(False)` cascades to riser symbol.

### 4.3 Fittings Group in Model Browser

**Files:** `firepro3d/model_browser.py`, `firepro3d/model_space.py`

**Browser group structure:**

```
Fittings (12)
  +-- Tee @ Pipe 3, Pipe 5, Pipe 7
  +-- 90 Elbow @ Pipe 1, Pipe 2
  +-- Cap @ Pipe 4
  +-- Tee Up @ Pipe 6, Pipe 8, Pipe 9
  ...
```

**Implementation — model_browser.py:**

- Add a "Fittings (N)" group after existing Sprinklers group.
- Iterate `sprinkler_system.nodes`, filter to nodes where `fitting.type != "no fitting"`.
- Each fitting item:
  - Label: `"{type} @ {pipe list}"` using pipe indices from the Pipes group.
  - `setData(0, _ROLE_ENTITY, id(node))` — stores parent node id.
  - Tooltip: `"Level: {node.level}  Type: {fitting.type}"`
  - `_style_hidden()` greys out if `fitting._display_overrides.get("visible") is False`.
- Selecting a fitting in the browser selects the parent node in the scene.
- Right-click context menu: Hide / Show (same pattern as pipes).

**Hide/show mechanics — model_space.py:**

- `_hide_items()` / `_show_items()` currently operate on QGraphicsItems. Add a branch for Fitting objects:
  - Hide: `fitting._display_overrides["visible"] = False`; `fitting.symbol.setVisible(False)`
  - Show: `fitting._display_overrides.pop("visible", None)`; `fitting.update()` to re-evaluate visibility (respects sprinkler/stacking rules).
- `fitting.update()` must check `_display_overrides["visible"]` before setting `symbol.setVisible(visibility)`:
  - If `_display_overrides.get("visible") is False`, force `visibility = False`.

**Filtering:**
- Nodes with `fitting.type == "no fitting"` (collinear mid-run joints) are excluded from the browser list.

---

## 5. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Override scope | All entity types | `_set_level_vis` is generic; restricting to pipes/nodes would be inconsistent |
| Override behavior | Early return, skip everything | Simplest and most predictable; hidden = fully inert |
| Riser symbol host | Pipe (not Node) | Both endpoint nodes may be outside view range; only the pipe spans the full riser height |
| Riser symbol visibility | Only when no endpoint node visible | Avoids doubling up with fitting symbols that already indicate risers |
| Riser symbol size | Fixed (not diameter-scaled) | User preference; simpler |
| Riser render method | SVG asset | Consistent with fitting symbol system |
| Fitting browser item entity | Parent node id | Fitting is not a QGraphicsItem; node is the selectable scene entity |
| Fitting hide mechanics | `_display_overrides` + `fitting.update()` check | Follows existing pattern; `update()` already controls symbol visibility |

---

## 6. Acceptance Criteria

### Task 1 — Hidden items stay hidden
- [ ] User-hidden items remain hidden after level switch
- [ ] User-hidden items remain hidden after view range change
- [ ] `_show_all_hidden()` correctly un-hides and re-applies level filtering
- [ ] Hidden items are not selectable, do not participate in Z-ordering

### Task 2 — Riser pass-through indicator
- [ ] Vertical pipes show yin-yang SVG symbol at XY location in plan view
- [ ] Symbol hidden when either endpoint node is visible
- [ ] Symbol shown when neither endpoint node is visible (riser passes through level)
- [ ] Symbol hidden when pipe is hidden via display overrides
- [ ] Symbol cleaned up on pipe deletion and undo/redo
- [ ] Symbol is non-interactive (no click/hover)

### Task 3 — Fittings in model browser
- [ ] Fittings group appears in model browser with correct count
- [ ] "no fitting" type nodes excluded from list
- [ ] Individual fittings can be hidden/shown via context menu
- [ ] Hidden fittings stay hidden across level switches (Task 1 interaction)
- [ ] Selecting a fitting selects the parent node in the scene
- [ ] Hidden fittings are greyed out in the browser tree

---

## 7. Verification Checklist

- [ ] `python -m pytest tests/` — all existing tests pass, no regressions
- [ ] New unit tests: ~10-15 covering visibility override, riser symbol logic, browser group
- [ ] Smoke test: hide pipe, switch levels, verify stays hidden
- [ ] Smoke test: draw riser between levels, verify symbol appears on intermediate level
- [ ] Smoke test: hide fitting from browser, verify symbol disappears, persists across level switch
