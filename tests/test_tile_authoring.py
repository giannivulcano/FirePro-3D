"""Block Editor pattern-tile authoring (hatch D-A32/D-A34, HD4a)."""
from PyQt6.QtCore import QPointF, Qt

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _editor_with(prims=()):
    proj = Model_Space()
    w = BlockEditorWidget(proj)
    for d in prims:
        w._add_primitive(LineItem.from_dict(d))
    return proj, w


def test_toggle_seeds_frame_from_content_extents(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(20, -8)).to_dict()])
    assert w.toggle_pattern_tile()
    t = w.editor_scene.block_tile
    assert (t["w"], t["h"], t["row_shift"], t["size"]) == (20.0, 8.0, 0.0, "drafting")
    assert w.editor_scene.tile_frame_item() is not None


def test_empty_block_seeds_10x10(qapp):
    proj, w = _editor_with()
    w.toggle_pattern_tile()
    assert (w.editor_scene.block_tile["w"], w.editor_scene.block_tile["h"]) == (10.0, 10.0)


def test_tile_saved_on_commit_and_undoable(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    w.toggle_pattern_tile()                       # one undo step (w = 5)
    sc = w.editor_scene
    sc.set_block_tile({**sc.block_tile, "w": 7.0})  # one undo step (w = 7)
    sc.undo()
    assert sc.block_tile["w"] == 5.0
    assert sc.tile_frame_item().grip_points()[0] == QPointF(5.0, -5.0)
    defn = w.commit_block("Zig", "L", "S")
    assert defn.tile["w"] == 5.0


def test_undo_past_toggle_removes_frame_and_reopen_restores_it(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    sc = w.editor_scene
    w.toggle_pattern_tile()
    frame = sc.tile_frame_item()
    sc.undo()
    assert sc.block_tile is None and sc.tile_frame_item() is None
    assert frame.scene() is None
    sc.redo()
    assert sc.block_tile["w"] == 5.0 and sc.tile_frame_item().scene() is sc
    defn = w.commit_block("Zig", "L", "S")
    w2 = BlockEditorWidget(proj, block_id=defn.id)
    w2.seed_from_definition(defn)
    assert w2.editor_scene.block_tile == defn.tile
    assert w2.editor_scene.tile_frame_item() is not None
    w2.editor_scene.undo()                        # the seed is the baseline
    assert w2.editor_scene.block_tile == defn.tile


def test_tile_on_refused_for_a_placed_symbol(qapp):
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    proj.register_block_definition(d)
    proj.place_block_instance(d.id, (0.0, 0.0))
    w = BlockEditorWidget(proj, block_id=d.id)
    w.seed_from_definition(d)
    assert w.toggle_pattern_tile() is False
    assert w.editor_scene.block_tile is None


def test_tile_on_refused_for_a_nested_symbol(qapp):
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    proj.register_block_definition(d)
    host = BlockDefinition.new(name="Host", library="L", series="S", origin=(0, 0),
                               primitives=[{"type": "block_instance", "block_id": d.id,
                                            "pos": [0.0, 0.0], "rotation": 0.0}])
    proj.register_block_definition(host)
    w = BlockEditorWidget(proj, block_id=d.id)
    w.seed_from_definition(d)
    assert w.toggle_pattern_tile() is False
    assert w.editor_scene.block_tile is None


def test_frame_survives_delete_and_is_not_gathered(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    frame = sc.tile_frame_item()
    frame.setSelected(True)
    pos0 = sc._undo_pos
    sc.delete_selected_items()
    assert sc.tile_frame_item() is frame and frame.scene() is sc
    assert sc._undo_pos == pos0, "a frame-only delete must not push an empty step"
    assert frame not in w.gather_primitives()
    # Mixed selection: the line goes, the frame stays.
    line = w.gather_primitives()[0]
    line.setSelected(True)
    frame.setSelected(True)
    sc.delete_selected_items()
    assert w.gather_primitives() == [] and frame.scene() is sc
    assert sc._undo_pos == pos0 + 1


def test_frame_is_not_a_snap_target(qapp):
    from firepro3d import snap_engine
    proj, w = _editor_with()
    w.toggle_pattern_tile()
    frame = w.editor_scene.tile_frame_item()
    assert frame.data(0) in snap_engine._NON_TARGET_TAGS


def test_manipulator_renders_frame_grips_after_real_selection(qapp):
    """U3 lesson: the live manipulator (not a direct manip_handles() call)
    shows the two frame grips once the frame is selected."""
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(20, -8)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    frame = sc.tile_frame_item()
    frame.setSelected(True)
    qapp.processEvents()
    m = sc._live_manip()
    assert m.isVisible()
    hosts = [h for h in m._host_pool if h.isVisible()]
    assert len(hosts) == 2
    want = {(20.0, -8.0), (0.0, -8.0)}
    got = {(round(h.scenePos().x(), 6), round(h.scenePos().y(), 6)) for h in hosts}
    assert got == want


def test_corner_grip_drag_is_one_undo_step(qapp):
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(20, -8)).to_dict()])
    w.toggle_pattern_tile()
    sc = w.editor_scene
    sc._snap_enabled = False
    frame = sc.tile_frame_item()
    frame.setSelected(True)
    qapp.processEvents()
    m = sc._live_manip()
    h = [x.handle for x in m._host_pool if x.isVisible()][0]
    assert h.index == 0
    pos0 = sc._undo_pos
    nm = Qt.KeyboardModifier.NoModifier
    m._begin_handle(h, QPointF(20, -8), QPointF(0, 0))
    m._update(QPointF(31, -12), nm, QPointF(200, 200))
    m._finish(QPointF(31, -12), nm)
    t = sc.block_tile
    assert (round(t["w"], 6), round(t["h"], 6)) == (31.0, 12.0)
    assert sc._undo_pos == pos0 + 1
    sc.undo()
    assert (sc.block_tile["w"], sc.block_tile["h"]) == (20.0, 8.0)


def test_panel_rows_edit_the_tile(qapp):
    from firepro3d.block_properties_info import BlockPropertiesInfo
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    info = BlockPropertiesInfo(w.editor_scene, "Zig", editor=w)
    assert info.get_properties()["Pattern tile"]["value"] is False
    info.set_property("Pattern tile", True)
    props = info.get_properties()
    assert props["Pattern tile"]["value"] is True
    assert props["Width"]["value_mm"] == 5.0 and props["Width"]["tooltip"]
    info.set_property("Width", 12.0)
    info.set_property("Row shift", 3.0)
    info.set_property("Size", "Model")
    assert w.editor_scene.block_tile == {"w": 12.0, "h": 5.0, "row_shift": 3.0,
                                         "size": "model"}
    info.set_property("Pattern tile", False)
    assert w.editor_scene.block_tile is None


def test_panel_rows_carry_tooltips(qapp):
    from PyQt6.QtWidgets import QLabel
    from firepro3d.block_properties_info import BlockPropertiesInfo
    from firepro3d.property_manager import PropertyManager
    proj, w = _editor_with([LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    w.toggle_pattern_tile()
    pm = PropertyManager()
    pm.show_properties(BlockPropertiesInfo(w.editor_scene, "Zig", editor=w))
    qapp.processEvents()
    tips = {l.text(): l.toolTip() for l in pm.findChildren(QLabel)}
    for key in ("Pattern tile", "Width", "Height", "Row shift", "Size"):
        assert tips.get(key), key


def test_place_click_refused_when_block_became_a_pattern(qapp):
    """Edge case: place_block armed, then the block is saved as a pattern in
    the Block Editor — the next click places nothing and leaves the mode."""
    proj = Model_Space()
    d = BlockDefinition.new(name="Sym", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()])
    proj.register_block_definition(d)
    proj.set_mode("place_block", template=d.id)
    assert proj.mode == "place_block"
    w = BlockEditorWidget(proj, block_id=d.id)
    w.seed_from_definition(d)
    assert w.toggle_pattern_tile()
    w.commit_block("Sym", "L", "S")
    assert proj.get_block_definition(d.id).tile is not None
    p = QPointF(100.0, 100.0)
    proj._press_place_block(None, p, p, None, None, None)
    assert proj.instance_count(d.id) == 0
    assert proj.mode != "place_block"


def test_pattern_badge_is_cached_per_dpr(qapp):
    from firepro3d import blocks_browser
    a = blocks_browser._pattern_badge(1.0)
    assert blocks_browser._pattern_badge(1.0) is a
    b = blocks_browser._pattern_badge(2.0)
    assert b is not a
    pm = b.pixmap(blocks_browser._BADGE_PX, blocks_browser._BADGE_PX)
    assert not pm.isNull()
