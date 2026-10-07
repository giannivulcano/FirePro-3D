---
status: partial           # + placement Weight / Linetype overrides pointer (WM2, 2026-10-07); + Block Editor capability slot pointer (LT4, 2026-10-06); + linetype capability (LT3, 2026-10-05); + pattern-tile capability (HF2, 2026-10-03); S1–S5 + Block Editor v2 (BE1–BE5) + block polish (2026-09-23: exact curve import, Save/Save As, library-folder Save dialog, library-backed browser, text in blocks) + nested blocks (2026-09-30: registry, nested references, drag-and-drop, Explode, .fpdb schema 2, one-click placement) built; thumbnails + attribute authoring + paper-space placement deferred
last-verified: 2026-10-07  # WM2 Account (Placement Weight / Linetype overrides pointer subsection); prior LT4 Account: "Block Editor capability slot (LT4)" pointer subsection (block_capability slot, symbol_use_refusal, library-row badges) + HF2 refusal name fixed (pattern_use_refusal → symbol_use_refusal alias; counts nesting too); prior LT3 Account: "Linetype capability (LT3)" pointer subsection (repeat key, placement/paste/drag refusal, linetype refs in referenced_ids + live-line delete refusal, stroke-op pieces); prior 2026-10-03 HF2 Account: "Pattern-tile capability (HF2)" subsection (tile key, typed RenderOp compile, referenced_ids, pattern placement refusal, browser badge + Edit Block) + flyweight-core render-op wording; prior 2026-10-02 CS1 constraint-foundation account: origin fixed at (0,0) (Set Origin + red marker + bbox-top-left default retired; migration on open), Create Block from selection = bbox-centre base + place_at (D24), BlockDefinition.constraints, reference lines persist as scaffolding (is_scaffold, D23), primitive uid incl. nested block_instance records; prior 2026-09-30 Block Editor ribbon tab account (feat/block-editor-ribbon-tab: permanent tab, Open picker, browser helpers); prior 2026-09-30 nested-blocks; prior 2026-09-28
verified-commit: a65daf67   # WM2 Account (feat/wm2-placement-overrides); prior b9b1094 LT4 repeat authoring (feat/lt4-repeat-authoring; pointer subsection only); prior be7c88a LT3 linetype renderer (feat/lt3-linetype-renderer); prior 53e1773 HF2 pattern renderer + tile blocks (hf2-pattern-renderer); prior 2a22ba9 CS1 constraint foundation (feat/cs1-constraint-foundation); prior 44325e5 Block Editor ribbon tab account (feat/block-editor-ribbon-tab); prior 345f1b7 nested-blocks account (feat/nested-blocks); prior d34aeb0   # batch A dead-code sweep; prior 892cf76   # snap-polish: block snap points (origin + stroked vertices + text boxes, never glyphs); prior f2b1d99   # HALO pixel ranking / grip limit / editor undo baseline; prior 434066c
related-contract: model-space-containment-contract.md   # LANDED in code (C1/C2/C5/C7/C8 + C3 instance level-scope). Body reconciled: "siblings"→C2 (Feature composes Blocks); Quick Block retired (C7); BlockInstance is level-scoped (C3). Flyweight/library/Manager/Editor bulk stays current.
applies-to:
  - firepro3d/block_definition.py   # new — the flyweight definition + render-op compile
  - firepro3d/block_instance.py     # new — the lightweight placed scene entity
  - firepro3d/block_library.py      # new — .fpdb I/O, per-folder index, divergence
  - firepro3d/block_manager.py      # new — Manager dialog (MVC + frameless shell)
  - firepro3d/blocks_browser.py     # new — Blocks browser dock (mirrors feature_browser) + module helpers library_only_entries / ensure_block_loaded (shared with the Open picker, 2026-09-30)
  - firepro3d/block_open_dialog.py  # 2026-09-30 — BlockOpenDialog, the Block Editor tab's Open… picker
  - firepro3d/app_data.py           # new — shared _app_data_dir() helper (GENERALIZE)
  - firepro3d/model_space.py        # registry, instance list, place_block mode, make-from-selection, commit_block_definition (v2; place_at + constraints since CS1)
  - firepro3d/scene_io.py           # .fpd embed of definitions + instances
  - firepro3d/main.py               # browser dock; Block Editor ribbon tab (permanent base tab since 2026-09-30 — Block group New/Open/Manager/Insert + editor-only groups; wiring owned by ribbon-bar.md) + active-scene routing (v2)
  - firepro3d/geometry_import.py    # v2 — pure geom_dict→primitive factory + geometric_bounds (bbox_top_left retired at CS1)
  - firepro3d/block_editor.py       # v2 — BlockEditorManager + BlockEditorWidget + BlockSaveDialog
  - firepro3d/block_import_dialog.py # v2 — flattened BlockImportDialog (subclasses UnderlayImportDialog)
  - firepro3d/block_registry.py     # nested blocks — BlockRegistry (resolution / dependency / cycle / invalidation choke point)
  - firepro3d/block_explode.py      # nested blocks — explode_instances (Block-Editor-only, C1)
  - firepro3d/mime_types.py         # nested blocks — one home for in-app drag MIME types (MIME_BLOCK)
  - firepro3d/model_view.py         # nested blocks — block drop target (plan + Block Editor views) + fit_scene_rect
source-tasks:
  - todo_open.md:18   # ribbon taxonomy (Draw = geometry + blocks)
  - todo_open.md:286  # block_item paste/undo orphan bug (constructively fixed)
  - todo_open.md:354  # BlockItem undocumented → this governing spec
  - todo_open.md:232  # shared _app_data_dir() helper (folded in)
  - todo_open.md:90   # Feature naming decision (settled for both systems)
  - todo_open.md:66   # "Open in Editor" → the v2 Block Editor authoring surface
  - todo_open.md:60   # interactive snapped origin-pick (folded into the v2 Set-Origin tool)
  - "todo_open.md → [feature] Nested blocks — drag a block from the Blocks browser into the Block Editor, plus a Block Editor ribbon Explode (2026-09-29)"
---

# Block System — Design Spec

> **Scope discipline.** This spec governs the **Block subsystem v1** only. The parallel **Feature
> re-architecture** (non-parametric, 3-tier `Feature > Family > Type`, opening decomposition, projection
> map) is **deferred to a later phase**; only the shared *naming/extension contract* below is locked
> now so neither library migrates twice. Where this spec reuses an existing pattern it **links** to
> that pattern's governing spec (Rule A) rather than restating it.
>
> **Reconciled to the containment contract (2026-09-18 — `model-space-containment-contract.md`,
> LANDED in code).** The contract's Block-touching invariants are shipped and woven into the body
> below: **(1)** the old "Blocks and Features are **sibling libraries**" premise is replaced by **C2:
> a Feature *composes* Blocks** (a Feature references Block definitions for its 2D representations —
> Feature build-out itself is still deferred; see `feature-system.md`); **(2)** the **Quick Block**
> entry point is **retired (C7)** — its premise (bake a selection of loose *model* geometry) is void
> under C1's placement-only Model Space; **(3)** a placed **`BlockInstance` is level-scoped (C3)** —
> see the "BlockInstance level scope" subsection below. Per C7/C9 a standalone Block instance is
> placeable in **both** Model Space *and* Paper Space (paper-placement rules pending — a known gap,
> see `paper-space.md`). The flyweight def/instance core, `.fpdb` library, Manager, and Block Editor
> **stay current**. Invariants live once in the contract; this links up (Rule A).

> **System Blocks (proposal, 2026-09-29).** A ratified concept extends this
> subsystem, but none of it is built yet: bound `@[key]` text fields plus an attribute schema in
> the reserved `attributes` slots (revisits decisions 6 and 9), `scale_mode:
> "annotative"` activated, and a read-only shipped **System** library tier with a
> multi-root library. See `docs/superpowers/specs/2026-09-29-system-blocks-concept-design.md`.
> This spec is amended in place as tasks SB1a/SB1b land. Until then the body below
> is the current contract.

> **Reference-graphic unification (2026-09-17, `3c3b00c`).** `BlockDefinition`
> gained a `render_mode` (`"default"` = per-primitive compile, unchanged for
> authored blocks; `"reference"` = **batched-per-layer** compile, one render op
> per distinct `layer` tag), an optional `geoms` field (import geom-dicts owned by
> a *reference* definition; cache-backed, NOT serialized in `.fpdb`/`.fpd`), and
> the `reference_from_geoms(...)` factory. Underlays are now re-homed onto such a
> reference definition (`Underlay.definition`). Authored-block render/snap is
> untouched. Target + rationale owned by `reference-graphic-model.md`; noted here
> per Rule A.

> **Nested blocks (2026-09-30, `feat/nested-blocks`, `345f1b7`).** A definition may
> hold **live references to other definitions** (acyclic), resolved through one
> `BlockRegistry`; blocks drag from the Blocks browser onto plan views and the
> Block Editor; the Block Editor gains **Explode**; `.fpdb` gains schema 2
> (`bundled`); placement became **one click at 0°** (Decision 8). The durable
> contract is the "Nested blocks" section below; the HOW (D1–D12, AC1–AC14) and
> the as-built amendments live in
> [`2026-09-29-nested-blocks-design.md`](../superpowers/specs/2026-09-29-nested-blocks-design.md).

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
- A **Feature composes Blocks** (`model-space-containment-contract.md` C2): a Feature references Block
  definitions for its 2D representations rather than being a disjoint sibling library. (This supersedes
  the earlier "Blocks and Features are sibling `.fpdb`/`.fpdf` libraries" premise; the shared
  naming/extension contract below still holds, the disjoint-siblings relationship does not. Feature
  build-out remains deferred — only the relationship framing is settled.) Building Blocks first as the
  lower-risk, baggage-free half de-risks the later Feature re-architecture.
- Reusable plumbing already exists (title-block library I/O, underlay-manager MVC, frameless shell,
  icon loader, feature-browser tree), so v1 is mostly *assembly + one genuinely new piece*
  (a graphical thumbnail cache).

## Architecture & Constraints

### Naming / storage contract (locked for BOTH systems; migrate-once)

- **Features:** hierarchy `Feature > Family > Type` (canonical labels settled 2026-09-21 —
  `feature-system.md` F4; relabels the earlier `Class / SubClass / Type`, same three tiers).
  On-disk `<Feature>/<Family>/<Type>.fpdf`; one `.fpdf` = one **Type**. Size is a read-only
  attribute of the Type (parametric engine deferred). Top-tier Features are `Door` / `Window` /
  `Opening`. *(Phase-A `feature.py` re-keyed; Manager/Editor + on-disk library deferred.)*
- **Blocks:** 2 folder tiers `Library / Series` + `.fpdb` files. *(Built in v1.)*

### The flyweight core

- **`BlockDefinition`** owns the block's identity + captured geometry. On construction/load it
  **compiles** its 2D primitives once into a cached, origin-relative list of typed `RenderOp`s
  (definition-local coordinates; see "Pattern-tile capability (HF2)"). It never lives in the scene.
- **`BlockInstance`** is a **single lightweight `QGraphicsItem`** (no child items). It holds its
  definition's `id`, resolves the definition from the scene registry, and in `paint()` applies its
  `(pos, rotation)` transform and strokes the **shared** render-ops. `boundingRect()`/`shape()`
  derive from the shared path bounds under the transform.
- **Constraint (perf gate):** N instances of one definition share one geometry object; there are
  **no per-instance geometry copies**. Editing a definition rebuilds its cached render-ops and calls
  `update()` on every instance → all repaint. This is the "edit def → all instances update"
  invariant *and* the responsiveness guarantee, in one mechanism.
- **Nested blocks keep the flyweight (2026-09-30):** a nested reference is **flattened at compile**
  — the host's cached op list is its own primitives plus each nested definition's cached ops
  mapped through the nested pose, then the host's origin shift — so there is still **one shared
  op list per definition** and no per-instance copies; paint, `boundingRect`/`shape` (HALO) and
  snap read the flattened list unchanged. Editing a nested definition invalidates every
  definition that uses it (`BlockRegistry.invalidate`). Guard:
  `tests/test_nested_block_compile.py::test_nested_compile_is_shared_across_instances`.
- **Theming/state applied at paint time:** definitions are colour-neutral; the display-manager
  colour, pre-highlight, and selection styling are applied as a pen override when the instance
  paints — so one shared geometry still respects per-instance/theme state.
- **Stroke weights (LT2, 2026-10-04):** stroke ops carry an unresolved `RenderOp.weight` and
  `BlockInstance.paint` resolves canvas px / paper mm per op (flyweight unchanged);
  `BlockDefinition.from_dict` migrates + canonicalises stored primitives and `to_dict` deep-copies
  them — contract in [`linetypes.md`](linetypes.md) "LT2" (H-a, H-c′/H-d).

### Runtime home & integration seams (on `Model_Space`)

- `_block_definitions: dict[str, BlockDefinition]` — project-scoped flyweight store, fronted by
  a **`BlockRegistry`** (`block_registry.py`, `Model_Space.block_registry`) — see "Nested blocks"
  below.
- `_block_instances: list[BlockInstance]` — placed instances (parallels the existing entity lists).
- Instances integrate as first-class entities: **selectable, movable, snappable** (`snap_engine`
  snaps the insertion origin, the definition's stroked on-curve vertices and each text
  primitive's frame-box points, but never glyph outlines; the matrix row is owned by
  [`snapping-engine.md §5`](snapping-engine.md#5-item-type-snap-type-matrix)), **level-scoped** (see "BlockInstance level scope" below — active level
  on place; participates in level visibility), **pre-highlightable**, **display-manager aware**, and
  **Z-ordered** per the elevation z-model (Z-order is owned by `view-relationships.md §7.3` +
  `constants.py` — not restated here).
- **Placement surfaces (contract C7/C9):** a standalone Block instance is placeable in **both** Model
  Space *and* Paper Space. Paper-space placement rules are still a known gap (see `paper-space.md`);
  the placement mechanics documented here cover the Model-Space path.
- **`BlockItem` is retired** (class + loose-`.json` Insert/Create buttons + paste path). Removal is
  grep-verified repo-wide and launch-smoked.

### BlockInstance level scope (containment contract C3)

The block **definition** is reusable and context-free — its primitives are **level-less**. "Which
level does this block show on?" is an **instance** question, so level scope lives on the placed
`BlockInstance`, not on the definition (`model-space-containment-contract.md` C3).

- **State on the instance:** `level` (defaults to the active level on place) and `_level_offset_mm`
  (Z/elevation offset from the level plane, `0.0` by default).
- **Elevation:** `z_range_mm()` returns a degenerate point `(e, e)` where `e =` the level's elevation
  `+ _level_offset_mm` (a block is a flat 2D graphic pinned to its level plane), mirroring
  `wall.z_range_mm`; `None` when no `LevelManager` is reachable. The level / elevation / Z model is
  owned by `view-relationships.md` (§7.3 for Z-order) — not restated here (Rule A).
- **Filtering:** `LevelManager` filters and z-orders instances exactly like any placed model entity —
  active-level/view-range visibility over `_block_instances`, and elevation-based z from `z_range_mm()`
  (heir of the loose-2D band, above all building geometry). Level rename remaps instances too.
- **Property rows:** the instance exposes **Level**, **Level Offset**, and **Rotation** rows via
  `get_properties()`/`set_property()` (Level Offset as a `ScaleManager`-formatted dimension; Rotation
  as a numeric line-edit matching the `RegularPolygonItem`/`EllipseItem` convention).
- **Serialization (both paths):** level + offset round-trip through **both** the `.fpd` file path
  (`scene_io`) **and** the undo path (`_capture_network`/`_restore_network`) — `to_dict()` always
  emits `level` and emits `level_offset_mm` only when non-zero.

### Reuse (link, don't reinvent)

- **Library I/O + project embedding + divergence:** reuse the pattern in
  `titleblock-template-system.md` (atomic write, embedded-copy-authoritative, `id`+`version`
  divergence). This spec *links* to it and only documents the block-specific schema below.
- **Manager UI:** underlay-manager MVC (model/proxy/delegate) + `FramelessShellMixin`
  (`architecture/theming.md`).
- **Browser dock:** mirror `feature_browser.py`'s tree pattern.
- **Ribbon + icons:** `ribbon-bar.md` for group/button wiring; `icon-style-guide.md` for the
  two-token themed icon authoring + guard tests (not restated here).
- **Placement/mode:** the existing placement-coordinator seam (grid-system placement conventions).
  Since 2026-09-30 `place_block` offers **no Dynamic-Input HUD** (one click at 0° — Decision 8).

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
6. **Capture = 2D drafting primitives + nested block references.** A definition's `primitives`
   hold the 2D drafting primitive records (the `BlockDefinition` primitive factory — line / rect /
   circle / arc / polyline / polygon / ellipse / spline, and text since 2026-09-23) and, since
   2026-09-30, inline **`block_instance` records: live references to other definitions** (editing
   the nested definition updates every host), **acyclic** (no definition may contain itself
   directly or transitively — refused at drop, double-click, library load/reload and Save).
   Nested references are **level-less** like primitives (containment C3). Walls/pipes/features/
   dimensions are refused. Attributes remain a future concern (the reserved `attributes` slot).
7. **Make-from-selection consumes the selection** (deletes the linework, drops one `BlockInstance` at
   the picked origin — AutoCAD `BLOCK` semantics), fully undoable. Chosen over copy-in-place because
   it matches the mental model and exercises the def→instance path immediately.
8. **Placement = one click at 0°** (amended 2026-09-30, smoke 2 — the original rotation step is
   **retired**): a ghost follows the snapped cursor, a click places the instance at 0° on the
   active level (one undo step), and the mode **stays live until Esc** (repeat placement). No
   Dynamic-Input HUD. Rotation is applied afterwards with **Modify ▸ Rotate** (clicked rays or
   the typed angle, in the plan and the Block Editor) or through the instance's **Rotation**
   property row. `BlockInstance.manip_rotate(angle, pivot)` turns the insertion point about the
   pivot and adds the angle to the stored rotation (Y-up CCW+, baked into the pose, not
   normalised); nested blocks follow because they render through the instance pose.
   Drag-and-drop placement follows the same
   one-drop-at-0° rule (see "Nested blocks" below).
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
    an arbitrary path loads — since 2026-09-30 via `block_library.load_block_file_with_bundle`, which also
    returns a schema-2 file's bundled definitions). Chosen over an in-app tree mirroring
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
  "origin": [x_mm, y_mm],           // vestigial since CS1: always [0, 0] on save (D4 — see below)
  "attributes": [],                 // reserved; no UI in v1
  "primitives": [ { /* each primitive's own to_dict(), incl. "uid" */ } ],   // reuse geometry_2d items
  "constraints": [ /* sketch constraint records */ ]   // additive since CS1; absent => []
}
```

**Nested reference record (2026-09-30).** A nested block rides *inside* `primitives` as an inline
record — the placed-instance shape minus level fields (containment C3):

```jsonc
{ "type": "block_instance", "block_id": "<nested id>", "pos": [x_mm, y_mm], "rotation": <deg>,
  "uid": "<primitive uid>" }
```

`pos` is definition-local (before the host's origin shift); `rotation` is Y-up CCW degrees (the
`BlockInstance.pose_transform` convention). Files without such records load unchanged. Record
producer: `BlockInstance.to_nested_dict`.

**Constraint foundation (CS1, 2026-10-02).** Additive, schema-1-compatible changes (no `schema`
bump; `BlockDefinition.from_dict` ignores `schema`):

- **`constraints`** — `BlockDefinition.constraints`, the editor's sketch constraint records (saved
  by the Block Editor's commit, re-loaded and first-solved on open). Record format, validity,
  forward compatibility and solve semantics are owned by
  [`parametric-constraint-system.md`](parametric-constraint-system.md) §6 — not restated here.
  Compile ignores them: instances render the saved (solved) geometry and never re-solve.
- **Primitive `uid`** — every primitive dict, nested `block_instance` records included, carries a
  stable `uid` (mint / carry rules: that spec §6.1). Legacy dicts gain one on the next save.
- **Origin fixed at (0,0)** — the definition origin is the editor scene's (0,0) cross; `origin` is a
  vestigial field written `[0, 0]`. A definition with a non-zero `origin` is migrated **on open** by
  translating its seeded primitives (nested instances included) by `−origin`; instances render
  identically because compile already applies `translate(−origin)` (that spec §6.5 / D4).
- **Reference lines persist as scaffolding** — every reference line is saved (`reference_line`
  joins the definition primitive factory) and re-seeded on reopen; a **non-printed** one is
  scaffolding (`block_definition.is_scaffold`): skipped by compile, snap points and Explode, and a
  definition holding only scaffolding is not savable. A printed one renders dashed (that spec D23;
  item behaviour in `2d-geometry.md`).

**`.fpdb` schema 2 — `bundled` (library files only).** A library save of a definition that nests
others writes `"schema": 2` plus `"bundled": { "<id>": { /* full definition */ }, … }` holding every
transitively nested definition (`BlockRegistry.bundle_for`); a definition with no nested references
is still written as schema 1, and **schema-1 files load unchanged**. Loading / reloading adds a
bundled definition only when its id is absent (**the project copy wins**), then the file's own
definition; a file that would form a nesting cycle is skipped with its reason in the load summary.
`index.json` is unchanged (one block per file). The `.fpd` project embed is unchanged in shape —
nested records ride inside each embedded definition's `primitives`.

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
  (icons), `ribbon_bar.py` (group/button API), `geometry_2d.py` (the captured primitives'
  `to_dict`/`from_dict` + `DisplayableItemMixin`), `snap_engine.py` (insertion + geometry + text-box snap).
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
- **Delete definition nested in another (2026-09-30):** `delete_block_definition` also refuses
  while any other definition nests it, directly or indirectly (`BlockRegistry.users_of`); the
  Manager's Delete names the users (`Model_Space.block_users_message`: "“B” is used inside: A, D —
  explode or remove it there first."). A linetype is also refused while lines use it — see
  "Linetype capability (LT3)".
- **Missing nested definition (2026-09-30):** a nested record whose id is not in the registry
  compiles to a red box-with-diagonal **placeholder** (never a crash); a project load lists the
  missing ids and their users in a "Missing Nested Blocks" warning, and a library load's summary
  counts them ("N nested block(s) missing").
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
  callers resolve it as **Overwrite / Rename / Cancel** (2026-09-23, block polish): the Manager's
  Save-to-Library catches it (Rename → `set_block_metadata`, then retry); the Block Editor's
  `BlockSaveDialog` pre-probes with `block_library.find_collision` so the choice is made before
  commit (a residual race falls back to `themed_confirm`). Overwrite passes `overwrite=True`.
  Prevents the earlier silent-overwrite data loss where two blocks named the same string clobbered
  each other's library entry.
- **Make-from-selection with non-primitives selected:** non-primitive items ignored/refused with a
  message; an all-non-primitive selection makes no block.
- **Corrupt `.fpdb` / stale `index.json`:** tolerant load — skip + log, like the title-block library.

## Performance

- **Shared-definition rendering is the perf contract:** many instances of one definition must stay
  responsive because they share one geometry object and one render-op list; instance `paint()` is a
  transform + stroke of the shared paths. A guard/bench asserts N-instance responsiveness and that no
  per-instance geometry copy is created.
- **Nested blocks (2026-09-30):** flattening keeps one compile per definition (guard linked under
  "The flyweight core"). **Block Manager rebuild bar (user-ratified 2026-09-29):** 300 definitions ×
  50 primitives with depth-2 nesting rebuild in a **median of 5 ≤ 50 ms** (measured ~1.4–2.4 ms
  with the one-pass `BlockRegistry.users_map`). No suite guard (host-noise); a session bench only —
  a `perf`-marked guard is an open follow-up.

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
- [ ] **Placement:** browser double-click → `place_block` mode; ~~2-step (position → rotation, Enter=0°)~~
      **one click at 0°** (amended 2026-09-30 — Decision 8), snapped, level-aware, repeat until Esc.
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
   HUD `angle_deg`, repeat-until-Esc — *the rotation step was retired 2026-09-30, Decision 8*); `make_block_from_selection` (consume → def + instance, one
   undo); the three seam fixes (`translate` movability, `block_instance` copy/paste branch, orphan
   placeholder); ribbon Make/Insert/Manager buttons. Origin = selection bbox top-left in v1 *(superseded at CS1: bbox centre → (0,0), D24)*
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

## Block Editor (v2)

> Status: **built — BE1–BE5** (2026-09-07, branch `feat/block-editor-v2`). WHAT locked via
> `/grill-me`; HOW in `docs/superpowers/specs/2026-09-07-block-editor-v2-design.md`. This section is
> the durable contract; the dated doc holds the fork rationale + slice plan. Fills the Editor that
> DD-10 and the "Open in Editor" stub reserve. Native-curve import (arc / full-ellipse / spline →
> editable primitives, `preserve_curves`-gated on the DXF worker so the underlay path is unchanged;
> schema in `2d-geometry.md §3.5.3`) + import rotation **ship in the curve-fidelity task**.
> Partial-ellipse + PDF-Bézier curve import **shipped 2026-09-23 (block polish)** — exact, no
> tessellation; contract in `2d-geometry.md §3.5.3`. **Deferred (P1 follow-ups):** block attribute
> authoring, thumbnails, strict ribbon-tab hiding.

The **Block Editor** is the authoring surface for `BlockDefinition`s: a standalone canvas tab where
the user draws/imports 2D geometry around the fixed (0,0) origin, sets metadata, and Saves a definition into the
project registry — **disconnected from all model views**.

### Contract

- **Editor scene = a standalone `Model_Space` instance** (scratchpad), hosted in a closable
  `central_tabs` tab via a `BlockEditorWidget` + `Model_View`, managed by a `BlockEditorManager`
  (mirrors `ElevationManager`). It runs **headless of the level/plan-view managers** (block geometry
  is definition-local/2D) and inherits the full 2D toolchain (drawing controllers, snap, HUD, grips,
  selection-manipulator, `push_undo_state`) for free. Undo is per-instance-isolated by construction.
  **Seeding** (edit / clone / make-from-selection via `seed_from_dicts`) resets the editor's undo
  history so the seeded geometry is the baseline and cannot be undone away (2026-09-24 — before this
  the first Ctrl+Z after an edit restored the empty construction snapshot and wiped the block).
  **Fit on open (2026-09-30):** seeding also frames the view on the block's own pen-free geometry
  (`BlockEditorWidget.fit_view_to_block` → `Model_View.fit_scene_rect`, deferred to first show when
  not yet shown); a blank editor keeps the default view, and re-focusing an open tab never re-seeds
  or re-zooms.
- **The editor never mutates the project scene** except through two calls:
  `Model_Space.commit_block_definition(...)` (Save) and S3 `save_to_library` (opt-in). It is a
  scratchpad; the definition lands in the **project** `Model_Space`.
- **`commit_block_definition(*, block_id, name, library, series, primitives, origin, place_instance,
  source_items, place_at, constraints)`** is the arm's-length commit (DD-11 posture): **new** (`block_id is None` →
  `BlockDefinition.new` → `register`) vs **edit-in-place** (`block_id` → `set_primitives` version-bump
  + repaint-all + metadata update; `constraints` stored on the definition); optional delete of
  `source_items` + one instance at `place_at` (default `origin`); **exactly one undo**. `make_block_from_selection` / the Quick Block path are thin callers of the
  same core.
- **Entry points:** Create Block button — since 2026-09-30 the Block Editor tab's **New** (blank | seeded-with-selection-**copy** → new `id`; `_open_block_editor`); Block Editor tab **Open…** (`BlockOpenDialog`, see "Open picker" below → `edit_definition`); Manager →
  Create new (blank); Manager → Create new based off selected (clone geometry + `attributes`, new
  `id`); Manager → **Open in Editor** (same `id`, edit-in-place); right-click **Edit Block** on a
  block instance (plan *or* Block Editor) and double-click on a nested instance (Block Editor only)
  — 2026-09-30. Open in Editor and Edit Block share one path, `BlockEditorManager.edit_definition`
  (focus an open tab unchanged, else open + seed). **Quick Block is retired**
  (`model-space-containment-contract.md` C7): under C1's placement-only Model Space there is no loose
  *model* geometry to consume-and-bake, so the separate Quick Block button and its `MakeBlockDialog`
  instant-bake path are gone. The block entry commands (New / Open / Manager / Insert) live in the
  **Block** group of the permanent **Block Editor** ribbon tab (*as-built 2026-09-30* — they moved
  there from the C7 Architecture "Block" group, which no longer exists; wiring owned by
  `ribbon-bar.md` §3.4).
- **Open picker (2026-09-30)** — `block_open_dialog.BlockOpenDialog` (a `HouseDialog`; metrics
  `theme.M.BLOCK_OPEN_*`): a search box over a tree of **Project** (the project's definitions) then
  **Library** ▸ library ▸ series holding **library-only** blocks (on-disk entries whose `id` is not
  in the project — `blocks_browser.library_only_entries`, the same catalog the Blocks browser uses);
  empty roots are omitted; empty states "No blocks yet — create one with New" / "No blocks match".
  **Open** (or activating a leaf) on a library-only block first loads it into the project via
  `blocks_browser.ensure_block_loaded` (one undoable `load_blocks_from_files` batch; a failed load
  shows the shared load-failure message and the dialog stays open); the caller then runs
  `block_editor_manager.edit_definition(chosen_id)`. Guards: `tests/test_block_open_dialog.py`,
  `tests/test_block_editor_ribbon_tab.py`.
- **Seeded create is non-destructive:** the editor works on a **copy**; the model is touched only at
  Save via a "replace source with an instance?" prompt (default yes), atomically in the one commit
  undo (source items passed as `source_items`).
- **Edit-in-place propagates at Save** (flyweight invariant: `set_primitives` → every
  `on_definition_changed`). *As-built (2026-09-23, block polish, `434066c`):* re-Save of a saved
  block is silent, so `BlockSaveDialog`'s "edit" context is no longer reached; instead the status
  line reports `Saved block "X" — updated N placed instance(s)` (suffix only when N > 0).
- **Import DXF/DWG/PDF → editable primitives** via the pure `geometry_import.geom_dicts_to_primitives(
  geoms, import_scale, *, lineweight)` (kind mapping line/circle/arc/path_points/ellipse/spline→
  primitives, text skipped + counted), reusing the async extraction workers + the `import_scale =
  real_mm/source_units` convention. The dialog is `BlockImportDialog` (a flattened
  `UnderlayImportDialog` subclass with `preserve_curves` on — preview UX in `underlay-workflow.md
  §10.14`). **SVG deferred.**
- **Metadata authored in the editor** (name + editable library/series combos) via a consolidated
  `BlockSaveDialog` (a `HouseDialog`; the old `MakeBlockDialog` was deleted 2026-09-26), validated at Save (reuse `set_block_metadata` rules;
  rename keeps `id`). The **Manager detail panel stays read-only** — the editor is *the* editing
  surface (resolves `todo_open.md:66`).
  *As-built divergence (2026-09-23):* the dialog opens only on a block's first Save and on Save As
  (new `id`), so renaming a saved block **in place** is not reachable from the editor; the Manager's
  collision Rename (`set_block_metadata`) is the only in-place rename. Tracked in `todo_open.md`
  ("Rename a saved block in place from the Block Editor").
- **Origin (amended CS1, 2026-10-02):** the definition origin is **always the editor scene's fixed
  (0,0)** (`BlockEditorWidget.origin_point()`); users design around the white origin cross or Move
  geometry to it. The snapped Set Origin tool, its persistent red marker and the `bbox_top_left`
  default are **retired** (parametric-constraint-system.md D4; migration of old definitions: "Input
  / Output" above). **Create Block from selection** (`seed_from_selection`) translates the copied
  selection so its pen-free **bounding-box centre** (scaffolding excluded) sits on (0,0) and
  remembers that plan point; a replace-on-save places the new instance there via
  `commit_block_definition(place_at=…)`, so nothing moves visually (D24).
- **Restricted "Block Editor" ribbon context** while an editor tab is active (2D geometry +
  modify/transform + constraints + editor verbs only); property panel reused; no level chrome.
  *As-built 2026-09-30:* realised as the permanent **Block Editor** base tab whose editor-only groups
  (Definition / 2D Geometry / Edit / Modify, and since CS1 Constrain / Inspect —
  `parametric-constraint-system.md` §10) are enabled only while a Block Editor canvas tab is
  current, and disabled (with an explanatory tooltip) otherwise; the Block group
  stays live. Mechanism owned by `ribbon-bar.md` §3.4 (Rule A).

### Save, import placement & library (2026-09-23, block polish)

- **Save / Save As** — Block Editor ribbon verbs; Ctrl+S / Ctrl+Shift+S route here when a Block Editor
  tab is active (`MainWindow._dispatch_save` / `_dispatch_save_as`, else project Save / Save As).
  `BlockEditorWidget.save()`: a never-saved editor opens `BlockSaveDialog`; afterwards Save is
  **silent** — an in-place `commit_block` under the current name/library/series that also rewrites
  the library copy when one exists (`block_library.source_status(defn) != "project-only"`).
  `save_as()`: dialog prefilled `"<name> copy"`, commits a **new** definition (original + its
  instances untouched) and the editor then edits the new block. Every commit emits
  `saved(widget, defn)` → `BlockEditorManager` retitles the tab `Block: <name>` and re-keys it by
  definition id (so `open_for_definition` focuses it instead of duplicating).
- **`BlockSaveDialog`** — Library / Series are `ui_kit.CreatableSelector`s (`ui-design-system.md`)
  fed by `library_tree_for(project)` = on-disk folders (`block_library.list_folders`) ∪ the
  project's used library/series; Series follows Library; "+" creates the folder on disk at once
  (`block_library.create_folder`) and selects it. Options are `ToggleSwitch`es; "Also save to
  library" defaults ON and remembers the last choice (QSettings `BlockEditor/save_to_library`).
  With it on, a clash with a **different** block's file (`block_library.find_collision`) is
  resolved in-dialog **before** commit: Overwrite / Rename (dialog stays open on Name) / Cancel.
- **Import placement by base point** (`import_with_params`) — the dialog's picked base point is the
  placing grip. *Insert at origin* ON → the base point lands on the block origin, the fixed (0,0).
  OFF → geometry is added base-at-origin, selected, and handed to Move with the base preset
  (`Model_Space.begin_move_from(base)` — skips Move's base click; same commit / undo / Esc as
  Move). *(Pre-CS1, an empty editor with no pinned origin pinned it at the base point — retired
  with the movable origin.)*
- **Imported primitives** take the standard new-geometry line weight (`lineweight=` fed from
  `_geom_color_lw()` — owned by `2d-geometry.md §1.1`) and are selected as one batch
  (`select_items` — `selection-mode.md §5.9`).
- **Text compiles into blocks** — `gather_primitives` includes `_texts` (glyph-outline compile, C5).
  Retires the "text-in-blocks" deferral.
- **Library layer** — root = `app_data.block_library_dir()` (precedence + System-Settings row →
  `settings-dialog.md §4.5b`). New `block_library` API: `list_folders`, `create_folder`,
  `find_collision`, `entry_path`, and `add_change_listener` (held weakly — `WeakMethod` for bound
  methods; fired on save / delete / create_folder).
- **Blocks browser = library view** — every on-disk Library/Series folder (even empty) + every
  indexed `.fpdb`, merged with the project registry (a library entry whose `id` is in the project
  lists once, as project). Library-only leaves are italic/dimmed; double-click loads them via
  `load_blocks_from_files` then emits `blockActivated` (a refused/unreadable load reports and does
  not place). *Since 2026-09-30 (behaviour unchanged):* the catalog and the loader are module
  helpers shared with the Open picker — `library_only_entries(scene, root)` (the
  `(library, series, name, block_id, path)` tuples of library entries not in the project) and
  `ensure_block_loaded(scene, block_id, path, name, root, parent)` (True when the id resolves in the
  project afterwards; loads a library-only block as one undoable batch, else shows the shared
  load-failure message). *Since 2026-09-30:* leaves also drag out, activation places into the **active**
  canvas, and a cycle refusal is checked **before** any load — see "Nested blocks" below. Bold folder rows + sibling-browser tree chrome; collapsed folders survive refresh;
  refreshes on `blockDefinitionsChanged`, the library change listener, and `showEvent`. (DD-12 still
  holds: the Manager's Load stays a browse-anywhere file dialog.)

Guards: `tests/test_block_save_library.py`, `tests/test_block_polish_bugs.py`,
`tests/test_block_curve_import.py`.

### Nested blocks, drag-and-drop & Explode (2026-09-30)

Built on `feat/nested-blocks` (`345f1b7`). This is the durable contract; the HOW, rejected
alternatives and as-built amendments live in
[`2026-09-29-nested-blocks-design.md`](../superpowers/specs/2026-09-29-nested-blocks-design.md).
Record shapes: "Input / Output" above.

- **Registry — the one resolution choke point.** `BlockRegistry` (`block_registry.py`) fronts the
  project `Model_Space._block_definitions`. `get` resolves (and injects itself as the definition's
  nested resolver); `add` inserts or replaces, then invalidates. Dependencies are derived **by id
  from definition contents**, never object back-references (undo restore recreates definition
  objects): `closure`, `users_of` (direct + indirect users), `users_map` (every definition's users
  in one pass), `would_cycle(host, candidate)`, `missing_nested`, `bundle_for`, and
  `merged_with_file` (the single merge rule shared by library load and drag preview).
  `invalidate(id)` drops the compile caches of *id* and every user and repaints their live
  instances in every attached scene (plan + open editors). Undo restore and `.fpd` load still
  write the store dict directly; `get` injects the resolver lazily so those definitions resolve too.
- **Editors borrow the registry read-only.** A Block Editor scene resolves through the project
  registry (`Model_Space.borrow_block_registry`); its own `_block_definitions` stays private to its
  undo snapshot, its instances take no definition back-reference (they repaint via `invalidate`),
  and closing the tab detaches its scene. Registry writes a drop triggers (a library load) go to the
  owning project scene.
- **Authoring nested blocks.** The editor saves its placed instances as nested records
  (instances-only blocks are savable), re-places
  them when seeding, and admits `block_instance` records on paste. Save re-checks `would_cycle`
  (refused: "A block can't contain itself") and invalidates every user; the status line adds the
  count of blocks that use the saved one. Nested instances are gathered **after** the primitive
  lists, so draw order across an editor round-trip is by type, not authoring order.
- **Delete a selected instance** (Delete key, plan and editor) removes it through
  `remove_block_instance` — one undo step.
- **Drag-and-drop.** Blocks-browser leaves drag out as `MIME_BLOCK` (payload `{"id", "path" | null}`
  — the path set for library-only leaves; every in-app drag MIME type lives in `mime_types.py`).
  **Plan views and Block Editor views accept; detail views refuse** (they share the plan scene but
  are not placement surfaces); paper and elevation views are other view classes. Hovering enters
  `place_block` with its ghost on the snapped point (a library-only leaf previews from a temporary,
  unregistered definition — nothing loads on hover); a drop that would form a cycle is refused with
  a footer reason ("B contains A — a block can't contain itself"). The drop places at the snapped
  point at **0°** (plan: active level), selects it, pushes **one undo step**, and restores the prior
  mode. Browser double-click enters `place_block` in the **active** canvas (plan or editor) with the
  same refusal, checked before any load. **A library-only (italic) leaf costs two undo steps**
  (user decision, 2026-09-29): the project load, then the placement — in an editor, the load is a
  project step and the placement an editor step.
- **Explode — Block-Editor-only (containment C1).** Modify ▸ **Explode** (small button, enabled while
  the selection holds a block instance; icon `graphics/Ribbon/explode_icon.svg`, the "shattered
  square" candidate the user picked) and right-click **Explode** on an editor block instance.
  `block_explode.explode_instances` re-creates the definition's primitives at their exact posed
  scene positions and turns nested records into new instances at the composed pose; when any
  selected block nests others, one prompt asks **This level only / Flatten all**. One undo step;
  the results become the selection; missing or imported-reference definitions are left in place
  (status message only); a failure part-way restores the prior state with no undo step. Non-printed
  reference lines (scaffolding) are not exploded. Constraints on an exploded instance's insertion
  point cascade-delete in the same undo step ("N constraint(s) removed" —
  `parametric-constraint-system.md` §8). Plan
  scenes never offer Explode. (Unrelated to the still-unreachable `SceneTools.explode_selected_items`
  — `scene-tools.md`.)
- **Edit Block** — see Entry points above (right-click in plan and editor; nested double-click in
  the editor; `BlockEditorManager.edit_definition`). Saving the nested block repaints every open
  host tab and placed host.
- **Block Manager.** A **"Used in"** column counts the definitions nesting each row (direct +
  indirect, from `users_map`); "Instances" stays the placed-instance count. Delete refusal and the
  missing-nested warning: see "Edge Cases & Error Handling". Save-to-Library writes the schema-2
  bundle (Manager and editor alike).

Guards: `tests/test_nested_block_compile.py`, `tests/test_block_drag_drop.py`,
`tests/test_block_explode.py`, `tests/test_block_library_bundle.py`,
`tests/test_block_usage_counts.py`, `tests/test_block_instance_delete.py`,
`tests/test_block_editor_fit.py`, `tests/test_block_placement.py`.

### Pattern-tile capability (HF2)

Built on `hf2-pattern-renderer` (`53e1773`). Pattern semantics, the renderer, the Hatch patterns
folder and the shipped patterns are owned by [`hatch-and-fill.md`](hatch-and-fill.md) (D-A9,
D-A32–D-A34, D-A39) — not restated here. Block-system-owned facts:

- **`BlockDefinition.tile`** — optional `{"w", "h", "row_shift", "size"}` (or None); a block with a
  tile *is* a pattern (a capability, not a kind). Additive `.fpdb` / embed key — **no `schema`
  bump**; absent ⇒ None. `set_tile` bumps the version and invalidates like a content edit. Library
  `index.json` entries gain a `tile` flag (readers tolerate older entries without it).
- **Typed compile** — `render_ops()` returns shared `RenderOp`s
  (`firepro3d/render_op.py`, file governed by `hatch-and-fill.md`; LT3 extends it) of kind `stroke` / `fill` / `pattern` / `text`;
  a primitive's per-item `fill` compiles to a `fill` or `pattern` op ahead of its stroke, and
  `BlockInstance.paint` dispatches on `kind` (fill/pattern ops through the hatch renderer). Nested
  flattening maps each op's path (and pattern origin) through the nested pose.
- **Dependencies** — `block_registry.referenced_ids(defn)` = nested records **plus** primitive
  hatch-fill pattern refs (legacy names canonicalised); `closure`, `bundle_for`, `would_cycle`,
  `users_of` / `users_map` and `invalidate` all follow it, so a pattern is bundled with, cycle-checked
  against and invalidates its users like a nested block.
- **Pattern blocks are never symbols** — placing one is refused with a status message
  (`block_library.PATTERN_REASON`) at the shared `set_mode("place_block")` entry and again at the
  placement click; paste skips them; Block Editor save of a tile on a block placed as a symbol is
  refused (`Model_Space.symbol_use_refusal` — placed instances + definitions nesting it; the HF2
  name `pattern_use_refusal` remains a tile alias), and a newly saved pattern is registered but
  never placed.
- **Blocks browser** — tiled leaves carry a pattern badge; right-click a leaf → **Edit Block** (loads
  a library-only leaf into the project first, then opens it in a Block Editor tab; no placement).
  Block Editor tile authoring (toggle, frame, panel) → `hatch-and-fill.md` D-A32.

Guards: `tests/test_render_op_compile.py`, `tests/test_pattern_placement_refusal.py`,
`tests/test_blocks_browser_edit_menu.py`, `tests/test_tile_authoring.py`.

### Linetype capability (LT3)

Built on `feat/lt3-linetype-renderer` (`be7c88a`). Linetype semantics, the unit reading, the
renderer, the missing badge and the Linetypes folder are owned by [`linetypes.md`](linetypes.md)
"LT3" (LT3-2, H3-e, H3-g, H3-h) — not restated here. Block-system-owned facts:

- **`BlockDefinition.repeat`** — optional `{"length", "size"}` (or None); a block with a repeat
  *is* a linetype (a capability, not a kind). Additive `.fpdb` / embed key — **no `schema` bump**;
  `set_repeat` bumps the version like `set_tile`. Library `index.json` entries gain a `repeat` flag.
- **Linetype blocks are never symbols** — the pattern refusal paths (shared `set_mode` entry,
  placement click, drag / browser gate, paste skip) also refuse `repeat` blocks
  (`block_library.LINETYPE_REASON`).
- **Dependencies** — `referenced_ids` also follows a styled primitive's `style.linetype` block id;
  the delete refusal additionally counts live styled primitives in the plan / an open Block
  Editor (`Model_Space.linetype_user_contexts`), and `block_users_message` names them.
- **Compile** — stroke `RenderOp`s carry definition-local `pieces` + `linetype`; nested flattening
  maps them with the path, so a nested block keeps its own definition's dash phase.
  `BlockInstance.paint` routing → `linetypes.md` H3-f.

### Block Editor capability slot (LT4)

Built on `feat/lt4-repeat-authoring` (`b9b1094`). The authoring contract is owned by
[`linetypes.md`](linetypes.md) "LT4" and the shared frame by [`hatch-and-fill.md`](hatch-and-fill.md)
§2 — not restated here. Block-system touch points (each a pointer):

- **One capability slot** — a Block Editor scene holds at most one capability,
  `Model_Space.block_capability` (tile or repeat), set through `set_block_capability`; it joins
  the undo snapshot and is loaded from the definition on open → `linetypes.md` H4-a.
  `commit_block_definition(..., capability=)` writes it to the definition, so **Save As keeps it**
  (LT4-11c) → H4-e.
- **Never a symbol** — `Model_Space.symbol_use_refusal(block_id, kind)` (tile or linetype wording;
  `pattern_use_refusal` is its tile alias) refuses turning either capability on, and saving it, while
  the block is placed or nested → `linetypes.md` LT4-11a / H4-e.
- **Blocks browser** — the capability badge (pattern or linetype) and its tooltip now show on
  **library** rows as well as project rows, read from the `index.json` `tile` / `repeat` flags →
  `linetypes.md` LT4-10 / H4-g. The delete refusal's linetype wording → LT4-11e.

### Placement Weight / Linetype overrides (WM2)

Built on `feat/wm2-placement-overrides` (`a65daf67`). The override contract is owned by
[`linetypes.md`](linetypes.md) "Weight model" + "WM2 — as built" — not restated here.
Block-system touch points (each a pointer):

- **Placement + nested-record slot** — `BlockInstance.overrides` / a nested record's optional
  `"overrides"` key (omitted when As Authored); `place_block_instance(..., overrides=)` at every
  restore site → WM2 H1 / H3.
- **Compile** — `_nested_ops` applies a record's overrides to the child's mapped ops (outermost
  wins); `_load_prim` normalises them → WM2 H2. Compiled definition ops stay the flyweight; a
  placement's override is a per-instance derived list.
- **Explode** — bakes the instance's override onto primitives and composes it onto nested
  children → WM2 H6 (Q6 / Q7).
- **Dependencies** — a nested record's linetype override is a ref in `prim_refs` (bundling,
  cycle check, delete refusal "used by blocks inside") → WM2 H4.

### Deferred (v2.x)

SVG import; attribute **authoring** (the `attributes` field is carried by clone, not edited);
trace-over-underlay import fallback; import layer-subset selection; calibrate-by-pick import scale;
annotative `scale_mode`. *(Text-in-blocks shipped 2026-09-23.)*

### Build order

BE1 `geometry_import` + `commit_block_definition` (headless core) · BE2 editor shell + entry-point
wiring + `BlockSaveDialog` · BE3 Set-Origin tool *(retired at CS1, 2026-10-02 — origin fixed at (0,0))* · BE4 import-into-editor · BE5 polish (its Quick
Block button was retired by containment contract C7) +
polish. Full slice detail + acceptance criteria in the dated design doc.
