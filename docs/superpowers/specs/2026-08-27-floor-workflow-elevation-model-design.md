---
status: proposal          # designed 2026-08-27, unbuilt
last-verified: 2026-08-27  # code claims below checked against the tree on this date
verified-commit: b84be35   # HEAD at design time
applies-to:
  - firepro3d/floor_slab.py
  - firepro3d/model_space.py
  - firepro3d/level_manager.py
  - firepro3d/model_browser.py
  - firepro3d/property_manager.py
  - firepro3d/scene_io.py
  - firepro3d/main.py
  - firepro3d/ribbon_bar.py
source-tasks:
  - "TODO.md ## Tasks — Revise floor placement workflow (mirror wall) + floor elevation/thickness reference model"
  - "folds in: L256 (Floor Z-range spec), L105 (floor placement group), L35 (floor template persistence), L121 (floor icon)"
---

# Revise Floor Placement Workflow + Floor Elevation/Thickness Reference Model — Design Spec

> Governance: this is a **design-of-record** (proposal). At wrap-up its verified content folds into the governing spec `docs/specs/wall-room-floor-system.md §11` (stamped `current`), and it touches `2d-geometry.md §4`, `ribbon-bar.md`, `view-relationships.md` (Z-model / plan view range), `property-panel.md`. Rule A: link to those homes; do not restate owned facts (Z-order constants, level-system view-range ownership) here.

## Goal

Two coupled changes to floor slabs:

1. **Workflow** — bring `FloorSlab` placement onto the unified 2D-geometry schema-driven dispatch, exactly as `feat/wall-placement-workflow` did for walls: one checkable **Floor** button, `F` shortcut, **←/→ primitive cycle** (Corner-Rect → Center-Rect → Polygon), typed-dimension HUD, rect rotate-step, closed-polyline reuse, continuous placement.
2. **Elevation model** — replace the fixed *single datum + downward thickness* Z-definition with **two independently-specified boundaries** (top and bottom), each choosing a reference mode. Retire the owning `.level` concept entirely; floor visibility becomes pure z-range.

## Motivation

Floors today use a hand-rolled two-mode placement (`floor` = click-vertex polygon, `floor_rect` = 2-click box) via a dropdown, **not** wired into the HUD dispatch — no typed dimensions, no ←/→ cycle, no rotated rects. And the `top = level + offset` / `bottom = top − thickness` model can't express a slab that spans a story, sits on a surveyed datum, or references different levels top vs. bottom. The two-boundary model unlocks the Revit-style floor constraint the user wants; and once a floor can span or float, a single owning `.level` is *semantically* obsolete — z-range intersection is the only coherent visibility rule. This mirrors the shipped wall revision (shared machinery, no parallel path).

## Architecture & Constraints

- **Reuse the wall dispatch verbatim.** Floor registers into the same `_PRESS_DISPATCH`/`_MOVE_DISPATCH`/`_SCHEMA_FOR_MODE`/`_APPLIER_FOR_MODE`/`_PLACEMENT_VARIANTS`/`_transform_seed_values` surfaces walls use. No new placement engine (`2d-geometry.md §4`).
- **Pure, testable Z-resolution.** A module-level resolver with no Qt dependency; `z_range_mm()`/`get_3d_mesh()` are thin callers. Enables ground-truth unit tests.
- **Dual serialization.** Every new persisted field lands in **both** `scene_io` (file) and `_capture_network`/`_restore_network` (undo) in the same change (project memory: dual serialization paths).
- **Degenerate-safety, not prevention.** Allow inverted/zero-height configurations; warn + degrade (no crash, no inverted winding). One anti-degeneracy constant.
- **Panel is the single authoritative elevation editor;** the ribbon tab is lightweight. Appearance is owned by the Display Manager "Floor" category, not the panel.
- **Perf:** the view-range upper-bound computation iterates `scene._floor_slabs` once at plan-activation (not per mouse-move); spatial cost is O(floors), acceptable (project memory: spatial-filter scene iteration).

## Design Decisions

### D1 — FloorSlab data-field shape (flat fields + pure resolver)

Chosen: **flat per-attribute fields** (matches FloorSlab/Wall style; trivial dual-serialization + migration) over nested `FloorBoundary` value-objects (cleaner OO, but nested dicts and more machinery for no functional gain).

```
# Top boundary
_top_mode: str          # "level" | "absolute"
_top_level: str
_top_offset_mm: float
_top_abs_z_mm: float
# Bottom boundary
_bottom_mode: str       # "level" | "absolute" | "thickness"
_bottom_level: str
_bottom_offset_mm: float
_bottom_abs_z_mm: float
_thickness_mm: float    # input only in "thickness" mode; else a derived readout
```
Retired: `_level_offset_mm`, owning `.level`. Kept: `_points`, `_color` (construction default, not panel-edited), `name`.

**Resolver (module-level, pure):**
```
_resolve_boundary_z(mode, level, offset_mm, abs_z_mm, level_manager) -> float | None
  absolute → abs_z_mm
  level    → lvl.elevation + offset_mm   (None if level_manager.get(level) is None)
```
**Z-range:**
```
z_range_mm(self) -> (bot, top) | None:
  lm = scene._level_manager  (None → None)
  top = _resolve_boundary_z(top…)         (None → None)
  bot = top - _thickness_mm               if _bottom_mode == "thickness"
        else _resolve_boundary_z(bot…)    (None → None)
  return (min(bot, top), max(bot, top))   # ordered
```
`get_3d_mesh()` uses the same resolution (it already receives `level_manager`). Derived thickness readout = `top − bot` when bottom is not in thickness-mode.

### D2 — Degenerate handling (allow + warn)

- One constant **`MIN_FLOOR_THICKNESS_MM` ≈ 1 mm** (anti-degeneracy floor, not an architectural minimum).
- Thickness-mode input: `DimensionEdit(minimum=MIN_FLOOR_THICKNESS_MM)` → rejects ≤ 0.
- Level/Absolute inversion (resolved `bot ≥ top`): **allowed.** `get_properties()` emits a `warning` row ("Floor top is at or below its bottom — zero/inverted thickness"); `get_3d_mesh` returns `None` when `top − bot < MIN_FLOOR_THICKNESS_MM` (no inverted-winding mesh); `z_range_mm` still returns the ordered tuple so visibility/section stay defined.

### D3 — Kill owning `.level`; pure z-range visibility

**What `.level` did today (verified):** (a) an active-level visibility fast-path in `level_manager._set_level_vis` (`if item.level == active → show fully`, else fall back to z-range); (b) rename remap (`item.level = new_name`); (c) a Model-Browser **tooltip** only — floors sit under a flat "Floors (N)" node, *not* grouped by level. It does **not** drive geometry, 3D, section-cut, or grouping.

**Decision:** remove `.level` from floors.
- Floors carry `_visibility_by_zrange = True`; `_set_level_vis` routes any flagged item through **pure z-range** (`_apply_z_filter` on the active level, `_z_intersects` on others), skipping the `.level == active` fast-path. No `isinstance` coupling in `level_manager`. The −1000 `view_bottom` margin (Level.view_bottom, `view-relationships.md` owns the view-range model) keeps default slabs and cross-level spans visible.
- **Rename remap:** `LevelManager.rename_level` remaps a floor's `_top_level`/`_bottom_level` (when `== old_name`) instead of `.level`.
- **Browser:** drop the `Level:` tooltip line for floors (or derive from the top boundary for display only).

### D4 — View-range upper-bound (fold-in fix)

Today `PlanView.create` sets `view_height = next_level.elevation − _DEFAULT_SLAB_THICKNESS_MM` — a hardcoded guess at the floor-above's thickness. With arbitrary-thickness/spanning floors this is wrong (thick floor above bleeds into the current plan).

**Decision:** compute the upper bound from **live scene floors** at plan-activation/apply time: `view_height = min(bot_z of floor slabs whose top_z ≈ next_datum, within tol)`, **fallback** to `next_datum − _DEFAULT_SLAB_THICKNESS_MM` when none. Explicit user `view_top` overrides still win. A `LevelManager` helper (e.g. `compute_view_height(scene, level)`) owns the rule; the plan finalizes whether it replaces the cached `PlanView.view_height` or is recomputed at activation (source-of-truth wiring is an implementation detail; the *rule* is fixed here). This is a `view-relationships.md`/level-system change — reconcile that spec at wrap-up.

### D5 — Placement dispatch (unify + mirror wall)

- **Unify** `floor` + `floor_rect` into one **`floor`** mode; keep a back-compat `set_mode("floor_rect") → "floor"` alias (wall has the same for `wall_rect`). State: `_floor_primitive ∈ {"rect","polygon"}`, `_floor_rect_from_center: bool`.
- Router pattern mirrors wall: `_press_floor_router`/`_move_floor_router` dispatch on `_floor_primitive`; `_apply_floor_dynamic_input(geometry)` (rect: size-step → advance to rotate; rotate-step → commit; polygon: route a point through the polygon press handler); `_floor_schema_for_primitive()` (rect → `rectangle`/`rotation`, polygon → `line`); `_PLACEMENT_VARIANTS["floor"]` = [Corner-Rect, Center-Rect, Polygon] with `_set_floor_primitive` lambdas; add `"floor"` to `_APPLIER_FOR_MODE` (and per-primitive schema, `_SCHEMA_FOR_MODE` stays absent like wall); add a **`floor` branch to `_transform_seed_values`** (rotate-step angle live-seed — the wall precedent, project memory `project_transform_seed_hud_per_mode`).
- **Rect** = anchor → size → **rotate** (reuse wall's rect rotate machinery). **Polygon** = reuse the shipped `PolylineItem._closed` closed-polyline UX (blue close-ring, Enter / click-near-start, Delete pops last vertex, double-click finish). **Continuous** placement (Esc exits). HUD = geometry only; **Spacebar/↑/↓ inert.**
- **Ribbon:** collapse the Floor dropdown → one checkable button (mirror the wall button). Add **`F`** to `Model_View._TOOL_SHORTCUTS` (verified free).

### D6 — Property panel (dynamic show/hide for free)

The panel already re-queries `get_properties()` after each edit (`_apply_property → _refresh_timer → _do_refresh → show_properties`; comment: "Auto-refresh so dependent fields (e.g. elevation) update immediately"). So dynamic show/hide needs **no new machinery** — `get_properties()` returns mode-conditional rows:

```
── Top ──
  Top Reference : enum {Level, Absolute}
  (level)  Top Level : level_ref ; Top Offset : dimension
  (abs)    Top Z     : dimension
  Top Elevation : label (read-only, always)
── Bottom ──
  Bottom Reference : enum {Level, Absolute, Thickness}
  (level)     Bottom Level : level_ref ; Bottom Offset : dimension
  (abs)       Bottom Z     : dimension
  (thickness) Thickness    : dimension (minimum = MIN_FLOOR_THICKNESS_MM)
  Thickness (derived) : label   [shown when bottom ≠ thickness]
  Bottom Elevation : label (read-only, always)
  ⚠ warning row   [when resolved bot ≥ top]
```
**No `Colour` row.** Multi-select uses the existing `< mixed >` display. `set_property` maps each enum/dimension key to the corresponding field.

### D7 — Graphic Override ribbon group (reusable)

New `_build_graphic_override_group(page)` in `main.py`: **stroke-color**, **fill-color**, **Clear-to-category** buttons. Each routes selected items through `display_manager.set_override(item, <key>, hex)` / `clear_overrides(item)` on `_display_overrides` (already serialized), wrapped in `scene.push_undo_state()` so it's one undo step. The exact override property keys the Display Manager uses for stroke/fill are confirmed in the plan. Built on the Floor contextual tab first; generalizes to other entity types (feeds L122). Category default appearance stays owned by Display Manager "Floor".

### D8 — Template persistence (L35 fold-in)

QSettings `template/floor` persists **`_top_mode`, `_top_offset_mm`, `_bottom_mode`, `_bottom_offset_mm`, `_thickness_mm`** only. On fresh apply per project: level-mode boundaries resolve to the **active** level; absolute-mode boundaries seed `_*_abs_z_mm` from the active level's elevation. **Not** persisted: color, level names, absolute-Z values. Mirror the pipe/sprinkler/text template QSettings pattern.

### D9 — Migration (lossless, both paths)

`from_dict` reads legacy `{level, level_offset_mm, thickness_mm}` → `_top_mode="level"`, `_top_level=level`, `_top_offset_mm=level_offset_mm`; `_bottom_mode="thickness"`, `_thickness_mm=thickness_mm`. Legacy `thickness_ft` conversion still handled. **Re-save writes the new schema only** (legacy keys dropped; load path keeps reading them). Same `(bot_z, top_z)`, mesh, section/occlusion state as before — no visual diff. Applied to **both** `scene_io` and `_capture_network`/`_restore_network`.

### D10 — Icon (mockup-gated)

Author the Floor ribbon icon per `icon-style-guide.md`: render 2–3 SVG candidates in Phase 5; user picks. Shrinks L121 by one.

## Acceptance Criteria

**Workflow (posted-event on a real shown `Model_View`):**
- [ ] `F` → floor mode; one checkable Floor button (dropdown gone); floor registered in the schema-driven dispatch.
- [ ] ←/→ cycles Corner-Rect → Center-Rect → Polygon; rects run anchor→size→rotate; polygon closes via close-ring/Enter; placement continuous (Esc exits).
- [ ] HUD accepts typed geometry (rect W/H/angle; polygon segment length/angle); Spacebar/↑/↓ inert.

**Elevation (ground-truth on `z_range_mm`/`get_3d_mesh`):**
- [ ] All 6 top×bottom mode combos resolve the correct `(bot_z, top_z)` incl. a cross-level span (top=Level 2, bottom=Level 1).
- [ ] Inversion → `warning` row present **and** `get_3d_mesh` returns None / no inverted winding; `z_range_mm` returns an ordered tuple; thickness input rejects ≤ 0.
- [ ] Absolute-Z uses the world-mm datum (same as `level.elevation`), parsed/formatted via ScaleManager.

**Visibility / view-range:**
- [ ] Floors have no `.level`; visibility is pure z-range (default slab + cross-level span visible on the right plan(s)).
- [ ] Level rename remaps `_top_level`/`_bottom_level`; no stale refs.
- [ ] Plan view-range upper bound derives from the actual floor above (thick floor above no longer bleeds); user `view_top` override still wins; fallback holds when no floor above.

**Migration / serialization (byte-level):**
- [ ] Existing `{level, level_offset_mm, thickness_mm}` floor loads to identical `(bot_z, top_z)`/mesh/section — no visual diff.
- [ ] Round-trips byte-identical through **both** `scene_io` and `_capture_network`; legacy keys read on load, dropped on re-save.

**Panel / display:**
- [ ] No `Colour` row; mode dropdowns dynamically show/hide the right fields; derived readouts live.
- [ ] Graphic Override group sets/clears per-item stroke+fill via `_display_overrides`, one undo step each.
- [ ] Floor template (modes+offsets+thickness) persists across sessions; level/absolute specifics resolve per project.

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] Tests pass at posted-event + ground-truth + byte-identical-serialization levels (mirror the wall task's gates); red-verified before fix.
- [ ] No regressions: full suite green (chunked); walls/rooms/roofs visibility unchanged by the `_set_level_vis` carve-out and the view-range change.
- [ ] Governing specs reconciled + stamped at wrap-up: `wall-room-floor-system.md §11`, `view-relationships.md` (view-range), `2d-geometry.md §4`, `ribbon-bar.md`, `property-panel.md`.
- [ ] User smoke-test on a real project (place floors via all 3 primitives; edit all mode combos; open a legacy `.fpd`; rename a level; check a thick floor above doesn't bleed).

## Tech Context

- **Framework:** PyQt6; geometry in mm; NFPA imperial-native display via `ScaleManager` (CLAUDE.md).
- **Reuse:** wall dispatch (`model_space.py`), closed-polyline (`construction_geometry.py`), `_display_overrides` (`display_manager.py`), panel field types (`property_manager.py`), dual serialization (`scene_io.py` + `_capture_network`).
- **Avoid:** parallel placement machinery; `isinstance` coupling in `level_manager`; `QDoubleSpinBox` for dimensions (use `DimensionEdit`).

## Existing Code Context

- `floor_slab.py` — `FloorSlab(DisplayableItemMixin, QGraphicsPathItem)`; current `z_range_mm`/`get_3d_mesh`/`get_properties`/`to_dict`/`from_dict`.
- `model_space.py` — floor in `_PRESS_DISPATCH`/`_MOVE_DISPATCH`/`_ALIGN_PLACEMENT_MODES`; wall router/applier/schema/variants to mirror; `_transform_seed_values`.
- `level_manager.py` — `_set_level_vis` (fast-path), `_apply_z_filter`/`_z_intersects`, `PlanView.create` (view range), `rename_level`.
- `model_browser.py` — flat "Floors (N)" node + `Level:` tooltip.
- `property_manager.py` — field types; `_apply_property → _refresh_timer` auto-refresh.
- `display_manager.py` — `set_override`/`clear_overrides`; `_display_overrides` serialization.
- `main.py`/`ribbon_bar.py` — Floor dropdown button; `_build_placement_group`; template-shown-in-panel on mode enter.

## Edge Cases & Error Handling

- Missing level (deleted/renamed away) on a level-mode boundary → resolver returns None → `z_range_mm`/mesh return None (item simply has no Z data; no crash).
- Both boundaries absolute → floor has no level ref; rename is a no-op for it; visibility still pure z-range.
- Legacy floor with `thickness_ft` only → converted on load, then migrated to the two-boundary schema.
- Multi-select edit across floors with different modes → `< mixed >`; setting a mode applies to all, then the panel re-renders each.

## Out of scope / follow-ups (filed at wrap-up)

- Roof twin (apply this identical treatment to `roof.py`/`roof_rect`).
- L105/L35 remainder: wall + roof contextual placement group / template persistence.
- Generalize the Graphic Override group to other entity types (L122).
- RegularPolygon as a floor boundary primitive (dropped scoping option).
