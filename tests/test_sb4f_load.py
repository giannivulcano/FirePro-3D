"""SB4f D2 through the real load: an untouched pre-SB4f head copy takes the new
seed; an edited copy keeps Mark and earns one notice."""
import json

import pytest
from PyQt6.QtCore import QRectF

from tests._sb4d_helpers import dispose, plan_scene


def _old_copy(rec, *, version, base):
    """*rec* (a shipped-seed record) as a pre-SB4f project held it: top slot Mark."""
    rec = json.loads(json.dumps(rec))
    a = next(x for x in rec["attributes"] if x["host_key"] == "Number")
    a.update(key="Mark", label="Mark", host_key="Mark")
    next(p for p in rec["primitives"] if p.get("text") == "@[Number]")["text"] = "@[Mark]"
    rec["version"], rec["base_version"] = version, base
    return rec


def _project(ms, det, tmp_path, recs):
    """Save a real project, patch its head copies, return the file path."""
    det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
    path = tmp_path / "old.FPD"
    assert ms.save_to_file(str(path), backup=False) is not False
    payload = json.loads(path.read_text())
    payload.setdefault("block_definitions", {}).update(recs)
    path.write_text(json.dumps(payload))
    return str(path)


def _seed(bid):
    from firepro3d import block_library
    return block_library._find_by_id(bid, None)[3]["path"]


def _rec(bid):
    with open(_seed(bid), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("base", ["same", None])
def test_untouched_copy_takes_the_new_seed(qapp, real_system_library, tmp_path, base):
    bid = "system-tags-sectionhead"
    ms, sec, det, tabs = plan_scene()
    try:
        lib = _rec(bid)
        old = lib["version"] - 1
        rec = _old_copy(lib, version=old, base=old if base == "same" else None)
        if base is None:
            del rec["base_version"]
        path = _project(ms, det, tmp_path, {bid: rec})
        ms.load_from_file(path)
        d = ms._block_definitions[bid]
        assert d.version == lib["version"] and d.base_version == lib["version"]
        assert [a["host_key"] for a in d.effective_attributes()
                if a.get("source") == "host"] == ["Number", "Sheet"]
    finally:
        dispose(ms, sec, tabs)


def test_edited_copy_keeps_mark_and_gets_one_notice(qapp, real_system_library, tmp_path):
    bids = ("system-tags-sectionhead", "system-tags-detailcallout")
    ms, sec, det, tabs = plan_scene()
    seen = []
    try:
        recs = {}
        for bid in bids:
            lib = _rec(bid)
            recs[bid] = _old_copy(lib, version=lib["version"] + 1, base=lib["version"] - 1)
        path = _project(ms, det, tmp_path, recs)
        ms._show_status = lambda msg, *a: seen.append(msg)
        ms.load_from_file(path)
        for bid in bids:
            assert [a["host_key"] for a in ms._block_definitions[bid].effective_attributes()
                    if a.get("source") == "host"] == ["Mark", "Sheet"]
        notices = [m for m in seen if "keep Mark" in m]
        assert len(notices) == 1 and "2 edited" in notices[0]
    finally:
        dispose(ms, sec, tabs)


def test_edited_copy_on_number_is_silent(qapp, real_system_library, tmp_path):
    bid = "system-tags-detailcallout"
    ms, sec, det, tabs = plan_scene()
    seen = []
    try:
        lib = _rec(bid)
        rec = json.loads(json.dumps(lib))
        rec["version"], rec["base_version"] = lib["version"] + 1, lib["version"]
        path = _project(ms, det, tmp_path, {bid: rec})
        ms._show_status = lambda msg, *a: seen.append(msg)
        ms.load_from_file(path)
        assert ms._block_definitions[bid].version == lib["version"] + 1
        assert not [m for m in seen if "keep Mark" in m]
    finally:
        dispose(ms, sec, tabs)
