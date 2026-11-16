"""SB5 Task 3 -- G2 round-trip (AC1): one of each Q1 element keeps its uid
through .fpd save / load and undo / redo; sprinkler_uid != node uid."""
from tests._ph1_helpers import add_room, ph1_cleanup  # noqa: F401
from tests._sb5_helpers import FIND, managed_scene, one_of_each, save_load, uids


def _want(made):
    return {k: made[k]._uid for k in FIND}


def test_g2_every_q1_uid_survives_save_and_load(qapp, tmp_path):
    ms = managed_scene()
    made = one_of_each(ms)
    want = _want(made)
    assert len(set(want.values())) == len(want)           # all distinct; head != node
    out, raw = save_load(ms, tmp_path)
    assert uids(out) == want
    (rec,) = [n for n in raw["nodes"] if n.get("sprinkler")]
    assert rec["uid"] == want["node"] and rec["sprinkler_uid"] == want["sprinkler"]
    assert raw["pipes"][0]["uid"] == want["pipe"]
    assert raw["water_supply"]["uid"] == want["water_supply"]
    assert raw["design_areas"][0]["uid"] == want["design_area"]


def test_g2_every_q1_uid_survives_undo_and_redo(qapp):
    ms = managed_scene()
    made = one_of_each(ms)
    want = _want(made)
    ms.push_undo_state()
    add_room(ms)                                          # an unrelated step
    ms.push_undo_state()
    ms.undo()
    assert uids(ms) == want
    assert FIND["room"](ms) is not made["room"]           # rebuilt from the snapshot
    assert FIND["node"](ms) is not made["node"]
    ms.redo()
    assert uids(ms) == want                               # the first room stays first
