"""Guards: posed primitive stand-ins of a placed block (block snap parity, T1).

Ground truth: the instance's own full pose (oracle) on hand-written
definition-local coordinates.
"""
from __future__ import annotations

import math

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


def _same_points(got, want, tol=0.01):
    return len(got) == len(want) and all(any(near(g, w, tol) for g in got)
                                         for w in want)


@pytest.mark.parametrize("pose", POSES, ids=POSE_IDS)
def test_posed_rect_corners_and_arc_ends_sit_on_the_drawn_geometry(qapp, pose):
    # Review I1: the mirror hooks of rect (angle fold) and arc (start-angle
    # fold) are the intricate ones -- check their posed geometry, not counts.
    scene, inst = _placed(qapp, pose, nested=False)
    items = _items(inst)
    rect = next(it for it in items if isinstance(it, RectangleItem))
    # grip_points() are already scene-space and rotation-aware (the items'
    # overridden mapToScene would rotate a rotated rect twice).
    corners = [rect.grip_points()[i] for i in (0, 2, 4, 6)]
    want = [oracle(inst, x, y) for x, y in
            ((-160.0, -40.0), (-60.0, -40.0), (-60.0, 40.0), (-160.0, 40.0))]
    assert _same_points(corners, want), (corners, want)
    arc = next(it for it in items if isinstance(it, ArcItem))
    ends = [arc.grip_points()[i] for i in (1, 2)]
    # 0 deg -> (cx + r, cy); 180 deg -> (cx - r, cy) (Y-down local)
    want = [oracle(inst, -70.0, 100.0), oracle(inst, -130.0, 100.0)]
    assert _same_points(ends, want), (ends, want)
    apex = oracle(inst, -100.0, 70.0)                  # 90 deg: still on the arc
    assert abs(math.hypot(apex.x() - arc._center.x(), apex.y() - arc._center.y())
               - arc._radius) < 0.01
    assert all(it.scene() is None for it in items)     # stand-ins are scene-free


def test_cyclic_nesting_terminates_with_each_primitive_once(qapp):
    # Review I2: A nests B nests A -- the active-set guard stops the loop.
    from firepro3d.block_definition import BlockDefinition
    scene = Model_Space(scene_role="block_editor")
    line = {"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
            "color": "#ffffff", "lineweight": 1.0}
    a = BlockDefinition.new(name="A", library="L", series="S",
                            origin=(0.0, 0.0), primitives=[dict(line)])
    b = BlockDefinition.new(name="B", library="L", series="S",
                            origin=(0.0, 0.0), primitives=[dict(line)])
    a.primitives.append({"type": "block_instance", "block_id": b.id,
                         "pos": [100, 0]})
    b.primitives.append({"type": "block_instance", "block_id": a.id,
                         "pos": [100, 0]})
    scene.register_block_definition(a)
    scene.register_block_definition(b)
    from firepro3d.block_snap_geometry import posed_primitives
    items = posed_primitives(a, (0.0, 0.0, 0.0, False, 1.0))
    assert [type(it) for it in items] == [LineItem, LineItem]   # A's + B's


def test_snap_primitives_rebuild_after_a_definition_edit_and_a_mirror(qapp):
    # Review I2: content edits and mirror / scale changes invalidate the cache.
    scene, inst = _placed(qapp, POSES[0], nested=False)
    d = inst.definition()
    first = inst.snap_primitives()
    d.set_primitives(d.primitives[:1])                 # keep only L1
    second = inst.snap_primitives()
    assert second is not first and len(second) == 1
    inst.set_block_mirrored(True)
    assert inst.snap_primitives() is not second


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
