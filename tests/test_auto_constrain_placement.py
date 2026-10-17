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
    n = _draw(view, sc, (200, 0), (260, 150))
    assert _recs(sc) == [("coincident", [(n._uid, "p1", None), (a._uid, "p2", None)])]


def test_midpoint_and_centre_and_origin(vs):
    view, sc = vs
    a = _line(sc, (-300, 100), (-100, 100))
    c = CircleItem(QPointF(300, 0), 60.0); sc.addItem(c); sc._draw_circles.append(c)
    n = _draw(view, sc, (-200, 100), (300, 0))           # MID -> CEN
    m = _draw(view, sc, (0, 0), (90, -150))                # origin -> free
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
    _draw(view, sc, (250, 0), (310, 150), ma=SHIFT)       # ON + Shift -> none
    assert _recs(sc) == []
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    _draw(view, sc, (50, 0), (110, -150))                  # OFF -> none
    assert _recs(sc) == []
    n = _draw(view, sc, (150, 0), (210, -150), ma=SHIFT)  # OFF + Shift -> a.mid
    assert _recs(sc) == [("coincident", [(n._uid, "p1", None), (a._uid, "mid", None)])]


def test_ctrl_lock_off_the_snap_gets_no_join(vs):
    view, sc = vs
    _line(sc, (0, 0), (200, 0))
    _line(sc, (300, 120), (400, 120))
    n = _draw(view, sc, (200, 0), (300, 120), mb=CTRL)   # ~50 deg -> locked 45
    assert math.hypot(n._pt2.x() - 300, n._pt2.y() - 120) > 1.0   # tip left its END snap
    assert [r[1][0][1] for r in _recs(sc)] == ["p1"]      # only click 1 joined


def test_typed_second_point_keeps_the_clicked_first(vs):
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    sc.set_mode("draw_line")
    move(view, QPointF(200, 0)); click(view, QPointF(200, 0))
    assert sc._geom_ctl._commit_draw_line_at(QPointF(260, 150))   # the HUD applier = typed
    n = sc._draw_lines[-1]
    assert _recs(sc) == [("coincident", [(n._uid, "p1", None), (a._uid, "p2", None)])]


def test_line_and_joins_are_one_undo_step(vs):
    view, sc = vs
    _line(sc, (0, 0), (200, 0))
    sc.push_undo_state()
    n_lines = len(sc._draw_lines)
    _draw(view, sc, (200, 0), (260, 150))
    assert len(sc.constraint_ctl.constraints) == 1
    sc.undo()
    QApplication.processEvents()
    assert len(sc._draw_lines) == n_lines and sc.constraint_ctl.constraints == []
    sc.redo()
    QApplication.processEvents()
    assert len(sc._draw_lines) == n_lines + 1 and len(sc.constraint_ctl.constraints) == 1


def _press_event(mods=Qt.KeyboardModifier.NoModifier):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QMouseEvent
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0), QPointF(0, 0),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods)


def test_inference_is_editor_only(vs, qapp):
    """The plan scene refuses 2D placement outright (containment C1), so the
    guard is at the capture: a plan scene's press never infers; the editor's
    does (same event, toggle ON)."""
    _view, sc = vs
    assert sc._geom_ctl._auto_infer(_press_event()) is True
    assert sc._geom_ctl._hv_on(None) is True                  # AC2: typed = the toggle
    pview, psc = make_view(role="plan", scale=1.0, mode=None)
    try:
        assert psc.constraint_ctl.enabled is False
        assert psc._geom_ctl._auto_infer(_press_event()) is False
        assert psc._geom_ctl._hv_on(None) is False            # AC2: editor only
    finally:
        close_view(pview, psc)


def test_gridline_clicks_never_join(vs):
    """A draw_gridline click 1 keeps no target (the anchor survives a switch
    to draw_line, so a stale gridline target must not exist to carry over)."""
    view, sc = vs
    _line(sc, (0, 0), (200, 0))
    sc.set_mode("draw_gridline")
    if sc.mode != "draw_gridline":
        pytest.skip("draw_gridline is refused in this scene role")
    move(view, QPointF(200, 0)); click(view, QPointF(200, 0))
    assert sc._geom_ctl._line_anchor_join is None


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
    _poly(view, sc, (200, 0), (300, 200), (100, 230), (200, 0), finish=None)
    pl = sc._polylines[-1]
    assert pl.is_closed()
    assert _recs(sc) == [("coincident", [(pl._uid, "v0", None), (a._uid, "p2", None)])]


def test_typed_polyline_vertex_gets_no_join(vs):
    """AD5: a vertex typed in the HUD carries no join even when the cursor's
    live snap sits exactly on it; the clicked vertices keep theirs."""
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    _line(sc, (500, 60), (700, 60))
    sc.set_mode("polyline")
    move(view, QPointF(200, 0)); click(view, QPointF(200, 0))      # v0 on a.p2
    move(view, QPointF(500, 60))                                    # live END snap on b.p1
    assert sc._snap_result is not None
    assert sc._geom_ctl._commit_polyline_at(QPointF(500, 60))      # typed v1 (HUD applier)
    _key(view, Qt.Key.Key_Return)
    ln = sc._draw_lines[-1]                                         # 2-vertex -> a line
    assert _recs(sc) == [("coincident", [(ln._uid, "p1", None), (a._uid, "p2", None)])]


def test_esc_then_new_chain_reuses_no_target(vs):
    """A cancelled chain's targets never reach the next chain: its v0 re-placed
    at the old v0's point (Shift: no inference) records nothing."""
    view, sc = vs
    _line(sc, (0, 0), (200, 0))
    sc.set_mode("polyline")
    move(view, QPointF(200, 0)); click(view, QPointF(200, 0))      # joined v0
    move(view, QPointF(300, 200)); click(view, QPointF(300, 200))
    _key(view, Qt.Key.Key_Escape)
    sc.set_mode("polyline")
    move(view, QPointF(200, 0), SHIFT); click(view, QPointF(200, 0), SHIFT)
    move(view, QPointF(300, -200)); click(view, QPointF(300, -200))
    move(view, QPointF(450, -250)); click(view, QPointF(450, -250))
    _key(view, Qt.Key.Key_Return)
    assert _recs(sc) == []


def test_circle_rim_click_is_point_on_curve(vs):
    """A NEA click on a circle outline puts the new end on the full circle."""
    view, sc = vs
    c = CircleItem(QPointF(300, 0), 80.0); sc.addItem(c); sc._draw_circles.append(c)
    # 60 deg on the rim (340, 69.282): a NEA point (45 deg reports TAN here).
    n = _draw(view, sc, (500, 300), (340.0, 69.2820323))
    assert _recs(sc) == [("point_on_curve", [(n._uid, "p2", None), (c._uid, "curve", None)])]


def test_reference_line_joins_like_a_line(vs):
    """A reference line is a draw_line placement stamped by Space (RG6)."""
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    sc.set_mode("draw_line")
    _key(view, Qt.Key.Key_Space)                          # placement -> reference
    move(view, QPointF(200, 0)); click(view, QPointF(200, 0))
    move(view, QPointF(260, 150)); click(view, QPointF(260, 150))
    n = sc._draw_lines[-1]
    assert getattr(n, "reference", False) is True
    assert _recs(sc) == [("coincident", [(n._uid, "p1", None), (a._uid, "p2", None)])]


def test_double_click_finish_keeps_the_clicked_joins(vs):
    """Double-click finish drops the extra press's vertex (and its target)."""
    from PyQt6.QtCore import QEvent
    from tests._snap_polish_helpers import post
    view, sc = vs
    a = _line(sc, (0, 0), (200, 0))
    b = _line(sc, (500, 0), (700, 0))
    sc.set_mode("polyline")
    for p in ((200, 0), (300, 200), (500, 0)):            # v0 on a.p2, v2 on b.p1
        move(view, QPointF(*p)); click(view, QPointF(*p))
    move(view, QPointF(700, 0)); click(view, QPointF(700, 0))      # press 1 of the double
    post(view, QEvent.Type.MouseButtonDblClick, QPointF(700, 0))
    post(view, QEvent.Type.MouseButtonRelease, QPointF(700, 0))
    pl = sc._polylines[-1]
    assert len(pl._points) == 3                           # the double-click vertex dropped
    assert _recs(sc) == [
        ("coincident", [(pl._uid, "v0", None), (a._uid, "p2", None)]),
        ("coincident", [(pl._uid, "v2", None), (b._uid, "p1", None)])]


def test_polyline_and_joins_are_one_undo_step(vs):
    view, sc = vs
    _line(sc, (0, 0), (200, 0))
    sc.push_undo_state()
    n_pl = len(sc._polylines)
    _poly(view, sc, (200, 0), (300, 200), (450, 100))
    assert len(sc.constraint_ctl.constraints) == 1
    sc.undo()
    QApplication.processEvents()
    assert len(sc._polylines) == n_pl and sc.constraint_ctl.constraints == []
