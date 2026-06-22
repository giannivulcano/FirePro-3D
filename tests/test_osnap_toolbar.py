"""Unit tests for the OSNAP toolbar (_OsnapToolbar). Tests 1-7 use a
lightweight toolbar built against a fresh SnapEngine + stub MainWindow;
test 8 (dialog sync) uses a real module-scoped MainWindow singleton.

Reuses the session-scoped ``qapp`` fixture from tests/conftest.py.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog

from firepro3d import snap_engine
from firepro3d.snap_engine import SnapEngine

import main as _main_module
from main import _OsnapToolbar

_ALL_ATTRS = [
    "snap_endpoint", "snap_midpoint", "snap_intersection", "snap_center",
    "snap_quadrant", "snap_nearest", "snap_perpendicular", "snap_tangent",
]


class _StubMainWindow:
    """Minimal stand-in: the toolbar only needs .settings and
    ._open_snap_tolerance_dialog from its owning window."""

    def __init__(self, settings):
        self.settings = settings
        self.dialog_opened = False

    def _open_snap_tolerance_dialog(self):
        self.dialog_opened = True


@pytest.fixture
def toolbar(qapp, tmp_path):
    """A fresh _OsnapToolbar wired to an isolated SnapEngine + QSettings."""
    settings = QSettings(str(tmp_path / "settings.ini"),
                         QSettings.Format.IniFormat)
    engine = SnapEngine()
    mw = _StubMainWindow(settings)
    tb = _OsnapToolbar(engine, mw)
    yield tb, engine, mw, settings
    tb.deleteLater()


def test_toggle_updates_engine(toolbar):
    tb, engine, _mw, _settings = toolbar
    assert engine.snap_endpoint is True
    tb._actions["snap_endpoint"].setChecked(False)
    assert engine.snap_endpoint is False
    tb._actions["snap_endpoint"].setChecked(True)
    assert engine.snap_endpoint is True


def test_toggle_persists_to_qsettings(toolbar):
    tb, _engine, _mw, settings = toolbar
    tb._actions["snap_midpoint"].setChecked(False)
    assert settings.value("snap/snap_midpoint", type=bool) is False
    tb._actions["snap_midpoint"].setChecked(True)
    assert settings.value("snap/snap_midpoint", type=bool) is True


def test_f3_off_disables_actions(toolbar):
    tb, _engine, _mw, _settings = toolbar
    tb._on_osnap_toggled(False)
    assert all(not act.isEnabled() for act in tb._actions.values())


def test_f3_on_restores_actions(toolbar):
    tb, _engine, _mw, _settings = toolbar
    # Uncheck one type, then dim and undim — checked state must survive.
    tb._actions["snap_tangent"].setChecked(False)
    tb._on_osnap_toggled(False)
    tb._on_osnap_toggled(True)
    assert all(act.isEnabled() for act in tb._actions.values())
    assert tb._actions["snap_tangent"].isChecked() is False


def test_enable_all(toolbar):
    tb, engine, _mw, _settings = toolbar
    for attr in _ALL_ATTRS:
        setattr(engine, attr, False)
    tb.refresh_from_engine()
    tb._set_all(True)
    assert all(getattr(engine, a) is True for a in _ALL_ATTRS)
    assert all(act.isChecked() for act in tb._actions.values())


def test_disable_all(toolbar):
    tb, engine, _mw, _settings = toolbar
    tb._set_all(False)
    assert all(getattr(engine, a) is False for a in _ALL_ATTRS)
    assert all(not act.isChecked() for act in tb._actions.values())


def test_refresh_from_engine(toolbar):
    tb, engine, _mw, _settings = toolbar
    engine.snap_center = False  # mutate engine directly
    tb.refresh_from_engine()
    assert tb._actions["snap_center"].isChecked() is False
    # refresh must not write back to the engine
    assert engine.snap_center is False


# ── Integration: dialog cancel re-syncs the toolbar ──────────────────────

from firepro3d.view_3d import View3D  # heavy import, required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    """Module-scoped MainWindow (constructing several per process hangs).

    MainWindow.restore_settings() reads QSettings ``snap/tolerance_px`` into
    the module-level ``snap_engine.SNAP_TOLERANCE_PX``; save/restore it so
    this fixture cannot leak that constant into other test modules (matches
    the guard in tests/test_osnap_ui.py)."""
    from PyQt6.QtTest import QTest
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
    win = _main_window_singleton
    win.scene.toggle_osnap(True)
    yield win


def test_dialog_cancel_syncs_toolbar(main_window, monkeypatch):
    """Open the Snap Settings dialog, change a type, cancel -> the
    toolbar reflects the reverted (pre-dialog) engine state."""
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
