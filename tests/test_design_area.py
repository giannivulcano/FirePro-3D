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


# ── Tile geometry ─────────────────────────────────────────────────────────────

from firepro3d.design_area import _tile_extents, _tile_polygon
from firepro3d.constants import SQFT_TO_MM2


def _make_node(scene, x, y):
    n = Node(x, y)
    scene.addItem(n)
    return n


def _make_pipe(scene, n1, n2):
    p = Pipe(n1, n2)
    scene.addItem(p)
    return p


def _add_sprinkler(scene_qt, node):
    """Attach a real sprinkler to a node (bare-scene variant of
    Model_Space.add_sprinkler)."""
    node.add_sprinkler()
    return node.sprinkler


def _branch_of_three(scene, spacing=3000.0):
    """Three sprinklers on one X-axis branch: (0,0), (spacing,0), (2*spacing,0)."""
    nodes = [_make_node(scene, i * spacing, 0) for i in range(3)]
    _make_pipe(scene, nodes[0], nodes[1])
    _make_pipe(scene, nodes[1], nodes[2])
    return [_add_sprinkler(scene, n) for n in nodes]


FALLBACK_130 = math.sqrt(130.0 * SQFT_TO_MM2) / 2.0   # ≈ 1737.7 mm


class TestTileExtents:
    def test_middle_sprinkler_shares_half_gap(self, scene):
        sprs = _branch_of_three(scene)
        ext, angle = _tile_extents(sprs[1], sprs, walls=[], ppm=1.0)
        fwd, back, left, right = ext
        assert fwd == pytest.approx(1500.0)
        assert back == pytest.approx(1500.0)
        # No cross-branch neighbours, no walls → fallback on L sides
        assert left == pytest.approx(FALLBACK_130, rel=1e-3)
        assert right == pytest.approx(FALLBACK_130, rel=1e-3)

    def test_end_sprinkler_stops_at_wall(self, scene):
        sprs = _branch_of_three(scene)
        # Wall 1000mm beyond the last sprinkler (x = 7000), facing the branch
        wall = _mock_wall(7000, -5000, 7000, 5000)
        ext, _ = _tile_extents(sprs[2], sprs, walls=[wall], ppm=1.0)
        fwd, back, left, right = ext
        # Branch orientation (fwd vs back) depends on _branch_direction's
        # vector averaging — assert the pair, not which side is which.
        along = sorted((fwd, back))
        assert along[0] == pytest.approx(1000.0)   # stops AT the wall, not 2×
        assert along[1] == pytest.approx(1500.0)   # half-gap to middle sprinkler
        assert along[0] < 1737.0                   # regression: no √cov overshoot

    def test_neighbour_and_wall_on_same_side_takes_nearer(self, scene):
        sprs = _branch_of_three(scene)
        # Wall between middle and end sprinkler, 1200mm from middle
        wall = _mock_wall(4200, -5000, 4200, 5000)
        ext, _ = _tile_extents(sprs[1], sprs, walls=[wall], ppm=1.0)
        # Wall side: min(wall 1200, half-gap 1500) = 1200; other side 1500.
        assert sorted(ext[:2]) == pytest.approx([1200.0, 1500.0])

    def test_cross_branch_neighbour_halves_l(self, scene):
        # Two parallel X branches 4000mm apart in Y
        a = [_make_node(scene, x, 0) for x in (0.0, 3000.0)]
        b = [_make_node(scene, x, 4000.0) for x in (0.0, 3000.0)]
        _make_pipe(scene, a[0], a[1])
        _make_pipe(scene, b[0], b[1])
        sprs = [_add_sprinkler(scene, n) for n in (*a, *b)]
        ext, _ = _tile_extents(sprs[0], sprs, walls=[], ppm=1.0)
        fwd, back, left, right = ext
        # Perp neighbour at +4000 in Y → half = 2000 on that side only
        assert sorted((left, right)) == pytest.approx(
            sorted((2000.0, FALLBACK_130)), rel=1e-3)

    def test_isolated_sprinkler_falls_back_square(self, scene):
        n = _make_node(scene, 0, 0)
        spr = _add_sprinkler(scene, n)
        ext, angle = _tile_extents(spr, [spr], walls=[], ppm=1.0)
        assert all(e == pytest.approx(FALLBACK_130, rel=1e-3) for e in ext)
        assert angle == 0.0


class TestTilePolygon:
    def test_axis_aligned_asymmetric(self):
        poly = _tile_polygon(100.0, 200.0, 0.0, 1500.0, 1000.0, 600.0, 400.0)
        xs = sorted(set(round(poly[i].x() - 100.0, 3) for i in range(poly.count())))
        ys = sorted(set(round(poly[i].y() - 200.0, 3) for i in range(poly.count())))
        assert xs == [-1000.0, 1500.0]    # cx-back .. cx+fwd
        assert ys == [-400.0, 600.0]      # cy-right(-perp) .. cy+left(+perp)

    def test_rotation_preserves_area(self):
        poly = _tile_polygon(0.0, 0.0, math.radians(30), 1500.0, 1500.0, 1000.0, 1000.0)
        # Shoelace area must equal (fwd+back) × (left+right)
        area = 0.0
        for i in range(poly.count()):
            p, q = poly[i], poly[(i + 1) % poly.count()]
            area += p.x() * q.y() - q.x() * p.y()
        assert abs(area) / 2.0 == pytest.approx(3000.0 * 2000.0)
