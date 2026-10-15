"""CS7 / CS8 glyphs (S3, SP2, FP3p) and target glow (spec §10, D27/D32)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import constraint_paint as cp
from firepro3d.geometry_2d import CircleItem, LineItem
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


def _circle(sc, c, r):
    it = CircleItem(QPointF(*c), r); sc.addItem(it); sc._draw_circles.append(it)
    return it


def _rects(v, ctl, cid):
    return [r for k, r in cp.glyph_layouts(v, ctl) if k == cid]


def test_symmetric_shows_one_glyph_beside_each_point(be):
    v, sc = be
    ctl = sc.constraint_ctl
    a = _line(sc, (-80, 0), (-40, 40)); b = _line(sc, (40, 40), (80, 0))
    c = ctl.add("symmetric", [{"uid": a._uid, "h": "p1"}, {"uid": b._uid, "h": "p2"},
                              {"ref": "y_axis"}])
    ctl.show_all = True
    ctl._repaint()
    rects = _rects(v, ctl, c.id)
    assert len(rects) == 2
    pa = QPointF(v.mapFromScene(a._pt1)); pb = QPointF(v.mapFromScene(b._pt2))

    def near(r, p):
        return (r.center() - p).manhattanLength() < 60
    assert any(near(r, pa) for r in rects) and any(near(r, pb) for r in rects)
    for r in rects:                                  # both glyphs pick the one constraint
        assert cp.glyph_at(v, ctl, r.center().toPoint()) == c.id


def test_symmetric_hover_glows_both_refs_and_the_axis(be):
    """S3 (T5 review Minor 1): hovering a Symmetric glows both points and
    the Y axis."""
    v, sc = be
    ctl = sc.constraint_ctl
    a = _line(sc, (-80, -20), (-40, 40)); b = _line(sc, (40, 40), (80, -20))
    c = ctl.add("symmetric", [{"uid": a._uid, "h": "p1"}, {"uid": b._uid, "h": "p2"},
                              {"ref": "y_axis"}])
    ctl.hover_id = c.id
    br = cp._glow_path(v, ctl, [(c.id, "selection_hover")]).boundingRect()
    pa = QPointF(v.mapFromScene(a._pt1)); pb = QPointF(v.mapFromScene(b._pt2))
    assert br.left() <= pa.x() and br.right() >= pb.x()          # both points
    vp = v.viewport().rect()
    assert br.top() <= vp.top() + 1 and br.bottom() >= vp.bottom() - 1   # the axis


def test_symmetric_circle_glyph_sits_up_right_of_each_centre(be):
    v, sc = be
    ctl = sc.constraint_ctl
    a = _circle(sc, (-60, 0), 20); b = _circle(sc, (60, 0), 20)
    c = ctl.add("symmetric", [{"uid": a._uid, "h": "curve"}, {"uid": b._uid, "h": "curve"},
                              {"ref": "y_axis"}])
    ctl.show_all = True
    ctl._repaint()
    rects = sorted(_rects(v, ctl, c.id), key=lambda r: r.center().x())
    assert len(rects) == 2
    for r, it in zip(rects, (a, b)):
        ctr = QPointF(v.mapFromScene(it._center))
        assert r.center().x() > ctr.x() and r.center().y() < ctr.y()


def test_fix_point_glyph_beside_the_point(be):
    v, sc = be
    ctl = sc.constraint_ctl
    ln = _line(sc, (-50, 0), (50, 0))
    c = ctl.add("fix", [{"uid": ln._uid, "h": "p1"}])
    ctl.show_all = True
    ctl._repaint()
    (r,) = _rects(v, ctl, c.id)
    p = QPointF(v.mapFromScene(ln._pt1))
    assert (r.center() - p).manhattanLength() < 60


def test_fix_whole_item_glyph_and_glow(be):
    v, sc = be
    ctl = sc.constraint_ctl
    ln = _line(sc, (0, 0), (120, 0))
    c = ctl.add("fix", [{"uid": ln._uid, "h": "item"}])
    ctl.show_all = True
    ctl._repaint()
    (r,) = _rects(v, ctl, c.id)
    mid = QPointF(v.mapFromScene(QPointF(60, 0)))
    assert (r.center() - mid).manhattanLength() < 60          # FP3p: the edge anchor
    path = cp._refs_path(v, c.refs, ctl.item_by_uid(), v.viewport().rect(),
                         QPointF(v.mapFromScene(QPointF(0, 0))))
    assert not path.isEmpty()
    br = path.boundingRect()
    assert br.width() >= 119                                  # the whole edge glows


def test_fix_whole_circle_glyph_up_right_of_its_bounds(be):
    v, sc = be
    ctl = sc.constraint_ctl
    it = _circle(sc, (0, 0), 30)
    c = ctl.add("fix", [{"uid": it._uid, "h": "item"}])
    ctl.show_all = True
    ctl._repaint()
    (r,) = _rects(v, ctl, c.id)
    tr = QPointF(v.mapFromScene(it.sceneBoundingRect().topRight()))
    assert r.center().x() > tr.x() and r.center().y() < tr.y()
