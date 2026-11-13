---
status: proposal         # designed, unbuilt (grill ratified 2026-11-13; design sections 1-6 approved 2026-11-13)
last-verified: 2026-11-13
verified-commit: 9caea64b
task: SB5 -- Hosting foundation (todo_open.md, System Blocks section)
owning-spec: docs/specs/element-parameters.md (new "Hosting" section at Account)
concept: docs/superpowers/specs/2026-09-29-system-blocks-concept-design.md (F7, G2, G4 groundwork)
base: 9caea64b (origin/main with SB4g merged; branch rebased 2026-11-13; local main lags, untouched)
applies-to:
  - firepro3d/element_uid.py           # new
  - firepro3d/hosted_dependents.py     # new
  - firepro3d/model_space.py           # addItem / removeItem / clear index, element_by_uid, paste remap, _bulk_delete cascade, push_undo_state / _restore_network refresh
  - firepro3d/block_instance.py        # _host_uid / element_host / host_uid serialization
  - firepro3d/network_codec.py         # uid / sprinkler_uid keys
  - firepro3d/scene_io.py              # load notice counts
  - firepro3d/section_manager.py       # uid-paired restore
  - firepro3d/modify_tools_controller.py  # footer reasons
source-tasks: "SB5 -- Hosting foundation; grill Q1-Q14 (2026-11-13); Phase 3 sections 1-6 + approach (index via add/remove override) approved 2026-11-13"
---

# SB5 -- Hosting foundation: design

## Goal

Every model element carries a stable `uid`; a scene uid index resolves it; one
`HostedDependents` hook pushes host changes to uid-hosted dependents; removing a
host cascades to its dependents. End goal (concept F7): placed tags (SB6) and
sheet tags (SB7) hosted on elements by uid.

## Motivation

Concept F7 (locked 2026-09-29): uid = uuid4 hex, minted on create, written by
`to_dict` on both serialization paths, re-applied on undo restore, new on
copy/paste; text pulled at paint; position pushed through one hook modelled on
wall -> opening `_reposition`; delete cascades through the uid index; a dangling
`host_uid` on load -> "?" placeholder + load warning. Today only walls,
gridlines, blocks, 2D geometry and text carry a uid; `element_host` is a
code-only object ref that is never saved (element-parameters D2 / D3).

## Ratified decisions (grill 2026-11-13, all via AskUserQuestion)

| # | Question | Ruling |
|---|---|---|
| Q1 | uid scope | **All model elements.** Add to rooms, floor slabs, roofs, wall openings (door / window / opening), floor voids, nodes, pipes, sprinklers, water supply, design areas, section / elevation / detail markers (walls, gridlines, 2D geometry, text, block instances already carry one). Levels, plan views, sheets, viewports, underlays keep their name / number keys. |
| Q2 | sprinkler vs node | **Separate uids.** Removing only the sprinkler affects only sprinkler-hosted dependents; the node keeps its uid. |
| Q3 | fittings | **No own uid** -- a fitting is a property of its node; a future fitting tag hosts the node. |
| Q4 | pipe split | **node1 half keeps the uid** (and its dependents), same as the Mark rule R1; the node2 half mints new. Replace-in-place transfers identity, never cascades. |
| Q5 | legacy file without uids | **Mint silently on load**; project not marked modified; persisted at next save (gridline precedent). |
| Q6 | duplicate uids in a file | **First in file order keeps it**; later duplicates re-minted; one status-bar notice "N duplicate element ids repaired"; file loads. |
| Q7 | hook scope | **Hook + gridline-hosted blocks** as its first real client. Wall->opening, slab->void, node->pipe/fitting keep their object-ref mechanisms (migration = filed follow-up). |
| Q8 | cascade paths | **Every final removal** cascades in its own undo step: Delete, Cut, room sprinkler re-populate, orphan-node removal, section-marker delete, trim / merge removals. Replace-in-place (pipe split) transfers the uid instead. |
| Q9 | paste | Host + dependent pasted together -> dependent **rebinds to the pasted host**. Dependent alone -> stays on its original host (today); original host gone -> skipped with the reason in the paste footer. |
| Q10 | element_host D2 / D3 | **Close both in SB5**: `element_host` saved as `host_uid` on both paths and across undo/redo; dangling on load -> "?" placeholders + one load notice; bound text refreshes on host move / grip, undo / redo. |
| Q11 | bound block on host delete | **Deleted with the host** in the same undo step; one Undo restores both, re-linked. |
| Q12 | uid in UI | **Hidden.** No panel row; Marks stay the user-facing ids. |
| Q13 | delete status text | **Generic suffix** when the cascade removed something: "Deleted 3 item(s) and 2 hosted item(s)" / "Cut 3 item(s) and 2 hosted item(s)"; gridline wording unchanged. |
| Q14 | absorbed scope (user choice; C2 phase-drift) | (a) deleting a sprinkler (any path) removes it from its design area's membership in the same undo step; (b) section-marker undo restore matches markers by uid, replacing the `_same_cut` heuristic (closes the filed "Depends SB5" section_manager line). |

## Architecture & Constraints

- **No add/remove choke point exists** (probe P2: ~293 direct `addItem` / `removeItem` sites, no override, no register helper). The index makes `Model_Space.addItem` / `removeItem` the choke point (D1).
- **PyQt dispatch (P4 probe, 2026-11-13, PyQt6 offscreen):** a Python `addItem` / `removeItem` override on a `QGraphicsScene` subclass catches every Python call, including `item.scene().removeItem(x)`; it does **not** see a child joining through `setParentItem` (the Sprinkler under its Node, `sprinkler.py`), nor `QGraphicsScene.clear()` (C++ path, no `removeItem`).
- **Both serialization paths share functions** (`to_dict` / `from_dict` / `network_codec`): the `.fpd` save and the undo snapshot carry whatever those write (Rule A: scene-io owns the dual-path rule). Model-space 2D geometry and text are not in `.fpd` (containment C8) -- their uids are unchanged by SB5.
- **Undo is snapshot-based** (`push_undo_state` / `_restore_network`), so a cascade inside an existing step is one Undo, and anything stored by uid re-links on restore with no extra code.
- The classes in Q1 share no base (`DesignArea`, `SectionMarker`, `DetailMarker`, `WaterSupply` are not `DisplayableItemMixin`s) -- uid code is helper functions, not a mixin.

## Design Decisions

| # | Decision | Ratified by |
|---|---|---|
| D1 | Index via `Model_Space.addItem` / `removeItem` override (rejected: explicit per-site register calls -- ~293 edits, a forgotten future site silently drops; no stored index -- O(n) per lookup, too slow for SB6 paint-time pulls) | approach question 2026-11-13 |
| D2 | uid storage + serialization (section 1) | section 1 approved |
| D3 | Index, validated lookup, duplicate repair (section 2) | section 2 approved |
| D4 | Copies re-mint; hosted remap; footer reasons; pipe-split transfer (section 3) | section 3 approved |
| D5 | `HostedDependents` module; `element_host` stored by uid; refresh at commit + undo / redo (section 4) | section 4 approved |
| D6 | One cascade function; DA membership; uid-paired section restore; AC10 restated (section 5) | section 5 approved |
| D7 | RiserSymbolItem gets no uid (derived from its pipe, like a fitting; a riser tag hosts the pipe) | section 1 approved |

### 1. Where the uid lives (D2, D7)

- New `firepro3d/element_uid.py`: `new_uid()` (uuid4 hex), `uid_to_dict(item, d)` (writes `"uid"`), `uid_from_dict(item, data)` (re-applies a saved uid; a record without one keeps the constructor's, which is Q5's silent legacy mint). Every serializer below calls these one-liners (the `display_overrides_to_dict` precedent).
- Storage: plain `self._uid` set in each class's `__init__` (the name walls / gridlines / blocks / 2D / text already use).
- Keys: Room, FloorSlab, RoofItem `"uid"` in `to_dict`; WallOpening / FloorOpening `"uid"` in their nested `openings` records; Node, Pipe, WaterSupply, DesignArea `"uid"` in their `network_codec` records; **Sprinkler** a sibling `"sprinkler_uid"` on its node's record (the `sprinkler_phase` pattern -- the sprinkler record is a nested property dict); SectionMarker, DetailMarker `"uid"` in `to_dict`.
- No uid: fittings (Q3), `RiserSymbolItem` (D7, never serialized). Walls, gridlines, blocks, 2D, text unchanged.

### 2. The uid index (D1, D3)

- `Model_Space.addItem(item)`: Qt add, then register `item` and every descendant carrying `_uid` into `self._uid_index` (uid -> item). `removeItem(item)`: unregister item + descendants, then Qt remove. The existing `clear()` override empties the index. Each add / remove bumps `_uid_gen`.
- `element_by_uid(uid)`: returns the indexed item only if `item.scene() is self` and `item._uid == uid`; on a miss, rebuild the index once from `self.items()` and retry (covers children joined via `setParentItem`); a confirmed miss is memoized until `_uid_gen` changes, so a dangling host does not rebuild per paint.
- Register collision (incoming uid held by a different live item): re-mint the incoming item, `_uid_repairs += 1`. On load this is Q6 (first in file order keeps it); paste and pipe split never reach it (they set uids explicitly, section 3).
- `gridline_by_uid` becomes `element_by_uid` + `isinstance`. Dependents stay a scan over `_block_instances` (`hosted_blocks_on`, `instances_bound_to`) -- no reverse index (YAGNI).

### 3. Copies, pipe split, paste footer (D4)

- **Copies never adopt a record's uid.** Every `paste_items` branch that builds a Q1 element drops the record's `uid` (and a node record's `sprinkler_uid`) before `from_dict` / codec apply -- so the copy never meets the register-collision repair, which counts only on load (`_uid_repairs` is reset at load start) -- lets the constructor mint, and records `uid_map[source] = new` (existing for walls / gridlines / blocks / 2D; added for rooms, slabs + voids, roofs, wall openings, nodes, sprinklers via `sprinkler_uid`, pipes, water supply, design areas). Covers Paste, Duplicate, Array, Copy-to-level, Duplicate Level. Offset and Mirror-copy build copies only through `_add_from_dict` (registry 2D types + `block_instance`; any other record returns None), so they copy no Q1 element today and keep its existing re-mint -- AC2's Offset / Mirror clause is satisfied by that path.
- **Hosted remap (Q9):** after all branches, for each pasted block's `host["gridline"]` and `host_uid`: source host in `uid_map` -> rebind to the pasted host; else original host live -> keep it; else skip the block.
- **Footer:** `_last_paste_skip_reason` becomes a list of reasons that `paste_items` appends to (pattern, design area, hosted host gone); `commit_paste` / `commit_duplicate`'s `_with_skip_reason` joins them all. This also surfaces the design-area reason that today's overwrite drops (probe P4 item 4).
- **Pipe split (Q4):** `split_pipe` and `_split_vertical_pipe` hand the original's uid to the node1 half through `element_uid.transfer_uid(scene, old, new)`, after the original has left the scene (no index collision). The node2 half keeps its fresh uid. Dependents resolve to the node1 half by uid; no cascade.

### 4. HostedDependents hook and element_host (D5)

- New `firepro3d/hosted_dependents.py` (concept F7's one hook; `Model_Space` keeps thin forwarders):
  - `dependents_of(scene, host)` -- gridline-hosted blocks (`host["gridline"] == host._uid`) + element-bound blocks (`_host_uid == host._uid`).
  - `push(scene, host)` -- set gridline-hosted blocks to their derived pose (today's `_sync_hosted_blocks` body), then `refresh_bound()` the bound ones.
  - `refresh_all_bound(scene)` -- `refresh_bound()` every block with a host uid.
  - `cascade(scene, removed)` -- section 5.
- Gridline is the first client (Q7): `_sync_hosted_blocks(gl)` forwards to `push`; the `GridlineItem._rebuild_geometry` call, grip-0 `_shift_hosted_along` compensation and section write-back stay put (AC6 parity is a rename, not a re-plumb).
- **`element_host` stored by uid:** `BlockInstance._host_uid` is the truth. The getter resolves it through `scene.element_by_uid` while the block is in a `Model_Space`; off-scene it returns a cached ref (existing tests, Block Editor). The setter records both. Saved as a sparse `"host_uid"` in `BlockInstance.to_dict` (both paths; closes element-parameters D3). Lazy resolution -> no load second pass; a pipe split's node1 half is picked up automatically.
- **Dangling:** an unresolved `_host_uid` -> `host_values()` None -> the attribute default placeholder `"?"` (`block_attributes`); the uid is kept and saved back unchanged.
- **Load notice:** the existing single composed load status (`scene_io`) appends "N duplicate element ids repaired" and "N hosted item(s) whose host is missing" when non-zero.
- **Refresh (Q10; closes element-parameters D2):** `push_undo_state` calls `refresh_all_bound(scene)`; a committed move, grip or panel edit of any host ends there. Undo / redo needs no call: `_restore_network` rebuilds every block, so bound text is fresh by construction (Phase 4 amendment 2026-11-13, user ruling: the end-of-restore call had no observable effect and was dropped; a guard asserts the undo / redo text). Gridline hosts also update live during a drag via `push`. Other hosts update at commit, not per drag frame (live per-frame following of placed tags is SB6).

### 5. Delete cascade, design-area membership, section restore (D6)

- `hosted_dependents.cascade(scene, removed)` returns the hosted blocks (gridline-hosted + `host_uid`-bound) of every removed host not already removed, and drops each removed sprinkler from every `DesignArea._sprinklers` (Q14a). Callers:
  - `_bulk_delete` (replacing its gridline-only cascade) -- Delete, Cut, model browser, 3D view;
  - room sprinkler re-populate (`auto_populate_room`);
  - orphan-node removal (`delete_pipe` -> `remove_node`; collinear extend);
  - section-marker delete (`delete_section`).
  Trim / merge are not callers: their only removal is circle -> arc, and 2D geometry is never a host (no `element_params` category).
- Each caller is already inside a snapshot undo step -> one Undo restores host, dependents (re-linked by uid) and membership (Q11).
- **Status (Q13):** cascade only from gridlines -> today's gridline wording; otherwise "Deleted N item(s) and M hosted item(s)" / "Cut N item(s) and M hosted item(s)".
- **Section restore (Q14b):** `restore_from_list` pairs placed markers by uid: present -> apply the record (rename when the name differs); missing -> re-add with its saved uid; absent from the snapshot -> delete. The four cardinals stay keyed by direction. `_same_cut` is retired.
- **AC10 restated (approved 2026-11-13):** probe P1 showed an undone delete of "Section 3" already keeps its number (the name is re-adopted before `_recount`); the original premise was wrong. The uid pairing replaces the geometry guess with identity (Phase 4: `_same_cut` already pairs a single-step rename undo correctly at base, so this is robustness, not a visible fix; see AC10).
- **Plan step 1 probe (hypothesis):** re-populate calls `node.delete_sprinkler()`, which never `removeItem`s the Sprinkler child -> a node keeping its pipes may hold a ghost sprinkler. A guard settles it before cascade relies on it; if real and pre-existing (VC7 at base), file it rather than fix it here.

## Acceptance Criteria

- [ ] AC1 Every Q1 element has a uid after create, file save/load, undo/redo; walls / gridlines / 2D / text / blocks unchanged.
- [ ] AC2 Copy/paste, Duplicate, Array, Offset, Mirror and level copy mint new uids for every Q1 element; constraint and hosted remaps follow (Q9).
- [ ] AC3 Scene uid index resolves every live element and drops removed ones, including after `clear()`, load and undo restore.
- [ ] AC4 Pipe split keeps the uid on the node1 half (Q4); sprinkler delete keeps the node uid (Q2); fitting has none (Q3).
- [ ] AC5 Legacy load mints silently (Q5); duplicate uids repaired with one notice (Q6).
- [ ] AC6 Gridline-hosted blocks follow through the HostedDependents hook with today's behaviour unchanged (parity: translate, rotate, Origin X/Y/Angle, grips incl. grip-0 compensation, perpendicular move, section drag write-back) (Q7).
- [ ] AC7 Every final removal path cascades uid-hosted dependents in one undo step; one Undo restores host + dependents re-linked (Q8, Q11); status text per Q13.
- [ ] AC8 `element_host` round-trips as `host_uid` through `.fpd` save/load and undo/redo; dangling -> "?" + one notice; bound text refreshes on host move, grip, undo, redo (Q10).
- [ ] AC9 Sprinkler delete removes design-area membership in the same undo step (Q14a).
- [ ] AC10 (restated; reworded at Phase 4 2026-11-13, user ruling) Section-marker undo / redo pairs markers by uid, replacing `_same_cut`: undoing a rename or move keeps the same marker object, its tab and sheet bindings, even when another marker has an identical cut; undoing a delete restores the marker with the same uid; the counter's recount behaviour is unchanged (Q14b). Phase 4 found today's `_same_cut` already pairs a single-step rename undo correctly, so this is a robustness refactor, not a visible fix.
- [ ] AC11 The paste footer shows every skip reason (pattern, design area, hosted host gone).

## Verification Checklist

Each guard drives the real tool / command and is shown RED with the change reverted (VC3).

- [ ] **G2 round-trip** -- one of each Q1 element -> `.fpd` save/load and undo/redo -> identical uids (`sprinkler_uid` != node uid); legacy fixture without uids -> all minted, project not modified.
- [ ] **G-index** -- add / remove keep the index; a sprinkler child resolves via its node; `clear()`, load, undo restore leave no stale entries; a miss rebuilds once and is memoized until the next add / remove.
- [ ] **G-dup** -- a file with duplicate uids -> one notice, unique uids, hosts resolve to the first.
- [ ] **G-paste** -- host + dependent together -> pasted dependent on the pasted host (element host; gridline via section); alone -> original host; original gone -> skipped with the footer reason; the design-area reason shows.
- [ ] **G-split** -- a block bound to a pipe, split through the real split tool -> bound to the node1 half; vertical split likewise.
- [ ] **G-follow parity** -- gridline-hosted block poses after each gridline mutator equal a baseline captured at base 9caea64b.
- [ ] **G-bound refresh** -- a block bound to a door: move the wall, grip, undo, redo -> painted text and `boundingRect` update; a dangling host -> "?" + counted in the load notice.
- [ ] **G-cascade** -- per Q8 path (Delete, Cut, re-populate, orphan node, section delete): dependents gone in one undo step, status text, Undo -> both back and `host_values()` resolves.
- [ ] **G-DA** -- delete a design-area sprinkler via Delete and via re-populate -> membership shrinks; Undo restores.
- [ ] **G-section** -- two sections with identical cuts: rename one, undo -> same marker object / uid, tab kept; delete + undo -> same uid.
- [ ] Keep-green: VC5 grep at plan time, seeded with `tests/test_hosted_blocks_*`, `tests/test_sb2a_binding.py`, `tests/test_paper_marker_exclusion.py`, Marks / paste / undo suites.
- [ ] No regressions: full suite (VC6) on the final tree.

## Existing Code Context

Probe notes (local, gitignored): `.todo/sb5-probes/p1-uid-serialization.md`, `p2-add-remove-sites.md`, `p3-hosting.md`, `p4-da-section.md`. Key seams: `Model_Space.clear`, `_bulk_delete`, `gridline_by_uid` / `hosted_blocks_on` / `_sync_hosted_blocks` / `_shift_hosted_along`, `instances_bound_to`, `paste_items` (`uid_map`), `push_undo_state`, `_restore_network`; `BlockInstance.element_host` / `host_values` / `refresh_bound`; `network_codec.serialize_node` (`sprinkler_phase` sibling-key pattern); `SectionManager.restore_from_list` / `_same_cut` / `_recount`; `modify_tools_controller._with_skip_reason`; `sprinkler_workflow_controller.auto_populate_room`.

## Dependencies & follow-ups

- Depends: SB4g -- merged (origin/main 9caea64b); concept gate "phase 4 done" met.
- SB4g delta (P2 re-probe 593d6653..9caea64b): `Sprinkler`, `WaterSupply` and the new `RiserSymbolItem` subclass `symbol_block.SymbolBlockItem`; no uid / serialization-shape change. Riser: no uid (D7).
- Follow-up (file at Phase 4/6): migrate wall->opening, slab->void, node->pipe/fitting onto HostedDependents (Q7).
- Follow-up candidate: the re-populate ghost-sprinkler hypothesis (section 5), filed only if the plan's step-1 probe proves it pre-existing.
