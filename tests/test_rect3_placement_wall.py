"""Wall rectangle placement is 3-click: base → side (angle + W) → depth (H).

Mirrors ``tests/test_rect3_placement_2d.py`` for the wall rect primitive
(Corner / Center variants).  The commit still goes through the unchanged
``_commit_wall_rect_rotated`` and builds four ``WallSegment``s.
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
    s.set_mode("wall")
    while not (s._wall_primitive == "rect"
               and s._wall_rect_from_center is from_center):
        assert s.cycle_placement_variant(+1)
    return s


@pytest.fixture
def scene(qapp):
    return _pick_variant(Model_Space(), False)


@pytest.fixture
def centre_scene(qapp):
    return _pick_variant(Model_Space(), True)


def _press(s, x, y):
    s._press_wall_rect(None, None, QPointF(x, y), None, None, None)


def _endpoints(walls):
    return {(round(w.pt1.x(), 3), round(w.pt1.y(), 3)) for w in walls}


def test_wall_rect_three_clicks_builds_four_walls_on_rotated_rect(scene):
    n0 = len(scene._walls)
    _press(scene, 0, 0)
    _press(scene, 3000, -3000)              # side: 45° (Y-up), W = 3000·√2
    _press(scene, 4000, -2000)              # depth: right of the side
    walls = scene._walls[n0:]
    assert len(walls) == 4
    assert _endpoints(walls) == {(0.0, 0.0), (3000.0, -3000.0),
                                 (4000.0, -2000.0), (1000.0, 1000.0)}
    assert scene._wall_rect_anchor is None
    assert scene._wall_rect_side_pt is None


def test_wall_rect_cursor_side_picks_rect_side(scene):
    _press(scene, 0, 0); _press(scene, 4000, 0); _press(scene, 2000, 1500)   # below
    ys = [w.pt1.y() for w in scene._walls]
    assert max(ys) == pytest.approx(1500)
    assert min(ys) == pytest.approx(0)


def test_wall_rect_centre_variant(centre_scene):
    s = centre_scene
    _press(s, 0, 0); _press(s, 2000, 0); _press(s, 0, -500)   # W 4000, H 1000
    xs = sorted(round(w.pt1.x(), 3) for w in s._walls)
    ys = sorted(round(w.pt1.y(), 3) for w in s._walls)
    assert xs == [-2000, -2000, 2000, 2000]
    assert ys == [-500, -500, 500, 500]


def test_wall_rect_schema_per_step(scene):
    _press(scene, 0, 0)
    assert scene.active_schema().name == "rect_side"
    _press(scene, 3000, 0)
    assert scene.active_schema().name == "rect_depth"


def test_wall_rect_centre_schema_per_step(centre_scene):
    _press(centre_scene, 0, 0)
    assert centre_scene.active_schema().name == "rect_side_center"
    _press(centre_scene, 3000, 0)
    assert centre_scene.active_schema().name == "rect_depth_center"


def test_wall_rect_anchor_is_base_at_both_steps(scene):
    _press(scene, 10, 20)
    assert scene.get_placement_anchor() == QPointF(10, 20)
    _press(scene, 3010, 20)
    assert scene.get_placement_anchor() == QPointF(10, 20)


def test_wall_rect_small_side_and_depth_rejected(scene):
    _press(scene, 0, 0); _press(scene, 0.2, 0)
    assert scene._wall_rect_side_pt is None
    _press(scene, 3000, 0); _press(scene, 1500, 0.1)
    assert scene._walls == []
    assert scene._wall_rect_side_pt is not None      # still at the depth step


def test_wall_rect_typed_side_then_depth(scene):
    _press(scene, 0, 0)
    side = SCHEMAS["rect_side"].resolve(QPointF(0, 0), {"Length": 3000.0, "Angle": 0.0})
    assert scene._apply_wall_dynamic_input(side) is True
    assert scene._wall_rect_side_pt is not None
    depth = SCHEMAS["rect_depth"].resolve(
        QPointF(0, 0), {"H": -1200.0, "__dir__": (0.0, -1.0)})
    assert scene._apply_wall_dynamic_input(depth) is True
    assert len(scene._walls) == 4
    assert max(w.pt1.y() for w in scene._walls) == pytest.approx(1200)


def test_wall_rect_thickness_overlay_follows_rotated_rect(scene):
    """At the depth step the wall-thickness ghost wraps the ROTATED corners."""
    _press(scene, 0, 0); _press(scene, 3000, -3000)
    scene._move_wall_rect(_MoveEventStub(), QPointF(4000, -2000))
    ov = scene._wall_rect_thickness_preview
    assert ov is not None and ov.isVisible()
    br = ov.path().boundingRect()
    # Rotated corners span x∈[0, 4000], y∈[-3000, 1000] — centre (2000, -1000).
    assert br.center().x() == pytest.approx(2000, abs=1.0)
    assert br.center().y() == pytest.approx(-1000, abs=1.0)
    assert br.width() >= 4000 and br.height() >= 4000


def test_wall_rect_side_step_ghost_is_side_guide(scene):
    _press(scene, 0, 0)
    scene._move_wall_rect(_MoveEventStub(), QPointF(3000, 0))
    line = scene._wall_rect_ref_line0.line()
    assert (line.x2(), line.y2()) == pytest.approx((3000, 0))
    assert scene._wall_rect_thickness_preview is None


def test_wall_rect_ghost_after_side_click_spans_the_side(scene):
    _press(scene, 0, 0); _press(scene, 3000, -4000)
    p = scene._wall_rect_preview
    br = p.mapToScene(p.rect()).boundingRect()
    assert (br.left(), br.right()) == pytest.approx((0, 3000), abs=1e-6)
    assert (br.top(), br.bottom()) == pytest.approx((-4000, 0), abs=1e-6)


def test_wall_rect_centre_side_prompt(centre_scene):
    got = []
    centre_scene.instructionChanged.connect(got.append)
    _press(centre_scene, 0, 0)
    assert got[-1] == "Pick edge midpoint (width + angle)"
    _press(centre_scene, 2000, 0)
    assert got[-1] == "Pick depth (second side)"


def test_wall_rect_overlay_collapses_when_cursor_returns_to_side(scene):
    """Deeper hover, then back onto the side line (depth < 0.5): the
    thickness overlay collapses onto the side instead of keeping the old depth."""
    _press(scene, 0, 0); _press(scene, 4000, 0)
    scene._move_wall_rect(_MoveEventStub(), QPointF(2000, -1500))
    deep = scene._wall_rect_thickness_preview.path().boundingRect()
    scene._move_wall_rect(_MoveEventStub(), QPointF(2000, -0.2))
    flat = scene._wall_rect_thickness_preview.path().boundingRect()
    t = scene._get_wall_template()._thickness_mm
    assert deep.height() > 1500
    assert flat.height() <= t + 1.0          # just the wall band along the side
    assert flat.width() >= 4000
