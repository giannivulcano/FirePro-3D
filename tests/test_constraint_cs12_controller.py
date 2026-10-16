"""CS12 Tangent -- controller (spec §7.3, §8; rulings T1-T6).

Real ``Model_Space(scene_role="block_editor")`` + real primitives; asserts
the solved geometry, records and status.
"""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import ArcItem, CircleItem, LineItem, RectangleItem
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


def _sd(ln, c):
    """Signed distance of point c from ln's infinite line (cross / |d|)."""
    a, b = ln._pt1, ln._pt2
    dx, dy = b.x() - a.x(), b.y() - a.y()
    return ((c.x() - a.x()) * dy - (c.y() - a.y()) * dx) / math.hypot(dx, dy)


def _cd(k1, k2):
    return math.hypot(k2._center.x() - k1._center.x(), k2._center.y() - k1._center.y())


def test_tangent_line_circle_least_change_keeps_radius(qapp):
    sc = _scene()
    ln = _line(sc, (0, 100), (200, 100)); k = _circle(sc, (100, 0), 50)
    c = sc.constraint_ctl.add("tangent", [P(ln, "edge"), P(k, "curve")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert float(k._radius) == pytest.approx(50.0, abs=1e-9)                 # T3
    assert abs(_sd(ln, k._center)) == pytest.approx(50.0, abs=1e-6)
    assert ln._pt1.y() == pytest.approx(100 - 50 / 3, abs=1e-4)               # both moved
    assert k._center.y() == pytest.approx(100 / 3, abs=1e-4)
    assert sc.constraint_ctl.diagnostics().dof == 7 - 1


def test_tangent_curve_first_pick_is_stored_edge_first_and_side_follows_geometry(qapp):
    sc = _scene()
    ln = _line(sc, (0, 100), (200, 100)); k = _circle(sc, (100, 0), 50)
    c = sc.constraint_ctl.add("tangent", [P(k, "curve"), P(ln, "edge")])
    assert c.refs == [P(ln, "edge"), P(k, "curve")]
    side = 1 if _sd(_line(_scene(), (0, 100), (200, 100)), QPointF(100, 0)) >= 0 else -1
    assert c.helper == {"side": side}
    sc2 = _scene()
    ln2 = _line(sc2, (0, -100), (200, -100)); k2 = _circle(sc2, (100, 0), 50)  # centre the other side
    c2 = sc2.constraint_ctl.add("tangent", [P(ln2, "edge"), P(k2, "curve")])
    assert c2.helper == {"side": -side}
    assert _sd(ln2, k2._center) * _sd(ln, k._center) < 0                      # kept its own side


def test_tangent_circles_external_and_internal_follow_geometry(qapp):
    sc = _scene()
    a = _circle(sc, (0, 0), 30); b = _circle(sc, (100, 0), 20)
    c = sc.constraint_ctl.add("tangent", [P(a, "curve"), P(b, "curve")])
    assert c.helper == {"internal": False}
    assert _cd(a, b) == pytest.approx(50.0, abs=1e-6)
    assert (float(a._radius), float(b._radius)) == (30.0, 20.0)
    sc2 = _scene()
    small = _circle(sc2, (10, 0), 10); big = _circle(sc2, (0, 0), 50)       # small picked first
    c2 = sc2.constraint_ctl.add("tangent", [P(small, "curve"), P(big, "curve")])
    assert c2.helper == {"internal": True}
    assert c2.refs == [P(big, "curve"), P(small, "curve")]                  # larger first
    assert _cd(big, small) == pytest.approx(40.0, abs=1e-6)


def test_tangent_line_and_arc_uses_the_full_circle(qapp):
    sc = _scene()
    ln = _line(sc, (-50, 200), (50, 200))
    arc = _arc(sc, (300, 0), 40, 0.0, 90.0)                       # line far outside the span
    c = sc.constraint_ctl.add("tangent", [P(ln, "edge"), P(arc, "curve")])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert abs(_sd(ln, arc._center)) == pytest.approx(float(arc._radius), abs=1e-6)


def test_tangent_rect_side_and_circle(qapp):
    from firepro3d.sketch_adapters import adapter_for
    sc = _scene()
    r = _rect(sc, (0, 0), (100, 60)); k = _circle(sc, (50, 150), 20)
    side = sorted(adapter_for(r).edges(r, 0))[0]
    c = sc.constraint_ctl.add("tangent", [P(r, side), P(k, "curve")])
    assert c is not None and c.id not in sc.constraint_ctl.red


def test_tangent_helper_must_match_the_ref_kinds(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    ln = _line(sc, (0, 100), (200, 100)); k = _circle(sc, (100, 0), 50)
    rec = {"id": "t1", "type": "tangent", "refs": [P(ln, "edge"), P(k, "curve")],
           "helper": {"internal": True}}
    ctl.load([rec])
    assert ctl.constraints[0].invalid
    ctl.load([{**rec, "id": "t2", "helper": {"side": True}}])
    assert ctl.constraints[0].invalid
    ctl.load([{**rec, "id": "t3", "helper": {"side": -1}}])
    assert not ctl.constraints[0].invalid


def _tangent_block(sc, touching):
    """A definition holding a line y=40 and a circle r 40 (touching) or r 30."""
    d = BlockDefinition.new(
        name="T", library="L", series="S", origin=(0.0, 0.0),
        primitives=[_prim("draw_line", pt1=[-50.0, 40.0], pt2=[50.0, 40.0]),
                    _prim("draw_circle", cx=0.0, cy=0.0, radius=40.0 if touching else 30.0)])
    sc.register_block_definition(d)
    inst = sc.place_block_instance(d.id, (0.0, 0.0), rotation=0.0, mirrored=False, scale=1.0)
    sc.push_undo_state()
    k0, k1 = (d.primitives[i].get("uid") or f"#{i}" for i in (0, 1))
    return [{"uid": inst._uid, "h": f"{k0}:edge"}, {"uid": inst._uid, "h": f"{k1}:curve"}]


def test_tangent_inside_one_rigid_block_refused_when_touching_else_red(qapp):
    from firepro3d.constraint_controller import TANGENT_TRIVIAL_STATUS
    sc = _scene()
    msgs = _status(sc)
    assert sc.constraint_ctl.add("tangent", _tangent_block(sc, True)) is None
    assert msgs[-1] == TANGENT_TRIVIAL_STATUS
    sc2 = _scene()
    c = sc2.constraint_ctl.add("tangent", _tangent_block(sc2, False))
    assert c is not None and c.id in sc2.constraint_ctl.red


def test_tangent_pick_kinds_and_status(qapp):
    from firepro3d.constraint_controller import PickState
    sc = _scene()
    p = PickState(sc.constraint_ctl, "tangent")
    assert p._allowed("edge") and p._allowed("curve")
    assert not p._allowed("point") and not p._allowed("axis")
    assert p.status() == ("Tangent: pick an edge or a circle/arc, then a circle/arc "
                          "(0/2) · Esc to cancel")
    p.picks, p.kinds = [{"uid": "a", "h": "edge"}], ["edge"]
    assert p._allowed("curve") and not p._allowed("edge")
    assert p.status() == "Tangent: pick a circle/arc (1/2) · Esc to cancel"
    p.kinds = ["curve"]
    assert p._allowed("curve") and p._allowed("edge")
    assert p.status() == "Tangent: pick an edge or another circle/arc (1/2) · Esc to cancel"
    _circle(sc, (0, 0), 10)
    kinds = {k for k, *_ in p._candidates()}
    assert "curve" in kinds and "axis" not in kinds


def test_selection_refs_tangent_exactly_two_valid(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (100, 0)); l2 = _line(sc, (0, 50), (100, 50))
    k = _circle(sc, (50, 100), 20); a = _arc(sc, (200, 0), 30, 0.0, 180.0)

    def sel(*its):
        sc.clearSelection()
        for it in its:
            it.setSelected(True)
        return ctl.selection_refs("tangent")
    assert sel(k, ln) == [P(ln, "edge"), P(k, "curve")]
    assert sel(k, a) is not None and len(sel(k, a)) == 2
    assert sel(ln, l2) is None and sel(ln) is None and sel(ln, k, a) is None


def test_tangent_copies_keep_and_mirror_negates_side(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    ln = _line(sc, (0, 50), (200, 50)); k = _circle(sc, (100, 0), 50)
    c = ctl.add("tangent", [P(ln, "edge"), P(k, "curve")])
    side = c.helper["side"]
    recs = ctl.internal_records([ln, k])
    # mirror about x = 300: x -> 600 - x
    ln2 = _line(sc, (600, 50), (400, 50)); k2 = _circle(sc, (500, 0), 50)
    ctl.paste_records(recs, {ln._uid: ln2._uid, k._uid: k2._uid},
                      mirror_axis=(QPointF(300, 0), QPointF(300, 10)),
                      point_map=lambda p: QPointF(600 - p.x(), p.y()))
    (m,) = ctl.constraints_on(ln2)
    assert m.type == "tangent" and m.helper == {"side": -side}
    assert not m.invalid and m.id not in ctl.red
    ln3 = _line(sc, (0, 300), (200, 300)); k3 = _circle(sc, (100, 250), 50)
    ctl.paste_records(recs, {ln._uid: ln3._uid, k._uid: k3._uid})
    (t,) = ctl.constraints_on(ln3)
    assert t.helper == {"side": side}


def test_tangent_in_place_flip_negates_side_and_stays_satisfied(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    ln = _line(sc, (0, 50), (200, 50)); k = _circle(sc, (100, 0), 50)
    c = ctl.add("tangent", [P(ln, "edge"), P(k, "curve")])
    side = c.helper["side"]

    def pm(p):                                                    # flip across y = 0
        return QPointF(p.x(), -p.y())
    with ctl.edit([ln, k], point_map=pm):
        for it in (ln, k):
            it.manip_reflect(QPointF(0, 0), QPointF(10, 0))
    assert c.helper == {"side": -side}
    assert c.id not in ctl.red
    assert ln._pt1.y() == pytest.approx(-50.0, abs=1e-6)                  # the flip held
    assert k._center.y() == pytest.approx(0.0, abs=1e-6)
