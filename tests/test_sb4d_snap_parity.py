"""SB4d D5 side effect: the annotation band keeps every item's pre-band snap
eligibility (snap_engine.is_snap_target, the one rule find() and the
grip session share)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.snap_engine import is_snap_target
from tests._sb4d_helpers import dispose, plan_scene, tag_def


def test_band_items_keep_their_pre_band_snap_eligibility(qapp):
    from firepro3d.gridline import GridlineItem
    from firepro3d.node import Node
    from firepro3d.room import Room
    from firepro3d.text_item import TextAnnotationData, TextItem
    from firepro3d.water_supply import WaterSupply
    ms, sec, det, tabs = plan_scene()
    try:
        ms._level_manager.get("Level 3").elevation = 20000.0       # a tall project
        text = TextItem(TextAnnotationData(text="NOTE", x=500.0, y=500.0))
        ms.addItem(text)
        ms._texts.append(text)
        inst = ms.place_block_instance(tag_def(ms).id, (4000.0, 0.0))
        room = Room([QPointF(0, 0), QPointF(6000, 0), QPointF(6000, 4000), QPointF(0, 4000)])
        room.level, room.name = "Level 1", "Office"
        ms.addItem(room)
        ms._rooms.append(room)
        gl = GridlineItem(QPointF(-1000.0, -1000.0), QPointF(-1000.0, 9000.0), label="1")
        ms._gridlines.append(gl)
        ms.addItem(gl)
        dmk = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        ws = WaterSupply(4000.0, 4000.0)
        ws.level = "Level 3"
        ms.addItem(ws)
        ms.water_supply_node = ws
        top, bot = Node(7000.0, 500.0), Node(7000.0, 500.0)   # ms.add_node would merge two coincident nodes
        for n in (top, bot):
            ms.addItem(n)
            ms.sprinkler_system.add_node(n)
        riser_pipe = ms.add_pipe(top, bot)   # add_pipe propagates the ceiling: set the heights after it
        for n, z in ((top, 3000.0), (bot, 0.0)):
            n.ceiling_level, n.ceiling_offset = "Level 1", z
            n.z_pos = z
        riser_pipe.update_label()
        ms._level_manager.apply_to_scene(ms)
        ws.setVisible(True)           # apply_to_scene hides a Level 3 item while Level 1 is active
        riser = riser_pipe._riser_symbol
        assert riser is not None and riser.isVisible()            # precondition (not vacuous)
        assert text.zValue() > 150 and inst.zValue() > 150 and ws.zValue() > 150
        assert riser.zValue() < 150
        assert is_snap_target(text, skip_pipes=False)              # was z 15
        assert is_snap_target(inst, skip_pipes=False)              # was elevation + 0.6
        assert is_snap_target(ws, skip_pipes=False)                # was 50; now 200.55
        assert not is_snap_target(riser, skip_pipes=False)         # was 200
        assert not is_snap_target(room._tag, skip_pipes=False)     # was a child
        assert not is_snap_target(gl, skip_pipes=False)            # was 500
        assert not is_snap_target(dmk, skip_pipes=False)           # was 500
    finally:
        dispose(ms, sec, tabs)
