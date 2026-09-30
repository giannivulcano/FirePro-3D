"""Guard tests for the S2 smoke-fix round (movability, HUD schema, snap, dialog)."""
from PyQt6.QtWidgets import QGraphicsItem
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance


def _def(name="A"):
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_block_instance_not_native_movable(qapp):
    # #4: ItemIsMovable must be OFF so the manipulator drives movement in harmony
    d = _def()
    inst = BlockInstance(block_id=d.id, resolver={d.id: d}.get)
    assert not bool(inst.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_place_block_offers_no_rotation_hud(model_space):
    # Smoke 2 retired the rotate step (and with it the S2 #2 rotation HUD):
    # before and after a placement there is no schema, no anchor, and the
    # HUD refuses to open.
    from PyQt6.QtCore import QPointF
    d = _def()
    model_space.register_block_definition(d)
    model_space.set_mode("place_block", template=d.id)
    p = QPointF(5.0, 7.0)
    for _ in range(2):                       # before, then after, a placement
        model_space._move_place_block(None, p)
        assert model_space.active_schema() is None
        assert model_space._plc.get_placement_anchor() is None
        assert model_space._plc._hud_available() is False
        assert model_space.begin_dynamic_input(seed="5") is False
        model_space._press_place_block(None, p, p, None, None, None)
    assert [i.block_rotation() for i in model_space._block_instances] == [0.0, 0.0]
    assert model_space.mode == "place_block"


def test_snap_collects_block_origin_and_vertices(model_space):
    # #1: a placed block exposes its insertion origin + transformed line endpoints
    d = _def()
    model_space.register_block_definition(d)
    inst = model_space.place_block_instance(d.id, (10.0, 0.0), rotation=0.0)
    eng = model_space._snap_engine
    eng.snap_endpoint = True
    eng.snap_center = True
    pts = [(round(p.x()), round(p.y())) for _t, p, _n in eng._collect(inst)]
    assert (10, 0) in pts     # origin (== insertion point)
    assert (110, 0) in pts    # line far end (0,0)-(100,0) shifted by +10 x
