"""Integration tests for the SNAP UX pair (F3 shortcut + status bar
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
    here doesn't leak the QSettings-derived value into other test modules.
    (Module-scoped, so the function-scoped conftest guard can't cover it.)"""
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    saved_hyst = snap_engine.SNAP_HYSTERESIS_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol
    snap_engine.SNAP_HYSTERESIS_PX = saved_hyst


@pytest.fixture
def main_window(_main_window_singleton):
    """Per-test view of the shared MainWindow with SNAP + inference reset to on."""
    win = _main_window_singleton
    win.scene.toggle_snap(True)
    win.scene.set_align_enabled(True)
    yield win


def test_ribbon_snap_button_click_toggles_and_syncs(main_window):
    """The ribbon SNAP button toggles SNAP on click, AND stays in sync
    when SNAP is toggled from elsewhere (pill / F3).

    Regression: previously the button drove the toggle but did not listen
    to snapToggled, so an external toggle (pill) left it desynced — which
    made the next F3 press a no-op.
    """
    win = main_window
    btn = win._snap_btn
    assert btn is not None
    assert btn.isCheckable()
    # External toggle keeps the ribbon button in sync (the fix).
    win.scene.toggle_snap(False)
    assert btn.isChecked() is False
    win.scene.toggle_snap(True)
    assert btn.isChecked() is True
    # Clicking the button still drives the toggle.
    btn.click()  # checked -> unchecked -> _toggle_snap(False)
    assert win.scene._snap_enabled is False
    btn.click()  # unchecked -> checked -> _toggle_snap(True)
    assert win.scene._snap_enabled is True


def test_f3_shortcut_toggles_snap_and_syncs(main_window):
    """F3 is a window-level shortcut (fires from any ribbon tab) that
    toggles SNAP and keeps the ribbon button + pill in sync."""
    win = main_window
    assert win._f3_shortcut.key() == QKeySequence("F3")
    win.scene.toggle_snap(True)
    win._f3_shortcut.activated.emit()
    assert win.scene._snap_enabled is False
    assert win._snap_btn.isChecked() is False
    assert win.snap_indicator.property("snapOn") is False
    win._f3_shortcut.activated.emit()
    assert win.scene._snap_enabled is True
    assert win._snap_btn.isChecked() is True
    assert win.snap_indicator.property("snapOn") is True


def test_indicator_exists_and_initial_state(main_window):
    label = main_window.snap_indicator
    assert label is not None
    assert label.text() == "SNAP"
    assert label.property("snapOn") is True


def test_indicator_restyles_on_toggle(main_window):
    label = main_window.snap_indicator
    main_window.scene.toggle_snap()  # -> False
    assert label.property("snapOn") is False
    main_window.scene.toggle_snap()  # -> True
    assert label.property("snapOn") is True


def test_indicator_click_toggles(main_window):
    label = main_window.snap_indicator
    assert main_window.scene._snap_enabled is True
    QTest.mouseClick(label, Qt.MouseButton.LeftButton)
    assert main_window.scene._snap_enabled is False
    QTest.mouseClick(label, Qt.MouseButton.LeftButton)
    assert main_window.scene._snap_enabled is True


def test_dialog_cancel_syncs_toolbar(main_window, monkeypatch):
    """Open the Snap Settings dialog, change a type, cancel -> the SNAP
    toolbar reflects the reverted (pre-dialog) engine state.

    Lives here (not in test_osnap_toolbar.py) so it reuses this module's
    single shared MainWindow — building a second MainWindow in the suite
    leaks a VTK GL context and crashes the later 3D-render tests.
    """
    win = main_window
    eng = win.scene._snap_engine
    eng.snap_endpoint = True
    win.snap_toolbar.refresh_from_engine()
    assert win.snap_toolbar._actions["snap_endpoint"].isChecked() is True

    def fake_exec(self):
        # Simulate the dialog's live setattr, then the user cancels.
        eng.snap_endpoint = False
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    win._open_snap_tolerance_dialog()

    # Cancel reverts the engine, and the toolbar must be re-synced.
    assert eng.snap_endpoint is True
    assert win.snap_toolbar._actions["snap_endpoint"].isChecked() is True


def test_snap_bar_button_toggles_toolbar(main_window):
    """The Snap-group 'SNAP Bar' button shows/hides the toolbar, and the
    button stays in sync with the toolbar's visibility."""
    win = main_window
    win._snap_bar_btn.setChecked(True)
    assert win.snap_toolbar.isVisible() is True
    assert win._snap_bar_btn.isChecked() is True
    win._snap_bar_btn.setChecked(False)
    assert win.snap_toolbar.isVisible() is False
    assert win._snap_bar_btn.isChecked() is False


# ── Inference / Alignment Guides toggle tests ─────────────────────────────


def test_align_checkbox_drives_flag(main_window):
    """The Inference tab checkbox in Snap Settings drives _align_enabled.

    Uses modal=False test seam to build the dialog without exec().
    Drives the checkbox with .click() (not by calling slots directly).
    """
    from PyQt6.QtWidgets import QCheckBox
    mw = main_window
    mw.scene.set_align_enabled(True)
    dlg = mw._open_snap_tolerance_dialog(modal=False)
    cb = dlg.findChild(QCheckBox, "align_enabled")
    assert cb is not None and cb.isChecked() is True
    cb.click()
    assert mw.scene._align_enabled is False


def test_guides_indicator_exists_and_initial_state(main_window):
    """ALIGN status-bar pill is present and reflects initial state."""
    label = main_window.guides_indicator
    assert label is not None
    assert label.text() == "ALIGN"
    # Ensure state is known for the assertion.
    main_window.scene.set_align_enabled(True)
    assert label.property("guidesOn") is True


def test_guides_indicator_restyles_on_toggle(main_window):
    """alignToggled signal restyles the GUIDES pill."""
    label = main_window.guides_indicator
    main_window.scene.set_align_enabled(True)
    assert label.property("guidesOn") is True
    main_window.scene.set_align_enabled(False)
    assert label.property("guidesOn") is False
    main_window.scene.set_align_enabled(True)
    assert label.property("guidesOn") is True


def test_f11_shortcut_toggles_guides(main_window):
    """F11 is a window-level shortcut that toggles ALIGN and syncs the pill."""
    win = main_window
    assert win._f11_shortcut.key() == QKeySequence("F11")
    win.scene.set_align_enabled(True)
    win._f11_shortcut.activated.emit()
    assert win.scene._align_enabled is False
    assert win.guides_indicator.property("guidesOn") is False
    win._f11_shortcut.activated.emit()
    assert win.scene._align_enabled is True
    assert win.guides_indicator.property("guidesOn") is True
