"""CS11 Equal -- controller (spec §7.3, §8; rulings E1-E5).

Real ``Model_Space(scene_role="block_editor")`` + real primitives; asserts
the solved geometry, records and status.
"""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import ArcItem, CircleItem, LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from tests._block_snap_helpers import register_snap_block


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _rect(sc, a, b):
    r = RectangleItem(QPointF(*a), QPointF(*b)); sc.addItem(r); sc._draw_rects.append(r)
    return r


def _circle(sc, c, r):
    it = CircleItem(QPointF(*c), r); sc.addItem(it); sc._draw_circles.append(it)
    return it


def _arc(sc, c, r, start, span):
    it = ArcItem(QPointF(*c), r, start, span); sc.addItem(it); sc._draw_arcs.append(it)
    return it


def _status(sc):
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    return msgs


def P(it, h):
    return {"uid": it._uid, "h": h}


def _len(a):
    return math.hypot(a._pt2.x() - a._pt1.x(), a._pt2.y() - a._pt1.y())


def _ang(a):
    return math.atan2(a._pt2.y() - a._pt1.y(), a._pt2.x() - a._pt1.x())


def _pick_view(sc):
    from firepro3d.model_view import Model_View
    v = Model_View(sc)
    v.resize(800, 600)
    v.resetTransform()
    v.centerOn(0, 0)
    return v


def _press(ctl, v, x, y):
    return ctl.pick_press(v, QPointF(v.mapFromScene(QPointF(x, y))))


def test_equal_lines_meet_in_the_middle_keeping_directions(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (36, 98))      # 60 mm at 53.13 deg
    ta, tb = _ang(a), _ang(b)
    c = sc.constraint_ctl.add("equal", [P(a, "edge"), P(b, "edge")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert _len(a) == pytest.approx(_len(b), abs=1e-6)
    assert 60.0 < _len(a) < 100.0                                          # E2: both moved
    assert _ang(a) == pytest.approx(ta, abs=1e-9) and _ang(b) == pytest.approx(tb, abs=1e-9)
    assert sc.constraint_ctl.diagnostics().dof == 8 - 1


def test_equal_circle_and_arc_radii_meet(qapp):
    sc = _scene()
    a = _circle(sc, (0, 0), 50.0); b = _arc(sc, (200, 0), 30.0, 0.0, 90.0)
    c = sc.constraint_ctl.add("equal", [P(a, "curve"), P(b, "curve")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert float(a._radius) == pytest.approx(float(b._radius), abs=1e-6)
    assert 30.0 < float(a._radius) < 50.0


def test_equal_rect_adjacent_sides_makes_a_square(qapp):
    sc = _scene()
    r = _rect(sc, (0, 0), (40, 30))
    c = sc.constraint_ctl.add("equal", [P(r, "top"), P(r, "left")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert r.rect().width() == pytest.approx(r.rect().height(), abs=1e-6)
    assert 30.0 - 1e-6 <= r.rect().width() <= 40.0 + 1e-6                  # a rect's sizes may be stiff (D34)


@pytest.mark.parametrize("make,refs", [
    ("rect", ("top", "bottom")),
    ("poly", ("s0", "s1")),
])
def test_equal_by_construction_is_refused(qapp, make, refs):
    from firepro3d.constraint_controller import EQUAL_TRIVIAL_STATUS
    from firepro3d.geometry_2d import RegularPolygonItem
    sc = _scene()
    msgs = _status(sc)
    if make == "rect":
        it = _rect(sc, (0, 0), (40, 30))
    else:
        it = RegularPolygonItem(QPointF(0, 0), 5, 50.0); sc.addItem(it); sc._draw_polygons.append(it)
    assert sc.constraint_ctl.add("equal", [P(it, refs[0]), P(it, refs[1])]) is None
    assert msgs[-1] == EQUAL_TRIVIAL_STATUS == "Those are already equal by construction -- pick another"
    assert sc.constraint_ctl.constraints == []


def _nested(sc, scale):
    d = register_snap_block(sc, nested=True)
    inst = sc.place_block_instance(d.id, (40.0, 20.0), rotation=0.0, mirrored=False, scale=scale)
    sc.push_undo_state()
    key = d.primitives[2].get("uid") or "#2"                 # circle C, r 40 (block units)
    return inst, {"uid": inst._uid, "h": f"{key}:curve"}


def test_equal_loose_circle_takes_the_nested_radius(qapp):
    sc = _scene()
    inst, nref = _nested(sc, 1.5)                             # nested r = 60
    loose = _circle(sc, (500.0, 500.0), 15.0)
    c = sc.constraint_ctl.add("equal", [P(loose, "curve"), nref])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert float(loose._radius) == pytest.approx(60.0, abs=1e-6)


def test_equal_two_nested_curves_same_radius_refused_different_red(qapp):
    from firepro3d.constraint_controller import EQUAL_TRIVIAL_STATUS
    sc = _scene()
    msgs = _status(sc)
    _i1, r1 = _nested(sc, 1.5)
    _i2, r2 = _nested(sc, 1.5)
    assert sc.constraint_ctl.add("equal", [r1, r2]) is None
    assert msgs[-1] == EQUAL_TRIVIAL_STATUS
    _i3, r3 = _nested(sc, 1.0)                                # r = 40
    c = sc.constraint_ctl.add("equal", [r1, r3])
    assert c is not None and c.id in sc.constraint_ctl.red    # E4: admitted red


def test_equal_pick_kinds_and_status(qapp):
    from firepro3d.constraint_controller import PickState
    sc = _scene()
    _circle(sc, (0, 0), 20); _line(sc, (50, 0), (90, 0))
    p = PickState(sc.constraint_ctl, "equal")
    kinds = {k for k, *_ in p._candidates()}
    assert "curve" in kinds and "edge" in kinds and "axis" not in kinds
    assert p._allowed("edge") and p._allowed("curve") and not p._allowed("point")
    assert p.status() == ("Equal: pick an edge or a circle/arc, then another of the"
                          " same kind (0/2) · Esc to cancel")
    p.picks, p.kinds = [{"uid": "u", "h": "edge"}], ["edge"]
    assert p._allowed("edge") and not p._allowed("curve")
    assert p.status() == "Equal: pick another edge (1/2) · Esc to cancel"
    p.picks, p.kinds = [{"uid": "u", "h": "curve"}], ["curve"]
    assert p._allowed("curve") and not p._allowed("edge")
    assert p.status() == "Equal: pick another circle/arc (1/2) · Esc to cancel"


def test_equal_pick_flow_two_edges(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (-100, 50), (0, 50)); b = _line(sc, (50, -50), (110, -50))
    v = _pick_view(sc)
    sc.set_mode("constrain_equal")
    assert not _press(ctl, v, -50, 50)
    assert _press(ctl, v, 80, -50)
    (c,) = ctl.constraints
    assert c.type == "equal" and c.refs == [P(a, "edge"), P(b, "edge")]
    assert _len(a) == pytest.approx(_len(b), abs=1e-6)


def test_equal_repeated_curve_says_pick_a_different_circle(qapp):
    from firepro3d.constraint_controller import PICK_SAME_CURVE_STATUS
    sc = _scene()
    ctl = sc.constraint_ctl
    _circle(sc, (0, 0), 40)
    v = _pick_view(sc)
    msgs = _status(sc)
    sc.set_mode("constrain_equal")
    _press(ctl, v, 40, 0)
    assert _press(ctl, v, 40, 0) is False
    assert msgs[-1] == PICK_SAME_CURVE_STATUS
    assert ctl.constraints == []


def test_selection_refs_equal_two_plus_same_kind_only(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (50, 0)); b = _line(sc, (0, 40), (50, 60)); c = _line(sc, (0, 90), (20, 90))
    a.setSelected(True)
    assert ctl.selection_refs("equal") is None
    b.setSelected(True); c.setSelected(True)
    refs = ctl.selection_refs("equal")
    assert sorted(r["uid"] for r in refs) == sorted([a._uid, b._uid, c._uid])
    assert {r["h"] for r in refs} == {"edge"}
    k = _circle(sc, (200, 0), 10); k.setSelected(True)
    assert ctl.selection_refs("equal") is None                             # mixed
    sc.clearSelection()
    k.setSelected(True); _arc(sc, (300, 0), 5, 0, 90).setSelected(True)
    assert {r["h"] for r in ctl.selection_refs("equal")} == {"curve"}


def test_add_many_equal_chain_is_one_undo_step(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    ls = [_line(sc, (0, y), (L, y)) for y, L in ((0, 100), (40, 60), (80, 30))]
    sc.push_undo_state()
    n0 = sc._undo_pos
    first = P(ls[0], "edge")
    out = ctl.add_many("equal", [[first, P(l, "edge")] for l in ls[1:]])
    assert [c.type for c in out] == ["equal", "equal"]
    assert sc._undo_pos == n0 + 1                                           # ONE undo step
    assert all(c.refs[0] == first for c in out)
    assert _len(ls[0]) == pytest.approx(_len(ls[1]), abs=1e-6) == pytest.approx(_len(ls[2]), abs=1e-6)
    uids = [l._uid for l in ls]
    sc.undo()                                               # undo rebuilds the items
    assert ctl.constraints == []
    by = {l._uid: l for l in sc._draw_lines}
    assert [round(_len(by[u]), 6) for u in uids] == [100.0, 60.0, 30.0]


def test_equal_copies_keep_under_mirror_and_rotation(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (0, 150))
    ctl.add("equal", [P(a, "edge"), P(b, "edge")])
    recs = ctl.internal_records([a, b])
    a2 = _line(sc, (300, 0), (400, 0)); b2 = _line(sc, (300, 50), (300, 150))
    ctl.paste_records(recs, {a._uid: a2._uid, b._uid: b2._uid},
                      mirror_axis=(QPointF(150, 0), QPointF(160, 37)))
    got = ctl.constraints_on(a2)
    assert [c.type for c in got] == ["equal"] and not got[0].invalid
    a3 = _line(sc, (0, 300), (0, 400)); b3 = _line(sc, (50, 300), (150, 300))
    ctl.paste_records(recs, {a._uid: a3._uid, b._uid: b3._uid}, rotation_deg=90.0)
    assert [c.type for c in ctl.constraints_on(a3)] == ["equal"]
