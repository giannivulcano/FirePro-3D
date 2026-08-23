"""tests/test_opening_ribbon.py — Architecture-tab Door/Window/Blank ribbon buttons (§7.6).

Verifies that the quick-access buttons on the Architecture tab enter the unified
"opening" placement mode with the correct default Feature id.

MainWindow construction mirrors ``test_dynamic_input_multiview.py``:
import View3D before MainWindow (heavy VTK import), create a module-scoped
singleton, and restore mutated module-globals on teardown.
"""

from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

from firepro3d import snap_engine

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, must precede MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _mw_singleton(qapp):
    """Module-scoped MainWindow shared across tests in this file."""
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
def main_window(_mw_singleton):
    """Per-test wrapper: reset to select mode before and after each test."""
    win = _mw_singleton
    win.scene.set_mode("select")
    yield win
    win.scene.set_mode("select")


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_door_button_enters_opening_mode_with_door_feature(qapp, main_window):
    mw = main_window
    mw._mode_buttons["door"].click()
    assert mw.scene.mode == "opening"
    assert mw.scene._opening_feature_id.startswith("door")


def test_window_button_enters_opening_mode_with_window_feature(qapp, main_window):
    mw = main_window
    mw._mode_buttons["window"].click()
    assert mw.scene.mode == "opening"
    assert mw.scene._opening_feature_id.startswith("window")


def test_blank_button_exists_in_mode_buttons(qapp, main_window):
    mw = main_window
    assert "blank" in mw._mode_buttons


def test_blank_button_enters_opening_mode(qapp, main_window):
    mw = main_window
    assert "blank" in mw._mode_buttons          # new Blank Opening button exists
    mw._mode_buttons["blank"].click()
    assert mw.scene.mode == "opening"
    assert mw.scene._opening_feature_id == "blank_900"
