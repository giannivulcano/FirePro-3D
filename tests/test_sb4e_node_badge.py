"""SB4e guards (.todo/sb4e-phase2.md G1-G10)."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import element_params as ep
from tests._sb4e_helpers import dispose, solve, tree_scene


@pytest.fixture
def tree(qapp):
    ms, sec, tabs, nodes = tree_scene()
    yield ms, nodes
    dispose(ms, sec, tabs)


def test_g10_node_keys_equal_the_solver_result(tree):
    ms, nodes = tree
    assert ep.category_of(nodes[1]) == "Hydraulic Node"
    assert all(ep.host_values(n)[k].raw is None for n in nodes
               for k in ("NodeNumber", "RequiredPressure", "Pressure", "Flow", "TotalFlow"))
    r = solve(ms)
    for n in nodes:
        hv = ep.host_values(n)
        assert hv["NodeNumber"].raw == (r.node_labels.get(n) or None)
        assert hv["RequiredPressure"].raw == r.required_node_pressures.get(n)
        assert hv["Pressure"].raw == r.node_pressures.get(n)
        flows = [abs(r.pipe_flows[p]) for p in n.pipes if p in r.pipe_flows]
        assert hv["TotalFlow"].raw == (max(flows) if flows else None)
        if n.has_sprinkler():
            k = float(n.sprinkler._properties["K-Factor"]["value"])
            assert hv["Flow"].raw == pytest.approx(k * math.sqrt(r.node_pressures[n]))
        else:
            assert hv["Flow"].raw is None


def test_g10_category_is_offered_to_the_block_editor():
    opts, _cur, _warn = ep.category_choice("")
    assert "Hydraulic Node" in opts
    assert set(ep.PARAMS["Hydraulic Node"]) == {
        "NodeNumber", "RequiredPressure", "Pressure", "Flow", "TotalFlow"}
