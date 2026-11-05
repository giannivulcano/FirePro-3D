"""Layer Height / Opaque / Constraint Points controls (D6, D7, D10)."""
import pytest

from firepro3d.block_instance import BlockInstance
from firepro3d.model_space import Model_Space
from tests._block_stack_helpers import rect_def


@pytest.fixture
def be(qapp):
    s = Model_Space(scene_role="block_editor")
    yield s
    s.cleanup()


def _three(be):
    d = rect_def(be)
    return [be.place_block_instance(d.id, (0.0, 0.0)) for _ in range(3)]


def _act(sc, target, text):
    menu = sc._build_entity_context_menu(target)
    acts = [a for a in menu.actions() if a.text() == text]
    assert acts, [a.text() for a in menu.actions()]
    acts[0].trigger()


def test_editor_rows(be):
    p = be.place_block_instance(rect_def(be).id, (0.0, 0.0)).get_properties()
    assert p["Layer Height"]["type"] == "number"
    assert (p["Layer Height"]["minimum"], p["Layer Height"]["maximum"]) == (-1000, 1000)
    assert p["Opaque"]["type"] == "bool"
    assert p["Constraint Points"]["value"] is True


def test_plan_shows_constraint_points_only(qapp):
    sc = Model_Space()
    p = sc.place_block_instance(rect_def(sc).id, (0.0, 0.0)).get_properties()
    assert "Layer Height" not in p and "Opaque" not in p
    assert "Constraint Points" in p
    sc.cleanup()


def test_rows_write_and_each_commit_is_one_undo_step(be):
    i = be.place_block_instance(rect_def(be).id, (0.0, 0.0))
    be.push_undo_state()
    n = be._undo_pos
    with be.deferred_undo_push():
        i.set_property("Layer Height", 4)
    assert i.layer_height == 4 and be._undo_pos == n + 1
    with be.deferred_undo_push():
        i.set_property("Layer Height", 4)
    assert be._undo_pos == n + 1                # a no-op commit is silent
    with be.deferred_undo_push():
        i.set_property("Opaque", True)
    assert i.is_opaque() and be._undo_pos == n + 2
    with be.deferred_undo_push():
        i.set_property("Constraint Points", False)
    assert i.constraint_points_off and be._undo_pos == n + 3


def test_undo_restores_the_values(be):
    i = be.place_block_instance(rect_def(be).id, (0.0, 0.0))
    be.push_undo_state()
    with be.deferred_undo_push():
        i.set_property("Layer Height", 4)
    be.undo()
    assert be._block_instances[0].layer_height == 0
    be.redo()
    b = be._block_instances[0]
    assert b.layer_height == 4 and b.zValue() != 0


def test_bring_to_front_is_one_above_the_highest(be):
    a, b, c = _three(be)
    b.set_layer_height(7)
    be.push_undo_state()
    n = be._undo_pos
    _act(be, a, "Bring to Front")
    assert a.layer_height == 8 and be._undo_pos == n + 1


def test_send_to_back_is_one_below_the_lowest(be):
    a, b, c = _three(be)
    b.set_layer_height(-3)
    _act(be, a, "Send to Back")
    assert a.layer_height == -4


def test_multi_selection_keeps_relative_order(be):
    a, b, c = _three(be)
    a.set_layer_height(5)
    b.set_layer_height(1)
    c.set_layer_height(9)
    a.setSelected(True)
    b.setSelected(True)
    _act(be, a, "Bring to Front")
    assert (b.layer_height, a.layer_height) == (10, 11)
    _act(be, a, "Send to Back")
    assert (a.layer_height, b.layer_height) == (8, 7)


def test_the_limit_clamps(be):
    a, b, c = _three(be)
    b.set_layer_height(1000)
    _act(be, a, "Bring to Front")
    assert a.layer_height == 1000


def test_plan_has_no_stack_actions(qapp):
    sc = Model_Space()
    i = sc.place_block_instance(rect_def(sc).id, (0.0, 0.0))
    menu = sc._build_entity_context_menu(i)       # held: Qt frees the actions with it
    texts = [a.text() for a in menu.actions()]
    assert "Bring to Front" not in texts and "Send to Back" not in texts
    sc.cleanup()
