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


def test_p4_scene_clear_does_not_reach_item_change(qapp):
    """Qt's QGraphicsScene.clear() deletes items in C++ without dispatching
    the scene-change events to Python -- so the scene's joint index must be
    cleared explicitly at every clear() site (cleanup, scene_io reset)."""
    seen = []

    class Probe(LineItem):
        def itemChange(self, change, value):
            seen.append(change)
            return super().itemChange(change, value)

    sc = Model_Space(); ln = Probe(QPointF(0, 0), QPointF(10, 0))
    sc.addItem(ln); seen.clear()
    sc.clear()
    gc = ln.GraphicsItemChange
    assert gc.ItemSceneChange not in seen and gc.ItemSceneHasChanged not in seen
    sc.cleanup()


def test_p4_transform_order(qapp):
    """QTransform multiplication is row-vector: ``a * b`` applies a, then b."""
    from PyQt6.QtGui import QTransform
    a = QTransform.fromTranslate(10, 0); b = QTransform.fromScale(2, 2)
    assert (a * b).map(QPointF(0, 0)) == QPointF(20, 0)      # translate, then scale
    assert (b * a).map(QPointF(0, 0)) == QPointF(10, 0)


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


def _render(items, size=(300, 200), weight_px=20.0, monkeypatch=None, scene=None):
    """Render *items* in a Model_Space (or the prepared *scene*) onto a QImage,
    identity view transform, canvas pens patched to *weight_px* (exaggerated
    so geometry is legible)."""
    import firepro3d.geometry_2d as g2
    if monkeypatch is not None:
        monkeypatch.setattr(g2, "canvas_px", lambda w: weight_px)
    sc = scene if scene is not None else Model_Space()
    try:
        sc.set_mode("select")
        for it in items:
            it.style["colour"] = "#000000"
            sc.addItem(it); sc._draw_lines.append(it)
        img = QImage(*size, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
        p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        from PyQt6.QtCore import QRectF
        try:
            sc.render(p, QRectF(0, 0, *size), QRectF(0, 0, *size))
        finally:
            p.end()
    finally:
        sc.cleanup()
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


# ---------------------------------------------------------------- F. scene index (D5a / D6)
def test_scene_registers_open_styled_items_and_tracks_moves(qapp):
    sc = Model_Space()
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0)); b = LineItem(QPointF(100, 0), QPointF(100, 100))
        for it in (a, b):
            sc.addItem(it); sc._draw_lines.append(it)
        ix = sc.stroke_joints
        assert len(ix) == 4
        ea = [e for e in ix.neighbours(QPointF(100, 0)) if e.owner is a][0]
        assert ix.partner(ea).owner is b
        a.apply_grip(2, QPointF(100, 50))            # move a's end off the corner
        assert ix.partner([e for e in ix.neighbours(QPointF(100, 0)) if e.owner is b][0]) is None
        assert len(ix.neighbours(QPointF(100, 50))) == 1
        sc.removeItem(a)
        assert len(ix) == 2
    finally:
        sc.cleanup()


def test_closed_reference_and_ghost_items_register_nothing(qapp):
    from firepro3d.geometry_2d import RectangleItem
    sc = Model_Space()
    try:
        sc.addItem(RectangleItem(QPointF(0, 0), QPointF(10, 10)))
        assert len(sc.stroke_joints) == 0
        ln = LineItem(QPointF(0, 0), QPointF(10, 0)); ln.reference = True
        sc.addItem(ln)
        assert len(sc.stroke_joints) == 0
    finally:
        sc.cleanup()


def test_cleanup_and_scene_clear_sites_empty_the_index(qapp):
    sc = Model_Space()
    sc.addItem(LineItem(QPointF(0, 0), QPointF(100, 0)))
    assert len(sc.stroke_joints) == 2
    sc.clear()                                   # the load / new reset path
    assert len(sc.stroke_joints) == 0
    sc.addItem(LineItem(QPointF(0, 0), QPointF(100, 0)))
    assert len(sc.stroke_joints) == 2
    sc.cleanup()
    assert len(sc.stroke_joints) == 0


def test_geometry_change_repaints_former_and_new_partners(qapp, monkeypatch):
    sc = Model_Space()
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0)); b = LineItem(QPointF(100, 0), QPointF(100, 100))
        c = LineItem(QPointF(0, 100), QPointF(-50, 100))
        for it in (a, b, c):
            sc.addItem(it); sc._draw_lines.append(it)
        calls = []
        for it in (a, b, c):
            monkeypatch.setattr(it, "update", lambda *args, _it=it: calls.append(_it))
        a.apply_grip(0, QPointF(0, 100))             # a's start now meets c's start
        assert b in calls and c in calls             # former partner and new partner repaint
    finally:
        sc.cleanup()


def _pair_in(sc, a, b):
    for it in (a, b):
        sc.addItem(it); sc._draw_lines.append(it); it._sync_stroke_pen()


def test_joined_item_bounds_pad_covers_the_miter_reach(qapp, monkeypatch):
    """m2: the pad is half_w * sqrt(1 + limit^2) (the tip AND the clip points
    sit there), plus half the weld distance -- 20 px: 41.23 + 0.5."""
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    sc = Model_Space()
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0))
        b = LineItem(QPointF(100, 0), QPointF(100, 100))
        _pair_in(sc, a, b)
        r = a.boundingRect()
        a._joint_pad = False
        plain = a.boundingRect()                 # the same item with the joint pad off
        a._joint_pad = True
        grow = 0.5 * 20.0 * math.sqrt(17.0) + 0.5 - (20.0 / 2.0 + 0.75)   # reach + weld - the plain pad
        assert plain.left() - r.left() >= grow - 1e-6, (r, plain)
        assert r.right() - plain.right() >= grow - 1e-6, (r, plain)
    finally:
        sc.cleanup()


def test_lone_line_bounds_are_qts_own_no_joint_pad(qapp, monkeypatch):
    """m3: with no partner the item pads w / 2 + the cosmetic 0.75 only, so a
    window-select needs no wider margin than before the joints."""
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    sc = Model_Space()
    try:
        ln = LineItem(QPointF(0, 0), QPointF(100, 0))
        sc.addItem(ln); sc._draw_lines.append(ln); ln._sync_stroke_pen()
        ln._joint_pad = False
        plain = ln.sceneBoundingRect()          # the bounds with the pad switched off
        ln._joint_pad = True
        assert ln.sceneBoundingRect() == plain
        # a partner arriving pads it; moving it away drops the pad again
        b = LineItem(QPointF(100, 0), QPointF(100, 100))
        sc.addItem(b); sc._draw_lines.append(b)
        assert ln.sceneBoundingRect().right() > plain.right() + 20.0
        b.apply_grip(0, QPointF(100, 100)); b.apply_grip(2, QPointF(100, 160))
        assert ln.sceneBoundingRect() == plain
    finally:
        sc.cleanup()


def test_selection_frame_ignores_the_joint_pad(qapp, monkeypatch):
    """The miter-reach pad is a repaint margin: the manipulator frame
    (manip_bounds) keeps the plain pen-padded bounds."""
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    sc = Model_Space()
    try:
        ln = LineItem(QPointF(0, 0), QPointF(100, 0))
        b = LineItem(QPointF(100, 0), QPointF(100, 100))
        _pair_in(sc, ln, b)
        frame = ln.manip_bounds()
        assert frame.left() > -20.0 and frame.right() < 120.0      # w / 2 + 0.75 = 10.75, not 2 w
        assert ln.boundingRect().left() <= -40.0                    # paint bounds still padded
    finally:
        sc.cleanup()


# ---------------------------------------------------------------- G. cross-item joints (D7)
def _tri_lines():
    a, b, c = QPointF(50, 150), QPointF(250, 150), QPointF(150, 150 - 100 * math.sqrt(3))
    return [LineItem(a, b), LineItem(b, c), LineItem(c, a)]


def _compare(img, oracle_path, size=(300, 200), band=2):
    """(dark px outside the oracle, oracle px not dark), each with a *band*
    px AA tolerance. The oracle is the mitered stroker outline (clips past
    the miter limit like Qt), so a bevel / overshoot shows up in either set."""
    got = _dark(img); want = _mask(_oracle(oracle_path, 20.0), size)
    near = lambda q, S: any((q[0]+dx, q[1]+dy) in S for dx in range(-band, band+1) for dy in range(-band, band+1))
    return {q for q in got if not near(q, want)}, {q for q in want if not near(q, got)}


def _core(xc, yc):
    """Pixels only the exterior wedge of a 90 deg corner at (xc, yc) can ink
    (20 px pen: the wedge fills [xc, xc+10] x [yc, yc+10]); clear of any
    end-glyph / cap sliver."""
    return {(x, y) for x in range(xc + 6, xc + 10) for y in range(yc + 6, yc + 10)}


def _corner_pair():
    """Two lines meeting at (150, 150): left-to-corner and corner-to-up."""
    return (LineItem(QPointF(50, 150), QPointF(150, 150)),
            LineItem(QPointF(150, 150), QPointF(150, 50)))


def test_g2_three_lines_triangle_matches_mitered_oracle(qapp, monkeypatch):
    img = _render(_tri_lines(), monkeypatch=monkeypatch)
    outside, missing = _compare(img, _tri_path())
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


def test_g2_two_lines_make_one_sharp_square_corner(qapp, monkeypatch):
    a, b = _corner_pair()
    img = _render([a, b], monkeypatch=monkeypatch)
    assert _core(150, 150) <= _dark(img)


def test_g3_three_ends_at_one_point_stay_flat(qapp, monkeypatch):
    c = QPointF(150, 100)
    # a fan (0, 60, 120 deg, all upward): every pairwise exterior wedge lands
    # below the corner, where no arm hides it (a symmetric 120 deg star would
    # cover each wedge with the third arm).
    items = [LineItem(c, QPointF(250, 100)), LineItem(c, QPointF(200, 100 - 50 * math.sqrt(3))),
             LineItem(c, QPointF(100, 100 - 50 * math.sqrt(3)))]
    img = _render(items, monkeypatch=monkeypatch)
    want = QPainterPath()
    for it in items:
        q = QPainterPath(it.line().p1()); q.lineTo(it.line().p2()); want.addPath(q)
    st = QPainterPathStroker(); st.setWidth(20.0); st.setCapStyle(Qt.PenCapStyle.FlatCap)
    flat = _mask(st.createStroke(want), (300, 200))
    got = _dark(img)
    outside = {q for q in got if not any((q[0]+dx, q[1]+dy) in flat for dx in (-2,-1,0,1,2) for dy in (-2,-1,0,1,2))}
    assert not outside, sorted(outside)[:5]


def test_g3_mixed_weights_stay_flat(qapp, monkeypatch):
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0 if w == "Thick" else 8.0)
    a, b = _corner_pair()
    a.style["weight"] = "Thick"; b.style["weight"] = "Thin"
    img = _render([a, b])
    # a wedge would put dark px in the exterior corner square
    assert not {(x, y) for x in range(151, 160) for y in range(151, 160)} & _dark(img)


def _snap(sc, size=(300, 200)):
    """Render a live scene to a QImage (identity view)."""
    from PyQt6.QtCore import QRectF
    img = QImage(*size, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    sc.render(p, QRectF(0, 0, *size), QRectF(0, 0, *size)); p.end()
    return img


def test_g3_mixed_colours_stay_flat(qapp, monkeypatch):
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    for red, expect_join in ((False, True), (True, False)):
        sc = Model_Space()
        try:
            sc.set_mode("select")
            a, b = _corner_pair()
            a.style["colour"] = "#ff0000" if red else "#000000"; b.style["colour"] = "#000000"
            for it in (a, b):
                sc.addItem(it); sc._draw_lines.append(it)
            img = _snap(sc)
        finally:
            sc.cleanup()
        inked = {(x, y) for x, y in _core(150, 150) if img.pixelColor(x, y) != QColor("white")}
        assert (inked == _core(150, 150)) if expect_join else not inked, (red, len(inked))


def test_g4_twenty_degree_sliver_is_clipped_like_qt(qapp, monkeypatch):
    # apex high in the frame, arms running down: the full miter tip (~57 px
    # above the apex) and Qt's clipped one (~41 px) both stay inside the image
    apex = QPointF(150, 100); a = math.radians(20.0)
    items = [LineItem(apex, QPointF(150, 190)),
             LineItem(apex, QPointF(150 + 90 * math.sin(a), 100 + 90 * math.cos(a)))]
    img = _render(items, monkeypatch=monkeypatch)
    p = QPainterPath(items[0].line().p2()); p.lineTo(apex); p.lineTo(items[1].line().p2())
    outside, missing = _compare(img, p)       # oracle: MiterJoin at Qt limit 2 -> clipped miter
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])
    # `not outside` is exactly "no dark pixel beyond the oracle's reach"


def test_g5_arrow_end_never_joins(qapp, monkeypatch):
    from tests.lt5_support import end_id, set_ends
    sc = Model_Space()
    try:
        sc.scale_manager.drawing_scale = 1.0
        a, b = _corner_pair()
        set_ends(a, finish=end_id(sc))
        img = _render([a, b], monkeypatch=monkeypatch, scene=sc)   # cleans sc
    finally:
        sc.cleanup()
    assert not _core(150, 150) & _dark(img)


def _dashed_corner(cx):
    """Hidden-dash (6 on / 3 off, period 9) line A ending at (cx, 150) and a
    vertical B starting there; scene at drawing scale 1. Returns
    (scene, items, a_end_inked, b_start_inked): the premise, read from
    ``linetype_render.expand`` independently of the paint."""
    from tests.lt3_support import hidden
    from firepro3d.linetype_render import expand, LinetypeDef
    from firepro3d.stroke_style import linetype_block
    sc = Model_Space(); sc.scale_manager.drawing_scale = 1.0
    lid = hidden(sc)
    a = LineItem(QPointF(50, 150), QPointF(cx, 150))
    b = LineItem(QPointF(cx, 150), QPointF(cx, 50))
    for it in (a, b):
        it.style["linetype"] = lid
    lt = LinetypeDef.from_block(linetype_block(lid, sc.block_registry))
    inked = [end_inked(expand(it.stroke_pieces(), lt, 1.0, (0.0, 0.0))[0], pt, 1e-4)
             for it, pt in ((a, QPointF(cx, 150)), (b, QPointF(cx, 150)))]
    return sc, [a, b], inked[0], inked[1]


def _pick_corner(a_inked):
    """The first cx whose A end is *a_inked* and whose B start is on ink."""
    for cx in range(150, 175):
        sc, _items, ia, ib = _dashed_corner(cx)
        sc.cleanup()
        if ib and ia == a_inked:
            return cx
    raise AssertionError(f"no corner with A end inked={a_inked} in 150..175")


def test_g5_dashed_end_in_a_gap_is_flat_and_inked_end_is_sharp(qapp, monkeypatch):
    cx_on, cx_off = _pick_corner(True), _pick_corner(False)
    sc, items, ia, ib = _dashed_corner(cx_on)
    try:
        assert ia and ib, "premise: both ends sit on ink"
        img_on = _render(items, monkeypatch=monkeypatch, scene=sc)    # cleans sc
    finally:
        sc.cleanup()
    assert _core(cx_on, 150) <= _dark(img_on)
    sc, items, ia, ib = _dashed_corner(cx_off)
    try:
        assert (ia, ib) == (False, True), "premise: A's end is in a gap"
        img_off = _render(items, monkeypatch=monkeypatch, scene=sc)   # cleans sc
    finally:
        sc.cleanup()
    assert not _core(cx_off, 150) & _dark(img_off)


def test_g7_move_breaks_and_undo_restores_the_join(qapp, monkeypatch):
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    sc = Model_Space()
    try:
        sc.set_mode("select")
        items = _tri_lines()
        for it in items:
            it.style["colour"] = "#000000"; sc.addItem(it); sc._draw_lines.append(it)

        snap = lambda: _snap(sc)
        corner = {(x, y) for x in range(251, 262) for y in range(151, 162)}   # exterior of the (250,150) corner
        assert corner & _dark(snap())                       # mitered: wedge present
        items[0].apply_grip(1, QPointF(150, 100))           # translate the base away (mid grip)
        assert not (corner & _dark(snap()))                 # both former partners flat
        items[0].apply_grip(1, QPointF(150, 150))           # back (undo path = the same setter)
        assert corner & _dark(snap())
    finally:
        sc.cleanup()


def test_f_transform_and_pos_moves_carry_the_wedge_with_the_item(qapp, monkeypatch):
    """The manipulator preview moves real items with setTransform: the wedge
    must paint at the NEW corner (not the old one), and restore on reset; a
    setPos move re-registers the ends too (design D6)."""
    import firepro3d.geometry_2d as g2
    from PyQt6.QtGui import QTransform
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    sc = Model_Space(); sc.set_mode("select")
    try:
        a, b = _corner_pair()
        for it in (a, b):
            it.style["colour"] = "#000000"; sc.addItem(it); sc._draw_lines.append(it)
        size = (300, 300)
        white = QColor("white")
        inked = lambda core: {q for q in core
                              if _snap(sc, size).pixelColor(*q) != white}
        assert inked(_core(150, 150)) == _core(150, 150)         # premise: joined
        for it in (a, b):
            it.setTransform(QTransform().translate(60, 60))
        assert inked(_core(210, 210)) == _core(210, 210)          # wedge at the new corner
        assert not inked(_core(150, 150))                         # none at the old one
        for it in (a, b):
            it.setTransform(QTransform())
        assert inked(_core(150, 150)) == _core(150, 150)         # restored
        for it in (a, b):
            it.setPos(60, 60)
        ix = sc.stroke_joints
        assert {e.owner for e in ix.neighbours(QPointF(210, 210))} == {a, b}
        assert not ix.neighbours(QPointF(150, 150))
    finally:
        sc.cleanup()


def test_copy_base_point_is_the_manip_bounds_centre_not_the_padded_scene_rect(qapp):
    """The joint pad (open line: 2 w; closed rect: w/2) must not shift the
    copy base point -- it is the centre of ``union_manip_bounds``."""
    from firepro3d.geometry_2d import RectangleItem
    from firepro3d.selection_manipulator import union_manip_bounds
    sc = Model_Space()
    try:
        ln = LineItem(QPointF(0, 0), QPointF(100, 0))
        rc = RectangleItem(QPointF(150, 40), QPointF(250, 140))
        for it in (ln, rc):
            sc.addItem(it); sc._draw_lines.append(it); it.setSelected(True)
        got = []
        sc._modify_ctl.write_clipboard = lambda items, base: got.append(base) or len(items)
        sc.copy_selected_items()
        want = union_manip_bounds([ln, rc]).center()
        assert len(got) == 1
        assert (got[0].x(), got[0].y()) == pytest.approx((want.x(), want.y()))
        padded = ln.sceneBoundingRect().united(rc.sceneBoundingRect()).center()
        assert abs(padded.x() - want.x()) > 0.1 or abs(padded.y() - want.y()) > 0.1, \
            "premise: the pad shifts the naive union"
    finally:
        sc.cleanup()


def test_wedge_for_pair_uses_the_midpoint_and_maps_through_xf():
    from firepro3d.stroke_joints import wedge_for_pair
    a = _end(0.2, 0, -1, 0, "A"); b = _end(-0.2, 0, 0, -1, "B", "finish")
    w = wedge_for_pair(a, b, 10.0)
    assert (w.at(0).x(), w.at(0).y()) == pytest.approx((0.0, 0.0))     # corner = midpoint
    assert (10.0, 10.0) in {(round(w.at(k).x(), 6), round(w.at(k).y(), 6)) for k in range(w.count())}
    from PyQt6.QtGui import QTransform
    w2 = wedge_for_pair(a, b, 20.0, QTransform.fromScale(2, 2))
    assert (20.0, 20.0) in {(round(w2.at(k).x(), 6), round(w2.at(k).y(), 6)) for k in range(w2.count())}


# ---------------------------------------------------------------- H. blocks + sheets (D5b / AC7 / AC8)
_BSIZE = (340, 300)
_BP = QPointF(170, 150)                  # block insertion point in the render
_TRI_LOCAL = [QPointF(-100, 100 * math.sqrt(3) / 3), QPointF(100, 100 * math.sqrt(3) / 3),
              QPointF(0, -200 * math.sqrt(3) / 3)]      # equilateral, centroid at (0, 0)


def _local_tri_lines():
    a, b, c = _TRI_LOCAL
    return [LineItem(a, b), LineItem(b, c), LineItem(c, a)]


def _prims(items):
    out = []
    for it in items:
        it.style["colour"] = "#000000"
        out.append(it.to_dict())
    return out


def _block_def(prims, name="Tri"):
    from firepro3d.block_definition import BlockDefinition
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=(0.0, 0.0))


def _patch_px(monkeypatch):
    """Canvas px = 20 on every paint path (plain ops, linetype loop, mixin)."""
    import firepro3d.block_instance as bi
    import firepro3d.geometry_2d as g2
    import firepro3d.stroke_style as ss
    for mod in (bi, g2, ss):
        monkeypatch.setattr(mod, "canvas_px", lambda w: 20.0)


def _block_scene(monkeypatch, rot=0.0, nested=False):
    """A Model_Space holding one placed instance of a definition built from
    three LineItems (the triangle, centroid at the block origin)."""
    _patch_px(monkeypatch)
    sc = Model_Space()
    d = _block_def(_prims(_local_tri_lines()))
    sc.register_block_definition(d)
    if nested:
        host = _block_def([{"type": "block_instance", "block_id": d.id,
                            "pos": [0.0, 0.0], "rotation": 0.0}], name="Host")
        sc.register_block_definition(host)
        d = host
    inst = sc.place_block_instance(d.id, (_BP.x(), _BP.y()), rotation=rot,
                                   level=sc.active_level)
    return sc, inst


def _tri_oracle(rot):
    """The triangle's closed path in scene px: local points turned by *rot*
    (Y-up CCW degrees = Qt rotate(-rot)) about the block origin, moved to
    the insertion point. Convention written out here, not read back."""
    t = QTransform(); t.translate(_BP.x(), _BP.y()); t.rotate(-rot)
    p = QPainterPath(t.map(_TRI_LOCAL[0]))
    p.lineTo(t.map(_TRI_LOCAL[1])); p.lineTo(t.map(_TRI_LOCAL[2])); p.closeSubpath()
    return p


def test_g6_triangle_inside_a_placed_block_is_mitered(qapp, monkeypatch):
    """AC7 / D5b: three block-op lines meeting end to end close sharp corners
    on the canvas, against the stroker oracle."""
    sc, _inst = _block_scene(monkeypatch, 0.0)
    img = _render([], size=_BSIZE, monkeypatch=monkeypatch, scene=sc)
    outside, missing = _compare(img, _tri_oracle(0.0), size=_BSIZE)
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


def test_g6_triangle_inside_a_rotated_block_is_mitered(qapp, monkeypatch):
    """Same at pose rotation 30 deg: oracle = the local triangle turned by
    the same angle (cosmetic pen: the wedge is filled in device space)."""
    sc, _inst = _block_scene(monkeypatch, 30.0)
    img = _render([], size=_BSIZE, monkeypatch=monkeypatch, scene=sc)
    outside, missing = _compare(img, _tri_oracle(30.0), size=_BSIZE)
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


def test_g6_nested_block_triangle_is_mitered(qapp, monkeypatch):
    """A nested child is its own container: its ops join among themselves."""
    sc, _inst = _block_scene(monkeypatch, 0.0, nested=True)
    img = _render([], size=_BSIZE, monkeypatch=monkeypatch, scene=sc)
    outside, missing = _compare(img, _tri_oracle(0.0), size=_BSIZE)
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


def test_g6_loose_line_touching_a_block_line_stays_flat(qapp, monkeypatch):
    """AC7: a LineItem ending exactly on a placed block's line end gets no
    wedge. Mechanism: a BlockInstance is not a Geometry2DMixin, so its ends
    never enter the scene index (only the loose line's two do)."""
    _patch_px(monkeypatch)
    sc = Model_Space()
    blk = LineItem(QPointF(-100, 0), QPointF(0, 0))
    d = _block_def(_prims([blk]))
    sc.register_block_definition(d)
    sc.place_block_instance(d.id, (150, 150), level=sc.active_level)   # ends at (150, 150)
    loose = LineItem(QPointF(150, 150), QPointF(150, 50))
    loose.style["colour"] = "#000000"
    sc.set_mode("select")
    sc.addItem(loose); sc._draw_lines.append(loose)
    assert len(sc.stroke_joints) == 2
    img = _render([], size=(300, 200), monkeypatch=monkeypatch, scene=sc)
    assert not _core(150, 150) & _dark(img)
    # premise: two scene lines on the same corner DO close it (the g2 pair)
    a, b = _corner_pair()
    img2 = _render([a, b], monkeypatch=monkeypatch)
    assert _core(150, 150) <= _dark(img2)


def test_block_definition_joint_index_is_static_and_recompiled_with_ops(qapp):
    """Three lines -> 6 ends, 3 pairs; set_primitives (one line moved away)
    recompiles; a mirrored variant gets its own index in the variant frame;
    a nested child is its own container."""
    from firepro3d.render_op import STROKE
    d = _block_def(_prims(_local_tri_lines()))
    ix = d.joint_index()
    assert len(ix) == 6 and d.joint_index() is ix            # static
    own = [i for i, o in enumerate(d.render_ops()) if o.kind == STROKE]
    ends = [e for i in own for e in ix.ends_of(i)]
    assert len(ends) == 6 and all(ix.partner(e) is not None for e in ends)
    # mirrored variant: its own index, ends in the variant frame
    per_op, _jops = d.joint_indexes(True, 1.0)
    vix = per_op[own[0]]
    assert vix is not ix
    e0, v0 = ix.ends_of(own[0])[0], vix.ends_of(own[0])[0]
    assert v0.x == pytest.approx(-e0.x) and v0.y == pytest.approx(e0.y)
    assert d.joint_indexes(True, 1.0)[0] is per_op           # keyed like _variants
    # edit: one edge moved away -> recompiled, a single shared corner left
    a, b, c = _TRI_LOCAL
    moved = [LineItem(a, b), LineItem(b, c),
             LineItem(QPointF(c.x() + 500, c.y() + 500), QPointF(a.x() + 500, a.y() + 500))]
    d.set_primitives(_prims(moved))
    ix2 = d.joint_index()
    assert ix2 is not ix and len(ix2) == 6
    ends2 = [e for i in range(len(d.render_ops())) for e in ix2.ends_of(i)]
    assert sum(ix2.partner(e) is not None for e in ends2) == 2
    # nested: the child's ops index in the child's own container
    child = _block_def(_prims(_local_tri_lines()), name="Child")
    host = _block_def(_prims([LineItem(QPointF(0, 0), QPointF(5, 5))]) + [
        {"type": "block_instance", "block_id": child.id, "pos": [0.0, 0.0], "rotation": 0.0}],
        name="Host")
    host._resolve = {child.id: child}.get
    hix = host.joint_index()
    assert len(hix) == 2                                      # the host's own line only
    per_op = host.joint_indexes(False, 1.0)[0]
    child_ixs = [x for x in per_op if x is not None and x is not hix]
    assert child_ixs and all(len(x) == 6 for x in child_ixs)


def test_g6_sheet_pdf_export_is_mitered(qapp, tmp_path, monkeypatch):
    """AC8: a sheet viewport over the placed 3-Line triangle block, exported
    through the real paper_export QPdfWriter path; PyMuPDF rasterises a base
    corner and the apex at high zoom; both match the mitered stroker oracle
    mapped by the viewport scale (stroke width read from the PDF)."""
    import fitz
    from firepro3d import paper_display as pd
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    from tests.test_lt1_block_paper import _VP_W, _VP_X, _VP_Y, _export
    save_paper_color_mode(PaperColorMode.BW)
    cats = pd.load_paper_categories()
    cats["Blocks"]["line_weight"] = "Heavy"
    pd.save_paper_categories(cats)
    scale = 0.02
    k = 5.0                                                  # model mm per local px
    ms = Model_Space()
    pts = [QPointF(p.x() * k, p.y() * k) for p in _TRI_LOCAL]
    d = _block_def(_prims([LineItem(pts[0], pts[1]), LineItem(pts[1], pts[2]),
                           LineItem(pts[2], pts[0])]))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    pdf = _export(tmp_path, ms, scale, "tri.pdf")
    pt_mm = 25.4 / 72.0
    z = 24.0
    doc = fitz.open(str(pdf))
    try:
        page = doc[0]
        cx, cy = _VP_X + _VP_W / 2.0, _VP_Y + _VP_W / 2.0
        pp = [((cx + p.x() * scale) / pt_mm, (cy + p.y() * scale) / pt_mm) for p in pts]
        # the block's stroke weight, read from the PDF: widest stroke whose
        # rect sits inside the triangle's page box
        x0, x1 = min(p[0] for p in pp), max(p[0] for p in pp)
        widths = [dr["width"] for dr in page.get_drawings()
                  if "s" in (dr.get("type") or "") and x0 - 3 <= dr["rect"].x0
                  and dr["rect"].x1 <= x1 + 3 and dr["rect"].height > 5]
        assert widths, "premise: the triangle strokes are in the PDF"
        width_pt = max(widths)
        for v in (0, 2):                                     # a base corner and the apex
            x, y = pp[v]
            clip = fitz.Rect(x - 8, y - 8, x + 8, y + 8)
            pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=clip,
                                  colorspace=fitz.csGRAY, alpha=False)
            n, w, h, s = pix.n, pix.width, pix.height, pix.samples
            got = {(i, j) for j in range(h) for i in range(w) if s[(j * w + i) * n] < 128}
            path = QPainterPath(QPointF((pp[0][0] - clip.x0) * z, (pp[0][1] - clip.y0) * z))
            path.lineTo(QPointF((pp[1][0] - clip.x0) * z, (pp[1][1] - clip.y0) * z))
            path.lineTo(QPointF((pp[2][0] - clip.x0) * z, (pp[2][1] - clip.y0) * z))
            path.closeSubpath()
            want = _mask(_oracle(path, width_pt * z), (w, h))
            near = lambda q, S: any((q[0] + dx, q[1] + dy) in S
                                    for dx in range(-3, 4) for dy in range(-3, 4))
            inner = lambda q: 6 <= q[0] < w - 6 and 6 <= q[1] < h - 6   # clip-edge raster noise
            outside = {q for q in got if inner(q) and not near(q, want)}
            missing = {q for q in want if inner(q) and not near(q, got)}
            assert len(want) > 500 and len(got) > 500, "premise: the stroke is in the clip"
            assert not outside and not missing, (v, sorted(outside)[:5], sorted(missing)[:5])
    finally:
        doc.close()


def test_g6_dashed_block_ends_follow_the_ink_like_scene_lines(qapp, monkeypatch):
    """AC6 inside a block (the linetype loop): the op end sitting on ink is
    sharp, the op end sitting in a gap stays flat -- same premise as g5."""
    _patch_px(monkeypatch)
    for cx, want_sharp in ((_pick_corner(True), True), (_pick_corner(False), False)):
        sc, items, _ia, _ib = _dashed_corner(cx)
        d = _block_def(_prims(items))
        sc.register_block_definition(d)
        sc.place_block_instance(d.id, (0.0, 0.0), level=sc.active_level)
        img = _render([], monkeypatch=monkeypatch, scene=sc)       # cleans sc
        assert (_core(cx, 150) <= _dark(img)) is want_sharp
        assert want_sharp or not _core(cx, 150) & _dark(img)


# ---------------------------------------------------------------- I. fix round (FR1): cache, halo, index, pens
_RED_LIGHT = "#800000"          # lighter(150) -> (192, 0, 0): the halo is told apart from the stroke


def _corner_scene(monkeypatch, colour="#000000"):
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    sc = Model_Space(); sc.set_mode("select")
    a, b = _corner_pair()
    for it in (a, b):
        it.style["colour"] = colour
        sc.addItem(it); sc._draw_lines.append(it)
    return sc, a, b


def _core_inked(img, xc=150, yc=150):
    return {q for q in _core(xc, yc) if img.pixelColor(*q) != QColor("white")}


def test_cached_wedge_follows_style_edits_after_a_warm_paint(qapp, monkeypatch):
    """The wedge cache is revalidated at paint (ratified D4): after the join
    has painted (cache warm), a partner weight / colour / visibility edit
    flattens the corner and the revert restores it -- no choke point needed."""
    import firepro3d.geometry_2d as g2
    sc, a, b = _corner_scene(monkeypatch)
    try:
        assert _core_inked(_snap(sc), 150, 150) == _core(150, 150)    # warm, joined
        monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0 if w == "Heavy" else 8.0)
        a.style["weight"] = "Heavy"
        b.style["weight"] = "Thin"
        assert not _core_inked(_snap(sc))                             # mixed weights: flat
        b.style["weight"] = "Heavy"
        assert _core_inked(_snap(sc)) == _core(150, 150)
        b.style["colour"] = "#ff0000"
        assert not _core_inked(_snap(sc))                             # mixed colours: flat
        b.style["colour"] = "#000000"
        assert _core_inked(_snap(sc)) == _core(150, 150)
        b.setVisible(False)
        assert not _core_inked(_snap(sc))
    finally:
        sc.cleanup()


def test_one_owner_per_pair_fills_the_wedge(qapp, monkeypatch):
    """The pair is filled once per paint (perf: not twice): exactly one of the
    two items holds the wedge, the one whose end is the FINISH. The owner's
    bounds pad covers the wedge region, so a repaint of that region reaches it."""
    sc, a, b = _corner_scene(monkeypatch)
    try:
        _snap(sc)
        holders = [it for it in (a, b) if it._jcache[True][1]]
        assert holders == [a]                  # a's finish meets b's start
        assert a.sceneBoundingRect().contains(QPointF(159, 159))
    finally:
        sc.cleanup()


def _no_manip(monkeypatch):
    """The selection manipulator boxes a selected item and suppresses its own
    halo; the halo path is under test, so run the pre-manipulator boundary."""
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "_manip_wraps", lambda item: False)


def _halo_pixel(img):
    """Red channel at an exterior-corner pixel inside the wedge (stroke red
    128, halo red 192)."""
    return img.pixelColor(157, 157).red()


def test_halo_wedge_on_the_continuous_route(qapp, monkeypatch):
    _no_manip(monkeypatch)
    sc, a, b = _corner_scene(monkeypatch, _RED_LIGHT)
    try:
        b.setSelected(True)                                  # the NON-owner is selected
        assert _halo_pixel(_snap(sc)) > 160
    finally:
        sc.cleanup()


def test_halo_wedge_on_the_dashed_route(qapp, monkeypatch):
    _no_manip(monkeypatch)
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    cx = _pick_corner(True)
    sc, items, ia, ib = _dashed_corner(cx)
    try:
        sc.set_mode("select")
        for it in items:
            it.style["colour"] = _RED_LIGHT
            sc.addItem(it); sc._draw_lines.append(it)
        items[1].setSelected(True)
        img = _snap(sc)
        assert img.pixelColor(cx + 7, 157).red() > 160
    finally:
        sc.cleanup()


def test_halo_wedge_on_the_ends_route(qapp, monkeypatch):
    """A line whose FINISH carries an arrow takes the LT5 ends route; its
    free start joins the partner. The base wedge must not cover the halo and
    the halo wedge must be drawn."""
    _no_manip(monkeypatch)
    from tests.lt5_support import end_id, set_ends
    import firepro3d.geometry_2d as g2
    monkeypatch.setattr(g2, "canvas_px", lambda w: 20.0)
    sc = Model_Space(); sc.set_mode("select")
    try:
        sc.scale_manager.drawing_scale = 1.0
        a = LineItem(QPointF(150, 150), QPointF(150, 50))
        b = LineItem(QPointF(150, 150), QPointF(50, 150))           # start meets a's start
        set_ends(b, finish=end_id(sc))
        for it in (a, b):                                           # b paints last, so a partner's
            it.style["colour"] = _RED_LIGHT                         # base wedge cannot cover its halo
            sc.addItem(it); sc._draw_lines.append(it)
        b.setSelected(True)
        assert _halo_pixel(_snap(sc)) > 160
    finally:
        sc.cleanup()


def test_reference_flip_reregisters_and_a_deleted_reference_leaves_no_stale_ends(qapp, monkeypatch):
    sc, a, b = _corner_scene(monkeypatch)
    try:
        ix = sc.stroke_joints
        assert len(ix) == 4
        b._set_reference_flag("Reference", True)
        assert len(ix) == 2 and not ix.ends_of(b)                   # unregistered on the flip
        b._set_reference_flag("Reference", False)
        assert len(ix) == 4                                         # (a) un-reference re-registers
        assert _core_inked(_snap(sc)) == _core(150, 150)
        b._set_reference_flag("Reference", True)                    # (b) flip, then delete
        sc.removeItem(b)
        assert len(ix) == 2                                         # no stale ends of b
        d = LineItem(QPointF(150, 150), QPointF(150, 250))
        d.style["colour"] = "#000000"
        sc.addItem(d); sc._draw_lines.append(d)
        assert ix.partner(ix.ends_of(a)[1]) is not None             # a pairs with the new line
    finally:
        sc.cleanup()


def test_open_polyline_closing_on_its_own_start_has_no_joint_partner(qapp):
    """m5: [P, Q, R, P] left open is ONE stroke with two free ends at P; they
    never pair with each other (AC3 'separate open strokes'). The drawn corner
    is not asserted by pixels: Qt's own stroker closes any path whose first
    and last points coincide, so the item mitres at P with or without a wedge."""
    sc = Model_Space()
    try:
        poly = PolylineItem(QPointF(50, 150))
        poly.append_point(QPointF(250, 150))
        poly.append_point(QPointF(150, 150 - 100 * math.sqrt(3)))
        poly.append_point(QPointF(50, 150))
        sc.addItem(poly); sc._draw_lines.append(poly)
        ix = sc.stroke_joints
        assert len(ix.ends_of(poly)) == 2                  # premise: open, registered
        assert all(ix.partner(e) is None for e in ix.ends_of(poly))
        assert not poly._has_joint_partner()               # ... and no pad either
    finally:
        sc.cleanup()


def test_index_rejects_a_same_owner_pair():
    ix = JointIndex(1.0)
    ix.register("P", [_end(0, 0, 1, 0, "P", "start"), _end(0.2, 0, 0, 1, "P", "finish")])
    for e in ix.ends_of("P"):
        assert ix.partner(e) is None


# -- m4: the crisp junction follows the pen's join style -----------------------------------
def _split_vs_plain(pen, size=(200, 160)):
    """Dark-pixel sets of a horizontal -> 120 deg turn (interior 60 deg) path stroked through the
    crisp split and plainly (the oracle: Qt's own join of the same pen)."""
    path = QPainterPath(QPointF(30, 60)); path.lineTo(QPointF(130, 60)); path.lineTo(QPointF(80, 60 + 50 * math.sqrt(3)))   # 120 deg turn
    out = []
    for split in (True, False):
        img = QImage(*size, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
        p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        sp = cs.split_axis(path, p.worldTransform()) if split else None
        cs.stroke(p, path, pen, sp); p.end()
        out.append(_dark(img))
    return out


def _close(got, want, band=2):
    near = lambda q, S: any((q[0] + dx, q[1] + dy) in S
                            for dx in range(-band, band + 1) for dy in range(-band, band + 1))
    return {q for q in got if not near(q, want)}, {q for q in want if not near(q, got)}


def test_crisp_junction_of_a_default_bevel_pen_is_a_bevel(qapp):
    pen = QPen(QColor("black"), 20.0); pen.setCosmetic(True)       # Qt default join: Bevel
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    assert pen.joinStyle() == Qt.PenJoinStyle.BevelJoin
    got, want = _split_vs_plain(pen)
    outside, missing = _close(got, want)
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


def test_crisp_junction_of_a_model_pen_stays_the_stroke_miter(qapp):
    pen = stroke_pen("#000000", 20.0)                              # Miter, Qt limit 2
    got, want = _split_vs_plain(pen)
    outside, missing = _close(got, want)
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


def test_crisp_junction_of_a_round_pen_is_a_dot(qapp):
    pen = QPen(QColor("black"), 20.0); pen.setCosmetic(True)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    got, want = _split_vs_plain(pen)
    outside, missing = _close(got, want)
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


# -- m6: AC sweep ---------------------------------------------------------------------------
def test_g2_corner_in_a_block_editor_scene(qapp, monkeypatch):
    """AC8 Block Editor: loose geometry in a scene_role="block_editor" scene
    joins like the plan scene's."""
    a, b = _corner_pair()
    sc = Model_Space(scene_role="block_editor")
    img = _render([a, b], monkeypatch=monkeypatch, scene=sc)
    assert _core(150, 150) <= _dark(img)


def test_polyline_end_joins_an_arc_end(qapp, monkeypatch):
    """AC3 non-line ends: a PolylineItem end meets an ArcItem end at a right
    angle; the corner is the mitered corner of the combined path."""
    from firepro3d.geometry_2d import ArcItem
    from firepro3d.stroke_joints import ends_of_pieces
    arc = ArcItem(QPointF(150, 150), 60.0, 0.0, 90.0)
    fin = [e for e in ends_of_pieces(arc.stroke_pieces(), arc) if e.which == "finish"][0]
    e = QPointF(fin.x, fin.y)
    ax, ay = fin.away                                              # into the arc
    d = (-ay, ax)                                                  # a right turn off the tangent
    far = QPointF(e.x() + d[0] * 70.0, e.y() + d[1] * 70.0)
    poly = PolylineItem(e)
    poly.append_point(far)
    path = QPainterPath(arc.path())
    path.lineTo(far)
    img = _render([arc, poly], size=(300, 300), monkeypatch=monkeypatch)
    outside, missing = _compare(img, path, size=(300, 300))
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


def test_g6_mirrored_rotated_block_triangle_is_mitered(qapp, monkeypatch):
    """AC8: the mirrored pose (local x -> -x, innermost; det < 0) paints its
    joints: an ASYMMETRIC triangle, mirrored then turned 30 deg."""
    _patch_px(monkeypatch)
    sc = Model_Space()
    loc = [QPointF(-100, 60), QPointF(100, 60), QPointF(60, -100)]
    d = _block_def(_prims([LineItem(loc[0], loc[1]), LineItem(loc[1], loc[2]),
                           LineItem(loc[2], loc[0])]))
    sc.register_block_definition(d)
    sc.place_block_instance(d.id, (_BP.x(), _BP.y()), rotation=30.0,
                            level=sc.active_level, mirrored=True)
    t = QTransform(); t.translate(_BP.x(), _BP.y()); t.rotate(-30.0)
    pts = [t.map(QPointF(-p.x(), p.y())) for p in loc]
    oracle = QPainterPath(pts[0]); oracle.lineTo(pts[1]); oracle.lineTo(pts[2]); oracle.closeSubpath()
    img = _render([], size=_BSIZE, monkeypatch=monkeypatch, scene=sc)
    outside, missing = _compare(img, oracle, size=_BSIZE)
    assert not outside and not missing, (sorted(outside)[:5], sorted(missing)[:5])


def test_g6_loose_corner_on_a_sheet_pdf_is_mitered(qapp, tmp_path, monkeypatch):
    """AC8: two LOOSE LineItems (no block) through the real paper_export
    path: the paper pass fills the wedge in the item frame (non-cosmetic
    pen). PyMuPDF rasterises the corner at high zoom: the exterior square
    of the right-angle corner is inked."""
    import fitz
    from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
    from tests.test_lt1_block_paper import _VP_W, _VP_X, _VP_Y, _export
    save_paper_color_mode(PaperColorMode.BW)
    scale = 0.02
    ms = Model_Space()
    for it in (LineItem(QPointF(-1000, 500), QPointF(0, 500)),
               LineItem(QPointF(0, 500), QPointF(0, -500))):
        ms.addItem(it); ms._draw_lines.append(it)
    pdf = _export(tmp_path, ms, scale, "corner.pdf")
    pt_mm = 25.4 / 72.0
    z = 24.0
    cx, cy = _VP_X + _VP_W / 2.0, _VP_Y + _VP_W / 2.0
    px, py = cx / pt_mm, (cy + 500.0 * scale) / pt_mm      # the corner, in pt
    doc = fitz.open(str(pdf))
    try:
        page = doc[0]
        widths = [dr["width"] for dr in page.get_drawings()
                  if "s" in (dr.get("type") or "")
                  and ((abs(dr["rect"].x1 - px) < 3 and dr["rect"].height > 5)
                       or (abs(dr["rect"].y1 - py) < 3 and dr["rect"].width > 5))]
        assert widths, "premise: the corner strokes are in the PDF"
        half = max(widths) / 2.0
        clip = fitz.Rect(px - 6, py - 6, px + 6, py + 6)
        pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=clip,
                              colorspace=fitz.csGRAY, alpha=False)
        n, w, s = pix.n, pix.width, pix.samples
        # Locate the arms' outer edges from the raster itself (the pixmap origin
        # is integer-snapped): the vertical arm alone inks row 0, the horizontal
        # arm alone inks column 0. The exterior square is bounded by exactly
        # those two edges (right edge of the vertical arm, bottom edge of the
        # horizontal arm); a flat corner leaves it white.
        dark = lambda i, j: s[(j * w + i) * n] < 128
        xr = max(i for i in range(w) if dark(i, 0))
        yb = max(j for j in range(pix.height) if dark(0, j))
        for d in (3, 4):                                # inside the square, off its AA edge
            assert dark(xr - d, yb - d), (d, xr, yb)
    finally:
        doc.close()
