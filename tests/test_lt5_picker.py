"""LT5 D2 -- one capability picker source + the End Types folder (Q10, Q13).

QSettings and the block library are isolated per test by the autouse
fixtures in tests/conftest.py, so setting END_DIR_KEY never leaks.
"""
import os

import pytest
from PyQt6.QtCore import QSettings

from firepro3d import app_data, block_library
from firepro3d import stroke_style as ss
from firepro3d.capabilities import (capability_choices, end_choices,
                                    end_ref_from_value, ensure_end_available)
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden, make_linetype
from tests.lt5_support import end_id, v_end


@pytest.fixture
def end_dir(qapp, tmp_path):
    root = tmp_path / "ends_root"
    root.mkdir()
    QSettings("GV", "FirePro3D").setValue(app_data.END_DIR_KEY, str(root))
    return root


def _folder(end_dir, name="Tick", series="End Types"):
    e = v_end(name=name, series=series)
    block_library.save_to_library(e, root=str(end_dir))
    return e


# ── folder + setting ────────────────────────────────────────────────────────

def test_default_under_block_library(qapp):
    QSettings("GV", "FirePro3D").setValue(app_data.END_DIR_KEY, "")
    assert app_data.end_types_dir() == os.path.join(
        app_data.block_library_dir(), "System", "End Types")


def test_override_wins(qapp, tmp_path):
    QSettings("GV", "FirePro3D").setValue(app_data.END_DIR_KEY, str(tmp_path / "e"))
    assert app_data.end_types_dir() == str(tmp_path / "e")


def test_general_pane_end_types_row_round_trips(qapp, tmp_path):
    from PyQt6.QtWidgets import QPushButton
    from firepro3d.settings import panes as pd
    pane = pd.GeneralPane()
    pane.load()
    assert pane._end_dir_edit.toolTip() == (
        "Folder of end type blocks offered in every Start End / Finish End "
        "picker (default: <block library>/System/End Types)")
    assert pane._end_dir_edit.placeholderText() == "(block library)/System/End Types"
    tips = {b.toolTip() for b in pane.findChildren(QPushButton)}
    assert "Choose the end types folder" in tips
    assert "Use the default (<block library>/System/End Types)" in tips
    pane._end_dir_edit.setText(str(tmp_path / "e"))
    pane.apply()
    assert app_data.end_types_dir() == str(tmp_path / "e")
    pane2 = pd.GeneralPane()
    pane2.load()
    assert pane2._end_dir_edit.text() == str(tmp_path / "e")
    pane2._end_dir_edit.setText("changed")
    pane2.revert()
    assert pane2._end_dir_edit.text() == str(tmp_path / "e")
    pane2._end_dir_edit.clear()
    pane2.apply()
    assert app_data.end_types_dir() == os.path.join(
        app_data.block_library_dir(), "System", "End Types")


# ── choices ─────────────────────────────────────────────────────────────────

def test_end_choices_none_then_project_then_folder_only_end_blocks(end_dir):
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    end_id(ms, name="Dot")
    hidden(ms)                                     # a linetype: never offered
    block_library.save_to_library(make_linetype("Center"), root=str(end_dir))
    tick = _folder(end_dir)
    ch = end_choices(ms.block_registry)
    assert ch == [("None", ss.NONE), ("Arrow", a),
                  ("Dot", ch[2][1]), ("Tick", tick.id)]


def test_folder_end_in_project_is_listed_once_and_names_are_unique(end_dir):
    ms = Model_Space()
    e = _folder(end_dir, name="Arrow")
    ms.register_block_definition(e)
    other = _folder(end_dir, name="Arrow", series="Other")
    labels = [n for n, _ in end_choices(ms.block_registry)]
    assert labels == ["None", "Arrow", "Arrow (library)"]
    assert end_ref_from_value("Arrow (library)", ms.block_registry) == other.id


def test_exclude_and_keyword_labels(end_dir):
    ms = Model_Space()
    a = end_id(ms, name="Arrow")
    assert [n for n, _ in end_choices(ms.block_registry, {a})] == ["None"]
    assert end_ref_from_value("None", ms.block_registry) == ss.NONE
    assert end_ref_from_value("By Linetype (Arrow)", ms.block_registry) \
        == ss.BY_LINETYPE
    assert end_ref_from_value("Arrow", ms.block_registry) == a
    assert end_ref_from_value("Missing: x", ms.block_registry) is None
    assert end_ref_from_value("Nope", ms.block_registry) is None


def test_capability_choices_is_the_one_source(qapp):
    """linetype / pattern pickers are thin callers: same generic rule."""
    from firepro3d.hatch_patterns import tile_choices
    from firepro3d.linetype_choices import linetype_choices
    ms = Model_Space()
    lid = hidden(ms)
    assert linetype_choices(ms.block_registry)[0] == ("Continuous", "continuous")
    assert (lid in [r for _n, r in linetype_choices(ms.block_registry)])
    assert capability_choices("repeat", lambda: [], ms.block_registry,
                              fixed=(("Continuous", "continuous"),)) \
        == linetype_choices(ms.block_registry, ())
    assert tile_choices(ms.block_registry, include_library=False) == \
        capability_choices("tile", lambda: [], ms.block_registry,
                           valid=lambda d: True, include_folder=False)


# ── load on pick ────────────────────────────────────────────────────────────

def test_ensure_end_available_loads_a_folder_end_in_one_step(end_dir):
    ms = Model_Space()
    e = _folder(end_dir)
    pos0 = ms._undo_pos
    assert ensure_end_available(e.id, ms) is True
    assert ms.get_block_definition(e.id) is not None
    assert ms._undo_pos == pos0 + 1
    for kw in (ss.NONE, ss.BY_LINETYPE, None):
        assert ensure_end_available(kw, ms) is True     # nothing to load


def test_failed_folder_load_returns_false(end_dir, monkeypatch):
    from firepro3d import themed_message
    shown = []
    monkeypatch.setattr(themed_message, "themed_info",
                        lambda *a, **k: shown.append(a))
    ms = Model_Space()
    e = _folder(end_dir, name="Tick")
    ms.register_block_definition(v_end(name="Tick"))  # clash: same L/S/name
    assert ensure_end_available(e.id, ms) is False
    assert ms.get_block_definition(e.id) is None and shown


# ── labels (stroke_style) ───────────────────────────────────────────────────

def test_end_labels(qapp):
    ms = Model_Space()
    reg = ms.block_registry
    a = end_id(ms, name="Arrow")
    lt = make_linetype("Hidden")
    rep = lt.repeat
    rep["ends"] = {"start": a}
    lt.set_repeat(rep)
    ms.register_block_definition(lt)
    assert ss.end_label(ss.BY_LINETYPE, lt.id, reg, which="start") == \
        "By Linetype (Arrow)"
    assert ss.end_label(ss.BY_LINETYPE, lt.id, reg, which="finish") == \
        "By Linetype (None)"
    assert ss.end_label(ss.BY_LINETYPE, ss.CONTINUOUS, reg) == "By Linetype (None)"
    assert ss.end_label(ss.NONE, lt.id, reg) == "None"
    assert ss.end_label(a, ss.CONTINUOUS, reg) == "Arrow"
    assert ss.end_label("deadbeef", ss.CONTINUOUS, reg) == "Missing: deadbeef"
    assert ss.end_label(lt.id, ss.CONTINUOUS, reg) == "Missing: Hidden"
    assert ss.end_from_label("None") == ss.NONE
    assert ss.end_from_label("By Linetype (Arrow)") == ss.BY_LINETYPE
    assert ss.end_from_label("Arrow") is None
