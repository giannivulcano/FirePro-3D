"""Tests for the Align tool: geometric primitives, edge extraction, and tool
integration. (The padlock / alignment-lock half retired with the legacy
constraint prototype — parametric-constraint-system.md §2.)"""

from __future__ import annotations

import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_intersect import is_parallel, perpendicular_translation


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


class TestPerpendicularTranslation:
    """perpendicular_translation(ref_p1, ref_p2, target_point) → QPointF delta"""

    def test_horizontal_ref_point_above(self):
        """Point above horizontal line → delta moves it down to the line."""
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(50, 30),
        )
        assert abs(delta.x()) < 1e-6
        assert abs(delta.y() - (-30.0)) < 1e-6

    def test_vertical_ref_point_right(self):
        """Point right of vertical line → delta moves it left to the line."""
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(0, 100),
            QPointF(20, 50),
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
            QPointF(50, 60),
        )
        new_x = 50 + delta.x()
        new_y = 60 + delta.y()
        assert abs(new_x - new_y) < 1e-6


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
        assert extract_edges("not_an_item") == []


from PyQt6.QtWidgets import QGraphicsScene


class TestAlignToolIntegration:
    """End-to-end tests using real scene items."""

    def test_align_gridline_to_line(self, qapp):
        """Gridline at x=100 aligns to a vertical line at x=50."""
        scene = QGraphicsScene()
        gl = GridlineItem(QPointF(100, 0), QPointF(100, 500), "A")
        scene.addItem(gl)

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
        assert abs(line.p1().x() - 100.0) < 1.0

    def test_point_item_projects_onto_reference(self, qapp):
        """A point at (30, 70) projected onto y=0 horizontal line → (30, 0)."""
        from firepro3d.geometry_intersect import perpendicular_translation
        delta = perpendicular_translation(
            QPointF(0, 0), QPointF(100, 0),
            QPointF(30, 70),
        )
        new_y = 70 + delta.y()
        assert abs(new_y) < 1e-6
        assert abs(delta.x()) < 1e-6
