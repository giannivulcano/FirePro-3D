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


class _Canvas:
    """Model-canvas stand-in whose project holds *registry* (hatch D-A39:
    patterns resolve through the project's block registry only)."""
    _hatch_paper_scale = None

    def __init__(self, registry=None):
        self.block_registry = registry


def _render(fill_type, colour="#ff0000", alpha=115, pattern="diagonal",
            mm_per_px=1.0, registry=None):
    """Fill a 40 px box; *mm_per_px* sets the world size it represents.

    Hatch tiles are world-scale (D-A30: Drafting tiles at an assumed 1:100 on
    the model canvas, so the diagonal's lines are 300 mm apart) — a hatch
    test must draw a box large enough in mm to contain a line.
    """
    img = QImage(50, 50, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    painter = QPainter(img)
    painter.scale(1.0 / mm_per_px, 1.0 / mm_per_px)
    path = _closed_rect_path(5 * mm_per_px, 5 * mm_per_px,
                             40 * mm_per_px, 40 * mm_per_px)
    draw_fill(painter, path, _Canvas(registry), fill_type, pattern, colour,
              alpha=alpha)
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


def test_hatch_fill_marks_some_interior_pixels(qapp, shipped_hatches):
    img = _render("hatch", "#000000", pattern="diagonal", mm_per_px=20.0,
                  registry=shipped_hatches())
    # at least some interior pixel differs from white (hatch lines present)
    found = any(img.pixelColor(x, 25) != QColor("white") for x in range(6, 44))
    assert found
