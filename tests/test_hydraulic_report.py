"""Tests for the 3-tab hydraulic report widget, exports, and support fields."""

import csv as csv_mod
import io
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
    n4 = _mock_node(z_mm=3000.0, fitting_type="tee")   # sprinkler node — fitting must NOT show in Notes
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

    from firepro3d.design_area import EffectiveCriteria
    da = MagicMock()
    da.sprinklers = [spr]
    da.get_properties.return_value = {
        "Hazard Classification": {"value": "Ordinary Hazard Group 1"},
        "System Name": {"value": "System 1"},
        "Area": {"value": "1500 sq ft"},
    }
    da.compute_area = MagicMock()
    da.effective_criteria.return_value = EffectiveCriteria(
        hazard="Ordinary Hazard Group 1",
        base_area_sqft=1500.0,
        density=0.15,
        system_type="Wet",
        inherited=False,
        governing_room=None,
        required_area_sqft=1500.0,
        drawn_area_sqft=1500.0,
        warnings=[],
    )

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


class TestDomesticAllowance:
    def test_property_present_default_zero(self, qapp):
        from firepro3d.water_supply import WaterSupply
        ws = WaterSupply()
        assert ws.get_properties()["Domestic Water Allowance"]["value"] == "0"
        assert ws.domestic_allowance_gpm == 0.0

    def test_accessor_parses(self, qapp):
        from firepro3d.water_supply import WaterSupply
        ws = WaterSupply()
        ws.set_property("Domestic Water Allowance", "75")
        assert ws.domestic_allowance_gpm == 75.0

    def test_accessor_garbage_returns_zero(self, qapp):
        from firepro3d.water_supply import WaterSupply
        ws = WaterSupply()
        ws.set_property("Domestic Water Allowance", "abc")
        assert ws.domestic_allowance_gpm == 0.0


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
        assert "90" in node2_row[13]          # 90° elbow fitting noted (plain junction)
        node4_row = rows[2]
        assert "K=5.6" in node4_row[13]
        assert "Tee" not in node4_row[13]     # sprinkler node: fitting is noise
        supply_row = rows[0]
        assert "Supply" in supply_row[13]

    def test_messages_render_above_sections(self, qapp):
        """A failed calc's reason must be the first thing read in the report."""
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        result.messages = ["No design area defined — create a design area "
                           "before running hydraulics."]
        w.populate(result, scene, sm)
        text = w._summary.toPlainText()
        assert text.index("No design area") < text.index("Project")

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


class TestSummaryTab:
    def test_summary_html_contains_all_sections_and_values(self, qapp):
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        w.populate(result, scene, sm)
        text = w._summary.toPlainText()
        for expected in ("Project", "Design Criteria", "Water Supply",
                         "Fire Station 4", "Ordinary Hazard Group 1",
                         "0.15 gpm/ft²", "2026-06-01", "2026-07-09",
                         "PASS", "14.8", "12.0", "62.0", "OK"):
            assert expected in text, f"missing {expected!r}"

    def test_summary_renders_on_failed_result_without_supply(self, qapp):
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        result.passed = False
        result.messages = ["No design area defined — create a design area "
                           "before running hydraulics."]
        scene.water_supply_node = None
        scene.active_design_area = None
        scene.design_area_sprinklers = []
        scene._project_info = {}
        w.populate(result, scene, sm)
        text = w._summary.toPlainText()
        assert "FAIL" in text
        assert "No design area" in text
        assert "—" in text

    def test_summary_escapes_user_html(self, qapp):
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        scene._project_info = {"name": "A & B <Co>"}
        w.populate(result, scene, sm)
        assert "A & B <Co>" in w._summary.toPlainText()


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
        assert crit["System Type"] == "Wet"
        assert crit["Design Point"] == "1500 ft² @ 0.15 gpm/ft²"
        assert crit["Required Area"] == "1500 ft²"
        assert crit["Drawn Area"] == "1500 sq ft"
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


class TestExports:
    def _populated(self, qapp):
        w = HydraulicReportWidget()
        result, scene, sm = _linear_result_and_scene()
        w.populate(result, scene, sm)
        return w

    def test_csv_structure_and_parseability(self, qapp):
        from firepro3d.hydraulic_report import NODE_SUMMARY_HEADERS
        w = self._populated(qapp)
        buf = io.StringIO()
        w._write_csv(buf)
        buf.seek(0)
        rows = list(csv_mod.reader(buf))
        flat = ["|".join(r) for r in rows]
        assert any("PROJECT" in s for s in flat)
        assert any("DESIGN CRITERIA" in s for s in flat)
        assert any("WATER SUPPLY" in s for s in flat)
        assert any("NODE SUMMARY" in s for s in flat)
        assert not any("SPRINKLER SCHEDULE" in s for s in flat)
        assert not any("PIPE SCHEDULE" in s for s in flat)
        header_i = next(i for i, r in enumerate(rows) if r == NODE_SUMMARY_HEADERS)
        data = rows[header_i + 1:header_i + 4]
        assert len(data) == 3                      # majors only (toggle off)
        assert all(len(r) == 14 for r in data)

    def test_csv_respects_minor_toggle(self, qapp):
        from firepro3d.hydraulic_report import NODE_SUMMARY_HEADERS
        w = self._populated(qapp)
        w._show_minor_cb.setChecked(True)
        buf = io.StringIO()
        w._write_csv(buf)
        buf.seek(0)
        rows = list(csv_mod.reader(buf))
        header_i = next(i for i, r in enumerate(rows) if r == NODE_SUMMARY_HEADERS)
        data = [r for r in rows[header_i + 1:] if len(r) == 14]
        assert len(data) == 4                      # includes 2a

    def test_html_has_node_table_and_graph_no_schedules(self, qapp):
        w = self._populated(qapp)
        out = w._build_html()
        assert "Node Summary" in out
        assert "hydraulic_graph" in out            # <img src='hydraulic_graph'>
        assert "Fire Station 4" in out
        assert "Sprinkler Schedule" not in out
        assert "Pipe Schedule" not in out
        assert "Pipe Results" not in out

    def test_graph_image_renders(self, qapp):
        w = self._populated(qapp)
        img = w._graph_image()
        assert not img.isNull()
        assert img.width() == 1000

    def test_pdf_export_writes_file(self, qapp, tmp_path, monkeypatch):
        from firepro3d.hydraulic_report import _PRINTER_AVAILABLE
        if not _PRINTER_AVAILABLE:
            pytest.skip("QtPrintSupport unavailable")
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        w = self._populated(qapp)
        out = tmp_path / "report.pdf"
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (str(out), "")))
        monkeypatch.setattr(QMessageBox, "information",
                            staticmethod(lambda *a, **k: None))
        w._export_pdf()
        # The embedded 1000×620 graph image dominates the file size — a low
        # size means the ImageResource silently failed to resolve.
        assert out.exists() and out.stat().st_size > 5000

    def test_export_default_dir_is_project_hc_reports(self, qapp, tmp_path):
        w = self._populated(qapp)
        w._scene._project_path = str(tmp_path / "job.fpd")
        d = w._export_dir()
        assert d == str(tmp_path / "HC Reports")
        assert (tmp_path / "HC Reports").is_dir()

    def test_export_default_dir_without_saved_project(self, qapp):
        w = self._populated(qapp)      # fixture scene has no _project_path
        assert w._export_dir() == ""

    def test_graph_resets_when_supply_removed(self, qapp):
        """Re-populating after the water supply is gone must not leave a
        stale curve on screen (or baked into an exported PDF)."""
        w = self._populated(qapp)
        assert w._graph._p_static == 80.0
        result, scene, sm = _linear_result_and_scene()
        result.total_demand = 0.0
        scene.water_supply_node = None
        w.populate(result, scene, sm)
        assert w._graph._p_static == 0.0
        assert w._graph._q_demand == 0.0
