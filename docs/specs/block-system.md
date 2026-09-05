---
status: partial           # S1–S5 built (Manager + load-from-library + Excel autofilter + themed ribbon icons; details panel read-only); thumbnails + Open-in-Editor deferred
last-verified: 2026-09-05
verified-commit: 74bc7bb
applies-to:
  - firepro3d/block_definition.py   # new — the flyweight definition + render-op compile
  - firepro3d/block_instance.py     # new — the lightweight placed scene entity
  - firepro3d/block_library.py      # new — .fpdb I/O, per-folder index, divergence
  - firepro3d/block_manager.py      # new — Manager dialog (MVC + frameless shell)
  - firepro3d/blocks_browser.py     # new — Blocks browser dock (mirrors feature_browser)
  - firepro3d/app_data.py           # new — shared _app_data_dir() helper (GENERALIZE)
  - firepro3d/model_space.py        # registry, instance list, place_block mode, make-from-selection
  - firepro3d/scene_io.py           # .fpd embed of definitions + instances
  - firepro3d/main.py               # Blocks ribbon group + browser dock wiring
source-tasks:
  - todo_open.md:18   # ribbon taxonomy (Draw = geometry + blocks)
  - todo_open.md:286  # block_item paste/undo orphan bug (constructively fixed)
  - todo_open.md:354  # BlockItem undocumented → this governing spec
  - todo_open.md:232  # shared _app_data_dir() helper (folded in)
  - todo_open.md:90   # Feature naming decision (settled for both systems)
---

# Block System — Design Spec

> **Scope discipline.** This spec governs the **Block subsystem v1** only. The parallel **Feature
> re-architecture** (non-parametric, 3-tier `Class/SubClass/Type`, opening decomposition, projection
> map) is **deferred to a later phase**; only the shared *naming/extension contract* below is locked
> now so neither library migrates twice. Where this spec reuses an existing pattern it **links** to
> that pattern's governing spec (Rule A) rather than restating it.

## Goal

Give the user a real, reusable **Block** system: define a named 2D symbol once (from drafting
linework), keep a library of it, and drop many **instances** into the model that all update when the
definition changes — the AutoCAD `WBLOCK`/`INSERT` loop, done natively and integrated with
FirePro3D's levels, snapping, undo, display manager, and `.fpd` persistence.

v1 delivers the **make → manage → place** loop. The dedicated Block Editor, geometry import, block
attributes/schedules, paper-space/elevation hosting, and the Feature **projection map** are v2+.

## Motivation

- The current `BlockItem` is a proof-of-concept: a thin `QGraphicsItemGroup` (name + children) with
  loose-`.json` file-dialog Insert/Create buttons. It is **not** in `scene_io` (blocks don't survive
  a project save), **not** in undo, **orphaned on paste** (`todo_open.md:18/286`), and has no
  library, manager, or tests. It cannot support real drafting content.
- Blocks and Features are **sibling libraries** (2D drafting content vs. modeled building elements).
  Settling the shared naming/extension contract now — and building Blocks first as the lower-risk,
  baggage-free sibling — de-risks the later Feature re-architecture.
- Reusable plumbing already exists (title-block library I/O, underlay-manager MVC, frameless shell,
  icon loader, feature-browser tree), so v1 is mostly *assembly + one genuinely new piece*
  (a graphical thumbnail cache).

## Architecture & Constraints

### Naming / storage contract (locked for BOTH systems; migrate-once)

- **Features:** 3 folder tiers `Class / SubClass / Type` + one-or-more `.fpdf` **type-definition**
  files under each `Type`. Non-parametric (size is a read-only attribute of the Type definition).
  Openings decomposed into `Door` / `Window` / `Opening` Classes. *(Deferred — contract locked, no
  code in this spec.)*
- **Blocks:** 2 folder tiers `Library / Series` + `.fpdb` files. *(Built in v1.)*

### The flyweight core

- **`BlockDefinition`** owns the block's identity + captured geometry. On construction/load it
  **compiles** its 2D primitives once into a cached, origin-relative render-op list
  `[(QPen, QPainterPath), …]` (definition-local coordinates). It never lives in the scene.
- **`BlockInstance`** is a **single lightweight `QGraphicsItem`** (no child items). It holds its
  definition's `id`, resolves the definition from the scene registry, and in `paint()` applies its
  `(pos, rotation)` transform and strokes the **shared** render-ops. `boundingRect()`/`shape()`
  derive from the shared path bounds under the transform.
- **Constraint (perf gate):** N instances of one definition share one geometry object; there are
  **no per-instance geometry copies**. Editing a definition rebuilds its cached render-ops and calls
  `update()` on every instance → all repaint. This is the "edit def → all instances update"
  invariant *and* the responsiveness guarantee, in one mechanism.
- **Theming/state applied at paint time:** definitions are colour-neutral; the display-manager
  colour, pre-highlight, and selection styling are applied as a pen override when the instance
  paints — so one shared geometry still respects per-instance/theme state.

### Runtime home & integration seams (on `Model_Space`)

- `_block_definitions: dict[str, BlockDefinition]` — project-scoped flyweight registry.
- `_block_instances: list[BlockInstance]` — placed instances (parallels the existing entity lists).
- Instances integrate as first-class entities: **selectable, movable, snappable** (`snap_engine`
  snaps the insertion origin), **level-aware** (active level on place; participates in level
  visibility), **pre-highlightable**, **display-manager aware**, and **Z-ordered** per the elevation
  z-model (Z-order is owned by `view-relationships.md §7.3` + `constants.py` — not restated here).
- **`BlockItem` is retired** (class + loose-`.json` Insert/Create buttons + paste path). Removal is
  grep-verified repo-wide and launch-smoked.

### Reuse (link, don't reinvent)

- **Library I/O + project embedding + divergence:** reuse the pattern in
  `titleblock-template-system.md` (atomic write, embedded-copy-authoritative, `id`+`version`
  divergence). This spec *links* to it and only documents the block-specific schema below.
- **Manager UI:** underlay-manager MVC (model/proxy/delegate) + `FramelessShellMixin`
  (`architecture/theming.md`).
- **Browser dock:** mirror `feature_browser.py`'s tree pattern.
- **Ribbon + icons:** `ribbon-bar.md` for group/button wiring; `icon-style-guide.md` for the
  two-token themed icon authoring + guard tests (not restated here).
- **Placement/mode + Dynamic-Input HUD:** the existing placement-coordinator seam and the transform
  HUD (`align-placement.md §4` / grid-system placement conventions).

## Design Decisions

1. **Instance rendering = flyweight over a shared render-op list** (chosen over per-instance child
   cloning, which fails the perf gate, and over a shared `QPicture`, which bakes pens/colours and
   fights per-instance theming/pre-highlight).
2. **Identity = one `uuid4` `id` per definition** (registry key = instance reference = library link),
   with human-readable `name`/`library`/`series` as *metadata*. `version` (monotonic int, bumped on
   save) drives divergence. Chosen over slugs, which collide and break instance references on rename.
   **Convention gate: this `id`/`version` scheme and the `.fpdb` key schema below are frozen before
   implementation fans out.**
3. **`.fpdb` filenames are human-readable** (`blocks/<Library>/<Series>/<sanitized-name>.fpdb`) with
   the `uuid` stored *inside* the file, because blocks are browsed in a folder tree. A per-folder
   `index.json` carries `filename ↔ {id, name, version, thumbnail}` so listings never open every file.
   (Contrast: the title-block library uses uuid-named files; blocks differ deliberately.)
4. **Embedded copy authoritative; library advisory.** Projects open standalone with the library
   folder **absent** (hard portability gate). Save-to-Library pushes embedded→disk; Reload-from-Library
   pulls disk→embedded (bumping the embedded `version`).
5. **Thumbnails — DEFERRED (cut from S4, 2026-09-04).** Intended design: in-memory render (from the
   already-cached render-ops) for project-only blocks; PNG-next-to-`.fpdb` for library blocks; keyed
   `(id, version)`. Cut from the S4 Manager to keep it pure assembly of existing parts; the `(id,
   version)` key stays reserved for the v2 Editor (which makes geometry mutable and gives thumbnails
   their reason to exist). Tracked as a follow-up (see `todo_open.md`).
6. **Capture = 2D drafting primitives only** (`LineItem`/`RectangleItem`/`CircleItem`/`ArcItem`/
   `PolylineItem`/`RegularPolygonItem`). Walls/pipes/features/text/dimensions are refused. Text +
   attributes are a coupled v2 concern.
7. **Make-from-selection consumes the selection** (deletes the linework, drops one `BlockInstance` at
   the picked origin — AutoCAD `BLOCK` semantics), fully undoable. Chosen over copy-in-place because
   it matches the mental model and exercises the def→instance path immediately.
8. **Placement = 2-step** (click position → rotation step with Ctrl-snap + typed HUD angle; Enter at
   step 1 accepts 0°), **stay-in-mode repeat until Esc**.
9. **`scale_mode` enum in schema, `Real-size` the only v1 value** (`Annotative` reserved for v2 with
   paper-space). Instances render at the definition's real size; **no rescale/mirror in plan views**
   (that is Editor-only, v2). **Attributes structure reserved in schema, no UI in v1.**
10. **v1 definitions are geometry-immutable** (no Editor yet). **The Manager is view-only**
    (2026-09-05): its details panel shows name/library/series read-only; the Manager's verbs are
    Load-from-Library / Save-to-Library / Reload / Delete / place. **All metadata editing
    (name/library/series) is reserved for the Block Editor (v2)** — `Model_Space.set_block_metadata`
    exists and is tested for that consumer but is not wired to any inline UI. To change geometry, make
    a new block.
11. **Manager = MVC view over an arm's-length scene API (S4, 2026-09-04).** The block-management logic
    lives as `Model_Space` methods (`instance_count`, `delete_block_definition`,
    `reload_block_definition`, `set_block_metadata`, + a `blockInstancesChanged` signal); the dialog is
    a thin `QAbstractTableModel` + delegate view mirroring the Underlay Manager
    (`underlay_manager*.py` + `FramelessShellMixin`). Chosen over embedding logic in the Qt model so
    guard tests target real scene methods with no dialog machinery. Metadata edits, Delete, and
    Reload-from-Library are undoable via `push_undo_state()` (no new undo plumbing —
    `_capture_network` already serializes definitions); Save-to-Library is a pure disk write (not
    undoable). Full HOW in `docs/superpowers/specs/2026-09-04-block-manager-s4-design.md`.
12. **Load = browse-anywhere file dialog, not an in-app library mirror (S4.5, 2026-09-04).** The
    S4-grill "union/library view" was un-deferred as a Revit "Load Family" flow: a multi-select
    `QFileDialog` embeds picked `.fpdb` definitions into the project (a `.fpdb` IS `to_dict()` JSON, so
    an arbitrary path loads via `block_library.load_block_file`). Chosen over an in-app tree mirroring
    the on-disk library because a file dialog also loads one-off blocks from anywhere and needs no live
    library-tree widget. The batch is one undoable registry mutation with per-file collision rules
    (skip / replace-via-`_swap_block_definition` / refuse). The project table becomes a
    Library→Series→block tree at the same time.

## Tech Context

- **Language/Framework:** Python 3.x + PyQt6; geometry in millimetres (scene unit = 1 mm).
- **Persistence:** JSON — `.fpdb` (library file), `.fpd` (project embed), `index.json` (per-folder).
- **Dependencies:** reuse existing modules per the reuse map; no new third-party deps.

## Input / Output

### `.fpdb` (library file) and embedded-definition schema

```jsonc
{
  "schema": 1,
  "id": "<uuid4 hex>",              // stable identity; instance references + library link
  "version": 3,                     // monotonic; bumped on save; divergence key
  "name": "Corner Joint",
  "library": "Typical Detail",      // tier 1
  "series": "Wall Joints",          // tier 2
  "scale_mode": "real_size",        // enum; v1 sole value; "annotative" reserved
  "origin": [x_mm, y_mm],           // definition-local insertion origin
  "attributes": [],                 // reserved; no UI in v1
  "primitives": [ { /* each primitive's own to_dict() */ } ]   // reuse construction_geometry items
}
```

### `.fpd` project embed

```jsonc
{
  "block_definitions": { "<id>": { /* schema above, sans file wrapper */ } },
  "blocks": [                       // instances
    { "block_id": "<id>", "pos": [x_mm, y_mm], "rotation": <deg>,
      "level": "Level 1", "attributes": {} }
  ]
}
```

### Per-folder `index.json`

```jsonc
{ "<sanitized-name>.fpdb": { "id": "<uuid>", "name": "Corner Joint",
                             "version": 3, "thumbnail": "<name>.png" } }
```

## Existing Code Context (reuse map)

- **REUSE:** `titleblock_template.py` (library I/O + embed + divergence), `titleblock_editor.py`
  (working-copy/snapshot — informs v2 Editor), `underlay_manager*.py` + `frameless_shell.py`
  (Manager), `feature_browser.py` (browser tree), `icons.py`/`svg_utils.py` + `tests/test_icon_theming.py`
  (icons), `ribbon_bar.py` (group/button API), `construction_geometry.py` (the captured primitives'
  `to_dict`/`from_dict` + `DisplayableItemMixin`), `snap_engine.py` (insertion snap).
- **GENERALIZE:** extract `app_data.py::_app_data_dir()` from the duplicated `%APPDATA% or ~` +
  `FirePro3D` resolution in `sprinkler_db._default_db_path` and `titleblock_template._library_dir`
  (`todo_open.md:232`) → roots `blocks/`.
- **GAP (net-new):** `BlockDefinition`/`BlockInstance`/`block_library`/`block_manager`/`block_browser`;
  the graphical thumbnail render+cache (no thumbnail system exists anywhere in the app).

## Edge Cases & Error Handling

- **Cross-machine open, library absent:** load from the embedded `block_definitions`; never fail on a
  missing library folder (hard gate).
- **Orphaned instance (definition id not in registry):** must not crash; render a visible
  placeholder + surface a warning; block delete of the (missing) definition is moot. Covered by a
  guard test.
- **Delete definition with live instances:** refused in the Manager (instance-count > 0).
- **Divergence:** embedded `version` ≠ library `version` for same `id` → Manager marks "modified";
  Save-to-Library / Reload-from-Library resolve it (embedded stays authoritative until the user acts).
- **Library lookups resolve by `id`, not folder location (2026-09-05).** `source_status` /
  `reload_from_library` scan the *whole* tree for the definition's `id` (a single `_iter_index_entries`
  walk → `_find_by_id`), so a block whose metadata (Library/Series/name) has drifted from its on-disk
  folder still reads its true status instead of falsely `project-only`. `save_to_library` **re-files**:
  a stale same-`id` `.fpdb` + index entry parked at a prior location is deleted before the new write,
  so a relocated/renamed block never duplicates on disk.
- **Cross-`id` filename collision on Save (2026-09-05).** If the target `<sanitized-name>.fpdb` is
  already held by a *different* `id`, `save_to_library` raises `BlockNameCollision(existing_name)`
  *without touching disk* (collision check precedes re-file/write, so a refused save is inert). The
  callers (Manager Save button, Make-Block flow) prompt overwrite/cancel (`themed_confirm`); overwrite
  passes `overwrite=True`. Prevents the earlier silent-overwrite data loss where two blocks named the
  same string clobbered each other's library entry. *(True rename-on-collision is deferred — overwrite
  metadata is read-only outside the v2 Editor; see `todo_open.md`.)*
- **Make-from-selection with non-primitives selected:** non-primitive items ignored/refused with a
  message; an all-non-primitive selection makes no block.
- **Corrupt `.fpdb` / stale `index.json`:** tolerant load — skip + log, like the title-block library.

## Performance

- **Shared-definition rendering is the perf contract:** many instances of one definition must stay
  responsive because they share one geometry object and one render-op list; instance `paint()` is a
  transform + stroke of the shared paths. A guard/bench asserts N-instance responsiveness and that no
  per-instance geometry copy is created.

## Code Style & Testing

- Google docstrings; PEP 8 module names; relative imports within `firepro3d/`.
- **Guard-test discipline:** construct the real scenario, drive the behavior, assert **observable
  ground truth** (not source text, not the impl's own internal value); use **real domain objects**;
  each guard shown RED with the fix reverted. Live-render behavior (paint/pre-highlight/snap) is
  additionally covered by the manual smoke checklist (headless-green is not "done").

## Acceptance Criteria

- [ ] **Project round-trip:** definitions + instances save to `.fpd` and reload identically
      (transforms, level, ids preserved).
- [ ] **Cross-machine portability (HARD):** project opens correctly with the `blocks/` library folder
      absent, from the embedded definitions alone.
- [ ] **Undo/redo:** placing, deleting, and make-from-selection are all undoable; blocks are in
      `_capture_network`/`_restore_network` (constructively fixes `todo_open.md:18/286`).
- [ ] **Def→instance propagation:** mutating a definition re-renders **every** instance (shared
      render-ops), proven with real `BlockInstance` objects.
- [ ] **Library I/O + divergence:** Save-to-Library writes `.fpdb` + updates `index.json` + PNG;
      Reload-from-Library updates the embedded copy; divergence detected on `version` mismatch.
- [ ] **Make-from-selection:** captures 2D primitives with correct origin, **consumes** the selection,
      refuses non-primitives.
- [ ] **Manager:** Delete refused while instances exist (project-registry-only, undoable);
      instance-count reflects the scene **live** (updates as instances are placed/deleted with the
      Manager open); source-status (project-only / library / modified) correct; Save-to-Library /
      Reload-from-Library resolve divergence (Reload rebuilds instance backrefs + repaints, undoable);
      metadata edits validate (blank/collision revert) with `id` stable across rename.
- [ ] **Load from Library (S4.5):** a browse-anywhere multi-select `*.fpdb` file dialog embeds picked
      definitions into the project (placeable, portable), applying per-file collision rules (skip same
      `id` / replace diff `version` with instance repaint / refuse `(library,series,name)` clash) in one
      undoable batch with a summary; the project view is a Library→Series→block tree; unload = Delete;
      "Open in Editor" is a stub.
- [ ] **Placement:** browser double-click → `place_block` mode; 2-step (position → rotation, Enter=0°),
      snapped, level-aware, repeat until Esc.
- [ ] ~~**Thumbnail:** non-blank pixmap; library PNG cached and referenced in `index.json`.~~
      **DEFERRED (cut from S4, 2026-09-04)** — tracked as a follow-up in `todo_open.md`.
- [ ] **`BlockItem` retired:** repo-wide grep shows no live importers; app launch-smoke passes.
- [ ] **Perf:** many instances of one block stay responsive (shared-definition rendering; no
      per-instance geometry copies).
- [x] **Icons:** themed Blocks-group icons pass the two-token guard tests (`icon-style-guide.md`).
      *(S5 shipped: `make_block_icon.svg` / `insert_block_icon.svg` / `block_manager_icon.svg`; 17 green.)*

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] Tests pass at unit + integration level (round-trip through the real `scene_io` path).
- [ ] No regressions: existing entity save/load/undo unaffected by the new blocks list.
- [ ] Manual smoke: place/render/rotate/pre-highlight/snap in the running app; Manager opens;
      make-from-selection end-to-end; save → reopen; open with library absent.
- [ ] `SPEC-INDEX.md` row added; `status` advanced from `proposal` as slices land; frontmatter
      `last-verified`/`verified-commit` stamped per touching task.

## Build Order (slices — each its own plan→implement→commit cycle)

1. **S1 — Data model & lifecycle.** `BlockDefinition` + `BlockInstance` + registry; retire
   `BlockItem`; `scene_io` embed + `_capture_network` undo. No UI (tested programmatically). Gates:
   round-trip, undo, propagation, perf, clean retirement.
2. **S2 — Create & place loop (project-only). BUILT 2026-09-04.** `BlocksBrowser` dock +
   `blockDefinitionsChanged` signal; `place_block` 2-step mode (position→rotation, ghost, Enter=0°,
   HUD `angle_deg`, repeat-until-Esc); `make_block_from_selection` (consume → def + instance, one
   undo); the three seam fixes (`translate` movability, `block_instance` copy/paste branch, orphan
   placeholder); ribbon Make/Insert/Manager buttons. Origin = selection bbox top-left in v1
   (interactive snapped origin-pick deferred to a smoke follow-up); "save to library?" not wired
   until S3. Seam-reviewed (one blocker fixed: ghost teardown on same-mode re-entry).
3. **S3 — Library layer.** `.fpdb` schema + `app_data.py` helper + per-folder `index.json` +
   embed/divergence + Save/Reload-from-Library; wire the real "save to library?" prompt into S2.
4. **S4 — Block Manager (thumbnails DEFERRED).** Underlay-manager-style MVC + frameless shell
   (toolbar + flat table + details panel + footer). Columns: name / library / series /
   **instance-count (live)** / source-status. Details-panel metadata editing (name/library/series,
   embedded-only, required-non-blank, revert-on-invalid, registry-level (library,series,name)
   uniqueness). Actions gated by selection + source-status: **Delete** (project-registry-only,
   undoable, refused when instance-count > 0 with a count-naming message), **Save-to-Library**
   (project-only | modified), **Reload-from-Library** (modified, undoable, rebuilds instance backrefs).
   Live count via a new `blockInstancesChanged` signal (place/remove instance does **not** fire
   `blockDefinitionsChanged`). Logic lives as arm's-length `Model_Space` methods; the dialog is a thin
   view. **Thumbnail pipeline cut → follow-up.** Replaces the `_open_block_manager` stub. Design:
   `docs/superpowers/specs/2026-09-04-block-manager-s4-design.md`.
4.5. **S4.5 — Load from Library ("Load Family") + tree reshape.** A "Load from Library…" toolbar
   button opens a browse-anywhere multi-select `QFileDialog` (`*.fpdb`, starts at `app_data_dir(
   "blocks")`); each picked file embeds its definition into the project (Revit Load-Family), applying
   per-file collision rules (same `id` → skip; same `id` diff `version` → replace via the shared
   `_swap_block_definition` backref-rebuild; diff `id` same `(library,series,name)` → refuse) in **one
   undoable batch** with a summary message. The S4 flat table is **reshaped into a Library→Series→block
   expandable tree** (`BlockTreeModel`; leaves keep instance-count + source-status; edit/delete/Save/
   Reload resolve to the selected leaf). Unload = the existing Delete. A stubbed **"Open in Editor"**
   button reserves the v2 Editor entry point. New: `block_library.load_block_file(path)`,
   `Model_Space.load_blocks_from_files(paths, root=None)`. Design:
   `docs/superpowers/specs/2026-09-04-block-manager-s4-design.md`.
4.6. **S4.6 — Excel-style flat autofilter table (supersedes the S4.5 tree).** The project view is a
   flat sortable `QTableView` with a per-column **autofilter** (funnel per header → popup: Sort A→Z/
   Z→A + search + (Select All) + multi-select checkboxes; OK/Cancel; active funnel highlighted), over a
   `BlockFilterProxy(QSortFilterProxyModel)` holding per-column accepted-value sets + a `FilterHeader`.
   Mockup-gated (`tools/block_autofilter_mockup.html`). Replaces `BlockTreeModel` (built in S4.5, then
   superseded); the S4.5 loader / `_swap_block_definition` / buttons / Open-in-Editor stub are kept.
5. **S5 — Icons & polish. ✅ SHIPPED 2026-09-05.** Themed ribbon icons authored mockup-gated
   (`icon-style-guide.md`): `make_block_icon.svg` (plus) / `insert_block_icon.svg` (arrow) /
   `block_manager_icon.svg` (grid), two-token compliant, wired into the Create▸Blocks group
   (`main.py`) + the Block Manager title bar (`block_manager.py`); guard tests in
   `test_icon_theming.py` (17 green). Replaced the placeholder-icon fallback S2–S4 ran on.
