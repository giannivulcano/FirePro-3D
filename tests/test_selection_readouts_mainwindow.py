"""Selection dimension readouts — MainWindow seams (selection-mode.md §15):
project units reach open Block Editors; a tab switch ends a readout edit.
Shared MainWindow singleton."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from firepro3d.geometry_2d import LineItem
from firepro3d.scale_manager import DisplayUnit
from main import MainWindow


@pytest.fixture(scope="module")
def win(qapp):
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = MainWindow()
    w.show()
    QTest.qWaitForWindowExposed(w)
    yield w
    w._modified = False
    w.close()
    w.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


@pytest.fixture
def editor(win):
    sm = win.scene.scale_manager
    saved = (sm.display_unit, sm.precision)
    ed = win.block_editor_manager.open_new()
    yield ed
    if ed.editor_scene.readouts.is_editing():
        ed.editor_scene.readouts.cancel_edit()
    if ed in list(win.block_editor_manager._open.values()):
        ed._dirty = False
        win.block_editor_manager.close(ed)
    win.central_tabs.setCurrentIndex(0)          # never leave the singleton on an editor tab
    win.scene.scale_manager.display_unit, win.scene.scale_manager.precision = saved
    win._modified = False


def _units(sc):
    return sc.scale_manager.display_unit, sc.scale_manager.precision


def test_display_unit_reaches_open_editor(win, editor):
    esc = editor.editor_scene
    win._set_display_unit(DisplayUnit.METRIC_M)
    assert esc.scale_manager.display_unit is DisplayUnit.METRIC_M
    assert esc.scale_manager is not win.scene.scale_manager   # copied, not shared
    win._set_display_unit(DisplayUnit.IMPERIAL)
    ln = LineItem(QPointF(-150, 0), QPointF(150, 0))
    esc.addItem(ln)
    ln.setSelected(True)
    text = esc.readouts.layouts(editor.view)[0].layout.text
    assert "'" in text or '"' in text, text


def test_precision_reaches_open_editor(win, editor):
    win._set_precision(1)
    assert editor.editor_scene.scale_manager.precision == 1
    win._set_precision(4)
    assert editor.editor_scene.scale_manager.precision == 4


def test_project_settings_change_reaches_open_editor(win, editor):
    win.scene.scale_manager.display_unit = DisplayUnit.METRIC_M
    win.scene.scale_manager.precision = 2
    win._on_project_settings_changed()
    assert _units(editor.editor_scene) == (DisplayUnit.METRIC_M, 2)


def test_new_editor_is_seeded_from_project(win, editor):
    win.scene.scale_manager.display_unit = DisplayUnit.METRIC_M
    win.scene.scale_manager.precision = 5
    ed2 = win.block_editor_manager.open_new()
    try:
        assert _units(ed2.editor_scene) == (DisplayUnit.METRIC_M, 5)
    finally:
        ed2._dirty = False
        win.block_editor_manager.close(ed2)


def test_tab_switch_cancels_readout_edit(win, editor):
    esc = editor.editor_scene
    win.central_tabs.setCurrentWidget(editor)
    QApplication.processEvents()
    ln = LineItem(QPointF(-150, 0), QPointF(150, 0))
    esc.addItem(ln)
    esc.set_mode("select")
    ln.setSelected(True)
    esc.readouts.begin_edit(editor.view, esc.readouts.layouts(editor.view)[0])
    assert esc.readouts.is_editing()
    win.central_tabs.setCurrentIndex(0)
    assert not esc.readouts.is_editing()


def test_project_load_reseeds_open_editor(win, editor, monkeypatch):
    """load_from_file REPLACES scene.scale_manager; open editors re-seed."""
    from firepro3d.scale_manager import ScaleManager

    class _Stop(Exception):
        pass

    def fake_load(_file):
        sm = ScaleManager()
        sm.display_unit = DisplayUnit.METRIC_M
        sm.precision = 1
        win.scene.scale_manager = sm

    def stop():
        raise _Stop
    real_sm = win.scene.scale_manager
    monkeypatch.setattr(win.scene, "load_from_file", fake_load)
    monkeypatch.setattr(win.level_widget, "populate", stop)
    try:
        with pytest.raises(_Stop):                 # halt right after the load
            win._apply_loaded_file("dummy.fpd")
        assert _units(editor.editor_scene) == (DisplayUnit.METRIC_M, 1)
        assert editor.editor_scene.scale_manager is not win.scene.scale_manager
    finally:
        win.scene.scale_manager = real_sm
