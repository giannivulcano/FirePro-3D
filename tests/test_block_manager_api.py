"""Model_Space block-management API (Block system S4)."""
from firepro3d.block_definition import BlockDefinition


def _def(name="A", library="L", series="S"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_instance_count_and_signal(model_space):
    d = _def()
    model_space.register_block_definition(d)
    fired = []
    model_space.blockInstancesChanged.connect(lambda: fired.append(1))

    assert model_space.instance_count(d.id) == 0
    a = model_space.place_block_instance(d.id, (0.0, 0.0))
    assert model_space.instance_count(d.id) == 1
    model_space.place_block_instance(d.id, (50.0, 0.0))
    assert model_space.instance_count(d.id) == 2
    model_space.remove_block_instance(a)
    assert model_space.instance_count(d.id) == 1
    # signal fired on each place (2) and each remove (1)
    assert len(fired) == 3
