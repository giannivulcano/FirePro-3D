---
status: current
last-verified: 2026-10-25  # SB2b Account: Marks payload keys + undo snapshot levels paragraph only (verified at ceacaab4), rest not re-audited; prior 2026-10-22  # gridline-hosted blocks Account: additive `host` / gridline `uid` keys + orphan-host drop (pointer only; verified at d44b0e11); prior 2026-10-20 HF3 Account: filled_regions key (loose-geometry list + C8 drop) pointer only (verified at 66880197); prior 2026-10-19 UP1 Account: fill-record no-version-bump pointer only (verified at 902c5c0e); prior 2026-10-18 HF1 Account: SAVE_VERSION 11 + colour_migration pointer; prior 2026-09-17  # + 2026-10-08 SV1 Account: `kind` sentence only (verified at b851b1aa) — rest not re-audited; + 2026-10-03 HF2 Account: §4 legacy-hatch sentence only (clean-dropped, hatch-and-fill H12; verified at 53e1773) — rest not re-audited
verified-commit: ceacaab4  # SB2b Account (Marks keys only); prior d44b0e11  # gridline-hosted blocks Account (host / uid keys only); prior 66880197 HF3 Account (filled_regions key only); prior 902c5c0e UP1 Account (fill pointer only); prior 084b43e0 HF1 Account (SAVE_VERSION sentence only); prior 6a36206
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
`Model_Space.SAVE_VERSION` (11 since HF1 — **version-gated**: `colour_migration.migrate_project_payload`
runs on the raw payload before any `from_dict` when `version < 11`, converting legacy default colours to
`token:auto`; `.fpdb` files carry a `colour_tokens: 1` marker instead of a version — rules owned by
[`hatch-and-fill.md` "HF1 build design"](hatch-and-fill.md). The 2D-shape `fill` record (UP1 two layers) adds **no** version bump or marker — a single read-time reader normalises the legacy record, see [`2026-10-18-up1-two-layer-fill-design.md`](../superpowers/specs/2026-10-18-up1-two-layer-fill-design.md) D1. 10 since LT2 was informational; primitive migration is
key-presence driven, and `load_from_file` installs the file's weight table + aliases
before any parse — see [`linetypes.md`](linetypes.md) "LT2" H-a / H-g) and `project_info`, `scale`, `display_settings`,
`paper_display`, `levels`, `plan_views`, `active_level`, and the entity
collections: `nodes`, `pipes`, `annotations` (dimensions + notes), `underlays`,
`water_supply`, `design_areas`, the construction-geometry keys (`polylines`,
`draw_lines`, `reference_lines`, `draw_rectangles`, `draw_circles`, `draw_arcs`,
`draw_ellipses`, `draw_splines`, `polygons`, `filled_regions` — HF3, record owned by
[`hatch-and-fill.md`](hatch-and-fill.md) "HF3 build design"), `texts` (unified `TextItem`
primitives, containment C5), `gridlines`, `walls`,
`floor_slabs`, `roofs`, `rooms`, `block_definitions` (embedded by id),
`blocks` (instances referencing definition ids), `constraints` (indexed against
`_tools._all_geometry_items()`), `detail_views`, `sheets`, `titleblock_template`.

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
The undo snapshot carries the same Marks data through the same `to_dict` / codec paths, and now also the
level list (`levels`), `plan_views`, `active_level` and per-underlay `underlay_levels`;
network_codec's load and undo paths add pipes and sprinklers with `mint=False`, so neither re-mints a Mark.

**Atomic write:** the existing file is copied to `<name>.bak` first; on write
failure the backup is restored; on success the backup is removed.

### §3 — Load

`load_from_file` reads `version` (default 1), runs `migrate_project_payload` (HF1) on the payload, calls `_clear_scene()`, then
restores each section. Node ids are temp integers assigned at save and
rehydrated into a `id → Node` map that pipes/design-areas reference. Constraints
reference geometry by index into the same ordered `_all_geometry_items()` list.
Load is **best-effort on migrations** (title-block field migration failures log
and continue; missing underlay files warn via `themed_warn` but do not abort).

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
