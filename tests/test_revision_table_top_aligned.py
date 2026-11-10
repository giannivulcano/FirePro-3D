"""The revision table header sits directly under the cell's label, not centred.

A cell sized for the template's full ``revision_rows`` with one entry used to
float the table mid-cell, leaving a gap under the REVISIONS label.
"""
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QGraphicsScene


def _scene(qapp):
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    from firepro3d.titleblock_template import make_default_template

    class _PM:
        _views = {}

        def get(self, n):
            return None

    sheet = Sheet.create_default()
    scene = PaperScene(sheet, ViewResolver(QGraphicsScene(), _PM(), None, None))
    scene.set_template(make_default_template(), project_info={})
    return scene, sheet


def test_row_text_is_vertically_centred_between_the_rules(qapp):
    """Ink of the 'Rev.' header has equal space above it and below it in its row."""
    from PyQt6.QtGui import QColor
    from firepro3d.constants import (
        TB_CELL_PAD_MM, TB_LABEL_ROW_MM, TB_REV_ROW_MM)

    scene, sheet = _scene(qapp)
    sheet.revisions.append({"no": "0", "description": "TEST", "date": "2026-11-09"})
    scene._refresh_titleblock()
    tb = scene._title_tb
    (idx,) = tb._layout.cell_revision_rows.keys()
    cell = tb._layout.cell_rects[idx]
    k = 10  # px per mm
    img = QImage(int(cell.width() * k), int(cell.height() * k),
                 QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.scale(k, k)
    p.translate(-cell.left(), -cell.top())
    tb.paint(p, None, None)
    p.end()

    row_top = cell.top() + TB_CELL_PAD_MM + TB_LABEL_ROW_MM    # header band top
    band_h = TB_REV_ROW_MM
    # "Rev." column: the left ~6 mm of the cell content (no descenders there).
    x0 = int((TB_CELL_PAD_MM + 1.0) * k)
    x1 = int((TB_CELL_PAD_MM + 7.0) * k)
    y0 = int((row_top - cell.top()) * k)
    y1 = int((row_top - cell.top() + band_h - 0.6) * k)   # stop above the rule
    ink = [y for y in range(y0, y1)
           if any(img.pixelColor(x, y).lightness() < 128 for x in range(x0, x1))]
    assert ink, "no header ink found in the Rev. column band"
    gap_above = (ink[0] - y0) / k
    gap_below = (y0 + band_h * k - ink[-1]) / k
    assert abs(gap_above - gap_below) < 0.45, (
        f"header text not centred in its row: {gap_above:.2f} mm above, "
        f"{gap_below:.2f} mm below")


def test_header_is_at_the_top_of_the_revision_cell(qapp, monkeypatch):
    from firepro3d.paper_space import TitleBlockTemplateItem as Item
    from firepro3d.constants import TB_CELL_PAD_MM, TB_LABEL_ROW_MM

    scene, sheet = _scene(qapp)
    sheet.revisions.append({"no": "0", "description": "TEST", "date": "2026-11-09"})
    scene._refresh_titleblock()
    tb = scene._title_tb
    lay = tb._layout

    seen = {}
    real = Item._draw_text_mm

    def rec(self, painter, rect, lines, f, **kw):
        if lines == ["Rev."]:
            seen["rect"] = QRectF(rect)
        return real(self, painter, rect, lines, f, **kw)

    monkeypatch.setattr(Item, "_draw_text_mm", rec)
    img = QImage(400, 300, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    tb.paint(p, None, None)
    p.end()

    assert "rect" in seen, "revision table header was not drawn"
    (idx,) = lay.cell_revision_rows.keys()
    cell = lay.cell_rects[idx]
    label_h = TB_LABEL_ROW_MM  # the default template's revision cell has a label
    top = cell.top() + TB_CELL_PAD_MM + label_h
    assert abs(seen["rect"].top() - top) < 0.01, (
        f"header at {seen['rect'].top():.2f} mm, expected {top:.2f} (cell top "
        f"{cell.top():.2f}); table is floating in the cell")
