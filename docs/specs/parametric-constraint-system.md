# Parametric Constraint System Specification

**Status:** Draft (foundation)
**Date:** 2026-05-01
**Scope:** Documents existing implementation + defines extension points
**Depends on:** [Snapping Engine](snapping-engine.md), [Align Tool](../superpowers/specs/2026-04-30-align-tool-design.md)

---

## Table of Contents

1. [Goal](#1-goal)
2. [Current State](#2-current-state)
3. [Architecture](#3-architecture)
4. [Constraint Base Class](#4-constraint-base-class)
5. [Existing Constraint Types](#5-existing-constraint-types)
6. [Solver](#6-solver)
7. [Serialization](#7-serialization)
8. [Visual Indicators](#8-visual-indicators)
9. [Lifecycle & Cleanup](#9-lifecycle--cleanup)
10. [Future Constraint Types](#10-future-constraint-types)
11. [Open Design Questions](#11-open-design-questions)

---

## 1. Goal

Define the parametric constraint system for FirePro3D: a framework for persistent geometric relationships between scene items that are automatically maintained when items move. The system supports an iterative solver with convergence detection, JSON serialization via item ID mapping, and visual indicators for constraint state.

This spec documents the existing implementation (3 constraint types, iterative solver, serialization) and defines the extension points for future constraint types.

## 2. Current State

The constraint system is implemented in `firepro3d/constraints.py` (~550 LOC) with solver integration in `firepro3d/scene_tools.py` (`_solve_constraints`) and state management in `firepro3d/model_space.py`.

### 2.1 Implemented Constraint Types

| Type | Purpose | Stored State | Solve Strategy |
|---|---|---|---|
| `ConcentricConstraint` | Two circles/arcs share the same center | `circle_a`, `circle_b` | Move non-mover's `_center` to match mover's |
| `DimensionalConstraint` | Fixed distance between two grip points | `item_a`, `grip_a`, `item_b`, `grip_b`, `distance` | Adjust mobile grip along direction vector via `apply_grip()` |
| `AlignmentConstraint` | Perpendicular offset from a reference line | `reference_item` or `reference_line`, `target_item`, `target_point`, `perp_direction`, `perpendicular_offset` | Project onto perp direction, translate target by error |

### 2.2 Integration Points

- **Solver call sites:** grip drag, body move, paste, constraint creation
- **Cleanup:** `set_mode()` clears per-mode constraint state; delete handler removes constraints involving deleted items
- **Undo:** constraints serialized into undo snapshots via `_capture_constraints()`; restored via `Constraint.from_dict()` factory
- **UI:** Concentric and Dimensional modes in Modify tab → Constraints group; Align tool in Modify tab → Transform group

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Model_Space                                                        │
│  ├─ _constraints: list[Constraint]       (all active constraints)   │
│  ├─ _solve_constraints(moved_item=None)  (iterative solver)         │
│  ├─ _capture_constraints() → list[dict]  (serialize for undo/save)  │
│  └─ Constraint cleanup on delete, undo, mode switch                 │
├──────────────────────────────────────────────────────────────────────┤
│  constraints.py                                                      │
│  ├─ Constraint (base class)                                          │
│  │   ├─ solve(moved_item) → bool                                     │
│  │   ├─ involves(item) → bool                                        │
│  │   ├─ visual_points() → list[(type, QPointF)]                      │
│  │   ├─ to_dict(item_to_id) → dict                                   │
│  │   └─ from_dict(data, id_to_item) → Constraint | None  (factory)   │
│  ├─ ConcentricConstraint                                              │
│  ├─ DimensionalConstraint                                             │
│  └─ AlignmentConstraint                                               │
├──────────────────────────────────────────────────────────────────────┤
│  scene_tools.py                                                       │
│  ├─ _solve_constraints(moved_item)   (iterative solver with stall)   │
│  ├─ _press_constraint()              (concentric/dimensional modes)   │
│  ├─ _press_align()                   (align tool handler)             │
│  └─ _PadlockItem                     (visual lock/unlock indicator)   │
└──────────────────────────────────────────────────────────────────────┘
```

## 4. Constraint Base Class

```python
class Constraint:
    id: int                    # Auto-incremented unique ID
    enabled: bool = True       # Disabled constraints are skipped by solver
    satisfied: bool = True     # Set by solve(); used by stall detection

    def solve(self, moved_item=None) -> bool: ...
    def involves(self, item) -> bool: ...
    def visual_points(self) -> list[tuple[str, QPointF]]: ...
    def to_dict(self, item_to_id: dict) -> dict: ...

    @staticmethod
    def from_dict(data: dict, id_to_item: dict) -> Constraint | None: ...
```

### 4.1 Contract

- `solve()` must adjust geometry so the constraint is satisfied, then set `self.satisfied` and return it.
- `solve()` receives `moved_item` as a hint: if the constraint involves two items, the non-mover adjusts. If `moved_item` is None, a default side adjusts.
- `involves(item)` must return True for every item the constraint references. Used by delete cleanup.
- `to_dict()` must produce a JSON-serializable dict with a `"constraint_type"` key. The factory dispatches on this key.
- `from_dict()` must return None (not raise) when referenced items are missing.

## 5. Existing Constraint Types

### 5.1 ConcentricConstraint

**Purpose:** Two circles/arcs share the same center.

**Solve:** Copy `_center` from the moved item to the other, then call `_rebuild_item()`. Satisfaction check: distance between centers < 1e-6.

**Applicable to:** `CircleItem`, `ArcItem` (anything with `_center` attribute).

### 5.2 DimensionalConstraint

**Purpose:** Fixed distance between two grip points on two different items.

**Solve:** Read grip positions via `grip_points()[index]`, compute direction vector from anchor to mobile, place mobile at exactly `distance` along that direction via `apply_grip()`. Satisfaction check: actual distance within 0.5mm.

**Applicable to:** Any item implementing `grip_points()` and `apply_grip()`.

### 5.3 AlignmentConstraint

**Purpose:** Maintain a perpendicular offset between a target item and a reference line.

**Solve:** Project `target_point` onto `perp_direction` (measured from reference line origin), compute error vs `perpendicular_offset`, translate target via `moveBy()`. Updates `target_point` after move.

**Reference modes:**
- **Fixed line:** `reference_line = (QPointF, QPointF)`, `reference_item = None`. Used for underlay geometry which lacks stable identity across save/load.
- **Live item:** `reference_item` with `_p1`/`_p2` attributes (future: `line()` method). Reference line recomputed on each solve.

**Applicable to:** Any movable scene item. GridlineItem targets use `move_perpendicular()` with lock check.

## 6. Solver

### 6.1 Algorithm

Located in `SceneToolsMixin._solve_constraints()`:

```python
MAX_ITERATIONS = 20
for each iteration:
    for each enabled constraint:
        if not constraint.solve(moved_item):
            mark unsatisfied
    if all satisfied: break
    if unsatisfied count >= previous count for 3 iterations:
        report conflict via status bar
        break
```

### 6.2 Convergence

- **Happy path:** Most constraint sets converge in 1-2 iterations.
- **Stall detection:** If the number of unsatisfied constraints doesn't decrease for 3 consecutive iterations, the solver assumes a conflict (e.g., circular dependencies) and stops.
- **Conflict reporting:** Status bar message "Constraint conflict detected" with unsatisfied constraint count.

### 6.3 Resolution Order

Constraints are solved in list order (insertion order). No priority system exists. For the current constraint types, order doesn't matter because each constraint adjusts only its own items. If future constraints create order-dependent interactions, a topological sort or priority mechanism may be needed.

### 6.4 Call Sites

| Trigger | `moved_item` | Purpose |
|---|---|---|
| Grip drag (mouseMoveEvent) | The dragged item | Maintain constraints during interactive editing |
| Body drag (mouseMoveEvent) | None | Maintain constraints during item movement |
| Paste/move (mouseReleaseEvent) | None | Enforce constraints after placement |
| Constraint creation | The first item picked | Initial solve to verify feasibility |

## 7. Serialization

### 7.1 Item ID Mapping

Constraints reference live scene items, which don't have stable IDs. Serialization uses a `item_to_id` / `id_to_item` mapping constructed from the geometry list index at save time.

```python
# Save
item_to_id = {item: idx for idx, item in enumerate(geometry_items)}
data = [c.to_dict(item_to_id) for c in constraints]

# Load
id_to_item = {idx: item for idx, item in enumerate(geometry_items)}
constraints = [Constraint.from_dict(d, id_to_item) for d in data]
```

### 7.2 Constraint Type Dispatch

`Constraint.from_dict()` dispatches on `data["constraint_type"]`:

| Value | Class |
|---|---|
| `"concentric"` | `ConcentricConstraint` |
| `"dimensional"` | `DimensionalConstraint` |
| `"alignment"` | `AlignmentConstraint` |

New constraint types must add a branch here.

### 7.3 AlignmentConstraint Special Cases

- **Fixed-line reference:** Serialized as `"reference_line": [x1, y1, x2, y2]`. No item ID needed.
- **Missing target:** `from_dict()` returns None (constraint silently dropped on load).

## 8. Visual Indicators

### 8.1 Constraint Visual Points

Each constraint type returns visual indicator data via `visual_points()`:

| Type | Visual | Color |
|---|---|---|
| `"concentric"` | Marker at shared center | (not rendered currently) |
| `"dimensional"` | Marker at midpoint between grips | (not rendered currently) |
| `"alignment"` | Marker at target point | (not rendered currently) |

**Note:** Visual point rendering is not currently implemented in the paint path. The data is available for future use.

### 8.2 Padlock Icons (Align Tool)

The Align tool uses `_PadlockItem` (scene_tools.py) for visual lock/unlock:

- Orange padlock: alignment performed but not locked
- Green padlock: constraint active
- Click orange → creates AlignmentConstraint, turns green
- Click green → removes constraint, removes padlock

## 9. Lifecycle & Cleanup

### 9.1 Creation

- **Concentric/Dimensional:** Created via constraint tool modes (2-click workflow)
- **Alignment:** Created when user clicks the padlock icon after an align operation

### 9.2 Deletion

Constraints are removed when:
1. **Item deleted:** `_constraints` filtered by `involves()` during `delete_selected_items()`
2. **Padlock clicked (unlock):** Direct removal from `_constraints` list
3. **Undo:** `_restore_network()` clears all constraints, rebuilds from snapshot

### 9.3 Padlock Cleanup

`_PadlockItem` instances are tracked in `_align_padlocks` and cleaned up:
- On item delete: stale padlocks (whose constraint was removed) are detected and removed
- On undo: all padlocks cleared before constraint restore
- On mode switch away from align: highlight/ghost cleaned up (padlocks persist)

## 10. Future Constraint Types

The following constraint types are candidates for future implementation. Each would be a new subclass of `Constraint` with its own `solve()`, serialization, and visual indicator.

### 10.1 Horizontal/Vertical Constraint

Lock an item's angle to exactly 0° or 90°. Simplest possible constraint — `solve()` just snaps the angle.

### 10.2 Equal Spacing Constraint

Maintain equal distances between 3+ items along a direction. Related to the inference engine's equal spacing detection (see `inferred-dimension-driven-placement.md` §7).

### 10.3 Tangent Constraint

Circle/arc tangent to a line. `solve()` moves the circle center to maintain tangency.

### 10.4 Parallel Constraint

Lock two line items to maintain the same angle. Unlike `AlignmentConstraint` (which locks perpendicular distance), this locks orientation without constraining position.

### 10.5 Perpendicular Constraint

Lock two line items to maintain a 90° angle between them.

### 10.6 Fix/Pin Constraint

Lock an item's position absolutely. `solve()` moves it back if disturbed. Useful for anchor points.

## 11. Open Design Questions

These questions should be resolved as the constraint system grows:

1. **Resolution order:** Should constraints have priorities? The current list-order approach works for independent constraints but may produce different results for interacting constraints depending on insertion order.

2. **Over-constrained detection:** The stall detector catches circular conflicts, but there's no upfront check for over-constrained systems (e.g., two conflicting dimensional constraints on the same item). Should constraints check for conflicts at creation time?

3. **Constraint visualization:** `visual_points()` data exists but isn't rendered. Should all constraints show visual indicators, or only selected/hovered ones?

4. **Constraint editing:** No UI exists for editing constraint parameters after creation (e.g., changing a dimensional constraint's distance). Should constraints support inline editing like gridline spacing dimensions?

5. **Dependency graph:** As constraint count grows, should the solver build a dependency graph to determine optimal resolution order? The current linear scan works for small counts but may not scale.

6. **Constraint groups:** Should constraints support grouping (e.g., "all alignment constraints from one align operation")? Currently each constraint is independent.

7. **Undo granularity:** Creating a constraint via padlock click doesn't push an undo state. Should locking/unlocking be undoable independently from the alignment move?
