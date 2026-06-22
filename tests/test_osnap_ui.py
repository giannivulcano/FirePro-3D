"""Integration tests for the OSNAP UX pair (F3 shortcut + status bar
indicator). All tests reuse the session-scoped ``qapp`` fixture from
tests/conftest.py.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog

from firepro3d import snap_engine

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow, shared across this module for speed.

    (Historically, creating multiple MainWindows in one process hung because
    each View3D leaked its VTK GL context; that is now fixed by View3D.cleanup()
    on MainWindow.closeEvent, so a shared singleton is an optimization, not a
    hard requirement.) Save/restore SNAP_TOLERANCE_PX so building MainWindow
    here doesn't leak the QSettings-derived value into other test modules."""
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
    """Per-test view of the shared MainWindow with OSNAP reset to on."""
    win = _main_window_singleton
    win.scene.toggle_osnap(True)
    yield win


def test_ribbon_osnap_button_click_toggles_and_syncs(main_window):
    """The ribbon OSNAP button toggles OSNAP on click, AND stays in sync
    when OSNAP is toggled from elsewhere (pill / F3).

    Regression: previously the button drove the toggle but did not listen
    to osnapToggled, so an external toggle (pill) left it desynced — which
    made the next F3 press a no-op.
    """
    win = main_window
    btn = win._osnap_btn
    assert btn is not None
    assert btn.isCheckable()
    # External toggle keeps the ribbon button in sync (the fix).
    win.scene.toggle_osnap(False)
    assert btn.isChecked() is False
    win.scene.toggle_osnap(True)
    assert btn.isChecked() is True
    # Clicking the button still drives the toggle.
    btn.click()  # checked -> unchecked -> _toggle_osnap(False)
    assert win.scene._osnap_enabled is False
    btn.click()  # unchecked -> checked -> _toggle_osnap(True)
    assert win.scene._osnap_enabled is True


def test_f3_shortcut_toggles_osnap_and_syncs(main_window):
    """F3 is a window-level shortcut (fires from any ribbon tab) that
    toggles OSNAP and keeps the ribbon button + pill in sync."""
    win = main_window
    assert win._f3_shortcut.key() == QKeySequence("F3")
    win.scene.toggle_osnap(True)
    win._f3_shortcut.activated.emit()
    assert win.scene._osnap_enabled is False
    assert win._osnap_btn.isChecked() is False
    assert win.osnap_indicator.property("osnapOn") is False
    win._f3_shortcut.activated.emit()
    assert win.scene._osnap_enabled is True
    assert win._osnap_btn.isChecked() is True
    assert win.osnap_indicator.property("osnapOn") is True


def test_indicator_exists_and_initial_state(main_window):
    label = main_window.osnap_indicator
    assert label is not None
    assert label.text() == "OSNAP"
    assert label.property("osnapOn") is True


def test_indicator_restyles_on_toggle(main_window):
    label = main_window.osnap_indicator
    main_window.scene.toggle_osnap()  # -> False
    assert label.property("osnapOn") is False
    main_window.scene.toggle_osnap()  # -> True
    assert label.property("osnapOn") is True


def test_indicator_click_toggles(main_window):
    label = main_window.osnap_indicator
    assert main_window.scene._osnap_enabled is True
    QTest.mouseClick(label, Qt.MouseButton.LeftButton)
    assert main_window.scene._osnap_enabled is False
    QTest.mouseClick(label, Qt.MouseButton.LeftButton)
    assert main_window.scene._osnap_enabled is True


def test_dialog_cancel_syncs_toolbar(main_window, monkeypatch):
    """Open the Snap Settings dialog, change a type, cancel -> the OSNAP
    toolbar reflects the reverted (pre-dialog) engine state.

    Lives here (not in test_osnap_toolbar.py) so it reuses this module's
    single shared MainWindow — building a second MainWindow in the suite
    leaks a VTK GL context and crashes the later 3D-render tests.
    """
    win = main_window
    eng = win.scene._snap_engine
    eng.snap_endpoint = True
    win.osnap_toolbar.refresh_from_engine()
    assert win.osnap_toolbar._actions["snap_endpoint"].isChecked() is True

    def fake_exec(self):
        # Simulate the dialog's live setattr, then the user cancels.
        eng.snap_endpoint = False
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    win._open_snap_tolerance_dialog()

    # Cancel reverts the engine, and the toolbar must be re-synced.
    assert eng.snap_endpoint is True
    assert win.osnap_toolbar._actions["snap_endpoint"].isChecked() is True


def test_osnap_bar_button_toggles_toolbar(main_window):
    """The Snap-group 'OSNAP Bar' button shows/hides the toolbar, and the
    button stays in sync with the toolbar's visibility."""
    win = main_window
    win._osnap_bar_btn.setChecked(True)
    assert win.osnap_toolbar.isVisible() is True
    assert win._osnap_bar_btn.isChecked() is True
    win._osnap_bar_btn.setChecked(False)
    assert win.osnap_toolbar.isVisible() is False
    assert win._osnap_bar_btn.isChecked() is False
