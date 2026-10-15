"""Guards: posed primitive stand-ins of a placed block (block snap parity, T1).

Ground truth: the instance's own full pose (oracle) on hand-written
definition-local coordinates.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import ArcItem, CircleItem, LineItem, RectangleItem
from firepro3d.model_space import Model_Space
from tests._block_snap_helpers import (C_C, C_R, POSE_IDS, POSES, near,
                                       nested_oracle, oracle,
                                       register_snap_block)


def _placed(qapp, pose, nested=True):
    scene = Model_Space(scene_role="block_editor")
    d = register_snap_block(scene, nested=nested)
    pos, rot, mir, s = pose
    inst = scene.place_block_instance(d.id, pos, rotation=rot,
                                      mirrored=mir, scale=s)
    return scene, inst


def _items(inst):
    return [it for _b, it in inst.snap_primitives()]


@pytest.mark.parametrize("pose", POSES, ids=POSE_IDS)
def test_posed_primitives_sit_on_the_drawn_geometry(qapp, pose):
    scene, inst = _placed(qapp, pose)
    s = pose[3]
    items = _items(inst)
    lines = [it for it in items if isinstance(it, LineItem)]
    circles = [it for it in items if isinstance(it, CircleItem)]
    assert len(lines) == 2 and len(circles) == 2                         # [RED]
    assert sum(isinstance(it, RectangleItem) for it in items) == 1
    assert sum(isinstance(it, ArcItem) for it in items) == 1
    l1 = lines[0]
    ends = [l1.mapToScene(l1.line().p1()), l1.mapToScene(l1.line().p2())]
    want = [oracle(inst, 60.0, -80.0), oracle(inst, 180.0, -80.0)]
    assert any(near(ends[0], w) for w in want) and any(near(ends[1], w) for w in want)
    outer = next(c for c in circles if abs(c._radius - C_R * s) < 1e-6)
    assert near(QPointF(outer._center), oracle(inst, *C_C))
    inner = next(c for c in circles if c is not outer)
    assert abs(inner._radius - 15.0 * 1.2 * s) < 1e-6
    assert near(QPointF(inner._center), nested_oracle(inst, 20.0, 0.0))


def test_text_and_scaffold_records_get_no_stand_in(qapp):
    from firepro3d.block_definition import BlockDefinition, is_scaffold
    from firepro3d.text_item import TextAnnotationData, TextItem
    scene = Model_Space(scene_role="block_editor")
    txt = TextItem(TextAnnotationData(text="A", x=0.0, y=0.0,
                                      height_mm=10.0)).to_dict()
    scaffold = {"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
                "color": "#ffffff", "lineweight": 1.0,
                "reference": True, "printed": False}
    assert is_scaffold(scaffold)                       # precondition
    d = BlockDefinition.new(name="T", library="L", series="S",
                            origin=(0.0, 0.0), primitives=[txt, scaffold])
    scene.register_block_definition(d)
    inst = scene.place_block_instance(d.id, (0.0, 0.0))
    assert _items(inst) == []


def test_snap_primitives_memoised_until_the_pose_changes(qapp):
    scene, inst = _placed(qapp, POSES[0], nested=False)
    first = inst.snap_primitives()
    assert inst.snap_primitives() is first
    inst.set_block_rotation(45.0)
    assert inst.snap_primitives() is not first


def test_a_missing_nested_block_is_skipped(qapp):
    from firepro3d.block_definition import BlockDefinition
    scene = Model_Space(scene_role="block_editor")
    d = BlockDefinition.new(
        name="Orph", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": "no-such-id",
                     "pos": [0, 0]},
                    {"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
                     "color": "#ffffff", "lineweight": 1.0}])
    scene.register_block_definition(d)
    inst = scene.place_block_instance(d.id, (0.0, 0.0))
    assert [type(it) for it in _items(inst)] == [LineItem]
