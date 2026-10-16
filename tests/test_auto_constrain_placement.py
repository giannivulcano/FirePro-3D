"""AC1 E2E: line / polyline placement clicks on real snaps record joins
(AD2-AD8). Shown view, posted presses (mods on the event), real snap engine."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import CircleItem, LineItem
from tests._snap_polish_helpers import click, close_view, make_view, move

SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier


@pytest.fixture
def vs(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    sc.set_align_enabled(False)
    yield view, sc
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    close_view(view, sc)


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _draw(view, sc, a, b, ma=Qt.KeyboardModifier.NoModifier,
          mb=Qt.KeyboardModifier.NoModifier):
    sc.set_mode("draw_line")
    move(view, QPointF(*a), ma); click(view, QPointF(*a), ma)
    move(view, QPointF(*b), mb); click(view, QPointF(*b), mb)
    new = sc._draw_lines[-1]
    return new


def _recs(sc):
    return [(c.type, [(r.get("uid"), r.get("h"), r.get("ref")) for r in c.refs])
            for c in sc.constraint_ctl.constraints]


def test_endpoint_click_records_one_coincident(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    n = _draw(view, sc, (200, 0), (200, 150))
    assert _recs(sc) == [("coincident", [(n._uid, "p1", None), (a._uid, "p2", None)])]


def test_midpoint_and_centre_and_origin(vs):
    view, sc = vs
    a = _line(sc, (-300, 100), (-100, 100))
    c = CircleItem(QPointF(300, 0), 60.0); sc.addItem(c); sc._draw_circles.append(c)
    n = _draw(view, sc, (-200, 100), (300, 0))           # MID -> CEN
    m = _draw(view, sc, (0, 0), (0, -150))                # origin -> free
    assert _recs(sc) == [
        ("coincident", [(n._uid, "p1", None), (a._uid, "mid", None)]),
        ("coincident", [(n._uid, "p2", None), (c._uid, "center", None)]),
        ("coincident", [(m._uid, "p1", None), (None, None, "origin")])]


def test_nearest_on_an_edge_is_point_on_curve(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (300, 0))
    n = _draw(view, sc, (0, 200), (77, 0))
    assert _recs(sc) == [("point_on_curve", [(n._uid, "p2", None), (a._uid, "edge", None)])]


def test_perpendicular_snap_adds_perpendicular(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (300, 100))
    # Raw source: the foot of the perpendicular from (100, 300) onto the line
    # through (0,0)-(300,100): t = (100*300 + 300*100) / (300^2 + 100^2) = 0.6
    # -> (180, 60).
    n = _draw(view, sc, (100, 300), (180, 60))
    assert _recs(sc) == [
        ("point_on_curve", [(n._uid, "p2", None), (a._uid, "edge", None)]),
        ("perpendicular", [(n._uid, "edge", None), (a._uid, "edge", None)])]


def test_shift_inverts_both_ways(vs):
    view, sc = vs
    a = _line(sc, (50, 0), (250, 0))                      # off the origin snap
    _draw(view, sc, (250, 0), (250, 150), ma=SHIFT)       # ON + Shift -> none
    assert _recs(sc) == []
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    _draw(view, sc, (50, 0), (50, -150))                  # OFF -> none
    assert _recs(sc) == []
    n = _draw(view, sc, (150, 0), (150, -150), ma=SHIFT)  # OFF + Shift -> a.mid
    assert _recs(sc) == [("coincident", [(n._uid, "p1", None), (a._uid, "mid", None)])]


def test_ctrl_lock_off_the_snap_gets_no_join(vs):
    view, sc = vs
    _line(sc, (0, 0), (200, 0))
    _line(sc, (300, 37), (400, 37))
    n = _draw(view, sc, (200, 0), (300, 37), mb=CTRL)    # ~20 deg -> angle-locked
    assert math.hypot(n._pt2.x() - 300, n._pt2.y() - 37) > 1.0   # tip left its END snap
    assert [r[1][0][1] for r in _recs(sc)] == ["p1"]      # only click 1 joined


def test_typed_second_point_keeps_the_clicked_first(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    sc.set_mode("draw_line")
    move(view, QPointF(200, 0)); click(view, QPointF(200, 0))
    assert sc._geom_ctl._commit_draw_line_at(QPointF(200, 150))   # the HUD applier = typed
    n = sc._draw_lines[-1]
    assert _recs(sc) == [("coincident", [(n._uid, "p1", None), (a._uid, "p2", None)])]


def test_line_and_joins_are_one_undo_step(vs):
    view, sc = vs
    _line(sc, (0, 0), (200, 0))
    sc.push_undo_state()
    n_lines = len(sc._draw_lines)
    _draw(view, sc, (200, 0), (200, 150))
    assert len(sc.constraint_ctl.constraints) == 1
    sc.undo()
    QApplication.processEvents()
    assert len(sc._draw_lines) == n_lines and sc.constraint_ctl.constraints == []
    sc.redo()
    QApplication.processEvents()
    assert len(sc._draw_lines) == n_lines + 1 and len(sc.constraint_ctl.constraints) == 1


def test_plan_scene_records_nothing(qapp):
    view, sc = make_view(role="plan", scale=1.0, mode=None)
    try:
        sc.set_align_enabled(False)
        _line(sc, (0, 0), (200, 0))
        _draw(view, sc, (200, 0), (200, 150))
        assert sc.constraint_ctl.constraints == []
    finally:
        close_view(view, sc)


def _key(view, key):
    """Keys on the viewport, as the shipped placement tests post them
    (test_arc_convention_tools Return, test_block_instance_delete Delete):
    Return finishes, Delete pops, Esc cancels."""
    view.setFocus()
    QTest.keyClick(view.viewport(), key)
    QApplication.processEvents()


def _poly(view, sc, *pts, finish=Qt.Key.Key_Return):
    sc.set_mode("polyline")
    for p in pts:
        move(view, QPointF(*p)); click(view, QPointF(*p))
    if finish is not None:
        _key(view, finish)


def test_polyline_vertices_join_at_finish(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    b = _line(sc, (400, -100), (400, 300))
    _poly(view, sc, (200, 0), (300, 200), (400, 77))
    pl = sc._polylines[-1]
    assert _recs(sc) == [
        ("coincident", [(pl._uid, "v0", None), (a._uid, "p2", None)]),
        ("point_on_curve", [(pl._uid, "v2", None), (b._uid, "edge", None)])]


def test_no_join_recorded_mid_chain_and_esc_leaves_none(vs):
    view, sc = vs
    _line(sc, (0, 0), (200, 0))
    sc.set_mode("polyline")
    move(view, QPointF(200, 0)); click(view, QPointF(200, 0))
    move(view, QPointF(300, 200)); click(view, QPointF(300, 200))
    assert sc.constraint_ctl.constraints == []            # AD8: added at finish only
    _key(view, Qt.Key.Key_Escape)
    assert sc.constraint_ctl.constraints == [] and sc._polyline_active is None


def test_two_vertex_finish_joins_land_on_the_line(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    n0 = len(sc._draw_lines)
    _poly(view, sc, (200, 0), (300, 200))
    assert len(sc._draw_lines) == n0 + 1
    ln = sc._draw_lines[-1]
    assert _recs(sc) == [("coincident", [(ln._uid, "p1", None), (a._uid, "p2", None)])]


def test_delete_pop_drops_that_vertex_join(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    _line(sc, (500, 0), (700, 0))
    sc.set_mode("polyline")
    for p in ((200, 0), (300, 200), (500, 0)):            # v2 on b.p1 (joined)
        move(view, QPointF(*p)); click(view, QPointF(*p))
    _key(view, Qt.Key.Key_Delete)                         # pop v2 -> its target goes too
    # Re-place v2 at the SAME point with Shift (no inference): a stale v2
    # target left in the list would still match this point and join it.
    move(view, QPointF(500, 0), SHIFT); click(view, QPointF(500, 0), SHIFT)
    _key(view, Qt.Key.Key_Return)
    pl = sc._polylines[-1]
    assert _recs(sc) == [("coincident", [(pl._uid, "v0", None), (a._uid, "p2", None)])]


def test_close_on_start_adds_no_extra_join(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    _poly(view, sc, (200, 0), (300, 200), (100, 200), (200, 0), finish=None)
    pl = sc._polylines[-1]
    assert pl.is_closed()
    assert _recs(sc) == [("coincident", [(pl._uid, "v0", None), (a._uid, "p2", None)])]
