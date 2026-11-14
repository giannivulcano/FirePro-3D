"""SB5 Task 10 -- G-cascade (Q8, Q11, Q13; AC7) and G-DA (Q14a; AC9).

Each final-removal path takes the removed host's dependents along in the same
undo step; one Undo restores host + dependents re-linked by uid. Deleting a
sprinkler (Delete or re-populate) drops it from its design area's membership
in the same step."""
from types import SimpleNamespace

from PyQt6.QtCore import QPointF

from tests._ph1_helpers import add_room, ph1_cleanup, scene  # noqa: F401
from tests._sb5_helpers import (add_design_area, bound_tag, door_scene,
                                managed_scene, painted_values)
from tests.test_sb3b_room_tag_style import _add_room

REC = SimpleNamespace(manufacturer="Tyco", model="", type="Upright", k_factor=5.6,
                      coverage_area=130, min_pressure=7, temp_rating=155)


def _status(ms):
    seen = []
    ms._show_status = lambda m, *a, **k: seen.append(m)
    return seen


def test_delete_cascades_bound_dependents_in_one_undo_step(qapp):
    ms = scene()
    op = door_scene(ms)
    tag = bound_tag(ms, op, "Door", {"R": "Room.Name"}, pos=(2000.0, -500.0))
    ms.push_undo_state()
    seen = _status(ms)
    p0 = ms._undo_pos
    ms.delete_items([op.wall])                            # the door goes with its wall
    assert tag.scene() is None and ms._block_instances == []
    assert seen[-1] == "Deleted 1 item(s) and 1 hosted item(s)"
    assert ms._undo_pos == p0 + 1
    ms.undo()
    (back,) = ms._block_instances
    assert back.element_host is ms._walls[0].openings[0]
    assert back.host_values() is not None and painted_values(back)["R"] == "Office"


def test_gridline_only_cascade_keeps_the_gridline_wording(qapp):
    from tests._hosted_blocks_helpers import defn, gridline
    ms = scene()
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    ms.place_block_instance(defn(ms).id, (0, 0), host={
        "gridline": gl._uid, "offset_mm": 0.0, "along_mm": 1000.0,
        "elevation_mm": 0.0, "facing": 1})
    ms.push_undo_state()
    seen = _status(ms)
    ms.delete_items([gl])
    assert seen[-1] == "Deleted gridline B and 1 hosted block(s)"


def test_cut_cascades_with_the_generic_status(qapp):
    from tests._snap_polish_helpers import click, close_view, make_view
    view, ms = make_view(role="plan", scale=1.0)
    try:
        ms.push_undo_state()
        room = add_room(ms)
        tag = bound_tag(ms, room, "Room", {"N": "Name"}, pos=(1500.0, -500.0))
        ms.push_undo_state()
        seen = _status(ms)
        room.setSelected(True)
        p0 = ms._undo_pos
        assert ms._modify_ctl.start("cut")
        click(view, QPointF(-300, -300))                  # the base click commits Cut
        assert room not in ms._rooms and tag.scene() is None
        assert seen[-1] == "Cut 1 item(s) and 1 hosted item(s)"
        assert ms._undo_pos == p0 + 1
        ms.undo()
        (back,) = ms._block_instances
        assert back.element_host is ms._rooms[0]
    finally:
        close_view(view, ms)


def test_repopulate_cascades_and_drops_design_area_membership(qapp):
    ms = scene()
    room = _add_room(ms, "Office")
    n = ms.add_node(500.0, 500.0)
    n._room_name = "Office"
    spr = ms.add_sprinkler(n)
    keep = ms.add_sprinkler(ms.add_node(9000.0, 9000.0))  # outside the room
    da = add_design_area(ms, [spr, keep])
    tag = bound_tag(ms, spr, "Sprinkler", {"K": "KFactor"}, pos=(500.0, -500.0))
    ms.push_undo_state()
    ms.auto_populate_room(room, [QPointF(1500.0, 1500.0)], REC,
                          "Level 1", "Level 1", -50.8)
    assert tag.scene() is None
    assert spr not in da.sprinklers and da.sprinklers == [keep]
    ms.undo()                                             # re-populate's own pre-step snapshot
    (back,) = ms._block_instances
    assert back.element_host is not None and back.host_values() is not None
    assert len(ms.design_areas[0].sprinklers) == 2


def test_collinear_extend_cascades_the_removed_node_dependents(qapp, shown_model_view):
    view, ms = shown_model_view
    ms.set_mode("pipe")
    ms._pipe_ctl.press_pipe(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    ms._pipe_ctl._commit_pipe_at(QPointF(1000, 0), None)
    mid = ms.pipe_start_node
    tag = bound_tag(ms, mid, "Hydraulic Node", {"F": "Flow"}, pos=(1000.0, -500.0))
    ms.push_undo_state()
    p0 = ms._undo_pos
    ms._pipe_ctl._commit_pipe_at(QPointF(2000, 0), None)  # collinear: extends, removes mid
    assert mid.scene() is None
    assert tag.scene() is None
    assert ms._undo_pos == p0 + 1
    ms.set_mode(None)
    ms.undo()
    (back,) = ms._block_instances
    host = back.element_host
    assert host is not None and host.scenePos() == QPointF(1000, 0)


def test_section_delete_cascades_in_one_undo_step(qapp):
    ms = managed_scene()
    ms.push_undo_state()
    mgr = ms._section_manager
    m = mgr.place_section(QPointF(0, 0), QPointF(5000, 0))
    ms.push_undo_state()
    tag = bound_tag(ms, m, "Section", {"K": "Mark"}, pos=(0.0, -1500.0))
    ms.push_undo_state()
    p0 = ms._undo_pos
    m._delete_with_undo()                                 # the marker menu's Delete
    assert "Section 1" not in mgr.markers and tag.scene() is None
    assert ms._undo_pos == p0 + 1
    ms.undo()
    m2 = mgr.markers["Section 1"]
    (back,) = ms._block_instances
    assert m2._uid == m._uid and back.element_host is m2


def test_g_da_delete_drops_the_sprinkler_from_its_area_one_undo(qapp):
    ms = scene()
    n1 = ms.add_node(0.0, 0.0)
    s1 = ms.add_sprinkler(n1)
    s2 = ms.add_sprinkler(ms.add_node(3000.0, 0.0))
    da = add_design_area(ms, [s1, s2])
    ms.push_undo_state()
    seen = _status(ms)
    ms.delete_items([n1])
    assert da.sprinklers == [s2]
    assert seen[-1] == "Deleted 1 item(s)"                 # membership is not a hosted item
    ms.undo()
    assert len(ms.design_areas[0].sprinklers) == 2
