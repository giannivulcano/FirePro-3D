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
