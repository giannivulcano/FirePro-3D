"""Linked page in exported PDFs (vector, D1) and in print (raster, D1b)."""
from __future__ import annotations

import fitz
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import linked_document, paper_export
from firepro3d.constants import LINKED_BADGE_FILL, LINKED_PAGE_PRINT_MAX_DPI
from firepro3d.paper_space import PAPER_SIZES, PaperScene, Sheet, ViewResolver
from firepro3d.titleblock_template import make_default_template, solve_layout
from tests._linked_doc_helpers import (
    MARK_RECT_PT, MM_PER_PT, OVERRUN_TEXT, PAGE_H_PT, PAGE_W_PT, PT_PER_MM,
    TWO_PAGE, fixture_text, make_link, render_scene, word_bbox,
)

PAGE_W_MM, PAGE_H_MM = PAGE_W_PT * MM_PER_PT, PAGE_H_PT * MM_PER_PT


def _resolver():
    return ViewResolver(None, None, None, None)


def _sheet(mode="fit", custom=1.0):
    sheet = Sheet.create_default()                      # ANSI D, native
    sheet.linked_document = make_link(TWO_PAGE, 1, mode, custom)
    return sheet


def _export(tmp_path, sheet, template):
    out = tmp_path / "out.pdf"
    paper_export.export_pdf([sheet], _resolver(), str(out), dpi=150,
                            template=template, project_info={})
    return fitz.open(str(out))


@pytest.mark.parametrize("mode,custom", [("fit", 1.0), ("custom", 1.5)])
def test_export_places_vector_text_at_scale(qapp, tmp_path, mode, custom):
    doc = _export(tmp_path, _sheet(mode, custom), make_default_template())
    page = doc[0]
    w_mm, h_mm = PAPER_SIZES["ANSI D"]
    assert (page.rect.width, page.rect.height) == pytest.approx(
        (w_mm * PT_PER_MM, h_mm * PT_PER_MM), abs=0.5)
    s = min(w_mm / PAGE_W_MM, h_mm / PAGE_H_MM) if mode == "fit" else custom
    off_x = (w_mm - PAGE_W_MM * s) / 2 * PT_PER_MM
    off_y = (h_mm - PAGE_H_MM * s) / 2 * PT_PER_MM
    src = fitz.open(str(TWO_PAGE))
    sx0, sy0, _, _ = word_bbox(src[0], fixture_text("ALPHA", 1))
    src.close()
    x0, y0, _, _ = word_bbox(page, fixture_text("ALPHA", 1))
    assert x0 == pytest.approx(off_x + sx0 * s, abs=0.5)
    assert y0 == pytest.approx(off_y + sy0 * s, abs=0.5)
    assert page.get_images(full=True) == []             # vector, not the raster
    doc.close()


def test_export_clips_at_the_drawing_area_and_omits_the_badge(qapp, tmp_path):
    tmpl = make_default_template()
    sheet = _sheet()
    live = PaperScene(sheet, _resolver())
    live.set_template(tmpl, {})
    badge = live.linked_badge().text()
    assert badge.startswith("Page content overlaps the title block by")
    doc = _export(tmp_path, sheet, tmpl)
    page = doc[0]
    w_mm, h_mm = PAPER_SIZES["ANSI D"]
    strip = solve_layout(tmpl.layout, w_mm, h_mm, {}).strip_rect
    strip_pt = fitz.Rect(strip.left() * PT_PER_MM, strip.top() * PT_PER_MM,
                         strip.right() * PT_PER_MM, strip.bottom() * PT_PER_MM)
    text = page.get_text()
    assert fixture_text("ALPHA", 1) in text
    assert OVERRUN_TEXT not in text
    assert OVERRUN_TEXT not in [w[4] for w in page.get_text("words", clip=strip_pt)]
    assert "overlaps the title block" not in text
    doc.close()


def test_export_without_template_keeps_text_inside_the_border(qapp, tmp_path):
    """Control: the clip is the drawing area, so with no title block the
    overrun text (inside the 10 mm border) stays."""
    doc = _export(tmp_path, _sheet(), None)
    assert OVERRUN_TEXT in doc[0].get_text()
    doc.close()


def _render_sheet_image(sheet, px_per_mm, template):
    w_mm, h_mm = PAPER_SIZES["ANSI D"]
    img = QImage(int(w_mm * px_per_mm), int(h_mm * px_per_mm),
                 QImage.Format.Format_RGB32)
    img.fill(Qt.GlobalColor.white)
    p = QPainter(img)
    paper_export.render_sheet(sheet, _resolver(), p,
                              QRectF(0, 0, img.width(), img.height()),
                              template=template, project_info={})
    p.end()
    return img


def _badge_pixels(img, rect_mm, px_per_mm):
    want = QColor(LINKED_BADGE_FILL).rgb()
    return sum(1 for x in range(int(rect_mm.left() * px_per_mm),
                                int(rect_mm.right() * px_per_mm))
               for y in range(int(rect_mm.top() * px_per_mm),
                              int(rect_mm.bottom() * px_per_mm))
               if img.pixel(x, y) == want)


@pytest.mark.parametrize("px_per_mm", [2.0, 6.0])
def test_print_path_paints_the_page_at_device_dpi_without_badge(
        qapp, monkeypatch, px_per_mm):
    tmpl = make_default_template()
    sheet = _sheet()
    w_mm, h_mm = PAPER_SIZES["ANSI D"]
    live = PaperScene(sheet, _resolver())
    live.set_template(tmpl, {})
    badge_rect = live.linked_badge().sceneBoundingRect()
    assert _badge_pixels(render_scene(live, w_mm, h_mm, px_per_mm), badge_rect,
                         px_per_mm) > 0                 # control: on screen
    seen = []
    real = linked_document.render_snapshot
    monkeypatch.setattr(linked_document, "render_snapshot",
                        lambda b64, dpi: seen.append(dpi) or real(b64, dpi))
    img = _render_sheet_image(sheet, px_per_mm, tmpl)
    s = min(w_mm / PAGE_W_MM, h_mm / PAGE_H_MM)
    cx = (MARK_RECT_PT[0] + MARK_RECT_PT[2]) / 2 * MM_PER_PT * s
    cy = (MARK_RECT_PT[1] + MARK_RECT_PT[3]) / 2 * MM_PER_PT * s
    assert QColor(img.pixel(int(cx * px_per_mm), int(cy * px_per_mm))).red() < 80
    assert _badge_pixels(img, badge_rect, px_per_mm) == 0
    assert seen and seen[-1] == pytest.approx(
        min(px_per_mm * 25.4 * s, LINKED_PAGE_PRINT_MAX_DPI),
        rel=2e-3)   # the image size is int()-truncated, so px/mm is not exact
