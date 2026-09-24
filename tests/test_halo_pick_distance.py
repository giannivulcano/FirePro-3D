"""halo_pick_distance_px: screen-px distance cursor -> drawn trace (SNAP model)."""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.node import Node
from firepro3d.halo import halo_pick_distance_px, halo_is_area


def _in_scene(item):
    sc = QGraphicsScene()
    sc.addItem(item)
    return sc


def test_line_distance_is_in_pixels_at_any_zoom(qapp):
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    keep = _in_scene(ln)
    for zoom in (0.5, 5.0, 50.0):
        dt = QTransform.fromScale(zoom, zoom)
        cursor = dt.map(QPointF(50, 0)) + QPointF(0, 7)   # 7 px below the line
        assert abs(halo_pick_distance_px(ln, cursor, dt) - 7.0) < 1e-6


def test_unfilled_rect_measures_to_its_outline(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    keep = _in_scene(r)
    assert not halo_is_area(r)
    d = halo_pick_distance_px(r, QPointF(50, 50), QTransform())
    assert abs(d - 50.0) < 1e-6          # centre is 50 px from every edge


def test_filled_rect_inside_is_a_direct_hit(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 100))
    r.fill_type = "solid"
    keep = _in_scene(r)
    assert halo_is_area(r)
    assert halo_pick_distance_px(r, QPointF(50, 50), QTransform()) == 0.0


def test_node_center_is_a_direct_hit_at_any_zoom(qapp):
    """Node is HALO_AREA — a cursor on its centre is a direct hit regardless
    of zoom. deviceTransform() keeps this correct even though Node's marker
    scales with the scene (it is not ItemIgnoresTransformations here)."""
    n = Node(10, 20)
    keep = _in_scene(n)
    assert halo_is_area(n)
    dt = QTransform.fromScale(10, 10)
    cursor = dt.map(QPointF(10, 20))
    assert halo_pick_distance_px(n, cursor, dt) == 0.0
    far_cursor = cursor + QPointF(300, 0)
    assert halo_pick_distance_px(n, far_cursor, dt) > 100.0
