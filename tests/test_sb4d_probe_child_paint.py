"""SB4d P4 probe (e): an OutlinedLabel CHILD painted directly -- painter set
to the view mapping, then composed with the label's sceneTransform(), then
label.paint(painter, QStyleOptionGraphicsItem(), None) -- inks its block ops
where the scene puts the label (the D6 Model_View.drawForeground path)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QImage, QPainter, QTransform
from PyQt6.QtWidgets import QStyleOptionGraphicsItem

from firepro3d.gridline import GridlineItem
from tests._sb4d_helpers import HEAD_R, head_def, ink, is_red

BG = 0xFF101010


def test_p4_child_outlined_label_paints_under_its_scene_transform(qapp, model_scene):
    ms = model_scene()
    head_def(ms, "Gridline", colour="#ff0000", texts=(("Mark", -1.0),))
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 10000.0), label="A")
    ms._gridlines.append(gl)
    ms.addItem(gl)
    b = gl.bubble1                                  # an OutlinedLabel child of the gridline
    assert b.parentItem() is gl
    c = b.scenePos()
    k = ms.scale_manager.drawing_scale              # 100 (ScaleManager default) -> radius 500 scene mm
    rect = QRectF(c.x() - 1000.0, c.y() - 1000.0, 2000.0, 2000.0)   # 10 scene mm per px
    img = QImage(200, 200, QImage.Format.Format_RGB32)
    img.fill(BG)
    p = QPainter(img)
    t = QTransform()
    t.scale(200.0 / rect.width(), 200.0 / rect.height())
    t.translate(-rect.left(), -rect.top())
    p.setTransform(t)
    p.setTransform(b.sceneTransform(), True)
    b.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    pts = ink(img, is_red)
    assert pts, "the child label painted nothing"
    xs = [x for x, _y in pts]
    ys = [y for _x, y in pts]
    assert (min(xs) + max(xs)) / 2.0 == pytest.approx(100.0, abs=2.0)      # centred on its scene pos
    assert (min(ys) + max(ys)) / 2.0 == pytest.approx(100.0, abs=2.0)
    assert max(xs) - min(xs) == pytest.approx(2 * HEAD_R * k / 10.0, abs=3.0)   # 100 px: annotative k
