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
