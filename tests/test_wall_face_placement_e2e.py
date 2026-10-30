"""Constraints between wall faces (design 2026-10-30) -- WF5 / WF6 / WF7, AC3,
AC4, AC8: wall ends joined to a host FACE through the real press path on the
shown MainWindow (plan tab). The OSNAP pick is staged: ``scene._snap_engine.find``
is replaced for the placement so the press lands exactly on the named face
target -- ``Model_Space.get_effective_position`` stores the result as
``scene._snap_result``, the read ``WallPlacementController._press_wall``
performs (WF5). Record kinds, handles and the gate are asserted as literals
(never read back from the code under test)."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.constants import AUTO_JOIN_TOLERANCE, TEE_TOLERANCE
from firepro3d.snap_engine import OsnapResult
from firepro3d.wall import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, WallSegment
from tests.test_build_editor_tabs import _editors, _plan_index, mw  # noqa: F401
from tests.test_plan_constraints_e2e import plan  # noqa: F401
from tests.test_auto_constrain_wall import (_cleanup_walls, _edge_of, _handle_of,  # noqa: F401
                                            _mine, _press, toggle)


def _host(sc, a, b, align=ALIGN_CENTER, thick=200.0):
    w = WallSegment(QPointF(*a), QPointF(*b), thickness_mm=thick)
    w._alignment = align
    sc.addItem(w)
    sc._walls.append(w)
    w.invalidate_geometry()
    return w


class _Staged:
    """``SnapEngine.find`` stand-in: *result* when the cursor is within *radius*
    scene mm of its point, else None (no snap: the raw click)."""

    def __init__(self, result, radius=50.0):
        self.result, self.radius = result, radius

    def __call__(self, cursor_scene, *args, **kwargs):
        if self.result is None:
            return None
        d = math.hypot(cursor_scene.x() - self.result.point.x(),
                       cursor_scene.y() - self.result.point.y())
        return self.result if d <= self.radius else None


def _press_mods(view, pt, mods):
    """``_press`` with explicit keyboard modifiers (Ctrl angle-constrain)."""
    vp = view.viewport()
    p = view.mapFromScene(pt)
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(vp, QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                               Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods))


def _place(sc, view, monkeypatch, a, b, staged, align=ALIGN_CENTER, shift=False,
           ctrl_end=False, radius=50.0):
    """One line wall a -> b through the real press path with the OSNAP pick staged.
    *ctrl_end*: the end press holds Ctrl (angle constrain); *radius*: the staged pick's reach."""
    assert sc._snap_enabled, "cursor snap must be live for the press to read a snap"
    tmpl = sc._get_wall_template()
    old_t, old_s = tmpl._alignment, sc._wall_alignment
    sc._wall_alignment = align                      # set_mode('wall') re-syncs the template from it
    tmpl._alignment = align
    n0 = len(sc._walls)
    monkeypatch.setattr(sc._snap_engine, "find", _Staged(staged, radius))
    try:
        sc.set_mode("wall")                         # default primitive: line
        _press(view, a, shift)
        if ctrl_end:
            _press_mods(view, b, Qt.KeyboardModifier.ControlModifier)
        else:
            _press(view, b, shift)
        sc.set_mode("select")
    finally:
        monkeypatch.undo()
        tmpl._alignment = old_t
        sc._wall_alignment = old_s
    return sc._walls[n0:]


def _names(mine):
    return {r.get("h") for _t, refs in mine for r in refs}


# The face / corner AWAY from the host's click line, with its quad_points index
# (order p1l, p1r, p2r, p2l). Left: click line = face_r; Right: click line = face_l.
_FAR_FACE = {ALIGN_CENTER: ("face_l", 0), ALIGN_LEFT: ("face_l", 0), ALIGN_RIGHT: ("face_r", 1)}
_FAR_CORNER = {ALIGN_CENTER: ("p2l", 3), ALIGN_LEFT: ("p2l", 3), ALIGN_RIGHT: ("p2r", 2)}


@pytest.mark.parametrize("host_align", [ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT])
@pytest.mark.parametrize("snap_type", ["nearest", "perpendicular", "midpoint"])
def test_ac3_end_on_a_host_face_line_or_midpoint(mw, plan, qapp, toggle, monkeypatch,
                                                 host_align, snap_type):
    sc, view = plan
    toggle(True)
    host = _host(sc, (0, 0), (4000, 0), host_align)          # 200 thick: faces 100 / 200 mm off the click line
    new = []
    try:
        face, qi = _FAR_FACE[host_align]
        q = host.quad_points()
        y = q[qi].y()                                        # the face line is y = that corner's y
        assert abs(y) > TEE_TOLERANCE, y                     # today's Pass 2 cannot reach it
        x = (q[0].x() + q[3].x()) / 2.0 if snap_type == "midpoint" else 1000.0
        click = QPointF(x, y)
        staged = OsnapResult(point=QPointF(click), snap_type=snap_type, source_item=host)
        start = QPointF(x, 1500.0 if y > 0 else -1500.0)     # on the face's side: never through the host body
        new = _place(sc, view, monkeypatch, start, click, staged)
        assert len(new) == 1
        w = new[0]
        # Every snap (PER included: it only places the click) holds the end exactly.
        assert (w._pt2 - click).manhattanLength() <= 1e-9, "the end moved off the face click"
        mine = _mine(sc, w, host)
        want = ("point_on_curve", [{"uid": w._uid, "h": _handle_of(w, 2)},
                                  {"uid": host._uid, "h": face}])
        assert want in mine, mine
        per = ("perpendicular", [{"uid": w._uid, "h": _edge_of(w)}, {"uid": host._uid, "h": face}])
        assert per not in mine, mine                         # smoke ruling: no PER row
        assert all(c[0] != "perpendicular" for c in mine), mine
    finally:
        _cleanup_walls(sc, new + [host])


def test_ac3_start_on_a_host_face_line(mw, plan, qapp, toggle, monkeypatch):
    sc, view = plan
    toggle(True)
    host = _host(sc, (0, 0), (4000, 0))
    new = []
    try:
        y = host.quad_points()[0].y()                        # face_l (Center: +100)
        click = QPointF(1000.0, y)
        staged = OsnapResult(point=QPointF(click), snap_type="nearest", source_item=host)
        new = _place(sc, view, monkeypatch, click, QPointF(1000.0, 1500.0), staged)
        w = new[0]
        assert (w._pt1 - click).manhattanLength() < 1e-9
        assert ("point_on_curve", [{"uid": w._uid, "h": _handle_of(w, 1)},
                                  {"uid": host._uid, "h": "face_l"}]) in _mine(sc, w, host)
    finally:
        _cleanup_walls(sc, new + [host])


@pytest.mark.parametrize("new_align", [ALIGN_LEFT, ALIGN_RIGHT])
def test_ac3_left_right_new_wall_records_its_drawn_handle(mw, plan, qapp, toggle, monkeypatch, new_align):
    sc, view = plan
    toggle(True)
    host = _host(sc, (0, 0), (4000, 0))
    new = []
    try:
        y = host.quad_points()[0].y()
        click = QPointF(1000.0, y)
        staged = OsnapResult(point=QPointF(click), snap_type="nearest", source_item=host)
        new = _place(sc, view, monkeypatch, QPointF(1000.0, 1500.0), click, staged, align=new_align)
        w = new[0]
        assert w._alignment == new_align
        assert (w._pt2 - click).manhattanLength() < 1e-9
        h2 = {ALIGN_LEFT: "p2r", ALIGN_RIGHT: "p2l"}[new_align]       # PD1 literal
        assert ("point_on_curve", [{"uid": w._uid, "h": h2}, {"uid": host._uid, "h": "face_l"}]) in _mine(sc, w, host)
    finally:
        _cleanup_walls(sc, new + [host])


@pytest.mark.parametrize("toggle_v,shift,on", [(True, False, True), (True, True, False),
                                             (False, False, False), (False, True, True)])
def test_ac3_face_join_honours_the_toggle_xor_shift_gate(mw, plan, qapp, toggle, monkeypatch,
                                                         toggle_v, shift, on):
    sc, view = plan
    toggle(toggle_v)
    host = _host(sc, (0, 0), (4000, 0))
    new = []
    try:
        y = host.quad_points()[0].y()
        click = QPointF(1000.0, y)
        staged = OsnapResult(point=QPointF(click), snap_type="nearest", source_item=host)
        new = _place(sc, view, monkeypatch, QPointF(1000.0, 1500.0), click, staged, shift=shift)
        w = new[0]
        assert (w._pt2 - click).manhattanLength() < 1e-9      # geometry first: the click holds either way
        assert bool(_mine(sc, w, host)) == on, _mine(sc, w, host)
    finally:
        _cleanup_walls(sc, new + [host])


@pytest.mark.parametrize("host_align", [ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT])
def test_ac4_end_on_a_host_face_corner(mw, plan, qapp, toggle, monkeypatch, host_align):
    sc, view = plan
    toggle(True)
    host = _host(sc, (0, 0), (4000, 0), host_align)
    new = []
    try:
        hname, qi = _FAR_CORNER[host_align]
        corner = QPointF(host.quad_points()[qi])
        # precondition: the far corner is 100 (Center) / 200 (Left, Right) mm from the
        # click-line end -- outside AUTO_JOIN_TOLERANCE, so Pass 1 cannot claim it
        assert math.hypot(corner.x() - host._pt2.x(), corner.y() - host._pt2.y()) > AUTO_JOIN_TOLERANCE
        staged = OsnapResult(point=QPointF(corner), snap_type="endpoint", source_item=host,
                             name="face-corner-B")
        start = QPointF(corner.x(), corner.y() + (1500.0 if corner.y() >= 0 else -1500.0))
        new = _place(sc, view, monkeypatch, start, corner, staged)
        w = new[0]
        assert (w._pt2 - corner).manhattanLength() < 1e-9, "the end moved off the corner"
        mine = _mine(sc, w, host)
        assert ("coincident", [{"uid": w._uid, "h": _handle_of(w, 2)},
                               {"uid": host._uid, "h": hname}]) in mine, mine
        assert not any(t == "point_on_curve" for t, _r in mine), mine
    finally:
        _cleanup_walls(sc, new + [host])


def test_ac8_an_end_inside_the_join_radius_takes_pass_1_over_the_corner(mw, plan, qapp, toggle, monkeypatch):
    sc, view = plan
    toggle(True)
    # 30 thick: half 15 mm -> the quad corners sit 15 mm from the click-line ends,
    # INSIDE AUTO_JOIN_TOLERANCE (20): Pass 1 (endpoint join) must win over 1b
    host = _host(sc, (0, 0), (4000, 0), ALIGN_CENTER, thick=30.0)
    new = []
    try:
        corner = QPointF(host.quad_points()[3])              # p2l
        assert 0.0 < math.hypot(corner.x() - host._pt2.x(), corner.y() - host._pt2.y()) < AUTO_JOIN_TOLERANCE
        staged = OsnapResult(point=QPointF(corner), snap_type="endpoint", source_item=host)
        new = _place(sc, view, monkeypatch, QPointF(4000.0, 1500.0), corner, staged)
        w = new[0]
        assert (w._pt2 - host._pt2).manhattanLength() < 1e-9, "Pass 1 did not snap the end onto the host end"
        mine = _mine(sc, w, host)
        assert ("coincident", [{"uid": w._uid, "h": "p2"}, {"uid": host._uid, "h": "p2"}]) in mine, mine
        assert "p2l" not in _names(mine), mine                # 1b did not also fire
    finally:
        _cleanup_walls(sc, new + [host])


def test_wf7_thin_host_named_face_click_stays_on_the_face(mw, plan, qapp, toggle, monkeypatch):
    sc, view = plan
    toggle(True)
    # 60 thick: half 30 < TEE_TOLERANCE (40) -- Pass 2 used to pull a face click to the centerline
    host = _host(sc, (0, 0), (4000, 0), ALIGN_CENTER, thick=60.0)
    new = []
    try:
        y = host.quad_points()[0].y()                        # face_l: +30
        assert 0.0 < abs(y) < TEE_TOLERANCE
        named = QPointF(2000.0, y)
        staged = OsnapResult(point=QPointF(named), snap_type="nearest", source_item=host)
        new = _place(sc, view, monkeypatch, QPointF(2000.0, 1500.0), named, staged)
        w = new[0]
        assert w._pt2.y() == pytest.approx(y, abs=1e-9), "the named face click was pulled to the centerline"
        assert ("point_on_curve", [{"uid": w._uid, "h": "p2"}, {"uid": host._uid, "h": "face_l"}]) in _mine(sc, w, host)
        # an UNNAMED click at the same offset (no OSNAP): today's Pass 2 tee, unchanged
        new += _place(sc, view, monkeypatch, QPointF(1000.0, 1500.0), QPointF(1000.0, y), None)
        w2 = new[1]
        assert w2._pt2.y() == pytest.approx(0.0, abs=1e-9)   # pulled onto the click line
        assert ("point_on_curve", [{"uid": w2._uid, "h": "p2"}, {"uid": host._uid, "h": "edge"}]) in _mine(sc, w2, host)
    finally:
        _cleanup_walls(sc, new + [host])


def test_s1_a_hidden_host_face_target_is_dropped(mw, plan, qapp, toggle, monkeypatch):
    sc, view = plan
    toggle(True)
    host = _host(sc, (0, 0), (4000, 0))
    new = []
    try:
        host.setVisible(False)
        assert not host.isVisible()
        y = host.quad_points()[0].y()
        click = QPointF(1000.0, y)
        staged = OsnapResult(point=QPointF(click), snap_type="nearest", source_item=host)
        new = _place(sc, view, monkeypatch, QPointF(1000.0, 1500.0), click, staged)
        w = new[0]
        assert (w._pt2 - click).manhattanLength() < 1e-9
        assert not any(host._uid in {r.get("uid") for r in refs}
                       for _t, refs in _mine(sc, w, host)), "a hidden host was recorded as a target"
    finally:
        host.setVisible(True)
        _cleanup_walls(sc, new + [host])


def test_i1_a_ctrl_constrained_end_off_the_face_records_nothing(mw, plan, qapp, toggle, monkeypatch):
    sc, view = plan
    toggle(True)
    host = _host(sc, (0, 0), (4000, 0))
    new = []
    try:
        y = host.quad_points()[0].y()                        # face_l: +100
        click = QPointF(2500.0, y)
        staged = OsnapResult(point=QPointF(click), snap_type="nearest", source_item=host)
        new = _place(sc, view, monkeypatch, QPointF(1000.0, 1500.0), click, staged, ctrl_end=True)
        w = new[0]
        # precondition: Ctrl angle-constrain moved the committed end off the named face point
        assert (w._pt2 - click).manhattanLength() > 5.0, w._pt2
        assert not any(host._uid in {r.get("uid") for r in refs}
                       for _t, refs in _mine(sc, w, host)), _mine(sc, w, host)
    finally:
        _cleanup_walls(sc, new + [host])


def test_i1_a_close_loop_end_off_the_face_records_nothing(mw, plan, qapp, toggle, monkeypatch):
    sc, view = plan
    toggle(True)
    host = _host(sc, (0, 0), (4000, 0))
    new = []
    try:
        px = 1.0 / view.transform().m11()                    # scene mm per screen pixel
        y = host.quad_points()[0].y()                        # face_l: +100
        face_pt = QPointF(1000.0, y)
        staged = OsnapResult(point=QPointF(face_pt), snap_type="nearest", source_item=host)
        # the start sits 10 px off the face point (outside the staged pick's 4 px reach, so
        # it names nothing); the end click names the face point, within the 15 px close-loop
        # radius of the start -> the tip jumps to the chain start, off the named point
        start = QPointF(1000.0, y + 10.0 * px)
        new = _place(sc, view, monkeypatch, start, face_pt, staged, radius=4.0 * px)
        assert len(new) == 1
        w = new[0]
        assert not any(host._uid in {r.get("uid") for r in refs}
                       for _t, refs in _mine(sc, w, host)), _mine(sc, w, host)
        # the end closed onto the chain start (a recorded face join would have solved it away)
        assert (w._pt2 - w._pt1).manhattanLength() < 1e-9, "the end did not close onto the chain start"
        assert (w._pt2 - face_pt).manhattanLength() > 5.0 * px, w._pt2
    finally:
        _cleanup_walls(sc, new + [host])
