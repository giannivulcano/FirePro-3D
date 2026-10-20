"""Section basis guards: cardinal h parity with the retired _world_to_elev table,
45-degree h / d on hand-computed points, painter order, classification."""
import math
import pytest

from firepro3d.section_marker import SectionBasis


# Pre-rename _world_to_elev (elevation_scene.py @ aeab43ff): h for each cardinal.
_OLD_H = {"north": lambda wx, wy: -wx, "south": lambda wx, wy: wx,
          "east": lambda wx, wy: wy, "west": lambda wx, wy: -wy}
# Pre-rename depth key (closer = larger key): north +wy, south -wy, east +wx, west -wx.
_OLD_KEY = {"north": lambda wx, wy: wy, "south": lambda wx, wy: -wy,
            "east": lambda wx, wy: wx, "west": lambda wx, wy: -wx}
# World-coordinate cardinal cuts around a 20 m x 10 m box (x -10000..10000, y -5000..5000).
_CUTS = {"north": ((10000.0, 5000.0), (-10000.0, 5000.0)),
         "south": ((-10000.0, -5000.0), (10000.0, -5000.0)),
         "east": ((10000.0, -5000.0), (10000.0, 5000.0)),
         "west": ((-10000.0, 5000.0), (-10000.0, -5000.0))}
_PTS = [(0.0, 0.0), (1234.5, -678.9), (-4000.0, 2500.0), (9999.0, 4999.0), (-9999.0, -4999.0)]


@pytest.mark.parametrize("card", list(_CUTS))
def test_cardinal_h_matches_pre_rename_table(card):
    a, b = _CUTS[card]
    basis = SectionBasis.from_cut(a, b, look_sign=1, depth_mm=10000.0)
    for wx, wy in _PTS:
        h, v = basis.project(wx, wy, 3000.0)
        assert h == pytest.approx(_OLD_H[card](wx, wy), abs=1e-9)
        assert v == -3000.0


@pytest.mark.parametrize("card", list(_CUTS))
def test_cardinal_sort_order_matches_pre_rename_depth(card):
    a, b = _CUTS[card]
    basis = SectionBasis.from_cut(a, b, look_sign=1, depth_mm=10000.0)
    new = sorted(_PTS, key=lambda p: basis.sort_key(*p))
    old = sorted(_PTS, key=lambda p: _OLD_KEY[card](*p))
    assert new == old


def test_45_degree_h_and_d_hand_computed():
    # Cut from (0, 0) to (1000, 1000): D = (1, 1)/sqrt2, N = (-1, 1)/sqrt2 (look_sign +1).
    basis = SectionBasis.from_cut((0.0, 0.0), (1000.0, 1000.0), look_sign=1, depth_mm=5000.0)
    r2 = math.sqrt(2.0)
    assert basis.h(1000.0, 0.0) == pytest.approx(1000.0 / r2)
    assert basis.d(1000.0, 0.0) == pytest.approx(-1000.0 / r2)       # in front
    assert basis.d(0.0, 1000.0) == pytest.approx(1000.0 / r2)        # look side
    assert (basis.h_min, basis.h_max) == pytest.approx((0.0, 2000.0 / r2))
    flipped = SectionBasis.from_cut((0.0, 0.0), (1000.0, 1000.0), look_sign=-1, depth_mm=5000.0)
    assert flipped.d(0.0, 1000.0) == pytest.approx(-1000.0 / r2)


def test_classify_polygon_cut_behind_hidden_and_chord():
    basis = SectionBasis.from_cut((0.0, 0.0), (10000.0, 0.0), look_sign=1, depth_mm=4000.0)  # looks toward +y
    square = lambda cx, cy, half: [(cx - half, cy - half), (cx + half, cy - half),
                                   (cx + half, cy + half), (cx - half, cy + half)]
    zone, lo, hi = basis.classify_polygon(square(5000.0, 0.0, 500.0))     # straddles the cut
    assert zone == "cut" and (lo, hi) == pytest.approx((4500.0, 5500.0))
    assert basis.classify_polygon(square(5000.0, 2000.0, 500.0))[0] == "behind"
    assert basis.classify_polygon(square(5000.0, -2000.0, 500.0))[0] == "hidden"   # in front
    assert basis.classify_polygon(square(5000.0, 6000.0, 500.0))[0] == "hidden"    # beyond depth
    assert basis.classify_polygon(square(15000.0, 2000.0, 500.0))[0] == "hidden"   # laterally outside
    # Collinear overlap counts as cut (spec s13): a 200 mm thick wall lying on the line.
    zone, lo, hi = basis.classify_polygon(square(5000.0, 0.0, 100.0))
    assert zone == "cut"
    # Behind item laterally straddling h_B is still behind (clipped later by the scene).
    assert basis.classify_polygon(square(10000.0, 2000.0, 500.0))[0] == "behind"


def test_classify_segment_crossing_param_and_collinear_midpoint():
    basis = SectionBasis.from_cut((0.0, 0.0), (10000.0, 0.0), look_sign=1, depth_mm=4000.0)
    zone, h, t = basis.classify_segment((3000.0, -1000.0), (3000.0, 3000.0))
    assert zone == "cut" and h == pytest.approx(3000.0) and t == pytest.approx(0.25)
    zone, h, t = basis.classify_segment((2000.0, 0.0), (6000.0, 0.0))        # along the cut
    assert zone == "cut" and h == pytest.approx(4000.0) and t == pytest.approx(0.5)
    assert basis.classify_segment((1000.0, 1000.0), (2000.0, 3000.0))[0] == "behind"
    assert basis.classify_segment((1000.0, -1000.0), (2000.0, -3000.0))[0] == "hidden"
    assert basis.classify_segment((20000.0, 1000.0), (30000.0, 1000.0))[0] == "hidden"


def test_classify_point_never_cut():
    basis = SectionBasis.from_cut((0.0, 0.0), (10000.0, 0.0), look_sign=1, depth_mm=4000.0)
    assert basis.classify_point((5000.0, 0.0)) == "behind"      # on the line: not cut
    assert basis.classify_point((5000.0, 1000.0)) == "behind"
    assert basis.classify_point((5000.0, -1.0)) == "hidden"
    assert basis.classify_point((5000.0, 4001.0)) == "hidden"


def test_degenerate_cut_rejected():
    with pytest.raises(ValueError):
        SectionBasis.from_cut((0.0, 0.0), (0.0, 0.0), look_sign=1, depth_mm=1.0)
