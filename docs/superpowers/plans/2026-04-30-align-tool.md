# Align Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Revit-style Align tool that aligns any movable item to a reference edge, with optional persistent lock constraints via padlock icons.

**Architecture:** New `AlignmentConstraint` class extends the existing constraint system (`constraints.py`). New geometric primitives (`is_parallel`, `perpendicular_translation`) in `geometry_intersect.py`. Tool handler (`_press_align`, `_move_align`) in `scene_tools.py` follows the established mode dispatch pattern. Padlock icon as a small `QGraphicsItem` subclass.

**Tech Stack:** PyQt6, existing constraint solver in `model_space.py`

**Spec:** `docs/superpowers/specs/2026-04-30-align-tool-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `firepro3d/geometry_intersect.py` | Add `is_parallel()`, `perpendicular_translation()` |
| Modify | `firepro3d/constraints.py` | Add `AlignmentConstraint` class + factory branch |
| Modify | `firepro3d/scene_tools.py` | Add `_extract_edges()`, `_press_align()`, `_move_align()`, `_execute_align()`, `_PadlockItem` |
| Modify | `firepro3d/model_space.py` | Wire mode dispatch, state vars, cleanup, status message |
| Modify | `main.py` | Add ribbon button in Transform group |
| Create | `tests/test_align_tool.py` | All tests for alignment primitives, constraint, edge extraction, tool integration |
| Modify | `docs/specs/grid-system.md` | Add alignment constraint participation section |

---

### Task 1: Geometric Primitives for Parallel Detection

**Files:**
- Create: `tests/test_align_tool.py`
- Modify: `firepro3d/geometry_intersect.py:264` (after `point_on_segment_param`)

- [ ] **Step 1: Write failing tests for `is_parallel` and `perpendicular_translation`**

In `tests/test_align_tool.py`:

```python
"""Tests for the Align tool: geometric primitives, AlignmentConstraint, edge
extraction, and tool integration."""

from __future__ import annotations

import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_intersect import is_parallel, perpendicular_translation


# ── is_parallel ──────────────────────────────────────────────────────────

class TestIsParallel:
    """is_parallel(p1, p2, p3, p4, tolerance_deg) → bool"""

    def test_exactly_parallel_horizontal(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(0, 50), QPointF(100, 50),
        ) is True

    def test_exactly_parallel_vertical(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(0, 100),
            QPointF(50, 0), QPointF(50, 100),
        ) is True

    def test_antiparallel(self):
        """180° offset is still parallel."""
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(100, 50), QPointF(0, 50),
        ) is True

    def test_within_tolerance_4deg(self):
        """4° is within default 5° tolerance."""
        rad = math.radians(4)
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(0, 0), QPointF(100 * math.cos(rad), 100 * math.sin(rad)),
        ) is True

    def test_outside_tolerance_6deg(self):
        """6° exceeds default 5° tolerance."""
        rad = math.radians(6)
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(0, 0), QPointF(100 * math.cos(rad), 100 * math.sin(rad)),
        ) is False

    def test_perpendicular(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(0, 0), QPointF(0, 100),
        ) is False

    def test_diagonal_parallel(self):
        assert is_parallel(
            QPointF(0, 0), QPointF(100, 100),
            QPointF(50, 0), QPointF(150, 100),
        ) is True

    def test_degenerate_zero_length_segment(self):
        """Zero-length segment → not parallel."""
        assert is_parallel(
            QPointF(0, 0), QPointF(0, 0),
            QPointF(0, 50), QPointF(100, 50),
        ) is False


# ── perpendicular_translation ────────────────────────────────────────────

class TestPerpendicularTranslation:
    """perpendicular_translation(ref_p1, ref_p2, target_point) → QPointF delta"""

    def test_horizontal_ref_point_above(self):
        """Point above horizontal line → delta moves it down to the line."""
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 0),  # horizontal ref at y=0
            QPointF(50, 30),                  # point at y=30
        )
        assert abs(delta.x()) < 1e-6
        assert abs(delta.y() - (-30.0)) < 1e-6

    def test_vertical_ref_point_right(self):
        """Point right of vertical line → delta moves it left to the line."""
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(0, 100),  # vertical ref at x=0
            QPointF(20, 50),                  # point at x=20
        )
        assert abs(delta.x() - (-20.0)) < 1e-6
        assert abs(delta.y()) < 1e-6

    def test_point_already_on_line(self):
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(50, 0),
        )
        assert abs(delta.x()) < 1e-6
        assert abs(delta.y()) < 1e-6

    def test_diagonal_ref(self):
        """45° line — perpendicular translation should be along (-1,1)/√2."""
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 100),
            QPointF(50, 60),  # 10/√2 above the line
        )
        # After translation, (50+dx, 60+dy) should lie on y=x
        new_x = 50 + delta.x()
        new_y = 60 + delta.y()
        assert abs(new_x - new_y) < 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Custom Code/FirePro3D" && python -m pytest tests/test_align_tool.py::TestIsParallel tests/test_align_tool.py::TestPerpendicularTranslation -v`

Expected: ImportError — `is_parallel` and `perpendicular_translation` not defined.

- [ ] **Step 3: Implement `is_parallel` and `perpendicular_translation`**

Add at end of `firepro3d/geometry_intersect.py` (after `nearest_intersection`):

```python
def is_parallel(p1: QPointF, p2: QPointF,
                p3: QPointF, p4: QPointF,
                tolerance_deg: float = 5.0) -> bool:
    """Return True if segment (p1,p2) is parallel to segment (p3,p4).

    Antiparallel (180°) counts as parallel.  Degenerate (zero-length)
    segments return False.
    """
    dx1 = p2.x() - p1.x()
    dy1 = p2.y() - p1.y()
    dx2 = p4.x() - p3.x()
    dy2 = p4.y() - p3.y()

    len1 = math.hypot(dx1, dy1)
    len2 = math.hypot(dx2, dy2)
    if len1 < EPS or len2 < EPS:
        return False

    # Cross product gives sin(angle)
    cross = abs(dx1 * dy2 - dy1 * dx2) / (len1 * len2)
    # Clamp for numerical safety
    cross = min(cross, 1.0)
    angle_deg = math.degrees(math.asin(cross))
    return angle_deg <= tolerance_deg


def perpendicular_translation(ref_p1: QPointF, ref_p2: QPointF,
                               target_point: QPointF) -> QPointF:
    """Return the translation vector that moves *target_point* onto the
    infinite line through *ref_p1*–*ref_p2*, perpendicular to the line.

    Returns a QPointF delta (dx, dy).  Add it to target_point (or any
    co-moving points) to reach the line.
    """
    dx = ref_p2.x() - ref_p1.x()
    dy = ref_p2.y() - ref_p1.y()
    len_sq = dx * dx + dy * dy
    if len_sq < EPS:
        return QPointF(0.0, 0.0)

    # Signed distance from point to line (positive = left of p1→p2)
    # Using: d = ((p - p1) × dir) / |dir|
    px = target_point.x() - ref_p1.x()
    py = target_point.y() - ref_p1.y()
    cross = px * dy - py * dx  # (p - p1) × dir
    dist = cross / math.sqrt(len_sq)

    # Normal vector (perpendicular, pointing left of p1→p2)
    length = math.sqrt(len_sq)
    nx = -dy / length
    ny = dx / length

    # Translation to reach the line: move by -dist along the normal
    return QPointF(-dist * nx, -dist * ny)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "D:/Custom Code/FirePro3D" && python -m pytest tests/test_align_tool.py::TestIsParallel tests/test_align_tool.py::TestPerpendicularTranslation -v`

Expected: All 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/geometry_intersect.py tests/test_align_tool.py
git commit -m "feat(align): add is_parallel and perpendicular_translation primitives"
```

---

### Task 2: AlignmentConstraint Class

**Files:**
- Modify: `firepro3d/constraints.py:98` (factory branch + new class at end)
- Modify: `tests/test_align_tool.py` (add constraint tests)

- [ ] **Step 1: Write failing tests for AlignmentConstraint**

Append to `tests/test_align_tool.py`:

```python
from firepro3d.constraints import AlignmentConstraint, Constraint


# ── AlignmentConstraint ──────────────────────────────────────────────────

class _FakeLineItem:
    """Minimal stand-in for a scene item with a line edge."""

    def __init__(self, x1, y1, x2, y2):
        self._p1 = QPointF(x1, y1)
        self._p2 = QPointF(x2, y2)

    def pos(self):
        return QPointF(0, 0)

    def setPos(self, p):
        delta = QPointF(p.x() - 0, p.y() - 0)
        self._p1 = QPointF(self._p1.x() + delta.x(), self._p1.y() + delta.y())
        self._p2 = QPointF(self._p2.x() + delta.x(), self._p2.y() + delta.y())

    def moveBy(self, dx, dy):
        self._p1 = QPointF(self._p1.x() + dx, self._p1.y() + dy)
        self._p2 = QPointF(self._p2.x() + dx, self._p2.y() + dy)


class TestAlignmentConstraint:

    def _make_constraint(self, ref_line, target_item, offset=0.0):
        """Helper: create constraint with a fixed reference line."""
        c = AlignmentConstraint(
            reference_item=None,
            reference_line=(ref_line[0], ref_line[1]),
            target_item=target_item,
            target_point=QPointF(target_item._p1.x(), target_item._p1.y()),
            perp_direction=QPointF(0, 1),  # perpendicular = Y axis
            perpendicular_offset=offset,
        )
        return c

    def test_solve_zero_offset_moves_target(self):
        """Target at y=30 should snap to y=0 (reference line y=0, offset 0)."""
        ref_line = (QPointF(0, 0), QPointF(100, 0))
        target = _FakeLineItem(10, 30, 90, 30)  # horizontal at y=30
        c = self._make_constraint(ref_line, target, offset=0.0)
        c.solve()
        assert abs(target._p1.y() - 0.0) < 1.0

    def test_solve_nonzero_offset(self):
        """Target should maintain perpendicular_offset=20 from reference."""
        ref_line = (QPointF(0, 0), QPointF(100, 0))
        target = _FakeLineItem(10, 50, 90, 50)
        c = self._make_constraint(ref_line, target, offset=20.0)
        c.solve()
        assert abs(target._p1.y() - 20.0) < 1.0

    def test_solve_disabled(self):
        """Disabled constraint should not move target."""
        ref_line = (QPointF(0, 0), QPointF(100, 0))
        target = _FakeLineItem(10, 30, 90, 30)
        c = self._make_constraint(ref_line, target, offset=0.0)
        c.enabled = False
        c.solve()
        assert abs(target._p1.y() - 30.0) < 1.0  # unchanged

    def test_involves(self):
        ref_line = (QPointF(0, 0), QPointF(100, 0))
        target = _FakeLineItem(10, 30, 90, 30)
        c = self._make_constraint(ref_line, target)
        assert c.involves(target) is True

    def test_serialization_round_trip(self):
        ref_line = (QPointF(0, 0), QPointF(100, 0))
        target = _FakeLineItem(10, 30, 90, 30)
        c = self._make_constraint(ref_line, target, offset=15.0)
        item_to_id = {target: 42}
        data = c.to_dict(item_to_id)
        assert data["constraint_type"] == "alignment"
        assert data["perpendicular_offset"] == 15.0
        # Round-trip
        id_to_item = {42: target}
        c2 = Constraint.from_dict(data, id_to_item)
        assert c2 is not None
        assert isinstance(c2, AlignmentConstraint)
        assert c2.perpendicular_offset == 15.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Custom Code/FirePro3D" && python -m pytest tests/test_align_tool.py::TestAlignmentConstraint -v`

Expected: ImportError — `AlignmentConstraint` not defined.

- [ ] **Step 3: Implement AlignmentConstraint**

Add at end of `firepro3d/constraints.py` (after `DimensionalConstraint`):

```python
# ─────────────────────────────────────────────────────────────────────────────
# AlignmentConstraint
# ─────────────────────────────────────────────────────────────────────────────

class AlignmentConstraint(Constraint):
    """Perpendicular-offset lock between a reference edge and a target item.

    The reference can be a live scene item (``reference_item``) or a fixed
    line in scene coordinates (``reference_line``).  Underlay geometry uses
    the fixed-line path because underlay children lack stable identity.

    When solved, the target is translated along ``perp_direction`` so that
    ``target_point`` (on the target) sits at ``perpendicular_offset`` from
    the reference edge.
    """

    def __init__(
        self,
        reference_item,
        reference_line: tuple[QPointF, QPointF] | None,
        target_item,
        target_point: QPointF,
        perp_direction: QPointF,
        perpendicular_offset: float = 0.0,
    ) -> None:
        super().__init__()
        self.reference_item = reference_item
        self.reference_line = reference_line  # (p1, p2) or None
        self.target_item = target_item
        self.target_point = QPointF(target_point)
        self.perp_direction = QPointF(perp_direction)  # unit vector
        self.perpendicular_offset = perpendicular_offset

    # -- solve -------------------------------------------------------------

    def solve(self, moved_item=None) -> bool:
        if not self.enabled:
            return True

        # Determine reference line
        if self.reference_item is not None and hasattr(self.reference_item, 'line'):
            line = self.reference_item.line()
            ref_p1 = QPointF(line.p1())
            ref_p2 = QPointF(line.p2())
        elif self.reference_line is not None:
            ref_p1, ref_p2 = self.reference_line
        else:
            self.satisfied = False
            return False

        # Current target point position
        tp = self.target_point

        # Perpendicular distance from target_point to reference line
        dx = ref_p2.x() - ref_p1.x()
        dy = ref_p2.y() - ref_p1.y()
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            self.satisfied = False
            return False

        length = math.sqrt(len_sq)
        # Signed perpendicular distance (cross product / length)
        px = tp.x() - ref_p1.x()
        py = tp.y() - ref_p1.y()
        current_dist = (px * dy - py * dx) / length

        error = current_dist - self.perpendicular_offset
        if abs(error) < 0.5:
            self.satisfied = True
            return True

        # Normal direction (perpendicular to reference, leftward)
        nx = -dy / length
        ny = dx / length

        # Move target by -error along normal
        move_dx = -error * nx
        move_dy = -error * ny
        self.target_item.moveBy(move_dx, move_dy)

        # Update stored target_point
        self.target_point = QPointF(tp.x() + move_dx, tp.y() + move_dy)

        self.satisfied = True
        return True

    # -- involves ----------------------------------------------------------

    def involves(self, item) -> bool:
        return item is self.reference_item or item is self.target_item

    # -- visual_points -----------------------------------------------------

    def visual_points(self) -> list[tuple[str, QPointF]]:
        return [("alignment", QPointF(self.target_point))]

    # -- serialisation -----------------------------------------------------

    def to_dict(self, item_to_id: dict) -> dict:
        d: dict = {
            "constraint_type": "alignment",
            "target_item": item_to_id.get(self.target_item, -1),
            "target_point": [self.target_point.x(), self.target_point.y()],
            "perp_direction": [self.perp_direction.x(), self.perp_direction.y()],
            "perpendicular_offset": self.perpendicular_offset,
            "enabled": self.enabled,
        }
        if self.reference_item is not None and self.reference_item in item_to_id:
            d["reference_item"] = item_to_id[self.reference_item]
            d["reference_line"] = None
        else:
            d["reference_item"] = None
            if self.reference_line is not None:
                p1, p2 = self.reference_line
                d["reference_line"] = [
                    [p1.x(), p1.y()], [p2.x(), p2.y()],
                ]
            else:
                d["reference_line"] = None
        return d

    @classmethod
    def from_dict(cls, data: dict, id_to_item: dict) -> AlignmentConstraint | None:
        target_id = data.get("target_item")
        if target_id is None or target_id == -1:
            return None
        target_item = id_to_item.get(target_id)
        if target_item is None:
            return None

        ref_item = None
        ref_line = None
        ref_id = data.get("reference_item")
        if ref_id is not None:
            ref_item = id_to_item.get(ref_id)
            if ref_item is None:
                return None  # stale reference
        else:
            rl = data.get("reference_line")
            if rl is not None:
                ref_line = (QPointF(rl[0][0], rl[0][1]),
                            QPointF(rl[1][0], rl[1][1]))

        tp = data.get("target_point", [0, 0])
        pd = data.get("perp_direction", [0, 1])

        obj = cls(
            reference_item=ref_item,
            reference_line=ref_line,
            target_item=target_item,
            target_point=QPointF(tp[0], tp[1]),
            perp_direction=QPointF(pd[0], pd[1]),
            perpendicular_offset=data.get("perpendicular_offset", 0.0),
        )
        obj.enabled = data.get("enabled", True)
        return obj
```

- [ ] **Step 4: Add factory branch in `Constraint.from_dict`**

In `firepro3d/constraints.py`, in the `from_dict` method (line 97), add the alignment branch:

```python
        elif ctype == "dimensional":
            return DimensionalConstraint.from_dict(data, id_to_item)
        elif ctype == "alignment":
            return AlignmentConstraint.from_dict(data, id_to_item)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "D:/Custom Code/FirePro3D" && python -m pytest tests/test_align_tool.py::TestAlignmentConstraint -v`

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/constraints.py tests/test_align_tool.py
git commit -m "feat(align): add AlignmentConstraint class with solve/serialization"
```

---

### Task 3: Edge Extraction Helper

**Files:**
- Modify: `firepro3d/scene_tools.py` (add `_extract_edges` method)
- Modify: `tests/test_align_tool.py` (add edge extraction tests)

- [ ] **Step 1: Write failing tests for edge extraction**

Append to `tests/test_align_tool.py`:

```python
from firepro3d.gridline import GridlineItem
from firepro3d.scene_tools import extract_edges


class TestExtractEdges:

    def test_gridline_returns_one_segment(self, qapp):
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 500), "A")
        edges = extract_edges(gl)
        assert len(edges) == 1
        p1, p2 = edges[0]
        assert abs(p1.x()) < 1e-6
        assert abs(p2.x()) < 1e-6

    def test_none_returns_empty(self):
        assert extract_edges(None) == []

    def test_unknown_type_returns_empty(self):
        """Unsupported item type → empty list."""
        assert extract_edges("not_an_item") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Custom Code/FirePro3D" && python -m pytest tests/test_align_tool.py::TestExtractEdges -v`

Expected: ImportError — `extract_edges` not defined.

- [ ] **Step 3: Implement `extract_edges` as a module-level function in `scene_tools.py`**

Add near the top of `firepro3d/scene_tools.py`, after imports but before the `SceneToolsMixin` class:

```python
def extract_edges(item) -> list[tuple[QPointF, QPointF]]:
    """Extract linear edge segments from a scene item for alignment.

    Returns a list of (start, end) point pairs in scene coordinates.
    Returns an empty list for unsupported or None items.
    """
    if item is None:
        return []

    from .gridline import GridlineItem
    from .wall import WallSegment
    from .pipe import Pipe
    from .node import Node
    from .construction_geometry import (
        LineItem, PolylineItem, ConstructionLine,
    )

    if isinstance(item, GridlineItem):
        line = item.line()
        return [(QPointF(line.p1()), QPointF(line.p2()))]

    if isinstance(item, WallSegment):
        edges = []
        # Centerline
        p1 = item.mapToScene(item.line().p1())
        p2 = item.mapToScene(item.line().p2())
        edges.append((p1, p2))
        # Face edges from wall path (left and right offsets)
        path = item.path()
        if not path.isEmpty():
            polys = path.toSubpathPolygons()
            for poly in polys:
                for i in range(len(poly) - 1):
                    sp1 = item.mapToScene(poly[i])
                    sp2 = item.mapToScene(poly[i + 1])
                    edges.append((sp1, sp2))
        return edges

    if isinstance(item, Pipe):
        if item.node1 and item.node2:
            return [(QPointF(item.node1.scenePos()),
                     QPointF(item.node2.scenePos()))]
        return []

    if isinstance(item, (LineItem, ConstructionLine)):
        line = item.line()
        p1 = item.mapToScene(line.p1())
        p2 = item.mapToScene(line.p2())
        return [(p1, p2)]

    if isinstance(item, PolylineItem):
        edges = []
        pts = item._points if hasattr(item, '_points') else []
        for i in range(len(pts) - 1):
            p1 = item.mapToScene(pts[i])
            p2 = item.mapToScene(pts[i + 1])
            edges.append((p1, p2))
        return edges

    # QGraphicsPathItem (DXF/PDF underlay children)
    if hasattr(item, 'path') and callable(item.path):
        from PyQt6.QtGui import QPainterPath
        path = item.path()
        edges = []
        prev = None
        for i in range(path.elementCount()):
            el = path.elementAt(i)
            pt = QPointF(el.x, el.y)
            if el.type == QPainterPath.ElementType.MoveToElement:
                prev = pt
            elif el.type == QPainterPath.ElementType.LineToElement:
                if prev is not None:
                    sp1 = item.mapToScene(prev)
                    sp2 = item.mapToScene(pt)
                    edges.append((sp1, sp2))
                prev = pt
            else:
                prev = pt  # skip curves
        return edges

    return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "D:/Custom Code/FirePro3D" && python -m pytest tests/test_align_tool.py::TestExtractEdges -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/scene_tools.py tests/test_align_tool.py
git commit -m "feat(align): add extract_edges utility for linear segment extraction"
```

---

### Task 4: Wire Align Mode into Model Space

**Files:**
- Modify: `firepro3d/model_space.py:178` (state vars)
- Modify: `firepro3d/model_space.py:770` (set_mode cleanup)
- Modify: `firepro3d/model_space.py:932` (status message)
- Modify: `firepro3d/model_space.py:4609` (press dispatch)
- Modify: `firepro3d/model_space.py:3989` (move dispatch)

- [ ] **Step 1: Add state variables**

In `firepro3d/model_space.py`, after line 178 (`self._constraint_grip_a`), add:

```python
        # Align tool state
        self._align_reference = None        # (line_seg, source_item, edge_index) or None
        self._align_highlight = None        # dashed highlight QGraphicsLineItem
        self._align_ghost = None            # ghost preview QGraphicsLineItem
        self._align_padlocks: list = []     # list of _PadlockItem in scene
```

- [ ] **Step 2: Add mode cleanup in `set_mode()`**

In `firepro3d/model_space.py`, after the constraint cleanup block (line 774), add:

```python
        # Clean up align state
        if mode != "align":
            self._align_reference = None
            if self._align_highlight is not None:
                if self._align_highlight.scene() is self:
                    self.removeItem(self._align_highlight)
                self._align_highlight = None
            if hasattr(self, '_align_ghost') and self._align_ghost is not None:
                if self._align_ghost.scene() is self:
                    self.removeItem(self._align_ghost)
                self._align_ghost = None
```

- [ ] **Step 3: Add status message**

In `firepro3d/model_space.py`, after the `"constraint_dimensional"` entry (line 932), add:

```python
            "align":              "Click reference edge",
```

- [ ] **Step 4: Add press dispatch entry**

In `firepro3d/model_space.py`, in `_PRESS_DISPATCH` (after line 4609), add:

```python
        "align":                    "_press_align",
```

- [ ] **Step 5: Add move dispatch entry**

In `firepro3d/model_space.py`, in `_MOVE_DISPATCH` (after line 3988 — the `"detail"` entry), add:

```python
        "align":                    "_move_align",
```

- [ ] **Step 6: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/model_space.py
git commit -m "feat(align): wire align mode into dispatch tables and state management"
```

---

### Task 5: Align Tool Press Handler (Core Alignment Logic)

**Files:**
- Modify: `firepro3d/scene_tools.py` (add `_press_align`, `_execute_align`)

- [ ] **Step 1: Implement `_press_align` and `_execute_align`**

Add to the `SceneToolsMixin` class in `firepro3d/scene_tools.py`:

```python
    # ── Align tool ────────────────────────────────────────────────────────

    def _press_align(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Handle mouse press in align mode.

        Pick 1: reference edge (stays put).
        Pick 2: target item (moves) — or anchor in multi-select.
        """
        from .geometry_intersect import is_parallel, perpendicular_translation

        if self._align_reference is None:
            # ── Pick reference ──────────────────────────────────────────
            ref_edge, ref_item = self._find_nearest_edge(snapped)
            if ref_edge is None:
                self._show_status("No edge found — click closer to geometry")
                return

            self._align_reference = (ref_edge, ref_item)

            # Draw dashed highlight along reference
            from PyQt6.QtGui import QPen, QColor, Qt
            from PyQt6.QtCore import Qt as QtCore
            p1, p2 = ref_edge
            highlight = self.addLine(
                p1.x(), p1.y(), p2.x(), p2.y(),
                QPen(QColor("#00ff00"), 0, QtCore.PenStyle.DashLine),
            )
            highlight.setZValue(1000)
            self._align_highlight = highlight
            self._show_status("Click item to align (or anchor in selection)")
            return

        # ── Pick target / anchor ────────────────────────────────────────
        ref_edge, ref_item = self._align_reference

        selected = [i for i in self.selectedItems()
                    if i is not ref_item and i is not self._align_highlight]

        if selected and item_under in selected:
            # Multi-select: item_under is the anchor
            self._execute_align(ref_edge, ref_item, item_under, group=selected)
        elif item_under is not None and item_under is not ref_item:
            # Single item
            self._execute_align(ref_edge, ref_item, item_under)
        else:
            self._show_status("Click a movable item to align")
            return

        # Reset for next alignment (keep tool active)
        if self._align_highlight is not None:
            if self._align_highlight.scene() is self:
                self.removeItem(self._align_highlight)
            self._align_highlight = None
        self._align_reference = None
        self._show_status("Click reference edge")

    def _execute_align(self, ref_edge, ref_item, target, group=None):
        """Move target (and optional group) to align with reference edge."""
        from .geometry_intersect import is_parallel, perpendicular_translation
        from .gridline import GridlineItem

        ref_p1, ref_p2 = ref_edge
        items_to_move = group if group else [target]

        # Find the target's nearest parallel edge
        target_edges = extract_edges(target)
        best_edge = None
        best_dist = float('inf')

        if not target_edges:
            # Point-like item — use its position directly
            delta = perpendicular_translation(ref_p1, ref_p2, target.scenePos())
        else:
            for edge in target_edges:
                if not is_parallel(ref_p1, ref_p2, edge[0], edge[1]):
                    continue
                mid = QPointF((edge[0].x() + edge[1].x()) / 2,
                              (edge[0].y() + edge[1].y()) / 2)
                d = perpendicular_translation(ref_p1, ref_p2, mid)
                dist = math.hypot(d.x(), d.y())
                if dist < best_dist:
                    best_dist = dist
                    best_edge = edge
                    delta = d

            if best_edge is None:
                self._show_status("No parallel edge found")
                return

        self.push_undo_state()

        # Apply translation
        for item in items_to_move:
            if isinstance(item, GridlineItem):
                if item._locked:
                    self._show_status(f"Gridline '{item._label_text}' is locked")
                    continue
                item.move_perpendicular(
                    delta.x() * item._perpendicular_vector()[0]
                    + delta.y() * item._perpendicular_vector()[1]
                )
            else:
                item.moveBy(delta.x(), delta.y())

        self._solve_constraints()
        self._show_status("Aligned")

        for v in self.views():
            v.viewport().update()

    def _find_nearest_edge(self, pos: QPointF):
        """Find the nearest linear edge segment to *pos* in the scene.

        Returns ((p1, p2), source_item) or (None, None).
        """
        views = self.views()
        if not views:
            return None, None
        scale = views[0].transform().m11()
        tol = 40.0 / max(scale, 1e-6)

        search_rect = QRectF(
            pos.x() - tol, pos.y() - tol,
            tol * 2, tol * 2,
        )

        best_edge = None
        best_item = None
        best_dist = tol

        for item in self.items(search_rect):
            # Skip our own highlight line
            if item is self._align_highlight:
                continue
            # Skip non-visible items
            if not item.isVisible():
                continue

            edges = extract_edges(item)
            for edge in edges:
                p1, p2 = edge
                # Distance from pos to segment
                dist = self._point_to_segment_dist(pos, p1, p2)
                if dist < best_dist:
                    best_dist = dist
                    best_edge = edge
                    best_item = item

        return best_edge, best_item

    @staticmethod
    def _point_to_segment_dist(p: QPointF, s1: QPointF, s2: QPointF) -> float:
        """Perpendicular distance from point p to segment s1-s2."""
        dx = s2.x() - s1.x()
        dy = s2.y() - s1.y()
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-12:
            return math.hypot(p.x() - s1.x(), p.y() - s1.y())

        t = ((p.x() - s1.x()) * dx + (p.y() - s1.y()) * dy) / len_sq
        t = max(0.0, min(1.0, t))
        proj = QPointF(s1.x() + t * dx, s1.y() + t * dy)
        return math.hypot(p.x() - proj.x(), p.y() - proj.y())
```

- [ ] **Step 2: Add required import at top of `scene_tools.py`**

Add `QRectF` to the QtCore import if not already present:

```python
from PyQt6.QtCore import QPointF, QRectF
```

- [ ] **Step 3: Quick smoke test — activate mode and verify no crash**

Run: `cd "D:/Custom Code/FirePro3D" && python -c "from firepro3d.scene_tools import SceneToolsMixin; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/scene_tools.py
git commit -m "feat(align): implement press handler with reference pick and alignment execution"
```

---

### Task 6: Align Tool Move Handler (Live Preview)

**Files:**
- Modify: `firepro3d/scene_tools.py` (add `_move_align`)

- [ ] **Step 1: Implement `_move_align`**

Add to the `SceneToolsMixin` class in `firepro3d/scene_tools.py`:

```python
    def _move_align(self, event, snapped):
        """Live preview for align mode.

        Before reference pick: highlight nearest edge under cursor.
        After reference pick: show ghost line where target edge would land.
        """
        from .geometry_intersect import is_parallel, perpendicular_translation

        if self._align_reference is None:
            # Preview mode: highlight nearest edge under cursor
            edge, item = self._find_nearest_edge(snapped)
            if edge is not None:
                p1, p2 = edge
                if self._align_highlight is not None:
                    self._align_highlight.setLine(p1.x(), p1.y(), p2.x(), p2.y())
                    self._align_highlight.show()
                else:
                    from PyQt6.QtGui import QPen, QColor
                    from PyQt6.QtCore import Qt as QtCore
                    highlight = self.addLine(
                        p1.x(), p1.y(), p2.x(), p2.y(),
                        QPen(QColor("#00ff00"), 0, QtCore.PenStyle.DashLine),
                    )
                    highlight.setZValue(1000)
                    self._align_highlight = highlight
            else:
                if self._align_highlight is not None:
                    self._align_highlight.hide()
        else:
            # Post-reference: show ghost preview of alignment result
            ref_edge, ref_item = self._align_reference
            # Find item under cursor
            items_at = self.items(snapped)
            target = None
            for it in items_at:
                if it is self._align_highlight:
                    continue
                if it is ref_item:
                    continue
                if not it.isVisible():
                    continue
                target = it
                break

            # Clean up previous ghost
            if hasattr(self, '_align_ghost') and self._align_ghost is not None:
                if self._align_ghost.scene() is self:
                    self.removeItem(self._align_ghost)
                self._align_ghost = None

            if target is not None:
                target_edges = extract_edges(target)
                ref_p1, ref_p2 = ref_edge
                for edge in target_edges:
                    if is_parallel(ref_p1, ref_p2, edge[0], edge[1]):
                        mid = QPointF((edge[0].x() + edge[1].x()) / 2,
                                      (edge[0].y() + edge[1].y()) / 2)
                        delta = perpendicular_translation(ref_p1, ref_p2, mid)
                        # Draw ghost line at destination
                        from PyQt6.QtGui import QPen, QColor
                        from PyQt6.QtCore import Qt as QtCore
                        gp1 = QPointF(edge[0].x() + delta.x(), edge[0].y() + delta.y())
                        gp2 = QPointF(edge[1].x() + delta.x(), edge[1].y() + delta.y())
                        self._align_ghost = self.addLine(
                            gp1.x(), gp1.y(), gp2.x(), gp2.y(),
                            QPen(QColor("#00ff00"), 0, QtCore.PenStyle.DotLine),
                        )
                        self._align_ghost.setZValue(1000)
                        self._align_ghost.setOpacity(0.6)
                        break
```

- [ ] **Step 2: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/scene_tools.py
git commit -m "feat(align): add move handler for live edge preview"
```

---

### Task 7: Padlock Visual and Lock/Unlock

**Files:**
- Modify: `firepro3d/scene_tools.py` (add `_PadlockItem` class, update `_execute_align`)

- [ ] **Step 1: Implement `_PadlockItem`**

Add before the `SceneToolsMixin` class in `firepro3d/scene_tools.py`:

```python
class _PadlockItem(QGraphicsPathItem):
    """Small padlock icon shown after alignment. Click to create/remove constraint."""

    _SIZE = 12  # pixels (screen-fixed)

    def __init__(self, scene_pos: QPointF, constraint_data: dict, parent=None):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(2000)
        self.setPos(scene_pos)
        self._constraint_data = constraint_data  # stored until user clicks to lock
        self._constraint = None  # set after locking
        self._locked = False
        self._build_path()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def _build_path(self):
        """Draw a simple padlock shape."""
        from PyQt6.QtGui import QPainterPath, QPen, QColor, QBrush
        s = self._SIZE
        path = QPainterPath()
        # Body (rectangle)
        path.addRect(-s / 2, 0, s, s * 0.7)
        # Shackle (arc)
        path.moveTo(-s * 0.3, 0)
        path.arcTo(-s * 0.3, -s * 0.5, s * 0.6, s * 0.6, 180, -180)
        self.setPath(path)

        color = QColor("#ffaa00") if not self._locked else QColor("#44cc44")
        self.setPen(QPen(color, 1.5))
        self.setBrush(QBrush(color.lighter(180)))

    def mousePressEvent(self, event):
        """Toggle lock state on click."""
        scene = self.scene()
        if scene is None:
            return

        if not self._locked:
            # Create the constraint
            from .constraints import AlignmentConstraint
            c = AlignmentConstraint(**self._constraint_data)
            scene._constraints.append(c)
            self._constraint = c
            self._locked = True
            self._build_path()
            scene._show_status("Alignment locked")
        else:
            # Remove constraint and padlock
            if self._constraint in scene._constraints:
                scene._constraints.remove(self._constraint)
            scene._align_padlocks.remove(self)
            scene.removeItem(self)
            scene._show_status("Alignment unlocked")

        for v in scene.views():
            v.viewport().update()
        event.accept()
```

- [ ] **Step 2: Update `_execute_align` to show padlock after alignment**

In `_execute_align`, replace the `self._show_status("Aligned")` line at the end with:

```python
        # Show padlock at the alignment point
        if best_edge is not None:
            mid = QPointF((best_edge[0].x() + best_edge[1].x()) / 2,
                          (best_edge[0].y() + best_edge[1].y()) / 2)
        else:
            mid = QPointF(target.scenePos())
        padlock_pos = QPointF(mid.x() + delta.x(), mid.y() + delta.y())

        # Compute perpendicular direction
        dx = ref_p2.x() - ref_p1.x()
        dy = ref_p2.y() - ref_p1.y()
        length = math.hypot(dx, dy)
        if length > 1e-9:
            perp_dir = QPointF(-dy / length, dx / length)
        else:
            perp_dir = QPointF(0, 1)

        constraint_data = dict(
            reference_item=ref_item,
            reference_line=(QPointF(ref_p1), QPointF(ref_p2)) if ref_item is None else None,
            target_item=target,
            target_point=QPointF(padlock_pos),
            perp_direction=perp_dir,
            perpendicular_offset=0.0,
        )
        padlock = _PadlockItem(padlock_pos, constraint_data)
        self.addItem(padlock)
        self._align_padlocks.append(padlock)

        self._show_status("Aligned — click padlock to lock")
```

Also update the `_execute_align` method to set `delta` before the conditional so it's available later. Move the `delta` variable initialization above the edge-finding logic, and ensure `best_edge` is initialized:

At the top of `_execute_align`, initialize:
```python
        delta = QPointF(0, 0)
        best_edge = None
```

- [ ] **Step 3: Add required imports at top of scene_tools.py**

Ensure these imports are present:

```python
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PyQt6.QtCore import Qt
```

- [ ] **Step 4: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/scene_tools.py
git commit -m "feat(align): add padlock icon with click-to-lock/unlock behavior"
```

---

### Task 8: Multi-Select Alignment with Per-Item Constraints

**Files:**
- Modify: `firepro3d/scene_tools.py` (update `_execute_align` for group padlocks)

- [ ] **Step 1: Update `_execute_align` to create per-item padlocks for group alignment**

The current `_execute_align` already handles group movement (applying the same delta to all items). Update the padlock creation section to create one padlock per item in the group:

Replace the single padlock creation block at the end of `_execute_align` with:

```python
        # Show padlocks — one per item
        dx_ref = ref_p2.x() - ref_p1.x()
        dy_ref = ref_p2.y() - ref_p1.y()
        length_ref = math.hypot(dx_ref, dy_ref)
        if length_ref > 1e-9:
            perp_dir = QPointF(-dy_ref / length_ref, dx_ref / length_ref)
        else:
            perp_dir = QPointF(0, 1)

        for item in items_to_move:
            item_pos = item.scenePos() if hasattr(item, 'scenePos') else QPointF(0, 0)
            # Compute this item's perpendicular offset from reference
            from .geometry_intersect import perpendicular_translation
            item_delta = perpendicular_translation(ref_p1, ref_p2, item_pos)
            item_offset = math.hypot(item_delta.x(), item_delta.y())
            # Sign: positive if on the perp_dir side
            dot = item_delta.x() * perp_dir.x() + item_delta.y() * perp_dir.y()
            if dot < 0:
                item_offset = -item_offset

            ref_line_for_constraint = None
            if ref_item is None or not hasattr(ref_item, 'line'):
                ref_line_for_constraint = (QPointF(ref_p1), QPointF(ref_p2))

            constraint_data = dict(
                reference_item=ref_item if ref_line_for_constraint is None else None,
                reference_line=ref_line_for_constraint,
                target_item=item,
                target_point=QPointF(item_pos),
                perp_direction=perp_dir,
                perpendicular_offset=0.0 if item is target else item_offset,
            )
            padlock = _PadlockItem(item_pos, constraint_data)
            self.addItem(padlock)
            self._align_padlocks.append(padlock)

        self._show_status("Aligned — click padlock to lock")
```

- [ ] **Step 2: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/scene_tools.py
git commit -m "feat(align): per-item padlock icons for multi-select alignment"
```

---

### Task 9: Ribbon Button and Keyboard Shortcut

**Files:**
- Modify: `main.py:1393` (add button after Constraints group, or in Transform group)

- [ ] **Step 1: Add Align button to the Transform group in the Modify tab**

In `main.py`, in `_init_modify_tab()`, after the "Merge Points" button (line 1384), add:

```python
        _mode_btn(g_xform, "Align", _I("placeholder_icon.svg"), "align", large=False).setToolTip(
            "Align items to a reference edge [AL]")
```

- [ ] **Step 2: Add keyboard shortcut**

In `main.py`, find where other keyboard shortcuts are defined (search for `QShortcut` or `addAction`). Add:

```python
        # Align shortcut
        from PyQt6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence("A, L"), self, lambda: self.scene.set_mode("align"))
```

If `QShortcut` is already imported, just add the shortcut line. Place it near other mode shortcuts.

- [ ] **Step 3: Verify button appears and mode activates**

Run: `cd "D:/Custom Code/FirePro3D" && python main.py`

Manual check: Modify tab → Transform group → "Align" button visible. Click it → status bar shows "Click reference edge". Press Escape → returns to select mode.

- [ ] **Step 4: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add main.py
git commit -m "feat(align): add ribbon button and AL keyboard shortcut"
```

---

### Task 10: Two-Stage Escape Handling

**Files:**
- Modify: `firepro3d/model_space.py:7267` (keyPressEvent Escape handler)

- [ ] **Step 1: Add align-specific Escape handling**

In `firepro3d/model_space.py`, in `keyPressEvent`, after the pipe Escape block (line 7275) and before the generic `set_mode(None)` (line 7278), add:

```python
            # Align: first Escape clears reference, second exits mode
            if self.mode == "align" and self._align_reference is not None:
                self._align_reference = None
                if self._align_highlight is not None:
                    if self._align_highlight.scene() is self:
                        self.removeItem(self._align_highlight)
                    self._align_highlight = None
                if hasattr(self, '_align_ghost') and self._align_ghost is not None:
                    if self._align_ghost.scene() is self:
                        self.removeItem(self._align_ghost)
                    self._align_ghost = None
                self._show_status("Click reference edge")
                return
```

This goes right after the pipe escape block (line 7275), so the flow is:
1. If align mode and reference is stored → clear reference, stay in align mode
2. If align mode but no reference → fall through to generic `set_mode(None)` which exits

- [ ] **Step 2: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/model_space.py
git commit -m "feat(align): add two-stage Escape handling (clear reference, then exit)"
```

---

### Task 11: Grid System Spec Update

**Files:**
- Modify: `docs/specs/grid-system.md`

- [ ] **Step 1: Add alignment constraint participation section**

In `docs/specs/grid-system.md`, before the Verification Checklist section, add:

```markdown
## Alignment Constraint Participation

Gridlines can be both **reference** and **target** for the Align tool:

- **As reference:** The gridline's single line segment (p1→p2) serves as the reference edge. Other items align to it.
- **As target:** The Align tool calls `set_perpendicular_position()` to move the gridline. This respects the existing `_locked` flag — locked gridlines cannot be aligned (status bar warning: "Gridline 'X' is locked").
- **Edge extraction:** A gridline exposes exactly one linear segment (p1→p2).
- **Lock constraint:** When locked via Align, an `AlignmentConstraint` is stored referencing the gridline. The padlock icon appears at the alignment point. Moving the reference triggers `set_perpendicular_position()` via the constraint solver.

No structural changes to `GridlineItem` are needed. The existing `move_perpendicular()` and `set_perpendicular_position()` APIs are sufficient.
```

- [ ] **Step 2: Add verification checklist items**

Append to the existing verification checklist:

```markdown
- [ ] Align tool can use gridline as reference (other items align to it)
- [ ] Align tool can use gridline as target (gridline moves to match reference)
- [ ] Locked gridlines rejected by Align tool with status bar warning
- [ ] AlignmentConstraint lock works with gridline as target
```

- [ ] **Step 3: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add docs/specs/grid-system.md
git commit -m "docs: add alignment constraint participation to grid system spec"
```

---

### Task 12: Integration Tests

**Files:**
- Modify: `tests/test_align_tool.py`

- [ ] **Step 1: Write integration test**

Append to `tests/test_align_tool.py`:

```python
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsLineItem
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem


class TestAlignToolIntegration:
    """End-to-end tests using real scene items."""

    def test_align_gridline_to_line(self, qapp):
        """Gridline at x=100 aligns to a vertical line at x=50."""
        scene = QGraphicsScene()
        gl = GridlineItem(QPointF(100, 0), QPointF(100, 500), "A")
        scene.addItem(gl)

        # Reference: vertical line at x=50
        ref_line = scene.addLine(50, 0, 50, 500)

        ref_edge = (QPointF(50, 0), QPointF(50, 500))
        edges = extract_edges(gl)
        assert len(edges) == 1

        from firepro3d.geometry_intersect import is_parallel, perpendicular_translation
        assert is_parallel(ref_edge[0], ref_edge[1], edges[0][0], edges[0][1])

        mid = QPointF((edges[0][0].x() + edges[0][1].x()) / 2,
                      (edges[0][0].y() + edges[0][1].y()) / 2)
        delta = perpendicular_translation(ref_edge[0], ref_edge[1], mid)
        gl.move_perpendicular(
            delta.x() * gl._perpendicular_vector()[0]
            + delta.y() * gl._perpendicular_vector()[1]
        )

        # Gridline should now be at x=50
        line = gl.line()
        assert abs(line.p1().x() - 50.0) < 1.0
        assert abs(line.p2().x() - 50.0) < 1.0

    def test_locked_gridline_does_not_move(self, qapp):
        """Locked gridlines should not be affected by alignment."""
        scene = QGraphicsScene()
        gl = GridlineItem(QPointF(100, 0), QPointF(100, 500), "B")
        gl._locked = True
        scene.addItem(gl)

        gl.move_perpendicular(-50)
        line = gl.line()
        assert abs(line.p1().x() - 100.0) < 1.0  # unchanged

    def test_point_item_projects_onto_reference(self, qapp):
        """A point at (30, 70) projected onto y=0 horizontal line → (30, 0)."""
        from firepro3d.geometry_intersect import perpendicular_translation
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(30, 70),
        )
        new_y = 70 + delta.y()
        assert abs(new_y) < 1e-6
        assert abs(delta.x()) < 1e-6  # X unchanged
```

- [ ] **Step 2: Run all tests**

Run: `cd "D:/Custom Code/FirePro3D" && python -m pytest tests/test_align_tool.py -v`

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add tests/test_align_tool.py
git commit -m "test(align): add integration tests for gridline-to-line alignment"
```

---

### Task 13: Clean Up Padlocks on Delete and Undo

**Files:**
- Modify: `firepro3d/model_space.py:616` (constraint cleanup on delete)

- [ ] **Step 1: Clean up padlocks when constraints are removed**

In `firepro3d/model_space.py`, after the constraint cleanup on delete (line 617), add padlock cleanup:

```python
        # Clean up padlocks for removed constraints
        surviving = set(self._constraints)
        stale_padlocks = [p for p in self._align_padlocks
                          if p._constraint is not None
                          and p._constraint not in surviving]
        for p in stale_padlocks:
            self._align_padlocks.remove(p)
            if p.scene() is self:
                self.removeItem(p)
```

- [ ] **Step 2: Clean up padlocks in `_restore_network` (undo)**

Find `_restore_network` in `model_space.py` and add padlock cleanup at the start of the restoration, near where constraints are cleared (line 2889):

```python
        # Clear padlocks
        for p in self._align_padlocks:
            if p.scene() is self:
                self.removeItem(p)
        self._align_padlocks.clear()
```

- [ ] **Step 3: Commit**

```bash
cd "D:/Custom Code/FirePro3D"
git add firepro3d/model_space.py
git commit -m "fix(align): clean up padlock icons on delete and undo"
```

---

## Summary

| Task | Description | Files | Estimated Steps |
|------|-------------|-------|----------------|
| 1 | Geometric primitives (`is_parallel`, `perpendicular_translation`) | geometry_intersect.py, test_align_tool.py | 5 |
| 2 | AlignmentConstraint class | constraints.py, test_align_tool.py | 6 |
| 3 | Edge extraction helper | scene_tools.py, test_align_tool.py | 5 |
| 4 | Wire align mode into model_space | model_space.py | 6 |
| 5 | Align press handler (core logic) | scene_tools.py | 4 |
| 6 | Move handler (live preview + ghost) | scene_tools.py | 2 |
| 7 | Padlock visual + lock/unlock | scene_tools.py | 4 |
| 8 | Multi-select per-item padlocks | scene_tools.py | 2 |
| 9 | Ribbon button + shortcut | main.py | 4 |
| 10 | Two-stage Escape handling | model_space.py | 2 |
| 11 | Grid system spec update | grid-system.md | 3 |
| 12 | Integration tests | test_align_tool.py | 3 |
| 13 | Padlock cleanup on delete/undo | model_space.py | 3 |
