"""tests/test_design_area.py — Design-area tile geometry, As cap, pick mode."""

from __future__ import annotations

import math

import pytest
from unittest.mock import MagicMock
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.node import Node
from firepro3d.pipe import Pipe
from firepro3d.design_area import (
    _closest_point_on_segment,
    _wall_distance_on_side,
)


@pytest.fixture
def scene(qapp):
    return QGraphicsScene()


def _mock_wall(x1, y1, x2, y2, level="Level 1"):
    """Wall stub exposing the attrs design_area geometry reads."""
    w = MagicMock()
    w.pt1 = QPointF(x1, y1)
    w.pt2 = QPointF(x2, y2)
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    w.normal.return_value = (-dy / length, dx / length)
    w.level = level
    return w


class TestClosestPointOnSegment:
    def test_interior_projection(self):
        cx, cy = _closest_point_on_segment(5, 3, 0, 0, 10, 0)
        assert (cx, cy) == (5.0, 0.0)

    def test_clamped_to_endpoint(self):
        cx, cy = _closest_point_on_segment(-4, 2, 0, 0, 10, 0)
        assert (cx, cy) == (0.0, 0.0)

    def test_degenerate_segment(self):
        cx, cy = _closest_point_on_segment(3, 4, 1, 1, 1, 1)
        assert (cx, cy) == (1.0, 1.0)


class TestWallDistanceOnSide:
    """Side-aware wall lookup: wall must face the query direction AND lie on
    that side of the point."""

    def test_wall_on_queried_side(self):
        # Vertical wall at x=1000; sprinkler at origin; query +X direction.
        wall = _mock_wall(1000, -5000, 1000, 5000)
        d = _wall_distance_on_side(0, 0, 1.0, 0.0, [wall])
        assert d == pytest.approx(1000.0)

    def test_wall_on_opposite_side_ignored(self):
        wall = _mock_wall(1000, -5000, 1000, 5000)
        d = _wall_distance_on_side(0, 0, -1.0, 0.0, [wall])
        assert d is None

    def test_parallel_wall_ignored(self):
        # Horizontal wall — its normal is perpendicular to the +X query.
        wall = _mock_wall(-5000, 1000, 5000, 1000)
        d = _wall_distance_on_side(0, 0, 1.0, 0.0, [wall])
        assert d is None

    def test_nearest_of_two_walls_wins(self):
        near = _mock_wall(800, -5000, 800, 5000)
        far = _mock_wall(2000, -5000, 2000, 5000)
        d = _wall_distance_on_side(0, 0, 1.0, 0.0, [far, near])
        assert d == pytest.approx(800.0)
