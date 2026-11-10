"""Sheet-linked documents through the real MainWindow load / save / export paths."""
from __future__ import annotations

import os

import fitz
import pytest
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d import linked_doc_service, paper_export, snap_engine
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow  # noqa: E402
from firepro3d.paper_commands import SetLinkedDocumentCommand  # noqa: E402
from tests._mainwindow_helpers import dispose_main_window  # noqa: E402
from tests._linked_doc_helpers import (  # noqa: E402
    build_fixture_pdf, fixture_text, make_link, pdf_bytes, rewrite_by_rename,
    snapshot_text,
)


@pytest.fixture(scope="module")
def _mw(qapp):
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _fresh(mw):
    mw._modified = False
    mw.new_file()
    assert mw._modified is False


def _link(mw, src, page=1):
    scene = mw.paper_space_widget.paper_scene
    scene.undo_stack.push(SetLinkedDocumentCommand(scene, mw._sheet,
                                                   make_link(src, page)))


def _save(mw, path):
    mw._current_file = str(path)
    assert mw.save_file()


def _dirs(mw):
    return {os.path.normcase(d) for d in mw.linked_docs.watcher.watched_dirs()}


def test_on_open_refreshes_a_changed_file_and_dirties(_mw, tmp_path):
    _fresh(_mw)
    src = build_fixture_pdf(tmp_path / "docs" / "spec.pdf", 2)
    _link(_mw, src)
    proj = tmp_path / "p.FPD"
    _save(_mw, proj)
    rewrite_by_rename(src, 2, "BETA-CHANGED")
    _mw._load_project(str(proj))
    ld = _mw.sheet_mgr.sheets[0].linked_document
    assert fixture_text("BETA-CHANGED", 1) in snapshot_text(ld)
    assert _mw._modified is True                  # D5: the new copy gets saved


def test_unchanged_file_opens_clean(_mw, tmp_path):
    _fresh(_mw)
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    _link(_mw, src)
    proj = tmp_path / "p.FPD"
    _save(_mw, proj)
    _mw._load_project(str(proj))
    assert _mw._modified is False


def test_missing_source_shows_the_copy_badge_and_exports(_mw, tmp_path):
    _fresh(_mw)
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    _link(_mw, src)
    proj = tmp_path / "p.FPD"
    _save(_mw, proj)
    os.remove(src)
    _mw._load_project(str(proj))
    sheet = _mw.sheet_mgr.sheets[0]
    assert fixture_text("ALPHA", 1) in snapshot_text(sheet.linked_document)
    badge = _mw.paper_space_widget.paper_scene.linked_badge()
    assert badge.isVisible()
    assert badge.text().startswith("Linked file missing - showing copy from ")
    out = tmp_path / "out.pdf"
    tmpl, info = _mw._current_template()
    paper_export.export_pdf([sheet], _mw._view_resolver, str(out),
                            template=tmpl, project_info=info)
    doc = fitz.open(str(out))
    text = doc[0].get_text()
    doc.close()
    assert fixture_text("ALPHA", 1) in text
    assert "Linked file missing" not in text


def test_load_and_new_rebind_the_folder_watch(_mw, tmp_path):
    _fresh(_mw)
    src = build_fixture_pdf(tmp_path / "docs" / "spec.pdf", 1)
    _link(_mw, src)
    assert _dirs(_mw) == {os.path.normcase(str(src.parent))}   # undo-stack rebind
    proj = tmp_path / "p.FPD"
    _save(_mw, proj)
    _fresh(_mw)
    assert _dirs(_mw) == set()
    _mw._load_project(str(proj))
    assert _dirs(_mw) == {os.path.normcase(str(src.parent))}


def test_window_adapter_links_through_the_service(_mw, tmp_path, monkeypatch):
    _fresh(_mw)
    src = build_fixture_pdf(tmp_path / "spec.pdf", 1)
    monkeypatch.setattr(linked_doc_service, "choose_linked_file",
                        lambda parent=None, start_dir="": str(src))
    props = _mw._sheet_props_adapter(_mw._sheet)
    props.get_properties()["Linked Document"]["callback"]()
    assert _mw._sheet.linked_document is not None
    assert _mw._modified is True


def test_delete_sheet_confirm_names_the_linked_file(_mw, tmp_path, monkeypatch):
    _fresh(_mw)
    _mw._create_sheet()
    src = build_fixture_pdf(tmp_path / "spec.pdf", 1)
    _link(_mw, src)
    seen = []
    monkeypatch.setattr(_main_module, "themed_confirm",
                        lambda parent, title, message, **k: seen.append(message)
                        or False)
    _mw._delete_sheet(_mw._sheet.number)
    assert seen and "spec.pdf" in seen[0]


def test_recovery_open_refreshes_a_changed_file(_mw, tmp_path, monkeypatch):
    """The recovery entry point checks linked files like File > Open does."""
    autosave = tmp_path / "recovery.FPD"
    monkeypatch.setattr(MainWindow, "_autosave_path",
                        staticmethod(lambda: str(autosave)))
    _fresh(_mw)
    src = build_fixture_pdf(tmp_path / "docs" / "spec.pdf", 2)
    _link(_mw, src)
    _mw._autosave()
    assert autosave.is_file()
    rewrite_by_rename(src, 2, "BETA-CHANGED")
    _fresh(_mw)
    monkeypatch.setattr(_main_module, "themed_confirm", lambda *a, **k: True)
    _mw._current_file = None
    _mw._check_recovery()
    ld = _mw.sheet_mgr.sheets[0].linked_document
    assert ld is not None
    assert fixture_text("BETA-CHANGED", 1) in snapshot_text(ld)
    assert _mw._modified is True


@pytest.fixture
def _own_win(qapp):
    """A throwaway window the close tests may really close."""
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)


def _start_blocked_conversion(win, tmp_path):
    """Link a .docx and start a conversion that only worker.cancel() frees."""
    import threading
    import time
    from firepro3d import doc_converter
    from firepro3d.linked_document import new_link
    docx = tmp_path / "spec.docx"
    docx.write_bytes(b"stand-in docx")
    st = os.stat(docx)
    link = new_link(str(docx), pdf_bytes(1, "ALPHA"), 1, st.st_mtime, st.st_size)
    scene = win.paper_space_widget.paper_scene
    scene.undo_stack.push(SetLinkedDocumentCommand(scene, win._sheet, link))
    started, holder = threading.Event(), []

    def stub(_path):
        started.set()
        while not holder:
            time.sleep(0.01)
        if holder[0].cancel_event.wait(15):
            raise doc_converter.ConversionCancelled("cancelled")
        return pdf_bytes(1, "NEVER")

    win.linked_docs._convert_fn = stub
    win.linked_docs._word_available_fn = lambda: True
    win.linked_docs.request_refresh(str(docx))
    assert started.wait(5)
    worker = win.linked_docs.findChildren(doc_converter.ConvertWorker)[0]
    holder.append(worker)
    assert worker.isRunning()
    return worker


@pytest.mark.parametrize("modified", [False, True])
def test_closing_the_window_stops_a_running_conversion(_own_win, tmp_path,
                                                       monkeypatch, modified):
    win = _own_win
    win._modified = False
    worker = _start_blocked_conversion(win, tmp_path)
    win._modified = modified
    monkeypatch.setattr(_main_module, "themed_choice",
                        lambda *a, **k: "discard")
    try:
        win.close()
        assert not worker.isRunning()
    finally:
        worker.cancel()
        worker.wait(3000)


def test_cancelled_close_keeps_the_conversion_running(_own_win, tmp_path,
                                                      monkeypatch):
    win = _own_win
    win._modified = False
    worker = _start_blocked_conversion(win, tmp_path)
    win._modified = True
    monkeypatch.setattr(_main_module, "themed_choice",
                        lambda *a, **k: "cancel")
    try:
        win.close()
        assert worker.isRunning()
    finally:
        worker.cancel()
        worker.wait(3000)
