"""SB6 AC7 (record half) -- the tag record seam: sparse to_dict, place_kwargs,
place_block_instance(tag=), from_dict normalise, save / load and undo / redo of
host_uid + tag, a dangling host on load ("?" + the SB5 load notice)."""
import json

from tests._ph1_helpers import ph1_cleanup, save_raw  # noqa: F401
from tests._sb5_helpers import managed_scene, save_load
from tests._sb6_helpers import add_door, add_wall, tags_of

REC = {"offset": [500.0, -800.0], "orientation": "aligned",
       "leader": {"edge": "T", "t": 0.25, "shoulder_mm": 9.0, "tip": [100.0, -300.0],
                  "end": "none", "weight": "Thin"}, "block": None}


def _tag(ms, host):
    from firepro3d import element_params
    d = ms.annotation_block(element_params.category_of(host))
    return ms.place_block_instance(d.id, (500.0, -800.0), level=host.level,
                                   host_uid=host._uid, tag=json.loads(json.dumps(REC)))


def _key(b):
    return (b._host_uid, json.dumps(b.tag, sort_keys=True))


def test_record_is_sparse_and_carried(qapp, real_system_library):
    from firepro3d.block_instance import BlockInstance
    ms = managed_scene()
    w = add_wall(ms)
    t = _tag(ms, w)
    d = t.to_dict()
    assert d["tag"] == REC and d["host_uid"] == w._uid
    assert BlockInstance.place_kwargs(d)["tag"] == REC
    d["tag"]["offset"][0] = 9.0
    assert t.tag["offset"][0] == 500.0                     # to_dict hands out a copy
    plain = ms.place_block_instance(t.block_id, (0.0, 0.0))
    assert "tag" not in plain.to_dict()                    # sparse
    assert BlockInstance.place_kwargs(plain.to_dict())["tag"] is None


def test_from_dict_normalises_a_stored_record(qapp):
    from firepro3d.block_instance import BlockInstance
    inst = BlockInstance.from_dict({"block_id": "x", "tag": {"offset": [1, 2], "orientation": "?"}},
                                   resolver=lambda _i: None)
    assert inst.tag == {"offset": [1.0, 2.0], "orientation": "horizontal",
                        "leader": None, "block": None}
    bad = BlockInstance.from_dict({"block_id": "x", "tag": {"offset": None}},
                                  resolver=lambda _i: None)
    assert bad.tag is None


def test_save_load_round_trips_host_uid_and_record(qapp, tmp_path, real_system_library):
    ms = managed_scene()
    w = add_wall(ms)
    op = add_door(ms, w)
    _tag(ms, w)
    _tag(ms, op)
    want = sorted(_key(b) for b in tags_of(ms))
    out, _raw = save_load(ms, tmp_path)
    assert sorted(_key(b) for b in tags_of(out)) == want
    hosts = {b._host_uid: b.element_host for b in tags_of(out)}
    assert hosts[w._uid] is out._walls[0]
    assert hosts[op._uid] is out._walls[0].openings[0]


def test_undo_redo_round_trips_the_record(qapp, real_system_library):
    ms = managed_scene()
    add_wall(ms)
    ms.push_undo_state()
    _tag(ms, ms._walls[0])
    ms.push_undo_state()
    want = _key(tags_of(ms)[0])
    ms.undo()
    assert tags_of(ms) == []
    ms.redo()
    (t,) = tags_of(ms)
    assert _key(t) == want
    assert t.element_host is ms._walls[0]


def test_dangling_host_on_load_draws_placeholder_with_the_notice(qapp, tmp_path, real_system_library):
    from tests.test_sb2a_binding import _painted_as
    ms = managed_scene()
    _tag(ms, add_wall(ms))
    path, raw = save_raw(ms, tmp_path)
    raw["walls"] = []                                       # the host is gone from the file
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    out = managed_scene()
    seen = []
    out._show_status = lambda m, *a, **k: seen.append(m)
    assert out.load_from_file(path)
    (t,) = tags_of(out)
    assert t.element_host is None
    ref = out.place_block_instance(t.block_id, t.block_pos(), rotation=t.block_rotation())
    assert _painted_as(t, ref, {"Mark": "?"})              # the shipped Mark placeholder (Task 1 files)
    assert any("1 hosted item(s) whose host is missing" in m for m in seen)   # scene_io.py:613
