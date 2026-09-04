"""place_block mode state machine (Block S2 T3)."""
from PyQt6.QtCore import QPointF
from firepro3d.block_definition import BlockDefinition


def _def(ms, name="A"):
    d = BlockDefinition.new(name=name, library="L", series="S",
                            primitives=[{"type": "draw_line", "pt1": [0, 0],
                                         "pt2": [100, 0], "color": "#ffffff",
                                         "lineweight": 1.0}], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    return d


def test_place_block_mode_two_step_commits_instance(model_space):
    d = _def(model_space)
    model_space.set_mode("place_block", template=d.id)
    assert model_space._place_block_id == d.id
    model_space._place_block_set_position(QPointF(50.0, 60.0))
    assert model_space._place_block_step == 1
    assert model_space._place_block_ghost is not None
    model_space._place_block_commit(90.0)
    assert len(model_space._block_instances) == 1
    inst = model_space._block_instances[0]
    assert (inst.pos().x(), inst.pos().y()) == (50.0, 60.0)
    assert inst.block_rotation() == 90.0
    assert model_space.mode == "place_block"
    assert model_space._place_block_step == 0


def test_place_block_exit_clears_ghost(model_space):
    d = _def(model_space)
    model_space.set_mode("place_block", template=d.id)
    model_space._place_block_set_position(QPointF(0.0, 0.0))
    assert model_space._place_block_ghost is not None
    model_space.set_mode(None)
    assert model_space._place_block_ghost is None
    assert model_space._place_block_id is None
