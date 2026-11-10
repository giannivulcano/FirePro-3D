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
