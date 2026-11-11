"""The linked page and its badge on a real PaperScene (design Z order and clip, D7-D9)."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainterPath
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from firepro3d.constants import LINKED_BADGE_FILL
from firepro3d.paper_space import (
    PAPER_SIZES, PaperScene, Sheet, TitleBlockTemplateItem, ViewResolver,
)
from firepro3d.titleblock_template import make_default_template, solve_layout
from tests._linked_doc_helpers import (
    FRAME_RECT_PT, MARK_RECT_PT, MM_PER_PT, PAGE_H_PT, PAGE_W_PT, TWO_PAGE,
    build_fixture_pdf, dark_at, make_link, render_scene,
)

PAGE_W_MM, PAGE_H_MM = PAGE_W_PT * MM_PER_PT, PAGE_H_PT * MM_PER_PT
MARK_CX_PT = (MARK_RECT_PT[0] + MARK_RECT_PT[2]) / 2
MARK_CY_PT = (MARK_RECT_PT[1] + MARK_RECT_PT[3]) / 2


def _scene(link, paper="ANSI D", template=False):
    sheet = Sheet.create_default()
    sheet.paper_size = paper
    sheet.linked_document = link
    scene = PaperScene(sheet, ViewResolver(None, None, None, None))
    if template:
        scene.set_template(make_default_template(), {})
    return scene


def _fit(paper):
    w, h = PAPER_SIZES[paper]
    return min(w / PAGE_W_MM, h / PAGE_H_MM)


def _any_dark_near(img, x_mm, y_mm, px_per_mm, r_mm=1.0):
    r = int(r_mm * px_per_mm)
    cx, cy = int(x_mm * px_per_mm), int(y_mm * px_per_mm)
    return any(QColor(img.pixel(x, y)).red() < 80
               for x in range(cx - r, cx + r + 1)
               for y in range(cy - r, cy + r + 1))


def _has_colour(img, rect_mm: QRectF, px_per_mm, hex_colour):
    want = QColor(hex_colour).rgb()
    x0, y0 = int(rect_mm.left() * px_per_mm), int(rect_mm.top() * px_per_mm)
    x1, y1 = int(rect_mm.right() * px_per_mm), int(rect_mm.bottom() * px_per_mm)
    return any(img.pixel(x, y) == want
               for x in range(x0, x1) for y in range(y0, y1))


def test_linked_page_sits_between_paper_and_title_block(qapp):
    from firepro3d.paper_space import LinkedPageItem
    scene = _scene(make_link(TWO_PAGE, 1), template=True)
    w, h = PAPER_SIZES["ANSI D"]
    items = scene.items()
    pages = [i for i in items if isinstance(i, LinkedPageItem)]
    assert len(pages) == 1
    bg_z = [i.zValue() for i in items if isinstance(i, QGraphicsRectItem)
            and i.rect() == QRectF(0, 0, w, h)][0]
    tb_z = [i.zValue() for i in items if isinstance(i, TitleBlockTemplateItem)][0]
    assert bg_z < pages[0].zValue() < tb_z


@pytest.mark.parametrize("paper,mode,custom", [
    ("ANSI D", "fit", 1.0), ("ANSI D", "custom", 1.5),
    ("ANSI B", "fit", 1.0), ("A1", "fit", 1.0),
])
def test_page_paints_centred_at_scale(qapp, paper, mode, custom):
    scene = _scene(make_link(TWO_PAGE, 1, mode, custom), paper)
    sw, sh = PAPER_SIZES[paper]
    s = _fit(paper) if mode == "fit" else custom
    ox, oy = (sw - PAGE_W_MM * s) / 2, (sh - PAGE_H_MM * s) / 2
    img = render_scene(scene, sw, sh, 2.0)
    cx = ox + MARK_CX_PT * MM_PER_PT * s
    cy = oy + MARK_CY_PT * MM_PER_PT * s
    assert dark_at(img, cx, cy, 2.0)
    assert not dark_at(img, ox + MARK_RECT_PT[0] * MM_PER_PT * s - 4.0, cy, 2.0)


def test_linked_page_never_selected_or_dragged(qapp):
    from firepro3d.paper_space import LinkedPageBadge, LinkedPageItem
    scene = _scene(make_link(TWO_PAGE, 1), template=True)
    path = QPainterPath()
    path.addRect(QRectF(-20, -20, 1000, 700))
    scene.setSelectionArea(path)
    assert not [i for i in scene.selectedItems()
                if isinstance(i, (LinkedPageItem, LinkedPageBadge))]
    item = scene.linked_page_item()
    assert not item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    assert item.acceptedMouseButtons() == Qt.MouseButton.NoButton


def test_page_clipped_at_the_drawing_area_on_screen(qapp):
    sw, sh = PAPER_SIZES["ANSI D"]
    sl = solve_layout(make_default_template().layout, sw, sh, {})
    s = _fit("ANSI D")
    fx = (FRAME_RECT_PT[0] + FRAME_RECT_PT[2]) / 2 * MM_PER_PT * s
    fy = FRAME_RECT_PT[1] * MM_PER_PT * s           # frame top edge
    assert sl.strip_rect.contains(QPointF(fx, fy))
    clipped = render_scene(_scene(make_link(TWO_PAGE, 1), template=True),
                           sw, sh, 4.0)
    assert not _any_dark_near(clipped, fx, fy, 4.0)
    plain = render_scene(_scene(make_link(TWO_PAGE, 1)), sw, sh, 4.0)
    assert _any_dark_near(plain, fx, fy, 4.0)       # control: border area keeps it


def test_overlap_badge_reports_mm_and_shows_on_screen(qapp):
    sw, sh = PAPER_SIZES["ANSI D"]
    sl = solve_layout(make_default_template().layout, sw, sh, {})
    over = FRAME_RECT_PT[2] * MM_PER_PT * _fit("ANSI D") - sl.area_rect.right()
    scene = _scene(make_link(TWO_PAGE, 1), template=True)
    badge = scene.linked_badge()
    assert badge.isVisible()
    assert badge.text() == f"Page content overlaps the title block by {over:.0f} mm"
    img = render_scene(scene, sw, sh, 2.0)
    assert _has_colour(img, badge.sceneBoundingRect(), 2.0, LINKED_BADGE_FILL)


def test_word_missing_badge_for_a_docx_link(qapp, tmp_path, monkeypatch):
    from firepro3d import doc_converter
    src = build_fixture_pdf(tmp_path / "spec.pdf", 1)
    link = make_link(src, 1)
    docx = tmp_path / "spec.docx"
    docx.write_bytes(b"stand-in")                    # the file exists
    link.path = str(docx)
    link.snapshot_at = "2026-11-09T14:30:00"
    monkeypatch.setattr(doc_converter, "word_available", lambda: False)
    scene = _scene(link)
    assert scene.linked_badge().text() == (
        "Word not available - showing copy from 2026-11-09 14:30")


def test_paper_size_change_recomputes_the_placement(qapp):
    scene = _scene(make_link(TWO_PAGE, 1))
    scene.paper_size = "ANSI B"
    sw, sh = PAPER_SIZES["ANSI B"]
    s = _fit("ANSI B")
    img = render_scene(scene, sw, sh, 2.0)
    assert dark_at(img, MARK_CX_PT * MM_PER_PT * s, MARK_CY_PT * MM_PER_PT * s, 2.0)


def test_unlinked_sheet_adds_nothing(qapp):
    scene = _scene(None)
    assert scene.linked_page_item() is None and scene.linked_badge() is None


def _screen_ladder(needed):
    """The screen raster ladder from its raw constants (design Performance)."""
    from firepro3d.constants import (
        LINKED_PAGE_DPI_STEP, LINKED_PAGE_MIN_DPI, LINKED_PAGE_SCREEN_MAX_DPI)
    dpi = LINKED_PAGE_MIN_DPI
    while dpi < needed and dpi < LINKED_PAGE_SCREEN_MAX_DPI:
        dpi *= LINKED_PAGE_DPI_STEP
    return min(dpi, LINKED_PAGE_SCREEN_MAX_DPI)


@pytest.mark.parametrize("zoom", [0.5, 2.0, 8.0])
def test_screen_view_rasters_on_the_ladder_at_zoom(qapp, zoom):
    # T6 review: every other pixel test renders with widget=None (the print
    # branch). RED: paint passes screen=False -> zoom 2 gives the raw need
    # (101.6 dpi), not the ladder step 121.5; zoom 8 gives 400, not 300.
    from PyQt6.QtGui import QTransform
    from PyQt6.QtWidgets import QGraphicsView
    scene = _scene(make_link(TWO_PAGE, 1))
    view = QGraphicsView(scene)
    view.resize(400, 300)
    view.setTransform(QTransform.fromScale(zoom, zoom))
    view.centerOn(scene.linked_page_item().placement_rect().center())
    try:
        view.viewport().grab()
        dpr = view.viewport().devicePixelRatioF()
        needed = zoom * dpr * 25.4 * _fit("ANSI D")
        assert scene.linked_page_item().last_dpi == pytest.approx(
            _screen_ladder(needed))
    finally:
        view.setScene(None)
        view.deleteLater()


def test_screen_raster_follows_the_device_pixel_ratio(qapp):
    # A hi-dpi screen (dpr 2) needs twice the source dpi. RED: drop the dpr
    # factor -> 36 * ... ladder at 1x need (81 dpi) instead of 2x (182.25).
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem, QWidget
    scene = _scene(make_link(TWO_PAGE, 1))
    item = scene.linked_page_item()
    img = QImage(400, 300, QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(2.0)
    img.fill(0xFFFFFFFF)
    widget = QWidget()
    painter = QPainter(img)
    try:
        painter.scale(1.5, 1.5)               # 1.5 logical px per mm
        item.paint(painter, QStyleOptionGraphicsItem(), widget)
    finally:
        painter.end()
        widget.deleteLater()
    needed = 1.5 * 2.0 * 25.4 * _fit("ANSI D")
    assert item.last_dpi == pytest.approx(_screen_ladder(needed))
    assert item.last_dpi > _screen_ladder(needed / 2.0)
