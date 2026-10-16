"""CS15 Smart Dimension point-line guards (D133-D136): real Block Editor
scenes, real solve."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import constraint_dims as cd
from firepro3d import sketch_model as sm
from firepro3d.constraint_controller import (DIM_COLLINEAR_STATUS, DIM_POINT_ON_LINE_STATUS,
                                             DIM_REPEAT_STATUS, PickState)
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.model_space import Model_Space


def _sc():
    sc = Model_Space(scene_role="block_editor")
    sc._msgs = []
    sc._show_status = lambda msg, timeout=5000: sc._msgs.append(msg)
    return sc


def _add(sc, it, lst):
    sc.addItem(it); getattr(sc, lst).append(it); return it


def _line(sc, a, b):
    return _add(sc, LineItem(QPointF(*a), QPointF(*b)), "_draw_lines")


def R(it, h):
    return {"uid": it._uid, "h": h}


def test_point_then_edge_and_axis_classify_point_line(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (200, 0))
    c = _add(sc, CircleItem(QPointF(50, -80), 10), "_draw_circles")
    by = ctl.item_by_uid()
    assert cd.classify_dim([R(c, "center"), R(ln, "edge")], by) == (
        "dim_point_line", [R(c, "center"), R(ln, "edge")])
    assert cd.classify_dim([R(c, "center"), {"ref": "y_axis"}], by) == (
        "dim_point_line", [R(c, "center"), {"ref": "y_axis"}])
    d = ctl.add(*ctl.dim_precheck([R(c, "center"), R(ln, "edge")]))
    # cross(p - a, d) = 50*0 - (-80)*200 > 0 -> side +1; distance = |y| = 80
    assert (d.type, d.value, d.helper) == ("dim_point_line", pytest.approx(80.0), {"side": 1})
    dx = ctl.add(*ctl.dim_precheck([R(c, "center"), {"ref": "x_axis"}]))
    dy = ctl.add(*ctl.dim_precheck([R(c, "center"), {"ref": "y_axis"}]))
    assert (dx.value, dy.value) == (pytest.approx(80.0), pytest.approx(50.0))


def test_measure_key_folds_only_a_parallel_midpoint(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0))
    b = _line(sc, (0, -50), (100, -120))                 # not parallel to a
    p = _line(sc, (0, -50), (100, -50))                  # parallel to a
    by = ctl.item_by_uid()
    k = lambda refs: cd.measure_key(sm.Constraint.new("dim_point_line", refs), by)  # noqa: E731
    assert k([R(a, "mid"), R(b, "edge")]) != k([R(b, "mid"), R(a, "edge")])
    assert k([R(p, "mid"), R(a, "edge")]) == k([R(a, "mid"), R(p, "edge")])
    assert ctl.add("dim_point_line", [R(a, "mid"), R(b, "edge")]) is not None
    assert ctl.add("dim_point_line", [R(b, "mid"), R(a, "edge")]) is not None   # another measure
    assert ctl.add(*ctl.dim_precheck([R(a, "edge"), R(p, "edge")])) is not None  # D81 pair
    assert ctl.add("dim_point_line", [R(a, "mid"), R(p, "edge")]) is None       # same measure
    assert sc._msgs[-1] == DIM_REPEAT_STATUS


def test_after_a_point_edges_and_axes_are_offered(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    _line(sc, (0, 0), (200, 0))
    c = _add(sc, CircleItem(QPointF(50, -80), 10), "_draw_circles")
    p = PickState(ctl, "dim_distance")
    assert {k for k, r, _a, _b in p._candidates() if p._allowed(k, r)} == {"point", "edge", "curve"}
    p.picks, p.kinds = [R(c, "center")], ["point"]
    assert {k for k, r, _a, _b in p._candidates() if p._allowed(k, r)} == {"point", "edge", "axis"}
    assert "line / axis" in p.status()
    assert "arc for its angle" not in p.status()          # a circle centre is no sweep pick


def test_typed_value_holds_the_line_and_moves_the_point(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (200, 0))
    c = _add(sc, CircleItem(QPointF(50, -80), 10), "_draw_circles")
    l2 = _line(sc, (50, -80), (150, -150))
    d1 = ctl.add(*ctl.dim_precheck([R(c, "center"), R(ln, "edge")]))
    assert ctl.set_value(d1.id, 120.0)
    assert (c._center.x(), c._center.y(), c._radius) == pytest.approx((50.0, -120.0, 10.0), abs=1e-6)
    assert (ln._pt1.x(), ln._pt1.y(), ln._pt2.x(), ln._pt2.y()) == pytest.approx((0, 0, 200, 0), abs=1e-9)
    d2 = ctl.add(*ctl.dim_precheck([R(l2, "p1"), R(ln, "edge")]))
    assert d2.value == pytest.approx(80.0)
    assert ctl.set_value(d2.id, 30.0)
    assert (l2._pt1.x(), l2._pt1.y()) == pytest.approx((50.0, -30.0), abs=1e-6)
    assert (l2._pt2.x(), l2._pt2.y()) == pytest.approx((150.0, -150.0), abs=1e-6)
    assert (ln._pt1.y(), ln._pt2.y()) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_typed_value_on_an_adjacent_side_midpoint_is_least_change(qapp):
    from firepro3d.geometry_2d import PolylineItem
    sc = _sc(); ctl = sc.constraint_ctl
    pl = PolylineItem(QPointF(0, 0))
    for q in (QPointF(100, 0), QPointF(100, -100)):
        pl.append_point(q)
    _add(sc, pl, "_polylines")
    d = ctl.add("dim_point_line", [R(pl, "m1"), R(pl, "s0")])
    assert d.value == pytest.approx(50.0)                # mid of s1 = (100, -50)
    assert ctl.set_value(d.id, 30.0)                     # s1 shares v1 with s0
    assert ctl.measure(d) == pytest.approx(30.0, abs=1e-6)


@pytest.mark.parametrize("through", [True, False])
def test_flip_of_an_origin_point_line_dim(qapp, through):
    """D137: a mirror through the origin keeps an origin -> line dim; any
    other mirror is refused whole (the origin is never reflected, D76) --
    held by the solve honouring the transform's edited vars, not by a D76
    helper rule."""
    from tests.test_constraint_cs5_controller import _flip_across
    sc = _sc(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, -60), (100, -60))
    c = ctl.add(*ctl.dim_precheck([{"ref": "origin"}, R(ln, "edge")]))
    assert c.value == pytest.approx(60.0)
    if through:
        _flip_across(sc, [ln], (-500, 0), (800, 0))      # the X axis line: y -> -y
        assert (ln._pt1.y(), ln._pt2.y()) == pytest.approx((60.0, 60.0), abs=1e-5)
        assert (ln._pt1.x(), ln._pt2.x()) == pytest.approx((0.0, 100.0), abs=1e-5)
    else:
        _flip_across(sc, [ln], (-500, -100), (800, -100))  # y = -100: misses the origin
        assert (ln._pt1.y(), ln._pt2.y()) == pytest.approx((-60.0, -60.0), abs=1e-9)
    assert c.id not in ctl.red
    assert ctl.measure(c) == pytest.approx(60.0, abs=1e-6)


def test_point_on_the_line_is_refused_parallel_keeps_collinear(qapp):
    sc = _sc(); ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (200, 0))
    c = _add(sc, CircleItem(QPointF(100, 0), 10), "_draw_circles")
    l2 = _line(sc, (300, 0), (400, 0))                   # collinear with ln
    assert ctl.dim_precheck([R(ln, "p1"), R(ln, "edge")]) is None
    assert sc._msgs[-1] == DIM_POINT_ON_LINE_STATUS
    assert ctl.dim_precheck([R(c, "center"), R(ln, "edge")]) is None
    assert sc._msgs[-1] == DIM_POINT_ON_LINE_STATUS
    assert ctl.dim_precheck([R(ln, "edge"), R(l2, "edge")]) is None
    assert sc._msgs[-1] == DIM_COLLINEAR_STATUS
