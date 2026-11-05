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
