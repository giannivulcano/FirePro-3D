"""Tests for Task D6: MainWindow._build_preferences_dialog / _open_preferences.

All tests reuse the session-scoped ``qapp`` fixture from tests/conftest.py.
The module-scoped ``_main_window_singleton`` fixture mirrors the pattern from
``test_osnap_ui.py`` to avoid creating a second MainWindow in the same process.
"""

from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow, shared across this module for speed.

    Save/restore SNAP_TOLERANCE_PX: MainWindow.__init__ overwrites the
    module-level constant from QSettings and would leak the value into other
    test modules if not restored.
    """
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_main_window_singleton):
    """Per-test view of the shared MainWindow."""
    yield _main_window_singleton


def test_open_preferences_has_five_tabs(main_window):
    """_build_preferences_dialog() returns a dialog with exactly 5 tabs."""
    dlg = main_window._build_preferences_dialog()
    assert dlg._tabs.count() == 5
    dlg.deleteLater()


EXPECTED_TABS = ["Manage", "View", "Create", "Architecture",
                 "Sprinkler Systems", "Analyze", "Draft"]


def test_base_tabs_roster_and_order(main_window):
    tb = main_window.ribbon._tab_bar
    titles = [tb.tabText(i) for i in range(tb.count())]
    assert titles == EXPECTED_TABS


def test_no_modify_base_tab(main_window):
    tb = main_window.ribbon._tab_bar
    assert "Modify" not in [tb.tabText(i) for i in range(tb.count())]


def test_undo_redo_present_on_manage(main_window):
    assert hasattr(main_window, "_btn_undo") and hasattr(main_window, "_btn_redo")
