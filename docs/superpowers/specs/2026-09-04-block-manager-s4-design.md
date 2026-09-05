# Block Manager (S4) — Design (HOW)

> Slice **S4** of the Block System. Governed by `docs/specs/block-system.md` (this design updates
> that spec's Manager sections in place). The **WHAT** was locked in a Phase-2 grill; this doc is the
> **HOW** only. **Thumbnails are cut from S4** (Design-Decision-5 + the thumbnail acceptance criterion
> are deferred — see Follow-ups).

## Goal

Replace the `_open_block_manager` stub (`main.py`) with a real, modeless **Block Manager** dialog that
manages the project's embedded block definitions (`Model_Space._block_definitions`): edit metadata,
see live instance counts + library source-status, delete unused definitions, and resolve
library divergence (Save-to-Library / Reload-from-Library). Mirrors the Underlay Manager
(MVC + `FramelessShellMixin`).

## Architecture & Components

### New module `firepro3d/block_manager.py` (thin Qt view over the scene API)

- **`BlockManagerDialog(FramelessShellMixin, QDialog)`** — singleton, modeless. Constructor
  `(scene, main_window, theme=None, parent=None, apply_stylesheet=True)`. Layout mirrors the Underlay
  Manager: mixin titlebar → **toolbar** (Save to Library · Reload from Library · Delete[danger]) →
  body split (**flat table** left / **details panel** right ~268px) → **footer**
  ("N blocks · M instances" + Close). Launched from `MainWindow._open_block_manager` via the
  lazy-singleton `show()/raise_()/activateWindow()` pattern (cache on `self._block_manager`).
- **`BlockTableModel(QAbstractTableModel)`** — flat (no child rows). Five columns via a `Col`
  IntEnum: `NAME / LIBRARY / SERIES / COUNT / STATUS`. On reset, snapshots
  `list(scene._block_definitions.values())` and builds a `{id: instance_count}` map by iterating
  `scene._block_instances` once. All columns **read-only for display** — metadata editing happens in
  the details panel (Fork 2 = full-mirror layout).
- **`SourceStatusDelegate(QStyledItemDelegate)`** — colored status badge, reusing the level-chip
  painting pattern + theme tokens: `project-only` → `muted`, `library` → `ok`/`accent`,
  `modified` → `warn`.
- **`build_block_manager_qss(theme)`** added to `theme.py` — clone of `build_underlay_manager_qss`
  (same `#shellHeader`/toolbar/footer/table/detailsPanel object names + tokens).

### `Model_Space` block-management API (net-new; the arm's-length logic home)

The Qt view calls these; guard tests target them directly (no dialog machinery).

- `blockInstancesChanged` — new `pyqtSignal()`; emitted from `place_block_instance` /
  `remove_block_instance` (and the clear/restore paths where instances are bulk-added/removed).
- `instance_count(block_id) -> int` — count of `_block_instances` whose `block_id` matches.
- `delete_block_definition(block_id) -> bool` — returns **False** (refuses) when
  `instance_count(block_id) > 0`; else pops the definition from `_block_definitions`,
  `push_undo_state()`, emits `blockDefinitionsChanged`.
- `reload_block_definition(block_id) -> bool` — fetches the library copy
  (`block_library.reload_from_library`); if absent returns False. Else replaces the registry entry,
  **rebuilds `new_defn._instances` backrefs** for every matching instance and calls
  `on_definition_changed()` on each (repaint + edit-propagation survive the swap), `push_undo_state()`,
  emits `blockDefinitionsChanged`.
- `set_block_metadata(block_id, name, library, series) -> bool` — validates non-blank (trimmed) and
  (library, series, name) uniqueness across the registry excluding self; on failure returns False; on
  success mutates the definition in place (`id`/`version` untouched), `push_undo_state()`, emits
  `blockDefinitionsChanged`.

**Save-to-Library** is not a model mutation: the dialog calls `block_library.save_to_library(defn)`
directly (disk write), then re-queries `source_status` to refresh the badge.

### Undo (no new plumbing)

`_capture_network` already serializes `block_definitions` via `to_dict()` and `blocks` (instances), so
every registry mutation is undoable simply by calling `push_undo_state()` after it. Delete, Reload, and
metadata edits each push one undo state. Save-to-Library is a pure disk write → **not** undoable.

## Data Flow

- **Live count:** the model connects to **both** `blockDefinitionsChanged` (registry add/remove/rename)
  **and** `blockInstancesChanged` (instance place/remove). Either → `beginResetModel`/`endResetModel`
  (recompute snapshot + count map). Full reset per event is fine (few definitions; user-paced).
- **Edit:** panel `QLineEdit` `editingFinished` → `scene.set_block_metadata(...)`. `False` → revert the
  field to the definition's current value. `True` → scene already pushed undo + emitted → model resets
  → panel re-syncs.
- **Actions (gated by selection + source-status):**
  - **Save to Library** — enabled when `project-only | modified` → `save_to_library`; `OSError` →
    themed error; refresh status.
  - **Reload from Library** — enabled when `modified` → `reload_block_definition`.
  - **Delete** — on click, if `instance_count > 0` show themed message *"Can't delete '{name}' —
    {n} instance(s) in the model"* and abort; else `delete_block_definition` (undoable).
- **Selection → panel sync:** `selectionChanged` → populate Name/Library/Series fields, status badge,
  instance-count label; enable/disable actions by status + count.

## Edge Cases & Error Handling

- **Empty project:** empty table, blank/disabled panel, disabled actions, footer "0 blocks ·
  0 instances". No error.
- **Delete refused (count > 0):** themed message names the count; definition untouched. The guard
  re-checks the **live** count at click time (display staleness can never cause a wrong delete).
- **Reload backref rebuild:** replacing the registry entry orphans the old `defn._instances`;
  `reload_block_definition` re-appends every matching instance to the new defn and calls
  `on_definition_changed()`. Covered by a guard test.
- **Library folder absent (portability):** `source_status` → `project-only`; Save/Reload operate
  against `app_data_dir("blocks")` and fail gracefully (themed `OSError`), never crash. Opening a
  project with `blocks/` absent is unaffected (embedded copy authoritative).
- **Rename / re-file doesn't reconcile disk:** editing `name` keeps the version-based `source_status`
  (on-disk name silently diverges from the embedded name); editing `library`/`series` re-points the
  library lookup to a *different* (empty) folder, so `source_status` flips to `project-only` and
  Reload can't find the on-disk copy until re-saved (seam review, 2026-09-04). Both are **accepted for
  S4** (metadata edit is embedded-only by design; stale-`.fpdb` cleanup + scan-by-`id` is a filed
  follow-up). `id` never changes → instances never break, and neither path crashes.
- **Metadata validation:** blank name/library/series → revert; a (library,series,name) triple already
  used by another definition → revert. Whitespace trimmed.
- **Modeless staleness:** the two signals keep the table live against edits made elsewhere.

## Testing

**Headless guards** (target the scene API + a light `BlockTableModel` test), each shown RED with the
fix reverted:

1. `instance_count` accurate; `blockInstancesChanged` fires on place/remove; model count updates.
2. `delete_block_definition` refuses at count > 0 (defn stays); succeeds + undo restores at count 0.
3. `source_status` mapping (project-only / library / modified) on a temp-root library (reuse the S3
   temp-root fixture pattern).
4. `save_to_library` writes `.fpdb` + index entry; `reload_block_definition` pulls a diverged copy,
   rebuilds backrefs, repaints, undoable.
5. `set_block_metadata` validation (blank → False, collision → False, legal rename mutates metadata,
   `id` stable).

**Live smoke checklist** (headless-green is not "done"): ribbon opens the real dialog (stub replaced);
frameless drag/resize; dark + light theme; live count while placing/deleting with the Manager open;
delete-refusal message names the count; Ctrl+Z restores a delete; Save/Reload flip the status badge;
project opens with `blocks/` absent.

## Spec impact (`docs/specs/block-system.md`, updated in place)

- Design-Decision-10 / S4 build-order line rewritten to this design (metadata panel edit + live count +
  divergence actions; five columns, no thumbnail column).
- **Design-Decision-5 (thumbnails) and the thumbnail acceptance criterion marked DEFERRED** (cut from
  S4). The `(id, version)` thumbnail key stays reserved for the v2 Editor.
- Frontmatter `last-verified` / `verified-commit` stamped when S4 lands.

## S4.5 — Load from Library ("Load Family") + tree reshape

> Added 2026-09-04 (grill + brainstorm). Folds into the same branch. Revit "Load
> Family" mental model: a file dialog embeds `.fpdb` definitions into the project.
> The user un-deferred the S4-grill "union/library view" (Q1) as a file-dialog
> load rather than an in-app library mirror.

### Library/loader layer (the tested seam)

- **`block_library.load_block_file(path) -> BlockDefinition | None`** — reads any
  `.fpdb` path directly (`BlockDefinition.from_dict(json.load(...))`; a `.fpdb`
  file IS exactly `to_dict()` JSON). Tolerant: logs + returns None on corrupt.
  (Existing `load_block` needs library/series/filename → can't serve a
  browse-anywhere path.)
- **`Model_Space.load_blocks_from_files(paths, root=None) -> dict`** — the
  arm's-length batch loader (headless test seam). Per path: `load_block_file`;
  None → `failed`. Collision rules vs `_block_definitions`:
  - `id` present, same `version` → **skip** (`skipped`).
  - `id` present, different `version` → **replace** via the shared
    `_swap_block_definition(block_id, new_defn)` helper (registry swap + backref
    rebuild + `on_definition_changed()` repaint) → `replaced`.
  - `id` absent, `(library, series, name)` matches another def → **refuse**
    (`refused`).
  - else → embed (`_block_definitions[new.id] = new`) → `loaded`.
  - **Batch discipline:** mutate the registry with NO per-file emit/undo; after
    the loop, if anything changed, `push_undo_state()` **once** + emit
    `blockDefinitionsChanged` **once** (guards against N model resets). Returns
    `{loaded, replaced, skipped, refused, failed}` (name lists for the summary).
- **GENERALIZE:** extract `_swap_block_definition(block_id, new_defn)` from the
  existing `reload_block_definition` (which becomes: fetch library copy →
  `_swap_block_definition` → push_undo + emit). One backref-rebuild, two callers.

### Tree reshape (replaces the flat table)

- **`BlockTreeModel(QAbstractItemModel)` replaces `BlockTableModel`** in
  `block_manager.py`, mirroring `UnderlayTreeModel`: Library group → Series group →
  block leaf, grouped from `_block_definitions.values()`, identity-keyed `_Node`
  cache. Same 5 columns; on **leaf** rows NAME/COUNT/STATUS populate (COUNT =
  `instance_count`, STATUS via the retained `SourceStatusDelegate`); on **group**
  rows only the label renders (group COUNT roll-up = deferred polish). Live resets
  on both `blockDefinitionsChanged` + `blockInstancesChanged` (unchanged). A
  `BlockDefRole` returns the definition for a leaf, `None` for group rows.
- **Dialog adaptation:** `self.view` becomes a `QTreeView` (`setRootIsDecorated`);
  `_current_def()` reads `BlockDefRole` → leaf def or None (group → panel blanks +
  leaf actions disable, same path as no-selection); selection-preservation stays
  keyed by definition `id` (`row_for_id` becomes a tree walk to the leaf index);
  panel metadata editing unchanged. The S4 `test_block_manager_model.py` tests are
  **rewritten** to the tree (same behaviors, tree indices).

### Wiring, file dialog, buttons

- Toolbar gains **"Load from Library…"** (`variant="primary"`, always enabled →
  `_load_from_library`) and **"Open in Editor"** (enabled only on a leaf → stubbed
  `themed_info(self, "Block Editor", "The Block Editor arrives in a later slice.")`,
  the S4 `_open_block_manager` stub pattern), alongside Save/Reload/Delete.
- `_load_from_library()` = thin shell: `QFileDialog.getOpenFileNames(self, "Load
  Blocks", app_data_dir("blocks"), "FirePro3D Blocks (*.fpdb)")` → on non-empty,
  `self.scene.load_blocks_from_files(paths, root=self._root)` → themed summary
  message (omit zero categories: "Loaded 3 · replaced 1 · skipped 1 (already
  present) · refused 1 (name in use) · 2 unreadable"). The loader's single emit
  refreshes the tree; `_sync_ui` runs via the reset handler.
- Open-in-Editor enablement folds into `_sync_ui`.

### Error handling (S4.5)

- Corrupt/unreadable `.fpdb` → `failed` count, never raises. Cancelled dialog →
  no-op, no undo. Nothing-changed batch (all skip/refuse) → no undo pushed, summary
  still shown. Group-row leaf actions unreachable (disabled + None-guard).
  Portability preserved (loads embed into the registry).

### Testing (S4.5)

Headless guards (target `load_blocks_from_files` + `load_block_file` with temp
`.fpdb` files, RED-first): (1) load embeds + placeable + one-undo + undo-unloads;
(2) collision rules (skip/replace-with-repaint/refuse) + summary counts;
(3) batch = exactly one `push_undo_state`, undo reverts whole batch; (4) unreadable
file → `failed`, no crash, others load; (5) `BlockTreeModel` shape (group→series→
leaf; leaf COUNT/STATUS; `BlockDefRole` None on groups; `_current_def` resolves a
leaf). Live smoke: file dialog at blocks folder / browse elsewhere / `*.fpdb` /
multi-select; loaded blocks in tree + browser + placeable; mixed-batch summary;
corrupt-file grace; undo unloads; Open-in-Editor stub message.

## Follow-ups (filed, out of S4)

- **Thumbnail pipeline** — render-ops → `QPixmap`; PNG-next-to-`.fpdb`; populate the `index.json`
  `thumbnail` field; keyed `(id, version)`; browser + Manager preview. (Was S4's "+ thumbnails".)
- **Stale-`.fpdb` cleanup** — on rename / tier-change + Save-to-Library, delete/relocate the old
  library file instead of leaving it (the S3.x `scan-by-id` / re-file follow-up).
- **Full library-file browser** — import library-only `.fpdb` blocks into a project; delete `.fpdb`
  files from disk (`block_library.delete_from_library` already exists).
- **Optional manual thumbnail-refresh** button (only meaningful once geometry is mutable in v2).
- **Shipped/default block set + preloading** (S4.5) — a curated block library shipped with the app,
  and auto-preloading blocks into a project via project templates / user profile (the user's stated
  future direction; S4.5 loads only what's already on disk).
- **Relax name-collision on load** (S4.5) — instead of refusing a different-`id` block whose
  `(library, series, name)` is already loaded, offer a rename-on-load. S4.5 refuses (safe).
- **Wire "Open in Editor"** to the real v2 Block Editor (stubbed in S4.5).
- **Group-row instance-count roll-up** in the tree (Library/Series rows summing child leaf counts) —
  deferred polish; S4.5 leaves group COUNT blank.
