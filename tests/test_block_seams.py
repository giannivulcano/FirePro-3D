"""Seam-fix guard tests: movability, copy/paste, orphan placeholder (Block S2 T1)."""
import json
import pytest
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance


def _def(name="A"):
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_instance_translate_moves_by_delta(qapp):
    d = _def()
    inst = BlockInstance(block_id=d.id, resolver={d.id: d}.get)
    inst.set_block_pos(10.0, 20.0)
    inst.translate(5.0, -3.0)
    assert inst.block_pos() == (15.0, 17.0)


def test_instance_movable_capability(qapp):
    from firepro3d.selection_manipulator import item_capabilities
    d = _def()
    inst = BlockInstance(block_id=d.id, resolver={d.id: d}.get)
    assert "translate" in item_capabilities(inst)


def test_to_dict_has_type_key(qapp):
    d = _def()
    inst = BlockInstance(block_id=d.id, resolver={d.id: d}.get)
    assert inst.to_dict()["type"] == "block_instance"


def test_copy_paste_round_trips_a_block(model_space):
    d = _def()
    model_space.register_block_definition(d)
    model_space.place_block_instance(d.id, (10.0, 20.0), rotation=30.0)
    model_space._block_instances[0].setSelected(True)
    model_space.copy_selected_items()
    from PyQt6.QtCore import QPointF
    model_space.paste_items(QPointF(5.0, 5.0))
    assert len(model_space._block_instances) == 2
    pasted = model_space._block_instances[1]
    assert pasted.block_pos() == (15.0, 25.0)
    assert pasted.block_rotation() == 30.0


def test_orphan_instance_has_visible_placeholder(qapp):
    inst = BlockInstance(block_id="deadbeef", resolver={}.get)
    assert inst.render_ops() == []
    assert not inst.boundingRect().isEmpty()   # placeholder gives real bounds
