"""Tests for firepro3d.geometry_import — pure, headless conversion layer.

Tests for bbox_top_left and geom_dicts_to_primitives.
"""

from PyQt6.QtCore import QPointF
from firepro3d.geometry_import import bbox_top_left
from firepro3d.construction_geometry import LineItem, CircleItem


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


from firepro3d.geometry_import import geom_dicts_to_primitives
from firepro3d.construction_geometry import PolylineItem


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
        {"kind": "ellipse_full", "x": 0, "y": 0, "w": 4, "h": 2},
        {"kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1},
    ]
    items, skipped = geom_dicts_to_primitives(geoms, import_scale=1.0)
    assert len(items) == 1 and skipped == 2


def test_primitives_roundtrip_to_block_type_keys(qapp):
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1}]
    items, _ = geom_dicts_to_primitives(geoms, import_scale=1.0)
    assert items[0].to_dict()["type"] == "draw_line"
