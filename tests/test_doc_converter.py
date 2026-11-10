"""doc_converter: .docx -> PDF through Word in powershell.exe (design D3)."""
from __future__ import annotations

import os
import subprocess
import zipfile

import fitz
import pytest

from firepro3d import doc_converter
from firepro3d.constants import LINKED_DOC_CONVERT_TIMEOUT_S
from tests._linked_doc_helpers import PAGE_H_PT, PAGE_W_PT, pdf_bytes, pump_until


@pytest.fixture(autouse=True)
def _fresh_word_cache():
    doc_converter.word_available.cache_clear()
    yield
    doc_converter.word_available.cache_clear()


def _fake_popen(record, *, returncode=0, write_pdf=True, hang=False,
                stderr="Word said no"):
    """Stand-in for subprocess.Popen (the converter polls communicate(0.25)
    so a window close can stop waiting - ratified "Close now, drop update")."""
    class FakePopen:
        def __init__(self, cmd, **kw):
            record["cmd"], record["kw"] = list(cmd), kw
            record["killed"] = False
            with open(cmd[cmd.index("-File") + 1], encoding="utf-8") as fh:
                record["script"] = fh.read()
            in_path = cmd[cmd.index("-InPath") + 1]
            out_path = cmd[cmd.index("-OutPath") + 1]
            record["in_path"] = in_path
            record["in_exists"] = os.path.isfile(in_path)
            self.returncode = None
            if not hang and write_pdf:
                with open(out_path, "wb") as fh:
                    fh.write(pdf_bytes(1, "WORD"))

        def communicate(self, timeout=None):
            if hang and not record["killed"]:
                raise subprocess.TimeoutExpired(["powershell.exe"], timeout)
            self.returncode = -9 if record["killed"] else returncode
            return "", ("" if self.returncode == 0 else stderr)

        def kill(self):
            record["killed"] = True
    return FakePopen


def test_paths_are_arguments_never_script_text(tmp_path, monkeypatch):
    src = tmp_path / "My Spec (rev 2).docx"
    src.write_bytes(b"docx bytes")
    rec = {}
    monkeypatch.setattr(doc_converter.subprocess, "Popen", _fake_popen(rec))
    data = doc_converter.convert_docx_to_pdf_bytes(str(src))
    doc = fitz.open(stream=data, filetype="pdf")
    assert "FIXTURE-WORD-P1" in doc[0].get_text()
    doc.close()
    assert rec["script"] == doc_converter._PS_SCRIPT
    assert str(src) not in rec["script"] and rec["in_path"] not in rec["script"]
    assert rec["in_path"] != str(src) and rec["in_exists"]     # a temp copy
    assert not os.path.exists(os.path.dirname(rec["in_path"]))  # temp removed


def test_timeout_is_a_conversion_error(tmp_path, monkeypatch):
    # RED: drop the deadline check -> the loop never ends (pytest-timeout /
    # hang); drop proc.kill() -> rec["killed"] stays False.
    src = tmp_path / "a.docx"
    src.write_bytes(b"x")
    rec = {}
    monkeypatch.setattr(doc_converter.subprocess, "Popen",
                        _fake_popen(rec, hang=True))
    with pytest.raises(doc_converter.ConversionError, match="1 s"):
        doc_converter.convert_docx_to_pdf_bytes(str(src), timeout=1)
    assert rec["killed"]
    assert not os.path.exists(os.path.dirname(rec["in_path"]))


def test_cancel_stops_waiting_without_killing_word(tmp_path, monkeypatch):
    # Ratified 2026-11-09 "Close now, drop update". RED: ignore *cancel* ->
    # the call waits for the 120 s deadline (elapsed bound fails); kill on
    # cancel -> rec["killed"]; rmtree on cancel -> work folder gone.
    import threading
    import time
    src = tmp_path / "a.docx"
    src.write_bytes(b"x")
    rec = {}
    monkeypatch.setattr(doc_converter.subprocess, "Popen",
                        _fake_popen(rec, hang=True))
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    t0 = time.monotonic()
    with pytest.raises(doc_converter.ConversionCancelled):
        doc_converter.convert_docx_to_pdf_bytes(str(src), cancel=cancel)
    assert time.monotonic() - t0 < 2.0
    assert not rec["killed"]                          # PowerShell left running
    assert os.path.isdir(os.path.dirname(rec["in_path"]))  # its folder kept


def test_word_error_text_is_reported(tmp_path, monkeypatch):
    src = tmp_path / "a.docx"
    src.write_bytes(b"x")
    monkeypatch.setattr(doc_converter.subprocess, "Popen",
                        _fake_popen({}, returncode=1, write_pdf=False))
    with pytest.raises(doc_converter.ConversionError, match="Word said no"):
        doc_converter.convert_docx_to_pdf_bytes(str(src))


def test_missing_file_is_a_conversion_error(tmp_path):
    with pytest.raises(doc_converter.ConversionError, match="not found"):
        doc_converter.convert_docx_to_pdf_bytes(str(tmp_path / "none.docx"))


def test_word_available_reads_the_com_registration(monkeypatch):
    import winreg

    def missing(*_a, **_k):
        raise FileNotFoundError("no key")

    monkeypatch.setattr(winreg, "OpenKey", missing)
    assert doc_converter.word_available() is False


def test_worker_reports_through_signals(qapp):
    got, failed = [], []
    ok = doc_converter.ConvertWorker("a.docx", lambda p: b"%PDF-bytes")
    ok.converted.connect(lambda path, data: got.append((path, data)))
    ok.start()
    assert pump_until(lambda: got, 5)
    ok.wait()
    assert got == [("a.docx", b"%PDF-bytes")]

    def boom(_p):
        raise doc_converter.ConversionError("Word did not finish in 120 s")

    bad = doc_converter.ConvertWorker("b.docx", boom)
    bad.failed.connect(lambda path, reason: failed.append((path, reason)))
    bad.start()
    assert pump_until(lambda: failed, 5)
    bad.wait()
    assert failed == [("b.docx", "Word did not finish in 120 s")]


def _write_min_docx(path, text: str) -> None:
    """A minimal 17x11 landscape .docx (no python-docx in the venv)."""
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    body = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
            '<w:sectPr><w:pgSz w:w="24480" w:h="15840" w:orient="landscape"/></w:sectPr>'
            '</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", body)


@pytest.mark.skipif(not doc_converter.word_available(),
                    reason="Microsoft Word is not installed")
def test_live_word_converts_a_tiny_docx(tmp_path):
    docx = tmp_path / "tiny.docx"
    _write_min_docx(docx, "LIVE-WORD-FIXTURE")
    data = doc_converter.convert_docx_to_pdf_bytes(str(docx))
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        assert "LIVE-WORD-FIXTURE" in doc[0].get_text()
        assert (doc[0].rect.width, doc[0].rect.height) == pytest.approx(
            (PAGE_W_PT, PAGE_H_PT), abs=1)
    finally:
        doc.close()
