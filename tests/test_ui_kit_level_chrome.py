"""ui_kit.glyph_button + ui_kit.SortHeader (Level Manager chrome, mockup
docs/mockups/level-manager-tuner.html): a square house glyph button and an accent sort
caret painted after the header text, plus the M.LEVEL_* tokens pinned to the approved
mockup literals. Rendered under the real house dialog QSS."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

from firepro3d import theme as th
from firepro3d.house_dialog import HouseDialog
from firepro3d.theme import M
from firepro3d.ui_kit import SortHeader, glyph_button


def test_level_tokens_equal_the_approved_mockup():
    """docs/mockups/level-manager-tuner.html :root (approved 2026-10-30): --row-h:26px
    --head-pt:7.5pt --cell-pad:8px --tb-h:28px --tb-gap:8px --dlg-w:520px --dlg-h:460px
    --col-num:90px --col-elev:120px; .toolbar{margin-top:10px}. Min size = the
    pre-rewrite level_dialog.py setMinimumSize(420, 350)."""
    assert (M.LEVEL_ROW_H, M.LEVEL_CELL_PAD, M.LEVEL_COL_NUMBER_W, M.LEVEL_COL_ELEV_W) == (26, 8, 90, 120)
    assert M.LEVEL_DLG_SIZE == (520, 460) and M.LEVEL_DLG_MIN == (420, 350)
    assert (M.GLYPH_BTN_PX, M.GLYPH_BTN_GAP, M.LEVEL_TOOLBAR_TOP) == (28, 8, 10)
    assert M.TABLE_HEADER_PX == 10            # 7.5pt @ 96 dpi


def test_glyph_button_is_square_tagged_and_wired(qapp):
    hits = []
    b = glyph_button("+", "Add level", lambda: hits.append(1))
    assert b.property("glyph") is True
    assert (b.width(), b.height()) == (M.GLYPH_BTN_PX, M.GLYPH_BTN_PX)
    assert b.toolTip() == "Add level" and b.text() == "+"
    b.click()
    assert hits == [1]


def _accent_pixels(img, x0, x1, accent: QColor) -> int:
    """Pixels within 12 (sum of channel deltas) of the accent: the caret's interior is the
    exact fill; ClearType text fringes sit further away (probe: 13 fringe pixels at < 60)."""
    n = 0
    for x in range(x0, x1):
        for y in range(img.height()):
            c = img.pixelColor(x, y)
            if (abs(c.red() - accent.red()) + abs(c.green() - accent.green())
                    + abs(c.blue() - accent.blue())) < 12:
                n += 1
    return n


def test_sort_header_paints_an_accent_caret_only_on_the_sort_section(qapp):
    t = th.detect()
    dlg = HouseDialog(None, title="T")
    table = QTableWidget(2, 2, dlg)
    table.setHorizontalHeaderLabels(["Name", "Elevation"])
    hdr = SortHeader(table)
    table.setHorizontalHeader(hdr)
    hdr.set_view_sorting(table, True)
    for r, (a, b) in enumerate((("x", "1"), ("y", "2"))):
        table.setItem(r, 0, QTableWidgetItem(a)); table.setItem(r, 1, QTableWidgetItem(b))
    table.setColumnWidth(0, 250); table.setColumnWidth(1, 250)
    dlg.body_layout().addWidget(table)
    dlg.resize(600, 200); dlg.show(); qapp.processEvents()
    table.sortByColumn(1, Qt.SortOrder.AscendingOrder); qapp.processEvents()
    assert hdr.isSortIndicatorShown() is False          # native arrow stays hidden after setSortingEnabled
    accent = t.color("accent")
    img = hdr.grab().toImage()
    s0 = hdr.sectionViewportPosition(0); s1 = hdr.sectionViewportPosition(1)
    assert _accent_pixels(img, s0, s0 + hdr.sectionSize(0), accent) == 0
    assert _accent_pixels(img, s1, s1 + hdr.sectionSize(1), accent) >= 4
    # The caret sits right after the text: nothing accent before text end + gap, caret within 12 px of it.
    from PyQt6.QtGui import QFont, QFontMetrics
    f = QFont(hdr.font()); f.setPixelSize(M.TABLE_HEADER_PX); f.setWeight(QFont.Weight.DemiBold)
    x_caret = s1 + M.TABLE_HEADER_PAD_X + QFontMetrics(f).horizontalAdvance("Elevation") + M.SORT_CARET_GAP
    assert _accent_pixels(img, s1, x_caret, accent) == 0
    assert _accent_pixels(img, x_caret, x_caret + M.SORT_CARET_W + 2, accent) >= 4
    # Flipping the sort column moves the caret to the other section.
    table.sortByColumn(0, Qt.SortOrder.AscendingOrder); qapp.processEvents()
    img = hdr.grab().toImage()
    assert _accent_pixels(img, s0, s0 + hdr.sectionSize(0), accent) >= 4
    assert _accent_pixels(img, s1, s1 + hdr.sectionSize(1), accent) == 0
    dlg.close()
