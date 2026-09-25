"""Per-primitive dimension_specs() + typed setters (2d-geometry.md §8). Pure."""
import math

import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.geometry_2d import LineItem, ReferenceLineItem
from firepro3d.selection_readouts import DimSpec, readout_text
from firepro3d.scale_manager import ScaleManager


def _by_key(item):
    return {s.key: s for s in item.dimension_specs()}


def test_line_length_spec(qapp):
    ln = LineItem(QPointF(0, 0), QPointF(300, 400))
    s = _by_key(ln)["length"]
    assert s.kind == "linear" and s.field == "Length" and s.prefix == ""
    assert s.value == pytest.approx(500.0)
    assert (s.a, s.b) == (QPointF(0, 0), QPointF(300, 400))


def test_line_set_length_keeps_pt1(qapp):
    ln = LineItem(QPointF(10, 10), QPointF(110, 10))
    _by_key(ln)["length"].apply(250.0)
    assert ln.line().p1() == QPointF(10, 10)
    assert ln.line().p2().x() == pytest.approx(260.0)
    assert ln.line().p2().y() == pytest.approx(10.0)


def test_reference_line_inherits_length(qapp):
    rl = ReferenceLineItem(QPointF(0, 0), QPointF(0, 100))
    assert _by_key(rl)["length"].value == pytest.approx(100.0)


def test_default_specs_empty(qapp):
    from firepro3d.geometry_2d import SplineItem
    sp = SplineItem([QPointF(0, 0), QPointF(10, 0), QPointF(20, 10), QPointF(30, 0)])
    assert sp.dimension_specs() == []


def test_readout_text_prefix_and_units(qapp):
    sm = ScaleManager()
    s = DimSpec(kind="linear", key="r", field="Radius", prefix="R",
                value=304.8, field_kind="dimension", apply=lambda v: None,
                a=QPointF(), b=QPointF(1, 0))
    assert readout_text(s, sm) == "R " + sm.format_length(304.8)
    ang = DimSpec(kind="angular", key="a", field="Angle", prefix="",
                  value=270.0, field_kind="span", apply=lambda v: None,
                  center=QPointF(), ref_radius=10.0, start_deg=0.0, span_deg=270.0)
    assert readout_text(ang, sm) == "270°"


from firepro3d.geometry_2d import RectangleItem


def test_rect_specs_width_height(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    d = _by_key(r)
    assert d["width"].value == pytest.approx(200.0)
    assert d["height"].value == pytest.approx(100.0)
    # width measured along the visual bottom edge (BL -> BR), height BR -> TR
    assert d["width"].a == QPointF(0, 100) and d["width"].b == QPointF(200, 100)
    assert d["height"].a == QPointF(200, 100) and d["height"].b == QPointF(200, 0)


@pytest.mark.parametrize("angle", [0.0, 30.0])
def test_rect_set_width_keeps_left_edge(qapp, angle):
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    r.set_angle(angle)
    bl0 = r.mapToScene(QPointF(r.rect().left(), r.rect().bottom()))
    tl0 = r.mapToScene(r.rect().topLeft())
    _by_key(r)["width"].apply(350.0)
    assert r.rect().width() == pytest.approx(350.0)
    bl1 = r.mapToScene(QPointF(r.rect().left(), r.rect().bottom()))
    tl1 = r.mapToScene(r.rect().topLeft())
    assert (bl1.x(), bl1.y()) == pytest.approx((bl0.x(), bl0.y()))
    assert (tl1.x(), tl1.y()) == pytest.approx((tl0.x(), tl0.y()))


@pytest.mark.parametrize("angle", [0.0, 30.0])
def test_rect_set_height_keeps_bottom_edge(qapp, angle):
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    r.set_angle(angle)
    bl0 = r.mapToScene(QPointF(r.rect().left(), r.rect().bottom()))
    br0 = r.mapToScene(QPointF(r.rect().right(), r.rect().bottom()))
    _by_key(r)["height"].apply(40.0)
    assert r.rect().height() == pytest.approx(40.0)
    bl1 = r.mapToScene(QPointF(r.rect().left(), r.rect().bottom()))
    br1 = r.mapToScene(QPointF(r.rect().right(), r.rect().bottom()))
    assert (bl1.x(), bl1.y()) == pytest.approx((bl0.x(), bl0.y()))
    assert (br1.x(), br1.y()) == pytest.approx((br0.x(), br0.y()))


from firepro3d.geometry_2d import CircleItem, ArcItem


def test_circle_radius_spec_and_setter(qapp):
    c = CircleItem(QPointF(50, 60), 100.0)
    s = _by_key(c)["radius"]
    assert s.prefix == "R" and s.value == pytest.approx(100.0)
    assert s.a == QPointF(50, 60) and s.b == QPointF(150, 60)   # single radial, +x
    s.apply(40.0)
    assert c._radius == pytest.approx(40.0) and c._center == QPointF(50, 60)
    assert c.rect().width() == pytest.approx(80.0)


def test_circle_radius_floor(qapp):
    c = CircleItem(QPointF(0, 0), 100.0)
    c.set_radius(0.2)
    assert c._radius == pytest.approx(1.0)       # existing floor (apply_grip)


def test_arc_specs(qapp):
    a = ArcItem(QPointF(0, 0), 100.0, 30.0, 120.0)
    d = _by_key(a)
    ang, rad = d["angle"], d["radius"]
    assert ang.kind == "angular" and ang.field_kind == "span"
    assert ang.value == pytest.approx(120.0)
    assert (ang.start_deg, ang.span_deg, ang.ref_radius) == pytest.approx((30.0, 120.0, 100.0))
    assert ang.maximum < 360.0
    assert rad.prefix == "R" and rad.value == pytest.approx(100.0)
    # radius along the START radial: (r cos30, -r sin30)
    assert (rad.b.x(), rad.b.y()) == pytest.approx((100 * math.cos(math.radians(30)),
                                                    -100 * math.sin(math.radians(30))))


def test_arc_set_span_keeps_start(qapp):
    a = ArcItem(QPointF(0, 0), 100.0, 30.0, 120.0)
    _by_key(a)["angle"].apply(45.0)
    assert a._start_deg == pytest.approx(30.0) and a._span_deg == pytest.approx(45.0)


def test_arc_set_radius_keeps_centre_and_angles(qapp):
    a = ArcItem(QPointF(5, 5), 100.0, 30.0, 120.0)
    _by_key(a)["radius"].apply(250.0)
    assert a._radius == pytest.approx(250.0) and a._center == QPointF(5, 5)
    assert (a._start_deg, a._span_deg) == pytest.approx((30.0, 120.0))


from firepro3d.geometry_2d import EllipseItem, RegularPolygonItem


def test_ellipse_r1_r2(qapp):
    e = EllipseItem(QPointF(0, 0), 300.0, 100.0, 0.0)
    d = _by_key(e)
    assert (d["r1"].field, d["r1"].prefix, d["r1"].value) == ("R1", "R1", pytest.approx(300.0))
    assert (d["r2"].field, d["r2"].prefix, d["r2"].value) == ("R2", "R2", pytest.approx(100.0))
    assert d["r1"].b == QPointF(300, 0)
    assert (d["r2"].b.x(), d["r2"].b.y()) == pytest.approx((0.0, -100.0))
    d["r2"].apply(500.0)            # no swap / renaming — R2 stays the ry axis
    assert e._ry == pytest.approx(500.0) and _by_key(e)["r2"].value == pytest.approx(500.0)


@pytest.mark.parametrize("inscribed", [True, False])
def test_polygon_defining_radius_radial(qapp, inscribed):
    p = RegularPolygonItem(QPointF(0, 0), 6, 100.0, 0.0, inscribed)
    s = _by_key(p)["radius"]
    assert s.prefix == "R" and s.value == pytest.approx(100.0)
    assert (s.b.x(), s.b.y()) == pytest.approx((100.0, 0.0))
    if inscribed:   # radial ends on a vertex
        assert any(math.hypot(v.x() - 100, v.y()) < 1e-6 for v in p.vertices())
    s.apply(50.0)
    assert p._radius_mm == pytest.approx(50.0) and p._sides == 6


from firepro3d.geometry_2d import PolylineItem


def _poly(pts, closed=False):
    p = PolylineItem(QPointF(*pts[0]))
    for x, y in pts[1:]:
        p.append_point(QPointF(x, y))
    if closed:
        p.close()
    return p


def test_polyline_open_segments_and_angles(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100)])          # right, then up (screen)
    d = _by_key(p)
    assert set(d) == {"seg:0", "seg:1", "ang:1"}
    assert d["seg:0"].value == pytest.approx(100.0)
    assert d["ang:1"].value == pytest.approx(90.0)
    assert d["ang:1"].field == "Angle 2" and d["seg:0"].field == "Seg 1"


def test_polyline_angle_is_le_180_side(qapp):
    p = _poly([(0, 0), (100, 0), (0, -10)])             # sharp turn
    a = _by_key(p)["ang:1"]
    assert 0 < a.value <= 180 and a.value == pytest.approx(
        math.degrees(math.atan2(10, 100)), abs=1e-6)


def test_polyline_closed_has_closing_segment_and_all_angles(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100), (0, -100)], closed=True)
    d = _by_key(p)
    assert {"seg:0", "seg:1", "seg:2", "seg:3"} <= set(d)
    assert {"ang:0", "ang:1", "ang:2", "ang:3"} <= set(d)
    assert all(d[f"ang:{i}"].value == pytest.approx(90.0) for i in range(4))


def test_polyline_zero_length_segment_skipped(qapp):
    p = _poly([(0, 0), (100, 0), (100, 0), (100, -50)])
    d = _by_key(p)
    assert "seg:1" not in d and "ang:1" not in d and "ang:2" not in d


def test_set_segment_length_moves_end_vertex_only(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100)])
    _by_key(p)["seg:0"].apply(40.0)
    assert p._points[0] == QPointF(0, 0)
    assert (p._points[1].x(), p._points[1].y()) == pytest.approx((40.0, 0.0))
    assert p._points[2] == QPointF(100, -100)            # downstream untouched


def test_closed_closing_segment_wraps_to_vertex0(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100)], closed=True)
    _by_key(p)["seg:2"].apply(50.0)                       # (100,-100) -> vertex 0
    v2, v0 = p._points[2], p._points[0]
    assert math.hypot(v0.x() - v2.x(), v0.y() - v2.y()) == pytest.approx(50.0)


def test_set_vertex_angle_keeps_side(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100)])
    _by_key(p)["ang:1"].apply(45.0)
    assert _by_key(p)["ang:1"].value == pytest.approx(45.0)
    assert p._points[0] == QPointF(0, 0) and p._points[1] == QPointF(100, 0)
    assert p._points[2].y() < 0                           # still the upper side


# ─────────────────────────────────────────────────────────────────────────
# Fix round: non-finite input hardening, polyline index robustness, floor
# consistency, arc_math reuse, degenerate-spec skipping, undo bookkeeping.
# ─────────────────────────────────────────────────────────────────────────

from firepro3d.model_space import Model_Space


def _rect2():
    return RectangleItem(QPointF(0, 0), QPointF(200, 100))


def _circle2():
    return CircleItem(QPointF(0, 0), 100.0)


def _arc2():
    return ArcItem(QPointF(0, 0), 100.0, 30.0, 120.0)


def _ellipse2():
    return EllipseItem(QPointF(0, 0), 300.0, 100.0, 0.0)


def _polygon2():
    return RegularPolygonItem(QPointF(0, 0), 6, 100.0, 0.0, True)


def _polyline2():
    return _poly([(0, 0), (100, 0), (100, -100)])


_NAN_INF_CASES = [
    ("line_length", lambda: LineItem(QPointF(0, 0), QPointF(100, 0)),
     lambda it: it.set_length,
     lambda it: (QPointF(it.line().p1()), QPointF(it.line().p2()))),
    ("rect_width", _rect2, lambda it: it.set_width, lambda it: QRectF(it.rect())),
    ("rect_height", _rect2, lambda it: it.set_height, lambda it: QRectF(it.rect())),
    ("circle_radius", _circle2, lambda it: it.set_radius,
     lambda it: (QPointF(it._center), it._radius)),
    ("arc_radius", _arc2, lambda it: it.set_radius,
     lambda it: (QPointF(it._center), it._radius, it._start_deg, it._span_deg)),
    ("arc_span", _arc2, lambda it: it.set_span,
     lambda it: (QPointF(it._center), it._radius, it._start_deg, it._span_deg)),
    ("ellipse_rx", _ellipse2, lambda it: it.set_rx, lambda it: (it._rx, it._ry)),
    ("ellipse_ry", _ellipse2, lambda it: it.set_ry, lambda it: (it._rx, it._ry)),
    ("polygon_radius", _polygon2, lambda it: it.set_radius, lambda it: it._radius_mm),
    ("polyline_seg_length", _polyline2,
     lambda it: (lambda v: it.set_segment_length(0, v)),
     lambda it: [QPointF(p) for p in it._points]),
    ("polyline_vertex_angle", _polyline2,
     lambda it: (lambda v: it.set_vertex_angle(1, v)),
     lambda it: [QPointF(p) for p in it._points]),
]


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("name,make,get_setter,snapshot", _NAN_INF_CASES,
                         ids=[c[0] for c in _NAN_INF_CASES])
def test_setters_reject_non_finite(qapp, name, make, get_setter, snapshot, bad):
    it = make()
    before = snapshot(it)
    get_setter(it)(bad)          # must not raise and must not mutate geometry
    after = snapshot(it)
    assert before == after


def test_polyline_set_segment_length_out_of_range_noop(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100)])
    before = [QPointF(pt) for pt in p._points]
    p.set_segment_length(5, 40.0)     # out of range
    p.set_segment_length(-1, 40.0)    # negative
    assert p._points == before


def test_polyline_set_vertex_angle_out_of_range_noop(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100)])
    before = [QPointF(pt) for pt in p._points]
    p.set_vertex_angle(5, 45.0)
    p.set_vertex_angle(-1, 45.0)
    assert p._points == before


def test_polyline_single_vertex_setters_noop(qapp):
    p = PolylineItem(QPointF(0, 0))       # n == 1
    before = [QPointF(pt) for pt in p._points]
    p.set_segment_length(0, 40.0)
    p.set_vertex_angle(0, 45.0)
    assert p._points == before
    assert p.dimension_specs() == []


def test_polyline_zero_points_setters_noop(qapp):
    p = PolylineItem(QPointF(0, 0))
    p._points = []                        # degenerate — robustness only
    p.set_segment_length(0, 40.0)
    p.set_vertex_angle(0, 45.0)
    assert p._points == []
    assert p.dimension_specs() == []


def test_polyline_open_endpoint_angle_noop(qapp):
    # Open polyline: the two endpoint vertices (0 and n-1) are never valid
    # angle indices.
    p = _poly([(0, 0), (100, 0), (100, -100)])
    before = [QPointF(pt) for pt in p._points]
    p.set_vertex_angle(0, 45.0)
    p.set_vertex_angle(2, 45.0)           # n - 1
    assert p._points == before


def test_circle_radius_minimum_just_below_floor(qapp):
    c = CircleItem(QPointF(0, 0), 100.0)
    s = _by_key(c)["radius"]
    assert s.minimum == pytest.approx(1.0 - 1e-9)


def test_arc_radius_minimum_just_below_floor(qapp):
    a = ArcItem(QPointF(0, 0), 100.0, 0.0, 90.0)
    s = _by_key(a)["radius"]
    assert s.minimum == pytest.approx(0.01 - 1e-12)


def test_ellipse_r1_r2_minimum_just_below_floor(qapp):
    from firepro3d.geometry_2d import _AXIS_MIN
    e = EllipseItem(QPointF(0, 0), 300.0, 100.0, 0.0)
    d = _by_key(e)
    assert d["r1"].minimum == pytest.approx(_AXIS_MIN - 1e-9)
    assert d["r2"].minimum == pytest.approx(_AXIS_MIN - 1e-9)


@pytest.mark.parametrize("inscribed", [True, False])
def test_polygon_radial_at_rotation_matches_vertex_or_edge_mid(qapp, inscribed):
    p = RegularPolygonItem(QPointF(0, 0), 6, 100.0, 30.0, inscribed)
    s = _by_key(p)["radius"]
    verts = p.vertices()
    if inscribed:
        assert any(math.hypot(v.x() - s.b.x(), v.y() - s.b.y()) < 1e-6
                   for v in verts)
    else:
        n = len(verts)
        mids = [QPointF((verts[k].x() + verts[(k + 1) % n].x()) / 2,
                        (verts[k].y() + verts[(k + 1) % n].y()) / 2)
               for k in range(n)]
        assert any(math.hypot(m.x() - s.b.x(), m.y() - s.b.y()) < 1e-6
                   for m in mids)


def test_ellipse_radials_at_rotation(qapp):
    e = EllipseItem(QPointF(0, 0), 300.0, 100.0, 40.0)
    d = _by_key(e)
    assert (d["r1"].b.x(), d["r1"].b.y()) == pytest.approx(
        (300 * math.cos(math.radians(40)), -300 * math.sin(math.radians(40))))
    assert (d["r2"].b.x(), d["r2"].b.y()) == pytest.approx(
        (100 * math.cos(math.radians(130)), -100 * math.sin(math.radians(130))))
    d["r1"].apply(500.0)
    assert e._rx == pytest.approx(500.0) and e._ry == pytest.approx(100.0)


def test_set_vertex_angle_keeps_side_cw_turn(qapp):
    p = _poly([(0, 0), (100, 0), (100, 100)])
    _by_key(p)["ang:1"].apply(30.0)
    assert _by_key(p)["ang:1"].value == pytest.approx(30.0)
    assert p._points[0] == QPointF(0, 0) and p._points[1] == QPointF(100, 0)
    assert p._points[2].y() > 0                           # still the lower side


def test_closed_polyline_set_angle_last_vertex_rotates_vertex0_only(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100), (0, -100)], closed=True)
    n = len(p._points)
    before = [QPointF(pt) for pt in p._points]
    _by_key(p)[f"ang:{n - 1}"].apply(60.0)
    for idx in range(1, n - 1):
        assert p._points[idx] == before[idx]
    assert p._points[n - 1] == before[n - 1]
    assert p._points[0] != before[0]


def test_closed_polyline_zero_length_closing_segment_skipped(qapp):
    p = _poly([(0, 0), (100, 0), (100, -100), (0, 0)], closed=True)
    d = _by_key(p)
    n = len(p._points)
    assert f"seg:{n - 1}" not in d


def test_arc_set_span_clamps_ends(qapp):
    a = ArcItem(QPointF(0, 0), 100.0, 0.0, 90.0)
    for v in (-10.0, 0.0, 400.0, 360.0):
        a.set_span(v)
        assert 0.0 < a._span_deg < 360.0


@pytest.mark.parametrize("make,key,val,check", [
    (_ellipse2, "R1", 500.0, lambda it: it._rx),
    (_ellipse2, "R2", 500.0, lambda it: it._ry),
    (_polygon2, "Radius", 50.0, lambda it: it._radius_mm),
])
def test_set_property_pushes_one_undo_step(qapp, make, key, val, check):
    s = Model_Space(scene_role="block_editor")
    it = make()
    s.addItem(it)
    s.push_undo_state()                       # baseline
    pos0 = s._undo_pos
    it.set_property(key, val)
    assert check(it) == pytest.approx(val)
    assert s._undo_pos == pos0 + 1


@pytest.mark.parametrize("make,setter,val,check", [
    (_ellipse2, "set_rx", 500.0, lambda it: it._rx),
    (_ellipse2, "set_ry", 500.0, lambda it: it._ry),
    (_polygon2, "set_radius", 50.0, lambda it: it._radius_mm),
])
def test_pure_setters_push_no_undo(qapp, make, setter, val, check):
    s = Model_Space(scene_role="block_editor")
    it = make()
    s.addItem(it)
    s.push_undo_state()
    pos0 = s._undo_pos
    getattr(it, setter)(val)
    assert check(it) == pytest.approx(val)
    assert s._undo_pos == pos0


@pytest.mark.parametrize("make,key,val,check", [
    (lambda: LineItem(QPointF(0, 0), QPointF(100, 0)), "Length", 250.0,
     lambda it: it.line().length()),
    (lambda: RectangleItem(QPointF(0, 0), QPointF(100, 50)), "Width", 80.0,
     lambda it: it.rect().width()),
    (lambda: RectangleItem(QPointF(0, 0), QPointF(100, 50)), "Height", 30.0,
     lambda it: it.rect().height()),
    (lambda: CircleItem(QPointF(0, 0), 100.0), "Radius", 60.0, lambda it: it._radius),
    (lambda: ArcItem(QPointF(0, 0), 100.0, 0.0, 90.0), "Radius", 70.0, lambda it: it._radius),
    (lambda: ArcItem(QPointF(0, 0), 100.0, 0.0, 90.0), "Span", 200.0, lambda it: it._span_deg),
])
def test_panel_rows_editable_and_undoable(qapp, make, key, val, check):
    s = Model_Space(scene_role="block_editor")
    it = make()
    s.addItem(it)
    s.push_undo_state()                       # baseline
    row = it.get_properties()[key]
    assert row["type"] == "dimension"
    pos0 = s._undo_pos
    it.set_property(key, val)
    assert check(it) == pytest.approx(val)
    assert s._undo_pos == pos0 + 1            # exactly one undo step


def test_span_row_formats_unsigned(qapp):
    a = ArcItem(QPointF(0, 0), 100.0, 0.0, 270.0)
    assert a.get_properties()["Span"]["value"] == "270°"
