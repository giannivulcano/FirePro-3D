"""D2/D3: Shift+key window shortcuts route to the active scene; select-first gate.

Governing spec: docs/specs/scene-tools.md D2 (shortcut map; Align -> Shift+L;
Ctrl+M retired; Ctrl+C/X/V/D aliases) and D3 (select-first).
QTest cannot drive QShortcutMap, so shortcuts are fired via
``shortcut.activated.emit()`` on the real QShortcut object.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLineEdit

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from firepro3d.geometry_2d import LineItem
from firepro3d.model_view import Model_View
from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window

EXPECTED = {
    "Shift+C": "copy", "Shift+X": "cut", "Shift+V": "paste", "Shift+D": "duplicate",
    "Shift+M": "move", "Shift+R": "rotate", "Shift+O": "offset", "Shift+A": "array",
    "Shift+F": "flip", "Shift+I": "mirror", "Shift+S": "scale",
    "Shift+E": "fillet",
    "Ctrl+C": "copy", "Ctrl+X": "cut", "Ctrl+V": "paste", "Ctrl+D": "duplicate",
}


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow singleton."""
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_main_window_singleton):
    """Per-test view of the shared MainWindow."""
    yield _main_window_singleton


def _shortcut(win, seq):
    hits = [s for s in win.findChildren(QShortcut)
            if s.key() == QKeySequence(seq)]
    assert len(hits) == 1, f"{seq}: expected exactly one QShortcut, got {len(hits)}"
    return hits[0]


def test_shortcut_table_is_registered(main_window):
    for seq, tool in EXPECTED.items():
        _shortcut(main_window, seq)                     # exactly one each
    _shortcut(main_window, "Shift+L")                   # Align moved here
    assert not [s for s in main_window.findChildren(QShortcut)
                if s.key() == QKeySequence("Ctrl+M")]


@pytest.mark.parametrize("seq,tool", sorted(EXPECTED.items()))
def test_each_shortcut_routes_its_tool(main_window, monkeypatch, seq, tool):
    calls = []
    scene = main_window._active_scene()
    monkeypatch.setattr(scene._modify_ctl, "start", lambda t: calls.append(t))
    _shortcut(main_window, seq).activated.emit()
    assert calls == [tool]


def test_shift_m_starts_move_on_active_scene(main_window, monkeypatch):
    calls = []
    scene = main_window._active_scene()
    monkeypatch.setattr(scene._modify_ctl, "start", lambda tool: calls.append(tool))
    _shortcut(main_window, "Shift+M").activated.emit()
    assert calls == ["move"]


def test_shift_e_enters_fillet_on_the_active_scene(main_window):
    scene = main_window._active_scene()
    scene.clearSelection()
    _shortcut(main_window, "Shift+E").activated.emit()
    assert scene.mode == "fillet"                          # [RED] no QShortcut / no tool
    scene.set_mode(None)


def test_shortcut_refused_while_line_edit_focused(main_window, monkeypatch, qapp):
    from PyQt6.QtWidgets import QApplication, QLineEdit
    calls = []
    scene = main_window._active_scene()
    monkeypatch.setattr(scene._modify_ctl, "start", lambda tool: calls.append(tool))
    le = QLineEdit(main_window)
    try:
        le.show()
        main_window.activateWindow()
        le.setFocus()
        qapp.processEvents()
        assert QApplication.focusWidget() is le         # precondition
        _shortcut(main_window, "Shift+M").activated.emit()
        assert calls == []                               # [RED]
    finally:
        le.hide()
        le.deleteLater()
        qapp.processEvents()


def test_shift_l_is_align(main_window):
    scene = main_window._active_scene()
    _shortcut(main_window, "Shift+L").activated.emit()
    assert scene.mode == "align"
    scene.set_mode(None)


def test_select_first_gate_refuses_without_selection(model_space):
    model_space.clearSelection()
    model_space._modify_ctl.start("move")
    assert model_space.mode in (None, "select")         # [RED]


def test_start_move_with_selection_enters_move(model_space):
    a = LineItem(QPointF(0, 0), QPointF(100, 0))
    model_space.addItem(a); a.setSelected(True)
    model_space._modify_ctl.start("move")
    assert model_space.mode == "move"


def test_shift_m_drives_the_block_editor_scene(main_window, qapp):
    """I-4(a): a real Block Editor tab is current -> Shift+M moves in the
    EDITOR scene, never the hidden plan scene."""
    main_window.scene.clearSelection()
    main_window._open_block_editor()
    qapp.processEvents()
    ed = main_window._active_editor_widget()
    try:
        assert ed is not None
        editor = ed.editor_scene
        assert main_window.central_tabs.currentWidget() is ed
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        editor.addItem(line); editor._draw_lines.append(line)
        line.setSelected(True)
        _shortcut(main_window, "Shift+M").activated.emit()
        assert editor.mode == "move"
        assert main_window.scene.mode != "move"
        editor.set_mode(None)
    finally:
        if ed is not None:
            ed._modified = False
            main_window.block_editor_manager.close(ed)
            qapp.processEvents()


def test_shift_m_does_nothing_on_a_paper_tab(main_window, qapp):
    """I-4(b): a Paper tab is current -> Shift+M must not drive the hidden
    plan scene (spec I1 window-shortcut refusal)."""
    plan = main_window.scene
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    plan.addItem(line)                       # a real, selected plan item
    prev = main_window.central_tabs.currentIndex()
    try:
        plan.clearSelection(); line.setSelected(True)
        main_window._activate_paper_sheet()
        qapp.processEvents()
        assert main_window.central_tabs.currentWidget() is main_window.paper_space_widget
        _shortcut(main_window, "Shift+M").activated.emit()
        assert plan.mode != "move"                       # [RED] without the guard
    finally:
        plan.set_mode(None)
        plan.removeItem(line)
        main_window.central_tabs.setCurrentIndex(prev)
        qapp.processEvents()


@pytest.mark.parametrize("seq,tool", [("Shift+F", "flip"), ("Shift+I", "mirror"), ("Shift+S", "scale")])
def test_flip_mirror_keys_drive_the_block_editor_scene(main_window, qapp, seq, tool):
    """P1 M2: a real Block Editor tab is current -> the QShortcut enters the
    tool on the EDITOR scene (never the hidden plan scene)."""
    main_window.scene.clearSelection()
    main_window._open_block_editor()
    qapp.processEvents()
    ed = main_window._active_editor_widget()
    try:
        assert ed is not None
        editor = ed.editor_scene
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        editor.addItem(line); editor._draw_lines.append(line)
        line.setSelected(True)
        _shortcut(main_window, seq).activated.emit()
        assert editor.mode == tool                                        # [RED]
        assert main_window.scene.mode != tool
        editor.set_mode(None)
    finally:
        if ed is not None:
            ed._modified = False
            main_window.block_editor_manager.close(ed)
            qapp.processEvents()


def _plan_tab(win):
    tabs = win.central_tabs
    return next(tabs.widget(i) for i in range(tabs.count())
                if isinstance(tabs.widget(i), Model_View)
                and tabs.tabText(i).startswith("Plan: "))


def _visible_line_edit(win):
    return next(e for e in win.findChildren(QLineEdit) if e.isVisible())


@pytest.mark.parametrize("via", ["tab_x", "manager"])
@pytest.mark.parametrize("landing", ["plan", "paper", "editor"])
def test_closing_an_editor_focuses_the_landing_canvas(main_window, qapp, via, landing):
    """Ruling 2026-11-06: closing an editor focuses the canvas of the tab you
    land on. window.focusWidget() is the window's own focus child, so this holds
    whether or not the test window is the active one."""
    tabs = main_window.central_tabs
    mgr = main_window.block_editor_manager
    extra = None
    if landing == "paper":
        main_window._activate_paper_sheet()
        qapp.processEvents()
        land, want = main_window.paper_space_widget, main_window.paper_space_widget.view
    elif landing == "editor":
        extra = mgr.open_new()
        qapp.processEvents()
        land, want = extra, extra.view
    else:
        land = want = _plan_tab(main_window)
    home = tabs.indexOf(land)
    # Last tab, current: closing the editor opened after it lands here whichever
    # selection-on-remove behaviour the tab bar uses.
    tabs.tabBar().moveTab(home, tabs.count() - 1)
    tabs.setCurrentWidget(land)
    qapp.processEvents()
    ed = mgr.open_new()
    qapp.processEvents()
    assert tabs.currentWidget() is ed
    ed._mark_clean()
    try:
        if via == "tab_x":
            main_window._on_tab_close_requested(tabs.indexOf(ed))
        else:
            mgr.close(ed)
        qapp.processEvents()
        assert tabs.currentWidget() is land
        assert main_window.focusWidget() is want                          # [RED]
    finally:
        tabs.tabBar().moveTab(tabs.indexOf(land), home)
        if extra is not None:
            extra._mark_clean()
            mgr.close(extra)
        tabs.setCurrentWidget(_plan_tab(main_window))
        qapp.processEvents()


def test_shift_m_works_after_closing_an_editor_without_a_canvas_click(main_window, qapp):
    """The user-visible half: no click on the canvas is needed after a close."""
    plan = main_window.scene
    tabs = main_window.central_tabs
    plan_tab = _plan_tab(main_window)
    home = tabs.indexOf(plan_tab)
    # Last tab, current: a paper tab left open by an earlier test would otherwise
    # be the landing tab, and tools rightly refuse on paper.
    tabs.tabBar().moveTab(home, tabs.count() - 1)
    tabs.setCurrentWidget(plan_tab)
    qapp.processEvents()
    ed = main_window.block_editor_manager.open_new()
    qapp.processEvents()
    ed._mark_clean()
    # The user was working in the editor: closing it hands focus down the chain
    # to the Properties panel's Name field, and the shortcut gate reads the
    # application's focus widget, so the window must be the active one.
    main_window.activateWindow()
    ed.view.setFocus()
    qapp.processEvents()
    assert main_window.focusWidget() is ed.view
    main_window._on_tab_close_requested(tabs.indexOf(ed))
    qapp.processEvents()
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    plan.addItem(line); plan._draw_lines.append(line)
    try:
        assert tabs.currentWidget() is plan_tab
        plan.clearSelection(); line.setSelected(True)
        _shortcut(main_window, "Shift+M").activated.emit()
        assert plan.mode == "move"                                        # [RED]
    finally:
        plan.set_mode(None)
        plan.clearSelection()
        plan._draw_lines.remove(line)
        plan.removeItem(line)
        tabs.tabBar().moveTab(tabs.indexOf(plan_tab), home)
        qapp.processEvents()


@pytest.mark.parametrize("reopen", [False, True], ids=["fresh", "reopen"])
def test_opening_an_editor_focuses_its_canvas(main_window, qapp, reopen):
    """Ruling 2026-11-06, both open branches: a text field holding focus (the
    Properties panel Name row) does not keep it, so tool keys reach the editor."""
    tabs = main_window.central_tabs
    mgr = main_window.block_editor_manager
    first = None
    if reopen:
        first = mgr.open_new()
        qapp.processEvents()
        tabs.setCurrentWidget(_plan_tab(main_window))
        qapp.processEvents()
    field = _visible_line_edit(main_window)
    field.setFocus()
    assert main_window.focusWidget() is field
    ed = mgr.open_for_definition(first._editor_key) if reopen else mgr.open_new()
    qapp.processEvents()
    try:
        assert tabs.currentWidget() is ed
        assert main_window.focusWidget() is ed.view                       # [RED]
    finally:
        ed._mark_clean()
        mgr.close(ed)
        qapp.processEvents()


@pytest.mark.parametrize("seq", ["Shift+F", "Shift+I", "Shift+S"])
def test_flip_mirror_keys_refused_while_line_edit_focused(main_window, monkeypatch,
                                                          qapp, seq):
    from PyQt6.QtWidgets import QApplication, QLineEdit
    calls = []
    scene = main_window._active_scene()
    monkeypatch.setattr(scene._modify_ctl, "start", lambda tool: calls.append(tool))
    le = QLineEdit(main_window)
    try:
        le.show()
        main_window.activateWindow()
        le.setFocus()
        qapp.processEvents()
        assert QApplication.focusWidget() is le         # precondition
        _shortcut(main_window, seq).activated.emit()
        assert calls == []
    finally:
        le.hide()
        le.deleteLater()
        qapp.processEvents()
