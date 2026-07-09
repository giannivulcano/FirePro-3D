"""Tests for the 3-tab hydraulic report widget, exports, and support fields."""

import pytest

from firepro3d.water_supply import WaterSupply


class TestWaterSupplyTestDate:
    def test_test_date_property_exists_and_roundtrips(self, qapp):
        ws = WaterSupply(0, 0)
        props = ws.get_properties()
        assert "Test Date" in props
        assert props["Test Date"]["value"] == ""
        ws.set_property("Test Date", "2026-07-09")
        assert ws.get_properties()["Test Date"]["value"] == "2026-07-09"

    def test_test_date_survives_scene_io_shape(self, qapp):
        """scene_io saves {k: v['value']} and loads via set_property —
        simulate that round trip."""
        ws = WaterSupply(0, 0)
        ws.set_property("Test Date", "2026-07-09")
        saved = {k: v["value"] for k, v in ws.get_properties().items()}
        ws2 = WaterSupply(0, 0)
        for k, v in saved.items():
            ws2.set_property(k, v)
        assert ws2.get_properties()["Test Date"]["value"] == "2026-07-09"
