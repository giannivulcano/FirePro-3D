"""Block library lists the .fpdb files on disk -- no index.json (2026-10-10).

Folder + filename win; loose files list under ``Ungrouped``; a copied file
(duplicate id) is listed too and loads as its own block; the app never writes
an ``index.json`` and removes a stale one when it next writes in that folder.
"""
from __future__ import annotations

import json
import os
import shutil

from PyQt6.QtCore import QPointF

from firepro3d import block_library as bl
from firepro3d import capability_folder
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem


def _defn(name, library="Fire", series="Valves", kind="block"):
    return BlockDefinition.new(
        name=name, library=library, series=series, origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()],
        kind=kind)


def _drop(folder, filename, defn):
    """Write a .fpdb the way a user copying files would: no index, no app."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(defn.to_dict(), fh)
    return path


# -- capability scan (G6) -----------------------------------------------------

def test_g6_hand_dropped_pattern_is_offered_by_the_capability_scan(tmp_path):
    from firepro3d import hatch_patterns as hp
    src = dict(hp.shipped_pattern_files())[hp.BUILTIN_DIAGONAL]
    folder = tmp_path / "Mine" / "Hatches"
    folder.mkdir(parents=True)
    shutil.copyfile(src, folder / "My Diagonal.fpdb")      # no index.json at all
    hits = capability_folder.scan(str(tmp_path), "tile")
    assert [bid for _n, bid, _p in hits] == [hp.BUILTIN_DIAGONAL]
    assert not (folder / "index.json").exists()


def test_capability_scan_ignores_a_stale_index_flag(tmp_path):
    from firepro3d import hatch_patterns as hp
    src = dict(hp.shipped_pattern_files())[hp.BUILTIN_DIAGONAL]
    folder = tmp_path / "L" / "Hatches"
    folder.mkdir(parents=True)
    shutil.copyfile(src, folder / "Diag.fpdb")
    # a stale index claims the file is NOT a pattern -- the file must win
    (folder / "index.json").write_text(json.dumps(
        {"Diag.fpdb": {"id": hp.BUILTIN_DIAGONAL, "name": "Diag", "tile": False}}))
    hits = capability_folder.scan(str(tmp_path), "tile")
    assert [b for _n, b, _p in hits] == [hp.BUILTIN_DIAGONAL]


# -- block_library disk walk (G2, G5) -----------------------------------------

def test_hand_dropped_file_is_listed_folder_and_filename_win(tmp_path):
    d = _defn("Stored Name", "Elsewhere", "Wrong")
    _drop(tmp_path / "Fire" / "Valves", "Gate Valve.fpdb", d)
    [e] = bl.list_library(str(tmp_path))
    assert (e["library"], e["series"], e["name"], e["id"]) == (
        "Fire", "Valves", "Gate Valve", d.id)
    assert bl.entry_path(e, str(tmp_path)) == str(
        tmp_path / "Fire" / "Valves" / "Gate Valve.fpdb")


def test_g5_loose_files_list_under_ungrouped(tmp_path):
    _drop(tmp_path / "Fire", "A.fpdb", _defn("A"))           # Library level
    _drop(tmp_path, "B.fpdb", _defn("B"))                    # root level
    got = {e["name"]: (e["library"], e["series"])
           for e in bl.list_library(str(tmp_path))}
    assert got == {"A": ("Fire", bl.UNGROUPED),
                   "B": (bl.UNGROUPED, bl.UNGROUPED)}


def test_one_tier_schematics_map_by_kind(tmp_path):
    _drop(tmp_path / "Risers", "Riser.fpdb", _defn("Riser", "", "", kind="schematic"))
    _drop(tmp_path, "Hanger.fpdb", _defn("Hanger", "", "", kind="schematic"))
    got = {e["name"]: (e["library"], e["series"])
           for e in bl.list_library(str(tmp_path))}
    assert got == {"Riser": ("", "Risers"), "Hanger": ("", "")}


def test_g2_no_index_written_and_stale_index_removed(tmp_path):
    folder = tmp_path / "Fire" / "Valves"
    folder.mkdir(parents=True)
    (folder / "index.json").write_text("{}")                 # from an older build
    bl.save_to_library(_defn("Joint"), root=str(tmp_path))
    assert not (folder / "index.json").exists()
    other = tmp_path / "Fire" / "Heads"
    _drop(other, "X.fpdb", _defn("X", series="Heads"))
    (other / "index.json").write_text("{}")
    bl.delete_from_library("Fire", "Heads", "X.fpdb", root=str(tmp_path))
    assert not (other / "index.json").exists()
    assert not (other / "X.fpdb").exists()
    assert not list(tmp_path.rglob("index.json"))


def test_collision_reads_the_occupying_file(tmp_path):
    occupant = _defn("Joint")
    _drop(tmp_path / "Fire" / "Valves", "Joint.fpdb", occupant)
    assert bl.find_collision("someone-else", "Fire", "Valves", "Joint",
                             str(tmp_path)) == "Joint"
    assert bl.find_collision(occupant.id, "Fire", "Valves", "Joint",
                             str(tmp_path)) is None


def test_refile_moves_a_loose_file_into_its_series(tmp_path):
    d = _defn("A", "Fire", bl.UNGROUPED)
    _drop(tmp_path / "Fire", "A.fpdb", d)                    # loose, owns d.id
    bl.save_to_library(d, root=str(tmp_path))
    assert not (tmp_path / "Fire" / "A.fpdb").exists()
    assert (tmp_path / "Fire" / bl.UNGROUPED / "A.fpdb").exists()
    assert bl.source_status(d, str(tmp_path)) == "library"


def test_unreadable_file_is_skipped(tmp_path):
    folder = tmp_path / "Fire" / "Valves"
    folder.mkdir(parents=True)
    (folder / "Broken.fpdb").write_text("{not json")
    _drop(folder, "Good.fpdb", _defn("Good"))
    assert [e["name"] for e in bl.list_library(str(tmp_path))] == ["Good"]


# -- load adopts the disk identity (G3, G4) -----------------------------------

def test_g4_load_adopts_the_folder_over_the_stored_series(tmp_path, qapp):
    from firepro3d.model_space import Model_Space
    d = _defn("2x4", "Typical Details", "Wet Valve Schematics")   # folder-jump repro
    path = _drop(tmp_path / "Typical Details" / "Dimensional Lumber", "2x4.fpdb", d)
    ms = Model_Space()
    ms.load_blocks_from_files([path], root=str(tmp_path))
    got = ms.get_block_definition(d.id)
    assert (got.library, got.series, got.name) == (
        "Typical Details", "Dimensional Lumber", "2x4")


def test_g3_copied_file_loads_as_a_separate_block(tmp_path, qapp):
    from firepro3d.model_space import Model_Space
    d = _defn("Corner")
    folder = tmp_path / "Fire" / "Valves"
    a = _drop(folder, "Corner.fpdb", d)
    b = str(folder / "Corner v2.fpdb")
    shutil.copyfile(a, b)
    ms = Model_Space()
    s = ms.load_blocks_from_files([a, b], root=str(tmp_path))
    assert s["loaded"] == ["Corner", "Corner v2"] and not s["refused"]
    defs = {x.name: x for x in ms._block_definitions.values()}
    assert defs["Corner"].id == d.id and defs["Corner v2"].id != d.id
    assert bl.source_status(defs["Corner"], str(tmp_path)) == "library"
    with open(b, encoding="utf-8") as fh:
        assert json.load(fh)["id"] == d.id               # file untouched until Save
    # Saving the copy writes over its own file -- not a collision
    bl.save_to_library(defs["Corner v2"], root=str(tmp_path))
    with open(b, encoding="utf-8") as fh:
        assert json.load(fh)["id"] == defs["Corner v2"].id
    with open(a, encoding="utf-8") as fh:
        assert json.load(fh)["id"] == d.id               # the original is kept


# -- Blocks browser (G1) -------------------------------------------------------

def _leaf_names(browser):
    out = {}
    for i in range(browser._tree.topLevelItemCount()):
        lib = browser._tree.topLevelItem(i)
        for j in range(lib.childCount()):
            ser = lib.child(j)
            for k in range(ser.childCount()):
                out[ser.child(k).text(0)] = (lib.text(0), ser.text(0))
    return out


def test_g1_file_dropped_while_running_appears_on_reactivation(tmp_path, qapp):
    from PyQt6.QtCore import Qt
    from firepro3d.blocks_browser import BlocksBrowser
    from firepro3d.model_space import Model_Space
    b = BlocksBrowser(Model_Space(), root=str(tmp_path))
    assert _leaf_names(b) == {}
    _drop(tmp_path / "Fire" / "Valves", "Gate Valve.fpdb", _defn("Old Name", "X", "Y"))
    qapp.applicationStateChanged.emit(Qt.ApplicationState.ApplicationActive)
    assert _leaf_names(b) == {"Gate Valve": ("Fire", "Valves")}


def test_duplicate_entry_stays_listed_after_its_owner_loads(tmp_path, qapp):
    from firepro3d.blocks_browser import library_only_entries
    from firepro3d.model_space import Model_Space
    a = _drop(tmp_path / "Fire" / "Valves", "Corner.fpdb", _defn("Corner"))
    shutil.copyfile(a, tmp_path / "Fire" / "Valves" / "Corner v2.fpdb")
    ms = Model_Space()
    ms.load_blocks_from_files([a], root=str(tmp_path))
    names = [n for _l, _s, n, _i, _p in library_only_entries(ms, str(tmp_path))]
    assert names == ["Corner v2"]
    ms.load_blocks_from_files([str(tmp_path / "Fire" / "Valves" / "Corner v2.fpdb")],
                              root=str(tmp_path))
    assert library_only_entries(ms, str(tmp_path)) == []


def test_activating_a_copy_leaf_places_the_copy_not_the_original(tmp_path, qapp):
    from firepro3d.blocks_browser import BlocksBrowser
    from firepro3d.model_space import Model_Space
    d = _defn("Corner")
    a = _drop(tmp_path / "Fire" / "Valves", "Corner.fpdb", d)
    shutil.copyfile(a, tmp_path / "Fire" / "Valves" / "Corner v2.fpdb")
    ms = Model_Space()
    ms.load_blocks_from_files([a], root=str(tmp_path))      # original in project
    b = BlocksBrowser(ms, root=str(tmp_path))
    got = []
    b.blockActivated.connect(got.append)
    lib = b._tree.topLevelItem(0)
    leaf = next(lib.child(0).child(k) for k in range(lib.child(0).childCount())
                if lib.child(0).child(k).text(0) == "Corner v2")
    b._on_item_activated(leaf, 0)
    [placed] = got
    assert placed != d.id
    assert ms.get_block_definition(placed).name == "Corner v2"


def test_status_reads_a_save_made_inside_one_clock_tick(tmp_path):
    """A re-save right after a read must not be served from the parse cache."""
    d = _defn("Joint")
    path = bl.save_to_library(d, root=str(tmp_path))
    assert bl.source_status(d, str(tmp_path)) == "library"          # caches v1
    before = os.stat(path)
    d.set_primitives(d.primitives)                                  # v2 (same size)
    bl.save_to_library(d, root=str(tmp_path))
    # Pin the clock tick: the re-saved file keeps the old mtime and size.
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert os.stat(path).st_size == before.st_size
    assert bl.list_library(str(tmp_path))[0]["version"] == d.version
    assert bl.source_status(d, str(tmp_path)) == "library"


# -- review round: ownership, human names, user folders (C1, I1-I3, M1) -------

def test_c1_same_filename_copy_in_another_folder_never_owns_and_survives_save(
        tmp_path, qapp):
    from firepro3d.model_space import Model_Space
    d = _defn("Corner")                                     # stored Fire/Valves
    a = _drop(tmp_path / "Fire" / "Valves", "Corner.fpdb", d)
    archive = tmp_path / "Archive" / "Old"                  # sorts before Fire
    archive.mkdir(parents=True)
    shutil.copyfile(a, archive / "Corner.fpdb")
    owner = bl._find_by_id(d.id, str(tmp_path))
    assert owner[3]["path"] == a                            # the original owns the id
    ms = Model_Space()
    ms.load_blocks_from_files([a], root=str(tmp_path))
    proj = ms.get_block_definition(d.id)
    proj.set_primitives(proj.primitives)                    # edit -> v2
    bl.save_to_library(proj, root=str(tmp_path))
    assert (archive / "Corner.fpdb").exists()               # the user's copy is kept
    with open(a, encoding="utf-8") as fh:
        assert json.load(fh)["version"] == proj.version


def test_i1_pattern_copy_elsewhere_does_not_rob_the_shipped_id(tmp_path, qapp):
    from firepro3d import hatch_patterns as hp
    from firepro3d.model_space import Model_Space
    hatches = tmp_path / "System" / "Hatches"
    hp.seed_hatch_folder(str(hatches))
    archive = tmp_path / "Archive" / "Old"
    archive.mkdir(parents=True)
    shutil.copyfile(hatches / "Brick.fpdb", archive / "Brick.fpdb")
    ms = Model_Space()
    s = ms.load_blocks_from_files([str(hatches / "Brick.fpdb")], root=str(tmp_path))
    assert s["ids"] == {str(hatches / "Brick.fpdb"): hp.BUILTIN_BRICK}


def test_i2_human_names_survive_the_sanitized_file_names(tmp_path, qapp):
    from firepro3d.model_space import Model_Space
    d = _defn("Valve (OS&Y)", "Pipe & Fittings", "Gate/Globe")
    path = bl.save_to_library(d, root=str(tmp_path))
    [e] = bl.list_library(str(tmp_path))
    assert (e["library"], e["series"], e["name"]) == (
        "Pipe & Fittings", "Gate/Globe", "Valve (OS&Y)")
    ms = Model_Space()
    ms.load_blocks_from_files([path], root=str(tmp_path))
    got = ms.get_block_definition(d.id)
    assert (got.library, got.series, got.name) == (
        "Pipe & Fittings", "Gate/Globe", "Valve (OS&Y)")
    got.set_primitives(got.primitives)
    bl.save_to_library(got, root=str(tmp_path))
    assert ms.reload_block_definition(d.id, root=str(tmp_path))
    again = ms.get_block_definition(d.id)
    assert (again.library, again.series, again.name) == (
        "Pipe & Fittings", "Gate/Globe", "Valve (OS&Y)")


def test_i3_a_user_made_folder_is_saved_back_in_place(tmp_path, qapp):
    from firepro3d.model_space import Model_Space
    path = _drop(tmp_path / "Pipe & Fittings" / "Elbows", "Elbow (90).fpdb",
                 _defn("Elbow", "Other", "Thing"))
    ms = Model_Space()
    s = ms.load_blocks_from_files([path], root=str(tmp_path))
    got = ms.get_block_definition(s["ids"][path])
    assert (got.library, got.series, got.name) == ("Pipe & Fittings", "Elbows", "Elbow (90)")
    got.set_primitives(got.primitives)
    assert bl.save_to_library(got, root=str(tmp_path)) == path   # same file, in place
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Pipe & Fittings"]


def test_m1_saving_the_original_onto_its_copys_file_name_asks_first(tmp_path):
    d = _defn("Corner")
    a = _drop(tmp_path / "Fire" / "Valves", "Corner.fpdb", d)
    shutil.copyfile(a, tmp_path / "Fire" / "Valves" / "Corner v2.fpdb")
    assert bl.find_collision(d.id, "Fire", "Valves", "Corner v2",
                             str(tmp_path)) == "Corner v2"
