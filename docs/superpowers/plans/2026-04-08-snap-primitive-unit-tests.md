# Snap Primitive Unit Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin down the current behavior of the three pure geometric primitives in `SnapEngine` (`_line_line_intersect`, `_line_circle_intersect`, `_project_to_segment`) with a Layer-1 unit test suite, per `docs/specs/snapping-engine.md` §10.1.

**Architecture:** Single flat test file `tests/test_snap_engine_primitives.py` following the existing `tests/test_snap_*.py` convention. Tests import the three `@staticmethod` primitives directly from `firepro3d.snap_engine.SnapEngine` and call them with `QPointF` inputs. No `QApplication` / `qapp` fixture required — `QPointF` is a pure data type from `PyQt6.QtCore`. Assertions use `pytest.approx` with `abs=1e-9` as the default numeric tolerance, and anchor to the engine's own epsilons (`1e-10` for line_line denom, `1e-12` for degenerate segment/radius) when the case sits near a threshold.

**Tech Stack:** Python 3.x, PyQt6 (`QPointF` only), pytest, pytest-qt (installed but unused here).

---

## Constraints

- **Test-only PR.** `firepro3d/snap_engine.py` is NOT modified. If the file ends up in `git diff`, the task has gone off-rails.
- **Every assertion is specific.** No `assert result is not None` without a follow-up assertion on the value. No `assert len(pts) > 0` without asserting which points.
- **Numeric tolerance:**
  - Default: `pytest.approx(expected, abs=1e-9)` for geometric results.
  - Near-threshold cases (e.g. denom just above/below `1e-10`): use the engine's own epsilon as the discrimination boundary.
- **Bug policy during implementation:** If a test reveals an actual bug (behavior the spec says is wrong, not just surprising), mark the test `@pytest.mark.xfail(reason="see todo.md: <new entry>")` and add a new `[ ]` entry to `todo.md`. Escalate severe bugs (crashes, wrong type returned) to the user live before proceeding.

## Current-behavior pins (tested explicitly)

Reading `firepro3d/snap_engine.py:620-803` reveals behavior that isn't obvious from the spec prose. These are **current contract**, pinned by tests:

1. `_line_line_intersect` returns `None` when `abs(denom) < 1e-10`. This catches BOTH parallel AND collinear-overlapping — there is no special case for collinear overlap.
2. `_line_line_intersect` touching-at-endpoint: when two segments share exactly one endpoint and are not collinear, `denom` is nonzero and `t`/`s` land on the boundary (`0.0` or `1.0`) — the shared point is returned.
3. `_line_circle_intersect` tangent case: the loop runs for both `sign` values with `disc_sqrt == 0`, so the returned list contains **two identical points**, not one. (Spec §10.1 says "tangent (one intersection)" — we pin current behavior, not the spec wording.)
4. `_project_to_segment` clamps `t` to `[0, 1]`, so:
   - "foot before `seg_a`" → returns `seg_a` exactly.
   - "foot after `seg_b`" → returns `seg_b` exactly.
   The function is effectively "closest point on finite segment," not "foot of unclamped perpendicular."
5. `_line_circle_intersect` with `radius == 0`: `c = fx*fx + fy*fy`, `disc = b*b - 4*a*c`. When the center lies exactly on the segment, `disc` can be ≥ 0 and return degenerate points; when it's off the segment, `disc < 0` returns `[]`. Test both.

## File Structure

- **Create:** `tests/test_snap_engine_primitives.py` — the entire deliverable.
- **Modify (Phase 6 only):** `todo.md` line 34 → mark `[x]`, add `done:2026-04-08`.
- **Do not touch:** `firepro3d/snap_engine.py`.

---

## Task 1: Scaffold the test file

**Files:**
- Create: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Create the test file with module docstring, imports, and a single smoke test**

```python
"""Layer-1 unit tests for SnapEngine geometric primitives.

Covers the three pure static methods in ``firepro3d/snap_engine.py``:

- ``_line_line_intersect`` (line 625)
- ``_line_circle_intersect`` (line 643)
- ``_project_to_segment`` (line 789)

Per ``docs/specs/snapping-engine.md`` §10.1 (roadmap item in ``todo.md``).

These tests pin the **current** contract of the primitives, including
behavior that is surprising but intentional (e.g. tangent returning two
identical points, projection clamping to the segment). Do not "fix" a
test to match intuition — if you believe a primitive is wrong, file a
follow-up in ``todo.md`` and mark the affected test ``xfail``.

No ``QApplication`` is required: ``QPointF`` is a pure data type.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.snap_engine import SnapEngine


# Engine epsilons — mirrors the literals used inside snap_engine.py.
# If snap_engine.py ever extracts these to named constants, update here.
LINE_LINE_DENOM_EPS = 1e-10
DEGENERATE_EPS = 1e-12


def _approx_point(expected: QPointF, abs_tol: float = 1e-9):
    """Return a matcher for a QPointF comparison via ``pytest.approx``.

    Compares x and y independently so failure messages stay readable.
    """
    return (pytest.approx(expected.x(), abs=abs_tol),
            pytest.approx(expected.y(), abs=abs_tol))


def _xy(pt: QPointF) -> tuple[float, float]:
    return (pt.x(), pt.y())


def test_smoke_primitives_are_importable():
    """Sanity check: all three primitives exist and are callable."""
    assert callable(SnapEngine._line_line_intersect)
    assert callable(SnapEngine._line_circle_intersect)
    assert callable(SnapEngine._project_to_segment)
```

- [ ] **Step 2: Run the smoke test**

Run: `pytest tests/test_snap_engine_primitives.py -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): scaffold primitive unit test file"
```

---

## Task 2: `_line_line_intersect` — crossing inside both segments

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the test**

```python
# ────────────────────────────────────────────────────────────────────
# _line_line_intersect
# ────────────────────────────────────────────────────────────────────


class TestLineLineIntersect:
    """Tests for ``SnapEngine._line_line_intersect``.

    Contract (pinned from snap_engine.py:625-638):
    - Parallel OR collinear (``abs(denom) < 1e-10``) → ``None``.
    - Otherwise compute t, s; return intersection only if
      ``0.0 <= t <= 1.0 and 0.0 <= s <= 1.0``, else ``None``.
    """

    def test_crossing_inside_both_segments(self):
        """Generic X-shape: two diagonals meeting at the midpoint."""
        result = SnapEngine._line_line_intersect(
            QPointF(0, 0), QPointF(10, 10),
            QPointF(0, 10), QPointF(10, 0),
        )
        assert result is not None
        assert _xy(result) == _approx_point(QPointF(5, 5))
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineLineIntersect -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-line crossing inside both segments"
```

---

## Task 3: `_line_line_intersect` — crossing outside segment range

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the test (inside `TestLineLineIntersect`)**

```python
    def test_crossing_outside_one_segment_returns_none(self):
        """Lines *would* cross if extended, but the crossing point falls
        outside segment B's [0, 1] parameter range → None."""
        # Segment A: y=5 horizontal, x in [0, 10]
        # Segment B: short diagonal near (20, 0) — the infinite lines
        # meet somewhere around x=15 but t falls outside A's range.
        result = SnapEngine._line_line_intersect(
            QPointF(0, 5), QPointF(10, 5),
            QPointF(20, 0), QPointF(22, 10),
        )
        assert result is None

    def test_crossing_outside_both_segments_returns_none(self):
        """Both infinite lines intersect far from either segment."""
        result = SnapEngine._line_line_intersect(
            QPointF(0, 0), QPointF(1, 1),
            QPointF(10, 0), QPointF(11, 1),
        )
        assert result is None
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineLineIntersect -v`
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-line crossing outside segment range"
```

---

## Task 4: `_line_line_intersect` — parallel & collinear

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the tests**

```python
    def test_parallel_non_collinear_returns_none(self):
        """Two horizontal lines at different y's → denom == 0 → None."""
        result = SnapEngine._line_line_intersect(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 5), QPointF(10, 5),
        )
        assert result is None

    def test_collinear_overlapping_returns_none(self):
        """CURRENT CONTRACT: collinear segments produce denom == 0 and
        the function returns None — it does NOT attempt to report an
        overlap region. Pinned; if spec demands overlap reporting later,
        this test becomes xfail + bug entry."""
        result = SnapEngine._line_line_intersect(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(5, 0), QPointF(15, 0),
        )
        assert result is None

    def test_collinear_non_overlapping_returns_none(self):
        """Collinear, disjoint segments → still None (same denom==0 branch)."""
        result = SnapEngine._line_line_intersect(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(20, 0), QPointF(30, 0),
        )
        assert result is None
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineLineIntersect -v`
Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-line parallel and collinear cases"
```

---

## Task 5: `_line_line_intersect` — touching at endpoint

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the test**

```python
    def test_touching_at_endpoint_returns_shared_point(self):
        """When two non-collinear segments share exactly one endpoint,
        denom is nonzero and t/s land on the [0, 1] boundary. The
        shared point is returned."""
        # L-joint: A ends at (10, 0), B starts at (10, 0) going up.
        result = SnapEngine._line_line_intersect(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(10, 0), QPointF(10, 10),
        )
        assert result is not None
        assert _xy(result) == _approx_point(QPointF(10, 0))
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineLineIntersect::test_touching_at_endpoint_returns_shared_point -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-line endpoint-touching returns shared point"
```

---

## Task 6: `_line_line_intersect` — near-zero denominator boundary

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the tests**

```python
    def test_near_zero_denominator_below_epsilon_returns_none(self):
        """denom slightly below 1e-10 → treated as parallel → None.

        Construct two segments whose direction vectors differ by a
        cross-product smaller than the engine's epsilon.
        """
        # Segment A: (0,0) -> (1,0). dx1=1, dy1=0.
        # Segment B: (0,1) -> (1, 1 + tiny). dx2=1, dy2=tiny.
        # denom = dx1*dy2 - dy1*dx2 = tiny.
        tiny = LINE_LINE_DENOM_EPS / 10.0  # 1e-11, strictly below eps
        result = SnapEngine._line_line_intersect(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(0, 1), QPointF(1, 1 + tiny),
        )
        assert result is None

    def test_near_zero_denominator_above_epsilon_may_intersect(self):
        """denom strictly above 1e-10 → engine proceeds with the
        intersection math. The segments here are effectively parallel
        but denom > eps, so the computed t/s are valid (though possibly
        outside [0,1]). This pins the boundary behavior: whatever the
        engine returns, it must not be None solely because of the
        epsilon check."""
        big = LINE_LINE_DENOM_EPS * 100.0  # 1e-8, well above eps
        # Choose B so the computed intersection falls inside both segments.
        # A: (0,0) -> (1,0). B: (0.5, -1) -> (0.5 + big, 1).
        # These cross near x=0.5.
        result = SnapEngine._line_line_intersect(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(0.5, -1), QPointF(0.5 + big, 1),
        )
        assert result is not None
        # x should be very close to 0.5; y should be 0.
        assert result.y() == pytest.approx(0.0, abs=1e-9)
        assert result.x() == pytest.approx(0.5, abs=1e-6)
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineLineIntersect -v`
Expected: 8 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-line near-zero denominator boundary"
```

---

## Task 7: `_line_circle_intersect` — two intersections inside segment

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the class and first test**

```python
# ────────────────────────────────────────────────────────────────────
# _line_circle_intersect
# ────────────────────────────────────────────────────────────────────


class TestLineCircleIntersect:
    """Tests for ``SnapEngine._line_circle_intersect``.

    Contract (pinned from snap_engine.py:643-664):
    - Degenerate segment (``a = dx² + dy² < 1e-12``) → ``[]``.
    - Discriminant < 0 → ``[]``.
    - Otherwise loop over sign in (-1, +1); append point iff
      ``0.0 <= t <= 1.0``. Tangent case (disc == 0) returns TWO
      IDENTICAL points.
    """

    def test_two_intersections_both_inside_segment(self):
        """A horizontal segment crossing through a circle centered on
        the segment produces two points symmetric about the center."""
        # Segment: y=0, x in [-10, 10]. Circle: center (0,0), r=5.
        pts = SnapEngine._line_circle_intersect(
            QPointF(-10, 0), QPointF(10, 0),
            QPointF(0, 0), radius=5.0,
        )
        assert len(pts) == 2
        xs = sorted(p.x() for p in pts)
        assert xs[0] == pytest.approx(-5.0, abs=1e-9)
        assert xs[1] == pytest.approx(5.0, abs=1e-9)
        for p in pts:
            assert p.y() == pytest.approx(0.0, abs=1e-9)
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineCircleIntersect -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-circle two intersections inside segment"
```

---

## Task 8: `_line_circle_intersect` — one inside / one outside

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the test**

```python
    def test_one_intersection_inside_one_outside_segment(self):
        """The infinite line meets the circle twice, but only one of the
        two parameter values t falls inside [0, 1]. Exactly one point
        is returned."""
        # Segment: (0, 0) -> (10, 0). Circle: center (8, 0), r=5.
        # Infinite line meets circle at x=3 and x=13.
        # x=3  → t = 0.3  (inside)
        # x=13 → t = 1.3  (outside)
        pts = SnapEngine._line_circle_intersect(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(8, 0), radius=5.0,
        )
        assert len(pts) == 1
        assert pts[0].x() == pytest.approx(3.0, abs=1e-9)
        assert pts[0].y() == pytest.approx(0.0, abs=1e-9)
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineCircleIntersect::test_one_intersection_inside_one_outside_segment -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-circle one-inside-one-outside"
```

---

## Task 9: `_line_circle_intersect` — tangent returns two identical points

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the test**

```python
    def test_tangent_returns_two_identical_points(self):
        """CURRENT CONTRACT: when the segment is tangent to the circle
        (disc == 0), the loop appends the same point twice. Spec §10.1
        calls this 'one intersection' but the code returns two. If the
        implementation changes to de-duplicate, update this test."""
        # Segment along y=5 from x=-10 to x=10.
        # Circle at origin with radius 5 → tangent at (0, 5).
        pts = SnapEngine._line_circle_intersect(
            QPointF(-10, 5), QPointF(10, 5),
            QPointF(0, 0), radius=5.0,
        )
        assert len(pts) == 2
        for p in pts:
            assert p.x() == pytest.approx(0.0, abs=1e-9)
            assert p.y() == pytest.approx(5.0, abs=1e-9)
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineCircleIntersect::test_tangent_returns_two_identical_points -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-circle tangent returns two identical points"
```

---

## Task 10: `_line_circle_intersect` — no intersection

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the test**

```python
    def test_no_intersection_returns_empty(self):
        """Segment and circle do not meet at all → ``[]``."""
        pts = SnapEngine._line_circle_intersect(
            QPointF(-10, 20), QPointF(10, 20),
            QPointF(0, 0), radius=5.0,
        )
        assert pts == []
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineCircleIntersect::test_no_intersection_returns_empty -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-circle no-intersection"
```

---

## Task 11: `_line_circle_intersect` — degenerate segment

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the test**

```python
    def test_degenerate_segment_returns_empty(self):
        """Zero-length segment → ``a < 1e-12`` → ``[]``, regardless of
        whether the point lies on the circle."""
        # Both endpoints coincide at (3, 4), which is ON a circle of
        # radius 5 at origin. Still returns empty.
        pts = SnapEngine._line_circle_intersect(
            QPointF(3, 4), QPointF(3, 4),
            QPointF(0, 0), radius=5.0,
        )
        assert pts == []
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineCircleIntersect::test_degenerate_segment_returns_empty -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-circle degenerate segment"
```

---

## Task 12: `_line_circle_intersect` — degenerate radius

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the tests**

```python
    def test_zero_radius_center_off_segment_returns_empty(self):
        """radius=0 reduces the circle to a point. When that point is
        off the segment, disc < 0 → ``[]``."""
        pts = SnapEngine._line_circle_intersect(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(5, 5), radius=0.0,
        )
        assert pts == []

    def test_zero_radius_center_on_segment_returns_center(self):
        """radius=0, center ON the segment → disc == 0 → tangent-style
        return: two identical points at the center."""
        pts = SnapEngine._line_circle_intersect(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(5, 0), radius=0.0,
        )
        # Mirrors the tangent case: two identical entries.
        assert len(pts) == 2
        for p in pts:
            assert p.x() == pytest.approx(5.0, abs=1e-9)
            assert p.y() == pytest.approx(0.0, abs=1e-9)
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestLineCircleIntersect -v`
Expected: all TestLineCircleIntersect tests passed (7 total).

**If the `center_on_segment` test fails:** this reveals a surprising behavior. Inspect the actual return value, update the expected assertion to match, and add a one-line comment noting what was observed. This is a *pin*, not a correctness assertion — the goal is to document current behavior.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): line-circle degenerate radius"
```

---

## Task 13: `_project_to_segment` — foot inside segment

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the class and first test**

```python
# ────────────────────────────────────────────────────────────────────
# _project_to_segment
# ────────────────────────────────────────────────────────────────────


class TestProjectToSegment:
    """Tests for ``SnapEngine._project_to_segment``.

    Contract (pinned from snap_engine.py:789-803):
    - Degenerate segment (``len_sq < 1e-12``) → ``None``.
    - Otherwise compute t, CLAMP to [0, 1], return foot at clamped t.
      This means the function is 'closest point on finite segment',
      not 'foot of unclamped perpendicular'.
    """

    def test_foot_inside_segment(self):
        """Cursor above the middle of a horizontal segment → foot at
        the midpoint."""
        foot = SnapEngine._project_to_segment(
            QPointF(5, 10),                  # cursor
            QPointF(0, 0), QPointF(10, 0),   # segment
        )
        assert foot is not None
        assert foot.x() == pytest.approx(5.0, abs=1e-9)
        assert foot.y() == pytest.approx(0.0, abs=1e-9)
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestProjectToSegment -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): project-to-segment foot inside segment"
```

---

## Task 14: `_project_to_segment` — clamping before / after

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the tests**

```python
    def test_foot_before_seg_a_clamps_to_seg_a(self):
        """CURRENT CONTRACT: t is clamped to [0, 1], so a cursor whose
        unclamped foot lies BEFORE seg_a returns seg_a exactly."""
        foot = SnapEngine._project_to_segment(
            QPointF(-5, 10),                 # cursor off the 'a' end
            QPointF(0, 0), QPointF(10, 0),
        )
        assert foot is not None
        assert foot.x() == pytest.approx(0.0, abs=1e-9)
        assert foot.y() == pytest.approx(0.0, abs=1e-9)

    def test_foot_after_seg_b_clamps_to_seg_b(self):
        """CURRENT CONTRACT: cursor past seg_b → returns seg_b."""
        foot = SnapEngine._project_to_segment(
            QPointF(15, 10),                 # cursor off the 'b' end
            QPointF(0, 0), QPointF(10, 0),
        )
        assert foot is not None
        assert foot.x() == pytest.approx(10.0, abs=1e-9)
        assert foot.y() == pytest.approx(0.0, abs=1e-9)
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestProjectToSegment -v`
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): project-to-segment clamping at both ends"
```

---

## Task 15: `_project_to_segment` — degenerate segment

**Files:**
- Modify: `tests/test_snap_engine_primitives.py`

- [ ] **Step 1: Append the test**

```python
    def test_degenerate_segment_returns_none(self):
        """Zero-length segment (``len_sq < 1e-12``) → ``None``."""
        foot = SnapEngine._project_to_segment(
            QPointF(5, 5),
            QPointF(3, 3), QPointF(3, 3),
        )
        assert foot is None
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_snap_engine_primitives.py::TestProjectToSegment -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): project-to-segment degenerate"
```

---

## Task 16: Full-suite verification and coverage report

**Files:** none (verification only)

- [ ] **Step 1: Run the whole new file**

Run: `pytest tests/test_snap_engine_primitives.py -v`
Expected: 17 passed (1 smoke + 8 line_line + 7 line_circle + 4 project). If any are `xfail`, note them in the PR description.

- [ ] **Step 2: Run the full snap test set to check for collateral damage**

Run: `pytest tests/test_snap_engine_primitives.py tests/test_snap_engine_case_studies.py tests/test_snap_nearest_perpendicular_decoupling.py -v`
Expected: all green (or previously-xfail).

- [ ] **Step 3: Run coverage for the three primitives only**

Run:
```bash
pytest tests/test_snap_engine_primitives.py \
  --cov=firepro3d.snap_engine \
  --cov-report=term-missing
```

Record the coverage percentage and the specific line ranges for the three primitives (`snap_engine.py:625-638`, `643-664`, `789-803`). These numbers go into the PR description, not a hard gate. If any line inside those ranges is uncovered, add a test case that exercises it (or document why it's unreachable).

- [ ] **Step 4: Confirm `snap_engine.py` is untouched**

Run: `git status firepro3d/snap_engine.py`
Expected: clean — no modifications to the source file.

- [ ] **Step 5: Commit (no-op if Step 3 added no tests)**

If Step 3 added fill-in tests:
```bash
git add tests/test_snap_engine_primitives.py
git commit -m "test(snap): cover remaining primitive branches"
```

---

## Out of Scope

- Modifications to `firepro3d/snap_engine.py` (including docstring additions, renames, or extracting epsilons to constants).
- Tests for any other `SnapEngine` method (`_geometric_snaps`, `_collect`, `find`, `_check_geometry_intersections`, phase-1/2/4 logic).
- Layer-2 matrix fixture harness — tracked as a separate P2 item in `todo.md`.
- Layer-3 case-study tests — already exist.
- Performance / timing assertions — spec §10.4 excludes them.
- CI / coverage configuration changes.
- Fixing bugs revealed by the tests — use `xfail` + new `todo.md` entry; escalate severe cases.

## Acceptance Checklist

- [ ] `tests/test_snap_engine_primitives.py` exists.
- [ ] Every §10.1 case is represented (line_line × 7, line_circle × 6, project × 4).
- [ ] Every current-behavior pin (1–5 in this plan) has an explicit test.
- [ ] Every assertion is a specific numeric/structural check.
- [ ] Tolerances anchor to engine epsilons where relevant.
- [ ] Full suite runs green (or xfail with follow-up in `todo.md`).
- [ ] Coverage of the three primitives reported in the PR description.
- [ ] `firepro3d/snap_engine.py` is untouched (`git status` clean for that file).
- [ ] Phase 6: `todo.md` line 34 marked `[x] done:2026-04-08`.

## Anticipated Follow-Ups (add to `todo.md` in Phase 6 if still relevant)

- Layer-2 matrix fixture test harness — already on roadmap.
- Extract snap primitive epsilons (`1e-10`, `1e-12`) to named constants on `SnapEngine` — surfaced by mirroring them in the test file.
- Any xfail-tagged bugs discovered during test writing.
