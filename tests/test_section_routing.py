"""Elevation parity, area A: section-tab routing guards (design D1).

Real MainWindow, shown, a placed section's tab current (the
``_window_with_hosted_block`` builder from test_hosted_blocks_edit). Keys go
through the window's wired QShortcuts (``QTest.keyClick`` on the window
handle); mouse / context events are sent to the section view's viewport.
"""
from __future__ import annotations

import sys

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu

from tests._mainwindow_helpers import dispose_main_window
from tests.test_hosted_blocks_edit import _window_with_hosted_block

SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
NOMOD = Qt.KeyboardModifier.NoModifier
KEYS = {
    "Shift+M": (Qt.Key.Key_M, SHIFT), "Shift+C": (Qt.Key.Key_C, SHIFT),
    "Shift+R": (Qt.Key.Key_R, SHIFT), "Shift+F": (Qt.Key.Key_F, SHIFT),
    "Shift+S": (Qt.Key.Key_S, SHIFT), "Shift+A": (Qt.Key.Key_A, SHIFT),
    "Ctrl+C": (Qt.Key.Key_C, CTRL), "Ctrl+X": (Qt.Key.Key_X, CTRL),
    "Ctrl+D": (Qt.Key.Key_D, CTRL), "Ctrl+A": (Qt.Key.Key_A, CTRL),
    "Ctrl+V": (Qt.Key.Key_V, CTRL),
    "Ctrl+Z": (Qt.Key.Key_Z, CTRL), "Ctrl+Y": (Qt.Key.Key_Y, CTRL),
    "F3": (Qt.Key.Key_F3, NOMOD), "Escape": (Qt.Key.Key_Escape, NOMOD),
    "Delete": (Qt.Key.Key_Delete, NOMOD),
}


def press(win, seq):
    """Send the real key through the window's wired QShortcut (VC3)."""
    key, mods = KEYS[seq]
    QTest.keyClick(win.windowHandle(), key, mods)
    QApplication.processEvents()


@pytest.fixture
def section_win(qapp):
    """``(win, ms, sec, gl, plan_gl, inst)``: shown MainWindow, placed section
    ``(0,0)-(10000,0)`` current, hosted block *inst* on gridline *gl* with its
    copy selected in the section, plan gridline *plan_gl* selected in plan.
    The tuple holds the Model_Space for the test's life."""
    made = _window_with_hosted_block()
    try:
        yield made
    finally:
        dispose_main_window(made[0])


# A forced, synchronous section rebuild (the debounce timer stopped): the
# one shared def (integrator PI-12).
from tests._section_window_helpers import settle as rebuild  # noqa: E402


def parallel_pipe(ms, sec):
    """A pipe parallel to the cut: ONE selectable proxy (probe at 41a76d1b)."""
    pipe = ms.add_pipe(ms.add_node(1000, -1500), ms.add_node(8000, -1500))
    rebuild(sec)
    return pipe


def crossing_pipe(ms, sec):
    """A pipe crossing the cut diagonally: TWO selectable proxies sharing one
    ``_ROLE_SOURCE`` (``_ElevCutEllipse`` + ``_ElevProxyLine``, probe at 41a76d1b)."""
    pipe = ms.add_pipe(ms.add_node(3000, 1000), ms.add_node(7000, -2000))
    rebuild(sec)
    return pipe


def proxies_of(sec, src):
    """Selectable section items whose ``_ROLE_SOURCE`` is *src*."""
    from firepro3d.section_scene import _ROLE_SOURCE
    return [it for it in sec.items() if it.data(_ROLE_SOURCE) is src
            and it.flags() & it.GraphicsItemFlag.ItemIsSelectable]


def test_right_click_hide_on_empty_section_canvas_hides_the_selection(
        section_win, monkeypatch):
    """AC8: a selection, then a right-click on EMPTY canvas, then Hide: the
    selection's source is hidden and nothing raises (target is None there)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = win.central_tabs.currentWidget()
    pipe = parallel_pipe(ms, sec)
    (line,) = proxies_of(sec, pipe)
    sec.clearSelection()
    line.setSelected(True)
    empty = QPointF(5000.0, -20000.0)            # 20 m above every projected item
    assert sec.items(empty) == []                # precondition: the click hits nothing
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: errors.append(a))
    fired = []

    def _exec(menu, *a, **k):                    # QMenu.exec is modal: trigger instead
        for act in menu.actions():
            if act.text() == "Hide" and act.isEnabled():
                fired.append(act.text())
                act.trigger()

    monkeypatch.setattr(QMenu, "exec", _exec)
    vp = view.mapFromScene(empty)
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, vp,
                           view.viewport().mapToGlobal(vp))
    QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()
    assert fired == ["Hide"]
    assert errors == []                          # [RED] AttributeError on None.setVisible
    assert pipe._display_overrides.get("visible") is False


def test_ctrl_a_on_a_section_tab_selects_the_section_items_once(section_win):
    """AC15: the ONE window Ctrl+A selects every selectable section item except
    gridlines / datums (SectionView._select_all_items), in one selection
    change, and leaves the plan selection alone."""
    from PyQt6.QtGui import QKeySequence, QShortcut
    from firepro3d.section_scene import ElevDatumItem, ElevGridlineItem
    win, ms, sec, gl, plan_gl, inst = section_win
    crossing_pipe(ms, sec)
    sec.clearSelection()
    emits = []
    sec.selectionChanged.connect(lambda: emits.append(1))
    press(win, "Ctrl+A")
    expected = {id(i) for i in sec.items()
                if i.isVisible()
                and i.flags() & i.GraphicsItemFlag.ItemIsSelectable
                and not isinstance(i, (ElevGridlineItem, ElevDatumItem))}
    assert expected                                    # the section has items to pick
    assert {id(i) for i in sec.selectedItems()} == expected     # [RED] nothing selected
    assert emits == [1]
    assert ms.selectedItems() == [plan_gl]
    assert len([s for s in win.findChildren(QShortcut)
                if s.key() == QKeySequence("Ctrl+A")]) == 1


def test_halo_readout_reaches_the_footer_on_a_section_tab(section_win):
    """AC6 / D8: hovering a section item shows plan's HALO line in the footer,
    naming the MODEL source (not the projection class); leaving every
    candidate clears it, as plan does."""
    from PyQt6.QtCore import QEvent
    from tests._note_helpers import mouse
    win, ms, sec, gl, plan_gl, inst = section_win
    view = win.central_tabs.currentWidget()
    sec.clearSelection()
    QApplication.processEvents()
    cp = sec._hosted_copies[id(inst)]
    centre = cp.sceneBoundingRect().center()
    nob = Qt.MouseButton.NoButton
    mouse(view, QEvent.Type.MouseMove, centre, buttons=nob, button=nob)
    assert sec._halo_candidates == [cp]          # precondition: one candidate (mixin engine)
    assert win.footer.instruction.text() == f"{type(inst).__name__} — 1 of 1"   # [RED] ''
    far = QPointF(centre.x(), centre.y() - 20000.0)
    mouse(view, QEvent.Type.MouseMove, far, buttons=nob, button=nob)
    assert sec.halo_item() is None               # precondition: nothing under the cursor
    assert win.footer.instruction.text() == ""


def plan_index(win):
    """Index of the window's plan tab."""
    for i in range(win.central_tabs.count()):
        if win.central_tabs.tabText(i).startswith("Plan: "):
            return i
    raise AssertionError("no plan tab")


@pytest.mark.parametrize("seq,tool", [
    ("Shift+M", "move"), ("Shift+C", "copy"), ("Shift+R", "rotate"),
    ("Shift+F", "flip"), ("Shift+S", "scale"), ("Shift+A", "array"),
    ("Ctrl+C", "copy"), ("Ctrl+X", "cut"), ("Ctrl+D", "duplicate")])
def test_modify_shortcut_on_a_section_tab_starts_on_the_section_scene(
        section_win, seq, tool):
    """AC1: with a hosted copy selected in the section, the window key enters
    the tool on the SECTION scene; the hidden plan (holding its own selected
    gridline) never enters it. Esc then ends it on the section."""
    from firepro3d.modify_tools_controller import ModifyToolsController
    win, ms, sec, gl, plan_gl, inst = section_win
    plan_mode0 = ms.mode
    press(win, seq)
    assert sec.mode == ModifyToolsController._TOOL_MODE[tool]   # [RED] plan routed
    assert ms.mode == plan_mode0
    press(win, "Escape")
    assert sec.mode in (None, "select")


def test_esc_on_a_section_tab_clears_the_section_selection_not_the_plan(section_win):
    """D1 fold: Esc on a section tab drops the SECTION selection; the plan's
    selection (a different scene) is untouched."""
    win, ms, sec, gl, plan_gl, inst = section_win
    assert sec.selectedItems() and plan_gl.isSelected()        # fixture state
    press(win, "Escape")
    assert sec.selectedItems() == []                            # [RED]
    assert plan_gl.isSelected()


def test_undo_redo_on_a_section_tab_step_the_shared_stack_and_refresh_the_header(
        section_win):
    """AC11 / R13: Ctrl+Z / Ctrl+Y on a section tab step the ONE plan stack and
    the header's undo / redo buttons follow it."""
    win, ms, sec, gl, plan_gl, inst = section_win
    undo_b, redo_b = win.header.undo_button(), win.header.redo_button()
    depth0 = ms._undo_pos
    press(win, "Delete")                       # R2: one step, the hosted block goes
    assert inst not in ms._block_instances and ms._undo_pos == depth0 + 1
    assert undo_b.isEnabled() and not redo_b.isEnabled()
    press(win, "Ctrl+Z")
    assert ms._undo_pos == depth0                               # [RED]
    (back,) = ms._block_instances
    assert back.host["along_mm"] == pytest.approx(2500.0)      # the fixture's placement x
    assert redo_b.isEnabled()                                   # [RED]
    press(win, "Ctrl+Y")
    assert ms._undo_pos == depth0 + 1 and not ms._block_instances
    assert not redo_b.isEnabled()


def test_f3_on_a_section_tab_toggles_the_section_snap_only(section_win):
    """AC13 / D3: F3 flips the SECTION's snap, never the plan's; the footer
    SNAP pill shows the current tab's scene, also across tab switches."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = win.central_tabs.currentWidget()
    s0, p0 = sec._snap_enabled, ms._snap_enabled
    press(win, "F3")
    assert sec._snap_enabled is (not s0)                       # [RED] plan toggled
    assert ms._snap_enabled is p0
    assert win.footer.snap_pill.isChecked() is sec._snap_enabled
    if sec._snap_enabled is not ms._snap_enabled:               # pills distinguishable
        win.central_tabs.setCurrentIndex(plan_index(win))
        QApplication.processEvents()
        assert win.footer.snap_pill.isChecked() is ms._snap_enabled
        win.central_tabs.setCurrentWidget(view)
        QApplication.processEvents()
        assert win.footer.snap_pill.isChecked() is sec._snap_enabled


def test_plan_draw_button_on_a_section_tab_is_refused(section_win):
    """D1: a routed ribbon draw mode (Gridline) on a section tab is refused with
    the footer reason; neither scene enters it and the button is not lit."""
    win, ms, sec, gl, plan_gl, inst = section_win
    btn = win._mode_buttons["draw_gridline"]
    mode0 = ms.mode
    btn.click()
    QApplication.processEvents()
    assert ms.mode == mode0
    assert getattr(sec, "mode", None) != "draw_gridline"
    assert win.footer.instruction.text() == win._NOT_IN_VIEW_TIP      # [RED]
    assert not btn.isChecked()


def test_leaving_a_section_tab_ends_its_running_tool(section_win):
    """A tool belongs to the tab it started in (as plan placements, main.py
    _on_tab_changed): switching away ends the section's Move."""
    win, ms, sec, gl, plan_gl, inst = section_win
    press(win, "Shift+M")
    assert sec.mode == "move"                                   # precondition (AC1)
    win.central_tabs.setCurrentIndex(plan_index(win))
    QApplication.processEvents()
    assert sec.mode in (None, "select")                         # [RED]


def test_delete_on_a_section_tab_removes_any_selected_source(section_win):
    """AC5 / R2 (integrator PI-15): Delete on a section tab removes a
    READ-ONLY proxy's model source too -- Delete is not restricted, only
    geometry edits are -- in one undo step; the plan's own selection stays."""
    win, ms, sec, gl, plan_gl, inst = section_win
    pipe = parallel_pipe(ms, sec)
    (line,) = proxies_of(sec, pipe)
    sec.clearSelection()
    line.setSelected(True)
    QApplication.processEvents()
    pos0 = ms._undo_pos
    press(win, "Delete")
    assert pipe not in ms.sprinkler_system.pipes                # [RED]
    assert ms._undo_pos == pos0 + 1
    assert plan_gl.scene() is ms and plan_gl.isSelected()


def test_select_on_a_section_shows_plans_select_text(section_win):
    """OPEN-8 (integrator, plan parity): entering Select on a section tab
    (the window's routed mode entry, `_set_active_mode`) puts plan's Select
    instruction on the footer, not the stale tool hint.
    RED when: the ``if mode == "select":`` emit is deleted from
    ``ModifyHostMixin.set_mode`` (the footer keeps "Pick base point")."""
    from firepro3d.modify_host import ModifyHostMixin
    win, ms, sec, gl, plan_gl, inst = section_win
    press(win, "Shift+M")
    assert sec.mode == "move"                                   # precondition (AC1)
    assert win.footer.instruction.text() != ModifyHostMixin._SELECT_INSTRUCTION
    win._set_active_mode("select")
    QApplication.processEvents()
    assert sec.mode == "select"
    assert win.footer.instruction.text() == ModifyHostMixin._SELECT_INSTRUCTION   # [RED]


def _two_readonly_proxies(ms, sec):
    """Two selectable read-only proxies (two parallel pipes, one proxy each)."""
    a = parallel_pipe(ms, sec)
    b = ms.add_pipe(ms.add_node(1000, -1700), ms.add_node(8000, -1700))
    rebuild(sec)
    return proxies_of(sec, a)[0], proxies_of(sec, b)[0]


def test_skip_count_is_current_when_a_tool_restarts_over_a_changed_selection(
        section_win):
    """R3 / AC2 (carry item): a mixed selection, Shift+M through the real
    window key -> "1 items skipped"; the selection then grows to two read-only
    proxies with the tool still running and Shift+R restarts it -> the status
    names 2, not the first tool's 1."""
    from firepro3d.constants import SECTION_EDIT_SKIPPED
    win, ms, sec, gl, plan_gl, inst = section_win
    cp = sec._hosted_copies[id(inst)]
    a, b = _two_readonly_proxies(ms, sec)
    cp = sec._hosted_copies[id(inst)]
    sec.clearSelection()
    cp.setSelected(True)
    a.setSelected(True)
    QApplication.processEvents()
    press(win, "Shift+M")
    assert sec.mode == "move"
    assert win.statusBar().currentMessage() == SECTION_EDIT_SKIPPED.format(n=1)
    b.setSelected(True)                  # selection changes with the tool running
    QApplication.processEvents()
    win.statusBar().clearMessage()
    press(win, "Shift+R")
    assert sec.mode == "rotate"
    assert win.statusBar().currentMessage() == SECTION_EDIT_SKIPPED.format(n=2)


def test_direct_set_mode_over_a_changed_selection_reports_the_current_skip(
        section_win):
    """R3 (carry item): a modify mode entered by a bare ``set_mode`` (no
    controller start) with a stale captured selection still reports the
    CURRENT skipped count.
    RED when: ``SectionScene._capture_modify_selection`` does not refresh
    ``_modify_skipped`` (the ``self.modify_selection()`` line is deleted)."""
    from firepro3d.constants import SECTION_EDIT_SKIPPED
    win, ms, sec, gl, plan_gl, inst = section_win
    a, b = _two_readonly_proxies(ms, sec)
    cp = sec._hosted_copies[id(inst)]
    sec.clearSelection()
    cp.setSelected(True)
    a.setSelected(True)
    QApplication.processEvents()
    press(win, "Shift+M")
    assert sec.mode == "move" and sec._selected_items == [cp]
    b.setSelected(True)
    QApplication.processEvents()
    win.statusBar().clearMessage()
    sec.set_mode("rotate")
    assert win.statusBar().currentMessage() == SECTION_EDIT_SKIPPED.format(n=2)


def test_section_snap_toggle_reaches_the_pill_through_exactly_one_connect(
        section_win, monkeypatch):
    """Carry item (Unit 3 review): ``_on_section_scene_built`` wires the
    section's ``snapToggled`` to the footer pill ONCE. One F3 updates the
    indicator once, and the signal has exactly one receiver.
    RED when: the connect is duplicated (two receivers, two updates)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    assert sec.receivers(sec.snapToggled) == 1
    calls = []
    real = win.footer.snap_pill.setChecked
    monkeypatch.setattr(win.footer.snap_pill, "setChecked",
                        lambda v: (calls.append(v), real(v))[1])
    press(win, "F3")
    assert calls == [sec._snap_enabled]


def test_section_selection_fills_the_properties_panel_with_its_sources(section_win):
    """AC6 / R6: the panel shows the section selection as MODEL sources, each
    once - a pipe crossing the cut (two proxies) is listed once."""
    from tests._note_helpers import click
    win, ms, sec, gl, plan_gl, inst = section_win
    view = win.central_tabs.currentWidget()
    pipe = crossing_pipe(ms, sec)                 # rebuild: the section selection is dropped
    pipe_proxies = proxies_of(sec, pipe)
    assert len(pipe_proxies) == 2                 # precondition (probe at 41a76d1b)
    cp = sec._hosted_copies[id(inst)]             # the rebuilt copy
    click(view, cp.sceneBoundingRect().center())  # real HALO-committed press
    assert win.prop_manager._targets == [inst]    # [RED] the copy / stale panel
    for p in pipe_proxies:
        p.setSelected(True)
    QApplication.processEvents()
    targets = win.prop_manager._targets
    assert len(targets) == 2                      # [RED] 3 without the de-dup
    assert {id(t) for t in targets} == {id(inst), id(pipe)}


def test_section_selection_drives_the_editor_buttons(section_win):
    """AC1 (ribbon) / R2 / R3: Edit is live on a section. A hosted copy
    selected enables Move, Copy and Delete; a read-only proxy alone keeps the
    modify tools off but Delete on."""
    win, ms, sec, gl, plan_gl, inst = section_win
    btns = win._be_modify_buttons
    assert win._canvas_kind == "section"                       # precondition
    QApplication.processEvents()
    on = {label for label, b in btns.items() if b.isEnabled()}
    assert {"Move", "Copy", "Delete"} <= on                    # [RED] all off
    pipe = parallel_pipe(ms, sec)
    (line,) = proxies_of(sec, pipe)
    sec.clearSelection()
    line.setSelected(True)
    QApplication.processEvents()
    on = {label for label, b in btns.items() if b.isEnabled()}
    assert "Delete" in on
    assert not on & {"Move", "Copy", "Cut", "Duplicate", "Rotate", "Array"}   # [RED] PI-14


def test_section_selection_jumps_to_editor_and_clear_restores(section_win):
    """U3 (plan approval 2026-11-10): a user selection on a section canvas
    makes Editor current, as in plan (G14); clearing it restores the tab
    the user was on."""
    win, ms, sec, gl, plan_gl, inst = section_win
    tb = win.ribbon._tab_bar
    sec.clearSelection()
    QApplication.processEvents()
    tb.setCurrentIndex(2)                                      # Sprinkler Systems
    QApplication.processEvents()
    assert tb.currentIndex() == 2                              # precondition
    sec._hosted_copies[id(inst)].setSelected(True)
    QApplication.processEvents()
    assert tb.currentIndex() == win._editor_page_index         # [RED] no jump
    sec.clearSelection()
    QApplication.processEvents()
    assert tb.currentIndex() == 2                              # [RED] stuck on Editor


def test_ribbon_button_over_a_mixed_selection_reports_the_current_skip(section_win):
    """R3 (carry item): the real Edit-group Rotate button over a hosted copy
    plus two read-only proxies enables, starts the tool on the SECTION and
    names the current skipped count (2), after a first tool left a count of 1.
    A regression pin, not a RED guard: three independent paths refresh the
    count (``_refresh_modify_buttons`` calls ``modify_selection()`` on every
    selection change, ``ModifyToolsController.start`` asks the host for it,
    and ``SectionScene``'s capture recounts); the bare ``set_mode`` guard
    above is the one that goes RED."""
    from firepro3d.constants import SECTION_EDIT_SKIPPED
    win, ms, sec, gl, plan_gl, inst = section_win
    a, b = _two_readonly_proxies(ms, sec)
    cp = sec._hosted_copies[id(inst)]
    sec.clearSelection()
    cp.setSelected(True)
    a.setSelected(True)
    QApplication.processEvents()
    press(win, "Shift+M")                                      # first tool: 1 skipped
    assert win.statusBar().currentMessage() == SECTION_EDIT_SKIPPED.format(n=1)
    b.setSelected(True)
    QApplication.processEvents()
    win.statusBar().clearMessage()
    btn = win._be_modify_buttons["Rotate"]
    assert btn.isEnabled()                                     # the editable subset is non-empty
    btn.click()
    QApplication.processEvents()
    assert sec.mode == "rotate"
    assert win.statusBar().currentMessage() == SECTION_EDIT_SKIPPED.format(n=2)
