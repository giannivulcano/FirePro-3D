"""The checked-in linked-document fixtures match their generator constants."""
from __future__ import annotations

import fitz
import pytest

from tests._linked_doc_helpers import (
    ALPHA_ORIGIN_PT, FRAME_RECT_PT, MARK_RECT_PT, ONE_PAGE, OVERRUN_ORIGIN_PT,
    OVERRUN_TEXT, PAGE_H_PT, PAGE_W_PT, TWO_PAGE, fixture_text, word_bbox,
)


@pytest.mark.parametrize("path,n_pages", [(TWO_PAGE, 2), (ONE_PAGE, 1)])
def test_checked_in_fixture_matches_generator(path, n_pages):
    doc = fitz.open(str(path))
    try:
        assert len(doc) == n_pages
        for i, page in enumerate(doc, start=1):
            assert (page.rect.width, page.rect.height) == (PAGE_W_PT, PAGE_H_PT)
            assert word_bbox(page, fixture_text("ALPHA", i))[0] == pytest.approx(
                ALPHA_ORIGIN_PT[0])
            assert word_bbox(page, OVERRUN_TEXT)[0] == pytest.approx(
                OVERRUN_ORIGIN_PT[0])
            rects = sorted(tuple(round(v, 3) for v in d["rect"])
                           for d in page.get_drawings())
            assert rects == sorted([FRAME_RECT_PT, MARK_RECT_PT])
    finally:
        doc.close()
