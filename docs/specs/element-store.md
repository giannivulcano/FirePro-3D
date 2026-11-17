---
status: current           # built 2026-11-17 on todo/element-store-20261116 (base 68511b61)
last-verified: 2026-11-17
verified-commit: e34918a5
applies-to:
  - firepro3d/element_store.py
source-tasks:
  - "todo_closed.md - Element store (one row per element kind) [P1], rulings R1-R8 + Phase 3 rulings O1, O2 + build rulings B1-B3 (D5)"
---

# Element store - Design Spec

> **Consolidating contract.** This spec owns the element-kind table and the rule that whole-model
> passes iterate it. The specs it touches link here (Rule A) and do not restate it:
> `model-space-architecture.md` §3.3 (the new-entity checklist), `scene-io.md` §1 (dual serialization),
> `parametric-constraint-system.md` (participating lists), `schematics.md` (primitive lists).

## Goal

One module holds a row per element kind. Every whole-model pass reads that row instead of a hand-written
list of the scene's element lists: save, load, undo capture and restore, clear, remove, the level walk,
and the class-to-list maps. Adding a kind means adding one row. A row that is incomplete fails one
table-driven test.

## Motivation

"Which kinds exist and where they live" is written out by hand in about 25 places, and the copies have
drifted. `_items_on_level` misses block instances (Duplicate Level copies no blocks: reproduced at base).
Restore does not give roofs their scale manager. The five 2D lists disagree on texts, splines and filled
regions. `model-space-architecture.md` §3.3 records the cost as a checklist that every new entity must
walk by hand.

## Architecture & Constraints

- **Lists stay scene attributes (R1).** The store holds no state. `scene._walls` and the others stay
  where they are, so `model-space-architecture.md` §5.3 (state stays scene-side) holds unchanged, and the
  ~1,000 test references to the private list names keep working.
- **Module shape.** `firepro3d/element_store.py` follows `project_tables.py`: plain functions plus a
  `KINDS` tuple, with lazy imports inside functions so the module never joins the
  `model_space` import cycle.
- **Load and restore stay separate orchestrations (§6 holds).** They share each row's `build` step
  and keep their own order and display tail.
- **Byte gate (R6).** Every relocation commit leaves the save bytes and undo-snapshot bytes of an
  every-kind fixture identical to base. Save, load, save stays a fixed point. Drift fixes land
  afterwards as separate commits.

## Design Decisions

### D1 - The row (R1, R3, R7)

`ElementKind` is a frozen dataclass:

| Field | Meaning |
|---|---|
| `attr` | the scene list name (`"_walls"`) |
| `cls` | the item class, resolved lazily |
| `undo_key` | the record key in the undo snapshot (`"draw_rectangles"` for `_draw_rects`) |
| `file_key` | the `.fpd` key, or `None` for a kind that is never written to file. The ten loose 2D kinds are `None`: undo captures them, file save clean-drops them (containment C8, R3) |
| `legacy_keys` | extra keys read on restore and counted on the load clean-drop (`reference_lines` -> `_draw_lines`) |
| `record_type` | the clipboard record type (`"draw_line"`); `None` where paste uses its own branch |
| `level_of` | `None` for a level-less kind, else the item's level name (floors read `_top_level`) |
| `children` | `None`, or the item's owned children (wall openings, slab openings) (R7) |
| `category` | the Display Manager category key the kind belongs to |
| `constraint_roles` | a `frozenset` of `"primitive"` (schematic and Block Editor primitive), `"editor"` (Block Editor solver item) and `"plan"` (plan constraint item). A set, because block instances are both `"editor"` and `"plan"`, and splines and filled regions are primitives that never take constraints |
| `codec_owned` | `True` when `network_codec` writes and reads the records (design areas only) |
| `build(scene, record, ctx)` | creates the item from a record, attaches its children, adds it to the scene and appends it to the list; returns the item or `None` |

`ctx` is a small `BuildContext`: which path is building (`"load"` or `"restore"`) and the orphan-host
counter (load: blocks whose gridline host is gone). Path-specific steps read `ctx`. They are not separate
build functions. The restore-only block-definition `source_path` map is not on `ctx`: it stays a closure
in `_restore_network`.

### D2 - Order (Phase 3 ruling O1)

The table's row order is the undo-capture order. Undo bytes therefore follow from the table itself.
A pass whose order differs names its own tuple of row `attr`s in `element_store.py`, and the
completeness test (G4) checks that each tuple covers exactly the rows of its role:

- `PRIMITIVE_ORDER`: the schematic gather order (`schematic_scene`, which reaches block-definition
  primitive order) and `scene_tools._all_geometry_items` (lines first; the index order constraints use).
  The two were identical, so one tuple serves both.
- `CONSTRAINT_EDITOR_ORDER`: the Block Editor solver's item order (`constraint_controller._PARTICIPATING`);
  `CONSTRAINT_PRIMITIVE_ORDER` adds splines and filled regions.
- `CONSTRAINT_PLAN_ORDER`: the plan constraint item order (`_PLAN_PARTICIPATING`, and
  `constraint_controller.plan_ref_uids`, which keeps its hosted-block filter).

Keys that are not rows are named splices inside the pass functions, not tuples: capture and save put
`block_definitions` (a D3 registry) between the `rooms` and `blocks` rows (`before_blocks`), and save puts
`constraints` after the `walls` row (`after_walls`).

### D3 - Exceptions (named, not rows)

- **Design areas** are a row with `codec_owned=True`. Save, capture, load and restore leave their
  records to `network_codec` (as recorded). Clear, the level walk and the completeness test iterate the row.
- **Block definitions** are a registry dict (`_block_definitions`), not an element list. They stay
  inline in each pass.
- Nodes, pipes, sprinklers and water supply stay in `network_codec` and `sprinkler_system`.

### D4 - Passes

| Pass | Reads the table for |
|---|---|
| `_capture_network` | each non-codec row's `undo_key` -> `[i.to_dict() for i in list]` |
| `_restore_network` | removal per row exactly as before: walls detach the list first (store-internal `_DETACH_FIRST`; a wall's join pool is `_walls`, so this avoids a quadratic join rebuild), every other row removes children, then the item, then clears the list in place; then `build` per record, `legacy_keys` included |
| `save_to_file` | rows with a `file_key`, in row order with the D2 splices |
| `load_from_file` | `build` per file row; the clean-drop count sums the `file_key is None` rows' `undo_key`s plus `legacy_keys` |
| `_clear_scene` | removes the scene items of design areas and blocks only (store-internal `_CLEAR_REMOVES`), then rebinds every row's list (clear rebinds, restore clears in place) |
| `_remove_item_from_lists` / `_bulk_delete` | the class-to-row map; owner removal goes through `children` |
| `_items_on_level` / `leveled_items` | one walk over rows with `level_of` (D5) |
| `_GEOM_TYPE_REGISTRY`, `schematic_scene._CLS_TO_LIST` / `_PRIMITIVE_LISTS`, `constraint_controller._PARTICIPATING` / `_PRIMITIVE_LISTS` / `_PLAN_PARTICIPATING` / `plan_ref_uids`, Display Manager's 2D and Reference tuples | derived from `record_type`, `constraint_roles`, `category` and the D2 tuples |

`category` is set only where `display_manager._items_for_category_static` serves a key from whole lists:
`"2D Geometry"` on the nine loose 2D rows, and `Design Area`, `Grid Line`, `Wall`, `Floor`, `Roof`,
`Room`. Texts and blocks have `None`. The 2D and Reference results come back in row order (filled regions
before polygons).

Each path keeps these steps inline:

- gridline counter sync and duplicate warnings
- `_recalc_name_counters`
- design-area tiles
- `_refresh_view_head_copies`
- `canonicalise_records` (load)
- `blockDefinitionsChanged`
- every display tail

### D5 - The level walk (R5, Phase 3 ruling O2)

One generator yields `(row, item)` for every row with a `level_of`. `_items_on_level` filters it by
level name. `leveled_items` adds `children` and leaves out floors, whose level refs are re-pointed
elsewhere.

The 2D rows have no `level_of` (containment C3: 2D primitives are level-less). Dropping them from
`_items_on_level` is its own commit after the relocation. It shows no visible change in the plan scene,
where the lists are always empty.

Block instances get a `level_of` in the R5 commit. Duplicate Level then copies them and
Select Same Level selects them.

**Order.** Both walks return items in row order. Each kind's own list order is unchanged, but the order
across kinds moved from the old hand lists: design areas come first in both walks, floors follow walls in
`_items_on_level`, and blocks come last in `leveled_items`. Every caller is order-independent
(Duplicate Level pastes per kind).

**Build rulings (2026-11-17, user):**

- **B1 - block paste goes to the active level.** `_paste_block_record` retargets a pasted block to the
  active level, as walls, rooms and slabs already do. Without it, Duplicate Level stacked the block copies
  on the source level. The same path serves Ctrl+V, Duplicate, Array and Polar Array, so all four now
  place blocks on the active level. Open edge: a hosted block pasted onto another level, without its host,
  stays anchored to the host on the source level (filed).
- **B2 - Duplicate Level leaves view-owned Notes behind.** Every Note is a placed block, so R5 put Notes in
  the walk. A Note's copy would re-key to the current view (detail and section Notes went wrong), so
  `duplicate_level_entities` skips blocks with `note` set.
- **B3 - Duplicate Level leaves gridline-hosted blocks behind.** Gridlines are level-less and never
  copied, so the copy would keep the original gridline and absolute elevation and land on the original.
  `duplicate_level_entities` skips blocks with `host` set. Wall-hosted blocks (`_element_host`) are still
  copied.

B2 and B3 filter in `duplicate_level_entities` only. Select Same Level and `leveled_items` keep every block.

### D6 - Commit sequence

1. Characterization at base, green: G1, G2, G3.
2. Store module and rows, with G4 and G5.
3. Capture and restore. 4. Save, load and clear. 5. Removal. 6. The derived maps (the dead
   `block_editor` re-export of `_CLS_TO_LIST` is removed). 7. The level walk, outputs unchanged
   (a temporary flag keeps 2D in `_items_on_level`).
   Commits 3-7 are relocations, so G1 stays byte-identical across them.
8. R2: restore gives roofs `_scale_manager_ref` (G6, RED at base).
9. R5: block instances join the level walk (G7, RED at base). Logged as phase-drift (C2 absorb).
10. O2: the 2D rows leave the level walk. The temporary flag goes, and
    `test_geo2d_serialization.py::test_polygon_included_in_items_on_level` is rewritten to assert
    polygons are excluded.

### Out of scope

- the structure of `paste_items`, though the gridline heuristic may read `record_type` later
- the per-kind readers (`model_browser`, `view_3d`, `section_scene`, `marks`, `section_marker`,
  `project_backup`, `materials`)
- the removal caller protocol, the category ladders, the uid index
- the Project tables order (`scene-io.md` §3a)

## Acceptance Criteria

- [x] Every pass in D4 reads the table. No class-to-list map or element-list name tuple is left
      outside `element_store.py` except the D2 order tuples and the D3 exceptions.
- [x] Commits 3-7 leave G1 byte-identical to base.
- [x] Roofs have a scale manager after undo (R2).
- [x] Duplicate Level copies a placed block and Select Same Level selects it (R5), with B1-B3 (D5).
- [x] The loose 2D rows are outside the level walk (O2).
- [x] The 1b before-baseline (138 coupled test files, `.todo/es-baseline-files.txt`) passes unchanged, except the
      O2 rewrite. Its failures were VC7-proved to fail the same way at base `68511b61` (filed in `todo_open.md`).

## Verification Checklist

- [x] **G1.** An every-kind fixture's save bytes and undo-snapshot bytes match the base golden, with EOL,
      uuid and date normalised. Save, load, save is a fixed point. The first save is pinned, and the fixed point
      is save2 == save3, because the first capture of fresh items is not one (filed).
- [x] **G2.** Each kind survives an undo / redo round trip with the same record.
- [x] **G3.** `_clear_scene` leaves every row's list empty and the scene holds none of the items.
- [x] **G4.** Table-driven completeness. Every row survives save / load (if `file_key`), capture / restore,
      clear and remove, and appears in the level walk (if `level_of`). Every D2 order tuple covers
      exactly its role's rows. A row with a missing piece turns it RED.
- [x] **G5.** A scan guard fails on a new class-to-list map or element-list tuple outside the store. It
      sees only literal tuples, lists and dict values that name two or more row attrs. It is blind to
      comprehension, `extend` and ladder passes, which G1, G3 and G4 cover.
- [x] **G6, G7, G7b, G7c.** Driven through the real paths: undo after a roof edit; `LevelWidget` Duplicate
      Level / Select Same Level (G7); block paste lands on the active level (G7b, B1); Notes and
      gridline-hosted blocks stay behind (G7c, B2 / B3). Each is shown RED at base or with its fix reverted.
- [x] The `place_block_instance` tripwire scan still accepts the store's block `build` (it passes `place_kwargs`).
- [x] The linked specs got their pointers at Account; this spec is `status: current`. The VC6 full suite
      was waived by the user (2026-11-17); keep-green and the VC7 proofs stand.

## Existing Code Context

The passes and maps the table replaces are those named in D4. Their current per-kind order lives in
the code until the relocation commits, and this spec does not copy it: the G1 goldens pin it.
