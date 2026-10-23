"""SB1b -- System library tier guards (design 2026-10-22, G1/G6/G9, D2)."""
import hashlib
import os
import shutil

import pytest

from firepro3d import block_library as bl
from firepro3d.block_definition import BlockDefinition


def _defn(name="Probe", library="Mine", series="Set"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[], origin=(0.0, 0.0))


def test_base_version_round_trips():
    d = _defn()
    d.base_version = 4
    assert d.to_dict()["base_version"] == 4
    assert BlockDefinition.from_dict(d.to_dict()).base_version == 4


def test_missing_base_version_reads_none_and_is_not_written():
    d = _defn()
    assert d.base_version is None
    rec = d.to_dict()
    assert "base_version" not in rec            # byte-identical for old defs
    assert BlockDefinition.from_dict(rec).base_version is None


SHIPPED = ["Brick", "Concrete", "Cross Hatch", "Diagonal", "Horizontal"]


def _digests(root):
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def _user_fpdb(root):
    return [os.path.join(d, f) for d, _s, fs in os.walk(root)
            for f in fs if f.endswith(".fpdb")]


def test_system_tier_lists_shipped_hatches(real_system_library):
    sys_entries = [e for e in bl.list_library() if e["tier"] == "system"]
    assert sorted(e["name"] for e in sys_entries) == SHIPPED
    assert {(e["library"], e["series"]) for e in sys_entries} == {("System", "Hatches")}
    assert all(not e["duplicate"] for e in sys_entries)


def test_list_library_system_false_excludes_tier(real_system_library):
    assert all(e["tier"] == "user" for e in bl.list_library(system=False))


def test_g1_save_of_a_system_id_is_refused_and_shipped_bytes_unchanged(
        real_system_library):
    before = _digests(real_system_library)
    defn = bl.load_block_file(
        os.path.join(real_system_library, "Hatches", "Diagonal.fpdb"))
    defn.library = "Mine"                 # even outside the reserved name
    with pytest.raises(bl.SystemLibraryReadOnly):
        bl.save_to_library(defn)
    assert _digests(real_system_library) == before
    assert _user_fpdb(bl.block_library_dir()) == []


@pytest.mark.parametrize("name", [
    pytest.param("System", id="System"),
    pytest.param("system", id="lower"),
    pytest.param(" SYSTEM ", id="padded"),
])
def test_g1_reserved_library_name_refused(name):
    with pytest.raises(bl.SystemLibraryReadOnly):
        bl.create_folder(name, "Hatches")
    with pytest.raises(bl.SystemLibraryReadOnly):
        bl.save_to_library(_defn(library=name, series="Hatches"))
    with pytest.raises(bl.SystemLibraryReadOnly):
        bl.delete_from_library(name, "Hatches", "Diagonal.fpdb")
    assert _user_fpdb(bl.block_library_dir()) == []


def test_g1_refile_never_deletes_a_system_file(real_system_library):
    before = _digests(real_system_library)
    defn = bl.load_block_file(
        os.path.join(real_system_library, "Hatches", "Brick.fpdb"))
    defn.id, defn.library, defn.series = "user-brick", "Mine", "Set"
    defn.source_path = os.path.join(real_system_library, "Hatches", "Brick.fpdb")
    path = bl.save_to_library(defn)
    assert os.path.isfile(path)
    assert _digests(real_system_library) == before


def test_d2_system_wins_an_id_clash(real_system_library):
    user = bl.block_library_dir()
    dst = os.path.join(user, "Mine", "Set")
    os.makedirs(dst)
    shutil.copyfile(os.path.join(real_system_library, "Hatches", "Diagonal.fpdb"),
                    os.path.join(dst, "Diagonal.fpdb"))
    owner = bl._find_by_id("builtin-hatch-diagonal", None)
    assert owner[3]["tier"] == "system"
    user_rows = [e for e in bl.list_library() if e["tier"] == "user"]
    assert [e["duplicate"] for e in user_rows] == [True]


def test_d2_system_owns_its_id_even_when_the_user_copy_is_consistent(tmp_path):
    """The user copy sits where its stored identity says (consistent) and the
    System file does not -- ownership must still go to System, not to the
    consistent-first rule."""
    import json
    sysroot = tmp_path / "sys"
    (sysroot / "Hatches").mkdir(parents=True)
    rec = _defn(name="Twin", library="System", series="Elsewhere").to_dict()
    (sysroot / "Hatches" / "Twin.fpdb").write_text(json.dumps(rec), "utf-8")
    bl.set_system_root(str(sysroot))
    user = _defn(name="Twin", library="Mine", series="Set")
    user.id = rec["id"]
    uroot = tmp_path / "u"
    user_dir = uroot / "Mine" / "Set"
    user_dir.mkdir(parents=True)
    (user_dir / "Twin.fpdb").write_text(json.dumps(user.to_dict()), "utf-8")
    owner = bl._find_by_id(rec["id"], str(uroot))
    assert owner[3]["tier"] == "system"
    rows = {e["tier"]: e for e in bl.list_library(str(uroot))}
    assert (rows["system"]["duplicate"], rows["user"]["duplicate"]) == (False, True)


def test_g1_previous_file_never_offers_a_system_file(real_system_library):
    """A Save may only re-file a file of the USER library: a System file whose
    id matches the definition is not one (so it is never deleted)."""
    path = os.path.join(real_system_library, "Hatches", "Brick.fpdb")
    defn = bl.load_block_file(path)
    defn.source_path = path
    assert bl._previous_file(defn, None) is None


def test_g1_user_root_inside_the_system_root_is_refused(tmp_path):
    """D3 guards the PATH too: a user root at / inside the System root (a
    mis-set library folder) must not let a save or a new folder land there."""
    sysroot = tmp_path / "sys"
    sysroot.mkdir()
    bl.set_system_root(str(sysroot))
    with pytest.raises(bl.SystemLibraryReadOnly):
        bl.save_to_library(_defn(), root=str(sysroot))
    with pytest.raises(bl.SystemLibraryReadOnly):
        bl.create_folder("Mine", "Set", root=str(sysroot / "nested"))
    assert list(sysroot.rglob("*")) == []


def test_missing_system_root_is_an_empty_tier(tmp_path):
    bl.set_system_root(str(tmp_path / "absent"))
    assert [e for e in bl.list_library() if e["tier"] == "system"] == []


def _saved_at(version):
    d = _defn(name="Tag", library="Mine", series="Set")
    d.version = version
    bl.save_to_library(d)
    return d


@pytest.mark.parametrize("version, base, expected", [
    pytest.param(3, 3, "library", id="same"),
    pytest.param(1, 1, "update available", id="older_untouched"),
    # a pre-SB1b project (no base_version) counts as untouched
    pytest.param(1, None, "update available", id="older_pre_sb1b"),
    pytest.param(2, 1, "modified", id="older_edited"),
    pytest.param(4, 3, "modified", id="past_library"),
])
def test_g6_status_values(version, base, expected):
    lib = _saved_at(3)
    proj = BlockDefinition.from_dict(lib.to_dict())
    proj.version, proj.base_version = version, base
    assert bl.source_status(proj) == expected


# ---------------------------------------------------------------------------
# T4: base_version stamped on load / reload (D7), G6 project half, G9
# ---------------------------------------------------------------------------
def _round_trip_project(scene, tmp_path):
    """Save the project with the real serializer and reopen it in a fresh scene."""
    from firepro3d.level_manager import LevelManager
    from firepro3d.model_space import Model_Space
    from firepro3d.scale_manager import ScaleManager

    proj = tmp_path / "proj.fpd"
    scene.save_to_file(str(proj))
    fresh = Model_Space()
    fresh._level_manager = LevelManager()
    fresh.scale_manager = ScaleManager()
    fresh.load_from_file(str(proj))
    return fresh


def test_g6_reload_clears_update_available(model_space):
    lib = _defn(name="Tag")
    path = bl.save_to_library(lib)
    model_space.load_blocks_from_files([path])
    proj = model_space._block_definitions[lib.id]
    assert (proj.base_version, bl.source_status(proj)) == (1, "library")
    lib.version = 3
    bl.save_to_library(lib)                       # the library moves on
    assert bl.source_status(proj) == "update available"
    assert model_space.reload_block_definition(lib.id)
    proj = model_space._block_definitions[lib.id]
    assert (proj.base_version, bl.source_status(proj)) == (3, "library")


def test_g6_edited_older_copy_reads_modified(model_space):
    lib = _defn(name="Tag")
    path = bl.save_to_library(lib)
    model_space.load_blocks_from_files([path])
    proj = model_space._block_definitions[lib.id]
    proj.set_primitives(list(proj.primitives))    # the real edit path bumps version
    lib.version = 5
    bl.save_to_library(lib)
    assert bl.source_status(proj) == "modified"


def test_g6_saving_an_edited_copy_stamps_it_untouched(model_space):
    """Saving the edited project copy to the library makes it the library
    version: base_version follows, the file carries it, status reads library."""
    lib = _defn(name="Tag")
    model_space.load_blocks_from_files([bl.save_to_library(lib)])
    proj = model_space._block_definitions[lib.id]
    proj.set_primitives(list(proj.primitives))    # edited -> version 2
    assert bl.source_status(proj) == "modified"
    path = bl.save_to_library(proj)
    assert proj.base_version == proj.version == 2
    assert bl.load_block_file(path).base_version == 2
    assert bl.source_status(proj) == "library"


def test_g6_replace_on_load_stamps_the_new_copy(model_space):
    lib = _defn(name="Tag")
    model_space.load_blocks_from_files([bl.save_to_library(lib)])
    lib.version = 4
    path = bl.save_to_library(lib)
    summary = model_space.load_blocks_from_files([path])
    assert summary["replaced"] == ["Tag"]
    proj = model_space._block_definitions[lib.id]
    assert (proj.base_version, bl.source_status(proj)) == (4, "library")


def test_g9_base_version_survives_project_round_trip(model_space, tmp_path):
    lib = _defn(name="Tag")
    model_space.load_blocks_from_files([bl.save_to_library(lib)])
    reopened = _round_trip_project(model_space, tmp_path)
    assert reopened._block_definitions[lib.id].base_version == 1


def _shipped_ids():
    from firepro3d.hatch_patterns import shipped_pattern_files
    return sorted(bid for bid, _p in shipped_pattern_files())


def test_g5_picker_lists_system_hatches_without_a_user_folder(
        real_system_library, tmp_path):
    from PyQt6.QtCore import QSettings
    from firepro3d.app_data import HATCH_DIR_KEY
    from firepro3d.hatch_patterns import library_patterns, tile_choices
    QSettings("GV", "FirePro3D").setValue(HATCH_DIR_KEY, str(tmp_path / "absent"))
    assert sorted(bid for _n, bid, _p in library_patterns()) == _shipped_ids()
    labels = [label for label, _ref in tile_choices(None)]
    for name in SHIPPED:
        assert name in labels


def test_g5_system_first_then_user_dedup_by_id(real_system_library, tmp_path):
    from PyQt6.QtCore import QSettings
    from firepro3d.app_data import HATCH_DIR_KEY
    from firepro3d.hatch_patterns import library_patterns
    user = tmp_path / "hatches"
    user.mkdir()
    shutil.copyfile(os.path.join(real_system_library, "Hatches", "Brick.fpdb"),
                    user / "Brick.fpdb")                      # same id: dropped
    QSettings("GV", "FirePro3D").setValue(HATCH_DIR_KEY, str(user))
    rows = library_patterns()
    assert [bid for _n, bid, _p in rows].count("builtin-hatch-brick") == 1
    assert all(p.startswith(real_system_library) for _n, _b, p in rows[:5])
