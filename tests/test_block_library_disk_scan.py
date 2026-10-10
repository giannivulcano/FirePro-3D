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
