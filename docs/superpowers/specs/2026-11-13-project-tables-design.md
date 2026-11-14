---
status: proposal
last-verified: 2026-11-13
verified-commit: 2509b668
applies-to:
  - firepro3d/project_tables.py
  - firepro3d/scene_io.py
  - firepro3d/paper_display.py
  - main.py
source-tasks: ["todo_open.md - Project tables (open / new / save): [type:maint] One project_tables module owns migrating, installing and saving the project tables"]
---

# Project tables -- Design Spec

Ratified inputs, not re-asked here: the architecture-review grill Q1-Q11 (recorded in the
task's Details in `todo_open.md`) and the three Phase 2 deltas of 2026-11-13 (the template-clone
kind is dropped; the QSettings-backed DM and paper stores are kept and filed as a +1 occurrence on
the paper-categories live-store bug; inputs and goldens are committed at base). Term:
**project tables** (`GLOSSARY.md`) = line weights and aliases, fill types, materials, phases,
Display Manager rows and paper categories.

## Goal

One module, `firepro3d/project_tables.py`, owns the order in which project tables are migrated,
installed, finished and saved on open (file and crash recovery), New, startup and Save.
Callers (`scene_io`, `main`) make a fixed series of calls into it and no longer know the
ordering. **Nothing moved:** every open, New, startup and Save gives the same tables, the same
holder weight names and the same saved bytes as before.

## Motivation

The "migrate, then install, then read" order is spread over `scene_io.load_from_file`,
`main._apply_loaded_file`, the module global `paper_display._PENDING_LW_MIGRATION`, payload
dicts mutated in place for a later re-apply, and a New/startup sequence repeated word for word
in `main.py`. Commits F3-F6 (LW-DC) were all bugs in this ordering. PH3 (phase graphics) is
about to add another table step; it should land on one owner.

## Architecture & Constraints

- **Orchestrator, not a store (Q8).** Each table module keeps its storage and its
  load/migrate functions; they become internal seams that only `project_tables` calls. No single
  stored `ProjectTables` value.
- **Call sites keep their place in `load_from_file`.** The undo baseline (`push_undo_state`)
  sits between the LW-DC-8 holder retarget (before it) and the DM / paper apply (today in
  `main`, after `load_from_file` returns, after the annotation-tag build). The design keeps that
  split, so the baseline's content is unchanged.
- **LW-DC-8 compute-when-used (Q2).** The weight mapping is computed when first used, after the
  block-library merge (`Model_Space._merge_bundled_weights`), never at stash time. No payload
  rewrite before parse.
- **Out of scope:** app-start QSettings migrations (`migrate_settings_weights`,
  `_migrate_display_keys`) (Q1); undo restore `_restore_network` (Q10); project scoping of DM rows
  and paper categories (filed: `todo_open.md`, paper categories live-store bug, +1 occurrence).
- Imports are relative within `firepro3d/`; Google docstrings.

## Design Decisions

**DD1 -- approach A: functional module + `LoadSession`.** Considered: (B) a table-adapter
registry looping over per-table hooks -- rejected: the weight step is non-uniform (stash,
retarget, payload fix) and the order must be explicit anyway, six fixed members (YAGNI);
(C) one `load_tables(scene, payload, build_callback)` that drives the scene build -- rejected:
turns `load_from_file` inside out, large diff for a maint task.

**DD2 -- API and call placement.**

| Call | Runs | Replaces |
|------|------|----------|
| `migrate_payload(payload)` | `load_from_file`, before `_clear_scene` | `migrate_project_payload` (HF1) then `phase_registry.migrate_payload` (D-PH6) |
| `begin_load(payload) -> LoadSession` | right after `_clear_scene`, same spot as today | `apply_project_weights(stash=True)`, `load_project_fill_types`, `load_project_materials`, `load_project_phases`, the `_loaded_*` stash |
| `session.underlay_map` | underlay loop | `pending_weight_mapping()`; lazy, computed on first read and cached |
| `session.migrate_holders(scene)` | before `push_undo_state` | `apply_pending_weight_migration(...)` |
| `session.apply_styles(scene)` | last statement before `return True` | `main._apply_loaded_file`'s DM block (project rows, else `apply_saved_display_settings`) then `apply_paper_display_from_project` |
| `start_fresh(scene)` | New and startup | `main.py` duplicated block: three `reset_project_table`, `apply_default_display_settings`, `reset_project_line_weights`, `apply_template_settings` |
| `tables_for_save() -> dict` | `save_to_file` | the five getters; spliced with `**` at the same position so key order (and bytes) are unchanged |

**DD3 -- the global goes.** `paper_display._PENDING_LW_MIGRATION` is deleted.
`apply_project_weights(data, stash=True)` returns the migration kind (`"table"`,
`"tableless"` or `None`); `_pending_migration`, `pending_weight_mapping` and
`apply_pending_weight_migration` take the kind as a parameter. The session holds the kind and
the `display_settings` / `paper_display` payload references; `migrate_holders` fixes those
payloads in place exactly as today, and `apply_styles` reads them.

**DD4 -- `scene._loaded_display_settings` / `scene._loaded_paper_display` are removed.** No
production reader remains once `main` stops reading them; the tests that read them go through
the session (DD6).

**DD5 -- `main._apply_loaded_file`** drops its DM / paper block and keeps
`_refresh_weight_canvases` (window re-pen) (Q4).

**DD6 -- characterisation first (Q6).** A harness committed against base code before any move:

| Case | Input | Entry point |
|------|-------|-------------|
| pre-LT1 | new `tests/fixtures/project_tables/pre_lt1_tableless.fpd` | `MainWindow._load_project` |
| schema-1 x2 | `tests/fixtures/hf5_legacy.fpd`, `tests/fixtures/ph1_pre_phasing_v12.fpd` | `_load_project` |
| schema-2 | new `tests/fixtures/project_tables/schema2.fpd` | `_load_project` |
| second open | schema-2, then pre-LT1, same window | `_load_project` x2 |
| crash recovery | schema-1 copied to the autosave `recovery.FPD` | `_check_recovery` (prompt patched to accept) |
| New | after opening schema-2 | `new_file` (save prompt patched) |
| startup | -- | `MainWindow()` |

By-name weight holders are injected into a copy of each input (`_inject_by_name_weights`).
Snapshot per case: weight table, aliases, Model Blocks weight; fill types, materials, phases;
DM rows (`get_display_settings_for_save`); paper categories (`load_paper_categories`); every
holder's weight name (`_holders`); immediate re-save (`save_to_file(..., backup=False)`), tmp
path normalised, compared as raw bytes and stored as pretty JSON for readable diffs. Goldens in
`tests/fixtures/project_tables/` are written only with `FP3D_REGEN_GOLDENS=1`, only at base.
`_holders` and `_inject_by_name_weights` are promoted from `tests/test_lwdc_open_migration.py`
into `tests/_project_tables_helpers.py` (GENERALIZE).

**DD7 -- test rewrites (VC5).** `tests/test_lwdc_open_migration.py` (reads of
`pd._PENDING_LW_MIGRATION` -> the session's kind; `apply_pending_weight_migration`
monkeypatches, F8 included -> `LoadSession.migrate_holders`); `tests/test_hf1_colour_tokens.py`,
`tests/test_lt1_project_weights.py`, `tests/test_lt2_rename.py` (`_loaded_*` reads -> session).
Each rewritten test is named in the done evidence.

**DD8 -- spec wiring at Account (Q11).** `docs/specs/scene-io.md` gains a "Project tables"
section owning the term link, the order (migrate -> begin_load -> build -> migrate_holders ->
undo baseline -> apply_styles), the three entry points (from file, fresh, save), the
`LoadSession` contract, the internal-seams rule, and the QSettings-backed DM / paper stores
(pointer to the filed bug); its section 2 and section 3 link to it. Linked instead of restated:
`linetypes.md` LT2 open-time install, H-g, LW-DC-8, LW-DC-9 (LW-DC header restamped built);
`project-phasing.md` D-PH6, D-PH11; `hatch-and-fill.md` D-A20 and "Load migration";
`materials.md` (dead "HF5 R9" label -> hatch-and-fill D-A14 + the new section);
`settings-dialog.md` section 4.5 (acceptance "startup opens a clone" corrected to
`apply_template_settings`). `SPEC-INDEX.md` row and `scene-io.md` applies-to for
`firepro3d/project_tables.py`; `GLOSSARY.md` entry points to the section. Docstrings corrected:
`reset_project_line_weights` (reads QSettings, not "the template"), `apply_project_weights`
(runs after `_clear_scene`).

## Acceptance Criteria

- [ ] AC1: all eight characterisation cases match the goldens committed at base 2509b668
      (tables, DM and paper rows, holder weight names, re-save bytes).
- [ ] AC2: `_PENDING_LW_MIGRATION` and `scene._loaded_*` are gone; `scene_io` and `main` call no
      table load/migrate/reset/save function directly, only `project_tables` (grep at Account).
- [ ] AC3: New and startup share `start_fresh`.
- [ ] AC4: the DD7 tests are rewritten against the module's interface and named in the done
      evidence.
- [ ] AC5: the 1b before-baseline (42 files from `D:/Custom Code/FPD/pt-baseline-files.txt`: 561
      passed, 1 skipped) and the full `run-suite.ps1` gate against base 2509b668 pass.
- [ ] AC6: DD8 spec wiring landed and stamped.

## Verification Checklist

- [ ] Harness + goldens committed before any production move; RED proofs at base via
      `red-proof.ps1`: deleting the `apply_pending_weight_migration` call turns pre-LT1,
      schema-1 and recovery RED; dropping `phase_registry.reset_project_table()` from `new_file`
      turns New RED; moving `apply_paper_display_from_project` above the DM apply is run and its
      result (RED or order-independent) recorded.
- [ ] Re-save determinism probed first (two saves of one scene give identical bytes).
- [ ] Keep-green: the 148 coupled test files (grep set from 1b) plus the harness.
- [ ] VC9 seam review (Large build) before smoke.
- [ ] Smoke: open an old (pre-LT1) project, a current project, crash recovery, New, startup;
      line weights, fills, phases, DM and paper rows look as before.

## Edge Cases & Error Handling

- Load failure before `_clear_scene` (bad JSON): no session exists, the open project stays
  (today's behaviour).
- Exception mid-build: the session is dropped with the stack; no stale stash survives (today a
  stale global lingered until the next open reset it -- invisible, not a parity break).
- A file with no `display_settings`: `apply_styles` falls back to `apply_saved_display_settings`
  (QSettings), as `main` does today.

## Existing Code Context

Load sequence: `firepro3d/scene_io.py` `load_from_file` (migrations before `_clear_scene`, table
installs after it, underlay loop, `apply_pending_weight_migration` before `push_undo_state`,
annotation tags last). Open/recovery: `main.MainWindow._apply_loaded_file` via `_guarded_load`
(`_load_project`, `_check_recovery`). Fresh: `main.py` startup construction and `new_file`.
Save: `scene_io.save_to_file`. Weight internals: `firepro3d/paper_display.py` project file
persistence block. Template: `firepro3d/settings/template.py` `apply_template_settings`.
