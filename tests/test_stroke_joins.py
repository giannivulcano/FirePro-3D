"""Stroke corner joins (design 2026-11-03-stroke-corner-joins-design.md).

Section A: P4 probes of the Qt facts the build rests on (pass at base).
Section B+: guards 1-8 (RED at base c20d2ec3).
"""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsLineItem, QGraphicsPathItem

from firepro3d.geometry_2d import LineItem, PolylineItem
from firepro3d.model_space import Model_Space


# ---------------------------------------------------------------- A. probes
def test_p4_python_setline_override_sees_every_setline_call(qapp):
    """Geometry2DMixin precedes QGraphicsLineItem in the MRO, so a Python
    `setLine` on the mixin intercepts every `self.setLine(...)` call made
    from Python (apply_grip, translate, rotate, set_length, __init__)."""
    seen = []

    class Probe(LineItem):
        def setLine(self, *a):
            seen.append(a)
            super().setLine(*a)

    ln = Probe(QPointF(0, 0), QPointF(10, 0))
    ln.apply_grip(2, QPointF(20, 0))
    ln.set_length(5.0)
    assert len(seen) == 3           # __init__, apply_grip, set_length


def test_p4_item_scene_has_changed_fires_without_geometry_flag(qapp):
    seen = []

    class Probe(LineItem):
        def itemChange(self, change, value):
            seen.append(change)
            return super().itemChange(change, value)

    sc = Model_Space(); ln = Probe(QPointF(0, 0), QPointF(10, 0))
    sc.addItem(ln); sc.removeItem(ln)
    gc = ln.GraphicsItemChange
    assert seen.count(gc.ItemSceneHasChanged) == 2
    sc.cleanup()


def test_p4_qt_miter_limit_2_equals_pdf_ratio_4(qapp):
    """A 20 deg corner (ratio 1/sin(10 deg) = 5.76 > 4) is bevelled under Qt
    limit 2 and mitered under Qt limit 4 -- Qt measures the tip's reach from
    the join point in pen widths, i.e. PDF ratio / 2 (design AC5)."""
    def tip_reach(limit):
        p = QPainterPath(QPointF(0, 100)); p.lineTo(QPointF(0, 0))
        a = math.radians(20.0); p.lineTo(QPointF(100 * math.sin(a), 100 * math.cos(a)))
        st = QPainterPathStroker(); st.setWidth(20.0)
        st.setJoinStyle(Qt.PenJoinStyle.MiterJoin); st.setMiterLimit(limit)
        st.setCapStyle(Qt.PenCapStyle.FlatCap)
        return -st.createStroke(p).boundingRect().top()      # reach above the apex
    # Measured at base: Qt does NOT bevel past the limit, it clips the miter
    # (reach grows ~linearly with the limit: 1 -> 22, 2 -> 41, 2.5 -> 50) and
    # reaches the full tip (half_w / sin(10 deg) ~ 56.7 after flat-cap box) from
    # limit 3 up, i.e. the full-miter threshold is ratio/2 = 2.88.
    full = tip_reach(8.0)
    assert full > 50.0
    assert tip_reach(2.0) < full - 5.0    # clipped below the full tip
    assert tip_reach(2.5) < full - 5.0    # still clipped just under ratio/2
    assert tip_reach(3.0) > full - 0.1    # full miter once limit >= ratio/2
    assert tip_reach(4.0) > full - 0.1


def test_p4_flat_cap_line_paints_exactly_between_its_endpoints(qapp):
    img = QImage(300, 100, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
    p = QPainter(img); pen = QPen(QColor("black"), 6.0)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap); p.setPen(pen)
    p.drawLine(QPointF(50, 50), QPointF(250, 50)); p.end()
    dark = [x for x in range(300) if img.pixelColor(x, 50).red() < 128]
    assert (min(dark), max(dark)) == (50, 249)


# ---------------------------------------------------------------- B. pens (D1)
from firepro3d import constants as C
from firepro3d.stroke_style import stroke_pen


def test_stroke_pen_is_flat_miter_qt_limit_2(qapp):
    pen = stroke_pen("#ff00ff", 6.0)
    assert pen.capStyle() == Qt.PenCapStyle.FlatCap
    assert pen.joinStyle() == Qt.PenJoinStyle.MiterJoin
    assert pen.miterLimit() == pytest.approx(C.STROKE_MITER_LIMIT / 2.0)
    assert pen.isCosmetic() and pen.widthF() == 6.0
    assert stroke_pen("#ff00ff", 0.5, cosmetic=False).isCosmetic() is False


def _render(items, size=(300, 200), weight_px=20.0, monkeypatch=None):
    """Render *items* in a Model_Space onto a QImage, identity view transform,
    canvas pens patched to *weight_px* (exaggerated so geometry is legible)."""
    import firepro3d.geometry_2d as g2
    if monkeypatch is not None:
        monkeypatch.setattr(g2, "canvas_px", lambda w: weight_px)
    sc = Model_Space(); sc.set_mode("select")
    for it in items:
        it.style["colour"] = "#000000"
        sc.addItem(it); sc._draw_lines.append(it)
    img = QImage(*size, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    from PyQt6.QtCore import QRectF
    sc.render(p, QRectF(0, 0, *size), QRectF(0, 0, *size))
    p.end(); sc.cleanup()
    return img


def _dark(img, thr=128):
    return {(x, y) for x in range(img.width()) for y in range(img.height())
            if img.pixelColor(x, y).red() < thr}


def test_g1_lone_line_dark_extent_equals_endpoints(qapp, monkeypatch):
    """AC1: a free end stops flat -- no dark pixel before x=50 or at/after x=250."""
    img = _render([LineItem(QPointF(50, 100), QPointF(250, 100))], monkeypatch=monkeypatch)
    xs = sorted({x for x, _ in _dark(img)})
    assert (xs[0], xs[-1]) == (50, 249)


# ---------------------------------------------------------------- C. joint_wedge (D2)
from firepro3d.stroke_joints import joint_wedge


def _dir(deg):
    a = math.radians(deg); return (math.cos(a), math.sin(a))


def _pts(poly):
    return [(round(poly.at(i).x(), 6), round(poly.at(i).y(), 6)) for i in range(poly.count())]


def _oracle_outline(deg, limit_qt, w=20.0):
    """Stroker outline of A (arriving along +y into the origin) then B at *deg*."""
    p = QPainterPath(QPointF(0, 100)); p.lineTo(QPointF(0, 0))
    a = math.radians(deg); p.lineTo(QPointF(100 * math.sin(a), 100 * math.cos(a)))
    st = QPainterPathStroker(); st.setWidth(w)
    st.setJoinStyle(Qt.PenJoinStyle.MiterJoin); st.setMiterLimit(limit_qt)
    st.setCapStyle(Qt.PenCapStyle.FlatCap)
    return st.createStroke(p)


def test_p4_qt_clip_rule_is_limit_times_width_along_the_edge_extension(qapp):
    """Derived 2026-11-03 (20 deg, width 20): Qt clips the miter with a chord
    whose end points lie on the two outer edges, extended past the join point,
    at distance limit_qt * width from the join point (the foot of the flat
    end) -- reach (bbox top) 22.2 / 31.6 / 41.0 / 50.4 at limit 1 / 1.5 / 2 /
    2.5. Not measured from the inner corner."""
    want_reach = {1.0: 22.214, 1.5: 31.611, 2.0: 41.008, 2.5: 50.405}
    for lim, reach in want_reach.items():
        o = _oracle_outline(20.0, lim)
        assert -o.boundingRect().top() == pytest.approx(reach, abs=0.01)
        pts = [(o.elementAt(i).x, o.elementAt(i).y) for i in range(o.elementCount())]
        # A's outer edge (x = -10) continues past the corner to y = -limit * width
        assert any(abs(x + 10.0) < 1e-3 and abs(y + lim * 20.0) < 1e-3 for x, y in pts)


@pytest.mark.parametrize("deg,n,tip_reach", [
    (90.0, 4, math.sqrt(2.0)),              # square corner: tip at half_w*sqrt2
    (60.0, 4, 1.0 / math.sin(math.radians(30))),
    (30.0, 4, 1.0 / math.sin(math.radians(15))),   # edge reach 3.73 < 4: still mitered
    (28.0, 5, None),                        # edge reach 4.01 > 4: clipped miter
    (20.0, 5, None),
])
def test_joint_wedge_table(deg, n, tip_reach):
    w = joint_wedge(QPointF(0, 0), _dir(0.0), _dir(deg), 1.0)
    assert w is not None and w.count() == n
    pts = _pts(w)
    assert pts[0] == (0.0, 0.0)                       # the corner
    if tip_reach is not None:
        tip = w.at(2)
        assert math.hypot(tip.x(), tip.y()) == pytest.approx(tip_reach, abs=1e-6)
        # tip lies on the exterior bisector: opposite to d_a + d_b
        bx, by = -(1.0 + math.cos(math.radians(deg))), -math.sin(math.radians(deg))
        assert math.atan2(tip.y(), tip.x()) == pytest.approx(math.atan2(by, bx), abs=1e-9)


@pytest.mark.parametrize("deg", [28.0, 20.0, 10.0])
def test_joint_wedge_clipped_reach_matches_stroker_oracle(deg):
    """Past the limit the wedge reaches exactly as far as the Qt-clipped miter
    (oracle: MiterJoin, FlatCap, Qt limit = STROKE_MITER_LIMIT / 2)."""
    o = _oracle_outline(deg, C.STROKE_MITER_LIMIT / 2.0)
    a = math.radians(deg)
    w = joint_wedge(QPointF(0, 0), (0.0, 1.0), (math.sin(a), math.cos(a)), 10.0)
    assert w is not None and w.count() == 5
    reach = -min(w.at(i).y() for i in range(w.count()))
    assert reach == pytest.approx(-o.boundingRect().top(), abs=0.05)


def test_joint_wedge_degenerate_none():
    assert joint_wedge(QPointF(0, 0), _dir(0.0), _dir(180.0), 1.0) is None   # straight through
    assert joint_wedge(QPointF(0, 0), _dir(0.0), _dir(0.0), 1.0) is None     # overlap
    assert joint_wedge(QPointF(0, 0), (0.0, 0.0), _dir(90.0), 1.0) is None   # zero tangent


def test_joint_wedge_outer_points_sit_on_the_flat_ends():
    w = joint_wedge(QPointF(10, 10), _dir(0.0), _dir(90.0), 2.0)
    pts = _pts(w)
    # A runs +x, B runs +y: the exterior is the (-,-) quadrant
    assert (10.0, 8.0) in pts and (8.0, 10.0) in pts and (8.0, 8.0) in pts
