"""HF5 Task 5 -- region panel rows."""
from PyQt6.QtCore import QPointF

from firepro3d import fill_types as ft
from firepro3d.constants import FILL_TYPE_CUSTOM_LABEL
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.filled_region import FilledRegionItem
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space

RED = FillLayers(BackgroundLayer("#ff0000", 1.0))


# -- helpers copied verbatim from tests/test_filled_region.py ----------------
def square_pieces(size=100.0):
    a, b, c, d = QPointF(10, 10), QPointF(10 + size, 10), QPointF(10 + size, 10 + size), QPointF(10, 10 + size)
    return [LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]


def editor_scene():
    """A Block Editor scene (containment C1) -- the only scene that holds regions."""
    return Model_Space(scene_role="block_editor")


def add_region(scene, region):
    scene.addItem(region)
    scene._filled_regions.append(region)
    return region
# ---------------------------------------------------------------------------


def _square():
    """100x100 square at (10,10), no islands."""
    return FilledRegionItem.from_pieces([square_pieces()])


def test_type_row_lists_custom_and_types(qapp):
    ft.set_project_table(ft.FillTypeTable([ft.FillType("red", "Red", RED)]))
    row = _square().get_properties()["Fill Type"]
    assert row["type"] == "enum" and row["value"] == FILL_TYPE_CUSTOM_LABEL
    assert row["options"][0] == FILL_TYPE_CUSTOM_LABEL and "Red" in row["options"]


def test_pick_type_is_one_undo_step(qapp):
    ft.set_project_table(ft.FillTypeTable([ft.FillType("red", "Red", RED)]))
    sc = editor_scene()
    r = add_region(sc, _square())
    sc.push_undo_state()
    r.set_property("Fill Type", "Red")
    assert r.fill_type == "red"
    sc.undo()
    assert sc._filled_regions[0].fill_type is None
    sc.redo()
    assert sc._filled_regions[0].fill_type == "red"


def test_pick_custom_and_missing_label(qapp):
    ft.set_project_table(ft.FillTypeTable([ft.FillType("red", "Red", RED)]))
    r = _square()
    r.set_property("Fill Type", "Red")
    r.set_property("Fill Type", FILL_TYPE_CUSTOM_LABEL)
    assert r.fill_type is None and r.fill_layers == RED
    r.set_fill_type("gone")
    r.set_property("Fill Type", "? gone")           # the missing marker is not a pick
    assert r.fill_type == "gone"


def test_override_shows_reset_button_that_clears_it(qapp):
    ft.set_project_table(ft.FillTypeTable([ft.FillType("red", "Red", RED)]))
    r = _square()
    r.set_fill_type("red")
    assert "Reset Fill to type" not in r.get_properties()
    r.fill_layers = FillLayers(BackgroundLayer("#ff0000", 0.5))
    props = r.get_properties()
    row = props["Reset Fill to type"]
    assert row["type"] == "button" and "opacity" in row["tooltip"]
    keys = list(props)
    assert keys.index("Reset Fill to type") == keys.index("Fill") + 1
    row["callback"]()
    assert "fill" not in r.to_dict()


def test_reset_is_per_layer(qapp):
    both = FillLayers(BackgroundLayer("#ff0000", 1.0), PatternLayer("diagonal", "#000000", 1.0, 1.0))
    ft.set_project_table(ft.FillTypeTable([ft.FillType("t", "T", both)]))
    r = _square()
    r.set_fill_type("t")
    r.fill_layers = FillLayers(BackgroundLayer("#ff0000", 0.5), PatternLayer("diagonal", "#000000", 1.0, 3.0))
    r.get_properties()["Reset Fill to type"]["callback"]()
    d = r.to_dict()
    assert "background" not in d["fill"] and d["fill"]["pattern"] == {"scale": 3.0}
    props = r.get_properties()
    assert "Reset Fill to type" not in props and "Reset Pattern to type" in props


def test_missing_type_shows_question_mark(qapp):
    ft.set_project_table(ft.FillTypeTable())
    r = _square()
    r.set_fill_type("deadbeefcafe")
    assert r.get_properties()["Fill Type"]["value"].startswith("? ")
