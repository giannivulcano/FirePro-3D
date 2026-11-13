"""SB5 Task 5 -- G-dup (Q6, AC5): a file with duplicate uids loads with one
notice, unique uids, and the first loaded holder keeps the uid."""
import json

from tests._ph1_helpers import add_room, ph1_cleanup, save_raw, scene  # noqa: F401


def _status(ms):
    seen = []
    ms._show_status = lambda m, *a, **k: seen.append(m)
    return seen


def test_g_dup_duplicate_uids_repaired_with_one_notice(qapp, tmp_path):
    ms = scene()
    first, second = add_room(ms), add_room(ms)
    second.name = "Second"
    path, raw = save_raw(ms, tmp_path)
    raw["rooms"][1]["uid"] = raw["rooms"][0]["uid"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)
    out = scene()
    seen = _status(out)
    assert out.load_from_file(path)
    r0, r1 = out._rooms
    assert r0._uid == first._uid
    assert r1._uid != first._uid and len(r1._uid) == 32
    assert out.element_by_uid(first._uid) is r0           # resolves to the first
    hits = [m for m in seen if "duplicate element ids repaired" in m]
    assert len(hits) == 1 and "1 duplicate element ids repaired" in hits[0]


def test_a_clean_file_shows_no_repair_notice(qapp, tmp_path):
    ms = scene()
    add_room(ms)
    path, _raw = save_raw(ms, tmp_path)
    out = scene()
    seen = _status(out)
    assert out.load_from_file(path)
    assert not any("duplicate element ids" in m for m in seen)
