"""Integration tests for the SNAP/ALIGN UX (F3/F11 shortcuts + footer rail).

Post chrome-revamp: the SNAP/ALIGN state surfaces on the footer pills
(``win.footer.snap_pill`` / ``win.footer.align_pill``) and the per-type osnap
bar lives inline in the footer with a ``−``/``+`` collapse chevron. All tests
reuse the session-scoped ``qapp`` fixture from tests/conftest.py.
"""

from __future__ import annotations

import pytest
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from firepro3d import snap_engine

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow, shared across this module for speed.

    Save/restore SNAP_TOLERANCE_PX/HYSTERESIS_PX so building MainWindow here
    doesn't leak the QSettings-derived value into other test modules
    (module-scoped, so the function-scoped conftest guard can't cover it)."""
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
    """Per-test view of the shared MainWindow with SNAP + ALIGN reset to on."""
    win = _main_window_singleton
    win.scene.toggle_snap(True)
    win.scene.set_align_enabled(True)
    yield win


# ── SNAP pill + F3 ────────────────────────────────────────────────────────


def test_snap_pill_click_toggles_and_syncs(main_window):
    """The footer SNAP pill toggles SNAP on click, AND stays in sync when SNAP
    is toggled from elsewhere (F3 / editor scene)."""
    win = main_window
    pill = win.footer.snap_pill
    assert pill.isCheckable()
    # External toggle keeps the footer pill in sync.
    win.scene.toggle_snap(False)
    assert pill.isChecked() is False
    win.scene.toggle_snap(True)
    assert pill.isChecked() is True
    # Clicking the pill drives the toggle.
    pill.click()   # checked -> unchecked -> toggle_snap()
    assert win.scene._snap_enabled is False
    pill.click()   # unchecked -> checked -> toggle_snap()
    assert win.scene._snap_enabled is True


def test_f3_shortcut_toggles_snap_and_syncs(main_window):
    """F3 is a window-level shortcut (fires from any ribbon tab) that toggles
    SNAP and keeps the footer pill in sync."""
    win = main_window
    assert win._f3_shortcut.key() == QKeySequence("F3")
    win.scene.toggle_snap(True)
    win._f3_shortcut.activated.emit()
    assert win.scene._snap_enabled is False
    assert win.footer.snap_pill.isChecked() is False
    win._f3_shortcut.activated.emit()
    assert win.scene._snap_enabled is True
    assert win.footer.snap_pill.isChecked() is True


def test_snap_pill_initial_state(main_window):
    pill = main_window.footer.snap_pill
    assert pill.text() == "SNAP"
    main_window.scene.toggle_snap(True)
    assert pill.isChecked() is True


def test_snap_off_dims_osnap_bar(main_window):
    """Master SNAP off dims (disables) the inline osnap bar; on re-enables it."""
    win = main_window
    win.scene.toggle_snap(False)
    assert win.footer.osnap_bar.isEnabled() is False
    win.scene.toggle_snap(True)
    assert win.footer.osnap_bar.isEnabled() is True


def test_osnap_chevron_collapses_and_expands(main_window):
    """The footer −/+ chevron collapses/expands the inline osnap bar."""
    win = main_window
    footer = win.footer
    if not footer._expanded:
        footer.chevron.click()
    assert footer.osnap_bar.isVisibleTo(footer) is True
    footer.chevron.click()
    assert footer._expanded is False
    assert footer.osnap_bar.isVisibleTo(footer) is False
    footer.chevron.click()
    assert footer._expanded is True
    assert footer.osnap_bar.isVisibleTo(footer) is True


# ── ALIGN pill + F11 ──────────────────────────────────────────────────────


def test_align_pill_initial_state(main_window):
    pill = main_window.footer.align_pill
    assert pill.text() == "ALIGN"
    main_window.scene.set_align_enabled(True)
    assert pill.isChecked() is True


def test_align_pill_restyles_on_toggle(main_window):
    pill = main_window.footer.align_pill
    main_window.scene.set_align_enabled(True)
    assert pill.isChecked() is True
    main_window.scene.set_align_enabled(False)
    assert pill.isChecked() is False
    main_window.scene.set_align_enabled(True)
    assert pill.isChecked() is True


def test_f11_shortcut_toggles_guides(main_window):
    """F11 is a window-level shortcut that toggles ALIGN and syncs the pill."""
    win = main_window
    assert win._f11_shortcut.key() == QKeySequence("F11")
    win.scene.set_align_enabled(True)
    win._f11_shortcut.activated.emit()
    assert win.scene._align_enabled is False
    assert win.footer.align_pill.isChecked() is False
    win._f11_shortcut.activated.emit()
    assert win.scene._align_enabled is True
    assert win.footer.align_pill.isChecked() is True
