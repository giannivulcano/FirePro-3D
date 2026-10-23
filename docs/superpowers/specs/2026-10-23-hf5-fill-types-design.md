---
status: draft             # approved in Phase 3 (2026-10-23); not built
last-verified: 2026-10-23
verified-commit: 969aca3b
applies-to:
  - firepro3d/fill_types.py
  - firepro3d/filled_region.py
  - firepro3d/display_manager.py
  - firepro3d/block_library.py
  - firepro3d/block_registry.py
  - firepro3d/scene_io.py
  - firepro3d/settings/template.py
source-tasks: [HF5 (todo_open.md, Hatch & Fill build)]
---

# HF5 -- Fill Types -- Design

Governing what: `docs/specs/hatch-and-fill.md` D-A14 (named project types), D-A15 (bundling,
project wins, "used by N"), D-A17 (Display Manager section cut picks a type), D-A36 (never
vanish). Concept: `2026-10-01-hatch-and-fill-concept-design.md` HD5, guards G6 / G7.

## Goal

One named, project-scoped vocabulary of fill styles ("Fill Types") used by Filled Regions and by
the Display Manager section cut, edited in one place, restyling every user live.

## Motivation

Today every region and every Display Manager category carries its own copy of colour + pattern +
scale. Changing "the concrete look" means editing each one, the section cut uses a different
vocabulary (colour + pattern + scale cell, `SectionPatternDialog`) from regions (two-layer
`FillLayers`), and library blocks cannot carry a look with them.

## Ratified rulings (Phase 2, FP1 -- do not re-ask)

- **R1 Scope:** Filled Regions + Display Manager section cuts use Fill Types. Closed 2D shapes keep
  the UP1 direct two-layer fill.
- **R2 Legacy regions:** open as "(Custom)" -- own fill kept, identical look, no type.
- **R3 Overrides:** any field (background colour / opacity, pattern colour / opacity / scale) per
  region; the panel marks overridden fields with "Reset to type".
- **R4 Display Manager legacy:** each category's current section colour / pattern / scale becomes a
  project type ("Wall Section", "Floor Section"); cuts look identical. Per-item section overrides
  convert the same way (one type per distinct look, named "<Category> Section 2", ...).
- **R5 Manager:** a "Fill Types" tab in the Display Manager beside Line Weights.
- **R6 Seed set:** created in code when a project's table is empty: Solid Black, Solid Grey 20 %
  (the missing-type fallback), and the converted category section types. HF8 later replaces it
  with the template set.
- **R7 App-wide section default:** QSettings stores the type's name + look; on open the project type
  with that name is used, else the type is added from the stored look (project wins).

## Architecture & Constraints

**Approach A (ratified): resolve at paint time from one project table.**

- New `firepro3d/fill_types.py`:
  - `FillType(id: str, name: str, layers: FillLayers)` (frozen) -- the look reuses
    `fill_layers.FillLayers` unchanged.
  - `FillTypeTable` held by the model (`Model_Space.fill_types`): by-id and by-name lookup,
    add / rename / replace / remove, `to_payload()` / `from_payload()`, `seed()`.
  - `resolve(type_id, overrides_record, table) -> (FillLayers, missing: bool)`: type layers, then
    the region's sparse overrides on top; unknown id -> Solid Grey 20 % + `missing=True`.
  - `users_of_type(scene, type_id)` and the shared counter used by both delete guards.
- Record I/O stays in `fill_layers.from_record` / `to_record` (the only fill parser); the type
  payload uses the same field names: `{"id", "name", "background"?: {"color","opacity"},
  "pattern"?: {"ref","color","opacity","scale"}}`.
- Types-table edits are **outside undo** (as every Display Manager setting -- an undo restore keeps
  the current project values). Region type / override edits are ordinary undoable item edits.
- No literal colours in new UI; the tab is built from `ui_kit` (Section, ToggleSwitch, FillSwatch,
  Stepper, Selector) under the app theme per `docs/specs/ui-design-system.md`.

## Design Decisions

### §1 Data and resolution

- Project payload: new top-level key `"fill_types"` (list). Additive and read with a default, so
  **no `SAVE_VERSION` bump**. A file without the key gets the seed set (R6) plus the R4
  conversion on open.
- Region record: `fill_type` (type id) beside `fill`. With a type, `fill` holds **only overridden
  fields** (sparse, same keys). With no type ("(Custom)"), `fill` is the full fill exactly as today
  (R2), so pre-HF5 regions are untouched.
- Paint: `FilledRegionItem` resolves `type -> overrides -> paint_fill` each paint. Missing type draws
  Solid Grey 20 % and the panel shows "?".
- Region panel: Fill Type selector ("(Custom)" + project types); overridden fields marked, each with
  "Reset to type" (R3). Picking a type clears the overrides; picking "(Custom)" copies the resolved
  look into `fill`.

### §2 Display Manager

- The Section cell (category row and per-item override) becomes a Fill Type selector;
  `SectionPatternDialog` is retired.
- Walls, floor slabs and section views draw the cut by resolving the type and calling the existing
  renderer: the type background is the cut body fill, its pattern colour replaces today's fixed
  `_SECTION_HATCH_COLOR`.
- Legacy conversion (R4): colour -> background (opacity 1), pattern + scale + today's fixed hatch
  colour -> pattern. Look identical.
- App-wide default (R7): QSettings stores name + look; matched by name on open, else added.
- Roof row loses its section cell (`roof.py` never draws a section; roof section cut is a separate
  filed task).
- Fill Types tab (layout B, mock `.superpowers/brainstorm/637-1792789701/content/fill-types-tab-b2.html`):
  type list with swatches on the left; editor on the right -- Name; Background (on/off, colour,
  opacity); Pattern (on/off, pattern, colour, scale, opacity); live preview; "Used by"; Add /
  Duplicate / Delete (refused when used, tooltip "Used by N"). **Look = house style, not the mock's
  colours** (user ruling); changes apply on OK.

### §3 Library bundling (D-A15, G7)

- `save_to_library` writes `fill_types`: every type used by a region anywhere in the block's closure
  (nested blocks included); `.fpdb` schema 3. `block_registry.prim_refs` follows a region's type to
  its pattern ref so the pattern block bundles too.
- Load: types merge **by name, project wins** -- a name hit re-points the loaded regions to the
  project type (project look used); a new name is added (fresh id when its id is taken). Region
  `fill_type` ids in the loaded definitions are remapped before the definitions register. Pattern
  blocks keep today's rule (by id, project copy wins).
- A type whose pattern block cannot resolve draws the tone (D-A36).

### §4 Restyle and delete guard

- OK after a type edit: repaint every scene; invalidate + recompile block definitions whose regions
  use the type; redraw wall / floor cuts and section views.
- One counter over: regions in every scene, region primitives in block definitions, Display Manager
  category + per-item section types, and Fill Types (for pattern refs). Type delete is refused while
  used ("Used by N", naming the users); pattern-block delete uses the same counter (closes the gap
  that a pattern used only by a loose region or a section setting can be deleted today).

## Existing Code Context (1b reuse sweep)

- REUSE AS-IS: `fill_layers` (records), `hatch_render.paint_fill`, `hatch_patterns.tile_choices`,
  `colour_picker.pick_fill`, `ui_kit.FillSwatch`, `BlockRegistry` (`prim_refs`, `bundle_for`,
  `users_of`), `ensure_project_patterns` (called from `main.py` on startup / new / open and the
  Display Manager OK), line-weight table as the named-table analog (`paper_display`).
- GENERALIZE: delete guard counter (today block->block only); section cut inputs
  (`draw_section_hatch` callers in `wall.py`, `floor_slab.py`, `section_scene.py`); template
  (`settings/template.py` `_blank_template_payload` / `save_current_as_default` carry only scale /
  project info / title block).
- GAP: `fill_types.py`, region `fill_type`, the tab, the section selector, `.fpdb` `fill_types`.

## Edge Cases & Error Handling

- Two loaded types with the same name in one file: first wins, the second's regions re-point to it.
- Renaming a type to an existing name: refused in the tab.
- Deleting the fallback "Solid Grey 20 %": allowed when unused; the fallback look is a code constant,
  not the table row.
- Region with `fill_type` and an empty `fill`: pure type look.
- Pattern off in the type but a pattern override on the region: override wins (field-level merge).
- Per-item `_display_overrides` are not serialized for walls (open bug, todo_open.md); HF5 converts
  what is present and does not fix that bug.

## Acceptance Criteria

- AC1 Fill Types table persists across save / open; table edits stay out of undo.
- AC2 A region picks a type; restyling the type updates it live (G6).
- AC3 Per-field overrides with marks and "Reset to type"; "(Custom)" copies the resolved look.
- AC4 A pre-HF5 project opens with regions and section cuts pixel-identical.
- AC5 The Display Manager section cell (category + per-item) is a Fill Type selector; walls, floors
  and section views draw via the type; restyle updates cut walls (G6); Roof section cell gone;
  `SectionPatternDialog` retired.
- AC6 App-wide section default matched by name, else added.
- AC7 `.fpdb` bundles types + pattern blocks; load merges by name, project wins, ids remapped (G7).
- AC8 Deleting a used type or pattern block is refused with "Used by N".
- AC9 Missing type -> Solid Grey 20 % + "?".
- AC10 New / empty project gets the seed set.
- AC11 Fill Types tab, layout B, house style (smoke-gated).

## Verification Checklist (VC3 guards, each shown RED with the change reverted)

- G6: restyle a type in a shown view; pixel-sample a region and a cut wall -- both change.
- G7: block with a typed region -> library -> fresh project: type + pattern arrive; into a project
  with a same-named, different-look type: project look wins.
- Legacy open: pre-HF5 project (custom region + custom DM sections) renders digest-identical.
- Delete refusal through the real tab action and the Block Manager action.
- Missing-type fallback colour + "?" in the panel.
- Round-trip: save -> open -> undo keeps `fill_type` + overrides.
- Smoke: the tab against the house style (deviation = defect).

## Cross-spec reconciliation (Account)

- `hatch-and-fill.md`: D-A14 / D-A15 / D-A17 "HF5 build design" pointer; H10 (dead Roof column) closed.
- `block-system.md`: Fill Type bundling (D-A15) pointer; `.fpdb` schema 3.
- `scene-io.md`: `fill_types` payload key.
- `docs/architecture/display-system.md`: section cut -> Fill Type link.
