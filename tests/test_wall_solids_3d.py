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


def test_band_bodies_mixed_height_l(qapp, model_scene):
    """G4 (band part): below the short wall's top the tall wall has the plan
    stop body; above it the tall wall's end is square (quad_points)."""
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0), top=3000.0)
    b = _wall(s, (3000, 0), (3000, 3000), top=2000.0)
    bands = a._solid_bands(a.pool_3d(), s._level_manager)
    assert [(z0, z1) for _p, z0, z1, _e in bands] == [(0.0, 2000.0), (2000.0, 3000.0)]
    low, high = bands[0][0], bands[1][0]
    assert [(round(p.x(), 6), round(p.y(), 6)) for p in low] == \
        [(round(p.x(), 6), round(p.y(), 6)) for p in a.outline_geometry().body]
    sq = a.quad_points()
    assert {(round(p.x(), 6), round(p.y(), 6)) for p in high} == \
        {(round(p.x(), 6), round(p.y(), 6)) for p in sq}


def test_uniform_wall_is_one_band(qapp, model_scene):
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    _wall(s, (3000, 0), (3000, 3000))
    assert len(a._solid_bands(a.pool_3d(), s._level_manager)) == 1


def test_plan_join_unchanged_without_pool(qapp, model_scene):
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    _wall(s, (3000, 0), (3000, 3000))
    assert a._join_ends()["quad"] == a._join_ends(pool=a._join_pool())["quad"]


def _mesh(w, s, pool=None):
    return w.get_3d_mesh(level_manager=s._level_manager, pool=pool)


def test_g1_l_joint_exact_closed_plan_body(qapp, model_scene):
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    b = _wall(s, (3000, 0), (3000, 3000))
    for w in (a, b):
        m = _mesh(w, s)
        assert _closed(m)
        assert _vol(m) == pytest.approx(_area(w.outline_geometry().body) * 3000,
                                        rel=1e-9)
        top = {(round(x, 3), round(y, 3)) for x, y, z in m["vertices"]
               if abs(z - 3000.0) < 1e-6}
        plan = {(round(p.x(), 3), round(-p.y(), 3))
                for p in w.outline_geometry().body}
        assert top == plan


def test_g2_pies_sum_to_union(qapp, model_scene):
    L = 2000.0
    s = model_scene()
    arms = [_wall(s, (0, 0), (L, 0)), _wall(s, (0, 0), (0, L)),
            _wall(s, (0, 0), (-L, 0)), _wall(s, (0, 0), (0, -L))]
    total = sum(_vol(_mesh(w, s)) for w in arms)
    assert total == pytest.approx((2 * (2 * L * T) - T * T) * 3000, rel=1e-9)
    s2 = model_scene()
    arms3 = [_wall(s2, (0, 0), (L, 0)), _wall(s2, (0, 0), (-L, 0)),
             _wall(s2, (0, 0), (0, L))]
    total3 = sum(_vol(_mesh(w, s2)) for w in arms3)
    assert total3 == pytest.approx((2 * L * T + (L - T / 2) * T) * 3000,
                                   rel=1e-9)


def test_g3_tee_stub_ends_on_host_face(qapp, model_scene):
    s = model_scene()
    _wall(s, (0, 0), (3000, 0))
    stub = _wall(s, (1500, 0), (1500, 2000))
    ys = [abs(y) for _x, y, _z in _mesh(stub, s)["vertices"]]
    assert min(ys) == pytest.approx(T / 2, abs=1e-6)


def test_g4_mixed_height_volumes(qapp, model_scene):
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0), top=3000.0)
    _wall(s, (3000, 0), (3000, 3000), top=2000.0)
    bands = a._solid_bands(a.pool_3d(), s._level_manager)
    exp = sum(_area(body) * (z1 - z0) for body, z0, z1, _e in bands)
    m = _mesh(a, s)
    assert _closed(m) and _vol(m) == pytest.approx(exp, rel=1e-9)
    assert _area(bands[1][0]) == pytest.approx(3000 * T, rel=1e-9)  # square end


def test_g5_cut_over_wedge_host_only(qapp, model_scene):
    from firepro3d.wall_opening import WallOpening
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    b = _wall(s, (3000, 0), (3000, 3000))
    vb = _vol(_mesh(b, s))
    op = WallOpening(wall=a, feature_id="door_914", offset_along=2950.0)
    s.addItem(op); a.openings.append(op)
    cuts = a._opening_cuts(s._level_manager)
    assert len(cuts) == 1
    m = _mesh(a, s)
    import manifold3d as m3
    from firepro3d.wall_solid import _prism       # winding-normalised prism
    body = [(p.x(), -p.y()) for p in a.outline_geometry().body]
    rect_q, cz0, cz1 = cuts[0]
    rect = [(p.x(), -p.y()) for p in rect_q]
    inter = m3.Manifold.batch_boolean(
        [_prism(body, 0.0, 3000.0), _prism(rect, cz0, cz1)],
        m3.OpType.Intersect).volume()
    assert inter > 0.0                            # the cut does reach the host
    assert _closed(m)
    assert _vol(m) == pytest.approx(_area(body) * 3000 - inter, rel=1e-9)
    assert _vol(_mesh(b, s)) == pytest.approx(vb, rel=1e-12)


def test_g7_hidden_in_3d_neighbour_squares(qapp, model_scene):
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    b = _wall(s, (3000, 0), (3000, 3000))
    joined = _vol(_mesh(a, s))
    b._display_overrides = {"visible": False}
    assert _vol(_mesh(a, s)) == pytest.approx(3000 * T * 3000, rel=1e-9)
    b._display_overrides = {}
    assert _vol(_mesh(a, s)) == pytest.approx(joined, rel=1e-12)


def test_g8_mesh_dict_contract(qapp, model_scene):
    s = model_scene()
    m = _mesh(_wall(s, (0, 0), (3000, 0)), s)
    assert set(m) == {"vertices", "faces", "color", "edges"}
    assert all(len(v) == 3 for v in m["vertices"])
    assert all(len(f) == 3 and all(isinstance(i, int) for i in f)
               for f in m["faces"])
    assert len(m["color"]) == 4
    assert all(len(seg) == 2 and len(seg[0]) == 3 for seg in m["edges"])


def test_build_solid_failed_cut_falls_back_uncut(caplog):
    """D8: a cut that empties the result retries without cuts, with a warning."""
    import logging
    from firepro3d.wall_solid import build_solid
    sq = [(0, 0), (1000, 0), (1000, 200), (0, 200)]
    huge = [(-5000, -5000), (5000, -5000), (5000, 5000), (-5000, 5000)]
    with caplog.at_level(logging.WARNING, logger="firepro3d.wall_solid"):
        m = build_solid([(sq, 0.0, 1000.0)], [(huge, -10.0, 2000.0)])
    assert m is not None and _vol(m) == pytest.approx(1000 * 200 * 1000, rel=1e-9)
    assert "opening cut failed" in caplog.text
