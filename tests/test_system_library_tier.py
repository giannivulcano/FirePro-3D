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
