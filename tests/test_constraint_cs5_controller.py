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


# ── CS5 T4-5 review fix round ───────────────────────────────────────────


def _flip(p):
    return QPointF(p.x(), -p.y())


def _mirror_copy(sc, ctl, srcs, make_copies):
    """Mirror-copy *srcs* across the X axis the way the Mirror tool does:
    reflected copies exist, then paste_records gets the reflection."""
    copies = make_copies()
    uid_map = {s._uid: c._uid for s, c in zip(srcs, copies)}
    n = len(ctl.constraints)
    ctl.paste_records(ctl.internal_records(srcs), uid_map,
                      mirror_axis=(QPointF(0, 0), QPointF(1, 0)), point_map=_flip)
    return ctl.constraints[n:]


def test_mirror_copy_mirrors_the_radial_leader(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(100, 50), 30), "_draw_circles")
    ctl.add("dim_diameter", [R(c, "curve")], label={"angle": 10.0})
    (new,) = _mirror_copy(sc, ctl, [c], lambda: [
        _add(sc, CircleItem(QPointF(100, -50), 30), "_draw_circles")])
    assert new.type == "dim_diameter" and not new.inert
    assert new.label["angle"] == pytest.approx(-10.0, abs=1e-6)
    assert new.id not in ctl.red


def test_mirror_copy_of_angle_and_point_line_keeps_value(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 0), QPointF(50, -86.6025403784)), "_draw_lines")
    m1 = _add(sc, LineItem(QPointF(0, 200), QPointF(100, 200)), "_draw_lines")
    m2 = _add(sc, LineItem(QPointF(20, 150), QPointF(120, 150)), "_draw_lines")
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(60, -20))
    ang = ctl.add("dim_angle", refs, helper=h)
    t, prefs = ctl.dim_precheck([R(m1, "edge"), R(m2, "edge")])
    pl = ctl.add(t, prefs)
    srcs = [l1, l2, m1, m2]

    def copies():
        return [_add(sc, LineItem(_flip(s._pt1), _flip(s._pt2)), "_draw_lines")
                for s in srcs]
    new = _mirror_copy(sc, ctl, srcs, copies)
    assert {x.type for x in new} == {"dim_angle", "dim_point_line"}
    pairs = zip(sorted(new, key=lambda x: x.type), sorted((ang, pl), key=lambda x: x.type))
    for x, src in pairs:
        assert not x.inert and x.id not in ctl.red
        assert ctl.measure(x) == pytest.approx(ctl.measure(src), abs=1e-6)


def test_polar_array_copy_turns_the_radial_leader(qapp):
    from firepro3d.constraint_dims import point_map_like
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(100, 0), 30), "_draw_circles")
    ctl.add("dim_diameter", [R(c, "curve")], label={"angle": 10.0})
    centre = QPointF(0, 0)
    turn = 90.0
    # exactly the Polar Array tool's calls (ModifyToolsController.commit_array)
    records = sc._clipboard_item_dicts([c])
    cons = ctl.internal_records([c])
    new = sc.paste_items(QPointF(0, 0), data=records, constraints=cons,
                         rotation_deg=turn) or []
    with ctl.edit(new):
        for it in new:
            it.manip_rotate(turn, QPointF(centre))
    (copy,) = [x for x in new if isinstance(x, CircleItem)]
    d2 = [x for x in ctl.constraints if x.refs[0].get("uid") == copy._uid]
    assert len(d2) == 1
    # ground truth: the source's hit point carried by the tool's own rotate
    a = math.radians(10.0)
    hit = QPointF(100 + 30 * math.cos(a), -30 * math.sin(a))
    q = point_map_like(lambda it: it.manip_rotate(turn, QPointF(centre)))(hit)
    want = math.degrees(math.atan2(-(q.y() - copy._center.y()), q.x() - copy._center.x()))
    assert (d2[0].label["angle"] - want + 180.0) % 360.0 - 180.0 == pytest.approx(0.0, abs=1e-6)


def test_cancel_dim_drag_restores_sector_value_and_label(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 0), QPointF(50, -86.6025403784)), "_draw_lines")
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(60, -20))
    c = ctl.add("dim_angle", refs, helper=h)
    v0, h0, l0 = c.value, dict(c.helper), c.label
    assert ctl.drag_dim_to_scene(c.id, QPointF(-60, -20))
    assert c.value == pytest.approx(120.0, abs=1e-6) and c.helper != h0
    assert ctl.cancel_dim_drag()
    assert c.value == pytest.approx(v0) and c.helper == h0 and c.label == l0
    circ = _add(sc, CircleItem(QPointF(300, 0), 30), "_draw_circles")
    d = ctl.add("dim_diameter", [R(circ, "curve")], label={"angle": 10.0})
    assert ctl.drag_dim_to_scene(d.id, QPointF(300, 100))
    assert d.label["angle"] != 10.0
    assert ctl.cancel_dim_drag() and d.label == {"angle": 10.0}


def test_begin_dim_drag_ignores_non_dims(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    ln = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 10)), "_draw_lines")
    h = ctl.add("horizontal", [R(ln, "edge")])
    ctl.begin_dim_drag(h.id, QPointF(0, 0))
    assert ctl.dim_drag is None


def test_dim_text_prefixes_and_reference_parentheses(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    e = _add(sc, EllipseItem(QPointF(300, 0), 80, 45, 15), "_draw_ellipses")
    arc = _add(sc, ArcItem(QPointF(0, 1200), 20, 0, 90), "_draw_arcs")
    l1 = _add(sc, LineItem(QPointF(0, 500), QPointF(100, 500)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 500), QPointF(50, 500 - 86.6025403784)), "_draw_lines")
    r = ctl.add("dim_radius", [R(c, "curve")])
    ctl.set_dim_kind(r.id, "dim_diameter")
    r1 = ctl.add("dim_radius", [R(e, "rx")])
    rr = ctl.add("dim_radius", [R(arc, "curve")])
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(60, 480))
    a = ctl.add("dim_angle", refs, helper=h)
    assert ctl.dim_text(r).startswith("Smart Dimension · Ø ")
    assert ctl.dim_text(r1).startswith("Smart Dimension · R1 ")
    assert ctl.dim_text(rr).startswith("Smart Dimension · R ")
    assert ctl.dim_text(a).endswith("60°")
    ctl.set_driving(a.id, False)
    assert ctl.dim_text(a).endswith("(60°)")
    ctl.set_driving(r.id, False)
    t = ctl.dim_text(r)
    assert t == "Smart Dimension · (Ø 60.000 mm)"


def test_adapter_show_as_and_angle_value_field(qapp):
    from firepro3d.constraint_controller import ConstraintAdapter
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    pg = _add(sc, RegularPolygonItem(QPointF(300, 0), 6, 60.0), "_draw_polygons")
    e = _add(sc, EllipseItem(QPointF(600, 0), 80, 45, 15), "_draw_ellipses")
    dc = ctl.add("dim_radius", [R(c, "curve")])
    dp = ctl.add("dim_radius", [R(pg, "radius")])
    de = ctl.add("dim_radius", [R(e, "rx")])
    props = ConstraintAdapter(ctl, dc).get_properties()
    assert props["Show as"] == {"type": "enum", "options": ["Radius", "Diameter"],
                                "value": "Radius"}
    assert "Show as" not in ConstraintAdapter(ctl, dp).get_properties()
    assert "Show as" not in ConstraintAdapter(ctl, de).get_properties()
    ConstraintAdapter(ctl, dc).set_property("Show as", "Diameter")
    assert dc.type == "dim_diameter" and dc.value == pytest.approx(60.0)
    l1, l2 = _vee(sc)
    refs = [R(l1, "edge"), R(l2, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, QPointF(30, -30))
    a = ctl.add("dim_angle", refs, helper=h)
    v = ConstraintAdapter(ctl, a).get_properties()["Value"]
    assert v["type"] == "string" and v["suffix"] == "°"
    ConstraintAdapter(ctl, a).set_property("Value", "75")
    assert ctl.measure(a) == pytest.approx(75.0, abs=1e-6)


def test_invalid_cs5_records_load_inert(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 50), QPointF(100, 50)), "_draw_lines")
    l3, l4 = _vee(sc)
    ci = _add(sc, CircleItem(QPointF(500, 0), 30), "_draw_circles")
    ar = _add(sc, ArcItem(QPointF(800, 0), 30, 0, 90), "_draw_arcs")
    good = [
        {"type": "dim_point_line", "refs": [R(l2, "mid"), R(l1, "edge")],
         "value": 50.0, "helper": {"side": 1}},
        {"type": "dim_arc_angle", "refs": [R(ar, "curve")], "value": 90.0},
        {"type": "dim_angle", "refs": [R(l3, "edge"), R(l4, "edge")], "value": 90.0,
         "helper": {"dirs": [1, 1], "sign": -1}},
    ]
    ctl.load([dict(g, id=f"g{i}") for i, g in enumerate(good)])
    assert [x.inert for x in ctl.constraints] == [False, False, False]
    bad = [
        dict(good[0], helper={"side": 2}),
        dict(good[0], helper={"side": True}),
        dict(good[1], refs=[R(ci, "curve")]),
        dict(good[1], value=360.0),
        dict(good[2], value=180.0),
    ]
    for i, b in enumerate(bad):
        ctl.load([dict(b, id=f"b{i}")])
        assert ctl.constraints[0].inert, bad[i]
