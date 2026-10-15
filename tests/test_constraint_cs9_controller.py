"""CS9 Parallel -- controller (spec §7.3, §8; rulings P1-P4).

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


def _sin(a, b):
    u = (a._pt2.x() - a._pt1.x(), a._pt2.y() - a._pt1.y())
    v = (b._pt2.x() - b._pt1.x(), b._pt2.y() - b._pt1.y())
    return (u[0] * v[1] - u[1] * v[0]) / (math.hypot(*u) * math.hypot(*v))


def _pick_view(sc):
    from firepro3d.model_view import Model_View
    v = Model_View(sc)
    v.resize(800, 600)
    v.resetTransform()
    v.centerOn(0, 0)
    return v


def _press(ctl, v, x, y):
    return ctl.pick_press(v, QPointF(v.mapFromScene(QPointF(x, y))))


def test_parallel_two_lines_solve_parallel(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (100, 90))
    c = sc.constraint_ctl.add("parallel", [P(a, "edge"), P(b, "edge")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert abs(_sin(a, b)) < 1e-9


def test_parallel_line_to_x_axis_is_level(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (100, 12))
    sc.constraint_ctl.add("parallel", [P(a, "edge"), {"ref": "x_axis"}])
    assert a._pt1.y() == pytest.approx(a._pt2.y(), abs=1e-6)


def test_parallel_plus_horizontal_on_x_axis_line_is_redundant_amber(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [P(a, "edge")])
    c = ctl.add("parallel", [P(a, "edge"), {"ref": "x_axis"}])
    assert c.id in ctl.diagnostics().redundant and c.id not in ctl.red


def test_parallel_rect_opposite_sides_refused_as_trivial(qapp):
    from firepro3d.constraint_controller import PARALLEL_TRIVIAL_STATUS
    sc = _scene()
    msgs = _status(sc)
    r = _rect(sc, (0, 0), (40, 30))
    assert sc.constraint_ctl.add("parallel", [P(r, "top"), P(r, "bottom")]) is None
    assert msgs[-1] == PARALLEL_TRIVIAL_STATUS == (
        "Those edges are already parallel by construction -- pick another edge")
    assert sc.constraint_ctl.constraints == []


def test_parallel_rect_adjacent_sides_admitted_red(qapp):
    sc = _scene()
    r = _rect(sc, (0, 0), (40, 30))
    c = sc.constraint_ctl.add("parallel", [P(r, "top"), P(r, "left")])
    assert c is not None and c.id in sc.constraint_ctl.red


def test_parallel_copies_keep_edge_pair_drop_axis(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (100, 50))
    ctl.add("parallel", [P(a, "edge"), P(b, "edge")])
    ctl.add("parallel", [P(a, "edge"), {"ref": "x_axis"}])
    recs = ctl.internal_records([a, b])
    a2 = _line(sc, (300, 0), (400, 0)); b2 = _line(sc, (300, 50), (400, 50))
    ctl.paste_records(recs, {a._uid: a2._uid, b._uid: b2._uid},
                      mirror_axis=(QPointF(150, 0), QPointF(160, 37)))
    got = ctl.constraints_on(a2)
    assert [c.type for c in got] == ["parallel"] and not got[0].invalid
    assert got[0].refs == [P(a2, "edge"), P(b2, "edge")]
    a3 = _line(sc, (0, 300), (0, 400)); b3 = _line(sc, (50, 300), (50, 400))
    ctl.paste_records(recs, {a._uid: a3._uid, b._uid: b3._uid}, rotation_deg=90.0)
    assert [c.type for c in ctl.constraints_on(a3)] == ["parallel"]   # a rotated copy too


def test_parallel_pick_kinds_by_step(qapp):
    from firepro3d.constraint_controller import PickState
    sc = _scene()
    p = PickState(sc.constraint_ctl, "parallel")
    assert p._allowed("edge") and p._allowed("axis")
    assert not p._allowed("point") and not p._allowed("curve")
    p.picks, p.kinds = [{"ref": "x_axis"}], ["axis"]
    assert p._allowed("edge") and not p._allowed("axis")
    p.picks, p.kinds = [{"uid": "u", "h": "edge"}], ["edge"]
    assert p._allowed("edge") and p._allowed("axis")
    assert p.status() == "Parallel: pick an edge, then an edge or the X/Y axis (1/2) · Esc to cancel"


def test_parallel_axes_offered_but_no_curves(qapp):
    from firepro3d.constraint_controller import PickState
    from firepro3d.geometry_2d import CircleItem
    sc = _scene()
    it = CircleItem(QPointF(0, 0), 20); sc.addItem(it); sc._draw_circles.append(it)
    kinds = {k for k, *_ in PickState(sc.constraint_ctl, "parallel")._candidates()}
    assert "axis" in kinds and "curve" not in kinds


def test_parallel_pick_flow_axis_first_stores_edge_first(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (-60, 40), (60, 70))
    v = _pick_view(sc)
    sc.set_mode("constrain_parallel")
    assert ctl.pick.status() == ("Parallel: pick an edge, then an edge or the X/Y axis"
                                 " (0/2) · Esc to cancel")
    assert not _press(ctl, v, 200, 0)                       # the X axis
    assert ctl.pick.status() == "Parallel: pick an edge (1/2) · Esc to cancel"
    assert _press(ctl, v, 30, 62.5)                         # on the edge, off its midpoint
    (c,) = ctl.constraints
    assert c.refs == [P(a, "edge"), {"ref": "x_axis"}]
    assert a._pt1.y() == pytest.approx(a._pt2.y(), abs=1e-6)


def test_parallel_repeated_edge_says_pick_a_different_edge(qapp):
    from firepro3d.constraint_controller import PICK_SAME_EDGE_STATUS
    sc = _scene()
    ctl = sc.constraint_ctl
    _line(sc, (-80, -50), (-40, 50))
    v = _pick_view(sc)
    msgs = _status(sc)
    sc.set_mode("constrain_parallel")
    _press(ctl, v, -50, 25)
    assert _press(ctl, v, -50, 25) is False
    assert msgs[-1] == PICK_SAME_EDGE_STATUS
    assert ctl.constraints == [] and len(ctl.pick.picks) == 1


def test_selection_refs_parallel_two_lines_only(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (50, 0)); b = _line(sc, (0, 40), (50, 60))
    a.setSelected(True)
    assert ctl.selection_refs("parallel") is None              # one line
    b.setSelected(True)
    assert sorted(r["uid"] for r in ctl.selection_refs("parallel")) == sorted([a._uid, b._uid])
    assert all(r["h"] == "edge" for r in ctl.selection_refs("parallel"))
    r = _rect(sc, (100, 100), (140, 130)); r.setSelected(True)
    assert ctl.selection_refs("parallel") is None              # any other selection


@pytest.mark.parametrize("b_ends", [((0, 50), (0, 150)),        # exactly perpendicular
                                    ((0, 50), (17.6, 150)),     # 80 deg
                                    ((0, 50), (100, 150))])     # 45 deg
def test_parallel_rotates_and_keeps_lengths(qapp, b_ends):
    """CS10 PP6: Parallel turns near-perpendicular lines instead of going red
    or shrinking them."""
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, *b_ends)
    ln = lambda it: math.hypot(it._pt2.x() - it._pt1.x(), it._pt2.y() - it._pt1.y())
    la, lb = ln(a), ln(b)
    c = sc.constraint_ctl.add("parallel", [P(a, "edge"), P(b, "edge")])
    assert c.id not in sc.constraint_ctl.red and abs(_sin(a, b)) < 1e-9
    assert ln(a) == pytest.approx(la, abs=1e-6) and ln(b) == pytest.approx(lb, abs=1e-6)
