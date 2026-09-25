"""S4 guard — grip-dragging an endpoint onto a circle/arc/ellipse lands ON the curve."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import ArcItem, CircleItem, EllipseItem, LineItem
from tests._snap_polish_helpers import close_view, drag, make_view

R = 500.0
A45 = math.radians(-45)      # scene Y-down: upper-right on screen


def _drag_line_end_to(view, scene, target_pt):
    ln = LineItem(QPointF(-1200, -900), QPointF(-800, -900))
    scene.addItem(ln)
    scene.clearSelection()
    ln.setSelected(True)
    drag(view, ln.grip_points()[2], target_pt)
    return ln.grip_points()[2]


@pytest.mark.parametrize("scale", [0.25, 1.0])
def test_circle_endpoint_lands_on_circle(qapp, scale):
    view, scene = make_view(scale=scale)
    try:
        scene.addItem(CircleItem(QPointF(0, 0), R))
        off = 3.0 / scale
        ep = _drag_line_end_to(view, scene, QPointF((R + off) * math.cos(A45),
                                                   (R + off) * math.sin(A45)))
        assert abs(math.hypot(ep.x(), ep.y()) - R) < 0.01
    finally:
        close_view(view, scene)


def test_circle_after_zoom_change_lands_on_circle(qapp):
    view, scene = make_view(scale=0.25)
    try:
        circ = CircleItem(QPointF(0, 0), R)
        scene.addItem(circ)
        circ.boundingRect()                      # cache the bbox at 0.25
        view.resetTransform(); view.scale(1.0, 1.0); view.centerOn(0, 0)
        qapp.processEvents()
        ep = _drag_line_end_to(view, scene, QPointF(R + 3.0, 0.0))
        assert abs(math.hypot(ep.x(), ep.y()) - R) < 0.01
    finally:
        close_view(view, scene)


def test_arc_outside_cursor_lands_on_arc(qapp):
    view, scene = make_view(scale=0.25)
    try:
        scene.addItem(ArcItem(QPointF(0, 0), R, 0.0, 180.0))
        off = 10.0 / 0.25
        ep = _drag_line_end_to(view, scene, QPointF((R + off) * math.cos(A45),
                                                   (R + off) * math.sin(A45)))
        assert abs(math.hypot(ep.x(), ep.y()) - R) < 0.01
    finally:
        close_view(view, scene)


def test_ellipse_outside_cursor_lands_on_curve(qapp):
    view, scene = make_view(scale=0.25)
    try:
        el = EllipseItem(QPointF(0, 0), R, R)    # rx == ry: distance from centre == R
        scene.addItem(el)
        off = 10.0 / 0.25
        ep = _drag_line_end_to(view, scene, QPointF((R + off) * math.cos(A45),
                                                   (R + off) * math.sin(A45)))
        assert abs(math.hypot(ep.x(), ep.y()) - R) < 1.0   # flatten tolerance
    finally:
        close_view(view, scene)
