"""CS1 end-to-end guards — parametric-constraint-system.md §11 #2-#4.

Real MainWindow (shown, live app QSS + font), a real Block Editor tab, the
real ribbon buttons, posted mouse / key events on the shown editor view, and
observable geometry as ground truth. The MainWindow + open-editor fixtures
are the Task 12 ones (``tests/test_constraint_pick_ribbon.py``).
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTabBar

from firepro3d import constraint_paint as cp
from firepro3d.geometry_2d import LineItem

# Re-exported fixtures (module scope -> this module gets its own MainWindow).
from tests.test_constraint_pick_ribbon import (  # noqa: F401
    _editors, _plan_index, mw, win_with_editor)


# ── helpers ──────────────────────────────────────────────────────────────────

def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _send(view, etype, vp, button, buttons):
    port = view.viewport()
    gp = QPointF(port.mapToGlobal(vp.toPoint()))     # real screen pos (drag threshold)
    QApplication.sendEvent(port, QMouseEvent(
        etype, QPointF(vp), gp, button, buttons, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _drag(view, a, b, steps=8):
    """A real press / move / release grip drag delivered through the viewport.

    Synchronous ``sendEvent`` with a real global position (as
    ``test_selection_manipulator`` does): ``QTest.mouseMove`` on a shown window
    proved flaky here (the gesture was cut short mid-drag), and an event
    without a global position never crosses the drag threshold.
    """
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    va, vb = QPointF(view.mapFromScene(a)), QPointF(view.mapFromScene(b))
    _send(view, QEvent.Type.MouseMove, va, NB, NB)
    _send(view, QEvent.Type.MouseButtonPress, va, L, L)
    for k in range(1, steps + 1):
        _send(view, QEvent.Type.MouseMove, va + (vb - va) * (k / steps), NB, L)
    _send(view, QEvent.Type.MouseButtonRelease, vb, L, NB)


def _click(view, vp):
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    vp = QPointF(vp)
    _send(view, QEvent.Type.MouseMove, vp, NB, NB)
    _send(view, QEvent.Type.MouseButtonPress, vp, L, L)
    _send(view, QEvent.Type.MouseButtonRelease, vp, L, NB)


def _ctrl(view, key):
    """Ctrl+<key> posted to the shown editor view (window QShortcut route)."""
    view.activateWindow()
    view.setFocus()
    QApplication.processEvents()
    # Precondition: a window QShortcut only fires in the active window.
    assert QApplication.activeWindow() is view.window(), "MainWindow not active"
    QTest.keyClick(view.viewport(), key, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()


def _ys(ln):
    return ln._pt1.y(), ln._pt2.y()


def _close_tab(win, w):
    """Close an editor tab through its real tab-bar close dot (a posted click)."""
    from PyQt6.QtWidgets import QToolButton
    tabs = win.central_tabs
    idx = tabs.indexOf(w)
    assert idx != -1
    wrap = tabs.tabBar().tabButton(idx, QTabBar.ButtonPosition.RightSide)
    (dot,) = wrap.findChildren(QToolButton)
    QTest.mouseClick(dot, Qt.MouseButton.LeftButton,
                     pos=dot.rect().center())
    QApplication.processEvents()


# ── §11 #2: ribbon button + a tilting grip drag on a shown view ──────────────

def test_e2e_horizontal_survives_a_tilting_grip_drag(win_with_editor):
    win = win_with_editor
    sc = win._active_scene()
    view = win._test_editor.view
    assert sc is win._test_editor.editor_scene
    ln = _line(sc, (-100, 0), (100, 30))                 # tilted
    sc.clearSelection()
    ln.setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Horizontal"].click()      # the REAL button
    QApplication.processEvents()
    assert [c.type for c in sc.constraint_ctl.constraints_on(ln)] == ["horizontal"]
    assert _ys(ln) == pytest.approx((15.0, 15.0), abs=1e-6)   # D22 mean
    sc.clearSelection()
    ln.setSelected(True)                                 # grips visible
    QApplication.processEvents()
    # Drag the p2 grip up 60 mm: unconstrained this would TILT the line.
    _drag(view, QPointF(100, 15), QPointF(100, 75))
    assert ln._pt2.y() == pytest.approx(75.0, abs=1.0)   # the grip moved
    assert ln._pt1.y() == pytest.approx(ln._pt2.y(), abs=1e-6)   # still level
    assert ln._pt1.x() == pytest.approx(-100.0, abs=1e-6)


# ── §11 #3: save -> close -> reopen; a placed instance renders frozen ────────

def test_e2e_save_close_reopen_and_frozen_instance(win_with_editor):
    win = win_with_editor
    w = win._test_editor
    sc = w.editor_scene
    ln = _line(sc, (-50, 10), (50, 30))
    sc.clearSelection()
    ln.setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Horizontal"].click()
    uid = ln._uid
    assert _ys(ln) == pytest.approx((20.0, 20.0), abs=1e-6)
    sc.clearSelection()
    defn = w.commit_block("cs1-e2e", "L", "S")
    assert defn is not None
    # Close the tab for real (clean after commit -> no discard prompt).
    _close_tab(win, w)
    assert w not in _editors(win)
    assert defn.id not in win.block_editor_manager._open
    # Reopen through the app's edit path.
    w2 = win.block_editor_manager.edit_definition(defn.id)
    QApplication.processEvents()
    assert w2 is not w and w2 in _editors(win)
    sc2 = w2.editor_scene
    ctl2 = sc2.constraint_ctl
    (l2,) = sc2._draw_lines
    # The geometry returns (solved, level) ...
    assert (l2._pt1.x(), l2._pt2.x()) == pytest.approx((-50.0, 50.0), abs=1e-6)
    assert _ys(l2) == pytest.approx((20.0, 20.0), abs=1e-6)
    # ... the constraint returns, bound to the reopened line ...
    assert [c.type for c in ctl2.active()] == ["horizontal"]
    assert [c.type for c in ctl2.constraints_on(l2)] == ["horizontal"]
    # ... its glyph is laid out on the reopened view ...
    w2.view.resetTransform()
    w2.view.centerOn(0, 0)
    w2.editor_scene.set_mode("select")
    sc2.clearSelection()
    l2.setSelected(True)                       # D32: the line's glyph shows
    QApplication.processEvents()
    assert [cid for cid, _r in cp.glyph_layouts(w2.view, ctl2)] == [
        ctl2.constraints[0].id]
    # ... and it still drives: a tilting grip drag on the reopened line holds level.
    sc2.clearSelection()
    l2.setSelected(True)
    QApplication.processEvents()
    _drag(w2.view, QPointF(50, 20), QPointF(50, 70))
    (l2,) = sc2._draw_lines
    assert l2._pt2.y() == pytest.approx(70.0, abs=1.0)
    assert l2._pt1.y() == pytest.approx(l2._pt2.y(), abs=1e-6)
    assert l2._uid == uid
    assert [(c["type"], c["refs"]) for c in defn.constraints] == [
        ("horizontal", [{"uid": uid, "h": "edge"}])]
    # A placed instance in the plan renders the solved (frozen) geometry.
    inst = win.scene.place_block_instance(defn.id, (0, 0))
    try:
        ops = inst.render_ops()
        assert len(ops) == 1
        r = ops[0].path.boundingRect()
        assert r.height() == pytest.approx(0.0, abs=1e-6)          # level
        assert r.width() == pytest.approx(100.0, abs=1e-6)
    finally:
        win.scene.remove_block_instance(inst)


# ── §11 #4: undo / redo of add, delete and a solver-driven drag ──────────────

def test_e2e_undo_redo_of_add_delete_and_a_solver_driven_drag(win_with_editor):
    win = win_with_editor
    sc = win._active_scene()
    view = win._test_editor.view
    ln = _line(sc, (-100, 0), (100, 30))
    uid = ln._uid
    sc.push_undo_state()                      # the drawn line is its own step

    def cur():
        (l,) = [x for x in sc._draw_lines if x._uid == uid]
        return l

    # Add through the ribbon.
    ln.setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Horizontal"].click()
    assert _ys(cur()) == pytest.approx((15.0, 15.0), abs=1e-6)
    _ctrl(view, Qt.Key.Key_Z)                                     # undo add
    assert _ys(cur()) == pytest.approx((0.0, 30.0), abs=1e-6)
    assert sc.constraint_ctl.constraints == []
    _ctrl(view, Qt.Key.Key_Y)                                     # redo add
    assert _ys(cur()) == pytest.approx((15.0, 15.0), abs=1e-6)
    assert [c.type for c in sc.constraint_ctl.constraints_on(cur())] == ["horizontal"]

    # A solver-driven grip drag.
    sc.clearSelection()
    cur().setSelected(True)
    QApplication.processEvents()
    _drag(view, QPointF(100, 15), QPointF(100, 75))
    assert _ys(cur())[1] == pytest.approx(75.0, abs=1.0)
    dragged = _ys(cur())
    assert dragged[0] == pytest.approx(dragged[1], abs=1e-6)
    _ctrl(view, Qt.Key.Key_Z)                                     # undo drag
    assert _ys(cur()) == pytest.approx((15.0, 15.0), abs=1e-6)
    assert len(sc.constraint_ctl.constraints) == 1
    _ctrl(view, Qt.Key.Key_Y)                                     # redo drag
    assert _ys(cur()) == pytest.approx(dragged, abs=1e-6)

    # Delete through the ribbon.
    sc.clearSelection()
    cur().setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Delete Constraints"].click()
    assert sc.constraint_ctl.constraints == []
    _ctrl(view, Qt.Key.Key_Z)                                     # undo delete
    assert [c.type for c in sc.constraint_ctl.constraints_on(cur())] == ["horizontal"]
    _ctrl(view, Qt.Key.Key_Y)                                     # redo delete
    assert sc.constraint_ctl.constraints == []
    assert _ys(cur()) == pytest.approx(dragged, abs=1e-6)         # geometry kept


# ── spec AC: a typed readout edit honours the constraints ────────────────────

def _type_length(view, sc, item, text):
    """Select *item*, click its Length label, type *text*, press Return."""
    sc.clearSelection()
    item.setSelected(True)
    QApplication.processEvents()
    # D31 seam guard through the readout HUD (pre-D57 line readout opt-in).
    sc.readouts.show_edge_lengths = True
    lay = next(e for e in sc.readouts.layouts(view) if e.spec.key == "length")
    _click(view, lay.layout.center)                    # click the label
    assert sc.readouts.is_editing()
    ed = sc.readouts.hud.editor("Length")
    ed.selectAll()
    QTest.keyClicks(ed, text)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QApplication.processEvents()
    assert not sc.readouts.is_editing()


def test_e2e_typed_length_readout_keeps_horizontal_and_the_typed_length(
        win_with_editor):
    win = win_with_editor
    sc = win._active_scene()
    view = win._test_editor.view
    ctl = sc.constraint_ctl
    # (1) A Horizontal line: the typed length lands and the line stays level.
    a = _line(sc, (-100, 0), (100, 0))
    ctl.add("horizontal", [{"uid": a._uid, "h": "edge"}])
    _type_length(view, sc, a, "260")
    (la,) = [x for x in sc._draw_lines if x._uid == a._uid]
    assert la.line().length() == pytest.approx(260.0, abs=1e-6)     # typed length
    assert la._pt1.y() == pytest.approx(la._pt2.y(), abs=1e-6)      # still level
    # (2) A tilted line whose p2 is Horizontal to a follower's p1: the typed
    # length moves p2 off the follower's y; the solve brings the follower
    # along and the typed line keeps its typed length.
    t = _line(sc, (0, 100), (60, 180))                # 3-4-5: length 100
    f = _line(sc, (300, 180), (400, 180))
    ctl.add("horizontal", [{"uid": t._uid, "h": "p2"}, {"uid": f._uid, "h": "p1"}])
    _type_length(view, sc, t, "200")
    (lt,) = [x for x in sc._draw_lines if x._uid == t._uid]
    (lf,) = [x for x in sc._draw_lines if x._uid == f._uid]
    # D31: a TYPED value is honoured exactly -- the typed edit's changed
    # variables are pinned (W_PIN) and the follower yields; the D6 anchor
    # (p1, unchanged) keeps W_EDIT.
    assert lt.line().length() == pytest.approx(200.0, abs=1e-6)
    assert (lt._pt1.x(), lt._pt1.y()) == pytest.approx((0.0, 100.0), abs=1e-6)
    assert lt._pt2.y() == pytest.approx(260.0, abs=1e-6)           # p2 moved up
    assert lf._pt1.y() == pytest.approx(lt._pt2.y(), abs=1e-6)      # follower held


# ── R4: undo / redo is refused while a manipulator drag is in progress ──────

def _gesture_setup(win):
    """A filter that swallows OS mouse events on the editor viewport (the real
    cursor resting over the window cuts posted gestures short)."""
    from tests.test_constraint_live_drag import _NoRealMouse
    view = win._test_editor.view
    sc = win._active_scene()
    sc.setSceneRect(-5000, -5000, 10000, 10000)       # no re-scroll mid-gesture
    guard = _NoRealMouse()
    view.viewport().installEventFilter(guard)
    return sc, view, guard


def _post(view, etype, scene_pt, button, buttons):
    vp = QPointF(view.mapFromScene(scene_pt))
    gp = QPointF(view.viewport().mapToGlobal(vp.toPoint()))
    QApplication.sendEvent(view.viewport(), QMouseEvent(
        etype, vp, gp, button, buttons, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _undo_mid_drag(win, sc, view, item, grab, geom):
    """Press on *grab*, move, Ctrl+Z AND Ctrl+Y mid-drag (both refused: the
    stack position and the item survive, the drag continues), release =
    exactly one new undo step."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    depth, pos = len(sc._undo_stack), sc._undo_pos
    _post(view, QEvent.Type.MouseMove, grab, NB, NB)
    _post(view, QEvent.Type.MouseButtonPress, grab, L, L)
    _post(view, QEvent.Type.MouseMove, grab + QPointF(0, 20), NB, L)
    assert sc._live_manip().is_dragging()
    g1 = geom()
    _ctrl(view, Qt.Key.Key_Z)
    _ctrl(view, Qt.Key.Key_Y)
    assert sc._undo_pos == pos and len(sc._undo_stack) == depth   # no undo / redo
    assert item.scene() is sc                                     # not rebuilt
    assert sc._live_manip().is_dragging()
    _post(view, QEvent.Type.MouseMove, grab + QPointF(0, 40), NB, L)
    assert geom() != g1                                           # drag continues
    _post(view, QEvent.Type.MouseButtonRelease, grab + QPointF(0, 40), L, NB)
    assert len(sc._undo_stack) == depth + 1                       # ONE step
    assert sc._undo_pos == pos + 1


def test_r4_undo_is_refused_mid_constrained_body_drag(win_with_editor):
    from firepro3d.geometry_2d import RectangleItem
    win = win_with_editor
    sc, view, guard = _gesture_setup(win)
    try:
        r = RectangleItem(QPointF(0, 0), QPointF(100, 60))
        sc.addItem(r)
        sc._draw_rects.append(r)
        ln = _line(sc, (200, 60), (320, 20))
        sc.constraint_ctl.add("horizontal", [{"uid": r._uid, "h": "br"},
                                             {"uid": ln._uid, "h": "p1"}])
        sc.clearSelection()
        r.setSelected(True)
        QApplication.processEvents()
        _undo_mid_drag(win, sc, view, r, QPointF(25, 15),
                       lambda: (r.rect().y(), ln._pt1.y()))
        assert ln._pt1.y() == pytest.approx(r.rect().bottom(), abs=1e-6)
    finally:
        view.viewport().removeEventFilter(guard)


def test_r4_undo_is_refused_mid_grip_drag(win_with_editor):
    win = win_with_editor
    sc, view, guard = _gesture_setup(win)
    try:
        ln = _line(sc, (-100, 0), (100, 0))
        sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
        sc.clearSelection()
        ln.setSelected(True)
        QApplication.processEvents()
        _undo_mid_drag(win, sc, view, ln, QPointF(100, 0),
                       lambda: (ln._pt1.y(), ln._pt2.y()))
        assert ln._pt1.y() == pytest.approx(ln._pt2.y(), abs=1e-6)
    finally:
        view.viewport().removeEventFilter(guard)


def test_r4_undo_is_refused_mid_held_preview_drag(win_with_editor):
    from firepro3d.geometry_2d import RectangleItem
    win = win_with_editor
    sc, view, guard = _gesture_setup(win)
    try:
        r = RectangleItem(QPointF(0, 0), QPointF(100, 60))   # unconstrained
        sc.addItem(r)
        sc._draw_rects.append(r)
        sc.push_undo_state()
        sc.clearSelection()
        r.setSelected(True)
        QApplication.processEvents()
        _undo_mid_drag(win, sc, view, r, QPointF(25, 15),
                       lambda: r.sceneTransform().dy())
    finally:
        view.viewport().removeEventFilter(guard)


# ── CS2: Vertical + the H+V conflict through the real ribbon ────────────────

def _xs(ln):
    return ln._pt1.x(), ln._pt2.x()


def test_e2e_vertical_survives_a_tilting_grip_drag(win_with_editor):
    win = win_with_editor
    sc = win._active_scene()
    view = win._test_editor.view
    ln = _line(sc, (0, -100), (30, 100))                 # tilted
    sc.clearSelection(); ln.setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Vertical"].click()        # the REAL button
    QApplication.processEvents()
    assert [c.type for c in sc.constraint_ctl.constraints_on(ln)] == ["vertical"]
    assert _xs(ln) == pytest.approx((15.0, 15.0), abs=1e-6)   # D22 mean
    sc.clearSelection(); ln.setSelected(True)
    QApplication.processEvents()
    _drag(view, QPointF(15, 100), QPointF(75, 100))       # would tilt it
    assert ln._pt2.x() == pytest.approx(75.0, abs=1.0)
    assert ln._pt1.x() == pytest.approx(ln._pt2.x(), abs=1e-6)
    assert ln._pt1.y() == pytest.approx(-100.0, abs=1e-6)


def test_e2e_h_plus_v_conflict_red_and_held_line(win_with_editor):
    win = win_with_editor
    sc = win._active_scene()
    ln = _line(sc, (-100, 0), (100, 30))
    sc.clearSelection(); ln.setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Horizontal"].click()
    QApplication.processEvents()
    win._be_constrain_buttons["Vertical"].click()
    QApplication.processEvents()
    ctl = sc.constraint_ctl
    v = [c for c in ctl.constraints if c.type == "vertical"][0]
    assert ctl.red == {v.id}
    assert _ys(ln) == pytest.approx((15.0, 15.0), abs=1e-6)
    assert _xs(ln) == pytest.approx((-100.0, 100.0), abs=1e-6)
    assert ctl.sketch_state() == ("Over-constrained", "conflict")


# ── CS2 §11 #3/#4: Vertical + red persist across save/reopen and undo/redo ──

def test_e2e_vertical_and_red_survive_save_close_reopen(win_with_editor):
    win = win_with_editor
    w = win._test_editor
    sc = w.editor_scene
    ln = _line(sc, (-50, 10), (50, 30))
    sc.clearSelection(); ln.setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Horizontal"].click()
    QApplication.processEvents()
    win._be_constrain_buttons["Vertical"].click()            # red (D36)
    QApplication.processEvents()
    sc.clearSelection()
    defn = w.commit_block("cs2-e2e", "L", "S")
    assert defn is not None
    _close_tab(win, w)
    w2 = win.block_editor_manager.edit_definition(defn.id)
    QApplication.processEvents()
    ctl2 = w2.editor_scene.constraint_ctl
    (l2,) = w2.editor_scene._draw_lines
    assert _ys(l2) == pytest.approx((20.0, 20.0), abs=1e-6)
    assert _xs(l2) == pytest.approx((-50.0, 50.0), abs=1e-6)
    assert [c.type for c in ctl2.constraints] == ["horizontal", "vertical"]
    assert ctl2.red == {ctl2.constraints[1].id}              # D38 list order on load
    assert [c["type"] for c in defn.constraints] == ["horizontal", "vertical"]


def test_e2e_undo_redo_of_vertical_add(win_with_editor):
    win = win_with_editor
    sc = win._active_scene()
    view = win._test_editor.view
    ln = _line(sc, (0, -100), (30, 100))
    uid = ln._uid
    sc.push_undo_state()

    def cur():
        (l,) = [x for x in sc._draw_lines if x._uid == uid]
        return l
    ln.setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Vertical"].click()
    assert _xs(cur()) == pytest.approx((15.0, 15.0), abs=1e-6)
    _ctrl(view, Qt.Key.Key_Z)
    assert _xs(cur()) == pytest.approx((0.0, 30.0), abs=1e-6)
    assert sc.constraint_ctl.constraints == []
    _ctrl(view, Qt.Key.Key_Y)
    assert _xs(cur()) == pytest.approx((15.0, 15.0), abs=1e-6)
    assert [c.type for c in sc.constraint_ctl.constraints_on(cur())] == ["vertical"]


def test_e2e_undo_of_a_red_add_and_redo_restores_red(win_with_editor):
    win = win_with_editor
    sc = win._active_scene()
    view = win._test_editor.view
    ln = _line(sc, (-100, 0), (100, 30))
    uid = ln._uid
    sc.push_undo_state()
    ln.setSelected(True)
    QApplication.processEvents()
    win._be_constrain_buttons["Horizontal"].click()
    win._be_constrain_buttons["Vertical"].click()            # red
    ctl = sc.constraint_ctl
    vid = [c.id for c in ctl.constraints if c.type == "vertical"][0]
    assert ctl.red == {vid}
    _ctrl(view, Qt.Key.Key_Z)                                 # undo the red add
    assert ctl.red == set() and [c.type for c in ctl.constraints] == ["horizontal"]
    _ctrl(view, Qt.Key.Key_Y)                                 # redo: red again
    assert ctl.red == {vid}
    (l,) = [x for x in sc._draw_lines if x._uid == uid]
    assert _ys(l) == pytest.approx((15.0, 15.0), abs=1e-6)


# ── CS3 Coincident §11 #2-#4 + D17 (real window, real ribbon, posted picks) ──

def _pick(win, *scene_pts):
    view = win._test_editor.view
    win._be_constrain_buttons["Coincident"].click()
    QApplication.processEvents()
    for p in scene_pts:
        _click(view, view.mapFromScene(QPointF(*p)))


def test_e2e_coincident_joined_ends_follow_a_grip_drag(win_with_editor):
    win = win_with_editor
    sc = win._active_scene(); view = win._test_editor.view
    a = _line(sc, (-100, 0), (-10, 4)); b = _line(sc, (10, -4), (100, 0))
    _pick(win, (-10, 4), (10, -4))
    assert [c.type for c in sc.constraint_ctl.constraints] == ["coincident"]
    assert (a._pt2.x(), a._pt2.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    sc.clearSelection(); a.setSelected(True); QApplication.processEvents()
    _drag(view, QPointF(0, 0), QPointF(0, 40))          # a.p2 grip (the joined end)
    assert a._pt2.y() == pytest.approx(40.0, abs=1.0)
    assert (b._pt1.x(), b._pt1.y()) == pytest.approx((a._pt2.x(), a._pt2.y()), abs=1e-6)


def test_e2e_point_stays_on_circle_when_the_centre_is_dragged(win_with_editor):
    from firepro3d.geometry_2d import CircleItem
    win = win_with_editor
    sc = win._active_scene(); view = win._test_editor.view
    circ = CircleItem(QPointF(0, 0), 60); sc.addItem(circ); sc._draw_circles.append(circ)
    ln = _line(sc, (100, 20), (160, 70))
    _pick(win, (100, 20), (0, -60))
    assert [c.type for c in sc.constraint_ctl.constraints] == ["point_on_curve"]
    sc.clearSelection(); circ.setSelected(True); QApplication.processEvents()
    c0 = QPointF(circ._center)
    _drag(view, c0, c0 + QPointF(-40, 0))
    assert circ._center.x() == pytest.approx(c0.x() - 40, abs=1.0)
    p, c = ln._pt1, circ._center
    assert math.hypot(p.x() - c.x(), p.y() - c.y()) == pytest.approx(circ._radius, abs=1e-6)


def test_e2e_point_on_x_axis_survives_a_grip_drag(win_with_editor):
    win = win_with_editor
    sc = win._active_scene(); view = win._test_editor.view
    ln = _line(sc, (20, 40), (90, 70))
    _pick(win, (20, 40), (-120, 0))
    assert ln._pt1.y() == pytest.approx(0.0, abs=1e-6)
    sc.clearSelection(); ln.setSelected(True); QApplication.processEvents()
    _drag(view, QPointF(ln._pt1), QPointF(60, 50))       # would lift it off the axis
    assert ln._pt1.y() == pytest.approx(0.0, abs=1e-6)
    assert ln._pt1.x() == pytest.approx(60.0, abs=1.0)


def test_e2e_coincident_save_close_reopen_and_frozen_instance(win_with_editor):
    win = win_with_editor
    w = win._test_editor
    sc = w.editor_scene
    a = _line(sc, (-60, 0), (-5, 3)); b = _line(sc, (5, -3), (60, 0))
    _pick(win, (-5, 3), (5, -3))
    ua, ub = a._uid, b._uid
    sc.clearSelection()
    defn = w.commit_block("cs3-e2e", "L", "S")
    assert defn is not None
    _close_tab(win, w)
    w2 = win.block_editor_manager.edit_definition(defn.id)
    QApplication.processEvents()
    sc2 = w2.editor_scene
    by = {l._uid: l for l in sc2._draw_lines}
    assert (by[ua]._pt2.x(), by[ua]._pt2.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert (by[ub]._pt1.x(), by[ub]._pt1.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert [c.type for c in sc2.constraint_ctl.active()] == ["coincident"]
    assert [c["type"] for c in defn.constraints] == ["coincident"]
    # A placed instance renders the solved (frozen) geometry: the joined ends
    # meet, so the compiled pair spans -60..60 at the base.
    inst = win.scene.place_block_instance(defn.id, (0, 0))
    try:
        ops = inst.render_ops()
        assert len(ops) >= 1
        r = ops[0].path.boundingRect()
        for op in ops[1:]:
            r = r.united(op.path.boundingRect())
        assert (r.left(), r.right()) == pytest.approx((-60.0, 60.0), abs=1e-6)
    finally:
        win.scene.remove_block_instance(inst)


def test_e2e_undo_redo_of_a_coincident_add(win_with_editor):
    win = win_with_editor
    sc = win._active_scene(); view = win._test_editor.view
    a = _line(sc, (-100, 0), (-10, 4)); b = _line(sc, (10, -4), (100, 0))
    ua = a._uid
    sc.push_undo_state()

    def cur():
        (l,) = [x for x in sc._draw_lines if x._uid == ua]
        return l
    _pick(win, (-10, 4), (10, -4))
    assert (cur()._pt2.x(), cur()._pt2.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    _ctrl(view, Qt.Key.Key_Z)
    assert (cur()._pt2.x(), cur()._pt2.y()) == pytest.approx((-10.0, 4.0), abs=1e-6)
    assert sc.constraint_ctl.constraints == []
    _ctrl(view, Qt.Key.Key_Y)
    assert (cur()._pt2.x(), cur()._pt2.y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert [c.type for c in sc.constraint_ctl.constraints] == ["coincident"]


def test_e2e_d17_move_of_a_fully_defined_text_is_refused(win_with_editor):
    from firepro3d.constraint_controller import GROUNDED_STATUS
    from firepro3d.text_item import TextAnnotationData, TextItem
    win = win_with_editor
    sc = win._active_scene()
    t = TextItem(TextAnnotationData(text="A", x=30.0, y=40.0, height_mm=20.0))
    sc.addItem(t); sc._texts.append(t)
    _pick(win, (0, 0), (30, 40))                        # origin, then the text's ins
    assert [c.type for c in sc.constraint_ctl.constraints] == ["coincident"]
    assert (t.pos().x(), t.pos().y()) == pytest.approx((0.0, 0.0), abs=1e-6)
    msgs = []
    sc._show_status = lambda m, *a, **k: msgs.append(m)
    sc.clearSelection(); t.setSelected(True); QApplication.processEvents()
    win._be_modify_buttons["Move"].click()
    QApplication.processEvents()
    assert sc.mode != "move"
    assert GROUNDED_STATUS in msgs
    assert (t.pos().x(), t.pos().y()) == pytest.approx((0.0, 0.0), abs=1e-6)


# ── CS3 smoke fix: a grip's own rule applies where the constraints allow ─────

def _locked(sc, it, lst, h, target=None):
    sc.addItem(it); getattr(sc, lst).append(it)
    ctype = "coincident" if target is None else "point_on_curve"
    assert sc.constraint_ctl.add(ctype, [{"uid": it._uid, "h": h},
                                         {"ref": target or "origin"}]) is not None
    return it


@pytest.mark.parametrize("make,lst,h,grip", [
    (lambda g: g.ArcItem(QPointF(0, 0), 60, 20, 100), "_draw_arcs", "center", 0),
    (lambda g: g.ArcItem(QPointF(-60, 0), 60, 0, 90), "_draw_arcs", "start", 1),
    (lambda g: g.RectangleItem(QPointF(0, 0), QPointF(80, 50)), "_draw_rects", "tl", 0),
], ids=["arc_centre", "arc_start", "rect_corner"])
def test_e2e_dragging_a_locked_grip_changes_nothing(win_with_editor, make, lst, h, grip):
    """User ruling (CS3 smoke): a grip the constraints lock does nothing --
    its rule (arc reshape, rect resize) never leaks radius / angle / size."""
    from firepro3d import geometry_2d as g
    win = win_with_editor
    sc = win._active_scene(); view = win._test_editor.view
    it = _locked(sc, make(g), lst, h)

    def geom():                     # observable: every grip point (an arc's
        return [c for p in it.grip_points() for c in (p.x(), p.y())]  # angles wrap)
    before = geom()
    sc.clearSelection(); it.setSelected(True); QApplication.processEvents()
    g0 = QPointF(it.grip_points()[grip])
    _drag(view, g0, g0 + QPointF(30, 20), steps=10)
    assert geom() == pytest.approx(before, abs=1e-6)


def test_e2e_partly_locked_rect_corner_slides_and_keeps_the_opposite_corner(win_with_editor):
    """tl on the X axis: the corner slides along the axis to the cursor's x and
    the rect's own resize rule (opposite corner fixed) applies there."""
    from firepro3d import geometry_2d as g
    win = win_with_editor
    sc = win._active_scene(); view = win._test_editor.view
    r = _locked(sc, g.RectangleItem(QPointF(0, 0), QPointF(80, 50)), "_draw_rects",
                "tl", target="x_axis")
    br0 = QPointF(r.grip_points()[4])
    sc.clearSelection(); r.setSelected(True); QApplication.processEvents()
    _drag(view, QPointF(r.grip_points()[0]), QPointF(30, 20), steps=10)
    tl, br = QPointF(r.grip_points()[0]), QPointF(r.grip_points()[4])
    assert (tl.x(), tl.y()) == pytest.approx((30.0, 0.0), abs=1.0)
    assert tl.y() == pytest.approx(0.0, abs=1e-6)
    assert (br.x(), br.y()) == pytest.approx((br0.x(), br0.y()), abs=1e-6)
