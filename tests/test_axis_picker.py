"""DD2 axis picker: the nearest visible STRAIGHT segment within tolerance.

Governing: docs/superpowers/specs/2026-10-01-scene-tools-p1-batch-design.md
DD2 (folded into snapping-engine.md / scene-tools.md at Account). Real
Model_Space scenes and real items; the asserted ground truth is the picked
segment's scene endpoints and its source item.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsItemGroup, QGraphicsPathItem

from firepro3d.axis_picker import pick_axis
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RectangleItem,
                                   ReferenceLineItem, RegularPolygonItem,
                                   SplineItem)
from firepro3d.gridline import GridlineItem
from firepro3d.underlay_snap_index import UnderlaySnapIndex
from firepro3d.wall import WallSegment

TOL = 10.0


@pytest.fixture
def editor(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space(scene_role="block_editor")
    yield s
    s.cleanup()


@pytest.fixture
def plan(qapp):
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    yield s
    s.cleanup()


def _add(scene, item, attr):
    scene.addItem(item)
    getattr(scene, attr).append(item)
    return item


def _ends(pick):
    return {(round(pick.p1.x(), 2), round(pick.p1.y(), 2)),
            (round(pick.p2.x(), 2), round(pick.p2.y(), 2))}


def _closed_poly():
    pl = PolylineItem(QPointF(300, 0))
    pl.append_point(QPointF(400, 0))
    pl.append_point(QPointF(400, -100))
    pl.close()
    return pl


STRAIGHT = {
    "line": (lambda: LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines",
             QPointF(50, 3), {(0.0, 0.0), (100.0, 0.0)}),
    "refline": (lambda: ReferenceLineItem(QPointF(0, 0), QPointF(100, 0)),
                "_reference_lines", QPointF(50, -3), {(0.0, 0.0), (100.0, 0.0)}),
    "rect_edge": (lambda: RectangleItem(QPointF(600, 0), QPointF(700, -50)),
                  "_draw_rects", QPointF(650, -48), {(600.0, -50.0), (700.0, -50.0)}),
    # The generator walks a polyline's vertex chain only; the closing edge of a
    # CLOSED polyline is still an edge (DD2: the selection's own edges count).
    "closed_poly_closing_edge": (_closed_poly, "_polylines", QPointF(350, -50),
                                 {(400.0, -100.0), (300.0, 0.0)}),
    "polygon_edge": (lambda: RegularPolygonItem(QPointF(0, 0), sides=4,
                                                radius_mm=100.0, rotation_deg=45.0),
                     "_draw_polygons", QPointF(0, -68),
                     {(70.71, -70.71), (-70.71, -70.71)}),
}


@pytest.mark.parametrize("name", list(STRAIGHT))
def test_picks_the_straight_segment_under_the_cursor(editor, name):
    factory, attr, cursor, ends = STRAIGHT[name]
    item = _add(editor, factory(), attr)
    pick = pick_axis(editor, cursor, TOL)
    assert pick is not None and pick.source is item                  # [RED]
    assert _ends(pick) == ends


CURVES = {
    "arc_top": (lambda: ArcItem(QPointF(0, -300), 100.0, 0.0, 180.0), "_draw_arcs",
                QPointF(0, -398)),
    "arc_centre_chord": (lambda: ArcItem(QPointF(0, -300), 100.0, 0.0, 180.0),
                         "_draw_arcs", QPointF(0, -300)),
    "circle": (lambda: CircleItem(QPointF(0, 0), 50.0), "_draw_circles",
               QPointF(50, 2)),
    "ellipse": (lambda: EllipseItem(QPointF(0, 0), 80.0, 40.0), "_draw_ellipses",
                QPointF(0, -38)),
    "spline": (lambda: SplineItem([QPointF(0, 300), QPointF(50, 240),
                                   QPointF(100, 300)]), "_draw_splines",
               QPointF(50, 270)),
}


@pytest.mark.parametrize("name", list(CURVES))
def test_curves_are_never_an_axis(editor, name):
    factory, attr, cursor = CURVES[name]
    _add(editor, factory(), attr)
    assert pick_axis(editor, cursor, TOL) is None                    # [RED]


def test_hidden_items_are_skipped(editor):
    ln = _add(editor, LineItem(QPointF(0, 600), QPointF(100, 600)), "_draw_lines")
    ln.setVisible(False)
    assert pick_axis(editor, QPointF(50, 600), TOL) is None


def test_exclude_and_empty_space(editor):
    ln = _add(editor, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    assert pick_axis(editor, QPointF(50, 3), TOL, exclude=[ln]) is None
    assert pick_axis(editor, QPointF(5000, 5000), TOL) is None


def test_nearest_segment_wins(editor):
    _add(editor, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    nearer = _add(editor, LineItem(QPointF(0, 6), QPointF(100, 6)), "_draw_lines")
    pick = pick_axis(editor, QPointF(50, 4), TOL)          # 4 mm vs 2 mm away
    assert pick.source is nearer


def test_axis_heading_is_y_up(editor):
    """A segment drawn visually upward reads 90° (scene Y is down)."""
    _add(editor, LineItem(QPointF(0, 0), QPointF(0, -100)), "_draw_lines")
    pick = pick_axis(editor, QPointF(2, -50), TOL)
    assert pick.angle_deg == pytest.approx(90.0)


def test_gridline_and_wall_face_are_axes(plan):
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 500), "A")
    plan._register_gridline(gl)
    pick = pick_axis(plan, QPointF(4, 250), TOL)
    assert pick is not None and pick.source is gl
    w = WallSegment(QPointF(1000, 0), QPointF(2000, 0), thickness_mm=200.0)
    plan.addItem(w)
    plan._walls.append(w)
    pick = pick_axis(plan, QPointF(1500, 98), TOL)
    assert pick is not None and pick.source is w
    assert _ends(pick) == {(1000.0, 100.0), (2000.0, 100.0)}


def _underlay_group(scene, path, index=None):
    grp = QGraphicsItemGroup()
    grp.setData(0, "DXF Underlay")
    scene.addItem(grp)
    child = QGraphicsPathItem(path)
    scene.addItem(child)
    grp.addToGroup(child)
    if index is not None:
        grp.setData(4, index)
    return grp, child


def test_indexed_underlay_segment_is_an_axis(plan):
    path = QPainterPath()
    path.moveTo(3000, 0)
    path.lineTo(3100, 0)
    grp, _ = _underlay_group(plan, path, UnderlaySnapIndex(
        [{"kind": "line", "x1": 3000, "y1": 0, "x2": 3100, "y2": 0}], []))
    pick = pick_axis(plan, QPointF(3050, 3), TOL)
    assert pick is not None and pick.source is grp
    assert _ends(pick) == {(3000.0, 0.0), (3100.0, 0.0)}


def test_unindexed_underlay_keeps_lines_drops_curves(plan):
    path = QPainterPath()
    path.moveTo(4000, 0)
    path.lineTo(4100, 0)
    path.arcTo(QRectF(4000, -100, 200, 200), 180, -180)
    _, child = _underlay_group(plan, path)
    pick = pick_axis(plan, QPointF(4050, 3), TOL)
    assert pick is not None and pick.source is child
    assert pick_axis(plan, QPointF(4100, -98), TOL) is None          # [RED]
