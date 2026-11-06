"""Materials table, store and resolver (docs/specs/materials.md)."""
import pytest

from firepro3d import fill_types as ft
from firepro3d import materials as mt
from firepro3d.constants import MATERIAL_NONE_ID, TOKEN_ELEMENT
from firepro3d.fill_layers import BackgroundLayer, FillLayers


@pytest.fixture(autouse=True)
def _fresh_tables():
    ft.reset_project_table()
    mt.reset_project_table()
    yield
    ft.reset_project_table()
    mt.reset_project_table()


def test_starters_are_none_plus_four_with_their_fill_types():
    names = [m.name for m in mt.project_table().all()]
    assert names == ["None", "Brick", "Concrete", "Steel Framed", "Wood Framed"]
    table = ft.project_table()
    by = {m.name: m for m in mt.project_table().all()}
    assert by["None"].fill_type is None
    assert table.get(by["Concrete"].fill_type).layers.pattern.ref == "builtin-hatch-concrete"
    assert table.get(by["Brick"].fill_type).layers.pattern.ref == "builtin-hatch-brick"
    assert table.get(by["Wood Framed"].fill_type).layers.pattern.ref == "builtin-hatch-cross-hatch"
    assert table.get(by["Steel Framed"].fill_type).layers.pattern.ref == "builtin-hatch-diagonal"
    assert table.get(by["Brick"].fill_type).layers.pattern.color == TOKEN_ELEMENT
    assert table.get(by["Brick"].fill_type).layers.background is None
    assert mt.project_table().default_for("Wall") == MATERIAL_NONE_ID
    assert mt.project_table().default_for("Floor") == MATERIAL_NONE_ID


def test_starter_fill_type_keeps_a_project_type_of_that_name():
    ft.reset_project_table()      # the fixture's materials reset already added the starter types
    keep = ft.project_table().add(ft.FillType("k", "Concrete", FillLayers(BackgroundLayer("#123456", 1.0))))
    mt.reset_project_table()
    assert mt.project_table().by_name("Concrete").fill_type == keep.id


def test_none_is_permanent():
    table = mt.project_table()
    with pytest.raises(ValueError):
        table.remove(MATERIAL_NONE_ID)
    none = table.get(MATERIAL_NONE_ID)
    with pytest.raises(ValueError):
        table.replace(mt.Material(none.id, "Nothing", None))
    table.replace(mt.Material(none.id, none.name, "some-type"))      # repoint is allowed
    assert table.get(MATERIAL_NONE_ID).fill_type == "some-type"


def test_names_are_unique_casefolded():
    with pytest.raises(ValueError):
        mt.project_table().add(mt.Material("x", "concrete", None))


def test_payload_round_trip_and_defaults():
    table = mt.project_table()
    brick = table.by_name("Brick")
    table.set_default("Wall", brick.id)
    back = mt.MaterialTable.from_payload(table.to_payload())
    assert [m.name for m in back.all()] == [m.name for m in table.all()]
    assert back.default_for("Wall") == brick.id
    assert back.default_for("Floor") == MATERIAL_NONE_ID


def test_payload_without_none_row_gets_one_and_a_stale_default_reads_none():
    back = mt.MaterialTable.from_payload(
        {"rows": [{"id": "a", "name": "A", "fill_type": None}],
         "defaults": {"Wall": "gone"}})
    assert back.get(MATERIAL_NONE_ID) is not None
    assert back.default_for("Wall") == MATERIAL_NONE_ID


@pytest.mark.parametrize("payload", [None, {}, [], {"rows": []}, {"rows": "x"}])
def test_load_without_rows_installs_starters(payload):
    mt.load_project_materials(payload)
    assert mt.project_table().by_name("Concrete") is not None


def test_set_project_table_notifies_the_fill_type_bus():
    hits = []
    ft.fill_type_bus().changed.connect(lambda: hits.append(1))
    mt.set_project_table(mt.project_table().copy())
    assert hits


def test_fill_type_of_reads_the_table_each_call():
    class Item:
        material_id = "m"
    table = mt.project_table()
    table.add(mt.Material("m", "M", "t1"))
    assert mt.fill_type_of(Item()) == "t1"
    table.replace(mt.Material("m", "M", "t2"))
    assert mt.fill_type_of(Item()) == "t2"


def test_unknown_or_missing_id_reads_as_the_none_material():
    class Unknown:
        material_id = "from-another-project"
    assert mt.fill_type_of(Unknown()) is None
    assert mt.fill_type_of(object()) is None
    table = mt.project_table()
    none = table.get(MATERIAL_NONE_ID)
    table.replace(mt.Material(none.id, none.name, "tid"))
    assert mt.fill_type_of(Unknown()) == "tid"
