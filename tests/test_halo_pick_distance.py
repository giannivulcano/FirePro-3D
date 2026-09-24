"""halo_pick_distance_px: screen-px distance cursor -> drawn trace (SNAP model)."""
import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import (QGraphicsScene, QGraphicsEllipseItem,
                             QGraphicsItem, QGraphicsPathItem)

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.node import Node
from firepro3d.gridline import GridlineItem
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


def test_screen_fixed_unfilled_marker_measures_in_true_device_pixels(qapp):
    """A synthetic ItemIgnoresTransformations marker (unfilled ring, no
    HALO_AREA): its screen-space radius must stay 5 px at any zoom, proving
    the distance is computed via item.deviceTransform(dt) and not by mapping
    the local trace through sceneTransform() then dt (which would scale the
    ring's radius by the zoom and give the wrong answer — see RED check in
    the commit body)."""
    marker = QGraphicsEllipseItem(-5, -5, 10, 10)
    marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
    marker.setPos(100, 0)
    keep = _in_scene(marker)
    assert not halo_is_area(marker)          # unfilled plain ellipse -> not an area
    dt = QTransform.fromScale(10, 10)
    cursor = dt.map(QPointF(100, 0)) + QPointF(8, 0)
    d = halo_pick_distance_px(marker, cursor, dt)
    assert abs(d - 3.0) < 1e-6               # 8px cursor - 5px (screen-constant) ring radius


def test_real_gridline_bubble_center_is_a_direct_hit(qapp):
    """A real plan GridBubble (HALO_AREA, ItemIgnoresTransformations, filled)
    is a direct hit (distance 0) at its own centre, at any zoom — this is
    the case the ranking task relies on: MIN over a gridline's raw child hits
    collapses to 0 through its bubble children."""
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 500), "A")
    keep = _in_scene(gl)
    bubble = gl.bubble1
    assert bubble.isVisible()                # visible by default; no toggle needed
    assert halo_is_area(bubble)
    for zoom in (1, 20):
        dt = QTransform.fromScale(zoom, zoom)
        center_vp = bubble.deviceTransform(dt).map(QPointF(0, 0))
        assert halo_pick_distance_px(bubble, center_vp, dt) == 0.0


def test_empty_path_item_has_no_traceable_geometry(qapp):
    """A bare QGraphicsPathItem() with an empty path: _halo_trace_path_local
    falls back to shape(), but shape() of an item with no path is ALSO empty
    (verified: QGraphicsPathItem().shape().isEmpty() is True), so the
    deviceTransform-mapped trace is empty and halo_pick_distance_px returns
    math.inf before the area/contains check ever runs. halo_is_area is still
    True for it (the QGraphicsPathItem-with-empty-path branch), but that
    predicate is moot with no geometry to be inside of."""
    item = QGraphicsPathItem()
    keep = _in_scene(item)
    assert item.shape().isEmpty()
    assert halo_is_area(item)
    assert halo_pick_distance_px(item, QPointF(0, 0), QTransform()) == math.inf
