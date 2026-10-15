"""Guards: a block's insertion origin snaps (and ALIGN-acquires) even when it
lies outside the block geometry's bounding rect.

Real path: shown Model_View over a real Model_Space (a plan scene placing a
second block, and the Block Editor drawing a line), posted mouse events through
the scene dispatch (cursor snap via get_effective_position -> find()). Ground
truth: the scene's published snap / ALIGN result. The block's only stroke sits
200-300 mm right of its origin, so the scene's bounding-rect query around the
origin never returned the instance (the bug).
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_definition import BlockDefinition
from tests._snap_polish_helpers import close_view, dwell, make_view, move

_INS = (100.0, 80.0)      # on-screen: make_view shows -400..400 x -300..300

# (scene role, cursor tool): model plans place blocks (no 2D drawing there);
# the Block Editor draws (nested instances live in its scene).
_SCENES = [("plan", "place_block"), ("block_editor", "draw_line")]


def _at(p: QPointF, x: float, y: float, tol: float = 0.01) -> bool:
    return math.hypot(p.x() - x, p.y() - y) <= tol


def _view_with_block(role: str, mode: str, x0: float = 200.0, x1: float = 300.0):
    view, scene = make_view(role=role, scale=1.0, mode=None)
    d = BlockDefinition.new(name="Off", library="L", series="S",
                            primitives=[{"type": "draw_line", "pt1": [x0, 0],
                                         "pt2": [x1, 0], "color": "#ffffff",
                                         "lineweight": 1.0}],
                            origin=(0.0, 0.0))
    scene.register_block_definition(d)
    inst = scene.place_block_instance(d.id, _INS, rotation=0.0)
    if mode == "place_block":
        scene.set_mode(mode, template=d.id)
    else:
        scene.set_mode(mode)
    assert scene.mode == mode
    eng = scene._snap_engine
    eng.snap_center = True
    eng.snap_intersection = False
    return view, scene, inst


@pytest.mark.parametrize("role,mode", _SCENES)
def test_hover_snaps_to_an_off_geometry_block_origin(qapp, role, mode):
    view, scene, inst = _view_with_block(role, mode)
    try:
        assert not inst.sceneBoundingRect().contains(QPointF(*_INS))   # precondition
        move(view, QPointF(_INS[0] + 1.0, _INS[1] + 1.0))
        res = scene._snap_result
        assert res is not None and res.snap_type == "center"               # [RED]
        assert _at(res.point, *_INS)
        assert res.source_item is inst
    finally:
        close_view(view, scene)


# ALIGN arms only in ``_ALIGN_PLACEMENT_MODES`` (place_block is not one), so
# the plan case acquires while placing a wall.
@pytest.mark.parametrize("role,mode", [("plan", "wall"), ("block_editor", "draw_line")])
def test_align_dwell_on_an_off_geometry_block_origin_tracks_its_axes(qapp, role, mode):
    view, scene, _inst = _view_with_block(role, mode)
    try:
        dwell(view, QPointF(_INS[0] + 1.0, _INS[1] + 1.0))   # acquire the origin
        move(view, QPointF(_INS[0] - 300.0, _INS[1] + 4.0))  # near its H ray
        res = scene._align_result
        assert res is not None and res.snap_type == "align_path"          # [RED]
        assert _at(res.point, _INS[0] - 300.0, _INS[1], 0.5)
    finally:
        close_view(view, scene)


def test_hidden_instance_or_cen_off_offers_no_origin(qapp):
    view, scene, inst = _view_with_block("plan", "place_block")
    try:
        scene._snap_engine.snap_center = False
        move(view, QPointF(_INS[0] + 1.0, _INS[1] + 1.0))
        res = scene._snap_result
        assert res is None or not _at(res.point, *_INS)
        scene._snap_engine.snap_center = True
        inst.setVisible(False)
        move(view, QPointF(_INS[0] + 2.0, _INS[1] + 2.0))
        res = scene._snap_result
        assert res is None or not _at(res.point, *_INS)
    finally:
        close_view(view, scene)


def test_item_filter_and_exclude_gate_the_off_geometry_origin(qapp):
    # The registry pass honours find()'s caller rules (a resized / dragged
    # block must not snap to its own origin).
    from PyQt6.QtGui import QTransform
    view, scene, inst = _view_with_block("plan", "place_block")
    try:
        eng, cur = scene._snap_engine, QPointF(_INS[0] + 1.0, _INS[1] + 1.0)
        hit = eng.find(cur, scene, QTransform())
        assert hit is not None and hit.source_item is inst              # positive control
        for kw in ({"item_filter": lambda it: it is not inst}, {"exclude": inst}):
            res = eng.find(cur, scene, QTransform(), **kw)
            assert res is None or res.source_item is not inst
    finally:
        close_view(view, scene)


def test_block_origin_inside_its_geometry_still_snaps_to_the_instance(qapp):
    # Control: the bbox query already collects this instance; the registry
    # pass must not change the winner or its source. The line's midpoint sits
    # ON the insertion point, and since block primitives snap like loose ones
    # (user ruling 2026-10-15: on a coincident point the primitive's snap wins
    # by the normal priority picker) MID beats the origin's CEN there.
    view, scene, inst = _view_with_block("plan", "place_block", -50.0, 50.0)
    try:
        move(view, QPointF(_INS[0] + 1.0, _INS[1] + 1.0))
        res = scene._snap_result
        assert res is not None and res.snap_type == "midpoint"
        assert _at(res.point, *_INS) and res.source_item is inst
    finally:
        close_view(view, scene)
