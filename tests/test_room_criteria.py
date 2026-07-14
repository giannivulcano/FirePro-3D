"""tests/test_room_criteria.py — Room protection criteria + serialization."""
import pytest
from PyQt6.QtCore import QPointF
from firepro3d.room import Room

_SQUARE = [QPointF(0, 0), QPointF(5000, 0), QPointF(5000, 5000), QPointF(0, 5000)]


@pytest.fixture
def room(qapp):
    return Room(boundary=list(_SQUARE))


class TestDefaults:
    def test_occupancy_defaults_empty(self, room):
        assert room._occupancy == ""

    def test_system_type_defaults_wet(self, room):
        assert room._system_type == "Wet"

    def test_design_point_defaults_to_curve_minimum(self, room):
        # default hazard = Light Hazard → (1500, 0.10)
        assert room.design_point() == (1500, 0.10)

    def test_design_point_none_for_storage(self, room):
        room.set_property("Hazard Class", "Miscellaneous Storage")
        assert room.design_point() is None


class TestSetProperty:
    def test_occupancy(self, room):
        room.set_property("Occupancy", "Office")
        assert room._occupancy == "Office"

    def test_system_type_validated(self, room):
        room.set_property("System Type", "Dry")
        assert room._system_type == "Dry"
        room.set_property("System Type", "Bogus")
        assert room._system_type == "Dry"  # unchanged


class TestSerialization:
    def test_round_trip(self, room, qapp):
        room.set_property("Occupancy", "Office")
        room.set_property("System Type", "Dry")
        room._design_point = (2000.0, 0.13)
        clone = Room.from_dict(room.to_dict())
        assert clone._occupancy == "Office"
        assert clone._system_type == "Dry"
        assert clone.design_point() == (2000.0, 0.13)

    def test_old_file_without_criteria_loads(self, room, qapp):
        data = room.to_dict()
        for k in ("occupancy", "system_type", "design_point"):
            data.pop(k, None)
        clone = Room.from_dict(data)
        assert clone._occupancy == ""
        assert clone._system_type == "Wet"
        assert clone._design_point is None


class TestPanelSections:
    def test_headers_present_in_order(self, room):
        keys = list(room.get_properties().keys())
        h1, h2, h3 = (keys.index("Room Info"), keys.index("Geometry"),
                      keys.index("Protection Criteria"))
        assert h1 < h2 < h3
        for k in ("Room Info", "Geometry", "Protection Criteria"):
            assert room.get_properties()[k]["type"] == "header"

    def test_criteria_fields_in_criteria_section(self, room):
        keys = list(room.get_properties().keys())
        crit = keys.index("Protection Criteria")
        for k in ("Hazard Class", "Occupancy", "System Type", "Design Point"):
            assert keys.index(k) > crit

    def test_design_point_button_face(self, room):
        meta = room.get_properties()["Design Point"]
        assert meta["type"] == "button"
        assert meta["value"] == "1500 ft² @ 0.10 gpm/ft²"

    def test_design_point_button_storage_hazard(self, room):
        room.set_property("Hazard Class", "High Piled Storage")
        meta = room.get_properties()["Design Point"]
        assert "N/A" in meta["value"]


def test_design_point_dialog_returns_selection(qapp):
    from firepro3d.design_point_dialog import DesignPointDialog
    dlg = DesignPointDialog("Ordinary Hazard Group 1", current=(1500, 0.15))
    assert dlg.selected_point() == (1500, 0.15)
    dlg._on_point(0.12, 3000.0)  # graph emits (density, area)
    assert dlg.selected_point() == (3000.0, 0.12)
