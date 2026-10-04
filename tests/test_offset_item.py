"""D9: offset_item per primitive — type preserved, style inherited, true distances.

scene-tools.md D9: Line/RefLine → parallel of the SAME type; open polyline →
mitered parallel (ends perpendicular to the end segment, interior vertices at
the offset legs' intersection); open spline → the same on its control
(reference) polygon (amended 2026-09-29); closed polyline / closed spline /
zero-chord chain → its (control) loop ±d, mitered at every vertex incl. the
seam; Rect (incl.
rotated) → rect ±d per side, same angle; Circle → concentric r±d (geometric r,
not pen-inflated); Arc → concentric, same angles; Regular polygon → same sides
+ rotation, apothem ±d; Ellipse → rx±d, ry±d; Text → not offsettable.
"""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import tool_geometry as tg
from firepro3d.geometry_2d import ReferenceLineItem
from tests._modify_tools_helpers import PRIMITIVES


def _make(name):
    return PRIMITIVES[name][0]()


def test_line_parallel_same_type(qapp):
    for name in ("line", "refline"):
        src = _make(name)
        new = tg.offset_item(src, 10.0)
        assert type(new) is type(src)                                  # [RED] refline
        a, b = new.grip_points()[0], new.grip_points()[-1]
        assert abs(abs(a.y()) - 10.0) < 1e-6 and abs(abs(b.y()) - 10.0) < 1e-6


def test_refline_keeps_printed_flag(qapp):
    src = _make("refline")
    src.printed = True
    new = tg.offset_item(src, 10.0)
    assert isinstance(new, ReferenceLineItem) and new.printed is True


def test_circle_radius_is_geometric_not_pen_inflated(qapp):
    src = _make("circle")                                 # r = 50
    new = tg.offset_item(src, 10.0)
    assert new._radius == pytest.approx(60.0)             # [RED] (was 63)
    assert (new._center.x(), new._center.y()) == pytest.approx((0.0, 0.0))


def test_closed_polyline_seam_is_offset(qapp):
    src = _make("polyline_closed")                        # square 0..100 x 0..-100
    out = tg.offset_item(src, 10.0)                       # outward
    xs = sorted(round(p.x(), 3) for p in out._points)
    ys = sorted(round(p.y(), 3) for p in out._points)
    assert xs[0] == -10.0 and xs[-1] == 110.0            # [RED] seam
    assert ys[0] == -110.0 and ys[-1] == 10.0
    assert out.is_closed()
    # every vertex is a mitered corner: exactly the 4 offset-square corners
    assert sorted((round(p.x(), 3), round(p.y(), 3)) for p in out._points) == \
        sorted([(-10.0, 10.0), (110.0, 10.0), (110.0, -110.0), (-10.0, -110.0)])


def test_closed_polyline_inward(qapp):
    out = tg.offset_item(_make("polyline_closed"), -10.0)
    assert sorted((round(p.x(), 3), round(p.y(), 3)) for p in out._points) == \
        sorted([(10.0, -10.0), (90.0, -10.0), (90.0, -90.0), (10.0, -90.0)])


def test_open_polyline_mitered(qapp):
    src = _make("polyline_open")                          # (0,0)-(100,0)-(100,-100)
    out = tg.offset_item(src, 10.0)                       # left normal: +y then +x
    pts = [(round(p.x(), 3), round(p.y(), 3)) for p in out._points]
    assert pts == [(0.0, 10.0), (110.0, 10.0), (110.0, -100.0)]
    assert not out.is_closed()


def test_rect_offset_per_side(qapp):
    new = tg.offset_item(_make("rect"), 5.0)              # 100 x 50
    r = new.rect()
    assert (r.width(), r.height()) == pytest.approx((110.0, 60.0))
    assert (r.center().x(), r.center().y()) == pytest.approx((50.0, -25.0))


def test_rotated_rect_keeps_angle(qapp):
    src = _make("rect_rotated")
    new = tg.offset_item(src, 5.0)
    assert new._angle == pytest.approx(30.0)
    r = new.rect()
    assert (r.width(), r.height()) == pytest.approx((110.0, 60.0))
    # every source corner is sqrt(2)*5 from the matching offset corner, and
    # each offset edge is exactly 5 from the source outline
    for g in (new.grip_points()[1], new.grip_points()[3]):   # edge midpoints
        assert tg.distance_to_item(src, g) == pytest.approx(5.0, abs=1e-6)


def test_arc_concentric_same_angles(qapp):
    src = _make("arc")
    new = tg.offset_item(src, 5.0)
    assert new._radius == pytest.approx(55.0)
    assert (new._start_deg, new._span_deg) == pytest.approx(
        (src._start_deg, src._span_deg))


def test_polygon_stays_regular_apothem_plus_d(qapp):
    src = _make("polygon")                                # inscribed, R=50, 6 sides
    new = tg.offset_item(src, 5.0)
    apothem = src._radius_mm * math.cos(math.pi / 6)
    new_apothem = new._radius_mm * math.cos(math.pi / 6)
    assert type(new).__name__ == "RegularPolygonItem" and new._sides == 6
    assert new_apothem == pytest.approx(apothem + 5.0)   # [RED]
    assert new._rotation_deg == pytest.approx(src._rotation_deg)


def test_ellipse_rx_ry_plus_d(qapp):
    new = tg.offset_item(_make("ellipse"), 5.0)          # 80 x 40
    assert (new._rx, new._ry) == pytest.approx((85.0, 45.0))           # [RED]


def test_inward_too_large_returns_none(qapp):
    assert tg.offset_item(_make("circle"), -60.0) is None
    assert tg.offset_item(_make("ellipse"), -45.0) is None
    assert tg.offset_item(_make("rect"), -30.0) is None  # rect half-height 25
    assert tg.offset_item(_make("arc"), -60.0) is None
    assert tg.offset_item(_make("polygon"), -50.0) is None
    assert tg.offset_item(_make("polyline_closed"), -50.0) is None   # collapses
    assert tg.offset_item(_make("polyline_closed"), -60.0) is None   # inverts


def test_text_is_not_offsettable(qapp):
    for name in ("text", "text_rotated"):
        assert tg.offset_item(_make(name), 5.0) is None


def test_style_inherited(qapp):
    from PyQt6.QtGui import QColor
    for name in ("line", "polyline_closed", "rect", "circle", "arc",
                 "polygon", "ellipse", "spline"):
        src = _make(name)
        src.style["colour"] = "#ff0000"
        src.style["weight"] = "Heavy"
        src._sync_stroke_pen()
        if src.is_fillable():
            src.fill_type = "solid"
            src._display_fill_color = "#00ff00"
        new = tg.offset_item(src, 5.0)
        assert new.style == src.style, name
        assert new.style["weight"] == "Heavy", name
        if src.is_fillable():
            assert new.fill_type == "solid", name
            assert new._display_fill_color == "#00ff00", name


def test_source_is_not_mutated(qapp):
    for name in ("line", "polyline_closed", "rect", "circle", "arc",
                 "polygon", "ellipse", "spline", "rect_rotated"):
        src = _make(name)
        before = src.to_dict()
        tg.offset_item(src, 5.0)
        assert src.to_dict() == before, name


def test_distance_to_item_open_polyline_uses_segments(qapp):
    src = _make("polyline_open")                          # (0,0)-(100,0)-(100,-100)
    # point beyond the first segment's end on its infinite line: true distance > 0
    assert tg.distance_to_item(src, QPointF(-50, 0)) == pytest.approx(50.0)   # [RED]


def test_distance_to_item_circle_is_geometric(qapp):
    src = _make("circle")
    assert tg.distance_to_item(src, QPointF(100, 0)) == pytest.approx(50.0, abs=0.05)
    assert tg.distance_to_item(src, QPointF(20, 0)) == pytest.approx(30.0, abs=0.05)


def test_offset_side_sign(qapp):
    # closed: inside -> -1 (inward), outside -> +1
    assert tg.offset_side_sign(_make("circle"), QPointF(1, 0)) == -1.0
    assert tg.offset_side_sign(_make("circle"), QPointF(400, -400)) == 1.0
    assert tg.offset_side_sign(_make("rect_rotated"), QPointF(50, -25)) == -1.0
    assert tg.offset_side_sign(_make("polyline_closed"), QPointF(50, -50)) == -1.0
    # open line: left normal of (0,0)->(100,0) is +y (scene)
    assert tg.offset_side_sign(_make("line"), QPointF(50, 20)) == 1.0
    assert tg.offset_side_sign(_make("line"), QPointF(50, -20)) == -1.0
    # open polyline: the NEAREST segment decides (second leg, x=100 going -y:
    # left normal is +x)
    assert tg.offset_side_sign(_make("polyline_open"), QPointF(120, -80)) == 1.0
    assert tg.offset_side_sign(_make("polyline_open"), QPointF(80, -80)) == -1.0


# ── fix round (review G7) ────────────────────────────────────────────────────

def _closed_spline():
    from firepro3d.geometry_2d import SplineItem
    return SplineItem([QPointF(0, 0), QPointF(100, 0), QPointF(100, -100),
                       QPointF(0, -100), QPointF(0, 0)])


def test_uniform_degenerate_floor(qapp):
    """M-2: an inward offset that leaves (almost) nothing is refused alike."""
    assert tg.OFFSET_MIN_EXTENT_MM > 0
    # hexagon inscribed R=50: apothem 43.301 -> 0.1 left
    assert tg.offset_item(_make("polygon"), -43.2) is None             # [RED]
    # 100 mm square -> 0.2 mm square
    assert tg.offset_item(_make("polyline_closed"), -49.9) is None     # [RED]
    assert tg.offset_item(_make("polyline_closed"), -49.0) is not None
    # rect 100x50 -> 0.2 mm tall
    assert tg.offset_item(_make("rect"), -24.9) is None                # [RED]
    assert tg.offset_item(_make("arc"), -49.9) is None                 # [RED]
    assert tg.offset_item(_make("ellipse"), -39.9) is None


def test_spline_offset_round_trips(qapp):
    from firepro3d.geometry_2d import SplineItem
    new = tg.offset_item(_make("spline"), 5.0)
    back = SplineItem.from_dict(new.to_dict())
    assert back.to_dict() == new.to_dict()



def _closed39():
    import math
    import random
    from firepro3d.geometry_2d import SplineItem
    rnd = random.Random(1)
    [rnd.uniform(-80, 80) for _ in range(40)]
    c = [QPointF(400 * math.cos(2 * math.pi * i / 39) + rnd.uniform(-30, 30),
                 -400 * math.sin(2 * math.pi * i / 39) + rnd.uniform(-30, 30))
         for i in range(39)]
    c.append(QPointF(c[0]))
    return SplineItem(c)


def test_closed_spline_inward_past_its_extent_is_refused(qapp):
    """The control loop's collapse test: inward past its extent -> None."""
    assert tg.offset_item(_closed39(), -420.0) is None
    assert tg.offset_item(_closed_spline(), -60.0) is None


# ── R3-1: an inward closed offset past collapse is refused, not mirrored ────

def _rounded_square():
    from firepro3d.geometry_2d import SplineItem
    P = lambda *xy: [QPointF(x, y) for x, y in xy]
    return SplineItem(P((50, 0), (100, 0), (100, -50), (100, -100), (50, -100),
                        (0, -100), (0, -50), (0, 0), (50, 0)))


@pytest.mark.parametrize("d", [-100.0, -1e4])
def test_inward_closed_offset_past_collapse_is_refused(qapp, d):
    """Past the curvature radius the inward targets come back point-reflected
    (winding kept, source-sized); that must be "Offset too large", not a
    committed mirrored loop."""
    assert tg.offset_item(_rounded_square(), d) is None                 # [RED]


def test_inward_closed_offset_within_reach_still_works(qapp):
    src = _rounded_square()
    new = tg.offset_item(src, -20.0)
    assert new is not None and new.is_closed()
    path = src.get_closed_path()
    assert all(path.contains(q) for q in new.path().toSubpathPolygons()[0])


# ── D9 amended 2026-09-29: per-vertex mitered offset; splines on their control
#    polygon; closed / zero-chord chains wrapped round the loop ────────────────

def _miter_expected(pts, d):
    """Independent reference: ends move d perpendicular to their end leg (left
    normal = + side); each interior vertex is where its offset legs meet."""
    def n(a, b):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        return (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)
    out = []
    for i, p in enumerate(pts):
        if i == 0 or i == len(pts) - 1:
            a, b = (pts[0], pts[1]) if i == 0 else (pts[-2], pts[-1])
            nx, ny = n(a, b)
            out.append((p[0] + d * nx, p[1] + d * ny))
            continue
        (ax, ay), (bx, by) = n(pts[i - 1], p), n(p, pts[i + 1])
        # line 1: p + d*na + s*(p - prev); line 2: p + d*nb + u*(next - p)
        p1 = (p[0] + d * ax, p[1] + d * ay)
        p2 = (p[0] + d * bx, p[1] + d * by)
        r = (p[0] - pts[i - 1][0], p[1] - pts[i - 1][1])
        q = (pts[i + 1][0] - p[0], pts[i + 1][1] - p[1])
        den = r[0] * q[1] - r[1] * q[0]
        s = ((p2[0] - p1[0]) * q[1] - (p2[1] - p1[1]) * q[0]) / den
        out.append((p1[0] + s * r[0], p1[1] + s * r[1]))
    return out


def test_open_spline_offsets_its_control_polygon_mitered(qapp):
    """Open spline: every control point moves per the polyline miter rule on
    the reference polygon; same count, knots, degree, weights."""
    src = _make("spline")                        # (0,0)(50,-60)(100,0)(150,-40)
    cps = [(p.x(), p.y()) for p in src._control_points]
    for d in (7.0, -12.0):
        out = tg.offset_item(src, d)
        assert type(out) is type(src) and not out.is_closed()
        assert out._degree == src._degree and out._knots == src._knots
        assert out._weights == src._weights
        got = [(q.x(), q.y()) for q in out._control_points]
        assert len(got) == len(cps)                                     # [RED]
        for g, e in zip(got, _miter_expected(cps, d)):
            assert g == pytest.approx(e, abs=1e-6)


def test_open_polyline_matches_the_miter_reference(qapp):
    pts = [(0, 0), (100, 0), (100, -100)]
    out = tg.offset_item(_make("polyline_open"), 10.0)
    for g, e in zip([(q.x(), q.y()) for q in out._points], _miter_expected(pts, 10.0)):
        assert g == pytest.approx(e, abs=1e-6)


def _zero_chord_polyline():
    from firepro3d.geometry_2d import PolylineItem
    p = PolylineItem(QPointF(0, 0))
    for q in [(100, 0), (100, -100), (0, -100), (0, 0)]:
        p.append_point(QPointF(*q))
    return p                                   # OPEN, end points coincide


@pytest.mark.parametrize("d, sq", [(30.0, (-30, 30, 130, -130)), (-20.0, (20, -20, 80, -80))])
def test_zero_chord_polyline_offsets_its_loop(qapp, d, sq):
    src = _zero_chord_polyline()
    assert not src.is_closed()
    out = tg.offset_item(src, d)
    x0, y0, x1, y1 = sq
    assert [(round(p.x(), 3), round(p.y(), 3)) for p in out._points] ==         [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]             # [RED]
    assert not out.is_closed()
    assert tg.offset_side_sign(src, QPointF(130, -50)) == 1.0          # outside
    assert tg.offset_side_sign(src, QPointF(80, -50)) == -1.0          # inside
    assert tg.distance_to_item(src, QPointF(130, -50)) == pytest.approx(30.0)


def test_zero_chord_two_point_chain_is_refused(qapp):
    from firepro3d.geometry_2d import PolylineItem
    p = PolylineItem(QPointF(5, 5)); p.append_point(QPointF(5, 5))
    assert tg.offset_item(p, 10.0) is None


def test_closed_spline_offsets_its_control_loop_and_keeps_fill(qapp):
    """Closed spline (first == last control point): control loop ±d, mitered
    at every vertex incl. the seam; stays closed, keeps its fill, same knots."""
    src = _closed_spline()                      # square loop 100 x 100
    src.fill_type = "solid"
    out = tg.offset_item(src, 5.0)
    assert out.is_closed() and out.fill_type == "solid" and out.is_fillable()
    assert out._knots == src._knots
    assert [(round(p.x(), 3), round(p.y(), 3)) for p in out._control_points] ==         [(-5, 5), (105, 5), (105, -105), (-5, -105), (-5, 5)]
    inward = tg.offset_item(src, -5.0)
    assert [(round(p.x(), 3), round(p.y(), 3)) for p in inward._control_points] ==         [(5, -5), (95, -5), (95, -95), (5, -95), (5, -5)]              # [RED]
    assert tg.offset_side_sign(src, QPointF(50, -50)) == -1.0
    assert tg.offset_side_sign(src, QPointF(300, -50)) == 1.0
