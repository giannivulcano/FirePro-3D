"""SV2 Task 1 -- raw primitives and text inside a viewport scene plot on
paper (schematics.md D-S12)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.geometry_2d import (EllipseItem, LineItem, RegularPolygonItem,
                                   SplineItem)
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import (PaperColorMode, apply_paper_overrides,
                                     restore_model_display,
                                     save_paper_color_mode)
from firepro3d.text_item import TextAnnotationData, TextItem

_CROP = QRectF(-60, -60, 120, 120)


def _render(scene):
    """Render *scene* through the paper override pass at 1 paper mm / model mm
    onto a 5 px/mm white image (the SheetViewport.paint recipe)."""
    img = QImage(600, 600, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.scale(5, 5)
    saved = apply_paper_overrides(scene, _CROP, paper_scale=1.0,
                                  source_view_key="schematic:x")
    try:
        scene.render(p, QRectF(0, 0, 120, 120), _CROP)
    finally:
        restore_model_display(saved)
    p.end()
    return img


def _count(img, pred):
    return sum(1 for y in range(0, img.height(), 2)
               for x in range(0, img.width(), 2)
               if pred(QColor(img.pixel(x, y))))


def _scene_with(item, list_attr):
    sc = Model_Space(scene_role="block_editor")
    sc.addItem(item)
    getattr(sc, list_attr).append(item)
    return sc


@pytest.mark.parametrize("make,attr", [
    (lambda: EllipseItem(QPointF(0, 0), 40.0, 20.0), "_draw_ellipses"),
    (lambda: SplineItem([QPointF(-40, 0), QPointF(-10, 30),
                         QPointF(10, -30), QPointF(40, 0)]), "_draw_splines"),
    (lambda: RegularPolygonItem(QPointF(0, 0), sides=6, radius_mm=40.0),
     "_draw_polygons"),
    (lambda: LineItem(QPointF(-40, 0), QPointF(40, 0)), "_draw_lines"),
])
def test_raw_primitive_plots_dark_on_bw_paper(qapp, make, attr):
    save_paper_color_mode(PaperColorMode.BW)
    img = _render(_scene_with(make(), attr))
    assert _count(img, lambda c: c.lightness() < 128) > 20


def test_text_in_viewport_scene_renders(qapp):
    save_paper_color_mode(PaperColorMode.BW)
    t = TextItem(TextAnnotationData(text="RISER"))
    t.setPos(-30, 0)
    img = _render(_scene_with(t, "_texts"))         # raised TypeError before
    assert _count(img, lambda c: c.name() != "#ffffff") > 20
