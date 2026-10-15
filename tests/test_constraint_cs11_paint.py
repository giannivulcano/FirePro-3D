"""CS11 Equal glyphs (E5): one beside each ref (edges and circles / arcs)."""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import constraint_paint as cp
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager


@pytest.fixture
def be(qapp):
    """(view, scene) -- shown Block Editor scene at 1 px / mm, centred
    (the tests/test_constraint_paint.py fixture)."""
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(800, 600)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    sc.set_mode("select")
    QApplication.processEvents()
    yield v, sc
    sc.clearSelection()
    sc.cleanup()
    v.close()
    v.deleteLater()
    QApplication.processEvents()


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _rects(v, ctl, cid):
    return [r for k, r in cp.glyph_layouts(v, ctl) if k == cid]


def _near(rect, v, ln):
    mid = QPointF(v.mapFromScene((ln._pt1 + ln._pt2) / 2))
    return math.dist((rect.center().x(), rect.center().y()), (mid.x(), mid.y())) < 40


def test_equal_shows_one_glyph_beside_each_edge(be):
    v, sc = be
    ctl = sc.constraint_ctl
    a = _line(sc, (-100, -80), (100, -80)); b = _line(sc, (150, -100), (150, 100))
    c = ctl.add("equal", [{"uid": a._uid, "h": "edge"}, {"uid": b._uid, "h": "edge"}])
    ctl.show_all = True
    ctl._repaint()
    rects = _rects(v, ctl, c.id)
    assert len(rects) == 2
    assert _near(rects[0], v, a) and _near(rects[1], v, b)
    for r in rects:
        assert cp.glyph_at(v, ctl, r.center().toPoint()) == c.id


def test_equal_shows_one_glyph_per_circle(be):
    from firepro3d.geometry_2d import CircleItem
    v, sc = be
    ctl = sc.constraint_ctl
    k1 = CircleItem(QPointF(-150, 0), 40); sc.addItem(k1); sc._draw_circles.append(k1)
    k2 = CircleItem(QPointF(150, 0), 30); sc.addItem(k2); sc._draw_circles.append(k2)
    c = ctl.add("equal", [{"uid": k1._uid, "h": "curve"}, {"uid": k2._uid, "h": "curve"}])
    ctl.show_all = True
    ctl._repaint()
    rects = _rects(v, ctl, c.id)
    assert len(rects) == 2
    xs = sorted(r.center().x() for r in rects)
    vc1, vc2 = v.mapFromScene(k1._center), v.mapFromScene(k2._center)
    assert xs[0] < (vc1.x() + vc2.x()) / 2 < xs[1]                  # one by each circle
