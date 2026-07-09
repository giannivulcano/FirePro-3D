"""Tests for the 3-tab hydraulic report widget, exports, and support fields."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from firepro3d.hydraulic_solver import HydraulicResult
from firepro3d.hydraulic_report import HydraulicReportWidget
from firepro3d.water_supply import WaterSupply


def _mock_pipe(diameter='1"Ø', c_factor="120", length_ft=10.0,
               node1=None, node2=None):
    pipe = MagicMock()
    pipe._properties = {
        "Diameter": {"value": diameter},
        "Schedule": {"value": "Schedule 40"},
        "C-Factor": {"value": c_factor},
        "Material": {"value": "Steel"},
    }
    pipe.node1 = node1
    pipe.node2 = node2
    pipe.length = length_ft * 304.8
    pipe.get_length_ft = MagicMock(return_value=length_ft)
    return pipe


class _Obj:
    """Attribute bag that stays identity-hashable (SimpleNamespace defines
    __eq__, which disables hashing — unusable as a result-dict key)."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _mock_node(z_mm=3000.0, fitting_type=None):
    node = _Obj(z_pos=z_mm, fitting=None)
    if fitting_type:
        node.fitting = SimpleNamespace(type=fitting_type)
    return node


def _mock_sprinkler(node, k="5.6"):
    return SimpleNamespace(node=node, _properties={
        "K-Factor": {"value": k},
        "Min Pressure": {"value": "7"},
    })


def _linear_result_and_scene():
    """Supply(1) -> N2 -> N3(minor '2a' pass-through) -> N4 sprinkler.

    Returns (result, scene, sm) ready for HydraulicReportWidget.populate().
    """
    supply = _mock_node(z_mm=0.0)
    n2 = _mock_node(z_mm=3000.0, fitting_type="90elbow")
    n3 = _mock_node(z_mm=3000.0)
    n4 = _mock_node(z_mm=3000.0)
    p1 = _mock_pipe(node1=supply, node2=n2)
    p2 = _mock_pipe(node1=n2, node2=n3)
    p3 = _mock_pipe(node1=n3, node2=n4)
    spr = _mock_sprinkler(n4)

    result = HydraulicResult(
        node_pressures={supply: 62.0, n2: 58.0, n3: 55.0, n4: 52.0},
        pipe_flows={p1: 14.8, p2: 14.8, p3: 14.8},
        pipe_velocity={p1: 5.5, p2: 5.5, p3: 5.5},
        pipe_friction_loss={p1: 1.2, p2: 1.2, p3: 1.2},
        required_node_pressures={supply: 12.0, n2: 10.5, n3: 8.5, n4: 7.0},
        total_demand=14.8,
        hose_stream_gpm=250.0,
        required_pressure=12.0,
        supply_pressure=62.0,
        passed=True,
        messages=["OK"],
        node_numbers={supply: 1, n2: 2, n4: 3},
        node_labels={supply: "1", n2: "2", n3: "2a", n4: "3"},
        node_parent_pipe={supply: None, n2: p1, n3: p2, n4: p3},
        calc_date="2026-07-09",
    )

    ws = MagicMock()
    ws.static_pressure = 80.0
    ws.residual_pressure = 60.0
    ws.test_flow = 500.0
    ws.elevation = 2.0
    ws.get_properties.return_value = {"Test Date": {"value": "2026-06-01"}}

    da = MagicMock()
    da.sprinklers = [spr]
    da.get_properties.return_value = {
        "Hazard Classification": {"value": "Ordinary Hazard Group 1"},
        "System Name": {"value": "System 1"},
        "Area": {"value": "1500 sq ft"},
    }
    da.compute_area = MagicMock()

    scene = SimpleNamespace(
        _project_info={"name": "Fire Station 4", "number": "FP-104",
                       "address": "12 Main St", "city": "Springfield",
                       "state": "ON", "client": "City", "designer": "GV",
                       "description": "Wet system, Level 1"},
        active_design_area=da,
        design_area_sprinklers=[spr],
        water_supply_node=ws,
        _supply_network_node=supply,
        sprinkler_system=SimpleNamespace(sprinklers=[spr], pipes=[p1, p2, p3]),
    )
    return result, scene, None


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


class TestTabStructure:
    def test_exactly_three_tabs(self, qapp):
        w = HydraulicReportWidget()
        labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
        assert labels == ["Summary", "Node Summary Table", "Hydraulic Graph"]

    def test_node_table_has_14_nfpa_headers(self, qapp):
        from firepro3d.hydraulic_report import NODE_SUMMARY_HEADERS
        w = HydraulicReportWidget()
        assert w._node_table.columnCount() == 14
        headers = [w._node_table.horizontalHeaderItem(i).text()
                   for i in range(w._node_table.columnCount())]
        assert headers == NODE_SUMMARY_HEADERS

    def test_populate_fills_majors_only_by_default(self, qapp):
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        w.populate(result, scene, sm)
        assert w._show_minor_cb.isChecked() is False
        assert w._node_table.rowCount() == 3          # majors 1, 2, 3

    def test_minor_toggle_refills_table(self, qapp):
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        w.populate(result, scene, sm)
        w._show_minor_cb.setChecked(True)
        assert w._node_table.rowCount() == 4          # + minor 2a

    def test_clear_resets(self, qapp):
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        w.populate(result, scene, sm)
        w.clear()
        assert w._node_table.rowCount() == 0
        assert w._summary.toPlainText() == ""


class TestNodeSummaryRows:
    def _widget(self, qapp):
        w = HydraulicReportWidget()
        w._result, w._scene, w._sm = _linear_result_and_scene()
        return w

    def test_majors_only_by_default(self, qapp):
        w = self._widget(qapp)
        rows = w._node_summary_rows(show_minor=False)
        assert [r[0] for r in rows] == ["1", "2", "3"]

    def test_minor_nodes_included_when_toggled(self, qapp):
        w = self._widget(qapp)
        rows = w._node_summary_rows(show_minor=True)
        assert [r[0] for r in rows] == ["1", "2", "2a", "3"]

    def test_row_width_is_14(self, qapp):
        w = self._widget(qapp)
        for row in w._node_summary_rows(show_minor=True):
            assert len(row) == 14

    def test_supply_row_has_no_pipe_data(self, qapp):
        w = self._widget(qapp)
        row = w._node_summary_rows(show_minor=False)[0]
        assert row[0] == "1"
        assert row[2] == "14.8"      # flow at supply = total demand
        assert row[3] == "—"         # no upstream pipe → diameter dash
        assert "Supply" in row[13]

    def test_sprinkler_k_and_fitting_in_notes(self, qapp):
        w = self._widget(qapp)
        rows = w._node_summary_rows(show_minor=False)
        node2_row = rows[1]
        assert "90" in node2_row[13]          # 90° elbow fitting noted
        node4_row = rows[2]
        assert "K=5.6" in node4_row[13]

    def test_elevation_in_feet(self, qapp):
        w = self._widget(qapp)
        rows = w._node_summary_rows(show_minor=False)
        assert rows[1][1] == f"{3000.0 / 304.8:.1f}"

    def test_friction_columns_use_equivalent_length(self, qapp):
        """Row '2a' (pipe p2, 1\"Ø with a 90° elbow at n2): equiv=2.5 ft,
        total=12.5 ft, psi/ft = 1.2/12.5."""
        w = self._widget(qapp)
        rows = w._node_summary_rows(show_minor=True)
        row_2a = next(r for r in rows if r[0] == "2a")
        assert row_2a[4] == "10.0"     # physical ft
        assert row_2a[5] == "2.5"      # 1"Ø 90° elbow equivalent
        assert row_2a[6] == "12.5"     # total
        assert row_2a[8] == "0.096"    # 1.2 / 12.5
        assert row_2a[9] == "1.20"     # total hf


class TestSummarySections:
    def test_sections_present_and_ordered(self, qapp):
        w = HydraulicReportWidget()
        w._result, w._scene, w._sm = _linear_result_and_scene()
        titles = [t for t, _ in w._summary_sections()]
        assert titles == ["Project", "Design Criteria", "Water Supply", "Results"]

    def test_metadata_values(self, qapp):
        w = HydraulicReportWidget()
        w._result, w._scene, w._sm = _linear_result_and_scene()
        sections = dict(w._summary_sections())
        proj = dict(sections["Project"])
        assert proj["Project Name"] == "Fire Station 4"
        assert proj["Calculation Date"] == "2026-07-09"
        crit = dict(sections["Design Criteria"])
        assert crit["Hazard Classification"] == "Ordinary Hazard Group 1"
        assert crit["Design Area"] == "1500 sq ft"
        assert crit["Density"] == "0.15 gpm/ft²"       # OH1 @ 1500 sqft
        assert crit["Sprinklers in Design Area"] == "1"
        ws = dict(sections["Water Supply"])
        assert ws["Test Date"] == "2026-06-01"
        res = dict(sections["Results"])
        assert res["Status"] == "PASS"

    def test_missing_data_degrades_to_dash(self, qapp):
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        scene._project_info = {}
        scene.active_design_area = None
        scene.design_area_sprinklers = []
        scene.water_supply_node = None
        w._result, w._scene, w._sm = result, scene, sm
        sections = dict(w._summary_sections())
        assert dict(sections["Project"])["Project Name"] == "—"
        assert dict(sections["Design Criteria"])["Hazard Classification"] == "—"
        assert dict(sections["Water Supply"])["Static Pressure"] == "—"
