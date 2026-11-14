# FirePro3D

Fire protection sprinkler design and analysis: a CAD model of a building and its sprinkler system, drawn on sheets and solved hydraulically to NFPA 13.

## Language

### Project file

**Project tables**:
The per-project lookup tables that elements resolve names and ids against: line weights and their aliases, fill types, materials, phases, Display Manager rows and paper categories. They are migrated and installed before any element is read, and they are saved with the project. The order and the entry points (from a file, fresh, save) are owned by [`docs/specs/scene-io.md`](docs/specs/scene-io.md) section 3a "Project tables".
_Avoid_: display state, project settings, registries (when meaning the set)
