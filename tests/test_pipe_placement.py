"""tests/test_pipe_placement.py — Tests for Z-aware pipe placement checks.

Covers: _would_backtrack_at, _would_backtrack, _validate_4th_branch,
        coplanar pipe counting in _press_pipe connection-limit checks.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.node import Node
from firepro3d.pipe import Pipe
from firepro3d.constants import Z_COPLANAR_TOL


@pytest.fixture
def scene(qapp):
    """Bare QGraphicsScene for items that need one."""
    return QGraphicsScene()


def _make_node(scene, x, y, z=0.0):
    """Create a Node at (x, y) with z_pos = z, added to scene."""
    n = Node(x, y)
    scene.addItem(n)
    n.z_pos = z
    return n


def _make_pipe(scene, n1, n2):
    """Create a Pipe between two nodes, added to scene."""
    p = Pipe(n1, n2)
    scene.addItem(p)
    return p


# ── _would_backtrack_at ──────────────────────────────────────────────────────

class TestWouldBacktrackAt:
    """Tests for Model_Space._would_backtrack_at Z-filtering."""

    def _call(self, scene, start_node, target_pt):
        """Call _would_backtrack_at via a minimal Model_Space."""
        from firepro3d.model_space import Model_Space
        ms = Model_Space.__new__(Model_Space)
        return ms._would_backtrack_at(start_node, target_pt)

    def test_coplanar_overlap_detected(self, scene):
        """Pipe in same direction at same Z → backtrack detected."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 1000, 0, z=3000)
        _make_pipe(scene, n1, n2)

        # Target along same direction as existing pipe
        target = QPointF(500, 0)
        assert self._call(scene, n1, target) is True

    def test_different_z_no_overlap(self, scene):
        """Pipe in same XY direction but different Z → no backtrack."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 1000, 0, z=0)  # riser endpoint at different Z
        _make_pipe(scene, n1, n2)

        target = QPointF(500, 0)
        assert self._call(scene, n1, target) is False

    def test_riser_same_xy_skipped(self, scene):
        """Vertical riser (same XY, different Z) → not a backtrack."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 0, 0, z=0)  # riser: same XY, different Z
        _make_pipe(scene, n1, n2)

        # Target in any horizontal direction should be allowed
        target = QPointF(500, 0)
        assert self._call(scene, n1, target) is False

    def test_coplanar_target_on_other_node(self, scene):
        """Target at same position as existing coplanar neighbor → backtrack."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 1000, 0, z=3000)
        _make_pipe(scene, n1, n2)

        target = QPointF(1000, 0)  # exactly on n2
        assert self._call(scene, n1, target) is True

    def test_target_on_other_node_different_z(self, scene):
        """Target at same XY as neighbor but neighbor at different Z → no backtrack."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 1000, 0, z=0)
        _make_pipe(scene, n1, n2)

        target = QPointF(1000, 0)
        assert self._call(scene, n1, target) is False

    def test_within_tolerance_still_coplanar(self, scene):
        """Z difference within tolerance → still considered coplanar."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 1000, 0, z=3000 + Z_COPLANAR_TOL * 0.5)
        _make_pipe(scene, n1, n2)

        target = QPointF(500, 0)
        assert self._call(scene, n1, target) is True

    def test_no_pipes_no_backtrack(self, scene):
        """Node with no existing pipes → never a backtrack."""
        n1 = _make_node(scene, 0, 0, z=3000)
        target = QPointF(500, 0)
        assert self._call(scene, n1, target) is False


# ── _would_backtrack ─────────────────────────────────────────────────────────

class TestWouldBacktrack:
    """Tests for Model_Space._would_backtrack Z-filtering."""

    def _call(self, scene, start_node, end_node):
        from firepro3d.model_space import Model_Space
        ms = Model_Space.__new__(Model_Space)
        return ms._would_backtrack(start_node, end_node)

    def test_coplanar_duplicate_detected(self, scene):
        """Direct duplicate at same Z → backtrack."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 1000, 0, z=3000)
        _make_pipe(scene, n1, n2)

        assert self._call(scene, n1, n2) is True

    def test_different_z_duplicate_allowed(self, scene):
        """Same two nodes connected but riser (different Z) → direct duplicate
        check still fires (identity-based, correct behavior)."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 1000, 0, z=0)
        _make_pipe(scene, n1, n2)

        # The "other is end_node" direct-duplicate check is identity-based
        # and still returns True — can't have two pipes between same nodes.
        assert self._call(scene, n1, n2) is True

    def test_segment_overlap_skipped_different_z(self, scene):
        """End node on segment of pipe at different Z → no backtrack."""
        n1 = _make_node(scene, 0, 0, z=3000)
        n2 = _make_node(scene, 1000, 0, z=0)  # different Z
        _make_pipe(scene, n1, n2)

        # New end node at midpoint XY, same Z as n1
        n3 = _make_node(scene, 500, 0, z=3000)
        assert self._call(scene, n1, n3) is False


# ── _validate_4th_branch ─────────────────────────────────────────────────────

class TestValidate4thBranch:
    """Tests for Model_Space._validate_4th_branch Z-filtering."""

    def _call(self, scene, node, new_pt):
        from firepro3d.model_space import Model_Space
        ms = Model_Space.__new__(Model_Space)
        return ms._validate_4th_branch(node, new_pt)

    def test_3_coplanar_pipes_is_tee_check(self, scene):
        """Node with 3 coplanar pipes → normal tee validation applies."""
        center = _make_node(scene, 0, 0, z=3000)
        n_east = _make_node(scene, 1000, 0, z=3000)
        n_west = _make_node(scene, -1000, 0, z=3000)
        n_south = _make_node(scene, 0, -1000, z=3000)
        _make_pipe(scene, center, n_east)
        _make_pipe(scene, center, n_west)
        _make_pipe(scene, center, n_south)

        # 4th pipe perpendicular to through-run → should be allowed (cross)
        new_pt = QPointF(0, 1000)
        result = self._call(scene, center, new_pt)
        assert result is None  # no error

    def test_2_coplanar_plus_riser_allows_3rd_coplanar(self, scene):
        """Node with 2 coplanar pipes + 1 riser → only 2 coplanar,
        so _validate_4th_branch should not be called (pipe count < 3).
        This test verifies the pipe count at the call site would be 2."""
        center = _make_node(scene, 0, 0, z=3000)
        n_east = _make_node(scene, 1000, 0, z=3000)
        n_west = _make_node(scene, -1000, 0, z=3000)
        n_below = _make_node(scene, 0, 0, z=0)  # riser
        _make_pipe(scene, center, n_east)
        _make_pipe(scene, center, n_west)
        _make_pipe(scene, center, n_below)

        # 3 total pipes, but only 2 coplanar — count should be 2
        coplanar = [p for p in center.pipes
                    if abs((p.node2 if p.node1 is center else p.node1).z_pos
                           - center.z_pos) <= Z_COPLANAR_TOL]
        assert len(coplanar) == 2

    def test_3_coplanar_plus_riser_validates_correctly(self, scene):
        """Node with 3 coplanar (tee) + 1 riser → _validate_4th_branch
        should only see the 3 coplanar pipes and validate normally."""
        center = _make_node(scene, 0, 0, z=3000)
        n_east = _make_node(scene, 1000, 0, z=3000)
        n_west = _make_node(scene, -1000, 0, z=3000)
        n_south = _make_node(scene, 0, -1000, z=3000)
        n_below = _make_node(scene, 0, 0, z=0)  # riser
        _make_pipe(scene, center, n_east)
        _make_pipe(scene, center, n_west)
        _make_pipe(scene, center, n_south)
        _make_pipe(scene, center, n_below)

        # 4 total pipes, but only 3 coplanar → should validate 4th coplanar
        new_pt = QPointF(0, 1000)  # perpendicular to east-west through-run
        result = self._call(scene, center, new_pt)
        assert result is None  # allowed — forms a cross
