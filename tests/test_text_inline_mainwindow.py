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


def test_block_editor_manager_close_commits_first(win, editing):
    """Renamed from test_block_editor_commit_block_commits_first — this drives
    BlockEditorManager.close(), not commit_block(); see
    test_commit_block_commits_first / test_save_commits_first below for the
    widget-level methods."""
    ed, s, t = editing
    ed.editor_scene.commit_text_edit()            # sanity: shell exists on the editor scene
    s._text_edit_ctl.begin(t)
    win.block_editor_manager.close(ed)
    assert editing_text_item(s) is None


def test_commit_block_commits_first(win, editing, monkeypatch):
    """BlockEditorWidget.commit_block() must commit the live inline edit before
    doing anything else (it reads gather_primitives()/to_dict() right after)."""
    ed, s, t = editing
    monkeypatch.setattr(ed._project_scene, "commit_block_definition",
                        lambda *a, **k: None)
    ed.commit_block("Name", "Lib", "Series")
    assert editing_text_item(s) is None and t.data.text == "Changed"


def test_save_commits_first(win, editing, monkeypatch):
    """BlockEditorWidget.save() must commit the live inline edit before it
    even checks gather_primitives() for the empty-editor guard. Both modal
    exits are stubbed so the test never blocks on a real dialog: the "no
    geometry" early-return (themed_info) and — since block polish made text a
    block primitive, so a text-only editor is no longer empty — the unsaved
    block's Save dialog (``_save_via_dialog``)."""
    from firepro3d import themed_message as _tm
    ed, s, t = editing
    monkeypatch.setattr(_tm, "themed_info", lambda *a, **k: None)
    monkeypatch.setattr(ed, "_save_via_dialog", lambda *a, **k: None)
    ed.save()
    assert editing_text_item(s) is None and t.data.text == "Changed"


def test_tab_close_commits_before_discard_prompt(win, editing, monkeypatch):
    """I1: the REAL tab-X close path (_on_tab_close_requested) must commit the
    live inline edit BEFORE the is_dirty() discard-prompt check — otherwise
    is_dirty() (blind to live typing, only set by sceneModified) sees a clean
    editor, skips the prompt, and BlockEditorManager.forget() drops the tab
    with the typed text never written to _data.text."""
    ed, s, t = editing
    idx = win.central_tabs.indexOf(ed)
    seen = []

    def fake_confirm(*args, **kwargs):
        seen.append((editing_text_item(s), t.data.text))
        return True   # "Discard" -> proceed with the close

    monkeypatch.setattr("firepro3d.themed_message.themed_confirm", fake_confirm)
    win._on_tab_close_requested(idx)
    assert seen == [(None, "Changed")], \
        "text must be committed BEFORE the discard prompt runs"
    assert win.central_tabs.indexOf(ed) == -1
    assert ed not in list(win.block_editor_manager.open_editors())


def test_new_file_commits_before_ask_save_changes(win, editing, monkeypatch):
    """I2: new_file() must commit the live inline edit BEFORE
    _ask_save_changes — otherwise _modified may still be False (live typing
    alone never marks the scene dirty) and the prompt never sees the change."""
    ed, s, t = editing
    seen = []

    def fake_ask(*args, **kwargs):
        seen.append((editing_text_item(s), t.data.text, win._modified))
        return False   # cancel -> new_file stops before mutating anything else

    monkeypatch.setattr(win, "_ask_save_changes", fake_ask)
    win.new_file()
    assert seen and seen[0][:2] == (None, "Changed")


def test_open_file_commits_before_dialog(win, editing, monkeypatch):
    """I2: open_file() must commit the live inline edit before the (modal)
    file dialog even opens."""
    ed, s, t = editing
    from PyQt6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    win.open_file()
    assert editing_text_item(s) is None and t.data.text == "Changed"


def test_open_recent_commits_before_load(win, editing, monkeypatch):
    """I2: _open_recent() must commit before _load_project runs."""
    ed, s, t = editing
    import os
    monkeypatch.setattr(os.path, "isfile", lambda p: False)   # short-circuit; no real load
    monkeypatch.setattr(_main_module, "themed_warn", lambda *a, **k: None)
    win._open_recent("nonexistent.fpd")
    assert editing_text_item(s) is None and t.data.text == "Changed"


def test_load_project_commits_first(win, editing, monkeypatch):
    """I2: _load_project() itself must also commit first (belt-and-suspenders
    with open_file/_open_recent, and the sole guard for any other caller)."""
    ed, s, t = editing
    monkeypatch.setattr(win, "_apply_loaded_file", lambda file: None)
    monkeypatch.setattr(win, "_add_recent_file", lambda path: None)
    monkeypatch.setattr(win, "_maybe_offer_template_push", lambda: None)
    win._load_project("dummy.fpd")
    assert editing_text_item(s) is None and t.data.text == "Changed"


def test_text_edit_scenes_survives_pre_init(win):
    """M7: _text_edit_scenes() must not AttributeError if called before
    block_editor_manager exists (e.g. a currentChanged signal firing during
    MainWindow.__init__, between the tab-widget setup and the manager's
    construction)."""
    real = win.block_editor_manager
    try:
        del win.block_editor_manager
        assert win._text_edit_scenes() == [win.scene]
    finally:
        win.block_editor_manager = real


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
