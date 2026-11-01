"""ScaleManager hydraulic precision, with_overrides and the unit list
(text-sizing-wrap design D8 / D9; AC7)."""
import pytest

from firepro3d.constants import (DEFAULT_FLOW_PRECISION, DEFAULT_PRESSURE_PRECISION,
                                 DEFAULT_VELOCITY_PRECISION, DISPLAY_PRECISION_MAX)
from firepro3d.scale_manager import DisplayUnit, ScaleManager

_HYD = ("pressure_precision", "flow_precision", "velocity_precision")


def _sm(unit, precision=3):
    sm = ScaleManager()
    sm.display_unit = unit
    sm.precision = precision
    return sm


def test_hydraulic_precision_defaults_print_todays_strings():
    sm = ScaleManager()
    assert (DEFAULT_PRESSURE_PRECISION, DEFAULT_FLOW_PRECISION,
            DEFAULT_VELOCITY_PRECISION, DISPLAY_PRECISION_MAX) == (1, 0, 1, 5)
    assert tuple(getattr(sm, a) for a in _HYD) == (1, 0, 1)
    # the strings test_sb2a_formatters pins today (AC7: nothing moves)
    assert sm.format_pressure(16.04) == "16.0 psi"
    assert sm.format_flow(22.4) == "22 gpm"
    assert sm.format_velocity(5.56) == "5.6 ft/s"


def test_hydraulic_precision_drives_the_formatters():
    sm = ScaleManager()
    sm.pressure_precision, sm.flow_precision, sm.velocity_precision = 2, 1, 3
    assert sm.format_pressure(12.34) == "12.34 psi"
    assert sm.format_flow(52.5) == "52.5 gpm"
    assert sm.format_velocity(5.5567) == "5.557 ft/s"
    sm.pressure_precision = 9                 # clamped like ``precision``
    sm.flow_precision = -2
    assert (sm.pressure_precision, sm.flow_precision) == (5, 0)


def test_hydraulic_precision_serialises_sparsely():
    assert not set(_HYD) & set(ScaleManager().to_dict())     # default: byte-identical
    sm = ScaleManager()
    sm.pressure_precision = 2
    d = sm.to_dict()
    assert d["pressure_precision"] == 2
    assert "flow_precision" not in d and "velocity_precision" not in d
    sm2 = ScaleManager.from_dict(d)
    assert tuple(getattr(sm2, a) for a in _HYD) == (2, 0, 1)
    legacy = ScaleManager.from_dict({"display_unit": "imperial", "precision": 3})
    assert tuple(getattr(legacy, a) for a in _HYD) == (1, 0, 1)
    bad = ScaleManager.from_dict({"pressure_precision": "abc", "flow_precision": None})
    assert (bad.pressure_precision, bad.flow_precision) == (1, 0)


def test_with_overrides_without_arguments_is_the_manager_itself():
    sm = ScaleManager()
    assert sm.with_overrides() is sm


def test_with_overrides_clones_and_never_mutates_the_project():
    sm = _sm(DisplayUnit.METRIC_M, 3)
    c = sm.with_overrides(unit="mm", precision=1)
    assert c is not sm
    assert c.format_length(3010.0) == "3010.0 mm"
    assert c.format_pressure(12.34) == "12.3 psi"          # the precision reaches pressure too
    assert sm.with_overrides(precision=2).format_pressure(12.34) == "12.34 psi"
    assert sm.format_length(3010.0) == "3.010 m"
    assert sm.format_pressure(12.34) == "12.3 psi"
    assert (sm.display_unit, sm.precision, sm.pressure_precision) == (DisplayUnit.METRIC_M, 3, 1)
    assert sm.with_overrides(precision=9).precision == 5    # clamped
    assert sm.with_overrides(unit="furlong").format_length(3010.0) == "3.010 m"


def test_with_overrides_imperial_precision_is_the_fraction_denominator():
    sm = _sm(DisplayUnit.IMPERIAL, 3)
    # 3010 mm = 118.504 in = 9' 10.504": eighths -> 4/8 = 1/2; whole inches -> 119 = 9' 11"
    assert sm.format_length(3010.0) == '9\' 10 1/2"'
    assert sm.with_overrides(precision=0).format_length(3010.0) == '9\' 11"'
    assert sm.with_overrides(unit=DisplayUnit.IMPERIAL, precision=1).format_length(3010.0) == '9\' 10 1/2"'


# 12e6 mm2 = 129.1669 sq ft = 12 m2; 3.24e10 mm3 = 1144.1952 cu ft = 32.4 m3
@pytest.mark.parametrize("unit,area,vol", [
    ("imperial", "129.17 sq ft", "1144.20 cu ft"),
    ("m", "12.00 m\u00b2", "32.40 m\u00b3"),
    ("mm", "12000000.00 mm\u00b2", "32400000000.00 mm\u00b3"),
])
def test_with_overrides_area_volume_follow_the_length_family(unit, area, vol):
    c = _sm(DisplayUnit.METRIC_MM).with_overrides(unit=unit, precision=2)
    assert c.format_area_mm2(12e6) == area
    assert c.format_volume_mm3(3.24e10) == vol


def test_display_unit_options_have_one_home():
    from firepro3d.scale_manager import DISPLAY_UNIT_OPTIONS
    from firepro3d.settings import panes
    assert DISPLAY_UNIT_OPTIONS == (("Imperial (ft-in)", "imperial"),
                                    ("Metric (m)", "m"), ("Metric (mm)", "mm"))
    assert panes._UNIT_OPTIONS is DISPLAY_UNIT_OPTIONS
    assert {v for _label, v in DISPLAY_UNIT_OPTIONS} == {u.value for u in DisplayUnit}
