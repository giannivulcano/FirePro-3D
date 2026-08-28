"""Direct tests for tool_geometry.py — the pure item-aware geometry helpers
extracted from SceneToolsMixin (Model_Space decomposition slice A).

The behavior is already exercised through the SceneToolsMixin wrappers in
tests/test_scene_tools.py (the parity net). These tests lock the *module* API
directly and cover the two helpers the parity net never touched:
point_to_segment_dist and compute_extend_intersections.
"""

from __future__ import annotations

import math
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d import tool_geometry as tg
from firepro3d.construction_geometry import (
    LineItem, PolylineItem, CircleItem, RectangleItem, ArcItem,
)


# ---------------------------------------------------------------------------
# Pure point math — no Qt scene needed
# ---------------------------------------------------------------------------

class TestOffsetLineIntersection:
    def test_angled_lines(self):
        pt = tg.offset_line_intersection(
            QPointF(0, 0), QPointF(1, 1),
            QPointF(10, 0), QPointF(-1, 1))
        assert pt is not None
        assert abs(pt.x() - 5.0) < 1e-6
        assert abs(pt.y() - 5.0) < 1e-6

    def test_parallel_returns_none(self):
        assert tg.offset_line_intersection(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(0, 5), QPointF(1, 0)) is None


class TestOffsetPolylinePts:
    def test_horizontal_offset(self):
        pts = [QPointF(0, 0), QPointF(100, 0)]
        result = tg.offset_polyline_pts(pts, 10.0)
        assert len(result) == 2
        for p in result:
            assert abs(p.y() - 10.0) < 1e-6

    def test_empty(self):
        assert tg.offset_polyline_pts([], 10.0) == []


class TestPointToSegmentDist:
    """Not covered by the parity net — direct coverage here."""

    def test_perpendicular_foot_inside(self):
        d = tg.point_to_segment_dist(
            QPointF(50, 30), QPointF(0, 0), QPointF(100, 0))
        assert abs(d - 30.0) < 1e-9

    def test_clamps_before_start(self):
        d = tg.point_to_segment_dist(
            QPointF(-30, 40), QPointF(0, 0), QPointF(100, 0))
        assert abs(d - 50.0) < 1e-9  # distance to endpoint (0,0)

    def test_clamps_after_end(self):
        d = tg.point_to_segment_dist(
            QPointF(130, 40), QPointF(0, 0), QPointF(100, 0))
        assert abs(d - 50.0) < 1e-9  # distance to endpoint (100,0)

    def test_degenerate_segment(self):
        d = tg.point_to_segment_dist(
            QPointF(3, 4), QPointF(0, 0), QPointF(0, 0))
        assert abs(d - 5.0) < 1e-9


# ---------------------------------------------------------------------------
# Item-aware helpers — need a QApplication (qapp fixture) for item construction
# ---------------------------------------------------------------------------

@pytest.fixture
def scene(qapp):
    sc = QGraphicsScene()
    yield sc


class TestGetItemSegments:
    def test_line(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(30, 40))
        scene.addItem(line)
        segs = tg.get_item_segments(line)
        assert len(segs) == 1 and segs[0][0] == "line"

    def test_rectangle_four_edges(self, scene):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 50))
        scene.addItem(rect)
        segs = tg.get_item_segments(rect)
        assert len(segs) == 4
        assert all(s[0] == "line" for s in segs)


class TestComputeFillet:
    def test_perpendicular_lines(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        l2 = LineItem(QPointF(0, 0), QPointF(0, 100))
        scene.addItem(l1)
        scene.addItem(l2)
        data = tg.compute_fillet(l1, l2, 10.0)
        assert data is not None
        assert abs(data["center"].x() - 10.0) < 1e-3
        assert abs(data["center"].y() - 10.0) < 1e-3

    def test_non_line_returns_none(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        c1 = CircleItem(QPointF(50, 50), 30)
        scene.addItem(l1)
        scene.addItem(c1)
        assert tg.compute_fillet(l1, c1, 10.0) is None


class TestExtractEdges:
    def test_none(self):
        assert tg.extract_edges(None) == []

    def test_polyline_two_segments(self, scene):
        pl = PolylineItem(QPointF(0, 0))
        pl.append_point(QPointF(100, 0))
        pl.append_point(QPointF(100, 100))
        scene.addItem(pl)
        assert len(tg.extract_edges(pl)) == 2


class TestComputeExtendIntersections:
    """Not covered by the parity net — direct coverage here."""

    def test_line_extends_forward_to_boundary(self, scene):
        # Horizontal line (0,0)-(50,0); extend the pt2 end toward +x.
        line = LineItem(QPointF(0, 0), QPointF(50, 0))
        # Vertical boundary at x=100.
        boundary = LineItem(QPointF(100, -50), QPointF(100, 50))
        scene.addItem(line)
        scene.addItem(boundary)
        pts = tg.compute_extend_intersections(line, 2, boundary)
        assert len(pts) == 1
        assert abs(pts[0].x() - 100.0) < 1e-6
        assert abs(pts[0].y() - 0.0) < 1e-6

    def test_polyline_interior_grip_returns_empty(self, scene):
        pl = PolylineItem(QPointF(0, 0))
        pl.append_point(QPointF(50, 0))
        pl.append_point(QPointF(100, 0))
        boundary = LineItem(QPointF(200, -50), QPointF(200, 50))
        scene.addItem(pl)
        scene.addItem(boundary)
        # grip_idx 1 is an interior vertex → cannot extend.
        assert tg.compute_extend_intersections(pl, 1, boundary) == []
