"""LT3 H3-c -- LinetypeDef reading (LT3-3) and dash expansion."""
import pytest
from PyQt6.QtGui import QPainterPath
from firepro3d import linetype_render as lr, path_walk as pw
from tests.lt3_support import make_linetype


def _subpaths(path: QPainterPath):
    out = []
    for i in range(path.elementCount()):
        e = path.elementAt(i)
        if e.isMoveTo():
            out.append([(e.x, e.y)])
        else:
            out[-1].append((e.x, e.y))
    return out


def test_unit_reading_dashes_dots_period():
    d = make_linetype(dashes=((0, 6), (7, 1)), dots=(8.5,), length=9)
    lt = lr.LinetypeDef.from_block(d)
    assert lt.period == 9.0 and lt.size == "drafting"
    assert lt.dashes == ((0.0, 6.0), (7.0, 1.0))
    assert lt.dots == (8.5,)


def test_off_axis_and_out_of_frame_content_ignored():
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    d = make_linetype()
    d.primitives.append(LineItem(QPointF(0, 2), QPointF(5, 2)).to_dict())   # off axis
    d.primitives.append(LineItem(QPointF(20, 0), QPointF(25, 0)).to_dict())  # past length
    d.invalidate_cache()
    assert lr.LinetypeDef.from_block(d).dashes == ((0.0, 6.0),)


def test_malformed_is_none():
    assert lr.LinetypeDef.from_block(make_linetype(length=0)) is None
    assert lr.LinetypeDef.from_block(make_linetype(dashes=(), dots=())) is None


def test_dash_weight_is_heaviest_named():
    d = make_linetype(dashes=((0, 3), (4, 3)), length=9)
    d.primitives[0]["style"]["weight"] = "Light"
    d.primitives[1]["style"]["weight"] = "Heavy"
    d.invalidate_cache()
    assert lr.LinetypeDef.from_block(d).dash_weight == "Heavy"


def test_expand_seg_dash_lengths_and_phase():
    lt = lr.LinetypeDef.from_block(make_linetype())         # 6 on / 3 off
    dash, dot = lr.expand((pw.Seg(0, 0, 20, 0),), lt, 1.0, (0.0, 0.0))
    xs = [(round(s[0][0], 6), round(s[-1][0], 6)) for s in _subpaths(dash)]
    assert xs == [(0.0, 6.0), (9.0, 15.0), (18.0, 20.0)]
    assert dot.isEmpty()


def test_expand_is_direction_independent_and_seamless():
    lt = lr.LinetypeDef.from_block(make_linetype())
    one, _ = lr.expand((pw.Seg(0, 0, 20, 0),), lt, 1.0, (0.0, 0.0))
    two, _ = lr.expand((pw.Seg(10, 0, 0, 0), pw.Seg(10, 0, 20, 0)), lt, 1.0, (0.0, 0.0))
    def cover(path):
        segs = sorted((min(s[0][0], s[-1][0]), max(s[0][0], s[-1][0]))
                      for s in _subpaths(path))
        merged = []
        for a, b in segs:
            if merged and a <= merged[-1][1] + 1e-9:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return [(round(a, 6), round(b, 6)) for a, b in merged]
    assert cover(one) == cover(two)


def test_length_factor_scales_pattern():
    lt = lr.LinetypeDef.from_block(make_linetype())
    dash, _ = lr.expand((pw.Seg(0, 0, 1000, 0),), lt, 100.0, (0.0, 0.0))
    first = _subpaths(dash)[0]
    assert (first[0][0], first[-1][0]) == pytest.approx((0.0, 600.0))


def test_dots_are_tiny_round_segments():
    lt = lr.LinetypeDef.from_block(make_linetype(dashes=((0, 6),), dots=(7.5,)))
    _, dot = lr.expand((pw.Seg(0, 0, 9, 0),), lt, 1.0, (0.0, 0.0))
    s = _subpaths(dot)
    assert len(s) == 1 and s[0][0][0] == pytest.approx(7.5)


def test_expand_cache_returns_same_objects():
    lt = lr.LinetypeDef.from_block(make_linetype())
    a = lr.expand((pw.Seg(0, 0, 20, 0),), lt, 1.0, (0.0, 0.0))
    b = lr.expand((pw.Seg(0, 0, 20, 0),), lt, 1.0, (0.0, 0.0))
    assert a is b


# ── F1 (ruled 2026-10-05): arc / ellipse rhythm restarts at 0° ──────────────

def _ink_angles(path, to_angle, lo):
    """Merged inked angle intervals of *path*'s subpaths, unwrapped >= *lo*."""
    segs = []
    for sp in _subpaths(path):
        a, b = to_angle(sp[0]), to_angle(sp[-1])
        a = a + 360.0 if a < lo - 0.5 else a
        b = b + 360.0 if b < lo - 0.5 else b
        if b < a - 1e-6:
            b += 360.0
        segs.append((a, b))
    segs.sort()
    merged = []
    for a, b in segs:
        if merged and a <= merged[-1][1] + 1e-4:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return [(round(a, 3), round(b, 3)) for a, b in merged]


def _circle_angle(xy):
    import math
    return math.degrees(math.atan2(-xy[1], xy[0])) % 360.0


def _ellipse_angle(cx, cy, rx, ry, rot):
    import math
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QTransform
    t = QTransform()
    t.rotate(-rot)
    inv, _ = t.inverted()

    def f(xy):
        q = inv.map(QPointF(xy[0] - cx, xy[1] - cy))
        return math.degrees(math.atan2(-q.y() / ry, q.x() / rx)) % 360.0
    return f


def _clip(iv, lo, hi):
    return [(max(a, lo), min(b, hi)) for a, b in iv if min(b, hi) - max(a, lo) > 1e-3]


def _same(iv1, iv2, tol=0.05):
    """Same inked intervals within *tol* degrees (Qt bezier arc ends drift µm)."""
    return len(iv1) == len(iv2) and all(
        abs(a1 - a2) <= tol and abs(b1 - b2) <= tol
        for (a1, b1), (a2, b2) in zip(iv1, iv2))


def _dash(pieces):
    lt = lr.LinetypeDef.from_block(make_linetype())        # 6 on / 3 off, period 9
    return lr.expand(tuple(pieces), lt, 1.0, (0.0, 0.0))[0]


def test_arc_crossing_zero_equals_arcs_broken_at_zero():
    one = _ink_angles(_dash([pw.Arc(0, 0, 10, 330.0, 60.0)]), _circle_angle, 330.0)
    two = _ink_angles(_dash([pw.Arc(0, 0, 10, 330.0, 30.0), pw.Arc(0, 0, 10, 0.0, 30.0)]),
                      _circle_angle, 330.0)
    assert _same(one, two), (one, two)


def test_arc_trim_keeps_surviving_dashes():
    full = _ink_angles(_dash([pw.Arc(0, 0, 10, 330.0, 90.0)]), _circle_angle, 330.0)
    end_trim = _ink_angles(_dash([pw.Arc(0, 0, 10, 330.0, 45.0)]), _circle_angle, 330.0)
    start_trim = _ink_angles(_dash([pw.Arc(0, 0, 10, 40.0, 20.0)]), _circle_angle, 330.0)
    assert _same(_clip(full, 330.0, 375.0), _clip(end_trim, 330.0, 375.0))
    assert _same(_clip(full, 400.0, 420.0), _clip(start_trim, 400.0, 420.0)),         (full, start_trim)


def test_ellipse_crossing_zero_equals_arcs_broken_at_zero():
    ang = _ellipse_angle(3, 4, 20, 10, 15.0)
    one = _ink_angles(_dash([pw.EllipseArc(3, 4, 20, 10, 15.0, 300.0, 120.0)]), ang, 300.0)
    two = _ink_angles(_dash([pw.EllipseArc(3, 4, 20, 10, 15.0, 300.0, 60.0),
                             pw.EllipseArc(3, 4, 20, 10, 15.0, 0.0, 60.0)]), ang, 300.0)
    assert _same(one, two), (one, two)


def test_ellipse_trim_keeps_surviving_dashes():
    ang = _ellipse_angle(3, 4, 20, 10, 15.0)
    full = _ink_angles(_dash([pw.EllipseArc(3, 4, 20, 10, 15.0, 300.0, 120.0)]), ang, 300.0)
    end_trim = _ink_angles(_dash([pw.EllipseArc(3, 4, 20, 10, 15.0, 300.0, 50.0)]), ang, 300.0)
    start_trim = _ink_angles(_dash([pw.EllipseArc(3, 4, 20, 10, 15.0, 20.0, 40.0)]), ang, 300.0)
    assert _same(_clip(full, 300.0, 350.0), _clip(end_trim, 300.0, 350.0))
    assert _same(_clip(full, 380.0, 420.0), _clip(start_trim, 380.0, 420.0)),         (full, start_trim)


# ── F2 (LT3-3): dot test uses the unclamped Line length ─────────────────────

def test_out_of_frame_lines_touching_boundary_are_not_dots():
    d = make_linetype(dashes=((0, 6), (-5, 5), (9, 6)), length=9)   # -5..0, 9..15
    lt = lr.LinetypeDef.from_block(d)
    assert lt.dashes == ((0.0, 6.0),)
    assert lt.dots == ()


def test_unit_with_only_out_of_frame_lines_is_malformed():
    assert lr.LinetypeDef.from_block(
        make_linetype(dashes=((-5, 5), (9, 6)), length=9)) is None


def test_partially_outside_line_is_clamped_dash():
    lt = lr.LinetypeDef.from_block(make_linetype(dashes=((-2, 6), (8, 4)), length=9))
    assert lt.dashes == ((0.0, 4.0), (8.0, 1.0))
    assert lt.dots == ()


def test_true_dot_kept_in_frame_and_dropped_outside():
    lt = lr.LinetypeDef.from_block(make_linetype(dashes=((0, 6),), dots=(9.0, 12.0)))
    assert lt.dots == (9.0,)


# ── F3: reading cache keys on origin and is bounded ─────────────────────────

def test_origin_change_without_version_bump_rereads():
    d = make_linetype()                                   # dash 0..6
    assert lr.LinetypeDef.from_block(d).dashes == ((0.0, 6.0),)
    v = d.version
    d.origin = (3.0, 0.0)                                 # real setter, no bump
    assert d.version == v
    assert lr.LinetypeDef.from_block(d).dashes == ((0.0, 3.0),)


def test_reading_cache_is_bounded():
    from firepro3d.constants import LINETYPE_DEF_CACHE_MAX
    for _ in range(LINETYPE_DEF_CACHE_MAX + 10):
        lr.LinetypeDef.from_block(make_linetype())
    assert len(lr.LinetypeDef._CACHE) <= LINETYPE_DEF_CACHE_MAX
