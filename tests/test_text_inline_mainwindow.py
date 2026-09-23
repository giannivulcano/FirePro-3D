"""App-level inline-edit commit triggers (spec § Inline edit: save / autosave /
tab switch / Block Editor / close commit first).  Shared MainWindow singleton."""
from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow
from firepro3d.text_item import TextItem, TextAnnotationData, editing_text_item


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
def editing(win):
    ed = win.block_editor_manager.open_new()
    s = ed.editor_scene
    d = TextAnnotationData(text="Hi", x=0.0, y=0.0, height_mm=40.0, wrap_width_mm=400.0)
    t = TextItem(d)
    s.addItem(t)
    s._texts.append(t)
    t._apply_format()
    s._text_edit_ctl.begin(t)
    t.setPlainText("Changed")
    yield ed, s, t
    if ed in list(win.block_editor_manager._open.values()):
        win.block_editor_manager.close(ed)
    win.central_tabs.setCurrentIndex(0)          # never leave the singleton on an editor tab


def test_commit_text_edits_ends_editor_sessions(win, editing):
    ed, s, t = editing
    win._commit_text_edits()
    assert editing_text_item(s) is None and t.data.text == "Changed"


def test_save_file_commits_first(win, editing, monkeypatch):
    ed, s, t = editing
    monkeypatch.setattr(win.scene, "save_to_file", lambda path: True)
    monkeypatch.setattr(win, "_current_file", "dummy.fpd")
    win.save_file()
    assert editing_text_item(s) is None


def test_tab_change_commits(win, editing):
    ed, s, t = editing
    win.central_tabs.setCurrentIndex(0)
    assert editing_text_item(s) is None


def test_block_editor_commit_block_commits_first(win, editing):
    ed, s, t = editing
    ed.editor_scene.commit_text_edit()            # sanity: shell exists on the editor scene
    s._text_edit_ctl.begin(t)
    win.block_editor_manager.close(ed)
    assert editing_text_item(s) is None


def test_autosave_skips_while_editing(win, editing, monkeypatch):
    """The autosave TIMER must never commit mid-typing — it skips the tick
    entirely while any scene has a live inline edit, and saves normally once
    the edit ends."""
    ed, s, t = editing
    calls = []
    monkeypatch.setattr(win.scene, "save_to_file", lambda path: calls.append(path))
    monkeypatch.setattr(win, "_modified", True)
    win._autosave()
    assert calls == [] and editing_text_item(s) is not None
    win._commit_text_edits()
    win._autosave()
    assert len(calls) == 1
