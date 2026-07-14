"""tests/test_auto_populate.py -- Auto-populate sprinkler placement algorithm tests.

Tests cover:
- NFPA 13 density/area curve interpolation (forward and inverse)
- Hazard classification lookups and data consistency
- Polygon area (shoelace formula)
- Point-to-boundary distance
- Point-to-segment distance
- Rectangle merging
- Grid dimension factoring (prime avoidance, aspect ratio)
- Polygon decomposition into rectangles
- Full sprinkler grid computation
"""

import math
import pytest

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPolygonF

from firepro3d.auto_populate_dialog import (
    _interpolate_density,
    _interpolate_area,
    _polygon_area_mm2,
    _min_dist_to_boundary,
    _merge_rectangles,
    _find_grid_dimensions,
    _decompose_into_rectangles,
    compute_sprinkler_grid,
    DENSITY_AREA_CURVES,
    NFPA_MAX_COVERAGE,
    NFPA_MAX_SPACING,
    NFPA_MIN_SPACING_FT,
    NFPA_MIN_WALL_DIST_IN,
    HAZARD_SPRINKLER_TYPES,
    HAZARD_CLASSES,
    FT_TO_MM,
    IN_TO_MM,
    SQFT_TO_MM2,
)
from firepro3d.design_area import _point_to_segment_dist
from firepro3d.constants import HAZARD_CLASSES as CONST_HAZARD_CLASSES


# ── Helpers ──────────────────────────────────────────────────────────────────

def _rect_boundary(w_mm: float, h_mm: float,
                   x0: float = 0.0, y0: float = 0.0) -> list[QPointF]:
    """Return a CCW rectangular boundary in mm."""
    return [
        QPointF(x0, y0),
        QPointF(x0 + w_mm, y0),
        QPointF(x0 + w_mm, y0 + h_mm),
        QPointF(x0, y0 + h_mm),
    ]


def _l_shape_boundary() -> list[QPointF]:
    """Return an L-shaped polygon (6 vertices, all axis-aligned).

    Shape (in mm):
        (0,0)──(6096,0)
          |          |
        (0,3048)──(3048,3048)
                    |
              (3048,6096)──(0,6096)
                             |
    Corrected for a proper closed L:
        Top-left block:  6096 x 3048  (20 ft x 10 ft)
        Bottom-left block: 3048 x 3048  (10 ft x 10 ft)
    """
    return [
        QPointF(0, 0),
        QPointF(6096, 0),
        QPointF(6096, 3048),
        QPointF(3048, 3048),
        QPointF(3048, 6096),
        QPointF(0, 6096),
    ]


# ═════════════════════════════════════════════════════════════════════════════
# 1. NFPA 13 Density / Area Curve Interpolation
# ═════════════════════════════════════════════════════════════════════════════

class TestInterpolateDensity:
    """_interpolate_density: area (sq ft) -> density (gpm/ft^2)."""

    def test_light_hazard_at_endpoint_low(self):
        """At the low-area endpoint, return the endpoint density."""
        d = _interpolate_density("Light Hazard", 1500)
        assert d == pytest.approx(0.10)

    def test_light_hazard_at_endpoint_high(self):
        """At the high-area endpoint, return the endpoint density."""
        d = _interpolate_density("Light Hazard", 3000)
        assert d == pytest.approx(0.07)

    def test_light_hazard_midpoint(self):
        """Midpoint of LH curve: area 2250 -> density 0.085."""
        d = _interpolate_density("Light Hazard", 2250)
        assert d == pytest.approx(0.085)

    def test_oh1_midpoint(self):
        """OH1 curve midpoint: area 2750 -> density 0.125."""
        d = _interpolate_density("Ordinary Hazard Group 1", 2750)
        assert d == pytest.approx(0.125)

    def test_oh2_at_endpoints(self):
        d_lo = _interpolate_density("Ordinary Hazard Group 2", 1500)
        d_hi = _interpolate_density("Ordinary Hazard Group 2", 4000)
        assert d_lo == pytest.approx(0.20)
        assert d_hi == pytest.approx(0.15)

    def test_eh1_midpoint(self):
        """EH1: area 3750 -> density 0.25."""
        d = _interpolate_density("Extra Hazard Group 1", 3750)
        assert d == pytest.approx(0.25)

    def test_eh2_at_endpoints(self):
        d_lo = _interpolate_density("Extra Hazard Group 2", 2500)
        d_hi = _interpolate_density("Extra Hazard Group 2", 5000)
        assert d_lo == pytest.approx(0.40)
        assert d_hi == pytest.approx(0.30)

    def test_clamp_below_min_area(self):
        """Area below the curve's first point clamps to that density."""
        d = _interpolate_density("Light Hazard", 500)
        assert d == pytest.approx(0.10)

    def test_clamp_above_max_area(self):
        """Area above the curve's last point clamps to that density."""
        d = _interpolate_density("Light Hazard", 5000)
        assert d == pytest.approx(0.07)

    def test_unknown_hazard_returns_default(self):
        """Unknown hazard class falls back to 0.10."""
        d = _interpolate_density("Nonexistent Hazard", 2000)
        assert d == pytest.approx(0.10)

    def test_density_decreases_with_area(self):
        """For all curves, density at min area >= density at max area."""
        for hazard, pts in DENSITY_AREA_CURVES.items():
            d_lo = _interpolate_density(hazard, pts[0][0])
            d_hi = _interpolate_density(hazard, pts[-1][0])
            assert d_lo >= d_hi, f"{hazard}: density should decrease with area"


class TestInterpolateArea:
    """_interpolate_area: density (gpm/ft^2) -> area (sq ft)."""

    def test_light_hazard_at_high_density(self):
        """LH: density 0.10 -> area 1500."""
        a = _interpolate_area("Light Hazard", 0.10)
        assert a == pytest.approx(1500.0)

    def test_light_hazard_at_low_density(self):
        """LH: density 0.07 -> area 3000."""
        a = _interpolate_area("Light Hazard", 0.07)
        assert a == pytest.approx(3000.0)

    def test_light_hazard_midpoint(self):
        """LH: density 0.085 -> area 2250."""
        a = _interpolate_area("Light Hazard", 0.085)
        assert a == pytest.approx(2250.0)

    def test_oh1_at_endpoints(self):
        a_hi = _interpolate_area("Ordinary Hazard Group 1", 0.15)
        a_lo = _interpolate_area("Ordinary Hazard Group 1", 0.10)
        assert a_hi == pytest.approx(1500.0)
        assert a_lo == pytest.approx(4000.0)

    def test_clamp_below_min_density(self):
        """Density below the curve's minimum clamps to that area."""
        a = _interpolate_area("Light Hazard", 0.01)
        # Sorted by density ascending: (3000, 0.07) is the low end
        assert a == pytest.approx(3000.0)

    def test_clamp_above_max_density(self):
        """Density above the curve's maximum clamps to that area."""
        a = _interpolate_area("Light Hazard", 0.50)
        # Sorted by density ascending: (1500, 0.10) is the high end
        assert a == pytest.approx(1500.0)

    def test_unknown_hazard_returns_default(self):
        a = _interpolate_area("Nonexistent Hazard", 0.10)
        assert a == pytest.approx(1500.0)

    def test_roundtrip_density_area(self):
        """Interpolating density then area should return the original area."""
        for hazard, pts in DENSITY_AREA_CURVES.items():
            a0 = pts[0][0]
            d = _interpolate_density(hazard, a0)
            a_back = _interpolate_area(hazard, d)
            assert a_back == pytest.approx(a0, rel=1e-4), (
                f"{hazard}: roundtrip failed ({a0} -> {d} -> {a_back})")


# ═════════════════════════════════════════════════════════════════════════════
# 2. Hazard Classification Lookups and Data Consistency
# ═════════════════════════════════════════════════════════════════════════════

class TestHazardData:
    """Verify NFPA data tables are complete and consistent."""

    def test_hazard_classes_match_constants(self):
        """HAZARD_CLASSES in auto_populate matches constants.py."""
        assert HAZARD_CLASSES == CONST_HAZARD_CLASSES

    def test_max_coverage_keys_match(self):
        """Every hazard class has a max coverage entry."""
        for hc in HAZARD_CLASSES:
            assert hc in NFPA_MAX_COVERAGE, f"Missing NFPA_MAX_COVERAGE for {hc}"

    def test_max_spacing_keys_match(self):
        """Every hazard class has max spacing entries for both obstruction types."""
        for hc in HAZARD_CLASSES:
            assert hc in NFPA_MAX_SPACING, f"Missing NFPA_MAX_SPACING for {hc}"
            assert "Unobstructed" in NFPA_MAX_SPACING[hc]
            assert "Obstructed" in NFPA_MAX_SPACING[hc]

    def test_sprinkler_types_keys_match(self):
        """Every hazard class has a sprinkler types entry."""
        for hc in HAZARD_CLASSES:
            assert hc in HAZARD_SPRINKLER_TYPES, (
                f"Missing HAZARD_SPRINKLER_TYPES for {hc}")

    def test_extra_hazard_restricts_sidewall(self):
        """Extra hazard classes should not include Sidewall or Concealed."""
        for hc in ["Extra Hazard Group 1", "Extra Hazard Group 2"]:
            types = HAZARD_SPRINKLER_TYPES[hc]
            assert "Sidewall" not in types
            assert "Concealed" not in types

    def test_light_hazard_highest_coverage(self):
        """Light Hazard should have the highest max coverage."""
        lh_cov = NFPA_MAX_COVERAGE["Light Hazard"]
        for hc, cov in NFPA_MAX_COVERAGE.items():
            assert lh_cov >= cov, (
                f"Light Hazard coverage ({lh_cov}) < {hc} coverage ({cov})")

    def test_max_coverage_positive(self):
        for hc, cov in NFPA_MAX_COVERAGE.items():
            assert cov > 0, f"{hc} coverage should be positive"

    def test_max_spacing_positive(self):
        for hc, obs_dict in NFPA_MAX_SPACING.items():
            for obs, sp in obs_dict.items():
                assert sp > 0, f"{hc}/{obs} spacing should be positive"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Polygon Area (Shoelace Formula)
# ═════════════════════════════════════════════════════════════════════════════

class TestPolygonArea:
    """_polygon_area_mm2: shoelace formula for polygon area."""

    def test_unit_square(self):
        boundary = _rect_boundary(1.0, 1.0)
        assert _polygon_area_mm2(boundary) == pytest.approx(1.0)

    def test_10ft_square(self):
        """10 ft x 10 ft = 100 sq ft -> 9,290,304 mm^2."""
        side_mm = 10 * FT_TO_MM  # 3048 mm
        boundary = _rect_boundary(side_mm, side_mm)
        expected = side_mm * side_mm
        assert _polygon_area_mm2(boundary) == pytest.approx(expected)

    def test_rectangle(self):
        """20 ft x 10 ft rectangle."""
        w_mm = 20 * FT_TO_MM
        h_mm = 10 * FT_TO_MM
        boundary = _rect_boundary(w_mm, h_mm)
        assert _polygon_area_mm2(boundary) == pytest.approx(w_mm * h_mm)

    def test_triangle(self):
        """Right triangle: base 10, height 10 -> area 50."""
        boundary = [QPointF(0, 0), QPointF(10, 0), QPointF(0, 10)]
        assert _polygon_area_mm2(boundary) == pytest.approx(50.0)

    def test_degenerate_line(self):
        """Fewer than 3 points returns 0."""
        assert _polygon_area_mm2([QPointF(0, 0), QPointF(1, 0)]) == 0.0

    def test_empty(self):
        assert _polygon_area_mm2([]) == 0.0

    def test_winding_order_invariant(self):
        """Area should be the same regardless of CW/CCW winding."""
        ccw = _rect_boundary(100, 200)
        cw = list(reversed(ccw))
        assert _polygon_area_mm2(ccw) == pytest.approx(_polygon_area_mm2(cw))


# ═════════════════════════════════════════════════════════════════════════════
# 4. Point-to-Boundary Distance
# ═════════════════════════════════════════════════════════════════════════════

class TestMinDistToBoundary:
    """_min_dist_to_boundary: minimum distance from point to polygon edges."""

    def test_center_of_square(self):
        """Center of a 100x100 square is 50 from nearest edge."""
        boundary = _rect_boundary(100, 100)
        pt = QPointF(50, 50)
        assert _min_dist_to_boundary(pt, boundary) == pytest.approx(50.0)

    def test_near_edge(self):
        """Point near the left edge of a 100x100 square."""
        boundary = _rect_boundary(100, 100)
        pt = QPointF(10, 50)
        assert _min_dist_to_boundary(pt, boundary) == pytest.approx(10.0)

    def test_on_vertex(self):
        """Point exactly on a vertex: distance should be 0."""
        boundary = _rect_boundary(100, 100)
        pt = QPointF(0, 0)
        assert _min_dist_to_boundary(pt, boundary) == pytest.approx(0.0, abs=1e-6)

    def test_on_edge(self):
        """Point on the bottom edge midpoint: distance 0."""
        boundary = _rect_boundary(100, 100)
        pt = QPointF(50, 0)
        assert _min_dist_to_boundary(pt, boundary) == pytest.approx(0.0, abs=1e-6)

    def test_outside_boundary(self):
        """Point outside the boundary still computes distance to nearest edge."""
        boundary = _rect_boundary(100, 100)
        pt = QPointF(-10, 50)
        assert _min_dist_to_boundary(pt, boundary) == pytest.approx(10.0)


# ═════════════════════════════════════════════════════════════════════════════
# 5. Point-to-Segment Distance (from design_area.py)
# ═════════════════════════════════════════════════════════════════════════════

class TestPointToSegmentDist:
    """_point_to_segment_dist: Euclidean distance from point to line segment."""

    def test_perpendicular_projection(self):
        """Point directly above a horizontal segment."""
        d = _point_to_segment_dist(5, 10, 0, 0, 10, 0)
        assert d == pytest.approx(10.0)

    def test_at_endpoint(self):
        """Point is at the start of the segment."""
        d = _point_to_segment_dist(0, 0, 0, 0, 10, 0)
        assert d == pytest.approx(0.0, abs=1e-9)

    def test_beyond_segment_start(self):
        """Point projects before segment start -> distance to start."""
        d = _point_to_segment_dist(-5, 0, 0, 0, 10, 0)
        assert d == pytest.approx(5.0)

    def test_beyond_segment_end(self):
        """Point projects past segment end -> distance to end."""
        d = _point_to_segment_dist(15, 0, 0, 0, 10, 0)
        assert d == pytest.approx(5.0)

    def test_degenerate_zero_length_segment(self):
        """Zero-length segment degenerates to point distance."""
        d = _point_to_segment_dist(3, 4, 0, 0, 0, 0)
        assert d == pytest.approx(5.0)

    def test_diagonal_segment(self):
        """Point to a 45-degree segment."""
        # Segment from (0,0) to (10,10), point at (10,0)
        # Distance from (10,0) to line y=x is 10/sqrt(2)
        d = _point_to_segment_dist(10, 0, 0, 0, 10, 10)
        assert d == pytest.approx(10.0 / math.sqrt(2), rel=1e-6)


# ═════════════════════════════════════════════════════════════════════════════
# 6. Rectangle Merging
# ═════════════════════════════════════════════════════════════════════════════

class TestMergeRectangles:
    """_merge_rectangles: merge adjacent axis-aligned rectangles."""

    def test_empty(self):
        assert _merge_rectangles([]) == []

    def test_single_rect(self):
        result = _merge_rectangles([(0, 0, 10, 10)])
        assert len(result) == 1
        assert result[0] == pytest.approx((0, 0, 10, 10))

    def test_two_horizontal_adjacent(self):
        """Two rects side by side sharing the same y-span merge into one."""
        rects = [(0, 0, 10, 20), (10, 0, 10, 20)]
        result = _merge_rectangles(rects)
        assert len(result) == 1
        x, y, w, h = result[0]
        assert x == pytest.approx(0)
        assert y == pytest.approx(0)
        assert w == pytest.approx(20)
        assert h == pytest.approx(20)

    def test_two_vertical_adjacent(self):
        """Two rects stacked sharing the same x-span merge into one."""
        rects = [(0, 0, 20, 10), (0, 10, 20, 10)]
        result = _merge_rectangles(rects)
        assert len(result) == 1
        x, y, w, h = result[0]
        assert x == pytest.approx(0)
        assert y == pytest.approx(0)
        assert w == pytest.approx(20)
        assert h == pytest.approx(20)

    def test_non_adjacent_no_merge(self):
        """Two rects with a gap do not merge."""
        rects = [(0, 0, 10, 10), (20, 0, 10, 10)]
        result = _merge_rectangles(rects)
        assert len(result) == 2

    def test_three_horizontal_merge_chain(self):
        """Three contiguous horizontal rects merge to one."""
        rects = [(0, 0, 5, 10), (5, 0, 5, 10), (10, 0, 5, 10)]
        result = _merge_rectangles(rects)
        assert len(result) == 1
        assert result[0] == pytest.approx((0, 0, 15, 10))


# ═════════════════════════════════════════════════════════════════════════════
# 7. Grid Dimension Factoring
# ═════════════════════════════════════════════════════════════════════════════

class TestFindGridDimensions:
    """_find_grid_dimensions: factorize sprinkler count for grid layout."""

    def test_perfect_square(self):
        """4 sprinklers in a square room -> 2x2."""
        n_long, n_short = _find_grid_dimensions(4, 10, 10)
        assert n_long * n_short == 4

    def test_six_in_2to1_room(self):
        """6 sprinklers in a 2:1 room -> 3x2."""
        n_long, n_short = _find_grid_dimensions(6, 20, 10)
        assert n_long * n_short == 6
        assert n_long == 3
        assert n_short == 2

    def test_prime_number_adjusted(self):
        """7 is prime -> adjusted to 8 (4x2) or similar composite."""
        n_long, n_short = _find_grid_dimensions(7, 20, 10)
        product = n_long * n_short
        # Should bump to a composite >= 7
        assert product >= 7
        assert n_long >= n_short
        # Should be a valid factorization
        assert product == n_long * n_short

    def test_one_sprinkler(self):
        """Edge case: 1 sprinkler."""
        n_long, n_short = _find_grid_dimensions(1, 10, 10)
        assert n_long * n_short == 1

    def test_two_sprinklers_long_room(self):
        """2 sprinklers in an elongated room -> 2x1."""
        n_long, n_short = _find_grid_dimensions(2, 30, 10)
        assert n_long == 2
        assert n_short == 1

    def test_long_side_gets_larger_count(self):
        """The larger count should be assigned to the longer side."""
        n_long, n_short = _find_grid_dimensions(12, 40, 10)
        assert n_long >= n_short

    def test_large_count(self):
        """Larger counts should still produce valid factorizations."""
        n_long, n_short = _find_grid_dimensions(24, 30, 20)
        assert n_long * n_short >= 24
        assert n_long >= n_short


# ═════════════════════════════════════════════════════════════════════════════
# 8. Polygon Decomposition into Rectangles
# ═════════════════════════════════════════════════════════════════════════════

class TestDecomposeIntoRectangles:
    """_decompose_into_rectangles: scanline polygon decomposition."""

    def test_simple_rectangle(self, qapp):
        """A simple rectangle decomposes into 1 rectangle."""
        boundary = _rect_boundary(3048, 3048)
        path = QPainterPath()
        path.addPolygon(QPolygonF(boundary))
        path.closeSubpath()
        rects = _decompose_into_rectangles(boundary, path, 0)
        assert len(rects) == 1
        x, y, w, h = rects[0]
        assert w == pytest.approx(3048)
        assert h == pytest.approx(3048)

    def test_l_shape_produces_multiple_rects(self, qapp):
        """An L-shape should decompose into 2 or more rectangles."""
        boundary = _l_shape_boundary()
        path = QPainterPath()
        path.addPolygon(QPolygonF(boundary))
        path.closeSubpath()
        rects = _decompose_into_rectangles(boundary, path, 0)
        # L-shape with 6 vertices produces a grid of cells; after merging,
        # we expect at least 2 distinct rectangles
        assert len(rects) >= 2

    def test_total_area_matches(self, qapp):
        """Sum of decomposed rectangle areas should equal polygon area."""
        boundary = _l_shape_boundary()
        path = QPainterPath()
        path.addPolygon(QPolygonF(boundary))
        path.closeSubpath()
        rects = _decompose_into_rectangles(boundary, path, 0)
        total_rect_area = sum(w * h for _, _, w, h in rects)
        poly_area = _polygon_area_mm2(boundary)
        assert total_rect_area == pytest.approx(poly_area, rel=0.01)


# ═════════════════════════════════════════════════════════════════════════════
# 9. Full Sprinkler Grid Computation
# ═════════════════════════════════════════════════════════════════════════════

class TestComputeSprinklerGrid:
    """compute_sprinkler_grid: end-to-end grid placement algorithm."""

    def test_empty_boundary(self, qapp):
        """Fewer than 3 points -> no positions."""
        positions, sx, sy, log = compute_sprinkler_grid(
            [QPointF(0, 0)], 130, 15)
        assert positions == []
        assert sx == 0.0
        assert sy == 0.0

    def test_10x10_room_light_hazard(self, qapp):
        """10 ft x 10 ft = 100 sq ft room with LH (225 sq ft max coverage).

        One sprinkler needed (100/225 < 1 -> ceil to 1).
        """
        side_mm = 10 * FT_TO_MM
        boundary = _rect_boundary(side_mm, side_mm)
        positions, sx, sy, log = compute_sprinkler_grid(
            boundary, max_coverage_sqft=225, max_spacing_ft=15)
        assert len(positions) >= 1

    def test_20x20_room_ordinary_hazard(self, qapp):
        """20 ft x 20 ft = 400 sq ft room with OH (130 sq ft max).

        400/130 = 3.08 -> ceil to 4 sprinklers minimum.
        """
        side_mm = 20 * FT_TO_MM
        boundary = _rect_boundary(side_mm, side_mm)
        positions, sx, sy, log = compute_sprinkler_grid(
            boundary, max_coverage_sqft=130, max_spacing_ft=15)
        assert len(positions) >= 4

    def test_30x20_room_count(self, qapp):
        """30 ft x 20 ft = 600 sq ft with OH (130 sq ft max).

        600/130 = 4.6 -> ceil to 5.  After factorization, grid >= 5.
        """
        w_mm = 30 * FT_TO_MM
        h_mm = 20 * FT_TO_MM
        boundary = _rect_boundary(w_mm, h_mm)
        positions, sx, sy, log = compute_sprinkler_grid(
            boundary, max_coverage_sqft=130, max_spacing_ft=15)
        assert len(positions) >= 5

    def test_all_positions_inside_boundary(self, qapp):
        """All computed positions must be inside the room polygon."""
        side_mm = 15 * FT_TO_MM
        boundary = _rect_boundary(side_mm, side_mm)
        path = QPainterPath()
        path.addPolygon(QPolygonF(boundary))
        path.closeSubpath()
        positions, _, _, _ = compute_sprinkler_grid(
            boundary, max_coverage_sqft=130, max_spacing_ft=15)
        for pt in positions:
            assert path.contains(pt), (
                f"Position ({pt.x():.1f}, {pt.y():.1f}) is outside boundary")

    def test_spacing_within_nfpa_limits(self, qapp):
        """Returned spacing should not exceed the max_spacing_ft."""
        side_mm = 25 * FT_TO_MM
        boundary = _rect_boundary(side_mm, side_mm)
        max_sp = 15.0
        positions, sx, sy, log = compute_sprinkler_grid(
            boundary, max_coverage_sqft=130, max_spacing_ft=max_sp)
        if sx > 0:
            assert sx <= max_sp + 0.01, f"Spacing X {sx} exceeds max {max_sp}"
        if sy > 0:
            assert sy <= max_sp + 0.01, f"Spacing Y {sy} exceeds max {max_sp}"

    def test_min_spacing_respected(self, qapp):
        """No two sprinklers should be closer than min_spacing."""
        side_mm = 20 * FT_TO_MM
        boundary = _rect_boundary(side_mm, side_mm)
        min_sp = NFPA_MIN_SPACING_FT
        min_sp_mm = min_sp * FT_TO_MM
        positions, _, _, _ = compute_sprinkler_grid(
            boundary, max_coverage_sqft=130, max_spacing_ft=15,
            min_spacing_ft=min_sp)
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                dist = math.hypot(
                    positions[i].x() - positions[j].x(),
                    positions[i].y() - positions[j].y(),
                )
                assert dist >= min_sp_mm - 1.0, (
                    f"Sprinklers {i} and {j} are {dist:.1f} mm apart "
                    f"(min: {min_sp_mm:.1f} mm)")

    def test_returns_calc_log(self, qapp):
        """compute_sprinkler_grid returns a non-empty calculation log."""
        side_mm = 15 * FT_TO_MM
        boundary = _rect_boundary(side_mm, side_mm)
        _, _, _, log = compute_sprinkler_grid(
            boundary, max_coverage_sqft=130, max_spacing_ft=15)
        assert len(log) > 0
        assert "TOTAL" in log

    def test_l_shape_room(self, qapp):
        """L-shaped room should still produce valid sprinkler positions."""
        boundary = _l_shape_boundary()
        positions, sx, sy, log = compute_sprinkler_grid(
            boundary, max_coverage_sqft=130, max_spacing_ft=15)
        assert len(positions) >= 1
        # All positions inside the polygon
        path = QPainterPath()
        path.addPolygon(QPolygonF(boundary))
        path.closeSubpath()
        for pt in positions:
            assert path.contains(pt), (
                f"Position ({pt.x():.1f}, {pt.y():.1f}) outside L-shape")

    def test_very_small_room_single_sprinkler(self, qapp):
        """A tiny room should get at least 1 sprinkler."""
        side_mm = 6 * FT_TO_MM  # 6 ft x 6 ft = 36 sq ft
        boundary = _rect_boundary(side_mm, side_mm)
        positions, _, _, _ = compute_sprinkler_grid(
            boundary, max_coverage_sqft=225, max_spacing_ft=15)
        assert len(positions) == 1


# ═════════════════════════════════════════════════════════════════════════════
# 10. Conversion Constants
# ═════════════════════════════════════════════════════════════════════════════

class TestConversionConstants:
    """Verify conversion constants are correct."""

    def test_ft_to_mm(self):
        assert FT_TO_MM == pytest.approx(304.8)

    def test_in_to_mm(self):
        assert IN_TO_MM == pytest.approx(25.4)

    def test_sqft_to_mm2(self):
        assert SQFT_TO_MM2 == pytest.approx(304.8 ** 2)

    def test_nfpa_min_spacing(self):
        assert NFPA_MIN_SPACING_FT == 6.0

    def test_nfpa_min_wall_dist(self):
        assert NFPA_MIN_WALL_DIST_IN == 4.0


# ═════════════════════════════════════════════════════════════════════════════
# 11. AutoPopulateDialog — design-point seeding
# ═════════════════════════════════════════════════════════════════════════════

class TestAutoPopulateDialogDesignPointSeeding:
    """AutoPopulateDialog seeds its graph from the room's design_point()."""

    def _make_room(self, hazard: str = "Ordinary Hazard Group 1"):
        from PyQt6.QtCore import QPointF
        from firepro3d.room import Room
        room = Room(boundary=[
            QPointF(0, 0), QPointF(10000, 0),
            QPointF(10000, 10000), QPointF(0, 10000),
        ])
        room.set_property("Hazard Class", hazard)
        return room

    def _make_dialog(self, room, qapp):
        from firepro3d.sprinkler_db import SprinklerDatabase
        from firepro3d.auto_populate_dialog import AutoPopulateDialog
        db = SprinklerDatabase()
        return AutoPopulateDialog(room=room, sprinkler_db=db)

    def test_dialog_seeds_from_room_design_point(self, qapp):
        """Stored design point on the room seeds _selected_area/_selected_density."""
        room = self._make_room()
        room._design_point = (3000.0, 0.125)
        dlg = self._make_dialog(room, qapp)
        assert dlg._selected_area == pytest.approx(3000.0)
        assert dlg._selected_density == pytest.approx(0.125)

    def test_dialog_seeds_curve_minimum_without_stored_point(self, qapp):
        """No stored point: dialog seeds from the hazard curve minimum via design_point()."""
        # OHG1 curve minimum is (1500 sq ft, 0.15 gpm/ft²)
        room = self._make_room("Ordinary Hazard Group 1")
        assert room._design_point is None  # no stored point
        dlg = self._make_dialog(room, qapp)
        # design_point() returns (1500, 0.15) for OHG1
        assert dlg._selected_area == pytest.approx(1500.0)
        assert dlg._selected_density == pytest.approx(0.15)
