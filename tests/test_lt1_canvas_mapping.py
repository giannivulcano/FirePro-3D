"""LT1-7 / LT1-8 — one mm->canvas-px mapping; Thin Lines = 1 px (guard T7)."""
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d import paper_display as pd
from firepro3d.paper_display import LineWeightDef
from firepro3d.text_item import TextAnnotationData, TextItem


@pytest.mark.parametrize("mm,px", [(0.13, 0.78), (0.18, 1.0), (0.25, 1.5),
                                   (0.35, 2.1), (0.50, 3.0)])
def test_mapping_table(mm, px):
    assert pd.canvas_weight_px(mm) == pytest.approx(px, abs=1e-6)


def test_thin_lines_forces_one_px():
    pd.set_thin_lines(True)
    assert pd.canvas_weight_px(0.50) == 1.0
    assert pd.thin_lines() is True


def _border_thickness_px(weight_name):
    """Render a bordered model-surface TextItem; dark-run across its left border."""
    sc = QGraphicsScene()
    item = TextItem(TextAnnotationData(text="WWWW", border=True,
                                       border_weight=weight_name,
                                       color="#000000", height_mm=40.0))
    sc.addItem(item)
    r = item.sceneBoundingRect()
    img = QImage(400, 400, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    sc.render(p, QRectF(0, 0, 400, 400), r.adjusted(-20, -20, 20, 20))
    p.end()
    return img


def _left_border_run(img):
    # Row 100 crosses the box's left border (leftmost dark run; glyphs start
    # well right of it, so the first run is border-only).
    y = 100
    best = run = 0
    for x in range(0, 200):
        if QColor(img.pixel(x, y)).lightness() < 128:
            run += 1
            best = max(best, run)
        elif best:
            break
    return best


def test_custom_border_weight_maps_mm_times_hint(qapp):
    """T7: a custom 0.80 mm weight draws ~4.8 px (pre-LT1: unknown name -> 1 px)."""
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("Fat", 0.80)])
    assert 4 <= _left_border_run(_border_thickness_px("Fat")) <= 6


def test_thin_lines_border_is_one_px(qapp):
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("Fat", 0.80)])
    pd.set_thin_lines(True)
    assert _left_border_run(_border_thickness_px("Fat")) <= 2
