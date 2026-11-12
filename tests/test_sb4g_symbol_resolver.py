"""SB4g T5 -- Model_Space.symbol_block (design D4, R8 / AC9 / G6 resolver half):
chosen id -> System default; eligibility = real size + symbol_for; one notice per
(category, id); the memo lives in _annot_memo (cleared on blockDefinitionsChanged)."""
import json
import logging
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.app_data import block_library_dir
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.system_blocks import SYMBOL_DEFAULTS, eligible_symbol


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def _notices(ms):
    out = []
    ms._show_status = lambda msg, timeout=5000: out.append(msg)
    return out


def _symbol_def(name, symbol_for="Sprinkler", scale_mode="real_size", block_id=None, r=150.0):
    d = BlockDefinition.new(name=name, library="Heads", series="Mine", origin=(0.0, 0.0),
                            primitives=[CircleItem(QPointF(0.0, 0.0), r).to_dict()])
    d.scale_mode, d.symbol_for = scale_mode, symbol_for
    if block_id:
        d.id = block_id
    return d


def _lib_file(d):
    folder = Path(block_library_dir()) / d.library / d.series
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{d.name}.fpdb").write_text(json.dumps(d.to_dict()), encoding="utf-8")


def test_defaults_table_names_the_seeds():
    assert SYMBOL_DEFAULTS == {"Sprinkler": "system-symbols-sprinkler0",
                               "Water Supply": "system-symbols-watersupply",
                               "Riser": "system-symbols-riser"}


def test_eligible_symbol_rule(qapp):
    assert eligible_symbol(_symbol_def("A"), "Sprinkler")
    assert not eligible_symbol(_symbol_def("B"), "Water Supply")              # other category
    assert not eligible_symbol(_symbol_def("C", symbol_for=""), "Sprinkler")  # unflagged
    assert not eligible_symbol(_symbol_def("D", scale_mode="annotative"), "Sprinkler")
    assert not eligible_symbol(None, "Sprinkler")


@pytest.mark.parametrize("cat", ["Sprinkler", "Water Supply", "Riser"])
def test_none_resolves_the_system_default_outside_undo(cat, qapp, real_system_library):
    ms = _scene()
    n = len(ms._undo_stack)
    d = ms.symbol_block(cat)
    assert d is not None and d.id == SYMBOL_DEFAULTS[cat]
    assert d.id in ms._block_definitions and len(ms._undo_stack) == n


def test_chosen_system_variant_wins(qapp, real_system_library):
    assert _scene().symbol_block("Sprinkler", "system-symbols-sprinkler2").id == \
        "system-symbols-sprinkler2"


def test_chosen_flagged_library_block_is_embedded(qapp, real_system_library):
    _lib_file(_symbol_def("MyHead", block_id="lib-head-1"))
    ms = _scene()
    d = ms.symbol_block("Sprinkler", "lib-head-1")
    assert d is not None and d.id == "lib-head-1" and "lib-head-1" in ms._block_definitions


def test_g6_missing_id_falls_back_with_one_notice(qapp, real_system_library, caplog):
    ms = _scene()
    notices = _notices(ms)
    with caplog.at_level(logging.WARNING):
        d = ms.symbol_block("Sprinkler", "ghost-head")
    assert d.id == "system-symbols-sprinkler0"
    assert len(notices) == 1 and "ghost-head" in notices[0]
    assert any("ghost-head" in r.getMessage() for r in caplog.records)
    ms._annot_memo.clear()                                   # a registry change clears the memo
    assert ms.symbol_block("Sprinkler", "ghost-head").id == "system-symbols-sprinkler0"
    assert len(notices) == 1                                 # once per (category, id)


@pytest.mark.parametrize("bad", [
    {"symbol_for": ""}, {"symbol_for": "Riser"}, {"scale_mode": "annotative"}])
def test_ineligible_project_block_is_treated_as_missing(bad, qapp, real_system_library):
    ms = _scene()
    d = _symbol_def("Odd", block_id="odd-1", **bad)
    ms.register_block_definition(d)
    notices = _notices(ms)
    assert ms.symbol_block("Sprinkler", "odd-1").id == "system-symbols-sprinkler0"
    assert len(notices) == 1


def test_other_categorys_system_symbol_is_not_eligible(qapp, real_system_library):
    assert _scene().symbol_block("Sprinkler", "system-symbols-riser").id == \
        "system-symbols-sprinkler0"


def test_memo_follows_the_registry(qapp, real_system_library):
    ms = _scene()
    assert ms.symbol_block("Sprinkler", "late-1").id == "system-symbols-sprinkler0"
    ms.register_block_definition(_symbol_def("Late", block_id="late-1"))   # blockDefinitionsChanged
    assert ms.symbol_block("Sprinkler", "late-1").id == "late-1"


def test_nothing_resolves_returns_none(qapp):
    """Empty System tier (conftest default) and no chosen id: None, no exception."""
    assert _scene().symbol_block("Riser") is None


def test_s5_embed_during_resolve_does_not_refresh_and_memo_is_written(
        qapp, real_system_library):
    """S5: the embed's blockDefinitionsChanged must not run the refresh chain
    mid-resolve; the outer resolve writes the memo; the caller's flag survives."""
    _lib_file(_symbol_def("MyHead", block_id="lib-head-1"))
    ms = _scene()
    calls = []
    ms.refresh_annotation_tags = lambda: calls.append(1)     # the refresh chain's entry
    d = ms.symbol_block("Sprinkler", "lib-head-1")           # embeds the library file
    assert d is not None and d.id == "lib-head-1"
    assert calls == []                                       # skipped while resolving
    assert ms._annot_memo[("symbol", "Sprinkler", "lib-head-1")] == "lib-head-1"
    assert ms._annot_resolving is False
    ms._annot_resolving = True                               # a nested call ...
    ms._annot_memo.clear()
    ms.symbol_block("Water Supply")
    assert ms._annot_resolving is True                       # ... keeps the outer flag
    ms._annot_resolving = False
