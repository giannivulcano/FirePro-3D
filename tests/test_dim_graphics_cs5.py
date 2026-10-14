"""CS5 graphics (D74 radial leader, D75 angular arc) -- real view, real paint."""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import dim_graphics as dg
from firepro3d import theme as th
from firepro3d.constants import DIM_LEADER_SHOULDER_PX
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


@pytest.fixture
def view(qapp):
    sc = Model_Space(scene_role="block_editor")
    v = Model_View(sc)
    v.resize(400, 300); v.show(); qapp.processEvents()
    v.resetTransform(); v.centerOn(0, 0); qapp.processEvents()
    yield v
    v.close()
    sc.cleanup()


def test_radius_leader_terminator_sits_on_the_curve(view):
    c, hit = QPointF(0, 0), QPointF(60, 0)
    g = dg.layout_radial(view, c, hit, "R 60")
    (tip, u), = g.terms
    H = view.mapFromScene(hit)
    assert (tip.x(), tip.y()) == pytest.approx((H.x(), H.y()), abs=0.5)
    assert u == pytest.approx((1.0, 0.0), abs=1e-9)
    (s, e), = g.segments
    assert e.x() - H.x() == pytest.approx(DIM_LEADER_SHOULDER_PX, abs=0.5)
    assert g.label.center.x() > e.x()


def test_diameter_leader_has_terminators_at_both_hits(view):
    g = dg.layout_radial(view, QPointF(0, 0), QPointF(0, -60), "\u00d8 120",
                         far=QPointF(0, 60))
    assert len(g.terms) == 2
    tips = sorted(round(t.y()) for t, _u in g.terms)
    F, H = view.mapFromScene(QPointF(0, 60)), view.mapFromScene(QPointF(0, -60))
    assert tips == sorted((round(F.y()), round(H.y())))


def test_arc_dim_hit_and_bounds(view):
    C = QPointF(view.mapFromScene(QPointF(0, 0)))
    g = dg.layout_arc_dim(view, QPointF(0, 0), 40.0, 0.0, 90.0, "90\u00b0",
                          dashed=[(QPointF(C.x() + 60, C.y()), QPointF(C.x() + 40, C.y()))])
    on = QPointF(C.x() + 40 * math.cos(math.radians(45)), C.y() - 40 * math.sin(math.radians(45)))
    off = QPointF(C.x() - 40, C.y())                          # 180 deg: outside the sweep
    assert dg.hit_dim(g, on) and not dg.hit_dim(g, off)
    b = dg.bounds(g)
    assert b.contains(on) and b.contains(QPointF(C.x() + 60, C.y()))
    assert g.label.arc_center is None                         # never the muted readout arc


def _paint(g, colour):
    img = QImage(400, 300, QImage.Format.Format_ARGB32)       # DPR 1: device px == logical px
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    dg.paint_dim(p, g, colour, th.detect())
    p.end()
    return img


def test_arc_dim_paints_solid_arc_and_dashed_muted_extension(view):
    C = QPointF(view.mapFromScene(QPointF(0, 0)))
    g = dg.layout_arc_dim(view, QPointF(0, 0), 40.0, 0.0, 90.0, "90\u00b0",
                          dashed=[(QPointF(C.x() + 90, C.y() + 0.5),
                                   QPointF(C.x() + 50, C.y() + 0.5))])
    col = QColor("#ff0000")             # far from both themes' muted token
    img = _paint(g, col)
    a = math.radians(30)
    ax, ay = int(C.x() + 40 * math.cos(a)), int(C.y() - 40 * math.sin(a))
    near = [img.pixelColor(ax + i, ay + j) for i in (-1, 0, 1) for j in (-1, 0, 1)]
    best = max(near, key=lambda q: q.red())
    assert best.red() > 120 and best.green() < 60 and best.blue() < 60   # arc: dim colour
    muted = th.detect().color("muted")
    hits = [img.pixelColor(x, int(C.y() + 0.5)) for x in range(int(C.x()) + 52, int(C.x()) + 88)]
    lit = [q for q in hits if q.value() > 40]
    assert lit and len(lit) < len(hits)                  # dashed: some lit, some gaps
    brightest = max(lit, key=lambda q: q.value())
    assert abs(brightest.blue() - muted.blue()) < 30     # muted, never the dim red
    assert abs(brightest.green() - muted.green()) < 30


def test_arc_end_terminators_point_outward_along_the_arc(view):
    g = dg.layout_arc_dim(view, QPointF(0, 0), 40.0, 0.0, 90.0, "90°")
    (t0, u0), (t1, u1) = g.terms
    assert u0 == pytest.approx((0.0, 1.0), abs=1e-9)     # at 0 deg: points down (CW, away)
    assert u1 == pytest.approx((-1.0, 0.0), abs=1e-9)    # at 90 deg: points left (CCW, away)
    assert t1.y() < t0.y()


def test_arc_hit_across_zero_degrees(view):
    C = QPointF(view.mapFromScene(QPointF(0, 0)))
    g = dg.layout_arc_dim(view, QPointF(0, 0), 40.0, 330.0, 60.0, "60°")

    def at(deg):
        r = math.radians(deg)
        return QPointF(C.x() + 40 * math.cos(r), C.y() - 40 * math.sin(r))
    assert dg.hit_dim(g, at(350)) and dg.hit_dim(g, at(10))
    assert not dg.hit_dim(g, at(180))
