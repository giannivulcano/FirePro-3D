"""SB2a: ScaleManager kind formatters (element-parameters.md; Room move)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.room import Room
from firepro3d.scale_manager import DisplayUnit, ScaleManager


def _sm(unit, precision=3):
    sm = ScaleManager()
    sm.display_unit = unit
    sm.precision = precision
    return sm


# 12e6 mm2 = 12 m2 = 12e6 / 304.8**2 = 129.1669 sq ft
# 3.24e10 mm3 = 32.4 m3 = 3.24e10 / 304.8**3 = 1144.21 cu ft
@pytest.mark.parametrize("unit,area,vol", [
    (DisplayUnit.IMPERIAL, "129.2 sq ft", "1144 cu ft"),
    (DisplayUnit.METRIC_M, "12.00 m\u00b2", "32.4 m\u00b3"),
    (DisplayUnit.METRIC_MM, "12000000 mm\u00b2", "32400000000 mm\u00b3"),
])
def test_area_volume_strings(unit, area, vol):
    sm = _sm(unit)
    assert sm.format_area_mm2(12e6) == area
    assert sm.format_volume_mm3(3.24e10) == vol


@pytest.mark.parametrize("unit,length,area,vol,sqft,pid", [
    (DisplayUnit.IMPERIAL, 914 / 25.4, 12e6 / 304.8 ** 2, 3.24e10 / 304.8 ** 3, 130.0, 1.049),
    (DisplayUnit.METRIC_M, 0.914, 12.0, 32.4, 130.0 * 0.09290304, 1.049 * 25.4),
    (DisplayUnit.METRIC_MM, 914.0, 12e6, 3.24e10, 130.0 * 0.09290304, 1.049 * 25.4),
])
def test_numeric_twins(unit, length, area, vol, sqft, pid):
    sm = _sm(unit)
    assert sm.length_value(914.0) == pytest.approx(length)
    assert sm.area_mm2_value(12e6) == pytest.approx(area)
    assert sm.volume_mm3_value(3.24e10) == pytest.approx(vol)
    assert sm.area_sqft_value(130.0) == pytest.approx(sqft)
    assert sm.pipe_id_value(1.049) == pytest.approx(pid)


def test_hydraulic_and_pipe_id_strings():
    imp, met = _sm(DisplayUnit.IMPERIAL), _sm(DisplayUnit.METRIC_MM)
    for sm in (imp, met):                        # imperial-only quantities
        assert sm.format_pressure(16.04) == "16.0 psi"
        assert sm.format_flow(22.4) == "22 gpm"
        assert sm.format_velocity(5.56) == "5.6 ft/s"
    assert imp.format_pipe_id(1.049) == '1.049"'
    assert met.format_pipe_id(1.049) == "26.6 mm"          # 1.049 * 25.4 = 26.64


def test_room_panel_area_volume_go_through_scale_manager(qapp, make_model_space, monkeypatch):
    """The move (not a copy): Room's panel strings come from the ScaleManager."""
    ms = make_model_space()
    room = Room([QPointF(0, 0), QPointF(4000, 0), QPointF(4000, 3000), QPointF(0, 3000)])
    ms.addItem(room)
    ms._rooms.append(room)
    monkeypatch.setattr(ScaleManager, "format_area_mm2", lambda self, v: "AREA")
    monkeypatch.setattr(ScaleManager, "format_volume_mm3", lambda self, v: "VOL")
    props = room.get_properties()
    assert props["Area"]["value"] == "AREA"
    assert props["Volume"]["value"] == "VOL"
