---
status: proposal          # designed 2026-11-16, unbuilt; flips to current at the build's Account
last-verified: 2026-11-16
verified-commit: 68511b61  # census base (probe digest); re-stamp at Account
applies-to:
  - firepro3d/element_store.py
source-tasks:
  - "todo_open.md - Element store (one row per element kind) [P1], rulings R1-R8 + Phase 3 rulings O1, O2"
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
| `constraint_role` | `None`, `"primitive"` (Block Editor) or `"plan"` |
| `codec_owned` | `True` when `network_codec` writes and reads the records (design areas only) |
| `build(scene, record, ctx)` | creates the item from a record, attaches its children, adds it to the scene and appends it to the list; returns the item or `None` |

`ctx` is a small `BuildContext`: which path is building (`"load"` or `"restore"`), the block-definition
`source_path` map (restore) and the orphan-host counter (load). Path-specific steps read `ctx`. They are
not separate build functions.

### D2 - Order (Phase 3 ruling O1)

The table's row order is the undo-capture order. Undo bytes therefore follow from the table itself.
A pass whose order differs names its own tuple of row `attr`s, and the completeness test (G4) checks
that each tuple covers exactly the rows that pass needs. Two such passes exist today:

- the file save, which writes `constraints` between `walls` and `floor_slabs`, splices that key after the
  `walls` row;
- `scene_tools._all_geometry_items`, whose order (lines first) is the index order constraints use.

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
| `_restore_network` | removal (children before owner; walls detach the list first, which avoids a quadratic join rebuild), then `build` per record, `legacy_keys` included |
| `save_to_file` | rows with a `file_key`, in the D2 save order |
| `load_from_file` | `build` per file row; the clean-drop count sums the `file_key is None` rows' `undo_key`s plus `legacy_keys` |
| `_clear_scene` | rebinding every row's list (as today: clear rebinds, restore clears in place) |
| `_remove_item_from_lists` / `_bulk_delete` | the class-to-row map; owner removal goes through `children` |
| `_items_on_level` / `leveled_items` | one walk over rows with `level_of` (D5) |
| `_GEOM_TYPE_REGISTRY`, `schematic_scene._CLS_TO_LIST` / `_PRIMITIVE_LISTS`, `constraint_controller._PARTICIPATING` / `_PRIMITIVE_LISTS` / `_PLAN_PARTICIPATING`, Display Manager's 2D and Reference tuples | derived from `record_type`, `constraint_role` and `category` |

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

- [ ] Every pass in D4 reads the table. No class-to-list map or element-list name tuple is left
      outside `element_store.py` except the D2 order tuples and the D3 exceptions.
- [ ] Commits 3-7 leave G1 byte-identical to base.
- [ ] Roofs have a scale manager after undo (R2).
- [ ] Duplicate Level copies a placed block and Select Same Level selects it (R5).
- [ ] The loose 2D rows are outside the level walk (O2).
- [ ] The 1b before-baseline (138 coupled test files, `.todo/es-baseline-files.txt`) passes unchanged, except the
      O2 rewrite. Its 3 known base failures stay the same.

## Verification Checklist

- [ ] **G1.** An every-kind fixture's save bytes and undo-snapshot bytes match the base golden, with EOL,
      uuid and date normalised. Save, load, save is a fixed point.
- [ ] **G2.** Each kind survives an undo / redo round trip with the same record.
- [ ] **G3.** `_clear_scene` leaves every row's list empty and the scene holds none of the items.
- [ ] **G4.** Table-driven completeness. Every row survives save / load (if `file_key`), capture / restore,
      clear and remove, and appears in the level walk (if `level_of`). Every D2 order tuple covers
      exactly its pass's rows. A row with a missing piece turns it RED.
- [ ] **G5.** A scan guard fails on a new class-to-list map or element-list tuple outside the store.
- [ ] **G6, G7.** Driven through the real paths: undo after a roof edit, and
      `LevelWidget` Duplicate Level / Select Same Level. Each is shown RED at base.
- [ ] The `place_block_instance` tripwire scan still accepts the store's block `build` (it passes `place_kwargs`).
- [ ] VC6 full suite; the linked specs get their pointers at Account; this spec flips to `status: current`.

## Existing Code Context

The passes and maps the table replaces are those named in D4. Their current per-kind order lives in
the code until the relocation commits, and this spec does not copy it: the G1 goldens pin it.
