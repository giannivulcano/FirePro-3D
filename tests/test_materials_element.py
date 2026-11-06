"""Material on walls and floors: save, undo, panel, legacy conversion (AC4, AC5, AC8)."""
import json

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import fill_types as ft
from firepro3d import materials as mt
from firepro3d.constants import MATERIAL_NONE_ID
from firepro3d.fill_layers import BackgroundLayer, FillLayers
from firepro3d.floor_slab import FloorSlab
from firepro3d.model_space import Model_Space
from firepro3d.wall import WallSegment

RED = FillLayers(BackgroundLayer("#ff0000", 1.0))
SQUARE = [QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)]


@pytest.fixture(autouse=True)
def _fresh_tables():
    ft.reset_project_table()
    mt.reset_project_table()
    yield
    ft.reset_project_table()
    mt.reset_project_table()


def _wall(ms):
    w = WallSegment(QPointF(0, 0), QPointF(4000, 0))
    ms.addItem(w)
    ms._walls.append(w)
    return w


def _slab(ms):
    s = FloorSlab(list(SQUARE))
    ms.addItem(s)
    ms._floor_slabs.append(s)
    return s


def _reload(ms, tmp_path):
    p = str(tmp_path / "m.fpd")
    ms.save_to_file(p)
    ft.reset_project_table()
    mt.reset_project_table()
    out = Model_Space()
    out.load_from_file(p)
    return out, p


def test_assignments_and_table_survive_save_and_reload(qapp, tmp_path):
    ms = Model_Space()
    w, s = _wall(ms), _slab(ms)
    table = mt.project_table()
    brick = table.by_name("Brick")
    custom = table.add(mt.Material("custom-id", "Custom", ft.project_table().by_name("Diagonal").id))
    table.set_default("Floor", custom.id)
    w.set_property("Building Material", "Brick")
    s.set_property("Building Material", "Custom")
    out, _ = _reload(ms, tmp_path)
    assert out._walls[0].material_id == brick.id
    assert out._floor_slabs[0].material_id == "custom-id"
    assert mt.project_table().get("custom-id").name == "Custom"
    assert mt.project_table().default_for("Floor") == "custom-id"


def test_a_none_element_writes_no_key(qapp):
    ms = Model_Space()
    assert "material" not in _wall(ms).to_dict()
    assert "material" not in _slab(ms).to_dict()


def test_a_file_with_no_materials_key_opens_on_none_with_starters(qapp, tmp_path):
    ms = Model_Space()
    _wall(ms)
    p = str(tmp_path / "old.fpd")
    ms.save_to_file(p)
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    data.pop("materials")
    # A true old file predates the starters: strip their Fill Types too, so the
    # load order (Fill Types, then Materials) is what puts them back.
    starters = {"Concrete", "Brick", "Cross Hatch", "Diagonal"}
    data["fill_types"] = [r for r in data["fill_types"] if r.get("name") not in starters]
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    out = Model_Space()
    out.load_from_file(p)
    assert out._walls[0].material_id == MATERIAL_NONE_ID
    assert mt.project_table().by_name("Concrete") is not None
    assert ft.project_table().get(mt.project_table().by_name("Concrete").fill_type) is not None


def test_instance_override_becomes_a_material_with_the_same_look(qapp, tmp_path):
    ms = Model_Space()
    ft.project_table().add(ft.FillType("red-id", "Red Cut", RED))
    w, s, plain = _wall(ms), _slab(ms), _wall(ms)
    w._display_overrides["section_type"] = "red-id"
    s._display_overrides["section_type"] = "red-id"
    out, _ = _reload(ms, tmp_path)
    ow, os_, op = out._walls[0], out._floor_slabs[0], out._walls[1]
    assert mt.project_table().by_name("Red Cut") is not None
    assert mt.fill_type_of(ow) == "red-id" and mt.fill_type_of(os_) == "red-id"
    assert ow.material_id == os_.material_id
    assert "section_type" not in ow._display_overrides
    assert "section_type" not in os_._display_overrides
    assert op.material_id == MATERIAL_NONE_ID


def test_conversion_reuses_a_material_already_on_that_type_and_never_retakes_a_name(qapp):
    table = mt.project_table()
    # the fixture's materials reset already put a "Brick" Fill Type in the table;
    # replace it with a clash on that name whose id the starter material does not use
    ft.reset_project_table()
    ft.project_table().add(ft.FillType("red-id", "Brick", RED))     # a clash with the starter name
    data = {"pt1": [0, 0], "pt2": [1000, 0], "display_overrides": {"section_type": "red-id"}}
    w = WallSegment.from_dict(data)
    assert mt.fill_type_of(w) == "red-id"
    assert table.by_name("Brick").fill_type != "red-id"
    again = WallSegment.from_dict(data)
    assert again.material_id == w.material_id


def test_a_saved_material_wins_over_a_stale_override_key(qapp):
    brick = mt.project_table().by_name("Brick")
    ft.project_table().add(ft.FillType("red-id", "Red Cut", RED))
    w = WallSegment.from_dict({"pt1": [0, 0], "pt2": [1000, 0], "material": brick.id,
                               "display_overrides": {"section_type": "red-id"}})
    assert w.material_id == brick.id
    assert "section_type" not in w._display_overrides


def test_legacy_section_keys_convert_too(qapp):
    w = WallSegment.from_dict({"pt1": [0, 0], "pt2": [1000, 0], "display_overrides": {
        "section": "#ff0000", "section_pattern": "horizontal"}})
    t = ft.project_table().get(mt.fill_type_of(w))
    assert t.layers.background.color == "#ff0000"
    assert t.layers.pattern.ref == "builtin-hatch-horizontal"
    assert not w._display_overrides


def test_unknown_id_reads_none_and_stays_stored(qapp):
    w = WallSegment.from_dict({"pt1": [0, 0], "pt2": [1000, 0], "material": "other-project"})
    assert w.get_properties()["Building Material"]["value"] == "None"
    assert w.to_dict()["material"] == "other-project"


def test_row_lists_the_table_for_wall_and_slab(qapp):
    ms = Model_Space()
    for it in (_wall(ms), _slab(ms)):
        row = it.get_properties()["Building Material"]
        assert row["type"] == "enum"
        assert row["options"] == [m.name for m in mt.project_table().all()]
        assert row["value"] == "None"


@pytest.mark.parametrize("make", [_wall, _slab])
def test_undo_restores_a_changed_material(qapp, make):
    ms = Model_Space()
    make(ms)
    ms.push_undo_state()
    brick = mt.project_table().by_name("Brick")
    target = (ms._walls or ms._floor_slabs)[0]
    target.set_property("Building Material", "Brick")     # the setter pushes its own step
    assert target.material_id == brick.id
    ms.undo()
    live = (ms._walls or ms._floor_slabs)[0]
    assert live.material_id == MATERIAL_NONE_ID


def test_setting_the_same_material_pushes_no_step(qapp):
    ms = Model_Space()
    w = _wall(ms)
    calls = []
    ms.request_undo_push = lambda: calls.append(1)
    w.set_property("Building Material", "None")
    assert not calls
    w.set_property("Building Material", "Brick")
    assert len(calls) == 1
    w.set_property("Building Material", "No Such Material")
    assert len(calls) == 1 and w.material_id == mt.project_table().by_name("Brick").id


def test_mixed_wall_pipe_selection_leaves_the_pipe_material(qapp):
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    from firepro3d.property_manager import PropertyManager
    ms = Model_Space()
    w = _wall(ms)
    n1, n2 = Node(0, 0), Node(1000, 0)
    pipe = Pipe(n1, n2)
    before = pipe.get_properties()["Material"]["value"]
    panel = PropertyManager()
    panel._targets = [w, pipe]
    panel._apply_property("Building Material", "Brick")
    assert w.material_id == mt.project_table().by_name("Brick").id
    assert pipe.get_properties()["Material"]["value"] == before
    assert "Building Material" not in pipe.get_properties()
