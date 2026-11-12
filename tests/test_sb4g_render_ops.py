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


import pytest

from firepro3d.geometry_2d import CircleItem

# Raw source for the ring: sprinkler0.svg / water_supply.svg circle r = 9.51192
# (viewBox 20) x K = 609.6 / 20 (TARGET_MM 24 in at 119fbbf0) = 289.923 mm.
K = 24.0 * 25.4 / 20.0
RING_R = 9.51192 * K


def _defn(*prims):
    return BlockDefinition.new(name="b", library="", series="",
                               primitives=[p.to_dict() for p in prims], origin=(0.0, 0.0))


def _ring_and_line_defn():
    """The sprinkler0 ring plus a short inner line (+-100 on y = 0), both at
    the default By Linetype weight (R14)."""
    return _defn(CircleItem(QPointF(0.0, 0.0), RING_R),
                 LineItem(QPointF(-100.0, 0.0), QPointF(100.0, 0.0)))


def test_ops_bounding_rect_is_the_centre_line_extent(qapp):
    r = ro.ops_bounding_rect(_ring_and_line_defn().render_ops())
    assert r.width() == pytest.approx(2 * RING_R, abs=0.01)      # 579.847
    assert r.height() == pytest.approx(2 * RING_R, abs=0.01)
    assert r.center().x() == pytest.approx(0.0, abs=1e-6)
    lr = ro.ops_bounding_rect(
        _defn(LineItem(QPointF(-100.0, 0.0), QPointF(100.0, 0.0))).render_ops())
    assert (lr.left(), lr.right(), lr.height()) == (-100.0, 100.0, 0.0)   # no stroke pad


def test_ops_shape_is_solid_for_closed_paths(qapp):
    s = ro.ops_shape(_ring_and_line_defn().render_ops())
    assert s.contains(QPointF(200.0, 50.0))            # inside the ring (winding fill)
    assert not s.contains(QPointF(RING_R + 5.0, 0.0))


def test_block_instance_local_path_is_ops_path(qapp):
    ms = Model_Space()
    d = _ring_and_line_defn()
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level="Level 1")
    assert inst._local_path().boundingRect() == ro.ops_path(inst.render_ops()).boundingRect()
