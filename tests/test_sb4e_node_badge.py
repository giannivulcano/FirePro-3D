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


def _badges(nodes):
    return {n: n._hydraulic_badge for n in nodes if n._hydraulic_badge is not None}


def test_g2_no_badge_before_a_solve(tree):
    _ms, nodes = tree
    assert _badges(nodes) == {}


def test_g1_numbered_nodes_carry_a_bound_badge_and_clear_removes_all(tree):
    from firepro3d.bound_label import BoundLabelItem
    from firepro3d.constants import Z_ANNOT_TAG
    ms, nodes = tree
    r = solve(ms)
    numbered = {n for n in nodes if str(r.node_labels.get(n, "")).isdigit()}
    assert numbered                                     # T1 probe set
    b = _badges(nodes)
    assert set(b) == numbered
    for n, badge in b.items():
        assert isinstance(badge, BoundLabelItem)
        assert badge.parentItem() is None and badge.scene() is ms
        assert badge.zValue() == Z_ANNOT_TAG
        hv = badge.host_values({"NodeNumber"})
        assert hv["NodeNumber"].raw == r.node_labels[n]
        assert badge.paints()                            # resolved seed, non-blank
    ms.clear_hydraulics()
    assert _badges(nodes) == {}
    assert not [i for i in ms.items() if type(i).__name__ == "HydraulicNodeBadge"]


def test_g6_stack_follows_the_top_node(tree):
    from firepro3d.constants import HYD_BADGE_OFFSET_MM, HYD_BADGE_STACK_STEP_MM
    ms, nodes = tree
    n4, n5 = nodes[4], nodes[5]
    # n4 becomes a tee so BOTH drop nodes are numbered (T1 probe: n4 alone is lettered)
    n6 = ms.add_node(9000.0, 3000.0)
    ms.add_pipe(n4, n6)
    ms.add_sprinkler(n6)
    n5.ceiling_offset = n4.ceiling_offset - 1000.0      # a pipe add may reset it
    n5._recompute_z_pos()
    solve(ms)
    assert n4._hydraulic_badge is not None and n5._hydraulic_badge is not None
    assert n4.z_pos > n5.z_pos
    n4.set_property("Badge Position", "Below")        # n4 is the higher node
    k = ms.scale_manager.drawing_scale
    b4, b5 = n4._hydraulic_badge.pos(), n5._hydraulic_badge.pos()
    np_ = n4.scenePos()
    assert b4.y() == pytest.approx(np_.y() + HYD_BADGE_OFFSET_MM * k)
    assert b5.y() == pytest.approx(b4.y())                       # one row ...
    assert abs(b4.x() - b5.x()) == pytest.approx(HYD_BADGE_STACK_STEP_MM * k)  # ... side by side
    assert (b4.x() + b5.x()) / 2 == pytest.approx(np_.x())      # centred on the node


def test_g3_fixed_position_survives_resolve_and_save_load(tree):
    from firepro3d.hydraulic_node_badge import best_position_for_node
    ms, nodes = tree
    solve(ms)
    n = nodes[2]                                    # a numbered sprinkler node (T1)
    n.set_property("Badge Position", "Below")
    solve(ms)
    assert n._hydraulic_badge.side == "Below"
    assert n._hydraulic_badge.pos().y() > n.scenePos().y()
    from firepro3d.network_codec import deserialize_node, serialize_node
    e = serialize_node(n, {n: 0})
    assert e["badge_position"] == "Below"
    assert not {"Badge Position", "Node Number", "Required P", "Actual P",
                "Flow Out q", "Total Flow Q"} & set(e["sprinkler"] or {})
    e2 = dict(e); e2.pop("badge_position")
    m = deserialize_node(ms, e2)                     # an old file: no key
    assert m.badge_position == "Auto"
    assert "badge_position" not in serialize_node(m, {m: 0})   # sparse
    assert deserialize_node(ms, e).badge_position == "Below"
    n.set_property("Badge Position", "Auto")
    solve(ms)
    assert n._hydraulic_badge.side == best_position_for_node(n)


def test_s1_rows_show_only_on_a_badged_node(tree):
    ms, nodes = tree
    for n in nodes:
        assert "Badge Position" not in n.get_properties()
    r = solve(ms)
    n = nodes[2]
    props = n.sprinkler.get_properties()            # the panel targets the sprinkler
    assert props["Badge Position"]["value"] == "Auto"
    assert props["Node Number"]["value"] == r.node_labels[n]
    assert props["Actual P"]["value"] == ep.host_values(n)["Pressure"].text


def test_g5_panel_commit_pushes_undo_and_marks_modified(qapp, tree):
    from firepro3d.property_manager import PropertyManager
    ms, nodes = tree
    solve(ms)
    n = nodes[2]
    ms.push_undo_state()
    ms._dirty = False
    before = len(ms._undo_stack)
    pm = PropertyManager()
    try:
        pm.show_properties(n)                       # resolves to the sprinkler (panel rule)
        pm._apply_property("Badge Position", "Left")
        assert n.badge_position == "Left"
        assert len(ms._undo_stack) == before + 1
        assert ms._dirty is True
    finally:
        pm._refresh_timer.stop()                    # tests own teardown (panel timer crash)
        pm.deleteLater()
