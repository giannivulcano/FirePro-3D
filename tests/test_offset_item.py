"""D9: offset_item per primitive — type preserved, style inherited, true distances.

scene-tools.md D9: Line/RefLine → parallel of the SAME type; open polyline →
mitered parallel; closed polyline → closed, mitered at every vertex incl. the
seam; Rect (incl. rotated) → rect ±d per side, same angle; Circle → concentric
r±d (geometric r, not pen-inflated); Arc → concentric, same angles; Regular
polygon → same sides + rotation, apothem ±d; Ellipse → rx±d, ry±d; Spline →
spline approximating the offset curve; Text → not offsettable.
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
        pen = src.pen(); pen.setColor(QColor("#ff0000")); pen.setWidthF(3.0)
        src.setPen(pen)
        if src.is_fillable():
            src.fill_type = "solid"
            src._display_fill_color = "#00ff00"
        new = tg.offset_item(src, 5.0)
        assert new.pen().color().name() == "#ff0000", name
        assert new.pen().widthF() == pytest.approx(3.0), name
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


def test_spline_offset_is_approximately_d(qapp):
    src = _make("spline")
    new = tg.offset_item(src, 5.0)
    assert type(new).__name__ == "SplineItem"
    # Measured at the offset CURVE's midpoint (a control point is off-curve,
    # so its distance to the source says nothing about the offset).
    poly = new.path().toSubpathPolygons()[0]
    d = tg.distance_to_item(src, poly.at(poly.count() // 2))
    assert d == pytest.approx(5.0, rel=0.35)


def test_spline_offset_curve_stays_near_d(qapp):
    """The offset CURVE (not just a control point) stays ~d from the source."""
    src = _make("spline")
    new = tg.offset_item(src, 5.0)
    poly = new.path().toSubpathPolygons()[0]
    n = poly.count()
    ds = [tg.distance_to_item(src, poly.at(i)) for i in range(n // 10, n - n // 10)]
    assert min(ds) == pytest.approx(5.0, rel=0.35)
    assert max(ds) == pytest.approx(5.0, rel=0.35)


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


def test_closed_spline_offsets_closed_and_keeps_fill(qapp):
    """I-2: a closed spline (first == last control point) offsets to a closed
    spline — seam included — and keeps its fill; its side is inside/outside."""
    src = _closed_spline()
    assert src.is_closed()
    src.fill_type = "solid"
    out = tg.offset_item(src, 5.0)
    assert out.is_closed()                                            # [RED]
    assert out.fill_type == "solid" and out.is_fillable()
    # outward: the loop grew on every side (seam corner included)
    cps = out._control_points
    assert (cps[0].x(), cps[0].y()) == pytest.approx((-5.0, 5.0))
    inward = tg.offset_item(src, -5.0)
    assert inward.is_closed()
    # inner seam corner: trimmed where the TRUE offset's head and tail cross
    # (the source is rounded near its seam, so this is not the control-loop
    # corner (5, -5)); the seam point sits d from the source curve.
    import numpy as np
    seam = inward._control_points[0]
    S = _exact_pts(src, 20000)
    gap = float(_seg_dists(np.array([[seam.x(), seam.y()]]), S)[0])
    assert gap == pytest.approx(5.0, rel=0.01)
    assert src.get_closed_path().contains(seam)
    # side: inside -> -1, outside -> +1, whatever the winding
    assert tg.offset_side_sign(src, QPointF(50, -50)) == -1.0          # [RED]
    assert tg.offset_side_sign(src, QPointF(300, -50)) == 1.0


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


# ── I-3: spline offset fits the TRUE offset curve (review G7, Option A) ──────
# Error is measured by an independent exact evaluator (ezdxf BSpline on the
# items' own control points / knots), over ALL interior samples of the result.

def _exact_pts(spline, m):
    import numpy as np
    from ezdxf.math import BSpline
    cps = [(p.x(), p.y()) for p in spline._control_points]
    b = BSpline(cps, order=spline._degree + 1, knots=spline._knots,
                weights=spline._weights)
    k = list(b.knots())
    t0, t1 = k[spline._degree], k[-spline._degree - 1]
    return np.array([tuple(v)[:2] for v in b.points(np.linspace(t0, t1, m))])


def _seg_dists(pts, poly):
    """Distance from each of *pts* to the polyline *poly* (numpy arrays)."""
    import numpy as np
    a, b = poly[:-1], poly[1:]
    ab = b - a
    L2 = np.maximum((ab ** 2).sum(1), 1e-18)
    out = np.empty(len(pts))
    for i, p in enumerate(pts):
        t = np.clip(((p - a) * ab).sum(1) / L2, 0.0, 1.0)
        out[i] = np.min(np.hypot(*(a + t[:, None] * ab - p).T))
    return out


def _open_spline_error(src, new, d):
    """Max |dist(new curve, source curve) - |d|| / |d| over interior samples."""
    import numpy as np
    S = _exact_pts(src, 6000)
    N = _exact_pts(new, 1500)[30:-30]           # interior (ends are pinned exact)
    return float(np.max(np.abs(_seg_dists(N, S) - abs(d))) / abs(d))


@pytest.mark.parametrize("d", [5.0, 20.0, -5.0, -20.0])
def test_open_spline_offset_within_2pct(qapp, d):
    src = _make("spline")
    new = tg.offset_item(src, d)
    assert type(new).__name__ == "SplineItem" and not new.is_closed()
    assert new._degree == src._degree
    err = _open_spline_error(src, new, d)
    assert err <= 0.02, f"max error {err:.2%} of d"                  # [RED] (~27 %)
    # clamped knots: the curve starts/ends exactly on the offset endpoints
    k = new._knots
    assert k[:new._degree + 1] == [k[0]] * (new._degree + 1)
    assert k[-new._degree - 1:] == [k[-1]] * (new._degree + 1)
    # capped control-point count
    assert len(new._control_points) <= 4 * len(src._control_points)


def test_open_spline_offset_side_matches_offset_side_sign(qapp):
    src = _make("spline")
    new = tg.offset_item(src, 5.0)
    mid = _exact_pts(new, 101)[50]
    from PyQt6.QtCore import QPointF as P
    assert tg.offset_side_sign(src, P(float(mid[0]), float(mid[1]))) == 1.0


def test_spline_offset_round_trips(qapp):
    from firepro3d.geometry_2d import SplineItem
    new = tg.offset_item(_make("spline"), 5.0)
    back = SplineItem.from_dict(new.to_dict())
    assert back.to_dict() == new.to_dict()


@pytest.mark.parametrize("d", [5.0, 20.0, -5.0, -20.0])
def test_closed_spline_offset_within_2pct(qapp, d):
    """Closed spline: the fitted offset stays within 2 % of |d| of the true
    offset everywhere away from the seam corner, and is exactly closed."""
    import numpy as np
    src = _closed_spline()
    new = tg.offset_item(src, d)
    assert new.is_closed() and new._degree == src._degree
    assert len(new._control_points) <= 4 * len(src._control_points)
    S = _exact_pts(src, 8000)
    N = _exact_pts(new, 2000)
    seam = N[0]
    away = np.hypot(*(N - seam).T) > 1.5 * abs(d)     # the corner is mitered
    assert away.sum() > len(N) // 3                    # most of the curve counts
    err = float(np.max(np.abs(_seg_dists(N[away], S) - abs(d))) / abs(d))
    assert err <= 0.02, f"max error {err:.2%} of d"                  # [RED]
    # outward = bigger, inward = smaller, whatever the winding
    grew = src.get_closed_path().contains(
        QPointF(float(seam[0]), float(seam[1])))
    assert grew == (d < 0)


@pytest.mark.parametrize("name, d", [("deg2", 5.0), ("deg2", 20.0),
                                     ("rational", 5.0), ("rational", -20.0),
                                     ("wiggly8", 5.0), ("wiggly8", -5.0)])
def test_other_open_splines_within_2pct(qapp, name, d):
    from firepro3d.geometry_2d import SplineItem
    Q = QPointF
    src = {
        "deg2": lambda: SplineItem([Q(0, 0), Q(50, -60), Q(100, 0), Q(150, -40)],
                                   degree=2),
        "rational": lambda: SplineItem([Q(0, 0), Q(50, -60), Q(100, 0), Q(150, -40)],
                                       weights=[1, 2, 0.5, 1]),
        # min radius of curvature ~10.9 mm: |d| = 5 stays swallowtail-free
        "wiggly8": lambda: SplineItem([Q(0, 0), Q(40, -50), Q(80, 20), Q(120, -60),
                                       Q(160, 10), Q(200, -40), Q(240, 30),
                                       Q(280, 0)]),
    }[name]()
    new = tg.offset_item(src, d)
    assert _open_spline_error(src, new, d) <= 0.02
    assert len(new._control_points) <= 4 * len(src._control_points)


# ── R-1: C0-corner splines (interior knot multiplicity == degree) ────────────

def _corner_spline():
    from firepro3d.geometry_2d import SplineItem
    return SplineItem([QPointF(0, 0), QPointF(30, -60), QPointF(60, 0),
                       QPointF(90, -60), QPointF(120, 0), QPointF(150, -60),
                       QPointF(180, 0)],
                      knots=[0, 0, 0, 0, .5, .5, .5, 1, 1, 1, 1])


def _dist_to_corner_points(spline, M):
    """Distance from *M* to the curve at the result's C0 knots (multiplicity
    >= degree), evaluated exactly with ezdxf — where a B-spline passes
    through a control point."""
    import numpy as np
    from collections import Counter
    from ezdxf.math import BSpline
    p = spline._degree
    k = spline._knots
    ks = [x for x, m in Counter(k[p + 1:-p - 1]).items() if m >= p]
    if not ks:
        return float("inf")
    b = BSpline([(q.x(), q.y()) for q in spline._control_points], order=p + 1,
                knots=k)
    return min(float(np.hypot(*(np.array(tuple(b.point(x))[:2]) - M)))
               for x in ks)


def _corner_miter(d):
    """Miter point of the source's corner (90,-60), from its end tangents."""
    import numpy as np
    c = np.array([90.0, -60.0])
    tin = np.array([30.0, -60.0]); tin /= np.linalg.norm(tin)
    tout = np.array([30.0, 60.0]); tout /= np.linalg.norm(tout)
    a = c + d * np.array([-tin[1], tin[0]])
    b = c + d * np.array([-tout[1], tout[0]])
    den = tin[0] * tout[1] - tin[1] * tout[0]
    s = ((b[0] - a[0]) * tout[1] - (b[1] - a[1]) * tout[0]) / den
    return a + s * tin, s


@pytest.mark.parametrize("d", [5.0, 20.0, -5.0, -20.0])
def test_corner_spline_offset_is_mitered_and_within_2pct(qapp, d):
    """A sharp (C0) corner is offset as two fitted runs joined by a miter
    (outer side) or trimmed at their crossing (inner side)."""
    import numpy as np
    src = _corner_spline()
    new = tg.offset_item(src, d)
    assert type(new).__name__ == "SplineItem" and not new.is_closed()
    assert len(new._control_points) <= 4 * len(src._control_points)
    S = _exact_pts(src, 12000)
    N = _exact_pts(new, 3000)[45:-45]
    M, s = _corner_miter(d)
    if s > 0:          # outer corner: the result runs through the miter point
        assert _dist_to_corner_points(new, M) <= 1e-6                    # [RED]
        leg = float(np.hypot(*(M - np.array([90.0, -60.0]))))
        N = N[np.hypot(*(N - M).T) > leg]            # the miter legs are > d
    err = float(np.max(np.abs(_seg_dists(N, S) - abs(d))) / abs(d))
    assert err <= 0.02, f"max error {err:.2%} of d"                      # [RED]


def test_fit_never_returns_an_out_of_tolerance_curve(qapp):
    """R-1 (a): whatever fit_offset_spline returns is within tolerance —
    never the best-at-cap curve (independently measured). The corner
    spline's inner side (d > 0 here) is exactly d from the source
    everywhere, so no exclusion is needed."""
    from firepro3d.geometry_2d import SplineItem
    for src, d in [(_corner_spline(), 5.0), (_corner_spline(), 20.0),
                   (_make("spline"), 5.0)]:
        fit = tg.fit_offset_spline(src, d)
        if fit is None:
            continue
        new = SplineItem(fit[0], src._degree, fit[1])
        err = _open_spline_error(src, new, d)
        assert err <= 0.02, f"{err:.2%}"                                 # [RED]
    assert tg.offset_item(_make("spline"), 200.0) is not None


# ── R2-2: a closed spline's legitimate inward offset is not refused ─────────

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


@pytest.mark.parametrize("d", [-100.0, -200.0])
def test_closed_noisy_spline_inward_offset_is_fitted(qapp, d):
    """The control-loop collapse check would refuse these (its 64 mm legs
    invert), but the true offset exists: the fit decides, not the loop."""
    import numpy as np
    src = _closed39()
    assert tg._offset_closed_loop(list(src._control_points)[:-1], d) is None
    new = tg.offset_item(src, d)
    assert new is not None and new.is_closed()                        # [RED]
    area = lambda P: 0.5 * float(np.sum(P[:-1, 0] * P[1:, 1] - P[1:, 0] * P[:-1, 1]))
    a0, a1 = area(_exact_pts(src, 8000)), area(_exact_pts(new, 8000))
    assert a0 * a1 > 0 and abs(a1) < abs(a0)          # same winding, shrunk


def test_closed_spline_inward_past_its_extent_is_refused(qapp):
    """The fit's own collapse test: inward past the loop's extent -> None."""
    assert tg.offset_item(_closed39(), -420.0) is None
    assert tg.offset_item(_closed_spline(), -60.0) is None


@pytest.mark.parametrize("chord_tol", [1.0, 0.25])
def test_result_path_chord_error_follows_chord_tol(qapp, chord_tol):
    """R2-1: the result path (the live ghost) is sampled to the caller's
    chord tolerance (the tool passes ~1 device px at the current zoom): the
    exact curve never strays more than that from the drawn polyline."""
    import numpy as np
    from tests.test_modify_tools_offset import _spline40
    src = _spline40()
    new = tg.offset_item(src, 5.0, cache={"chord_tol": chord_tol})
    poly = np.array([(q.x(), q.y()) for q in new.path().toSubpathPolygons()[0]])
    exact = _exact_pts(new, 20000)
    err = float(_seg_dists(exact[::7], poly).max())
    assert err <= chord_tol * 1.05, f"chord error {err:.3f} > {chord_tol}"
    if chord_tol == 1.0:
        fine = tg.offset_item(src, 5.0, cache={"chord_tol": 0.25})
        assert fine.path().elementCount() > new.path().elementCount()   # zoom-driven


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
