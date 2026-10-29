"""L283 -- per-item ``_display_overrides`` (Model Browser Hide = visible, Fill Type
section override = section_type, Graphic Override colours) round-trip to_dict /
from_dict on every DisplayableItemMixin holder: undo snapshot, .fpd and paste.
One helper pair on the mixin (display_overrides_to_dict / _from_dict)."""
import json

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import fill_types as ft
from firepro3d.fill_layers import BackgroundLayer, FillLayers
from firepro3d.floor_slab import FloorSlab
from firepro3d.gridline import GridlineItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space

RED = FillLayers(BackgroundLayer("#ff0000", 1.0))
SQUARE = [QPointF(0.0, 0.0), QPointF(2000.0, 0.0), QPointF(2000.0, 2000.0), QPointF(0.0, 2000.0)]


def test_mixin_helpers_write_sparsely_and_read_missing_as_empty(qapp):
    slab = FloorSlab(points=list(SQUARE))
    assert "display_overrides" not in slab.to_dict()                  # untouched: no key
    slab._display_overrides["visible"] = False
    slab._display_overrides["color"] = "#112233"
    d = slab.to_dict()
    assert d["display_overrides"] == {"visible": False, "color": "#112233"}
    d["display_overrides"]["color"] = "#ffffff"                       # a copy, not the live dict
    assert slab._display_overrides["color"] == "#112233"
    back = FloorSlab.from_dict(d)
    assert back._display_overrides == {"visible": False, "color": "#ffffff"}
    assert back.isVisible() is False                                  # a carried Hide applies
    assert back._display_overrides is not d["display_overrides"]      # no aliasing of the record
    assert FloorSlab.from_dict({"points": [[0, 0], [1, 0], [1, 1]], "display_overrides": 7})._display_overrides == {}
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(5000.0, 0.0), label="A")
    gl._display_overrides["visible"] = False
    g = gl.to_dict()
    assert g["display_overrides"] == {"visible": False}
    gl2 = GridlineItem.from_dict(g)
    assert gl2._display_overrides == {"visible": False} and gl2.isVisible() is False
    assert gl2._display_overrides is not g["display_overrides"]


def test_mixin_from_dict_routes_section_type_through_canonical_id(qapp, monkeypatch):
    """The helper re-points section_type through fill_types.canonical_id (HF5 VC9 M2).
    The real alias (a name-duplicate type loaded from a file) is guarded end to end by
    tests/test_hf5_fill_types_persist.py; FillTypeTable.add refuses a duplicate name
    in memory (fill_types.py:87-94), so the alias cannot be built here without a file."""
    ft.reset_project_table()
    ft.project_table().add(ft.FillType("keep", "Red", RED))
    slab = FloorSlab(points=list(SQUARE))
    slab._display_overrides["section_type"] = "keep"
    rec = slab.to_dict()
    assert FloorSlab.from_dict(rec)._display_overrides["section_type"] == "keep"   # a kept id is itself
    assert FloorSlab.from_dict({"points": [[0, 0], [1, 0], [1, 1]],
                                "display_overrides": {"section_type": "nope"}}
                               )._display_overrides["section_type"] == "nope"      # unknown id unchanged
    seen = []
    monkeypatch.setattr(ft, "canonical_id", lambda tid, table=None: seen.append(tid) or f"kept-{tid}")
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(5000.0, 0.0), label="A")
    gl._display_overrides["section_type"] = "alias"
    assert GridlineItem.from_dict(gl.to_dict())._display_overrides["section_type"] == "kept-alias"
    assert seen == ["alias"]                     # exactly one re-point, through the module attribute
    ft.reset_project_table()
