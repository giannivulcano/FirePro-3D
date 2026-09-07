"""Tests for Model_Space.commit_block_definition (Block Editor BE1).

Task 3: new-definition path.
Task 4: edit-in-place propagation guard.
"""
from PyQt6.QtCore import QPointF
from firepro3d.model_space import Model_Space
from firepro3d.construction_geometry import LineItem


def _line_dicts():
    a = LineItem(QPointF(0, 0), QPointF(100, 0))
    b = LineItem(QPointF(100, 0), QPointF(100, 50))
    return [a.to_dict(), b.to_dict()]


# ── Task 3: new-definition path ──────────────────────────────────────────────

def test_commit_new_registers_and_places_one_undo(qapp):
    scene = Model_Space()
    n_undo = len(scene._undo_stack)
    defn = scene.commit_block_definition(
        block_id=None, name="Corner", library="Lib", series="Ser",
        primitives=_line_dicts(), origin=(0.0, 0.0), place_instance=True)
    assert defn is not None and defn.id in scene._block_definitions
    assert defn.version == 1
    assert scene.instance_count(defn.id) == 1
    assert len(scene._undo_stack) == n_undo + 1


def test_commit_empty_primitives_returns_none(qapp):
    scene = Model_Space()
    assert scene.commit_block_definition(
        block_id=None, name="X", library="L", series="S",
        primitives=[], origin=(0.0, 0.0)) is None


# ── Task 4: edit-in-place propagation guard ──────────────────────────────────

def test_commit_edit_bumps_version_and_repaints_all_instances(qapp):
    scene = Model_Space()
    defn = scene.commit_block_definition(
        block_id=None, name="Sym", library="L", series="S",
        primitives=_line_dicts(), origin=(0.0, 0.0), place_instance=True)
    scene.place_block_instance(defn.id, (200.0, 0.0))
    insts = [i for i in scene._block_instances if i.block_id == defn.id]
    assert len(insts) == 2
    calls = {"n": 0}
    for i in insts:
        orig = i.on_definition_changed
        i.on_definition_changed = lambda _o=orig: (calls.__setitem__("n", calls["n"] + 1), _o())[1]
    new_prims = _line_dicts() + _line_dicts()
    ret = scene.commit_block_definition(
        block_id=defn.id, name="Sym2", library="L2", series="S2",
        primitives=new_prims, origin=(1.0, 2.0), place_instance=False)
    assert ret is defn
    assert defn.version == 2
    assert (defn.name, defn.library, defn.series) == ("Sym2", "L2", "S2")
    assert defn.origin == (1.0, 2.0)
    assert calls["n"] == 2


def test_commit_edit_missing_id_returns_none(qapp):
    scene = Model_Space()
    assert scene.commit_block_definition(
        block_id="nope", name="X", library="L", series="S",
        primitives=_line_dicts(), origin=(0.0, 0.0)) is None


# ── Fix BE1: partial-mutation guard (source_items after all guards) ──────────

def test_commit_missing_id_does_not_delete_source_items(qapp):
    scene = Model_Space()
    src = LineItem(QPointF(0, 0), QPointF(10, 0))
    scene.addItem(src)
    scene._draw_lines.append(src)
    n_undo = len(scene._undo_stack)
    ret = scene.commit_block_definition(
        block_id="nope", name="X", library="L", series="S",
        primitives=_line_dicts(), origin=(0.0, 0.0), source_items=[src])
    assert ret is None
    assert src in scene._draw_lines          # NOT deleted on the failed guard
    assert len(scene._undo_stack) == n_undo   # no undo pushed


def test_commit_new_place_instance_false_registers_without_instance(qapp):
    scene = Model_Space()
    defn = scene.commit_block_definition(
        block_id=None, name="NoInst", library="L", series="S",
        primitives=_line_dicts(), origin=(0.0, 0.0), place_instance=False)
    assert defn is not None and defn.id in scene._block_definitions
    assert scene.instance_count(defn.id) == 0
