"""SB4g T6 -- the Symbol row's one choice list (design D7 / AC3): System symbols of
the category, then eligible user-library blocks; unflagged / annotative /
other-category blocks never listed; a kept id shown "(missing)" / "(not eligible)"."""
import json
from pathlib import Path

from PyQt6.QtCore import QPointF

from firepro3d import annotation_choices as ac
from firepro3d.app_data import block_library_dir
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def _lib(name, block_id, symbol_for="Sprinkler", scale_mode="real_size"):
    d = BlockDefinition.new(name=name, library="Heads", series="Mine", origin=(0.0, 0.0),
                            primitives=[CircleItem(QPointF(0.0, 0.0), 150.0).to_dict()])
    d.id, d.scale_mode, d.symbol_for = block_id, scale_mode, symbol_for
    folder = Path(block_library_dir()) / "Heads" / "Mine"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.fpdb").write_text(json.dumps(d.to_dict()), encoding="utf-8")


def _labels(ms, cat, current=None):
    return [(c.label, c.block_id, c.path is not None)
            for c in ac.symbol_choices(ms, cat, current=current)]


def test_sprinkler_list_is_system_then_flagged_library(qapp, real_system_library):
    _lib("MyHead", "lib-head-1")                                  # flagged: listed
    _lib("Plain", "lib-plain-1", symbol_for="")                   # unflagged: never
    _lib("Annot", "lib-annot-1", scale_mode="annotative")         # annotative: never
    _lib("MySupply", "lib-ws-1", symbol_for="Water Supply")       # other category: never
    assert _labels(_scene(), "Sprinkler") == [
        ("Sprinkler0 (System)", "system-symbols-sprinkler0", False),
        ("Sprinkler1 (System)", "system-symbols-sprinkler1", False),
        ("Sprinkler2 (System)", "system-symbols-sprinkler2", False),
        ("MyHead (Library)", "lib-head-1", True)]


def test_water_supply_and_riser_lists(qapp, real_system_library):
    _lib("MySupply", "lib-ws-1", symbol_for="Water Supply")
    ms = _scene()
    assert _labels(ms, "Water Supply") == [
        ("Water Supply (System)", "system-symbols-watersupply", False),
        ("MySupply (Library)", "lib-ws-1", True)]
    assert _labels(ms, "Riser") == [("Riser (System)", "system-symbols-riser", False)]


def test_embedded_symbol_lists_once_from_the_project(qapp, real_system_library):
    ms = _scene()
    ms.symbol_block("Sprinkler")                                  # embeds sprinkler0
    labels = [lab for lab, _b, _p in _labels(ms, "Sprinkler")]
    assert labels.count("Sprinkler0 (System)") == 1


def test_kept_current_is_shown_missing_or_not_eligible(qapp, real_system_library):
    _lib("Plain", "lib-plain-1", symbol_for="")
    ms = _scene()
    assert _labels(ms, "Sprinkler", current="ghost")[-1] == ("ghost (missing)", "ghost", False)
    assert _labels(ms, "Sprinkler", current="lib-plain-1")[-1] == \
        ("Plain (not eligible)", "lib-plain-1", False)
    assert _labels(ms, "Sprinkler", current="system-symbols-riser")[-1] == \
        ("Riser (not eligible)", "system-symbols-riser", False)


def test_room_choices_unchanged_by_the_predicate_parameter(qapp, real_system_library):
    """choices() without eligible= is the SB3b list: no symbol block leaks into it."""
    assert all("symbols" not in c.block_id for c in ac.choices(_scene(), "Room"))


def test_project_embedded_non_symbols_never_listed(qapp, real_system_library):
    ms = _scene()
    for bid, name, sf, sm in [("proj-plain", "PPlain", "", "real_size"),
                              ("proj-annot", "PAnnot", "Sprinkler", "annotative"),
                              ("proj-ws", "PWs", "Water Supply", "real_size"),
                              ("proj-ok", "POk", "Sprinkler", "real_size")]:
        d = BlockDefinition.new(name=name, library="Heads", series="Mine", origin=(0.0, 0.0),
                                primitives=[CircleItem(QPointF(0.0, 0.0), 150.0).to_dict()])
        d.id, d.scale_mode, d.symbol_for = bid, sm, sf
        ms.register_block_definition(d)                 # the scene's real embed registry
    ids = [b for _l, b, _p in _labels(ms, "Sprinkler")]
    assert "proj-ok" in ids
    assert not {"proj-plain", "proj-annot", "proj-ws"} & set(ids)
