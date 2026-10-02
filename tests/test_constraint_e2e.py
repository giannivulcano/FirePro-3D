"""CS1 end-to-end guards — parametric-constraint-system.md §11 #2-#4.

Real MainWindow (shown, live app QSS + font), a real Block Editor tab, the
real ribbon buttons, posted mouse / key events on the shown editor view, and
observable geometry as ground truth. The MainWindow + open-editor fixtures
are the Task 12 ones (``tests/test_constraint_pick_ribbon.py``).
"""
from __future__ import annotations

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
        r = ops[0][2].boundingRect()
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
