"""linked_document pure helpers (design Data model, D1, D1b, D2, D7, D8, D9, Q11)."""
from __future__ import annotations

import base64
import datetime
import os
from pathlib import Path

import fitz
import pytest
from PyQt6.QtCore import QRectF

from firepro3d.paper_space import PAPER_SIZES
from firepro3d.titleblock_template import make_default_template, solve_layout
from tests._linked_doc_helpers import (
    ALPHA_ORIGIN_PT, FRAME_RECT_PT, MM_PER_PT, PAGE_H_PT, PAGE_W_PT, PT_PER_MM,
    TWO_PAGE, build_fixture_pdf, fixture_text, make_link, pdf_bytes,
    snapshot_text,
)

NOW = datetime.datetime(2026, 11, 9, 14, 30, 0)
PAGE_W_MM, PAGE_H_MM = PAGE_W_PT * MM_PER_PT, PAGE_H_PT * MM_PER_PT


def _area_ansi_d() -> QRectF:
    w, h = PAPER_SIZES["ANSI D"]
    return solve_layout(make_default_template().layout, w, h, {}).area_rect


def _fit(paper: str) -> float:
    w, h = PAPER_SIZES[paper]
    return min(w / PAGE_W_MM, h / PAGE_H_MM)


def test_new_link_snapshots_one_page(qapp):
    from firepro3d.linked_document import new_link
    data = new_link(str(TWO_PAGE), Path(TWO_PAGE).read_bytes(), 2, 123.5, 456,
                    now=NOW)
    doc = fitz.open(stream=base64.b64decode(data.snapshot_pdf), filetype="pdf")
    try:
        assert len(doc) == 1
        text = doc[0].get_text()
    finally:
        doc.close()
    assert fixture_text("ALPHA", 2) in text
    assert fixture_text("ALPHA", 1) not in text
    assert (data.page, data.source_pages, data.offered_pages) == (2, 2, 2)
    assert (data.source_mtime, data.source_size) == (123.5, 456)
    assert data.snapshot_at == "2026-11-09T14:30:00"
    assert data.path == os.path.abspath(str(TWO_PAGE))


def test_new_link_refuses_a_page_the_file_lacks(qapp):
    from firepro3d.linked_document import SnapshotError, new_link
    with pytest.raises(SnapshotError):
        new_link(str(TWO_PAGE), Path(TWO_PAGE).read_bytes(), 3, 1.0, 1)


def test_dict_round_trip_and_old_defaults(qapp):
    from firepro3d.linked_document import LinkedDocData
    data = make_link(TWO_PAGE, 1, "custom", 1.5)
    data.last_error = "runtime only"
    d = data.to_dict()
    assert "last_error" not in d
    assert LinkedDocData.from_dict(d).to_dict() == d
    old = LinkedDocData.from_dict({"path": "x.pdf", "scale_mode": "bogus"})
    assert (old.page, old.scale_mode, old.snapshot_pdf, old.offered_pages) == (
        1, "fit", "", 0)


def test_page_size_comes_from_the_snapshot(qapp):
    from firepro3d.linked_document import page_size_mm
    w, h = page_size_mm(make_link(TWO_PAGE, 1).snapshot_pdf)
    assert (w, h) == pytest.approx((PAGE_W_MM, PAGE_H_MM))


def test_fit_is_2x_on_ansi_d_and_1x_on_ansi_b(qapp):
    """AC4 numbers as the design states them (11x17 on D = 2x, on B = 1x)."""
    from firepro3d.linked_document import placement
    data = make_link(TWO_PAGE, 1)
    assert placement(data, *PAPER_SIZES["ANSI D"]).scale == pytest.approx(2.0)
    assert placement(data, *PAPER_SIZES["ANSI B"]).scale == pytest.approx(1.0)


@pytest.mark.parametrize("paper,mode,custom", [
    ("ANSI D", "fit", 1.0), ("ANSI B", "fit", 1.0), ("A1", "fit", 1.0),
    ("ANSI D", "1", 1.0), ("ANSI D", "2", 1.0), ("ANSI D", "custom", 1.5),
])
def test_placement_is_centred_at_the_mode_scale(qapp, paper, mode, custom):
    from firepro3d.linked_document import placement
    sw, sh = PAPER_SIZES[paper]
    s = {"fit": _fit(paper), "1": 1.0, "2": 2.0, "custom": custom}[mode]
    geo = placement(make_link(TWO_PAGE, 1, mode, custom), sw, sh)
    r = geo.rect
    assert geo.scale == pytest.approx(s)
    assert (r.x(), r.y(), r.width(), r.height()) == pytest.approx(
        ((sw - PAGE_W_MM * s) / 2, (sh - PAGE_H_MM * s) / 2,
         PAGE_W_MM * s, PAGE_H_MM * s))


def test_content_bounds_and_overlap(qapp):
    from firepro3d.linked_document import content_bounds_mm, overlap_mm
    sw, sh = PAPER_SIZES["ANSI D"]
    s = _fit("ANSI D")
    b = content_bounds_mm(make_link(TWO_PAGE, 1), sw, sh)
    assert b.left() == pytest.approx(ALPHA_ORIGIN_PT[0] * MM_PER_PT * s)
    assert b.right() == pytest.approx(FRAME_RECT_PT[2] * MM_PER_PT * s)
    area = _area_ansi_d()
    assert overlap_mm(b, area) == pytest.approx(
        FRAME_RECT_PT[2] * MM_PER_PT * s - area.right())
    assert overlap_mm(b, QRectF(0, 0, sw, sh)) == 0.0
    assert overlap_mm(None, area) == 0.0


def test_export_geometry_clips_destination_and_source_alike(qapp):
    from firepro3d.linked_document import export_geometry
    sw, sh = PAPER_SIZES["ANSI D"]
    s = _fit("ANSI D")                 # placement origin is (0, 0) at fit on D
    area = _area_ansi_d()
    geo = export_geometry(make_link(TWO_PAGE, 1), sw, sh, area)
    assert geo.dest_pt == pytest.approx(
        (area.left() * PT_PER_MM, area.top() * PT_PER_MM,
         area.right() * PT_PER_MM, area.bottom() * PT_PER_MM))
    assert geo.clip_pt == pytest.approx(
        (area.left() / s * PT_PER_MM, area.top() / s * PT_PER_MM,
         area.right() / s * PT_PER_MM, area.bottom() / s * PT_PER_MM))


def test_refresh_updates_or_keeps_copy_when_page_gone(qapp):
    from firepro3d.linked_document import (
        REFRESH_PAGE_GONE, REFRESH_UPDATED, SnapshotError, new_link,
        refresh_from_pdf,
    )
    data = new_link(str(TWO_PAGE), Path(TWO_PAGE).read_bytes(), 2, 1.0, 10,
                    now=NOW)
    before = data.snapshot_pdf
    assert refresh_from_pdf(data, pdf_bytes(1, "BETA"), 2.0, 20,
                            now=NOW) == REFRESH_PAGE_GONE
    assert data.snapshot_pdf == before
    assert (data.source_pages, data.source_mtime, data.source_size) == (1, 2.0, 20)
    assert refresh_from_pdf(data, pdf_bytes(3, "BETA"), 3.0, 30,
                            now=NOW) == REFRESH_UPDATED
    assert fixture_text("BETA", 2) in snapshot_text(data)
    assert data.source_pages == 3
    with pytest.raises(SnapshotError):
        refresh_from_pdf(data, b"not a pdf", 4.0, 1)


def test_badge_priority(qapp, tmp_path):
    from firepro3d.linked_document import badge_text
    src = build_fixture_pdf(tmp_path / "spec.pdf", 2)
    data = make_link(src, 1)
    data.snapshot_at = "2026-11-09T14:30:00"
    sw, sh = PAPER_SIZES["ANSI D"]
    area = _area_ansi_d()
    over = FRAME_RECT_PT[2] * MM_PER_PT * _fit("ANSI D") - area.right()

    def badge(**kw):
        base = dict(sheet_w=sw, sheet_h=sh, area=area, file_exists=True,
                    word_ok=True)
        base.update(kw)
        return badge_text(data, **base)

    assert badge() == f"Page content overlaps the title block by {over:.0f} mm"
    assert badge(area=QRectF(0, 0, sw, sh)) == "Page shown at 2x"
    data.last_error = "Word did not finish in 120 s"
    assert badge() == "Could not update from spec.pdf: Word did not finish in 120 s"
    data.path = str(tmp_path / "spec.docx")
    assert badge(word_ok=False) == (
        "Word not available - showing copy from 2026-11-09 14:30")
    data.page, data.source_pages = 2, 1
    assert badge(word_ok=False) == "Page 2 is no longer in spec.docx"
    assert badge(file_exists=False, word_ok=False) == (
        "Linked file missing - showing copy from 2026-11-09 14:30")
    b_w, b_h = PAPER_SIZES["ANSI B"]
    plain = make_link(src, 1)
    assert badge_text(plain, sheet_w=b_w, sheet_h=b_h, area=QRectF(0, 0, b_w, b_h),
                      file_exists=True, word_ok=True) == ""


def test_paths_are_stored_like_underlays(tmp_path):
    from firepro3d.linked_document import loaded_path, stored_path
    proj = tmp_path / "proj"
    inside = build_fixture_pdf(proj / "docs" / "spec.pdf", 1)
    rel = os.path.relpath(str(inside), str(proj))
    assert stored_path(str(inside), str(proj)) == rel
    assert loaded_path(rel, str(proj)) == os.path.abspath(str(inside))
    far = tmp_path / "x" / "spec.pdf"
    assert stored_path(str(far), str(tmp_path / "a" / "b" / "c")) == (
        os.path.abspath(str(far)))
    assert loaded_path(os.path.join("docs", "gone.pdf"), str(proj)) == (
        os.path.normpath(os.path.join(str(proj), "docs", "gone.pdf")))


def test_raster_dpi_screen_ladder_and_print_cap():
    from firepro3d.constants import (
        LINKED_PAGE_DPI_STEP, LINKED_PAGE_MIN_DPI, LINKED_PAGE_PRINT_MAX_DPI,
        LINKED_PAGE_SCREEN_MAX_DPI,
    )
    from firepro3d.linked_document import raster_dpi
    assert raster_dpi(10.0, screen=True) == LINKED_PAGE_MIN_DPI
    assert raster_dpi(LINKED_PAGE_MIN_DPI * 1.2, screen=True) == pytest.approx(
        LINKED_PAGE_MIN_DPI * LINKED_PAGE_DPI_STEP)
    assert raster_dpi(10_000.0, screen=True) == LINKED_PAGE_SCREEN_MAX_DPI
    assert raster_dpi(101.6, screen=False) == pytest.approx(101.6)
    assert raster_dpi(10_000.0, screen=False) == LINKED_PAGE_PRINT_MAX_DPI
