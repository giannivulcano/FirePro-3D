"""Per-item baked-rotation (manip_rotate) math tests — U1.

Ground truth: a Y-up CCW+ rotation of a scene point p about pivot equals
CADMath.rotate_point(p, pivot, -deg) (the helper is CCW+ screen-Y-down).
Each item test rotates, checks every geometry point against ground truth,
and verifies rotate(θ) then rotate(-θ) round-trips to the original.
"""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.cad_math import CAD_Math

EPS = 1e-6


def rot_yup(pt: QPointF, pivot: QPointF, deg: float) -> QPointF:
    """Baked Y-up CCW+ rotation of a scene point (ground truth)."""
    return CAD_Math.rotate_point(pt, pivot, -deg)


def approx_pt(a: QPointF, b: QPointF, eps: float = EPS):
    assert abs(a.x() - b.x()) < eps and abs(a.y() - b.y()) < eps, \
        f"{(a.x(), a.y())} != {(b.x(), b.y())}"


@pytest.fixture
def scene(qapp):
    """A bare scene so items with scene-dependent _rebuild paths work."""
    return QGraphicsScene()


def test_wall_manip_rotate_endpoints(scene):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(w)
    pivot = QPointF(50, 0)
    p1_0, p2_0 = QPointF(w._pt1), QPointF(w._pt2)
    w.manip_rotate(90.0, pivot)
    approx_pt(w._pt1, rot_yup(p1_0, pivot, 90.0))
    approx_pt(w._pt2, rot_yup(p2_0, pivot, 90.0))
    w.manip_rotate(-90.0, pivot)
    approx_pt(w._pt1, p1_0)
    approx_pt(w._pt2, p2_0)


def test_node_manip_rotate_keeps_z(scene):
    from firepro3d.node import Node
    n = Node(30, 40, z=2500.0)
    scene.addItem(n)
    pivot = QPointF(0, 0)
    p0 = QPointF(n.scenePos())
    z0 = n.z_pos
    n.manip_rotate(90.0, pivot)
    approx_pt(n.scenePos(), rot_yup(p0, pivot, 90.0))
    assert n.z_pos == z0                      # elevation untouched
    assert n.x_pos == pytest.approx(n.scenePos().x())
    assert n.y_pos == pytest.approx(n.scenePos().y())
    n.manip_rotate(-90.0, pivot)
    approx_pt(n.scenePos(), p0)


def test_gridline_manip_rotate_origin_and_angle(scene):
    from firepro3d.gridline import GridlineItem
    g = GridlineItem(QPointF(0, 0), QPointF(100, 0), label="A")
    scene.addItem(g)
    pivot = QPointF(0, 0)
    origin0 = QPointF(g._origin)
    ang0 = g._angle_deg
    far0 = g.grip_points()[1]                 # far endpoint (rendered)
    g.manip_rotate(90.0, pivot)
    approx_pt(g._origin, rot_yup(origin0, pivot, 90.0))
    assert g._angle_deg == pytest.approx((ang0 + 90.0) % 360.0)
    approx_pt(g.grip_points()[1], rot_yup(far0, pivot, 90.0), eps=1e-4)
    g.manip_rotate(-90.0, pivot)
    approx_pt(g._origin, origin0)


def test_gridline_manip_rotate_respects_lock(scene):
    from firepro3d.gridline import GridlineItem
    g = GridlineItem(QPointF(0, 0), QPointF(100, 0), label="A")
    scene.addItem(g)
    g._locked = True
    o0, a0 = QPointF(g._origin), g._angle_deg
    g.manip_rotate(45.0, QPointF(10, 10))
    approx_pt(g._origin, o0)
    assert g._angle_deg == a0


def test_room_manip_rotate_boundary(scene):
    from firepro3d.room import Room
    r = Room(boundary=[QPointF(0, 0), QPointF(100, 0), QPointF(100, 80)])
    scene.addItem(r)
    pivot = QPointF(50, 40)
    b0 = [QPointF(p) for p in r._boundary]
    r.manip_rotate(90.0, pivot)
    for got, orig in zip(r._boundary, b0):
        approx_pt(got, rot_yup(orig, pivot, 90.0))
    r.manip_rotate(-90.0, pivot)
    for got, orig in zip(r._boundary, b0):
        approx_pt(got, orig)


def test_room_marks_no_solo_rotate():
    from firepro3d.room import Room
    assert getattr(Room, "MANIP_NO_SOLO_ROTATE", False) is True


def test_floor_manip_rotate_points_keeps_zrange(scene):
    from firepro3d.floor_slab import FloorSlab
    f = FloorSlab(points=[QPointF(0, 0), QPointF(200, 0),
                          QPointF(200, 150), QPointF(0, 150)])
    scene.addItem(f)
    pivot = QPointF(100, 75)
    p0 = [QPointF(p) for p in f._points]
    z0 = f.z_range_mm()
    # Elevation-field snapshot: z_range_mm() is None in a bare scene (no level
    # manager), so its equality is trivially true; assert the real fields too.
    elev0 = (f._top_mode, f._top_level, f._top_offset_mm, f._top_abs_z_mm,
             f._bottom_mode, f._bottom_level, f._bottom_offset_mm,
             f._bottom_abs_z_mm, f._thickness_mm)
    f.manip_rotate(90.0, pivot)
    for got, orig in zip(f._points, p0):
        approx_pt(got, rot_yup(orig, pivot, 90.0))
    assert f.z_range_mm() == z0               # elevation invariant
    assert (f._top_mode, f._top_level, f._top_offset_mm, f._top_abs_z_mm,
            f._bottom_mode, f._bottom_level, f._bottom_offset_mm,
            f._bottom_abs_z_mm, f._thickness_mm) == elev0
    f.manip_rotate(-90.0, pivot)
    for got, orig in zip(f._points, p0):
        approx_pt(got, orig)


def test_roof_manip_rotate_points(scene):
    from firepro3d.roof import RoofItem
    r = RoofItem(points=[QPointF(0, 0), QPointF(300, 0),
                         QPointF(300, 200), QPointF(0, 200)])
    scene.addItem(r)
    pivot = QPointF(0, 0)
    p0 = [QPointF(p) for p in r._points]
    pitch0 = r._pitch_deg
    r.manip_rotate(45.0, pivot)
    for got, orig in zip(r._points, p0):
        approx_pt(got, rot_yup(orig, pivot, 45.0))
    assert r._pitch_deg == pitch0             # roof form untouched
    r.manip_rotate(-45.0, pivot)
    for got, orig in zip(r._points, p0):
        approx_pt(got, orig)


def test_polyline_manip_rotate(scene):
    from firepro3d.construction_geometry import PolylineItem
    pl = PolylineItem(QPointF(0, 0))
    pl._points = [QPointF(0, 0), QPointF(50, 0), QPointF(50, 50)]
    pl._rebuild_path()
    scene.addItem(pl)
    pivot = QPointF(0, 0)
    p0 = [QPointF(p) for p in pl._points]
    pl.manip_rotate(90.0, pivot)
    for got, orig in zip(pl._points, p0):
        approx_pt(got, rot_yup(orig, pivot, 90.0))


def test_line_manip_rotate(scene):
    from firepro3d.construction_geometry import LineItem
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(ln)
    pivot = QPointF(50, 0)
    a0, b0 = QPointF(ln._pt1), QPointF(ln._pt2)
    ln.manip_rotate(90.0, pivot)
    approx_pt(ln._pt1, rot_yup(a0, pivot, 90.0))
    approx_pt(ln._pt2, rot_yup(b0, pivot, 90.0))
    approx_pt(ln.line().p1(), ln._pt1)        # setLine synced


def test_circle_manip_rotate_moves_center_only(scene):
    from firepro3d.construction_geometry import CircleItem
    c = CircleItem(QPointF(100, 0), 20.0)
    scene.addItem(c)
    pivot = QPointF(0, 0)
    ctr0, r0 = QPointF(c._center), c._radius
    c.manip_rotate(90.0, pivot)
    approx_pt(c._center, rot_yup(ctr0, pivot, 90.0))
    assert c._radius == r0                     # shape invariant


def test_arc_manip_rotate_center_and_angle(scene):
    from firepro3d.construction_geometry import ArcItem
    a = ArcItem(QPointF(0, 0), 50.0, 0.0, 90.0)
    scene.addItem(a)
    pivot = QPointF(0, 0)
    start0, span0 = a._start_deg, a._span_deg
    startpt0 = a.grip_points()[1]              # rendered start point probe
    a.manip_rotate(30.0, pivot)
    assert a._start_deg == pytest.approx(start0 + 30.0)
    assert a._span_deg == pytest.approx(span0)         # span unchanged
    approx_pt(a.grip_points()[1], rot_yup(startpt0, pivot, 30.0), eps=1e-3)


def test_regular_polygon_manip_rotate(scene):
    from firepro3d.construction_geometry import RegularPolygonItem
    rp = RegularPolygonItem(QPointF(0, 0), sides=5, radius_mm=40.0,
                            rotation_deg=0.0)
    scene.addItem(rp)
    pivot = QPointF(100, 0)
    ctr0 = QPointF(rp._center)
    rot0 = rp._rotation_deg
    v0 = rp.vertices()[0]
    rp.manip_rotate(72.0, pivot)
    approx_pt(rp._center, rot_yup(ctr0, pivot, 72.0))
    assert rp._rotation_deg == pytest.approx(rot0 + 72.0)
    approx_pt(rp.vertices()[0], rot_yup(v0, pivot, 72.0), eps=1e-3)


# ── DesignArea badge (baked _angle on a fixed-layout label) — Task 8 ────

def test_badge_self_rotate_tilts_in_place(qapp):
    from firepro3d.design_area import DesignArea, badge_fixed_size_mm
    sc = QGraphicsScene()
    da = DesignArea()
    sc.addItem(da)
    assert da.badge is not None
    da.set_badge_offset(QPointF(500, 300))
    w, h = badge_fixed_size_mm()
    center0 = da.badge.pos() + QPointF(w / 2, h / 2)
    da.manip_rotate(30.0, QPointF(center0))   # rotate about own centre
    center1 = da.badge.pos() + QPointF(w / 2, h / 2)
    approx_pt(center1, center0, eps=1e-3)
    assert da.badge._angle == pytest.approx(30.0)


def test_badge_group_rotate_moves_center(qapp):
    from firepro3d.design_area import DesignArea, badge_fixed_size_mm
    sc = QGraphicsScene()
    da = DesignArea()
    sc.addItem(da)
    da.set_badge_offset(QPointF(500, 300))
    w, h = badge_fixed_size_mm()
    center0 = da.badge.pos() + QPointF(w / 2, h / 2)
    pivot = QPointF(0, 0)
    da.manip_rotate(90.0, pivot)
    center1 = da.badge.pos() + QPointF(w / 2, h / 2)
    approx_pt(center1, rot_yup(center0, pivot, 90.0), eps=1e-3)
    assert da.badge._angle == pytest.approx(90.0)


def test_badge_angle_round_trips_through_serialization(qapp):
    from firepro3d.design_area import DesignArea
    from firepro3d import network_codec
    sc = QGraphicsScene()
    da = DesignArea()
    sc.addItem(da)
    da.set_badge_offset(QPointF(500, 300))
    da.badge._angle = 42.0
    d = network_codec.serialize_design_area(da, {}, None)
    assert d.get("badge_angle") == pytest.approx(42.0)
