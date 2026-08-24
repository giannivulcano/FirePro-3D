"""Snap-engine integration tests for RegularPolygonItem.

Covers:
- vertex (endpoint) snaps
- edge midpoint (midpoint) snaps
- center snaps
- polygon edges as intersection-segment candidates (phase 4)

The SnapEngine is constructed directly (not via Model_Space) so we exercise
the _collect() / _phase4_items() paths without MainWindow overhead.

Uses the ``qapp`` session fixture from conftest.py (no pytest-qt).
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from firepro3d.construction_geometry import RegularPolygonItem
from firepro3d.snap_engine import SnapEngine


# ── Helpers ──────────────────────────────────────────────────────────────────

def _engine() -> SnapEngine:
    """SnapEngine with all snap types enabled."""
    eng = SnapEngine()
    eng.snap_endpoint     = True
    eng.snap_midpoint     = True
    eng.snap_center       = True
    eng.snap_intersection = True
    return eng


def _scene_with_polygon(**kwargs) -> tuple[QGraphicsScene, RegularPolygonItem]:
    """Minimal scene containing one RegularPolygonItem.

    Keyword args forwarded to RegularPolygonItem (center, sides,
    radius_mm, rotation_deg, inscribed).  Defaults: square inscribed
    in radius=100 at origin, rotation=0.
    """
    s = QGraphicsScene()
    # Attributes used by SnapEngine._check_scene_items / _phase4_items guards
    s._walls = []
    s._gridlines = []

    kwargs.setdefault("center", QPointF(0, 0))
    kwargs.setdefault("sides", 4)
    kwargs.setdefault("radius_mm", 100.0)
    kwargs.setdefault("rotation_deg", 0.0)
    kwargs.setdefault("inscribed", True)

    poly = RegularPolygonItem(**kwargs)
    s.addItem(poly)
    return s, poly


def _find(eng: SnapEngine, scene: QGraphicsScene,
          cursor: QPointF):
    """Run find() with identity transform (tolerance = 40 scene units)."""
    return eng.find(cursor, scene, QTransform())


# ── Geometry: inscribed square (sides=4, radius=100, rotation=0) ─────────────
#
#   vertices:   (100, 0), (0, 100), (-100, 0), (0, -100)
#     [Qt Y-down: sin(90°)=+1 → y=+100]
#   edge mids:  midpoint of each consecutive pair
#     (100,0)↔(0,100) → (50,50)
#     (0,100)↔(-100,0) → (-50,50)
#     (-100,0)↔(0,-100) → (-50,-50)
#     (0,-100)↔(100,0) → (50,-50)
#   center: (0, 0)


class TestPolygonVertexSnap:
    """Vertex → endpoint snap."""

    def test_snap_to_right_vertex(self, qapp):
        scene, _ = _scene_with_polygon()
        eng = _engine()
        # cursor near (100, 0), within 40-unit tolerance
        hit = _find(eng, scene, QPointF(99, 1))
        assert hit is not None, "expected endpoint snap near (100, 0)"
        assert hit.snap_type == "endpoint"
        assert math.isclose(hit.point.x(), 100.0, abs_tol=1.0)
        assert math.isclose(hit.point.y(), 0.0, abs_tol=1.0)

    def test_snap_to_bottom_vertex(self, qapp):
        scene, _ = _scene_with_polygon()
        eng = _engine()
        # cursor near (0, 100)
        hit = _find(eng, scene, QPointF(1, 99))
        assert hit is not None, "expected endpoint snap near (0, 100)"
        assert hit.snap_type == "endpoint"
        assert math.isclose(hit.point.x(), 0.0, abs_tol=1.0)
        assert math.isclose(hit.point.y(), 100.0, abs_tol=1.0)

    def test_no_endpoint_when_toggle_off(self, qapp):
        scene, _ = _scene_with_polygon()
        eng = _engine()
        eng.snap_endpoint = False
        eng.snap_midpoint = False
        eng.snap_center   = False
        eng.snap_nearest  = False
        eng.snap_intersection = False
        eng.snap_perpendicular = False
        eng.snap_tangent = False
        eng.snap_quadrant = False
        hit = _find(eng, scene, QPointF(99, 1))
        # With all snaps off there must be no result at all
        assert hit is None, f"expected no snap with all toggles off, got {hit}"


class TestPolygonCenterSnap:
    """Centre → center snap."""

    def test_center_at_origin(self, qapp):
        scene, _ = _scene_with_polygon()
        eng = _engine()
        hit = _find(eng, scene, QPointF(1, 1))
        assert hit is not None, "expected center snap near origin"
        assert hit.snap_type == "center"
        assert math.isclose(hit.point.x(), 0.0, abs_tol=1.0)
        assert math.isclose(hit.point.y(), 0.0, abs_tol=1.0)

    def test_center_non_origin(self, qapp):
        """Center at a non-origin position."""
        scene, _ = _scene_with_polygon(center=QPointF(200, 300), sides=6,
                                       radius_mm=50.0)
        eng = _engine()
        hit = _find(eng, scene, QPointF(201, 299))
        assert hit is not None, "expected center snap near (200, 300)"
        assert hit.snap_type == "center"
        assert math.isclose(hit.point.x(), 200.0, abs_tol=1.0)
        assert math.isclose(hit.point.y(), 300.0, abs_tol=1.0)

    def test_no_center_when_toggle_off(self, qapp):
        scene, _ = _scene_with_polygon()
        eng = _engine()
        eng.snap_center = False
        hit = _find(eng, scene, QPointF(1, 1))
        # If we get a hit it must not be center type
        if hit is not None:
            assert hit.snap_type != "center"


class TestPolygonEdgeMidpointSnap:
    """Edge midpoints → midpoint snap."""

    def test_midpoint_first_edge(self, qapp):
        """Midpoint of edge (100,0)→(0,100) is (50,50)."""
        scene, _ = _scene_with_polygon()
        eng = _engine()
        hit = _find(eng, scene, QPointF(49, 51))
        assert hit is not None, "expected midpoint snap near (50, 50)"
        assert hit.snap_type == "midpoint"
        assert math.isclose(hit.point.x(), 50.0, abs_tol=1.0)
        assert math.isclose(hit.point.y(), 50.0, abs_tol=1.0)

    def test_midpoint_third_edge(self, qapp):
        """Midpoint of edge (-100,0)→(0,-100) is (-50,-50)."""
        scene, _ = _scene_with_polygon()
        eng = _engine()
        hit = _find(eng, scene, QPointF(-49, -51))
        assert hit is not None, "expected midpoint snap near (-50, -50)"
        assert hit.snap_type == "midpoint"
        assert math.isclose(hit.point.x(), -50.0, abs_tol=1.0)
        assert math.isclose(hit.point.y(), -50.0, abs_tol=1.0)

    def test_no_midpoint_when_toggle_off(self, qapp):
        scene, _ = _scene_with_polygon()
        eng = _engine()
        eng.snap_midpoint = False
        hit = _find(eng, scene, QPointF(49, 51))
        if hit is not None:
            assert hit.snap_type != "midpoint"


class TestPolygonPhase4Intersection:
    """Phase-4: polygon edges are registered as intersection segments."""

    def test_vertical_line_intersects_polygon_edge(self, qapp):
        """A vertical line crossing the right edge (100,0)→(0,100) should
        produce an intersection snap near that crossing point.

        Edge eqn: x + y = 100.  Vertical x=80 → crossing at (80, 20).
        """
        scene, _ = _scene_with_polygon()
        eng = _engine()

        # Add a vertical line crossing the right edge of the square
        vline = QGraphicsLineItem(
            QLineF(QPointF(80, -200), QPointF(80, 200)))
        scene.addItem(vline)

        # Cursor near the crossing point (80, 20)
        hit = _find(eng, scene, QPointF(80, 20))
        assert hit is not None, (
            "expected intersection snap at polygon edge × vertical line")
        assert hit.snap_type == "intersection"
        assert math.isclose(hit.point.x(), 80.0, abs_tol=2.0)
        assert math.isclose(hit.point.y(), 20.0, abs_tol=2.0)


class TestPolygonSnapVariants:
    """Additional coverage: different polygon configurations."""

    def test_hexagon_center_snap(self, qapp):
        """6-sided polygon at a non-origin center."""
        scene, poly = _scene_with_polygon(
            center=QPointF(500, 500), sides=6,
            radius_mm=80.0, rotation_deg=0.0, inscribed=True)
        eng = _engine()
        hit = _find(eng, scene, QPointF(502, 498))
        assert hit is not None
        assert hit.snap_type == "center"
        assert math.isclose(hit.point.x(), 500.0, abs_tol=2.0)
        assert math.isclose(hit.point.y(), 500.0, abs_tol=2.0)

    def test_hexagon_vertex_snap(self, qapp):
        """6-sided polygon: vertex at (cx+r, cy) when rotation=0, inscribed."""
        # rotation=0, inscribed → first vertex at angle=0 → (500+80, 500) = (580, 500)
        scene, _ = _scene_with_polygon(
            center=QPointF(500, 500), sides=6,
            radius_mm=80.0, rotation_deg=0.0, inscribed=True)
        eng = _engine()
        hit = _find(eng, scene, QPointF(579, 501))
        assert hit is not None
        assert hit.snap_type == "endpoint"
        assert math.isclose(hit.point.x(), 580.0, abs_tol=2.0)
        assert math.isclose(hit.point.y(), 500.0, abs_tol=2.0)


class TestPolygonClosingEdge:
    """Closing (last→first) edge: midpoint snap and nearest snap coverage."""

    def test_closing_edge_midpoint(self, qapp):
        """Midpoint of the closing edge (0,-100)→(100,0) is (50,-50).

        Vertices: (100,0),(0,100),(-100,0),(0,-100).
        Closing edge: verts[3]→verts[0] = (0,-100)→(100,0).
        Midpoint: (50, -50).
        """
        scene, _ = _scene_with_polygon()
        eng = _engine()
        hit = _find(eng, scene, QPointF(49, -51))
        assert hit is not None, "expected midpoint snap near (50, -50)"
        assert hit.snap_type == "midpoint"
        assert math.isclose(hit.point.x(), 50.0, abs_tol=1.0)
        assert math.isclose(hit.point.y(), -50.0, abs_tol=1.0)

    def test_nearest_snap_on_edge_via_geometric_snaps(self, qapp):
        """_geometric_snaps must project the cursor onto each polygon edge,
        including the closing edge, and emit a 'nearest' candidate.

        Cursor at (75, 15) — off all vertices/midpoints of the first edge
        (100,0)→(0,100).  Expected foot:
          t = ((75-100)*(-100) + (15-0)*(100)) / (100²+100²) = 0.2
          foot = (80.0, 20.0)

        We call _geometric_snaps directly (not find()) to avoid priority
        competition suppressing the nearest result.
        """
        _, poly = _scene_with_polygon()
        eng = SnapEngine()
        eng.snap_nearest = True
        eng.snap_perpendicular = False
        eng.snap_endpoint = False
        eng.snap_midpoint = False
        eng.snap_center = False
        eng.snap_intersection = False

        results = eng._geometric_snaps(QPointF(75, 15), poly)
        nearest_pts = [pt for snap_type, pt in results if snap_type == "nearest"]
        assert nearest_pts, (
            "expected at least one 'nearest' candidate from _geometric_snaps "
            "on RegularPolygonItem; got zero — check that the RegularPolygonItem "
            "branch was added before the generic QGraphicsPathItem branch"
        )
        # The nearest point on the first edge (100,0)→(0,100) to cursor (75,15)
        # should be approximately (80.0, 20.0)
        foot = nearest_pts[0]
        assert math.isclose(foot.x(), 80.0, abs_tol=1.0), (
            f"expected foot.x ≈ 80.0, got {foot.x():.3f}"
        )
        assert math.isclose(foot.y(), 20.0, abs_tol=1.0), (
            f"expected foot.y ≈ 20.0, got {foot.y():.3f}"
        )
