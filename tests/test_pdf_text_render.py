"""Item 6: PDF import text matches the source — DPI-independent, fractional-
exact size (pixel-100 font scaled, not rounded point size), and placed at the
span's baseline origin. The text-render path builder is duplicated in
model_space + underlay_import_dialog; both must render identically."""
import fitz  # PyMuPDF
from PyQt6.QtGui import QFont, QPainterPath

from firepro3d.pdf_import_worker import extract_pdf_vectors_sync
from firepro3d.model_space import Model_Space
from firepro3d.underlay_import_dialog import UnderlayImportDialog


def _text_pdf(path):
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 50), "SPRINKLER", fontsize=10)   # baseline at y=50
    doc.save(str(path))
    doc.close()


def test_extract_text_is_baseline_anchored_and_sized(tmp_path, qapp):
    p = tmp_path / "text.pdf"
    _text_pdf(p)
    geoms, _ = extract_pdf_vectors_sync(str(p), page=0)
    texts = [g for g in geoms if g.get("kind") == "text"]
    assert texts, "expected at least one text geom"
    g = texts[0]
    assert g.get("valign") == 3                 # baseline positioning
    assert abs(g.get("y", 0) - 50) < 3          # y == the span baseline origin
    assert abs(g.get("size", 0) - 10) < 1.5
    assert g.get("twidth", 0) > 0               # carries the source span width


def _rendered_text_bbox(append_fn, size=10.0):
    path = QPainterPath()
    append_fn(path, {"kind": "text", "text": "Hg", "x": 0.0, "y": 0.0,
                     "size": size, "valign": 3})
    return path.boundingRect()


def test_text_uses_pixel_sizing_not_point_sizing(qapp):
    # Glyph height must match a DPI-independent PIXEL-sized font (point sizing
    # inflates by the screen-DPI/72 factor on the real app; here we lock the
    # pixel-based expectation so a revert to setPointSizeF is caught on any
    # DPI != 72 display).
    fx = QFont("Arial"); fx.setPixelSize(10)
    exp = QPainterPath(); exp.addText(0, 0, fx, "Hg")
    expected = exp.boundingRect().height()

    ms_h = _rendered_text_bbox(Model_Space._append_geom_to_path).height()
    dlg_h = _rendered_text_bbox(UnderlayImportDialog._append_geom_to_path).height()
    assert abs(ms_h - expected) < 0.6      # matches pixel sizing, not point
    assert abs(dlg_h - expected) < 0.6     # preview copy renders identically


def test_text_size_is_fractional_not_rounded(qapp):
    # 10.0 vs 10.5 must differ by ~5%. Rounding to int px would give 1.0x or 1.1x.
    h10 = _rendered_text_bbox(Model_Space._append_geom_to_path, 10.0).height()
    h105 = _rendered_text_bbox(Model_Space._append_geom_to_path, 10.5).height()
    assert abs(h105 / h10 - 1.05) < 0.02


def test_text_width_fits_source_span(qapp):
    # With a source span width, text is x-scaled to it (no substitute-font drift).
    for append_fn in (Model_Space._append_geom_to_path,
                      UnderlayImportDialog._append_geom_to_path):
        path = QPainterPath()
        append_fn(path, {"kind": "text", "text": "SPRINKLER", "x": 0.0,
                         "y": 0.0, "size": 10.0, "valign": 3, "twidth": 40.0})
        assert abs(path.boundingRect().width() - 40.0) < 3.0
