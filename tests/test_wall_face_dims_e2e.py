"""Constraints between wall faces (design 2026-10-30) -- AC1 / AC2 / AC5 / WF9
on the shown MainWindow: the real Smart Dimension button, posted face clicks,
the value HUD, a real host grip drag (tests/test_plan_constraints_e2e.py
pattern)."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from firepro3d.constraint_controller import DIM_WALL_THICKNESS_STATUS
from firepro3d.wall import WallSegment
from tests.test_build_editor_tabs import _editors, _plan_index, mw  # noqa: F401
from tests.test_constraint_e2e import _click
from tests.test_plan_constraints_e2e import plan  # noqa: F401
from tests.test_auto_constrain_wall import _drag_raw


def _wall(sc, a, b, thick=200.0):
    w = WallSegment(QPointF(*a), QPointF(*b), thickness_mm=thick)
    sc.addItem(w)
    sc._walls.append(w)
    w.invalidate_geometry()
    return w


def _dist_to_line(p, a, b) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    return abs((p.x() - a.x()) * dy - (p.y() - a.y()) * dx) / math.hypot(dx, dy)


def _pick_two_faces(mw, sc, view, qapp, first, second):
    """Smart Dimension with nothing selected (pick mode), then two posted clicks."""
    sc.clearSelection()
    qapp.processEvents()
    mw._be_constrain_buttons["Smart Dimension"].click()       # the REAL button
    qapp.processEvents()
    assert sc.mode == "constrain_dim_distance"
    _click(view, view.mapFromScene(first))
    _click(view, view.mapFromScene(second))


def test_ac1_face_to_face_smart_dimension_through_the_real_button(mw, plan, qapp):
    sc, view = plan
    ctl = sc.constraint_ctl
    # 400 thick (faces 200 mm = ~21 px off the centerline at the plan fit: no pick ambiguity)
    a = _wall(sc, (0, 0), (4000, 0), thick=400.0)              # faces y = +200 (face_l) / -200
    b = _wall(sc, (0, 1500), (3000, 1500), thick=400.0)        # faces y = 1700 (face_l) / 1300 (face_r)
    qa, qb = a.quad_points(), b.quad_points()                  # p1l, p1r, p2r, p2l
    assert qa[0].y() == pytest.approx(200.0) and qb[1].y() == pytest.approx(1300.0)
    _pick_two_faces(mw, sc, view, qapp, QPointF(1000.0, qa[0].y()), QPointF(1000.0, qb[1].y()))
    p = ctl.pick
    assert p is not None and p.pending_type == "dim_point_line"
    assert p.pending == [{"uid": b._uid, "h": "mid_r"}, {"uid": a._uid, "h": "face_l"}]
    _click(view, view.mapFromScene(QPointF(-600.0, 750.0)))    # the placement click, left of the walls
    dims = [c for c in ctl.constraints_on(b) if c.type == "dim_point_line"]
    assert len(dims) == 1
    assert dims[0].value == pytest.approx(1100.0)              # clear: 1300 - 200
    assert sc.readouts.is_editing(), "no value HUD after the placement click"
    (field,) = sc.readouts.hud.field_names()
    ed = sc.readouts.hud.editor(field)
    ed.selectAll()
    QTest.keyClicks(ed, "1500")
    QTest.keyClick(ed, Qt.Key.Key_Return)
    qapp.processEvents()
    assert not sc.readouts.is_editing()
    # B moved +400 (1500 - 1100) along +y, both ends; A holds
    assert (b._pt1.x(), b._pt1.y()) == pytest.approx((0.0, 1900.0), abs=1e-6)
    assert (b._pt2.x(), b._pt2.y()) == pytest.approx((3000.0, 1900.0), abs=1e-6)
    assert (a._pt1.x(), a._pt1.y(), a._pt2.x(), a._pt2.y()) == pytest.approx((0.0, 0.0, 4000.0, 0.0), abs=1e-6)
    sc.set_mode("select")


def test_ac2_same_wall_faces_post_the_thickness_status_and_keep_the_tool_live(mw, plan, qapp, monkeypatch):
    sc, view = plan
    ctl = sc.constraint_ctl
    msgs = []
    monkeypatch.setattr(sc, "_show_status", lambda msg, timeout=5000: msgs.append(msg))
    a = _wall(sc, (0, 0), (4000, 0), thick=400.0)
    qa = a.quad_points()
    _pick_two_faces(mw, sc, view, qapp, QPointF(1000.0, qa[0].y()), QPointF(1000.0, qa[1].y()))
    assert msgs and msgs[-1] == DIM_WALL_THICKNESS_STATUS, msgs
    assert ctl.constraints_on(a) == []                         # no record
    assert sc.mode == "constrain_dim_distance"                 # tool live ...
    p = ctl.pick
    assert p is not None and p.pending is None and p.picks == []   # ... and the pick reset
    assert not sc.readouts.is_editing()
    sc.set_mode("select")


def test_ac5_host_grip_drag_carries_a_face_tied_end(mw, plan, qapp):
    sc, view = plan
    ctl = sc.constraint_ctl
    a = _wall(sc, (0, 0), (4000, 0))                           # host, 200 thick: face_l y = +100
    y = a.quad_points()[0].y()
    b = _wall(sc, (2000, 1500), (2000, y))                     # partition ending ON face_l
    c = ctl.add("point_on_curve", [{"uid": b._uid, "h": "p2"}, {"uid": a._uid, "h": "face_l"}])
    assert c is not None and c.id not in ctl.red
    qapp.processEvents()
    sc.clearSelection()
    a.setSelected(True)
    qapp.processEvents()
    end = QPointF(a._pt2)
    _drag_raw(sc, view, end, QPointF(end.x(), end.y() + 600.0))    # swing the host end 600 mm
    assert (a._pt2 - end).manhattanLength() > 100.0, "the host grip did not move"
    q = a.quad_points()
    assert _dist_to_line(b._pt2, q[0], q[3]) < 1e-3, "tied end is off the new face line"   # Newton 1e-3
    assert (b._pt2 - QPointF(2000.0, y)).manhattanLength() > 50.0, "tied end did not follow"
    assert c.id not in ctl.red


def test_wf9_sliding_the_host_off_span_leaves_the_end_on_the_line_not_red(mw, plan, qapp):
    sc, view = plan
    ctl = sc.constraint_ctl
    a = _wall(sc, (0, 0), (4000, 0))
    y = a.quad_points()[0].y()
    b = _wall(sc, (2000, 1500), (2000, y))
    c = ctl.add("point_on_curve", [{"uid": b._uid, "h": "p2"}, {"uid": a._uid, "h": "face_l"}])
    assert c is not None
    qapp.processEvents()
    sc.clearSelection()
    a.setSelected(True)
    qapp.processEvents()
    end = QPointF(a._pt2)
    _drag_raw(sc, view, end, QPointF(1500.0, end.y()))        # along the host axis: span now 0..1500
    assert a._pt2.x() < 1600.0, a._pt2
    assert b._pt2.x() == pytest.approx(2000.0, abs=1e-3)      # past the host corner: no clamp
    assert b._pt2.y() == pytest.approx(y, abs=1e-3)           # still on the face's infinite line
    assert c.id not in ctl.red                                # no red state
