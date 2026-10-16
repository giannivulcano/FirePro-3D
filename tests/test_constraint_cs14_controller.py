"""CS14 Collinear -- controller (spec §7.3, §8; rulings C1-C4).

Real ``Model_Space(scene_role="block_editor")`` + real primitives; asserts
the solved geometry, records and status.
"""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, PolylineItem, RectangleItem
from firepro3d.model_space import Model_Space
from tests._block_snap_helpers import _prim


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


def _off(ln, p):
    """Signed distance of point p from ln's infinite line."""
    a, b = ln._pt1, ln._pt2
    dx, dy = b.x() - a.x(), b.y() - a.y()
    return ((p.x() - a.x()) * dy - (p.y() - a.y()) * dx) / math.hypot(dx, dy)


def _len(a):
    return math.hypot(a._pt2.x() - a._pt1.x(), a._pt2.y() - a._pt1.y())


def _collinear(a, b):
    return abs(_off(a, b._pt1)) < 1e-6 and abs(_off(a, b._pt2)) < 1e-6


def _pick_view(sc):
    from firepro3d.model_view import Model_View
    v = Model_View(sc)
    v.resize(800, 600)
    v.resetTransform()
    v.centerOn(0, 0)
    return v


def _press(ctl, v, x, y):
    return ctl.pick_press(v, QPointF(v.mapFromScene(QPointF(x, y))))


@pytest.mark.parametrize("b_ends", [((0, 50), (100, 50)),        # parallel, 50 apart
                                    ((0, 50), (50, 78.87)),      # short, 30 deg
                                    ((50, -50), (50, 50)),       # crossing, 90 deg
                                    ((300, 20), (400, 20))])     # beyond the segment
def test_collinear_lands_on_one_line_keeping_lengths(qapp, b_ends):
    """C2: rotate-first (lengths held) -- the edges turn / slide, none shrinks."""
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, *b_ends)
    la, lb = _len(a), _len(b)
    c = sc.constraint_ctl.add("collinear", [P(a, "edge"), P(b, "edge")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert _collinear(a, b)
    assert _len(a) == pytest.approx(la, abs=1e-6) and _len(b) == pytest.approx(lb, abs=1e-6)


def test_collinear_parallel_pair_both_move(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (100, 50))
    sc.constraint_ctl.add("collinear", [P(a, "edge"), P(b, "edge")])
    assert a._pt1.y() > 1.0 and b._pt1.y() < 49.0           # split by least change
    assert _collinear(a, b)


@pytest.mark.parametrize("axis,k", [("x_axis", 1), ("y_axis", 0)])
def test_collinear_edge_onto_axis_keeps_length(qapp, axis, k):
    sc = _scene()
    a = _line(sc, (10, 20), (100, 45))
    la = _len(a)
    c = sc.constraint_ctl.add("collinear", [P(a, "edge"), {"ref": axis}])
    assert c.id not in sc.constraint_ctl.red
    coord = (lambda q: q.y()) if k == 1 else (lambda q: q.x())
    assert coord(a._pt1) == pytest.approx(0.0, abs=1e-6)
    assert coord(a._pt2) == pytest.approx(0.0, abs=1e-6)
    assert _len(a) == pytest.approx(la, abs=1e-6)


def test_parallel_on_a_collinear_pair_is_redundant_amber(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (100, 60))
    ctl.add("collinear", [P(a, "edge"), P(b, "edge")])
    p = ctl.add("parallel", [P(a, "edge"), P(b, "edge")])
    assert p.id in ctl.diagnostics().redundant and p.id not in ctl.red


def test_horizontal_on_an_edge_collinear_with_x_axis_is_redundant_amber(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 5), (100, 25))
    ctl.add("collinear", [P(a, "edge"), {"ref": "x_axis"}])
    h = ctl.add("horizontal", [P(a, "edge")])
    assert h.id in ctl.diagnostics().redundant and h.id not in ctl.red


def test_collinear_rect_opposite_sides_admitted_red(qapp):
    sc = _scene()
    r = _rect(sc, (0, 0), (40, 30))
    c = sc.constraint_ctl.add("collinear", [P(r, "top"), P(r, "bottom")])
    assert c is not None and c.id in sc.constraint_ctl.red


def test_collinear_polyline_segments_admitted_and_straightened(qapp):
    sc = _scene()
    pl = PolylineItem(QPointF(0, 0))
    for q in (QPointF(100, 30), QPointF(200, 0)):
        pl.append_point(q)
    sc.addItem(pl); sc._polylines.append(pl)
    c = sc.constraint_ctl.add("collinear", [P(pl, "s0"), P(pl, "s1")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    p0, p1, p2 = pl._points[:3]
    cross = (p1.x() - p0.x()) * (p2.y() - p0.y()) - (p1.y() - p0.y()) * (p2.x() - p0.x())
    assert abs(cross) < 1e-6


def _collinear_block(sc, in_line):
    """A definition holding two segments at y=40 (in line) or y=40 / y=60."""
    d = BlockDefinition.new(
        name="C", library="L", series="S", origin=(0.0, 0.0),
        primitives=[_prim("draw_line", pt1=[-50.0, 40.0], pt2=[-10.0, 40.0]),
                    _prim("draw_line", pt1=[10.0, 40.0 if in_line else 60.0],
                          pt2=[50.0, 40.0 if in_line else 60.0])])
    sc.register_block_definition(d)
    inst = sc.place_block_instance(d.id, (0.0, 0.0), rotation=0.0, mirrored=False, scale=1.0)
    sc.push_undo_state()
    k0, k1 = (d.primitives[i].get("uid") or f"#{i}" for i in (0, 1))
    return [{"uid": inst._uid, "h": f"{k0}:edge"}, {"uid": inst._uid, "h": f"{k1}:edge"}]


def test_collinear_inside_one_rigid_block_refused_when_in_line_else_red(qapp):
    from firepro3d.constraint_controller import COLLINEAR_TRIVIAL_STATUS
    sc = _scene()
    msgs = _status(sc)
    assert sc.constraint_ctl.add("collinear", _collinear_block(sc, True)) is None
    assert msgs[-1] == COLLINEAR_TRIVIAL_STATUS == (
        "Those edges are already collinear by construction -- pick another edge")
    sc2 = _scene()
    c = sc2.constraint_ctl.add("collinear", _collinear_block(sc2, False))
    assert c is not None and c.id in sc2.constraint_ctl.red


def test_collinear_record_kinds_validated(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (100, 50))
    ctl.load([{"id": "c1", "type": "collinear", "refs": [P(a, "p1"), P(b, "edge")]}])
    assert ctl.constraints[0].invalid
    ctl.load([{"id": "c2", "type": "collinear", "refs": [P(a, "edge"), P(b, "edge")]}])
    assert not ctl.constraints[0].invalid


def test_collinear_copies_keep_edge_pair_drop_axis(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (150, 0), (250, 0))
    ctl.add("collinear", [P(a, "edge"), P(b, "edge")])
    ctl.add("collinear", [P(b, "edge"), {"ref": "x_axis"}])
    recs = ctl.internal_records([a, b])
    a2 = _line(sc, (0, 300), (100, 300)); b2 = _line(sc, (150, 300), (250, 300))
    ctl.paste_records(recs, {a._uid: a2._uid, b._uid: b2._uid},
                      mirror_axis=(QPointF(150, 0), QPointF(160, 37)))
    got = ctl.constraints_on(a2)
    assert [c.type for c in got] == ["collinear"] and not got[0].invalid
    assert got[0].refs == [P(a2, "edge"), P(b2, "edge")]
    a3 = _line(sc, (500, 0), (500, 100)); b3 = _line(sc, (500, 150), (500, 250))
    ctl.paste_records(recs, {a._uid: a3._uid, b._uid: b3._uid}, rotation_deg=90.0)
    assert [c.type for c in ctl.constraints_on(a3)] == ["collinear"]


def test_collinear_pick_kinds_and_status(qapp):
    from firepro3d.constraint_controller import PickState
    from firepro3d.geometry_2d import CircleItem
    sc = _scene()
    it = CircleItem(QPointF(0, 0), 20); sc.addItem(it); sc._draw_circles.append(it)
    p = PickState(sc.constraint_ctl, "collinear")
    kinds = {k for k, *_ in p._candidates()}
    assert "axis" in kinds and "curve" not in kinds
    assert p._allowed("edge") and p._allowed("axis") and not p._allowed("point")
    assert p.status() == ("Collinear: pick an edge, then an edge or the X/Y axis"
                          " (0/2) · Esc to cancel")
    p.picks, p.kinds = [{"ref": "x_axis"}], ["axis"]
    assert p._allowed("edge") and not p._allowed("axis")
    assert p.status() == "Collinear: pick an edge (1/2) · Esc to cancel"


def test_collinear_pick_flow_axis_first_stores_edge_first(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (-60, 40), (60, 70))
    v = _pick_view(sc)
    sc.set_mode("constrain_collinear")
    assert not _press(ctl, v, 200, 0)                       # the X axis
    assert _press(ctl, v, 30, 62.5)                         # the edge
    (c,) = ctl.constraints
    assert c.refs == [P(a, "edge"), {"ref": "x_axis"}]
    assert a._pt1.y() == pytest.approx(0.0, abs=1e-6) and a._pt2.y() == pytest.approx(0.0, abs=1e-6)


def test_collinear_repeated_edge_says_pick_a_different_edge(qapp):
    from firepro3d.constraint_controller import PICK_SAME_EDGE_STATUS
    sc = _scene()
    ctl = sc.constraint_ctl
    _line(sc, (-80, -50), (-40, 50))
    v = _pick_view(sc)
    msgs = _status(sc)
    sc.set_mode("constrain_collinear")
    _press(ctl, v, -50, 25)
    assert _press(ctl, v, -50, 25) is False
    assert msgs[-1] == PICK_SAME_EDGE_STATUS
    assert ctl.constraints == [] and len(ctl.pick.picks) == 1


def test_selection_refs_collinear_two_lines_only(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (50, 0)); b = _line(sc, (0, 40), (50, 60))
    a.setSelected(True)
    assert ctl.selection_refs("collinear") is None
    b.setSelected(True)
    assert sorted(r["uid"] for r in ctl.selection_refs("collinear")) == sorted([a._uid, b._uid])
    r = _rect(sc, (100, 100), (140, 130)); r.setSelected(True)
    assert ctl.selection_refs("collinear") is None


def test_collinear_rotate_first_leaves_no_temporary_records(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (0, 50), (100, 50))
    ctl.add("collinear", [P(a, "edge"), P(b, "edge")])
    assert [c.type for c in ctl.constraints] == ["collinear"]
    assert ctl.diagnostics().dof == 8 - 2
