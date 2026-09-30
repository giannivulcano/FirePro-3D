"""MainWindow end-to-end guards for the closable 3D Model tab (view-3d.md §10).

Real MainWindow + real View3D (not the stub): the behaviour under test is the
VTK widget's lifecycle. Pops a real window (exposure needed for isVisible()).
"""
from __future__ import annotations

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtTest import QTest


def _make_window():
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    return main_mod.MainWindow()


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from firepro3d import snap_engine
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = _make_window()
    w.resize(1200, 800)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(300)
    yield w
    w._modified = False
    w.close()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _close_3d(win):
    win._on_tab_close_requested(win.central_tabs.indexOf(win.view_3d))


def _close_all(win):
    while win.central_tabs.count():
        _close_3d(win) if win.central_tabs.widget(0) is win.view_3d \
            else win._on_tab_close_requested(0)
    QTest.qWait(100)


def _count(obj, name):
    calls = []
    orig = getattr(obj, name)
    setattr(obj, name, lambda *a, **k: (calls.append(1), orig(*a, **k))[1])
    return calls


def _wall_and_pipe(win):
    from firepro3d.wall import WallSegment
    wall = WallSegment(QPointF(0, 500), QPointF(1000, 500))
    win.scene.addItem(wall)
    win.scene._walls.append(wall)
    pipe = win.scene.add_pipe(win.scene.add_node(0, 0),
                              win.scene.add_node(1000, 0))
    return wall, pipe


def test_close_keeps_view_alive_and_idle_then_reopen_rebuilds_once(mw):   # guard 1
    win = mw
    assert win.central_tabs.tabBar().tabButton(
        win.central_tabs.indexOf(win.view_3d),
        win.central_tabs.tabBar().ButtonPosition.RightSide
    ) is not None, "3D tab must carry the close dot"
    _close_3d(win)
    assert win.central_tabs.indexOf(win.view_3d) == -1
    assert not sip.isdeleted(win.view_3d)
    rebuilds = _count(win.view_3d, "rebuild")
    win.scene.push_undo_state()                 # a scene edit
    QTest.qWait(500)
    assert rebuilds == []
    win.project_browser.activate3DView.emit()
    QTest.qWait(500)
    assert win.central_tabs.indexOf(win.view_3d) == 0
    assert win.central_tabs.currentWidget() is win.view_3d
    assert len(rebuilds) == 1


def test_open_closed_state_is_remembered_across_windows(mw, qapp):           # guard 2
    _close_3d(mw)
    assert QSettings("GV", "FirePro3D").value("ui/view3d_open", True, type=bool) is False
    win2 = _make_window()
    try:
        assert win2.central_tabs.indexOf(win2.view_3d) == -1
        win2.view3d_tab.open()
        assert QSettings("GV", "FirePro3D").value("ui/view3d_open", False, type=bool) is True
    finally:
        win2._modified = False
        win2.close()


def test_stale_3d_pick_never_deletes_from_a_plan(mw):                       # guard 3 (D8)
    """A 3D pick left behind when the user switches (3D tab still open) to a
    plan must not hijack Delete there — the plan's selection is deleted."""
    win = mw
    wall, pipe = _wall_and_pipe(win)
    win.view_3d._3d_selected = [wall]          # a pick made in 3D
    win._activate_plan_view("Level 1")         # 3D tab stays open, not current
    assert win.central_tabs.indexOf(win.view_3d) != -1
    assert win.central_tabs.currentWidget() is not win.view_3d
    win.scene.clearSelection(); pipe.setSelected(True)
    win._delete_if_not_editing()
    assert pipe not in win.scene.sprinkler_system.pipes
    assert wall in win.scene._walls


def test_closing_3d_drops_its_pick_before_a_plan_delete(mw):                # guard 3b (I7)
    win = mw
    wall, pipe = _wall_and_pipe(win)
    win.view_3d._3d_selected = [wall]          # a pick made in 3D
    _close_3d(win)
    win._activate_plan_view("Level 1")
    win.scene.clearSelection(); pipe.setSelected(True)
    win._delete_if_not_editing()
    assert pipe not in win.scene.sprinkler_system.pipes
    assert wall in win.scene._walls


def test_empty_canvas_placeholder_refuses_tools_and_reopens(mw):            # guard 4
    win = mw
    seen = []
    win.central_tabs.currentChanged.connect(seen.append)
    win.scene.set_mode("pipe")                 # an armed tool when the last view closes
    _close_all(win)
    # _on_tab_changed ran for the empty canvas (index -1) without raising —
    # a raise in a PyQt slot would abort this process.
    assert seen[-1] == -1
    assert win._canvas_stack.currentWidget() is win._empty_canvas
    assert win._empty_canvas.isVisible()
    assert win.scene.mode == "select", "an armed tool must not survive the last view"
    win.scene.set_mode("pipe")
    assert win.scene.mode != "pipe"
    win._empty_canvas._btn_plan.click()
    assert win.central_tabs.tabText(win.central_tabs.currentIndex()).startswith("Plan: ")
    assert win._canvas_stack.currentWidget() is win.central_tabs
    win._empty_canvas._btn_3d.click()
    assert win.central_tabs.currentWidget() is win.view_3d


def test_placeholder_rail_matches_canvas_tab_bar(qapp, tmp_path, monkeypatch):  # guard 5
    """Under the live app QSS/font the placeholder rail keeps the tab row's
    height and bottom edge, so the dock-header divider row stays aligned."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from firepro3d import theme as th
    old_font, old_ss = qapp.font(), qapp.styleSheet()
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    try:
        win = _make_window()
        try:
            win.resize(1200, 800)
            win.show()
            QTest.qWaitForWindowExposed(win)
            QTest.qWait(300)
            bar = win.central_tabs.tabBar()
            bottom = lambda wd: wd.mapTo(win, wd.rect().bottomLeft()).y()
            bar_h, bar_bottom = bar.height(), bottom(bar)
            _close_all(win)
            rail = win._empty_canvas._rail
            assert rail.height() == bar_h
            assert bottom(rail) == bar_bottom
        finally:
            win._modified = False
            win.close()
    finally:
        qapp.setStyleSheet(old_ss)
        qapp.setFont(old_font)


def test_new_project_reseats_the_3d_view(mw):                               # guard 6
    win = mw
    win.view_3d._first_build = False
    win._modified = False
    win.new_file()
    assert win.view_3d._sm is win.scene.scale_manager
    assert win.view_3d._first_build is True
