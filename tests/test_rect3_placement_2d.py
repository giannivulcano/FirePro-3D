"""2D rectangle placement is base → side (angle + W) → depth (H) (plan Task 6).

Drives the real press/move handlers on a ``Model_Space`` and asserts the
committed ``RectangleItem`` footprint, the per-step HUD schema, the depth-step
seed and the ghost.
"""
import math
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.model_space import Model_Space
from firepro3d.geometry_2d import RectangleItem
from firepro3d.dynamic_input import SCHEMAS


def _close(p, q, tol=1e-6):
    return abs(p.x() - q.x()) < tol and abs(p.y() - q.y()) < tol


@pytest.fixture
def scene(qapp):
    s = Model_Space(scene_role="block_editor")
    s.set_mode("draw_rectangle")
    return s


def _press(s, x, y):
    s._press_draw_rectangle(None, None, QPointF(x, y), None, None, None)


def _corners(item):
    return item.grip_points()[0:8:2]          # TL, TR, BR, BL


def test_corner_variant_three_clicks(scene):
    ang = math.radians(30)
    side = QPointF(40 * math.cos(ang), -40 * math.sin(ang))
    n = (-math.sin(ang), -math.cos(ang))                 # left normal (Qt)
    depth_pt = QPointF(side.x() + 15 * n[0], side.y() + 15 * n[1])
    _press(scene, 0, 0)
    _press(scene, side.x(), side.y())
    _press(scene, depth_pt.x(), depth_pt.y())
    item = scene._draw_rects[-1]
    cs = _corners(item)
    for p in (QPointF(0, 0), side, depth_pt):
        assert any(_close(c, p, 1e-6) for c in cs)
    assert item._angle == pytest.approx(30.0)


def test_cursor_side_picks_rect_side(scene):
    _press(scene, 0, 0)
    _press(scene, 40, 0)
    _press(scene, 20, 15)                                  # below the side
    cs = _corners(scene._draw_rects[-1])
    assert max(c.y() for c in cs) == pytest.approx(15)
    assert min(c.y() for c in cs) == pytest.approx(0)


def test_centre_variant(scene):
    scene.cycle_placement_variant(+1)
    assert scene._draw_rect_from_center
    _press(scene, 0, 0)
    _press(scene, 20, 0)
    _press(scene, 0, -5)                                   # W 40, H 10
    cs = _corners(scene._draw_rects[-1])
    assert sorted(round(c.x(), 6) for c in cs) == [-20, -20, 20, 20]
    assert sorted(round(c.y(), 6) for c in cs) == [-5, -5, 5, 5]


def test_small_side_and_depth_rejected(scene):
    _press(scene, 0, 0)
    _press(scene, 0.2, 0)
    assert scene._draw_rect_side_pt is None                # still at the side step
    _press(scene, 40, 0)
    _press(scene, 20, 0.1)
    assert scene._draw_rects == []
    assert scene._draw_rect_side_pt is not None            # still at the depth step


def test_typed_negative_depth_flips(scene):
    _press(scene, 0, 0)
    _press(scene, 40, 0)
    p = SCHEMAS["rect_depth"].resolve(QPointF(0, 0), {"H": -12.0, "__dir__": (0.0, -1.0)})
    assert scene._apply_rectangle_dynamic_input(p) is True
    assert max(c.y() for c in _corners(scene._draw_rects[-1])) == pytest.approx(12)


def test_typed_side_advances_to_depth_step(scene):
    _press(scene, 0, 0)
    p = SCHEMAS["rect_side"].resolve(QPointF(0, 0), {"Length": 30.0, "Angle": 90.0})
    assert scene._apply_rectangle_dynamic_input(p) is True
    assert _close(scene._draw_rect_side_pt, QPointF(0, -30))


def test_schema_per_step(scene):
    _press(scene, 0, 0)
    assert scene.active_schema().name == "rect_side"
    _press(scene, 40, 0)
    assert scene.active_schema().name == "rect_depth"


def test_schema_per_step_centre(scene):
    scene.cycle_placement_variant(+1)
    _press(scene, 0, 0)
    assert scene.active_schema().name == "rect_side_center"
    _press(scene, 20, 0)
    assert scene.active_schema().name == "rect_depth_center"


def test_depth_seed_and_normal(scene):
    _press(scene, 0, 0)
    _press(scene, 40, 0)
    scene._move_draw_rectangle(None, QPointF(20, 15))      # 15 below = -15
    coord = scene._plc
    schema = scene.active_schema()
    assert coord._seed_values_for(schema, scene.get_placement_anchor()) == {
        "H": pytest.approx(-15.0)}
    nx, ny = coord._rect_depth_normal()
    assert (nx, ny) == (pytest.approx(0.0), pytest.approx(-1.0))


def test_depth_ghost_matches_commit(scene):
    _press(scene, 0, 0)
    _press(scene, 30, -10)
    scene._move_draw_rectangle(None, QPointF(5, -25))
    ghost = scene._draw_rect_preview
    ghost_pts = [ghost.mapToScene(p) for p in (
        ghost.rect().topLeft(), ghost.rect().topRight(),
        ghost.rect().bottomRight(), ghost.rect().bottomLeft())]
    _press(scene, 5, -25)
    for c in _corners(scene._draw_rects[-1]):
        assert any(_close(c, g, 1e-6) for g in ghost_pts)


def test_roundtrip(scene):
    _press(scene, 3, 4)
    _press(scene, 33, -8)
    _press(scene, 20, -30)
    it = scene._draw_rects[-1]
    back = RectangleItem.from_dict(it.to_dict())
    for a, b in zip(back.grip_points(), it.grip_points()):
        assert _close(a, b)
