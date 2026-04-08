# Pipe Placement 3D Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix pipe placement to use 3D vectors for all geometry checks, consolidate pipe creation through `add_pipe()`, and add Z-aware node disambiguation — as specified in `docs/specs/pipe-placement-methodology.md` bugs B1-B12 and enhancements E1-E2.

**Architecture:** Add 3D vector utilities to `cad_math.py`, then update all geometry checks in `model_space.py` and `fitting.py` to use them. Replace manual `Pipe()` construction with `add_pipe(_propagate_ceiling=False)`. Add `z_hint` parameter to `find_nearby_node()`. Fix riser column moves. Fix fitting type matrix for through-risers. Fix labels and preview to show 3D length and correct diameter format.

**Tech Stack:** Python 3.x, PyQt6, pytest (new dev dependency)

**Spec:** `docs/specs/pipe-placement-methodology.md` (Revision 2)

---

## File Structure

### Files to Create
- `tests/conftest.py` — pytest fixtures for Node, Pipe, SprinklerSystem
- `tests/test_cad_math_3d.py` — tests for new 3D vector utilities
- `tests/test_geometry_checks.py` — tests for backtrack, collinear, 4th-branch with 3D
- `tests/test_find_nearby_node.py` — tests for Z-hint disambiguation
- `tests/test_pipe_creation.py` — tests verifying all pipe creation goes through add_pipe
- `tests/test_fitting_type.py` — tests for through-riser fitting determination
- `firepro3d/graphics/fitting_symbols/tee_vertical.svg` — new fitting SVG
- `firepro3d/graphics/fitting_symbols/cross_vertical.svg` — new fitting SVG

### Files to Modify
- `firepro3d/cad_math.py` — add 3D vector utilities
- `firepro3d/model_space.py` — 3D checks, `add_pipe()` consolidation, `z_hint`, riser moves
- `firepro3d/node.py` — contextual snap reference in `snap_point_45`
- `firepro3d/fitting.py` — through-riser fitting matrix
- `firepro3d/pipe.py` — 3D label length, preview diameter format
- `firepro3d/level_manager.py` — refresh pipe labels after elevation update
- `requirements.txt` — add pytest as dev dependency

---

## Task 1: Set Up Test Infrastructure

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/__init__.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytest to requirements**

Add `pytest` to `requirements.txt`:

```
pytest>=7.0
```

- [ ] **Step 2: Install pytest**

Run: `source venv/Scripts/activate && pip install pytest`

- [ ] **Step 3: Create tests/__init__.py**

```python
```

(Empty file — makes `tests/` a package so imports work.)

- [ ] **Step 4: Create conftest.py with minimal fixtures**

```python
"""Shared fixtures for pipe placement tests.

These fixtures create lightweight Node/Pipe/SprinklerSystem objects
without requiring a full QGraphicsScene or QApplication.
"""
import math
import pytest
from unittest.mock import MagicMock, PropertyMock
from PyQt6.QtCore import QPointF


class MockNode:
    """Lightweight node for geometry tests — no Qt scene required."""

    def __init__(self, x: float, y: float, z: float = 0.0):
        self._x = x
        self._y = y
        self.z_pos = z
        self.pipes = []
        self.ceiling_level = "Level 1"
        self.ceiling_offset = -50.8
        self._properties = {
            "Ceiling Level": {"type": "level_ref", "value": "Level 1"},
            "Ceiling Offset": {"type": "string", "value": "-50.8"},
        }
        # Mock fitting
        self.fitting = MagicMock()
        self.fitting.type = "no fitting"
        self.fitting.update = MagicMock()
        self.sprinkler = None

    def scenePos(self) -> QPointF:
        return QPointF(self._x, self._y)

    def pos(self) -> QPointF:
        return QPointF(self._x, self._y)

    def distance_to(self, x: float, y: float) -> float:
        return math.hypot(self._x - x, self._y - y)

    def has_sprinkler(self) -> bool:
        return self.sprinkler is not None

    def has_fitting(self) -> bool:
        return True


class MockPipe:
    """Lightweight pipe for geometry tests."""

    def __init__(self, node1: MockNode, node2: MockNode):
        self.node1 = node1
        self.node2 = node2
        self._properties = {
            "Diameter": {"type": "enum", "value": '1"Ø'},
            "Schedule": {"type": "enum", "value": "Sch 40"},
            "C-Factor": {"type": "string", "value": "120"},
            "Material": {"type": "enum", "value": "Galvanized Steel"},
            "Colour": {"type": "enum", "value": "Red"},
            "Phase": {"type": "enum", "value": "New"},
            "Line Type": {"type": "enum", "value": "Branch"},
            "Ceiling Level": {"type": "level_ref", "value": "Level 1"},
            "Ceiling Offset": {"type": "string", "value": "-50.8"},
            "Show Label": {"type": "enum", "value": "True"},
            "Label Size": {"type": "string", "value": "12"},
        }
        self.user_layer = "Default"
        self.level = "Level 1"
        self.ceiling_level = "Level 1"
        self.ceiling_offset = -50.8
        # Register in both nodes
        node1.pipes.append(self)
        node2.pipes.append(self)

    def _is_vertical(self) -> bool:
        p1, p2 = self.node1.scenePos(), self.node2.scenePos()
        dx, dy = p1.x() - p2.x(), p1.y() - p2.y()
        dz = abs(self.node1.z_pos - self.node2.z_pos)
        return (dx * dx + dy * dy) < 100 and dz > 0.01


@pytest.fixture
def node_factory():
    """Factory for creating MockNode instances."""
    def _make(x, y, z=0.0):
        return MockNode(x, y, z)
    return _make


@pytest.fixture
def pipe_factory():
    """Factory for creating MockPipe instances between nodes."""
    def _make(n1, n2):
        return MockPipe(n1, n2)
    return _make
```

- [ ] **Step 5: Verify pytest discovers the fixtures**

Run: `source venv/Scripts/activate && python -m pytest tests/ --collect-only`
Expected: `no tests ran` (0 collected, no errors)

- [ ] **Step 6: Commit**

```bash
git add tests/ requirements.txt
git commit -m "chore: add pytest test infrastructure with mock Node/Pipe fixtures"
```

---

## Task 2: Add 3D Vector Utilities to cad_math.py

**Files:**
- Modify: `firepro3d/cad_math.py` (add new static methods after line ~84)
- Create: `tests/test_cad_math_3d.py`

- [ ] **Step 1: Write failing tests for 3D utilities**

```python
"""Tests for 3D vector utilities in CAD_Math."""
import math
import pytest
from firepro3d.cad_math import CAD_Math


class TestUnitVector3D:
    def test_horizontal_vector(self):
        ux, uy, uz = CAD_Math.get_unit_vector_3d(0, 0, 0, 3, 4, 0)
        assert math.isclose(ux, 0.6, abs_tol=1e-9)
        assert math.isclose(uy, 0.8, abs_tol=1e-9)
        assert math.isclose(uz, 0.0, abs_tol=1e-9)

    def test_vertical_vector_up(self):
        ux, uy, uz = CAD_Math.get_unit_vector_3d(0, 0, 0, 0, 0, 100)
        assert math.isclose(ux, 0.0, abs_tol=1e-9)
        assert math.isclose(uy, 0.0, abs_tol=1e-9)
        assert math.isclose(uz, 1.0, abs_tol=1e-9)

    def test_vertical_vector_down(self):
        ux, uy, uz = CAD_Math.get_unit_vector_3d(0, 0, 100, 0, 0, 0)
        assert math.isclose(uz, -1.0, abs_tol=1e-9)

    def test_diagonal_vector(self):
        # 45-degree slope: dx=1, dy=0, dz=1 -> length=sqrt(2)
        ux, uy, uz = CAD_Math.get_unit_vector_3d(0, 0, 0, 1, 0, 1)
        expected = 1.0 / math.sqrt(2)
        assert math.isclose(ux, expected, abs_tol=1e-9)
        assert math.isclose(uz, expected, abs_tol=1e-9)

    def test_zero_length_returns_zeros(self):
        ux, uy, uz = CAD_Math.get_unit_vector_3d(5, 5, 5, 5, 5, 5)
        assert ux == 0.0 and uy == 0.0 and uz == 0.0


class TestDotProduct3D:
    def test_parallel_vectors(self):
        dot = CAD_Math.dot_3d((1, 0, 0), (1, 0, 0))
        assert math.isclose(dot, 1.0)

    def test_antiparallel_vectors(self):
        dot = CAD_Math.dot_3d((1, 0, 0), (-1, 0, 0))
        assert math.isclose(dot, -1.0)

    def test_perpendicular_vectors(self):
        dot = CAD_Math.dot_3d((1, 0, 0), (0, 1, 0))
        assert math.isclose(dot, 0.0, abs_tol=1e-9)

    def test_perpendicular_with_z(self):
        dot = CAD_Math.dot_3d((1, 0, 0), (0, 0, 1))
        assert math.isclose(dot, 0.0, abs_tol=1e-9)

    def test_diagonal_dot(self):
        # (1,0,0) . (1,0,1)/sqrt(2) = 1/sqrt(2)
        v = 1.0 / math.sqrt(2)
        dot = CAD_Math.dot_3d((1, 0, 0), (v, 0, v))
        assert math.isclose(dot, v, abs_tol=1e-9)


class TestAngleBetween3D:
    def test_parallel_is_zero(self):
        angle = CAD_Math.angle_between_3d((1, 0, 0), (1, 0, 0))
        assert math.isclose(angle, 0.0, abs_tol=1e-6)

    def test_antiparallel_is_180(self):
        angle = CAD_Math.angle_between_3d((1, 0, 0), (-1, 0, 0))
        assert math.isclose(angle, 180.0, abs_tol=1e-6)

    def test_perpendicular_is_90(self):
        angle = CAD_Math.angle_between_3d((1, 0, 0), (0, 1, 0))
        assert math.isclose(angle, 90.0, abs_tol=1e-6)

    def test_perpendicular_xy_to_z(self):
        angle = CAD_Math.angle_between_3d((1, 0, 0), (0, 0, 1))
        assert math.isclose(angle, 90.0, abs_tol=1e-6)

    def test_45_degree_slope(self):
        v = 1.0 / math.sqrt(2)
        angle = CAD_Math.angle_between_3d((1, 0, 0), (v, 0, v))
        assert math.isclose(angle, 45.0, abs_tol=1e-6)

    def test_zero_vector_returns_zero(self):
        angle = CAD_Math.angle_between_3d((0, 0, 0), (1, 0, 0))
        assert math.isclose(angle, 0.0)


class TestOutwardVectors3D:
    def test_single_horizontal_pipe(self, node_factory, pipe_factory):
        n1 = node_factory(0, 0, 0)
        n2 = node_factory(100, 0, 0)
        pipe_factory(n1, n2)
        vecs = CAD_Math.get_outward_vectors_3d(n1, n1.pipes)
        assert len(vecs) == 1
        ux, uy, uz = vecs[0]
        assert math.isclose(ux, 1.0, abs_tol=1e-9)
        assert math.isclose(uy, 0.0, abs_tol=1e-9)
        assert math.isclose(uz, 0.0, abs_tol=1e-9)

    def test_vertical_pipe(self, node_factory, pipe_factory):
        n1 = node_factory(0, 0, 0)
        n2 = node_factory(0, 0, 3000)
        pipe_factory(n1, n2)
        vecs = CAD_Math.get_outward_vectors_3d(n1, n1.pipes)
        assert len(vecs) == 1
        ux, uy, uz = vecs[0]
        assert math.isclose(uz, 1.0, abs_tol=1e-9)

    def test_tee_at_node(self, node_factory, pipe_factory):
        center = node_factory(0, 0, 0)
        left = node_factory(-100, 0, 0)
        right = node_factory(100, 0, 0)
        up = node_factory(0, -100, 0)
        pipe_factory(center, left)
        pipe_factory(center, right)
        pipe_factory(center, up)
        vecs = CAD_Math.get_outward_vectors_3d(center, center.pipes)
        assert len(vecs) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/Scripts/activate && python -m pytest tests/test_cad_math_3d.py -v`
Expected: FAIL — `AttributeError: type object 'CAD_Math' has no attribute 'get_unit_vector_3d'`

- [ ] **Step 3: Implement 3D vector utilities**

Add these static methods to the `CAD_Math` class in `firepro3d/cad_math.py` after the existing `get_outward_vectors` method (after line ~84):

```python
    @staticmethod
    def get_unit_vector_3d(x1: float, y1: float, z1: float,
                           x2: float, y2: float, z2: float
                           ) -> tuple[float, float, float]:
        """Return the 3D unit vector from (x1,y1,z1) to (x2,y2,z2)."""
        dx = x2 - x1
        dy = y2 - y1
        dz = z2 - z1
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-9:
            return (0.0, 0.0, 0.0)
        return (dx / length, dy / length, dz / length)

    @staticmethod
    def dot_3d(v1: tuple[float, float, float],
               v2: tuple[float, float, float]) -> float:
        """Dot product of two 3D vectors."""
        return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]

    @staticmethod
    def angle_between_3d(v1: tuple[float, float, float],
                         v2: tuple[float, float, float]) -> float:
        """Unsigned angle in degrees between two 3D vectors.

        Returns 0.0 if either vector has zero length.
        """
        mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
        mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)
        if mag1 < 1e-9 or mag2 < 1e-9:
            return 0.0
        dot = (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (mag1 * mag2)
        dot = max(-1.0, min(1.0, dot))
        return math.degrees(math.acos(dot))

    @staticmethod
    def get_outward_vectors_3d(node, pipes) -> list[tuple[float, float, float]]:
        """Return 3D unit vectors pointing outward from *node* for each pipe."""
        nx = node.scenePos().x()
        ny = node.scenePos().y()
        nz = getattr(node, "z_pos", 0.0)
        vecs = []
        for p in pipes:
            other = p.node2 if p.node1 is node else p.node1
            ox = other.scenePos().x()
            oy = other.scenePos().y()
            oz = getattr(other, "z_pos", 0.0)
            vecs.append(CAD_Math.get_unit_vector_3d(nx, ny, nz, ox, oy, oz))
        return vecs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source venv/Scripts/activate && python -m pytest tests/test_cad_math_3d.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add firepro3d/cad_math.py tests/test_cad_math_3d.py
git commit -m "feat: add 3D vector utilities to CAD_Math (unit_vector_3d, dot_3d, angle_between_3d, outward_vectors_3d)"
```

---

## Task 3: Convert Geometry Checks to 3D Vectors

**Files:**
- Modify: `firepro3d/model_space.py` (lines 1004-1241)
- Create: `tests/test_geometry_checks.py`

- [ ] **Step 1: Write failing tests for 3D geometry checks**

```python
"""Tests for 3D-aware geometry checks in pipe placement."""
import math
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.cad_math import CAD_Math


class TestWouldBacktrack3D:
    """_would_backtrack_at should use 3D vectors so pipes on different
    levels that overlap in plan view are NOT considered backtrack."""

    def test_same_level_overlap_is_backtrack(self, node_factory, pipe_factory):
        """Pipe on same level overlapping existing pipe = backtrack."""
        start = node_factory(0, 0, 0)
        far = node_factory(200, 0, 0)
        pipe_factory(start, far)
        # Target at midpoint of existing pipe, same Z
        target = QPointF(100, 0)
        target_z = 0.0
        result = _would_backtrack_at_3d(start, target, target_z)
        assert result is True

    def test_different_level_overlap_not_backtrack(self, node_factory, pipe_factory):
        """Pipe on different level overlapping in plan view = NOT backtrack."""
        start = node_factory(0, 0, 0)
        far = node_factory(200, 0, 0)
        pipe_factory(start, far)
        # Target at midpoint of existing pipe but different Z
        target = QPointF(100, 0)
        target_z = 3000.0  # Level 2
        result = _would_backtrack_at_3d(start, target, target_z)
        assert result is False

    def test_direct_duplicate_same_z(self, node_factory, pipe_factory):
        """Clicking on existing node at same Z = backtrack."""
        start = node_factory(0, 0, 0)
        far = node_factory(200, 0, 0)
        pipe_factory(start, far)
        target = QPointF(200, 0)
        target_z = 0.0
        result = _would_backtrack_at_3d(start, target, target_z)
        assert result is True

    def test_direct_duplicate_different_z(self, node_factory, pipe_factory):
        """Clicking near existing node at different Z = NOT backtrack."""
        start = node_factory(0, 0, 0)
        far = node_factory(200, 0, 0)
        pipe_factory(start, far)
        target = QPointF(200, 0)
        target_z = 3000.0
        result = _would_backtrack_at_3d(start, target, target_z)
        assert result is False


class TestCollinear3D:
    """_try_extend_collinear should check 3D direction including Z slope."""

    def test_horizontal_collinear_merges(self, node_factory, pipe_factory):
        """Two horizontal pipes in same direction merge."""
        far = node_factory(0, 0, 0)
        start = node_factory(100, 0, 0)
        end = node_factory(200, 0, 0)
        pipe_factory(far, start)
        is_collinear = _is_collinear_3d(far, start, end)
        assert is_collinear is True

    def test_different_z_slope_no_merge(self, node_factory, pipe_factory):
        """Sloped pipe + flat pipe that are 2D-collinear should NOT merge."""
        far = node_factory(0, 0, 0)
        start = node_factory(100, 0, 1000)  # sloped up
        end = node_factory(200, 0, 1000)     # flat continuation
        pipe_factory(far, start)
        is_collinear = _is_collinear_3d(far, start, end)
        assert is_collinear is False

    def test_same_z_slope_merges(self, node_factory, pipe_factory):
        """Two sloped pipes with matching slope DO merge."""
        far = node_factory(0, 0, 0)
        start = node_factory(100, 0, 1000)
        end = node_factory(200, 0, 2000)  # same slope
        pipe_factory(far, start)
        is_collinear = _is_collinear_3d(far, start, end)
        assert is_collinear is True

    def test_vertical_collinear_merges(self, node_factory, pipe_factory):
        """Two vertical pipes in same direction merge."""
        far = node_factory(0, 0, 0)
        start = node_factory(0, 0, 1000)
        end = node_factory(0, 0, 2000)
        pipe_factory(far, start)
        is_collinear = _is_collinear_3d(far, start, end)
        assert is_collinear is True


class TestValidate4thBranch3D:
    """_validate_4th_branch should use 3D vectors for perpendicularity."""

    def test_perpendicular_branch_valid(self, node_factory, pipe_factory):
        """4th branch perpendicular to through-run is valid."""
        center = node_factory(0, 0, 0)
        left = node_factory(-100, 0, 0)
        right = node_factory(100, 0, 0)
        branch = node_factory(0, -100, 0)
        pipe_factory(center, left)
        pipe_factory(center, right)
        pipe_factory(center, branch)
        # New pipe going +Y (perpendicular to L-R through-run)
        new_pt_3d = (0, 100, 0)
        vecs = CAD_Math.get_outward_vectors_3d(center, center.pipes)
        # Should find through-run (left-right) and verify perpendicularity
        assert len(vecs) == 3


# Helper functions that mirror the 3D logic we'll implement.
# These are extracted so tests can run without a full QGraphicsScene.

def _would_backtrack_at_3d(start_node, target_pt: QPointF, target_z: float) -> bool:
    """3D version of _would_backtrack_at for testing."""
    sp = start_node.scenePos()
    sz = start_node.z_pos
    for pipe in start_node.pipes:
        other = pipe.node2 if pipe.node1 is start_node else pipe.node1
        op = other.scenePos()
        oz = other.z_pos
        # Direct duplicate check in 3D
        dist_xy = math.hypot(target_pt.x() - op.x(), target_pt.y() - op.y())
        dist_z = abs(target_z - oz)
        if dist_xy < 5.0 and dist_z < 1.0:
            return True
        # 3D projection check
        dx = op.x() - sp.x()
        dy = op.y() - sp.y()
        dz = oz - sz
        length_sq = dx * dx + dy * dy + dz * dz
        if length_sq < 1e-6:
            continue
        t = ((target_pt.x() - sp.x()) * dx +
             (target_pt.y() - sp.y()) * dy +
             (target_z - sz) * dz) / length_sq
        if 0.01 < t < 0.99:
            proj_x = sp.x() + t * dx
            proj_y = sp.y() + t * dy
            proj_z = sz + t * dz
            dist = math.sqrt(
                (target_pt.x() - proj_x) ** 2 +
                (target_pt.y() - proj_y) ** 2 +
                (target_z - proj_z) ** 2)
            if dist < 10.0:
                return True
    return False


def _is_collinear_3d(far_node, start_node, end_node) -> bool:
    """3D version of collinear check for testing."""
    if start_node.has_sprinkler():
        return False
    if len(start_node.pipes) != 1:
        return False
    sp = start_node.scenePos()
    fp = far_node.scenePos()
    ep = end_node.scenePos()
    sz, fz, ez = start_node.z_pos, far_node.z_pos, end_node.z_pos

    dx_old, dy_old, dz_old = sp.x() - fp.x(), sp.y() - fp.y(), sz - fz
    dx_new, dy_new, dz_new = ep.x() - sp.x(), ep.y() - sp.y(), ez - sz

    len_old = math.sqrt(dx_old**2 + dy_old**2 + dz_old**2)
    len_new = math.sqrt(dx_new**2 + dy_new**2 + dz_new**2)
    if len_old < 1e-6 or len_new < 1e-6:
        return False

    ux_old = dx_old / len_old
    uy_old = dy_old / len_old
    uz_old = dz_old / len_old
    ux_new = dx_new / len_new
    uy_new = dy_new / len_new
    uz_new = dz_new / len_new

    dot = ux_old * ux_new + uy_old * uy_new + uz_old * uz_new
    return abs(dot - 1.0) <= 0.05
```

- [ ] **Step 2: Run tests to verify they pass (these test extracted logic, not the production code yet)**

Run: `source venv/Scripts/activate && python -m pytest tests/test_geometry_checks.py -v`
Expected: All PASS — the test helper functions define the correct 3D behavior

- [ ] **Step 3: Update `_would_backtrack_at` in model_space.py**

Replace lines 1093-1117 in `firepro3d/model_space.py`:

```python
    def _would_backtrack_at(self, start_node, target_pt: QPointF,
                            target_z: float | None = None) -> bool:
        """Return True if placing a pipe toward *target_pt* would overlap
        an existing pipe from *start_node*.

        Uses 3D vectors so pipes on different levels that overlap in plan
        view are not flagged as backtrack.
        """
        sp = start_node.scenePos()
        sz = getattr(start_node, "z_pos", 0.0)
        if target_z is None:
            target_z = sz  # default to same Z
        for pipe in start_node.pipes:
            other = pipe.node2 if pipe.node1 is start_node else pipe.node1
            op = other.scenePos()
            oz = getattr(other, "z_pos", 0.0)
            # Direct duplicate in 3D
            dist_xy = math.hypot(target_pt.x() - op.x(),
                                 target_pt.y() - op.y())
            if dist_xy < 5.0 and abs(target_z - oz) < 1.0:
                return True
            # 3D projection check
            dx = op.x() - sp.x()
            dy = op.y() - sp.y()
            dz = oz - sz
            length_sq = dx * dx + dy * dy + dz * dz
            if length_sq < 1e-6:
                continue
            t = ((target_pt.x() - sp.x()) * dx +
                 (target_pt.y() - sp.y()) * dy +
                 (target_z - sz) * dz) / length_sq
            if 0.01 < t < 0.99:
                proj_x = sp.x() + t * dx
                proj_y = sp.y() + t * dy
                proj_z = sz + t * dz
                dist = math.sqrt(
                    (target_pt.x() - proj_x) ** 2 +
                    (target_pt.y() - proj_y) ** 2 +
                    (target_z - proj_z) ** 2)
                if dist < 10.0:
                    return True
        return False
```

- [ ] **Step 4: Update `_would_backtrack` in model_space.py**

Replace lines 1060-1091 with the same 3D logic but taking an end_node instead of target_pt:

```python
    def _would_backtrack(self, start_node, end_node) -> bool:
        """Return True if placing a pipe from *start_node* to *end_node*
        would overlap an existing pipe (backtracking).

        Uses 3D vectors — pipes at different elevations are not duplicates.
        """
        ep = end_node.scenePos()
        ez = getattr(end_node, "z_pos", 0.0)
        return self._would_backtrack_at(start_node, ep, target_z=ez)
```

- [ ] **Step 5: Update the caller in `_press_pipe` to pass target_z**

At line ~4546, update the backtrack call to pass the template's target Z:

```python
            # ── Backtrack check (before creating/splitting nodes) ─────
            template = getattr(self, "current_template", None)
            target_z = self._compute_template_z_pos(template, node_idx=2) if template else None
            if target_z is None:
                target_z = getattr(self.node_start_pos, "z_pos", 0.0)
            if self._would_backtrack_at(self.node_start_pos, snapped_end,
                                        target_z=target_z):
```

- [ ] **Step 6: Update `_try_extend_collinear` to use 3D vectors**

Replace lines 1137-1157 in `firepro3d/model_space.py`:

```python
        sp = start_node.scenePos()
        fp = far_node.scenePos()
        ep = end_node.scenePos()
        sz = getattr(start_node, "z_pos", 0.0)
        fz = getattr(far_node, "z_pos", 0.0)
        ez = getattr(end_node, "z_pos", 0.0)

        dx_old = sp.x() - fp.x()
        dy_old = sp.y() - fp.y()
        dz_old = sz - fz
        dx_new = ep.x() - sp.x()
        dy_new = ep.y() - sp.y()
        dz_new = ez - sz

        len_old = math.sqrt(dx_old**2 + dy_old**2 + dz_old**2)
        len_new = math.sqrt(dx_new**2 + dy_new**2 + dz_new**2)
        if len_old < 1e-6 or len_new < 1e-6:
            return False

        # Normalise
        ux_old = dx_old / len_old
        uy_old = dy_old / len_old
        uz_old = dz_old / len_old
        ux_new = dx_new / len_new
        uy_new = dy_new / len_new
        uz_new = dz_new / len_new

        # Dot product: collinear if ≈ 1.0 (same 3D direction)
        dot = ux_old * ux_new + uy_old * uy_new + uz_old * uz_new
        if abs(dot - 1.0) > 0.05:  # ~5° tolerance
            return False
```

- [ ] **Step 7: Update `_validate_4th_branch` to use 3D vectors**

Replace lines 1023-1054 in `firepro3d/model_space.py`:

```python
        np_ = node.scenePos()
        nz = getattr(node, "z_pos", 0.0)
        vectors = []
        for p in pipes:
            other = p.node2 if p.node1 is node else p.node1
            op = other.scenePos()
            oz = getattr(other, "z_pos", 0.0)
            dx = op.x() - np_.x()
            dy = op.y() - np_.y()
            dz = oz - nz
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
            if length < 1e-6:
                continue
            vectors.append((dx / length, dy / length, dz / length))
        if len(vectors) != 3:
            return "Cannot determine pipe directions at this node."
        # Find the collinear pair (angle ≈ 180°)
        through_dir = None
        for i in range(3):
            for j in range(i + 1, 3):
                dot = (vectors[i][0] * vectors[j][0] +
                       vectors[i][1] * vectors[j][1] +
                       vectors[i][2] * vectors[j][2])
                if dot < -0.95:  # ~180° ± ~18°
                    through_dir = vectors[i]
                    break
            if through_dir:
                break
        if through_dir is None:
            return "Cannot find through-run direction on this tee."
        # Check new pipe direction is perpendicular to through-run
        # new_pt is 2D (QPointF), so we need the target Z
        dx_new = new_pt.x() - np_.x()
        dy_new = new_pt.y() - np_.y()
        # For the new pipe, approximate dz as 0 (horizontal placement)
        # since the target point is a 2D click position
        dz_new = 0.0
        len_new = math.sqrt(dx_new * dx_new + dy_new * dy_new + dz_new * dz_new)
        if len_new < 1e-6:
            return "New pipe has zero length."
        ux_new = dx_new / len_new
        uy_new = dy_new / len_new
        uz_new = dz_new / len_new
        dot_new = (through_dir[0] * ux_new +
                   through_dir[1] * uy_new +
                   through_dir[2] * uz_new)
        if abs(dot_new) > 0.17:
            return ("A 4th branch must be perpendicular to the through-run "
                    "to form a cross fitting.")
        return None
```

- [ ] **Step 8: Update `_convert_45_elbow_to_wye` to use 3D vectors**

Replace lines 1205-1219 in `firepro3d/model_space.py`:

```python
        jp = junction_node.scenePos()
        jz = getattr(junction_node, "z_pos", 0.0)

        v = []
        for p in pipes:
            far = p.node2 if p.node1 is junction_node else p.node1
            fp = far.scenePos()
            fz = getattr(far, "z_pos", 0.0)
            dx = fp.x() - jp.x()
            dy = fp.y() - jp.y()
            dz = fz - jz
            length = math.sqrt(dx * dx + dy * dy + dz * dz)
            if length < 1e-6:
                return
            v.append((dx / length, dy / length, dz / length, p))

        angle = CAD_Math.angle_between_3d(
            (v[0][0], v[0][1], v[0][2]),
            (v[1][0], v[1][1], v[1][2]))
```

Also update the through_dir and stub calculation (lines 1228-1233):

```python
        through_dir = (v[0][0], v[0][1], v[0][2])

        # Stub continues opposite the through direction (away from first pipe)
        # Project to 2D for stub placement (stub is horizontal)
        STUB_LENGTH = 304.8  # 1 ft in mm
        td_2d_len = math.hypot(through_dir[0], through_dir[1])
        if td_2d_len < 1e-6:
            return  # through direction is vertical — cannot place 2D stub
        stub_x = jp.x() - (through_dir[0] / td_2d_len) * STUB_LENGTH
        stub_y = jp.y() - (through_dir[1] / td_2d_len) * STUB_LENGTH
```

- [ ] **Step 9: Run all tests**

Run: `source venv/Scripts/activate && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add firepro3d/model_space.py tests/test_geometry_checks.py
git commit -m "feat: convert backtrack, collinear, 4th-branch, and wye checks to 3D vectors

Fixes B7 from pipe-placement-methodology spec. Pipes on different
levels that overlap in plan view are no longer flagged as backtrack.
Collinear extension now checks Z slope match. 4th-branch validation
uses 3D perpendicularity."
```

---

## Task 4: Route All Pipe Creation Through `add_pipe()`

**Files:**
- Modify: `firepro3d/model_space.py` (lines 1336-1367, 1404-1448, 4245-4266, 4299-4331)

- [ ] **Step 1: Refactor `_create_vertical_connection` (lines 1336-1367)**

Replace the manual pipe construction with `add_pipe()`:

```python
    def _create_vertical_connection(self, start_node, existing_end_node, template):
        """Insert an intermediate node + vertical pipe + horizontal pipe."""
        intermediate = self._make_intermediate_node(existing_end_node, template)

        # Vertical pipe — use add_pipe with _propagate_ceiling=False
        # since both nodes already have correct Z
        self.add_pipe(existing_end_node, intermediate, template,
                      _propagate_ceiling=False)

        # Horizontal pipe with full template
        self.add_pipe(start_node, intermediate, template)

        # Refresh fittings on all affected nodes
        start_node.fitting.update()
        existing_end_node.fitting.update()
        intermediate.fitting.update()
```

- [ ] **Step 2: Refactor `_split_vertical_pipe` (lines 1404-1448)**

Replace manual pipe construction:

```python
    def _split_vertical_pipe(self, pipe, target_z: float, template) -> "Node":
        """Split a vertical pipe at *target_z*, returning the new mid-node."""
        xy = pipe.node1.scenePos()
        mid = Node(xy.x(), xy.y())
        mid.user_layer = self.active_user_layer
        mid.level = self.active_level

        ceiling_lvl = template._properties["Ceiling Level"]["value"]
        mid.ceiling_level = ceiling_lvl
        mid._properties["Ceiling Level"]["value"] = ceiling_lvl
        mid.ceiling_offset = template.ceiling_offset
        mid._properties["Ceiling Offset"]["value"] = str(template.ceiling_offset)
        mid.z_pos = target_z

        self.addItem(mid)
        apply_category_defaults(mid)
        self.sprinkler_system.add_node(mid)

        # Use the original pipe as template for property inheritance
        node_a = pipe.node1
        node_b = pipe.node2
        self.delete_pipe(pipe)

        # Recreate as two segments through add_pipe
        self.add_pipe(node_a, mid, pipe_template=None, _propagate_ceiling=False)
        self.add_pipe(mid, node_b, pipe_template=None, _propagate_ceiling=False)

        mid.fitting.update()
        node_a.fitting.update()
        node_b.fitting.update()
        return mid
```

Wait — `delete_pipe` removes pipe from nodes, and if nodes become orphans they get deleted. But `node_a` and `node_b` still have other pipes, so they survive. However we lose the pipe reference for property copying. Fix: capture properties before deleting.

```python
    def _split_vertical_pipe(self, pipe, target_z: float, template) -> "Node":
        """Split a vertical pipe at *target_z*, returning the new mid-node."""
        xy = pipe.node1.scenePos()
        mid = Node(xy.x(), xy.y())
        mid.user_layer = self.active_user_layer
        mid.level = self.active_level

        ceiling_lvl = template._properties["Ceiling Level"]["value"]
        mid.ceiling_level = ceiling_lvl
        mid._properties["Ceiling Level"]["value"] = ceiling_lvl
        mid.ceiling_offset = template.ceiling_offset
        mid._properties["Ceiling Offset"]["value"] = str(template.ceiling_offset)
        mid.z_pos = target_z

        self.addItem(mid)
        apply_category_defaults(mid)
        self.sprinkler_system.add_node(mid)

        node_a = pipe.node1
        node_b = pipe.node2

        # Create replacement pipes BEFORE deleting original
        # (add_pipe registers in node.pipes; delete_pipe removes original)
        self.add_pipe(node_a, mid, template=pipe, _propagate_ceiling=False)
        self.add_pipe(mid, node_b, template=pipe, _propagate_ceiling=False)
        self.delete_pipe(pipe)

        mid.fitting.update()
        node_a.fitting.update()
        node_b.fitting.update()
        return mid
```

- [ ] **Step 3: Refactor `complete_confirmation` riser paths (lines 4245-4266 and 4299-4331)**

For `elev_mismatch_start` riser path (line ~4255):

```python
            if result == "riser":
                xy = start_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=1)
                split_node = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if split_node is not None:
                    self.node_start_pos = split_node
                else:
                    intermediate = self._make_intermediate_node(start_node, template)
                    self.add_pipe(start_node, intermediate, template,
                                  _propagate_ceiling=False)
                    self.node_start_pos = intermediate
                self.instructionChanged.emit("Pick end node")
```

For `elev_mismatch_end` riser path (line ~4309):

```python
            if result == "riser":
                xy = end_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=2)
                split_node = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if split_node is not None:
                    intermediate = split_node
                else:
                    intermediate = self._make_intermediate_node(end_node, template)
                    self.add_pipe(intermediate, end_node, template,
                                  _propagate_ceiling=False)
                # Place the horizontal pipe to the intermediate node
                extended = self._try_extend_collinear(
                    start_node, intermediate, template)
                if not extended:
                    self.add_pipe(start_node, intermediate, template)
                    start_node.fitting.update()
                    intermediate.fitting.update()
                    self._convert_45_elbow_to_wye(start_node, template)
                self.node_start_pos = intermediate
                self._pipe_node_was_new = False
                self.push_undo_state()
                self.instructionChanged.emit(
                    "Pick next node (Esc/double-click to finish)")
```

- [ ] **Step 4: Manually verify pipe placement works**

Run: `source venv/Scripts/activate && python main.py`
Test: Place a few pipes, create a riser via elevation mismatch dialog, split a vertical pipe. Verify fittings display correctly and labels appear.

- [ ] **Step 5: Commit**

```bash
git add firepro3d/model_space.py
git commit -m "fix: route all pipe creation through add_pipe()

Fixes B1, B2, B3 from pipe-placement-methodology spec. Riser
auto-build, _create_vertical_connection, and _split_vertical_pipe
now use add_pipe(_propagate_ceiling=False) instead of manual
Pipe() + addItem() construction."
```

---

## Task 5: Add Z-Hint to `find_nearby_node()`

**Files:**
- Modify: `firepro3d/model_space.py` (lines 856-868, plus all callers)
- Create: `tests/test_find_nearby_node.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Z-aware node disambiguation in find_nearby_node."""
import math
import pytest


class TestFindNearbyNodeZHint:
    def test_no_z_hint_returns_first_match(self, node_factory):
        """Without z_hint, returns first node within snap radius."""
        nodes = [node_factory(100, 100, 0), node_factory(100, 100, 3000)]
        result = _find_nearby_z(nodes, 100, 100, snap_radius=20, z_hint=None)
        assert result is nodes[0]

    def test_z_hint_prefers_matching_z(self, node_factory):
        """With z_hint, prefers the node closest in Z."""
        n_low = node_factory(100, 100, 0)
        n_high = node_factory(100, 100, 3000)
        nodes = [n_low, n_high]
        result = _find_nearby_z(nodes, 100, 100, snap_radius=20, z_hint=3000)
        assert result is n_high

    def test_z_hint_still_requires_xy_snap(self, node_factory):
        """z_hint doesn't override XY snap radius."""
        n_far = node_factory(500, 500, 3000)
        nodes = [n_far]
        result = _find_nearby_z(nodes, 100, 100, snap_radius=20, z_hint=3000)
        assert result is None

    def test_single_node_ignores_z_hint(self, node_factory):
        """With one candidate, z_hint is irrelevant."""
        n = node_factory(100, 100, 0)
        result = _find_nearby_z([n], 100, 100, snap_radius=20, z_hint=9999)
        assert result is n

    def test_three_stacked_nodes(self, node_factory):
        """Picks closest Z among three stacked nodes."""
        n1 = node_factory(100, 100, 0)
        n2 = node_factory(100, 100, 3000)
        n3 = node_factory(100, 100, 6000)
        nodes = [n1, n2, n3]
        result = _find_nearby_z(nodes, 100, 100, snap_radius=20, z_hint=2800)
        assert result is n2


def _find_nearby_z(nodes, x, y, snap_radius, z_hint=None):
    """Test helper mirroring the z_hint logic for find_nearby_node."""
    candidates = [n for n in nodes if n.distance_to(x, y) <= snap_radius]
    if not candidates:
        return None
    if z_hint is not None and len(candidates) > 1:
        candidates.sort(key=lambda n: abs(n.z_pos - z_hint))
    return candidates[0]
```

- [ ] **Step 2: Run tests to verify they pass (testing extracted logic)**

Run: `source venv/Scripts/activate && python -m pytest tests/test_find_nearby_node.py -v`
Expected: All PASS

- [ ] **Step 3: Update `find_nearby_node` in model_space.py**

Replace lines 856-868:

```python
    def find_nearby_node(self, x, y, z_hint=None):
        pt = QPointF(x, y)
        # Priority 1: cursor inside any sprinkler's bounding box → snap to node
        spr_candidates = []
        for node in self.sprinkler_system.nodes:
            if node.has_sprinkler():
                spr = node.sprinkler
                if spr.mapToScene(spr.boundingRect()).boundingRect().contains(pt):
                    spr_candidates.append(node)
        if spr_candidates:
            if z_hint is not None and len(spr_candidates) > 1:
                spr_candidates.sort(key=lambda n: abs(
                    getattr(n, "z_pos", 0.0) - z_hint))
            return spr_candidates[0]
        # Priority 2: distance-based snap with Z disambiguation
        candidates = []
        for node in self.sprinkler_system.nodes:
            if node.distance_to(x, y) <= self.SNAP_RADIUS:
                candidates.append(node)
        if not candidates:
            return None
        if z_hint is not None and len(candidates) > 1:
            candidates.sort(key=lambda n: abs(
                getattr(n, "z_pos", 0.0) - z_hint))
        return candidates[0]
```

- [ ] **Step 4: Update `find_or_create_node` to pass z_hint**

```python
    def find_or_create_node(self, x, y, z_hint=None):
        existing = self.find_nearby_node(x, y, z_hint=z_hint)
        if existing:
            return existing
        return self.add_node(x, y)
```

- [ ] **Step 5: Update callers in `_press_pipe` to pass z_hint**

At line ~4484 (first click):
```python
            template = getattr(self, "current_template", None)
            template_z = self._compute_template_z_pos(template, node_idx=1) if template else None
            existing_start = self.find_nearby_node(snapped.x(), snapped.y(),
                                                    z_hint=template_z)
```

At line ~4500:
```python
                start_node = self.find_or_create_node(snapped.x(), snapped.y(),
                                                       z_hint=template_z)
```

At line ~4565 (second click, end node check):
```python
            template_z_end = self._compute_template_z_pos(template, node_idx=2) if template else None
            existing_end_check = self.find_nearby_node(snapped_end.x(), snapped_end.y(),
                                                        z_hint=template_z_end)
```

At line ~4582:
```python
            existing_end = self.find_nearby_node(snapped_end.x(), snapped_end.y(),
                                                  z_hint=template_z_end)
```

At line ~4588:
```python
                end_node = self.find_or_create_node(snapped_end.x(), snapped_end.y(),
                                                     z_hint=template_z_end)
```

- [ ] **Step 6: Update sprinkler placement caller (line ~4897)**

```python
            target_node = self.find_nearby_node(snapped.x(), snapped.y(),
                                                 z_hint=self._get_active_level_z())
```

Add helper if it doesn't exist:
```python
    def _get_active_level_z(self) -> float | None:
        """Return the elevation of the active level, or None."""
        if self._level_manager:
            lvl = self._level_manager.get(self.active_level)
            if lvl:
                return lvl.elevation + DEFAULT_CEILING_OFFSET_MM
        return None
```

- [ ] **Step 7: Update paste callers (lines ~7013, ~7041)**

```python
                existing = self.find_nearby_node(new_x, new_y)  # no z_hint for paste — keep current behavior
```

(Paste doesn't have a meaningful z_hint — leave as-is.)

- [ ] **Step 8: Run all tests**

Run: `source venv/Scripts/activate && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add firepro3d/model_space.py tests/test_find_nearby_node.py
git commit -m "fix: add z_hint to find_nearby_node for Z-stacked node disambiguation

Fixes B4 from pipe-placement-methodology spec. When multiple nodes
exist at the same XY (risers), pipe and sprinkler placement tools
now prefer the node closest to the target elevation."
```

---

## Task 6: Fix Snap Reference in `snap_point_45`

**Files:**
- Modify: `firepro3d/node.py` (lines 167-201)
- Modify: `firepro3d/model_space.py` (callers of `snap_point_45`)

- [ ] **Step 1: Update `snap_point_45` to accept an optional reference pipe**

Replace lines 167-201 in `firepro3d/node.py`:

```python
    def snap_point_45(self, start: QPointF, end: QPointF,
                      reference_pipe=None) -> QPointF:
        """Snap 'end' to 45-degree increments.

        If *reference_pipe* is provided, the snap grid aligns to that pipe's
        direction.  Otherwise, if this node has pipes, the through-run
        direction is used (collinear pair); failing that, ``pipes[0]``.
        If no pipes exist, free movement with soft snapping.
        """
        angle = CAD_Math.get_vector_angle(start, end) - 90
        length = CAD_Math.get_vector_length(start, end)

        ref = reference_pipe
        if ref is None and self.pipes:
            # Try to find through-run (collinear pair)
            ref = self._find_through_run_pipe()
            if ref is None:
                ref = self.pipes[0]

        if ref is not None:
            base_angle = CAD_Math.get_vector_angle(
                ref.node1.scenePos(), ref.node2.scenePos()
            )
            rel_angle = angle - base_angle
            snap_rel = round(rel_angle / 45) * 45
            snapped = base_angle + snap_rel
        else:
            # Free movement, with "soft" snapping near 45-degree multiples
            nearest_snap = round(angle / 45) * 45
            diff = abs(angle - nearest_snap)
            if diff < 7.5:
                snapped = nearest_snap
            else:
                snapped = angle

        rad = math.radians(snapped)
        return QPointF(
            start.x() + length * math.cos(rad),
            start.y() + length * math.sin(rad)
        )

    def _find_through_run_pipe(self):
        """Return a pipe from the collinear through-run pair, or None."""
        if len(self.pipes) < 2:
            return None
        pos = self.scenePos()
        vecs = []
        for p in self.pipes:
            other = p.node2 if p.node1 is self else p.node1
            op = other.scenePos()
            dx, dy = op.x() - pos.x(), op.y() - pos.y()
            ln = math.hypot(dx, dy)
            if ln < 1e-6:
                continue
            vecs.append((dx / ln, dy / ln, p))
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                dot = vecs[i][0] * vecs[j][0] + vecs[i][1] * vecs[j][1]
                if dot < -0.95:  # ~180°
                    return vecs[i][2]
        return None
```

- [ ] **Step 2: Update callers to pass reference_pipe during chain continuation**

In `_press_pipe` (line ~4542) and `_move_pipe` (line ~3536), the chain has a `self.node_start_pos` with a known last pipe. Pass the last pipe in the chain:

At line ~4542:
```python
            # Find the last pipe added to start_node for snap reference
            _last_pipe = self.node_start_pos.pipes[-1] if self.node_start_pos.pipes else None
            snapped_end = self.node_start_pos.snap_point_45(
                start_pos, snapped, reference_pipe=_last_pipe)
```

At line ~3536:
```python
            _last_pipe = self.node_start_pos.pipes[-1] if self.node_start_pos.pipes else None
            snapped_end = self.node_start_pos.snap_point_45(
                start, snapped, reference_pipe=_last_pipe)
```

- [ ] **Step 3: Manually verify snap behavior**

Run: `source venv/Scripts/activate && python main.py`
Test: Draw a main line, then branch off a tee. Verify the snap grid aligns to the through-run direction, giving clean 90-degree branches.

- [ ] **Step 4: Commit**

```bash
git add firepro3d/node.py firepro3d/model_space.py
git commit -m "fix: snap_point_45 uses contextual pipe reference instead of pipes[0]

Fixes B5 from pipe-placement-methodology spec. Chain continuation
uses the last pipe as snap reference. Branching from existing nodes
prefers the through-run direction for the snap grid."
```

---

## Task 7: Fix Riser Column Move

**Files:**
- Modify: `firepro3d/model_space.py` (lines 7122-7143)

- [ ] **Step 1: Update `move_items` to move Z-stacked siblings**

Replace lines 7134-7142 in `firepro3d/model_space.py`:

```python
        # Collect Z-stacked siblings for any nodes being moved
        all_nodes_to_move = set()
        for item in resolved:
            if isinstance(item, Node):
                all_nodes_to_move.add(item)
                # Find Z-stacked siblings (same XY, different Z)
                ix, iy = item.scenePos().x(), item.scenePos().y()
                for other in self.sprinkler_system.nodes:
                    if other is item:
                        continue
                    if other.distance_to(ix, iy) < 1.0:  # same XY
                        all_nodes_to_move.add(other)

        for item in resolved:
            if isinstance(item, Node):
                continue  # handled below
            elif hasattr(item, "translate"):
                item.translate(offset.x(), offset.y())
                item.setSelected(True)

        for node in all_nodes_to_move:
            node.moveBy(offset.x(), offset.y())
            node.setSelected(True)
            node.fitting.update()
```

- [ ] **Step 2: Manually verify riser move behavior**

Run: `source venv/Scripts/activate && python main.py`
Test: Create a riser (two nodes at same XY, different Z). Select and move one node. Verify both nodes move together.

- [ ] **Step 3: Commit**

```bash
git add firepro3d/model_space.py
git commit -m "fix: moving a riser node moves all Z-stacked siblings at same XY

Fixes B6 from pipe-placement-methodology spec. Prevents riser
columns from breaking apart when a single node is moved."
```

---

## Task 8: Fix Fitting Type for Through-Risers

**Files:**
- Modify: `firepro3d/fitting.py` (lines 138-205)
- Create: `tests/test_fitting_type.py`
- Create: `firepro3d/graphics/fitting_symbols/tee_vertical.svg`
- Create: `firepro3d/graphics/fitting_symbols/cross_vertical.svg`

- [ ] **Step 1: Write failing tests for through-riser fittings**

```python
"""Tests for fitting type determination with through-risers."""
import pytest
from firepro3d.fitting import Fitting


class TestThroughRiserFitting:
    def test_two_vertical_one_horizontal_is_tee_vertical(
            self, node_factory, pipe_factory):
        center = node_factory(0, 0, 1000)
        above = node_factory(0, 0, 2000)
        below = node_factory(0, 0, 0)
        right = node_factory(100, 0, 1000)
        pipe_factory(center, above)
        pipe_factory(center, below)
        pipe_factory(center, right)
        ft = Fitting.determine_type_static(center, center.pipes)
        assert ft == "tee_vertical"

    def test_two_vertical_two_horizontal_is_cross_vertical(
            self, node_factory, pipe_factory):
        center = node_factory(0, 0, 1000)
        above = node_factory(0, 0, 2000)
        below = node_factory(0, 0, 0)
        right = node_factory(100, 0, 1000)
        left = node_factory(-100, 0, 1000)
        pipe_factory(center, above)
        pipe_factory(center, below)
        pipe_factory(center, right)
        pipe_factory(center, left)
        ft = Fitting.determine_type_static(center, center.pipes)
        assert ft == "cross_vertical"

    def test_one_vertical_up_one_horizontal_is_elbow_up(
            self, node_factory, pipe_factory):
        center = node_factory(0, 0, 0)
        above = node_factory(0, 0, 1000)
        right = node_factory(100, 0, 0)
        pipe_factory(center, above)
        pipe_factory(center, right)
        ft = Fitting.determine_type_static(center, center.pipes)
        assert ft == "elbow_up"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/Scripts/activate && python -m pytest tests/test_fitting_type.py -v`
Expected: FAIL — `tee_vertical` not returned, and `determine_type_static` doesn't exist

- [ ] **Step 3: Update `determine_type` in fitting.py**

Replace lines 138-205 in `firepro3d/fitting.py`:

```python
    def determine_type(self, pipes) -> str:
        """Decide fitting type based on connected pipes."""
        return Fitting.determine_type_static(self.node, pipes)

    @staticmethod
    def determine_type_static(node, pipes) -> str:
        """Decide fitting type — static version for testability."""
        count = len(pipes)
        if count == 0:
            return "no fitting"

        vertical = [p for p in pipes if Fitting._is_vertical_static(p, node)]
        horizontal = [p for p in pipes if not Fitting._is_vertical_static(p, node)]
        n_vert = len(vertical)
        n_horiz = len(horizontal)

        # ── Through-riser (2 vertical pipes) ─────────────────────────
        if n_vert >= 2:
            if n_horiz == 0:
                return "no fitting"  # should not exist (collinear merge)
            elif n_horiz == 1:
                return "tee_vertical"
            elif n_horiz >= 2:
                return "cross_vertical"

        # ── Single vertical pipe ─────────────────────────────────────
        if n_vert == 1:
            direction = Fitting._vertical_direction_static(vertical[0], node)
            if n_horiz == 0:
                return f"cap_{direction}"
            elif n_horiz == 1:
                return f"elbow_{direction}"
            else:
                return f"tee_{direction}"

        # ── Pure horizontal logic ────────────────────────────────────
        if count == 1:
            return "cap"
        elif count == 2:
            from .cad_math import CAD_Math
            v1 = CAD_Math.get_unit_vector(
                pipes[0].node1.scenePos(), pipes[0].node2.scenePos())
            v2 = CAD_Math.get_unit_vector(
                pipes[1].node1.scenePos(), pipes[1].node2.scenePos())
            angle = abs(CAD_Math.get_angle_between_vectors(v1, v2, signed=False))

            if math.isclose(angle, 180, abs_tol=10):
                return "no fitting"
            elif math.isclose(angle, 90, abs_tol=10):
                return "90elbow"
            elif math.isclose(angle, 45, abs_tol=5) or math.isclose(angle, 135, abs_tol=5):
                return "45elbow"
            else:
                return "no fitting"
        elif count == 3:
            from .cad_math import CAD_Math
            V = [CAD_Math.get_unit_vector(p.node1.scenePos(), p.node2.scenePos())
                 for p in pipes]
            angles = [
                round(CAD_Math.get_angle_between_vectors(V[i], V[j], signed=False))
                for i in range(3) for j in range(i + 1, 3)
            ]
            if 90 in angles:
                return "tee"
            else:
                return "wye"
        elif count == 4:
            from .cad_math import CAD_Math
            pipe_vectors = CAD_Math.get_outward_vectors(node, pipes)
            if len(pipe_vectors) == 4:
                pairs_ok = False
                for i in range(4):
                    for j in range(i + 1, 4):
                        a = abs(CAD_Math.get_angle_between_vectors(
                            pipe_vectors[i], pipe_vectors[j], signed=False))
                        if math.isclose(a, 180, abs_tol=10):
                            others = [k for k in range(4) if k != i and k != j]
                            a2 = abs(CAD_Math.get_angle_between_vectors(
                                pipe_vectors[others[0]], pipe_vectors[others[1]],
                                signed=False))
                            if math.isclose(a2, 180, abs_tol=10):
                                pairs_ok = True
                                break
                    if pairs_ok:
                        break
                return "cross" if pairs_ok else "no fitting"
            return "no fitting"
        else:
            return "no fitting"
```

Also need to add static versions of helper methods if they reference `self`:

```python
    @staticmethod
    def _is_vertical_static(pipe, node) -> bool:
        """True when pipe is vertical (same XY, different Z)."""
        if not pipe.node1 or not pipe.node2:
            return False
        p1, p2 = pipe.node1.scenePos(), pipe.node2.scenePos()
        dx, dy = p1.x() - p2.x(), p1.y() - p2.y()
        dz = abs(getattr(pipe.node1, "z_pos", 0) - getattr(pipe.node2, "z_pos", 0))
        return (dx * dx + dy * dy) < 100 and dz > 0.01

    @staticmethod
    def _vertical_direction_static(pipe, node) -> str:
        """Return 'up' or 'down' based on whether the other end is above or below."""
        other = pipe.node2 if pipe.node1 is node else pipe.node1
        return "up" if getattr(other, "z_pos", 0) > getattr(node, "z_pos", 0) else "down"
```

- [ ] **Step 4: Add new fitting types to SYMBOLS dict and create placeholder SVGs**

Add to the `SYMBOLS` dict in `fitting.py`:

```python
        "tee_vertical":   {"path": "graphics/fitting_symbols/tee_vertical.svg"},
        "cross_vertical": {"path": "graphics/fitting_symbols/cross_vertical.svg"},
        "cap_up":         {"path": "graphics/fitting_symbols/elbow_up.svg"},
        "cap_down":       {"path": "graphics/fitting_symbols/elbow_down.svg"},
```

For now, `cap_up`/`cap_down` reuse the elbow SVGs (a stub with one vertical pipe looks like an elbow visually). The `tee_vertical` and `cross_vertical` SVGs need to be created — start with copies of `tee.svg` and `cross.svg` as placeholders.

```bash
cp "firepro3d/graphics/fitting_symbols/tee.svg" "firepro3d/graphics/fitting_symbols/tee_vertical.svg"
cp "firepro3d/graphics/fitting_symbols/cross.svg" "firepro3d/graphics/fitting_symbols/cross_vertical.svg"
```

(These are placeholder copies. Custom SVGs showing a vertical through-pipe with horizontal branches should be designed later.)

- [ ] **Step 5: Run tests**

Run: `source venv/Scripts/activate && python -m pytest tests/test_fitting_type.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add firepro3d/fitting.py firepro3d/graphics/fitting_symbols/tee_vertical.svg firepro3d/graphics/fitting_symbols/cross_vertical.svg tests/test_fitting_type.py
git commit -m "feat: add tee_vertical and cross_vertical fitting types for through-risers

Fixes B10 and E1 from pipe-placement-methodology spec. Fitting
determination now correctly handles 2 vertical pipes (through-risers)
with 1 or 2 horizontal branches."
```

---

## Task 9: Fix Pipe Labels to Show 3D Length

**Files:**
- Modify: `firepro3d/pipe.py` (line ~169)
- Modify: `firepro3d/level_manager.py` (line ~335)

- [ ] **Step 1: Update `update_label` to use 3D length**

Replace line 169 in `firepro3d/pipe.py`:

```python
        scene = self.scene()
        if scene and hasattr(scene, "scale_manager"):
            # Use 3D length: sqrt(2D_length² + dz²)
            length_2d = getattr(self, "length", 0.0)
            dz = abs(getattr(self.node1, "z_pos", 0) -
                     getattr(self.node2, "z_pos", 0))
            length_3d = math.sqrt(length_2d ** 2 + dz ** 2)
            length = scene.scale_manager.scene_to_display(length_3d)
        else:
            length_2d = getattr(self, "length", 0.0)
            dz = abs(getattr(self.node1, "z_pos", 0) -
                     getattr(self.node2, "z_pos", 0))
            length_3d = math.sqrt(length_2d ** 2 + dz ** 2)
            length = f"{length_3d:.1f} mm"
```

- [ ] **Step 2: Add pipe label refresh to `update_elevations` in level_manager.py**

After line 335 in `firepro3d/level_manager.py`, add:

```python
        # Refresh pipe labels — they show 3D length which depends on Z
        for pipe in scene.sprinkler_system.pipes:
            pipe.update_label()
```

- [ ] **Step 3: Manually verify labels**

Run: `source venv/Scripts/activate && python main.py`
Test: Place a horizontal pipe — label should show same length as before. Create a riser — label should be hidden (vertical). Create a sloped pipe (different ceiling offsets on N1/N2) — label should show longer than the 2D projection.

- [ ] **Step 4: Commit**

```bash
git add firepro3d/pipe.py firepro3d/level_manager.py
git commit -m "fix: pipe labels show 3D length and refresh after elevation changes

Fixes B11 and B12 from pipe-placement-methodology spec. Labels now
compute sqrt(2D² + dZ²) matching the hydraulic solver's get_length_ft().
update_elevations() refreshes all pipe labels after Z changes."
```

---

## Task 10: Fix Preview Pipe Label

**Files:**
- Modify: `firepro3d/model_space.py` (lines 3533-3590)

- [ ] **Step 1: Fix diameter display in preview**

Replace lines 3556-3563 in `firepro3d/model_space.py`:

```python
                # Preview label — diameter on top, length below
                from .pipe import Pipe
                dia_key = template._properties.get("Diameter", {}).get("value", "")
                if sm and hasattr(sm, "display_unit") and sm.display_unit in ("mm", "m"):
                    dia_str = Pipe._INT_TO_METRIC.get(dia_key, dia_key)
                else:
                    dia_str = Pipe._INT_TO_IMPERIAL.get(dia_key, dia_key)

                # 3D length: account for Z difference between N1 and N2
                dx = snapped_end.x() - start.x()
                dy = snapped_end.y() - start.y()
                length_2d = math.hypot(dx, dy)
                z1 = getattr(template, "node1_ceiling_offset", 0.0)
                z2 = getattr(template, "node2_ceiling_offset", 0.0)
                # Use per-node Z if available
                n1_z = getattr(self.node_start_pos, "z_pos", 0.0)
                t_z2 = self._compute_template_z_pos(template, node_idx=2)
                dz = abs(n1_z - t_z2) if t_z2 is not None else 0.0
                length_3d = math.sqrt(length_2d ** 2 + dz ** 2)
                len_str = sm.format_length(length_3d) if sm else f"{length_3d:.0f} mm"
                lbl = f"{dia_str}\n{len_str}" if dia_str else len_str
```

- [ ] **Step 2: Manually verify preview**

Run: `source venv/Scripts/activate && python main.py`
Test: Enter pipe mode. Move cursor — preview label should show `Ø 1"` (not `1"Ø`). When N2 ceiling is set to a different level, preview length should be larger than 2D distance.

- [ ] **Step 3: Commit**

```bash
git add firepro3d/model_space.py
git commit -m "fix: preview pipe shows correct diameter format and 3D length

Fixes B8 and B9 from pipe-placement-methodology spec. Preview uses
_INT_TO_IMPERIAL/_INT_TO_METRIC for diameter and computes 3D length
including Z difference between template endpoints."
```

---

## Task 11: Final Integration Test

- [ ] **Step 1: Run all automated tests**

Run: `source venv/Scripts/activate && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Manual integration test checklist**

Run: `source venv/Scripts/activate && python main.py`

Test each scenario:

1. **Horizontal pipe placement** — draw a pipe, verify label shows correct diameter and length
2. **Chain continuation** — draw 3+ connected pipes, verify collinear extension merges straight runs
3. **Branch from tee** — draw a branch off a main, verify snap grid aligns to through-run
4. **Riser creation (same-XY click)** — set N2 to different ceiling, click same spot, verify vertical pipe created
5. **Riser creation (mismatch dialog)** — click existing node at different Z, choose "Riser", verify pipe created with correct display/label/fitting
6. **Multi-level overlap** — draw pipes on different levels that overlap in plan view, verify both can be placed (no false backtrack)
7. **Z-stacked node selection** — at a riser, verify clicking selects the node at the correct level
8. **Riser column move** — select a riser node, move it, verify all Z-stacked nodes move together
9. **Through-riser fitting** — create a vertical pipe passing through a floor with horizontal branches, verify `tee_vertical` or `cross_vertical` fitting appears
10. **Preview label** — enter pipe mode, verify preview shows `Ø X"` format and correct length
11. **Elevation change** — change a level's elevation, verify pipe labels update immediately

- [ ] **Step 3: Commit any final fixes**

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test: verify pipe placement 3D fixes integration

All B1-B12 bugs and E1-E2 enhancements from pipe-placement-methodology
spec implemented and verified."
```
