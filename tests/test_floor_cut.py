"""floor_cut (pure) + the bridged-ring ear-clipper -- every expected number is hand-computed."""
import pytest
from PyQt6.QtCore import QPointF as P

from firepro3d.geometry_utils import triangulate_polygon


def _shoelace(xy):
    """Independent unsigned area of an (x, y) ring (never the module's helper)."""
    n = len(xy)
    return abs(sum(xy[i][0] * xy[(i + 1) % n][1] - xy[(i + 1) % n][0] * xy[i][1]
                   for i in range(n))) / 2.0


def _tri_area(pts, tris):
    return sum(_shoelace([pts[a], pts[b], pts[c]]) for a, b, c in tris)


def test_ear_clipper_triangulates_a_bridged_ring():
    # 4000 x 3000 slab (CCW) with a 1000 x 1000 hole (CW) bridged at (0,0)-(1000,1000).
    # Material = 12,000,000 - 1,000,000 = 11,000,000 mm^2; a simple n-gon gives n-2 = 8.
    ring = [(0.0, 0.0), (1000.0, 1000.0), (1000.0, 2000.0), (2000.0, 2000.0),
            (2000.0, 1000.0), (1000.0, 1000.0), (0.0, 0.0),
            (4000.0, 0.0), (4000.0, 3000.0), (0.0, 3000.0)]
    tris = triangulate_polygon(ring)
    assert len(tris) == 8
    assert _tri_area(ring, tris) == pytest.approx(11_000_000.0)


def test_ear_clipper_simple_polygon_unchanged():
    # Roof/floor regression: a plain rectangle still yields the same two ears.
    assert triangulate_polygon([(0.0, 0.0), (4000.0, 0.0), (4000.0, 3000.0),
                                (0.0, 3000.0)]) == [(3, 0, 1), (3, 1, 2)]


from firepro3d import floor_cut as fc


def _rect(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


SLAB = _rect(0, 0, 4000, 3000)                     # 12,000,000 mm^2


def _xy(ring):
    return [(p.x(), p.y()) for p in ring]


def _material_area(rings):
    return sum(_shoelace(_xy(o)) - sum(_shoelace(_xy(h)) for h in hs) for o, hs in rings)


def test_no_void_returns_slab_ring_untouched():
    rings = fc.cut_rings(SLAB, [])
    assert len(rings) == 1 and rings[0][1] == []
    assert rings[0][0] == SLAB                     # same vertices, same order


def test_void_outside_slab_is_a_noop():
    rings = fc.cut_rings(SLAB, [_rect(5000, 5000, 6000, 6000)])
    assert rings == [(SLAB, [])]


def test_noop_skips_the_snapping_clipper():
    # 4000.0000004 is off the 1e-6 snap grid: a clipper pass would weld it to
    # 4000.0, so an exact match proves no boolean ran (lesson: skip no-op booleans).
    noisy = [P(0, 0), P(4000.0000004, 0), P(4000.0000004, 3000), P(0, 3000)]
    assert fc.cut_rings(noisy, [])[0][0] == noisy
    assert fc.cut_rings(noisy, [_rect(5000, 5000, 6000, 6000)])[0][0] == noisy


@pytest.mark.parametrize("voids, pieces, holes, area", [
    # interior: 12e6 - 1000*1000
    ([_rect(1000, 1000, 2000, 2000)], 1, [1], 11_000_000.0),
    # two holes: 12e6 - 1e6 - 1000*1500
    ([_rect(500, 500, 1500, 1500), _rect(2500, 1000, 3500, 2500)], 1, [2], 9_500_000.0),
    # edge-crossing: only the 1000*1000 overlap is cut, leaving a notch (no hole)
    ([_rect(3000, 1000, 5000, 2000)], 1, [0], 11_000_000.0),
    # overlapping voids: union = 2*1e6 - 500*500 = 1,750,000
    ([_rect(1000, 1000, 2000, 2000), _rect(1500, 1500, 2500, 2500)], 1, [1], 10_250_000.0),
    # a full-depth strip splits the slab: 2 * 1500*3000
    ([_rect(1500, -100, 2500, 3100)], 2, [0, 0], 9_000_000.0),
], ids=["interior", "two-holes", "edge-crossing", "overlapping", "split"])
def test_cut_rings_areas(voids, pieces, holes, area):
    rings = fc.cut_rings(SLAB, voids)
    assert len(rings) == pieces
    assert sorted(len(h) for _, h in rings) == holes
    assert _material_area(rings) == pytest.approx(area, abs=1e-3)


def test_swallowed_slab_has_no_material():
    assert fc.cut_rings(SLAB, [_rect(-100, -100, 4100, 3100)]) == []


@pytest.mark.parametrize("voids, area", [
    ([_rect(1000, 1000, 2000, 2000)], 11_000_000.0),
    ([_rect(500, 500, 1500, 1500), _rect(2500, 1000, 3500, 2500)], 9_500_000.0),
    ([_rect(3000, 1000, 5000, 2000)], 11_000_000.0),
    ([_rect(1000, 1000, 2000, 2000), _rect(1500, 1500, 2500, 2500)], 10_250_000.0),
], ids=["interior", "two-holes", "edge-crossing", "overlapping"])
def test_triangulate_with_holes_covers_material(voids, area):
    total = 0.0
    for outer, holes in fc.cut_rings(SLAB, voids):
        pts, tris = fc.triangulate_with_holes(outer, holes)
        assert all(isinstance(p, tuple) and len(p) == 2 for p in pts)
        total += _tri_area(pts, tris)
    assert total == pytest.approx(area, abs=1e-3)


def test_triangulate_with_holes_accepts_either_winding():
    outer = [(0.0, 0.0), (0.0, 3000.0), (4000.0, 3000.0), (4000.0, 0.0)]   # CW
    hole = [(1000.0, 1000.0), (2000.0, 1000.0), (2000.0, 2000.0), (1000.0, 2000.0)]  # CCW
    pts, tris = fc.triangulate_with_holes(outer, [hole])
    assert _tri_area(pts, tris) == pytest.approx(11_000_000.0)


# Cut line y = 1500 from x = -1000 to x = 5000 (length 6000): t = (x + 1000) / 6000.
A, B = P(-1000, 1500), P(5000, 1500)


@pytest.mark.parametrize("voids, spans", [
    ([], [(1 / 6, 5 / 6)]),                                      # slab x 0..4000
    ([_rect(1000, 1000, 2000, 2000)], [(1 / 6, 2 / 6), (3 / 6, 5 / 6)]),   # break 1000..2000
    ([_rect(3000, 1000, 5000, 2000)], [(1 / 6, 4 / 6)]),         # material 0..3000
    ([_rect(1500, -100, 2500, 3100)], [(1 / 6, 2.5 / 6), (3.5 / 6, 5 / 6)]),
    ([_rect(-100, -100, 4100, 3100)], []),                       # swallowed
], ids=["none", "interior", "edge-crossing", "split", "swallowed"])
def test_intervals_inside(voids, spans):
    got = fc.intervals_inside(fc.cut_rings(SLAB, voids), A, B)
    assert len(got) == len(spans)
    for (g0, g1), (e0, e1) in zip(got, spans):
        assert g0 == pytest.approx(e0) and g1 == pytest.approx(e1)


def test_intervals_inside_segment_inside_material():
    # Both ends inside the slab, no void: the whole segment is one span.
    got = fc.intervals_inside(fc.cut_rings(SLAB, []), P(100, 100), P(200, 200))
    assert got == [(0.0, 1.0)]
