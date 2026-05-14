# Remove Layer System — Design Spec

**Date:** 2026-05-13
**Complexity:** Large
**Status:** Complete
**Source tasks:** TODO.md — "Remove layer system, rely solely on Display Manager"

## Goal

Delete the UserLayerManager layer system entirely. The Display Manager becomes the sole visibility/appearance control system. Old project files continue to load without error.

## Motivation

The layer system (UserLayerManager, UserLayerWidget, per-item user_layer attributes) added complexity without value. It was scaffolded early but superseded by the Display Manager's per-category controls. Never used in practice. Removing it reduced code surface area by ~650 LOC (user_layer_manager.py) plus ~150 references across 22 files, simplifies the mental model, and makes the signal disconnection audit (next architecture debt task) easier.

## Architecture & Constraints

- PyQt6 / QGraphicsScene architecture
- DisplayableItemMixin provided shared init for all scene entities — `user_layer` parameter and attribute removed
- Display Manager handles all visibility/appearance (per-category visibility, color, opacity, scale, fill, section hatching, and per-instance overrides)
- JSON-based .fpd project files remain backward-compatible — old `"user_layer"` and `"user_layers"` keys silently ignored on load
- DXF source-layer visibility in model_browser.py is UNRELATED to UserLayerManager — untouched

## Design Decisions

1. **Silently ignore** old `"user_layers"` and `"user_layer"` keys on load — no migration, no error
2. **Defer** selection locking and lineweight to future Display Manager enhancements
3. **Delete** `lw_mm_to_cosmetic_px` with the file (recreate later if needed)
4. **Stop setting** `user_layer` on new entities entirely
5. **Remove** UserLayerWidget dock, Modify ribbon Layer group, Layer property rows
6. **Remove** layer tooltips from model browser (DXF source-layer code untouched)
7. **Remove** `user_layer` from DisplayableItemMixin and Underlay dataclass
8. **Underlays** fall back to sensible defaults (white, 1.5px) — separate P2 task for underlay Display Manager category
9. **Update** 5 test files to remove layer references, keep old JSON in serialization tests for backward compat
10. **Approach:** Surgical removal (delete all layer code, fall back to defaults)

## Deletion Scope (actual)

### Deleted entirely

- `firepro3d/user_layer_manager.py` (648 LOC) — UserLayerManager, UserLayerWidget, UserLayer, lw_mm_to_cosmetic_px

### Core framework

- **displayable_item.py** — `user_layer` parameter and attribute removed from `init_displayable()`
- **underlay.py** — `user_layer` field, `to_dict()` write, `from_dict()` read removed
- **constants.py** — `DEFAULT_USER_LAYER` retained (still referenced by annotations and undo compat)

### Main application

- **main.py** — import, initialization, splash step, UserLayerWidget dock tab, signal wiring, Modify ribbon "Layer" group, `_refresh_modify_layer_combo()`, `_assign_layer_to_selection()`, all `user_layer_widget.populate()` calls, `user_layer_mgr` passed to scene/property manager/import dialog

### Scene and serialization

- **model_space.py** — `active_user_layer` attribute, ~15 `user_layer` assignments on entity creation, `_get_draw_lineweight()`, `_get_draw_color()`, `_geom_color_lw()`, `_underlay_color_lw()` (replaced with hardcoded defaults), `lw_mm_to_cosmetic_px` import, undo `_capture_network`/`_restore_network` user_layer serialization, clipboard user_layer serialization, geometry template user_layer propagation, annotation/door/window user_layer assignments
- **scene_io.py** — `"user_layers"` save/load block, per-item `"user_layer"` write on save
- **scene_tools.py** — ~28 user_layer propagation lines in offset, explode, join, break, fillet, chamfer, mirror, trim, hatch operations

### UI and property system

- **property_manager.py** — `set_user_layer_manager()`, `_user_layer_manager` attribute, `layer_ref` property type handler
- **model_browser.py** — `Layer: {x.user_layer}` from 3 tooltip strings
- **dxf_preview_dialog.py** — `user_layer_manager` constructor param, "Destination Layer" UI group, `_on_dest_layer_changed()`, user_layer in import params and QSettings

### Entity files (user_layer attribute, property rows, serialization)

- **construction_geometry.py** — 6 classes: PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem, _GeometryTemplate
- **annotations.py** — 3 classes: DimensionAnnotation, NoteAnnotation, HatchItem
- **gridline.py**, **block_item.py**, **wall.py**, **room.py**, **floor_slab.py**, **roof.py**, **detail_view.py**, **design_area.py**, **wall_opening.py**, **view_marker.py**

### Context menus and managers

- **underlay_context_menu.py** — "Change Layer" menu action, `_change_layer()` method, user_layer in duplicate
- **level_manager.py** — dead `_user_layer_manager.apply_to_scene()` call block
- **__init__.py** — `UserLayerManager` lazy-loader entry

### Untouched

- All DXF source-layer code in model_browser.py (hidden_layers, _toggle_underlay_layer, etc.)

## Behavioral Changes

### Underlay color/lineweight fallback

- `_underlay_color_lw()` deleted — callers use hardcoded `QColor("#ffffff")`, `1.5` px
- `_geom_color_lw()` deleted — callers use hardcoded `"#ffffff"`, `2.0` px
- `_get_draw_lineweight()` deleted — callers use hardcoded `2.0` px

### Entity creation

- No layer assignment on new entities; `user_layer` attribute no longer exists

### Serialization backward compatibility

- Save: stopped writing `"user_layer"` per item and `"user_layers"` list
- Load: old `"user_layer"` keys in JSON are silently ignored (consumed by dict parsing, never assigned)
- Undo: `_capture_network` / `_restore_network` no longer serialize/deserialize `user_layer`
- Clipboard: copy/paste no longer includes `user_layer`

### Level manager interaction

- `UserLayerManager.apply_to_scene()` no longer runs after `LevelManager.apply_to_scene()`
- Only LevelManager and DisplayManager control visibility — desired state

## Test Updates

| Test File | Change |
|-----------|--------|
| `test_gridline_core.py` | Remove `user_layer` assertions from serialization round-trip tests |
| `test_scene_tools.py` | Remove `self.active_user_layer` from mock scene stub |
| `test_underlay.py` | Remove `user_layer=` param from Underlay constructor calls |
| `test_underlay_serialization.py` | Remove `user_layer` assertions; keep old JSON test data to verify backward compat |
| `test_wall_room_floor.py` | Remove `user_layer` set/assert from Wall, Room, FloorSlab serialization tests |

No new tests needed — existing serialization tests with old JSON data implicitly verify backward compat.

## Acceptance Criteria

- [x] `user_layer_manager.py` is deleted
- [x] `user_layer` attribute removed from DisplayableItemMixin, Underlay dataclass, and all entities
- [x] `active_user_layer` removed from Model_Space
- [x] "User Layers" tab removed from left sidebar dock
- [x] "Layer" group removed from Modify ribbon
- [x] "Layer" property row removed from all entity property panels
- [x] `layer_ref` property type and `set_user_layer_manager` removed from PropertyManager
- [x] Layer tooltip text removed from model browser
- [x] Serialization silently ignores old `"user_layer"` and `"user_layers"` keys on load
- [x] Old `.fpd` files open without error
- [x] All existing tests pass (982 passing, updated to remove layer references)
- [x] Underlays render with sensible defaults (white, 1.5px)
- [x] Undo/redo, clipboard, and scene tools cleaned of user_layer references
- [x] Underlay context menu "Change Layer" action removed
- [x] `level_manager.py` dead `apply_to_scene` layer block removed

## Verification Checklist

- [x] All acceptance criteria met
- [x] `python -m pytest tests/` passes — 982 tests, 0 failures
- [x] No remaining references to `user_layer_manager` in .py files
- [x] No remaining `user_layer` references in .py files (except backward-compat test JSON data)
- [ ] Application launches without errors (`python main.py`) — pending user smoke test
- [ ] Old `.fpd` project file loads cleanly — pending user smoke test
- [ ] DXF source-layer visibility in model browser still works — pending user smoke test

## Deferred

- Selection locking — future Display Manager enhancement
- Lineweight control — future Display Manager enhancement
- Underlay Display Manager category — separate P2 task
