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


_TILE = {"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"}
_REP = {"length": 9.0, "size": "drafting"}


def _frames(sc):
    from firepro3d.capability_frame import CAPABILITY_FRAME_TAG
    return [i for i in sc.items() if i.data(0) == CAPABILITY_FRAME_TAG]


def test_undo_redo_across_a_kind_switch(qapp):
    """Review G3 M6a: tile -> repeat; undo restores the TileFrame, redo the
    RepeatFrame -- always exactly one frame in the scene."""
    from firepro3d.repeat_frame import RepeatFrame
    from firepro3d.tile_frame import TileFrame
    sc = _sc()
    sc.set_block_capability(("tile", _TILE))
    sc.set_block_capability(("repeat", _REP))
    assert isinstance(sc.capability_frame_item(), RepeatFrame)
    assert len(_frames(sc)) == 1
    sc.undo()
    assert sc.block_tile == _TILE and sc.block_repeat is None
    assert isinstance(sc.capability_frame_item(), TileFrame)
    assert sc.tile_frame_item() is sc.capability_frame_item()
    assert _frames(sc) == [sc.capability_frame_item()]
    sc.redo()
    assert sc.block_repeat == _REP and sc.block_tile is None
    assert isinstance(sc.capability_frame_item(), RepeatFrame)
    assert sc.tile_frame_item() is None
    assert _frames(sc) == [sc.capability_frame_item()]


def test_set_after_scene_clear_adds_a_live_frame(qapp):
    """Review G3 M6b: scene.clear() sweeps (sip-deletes) the frame; the next
    set builds a fresh live frame in the scene, same kind or other."""
    from PyQt6 import sip
    sc = _sc()
    for first, second in ((("repeat", _REP), ("repeat", _REP)),
                          (("repeat", _REP), ("tile", _TILE))):
        sc.set_block_capability(first, push_undo=False)
        old = sc.capability_frame_item()
        sc.clear()
        assert sip.isdeleted(old)
        sc.set_block_capability(second, push_undo=False)
        f = sc.capability_frame_item()
        assert f is not None and not sip.isdeleted(f) and f.scene() is sc
        assert f.KIND == second[0]
        assert _frames(sc) == [f]
