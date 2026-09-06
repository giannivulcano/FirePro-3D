"""Guards for borderless fullscreen/immersive mode."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow
from firepro3d.preferences_dialog import UIPane, _QSETTINGS_ORG, _QSETTINGS_APP


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


def test_apply_immersive_toggles_window(win):
    win._apply_immersive(True)
    QTest.qWait(50)
    assert win.isFullScreen()
    win._apply_immersive(False)
    QTest.qWait(50)
    assert not win.isFullScreen()


def test_uipane_immersive_persists_and_calls_back(qapp):
    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    saved = s.value("ui/immersive", None)
    try:
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
    finally:
        if saved is None:
            s.remove("ui/immersive")
        else:
            s.setValue("ui/immersive", saved)
        s.sync()
