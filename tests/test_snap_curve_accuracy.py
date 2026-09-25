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


def test_large_ellipse_far_sector_lands_on_curve(qapp):
    """I1: a 20 m ellipse flattens to >511 segments; the sector past the
    old per-item segment cap (350°) must still snap onto the curve."""
    big_r = 10000.0
    a350 = math.radians(350)
    # Centre placed so the 350° point sits on screen at (600, 400), clear of
    # the origin's own snap candidates.
    c = QPointF(600 - big_r * math.cos(a350), 400 - big_r * math.sin(a350))
    view, scene = make_view(scale=0.25)
    try:
        el = EllipseItem(c, big_r, big_r)
        scene.addItem(el)
        off = 3.0 / 0.25
        tgt = QPointF(c.x() + (big_r + off) * math.cos(a350),
                      c.y() + (big_r + off) * math.sin(a350))
        ep = _drag_line_end_to(view, scene, tgt)
        # Ground truth = the DRAWN curve (4 cubic Béziers, whose own radial
        # error vs the analytic circle is ~0.027 % R = 2.7 mm here), sampled
        # with pointAtPercent (coarse, then ~0.06 mm around the best hit) —
        # independent of the engine's toSubpathPolygons flattening.
        path = el.path()

        def _d(t):
            q = el.mapToScene(path.pointAtPercent(min(max(t, 0.0), 1.0)))
            return math.hypot(q.x() - ep.x(), q.y() - ep.y())

        n = 2000
        t0 = min((i / n for i in range(n + 1)), key=_d)
        d_curve = min(_d(t0 + (k / 1000.0 - 1.0) * 2.0 / n) for k in range(2001))
        assert d_curve < 1.0
    finally:
        close_view(view, scene)
