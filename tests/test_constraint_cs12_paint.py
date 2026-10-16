"""CS12 Tangent glyphs (T4): one beside each ref (the edge and the circle / arc)."""
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


def test_tangent_shows_one_glyph_beside_the_edge_and_one_by_the_circle(be):
    from firepro3d.geometry_2d import CircleItem
    v, sc = be
    ctl = sc.constraint_ctl
    ln = _line(sc, (-200, -50), (0, -50))
    k = CircleItem(QPointF(150, 0), 40); sc.addItem(k); sc._draw_circles.append(k)
    c = ctl.add("tangent", [{"uid": ln._uid, "h": "edge"}, {"uid": k._uid, "h": "curve"}])
    ctl.show_all = True
    ctl._repaint()
    rects = _rects(v, ctl, c.id)
    assert len(rects) == 2
    assert any(_near(r, v, ln) for r in rects)                     # one by the line
    vk = v.mapFromScene(k._center)
    xs = sorted(r.center().x() for r in rects)
    assert abs(xs[1] - vk.x()) < abs(xs[1] - xs[0])                # one by the circle
    for r in rects:
        assert cp.glyph_at(v, ctl, r.center().toPoint()) == c.id

