"""Regression: multi-page PDF import must persist page/dpi into the record.

The freeze-blit live-debug session (2026-08-30) found that the interactive
placement commit defaulted the record to page 0 while the geometry cache
carried the *selected* page. That stayed masked by cache hits until any
re-extraction (refresh, cache miss) rebuilt from page 0 — the cover sheet
("you broke the underlay"). The fix (a62f543/46e37d6) persists
``params.pdf_page``/``pdf_dpi`` at ``_commit_place_import``; no automated test
drove that path. These tests are that guard (TODO 72).
"""
import fitz  # PyMuPDF
from PyQt6.QtCore import QPointF

from firepro3d.underlay_import_dialog import ImportParams
from firepro3d.model_space import Model_Space
from firepro3d.pdf_import_worker import extract_pdf_vectors_sync
from firepro3d.underlay_cache import compute_cache_key


def _make_2page_pdf(path):
    """Page 0 draws only near the TOP (y~10); page 1 only near the BOTTOM
    (y~100-180). The two pages are distinguished by geometry Y-extent, which
    is robust to how PyMuPDF merges strokes into polylines."""
    doc = fitz.open()
    p0 = doc.new_page(width=200, height=200)
    sh0 = p0.new_shape()
    sh0.draw_line((10, 10), (180, 10))
    sh0.finish(width=1.0, color=(0, 0, 0))
    sh0.commit()
    p1 = doc.new_page(width=200, height=200)
    sh1 = p1.new_shape()
    for y in (100, 140, 180):
        sh1.draw_line((10, y), (180, y))
    sh1.finish(width=1.0, color=(0, 0, 0))
    sh1.commit()
    doc.save(str(path))
    doc.close()


def _max_y(geoms):
    """Largest Y coordinate across all stroked geometry (page discriminator)."""
    ys = []
    for g in geoms:
        if g.get("kind") == "line":
            ys += [g["y1"], g["y2"]]
        elif g.get("kind") == "path_points":
            ys += [p[1] for p in g.get("points", [])]
    return max(ys) if ys else 0.0


def test_pages_are_distinguishable(tmp_path):
    """Sanity: the two pages really do extract to different geometry."""
    p = tmp_path / "two.pdf"
    _make_2page_pdf(p)
    g0, _ = extract_pdf_vectors_sync(str(p), page=0)
    g1, _ = extract_pdf_vectors_sync(str(p), page=1)
    assert _max_y(g0) < 50      # page 0: top only
    assert _max_y(g1) > 90      # page 1: bottom only


def test_commit_persists_page_and_dpi(qapp, tmp_path):
    p = tmp_path / "two.pdf"
    _make_2page_pdf(p)
    geoms, _ = extract_pdf_vectors_sync(str(p), page=1)

    params = ImportParams()
    params.file_path = str(p)
    params.file_type = "pdf"
    params.geom_list = geoms
    params.pdf_page = 1
    params.pdf_dpi = 300
    params.import_mode = "vectors"

    scene = Model_Space()
    scene._place_import_params = params
    scene._place_import_ghost = None
    scene._commit_place_import(QPointF(0.0, 0.0))

    assert scene.underlays, "placement should append an underlay record"
    record, _group = scene.underlays[-1]
    # the record MUST carry the selected page/dpi, else any re-extraction
    # (refresh / cache miss) silently rebuilds page 0.
    assert record.page == 1
    assert record.dpi == 300


def test_cache_key_is_page_sensitive(tmp_path):
    """The geometry cache key must include the page so page 0 and page 1
    never collide (a colliding key would serve the wrong sheet on reload)."""
    p = str(tmp_path / "two.pdf")
    assert compute_cache_key(p, page=0) != compute_cache_key(p, page=1)


def test_reload_extraction_uses_record_page(qapp, tmp_path):
    """End-to-end shape of the bug: after placing page 1, the persisted
    record.page routes a cache-miss re-extraction back to page 1's geometry
    (3 lines), not page 0's cover sheet (1 line)."""
    p = tmp_path / "two.pdf"
    _make_2page_pdf(p)
    geoms, _ = extract_pdf_vectors_sync(str(p), page=1)

    params = ImportParams()
    params.file_path = str(p)
    params.file_type = "pdf"
    params.geom_list = geoms
    params.pdf_page = 1
    params.pdf_dpi = 150
    params.import_mode = "vectors"

    scene = Model_Space()
    scene._place_import_params = params
    scene._place_import_ghost = None
    scene._commit_place_import(QPointF(0.0, 0.0))
    record, _ = scene.underlays[-1]

    # simulate the refresh / cache-miss reload path: re-extract by record.page
    reloaded, _ = extract_pdf_vectors_sync(str(p), page=record.page)
    assert _max_y(reloaded) > 90      # page 1, not the page-0 cover sheet
