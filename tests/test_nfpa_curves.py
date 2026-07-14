"""tests/test_nfpa_curves.py — NFPA 13 curve data + helpers."""
import pytest
from firepro3d.nfpa_curves import (
    DENSITY_AREA_CURVES, HAZARD_ABBREV, STORAGE_HAZARDS,
    interpolate_density, interpolate_area, min_design_point,
)


class TestMinDesignPoint:
    def test_light_hazard_minimum(self):
        assert min_design_point("Light Hazard") == (1500, 0.10)

    def test_extra_hazard_minimum(self):
        assert min_design_point("Extra Hazard Group 1") == (2500, 0.30)

    def test_storage_class_has_no_curve(self):
        assert min_design_point("Miscellaneous Storage") is None
        assert min_design_point("High Piled Storage") is None


class TestInterpolation:
    def test_density_at_curve_endpoints(self):
        assert interpolate_density("Ordinary Hazard Group 1", 1500) == pytest.approx(0.15)
        assert interpolate_density("Ordinary Hazard Group 1", 4000) == pytest.approx(0.10)

    def test_density_midpoint(self):
        assert interpolate_density("Ordinary Hazard Group 1", 2750) == pytest.approx(0.125)

    def test_area_inverse(self):
        assert interpolate_area("Ordinary Hazard Group 1", 0.125) == pytest.approx(2750)

    def test_density_fallback_for_storage_hazard(self):
        assert interpolate_density("High Piled Storage", 2000) == 0.10

    def test_area_fallback_for_storage_hazard(self):
        assert interpolate_area("High Piled Storage", 0.15) == 1500.0


class TestAbbrev:
    def test_all_curve_classes_abbreviated(self):
        for hz in DENSITY_AREA_CURVES:
            assert hz in HAZARD_ABBREV

    def test_storage_tuple(self):
        assert "Miscellaneous Storage" in STORAGE_HAZARDS
        assert "High Piled Storage" in STORAGE_HAZARDS
