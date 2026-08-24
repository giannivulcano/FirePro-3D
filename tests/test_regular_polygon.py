import math
from PyQt6.QtCore import QPointF
from firepro3d.construction_geometry import RegularPolygonItem

def _approx(a, b, tol=1e-6):
    return abs(a - b) < tol

def test_inscribed_square_vertices(qapp):
    p = RegularPolygonItem(QPointF(0, 0), sides=4, radius_mm=100.0,
                           rotation_deg=0.0, inscribed=True)
    vs = p.vertices()
    assert len(vs) == 4
    xs = sorted([(round(v.x(), 3), round(v.y(), 3)) for v in vs])
    assert xs == sorted([(100.0, 0.0), (0.0, 100.0), (-100.0, 0.0), (0.0, -100.0)])

def test_circumscribed_square_apothem(qapp):
    p = RegularPolygonItem(QPointF(0, 0), sides=4, radius_mm=100.0,
                           rotation_deg=0.0, inscribed=False)
    vs = p.vertices()
    corners = sorted([(round(v.x()), round(v.y())) for v in vs])
    assert corners == sorted([(100, -100), (100, 100), (-100, 100), (-100, -100)])

def test_regenerate_on_sides_change(qapp):
    p = RegularPolygonItem(QPointF(0, 0), sides=4, radius_mm=100.0)
    p.set_property("Sides", 6)
    assert len(p.vertices()) == 6

def test_vertex_grip_keeps_regular(qapp):
    p = RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=100.0,
                           rotation_deg=0.0, inscribed=True)
    p.apply_grip(1, QPointF(200, 0))
    vs = p.vertices()
    edges = [math.hypot(vs[(i+1) % 6].x()-vs[i].x(), vs[(i+1) % 6].y()-vs[i].y())
             for i in range(6)]
    assert all(_approx(e, edges[0], tol=1e-3) for e in edges)
    assert _approx(p._radius_mm, 200.0, tol=1e-3)

def test_centre_grip_moves(qapp):
    p = RegularPolygonItem(QPointF(0, 0), sides=5, radius_mm=50.0)
    p.apply_grip(0, QPointF(10, 20))
    assert p._center == QPointF(10, 20)

def test_grip_points_centre_first(qapp):
    p = RegularPolygonItem(QPointF(0, 0), sides=5, radius_mm=50.0)
    gp = p.grip_points()
    assert gp[0] == QPointF(0, 0)
    assert len(gp) == 6

def test_serialization_round_trip(qapp):
    p = RegularPolygonItem(QPointF(3, 4), sides=7, radius_mm=42.0,
                           rotation_deg=15.0, inscribed=False)
    d = p.to_dict()
    assert d["type"] == "polygon"
    p2 = RegularPolygonItem.from_dict(d)
    assert p2._sides == 7 and _approx(p2._radius_mm, 42.0)
    assert _approx(p2._rotation_deg, 15.0) and p2._inscribed is False
    assert p2._center == QPointF(3, 4)

def test_is_fillable(qapp):
    p = RegularPolygonItem(QPointF(0, 0), sides=4, radius_mm=100.0)
    assert p.is_fillable() is True

def test_sides_clamped(qapp):
    p = RegularPolygonItem(QPointF(0, 0), sides=2, radius_mm=100.0)
    assert p._sides == 3
    p.set_property("Sides", 999)
    assert p._sides == 120
