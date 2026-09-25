"""Smoke item 2b guard — a placement that STARTS on any primitive (rect edge,
circle, …) inherits the primitive's direction AT THE CLICKED POINT, so the
ALIGN perpendicular ray exists: ⟂ to a rect edge, radial to a circle."""
import math

from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import CircleItem, LineItem, RectangleItem
from tests._snap_polish_helpers import click, close_view, make_view, move


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def _draw_off(view, scene, start_click, perp, tangent, away_from):
    """Arm at *start_click*, hover 10 mm beside the perpendicular ray 800 mm
    out (on the side away from *away_from*), commit; return (S, end)."""
    click(view, start_click)
    s = scene._mode_placement_anchor()
    assert s is not None
    sign = -1.0 if ((perp[0] * (away_from.x() - s.x())
                     + perp[1] * (away_from.y() - s.y())) > 0) else 1.0
    p = QPointF(s.x() + sign * 800 * perp[0], s.y() + sign * 800 * perp[1])
    cursor = QPointF(p.x() + 10 * tangent[0], p.y() + 10 * tangent[1])
    move(view, cursor)
    res = scene._align_result
    assert res is not None and res.snap_type in ("align_path", "align_intersection"), (
        res, scene._snap_result)
    click(view, cursor)
    ln = [i for i in scene._draw_lines
          if math.hypot(i.grip_points()[0].x() - s.x(), i.grip_points()[0].y() - s.y()) < 0.01]
    assert len(ln) == 1
    return s, ln[0].grip_points()[2]


def test_line_started_on_rotated_rect_edge_tracks_perpendicular(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        r = RectangleItem(QPointF(0, 0), QPointF(1000, 600))
        r.set_angle(30.0, QPointF(0, 0))              # non-axis edge: H/V rays can't fake it
        scene.addItem(r)
        e0, e1 = r.mapToScene(QPointF(0, 0)), r.mapToScene(QPointF(1000, 0))
        u = _unit(e1.x() - e0.x(), e1.y() - e0.y())    # edge direction
        perp = (-u[1], u[0])
        start = r.mapToScene(QPointF(400, 0))          # on the edge, clear of mid/corners
        s, end = _draw_off(view, scene, start, perp, u, r.mapToScene(QPointF(500, 300)))
        # Ground truth: the committed line is ⟂ to the edge (dot ≈ 0).
        d = _unit(end.x() - s.x(), end.y() - s.y())
        assert abs(d[0] * u[0] + d[1] * u[1]) < 1e-6
    finally:
        close_view(view, scene)


def test_line_started_on_circle_tracks_radial(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        r = 500.0
        scene.addItem(CircleItem(QPointF(0, 0), r))
        a = math.radians(-30)
        start = QPointF(r * math.cos(a), r * math.sin(a))   # on the circle, off quadrants
        radial = (math.cos(a), math.sin(a))
        tangent = (-radial[1], radial[0])
        s, end = _draw_off(view, scene, start, radial, tangent, QPointF(0, 0))
        # Ground truth: the committed line is radial — collinear with the centre.
        cross = (end.x() - s.x()) * s.y() - (end.y() - s.y()) * s.x()
        assert abs(cross) / (math.hypot(end.x() - s.x(), end.y() - s.y())
                             * math.hypot(s.x(), s.y())) < 1e-6
    finally:
        close_view(view, scene)


def test_line_started_on_line_keeps_line_direction(qapp):
    """Parity: a line-like source keeps its end-to-end direction."""
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(-1000, 300), QPointF(1000, -300)))
        click(view, QPointF(-400, 120))
        d = scene._align_anchor_direction()
        u = _unit(2000, -600)
        assert d is not None and abs(abs(d[0] * u[0] + d[1] * u[1]) - 1) < 1e-9
    finally:
        close_view(view, scene)


def test_line_started_on_ellipse_tracks_normal(qapp):
    from firepro3d.geometry_2d import EllipseItem
    view, scene = make_view(mode="draw_line")
    try:
        rx, ry, t = 800.0, 400.0, math.radians(60)
        scene.addItem(EllipseItem(QPointF(0, 0), rx, ry))
        start = QPointF(rx * math.cos(t), -ry * math.sin(t))
        tan = _unit(-rx * math.sin(t), -ry * math.cos(t))   # analytic tangent
        normal = (-tan[1], tan[0])
        s, end = _draw_off(view, scene, start, normal, tan, QPointF(0, 0))
        # Ground truth: ⟂ to the ANALYTIC tangent, within the flatten chord
        # angle (the engine works on the flattened curve).
        d = _unit(end.x() - s.x(), end.y() - s.y())
        assert abs(d[0] * tan[0] + d[1] * tan[1]) < 0.02
    finally:
        close_view(view, scene)
