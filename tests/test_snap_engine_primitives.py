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

    def test_no_intersection_returns_empty(self):
        """Segment and circle do not meet at all → ``[]``."""
        pts = SnapEngine._line_circle_intersect(
            QPointF(-10, 20), QPointF(10, 20),
            QPointF(0, 0), radius=5.0,
        )
        assert pts == []

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

    def test_degenerate_segment_returns_none(self):
        """Zero-length segment (``len_sq < 1e-12``) → ``None``."""
        foot = SnapEngine._project_to_segment(
            QPointF(5, 5),
            QPointF(3, 3), QPointF(3, 3),
        )
        assert foot is None
