"""AC-F3: a Fillet in the Block Editor ties the arc to the trimmed edges --
2 coincident + 2 tangent, solve satisfied; model space records nothing."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtTest import QTest

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import ArcItem, LineItem, PolylineItem, RectangleItem
from tests._snap_polish_helpers import click, close_view, make_view, move
from tests.test_arc_convention_tools import _add, _baseline


SHIFT = Qt.KeyboardModifier.ShiftModifier


@pytest.fixture(autouse=True)
def _toggle_on(qapp):
    """F3: relations follow the Auto Constrain toggle (as Offset AC4); default ON here."""
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    yield
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)


def _recs(sc):
    return [(c.type, [(r.get("uid"), r.get("h")) for r in c.refs])
            for c in sc.constraint_ctl.constraints]


def _fillet(view, sc, at, radius=10.0, mods=Qt.KeyboardModifier.NoModifier):
    sc._fillet_radius = radius
    sc._modify_ctl.start("fillet")
    move(view, at)
    click(view, at, mods)


def test_plan_fillet_emits_tangents_first(qapp):
    arc = ArcItem(QPointF(10, -10), 10.0, 180.0, 90.0)
    l1, l2 = LineItem(QPointF(100, 0), QPointF(10, 0)), LineItem(QPointF(0, -100), QPointF(0, -10))
    recs = ac.plan_fillet(arc, [(l1, "edge", "p2", "end"), (l2, "edge", "p2", "start")])
    assert recs == [
        ("tangent", [{"uid": l1._uid, "h": "edge"}, {"uid": arc._uid, "h": "curve"}]),
        ("tangent", [{"uid": l2._uid, "h": "edge"}, {"uid": arc._uid, "h": "curve"}]),
        ("coincident", [{"uid": arc._uid, "h": "end"}, {"uid": l1._uid, "h": "p2"}]),
        ("coincident", [{"uid": arc._uid, "h": "start"}, {"uid": l2._uid, "h": "p2"}]),
    ]


def test_plan_fillet_needs_every_uid(qapp):
    arc = ArcItem(QPointF(10, -10), 10.0, 180.0, 90.0)
    ln = LineItem(QPointF(100, 0), QPointF(10, 0))
    arc._uid = None
    assert ac.plan_fillet(arc, [(ln, "edge", "p2", "end")]) == []


def test_block_editor_line_fillet_records_two_coincident_two_tangent(qapp):
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        l1 = _add(sc, LineItem(QPointF(100, 0), QPointF(0, 0)), "_draw_lines")
        l2 = _add(sc, LineItem(QPointF(0, -100), QPointF(0, 0)), "_draw_lines")
        p0 = _baseline(sc)
        _fillet(view, sc, QPointF(0, 0))
        arc = sc._draw_arcs[0]
        # theta 90: arc starts at T2 (on l2), ends at T1 (on l1); both trimmed ends are p2
        assert _recs(sc) == [
            ("tangent", [(l1._uid, "edge"), (arc._uid, "curve")]),
            ("tangent", [(l2._uid, "edge"), (arc._uid, "curve")]),
            ("coincident", [(arc._uid, "end"), (l1._uid, "p2")]),           # [RED] order / handles
            ("coincident", [(arc._uid, "start"), (l2._uid, "p2")]),
        ]
        ctl = sc.constraint_ctl
        assert not ctl.red and not ctl.diagnostics().redundant            # solve satisfied
        assert sc._undo_pos == p0 + 1                                     # relations ride the one step
        sc.undo()
        assert sc.constraint_ctl.constraints == [] and sc._draw_arcs == []
    finally:
        close_view(view, sc)


def test_model_space_fillet_records_nothing(qapp):
    view, sc = make_view(role="plan", scale=1.0, mode=None)
    try:
        _add(sc, LineItem(QPointF(100, 0), QPointF(0, 0)), "_draw_lines")
        _add(sc, LineItem(QPointF(0, -100), QPointF(0, 0)), "_draw_lines")
        _fillet(view, sc, QPointF(0, 0))
        assert len(sc._draw_arcs) == 1 and sc.constraint_ctl.constraints == []
    finally:
        close_view(view, sc)


def test_block_editor_polyline_fillet_ties_both_pieces(qapp):
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        pl = PolylineItem(QPointF(0, 0)); pl.append_point(QPointF(100, 0)); pl.append_point(QPointF(100, -100))
        _add(sc, pl, "_polylines")
        _baseline(sc)
        _fillet(view, sc, QPointF(100, 0))
        a, b = sorted(sc._polylines, key=lambda q: q._points[0].x())
        arc = sc._draw_arcs[0]
        # vertex 1: previous edge -> T1 (90,0) ends piece a; next edge -> T2 (100,-10) starts piece b.
        # theta 90, edge 1 = -X, edge 2 = -Y: the arc starts at T1 (start_is_t1), ends at T2.
        assert _recs(sc) == [
            ("tangent", [(a._uid, "s0"), (arc._uid, "curve")]),
            ("tangent", [(b._uid, "s0"), (arc._uid, "curve")]),
            ("coincident", [(arc._uid, "start"), (a._uid, "v1")]),
            ("coincident", [(arc._uid, "end"), (b._uid, "v0")]),
        ]
        assert not sc.constraint_ctl.red
    finally:
        close_view(view, sc)


def test_block_editor_rect_fillet_ties_the_single_open_polyline(qapp):
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        _add(sc, RectangleItem(QPointF(0, 0), QPointF(100, -50)), "_draw_rects")
        _baseline(sc)
        _fillet(view, sc, QPointF(100, 0))
        (p,) = sc._polylines
        arc = sc._draw_arcs[0]
        # 5 points: v0 = T2 (90,0) ... v4 = T1 (100,-10); the arc starts at T2.
        assert _recs(sc) == [
            ("tangent", [(p._uid, "s0"), (arc._uid, "curve")]),
            ("tangent", [(p._uid, "s3"), (arc._uid, "curve")]),
            ("coincident", [(arc._uid, "start"), (p._uid, "v0")]),
            ("coincident", [(arc._uid, "end"), (p._uid, "v4")]),
        ]
        assert not sc.constraint_ctl.red
    finally:
        close_view(view, sc)


def _two_lines(sc):
    _add(sc, LineItem(QPointF(100, 0), QPointF(0, 0)), "_draw_lines")
    _add(sc, LineItem(QPointF(0, -100), QPointF(0, 0)), "_draw_lines")


def test_toggle_off_click_records_nothing(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        _two_lines(sc)
        _fillet(view, sc, QPointF(0, 0))
        assert len(sc._draw_arcs) == 1 and _recs(sc) == []            # geometry only
    finally:
        close_view(view, sc)


def test_toggle_off_shift_click_records(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        _two_lines(sc)
        _fillet(view, sc, QPointF(0, 0), mods=SHIFT)
        assert sorted(t for t, _ in _recs(sc)) == ["coincident", "coincident", "tangent", "tangent"]
    finally:
        close_view(view, sc)


def test_toggle_on_shift_click_records_nothing(qapp):
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    try:
        _two_lines(sc)
        _fillet(view, sc, QPointF(0, 0), mods=SHIFT)
        assert len(sc._draw_arcs) == 1 and _recs(sc) == []
    finally:
        close_view(view, sc)


def test_toggle_off_enter_records_nothing_toggle_on_enter_records(qapp):
    for on, n in ((False, 0), (True, 4)):
        QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, on)
        view, sc = make_view(role="block_editor", scale=1.0, mode=None)
        try:
            _two_lines(sc)
            sc._fillet_radius = 10.0
            sc._modify_ctl.start("fillet")
            move(view, QPointF(0, 0))
            QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
            assert len(sc._draw_arcs) == 1 and len(_recs(sc)) == n
        finally:
            close_view(view, sc)


def test_drop_at_removes_constraints_naming_an_end_without_an_undo_step(qapp):
    from firepro3d.model_space import Model_Space
    sc = Model_Space(scene_role="block_editor")
    a = LineItem(QPointF(100, 0), QPointF(0, 0)); b = LineItem(QPointF(0, -100), QPointF(0, 0))
    for ln in (a, b):
        sc.addItem(ln); sc._draw_lines.append(ln)
    ctl = sc.constraint_ctl
    ctl.add("coincident", [{"uid": a._uid, "h": "p2"}, {"uid": b._uid, "h": "p2"}])
    ctl.add("dim_distance", [{"uid": a._uid, "h": "edge"}])
    sc.push_undo_state()
    pos = sc._undo_pos
    assert ctl.drop_at([(a._uid, "p2")]) == 1
    assert [c.type for c in ctl.constraints] == ["dim_distance"]      # the edge dim names no end handle
    assert sc._undo_pos == pos                                       # no push
