# Refactoring Candidates

Opportunities identified during the documentation effort.

## Model_Space Decomposition

**Problem:** `model_space.py` is 7,195 lines with 196 methods covering scene state, selection, undo/redo, snapping coordination, entity creation, and tool dispatching.

**Why it matters:** New contributors must read thousands of lines to understand any single concern. The `__init__` method alone is 240+ lines of state initialization spanning 20+ separate tool subsystems.

**Rough approach:**

- Extract selection logic into a `SelectionManager`
- Extract undo/redo into an `UndoManager` (currently inline with full-scene JSON snapshots)
- Extract entity factory methods into a `SceneBuilder`
- Extract the mode state machine into a `ToolDispatcher` that routes mouse/keyboard events by mode string
- Keep Model_Space as thin orchestrator

**Risk:** Deep coupling with SceneToolsMixin and SceneIOMixin mixins. Both mixins reference `self` attributes (walls, rooms, floors, undo stack, snap engine, etc.) freely, so extracting managers requires defining clear interfaces.

## display_manager.py: UI and Logic Tangled

**Problem:** `display_manager.py` is 2,071 lines mixing three concerns: (1) SVG recolouring utilities, (2) category definition data and settings read/write helpers, and (3) a large QDialog subclass for the display manager UI.

**Why it matters:** The SVG recolouring functions (`_recolor_svg_bytes`, `_set_svg_tint`) are used by entities at paint time but live in the dialog module. The category data (`_CATEGORIES`, `_CATEGORY_MAP`) is configuration but is embedded alongside widget code.

**Rough approach:**

- Extract SVG recolouring to `svg_tint.py`
- Extract category definitions and settings helpers to `display_settings.py`
- Keep the QDialog in `display_manager.py` with only UI code

**Risk:** Low. The functions are already standalone; they just need to be moved and imports updated.

## Undo System: Full-Scene Snapshots

**Problem:** The undo system serializes the *entire scene* to a JSON dict on every undoable action (`push_undo_state()`). With a max stack depth of 50, this means up to 50 full copies of the scene state in memory.

**Why it matters:** For large projects with many walls, pipes, and underlays, each snapshot can be substantial. The serialize-everything approach also means undo/redo is slow on complex drawings.

**Rough approach:**

- Move to a command-based undo system where each action records its inverse operation
- Fall back to snapshot-based undo only for complex multi-entity operations
- Consider using `QUndoStack` from Qt's undo framework

**Risk:** High. The current approach is simple and correct. A command-based system requires every editing operation to define its own undo logic, which is error-prone for the many tool modes in SceneToolsMixin.

## Fitting Class: Not a QGraphicsItem

**Problem:** `Fitting` (429 lines) is not a QGraphicsItem subclass. It manages an optional `_TintedSvg` child item on the parent Node but does not inherit from `DisplayableItemMixin`. Instead, it manually duplicates display attributes (`_display_overrides`, `_display_color`, `_display_fill_color`, `_display_opacity`, `_display_visible`).

**Why it matters:** The Fitting class is an outlier -- every other visual entity inherits `DisplayableItemMixin`. The duplicated attributes must be kept in sync manually, and the Display Manager has special-case code for fittings.

**Rough approach:**

- Make Fitting extend DisplayableItemMixin (as a mixin, not a QGraphicsItem)
- Or refactor Fitting to be a proper QGraphicsSvgItem subclass like Sprinkler

**Risk:** Medium. Fitting's non-standard architecture (a plain Python class managing a child SVG item) exists because a Node always has exactly one Fitting, and the Fitting's visual is optional (the "no fitting" type has no SVG). Changing this requires careful handling of the fitting lifecycle.

## Wall Segment Complexity

**Problem:** `wall.py` is 1,028 lines for a single entity class. WallSegment handles 2D rendering (double-line, fill modes, section hatching), 3D mesh generation, opening management, thickness calculations with scale-dependent display, and multiple alignment modes.

**Why it matters:** Adding a new wall feature (e.g., curved walls, multi-layer walls) requires understanding the entire 1,028-line class.

**Rough approach:**

- Extract 3D mesh generation to a helper module (used by walls, floors, and roofs)
- Extract fill/hatch rendering to a shared painter utility (partially done in `displayable_item.py` with `draw_section_hatch`)
- Keep WallSegment focused on geometry and property management

**Risk:** Low for mesh extraction (already a standalone method). Medium for paint refactoring due to the interaction between fill mode, section-cut state, and display overrides.

## Constants Consolidation

**Problem:** Some constants are defined in `constants.py`, but others are scattered across individual modules. For example, `THICKNESS_PRESETS_IN`, `DEFAULT_THICKNESS_MM`, and alignment modes are in `wall.py`; NFPA ceiling types and compartment types are in `room.py`; pipe schedule data is in `pipe.py`.

**Why it matters:** A developer looking for "what are the valid wall thicknesses" must know to look in `wall.py`, not `constants.py`.

**Rough approach:**

- Move NFPA-related constants (ceiling types, compartment types) to `constants.py`
- Keep entity-specific data (pipe schedules, fitting symbols) with the entity class, but document the split in a comment at the top of `constants.py`

**Risk:** Low. Purely a reorganization with import updates.
