"""tests/test_scale_manager_dimension.py — the dimension input grammar.

``parse_dimension`` backs every ``DimensionEdit`` in the app (units spec:
"Length input | any format"), but had no direct coverage of its own — which is
how it came to reject ``.5`` while ``parse_angle`` accepted it.
"""

from __future__ import annotations

import pytest

from firepro3d.scale_manager import ScaleManager


class TestBareNumbers:

    @pytest.mark.parametrize("text,expected", [
        ("12", 12.0),
        ("12.5", 12.5),
        ("1000.75", 1000.75),
        ("0.5", 0.5),
        ("-12.5", -12.5),
        ("  42  ", 42.0),
    ])
    def test_accepts(self, text, expected):
        assert ScaleManager.parse_dimension(text, "mm") == pytest.approx(expected)


class TestPartialDecimals:
    """A leading or trailing dot is an ordinary way to type a decimal.

    ``parse_angle`` has always accepted both, and ``.`` is one of
    ``Model_Space.ENGAGE_CHARS`` — pressing it opens the dynamic-input HUD and
    seeds the field with ``"."``, so the very keystroke that starts a decimal
    produced text the dimension parser then refused.
    """

    @pytest.mark.parametrize("text,expected", [
        (".5", 0.5),
        (".25", 0.25),
        ("-.5", -0.5),
        ("12.", 12.0),
        ("-12.", -12.0),
    ])
    def test_accepts_partial_decimals(self, text, expected):
        assert ScaleManager.parse_dimension(text, "mm") == pytest.approx(expected)

    def test_leading_dot_with_unit_suffix(self):
        assert ScaleManager.parse_dimension(".5 m", "mm") == pytest.approx(500.0)

    def test_leading_dot_inches(self):
        assert ScaleManager.parse_dimension('.5"', "mm") == pytest.approx(12.7)

    def test_leading_dot_feet(self):
        assert ScaleManager.parse_dimension(".5'", "mm") == pytest.approx(152.4)

    def test_agrees_with_the_angle_parser(self):
        """The two grammars disagreed on exactly this; pin that they no longer do."""
        for text in (".5", "-.5", "12."):
            assert ScaleManager.parse_angle(text) is not None
            assert ScaleManager.parse_dimension(text, "mm") is not None


class TestExistingFormatsStillWork:
    """Regression guard: broadening the number pattern must not disturb these."""

    @pytest.mark.parametrize("text,expected_mm", [
        ("3048 mm", 3048.0),
        ("3.048 m", 3048.0),
        ("10 ft", 3048.0),
        ("126\"", 3200.4),
        ("10'", 3048.0),
        ("10' 6\"", 3200.4),
        ("10' 6 1/2\"", 3213.1),
        ("6 1/2\"", 165.1),
        ("-10'", -3048.0),
    ])
    def test_formats(self, text, expected_mm):
        assert ScaleManager.parse_dimension(text, "mm") == pytest.approx(
            expected_mm, abs=0.05)

    def test_fallback_unit_is_honoured(self):
        assert ScaleManager.parse_dimension("10", "ft") == pytest.approx(3048.0)


class TestRejects:

    @pytest.mark.parametrize("text", [
        "", "   ", "abc", "12abc",
        ".",            # a lone dot is not a number
        "-",            # nor a lone sign
        "-.",           # nor a signed lone dot
        "1,5",          # decimal comma is ambiguous with a thousands separator
        "1e3",          # scientific notation, rejected as for angles
    ])
    def test_returns_none(self, text):
        assert ScaleManager.parse_dimension(text, "mm") is None
