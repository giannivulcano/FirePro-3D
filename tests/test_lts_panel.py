"""LTS-1 / LTS-5 / LTS-9a -- the On screen row, the Fixed seed, one undo step."""
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.capability_panel import capability_rows, set_capability_property
from firepro3d.model_space import Model_Space


def _lt():
    w = BlockEditorWidget(Model_Space())
    w.toggle_capability("repeat")
    return w, w.editor_scene


def test_turning_linetype_on_seeds_fixed(qapp):
    _, sc = _lt()
    assert sc.block_repeat.get("screen") == "fixed"
    r = capability_rows(sc)
    assert r["On screen"]["value"] == "Fixed size"
    assert r["On screen"]["options"] == ["Fixed size", "Scale with zoom"]
    assert r["On screen"]["tooltip"]
    keys = list(r)
    assert keys.index("On screen") == keys.index("Size") + 1     # under Size


def test_on_screen_row_edit_is_one_undo_step(qapp):
    w, sc = _lt()
    set_capability_property(sc, w, "On screen", "Scale with zoom")
    assert "screen" not in sc.block_repeat
    assert capability_rows(sc)["On screen"]["value"] == "Scale with zoom"
    sc.undo()
    assert sc.block_repeat.get("screen") == "fixed"
    sc.redo()
    assert "screen" not in sc.block_repeat
    set_capability_property(sc, w, "On screen", "Fixed size")
    assert sc.block_repeat.get("screen") == "fixed"


def test_same_value_is_not_an_undo_step(qapp):
    w, sc = _lt()
    set_capability_property(sc, w, "On screen", "Fixed size")    # no change
    sc.undo()                                  # undoes the toggle itself
    assert sc.block_repeat is None
