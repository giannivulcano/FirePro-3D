"""Layer Height / Opaque / Constraint Points records and block z (D3, D4, D6, D14)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_instance import BlockInstance
from firepro3d.block_stack import clamp_layer_height
from firepro3d.constants import Z_BLOCK_STACK, Z_BLOCK_STACK_STEP, Z_FILLED_REGION, Z_ROOF
from firepro3d.model_space import Model_Space
from tests._block_stack_helpers import rect_def


@pytest.fixture
def be(qapp):
    s = Model_Space(scene_role="block_editor")
    yield s
    s.cleanup()


def test_defaults_write_no_keys(be):
    inst = be.place_block_instance(rect_def(be).id, (0.0, 0.0))
    for rec in (inst.to_dict(), inst.to_nested_dict()):
        assert not {"layer_height", "opaque", "constraint_points_off"} & set(rec)


def test_values_survive_both_record_shapes(be):
    d = rect_def(be)
    a = be.place_block_instance(d.id, (0.0, 0.0))
    a.set_layer_height(3)
    a.set_opaque(True)
    a.constraint_points_off = True
    for rec in (a.to_dict(), a.to_nested_dict()):
        b = be.place_block_instance(rec["block_id"], (0.0, 0.0),
                                    **BlockInstance.place_kwargs(rec))
        assert (b.layer_height, b.is_opaque(), b.constraint_points_off) == (3, True, True)
        assert b.zValue() == a.zValue()
        c = BlockInstance.from_dict(rec, be.get_block_definition)    # the paste ghost path
        assert (c.layer_height, c.constraint_points_off) == (3, True)


@pytest.mark.parametrize("raw,want", [(5, 5), ("7", 7), (2.9, 2), (5000, 1000), (-5000, -1000),
                                      ("x", 0), (None, 0), (float("nan"), 0), (float("inf"), 0)])
def test_clamp_layer_height(raw, want):
    assert clamp_layer_height(raw) == want


def test_a_bad_opaque_value_reads_as_absent():
    assert BlockInstance.place_kwargs({"opaque": "yes"})["opaque"] is None


def test_opaque_default_follows_the_context(qapp):
    proj = Model_Space()
    from firepro3d.block_editor import BlockEditorWidget
    d = rect_def(proj)
    w1, w2 = BlockEditorWidget(proj, kind="block"), BlockEditorWidget(proj, kind="schematic")
    plain, schem = w1.editor_scene, w2.editor_scene
    rec = {"type": "block_instance", "block_id": d.id, "pos": [0, 0], "rotation": 0}
    a = plain.place_block_instance(d.id, (0.0, 0.0), **BlockInstance.place_kwargs(rec))
    b = schem.place_block_instance(d.id, (0.0, 0.0), **BlockInstance.place_kwargs(rec))
    assert (a.is_opaque(), b.is_opaque()) == (False, True)


def test_setting_the_context_default_keeps_the_record_clean(qapp):
    proj = Model_Space()
    from firepro3d.block_editor import BlockEditorWidget
    d = rect_def(proj)
    w = BlockEditorWidget(proj, kind="schematic")
    sc = w.editor_scene
    i = sc.place_block_instance(d.id, (0.0, 0.0))
    i.set_opaque(False)
    assert i.to_nested_dict()["opaque"] is False
    i.set_opaque(True)
    assert "opaque" not in i.to_nested_dict()


def test_block_z_sits_in_its_band_and_follows_height(be):
    d = rect_def(be)
    i = be.place_block_instance(d.id, (0.0, 0.0))
    assert i.zValue() == Z_BLOCK_STACK
    i.set_layer_height(1000)
    assert i.zValue() == Z_BLOCK_STACK + 1000 * Z_BLOCK_STACK_STEP < Z_FILLED_REGION
    i.set_layer_height(-1000)
    assert i.zValue() == Z_BLOCK_STACK - 1000 * Z_BLOCK_STACK_STEP > Z_ROOF


def test_plan_block_z_is_untouched(qapp):
    sc = Model_Space()
    i = sc.place_block_instance(rect_def(sc).id, (0.0, 0.0))
    z = i.zValue()
    i.set_layer_height(50)
    assert i.zValue() == z
    sc.cleanup()
