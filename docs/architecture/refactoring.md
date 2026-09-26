# Refactoring Candidates

Opportunities identified during the documentation effort, with their current
status. This page is orientation only: where a candidate has a governing spec
or an open task, that is the home of its plan — this page links, it does not
restate. (Per the docs leash, no line/LOC counts are cited here; they rot.)

## Model_Space Decomposition — in progress

**Problem:** `model_space.py` concentrates scene state, selection, undo/redo,
snapping coordination, entity creation and mode-driven tool dispatch in one
class, and it keeps growing.

**Status:** under way as incremental, behavior-preserving slices that lift
concerns into composed domain controllers (geometry tools, pipe network,
sprinkler workflow, placement input, 2D-geometry drawing, wall/feature
placement, modify tools, text editing, underlays). The contract, the slice
history and the remaining concerns are owned by
[`model-space-architecture.md`](../specs/model-space-architecture.md); the next
slices are the open "Model_Space decomposition" task in `todo_open.md`.

## MainWindow (`main.py`) Decomposition — open

**Problem:** `main.py` (the `MainWindow`) has grown alongside `Model_Space` —
ribbon construction, dock wiring, canvas tabs and per-surface glue all live in
one module.

**Status:** filed as its own sibling task with its own spec-to-be ("`main.py`
(MainWindow) decomposition" in `todo_open.md`). Chrome layout is already
governed by [`mainwindow-chrome-revamp.md`](../specs/mainwindow-chrome-revamp.md).

## display_manager.py: UI and Logic Tangled — open

**Problem:** `display_manager.py` mixes three concerns: (1) SVG recolouring
utilities, (2) category definition data and settings read/write helpers, and
(3) a large QDialog subclass for the display manager UI.

**Why it matters:** The SVG recolouring functions (`_recolor_svg_bytes`,
`_set_svg_tint`) are used by entities at paint time but live in the dialog
module. The category data (`_CATEGORIES`, `_CATEGORY_MAP`) is configuration but
is embedded alongside widget code.

**Rough approach:**

- Extract SVG recolouring to its own module (e.g. `svg_tint.py`)
- Extract category definitions and settings helpers (e.g. `display_settings.py`)
- Keep the QDialog in `display_manager.py` with only UI code

**Risk:** Low. The functions are already standalone; they just need to be moved and imports updated.

## Undo System: Scene Snapshots — open

**Problem:** Model-space undo stores a snapshot of the scene's model content
(`_capture_network()`; underlays and scale excluded) on every undoable action,
up to `UNDO_MAX` entries. Paper space already uses Qt's `QUndoStack` with
per-action commands (`paper_commands.py`), so the app runs two undo models.

**Why it matters:** For large projects each snapshot can be substantial, and
restore cost grows with drawing size. The snapshot path is also the second of
the two serialization paths that must stay in parity (invariant owned by
[`scene-io.md`](../specs/scene-io.md)).

**Rough approach:**

- Move to command-based undo (`QUndoStack`, as paper space does), each action recording its inverse
- Fall back to snapshot-based undo only for complex multi-entity operations

**Risk:** High. The snapshot approach is simple and correct. A command-based
system requires every editing operation to define its own undo logic, which is
error-prone across the many tool modes.

## Fitting Class: Not a QGraphicsItem — open

**Problem:** `Fitting` is not a QGraphicsItem subclass. It manages an optional `_TintedSvg` child item on the parent Node but does not inherit from `DisplayableItemMixin`. Instead, it manually duplicates display attributes (`_display_overrides`, `_display_color`, `_display_fill_color`, `_display_opacity`, `_display_visible`).

**Why it matters:** The Fitting class is an outlier -- every other visual entity inherits `DisplayableItemMixin`. The duplicated attributes must be kept in sync manually, and the Display Manager has special-case code for fittings.

**Rough approach:**

- Make Fitting extend DisplayableItemMixin (as a mixin, not a QGraphicsItem)
- Or refactor Fitting to be a proper QGraphicsSvgItem subclass like Sprinkler

**Risk:** Medium. Fitting's non-standard architecture (a plain Python class managing a child SVG item) exists because a Node always has exactly one Fitting, and the Fitting's visual is optional (the "no fitting" type has no SVG). Changing this requires careful handling of the fitting lifecycle.

## Wall Segment Complexity — open

**Problem:** `wall.py` holds a single large entity class. WallSegment handles 2D rendering (double-line, fill modes, section hatching), 3D mesh generation, joinery, opening management, thickness calculations with scale-dependent display, and multiple alignment modes.

**Why it matters:** Adding a new wall feature (e.g., curved walls, multi-layer walls — both open tasks) requires understanding the entire class.

**Rough approach:**

- Extract 3D mesh generation to a helper module (used by walls, floors, and roofs)
- Extract fill/hatch rendering to a shared painter utility (partially done in `displayable_item.py` with `draw_section_hatch`)
- Keep WallSegment focused on geometry and property management

**Risk:** Low for mesh extraction (already a standalone method). Medium for paint refactoring due to the interaction between fill mode, section-cut state, and display overrides.

## Other large single-module entities — to assess

`design_area.py` (design areas + their badge) and `gridline.py` (gridline item,
bubbles and lock indicator) have each grown past the size where a refactor
audit is warranted. Neither has a decomposition plan yet; assess on next touch
against their governing specs
([`sprinkler-system-components.md`](../specs/sprinkler-system-components.md),
[`grid-system.md`](../specs/grid-system.md)).

## Constants Consolidation — open

**Problem:** Some constants are defined in `constants.py`, but others are scattered across individual modules. For example, `THICKNESS_PRESETS_IN`, `DEFAULT_THICKNESS_MM`, and alignment modes are in `wall.py`; NFPA ceiling types and compartment types are in `room.py`; pipe schedule data is in `pipe.py`.

**Why it matters:** A developer looking for "what are the valid wall thicknesses" must know to look in `wall.py`, not `constants.py`.

**Rough approach:**

- Move NFPA-related constants (ceiling types, compartment types) to `constants.py`
- Keep entity-specific data (pipe schedules, fitting symbols) with the entity class, but document the split in a comment at the top of `constants.py`

**Risk:** Low. Purely a reorganization with import updates.
