"""SV3 Task 3 -- one-tier library root for schematic templates
(schematics.md D-S15: <schematics>[/<Series>]/<name>.fpdb; the file's `kind`
decides the tier mapping -- the index is retired, 2026-10-10).

The two-tier block tree must be byte-for-byte unaffected.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QPointF

from firepro3d import block_library as bl
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem


def _defn(name, library, series, kind="block"):
    return BlockDefinition.new(
        name=name, library=library, series=series, origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()],
        kind=kind)


def _no_index(root):
    """No ``index.json`` anywhere under *root* (retired 2026-10-10)."""
    return not any("index.json" in files for _d, _s, files in os.walk(root))


# -- one-tier paths ----------------------------------------------------------

def test_series_and_root_paths_skip_empty_tiers(tmp_path):
    root = str(tmp_path)
    grouped = _defn("Riser", "", "Risers", kind="schematic")
    loose = _defn("Hanger", "", "", kind="schematic")
    assert bl.save_to_library(grouped, root=root) == os.path.join(root, "Risers", "Riser.fpdb")
    assert bl.save_to_library(loose, root=root) == os.path.join(root, "Hanger.fpdb")
    assert not os.path.exists(os.path.join(root, "_"))          # never a "_" tier
    assert {(e["series"], e["name"], e["kind"]) for e in bl.list_library(root)} == {
        ("Risers", "Riser", "schematic"), ("", "Hanger", "schematic")}
    assert _no_index(root)


def test_list_find_load_delete_see_one_tier_entries(tmp_path):
    root = str(tmp_path)
    grouped = _defn("Riser", "", "Risers", kind="schematic")
    loose = _defn("Hanger", "", "", kind="schematic")
    bl.save_to_library(grouped, root=root)
    bl.save_to_library(loose, root=root)
    entries = bl.list_library(root)
    assert {(e["library"], e["series"], e["name"], e.get("kind")) for e in entries} == {
        ("", "Risers", "Riser", "schematic"), ("", "", "Hanger", "schematic")}
    by_name = {e["name"]: e for e in entries}
    assert bl.entry_path(by_name["Riser"], root) == os.path.join(root, "Risers", "Riser.fpdb")
    assert bl.entry_path(by_name["Hanger"], root) == os.path.join(root, "Hanger.fpdb")
    assert bl._find_by_id(grouped.id, root)[:3] == ("", "Risers", "Riser.fpdb")
    assert bl._find_by_id(loose.id, root)[:3] == ("", "", "Hanger.fpdb")
    assert bl.load_block("", "Risers", "Riser.fpdb", root).id == grouped.id
    assert bl.load_block("", "", "Hanger.fpdb", root).id == loose.id
    assert bl.source_status(grouped, root) == "library"
    assert bl.reload_from_library(loose, root).id == loose.id
    bl.delete_from_library("", "", "Hanger.fpdb", root)
    assert not os.path.exists(os.path.join(root, "Hanger.fpdb"))
    assert _no_index(root)
    assert bl._find_by_id(loose.id, root) is None


def test_one_tier_resave_refiles_without_duplicates(tmp_path):
    root = str(tmp_path)
    d = _defn("Riser", "", "", kind="schematic")
    bl.save_to_library(d, root=root)
    d.series = "Risers"                                   # moved into a Series
    bl.save_to_library(d, root=root)
    assert not os.path.exists(os.path.join(root, "Riser.fpdb"))
    assert _no_index(root)
    assert os.path.isfile(os.path.join(root, "Risers", "Riser.fpdb"))
    bl.save_to_library(d, root=root)                     # same place: no churn
    assert [e["id"] for e in bl.list_library(root)] == [d.id]


def test_find_collision_and_create_folder_one_tier(tmp_path):
    root = str(tmp_path)
    a = _defn("Riser", "", "Risers", kind="schematic")
    bl.save_to_library(a, root=root)
    assert bl.find_collision(a.id, "", "Risers", "Riser", root=root) is None
    assert bl.find_collision("other", "", "Risers", "Riser", root=root) == "Riser"
    assert bl.find_collision("other", "", "", "Riser", root=root) is None
    assert bl.create_folder("", "Trim", root=root) == os.path.join(root, "Trim")
    assert bl.list_folders(root) == {"Risers": [], "Trim": []}


# -- two-tier block tree unchanged --------------------------------------------

def test_two_tier_block_tree_unchanged(tmp_path):
    root = str(tmp_path)
    b = _defn("Joint", "Fire", "Valves")
    assert bl.save_to_library(b, root=root) == os.path.join(root, "Fire", "Valves", "Joint.fpdb")
    [entry] = bl.list_library(root)
    assert (entry["library"], entry["series"], entry["kind"]) == ("Fire", "Valves", "block")
    assert _no_index(root)


def test_library_only_entries_skip_schematic_index_entries(tmp_path, qapp):
    from firepro3d.blocks_browser import library_only_entries
    from firepro3d.model_space import Model_Space
    root = str(tmp_path)
    bl.save_to_library(_defn("Joint", "Fire", "Valves"), root=root)
    bl.save_to_library(_defn("Stray", "Fire", "Valves", kind="schematic"), root=root)
    names = [name for _l, _s, name, _i, _p in library_only_entries(Model_Space(), root)]
    assert names == ["Joint"]


def test_load_failure_message_noun():
    summary = {"refused": ["Riser"]}
    assert bl.load_failure_message("Riser", summary) == (
        "Could not load “Riser”: a different block already uses this name in the project.")
    assert bl.load_failure_message("Riser", summary, noun="schematic") == (
        "Could not load “Riser”: a different schematic already uses this name in the project.")
