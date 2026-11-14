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


def _segs2d(edges, z):
    return [((round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3)))
            for a, b in edges if abs(a[2] - z) < 1e-6 and abs(b[2] - z) < 1e-6]


def _on_segment(pt, a, b, tol=1e-3):
    (px, py), (ax, ay), (bx, by) = pt, a, b
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if abs(cross) / max(math.hypot(bx - ax, by - ay), 1e-9) > tol:
        return False
    return min(ax, bx) - tol <= px <= max(ax, bx) + tol and \
        min(ay, by) - tol <= py <= max(ay, by) + tol


def test_g6_no_mitre_seam_in_top_outline(qapp, model_scene):
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    _wall(s, (3000, 0), (3000, 3000))
    top = _segs2d(_mesh(a, s)["edges"], 3000.0)
    # mitre diagonal runs inner corner (2900, -100) -> outer corner (3100, 100)
    # in 3D coords (Y negated); no top segment may lie along it
    mid = (3000.0, 0.0)
    assert not any(_on_segment(mid, p, q) for p, q in top)
    assert top                       # the outer faces do draw


def test_g6_stop_seam_draws(qapp, model_scene):
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0), top=3000.0)
    b = _wall(s, (3000, 0), (3000, 3000), top=2000.0)
    seams = b.outline_geometry().seams
    assert seams, "precondition: unequal L gives the lower wall a seam"
    top = _segs2d(_mesh(b, s)["edges"], 2000.0)
    (p, q) = seams[0]
    mid = ((p.x() + q.x()) / 2, -(p.y() + q.y()) / 2)
    assert any(_on_segment(mid, sp, sq) for sp, sq in top)


def test_g6_reveal_edges(qapp, model_scene):
    from firepro3d.wall_opening import WallOpening
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    op = WallOpening(wall=a, feature_id="door_914", offset_along=1500.0)
    s.addItem(op); a.openings.append(op)
    edges = _mesh(a, s)["edges"]
    head = 0.0 + op._sill_mm + op._height_mm
    hw = op._width_mm / 2
    verticals = [(a3, b3) for a3, b3 in edges
                 if abs(a3[0] - b3[0]) < 1e-6 and abs(a3[1] - b3[1]) < 1e-6]
    jamb_x = {round(a3[0], 3) for a3, _b in verticals}
    assert {round(1500 - hw, 3), round(1500 + hw, 3)} <= jamb_x
    assert _segs2d(edges, head)      # head reveal edges
    base = _segs2d(edges, 0.0)       # bottom outline broken across the door
    assert not any(_on_segment((1500.0, -T / 2), p, q) for p, q in base)


def test_clip_depth_pulls_corners_to_faces():
    from firepro3d.wall_solid import clip_depth
    rect = [(1, -1), (2, -1), (2, 201), (1, 201)]
    poly = [(0, 0), (10, 0), (10, 200), (0, 200)]
    assert clip_depth(rect, poly) == [(1.0, 0.0), (2.0, 0.0), (2.0, 200.0), (1.0, 200.0)]


@pytest.mark.parametrize("align", ["Centered", "Flush-front", "Flush-back"])
def test_cut_on_axis_for_any_alignment(qapp, model_scene, align):
    """D5/Q4: the cut is full thickness on the wall axis; the opening's
    alignment/cross offset shifts its plan symbol but not the cut."""
    from firepro3d.wall_opening import WallOpening
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    op = WallOpening(wall=a, feature_id="door_914", offset_along=1500.0)
    op.alignment = align
    s.addItem(op); a.openings.append(op)
    op._reposition()
    m = _mesh(a, s)
    exp = 3000 * T * 3000 - op._width_mm * T * (
        op._sill_mm + op._height_mm - op._sill_mm)
    assert _closed(m)
    assert _vol(m) == pytest.approx(exp, rel=1e-9)


def test_get_3d_mesh_excludes_self_from_pool(qapp, model_scene):
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0))
    _wall(s, (3000, 0), (3000, 3000))
    want = _vol(_mesh(a, s))
    assert _vol(_mesh(a, s, pool=list(s._walls))) == pytest.approx(want, rel=1e-12)
    bands = a._solid_bands(list(s._walls), s._level_manager)
    assert _area(bands[0][0]) == pytest.approx(_area(a.outline_geometry().body),
                                               rel=1e-9)


def test_band_keeps_member_set_across_mid_span_stub(qapp, model_scene):
    """A tee stub shorter than its host splits the host's bands even though
    the host body is identical, so the top outline above the stub is drawn."""
    s = model_scene()
    a = _wall(s, (0, 0), (3000, 0), top=3000.0)
    _wall(s, (1500, 0), (1500, 2000), top=2000.0)
    bands = a._solid_bands(a.pool_3d(), s._level_manager)
    assert [(z0, z1) for _b, z0, z1, _e in bands] == [(0.0, 2000.0), (2000.0, 3000.0)]
    m = _mesh(a, s)
    assert _closed(m)
    assert _vol(m) == pytest.approx(3000 * T * 3000, rel=1e-9)
    top = _segs2d(m["edges"], 3000.0)
    for x in (1400.0, 1450.0, 1500.0, 1550.0, 1600.0):
        for y in (-T / 2, T / 2):
            assert any(_on_segment((x, y), p, q) for p, q in top), (x, y)
    # z = 2000 (D7.2): band-below pieces XOR band-above pieces -- only the
    # host face the stub stands on (y = -100, the stub's width) differs.
    mid = _segs2d(m["edges"], 2000.0)
    assert mid
    assert all(abs(p[1] + T / 2) < 1e-3 and abs(q[1] + T / 2) < 1e-3
               and 1400.0 - 1e-3 <= min(p[0], q[0])
               and max(p[0], q[0]) <= 1600.0 + 1e-3 for p, q in mid), mid


def test_no_duplicate_edges_mixed_height_l(qapp, model_scene):
    s = model_scene()
    _wall(s, (0, 0), (3000, 0), top=3000.0)
    b = _wall(s, (3000, 0), (3000, 3000), top=2000.0)
    edges = _mesh(b, s)["edges"]
    keys = [tuple(sorted((tuple(round(c, 3) for c in p),
                          tuple(round(c, 3) for c in q)))) for p, q in edges]
    assert len(keys) == len(set(keys))


def test_calibrated_scene_cut_exact_mm(qapp, model_scene):
    from firepro3d.wall_opening import WallOpening
    s = model_scene()
    s.scale_manager.calibrate(QPointF(0, 0), QPointF(200, 0), 100.0)  # 2 px/mm
    ppm = s.scale_manager.pixels_per_mm
    assert ppm == pytest.approx(2.0)
    a = _wall(s, (0, 0), (3000 * ppm, 0))
    op = WallOpening(wall=a, feature_id="door_914", offset_along=1500.0 * ppm)
    s.addItem(op); a.openings.append(op)
    op._reposition()
    m = _mesh(a, s)
    hw = op._width_mm / 2
    exp = 3000 * T * 3000 - op._width_mm * T * op._height_mm
    assert _closed(m) and _vol(m) == pytest.approx(exp, rel=1e-9)
    jx = {round(a3[0], 3) for a3, b3 in m["edges"]
          if abs(a3[0] - b3[0]) < 1e-6 and abs(a3[1] - b3[1]) < 1e-6}
    assert {round(1500 - hw, 3), round(1500 + hw, 3)} <= jx
