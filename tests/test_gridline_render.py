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


def test_grip_uses_house_selection_style(qapp):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor
    from firepro3d.gridline import GridlineItem
    from firepro3d.constants import SELECTION_OUTLINE_COLOR
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000), label="A")
    grip = gl._grip1
    # white fill
    assert grip.brush().color() == QColor(Qt.GlobalColor.white)
    # SELECTION_OUTLINE_COLOR outline (a real pen, not NoPen)
    assert grip.pen().style() != Qt.PenStyle.NoPen
    assert grip.pen().color().name().lower() == QColor(SELECTION_OUTLINE_COLOR).name().lower()


def test_duplicate_warning_keeps_border_width(qapp):
    from PyQt6.QtCore import QPointF
    from firepro3d.gridline import GridlineItem
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000), label="A")
    w_before = gl.bubble1.pen().widthF()
    gl.update_duplicate_warning(True)
    assert gl.bubble1.pen().widthF() == w_before   # only color changes
    assert gl.bubble1.pen().color().name() == "#ff8800"
