---
status: current
last-verified: 2026-09-17
verified-commit: 6a36206
applies-to:
  - firepro3d/scene_io.py
  - firepro3d/network_codec.py
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
`Model_Space.SAVE_VERSION` and `project_info`, `scale`, `display_settings`,
`paper_display`, `levels`, `plan_views`, `active_level`, and the entity
collections: `nodes`, `pipes`, `annotations` (dimensions + notes), `underlays`,
`water_supply`, `design_areas`, the construction-geometry keys (`polylines`,
`draw_lines`, `reference_lines`, `draw_rectangles`, `draw_circles`, `draw_arcs`,
`draw_ellipses`, `draw_splines`, `polygons`), `texts` (unified `TextItem`
primitives, containment C5), `gridlines`, `walls`,
`floor_slabs`, `roofs`, `rooms`, `block_definitions` (embedded by id),
`blocks` (instances referencing definition ids), `constraints` (indexed against
`_tools._all_geometry_items()`), `detail_views`, `sheets`, `titleblock_template`.

**Atomic write:** the existing file is copied to `<name>.bak` first; on write
failure the backup is restored; on success the backup is removed.

### §3 — Load

`load_from_file` reads `version` (default 1), calls `_clear_scene()`, then
restores each section. Node ids are temp integers assigned at save and
rehydrated into a `id → Node` map that pipes/design-areas reference. Constraints
reference geometry by index into the same ordered `_all_geometry_items()` list.
Load is **best-effort on migrations** (title-block field migration failures log
and continue; missing underlay files warn via `themed_warn` but do not abort).

### §4 — Legacy migrations (load-only)

Load silently accommodates older files: the pre-2026 `construction_lines` key is
dropped; a legacy `HatchItem` block is migrated by re-creating filled
`PolylineItem`s; title-block address keys are migrated one-way. These are
load-only — save never writes the legacy shapes.

### §5 — Clean-drop invariant (containment C8 — built)

Under containment contract [C1/C8](model-space-containment-contract.md), Model
Space is placement-only. The format contract enforces a **clean-drop
invariant**:

- **Forbidden content is read-but-discarded, silently.** On load, the payload
  keys for loose geometry (`polylines`, `draw_lines`, `reference_lines`,
  `draw_rectangles`, `draw_circles`, `draw_arcs`, `draw_ellipses`,
  `draw_splines`, `polygons`), the top-level `texts` key (**standalone model
  text** — C1 retires it; block-content text lives in `block_definitions` and
  paper text in `sheets`, both of which survive), the `note` and `dimension`
  entries in `annotations`, the `constraints` block, and any legacy hatch are
  **not reconstructed**. A single `logging` line records dropped counts; there
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
- **Unaffected:** `block_definitions`, `blocks` (instances), `underlays`,
  `walls`/`rooms`/`floor_slabs`/`roofs`, `gridlines`, `nodes`/`pipes`, `sheets`
  (paper annotations, incl. the unified Text), `levels`, and all view/scale
  metadata persist normally.

## Acceptance Criteria
- [x] Save→load round-trips every surviving entity collection; `.bak`
      atomic-write behaviour holds.
- [x] (C8) A legacy `.fpd` with loose geometry / model text / notes / dimensions /
      constraints / hatch loads with those discarded, no exceptions, counts
      logged; a re-save omits them.
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
