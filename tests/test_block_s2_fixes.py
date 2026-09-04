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


def test_place_block_hud_schema_only_at_rotate_step(model_space):
    # #2: the rotation schema surfaces at step 1, nothing at step 0
    from firepro3d.dynamic_input import SCHEMAS
    model_space._place_block_step = 0
    assert model_space._plc._place_block_schema_for_step() is None
    model_space._place_block_step = 1
    assert model_space._plc._place_block_schema_for_step() is SCHEMAS.get("rotation")


def test_place_block_hud_available_at_rotate_step(model_space):
    # #2 (real gate): the HUD was refused because get_placement_anchor() knew no
    # _place_block_anchor, so _hud_available() returned False despite the schema.
    from PyQt6.QtCore import QPointF
    d = _def()
    model_space.register_block_definition(d)
    model_space.set_mode("place_block", template=d.id)
    model_space._place_block_step = 1
    model_space._place_block_anchor = QPointF(5.0, 7.0)
    anc = model_space._plc.get_placement_anchor()
    assert anc is not None and (anc.x(), anc.y()) == (5.0, 7.0)
    assert model_space._plc._hud_available() is True


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


def test_make_block_dialog_is_frameless_themed(qapp):
    # #2: dialog adopts the house frameless shell (themed header, scoped objectName)
    from firepro3d.make_block_dialog import MakeBlockDialog
    dlg = MakeBlockDialog()
    assert dlg.objectName() == "MakeBlockDialog"
    assert hasattr(dlg, "_titlebar")
    dlg.deleteLater()
