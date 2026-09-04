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
    assert inst.block_pos() == (50.0, 60.0)
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


def test_place_block_reentry_clears_stale_ghost(model_space):
    # Seam-review blocker: activating a DIFFERENT block mid-placement must drop
    # the previous block's ghost (else it previews the wrong block).
    a = _def(model_space, "A")
    b = _def(model_space, "B")
    model_space.set_mode("place_block", template=a.id)
    model_space._place_block_set_position(QPointF(0.0, 0.0))
    old_ghost = model_space._place_block_ghost
    assert old_ghost is not None
    model_space.set_mode("place_block", template=b.id)   # re-enter for block B
    assert model_space._place_block_id == b.id
    assert model_space._place_block_ghost is None         # stale ghost cleared
    assert old_ghost.scene() is None                      # removed from the scene
    assert model_space._place_block_anchor is None
    assert model_space._place_block_step == 0


def test_make_block_from_selection_consumes_and_places(model_space):
    from firepro3d.construction_geometry import LineItem
    from PyQt6.QtCore import QPointF
    li = LineItem.from_dict({"type": "draw_line", "pt1": [0, 0], "pt2": [100, 0],
                             "color": "#ffffff", "lineweight": 1.0})
    model_space.addItem(li)
    model_space._draw_lines.append(li)
    inst = model_space.make_block_from_selection(
        [li], origin=QPointF(0.0, 0.0), name="Corner", library="Detail", series="Joints")
    assert li not in model_space._draw_lines
    assert li.scene() is None
    assert inst.block_id in model_space._block_definitions
    assert inst in model_space._block_instances
    d = model_space.get_block_definition(inst.block_id)
    assert d.name == "Corner" and d.library == "Detail" and d.series == "Joints"


def test_make_block_refuses_empty(model_space):
    from PyQt6.QtCore import QPointF
    assert model_space.make_block_from_selection(
        [], origin=QPointF(0, 0), name="x", library="l", series="s") is None
