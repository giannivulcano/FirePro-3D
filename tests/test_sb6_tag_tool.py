"""SB6 AC1 / D7 -- the Tag tool through posted mouse events on a shown plan view.
Raw scene: wall (-2000,0)-(2000,0), 200 mm thick (band |y| <= 100 scene at ppm 1 and
1:100); door_914 at offset_along 1000 -> centre (-1000, 0), 914 wide."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from tests._sb6_helpers import add_door, add_wall, tags_of
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
        assert tag.tag["leader"] == {"knee": None}                        # [RED]
        from firepro3d.paper_display import tag_leader_end
        assert scene.get_block_definition(tag_leader_end()) is not None   # End loaded before placing
    finally:
        close_view(view, scene)
