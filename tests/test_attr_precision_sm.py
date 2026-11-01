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
