"""Paper persistence: sheetModified signal, dirty flag, recovery parity.

Scene-level tests exercise PaperScene.sheetModified directly; MainWindow-level
tests cover the _modified flag, crash recovery, and resolver identity.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from firepro3d.paper_space import (
    PaperScene, PaperSpaceWidget, Sheet, TextAnnotationData, ViewResolver,
)
from firepro3d.paper_commands import AddTextAnnotationCommand


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stub_resolver():
    """ViewResolver with all-None managers — safe for sheets with no viewports."""
    return ViewResolver(None, None, None, None)


def _text_scene():
    return PaperScene(Sheet.create_default(), _stub_resolver())


def _spy(scene):
    """Collect sheetModified emissions."""
    hits = []
    scene.sheetModified.connect(lambda: hits.append(1))
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# Scene-level: sheetModified emission rules
# ─────────────────────────────────────────────────────────────────────────────

def test_sheet_modified_on_command_push_undo_redo(qapp):
    scene = _text_scene()
    hits = _spy(scene)
    data = TextAnnotationData(text="N", x=10, y=10)
    scene.undo_stack.push(AddTextAnnotationCommand(scene, data))
    assert len(hits) == 1, "command push must emit sheetModified"
    scene.undo_stack.undo()
    assert len(hits) == 2, "undo must emit sheetModified (dirty rule: undo dirties)"
    scene.undo_stack.redo()
    assert len(hits) == 3, "redo must emit sheetModified"


def test_sheet_modified_suppressed_during_update_from_sheet(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="N", x=10, y=10)
    scene.undo_stack.push(AddTextAnnotationCommand(scene, data))  # non-empty stack
    hits = _spy(scene)
    scene.update_from_sheet(Sheet.create_default())
    # _setup() rebuild + undo_stack.clear() (which fires indexChanged) must not leak
    assert hits == [], "load-path rebuild must not emit sheetModified"


def test_sheet_modified_on_paper_size_change_only(qapp):
    scene = _text_scene()
    hits = _spy(scene)
    same = scene.paper_size
    scene.paper_size = same
    assert hits == [], "no-op paper size set must not emit"
    other = "ANSI B" if same != "ANSI B" else "ANSI D"
    scene.paper_size = other
    assert len(hits) == 1, "real paper size change must emit sheetModified"
    assert scene.paper_size == other


def test_title_dialog_commit_emits_only_on_change(qapp, monkeypatch):
    from firepro3d import paper_space as ps_mod

    widget = PaperSpaceWidget(Sheet.create_default(), _stub_resolver())
    hits = _spy(widget.paper_scene)

    class _FakeDialogNoChange:
        def __init__(self, *a, **k): pass
        def exec(self): return 0  # cancelled — mutates nothing

    monkeypatch.setattr(ps_mod, "TitleBlockDialog", _FakeDialogNoChange)
    widget.edit_title_block()
    assert hits == [], "cancelled/no-change dialog must not emit sheetModified"

    class _FakeDialogChange:
        def __init__(self, *a, **k): pass
        def exec(self):
            widget._sheet.title_block_fields["Project"] = "Changed"
            return 1

    monkeypatch.setattr(ps_mod, "TitleBlockDialog", _FakeDialogChange)
    widget.edit_title_block()
    assert len(hits) == 1, "field change through the dialog must emit sheetModified"


# ─────────────────────────────────────────────────────────────────────────────
# MainWindow-level: dirty flag, recovery, resolver identity
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtTest import QTest

from firepro3d import snap_engine

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _mw(qapp):
    """Module-scoped MainWindow singleton with safe teardown.

    Saves/restores module-level constants MainWindow.__init__ overwrites from
    QSettings (snap tolerance); resets _modified before close so teardown
    never blocks on the unsaved-changes prompt.
    """
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False  # never let teardown hit the unsaved-changes prompt
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _fresh(mw):
    """Reset to a clean default project without tripping the save prompt."""
    mw._modified = False
    mw.new_file()
    assert mw._modified is False


def _add_text(mw, text="note"):
    scene = mw.paper_space_widget.paper_scene
    data = TextAnnotationData(text=text, x=30, y=30)
    scene.undo_stack.push(AddTextAnnotationCommand(scene, data))
    return data


def test_paper_text_op_sets_modified(_mw):
    _fresh(_mw)
    _add_text(_mw)
    assert _mw._modified is True
    assert " *" in _mw.windowTitle()


def test_paper_undo_redo_keep_modified_latched(_mw, tmp_path):
    _fresh(_mw)
    _add_text(_mw)
    _mw._current_file = str(tmp_path / "t.FPD")
    _mw.save_file()
    assert _mw._modified is False, "save clears the flag"
    _mw.paper_space_widget.paper_scene.undo_stack.undo()
    assert _mw._modified is True, "undo after save re-dirties (latch rule)"


def test_paper_size_change_sets_modified(_mw):
    _fresh(_mw)
    current = _mw.paper_space_widget.paper_scene.paper_size
    other = "ANSI B" if current != "ANSI B" else "ANSI D"
    _mw.paper_space_widget.change_paper(other)
    assert _mw._modified is True


def test_text_template_edit_does_not_dirty(_mw):
    _fresh(_mw)
    tpl = _mw.current_text_template
    tpl.set_property("Bold", not tpl.data.bold)
    assert _mw._modified is False, "Add-Text template is QSettings-only, never dirties"


def test_load_and_new_end_clean(_mw, tmp_path):
    _fresh(_mw)
    _add_text(_mw)
    path = str(tmp_path / "clean.FPD")
    _mw._current_file = path
    _mw.save_file()
    _mw._load_project(path)
    assert _mw._modified is False, "open must end clean despite paper rebuild"
    _fresh(_mw)  # new_file
    assert _mw._modified is False


# ─────────────────────────────────────────────────────────────────────────────
# Crash recovery + resolver identity
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtWidgets import QMessageBox

from firepro3d.paper_space import TextAnnotationItem


def _find_scene_text(mw, text):
    scene = mw.paper_space_widget.paper_scene
    return [it for it in scene.items()
            if isinstance(it, TextAnnotationItem) and it.data.text == text]


def test_recovery_restores_paper_and_survives_save(_mw, tmp_path, monkeypatch):
    """The money test: recovered sheet annotations are visible AND survive a save."""
    autosave = tmp_path / "recovery.FPD"
    monkeypatch.setattr(MainWindow, "_autosave_path",
                        staticmethod(lambda: str(autosave)))

    # 1. Author a project with a paper text annotation and autosave it.
    _fresh(_mw)
    _add_text(_mw, "RECOVER-ME")
    _mw._autosave()
    assert autosave.is_file()

    # 2. Simulate the post-crash fresh session.
    _fresh(_mw)
    assert not _find_scene_text(_mw, "RECOVER-ME")

    # 3. Accept recovery.
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    _mw._current_file = None
    _mw._check_recovery()

    # Visible + correctly bound (stale-self._sheet overwrite is the old bug):
    assert _find_scene_text(_mw, "RECOVER-ME"), "recovered annotation must be on the paper scene"
    assert _mw._sheet is _mw.scene._sheets[0]
    assert _mw.paper_space_widget._sheet is _mw._sheet
    assert _mw._modified is True
    assert _mw._current_file is None, "recovery must not adopt the temp path (Save → Save-As)"
    assert not autosave.is_file(), "recovery file cleaned up after handling"

    # 4. Save and reload — the annotation must survive.
    out = str(tmp_path / "saved.FPD")
    _mw._current_file = out
    _mw.save_file()
    _mw._load_project(out)
    assert _find_scene_text(_mw, "RECOVER-ME"), "annotation lost on save-after-recovery"


def test_recovery_declined_unchanged(_mw, tmp_path, monkeypatch):
    autosave = tmp_path / "recovery2.FPD"
    monkeypatch.setattr(MainWindow, "_autosave_path",
                        staticmethod(lambda: str(autosave)))
    _fresh(_mw)
    _add_text(_mw, "DECLINED")
    _mw._autosave()
    _fresh(_mw)
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    _mw._check_recovery()
    assert not _find_scene_text(_mw, "DECLINED")
    assert not autosave.is_file(), "declined recovery still deletes the autosave"
    assert _mw._modified is False


def test_autosave_contains_paper_only_edit(_mw, tmp_path, monkeypatch):
    autosave = tmp_path / "recovery3.FPD"
    monkeypatch.setattr(MainWindow, "_autosave_path",
                        staticmethod(lambda: str(autosave)))
    _fresh(_mw)
    _add_text(_mw, "AUTOSAVED")   # paper-only edit → _modified True (Task 2)
    _mw._autosave()
    assert autosave.is_file(), "paper-only edits must be autosave-eligible"
    import json
    payload = json.loads(autosave.read_text())
    assert any(a.get("text") == "AUTOSAVED"
               for s in payload.get("sheets", []) for a in s.get("annotations", []))


def test_resolver_identity_after_load_paths(_mw, tmp_path, monkeypatch):
    # After open:
    _fresh(_mw)
    path = str(tmp_path / "res.FPD")
    _mw._current_file = path
    _mw.save_file()
    _mw._load_project(path)
    scene = _mw.paper_space_widget.paper_scene
    assert scene._resolver is _mw._view_resolver, "open must rebind the live resolver"
    assert _mw.paper_space_widget._sheet is _mw._sheet, "open must rebind widget._sheet"

    # After recovery:
    autosave = tmp_path / "recovery4.FPD"
    monkeypatch.setattr(MainWindow, "_autosave_path",
                        staticmethod(lambda: str(autosave)))
    _add_text(_mw, "X")
    _mw._autosave()
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    _mw._check_recovery()
    assert scene._resolver is _mw._view_resolver, "recovery must rebind the live resolver"
