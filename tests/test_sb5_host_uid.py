"""SB5 Task 6 -- AC8 / Q10: element_host round-trips as host_uid through .fpd
save / load and undo / redo; a dangling host paints "?" and is counted once in
the load notice; a duplicated host uid resolves to the first loaded holder."""
import json

from tests._hosted_blocks_helpers import gridline
from tests._ph1_helpers import add_room, ph1_cleanup, save_raw, scene  # noqa: F401
from tests._sb5_helpers import bound_tag, door_scene, painted_values
from tests.test_sb2a_binding import _defs, _painted_as


def _tagged(ms):
    op = door_scene(ms)
    bound, ref = _defs(ms)
    inst = ms.place_block_instance(bound.id, (0.0, -1000.0))
    inst.element_host = op
    inst.refresh_bound()
    return op, inst, ref


def _status(ms):
    seen = []
    ms._show_status = lambda m, *a, **k: seen.append(m)
    return seen


def test_host_uid_round_trips_through_the_file(qapp, tmp_path):
    ms = scene()
    op, inst, _ref = _tagged(ms)
    assert inst.to_dict()["host_uid"] == op._uid
    path, raw = save_raw(ms, tmp_path)
    assert [b.get("host_uid") for b in raw["blocks"]] == [op._uid]
    out = scene()
    assert out.load_from_file(path)
    (inst2,) = out._block_instances
    assert inst2.element_host is out._walls[0].openings[0]
    assert painted_values(inst2)["R"] == "Office"


def test_host_uid_survives_undo_and_redo(qapp):
    ms = scene()
    op, inst, _ref = _tagged(ms)
    ms.push_undo_state()
    gridline(ms, (0, -9000), (6000, -9000), "Z")          # an unrelated step
    ms.push_undo_state()
    ms.undo()
    (inst2,) = ms._block_instances
    assert inst2 is not inst
    assert inst2.element_host is ms._walls[0].openings[0]
    ms.redo()
    (inst3,) = ms._block_instances
    assert inst3.element_host is ms._walls[0].openings[0]
    assert painted_values(inst3)["R"] == "Office"


def test_dangling_host_paints_placeholders_and_is_counted_once(qapp, tmp_path):
    ms = scene()
    _op, _inst, ref = _tagged(ms)
    path, raw = save_raw(ms, tmp_path)
    raw["blocks"][0]["host_uid"] = "f" * 32
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    out = scene()
    seen = _status(out)
    assert out.load_from_file(path)
    (inst2,) = out._block_instances
    assert inst2.host_values() is None
    ref2 = out.place_block_instance(ref.id, (0.0, -1000.0))
    assert _painted_as(inst2, ref2, {"W": "?", "R": "?", "N": "?"})
    hits = [m for m in seen if "hosted item(s) whose host is missing" in m]
    assert len(hits) == 1 and "1 hosted item(s) whose host is missing" in hits[0]
    _p2, raw2 = save_raw(out, tmp_path, "again.fpd")
    assert raw2["blocks"][0]["host_uid"] == "f" * 32      # kept and saved back unchanged


def test_duplicated_host_uid_resolves_to_the_first_loaded(qapp, tmp_path):
    ms = scene()
    first, second = add_room(ms), add_room(ms)
    first.name, second.name = "First", "Second"
    bound_tag(ms, first, "Room", {"N": "Name"})
    path, raw = save_raw(ms, tmp_path)
    raw["rooms"][1]["uid"] = raw["rooms"][0]["uid"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    out = scene()
    assert out.load_from_file(path)
    (inst2,) = out._block_instances
    assert inst2.element_host is out._rooms[0]
    assert painted_values(inst2)["N"] == "First"


def test_off_scene_and_uid_less_hosts_keep_the_cached_ref(qapp):
    from firepro3d.block_instance import BlockInstance
    ms = scene()
    op = door_scene(ms)
    bound, _ref = _defs(ms)
    loose = BlockInstance(block_id=bound.id, resolver=ms.get_block_definition)
    loose.element_host = op                                # never placed: cached ref
    assert loose.element_host is op and loose._host_uid == op._uid
    host = object()                                        # a host with no _uid
    loose.element_host = host
    assert loose._host_uid is None and loose.element_host is host
