"""MainWindow end-to-end guards for the closable 3D Model tab (view-3d.md §10).

Real MainWindow + real View3D (not the stub): the behaviour under test is the
VTK widget's lifecycle. Pops a real window (exposure needed for isVisible()).
"""
from __future__ import annotations

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtTest import QTest

from firepro3d.model_space import NO_VIEW_HINT


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
    # A plan selection alive at close emits selectionChanged during the
    # scene's destruction into _on_selection_changed_contextual (pre-existing,
    # filed separately) — clear it first so teardown can't abort the process.
    w.scene.clearSelection()
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


def _selected_pipe(win):
    pipe = win.scene.add_pipe(win.scene.add_node(0, -800),
                              win.scene.add_node(1000, -800))
    win.scene.clearSelection()
    pipe.setSelected(True)
    return pipe


def _shortcut(win, seq):
    from PyQt6.QtGui import QKeySequence, QShortcut
    hits = [s for s in win.findChildren(QShortcut) if s.key() == QKeySequence(seq)]
    assert len(hits) == 1, f"{seq}: {len(hits)} shortcuts"
    return hits[0]


def _ribbon_buttons(win, tooltip):
    from PyQt6.QtWidgets import QAbstractButton
    hits = [b for b in win.findChildren(QAbstractButton) if b.toolTip() == tooltip]
    assert hits, f"no ribbon button with tooltip {tooltip!r}"
    return hits


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
    assert win.view_3d.get_3d_selected() == []  # closing drops the pick (I7)
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
    # Delete key and Shift+M (real QShortcuts) are refused with the hint.
    pipe = _selected_pipe(win)
    win.footer.set_instruction("")
    _shortcut(win, "Delete").activated.emit()
    assert pipe in win.scene.sprinkler_system.pipes
    assert win.footer.instruction.text() == NO_VIEW_HINT
    win.footer.set_instruction("")
    _shortcut(win, "Shift+M").activated.emit()
    assert win.scene.mode in (None, "select")
    assert win.footer.instruction.text() == NO_VIEW_HINT
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


def test_open_project_reseats_the_3d_view(mw, tmp_path, monkeypatch):      # guard 6b (I9)
    win = mw
    path = str(tmp_path / "reseat.fpd")
    assert win.scene.save_to_file(path) is not False
    wall, _pipe = _wall_and_pipe(win)
    win.view3d_tab.open()
    win.view_3d._3d_selected = [wall]          # a pick in the old project
    old_sm = win.scene.scale_manager
    win._modified = False
    monkeypatch.setattr(win, "_maybe_offer_template_push", lambda: None)
    win._load_project(path)
    assert win.scene.scale_manager is not old_sm, "load replaces the manager"
    assert win.view_3d._sm is win.scene.scale_manager
    assert win.view_3d.get_3d_selected() == []


def test_startup_seats_the_live_scale_manager(mw):                         # MINOR-3
    assert mw.view_3d._sm is mw.scene.scale_manager


def test_visible_3d_rebuilds_once_per_edit(mw):                            # guard 7 (I6)
    win = mw
    win.view3d_tab.open()
    QTest.qWait(800)
    rebuilds = _count(win.view_3d, "rebuild")
    win.scene.push_undo_state()                 # one edit
    QTest.qWait(900)                            # > 200 ms debounce + 100 ms timer
    assert len(rebuilds) == 1


def test_ribbon_delete_is_refused_on_empty_canvas(mw):                     # guard 8 (I5)
    win = mw
    _close_all(win)
    pipe = _selected_pipe(win)
    win.footer.set_instruction("")
    for b in _ribbon_buttons(win, "Delete selected items (Del)"):
        b.click()
    assert pipe in win.scene.sprinkler_system.pipes
    assert win.footer.instruction.text() == NO_VIEW_HINT


def test_paste_and_offset_are_refused_on_empty_canvas(mw):          # guard 9 (I5)
    from firepro3d.geometry_2d import LineItem
    win = mw
    s = win.scene
    pipe = _selected_pipe(win)
    assert s._modify_ctl.write_clipboard([pipe.node1], QPointF(0, 0)), \
        "OS clipboard refused the write (environment)"
    assert s.clipboard_payload() is not None
    _close_all(win)
    # The contextual (pipe) tab's Edit group carries Paste while the pipe
    # stays selected.
    s.clearSelection(); pipe.setSelected(True)
    s._last_scene_pos = QPointF(50, 50)        # cursor was last over the canvas
    n_items = len(s.items())
    start_pos = s.node_start_pos
    win.footer.set_instruction("")
    _ribbon_buttons(win, "Paste — ghost on the cursor, click to place "
                         "(Shift+V / Ctrl+V)")[0].click()
    assert s._paste_payload is None
    assert s.node_start_pos is start_pos
    assert len(s.items()) == n_items, "no ghost items on an empty canvas"
    assert s.mode in (None, "select")
    assert win.footer.instruction.text() == NO_VIEW_HINT
    line = LineItem(QPointF(0, 2000), QPointF(1000, 2000))
    s.addItem(line)
    s.clearSelection(); line.setSelected(True)
    win.footer.set_instruction("")
    # The plan ribbon has no Modify group (Block Editor page only) — Offset's
    # plan entry is the Shift+O window shortcut.
    _shortcut(win, "Shift+O").activated.emit()
    assert s._offset_source is None
    assert s.mode in (None, "select")
    assert win.footer.instruction.text() == NO_VIEW_HINT


def test_radiation_is_refused_with_no_view(mw):                            # MINOR-2 (a)
    win = mw
    _close_all(win)
    win.footer.set_instruction("")
    btn = _ribbon_buttons(win, "Run thermal radiation analysis [F6]")[0]
    btn.click()
    assert win.scene._radiation_selecting is False
    assert win._radiation_step == 0
    assert not btn.isChecked()
    assert win.footer.instruction.text() == NO_VIEW_HINT


def test_closing_last_view_cancels_a_radiation_pick(mw):                   # MINOR-2 (b)
    win = mw
    win._radiation_step1_start()
    assert win.scene._radiation_selecting is True
    _close_all(win)
    assert win.scene._radiation_selecting is False
    assert win._radiation_step == 0
    assert win.scene.mode in (None, "select")


def test_placeholder_plan_label_follows_level_changes(mw):                 # MINOR-6
    win = mw
    _close_all(win)
    win.level_widget._add_level()
    new = win.level_mgr.levels[-1].name
    win._apply_plan_level(new)                 # active level changes, canvas still empty
    win.level_widget._add_level()              # a levels edit while empty
    assert win._canvas_stack.currentWidget() is win._empty_canvas
    assert win._empty_canvas._btn_plan.text() == f"Plan: {new}"
    win._empty_canvas._btn_plan.click()
    assert win.central_tabs.tabText(win.central_tabs.currentIndex()) == f"Plan: {new}"
