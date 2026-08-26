# Selection Mode — Specification

> **Status:** Approved (spec-only — no code changes delivered by this document)
> **Source files:** `firepro3d/model_space.py`, `firepro3d/model_view.py`, `firepro3d/scene_tools.py`
> **Date:** 2026-05-02
> **Revision:** 1 (post grill + brainstorm session)
> **Absorbs:** TODO "Restore label-only click-selection for rooms"

---

## 1. Goal & Motivation

### 1.1 Goal

Define the authoritative selection/interaction model for plan view (Model_Space) when no drawing tool is active. This spec is the single source of truth for all selection behavior — other entity specs defer here for selection rules and define only their own grip catalogs and context menu contents.

### 1.2 Motivation

Selection behavior has grown organically across multiple modules and specs. Z-order drives implicit priority with no formal contract. Tab does post-click same-type cycling rather than pre-click disambiguation. No hover feedback exists — users click blind. Rubber-band is window-only. Room selection is broken after the `shape()` fix (clicking anywhere inside the polygon selects the room). This spec fills those gaps and establishes the interaction contract.

### 1.3 Why now

Several planned features (inferred placement, section views, OSNAP toolbar) depend on a stable, documented selection model. The room click-selection bug needs a principled fix, not a patch. Hover pre-highlight is the highest-impact UX gap in the current drafting experience.

---

## 2. Scope

### 2.1 In scope

- All mouse/keyboard interaction in select mode (plan view): hover, click, Ctrl+click, right-click, double-click, rubber-band, Tab, Escape, grip activation protocol.
- Formalized selection priority table.
- Hover pre-highlight visual treatment.
- Direction-dependent rubber-band (window vs crossing).
- Tab-cycle disambiguation (replaces current same-type cycling).
- Room label-only click restriction.
- Underlay Tab-reachability.

### 2.2 Out of scope (named, not specced)

- **Elevation scene selection** — separate spec. See TODO.
- **3D view selection** — separate spec. See TODO.
- **Per-entity grip catalogs** — owned by each entity's spec.
- **Context menu contents** — owned by each entity's spec.
- **Tool-mode interactions** — pipe placement, wall drawing, floor polygon, stretch mode, etc.
- **Snap engine** — snapping is independent of selection; operates in parallel.

### 2.3 Cross-references

| Spec | Relationship |
|------|-------------|
| `snapping-engine.md` | Snap is independent of selection. Snap engine remains active during grip drag. No overlap. |
| `grid-system.md` | Gridline click/selection behavior defers to this spec. Grid spec owns grip catalog (pull-tab, reposition) and spacing dimensions. |
| `underlay-workflow.md` | Underlay selectability rules defined here. Underlay spec owns browser tree management, layer visibility, context menu contents. |
| `wall-room-floor-system.md` | Wall/room/floor selection highlight and grip behavior defers to this spec for protocol. Entity spec owns grip catalog and visual treatment. |
| `align-placement.md` | Selection dimensions (post-placement spacing edit) triggered by selection state defined here. Inferred spec owns the dimension behavior itself. |

### 2.4 Absorbs

- TODO item: "Restore label-only click-selection for rooms" — resolved by §5.4 (Room click restriction).

---

## 3. Selection Priority

Selection priority follows runtime Z-order. When multiple selectable items overlap under the cursor, the highest-Z item wins. The hover pre-highlight (§4) and Tab-cycle (§5.1) both use this ordering.

### 3.1 Priority Table

| Priority | Entity | Runtime Z | Notes |
|----------|--------|-----------|-------|
| 1 (highest) | Node (+ Sprinkler child) | 0.5 | Sprinkler click resolves to parent Node |
| 2 | Pipe | 0.4 | |
| 3 | WallSegment | 0.3 | |
| 4 | Room | 0.2 | Label-bg rect only (§5.4) |
| 5 | RoofItem | 0.1 | |
| 6 | FloorSlab | 0.0 | |
| Special | GridlineItem | own Z | Selectable; bubble click resolves to parent |
| Special | DetailMarker | own Z | Selectable; excluded from rubber-band |
| Special | DesignArea | own Z | Selectable |
| Special | Construction geometry | own Z | Selectable |
| Lowest | Underlay | below geometry | Tab-only (§5.5); no direct click |
| Never | Annotations, snap markers, preview items | — | `ItemIsSelectable` flag not set |

### 3.2 Resolution rules

- Only items with the `ItemIsSelectable` flag participate in selection.
- Child items (sprinkler SVG, gridline bubble) resolve to their parent entity.
- "Special" items with their own Z-values participate in the normal Z-sort alongside core entities — their actual Z determines where they fall.

---

## 4. Hover Pre-highlight

When the cursor moves in select mode, the top-priority selectable item under the cursor receives a transient **outline glow**.

### 4.1 Visual treatment

- **Color:** Cyan (`#00BFFF`)
- **Pen:** Cosmetic 2px, drawn around the item's shape path or bounding rect
- **Distinct from:** Selection highlight (item color `lighter(150)`), snap markers (green/yellow), wall selection (red outline)

### 4.2 Rules

- Fires on `mouseMoveEvent` when no tool is active and no grip drag or rubber-band drag is in progress.
- Uses `scene.items(cursor_pos)` filtered by `ItemIsSelectable`, sorted by Z-order descending.
- Only one item highlighted at a time — the top-priority candidate (or Tab-cycled candidate per §5.1).
- When cursor moves off all selectable items, highlight clears.
- Room: only highlights when cursor is over the label-bg rect, not the polygon interior.
- Underlay: no hover highlight (pass-through to items behind).

### 4.3 Suppression

Hover pre-highlight is suppressed during:
- Rubber-band drag
- Grip drag
- Any active drawing tool (mode != select)

### 4.4 Performance

- Use `scene.items(pos, ...)` spatial index — not full scene iteration.
- The hit-test runs on every mouse move and must remain cheap.
- Consider early-out if the top-Z item at the position hasn't changed since last move event.

---

## 5. Click Selection

### 5.1 Tab-Cycle Disambiguation

When multiple selectable items overlap under the cursor, Tab cycles the hover pre-highlight through candidates before the user clicks.

**Behavior:**
1. First Tab press: highlight advances from top-priority to second-priority item.
2. Subsequent presses: cycle through all candidates, wrapping to top.
3. Click commits the currently highlighted candidate as the selection.
4. Moving the cursor resets the Tab cycle (re-evaluates candidates at new position).

**Candidate list:** All selectable items at cursor position sorted by Z-order descending, with the underlay group (if any) appended at the end as the last candidate.

**State:** `_tab_candidates: list[QGraphicsItem]` and `_tab_index: int` on Model_Space, cleared on cursor move or mode change.

**Replaces:** Current post-click same-type Tab cycling (`model_space.py:3374`). That behavior is removed from select mode. Wall alignment cycling (Tab in wall mode) is unaffected — it's a tool-mode behavior.

### 5.2 Left-Click (no modifier)

1. If a grip handle is within tolerance (12px viewport distance) on a selected item: begin grip drag. Click is consumed — no selection change.
2. Otherwise, clear entire current selection.
3. Select the currently hover-highlighted item (top-priority or Tab-cycled candidate).
4. If no item is highlighted (cursor on empty space): deselect all.

### 5.3 Ctrl+Click

- Toggle the hover-highlighted item in/out of the current selection set.
- Unselected item: add to selection.
- Already selected item: remove from selection.
- No other items affected.
- Universal across all selectable entity types — no type-specific special cases.
- Ctrl+click on empty space: no effect (preserves current selection).

### 5.4 Room Click Restriction

Room is only selectable by clicking on its **label background rect**, not anywhere inside the room polygon. Clicks inside the polygon but outside the label pass through to the next-priority candidate or to empty space.

This applies to:
- Direct click selection
- Hover pre-highlight detection
- Tab-cycle candidate evaluation

Room rubber-band selection uses the label-bg rect for containment/intersection testing (§6).

### 5.5 Underlay Tab-Reachability

Underlays are not directly clickable for selection — clicks pass through to items behind or to empty space. However, underlays are reachable via Tab-cycle as the lowest-priority candidate.

When a Tab-cycled underlay is highlighted and clicked:
- The underlay is selected (highlight shown on boundary).
- Property panel shows read-only underlay properties (file path, scale, level, layers).
- Right-click shows the underlay context menu (same as browser tree right-click).
- No grips appear. No drag/transform is possible.

### 5.6 Right-Click

- Never changes selection state.
- If an item is under cursor: show that item's context menu.
- If on empty space: show scene-level context menu.
- Menu contents are per-entity, out of scope.

### 5.7 Double-Click

In select mode, double-click behaves as a regular click (selects item). No special action.

Double-click behaviors in tool modes (finish polyline, close polygon, activate view marker) are unaffected.

### 5.8 Sprinkler Resolution

Clicking a sprinkler SVG child resolves to the parent Node. The Node is selected, properties shown, and grips activated — not the sprinkler.

---

## 6. Rubber-Band Selection

Direction of drag determines selection mode, matching AutoCAD/Revit convention.

### 6.1 Window Selection (left-to-right)

- **Visual:** Solid blue outline, light blue semi-transparent fill.
- **Mode:** `Qt.ContainsItemShape` — selects items **fully contained** within the rectangle.

### 6.2 Crossing Selection (right-to-left)

- **Visual:** Dashed green outline, light green semi-transparent fill.
- **Mode:** `Qt.IntersectsItemShape` — selects items that **intersect** the rectangle (partial overlap counts).

### 6.3 Shared Rules

- Drag < 5px Manhattan distance: treated as click, no rubber-band (current behavior).
- **Plain drag:** Clears current selection before applying rubber-band results.
- **Ctrl+drag:** Additive — rubber-band results are added to existing selection.
- Items with `_exclude_from_bulk_select` flag (DetailMarker, ViewMarkerArrow) are excluded from both modes.
- Underlays excluded from both modes.
- Room: rubber-band tests against the label-bg rect, not the polygon.
- Hover pre-highlight suppressed during drag.
- Direction detection: compare start X to end X on mouse release. `end.x() < start.x() - 5` = crossing; otherwise = window.

---

## 7. Escape & Deselection

### 7.1 Escape Key

In select mode:
- Clears entire selection (all items deselected).
- If a grip drag is in progress: cancels the drag, restores item to pre-drag position, then clears selection.
- If Tab-cycle is active: resets Tab cycle and clears hover highlight.
- No effect if nothing is selected and no interaction is active.

### 7.2 Click-on-Empty

- Plain left-click on empty canvas: clears entire selection.
- Ctrl+click on empty: no effect (preserves current selection).

### 7.3 Deselection During Rubber-Band

- Plain rubber-band drag: clears current selection before applying results.
- Ctrl+rubber-band drag: preserves current selection, adds results.

---

## 8. Grip Activation Protocol

This section defines the grip interaction protocol. Per-entity grip catalogs (which points, what constraints, visual style) are owned by each entity's spec.

### 8.1 Activation

- Grips become visible immediately when an item is selected.
- Multi-selection: all selected items show their grips simultaneously.

### 8.2 Interaction Priority

- Grip click takes **absolute priority** over all other mouse interactions in select mode.
- Detection tolerance: 12px viewport distance (current `_find_grip_hit` behavior).
- When grip and selectable item overlap at cursor position: grip wins.

### 8.3 Drag Mechanics

1. Mouse down within grip tolerance: grip drag begins.
2. Mouse move: item updates geometry in real-time following the grip's constraint.
3. Mouse up: commit new geometry, push undo state.
4. Escape during drag: cancel, restore pre-drag geometry.

### 8.4 Multi-Item Grip Drag

- **Gridlines:** Dragging one selected gridline's grip applies the same delta to all selected gridlines in parallel (current behavior).
- **Other entities:** Grip drag applies to the single item whose grip was grabbed.

### 8.5 Snap During Grip Drag

Snap engine remains active during grip drag — the grip position snaps to OSNAP candidates. This is existing behavior and is preserved.

---

## 9. Keyboard Summary

| Key | Select Mode Behavior |
|-----|---------------------|
| Tab | Cycle hover pre-highlight through overlapping candidates (§5.1) |
| Escape | Deselect all / cancel grip drag / reset Tab cycle (§7.1) |
| Delete | Delete selected items (existing behavior, not changed by this spec) |
| F3 | Toggle OSNAP (snap engine, independent of selection) |

---

## 10. Divergences from Current Implementation

| Behavior | Current | Target | Change |
|----------|---------|--------|--------|
| Hover pre-highlight | None | Cyan outline glow on top-priority item | **NEW** |
| Tab (select mode) | Post-click: cycles same-type items | Pre-click: cycles overlapping candidates | **CHANGED** |
| Tab (wall mode) | Cycles alignment (Center/Left/Right) | Unchanged | None |
| Rubber-band (select) | Window only (L->R containment) | Direction-dependent: L->R window, R->L crossing | **CHANGED** |
| Rubber-band visual | Default Qt style | Blue/solid (window) vs green/dashed (crossing) | **NEW** |
| Ctrl+rubber-band | Replaces selection | Additive (adds to existing) | **CHANGED** |
| Room click target | Anywhere inside polygon | Label-bg rect only | **CHANGED** |
| Underlay selectability | Never, no Tab access | Tab-reachable last; property view + context menu | **CHANGED** |
| Click-on-empty | Deselects all | Deselects all | None |
| Ctrl+click | Toggle (gridlines only) | Universal toggle (all types) | **CHANGED** |
| Right-click | Blocked from deselecting | Blocked, shows context menu | None |
| Escape | Mode-dependent | Deselects all, cancels grip drag | **CLARIFIED** |
| Double-click (select) | Falls through to Qt | Regular click, no special action | **CLARIFIED** |
| Grip activation | On selection | On selection | None |
| Grip priority | Over mode handlers | Over all select-mode interactions | **CLARIFIED** |
| Selection priority | Implicit Z-order | Formalized Z-order table | **FORMALIZED** |

---

## 11. Acceptance Criteria

- [ ] Hover pre-highlight: cyan outline glow on top-priority selectable item under cursor; clears when cursor leaves all items
- [ ] Tab-cycle: pre-click disambiguation through overlapping candidates sorted by Z-order; underlay reachable as last candidate; resets on cursor move
- [ ] Current post-click same-type Tab cycling removed from select mode
- [ ] Selection priority follows formalized Z-order table (§3)
- [ ] Room click-selection restricted to label-bg rect only
- [ ] Direction-dependent rubber-band: L->R window (blue/solid), R->L crossing (green/dashed)
- [ ] Ctrl+drag adds rubber-band results to existing selection
- [ ] Ctrl+Click universal toggle for all selectable entity types
- [ ] Click-on-empty deselects all; Ctrl+click-on-empty preserves selection
- [ ] Escape deselects all and cancels in-progress grip drag
- [ ] Underlay Tab-selectable for property view and right-click context menu; no grips, no transforms, no direct click selection
- [ ] Grip click takes priority over all other select-mode interactions
- [ ] Right-click never changes selection; shows context menu
- [ ] Double-click in select mode behaves as regular click
- [ ] Hover highlight suppressed during rubber-band drag and grip drag
- [ ] Performance: hover hit-test uses spatial index, not full scene iteration

## 12. Verification Checklist

- [ ] All acceptance criteria met
- [ ] No regressions in existing selection behavior (gridline, wall, pipe, node click-selection)
- [ ] Tool-mode behaviors unaffected (pipe placement, wall drawing, floor polygon, stretch mode)
- [ ] Snap engine unaffected during grip drag and general select mode
- [ ] Undo/redo unaffected by selection changes
- [ ] Cross-reference notes added to dependent specs (§2.3)

## 13. Future Work (out of scope)

- Elevation view selection mode — separate spec (TODO added)
- 3D view selection mode — separate spec (TODO added)
- Per-entity context menu definitions
- Selection filter toolbar (select only pipes, only walls, etc.)
- Lasso selection (freeform rubber-band)
