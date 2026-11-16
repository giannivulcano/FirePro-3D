---
status: implemented
last-verified: 2026-11-15
verified-commit: 807cd649
applies-to:
  - firepro3d/node.py
  - firepro3d/pipe_network_controller.py
  - firepro3d/model_space.py
  - firepro3d/network_codec.py
  - firepro3d/property_manager.py
  - firepro3d/sprinkler.py
  - firepro3d/sprinkler_workflow_controller.py
  - firepro3d/level_manager.py
source-tasks: ["todo_open.md: Node owns its node elevation (Q1-Q14)"]
---

# Node elevation: one owner for a node's z (design)

Governing home once built: `docs/specs/sprinkler-system-components.md` §7 (Q6). This doc is the
build design; at Account its contract moves into §7 and this file is marked implemented.
**Implemented 2026-11-15 (0.105.1):** the contract now lives in `docs/specs/sprinkler-system-components.md` §7; this doc is the historical build design.
Rulings Q1-Q15 live on the closed line in `todo_closed.md` (grep "Node owns its"); this doc cites them and does not restate them.
**As built:** `docs/specs/sprinkler-system-components.md` §7 governs wherever it differs from this doc. In particular, load and undo do not call `refresh_nodes`: `deserialize_node` hosts with `refresh=False` and each caller's existing fitting loop is the batched refresh (the D3 table rows for undo restore and load, which say one `refresh_nodes` after the loop, are superseded).

## Goal

A node's elevation (ceiling level + offset, z derived) is written only by `Node`. Every placement,
paste, load, panel and level path calls one Node method; `add_pipe` never changes a node it did not
create. The four Q9 bugs (duplicate offset, far-end record, sprinkler panel fitting refresh,
copy-to-level retarget) and the Q11-Q14 gaps are fixed by construction.

## Motivation

Today the elevation is four fields (`ceiling_level`, `ceiling_offset`, `z_pos`, the
`_properties["Ceiling Level"/"Ceiling Offset"]` panel mirror) plus a network refresh, and callers
reassemble them: 38 field writes and 24 node-mirror writes outside `node.py` across 7 files, and 8
copies of `lvl.elevation + ceiling_offset` outside `Node._recompute_z_pos` (probed at `7de45ab4`).
Each copy drifts: `add_pipe` re-hosts existing nodes (the paste/duplicate bug), the sprinkler panel
skips the fitting refresh, `update_elevations` turns an unresolved level into 0 + offset.

## Architecture & Constraints

- Geometry in mm (CLAUDE.md). No file-format change (Q3).
- Z rule (Q2): `z_pos = level(ceiling_level).elevation + ceiling_offset` whenever the level resolves;
  otherwise z keeps its last value and re-derives when the node is hosted with a resolvable level.
- Only `firepro3d/node.py` assigns `ceiling_level`, `ceiling_offset`, `z_pos` on a node.
- Undo pushes stay with callers (Q5).

## Design Decisions

### D1 Node API (ratified Phase 3: shape A, explicit methods)

| Method | Behaviour | Callers |
|---|---|---|
| `host(level, offset, *, refresh=True)` | Re-host 1 (Q7): store level and offset, z follows the level | placement of new ends, paste / duplicate (record values), codec load, panel Ceiling Level / Offset rows (node and sprinkler panels), copy-to-level and cross-level paste retarget (Q13), Move to Level, level rename, legacy `_change_level` |
| `rehost_keep_z(level, *, refresh=True)` | Re-host 2 (Q7): keep z, offset = z - new level elevation | level delete, `_split_vertical_pipe` |
| `set_z(z, *, refresh=True)` | Re-host 2 on the node's own level | panel Z edit (`_edit_position`) |
| `rederive(*, refresh=True)` | recompute z from the stored fields | level elevation change (`update_elevations`) |
| `Node.refresh_nodes(nodes)` (static) | one `_refresh_network` pass over many nodes | load, undo restore, paste, `update_elevations` (callers pass `refresh=False` to the methods above, then call this once) |

- **Unresolved level** (no scene, no level manager, or unknown name): `host` stores level and
  offset and keeps z; `rehost_keep_z` stores the level and keeps z and offset. Never 0 + offset (Q2, Q12).
- **Order:** a creator adds the node to the scene, then calls `host`, so a new node always derives.
- **refresh=True** runs `_refresh_network([self])`: the node's pipes and the fittings at it and its
  neighbours (Q5). A call that changes nothing skips the refresh.
- **Enforcement:** a source-scan test fails if any file outside `node.py` assigns `.ceiling_level`,
  `.ceiling_offset` or `.z_pos` (attribute or `setattr` with the literal name), or touches
  `_properties["Ceiling Level"/"Ceiling Offset"]` on a node. One named exemption: the template
  sprinkler's own rows in `sprinkler.py` / `sprinkler_workflow_controller.py` (it has no node; its
  rows are its storage, Q3 / Q8).

### D2 New ends are hosted at creation (ratified Phase 3)

`add_node(x, y, z_hint=None, host=None)`: a node it creates is hosted with `host`, default
`(active level, DEFAULT_CEILING_OFFSET_MM)`; a node it finds is returned untouched.
`find_or_create_node` passes `host` through. `template_ceiling(template, end) -> (level, offset)`
is the single DEFAULT_LEVEL / -50.8 fallback (replaces 4 copies).

### D3 Writer site map

| Module | Site today | Becomes |
|---|---|---|
| `pipe_network_controller` | `add_node` inline formula | D2 |
| | `add_pipe` `_propagate_ceiling` + both default-reset branches | deleted (Q4); the parameter is removed from every caller (codec, split, intermediate, the two later `add_pipe(..., _propagate_ceiling=False)` calls) |
| | `_make_intermediate_node` / `_make_intermediate_node_for_n2` | one `_make_intermediate_node(existing, template, end)` -> `host(*template_ceiling(template, end))` |
| | `_split_vertical_pipe` | seed z = target z, then `rehost_keep_z(template_ceiling(template, 1)[0])` (Q7-2) |
| | `split_pipe` | `new_node.host(node_a.ceiling_level, node_a.ceiling_offset)` (unchanged outcome) |
| | start-node commit (new node takes template N1) | `start_node.host(*template_ceiling(template, 1))` |
| `model_space` | `paste_items` node records (incl. legacy `z_offset`, `elevation` fallback) | `host(level, offset, refresh=False)`, one `refresh_nodes` at the end; ceiling level mapped by the shared retarget helper (D4) |
| | `copy_items_to_level` | shared retarget helper (D4) |
| | `_move_selection_to_level` | `host(target_level, node.ceiling_offset)` (Q7-1) |
| | undo restore (`deserialize_node` loop) | codec path + one `refresh_nodes` after the loop |
| `scene_io` | load (`deserialize_node` loop) | one `refresh_nodes` after the loop |
| `network_codec` | `deserialize_node` fields, mirror, formula | legacy inches offset converted, saved `elevation` seeds z, then `host(level, offset, refresh=False)`; `sprinkler_props` drops Ceiling Level / Offset; such rows in old records are ignored on load (Q8) |
| `property_manager` | `_change_level` | `node.host(new_level, node.ceiling_offset)` |
| `sprinkler` | `set_property` Ceiling rows writing into the node | `self.node.host(...)` (refresh included, so `Fitting.type` follows, Q5); a node-less template sprinkler keeps its own rows |
| `sprinkler_workflow_controller` | room auto-populate hosting new nodes | `node.host(ceiling_level, ceiling_offset)` |
| | `add_sprinkler(node, template)` copying template Ceiling rows into the node | stops (Q11) |
| `level_manager` | `update_elevations` formula | `rederive(refresh=False)` per node, then `refresh_nodes` (Q12) |
| | delete: `_rebase_offsets` node column + `_remap_level_refs` -> `set_property` | nodes skip `_rebase_offsets`; the delete remap calls `rehost_keep_z(new)`; rename calls `host(new, same offset)`; rooms, templates, slabs keep the generic table |
| `node` | `set_property` Ceiling rows, `_edit_position` Z | `host(...)`, `set_z(v)`; `get_properties` builds both rows from the attributes (Q3) |

### D4 Shared level retarget (Q13, Q9 copy-to-level)

One helper maps a node record's ceiling level for a cross-level paste and for copy-to-level: a
ceiling level that names the record's own (source) level follows to the target level, offset kept;
any other ceiling level is kept (element-parameters ruling 2026-10-24, SB2b T6 "retarget source refs").

### D5 Migration order

1. Characterization tests (Q9 "passes at base" set), green at `7de45ab4`.
2. Node API + parametrized Node test (both re-host behaviours, with / without level manager,
   unknown level); `node.py`'s own Ceiling rows and Z edit use it. The mirror stays (written by
   `host`) until step 7, so unmigrated sites never KeyError.
3. Placement (D2, intermediate fold, splits, start node, delete `_propagate_ceiling`); Q14 guard.
4. Paste / duplicate / copy-to-level / Move to Level / codec / load / undo (D4); Q9 duplicate,
   far-end and copy-to-level guards go green; Q13 guard.
5. Sprinklers (`set_property`, auto-populate, `add_sprinkler` Q11, records Q8); Q9 sprinkler guard
   green; Q11 guard.
6. Levels (`update_elevations`, delete, rename, `_rebase_offsets`); Q12 guard; existing "level
   delete: nothing moves" tests stay green.
7. `_change_level`; delete the Node mirror; source-scan guard; rewrite the 4 test files that poke
   `_properties["Ceiling …"]` to assert through Node.

Steps 2-7 share `node.py` / `pipe_network_controller.py` and run sequentially.

## Acceptance Criteria

- [ ] The four Q9 guards in `tests/test_node_elevation.py` (6 cases, RED at `0ef262a7`) pass.
- [ ] Q9 characterization set passes before and after.
- [ ] Guards for Q11 (head on an existing node keeps z), Q12 (unresolved level keeps z),
      Q13 (cross-level paste retargets the source ceiling level), Q14 (drawing to an existing node at
      the template z on another ceiling level keeps its level) pass, each shown RED with its change reverted.
- [ ] Parametrized Node test covers host / rehost_keep_z / set_z / rederive with and without a level manager.
- [ ] Source-scan guard passes; it fails when a write is re-added outside `node.py`.
- [ ] No `_properties["Ceiling Level"/"Ceiling Offset"]` on Node; panel rows unchanged to the user.
- [ ] Old project files and clipboard records load with the same node z (no format change).
- [ ] Full suite green (VC6).

## Verification Checklist

- [ ] Each guard shown RED with its fix reverted (VC3).
- [ ] Smoke: draw pipes (new-to-new, onto an existing node, each mismatch-dialog choice), split,
      vertical split; duplicate and paste a network with a -300 offset; copy to level; edit a
      sprinkler's Ceiling Offset and see the fitting update; change and delete a level; save / reopen.
- [ ] Account: §7 rewritten (§7.2 method table, §7.4 rows from attributes, §7.6 unresolved level and
      batched refresh), §13.1 / §13.3 (Q8); `pipe-placement-methodology.md` (drop `_propagate_ceiling`,
      link the formula and the template-propagation block to §7), `view-relationships.md` §12.4 and
      `docs/architecture/level-system.md` link to §7.

## Edge Cases & Error Handling

- Legacy inches `ceiling_offset` and paste's `z_offset` are converted before `host`; the `elevation`
  key seeds z for an unresolved level.
- Drawing onto an existing node: the Elevation Mismatch dialog still resolves first; `add_pipe` no
  longer writes, so geometry is unchanged (Q14).
- A no-change `host` / `set_z` skips the refresh and changes nothing.

## Out of scope

The pipe template's `node1_/node2_ceiling_*` stay template data; paste's overall structure
(architecture review candidate 2); the Display Manager Fitting row parts of the fitting-stale line.
