"""LT3-13 / H3-i -- Linetypes folder: default, override, shared scan, settings row.

QSettings and the block library are isolated per test by the autouse
fixtures in tests/conftest.py (``_isolate_qsettings`` /
``_isolate_block_library``), so nothing here touches the real store.
"""
from __future__ import annotations

import json
import os

from PyQt6.QtCore import QPointF, QSettings

from firepro3d import app_data, block_library as bl, capability_folder
from firepro3d import hatch_patterns as hp
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from tests.lt3_support import make_linetype


def _pattern(name="Zig"):
    return BlockDefinition.new(
        name=name, library="L", series="Linetypes", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})


def _symbol(name="Sym"):
    return BlockDefinition.new(
        name=name, library="L", series="Linetypes", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()])


# ── Setting ─────────────────────────────────────────────────────────────────

def test_default_under_block_library(qapp):
    QSettings("GV", "FirePro3D").setValue(app_data.LINETYPE_DIR_KEY, "")
    assert app_data.linetypes_dir() == os.path.join(
        app_data.block_library_dir(), "System", "Linetypes")


def test_override_wins(qapp, tmp_path):
    QSettings("GV", "FirePro3D").setValue(
        app_data.LINETYPE_DIR_KEY, str(tmp_path / "lts"))
    assert app_data.linetypes_dir() == str(tmp_path / "lts")


def test_general_pane_linetypes_row_round_trips(qapp, tmp_path):
    from firepro3d.settings import panes as pd
    pane = pd.GeneralPane()
    pane.load()
    assert pane._lt_dir_edit.toolTip() == (
        "Folder of linetype blocks offered in every Linetype picker "
        "(default: <block library>/System/Linetypes)")
    assert pane._lt_dir_edit.placeholderText() == "(block library)/System/Linetypes"
    pane._lt_dir_edit.setText(str(tmp_path / "lts"))
    pane.apply()
    assert QSettings("GV", "FirePro3D").value(
        app_data.LINETYPE_DIR_KEY, "", type=str) == str(tmp_path / "lts")
    assert app_data.linetypes_dir() == str(tmp_path / "lts")
    pane2 = pd.GeneralPane()
    pane2.load()
    assert pane2._lt_dir_edit.text() == str(tmp_path / "lts")
    pane2._lt_dir_edit.setText("changed")
    pane2.revert()
    assert pane2._lt_dir_edit.text() == str(tmp_path / "lts")
    pane2._lt_dir_edit.clear()                     # blank = default
    pane2.apply()
    assert app_data.linetypes_dir() == os.path.join(
        app_data.block_library_dir(), "System", "Linetypes")


def test_general_pane_linetypes_buttons_have_tooltips(qapp):
    from PyQt6.QtWidgets import QPushButton
    from firepro3d.settings import panes as pd
    pane = pd.GeneralPane()
    tips = {b.toolTip() for b in pane.findChildren(QPushButton)}
    assert "Choose the linetypes folder" in tips
    assert "Use the default (<block library>/System/Linetypes)" in tips


# ── Shared scan ─────────────────────────────────────────────────────────────

def test_scan_finds_repeat_blocks_only(qapp, tmp_path):
    lt = make_linetype(name="Hidden")
    bl.save_to_library(lt, root=str(tmp_path))
    bl.save_to_library(_symbol(), root=str(tmp_path))
    pat = _pattern()
    bl.save_to_library(pat, root=str(tmp_path))
    found = capability_folder.scan(str(tmp_path), "repeat")
    assert [(n, b) for n, b, _ in found] == [("Hidden", lt.id)]
    assert os.path.isfile(found[0][2])
    # Same folder, other flag: the cache is per (folder, flag).
    assert [b for _n, b, _p in capability_folder.scan(str(tmp_path), "tile")] \
        == [pat.id]
    assert [b for _n, b, _p in hp.library_patterns(str(tmp_path))] == [pat.id]


def test_a_stale_index_is_ignored_the_file_decides(qapp, tmp_path):
    lt = make_linetype(name="Hidden")
    bl.save_to_library(lt, root=str(tmp_path))
    sym = _symbol()
    bl.save_to_library(sym, root=str(tmp_path))
    idx_path = tmp_path / "L" / "Linetypes" / "index.json"   # older build's index
    idx_path.write_text(json.dumps({"Hidden.fpdb": {"id": lt.id, "repeat": False}}))
    assert [b for _n, b, _p in capability_folder.scan(str(tmp_path), "repeat")] \
        == [lt.id]


def test_newly_saved_linetype_appears_without_restart(qapp, tmp_path):
    assert capability_folder.scan(str(tmp_path), "repeat") == []
    lt = make_linetype(name="Hidden")
    bl.save_to_library(lt, root=str(tmp_path))
    assert [b for _n, b, _p in capability_folder.scan(str(tmp_path), "repeat")] \
        == [lt.id]


def test_missing_folder_scans_empty(qapp, tmp_path):
    assert capability_folder.scan(str(tmp_path / "nope"), "repeat") == []
