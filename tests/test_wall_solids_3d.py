import math
import numpy as np
import pytest
import pyvista as pv
from PyQt6.QtCore import QPointF

T = 200.0          # wall thickness mm (uncalibrated scene: 1 unit = 1 mm)


def _wall(scene, p1, p2, top=3000.0, base=0.0):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=T)
    w._top_level = w._base_level            # z range = (base, top) exactly
    w._base_offset_mm = base
    w._top_offset_mm = top
    scene.addItem(w)
    scene._walls.append(w)
    return w


def _pd(mesh):
    return pv.PolyData.from_regular_faces(
        np.array(mesh["vertices"], dtype=float),
        np.array(mesh["faces"], dtype=np.int64))


def _closed(mesh):
    pd = _pd(mesh)
    return pd.n_open_edges == 0 and pd.is_manifold


def _vol(mesh):
    return abs(_pd(mesh).volume)


def _area(poly):
    pts = [(p.x(), p.y()) for p in poly] if hasattr(poly[0], "x") else poly
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                   in zip(pts, pts[1:] + pts[:1]))) / 2.0


def test_build_solid_band_and_cut_exact():
    from firepro3d.wall_solid import build_solid
    body = [(0, 0), (5000, 0), (5000, 200), (200, 200)]      # mitred L end
    square = [(0, 0), (5000, 0), (5000, 200), (0, 200)]
    cuts = [([(1000, -1), (1900, -1), (1900, 201), (1000, 201)], 0.0, 2100.0),
            ([(3000, -1), (4200, -1), (4200, 201), (3000, 201)], 900.0, 2100.0)]
    m = build_solid([(body, 0.0, 2400.0), (square, 2400.0, 3000.0)], cuts)
    exp = (_area(body) * 2400 + _area(square) * 600
           - 900 * 200 * 2100 - 1200 * 200 * 1200)
    assert _closed(m)
    assert _vol(m) == pytest.approx(exp, rel=1e-9)


def test_build_solid_cw_ring_and_degenerate_band():
    from firepro3d.wall_solid import build_solid
    cw = [(0, 0), (0, 200), (1000, 200), (1000, 0)]
    m = build_solid([(cw, 0.0, 1000.0), ([(0, 0), (1, 0)], 1000.0, 2000.0)], [])
    assert _vol(m) == pytest.approx(1000 * 200 * 1000, rel=1e-9)
    assert build_solid([], []) is None


def test_subtract_collinear():
    from firepro3d.wall_solid import subtract_collinear
    a = [((0.0, 0.0), (10.0, 0.0))]
    b = [((3.0, 0.0), (5.0, 0.0)), ((0.0, 1.0), (10.0, 1.0))]
    got = sorted(subtract_collinear(a, b, 1e-6))
    assert got == [((0.0, 0.0), (3.0, 0.0)), ((5.0, 0.0), (10.0, 0.0))]
