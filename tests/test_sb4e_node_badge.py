"""SB4e guards (.todo/sb4e-phase2.md G1-G10)."""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt

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


def test_pipe_panel_node_sections_hide_the_hydraulic_rows(qapp, tree):
    from firepro3d.node import HYDRAULIC_ROW_KEYS
    from firepro3d.property_manager import PropertyManager
    ms, nodes = tree
    solve(ms)
    pipe = next(p for p in ms.sprinkler_system.pipes
                if p.node1._hydraulic_badge is not None
                and p.node2._hydraulic_badge is not None)
    assert "Badge Position" in pipe.node1.get_properties()      # the node itself has them
    pm = PropertyManager()
    try:
        pm.show_properties(pipe)
        labels = []
        for i in range(pm._form.rowCount()):
            item = pm._form.itemAt(i, pm._form.ItemRole.LabelRole)
            w = item.widget() if item is not None else None
            if w is not None and hasattr(w, "text"):
                labels.append(w.text())
        assert "NODE 1" in labels and "NODE 2" in labels
        shown = {"Badge Position", "Node Number", "Required P", "Actual P",
                 "Flow Out q", "Total Flow Q"}
        assert not shown & set(labels)
        assert HYDRAULIC_ROW_KEYS == shown
        assert labels.count("Offset") >= 2 and labels.count("Absolute Elev.") == 2
    finally:
        pm._refresh_timer.stop()                    # tests own teardown (panel timer crash)
        pm.deleteLater()


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


def test_g4_click_on_the_badge_selects_the_node(qapp, shown_model_view, real_system_library):
    from firepro3d import paper_display as pd
    from firepro3d.water_supply import WaterSupply
    from tests._snap_polish_helpers import click, move
    view, ms = shown_model_view
    ws = WaterSupply(0.0, 0.0)
    ms.addItem(ws)
    ms.water_supply_node = ws
    ms.sprinkler_system.supply_node = ws
    a = ms.add_node(0.0, 0.0)
    b = ms.add_node(1500.0, 0.0)
    ms.add_pipe(a, b)
    ms.add_sprinkler(b)
    solve(ms)
    n = next(x for x in (a, b) if x._hydraulic_badge is not None)
    badge = n._hydraulic_badge
    ms.set_mode("select")
    view.centerOn(badge.sceneBoundingRect().center())
    qapp.processEvents()
    hit = badge.sceneBoundingRect().center()
    # precondition: the click lands on the badge only, not on the node's marker
    dt = view.viewportTransform()
    under = ms.items(hit, Qt.ItemSelectionMode.IntersectsItemShape,
                     Qt.SortOrder.DescendingOrder, dt)
    assert badge in under and n not in under
    assert not n.isSelected()
    move(view, hit)                      # hover first: a select click commits the HALO pick
    qapp.processEvents()
    assert ms.halo_item() is n
    click(view, hit)
    qapp.processEvents()
    assert n.isSelected() and not badge.isSelected()
    assert ms.selectedItems() == [n]
    assert badge.overlay_pens()                               # ring on screen
    orig = pd.paper_pass_active
    pd.paper_pass_active = lambda: True
    try:
        assert badge.overlay_pens() == []                     # never plots
    finally:
        pd.paper_pass_active = orig


def test_g4_click_without_a_hover_selects_the_node(qapp, shown_model_view, real_system_library):
    """No HALO pick (no move first, or Esc cleared it): the press path itself
    resolves the badge to its node (review T6 I1)."""
    from firepro3d.water_supply import WaterSupply
    from tests._snap_polish_helpers import click
    view, ms = shown_model_view
    ws = WaterSupply(0.0, 0.0)
    ms.addItem(ws)
    ms.water_supply_node = ws
    ms.sprinkler_system.supply_node = ws
    a = ms.add_node(0.0, 0.0)
    b = ms.add_node(1500.0, 0.0)
    ms.add_pipe(a, b)
    ms.add_sprinkler(b)
    solve(ms)
    n = next(x for x in (a, b) if x._hydraulic_badge is not None)
    badge = n._hydraulic_badge
    ms.set_mode("select")
    view.centerOn(badge.sceneBoundingRect().center())
    qapp.processEvents()
    hit = badge.sceneBoundingRect().center()
    ms.halo_clear()
    assert ms.halo_item() is None
    click(view, hit)
    qapp.processEvents()
    assert ms.selectedItems() == [n]


def test_placement_mode_click_on_a_badge_acts_on_the_pipe_under_it(
        qapp, shown_model_view, real_system_library):
    """T6 ruling: only Select mode resolves a badge to its node; sprinkler
    placement on a badge over a pipe splits the pipe, as before SB4e."""
    from firepro3d.water_supply import WaterSupply
    from tests._snap_polish_helpers import click
    view, ms = shown_model_view
    ws = WaterSupply(0.0, 0.0)
    ms.addItem(ws)
    ms.water_supply_node = ws
    ms.sprinkler_system.supply_node = ws
    a = ms.add_node(0.0, 0.0)
    b = ms.add_node(3000.0, 0.0)
    pipe = ms.add_pipe(a, b)
    ms.add_sprinkler(b)
    solve(ms)
    n = b if b._hydraulic_badge is not None else a
    n.set_property("Badge Position", "Left" if n is b else "Right")
    solve(ms)
    badge = n._hydraulic_badge
    view.centerOn(badge.sceneBoundingRect().center())
    qapp.processEvents()
    hit = badge.sceneBoundingRect().center()
    assert 0.0 < hit.x() < 3000.0 and abs(hit.y()) < 1.0      # badge sits over the pipe
    assert pipe in ms.items(hit)
    before = len(ms.sprinkler_system.nodes)
    ms.set_mode("sprinkler")
    click(view, hit)
    qapp.processEvents()
    assert len(ms.sprinkler_system.nodes) == before + 1       # the pipe was split
