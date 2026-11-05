"""Shared builders for the block stacking guards."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem

SCALE = 2


def line_def(sc, name="Line", length=200.0):
    """A block of one horizontal line from its origin (open geometry)."""
    d = BlockDefinition.new(
        name=name, library="L", series="S",
        primitives=[LineItem(QPointF(0, 0), QPointF(length, 0)).to_dict()],
        origin=(0.0, 0.0))
    sc.register_block_definition(d)
    return d


def rect_def(sc, name="Rect", w=100.0, h=100.0):
    """A block of one closed rectangle with its corner at the origin."""
    d = BlockDefinition.new(
        name=name, library="L", series="S",
        primitives=[RectangleItem(QPointF(0, 0), QPointF(w, h)).to_dict()],
        origin=(0.0, 0.0))
    sc.register_block_definition(d)
    return d


def render(scene, view: QRectF) -> QImage:
    img = QImage(int(view.width() * SCALE), int(view.height() * SCALE),
                 QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(img.rect()), view)
    p.end()
    return img


def ink(scene, item, region: QRectF, view: QRectF) -> int:
    """Pixels of scene *region* that change when *item* is hidden: *item*'s
    own visible ink there, whatever the theme's colours. Hide only an item
    that does not cover anything being measured."""
    with_it = render(scene, view)
    item.setVisible(False)
    without = render(scene, view)
    item.setVisible(True)
    x0 = int((region.left() - view.left()) * SCALE)
    y0 = int((region.top() - view.top()) * SCALE)
    n = 0
    for y in range(y0, y0 + int(region.height() * SCALE)):
        for x in range(x0, x0 + int(region.width() * SCALE)):
            if with_it.pixel(x, y) != without.pixel(x, y):
                n += 1
    return n


def lines_def(sc, name, segments, rects=()):
    """A block of separate line ops (``segments`` = ``((x0, y0), (x1, y1))``
    pairs) and closed rectangles (``rects`` = ``(x0, y0, x1, y1)``): outlines
    with no closed shape of their own."""
    prims = [LineItem(QPointF(*a), QPointF(*b)).to_dict() for a, b in segments]
    prims += [RectangleItem(QPointF(x0, y0), QPointF(x1, y1)).to_dict()
              for x0, y0, x1, y1 in rects]
    d = BlockDefinition.new(name=name, library="L", series="S", primitives=prims,
                            origin=(0.0, 0.0))
    sc.register_block_definition(d)
    return d


# An L drawn as six separate line ops: a horizontal arm (x 0..100, y 0..40) and
# a vertical arm (x 0..40, y 0..100). Its bounding box corner (x 40..100,
# y 40..100) is empty.
L_SEGMENTS = [((0, 0), (100, 0)), ((100, 0), (100, 40)), ((100, 40), (40, 40)),
              ((40, 40), (40, 100)), ((40, 100), (0, 100)), ((0, 100), (0, 0))]


def l_def(sc, name="L"):
    return lines_def(sc, name, L_SEGMENTS)
