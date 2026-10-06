"""LT4 H4-a: one Block Editor capability slot (tile | repeat)."""
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.model_space import Model_Space


def _sc():
    proj = Model_Space()
    return BlockEditorWidget(proj).editor_scene


def test_repeat_slot_views_and_undo(qapp):
    sc = _sc()
    sc.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}))
    assert sc.block_repeat == {"length": 9.0, "size": "drafting"}
    assert sc.block_tile is None
    sc.set_block_capability(("repeat", {"length": 12.0, "size": "drafting"}))
    sc.undo()
    assert sc.block_repeat["length"] == 9.0
    sc.undo()
    assert sc.block_capability is None and sc.capability_frame_item() is None


def test_views_are_copies(qapp):
    sc = _sc()
    sc.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}))
    sc.block_repeat["length"] = 1.0
    assert sc.block_repeat["length"] == 9.0


def test_legacy_block_tile_snapshot_restores(qapp):
    sc = _sc()
    state = sc._capture_network()
    state.pop("block_capability")
    state["block_tile"] = {"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"}
    sc._restore_network(state)
    assert sc.block_tile["w"] == 5.0
