"""CS5 dim geometry / classification / entries / readout retirement
(parametric-constraint-system D68-D78, D81). Real block-editor scenes."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import constraint_dims as cd
from firepro3d import sketch_model as sm
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RegularPolygonItem)
from firepro3d.model_space import Model_Space


def _sc():
    return Model_Space(scene_role="block_editor")


def _add(sc, it, lst):
    sc.addItem(it); getattr(sc, lst).append(it); return it


def R(it, h):
    return {"uid": it._uid, "h": h}


def test_classify_curve_picks(qapp):
    sc = _sc()
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    a = _add(sc, ArcItem(QPointF(200, 0), 40, 20, 120), "_draw_arcs")
    by = sc.constraint_ctl.item_by_uid()
    assert cd.classify_dim([R(c, "curve")], by) == ("dim_diameter", [R(c, "curve")])
    assert cd.classify_dim([R(a, "curve")], by) == ("dim_radius", [R(a, "curve")])
    assert cd.classify_dim([R(a, "center"), R(a, "curve")], by) == (
        "dim_arc_angle", [R(a, "curve")])


def test_classify_polygon_and_ellipse_radius(qapp):
    sc = _sc()
    pi = _add(sc, RegularPolygonItem(QPointF(0, 0), 6, 60.0, 0.0, True), "_draw_polygons")
    pc = _add(sc, RegularPolygonItem(QPointF(300, 0), 6, 60.0, 0.0, False), "_draw_polygons")
    e = _add(sc, EllipseItem(QPointF(600, 0), 80, 45, 15), "_draw_ellipses")
    by = sc.constraint_ctl.item_by_uid()
    assert cd.classify_dim([R(pi, "center"), R(pi, "v3")], by) == ("dim_radius", [R(pi, "radius")])
    assert cd.classify_dim([R(pi, "m3"), R(pi, "center")], by)[0] == "dim_distance"
    assert cd.classify_dim([R(pc, "center"), R(pc, "m2")], by) == ("dim_radius", [R(pc, "radius")])
    assert cd.classify_dim([R(e, "a1"), R(e, "center")], by) == ("dim_radius", [R(e, "rx")])
    assert cd.classify_dim([R(e, "center"), R(e, "b0")], by) == ("dim_radius", [R(e, "ry")])


def test_classify_angles_and_measure(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 0), QPointF(50, -86.6025403784)), "_draw_lines")
    by = ctl.item_by_uid()
    t, refs = cd.classify_dim([R(l1, "edge"), R(l2, "edge")], by)
    assert t == "dim_angle" and refs == [R(l1, "edge"), R(l2, "edge")]
    c = sm.Constraint.new(t, refs)
    # cursor inside the 60 deg sector (above the X axis between the lines)
    c.helper, _lab = cd.placement_for(ctl, t, refs, QPointF(60, -30))
    assert ctl.measure(c) == pytest.approx(60.0, abs=1e-6)
    c.helper, _lab = cd.placement_for(ctl, t, refs, QPointF(-60, -30))   # the 120 sector
    assert ctl.measure(c) == pytest.approx(120.0, abs=1e-6)
    ax = sm.Constraint.new("dim_angle", [R(l2, "edge"), {"ref": "x_axis"}])
    ax.helper, _lab = cd.placement_for(ctl, "dim_angle", ax.refs, QPointF(60, -30))
    assert ctl.measure(ax) == pytest.approx(60.0, abs=1e-6)


def test_parallel_edges_classify_as_linear(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(20, -50), QPointF(120, -50)), "_draw_lines")
    l3 = _add(sc, LineItem(QPointF(0, 40), QPointF(100, 40)), "_draw_lines")
    by = ctl.item_by_uid()
    assert cd.classify_dim([R(l1, "edge"), R(l2, "edge")], by) == (
        "dim_point_line", [R(l2, "mid"), R(l1, "edge")])
    assert cd.classify_dim([R(l3, "edge"), {"ref": "x_axis"}], by) == (
        "dim_point_line", [R(l3, "mid"), {"ref": "x_axis"}])
    c = sm.Constraint.new("dim_point_line", [R(l2, "mid"), R(l1, "edge")],
                          helper={"side": 1})
    assert ctl.measure(c) == pytest.approx(50.0)
    a, b = ctl.dim_ends(c)                                  # (foot, point)
    assert (a.x(), a.y(), b.x(), b.y()) == pytest.approx((70.0, 0.0, 70.0, -50.0))


def test_measure_key_one_per_measure(qapp):
    sc = _sc()
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(0, 0), QPointF(0, -100)), "_draw_lines")
    by = sc.constraint_ctl.item_by_uid()
    k = lambda t, refs: cd.measure_key(sm.Constraint.new(t, refs), by)   # noqa: E731
    assert k("dim_radius", [R(c, "curve")]) == k("dim_diameter", [R(c, "curve")])
    assert k("dim_angle", [R(l1, "edge"), R(l2, "edge")]) == k(
        "dim_angle", [R(l2, "edge"), R(l1, "edge")])
    assert k("dim_angle", [R(l1, "edge"), {"ref": "x_axis"}]) != k(
        "dim_angle", [R(l1, "edge"), {"ref": "y_axis"}])


def test_readout_for_diameter_doubles_and_halves(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    d = sm.Constraint.new("dim_diameter", [R(c, "curve")])
    it, spec = cd.readout_for(ctl, d)
    assert it is c and spec.value == pytest.approx(60.0) and spec.prefix == "Ø"
    spec.apply(50.0)
    assert c._radius == pytest.approx(25.0)


@pytest.mark.parametrize("make", [
    lambda: CircleItem(QPointF(0, 0), 30),
    lambda: ArcItem(QPointF(0, 0), 40, 20, 120),
    lambda: RegularPolygonItem(QPointF(0, 0), 6, 60.0),
    lambda: EllipseItem(QPointF(0, 0), 80, 45, 15),
])
def test_block_editor_selection_shows_no_readouts(qapp, make):
    sc = _sc()
    it = make(); sc.addItem(it)
    it.setSelected(True)
    assert it.dimension_specs()                     # items still report specs (D68)
    assert sc.readouts.entries() == []
    sc.readouts.show_dim_readouts = True            # the machinery is not broken
    assert sc.readouts.entries()


def test_off_vertex_angle_extension_reaches_the_arc(qapp):
    from firepro3d.model_view import Model_View
    sc = _sc(); ctl = sc.constraint_ctl
    V = QPointF(0, -70)

    def up(r, deg):
        a = math.radians(deg)
        return QPointF(V.x() + r * math.cos(a), V.y() - r * math.sin(a))
    la = _add(sc, LineItem(up(140, 220), up(200, 220)), "_draw_lines")
    lb = _add(sc, LineItem(up(40, 320), up(90, 320)), "_draw_lines")
    v = Model_View(sc); v.resize(500, 400); v.show(); qapp.processEvents()
    v.resetTransform(); v.centerOn(0, 0); qapp.processEvents()
    refs = [R(la, "edge"), R(lb, "edge")]
    h, _ = cd.placement_for(ctl, "dim_angle", refs, up(100, 270))
    c = ctl.add("dim_angle", refs, helper=h)
    e = cd.entry_for(v, ctl, c)
    (C, r, _st, _sp), = e.graphic.arcs
    assert e.graphic.dashed                                   # edge A is missed
    s, t = e.graphic.dashed[0]
    assert math.hypot(t.x() - C.x(), t.y() - C.y()) == pytest.approx(r, abs=0.6)
    A1 = v.viewportTransform().map(up(140, 220))
    assert (s.x(), s.y()) == pytest.approx((A1.x(), A1.y()), abs=0.6)
    v.close()


def test_polyline_corner_readout_retired(qapp):
    sc = _sc()
    pl = PolylineItem(QPointF(0, 0)); pl.append_point(QPointF(100, 0))
    pl.append_point(QPointF(100, -80))
    _add(sc, pl, "_polylines"); pl.setSelected(True)
    assert any(s.key.startswith("ang:") for s in pl.dimension_specs())
    assert sc.readouts.entries() == []
    sc.readouts.show_dim_readouts = True             # machinery opt-in still works
    assert any(s.key.startswith("ang:") for _i, s in sc.readouts.entries())


# ── CS5 T4-5 review fix round ───────────────────────────────────────────


def _polygon_hit(inscribed):
    sc = _sc(); ctl = sc.constraint_ctl
    pg = _add(sc, RegularPolygonItem(QPointF(5, 7), 6, 60.0, 17.0, inscribed),
              "_draw_polygons")
    c = sm.Constraint.new("dim_radius", [R(pg, "radius")])
    g = cd.dim_geom(ctl, c)
    return pg, cd._radial_points(g, 20.0)[0]


def test_circumscribed_polygon_leader_hits_a_side_midpoint(qapp):
    pg, hit = _polygon_hit(False)
    vs = pg.vertices()
    mids = [QPointF((vs[k].x() + vs[(k + 1) % 6].x()) / 2,
                    (vs[k].y() + vs[(k + 1) % 6].y()) / 2) for k in range(6)]
    assert min(math.hypot(hit.x() - m.x(), hit.y() - m.y()) for m in mids) < 1e-6


def test_inscribed_polygon_leader_hits_a_vertex(qapp):
    pg, hit = _polygon_hit(True)
    assert min(math.hypot(hit.x() - v.x(), hit.y() - v.y()) for v in pg.vertices()) < 1e-6


def test_point_line_key_ignores_pick_order(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    l1 = _add(sc, LineItem(QPointF(0, 0), QPointF(100, 0)), "_draw_lines")
    l2 = _add(sc, LineItem(QPointF(20, -50), QPointF(120, -50)), "_draw_lines")
    t, refs = ctl.dim_precheck([R(l1, "edge"), R(l2, "edge")])
    assert ctl.add(t, refs) is not None
    msgs = []
    ctl._status = msgs.append
    assert ctl.dim_precheck([R(l2, "edge"), R(l1, "edge")]) is None
    assert msgs and "Already dimensioned" in msgs[-1]


def test_entry_for_without_a_readout_spec_is_none(qapp):
    from firepro3d.model_view import Model_View
    sc = _sc(); ctl = sc.constraint_ctl
    c = _add(sc, CircleItem(QPointF(0, 0), 30), "_draw_circles")
    d = ctl.add("dim_diameter", [R(c, "curve")], label={"angle": 20.0})
    v = Model_View(sc)
    assert cd.entry_for(v, ctl, d) is not None
    c.dimension_specs = lambda: []
    assert cd.entry_for(v, ctl, d) is None
    v.close()
