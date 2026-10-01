"""ScaleManager.format_factor / parse_factor — the one unitless-ratio
formatter (Scale tool factor; units-and-formatting.md §3.1 grammar, §7 rule 1).
"""
import math

import pytest

from firepro3d.scale_manager import ScaleManager
from firepro3d import dynamic_input

fmt, parse = ScaleManager.format_factor, ScaleManager.parse_factor


@pytest.mark.parametrize("text", [
    "1e3", "1E3", "1_000", "nan", "inf", "-inf", "-0.5", "-2", "+2",
    "", ".", "x", "1,5", "2 2", "0x10",
])
def test_parse_factor_refuses_outside_the_shared_grammar(text):
    assert parse(text) is None                                           # [RED]


@pytest.mark.parametrize("text,value", [
    ("0.5", 0.5), ("2", 2.0), ("1.25", 1.25), (".5", 0.5), ("12.", 12.0),
    ("2x", 2.0), ("1.5 ×", 1.5), (" 3 ", 3.0), ("0", 0.0),
])
def test_parse_factor_accepts_the_shared_grammar(text, value):
    assert parse(text) == pytest.approx(value)


@pytest.mark.parametrize("value,text", [
    (2.0, "2"), (0.5, "0.5"), (1 / 3, "0.3333"), (1.23456, "1.2346"),
    (12345.6, "12345.6"), (0.00002, "0.00002"), (4e-5, "0.00004"),
    (1e-6, "0.000001"), (0.0, "0"), (math.nan, "1"), (math.inf, "1"),
])
def test_format_factor_cases(value, text):
    assert fmt(value) == text                                            # [RED]


def _sweep():
    """Every candidate on a log grid 1e-12 .. 1e12 (VC2: not a hand sample)."""
    return [m * 10.0 ** e for e in range(-12, 13)
            for m in (1.0, 1.234567, 2.5, 3.333333, 5.0, 7.777777, 9.99996)]


def test_every_positive_factor_shows_a_value_enter_accepts():
    """A positive factor never displays as something Enter would refuse
    (``"0"``, scientific notation, ``nan``) and round-trips closely."""
    bad = []
    for v in _sweep():
        s = fmt(v)
        back = parse(s)
        tol = 5e-5 if v >= 1.0 else 5e-4 * v
        if back is None or back <= 0.0 or abs(back - v) > tol + 1e-12 * v:
            bad.append((v, s, back))
    assert bad == []                                                     # [RED]


def test_dynamic_input_shells_delegate():
    assert dynamic_input._format_factor(0.00002) == fmt(0.00002)
    assert dynamic_input._parse_factor("1e3") is parse("1e3") is None   # [RED]
    assert dynamic_input._parse_factor("2x") == parse("2x") == 2.0
