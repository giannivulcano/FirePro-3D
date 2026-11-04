"""Leader panel rows on paper and in editors (design D6, spec edge case)."""
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import (
    PaperScene, Sheet, _text_panel_change, _text_panel_properties,
)
from firepro3d.text_item import TextAnnotationData, TextItem


def _paper():
    from tests.test_paper_annotations import _stub_resolver
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    return scene, scene.add_annotation(TextAnnotationData(
        text="n", x=20.0, y=20.0, wrap_width_mm=30.0, box_height_mm=10.0))


def test_paper_form_replaces_the_placeholder_with_a_toggle(qapp):
    rows = _text_panel_properties(TextAnnotationData(text="n"))
    assert rows["Leader"]["type"] == "bool" and rows["Leader"]["value"] is False
    assert "Leader End" not in rows
    assert list(rows)[-1] == "Leader"          # the row keeps its place: last


def test_toggle_on_seeds_a_default_and_off_drops_it(qapp):
    sc = Model_Space(scene_role="block_editor")
    item = TextItem(TextAnnotationData(text="n", wrap_width_mm=30.0, box_height_mm=10.0))
    sc.addItem(item)
    item.set_property("Leader", True)
    assert item.data.leader["edge"] == "R"
    assert "Leader End" in item.get_properties()
    assert "Leader Weight" in item.get_properties()
    item.set_property("Leader", False)
    assert item.data.leader is None


def test_paper_change_writes_the_leader_field(qapp):
    d = TextAnnotationData(text="n", wrap_width_mm=30.0, box_height_mm=10.0)
    assert set(_text_panel_change(d, "Leader", False) or {}) == set()


def test_paper_toggle_is_one_undo_step_and_drops_then_restores(qapp):
    scene, item = _paper()
    idx0 = scene.undo_stack.index()
    item.set_property("Leader", True)
    assert item.data.leader is not None and item.data.leader["edge"] == "R"
    assert scene.undo_stack.index() == idx0 + 1
    rows = item.get_properties()
    assert list(rows)[-3:] == ["Leader", "Leader End", "Leader Weight"]
    scene.undo_stack.undo()
    assert item.data.leader is None
    scene.undo_stack.redo()
    assert item.data.leader is not None
    item.set_property("Leader", False)
    assert item.data.leader is None
    scene.undo_stack.undo()
    assert item.data.leader is not None


def test_paper_weight_and_end_rows_write_the_record_through_undo(qapp):
    scene, item = _paper()
    item.set_property("Leader", True)
    names = item.get_properties()["Leader Weight"]["options"]
    pick = names[-1]
    item.set_property("Leader Weight", pick)
    assert item.data.leader["weight"] == pick
    item.set_property("Leader End", "None")
    assert item.data.leader["end"] == "none"
    scene.undo_stack.undo()
    assert item.data.leader["end"] != "none"
    scene.undo_stack.undo()
    assert item.data.leader["weight"] != pick


def test_a_grip_drag_after_an_undone_toggle_does_not_alias_the_command(qapp):
    scene, item = _paper()
    item.set_property("Leader", True)
    scene.undo_stack.undo()
    scene.undo_stack.redo()
    tip0 = item.data.leader["tip_x"]
    item.data.leader["tip_x"] += 50.0          # a live in-place edit
    scene.undo_stack.undo()
    scene.undo_stack.redo()
    assert item.data.leader["tip_x"] == tip0   # redo restores the command's own record
