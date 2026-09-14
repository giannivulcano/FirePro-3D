---
status: proposal          # design-of-record for U5 Leg B — unbuilt
last-verified: 2026-09-14
verified-commit: 746cc1c   # HEAD at design time (U5 Leg A merged)
applies-to:               # governing specs updated in place when built (no parallel spec file)
  - firepro3d/elevation_scene.py
  - firepro3d/elevation_view.py
  - firepro3d/elevation_manager.py
  - firepro3d/selection_manipulator.py
  - firepro3d/manip_handle.py
  - firepro3d/halo.py             # + new paint_rubber_band helper
  - firepro3d/halo_selection.py   # NEW — HaloSelectionMixin (extracted generic HALO/band engine)
  - firepro3d/model_space.py     # HALO engine → mixed in via HaloSelectionMixin; keeps the 5 hook overrides
  - firepro3d/model_view.py      # scene-drawn rubber-band paint → shared halo.paint_rubber_band
governing-specs:          # the in-place homes for the built contract
  - docs/specs/selection-mode.md          # §13 Leg B → built; add elevation section
  - docs/specs/selection-manipulator.md   # U5 Leg B → built
  - docs/specs/view-relationships.md       # §3.1 reconciliation (annotation-extent editing)
source-tasks:
  - "todo_open.md: U5 Leg B — elevation-scene selection + handle providers [P2]"
---

# U5 Leg B — Elevation-scene Selection + Handle Providers — Design Spec

> **Phase 2 (grill) locked the WHAT (2026-09-14).** This DoR carries the design ("how"). Scope
> decision: **A — selection-UX parity + wrap the existing annotation-extent grips only; introduce NO
> new editable geometry.** The `## Design Decisions` section holds the open questions for the
> Phase 3 brainstorming session.

## Goal

Bring the plan scene's selection UX — **HALO** preselection (hover highlight + Spacebar
disambiguation), the unified `SelectionManipulator` frame, and the scene-drawn window/crossing
rubber-band with live preview — to the **elevation scene**, and retire elevation's independent grip
path (`elevation_scene._find_grip_hit` + `ElevationView.paintEvent` grip squares) by folding its
existing annotation-extent grips into the manipulator. No expansion of what is editable in elevation.

## Motivation

The elevation scene is the last place in the app with an **independent, parallel grip system** (its
own `_find_grip_hit` hit-test + `paintEvent` grip renderer + press/move/release lifecycle). The U1–U4
unification made the `SelectionManipulator` the sole grip owner in the plan scene precisely to kill
the "two systems fighting one item" bug class (`selection-manipulator.md` Unification Roadmap). Leg B
extends that single-owner model to elevation. It also closes the selection-UX inconsistency: elevation
has no hover preselection and only a Qt-native rubber-band (no window/crossing, no live preview),
while the plan scene has the full HALO experience.

## Architecture & Constraints

Binding constraints (from the governing specs + Phase 2 grill):

- **§3.1 read-only-geometry invariant (`view-relationships.md`).** Elevation is a read-only projection;
  geometry is authored only in plan. The existing gridline/datum grips edit **view-furniture /
  annotation extents** (gridline vertical draw-extent → `_gridline_z_overrides`; datum horizontal
  draw-extent — session-only), never model geometry: gridline H is pinned (`self._h`), datum V is
  pinned (`self._v`). Leg B must **preserve those constraints** — no interior-drag "move" for
  gridline/datum (a lateral drag would change the pinned axis = geometry authoring), and no group
  transform on read-only proxies. Spec work **reconciles §3.1** to explicitly permit annotation-extent
  editing (it is not a contract *relaxation*).
- **Capability gating (`selection-manipulator.md`).** The manipulator surfaces handles per each item's
  declared capabilities. Read-only proxies (wall/opening/pipe/sprinkler/floor-slab/roof) get
  **frame-only, zero handles**. Gridline/datum expose their extent grips (constrained exactly as
  today). Nothing in elevation implements `manip_rotate`/`manip_scale` in v1.
- **Sole-owner / no parallel path.** After Leg B, `_find_grip_hit` + the `paintEvent` grip loop are
  retired for elevation, mirroring U4's plan-scene retirement.
- **Parity, not new behavior.** Grip drags produce byte-identical `_gridline_z_overrides` results;
  commit persists as today; **no undo** (elevation has no undo stack — deferred follow-up).
- **Fixed, small selectable set** — 2D geometry cannot be placed in elevation today, so there are no
  2D-geometry handle providers to build (deferred feature; would ride this frame later).

## Design Decisions

> **Resolved in the Phase 3 brainstorming session (2026-09-14).** Scope A held throughout.

### 1. HALO/rubber-band reuse → extract a scene-agnostic `HaloSelectionMixin` *(chosen; alts B/C rejected)*

The HALO + scene-drawn-rubber-band engine currently lives as `Model_Space` methods but is **almost
entirely scene-generic** — `halo_rank`, `halo_candidates_at`, `halo_update`, `halo_clear`,
`halo_item`, `commit_rubber_band`, `rubber_band_hits`, `update_band_preview`, `clear_band_preview`,
`_escape_ladder` — reaching into only **five small plan-specific hooks**:

| Hook | Plan (Model_Space) behavior | Generic default (mixin) | Elevation override |
|---|---|---|---|
| `_halo_resolve(item)` | Sprinkler→Node, Badge→DesignArea, gridline-label→GridlineItem | identity (return item) | `_ElevBubble`→parent gridline/datum; proxies→self |
| `_halo_is_underlay(item)` | `find_underlay_for_item` parent-walk | `False` | inherit default (no underlays in elevation) |
| candidate-filter (Room label-rect) | `_halo_room_hit` line in `halo_candidates_at`/`rubber_band_hits` | pass-through (no filter) | inherit default (no rooms) |
| `_halo_in_view_range(item)` | already permissive `True` | `True` | inherit |
| `_halo_mode_ok()` (used by `_halo_suppressed`) | `self.mode in (None,"select")` | `True` | inherit (elevation has no tool modes) |

New module **`firepro3d/halo_selection.py`** holds `HaloSelectionMixin` (the 9 generic methods + HALO/
band state: `_halo_candidates`/`_halo_index`/`_halo_pick_pos`/`halo_enabled`/`_band_preview`/
`_rb_active_flag`). `Model_Space` mixes it in and **overrides the 5 hooks** to preserve today's
behavior verbatim; `ElevationScene` mixes it in with the elevation `_halo_resolve` and inherits the
rest. Chosen over (B) a shared base scene class (heavier — both already extend `QGraphicsScene`; MI/
hierarchy churn) and (C) minimal reimplementation on `ElevationScene` (two divergent copies of the
ranking/band logic — drift risk, violates one-fact-one-home). **Regression guard:** the existing
plan-HALO parity suite must stay green across the extraction (run it as the first checkpoint).
`halo.py` paint functions are already scene-agnostic → reused as-is.

### 2. `ElevationView` overlay path → focused `drawForeground`, NOT a `Model_View` subclass

`ElevationView` stays a lean `QGraphicsView`. Subclassing `Model_View` is rejected — it would drag in
tool-modes / snap / placement / keyPress routing that the elevation view must never have. Add a
focused `drawForeground` override that paints HALO highlight + scene-drawn band + band preview,
reusing the scene-agnostic `halo.py` paint helpers. The manipulator **frame/handles render
themselves** (the manipulator is a `QGraphicsObject` added to the scene at `z=1e6`), so
`render_overlay` (the clipped-detail-view path) is **not** required here. The legacy `paintEvent`
grip-square loop is removed (retired with `_find_grip_hit`).

### 3. Manipulator construction for `ElevationScene`

Reuse the scene-parameterized `SelectionManipulator` exactly as `PaperScene` does:
`commit_hook` = the annotation-extent persist (`ElevGridlineItem._commit_grip_override` →
`_gridline_z_overrides`; datum live-apply) — **no undo**; `handle_units="px"` (screen scene);
`exclude` = elevation furniture that must never be wrapped (`_ElevBubble` and other
`_ROLE_ELEV_ANNOTATION` child decoration that isn't itself selectable). Verify no `Model_Space`-only
attribute leaks into the manipulator's generic path (getattr-guard scene bridges).

### 4. Gridline/datum + read-only-proxy capabilities (CORRECTED 2026-09-14 after T4 grounding)

**Correction:** the manipulator **only wraps items that declare a `"translate"` capability** —
`item_capabilities()` grants it iff the item has `manip_translate`/`translate`/is a Node, and
`rebake()` (`selection_manipulator.py:451`) *excludes* anything lacking it (hides the frame if
`_items` is empty). `manip_capabilities()` can only *narrow* (intersect), never add. So the original
"omit `manip_translate` → frame-only, no interior move" is **impossible**: a no-translate item gets
**no frame and no grips at all**. (`ViewMarkerArrow`, the cited "resize-only" precedent, in fact
implements `manip_translate` — that's why it wraps.) The fix:

- **`ElevGridlineItem`/`ElevDatumItem`** — implement an **axis-constrained `manip_translate`**:
  gridline drops `dx` (H pinned to `self._h`; applies `dy` to both endpoints → vertical extent
  shift); datum drops `dy` (V pinned to `self._v`; applies `dx` → horizontal extent shift). This
  grants the `translate` capability so the manipulator wraps them and their `manip_handles()` extent
  grips render, while the §3.1 invariant (pinned axis unchanged) holds. Plus `manip_handles()` via
  `default_grip_handles(self, circular={0,1})`. The §3.1 guard is **behavioral** — "an interior-drag
  does not change the pinned axis" — NOT structural ("no `manip_translate`").
- **Read-only proxies** (wall/opening/pipe/sprinkler/floor-slab/roof) — implement a **no-op
  `manip_translate(dx, dy)`** (documented: elevation projections are not editable; the no-op exists
  solely to obtain the manipulator frame for selection **parity with the plan scene**, honoring
  §3.1). They implement no `manip_handles`/`manip_scale`/`manip_rotate` → the manipulator shows the
  **frame + zero editing handles**. Interior-drag is inert (bakes nothing; `commit_hook` finds no
  gridline to persist). **Residual parity gap (accepted, smoke-checked):** a drag-attempt on a proxy
  previews a move then snaps back — file an interior-move-suppression polish follow-up if it reads
  janky.

**Rebake-ordering:** gate grip presence on `isSelected()`, never on an `itemChange`-mutated
visibility flag (the ViewMarkerArrow lesson in `selection-manipulator.md`).

**Governing-spec note (Phase 6):** `selection-manipulator.md:676-679` says `manip_translate` is
mandatory to wrap — the elevation section must record the **no-op / axis-constrained translate**
idiom as the sanctioned way to get a read-only or axis-pinned item wrapped. **Also** record the
`_active_handles` contract refinement made during T4b: an item that *declares* `manip_handles()` is
now authoritative (its possibly-**empty** set is honored); the rigid resize fallback fires only when
**no** selected item provides `manip_handles` (Node/sprinkler). This supersedes the U2 as-built line
"`_active_handles()` returns `union(...) or rigid_set`". Verified safe against Room/DesignArea/
ViewMarker/box-native-rect parity suites (they route via the earlier box-native return or are
capability-gated to frame+move regardless).

### 5. Rubber-band generalization

The scene-side band query rides on the mixin (§1). View-side: set `ElevationView` drag mode
`RubberBandDrag → NoDrag`; add the band lifecycle to its mouse handlers (empty-canvas press →
extend on move → `update_band_preview` → release → `commit_rubber_band`; Esc cancels). The band
**paint** — currently inline in `Model_View.drawForeground` — is extracted to a shared
`halo.py` helper `paint_rubber_band(painter, view, rb_start, rb_end, crossing, theme)` (mirroring
`paint_halo_highlight`) and **both** views repoint at it (small GENERALIZE, parity-tested against the
current plan band look).

### 6. Selection routing

Add a HALO-committed press path to `ElevationScene.mousePressEvent` (select `halo_item() or
item_under`, Ctrl-toggle, clear-on-empty) — the plan `_press_select_item` equivalent — replacing
reliance on Qt-native select-on-press. Handle presses are consumed by the manipulator's `_HandleItem`
scene children first (same ordering as plan); non-handle presses run HALO commit or band start. The
existing `_on_selection_changed → entitySelected` (property-panel wiring) is untouched and still
fires. **One reconciliation:** `ElevDatumItem.mousePressEvent` (self-intercepts bubble clicks) is
removed so the datum flows through HALO like every other item.

### Governing-spec updates when built (in place — no parallel file)

- `view-relationships.md §3.1` — reconcile: elevation permits **view-furniture / annotation-extent**
  editing (gridline draw-extent, datum draw-extent), which is *not* geometry authoring; the read-only-
  *geometry* contract stands.
- `selection-mode.md` — add an elevation section; flip §13 "Leg B" from pending → built.
- `selection-manipulator.md` — U5 Leg B → built (mixin extraction, elevation manipulator, retirement).
- `SPEC-INDEX.md` — stamp selection-mode / selection-manipulator statuses.

## Acceptance Criteria

- [ ] HALO hover highlights the top-ranked selectable elevation item within the aperture; clears on
      empty aperture; Spacebar cycles overlapping candidates with a `"<Type> — i of N"` readout.
- [ ] Click commits the HALO-highlighted item; Ctrl+click universal toggle; click-on-empty deselects.
- [ ] On selection the manipulator frame wraps the item(s). **Handle gating:** gridline/datum surface
      their extent grips; read-only proxies (wall/opening/pipe/sprinkler/floor-slab/roof) show
      **frame + zero handles**; property inspection (`entitySelected` → panel) still fires.
- [ ] **Interior-drag is axis-constrained** for gridline/datum (drag never changes the pinned axis —
      H for gridline, V for datum); **no group transform** (rotate/scale) on any selection. Read-only
      proxies' interior-drag is inert. *(§3.1 invariant — behavioral guard.)*
- [ ] Scene-drawn rubber-band replaces Qt-native: L→R window (blue/solid, contained), R→L crossing
      (green/dashed, intersects), live HALO preview, Ctrl+drag additive.
- [ ] Gridline/datum grip drag produces the **byte-identical** `_gridline_z_overrides` result as the
      legacy path; commit persists as today (**no undo** — parity).
- [ ] Legacy `elevation_scene._find_grip_hit` + `ElevationView.paintEvent` grip-square rendering
      retired (manipulator is the sole grip owner in elevation).

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] Posted-`QMouseEvent` interaction tests on a **shown** `ElevationView` (hover/click/grip/Esc/band);
      assert observable ground truth (selected set, committed override value, HALO item) — never
      `inspect.getsource`, never `QTest.mouseMove`.
- [ ] Grip-override **byte-parity** vs the legacy `_find_grip_hit`/`apply_grip` path.
- [ ] Each guard **mutation-checked RED** with the fix reverted.
- [ ] **§3.1 no-lateral-move guard** (interior gridline/datum body drag does not change the pinned axis).
- [ ] Retirement assertion (legacy elevation grip path gone/no-op).
- [ ] No regression to Leg A (plan-scene HALO/manipulator/rubber-band) if HALO is generalized.
- [ ] Full suite green (chunked per convention); live smoke in an elevation view, both themes.
- [ ] Governing specs updated in place + SPEC-INDEX statuses stamped (Phase 6).

---

## Existing Code Context

(from Phase 1b recon — cite, do not restate mechanics the code owns)

- **`elevation_scene.py`** — `ElevationScene(QGraphicsScene)`; grip path: `_find_grip_hit` (~:474),
  `mousePressEvent` (~:490), `mouseMoveEvent` (~:517), `mouseReleaseEvent` (~:541); `ElevGridlineItem`
  (:127, `grip_points`/`apply_grip`/`_commit_grip_override` → `_gridline_z_overrides`),
  `ElevDatumItem` (:249, `grip_points`/`apply_grip`, session-only); `_gridline_z_overrides` serialized
  via `to_dict`/`from_dict` (:651/:661), re-applied on rebuild (:1307). `_ROLE_SOURCE` on proxies.
- **`elevation_view.py`** — `ElevationView(QGraphicsView)`; `paintEvent` grip squares (:74); Qt-native
  `RubberBandDrag` (:41); **no `drawForeground`**.
- **`elevation_manager.py`** — `ElevationManager.open_elevation` creates scene+view (:72).
- **Reuse targets:** `halo.py` (`paint_halo_highlight`, `halo_scene_path` — scene-agnostic),
  `SelectionManipulator` (scene-parameterized; `render_overlay` for overlay paint),
  `manip_handle.py` (`GripHandle`, `default_grip_handles`), plan HALO methods + rubber-band in
  `model_space.py`/`model_view.py` (generalization candidates).

## Edge Cases & Error Handling

- Multi-select mixing annotation items + read-only proxies → frame wraps all; grips only on annotation
  items; no group transform.
- Datum extent edits are session-only (not persisted) — parity; do not add persistence in Leg B.
- Headless/plain-scene degradation (getattr-guarded scene bridges, per the U3 wall/gridline pattern).
- Rebake-ordering: gate grips on selection, not on a visibility flag mutated by `itemChange`
  (the ViewMarkerArrow lesson, `selection-manipulator.md`).

## Non-Goals (explicit)

- Editing model geometry in elevation; 2D-geometry selection/handles in elevation (deferred feature);
  undo for elevation edits; datum-extent persistence; cross-view selection sync (`view-relationships.md
  §1.3`, own spec session).
