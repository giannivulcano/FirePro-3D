from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsScene
from firepro3d.gridline import GridlineItem, _dash_pattern_px


def test_dash_pattern_helper_scales_inversely_with_scale():
    fine = _dash_pattern_px(sx=1.0)
    coarse = _dash_pattern_px(sx=0.1)
    assert coarse[0] > fine[0]           # dash grows in scene units as you zoom out
    assert all(v > 0 for v in fine)


def test_paint_uses_dash_pattern_not_solid(qapp):
    scene = QGraphicsScene()
    gl = GridlineItem(QPointF(0, 0), QPointF(1000, 0), label="1")
    scene.addItem(gl)
    pen = gl._build_line_pen(sx=1.0)
    assert pen.style().name != "SolidLine"
    assert len(pen.dashPattern()) >= 2
