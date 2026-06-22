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
    """Module-scoped MainWindow. Creating multiple MainWindow instances
    in the same process hangs (View3D / splash / singleton managers are
    not re-entrant), so we share one across this test module."""
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


def test_ribbon_osnap_button_bound_to_f3(main_window):
    """The ribbon OSNAP button owns the F3 shortcut and toggles state.

    F3 binding lives on the ribbon button (created in init_ribbon via
    `shortcut="F3"`), not on a standalone QShortcut. This test asserts
    the button exists, is checkable, carries the F3 shortcut, and that
    its click path reaches Model_Space.toggle_osnap.
    """
    btn = main_window._osnap_btn
    assert btn is not None
    assert btn.isCheckable()
    assert btn.shortcut() == QKeySequence("F3")
    # Programmatic click drives the same path as F3 / mouse click.
    # Start with both button and scene in the "on" state.
    main_window.scene.toggle_osnap(True)
    btn.setChecked(True)
    btn.click()  # -> unchecked -> _toggle_osnap(False)
    assert main_window.scene._osnap_enabled is False
    btn.click()  # -> checked -> _toggle_osnap(True)
    assert main_window.scene._osnap_enabled is True


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
