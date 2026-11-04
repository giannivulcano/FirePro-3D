"""SB4d guard 1 (Q21): after apply_to_scene every annotation's effective z
(top-level ancestor -- Qt child z is local) is above every model item's, in
the Q15 sub-order text < tags + labels + badge < gridlines + bubbles <
view markers. Numbers: Z_ANNOT_* (constants.py); a 20 m wall top is
20000 * Z_ELEV_SCALE + Z_CAT_WALL = 200.3, above the pre-SB4d Z_OVERLAY 200."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.constants import (Z_ANNOT_GRID, Z_ANNOT_MARKER, Z_ANNOT_TAG,
                                 Z_ANNOT_TEXT, Z_CAT_NODE, Z_CAT_WALL, Z_ELEV_SCALE)
from tests._sb4d_helpers import dispose, plan_scene, tag_def, top_z, wall


def test_p4_sprinkler_is_a_node_child(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        n = ms.add_node(0.0, 0.0)
        n.add_sprinkler()
        assert n.sprinkler is not None and n.sprinkler.parentItem() is n
    finally:
        dispose(ms, sec, tabs)


def test_guard1_every_annotation_draws_above_every_model_item_in_sub_order(qapp):
    from firepro3d.gridline import GridlineItem
    from firepro3d.room import Room
    from firepro3d.text_item import TextAnnotationData, TextItem
    from firepro3d.water_supply import WaterSupply
    ms, sec, det, tabs = plan_scene()
    try:
        tall = wall(ms, top_offset=20000.0)
        upper = wall(ms, base="Level 2", top="Level 3", top_offset=0.0, y=5000.0)
        room = Room([QPointF(0, 0), QPointF(6000, 0), QPointF(6000, 4000), QPointF(0, 4000)])
        room.level, room.name = "Level 1", "Office"
        ms.addItem(room)
        ms._rooms.append(room)
        inst = ms.place_block_instance(tag_def(ms).id, (4000.0, 0.0))
        pipe = ms.add_pipe(ms.add_node(0.0, 1000.0), ms.add_node(3000.0, 1000.0))
        for n in (pipe.node1, pipe.node2):
            n.z_pos = 2997.2                                 # Level 1 ceiling - 50.8
        pipe.update_label()
        node = pipe.node1
        node.add_sprinkler()
        node.create_hydraulic_badge(1, 50.0, 40.0, 10.0, 10.0)
        gl = GridlineItem(QPointF(-1000.0, -1000.0), QPointF(-1000.0, 9000.0), label="1")
        ms._gridlines.append(gl)
        ms.addItem(gl)
        dmk = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        smk = sec.place_section(QPointF(0.0, -2000.0), QPointF(6000.0, -2000.0))
        text = TextItem(TextAnnotationData(text="NOTE", x=500.0, y=500.0))
        ms.addItem(text)
        ms._texts.append(text)
        ws = WaterSupply(4000.0, 4000.0)
        ws.level = "Level 1"
        ms.addItem(ws)
        ms.water_supply_node = ws
        ms._level_manager.apply_to_scene(ms)

        assert tall.zValue() == pytest.approx(20000.0 * Z_ELEV_SCALE + Z_CAT_WALL)   # 200.3
        model = [tall, upper, room, pipe, node, node.sprinkler, ws]
        texts = [text]
        tags = [inst, room._tag, pipe.label, node._hydraulic_badge]
        grids = [gl, gl.bubble1, gl.bubble2]
        markers = [dmk, smk]
        top_model = max(top_z(i) for i in model)
        for it in texts + tags + grids + markers:
            assert top_z(it) > top_model, type(it).__name__
        assert {top_z(i) for i in texts} == {Z_ANNOT_TEXT}
        assert {top_z(i) for i in tags} == {Z_ANNOT_TAG}
        assert {top_z(i) for i in grids} == {Z_ANNOT_GRID}
        assert {top_z(i) for i in markers} == {Z_ANNOT_MARKER}
        assert Z_ANNOT_TEXT < Z_ANNOT_TAG < Z_ANNOT_GRID < Z_ANNOT_MARKER
        assert ms.items(QPointF(4000.0, 0.0))[0] is inst      # Qt stacking: the tag over the 20 m wall
    finally:
        dispose(ms, sec, tabs)


def test_guard1_sprinkler_sits_between_a_lower_wall_and_a_higher_levels_wall(qapp):
    """Sprinklers stay model (D5: Node children, no row): effective z = the
    node's 2997.2 * 0.01 + Z_CAT_NODE = 30.472 -- above a 1.2 m Level-1
    partition (1200 * 0.01 + 0.3 = 12.3), below a Level-2 wall topping at
    Level 3 (6096 * 0.01 + 0.3 = 61.26)."""
    ms, sec, det, tabs = plan_scene()
    try:
        low = wall(ms, top_offset=1200.0)
        high = wall(ms, base="Level 2", top="Level 3", top_offset=0.0, y=3000.0)
        n = ms.add_node(500.0, 500.0)
        n.z_pos = 2997.2
        n.add_sprinkler()
        ms._level_manager.apply_to_scene(ms)
        spr = top_z(n.sprinkler)
        assert spr == pytest.approx(2997.2 * Z_ELEV_SCALE + Z_CAT_NODE)
        assert low.zValue() == pytest.approx(12.3)
        assert high.zValue() == pytest.approx(61.26)
        assert low.zValue() < spr < high.zValue()
    finally:
        dispose(ms, sec, tabs)
