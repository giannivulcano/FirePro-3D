"""Heavy cosmetic strokes paint inside boundingRect at any zoom.

Qt invalidates an item's old position by its boundingRect (+ the view's 2 px
margin); ink outside it is left behind as a trail. Real shown view, real items,
the panel-reachable style weight; assert painted ink lies inside the item's
boundingRect mapped to viewport pixels.
"""
import numpy as np
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QGraphicsView

from firepro3d import geometry_2d as g2
from firepro3d import paper_display as pd
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef

_KINDS = ["Rect", "Circle", "Line", "Arc", "Polyline", "Polygon",
          "Ellipse", "Spline"]


def _make(kind):
    if kind == "Rect":
        return g2.RectangleItem(QPointF(-1000, -1000), QPointF(1000, 1000))
    if kind == "Circle":
        return g2.CircleItem(QPointF(0, 0), 1000.0)
    if kind == "Line":
        return g2.LineItem(QPointF(-1000, 0), QPointF(1000, 0))
    if kind == "Arc":
        return g2.ArcItem(QPointF(0, 0), 1000.0, 0.0, 180.0)
    if kind == "Polyline":
        it = g2.PolylineItem(QPointF(-1000, -1000))
        it.append_point(QPointF(1000, -1000))
        it.append_point(QPointF(1000, 1000))
        return it
    if kind == "Polygon":
        return g2.RegularPolygonItem(QPointF(0, 0), 6, 1000.0)
    if kind == "Ellipse":
        return g2.EllipseItem(QPointF(0, 0), 1000.0, 600.0)
    return g2.SplineItem([QPointF(-1000, 0), QPointF(-300, 800),
                          QPointF(300, -800), QPointF(1000, 0)])


def _ink_bbox(img: QImage):
    img = img.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, img.bytesPerLine())
    red = arr[:, : w * 4].reshape(h, w, 4)[:, :, 2]
    ys, xs = np.nonzero(red > 128)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("zoom", [0.15, 0.06])
@pytest.mark.parametrize("kind", _KINDS)
def test_heavy_stroke_ink_inside_bounds(qapp, request, kind, zoom, selected):
    if kind in ("Spline", "Polygon") and selected:
        # Pre-existing, weight-independent: selection reference guides (spline
        # control polygon, polygon circumcircle) paint outside boundingRect
        # (todo_open.md, "Selection reference guides paint outside bounds").
        # Non-strict: the pen pad covers the polygon circle at some zooms.
        request.applymarker(pytest.mark.xfail(
            strict=False, reason="selection reference guide outside bounds"))
    pd.set_project_line_weights([*pd.project_line_weights(),
                                 LineWeightDef("Huge", 3.0)])
    ms = Model_Space()
    ms.setBackgroundBrush(QColor("black"))
    it = _make(kind)
    ms.addItem(it)
    it.style["weight"] = "Huge"
    it.style["colour"] = "#ffffff"
    it.setSelected(selected)
    v = QGraphicsView(ms)
    try:
        v.resize(400, 400)
        v.setTransform(v.transform().fromScale(zoom, zoom))
        v.centerOn(0, 0)
        v.show()
        qapp.processEvents()
        img = v.viewport().grab().toImage()
        assert it.pen().widthF() > 10.0, it.pen().widthF()   # heavy pen really built
        br = v.mapFromScene(
            it.sceneTransform().mapRect(it.boundingRect())).boundingRect()
        x0, y0, x1, y1 = _ink_bbox(img)
        over = max(br.left() - x0, br.top() - y0,
                   x1 - br.right(), y1 - br.bottom())
        assert over <= 1, (kind, zoom, selected, (x0, y0, x1, y1), br, over)
    finally:
        v.close()


def test_text_item_content_rect_is_unpadded(qapp):
    """TextItem shares Geometry2DMixin but has no pen: its content measurement
    (``super().boundingRect()``) must stay the raw QGraphicsTextItem rect."""
    from PyQt6.QtWidgets import QGraphicsTextItem
    from firepro3d.text_item import TextAnnotationData, TextItem
    ms = Model_Space()
    t = TextItem(TextAnnotationData(text="T", x=0.0, y=0.0, height_mm=20.0))
    ms.addItem(t)
    assert (super(TextItem, t).boundingRect()
            == QGraphicsTextItem.boundingRect(t))
