"""Pick mode (D21) + Constrain/Inspect ribbon (D15) — parametric-constraint-system.md.

Real MainWindow, shown, under the live app QSS + font; real ribbon buttons;
posted mouse / key events on the shown Block Editor view; pixel sampling of
the pick markers and the hovered-edge glow (D27).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from firepro3d import snap_engine
from firepro3d import theme as th
from firepro3d.geometry_2d import CircleItem, LineItem

NO_EDITOR_TIP = "Open or create a block to edit"
PAGE = "Block Editor"
CONSTRAIN_LABELS = {"Horizontal", "Show Constraints", "Delete Constraints"}


@pytest.fixture(scope="module")
def mw(qapp, tmp_path_factory):
    import os
    prev_qss, prev_font = qapp.styleSheet(), qapp.font()
    prev_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(tmp_path_factory.mktemp("appdata"))
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    w = main_mod.MainWindow()
    w.resize(1400, 850)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(200)
    yield w
    # A plan selection alive at close kills the process (filed) — clear first.
    w.scene.clearSelection()
    w._modified = False
    w.close()
    w.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)
    if prev_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = prev_appdata


def _editors(w):
    from firepro3d.block_editor import BlockEditorWidget
    return [w.central_tabs.widget(i) for i in range(w.central_tabs.count())
            if isinstance(w.central_tabs.widget(i), BlockEditorWidget)]


def _plan_index(w):
    for i in range(w.central_tabs.count()):
        if w.central_tabs.tabText(i).startswith("Plan: "):
            return i
    raise AssertionError("no plan tab")


@pytest.fixture
def win_with_editor(mw, qapp):
    """The MainWindow with a fresh, current Block Editor tab whose view sits
    at 1 px / mm centred on the origin."""
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    v = ed.view
    v.resetTransform()
    v.centerOn(0, 0)
    ed.editor_scene.set_mode("select")
    qapp.processEvents()
    mw._test_editor = ed
    yield mw
    try:
        ed.editor_scene.set_mode("select")
        ed.editor_scene.clearSelection()
    except RuntimeError:
        pass
    for e in _editors(mw):
        mw.block_editor_manager.close(e)
    mw._test_editor = None
    mw.scene.clearSelection()
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()


# ── helpers ──────────────────────────────────────────────────────────────────

def _editor_scene(win):
    return win._active_scene()


def _view(win):
    return win._test_editor.view


def _btn(win, label):
    return win._be_constrain_buttons[label]


def _page(w):
    tb = w.ribbon._tab_bar
    for i in range(tb.count()):
        if tb.tabText(i) == PAGE:
            return w.ribbon._stack.widget(i)
    raise AssertionError(PAGE)


def _groups(page):
    """``[(TITLE, RibbonGroup)]`` in on-page (layout) order."""
    from firepro3d.ribbon_bar import RibbonGroup
    from PyQt6.QtWidgets import QLabel
    out = []
    lay = page._layout
    for i in range(lay.count()):
        g = lay.itemAt(i).widget()
        if isinstance(g, RibbonGroup):
            out.append((g.findChildren(QLabel)[0].text(), g))
    return out


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    sc.addItem(ln)
    sc._draw_lines.append(ln)
    return ln


def _vp(v, x, y):
    return v.mapFromScene(QPointF(x, y))


def _move(v, vp):
    """A real hover move delivered through the viewport (no buttons)."""
    QApplication.sendEvent(v.viewport(), QMouseEvent(
        QEvent.Type.MouseMove, QPointF(vp), Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def _click(v, vp):
    _move(v, vp)
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton, pos=vp)
    QApplication.processEvents()


def _grab(v):
    v.viewport().repaint()
    QApplication.processEvents()
    img = v.viewport().grab().toImage()
    return img, img.devicePixelRatio()


def _px(img, dpr, x, y) -> QColor:
    return img.pixelColor(int(round(x * dpr)), int(round(y * dpr)))


def _dist(a: QColor, b: QColor) -> int:
    return (abs(a.red() - b.red()) + abs(a.green() - b.green())
            + abs(a.blue() - b.blue()))


def _status(win):
    return win.statusBar().currentMessage()


# ── D15: groups, roster, tooltips ────────────────────────────────────────────

def test_constrain_and_inspect_groups_after_modify(win_with_editor):
    win = win_with_editor
    titles = [t for t, _g in _groups(_page(win))]
    i = titles.index("MODIFY")
    assert titles[i + 1:] == ["CONSTRAIN", "INSPECT"]
    groups = dict(_groups(_page(win)))
    assert {b.text() for b in groups["CONSTRAIN"].findChildren(QToolButton)} \
        == {"Horizontal"}                       # no greyed placeholders (D15)
    assert {b.text() for b in groups["INSPECT"].findChildren(QToolButton)} \
        == {"Show Constraints", "Delete Constraints"}
    assert set(win._be_constrain_buttons) == CONSTRAIN_LABELS
    for b in win._be_constrain_buttons.values():
        assert b.toolTip() and b.toolTip() != NO_EDITOR_TIP


def test_buttons_disabled_with_no_editor_tooltip_when_no_editor_current(
        win_with_editor, qapp):
    win = win_with_editor
    win.central_tabs.setCurrentIndex(_plan_index(win))
    qapp.processEvents()
    win._refresh_modify_buttons()            # a selection/clipboard refresh
    for label, b in win._be_constrain_buttons.items():
        assert not b.isEnabled(), label
        assert b.toolTip() == NO_EDITOR_TIP, label


def test_plan_scene_refuses_the_constraint_pick_mode(win_with_editor, qapp):
    win = win_with_editor
    win.central_tabs.setCurrentIndex(_plan_index(win))
    qapp.processEvents()
    win.scene.set_mode("constrain_horizontal")
    assert win.scene.mode != "constrain_horizontal"
    assert win.scene.constraint_ctl.pick is None


# ── D21 selection-first ──────────────────────────────────────────────────────

def test_selection_first_horizontal_on_a_selected_line(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    ln = _line(sc, (0, 0), (100, 30))
    ln.setSelected(True)
    QApplication.processEvents()
    assert _btn(win, "Horizontal").isEnabled()
    _btn(win, "Horizontal").click()
    QApplication.processEvents()
    assert abs(ln._pt1.y() - ln._pt2.y()) < 1e-6
    assert abs(ln._pt1.y() - 15) < 1e-6                      # D22 mean
    assert [c.type for c in sc.constraint_ctl.constraints_on(ln)] == ["horizontal"]
    assert sc.mode in (None, "select")
    assert not _btn(win, "Horizontal").isChecked()


def test_horizontal_disabled_on_an_invalid_selection(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    c = CircleItem(QPointF(0, 0), 20)
    sc.addItem(c)
    sc._draw_circles.append(c)
    c.setSelected(True)
    QApplication.processEvents()
    assert not _btn(win, "Horizontal").isEnabled()
    c.setSelected(False)
    QApplication.processEvents()
    assert _btn(win, "Horizontal").isEnabled()               # nothing -> pick mode


# ── D21 pick mode by posted events ───────────────────────────────────────────

def test_pick_mode_two_points_by_posted_clicks(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    _line(sc, (0, 0), (100, 0))
    b = _line(sc, (0, 60), (100, 90))
    sc.clearSelection()
    QApplication.processEvents()
    _btn(win, "Horizontal").click()
    assert sc.mode == "constrain_horizontal"
    assert _btn(win, "Horizontal").isChecked()
    assert sc.constraint_ctl.pick is not None
    v = _view(win)
    _click(v, _vp(v, 0, 60))
    assert sc.constraint_ctl.pick is not None and len(sc.constraint_ctl.pick.picks) == 1
    _click(v, _vp(v, 100, 90))
    assert abs(b._pt1.y() - b._pt2.y()) < 1e-6 and abs(b._pt1.y() - 75) < 1e-6
    assert [c.refs for c in sc.constraint_ctl.constraints] == [
        [{"uid": b._uid, "h": "p1"}, {"uid": b._uid, "h": "p2"}]]
    assert sc.mode in (None, "select") and sc.constraint_ctl.pick is None
    assert not _btn(win, "Horizontal").isChecked()


def test_pick_mode_one_edge_by_posted_click(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    b = _line(sc, (0, 60), (200, 90))
    sc.clearSelection()
    _btn(win, "Horizontal").click()
    v = _view(win)
    _click(v, _vp(v, 100, 75))                    # mid-edge, far from the ends
    assert abs(b._pt1.y() - b._pt2.y()) < 1e-6
    assert [c.refs for c in sc.constraint_ctl.constraints] == [
        [{"uid": b._uid, "h": "edge"}]]
    assert sc.mode in (None, "select")


def test_pick_status_counts_and_same_point_is_refused(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    b = _line(sc, (0, 60), (100, 90))
    sc.clearSelection()
    _btn(win, "Horizontal").click()
    QApplication.processEvents()
    instr = []
    sc.instructionChanged.connect(instr.append)
    try:
        v = _view(win)
        _click(v, _vp(v, 0, 60))
        assert instr[-1] == "Horizontal: pick 2 points or 1 edge (1/2) · Esc to cancel"
        _click(v, _vp(v, 0, 60))                  # the same handle again
        assert _status(win) == "Pick a different point"
        assert len(sc.constraint_ctl.pick.picks) == 1
        assert sc.constraint_ctl.constraints == []
        assert sc.mode == "constrain_horizontal"
        assert (b._pt1.y(), b._pt2.y()) == (60, 90)
    finally:
        sc.instructionChanged.disconnect(instr.append)


def test_entering_pick_mode_posts_the_counted_status(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    instr = []
    sc.instructionChanged.connect(instr.append)
    try:
        _btn(win, "Horizontal").click()
    finally:
        sc.instructionChanged.disconnect(instr.append)
    assert instr[-1] == "Horizontal: pick 2 points or 1 edge (0/2) · Esc to cancel"


# ── Esc ──────────────────────────────────────────────────────────────────────

def test_escape_cancels_pick(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    sc.clearSelection()
    _btn(win, "Horizontal").click()
    assert sc.constraint_ctl.pick is not None
    QTest.keyClick(_view(win).viewport(), Qt.Key.Key_Escape)
    QApplication.processEvents()
    assert sc.mode in (None, "select") and sc.constraint_ctl.pick is None
    assert not _btn(win, "Horizontal").isChecked()


def test_window_escape_clears_a_selected_constraint(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    ctl.select(c.id)
    assert ctl.selected_id == c.id
    win._on_escape()                          # the window Esc QShortcut slot
    assert ctl.selected_id is None
    assert c in ctl.constraints               # deselected, not deleted


def test_scene_escape_clears_a_selected_constraint(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    ctl.select(c.id)
    QApplication.sendEvent(sc, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                         Qt.KeyboardModifier.NoModifier))
    assert ctl.selected_id is None
    assert c in ctl.constraints


# ── Delete Constraints ───────────────────────────────────────────────────────

def test_delete_constraints_on_a_selected_line_removes_its_constraints(
        win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    ln = _line(sc, (0, 0), (100, 30))
    other = _line(sc, (0, 100), (100, 140))
    ctl = sc.constraint_ctl
    ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    keep = ctl.add("horizontal", [{"uid": other._uid, "h": "edge"}])
    sc.clearSelection()
    ln.setSelected(True)
    QApplication.processEvents()
    d = _btn(win, "Delete Constraints")
    assert d.isEnabled()
    d.click()
    QApplication.processEvents()
    assert ctl.constraints_on(ln) == []
    assert ctl.constraints == [keep]
    assert ln.scene() is sc                   # geometry untouched
    assert not d.isEnabled()                  # nothing left on the selection


def test_delete_constraints_enables_on_a_glyph_selected_constraint(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    ln = _line(sc, (0, 0), (100, 30))
    ctl = sc.constraint_ctl
    c = ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    sc.clearSelection()
    QApplication.processEvents()
    d = _btn(win, "Delete Constraints")
    assert not d.isEnabled()
    ctl.select(c.id)                          # glyph click path
    assert d.isEnabled()
    d.click()
    assert ctl.constraints == [] and ctl.selected_id is None


# ── D27 pixels: markers + edge glow ──────────────────────────────────────────

def test_pick_markers_paint_hollow_and_hover_filled(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    v = _view(win)
    _line(sc, (40, 60), (240, 60))
    sc.clearSelection()
    t = th.detect()
    end = _vp(v, 240, 60)
    _move(v, _vp(v, 0, -200))                 # cursor far from every handle
    before, dpr = _grab(v)
    on_line = _px(before, dpr, end.x() - 1, end.y())
    _btn(win, "Horizontal").click()
    _move(v, _vp(v, 0, -200))
    img, dpr = _grab(v)
    centre = _px(img, dpr, end.x() - 1, end.y())
    border = _px(img, dpr, end.x() + 4, end.y() + 2)
    bg = _px(before, dpr, end.x() + 4, end.y() + 2)
    # Hollow: the surface fill hides the line inside, the border is drawn.
    assert _dist(centre, t.color("surface")) < _dist(on_line, t.color("surface"))
    assert _dist(centre, t.color("surface")) <= 30
    assert _dist(border, t.color("muted")) < _dist(bg, t.color("muted"))
    # Hover the endpoint: the marker fills with accent.
    _move(v, end)
    hov, dpr = _grab(v)
    assert sc.constraint_ctl.pick.hover == {"uid": sc._draw_lines[-1]._uid, "h": "p2"}
    assert _dist(_px(hov, dpr, end.x() - 1, end.y()), t.color("accent")) <= 30


def test_edge_hover_glows_before_the_first_point_pick(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    v = _view(win)
    ln = _line(sc, (40, 60), (240, 60))
    sc.clearSelection()
    t = th.detect()
    mid = _vp(v, 140, 60)
    _btn(win, "Horizontal").click()
    _move(v, _vp(v, 0, -200))
    base, dpr = _grab(v)
    _move(v, mid + type(mid)(0, 3))           # 3 px off the edge (tol 6)
    assert sc.constraint_ctl.pick.hover == {"uid": ln._uid, "h": "edge"}
    img, dpr = _grab(v)
    off = _px(img, dpr, mid.x(), mid.y() + 2)
    off0 = _px(base, dpr, mid.x(), mid.y() + 2)
    assert _dist(off, t.color("accent")) + 60 < _dist(off0, t.color("accent"))


def test_halo_suppressed_during_pick(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    v = _view(win)
    ln = _line(sc, (40, 60), (240, 60))
    sc.clearSelection()
    _move(v, _vp(v, 140, 60))
    assert sc.halo_item() is ln               # HALO live in select mode
    _btn(win, "Horizontal").click()
    _move(v, _vp(v, 140, 61))
    assert sc.halo_item() is None
    assert sc._halo_suppressed()


def test_new_mode_ends_the_pick_session(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    _btn(win, "Horizontal").click()
    assert sc.constraint_ctl.pick is not None
    sc.set_mode("draw_line")
    assert sc.constraint_ctl.pick is None
    assert not _btn(win, "Horizontal").isChecked()


def test_lit_horizontal_button_click_ends_pick(win_with_editor):
    win = win_with_editor
    sc = _editor_scene(win)
    _btn(win, "Horizontal").click()
    assert sc.mode == "constrain_horizontal"
    _btn(win, "Horizontal").click()
    assert sc.mode in (None, "select") and sc.constraint_ctl.pick is None
    assert not _btn(win, "Horizontal").isChecked()


def test_show_constraints_toggle_is_the_show_all_override(win_with_editor):
    """D32: Show Constraints is a temporary SHOW-ALL override, default OFF."""
    from firepro3d import constraint_paint as cp
    win = win_with_editor
    sc = _editor_scene(win)
    sc.clearSelection()
    ln = _line(sc, (0, 0), (100, 30))
    c = sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    b = _btn(win, "Show Constraints")
    assert b.toolTip() == ("Show Constraints \u2014 show every constraint glyph "
                           "(otherwise only the selected geometry's)")
    view = _view(win)
    assert not b.isChecked() and not sc.constraint_ctl.show_all
    assert cp.glyph_layouts(view, sc.constraint_ctl) == []
    b.click()
    assert sc.constraint_ctl.show_all
    assert [cid for cid, _r in cp.glyph_layouts(view, sc.constraint_ctl)] == [c.id]
    b.click()
    assert not sc.constraint_ctl.show_all
    assert cp.glyph_layouts(view, sc.constraint_ctl) == []


# ── CS2 D40: the nothing-selected Block Editor panel is the block view ──────

def test_d40_nothing_selected_in_editor_shows_block_view(win_with_editor, qapp):
    from firepro3d.ui_kit import StatusBadge
    win = win_with_editor
    sc = win._active_scene()
    ln = LineItem(QPointF(0, 0), QPointF(100, 30))
    sc.addItem(ln); sc._draw_lines.append(ln)
    sc.clearSelection()
    win.update_property_manager()
    qapp.processEvents()
    badges = [b for b in win.prop_manager.findChildren(StatusBadge) if b.isVisible()]
    assert [b.text() for b in badges] == ["Under-defined \u00b7 4 DOF"]
    # A constraint commit refreshes it through the controller's fallback.
    sc.constraint_ctl.add("horizontal", [{"uid": ln._uid, "h": "edge"}])
    qapp.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()
    badges = [b for b in win.prop_manager.findChildren(StatusBadge) if b.isVisible()]
    assert [b.text() for b in badges] == ["Under-defined \u00b7 3 DOF"]
