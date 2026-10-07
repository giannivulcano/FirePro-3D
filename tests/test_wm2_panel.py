"""WM2 Q4/Q5/Q12 panel rows + G11 mixed selection."""
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.geometry_2d import LineItem
from tests.lt3_support import make_linetype
from tests.wm2_support import scene_with, sprinkler_def


def test_rows_and_options(qapp):
    lt = make_linetype()
    s = sprinkler_def()
    ms, inst = scene_with([lt, s], s.id)
    props = inst.get_properties()
    keys = list(props)
    assert keys.index("Linetype") == keys.index("Rotation") + 1
    assert keys.index("Weight") == keys.index("Linetype") + 1
    w = props["Weight"]
    assert w["value"] == "As Authored"
    assert w["options"][:2] == ["As Authored",
                                f"By Category ({pd.picker_weight_name(pd.model_blocks_weight())})"]
    assert not any(o.startswith("By Linetype") for o in w["options"])
    assert w["options"][2:] == pd.weight_names()
    lto = props["Linetype"]["options"]
    assert lto[0] == "As Authored" and "Continuous" in lto and "Hidden" in lto
    assert props["Linetype"]["value"] == "As Authored"
    assert props["Weight"]["tooltip"] and props["Linetype"]["tooltip"]


def test_rows_show_stored_override(qapp):
    lt = make_linetype()
    s = sprinkler_def()
    ms, inst = scene_with([lt, s], s.id, {"weight": "by_category",
                                          "linetype": lt.id})
    props = inst.get_properties()
    assert props["Weight"]["value"] == props["Weight"]["options"][1]
    assert props["Linetype"]["value"] == "Hidden"
    inst.set_overrides({"weight": "Thick"})
    assert inst.get_properties()["Weight"]["value"] == "Thick"


def test_set_property_applies_and_ignores_foreign_labels(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    inst.set_property("Weight", "Thick")
    assert inst.overrides["weight"] == "Thick"
    inst.set_property("Weight", "By Linetype (Thin)")       # primitive label
    assert inst.overrides["weight"] == "Thick"
    inst.set_property("Weight", "No Such Weight")
    assert inst.overrides["weight"] == "Thick"
    inst.set_property("Weight", inst.get_properties()["Weight"]["options"][1])
    assert inst.overrides["weight"] == "by_category"
    inst.set_property("Linetype", "Continuous")
    assert inst.overrides["linetype"] == "continuous"
    inst.set_property("Linetype", "Missing (abc)")
    assert inst.overrides["linetype"] == "continuous"
    inst.set_property("Linetype", "As Authored")
    assert inst.overrides["linetype"] == "as_authored"


def test_set_property_pushes_one_undo_step_and_noop_pushes_none(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ms.push_undo_state()
    before = ms._undo_pos
    inst.set_property("Weight", "Thick")
    assert ms._undo_pos == before + 1
    inst.set_property("Weight", "Thick")                     # no-op commit
    assert ms._undo_pos == before + 1


def test_g11_mixed_selection_primitive_ignores_block_labels(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["weight"] = "Thin"
    ln.set_property("Weight", "As Authored")
    ln.set_property("Weight", "By Category (Thinnest)")
    assert ln.style["weight"] == "Thin"
    for t in (inst, ln):
        t.set_property("Weight", "Thick")
    assert inst.overrides["weight"] == "Thick" and ln.style["weight"] == "Thick"


def test_q12_rows_locked_in_capability_editor(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    assert not inst.get_properties()["Weight"].get("disabled")
    ms.set_block_tile({"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"},
                     push_undo=False)
    props = inst.get_properties()
    assert props["Linetype"].get("disabled") and props["Weight"].get("disabled")
    assert props["Weight"]["tooltip"] == props["Linetype"]["tooltip"]
    assert "pattern" in props["Weight"]["tooltip"]


def test_q12_rows_locked_in_linetype_unit_editor(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ms.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}),
                            push_undo=False)
    props = inst.get_properties()
    assert props["Linetype"].get("disabled") and props["Weight"].get("disabled")
