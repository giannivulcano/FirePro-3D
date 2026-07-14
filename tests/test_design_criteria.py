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


class TestPanelView:
    def test_inherited_fields_read_only(self, scene):
        scene._rooms = [_mock_room("A", "Ordinary Hazard Group 2", _SQ_A)]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=1600)
        props = da.get_properties()
        for k in ("Hazard Classification", "System Type", "Design Area (Base)"):
            assert props[k].get("readonly") is True
        assert props["Criteria From"]["value"] == "A"

    def test_fallback_fields_editable(self, scene):
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=1600)
        props = da.get_properties()
        for k in ("Hazard Classification", "System Type", "Design Area (Base)"):
            assert not props[k].get("readonly")

    def test_derived_rows_present(self, scene):
        scene._rooms = [_mock_room("A", "Light Hazard", _SQ_A, system="Dry",
                                   point=(1000.0, 0.10))]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=900)
        props = da.get_properties()
        assert props["Design Density"]["value"] == "0.10 gpm/ft²"
        assert props["Required Area"]["value"] == "1300 ft² (+30% dry)"
        assert "below the required" in props["⚠ Warnings"]["value"]

    def test_set_property_ignored_while_inherited(self, scene):
        scene._rooms = [_mock_room("A", "Ordinary Hazard Group 2", _SQ_A)]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=1600)
        da.get_properties()
        da.set_property("Hazard Classification", "Light Hazard")
        assert da.effective_criteria().hazard == "Ordinary Hazard Group 2"

    def test_show_badge_bool_coercion(self, scene):
        da = _area_with(scene, [])
        da.set_property("Show Badge", "False")
        assert da._properties["Show Badge"]["value"] is False
        da.set_property("Show Badge", True)
        assert da._properties["Show Badge"]["value"] is True

    def test_unknown_hazard_room_disengages(self, scene):
        # corrupt-file case: hazard string with no curve and not storage
        scene._rooms = [_mock_room("A", "Bogus Hazard", _SQ_A, point=None)]
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)], drawn_sqft=1600)
        crit = da.effective_criteria()
        assert not crit.inherited
        assert da._properties["Design Area (Base)"]["value"] == "1500"  # not clobbered


class TestBadgeRows:
    def _da(self, scene, dry=False):
        room = _mock_room("A", "Ordinary Hazard Group 2", _SQ_A,
                          system="Dry" if dry else "Wet",
                          point=(1500.0, 0.20))
        scene._rooms = [room]
        spr = _mock_sprinkler(5000, 5000)
        spr._properties = {"K-Factor": {"value": "5.6"},
                           "Coverage Area": {"value": "130"}}
        da = _area_with(scene, [spr], drawn_sqft=1600)
        da.set_property("System Name", "System 1")
        return da

    def test_rows_before_calc_show_tbd(self, scene):
        rows = self._da(scene).badge_rows()
        flat = str(rows)
        assert "TBD" in flat                      # hydraulic cells
        assert "System 1" in flat
        assert "1600 ft²" in flat                 # drawn area
        assert "0.20" in flat                     # design density

    def test_occupancy_cell_concise(self, scene):
        da = self._da(scene)
        scene._rooms[0]._occupancy = "Office"
        rows = da.badge_rows()
        assert any("OH2 — Office" in str(r) for r in rows)

    def test_zone_and_capacity_dry(self, scene, monkeypatch):
        da = self._da(scene, dry=True)
        pipe = MagicMock()
        pipe.get_inner_diameter.return_value = 2.067
        pipe.get_length_ft.return_value = 100.0
        da.scene().sprinkler_system = MagicMock(pipes=[pipe])
        rows = da.badge_rows()
        flat = str(rows)
        assert "DRY" in flat
        # 0.040802 × 2.067² × 100 ≈ 17.4 gal
        assert "17 gal" in flat

    def test_capacity_na_when_wet(self, scene):
        rows = self._da(scene, dry=False).badge_rows()
        cap_row = [r for r in rows if "SYSTEM CAPACITY" in str(r)][0]
        assert "N/A" in str(cap_row)

    def test_orifice_from_k(self, scene):
        rows = self._da(scene).badge_rows()
        assert any('½"' in str(r) for r in rows)

    def test_after_snapshot_hydraulic_cells_fill(self, scene):
        da = self._da(scene)
        da.set_hydraulic_snapshot({"total_demand_gpm": 750.0,
                                   "demand_psi": 68.3,
                                   "remote_head_psi": 20.0,
                                   "sprinklers_calculated": 27,
                                   "hose_gpm": 250.0})
        flat = str(da.badge_rows())
        assert "1000" in flat        # 750 + 250 hose
        assert "68.3" in flat
        assert "27" in flat
        assert "5.6 @ 20.0 psi" in flat

    def test_occupancy_prefers_governing_room(self, scene):
        a = _mock_room("A", "Light Hazard", _SQ_A)
        a._occupancy = "Office"
        b = _mock_room("B", "Extra Hazard Group 1", _SQ_B, point=(2500.0, 0.30))
        b._occupancy = "Sawmill"
        scene._rooms = [a, b]
        spr_a, spr_b = _mock_sprinkler(5000, 5000), _mock_sprinkler(25000, 5000)
        for s in (spr_a, spr_b):
            s._properties = {"K-Factor": {"value": "5.6"},
                             "Coverage Area": {"value": "130"}}
        da = _area_with(scene, [spr_a, spr_b], drawn_sqft=3000)
        assert any("EH1 — Sawmill" in str(r) for r in da.badge_rows())

    def test_membership_change_clears_snapshot(self, scene):
        da = self._da(scene)
        da.set_hydraulic_snapshot({"total_demand_gpm": 750.0,
                                   "demand_psi": 68.3,
                                   "remote_head_psi": 20.0,
                                   "sprinklers_calculated": 27,
                                   "hose_gpm": 0.0})
        # Monkeypatch _update_shape to avoid walking mock geometry
        da._update_shape = lambda: None
        da.remove_sprinkler(da._sprinklers[0])
        assert da._hyd_snapshot is None


class TestBadgeItem:
    def test_badge_created_with_area(self, scene):
        da = _area_with(scene, [])
        assert da.badge is not None
        assert da.badge.parentItem() is da

    def test_badge_hidden_when_show_badge_false(self, scene):
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)])
        da.set_property("Show Badge", "False")
        assert not da.badge.isVisible()
        da.set_property("Show Badge", "True")
        assert da.badge.isVisible()

    def test_badge_hidden_in_editing_mode(self, scene):
        da = _area_with(scene, [_mock_sprinkler(5000, 5000)])
        scene.mode = "design_area"
        da.sync_z_for_mode(editing=True)
        assert not da.badge.isVisible()
        scene.mode = "select"
        da.sync_z_for_mode(editing=False)
        assert da.badge.isVisible()

    def test_badge_hidden_for_empty_area(self, scene):
        da = _area_with(scene, [])
        da._sync_badge()
        assert not da.badge.isVisible()

    def test_badge_offset_round_trips(self, scene):
        da = _area_with(scene, [])
        da.set_badge_offset(QPointF(1234.0, -500.0))
        assert da.badge_offset() == (1234.0, -500.0)
        assert da._badge_user_moved

    def test_fixed_size_matches_rows_size(self, scene):
        from firepro3d.design_area import badge_fixed_size_mm, badge_size_mm
        da = _area_with(scene, [])
        assert badge_fixed_size_mm() == badge_size_mm(da.badge_rows())


# ── run_hydraulics wiring ────────────────────────────────────────────────────


class TestRunHydraulicsWiring:
    def test_criteria_warnings_prepended_and_snapshot_set(self, qapp):
        """run_hydraulics prepends effective-criteria warnings to the result
        messages and pushes a badge snapshot onto the active design area."""
        from firepro3d.model_space import Model_Space
        from firepro3d.design_area import DesignArea
        from firepro3d.water_supply import WaterSupply

        ms = Model_Space()

        # Build a tiny 2-sprinkler network (2 sprinklers on one branch)
        n1 = ms.add_node(0.0, 0.0)
        n2 = ms.add_node(3000.0, 0.0)
        ms.add_pipe(n1, n2)
        sprs = [ms.add_sprinkler(n1), ms.add_sprinkler(n2)]

        # Attach water supply
        ws = WaterSupply(0.0, 0.0)
        ms.addItem(ws)
        ms.water_supply_node = ws
        ms.sprinkler_system.supply_node = ws

        # Create and wire design area
        da = DesignArea(list(sprs))
        ms.addItem(da)
        ms.design_areas = [da]
        ms.active_design_area = da

        # Force a shortfall: set the Design Area (Base) large enough to exceed
        # any drawn area so effective_criteria() will emit a "below the required" warning.
        da.set_property("Design Area (Base)", "99999")

        # Run hydraulics
        result = ms.run_hydraulics(ms.design_area_sprinklers)

        # criteria warning must have been prepended
        assert any("below the required" in m for m in result.messages), (
            f"Expected shortfall warning in messages: {result.messages}"
        )

        # snapshot must be set
        assert da._hyd_snapshot is not None, "Badge snapshot should have been set"

        # sprinklers_calculated must match the design area sprinkler count
        assert da._hyd_snapshot["sprinklers_calculated"] == len(sprs), (
            f"Expected {len(sprs)} sprinklers, got "
            f"{da._hyd_snapshot['sprinklers_calculated']}"
        )
