"""CS10 Perpendicular -- controller (spec §7.3, §8; rulings PP1-PP5).

Real ``Model_Space(scene_role="block_editor")`` + real primitives; asserts
the solved geometry, records and status.
"""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _rect(sc, a, b):
    r = RectangleItem(QPointF(*a), QPointF(*b)); sc.addItem(r); sc._draw_rects.append(r)
    return r


def _status(sc):
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    return msgs


def P(it, h):
    return {"uid": it._uid, "h": h}


def _cos(a, b):
    u = (a._pt2.x() - a._pt1.x(), a._pt2.y() - a._pt1.y())
    v = (b._pt2.x() - b._pt1.x(), b._pt2.y() - b._pt1.y())
    return (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))


def _len(a):
    return math.hypot(a._pt2.x() - a._pt1.x(), a._pt2.y() - a._pt1.y())


def _pick_view(sc):
    from firepro3d.model_view import Model_View
    v = Model_View(sc)
    v.resize(800, 600)
    v.resetTransform()
    v.centerOn(0, 0)
    return v


def _press(ctl, v, x, y):
    return ctl.pick_press(v, QPointF(v.mapFromScene(QPointF(x, y))))


def test_perpendicular_near_perpendicular_lines_solve(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (17.6, 150))
    c = sc.constraint_ctl.add("perpendicular", [P(a, "edge"), P(b, "edge")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert abs(_cos(a, b)) < 1e-9


@pytest.mark.parametrize("b_ends", [((0, 50), (100, 50)),        # exactly parallel
                                    ((100, 50), (0, 50)),        # anti-parallel
                                    ((0, 50), (100, 67.6)),      # 10 deg
                                    ((0, 50), (100, 150))])      # 45 deg
def test_perpendicular_rotates_and_keeps_lengths(qapp, b_ends):
    """PP5: the rotate-first pass turns the edges; neither shrinks."""
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, *b_ends)
    la, lb = _len(a), _len(b)
    c = sc.constraint_ctl.add("perpendicular", [P(a, "edge"), P(b, "edge")])
    assert c.id not in sc.constraint_ctl.red
    assert abs(_cos(a, b)) < 1e-9
    assert _len(a) == pytest.approx(la, abs=1e-6) and _len(b) == pytest.approx(lb, abs=1e-6)


def test_perpendicular_short_line_turns_most(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (200, 0)); b = _line(sc, (0, 50), (50, 50))
    sc.constraint_ctl.add("perpendicular", [P(a, "edge"), P(b, "edge")])
    ta = abs(math.degrees(math.atan2(a._pt2.y() - a._pt1.y(), a._pt2.x() - a._pt1.x())))
    assert ta < 10.0 and abs(_cos(a, b)) < 1e-9


def test_perpendicular_line_to_x_axis_turns_vertical_keeping_length(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (100, 12))
    la = _len(a)
    sc.constraint_ctl.add("perpendicular", [P(a, "edge"), {"ref": "x_axis"}])
    assert a._pt1.x() == pytest.approx(a._pt2.x(), abs=1e-6)
    assert _len(a) == pytest.approx(la, abs=1e-6)


def test_perpendicular_to_y_axis_beside_horizontal_is_redundant_amber(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [P(a, "edge")])
    c = ctl.add("perpendicular", [P(a, "edge"), {"ref": "y_axis"}])
    assert c.id in ctl.diagnostics().redundant and c.id not in ctl.red


def test_perpendicular_plus_parallel_on_one_pair_is_red_and_held(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (100, 50))
    ctl.add("parallel", [P(a, "edge"), P(b, "edge")])
    before = [(p.x(), p.y()) for p in (a._pt1, a._pt2, b._pt1, b._pt2)]
    c = ctl.add("perpendicular", [P(a, "edge"), P(b, "edge")])
    assert c.id in ctl.red
    assert [(p.x(), p.y()) for p in (a._pt1, a._pt2, b._pt1, b._pt2)] == before


def test_perpendicular_rect_adjacent_sides_refused_as_trivial(qapp):
    from firepro3d.constraint_controller import PERPENDICULAR_TRIVIAL_STATUS
    sc = _scene()
    msgs = _status(sc)
    r = _rect(sc, (0, 0), (40, 30))
    assert sc.constraint_ctl.add("perpendicular", [P(r, "top"), P(r, "left")]) is None
    assert msgs[-1] == PERPENDICULAR_TRIVIAL_STATUS == (
        "Those edges are already perpendicular by construction -- pick another edge")
    assert sc.constraint_ctl.constraints == []


def test_perpendicular_square_polygon_adjacent_sides_refused(qapp):
    from firepro3d.constraint_controller import PERPENDICULAR_TRIVIAL_STATUS
    from firepro3d.geometry_2d import RegularPolygonItem
    sc = _scene()
    msgs = _status(sc)
    pg = RegularPolygonItem(QPointF(0, 0), 4, 50.0); sc.addItem(pg); sc._draw_polygons.append(pg)
    assert sc.constraint_ctl.add("perpendicular", [P(pg, "s0"), P(pg, "s1")]) is None
    assert msgs[-1] == PERPENDICULAR_TRIVIAL_STATUS


def test_perpendicular_rect_opposite_sides_admitted_red(qapp):
    sc = _scene()
    r = _rect(sc, (0, 0), (40, 30))
    c = sc.constraint_ctl.add("perpendicular", [P(r, "top"), P(r, "bottom")])
    assert c is not None and c.id in sc.constraint_ctl.red


def test_perpendicular_copies_keep_edge_pair_drop_axis(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (0, 150))
    ctl.add("perpendicular", [P(a, "edge"), P(b, "edge")])
    ctl.add("perpendicular", [P(b, "edge"), {"ref": "x_axis"}])
    recs = ctl.internal_records([a, b])
    a2 = _line(sc, (300, 0), (400, 0)); b2 = _line(sc, (300, 50), (300, 150))
    ctl.paste_records(recs, {a._uid: a2._uid, b._uid: b2._uid},
                      mirror_axis=(QPointF(150, 0), QPointF(160, 37)))
    got = ctl.constraints_on(a2)
    assert [c.type for c in got] == ["perpendicular"] and not got[0].invalid
    assert got[0].refs == [P(a2, "edge"), P(b2, "edge")]
    a3 = _line(sc, (0, 300), (0, 400)); b3 = _line(sc, (50, 300), (150, 300))
    ctl.paste_records(recs, {a._uid: a3._uid, b._uid: b3._uid}, rotation_deg=90.0)
    assert [c.type for c in ctl.constraints_on(a3)] == ["perpendicular"]


def test_perpendicular_pick_kinds_and_status(qapp):
    from firepro3d.constraint_controller import PickState
    from firepro3d.geometry_2d import CircleItem
    sc = _scene()
    it = CircleItem(QPointF(0, 0), 20); sc.addItem(it); sc._draw_circles.append(it)
    p = PickState(sc.constraint_ctl, "perpendicular")
    kinds = {k for k, *_ in p._candidates()}
    assert "axis" in kinds and "curve" not in kinds
    assert p._allowed("edge") and p._allowed("axis") and not p._allowed("point")
    p.picks, p.kinds = [{"ref": "x_axis"}], ["axis"]
    assert p._allowed("edge") and not p._allowed("axis")
    assert p.status() == "Perpendicular: pick an edge (1/2) · Esc to cancel"
    p.picks, p.kinds = [{"uid": "u", "h": "edge"}], ["edge"]
    assert p.status() == ("Perpendicular: pick an edge, then an edge or the X/Y axis"
                          " (1/2) · Esc to cancel")


def test_perpendicular_pick_flow_axis_first_stores_edge_first(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (-60, 40), (60, 70))
    v = _pick_view(sc)
    sc.set_mode("constrain_perpendicular")
    assert not _press(ctl, v, 200, 0)                       # the X axis
    assert _press(ctl, v, 30, 62.5)                         # the edge
    (c,) = ctl.constraints
    assert c.refs == [P(a, "edge"), {"ref": "x_axis"}]
    assert a._pt1.x() == pytest.approx(a._pt2.x(), abs=1e-6)


def test_perpendicular_repeated_edge_says_pick_a_different_edge(qapp):
    from firepro3d.constraint_controller import PICK_SAME_EDGE_STATUS
    sc = _scene()
    ctl = sc.constraint_ctl
    _line(sc, (-80, -50), (-40, 50))
    v = _pick_view(sc)
    msgs = _status(sc)
    sc.set_mode("constrain_perpendicular")
    _press(ctl, v, -50, 25)
    assert _press(ctl, v, -50, 25) is False
    assert msgs[-1] == PICK_SAME_EDGE_STATUS
    assert ctl.constraints == [] and len(ctl.pick.picks) == 1


def test_selection_refs_perpendicular_two_lines_only(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (50, 0)); b = _line(sc, (0, 40), (50, 60))
    a.setSelected(True)
    assert ctl.selection_refs("perpendicular") is None
    b.setSelected(True)
    assert sorted(r["uid"] for r in ctl.selection_refs("perpendicular")) == sorted([a._uid, b._uid])
    r = _rect(sc, (100, 100), (140, 130)); r.setSelected(True)
    assert ctl.selection_refs("perpendicular") is None


def test_rotate_first_falls_back_to_the_plain_solve_when_turning_cannot_satisfy(qapp):
    """PP5 fallback (T3 review Minor 2): b's start is fixed and its end rides a
    fixed horizontal guide, so b can only become vertical by shortening -- the
    length-holding pass fails and the plain least change still applies it."""
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0))
    guide = _line(sc, (-200, 50), (200, 50))
    b = _line(sc, (0, 0), (100, 50))
    ctl.add("fix", [{"uid": a._uid, "h": "item"}])
    ctl.add("fix", [{"uid": guide._uid, "h": "item"}])
    ctl.add("fix", [P(b, "p1")])
    ctl.add("point_on_curve", [P(b, "p2"), P(guide, "edge")])
    c = ctl.add("perpendicular", [P(a, "edge"), P(b, "edge")])
    assert c.id not in ctl.red
    assert abs(_cos(a, b)) < 1e-9
    assert (b._pt2.x(), b._pt2.y()) == pytest.approx((0.0, 50.0), abs=1e-6)


def test_rotate_first_pass_leaves_no_temporary_records(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (100, 50))
    ctl.add("perpendicular", [P(a, "edge"), P(b, "edge")])
    assert [c.type for c in ctl.constraints] == ["perpendicular"]
    assert ctl.diagnostics().dof == 8 - 1     # two free lines, one row
