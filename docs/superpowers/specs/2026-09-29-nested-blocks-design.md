---
status: proposal
last-verified: 2026-09-29
verified-commit: c60baa2
applies-to:
  - firepro3d/block_registry.py        # NEW — registry choke point (resolve / users_of / would_cycle / invalidate)
  - firepro3d/block_definition.py      # resolver-aware compile + text snap points; origin property
  - firepro3d/block_instance.py        # nested record schema (to_dict sans level)
  - firepro3d/block_explode.py         # NEW — explode_instances
  - firepro3d/block_library.py         # .fpdb schema 2 "bundled"
  - firepro3d/block_editor.py          # gather / seed / has_geometry / save message / Edit Block
  - firepro3d/block_manager.py         # "Used in" column, delete refusal
  - firepro3d/blocks_browser.py        # drag source
  - firepro3d/mime_types.py            # NEW — one home for drag MIME types
  - firepro3d/model_view.py            # block drop target
  - firepro3d/model_space.py           # registry wiring, delete fix, paste allow-list, commit guard
  - firepro3d/modify_tools_controller.py
  - firepro3d/scene_io.py              # missing-nested warning
  - main.py                            # Explode button, active-scene double-click, right-click entries
source-tasks:
  - "todo_open.md → [feature] Nested blocks — drag a block from the Blocks browser into the Block Editor, plus a Block Editor ribbon Explode (2026-09-29)"
  - "todo_open.md → [bug] Delete does nothing on a selected block instance (absorbed as step 1)"
---

# Nested Blocks — Design Spec

> **Status: proposal (unbuilt).** Phase 2 grill ratified the WHAT (2026-09-29);
> this document records the HOW agreed in Phase 3 brainstorming (all four design
> sections user-approved). Two framework behaviours are **unverified** and stay
> *as-proposed pending the Phase 4 probe* (marked P4 below).

## Goal

A block definition may contain placed instances of other blocks — **live
references**: editing B updates every A that nests it, anywhere it is shown.
Users build them by **dragging a block from the Blocks browser** onto the Block
Editor (nesting) or onto a plan view (normal placement), and turn a nested block
back into editable geometry with a Block Editor **Explode** command.

## Motivation

Reusable composite symbols (Revit nested families / AutoCAD nested blocks): a
fire-protection detail assembled from standard sub-symbols stays consistent when
a sub-symbol is revised. Drag-to-place is the natural gesture for a browser of
symbols. Containment contract C1 keeps Explode Block-Editor-only — Model Space
never holds loose authored geometry.

## Architecture & Constraints

- **Flyweight perf gate holds** (block-system "The flyweight core"): N instances
  of a definition stroke ONE shared render-op list; nesting never creates
  per-instance geometry copies.
- **Definitions stay level-less** (contract C3): nested records carry no level.
- **Acyclic:** no definition may contain itself directly or transitively.
- **The Block Editor's own registry is wiped by its undo restore**
  (`Model_Space._restore_network` clears `_block_definitions`), so the project
  registry is **never aliased** into an editor scene — editors borrow it for
  resolution only.
- **Undo restore recreates definition objects** → dependency relationships are
  derived **by id** from definition contents, never held as object back-refs.
- **One fact, one home:** snap-matrix rows stay in `snapping-engine.md §5`;
  Z-order stays in `view-relationships.md §7.3`; containment invariants stay in
  the contract (it gains one clause).

## Design Decisions

### D1 — Flatten at compile (chosen over paint-time recursion and copy-on-save)

A's cached render-ops = A's own primitives + each nested B's cached ops mapped
through the nested pose, then A's origin shift. Compiled once per definition.
Every consumer that walks `render_ops()` / `text_snap_points()` — instance
paint, `boundingRect`/`shape` (HALO), snap — works unchanged.
*Rejected:* paint-time recursion (every consumer must learn to recurse; cost
grows with depth × instances); copy-on-save (duplicates data, breaks the live
reference through load/library paths).

### D2 — Nested record schema: inline `block_instance` records

Nested entries live **inside** `primitives`, in draw order (stacking between A's
own linework and B is preserved), using the placed-instance record shape minus
level fields:

```jsonc
{ "type": "block_instance", "block_id": "<B id>", "pos": [x_mm, y_mm], "rotation": 30.0 }
```

`pos` is definition-local (A's coordinates, before A's origin shift); `rotation`
is Y-up CCW degrees (the `BlockInstance.pose_transform` convention). No new
top-level key; files without such entries load unchanged.

### D3 — `BlockRegistry` (new `block_registry.py`) is the single choke point

Owned by the **project** `Model_Space`. API (names as-proposed; grep before
adding — VC4):

- `get(id)`, `add(defn)`, `replace(defn)`, `remove(id)`, `ids()` — every current
  write path routes here: `register_block_definition`, `_swap_block_definition`,
  `load_blocks_from_files` (today a direct dict write), undo restore, `scene_io`
  project load.
- `users_of(id) -> set[str]` — definitions that nest `id` directly or
  transitively (a walk over definition contents; registry-sized, cheap).
- `would_cycle(host_id, candidate_id) -> bool` — true if `candidate_id ==
  host_id` or `host_id ∈ nested_closure(candidate_id)`.
- `invalidate(id)` — clear the compile caches of `id` and every `users_of(id)`,
  then `on_definition_changed()` every live instance of those definitions in
  every scene (plan + open editors).

`Model_Space._block_definitions` remains the project's storage dict behind the
registry so existing readers keep working; readers that need resolution call
the registry.

### D4 — Editors borrow the registry read-only

An editor scene receives a reference to the project registry and resolves
nested B through it (`get_block_definition`, `place_block_instance`, the
place_block ghost, paste existence check). Its undo snapshot keeps capturing
**only its own instances** (nested records), never registry contents.

### D5 — `BlockDefinition` resolves through the registry

`BlockDefinition` gains a resolver (`registry.get`), injected when it enters the
registry. `_compile` and `text_snap_points` handle `block_instance` records:
resolve B, map B's cached ops / snap points through the record's pose, then
apply A's origin shift. Unresolved B → the existing red "missing block"
placeholder. `origin` becomes a property whose setter clears both caches (closes
the filed stale-origin task).

### D6 — Drag source and MIME home

New `mime_types.py`: `MIME_BLOCK = "application/x-firepro3d-block"`, and the two
existing duplicated literals (`paper_space.MIME_VIEW`, the project-browser sheet
type) move there. Payload JSON: `{"id": str, "path": str | null}` (path set for
library-only leaves). The Blocks tree becomes a `QTreeWidget` subclass mirroring
`project_browser._ProjectTree` (`mimeData`/`mimeTypes`, drag enabled); only
block leaves drag; tree chrome unchanged.

### D7 — Drop target reuses `place_block`'s ghost + snap

`Model_View` accepts `MIME_BLOCK` when its scene is the project plan scene or a
Block Editor scene (paper untouched — sibling task):

1. `dragEnterEvent`: decode; resolve the definition (library-only leaf →
   parsed into a **temporary, unregistered** definition for the ghost; nothing is
   loaded on hover). Cycle check (`would_cycle(edited_id, id)`, including the
   italic file's bundle) → on failure `ignore()` + footer reason ("B contains A —
   a block can't contain itself"). Else remember the current mode and enter
   `place_block` with that block.
2. `dragMoveEvent`: feed the position through the same move handler the mouse
   uses → ghost on the **snapped** point.
3. `dropEvent`: italic leaf → `load_blocks_from_files`; failure refuses with the
   double-click message. Then `place_block_instance(id, snapped, 0°)`, one undo
   step, select it, restore the mode. `dragLeaveEvent` restores the mode.

**P4 (unverified, first plan step):** switching scene mode inside Qt's drag loop
and feeding `dragMoveEvent` positions through the snap path. **Fallback:** a
view-painted drag-only ghost reusing the same snap call + the ghost paint
routine.

Browser double-click routes through `MainWindow._active_scene()` with the same
cycle refusal.

### D8 — Editor integration

- `gather_primitives` emits editor `BlockInstance`s as D2 records;
  `_has_geometry` counts them (instances-only blocks are savable); A's default
  origin bbox includes them.
- `seed_from_definition` recreates nested records via `place_block_instance`
  (not the undo-resetting primitive factory); `_add_primitive` handles instances.
- Paste allow-list (`modify_tools_controller` D13) admits `block_instance`
  records in the editor; existence check via the registry.
- `commit_block_definition` re-checks `would_cycle` (defence in depth), then
  `registry.invalidate(A)`.
- **Delete fix (absorbed bug):** `_remove_item_from_lists` / bulk delete route a
  `BlockInstance` through `remove_block_instance` (drops the backref, emits
  `blockInstancesChanged`), both scene roles, one undo step.

### D9 — Explode (`block_explode.py`)

`explode_instances(scene, instances, flatten: bool)`: for each instance, walk its
definition's `primitives`:

- primitive record → `scene._add_from_dict(rec)`, then `translate(pos − origin)`
  and `manip_rotate(rotation, pivot=pos)` (TextItem: `manip_translate`);
- nested record → a new `BlockInstance` at the **composed** pose; when
  `flatten`, recurse into it.

Remove the source instance; **one** `push_undo_state()`; select the results. The
command handler asks **one** house-style prompt first when any selected instance
contains nested records: *This level only* / *Flatten all*. Non-block items in
the selection are ignored. `SceneTools.explode_selected_items` is untouched.

### D10 — Ribbon, right-click, Edit Block

- **Explode** small button in the Block Editor Modify group (`_be_modify_buttons`),
  tooltip "Explode — break the selected block into editable geometry"; enabled
  only while the selection contains a `BlockInstance` (a per-button predicate in
  `_refresh_modify_buttons`). New `explode_icon.svg` on the 40-unit two-token
  modify-icon contract — **mockup-gated** before authoring.
- Nested instance right-click → **Edit Block** + **Explode**, wired into both
  context-menu paths (entity menu + selection fallback).
- Double-click a nested instance / Edit Block → open B via the Block Manager's
  existing Open-in-Editor path; an already-open B tab is focused instead.

### D11 — Library bundling (`.fpdb` schema 2)

```jsonc
{ "schema": 2, "id": "<A>", ..., "primitives": [ ... ],
  "bundled": { "<B id>": { /* full definition */ }, "<C id>": { ... } } }
```

- Save: `save_to_library` writes A's transitive dependencies (via the registry)
  into `bundled`. `index.json` unchanged (one block per file).
- Load / Reload: bundle first — add each bundled definition only if its id is
  absent (**project copy wins**); then the file's own definition; cycle check
  over the union; a looping file is skipped with its reason in the load summary.
- Schema-1 files load exactly as today.

### D12 — Counts, delete refusal, load warnings

- Block Manager gains a **"Used in"** column (`len(registry.users_of(id))`);
  "Instances" stays placed plan instances.
- Save message: "updated N placed instance(s) and M block(s) that use it".
- `delete_block_definition` + the Manager's Delete refuse while `users_of` is
  non-empty: "B is used inside: A, D — explode or remove it there first."
- Project load (`scene_io`) and library load report unresolved nested ids:
  "Missing nested block(s): …"; rendering falls back to the placeholder.

## Acceptance Criteria

(Ratified in the Phase 2 grill, 2026-09-29.)

- [ ] **AC1** Delete removes a selected block instance in plan and editor; one undo step restores it.
- [ ] **AC2** A real drag from the browser onto a plan view places an instance at the snapped drop point, 0°, active level, selected; one undo step.
- [ ] **AC3** Dropping B into A's editor and saving stores a nested reference; a plan instance of A renders B's pixels; editing + saving B changes the plan A's pixels.
- [ ] **AC4** A ghost follows the snapped cursor during a drag; an italic leaf auto-loads on drop; a clashing italic leaf refuses the drop and places nothing.
- [ ] **AC5** Cycle drags are refused (A onto A's editor; B⊃A onto A's editor) with a footer reason; a looping library file is skipped with its reason.
- [ ] **AC6** Explode is one level: primitive scene coordinates equal the instance's rendered positions at 30° (pixel-sampled); a nested C stays an instance; result selected; Ctrl+Z restores the single instance.
- [ ] **AC7** The flatten prompt appears when nested blocks exist: "Flatten all" leaves no instances; "This level only" keeps C.
- [ ] **AC8** Explode is enabled only while a block instance is selected; right-click on a nested instance offers Edit Block + Explode.
- [ ] **AC9** Saving A (nesting B, C) to the library and loading into a fresh project yields A, B, C with A fully rendered; loading where B exists leaves the project's B unchanged.
- [ ] **AC10** Deleting B while A nests it is refused, naming A; B remains.
- [ ] **AC11** "Used in" counts direct + indirect users; the save message includes the user-block count.
- [ ] **AC12** Edit Block opens (or focuses) B's editor tab; saving B repaints the open A tab.
- [ ] **AC13** Browser double-click places into the active canvas (editor → nested flow).
- [ ] **AC14** A missing nested definition loads as a placeholder and is listed in the load warning.

## Verification Checklist

- [ ] All AC guard tests pass and each is shown RED with its change reverted (VC3).
- [ ] P4 probe result recorded; D7 either confirmed or switched to the fallback (then re-approved).
- [ ] Keep-green: every `tests/test_block_*.py`, `test_blocks_browser_style.py`, `test_model_browser_blocks.py`, `test_reference_compile.py`, `test_reference_definition_import.py`, `test_snap_engine_primitives.py`, `test_snap_text_points.py`, `test_project_browser_sheets.py`, `test_modify_tools_ribbon.py` (exact set extended with Explode), `test_icon_theming.py` (`_MODIFY_ICONS` extended), ribbon roster/contextual tests.
- [ ] Full suite in alphabetical chunks on the native platform (never forced offscreen); pre-existing failures proved at base (VC7).
- [ ] VC9 whole-diff seam review (Large build).
- [ ] Flyweight perf gate: 200 plan instances of a 2-level nested block — one compile per definition, no per-instance op copies.
- [ ] User smoke in the real app.

## Input / Output

See D2 (nested record), D6 (drag payload), D11 (`.fpdb` schema 2). The `.fpd`
project embed is unchanged in shape: definitions already embed via `to_dict`,
and nested records ride inside `primitives`.

## Examples

- **Nest:** open "Riser Detail" (A); drag "Gate Valve" (B) onto the canvas → a
  ghost tracks the snapped cursor; release → B placed at 0°, selected. Save A →
  every placed Riser Detail now shows the valve.
- **Live edit:** double-click the valve inside A → "Gate Valve" opens in its own
  tab; change it, Save → the open Riser Detail tab and every placed Riser Detail
  repaint.
- **Explode:** select the valve in A → Explode → its lines/arcs appear exactly
  where it was drawn, selected; the valve's own nested "Handwheel" either stays a
  block (This level only) or explodes too (Flatten all).
- **Refuse:** drag "Riser Detail" onto its own editor → ⛔, footer "Riser Detail
  can't contain itself".

## Existing Code Context

Verified in the Phase 1b reuse sweep at `c60baa2` (two read-only sweeps,
spot-checked): see the task's Details in `todo_open.md` and this doc's D-sections.
Key reuse: `place_block_instance`, `BlockInstance` resolver + `pose_transform` +
`to_dict`, `_add_from_dict`, primitive `translate`/`manip_translate`/`manip_rotate`,
`_active_scene`/`_active_editor_widget`, `project_browser._ProjectTree` drag
pattern, `PaperGraphicsView` MIME drop pattern, `load_blocks_from_files`,
`get_effective_position`, `themed_icon`.

## Edge Cases & Error Handling

- An unsaved new block in the editor has no id yet, so nothing can nest it and
  no drop into it can form a cycle; `would_cycle` is skipped (always false) until
  its first save assigns an id.
- Library-only leaf dropped into the editor: the load is a **project** undo step;
  the instance is an **editor** undo step (Ctrl+Z in the editor keeps the load,
  like double-click).
- Deep nesting: compile recursion depth = nesting depth (acyclic guarantees
  termination); caches make repeated resolution O(1) after first compile.
- A bundled definition whose id exists in the project with different content:
  project copy wins silently (ratified).

## Code Style & Testing

Google docstrings; relative imports inside `firepro3d/`; constants in
`constants.py`; mm scene units. Guard tests drive real paths (shown views,
real `QDrag`/mouse input, real `.fpdb` files in `tmp_path`) and assert
observable ground truth (scene coordinates, pixels, registry contents) — six
files: `test_block_instance_delete.py`, `test_block_drag_drop.py`,
`test_nested_block_compile.py`, `test_block_explode.py`,
`test_block_library_bundle.py`, `test_block_usage_counts.py`.
