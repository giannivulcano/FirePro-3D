"""SB4d D5: Qt child z is local to its parent, so the room tag and the
hydraulic node badge become TOP-LEVEL items synced by their host (the SB4a
pipe-label pattern): position on move, z in the tag band, visibility with
the host, removal with the host."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.constants import Z_ANNOT_TAG
from tests._sb4d_helpers import dispose, plan_scene, wall


def _room(ms):
    from firepro3d.room import Room
    r = Room([QPointF(0, 0), QPointF(6000, 0), QPointF(6000, 4000), QPointF(0, 4000)])
    r.level = "Level 1"
    r.name = "Office"
    ms.addItem(r)
    ms._rooms.append(r)
    return r


def test_room_tag_is_top_level_in_the_tag_band_and_follows_the_room(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        tall = wall(ms, top_offset=20000.0, y=2000.0)         # 200.3, crosses the centroid
        r = _room(ms)
        tag = r._tag
        assert tag.parentItem() is None and tag.scene() is ms
        assert tag.host is r
        assert tag.pos() == QPointF(3000.0, 2000.0)             # centroid
        ms._level_manager.apply_to_scene(ms)
        assert tag.zValue() == Z_ANNOT_TAG > tall.zValue()
        r.translate(1000.0, 0.0)
        assert tag.pos() == QPointF(4000.0, 2000.0)
        r.setVisible(False)
        assert not tag.isVisible()
        r.setVisible(True)
        assert tag.isVisible()
        r.setOpacity(0.4)
        assert tag.opacity() == pytest.approx(0.4)
        ms.removeItem(r)
        assert tag.scene() is None
        ms.addItem(r)
        assert tag.scene() is ms
    finally:
        dispose(ms, sec, tabs)


def test_badge_is_top_level_in_the_tag_band_and_follows_its_node(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        n = ms.add_node(1000.0, 1000.0)
        n.create_hydraulic_badge(1, 50.0, 40.0, 10.0, 10.0)      # position "Right"
        b = n._hydraulic_badge
        from firepro3d.hydraulic_node_badge import _POSITION_OFFSETS
        assert b.parentItem() is None and b.scene() is ms
        assert b.zValue() == Z_ANNOT_TAG
        assert b.pos() == n.scenePos() + _POSITION_OFFSETS["Right"]
        n.setPos(2000.0, 1500.0)
        assert b.pos() == QPointF(2000.0, 1500.0) + _POSITION_OFFSETS["Right"]
        n.setVisible(False)
        assert not b.isVisible()
        n.setVisible(True)
        assert b.isVisible()
        ms.removeItem(n)
        assert b.scene() is None
        ms.addItem(n)
        n.remove_hydraulic_badge()
        assert n._hydraulic_badge is None and b.scene() is None
    finally:
        dispose(ms, sec, tabs)


def _badged_node(ms):
    n = ms.add_node(1000.0, 1000.0)
    n.create_hydraulic_badge(1, 50.0, 40.0, 10.0, 10.0)
    return n, n._hydraulic_badge


def test_badge_takes_the_node_opacity(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        n, b = _badged_node(ms)
        n.setOpacity(0.4)
        assert b.opacity() == pytest.approx(0.4)
        n.create_hydraulic_badge(2, 50.0, 40.0, 10.0, 10.0)      # a new badge copies it
        assert n._hydraulic_badge.opacity() == pytest.approx(0.4)
        ms.removeItem(n)
        n.setOpacity(0.7)
        ms.addItem(n)                                            # re-added badge copies it
        assert n._hydraulic_badge.opacity() == pytest.approx(0.7)
    finally:
        dispose(ms, sec, tabs)


def test_dm_hidden_badge_stays_hidden_when_the_node_toggles(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        n, b = _badged_node(ms)
        b._display_overrides["visible"] = False
        b.setVisible(False)
        n.setVisible(False)
        n.setVisible(True)
        assert not b.isVisible()
    finally:
        dispose(ms, sec, tabs)


def test_dm_row_visible_does_not_show_a_badge_of_a_hidden_node(qapp):
    from firepro3d.display_manager import _apply_vals_to_item
    ms, sec, det, tabs = plan_scene()
    try:
        n, b = _badged_node(ms)
        n.setVisible(False)
        vals = {"color": "#ffffff", "fill": "#2b2b2b", "scale": 1.0,
                "opacity": 100, "visible": True, "font": None}
        _apply_vals_to_item(b, vals, key="Hydraulic Badge")
        assert not b.isVisible()
        n.setVisible(True)
        assert b.isVisible()
    finally:
        dispose(ms, sec, tabs)


def test_show_all_hidden_leaves_the_badge_of_a_hidden_node_hidden(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        n, b = _badged_node(ms)
        b._display_overrides["visible"] = False
        b.setVisible(False)
        n.level = "Level 2"                  # off the active level: the level pass keeps it hidden
        n.setVisible(False)
        ms._show_all_hidden()
        assert not n.isVisible()
        assert not b.isVisible()
        assert "visible" not in b._display_overrides
    finally:
        dispose(ms, sec, tabs)
