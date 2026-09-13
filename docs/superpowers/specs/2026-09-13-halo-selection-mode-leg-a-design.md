# HALO + Selection-Mode Leg A — Design of Record

> **Date:** 2026-09-13
> **Task:** U5 Leg A (from `selection-manipulator.md` Unification Roadmap) — fold `selection-mode.md`
> into the plan scene against the already-unified `SelectionManipulator`.
> **Status:** approved (brainstorm) → drives the implementation plan.
> **Governing specs updated by this work:** `docs/specs/selection-mode.md` (§4 rewritten as HALO,
> in place; §5.1/§8/§10 reconciled), `docs/specs/snap-toolbar.md` (HALO pill row),
> `docs/specs/selection-manipulator.md` (U5 as-built stamp at wrap-up).

## 1. Scope

**In scope (this task):**
- **HALO** — the preselection highlight engine (aperture pick → pure ranking → hover highlight →
  status readout → Spacebar cycle), replacing `selection-mode.md` §4's bare cyan outline.
- HALO **disable-during-placement** gate (only SNAP + ALIGN live in tool modes).
- HALO **on/off pill** beside SNAP/ALIGN + a **minimal** settings surface (enable + aperture px) in
  the existing Snapping pane.
- Scene-drawn **direction-dependent rubber-band** (live window/crossing).
- **Room** label-rect click restriction (with polygon fallback when no label).
- **Underlay** as terminal Spacebar candidate (read-only + context menu, no grips).
- **Universal Ctrl+click** toggle (retire the gridline-only special case).
- **Escape** clears selection / cancels drag / resets the HALO cycle.

**Out of scope (filed as follow-ups):**
- **Leg B** (elevation-scene handle providers) and **Leg C** (3D-scene handle providers) — each
  blocked on its own unbuilt selection spec; already tracked as P2 backlog spec-sessions.
- **Preferences "UX pane" reorganization** — rename *Snapping* → **UX**; SNAP/ALIGN/HALO tabs;
  remove dead grid-spacing; move angle-snap into SNAP (own container, default 5°). Touches the
  **orphan** `preferences_dialog.py` (needs its governing spec forged first — existing P3 todo) and
  bundles snap/grid cleanups. Separate task.
- HALO **"pick from list"** dropdown for very dense stacks (Spacebar cycling covers v1).

**Precondition honored:** the `SelectionManipulator` is already the sole grip owner (U4, 2026-09-12).
This task does **not** reintroduce the deleted `scene_tools._find_grip_hit` path; grip priority is the
manipulator's job. Manipulator press routing (`model_space.py:4260-4273`) is untouched.

## 2. Problem definition (settled in Phase 2 grill — the WHAT)

Locked decisions:
- **Disambiguation → Spacebar.** Spacebar cycles HALO candidates (top-Z → … → underlay-last). The
  post-click same-type cycling (`_cycle_similar_selection`) is **retired**. **Tab is freed** for the
  dynamic-input HUD unconditionally. Tool-mode Spacebar (wall/opening alignment, pipe Z-stack)
  unchanged.
- **Rubber-band:** empty-canvas-start only (item interior = manipulator move, handle = transform);
  **live-flipping** blue/solid (window, `ContainsItemShape`) ↔ green/dashed (crossing,
  `IntersectsItemShape`); mode locked at release; `<5px` = click; **Ctrl = additive**.
- **Room click target:** label-bg rect when a label is visible; **fall back to polygon interior**
  when no label. Rubber-band tests the same target.
- **Underlay:** reachable **only** as the terminal Spacebar candidate; read-only properties + canvas
  context menu; no grips; locked underlays excluded.
- **Hover (HALO):** highlight the top-ranked candidate; suppressed during rubber-band drag /
  manipulator drag / tool mode / pan / pill-off; early-out when the top candidate is unchanged;
  child → parent resolution (sprinkler → Node, gridline bubble → Gridline).
- **Ctrl+click:** universal toggle across all selectable types (retire gridline special case);
  Ctrl+click on empty = no-op. **Escape:** clears selection + cancels in-progress manipulator drag +
  resets HALO cycle/clears hover. **Double-click** in select mode = regular click. **Right-click**
  never deselects; auto-selects an unselected item under cursor for its context menu.

## 3. HALO — Highlight-Activated Lock-On (engine design)

HALO is the user's richer replacement for `selection-mode.md` §4. It is framed as a peer to SNAP and
ALIGN (own pill, own future Preferences tab), but for this task its behavior lives in
`selection-mode.md` §4-as-HALO (promote to its own governing spec if/when the UX-pane follow-up lands).

### 3.1 Candidate gathering (aperture pick)
- On every mouse move in select mode, the **view** runs an aperture pick: a **4–8px screen-space box**
  around the cursor (default ~6px), mapped to a scene `QRectF`, queried via
  `scene.items(apertureRect, Qt.ItemSelectionMode.IntersectsItemShape, Qt.SortOrder.DescendingOrder, dt)`
  where `dt = view.viewportTransform()`. Qt's scene BSP **is** the spatial index (sub-ms at
  mouse-move frequency) — no full-scene iteration.
- **Two hard filters** (a candidate must pass both):
  1. **Z-slab / view-range:** intersects the active plan view range (reuse `_apply_z_filter` /
     `view_height` / `view_depth`). Anything above the cut plane or below view depth is invisible to
     picking even if it projects onto the same XY.
  2. **Visibility:** `isVisible()` **and** its Display-Manager category is visible (hidden/frozen
     categories excluded).
- Only items with `ItemIsSelectable` participate. `_exclude_from_bulk_select` items
  (DetailMarker, ViewMarkerArrow) still participate in *hover/click* (they're individually
  selectable) — that flag governs bulk/rubber-band only.

### 3.2 Ranking (pure, deterministic, shared)
The ranking function is **pure** and is the single source consumed by hover, Spacebar cycle, **and**
click — the three paths must never compute candidates differently (the classic bug source). Order:
1. **Runtime Z descending** — the app's elevation-based Z already encodes "depth along the view"
   (Node 0.5 > Pipe 0.4 > Wall 0.3 > Room 0.2 > Roof 0.1 > Floor 0.0; specials by their own Z).
2. **Screen distance** from cursor to the candidate's nearest geometry (so a small item on a big
   slab is reachable).
3. **§3 priority class** (`selection-mode.md` §3 table) as the "detail over background" tiebreak.
4. **Stable element-ID** — coincident items at identical Z need a deterministic order or the cycle
   sequence jitters between frames.

**Deviation from the source idea:** sub-geometry ranking (vertices > edges > faces) does **not**
apply — the manipulator owns vertex/edge grips. HALO ranks **whole entities**.

**Child → parent resolution** happens during candidate assembly (sprinkler SVG → parent Node,
gridline bubble → parent Gridline), so the candidate list holds selectable parents, deduped.

**Room** enters the candidate list only if the aperture hits its **label-scene-rect** when a label is
visible; when no label is visible, the room's full polygon is the hit target (fallback).

**Underlay** is appended **last** (terminal candidate), and only when unlocked
(`ItemIsSelectable` true).

### 3.3 Hover highlight + readout
- The **top-ranked** candidate (or the Spacebar-cycled one) gets an immediate preselection highlight
  (no delay), drawn as an **overlay pass** in `Model_View.drawForeground` (reuse the
  `paint_snap_indicator` cosmetic-outline pattern) — the **whole element's** `shape()` outline in
  scene coords, cosmetic pen.
- Color routes through a **new theme token** `selection_hover` (seed `#00BFFF` DeepSkyBlue), distinct
  from committed-selection styling and from snap-center cyan (`#00eeee`). (Smoke check: reads distinct
  from the window rubber-band blue — different context, thin item outline vs rect.)
- **Status-bar readout:** `"<Type> <Name> — <i> of <N>"` (e.g. `Wall W2 — 1 of 4`), so the user knows
  cycling is available before trying it.

### 3.4 Spacebar cycle
- State on the **scene** (`Model_Space`): `_halo_candidates: list`, `_halo_index: int`,
  `_halo_pick_pos: QPointF`.
- Spacebar (scene `keyPressEvent`) advances `_halo_index` through the ranked list, **wrapping**;
  the readout counter updates.
- The **pick point is frozen** during cycling; a cursor move **> tolerance (~a few px)** rebuilds the
  candidate list and **resets** the cycle to the top item (safe default; if the rebuilt list is
  identical the index may be preserved for smoothness).
- **Esc** drops to the top candidate or clears the pre-highlight (see §7 Escape for the full
  precedence).
- Guarded to fire only when the **viewport has focus and no text field does** (existing scene-focus
  gating). **Retires** `_cycle_similar_selection` (the old post-click same-type Spacebar behavior);
  tool-mode Spacebar (wall/opening alignment, pipe Z-stack) is untouched.

### 3.5 Click to select
- Left-click commits the **currently highlighted** candidate (the cycled-to one, **not** automatically
  the topmost). Style switches from preselection to committed selection; cycle state resets.
- **Ctrl+click** adds/toggles the highlighted candidate in the selection set (cycling still works
  before a modified click). Universal across all selectable types (folds the gridline-only special
  case at `model_space.py:4275-4293` into the generic toggle at `4342-4346`).
- Click on empty space clears the selection (or begins a rubber-band per §5).

### 3.6 Disable gate (state ownership: scene, driven by view + pill)
HALO is **suppressed** (no candidate build, no highlight, no cycle) when **any** of:
- `mode ∉ {select, None}` (a placement/drawing tool is active — only SNAP + ALIGN wanted there),
- a rubber-band drag is in progress,
- a manipulator drag (move / grip / rotate / resize) is in progress,
- the view is panning,
- the **HALO pill is off** (global user switch, persisted to `QSettings`).

## 4. Rubber-band (scene-drawn, replaces Qt-native in select mode)

- `Model_View._on_mode_changed`: in select mode set **`DragMode.NoDrag`** (was `RubberBandDrag`); the
  band is app-drawn, not Qt-native (Qt-native gives one style + one selection mode + no live
  direction switch).
- **Initiation:** band begins only on an **empty-canvas** left-press (item interior = manipulator
  move, handle = transform, grip = grip-drag — all higher priority, unchanged). `_rb_start` recorded
  on the view (existing field); `_rb_active`/`_rb_end` added.
- **Live feedback:** the band is drawn in `drawForeground`, its style **flipping live** as the cursor
  crosses `start.x()`: `end.x() ≥ start.x()` → **blue solid** (window); `end.x() < start.x()` →
  **green dashed** (crossing). Colors route through theme tokens.
- **Threshold:** Manhattan `< 5px` on release = treat as click (existing behavior).
- **Commit at release** (view → `scene.commit_rubber_band(sceneRect, crossing: bool, additive: bool)`):
  - window → `Qt.ItemSelectionMode.ContainsItemShape`; crossing → `IntersectsItemShape`.
  - `additive` = Ctrl held: results **added** to the current selection; otherwise selection is
    **cleared first**.
  - **Exclusions:** `_exclude_from_bulk_select` items and underlays are excluded from both modes.
  - **Room** is tested against its label-scene-rect (or polygon when no label).
- Direction-detection logic is generalized from the existing stretch-mode crossing path
  (`model_view.py:709-725`), but select-mode selection is **plain selection**, not stretch geometry
  edits — no coupling to `begin_stretch_crossing`.

## 5. Entity-selectability rules

### 5.1 Room label-rect (no `shape()` narrowing)
- **`shape()` stays the full polygon.** A prior narrowing of `shape()` to the label area caused a Qt
  paint-culling regression (the room vanished when the label scrolled off-screen — memories
  `project_qt_shape_culling`, `room.py:405-425` note). We do **not** repeat that.
- Add a public **`Room.label_scene_rect() -> QRectF | None`** — the label-bg rect in scene coords, or
  `None` when no label is visible (no name/tag or `_show_label` off). Derived from the existing
  `_label_bg` child (`room.py:250-261`).
- HALO candidate assembly + rubber-band containment use `label_scene_rect()`:
  **present** → the room is a candidate only if the aperture/band hits the label rect;
  **absent** → fall back to the full polygon (`contains`/intersect) so every room stays
  canvas-selectable.

### 5.2 Underlay terminal candidate
- Underlays keep `ItemIsSelectable` (already set; cleared when locked). They are **never** the target
  of a direct click or rubber-band; they are appended **last** to the HALO candidate list.
- Selecting a Spacebar-reached underlay: property panel shows **read-only** underlay props
  (path/scale/level/layers); right-click shows the underlay context menu (reuse the canvas path
  `model_space.py:6396-6408` → `underlay_context_menu.py`). **No grips**, no transform (the
  manipulator already renders none for an underlay group).

### 5.3 Escape (precedence)
Extend `model_space.py:6759-6787`:
1. If a manipulator drag is in progress → cancel it (manipulator restores pre-drag state, no undo).
2. Else if a rubber-band drag is in progress → cancel the band.
3. Else if the HALO cycle is active → reset the cycle + clear the hover highlight.
4. Else clear the entire selection.
(Tool-mode Escape — exit mode — is unchanged for `mode ∉ {select, None}`.)

## 6. State ownership summary

| State | Home | Rationale |
|---|---|---|
| `_halo_candidates`, `_halo_index`, `_halo_pick_pos` | `Model_Space` (scene) | spec §5.1; read by `drawForeground`; Spacebar in scene `keyPressEvent`; selection commit is scene-level |
| aperture pick (per-move) | `Model_View.mouseMoveEvent` → `scene.halo_update(pos, view)` | view owns `viewportTransform` + cursor px |
| `_rb_start` / `_rb_active` / `_rb_end` | `Model_View` (view) | viewport-px interaction; already view-side |
| rubber-band selection commit | `scene.commit_rubber_band(...)` | selection is scene-level |
| HALO pill on/off | `QSettings` + status chrome | global user switch |
| theme tokens (`selection_hover`, band colors) | `theme.py` | theming leash (no raw hex in chrome/canvas-feedback) |

## 7. Phasing (each independently shippable + parity-tested)

- **Phase A — HALO engine:** aperture candidate-gather + pure ranking + hover overlay + status
  readout + Spacebar cycle (retire `_cycle_similar_selection`, free Tab) + disable-gate + on/off pill
  + minimal settings (enable + aperture px) in the Snapping pane + `selection_hover` token.
- **Phase B — rubber-band:** scene-drawn live-flipping window/crossing band, additive-Ctrl, `<5px`
  click, exclusions, room label-rect containment; view → `NoDrag` in select mode.
- **Phase C — entity rules:** `Room.label_scene_rect()` + label-rect restriction (polygon fallback);
  underlay terminal-candidate selection (read-only + context menu); universal Ctrl+click (fold
  gridline special case); Escape precedence.

## 8. Testing

- **Posted-`QMouseEvent` / `QKeyEvent`** interaction tests via `app.sendEvent` — never
  `QTest.mouseMove` (inert here, `project_qtest_mousemove_inert`), never slot-level calls
  (`project_qt_tests_drive_widgets_not_slots`). Drive a **shown** view (`project_offscreen_qpa...`
  / fixtures must `show()`).
- **HALO ranking is a pure-function unit test:** construct overlapping real domain items
  (Wall/Room/Pipe/Node/Underlay), assert the single ordered candidate list; assert hover, cycle, and
  click all consume that same order (the correctness invariant).
- **Suppression + early-out:** assert no candidate build during tool mode / band drag / manipulator
  drag / pan / pill-off; assert early-out when the top candidate is unchanged.
- **Spacebar cycle:** posted-key test cycling top-Z → … → **underlay last**, wrapping; reset on cursor
  move > tolerance.
- **Rubber-band:** posted press→move→release with real start/end X — window (L→R) selects
  fully-contained, crossing (R→L) selects intersecting; Ctrl additive; exclusions honored.
- **Room:** label-present → only label-rect selects; label-absent → polygon selects (both asserted).
- **Underlay:** locked → not a candidate; unlocked → terminal candidate, read-only, context menu, no
  grips.
- **Ctrl+click** universal toggle; **Escape** precedence ladder.
- Every guard **red-verified** (revert the behavior → the test goes RED).
- **Full suite** run chunked in separate processes (`project_fullsuite_crash_playbook`).
- **Live smoke** in both themes via the real entry point — hover/pan/band are live-only bug classes
  (`project_live_render_bugs_dodge_headless`); verify HALO highlight renders live (the focused-item
  `QPainter engine==0` class is a known live-only hazard for overlay paints).

## 9. Spec reconciliation (Phase 6)

- `selection-mode.md`: rewrite §4 as **HALO**; update §5.1 (Tab → Spacebar disambiguation; retire
  post-click same-type), §8 (grip protocol now the manipulator's — remove the `_find_grip_hit` /
  12px-tolerance language), §10 divergence table (Tab rows, hover→HALO), §5.3 room fallback, §5.5
  underlay; flip status from "spec-only" to *building/partial*. Add cross-refs.
- `snap-toolbar.md`: add the HALO pill row beside SNAP/ALIGN.
- `selection-manipulator.md`: stamp the U5 (Leg A) as-built section; `last-verified` + `verified-commit`.
- `SPEC-INDEX.md`: note HALO's home in `selection-mode.md`; flip Selection-mode status to partial.

## 10. Follow-ups to file (Phase 6)

- U5 Leg B — elevation-scene handle providers (maps to the existing P2 "Spec session: Elevation view
  selection mode").
- U5 Leg C — 3D-scene handle providers (orphan gate on `view_3d.py`; maps to P2 "Spec session: 3D
  view selection mode").
- Preferences **UX-pane reorg** (rename Snapping→UX; SNAP/ALIGN/HALO tabs; grid-spacing removal;
  angle-snap→SNAP@5°) — gated on forging the Preferences governing spec.
- HALO **"pick from list"** dropdown for very dense stacks.
