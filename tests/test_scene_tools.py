"""Tests for scene_tools.py — geometry editing helpers.

Covers:
- Offset algorithm (line intersection, polyline offset, perpendicular distance)
- Fillet / chamfer geometry computation
- Break / break-at-point logic
- _find_grip_hit (closest grip detection)
- extract_edges helper
- _get_item_segments
- _offset_signed_dist (side detection)
"""

from __future__ import annotations

import math
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import (
    LineItem, PolylineItem, CircleItem, RectangleItem, ArcItem,
)
from firepro3d.scene_tools import SceneTools, extract_edges
from firepro3d.cad_math import CAD_Math
from firepro3d import geometry_intersect as gi


def _flush():
    """Pump the Qt event loop so deferred scene updates take effect."""
    QApplication.processEvents()


# ---------------------------------------------------------------------------
# Minimal scene stub that satisfies SceneTools's dependencies
# ---------------------------------------------------------------------------

class _StubScene(QGraphicsScene):
    """Thin scene that composes SceneTools and provides required attrs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tools = SceneTools(self)
        self._draw_lines: list = []
        self._draw_rects: list = []
        self._draw_circles: list = []
        self._draw_arcs: list = []
        self._polylines: list = []
        self._constraints: list = []
        self._offset_preview = None
        self._trim_edge = None
        self._trim_edge_highlight = None
        self._extend_boundary = None
        self._extend_boundary_highlight = None
        self._merge_point1 = None
        self._merge_preview = None
        self._constraint_circle_a = None
        self._constraint_grip_a = None
        self._stretch_vertices: list = []
        self._stretch_full_items: list = []
        self._selected_items: list = []
        self._align_reference = None
        self._align_highlight = None
        self._align_ghost = None
        self._align_padlocks: list = []
        self._grip_tolerance_px = 12
        self.active_level = "Level 1"

    def _show_status(self, msg, timeout=0):
        pass

    def push_undo_state(self):
        pass


@pytest.fixture
def scene(qapp):
    """Provide a stub scene with an attached view (needed for scale-aware helpers)."""
    sc = _StubScene()
    view = QGraphicsView(sc)
    # resize is enough to establish a valid transform — no need to show()
    view.resize(800, 600)
    qapp.processEvents()
    sc._test_view = view  # prevent GC from detaching the view
    yield sc
    view.close()


# =========================================================================
# 1. OFFSET ALGORITHM
# =========================================================================


class TestOffsetLineIntersection:
    """SceneTools._offset_line_intersection — 2D infinite line intersect."""

    def test_perpendicular_lines(self, scene):
        # Horizontal line through origin, vertical line through (5,0)
        pt = scene._tools._offset_line_intersection(
            QPointF(0, 0), QPointF(1, 0),   # line 1: horizontal
            QPointF(5, 0), QPointF(0, 1),   # line 2: vertical at x=5
        )
        assert pt is not None
        assert abs(pt.x() - 5.0) < 1e-6
        assert abs(pt.y() - 0.0) < 1e-6

    def test_angled_lines(self, scene):
        # y = x  and  y = -x + 10  => intersect at (5, 5)
        pt = scene._tools._offset_line_intersection(
            QPointF(0, 0), QPointF(1, 1),
            QPointF(10, 0), QPointF(-1, 1),
        )
        assert pt is not None
        assert abs(pt.x() - 5.0) < 1e-6
        assert abs(pt.y() - 5.0) < 1e-6

    def test_parallel_returns_none(self, scene):
        pt = scene._tools._offset_line_intersection(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(0, 5), QPointF(1, 0),
        )
        assert pt is None

    def test_identical_lines_returns_none(self, scene):
        pt = scene._tools._offset_line_intersection(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(0, 0), QPointF(1, 0),
        )
        assert pt is None

    def test_45_degree_lines(self, scene):
        # line1: y=0 (horizontal), line2: y=x (45 deg through origin)
        pt = scene._tools._offset_line_intersection(
            QPointF(0, 0), QPointF(1, 0),
            QPointF(0, 0), QPointF(1, 1),
        )
        assert pt is not None
        assert abs(pt.x() - 0.0) < 1e-6
        assert abs(pt.y() - 0.0) < 1e-6


class TestOffsetPolylinePts:
    """SceneTools._offset_polyline_pts — miter-join offset."""

    def test_horizontal_line_offset_up(self, scene):
        pts = [QPointF(0, 0), QPointF(100, 0)]
        result = scene._tools._offset_polyline_pts(pts, 10.0)
        assert len(result) == 2
        # Left-normal of rightward segment is (0, -1) => offset by +10 means y = -10
        # (signed_dist positive with left-normal (-dy, dx))
        # For segment (0,0)->(100,0): dx=100, dy=0 => normal=(-0, 1)=(0,1)
        # offset by +10 => y increases by 10
        for p in result:
            assert abs(p.y() - 10.0) < 1e-6

    def test_horizontal_line_offset_down(self, scene):
        pts = [QPointF(0, 0), QPointF(100, 0)]
        result = scene._tools._offset_polyline_pts(pts, -10.0)
        assert len(result) == 2
        for p in result:
            assert abs(p.y() - (-10.0)) < 1e-6

    def test_l_shape_miter(self, scene):
        """L-shaped polyline: right then up. Miter should produce clean corner."""
        pts = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)]
        result = scene._tools._offset_polyline_pts(pts, 10.0)
        assert len(result) == 3
        # First segment (0,0)->(100,0): normal (0,1) => offset y+10
        assert abs(result[0].y() - 10.0) < 1e-6
        # Last segment (100,0)->(100,100): dx=0, dy=100 => normal (-1,0)
        # offset by 10 in direction (-1,0) => x decreases by 10
        assert abs(result[2].x() - 90.0) < 1e-6

    def test_single_point_returns_copy(self, scene):
        pts = [QPointF(5, 5)]
        result = scene._tools._offset_polyline_pts(pts, 10.0)
        assert len(result) == 1

    def test_empty_input(self, scene):
        result = scene._tools._offset_polyline_pts([], 10.0)
        assert result == []


class TestPerpendicularDistance:
    """SceneTools._perpendicular_distance — distance from point to entity."""

    def test_line_distance(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        d = scene._tools._perpendicular_distance(line, QPointF(50, 30))
        assert abs(d - 30.0) < 1e-3

    def test_line_distance_zero(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        d = scene._tools._perpendicular_distance(line, QPointF(50, 0))
        assert abs(d) < 1e-3

    def test_circle_distance_outside(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)
        # _perpendicular_distance uses boundingRect().width()/2 as radius,
        # which includes cosmetic pen padding (~55 for a 50-radius circle).
        r_effective = circle.boundingRect().width() / 2
        d = scene._tools._perpendicular_distance(circle, QPointF(100, 0))
        assert abs(d - (100.0 - r_effective)) < 1e-3

    def test_circle_distance_inside(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)
        r_effective = circle.boundingRect().width() / 2
        d = scene._tools._perpendicular_distance(circle, QPointF(20, 0))
        assert abs(d - (r_effective - 20.0)) < 1e-3

    def test_polyline_distance(self, scene):
        pl = PolylineItem(QPointF(0, 0))
        pl.append_point(QPointF(100, 0))
        scene.addItem(pl)
        d = scene._tools._perpendicular_distance(pl, QPointF(50, 20))
        assert abs(d - 20.0) < 1e-3

    def test_arc_distance(self, scene):
        arc = ArcItem(QPointF(0, 0), 50.0, 0, 180)
        scene.addItem(arc)
        # Point at (80, 0) => distance = |80 - 50| = 30
        d = scene._tools._perpendicular_distance(arc, QPointF(80, 0))
        assert abs(d - 30.0) < 1e-3

    def test_rectangle_distance_outside(self, scene):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
        scene.addItem(rect)
        # Point at (150, 50) => nearest edge at x=100 => distance = 50
        d = scene._tools._perpendicular_distance(rect, QPointF(150, 50))
        assert abs(d - 50.0) < 1e-3

    def test_rectangle_distance_inside(self, scene):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
        scene.addItem(rect)
        # Point at (10, 50) => nearest edge is left (x=0) => distance = 10
        d = scene._tools._perpendicular_distance(rect, QPointF(10, 50))
        assert abs(d - 10.0) < 1e-3


class TestOffsetSignedDist:
    """SceneTools._offset_signed_dist — side detection."""

    def test_line_left_side_positive(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        # Point above the line (y > 0) is on the left for rightward segment
        # Cross product: dx*(side_y - p1_y) - dy*(side_x - p1_x)
        # 100*(50-0) - 0*(50-0) = 5000 > 0 => left => positive
        sd = scene._tools._offset_signed_dist(line, 10.0, QPointF(50, 50))
        assert sd == 10.0

    def test_line_right_side_negative(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        sd = scene._tools._offset_signed_dist(line, 10.0, QPointF(50, -50))
        assert sd == -10.0

    def test_circle_outside_positive(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)
        sd = scene._tools._offset_signed_dist(circle, 10.0, QPointF(100, 0))
        assert sd == 10.0  # outside => grow

    def test_circle_inside_negative(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)
        sd = scene._tools._offset_signed_dist(circle, 10.0, QPointF(10, 0))
        assert sd == -10.0  # inside => shrink

    def test_rectangle_outside_positive(self, scene):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
        scene.addItem(rect)
        sd = scene._tools._offset_signed_dist(rect, 5.0, QPointF(150, 50))
        assert sd == 5.0

    def test_rectangle_inside_negative(self, scene):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
        scene.addItem(rect)
        sd = scene._tools._offset_signed_dist(rect, 5.0, QPointF(50, 50))
        assert sd == -5.0

    def test_arc_outside_positive(self, scene):
        arc = ArcItem(QPointF(0, 0), 50.0, 0, 180)
        scene.addItem(arc)
        sd = scene._tools._offset_signed_dist(arc, 10.0, QPointF(80, 0))
        assert sd == 10.0

    def test_arc_inside_negative(self, scene):
        arc = ArcItem(QPointF(0, 0), 50.0, 0, 180)
        scene.addItem(arc)
        sd = scene._tools._offset_signed_dist(arc, 10.0, QPointF(10, 0))
        assert sd == -10.0


# =========================================================================
# 2. FILLET / CHAMFER
# =========================================================================


class TestComputeFillet:
    """SceneTools._compute_fillet — arc data between two lines."""

    def test_perpendicular_lines_radius_10(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        l2 = LineItem(QPointF(0, 0), QPointF(0, 100))
        scene.addItem(l1)
        scene.addItem(l2)

        data = scene._tools._compute_fillet(l1, l2, 10.0)
        assert data is not None
        assert abs(data["radius"] - 10.0) < 1e-6
        # Center should be at (10, 10) — 10 away from both axes
        assert abs(data["center"].x() - 10.0) < 1e-3
        assert abs(data["center"].y() - 10.0) < 1e-3
        # Tangent points
        assert abs(data["tp1"].y()) < 1e-3   # on x-axis
        assert abs(data["tp2"].x()) < 1e-3   # on y-axis

    def test_parallel_lines_returns_none(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        l2 = LineItem(QPointF(0, 50), QPointF(100, 50))
        scene.addItem(l1)
        scene.addItem(l2)
        assert scene._tools._compute_fillet(l1, l2, 10.0) is None

    def test_non_line_items_returns_none(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        c1 = CircleItem(QPointF(50, 50), 30)
        scene.addItem(l1)
        scene.addItem(c1)
        assert scene._tools._compute_fillet(l1, c1, 10.0) is None

    def test_45_degree_lines(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        l2 = LineItem(QPointF(0, 0), QPointF(100, 100))
        scene.addItem(l1)
        scene.addItem(l2)

        data = scene._tools._compute_fillet(l1, l2, 10.0)
        assert data is not None
        assert abs(data["radius"] - 10.0) < 1e-6


class TestComputeChamfer:
    """SceneTools._compute_chamfer — bevel line between two lines."""

    def test_perpendicular_lines_dist_10(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        l2 = LineItem(QPointF(0, 0), QPointF(0, 100))
        scene.addItem(l1)
        scene.addItem(l2)

        data = scene._tools._compute_chamfer(l1, l2, 10.0)
        assert data is not None
        # Chamfer points should be 10 units along each line from intersection
        assert abs(data["cp1"].x() - 10.0) < 1e-3
        assert abs(data["cp1"].y()) < 1e-3
        assert abs(data["cp2"].x()) < 1e-3
        assert abs(data["cp2"].y() - 10.0) < 1e-3

    def test_parallel_lines_returns_none(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        l2 = LineItem(QPointF(0, 50), QPointF(100, 50))
        scene.addItem(l1)
        scene.addItem(l2)
        assert scene._tools._compute_chamfer(l1, l2, 10.0) is None

    def test_non_line_items_returns_none(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        c1 = CircleItem(QPointF(50, 50), 30)
        scene.addItem(l1)
        scene.addItem(c1)
        assert scene._tools._compute_chamfer(l1, c1, 10.0) is None

    def test_meeting_at_nonorigin_intersection(self, scene):
        l1 = LineItem(QPointF(-50, 50), QPointF(50, 50))
        l2 = LineItem(QPointF(50, 0), QPointF(50, 100))
        scene.addItem(l1)
        scene.addItem(l2)

        data = scene._tools._compute_chamfer(l1, l2, 15.0)
        assert data is not None
        # Intersection is at (50, 50)
        # l1: unit vector from (50,50) toward far end (-50,50) is (-1,0); cp1 at (35, 50)
        # l2: unit vector from (50,50) toward far end depends on near end detection
        assert data["cp1"] is not None
        assert data["cp2"] is not None


# =========================================================================
# 3. BREAK / BREAK AT POINT
# =========================================================================


class TestBreakAtPoint:
    """SceneTools._break_at_point — splitting items."""

    def test_line_split_at_midpoint(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        scene._draw_lines.append(line)

        scene._tools._break_at_point(line, QPointF(50, 0))

        # Original should be removed; two new lines created
        assert line not in scene._draw_lines
        assert len(scene._draw_lines) == 2

        # Verify the pieces
        pieces = sorted(scene._draw_lines, key=lambda l: l._pt1.x())
        assert abs(pieces[0]._pt1.x()) < 1e-3
        assert abs(pieces[0]._pt2.x() - 50.0) < 1e-3
        assert abs(pieces[1]._pt1.x() - 50.0) < 1e-3
        assert abs(pieces[1]._pt2.x() - 100.0) < 1e-3

    def test_line_split_at_quarter(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        scene._draw_lines.append(line)

        scene._tools._break_at_point(line, QPointF(25, 0))

        assert len(scene._draw_lines) == 2
        pieces = sorted(scene._draw_lines, key=lambda l: l._pt1.x())
        assert abs(pieces[0]._pt2.x() - 25.0) < 1e-3
        assert abs(pieces[1]._pt1.x() - 25.0) < 1e-3

    def test_circle_break_produces_arc(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)
        scene._draw_circles.append(circle)

        scene._tools._break_at_point(circle, QPointF(50, 0))

        assert circle not in scene._draw_circles
        assert len(scene._draw_arcs) == 1
        arc = scene._draw_arcs[0]
        assert abs(arc._radius - 50.0) < 1e-3
        assert abs(arc._span_deg - 359.0) < 1e-3

    def test_arc_break_produces_two_arcs(self, scene):
        arc = ArcItem(QPointF(0, 0), 50.0, 0, 180)
        scene.addItem(arc)
        scene._draw_arcs.append(arc)

        # Break at 90 degrees (top of arc)
        bp = QPointF(50.0 * math.cos(math.radians(90)),
                     50.0 * math.sin(math.radians(90)))
        scene._tools._break_at_point(arc, bp)

        assert arc not in scene._draw_arcs
        assert len(scene._draw_arcs) == 2


class TestBreakItem:
    """SceneTools._break_item — removing segment between two points."""

    def test_line_break_between(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        scene._draw_lines.append(line)

        scene._tools._break_item(line, QPointF(25, 0), QPointF(75, 0))

        assert line not in scene._draw_lines
        assert len(scene._draw_lines) == 2
        pieces = sorted(scene._draw_lines, key=lambda l: l._pt1.x())
        # First piece: (0,0) to ~(25,0)
        assert abs(pieces[0]._pt2.x() - 25.0) < 1e-3
        # Second piece: ~(75,0) to (100,0)
        assert abs(pieces[1]._pt1.x() - 75.0) < 1e-3

    def test_circle_break_produces_arc(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)
        scene._draw_circles.append(circle)

        # Break between 0 degrees and 90 degrees
        bp1 = QPointF(50, 0)   # 0 degrees
        bp2 = QPointF(0, 50)   # 90 degrees

        scene._tools._break_item(circle, bp1, bp2)

        assert circle not in scene._draw_circles
        assert len(scene._draw_arcs) == 1


# =========================================================================
# 4. GRIP HIT DETECTION
# =========================================================================


class TestFindGripHit:
    """SceneTools._find_grip_hit — nearest grip within tolerance."""

    def test_finds_nearest_grip_on_selected_line(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        line.setSelected(True)
        _flush()

        result = scene._tools._find_grip_hit(QPointF(1, 0))
        assert result is not None
        item, idx = result
        assert item is line
        assert idx == 0  # pt1 grip

    def test_finds_far_endpoint(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        line.setSelected(True)
        _flush()

        result = scene._tools._find_grip_hit(QPointF(99, 0))
        assert result is not None
        item, idx = result
        assert item is line
        assert idx == 2  # pt2 grip

    def test_finds_midpoint(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        line.setSelected(True)
        _flush()

        result = scene._tools._find_grip_hit(QPointF(50, 1))
        assert result is not None
        item, idx = result
        assert item is line
        assert idx == 1  # midpoint

    def test_returns_none_when_too_far(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        line.setSelected(True)
        _flush()

        # Way outside tolerance
        result = scene._tools._find_grip_hit(QPointF(500, 500))
        assert result is None

    def test_returns_none_when_not_selected(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        line.setSelected(False)
        _flush()

        result = scene._tools._find_grip_hit(QPointF(1, 0))
        assert result is None

    def test_circle_center_grip(self, scene):
        circle = CircleItem(QPointF(50, 50), 30)
        scene.addItem(circle)
        circle.setSelected(True)
        _flush()

        result = scene._tools._find_grip_hit(QPointF(50, 50))
        assert result is not None
        item, idx = result
        assert item is circle
        assert idx == 0  # center grip

    def test_rectangle_corner_grip(self, scene):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 100))
        scene.addItem(rect)
        rect.setSelected(True)
        _flush()

        # Near top-left corner (grip index 0)
        result = scene._tools._find_grip_hit(QPointF(1, 1))
        assert result is not None
        item, idx = result
        assert item is rect
        assert idx == 0


# =========================================================================
# 5. extract_edges
# =========================================================================


class TestExtractEdges:
    """extract_edges(item) — linear edge extraction."""

    def test_none_input(self):
        assert extract_edges(None) == []

    def test_line_item(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)
        edges = extract_edges(line)
        assert len(edges) == 1
        p1, p2 = edges[0]
        assert abs(p1.x() - 0.0) < 1e-3 or abs(p2.x() - 0.0) < 1e-3

    def test_polyline_item(self, scene):
        pl = PolylineItem(QPointF(0, 0))
        pl.append_point(QPointF(100, 0))
        pl.append_point(QPointF(100, 100))
        scene.addItem(pl)

        edges = extract_edges(pl)
        assert len(edges) == 2  # two segments

    def test_polyline_single_point(self, scene):
        pl = PolylineItem(QPointF(0, 0))
        scene.addItem(pl)
        edges = extract_edges(pl)
        assert edges == []


# =========================================================================
# 6. _get_item_segments
# =========================================================================


class TestGetItemSegments:
    """SceneTools._get_item_segments — geometric representation."""

    def test_line_item(self, scene):
        line = LineItem(QPointF(10, 20), QPointF(30, 40))
        scene.addItem(line)
        segs = scene._tools._get_item_segments(line)
        assert len(segs) == 1
        assert segs[0][0] == "line"

    def test_circle_item(self, scene):
        circle = CircleItem(QPointF(0, 0), 50)
        scene.addItem(circle)
        segs = scene._tools._get_item_segments(circle)
        assert len(segs) == 1
        assert segs[0][0] == "circle"
        assert abs(segs[0][2] - 50.0) < 1e-6

    def test_arc_item(self, scene):
        arc = ArcItem(QPointF(0, 0), 50.0, 45, 90)
        scene.addItem(arc)
        segs = scene._tools._get_item_segments(arc)
        assert len(segs) == 1
        assert segs[0][0] == "arc"
        assert abs(segs[0][3] - 45.0) < 1e-6
        assert abs(segs[0][4] - 90.0) < 1e-6

    def test_rectangle_item(self, scene):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 50))
        scene.addItem(rect)
        segs = scene._tools._get_item_segments(rect)
        assert len(segs) == 4  # four edges
        for seg in segs:
            assert seg[0] == "line"

    def test_polyline_item(self, scene):
        pl = PolylineItem(QPointF(0, 0))
        pl.append_point(QPointF(50, 0))
        pl.append_point(QPointF(50, 50))
        scene.addItem(pl)
        segs = scene._tools._get_item_segments(pl)
        assert len(segs) == 2
        for seg in segs:
            assert seg[0] == "line"


# =========================================================================
# 7. _compute_intersections (via _get_item_segments + geometry_intersect)
# =========================================================================


class TestComputeIntersections:
    """SceneTools._compute_intersections — intersection dispatch."""

    def test_two_crossing_lines(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 100))
        l2 = LineItem(QPointF(0, 100), QPointF(100, 0))
        scene.addItem(l1)
        scene.addItem(l2)
        scene._draw_lines.extend([l1, l2])

        pts = scene._tools._compute_intersections(l1, l2)
        assert len(pts) == 1
        assert abs(pts[0].x() - 50.0) < 1e-3
        assert abs(pts[0].y() - 50.0) < 1e-3

    def test_line_and_circle(self, scene):
        line = LineItem(QPointF(-100, 0), QPointF(100, 0))
        circle = CircleItem(QPointF(0, 0), 50)
        scene.addItem(line)
        scene.addItem(circle)
        scene._draw_lines.append(line)
        scene._draw_circles.append(circle)

        pts = scene._tools._compute_intersections(line, circle)
        assert len(pts) == 2

    def test_parallel_lines_no_intersection(self, scene):
        l1 = LineItem(QPointF(0, 0), QPointF(100, 0))
        l2 = LineItem(QPointF(0, 50), QPointF(100, 50))
        scene.addItem(l1)
        scene.addItem(l2)

        pts = scene._tools._compute_intersections(l1, l2)
        assert len(pts) == 0


# =========================================================================
# 8. geometry_intersect standalone functions (used by scene tools)
# =========================================================================


class TestPointOnSegmentParam:
    """gi.point_on_segment_param — parametric projection."""

    def test_midpoint(self):
        t = gi.point_on_segment_param(
            QPointF(50, 0), QPointF(0, 0), QPointF(100, 0))
        assert abs(t - 0.5) < 1e-6

    def test_start(self):
        t = gi.point_on_segment_param(
            QPointF(0, 0), QPointF(0, 0), QPointF(100, 0))
        assert abs(t) < 1e-6

    def test_end(self):
        t = gi.point_on_segment_param(
            QPointF(100, 0), QPointF(0, 0), QPointF(100, 0))
        assert abs(t - 1.0) < 1e-6

    def test_beyond_end(self):
        t = gi.point_on_segment_param(
            QPointF(200, 0), QPointF(0, 0), QPointF(100, 0))
        assert t > 1.0

    def test_before_start(self):
        t = gi.point_on_segment_param(
            QPointF(-50, 0), QPointF(0, 0), QPointF(100, 0))
        assert t < 0.0

    def test_degenerate_segment(self):
        t = gi.point_on_segment_param(
            QPointF(5, 5), QPointF(0, 0), QPointF(0, 0))
        assert t == 0.0


class TestNearestIntersection:
    """gi.nearest_intersection — closest point to click."""

    def test_empty_list(self):
        assert gi.nearest_intersection(QPointF(0, 0), []) is None

    def test_single_point(self):
        pts = [QPointF(10, 0)]
        result = gi.nearest_intersection(QPointF(0, 0), pts)
        assert abs(result.x() - 10.0) < 1e-6

    def test_picks_closest(self):
        pts = [QPointF(100, 0), QPointF(10, 0), QPointF(50, 0)]
        result = gi.nearest_intersection(QPointF(0, 0), pts)
        assert abs(result.x() - 10.0) < 1e-6


class TestLineLineIntersection:
    """gi.line_line_intersection — bounded segment intersection."""

    def test_crossing_segments(self):
        pt = gi.line_line_intersection(
            QPointF(0, 0), QPointF(10, 10),
            QPointF(10, 0), QPointF(0, 10))
        assert pt is not None
        assert abs(pt.x() - 5.0) < 1e-6
        assert abs(pt.y() - 5.0) < 1e-6

    def test_non_crossing_segments(self):
        pt = gi.line_line_intersection(
            QPointF(0, 0), QPointF(5, 0),
            QPointF(10, 10), QPointF(20, 10))
        assert pt is None

    def test_parallel_segments(self):
        pt = gi.line_line_intersection(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 5), QPointF(10, 5))
        assert pt is None


class TestLineLineIntersectionUnbounded:
    """gi.line_line_intersection_unbounded — infinite line intersection."""

    def test_perpendicular(self):
        pt = gi.line_line_intersection_unbounded(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(100, -5), QPointF(100, 5))
        assert pt is not None
        assert abs(pt.x() - 100.0) < 1e-6

    def test_parallel_returns_none(self):
        pt = gi.line_line_intersection_unbounded(
            QPointF(0, 0), QPointF(10, 0),
            QPointF(0, 5), QPointF(10, 5))
        assert pt is None


class TestLineCircleIntersections:
    """gi.line_circle_intersections — segment-circle."""

    def test_through_center(self):
        pts = gi.line_circle_intersections(
            QPointF(-100, 0), QPointF(100, 0),
            QPointF(0, 0), 50.0)
        assert len(pts) == 2
        xs = sorted(p.x() for p in pts)
        assert abs(xs[0] - (-50.0)) < 1e-3
        assert abs(xs[1] - 50.0) < 1e-3

    def test_tangent(self):
        pts = gi.line_circle_intersections(
            QPointF(-100, 50), QPointF(100, 50),
            QPointF(0, 0), 50.0)
        assert len(pts) == 1
        assert abs(pts[0].y() - 50.0) < 1e-3

    def test_miss(self):
        pts = gi.line_circle_intersections(
            QPointF(-100, 100), QPointF(100, 100),
            QPointF(0, 0), 50.0)
        assert len(pts) == 0


# =========================================================================
# 9. CAD_Math helpers (used extensively by scene tools)
# =========================================================================


class TestCADMathRotatePoint:
    """CAD_Math.rotate_point — point rotation around pivot."""

    def test_90_degrees(self):
        result = CAD_Math.rotate_point(
            QPointF(10, 0), QPointF(0, 0), 90)
        assert abs(result.x() - 0.0) < 1e-6
        assert abs(result.y() - 10.0) < 1e-6

    def test_180_degrees(self):
        result = CAD_Math.rotate_point(
            QPointF(10, 0), QPointF(0, 0), 180)
        assert abs(result.x() - (-10.0)) < 1e-6
        assert abs(result.y() - 0.0) < 1e-6

    def test_360_degrees_identity(self):
        result = CAD_Math.rotate_point(
            QPointF(10, 5), QPointF(0, 0), 360)
        assert abs(result.x() - 10.0) < 1e-6
        assert abs(result.y() - 5.0) < 1e-6

    def test_nonzero_pivot(self):
        result = CAD_Math.rotate_point(
            QPointF(20, 10), QPointF(10, 10), 90)
        assert abs(result.x() - 10.0) < 1e-6
        assert abs(result.y() - 20.0) < 1e-6


class TestCADMathMirrorPoint:
    """CAD_Math.mirror_point — reflection across axis."""

    def test_horizontal_axis(self):
        result = CAD_Math.mirror_point(
            QPointF(5, 10), QPointF(0, 0), QPointF(100, 0))
        assert abs(result.x() - 5.0) < 1e-6
        assert abs(result.y() - (-10.0)) < 1e-6

    def test_vertical_axis(self):
        result = CAD_Math.mirror_point(
            QPointF(10, 5), QPointF(0, 0), QPointF(0, 100))
        assert abs(result.x() - (-10.0)) < 1e-6
        assert abs(result.y() - 5.0) < 1e-6

    def test_point_on_axis(self):
        result = CAD_Math.mirror_point(
            QPointF(50, 0), QPointF(0, 0), QPointF(100, 0))
        assert abs(result.x() - 50.0) < 1e-6
        assert abs(result.y() - 0.0) < 1e-6


class TestCADMathScalePoint:
    """CAD_Math.scale_point — scaling relative to base."""

    def test_double(self):
        result = CAD_Math.scale_point(
            QPointF(10, 20), QPointF(0, 0), 2.0)
        assert abs(result.x() - 20.0) < 1e-6
        assert abs(result.y() - 40.0) < 1e-6

    def test_half(self):
        result = CAD_Math.scale_point(
            QPointF(10, 20), QPointF(0, 0), 0.5)
        assert abs(result.x() - 5.0) < 1e-6
        assert abs(result.y() - 10.0) < 1e-6

    def test_nonzero_base(self):
        result = CAD_Math.scale_point(
            QPointF(20, 10), QPointF(10, 10), 3.0)
        assert abs(result.x() - 40.0) < 1e-6
        assert abs(result.y() - 10.0) < 1e-6


class TestCADMathPointOnLineNearest:
    """CAD_Math.point_on_line_nearest — perpendicular projection."""

    def test_horizontal_line(self):
        result = CAD_Math.point_on_line_nearest(
            QPointF(50, 30), QPointF(0, 0), QPointF(100, 0))
        assert abs(result.x() - 50.0) < 1e-6
        assert abs(result.y() - 0.0) < 1e-6

    def test_vertical_line(self):
        result = CAD_Math.point_on_line_nearest(
            QPointF(30, 50), QPointF(0, 0), QPointF(0, 100))
        assert abs(result.x() - 0.0) < 1e-6
        assert abs(result.y() - 50.0) < 1e-6

    def test_degenerate_line(self):
        result = CAD_Math.point_on_line_nearest(
            QPointF(30, 50), QPointF(0, 0), QPointF(0, 0))
        assert abs(result.x() - 0.0) < 1e-6
        assert abs(result.y() - 0.0) < 1e-6


# =========================================================================
# 10. Construction geometry grip protocol
# =========================================================================


class TestConstructionGeometryGrips:
    """Grip protocol on construction geometry items used by scene tools."""

    def test_line_grip_points(self):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        grips = line.grip_points()
        assert len(grips) == 3  # pt1, mid, pt2
        assert abs(grips[0].x()) < 1e-6
        assert abs(grips[1].x() - 50.0) < 1e-6
        assert abs(grips[2].x() - 100.0) < 1e-6

    def test_line_apply_grip_endpoint(self):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        line.apply_grip(2, QPointF(200, 0))
        assert abs(line._pt2.x() - 200.0) < 1e-6

    def test_line_apply_grip_midpoint_translates(self):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        line.apply_grip(1, QPointF(60, 10))
        # Midpoint was (50,0), moved to (60,10) => delta (10,10)
        assert abs(line._pt1.x() - 10.0) < 1e-6
        assert abs(line._pt1.y() - 10.0) < 1e-6
        assert abs(line._pt2.x() - 110.0) < 1e-6

    def test_circle_grip_points(self):
        circle = CircleItem(QPointF(0, 0), 50)
        grips = circle.grip_points()
        assert len(grips) == 5  # center + 4 cardinal
        assert abs(grips[0].x()) < 1e-6  # center
        assert abs(grips[1].x() - 50.0) < 1e-6  # right

    def test_circle_apply_grip_resize(self):
        circle = CircleItem(QPointF(0, 0), 50)
        circle.apply_grip(1, QPointF(80, 0))
        assert abs(circle._radius - 80.0) < 1e-3

    def test_rectangle_grip_points(self):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 50))
        grips = rect.grip_points()
        assert len(grips) == 9

    def test_polyline_grip_points(self):
        pl = PolylineItem(QPointF(0, 0))
        pl.append_point(QPointF(50, 0))
        pl.append_point(QPointF(50, 50))
        grips = pl.grip_points()
        assert len(grips) == 3

    def test_arc_grip_points(self):
        arc = ArcItem(QPointF(0, 0), 50.0, 0, 90)
        grips = arc.grip_points()
        assert len(grips) == 3  # center, start, end


# =========================================================================
# 11. _make_offset_item
# =========================================================================


class TestMakeOffsetItem:
    """SceneTools._make_offset_item — produces offset copies."""

    def test_line_offset(self, scene):
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line)

        result = scene._tools._make_offset_item(line, 10.0)
        assert result is not None
        assert isinstance(result, LineItem)

    def test_polyline_offset(self, scene):
        pl = PolylineItem(QPointF(0, 0))
        pl.append_point(QPointF(100, 0))
        scene.addItem(pl)

        result = scene._tools._make_offset_item(pl, 10.0)
        assert result is not None
        assert isinstance(result, PolylineItem)

    def test_circle_offset_grow(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)

        # _make_offset_item uses boundingRect().width()/2 as radius (includes pen)
        r_eff = circle.boundingRect().width() / 2
        result = scene._tools._make_offset_item(circle, 10.0)
        assert result is not None
        assert isinstance(result, CircleItem)
        assert abs(result._radius - (r_eff + 10.0)) < 1e-3

    def test_circle_offset_shrink(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)

        r_eff = circle.boundingRect().width() / 2
        result = scene._tools._make_offset_item(circle, -20.0)
        assert result is not None
        assert abs(result._radius - (r_eff - 20.0)) < 1e-3

    def test_circle_offset_shrink_to_nothing(self, scene):
        circle = CircleItem(QPointF(0, 0), 50.0)
        scene.addItem(circle)

        r_eff = circle.boundingRect().width() / 2
        # Offset inward by more than the effective radius => None
        result = scene._tools._make_offset_item(circle, -(r_eff + 10.0))
        assert result is None  # negative radius not allowed

    def test_rectangle_offset(self, scene):
        rect = RectangleItem(QPointF(0, 0), QPointF(100, 50))
        scene.addItem(rect)

        result = scene._tools._make_offset_item(rect, 10.0)
        assert result is not None
        assert isinstance(result, RectangleItem)
        r = result.rect()
        assert abs(r.width() - 120.0) < 1e-3
        assert abs(r.height() - 70.0) < 1e-3

    def test_arc_offset(self, scene):
        arc = ArcItem(QPointF(0, 0), 50.0, 0, 180)
        scene.addItem(arc)

        result = scene._tools._make_offset_item(arc, 10.0)
        assert result is not None
        assert isinstance(result, ArcItem)
        assert abs(result._radius - 60.0) < 1e-3
        assert abs(result._span_deg - 180.0) < 1e-3
