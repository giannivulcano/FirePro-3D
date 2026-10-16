"""CS14 Collinear glyphs (C4.2): one beside each edge, none on an axis."""
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


def test_collinear_shows_one_glyph_beside_each_edge(be):
    v, sc = be
    ctl = sc.constraint_ctl
    a = _line(sc, (-250, 0), (-100, 0)); b = _line(sc, (100, 0), (250, 0))
    c = ctl.add("collinear", [{"uid": a._uid, "h": "edge"}, {"uid": b._uid, "h": "edge"}])
    ctl.show_all = True
    ctl._repaint()
    rects = _rects(v, ctl, c.id)
    assert len(rects) == 2
    assert any(_near(r, v, a) for r in rects) and any(_near(r, v, b) for r in rects)
    for r in rects:
        assert cp.glyph_at(v, ctl, r.center().toPoint()) == c.id


def test_collinear_with_an_axis_shows_one_glyph(be):
    v, sc = be
    ctl = sc.constraint_ctl
    a = _line(sc, (50, 0), (200, 0))
    c = ctl.add("collinear", [{"uid": a._uid, "h": "edge"}, {"ref": "x_axis"}])
    ctl.show_all = True
    ctl._repaint()
    rects = _rects(v, ctl, c.id)
    assert len(rects) == 1 and _near(rects[0], v, a)
