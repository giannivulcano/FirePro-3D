"""Batch export dialog (spec §19.6) — widget-driven; QPdfWriter only."""
from __future__ import annotations

import pytest

from firepro3d.paper_space import Sheet
from firepro3d.paper_export_dialog import PaperExportDialog


def _sheets(n):
    out = []
    for i in range(n):
        s = Sheet.create_default()
        s.number, s.name = f"FP-{i + 1}.0", f"Sheet {i + 1}"
        out.append(s)
    return out


@pytest.fixture()
def dlg(qapp, tmp_path):
    d = PaperExportDialog(_sheets(3))
    d._path_edit.setText(str(tmp_path / "out.pdf"))
    yield d
    d.deleteLater()


def test_all_sheets_listed_checked_in_order(dlg):
    labels = [cb.text() for cb in dlg._checks]
    assert labels == ["FP-1.0 - Sheet 1", "FP-2.0 - Sheet 2",
                      "FP-3.0 - Sheet 3"]
    assert all(cb.isChecked() for cb in dlg._checks)


def test_ok_disabled_at_zero_selection(dlg):
    for cb in dlg._checks:
        cb.setChecked(False)
    assert not dlg._ok_btn.isEnabled()
    dlg._checks[1].setChecked(True)
    assert dlg._ok_btn.isEnabled()


def test_select_all_toggle(dlg):
    dlg._select_all.setChecked(False)
    assert not any(cb.isChecked() for cb in dlg._checks)
    dlg._select_all.setChecked(True)
    assert all(cb.isChecked() for cb in dlg._checks)


def test_selection_result_document_order(dlg):
    dlg._checks[0].setChecked(False)
    sel = dlg.selection()
    assert [s.number for s in sel.sheets] == ["FP-2.0", "FP-3.0"]
    assert sel.separate_files is False
    assert sel.dpi == 300
    assert sel.path.endswith("out.pdf")


def test_separate_files_mode(dlg, tmp_path):
    dlg._radio_separate.setChecked(True)
    dlg._path_edit.setText(str(tmp_path))
    sel = dlg.selection()
    assert sel.separate_files is True


def test_print_mode_hides_path_and_dpi(qapp):
    d = PaperExportDialog(_sheets(2), print_mode=True)
    assert d._path_row_hidden and d._dpi_hidden
    assert d._ok_btn.isEnabled()            # no path required for print
    d.deleteLater()


def test_ok_requires_path_in_export_mode(qapp):
    d = PaperExportDialog(_sheets(1))
    d._path_edit.setText("")
    assert not d._ok_btn.isEnabled()
    d.deleteLater()


def test_batch_export_page_count(qapp, tmp_path):
    from PyQt6.QtPdf import QPdfDocument
    from firepro3d import paper_export
    from firepro3d.paper_space import ViewResolver
    from unittest.mock import MagicMock
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QGraphicsScene

    model_scene = QGraphicsScene()
    model_scene.addRect(0, 0, 10000, 8000)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = (model_scene, QRectF(0, 0, 10000, 8000))

    sheets = _sheets(3)
    out = str(tmp_path / "batch.pdf")
    paper_export.export_pdf(sheets, resolver, out)

    doc = QPdfDocument(None)
    doc.load(out)
    assert doc.pageCount() == 3


def test_separate_files_naming(tmp_path):
    from firepro3d.paper_export import default_pdf_filename
    s = Sheet.create_default()
    s.number, s.name = "FP-1.0", 'Bad:Name?*'
    assert default_pdf_filename(s) == "FP-1.0 - Bad_Name__.pdf"


def test_select_all_reflects_manual_deselection(dlg):
    dlg._checks[0].setChecked(False)
    assert not dlg._select_all.isChecked(), "Select All must drop on partial"
    dlg._checks[0].setChecked(True)
    assert dlg._select_all.isChecked(), "Select All returns when all checked"
