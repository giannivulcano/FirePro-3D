"""Unit tests for draw_fill() in displayable_item.py.

Renders into a QImage and asserts pixel-level correctness.
"""
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainterPath
from firepro3d.displayable_item import draw_fill


def _closed_rect_path(x, y, w, h):
    p = QPainterPath()
    p.addRect(QRectF(x, y, w, h))
    return p


def _render(fill_type, colour="#ff0000", alpha=115, pattern="diagonal"):
    img = QImage(50, 50, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    painter = QPainter(img)
    path = _closed_rect_path(5, 5, 40, 40)
    draw_fill(painter, path, None, fill_type, pattern, colour, alpha=alpha)
    painter.end()
    return img


def test_solid_fill_paints_semi_transparent_interior(qapp):
    img = _render("solid", "#ff0000", alpha=115)
    c = img.pixelColor(25, 25)
    # semi-transparent red over white -> reddish but not pure red (green/blue lifted)
    assert c.red() > 180
    assert c.green() > 60 and c.blue() > 60
    assert c != QColor("#ff0000")


def test_none_fill_leaves_background(qapp):
    img = _render("none")
    assert img.pixelColor(25, 25) == QColor("white")


def test_hatch_fill_marks_some_interior_pixels(qapp):
    img = _render("hatch", "#000000", pattern="diagonal")
    # at least some interior pixel differs from white (hatch lines present)
    found = any(img.pixelColor(x, 25) != QColor("white") for x in range(6, 44))
    assert found
