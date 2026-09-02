"""PDF extraction honours Cancel mid-run.

``extract_pdf_vectors_sync`` used to be one blocking call, so a Cancel during a
large page's extraction had no effect until the whole page finished. It now
accepts an optional ``should_cancel`` poll and returns ``None`` when the flag
trips mid-loop; the dialog's ``_DialogPdfExtractWorker`` feeds it its own
``_cancelled`` flag and emits ``aborted`` on the ``None`` result.

These tests build a REAL multi-path fitz PDF (many drawing paths so the poll
loop actually iterates) and drive both the sync helper and the dialog worker.
"""

from __future__ import annotations

import time

import fitz  # PyMuPDF


# ── Real 1-page PDF with MANY drawing paths (so the poll loop iterates) ──────

def _make_busy_pdf(path, n_lines=400):
    """A single page carrying *n_lines* separate stroked lines (=paths)."""
    doc = fitz.open()
    pg = doc.new_page(width=500, height=500)
    for i in range(n_lines):
        sh = pg.new_shape()
        y = 5 + (i % 490)
        sh.draw_line((5, y), (495, y))
        sh.finish(width=1.0, color=(0, 0, 0))
        sh.commit()
    doc.save(str(path))
    doc.close()


# ── (a) Unit: should_cancel controls the return ─────────────────────────────

def test_sync_returns_none_when_cancelled(tmp_path):
    """should_cancel→True aborts the extraction and returns the None sentinel."""
    from firepro3d.pdf_import_worker import extract_pdf_vectors_sync

    p = tmp_path / "busy.pdf"
    _make_busy_pdf(p)

    result = extract_pdf_vectors_sync(str(p), 0, should_cancel=lambda: True)
    assert result is None


def test_sync_normal_when_not_cancelled(tmp_path):
    """should_cancel=None (default) and lambda:False both return the tuple."""
    from firepro3d.pdf_import_worker import extract_pdf_vectors_sync

    p = tmp_path / "busy.pdf"
    _make_busy_pdf(p)

    default = extract_pdf_vectors_sync(str(p), 0)
    assert default is not None
    geoms, layers = default
    assert geoms and layers

    never = extract_pdf_vectors_sync(str(p), 0, should_cancel=lambda: False)
    assert never is not None
    assert never[0]


# ── (b) Worker: a should-cancel that trips → emits aborted, not finished ─────

def test_dialog_worker_emits_aborted_on_cancel(qapp, tmp_path):
    """Cancel a _DialogPdfExtractWorker before it runs → it emits ``aborted``
    (not ``finished_geoms``)."""
    from firepro3d.underlay_import_dialog import _DialogPdfExtractWorker

    p = tmp_path / "busy.pdf"
    _make_busy_pdf(p)

    w = _DialogPdfExtractWorker(str(p), 0)
    seen = {"aborted": False, "finished": False}
    w.aborted.connect(lambda: seen.__setitem__("aborted", True))
    w.finished_geoms.connect(
        lambda *_: seen.__setitem__("finished", True))

    # Trip the flag before starting so the very first poll (i == 0) aborts.
    w.cancel()
    w.run()   # run synchronously in-thread — no event loop needed

    assert seen["aborted"] is True
    assert seen["finished"] is False


def test_dialog_worker_finishes_when_not_cancelled(qapp, tmp_path):
    """A non-cancelled worker emits ``finished_geoms`` with real geometry."""
    from firepro3d.underlay_import_dialog import _DialogPdfExtractWorker

    p = tmp_path / "busy.pdf"
    _make_busy_pdf(p)

    w = _DialogPdfExtractWorker(str(p), 0)
    captured = {}
    w.finished_geoms.connect(
        lambda geoms, layers: captured.update(geoms=geoms, layers=layers))
    w.aborted.connect(lambda: captured.setdefault("aborted", True))

    w.run()

    assert "aborted" not in captured
    assert captured.get("geoms")
    assert captured.get("layers")
