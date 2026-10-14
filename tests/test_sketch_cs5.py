"""CS5 pure core: model rows, radial / angular builders, ellipse + polygon
handles (parametric-constraint-system D67-D81, §11 #1 math guards)."""
import math

import numpy as np
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import sketch_model as sm
from firepro3d.sketch_adapters import adapter_for
from firepro3d.sketch_solver import (ANG_SCALE, CurveExpr, NumpySolver, System,
                                     build_dim_angle, build_dim_arc_angle,
                                     build_dim_diameter, build_dim_radius,
                                     const_point, raw_point)


def test_registry_cs5_types_built_and_valued():
    for t in ("dim_radius", "dim_diameter", "dim_angle", "dim_arc_angle"):
        assert sm.REGISTRY[t].implemented and t in sm.VALUED
    assert sm.REGISTRY["dim_arc_angle"].patterns == (("curve",),)
    assert sm.LENGTH_DIMS == {"dim_distance", "dim_radius", "dim_diameter", "dim_point_line"}
    assert sm.ANGLE_DIMS == {"dim_angle", "dim_arc_angle"}
    assert sm.VALUE_MAX == {"dim_angle": 180.0, "dim_arc_angle": 360.0}


def test_point_line_registry_and_row():
    from firepro3d.sketch_solver import build_dim_point_line
    assert sm.REGISTRY["dim_point_line"].implemented
    assert sm.REGISTRY["dim_point_line"].patterns == (("point", "edge"), ("point", "axis"))
    assert sm.LINEAR_DIMS == {"dim_distance", "dim_point_line"}
    # point (30, -40) vs the line (0,0)->(100,0): cross((30,-40), (100,0))/100 = 40
    x = np.array([30.0, -40.0, 0.0, 0.0, 100.0, 0.0])
    p, a, b = raw_point(0, 1), raw_point(2, 3), raw_point(4, 5)
    sys_ = System(x=x)
    build_dim_point_line("d", (p, (a, b)), sys_, value=40.0, helper={"side": 1})
    (row,) = sys_.rows
    assert row.fn(x)[0] == pytest.approx(0.0, abs=1e-9)
    x2 = x.copy(); x2[1] = -55.0
    assert row.fn(x2)[0] == pytest.approx(15.0)
    assert np.allclose(row.fn(x2)[1], _fd(row, x2), atol=1e-5)
    sys2 = System(x=np.array([30.0, -40.0]))
    # X axis = the line from the origin along +X: signed distance = -p.y = 40
    build_dim_point_line("d", (raw_point(0, 1), "x_axis"), sys2, value=40.0, helper={"side": 1})
    assert sys2.fixes == [(1, -40.0, "d")]


def test_radius_and_diameter_are_fixes():
    sys_ = System(x=np.array([0.0, 0.0, 7.0]))
    cv = CurveExpr(center=raw_point(0, 1), r=2)
    build_dim_radius("a", cv, sys_, value=12.5)
    build_dim_diameter("b", cv, sys_, value=30.0)
    assert sys_.fixes == [(2, 12.5, "a"), (2, 15.0, "b")] and not sys_.rows


def _fd(row, x, h=1e-6):
    g = np.zeros(len(row.deps))
    for k, d in enumerate(row.deps):
        xp, xm = x.copy(), x.copy()
        xp[d] += h; xm[d] -= h
        g[k] = (row.fn(xp)[0] - row.fn(xm)[0]) / (2 * h)
    return g


def test_arc_angle_row_residual_and_jacobian():
    sys_ = System(x=np.array([0.0, 0.0, 10.0, 0.2, 1.4]))
    cv = CurveExpr(center=raw_point(0, 1), r=2, span=(3, 4))
    build_dim_arc_angle("s", cv, sys_, value=math.degrees(1.2))
    (row,) = sys_.rows
    assert row.fn(sys_.x)[0] == pytest.approx(0.0, abs=1e-9)
    x = sys_.x.copy(); x[4] = 1.5
    assert row.fn(x)[0] == pytest.approx(ANG_SCALE * 0.1, rel=1e-9)
    assert np.allclose(row.fn(x)[1], _fd(row, x), atol=1e-4)


@pytest.mark.parametrize("seed", range(5))
def test_angle_row_zero_on_satisfying_geometry_and_fd_jacobian(seed):
    rng = np.random.default_rng(seed)
    x = rng.uniform(-50, 50, 8)
    a1, b1, a2, b2 = (raw_point(2 * k, 2 * k + 1) for k in range(4))
    u = x[2:4] - x[0:2]; v = x[6:8] - x[4:6]
    phi = math.atan2(u[0] * v[1] - u[1] * v[0], u @ v)
    sign = 1 if phi >= 0 else -1
    sys_ = System(x=x)
    build_dim_angle("g", ((a1, b1), (a2, b2)), sys_, value=math.degrees(abs(phi)),
                    helper={"dirs": [1, 1], "sign": sign})
    (row,) = sys_.rows
    assert row.fn(x)[0] == pytest.approx(0.0, abs=1e-6)
    assert np.allclose(row.fn(x)[1], _fd(row, x), atol=1e-3)


def test_angle_row_sector_dirs_and_axis():
    # edge along +x from origin, X axis: u = (1, 0), v = s2 * (1, 0)
    x = np.array([0.0, 0.0, 10.0, 10.0])          # a 45 deg (scene) edge
    a, b = raw_point(0, 1), raw_point(2, 3)
    sys_ = System(x=x)
    build_dim_angle("g", ((a, b), "x_axis"), sys_, value=45.0,
                    helper={"dirs": [1, 1], "sign": -1})
    assert sys_.rows[0].fn(x)[0] == pytest.approx(0.0, abs=1e-6)
    sys2 = System(x=x)
    build_dim_angle("g", ((a, b), "x_axis"), sys2, value=135.0,
                    helper={"dirs": [1, -1], "sign": 1})
    assert sys2.rows[0].fn(x)[0] == pytest.approx(0.0, abs=1e-6)


def test_angle_solve_moves_geometry_to_the_value():
    x = np.array([0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, -100.0])   # 90 deg (scene)
    a1, b1, a2, b2 = (raw_point(2 * k, 2 * k + 1) for k in range(4))
    sys_ = System(x=x)
    sys_.fixes += [(0, 0.0, "f"), (1, 0.0, "f"), (2, 100.0, "f"), (3, 0.0, "f"),
                   (4, 0.0, "f"), (5, 0.0, "f")]
    build_dim_angle("g", ((a1, b1), (a2, b2)), sys_, value=60.0,
                    helper={"dirs": [1, 1], "sign": -1})
    res = NumpySolver().solve(sys_, x.copy(), np.ones(8))
    assert res.converged
    v = res.x[6:8]
    assert math.degrees(math.atan2(-v[1], v[0])) == pytest.approx(60.0, abs=1e-6)


def test_angle_row_zero_length_edge_is_a_zero_row():
    x = np.array([5.0, 5.0, 5.0, 5.0, 0.0, 0.0, 10.0, 0.0])
    a1, b1, a2, b2 = (raw_point(2 * k, 2 * k + 1) for k in range(4))
    sys_ = System(x=x)
    build_dim_angle("g", ((a1, b1), (a2, b2)), sys_, value=30.0,
                    helper={"dirs": [1, 1], "sign": 1})
    r, g = sys_.rows[0].fn(x)
    assert r == 0.0 and not np.any(g)


def test_ellipse_axis_end_handles_match_its_grips(qapp):
    from firepro3d.geometry_2d import EllipseItem
    e = EllipseItem(QPointF(10, 20), 80, 45, 15)
    ad = adapter_for(e)
    x = np.array(ad.read(e), dtype=float)
    pts = ad.points(e, 0)
    grips = e.grip_points()
    for k, name in enumerate(("a0", "a1", "b0", "b1"), start=1):
        p = pts[name].eval(x)[0]
        assert (p[0], p[1]) == pytest.approx((grips[k].x(), grips[k].y()), abs=1e-9)
        assert ad.grip_handle(e, k) == name
    assert ad.hidden_names(e) >= {"rx", "ry"}
    assert set(ad.curves(e, 0)) == {"rx", "ry"} and ad.curves(e, 0)["rx"].r == 2


@pytest.mark.parametrize("name", ["a0", "a1", "b0", "b1"])
def test_ellipse_axis_end_jacobian(qapp, name):
    from firepro3d.geometry_2d import EllipseItem
    e = EllipseItem(QPointF(10, 20), 80, 45, 15)
    ad = adapter_for(e)
    x = np.array(ad.read(e), dtype=float)
    pe = ad.points(e, 0)[name]
    _p, dp = pe.eval(x)
    for k in range(5):
        xp, xm = x.copy(), x.copy(); xp[k] += 1e-6; xm[k] -= 1e-6
        fd = (pe.eval(xp)[0] - pe.eval(xm)[0]) / 2e-6
        assert np.allclose(dp[:, k], fd, atol=1e-5)


def test_polygon_hidden_radius_curve_and_arc_span(qapp):
    from firepro3d.geometry_2d import ArcItem, RegularPolygonItem
    pg = RegularPolygonItem(QPointF(0, 0), 6, 60.0)
    ad = adapter_for(pg)
    assert ad.curves(pg, 0)["radius"].r == 2 and "radius" in ad.hidden_names(pg)
    arc = ArcItem(QPointF(0, 0), 50, 20, 120)
    assert adapter_for(arc).curves(arc, 7)["curve"].span == (10, 11)
