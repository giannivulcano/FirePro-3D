"""Slice 3 (G10/G11): wall placement Auto Constrain."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, QSettings, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d import auto_constrain as ac
from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.sketch_adapters import adapter_for
from firepro3d.wall import ALIGN_LEFT, ALIGN_RIGHT, WallSegment


def _w(a, b, align=None, uid="u"):
    w = WallSegment(QPointF(*a), QPointF(*b))
    if align is not None:
        w._alignment = align
    w._uid = uid
    return w


def _adapter_points(w) -> dict:
    """handle -> (x, y) from the REAL adapter (the test_auto_constrain_shapes
    ``_pos`` idiom: read the vars, eval each PointExpr)."""
    import numpy as np
    ad = adapter_for(w)
    x = np.array(ad.read(w), dtype=float)
    return {h: tuple(e.eval(x)[0]) for h, e in ad.points(w, 0).items()}


@pytest.mark.parametrize("align,expect", [
    (None, ("p1", "p2", "edge")),
    (ALIGN_LEFT, ("p1r", "p2r", "face_r")),
    (ALIGN_RIGHT, ("p1l", "p2l", "face_l")),
])
def test_drawn_handles_sit_on_the_click_line(align, expect):
    w = _w((0, 0), (3000, 0), align)
    assert ac.wall_drawn_handles(w) == expect
    got = _adapter_points(w)                 # ground truth: the adapter's own math
    for h, p in ((expect[0], w._pt1), (expect[1], w._pt2)):
        assert math.hypot(got[h][0] - p.x(), got[h][1] - p.y()) < 1e-6, h


def test_join_records():
    a = _w((0, 0), (2000, 0), ALIGN_LEFT, "A")
    b = _w((2000, 0), (2000, 1500), None, "B")
    assert ac.plan_wall_join(b, 0, a, 1) == [
        ("coincident", [{"uid": "B", "h": "p1"}, {"uid": "A", "h": "p2r"}])]
    assert ac.plan_wall_join(b, 0, a) == [
        ("point_on_curve", [{"uid": "B", "h": "p1"}, {"uid": "A", "h": "face_r"}])]


def test_hv_and_rect_records():
    h = _w((0, 0), (2000, 0), None, "H")
    s = _w((0, 0), (2000, 3), None, "S")
    assert ac.plan_wall_hv(h) == [("horizontal", [{"uid": "H", "h": "edge"}])]
    assert ac.plan_wall_hv(s) == []
    ws = [_w((0, 0), (1, 0), None, f"R{i}") for i in range(4)]
    assert ac.plan_wall_rect(ws) == [
        ("perpendicular", [{"uid": f"R{i}", "h": "edge"}, {"uid": f"R{i + 1}", "h": "edge"}])
        for i in range(3)]


@pytest.mark.parametrize("toggle,shift,on", [(True, False, True), (True, True, False),
                                             (False, False, False), (False, True, True)])
def test_infer_on_is_toggle_xor_shift(toggle, shift, on):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, toggle)
    try:
        assert ac.infer_on(shift) is on
    finally:
        QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)


from tests.test_build_editor_tabs import _editors, _plan_index, mw  # noqa: E402,F401
from tests.test_constraint_e2e import _drag  # noqa: E402
from tests.test_plan_constraints_e2e import plan  # noqa: E402,F401


def _press(view, pt, shift=False):
    vp = view.viewport()
    p = view.mapFromScene(pt)
    mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        QApplication.sendEvent(vp, QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                               Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods))


@pytest.fixture
def toggle():
    s = QSettings("GV", "FirePro3D")
    yield lambda v: s.setValue(AUTO_CONSTRAIN_KEY, v)
    s.remove(AUTO_CONSTRAIN_KEY)


def _refs_uids(c):
    return {r.get("uid") for r in c.refs if isinstance(r, dict)}


def _cleanup_walls(sc, walls):
    ctl = sc.constraint_ctl
    uids = {w._uid for w in walls}
    for c in [c for c in ctl.constraints if _refs_uids(c) & uids]:
        ctl.constraints.remove(c)
    for w in walls:
        if w.scene() is sc:
            sc.removeItem(w)
        if w in sc._walls:
            sc._walls.remove(w)


def _place_L(sc, view, align, shift=False):
    """Two single line walls through the real press path: (0,0)-(2000,0),
    then (2000,0)-(2000,1500) (the start auto-joins to the first end)."""
    sc._wall_alignment = align                       # set_mode('wall') re-syncs the template from it
    sc._get_wall_template()._alignment = align
    n0 = len(sc._walls)
    for a, b in ((QPointF(0, 0), QPointF(2000, 0)), (QPointF(2000, 0), QPointF(2000, 1500))):
        sc.set_mode("wall")                          # default primitive: line
        _press(view, a, shift)
        _press(view, b, shift)
    sc.set_mode("select")
    return sc._walls[n0:]


@pytest.mark.parametrize("align", [None, ALIGN_LEFT, ALIGN_RIGHT])
def test_t8_on_records_the_join_without_moving_walls(mw, plan, qapp, toggle, align):
    sc, view = plan
    toggle(True)
    tmpl = sc._get_wall_template()
    old = tmpl._alignment
    old_sc = sc._wall_alignment
    walls = []
    try:
        walls = _place_L(sc, view, old if align is None else align)
        a, b = walls
        assert a._alignment == b._alignment == (old if align is None else align)
        snap = [QPointF(p) for w in walls for p in (w._pt1, w._pt2)]
        h1, h2 = {None: ("p1", "p2"), ALIGN_LEFT: ("p1r", "p2r"),
                  ALIGN_RIGHT: ("p1l", "p2l")}[align]   # literal: not the code under test
        want = ("coincident", [{"uid": b._uid, "h": h1}, {"uid": a._uid, "h": h2}])
        mine = [(c.type, [dict(r) for r in c.refs]) for c in sc.constraint_ctl.constraints
                if _refs_uids(c) & {a._uid, b._uid}]
        assert want in mine, mine
        now = [QPointF(p) for w in walls for p in (w._pt1, w._pt2)]
        assert all((p - q).manhattanLength() < 1e-6 for p, q in zip(snap, now)), \
            "adding the records moved a wall"
        assert (a._pt2 - b._pt1).manhattanLength() < 1e-6
    finally:
        tmpl._alignment = old
        sc._wall_alignment = old_sc
        _cleanup_walls(sc, walls)


@pytest.mark.parametrize("toggle_v,shift", [(False, False), (True, True)])
def test_t8_off_or_shift_adds_no_constraints(mw, plan, qapp, toggle, toggle_v, shift):
    sc, view = plan
    toggle(toggle_v)
    n0 = len(sc.constraint_ctl.constraints)
    walls = []
    try:
        walls = _place_L(sc, view, sc._get_wall_template()._alignment, shift)
        assert len(walls) == 2
        assert (walls[0]._pt2 - walls[1]._pt1).manhattanLength() < 1e-6   # joined anyway
        assert len(sc.constraint_ctl.constraints) == n0
    finally:
        _cleanup_walls(sc, walls)


def test_t3_rect_corner_drag_stays_a_rectangle(mw, plan, qapp, toggle):
    sc, view = plan
    toggle(True)
    sc.set_mode("wall")
    prim0 = sc._wall_primitive
    sc.cycle_placement_variant(+1)
    sc.cycle_placement_variant(+1)                   # line -> polyline -> corner rect
    assert sc._wall_primitive == "rect"
    n0 = len(sc._walls)
    walls = []
    try:
        for p in (QPointF(0, 0), QPointF(2000, 0), QPointF(1000, 1500)):
            _press(view, p)
        walls = sc._walls[n0:]
        assert len(walls) == 4
        uids = {w._uid for w in walls}
        types = [c.type for c in sc.constraint_ctl.constraints if _refs_uids(c) & uids]
        assert types.count("perpendicular") == 3 and types.count("coincident") == 4, types
        sc.set_mode("select")
        sc.clearSelection()
        w0 = walls[0]
        w0.setSelected(True)
        qapp.processEvents()
        corner = QPointF(w0._pt2)
        snap0, align0 = sc._snap_enabled, sc._align_enabled
        sc._snap_enabled = sc._align_enabled = False     # raw cursor: the stale partner
        try:                                             # corner would otherwise pull it back
            _drag(view, corner, QPointF(corner.x() + 400, corner.y() + 300))
        finally:
            sc._snap_enabled, sc._align_enabled = snap0, align0
        assert (w0._pt2 - corner).manhattanLength() > 100.0, "the grip did not move"
        for i in range(4):                           # closed and right-angled
            a, b = walls[i], walls[(i + 1) % 4]
            assert (a._pt2 - b._pt1).manhattanLength() < 1e-3, f"corner {i} opened"
            ux, uy = a._pt2.x() - a._pt1.x(), a._pt2.y() - a._pt1.y()
            vx, vy = b._pt2.x() - b._pt1.x(), b._pt2.y() - b._pt1.y()
            cos = (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))
            assert abs(cos) < 1e-4, f"corner {i} not square: cos={cos}"
    finally:
        sc.set_mode("select")
        sc.set_mode("wall")
        for _ in range(6):                           # the variant persists across tests
            if sc._wall_primitive == prim0:
                break
            sc.cycle_placement_variant(+1)
        sc.set_mode("select")
        _cleanup_walls(sc, walls)


def test_placement_and_its_constraints_undo_as_one_step(mw, plan, qapp, toggle):
    sc, view = plan
    toggle(True)
    sc.push_undo_state()                             # baseline: earlier tests' cleanup left the stack stale
    n_c, n_w = len(sc.constraint_ctl.constraints), len(sc._walls)
    _a, b = _place_L(sc, view, sc._get_wall_template()._alignment)
    assert len(sc.constraint_ctl.constraints) > n_c
    sc.undo()                                        # the 2nd wall and its join together
    qapp.processEvents()
    assert len(sc._walls) == n_w + 1
    assert not [c for c in sc.constraint_ctl.constraints if b._uid in _refs_uids(c)]
    assert len(sc.constraint_ctl.constraints) == n_c + 1   # wall 1's own H record stays
    sc.undo()
    qapp.processEvents()
    assert len(sc._walls) == n_w
    assert len(sc.constraint_ctl.constraints) == n_c
