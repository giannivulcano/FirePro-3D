"""PH1 AC12 (D-PH16): copies keep the source's phase; pasted / duplicated /
arrayed pipes keep the source pipe's properties; water supply pastes.

Raw sources: D-PH16 + ruling 2026-11-11 ("PH1 makes pasted, duplicated and
arrayed pipes keep the source pipe's properties (phase included) and adds
water supply to paste"); todo_open P2 "Pasted pipes lose all their properties
(Diameter, Material, Show Label, Tag, display overrides)"; element-parameters
Marks: a copy never keeps the source Mark. Pipe option strings from
pipe.py Pipe.__init__ (Material "PVC", Show Label "False").
"""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import marks
from tests._ph1_helpers import (  # noqa: F401
    _MADE, add_block, add_opening, add_water_supply, block_definition,
    ph1_cleanup, scene)


def _network(ms):
    a, b = ms.add_node(0.0, 0.0), ms.add_node(1000.0, 0.0)
    p = ms.add_pipe(a, b)
    p.set_property("Diameter", p._properties["Diameter"]["options"][4])   # 2" (option index 4)
    p.set_property("Material", "PVC")
    p.set_property("Show Label", "False")
    p._display_overrides = {"color": "#00ff00"}
    p.phase = "existing"
    sp = ms.add_sprinkler(b)
    sp.phase = "demolition"
    a.fitting.phase_override = "new"
    return a, b, p


def _copies(ms, src):
    return [q for q in ms.sprinkler_system.pipes if q is not src]


def _assert_copy(src, cp):
    keep = {k: v["value"] for k, v in src._properties.items() if k != "Mark"}
    assert {k: v["value"] for k, v in cp._properties.items() if k != "Mark"} == keep
    assert cp._display_overrides == {"color": "#00ff00"}
    assert cp.phase == "existing"
    assert marks.get_mark(cp) != marks.get_mark(src)                 # a copy mints


def _assert_copied_override(cp):
    """The copy of node a (x == 0) keeps a's fitting override.

    Both record orders matter: when b's record pastes first, its pipe creates
    a's copy as a far-end node, and a's own record then lands on that node
    (find_nearby_node). Selection order follows selectedItems(), which is not
    stable across processes, so each guard pins it (_ORDERS).
    """
    new_a = cp.node1 if cp.node1.scenePos().x() == 0.0 else cp.node2
    assert new_a.scenePos().x() == 0.0
    assert new_a.fitting.phase_override == "new"


_ORDERS = pytest.mark.parametrize("order", ["ab", "ba"])


def _pick(a, b, order):
    return [a, b] if order == "ab" else [b, a]


@_ORDERS
def test_duplicate_keeps_pipe_properties_phase_head_and_override(qapp, order):
    ms = scene()
    a, b, p = _network(ms)
    ms.clearSelection(); a.setSelected(True); b.setSelected(True)
    ms._selected_items = _pick(a, b, order)               # commit_duplicate reads this first
    ms._modify_ctl.commit_duplicate(QPointF(0.0, 3000.0))
    (cp,) = _copies(ms, p)                                            # exactly one new pipe
    _assert_copy(p, cp)
    heads = [s for s in ms.sprinkler_system.sprinklers if s is not b.sprinkler]
    assert [s.phase for s in heads] == ["demolition"]
    _assert_copied_override(cp)


@_ORDERS
def test_copy_paste_keeps_pipe_properties(qapp, order):
    ms = scene()
    a, b, p = _network(ms)
    ms.clearSelection(); a.setSelected(True); b.setSelected(True)
    ctl = ms._modify_ctl
    assert ctl.write_clipboard(_pick(a, b, order), QPointF(0.0, 0.0))
    assert ctl.begin_paste()
    ctl.commit_paste(QPointF(0.0, 4000.0))
    (cp,) = _copies(ms, p)
    _assert_copy(p, cp)
    assert [s.phase for s in ms.sprinkler_system.sprinklers if s is not b.sprinkler] \
        == ["demolition"]
    _assert_copied_override(cp)


@_ORDERS
def test_array_keeps_pipe_properties(qapp, order):
    ms = scene()
    a, b, p = _network(ms)
    ms._array_variant = "linear"
    ms._array_dir = QPointF(0.0, 1.0)
    ms._selected_items = _pick(a, b, order)
    assert ms._modify_ctl.commit_array({"count": 2, "spacing": 3000.0})
    (cp,) = _copies(ms, p)
    _assert_copy(p, cp)
    assert [s.phase for s in ms.sprinkler_system.sprinklers if s is not b.sprinkler] \
        == ["demolition"]
    _assert_copied_override(cp)


def test_a_paste_onto_a_network_node_leaves_its_override(qapp):
    """A record landing on a node that was in the network before the paste
    (find_nearby_node) never mutates it, override included."""
    ms = scene()
    a, b, p = _network(ms)
    records = ms._clipboard_item_dicts([a])                # a's record carries "new"
    a.fitting.phase_override = "existing"
    ms.paste_items(QPointF(0.0, 0.0), data=records)        # lands on a itself
    assert a.fitting.phase_override == "existing"


def test_pasted_wall_and_opening_keep_their_phases(qapp):
    ms = scene()
    op = add_opening(ms)
    op._wall.phase, op.phase = "demolition", "existing"
    ms.clearSelection(); op._wall.setSelected(True)
    ms._modify_ctl.commit_duplicate(QPointF(0.0, 5000.0))
    w2 = ms._walls[1]
    assert (w2.phase, w2.openings[0].phase) == ("demolition", "existing")


ONE_WS = "A project has one water supply"     # ruling R5 2026-11-11, verbatim


def _status(ms):
    """Record what the scene posts to the status bar (ModifyHostMixin._show_status)."""
    seen = []
    ms._show_status = lambda message, *a, **k: seen.append(message)
    return seen


def _water_supplies(ms):
    from firepro3d.water_supply import WaterSupply
    return [i for i in ms.items() if isinstance(i, WaterSupply)]


def test_water_supply_paste_is_refused_while_one_exists(qapp):
    """R5: nothing changes; the status bar says why."""
    ms = scene()
    ws = add_water_supply(ms)
    ms.push_undo_state()
    pos, seen = ms._undo_pos, _status(ms)
    ctl = ms._modify_ctl
    assert ctl.write_clipboard([ws], ws.pos())
    assert ctl.begin_paste() is False
    assert ONE_WS in seen
    assert _water_supplies(ms) == [ws] and ms.water_supply_node is ws and ms._undo_pos == pos


def test_water_supply_duplicate_is_refused_while_one_exists(qapp):
    ms = scene()
    ws = add_water_supply(ms)
    ms.push_undo_state()
    pos, seen = ms._undo_pos, _status(ms)
    ms.clearSelection(); ws.setSelected(True)
    ms._modify_ctl.commit_duplicate(QPointF(2000.0, 0.0))
    assert ONE_WS in seen
    assert _water_supplies(ms) == [ws] and ms._undo_pos == pos


def test_a_cut_water_supply_pastes_back_with_its_properties_and_phase(qapp):
    """R5, none present: the paste creates it with its properties and phase."""
    ms = scene()
    ws = add_water_supply(ms)
    ws.set_property("Static Pressure", "95")
    ws.phase = "existing"
    ms.push_undo_state()
    ctl = ms._modify_ctl
    ms._copy_is_cut = True
    ms._selected_items = [ws]
    ctl.press_copy_base(None, ws.pos(), ws.pos())        # the real Cut: copy + delete, one step
    assert ms.water_supply_node is None and _water_supplies(ms) == []
    assert ctl.begin_paste()
    ctl.commit_paste(QPointF(2000.0, 0.0))
    new = ms.water_supply_node
    assert new is not None and _water_supplies(ms) == [new]
    assert (new.pos().x(), new.pos().y()) == (2200.0, 200.0)
    assert new._properties["Static Pressure"]["value"] == "95" and new.phase == "existing"
    assert ms.sprinkler_system.supply_node is new


# -- held from the Task 3 review ---------------------------------------------------
def test_a_block_editor_instance_has_no_phase_row(qapp):
    from firepro3d.model_space import Model_Space
    ms = Model_Space(scene_role="block_editor")
    _MADE.append(ms)                                     # ph1_cleanup ends it
    inst = ms.place_block_instance(block_definition(ms).id, (0.0, 0.0))
    assert inst is not None and inst.scene() is ms
    assert "Phase" not in inst.get_properties()
    inst.set_property("Phase", "Existing")
    assert inst.phase == "new"


def test_a_pasted_and_a_duplicated_block_keep_the_source_phase(qapp):
    ms = scene()
    src = add_block(ms)
    src.phase = "demolition"
    records = ms._clipboard_item_dicts([src])
    (pasted,) = ms.paste_items(QPointF(500.0, 0.0), data=records)
    assert pasted is not src and pasted.phase == "demolition"
    ms.clearSelection(); src.setSelected(True)
    before = list(ms._block_instances)
    ms._modify_ctl.commit_duplicate(QPointF(0.0, 800.0))
    (dup,) = [b for b in ms._block_instances if b not in before]
    assert dup.phase == "demolition"


# -- Phase 6 held minors -------------------------------------------------------------
def test_a_mixed_paste_with_a_supply_present_refuses_only_the_supply(qapp):
    """T8-M3: [water supply, node] with a supply present -> the supply is skipped,
    the node pastes with its head phase, and the status keeps the R5 reason."""
    ms = scene()
    ws = add_water_supply(ms)
    a, b, _p = _network(ms)
    records = ms._clipboard_item_dicts([ws, b])
    seen = _status(ms)
    new = ms.paste_items(QPointF(0.0, 3000.0), data=records)
    assert _water_supplies(ms) == [ws]
    assert len(new) == 1 and new[0].sprinkler.phase == "demolition"
    assert ONE_WS in seen[-1]


def test_a_level_copy_of_a_water_supply_says_why_it_was_refused(qapp):
    """VC9 unconfirmed: copy_items_to_level reaches paste_items; the R5 refusal is
    not silent there."""
    ms = scene()
    ws = add_water_supply(ms)
    seen = _status(ms)
    ms.copy_items_to_level([ws], ms.active_level)
    assert _water_supplies(ms) == [ws]
    assert any(ONE_WS in m for m in seen)
