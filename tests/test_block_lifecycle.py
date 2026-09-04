"""Registry, serialization, undo, and retirement guard tests (Block system S1)."""
import pytest
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance


def _def(name="A"):
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_register_and_place(model_space):
    d = _def()
    model_space.register_block_definition(d)
    assert model_space.get_block_definition(d.id) is d
    inst = model_space.place_block_instance(d.id, (10.0, 20.0), rotation=0.0)
    assert inst in model_space._block_instances
    assert inst.scene() is model_space


def test_definition_edit_propagates_to_instances(model_space):
    d = _def()
    model_space.register_block_definition(d)
    a = model_space.place_block_instance(d.id, (0.0, 0.0))
    b = model_space.place_block_instance(d.id, (50.0, 0.0))
    w_before = a.boundingRect().width()
    d.set_primitives([{"type": "draw_line", "pt1": [0, 0], "pt2": [300, 0],
                       "color": "#ffffff", "lineweight": 1.0}])
    assert a.boundingRect().width() > w_before
    assert abs(a.boundingRect().width() - b.boundingRect().width()) < 1e-6
