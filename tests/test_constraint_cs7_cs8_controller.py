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
