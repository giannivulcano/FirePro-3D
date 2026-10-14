"""CS5 controller guards (D71-D77, D81): real Block Editor scenes, real solve."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import constraint_dims as cd
from firepro3d.geometry_2d import ArcItem, CircleItem, EllipseItem, LineItem, RegularPolygonItem
from firepro3d.model_space import Model_Space


def _sc():
    return Model_Space(scene_role="block_editor")


def _add(sc, it, lst):
    sc.addItem(it); getattr(sc, lst).append(it); return it


def R(it, h):
    return {"uid": it._uid, "h": h}


def _dir(ln):
    return math.degrees(math.atan2(-(ln._pt2.y() - ln._pt1.y()), ln._pt2.x() - ln._pt1.x()))


def test_circle_diameter_typed_keeps_centre_and_holds_on_grip_edit(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(10, 20), 30), "_draw_circles")
    d = ctl.add("dim_diameter", [R(c, "curve")])
    assert d.value == pytest.approx(60.0)
    assert ctl.set_value(d.id, 25.0)
    assert c._radius == pytest.approx(12.5, abs=1e-9)
    assert (c._center.x(), c._center.y()) == pytest.approx((10.0, 20.0))
    with ctl.edit([c]):
        c.set_radius(40.0)
    assert c._radius == pytest.approx(12.5, abs=1e-6)


def test_arc_sweep_typed_keeps_start(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    a = _add(sc, ArcItem(QPointF(0, 0), 50, 20, 120), "_draw_arcs")
    s = ctl.add("dim_arc_angle", [R(a, "curve")])
    assert s.value == pytest.approx(120.0)
    assert ctl.set_value(s.id, 90.0)
    assert (a._start_deg, a._span_deg) == pytest.approx((20.0, 90.0), abs=1e-6)


def test_polygon_and_ellipse_radius_dims(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    pg = _add(sc, RegularPolygonItem(QPointF(0, 0), 6, 60.0), "_draw_polygons")
    e = _add(sc, EllipseItem(QPointF(300, 0), 80, 45, 15), "_draw_ellipses")
    p = ctl.add("dim_radius", [R(pg, "radius")])
    r1 = ctl.add("dim_radius", [R(e, "rx")])
    assert ctl.set_value(p.id, 40.0) and pg._radius_mm == pytest.approx(40.0)
    assert ctl.set_value(r1.id, 70.0) and e._rx == pytest.approx(70.0) and e._ry == pytest.approx(45.0)


def _vee(sc):
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 0), QPointF(0, -100)), "_draw_lines")
    return l1, l2


def test_angle_typed_holds_first_edge_and_pivots_second(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1, l2 = _vee(sc)
    refs = [R(l1, "edge"), R(l2, "edge")]
    helper, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(30, -30))
    c = ctl.add("dim_angle", refs, helper=helper)
    assert c.value == pytest.approx(90.0)
    assert ctl.set_value(c.id, 60.0)
    assert _dir(l1) == pytest.approx(0.0, abs=1e-9)
    assert (l2._pt1.x(), l2._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert _dir(l2) == pytest.approx(60.0, abs=1e-6)
    assert math.hypot(l2._pt2.x(), l2._pt2.y()) == pytest.approx(100.0, abs=1e-6)


def test_edge_axis_angle_typed_pivots_the_edge(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    ln = _add(sc, LineItem(QPointF(0, 0), QPointF(50, -86.6025403784)), "_draw_lines")
    refs = [R(ln, "edge"), {"ref": "x_axis"}]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(60, -30))
    c = ctl.add("dim_angle", refs, helper=h)
    assert c.value == pytest.approx(60.0, abs=1e-6)
    assert ctl.set_value(c.id, 30.0)
    assert (ln._pt1.x(), ln._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert _dir(ln) == pytest.approx(30.0, abs=1e-6)
    assert math.hypot(ln._pt2.x(), ln._pt2.y()) == pytest.approx(100.0, abs=1e-6)


def test_parallel_edges_precheck_is_linear(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 50), QPointF(100, 50)), "_draw_lines")
    assert ctl.dim_precheck([R(l1, "edge"), R(l2, "edge")])[0] == "dim_point_line"
    assert ctl.constraints == []


def test_angle_value_range_rejected(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1, l2 = _vee(sc)
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(30, -30))
    c = ctl.add("dim_angle", refs, helper=h)
    n = len(sc._undo_stack)
    assert not ctl.set_value(c.id, 180.0) and c.value == pytest.approx(90.0)
    assert len(sc._undo_stack) == n
    from firepro3d.model_view import Model_View
    v = Model_View(sc)
    assert cd.entry_for(v, ctl, c).spec.maximum == pytest.approx(180.0 - 1e-6)


def test_one_dim_per_measure_radius_vs_diameter(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    assert ctl.add("dim_radius", [R(c, "curve")]) is not None
    assert ctl.add("dim_diameter", [R(c, "curve")]) is None          # D71


def test_second_axis_angle_is_reference(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    ln = _add(sc, LineItem(QPointF(0, 0), QPointF(100, -100)), "_draw_lines")
    for ax, p in (("x_axis", QPointF(50, -10)), ("y_axis", QPointF(10, -50))):
        refs = [R(ln, "edge"), {"ref": ax}]
        h, _ = cd.placement_for(ctl, "dim_angle", refs, p)
        ctl.add("dim_angle", refs, helper=h)
    a, b = ctl.constraints
    assert a.driving and not b.driving                              # D52


def test_toggle_radius_to_diameter_one_undo_step(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    d = ctl.add("dim_radius", [R(c, "curve")], label={"angle": 30.0})
    n = len(sc._undo_stack)
    assert ctl.set_dim_kind(d.id, "dim_diameter")
    assert (d.type, d.value, d.label) == ("dim_diameter", pytest.approx(60.0), {"angle": 30.0})
    assert c._radius == pytest.approx(30.0) and len(sc._undo_stack) == n + 1


def test_scale_scales_lengths_not_angles(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1, l2 = _vee(sc)
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(30, -30))
    ang = ctl.add("dim_angle", refs, helper=h)
    ln = ctl.add("dim_distance", [R(l1, "edge")])
    out = ctl._scale_dims([l1, l2], 2.0)
    assert [c.id for c, _v in out] == [ln.id] and ang.value == pytest.approx(90.0)


def test_reflection_keeps_angle_value_on_mirrored_sector(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 0), QPointF(50, -86.6025403784)), "_draw_lines")
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(60, -20))
    c = ctl.add("dim_angle", refs, helper=h)
    sign0 = c.helper["sign"]

    def flip(p):                                   # reflect across the X axis
        return QPointF(p.x(), -p.y())
    with ctl.edit([l1, l2], point_map=flip):
        for ln in (l1, l2):
            ln._pt1, ln._pt2 = flip(ln._pt1), flip(ln._pt2)
            ln.setLine(ln._pt1.x(), ln._pt1.y(), ln._pt2.x(), ln._pt2.y())
    assert c.helper["sign"] == -sign0 and ctl.measure(c) == pytest.approx(60.0, abs=1e-6)
    assert _dir(l2) == pytest.approx(-60.0, abs=1e-6)              # geometry not fought


def test_angle_sector_drag_remeasures_without_moving_geometry(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 0), QPointF(50, -86.6025403784)), "_draw_lines")
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(60, -20))
    c = ctl.add("dim_angle", refs, helper=h)
    before = (l2._pt2.x(), l2._pt2.y())
    n = len(sc._undo_stack)
    assert ctl.drag_dim_to_scene(c.id, QPointF(-60, -20))
    assert c.value == pytest.approx(120.0, abs=1e-6)
    assert (l2._pt2.x(), l2._pt2.y()) == pytest.approx(before)
    ctl.end_dim_drag()
    assert len(sc._undo_stack) == n + 1


def test_persistence_round_trip_of_cs5_records(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    l1, l2 = _vee(sc)
    ctl.add("dim_diameter", [R(c, "curve")], label={"angle": 10.0})
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(30, -30))
    ctl.add("dim_angle", refs, helper=h)
    recs = ctl.to_records()
    ctl.load(recs)
    assert [(x.type, x.inert, x.label, x.helper) for x in ctl.constraints] == [
        ("dim_diameter", False, {"angle": 10.0}, {}),
        ("dim_angle", False, None, h)]


def test_invalid_angle_helper_is_inert(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1, l2 = _vee(sc)
    rec = {"id": "x", "type": "dim_angle", "refs": [R(l1, "edge"), R(l2, "edge")],
           "value": 90.0, "helper": {"dirs": [2, 1], "sign": 1}}
    ctl.load([rec])
    assert ctl.constraints[0].inert


def test_parallel_lines_linear_dim_typed_moves_the_second(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(20, -50), QPointF(120, -50)), "_draw_lines")
    t, refs = ctl.dim_precheck([R(l1, "edge"), R(l2, "edge")])
    c = ctl.add(t, refs)
    assert (c.type, c.value, c.helper) == ("dim_point_line", pytest.approx(50.0), {"side": 1})
    assert ctl.set_value(c.id, 80.0)
    assert (l1._pt1.y(), l1._pt2.y()) == pytest.approx((0.0, 0.0))
    assert (l2._pt1.y(), l2._pt2.y()) == pytest.approx((-80.0, -80.0), abs=1e-6)
    assert l2._pt1.x() == pytest.approx(20.0, abs=1e-6)


def test_collinear_lines_refused(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(150, 0), QPointF(250, 0)), "_draw_lines")
    assert ctl.dim_precheck([R(l1, "edge"), R(l2, "edge")]) is None


def test_mirror_keeps_parallel_distance_value(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, -50), QPointF(100, -50)), "_draw_lines")
    t, refs = ctl.dim_precheck([R(l1, "edge"), R(l2, "edge")])
    c = ctl.add(t, refs)

    def flip(p):
        return QPointF(p.x(), -p.y())
    with ctl.edit([l1, l2], point_map=flip):
        for ln in (l1, l2):
            ln._pt1, ln._pt2 = flip(ln._pt1), flip(ln._pt2)
            ln.setLine(ln._pt1.x(), ln._pt1.y(), ln._pt2.x(), ln._pt2.y())
    assert c.helper["side"] == -1 and l2._pt1.y() == pytest.approx(50.0, abs=1e-6)


def test_rotate_carries_the_radial_leader(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    d = ctl.add("dim_diameter", [R(c, "curve")], label={"angle": 10.0})

    def rot90(p):                                  # +90 deg Y-up about the origin
        return QPointF(p.y(), -p.x())
    with ctl.edit([c], point_map=rot90):
        c._center = rot90(c._center); c.set_radius(c._radius)
    assert d.label["angle"] == pytest.approx(100.0, abs=1e-6)
