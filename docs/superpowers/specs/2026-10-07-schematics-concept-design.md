---
status: proposal          # concept ratified 2026-10-07 (grill Q1–Q18 + brainstorm SD1–SD11); SV1 built 2026-10-08; SV2–SV4 unbuilt
last-verified: 2026-10-08  # SV1 Account (SD1/SD4/SD5 SV1 halves match the code)
verified-commit: b851b1aa   # prior 7f97f687
applies-to:
  - firepro3d/block_definition.py
  - firepro3d/block_editor.py
  - firepro3d/block_library.py
  - firepro3d/block_registry.py
  - firepro3d/block_manager.py
  - firepro3d/blocks_browser.py
  - firepro3d/block_open_dialog.py
  - firepro3d/app_data.py
  - firepro3d/project_browser.py
  - firepro3d/paper_space.py
  - firepro3d/paper_display.py
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/scene_io.py
  - firepro3d/settings/panes.py
  - main.py
  # new: schematic_scene.py
source-tasks: ["Schematic views concept — block-like definition authored in a Schematic Editor, stored project or system, placed on sheets only as a viewport; SV1…SVn series (2026-10-07)"]
---

# Schematics — Concept Design

> **Rule A.** The *what* — decisions D-S1…D-S18 — is owned by
> [`docs/specs/schematics.md`](../../specs/schematics.md) "Design Decisions".
> This doc owns the *how* (SD1–SD11) and the build slices SV1–SV4; it cites
> D-S ids rather than restating them. Promote into `schematics.md` (and the
> specs in its reconciliation list) as each slice lands.

## Goal

Deliver schematics (D-S1) on top of the shipped block registry, Block Editor,
block library and sheet-view pipeline, adding exactly one new mechanism — an
off-screen **render scene** per placed schematic — and generalizing the few
seams that today hard-code "plan | elevation | detail" or "tile or repeat".

## Motivation

See `schematics.md` Motivation. The 2026-10-07 reuse sweep found the viewport
layer, drop gesture, undo, PDF export, paper pens, editor, and library all
reusable as-is; the only true gaps are the render scene, the schematics folder
root, a project-vs-template save destination, and browser verbs.

## Architecture & Constraints (reuse map — 1b sweep, verdicts re-checked)

| Area | Verdict | Mechanism reused / changed |
|---|---|---|
| `SheetViewData` / `SheetViewport` paint, crop, resize, undo commands, PDF / print | REUSE AS-IS | `source_view_type` is a free string; `_resolve_level_context` returns `None` for unknown types so isolation is skipped; `render_sheet` → temp `PaperScene` → `dispose()` |
| `MIME_VIEW` + `PaperGraphicsView.dropEvent` | REUSE AS-IS | payload `{view_type, view_name}`; dialog + fit-to-sheet generic |
| `apply_paper_overrides` / `_category_for_item` | REUSE AS-IS | per item on any scene → D-S12 Blocks / Construction split for free |
| `BlockEditorWidget` / `BlockEditorManager` | REUSE + kind flag | one tab per definition keyed by id; seeding, Save, undo, import kind-agnostic |
| `block_library.*` | REUSE AS-IS | every function takes `root=` |
| `BlockRegistry.users_of` / `referenced_ids` / `bundle_for` | REUSE AS-IS | nested-usage delete refusal (D-S11b) and template bundling (D-S11c) already exist |
| `ViewResolver.resolve` / `available_views` | GENERALIZE | schematic branch; the elevation kind is the non-model-scene precedent |
| `BlockDefinition` | GENERALIZE | additive `kind` (refusal: `capabilities.place_refusal` wraps the LT5 `capability_place_reason` — SD1) |
| `BlockSaveDialog`, `BlockOpenDialog`, `library_tree_for` | GENERALIZE | kind-aware title / tiers / root |
| Project Browser roles, `_MS_STUBS`, `mimeData`, `set_placed_views`, `_on_item_activated` | GENERALIZE | real `schematic` role |
| `main.py` `isinstance(BlockEditorWidget)` branches, `_close_stale_view_tabs`, `_navigate_to_source_view` | GENERALIZE | schematic prefix / branch |
| `block_library._series_dir` | GENERALIZE | skip an empty tier (one-tier Series layout, D-S15) — **P4 probe first** |
| `BlockEditorWidget.seed_from_dicts` | GENERALIZE | promote the materializer to a scene-level helper (editor + render scene = two callers) |
| Render scene per schematic | GAP | `SchematicSceneManager` (new `schematic_scene.py`) |
| `app_data.schematics_dir()` + settings key + migration | GAP | mirrors `linetypes_dir()` |
| Project-vs-template save destination | GAP | "Also save as Template" toggle + verb |
| Browser New / Rename / Duplicate / Delete / Save as Template verbs | GAP | none exist for any view today |

Constraints carried from the governing specs: Block Editor = scratchpad
`Model_Space` that never mutates the project except through
`commit_block_definition` (block-system.md); paper undo is a `QUndoStack`
(paper-space.md §4.12); the browser is pure-push, signals carry names/ids not
objects (project-browser.md); both serialization paths carry every new field
(scene-io.md).

## Design Decisions (the how — ratified in the 2026-10-07 brainstorm, groups A–C)

### SD1 — Kind flag (D-S3, D-S4)

- `BlockDefinition.kind: str = "block"`; `"schematic"` for schematics.
  `to_dict` writes `"kind"` **only when not `"block"`** (the LT5 `end`
  byte-identical precedent); `from_dict` defaults it. `to_dict`/`from_dict` is
  the one serializer behind `.fpd` `block_definitions`, `.fpdb` and the
  `_capture_network` undo path, so both serialization paths carry it;
  `index.json` gains it in SV3.
- **Refusal home (SV1 delta, ratified 2026-10-08 — supersedes the
  `never_placed` property).** LT5 already made
  `capabilities.capability_place_reason(defn)` the one "can't be placed"
  function, called by all four placement sites (`Model_Space.set_mode`,
  `_press_place_block`, the paste `block_instance` branch,
  `Model_View._resolve_block_drag`); the editor's drop and paste nesting reach
  the same functions. SV1 adds `capabilities.place_refusal(defn)` →
  `block_library.SCHEMATIC_REASON` when `kind == "schematic"`, else
  `capability_place_reason(defn)`; the four sites switch to it.
  `capability_place_reason` keeps its capability-only meaning.
- `commit_block_definition(..., kind=)` stores it; Save As keeps it (the
  capability precedent). `symbol_use_refusal` logic is untouched — a schematic
  simply never reaches a placement.
- **Identity (D-S15):** a schematic's `library` is `""`, `series` optional,
  name unique among schematics within its series. `set_block_metadata` and the
  Save validator apply this rule when `kind == "schematic"`; block rules are
  unchanged.
- Listing filters: Blocks browser (`_grouped`, which Insert focuses),
  `BlockOpenDialog` project root, the Save Block dialog's `library_tree_for`,
  and `library_only_entries` (SV3, once templates exist) exclude
  `kind == "schematic"`. The Block Manager **hides** schematics until SV4 adds
  its **Kind** column + filter (with the library verbs disabled for schematic
  rows).

### SD2 — Render source: materialized render scene (D-S10, D-S12)

Approaches weighed: (1) **materialized off-screen scene** per schematic —
chosen; (2) one `BlockInstance` wrapper in a private scene — cheapest but
everything plots as "Blocks", contradicting D-S12; (3) the open editor scene —
exists only while the tab is open, PDF export needs (1) regardless.

- New `schematic_scene.py`: `SchematicSceneManager(project_scene)` with
  `scene_for(block_id) -> Model_Space`, `invalidate(block_id)`,
  `dispose(block_id)`, `dispose_all()`.
- Each render scene is a `Model_Space(scene_role="block_editor")` that borrows
  the project registry (`borrow_block_registry`, the editor's pattern) and is
  **materialized** from the definition's primitives by the promoted helper
  `materialize_primitives(scene, prim_dicts)` (today the body of
  `BlockEditorWidget.seed_from_dicts`; the editor becomes a caller). Nested
  `block_instance` records become real `BlockInstance`s, primitives real items,
  text real `TextItem`s — so `apply_paper_overrides` and paper-fixed text sizing
  behave exactly as inside a plan viewport.
- Built lazily on first `resolve`; rebuilt when the definition's `version`
  changes (hook on `BlockRegistry.invalidate` and on `blockDefinitionsChanged`);
  disposed on definition delete, project load / new file, and
  `MainWindow` teardown. The scene's `changed` signal is what `SheetViewport`
  already subscribes to, so viewports dirty themselves on rebuild.
- Lifetime rule: render scenes outlive every `PaperScene` (including the
  temporary export scene) — `dispose()` of a `PaperScene` disconnects its
  viewport subscriptions, never the render scene.
- `scene._hatch_paper_scale` is declared `None` on the render scene (the
  `PaperScene` precedent) so the override pass has a declared slot.

### SD3 — Resolver & viewport (D-S7, D-S8, D-S10)

- `ViewResolver.__init__` gains `schematic_scenes` (the manager); both
  construction sites in `main.py` pass it.
- `resolve("schematic", block_id)` → `(render_scene, extent)` where `extent =
  scene.itemsBoundingRect()`, falling back to the plan / elevation default rect
  when empty. `available_views` adds a "Schematics" group of display names.
- `source_view_name` holds the **definition id**; `SheetViewport` resolves the
  display name for the title bubble at paint (`definition.name`) so Rename
  needs no sheet migration.
- `_effective_crop`: the schematic kind takes the **detail** branch shape (live
  extent each paint) rather than the frozen plan `crop_rect` — D-S10 live crop.
  Grips are inert like details; the user resizes the NTS box or picks a scale.
- `PaperGraphicsView.dropEvent`: for `view_type == "schematic"` the properties
  dialog opens with scale preset **NTS**; the initial box is the extent at
  1 mm = 1 mm clamped to the sheet (the existing clamp).
- Context menu for schematic viewports: Go to View, Delete. `navigate_requested`
  → `main._navigate_to_source_view` schematic branch →
  `block_editor_manager.edit_definition(id)` (D-S10 non-navigable).
- `_compute_scale_field` already yields NTS / AS NOTED; no change.

### SV2 delta (ratified 2026-10-08 — /todo SV2 Phase 2 FP1 + Phase 3 FP3)

Supersedes the SD2 / SD3 bullets it contradicts (the "grips inert" vs "resize
the NTS box" clash; the deferred rebuild; `definition.name` always painted).

- **Rebuild in place.** A render scene is one long-lived `Model_Space` per
  schematic id. On a change the manager clears the materialized items (tracked
  primitive lists + `remove_block_instance`) and re-materializes into the
  **same** scene, so viewport references and `changed` subscriptions survive
  and `changed` drives the repaint. Cache key `(id(defn), defn.version)` —
  project undo restores **new** definition objects.
- **Never rebuild during paint.** Rebuild runs only in the manager's
  `blockDefinitionsChanged` handler or synchronously inside `resolve()`
  (reconnect / drop / export — never mid-paint), so PDF export always sees the
  current definition and no deferred-rebuild machinery exists. Paint-time
  `_effective_crop` reads the cached extent (`ViewResolver.schematic_extent`).
- **Extent** = `geometry_import.geometric_bounds` over the materialized
  primitives minus scaffolding (the editor-fit bound: no origin cross, no pen
  slop); empty → the 1000×1000 default rect.
- **Rename repaint.** On `blockDefinitionsChanged` the manager `update()`s
  every live render scene (viewports repaint the live title) and disposes
  scenes whose id vanished or is no longer a schematic.
- **Materializer home.** `schematic_scene.py` owns `_CLS_TO_LIST` (moved from
  `block_editor`, re-imported there), `add_primitive(scene, item)` and
  `materialize_primitives(scene, dicts)`; `BlockEditorWidget._add_primitive` /
  `seed_from_dicts` delegate (one materializer, two callers).
- **Ownership.** `MainWindow` builds one `SchematicSceneManager(self.scene)`;
  both `ViewResolver` sites pass it; `dispose_all()` on load, new file and
  `closeEvent`; disposal detaches each scene from the registry.
- **Sheet usage.** `Model_Space.schematic_sheet_users(id)` scans
  `self._sheets` → sheet numbers; `delete_block_definition` refuses when
  non-empty; `block_users_message` adds "used on sheets 2, 5 — remove its
  viewports first".
- **Viewport rules (schematics.md D-S10 SV2 delta).** Live-crop predicate
  covers detail + schematic (no persisted crop). Title = stored `title` if
  non-empty, else the live `definition.name`; the drop dialog shows the name
  as placeholder text with an empty field and defaults the scale to NTS.
  Resize handles only at NTS (scaled: box = extent × scale, no handles). On a
  definition change an NTS box keeps its size (content re-fits); a scaled box
  recomputes extent × scale, top-left anchored.

### SD4 — Project Browser (D-S4, D-S8, D-S15, D-S16)

- Role `"schematic"` added to `_ROLE_TYPE`; the Schematics root leaves
  `_MS_STUBS` and gets its own role `"schematic_root"` so `_on_item_activated`
  stops routing it to the plan. Series rows are plain parents (no role action).
- `refresh_schematics(rows)` with `rows = [(id, name, series)]` — wholesale
  rebuild (`takeChildren` + repopulate), italics from `_placed_views` keyed
  `("schematic", id)`; `set_placed_views` adds the root to its tuple.
- Signals: `createSchematic()`, `activateSchematic(id)`, `renameSchematic(id)`,
  `duplicateSchematic(id)`, `deleteSchematic(id)`, `saveSchematicTemplate(id)`.
  `MainWindow` owns every dialog / confirm and pushes state back (pure push).
- `mimeData`: role `"schematic"` → `MIME_VIEW` `{"view_type": "schematic",
  "view_name": id}` — **SV2** (with the resolver; SV1 leaves are not
  draggable, so a drop can never make a "View not found" viewport — SV1
  delta, ratified 2026-10-08). Placed italics are SV2 likewise.
- `MainWindow` pushes `refresh_schematics` on load, new file,
  `blockDefinitionsChanged`, and after each verb; `_recompute_placed_views`
  scans `source_view_type == "schematic"`.

### SD5 — Editor (D-S9, D-S14, D-S17)

- `BlockEditorManager.open_new(kind="block")` and `open_for_definition` read
  the kind; the widget stores `self.kind`. Tab title prefix `"Schematic: "`;
  `_close_stale_view_tabs` sweeps that prefix too (today Block Editor tabs are
  not swept — a schematic tab bound to a project definition must be).
- Capability toggles (three since LT5: pattern tile / linetype / end type):
  `_sync_capability_buttons` disables the three ribbon buttons with a tooltip
  in a Schematic tab, `capability_rows` omits the capability section from the
  property panel, and `toggle_capability` refuses as the backstop.
- Silent re-save of a schematic never calls `_save_to_library` (the block
  library is never its home, D-S5).
- Delete from the browser closes that schematic's open editor tab (one
  confirm covers both); Rename re-titles it.
- `BlockSaveDialog(kind=)`: title "Save Schematic", Series selector only
  (`library_tree_for(root=schematics_dir(), tiers=1)`), "Also save as Template"
  toggle (QSettings `BlockEditor/save_schematic_template`). Save → project
  (`commit_block_definition`, one undo); Save as Template → `save_to_library(
  defn, root=schematics_dir())` with bundling and the Overwrite / Rename /
  Cancel collision dialog.
- Rename / Duplicate from the browser reuse `set_block_metadata` (rename) and
  the Block Manager's clone path (duplicate → new id, `kind` kept), each one
  project undo step.

### SD6 — New Schematic dialog (D-S9)

- Reuse `BlockOpenDialog`'s shape with `root=schematics_dir()`, a first row
  **Blank schematic**, and the Series tree of templates beneath. Result →
  `open_new(kind="schematic")` or `load_blocks_from_files([path])` (one undo,
  adopts bundled blocks) then `edit_definition(id)`.
- This is a new dialog surface: **mockup gate** (live render under the app QSS
  + font, Qt constraints named) before the SV3 build; "reconfigured
  `BlockOpenDialog`" is option 1 of that gate.

### SD7 — Library root & migration (D-S5, D-S15)

- `app_data.SCHEMATIC_DIR_KEY = "paths/schematic_dir"`; `schematics_dir()`
  mirrors `linetypes_dir()` (configured dir, else
  `<user_data_root>/schematics`, created on demand); `_MIGRATABLE +=
  ("schematics",)`; System Settings gains the path row next to the hatch /
  linetype folders.
- One-tier layout `<schematics>/<Series>/<name>.fpdb`: `_series_dir` (and the
  callers that build a `(library, series)` pair) skip an empty tier. **P4
  probe = SV3 first step:** confirm `sanitize("")` / `os.path.join` behaviour
  and `_iter_index_entries` with a one-level tree before writing the slice.
- `index.json` entries carry `kind`; `capability_folder.FLAGS` is untouched
  (schematics are not capabilities; the schematics folder is never scanned by
  the pattern / linetype pickers).

### SD8 — Delete refusals (D-S11a, D-S11b)

- `delete_block_definition` adds a sheet-usage check: `SheetManager` scan for
  viewports with `source_view_type == "schematic"` and `source_view_name ==
  block_id`; `block_users_message` gains "used on sheets 2, 5". Nested usage is
  the shipped `users_of` refusal — the message already names the user
  definitions.
- Block Manager "Used in" lists schematics by name (they are definitions in
  the same registry; only the column filter changes).

### SD9 — Paper display (D-S12)

No change: `_category_for_item` maps nested `BlockInstance` → Blocks, raw
primitives → Construction, `TextItem` → its branch. Selection accent never
plots (LT1 rule). `restore_model_display` restores the render scene like any
source scene.

### SD10 — Spec homes & reconciliation

`docs/specs/schematics.md` (what; `SPEC-INDEX.md` row) + this doc (how).
Reconciliation pointers are enumerated in `schematics.md` "Cross-spec
reconciliation" and applied at each slice's Account; the P1 "Paper-space block
placement" task and SB7's host note are amended at SV1's filing.

### SD11 — Build slices

| Slice | Content | Guards | Depends |
|---|---|---|---|
| **SV1** (built 2026-10-08) | SD1 kind flag + `place_refusal` + `SCHEMATIC_REASON` at all sites; SD5 editor (kind, title, capability lock, Save Schematic → project); SD4 browser root / role / leaves / verbs Open / Rename / Delete / New (blank only), leaves not draggable; `.fpd` + undo persistence; listing filters (Block Manager hidden); `_close_stale_view_tabs` prefix | G1 (project half), G2, G6 (SV1 half) | — |
| **SV2** | SD2 `SchematicSceneManager` + promoted materializer; SD3 resolver branch, drop NTS default, live crop, title bubble name lookup, Go-to-view, placed italics; SD4 leaf drag (`mimeData`); SD8 "used on sheets" refusal; PDF | G1 (sheet half), G3, G5, G6 (SV2 half) | SV1 |
| **SV3** | SD7 `schematics_dir` + settings row + migration + one-tier `_series_dir` (P4 probe first); SD5 Save as Template (bundling, collision) + browser verb; SD6 New-from-template dialog (**mockup gate**) | G4 | SV1 (editor), SV2 for the placed-template smoke |
| **SV4** | Block Manager Kind column / filter + Used-in; Duplicate verb; `available_views` Schematics group; spec Account (`schematics.md` → partial/current, reconciliation pointers, SPEC-INDEX) | keep-green only | SV2 |

SV1 → SV2 → SV3 sequential; SV4 after SV2 (∥ SV3).

## Acceptance Criteria

- [ ] `schematics.md` acceptance criteria.
- [ ] One render path serves on-screen sheet preview and PDF export (SD2).
- [ ] No duplicated materializer: the editor and the render scene share one
      helper (SD2).
- [ ] No fifth ad-hoc refusal check: `capabilities.place_refusal` is the single function
      (SD1).

## Verification Checklist (guards — VC3: real path, observable ground truth)

- **G1 Round trip** — real `MainWindow`: New Schematic (blank) → draw a line +
  nest a shipped block → Save → place on a sheet → save `.fpd` → reopen: the
  Schematics tree lists it (role + name), `block_definitions` holds
  `kind == "schematic"` with equal primitives, the sheet viewport resolves and
  `scene.render` of the sheet produces non-background pixels inside the
  viewport box; Ctrl+Z after Save is one project step; viewport delete is one
  paper step.
- **G2 Refusals** — drop (`_resolve_block_drag`), `set_mode` Insert, paste, and
  editor nesting of a schematic each leave the scene unchanged and surface
  `SCHEMATIC_REASON`; a plain block at the same sites still places.
- **G3 Viewport** — drop a schematic → `scale == 0`, box = extent clamped; edit
  the definition (grow it) + Save → every viewport of it re-fits (extent
  compared); `paper_export.export_pdf` of the sheet yields a PDF whose vector
  strokes include the schematic's line (parsed), nested block plotted at the
  Blocks row weight and the raw line at the Construction weight; title text
  reads `NTS`.
- **G4 Library** — Save as Template writes `<schematics>/<Series>/<name>.fpdb`
  (bundled nested ids present) + `index.json` with `kind`; New → From template
  on a fresh project loads a project copy (one undo, adopted block present);
  re-save shows Overwrite / Rename / Cancel; `paths/schematic_dir` override
  redirects both; the folder migrates with `_MIGRATABLE`.
- **G5 Delete** — delete a placed schematic → refused, message names the sheet
  numbers; after removing the viewports → allowed, render scene disposed;
  delete a block nested in a schematic → refused naming the schematic.
- **G6 Browser** — *SV1 half:* Schematics root has its own role (double-click
  no longer activates the plan); double-click a leaf opens its seeded
  `Schematic:` tab; a leaf's `mimeData` is empty; hidden from the Blocks browser
  / Insert / Open block roots / Save Block library tree / Block Manager; Rename
  re-titles the open editor tab (one undo); Delete removes the leaf and closes
  the tab. *SV2 half:* leaf drag emits `MIME_VIEW` `{schematic, id}`; placed
  italics follow sheet placement; Rename re-titles the viewport title.

**Keep-green (registry / enumerator tests, from the 1b sweep):**
`test_project_browser_3d`, `test_project_browser_sheets` (roles, `mimeData`,
`set_placed_views`); `test_stale_view_tabs` (`_close_stale_view_tabs`,
`_navigate_to_source_view`); `test_view_resolver_level_context`,
`test_paper_space`, `test_paper_commands`, `test_paper_viewport_crop`,
`test_multi_sheet`, `test_paper_persistence` (`ViewResolver`,
`source_view_type`); `test_block_editor`, `test_block_save_library`,
`test_lt4_roundtrip` (`BlockSaveDialog`); `test_block_open_dialog`,
`test_block_editor_ribbon_tab` (`BlockOpenDialog`); `test_lt3_integrity`,
`test_tile_authoring` (refusal reasons); `test_block_library_bundle`,
`test_nested_block_compile`, `test_wm2_integrity`, `test_wm2_persistence`
(`bundled` / `to_dict`); `test_app_data`, `test_settings_dialogs`
(`user_data_root`, path rows); `test_lt3_linetypes_folder`
(`capability_folder` — must stay untouched by the schematics folder);
`test_block_drag_drop` (`MIME_*`).

## Edge Cases & Error Handling

See `schematics.md` "Edge Cases". Implementation notes:

- Render-scene rebuild during a paint (definition saved while a sheet repaints):
  rebuild is deferred to the next event-loop turn except under PDF export,
  which has no loop — export resolves synchronously from the current
  definition version.
- `itemsBoundingRect` on a scene with pen-free geometry: use the same
  pen-free extent the editor's fit-on-open uses so NTS boxes don't inherit pen
  slop.
- A schematic whose only content is text: extent = text bounding rect; the
  Construction / Blocks rows don't apply, text handling does.

## Performance & Security

- One render scene per **placed** schematic, built on demand; a riser of a few
  hundred primitives materializes in the same time the editor seeds it. No
  bench required unless a sheet carries dozens of schematics (file a perf task
  then; confirm the metric with the user first).
- No security surface (local files only).
