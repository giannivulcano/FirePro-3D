"""SB4g T1 / T2 -- paint_ops fill_override; shared ops bounds / shape helper."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QTransform

from firepro3d import render_op as ro
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space

GREEN, BLUE = "#00ff00", "#0000ff"


def _host():
    """A real placed BlockInstance as the paint_ops item (its protocol)."""
    ms = Model_Space()
    d = BlockDefinition.new(name="h", library="", series="",
                            primitives=[LineItem(QPointF(0, 0), QPointF(1, 0)).to_dict()],
                            origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return ms, ms.place_block_instance(d.id, (0.0, 0.0), level="Level 1")


def _fill_op(keep=False):
    p = QPainterPath()
    p.addRect(QRectF(0, 0, 40, 40))
    return ro.RenderOp(ro.FILL, p, colour=GREEN, keep_colour=keep)


def _centre(ops, **kw):
    ms, inst = _host()
    img = QImage(40, 40, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    ro.paint_ops(p, ops, QTransform(), inst, **kw)
    p.end()
    return QColor(img.pixel(20, 20)).name()


def test_fill_override_recolours_fill_ops(qapp):
    assert _centre([_fill_op()]) == GREEN
    assert _centre([_fill_op()], fill_override=QColor(BLUE)) == BLUE


def test_fill_override_spares_keep_colour_ops(qapp):
    assert _centre([_fill_op(keep=True)], fill_override=QColor(BLUE)) == GREEN


def test_override_alone_leaves_fills(qapp):
    assert _centre([_fill_op()], override=QColor(BLUE)) == GREEN
