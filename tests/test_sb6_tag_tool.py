"""SB6 AC1 / D7 -- the Tag tool through posted mouse events on a shown plan view.
Raw scene: wall (-2000,0)-(2000,0), 200 mm thick (band |y| <= 100 scene at ppm 1 and
1:100); door_914 at offset_along 1000 -> centre (-1000, 0), 914 wide."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from tests._sb6_helpers import LEADER, add_door, add_wall, tags_of
from tests._snap_polish_helpers import click, close_view, make_view, move


def _armed(view, scene):
    w = add_wall(scene)
    add_door(scene, w)
    scene.push_undo_state()
    scene.set_mode("tag")
    return w


def test_ac1_hover_previews_click_places_tool_stays_armed_esc_exits(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = _armed(view, scene)
        move(view, QPointF(800.0, 0.0))                                   # over the wall
        assert scene._move_ghost                                          # [RED]
        assert scene._tag_ctl.ghost.block_id == "system-tags-walltag"
        move(view, QPointF(-1000.0, 0.0))                                 # over the door (inside the wall)
        assert scene._tag_ctl.ghost.block_id == "system-tags-doortag"     # [RED: openings first]
        move(view, QPointF(800.0, 2500.0))                                # empty space
        assert not scene._move_ghost
        p0 = scene._undo_pos
        move(view, QPointF(800.0, 0.0))
        click(view, QPointF(800.0, 0.0))
        (tag,) = tags_of(scene)
        assert tag._host_uid == w._uid and scene._undo_pos == p0 + 1
        u, v = tag.tag["offset"]
        assert u == pytest.approx(800.0, abs=1.0) and abs(v) <= 100.0     # at the click, on the wall
        assert tag.tag["leader"] is None                                  # Leader toggle off (default)
        assert scene.mode == "tag" and scene._move_ghost                  # stays armed   [RED]
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
        assert scene.mode in (None, "select") and not scene._move_ghost
    finally:
        close_view(view, scene)


def test_ac1_click_on_empty_space_places_nothing(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        _armed(view, scene)
        p0 = scene._undo_pos
        move(view, QPointF(800.0, 2500.0))
        click(view, QPointF(800.0, 2500.0))
        assert tags_of(scene) == [] and scene._undo_pos == p0
    finally:
        close_view(view, scene)


def test_ac1_leader_toggle_on_gives_new_tags_a_leader(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        _armed(view, scene)
        scene.tag_leader_on = True
        move(view, QPointF(800.0, 0.0))
        click(view, QPointF(800.0, 0.0))
        (tag,) = tags_of(scene)
        assert tag.tag["leader"] == LEADER                                # [RED] the Note default (D9)
        assert scene.get_block_definition(LEADER["end"]) is not None      # End loaded before placing
    finally:
        close_view(view, scene)


def test_gc3_hidden_wall_is_not_taggable(qapp, real_system_library):
    """A wall hidden (another level's) under the cursor gives no ghost and no tag."""
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = _armed(view, scene)
        move(view, QPointF(800.0, 0.0))
        assert scene._tag_ctl.find_host_at(QPointF(800.0, 0.0)) is w      # visible: taggable
        assert scene._move_ghost
        w.setVisible(False)
        move(view, QPointF(800.0, 500.0))                                 # off the wall: drops the ghost
        move(view, QPointF(800.0, 0.0))
        assert scene._tag_ctl.find_host_at(QPointF(800.0, 0.0)) is None   # [RED: _find_wall_at ignores visibility]
        assert not scene._move_ghost
        p0 = scene._undo_pos
        click(view, QPointF(800.0, 0.0))
        assert tags_of(scene) == [] and scene._undo_pos == p0
    finally:
        close_view(view, scene)


def _united_rect(paths):
    from PyQt6.QtCore import QRectF
    r = QRectF()
    for p in paths:
        r = r.united(p.boundingRect())
    return r


def test_d7_hover_ghost_is_traced_at_the_placed_tag_size(qapp, real_system_library):
    """Smoke S2: the off-scene ghost was traced at authored mm (~10 scene units, a
    sub-pixel dot at 1:100); it must match the tag the click then places."""
    from firepro3d.transform_ghost import ghost_base_paths
    view, scene = make_view(role="plan", scale=0.1)
    try:
        _armed(view, scene)
        assert scene.scale_manager.drawing_scale == pytest.approx(100.0)
        move(view, QPointF(800.0, 0.0))                                   # over the wall
        ghost = _united_rect(scene._move_ghost_base)
        click(view, QPointF(800.0, 0.0))
        (tag,) = tags_of(scene)
        placed = _united_rect(ghost_base_paths([tag]))
        assert placed.width() > 100.0 and placed.height() > 100.0
        assert ghost.width() == pytest.approx(placed.width(), rel=0.03)    # [RED: authored mm]
        assert ghost.height() == pytest.approx(placed.height(), rel=0.03)
    finally:
        close_view(view, scene)
