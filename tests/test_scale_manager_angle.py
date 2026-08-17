"""tests/test_scale_manager_angle.py — angle formatting and parsing."""

from __future__ import annotations

import pytest

from firepro3d.scale_manager import ScaleManager


class TestNormalize:

    @pytest.mark.parametrize("raw,expected", [
        (0.0, 0.0), (45.0, 45.0), (-45.0, -45.0),
        (180.0, 180.0), (-180.0, 180.0),
        (270.0, -90.0), (360.0, 0.0), (450.0, 90.0), (-270.0, 90.0),
    ])
    def test_folds_into_half_open_range(self, raw, expected):
        assert ScaleManager.normalize_angle(raw) == pytest.approx(expected)


class TestFormat:

    @pytest.mark.parametrize("deg,expected", [
        (0.0, "0°"), (45.0, "45°"), (-16.4, "-16.4°"),
        (16.40, "16.4°"), (90.0, "90°"), (270.0, "-90°"),
        (45.125, "45.13°"),          # 2-decimal cap, rounded
        (-0.001, "0°"),              # no "-0°"
    ])
    def test_formats(self, deg, expected):
        assert ScaleManager.format_angle(deg) == expected


class TestParse:

    @pytest.mark.parametrize("text,expected", [
        ("45", 45.0), ("45°", 45.0), ("45 deg", 45.0), ("45degrees", 45.0),
        ("-16.4", -16.4), ("  90  ", 90.0), (".5", 0.5), ("+30", 30.0),
        ("270", -90.0),              # normalized on parse
    ])
    def test_accepts(self, text, expected):
        assert ScaleManager.parse_angle(text) == pytest.approx(expected)

    @pytest.mark.parametrize("text", [
        "", "   ", "abc", "45x", "4 5", "45°°", None, "1/2",
    ])
    def test_rejects_returns_none(self, text):
        assert ScaleManager.parse_angle(text) is None

    def test_round_trip(self):
        for deg in (0.0, 45.0, -16.4, 90.0, 179.99):
            text = ScaleManager.format_angle(deg)
            assert ScaleManager.parse_angle(text) == pytest.approx(deg, abs=0.01)

    # Boundary and edge cases
    def test_wraps_past_180(self):
        # 180.5 normalizes to -179.5
        assert ScaleManager.parse_angle("180.5") == pytest.approx(-179.5)

    def test_negative_180_becomes_180(self):
        assert ScaleManager.parse_angle("-180") == pytest.approx(180.0)

    def test_accepts_trailing_dot(self):
        assert ScaleManager.parse_angle("45.") == pytest.approx(45.0)

    def test_accepts_leading_dot_with_sign(self):
        assert ScaleManager.parse_angle("+.5") == pytest.approx(0.5)

    def test_rejects_scientific_notation(self):
        # 1e3 is deliberately not accepted (regex requires no 'e')
        assert ScaleManager.parse_angle("1e3") is None

    def test_case_insensitive_deg_suffix(self):
        assert ScaleManager.parse_angle("45 DEG") == pytest.approx(45.0)

    # Non-finite input to parse_angle must return None
    def test_parse_nan_string_returns_none(self):
        assert ScaleManager.parse_angle("NaN°") is None

    def test_parse_inf_string_returns_none(self):
        assert ScaleManager.parse_angle("inf") is None


class TestFormatNonFinite:
    """format_angle must never raise or return a NaN/inf string."""

    def test_nan_formats_as_zero(self):
        assert ScaleManager.format_angle(float("nan")) == "0°"

    def test_inf_formats_as_zero(self):
        assert ScaleManager.format_angle(float("inf")) == "0°"

    def test_neg_inf_formats_as_zero(self):
        assert ScaleManager.format_angle(float("-inf")) == "0°"
