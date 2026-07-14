"""tests/test_design_criteria.py — Room→DesignArea criteria inheritance."""
import pytest
from unittest.mock import MagicMock
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from firepro3d.design_area import DesignArea


def _mock_room(name, hazard, poly_pts, system="Wet", point=(1500.0, 0.15),
               level="Level 1"):
    r = MagicMock()
    r.name = name
    r._hazard_class = hazard
    r._system_type = system
    r.level = level
    r.boundary = [QPointF(x, y) for x, y in poly_pts]
    r.design_point.return_value = None if point is None else point
    return r


def _mock_sprinkler(x, y, level="Level 1"):
    s = MagicMock()
    s.node.scenePos.return_value = QPointF(x, y)
    s.node.level = level
    return s


_SQ_A = [(0, 0), (10000, 0), (10000, 10000), (0, 10000)]          # room A
_SQ_B = [(20000, 0), (30000, 0), (30000, 10000), (20000, 10000)]  # room B


@pytest.fixture
def scene(qapp):
    sc = QGraphicsScene()
    sc._rooms = []
    return sc


def _area_with(scene, sprinklers, drawn_sqft=0.0):
    da = DesignArea()
    scene.addItem(da)
    da._sprinklers = list(sprinklers)
    if drawn_sqft:
        da._as_entries = [(None, drawn_sqft, 0.0, 0.0)]
    return da


class TestSingleRoom:
    def test_inherits_read_only(self, scene):
        scene._rooms = [_mock_room("A", "Ordinary Hazard Group 2", _SQ_A,
                                   point=(2000.0, 0.18))]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=2100)
        crit = da.effective_criteria()
        assert crit.inherited
        assert crit.hazard == "Ordinary Hazard Group 2"
        assert crit.base_area_sqft == 2000.0
        assert crit.density == 0.18
        assert crit.system_type == "Wet"
        assert crit.required_area_sqft == 2000.0
        assert crit.warnings == []


class TestMultiRoom:
    def test_most_demanding_governs_with_warning(self, scene):
        scene._rooms = [
            _mock_room("A", "Light Hazard", _SQ_A, point=(1500.0, 0.10)),
            _mock_room("B", "Extra Hazard Group 1", _SQ_B, point=(2500.0, 0.30)),
        ]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000),
                                _mock_sprinkler(25000, 5000)], drawn_sqft=3000)
        crit = da.effective_criteria()
        assert crit.hazard == "Extra Hazard Group 1"
        assert crit.base_area_sqft == 2500.0
        assert any("most demanding" in w for w in crit.warnings)

    def test_any_dry_room_makes_system_dry(self, scene):
        scene._rooms = [
            _mock_room("A", "Light Hazard", _SQ_A, system="Dry"),
            _mock_room("B", "Light Hazard", _SQ_B, system="Wet"),
        ]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000),
                                _mock_sprinkler(25000, 5000)], drawn_sqft=5000)
        assert da.effective_criteria().system_type == "Dry"


class TestDryCheck:
    def test_required_area_is_base_times_1_3(self, scene):
        scene._rooms = [_mock_room("A", "Light Hazard", _SQ_A, system="Dry",
                                   point=(1000.0, 0.10))]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=1300)
        crit = da.effective_criteria()
        assert crit.required_area_sqft == pytest.approx(1300.0)
        assert not any("below the required" in w for w in crit.warnings)

    def test_shortfall_raises_warning(self, scene):
        scene._rooms = [_mock_room("A", "Light Hazard", _SQ_A, system="Dry",
                                   point=(1000.0, 0.10))]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=1000)
        assert any("below the required" in w
                   for w in da.effective_criteria().warnings)


class TestDisengage:
    def test_storage_room_disengages_editable(self, scene):
        scene._rooms = [_mock_room("A", "Miscellaneous Storage", _SQ_A,
                                   point=None)]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=1500)
        crit = da.effective_criteria()
        assert not crit.inherited
        assert any("storage protection criteria" in w for w in crit.warnings)

    def test_no_rooms_editable_silent(self, scene):
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=1600)
        crit = da.effective_criteria()
        assert not crit.inherited
        assert crit.hazard == "Ordinary Hazard Group 1"  # stored default
        assert not any("room" in w.lower() for w in crit.warnings)

    def test_disengage_keeps_last_effective(self, scene):
        room = _mock_room("A", "Extra Hazard Group 2", _SQ_A,
                          point=(2500.0, 0.40))
        scene._rooms = [room]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=2600)
        da.effective_criteria()          # inherit + write back
        scene._rooms = []                # room deleted
        crit = da.effective_criteria()
        assert not crit.inherited
        assert crit.hazard == "Extra Hazard Group 2"   # kept
        assert crit.base_area_sqft == 2500.0


class TestMixed:
    def test_roomless_sprinklers_noted(self, scene):
        scene._rooms = [_mock_room("A", "Light Hazard", _SQ_A)]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000),
                                _mock_sprinkler(50000, 50000)], drawn_sqft=1600)
        crit = da.effective_criteria()
        assert crit.inherited
        assert any("outside any room" in w for w in crit.warnings)
