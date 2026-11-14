"""SB5 Task 8 -- G-paste (Q9), AC2 (copies mint), AC11 (every skip reason).

Paths: the real Copy -> Paste commit (write_clipboard / begin_paste /
commit_paste), Duplicate (commit_duplicate) and Copy to Level
(copy_items_to_level). Offset / Mirror copy no Q1 element (Plan delta 9;
their 2D / block re-mint stays guarded by tests/test_primitive_uid.py).
"""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d.constants import HOSTED_HOST_GONE, WATER_SUPPLY_ONE
from tests._hosted_blocks_helpers import defn, gridline
from tests._ph1_helpers import add_water_supply, ph1_cleanup, scene  # noqa: F401
from tests._sb5_helpers import (add_design_area, all_q1, bound_tag, door_scene,
                                one_of_each)


def _status(ms):
    seen = []
    ms._show_status = lambda m, *a, **k: seen.append(m)
    return seen


def _paste(ms, items, dy=8000.0):
    """Copy *items* (base at the origin) and commit one Paste at +dy."""
    ctl = ms._modify_ctl
    assert ctl.write_clipboard(items, QPointF(0.0, 0.0))
    assert ctl.begin_paste()
    ctl.commit_paste(QPointF(0.0, dy))


def _tops(made):
    return [made[k] for k in ("room", "floor_slab", "roof", "wall", "node_a",
                              "node", "design_area")]


@pytest.mark.parametrize("path", ["paste", "duplicate"])
def test_ac2_copies_mint_new_uids_for_every_q1_element(qapp, path):
    ms = scene()
    made = one_of_each(ms)
    ms.removeItem(made["water_supply"])                   # one per project (R5): own test below
    ms.water_supply_node = None
    ms.sprinkler_system.supply_node = None
    src = {it._uid for it in all_q1(ms)}
    if path == "paste":
        _paste(ms, _tops(made))
    else:
        ms.clearSelection()
        ms._selected_items = _tops(made)
        ms._modify_ctl.commit_duplicate(QPointF(0.0, 8000.0))
    q1 = all_q1(ms)
    assert len(q1) == 2 * len(src)                         # every element copied once
    assert len({it._uid for it in q1}) == len(q1)          # all distinct
    assert ms._uid_repairs == 0                            # copies never reached the repair


def test_ac2_copy_to_level_mints(qapp):
    ms = scene()
    made = one_of_each(ms)
    ms._level_manager.add_level("Level 2", 3000.0)
    src = {it._uid for it in (made["room"], made["floor_slab"], made["floor_opening"],
                              made["roof"], made["opening"])}
    ms.copy_items_to_level([made["room"], made["floor_slab"], made["roof"], made["wall"]],
                           "Level 2")
    copies = [ms._rooms[1], ms._floor_slabs[1], ms._floor_slabs[1].openings[0],
              ms._roofs[1], ms._walls[1].openings[0]]
    assert not ({c._uid for c in copies} & src)
    assert ms._uid_repairs == 0


def test_ac2_water_supply_paste_mints(qapp):
    ms = scene()
    ws = add_water_supply(ms)
    ctl = ms._modify_ctl
    assert ctl.write_clipboard([ws], QPointF(0.0, 0.0))
    ms.delete_items([ws])
    assert ctl.begin_paste()
    ctl.commit_paste(QPointF(0.0, 3000.0))
    assert ms.water_supply_node is not None and ms.water_supply_node._uid != ws._uid


def test_g_paste_host_and_bound_dependent_together_rebind(qapp):
    ms = scene()
    op = door_scene(ms)
    tag = bound_tag(ms, op, "Door", {"R": "Room.Name"}, pos=(2000.0, -500.0))
    _paste(ms, [op.wall, tag])
    new_tag = next(b for b in ms._block_instances if b is not tag)
    new_door = next(o for w in ms._walls for o in w.openings if o is not op)
    assert new_tag.element_host is new_door
    assert new_tag._host_uid == new_door._uid and new_door._uid != op._uid
    assert tag.element_host is op                          # the source keeps its host


def test_g_paste_tag_on_a_node_made_as_a_pipe_far_end_rebinds(qapp):
    """Records [a, b, tag]: a's pipe creates b' before b's record runs, which
    then reuses b' through find_nearby_node -- b' is still b's copy (Q9)."""
    ms = scene()
    a = ms.add_node(0.0, 5000.0)
    b = ms.add_node(1000.0, 5000.0)
    ms.add_pipe(a, b)
    tag = bound_tag(ms, b, "Hydraulic Node", {"N": "NodeNumber"}, pos=(1000.0, 4500.0))
    before = set(ms.sprinkler_system.nodes)
    _paste(ms, [a, b, tag])
    new_tag = next(x for x in ms._block_instances if x is not tag)
    new_nodes = [n for n in ms.sprinkler_system.nodes if n not in before]
    assert new_tag.element_host in new_nodes and new_tag.element_host is not b
    assert tag.element_host is b


def test_g_paste_gridline_and_hosted_block_together_rebind(qapp):
    ms = scene()
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    blk = ms.place_block_instance(defn(ms).id, (0, 0), host={
        "gridline": gl._uid, "offset_mm": 0.0, "along_mm": 1500.0,
        "elevation_mm": 0.0, "facing": 1})
    _paste(ms, [gl, blk])
    new_gl = next(g for g in ms._gridlines if g is not gl)
    new_blk = next(b for b in ms._block_instances if b is not blk)
    assert new_blk.host["gridline"] == new_gl._uid
    assert ms.hosted_blocks_on(new_gl) == [new_blk]
    assert ms.hosted_blocks_on(gl) == [blk]


def test_g_paste_dependent_alone_stays_on_its_original_host(qapp):
    ms = scene()
    op = door_scene(ms)
    tag = bound_tag(ms, op, "Door", {"R": "Room.Name"}, pos=(2000.0, -500.0))
    _paste(ms, [tag])
    new_tag = next(b for b in ms._block_instances if b is not tag)
    assert new_tag.element_host is op


def test_g_paste_dependent_whose_host_is_gone_is_skipped_with_the_reason(qapp):
    ms = scene()
    op = door_scene(ms)
    tag = bound_tag(ms, op, "Door", {"R": "Room.Name"}, pos=(2000.0, -500.0))
    ctl = ms._modify_ctl
    assert ctl.write_clipboard([tag], QPointF(0.0, 0.0))
    ms.delete_items([op.wall, tag])
    seen = _status(ms)
    assert ctl.begin_paste()
    ctl.commit_paste(QPointF(0.0, 8000.0))
    assert ms._block_instances == []
    assert HOSTED_HOST_GONE.format(n=1) in seen[-1]


def test_ac11_footer_lists_every_skip_reason(qapp):
    ms = scene()
    ws = add_water_supply(ms)                              # a second one is refused (R5)
    op = door_scene(ms)
    tag = bound_tag(ms, op, "Door", {"R": "Room.Name"}, pos=(2000.0, -500.0))
    spr = ms.add_sprinkler(ms.add_node(0.0, 9000.0))
    da = add_design_area(ms, [spr])                        # copied without its sprinkler
    ctl = ms._modify_ctl
    assert ctl.write_clipboard([ws, da, tag], QPointF(0.0, 0.0))
    ms.delete_items([op.wall])                             # the tag's host is gone
    seen = _status(ms)
    assert ctl.begin_paste()
    ctl.commit_paste(QPointF(0.0, 8000.0))
    final = seen[-1]
    assert WATER_SUPPLY_ONE in final
    assert "1 design area(s) skipped - their sprinklers were not copied" in final
    assert HOSTED_HOST_GONE.format(n=1) in final


def _gl_hosted(ms):
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    blk = ms.place_block_instance(defn(ms).id, (0, 0), host={
        "gridline": gl._uid, "offset_mm": 0.0, "along_mm": 1500.0,
        "elevation_mm": 0.0, "facing": 1})
    return gl, blk


def test_g_paste_gridline_hosted_block_alone_stays_on_its_original_gridline(qapp):
    ms = scene()
    gl, blk = _gl_hosted(ms)
    _paste(ms, [blk])
    new_blk = next(b for b in ms._block_instances if b is not blk)
    assert new_blk.host["gridline"] == gl._uid
    assert set(ms.hosted_blocks_on(gl)) == {blk, new_blk}
    assert len(ms._gridlines) == 1                         # the gridline itself was not copied


def test_g_paste_gridline_hosted_block_alone_whose_gridline_left_the_list_is_skipped(qapp):
    """The liveness check is gridline_by_uid (needs membership in _gridlines),
    the same lookup placement uses: a gridline still in the scene but dropped
    from _gridlines is host-gone, not silently dropped without the reason."""
    ms = scene()
    gl, blk = _gl_hosted(ms)
    ctl = ms._modify_ctl
    assert ctl.write_clipboard([blk], QPointF(0.0, 0.0))
    ms._gridlines.remove(gl)                               # still in the scene / uid index
    assert ms.element_by_uid(gl._uid) is gl and ms.gridline_by_uid(gl._uid) is None
    seen = _status(ms)
    assert ctl.begin_paste()
    ctl.commit_paste(QPointF(0.0, 8000.0))
    assert ms._block_instances == [blk]
    assert HOSTED_HOST_GONE.format(n=1) in seen[-1]
