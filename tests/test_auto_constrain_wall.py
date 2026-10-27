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
        _drag_raw(sc, view, corner, QPointF(corner.x() + 400, corner.y() + 300))
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


def _drag_raw(sc, view, a, b):
    """A real grip drag with cursor snap / ALIGN off: a stale coincident-partner
    corner would otherwise pull the cursor back onto itself (the grip would not
    move at all)."""
    QApplication.processEvents()
    refresh = getattr(view.window(), "_refresh_all_views", None)
    if refresh is not None:
        refresh()                                    # settle the debounced view refresh first
    QApplication.processEvents()
    assert not sc.is_input_mode(), "a placement HUD is open: the canvas is inert to the drag"
    assert view.viewport().rect().contains(view.mapFromScene(a)), "grip is off the viewport"
    snap0, align0 = sc._snap_enabled, sc._align_enabled
    sc._snap_enabled = sc._align_enabled = False
    try:
        _drag(view, a, b)
    finally:
        sc._snap_enabled, sc._align_enabled = snap0, align0


def test_t6_untied_touching_end_still_follows(mw, plan, qapp, toggle):
    sc, view = plan
    toggle(False)                                    # legacy-style: no records
    walls = []
    try:
        walls = _place_L(sc, view, sc._get_wall_template()._alignment)
        a, b = walls
        sc.clearSelection()
        a.setSelected(True)
        qapp.processEvents()
        end = QPointF(a._pt2)
        _drag_raw(sc, view, end, QPointF(end.x() + 300, end.y() - 200))
        assert (a._pt2 - end).manhattanLength() > 100.0, "the grip did not move"
        assert (b._pt1 - a._pt2).manhattanLength() < 1e-3, "untied end did not follow"
    finally:
        _cleanup_walls(sc, walls)


def test_t6_tied_end_follows_the_solver_in_a_real_drag(mw, plan, qapp, toggle):
    """Regression guard (passes with and without the G10 skip): a placement-tied
    end stays one coherent position with the dragged end."""
    sc, view = plan
    toggle(True)
    walls = []
    try:
        walls = _place_L(sc, view, sc._get_wall_template()._alignment)
        a, b = walls
        sc.clearSelection()
        a.setSelected(True)
        qapp.processEvents()
        end = QPointF(a._pt2)
        _drag_raw(sc, view, end, QPointF(end.x() + 300, end.y() - 200))
        assert (a._pt2 - end).manhattanLength() > 100.0, "the grip did not move"
        assert (b._pt1 - a._pt2).manhattanLength() < 1e-3, "tie broken"
    finally:
        _cleanup_walls(sc, walls)


def test_t6_proximity_never_moves_a_coincident_tied_end(mw, plan, qapp, toggle):
    """G10 contract: _propagate_wall_endpoint skips an end held by an enabled
    coincident (the solver owns it); with the tie gone the same call moves it."""
    sc, view = plan
    toggle(True)
    walls = []
    try:
        walls = _place_L(sc, view, sc._get_wall_template()._alignment)
        a, b = walls
        ctl = sc.constraint_ctl
        tie = [c for c in ctl.constraints if c.type == "coincident"
               and _refs_uids(c) == {a._uid, b._uid}]
        assert len(tie) == 1 and tie[0].enabled
        old = QPointF(a._pt2)
        new = QPointF(old.x() + 300, old.y() - 200)
        b1 = QPointF(b._pt1)
        sc._propagate_wall_endpoint(a, old, new)
        assert (b._pt1 - b1).manhattanLength() < 1e-6, "proximity moved a tied end"
        tie[0].enabled = False                       # positive control: untied -> follows
        sc._propagate_wall_endpoint(a, old, new)
        assert (b._pt1 - new).manhattanLength() < 1e-6, "untied end did not follow"
    finally:
        _cleanup_walls(sc, walls)


# ── Slice 3 fix round ───────────────────────────────────────────────────────

from tests.test_plan_constraints_e2e import _wall  # noqa: E402
from tests.test_plan_glyph_visibility import _cleanup as _drop_level2  # noqa: E402
from tests.test_plan_glyph_visibility import _hide_level2  # noqa: E402


def _place_line(sc, view, a, b, shift=False):
    """One line wall through the real press path with cursor snap / ALIGN off
    (so the join logic alone decides where the end lands)."""
    n0 = len(sc._walls)
    snap0, align0 = sc._snap_enabled, sc._align_enabled
    sc._snap_enabled = sc._align_enabled = False
    try:
        sc.set_mode("wall")
        _press(view, a, shift)
        _press(view, b, shift)
        sc.set_mode("select")
    finally:
        sc._snap_enabled, sc._align_enabled = snap0, align0
    return sc._walls[n0:]


@pytest.mark.parametrize("kind,start,click,joined", [
    ("miter", (2000, 1500), (2010, 8), (2000, 0)),
    ("tee", (1000, 1500), (1000, 12), None),          # None: onto the y=0 centerline
])
@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("toggle_v", [True, False])
def test_s1_hidden_walls_are_not_join_targets(mw, plan, qapp, toggle, toggle_v,
                                              hidden, kind, start, click, joined):
    sc, view = plan
    toggle(toggle_v)
    host = _wall(sc, (0, 0), (2000, 0))
    new = []
    try:
        if hidden:
            _hide_level2(mw, qapp, host)
            assert not host.isVisible()
        else:
            assert host.isVisible()
        # The press lands on a whole viewport pixel: use that exact scene point.
        exact = view.mapToScene(view.mapFromScene(QPointF(*click)))
        gap = (abs(exact.y()) if joined is None
               else math.hypot(exact.x() - joined[0], exact.y() - joined[1]))
        assert 3.0 < gap < 19.0, gap                 # inside the join radius, off the target
        new = _place_line(sc, view, QPointF(*start), exact)
        assert len(new) == 1
        end = new[0]._pt2
        refs = [c for c in sc.constraint_ctl.constraints
                if host._uid in _refs_uids(c) and new[0]._uid in _refs_uids(c)]
        if hidden:
            # the press rounds to whole mm, hence the 1.5 mm slack
            assert (end - exact).manhattanLength() < 1.5, \
                "a hidden wall pulled the end (snap)"
            assert not refs, "a record references the hidden wall"
        else:                                        # positive control: it joins
            want = QPointF(exact.x(), 0.0) if joined is None else QPointF(*joined)
            assert (end - want).manhattanLength() < 1.5, "visible wall did not snap"
            assert abs(end.y() - want.y()) < 1e-6, "end is off the host line"
            assert bool(refs) == toggle_v, refs
    finally:
        _cleanup_walls(sc, new + [host])
        if hidden:
            _drop_level2(mw, sc.constraint_ctl)


# ── M3: the proximity skip honours a disabled controller / a red tie ─────────

@pytest.mark.parametrize("mode", ["disabled", "red"])
def test_m3_disabled_or_red_tie_does_not_skip(mw, plan, qapp, toggle, mode):
    sc, view = plan
    toggle(True)
    walls = []
    ctl = sc.constraint_ctl
    try:
        walls = _place_L(sc, view, sc._get_wall_template()._alignment)
        a, b = walls
        tie = [c for c in ctl.constraints if c.type == "coincident"
               and _refs_uids(c) == {a._uid, b._uid}]
        assert len(tie) == 1 and tie[0].enabled
        old = QPointF(a._pt2)
        new = QPointF(old.x() + 300, old.y() - 200)
        b1 = QPointF(b._pt1)
        sc._propagate_wall_endpoint(a, old, new)          # control: a live tie is skipped
        assert (b._pt1 - b1).manhattanLength() < 1e-6, "proximity moved a live tied end"
        try:
            if mode == "disabled":
                ctl.enabled = False
            else:
                ctl.red.add(tie[0].id)
            sc._propagate_wall_endpoint(a, old, new)
            assert (b._pt1 - new).manhattanLength() < 1e-6, \
                f"a {mode} constraint still held the end back"
        finally:
            ctl.enabled = True
            ctl.red.discard(tie[0].id)
    finally:
        _cleanup_walls(sc, walls)


# ── M4: a typed rectangle completion is the toggle alone, never live Shift ───

def _rect_to_depth_step(sc, view):
    """Arm the corner-rect wall variant and fix the first side by two clicks."""
    sc.set_mode("wall")
    sc.cycle_placement_variant(+1)
    sc.cycle_placement_variant(+1)
    assert sc._wall_primitive == "rect"
    _press(view, QPointF(0, 0))
    _press(view, QPointF(2000, 0))
    assert sc._wall_rect_side_pt is not None, "side step not fixed"


def _reset_wall_variant(sc, prim0):
    sc.set_mode("select")
    sc.set_mode("wall")
    for _ in range(6):                                   # the variant persists across tests
        if sc._wall_primitive == prim0:
            break
        sc.cycle_placement_variant(+1)
    sc.set_mode("select")


@pytest.mark.parametrize("path", ["typed", "click"])
def test_m4_rect_completion_modifier_source(mw, plan, qapp, toggle, monkeypatch, path):
    """Typed: the toggle alone (live Shift ignored) -> records. Click: toggle XOR
    the live Shift (the companion that proves Shift is read at all)."""
    sc, view = plan
    toggle(True)
    sc.set_mode("wall")
    prim0 = sc._wall_primitive
    sc.set_mode("select")
    monkeypatch.setattr(QApplication, "keyboardModifiers",
                        staticmethod(lambda: Qt.KeyboardModifier.ShiftModifier))
    n0 = len(sc._walls)
    walls = []
    try:
        _rect_to_depth_step(sc, view)
        if path == "typed":
            assert sc._apply_wall_dynamic_input(QPointF(1000, 1500)) is True
        else:
            _press(view, QPointF(1000, 1500))
        walls = sc._walls[n0:]
        assert len(walls) == 4, "the rectangle was not committed"
        uids = {w._uid for w in walls}
        types = [c.type for c in sc.constraint_ctl.constraints if _refs_uids(c) & uids]
        if path == "typed":
            assert types.count("perpendicular") == 3 and types.count("coincident") == 4, types
        else:
            assert types == [], f"Shift-held click still recorded: {types}"
    finally:
        monkeypatch.undo()
        _reset_wall_variant(sc, prim0)
        _cleanup_walls(sc, walls)


# ── M5: test gaps ────────────────────────────────────────────────────────────

def _handle_of(w, which):
    """Literal drawn handle name of end *which* (1/2) for the wall alignment."""
    suffix = {ALIGN_LEFT: "r", ALIGN_RIGHT: "l"}.get(w._alignment, "")   # else centre
    return f"p{which}{suffix}"


def _edge_of(w):
    return {ALIGN_LEFT: "face_r", ALIGN_RIGHT: "face_l"}.get(w._alignment, "edge")


def _mine(sc, *walls):
    uids = {w._uid for w in walls}
    return [(c.type, [dict(r) for r in c.refs]) for c in sc.constraint_ctl.constraints
            if _refs_uids(c) & uids]


def test_m5_polyline_chain_and_loop_close_join_each_segment(mw, plan, qapp, toggle):
    sc, view = plan
    toggle(True)
    sc.set_mode("wall")
    prim0 = sc._wall_primitive
    sc.cycle_placement_variant(+1)
    assert sc._wall_primitive == "polyline"
    n0 = len(sc._walls)
    walls = []
    try:
        # A triangle: three clicks open a 2-wall chain, the 4th (on the start) closes it.
        for p in (QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 1500)):
            _press(view, p)
        a, b = sc._walls[n0:n0 + 2]
        want_chain = ("coincident", [{"uid": b._uid, "h": _handle_of(b, 1)},
                                     {"uid": a._uid, "h": _handle_of(a, 2)}])
        assert want_chain in _mine(sc, a, b), _mine(sc, a, b)
        _press(view, QPointF(0, 0))                       # back on the chain start: closes
        walls = sc._walls[n0:]
        assert len(walls) == 3
        c = walls[2]
        got = _mine(sc, c)
        assert ("coincident", [{"uid": c._uid, "h": _handle_of(c, 1)},
                               {"uid": b._uid, "h": _handle_of(b, 2)}]) in got, got
        assert ("coincident", [{"uid": c._uid, "h": _handle_of(c, 2)},
                               {"uid": a._uid, "h": _handle_of(a, 1)}]) in got, got
    finally:
        sc.set_mode("select")
        _reset_wall_variant(sc, prim0)
        _cleanup_walls(sc, sc._walls[n0:])


@pytest.mark.parametrize("toggle_v", [True, False])
def test_m5_typed_line_completion_follows_the_toggle(mw, plan, qapp, toggle, toggle_v):
    sc, view = plan
    toggle(toggle_v)
    n0 = len(sc._walls)
    walls = []
    try:
        sc.set_mode("wall")
        assert sc._wall_primitive == "line"
        _press(view, QPointF(0, 0))                       # anchor by click
        assert sc._apply_wall_dynamic_input(QPointF(2000, 0)) is True   # typed end
        walls = sc._walls[n0:]
        assert len(walls) == 1
        got = _mine(sc, walls[0])
        want = ("horizontal", [{"uid": walls[0]._uid, "h": _edge_of(walls[0])}])
        assert (want in got) == toggle_v, got
    finally:
        sc.set_mode("select")
        _cleanup_walls(sc, walls)


def test_m5_tee_join_records_point_on_curve_through_the_press_path(mw, plan, qapp, toggle):
    sc, view = plan
    toggle(True)
    host = _wall(sc, (0, 0), (4000, 0))
    host._uid = "m5host"
    new = []
    try:
        new = _place_line(sc, view, QPointF(2000, 1500), QPointF(2000, 10))
        assert len(new) == 1
        w = new[0]
        assert abs(w._pt2.y()) < 1e-6, "end did not tee onto the host centerline"
        edge = _edge_of(host)
        want = ("point_on_curve", [{"uid": w._uid, "h": _handle_of(w, 2)},
                                  {"uid": host._uid, "h": edge}])
        assert want in _mine(sc, w, host), _mine(sc, w, host)
    finally:
        _cleanup_walls(sc, new + [host])


def test_m5_block_editor_wall_placement_adds_no_records(mw, plan, qapp, toggle):
    """Walls CAN be placed in a Block Editor (probe: set_mode wall is accepted);
    the plan scene records the join, the Block Editor scene must not."""
    from PyQt6.QtCore import QRectF
    sc, view = plan
    toggle(True)
    plan_walls = []
    try:
        plan_walls = _place_L(sc, view, sc._get_wall_template()._alignment)
        assert _mine(sc, *plan_walls), "positive control: plan placement recorded nothing"
    finally:
        _cleanup_walls(sc, plan_walls)
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    esc, eview = ed.editor_scene, ed.view
    eview.resetTransform()
    eview.fitInView(QRectF(-1500, -2000, 6000, 4000), Qt.AspectRatioMode.KeepAspectRatio)
    qapp.processEvents()
    n_c = len(esc.constraint_ctl.constraints)
    n_w = len(esc._walls)
    try:
        for a, b in ((QPointF(0, 0), QPointF(2000, 0)), (QPointF(2000, 0), QPointF(2000, 1500))):
            esc.set_mode("wall")
            _press(eview, a)
            _press(eview, b)
        esc.set_mode("select")
        assert len(esc._walls) == n_w + 2, "walls were not placed in the Block Editor"
        assert len(esc.constraint_ctl.constraints) == n_c, "Block Editor wall placement recorded"
    finally:
        mw.block_editor_manager.close(ed)
        qapp.processEvents()
