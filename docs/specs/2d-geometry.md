---
title: 2D Geometry System
status: current
applies-to:
  - firepro3d/construction_geometry.py
  - firepro3d/model_space.py   # 2D-geometry placement + dispatch tables only
last-verified: 2026-08-24
verified-commit: 8a7dde4
---

# 2D Geometry System

Governing spec for the reference / drawing-geometry subsystem: the item models in
`construction_geometry.py` and their placement layer in `model_space.py`. Closes
the long-standing `construction_geometry.py` orphan (former backlog "Spec session:
construction geometry system"). Seeded from the 2026-08-22 (level-plane + fill) and
2026-08-24 (polish cluster) design-of-records under `docs/superpowers/specs/`.

> **Naming:** the module is still `construction_geometry.py` for legacy reasons
> (it began with the now-retired `ConstructionLine`). Everything user-facing says
> "2D Geometry" (the ribbon group, the Display-Manager category, `Geometry2DMixin`).
> A rename to `geometry_2d.py` is a filed follow-up.

## 1. Scope & item models

Six item classes, all built on `Geometry2DMixin` + `DisplayableItemMixin` + a Qt base:

| Class | Base | Shape |
|---|---|---|
| `LineItem` | `QGraphicsLineItem` | finite 2-point line |
| `PolylineItem` | `QGraphicsPathItem` | multi-segment polyline, **open or closed** |
| `RectangleItem` | `QGraphicsRectItem` | axis-aligned rect + optional rotation |
| `CircleItem` | `QGraphicsEllipseItem` | centre + radius |
| `ArcItem` | `QGraphicsPathItem` | 3-point / centre arc |
| `RegularPolygonItem` | `QGraphicsPathItem` | **parametric** regular N-gon |

`GridlineItem` is **not** a 2D-geometry item (it is a datum; see `grid-system.md`).

### 1.1 `Geometry2DMixin` (the shared contract)
Provides level-plane placement + fill for all six classes:
- `level` + `_level_offset_mm` (default 0, +up); `z_range_mm()` → `(elev, elev)` at
  `level.elevation + offset`; items participate in view-range + elevation-based
  z-ordering at **`Z_CAT_CONSTRUCTION`** (2D geometry wins over building geometry at
  equal elevation; below annotation/symbol/design bands).
- Fill state: `fill_type` (`none`/`solid`/`hatch`), `fill_pattern`, `fill_opacity`
  (default 0.45, solid only), fill colour on `_display_color`'s sibling
  `_display_fill_color`. `is_fillable()` is true iff `get_closed_path()` returns
  non-None. Fill is rendered in each item's own `paint()` via `draw_fill()`.
- Property rows (`_geom2d_properties`) + setter (`_geom2d_set`) + dual-path
  serialization stamps (`_geom2d_to_dict`/`_geom2d_from_dict`).

## 2. Closed polylines (invariant)

`PolylineItem` closure is an **explicit `_closed: bool` flag**, NOT a duplicated
vertex (the FloorSlab model):
- vertex list stays `[P0…Pn]` with no duplicate; `_rebuild_path()` calls
  `closeSubpath()` when `_closed and len>=3`; `is_closed()` returns the flag;
  `close()` sets it.
- The shared start/end is therefore a **single grip** (grip 0) whose drag moves
  both adjoining segments.
- **Back-compat (required):** `from_dict` migrates legacy coincident-first/last
  polylines (no `closed` key, first≈last within 1e-3) → flagged closed with the
  duplicate dropped. The `scene_io` legacy-`HatchItem` migration builds a filled
  closed polyline via `close()`. Both preserve fill.
- Consumers that copy a polyline (offset `_make_offset_item`, `update_preview`)
  forward the flag.

## 3. RegularPolygonItem (parametric)

Stores `_center`, `_sides` (3–120), `_radius_mm`, `_rotation_deg`, `_inscribed`;
**vertices are always derived** (`vertices()`), never stored.

- **Geometry convention:** *inscribed* → `_radius_mm` is the circumradius
  (centre→vertex); *circumscribed* → `_radius_mm` is the apothem (centre→edge
  midpoint). `vertices()` applies a half-step (`180/sides`) orientation offset for
  circumscribed internally, so `_rotation_deg` = the desired orientation directly
  (0° = a vertex/edge pointing +x).
- **Y-up rotation (invariant):** `vertices()` uses `cy - rv*sin(a)` and `apply_grip`
  uses `atan2(-dy, dx)` — the app-wide **Y-up / CCW-positive** convention, matching
  the placement rotate angle, the dashed reference line, and the shared "rotation"
  HUD schema. The two are exact mutual inverses (a dragged vertex lands under the
  cursor). Ground-truth tests assert the *observable* vertex direction, not
  `rotation()==angle`.
- **Grips:** `grip_points()` = `[centre] + vertices`; grip 0 moves the centre; a
  vertex grip drag sets radius+rotation keeping it regular (no free deform).
- **Properties:** Sides / Radius / Rotation / Shape(enum) + the mixin rows;
  `set_property` regenerates.
- **Serialization:** `type: "polygon"` with centre/sides/radius/rotation/inscribed.

## 4. Placement workflows (`model_space.py`)

Placement is **always continuous** (the `single_place_mode` opt-in was removed
2026-08-24): every commit re-arms the tool; **Esc** exits to select. A mode is
registered by adding rows to the dispatch tables: `_PRESS_DISPATCH`,
`_MOVE_DISPATCH` (mouse-move preview — distinct from `_PREVIEW_DISPATCH`, the HUD
field-commit path), the instruction map, cursor map (`model_view.py`),
`_SCHEMA_FOR_MODE`/`_APPLIER_FOR_MODE`, and `get_placement_anchor`.

- **Line/rect/circle/arc:** see the existing 2-click (+ rect/arc rotate/variant)
  handlers. Rectangle & Arc expose ←/→ placement variants; rectangle & polygon
  have a rotate step whose HUD uses the shared **"rotation"** schema (step-aware
  `active_schema`; the rotation seed dispatches by mode to the correct pivot).
- **Polyline:** multi-click; **click the START vertex (≥3 verts) to close** (a
  distinct blue close-ring cues it near the first vertex); double-click / Enter
  finish *open*; **Delete** pops the last vertex (routed via a `Model_View`
  `ShortcutOverride` accept so it beats the window Delete shortcut; cancels at one
  vertex). All stay in polyline mode.
- **Polygon (3-step, mirrors centre-rectangle):** centre → radius (axis-aligned) →
  rotate. `↑/↓` change #sides and `←/→` toggle inscribed/circumscribed **live at
  every step**; a dashed **reference circle** shows during placement and while the
  polygon is **selected**; the readout carries the sides/shape hints; the HUD
  Angle field live-seeds during the rotate step. Radius < 0.5 mm is rejected
  (centre stays armed).

## 5. Snap contribution (`snap_engine.py`)

Each closed shape emits its named snap points and intersection segments. The
polygon (like the rectangle) emits **vertices (endpoint), edge midpoints
(midpoint), centre (center)**, plus its edges as intersection/nearest/perpendicular
segments — its branch must precede the generic `QGraphicsPathItem` branch in every
dispatch site (emitter, `_phase4_items`, `_geometric_snaps`).

## 6. Persistence (dual path — invariant)

Every item type persists through **both** hand-written serializers (memory: dual
serialization): `_capture_network`/`_restore_network` (undo) **and** `scene_io.py`
(file), plus copy/paste dispatch and the clipboard-ghost ctors. A new item list
(e.g. `_draw_polygons`) must also be added to the read/collect helpers that
enumerate the sibling lists: `_items_on_level`, `_all_geometry_items`
(`scene_tools.py`), the level-visibility + elevation-z passes (`level_manager.py`),
`_all_scene_items` (`level_widget.py`), the "2D Geometry" category collector
(`display_manager.py`), and the 3D renderer (`view_3d.py`). Grep `_draw_arcs`
across `firepro3d/` to find them all.

## 7. Display

The **"2D Geometry"** Display-Manager category owns colour / visibility / opacity
for all six item types (mirrors Design Area; no per-category line-weight yet).
Fill is a per-item property, independent of the category.

## Cross-references (Rule A — these own the linked facts)
- Z-order / elevation model → `view-relationships.md §7.3` + `constants.py`.
- Level-plane placement + fill design → `view-relationships.md §3.3/§7.3`.
- Ribbon "2D Geometry" group + contextual tab → `ribbon-bar.md §3.8`.
- Snapping engine → `snapping-engine.md`.
- Units / dimension parsing → `units-and-formatting.md`.

## Deferred / follow-ups
- Vertical / elevation-plane anchoring; elevation-view projection; 3D extrude of
  filled 2D profiles; hatch scale control; per-category 2D-geometry line-weight.
- Parametric-polygon polish (explode → editable polyline; "Sides" as a HUD COUNT
  field); Line+Polyline single ←/→ cycle tool (retire the `K` placeholder).
- Module rename `construction_geometry.py → geometry_2d.py`.
