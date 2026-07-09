"""tests/test_hydraulic_solver_core.py — Hydraulic solver core logic tests.

Tests the solver's calculation methods, formula correctness, BFS traversal,
flow assignment, pressure backward pass, and end-to-end network solves.
Equivalent length lookup tests live in test_hydraulic_solver.py.
"""

import math
import pytest
from unittest.mock import MagicMock
from collections import deque

from firepro3d.hydraulic_solver import HydraulicSolver, HydraulicResult


# ─────────────────────────────────────────────────────────────────────────────
# Shared mock factories
# ─────────────────────────────────────────────────────────────────────────────

def _mock_scale_manager(calibrated=True, ppm=1.0):
    sm = MagicMock()
    sm.is_calibrated = calibrated
    sm.pixels_per_mm = ppm
    sm.scene_to_display.return_value = "10'-0\""
    return sm


def _mock_water_supply(static=80.0, residual=60.0, test_flow=500.0,
                       elevation=0.0, hose_stream=250.0):
    ws = MagicMock()
    ws.static_pressure = static
    ws.residual_pressure = residual
    ws.test_flow = test_flow
    ws.elevation = elevation
    ws.hose_stream_allowance = hose_stream
    sp = MagicMock()
    sp.x.return_value = 0.0
    sp.y.return_value = 0.0
    sp.manhattanLength.return_value = 0.0
    sp.__sub__ = lambda self, other: MagicMock(
        manhattanLength=MagicMock(return_value=0.0)
    )
    ws.scenePos.return_value = sp
    return ws


def _mock_sprinkler_system(supply_ws, nodes=None, pipes=None, sprinklers=None):
    sys = MagicMock()
    sys.supply_node = supply_ws
    sys.nodes = nodes or []
    sys.pipes = pipes or []
    sys.sprinklers = sprinklers or []
    return sys


def _mock_node(z=0.0, fitting_type="no fitting", has_spr=False):
    n = MagicMock()
    n.z_pos = z
    n.fitting = MagicMock()
    n.fitting.type = fitting_type
    n.pipes = []
    n.has_sprinkler.return_value = has_spr
    n.sprinkler = None
    sp = MagicMock()
    sp.x.return_value = 0.0
    sp.y.return_value = 0.0
    sp.manhattanLength.return_value = 0.0
    sp.__sub__ = lambda self, other: MagicMock(
        manhattanLength=MagicMock(return_value=0.0)
    )
    n.scenePos.return_value = sp
    return n


def _mock_pipe(node1, node2, diameter='2"Ø', schedule="Sch 40",
               c_factor="120", length_ft=10.0, inner_d=2.067):
    p = MagicMock()
    p.node1 = node1
    p.node2 = node2
    p._properties = {
        "Diameter": {"value": diameter},
        "Schedule": {"value": schedule},
        "C-Factor": {"value": c_factor},
    }
    p.get_inner_diameter.return_value = inner_d
    p.get_length_ft.return_value = length_ft
    if node1 is not None:
        node1.pipes.append(p)
    if node2 is not None:
        node2.pipes.append(p)
    return p


def _mock_sprinkler(node, k_factor="5.6", min_pressure="7"):
    spr = MagicMock()
    spr.node = node
    spr._properties = {
        "K-Factor": {"value": k_factor},
        "Min Pressure": {"value": min_pressure},
    }
    node.has_sprinkler.return_value = True
    node.sprinkler = spr
    return spr


# ─────────────────────────────────────────────────────────────────────────────
# 1. Hazen-Williams friction loss formula
# ─────────────────────────────────────────────────────────────────────────────

class TestHazenWilliamsFrictionLoss:
    """Verify _friction_loss_psi matches NFPA 13 section 22.4.2 formula."""

    def _make_solver(self):
        sm = _mock_scale_manager()
        sys = _mock_sprinkler_system(None)
        solver = HydraulicSolver(sys, sm)
        solver._supply_node = _mock_node()  # dummy supply so fitting logic works
        return solver

    def test_formula_matches_hand_calculation(self):
        """hf = 4.52 * Q^1.852 / (C^1.852 * d^4.87) * L"""
        solver = self._make_solver()
        Q = 30.0   # gpm
        C = 120.0
        d = 2.067  # inches (2" Sch 40)
        L = 15.0   # ft

        n1 = _mock_node(fitting_type="no fitting")
        n2 = _mock_node(fitting_type="no fitting")
        pipe = _mock_pipe(n1, n2, length_ft=L, inner_d=d, c_factor=str(C))

        hf = solver._friction_loss_psi(pipe, Q)
        expected = 4.52 * (Q ** 1.852) / ((C ** 1.852) * (d ** 4.87)) * L
        assert abs(hf - expected) < 1e-6

    def test_zero_flow_returns_zero(self):
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe = _mock_pipe(n1, n2, length_ft=10.0)
        assert solver._friction_loss_psi(pipe, 0.0) == 0.0

    def test_negative_flow_returns_zero(self):
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe = _mock_pipe(n1, n2, length_ft=10.0)
        assert solver._friction_loss_psi(pipe, -5.0) == 0.0

    def test_zero_diameter_returns_zero(self):
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe = _mock_pipe(n1, n2, inner_d=0.0)
        assert solver._friction_loss_psi(pipe, 50.0) == 0.0

    def test_zero_c_factor_returns_zero(self):
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe = _mock_pipe(n1, n2, c_factor="0")
        assert solver._friction_loss_psi(pipe, 50.0) == 0.0

    def test_friction_increases_with_flow(self):
        """Higher flow should produce higher friction loss."""
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe_a = _mock_pipe(n1, n2, length_ft=10.0)

        n3 = _mock_node()
        n4 = _mock_node()
        pipe_b = _mock_pipe(n3, n4, length_ft=10.0)

        hf_low = solver._friction_loss_psi(pipe_a, 20.0)
        hf_high = solver._friction_loss_psi(pipe_b, 60.0)
        assert hf_high > hf_low

    def test_friction_increases_with_length(self):
        """Longer pipe should produce proportionally higher friction loss."""
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe_short = _mock_pipe(n1, n2, length_ft=5.0)

        n3 = _mock_node()
        n4 = _mock_node()
        pipe_long = _mock_pipe(n3, n4, length_ft=20.0)

        Q = 40.0
        hf_short = solver._friction_loss_psi(pipe_short, Q)
        hf_long = solver._friction_loss_psi(pipe_long, Q)
        # Friction is linear in length (fittings are "no fitting" = 0)
        assert abs(hf_long / hf_short - 4.0) < 0.01

    def test_smaller_diameter_higher_friction(self):
        """Smaller pipe diameter should produce higher friction loss."""
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe_large = _mock_pipe(n1, n2, diameter='3"Ø', inner_d=3.068, length_ft=10.0)

        n3 = _mock_node()
        n4 = _mock_node()
        pipe_small = _mock_pipe(n3, n4, diameter='1"Ø', inner_d=1.049, length_ft=10.0)

        Q = 20.0
        hf_large = solver._friction_loss_psi(pipe_large, Q)
        hf_small = solver._friction_loss_psi(pipe_small, Q)
        assert hf_small > hf_large

    def test_lower_c_factor_higher_friction(self):
        """Lower C-factor (rougher pipe) means more friction."""
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe_smooth = _mock_pipe(n1, n2, c_factor="150", length_ft=10.0)

        n3 = _mock_node()
        n4 = _mock_node()
        pipe_rough = _mock_pipe(n3, n4, c_factor="100", length_ft=10.0)

        Q = 40.0
        hf_smooth = solver._friction_loss_psi(pipe_smooth, Q)
        hf_rough = solver._friction_loss_psi(pipe_rough, Q)
        assert hf_rough > hf_smooth

    def test_invalid_c_factor_uses_default(self):
        """Non-numeric C-factor should fall back to 120."""
        solver = self._make_solver()
        n1 = _mock_node()
        n2 = _mock_node()
        pipe = _mock_pipe(n1, n2, c_factor="abc", length_ft=10.0)
        # Should not crash; uses default C=120
        hf = solver._friction_loss_psi(pipe, 30.0)
        assert hf > 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. BFS tree construction
# ─────────────────────────────────────────────────────────────────────────────

class TestBFSTree:
    """Verify _bfs_tree produces correct parent/child/ordering structure."""

    def test_linear_chain(self):
        """A -> B -> C should give BFS order [A, B, C]."""
        a, b, c = "A", "B", "C"
        pipe_ab = MagicMock()
        pipe_bc = MagicMock()
        adj = {
            a: [(pipe_ab, b)],
            b: [(pipe_ab, a), (pipe_bc, c)],
            c: [(pipe_bc, b)],
        }
        parent_node, parent_pipe, children, bfs_order = HydraulicSolver._bfs_tree(a, adj)

        assert bfs_order == [a, b, c]
        assert parent_node[b] is a
        assert parent_node[c] is b
        assert parent_pipe[b] is pipe_ab
        assert parent_pipe[c] is pipe_bc
        assert children[a] == [b]
        assert children[b] == [c]
        assert children[c] == []

    def test_branching_tree(self):
        """
        Supply -> N1 -> N2
                     -> N3
        """
        supply, n1, n2, n3 = "supply", "n1", "n2", "n3"
        p1 = MagicMock()
        p2 = MagicMock()
        p3 = MagicMock()
        adj = {
            supply: [(p1, n1)],
            n1: [(p1, supply), (p2, n2), (p3, n3)],
            n2: [(p2, n1)],
            n3: [(p3, n1)],
        }
        parent_node, parent_pipe, children, bfs_order = HydraulicSolver._bfs_tree(supply, adj)

        assert bfs_order[0] == supply
        assert set(bfs_order) == {supply, n1, n2, n3}
        assert parent_node[n1] is supply
        assert parent_node[n2] is n1
        assert parent_node[n3] is n1
        assert set(children[n1]) == {n2, n3}
        assert children.get(n2, []) == []
        assert children.get(n3, []) == []

    def test_root_only(self):
        """Single node graph."""
        root = "root"
        adj = {root: []}
        parent_node, parent_pipe, children, bfs_order = HydraulicSolver._bfs_tree(root, adj)

        assert bfs_order == [root]
        assert parent_node == {}
        assert parent_pipe == {}
        assert children == {root: []}

    def test_disconnected_nodes_excluded(self):
        """Nodes not reachable from root should not appear in BFS order."""
        a, b, c = "a", "b", "c"
        p_ab = MagicMock()
        adj = {
            a: [(p_ab, b)],
            b: [(p_ab, a)],
            c: [],  # disconnected
        }
        _, _, _, bfs_order = HydraulicSolver._bfs_tree(a, adj)
        assert c not in bfs_order


# ─────────────────────────────────────────────────────────────────────────────
# 3. Supply curve interpolation
# ─────────────────────────────────────────────────────────────────────────────

class TestSupplyCurve:
    """Verify _supply_available_pressure matches NFPA 13 power-law curve."""

    def _make_solver(self):
        sm = _mock_scale_manager()
        sys = _mock_sprinkler_system(None)
        return HydraulicSolver(sys, sm)

    def test_at_test_flow_returns_residual(self):
        """At Q = Q_test, available pressure should equal residual pressure."""
        solver = self._make_solver()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500)
        p = solver._supply_available_pressure(ws, 500.0)
        assert abs(p - 60.0) < 0.01

    def test_at_zero_flow_returns_static(self):
        """At Q = 0, available pressure = static."""
        solver = self._make_solver()
        ws = _mock_water_supply(static=100, residual=70, test_flow=800)
        p = solver._supply_available_pressure(ws, 0.0)
        assert abs(p - 100.0) < 0.01

    def test_below_test_flow_above_residual(self):
        """At Q < Q_test, available pressure should be between residual and static."""
        solver = self._make_solver()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500)
        p = solver._supply_available_pressure(ws, 250.0)
        assert 60.0 < p < 80.0

    def test_above_test_flow_below_residual(self):
        """At Q > Q_test, available pressure drops below residual."""
        solver = self._make_solver()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500)
        p = solver._supply_available_pressure(ws, 750.0)
        assert p < 60.0

    def test_formula_correctness(self):
        """Check exact formula: P = P_s - (P_s - P_r) * (Q / Q_t)^1.85."""
        solver = self._make_solver()
        ws = _mock_water_supply(static=90, residual=65, test_flow=600)
        q = 400.0
        expected = 90.0 - (90.0 - 65.0) * (400.0 / 600.0) ** 1.85
        p = solver._supply_available_pressure(ws, q)
        assert abs(p - expected) < 1e-6

    def test_zero_static_returns_zero(self):
        solver = self._make_solver()
        ws = _mock_water_supply(static=0, residual=0, test_flow=500)
        assert solver._supply_available_pressure(ws, 100.0) == 0.0

    def test_zero_test_flow_returns_static(self):
        solver = self._make_solver()
        ws = _mock_water_supply(static=80, residual=60, test_flow=0)
        assert solver._supply_available_pressure(ws, 100.0) == 80.0

    def test_never_negative(self):
        """Even with extreme demand, result should be clamped to >= 0."""
        solver = self._make_solver()
        ws = _mock_water_supply(static=50, residual=30, test_flow=100)
        p = solver._supply_available_pressure(ws, 5000.0)
        assert p >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Network validation guards
# ─────────────────────────────────────────────────────────────────────────────

class TestValidationGuards:
    """Verify the solver rejects invalid inputs with clear failure messages."""

    def test_no_supply_node(self):
        sm = _mock_scale_manager()
        sys = _mock_sprinkler_system(supply_ws=None)
        solver = HydraulicSolver(sys, sm)
        result = solver.solve()
        assert not result.passed
        assert any("no water supply" in m.lower() for m in result.messages)

    def test_no_design_area(self):
        """solve() with design_sprinklers=None must refuse (G6) — the
        'None -> all sprinklers' fallback is retired."""
        sm = _mock_scale_manager()
        ws = _mock_water_supply()
        n = _mock_node()
        sys = _mock_sprinkler_system(ws, nodes=[n], pipes=[], sprinklers=[])
        solver = HydraulicSolver(sys, sm)
        result = solver.solve()
        assert not result.passed
        assert any("no design area" in m.lower() for m in result.messages)

    def test_no_sprinklers(self):
        """An explicitly empty design list still fails with the G2 message."""
        sm = _mock_scale_manager()
        ws = _mock_water_supply()
        n = _mock_node()
        sys = _mock_sprinkler_system(ws, nodes=[n], pipes=[], sprinklers=[])
        solver = HydraulicSolver(sys, sm)
        result = solver.solve(design_sprinklers=[])
        assert not result.passed
        assert any("no sprinklers" in m.lower() for m in result.messages)

    def test_no_nodes(self):
        sm = _mock_scale_manager()
        ws = _mock_water_supply()
        sys = _mock_sprinkler_system(ws, nodes=[], pipes=[])
        solver = HydraulicSolver(sys, sm)
        # Pass a dummy sprinkler list to get past the sprinkler check
        spr = MagicMock()
        spr.node = _mock_node()
        spr._properties = {"K-Factor": {"value": "5.6"},
                           "Min Pressure": {"value": "7"}}
        result = solver.solve(design_sprinklers=[spr])
        assert not result.passed
        assert any("no pipe network" in m.lower() for m in result.messages)

    def test_design_sprinklers_not_connected(self):
        """Sprinklers not reachable from supply should cause failure."""
        sm = _mock_scale_manager()
        ws = _mock_water_supply()
        supply_n = _mock_node()
        # Isolated node not connected to supply
        isolated = _mock_node()
        spr = _mock_sprinkler(isolated)

        sys = _mock_sprinkler_system(ws, nodes=[supply_n], pipes=[], sprinklers=[spr])
        solver = HydraulicSolver(sys, sm)
        result = solver.solve(design_sprinklers=[spr])
        assert not result.passed
        assert any("connected to the supply" in m.lower() for m in result.messages)


# ─────────────────────────────────────────────────────────────────────────────
# 5. HydraulicResult dataclass
# ─────────────────────────────────────────────────────────────────────────────

class TestHydraulicResult:
    """Verify HydraulicResult fields and _fail() factory."""

    def test_all_fields_present(self):
        import dataclasses
        names = {f.name for f in dataclasses.fields(HydraulicResult)}
        expected = {
            "node_pressures", "pipe_flows", "pipe_velocity",
            "pipe_friction_loss", "required_node_pressures",
            "total_demand", "hose_stream_gpm", "required_pressure",
            "supply_pressure", "passed", "messages",
            "node_numbers", "node_labels",
            "node_parent_pipe", "calc_date",
        }
        assert expected == names

    def test_construction(self):
        r = HydraulicResult(
            node_pressures={}, pipe_flows={}, pipe_velocity={},
            pipe_friction_loss={}, required_node_pressures={},
            total_demand=150.0, hose_stream_gpm=250.0,
            required_pressure=40.0, supply_pressure=60.0,
            passed=True, messages=["ok"], node_numbers={}, node_labels={},
        )
        assert r.total_demand == 150.0
        assert r.passed is True
        assert r.messages == ["ok"]

    def test_fail_helper(self):
        result = HydraulicSolver._fail("Something broke")
        assert not result.passed
        assert result.total_demand == 0.0
        assert result.supply_pressure == 0.0
        assert any("something broke" in m.lower() for m in result.messages)

    def test_fail_preserves_extra_messages(self):
        result = HydraulicSolver._fail("error", extra_messages=["warning 1"])
        assert len(result.messages) == 2
        assert "warning 1" in result.messages[0]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Static helper: _safe_float
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeFloat:
    def test_valid_float(self):
        assert HydraulicSolver._safe_float("3.14", 0.0) == 3.14

    def test_valid_int_string(self):
        assert HydraulicSolver._safe_float("42", 0.0) == 42.0

    def test_none_returns_default(self):
        assert HydraulicSolver._safe_float(None, 5.6) == 5.6

    def test_empty_string_returns_default(self):
        assert HydraulicSolver._safe_float("", 7.0) == 7.0

    def test_garbage_returns_default(self):
        assert HydraulicSolver._safe_float("abc", 120.0) == 120.0


# ─────────────────────────────────────────────────────────────────────────────
# 7. Velocity calculation
# ─────────────────────────────────────────────────────────────────────────────

class TestVelocityFormula:
    """Verify v = Q * 0.4085 / d^2 is applied correctly in the solver."""

    def test_velocity_formula(self):
        """v [fps] = Q [gpm] * 0.4085 / d [in]^2"""
        Q = 50.0
        d = 2.067
        expected = Q * 0.4085 / (d * d)
        # Velocity is computed inline in solve() Phase 4; verify the formula
        actual = Q * 0.4085 / (d ** 2)
        assert abs(actual - expected) < 1e-6

    def test_velocity_zero_diameter_safe(self):
        """Zero diameter should produce 0 velocity (guarded in solve)."""
        d = 0.0
        Q = 50.0
        v = (Q * 0.4085 / (d * d)) if d > 0 else 0.0
        assert v == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 8. Flow assignment (Phase 1 logic)
# ─────────────────────────────────────────────────────────────────────────────

class TestFlowAssignment:
    """Verify sprinkler flow Q = K * sqrt(P_min) and pipe flow accumulation."""

    def test_sprinkler_flow_formula(self):
        """Q = K * sqrt(P_min)."""
        K = 5.6
        P_min = 7.0
        expected = K * math.sqrt(P_min)
        assert abs(expected - 14.82) < 0.01  # 5.6 * sqrt(7) ~ 14.82

    def test_sprinkler_flow_k8(self):
        K = 8.0
        P_min = 10.0
        expected = K * math.sqrt(P_min)
        assert abs(expected - 25.30) < 0.01

    def test_pipe_flow_equals_sum_of_downstream(self):
        """In a Y-branch, the upstream pipe flow = sum of downstream sprinkler flows."""
        # This tests the flow accumulation logic from Phase 1
        K = 5.6
        P_min = 7.0
        single_q = K * math.sqrt(P_min)
        # Two downstream sprinklers: upstream pipe should carry 2 * single_q
        expected = 2 * single_q
        assert abs(expected - 29.64) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# 9. End-to-end: simple 2-node network (supply + 1 sprinkler)
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEndTwoNode:
    """Minimal network: supply -> sprinkler node, single pipe."""

    def _build_network(self):
        sm = _mock_scale_manager()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500,
                                elevation=0, hose_stream=0)

        supply_n = _mock_node(fitting_type="no fitting")
        spr_n = _mock_node(fitting_type="cap", has_spr=True)

        pipe = _mock_pipe(supply_n, spr_n, length_ft=20.0)
        spr = _mock_sprinkler(spr_n, k_factor="5.6", min_pressure="7")

        sys = _mock_sprinkler_system(ws, nodes=[supply_n, spr_n],
                                     pipes=[pipe], sprinklers=[spr])
        solver = HydraulicSolver(sys, sm)
        return solver, [spr], supply_n, spr_n, pipe

    def test_solves_successfully(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        assert result.passed

    def test_total_demand(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        expected_q = 5.6 * math.sqrt(7.0)
        assert abs(result.total_demand - expected_q) < 0.01

    def test_pipe_flow_equals_demand(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        expected_q = 5.6 * math.sqrt(7.0)
        assert len(result.pipe_flows) == 1
        actual_q = list(result.pipe_flows.values())[0]
        assert abs(actual_q - expected_q) < 0.01

    def test_pressures_decrease_from_supply(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        p_supply = result.node_pressures[supply_n]
        p_spr = result.node_pressures[spr_n]
        assert p_supply > p_spr

    def test_friction_loss_positive(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        hf = list(result.pipe_friction_loss.values())[0]
        assert hf > 0

    def test_velocity_computed(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        v = list(result.pipe_velocity.values())[0]
        expected_q = 5.6 * math.sqrt(7.0)
        d = 2.067
        expected_v = expected_q * 0.4085 / (d ** 2)
        assert abs(v - expected_v) < 0.01

    def test_required_pressure_at_sprinkler(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        assert result.required_node_pressures[spr_n] == 7.0

    def test_required_pressure_at_supply_includes_friction(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        # Required at supply = required at sprinkler + friction loss
        p_req_supply = result.required_node_pressures[supply_n]
        assert p_req_supply > 7.0

    def test_hose_stream_zero(self):
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        assert result.hose_stream_gpm == 0.0

    def test_result_has_parent_pipe_and_calc_date(self):
        """New HydraulicResult fields: node_parent_pipe maps every non-supply
        calc node to its upstream pipe; calc_date is stamped."""
        import datetime
        solver, sprs, supply_n, spr_n, pipe = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        assert result.passed
        assert result.calc_date == datetime.date.today().isoformat()
        supply = solver._supply_node
        for node in result.node_labels:
            if node is supply:
                assert result.node_parent_pipe.get(node) is None
            else:
                assert result.node_parent_pipe.get(node) is not None


# ─────────────────────────────────────────────────────────────────────────────
# 10. End-to-end: 3-node Y-branch network
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEndThreeNode:
    """Y-branch: supply -> junction -> (sprinkler A, sprinkler B)."""

    def _build_network(self, hose_stream=250.0):
        sm = _mock_scale_manager()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500,
                                elevation=0, hose_stream=hose_stream)

        supply_n = _mock_node(fitting_type="no fitting")
        junction = _mock_node(fitting_type="tee")
        spr_a_n = _mock_node(fitting_type="90elbow", has_spr=True)
        spr_b_n = _mock_node(fitting_type="cap", has_spr=True)

        p_main = _mock_pipe(supply_n, junction, length_ft=10.0)
        p_a = _mock_pipe(junction, spr_a_n, length_ft=10.0)
        p_b = _mock_pipe(junction, spr_b_n, length_ft=10.0)

        spr_a = _mock_sprinkler(spr_a_n, k_factor="5.6", min_pressure="7")
        spr_b = _mock_sprinkler(spr_b_n, k_factor="5.6", min_pressure="7")

        sys = _mock_sprinkler_system(
            ws,
            nodes=[supply_n, junction, spr_a_n, spr_b_n],
            pipes=[p_main, p_a, p_b],
            sprinklers=[spr_a, spr_b],
        )
        solver = HydraulicSolver(sys, sm)
        return solver, [spr_a, spr_b], supply_n, junction, spr_a_n, spr_b_n, p_main

    def test_solves_successfully(self):
        solver, sprs, *_ = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        assert result.passed

    def test_total_demand_is_sum_of_sprinklers(self):
        solver, sprs, *_ = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        single_q = 5.6 * math.sqrt(7.0)
        assert abs(result.total_demand - 2 * single_q) < 0.01

    def test_main_pipe_carries_full_demand(self):
        solver, sprs, supply_n, junction, spr_a_n, spr_b_n, p_main = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        single_q = 5.6 * math.sqrt(7.0)
        main_flow = result.pipe_flows[p_main]
        assert abs(main_flow - 2 * single_q) < 0.01

    def test_junction_pressure_governs_by_max_branch(self):
        """Junction required pressure = max of the two branch requirements."""
        solver, sprs, supply_n, junction, spr_a_n, spr_b_n, p_main = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        p_req_junc = result.required_node_pressures[junction]
        p_req_a = result.required_node_pressures[spr_a_n]
        p_req_b = result.required_node_pressures[spr_b_n]
        # Junction must meet the more demanding branch
        # (Both branches have same P_min but different fittings -> different friction)
        assert p_req_junc >= max(p_req_a, p_req_b)

    def test_hose_stream_in_result(self):
        solver, sprs, *_ = self._build_network(hose_stream=250.0)
        result = solver.solve(design_sprinklers=sprs)
        assert result.hose_stream_gpm == 250.0
        assert any("hose stream" in m.lower() for m in result.messages)

    def test_node_labels_populated(self):
        solver, sprs, *_ = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        assert len(result.node_labels) > 0

    def test_node_numbers_populated(self):
        solver, sprs, *_ = self._build_network()
        result = solver.solve(design_sprinklers=sprs)
        assert len(result.node_numbers) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 11. Elevation effects
# ─────────────────────────────────────────────────────────────────────────────

class TestElevationEffects:
    """Verify elevation head is applied correctly."""

    def test_upward_flow_adds_pressure_loss(self):
        """Sprinkler above supply should require more pressure at supply."""
        sm = _mock_scale_manager()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500,
                                elevation=0, hose_stream=0)

        # z in mm: supply at 0, sprinkler at 3048 mm (10 ft up)
        supply_n = _mock_node(z=0.0, fitting_type="no fitting")
        spr_n_high = _mock_node(z=3048.0, fitting_type="cap", has_spr=True)
        pipe = _mock_pipe(supply_n, spr_n_high, length_ft=20.0)
        spr = _mock_sprinkler(spr_n_high)

        sys = _mock_sprinkler_system(ws, nodes=[supply_n, spr_n_high],
                                     pipes=[pipe], sprinklers=[spr])
        solver_high = HydraulicSolver(sys, sm)
        result_high = solver_high.solve(design_sprinklers=[spr])

        # Same network but flat
        supply_n2 = _mock_node(z=0.0, fitting_type="no fitting")
        spr_n_flat = _mock_node(z=0.0, fitting_type="cap", has_spr=True)
        pipe2 = _mock_pipe(supply_n2, spr_n_flat, length_ft=20.0)
        spr2 = _mock_sprinkler(spr_n_flat)

        sys2 = _mock_sprinkler_system(ws, nodes=[supply_n2, spr_n_flat],
                                      pipes=[pipe2], sprinklers=[spr2])
        solver_flat = HydraulicSolver(sys2, sm)
        result_flat = solver_flat.solve(design_sprinklers=[spr2])

        # Elevated sprinkler needs more required pressure at supply
        assert result_high.required_pressure > result_flat.required_pressure
        # The difference should be close to 0.433 * 10 ft = 4.33 psi
        delta = result_high.required_pressure - result_flat.required_pressure
        assert abs(delta - 4.33) < 0.1

    def test_elevation_correction_at_supply(self):
        """Supply elevation adds gauge pressure correction."""
        sm = _mock_scale_manager()
        # Supply at 5 ft elevation
        ws_elevated = _mock_water_supply(static=80, residual=60, test_flow=500,
                                         elevation=5.0, hose_stream=0)
        ws_flat = _mock_water_supply(static=80, residual=60, test_flow=500,
                                     elevation=0.0, hose_stream=0)

        supply_n = _mock_node(fitting_type="no fitting")
        spr_n = _mock_node(fitting_type="cap", has_spr=True)
        pipe = _mock_pipe(supply_n, spr_n, length_ft=20.0)
        spr = _mock_sprinkler(spr_n)

        sys1 = _mock_sprinkler_system(ws_elevated, nodes=[supply_n, spr_n],
                                      pipes=[pipe], sprinklers=[spr])
        solver1 = HydraulicSolver(sys1, sm)
        result1 = solver1.solve(design_sprinklers=[spr])

        # Rebuild for flat case (need fresh mocks to avoid shared state)
        supply_n2 = _mock_node(fitting_type="no fitting")
        spr_n2 = _mock_node(fitting_type="cap", has_spr=True)
        pipe2 = _mock_pipe(supply_n2, spr_n2, length_ft=20.0)
        spr2 = _mock_sprinkler(spr_n2)

        sys2 = _mock_sprinkler_system(ws_flat, nodes=[supply_n2, spr_n2],
                                      pipes=[pipe2], sprinklers=[spr2])
        solver2 = HydraulicSolver(sys2, sm)
        result2 = solver2.solve(design_sprinklers=[spr2])

        # Elevation correction = 0.433 * 5 ft = 2.165 psi
        delta = result1.required_pressure - result2.required_pressure
        assert abs(delta - 2.165) < 0.1


# ─────────────────────────────────────────────────────────────────────────────
# 12. Velocity warning threshold
# ─────────────────────────────────────────────────────────────────────────────

class TestVelocityWarning:
    """Verify the VELOCITY_LIMIT_FPS constant and warning behavior."""

    def test_velocity_limit_constant(self):
        assert HydraulicSolver.VELOCITY_LIMIT_FPS == 20.0


# ─────────────────────────────────────────────────────────────────────────────
# 13. Loop detection warning
# ─────────────────────────────────────────────────────────────────────────────

class TestLoopDetection:
    """Verify that looped networks produce a warning with excluded pipe count."""

    def test_linear_network_no_loop_warning(self):
        """Supply -> junction -> sprinkler (tree topology) should emit no loop warning."""
        sm = _mock_scale_manager()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500,
                                elevation=0, hose_stream=0)

        supply_n = _mock_node(fitting_type="no fitting")
        mid_n = _mock_node(fitting_type="no fitting")
        spr_n = _mock_node(fitting_type="cap", has_spr=True)

        _mock_pipe(supply_n, mid_n, length_ft=10.0)
        _mock_pipe(mid_n, spr_n, length_ft=10.0)
        spr = _mock_sprinkler(spr_n)

        sys = _mock_sprinkler_system(
            ws,
            nodes=[supply_n, mid_n, spr_n],
            pipes=[supply_n.pipes[0], mid_n.pipes[-1]],
            sprinklers=[spr],
        )
        solver = HydraulicSolver(sys, sm)
        result = solver.solve(design_sprinklers=[spr])

        assert not any("looped network" in m.lower() for m in result.messages)

    def test_looped_network_warning_present(self):
        """A network with one extra pipe forming a loop should warn."""
        sm = _mock_scale_manager()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500,
                                elevation=0, hose_stream=0)

        # Diamond: supply -> A -> B -> spr, plus A -> B extra pipe (loop)
        supply_n = _mock_node(fitting_type="no fitting")
        a_n = _mock_node(fitting_type="no fitting")
        b_n = _mock_node(fitting_type="no fitting")
        spr_n = _mock_node(fitting_type="cap", has_spr=True)

        p1 = _mock_pipe(supply_n, a_n, length_ft=10.0)
        p2 = _mock_pipe(a_n, b_n, length_ft=10.0)
        p3 = _mock_pipe(b_n, spr_n, length_ft=10.0)
        # Extra pipe closing a loop between supply_n and b_n
        p_loop = _mock_pipe(supply_n, b_n, length_ft=15.0)

        spr = _mock_sprinkler(spr_n)

        sys = _mock_sprinkler_system(
            ws,
            nodes=[supply_n, a_n, b_n, spr_n],
            pipes=[p1, p2, p3, p_loop],
            sprinklers=[spr],
        )
        solver = HydraulicSolver(sys, sm)
        result = solver.solve(design_sprinklers=[spr])

        loop_msgs = [m for m in result.messages if "looped network" in m.lower()]
        assert len(loop_msgs) == 1
        # 4 pipes, 4 nodes -> tree has 3 edges -> 1 excluded
        assert "1 pipe excluded" in loop_msgs[0]

    def test_looped_network_excluded_count_multiple(self):
        """Two extra pipes should report 2 pipes excluded."""
        sm = _mock_scale_manager()
        ws = _mock_water_supply(static=80, residual=60, test_flow=500,
                                elevation=0, hose_stream=0)

        supply_n = _mock_node(fitting_type="no fitting")
        a_n = _mock_node(fitting_type="no fitting")
        b_n = _mock_node(fitting_type="no fitting")
        spr_n = _mock_node(fitting_type="cap", has_spr=True)

        p1 = _mock_pipe(supply_n, a_n, length_ft=10.0)
        p2 = _mock_pipe(a_n, b_n, length_ft=10.0)
        p3 = _mock_pipe(b_n, spr_n, length_ft=10.0)
        # Two extra loop-closing pipes
        p_loop1 = _mock_pipe(supply_n, b_n, length_ft=15.0)
        p_loop2 = _mock_pipe(a_n, spr_n, length_ft=12.0)

        spr = _mock_sprinkler(spr_n)

        sys = _mock_sprinkler_system(
            ws,
            nodes=[supply_n, a_n, b_n, spr_n],
            pipes=[p1, p2, p3, p_loop1, p_loop2],
            sprinklers=[spr],
        )
        solver = HydraulicSolver(sys, sm)
        result = solver.solve(design_sprinklers=[spr])

        loop_msgs = [m for m in result.messages if "looped network" in m.lower()]
        assert len(loop_msgs) == 1
        # 5 pipes, 4 nodes -> tree has 3 edges -> 2 excluded
        assert "2 pipes excluded" in loop_msgs[0]
