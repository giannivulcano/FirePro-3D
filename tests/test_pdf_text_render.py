"""Item 6: PDF import text is DPI-independently sized (pixel size, not point
size -> no 96/72 or HiDPI inflation) and top-anchored (PDF span bbox top).
The text-render path builder is duplicated in model_space + dxf_preview_dialog;
both must render identically."""
import fitz  # PyMuPDF
from PyQt6.QtGui import QFont, QPainterPath

from firepro3d.pdf_import_worker import extract_pdf_vectors_sync
from firepro3d.model_space import Model_Space
from firepro3d.dxf_preview_dialog import UnderlayImportDialog


def _text_pdf(path):
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 50), "SPRINKLER", fontsize=10)
    doc.save(str(path))
    doc.close()


def test_extract_text_is_top_anchored_and_sized(tmp_path, qapp):
    p = tmp_path / "text.pdf"
    _text_pdf(p)
    geoms, _ = extract_pdf_vectors_sync(str(p), page=0)
    texts = [g for g in geoms if g.get("kind") == "text"]
    assert texts, "expected at least one text geom"
    g = texts[0]
    assert g.get("valign") == 0          # top-anchored to the span bbox top
    assert g.get("size", 0) > 0


def _rendered_text_height(append_fn):
    path = QPainterPath()
    append_fn(path, {"kind": "text", "text": "Hg", "x": 0.0, "y": 0.0,
                     "size": 10.0, "valign": 0})
    return path.boundingRect().height()


def test_text_uses_pixel_sizing_not_point_sizing(qapp):
    # Expected: pixel-sized glyphs (DPI-independent). Point-sizing would be
    # ~1.33x taller at 96 DPI (and more on HiDPI).
    fx = QFont("Arial"); fx.setPixelSize(10)
    exp = QPainterPath(); exp.addText(0, 0, fx, "Hg")
    expected = exp.boundingRect().height()

    fp = QFont("Arial"); fp.setPointSizeF(10.0)
    ptp = QPainterPath(); ptp.addText(0, 0, fp, "Hg")
    point_height = ptp.boundingRect().height()
    assert point_height > expected + 0.5   # sanity: the two differ meaningfully

    ms_h = _rendered_text_height(Model_Space._append_geom_to_path)
    dlg_h = _rendered_text_height(UnderlayImportDialog._append_geom_to_path)
    assert abs(ms_h - expected) < 0.6      # matches pixel sizing, not point
    assert abs(dlg_h - expected) < 0.6     # preview copy renders identically
