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
    inst.set_block_pos(30.0, 40.0)
    inst.set_block_rotation(90.0)
    inst.level = "Level 2"
    data = inst.to_dict()
    assert data == {"type": "block_instance", "block_id": d.id,
                    "pos": [30.0, 40.0], "rotation": 90.0,
                    "level": "Level 2", "attributes": {}, "uid": inst._uid}
    inst2 = BlockInstance.from_dict(data, resolver=reg.get)
    assert inst2.block_id == d.id
    assert inst2._uid == inst._uid
    assert inst2.block_pos() == (30.0, 40.0)
    assert inst2.block_rotation() == 90.0
    assert inst2.level == "Level 2"


def test_missing_definition_does_not_crash(qapp):
    inst = BlockInstance(block_id="deadbeef", resolver={}.get)
    assert inst.render_ops() == []
    _ = inst.boundingRect()  # must not raise


def test_posed_path_memo_tracks_pose_content_and_nesting(qapp):
    """The memoised posed path never serves stale geometry: pose edits,
    definition edits and nested-child edits all show; shape() mutation is safe."""
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    sc = Model_Space()
    child = BlockDefinition.new(name="C", library="L", series="S", origin=(0.0, 0.0),
                                primitives=[LineItem(QPointF(0, 0), QPointF(50, 0)).to_dict()])
    sc.register_block_definition(child)
    d = BlockDefinition.new(name="P", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(),
                                        {"type": "block_instance", "block_id": child.id,
                                         "pos": [0.0, 500.0], "rotation": 0.0}])
    sc.register_block_definition(d)
    inst = sc.place_block_instance(d.id, (0.0, 0.0))
    r0 = inst.geometric_rect()
    assert (r0.width(), r0.height()) == (100.0, 500.0)
    inst.translate(10.0, 20.0)                              # pose
    assert inst.geometric_rect() == r0.translated(10.0, 20.0)
    inst.set_block_rotation(90.0)
    r1 = inst.geometric_rect()
    assert abs(r1.width() - 500.0) < 1e-6 and abs(r1.height() - 100.0) < 1e-6
    inst.set_block_rotation(0.0)
    d.set_primitives([LineItem(QPointF(0, 0), QPointF(300, 0)).to_dict()])   # content
    assert inst.geometric_rect().width() == 300.0
    child.set_primitives([LineItem(QPointF(0, 0), QPointF(700, 0)).to_dict()])
    sc.block_registry.invalidate(child.id)                  # nested-child edit
    d.set_primitives(d.primitives + [{"type": "block_instance", "block_id": child.id,
                                      "pos": [0.0, 500.0], "rotation": 0.0}])
    assert inst.geometric_rect().width() == 700.0
    child.set_primitives([LineItem(QPointF(0, 0), QPointF(800, 0)).to_dict()])
    sc.block_registry.invalidate(child.id)                  # parent ops dropped, version kept
    assert inst.geometric_rect().width() == 800.0
    shp = inst.shape()
    shp.translate(1e6, 0.0)                                 # caller mutates shape()
    assert inst.geometric_rect().left() == 10.0

