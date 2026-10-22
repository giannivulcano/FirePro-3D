---
status: proposal
last-verified: 2026-10-22
verified-commit: 55dc0e26
applies-to:
  - firepro3d/block_library.py        # tier-aware roots, write guard, reserved name, status
  - firepro3d/block_definition.py     # base_version (serialized)
  - firepro3d/assets.py               # system root
  - firepro3d/app_data.py             # Styles/ defaults
  - firepro3d/hatch_patterns.py       # seeding retired; pickers System-first
  - firepro3d/system_library.py       # NEW: startup migration
  - firepro3d/blocks_browser.py       # pinned System row, padlock, Duplicate verb
  - firepro3d/block_editor.py         # BlockSaveDialog "duplicate" context
  - firepro3d/block_manager.py        # "update available" pill, Save -> Duplicate
  - firepro3d/model_space.py          # retarget_block_refs
  - firepro3d/schematic_new_dialog.py # system=False
  - firepro3d/settings/panes.py       # Styles/ placeholders
  - main.py                           # startup migration call
source-tasks:
  - "SB1b -- System library tier (todo_open.md, [type:feature], P1)"
---

# SB1b -- System Library Tier -- Design Spec

> Governing concept: `docs/superpowers/specs/2026-09-29-system-blocks-concept-design.md`
> (Q8, F4, F8, G5). This doc owns the SB1b build decisions; facts owned by
> `docs/specs/block-system.md` and `docs/specs/hatch-and-fill.md` are linked, not
> restated (Rule A). Every decision below was ratified by the user on 2026-10-22
> (Phase 2 grill Q1-Q10, Phase 3 approaches + sections 1-4).

## Goal

Shipped blocks live in a read-only **System** tier that sits beside the user's
block library. The user sees it first in the Blocks browser with a padlock, can
use it everywhere a library block is used, and customizes a System block only
by **Duplicate to library...** (a new block with a new id). In SB1b the tier
ships the five hatches only.

## Motivation

D-A39 copied the shipped hatches into an editable user folder, so an app update
could never fix them and an edited copy forked the frozen id. F4 rejected that
model: read-only shipped content plus Duplicate keeps shipped and customized
content apart. SB3/SB4 will put the app's own annotation graphics in this tier,
so the tier, its guard and its update path must exist first.

## Architecture & Constraints

- One library module owns the tiers (`block_library`); callers keep their
  `root=` idiom and mostly don't change (Approach A).
- The System tier is never written by the app (G5). The only write path into a
  user library from System content is Duplicate, which always mints a new id.
- A project embeds every block it uses and its copy is authoritative
  (`block-system.md` decision 4). A newer shipped version surfaces only through
  the Block Manager status pill; Reload stays explicit (concept Q8).
- Geometry stays in mm; theme colours by token (`theme.color(...)`); constants
  in `constants.py`; graphics via `assets.py`.

## Design Decisions

| # | Decision | Rejected | Why |
|---|----------|----------|-----|
| D1 | **Tier-aware roots in `block_library`.** `_roots(root, *, system=True)` -> `[("system", system_root()), ("user", root or block_library_dir())]`. `system_root()` = `assets.system_blocks_path()` with a module-level test override. Entries carry `tier`. A System entry is Library `"System"`, Series = its first folder (`Hatches`). | B: a separate module merged by each of ~10 walkers; C: a virtual `System/` overlay in the user root | One choke point for listing, ownership and the read-only guard. |
| D2 | **System wins an id clash.** `_find_by_id` and the duplicate-owner rule check the System tier first. | user copy wins | A leftover user copy must not shadow a shipped id. |
| D3 | **Write guard + reserved name.** `save_to_library`, `create_folder`, `delete_from_library` raise `SystemLibraryReadOnly` for any path under the System root, and refuse a user Library named `System` (case-insensitive). | per-caller checks | G5 at the single write choke point. |
| D4 | **Shipped hatches live only in System (Q1-A).** D-A39 seeding retires: `seed_hatch_folder` and its two callers (`main.py` startup, the settings dialog Apply) go. Pattern pickers list System hatches first, then the user Hatch patterns folder, de-duplicated by id, and work with no user folder at all. | keep seeding; both | F4; updates reach users. |
| D5 | **Startup migration (Q2-A, Q3-A)** in new `system_library.migrate_user_library()`, idempotent by state (no new flag): (1) for every folder in the `paths/hatch_seeded` list, delete `.fpdb` files byte-identical to a shipped file, give a file that holds a shipped id but differs a fresh uuid (it becomes an ordinary user block), then clear the key; (2) if `<block_library>/System/` exists and none of the three folder overrides points into it, move it to `<block_library>/Styles/` (file by file without overwriting when `Styles/` exists). Default folders become `<block_library>/Styles/{Hatches,Linetypes,End Types}`. Explicit overrides are never moved. | leave copies; rename only | One clean library; no duplicate ids on disk. |
| D6 | **SB1b ships Hatches only (Q4).** No empty series folders. `SYSTEM_DEFAULTS` and the G5 missing-block fallback move to SB3 (Q5). | ship empty series | Nothing to put there yet. |
| D7 | **`base_version` (Phase 3).** `BlockDefinition.base_version`: the library version the project copy was last loaded, reloaded or saved at; serialized with the definition. Untouched = `version == base_version`; a definition without the field counts as untouched. | version compare only; drop the state | An integer version bumped per edit cannot tell an edited older copy from an untouched one. |
| D8 | **New status `"update available"` (Q6-B).** `source_status` returns it when the library file's version is greater than the project's and the project copy is untouched. Edited copies stay `"modified"`. Block Manager pill token `accent`. | keep "modified" | An app update must not read as a user edit. |
| D9 | **Duplicate to library... (Q7).** `BlockSaveDialog` in a new `"duplicate"` context: name defaults to `"<name> copy"`, Library/Series from the user tree ("System" refused by the validator, "+" creates folders as today). On OK: new id, saved to the user library, loaded into the project, opened in the Block Editor (`BlockEditorManager.edit_definition`). | in-place copy | The only customization path. |
| D10 | **Edit Block / double-click-to-edit on a System block opens the Duplicate dialog (Q8).** No read-only editor. | read-only editor | One verb. |
| D11 | **Block Manager Save on a System-origin copy (Q8b)** opens the Duplicate dialog; on OK the edited project copy is committed under the new id and the project is **retargeted** to it (D12). | copy without switch | The project uses the user's copy everywhere. |
| D12 | **`model_space.retarget_block_refs(old_id, new_id)`**, one undo step: re-points block instances (`block_id`) and every hatch/tile ref holder. Known holders: fill layers (`fill_layers.py`), Display Manager category rows (`display_manager.py`), refs inside block-definition primitives (`geometry_2d.py`). **As-proposed:** the complete holder list is plan step 1 (P3 grep of every holder of a hatch/tile ref); guard 8 enumerates it. | instances only | Q8b. |
| D13 | **Blocks browser (Q9-A).** The System Library row is pinned first with a padlock icon (path builder extracted from `gridline._LockIndicator` at the origin, rendered to a cached `QIcon`), then a separator, then user libraries A-Z. Tooltip on System rows: "Shipped with FirePro3D -- read-only. Duplicate to customise." Context menu adds **Duplicate to library...**. | padlock per block; no mark | Q9. |
| D14 | **Schematics.** `NewSchematicDialog` lists with `system=False`; System content is never a schematic template. | include | No schematic ships in System. |
| D15 | **Tests.** An autouse conftest fixture points `system_root()` at an empty temp folder; guards that need the real shipped tier opt in. | rewrite every count | ~20 tests enumerate a temp root. |

## Acceptance Criteria (guards, VC3 -- Q10 + Phase 3)

- [ ] G1 Read-only: `save_to_library`, `create_folder` and `delete_from_library` against the System tier are refused; the shipped files are byte-identical afterwards. A user Library named "System" is refused.
- [ ] G2 Duplicate to library: a new id lands in the picked Library/Series as "<name> copy" and opens in the Block Editor; the same from Block Manager Save on a System-origin copy, and the project switches to the copy.
- [ ] G3 Edit Block on a System block opens the Duplicate dialog, not the editor.
- [ ] G4 Migration on a real temp library: identical seeded hatches deleted, an edited one kept with a new id, `System/` moved to `Styles/`, a folder override untouched; a second run changes nothing.
- [ ] G5 The pattern picker lists the 5 System hatches with no user hatch folder.
- [ ] G6 An older untouched project copy reads "update available"; Reload brings it to "library"; an edited older copy reads "modified".
- [ ] G7 Blocks browser, shown live: System first, padlock + tooltip on its row; separator; user libraries A-Z.
- [ ] G8 `retarget_block_refs` re-points every holder kind from the plan step 1 enumeration; undo restores each.
- [ ] G9 `base_version` round-trips through save/load; a project without it reads as untouched.
- [ ] Keep-green: existing library, hatch, linetype, end-type and browser tests (coupled set in the plan).

## Verification Checklist

- [ ] All guards GREEN, each shown RED with its change reverted.
- [ ] VC5 coupled set green; VC6 full suite on the final tree.
- [ ] Live smoke: first launch over a library seeded by HF2 (cleanup + `Styles/`), browser, Duplicate, Block Manager pill + Save, picker.
- [ ] Spec amendments landed at Account (below).

## Spec amendments (Account)

- `docs/specs/block-system.md`: System tier + multi-root section (F8), `base_version`, status values.
- `docs/specs/hatch-and-fill.md`: D-A39 retired (System tier owns shipped hatches), D-A24 "shipped set" now in System; Hatch patterns default `Styles/Hatches`.
- `docs/specs/linetypes.md`, `docs/specs/settings-dialog.md`: default folders `Styles/...`.
- `todo_open.md`: SB3 gains `SYSTEM_DEFAULTS` + the G5 missing-block fallback; SB1b line drops them.
- Concept promotion to `docs/specs/system-blocks.md` stays with SB3 (end of build phase 1).

## Existing Code Context (probed at 55dc0e26)

- `block_library`: `_root`, `_walk_fpdb` (depth <= 2), `_tiers`, `_iter_entries`, `_find_by_id`, `source_status` (integer version compare by id), writers `save_to_library` / `create_folder` / `delete_from_library` (no production caller).
- `hatch_patterns`: frozen `BUILTIN_*` ids, `shipped_pattern_files`, `seed_hatch_folder` + `paths/hatch_seeded`, `library_patterns` -> `capability_folder.scan`.
- `app_data`: `hatch_patterns_dir` / `linetypes_dir` / `end_types_dir` default under `<block_library>/System/`.
- `blocks_browser`: `_grouped`, `refresh` (`sorted(grouped)`), `_build_context_menu` (Edit Block only), `_edit_item`, `ensure_block_loaded`.
- `block_editor`: `BlockSaveDialog`, `_save_via_dialog`, `_save_to_library`, `BlockEditorManager.edit_definition`.
- `block_manager`: `status_root`, `_STATUS_TOKEN`, `SourceStatusDelegate`, `_sync_ui`, `_save_to_library`, `_reload`.
- `model_space`: `_swap_block_definition` (same id only), `reload_block_definition`, `duplicate_block_definition`, `commit_block_definition`.

## Edge Cases & Error Handling

- A user `Styles/` already exists when `System/` is migrated -> per-file move, never overwrite; a clashing file stays in `System/` and is logged; the next run retries.
- A seeded folder from the `hatch_seeded` list no longer exists -> skipped; the key still clears.
- The System root is missing (broken install) -> the tier is empty; pickers fall back to the user folder; no crash.
- A user `.fpdb` carries a frozen System id (copied by hand) -> System wins (D2); Block Manager shows the System status.
- Duplicate cancelled -> nothing written, project unchanged.
- Retarget undo -> every holder restored; the new definition stays registered (one undo step pops both).
