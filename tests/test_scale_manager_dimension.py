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
        "5 min",        # unit word must end at a letter boundary
    ])
    def test_returns_none(self, text):
        assert ScaleManager.parse_dimension(text, "mm") is None


class TestImperialForms:
    """Backlog 823 + the 2026-10-30 robustness probe (units spec §3.1)."""

    @pytest.mark.parametrize("text,expected_mm", [
        ('5\' 5.5"', 1663.7),
        ('5\'-5.5"', 1663.7),
        ('5\'6-1/2"', 1689.1),
        ('5\'-6 1/2"', 1689.1),
        ('6-1/2"', 165.1),
        ('3/8"', 9.525),
        ('1/2"', 12.7),
        ('5 3/8"', 136.525),
        ('5 3/8 in', 136.525),
        ('5ft 6in', 1676.4),
        ('5 ft 6 in', 1676.4),
        ("5'-6\"", 1676.4),
        ("14'-9\"", 4495.8),
        ("10'-3\"", 3124.2),
        ("5' 6", 1676.4),
    ])
    def test_accepts(self, text, expected_mm):
        assert ScaleManager.parse_dimension(text, "ft") == pytest.approx(
            expected_mm, abs=1e-6)

    @pytest.mark.parametrize("text,unit,expected_mm", [
        ("5 3/8", "ft", 1638.3),
        ("3/8", "ft", 114.3),
        ("5 3/8", "mm", 5.375),
    ])
    def test_bare_fraction_is_the_default_unit(self, text, unit, expected_mm):
        assert ScaleManager.parse_dimension(text, unit) == pytest.approx(
            expected_mm, abs=1e-6)


class TestArithmetic:
    """Backlog 1066 — ratified rules 2-4 (units spec §3.2)."""

    @pytest.mark.parametrize("text,expected_mm", [
        ("10' - 3\"", 2971.8),
        ("5'6\" - 3\"", 1600.2),
        ("12\"-3\"", 228.6),
        ("12\" * 2", 609.6),
        ("10' / 3", 1016.0),
        ("2 * 6'", 3657.6),
        ("10' + 2", 3657.6),
        ("(10' - 6\") / 2", 1447.8),
        ("3' + 2 * 6\"", 1219.2),
        ("(2 + 3) * 6'", 9144.0),
        ("3ft - 1.5ft", 457.2),
        ("-(5')", -1524.0),
        ("5' -6\"", 1371.6),
        ("10' \u2212 3\"", 2971.8),
        ("12\" \u00d7 2", 609.6),
        ("10' \u00f7 3", 1016.0),
    ])
    def test_evaluates(self, text, expected_mm):
        assert ScaleManager.parse_dimension(text, "ft") == pytest.approx(
            expected_mm, abs=1e-6)

    @pytest.mark.parametrize("text,expected_mm", [
        ("10'/2/5", 304.8),         # T1-2 review: was 25' (2/5 read as one literal)
        ("10' / 2 / 5", 304.8),
        ("10'/1/2", 1524.0),
        ("6/3/4", 152.4),           # bare, ft default: 0.5 ft
        ("6 / 3/4", 152.4),
        ("10' / (2 1/2)", 1219.2),  # bracketed mixed-number divisor: 4'
    ])
    def test_chained_division_is_left_to_right(self, text, expected_mm):
        assert ScaleManager.parse_dimension(text, "ft") == pytest.approx(
            expected_mm, abs=1e-6)

    def test_metric_bare_division(self):
        assert ScaleManager.parse_dimension("10 / 4", "mm") == pytest.approx(2.5)

    @pytest.mark.parametrize("text", [
        "6' * 2'",          # length x length is an area
        "10' / 2'",         # length / length is a ratio
        "2 / 3'",           # number / length
        "10' / 0",          # divide by zero
        "1/0\"",            # zero denominator
        "(10'", "10')", "()", "10' +", "* 2",
        "5' 6\" 3\"",       # juxtaposed literals: never truncate
        "5ft 6in 2",
        "1m 50mm",
        "1/2 3/4",          # two fractions side by side, not 1 / (2 3/4)
        "3/8 5/16",
        "1/ 2 3/4",         # spacing never changes the reading
        "10' / 2 1/2",      # a mixed-number divisor takes brackets
        "9" * 400,          # over the 200-char cap (inf is unreachable under it;
                            # the isfinite checks are defensive)
        "1" + " + 1" * 150, # over the length cap, deep but valid otherwise
    ])
    def test_rejects(self, text):
        assert ScaleManager.parse_dimension(text, "ft") is None
