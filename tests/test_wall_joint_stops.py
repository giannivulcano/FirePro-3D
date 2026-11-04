"""Wall joint stops: a wall stops flat on the walls it meets, with a seam.

Hand-derived geometry: 300 mm walls meeting at the origin, y grows downward.
LEFT and DOWN form the shaft corner, RIGHT comes in from the east.
"""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.level_manager import LevelManager
from firepro3d.wall import WallSegment

HALF = 150.0
LOW = -1500.0        # Top Offset of a wall that ends below its neighbours


def _ms():
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    s._level_manager = LevelManager()
    lm = s._level_manager
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=lm.get("Level 1").elevation + 3000.0)
    return s


def _wall(s, p1, p2, top_offset=0.0, j1="Auto", j2="Auto"):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=2 * HALF)
    w._top_offset_mm = top_offset
    w._join_mode_pt1 = j1
    w._join_mode_pt2 = j2
    s.addItem(w)
    s._walls.append(w)
    assert abs(w.half_thickness_scene() - HALF) < 1e-9
    w.invalidate_geometry()
    return w


def _left(s, **kw):
    return _wall(s, (-1500, 0), (0, 0), **kw)


def _down(s, **kw):
    return _wall(s, (0, 0), (0, 1500), **kw)


def _right(s, **kw):
    return _wall(s, (0, 0), (1500, 0), **kw)


def _pts(wall):
    body = wall.outline().body
    return [(round(body.at(i).x(), 3), round(body.at(i).y(), 3))
            for i in range(body.count())]


def _on_segment(pt, a, b, tol=1e-3):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length == 0.0:
        return False
    t = ((pt.x() - a.x()) * dx + (pt.y() - a.y()) * dy) / length
    d = abs((pt.x() - a.x()) * dy - (pt.y() - a.y()) * dx) / length
    return d <= tol and -tol <= t <= length + tol


def _stroked(wall, x, y):
    return any(_on_segment(QPointF(x, y), a, b)
               for a, b in wall.outline().stroke_segments)


def _assert_shaft_stop(left, down, right):
    assert min(x for x, _y in _pts(right)) == pytest.approx(HALF)
    assert (HALF, -HALF) in _pts(left) and (-HALF, HALF) in _pts(left)
    assert (HALF, -HALF) in _pts(down) and (-HALF, HALF) in _pts(down)
    assert _stroked(right, HALF, 0.0), "seam on the contact edge"
    assert _stroked(right, 800.0, -HALF), "far face kept"
    assert not _stroked(left, 0.0, 0.0), "the L's own mitre stays unlined"
    assert not _stroked(down, 0.0, 0.0), "the L's own mitre stays unlined"


def test_shaft_by_height(qapp):
    s = _ms()
    left, down = _left(s), _down(s)
    _assert_shaft_stop(left, down, _right(s, top_offset=LOW))


def test_shaft_by_explicit_butt_at_equal_tops(qapp):
    s = _ms()
    left, down = _left(s), _down(s)
    _assert_shaft_stop(left, down, _right(s, j1="Butt"))


def test_shaft_any_creation_order(qapp):
    s = _ms()
    right = _right(s, top_offset=LOW)
    down, left = _down(s), _left(s)
    _assert_shaft_stop(left, down, right)


def test_down_butt_gives_a_straight_through_tee(qapp):
    s = _ms()
    left, right = _left(s), _right(s)
    down = _down(s, j1="Butt")
    assert min(y for _x, y in _pts(down)) == pytest.approx(HALF)
    assert max(x for x, _y in _pts(left)) == pytest.approx(0.0)
    assert min(x for x, _y in _pts(right)) == pytest.approx(0.0)
    assert _stroked(down, 0.0, HALF), "seam"
    assert not _stroked(left, 0.0, 0.0), "no line across the through walls"


def _is_pie(*walls):
    return all(w.outline().wedge[0] or w.outline().wedge[1] for w in walls)


@pytest.mark.parametrize("tops, expect_pie, stopped", [
    ((0.0, 0.0, 0.0), True, ()),                    # all the same
    ((0.0, LOW, LOW), True, ()),                    # one tallest wall
    ((0.0, -500.0, LOW), True, ()),                 # one tallest wall
    ((0.0, 0.0, LOW), False, (2,)),                 # two tall, one low
])
def test_height_rule_table(qapp, tops, expect_pie, stopped):
    s = _ms()
    walls = [_left(s, top_offset=tops[0]), _down(s, top_offset=tops[1]),
             _right(s, top_offset=tops[2])]
    assert _is_pie(*walls) is expect_pie
    assert [i for i, w in enumerate(walls) if w.outline().seams] == list(stopped)


def test_two_low_walls_both_stop_at_a_cross(qapp):
    s = _ms()
    left, right = _left(s), _right(s)
    up = _wall(s, (0, -1500), (0, 0), top_offset=LOW)
    down = _down(s, top_offset=LOW)
    assert up.outline().seams and down.outline().seams
    assert not left.outline().seams and not right.outline().seams


def test_solid_keeps_a_low_wall_in_the_pie(qapp):
    s = _ms()
    walls = [_left(s), _down(s), _right(s, top_offset=LOW, j1="Solid")]
    assert _is_pie(*walls)
    assert not walls[2].outline().seams


def test_two_wall_corner_lower_wall_stops(qapp):
    s = _ms()
    left = _left(s)
    down = _down(s, top_offset=LOW)
    assert max(x for x, _y in _pts(left)) == pytest.approx(HALF)
    assert min(y for _x, y in _pts(down)) == pytest.approx(HALF)
    assert _stroked(down, 0.0, HALF), "seam"


def test_two_wall_corner_solid_keeps_the_mitre(qapp):
    s = _ms()
    left = _left(s)
    down = _down(s, top_offset=LOW, j1="Solid")
    assert (HALF, -HALF) in _pts(left) and (-HALF, HALF) in _pts(left)
    assert (HALF, -HALF) in _pts(down) and (-HALF, HALF) in _pts(down)
    assert not down.outline().seams


def test_two_wall_corner_explicit_butt_matches_the_height_stop(qapp):
    s = _ms()
    left = _left(s)
    down = _down(s, j1="Butt")
    assert max(x for x, _y in _pts(left)) == pytest.approx(HALF)
    assert min(y for _x, y in _pts(down)) == pytest.approx(HALF)


def test_butt_on_the_taller_wall_makes_it_the_one_that_stops(qapp):
    s = _ms()
    left = _left(s, j2="Butt")
    down = _down(s, top_offset=LOW)
    assert max(x for x, _y in _pts(left)) == pytest.approx(-HALF)
    assert not down.outline().seams and left.outline().seams


def test_two_butts_of_three_keep_todays_result(qapp):
    s = _ms()
    left = _left(s)
    down, right = _down(s, j1="Butt"), _right(s, j1="Butt")
    assert not down.outline().seams and not right.outline().seams
    assert min(y for _x, y in _pts(down)) == pytest.approx(0.0)
    assert left.outline().body.count() == 5


def test_angled_stopper_wraps_the_outer_corner(qapp):
    s = _ms()
    left, down = _left(s), _down(s)
    ne = _wall(s, (0, 0), (1200, -1200), top_offset=LOW)
    assert (HALF, -HALF) in _pts(ne), "the end hugs the L's outer corner"
    assert len(ne.outline().seams) == 2
    for wall in (left, down):
        overlap = ne.path().intersected(wall.path())
        assert overlap.boundingRect().width() * overlap.boundingRect().height() < 1.0
    assert _stroked(left, -800.0, -HALF)
    assert _stroked(down, HALF, 800.0)


def test_stop_at_right_alignment_keeps_every_body(qapp):
    from firepro3d.wall import ALIGN_RIGHT
    s = _ms()
    left, down = _left(s), _down(s)
    right = _right(s, top_offset=LOW)
    for wall in (left, down, right):
        wall._alignment = ALIGN_RIGHT
    for wall in (left, down, right):
        wall.invalidate_geometry()
    for wall in (left, down, right):
        assert wall.outline().stroke_segments, "body kept in the union"


def test_top_offset_edit_refreshes_the_partners(qapp):
    s = _ms()
    left, down, right = _left(s), _down(s), _right(s)
    assert _is_pie(left, down, right)
    right.set_property("Top Offset", str(LOW))
    assert right.outline().seams, "the panel path takes effect"
    assert not left.outline().wedge[1], "the partner left the pie"


def test_level_elevation_edit_refreshes_joints(qapp):
    s = _ms()
    left, down = _left(s), _down(s)
    right = _wall(s, (0, 0), (1500, 0))
    right._top_level = "Level 1"
    right.invalidate_geometry()
    assert right.outline().seams, "precondition: a lower wall"
    lm = s._level_manager
    lm.get("Level 2").elevation = lm.get("Level 1").elevation
    lm.update_elevations(s)
    assert not right.outline().seams
    assert _is_pie(left, down, right)


def test_stop_survives_save_and_reload(qapp, tmp_path):
    s = _ms()
    _left(s), _down(s), _right(s, top_offset=LOW)
    path = str(tmp_path / "stops.fpd")
    s.save_to_file(path)
    fresh = _ms()
    fresh.load_from_file(path)
    stopped = [w for w in fresh._walls if w.outline().seams]
    assert len(fresh._walls) == 3 and len(stopped) == 1
    assert min(x for x, _y in _pts(stopped[0])) == pytest.approx(HALF)
