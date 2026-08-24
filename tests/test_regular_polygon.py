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

def test_circumscribed_vertex_grip_round_trip(qapp):
    # Grip index 0 = centre; grip index k+1 = vertex k.
    # apply_grip(3, ...) → vi = 3-1 = 2 → vertex index 2.
    p = RegularPolygonItem(QPointF(0, 0), sides=5, radius_mm=80.0,
                           rotation_deg=10.0, inscribed=False)
    target = QPointF(150.0, 40.0)
    p.apply_grip(3, target)   # drag grip 3 → vertex index 2
    vs = p.vertices()
    assert _approx(vs[2].x(), target.x(), tol=1e-3)
    assert _approx(vs[2].y(), target.y(), tol=1e-3)
    # still regular: all edges equal
    edges = [math.hypot(vs[(i+1) % 5].x()-vs[i].x(), vs[(i+1) % 5].y()-vs[i].y())
             for i in range(5)]
    assert all(_approx(e, edges[0], tol=1e-3) for e in edges)


def test_positive_rotation_swings_vertex_up_yup(qapp):
    """Ground truth (Y-up, CCW+): rotation_deg=90 puts vertex 0 straight UP.

    'Up' on screen is -y in Qt scene.  Asserts the OBSERVABLE direction, not
    rotation()==angle — it fails on a y-down (mirrored) convention.
    """
    p = RegularPolygonItem(QPointF(0, 0), sides=4, radius_mm=100.0,
                           rotation_deg=90.0, inscribed=True)
    v0 = p.vertices()[0]
    assert _approx(v0.x(), 0.0, tol=1e-6)
    assert _approx(v0.y(), -100.0, tol=1e-6)   # up = -y in Qt scene
    # 0 deg points due-east (+x), matching the reference-line datum.
    p0 = RegularPolygonItem(QPointF(0, 0), sides=4, radius_mm=100.0,
                            rotation_deg=0.0, inscribed=True)
    e0 = p0.vertices()[0]
    assert _approx(e0.x(), 100.0, tol=1e-6) and _approx(e0.y(), 0.0, tol=1e-6)
