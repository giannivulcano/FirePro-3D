"""tests/test_wall_ribbon.py — Task 6: single wall ribbon button (no dropdown).

Verifies that the Wall button on the Architecture ribbon:
- Has no attached QMenu (the dropdown was removed).
- Is the only wall-related button (wall_rect alias removed from _mode_buttons).
- When clicked, enters the "wall" scene mode.
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
def _wall_ribbon_window_singleton(qapp):
    """Module-scoped MainWindow shared across this test module."""
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
def win(_wall_ribbon_window_singleton):
    yield _wall_ribbon_window_singleton


def test_wall_button_has_no_dropdown(win):
    """The Wall button must have no QMenu attached after Task 6 collapse."""
    btn = win._mode_buttons["wall"]
    assert btn.menu() is None, "Wall button should have no dropdown menu"


def test_wall_rect_not_in_mode_buttons(win):
    """wall_rect alias must be removed from _mode_buttons after Task 6."""
    assert "wall_rect" not in win._mode_buttons


def test_wall_button_click_enters_wall_mode(win):
    """Clicking the Wall button must call scene.set_mode('wall')."""
    btn = win._mode_buttons["wall"]
    if btn.isCheckable() and btn.isChecked():
        btn.setChecked(False)
    btn.click()
    assert win.scene.mode == "wall"
