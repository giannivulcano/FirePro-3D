"""LinkedDocService: refresh, conversion queue, page gone, growth, link flow."""
from __future__ import annotations

import os
import threading
import time

import pytest
from PyQt6.QtCore import QTimer

from firepro3d import doc_converter, linked_doc_service
from firepro3d.linked_document import new_link
from firepro3d.paper_space import PaperScene, Sheet, SheetManager, ViewResolver
from tests._linked_doc_helpers import (
    build_fixture_pdf, fixture_text, make_link, pdf_bytes, pump_until,
    rewrite_by_rename, snapshot_text,
)


@pytest.fixture
def made():
    """Collects services so every test shuts its workers down."""
    services = []
    yield services
    for svc in services:
        svc.shutdown()


def _service(made, links, **kw):
    sheets = []
    for i, link in enumerate(links, start=1):
        s = Sheet.create_default()
        s.number = f"FP-{i}.0"
        s.linked_document = link
        sheets.append(s)
    mgr = SheetManager(sheets)
    scene = PaperScene(mgr.sheets[0], ViewResolver(None, None, None, None))
    msgs = []
    svc = linked_doc_service.LinkedDocService(
        sheets_getter=lambda: mgr.sheets, scene_getter=lambda: scene,
        manager_getter=lambda: mgr,
        notify=lambda message, timeout_ms=6000: msgs.append(message), **kw)
    made.append(svc)
    return svc, scene, mgr, msgs


def _docx_link(tmp_path, page, n_pages=2):
    docx = tmp_path / "spec.docx"
    if not docx.exists():
        docx.write_bytes(b"stand-in docx")
    st = os.stat(docx)
    return new_link(str(docx), pdf_bytes(n_pages, "ALPHA"), page,
                    st.st_mtime, st.st_size)


def test_watch_refreshes_without_an_undo_step(qapp, tmp_path, made):
    src = build_fixture_pdf(tmp_path / "docs" / "spec.pdf", 2)
    svc, scene, mgr, msgs = _service(made, [make_link(src, 1)])
    svc.rebind()
    mods = []
    scene.sheetModified.connect(lambda: mods.append(1))
    before = (scene.undo_stack.index(), scene.undo_stack.count())
    rewrite_by_rename(src, 2, "BETA-CHANGED")
    assert pump_until(lambda: fixture_text("BETA-CHANGED", 1) in snapshot_text(
        mgr.sheets[0].linked_document), 6)
    assert mods
    assert (scene.undo_stack.index(), scene.undo_stack.count()) == before
    assert "Updated spec.pdf on 1 sheet(s)" in msgs


def test_docx_converts_once_for_every_sheet_linking_it(qapp, tmp_path, made):
    calls = []

    def conv(path):
        calls.append(path)
        return pdf_bytes(2, "BETA")

    svc, scene, mgr, msgs = _service(
        made, [_docx_link(tmp_path, 1), _docx_link(tmp_path, 2)],
        convert_fn=conv, word_available_fn=lambda: True)
    svc.request_refresh(str(tmp_path / "spec.docx"))
    assert pump_until(lambda: all(
        fixture_text("BETA", s.linked_document.page) in snapshot_text(s.linked_document)
        for s in mgr.sheets), 5)
    assert len(calls) == 1
    assert "Updated spec.docx on 2 sheet(s)" in msgs


def test_one_conversion_per_file_with_one_queued_follow_up(qapp, tmp_path, made):
    calls, gate = [], threading.Event()

    def conv(path):
        calls.append(path)
        gate.wait(10)
        return pdf_bytes(2, f"Q{len(calls)}")

    svc, scene, mgr, msgs = _service(made, [_docx_link(tmp_path, 1)],
                                     convert_fn=conv,
                                     word_available_fn=lambda: True)
    docx = str(tmp_path / "spec.docx")
    for _ in range(3):
        svc.request_refresh(docx)
    assert pump_until(lambda: len(calls) == 1, 3)
    assert svc.converting(docx)
    gate.set()
    assert pump_until(lambda: len(calls) == 2 and not svc.converting(docx), 10)
    pump_until(lambda: False, 0.5)
    assert len(calls) == 2
    assert fixture_text("Q2", 1) in snapshot_text(mgr.sheets[0].linked_document)


def test_app_stays_usable_during_a_conversion(qapp, tmp_path, made):
    started, release = threading.Event(), threading.Event()

    def slow(path):
        started.set()
        release.wait(10)
        return pdf_bytes(2, "BETA")

    svc, scene, mgr, msgs = _service(made, [_docx_link(tmp_path, 1)],
                                     convert_fn=slow,
                                     word_available_fn=lambda: True)
    t0 = time.monotonic()
    svc.request_refresh(str(tmp_path / "spec.docx"))
    assert time.monotonic() - t0 < 0.5             # returned at once
    ticks = []
    QTimer.singleShot(50, lambda: ticks.append(1))
    assert pump_until(lambda: ticks and started.is_set(), 3)   # loop alive
    assert fixture_text("BETA", 1) not in snapshot_text(mgr.sheets[0].linked_document)
    assert any(m.startswith("Updating spec.docx") for m in msgs)
    release.set()
    assert pump_until(lambda: fixture_text("BETA", 1) in snapshot_text(
        mgr.sheets[0].linked_document), 5)


def test_page_gone_keeps_the_copy_and_names_the_page(qapp, tmp_path, made):
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    svc, scene, mgr, msgs = _service(made, [make_link(src, 2)])
    saved = mgr.sheets[0].linked_document.snapshot_pdf
    rewrite_by_rename(src, 1, "BETA")
    svc.request_refresh(str(src))
    ld = mgr.sheets[0].linked_document
    assert ld.snapshot_pdf == saved and ld.source_pages == 1
    assert scene.linked_badge().text() == "Page 2 is no longer in spec.pdf"
    assert any("page 2 is no longer in the file" in m for m in msgs)


def test_growth_prompts_once_and_creates_sheets(qapp, tmp_path, made, monkeypatch):
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    asks = []
    monkeypatch.setattr(linked_doc_service, "ask_create_pages",
                        lambda name, n, on, missing: asks.append(
                            (name, n, on, list(missing))) or True)
    svc, scene, mgr, msgs = _service(made, [make_link(src, 1)])
    probe = SheetManager([Sheet.create_default()])  # suggest_number's sequence
    expected_numbers = [probe.create().number, probe.create().number]
    rewrite_by_rename(src, 3, "ALPHA")
    svc.request_refresh(str(src))
    assert asks == [("spec.pdf", 3, 1, [2, 3])]
    assert [s.linked_document.page for s in mgr.sheets] == [1, 2, 3]
    assert [s.number for s in mgr.sheets[1:]] == expected_numbers
    assert all(s.linked_document.offered_pages == 3 for s in mgr.sheets)
    assert fixture_text("ALPHA", 3) in snapshot_text(mgr.sheets[2].linked_document)
    svc.request_refresh(str(src))
    assert len(asks) == 1


def test_growth_declined_records_the_offer(qapp, tmp_path, made, monkeypatch):
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    asks = []
    monkeypatch.setattr(linked_doc_service, "ask_create_pages",
                        lambda *a: asks.append(a) and False)
    svc, scene, mgr, msgs = _service(made, [make_link(src, 1)])
    rewrite_by_rename(src, 3, "ALPHA")
    svc.request_refresh(str(src))
    svc.request_refresh(str(src))
    assert len(asks) == 1 and len(mgr.sheets) == 1
    assert mgr.sheets[0].linked_document.offered_pages == 3


def test_conversion_error_keeps_the_copy_and_reports(qapp, tmp_path, made,
                                                      monkeypatch):
    # The scene's badge asks doc_converter directly; pin Word as present so
    # the error line (not "Word not available") is the top-priority badge.
    monkeypatch.setattr(doc_converter, "word_available", lambda: True)

    def boom(_path):
        raise doc_converter.ConversionError("Word did not finish in 120 s")

    svc, scene, mgr, msgs = _service(made, [_docx_link(tmp_path, 1)],
                                     convert_fn=boom,
                                     word_available_fn=lambda: True)
    saved = mgr.sheets[0].linked_document.snapshot_pdf
    svc.request_refresh(str(tmp_path / "spec.docx"))
    want = "Could not update from spec.docx: Word did not finish in 120 s"
    assert pump_until(lambda: want in msgs, 5)
    assert mgr.sheets[0].linked_document.snapshot_pdf == saved
    assert scene.linked_badge().text() == want


def test_word_unavailable_keeps_the_copy(qapp, tmp_path, made):
    calls = []
    svc, scene, mgr, msgs = _service(made, [_docx_link(tmp_path, 1)],
                                     convert_fn=lambda p: calls.append(p),
                                     word_available_fn=lambda: False)
    svc.request_refresh(str(tmp_path / "spec.docx"))
    pump_until(lambda: False, 0.3)
    assert calls == []
    assert "Word not available - cannot update spec.docx" in msgs


def test_on_open_check_refreshes_only_changed_files(qapp, tmp_path, made):
    a = build_fixture_pdf(tmp_path / "a.pdf", 1)
    b = build_fixture_pdf(tmp_path / "b.pdf", 1)
    svc, scene, mgr, msgs = _service(made, [make_link(a, 1), make_link(b, 1)])
    rewrite_by_rename(b, 1, "BETA-CHANGED")
    mods = []
    scene.sheetModified.connect(lambda: mods.append(1))
    svc.check_all_on_open()
    assert fixture_text("BETA-CHANGED", 1) in snapshot_text(mgr.sheets[1].linked_document)
    assert msgs == ["Updated b.pdf on 1 sheet(s)"] and mods


def test_docx_link_flow_converts_then_pushes_one_command(qapp, tmp_path, made,
                                                         monkeypatch):
    docx = tmp_path / "spec.docx"
    docx.write_bytes(b"stand-in docx")
    monkeypatch.setattr(linked_doc_service, "choose_linked_file",
                        lambda parent=None, start_dir="": str(docx))
    monkeypatch.setattr(linked_doc_service, "pick_linked_page",
                        lambda parent, name, n: (2, False))
    svc, scene, mgr, msgs = _service(made, [None],
                                     convert_fn=lambda p: pdf_bytes(2, "WORD"),
                                     word_available_fn=lambda: True)
    sheet = mgr.sheets[0]
    svc.link_interactive(scene, sheet)
    assert pump_until(lambda: sheet.linked_document is not None, 5)
    assert sheet.linked_document.page == 2
    assert fixture_text("WORD", 2) in snapshot_text(sheet.linked_document)
    assert scene.undo_stack.count() == 1 and len(mgr.sheets) == 1


# -- Added guards: shutdown cancels, joins, and silences workers --------------

def _blocked_conversion(made, tmp_path, outcome):
    """A service whose one .docx conversion blocks until ``release`` is set."""
    started, release = threading.Event(), threading.Event()

    def stub(_path):
        started.set()
        release.wait(10)
        if outcome == "error":
            raise doc_converter.ConversionError("late failure")
        return pdf_bytes(2, "LATE")

    svc, scene, mgr, msgs = _service(made, [_docx_link(tmp_path, 1)],
                                     convert_fn=stub,
                                     word_available_fn=lambda: True)
    svc.request_refresh(str(tmp_path / "spec.docx"))
    assert started.wait(5)
    return svc, scene, mgr, msgs, release


@pytest.mark.parametrize("outcome", ["result", "error"])
def test_shutdown_silences_a_cancelled_worker(qapp, tmp_path, made, outcome):
    svc, scene, mgr, msgs, release = _blocked_conversion(made, tmp_path, outcome)
    ld = mgr.sheets[0].linked_document
    saved = ld.snapshot_pdf
    badge_before = scene.linked_badge().text()
    mods = []
    scene.sheetModified.connect(lambda: mods.append(1))
    # The blocked stub never sees the cancel event, so free it just after
    # shutdown starts waiting; its late result or error must go nowhere.
    threading.Timer(0.3, release.set).start()
    svc.shutdown()
    pump_until(lambda: False, 0.6)                 # deliver anything queued
    assert ld.snapshot_pdf == saved
    assert ld.last_error == ""
    assert mods == []
    assert scene.linked_badge().text() == badge_before
    assert not any(m.startswith(("Updated", "Could not update")) for m in msgs)


def test_shutdown_joins_every_worker_thread(qapp, tmp_path, made):
    svc, scene, mgr, msgs, release = _blocked_conversion(made, tmp_path, "result")
    workers = svc.findChildren(doc_converter.ConvertWorker)
    assert len(workers) == 1 and workers[0].isRunning()
    threading.Timer(0.3, release.set).start()
    svc.shutdown()
    assert all(w.isFinished() and not w.isRunning() for w in workers)
    assert not svc.converting(str(tmp_path / "spec.docx"))
