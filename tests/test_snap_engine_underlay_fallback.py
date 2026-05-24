"""Regression tests for snap engine underlay fallback.

The lazy-snap refactor (60f17a5) changed Phase 1 and Phase 4 to query
UnderlaySnapIndex via group.data(4).  Groups without data(4) — like
the import dialog preview — must fall back to processing invisible
child items directly.

See: docs/superpowers/plans/2026-05-23-snap-engine-fallback-for-import-dialog.md
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QLineF, QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QTransform
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
)

from firepro3d.snap_engine import SnapEngine
from firepro3d.underlay_snap_index import UnderlaySnapIndex

from PyQt6.QtCore import Qt


# ── Helpers ──────────────────────────────────────────────────────────────────

ABS_TOL = 2.0  # point comparison tolerance (scene units)
OFFSET = 5.0   # cursor offset from expected snap point


def _engine() -> SnapEngine:
    """Create a SnapEngine with all snaps on."""
    return SnapEngine()


def _scene() -> QGraphicsScene:
    """Minimal scene with required attributes."""
    s = QGraphicsScene()
    s._walls = []
    s._gridlines = []
    return s


def _find(engine: SnapEngine, scene: QGraphicsScene,
          cursor: QPointF):
    """Run find() with identity transform (scale=1, tol=40 scene units)."""
    return engine.find(cursor, scene, QTransform())


def _invisible_pen() -> QPen:
    """Transparent cosmetic pen matching the import dialog's _create_snap_item."""
    pen = QPen(QColor(0, 0, 0, 0), 0)
    pen.setCosmetic(True)
    return pen


def _make_underlay_group_with_items(
    scene: QGraphicsScene,
) -> QGraphicsItemGroup:
    """Create an underlay group with invisible child items (import dialog style).

    Geometry: a horizontal line from (0,0) to (200,0).
    No UnderlaySnapIndex — mimics the import dialog preview.
    """
    group = QGraphicsItemGroup()
    group.setData(0, "DXF Underlay")
    scene.addItem(group)

    # Invisible line item (same pattern as dxf_preview_dialog._create_snap_item)
    line = QGraphicsLineItem(0, 0, 200, 0)
    line.setPen(_invisible_pen())
    scene.addItem(line)
    group.addToGroup(line)

    return group


def _make_underlay_group_with_index(
    scene: QGraphicsScene,
) -> QGraphicsItemGroup:
    """Create an underlay group with a UnderlaySnapIndex (main scene style).

    Same geometry as the item-based group: a horizontal line from (0,0) to (200,0).
    Has UnderlaySnapIndex on data(4) — mimics the main scene.
    """
    group = QGraphicsItemGroup()
    group.setData(0, "DXF Underlay")
    scene.addItem(group)

    # Batched render path (visible but no snap contribution from the item)
    path = QPainterPath()
    path.moveTo(0, 0)
    path.lineTo(200, 0)
    batched = QGraphicsPathItem(path)
    scene.addItem(batched)
    group.addToGroup(batched)

    # Snap index with the same geometry
    geom_list = [{"kind": "line", "x1": 0, "y1": 0, "x2": 200, "y2": 0,
                  "layer": "0"}]
    index = UnderlaySnapIndex(geom_list, [])
    group.setData(4, index)

    return group


# ── Phase 1 tests ────────────────────────────────────────────────────────────

class TestPhase1NoIndex:
    """Phase 1 fallback: invisible child items (import dialog path)."""

    def test_endpoint_at_line_start(self, qapp):
        scene = _scene()
        _make_underlay_group_with_items(scene)
        engine = _engine()

        result = _find(engine, scene, QPointF(OFFSET, 0))
        assert result is not None
        assert result.snap_type == "endpoint"
        assert abs(result.point.x() - 0) < ABS_TOL
        assert abs(result.point.y() - 0) < ABS_TOL

    def test_endpoint_at_line_end(self, qapp):
        scene = _scene()
        _make_underlay_group_with_items(scene)
        engine = _engine()

        result = _find(engine, scene, QPointF(200 - OFFSET, 0))
        assert result is not None
        assert result.snap_type == "endpoint"
        assert abs(result.point.x() - 200) < ABS_TOL
        assert abs(result.point.y() - 0) < ABS_TOL

    def test_midpoint(self, qapp):
        scene = _scene()
        _make_underlay_group_with_items(scene)
        engine = _engine()

        result = _find(engine, scene, QPointF(100, OFFSET))
        assert result is not None
        assert result.snap_type == "midpoint"
        assert abs(result.point.x() - 100) < ABS_TOL
        assert abs(result.point.y() - 0) < ABS_TOL

    def test_perpendicular(self, qapp):
        scene = _scene()
        _make_underlay_group_with_items(scene)
        engine = _engine()

        # Cursor above the line at x=50 — perpendicular foot is (50, 0)
        result = _find(engine, scene, QPointF(50, 30))
        assert result is not None
        assert result.snap_type == "perpendicular"
        assert abs(result.point.x() - 50) < ABS_TOL
        assert abs(result.point.y() - 0) < ABS_TOL


class TestPhase1WithIndex:
    """Phase 1 with UnderlaySnapIndex (main scene path)."""

    def test_endpoint_at_line_start(self, qapp):
        scene = _scene()
        _make_underlay_group_with_index(scene)
        engine = _engine()

        result = _find(engine, scene, QPointF(OFFSET, 0))
        assert result is not None
        assert result.snap_type == "endpoint"
        assert abs(result.point.x() - 0) < ABS_TOL
        assert abs(result.point.y() - 0) < ABS_TOL

    def test_midpoint(self, qapp):
        scene = _scene()
        _make_underlay_group_with_index(scene)
        engine = _engine()

        result = _find(engine, scene, QPointF(100, OFFSET))
        assert result is not None
        assert result.snap_type == "midpoint"
        assert abs(result.point.x() - 100) < ABS_TOL
        assert abs(result.point.y() - 0) < ABS_TOL


# ── Phase 4 tests ────────────────────────────────────────────────────────────

class TestPhase4NoIndex:
    """Phase 4 intersection: invisible child items contribute segments."""

    def test_intersection_with_crossing_line(self, qapp):
        scene = _scene()
        _make_underlay_group_with_items(scene)
        engine = _engine()

        # Add a vertical line crossing at (100, 0)
        crossing = QGraphicsLineItem(QLineF(
            QPointF(100, -50), QPointF(100, 50)))
        scene.addItem(crossing)

        result = _find(engine, scene, QPointF(100 + OFFSET, OFFSET))
        assert result is not None
        assert result.snap_type == "intersection"
        assert abs(result.point.x() - 100) < ABS_TOL
        assert abs(result.point.y() - 0) < ABS_TOL


class TestPhase4WithIndex:
    """Phase 4 intersection: snap index contributes segments."""

    def test_intersection_with_crossing_line(self, qapp):
        scene = _scene()
        _make_underlay_group_with_index(scene)
        engine = _engine()

        # Add a vertical line crossing at (100, 0)
        crossing = QGraphicsLineItem(QLineF(
            QPointF(100, -50), QPointF(100, 50)))
        scene.addItem(crossing)

        result = _find(engine, scene, QPointF(100 + OFFSET, OFFSET))
        assert result is not None
        assert result.snap_type == "intersection"
        assert abs(result.point.x() - 100) < ABS_TOL
        assert abs(result.point.y() - 0) < ABS_TOL
