# Selection Mode — Specification

> **Status:** **Partial — Leg A (PLAN scene, 2026-09-13) + Leg B (ELEVATION scene, 2026-09-14) implemented.** The selection-mode contract + the **HALO** (Highlight-Activated Lock-On) preselection engine are built against the unified `SelectionManipulator` (the sole grip owner since U4 — see `selection-manipulator.md`). Leg B folds HALO + the manipulator + the scene-drawn rubber-band onto the elevation scene via the extracted scene-agnostic `HaloSelectionMixin` (`halo_selection.py`) — see §14. 3D-scene selection (Leg C) remains future work — see §13. DoRs: `docs/superpowers/specs/2026-09-13-halo-selection-mode-leg-a-design.md`, `docs/superpowers/specs/2026-09-14-u5-leg-b-elevation-selection-design.md`.
> **Source files:** `firepro3d/model_space.py`, `firepro3d/model_view.py`, `firepro3d/halo.py`, `firepro3d/halo_selection.py` (ranking + band + app-wide HALO tunables), `firepro3d/view_scale.py` (visible-view hit width), `firepro3d/theme.py` (`accent` token), `firepro3d/constants.py` (`HALO_TRACE_*`)
> **Date:** 2026-05-02 (spec); 2026-09-13 (Leg A as-built); 2026-09-21 (§4.2 trace-render polish); 2026-09-23 (§4.3 undo/redo candidate invalidation, verified `b05244d`); 2026-09-23 (§4.3 removal pruning + §5.9 batch selection, block polish, verified `434066c`); 2026-09-24 (Rev 4: HALO pixel ranking, app-wide aperture/band, no band preview, batched band commit, verified `f2b1d99`)
> **Revision:** 4 (Rev 4: HALO ranks SNAP-style — px distance to the drawn trace, Z only inside a px priority band; aperture/band app-wide + tunable; live band preview removed. Rev 2: Leg A reconciliation — HALO engine, Spacebar disambiguation, manipulator owns grips. Rev 3: §4.2 HALO render reworked — traces the *drawn* primitive geometry in the `accent` token, semi-transparent + soft glow, composite `halo_trace_path` hook.)
> **Absorbs:** TODO "Restore label-only click-selection for rooms"
>
> **Ownership boundary:** this spec owns **what gets selected** (HALO preselection, disambiguation, click/rubber-band picking, priority). `selection-manipulator.md` owns **what happens to the selection** (frame, handles, rigid transforms, grip editing). Grip activation is delegated there (§8).

---

## 1. Goal & Motivation

### 1.1 Goal

Define the authoritative selection/interaction model for plan view (Model_Space) when no drawing tool is active. This spec is the single source of truth for all selection behavior — other entity specs defer here for selection rules and define only their own grip catalogs and context menu contents.

### 1.2 Motivation

Selection behavior had grown organically across multiple modules and specs: implicit Z-order priority with no formal contract; Tab doing post-click same-type cycling rather than pre-click disambiguation; no hover feedback (users clicked blind); window-only rubber-band; and broken room selection after the `shape()` fix (clicking anywhere inside the polygon selected the room). Leg A fills those gaps in the plan scene with the HALO engine and this interaction contract.

### 1.3 Why now

Several planned features (inferred placement, section views, OSNAP toolbar) depended on a stable, documented selection model, and the room click-selection bug needed a principled fix, not a patch. Preselection feedback was the highest-impact UX gap — Leg A closes it with the HALO engine (§4).

---

## 2. Scope

### 2.1 In scope

- All mouse/keyboard interaction in select mode (plan view): HALO hover, click, Ctrl+click, right-click, double-click, rubber-band, Spacebar (disambiguation), Escape, grip activation delegation.
- Formalized selection priority table.
- HALO preselection-highlight engine (aperture pick + shared ranking + hover outline).
- Direction-dependent rubber-band (window vs crossing).
- Spacebar-cycle disambiguation (replaces the retired post-click same-type cycling; Tab is freed for the dynamic-input HUD).
- Room label-only click restriction (with polygon fallback).
- Underlay Spacebar-reachability.

### 2.2 Out of scope (named, not specced)

- **Elevation scene selection** — **Leg B**, built 2026-09-14. Specced in §14 (elevation is a distinct scene with a read-only-geometry contract, so it gets its own section, not a rule change to §1–§12). See `selection-manipulator.md` U5 roadmap.
- **3D view selection** — **Leg C** (3D-scene handle providers; orphan), still pending. See §13.
- **Per-entity grip catalogs** — owned by each entity's spec.
- **Context menu contents** — owned by each entity's spec.
- **Tool-mode interactions** — pipe placement, wall drawing, floor polygon, stretch mode, etc.
- **Snap engine** — snapping is independent of selection; operates in parallel.

### 2.3 Cross-references

| Spec | Relationship |
|------|-------------|
| `selection-manipulator.md` | **Owns what happens to the selection** (frame, handles, rigid transforms, grip editing, undo). This spec owns **what gets selected** (HALO preselection lives here). §8 delegates all grip/handle interaction there. |
| `snapping-engine.md` | Snap is independent of selection. Snap engine remains active during grip/handle drag. No overlap. |
| `grid-system.md` | Gridline click/selection behavior defers to this spec. Grid spec owns grip catalog (pull-tab, reposition) and spacing dimensions. |
| `underlay-workflow.md` | Underlay selectability rules defined here. Underlay spec owns browser tree management, layer visibility, context menu contents. |
| `wall-room-floor-system.md` | Wall/room/floor selection highlight and grip behavior defers to this spec for protocol. Entity spec owns grip catalog and visual treatment. |
| `align-placement.md` | Selection dimensions (post-placement spacing edit) triggered by selection state defined here. Inferred spec owns the dimension behavior itself. |

### 2.4 Absorbs

- TODO item: "Restore label-only click-selection for rooms" — resolved by §5.4 (Room click restriction).

---

## 3. Selection Priority

Selection priority is **closest-first, Z within a band** (Rev 4, 2026-09-24 — replaces pure Z-first, under which a tiny item near the cursor beat a long item the cursor was actually on). HALO preselection (§4) and Spacebar-cycle (§5.1) both consume the shared `halo_rank` ordering, judged in **screen pixels** against each candidate's *drawn trace* (SNAP picker model, `snapping-engine.md §6.1`): candidates within `HALO_PRIORITY_BAND_PX` of the closest rank by **runtime-Z descending**, then distance; the rest rank by distance; stable id last. Runtime Z (and so the §3.1 table) decides only between candidates inside the band.

Runtime Z values are owned by `view-relationships.md §7.3` + `constants.py` — the §3.1 table below is a *priority tie-break reference*, not the authoritative Z source; do not treat its numbers as canonical.

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
| Lowest | Underlay | below geometry | Spacebar-only (§5.5); appended LAST in the HALO candidate list; no direct click |
| Never | Annotations, snap markers, preview items | — | `ItemIsSelectable` flag not set |

### 3.2 Resolution rules

- Only items with the `ItemIsSelectable` flag participate in selection.
- Child items (sprinkler SVG, gridline bubble) resolve to their parent entity.
- "Special" items with their own Z-values participate in the normal Z-sort alongside core entities — their actual Z determines where they fall.

---

## 4. HALO — Preselection Highlight Engine

**HALO** (Highlight-Activated Lock-On) is the preselection engine: as the cursor moves in select mode, the top-ranked selectable item within an **aperture** around the cursor receives a transient hover outline. HALO is the single source of the preselection that hover, Spacebar-cycle (§5.1), and click-commit (§5.2) all consume — click commits *what HALO shows*, not a fresh hit-test.

### 4.1 Aperture pick & shared ranking

- Per move, `Model_View.mouseMoveEvent` calls `Model_Space.halo_update(scene_pos, aperture, dt)`. The aperture is a screen-pixel radius read live from the app-wide module global `halo_selection.HALO_APERTURE_PX` (default `constants.HALO_APERTURE_PX`, user-tunable — §4.5); the view converts it to a scene-unit search box for the `scene.items()` pre-filter.
- `halo_candidates_at` gathers candidates within the aperture, filtered by: `isVisible()` (which already reflects the `LevelManager` z-slab sweep — do not re-filter by level here), the `_halo_is_underlay` parent-walk (an underlay group is appended **LAST**, never interleaved), and `ItemIsSelectable`.
- **Distance** is `halo.halo_pick_distance_px`: the cursor's px distance to the item's drawn trace (the same geometry §4.2 outlines), mapped through `item.deviceTransform(dt)` so it is zoom-invariant and correct for `ItemIgnoresTransformations` markers. Inside an **area** item it is 0 — filled 2D geometry (`fill_type`), classes flagged `HALO_AREA` (walls, slabs, roofs, openings, rooms, nodes, design areas, view arrows, gridline/elevation bubbles, solid elevation proxies) and shape-fallback items (text, SVG, blocks). Open geometry is measured to its stroke (never `QPainterPath.contains`, which implicitly closes open paths). A resolved parent takes the **minimum** over its raw child hits (a bubble/label counts for its gridline). Candidates farther than the aperture are dropped.
- A **pure, shared** `halo_rank` orders candidates: judged in **screen pixels** against each candidate's *drawn trace* (SNAP picker model, `snapping-engine.md §6.1`): candidates within `HALO_PRIORITY_BAND_PX` of the closest rank by **runtime-Z descending**, then distance; the rest rank by distance; stable id last (band = `halo_selection.HALO_PRIORITY_BAND_PX`, default `constants.HALO_PRIORITY_BAND_PX`). `halo_rank` is deterministic and consumed identically by hover, cycle, and click — there is no separate per-consumer ordering.
- `halo_item()` returns the current top-ranked (or cycled — §5.1) candidate; `None` when the aperture is empty.

### 4.2 Hover outline

- Drawn in `Model_View.drawForeground` via `firepro3d/halo.py:paint_halo_highlight`.
- **Traces the drawn primitive geometry, not the hit-shape.** The outline follows the item's *actual* drawn geometry (its `path()`/`line()`/`rect()`/`polygon()`), **not** the fattened `shape()` hit-region — so thin/open geometry (lines, arcs, pipes) gets a single clean line instead of a capsule outline. `halo.py:_halo_trace_path_local` dispatches by Qt base type; baked rotation already lives in the local trace, so the scene mapping stays `sceneTransform().map(...)` (never the items' overridden `mapToScene`, which would double-apply rotation).
- **Composite items** (gridlines, and future dimensions/markers) expose a `halo_trace_path(scene_scale)` hook returning a QPainterPath that unions all their constituent primitives — the same way a `BlockInstance.shape()` is the union of its render-op paths. `halo_scene_path` honors the hook and falls back to the type dispatch. `scene_scale` (view scene→device) is threaded through for screen-fixed sub-parts (e.g. a gridline's `ItemIgnoresTransformations` bubbles); the gridline trace = drawn line + extension (trimmed at each visible bubble's edge) + bubble circles, mirroring its `paint()`.
- **Color token:** `theme.py` `accent` (dark `#63BE8B` / light `#2f9e63`) — do not hard-code the hex. Rendered **semi-transparent** with a **soft outer glow** (a QPainter multi-pass approximation — `drawForeground` has no filter pipeline). Tuning lives in `constants.py`: `HALO_TRACE_COLOR` / `HALO_TRACE_ALPHA` / `HALO_TRACE_WIDTH_PX` / `HALO_GLOW_PX`.
- Distinct-by-treatment from the selection highlight (in the dark theme `accent` shares the `selection` hue; the HALO reads apart via its alpha + glow + trace, not hue), snap markers, and the manipulator frame/handles (`selection-manipulator.md`).
- One item outlined at a time (the HALO item). Clears when the aperture is empty.
- Room: outlines the label rect when a label is visible, else the polygon (§5.4). Underlay: no hover outline (reachable only as the terminal Spacebar candidate — §5.5).

### 4.3 Suppression

The hover outline is gated on `not scene._halo_suppressed()`. HALO is suppressed during:
- An active manipulator drag (handle/grip/interior-move) or rubber-band drag.
- **Any active placement/drawing tool** (mode != select) — HALO is a select-mode-only affordance.
- HALO disabled via the status-bar pill / Preferences (§4.5).

**Candidate invalidation on undo/redo (2026-09-23).** `_restore_network` (the single restore path for undo AND redo) rebuilds every item from the snapshot, so any held HALO candidate is a detached object at its pre-restore geometry. It calls `halo_clear()` (+ repaint) before rebuilding, so no ghost outline is painted at the old position; the next mouse move re-acquires the hover. Guard: `tests/test_halo_stale_highlight.py`.

**Candidate pruning on removal (2026-09-23, block polish).** `halo_item()` (`HaloSelectionMixin`) first drops candidates no longer in the scene (delete / cut / restore) and resets the cycle index, so a stale outline is never painted over a vanished item while the cursor sits still. Guard: `tests/test_block_polish_bugs.py::test_halo_highlight_drops_deleted_item`.

### 4.4 Status readout

When the HALO item resolves to one of several overlapping candidates, the scene emits a `"<Type> — i of N"` readout via its `instructionChanged` signal (status bar), so the user knows a Spacebar cycle (§5.1) is available and where in the ring they are.

### 4.5 Enable / disable (pill + Preferences)

- A **HALO** on/off pill sits beside the SNAP/ALIGN pills (`main.py`); its state persists under QSettings `halo/enabled`. See `snap-toolbar.md` for the pill's UI contract.
- The Preferences **HALO** tab exposes Enable + **Aperture** (px) + **Priority band** (px). Aperture/band are **app-wide** module globals (`halo_selection.HALO_APERTURE_PX` / `HALO_PRIORITY_BAND_PX`, the `SNAP_TOLERANCE_PX` pattern) honored by every scene (plan, Block Editor, elevation), persisted under `halo/pick_aperture_px` / `halo/priority_band_px` and restored by `main.py`. The retired key `halo/aperture_px` is **deliberately ignored**: nearly every install persisted the old 6 px there, which would put the aperture inside the band (making Z decide everything again).

### 4.6 Performance

- Use the `scene.items(...)` spatial index over the aperture — never full-scene iteration (thin cosmetic items need the spatial index; see the sceneBoundingRect/cosmetic caveat).
- The pick runs on every mouse move and must stay cheap; `dt` is threaded through for throttle/early-out.
- Item `shape()` hit widths are N screen px at the **visible** view's zoom via `view_scale.scene_hit_width` (no mm floor) — never `views()[0]` (`snapping-engine.md §14.4`); otherwise the aperture pre-filter catches items far from the cursor when zoomed in.
- Known cost (2026-09-24 bench, 20k-primitive PDF import): the `scene.items()` box query is ~50 ms/move because the model scene is `NoIndex`; the px ranking adds ~3–7 ms. Filed follow-up (spatial index).

---

## 5. Click Selection

### 5.1 Spacebar-Cycle Disambiguation

When multiple selectable items fall within the HALO aperture, **Spacebar** cycles the HALO preselection through the ranked candidates before the user clicks. (**Tab is deliberately NOT used** — it is freed for the dynamic-input HUD.)

**Behavior:**
1. First Spacebar press (`_halo_cycle`): the HALO item advances from the top-ranked to the next candidate in `halo_rank` order (§4.1).
2. Subsequent presses: cycle through all candidates, wrapping to the top; the underlay (if present) is the terminal candidate.
3. Click commits the current HALO item (§5.2).
4. Moving the cursor re-runs `halo_update` and resets the cycle.
5. Escape resets the cycle (§7.1 precedence ladder).

**Candidate list & order:** the `halo_rank` ordering (§4.1) — px distance to the trace, runtime-Z inside the priority band, stable id — with the underlay group (if any) appended LAST.

**Status readout:** `"<Type> — i of N"` via `instructionChanged` (§4.4).

**Replaces:** the retired post-click same-type cycling (`_cycle_similar_selection`) — that behavior is **removed** from select mode. Wall alignment cycling (Tab in *wall* mode) is a separate tool-mode behavior and is unaffected.

### 5.2 Left-Click (no modifier)

1. Grip / manipulator-handle activation is owned by the `SelectionManipulator` (§8, `selection-manipulator.md`): a handle/grip press within the manipulator's own hit-test is consumed by it before selection picking — no selection change.
2. Otherwise the click commits the **HALO-highlighted candidate**: `_press_select_item` selects `target = self.halo_item() or item_under` (HALO preselection wins; the raw item under the cursor is only a fallback when HALO has no candidate).
3. Plain click clears the prior selection before committing the target.
4. If HALO has no candidate and nothing is under the cursor (empty canvas): deselect all.

### 5.3 Ctrl+Click

- Toggle the HALO-highlighted item in/out of the current selection set.
- Unselected item: add to selection.
- Already selected item: remove from selection.
- No other items affected.
- **Universal** across all selectable entity types — the former gridline-only special case in `mousePressEvent` was **removed**; gridlines now flow through the same HALO-driven `_press_select_item`.
- Ctrl+click on empty space: no effect (preserves current selection).
- **Known pre-existing gap:** Ctrl+click over the manipulator frame interior is swallowed by the manipulator's interior-press guard (§8 / `selection-manipulator.md`) — filed, not addressed by Leg A.

### 5.4 Room Click Restriction

Room selection is restricted to its **label rect** *when a label is visible* — clicks inside the polygon but outside the label pass through to the next candidate or to empty space. When **no** label is visible, selection **falls back to the full polygon**. The label rect is exposed via the new `Room.label_scene_rect()` accessor.

This applies to HALO preselection detection, Spacebar-cycle candidate evaluation, and click commit.

**`shape()` stays the full polygon** — it is *not* narrowed to the label rect. Narrowing `shape()` would cull the room off-screen when only its label is on-screen (Qt `shape()` affects paint culling); the label-rect restriction is enforced in the HALO/selection path, not via `shape()`.

Room rubber-band selection uses the label rect for containment/intersection testing (§6).

### 5.5 Underlay Spacebar-Reachability

Underlays are not directly clickable for selection — clicks pass through to items behind or to empty space. They are reachable ONLY as the **terminal Spacebar candidate** (appended LAST in the HALO candidate list — §4.1).

When a Spacebar-cycled underlay is highlighted and clicked:
- The underlay is selected.
- For a sole-selected underlay the scene emits `requestPropertyUpdate`, driving read-only underlay properties (file path, scale, level, layers).
- The existing canvas context menu applies (same as browser tree right-click).
- No grips appear; no drag/transform is possible.
- **Locked underlays** (`ItemIsSelectable` off) are excluded — not reachable via HALO/Spacebar.

### 5.6 Right-Click

- Never changes selection state.
- If an item is under cursor: show that item's context menu.
- If on empty space: show scene-level context menu.
- Menu contents are per-entity, out of scope.

### 5.7 Double-Click

In select mode, double-click behaves as a regular click (selects item). No special action.

Double-click behaviors in tool modes (finish polyline, close polygon, activate view marker) are unaffected.

### 5.8 Sprinkler Resolution

Clicking a sprinkler SVG child resolves to the parent Node. The Node is selected and its properties/manipulator handles are shown (§8) — not the sprinkler.

### 5.9 Programmatic batch selection & delete notification (2026-09-23, block polish)

- `Model_Space.select_items(items, *, clear=True)` selects a batch with **one** `selectionChanged` (signals blocked across the loop; items not in this scene or not selectable are skipped). Per-item `setSelected` rebaked the manipulator over the growing selection — O(n²). Routed through it: Block Editor import, select-all (`clear=False`), select-same-level, level copy (select + restore), and the single-placement end-switch.
- `delete_selected_items` re-emits `selectionChanged` once after its signal-blocked bulk delete, so the manipulator frame, property panel and browser drop the deleted items.

Guards: `tests/test_block_polish_bugs.py` (`test_select_items_emits_selection_changed_once`, `test_delete_notifies_selection_listeners`, `test_delete_hides_manipulator_frame`).

---

## 6. Rubber-Band Selection

Direction of drag determines selection mode, matching AutoCAD/Revit convention. **As-built:** the rubber-band is **scene-drawn** and replaces Qt-native `RubberBandDrag` in select mode (the view's drag mode is set to `NoDrag`). It starts only from an empty-canvas press.

### 6.1 Window Selection (left-to-right)

- **Visual:** Solid blue outline, light blue semi-transparent fill.
- **Mode:** `Qt.ContainsItemShape` — selects items **fully contained** within the rectangle.

### 6.2 Crossing Selection (right-to-left)

- **Visual:** Dashed green outline, light green semi-transparent fill.
- **Mode:** `Qt.IntersectsItemShape` — selects items that **intersect** the rectangle (partial overlap counts).

The blue/solid ↔ green/dashed flip is live during the drag as direction changes.

### 6.3 Shared Rules

- Starts on an **empty-canvas press only**.
- Drag < 5px: treated as click, no rubber-band.
- Commit is `commit_rubber_band(rect, crossing, additive, dt)`, which is passed the view `viewportTransform()` (needed to map the shape-based hit-test); it selects the `rubber_band_hits(rect, crossing, dt)` result through `select_items` — **one** `selectionChanged` for the whole batch (§5.9; per-item selection was O(n²): >10 min on an 85k-primitive import).
- **No live preview** (removed 2026-09-24, user decision): nothing is highlighted while dragging — the per-move query + per-item glow cost seconds per frame on large drawings. Colours: window = `band_window` token (blue, solid), crossing = `band_crossing` token (green, dashed) — `halo.paint_rubber_band`.
- **Plain drag:** clears current selection before applying rubber-band results.
- **Ctrl+drag:** additive — rubber-band results are added to the existing selection.
- Items with the `_exclude_from_bulk_select` flag (DetailMarker, ViewMarkerArrow) are excluded from both modes.
- Underlays excluded from both modes.
- Room: rubber-band tests against the label rect (`Room.label_scene_rect()`), not the polygon.
- HALO suppressed during drag (§4.3).

---

## 7. Escape & Deselection

### 7.1 Escape Key

In select mode, Escape follows a **precedence ladder** (first applicable rung fires; each rung is a separate press):
1. Cancel an in-progress manipulator drag (restore pre-drag state — owned by `selection-manipulator.md`).
2. Cancel an in-progress rubber-band.
3. Reset the HALO Spacebar cycle (§5.1) back to the top-ranked candidate.
4. Clear the entire selection.

No effect if nothing is selected and no interaction is active.

### 7.2 Click-on-Empty

- Plain left-click on empty canvas: clears entire selection.
- Ctrl+click on empty: no effect (preserves current selection).

### 7.3 Deselection During Rubber-Band

- Plain rubber-band drag: clears current selection before applying results.
- Ctrl+rubber-band drag: preserves current selection, adds results.
- HALO hover suppressed during the drag (§4.3).

---

## 8. Grip / Handle Activation (delegated)

Grip and handle interaction is **owned by the `SelectionManipulator`** — since U4 (2026-09-12) it is the sole model-scene grip renderer, hit-tester, and undo funnel. The legacy `scene_tools._find_grip_hit` path and the view-level grip loop are **deleted** and were NOT reintroduced by Leg A. This spec no longer defines a grip protocol; see **`selection-manipulator.md`** for handle lifecycle (activation, hit-test, held-preview/bake-on-release, per-item drag semantics, multi-item propagation, OSNAP-per-handle, Esc-restore) and each entity's own spec for its grip catalog.

**What this spec guarantees at the selection boundary:**

- On selection, the manipulator wraps the selection and surfaces its handles; multi-selection shows a group frame (and handles per the manipulator's capability gating).
- A handle/grip press within the manipulator's own hit-test is consumed by it **before** HALO-driven selection picking (§5.2 step 1) — so a handle click never changes the selection.
- **Known pre-existing gap:** a Ctrl+click over the manipulator frame interior is swallowed by the interior-press guard (also noted in §5.3).

---

## 9. Keyboard Summary

| Key | Select Mode Behavior |
|-----|---------------------|
| Spacebar | Cycle the HALO preselection through overlapping candidates (§5.1) |
| Tab | **Not a selection key** — freed for the dynamic-input HUD |
| Escape | Precedence ladder: cancel manip-drag → cancel band → reset HALO cycle → clear selection (§7.1) |
| Delete | Delete selected items (`delete_selected_items`; one `selectionChanged` re-emit after the bulk delete — §5.9) |
| F3 | Toggle SNAP (snap engine, independent of selection) |

---

## 10. Divergences from Current Implementation

"Was" = pre-Leg-A behavior; "Now" = as-built (2026-09-13, plan scene). Legs B/C (elevation/3D) are unbuilt.

| Behavior | Was (pre-Leg-A) | Now (Leg A as-built) | Status |
|----------|---------|--------|--------|
| Preselection highlight | None | HALO aperture pick + `accent`-tokened traced-geometry outline (semi-transparent + glow; Rev 3) | **SHIPPED** |
| Disambiguation key | Post-click: Tab cycled same-type items (`_cycle_similar_selection`) | Pre-click: **Spacebar** cycles HALO candidates; Tab freed for the HUD | **SHIPPED** |
| Tab (wall mode) | Cycles alignment (Center/Left/Right) | Unchanged | None |
| Rubber-band (select) | Window only (L->R), Qt-native `RubberBandDrag` | Scene-drawn (view `NoDrag`), direction-dependent L->R window / R->L crossing, empty-start | **SHIPPED** |
| Rubber-band visual | Default Qt style | Blue/solid (window) vs green/dashed (crossing), live flip | **SHIPPED** |
| Ctrl+rubber-band | Replaces selection | Additive | **SHIPPED** |
| Room click target | Anywhere inside polygon | Label rect when a label shows, else polygon fallback; `shape()` stays full polygon | **SHIPPED** |
| Underlay selectability | Never | Terminal Spacebar candidate; read-only props (`requestPropertyUpdate`) + canvas context menu; locked excluded | **SHIPPED** |
| Ctrl+click | Toggle (gridlines only) | Universal toggle — gridline special case removed | **SHIPPED** |
| Escape | Mode-dependent | Precedence ladder (§7.1) | **SHIPPED** |
| Double-click (select) | Falls through to Qt | Regular click, no special action | **CLARIFIED** |
| Grip / handle ownership | Split (view-level grip loop + `_find_grip_hit`) | Owned by `SelectionManipulator` (U4); this spec delegates (§8) | **DELEGATED** |
| Selection priority | Implicit Z-order | `halo_rank`: px distance to trace; Z inside a px band; id (Rev 4) | **FORMALIZED** |
| Ctrl+click over manip frame | (n/a) | Swallowed by interior-press guard — known pre-existing gap, filed | **KNOWN GAP** |

---

## 11. Acceptance Criteria

Leg A (plan scene, 2026-09-13) — shipped:

- [x] HALO preselection: `accent`-tokened outline tracing the drawn primitive geometry (semi-transparent + soft glow; Rev 3) on the top-ranked selectable item within the aperture; clears when the aperture is empty
- [x] Spacebar-cycle: pre-click disambiguation through candidates in `halo_rank` order; underlay reachable as the last candidate; resets on cursor move; `"<Type> — i of N"` readout
- [x] Post-click same-type cycling (`_cycle_similar_selection`) removed from select mode; **Tab freed for the HUD**
- [x] Selection priority follows the shared `halo_rank` ordering (§3, §4.1)
- [x] Room click-selection restricted to the label rect when a label shows, polygon fallback otherwise; `shape()` unchanged
- [x] Direction-dependent scene-drawn rubber-band: L->R window (blue/solid), R->L crossing (green/dashed)
- [x] Ctrl+drag adds rubber-band results to existing selection
- [x] Ctrl+Click universal toggle for all selectable entity types (gridline special case removed)
- [x] Click-on-empty deselects all; Ctrl+click-on-empty preserves selection
- [x] Escape precedence ladder (§7.1)
- [x] Underlay reachable as the terminal Spacebar candidate for read-only props + context menu; no grips/transforms/direct click; locked underlays excluded
- [x] Handle press consumed by the manipulator before selection picking (§8)
- [x] Right-click never changes selection; shows context menu
- [x] Double-click in select mode behaves as regular click
- [x] HALO suppressed during rubber-band drag, manipulator drag, and active tools
- [x] Performance: HALO pick uses the spatial index, not full scene iteration
- [x] HALO on/off pill (persisted `halo/enabled`) + Preferences HALO tab (aperture + priority band, app-wide, persisted `halo/pick_aperture_px` / `halo/priority_band_px` — Rev 4)

Known pre-existing gap (filed, not resolved by Leg A):

- [ ] Ctrl+click over the manipulator frame interior is swallowed by the interior-press guard

## 12. Verification Checklist

- [ ] All acceptance criteria met
- [ ] No regressions in existing selection behavior (gridline, wall, pipe, node click-selection)
- [ ] Tool-mode behaviors unaffected (pipe placement, wall drawing, floor polygon, stretch mode)
- [ ] Snap engine unaffected during grip drag and general select mode
- [ ] Undo/redo unaffected by selection changes
- [ ] Cross-reference notes added to dependent specs (§2.3)

## 13. Future Work (out of scope for Leg A)

- **Leg B — elevation-scene selection**: ✅ **DONE (2026-09-14)** — see §14.
- **Leg C — 3D-scene selection**: handle providers for the 3D scene (orphan). Pending.
- HALO "pick from list" dense-stack dropdown (deferred).
- Preferences UX-pane reorg (rename Snapping→UX; SNAP·ALIGN·HALO tabs; grid removal; angle-snap→5°) — deferred.
- Per-entity context menu definitions.
- Selection filter toolbar (select only pipes, only walls, etc.).
- Lasso selection (freeform rubber-band).

---

## 14. Elevation Scene (Leg B, 2026-09-14)

The elevation scene (`ElevationScene`/`ElevationView`) reuses this contract via the extracted
scene-agnostic **`HaloSelectionMixin`** (`firepro3d/halo_selection.py`) — the generic HALO ranking /
aperture pick / scene-drawn rubber-band engine + 5 overridable hooks (`_halo_resolve`,
`_halo_is_underlay`, `_halo_candidate_ok`, `_halo_in_view_range`, `_halo_mode_ok`). `Model_Space`
overrides the hooks to keep §1–§12 plan behavior; `ElevationScene` mixes in with an elevation
`_halo_resolve` (walks the full parent chain: a bubble **and its label text** → parent gridline/datum) and generic defaults for the rest (no
underlays, no rooms, no tool modes in elevation). `_halo_cycle` (Spacebar) lives on the mixin;
`_emit_halo_readout` stays scene-specific (Model_Space → `instructionChanged`, Elevation →
`cursorMoved`). Rubber-band paint is shared via `halo.paint_rubber_band`; like plan, there is no live band preview and the commit is one batched `select_items` (inherited from the mixin). The manipulator is the
**sole grip owner** in elevation — the legacy `ElevationScene._find_grip_hit` + `ElevationView.paintEvent`
grip loop are retired (the borrowed `_grip_item`/`_grip_dragging` state is kept for `GripHandle`).

**Read-only-geometry contract (`view-relationships.md §3.1`).** Elevation is a read-only projection;
what's editable there is **view-furniture / annotation extent only**, never model geometry:

| Elevation item | Selectable | Manipulator surface | Editable |
|---|---|---|---|
| `ElevGridlineItem` | yes | frame + 2 extent grips | vertical draw-extent only (H pinned; persists to `_gridline_z_overrides`) |
| `ElevDatumItem` | yes | frame + 2 extent grips | horizontal draw-extent only (V pinned; session-only) |
| Read-only proxies (wall/opening/pipe/sprinkler/floor-slab/roof) | yes (property inspection) | **frame + zero handles** | none (interior-drag inert) |

**Capability idiom (`selection-manipulator.md`):** the manipulator only wraps items declaring a
`translate` capability, so §3.1-safe wrapping uses (a) an **axis-constrained `manip_translate`** for
gridline/datum (drops the pinned axis) and (b) a **no-op `manip_translate`** for read-only proxies
(which also declare `manip_handles() → []` for the frame-with-zero-handles look). Interior-drag never
changes a pinned axis (behavioral §3.1 guard) and never moves a proxy. **No undo** in elevation
(parity with prior behavior; filed follow-up). Cross-view selection sync stays out of scope
(`view-relationships.md §1.3`).
