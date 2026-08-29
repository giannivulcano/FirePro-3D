"""Tests for the Underlay Manager ribbon wiring (Task 12).

Verifies:
- open_underlay_manager() creates a modeless, non-duplicate singleton
- The ribbon button points at open_underlay_manager

MainWindow fixture follows the same pattern as test_underlay_display.py:
pre-import View3D, save/restore SNAP_TOLERANCE_PX, clear _modified on teardown.
"""
from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

from firepro3d.underlay_manager import UnderlayManagerDialog


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow shared by all tests here (VTK-heavy).

    Mirrors the identical fixture in test_underlay_display.py.
    """
    from firepro3d import snap_engine
    import main as _main_module
    from firepro3d.view_3d import View3D  # must be imported before MainWindow
    _main_module.View3D = View3D
    from main import MainWindow

    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False
    win.close()
    win.deleteLater()
    qapp.processEvents()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def main_window(_main_window_singleton):
    return _main_window_singleton


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_open_underlay_manager_modeless_singleton(main_window):
    """open_underlay_manager() creates a visible, non-modal dialog once."""
    # Remove any existing singleton from a prior call so this test is clean.
    if hasattr(main_window, "_underlay_manager"):
        del main_window._underlay_manager

    main_window.open_underlay_manager()
    dlg1 = main_window._underlay_manager

    assert isinstance(dlg1, UnderlayManagerDialog)
    assert dlg1.isVisible()
    assert dlg1.isModal() is False

    # Second call must not create a second dialog.
    main_window.open_underlay_manager()
    assert main_window._underlay_manager is dlg1


def test_ribbon_button_calls_open_underlay_manager(main_window):
    """The 'Underlay Manager' ribbon button is wired to open_underlay_manager.

    PyQt6 binds the clicked signal directly to the bound method at
    construction time, so monkeypatching the instance afterwards cannot
    intercept the already-connected slot.  Instead we verify two things:
    1.  The ribbon button with text "Underlay Manager" exists.
    2.  Clicking it actually opens an UnderlayManagerDialog (behavioural proof
        that the wiring points at open_underlay_manager, not open_import_dialog).
    """
    # Remove any existing singleton so the click can create a fresh one.
    if hasattr(main_window, "_underlay_manager"):
        del main_window._underlay_manager

    from PyQt6.QtWidgets import QAbstractButton
    btn = None
    for widget in main_window.findChildren(QAbstractButton):
        txt = widget.text().replace("\n", " ").strip()
        if txt == "Underlay Manager":
            btn = widget
            break

    assert btn is not None, "Could not find 'Underlay Manager' ribbon button"

    btn.click()

    # The click must have created (or reshown) an UnderlayManagerDialog.
    assert hasattr(main_window, "_underlay_manager"), (
        "btn.click() did not set main_window._underlay_manager; "
        "button is not wired to open_underlay_manager"
    )
    assert isinstance(main_window._underlay_manager, UnderlayManagerDialog)
