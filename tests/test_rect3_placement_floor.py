"""Floor rectangle placement is 3-click: base → side (angle + W) → depth (H).

Mirrors ``tests/test_rect3_placement_wall.py`` for the floor rect primitive
(Corner / Center variants).  The commit still goes through the unchanged
``_commit_floor_rect_rotated`` and builds ONE ``FloorSlab``.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt

from firepro3d.model_space import Model_Space
from firepro3d.dynamic_input import SCHEMAS


class _MoveEventStub:
    """Minimal ``QGraphicsSceneMouseEvent`` stand-in (modifiers only)."""

    def __init__(self, modifiers=Qt.KeyboardModifier.NoModifier):
        self._mods = modifiers

    def modifiers(self):
        return self._mods


def _pick_variant(s, from_center):
    s.set_mode("floor")
    while not (s._floor_primitive == "rect"
               and s._floor_rect_from_center is from_center):
        assert s.cycle_placement_variant(+1)
    return s


@pytest.fixture
def scene(qapp):
    return _pick_variant(Model_Space(), False)


@pytest.fixture
def centre_scene(qapp):
    return _pick_variant(Model_Space(), True)


def _press(s, x, y):
    s._press_floor_rect(None, None, QPointF(x, y), None, None, None)


def _pts(slab):
    return {(round(p.x(), 3), round(p.y(), 3)) for p in slab._points}


def test_floor_rect_three_clicks_one_slab(scene):
    n0 = len(scene._floor_slabs)
    for x, y in ((0, 0), (4000, 0), (2000, -2500)):
        _press(scene, x, y)
    slabs = scene._floor_slabs[n0:]
    assert len(slabs) == 1
    assert _pts(slabs[0]) == {(0.0, 0.0), (4000.0, 0.0),
                              (4000.0, -2500.0), (0.0, -2500.0)}
    assert scene._floor_rect_anchor is None
    assert scene._floor_rect_side_pt is None


def test_floor_rect_angled_side_gives_rotated_slab(scene):
    _press(scene, 0, 0); _press(scene, 3000, -3000); _press(scene, 4000, -2000)
    assert _pts(scene._floor_slabs[-1]) == {(0.0, 0.0), (3000.0, -3000.0),
                                            (4000.0, -2000.0), (1000.0, 1000.0)}


def test_floor_rect_centre_variant(centre_scene):
    s = centre_scene
    _press(s, 0, 0); _press(s, 2000, 0); _press(s, 0, -500)   # W 4000, H 1000
    assert _pts(s._floor_slabs[-1]) == {(-2000.0, -500.0), (2000.0, -500.0),
                                        (2000.0, 500.0), (-2000.0, 500.0)}


def test_floor_rect_schema_per_step(scene):
    _press(scene, 0, 0)
    assert scene.active_schema().name == "rect_side"
    _press(scene, 3000, 0)
    assert scene.active_schema().name == "rect_depth"


def test_floor_rect_centre_schema_per_step(centre_scene):
    _press(centre_scene, 0, 0)
    assert centre_scene.active_schema().name == "rect_side_center"
    _press(centre_scene, 3000, 0)
    assert centre_scene.active_schema().name == "rect_depth_center"


def test_floor_rect_anchor_is_base_at_both_steps(scene):
    _press(scene, 10, 20)
    assert scene.get_placement_anchor() == QPointF(10, 20)
    _press(scene, 3010, 20)
    assert scene.get_placement_anchor() == QPointF(10, 20)


def test_floor_rect_small_side_and_depth_rejected(scene):
    _press(scene, 0, 0); _press(scene, 0.2, 0)
    assert scene._floor_rect_side_pt is None
    _press(scene, 3000, 0); _press(scene, 1500, 0.1)
    assert scene._floor_slabs == []
    assert scene._floor_rect_side_pt is not None     # still at the depth step


def test_floor_rect_typed_side_then_depth(scene):
    _press(scene, 0, 0)
    side = SCHEMAS["rect_side"].resolve(QPointF(0, 0), {"Length": 3000.0, "Angle": 0.0})
    assert scene._apply_floor_dynamic_input(side) is True
    assert scene._floor_rect_side_pt is not None
    depth = SCHEMAS["rect_depth"].resolve(
        QPointF(0, 0), {"H": -1200.0, "__dir__": (0.0, -1.0)})
    assert scene._apply_floor_dynamic_input(depth) is True
    assert len(scene._floor_slabs) == 1
    assert max(p.y() for p in scene._floor_slabs[-1]._points) == pytest.approx(1200)


def test_floor_rect_depth_ghost_is_rotated_rect(scene):
    _press(scene, 0, 0); _press(scene, 3000, -3000)
    scene._move_floor_rect(_MoveEventStub(), QPointF(4000, -2000))
    prev = scene._floor_rect_preview
    br = prev.mapToScene(prev.rect()).boundingRect()
    assert br.left() == pytest.approx(0, abs=1e-6)
    assert br.right() == pytest.approx(4000, abs=1e-6)
    assert br.top() == pytest.approx(-3000, abs=1e-6)
    assert br.bottom() == pytest.approx(1000, abs=1e-6)


def test_floor_rect_side_step_ghost_is_side_guide(scene):
    _press(scene, 0, 0)
    scene._move_floor_rect(_MoveEventStub(), QPointF(3000, 0))
    line = scene._floor_rect_ref_line0.line()
    assert (line.x2(), line.y2()) == pytest.approx((3000, 0))


def test_floor_rect_ghost_after_side_click_spans_the_side(scene):
    _press(scene, 0, 0); _press(scene, 3000, -4000)
    p = scene._floor_rect_preview
    br = p.mapToScene(p.rect()).boundingRect()
    assert (br.left(), br.right()) == pytest.approx((0, 3000), abs=1e-6)
    assert (br.top(), br.bottom()) == pytest.approx((-4000, 0), abs=1e-6)


def test_floor_rect_centre_side_prompt(centre_scene):
    got = []
    centre_scene.instructionChanged.connect(got.append)
    _press(centre_scene, 0, 0)
    assert got[-1] == "Pick edge midpoint (width + angle)"
