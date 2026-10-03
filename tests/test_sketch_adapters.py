"""sketch_adapters — handles agree with grip_points(); write_back round-trips.

Convention guards (parametric-constraint-system.md §5.1/§5.3): every handle the
adapter derives must equal the item's OWN ``grip_points()`` (rotated rects incl.
an explicit pivot, Y-up arcs), analytic derivatives must equal finite
differences, and a write-back must move the item's observable geometry.
"""
import math

import numpy as np
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem, PolylineItem,
                                   RectangleItem, ReferenceLineItem, RegularPolygonItem,
                                   SplineItem)
from firepro3d.sketch_adapters import ANG_W, GRIP_HANDLES, W_SIZE, adapter_for
from firepro3d.sketch_solver import ANG_SCALE
from firepro3d.text_item import TextAnnotationData, TextItem


def _pt(expr, x):
    p, _ = expr.eval(x)
    return p


def _close(p, q, tol=1e-6):
    return abs(p[0] - q.x()) < tol and abs(p[1] - q.y()) < tol


def _qclose(a, b, tol=1e-6):
    return abs(a.x() - b.x()) < tol and abs(a.y() - b.y()) < tol


def _polyline(closed=False):
    p = PolylineItem(QPointF(0, 0))
    for q in (QPointF(10, 0), QPointF(10, 10)):
        p.append_point(q)
    if closed:
        p.close()
    return p


def _rotated_rect():
    r = RectangleItem(QPointF(0, 0), QPointF(100, 40))
    r.set_angle(25.0)
    return r


_MAKERS = {
    "line": lambda: LineItem(QPointF(0, 0), QPointF(40, 10)),
    "reference_line": lambda: ReferenceLineItem(QPointF(0, 0), QPointF(40, 10)),
    "circle": lambda: CircleItem(QPointF(5, 5), 20),
    "rect": lambda: RectangleItem(QPointF(0, 0), QPointF(50, 30)),
    "rect_rotated": _rotated_rect,
    "arc": lambda: ArcItem(QPointF(3, 4), 10.0, 20.0, 110.0),
    "polyline": _polyline,
    "polyline_closed": lambda: _polyline(closed=True),
    "polygon": lambda: RegularPolygonItem(QPointF(5, 6), sides=6, radius_mm=20.0,
                                          rotation_deg=15.0),
    "polygon_circ": lambda: RegularPolygonItem(QPointF(-4, 9), sides=5, radius_mm=12.0,
                                               rotation_deg=-35.0, inscribed=False),
    "ellipse": lambda: EllipseItem(QPointF(5, 6), 30.0, 12.0, rotation_deg=20.0),
    "text": lambda: TextItem(TextAnnotationData(text="Hi", x=12.0, y=-7.0)),
    "block": lambda: _block(),
}


def _block():
    b = BlockInstance(block_id="b", resolver=lambda _bid: None)
    b.set_block_pos(4.0, 9.0)
    return b


# ── handle points == the item's own grip_points (convention guard) ──────────

@pytest.mark.parametrize("angle,pivot", [(0.0, None), (30.0, None), (-75.0, None),
                                         (40.0, QPointF(5, 7)), (-120.0, QPointF(-30, 90))])
def test_rect_points_match_grip_points(qapp, angle, pivot):
    r = RectangleItem(QPointF(10, 20), QPointF(130, 80))
    r.set_angle(angle, pivot)
    ad = adapter_for(r)
    x = np.array(ad.read(r))
    pts = ad.points(r, 0)
    grips = r.grip_points()
    for i, name in GRIP_HANDLES["draw_rectangle"].items():
        assert _close(_pt(pts[name], x), grips[i]), (i, name)


@pytest.mark.parametrize("key", ["line", "reference_line", "circle", "rect", "rect_rotated",
                                 "arc", "polyline", "polyline_closed", "polygon",
                                 "polygon_circ", "ellipse"])
def test_every_mapped_grip_index_names_its_grip_point(qapp, key):
    """§5.3: grip index -> handle name -> point equals grip_points()[index]."""
    it = _MAKERS[key]()
    ad = adapter_for(it)
    x = np.array(ad.read(it))
    pts = ad.points(it, 0)
    grips = it.grip_points()
    mapped = 0
    for i in range(len(grips)):
        name = ad.grip_handle(it, i)
        if name is None:
            continue
        mapped += 1
        assert _close(_pt(pts[name], x), grips[i]), (key, i, name)
    assert mapped >= 1


def test_ins_handle_is_the_insertion_point(qapp):
    t = _MAKERS["text"]()
    ad = adapter_for(t)
    x = np.array(ad.read(t))
    assert _close(_pt(ad.points(t, 0)["ins"], x), t.pos())
    b = _block()
    ad = adapter_for(b)
    x = np.array(ad.read(b))
    assert _close(_pt(ad.points(b, 0)["ins"], x), b.pose_transform().map(QPointF(0, 0)))


def test_line_translate_grip_is_not_a_handle(qapp):
    ln = _MAKERS["line"]()
    ad = adapter_for(ln)
    assert ad.grip_handle(ln, 1) is None
    assert ad.pin_vars(ln, 0) == (0, 1)
    assert ad.pin_vars(ln, 2) == (2, 3)
    assert ad.pin_vars(ln, 1) == (0, 1, 2, 3)          # translate grip pins all


def test_rect_derived_grip_pins_every_var(qapp):
    r = _rotated_rect()
    assert adapter_for(r).pin_vars(r, 0) == (0, 1, 2, 3, 4)


# ── analytic derivatives == finite differences ──────────────────────────────

@pytest.mark.parametrize("key", ["rect", "rect_rotated", "arc", "line", "circle",
                                 "polyline_closed", "polygon", "polygon_circ", "ellipse"])
def test_derivatives_match_finite_differences(qapp, key):
    it = _MAKERS[key]()
    ad = adapter_for(it)
    off = 3                                             # non-zero offset exercises idx
    x = np.concatenate([np.array([7.0, -2.0, 11.0]), np.array(ad.read(it))])
    exprs = dict(ad.points(it, off))
    for ename, (a, b) in ad.edges(it, off).items():
        exprs[ename + ".a"], exprs[ename + ".b"] = a, b
    for name, e in exprs.items():
        assert all(d >= off for d in e.deps), name
        _, dp = e.eval(x)
        assert dp.shape == (2, len(e.deps)), name
        for c, d in enumerate(e.deps):
            h = np.zeros_like(x); h[d] = 1e-6
            fd = (_pt(e, x + h) - _pt(e, x - h)) / 2e-6
            assert np.allclose(fd, dp[:, c], atol=1e-5), (name, d)


# ── arc Y-up convention ─────────────────────────────────────────────────────

def test_arc_endpoints_follow_the_y_up_convention(qapp):
    a = ArcItem(QPointF(0, 0), 10.0, 0.0, 90.0)
    ad = adapter_for(a)
    x = np.array(ad.read(a))
    pts = ad.points(a, 0)
    assert _close(_pt(pts["start"], x), a.grip_points()[1])
    assert _close(_pt(pts["end"], x), a.grip_points()[2])
    end = _pt(pts["end"], x)
    assert abs(end[0]) < 1e-9 and end[1] == pytest.approx(-10.0)   # 90° Y-up = screen-UP


# ── edges ───────────────────────────────────────────────────────────────────

def test_polyline_segments_include_the_closing_one(qapp):
    p = _polyline(closed=True)
    assert p.is_closed()
    edges = adapter_for(p).edges(p, 0)
    assert set(edges) == {"s0", "s1", "s2"}
    x = np.array(adapter_for(p).read(p))
    a, b = edges["s2"]
    assert _close(_pt(a, x), p.grip_points()[2]) and _close(_pt(b, x), p.grip_points()[0])


def test_open_polyline_has_no_closing_segment(qapp):
    p = _polyline()
    assert set(adapter_for(p).edges(p, 0)) == {"s0", "s1"}


def test_rect_edges_follow_the_local_frame(qapp):
    r = _rotated_rect()
    ad = adapter_for(r)
    x = np.array(ad.read(r))
    g = r.grip_points()
    want = {"top": (0, 2), "right": (2, 4), "bottom": (4, 6), "left": (6, 0)}
    for name, (ia, ib) in want.items():
        a, b = ad.edges(r, 0)[name]
        assert _close(_pt(a, x), g[ia]) and _close(_pt(b, x), g[ib]), name


# ── D28 / D34 weights ───────────────────────────────────────────────────────

def test_nvars_equals_len_read_for_every_adapter(qapp):
    """D18: nvars is answered without a read -- it must still equal it."""
    for key, make in _MAKERS.items():
        it = make()
        ad = adapter_for(it)
        if ad is None:
            continue
        assert ad.nvars(it) == len(ad.read(it)), key
    pl = _polyline()
    pl.append_point(QPointF(77, 11))
    assert adapter_for(pl).nvars(pl) == len(adapter_for(pl).read(pl))


def test_angle_variables_carry_the_d28_weight(qapp):
    """D28: angles ANG_W. D34 (fix round A, VC5 -- this test's size entries
    were 1 before the ruling): sizes (rect w/h, circle / arc r, polygon R,
    ellipse rx/ry) carry W_SIZE; positions 1."""
    assert ANG_W == ANG_SCALE ** 2
    assert 1.0 < W_SIZE < ANG_W
    exp = {"rect": [1, 1, W_SIZE, W_SIZE, ANG_W], "arc": [1, 1, W_SIZE, ANG_W, ANG_W],
           "polygon": [1, 1, W_SIZE, ANG_W], "ellipse": [1, 1, W_SIZE, W_SIZE, ANG_W],
           "line": [1, 1, 1, 1], "circle": [1, 1, W_SIZE], "text": [1, 1], "block": [1, 1]}
    for key, w in exp.items():
        it = _MAKERS[key]()
        ad = adapter_for(it)
        assert ad.var_weights(it) == w, key
        assert ad.nvars(it) == len(w), key


# ── D33: polygon vertex / edge handles ─────────────────────────────────────

@pytest.mark.parametrize("inscribed", [True, False])
@pytest.mark.parametrize("sides,rot", [(3, 0.0), (5, 17.5), (6, -100.0), (8, 222.0)])
def test_polygon_vertices_are_its_grip_points(qapp, sides, rot, inscribed):
    """D33: v_i == grip_points()[i + 1] (the §5.3 map 0 = centre, 1..n =
    vertices) for both radius meanings; s_i = v_i -> v_(i+1), closing one
    included; the grip map names them."""
    it = RegularPolygonItem(QPointF(12, -7), sides=sides, radius_mm=30.0,
                            rotation_deg=rot, inscribed=inscribed)
    ad = adapter_for(it)
    x = np.array(ad.read(it))
    pts, edges = ad.points(it, 0), ad.edges(it, 0)
    g = it.grip_points()
    assert len(g) == sides + 1
    assert ad.grip_handle(it, 0) == "center"
    assert _close(_pt(pts["center"], x), g[0])
    for i in range(sides):
        assert ad.grip_handle(it, i + 1) == f"v{i}"
        assert _close(_pt(pts[f"v{i}"], x), g[i + 1]), i
        a, b = edges[f"s{i}"]
        assert _close(_pt(a, x), g[i + 1]) and _close(_pt(b, x), g[(i + 1) % sides + 1]), i
    assert ad.grip_handle(it, sides + 1) is None
    assert set(edges) == {f"s{i}" for i in range(sides)}


def test_polygon_vertex_grip_pins_every_var(qapp):
    it = _MAKERS["polygon"]()
    assert adapter_for(it).pin_vars(it, 3) == (0, 1, 2, 3)


# ── write-back moves the item's own observable geometry ─────────────────────

D = 1.5


def _yup_deg(p, q):
    return math.degrees(math.atan2(-(q.y() - p.y()), q.x() - p.x()))


def _ang_eq(a_deg, b_deg, tol=1e-6):
    d = (a_deg - b_deg + 180.0) % 360.0 - 180.0
    return abs(d) < tol


@pytest.mark.parametrize("key", list(_MAKERS))
def test_write_back_round_trips(qapp, key):
    it = _MAKERS[key]()
    ad = adapter_for(it)
    vals = np.array(ad.read(it)) + D
    ad.write(it, vals)
    v = vals
    if key in ("line", "reference_line"):
        g = it.grip_points()
        assert _close(v[0:2], g[0]) and _close(v[2:4], g[2])
        ln = it.line()
        assert _close(v[0:2], ln.p1()) and _close(v[2:4], ln.p2())
    elif key == "circle":
        g = it.grip_points()
        assert _close(v[0:2], g[0])
        assert math.hypot(g[1].x() - g[0].x(), g[1].y() - g[0].y()) == pytest.approx(v[2])
        assert it.rect().center().x() == pytest.approx(v[0])
        assert it.rect().width() == pytest.approx(2 * v[2])
    elif key in ("rect", "rect_rotated"):
        g = it.grip_points()
        cx, cy, w, h, th = v
        assert _close((cx, cy), g[8])
        assert math.hypot(g[2].x() - g[0].x(), g[2].y() - g[0].y()) == pytest.approx(w)
        assert math.hypot(g[4].x() - g[2].x(), g[4].y() - g[2].y()) == pytest.approx(h)
        assert _ang_eq(_yup_deg(g[0], g[2]), math.degrees(th))      # TL->TR is +u, Y-up
        assert it._pivot is None                                     # §5.1 canonicalised
    elif key == "arc":
        cx, cy, r, ts, te = v
        g = it.grip_points()
        assert _close((cx, cy), g[0])
        assert _close((cx + r * math.cos(ts), cy - r * math.sin(ts)), g[1])
        assert _close((cx + r * math.cos(te), cy - r * math.sin(te)), g[2])
        # The rendered path (Qt's own arcMoveTo, Y-up angles) starts at `start`.
        # Qt locates arc points on its Bezier quadrant approximation (~5e-3 mm
        # off here), so the bar is 0.02 mm — a handedness slip is ~r off.
        e0 = it.path().elementAt(0)
        assert _close((e0.x, e0.y), g[1], tol=0.02)
        assert it._span_deg > 0
    elif key.startswith("polyline"):
        g = it.grip_points()
        for i, q in enumerate(g):
            assert _close(v[2 * i:2 * i + 2], q), i
        path = it.path()
        assert _close(v[0:2], QPointF(path.elementAt(0).x, path.elementAt(0).y))
    elif key.startswith("polygon"):
        cx, cy, rad, rot = v
        n = it._sides
        # _radius_mm is the circumradius when inscribed, else the apothem
        # (vertex 0 then sits half a step past the rotation).
        rv = rad if it._inscribed else rad / math.cos(math.pi / n)
        off = 0.0 if it._inscribed else 180.0 / n
        g = it.grip_points()
        assert _close((cx, cy), g[0])
        assert math.hypot(g[1].x() - cx, g[1].y() - cy) == pytest.approx(rv)
        assert _ang_eq(_yup_deg(g[0], g[1]), math.degrees(rot) + off)
        # The rendered outline moved too (grip_points reads fields, not the path).
        e0 = it.path().elementAt(0)
        assert _close((e0.x, e0.y), g[1])
    elif key == "ellipse":
        cx, cy, rx, ry, rot = v
        g = it.grip_points()
        assert _close((cx, cy), g[0])
        assert math.hypot(g[1].x() - cx, g[1].y() - cy) == pytest.approx(rx)
        assert math.hypot(g[3].x() - cx, g[3].y() - cy) == pytest.approx(ry)
        assert _ang_eq(_yup_deg(g[0], g[1]), math.degrees(rot))
        assert _close((cx, cy), it.path().boundingRect().center(), tol=1e-6)
    elif key == "text":
        assert _close(v, it.pos())
        assert (it._data.x, it._data.y) == pytest.approx((v[0], v[1]))
    elif key == "block":
        assert it.block_pos() == pytest.approx((v[0], v[1]))
        assert _close(v, it.pose_transform().map(QPointF(0, 0)))
    else:                                                # pragma: no cover
        pytest.fail(f"no observable check for {key}")
    # ...and the adapter re-reads what it wrote (angles modulo 2π).
    back = np.array(ad.read(it))
    diff = back - vals
    diff = np.where(np.abs(diff) > 6.0, (diff + math.pi) % (2 * math.pi) - math.pi, diff)
    assert np.allclose(diff, 0.0, atol=1e-9), (key, back, vals)


def test_rect_write_back_canonicalises_an_explicit_pivot_without_moving(qapp):
    r = RectangleItem(QPointF(10, 20), QPointF(130, 80))
    r.set_angle(40.0, QPointF(5, 7))
    before = [QPointF(p) for p in r.grip_points()]
    ad = adapter_for(r)
    ad.write(r, np.array(ad.read(r)))
    assert r._pivot is None
    for a, b in zip(before, r.grip_points()):
        assert _qclose(a, b)


# ── registry ────────────────────────────────────────────────────────────────

def test_spline_is_excluded(qapp):
    s = SplineItem([QPointF(0, 0), QPointF(10, 10), QPointF(20, 0), QPointF(30, 10)])
    assert adapter_for(s) is None


def test_reference_line_gets_its_own_type_key(qapp):
    assert adapter_for(_MAKERS["reference_line"]()).type_key == "reference_line"
    assert adapter_for(_MAKERS["line"]()).type_key == "draw_line"


def test_type_keys_match_to_dict(qapp):
    for key in ("line", "reference_line", "circle", "rect", "arc", "polyline",
                "polygon", "ellipse", "text"):
        it = _MAKERS[key]()
        assert adapter_for(it).type_key == it.to_dict()["type"], key
    b = _block()
    assert adapter_for(b).type_key == b.to_nested_dict()["type"]
