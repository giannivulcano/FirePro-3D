"""Guard tests for BlockInstance (Block system S1)."""
from PyQt6.QtGui import QPainterPath
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance


def _def():
    return BlockDefinition.new(name="A", library="L", series="S",
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_instance_resolves_shared_render_ops(qapp):
    d = _def()
    reg = {d.id: d}
    a = BlockInstance(block_id=d.id, resolver=reg.get)
    b = BlockInstance(block_id=d.id, resolver=reg.get)
    # PERF GATE: both instances share ONE render-op object (no per-instance copy)
    assert a.render_ops() is b.render_ops()
    assert a.render_ops() is d.render_ops()


def test_bounding_rect_reflects_definition(qapp):
    d = _def()
    inst = BlockInstance(block_id=d.id, resolver={d.id: d}.get)
    assert abs(inst.boundingRect().width() - 100.0) < 5.0  # + pen margin


def test_to_dict_from_dict_round_trip(qapp):
    d = _def()
    reg = {d.id: d}
    inst = BlockInstance(block_id=d.id, resolver=reg.get)
    inst.setPos(30.0, 40.0)
    inst.set_block_rotation(90.0)
    inst.level = "Level 2"
    data = inst.to_dict()
    assert data == {"type": "block_instance", "block_id": d.id,
                    "pos": [30.0, 40.0], "rotation": 90.0,
                    "level": "Level 2", "attributes": {}}
    inst2 = BlockInstance.from_dict(data, resolver=reg.get)
    assert inst2.block_id == d.id
    assert (inst2.pos().x(), inst2.pos().y()) == (30.0, 40.0)
    assert inst2.block_rotation() == 90.0
    assert inst2.level == "Level 2"


def test_missing_definition_does_not_crash(qapp):
    inst = BlockInstance(block_id="deadbeef", resolver={}.get)
    assert inst.render_ops() == []
    _ = inst.boundingRect()  # must not raise
