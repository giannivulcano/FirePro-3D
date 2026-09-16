"""Tests for firepro3d.geometry_import — pure, headless conversion layer.

Tests for bbox_top_left and geom_dicts_to_primitives.
"""

import math

from PyQt6.QtCore import QPointF
from firepro3d.geometry_import import bbox_top_left, geom_dicts_to_primitives
from firepro3d.construction_geometry import LineItem, CircleItem, PolylineItem, ArcItem, EllipseItem, SplineItem


def test_bbox_top_left_over_mixed_primitives(qapp):
    items = [
        LineItem(QPointF(10, 40), QPointF(30, 10)),
        CircleItem(QPointF(50, 50), 5),
    ]
    tl = bbox_top_left(items)
    assert (round(tl.x(), 3), round(tl.y(), 3)) == (10.0, 10.0)


def test_bbox_top_left_empty_returns_origin(qapp):
    tl = bbox_top_left([])
    assert (tl.x(), tl.y()) == (0.0, 0.0)


def test_line_dict_scales_to_lineitem(qapp):
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 10, "y2": 0, "color": "#ff0000"}]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=2.0)
    assert skipped == 0 and len(items) == 1
    ln = items[0]
    assert isinstance(ln, LineItem)
    assert (ln.line().x2(), ln.line().y2()) == (20.0, 0.0)
    assert ln.pen().color().name() == "#ff0000"


def test_circle_dict_center_radius_scaled(qapp):
    geoms = [{"kind": "circle", "x": 5, "y": 5, "w": 10, "h": 10, "color": "#00ff00"}]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=3.0)
    c = items[0]
    assert isinstance(c, CircleItem)
    assert (round(c._center.x()), round(c._center.y()), round(c._radius)) == (30, 30, 15)


def test_path_points_open_and_closed(qapp):
    geoms = [
        {"kind": "path_points", "points": [(0, 0), (10, 0), (10, 10)], "closed": True},
        {"kind": "path_points", "points": [(0, 0), (5, 5)], "closed": False},
    ]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=1.0)
    assert skipped == 0 and all(isinstance(i, PolylineItem) for i in items)
    assert items[0]._closed is True and items[1]._closed is False
    assert len(items[0]._points) == 3


def test_unsupported_kinds_skipped_and_counted(qapp):
    geoms = [
        {"kind": "text", "x": 0, "y": 0, "text": "A"},
        {"kind": "hatch", "x": 0, "y": 0},
        {"kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
    ]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=1.0)
    assert len(items) == 1 and skipped == 2


def test_arc_dict_maps_to_arcitem_observable_endpoints(qapp):
    geoms = [{"kind": "arc", "rx": -100, "ry": -100, "rw": 200, "rh": 200,
              "start": 30, "span": 90, "color": "#123456"}]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=1.0)
    assert skipped == 0 and len(items) == 1
    a = items[0]
    assert isinstance(a, ArcItem)
    grips = a.grip_points()
    assert (round(grips[0].x()), round(grips[0].y())) == (0, 0)
    assert round(grips[1].x()) == round(100 * math.cos(math.radians(30)))
    assert round(grips[1].y()) == round(-100 * math.sin(math.radians(30)))
    assert round(grips[2].x()) == round(100 * math.cos(math.radians(120)))
    assert round(grips[2].y()) == round(-100 * math.sin(math.radians(120)))
    # pointAtPercent(0.5) uses Bezier approximation — within 2 units of analytic midpoint
    mid = a.path().pointAtPercent(0.5)
    assert abs(mid.x() - 100 * math.cos(math.radians(75))) < 2.0
    assert abs(mid.y() - (-100 * math.sin(math.radians(75)))) < 2.0


def test_ellipse_full_dict_maps_to_ellipse_item(qapp):
    geoms = [{"kind": "ellipse_full", "x": -20, "y": -10, "w": 40, "h": 20,
              "pos_cx": 100, "pos_cy": 50, "rotation": 30, "color": "#00aa00"}]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=2.0)
    assert skipped == 0 and len(items) == 1
    e = items[0]
    assert isinstance(e, EllipseItem)
    assert (round(e._center.x()), round(e._center.y())) == (200, 100)
    assert (round(e._rx), round(e._ry)) == (40, 20)
    assert round(e._rotation_deg) == 30
    assert e.pen().color().name() == "#00aa00"


def test_primitives_roundtrip_to_block_type_keys(qapp):
    geoms = [
        {"kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
        {"kind": "circle", "x": 0, "y": 0, "w": 10, "h": 10},
        {"kind": "path_points", "points": [(0, 0), (5, 5), (10, 0)], "closed": False},
    ]
    items, _ = geom_dicts_to_primitives(geoms, import_scale=1.0)
    assert items[0].to_dict()["type"] == "draw_line"
    assert items[1].to_dict()["type"] == "draw_circle"
    assert items[2].to_dict()["type"] == "polyline"


def test_spline_dict_maps_to_splineitem_endpoints(qapp):
    cps = [[0, 0], [10, 20], [30, -20], [40, 0]]
    geoms = [{"kind": "spline", "control_points": cps, "degree": 3,
              "knots": None, "weights": None, "closed": False, "color": "#abcdef"}]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=2.0)
    assert skipped == 0 and len(items) == 1
    sp = items[0]
    assert isinstance(sp, SplineItem)
    assert len(sp._control_points) == 4
    assert (sp._control_points[0].x(), sp._control_points[0].y()) == (0.0, 0.0)
    assert (sp._control_points[-1].x(), sp._control_points[-1].y()) == (80.0, 0.0)
    p0 = sp.path().pointAtPercent(0.0)
    assert (round(p0.x()), round(p0.y())) == (0, 0)
    assert sp.pen().color().name() == "#abcdef"


def test_malformed_line_dict_skipped_not_raised(qapp):
    """A malformed line dict (missing 'x2') among valid dicts: skip + count, no exception."""
    geoms = [
        {"kind": "line", "x1": 0, "y1": 0, "x2": 5, "y2": 0},   # valid
        {"kind": "line", "x1": 0, "y1": 0},                       # malformed: missing x2
        {"kind": "line", "x1": 1, "y1": 1, "x2": 6, "y2": 1},   # valid
    ]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=1.0)
    assert len(items) == 2
    assert skipped == 1
