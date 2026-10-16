"""AC1 AD9: auto_join adds clean records, drops refused / red / redundant
ones silently, and never pushes an undo step."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import close_view, make_view


@pytest.fixture
def sc(qapp):
    view, s = make_view(role="block_editor", scale=1.0, mode="select")
    s._status_log = []
    s._show_status = lambda msg, timeout=0: s._status_log.append(msg)
    yield s
    close_view(view, s)


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _p(it, h):
    return {"uid": it._uid, "h": h}


def test_clean_join_is_kept_and_no_undo_is_pushed(sc):
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (100, 0), (100, 80))
    ctl = sc.constraint_ctl
    pushes = []
    sc.push_undo_state = lambda *a_, **k: pushes.append(1)
    kept = ctl.auto_join([("coincident", [_p(b, "p1"), _p(a, "p2")])])
    assert [c.type for c in kept] == ["coincident"]
    assert [c.type for c in ctl.constraints] == ["coincident"]
    assert pushes == [] and sc._status_log == []


def test_redundant_join_is_dropped_silently(sc):
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (100, 0), (100, 80))
    ctl = sc.constraint_ctl
    ctl.add("coincident", [_p(b, "p1"), _p(a, "p2")])
    sc._status_log.clear()
    assert ctl.auto_join([("coincident", [_p(a, "p2"), _p(b, "p1")])]) == []
    assert len(ctl.constraints) == 1 and sc._status_log == []


def test_refused_join_posts_no_status(sc):
    a = _line(sc, (0, 0), (100, 0))
    ctl = sc.constraint_ctl
    # D44: a line's own end on its own edge holds by construction -> refused.
    assert ctl.auto_join([("point_on_curve", [_p(a, "p1"), _p(a, "edge")])]) == []
    assert ctl.constraints == [] and sc._status_log == []


def test_conflicting_join_is_dropped_and_geometry_held(sc):
    a = _line(sc, (0, 0), (100, 0))
    ctl = sc.constraint_ctl
    ctl.add("fix", [{"uid": a._uid, "h": "item"}])
    sc._status_log.clear()
    before = (a._pt1.x(), a._pt1.y(), a._pt2.x(), a._pt2.y())
    assert ctl.auto_join([("coincident", [_p(a, "p1"), {"ref": "origin"}]),
                          ("coincident", [_p(a, "p2"), {"ref": "origin"}])]) == []
    assert [c.type for c in ctl.constraints] == ["fix"]
    assert not ctl.red
    assert (a._pt1.x(), a._pt1.y(), a._pt2.x(), a._pt2.y()) == before
    assert sc._status_log == []


def test_a_failing_join_is_dropped_and_the_rest_kept(sc):
    """M1: an exception inside one add never breaks the placement -- that
    record is dropped (nothing left appended), the next is still added."""
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (100, 0), (100, 80))
    ctl = sc.constraint_ctl
    real_add = ctl.add
    calls = []

    def flaky(ctype, refs, **kw):
        calls.append(ctype)
        if len(calls) == 1:
            ctl.constraints.append(type("Half", (), {"id": "half"})())   # appended, then boom
            ctl.red.add("half")
            raise RuntimeError("solver blew up")
        return real_add(ctype, refs, **kw)

    ctl.add = flaky
    try:
        kept = ctl.auto_join([("coincident", [_p(b, "p1"), _p(a, "p2")]),
                              ("coincident", [_p(b, "p1"), _p(a, "p2")])])
    finally:
        del ctl.add
    assert [c.type for c in kept] == ["coincident"]
    assert [c.type for c in ctl.constraints] == ["coincident"]
    assert "half" not in ctl.red
    assert ctl._mute == 0 and sc._status_log == []


def test_a_raise_after_add_drops_that_join_too(sc):
    """The guard spans the whole per-record body: a raise in the redundancy
    check (diagnostics) drops the just-added record instead of aborting."""
    a = _line(sc, (0, 0), (100, 0)); b = _line(sc, (100, 0), (100, 80))
    ctl = sc.constraint_ctl

    def boom():
        raise RuntimeError("diagnostics blew up")

    ctl.diagnostics = boom
    try:
        kept = ctl.auto_join([("coincident", [_p(b, "p1"), _p(a, "p2")])])
    finally:
        del ctl.diagnostics
    assert kept == [] and ctl.constraints == [] and not ctl.red
    assert ctl._mute == 0
