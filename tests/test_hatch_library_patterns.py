"""Hatch patterns folder: library pattern blocks reach every pattern picker
(hatch-and-fill.md D-A37) + Pattern tile seeds Size = Model (D-A38).

A library-only pattern used to be unreachable: pickers listed built-ins +
project tiles, library blocks load on place, and pattern blocks can't be
placed (D-A34). The folder setting makes the library a picker source; picking
a library pattern loads it into the project, then stores its id.
"""
from __future__ import annotations

import json
import os

import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d import app_data, block_library as bl
from firepro3d import hatch_patterns as hp
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space


def _pattern(name="Zig", library="System", series="Hatches"):
    return BlockDefinition.new(
        name=name, library=library, series=series, origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})


def _symbol(name="Valve", library="System", series="Hatches"):
    return BlockDefinition.new(
        name=name, library=library, series=series, origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(10, 0)).to_dict()])


@pytest.fixture
def hatch_dir(qapp, tmp_path):
    """A Library-root folder set as the Hatch patterns folder (isolated
    QSettings — tests/conftest.py ``_isolate_qsettings``)."""
    root = tmp_path / "patterns_root"
    root.mkdir()
    QSettings("GV", "FirePro3D").setValue(app_data.HATCH_DIR_KEY, str(root))
    return root


def _labels(registry):
    return {label: ref for label, ref in hp.tile_choices(registry)}


# ── Setting ─────────────────────────────────────────────────────────────────

def test_hatch_dir_defaults_under_the_block_library(qapp):
    QSettings("GV", "FirePro3D").setValue(app_data.HATCH_DIR_KEY, "")
    assert app_data.hatch_patterns_dir() == os.path.join(
        app_data.block_library_dir(), "System", "Hatches")


def test_hatch_dir_override_wins(hatch_dir):
    assert app_data.hatch_patterns_dir() == str(hatch_dir)


def test_general_pane_hatch_patterns_row_round_trips(qapp, tmp_path):
    from firepro3d.settings import panes as pd
    pane = pd.GeneralPane()
    pane.load()
    assert pane._hatch_dir_edit.toolTip() == (
        "Folder of hatch pattern blocks offered in every pattern picker "
        "(default: <block library>/System/Hatches)")
    pane._hatch_dir_edit.setText(str(tmp_path / "hatches"))
    pane.apply()
    assert QSettings("GV", "FirePro3D").value(
        app_data.HATCH_DIR_KEY, "", type=str) == str(tmp_path / "hatches")
    assert app_data.hatch_patterns_dir() == str(tmp_path / "hatches")
    pane2 = pd.GeneralPane()
    pane2.load()
    assert pane2._hatch_dir_edit.text() == str(tmp_path / "hatches")
    pane2._hatch_dir_edit.setText("changed")
    pane2.revert()
    assert pane2._hatch_dir_edit.text() == str(tmp_path / "hatches")
    pane2._hatch_dir_edit.clear()                 # blank = default
    pane2.apply()
    assert app_data.hatch_patterns_dir() == os.path.join(
        app_data.block_library_dir(), "System", "Hatches")


# ── Index flag + scan ───────────────────────────────────────────────────────

def test_save_to_library_flags_tile_in_the_index(tmp_path):
    p, s = _pattern(), _symbol()
    bl.save_to_library(p, root=str(tmp_path))
    bl.save_to_library(s, root=str(tmp_path))
    idx = json.loads((tmp_path / "System" / "Hatches" / "index.json").read_text())
    assert idx["Zig.fpdb"]["tile"] is True
    assert idx["Valve.fpdb"]["tile"] is False


def test_library_pattern_is_listed_and_symbol_is_not(hatch_dir):
    p, s = _pattern(), _symbol()
    bl.save_to_library(p, root=str(hatch_dir))
    bl.save_to_library(s, root=str(hatch_dir))
    ms = Model_Space()
    labels = _labels(ms.block_registry)
    assert labels.get("Zig") == p.id
    assert s.id not in labels.values()
    assert p.id not in ms._block_definitions          # listing never loads
    # Category defaults (no registry) list the folder (D-A39, was built-ins only).
    assert p.id in {r for _n, r in hp.tile_choices(None)}


def test_series_folder_itself_works_as_the_patterns_folder(qapp, tmp_path):
    # The default is <block library>/System/Hatches — a Series folder.
    p = _pattern()
    bl.save_to_library(p, root=str(tmp_path))
    series = tmp_path / "System" / "Hatches"
    QSettings("GV", "FirePro3D").setValue(app_data.HATCH_DIR_KEY, str(series))
    assert _labels(Model_Space().block_registry).get("Zig") == p.id


def test_project_copy_wins_and_library_name_collision_is_suffixed(hatch_dir):
    p = _pattern()
    bl.save_to_library(p, root=str(hatch_dir))
    other = _pattern(name="Zig", library="Mine", series="Own")
    bl.save_to_library(other, root=str(hatch_dir))
    ms = Model_Space()
    ms.register_block_definition(p)                    # p already in project
    choices = hp.tile_choices(ms.block_registry)
    refs = [r for _n, r in choices]
    assert refs.count(p.id) == 1
    assert ("Zig", p.id) in choices
    assert ("Zig (library)", other.id) in choices


def test_newly_saved_pattern_appears_without_restart(hatch_dir):
    ms = Model_Space()
    assert "Zig" not in _labels(ms.block_registry)
    p = _pattern()
    bl.save_to_library(p, root=str(hatch_dir))
    assert _labels(ms.block_registry).get("Zig") == p.id
    q = _pattern(name="Brick2")
    bl.save_to_library(q, root=str(hatch_dir))
    assert _labels(ms.block_registry).get("Brick2") == q.id


def test_old_index_entry_without_tile_is_detected_by_parsing(hatch_dir):
    p, s = _pattern(), _symbol()
    bl.save_to_library(p, root=str(hatch_dir))
    bl.save_to_library(s, root=str(hatch_dir))
    idx_path = hatch_dir / "System" / "Hatches" / "index.json"
    idx = json.loads(idx_path.read_text())
    for meta in idx.values():
        meta.pop("tile")                               # a pre-D-A37 index
    idx_path.write_text(json.dumps(idx))
    labels = _labels(Model_Space().block_registry)
    assert labels.get("Zig") == p.id
    assert s.id not in labels.values()


def test_unreadable_files_are_skipped(hatch_dir):
    p = _pattern()
    bl.save_to_library(p, root=str(hatch_dir))
    bad = hatch_dir / "System" / "Hatches" / "broken.fpdb"
    bad.write_text("{not json")
    assert [bid for _n, bid, _p in hp.library_patterns()] == [p.id]


# ── Picking loads the pattern into the project ──────────────────────────────

def _rect_in(ms):
    rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    ms.addItem(rect)
    ms._draw_rects.append(rect)            # the undo snapshot's draw list
    rect.set_property("Fill", "hatch")
    ms.push_undo_state()
    return rect


def test_picking_via_the_property_setter_loads_then_stores(hatch_dir):
    p = _pattern()
    bl.save_to_library(p, root=str(hatch_dir))
    ms = Model_Space()
    rect = _rect_in(ms)
    opts = rect.get_properties()["Pattern"]["options"]
    assert "Zig" in opts
    pos0 = ms._undo_pos
    rect.set_property("Pattern", "Zig")
    assert rect.fill_pattern == p.id
    assert p.id in ms._block_definitions
    assert hp.resolve_tile(p.id, ms.block_registry) is not None
    assert ms._undo_pos == pos0 + 1                    # the load's one batch
    ms.undo()                                          # one step removes the load
    assert p.id not in ms._block_definitions
    (rect2,) = ms._draw_rects                          # restored (refs invalidated)
    assert (rect2.fill_type, rect2.fill_pattern) == ("hatch", hp.DEFAULT_TILE_REF)


def test_picking_via_the_entity_context_menu_loads_then_stores(hatch_dir):
    p = _pattern()
    bl.save_to_library(p, root=str(hatch_dir))
    ms = Model_Space()
    rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    ms.addItem(rect)
    rect.setSelected(True)
    ms.push_undo_state()
    menu = ms._build_entity_context_menu(rect)
    fill = next(a.menu() for a in menu.actions() if a.text() == "Fill")
    hatch = next(a.menu() for a in fill.actions() if a.text() == "Hatch")
    act = next((a for a in hatch.actions() if a.text() == "Zig"), None)
    assert act is not None, [a.text() for a in hatch.actions()]
    act.trigger()
    assert (rect.fill_type, rect.fill_pattern) == ("hatch", p.id)
    assert p.id in ms._block_definitions
    ms.undo()                                          # one step removes the load
    assert p.id not in ms._block_definitions


def test_picking_in_the_plan_context_menu_loads(hatch_dir):
    from PyQt6.QtWidgets import QApplication
    from firepro3d.model_view import Model_View
    p = _pattern()
    bl.save_to_library(p, root=str(hatch_dir))
    ms = Model_Space()
    view = Model_View(ms)
    QApplication.processEvents()
    rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    ms.addItem(rect)
    rect.setSelected(True)
    menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
    fill = next(a.menu() for a in menu.actions() if a.text() == "Fill")
    hatch = next(a.menu() for a in fill.actions() if a.text() == "Hatch")
    next(a for a in hatch.actions() if a.text() == "Zig").trigger()
    assert (rect.fill_type, rect.fill_pattern) == ("hatch", p.id)
    assert p.id in ms._block_definitions


def test_picking_in_a_block_editor_loads_into_the_project(hatch_dir):
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.block_editor import BlockEditorManager
    p = _pattern()
    bl.save_to_library(p, root=str(hatch_dir))
    project = Model_Space()
    w = BlockEditorManager(QTabWidget(), project).open_new()
    rect = RectangleItem(QPointF(0, 0), QPointF(20, 10))
    w._add_primitive(rect)
    rect.set_property("Fill", "hatch")
    assert "Zig" in rect.get_properties()["Pattern"]["options"]
    rect.set_property("Pattern", "Zig")
    assert rect.fill_pattern == p.id
    assert p.id in project._block_definitions          # the PROJECT, not the editor


def test_loaded_pattern_is_saved_and_bundled(hatch_dir, tmp_path):
    # Bundling sanity: once loaded it is an ordinary project definition.
    p = _pattern()
    bl.save_to_library(p, root=str(hatch_dir))
    ms = Model_Space()
    rect = _rect_in(ms)
    rect.set_property("Pattern", "Zig")
    out = tmp_path / "proj.fpd"
    ms.save_to_file(str(out))
    assert p.id in json.loads(out.read_text(encoding="utf-8"))["block_definitions"]
    host = BlockDefinition.new(name="Host", library="L", series="S",
                               origin=(0.0, 0.0), primitives=[rect.to_dict()])
    ms.register_block_definition(host)
    assert p.id in ms.block_registry.bundle_for(host.id)


# ── D-A38 ───────────────────────────────────────────────────────────────────

def test_pattern_tile_toggle_seeds_size_model(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.tile_frame import seed_tile
    assert seed_tile([])["size"] == "model"
    w = BlockEditorWidget(Model_Space())
    w._add_primitive(LineItem(QPointF(0, 0), QPointF(20, -8)))
    assert w.toggle_pattern_tile()
    assert w.editor_scene.block_tile["size"] == "model"
