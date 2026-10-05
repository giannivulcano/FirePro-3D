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
    assert line["style"]["weight"] == "by_linetype"   # WM-9 (was by_block)
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


# ---- Task 10: G9 legacy-print parity + G8a round-trip -----------------------
import json

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests.test_lt1_block_paper import _HALF_LEN, _block_strokes, _export

# Base-commit (8ee2ad3) widths in mm, measured by running this scenario in a
# worktree of that commit under the conftest QSettings isolation (factory
# table, BW mode). Identical at both scales: Blocks weight is scale-free on paper.
_BASE_WIDTHS = {0.02: 0.17990455163849722, 0.01: 0.17990455163849722}


@pytest.mark.parametrize("scale", [0.02, 0.01])
def test_g9_legacy_block_prints_identically(qapp, tmp_path, scale):
    save_paper_color_mode(PaperColorMode.BW)
    ms = Model_Space()
    legacy = {"schema": 1, "id": "leg", "version": 3, "name": "Leg",
              "library": "L", "series": "S", "origin": [0, 0],
              "primitives": [{"type": "draw_line",
                              "pt1": [-_HALF_LEN, 0], "pt2": [_HALF_LEN, 0],
                              "color": "#ffffff", "lineweight": 3.0}]}
    ms.register_block_definition(BlockDefinition.from_dict(legacy))
    ms.place_block_instance("leg", (0.0, 0.0), level=ms.active_level)
    widths = [w for w, _ in _block_strokes(
        _export(tmp_path, ms, scale, "g9.pdf"), scale)]
    assert widths and all(w == pytest.approx(_BASE_WIDTHS[scale], abs=1e-3)
                          for w in widths)


def test_g8a_fpd_round_trip_keeps_full_record(qapp, tmp_path):
    from firepro3d.geometry_2d import LineItem
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(10, 0), "#ff0000")
    # WM-9: by_block is no longer storable; a linetype id is the marker.
    ln.style.update(weight="Heavy", linetype="lt-marker")
    ln.style["finish"]["visible"] = False
    d = BlockDefinition.new(name="R", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0, 0))
    ms.register_block_definition(d)
    path = tmp_path / "rt.fpd"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 10
    ms2 = Model_Space()
    ms2.load_from_file(str(path))
    assert ms2.block_registry.get(d.id).primitives[0]["style"] == ln.style


def test_item_from_dict_never_shares_caller_style(qapp):
    """M4: _geom2d_from_dict builds a fresh record even for a dict without
    "type" (no aliasing of the caller's style dict)."""
    from firepro3d.geometry_2d import LineItem
    from firepro3d.stroke_style import default_style
    st = default_style("#00ff00")
    st["weight"] = "Heavy"
    item = LineItem.from_dict({"pt1": [0, 0], "pt2": [10, 0], "style": st})
    assert item.style == st and item.style is not st
    item.style["finish"]["visible"] = False
    assert st["finish"]["visible"] is True
    legacy = LineItem.from_dict({"pt1": [0, 0], "pt2": [10, 0],
                                 "color": "#123456", "lineweight": 3.0})
    assert legacy.style == default_style("#123456")
