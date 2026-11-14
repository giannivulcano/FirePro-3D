---
status: current
last-verified: 2026-11-14  # project-tables Account: s2/s3 pointers + s3a Project tables only, rest not re-audited; prior 2026-11-12  # room-detection Account: s2 rooms[].holes key paragraph only, rest not re-audited; prior 2026-11-12  # PH1 Account: s2 SAVE_VERSION sentence + phasing keys paragraph, s3 load order only, rest not re-audited; prior 2026-11-10  # sheet-linked doc Account: s2 sheets linked_document key paragraph only, rest not re-audited; prior 2026-11-06  # notes on schematics Account: SAVE_VERSION sentence, rest not re-audited; prior 2026-11-04  # data-loss Account: s2 backups + atomic write, s3 load failure contract + marker drop, acceptance lines only (verified at db3c357b), rest not re-audited; prior 2026-10-30  # SB3b + L283 Account: s2 additive keys paragraph + s5 undo-capture note only, rest not re-audited; prior 2026-10-27  # Editor/Build slice 2 Account: `constraints` key / load / checklist lines only (verified at db16090a), rest not re-audited; prior 2026-10-25  # SB2b Account: Marks payload keys + undo snapshot levels paragraph only (verified at ceacaab4), rest not re-audited; prior 2026-10-22  # gridline-hosted blocks Account: additive `host` / gridline `uid` keys + orphan-host drop (pointer only; verified at d44b0e11); prior 2026-10-20 HF3 Account: filled_regions key (loose-geometry list + C8 drop) pointer only (verified at 66880197); prior 2026-10-19 UP1 Account: fill-record no-version-bump pointer only (verified at 902c5c0e); prior 2026-10-18 HF1 Account: SAVE_VERSION 11 + colour_migration pointer; prior 2026-09-17  # + 2026-10-08 SV1 Account: `kind` sentence only (verified at b851b1aa) — rest not re-audited; + 2026-10-03 HF2 Account: §4 legacy-hatch sentence only (clean-dropped, hatch-and-fill H12; verified at 53e1773) — rest not re-audited
verified-commit: b5f653ea  # project-tables refactor (s3a Project tables + s2/s3 pointers only); prior 7cdb7146  # room-detection rework (s2 rooms[].holes key only); prior f2f0db3e  # PH1 (v0.101.0; s2 SAVE_VERSION + phasing keys, s3 load order only); prior f1dcede4  # feature/sheet-linked-doc close (0.96.0; linked_document key only); prior bfe51a30  # notes merge on main (v0.93.0; SAVE_VERSION sentence); prior db3c357b  # data-loss merge on main (save / load failure clauses only); prior 7e5d3b15   # SB3b + L283 merge on main; prior db16090a  # Editor/Build slice 2 Account (constraints key only); prior ceacaab4  # SB2b Account (Marks keys only); prior d44b0e11  # gridline-hosted blocks Account (host / uid keys only); prior 66880197 HF3 Account (filled_regions key only); prior 902c5c0e UP1 Account (fill pointer only); prior 084b43e0 HF1 Account (SAVE_VERSION sentence only); prior 6a36206
applies-to:
  - firepro3d/scene_io.py
  - firepro3d/project_backup.py
  - firepro3d/network_codec.py
  - firepro3d/project_tables.py
related-contract: model-space-containment-contract.md
source-tasks:
  - "todo_open.md → [feature] Implement the containment contract (orphan-gate: scene_io forged on first touch)"
---

# Scene I/O — the `.fpd` project format

> **Status: current.** The format contract (§2/§3) and the **clean-drop
> invariant** (§5, containment [C8](model-space-containment-contract.md)) are both
> code-verified as of the C1/C8 slice: standalone loose geometry / model text /
> model dimensions no longer serialize, and legacy ones are silently discarded on
> load. Forged on first touch (orphan-gate); promotes the thin
> `architecture/io.md`. Project extension is `.fpd` (see
> [`project_file_extension_fpd`]).

## Goal

Define the `.fpd` project persistence contract: what a saved project contains,
how load reconstructs it, and the invariants that keep the two serialization
paths (file vs undo) honest.

## Architecture & Constraints

### §1 — Two independent serialization paths (the dual-serialization invariant)

The scene is serialized by **two separate code paths that must carry the same
entity set**:

- **File I/O** — `SceneIOMixin.save_to_file` / `load_from_file` (`scene_io.py`),
  JSON to/from disk.
- **Undo snapshot** — `_capture_network` / `_restore_network` (`model_space.py`),
  in-memory snapshots for undo/redo.

**Invariant:** any entity persisted to the `.fpd` file must also be captured in
the undo snapshot, and vice versa. Adding or removing an entity type requires
editing **both** paths in the same change. Divergence between them is a known
bug-magnet (see [`project_dual_serialization_paths`]). Per-entity encode/decode
lives once in `network_codec.py` (nodes, pipes, dimensions, notes, water supply,
design areas) or on each item's `to_dict`/`from_dict` (geometry, walls, blocks…).

### §2 — Save

`save_to_file` writes a single JSON object (`payload`) with `version` =
`Model_Space.SAVE_VERSION` (13 since PH1 project phasing: below it, `phase_registry.migrate_payload` runs on the raw payload before any deserializer (order: §3a) and turns a pipe's `properties["Phase"]` text into the sparse `"phase"` id, rule owned by [`project-phasing.md`](project-phasing.md) D-PH6; 12 since the notes run: below it, `schematic_scene.migrate_old_schematics` turns old schematics Printed at the end of load, once per file, notes design N13; 11 since HF1 — **version-gated**: `colour_migration.migrate_project_payload`
runs on the raw payload before any `from_dict` when `version < 11`, converting legacy default colours to
`token:auto`; `.fpdb` files carry a `colour_tokens: 1` marker instead of a version — rules owned by
[`hatch-and-fill.md` "HF1 build design"](hatch-and-fill.md). The 2D-shape `fill` record (UP1 two layers) adds **no** version bump or marker — a single read-time reader normalises the legacy record, see [`2026-10-18-up1-two-layer-fill-design.md`](../superpowers/specs/2026-10-18-up1-two-layer-fill-design.md) D1. 10 since LT2 was informational; primitive migration is
key-presence driven; the weight table + aliases install at open, see §3a and [`linetypes.md`](linetypes.md) "LT2" H-a / H-g) and `project_info`, `scale`, `display_settings`,
`paper_display`, `levels`, `plan_views`, `active_level`, and the entity
collections: `nodes`, `pipes`, `annotations` (dimensions + notes), `underlays`,
`water_supply`, `design_areas`, the construction-geometry keys (`polylines`,
`draw_lines`, `reference_lines`, `draw_rectangles`, `draw_circles`, `draw_arcs`,
`draw_ellipses`, `draw_splines`, `polygons`, `filled_regions` — HF3, record owned by
[`hatch-and-fill.md`](hatch-and-fill.md) "HF3 build design"), `texts` (unified `TextItem`
primitives, containment C5), `gridlines`, `walls`,
`floor_slabs`, `roofs`, `rooms`, `block_definitions` (embedded by id),
`blocks` (instances referencing definition ids), `constraints` (plan-controller records on walls + gridlines, referenced by uid -- Editor/Build slice 2, design §2 Persistence; additive key, no `SAVE_VERSION` bump), `detail_views`, `sheets`, `titleblock_template`.

Each `sheets` entry may carry an additive `"linked_document"` key (written only when the sheet links
a document; no `SAVE_VERSION` bump; project-file path only, sheets are not in the undo snapshot). It
holds the link record including the base64 one-page PDF copy (`snapshot_pdf`).
`save_to_file` rewrites its `path` relative to the project folder on the saved copy, like underlays,
and `load_from_file` makes it absolute again. Record and path rule owned by the
[sheet-linked-document design](../superpowers/specs/2026-11-09-sheet-linked-document-design.md)
(Data model, D2).

Each `block_definitions` entry carries an additive `"kind"` key (written for schematics
only, omitted for plain blocks) on both serialization paths (project file and undo
snapshot) — see `schematics.md` Input / Output.

Two additive keys for gridline-hosted blocks (no `SAVE_VERSION` bump; record owned by `block-system.md`
"Gridline-hosted instances"): each `gridlines` entry carries `"uid"` (a file without one gets a fresh uid on
load), and a `blocks` entry carries `"host"` only when hosted. Both serialization paths round-trip them.
On project load a `blocks` record whose host gridline does not resolve (or is malformed) is **dropped**, and
the load status appends " -- dropped N hosted block(s) whose gridline is missing".

SB2b Marks adds these additive keys (no `SAVE_VERSION` bump; meaning owned by
[`element-parameters.md`](element-parameters.md) "Marks (SB2b)", dialog size by
[`settings-dialog.md`](settings-dialog.md) §4.2):
top-level `mark_patterns` (category -> pattern; a load keeps only str -> str entries over the defaults, so a
corrupt value falls back to them) and `project_settings_size` (`[w, h]` or null; a load accepts only two
positive finite numbers below 100000, else None); each `levels` entry carries `number`; `walls`, nested
wall openings and `rooms` carry `mark` (a room file with no `mark` reads the legacy `tag`; save writes
`mark` only); a pipe's `properties` map and a node's `sprinkler` record carry `"Mark"`. A level list with no `number` key
anywhere (an old file) is numbered by elevation on load.
The room-detection rework adds one more additive key (no `SAVE_VERSION` bump), on the file and the undo-snapshot
paths alike: `rooms[].holes`, a list of rings (each a list of `[x, y]`; the island rings a room surrounds,
record contract in [`wall-room-floor-system.md`](wall-room-floor-system.md) section 12.3). It is written only
when the room has holes; an absent key loads as no holes, so an old file loads and re-saves unchanged.
SB3b / L283 add two more additive keys (no `SAVE_VERSION` bump), both on the file and the undo-snapshot
paths: `rooms[].tag_block` (the room's own tag block id; written only when set, meaning owned by
[`system-blocks.md`](system-blocks.md) section 8) and `display_overrides` on `walls` (and their nested
`openings`), `rooms` and `roofs` -- written only when non-empty, from the one mixin helper
(`displayable_item.display_overrides_to_dict`). `floor_slabs`, `gridlines` and the network records
(nodes, pipes, water supply) already carried it. A stored Hide (`visible: false`) is re-applied on load
and paste. Meaning of the overrides: [`display-system.md`](../architecture/display-system.md).
The undo snapshot carries the same Marks data through the same `to_dict` / codec paths, and now also the
level list (`levels`), `plan_views`, `active_level` and per-underlay `underlay_levels`;
network_codec's load and undo paths add pipes and sprinklers with `mint=False`, so neither re-mints a Mark.
PH1 project phasing (SAVE_VERSION 13) adds a top-level `phases` key (the project status registry,
`phase_registry.to_list()`) and a sparse `"phase"` status id, written only when not New, on `walls`
(and their nested `openings`), `floor_slabs` (and their nested openings), `roofs`, `rooms`, `pipes`,
`water_supply`, `blocks` and `underlays`. A pipe's `properties` map no longer carries `"Phase"`, and a
node's `sprinkler` record drops its Phase row: the node entry carries a sparse `sprinkler_phase` instead,
plus a sparse `fitting_phase_override` beside `fitting_display_overrides`. The undo snapshot carries
the element keys through the same `to_dict` / `network_codec` paths; the `phases` registry and
underlays are file-path only (underlays are never in the undo snapshot). Meaning of the ids and the override:
[`project-phasing.md`](project-phasing.md) D-PH3, D-PH4.

The tables' keys (`display_settings`, `paper_display`, `fill_types`, `materials`, `phases`) are
assembled by `project_tables.tables_for_save()`, see §3a.

**Backups and atomic write** (`project_backup.py`): a Save first copies the existing file to
`Backups/<stem> <YYYY-MM-DD HHMMSS><ext>` beside it, keeping the newest `PROJECT_BACKUP_KEEP` per
project. A failed backup fails the Save: nothing is overwritten without one. The payload is written
to `<name>.tmp`, flushed and fsynced, then moved over the target with `os.replace`, so the original
survives any failure. Autosave passes `backup=False`.

**Content-loss warning:** before a Save or Save As, `MainWindow._confirm_content_loss` asks for
confirmation when the target holds at least `CONTENT_LOSS_MIN_ITEMS` model items and the scene holds
under half of them; Cancel leaves the file alone. Autosave never asks. `save_file` and `save_file_as`
return a bool, so a cancelled or failed save also stops a Close.

### §3 — Load

`load_from_file` reads `version` (default 1), migrates the raw payload, calls `_clear_scene()`,
installs the project tables, then restores each section. The order of the table steps (migrate,
install, holder retarget, undo baseline, styles) is owned by §3a and not restated here. Node ids are temp integers assigned at save and
rehydrated into a `id → Node` map that pipes/design-areas reference. Constraints
reference geometry by index into the same ordered `_all_geometry_items()` list.
Load is **best-effort on migrations** (title-block field migration failures log
and continue; missing underlay files warn via `themed_warn` but do not abort).

`_clear_scene` drops section and detail markers through their managers before `self.clear()`, so no
manager keeps a wrapper the clear deletes.

**Failure contract:** `load_from_file` returns False for a file it cannot open or parse, before
`_clear_scene`, so the open project stays open; it returns True when it finishes.
`MainWindow._load_project` claims `_current_file` only after a finished load. `_guarded_load` reports
a failure. An exception mid-restore leaves a partial scene: it is logged, `_current_file` is cleared
and `_detached_name` is set (title `Untitled (<name> failed to load)`), so Save asks for a new name.
While `_detached_name` is set, autosave and Close leave the recovery file alone. Crash recovery runs
the same guard and keeps its file when it fails.

### §3a — Project tables

**Project tables** ([`GLOSSARY.md`](../../GLOSSARY.md)) are the line weights and rename aliases,
fill types, materials, phases, Display Manager (DM) rows and paper categories.
`firepro3d/project_tables.py` owns the order in which they are migrated, installed, finished and
saved; callers (`scene_io`, `main`) make a fixed series of calls into it and do not know the order.
What each table is, and why it is migrated, stays with its own spec:
[`linetypes.md`](linetypes.md) (LT2 install, H-g aliases, LW-DC-8 / LW-DC-9),
[`hatch-and-fill.md`](hatch-and-fill.md) (D-A20 colour tokens),
[`project-phasing.md`](project-phasing.md) (D-PH6 ids, D-PH11 template overlay),
[`materials.md`](materials.md).

**Entry point 1 — from a file** (`load_from_file`; reached by `MainWindow._apply_loaded_file` for
File→Open and crash recovery). The order:

1. `project_tables.migrate_payload(payload)` on the raw payload, before `_clear_scene`: HF1 colour
   tokens (D-A20), then phase ids (D-PH6). A parse failure returns False before this, so the open
   project stays (§3).
2. `_clear_scene()`, then `project_tables.begin_load(payload)` returns a `LoadSession`. It installs
   the weights and aliases first, before any definition or text parse canonicalises a name
   (LT2-8 / H-g), then the fill types, materials and phases, before any element resolves an id.
3. The scene build. The underlay loop reads `session.underlay_map`.
4. `session.migrate_holders(scene)`, before `push_undo_state` (the undo baseline).
5. `session.apply_styles(scene)` as the last step: the DM rows, then the paper categories.

**Entry point 2 — fresh** (New and startup, both in `main.py`): `project_tables.start_fresh(scene)`
resets the fill types, materials and phases to their seeds, applies the DM defaults, resets the
project line weights (a copy of the app weight table from QSettings, factory fallback; clears the
aliases), then calls `settings.template.apply_template_settings(scene)`, which overlays the
template's phases (D-PH11). Startup and New do not clone the template (`clone_template_into` is not
wired, see [`settings-dialog.md`](settings-dialog.md) §4.5).

**Entry point 3 — save** (`save_to_file`): `project_tables.tables_for_save()` returns
`display_settings`, `paper_display`, `fill_types`, `materials`, `phases`, in that file order,
spliced into the payload at the same position (the saved bytes did not change).

**`LoadSession` contract** (one open's table state from `begin_load` to the end of
`load_from_file`; it replaces the old module-global weight stash and the scene's stashed
`display_settings` / `paper_display`):

- Fields: `display_settings` and `paper_display` (the file's payload dicts, or None) and
  `weight_kind`, the pending LW-DC-8 migration kind (`"table"`, `"tableless"` or None) that
  `paper_display.apply_project_weights(..., stash=True)` returns.
- `underlay_map` is the LW-DC-8 old-name to new-name map for underlay payloads. It is computed on
  first read, after the block-library merge, then cached, so rows the merge adds survive; it is
  never computed when the session is built.
- `migrate_holders(scene)` retargets every by-name weight holder, installs the migrated table and
  fixes the session's payload dicts in place. It runs before the undo baseline (the migration sits
  outside undo) and is idempotent: it clears `weight_kind`, so a second call does nothing.
- `apply_styles(scene)` runs last: the file's `display_settings` if it has any, else the QSettings
  fallback `apply_saved_display_settings`; then `apply_paper_display_from_project`.

So `load_from_file` returns a fully styled scene to every caller. `MainWindow._apply_loaded_file`
keeps only `_refresh_weight_canvases` (the window re-pen). The other callers are
`settings/template.py` `clone_template_into` (test-only today) and `tools/perf_probe_underlay.py`;
a tool or probe that calls `load_from_file` now writes real QSettings (DM rows, paper categories)
unless it isolates settings. Follow-up filed in `todo_open.md`: "`tools/perf_probe_underlay.py`
loads a project with no settings isolation…".

**Internal-seams rule.** Each table module keeps its own storage. Its load / migrate / reset / save
functions are seams that only `project_tables` calls on the open, new, startup and save paths; no
other module sequences them. The legitimate other callers are:

- the undo restore in `model_space` (`apply_saved_display_settings`); out of scope here, filed as
  the `todo_open.md` bug "A model Ctrl+Z flips Display Manager category settings…";
- the Display Manager dialog's live re-apply in `main.py`;
- `paper_display`'s own second `apply_project_weights` (inside `apply_paper_display_from_project`);
- `settings/template.py`: the phase overlay in `apply_template_settings` and the save-as-template
  `phase_registry.to_list()`.

The QSettings-side migrations (`paper_display.migrate_settings_weights`, run lazily on the first
`load_line_weights` read; `display_manager._migrate_display_keys`) are not part of this order.

**QSettings-backed stores.** The DM rows and paper categories are live QSettings-backed stores,
not project-scoped: open writes the file's rows there and save reads them back, and a file with no
`display_settings` inherits the previous project's DM rows through the fallback. Kept as-is by
ruling; filed as the `todo_open.md` bug "Paper categories use QSettings as the live store --
opening a project overwrites the new-project template, and New doesn't reset" (a second occurrence
there covers the DM rows).

### §4 — Legacy migrations (load-only)

Load silently accommodates older files: the pre-2026 `construction_lines` key is
dropped; a legacy `HatchItem` (`hatches`) block is no longer migrated — it is
clean-dropped (§5; the polyline-recreating migration was retired under C8);
title-block address keys are migrated one-way. These are
load-only — save never writes the legacy shapes.

### §5 — Clean-drop invariant (containment C8 — built)

Under containment contract [C1/C8](model-space-containment-contract.md), Model
Space is placement-only. The format contract enforces a **clean-drop
invariant**:

- **Forbidden content is read-but-discarded, silently.** On load, the payload
  keys for loose geometry (`polylines`, `draw_lines`, `reference_lines`,
  `draw_rectangles`, `draw_circles`, `draw_arcs`, `draw_ellipses`,
  `draw_splines`, `polygons`, `filled_regions` — HF3, dropped by the same rule), the top-level `texts` key (**standalone model
  text** — C1 retires it; block-content text lives in `block_definitions` and
  paper text in `sheets`, both of which survive), the `note` and `dimension`
  entries in `annotations`, and any legacy hatch are
  **not reconstructed**; the `constraints` block is adopted only for records whose refs all resolve to a loaded wall / gridline uid -- unresolvable or malformed records are dropped into the same clean-drop count (Editor/Build slice 2, design §2 Persistence). A single `logging` line records dropped counts; there
  is **no UI**.
- **Save stops writing them**, so a load→save of a legacy file cleanly sheds the
  forbidden content.
- **Clean-drop is FILE-path only.** The undo path (`_capture_network` /
  `_restore_network`) is *shared* with the Block-Editor scratchpad (a
  `scene_role="block_editor"` `Model_Space`, which legitimately authors loose
  geometry + text), so it **retains** loose-geometry/text capture — the Block
  Editor needs authoring undo. This is a deliberate asymmetry to §1: in a **plan**
  scene the loose-geometry/text/dimension collectors are always empty (the C1
  authoring gate refuses those modes, and load clean-drops legacy content), so
  the retained undo capture never reintroduces forbidden content into a project.
  Dimensions are retired entirely (not a block primitive), so no scene captures them.
  The 2D geometry and text `display_overrides` (L283) ride this retained Block-Editor undo
  capture only -- a plan scene never writes them to the file (that content is clean-dropped).
- **Unaffected:** `block_definitions`, `blocks` (instances), `underlays`,
  `walls`/`rooms`/`floor_slabs`/`roofs`, `gridlines`, `nodes`/`pipes`, `sheets`
  (paper annotations, incl. the unified Text), `levels`, and all view/scale
  metadata persist normally.

## Acceptance Criteria
- [x] Save→load round-trips every surviving entity collection; the
      `Backups` copy and atomic write hold.
- [x] Re-opening a project restores every detail view, and a project with none leaves no dead markers.
- [x] A failed load shows an error and never reaches the file: a parse failure keeps the open project,
      and a mid-restore failure detaches the partial scene from any file.
- [x] Saving under half of a file of `CONTENT_LOSS_MIN_ITEMS` or more warns, and Cancel leaves it intact.
- [x] (C8) A legacy `.fpd` with loose geometry / model text / notes / dimensions /
      constraints / hatch loads with those discarded, no exceptions, counts
      logged; a re-save omits them (plan wall / gridline constraints whose refs resolve are the slice-2 exception and are kept).
- [x] (C8) Clean-drop is FILE-path only; the undo path retains loose-geometry/text
      capture for the Block-Editor scratchpad (§5) — plan scenes are empty via the
      gate so nothing is reintroduced.

## Verification Checklist
- [x] Format claims match `scene_io.py` at the stamped commit.
- [x] §1 dual-path invariant honoured, with the deliberate file-vs-undo asymmetry
      documented in §5 (clean-drop is file-path only).
- [x] Rule A: Z-order/level/units facts are linked to their owning specs, not
      restated here.

## Divergences ledger

| # | Target (§5) | Status | Closed |
|---|---|---|---|
| S1 | Forbidden content read-but-discarded on load; save omits it | **CLOSED** — authoring gate + silent clean-drop landed in the C1/C8 slice (`scene_io.py`); undo path retains loose-geometry capture for the Block-Editor scratchpad (file-vs-undo asymmetry, §5) | C1/C8 slice |
