import pytest
from PyQt6.QtCore import QPointF
from firepro3d.construction_geometry import SplineItem


def _cp(*xy):
    return [QPointF(x, y) for x, y in xy]


def test_construct_cubic_defaults():
    s = SplineItem(_cp((0, 0), (10, 20), (30, -10), (40, 5)))
    assert s._degree == 3
    assert len(s._control_points) == 4
    assert s._weights is None
    assert s._knots is not None


def test_degree_lowers_below_four_points():
    assert SplineItem(_cp((0, 0), (10, 10)))._degree == 1
    assert SplineItem(_cp((0, 0), (5, 10), (10, 0)))._degree == 2


def test_path_endpoints_are_first_and_last_control_points():
    s = SplineItem(_cp((0, 0), (10, 20), (30, -10), (40, 5)))
    path = s.path()
    assert path.pointAtPercent(0.0).x() == pytest.approx(0, abs=1e-3)
    assert path.pointAtPercent(0.0).y() == pytest.approx(0, abs=1e-3)
    assert path.pointAtPercent(1.0).x() == pytest.approx(40, abs=0.5)
    assert path.pointAtPercent(1.0).y() == pytest.approx(5, abs=0.5)


def test_grips_are_control_points():
    pts = _cp((0, 0), (10, 20), (30, -10), (40, 5))
    s = SplineItem(pts)
    g = s.grip_points()
    assert len(g) == 4
    assert g[2] == QPointF(30, -10)


def test_grip_drag_moves_control_point():
    s = SplineItem(_cp((0, 0), (10, 20), (30, -10), (40, 5)))
    s.apply_grip(1, QPointF(15, 25))
    assert s._control_points[1] == QPointF(15, 25)


def test_open_spline_not_fillable():
    s = SplineItem(_cp((0, 0), (10, 20), (30, -10), (40, 5)))
    assert s.is_fillable() is False
    assert s.get_closed_path() is None


def test_roundtrip_authored():
    s = SplineItem(_cp((0, 0), (10, 20), (30, -10), (40, 5)))
    s.level = "Level 3"
    d = s.to_dict()
    assert d["type"] == "draw_spline"
    s2 = SplineItem.from_dict(d)
    assert [(p.x(), p.y()) for p in s2._control_points] == \
           [(p.x(), p.y()) for p in s._control_points]
    assert s2._degree == s._degree
    assert s2.level == "Level 3"


def test_roundtrip_arbitrary_degree_rational():
    pts = _cp((0, 0), (10, 20), (30, -10), (40, 5), (60, 0))
    knots = [0, 0, 0, 0, 0.5, 1, 1, 1, 1]
    weights = [1.0, 2.0, 1.0, 0.5, 1.0]
    s = SplineItem(pts, degree=3, knots=knots, weights=weights)
    d = s.to_dict()
    s2 = SplineItem.from_dict(d)
    assert s2._degree == 3
    assert s2._knots == knots
    assert s2._weights == weights
