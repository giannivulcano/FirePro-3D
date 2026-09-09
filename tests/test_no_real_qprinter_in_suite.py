"""Guard: no suite-reachable PDF-export path may construct a real QPrinter.

A real ``QPrinter(HighResolution)`` queries the default printer driver in its
constructor, which SEH-aborts the full test run on Windows (bug #371). PDF
export must use ``QPdfWriter``. This guard installs a sentinel that raises if
any ``QPrinter`` is constructed, then drives the suite-reachable PDF-export
entry points. The real *print* path (main._print_paper behind QPrintDialog) is
intentionally NOT exercised here — it legitimately builds a QPrinter and is
stubbed in test_titleblock_render.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def forbid_qprinter(monkeypatch):
    import PyQt6.QtPrintSupport as qps

    class _Forbidden:
        PrinterMode = qps.QPrinter.PrinterMode
        OutputFormat = qps.QPrinter.OutputFormat

        def __init__(self, *args, **kwargs):
            raise AssertionError(
                "A real QPrinter was constructed in a suite-reachable PDF path. "
                "Use QPdfWriter instead (bug #371).")

    monkeypatch.setattr(qps, "QPrinter", _Forbidden)
    return _Forbidden


def test_hydraulic_pdf_export_uses_no_real_qprinter(
        qapp, tmp_path, monkeypatch, forbid_qprinter):
    from firepro3d.hydraulic_report import _PRINTER_AVAILABLE
    if not _PRINTER_AVAILABLE:
        pytest.skip("QtPrintSupport unavailable")
    import firepro3d.hydraulic_report as _hr
    from PyQt6.QtWidgets import QFileDialog
    # hydraulic_report binds QPrinter at module import (`from ... import QPrinter`),
    # so a reintroduced `QPrinter(...)` in _export_pdf resolves the module-local
    # name, not qps.QPrinter. Patch it there too or this guard is a false negative.
    monkeypatch.setattr(_hr, "QPrinter", forbid_qprinter, raising=False)
    # Reuse the populated-report helper from the hydraulic-report tests.
    from tests.test_hydraulic_report import TestExports
    w = TestExports()._populated(qapp)
    out = tmp_path / "guard.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    monkeypatch.setattr(_hr, "themed_info", lambda *a, **k: None)
    w._export_pdf()   # must NOT hit the forbidden QPrinter
    assert out.exists() and out.stat().st_size > 5000


def test_paper_export_pdf_uses_no_real_qprinter(
        qapp, tmp_path, forbid_qprinter):
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtCore import QRectF
    from unittest.mock import MagicMock
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, ViewResolver

    model_scene = QGraphicsScene()
    model_scene.addRect(0, 0, 10000, 8000)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = (model_scene, QRectF(0, 0, 10000, 8000))
    out = tmp_path / "guard_export.pdf"

    paper_export.export_pdf([Sheet.create_default()], resolver, str(out))  # QPdfWriter
    assert out.exists() and out.stat().st_size > 0
