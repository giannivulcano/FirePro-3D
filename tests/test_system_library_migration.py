"""SB1b G4 -- startup migration (design D5)."""
import hashlib
import json
import os
import shutil

from PyQt6.QtCore import QSettings

from firepro3d import app_data
from firepro3d.app_data import HATCH_DIR_KEY, block_library_dir
from firepro3d.hatch_patterns import (HATCH_SEEDED_KEY, library_patterns,
                                      shipped_pattern_files)
from firepro3d.system_library import migrate_user_library


def _tree(base):
    out = {}
    for d, _s, fs in os.walk(base):
        for f in fs:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, base)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def _seed_like_hf2(base):
    """What D-A39 seeding left on disk: five copies + the seeded key."""
    hatch = os.path.join(base, "System", "Hatches")
    os.makedirs(hatch)
    for _bid, src in shipped_pattern_files():
        shutil.copyfile(src, os.path.join(hatch, os.path.basename(src)))
    os.makedirs(os.path.join(base, "System", "Linetypes"))
    with open(os.path.join(base, "System", "Linetypes", "Mine.fpdb"), "w") as fh:
        json.dump({"id": "user-lt", "version": 1, "name": "Mine",
                   "library": "System", "series": "Linetypes"}, fh)
    QSettings("GV", "FirePro3D").setValue(
        HATCH_SEEDED_KEY, [os.path.normcase(os.path.abspath(hatch))])
    return hatch


def _edit(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["version"] = 2                   # an in-place edit the user saved
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def test_g4_migration_cleans_reids_and_moves():
    base = block_library_dir()
    hatch = _seed_like_hf2(base)
    _edit(os.path.join(hatch, "Diagonal.fpdb"))
    migrate_user_library()
    assert not os.path.exists(os.path.join(base, "System"))
    styles_hatch = os.path.join(base, "Styles", "Hatches")
    assert sorted(os.listdir(styles_hatch)) == ["Diagonal.fpdb"]
    with open(os.path.join(styles_hatch, "Diagonal.fpdb"), encoding="utf-8") as fh:
        kept = json.load(fh)
    assert kept["id"] != "builtin-hatch-diagonal" and kept["version"] == 2
    assert kept["library"] == "Styles"                 # reserved name left behind
    mine = os.path.join(base, "Styles", "Linetypes", "Mine.fpdb")
    with open(mine, encoding="utf-8") as fh:
        assert json.load(fh)["library"] == "Styles"
    assert not QSettings("GV", "FirePro3D").value(HATCH_SEEDED_KEY, [])
    assert app_data.hatch_patterns_dir() == styles_hatch
    assert [bid for _n, bid, _p in library_patterns()] == [kept["id"]]


def test_g4_second_run_changes_nothing():
    base = block_library_dir()
    _seed_like_hf2(base)
    migrate_user_library()
    before = _tree(base)
    migrate_user_library()
    assert _tree(base) == before


def test_g4_override_into_system_is_never_moved(tmp_path):
    base = block_library_dir()
    hatch = os.path.join(base, "System", "Hatches")
    os.makedirs(hatch)
    QSettings("GV", "FirePro3D").setValue(HATCH_DIR_KEY, hatch)
    migrate_user_library()
    assert os.path.isdir(hatch)
    assert not os.path.exists(os.path.join(base, "Styles"))


def test_g4_existing_styles_never_overwritten():
    base = block_library_dir()
    _seed_like_hf2(base)
    os.makedirs(os.path.join(base, "Styles", "Linetypes"))
    clash = os.path.join(base, "Styles", "Linetypes", "Mine.fpdb")
    with open(clash, "w") as fh:
        fh.write("{}")
    migrate_user_library()
    with open(clash) as fh:
        assert fh.read() == "{}"                       # untouched
    assert os.path.isfile(os.path.join(base, "System", "Linetypes", "Mine.fpdb"))


def test_g4_vanished_seeded_folder_is_skipped_and_key_clears():
    gone = os.path.join(block_library_dir(), "Nowhere", "Hatches")
    QSettings("GV", "FirePro3D").setValue(
        HATCH_SEEDED_KEY, [os.path.normcase(os.path.abspath(gone))])
    migrate_user_library()
    assert not QSettings("GV", "FirePro3D").value(HATCH_SEEDED_KEY, [])


def test_g4_migrated_files_load_raw_and_save_back(tmp_path, qapp):
    """A file opened outside a scanned root keeps its meta library (from_dict),
    so a leftover "System" would refuse the save (SystemLibraryReadOnly)."""
    from firepro3d import block_library as bl
    base = block_library_dir()
    _seed_like_hf2(base)
    brick = dict(shipped_pattern_files())["builtin-hatch-brick"]
    with open(brick, encoding="utf-8") as fh:
        data = json.load(fh)
    data["id"] = "user-moved"                          # a user block in System/
    with open(os.path.join(base, "System", "Linetypes", "Moved.fpdb"), "w",
              encoding="utf-8") as fh:
        json.dump(data, fh)
    outside = tmp_path / "Override" / "Hatches"        # seeded outside the root
    outside.mkdir(parents=True)
    shutil.copyfile(brick, outside / "Brick.fpdb")
    _edit(str(outside / "Brick.fpdb"))
    QSettings("GV", "FirePro3D").setValue(
        HATCH_SEEDED_KEY, [os.path.normcase(os.path.abspath(str(outside)))])
    migrate_user_library()
    for path in (os.path.join(base, "Styles", "Linetypes", "Moved.fpdb"),
                 str(outside / "Brick.fpdb")):
        defn, _bundled = bl.load_block_file_with_bundle(path)
        assert bl.save_to_library(defn, root=base, overwrite=True)


def test_g4_per_file_merge_restamps_and_keeps_empty_series():
    base = block_library_dir()
    _seed_like_hf2(base)
    os.makedirs(os.path.join(base, "System", "End Types"))   # empty series
    os.makedirs(os.path.join(base, "Styles"))                # forces the per-file path
    migrate_user_library()
    assert os.path.isdir(os.path.join(base, "Styles", "End Types"))
    with open(os.path.join(base, "Styles", "Linetypes", "Mine.fpdb"),
              encoding="utf-8") as fh:
        assert json.load(fh)["library"] == "Styles"


def test_g4_failing_move_never_raises(monkeypatch):
    base = block_library_dir()
    _seed_like_hf2(base)

    def _locked(*_a, **_k):
        raise PermissionError("locked")
    monkeypatch.setattr(os, "replace", _locked)
    migrate_user_library()                                   # no exception
    assert os.path.isfile(os.path.join(base, "System", "Linetypes", "Mine.fpdb"))


def test_g4_unreadable_seeded_copy_keeps_the_key_for_a_retry(monkeypatch):
    from firepro3d import system_library
    base = block_library_dir()
    hatch = _seed_like_hf2(base)
    _edit(os.path.join(hatch, "Diagonal.fpdb"))

    def _corrupt(_path):
        raise ValueError("bad json")
    monkeypatch.setattr(system_library, "_reid", _corrupt)
    migrate_user_library()
    assert QSettings("GV", "FirePro3D").value(HATCH_SEEDED_KEY, [])


def test_g4_reid_outside_system_drops_the_reserved_library():
    base = block_library_dir()
    hatch = os.path.join(base, "Mine", "Hatches")         # seeded via an override
    os.makedirs(hatch)
    for _bid, src in shipped_pattern_files():
        shutil.copyfile(src, os.path.join(hatch, os.path.basename(src)))
    QSettings("GV", "FirePro3D").setValue(
        HATCH_SEEDED_KEY, [os.path.normcase(os.path.abspath(hatch))])
    _edit(os.path.join(hatch, "Diagonal.fpdb"))
    migrate_user_library()
    with open(os.path.join(hatch, "Diagonal.fpdb"), encoding="utf-8") as fh:
        assert json.load(fh)["library"] == "Styles"
