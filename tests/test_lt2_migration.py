"""LT2-2 / G9 (data half) / T-snap -- definition primitives migrate on load."""
import copy

from firepro3d.block_definition import BlockDefinition
from firepro3d.model_space import Model_Space

_LEGACY_LINE = {"type": "draw_line", "pt1": [0, 0], "pt2": [10, 0],
                "color": "#ff0000", "lineweight": 3.0}


def _legacy_def_dict():
    return {"schema": 1, "id": "d1", "version": 7, "name": "N",
            "library": "L", "series": "S", "origin": [0, 0],
            "primitives": [copy.deepcopy(_LEGACY_LINE),
                           {"type": "text", "border_weight": "Medium"}]}


def test_from_dict_migrates_without_version_bump():
    d = BlockDefinition.from_dict(_legacy_def_dict())
    assert d.version == 7
    line = d.primitives[0]
    assert "lineweight" not in line and line["style"]["colour"] == "#ff0000"
    assert line["style"]["weight"] == "by_block"
    assert d.primitives[1] == {"type": "text", "border_weight": "Medium"}


def test_from_dict_does_not_alias_the_input():
    raw = _legacy_def_dict()
    d = BlockDefinition.from_dict(raw)
    d.primitives[0]["style"]["weight"] = "Heavy"
    assert "style" not in raw["primitives"][0]


def test_snapshot_isolated_from_in_place_edit(qapp):
    """T-snap: an in-place edit of a live primitive dict never rewrites undo."""
    ms = Model_Space()
    ms.register_block_definition(BlockDefinition.from_dict(_legacy_def_dict()))
    ms.push_undo_state()
    snap = ms._undo_stack[ms._undo_pos]
    ms.block_registry.get("d1").primitives[1]["border_weight"] = "Heavy"
    assert snap["block_definitions"]["d1"]["primitives"][1]["border_weight"] == "Medium"
