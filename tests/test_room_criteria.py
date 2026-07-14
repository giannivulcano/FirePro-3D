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
