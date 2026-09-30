"""Guards for the maximized-window (immersive) mode."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow
from firepro3d.settings.panes import UIPane, _QSETTINGS_ORG, _QSETTINGS_APP


@pytest.fixture(scope="module")
def win(qapp):
    saved = snap_engine.SNAP_TOLERANCE_PX
    w = MainWindow()
    w.show()
    QTest.qWaitForWindowExposed(w)
    yield w
    w.showNormal()
    w.close()
    w.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved


def test_apply_immersive_calls_show_methods(win, monkeypatch):
    # Assert the enabled->showFullScreen / disabled->showNormal wiring (chrome
    # revamp: immersive is now frameless-fullscreen, not maximize).
    # NOTE: we monkeypatch the show* methods rather than driving the real
    # window-state change: fullscreen-ing a real MainWindow triggers a View3D/VTK
    # resize that native-crashes the headless test process (the documented
    # "MainWindow test mode without View3D" crash class). The actual fullscreen
    # behaviour is covered by the mandatory live-smoke checklist.
    calls = []
    monkeypatch.setattr(win, "showFullScreen", lambda: calls.append("fullscreen"))
    monkeypatch.setattr(win, "showNormal", lambda: calls.append("normal"))
    win._apply_immersive(True)
    win._apply_immersive(False)
    assert calls == ["fullscreen", "normal"]


def test_migrate_fullscreen_pref_reads_and_migrates():
    """ui/immersive (the System Settings toggle) wins; the retired ui/fullscreen
    key is read only when ui/immersive is absent; else default True.
    (Rewritten 2026-09-30: user retired "ui/fullscreen wins" — the header
    toggle no longer persists a startup state.)"""
    from firepro3d.main_helpers import migrate_fullscreen_pref
    assert migrate_fullscreen_pref({"ui/immersive": True}.get) is True
    assert migrate_fullscreen_pref({"ui/immersive": False}.get) is False
    assert migrate_fullscreen_pref(
        {"ui/fullscreen": False, "ui/immersive": True}.get) is True
    assert migrate_fullscreen_pref({"ui/fullscreen": False}.get) is False
    assert migrate_fullscreen_pref({}.get) is True


def test_startup_setting_beats_stale_header_toggle_key(qapp):
    """User scenario 2026-09-30: "Maximize window on startup" = on, but the app
    was last closed restored (old header toggle wrote ui/fullscreen=false) →
    the window must still start fullscreen, and the retired key is removed."""
    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)   # conftest-isolated store
    s.setValue("ui/immersive", True)
    s.setValue("ui/fullscreen", False)
    s.sync()
    w = MainWindow()                                # __init__ runs restore_settings
    try:
        assert w._start_fullscreen is True          # what main() applies
        assert not QSettings(_QSETTINGS_ORG, _QSETTINGS_APP).contains("ui/fullscreen")
    finally:
        w.close()
        w.deleteLater()


def test_retire_fullscreen_key_folds_into_setting_when_unset():
    from firepro3d.main_helpers import retire_fullscreen_key
    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    s.remove("ui/immersive")
    s.setValue("ui/fullscreen", False)
    retire_fullscreen_key(s)
    assert s.value("ui/immersive", type=bool) is False
    assert not s.contains("ui/fullscreen")


def test_header_toggle_does_not_persist_startup_state(win, monkeypatch):
    """The header restore dot / double-click is session-only: it must not write
    any startup pref (fullscreen shown via monkeypatch — real fullscreen on a
    headless MainWindow native-crashes, see test above)."""
    monkeypatch.setattr(win, "showFullScreen", lambda: None)
    monkeypatch.setattr(win, "showNormal", lambda: None)
    s = win.settings            # the store the window itself writes (module-
    s.remove("ui/fullscreen")   # scoped fixture → not this test's isolated dir)
    s.setValue("ui/immersive", True)
    win.header.maximizeRequested.emit()             # real header signal path
    assert not s.contains("ui/fullscreen")
    assert s.value("ui/immersive", type=bool) is True


def test_uipane_immersive_persists_and_calls_back(qapp):
    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)   # conftest-isolated store
    s.setValue("ui/immersive", False)
    s.sync()
    calls = []
    pane = UIPane(on_immersive_changed=lambda v: calls.append(v))
    pane.load()
    assert pane._immersive_cb.isChecked() is False
    pane._immersive_cb.setChecked(True)
    pane.apply()
    assert QSettings(_QSETTINGS_ORG, _QSETTINGS_APP).value(
        "ui/immersive", type=bool) is True
    assert calls == [True]


def test_restored_geometry_does_not_carry_fullscreen_state(qapp):
    """A geometry blob saved while fullscreen must not leave the new MainWindow
    in a fullscreen state before main() applies the ui/fullscreen pref — else
    showFullScreen() is a no-op and the window shows small, stuck 'fullscreen'
    (header-drag and edge-resize both gated off)."""
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtWidgets import QMainWindow
    src = QMainWindow()
    src.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
    src.setGeometry(QRect(200, 150, 900, 640))
    src.setWindowState(Qt.WindowState.WindowFullScreen)
    blob = src.saveGeometry()
    src.deleteLater()
    s = QSettings("GV", "FirePro3D")               # conftest-isolated store
    s.setValue("geometry", blob)
    s.sync()

    w = MainWindow()                                # __init__ runs restore_settings
    try:
        assert not w.isFullScreen()
        assert not w.isMaximized()
        probe = QMainWindow()                       # what the blob encodes as normal
        probe.restoreGeometry(blob)
        assert w.normalGeometry() == probe.normalGeometry()
        probe.deleteLater()
    finally:
        w.close()
        w.deleteLater()
