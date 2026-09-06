"""Guards for the View-tab retirement + Fit triggers."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QKeyEvent
from PyQt6.QtWidgets import QToolButton, QApplication
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow


@pytest.fixture(scope="module")
def win(qapp):
    saved = snap_engine.SNAP_TOLERANCE_PX
    w = MainWindow()
    w.show()
    QTest.qWaitForWindowExposed(w)
    yield w
    w.close()
    w.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved


def _ribbon_button_texts(w):
    return {b.text() for b in w.ribbon.findChildren(QToolButton)}


def test_no_view_tab(win):
    tb = win.ribbon._tab_bar
    titles = [tb.tabText(i) for i in range(tb.count())]
    assert "View" not in titles
    assert titles == ["Manage", "Create", "Architecture",
                      "Sprinkler Systems", "Analyze", "Draft"]


def test_deleted_buttons_absent(win):
    texts = _ribbon_button_texts(win)
    for gone in ("Fit to\nScreen", "Properties", "Browser",
                 "Hydraulic\nReport", "Radiation\nReport"):
        assert gone not in texts, f"{gone!r} should be removed"


def test_underlay_display_present(win):
    texts = _ribbon_button_texts(win)
    assert "Underlay\nManager" in texts
    assert "Display\nManager" in texts


def test_home_key_fits(win, monkeypatch):
    v = win.scene.views()[0]
    calls = []
    monkeypatch.setattr(v, "fit_to_screen", lambda: calls.append(1))
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Home,
                   Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(v, ev)
    assert calls == [1]


def test_middle_double_click_fits(win, monkeypatch):
    v = win.scene.views()[0]
    calls = []
    monkeypatch.setattr(v, "fit_to_screen", lambda: calls.append(1))
    pos = v.viewport().rect().center()
    ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, pos.toPointF(),
                     Qt.MouseButton.MiddleButton, Qt.MouseButton.MiddleButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(v.viewport(), ev)
    assert calls == [1]


def test_report_docks_start_hidden(win):
    assert not win.hydro_dock.isVisible()
    assert not win.radiation_dock.isVisible()


def test_generalpane_drops_report_dock_defaults(qapp):
    from firepro3d.preferences_dialog import GeneralPane
    pane = GeneralPane()
    pane.load()
    labels = {cb.text() for cb in pane._dock_checks.values()}
    assert "Radiation Report" not in labels
    assert "Hydraulic Report" not in labels
    assert "Browser" in labels and "Properties" in labels
