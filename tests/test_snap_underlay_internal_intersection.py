"""Regression: intersection snapping between two geometries WITHIN one placed
underlay (main-scene UnderlaySnapIndex path).

Every segment extracted from an underlay snap index used to be tagged with the
underlay *group* as its source, so phase-4's same-parent suppression
(`src1 is src2`, built to drop wall-internal face crossings) silently dropped
EVERY crossing between two imported lines — underlay intersection snapping
never worked in the main scene, at any tolerance. Phase 4 now compares a
*per-geometry* parent key, so two distinct underlay entities produce an
intersection while one polyline's own consecutive segments stay suppressed.

See docs/specs/snapping-engine.md §6.1 / §6.3.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QTransform
from PyQt6.QtWidgets import (
    QGraphicsItemGroup, QGraphicsPathItem, QGraphicsScene,
)

from firepro3d.snap_engine import SnapEngine
from firepro3d.underlay_snap_index import UnderlaySnapIndex


def _scene() -> QGraphicsScene:
    s = QGraphicsScene()
    s._walls = []
    s._gridlines = []
    return s


def _indexed_underlay(scene: QGraphicsScene, geom: list[dict]):
    """Underlay group with a snap index (main-scene path).

    A batched render-path child gives the empty group a bounding rect so
    ``scene.items(search_rect)`` returns it; it contributes no snaps itself.
    """
    grp = QGraphicsItemGroup()
    grp.setData(0, "DXF Underlay")
    scene.addItem(grp)

    path = QPainterPath()
    for g in geom:
        if g["kind"] == "line":
            path.moveTo(g["x1"], g["y1"])
            path.lineTo(g["x2"], g["y2"])
        else:  # path_points
            pts = g["points"]
            path.moveTo(*pts[0])
            for p in pts[1:]:
                path.lineTo(*p)
    batched = QGraphicsPathItem(path)
    scene.addItem(batched)
    grp.addToGroup(batched)

    grp.setData(4, UnderlaySnapIndex(list(geom), []))
    return grp


def test_two_underlay_lines_crossing_snaps_intersection(qapp):
    """Two distinct line entities crossing at (100, 0) → intersection.

    Cursor (104, 1) is offset *along* the horizontal line: the perpendicular
    foot is (104, 0) at distance 1, closer than the intersection at (100, 0)
    (d ~= 4.12). Before the fix the crossing was suppressed and the picker
    returned perpendicular; now intersection (priority 0) wins.
    """
    scene = _scene()
    _indexed_underlay(scene, [
        {"kind": "line", "x1": 0, "y1": 0, "x2": 300, "y2": 0, "layer": "0"},
        {"kind": "line", "x1": 100, "y1": -60, "x2": 100, "y2": 140,
         "layer": "0"},
    ])
    result = SnapEngine().find(QPointF(104, 1), scene, QTransform())
    assert result is not None, "expected a snap near the crossing"
    assert result.snap_type == "intersection", (
        f"expected intersection, got {result.snap_type} "
        f"at ({result.point.x():.1f}, {result.point.y():.1f})")
    assert abs(result.point.x() - 100.0) < 1.5
    assert abs(result.point.y() - 0.0) < 1.5


def test_self_crossing_polyline_snaps_intersection(qapp):
    """A single underlay polyline whose path crosses itself must still snap at
    the crossing — the DXF's entity grouping is invisible to the user.

    Polyline (0,0)->(120,120)->(120,0)->(0,90): segment 0 (y=x) and segment 2
    cross at (~51.4, ~51.4), which is not a vertex or midpoint of either.
    """
    scene = _scene()
    _indexed_underlay(scene, [
        {"kind": "path_points",
         "points": [(0.0, 0.0), (120.0, 120.0), (120.0, 0.0), (0.0, 90.0)],
         "layer": "0"},
    ])
    result = SnapEngine().find(QPointF(53, 51), scene, QTransform())
    assert result is not None, "expected a snap near the self-crossing"
    assert result.snap_type == "intersection", (
        f"expected intersection, got {result.snap_type} "
        f"at ({result.point.x():.1f}, {result.point.y():.1f})")
    assert abs(result.point.x() - 51.4) < 2.0
    assert abs(result.point.y() - 51.4) < 2.0


def test_polyline_vertex_snaps_endpoint_not_spurious_intersection(qapp):
    """Guard: removing same-parent suppression for underlays must NOT turn a
    polyline's own vertex into a spurious intersection — the endpoint
    protection band keeps the vertex an endpoint snap."""
    scene = _scene()
    _indexed_underlay(scene, [
        {"kind": "path_points",
         "points": [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)],
         "layer": "0"},
    ])
    # Cursor near the corner vertex (100, 0).
    result = SnapEngine().find(QPointF(96, 4), scene, QTransform())
    assert result is not None
    assert result.snap_type == "endpoint", (
        f"expected endpoint at the vertex, got {result.snap_type} "
        f"at ({result.point.x():.1f}, {result.point.y():.1f})")
    assert abs(result.point.x() - 100.0) < 1.5
    assert abs(result.point.y() - 0.0) < 1.5


def test_underlay_line_crossing_polyline_snaps_intersection(qapp):
    """A line entity crossing a separate polyline entity → intersection."""
    scene = _scene()
    _indexed_underlay(scene, [
        {"kind": "line", "x1": 0, "y1": 0, "x2": 300, "y2": 0, "layer": "0"},
        {"kind": "path_points", "points": [(100.0, -60.0), (100.0, 140.0)],
         "layer": "0"},
    ])
    result = SnapEngine().find(QPointF(104, 1), scene, QTransform())
    assert result is not None, "expected a snap near the crossing"
    assert result.snap_type == "intersection", (
        f"expected intersection, got {result.snap_type} "
        f"at ({result.point.x():.1f}, {result.point.y():.1f})")
    assert abs(result.point.x() - 100.0) < 1.5
    assert abs(result.point.y() - 0.0) < 1.5
