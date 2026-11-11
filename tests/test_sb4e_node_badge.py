"""SB4e guards (.todo/sb4e-phase2.md G1-G10)."""
import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import element_params as ep
from tests._sb4e_helpers import dispose, solve, tree_scene


@pytest.fixture
def tree(qapp, real_system_library):    # the shipped System tier holds the seed
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


def test_ac2_seed_resolves_as_the_hydraulic_node_default(tree):
    from firepro3d.annotative import is_annotative
    from firepro3d.system_blocks import ANNOTATION_CATEGORIES, LABEL_FIELD, PAINT_WHEN_BLANK, SYSTEM_DEFAULTS
    ms, _nodes = tree
    assert "Hydraulic Node" in ANNOTATION_CATEGORIES
    assert LABEL_FIELD["Hydraulic Node"] == "NodeNumber"
    assert "Hydraulic Node" not in PAINT_WHEN_BLANK
    assert SYSTEM_DEFAULTS["Hydraulic Node"] == "system-tags-hydraulicnode"
    d = ms.annotation_block("Hydraulic Node", None)
    assert d is not None and d.id == "system-tags-hydraulicnode"
    assert d.host_category == "Hydraulic Node" and is_annotative(d)
    assert [a.get("host_key") for a in d.effective_attributes()
            if a.get("source") == "host"] == ["NodeNumber"]
    assert set(ep.PARAMS["Hydraulic Node"]) == {
        "NodeNumber", "RequiredPressure", "Pressure", "Flow", "TotalFlow"}
