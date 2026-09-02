"""Item 3 of the PDF Import Polish cluster: multi-page PDFs are selectable by
name (PyMuPDF page label else 'Page N'), with the name shown as the thumbnail
caption. Single-page import is unchanged. Uses generated fitz fixtures (no
external files)."""
import fitz  # PyMuPDF

from firepro3d.pdf_import_worker import pdf_page_names


def _make_pdf(path, pages=1, widths=None, labels=None):
    """Create a PDF. widths: stroke widths to draw on page 0.
    labels: fitz page-label rule list."""
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=200, height=200)
    if widths:
        page = doc[0]
        shape = page.new_shape()
        for i, w in enumerate(widths):
            y = 20 + i * 20
            shape.draw_line((10, y), (180, y))
            shape.finish(width=w, color=(0, 0, 0))
        shape.commit()
    if labels:
        doc.set_page_labels(labels)
    doc.save(str(path))
    doc.close()


def test_page_names_fall_back_to_page_n(tmp_path):
    p = tmp_path / "plain.pdf"
    _make_pdf(p, pages=3)
    assert pdf_page_names(str(p)) == ["Page 1", "Page 2", "Page 3"]


def test_page_names_use_labels_when_present(tmp_path):
    p = tmp_path / "labeled.pdf"
    _make_pdf(p, pages=2,
              labels=[{"startpage": 0, "prefix": "A-", "style": "D",
                       "firstpagenum": 100}])
    names = pdf_page_names(str(p))
    assert names[0] == "A-100"
    assert names[1] == "A-101"


def test_dialog_shows_page_name_captions(qapp, tmp_path):
    p = tmp_path / "multi.pdf"
    _make_pdf(p, pages=3)
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None)
    dlg._load_pdf(str(p))
    captions = [dlg._thumb_list.item(i).text()
                for i in range(dlg._thumb_list.count())]
    assert captions == ["Page 1", "Page 2", "Page 3"]
    assert dlg._pdf_page == 0
