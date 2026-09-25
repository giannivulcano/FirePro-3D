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

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from firepro3d.geometry_2d import LineItem
from main import MainWindow

EXPECTED = {
    "Shift+C": "copy", "Shift+X": "cut", "Shift+V": "paste", "Shift+D": "duplicate",
    "Shift+M": "move", "Shift+R": "rotate", "Shift+O": "offset", "Shift+A": "array",
    "Ctrl+C": "copy", "Ctrl+X": "cut", "Ctrl+V": "paste", "Ctrl+D": "duplicate",
}


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow (same pattern as test_ribbon_contextual.py)."""
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False
    win.close()
    win.deleteLater()
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
