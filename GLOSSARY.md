# FirePro3D

Fire protection sprinkler design and analysis: a CAD model of a building and its sprinkler system, drawn on sheets and solved hydraulically to NFPA 13.

## Language

### Project file

**Project tables**:
The per-project lookup tables that elements resolve names and ids against: line weights and their aliases, fill types, materials, phases, Display Manager rows and paper categories. They are migrated and installed before any element is read, and they are saved with the project. The order and the entry points (from a file, fresh, save) are owned by [`docs/specs/scene-io.md`](docs/specs/scene-io.md) section 3a "Project tables".
_Avoid_: display state, project settings, registries (when meaning the set)

### Building model

**Vertical extent**:
The height interval an element occupies in the building, worked out from its levels and offsets. A wall's runs from its base level plus base offset to its top level plus top offset. When the top level cannot be found, the wall keeps its own height above its base. An opening's runs from its assigned level plus its sill, up by its height; it is measured from that level, not from the wall's base.
_Avoid_: z range, z span (when meaning the concept)

### Editing

**Element removal**:
Taking elements out of the model in one step, together with everything that cannot exist without them (a wall's or floor's openings, a node's pipes and head, nodes left with no pipe and no head, blocks hosted on or bound to a removed element) and every record that lists them. Delete, Cut, merging, re-populating a room and deleting a section are all element removal.
_Avoid_: bulk delete, delete cascade

### Sprinkler system

**Node elevation**:
A node's height in the building. It is always the elevation of the node's ceiling level plus the node's offset from that ceiling. When a level's elevation changes, the nodes on that ceiling move with it. When a level is deleted, its nodes stay where they are and are re-measured from the replacement level.
_Avoid_: z offset, elevation offset
