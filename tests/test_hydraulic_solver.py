"""tests/test_hydraulic_solver.py — Hydraulic solver unit tests."""

import pytest
from firepro3d.equivalent_length import equivalent_length_ft, FITTING_TYPE_MAP


class TestEquivalentLength:
    """NFPA 13 Table 22.4.3.1.1 lookup tests."""

    def test_90_elbow_2_inch(self):
        assert equivalent_length_ft("90elbow", '2"Ø') == 5

    def test_90_elbow_1_inch(self):
        assert equivalent_length_ft("90elbow", '1"Ø') == 2.5

    def test_45_elbow_3_inch(self):
        assert equivalent_length_ft("45elbow", '3"Ø') == 4

    def test_tee_4_inch(self):
        assert equivalent_length_ft("tee", '4"Ø') == 20

    def test_tee_up_is_tee(self):
        assert equivalent_length_ft("tee_up", '2"Ø') == 10

    def test_tee_down_is_tee(self):
        assert equivalent_length_ft("tee_down", '2"Ø') == 10

    def test_elbow_up_is_90(self):
        assert equivalent_length_ft("elbow_up", '2"Ø') == 5

    def test_elbow_down_is_90(self):
        assert equivalent_length_ft("elbow_down", '2"Ø') == 5

    def test_wye_is_45(self):
        assert equivalent_length_ft("wye", '2"Ø') == 3

    def test_cross_4_inch(self):
        assert equivalent_length_ft("cross", '4"Ø') == 20

    def test_cap_is_zero(self):
        assert equivalent_length_ft("cap", '2"Ø') == 0

    def test_no_fitting_is_zero(self):
        assert equivalent_length_ft("no fitting", '2"Ø') == 0

    def test_unknown_fitting_returns_zero(self):
        assert equivalent_length_ft("unknown_type", '2"Ø') == 0

    def test_unknown_diameter_returns_zero(self):
        assert equivalent_length_ft("90elbow", '99"Ø') == 0

    def test_three_quarter_inch(self):
        """Verify future pipe size is in the table."""
        assert equivalent_length_ft("90elbow", '¾"Ø') == 2

    def test_all_fitting_types_mapped(self):
        """Every Fitting.type value must appear in FITTING_TYPE_MAP."""
        expected_types = [
            "no fitting", "cap", "45elbow", "90elbow", "tee", "wye",
            "cross", "tee_up", "tee_down", "elbow_up", "elbow_down",
        ]
        for ft in expected_types:
            assert ft in FITTING_TYPE_MAP, f"{ft} not in FITTING_TYPE_MAP"


# ─────────────────────────────────────────────────────────────────────────────
# Shared mock helpers for Tasks 2–5
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock


def _mock_scale_manager(calibrated=True):
    sm = MagicMock()
    sm.is_calibrated = calibrated
    sm.pixels_per_mm = 1.0
    return sm


def _mock_water_supply(static=80, residual=60, test_flow=500,
                       elevation=0, hose_stream=250):
    ws = MagicMock()
    ws.static_pressure = static
    ws.residual_pressure = residual
    ws.test_flow = test_flow
    ws.elevation = elevation
    ws.hose_stream_allowance = hose_stream
    ws.scenePos.return_value = MagicMock(x=lambda: 0, y=lambda: 0,
                                         manhattanLength=lambda: 0)
    return ws


def _mock_sprinkler_system(supply_ws, nodes=None, pipes=None, sprinklers=None):
    sys = MagicMock()
    sys.supply_node = supply_ws
    sys.nodes = nodes or []
    sys.pipes = pipes or []
    sys.sprinklers = sprinklers or []
    return sys


# ─────────────────────────────────────────────────────────────────────────────
# Task 2: Scale Guard
# ─────────────────────────────────────────────────────────────────────────────

class TestScaleGuard:
    def test_uncalibrated_scale_fails(self):
        from firepro3d.hydraulic_solver import HydraulicSolver
        sm = _mock_scale_manager(calibrated=False)
        ws = _mock_water_supply()
        sys = _mock_sprinkler_system(ws)
        solver = HydraulicSolver(sys, sm)
        result = solver.solve()
        assert result.passed is False
        assert any("not calibrated" in m.lower() or "uncalibrated" in m.lower()
                    for m in result.messages)

    def test_calibrated_scale_proceeds(self):
        from firepro3d.hydraulic_solver import HydraulicSolver
        sm = _mock_scale_manager(calibrated=True)
        ws = _mock_water_supply()
        sys = _mock_sprinkler_system(ws, nodes=[])
        solver = HydraulicSolver(sys, sm)
        result = solver.solve()
        assert not any("calibrat" in m.lower() for m in result.messages)

    def test_none_scale_manager_fails(self):
        from firepro3d.hydraulic_solver import HydraulicSolver
        ws = _mock_water_supply()
        sys = _mock_sprinkler_system(ws)
        solver = HydraulicSolver(sys, None)
        result = solver.solve()
        assert result.passed is False
        assert any("calibrat" in m.lower() for m in result.messages)


# ─────────────────────────────────────────────────────────────────────────────
# Task 3: Friction Loss with Equivalent Lengths
# ─────────────────────────────────────────────────────────────────────────────

class TestFrictionLossWithEquivalentLengths:
    def test_equivalent_length_added_to_physical(self):
        from firepro3d.hydraulic_solver import HydraulicSolver
        sm = _mock_scale_manager()
        sys = _mock_sprinkler_system(None)
        solver = HydraulicSolver(sys, sm)

        def _make_pipe(ft1, ft2):
            pipe = MagicMock()
            pipe._properties = {
                "Diameter": {"value": '2"Ø'},
                "Schedule": {"value": "Sch 40"},
                "C-Factor": {"value": "120"},
            }
            pipe.get_inner_diameter.return_value = 2.067
            pipe.get_length_ft.return_value = 10.0
            n1 = MagicMock(); n1.fitting = MagicMock(); n1.fitting.type = ft1
            n2 = MagicMock(); n2.fitting = MagicMock(); n2.fitting.type = ft2
            pipe.node1 = n1; pipe.node2 = n2
            return pipe

        hf_bare = solver._friction_loss_psi(_make_pipe("no fitting", "no fitting"), 50.0)
        hf_elbows = solver._friction_loss_psi(_make_pipe("90elbow", "90elbow"), 50.0)
        # 10 ft physical + 2×5 ft elbows = 20 ft → hf should be 2× bare
        assert hf_bare > 0
        assert abs(hf_elbows - 2.0 * hf_bare) < 0.001

    def test_supply_node_fitting_excluded(self):
        from firepro3d.hydraulic_solver import HydraulicSolver
        sm = _mock_scale_manager()
        sys = _mock_sprinkler_system(None)
        solver = HydraulicSolver(sys, sm)

        supply_node = MagicMock()
        supply_node.fitting = MagicMock(); supply_node.fitting.type = "tee"
        solver._supply_node = supply_node

        other_node = MagicMock()
        other_node.fitting = MagicMock(); other_node.fitting.type = "90elbow"

        pipe = MagicMock()
        pipe._properties = {"Diameter": {"value": '2"Ø'}, "Schedule": {"value": "Sch 40"}, "C-Factor": {"value": "120"}}
        pipe.get_inner_diameter.return_value = 2.067
        pipe.get_length_ft.return_value = 10.0
        pipe.node1 = supply_node; pipe.node2 = other_node

        hf = solver._friction_loss_psi(pipe, 50.0)
        # Should use 10 + 5 (elbow only, tee excluded) = 15 ft
        pipe_15 = MagicMock()
        pipe_15._properties = pipe._properties
        pipe_15.get_inner_diameter.return_value = 2.067
        pipe_15.get_length_ft.return_value = 15.0
        n1 = MagicMock(); n1.fitting = MagicMock(); n1.fitting.type = "no fitting"
        n2 = MagicMock(); n2.fitting = MagicMock(); n2.fitting.type = "no fitting"
        pipe_15.node1 = n1; pipe_15.node2 = n2
        hf_15 = solver._friction_loss_psi(pipe_15, 50.0)
        assert abs(hf - hf_15) < 0.001


# ─────────────────────────────────────────────────────────────────────────────
# Task 4: Hose Stream Allowance
# ─────────────────────────────────────────────────────────────────────────────

class TestHoseStream:
    def test_result_has_hose_stream_field(self):
        from firepro3d.hydraulic_solver import HydraulicResult
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(HydraulicResult)]
        assert "hose_stream_gpm" in field_names

    def test_hose_stream_zero_no_message(self):
        from firepro3d.hydraulic_solver import HydraulicResult
        # Create a result with zero hose stream — verify field works
        result = HydraulicResult(
            node_pressures={}, pipe_flows={}, pipe_velocity={},
            pipe_friction_loss={}, required_node_pressures={},
            total_demand=100, hose_stream_gpm=0.0,
            required_pressure=30, supply_pressure=50,
            passed=True, messages=[], node_numbers={}, node_labels={},
        )
        assert result.hose_stream_gpm == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Task 5: Required Node Pressures
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredNodePressures:
    def test_result_has_required_node_pressures(self):
        from firepro3d.hydraulic_solver import HydraulicResult
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(HydraulicResult)]
        assert "required_node_pressures" in field_names
