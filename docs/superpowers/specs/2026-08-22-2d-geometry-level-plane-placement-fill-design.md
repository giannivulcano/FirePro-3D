---
status: built              # shipped on feat/geo2d-level-fill (2026-08-22); folded into governing specs (view-relationships §3.3/§7.3, ribbon-bar §3.8)
last-verified: 2026-08-22  # built + full suite (3049) green at commit ce37220
verified-commit: ce37220   # branch HEAD after implementation
applies-to:
  - firepro3d/construction_geometry.py
  - firepro3d/annotations.py
  - firepro3d/displayable_item.py
  - firepro3d/level_manager.py
  - firepro3d/property_manager.py
  - firepro3d/scene_io.py
  - firepro3d/model_space.py
  - firepro3d/scene_tools.py
  - firepro3d/snap_engine.py
  - firepro3d/paper_display.py
  - firepro3d/ribbon_bar.py
  - main.py
  - firepro3d/constants.py
source-tasks:
  - 'TODO.md "2D geometry: first-class level-plane placement + fill (foundation for 3D extrude)"'
governing-specs-to-fold-into:
  - docs/specs/view-relationships.md   # §3.3 world-Z table rows; §7.3 Z-category
  - docs/specs/property-panel.md         # Geometry2D placement + fill rows
  - docs/specs/ribbon-bar.md             # geo2d contextual groups
---

# 2D Geometry: First-Class Level-Plane Placement + Fill — Design Spec

## Goal

Make 2D draw geometry (line, polyline, rectangle, circle, arc) a **first-class,
3D-anchored, fillable** entity:

- **Placement (Phase A):** every 2D item lives at a real world-Z (`level.elevation +
  offset`), participates in view-range visibility like other model geometry, and — at
  the same elevation — **draws on top of** building geometry (slabs/rooms/walls/pipes/
  nodes) so reference/profile geometry is never buried.
- **Fill (Phase B):** a closed 2D shape (rect, circle, closed polyline) can carry a
  **fill** (none / solid / hatch-pattern + colour) rendered in the item's own `paint()`,
  replacing the standalone `HatchItem`.

This is the data-model **foundation for future 3D extrude**: a 2D profile with a known
level + offset is the input an extrude operation will lift into a solid.

## Motivation

Today the 5 draw-geometry classes each duplicate a `level` attribute + panel row +
serialization, sit at a **static** render-Z (`Z_CONSTRUCTION = 1`) with **no
`z_range_mm()`**, so they have no true elevation, don't obey view range, and there is no
principled reason they draw where they do. Hatch fill is a separate `HatchItem` spawned
*from* a shape — a tracking item that duplicates the shape's boundary and drifts on
rotation (filed rotated-rect bug). `ConstructionLine` is an unused infinite reference
line with its own snap/paint special cases and a latent zero-length bug.

Giving 2D geometry a real world-Z + folding fill into the shape itself unifies it with
how every other geometry type already works (`DisplayableItemMixin`, elevation-based
Z-ordering, the Display Manager, `make_hatch_brush`), removes two vestigial subsystems,
and unblocks 3D extrude.

## Architecture & Constraints

**Reuse-maximal (Approach A).** The 5 classes adopt the existing
`DisplayableItemMixin` (level, stroke/fill colour, display overrides, Display-Manager
category) and gain a thin new `Geometry2DMixin` for the 2D-geometry-specific pieces
(offset, `z_range_mm`, fill fields, shared property/serialization fragments). MRO:

```python
class RectangleItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsRectItem): ...
```

Constraints honored:
- **No new render path.** Fill reuses `make_hatch_brush`/`draw_svg_hatch` (the vocabulary
  walls/slabs use); Z/visibility reuses `level_manager.apply_to_scene`.
- **`FloorSlab` is the offset template** — identical `_level_offset_mm` semantics
  (default 0, +up, serialize-when-nonzero, `z_range_mm` reads `scene._level_manager`).
- **Dual serialization** — every persisted field lands in *both* `scene_io.py` and
  `model_space._capture_network`/`_restore_network` in the same change.
- **Two context menus** — right-click fill wired into both `Model_View` menu paths.
- **`shape()`/`contains()` culling** — widening `shape()` for interior click must not
  shrink paint coverage; `boundingRect` already spans the closed path.
- **No `scene.clear()` in event frames**; `DimensionEdit` for the offset field; property
  panel over dialogs; house selection-grip style — all pre-existing conventions kept.

## Design Decisions

### D1 — Shared behavior: `DisplayableItemMixin` + `Geometry2DMixin` (chosen)
Considered: (B) standalone mixin re-implementing fill; (C) minimal per-class edits.
Chosen A: the 5 classes join `DisplayableItemMixin` (reuses fill renderer + Display
Manager; **resolves the filed "Model-side Construction Display-Manager category"
follow-up**) and a new `Geometry2DMixin` holds offset/`z_range_mm`/fill + shared
`_geom2d_properties`/`_geom2d_set`/`_geom2d_to_dict`/`_geom2d_from_dict` fragments that
collapse the per-class duplication. Rationale: max reuse, matches walls/slabs, one home
for the new fields.

### D2 — World-Z & ordering
`z_range_mm()` returns zero-thickness `(E, E)`, `E = level.elevation + _level_offset_mm`.
New `Z_CAT_CONSTRUCTION` in `constants.py` just above `Z_CAT_NODE`; the class names join
`_Z_CATEGORY` and the construction lists join the `_apply_elev_z` pass in
`level_manager.apply_to_scene`. Elevation-based Z (`elev × Z_ELEV_SCALE +
Z_CAT_CONSTRUCTION`) → wins over building geometry at equal elevation, correct
cross-level ordering, still below the static annotation/symbol/design bands (sprinkler
100, overlay 200, bubbles 500, etc.). Dead `Z_CONSTRUCTION` removed.

### D3 — Visibility
View-range participation turns on automatically once `z_range_mm()` exists
(`_apply_z_filter`/`_z_intersects` stop bailing). Default offset 0 keeps every existing
drawing visible on its home level and off adjacent levels (Level-1 default range
`[-1000, +2896]` contains elevation 0; Level-2 range does not).

### D4 — Fill rendering & hit-testing
New `draw_fill(painter, closed_path, scene, fill_type, pattern, colour, alpha)` in
`displayable_item.py`, sharing brush internals with `draw_section_hatch`. Each class's
existing `paint()` draws the fill first (when `fill_type != "none"` and `is_closed()`),
then the outline; fill is in item-local coords → rotates with the shape (fixes the filed
rotated-rect hatch bug). **Solid** = semi-transparent (~45% alpha default) so on-top
fills don't occlude; **hatch** via the shared pattern path. Each class's existing
`shape()`: when filled, return `get_closed_path()` united with the stroked outline
(interior selectable); else outline-only.

> **Visual bind rule:** the exact default solid alpha and the curated pattern list get a
> throwaway rendered mockup at implementation before binding (house rule: visual
> decisions bind on a rendered pick).

### D5 — Retire `ConstructionLine`
Full removal: class, `scene._construction_lines`, tool/mode + placeholder `K` shortcut,
snap participation, paper/elevation/3D/level handling, `_family_key_for` branch,
`model_space` type map. Load: **silently skip** legacy `construction_line` entries
(tolerant, one-line log). Resolves the filed zero-length typed-input bug (path removed).

### D6 — Retire `HatchItem`, migrate to fills
Full removal from `annotations.py`; `scene._hatch_items` and all handling dropped;
`scene_tools` "spawn HatchItem" replaced by the fill-on-shape flow. **File-load
migration only** (undo snapshots are session-only): each `"hatch"` entry →
`_rebuild_path_from_elements` → closed `PolylineItem` (`toFillPolygon`) carrying level +
fill (`solid`→Solid; `diagonal`/`cross`→nearest `PATTERN_NAMES`) + colour. Minor
curve→segment tessellation accepted (source type not recorded).

### D7 — Surfaces
`geo2d` contextual tab gets a controller (à la `FontGroupController`) building a
**Placement group** (reusable `_build_placement_group` helper — other families adopt
later) + **Fill group** (enabled iff a closed shape is selected; no empty macros) +
universal Edit group. Right-click **Fill ▸ None/Solid/Hatch▸patterns** in both
`Model_View` menu paths. Panel rows come free from `Geometry2DMixin`. All writes route
through the existing undo-routed `set_property` path; multi-select = one macro.

### D8 — Defaults
`GeometryTemplate` gains `offset` (default 0); new items inherit active level (already)
+ session offset. Cross-session template persistence stays the separate filed D0 task.

## Acceptance Criteria

- [ ] Line/polyline/rect/circle/arc carry `level` + Level Offset (default 0, +up);
      panel shows Level, Level Offset, read-only computed Elevation.
- [ ] `z_range_mm()` == `(E, E)`, `E = level.elevation + offset`; `None` when no level
      manager / dangling level (graceful).
- [ ] At equal elevation, a 2D item's `zValue()` > wall/room/node and < sprinkler/
      overlay/label (ground-truth ordering, not constant equality).
- [ ] Visible on home level at offset 0; hidden when offset pushes it outside the active
      view range; appears on an adjacent level whose range includes it.
- [ ] Closed shapes fill (none/solid/hatch + colour) via panel, ribbon Fill group, and
      right-click (both menu paths); rotated rect fills correctly; open shapes offer no
      fill.
- [ ] Filled shapes interior-clickable; unfilled outline-click only.
- [ ] Fills plot on sheets (solid + hatch, BW-aware) through paper viewports with correct
      view-range isolation.
- [ ] `ConstructionLine` fully removed; legacy `construction_line` entries load clean and
      are dropped; `K` shortcut gone.
- [ ] `HatchItem` fully removed; legacy `hatch` entries migrate to filled closed
      polylines (pattern/colour/level preserved).
- [ ] New 2D geometry inherits active level + session template offset.
- [ ] Placement + fill round-trip through **both** serialization paths (scene_io + undo).
- [ ] Construction geometry appears as a "2D Geometry" Display-Manager category.

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] Behavioral tests, red-verified before green; drive real entry points (panel/ribbon/
      right-click/`apply_to_scene`), not raw attribute sets or slots.
- [ ] Full suite green (chunked if the OneDrive-venv 127 flake appears).
- [ ] No regression: existing drawings render identically on their home level (offset 0).
- [ ] No `scene.clear()` in event frames; no shape()-culling regression; dual paths
      updated together.
- [ ] Deferred items (vertical-plane anchoring, elevation projection, 3D/extrude) not
      started; named in the doc.

## Existing Code Context

- `construction_geometry.py` — 5 classes (post-`ConstructionLine`), each overriding
  `paint`/`shape`/`is_closed`/`get_closed_path`; `GeometryTemplate` seeds new items.
- `displayable_item.py` — `DisplayableItemMixin.init_displayable()`, `draw_section_hatch`
  (solid + hatch via `make_hatch_brush`/`draw_svg_hatch`, IntersectClip, paper-aware).
- `floor_slab.py` — offset template (`_level_offset_mm`, `z_range_mm`, panel row,
  serialize-when-nonzero).
- `level_manager.apply_to_scene` — `_set_level_vis` (visibility, already iterates
  construction lists), `_apply_elev_z` + `_Z_CATEGORY` (construction not yet in it),
  `_apply_z_filter`/`_z_intersects` (use `z_range_mm`).
- `hatch_patterns.py` — `make_hatch_brush`, `PATTERN_NAMES`, `is_builtin/is_svg/
  draw_svg_hatch`.
- `annotations.py:430` — `HatchItem` (copy of boundary path, `_rebuild_path_from_elements`,
  patterns diagonal/cross/solid).
- `main.py` — `_contextual_registry`, `_family_key_for` (`"geo2d"`),
  `_build_contextual_edit_group`, `_on_selection_changed_contextual`; `font_group.py`
  `FontGroupController` is the controller pattern to mirror.
- Dual serialization: `scene_io.py` + `model_space._capture_network`/`_restore_network`.

## Edge Cases & Error Handling

- Dangling/deleted level → `z_range_mm` `None` → item keeps current visibility, z falls
  back to base offset (no crash); rename already remaps via `LevelManager.rename_level`.
- Scene without `_level_manager` (import-preview) → `z_range_mm` `None` → legacy behavior.
- Multi-select mixed level/offset/fill → panel blanks differing values; one edit = one
  undo macro.
- Template panel (draw mode, nothing selected) → read-only Elevation shown as "—".
- Migration of a hatch whose boundary had curves → tessellated closed polyline (accepted).

## Deferred (named, out of scope)

Vertical/"elevation plane" (section-based) anchoring; elevation-view projection of 2D
geometry; 3D rendering / extrude (this spec is its foundation). Cross-session geometry
template persistence (filed D0). Hatch scale/density knobs (dropped legacy angle/spacing;
revisit as polish).
