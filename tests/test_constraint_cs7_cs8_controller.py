"""CS7 Symmetric + CS8 Fix -- controller (spec §7.3, §8; rulings S1/S2/F1-F3).

Every test drives a real ``Model_Space(scene_role="block_editor")`` with real
primitives and asserts the solved scene geometry / records / undo stack.
"""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import CircleItem, LineItem, RectangleItem
from firepro3d.model_space import Model_Space


def _scene():
    return Model_Space(scene_role="block_editor")


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _circle(sc, c, r):
    it = CircleItem(QPointF(*c), r); sc.addItem(it); sc._draw_circles.append(it)
    return it


def _status(sc):
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    return msgs


def P(it, h):
    return {"uid": it._uid, "h": h}


def _xy(p):
    return (p.x(), p.y())


# ── Task 3: records + solve ─────────────────────────────────────────────────

def test_symmetric_two_points_about_y_axis(qapp):
    sc = _scene()
    a = _line(sc, (-30, 10), (-60, 40)); b = _line(sc, (20, 14), (80, 80))
    c = sc.constraint_ctl.add("symmetric", [P(a, "p1"), P(b, "p1"), {"ref": "y_axis"}])
    assert c is not None and c.id not in sc.constraint_ctl.red
    assert a._pt1.x() == pytest.approx(-b._pt1.x(), abs=1e-6)
    assert a._pt1.y() == pytest.approx(b._pt1.y(), abs=1e-6)


def test_symmetric_two_points_about_an_oblique_edge(qapp):
    sc = _scene()
    ax = _line(sc, (0, 0), (100, 60))
    a = _line(sc, (10, 50), (0, 90)); b = _line(sc, (60, -5), (120, -40))
    sc.constraint_ctl.add("symmetric", [P(a, "p1"), P(b, "p1"), P(ax, "edge")])
    p, q = ax._pt1, ax._pt2
    d = (q.x() - p.x(), q.y() - p.y()); L = math.hypot(*d)
    m = ((a._pt1.x() + b._pt1.x()) / 2 - p.x(), (a._pt1.y() + b._pt1.y()) / 2 - p.y())
    assert abs(m[0] * d[1] - m[1] * d[0]) / L < 1e-6                  # midpoint on axis
    w = (b._pt1.x() - a._pt1.x(), b._pt1.y() - a._pt1.y())
    assert abs(w[0] * d[0] + w[1] * d[1]) / L < 1e-6                  # perpendicular


def test_symmetric_two_lines_pairs_nearer_ends_sp1(qapp):
    sc = _scene()
    a = _line(sc, (-50, 0), (-20, 40))
    b = _line(sc, (22, 38), (49, 1))           # drawn reversed: b.p2 mirrors a.p1
    c = sc.constraint_ctl.add("symmetric", [P(a, "edge"), P(b, "edge"), {"ref": "y_axis"}])
    assert c.helper == {"swap": True}
    assert _xy(a._pt1) == pytest.approx((-b._pt2.x(), b._pt2.y()), abs=1e-6)
    assert _xy(a._pt2) == pytest.approx((-b._pt1.x(), b._pt1.y()), abs=1e-6)


def test_symmetric_two_circles_equal_radius(qapp):
    sc = _scene()
    a = _circle(sc, (-40, 0), 20); b = _circle(sc, (44, 6), 10)
    sc.constraint_ctl.add("symmetric", [P(a, "curve"), P(b, "curve"), {"ref": "y_axis"}])
    assert a._center.x() == pytest.approx(-b._center.x(), abs=1e-6)
    assert a._center.y() == pytest.approx(b._center.y(), abs=1e-6)
    assert float(a._radius) == pytest.approx(float(b._radius), abs=1e-6)


def test_fix_point_captures_v0_and_holds_through_a_rotate_commit(qapp):
    sc = _scene()
    ln = _line(sc, (10, 20), (110, 20))
    c = sc.constraint_ctl.add("fix", [P(ln, "p1")])
    assert c.helper == {"v0": [10.0, 20.0]}
    with sc.constraint_ctl.edit([ln]):
        ln.manip_rotate(30.0, QPointF(110, 20))      # a Rotate commit about p2
    assert _xy(ln._pt1) == pytest.approx((10.0, 20.0), abs=1e-6)


def test_fix_whole_item_is_fully_defined(qapp):
    sc = _scene()
    r = RectangleItem(QPointF(0, 0), QPointF(40, 30)); sc.addItem(r); sc._draw_rects.append(r)
    ctl = sc.constraint_ctl
    c = ctl.add("fix", [{"uid": r._uid, "h": "item"}])
    assert c is not None and len(c.helper["v0"]) == 5
    assert ctl.diagnostics().state(r._uid) == "defined"


def test_fix_origin_refused_as_trivial(qapp):
    from firepro3d.constraint_controller import TRIVIAL_STATUS
    sc = _scene()
    _line(sc, (0, 0), (10, 0))
    msgs = _status(sc)
    assert sc.constraint_ctl.add("fix", [{"ref": "origin"}]) is None
    assert msgs[-1] == TRIVIAL_STATUS


def test_fix_twice_is_redundant_amber(qapp):
    sc = _scene()
    ln = _line(sc, (10, 20), (110, 20))
    ctl = sc.constraint_ctl
    ctl.add("fix", [P(ln, "p1")])
    k = ctl.add("fix", [P(ln, "p1")])
    assert k is not None and k.id in ctl.diagnostics().redundant and not ctl.red


def test_fix_record_with_bad_v0_is_inert(qapp):
    sc = _scene()
    ln = _line(sc, (10, 20), (110, 20))
    ctl = sc.constraint_ctl
    ctl.load([{"id": "f1", "type": "fix", "refs": [P(ln, "item")], "helper": {"v0": [1.0]}}])
    (c,) = ctl.constraints
    assert c.inert


def test_add_fixes_is_one_undo_step(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (10, 0)); b = _circle(sc, (50, 0), 5)
    sc.push_undo_state()
    n0 = sc._undo_pos
    out = sc.constraint_ctl.add_fixes([{"uid": a._uid, "h": "item"}, {"uid": b._uid, "h": "item"}])
    assert [c.type for c in out] == ["fix", "fix"]
    assert sc._undo_pos == n0 + 1
    assert len(sc._undo_stack[sc._undo_pos]["constraints"]) == 2


def test_copies_drop_fix_keep_internal_symmetric(qapp):
    sc = _scene()
    ax = _line(sc, (0, -50), (0, 50))
    a = _line(sc, (-30, 0), (-10, 20)); b = _line(sc, (10, 20), (30, 0))
    ctl = sc.constraint_ctl
    ctl.add("symmetric", [P(a, "edge"), P(b, "edge"), P(ax, "edge")])
    ctl.add("fix", [P(a, "p1")])
    recs = ctl.internal_records([ax, a, b])
    ax2 = _line(sc, (300, -50), (300, 50))
    a2 = _line(sc, (270, 0), (290, 20)); b2 = _line(sc, (310, 20), (330, 0))
    ctl.paste_records(recs, {ax._uid: ax2._uid, a._uid: a2._uid, b._uid: b2._uid},
                      mirror_axis=(QPointF(150, 0), QPointF(160, 37)))
    assert [c.type for c in ctl.constraints_on(a2)] == ["symmetric"]       # F3: no fix
    assert not any(c.invalid for c in ctl.constraints_on(a2))


def test_symmetric_about_y_axis_dropped_from_copies(qapp):
    sc = _scene()
    a = _line(sc, (-30, 0), (-10, 20)); b = _line(sc, (10, 20), (30, 0))
    ctl = sc.constraint_ctl
    ctl.add("symmetric", [P(a, "p1"), P(b, "p2"), {"ref": "y_axis"}])
    recs = ctl.internal_records([a, b])
    a2 = _line(sc, (270, 0), (290, 20)); b2 = _line(sc, (310, 20), (330, 0))
    ctl.paste_records(recs, {a._uid: a2._uid, b._uid: b2._uid})
    assert ctl.constraints_on(a2) == []


def test_ref_text_for_a_whole_item(qapp):
    sc = _scene()
    ln = _line(sc, (0, 0), (10, 0))
    assert sc.constraint_ctl.ref_text({"uid": ln._uid, "h": "item"}) == "Line"


# ── Task 4: pick mode + selection-first refs ───────────────────────────────

def test_symmetric_pick_kinds_by_step(qapp):
    from firepro3d.constraint_controller import PickState
    sc = _scene()
    _line(sc, (0, 0), (100, 0)); _circle(sc, (0, 100), 20)
    p = PickState(sc.constraint_ctl, "symmetric")

    def kinds():
        return {k for k, r, _a, _b in p._candidates() if p._allowed(k, r)}
    assert kinds() == {"point", "edge", "curve"}
    p.picks, p.kinds = [{"uid": "x", "h": "p1"}], ["point"]
    assert kinds() == {"point"}
    p.picks, p.kinds = [{"uid": "x", "h": "edge"}], ["edge"]
    assert kinds() == {"edge"}
    p.picks, p.kinds = [{"uid": "x", "h": "curve"}], ["curve"]
    assert kinds() == {"curve"}
    p.picks, p.kinds = [{"uid": "x", "h": "p1"}, {"uid": "y", "h": "p1"}], ["point", "point"]
    assert kinds() == {"edge", "axis"}
    assert p.status() == ("Symmetric: pick the axis -- an edge or the X/Y axis (2/3)"
                          " · Esc to cancel")


def test_fix_pick_kinds(qapp):
    from firepro3d.constraint_controller import PickState
    sc = _scene()
    _line(sc, (0, 0), (100, 0)); _circle(sc, (0, 100), 20)
    p = PickState(sc.constraint_ctl, "fix")
    assert {k for k, r, _a, _b in p._candidates() if p._allowed(k, r)} == {"point", "edge", "curve"}


def test_selection_refs_symmetric(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (-30, 0), (-10, 20)); b = _line(sc, (10, 20), (30, 0))
    ax = _line(sc, (0, -50), (0, 50)); ax.reference = True
    for it in (a, b, ax):
        it.setSelected(True)
    refs = ctl.selection_refs("symmetric")
    assert len(refs) == 3 and refs[2] == {"uid": ax._uid, "h": "edge"}
    assert sorted(r["uid"] for r in refs[:2]) == sorted([a._uid, b._uid])
    ax.setSelected(False)
    pair = ctl.selection_refs("symmetric")
    assert sorted(r["uid"] for r in pair) == sorted([a._uid, b._uid])
    assert all(r["h"] == "edge" for r in pair)
    c1 = _circle(sc, (-40, 0), 10); c2 = _circle(sc, (40, 0), 10)
    sc.clearSelection(); c1.setSelected(True); c2.setSelected(True)
    assert all(r["h"] == "curve" for r in ctl.selection_refs("symmetric"))
    a.setSelected(True)                                      # circles + a line
    assert ctl.selection_refs("symmetric") is None
    sc.clearSelection(); a.setSelected(True)
    assert ctl.selection_refs("symmetric") is None           # a lone line


def test_selection_refs_fix_every_selected_item(qapp):
    sc = _scene()
    a = _line(sc, (0, 0), (10, 0)); c = _circle(sc, (50, 0), 5)
    a.setSelected(True); c.setSelected(True)
    refs = sc.constraint_ctl.selection_refs("fix")
    assert sorted(r["uid"] for r in refs) == sorted([a._uid, c._uid])
    assert all(r["h"] == "item" for r in refs)


def test_begin_symmetric_axis_prefills_the_pair(qapp):
    sc = _scene()
    ctl = sc.constraint_ctl
    a = _line(sc, (-30, 0), (-10, 20)); b = _line(sc, (10, 20), (30, 0))
    sc.set_mode("constrain_symmetric")
    assert ctl.begin_symmetric_axis([P(a, "edge"), P(b, "edge")])
    assert ctl.pick.kinds == ["edge", "edge"]
    assert ctl.pick.status().startswith("Symmetric: pick the axis")


# -- T1-T3 review round (I1, M1, M2, M3) ----------------------------------------

def test_stale_whole_item_fix_sits_out_after_a_vertex_is_removed(qapp):
    """Review I1: a whole-item Fix whose v0 no longer matches the item's
    variable count never pins shifted variables (FP2p)."""
    from firepro3d.geometry_2d import PolylineItem
    sc = _scene()
    pl = PolylineItem(QPointF(0, 0))
    for q in (QPointF(100, 30), QPointF(200, 0)):
        pl.append_point(q)
    sc.addItem(pl); sc._polylines.append(pl)
    ctl = sc.constraint_ctl
    ctl.add("fix", [{"uid": pl._uid, "h": "item"}])
    pl._points.pop(1); pl._rebuild_path()             # a vertex removed in-session
    h = ctl.add("horizontal", [{"uid": pl._uid, "h": "s0"}])
    assert h is not None and h.id not in ctl.red
    assert pl._points[0].y() == pytest.approx(pl._points[1].y(), abs=1e-6)


def test_symmetric_swap_uses_both_ends(qapp):
    """Review M1: a short pair edge whose a1 mirror sits nearer the wrong
    end is still paired by the total of both ends."""
    sc = _scene()
    a = _line(sc, (-10, 0), (-100, 0))                # long edge, a.p1 near the axis
    b = _line(sc, (12, 0), (5, 0))                    # short edge, reversed
    c = sc.constraint_ctl.add("symmetric", [P(a, "edge"), P(b, "edge"), {"ref": "y_axis"}])
    # by ends: a.p1 (-10) <-> b.p1 (12) and a.p2 (-100) <-> b.p2 (5) total 2+95;
    # crossed: a.p1 <-> b.p2 (5 off) and a.p2 <-> b.p1 (88 off) total 93 -> crossed.
    assert c.helper == {"swap": True}


def test_symmetric_edge_pair_needs_a_bool_swap(qapp):
    sc = _scene()
    a = _line(sc, (-30, 0), (-10, 20)); b = _line(sc, (10, 20), (30, 0))
    ctl = sc.constraint_ctl
    ctl.load([{"id": "s1", "type": "symmetric",
               "refs": [P(a, "edge"), P(b, "edge"), {"ref": "y_axis"}], "helper": {}},
              {"id": "s2", "type": "symmetric",
               "refs": [P(a, "edge"), P(b, "edge"), {"ref": "y_axis"}],
               "helper": {"swap": 1}}])
    assert all(c.inert for c in ctl.constraints)


def test_add_fixes_posts_redundant_status(qapp):
    from firepro3d.constraint_controller import REDUNDANT_STATUS
    sc = _scene()
    a = _line(sc, (0, 0), (10, 0))
    ctl = sc.constraint_ctl
    ctl.add("fix", [P(a, "item")])
    msgs = _status(sc)
    ctl.add_fixes([P(a, "item")])
    assert msgs[-1] == REDUNDANT_STATUS


def test_mirrored_copy_of_a_symmetric_pair_is_satisfied(qapp):
    """Review M3: the mirrored copy keeps the pairing and is not red."""
    sc = _scene()
    ax = _line(sc, (0, -50), (0, 50))
    a = _line(sc, (-30, 0), (-10, 20)); b = _line(sc, (10, 20), (30, 0))
    ctl = sc.constraint_ctl
    ctl.add("symmetric", [P(a, "edge"), P(b, "edge"), P(ax, "edge")])
    recs = ctl.internal_records([ax, a, b])
    # the copies are the sources mirrored across x = 150
    ax2 = _line(sc, (300, -50), (300, 50))
    a2 = _line(sc, (330, 0), (310, 20)); b2 = _line(sc, (290, 20), (270, 0))
    ctl.paste_records(recs, {ax._uid: ax2._uid, a._uid: a2._uid, b._uid: b2._uid},
                      mirror_axis=(QPointF(150, -10), QPointF(150, 10)))
    (c2,) = ctl.constraints_on(a2)
    assert c2.type == "symmetric" and c2.id not in ctl.red
