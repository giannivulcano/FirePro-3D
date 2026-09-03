"""T19 — pipe as a Dynamic Input HUD client (typed Length+Angle)."""
import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.dynamic_input import is_valid_relative_angle


class TestRelativeAngleValidation:
    @pytest.mark.parametrize("deg", [0, 45, 90, 135, 180, 225, 270, 315,
                                     -45, -90, -135, 360, 405])
    def test_multiples_of_45_are_valid(self, deg):
        assert is_valid_relative_angle(float(deg)) is True

    @pytest.mark.parametrize("deg", [1, 37, 44, 46, 89, 22.5, -30])
    def test_non_multiples_are_invalid(self, deg):
        assert is_valid_relative_angle(float(deg)) is False

    @pytest.mark.parametrize("deg", [44.999, 45.0009, 89.9995, -44.9990])
    def test_seed_float_dust_is_tolerated(self, deg):
        # A value seeded from the live preview carries sub-degree float dust
        # from get_vector_angle/subtraction; it must still validate.
        assert is_valid_relative_angle(float(deg)) is True
