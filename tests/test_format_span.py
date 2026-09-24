"""ScaleManager.format_span / parse_span — the one unsigned-sweep formatter
(units-and-formatting.md, 'Unsigned sweep' row)."""
import math

from firepro3d.scale_manager import ScaleManager
from firepro3d import dynamic_input


def test_format_span_is_unsigned():
    assert ScaleManager.format_span(270.0) == "270°"      # not -90
    assert ScaleManager.format_span(57.2957795) == "57.3°"
    assert ScaleManager.format_span(90.0) == "90°"
    assert ScaleManager.format_span(math.nan) == "0°"


def test_parse_span_unwrapped():
    assert ScaleManager.parse_span("270°") == 270.0
    assert ScaleManager.parse_span("300") == 300.0
    assert ScaleManager.parse_span("junk") is None
    assert ScaleManager.parse_span("") is None


def test_dynamic_input_shells_delegate():
    assert dynamic_input._format_span(270.0) == ScaleManager.format_span(270.0)
    assert dynamic_input._parse_span("45") == ScaleManager.parse_span("45")
