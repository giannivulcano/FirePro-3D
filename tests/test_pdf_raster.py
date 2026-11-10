"""pdf_page_to_qimage (shared raster helper) + underlay raster-import parity."""
from __future__ import annotations

import fitz
from PyQt6.QtGui import QColor

from tests._linked_doc_helpers import (
    MARK_RECT_PT, PAGE_H_PT, PAGE_W_PT, TWO_PAGE,
)


def _mark_centre_px(dpi: float):
    k = dpi / 72.0
    return (int((MARK_RECT_PT[0] + MARK_RECT_PT[2]) / 2 * k),
            int((MARK_RECT_PT[1] + MARK_RECT_PT[3]) / 2 * k))


def test_page_to_qimage_size_and_pixels_survive_close(qapp):
    from firepro3d.pdf_raster import pdf_page_to_qimage
    doc = fitz.open(str(TWO_PAGE))
    img = pdf_page_to_qimage(doc[0], 144.0)
    doc.close()                                   # detached copy outlives fitz
    assert (img.width(), img.height()) == (int(PAGE_W_PT * 2), int(PAGE_H_PT * 2))
    x, y = _mark_centre_px(144.0)
    assert QColor(img.pixel(x, y)).red() < 80     # inside the filled square
    assert QColor(img.pixel(5, 5)).red() > 200    # blank page corner


def test_underlay_raster_import_unchanged(qapp):
    """Maint parity guard: passes before and after the extraction."""
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager
    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    scene.import_pdf(str(TWO_PAGE), dpi=72, page=0, import_mode="raster")
    assert len(scene.underlays) == 1
    _record, item = scene.underlays[0]
    img = item.pixmap().toImage()
    assert (img.width(), img.height()) == (int(PAGE_W_PT), int(PAGE_H_PT))
    x, y = _mark_centre_px(72.0)
    assert QColor(img.pixel(x, y)).red() < 80
