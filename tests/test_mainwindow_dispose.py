"""Guards for tests/_mainwindow_helpers.dispose_main_window (test-harness.md
Invariant 6 fixture note): close()+deleteLater() alone never deletes a window
at fixture-teardown loop level; the helper must actually destroy it."""
from __future__ import annotations

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication

from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window


@pytest.fixture
def win(qapp, stub_view3d):
    w = MainWindow()
    w.show()
    QApplication.processEvents()
    yield w
    dispose_main_window(w)          # idempotent: a no-op once disposed


def test_close_plus_deletelater_alone_leaves_the_window_alive(qapp, stub_view3d):
    """Premise check (P4): the pattern the helper replaces does NOT delete."""
    w = MainWindow()
    w._modified = False
    w.close()
    w.deleteLater()
    QApplication.processEvents()
    assert not sip.isdeleted(w)
    dispose_main_window(w)
    assert sip.isdeleted(w)


def test_dispose_destroys_the_window(win):
    dispose_main_window(win)
    assert sip.isdeleted(win)


def test_dispose_clears_a_live_plan_selection_first(win):
    """A plan item still selected at close kills the process (filed bug);
    the helper clears it before close, so disposal survives."""
    from firepro3d.node import Node
    node = Node(0.0, 0.0)
    win.scene.addItem(node)
    node.setSelected(True)
    assert len(win.scene.selectedItems()) == 1
    # Spy on close() (a Python-level call), never a selectionChanged slot: a
    # slot reading the scene during destruction is the Invariant 6 hazard.
    at_close = []
    orig_close = win.close

    def _spy():
        at_close.append(len(win.scene.selectedItems()))
        return orig_close()

    win.close = _spy
    dispose_main_window(win)
    assert sip.isdeleted(win)
    assert at_close == [0]           # selection cleared before close()


def test_dispose_skips_the_save_prompt(win, monkeypatch):
    import main
    asked = []
    monkeypatch.setattr(main, "themed_choice",
                        lambda *a, **k: asked.append(a) or "cancel")
    win._modified = True
    dispose_main_window(win)
    assert asked == []
    assert sip.isdeleted(win)


def test_dispose_is_idempotent(win):
    dispose_main_window(win)
    dispose_main_window(win)        # must not raise on a deleted wrapper
    dispose_main_window(None)
