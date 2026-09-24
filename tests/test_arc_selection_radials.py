"""Selected ArcItem paints dashed centre→start / centre→end radials
(smoke-test tweak 2026-09-24) without widening hit-testing."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.geometry_2d import ArcItem


@pytest.fixture
def arc(qapp):
    sc = QGraphicsScene()
    a = ArcItem(QPointF(0, 0), 100.0, 0.0, 90.0)      # quarter: (100,0)→(0,-100)
    sc.addItem(a)
    yield a
    sc.removeItem(a)


def _xy(p):
    return (round(p.x(), 6), round(p.y(), 6))


def test_ref_segments_are_centre_to_both_ends(arc):
    segs = arc._selection_ref_segments()
    assert [(_xy(a), _xy(b)) for a, b in segs] == [
        ((0.0, 0.0), (100.0, 0.0)), ((0.0, 0.0), (0.0, -100.0))]


def test_bounding_rect_includes_centre_only_when_selected(qapp):
    sc = QGraphicsScene()
    a = ArcItem(QPointF(0, 0), 100.0, 30.0, 30.0)     # centre far off the path
    sc.addItem(a)
    assert not a.boundingRect().contains(QPointF(0.0, 0.0))
    a.setSelected(True)
    assert a.boundingRect().contains(QPointF(0.0, 0.0))
    assert not a.shape().contains(QPointF(0.0, 0.0))
    a.setSelected(False)
    assert not a.boundingRect().contains(QPointF(0.0, 0.0))
    sc.removeItem(a)


def test_shape_excludes_centre_when_selected(arc):
    arc.setSelected(True)
    assert not arc.shape().contains(QPointF(0.0, 0.0))
    assert not arc.contains(QPointF(0.0, 0.0))
    assert not arc.contains(QPointF(20.0, -20.0))


def test_selected_paint_draws_radials(arc):
    """Render the selected arc and sample a pixel on the start radial."""
    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtCore import Qt
    arc.setSelected(True)
    img = QImage(240, 240, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    p.translate(120, 120)
    from PyQt6.QtWidgets import QStyleOptionGraphicsItem
    arc.paint(p, QStyleOptionGraphicsItem(), None)
    p.end()
    # Radial centre→start runs along y=0 from x=0..100 (image row 120).
    lit = [x for x in range(125, 215) if QColor(img.pixel(x, 120)).lightness() > 60]
    assert lit, "no radial pixels on the centre→start line"
    arc.setSelected(False)
