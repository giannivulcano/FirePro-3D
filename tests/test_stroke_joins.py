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


# ---------------------------------------------------------------- D. crisp junctions (D3)
from firepro3d import crisp_stroke as cs
from PyQt6.QtGui import QTransform


def _oracle(path, w):
    """Mitered outline (MiterJoin, Qt limit = STROKE_MITER_LIMIT / 2)."""
    st = QPainterPathStroker(); st.setWidth(w)
    st.setJoinStyle(Qt.PenJoinStyle.MiterJoin); st.setMiterLimit(C.STROKE_MITER_LIMIT / 2.0)
    st.setCapStyle(Qt.PenCapStyle.FlatCap)
    return st.createStroke(path)


def _mask(outline, size):
    img = QImage(*size, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("black")); p.drawPath(outline); p.end()
    return _dark(img)


def _tri_path():
    p = QPainterPath(QPointF(50, 150)); p.lineTo(QPointF(250, 150))   # axis base
    p.lineTo(QPointF(150, 150 - 100 * math.sqrt(3)))                  # 60 deg sides
    p.closeSubpath(); return p


def test_g2_closed_polyline_triangle_matches_mitered_oracle(qapp, monkeypatch):
    """AC2: the crisp split's axis<->diagonal junctions are sharp (no notch,
    no dot bulge). Compare against the stroker oracle with a 2 px AA band."""
    poly = PolylineItem(QPointF(50, 150))
    poly.append_point(QPointF(250, 150))
    poly.append_point(QPointF(150, 150 - 100 * math.sqrt(3)))
    poly.close()
    img = _render([poly], size=(300, 200), monkeypatch=monkeypatch)
    got = _dark(img); want = _mask(_oracle(_tri_path(), 20.0), (300, 200))
    near = [(dx, dy) for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)]
    outside = {q for q in got if all((q[0] + dx, q[1] + dy) not in want for dx, dy in near)}
    missing = {q for q in want if all((q[0] + dx, q[1] + dy) not in got for dx, dy in near)}
    assert not outside, f"{len(outside)} dark px outside the mitered outline, e.g. {sorted(outside)[:5]}"
    assert not missing, f"{len(missing)} px missing inside, e.g. {sorted(missing)[:5]}"


def test_split_records_junction_directions(qapp):
    p = QPainterPath(QPointF(0, 0)); p.lineTo(QPointF(10, 0)); p.lineTo(QPointF(20, 10))
    s = cs.split_axis(p, QTransform())
    assert len(s.joints) == 1
    pt, d_in, d_out = s.joints[0]
    assert pt == QPointF(10, 0)
    assert d_in == pytest.approx((1.0, 0.0)) and d_out == pytest.approx((math.sqrt(0.5), math.sqrt(0.5)))


# ---------------------------------------------------------------- E. JointIndex (D4)
from firepro3d.stroke_joints import (JointAttrs, JointEnd, JointIndex, end_inked,
                                     ends_of_pieces, joinable, unit)
from firepro3d.path_walk import Seg


def _end(x, y, tx, ty, owner, which="start"):
    return JointEnd(x, y, tx, ty, which, owner)


def test_unit_normalises_and_keeps_the_zero_case():
    assert unit(3.0, 4.0) == pytest.approx((0.6, 0.8))
    assert unit(0.0, 0.0) == (0.0, 0.0)


def test_index_pairs_two_ends_within_weld_and_rejects_three():
    ix = JointIndex()
    a = _end(0, 0, 1, 0, "A"); b = _end(0.5, 0, 0, 1, "B", "finish")
    ix.register("A", (a,)); ix.register("B", (b,))
    assert ix.partner(a) is b and ix.partner(b) is a
    c = _end(0, 0.4, 0, -1, "C"); ix.register("C", (c,))
    assert ix.partner(a) is None and ix.partner(b) is None and ix.partner(c) is None
    ix.unregister("C")
    assert ix.partner(a) is b


def test_index_distance_is_exact_not_cell():
    ix = JointIndex()
    a = _end(0.99, 0, 1, 0, "A"); b = _end(2.0, 0, -1, 0, "B")   # 1.01 apart > CHAIN_WELD_MM
    ix.register("A", (a,)); ix.register("B", (b,))
    assert ix.partner(a) is None
    ix.register("B", (_end(1.98, 0, -1, 0, "B"),))                 # 0.99 apart, across a cell edge
    assert ix.partner(a) is not None


def test_register_replaces_and_unregister_returns_old_ends():
    ix = JointIndex()
    a = _end(0, 0, 1, 0, "A"); ix.register("A", (a,))
    old = ix.register("A", (_end(5, 5, 1, 0, "A"),))
    assert old == (a,)
    assert ix.unregister("A")[0].x == 5 and ix.unregister("A") == ()


def test_ends_of_is_the_public_registered_tuple():
    ix = JointIndex()
    a = _end(0, 0, 1, 0, "A"); ix.register("A", (a,))
    assert ix.ends_of("A") == (a,) and ix.ends_of("Z") == ()


def test_neighbours_reports_every_end_near_a_point():
    ix = JointIndex()
    a = _end(0, 0, 1, 0, "A"); b = _end(0, 0, 0, 1, "B")
    ix.register("A", (a,)); ix.register("B", (b,))
    assert set(ix.neighbours(QPointF(0.2, 0.2))) == {a, b}


def test_joinable_is_the_ac4_ac6_match():
    base = dict(weight="Thin", colour="#000000", inked=True, has_end_type=False, visible=True)
    assert joinable(JointAttrs(**base), JointAttrs(**base))
    assert not joinable(JointAttrs(**{**base, "weight": "Thick"}), JointAttrs(**base))
    assert not joinable(JointAttrs(**{**base, "colour": "#ff0000"}), JointAttrs(**base))
    assert not joinable(JointAttrs(**{**base, "inked": False}), JointAttrs(**base))
    assert not joinable(JointAttrs(**{**base, "has_end_type": True}), JointAttrs(**base))
    assert not joinable(JointAttrs(**{**base, "visible": False}), JointAttrs(**base))
    assert not joinable(None, JointAttrs(**base))


def test_ends_of_pieces_tangents_point_into_the_stroke():
    s, f = ends_of_pieces((Seg(0, 0, 10, 0), Seg(10, 0, 10, 10)), "K")
    assert (s.x, s.y, s.which) == (0, 0, "start") and (s.tx, s.ty) == pytest.approx((1.0, 0.0))
    assert (f.x, f.y, f.which) == (10, 10, "finish") and (f.tx, f.ty) == pytest.approx((0.0, -1.0))
    assert s.owner == "K" and f.owner == "K"
    assert ends_of_pieces((), "K") == ()


def test_end_inked_reads_the_dash_path_ends():
    dash = QPainterPath(QPointF(0, 0)); dash.lineTo(QPointF(4, 0))
    dash.moveTo(QPointF(8, 0)); dash.lineTo(QPointF(12, 0))
    assert end_inked(dash, QPointF(0, 0)) is True
    assert end_inked(dash, QPointF(12, 0)) is True
    assert end_inked(dash, QPointF(14, 0)) is False       # the stroke ends in a gap
    assert end_inked(QPainterPath(), QPointF(0, 0)) is False
